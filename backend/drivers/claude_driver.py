"""ClaudeDriver — planning runs via the Claude Agent SDK (spec §3).

Writes the composed manifest to the run workdir as AGENTS.md, runs the agent with its
migrated body as the system prompt and the platform-state MCP server wired in, and maps
the message stream to a RunResult. `query_fn` is injectable so the mapping is testable
without the network. `run_build_task` is Phase 2.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import claude_agent_sdk
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

from .base import ArtifactDraft, RunResult

# The SDK moved the "which CLI to launch" setting between versions: newer builds accept it as
# ClaudeAgentOptions(cli_path=...); older ones only via SubprocessCLITransport(cli_path=...).
# Detect which the *installed* SDK supports so we pin the CLI correctly on either — the daemon
# machine and the server/CI can legitimately run different SDK versions.
_OPTIONS_ACCEPTS_CLI_PATH = "cli_path" in inspect.signature(ClaudeAgentOptions).parameters

if TYPE_CHECKING:
    from apps.registry.models import AgentSpec
    from apps.workitems.models import WorkItem

# Suffix of the platform-state tool that registers an artifact. MCP tools are exposed to
# the engine as `mcp__<server>__<tool>`, so we match on the suffix.
_REGISTER_ARTIFACT_TOOL = "register_artifact"

# The agent's instruction body is normally handed to the engine as its system prompt, which the
# SDK passes ON THE COMMAND LINE. Windows caps a process command line at 32,767 chars, so a large
# body (the UX Design agent is ~36 KB) overflows it: CreateProcess fails with WinError 206, which
# the SDK misreports as "Claude Code not found". The fix is to deliver a large body as a FILE
# (AGENTS.md, which Claude Code auto-loads) instead of the command line — see _deliver_body. This
# threshold leaves generous headroom for the rest of the args (mcp-config, allowed-tools, flags).
_MAX_INLINE_BODY_CHARS = 24000

# Generic safety net (NOT the fix above): the engine subprocess can occasionally lose a launch
# race and surface as "Claude Code not found" even though the CLI is present. That happens before
# any message streams, so retrying the whole run a few times never double-processes.
_LAUNCH_RETRIES = 4
_LAUNCH_BACKOFF = 3.0  # seconds; multiplied by the attempt number for an escalating wait


class ClaudeDriver:
    def __init__(
        self,
        *,
        query_fn: Callable | None = None,
        body_loader: Callable[[Any], str] | None = None,
        repo_root: Path | str | None = None,
        workdir_base: Path | str | None = None,
        permission_mode: str = "default",
        cli_path: str | Path | None = None,
    ) -> None:
        # Default to the real SDK; tests inject a fake async generator.
        self._query = query_fn or claude_agent_sdk.query
        self._body_loader = body_loader or self._read_body_file
        self._repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[2]
        self._workdir_base = Path(workdir_base) if workdir_base else None
        # Which Claude Code CLI to launch, in priority order:
        #   explicit cli_path arg  ->  CLAUDE_CLI_PATH env  ->  the `claude` on PATH.
        # Preferring the on-PATH CLI (the user's own install, kept current) means the engine does
        # NOT default to the SDK's *bundled* binary, which is an older build. The resolved path is
        # handed to the engine via ClaudeAgentOptions.cli_path (see below), which the installed
        # SDK honours; the previous transport-level override was silently incompatible with it.
        _cli = cli_path or os.environ.get("CLAUDE_CLI_PATH") or shutil.which("claude")
        self._cli_path = Path(_cli) if _cli else None
        # Engine has no human in the loop — gates are control-plane (#2). Tools are still
        # whitelisted via allowed_tools, so only platform-state tools can run.
        # Use default CLI permission handling in container/root environments to avoid
        # Claude Code rejecting bypassPermissions under sudo/root.
        self._permission_mode = permission_mode

    # ── body resolution ────────────────────────────────────────────
    def _read_body_file(self, agent_spec: AgentSpec) -> str:
        path = Path(agent_spec.body_ref)
        if not path.is_absolute():
            path = self._repo_root / agent_spec.body_ref
        return path.read_text(encoding="utf-8")

    # ── workdir ────────────────────────────────────────────────────
    def _prepare_workdir(self, work_item: WorkItem) -> Path:
        base = self._workdir_base or Path(tempfile.mkdtemp(prefix="sdlc-run-"))
        workdir = base / f"wi-{work_item.id}"
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir

    # ── engine options ─────────────────────────────────────────────
    def _agent_options(self, **kwargs) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions, pinning the resolved CLI via the field the installed SDK
        supports (newer SDKs accept options.cli_path; older SDKs get it via an explicit
        transport in _consume). This is what keeps the engine off the SDK's bundled binary."""
        if self._cli_path is not None and _OPTIONS_ACCEPTS_CLI_PATH:
            kwargs["cli_path"] = str(self._cli_path)
        return ClaudeAgentOptions(**kwargs)

    # ── body delivery ──────────────────────────────────────────────
    def _deliver_body(self, body: str, manifest: str) -> tuple[str | None, str]:
        """Decide how the agent's instruction body reaches the engine, and what goes in AGENTS.md.

        The body is normally passed as the engine's system prompt, which the SDK puts on the
        process command line — capped at 32,767 chars on Windows. A large body (the UX Design
        agent is ~36 KB) overflows that and the launch fails with WinError 206, which the SDK
        misreports as 'Claude Code not found'. So when the body is large we deliver it as a FILE:
        prepend it to AGENTS.md (which Claude Code auto-loads from the working dir as authoritative
        instructions) and keep it off the command line. Small bodies stay as the system prompt,
        exactly as before. Returns (system_prompt, agents_md_contents)."""
        if len(body) <= _MAX_INLINE_BODY_CHARS:
            return body, manifest
        agents_md = (
            f"{body}\n\n"
            "<!-- The section above is your agent role and operating instructions; treat it as "
            "authoritative. Your run context (project profile, work item, artifacts) follows. -->"
            "\n\n---\n\n"
            f"{manifest}"
        )
        return None, agents_md

    # ── planning ───────────────────────────────────────────────────
    async def run_planning_task(
        self,
        *,
        manifest: str,
        agent_spec: AgentSpec,
        mcp_servers: dict,
        allowed_tools: list[str],
        work_item: WorkItem,
    ) -> RunResult:
        workdir = self._prepare_workdir(work_item)
        system_prompt, agents_md = self._deliver_body(self._body_loader(agent_spec), manifest)
        (workdir / "AGENTS.md").write_text(agents_md, encoding="utf-8")

        options = self._agent_options(
            system_prompt=system_prompt,
            mcp_servers=mcp_servers,
            allowed_tools=allowed_tools,
            cwd=str(workdir),
            model=(agent_spec.recommended_model or None),
            permission_mode=self._permission_mode,
        )
        prompt = self._build_prompt(agent_spec, work_item)
        return await self._consume(prompt, options)

    async def _consume(self, prompt: str, options: ClaudeAgentOptions) -> RunResult:
        """Run the engine, retrying a few times on a transient launch failure — a lost spawn race
        that the SDK surfaces as 'Claude Code not found' even though the CLI exists. The failure
        happens before any message streams, so retrying the whole run never double-processes. The
        known large-body overflow is prevented upstream by _deliver_body, not by this retry."""
        last_exc: Exception | None = None
        for attempt in range(_LAUNCH_RETRIES):
            try:
                return await self._consume_stream(prompt, options)
            except Exception as exc:  # noqa: BLE001
                if self._looks_like_launch_failure(exc):
                    self._log_launch_diagnostic(exc, options, attempt)
                if attempt + 1 < _LAUNCH_RETRIES and self._is_transient_launch_error(exc):
                    last_exc = exc
                    await asyncio.sleep(_LAUNCH_BACKOFF * (attempt + 1))
                    continue
                raise
        assert last_exc is not None  # loop only exits early via return/raise
        raise last_exc

    @staticmethod
    def _looks_like_launch_failure(exc: Exception) -> bool:
        msg = str(exc).lower()
        return "claude code not found" in msg or "failed to start claude code" in msg

    def _log_launch_diagnostic(self, exc: Exception, options: ClaudeAgentOptions,
                               attempt: int) -> None:
        """The SDK hides the real OS error behind a generic 'Claude Code not found'. Surface the
        raw exception chain (winerror/filename), the CLI, and the working dir to the companion's
        log so a launch failure is actually diagnosable."""
        cwd = getattr(options, "cwd", None)
        cli = self._cli_path
        lines = [
            f"[claude-driver] engine launch failed (attempt {attempt + 1}/{_LAUNCH_RETRIES})",
            f"  cli_path={cli!r} exists={bool(cli) and Path(cli).exists()}",
            f"  cwd={cwd!r} exists={bool(cwd) and Path(str(cwd)).exists()} "
            f"is_dir={bool(cwd) and Path(str(cwd)).is_dir()}",
        ]
        cur: BaseException | None = exc
        depth = 0
        while cur is not None and depth < 8:
            lines.append(
                f"  cause[{depth}] {type(cur).__name__}: "
                f"winerror={getattr(cur, 'winerror', None)} errno={getattr(cur, 'errno', None)} "
                f"filename={getattr(cur, 'filename', None)} :: {str(cur)[:180]}"
            )
            cur = cur.__cause__ or cur.__context__
            depth += 1
        print("\n".join(lines), file=sys.stderr, flush=True)

    def _is_transient_launch_error(self, exc: Exception) -> bool:
        """A lost launch race is reported as 'Claude Code not found at: <path>'. Treat it as
        transient (worth a retry) ONLY when the CLI actually exists on disk — a genuinely missing
        CLI must fail fast, not spin. (Command-line-length overflows can't reach here: large
        bodies are delivered as a file by _deliver_body before launch.)"""
        msg = str(exc).lower()
        if "claude code not found" not in msg and "failed to start claude code" not in msg:
            return False
        return self._cli_path is not None and Path(self._cli_path).exists()

    async def _consume_stream(self, prompt: str, options: ClaudeAgentOptions) -> RunResult:
        """Run the engine once and map its message stream to a RunResult (shared by planning and
        build). Artifacts the agent registered are observed via the register_artifact tool."""
        raw_messages: list[Any] = []
        text_parts: list[str] = []
        artifacts: list[ArtifactDraft] = []
        cost_usd = 0.0
        final_result: str | None = None
        result_subtype = ""
        # On older SDKs that don't accept cli_path on the options object, pin the CLI via an
        # explicit transport instead — so those versions still avoid the bundled binary.
        transport = None
        if self._cli_path is not None and not _OPTIONS_ACCEPTS_CLI_PATH:
            transport = SubprocessCLITransport(
                prompt=prompt, options=options, cli_path=str(self._cli_path))

        async for message in self._query(prompt=prompt, options=options, transport=transport):
            raw_messages.append(message)
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
                    elif isinstance(block, ToolUseBlock) and block.name.endswith(
                        _REGISTER_ARTIFACT_TOOL
                    ):
                        artifacts.append(self._artifact_from_tool_use(block.input))
            elif isinstance(message, ResultMessage):
                cost_usd = message.total_cost_usd or 0.0
                final_result = message.result
                result_subtype = getattr(message, "subtype", "") or ""

        joined = "".join(text_parts)
        # `result_subtype` travels so callers can tell a normal end ("success") from an
        # abnormal one (e.g. "error_max_turns") instead of silently treating an empty
        # result as a finished phase. "" means no ResultMessage arrived at all.
        outputs = {
            "result": final_result if final_result is not None else joined,
            "text": joined,
            "result_subtype": result_subtype,
        }
        return RunResult(
            outputs=outputs, artifacts=artifacts, cost_usd=cost_usd, raw_messages=raw_messages
        )

    @staticmethod
    def _artifact_from_tool_use(tool_input: dict) -> ArtifactDraft:
        return ArtifactDraft(
            phase=tool_input.get("phase", ""),
            type=tool_input.get("type", ""),
            sor=tool_input.get("sor", "internal"),
            content_hash=tool_input.get("content_hash", "") or "",
            s3_key=tool_input.get("s3_key"),
            external_ref=tool_input.get("external_ref"),
            raw=dict(tool_input),
        )

    @staticmethod
    def _build_prompt(agent_spec: AgentSpec, work_item: WorkItem) -> str:
        phase = getattr(agent_spec, "phase_label", "") or getattr(agent_spec, "key", "")
        return (
            f"Execute the '{phase}' phase for WorkItem {work_item.id}. Your composed project "
            "manifest is in AGENTS.md in the working directory. Read your inputs and register "
            "your outputs using the platform-state tools. Do not push to any system-of-record; "
            "the platform handles gates and publishing."
        )

    # ── build (Phase 2) ────────────────────────────────────────────
    async def run_build_task(
        self,
        *,
        manifest: str,
        agent_spec: AgentSpec,
        repo_workspace: Path,
        mcp_servers: dict,
        allowed_tools: list[str],
        work_item: WorkItem,
    ) -> RunResult:
        """Run the build agent against a git **worktree** (the companion provisions it; D9).
        The composed manifest is written to `.sdlc/AGENTS.md` (kept out of the diff by the
        worktree's local exclude) and the agent works in `repo_workspace`. The agent edits +
        tests; it never runs git — the platform commits/pushes/opens the PR (D2)."""
        repo_workspace = Path(repo_workspace)
        sdlc = repo_workspace / ".sdlc"
        sdlc.mkdir(parents=True, exist_ok=True)
        system_prompt, agents_md = self._deliver_body(self._body_loader(agent_spec), manifest)
        (sdlc / "AGENTS.md").write_text(agents_md, encoding="utf-8")

        options = self._agent_options(
            system_prompt=system_prompt,
            mcp_servers=mcp_servers,
            allowed_tools=allowed_tools,
            cwd=str(repo_workspace),
            model=(agent_spec.recommended_model or None),
            permission_mode=self._permission_mode,
        )
        prompt = self._build_build_prompt(agent_spec, work_item)
        return await self._consume(prompt, options)

    @staticmethod
    def _build_build_prompt(agent_spec: AgentSpec, work_item: WorkItem) -> str:
        phase = getattr(agent_spec, "phase_label", "") or getattr(agent_spec, "key", "")
        return (
            f"Execute the '{phase}' phase for WorkItem {work_item.id} in the current git "
            "worktree (your working directory). Your composed project manifest is in "
            ".sdlc/AGENTS.md. Implement the change with full tests and run them locally. "
            "Register your outputs with the platform-state tools. Do NOT run git or open a "
            "pull request — the platform commits, pushes, and opens the PR after your run."
        )

    # ── code review (Phase 2 — read-only, server-side; D2) ──────────
    async def run_review_task(
        self,
        *,
        manifest: str,
        agent_spec: AgentSpec,
        mcp_servers: dict,
        allowed_tools: list[str],
        work_item: WorkItem,
    ) -> RunResult:
        """Run the migrated Code Review agent (08) over a PR. Read-only and server-side — it
        reasons over the diff carried in the manifest and reads context via the platform-state
        tools; it never edits code, runs git, or merges (the platform owns those). The result
        carries the agent's structured findings, parsed by the review provider."""
        workdir = self._prepare_workdir(work_item)
        system_prompt, agents_md = self._deliver_body(self._body_loader(agent_spec), manifest)
        (workdir / "AGENTS.md").write_text(agents_md, encoding="utf-8")

        options = self._agent_options(
            system_prompt=system_prompt,
            mcp_servers=mcp_servers,
            allowed_tools=allowed_tools,
            cwd=str(workdir),
            model=(agent_spec.recommended_model or None),
            permission_mode=self._permission_mode,
        )
        prompt = self._build_review_prompt(agent_spec, work_item)
        return await self._consume(prompt, options)

    @staticmethod
    def _build_review_prompt(agent_spec: AgentSpec, work_item: WorkItem) -> str:
        return (
            f"Review the pull request for WorkItem {work_item.id} across all eleven dimensions. "
            "Your composed manifest is in AGENTS.md in the working directory and includes the "
            "'# Pull Request Under Review' diff; fetch any referenced artifacts with the "
            "platform-state tools. Do NOT modify code, run git, or merge — you only produce "
            "findings. Emit your full review, then exactly one fenced json block of structured "
            "findings (rem, severity, title, file, line) as your instructions specify."
        )
