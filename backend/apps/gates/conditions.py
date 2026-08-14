"""Per-phase control-plane gate conditions (#2/#5) — the composition point.

A gate condition is a checklist item on the `Approval` that must be satisfied before an
APPROVED decision is accepted. Never an engine hook. Two kinds compose here:

  - **reviewer-attested** (D6) — the WCAG 2.2 AA checklist on the design gate and the
    pre-deployment readiness checklist on the deployment gate: a human inspects and marks
    each criterion satisfied.
  - **derived** (D9) — the blocking-test rule on the test gate: the platform evaluates it
    from live state at decide time; a reviewer cannot attest it.

Keyed off phase so triggers stay generic — a phase with no conditions gets `[]`.
"""
from __future__ import annotations

from .readiness import conditions_for_readiness_phase
from .testgate import conditions_for_test_phase
from .testgate import evaluate as _evaluate_test_condition
from .wcag import conditions_for_wcag_phase


def conditions_for_phase(phase: str) -> list[dict]:
    """Every control-plane condition this phase's gate carries (empty for most phases)."""
    return (
        conditions_for_wcag_phase(phase)
        + conditions_for_test_phase(phase)
        + conditions_for_readiness_phase(phase)
    )


def refresh_derived(conditions, *, tenant_id, work_item_id) -> list[dict]:
    """Re-evaluate every `derived` condition from live state.

    Called at decide time so neither a stale value seeded when the gate opened nor a
    reviewer's payload can stand in for the real state. Reviewer-attested conditions pass
    through untouched, and a gate with no derived conditions costs no queries.
    """
    return [
        _evaluate_test_condition(c, tenant_id=tenant_id, work_item_id=work_item_id)
        if c.get("derived") else c
        for c in (conditions or [])
    ]
