"""ClaudeDriver — planning runs via the Claude Agent SDK (spec §3).

Writes the agent's migrated body + composed manifest to the run workdir as SYSTEM_PROMPT.md
and delivers it as the engine's system prompt via `--system-prompt-file` (file-based, so any
body size is safe on Windows), with the platform-state MCP server wired in, and maps the
message stream to a RunResult. `query_fn` is injectable so the mapping is testable without the
network. `run_build_task` is Phase 2.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
import shutil
import sys
import tempfile
from collections import deque
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import claude_agent_sdk
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
)
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

from .base import ArtifactDraft, RunResult


def _install_resilient_message_parser() -> None:
    """Make the SDK tolerant of engine message types it doesn't know (CLI/SDK version skew).

    The pinned CLI (2.1.205) is newer than the pinned SDK (0.1.0) and emits notification
    messages the SDK's parser has no case for — e.g. `rate_limit_event`. The parser then raises
    `MessageParseError: Unknown message type: …`, which propagates out of `query()` and ABORTS
    the whole phase (observed: a UX run failed with exactly this). These messages are
    non-essential telemetry; the run's real output still arrives as Assistant/Result messages.

    So we wrap `parse_message`: an unknown message type becomes a benign `SystemMessage` the
    consumer ignores, instead of crashing the run. This is forward-robust — it tolerates ANY
    future unknown notification type, not just `rate_limit_event` — while still raising on
    genuinely malformed messages (missing type, bad shape). Patched at both the source module
    and the `_internal.client` call site so `query()` picks it up. Idempotent."""
    from claude_agent_sdk._errors import MessageParseError
    from claude_agent_sdk._internal import client as _client
    from claude_agent_sdk._internal import message_parser as _mp

    if getattr(_mp.parse_message, "_sdlc_resilient", False):
        return
    _orig = _mp.parse_message

    def _resilient(data):
        try:
            return _orig(data)
        except MessageParseError as exc:
            mtype = data.get("type") if isinstance(data, dict) else None
            if mtype and "Unknown message type" in str(exc):
                print(f"[claude-driver] ignoring unknown engine message type: {mtype!r} "
                      "(CLI/SDK version skew — non-fatal)", file=sys.stderr, flush=True)
                return SystemMessage(subtype=str(mtype), data=data)
            raise

    _resilient._sdlc_resilient = True
    _mp.parse_message = _resilient
    _client.parse_message = _resilient   # the actual call site in process_query


_install_resilient_message_parser()

# The SDK moved the "which CLI to launch" setting between versions: newer builds accept it as
# ClaudeAgentOptions(cli_path=...); older ones only via SubprocessCLITransport(cli_path=...).
# Detect which the *installed* SDK supports so we pin the CLI correctly on either — the daemon
# machine and the server/CI can legitimately run different SDK versions.
_OPTIONS_ACCEPTS_CLI_PATH = "cli_path" in inspect.signature(ClaudeAgentOptions).parameters
# The SDK only pipes (and thus lets us capture) the engine CLI's stderr when a callback is
# registered on options.stderr; otherwise ProcessError.stderr is the bare "Check stderr output
# for details" placeholder and the real cause (e.g. a usage-limit notice) is lost (Bugs S.No 146).
_OPTIONS_ACCEPTS_STDERR = "stderr" in inspect.signature(ClaudeAgentOptions).parameters
_STDERR_TAIL_LINES = 80  # trailing engine-output lines kept for the failure reason
# …but stderr is the wrong channel, which is why the S.No 146 fix never once fired: across nine
# engine-exit failures on two tenants, not one carried an "Engine stderr" tail. The CLI's
# diagnostic notices — including "Claude AI usage limit reached|<epoch>" — arrive on **stdout**
# as non-JSON lines, and the SDK drops them at `logger.debug` (subprocess_cli: "Skipping non-JSON
# line from CLI stdout"). The companion configures no logging anywhere, so the root logger has no
# handlers and logging.lastResort is WARNING-level: those records are discarded outright, and the
# reason reaching the platform degrades to the bare placeholder for every cause alike.
#
# Attaching a handler to the SDK's own logger is the supported seam for this — no SDK fork, and it
# also picks up query.py's `logger.error("Fatal error in message reader: …")`, the line the QA
# member could see in the companion terminal but the platform never received.
_SDK_LOGGER_NAME = "claude_agent_sdk"

if TYPE_CHECKING:
    from apps.registry.models import AgentSpec
    from apps.workitems.models import WorkItem

# Suffix of the platform-state tool that registers an artifact. MCP tools are exposed to
# the engine as `mcp__<server>__<tool>`, so we match on the suffix.
_REGISTER_ARTIFACT_TOOL = "register_artifact"

# The agent's role body + the composed run manifest are delivered to the engine as its SYSTEM
# PROMPT, via a FILE (`--system-prompt-file <path>`), never on the command line. Passing the
# system prompt inline (`--system-prompt <text>`) puts it on the process command line, which
# Windows caps at 32,767 chars — a large body (the UX Design agent is ~36 KB) overflows it and
# CreateProcess fails with WinError 206, which the SDK misreports as "Claude Code not found".
# Delivering via a file makes overflow structurally impossible for ANY body size, and — unlike
# the earlier AGENTS.md attempt — a `--system-prompt-file` genuinely reaches the model (Claude
# Code does NOT auto-load AGENTS.md, and planning agents have no Read tool to open it). See
# `_write_system_prompt_file`. The pinned CLI (2.1.205) accepts `--system-prompt-file`; our SDK
# (0.1.0) doesn't type it, so we pass it through `ClaudeAgentOptions.extra_args`.
_SYSTEM_PROMPT_FLAG = "system-prompt-file"
_SYSTEM_PROMPT_FILENAME = "SYSTEM_PROMPT.md"

# ── planning/review sandbox (Bugs S.No 63) ─────────────────────────────────────────────────
# Planning and review phases REASON over the platform-provided manifest (project context,
# registered artifacts, and — for review — the PR diff the platform inlines by reading it
# THROUGH the CodeHost capability). They run in a fresh EMPTY temp workdir with no repo checked
# out, so the engine's built-in filesystem/shell/subagent tools can reach nothing useful — they
# only let the agent WANDER (observed: a UX run spawned subagents to grep an empty dir for
# minutes before doing real work). We deny those tools so a planning/review agent can use ONLY
# the platform-state MCP tools it was granted. Two layers:
#   (1) disallowed_tools — a hard denylist the CLI enforces even in headless mode (verified: a
#       disallowed Read returns "blocked"); covers built-ins + the subagent tool (`Agent`).
#   (2) setting_sources=["project"] — load settings ONLY from the (empty) run workdir, never the
#       user's global Claude Code config, so no user skills / custom subagents / extra MCP
#       servers leak into the sandbox and tempt the agent off the platform tools. Context is
#       delivered via --system-prompt-file (not settings), so this does not affect it.
# Implementation/build is the ONE phase that works in a real git worktree and MUST keep these
# tools — it runs through run_build_task and is deliberately NOT sandboxed here.
# `ToolSearch` is deliberately ABSENT from this denylist (2026-07-30). It was added on 2026-07-09
# when it was simply another built-in to sandbox away. Since then the CLI (now 2.1.208) DEFERS
# tools out of the initial context and makes `ToolSearch` the only way to load them back — the SDK
# models this as `deferredBuiltinTools`. Blocking it therefore stopped being "one less tool to
# wander with" and became "some of your granted tools are permanently invisible".
#
# That is the failure this cost days: run 457f65e1 opened with, in the agent's own words,
# "The platform-state tools (ask_human, register_artifact, add_trace_edge, log_event) referenced
# in my operating instructions are not present in my available tool context" — while the SAME run
# successfully called `list_artifacts` and `get_artifact`. Read tools surfaced, write tools and
# `ask_human` deferred and unreachable, so the agent wrote 39,417 chars of deliverables as prose
# and the platform filed its questions as an artifact. Intermittent, because what the CLI defers
# depends on context pressure that varies run to run.
#
# Allowing it does NOT widen the sandbox: `ToolSearch` only loads SCHEMAS for tools already
# granted in `allowed_tools`, and execution is still gated by that allowlist plus this denylist.
# Tools that hand work to something OUTSIDE this run — a task queue, a cron schedule, another
# session, a notification channel. A phase run has none of those: it is one engine invocation the
# platform waits on, and anything it defers is never executed by anyone.
#
# These are DEFERRED tools: the CLI keeps them out of the agent's initial context and `ToolSearch`
# loads them on request. We must allow `ToolSearch` (it is the only way the platform-state write
# tools come back — see the note above it), so the agent can and does reach for these. Live proof,
# run fed0f385: the agent's FIRST action was
#   ToolSearch select:CronCreate,…,TaskCreate,TaskGet,TaskList,TaskOutput,TaskStop,TaskUpdate
# then "I'll set up the task list and kick off the index in parallel" → `TaskCreate` → "Task #1
# created successfully" → and it went silent, waiting on a task nothing would ever run. Denying
# them costs the agent nothing: it has no legitimate use for a cron job or a second session.
_BACKGROUND_TOOLS = [
    "TaskCreate", "TaskGet", "TaskList", "TaskOutput", "TaskStop", "TaskUpdate",
    "CronCreate", "CronDelete", "CronList", "Monitor", "SendMessage", "PushNotification",
    "RemoteTrigger", "DesignSync", "EnterWorktree", "ExitWorktree",
    "EnterPlanMode", "ExitPlanMode",
]
_PLANNING_DISALLOWED_TOOLS = [
    "Agent", "Task", "Bash", "BashOutput", "KillShell", "Read", "Write", "Edit",
    "NotebookEdit", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite", "Skill",
    *_BACKGROUND_TOOLS,
]
# A REPO-SCOPED planning phase (catalog `reads_code`, e.g. 10_security) runs the agent in a git
# worktree so it can scan real source. It needs full local tooling — Read/Grep/Glob AND Bash — to
# run real security scanners (semgrep / pip-audit / syft for SAST/SCA/SBOM), so this denylist
# blocks only the sandbox-hygiene tools (subagents + web + skills). The worktree is THROWAWAY and
# is never committed or pushed (the companion calls no git-write helper and tears it down after),
# so the "read-only-to-the-real-repo" guarantee comes from never-pushing, not from blocking Bash —
# the same posture run_build_task already uses to run the repo's own code.
_SCAN_DISALLOWED_TOOLS = [
    # `ToolSearch` omitted for the same reason as the planning denylist above — a repo-scoped
    # phase needs its platform-state write tools just as much, and blocking the only mechanism
    # that loads deferred tools is what made them vanish.
    "Agent", "Task", "WebFetch", "WebSearch", "TodoWrite", "Skill", "NotebookEdit",
    # A repo-scoped run is the one that PROVED this necessary — see `_BACKGROUND_TOOLS`.
    *_BACKGROUND_TOOLS,
]
# Taking a built-in tool OFF the denylist is only half of granting it. Under
# `permission-mode=default` a tool that is neither denied nor allow-listed raises a PERMISSION
# REQUEST — and an engine run has no human and no TTY to answer one, so the CLI blocks forever.
# That is exactly what happened: every repo-scoped run (00c code intelligence, 10_security) sat
# at ~0% CPU with no tool calls, no artifacts and no error until it was killed, because the
# denylist above "allowed" these tools while `allowed_tools` never named them. The sandbox path
# never hit it — there the same tools are hard-DENIED, so the agent is told "no" and moves on.
# Keep this list in step with what `_SCAN_DISALLOWED_TOOLS` stops blocking.
_SCAN_LOCAL_TOOLS = ["Read", "Glob", "Grep", "Bash", "BashOutput", "KillShell"]
_SANDBOX_SETTING_SOURCES = ["project"]

# Generic safety net: the engine subprocess can occasionally lose a launch race and surface as
# "Claude Code not found" even though the CLI is present. That happens before any message
# streams, so retrying the whole run a few times never double-processes. (This is NOT the fix
# for the overflow above — that is now impossible because the system prompt never touches the
# command line; this only covers transient spawn races.)
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
        # Bounded tail of the engine CLI's stderr for the last run, so a launch/usage-limit
        # failure carries a human-readable cause instead of the SDK's opaque placeholder.
        self._stderr_tail: deque[str] = deque(maxlen=_STDERR_TAIL_LINES)

    # ── engine output capture (Bugs S.No 146) ─────────────────────
    def _collect_stderr(self, line: str) -> None:
        """options.stderr callback: keep a bounded tail of the engine's stderr for the failure
        reason, and echo it live to the companion console (registering this callback pipes stderr,
        which would otherwise inherit the console — so we re-emit it to preserve live output)."""
        text = line.rstrip("\n")
        if text:
            self._stderr_tail.append(f"[stderr] {text}")
        print(line, end="" if line.endswith("\n") else "\n", file=sys.stderr, flush=True)

    @contextmanager
    def _capturing_sdk_log(self):
        """Capture the SDK's own log records into the same tail for the duration of one run.

        This is where the cause actually lives (see `_SDK_LOGGER_NAME`). The handler is installed
        and removed around the run: attaching to a library logger is global state, and a companion
        that serves builds all day would otherwise accumulate one handler per run. The previous
        level and `propagate` are restored too, so we never leave the SDK noisier than we found it
        — and `propagate=False` while we hold it keeps the DEBUG flood off anyone else's console.
        """
        logger = logging.getLogger(_SDK_LOGGER_NAME)
        tail = self._stderr_tail

        class _TailHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                try:
                    tail.append(f"[engine] {record.getMessage()}")
                except Exception:      # noqa: BLE001 — diagnostics must never break the run
                    pass

        handler = _TailHandler(level=logging.DEBUG)
        prev_level, prev_propagate = logger.level, logger.propagate
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        try:
            yield
        finally:
            logger.removeHandler(handler)
            logger.setLevel(prev_level)
            logger.propagate = prev_propagate

    @staticmethod
    def _with_progress(exc: Exception, *, messages: int, text: str, artifacts: int,
                       cost_usd: float, subtype: str) -> Exception:
        """Attach how far the run actually got to an exception raised mid-stream.

        A run that dies after 200 messages and one that dies before the first are different
        failures; without this they are the same string. The last of the agent's own words is the
        most useful single line here — it says what it was doing when the engine went away."""
        parts = [f"{messages} message(s)"]
        if artifacts:
            parts.append(f"{artifacts} artifact(s) registered")
        if cost_usd:
            parts.append(f"${cost_usd:.4f}")
        if subtype:
            parts.append(f"result subtype {subtype!r}")
        progress = f"Engine progress before the failure: {', '.join(parts)}."
        tail = " ".join(text.split())[-400:]
        if tail:
            progress += f"\nLast agent output: …{tail}"
        return RuntimeError(f"{exc}\n{progress}")

    def _with_stderr_tail(self, exc: Exception) -> Exception:
        """Fold the captured engine output into the error when the SDK only surfaced its
        'Check stderr output for details' placeholder, so the platform can classify the failure
        (e.g. a usage/rate limit) and a human can read WHY (Bugs S.No 146). Returns the original
        exception unchanged when there is nothing to add."""
        tail = "\n".join(self._stderr_tail).strip()
        if not tail or tail.lower() in str(exc).lower():
            return exc
        return RuntimeError(f"{exc}\nEngine output (tail):\n{tail[-4000:]}")

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
        # Capture the engine's stderr (Bugs S.No 146) unless the caller wired its own sink.
        if _OPTIONS_ACCEPTS_STDERR and "stderr" not in kwargs:
            kwargs["stderr"] = self._collect_stderr
        return ClaudeAgentOptions(**kwargs)

    # ── system-prompt delivery (body + manifest, file-based) ───────
    @staticmethod
    def _compose_system_prompt(body: str, manifest: str) -> str:
        """The agent's authoritative system prompt = its role/process body, then the composed run
        manifest (project profile, work item, artifacts, and — reaching the model for the first
        time via this channel — `# Rules`). Body first so the identity leads; the manifest follows
        as the run context the body references."""
        return (
            f"{body}\n\n"
            "<!-- The section above is your agent role and operating instructions; treat it as "
            "authoritative. Your run context (project profile, work item, artifacts) follows. -->"
            "\n\n---\n\n"
            f"{manifest}"
        )

    def _write_system_prompt_file(self, dir_: Path, body: str, manifest: str) -> str:
        """Write the composed system prompt to `SYSTEM_PROMPT.md` in the run dir and return its
        ABSOLUTE path (the CLI resolves a relative `--system-prompt-file` against cwd and validates
        it exists). A distinct filename — not AGENTS.md/CLAUDE.md — so it is never confused with a
        project-instructions file, and size-independent: no command-line channel, no overflow."""
        path = (dir_ / _SYSTEM_PROMPT_FILENAME).resolve()
        path.write_text(self._compose_system_prompt(body, manifest), encoding="utf-8")
        return str(path)

    # ── planning ───────────────────────────────────────────────────
    async def run_planning_task(
        self,
        *,
        manifest: str,
        agent_spec: AgentSpec,
        mcp_servers: dict,
        allowed_tools: list[str],
        work_item: WorkItem,
        repo_workspace: Path | None = None,
    ) -> RunResult:
        """Run a planning agent. Default: sandboxed reasoning in an empty temp workdir (no
        filesystem). When `repo_workspace` is given (a repo-scoped `reads_code` phase like
        10_security), run inside that git worktree so the agent can scan real source and run real
        scanners: cwd is the worktree, the denylist allows the full local toolset (Read/Grep/Glob
        /Bash) but blocks subagents + web + skills, and (mirroring run_build_task) no
        `setting_sources` so the scanned repo's own .claude/CLAUDE.md is never loaded. The worktree
        is throwaway and is never committed or pushed, so the real repo is never mutated."""
        if repo_workspace is not None:
            repo_workspace = Path(repo_workspace)
            # System prompt to .sdlc/ (kept out of the diff by the worktree's local exclude),
            # exactly like the build path — the worktree root stays pristine.
            sdlc = repo_workspace / ".sdlc"
            sdlc.mkdir(parents=True, exist_ok=True)
            sp_file = self._write_system_prompt_file(
                sdlc, self._body_loader(agent_spec), manifest)
            options = self._agent_options(
                extra_args={_SYSTEM_PROMPT_FLAG: sp_file},
                mcp_servers=mcp_servers,
                # Allow-list the local tools too, not just un-deny them — see _SCAN_LOCAL_TOOLS.
                allowed_tools=list(allowed_tools) + _SCAN_LOCAL_TOOLS,
                disallowed_tools=_SCAN_DISALLOWED_TOOLS,  # full local toolset; never pushed
                cwd=str(repo_workspace),
                model=(agent_spec.recommended_model or None),
                permission_mode=self._permission_mode,
            )
        else:
            workdir = self._prepare_workdir(work_item)
            sp_file = self._write_system_prompt_file(
                workdir, self._body_loader(agent_spec), manifest)
            options = self._agent_options(
                extra_args={_SYSTEM_PROMPT_FLAG: sp_file},
                mcp_servers=mcp_servers,
                allowed_tools=allowed_tools,
                disallowed_tools=_PLANNING_DISALLOWED_TOOLS,   # sandbox: platform-state MCP only
                setting_sources=_SANDBOX_SETTING_SOURCES,      # no user skills/subagents/MCP leak
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
        old large-body overflow can no longer occur here: the system prompt (body + manifest) is
        delivered via `--system-prompt-file`, so it never touches the command line at all."""
        self._stderr_tail.clear()  # fresh capture per run (Bugs S.No 146)
        with self._capturing_sdk_log():
            return await self._consume_retrying(prompt, options)

    async def _consume_retrying(self, prompt: str, options: ClaudeAgentOptions) -> RunResult:
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
                # Final failure — surface the engine's stderr tail so the platform can classify it.
                enriched = self._with_stderr_tail(exc)
                if enriched is exc:
                    raise
                raise enriched from exc
        assert last_exc is not None  # loop only exits early via return/raise
        enriched = self._with_stderr_tail(last_exc)
        if enriched is last_exc:
            raise last_exc
        raise enriched from last_exc

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
        CLI must fail fast, not spin. (Command-line-length overflows can't reach here at all: the
        system prompt is delivered via --system-prompt-file, never on the command line.)"""
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

        # The stream can die PART WAY THROUGH — the transport raises when the CLI exits non-zero,
        # after however much real work already streamed. Everything below used to be local state
        # discarded by that exception: TASK-014 ran 12.5 minutes and left no record of what it did,
        # while another failure died in 12 seconds, and both reported the identical message. Keep
        # what we have and fold it into the error so the two can never again be confused.
        try:
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
        except Exception as exc:
            raise self._with_progress(
                exc, messages=len(raw_messages), text="".join(text_parts),
                artifacts=len(artifacts), cost_usd=cost_usd, subtype=result_subtype,
            ) from exc

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
            f"Execute the '{phase}' phase for WorkItem {work_item.id}. Your role instructions and "
            "composed run manifest are provided in your system prompt. Register your outputs and "
            "fetch any referenced artifact bodies using the platform-state tools. Do not push to "
            "any system-of-record; the platform handles gates and publishing."
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
        The system prompt (role body + manifest) is written to `.sdlc/SYSTEM_PROMPT.md` (kept out
        of the diff by the worktree's local exclude) and delivered via `--system-prompt-file`; the
        agent works in `repo_workspace`. We deliberately set no `setting_sources`, so the client
        repo's own CLAUDE.md/.claude hooks are NOT loaded (no collision, no client-hook execution).
        The agent edits + tests; it never runs git — the platform commits/pushes/opens the PR (D2)."""
        repo_workspace = Path(repo_workspace)
        sdlc = repo_workspace / ".sdlc"
        sdlc.mkdir(parents=True, exist_ok=True)
        sp_file = self._write_system_prompt_file(sdlc, self._body_loader(agent_spec), manifest)

        options = self._agent_options(
            extra_args={_SYSTEM_PROMPT_FLAG: sp_file},
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
            "worktree (your working directory). Your role instructions and composed run manifest "
            "are provided in your system prompt. Implement the change with full tests and run them "
            "locally. Register your outputs with the platform-state tools. Do NOT run git or open "
            "a pull request — the platform commits, pushes, and opens the PR after your run."
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
        sp_file = self._write_system_prompt_file(
            workdir, self._body_loader(agent_spec), manifest)

        options = self._agent_options(
            extra_args={_SYSTEM_PROMPT_FLAG: sp_file},
            mcp_servers=mcp_servers,
            allowed_tools=allowed_tools,
            disallowed_tools=_PLANNING_DISALLOWED_TOOLS,   # sandbox: platform-state MCP + inlined diff only
            setting_sources=_SANDBOX_SETTING_SOURCES,      # no user skills/subagents/MCP leak
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
            "Your role instructions and composed manifest are provided in your system prompt, "
            "including the '# Pull Request Under Review' diff; fetch any referenced artifacts with "
            "the platform-state tools. Do NOT modify code, run git, or merge — you only produce "
            "findings. Emit your full review, then exactly one fenced json block of structured "
            "findings (rem, severity, title, file, line) as your instructions specify."
        )
