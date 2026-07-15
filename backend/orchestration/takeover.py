"""Human takeover (Phase-2 §7, PG10) — the developer-in-the-loop control.

A developer can take a WorkItem over and just **work the worktree by hand** — commit, push,
iterate locally, exactly as today. `request_takeover` sets `WorkItem.takeover_flag`, which
pauses the platform's automated build steps for that item; the human's commits then reconcile
back through the signed GitHub webhook (`integrations.webhooks`). `release_takeover` hands the
item back to automation. Both log an Event so the ledger shows who drove each change. (Dead-
lettered runs are routed here by the saga's offline/failed paths; this is the explicit, user-
initiated entry.)
"""
from __future__ import annotations

from mcp_platform_state import tools

from apps.tenancy.context import tenant_context
from apps.workitems.models import WorkItem


class TakeoverError(Exception):
    """The takeover could not be applied (e.g. unknown work item for this tenant)."""


def request_takeover(*, tenant_id: str, work_item_id: str, actor: str = "developer",
                     reason: str = "") -> dict:
    """Flag a WorkItem for human takeover (pauses automation for it) and log the Event."""
    with tenant_context(tenant_id):
        work_item = WorkItem.objects.filter(id=work_item_id, tenant_id=tenant_id).first()
        if work_item is None:
            raise TakeoverError(f"work item {work_item_id} not found in tenant")
        if not work_item.takeover_flag:
            work_item.takeover_flag = True
            work_item.save(update_fields=["takeover_flag", "updated_at"])
    tools.log_event(tenant_id, actor, "workitem.takeover", "work_item", str(work_item_id),
                    {"reason": reason})
    return {"work_item_id": str(work_item_id), "takeover": True}


def release_takeover(*, tenant_id: str, work_item_id: str, actor: str = "developer") -> dict:
    """Return a taken-over WorkItem to automated handling and log the Event."""
    with tenant_context(tenant_id):
        work_item = WorkItem.objects.filter(id=work_item_id, tenant_id=tenant_id).first()
        if work_item is None:
            raise TakeoverError(f"work item {work_item_id} not found in tenant")
        if work_item.takeover_flag:
            work_item.takeover_flag = False
            work_item.save(update_fields=["takeover_flag", "updated_at"])
    tools.log_event(tenant_id, actor, "workitem.takeover_released", "work_item",
                    str(work_item_id), {})
    return {"work_item_id": str(work_item_id), "takeover": False}


def _default_abandon_sender(workflow_id: str) -> None:
    import asyncio

    from django.conf import settings
    from temporalio.client import Client

    async def _send() -> None:
        client = await Client.connect(
            settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE
        )
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal("abandon_run")

    asyncio.run(_send())


def abandon_stalled_run(*, tenant_id: str, run_id: str, signal_sender=None) -> dict:
    """End a report-timeout-parked (STALLED) run terminally when a human explicitly takes it
    over (Bugs S.No 89). A soft-takeover keeps the AgentRunWorkflow ALIVE so a returning
    companion can still reconcile; but once the operator decides to hand-work the item or
    re-run from a clean dispatch, the old still-waiting run must not linger — signal it to
    abandon. No-op for any run that is not currently parked (only STALLED runs wait on this
    signal), and tolerant of an already-gone workflow (a late report may have just reconciled
    it, or it was a server-side run with no live handle)."""
    from apps.runs.models import Run

    signal_sender = signal_sender or _default_abandon_sender
    with tenant_context(tenant_id):
        run = Run.objects.filter(id=run_id, tenant_id=tenant_id).first()
        if run is None or run.status != Run.Status.STALLED or not run.temporal_workflow_id:
            return {"run_id": str(run_id), "abandoned": False}
        workflow_id = run.temporal_workflow_id
    try:
        signal_sender(workflow_id)
    except Exception as exc:  # noqa: BLE001
        # The workflow may have already completed (e.g. a report landed first and reconciled
        # it). That is not an error — the run is no longer parked either way.
        if "already completed" in str(exc).lower() or "not found" in str(exc).lower():
            return {"run_id": str(run_id), "abandoned": False,
                    "note": "no live workflow to abandon"}
        raise
    return {"run_id": str(run_id), "abandoned": True}
