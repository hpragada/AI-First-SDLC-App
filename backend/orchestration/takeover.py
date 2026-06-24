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
