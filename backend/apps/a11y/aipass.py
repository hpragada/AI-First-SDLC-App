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
                # `source` is what marks this a CARRIER — internal plumbing that exists only to
                # host a run, hidden from the backlog, from Phases & Runs and from what an agent
                # is shown as this project's backlog (`integrations.onboarding.CARRIER_SOURCES`).
                # It was written as `kind` alone, which no filter in the platform reads, so every
                # test run left an "Accessibility judging" task on the user's board. `kind` is
                # kept beside it: it is what this object IS, and something may read it.
                "external_ref": {"kind": "a11y_judging", "source": "a11y_judging_carrier",
                                 "run": str(run_id)},
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
                  trigger=None, triggered_by=None, only_hashes=None) -> dict:
    """Ask the AI checks about everything this run captured. Never raises.

    Returns what happened in numbers a person can check — how many elements were already known,
    how many were sent, how many were left for the next run at the cap — because "did the AI
    pass actually do anything?" must be answerable without reading a log.

    `run_id` is the capture's **key**, which is normally an agent run's id and since QA-17 may
    instead be a baseline audit's. `triggered_by` exists for that case: the judge runs on
    somebody's companion, and with no `Run` to read the user off, the caller has to say who.

    `only_hashes` narrows the pass to named elements and exists for exactly one caller,
    `rejudge_capture`. Left None — every other caller — the whole capture is offered and
    `dispatch` decides, which is the original behaviour unchanged. It cannot be used to *widen*
    a pass: what it names is intersected with what was captured, never added to it.
    """
    requests = requests_for(tenant_id, project_id, run_id)
    if only_hashes is not None:
        wanted = {str(h) for h in only_hashes}
        requests = [r for r in requests if r.content_hash in wanted]
    if not requests:
        # Not an error and not a clean page: a run that captured nothing simply has nothing to
        # judge. Whether a scan should have run is the test report's question, not this one's.
        return {"started": False, "dispatched": 0, "from_cache": 0, "deferred": 0,
                "reason": ("none of the elements named are still in this capture"
                           if only_hashes is not None
                           else "no accessibility candidates were captured for this run")}

    item = judging_work_item(tenant_id=tenant_id, project_id=project_id, run_id=run_id,
                             parent_work_item_id=work_item_id, title=title)
    result = dispatch_judgments(
        tenant_id=tenant_id, project_id=project_id, work_item_id=str(item.id),
        requests=requests,
        triggered_by=triggered_by or _triggering_user(tenant_id, run_id), trigger=trigger,
    )

    out: dict = {
        "started": bool(result.run_id),
        "judge_run_id": result.run_id,
        "dispatched": len(result.dispatched),
        # How many DISTINCT elements those requests are about, which is not the same number and
        # is the one a screen must show. The same markup on ten pages — a site header, a footer
        # link — is one thing to judge: it hashes identically, one verdict answers all ten, and
        # the judge is right to record 81 verdicts for 144 requests. Counting requests against
        # verdicts made a complete run read as two-thirds done, which is this capability's own
        # worst failure told about itself.
        "distinct": len({r.content_hash for r in result.dispatched}),
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
    out = {"published": True,
           "report": _publish(tenant_id=tenant_id, project_id=project_id,
                              run_id=source_run, title="")}
    # If that capture key was a baseline audit's rather than a build run's, this is where the
    # audit ends (QA-17). Asked after the report is published, so an audit is never shown as
    # complete before the document it is complete *because of* exists.
    from .baseline import complete_audit

    out["audit_completed"] = complete_audit(tenant_id, source_run)
    return out


def close_unfinished_ai_pass(*, tenant_id, run_id) -> dict:
    """Close a judgment pass whose run DIED, if the run's own closing step never got to run.

    **Why the platform has to do this at all.** The judge's accounting — file every unjudged
    element as `uncertain`, then publish the merged report and complete the audit — lives in the
    run's write-completeness step, and a run that reports failure returns before that step is
    ever reached (`workflows.run`, the `phase_failed` branch). So an engine that crashed, lost
    its session or ran out of context left the audit reading *Checking what was found* for ever,
    with the elements it never answered recorded nowhere at all. That is the exact silence the
    whole design refuses: an element that was dispatched and never reported on must reach a
    person, and an audit that has stopped must say so.

    This is the judge's half of what `journey.close_unfinished_journey` already does one line
    below it in `fail_run_core`, and it lands the crash path in the state the normal path
    already produces — because the normal path publishes from a `finally` and completes the
    audit whether or not the judging was complete (QA-12, D-A11Y-3). A partial pass is never
    readable as a clean one: the report says at the top that the check was incomplete.

    Idempotent, and a no-op for a run that judged nothing — `verify_judgment_completeness`
    returns empty for a run carrying no batches and `finish_ai_pass` publishes nothing for a run
    carrying no source run, so every non-judging phase passes straight through. It DOES run
    twice on one path — a judging run whose completeness check failed reaches `fail_run` having
    already published from its `finally` — and that is left alone rather than guarded with a
    flag: `publish_report` registers-don't-recreates, `record_run_findings` records a finding
    seen again rather than a second copy, and `complete_audit` sets a status it already holds.
    Redundant work on an already-failing path, and no second report.

    Never raises. It runs on a path that is already failing, and a recovery that throws would
    mask the failure it was called to clean up after.
    """
    from .judge import verify_judgment_completeness

    out: dict = {"accounted": False, "reason": "", "closed": None}
    try:
        verify_judgment_completeness(tenant_id=tenant_id, run_id=run_id)
        out["accounted"] = True
    except Exception as exc:  # noqa: BLE001 — see the docstring
        # Raised BY DESIGN the moment anything was missing — but only after each missing element
        # has been filed as `uncertain`, which is the half that matters here. The run is already
        # failed and its reason already recorded, so the raise has nothing left to tell anyone;
        # its message is kept for the caller because it names how many went unanswered.
        out["reason"] = str(exc)[:300]
    try:
        out["closed"] = finish_ai_pass(tenant_id=tenant_id, judge_run_id=run_id)
    except Exception as exc:  # noqa: BLE001 — same trade
        out["closed"] = {"published": False, "error": str(exc)[:300]}
    return out


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


# ── asking again about what nothing ever looked at (task R1) ─────────────────


def _judge_run_for(tenant_id, capture_key: str) -> str:
    """The judging run that was started for this capture, whatever kind of capture it is.

    A baseline audit remembers its judge run on its own summary; a greenfield build run does
    not, so the judge run is found by the source-run key it was stamped with when it started
    (`_remember_source_run`). Newest first, because a capture may have been judged more than
    once and it is the last attempt that knows what is still unanswered.
    """
    from apps.runs.models import Run

    from .models import A11yBaselineAudit

    with tenant_context(tenant_id):
        audit = A11yBaselineAudit.objects.filter(
            id=capture_key, tenant_id=tenant_id).first() if _is_uuid(capture_key) else None
        if audit is not None:
            named = ((audit.summary or {}).get("ai_pass") or {}).get("judge_run_id")
            if named:
                return str(named)
        run = (Run.objects
               .filter(tenant_id=tenant_id, inputs__contains={SOURCE_RUN_KEY: capture_key})
               .order_by("-created_at").first())
    return str(run.id) if run else ""


def _is_uuid(value) -> bool:
    from uuid import UUID

    try:
        UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def unanswered_for_capture(*, tenant_id, project_id, run_id) -> list[str]:
    """The elements of this capture that NOTHING ever looked at. Content hashes, sorted.

    Two ways an element gets here, and both are *work that did not happen* rather than a
    judgement:

      * **the pass could not be started at all** — no judge registered in the workspace, no
        machine connected. `_file_unjudged` files those with no run against them, and nothing
        else in the platform writes a verdict with a null run;
      * **the judge run started and never reported on it** — it ran out of session, context or
        connection. `judge._remember_unanswered` records those on the run itself, at the one
        moment they are still distinguishable from an answered `uncertain`.

    Deliberately **not** "every `uncertain` in this capture". A check that looked and could not
    decide produced a real verdict; it belongs to a person, and handing it back to the machine
    for another attempt would quietly recycle the review queue's own contents.

    Everything is intersected with what this capture actually holds, because a judgment row is
    project-wide: without that, re-judging one audit would drag in another audit's leftovers.
    """
    from integrations.types import A11Y_UNCERTAIN

    from .models import A11yJudgmentCache

    key = str(run_id or "").strip()
    if not key:
        return []
    # Straight off the stored bundles — the same call `start_ai_pass` makes, so the hashes are
    # the ones a dispatch would actually use. `A11yCandidateBundle` stores the element, not its
    # hash: the hash is of (checker, candidate) and is computed here, once, by the same code.
    captured = {r.content_hash for r in requests_for(tenant_id, project_id, key)}
    if not captured:
        return []

    with tenant_context(tenant_id):
        hashes = set(
            A11yJudgmentCache.objects
            .filter(tenant_id=tenant_id, project_id=project_id, verdict=A11Y_UNCERTAIN,
                    run__isnull=True, content_hash__in=list(captured))
            .values_list("content_hash", flat=True)
        )
    judge_run_id = _judge_run_for(tenant_id, key)
    if judge_run_id:
        from apps.runs.models import Run

        from .judge import UNANSWERED_KEY

        with tenant_context(tenant_id):
            run = Run.objects.filter(id=judge_run_id, tenant_id=tenant_id).first()
        recorded = ((run.outputs or {}).get(UNANSWERED_KEY) or []) if run else []
        hashes |= {str(h) for h in recorded} & captured

    if not hashes:
        return []
    # Anything that has since been ANSWERED drops out, whoever answered it and whenever. A
    # re-judge that ran and succeeded leaves its verdicts here, and a list read from a run that
    # has been superseded would otherwise offer them up again — asking the machine to re-decide
    # what it has already decided, for ever.
    with tenant_context(tenant_id):
        answered = set(
            A11yJudgmentCache.objects
            .filter(tenant_id=tenant_id, project_id=project_id, content_hash__in=sorted(hashes))
            .exclude(verdict=A11Y_UNCERTAIN)
            .values_list("content_hash", flat=True)
        )
    return sorted(hashes - answered)


def rejudge_capture(*, tenant_id, project_id, run_id, title: str = "",
                    triggered_by=None, trigger=None) -> dict:
    """Ask the machine again about the elements nothing ever looked at (task R1). Never raises.

    **No page is visited and no browser is opened.** Everything the judge needs — the markup, the
    text around it, the computed styles, the accessible name, the screenshot crop — was stored
    when the pages were captured, and `requests_for` reads it straight back. This is a second
    pass over one capture, not a second audit, and the distinction is the point: re-running the
    audit would re-visit every page to re-ask about a handful of elements, and would compare a
    fresh capture against a report drawn from the old one.

    **It re-uses the ordinary machinery rather than a path of its own**, which is why it is
    short: the same judging work item, the same dispatch, the same closing step, the same report
    re-published, the same audit completed. Whatever it does not answer this time is filed again,
    and the report says again that the check was incomplete.

    `trigger` is injectable for the same reason it is on `dispatch_judgments` — so a test can
    dispatch without Temporal. It is the trigger CALLABLE, not a label.
    """
    unanswered = unanswered_for_capture(
        tenant_id=tenant_id, project_id=project_id, run_id=run_id)
    if not unanswered:
        return {"started": False, "asked": 0,
                "reason": "every element of this check has been looked at"}
    out = start_ai_pass(
        tenant_id=tenant_id, project_id=project_id, run_id=run_id, title=title,
        trigger=trigger, triggered_by=triggered_by, only_hashes=unanswered,
    )
    out["asked"] = len(unanswered)
    if out.get("started"):
        # (`start_ai_pass` has already stamped the new run with the capture it is judging.)
        # Back to `judging`, because that is exactly what is happening — and the running panel
        # and the audit's own row then say so in the words they already use, including how far
        # the new pass has got. It reaches `complete` again through the ordinary closing step.
        from .models import A11yBaselineAudit

        with tenant_context(tenant_id):
            # A capture key is not always a UUID — a CI post's key is whatever it chose — and an
            # id lookup on one would raise rather than simply not match.
            audit = (A11yBaselineAudit.objects.filter(id=str(run_id), tenant_id=tenant_id).first()
                     if _is_uuid(run_id) else None)
            if audit is not None:
                # The audit now points at the NEW run, not the one that gave up. Everything that
                # reads "which run is judging this" follows from here: the running panel's
                # `n of m dispatched`, and the next reading of what is still unanswered. Left
                # pointing at the old run, a second re-judge would offer up elements this pass
                # had already answered.
                summary = dict(audit.summary or {})
                summary["ai_pass"] = {**(summary.get("ai_pass") or {}),
                                      "judge_run_id": out["judge_run_id"],
                                      "dispatched": out.get("dispatched", 0),
                                      # …and the new pass's OWN filed count replaces the old
                                      # one, which the button's arithmetic adds. Carried over,
                                      # elements this pass has just answered would go on being
                                      # counted as never looked at.
                                      "filed_unjudged": out.get("filed_unjudged", 0),
                                      "rejudged": True}
                audit.summary = summary
                audit.status = A11yBaselineAudit.Status.JUDGING
                audit.save(update_fields=["summary", "status", "updated_at"])
    return out
