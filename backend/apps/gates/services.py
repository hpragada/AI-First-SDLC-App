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
from apps.gates.conditions import refresh_derived
from apps.gates.models import Approval
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Membership, User

_VALID_DECISIONS = {"approved", "rejected"}


class GateError(Exception):
    """Gate decision could not be applied (e.g. already decided, no workflow)."""


class GateRoleError(GateError):
    """Deciding user lacks the gate's required Membership role."""


class GateConditionsError(GateError):
    """A required gate condition (e.g. a WCAG 2.1 AA criterion) is not yet satisfied."""


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


def _default_signal_sender(
    workflow_id: str, decision: str, approver_id: str | None, comment: str
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
            GateDecision(decision=decision, approver_id=approver_id, comment=comment),
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
    signal_sender=None,
) -> dict:
    """Record a gate decision (after role check + condition check) and signal the workflow
    to resume. `conditions` carries the reviewer's `satisfied` updates for the gate's
    checklist (e.g. the WCAG 2.1 AA criteria on the design gate); an APPROVED decision is
    rejected while any *required* condition is unsatisfied (D6). Derived conditions (e.g. the
    test gate's blocking-test rule, D9) are recomputed from live state here and ignore the
    reviewer's `satisfied` — they are the platform's finding, not the reviewer's."""
    if decision not in _VALID_DECISIONS:
        raise GateError(f"invalid decision: {decision!r}")
    signal_sender = signal_sender or _default_signal_sender

    with tenant_context(tenant_id):
        approval = Approval.objects.select_related("work_item", "run").get(
            id=approval_id, tenant_id=tenant_id
        )
        if approval.decision != Approval.Decision.PENDING:
            raise GateError(f"approval already decided: {approval.decision}")

        # Role check: the deciding user must hold the required role on this project — OR be
        # an admin who can approve any gate (project-admin = Membership(role="admin"), or
        # tenant-admin = User.is_tenant_admin). Team decision (P4.7-T4).
        has_role = Membership.objects.filter(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=approval.work_item.project_id,
            role__in=[approval.required_role, Role.ADMIN],
        ).exists()
        if not has_role:
            has_role = User.objects.filter(
                id=user_id, tenant_id=tenant_id, is_tenant_admin=True
            ).exists()
        if not has_role:
            raise GateRoleError(
                f"user {user_id} lacks role '{approval.required_role}' for this gate"
            )

        # Fold in the reviewer's checklist updates, re-derive the platform-evaluated ones from
        # live state, then enforce required conditions on APPROVE.
        approval.conditions = _merge_conditions(approval.conditions, conditions)
        approval.conditions = refresh_derived(
            approval.conditions, tenant_id=tenant_id, work_item_id=approval.work_item_id,
        )
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
                raise GateConditionsError(
                    f"cannot approve: {len(unmet)} required gate condition(s) unmet: {reasons}"
                )

        workflow_id = approval.run.temporal_workflow_id
        if not workflow_id:
            raise GateError("run has no temporal_workflow_id; cannot resume the workflow")

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
            {"decision": decision, "comment": comment},
        )
        result = {
            "id": str(approval.id),
            "decision": approval.decision,
            "approver_id": user_id,
            "comment": comment,
            "conditions": approval.conditions,
        }

    # Signal outside the tenant_context cursor.
    signal_sender(workflow_id, decision, user_id, comment)
    return result
