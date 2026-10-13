"""Open-findings gate condition — the security gate's control-plane rule (D8 / Bugs S.No 178).

The Security agent's contract says its gate must not be grantable while any Critical or High
finding is open. **No such rule existed in the platform**: `conditions_for_phase` contributed
conditions for the design, testing, accessibility and readiness gates and nothing at all for
security, so the security gate was a plain human approval. The only thing between an open
Critical and a passed gate was a reviewer reading carefully.

Modelled on `testgate` deliberately, because the situation is the same one: the security defect
loopback (`apps.quality.services.record_security_findings`) already opens a `defect` child
WorkItem per open Critical/High finding and closes it once a later run reports it resolved. So
"no open blocking security finding" *is* "no open security defect" — this reads that
reconciliation rather than recomputing a parallel, driftable notion of open. Gate and defect
board can therefore never disagree, and a finding fixed on a later run clears this condition
with no manual step.

**Derived**, not reviewer-attested: the platform evaluates it at decide time, so a reviewer can
never tick past an open Critical. That is also why it MUST stay registered in
`conditions._DERIVED_EVALUATORS` — a derived condition is seeded unsatisfied and no human may
satisfy it, so one that never refreshes is a gate nobody can ever approve.

Scoped to security defects by `external_ref["finding"]`, exactly as `record_security_findings`
scopes its own writes — test defects (`test_ref`) and accessibility defects (`a11y_finding`)
gate their own phases and are untouched here.
"""
from __future__ import annotations

SECURITY_GATE_KEY = "no_blocking_security_findings"

# Phases whose gate carries this rule. 10 Security's gate is where the `security_review` is
# accepted, so the rule binds there.
_SECURITY_GATED_PHASES = {"security"}

#: How many findings are named before the detail says "and N more" — the same bound the
#: accessibility gate uses, for the same reason: a reviewer reads a sentence, not a list of 40.
_MAX_NAMED = 5


def blocking_security_condition() -> dict:
    """A fresh (unsatisfied) open-findings condition."""
    return {
        "key": SECURITY_GATE_KEY,
        "label": (
            "No unresolved Critical or High security finding — every one the security review "
            "raised has been fixed"
        ),
        "required": True,
        "satisfied": False,
        "derived": True,
    }


def conditions_for_security_phase(phase: str) -> list[dict]:
    """The open-findings condition for the security gate, empty for every other phase."""
    return [blocking_security_condition()] if phase in _SECURITY_GATED_PHASES else []


def _describe(defect) -> str:
    """One finding, as a reviewer should read it: its severity and what it is.

    Never the finding's id. The reviewer is being told why they cannot approve yet, and
    "SEC-003" is not something they can act on — the title the security review wrote is. When
    the review recorded no title, `record_security_findings` falls back to the id for the work
    item's own name; say so plainly rather than printing the identifier.
    """
    ref = defect.external_ref or {}
    severity = str(ref.get("severity") or "").capitalize() or "Open"
    finding_id = str(ref.get("finding") or "")
    title = (defect.title or "").removeprefix("Security: ").strip()
    if not title or title == finding_id:
        return f"{severity} — the security review recorded no title for this one"
    return f"{severity} — {title}"


def open_security_findings(*, tenant_id, work_item_id) -> list[str]:
    """This work item's still-open blocking security findings, described for a reviewer.

    Ordered most severe first so the sentence leads with the worst of it.
    """
    from apps.quality.services import _SECURITY_BLOCKING
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    with tenant_context(tenant_id):
        defects = list(
            WorkItem.objects.filter(
                tenant_id=tenant_id, parent_id=work_item_id, type=WorkItem.Type.DEFECT,
            # `TERMINAL_STATES`, not `DONE` alone — the same rule the test gate follows
            # (S.No 140): cancelling a defect RELEASES the gate it was blocking, and the
            # acknowledgement condition `apps.workitems.cancel` adds is what makes that safe.
            ).exclude(state__in=WorkItem.TERMINAL_STATES)
        )
    blocking = [
        d for d in defects
        if (d.external_ref or {}).get("finding")
        and str((d.external_ref or {}).get("severity") or "").lower() in _SECURITY_BLOCKING
    ]
    blocking.sort(key=lambda d: (
        0 if str((d.external_ref or {}).get("severity") or "").lower() == "critical" else 1,
        d.title or "",
    ))
    return [_describe(d) for d in blocking]


def evaluate(condition: dict, context) -> dict:
    """Re-evaluate the open-findings condition from live state; returns an updated copy.

    `context` is `apps.gates.conditions.ConditionContext` — every derived evaluator takes the
    same shape; this one needs the work item, because the security loopback hangs its defects
    there. The key guard is belt-and-braces (the registry only routes this condition here) and
    costs one comparison on a decision that gates a merge.
    """
    if condition.get("key") != SECURITY_GATE_KEY:
        return condition
    open_findings = open_security_findings(tenant_id=context.tenant_id,
                                           work_item_id=context.work_item_id)
    updated = {**condition, "satisfied": not open_findings}
    if open_findings:
        named = "; ".join(open_findings[:_MAX_NAMED])
        rest = len(open_findings) - _MAX_NAMED
        if rest > 0:
            named += f"; and {rest} more"
        plural = "finding" if len(open_findings) == 1 else "findings"
        updated["detail"] = f"{len(open_findings)} security {plural} still open: {named}"
    else:
        updated.pop("detail", None)
    return updated
