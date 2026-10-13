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


def _signal_sender(workflow_id: str, signal_name: str, *args) -> None:
    """Send one signal to a live workflow (the seam tests substitute). `args` are the signal's own
    arguments — `pause_run` carries who paused the run; `resume_run` and `abandon_run` take none."""
    import asyncio

    from django.conf import settings
    from temporalio.client import Client

    async def _send() -> None:
        client = await Client.connect(
            settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE
        )
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal(signal_name, *args)

    asyncio.run(_send())


def _default_abandon_sender(workflow_id: str) -> None:
    _signal_sender(workflow_id, "abandon_run")


def _default_resume_sender(workflow_id: str) -> None:
    _signal_sender(workflow_id, "resume_run")


def _default_pause_sender(workflow_id: str, paused_by: str) -> None:
    _signal_sender(workflow_id, "pause_run", paused_by)


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
        # PAUSED counts here too: discarding a run the user paused is the same signal and the same
        # terminal end. Without it, a paused run could only ever be resumed — and because PAUSED
        # blocks a re-trigger of that phase, somebody who changed their mind would have been stuck.
        if (run is None or not run.temporal_workflow_id
                or run.status not in (Run.Status.STALLED, Run.Status.PAUSED)):
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

    Only ever signals a run that is genuinely waiting on this signal: STALLED or PAUSED, **and**
    flagged `outputs.resumable` by park_build/park_run/pause_run. That flag is what distinguishes it
    from an S.No 89 report-timeout park, which is not waiting on `resume_run` and whose recovery is
    the takeover path instead.

    PAUSED runs come through here unchanged: the workflow waits on the same `resume_run` signal
    whether it parked at an error or was paused on purpose, which is why the console offers one
    Resume for both and why this needed no second code path."""
    from apps.runs.models import Run

    signal_sender = signal_sender or _default_resume_sender
    with tenant_context(tenant_id):
        run = Run.objects.filter(id=run_id, tenant_id=tenant_id).first()
        if run is None:
            raise ResumeError("That run no longer exists.")
        outputs = run.outputs or {}
        if (run.status not in (Run.Status.STALLED, Run.Status.PAUSED)
                or not outputs.get("resumable")):
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
        was_paused = run.status == Run.Status.PAUSED
    if was_paused:
        # Release the run HERE, not in the workflow. A run paused while its companion was working
        # leaves the workflow blocked on `wait_condition(report)`, which `resume_run` does not
        # satisfy — so nothing would ever call `resume_run_state`, the dispatch would stay out of
        # the claim queue, and the run would be stuck paused for good. Doing it synchronously means
        # the companion can claim the work again the moment the person presses Resume, rather than
        # whenever the workflow next happens to wake. Idempotent, so the workflow calling it again
        # at its own checkpoint changes nothing.
        #
        # The error-park path is deliberately NOT routed through here: its workflow is always
        # sitting in the park wait when the signal lands, so it un-parks itself correctly, and that
        # behaviour is covered by the S.No 157 tests.
        from .activities import resume_run_state

        resume_run_state(str(tenant_id), str(run_id), extra_keys=("kept",))
    try:
        signal_sender(workflow_id)
    except Exception as exc:  # noqa: BLE001
        # A PAUSED run has already been released above, so a lost signal must not fail this request
        # — the dialog said "nothing was saved" while the console behind it showed the run running
        # again. What is lost is only the workflow's own un-parking, which it does idempotently when
        # it next wakes.
        #
        # An error-parked run is NOT treated this way, deliberately: there the un-parking happens
        # INSIDE the workflow, so a signal that never lands means nothing has happened and the
        # refusal below is the honest answer.
        if was_paused and "already completed" not in str(exc).lower() \
                and "not found" not in str(exc).lower():
            tools.log_event(str(tenant_id), "platform", "run.resume_signal_failed", "run",
                            str(run_id),
                            {"error_detail": str(exc)[:500],
                             "operator_note": ("the run is resumed and claimable again; the "
                                               "workflow was not reached")})
            return {"run_id": str(run_id), "resumed": True, "workflow_notified": False,
                    "resume_from": resume_from}
        # A workflow that has since closed can't be resumed — say so plainly rather than 500.
        if "already completed" in str(exc).lower() or "not found" in str(exc).lower():
            # Screen Words group 5: capital, no "workflow" (the reader has never heard of one),
            # and the thing to do next as an instruction rather than an aside.
            raise ResumeError(
                "This run has already finished, so it can't be picked up. Start the phase "
                "again instead."
            ) from exc
        raise
    return {"run_id": str(run_id), "resumed": True, "workflow_notified": True,
            "resume_from": resume_from}


class PauseError(Exception):
    """The run cannot be paused (already finished, waiting at a gate, or already paused)."""


# Statuses a pause makes sense for. A run AWAITING_GATE is already stopped and costs nothing —
# offering to pause it would be offering to stop something that is not running — and a terminal
# run has nothing left to pause.
_PAUSABLE = ("pending", "running")


def pause_run(*, tenant_id: str, run_id: str, paused_by: str = "", signal_sender=None) -> dict:
    """Stop a running phase on purpose, so the person can come back to it later.

    Two things happen here, and the order matters:

    1. **The dispatch is marked paused in our database, synchronously.** This is the only control we
       have over the companion, and it is a real one: the companion *pulls* work
       (`GET /api/runner/work/`), and the claim query only offers a dispatch that is `pending` or
       `claimed`. A paused dispatch is simply never handed out. Done here rather than in the
       workflow because the workflow is blocked waiting for the companion's report while a phase
       runs — it could not reach a checkpoint in time, and the companion polls every five seconds.
       So for the case that matters most, a pause pressed before the work is picked up, this is
       total and immediate.
    2. **The workflow is signalled**, so that when it next reaches a checkpoint it stops there
       instead of carrying on to the gate (or, for a build, into review, remediation and merge).

    What this does NOT do is interrupt an agent already working. There is no channel from the
    platform to the companion at all, and a terminated run once kept writing for 49 minutes. The
    dialog says so, and tells the user to close the companion if they need it stopped right now.

    Returns `was_claimed`, which is how the screen knows which of those two truths to tell."""
    from apps.runs.models import Run

    from .activities import pause_run_state
    from .build_activities import BUILD_KEPT

    signal_sender = signal_sender or _default_pause_sender
    with tenant_context(tenant_id):
        run = Run.objects.filter(id=run_id, tenant_id=tenant_id).first()
        if run is None:
            raise PauseError("That run no longer exists.")
        if run.status == Run.Status.PAUSED:
            # Idempotent, and said as agreement rather than as an error: two clicks on Pause, or a
            # second tab, must not read like a fault.
            return {"run_id": str(run_id), "paused": True, "already": True,
                    "was_claimed": bool(((run.outputs or {}).get("paused") or {})
                                        .get("was_claimed"))}
        if run.status not in _PAUSABLE:
            from apps.labels import run_status_label

            raise PauseError(
                f"This run is {run_status_label(run.status).lower()}, so there is nothing to pause."
            )
        if not run.temporal_workflow_id:
            raise PauseError("This run is no longer active, so it can't be paused.")
        workflow_id = run.temporal_workflow_id
        dispatch = (run.inputs or {}).get("dispatch") or {}
        is_build = dispatch.get("kind") == "build"
        kept = BUILD_KEPT if is_build else ""

    # Step 1 — hold the dispatch back, synchronously. The same function the activity uses, so there
    # is one definition of what "paused" means on a run.
    resume_from = "open_build_pr" if is_build else "dispatch_phase"
    result = pause_run_state(str(tenant_id), str(run_id), paused_by, resume_from, kept=kept)

    # Step 2 — tell the workflow, so it stops at its next checkpoint rather than opening the gate.
    notified = True
    try:
        signal_sender(workflow_id, paused_by)
    except Exception as exc:  # noqa: BLE001
        if "already completed" in str(exc).lower() or "not found" in str(exc).lower():
            # The run finished between our read and our signal — a companion's report can land at
            # any moment. Undo the hold rather than leave a finished run looking paused.
            from .activities import resume_run_state

            resume_run_state(str(tenant_id), str(run_id), extra_keys=("kept",))
            raise PauseError(
                "This run finished just now, so there was nothing left to pause."
            ) from exc
        # ANY OTHER failure — Temporal unreachable, a transport error, a timeout — must NOT fail
        # this request, and the reason is not politeness. Step 1 has already happened: the dispatch
        # is held back, which is the half that actually stops work, because the companion pulls and
        # a paused dispatch is never offered to it. Raising here returned a 500 that told the user
        # "nothing was saved" while the run sat paused on the screen behind the dialog — found by
        # opening a browser, and not catchable from a test that stubs the sender with a success.
        #
        # What is lost is the checkpoint stop: a workflow that was not told will carry on to its
        # gate. That is worth recording, not worth refusing the pause over.
        notified = False
        # `error_detail`, deliberately NOT `detail`/`error`/`reason`: EventSerializer.get_message
        # prints those straight onto the run console, and this one is a Rust transport dump. The
        # raw text belongs in the server log our team reads; the reader gets the sentence below.
        tools.log_event(str(tenant_id), "platform", "run.pause_signal_failed", "run", str(run_id),
                        {"error_detail": str(exc)[:500],
                         "operator_note": ("the run is paused and its companion will not be given "
                                           "the work; the workflow was not reached, so it may "
                                           "continue past its next checkpoint")})
    return {"run_id": str(run_id), "paused": True, "workflow_notified": notified,
            "was_claimed": bool(result.get("was_claimed"))}
