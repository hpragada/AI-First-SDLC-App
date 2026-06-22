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

from apps.gates.models import Approval
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Membership

_VALID_DECISIONS = {"approved", "rejected"}


class GateError(Exception):
    """Gate decision could not be applied (e.g. already decided, no workflow)."""


class GateRoleError(GateError):
    """Deciding user lacks the gate's required Membership role."""


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
    signal_sender=None,
) -> dict:
    """Record a gate decision (after role check) and signal the workflow to resume."""
    if decision not in _VALID_DECISIONS:
        raise GateError(f"invalid decision: {decision!r}")
    signal_sender = signal_sender or _default_signal_sender

    with tenant_context(tenant_id):
        approval = Approval.objects.select_related("work_item", "run").get(
            id=approval_id, tenant_id=tenant_id
        )
        if approval.decision != Approval.Decision.PENDING:
            raise GateError(f"approval already decided: {approval.decision}")

        # Role check: the deciding user must hold the required role on this project.
        has_role = Membership.objects.filter(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=approval.work_item.project_id,
            role=approval.required_role,
        ).exists()
        if not has_role:
            raise GateRoleError(
                f"user {user_id} lacks role '{approval.required_role}' for this gate"
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
        approval.save(update_fields=["decision", "approver", "comment", "decided_at", "updated_at"])

        tools.log_event(
            tenant_id, f"user:{user_id}", "gate.decided", "approval", str(approval.id),
            {"decision": decision, "comment": comment},
        )
        result = {
            "id": str(approval.id),
            "decision": approval.decision,
            "approver_id": user_id,
            "comment": comment,
        }

    # Signal outside the tenant_context cursor.
    signal_sender(workflow_id, decision, user_id, comment)
    return result
