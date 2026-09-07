"""Blocking-test gate condition — the test gate's control-plane rule (Phase 3 §5 / D9).

> "a failing **blocking** test cannot be gated past until its defect is resolved or
> quarantined" — PHASE_3_BUILD_SPEC §5.

Like the WCAG checklist (D6) this is a condition on the `Approval`, never an engine hook
(#2) — 09's own "zero open Critical defects" quality gate is the agent self-checking, which
is exactly what a control-plane gate must not rely on. Unlike WCAG it is **derived**, not
reviewer-attested: the platform evaluates it from live state at decide time, so a reviewer
can never tick past a red suite.

The defect loopback already computes this set precisely — `import_test_results` opens a
`defect` child WorkItem per failing **non-quarantined** test and closes it once the test
passes on a later import. So "no open test defects" *is* "no failing blocking test": we read
that reconciliation rather than recompute a parallel (and driftable) notion of failing.

Note the bound this inherits: the rule blocks on *any* open test defect, whatever its
severity — stricter than 09's own body (which tolerates open Medium/Low). §5 is the
authority, and "quarantined" is the documented escape hatch for a test that shouldn't block.
"""
from __future__ import annotations

BLOCKING_TESTS_KEY = "no_blocking_test_failures"

# Phases whose gate carries the blocking-test rule. 09 Testing's gate is where the
# `test_report` is accepted (§5), so the rule binds there. 09b Test Automation generates a
# script rather than accepting results — whether its gate should also block on a red suite
# is a product decision, not something this module should assume.
_TEST_GATED_PHASES = {"testing"}


def blocking_tests_condition() -> dict:
    """A fresh (unsatisfied) blocking-test condition. `derived` marks it platform-evaluated:
    `apps.gates.conditions.refresh_derived` recomputes it at decide time (routing it here by
    `key`) and `services._merge_conditions` refuses a reviewer's `satisfied` update on it.

    Those two facts together are why a derived condition MUST have a registered evaluator: it
    is seeded unsatisfied and no human is permitted to satisfy it, so one that never refreshes
    is a gate that can never be approved."""
    return {
        "key": BLOCKING_TESTS_KEY,
        "label": (
            "No failing blocking test — every failing test's defect is resolved, "
            "or the test is quarantined as flaky"
        ),
        "required": True,
        "satisfied": False,
        "derived": True,
    }


def conditions_for_test_phase(phase: str) -> list[dict]:
    """The blocking-test condition for the test gate, empty for every other phase."""
    return [blocking_tests_condition()] if phase in _TEST_GATED_PHASES else []


def open_test_defect_refs(*, tenant_id, work_item_id) -> list[str]:
    """The `test_ref`s of this work item's still-open test defects.

    Security defects carry `finding` (not `test_ref`) and are scoped out — they gate the
    security phase (D8), never this one, mirroring `record_security_findings`.
    """
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    with tenant_context(tenant_id):
        defects = WorkItem.objects.filter(
            tenant_id=tenant_id, parent_id=work_item_id, type=WorkItem.Type.DEFECT,
        # `TERMINAL_STATES`, not `DONE` alone (S.No 140). Team decision: cancelling a defect
        # RELEASES the gate it was blocking — a defect nobody will fix must not hold a story
        # shut for ever. The disclosure that makes that safe is the acknowledgement condition
        # `apps.workitems.cancel` puts on the pending approval: the gate opens, but a reviewer
        # has to read what was cancelled and say so before it does.
        ).exclude(state__in=WorkItem.TERMINAL_STATES)
        refs = {
            (d.external_ref or {}).get("test_ref")
            for d in defects
            if (d.external_ref or {}).get("test_ref")
        }
    return sorted(refs)


def evaluate(condition: dict, context) -> dict:
    """Re-evaluate the blocking-test condition from live state; returns an updated copy.
    `detail` names the tests still holding the gate shut, so the reviewer sees why.

    `context` is `apps.gates.conditions.ConditionContext` — every derived evaluator takes the
    same shape (QA-15a) and reads the part it needs; this one needs the work item, because the
    defect loopback hangs its defects there.

    The key guard below is now redundant — the registry only routes this condition here — and
    it stays anyway: this decides whether a gate opens, and a belt-and-braces early return
    costs one comparison.
    """
    if condition.get("key") != BLOCKING_TESTS_KEY:
        return condition
    refs = open_test_defect_refs(tenant_id=context.tenant_id,
                                 work_item_id=context.work_item_id)
    updated = {**condition, "satisfied": not refs}
    if refs:
        updated["detail"] = "open test defects: " + ", ".join(refs)
    else:
        updated.pop("detail", None)
    return updated
