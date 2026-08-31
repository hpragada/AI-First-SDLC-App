"""What the accessibility judge agent reads and writes (QA-02a).

QA-02 built the whole dispatch path and left an agent-shaped hole in it: it starts a
`09c_a11y_judge` run, attaches the screen batches to the run's inputs, and waits for verdicts
to arrive through `record_verdict`. This module is the surface the agent works against —

  * `batch_for_run()`   — the elements this run must judge (what the agent reads)
  * `grounding_for()`   — the exact WCAG wording to judge them against (QA-04's text)
  * `record_finding()`  — one verdict, validated and coerced (what the agent writes)
  * `verify_judgment_completeness()` — did every dispatched element actually get judged?

**Why the agent never sees a content hash.** The batch is keyed internally by the hash of what
was judged, but the agent is handed a short `id` instead and echoes that back. Copying a
64-character hash is the most error-prone thing we could ask a model to do, and one wrong
character files a verdict against a different element — silently, and in a compliance report.

**Why the checker is not a parameter.** `record_finding` reads the checker from the batch, not
from the agent's claim. Which check an element was queued for is a platform fact; letting the
agent restate it would let a mislabelled call slip past the guard in `A11yJudgment` that stops
a checker reporting against criteria it does not own.

**Why completeness is checked at all.** We have a verified instance of an agent being told to
call a tool and simply not doing it (the ideation agent skipping `ask_human`). For a
compliance feature, quietly returning 31 verdicts for 40 elements is the *worst* available
failure — worse than returning none, because it reads as a clean pass. So every dispatched
element is accounted for: anything unjudged is stored as `uncertain` so it still reaches a
person, **and** the run fails so nobody mistakes it for a complete one (team, 2026-08-13).

**What `record_finding` accepts is checker-specific (QA-03).** Beyond the universal rules below
it applies `checkers.schema`, which asks each checker's *failures* for the one thing that makes
them actionable — the replacement alt text, the missing second colour cue, both sides of a
label mismatch. Failures only, so an `uncertain` is never stranded on a requirement it just
said it could not meet.

**Malformed calls correct themselves.** Every rejection here is a `ValueError` carrying what
was wrong and what is valid, which `RunnerStateView` returns as a 400 rather than a 500 — an
agent reading "500" concludes the platform is broken and repeats the same call, while one
reading "confidence must be between 0 and 1, got 95" fixes it on the next try. Nothing
malformed is ever stored, so the retry costs a round trip and not a corrupted report.
"""
from __future__ import annotations

from integrations.types import A11Y_VERDICTS, A11yJudgment, uncertain

from .checkers import verify_answer
from .dispatch import record_verdict

#: The catalog phase this agent runs as — the key the completeness check keys off.
JUDGE_PHASE = "a11y_judge"

#: Recorded against an element the judge never reported on, so it reaches a human rather than
#: silently disappearing from a conformance report.
NOT_JUDGED = (
    "The accessibility judge finished without reporting on this element, so nothing was "
    "judged here. It was sent for human review."
)


def _batches(tenant_id, run_id) -> list[dict]:
    """The screen batches `dispatch` attached to this run. Empty if there are none."""
    from apps.runs.models import Run
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        run = Run.objects.filter(id=run_id, tenant_id=tenant_id).first()
    if run is None:
        raise ValueError(f"no run {run_id} in this workspace")
    return list((run.inputs or {}).get("a11y_batches") or [])


def _elements(batches: list[dict]) -> dict[str, dict]:
    """Every dispatched element in the run, by the handle the agent echoes back."""
    return {
        element["id"]: {**element, "route": batch.get("route", "")}
        for batch in batches
        for element in batch.get("elements", [])
        if element.get("id")
    }


#: Statuses in which a judgment run has FINISHED, one way or another, and must not be given or
#: accept any more work.
#:
#: `STALLED` is deliberately absent, and that is the whole subtlety. A parked run is not over —
#: it is a run whose report deadline passed while the machine was still working, and the platform
#: keeps waiting on purpose so a late report still reconciles it (Bugs S.No 89). Refusing its
#: verdicts would break the exact recovery the park exists to allow, and would have thrown away
#: the last fifteen answers of the 31 August pass.
ENDED_RUN_STATUSES = ("failed", "completed", "rejected", "approved")

#: What the agent is told when it keeps working on a run that has ended. Written for a model to
#: act on, because that is who reads it: it says the work is over, that nothing was stored, and
#: what to do — stop — rather than describing a state and leaving the next move to be guessed.
RUN_HAS_ENDED = (
    "Run {run_id} has already ended ({status}), so this was not stored and there is no more "
    "work to do on it. Stop now and do not call this or any other accessibility tool for this "
    "run again — anything you report from here would be filed against a finished audit."
)


def _refuse_if_ended(tenant_id, run_id) -> None:
    """Stop an agent still working on a run the platform has finished with.

    **This is not hypothetical.** On 31 August a judgment workflow was terminated on Temporal at
    06:46:36 and reported `TERMINATED` — and verdicts went on arriving until **07:37**, one every
    five to ten seconds for forty-nine minutes, every one of them stamped with the terminated
    run's id. Nothing was wrong with the agent: it is a Claude Code process on a machine this
    server cannot see, holding a task it was given, and no tool it called ever asked whether the
    run it named was still alive. Killing the companion was the only thing that stopped it.

    So "stop" stopped the ORCHESTRATION and not the WORK, and the gap between those two is a
    hole a client-facing conformance report can be written through: verdicts landing in the
    project's judgment cache, after the audit they belong to was closed, from a run whose own
    history says it never finished.

    Applied at the three tools the AGENT calls and nowhere else. The platform's own closing path
    — `verify_judgment_completeness` filing fallbacks, `close_unfinished_ai_pass` republishing —
    runs on runs that are already terminal by design, and must go on working: it is the thing
    that accounts for what the agent did not answer. A guard that could not tell those apart
    would break the recovery that saved this audit twice.
    """
    from apps.runs.models import Run
    from apps.tenancy.context import tenant_context

    if not run_id:
        return
    with tenant_context(tenant_id):
        status = (Run.objects.filter(id=run_id, tenant_id=tenant_id)
                  .values_list("status", flat=True).first())
    if status in ENDED_RUN_STATUSES:
        raise ValueError(RUN_HAS_ENDED.format(run_id=run_id, status=status))


#: Most elements handed over in one call. A cap counted in ELEMENTS rather than characters,
#: because that is the unit the judge reasons in and the number it can check itself against —
#: but the two are only loosely related, and saying so matters: on our own reference application
#: the home page averages 553 characters per element and the terms page 914, so 25 elements is
#: ~14k characters on one screen and ~23k on another. It is a sane bound, not a guarantee.
MAX_BATCH_ELEMENTS = 25


def batch_for_run(tenant_id, run_id, start: int = 0,
                  max_elements: int = MAX_BATCH_ELEMENTS) -> dict:
    """The elements this judgment run must judge, ONE SCREEN AT A TIME (QA-02a).

    The internal `content_hash` is stripped: the agent works in `id`s, and the platform maps
    each one back when the verdict arrives.

    **Paged, and it was always meant to be.** This function's own contract said "one screen at
    a time" from the day it was written; the code returned every screen in a single dict. On the
    first live run that was 144 elements over 10 screens — 80,000 characters before the rulebook
    or a single screenshot had been added — and the judge correctly reported it could not hold
    the batch, then stopped rather than judging a part of it and calling that the whole. Ten
    screens is the SMALL case: an audit visits up to `capture.MAX_SCREENS` in a pass.

    `start` is a flat element index across the run, exactly like `get_a11y_screenshots` — the
    tool it sits beside, which has always paged this way, so the judge already knows the shape.
    One call never crosses a screen boundary: elements are grouped by screen deliberately (an
    element's meaning depends on the page around it), and a slice spanning two pages would hand
    the judge half of each. A screen with more elements than `max_elements` is split across
    calls, and `screen.offset` says where in that screen this piece begins.

    `total_elements` is the whole run's count on EVERY page, never the count of this page. It is
    the judge's contract — every dispatched element gets exactly one verdict — and a number that
    shrank to the size of the current slice would quietly redefine what "all of them" means.
    """
    _refuse_if_ended(tenant_id, run_id)
    batches = _batches(tenant_id, run_id)
    # A RESUMED run is handed what is left of itself, not the whole dispatch again (9.26.E2).
    # Empty on every ordinary run, so the normal path is byte-for-byte what it was.
    skip = already_answered_ids(tenant_id, run_id)
    screens = [
        {
            "route": batch.get("route", ""),
            "elements": [
                {key: value for key, value in element.items() if key != "content_hash"}
                for element in batch.get("elements", [])
                if element.get("id") not in skip
            ],
        }
        for batch in batches
    ]
    # A screen whose every element was already answered is dropped rather than handed over empty:
    # `next_start` walks screens, and an empty one reads to the judge as a page with nothing on it.
    screens = [screen for screen in screens if screen["elements"]]
    total = sum(len(screen["elements"]) for screen in screens)
    start = max(0, int(start or 0))
    cap = max(1, int(max_elements or MAX_BATCH_ELEMENTS))

    cursor = 0
    for index, screen in enumerate(screens):
        count = len(screen["elements"])
        if start < cursor + count:
            offset = start - cursor
            elements = screen["elements"][offset:offset + cap]
            nxt = start + len(elements)
            return {
                "screens": [{"route": screen["route"], "elements": elements}],
                "screen": {
                    "route": screen["route"],
                    "index": index + 1,
                    "of": len(screens),
                    "elements_on_screen": count,
                    "offset": offset,
                    # True when this screen is split, so the judge knows the page continues and
                    # does not read a partial screen as the whole of it.
                    "continues": offset + len(elements) < count,
                },
                "total_elements": total,
                "start": start,
                "returned": len(elements),
                "next_start": nxt if nxt < total else None,
            }
        cursor += count

    # Past the end (or nothing to judge at all): an empty page, said plainly.
    return {
        "screens": [], "screen": None, "total_elements": total,
        "start": start, "returned": 0, "next_start": None,
    }


def already_answered_ids(tenant_id, run_id) -> set[str]:
    """Element handles this run answered in an EARLIER session of ITSELF (9.26.E2).

    **Why a run can have more than one session.** A companion that dies mid-phase stops
    heartbeating; its claim goes stale after `CLAIM_LEASE`, and the next companion to poll
    **re-claims this very run** and starts the agent again. That is the recovery, and it is the
    right one — but the agent starts a fresh session at element 1 with no idea that hundreds of
    the elements in front of it already have its own verdicts. On 31 August a machine restarted
    99 elements into a 269-element pass, so the recovery was about to re-decide 99 questions whose
    answers were already in the database — 37% of a pass, spent out of the user's own Claude
    subscription, to arrive where it already was.

    **The boundary is `first_claimed_at`, and it must be, or this skips live work.** That field is
    stamped at every fresh claim and re-claim and never touched by the heartbeat, so it is exactly
    "when this session began". Filtering on *any* answer this run has given would shrink the list
    while the agent is paging through it — it asks for elements from a flat index, so a list that
    got shorter behind it would step straight over elements nobody had judged. Anchored to the
    session start, the set is fixed for as long as the session lasts.

    Only ever non-empty on a re-claim (`claim_count > 1`), so the ordinary first run of a phase
    pays one cheap read and gets an empty set.

    **Deliberately not used by `verify_judgment_completeness`.** That check must measure against
    everything this run was DISPATCHED, not against what is left of it — a contract that shrinks
    to fit what was done is not a contract.
    """
    from django.utils.dateparse import parse_datetime

    from apps.runs.models import Run
    from apps.tenancy.context import tenant_context

    from .models import A11yJudgmentCache

    with tenant_context(tenant_id):
        run = Run.objects.filter(id=run_id, tenant_id=tenant_id).first()
        if run is None:
            return set()
        dispatch = (run.inputs or {}).get("dispatch") or {}
        if int(dispatch.get("claim_count") or 0) <= 1:
            return set()
        started = parse_datetime(str(dispatch.get("first_claimed_at") or ""))
        if started is None:
            return set()
        answered = set(
            A11yJudgmentCache.objects
            .filter(tenant_id=tenant_id, run_id=run_id, updated_at__lt=started)
            .values_list("content_hash", flat=True)
        )
    if not answered:
        return set()
    return {
        element["id"]
        for element in _elements(_batches(tenant_id, run_id)).values()
        if element.get("content_hash") in answered
    }


def screenshot_pointers(tenant_id, run_id) -> tuple[list[dict], list[dict]]:
    """(images to fetch, elements with no image) for this run's batch — the judge's eyes (QA-11b).

    Returns the crop pointers in batch order, each labelled with the element's own handle so a
    picture can never be attributed to a different element, and separately the elements that
    have no picture at all. The second list is the important one: an element with no image is a
    fact the judge is told, so it records `uncertain` naming what was missing, rather than
    quietly judging from markup a question that had to be seen.
    """
    _refuse_if_ended(tenant_id, run_id)
    # Same set the batch tool serves, or the judge is shown pictures of elements it is not being
    # asked about — harmless (every image is labelled with its element's handle) and confusing,
    # and it would spend the vision budget on questions already answered.
    skip = already_answered_ids(tenant_id, run_id)
    elements = [element for element in _elements(_batches(tenant_id, run_id)).values()
                if element["id"] not in skip]
    pointers: list[dict] = []
    unseen: list[dict] = []
    for index, element in enumerate(elements):
        ref = str(element.get("screenshot_ref") or "")
        if ref:
            pointers.append({"name": element["id"], "page": index, "s3_key": ref})
        else:
            unseen.append({
                "id": element["id"],
                "checker": element.get("checker", ""),
                "reason": "no image of this element was captured — judge it from the markup, "
                          "or record `uncertain` if the question needs to be seen",
            })
    return pointers, unseen


def grounding_for(criteria) -> dict:
    """The exact WCAG 2.2 wording for the criteria an element is queued against (QA-04).

    The judge must decide against the standard's own words — and against the *defined terms*
    those words lean on, because "non-text content" and "cognitive function test" mean what
    W3C says they mean, not what they sound like. An unknown criterion is a `ValueError` so
    the agent is told which one it got wrong, rather than a `LookupError` the transport would
    surface as a platform fault.
    """
    from .wcag import UnknownCriterion, WcagNotLoaded, grounding

    numbers = [str(c).strip() for c in (criteria or []) if str(c).strip()]
    if not numbers:
        raise ValueError("name at least one WCAG criterion, e.g. criteria=['1.1.1']")
    try:
        return {"criteria": numbers, "grounding": grounding(numbers)}
    except UnknownCriterion as exc:
        raise ValueError(str(exc)) from exc
    except WcagNotLoaded as exc:                       # pragma: no cover - operator error
        raise ValueError(str(exc)) from exc


def _coerce_confidence(value) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"confidence must be a number between 0 and 1, got {value!r}") from exc
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(
            f"confidence must be between 0 and 1, got {confidence} — it is a probability, "
            f"not a percentage"
        )
    return confidence


def record_finding(*, tenant_id, run_id, element_id, criteria, verdict, confidence,
                   evidence, suggested_fix="", project_id=None) -> dict:
    """Store one verdict for one dispatched element. Rejects anything malformed.

    Coerces what is safely coercible — surrounding whitespace, verdict case, a numeric string
    for confidence — and refuses everything else with a message the agent can act on. Nothing
    partial is ever written: the judgment is fully constructed and validated before it reaches
    the database.

    Idempotent, so the retry after a rejection (or a resumed run) updates the element's row
    rather than failing on it.

    **Refused outright once the run has ended.** Checked first, before anything is validated:
    the answer is the same whatever the verdict says, and a run that is over is a fact about the
    platform rather than about this call. See `_refuse_if_ended` — a terminated run went on
    accepting verdicts for forty-nine minutes.
    """
    _refuse_if_ended(tenant_id, run_id)
    elements = _elements(_batches(tenant_id, run_id))
    if not elements:
        raise ValueError(f"run {run_id} has no accessibility elements to judge")

    handle = str(element_id or "").strip()
    element = elements.get(handle)
    if element is None:
        raise ValueError(
            f"{handle!r} is not an element in this run — use the `id` exactly as it appears "
            f"in get_a11y_batch (this run has {len(elements)})"
        )

    verdict = str(verdict or "").strip().lower()
    if verdict not in A11Y_VERDICTS:
        raise ValueError(
            f"verdict must be one of {sorted(A11Y_VERDICTS)}, got {verdict!r}")

    reported = [str(c).strip() for c in (criteria or []) if str(c).strip()]
    if not reported:
        raise ValueError(
            f"name the WCAG criteria this applies to — element {handle} was queued against "
            f"{element.get('criteria') or []}"
        )
    # Report the criteria that ACTUALLY apply, never the whole set by reflex (D-A11Y-2): a
    # real button with no readable name breaches 4.1.2 alone, and claiming 1.3.1 as well
    # would put a breach in the report that was never found.
    queued = set(element.get("criteria") or [])
    if stray := sorted(set(reported) - queued):
        raise ValueError(
            f"element {handle} was queued against {sorted(queued)}; it cannot be judged "
            f"against {stray}"
        )

    evidence = str(evidence or "").strip()
    # A verdict nobody can check is not usable: a developer cannot act on it and an auditor
    # cannot accept it. Required for a failure, and for `uncertain` — where the evidence IS
    # the reason a person is being asked. A pass may legitimately have nothing to quote.
    if verdict != "pass" and not evidence:
        raise ValueError(
            f"a {verdict!r} finding needs evidence — quote the markup, the accessible name "
            f"or what you saw that led to it"
        )

    # ...and the one further thing THIS check's failures need to be actionable (QA-03,
    # D-A11Y-5). Applies to failures only, so an `uncertain` is never stranded on a
    # requirement it just said it could not meet.
    suggested_fix = str(suggested_fix or "").strip()
    verify_answer(
        checker=element.get("checker", ""), verdict=verdict,
        evidence=evidence, suggested_fix=suggested_fix,
    )

    judgment = A11yJudgment(
        criteria=tuple(reported), verdict=verdict,
        confidence=_coerce_confidence(confidence), evidence=evidence,
        suggested_fix=suggested_fix,
        # From the batch, never the agent's claim — see the module docstring.
        checker=element.get("checker", ""),
    )
    record_verdict(
        tenant_id=tenant_id, project_id=project_id or _project_for(tenant_id, run_id),
        run_id=run_id, content_hash=element["content_hash"], judgment=judgment,
    )
    return {
        "element_id": handle, "checker": judgment.checker,
        "criteria": list(judgment.criteria), "verdict": judgment.verdict,
        "recorded": True,
    }


def _project_for(tenant_id, run_id):
    """The run's own project. Taken from the run rather than the agent, so a verdict can never
    be filed against a project the run does not belong to."""
    from apps.runs.models import Run
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        run = Run.objects.filter(id=run_id, tenant_id=tenant_id).first()
        if run is None:
            raise ValueError(f"no run {run_id} in this workspace")
        return run.work_item.project_id


#: Where a judgment run records the elements NOTHING ever looked at.
UNANSWERED_KEY = "a11y_unanswered"


def _remember_unanswered(tenant_id, run_id, content_hashes: list[str]) -> None:
    """Record, on the run itself, which elements it never reported on.

    **Why this has to be written down at all.** The moment the fallback verdicts above are
    stored, the two kinds of `uncertain` become indistinguishable: *"a check looked at this and
    could not decide"* and *"nothing ever looked at this"* are the same row — same verdict, same
    confidence of 0.0, same run, same prompt version. Only the difference between the dispatched
    set and the judged set tells them apart, and that difference exists for exactly as long as
    this function is running.

    It matters because they deserve opposite treatment. An answered `uncertain` belongs to a
    person and must never be handed back to the machine for another go. An element nothing looked
    at is not a judgement at all — it is work that did not happen, and asking again is the right
    response to it. `aipass.rejudge_capture` is what asks, and this is what it reads.

    Written to `Run.outputs`, which is a JSON field the run already owns, so no schema change and
    no second place to keep in step. Merged rather than replaced: the run's own outputs (the
    error a failed run records, for one) must survive this.

    **The LIST is unioned too, and that is not tidiness (9.26.G).** The closing path is not called
    once — on 31 August it ran three times over one run, and the attempts overlapped: verdicts
    were still being filed while a later attempt was already counting what was still missing. So
    the later attempt saw a SMALLER set (an earlier one had just filed the difference) and its
    shorter list replaced the true one — 170 elements recorded as never-looked-at became 65, and
    105 of them silently changed meaning from *work that did not happen* to *somebody's job in
    the review queue*. That is the exact distinction this function exists to preserve, destroyed
    by this function.
    A later, shorter reading is never a correction: an element that was never looked at does not
    stop having been never looked at because a subsequent pass found it already filed. Anything
    that IS answered later drops out where it should — `aipass.unanswered_for_capture` removes
    every hash that has since been decided, so a union here cannot re-offer settled work.
    """
    if not content_hashes:
        return
    from apps.runs.models import Run
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        run = Run.objects.filter(id=run_id, tenant_id=tenant_id).first()
        if run is None:
            return
        known = set((run.outputs or {}).get(UNANSWERED_KEY) or [])
        run.outputs = {**(run.outputs or {}),
                       UNANSWERED_KEY: sorted(known | set(content_hashes))}
        run.save(update_fields=["outputs", "updated_at"])


def verify_judgment_completeness(*, tenant_id, project_id=None, run_id) -> dict:
    """Every dispatched element must have been judged. Records the gaps, then fails.

    Two things happen to an element the judge never reported on, and both are needed:

      * it is stored as `uncertain` with a reason, so it still reaches a person — nothing
        dispatched may vanish from a conformance report;
      * the run fails, so a partial pass is never read as a complete one.

    Returns the counts when the run is complete.
    """
    from apps.a11y.models import A11yJudgmentCache
    from apps.tenancy.context import tenant_context

    elements = _elements(_batches(tenant_id, run_id))
    if not elements:
        # Not a judgment run at all (or nothing needed judging) — nothing to verify.
        return {"dispatched": 0, "judged": 0, "unjudged": []}

    project_id = project_id or _project_for(tenant_id, run_id)
    with tenant_context(tenant_id):
        judged = set(
            A11yJudgmentCache.objects
            .filter(tenant_id=tenant_id, project_id=project_id, run_id=run_id)
            .values_list("content_hash", flat=True)
        )

    missing = [element for element in elements.values()
               if element["content_hash"] not in judged]
    for element in missing:
        record_verdict(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id,
            content_hash=element["content_hash"],
            judgment=uncertain(tuple(element.get("criteria") or ()),
                               checker=element.get("checker", ""), reason=NOT_JUDGED),
        )

    _remember_unanswered(tenant_id, run_id, [e["content_hash"] for e in missing])

    unjudged: list[str] = sorted(element["id"] for element in missing)
    counts: dict = {
        "dispatched": len(elements),
        "judged": len(elements) - len(missing),
        "unjudged": unjudged,
    }
    if missing:
        from orchestration.activities import WriteCompletenessError

        named = ", ".join(unjudged[:8]) + (", …" if len(missing) > 8 else "")
        raise WriteCompletenessError(
            f"run {run_id} judged {counts['judged']} of {counts['dispatched']} accessibility "
            f"element(s) — {len(missing)} were never reported on ({named}). They have been "
            f"sent for human review, and this run is not reported as a complete "
            f"accessibility check."
        )
    return counts
