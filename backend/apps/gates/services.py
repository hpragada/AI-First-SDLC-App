"""Gate decision service (spec §6).

A human decides a pending Approval; only a user whose Membership role equals the gate's
`required_role` may decide. On decision we record it (decision + approver + timestamp)
and send the `gate_decision` signal to resume the blocked AgentRunWorkflow. RBAC here is
minimal (role check only) — full segregation of duties is Phase 5.

The signal sender is injectable so the decision logic is unit-testable without Temporal.
"""
from __future__ import annotations

from datetime import UTC, datetime

from django.conf import settings
from mcp_platform_state import tools

from apps.base import Role
from apps.gates.conditions import conditions_for_phase, refresh_derived
from apps.gates.models import Approval
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Membership, User

_VALID_DECISIONS = {"approved", "rejected"}


class GateError(Exception):
    """Gate decision could not be applied (e.g. already decided, no workflow)."""


class GateRoleError(GateError):
    """Deciding user lacks the gate's required Membership role."""


class GateConditionsError(GateError):
    """A required gate condition (e.g. a WCAG 2.2 AA criterion) is not yet satisfied."""


def _merge_conditions(existing: list, updates: list | None) -> list:
    """Fold the reviewer's `satisfied` updates (keyed by `key`) into the gate's conditions.
    Unknown keys are appended; reasoning/labels on existing items are preserved.

    A **derived** condition (D9 — platform-evaluated from live state, e.g. the blocking-test
    rule) ignores the reviewer's `satisfied`: attesting it is not the reviewer's to do, and
    `refresh_derived` recomputes it immediately after this merge regardless. The append path
    below never carries `derived` through, so a payload cannot mint one either."""
    merged = [dict(c) for c in (existing or [])]
    by_key = {c.get("key"): c for c in merged}
    for upd in updates or []:
        key = upd.get("key")
        if key in by_key:
            if "satisfied" in upd and not by_key[key].get("derived"):
                by_key[key]["satisfied"] = bool(upd["satisfied"])
        else:
            merged.append({
                "key": key, "label": upd.get("label", ""),
                "required": bool(upd.get("required", True)),
                "satisfied": bool(upd.get("satisfied", False)),
            })
    return merged


def _phase_of(approval) -> str:
    """The phase this gate belongs to, named the way `conditions_for_phase` names phases.

    The agent spec's `phase_label`, deliberately — not its `key` with the ordinal stripped. For
    `00c_intelligent_context_extractor` the label is `context_extraction`, so stripping the
    prefix produces a phase name that matches nothing. And `gate_type` is a gate KIND
    ("phase_gate" / "merge_gate"), never a phase.
    """
    spec = getattr(approval.run, "agent_spec", None) if approval.run_id else None
    return (spec.phase_label or spec.key or "") if spec is not None else ""


def _top_up_derived_conditions(approval, *, tenant_id) -> list:
    """Add derived conditions this gate's phase carries that this Approval was never seeded with.

    Conditions are seeded once, when the gate is opened (`open_gate_core`). So a rule added to
    the platform after a gate opened could never reach that gate: the security rule (Bugs
    S.No 178) would have guarded every future security gate while leaving every gate already
    pending approvable with open Criticals — exactly the hole it was written to close.

    **Derived conditions only, and that is the whole point.** A derived condition is computed
    from live state, so topping one up either blocks for a real reason or goes green immediately
    and changes nothing. A reviewer-attested checklist is the opposite: adding one to a gate that
    is already pending would confront a reviewer with questions they were never shown, and the
    platform has no honest way to answer those on their behalf.

    Existing conditions are never touched — this only appends keys that are absent, so a
    reviewer's attestations and a derived condition's current state both survive.
    """
    current = [dict(c) for c in (approval.conditions or [])]
    phase = _phase_of(approval)
    if not phase:
        return current
    seen = {c.get("key") for c in current}
    for condition in conditions_for_phase(
        phase, tenant_id=tenant_id, project_id=approval.work_item.project_id,
    ):
        if condition.get("derived") and condition.get("key") not in seen:
            current.append(condition)
    return current


def current_conditions(approval, *, tenant_id) -> list:
    """This gate's checklist as it stands right now — topped up and re-derived, not persisted.

    The read path and the decide path must agree, or the reviewer is told one thing and the
    platform does another. Stored conditions alone cannot agree with it: a derived condition is
    seeded `satisfied: False` and only ever recomputed at decide time, so a checklist read
    straight from the column shows every platform-evaluated rule as unmet even when nothing is
    actually blocking — which disables Approve in the UI on a gate the backend would let through.

    Harmless to call on a decided approval; it just reports what is true now.
    """
    topped_up = _top_up_derived_conditions(approval, tenant_id=tenant_id)
    return refresh_derived(
        topped_up, tenant_id=tenant_id, work_item_id=approval.work_item_id,
        run_id=approval.run_id, project_id=approval.work_item.project_id,
    )


def gate_roles_decidable_by(*, tenant_id, user_id, project_id) -> frozenset[str] | None:
    """Which gates this person may decide on this project: the `required_role` values they
    hold, or `None` meaning every gate.

    One definition for the two callers that must never disagree — `decide_gate`, which enforces
    it, and the dashboard, which lists "Gates need your approval" (Bugs S.No 222). A queue built on
    a different rule from the check behind its Approve button would show people gates they are
    then refused on, or hide gates that genuinely are theirs.

    The rule itself is unchanged (team decision, P4.7-T4): the gate's required role on this
    project, OR project-admin (`Membership(role="admin")`), OR tenant-admin. Either kind of admin
    may decide any gate, which is why they get `None` rather than a list of roles.
    """
    roles = frozenset(
        Membership.objects.filter(
            tenant_id=tenant_id, user_id=user_id, project_id=project_id,
        ).values_list("role", flat=True)
    )
    if Role.ADMIN in roles:
        return None
    if User.objects.filter(id=user_id, tenant_id=tenant_id, is_tenant_admin=True).exists():
        return None
    return roles


def may_decide_gate(*, tenant_id, user_id, project_id, required_role) -> bool:
    """True when `gate_roles_decidable_by` lets this person decide a gate needing `required_role`."""
    roles = gate_roles_decidable_by(tenant_id=tenant_id, user_id=user_id, project_id=project_id)
    return roles is None or required_role in roles


def _default_signal_sender(
    workflow_id: str, decision: str, approver_id: str | None, comment: str,
    revise: bool = False,
) -> None:
    import asyncio

    from temporalio.client import Client

    from orchestration.types import GateDecision

    async def _send() -> None:
        client = await Client.connect(
            settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE
        )
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal(
            "gate_decision",
            GateDecision(decision=decision, approver_id=approver_id, comment=comment,
                         revise=revise),
        )

    asyncio.run(_send())


def decide_gate(
    *,
    tenant_id: str,
    approval_id: str,
    user_id: str,
    decision: str,
    comment: str = "",
    conditions: list | None = None,
    revise: bool = False,
    signal_sender=None,
) -> dict:
    """Record a gate decision (after role check + condition check) and signal the workflow
    to resume. `conditions` carries the reviewer's `satisfied` updates for the gate's
    checklist (e.g. the WCAG 2.2 AA criteria on the design gate); an APPROVED decision is
    rejected while any *required* condition is unsatisfied (D6). Derived conditions (e.g. the
    test gate's blocking-test rule, D9) are recomputed from live state here and ignore the
    reviewer's `satisfied` — they are the platform's finding, not the reviewer's.

    `revise` is "Request changes": a rejection the reviewer wants ACTED ON. The decision recorded
    is still `rejected` — that is the audit truth, and adding a third decision value would change
    the meaning of every historical row — but the workflow re-runs the phase with `comment` as
    authoritative direction. It is meaningless without a comment (there would be nothing to act on)
    and meaningless on an approval, so both are refused rather than silently ignored."""
    if decision not in _VALID_DECISIONS:
        raise GateError("That isn't a decision this gate accepts.")
    if revise and decision != "rejected":
        raise GateError("Requesting changes can't be combined with approving.")
    if revise and not (comment or "").strip():
        raise GateError(
            "Say what needs to change — the comment is what the next run works from."
        )
    signal_sender = signal_sender or _default_signal_sender

    with tenant_context(tenant_id):
        approval = Approval.objects.select_related("work_item", "run", "run__agent_spec").get(
            id=approval_id, tenant_id=tenant_id
        )
        if approval.decision != Approval.Decision.PENDING:
            raise GateError(
                "Someone has already decided this gate — it was "
                f"{approval.get_decision_display().lower()}. Refresh to see the latest."
            )

        # Role check: the deciding user must hold the required role on this project — OR be
        # an admin who can approve any gate (project-admin = Membership(role="admin"), or
        # tenant-admin = User.is_tenant_admin). Team decision (P4.7-T4). The same function
        # builds the dashboard's "Gates need your approval" queue (S.No 222), so the queue and
        # this check cannot drift apart.
        if not may_decide_gate(
            tenant_id=tenant_id, user_id=user_id,
            project_id=approval.work_item.project_id, required_role=approval.required_role,
        ):
            # Screen Words group 5. Named role, no internal user id. "Or an admin" is true here:
            # `may_decide_gate` lets a project or workspace admin decide any gate.
            from apps.labels import role_label

            raise GateRoleError(
                f"Only a {role_label(approval.required_role)} on this project, or an admin, "
                "can decide this gate."
            )

        # Fold in the reviewer's checklist updates, re-derive the platform-evaluated ones from
        # live state, then enforce required conditions on APPROVE.
        approval.conditions = _merge_conditions(approval.conditions, conditions)
        # Top up any derived rule this gate predates (S.No 178), then re-derive the
        # platform-evaluated ones from live state — the same two steps the read path takes, so
        # the checklist a reviewer was shown is the checklist that is enforced here. The run and
        # the project travel with the refresh (QA-15a): the blocking-test rule needs only the
        # work item, but the accessibility gate reads the project's policy and the run whose
        # findings it is judging, and every evaluator takes the same context.
        approval.conditions = current_conditions(approval, tenant_id=tenant_id)
        if decision == "approved":
            unmet = [
                c for c in (approval.conditions or [])
                if c.get("required") and not c.get("satisfied")
            ]
            if unmet:
                # Nothing is persisted on a blocked approve (the approval stays untouched and
                # PENDING), so a derived condition's `detail` — the tests actually holding the
                # gate shut — has to travel in the error, or the reviewer is told only "no".
                reasons = "; ".join(
                    str(c.get("key")) + (f" ({c['detail']})" if c.get("detail") else "")
                    for c in unmet
                )
                raise GateConditionsError(  # noqa: CLIENT-TEXT — Group 1, on hold for the team
                    f"cannot approve: {len(unmet)} required gate condition(s) unmet: {reasons}"
                )

        workflow_id = approval.run.temporal_workflow_id
        if not workflow_id:
            raise GateError(
                "This gate's run is no longer active, so the decision can't reach it. "
                "Start the phase again."
            )

        approval.decision = (
            Approval.Decision.APPROVED if decision == "approved" else Approval.Decision.REJECTED
        )
        approval.approver_id = user_id
        approval.comment = comment
        approval.decided_at = datetime.now(UTC)
        approval.save(update_fields=["decision", "approver", "comment", "conditions",
                                     "decided_at", "updated_at"])

        tools.log_event(
            tenant_id, f"user:{user_id}", "gate.decided", "approval", str(approval.id),
            {"decision": decision, "comment": comment, "revise": revise},
        )
        result = {
            "id": str(approval.id),
            "decision": approval.decision,
            "approver_id": user_id,
            "comment": comment,
            "conditions": approval.conditions,
            "revise": revise,
        }

    # Signal outside the tenant_context cursor.
    signal_sender(workflow_id, decision, user_id, comment, revise=revise)
    return result
