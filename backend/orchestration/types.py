"""Workflow/activity payloads. Deliberately Django-free so the workflow sandbox
can import them without pulling in the ORM."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentRunInput:
    """One agent run = one AgentRunWorkflow (spec §5)."""

    run_id: str
    tenant_id: str
    project_id: str
    work_item_id: str
    agent_spec_id: str
    phase: str
    gate_type: str = "phase_gate"
    required_role: str = "product_owner"
    # Where the engine runs (req #1). "companion" = the user's local Claude Code via their
    # enrolled companion (the real path; set by trigger_phase when an enrollment exists);
    # "server" = the in-worker ClaudeDriver (the CI/test/headless fallback). The dataclass
    # default stays "server" so existing tests that build the input directly are unchanged.
    execution_mode: str = "server"
    # Which enrolled companion to dispatch to (the triggering user's), when companion mode.
    enrollment_id: str | None = None
    # If the companion never reports within this window, park the run for human takeover.
    report_timeout_seconds: int = 7200
    # Repo-scoped PLANNING phases (catalog `reads_code`, e.g. 10_security) carry the target
    # repo + base branch so the companion can check out a READ-ONLY worktree to scan the real
    # source. None for every other planning phase → no worktree, behaviour unchanged. This is
    # NOT the build path (no commit/push/PR); the run still rides AgentRunWorkflow.
    repo: str | None = None
    base: str | None = None


@dataclass
class GateDecision:
    """Payload of the `gate_decision` signal."""

    decision: str  # "approved" | "rejected"
    approver_id: str | None = None
    comment: str = ""


@dataclass
class PhaseReport:
    """What the companion posts back after running a planning/review phase locally (the
    `phase_reported` signal payload). The artifact body travels here; the platform writes it
    to S3 and registers the pointer (state stays server-side)."""

    status: str = "ok"          # "ok" | "failed"
    body: str = ""              # the phase's produced text (becomes the draft artifact)
    cost_usd: float = 0.0
    message: str = ""
