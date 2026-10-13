"""A merge that happened outside the platform (Bugs S.No 88).

A developer merging the pull request on GitHub is a legitimate outcome, not a policy breach —
the team was explicit that developer habits must not be changed to suit the platform. But the
merge gate then waited for an approval nobody would ever give: the run sat at `awaiting_gate`
for ever, the work item never reached done, its documents stayed drafts and the preview
environment was never torn down. The reviewer saw a gate asking them to approve a merge that
had already happened, with nothing on screen saying so.

**Nothing in here decides a gate.** Detection only writes a note; a person still approves
through the same endpoint, with the same role check, the same ledger event and the same signal
to the workflow. That containment is not decoration — the GitHub webhook secret is a single
global setting and the tenant rides in the URL path, so anyone able to sign a payload can aim
it at any workspace. Because a mis-addressed delivery can only ever add a note that a human
must still act on, the blast radius of that weakness stays at zero. Making the platform
self-approve on a webhook would turn it into a way to complete somebody else's run.

The workflow needs no change at all: `merge_build_pr_core` already reads the pull request
first and skips an already-merged one, so the moment any approval arrives the run completes
correctly on its own.
"""
from __future__ import annotations

from mcp_platform_state import tools

#: The gate that holds a build before its pull request is merged.
MERGE_GATE_TYPE = "merge_gate"


def pending_merge_gate(tenant_id: str, run_id):
    """The un-decided merge gate for this run, or None."""
    from apps.gates.models import Approval

    return Approval.objects.filter(
        run_id=run_id, tenant_id=tenant_id,
        gate_type=MERGE_GATE_TYPE, decision=Approval.Decision.PENDING,
    ).first()


def note_external_merge(tenant_id: str, run, *, repo: str, number, merged_by: str = "",
                        merged_at: str = "", detected_by: str = "webhook") -> str | None:
    """Record on the pending merge gate that its pull request is already merged.

    Idempotent: a gate that already carries the note is left exactly as it is, so a redelivered
    webhook and the sweep cannot fight over it or log the same observation twice. Returns the
    approval id when a note was newly written, else None.
    """
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        approval = pending_merge_gate(tenant_id, run.id)
        if approval is None or approval.external_merge:
            return None
        approval.external_merge = {
            "merged_by": merged_by or "",
            "merged_at": merged_at or "",
            "pr_ref": f"{repo}#{number}" if repo and number else "",
            "detected_by": detected_by,
        }
        approval.save(update_fields=["external_merge", "updated_at"])
        tools.log_event(
            tenant_id, detected_by, "webhook.pr_merged_while_gated", "approval",
            str(approval.id),
            {"pr_ref": approval.external_merge["pr_ref"], "merged_by": merged_by,
             "run_id": str(run.id), "work_item_id": str(run.work_item_id)},
        )
        return str(approval.id)
