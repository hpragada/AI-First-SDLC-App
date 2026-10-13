"""Deployment readiness gate checklist — the deployment gate's control-plane conditions.

The deployment gate is **not** a prompt rule and **not** an engine hook (#2): it is a
readiness checklist attached to the deployment-phase `Approval`. Each item mirrors the 12
Deployment agent's Step 1 pre-deployment readiness check (Google SRE release engineering;
ITIL 4 Change Enablement). A required item the DevOps reviewer has not marked satisfied
**blocks approval** — the release cannot be gated past until readiness is attested, so the
agent's "never deploy without a completed checklist" principle is enforced by the control
plane, not merely narrated by the agent.

Reviewer-attested (like the WCAG checklist, D6), not derived: the on-call, staging, and
stakeholder-communication items are human judgement the platform cannot compute at decide
time. (Some items — no open Critical/High security findings, no failing blocking test —
could later become *derived* conditions like the test gate, D9; that is a future refinement.)
"""
from __future__ import annotations

# (key, label) — every item is `required` for the deployment bar. The DevOps reviewer marks
# each `satisfied` at the gate; an unmet required item blocks the APPROVED decision.
_READINESS_CRITERIA: list[tuple[str, str]] = [
    ("code_quality", "All merged PRs are CI-passing; test coverage ≥ 80%; linting passes"),
    ("testing", "All Critical/High test cases passed and UAT is signed off by the Product Owner"),
    ("security", "Zero open Critical or High security findings; dependency scan passed"),
    ("migrations", "Database migrations tested on staging with a tested rollback script (or none)"),
    ("rollback", "Rollback procedure is documented and tested"),
    ("on_call", "On-call engineer designated and available; deployment window communicated to stakeholders"),
    ("deliverables", "Release notes and the version-specific rollback runbook are registered"),
]

# Phases whose gate carries the readiness checklist (the deployment review — 12 Deployment,
# gate role devops). Keyed off phase so triggers stay generic — every other phase gets `[]`.
_READINESS_GATED_PHASES = {"deployment"}


def readiness_checklist() -> list[dict]:
    """A fresh deployment-readiness checklist (all required, none yet satisfied)."""
    return [
        {"key": key, "label": label, "required": True, "satisfied": False}
        for key, label in _READINESS_CRITERIA
    ]


def conditions_for_readiness_phase(phase: str) -> list[dict]:
    """The readiness checklist for the deployment gate, empty for every other phase.
    Composed with the other phases' conditions in `apps.gates.conditions`."""
    return readiness_checklist() if phase in _READINESS_GATED_PHASES else []
