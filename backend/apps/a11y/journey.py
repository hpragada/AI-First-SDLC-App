"""Walking a journey with a keyboard, and recording only what was actually walked (QA-20).

The element checks judge a page that is standing still. These eight judge what happens *while
somebody uses the application* — whether tabbing ever traps you, whether focus stays visible and
unobscured, whether anything changes under you when an element takes focus or a field is typed
in, whether a status message is announced at all. None of that is in a captured page, which is
why this is the one check whose input is a journey and whose work happens in a live browser.

**Everything here exists to keep three states apart**, because collapsing any two of them is how
an untested journey comes back looking clean:

    walked + judged     → a real result about a real step
    walked + blocked    → the agent got here and could not go on, and said why
    never reported      → the agent never mentioned this step at all

The third is the dangerous one and it is not something the agent can be trusted to report: an
agent that stopped early is, by definition, not still running to tell you it stopped. So the
step list is **frozen at the start** and the platform subtracts at the end — the same rule and
the same reason as QA-17's route reconciliation (D-A11Y-50).

**Resolution is deliberately narrow, and this is the D-A11Y-49 lesson applied a second time.**
`findings.record_run_findings` closes findings *by absence* across the routes a run covered. If
a journey pass went through that path it would close every static finding on the routes it
walked — a keyboard walk of `/checkout` would silently mark the missing alt text there as fixed,
because a keyboard walk has nothing to say about alt text and absence would be read as a clean
bill. So journey passes never call it. `_resolve_walked` closes only rows that carry **one of this
module's own checkers AND sit on a route this pass actually walked AND come from a source this
module can produce**, and each of those three conditions has a test in both directions.

**And the same mistake was live in the opposite direction (QA-21, D-A11Y-79).** These checks are
never in a static run's report — a captured page cannot answer "does tabbing ever reach this
region" — so `record_run_findings` was closing every keyboard finding on every screen a scan
covered. That was the more dangerous direction of the two, because a static run happens far more
often than a journey does. Coverage is by screen *and* by kind; the fix lives in `findings.py`.
"""
from __future__ import annotations

from apps.tenancy.context import tenant_context
from integrations.types import (
    A11Y_JOURNEY_CRITERIA,
    A11Y_STEP_BLOCKED,
    A11Y_STEP_NOT_REACHED,
    A11Y_STEP_OUTCOMES,
    A11Y_STEP_WALKED,
    A11yCandidate,
    A11yJudgment,
)

from .findings import fingerprint, levels_for, severity_for
from .selectors import is_positional

#: The agent that operates the app. Platform-native like 09c — the legacy suite had no
#: interaction testing of any kind, so there is no v6 body to migrate.
JOURNEY_AGENT_KEY = "09d_a11y_journey"

#: Every reason this check can be unavailable, said in words a person can act on. Same
#: discipline as `dispatch.NO_JUDGE_AGENT` (D-A11Y-3): an unavailable check is reported, never
#: quietly skipped, because a skipped check and a passed check look identical in a report.
NO_JOURNEY_AGENT = (
    "no `{key}` agent is registered for this workspace, so no journey can be keyboard-tested. "
    "Seed the agent catalog for this tenant."
)
NO_COMPANION = (
    "there is no connected companion to run the journey on. The application under test runs on "
    "a machine the platform cannot reach, so the walk happens there or not at all."
)
NO_JOURNEY = (
    "this project has no walkable journey. A journey is a test case the testing phase wrote "
    "with `Type: E2E` and readable steps; run the testing phase, or check that its E2E cases "
    "have a Test Steps section."
)
DISPATCH_FAILED = "the journey run could not be started ({detail}), so nothing was walked."

#: A blocked step must say what blocked it. Recorded rather than rejected when the agent leaves
#: it out — refusing the call would lose the fact that the step was blocked at all, which is the
#: more valuable half.
NO_REASON_GIVEN = "the agent reported this step as blocked without saying what blocked it"

#: Why a check has no stored answer, in the two opposite cases `stored_journey_judgments`
#: must not confuse. Both are `uncertain`, never `pass`.
NOT_ASKED = (
    "no step of this journey was walked, so this check was never asked. It has not passed."
)
NOTHING_TO_REPORT = (
    "the last pass walked this journey and recorded nothing for this check — either it found "
    "no problem, or the check did not apply to any step it reached. Read the pass's step "
    "accounting to tell which."
)


class JourneyRunError(ValueError):
    """Asked to record against a journey run that does not exist, or with an invalid value."""


def _journey_run(tenant_id, run_id):
    from .models import A11yJourneyRun

    with tenant_context(tenant_id):
        row = A11yJourneyRun.objects.filter(tenant_id=tenant_id, run_id=run_id).first()
    if row is None:
        raise JourneyRunError(
            f"no accessibility journey is attached to run {run_id} — this run was not started "
            "by `start_journey_check`, so there is nothing to report against."
        )
    return row


def journey_available(tenant_id, project_id, triggered_by=None) -> str:
    """"" if a journey can be walked, else the sentence saying why it cannot."""
    from apps.registry.models import AgentSpec
    from orchestration.trigger import _resolve_enrollment

    with tenant_context(tenant_id):
        if not AgentSpec.objects.filter(tenant_id=tenant_id, key=JOURNEY_AGENT_KEY).exists():
            return NO_JOURNEY_AGENT.format(key=JOURNEY_AGENT_KEY)
        if _resolve_enrollment(tenant_id, project_id, triggered_by) is None:
            return NO_COMPANION
    return ""


def start_journey_check(*, tenant_id, project_id, work_item_id, test_ref=None,
                        triggered_by=None, trigger=None, object_store=None) -> dict:
    """Freeze a journey's steps and dispatch one agent run to walk it.

    Never raises at the caller. Every way this can fail — no journey, no agent, no companion,
    a refused trigger — comes back as `{"started": False, "reason": ...}`, because the caller
    is a run that has other work to finish and an accessibility check that could not start is
    a thing to report, not an exception to throw.
    """
    from .journeys import JourneyError, journey_for, journeys_for_project
    from .models import A11yJourneyRun

    try:
        if test_ref:
            journey = journey_for(tenant_id, project_id, test_ref, object_store=object_store)
            found: dict = {"skipped": [], "over_cap": []}
        else:
            found = journeys_for_project(tenant_id, project_id, object_store=object_store)
            if not found["journeys"]:
                return {"started": False, "reason": NO_JOURNEY,
                        "skipped": found["skipped"], "over_cap": found["over_cap"]}
            journey = found["journeys"][0]
    except JourneyError as exc:
        return {"started": False, "reason": str(exc), "skipped": [], "over_cap": []}

    unavailable = journey_available(tenant_id, project_id, triggered_by)
    if unavailable:
        return {"started": False, "reason": unavailable, "test_ref": journey.test_ref,
                "skipped": found.get("skipped", []), "over_cap": found.get("over_cap", [])}

    if trigger is None:
        from orchestration.trigger import trigger_phase as trigger
    try:
        outcome = trigger(
            tenant_id=tenant_id, project_id=project_id, work_item_id=work_item_id,
            agent_key=JOURNEY_AGENT_KEY, triggered_by=triggered_by,
            execution_mode="companion", auto_approve=True,
        )
    except Exception as exc:  # noqa: BLE001 — a refusal to start is a reason, never a crash
        return {"started": False, "reason": DISPATCH_FAILED.format(detail=exc),
                "test_ref": journey.test_ref, "skipped": found.get("skipped", []),
                "over_cap": found.get("over_cap", [])}

    steps = [{"number": s.number, "text": s.text, "route": s.route} for s in journey.steps]
    with tenant_context(tenant_id):
        row = A11yJourneyRun.objects.create(
            tenant_id=tenant_id, project_id=project_id, run_id=outcome.run_id,
            test_ref=journey.test_ref, title=journey.title[:512],
            artifact_id=journey.artifact_id, steps=steps,
            preconditions=list(journey.preconditions),
            started_by_id=triggered_by or None,
            status=A11yJourneyRun.Status.WALKING,
        )
    return {"started": True, "run_id": outcome.run_id, "journey_run_id": str(row.id),
            "test_ref": journey.test_ref, "steps": len(steps),
            "skipped": found.get("skipped", []), "over_cap": found.get("over_cap", [])}


def journey_for_run(tenant_id, run_id) -> dict:
    """What this run must walk — the agent's contract, read once at the start.

    `total_steps` is stated explicitly for the same reason `get_a11y_batch` states
    `total_elements`: it is the number the agent checks itself against before finishing, and
    an agent that cannot see the size of its own job will stop when the answers start looking
    similar.
    """
    row = _journey_run(tenant_id, run_id)
    return {
        "journey_run_id": str(row.id),
        "test_ref": row.test_ref,
        "title": row.title,
        "artifact_id": row.artifact_id,
        "preconditions": list(row.preconditions or []),
        "steps": list(row.steps or []),
        "total_steps": len(row.steps or []),
        "checks": {checker: list(criteria)
                   for checker, criteria in A11Y_JOURNEY_CRITERIA.items()},
    }


def _step_text(row, number: int) -> tuple[str, str]:
    for step in row.steps or []:
        if int(step.get("number", 0)) == int(number):
            return str(step.get("text", "")), str(step.get("route", ""))
    return "", ""


def record_step(*, tenant_id, run_id, number, outcome, reason="") -> dict:
    """Record what became of one step. `walked` or `blocked` — never `not_reached`.

    `not_reached` is the platform's own answer for a step nobody spoke about, written by
    `finish_journey`. Letting an agent claim it would let a run assert that it did not do
    something, which is exactly the claim that cannot be trusted from a run that stopped.
    """
    from .models import A11yJourneyStepResult

    row = _journey_run(tenant_id, run_id)
    outcome = str(outcome or "").strip().lower()
    if outcome not in (A11Y_STEP_WALKED, A11Y_STEP_BLOCKED):
        raise JourneyRunError(
            f"step outcome must be {A11Y_STEP_WALKED!r} or {A11Y_STEP_BLOCKED!r}, got "
            f"{outcome!r} — `{A11Y_STEP_NOT_REACHED}` is written by the platform for steps "
            "nothing was reported about, and cannot be claimed."
        )
    try:
        number = int(number)
    except (TypeError, ValueError) as exc:
        raise JourneyRunError(f"step number must be a whole number, got {number!r}") from exc

    text, route = _step_text(row, number)
    if not text:
        known = ", ".join(str(s.get("number")) for s in row.steps or []) or "none"
        raise JourneyRunError(
            f"this journey has no step {number} — its steps are {known}. Report against the "
            "numbers `get_a11y_journey` gave you, not the numbering in the test case body."
        )
    reason = str(reason or "").strip()[:2000]
    if outcome == A11Y_STEP_BLOCKED and not reason:
        reason = NO_REASON_GIVEN
    with tenant_context(tenant_id):
        result, _ = A11yJourneyStepResult.objects.update_or_create(
            tenant_id=tenant_id, journey_run=row, number=number,
            defaults={"project_id": row.project_id, "text": text[:2000], "route": route[:512],
                      "outcome": outcome, "reason": reason},
        )
    return {"step": number, "outcome": result.outcome, "reason": result.reason}


def _mark_walked(tenant_id, row, number: int) -> None:
    """A step that produced a judgment was, by definition, reached. Recorded here so an agent
    that reports findings but forgets the step outcome does not leave a walked step looking
    like one nobody reached — and never downgraded: a step already recorded as `blocked` stays
    blocked, because "I got here, saw this, then hit a wall" is one step, not two."""
    from .models import A11yJourneyStepResult

    text, route = _step_text(row, number)
    with tenant_context(tenant_id):
        A11yJourneyStepResult.objects.get_or_create(
            tenant_id=tenant_id, journey_run=row, number=number,
            defaults={"project_id": row.project_id, "text": text[:2000], "route": route[:512],
                      "outcome": A11Y_STEP_WALKED, "reason": ""},
        )


def record_journey_finding(*, tenant_id, run_id, step, checker, verdict, confidence, evidence,
                           criteria=None, suggested_fix="", route="", selector="",
                           measurement=None) -> dict:
    """One check's answer about one step, triaged and written to the ledger.

    Validation is `A11yJudgment`'s, unchanged and deliberately: a journey judgment naming a
    criterion its checker does not own would corrupt the conformance report exactly as an
    element judgment would, and the report cannot tell which half of the system produced it.

    **`measurement` closes D-A11Y-72 (QA-21).** Two of the eight criteria have a deterministic
    half — 2.4.7's suppressed outline and 4.1.3's absent live region — and the agent reads them
    with a prescribed probe while it has the element focused, which is the only moment they are
    true. `journey_rules` decides what the reading means; nothing here interprets it, and a
    reading that proves nothing leaves the agent's verdict exactly as it was. See that module
    for why the reading being the agent's does not make the ruling the agent's.

    A measurement that overrules the agent makes the row a **`rule`** finding rather than an
    agentic one, mirroring `report._row_from_triage` — a reader deciding whether to trust a
    finding needs to know it was measured, and the AI's agreement does not make it an AI
    finding. It also means the project's confidence dial no longer applies to it (`policy.blocks`
    exempts measurements), which is the correct consequence and not a side effect.
    """
    from .journey_rules import rule_failures_for
    from .models import A11yFinding
    from .triage import TRIAGE_FAILURE, TRIAGE_REVIEW, thresholds_for, triage

    row = _journey_run(tenant_id, run_id)
    checker = str(checker or "").strip()
    if checker not in A11Y_JOURNEY_CRITERIA:
        raise JourneyRunError(
            f"{checker!r} is not a journey check — the checks are "
            f"{', '.join(sorted(A11Y_JOURNEY_CRITERIA))}"
        )
    try:
        step = int(step)
    except (TypeError, ValueError) as exc:
        raise JourneyRunError(f"step must be a whole number, got {step!r}") from exc
    text, step_route = _step_text(row, step)
    if not text:
        raise JourneyRunError(f"this journey has no step {step}")

    try:
        judgment = A11yJudgment(
            criteria=tuple(criteria or A11Y_JOURNEY_CRITERIA[checker]),
            verdict=str(verdict or "").strip().lower(),
            confidence=float(confidence),
            evidence=str(evidence or ""),
            suggested_fix=str(suggested_fix or ""),
            checker=checker,
        )
    except (TypeError, ValueError) as exc:
        raise JourneyRunError(str(exc)) from exc

    route = (str(route or "").strip() or step_route)[:512]
    # A journey finding is about the step when it names no element — "focus order on this
    # screen" has no single element to point at. The step handle keeps the fingerprint stable
    # across runs of the same journey, which is what lets a fixed problem resolve.
    selector = (str(selector or "").strip() or f"step:{step}")[:512]

    proven = rule_failures_for(checker=checker, route=route, selector=selector,
                               measurement=measurement)
    triaged = triage(judgment, A11yCandidate(selector=selector, route=route),
                     rule_failures=proven, thresholds=thresholds_for(tenant_id))
    _mark_walked(tenant_id, row, step)

    if triaged.outcome not in (TRIAGE_FAILURE, TRIAGE_REVIEW):
        # A confident pass is not a finding — its absence next run is how a fix is recognised.
        return {"step": step, "checker": checker, "outcome": triaged.outcome,
                "recorded": False, "reason": triaged.reason, "measured": False}

    criterion = judgment.criterion
    level = levels_for(judgment.criteria).get(criterion, "")
    # The fingerprint keeps the checker whatever the source becomes. It is the *identity* of the
    # problem, and "the focus indicator on this element" is one problem whether the measurement
    # or the agent settled it this time — a key that moved when a probe happened to run would
    # give one problem two rows and two tickets across consecutive runs.
    key = fingerprint(route=route, selector=selector, criterion=criterion, checker=checker)
    proof = triaged.rule_failure
    measured = proof is not None
    with tenant_context(tenant_id):
        finding, created = A11yFinding.objects.update_or_create(
            tenant_id=tenant_id, project_id=row.project_id, fingerprint=key,
            defaults={
                "route": route, "selector": selector,
                "stable": not is_positional(selector, route),
                "criterion": criterion, "criteria": list(judgment.criteria),
                "wcag_level": level, "checker": checker,
                "source": (A11yFinding.Source.RULE if proof is not None
                           else A11yFinding.Source.AGENTIC),
                "verdict": judgment.verdict, "outcome": triaged.outcome,
                # A measurement has no confidence to doubt, and storing the agent's alongside it
                # would invite a reader to discount a proven failure by how unsure the AI was.
                "confidence": None if proof is not None else judgment.confidence,
                "severity": severity_for(level),
                "rule_id": proof.rule_id if proof is not None else "",
                "evidence": (proof.evidence if proof is not None else judgment.evidence),
                "suggested_fix": judgment.suggested_fix,
                "last_seen_run_id": run_id,
                "status": A11yFinding.Status.OPEN,
            },
        )
        if created:
            finding.first_seen_run_id = run_id
            finding.save(update_fields=["first_seen_run", "updated_at"])
    return {"step": step, "checker": checker, "outcome": triaged.outcome, "recorded": True,
            "finding_id": str(finding.id), "opened": created, "reason": triaged.reason,
            "measured": measured}


def _reconcile_steps(tenant_id, row) -> dict:
    """Write a `not_reached` row for every frozen step nothing was reported about.

    This is the subtraction QA-17 taught: a step that reports nothing is indistinguishable from
    a step that was fine, unless the list was frozen first and the difference is written down.
    """
    from .models import A11yJourneyStepResult

    with tenant_context(tenant_id):
        reported = {r.number: r for r in A11yJourneyStepResult.objects.filter(
            tenant_id=tenant_id, journey_run=row)}
        missing = []
        for step in row.steps or []:
            number = int(step.get("number", 0))
            if number in reported:
                continue
            A11yJourneyStepResult.objects.create(
                tenant_id=tenant_id, project_id=row.project_id, journey_run=row,
                number=number, text=str(step.get("text", ""))[:2000],
                route=str(step.get("route", ""))[:512],
                outcome=A11Y_STEP_NOT_REACHED,
                reason="the agent never reported on this step, so it was not tested",
            )
            missing.append(number)
        walked = sorted(n for n, r in reported.items() if r.outcome == A11Y_STEP_WALKED)
        blocked = [{"step": n, "reason": r.reason}
                   for n, r in sorted(reported.items()) if r.outcome == A11Y_STEP_BLOCKED]
    return {"walked": walked, "blocked": blocked, "not_reached": sorted(missing)}


def _resolve_walked(tenant_id, row, walked_routes: set[str], seen: set[str]) -> list[str]:
    """Close journey findings on routes this pass walked and did not report again.

    Three conditions, every one of them load-bearing — see the module docstring:
      * the source is one **this module can produce** — agentic, or `rule` where a measurement
        overrode the agent (QA-21). A keyboard walk still has nothing to say about alt text, so
        it may never close a finding the element checks or a page scan made.
      * `checker in A11Y_JOURNEY_CRITERIA` — and nothing else, so a future agentic check of a
        different shape does not inherit this resolution by accident. This is the condition
        actually doing the narrowing: a scanner row has no checker at all, so widening the
        source above cannot reach one.
      * the route was **walked** — not blocked, not unreached. A route the agent never got to
        is not a route it found clean.
    """
    from .models import A11yFinding

    if not walked_routes:
        return []
    resolved = []
    with tenant_context(tenant_id):
        stale = A11yFinding.objects.filter(
            tenant_id=tenant_id, project_id=row.project_id,
            status=A11yFinding.Status.OPEN,
            source__in=[A11yFinding.Source.AGENTIC, A11yFinding.Source.RULE],
            checker__in=sorted(A11Y_JOURNEY_CRITERIA),
            route__in=sorted(walked_routes),
        ).exclude(fingerprint__in=sorted(seen) or [""])
        for finding in stale:
            finding.status = A11yFinding.Status.RESOLVED
            finding.last_seen_run_id = row.run_id
            finding.save(update_fields=["status", "last_seen_run", "updated_at"])
            resolved.append(str(finding.id))
    return resolved


def finish_journey(*, tenant_id, run_id) -> dict:
    """Account for every step, close what was fixed, and say what was never tested.

    The summary is the pass's own honesty check. "We keyboard-tested the checkout journey" is
    not a claim anyone should have to take on trust, so the numbers that would falsify it —
    how many steps were asked for, how many were walked, how many were blocked and by what,
    how many were never reached — are recorded next to the result.
    """
    from .models import A11yFinding, A11yJourneyRun

    row = _journey_run(tenant_id, run_id)
    steps = _reconcile_steps(tenant_id, row)

    with tenant_context(tenant_id):
        walked_routes = {
            r.route for r in row.step_results.filter(outcome=A11Y_STEP_WALKED) if r.route
        }
        # Both sources, and it must be both: a finding this very pass recorded as `rule`
        # because a measurement overrode the agent (QA-21) would otherwise be absent from
        # `seen`, and `_resolve_walked` would close it as fixed the moment it was found.
        seen = set(
            A11yFinding.objects.filter(
                tenant_id=tenant_id, project_id=row.project_id,
                source__in=[A11yFinding.Source.AGENTIC, A11yFinding.Source.RULE],
                checker__in=sorted(A11Y_JOURNEY_CRITERIA), last_seen_run_id=run_id,
            ).values_list("fingerprint", flat=True)
        )
    resolved = _resolve_walked(tenant_id, row, walked_routes, seen)

    asked = len(row.steps or [])
    summary = {
        "asked": asked,
        "walked": len(steps["walked"]),
        "blocked": steps["blocked"],
        "not_reached": steps["not_reached"],
        "findings": len(seen),
        "resolved": resolved,
        "checks": sorted(A11Y_JOURNEY_CRITERIA),
    }
    # A pass that walked nothing has nothing to report on — and must not be recorded as a
    # journey that came back clean. Same rule as `finish_baseline_audit` on an empty capture.
    complete = bool(steps["walked"])
    if not complete:
        summary["reason"] = (
            "not one step of this journey could be walked, so nothing was tested. Check that "
            "the application was running and reachable from the machine that ran the journey, "
            "and that the journey's preconditions (test accounts, seeded data) hold."
        )
    # QA-21: what the agent found becomes a real ticket, in the same loop as everything else.
    #
    # **Only when something was walked.** The loopback reconciles the whole project ledger, so
    # calling it after a journey that walked nothing would open tickets from other runs'
    # findings and hang them off a journey that tested nothing — the same rule as the `reason`
    # above, one line further on.
    #
    # Wrapped exactly as `aipass._publish` wraps it, and for the same trade: a loopback that
    # fell over is not a reason to lose the journey result, which is the more expensive half
    # (a real browser walked a real application to produce it). The error is returned rather
    # than swallowed, and it is stored on the run so it is still there tomorrow.
    if complete:
        from .defects import record_a11y_findings
        try:
            loop = record_a11y_findings(
                tenant_id=tenant_id, project_id=row.project_id, run_id=run_id)
            # The ticket ids only. The loopback also hands back the policy it applied and the
            # whole blocking set, which belong to the report that asked for them — copying them
            # onto every journey run would store the same policy over and over.
            summary["defects"] = {key: loop[key] for key in ("opened", "closed", "reopened")}
        except Exception as exc:  # noqa: BLE001 — see above
            summary["defects"] = {"error": str(exc)}

    with tenant_context(tenant_id):
        row.status = (A11yJourneyRun.Status.COMPLETE if complete
                      else A11yJourneyRun.Status.FAILED)
        row.summary = summary
        row.save(update_fields=["status", "summary", "updated_at"])
    return {"journey_run_id": str(row.id), "test_ref": row.test_ref,
            "status": row.status, **summary}


def verify_journey_completeness(*, tenant_id, run_id) -> dict:
    """Did this run answer for every step it was given? The coverage check `09d`'s completeness
    verification reads, mirroring `judge.verify_judgment_completeness` for the element path."""
    row = _journey_run(tenant_id, run_id)
    with tenant_context(tenant_id):
        reported = set(row.step_results.exclude(outcome=A11Y_STEP_NOT_REACHED)
                       .values_list("number", flat=True))
    asked = {int(s.get("number", 0)) for s in row.steps or []}
    missing = sorted(asked - reported)
    return {"asked": len(asked), "reported": len(reported & asked), "missing": missing,
            "complete": not missing}


#: Outcomes a step may carry, re-exported so a caller does not import from two modules to read
#: one row. Names live in `integrations.types` because the companion-facing contract needs them.
STEP_OUTCOMES = A11Y_STEP_OUTCOMES


def stored_journey_judgments(*, tenant_id, journey, project_id=None) -> list[A11yJudgment]:
    """What the last pass over this journey found, as capability-shaped judgments.

    The read half of `A11yAI.check_journey` (D-A11Y-4): it answers from the most recent pass
    and never starts one. Findings are stored per (step, check); a caller asking about the
    journey wants one answer per check, so the **worst** outcome per check wins — a trap found
    at step 3 is a trap in this journey, and averaging it away with two clean steps would hide
    the only thing worth reporting.

    A check with no row for it comes back `uncertain`, not `pass`. There are two reasons a
    check has no row and they are opposite: it passed confidently (a pass is stored as no
    finding), or it was never asked because its step was blocked. This function cannot tell
    them apart from findings alone, and guessing "pass" would turn a step nobody reached into
    a clean bill of health — so it defers to the pass's own step accounting instead.
    """
    from integrations.types import uncertain

    from .models import A11yFinding, A11yJourneyRun

    with tenant_context(tenant_id):
        runs = A11yJourneyRun.objects.filter(tenant_id=tenant_id)
        if project_id:
            runs = runs.filter(project_id=project_id)
        if journey.test_ref:
            runs = runs.filter(test_ref=journey.test_ref)
        last = runs.order_by("-created_at").first()
        if last is None:
            return []
        walked = set(
            last.step_results.filter(outcome=A11Y_STEP_WALKED).values_list("number", flat=True)
        )
        rows = list(A11yFinding.objects.filter(
            tenant_id=tenant_id, project_id=last.project_id,
            source=A11yFinding.Source.AGENTIC, last_seen_run_id=last.run_id,
            checker__in=sorted(A11Y_JOURNEY_CRITERIA),
        ))

    # Worst-first, so the first row seen per check is the one that decides it.
    rank = {"fail": 0, "uncertain": 1, "pass": 2}
    rows.sort(key=lambda r: (rank.get(r.verdict, 3), -(r.confidence or 0.0)))
    worst: dict[str, A11yFinding] = {}
    for row in rows:
        worst.setdefault(row.checker, row)

    out: list[A11yJudgment] = []
    for checker, criteria in A11Y_JOURNEY_CRITERIA.items():
        found_row = worst.get(checker)
        if found_row is not None:
            out.append(A11yJudgment(
                criteria=tuple(found_row.criteria or criteria), verdict=found_row.verdict,
                confidence=found_row.confidence or 0.0, evidence=found_row.evidence,
                suggested_fix=found_row.suggested_fix, checker=checker,
            ))
            continue
        reason = (NOT_ASKED if not walked else NOTHING_TO_REPORT)
        out.append(uncertain(criteria, checker=checker, reason=reason))
    return out
