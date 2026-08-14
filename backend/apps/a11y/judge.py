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


def batch_for_run(tenant_id, run_id) -> dict:
    """The elements this judgment run must judge, as the agent sees them.

    The internal `content_hash` is stripped: the agent works in `id`s, and the platform maps
    each one back when the verdict arrives.
    """
    batches = _batches(tenant_id, run_id)
    screens = [
        {
            "route": batch.get("route", ""),
            "elements": [
                {key: value for key, value in element.items() if key != "content_hash"}
                for element in batch.get("elements", [])
            ],
        }
        for batch in batches
    ]
    return {
        "screens": screens,
        "total_elements": sum(len(screen["elements"]) for screen in screens),
    }


def screenshot_pointers(tenant_id, run_id) -> tuple[list[dict], list[dict]]:
    """(images to fetch, elements with no image) for this run's batch — the judge's eyes (QA-11b).

    Returns the crop pointers in batch order, each labelled with the element's own handle so a
    picture can never be attributed to a different element, and separately the elements that
    have no picture at all. The second list is the important one: an element with no image is a
    fact the judge is told, so it records `uncertain` naming what was missing, rather than
    quietly judging from markup a question that had to be seen.
    """
    elements = list(_elements(_batches(tenant_id, run_id)).values())
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
    """
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
