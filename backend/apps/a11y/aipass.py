"""Running the AI accessibility pass on a completed test run (QA-12).

The two ends of this file are the whole task. `start_ai_pass` picks up what the test run
captured and asks the judge; `finish_ai_pass` runs when the judge's run ends and turns its
verdicts into the merged report. Everything between them was built in QA-02, QA-03, QA-06,
QA-07 and QA-11b and is called here for the first time.

**Why the judge runs on its own work item.** `orchestration.trigger._guard_no_active_run`
refuses to start a run for a work item that already has a live one, and the test run's own run
stays live for the whole build workflow — so dispatching the judge against the story would be
refused every single time. It gets a work item of its own instead, one per source run, keyed on
a stable stream name. Per *run* rather than per project on purpose: a project-wide container
would be a live run whenever any build in that project was judging, and two builds finishing
close together would collide on exactly the guard this avoids.

**The pass never fails the build.** Every entry point here returns a dict saying what happened
and swallows what went wrong. A build whose branch, tests and defects are all correct must not
be failed because an accessibility judgment could not be started — the capture is already
stored, and the pass can be run again against the same run without re-capturing anything.

**Where the report comes from depends on whether a judge ran at all.** If everything was
answered from cache, or there was no judge to ask, no run starts — and the merged report is
published here and now, from what is already known. If a run does start, the report waits for
it, because half the verdicts are still in flight.
"""
from __future__ import annotations

from apps.tenancy.context import tenant_context

from .defects import record_a11y_findings
from .dispatch import dispatch_judgments, record_verdict
from .ingest import requests_for
from .report import publish_report

#: The `feature_stream` a judging work item is keyed on. Mirrors `ci_ingest._REGRESSION_STREAM`
#: — a stable string get-or-create can key on, distinctive enough to be greppable and obviously
#: not a human's feature name.
JUDGING_STREAM = "__a11y_judging__"

#: Where the judge run remembers which run's capture it was asked about. Read back by
#: `finish_ai_pass`, because the verdicts land under the judge's run while the report belongs
#: to the run that did the testing.
SOURCE_RUN_KEY = "a11y_source_run"


def judging_work_item(*, tenant_id, project_id, run_id, parent_work_item_id=None,
                      title: str = ""):
    """The work item this run's accessibility judging runs on (get-or-create; idempotent)."""
    from apps.workitems.models import WorkItem

    stream = f"{JUDGING_STREAM}{run_id}"
    with tenant_context(tenant_id):
        item, _ = WorkItem.objects.get_or_create(
            tenant_id=tenant_id, project_id=project_id,
            feature_stream=stream, type=WorkItem.Type.TASK,
            defaults={
                "title": f"Accessibility judging{f' — {title}' if title else ''}",
                "description": (
                    "The AI accessibility checks for one test run. Created by the platform; "
                    "it exists so the judge has a work item of its own to run on."
                ),
                "state": WorkItem.State.IN_PROGRESS,
                "parent_id": parent_work_item_id,
                "external_ref": {"kind": "a11y_judging", "run": str(run_id)},
            },
        )
    return item


def _remember_source_run(tenant_id, judge_run_id, source_run_id) -> None:
    """Note on the judge's run which capture it is judging.

    Kept on `Run.inputs` next to the batches `dispatch` already puts there, rather than passed
    through the workflow: the judge run is started by `trigger_phase`, whose signature belongs
    to every phase in the platform and must not grow an accessibility-shaped argument (#9's
    reasoning applied to our own seams).
    """
    from apps.runs.models import Run

    with tenant_context(tenant_id):
        run = Run.objects.filter(id=judge_run_id, tenant_id=tenant_id).first()
        if run is None:                                  # pragma: no cover - just dispatched
            return
        run.inputs = {**(run.inputs or {}), SOURCE_RUN_KEY: str(source_run_id)}
        run.save(update_fields=["inputs", "updated_at"])


def _triggering_user(tenant_id, run_id):
    """Who started the test run — the judge runs on their companion, as every phase does."""
    from apps.runs.models import Run

    with tenant_context(tenant_id):
        run = Run.objects.filter(id=run_id, tenant_id=tenant_id).first()
        return str(run.triggered_by_id) if run and run.triggered_by_id else None


def start_ai_pass(*, tenant_id, project_id, run_id, work_item_id=None, title: str = "",
                  trigger=None) -> dict:
    """Ask the AI checks about everything this run captured. Never raises.

    Returns what happened in numbers a person can check — how many elements were already known,
    how many were sent, how many were left for the next run at the cap — because "did the AI
    pass actually do anything?" must be answerable without reading a log.
    """
    requests = requests_for(tenant_id, project_id, run_id)
    if not requests:
        # Not an error and not a clean page: a run that captured nothing simply has nothing to
        # judge. Whether a scan should have run is the test report's question, not this one's.
        return {"started": False, "dispatched": 0, "from_cache": 0, "deferred": 0,
                "reason": "no accessibility candidates were captured for this run"}

    item = judging_work_item(tenant_id=tenant_id, project_id=project_id, run_id=run_id,
                             parent_work_item_id=work_item_id, title=title)
    result = dispatch_judgments(
        tenant_id=tenant_id, project_id=project_id, work_item_id=str(item.id),
        requests=requests, triggered_by=_triggering_user(tenant_id, run_id), trigger=trigger,
    )

    out: dict = {
        "started": bool(result.run_id),
        "judge_run_id": result.run_id,
        "dispatched": len(result.dispatched),
        "from_cache": len(result.from_cache),
        "deferred": len(result.deferred),
        "reason": result.unavailable_reason,
    }
    # Whatever could not be asked about is FILED, not just reported (QA-13). `dispatch` builds
    # a complete `uncertain` for each one carrying the real reason — "no judge is registered in
    # this workspace", "no machine is connected" — and until this line the caller read that
    # sentence and threw the results away. Two things went wrong because of it: the report said
    # "no verdict was recorded" instead of why, and nothing reached the review queue, so the
    # queue stood empty in precisely the situation that should fill it.
    out["filed_unjudged"] = _file_unjudged(
        tenant_id=tenant_id, project_id=project_id, result=result)

    if result.run_id:
        _remember_source_run(tenant_id, result.run_id, run_id)
        # The report waits for the judge — half its verdicts are still in flight.
        return out

    # Nothing was dispatched: everything came from cache, or there was no judge to ask. Either
    # way what is knowable is known now, so the report is published here rather than never.
    out["report"] = _publish(tenant_id=tenant_id, project_id=project_id, run_id=run_id,
                             title=title)
    return out


def _file_unjudged(*, tenant_id, project_id, result) -> int:
    """Store the `uncertain` results for everything the dispatch could not ask about.

    Safe to store *because* the dispatch cache no longer serves an `uncertain` back to a later
    dispatch (see `dispatch._cached`). Without that, filing these would be the worse bug: the
    element would be permanently answered "the judge was unavailable" and never asked again.
    """
    for request, judgment in zip(result.unjudged_requests, result.unjudged, strict=True):
        record_verdict(tenant_id=tenant_id, project_id=project_id, run_id=None,
                       content_hash=request.content_hash, judgment=judgment)
    return len(result.unjudged_requests)


def finish_ai_pass(*, tenant_id, judge_run_id) -> dict:
    """Publish the merged report for the run this judgment run was about. Never raises.

    Called when the judge's run ends — including when it ends badly. An incomplete judgment run
    still has to produce a report, because its unjudged elements were recorded as `uncertain`
    for human review and a person has to be able to see them. The report says at the top that
    the check was incomplete (D-A11Y-3), so a partial pass is never readable as a clean one.
    """
    from apps.runs.models import Run

    with tenant_context(tenant_id):
        run = Run.objects.filter(id=judge_run_id, tenant_id=tenant_id).first()
        inputs = (run.inputs or {}) if run else {}
        project_id = str(run.work_item.project_id) if run else None
    source_run = str(inputs.get(SOURCE_RUN_KEY) or "")
    if not source_run or project_id is None:
        # Not a judgment run this module started (or a run that has since gone). Nothing to
        # publish, and nothing wrong: say so rather than guessing which run it meant.
        return {"published": False, "reason": "this run carries no accessibility source run"}
    return {"published": True,
            "report": _publish(tenant_id=tenant_id, project_id=project_id,
                               run_id=source_run, title="")}


def _publish(*, tenant_id, project_id, run_id, title: str) -> dict:
    """`publish_report`, then the defect loopback — with failures turned into a reported fact.

    The merge reads a tenant's configured thresholds, and `thresholds_for` deliberately raises
    on a misconfiguration rather than falling back — that is right, and it must not take a
    build down with it. The build already has its branch, its tests and its defects; losing the
    accessibility report is a smaller loss than losing those, and the reason is returned so it
    is visible rather than swallowed.

    The defect loopback runs **here rather than inside `publish_report`** (QA-14), so the
    sequence reads dispatch → report → defects and a function called "publish report" stays one
    that renders and registers. It runs after, and separately, because a report that could not
    be written is not a reason to leave a real accessibility failure untracked — nor the other
    way round.
    """
    out: dict
    try:
        out = publish_report(tenant_id=tenant_id, project_id=project_id, run_id=run_id,
                             title=title)
    except Exception as exc:  # noqa: BLE001 — see the docstring
        out = {"artifact_id": None, "error": str(exc)}
    try:
        out["defects"] = record_a11y_findings(tenant_id=tenant_id, project_id=project_id,
                                              run_id=run_id)
    except Exception as exc:  # noqa: BLE001 — same trade: never fail a build over the loopback
        out["defects"] = {"error": str(exc)}
    return out
