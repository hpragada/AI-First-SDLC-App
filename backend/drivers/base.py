"""The engine seam (non-negotiable #7).

Business logic NEVER calls an engine directly — it goes through `ExecutionDriver`.
`ClaudeDriver` is the default (Claude Agent SDK); Codex/Copilot drivers arrive in
Phase 6 behind this same interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path  # noqa: F401  (used in Protocol annotations)
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:  # hints only; the driver package stays import-safe without Django
    from apps.registry.models import AgentSpec
    from apps.workitems.models import WorkItem


@dataclass
class ArtifactDraft:
    """An artifact the agent registered during a run (observed via the
    platform-state `register_artifact` tool). Pointer-level, not the body (#1/#3)."""

    phase: str
    type: str
    sor: str = "internal"
    content_hash: str = ""
    s3_key: str | None = None
    external_ref: dict | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class RunResult:
    """What an engine run yields back to the orchestration layer (spec §3)."""

    outputs: dict[str, Any]
    artifacts: list[ArtifactDraft]
    cost_usd: float
    raw_messages: list[Any]


@runtime_checkable
class ExecutionDriver(Protocol):
    async def run_planning_task(
        self,
        *,
        manifest: str,
        agent_spec: AgentSpec,
        mcp_servers: dict,
        allowed_tools: list[str],
        work_item: WorkItem,
    ) -> RunResult: ...

    async def run_build_task(
        self,
        *,
        manifest: str,
        agent_spec: AgentSpec,
        repo_workspace: Path,
        mcp_servers: dict,
        allowed_tools: list[str],
        work_item: WorkItem,
    ) -> RunResult: ...

    async def run_review_task(
        self,
        *,
        manifest: str,
        agent_spec: AgentSpec,
        mcp_servers: dict,
        allowed_tools: list[str],
        work_item: WorkItem,
    ) -> RunResult: ...
