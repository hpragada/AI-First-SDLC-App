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
            raise TakeoverError(
                "That work item no longer exists, so it can't be taken over."
            )
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
            raise TakeoverError(
                "That work item no longer exists, so it can't be taken over."
            )
        if work_item.takeover_flag:
            work_item.takeover_flag = False
            work_item.save(update_fields=["takeover_flag", "updated_at"])
    tools.log_event(tenant_id, actor, "workitem.takeover_released", "work_item",
                    str(work_item_id), {})
    return {"work_item_id": str(work_item_id), "takeover": False}


def _signal_sender(workflow_id: str, signal_name: str) -> None:
    """Send one signal to a live workflow (the seam tests substitute)."""
    import asyncio

    from django.conf import settings
    from temporalio.client import Client

    async def _send() -> None:
        client = await Client.connect(
            settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE
        )
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal(signal_name)

    asyncio.run(_send())


def _default_abandon_sender(workflow_id: str) -> None:
    _signal_sender(workflow_id, "abandon_run")


def _default_resume_sender(workflow_id: str) -> None:
    _signal_sender(workflow_id, "resume_run")


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


class ResumeError(Exception):
    """The run cannot be resumed (not parked, or nothing left to resume)."""


def resume_stalled_run(*, tenant_id: str, run_id: str, signal_sender=None) -> dict:
    """Resume a run parked by an error, from the step that failed (Bugs S.No 157).

    Before, any mid-run error ended the workflow terminally, so the only way forward was a whole
    new run from step 1 — re-doing the expensive build/phase. A parked run's workflow is still
    ALIVE and waiting on this signal, so resuming picks up at the failed step and keeps everything
    already done (the build, the branch, the PR).

    Only ever signals a genuinely parked-by-error run: STALLED **and** flagged `outputs.resumable`
    by park_build/park_run. That flag is what distinguishes it from an S.No 89 report-timeout park,
    which is not waiting on `resume_run` and whose recovery is the takeover path instead."""
    from apps.runs.models import Run

    signal_sender = signal_sender or _default_resume_sender
    with tenant_context(tenant_id):
        run = Run.objects.filter(id=run_id, tenant_id=tenant_id).first()
        if run is None:
            raise ResumeError("That run no longer exists.")
        outputs = run.outputs or {}
        if run.status != Run.Status.STALLED or not outputs.get("resumable"):
            raise ResumeError(
                "This run isn't paused at a step that can be picked up, so there is nothing to "
                "resume. Start the phase again instead."
            )
        if not run.temporal_workflow_id:
            raise ResumeError(
                "This run is no longer active, so it can't be picked up. Start the phase again "
                "instead."
            )
        workflow_id, resume_from = run.temporal_workflow_id, outputs.get("resume_from", "")
    try:
        signal_sender(workflow_id)
    except Exception as exc:  # noqa: BLE001
        # A workflow that has since closed can't be resumed — say so plainly rather than 500.
        if "already completed" in str(exc).lower() or "not found" in str(exc).lower():
            # Screen Words group 5: capital, no "workflow" (the reader has never heard of one),
            # and the thing to do next as an instruction rather than an aside.
            raise ResumeError(
                "This run has already finished, so it can't be picked up. Start the phase "
                "again instead."
            ) from exc
        raise
    return {"run_id": str(run_id), "resumed": True, "resume_from": resume_from}
