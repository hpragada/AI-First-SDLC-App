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


@dataclass
class GateDecision:
    """Payload of the `gate_decision` signal."""

    decision: str  # "approved" | "rejected"
    approver_id: str | None = None
    comment: str = ""
