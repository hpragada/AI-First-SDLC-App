"""ClaudeDriver — planning runs via the Claude Agent SDK (spec §3).

Writes the composed manifest to the run workdir as AGENTS.md, runs the agent with its
migrated body as the system prompt and the platform-state MCP server wired in, and maps
the message stream to a RunResult. `query_fn` is injectable so the mapping is testable
without the network. `run_build_task` is Phase 2.
"""
from __future__ import annotations

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

from .base import ArtifactDraft, RunResult

if TYPE_CHECKING:
    from apps.registry.models import AgentSpec
    from apps.workitems.models import WorkItem

# Suffix of the platform-state tool that registers an artifact. MCP tools are exposed to
# the engine as `mcp__<server>__<tool>`, so we match on the suffix.
_REGISTER_ARTIFACT_TOOL = "register_artifact"


class ClaudeDriver:
    def __init__(
        self,
        *,
        query_fn: Callable | None = None,
        body_loader: Callable[[Any], str] | None = None,
        repo_root: Path | str | None = None,
        workdir_base: Path | str | None = None,
        permission_mode: str = "bypassPermissions",
    ) -> None:
        # Default to the real SDK; tests inject a fake async generator.
        self._query = query_fn or claude_agent_sdk.query
        self._body_loader = body_loader or self._read_body_file
        self._repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[2]
        self._workdir_base = Path(workdir_base) if workdir_base else None
        # Engine has no human in the loop — gates are control-plane (#2). Tools are still
        # whitelisted via allowed_tools, so only platform-state tools can run.
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
        (workdir / "AGENTS.md").write_text(manifest, encoding="utf-8")

        options = ClaudeAgentOptions(
            system_prompt=self._body_loader(agent_spec),
            mcp_servers=mcp_servers,
            allowed_tools=allowed_tools,
            cwd=str(workdir),
            model=(agent_spec.recommended_model or None),
            permission_mode=self._permission_mode,
        )
        prompt = self._build_prompt(agent_spec, work_item)

        raw_messages: list[Any] = []
        text_parts: list[str] = []
        artifacts: list[ArtifactDraft] = []
        cost_usd = 0.0
        final_result: str | None = None

        async for message in self._query(prompt=prompt, options=options):
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

        joined = "".join(text_parts)
        outputs = {"result": final_result if final_result is not None else joined, "text": joined}
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
        raise NotImplementedError("run_build_task is implemented in Phase 2 (P0 is planning-only).")
