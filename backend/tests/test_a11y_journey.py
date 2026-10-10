"""QA-20 — keyboard- and interaction-testing a journey.

Against the task's acceptance criteria:

  AC1  a critical journey produces pass/fail per criterion with a confidence
  AC2  a page with a keyboard trap reports `fail` on 2.1.2
  AC3  a status message that never announces reports `fail` on 4.1.3
  AC4  an unreachable step reports "could not test" — never a pass, never a fail
  AC5  a journey with a planted keyboard trap is covered end to end

**The two sharpest things in this file** are both about absence, and both are lessons this
build has already paid for once:

  * `test_a_journey_pass_never_resolves_a_static_finding` — `findings.record_run_findings`
    closes findings by ABSENCE across a run's routes. A keyboard walk of `/checkout` has
    nothing whatsoever to say about the missing alt text there, so if a journey pass went
    through that path it would mark it fixed. This is D-A11Y-49 in a new place, and the test
    asserts it in both directions: the static finding survives, the agentic one resolves.

  * `test_a_step_the_agent_never_mentioned_is_recorded_as_not_reached` — a step nobody spoke
    about is not a clean step. The platform freezes the list and subtracts, because an agent
    that stopped early cannot be relied on to report that it stopped (D-A11Y-50's rule, applied
    to steps instead of routes).
"""
from __future__ import annotations

import pytest

from apps.a11y.journey import (
    JOURNEY_AGENT_KEY,
    JOURNEY_PHASE,
    NO_ADDRESS,
    NO_COMPANION,
    NO_JOURNEY,
    JourneyRunError,
    close_unfinished_journey,
    finish_journey,
    journey_for_run,
    record_journey_finding,
    record_step,
    start_journey_check,
    verify_journey_completeness,
)
from apps.a11y.journeys import (
    JourneyError,
    declared_type,
    is_journey,
    journey_for,
    journeys_for_project,
    parse_preconditions,
    parse_steps,
)
from apps.a11y.models import A11yFinding, A11yJourneyRun, A11yJourneyStepResult
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from integrations.types import (
    A11Y_ALL_CHECKER_CRITERIA,
    A11Y_CHECKER_CRITERIA,
    A11Y_HELD_BACK_CRITERIA,
    A11Y_JOURNEY_CRITERIA,
    A11Y_STEP_BLOCKED,
    A11Y_STEP_NOT_REACHED,
    A11Y_STEP_WALKED,
)

# ── a realistic journey, in agent 09's own test-case format ──────────────────

#: Where the application under test is answering for these walks. A journey now refuses to start
#: without one (G6a), so it is part of the fixture rather than an argument each test invents.
APP_URL = "http://127.0.0.1:5173"

JOURNEY_BODY = """## TC-031: Complete Registration to First Expense
**User Story:** US-004
**Type:** E2E
**Priority:** Critical

### Preconditions
- No account exists for tc031@test.com
- The seed database is empty

### Test Steps
1. Navigate to /register and create an account
2. Log in and open /dashboard
3. Add an expense of 12.50 from /expenses/new
4. Confirm the expense appears on /dashboard

### Expected Result
1. The dashboard lists the new expense

### Test Data
- Input: email tc031@test.com
"""

FUNCTIONAL_BODY = """## TC-002: Registration Rejects Duplicate Email
**Type:** Functional

### Test Steps
1. Submit the form with an existing email
2. Read the error
"""


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="SpendLog")
    AgentSpec.objects.create(tenant=tenant, key=JOURNEY_AGENT_KEY, semver="1.0.0")
    # A journey pass hangs off a work item like any other agent run — `runs_run.work_item_id`
    # is NOT NULL, so a fixture without one tests a shape production never produces.
    item = WorkItem.objects.create(tenant=tenant, project=project, type=WorkItem.Type.STORY,
                                   title="Log an expense")
    return {"t": str(tenant.id), "p": str(project.id), "w": str(item.id),
            "tenant": tenant, "project": project, "item": item}


class _Outcome:
    def __init__(self, run_id):
        self.run_id = run_id


def _trigger(world=None, run_id="11111111-1111-4111-8111-111111111111"):
    """A stand-in for `trigger_phase`. Injected so a test never reaches Temporal — an
    unpatched trigger here would start a REAL workflow on the team's shared server.

    It creates the `Run` row a real dispatch would, because `A11yJourneyRun.run` is a genuine
    foreign key: a journey pass IS an agent run, unlike a baseline audit whose id is only a
    partition string. Faking the id without the row passes the test and fails at teardown.
    """
    from apps.runs.models import Run

    def _fn(**kwargs):
        _fn.calls.append(kwargs)
        if world is not None:
            spec = AgentSpec.objects.get(tenant=world["tenant"], key=JOURNEY_AGENT_KEY)
            Run.objects.get_or_create(
                id=run_id, defaults={"tenant": world["tenant"], "agent_spec": spec,
                                     "work_item": world["item"], "status": "running"})
        return _Outcome(run_id)
    _fn.calls = []
    return _fn


def _start(world, body=JOURNEY_BODY, *, trigger=None, monkeypatch=None, available=""):
    """Start a journey run without going near the registry or the object store: the parsing
    half has its own tests, and threading a real artifact through every behaviour test would
    test the fixture instead of the behaviour."""
    from apps.a11y import journeys as journeys_mod
    from integrations.types import A11yJourney

    parsed = A11yJourney(
        test_ref="TC-031", title="Complete Registration to First Expense",
        steps=tuple(parse_steps(body)), preconditions=tuple(parse_preconditions(body)),
        artifact_id="a-1",
    )
    # Patched on the SOURCE module, not on `journey`: `start_journey_check` imports it inside
    # the function (the platform's lazy-import discipline), so the local name is resolved at
    # call time and a patch on the importing module would never be seen.
    monkeypatch.setattr(journeys_mod, "journeys_for_project",
                        lambda *a, **k: {"journeys": [parsed] if parsed.steps else [],
                                         "skipped": [], "over_cap": []})
    # A journey needs a connected companion — the app under test runs on a machine the
    # platform cannot reach (R2). Stubbed here so every behaviour test does not have to
    # enroll a runner; the availability path has its own tests below.
    from apps.a11y import journey as journey_mod

    monkeypatch.setattr(journey_mod, "journey_available", lambda *a, **k: available)
    trigger = trigger or _trigger(world)
    result = start_journey_check(
        tenant_id=world["t"], project_id=world["p"], work_item_id=world["w"],
        base_url=APP_URL, trigger=trigger,
    )
    return result, trigger


# ── where a journey comes from (decision D1) ─────────────────────────────────

def test_only_an_e2e_test_case_is_a_journey():
    """A journey is the platform's own `Type: E2E` case, not every test case with steps."""
    assert is_journey(JOURNEY_BODY) is True
    assert is_journey(FUNCTIONAL_BODY) is False
    assert declared_type(JOURNEY_BODY) == "e2e"


def test_the_templates_own_placeholder_is_not_a_declared_type():
    """`**Type:** [Functional / Integration / E2E / ...]` is agent 09's blank, not a claim.
    Reading it as E2E would walk every unfilled test case as a critical journey."""
    assert declared_type("**Type:** [Functional / Integration / E2E / Performance]") == ""
    assert is_journey("**Type:** [Functional / Integration / E2E]") is False


def test_steps_come_from_the_test_steps_section_and_nothing_else():
    """`Expected Result` and `Test Data` are numbered and bulleted too. A body-wide scrape
    would fold an assertion into the walk and have the agent try to *perform* it."""
    steps = parse_steps(JOURNEY_BODY)
    assert [s.number for s in steps] == [1, 2, 3, 4]
    assert steps[0].text.startswith("Navigate to /register")
    assert "dashboard lists the new expense" not in " ".join(s.text for s in steps)


def test_a_route_is_read_only_when_the_step_names_one():
    steps = {s.number: s for s in parse_steps(JOURNEY_BODY)}
    assert steps[1].route == "/register"
    assert steps[2].route == "/dashboard"
    # "Log in and open /dashboard" names one; a step that names none stays blank rather than
    # inheriting the previous step's route, which would file findings on the wrong screen.
    assert parse_steps("### Test Steps\n1. Press the button\n2. Press it again")[0].route == ""


def test_preconditions_are_carried_so_the_agent_can_refuse_a_journey_it_cannot_set_up():
    assert parse_preconditions(JOURNEY_BODY) == [
        "No account exists for tc031@test.com", "The seed database is empty"]


def test_an_e2e_case_with_no_readable_steps_is_not_walkable():
    """The export parser's last resort is a synthetic "execute as documented" step so an
    export always succeeds. That is right for an export and catastrophic here: an agent handed
    one vague instruction will report *something*, and it would enter the ledger as real."""
    from integrations.types import A11yJourney

    assert parse_steps("**Type:** E2E\n\nRun the registration journey.") == []
    assert A11yJourney(test_ref="TC-9", title="x", steps=()).is_walkable is False


def test_a_renumbered_body_is_renumbered_by_position():
    """A body that jumps 1, 2, 4 (or restarts) would otherwise produce a step number the
    reconciliation cannot subtract against, and a step nobody can file a finding for."""
    steps = parse_steps("### Test Steps\n1. First\n2. Second\n4. Fourth\n")
    assert [s.number for s in steps] == [1, 2, 3]
    assert steps[2].text == "Fourth"


def test_asking_for_a_journey_that_does_not_exist_says_what_was_available(world, monkeypatch):
    from apps.a11y import journeys as journeys_mod

    monkeypatch.setattr(journeys_mod, "journeys_for_project",
                        lambda *a, **k: {"journeys": [], "skipped": [], "over_cap": []})
    with pytest.raises(JourneyError, match="The ones that can: none"):
        journey_for(world["t"], world["p"], "TC-999")


def test_journeys_for_project_reports_what_it_could_not_read(world, monkeypatch):
    """"We found no journeys" and "we found three and could not read them" are different
    facts about a project. A caller that only ever sees a list cannot tell them apart."""
    from mcp_platform_state import tools

    from apps.registry.models import Artifact

    art = Artifact.objects.create(
        tenant=world["tenant"], project=world["project"], phase="testing",
        type="test_case", status="internal", title="TC-040 — E2E: Broken",
    )
    monkeypatch.setattr(tools, "get_artifact_body",
                        lambda *a, **k: {"body": "**Type:** E2E\n\nNo steps here."})
    found = journeys_for_project(world["t"], world["p"])
    assert found["journeys"] == []
    assert len(found["skipped"]) == 1
    assert "no steps could be read" in found["skipped"][0]["reason"]
    assert found["skipped"][0]["artifact_id"] == str(art.id)


# ── starting a pass ──────────────────────────────────────────────────────────

def test_starting_a_journey_freezes_its_steps(world, monkeypatch):
    result, trigger = _start(world, monkeypatch=monkeypatch)
    assert result["started"] is True and result["steps"] == 4
    row = A11yJourneyRun.objects.get(id=result["journey_run_id"])
    assert [s["number"] for s in row.steps] == [1, 2, 3, 4]
    assert row.status == A11yJourneyRun.Status.WALKING
    assert trigger.calls[0]["agent_key"] == JOURNEY_AGENT_KEY
    assert trigger.calls[0]["execution_mode"] == "companion"


def test_a_project_with_no_journey_is_told_so_rather_than_dispatched(world, monkeypatch):
    from apps.a11y import journeys as journeys_mod

    monkeypatch.setattr(journeys_mod, "journeys_for_project",
                        lambda *a, **k: {"journeys": [], "skipped": [], "over_cap": []})
    trigger = _trigger(world)
    out = start_journey_check(tenant_id=world["t"], project_id=world["p"],
                              work_item_id=world["w"], base_url=APP_URL, trigger=trigger)
    assert out["started"] is False and out["reason"] == NO_JOURNEY
    assert trigger.calls == []          # nothing dispatched to walk nothing


def test_no_companion_is_a_reported_reason_not_an_exception(world, monkeypatch):
    """An unavailable check must be reported. A skipped check and a passed check look
    identical in a report, which is the whole of D-A11Y-3."""
    result, trigger = _start(world, monkeypatch=monkeypatch, available=NO_COMPANION)
    assert result["started"] is False and result["reason"] == NO_COMPANION
    assert trigger.calls == []


def test_a_refused_trigger_comes_back_as_a_reason(world, monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError("temporal is unreachable")

    result, _ = _start(world, trigger=_boom, monkeypatch=monkeypatch)
    assert result["started"] is False
    assert "temporal is unreachable" in result["reason"]


def test_the_agent_reads_its_contract_including_the_step_count(world, monkeypatch):
    result, _ = _start(world, monkeypatch=monkeypatch)
    work = journey_for_run(world["t"], result["run_id"])
    assert work["total_steps"] == 4 and work["test_ref"] == "TC-031"
    assert sorted(work["checks"]) == sorted(A11Y_JOURNEY_CRITERIA)
    assert work["preconditions"][0].startswith("No account exists")


# ── AC1: pass/fail per criterion, with a confidence ──────────────────────────

def test_a_journey_reports_per_criterion_with_a_confidence(world, monkeypatch):
    """AC1. Eight checks report separately, each against the criterion it owns."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    record_step(tenant_id=world["t"], run_id=run_id, number=1, outcome=A11Y_STEP_WALKED)

    for checker in ("trap", "focus_visible", "status"):
        out = record_journey_finding(
            tenant_id=world["t"], run_id=run_id, step=1, checker=checker,
            verdict="fail", confidence=0.93, evidence="observed while tabbing",
            suggested_fix="fix it", route="/register",
        )
        assert out["recorded"] is True

    rows = {f.checker: f for f in A11yFinding.objects.filter(project_id=world["p"])}
    assert rows["trap"].criterion == "2.1.2"
    assert rows["focus_visible"].criterion == "2.4.7"
    assert rows["status"].criterion == "4.1.3"
    assert all(r.confidence == 0.93 for r in rows.values())
    assert all(r.source == A11yFinding.Source.AGENTIC for r in rows.values())


def test_a_confident_pass_is_recorded_as_a_pass_and_stored_as_no_finding(world, monkeypatch):
    """A pass is not a finding — its absence next run is how a fix is recognised."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    out = record_journey_finding(
        tenant_id=world["t"], run_id=result["run_id"], step=2, checker="focus_order",
        verdict="pass", confidence=0.95, evidence="tab order followed the visual order",
        route="/dashboard",
    )
    assert out["recorded"] is False
    assert A11yFinding.objects.filter(project_id=world["p"]).count() == 0


def test_a_low_confidence_verdict_goes_to_review_not_to_a_failure(world, monkeypatch):
    """The confidence gate is QA-06's and it applies here unchanged. 'Is this focus ring
    visible enough' is exactly the judgement that belongs with a person."""
    from apps.a11y.triage import TRIAGE_REVIEW

    result, _ = _start(world, monkeypatch=monkeypatch)
    out = record_journey_finding(
        tenant_id=world["t"], run_id=result["run_id"], step=1, checker="focus_visible",
        verdict="fail", confidence=0.4, evidence="a faint outline", route="/register",
    )
    assert out["outcome"] == TRIAGE_REVIEW
    assert A11yFinding.objects.get(checker="focus_visible").outcome == TRIAGE_REVIEW


def test_an_uncertain_verdict_is_a_first_class_answer(world, monkeypatch):
    from apps.a11y.triage import TRIAGE_REVIEW

    result, _ = _start(world, monkeypatch=monkeypatch)
    out = record_journey_finding(
        tenant_id=world["t"], run_id=result["run_id"], step=1, checker="focus_obscured",
        verdict="uncertain", confidence=0.0,
        evidence="the header overlapped the field but I could not tell if it was fully hidden",
        route="/register",
    )
    assert out["outcome"] == TRIAGE_REVIEW and out["recorded"] is True


# ── AC2 + AC5: the planted keyboard trap, end to end ─────────────────────────

def test_a_keyboard_trap_reports_fail_on_2_1_2(world, monkeypatch):
    """AC2 + AC5. The whole journey: four steps, a trap planted at step 3, walked and
    reported the way the agent would."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]

    for number in (1, 2, 3, 4):
        record_step(tenant_id=world["t"], run_id=run_id, number=number,
                    outcome=A11Y_STEP_WALKED)
    record_journey_finding(
        tenant_id=world["t"], run_id=run_id, step=3, checker="trap", verdict="fail",
        confidence=0.97,
        evidence="Tabbed 12 times inside the amount date picker; focus cycled between the "
                 "month and year selects; Shift+Tab and Escape both had no effect",
        suggested_fix="Let Escape close the picker and return focus to the field",
        route="/expenses/new", selector="div.datepicker",
    )
    summary = finish_journey(tenant_id=world["t"], run_id=run_id)

    finding = A11yFinding.objects.get(project_id=world["p"], checker="trap")
    assert finding.criterion == "2.1.2"
    assert finding.verdict == "fail"
    assert finding.severity == "critical"          # 2.1.2 is Level A
    assert finding.source == A11yFinding.Source.AGENTIC
    assert "Shift+Tab and Escape" in finding.evidence
    assert summary["status"] == A11yJourneyRun.Status.COMPLETE
    assert summary["walked"] == 4 and summary["not_reached"] == []


# ── AC3: a status message that never announces ───────────────────────────────

def test_a_status_message_that_never_announces_reports_fail_on_4_1_3(world, monkeypatch):
    """AC3."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    record_step(tenant_id=world["t"], run_id=run_id, number=3, outcome=A11Y_STEP_WALKED)
    record_journey_finding(
        tenant_id=world["t"], run_id=run_id, step=3, checker="status", verdict="fail",
        confidence=0.9,
        evidence='"Expense saved" appeared in a div with no role and no aria-live; the '
                 "element was created at the same moment as its text",
        suggested_fix='Render an empty role="status" region on load and write into it',
        route="/expenses/new",
    )
    finding = A11yFinding.objects.get(checker="status")
    assert finding.criterion == "4.1.3"
    assert finding.wcag_level == "AA" and finding.severity == "high"


# ── AC4: a step that could not be reached ────────────────────────────────────

def test_a_blocked_step_is_reported_with_its_reason(world, monkeypatch):
    """AC4. Never a pass, never a fail — the step is recorded as one the agent could not
    test, and it says what stopped it."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    record_step(tenant_id=world["t"], run_id=run_id, number=1, outcome=A11Y_STEP_WALKED)
    record_step(tenant_id=world["t"], run_id=run_id, number=2, outcome=A11Y_STEP_BLOCKED,
                reason="the login form rejected the seeded account")

    summary = finish_journey(tenant_id=world["t"], run_id=run_id)
    assert summary["blocked"] == [
        {"step": 2, "reason": "the login form rejected the seeded account"}]
    assert summary["not_reached"] == [3, 4]
    assert A11yFinding.objects.filter(project_id=world["p"]).count() == 0


def test_a_step_the_agent_never_mentioned_is_recorded_as_not_reached(world, monkeypatch):
    """The subtraction, not the agent's word for it. An agent that stopped early is by
    definition not still running to tell you that it stopped (D-A11Y-50's rule, on steps)."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    record_step(tenant_id=world["t"], run_id=run_id, number=1, outcome=A11Y_STEP_WALKED)

    finish_journey(tenant_id=world["t"], run_id=run_id)
    outcomes = {r.number: r.outcome for r in A11yJourneyStepResult.objects.all()}
    assert outcomes == {1: A11Y_STEP_WALKED, 2: A11Y_STEP_NOT_REACHED,
                        3: A11Y_STEP_NOT_REACHED, 4: A11Y_STEP_NOT_REACHED}


def test_the_agent_cannot_claim_a_step_was_never_reached(world, monkeypatch):
    """Letting a run assert that it did not do something is exactly the claim that cannot be
    trusted from a run that stopped."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    with pytest.raises(JourneyRunError, match="written by the platform"):
        record_step(tenant_id=world["t"], run_id=result["run_id"], number=1,
                    outcome=A11Y_STEP_NOT_REACHED)


def test_a_journey_that_walked_nothing_is_a_failed_pass_not_a_clean_one(world, monkeypatch):
    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    record_step(tenant_id=world["t"], run_id=run_id, number=1, outcome=A11Y_STEP_BLOCKED,
                reason="the application was not reachable")
    summary = finish_journey(tenant_id=world["t"], run_id=run_id)
    assert summary["status"] == A11yJourneyRun.Status.FAILED
    assert "nothing was tested" in summary["reason"]


def test_a_blocked_step_says_so_even_when_the_agent_forgets_the_reason(world, monkeypatch):
    from apps.a11y.journey import NO_REASON_GIVEN

    result, _ = _start(world, monkeypatch=monkeypatch)
    out = record_step(tenant_id=world["t"], run_id=result["run_id"], number=2,
                      outcome=A11Y_STEP_BLOCKED, reason="  ")
    assert out["reason"] == NO_REASON_GIVEN


def test_completeness_names_the_steps_that_were_never_answered_for(world, monkeypatch):
    result, _ = _start(world, monkeypatch=monkeypatch)
    record_step(tenant_id=world["t"], run_id=result["run_id"], number=1,
                outcome=A11Y_STEP_WALKED)
    check = verify_journey_completeness(tenant_id=world["t"], run_id=result["run_id"])
    assert check == {"asked": 4, "reported": 1, "missing": [2, 3, 4], "complete": False}


# ── the resolution safety property (D-A11Y-49, second application) ───────────

def _static_finding(world, **over):
    fields = {
        "tenant_id": world["t"], "project_id": world["p"],
        "fingerprint": "static-1", "route": "/register", "selector": "img.hero",
        "criterion": "1.1.1", "criteria": ["1.1.1"], "wcag_level": "A",
        "checker": "alt", "source": A11yFinding.Source.AI, "verdict": "fail",
        "outcome": "failure", "confidence": 0.9, "severity": "critical",
        "status": A11yFinding.Status.OPEN,
    }
    fields.update(over)
    return A11yFinding.objects.create(**fields)


def test_a_journey_pass_never_resolves_a_static_finding(world, monkeypatch):
    """The one way this task could have quietly destroyed data.

    A keyboard walk of /register has nothing to say about the alt text on that page. If a
    journey pass closed findings by absence the way a scan run does, it would mark the missing
    alt text fixed — reporting a problem as solved that nobody touched.
    """
    static = _static_finding(world)
    scanner = _static_finding(world, fingerprint="static-2", checker="",
                              source=A11yFinding.Source.RULE, criterion="1.4.3")

    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    record_step(tenant_id=world["t"], run_id=run_id, number=1, outcome=A11Y_STEP_WALKED)
    record_journey_finding(
        tenant_id=world["t"], run_id=run_id, step=1, checker="trap", verdict="fail",
        confidence=0.95, evidence="focus could not leave the picker", route="/register")
    finish_journey(tenant_id=world["t"], run_id=run_id)

    static.refresh_from_db()
    scanner.refresh_from_db()
    assert static.status == A11yFinding.Status.OPEN
    assert scanner.status == A11yFinding.Status.OPEN


def test_a_journey_pass_does_resolve_its_own_finding_once_it_is_fixed(world, monkeypatch):
    """The other direction — otherwise nothing this agent finds could ever be closed."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    record_step(tenant_id=world["t"], run_id=run_id, number=1, outcome=A11Y_STEP_WALKED)
    record_journey_finding(
        tenant_id=world["t"], run_id=run_id, step=1, checker="trap", verdict="fail",
        confidence=0.95, evidence="focus could not leave the picker", route="/register")
    finish_journey(tenant_id=world["t"], run_id=run_id)
    assert A11yFinding.objects.get(checker="trap").status == A11yFinding.Status.OPEN

    # A second pass over the same journey, now clean.
    second, _ = _start(world, trigger=_trigger(world, "22222222-2222-4222-8222-222222222222"),
                       monkeypatch=monkeypatch)
    record_step(tenant_id=world["t"], run_id=second["run_id"], number=1,
                outcome=A11Y_STEP_WALKED)
    finish_journey(tenant_id=world["t"], run_id=second["run_id"])
    assert A11yFinding.objects.get(checker="trap").status == A11yFinding.Status.RESOLVED


def test_a_finding_on_a_route_the_pass_never_walked_is_not_resolved(world, monkeypatch):
    """A route the agent never got to is not a route it found clean — the same rule QA-17
    needed for unreachable routes, applied to steps that were blocked or never reached."""
    old = _static_finding(
        world, fingerprint="agentic-old", route="/expenses/new", selector="div.datepicker",
        criterion="2.1.2", criteria=["2.1.2"], checker="trap",
        source=A11yFinding.Source.AGENTIC)

    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    record_step(tenant_id=world["t"], run_id=run_id, number=1, outcome=A11Y_STEP_WALKED)
    record_step(tenant_id=world["t"], run_id=run_id, number=2, outcome=A11Y_STEP_BLOCKED,
                reason="login failed")
    finish_journey(tenant_id=world["t"], run_id=run_id)

    old.refresh_from_db()
    assert old.status == A11yFinding.Status.OPEN


# ── validation ───────────────────────────────────────────────────────────────

def test_a_check_that_does_not_exist_is_refused(world, monkeypatch):
    result, _ = _start(world, monkeypatch=monkeypatch)
    with pytest.raises(JourneyRunError, match="is not a journey check"):
        record_journey_finding(
            tenant_id=world["t"], run_id=result["run_id"], step=1, checker="alt",
            verdict="fail", confidence=0.9, evidence="x")


def test_a_check_reporting_a_criterion_it_does_not_own_is_refused(world, monkeypatch):
    """A check reporting against a criterion it does not judge corrupts the one artifact a
    client or auditor actually reads. The element path's rule, unchanged."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    with pytest.raises(JourneyRunError, match="which it does not"):
        record_journey_finding(
            tenant_id=world["t"], run_id=result["run_id"], step=1, checker="trap",
            criteria=["1.1.1"], verdict="fail", confidence=0.9, evidence="x")


def test_reporting_against_a_step_the_journey_does_not_have_is_refused(world, monkeypatch):
    result, _ = _start(world, monkeypatch=monkeypatch)
    with pytest.raises(JourneyRunError, match="has no step 9"):
        record_step(tenant_id=world["t"], run_id=result["run_id"], number=9,
                    outcome=A11Y_STEP_WALKED)


def test_recording_against_a_run_that_is_not_a_journey_says_so(world):
    with pytest.raises(JourneyRunError, match="no accessibility journey is attached"):
        journey_for_run(world["t"], "33333333-3333-4333-8333-333333333333")


def test_a_finding_marks_its_step_walked_when_the_agent_forgot_to(world, monkeypatch):
    """An agent that reports findings but skips the step outcome must not leave a walked step
    looking like one nobody reached."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    record_journey_finding(
        tenant_id=world["t"], run_id=result["run_id"], step=2, checker="keyboard",
        verdict="fail", confidence=0.9, evidence="could not tab to Submit", route="/dashboard")
    assert A11yJourneyStepResult.objects.get(number=2).outcome == A11Y_STEP_WALKED


def test_a_blocked_step_is_not_downgraded_by_a_later_finding(world, monkeypatch):
    """"I got here, saw this, then hit a wall" is one step, not two."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    record_step(tenant_id=world["t"], run_id=run_id, number=2, outcome=A11Y_STEP_BLOCKED,
                reason="the form never submitted")
    record_journey_finding(
        tenant_id=world["t"], run_id=run_id, step=2, checker="focus_visible", verdict="fail",
        confidence=0.9, evidence="no focus ring on the submit button", route="/dashboard")
    assert A11yJourneyStepResult.objects.get(number=2).outcome == A11Y_STEP_BLOCKED


def test_a_screen_level_finding_needs_no_element(world, monkeypatch):
    """Focus order is a property of the page. Pinning it to an arbitrary element would file
    the problem against something that is not what is wrong."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    out = record_journey_finding(
        tenant_id=world["t"], run_id=result["run_id"], step=2, checker="focus_order",
        verdict="fail", confidence=0.9, evidence="focus jumped to the footer between fields",
        route="/dashboard")
    assert out["recorded"] is True
    assert A11yFinding.objects.get(checker="focus_order").selector == "step:2"


# ── the maps, and the registry they must agree with ──────────────────────────

def test_the_journey_checks_are_one_per_criterion():
    """QA-22 promotes reliability per checker, and its stated edge case is that a proven
    keyboard-trap check may gate while a newer check stays advisory. One checker owning all
    eight would make that impossible — one weak check would hold back seven good ones."""
    assert A11Y_JOURNEY_CRITERIA == {
        "keyboard": ("2.1.1",), "trap": ("2.1.2",), "focus_order": ("2.4.3",),
        "focus_visible": ("2.4.7",), "focus_obscured": ("2.4.11",),
        "on_focus": ("3.2.1",), "on_input": ("3.2.2",), "status": ("4.1.3",),
    }
    assert all(len(c) == 1 for c in A11Y_JOURNEY_CRITERIA.values())


def test_the_poc_element_checks_are_untouched():
    """Merging the journey checks into the element map would have silently broken the
    ownership drift test, whose docstring says extending AI coverage must be a decision.

    **Five, not four.** `structure` was added on 24 August (§9.16, the 1.3.1 scope gap) and this
    list was not updated with it, so this test has been red ever since — asserting a fourth
    element check that the platform had deliberately grown past. The point of the test is that
    the set only changes when somebody decides to change it; that is served by naming the set
    it should be, and a stale list serves the opposite.

    `semantics` and `structure` both carry 1.3.1 and are still two checks — one asks whether an
    element is pretending to be a control, the other whether a container's visible arrangement
    is in the markup at all. See `A11Y_CHECKER_CRITERIA` for that in full.
    """
    assert set(A11Y_CHECKER_CRITERIA) == {"alt", "semantics", "structure", "color", "label",
                                          "graphics"}
    assert set(A11Y_ALL_CHECKER_CRITERIA) == (set(A11Y_CHECKER_CRITERIA)
                                             | set(A11Y_JOURNEY_CRITERIA)
                                             | set(A11Y_HELD_BACK_CRITERIA))


def test_the_journey_checks_match_what_the_registry_calls_phase_2(db):
    """The eight are not invented: `ownership.json` classifies every one as `tier=phase_2`,
    and five carry the rationale "(agentic Phase 2)" in the registry's own words. If this
    fails, one of the two is wrong about what Phase 2 covers."""
    from apps.a11y.ownership import load_ownership, ownership

    load_ownership()
    claimed = {n for owned in A11Y_JOURNEY_CRITERIA.values() for n in owned}
    assert len(claimed) == 8
    for number in claimed:
        assert ownership(number).tier == "phase_2", f"{number} is not a Phase 2 criterion"


def test_a_tenant_can_tune_a_journey_check(db):
    """Before QA-20 `thresholds_for` iterated the four element checks only, so configuring
    `trap` was rejected as a check that "does not exist" — for a check the platform would be
    actively running against that tenant."""
    from apps.a11y.triage import DEFAULT_CONFIDENCE_THRESHOLD, thresholds_for
    from apps.tenancy.services import create_tenant

    tenant = create_tenant(name="Tuner")
    resolved = thresholds_for(tenant.id)
    assert set(resolved) == set(A11Y_ALL_CHECKER_CRITERIA)
    assert resolved["trap"] == DEFAULT_CONFIDENCE_THRESHOLD


# ── the agent body ───────────────────────────────────────────────────────────

def _body() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[2] / "agents" / "09d_a11y_journey"
            / "agent.md").read_text(encoding="utf-8")


def test_the_agent_body_covers_all_eight_checks_and_their_criteria():
    body = _body()
    for checker, criteria in A11Y_JOURNEY_CRITERIA.items():
        assert f"`{checker}`" in body, f"the body never names the {checker} check"
        for criterion in criteria:
            assert criterion in body


def test_the_agent_body_passes_the_reference_sweep():
    """Non-negotiable #11 §8: an authored agent naming a local file is a failed migration."""
    body = _body().lower()
    for banned in ("tasks.md", "requirements.md", "claude.md", "docs/", "./", "../"):
        assert banned not in body, f"the body still names {banned!r}"


def test_the_agent_body_states_the_rule_that_matters_most():
    """Two instructions carry this agent: keyboard-only, and never report a step you did not
    reach. If an edit ever removes either, every result it produces becomes unfounded."""
    body = _body().lower()
    assert "keyboard only" in body
    assert "never report on a step you did not reach" in body


# ── the capability read path (A11yAI.check_journey) ──────────────────────────

def _capability(world):
    from integrations.a11yai.builtin import BuiltinA11yAI

    return BuiltinA11yAI(tenant_id=world["t"])


def _journey(steps=True):
    from integrations.types import A11yJourney

    return A11yJourney(test_ref="TC-031", title="x",
                       steps=tuple(parse_steps(JOURNEY_BODY)) if steps else ())


def test_asking_about_a_journey_nobody_walked_is_uncertain_never_a_pass(world):
    """The single most dangerous thing this capability could return is an empty list, which
    reads as "eight checks ran and found nothing". These eight criteria are the ones nothing
    else in the platform can see, so silence here is the least safe silence in the build."""
    out = _capability(world).check_journey(journey=_journey(), project_id=world["p"])
    assert len(out) == len(A11Y_JOURNEY_CRITERIA)
    assert {j.verdict for j in out} == {"uncertain"}
    assert all(j.confidence == 0.0 for j in out)


def test_asking_about_a_journey_with_no_steps_says_there_was_nothing_to_walk(world):
    from integrations.a11yai.builtin import NO_STEPS

    out = _capability(world).check_journey(journey=_journey(steps=False))
    assert {j.verdict for j in out} == {"uncertain"}
    assert all(NO_STEPS in j.evidence for j in out)


def test_the_worst_outcome_per_check_wins(world, monkeypatch):
    """A trap found at step 3 is a trap in this journey. Averaging it away with two clean
    steps would hide the only thing worth reporting."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    for number in (1, 2, 3):
        record_step(tenant_id=world["t"], run_id=run_id, number=number,
                    outcome=A11Y_STEP_WALKED)
    record_journey_finding(
        tenant_id=world["t"], run_id=run_id, step=1, checker="trap", verdict="uncertain",
        confidence=0.0, evidence="could not tell", route="/register")
    record_journey_finding(
        tenant_id=world["t"], run_id=run_id, step=3, checker="trap", verdict="fail",
        confidence=0.97, evidence="focus never left the picker", route="/expenses/new")

    out = {j.checker: j for j in
           _capability(world).check_journey(journey=_journey(), project_id=world["p"])}
    assert out["trap"].verdict == "fail"
    assert "focus never left" in out["trap"].evidence


def test_a_check_with_no_row_after_a_real_walk_is_still_uncertain(world, monkeypatch):
    """Two opposite reasons produce no row — it passed confidently (a pass is stored as no
    finding), or its step was blocked. Findings alone cannot tell them apart, so guessing
    `pass` would turn a step nobody reached into a clean bill of health."""
    from apps.a11y.journey import NOTHING_TO_REPORT

    result, _ = _start(world, monkeypatch=monkeypatch)
    record_step(tenant_id=world["t"], run_id=result["run_id"], number=1,
                outcome=A11Y_STEP_WALKED)
    out = {j.checker: j for j in
           _capability(world).check_journey(journey=_journey(), project_id=world["p"])}
    assert out["status"].verdict == "uncertain"
    assert NOTHING_TO_REPORT in out["status"].evidence


def test_a_pass_that_walked_nothing_says_the_check_was_never_asked(world, monkeypatch):
    from apps.a11y.journey import NOT_ASKED

    result, _ = _start(world, monkeypatch=monkeypatch)
    record_step(tenant_id=world["t"], run_id=result["run_id"], number=1,
                outcome=A11Y_STEP_BLOCKED, reason="the app was not reachable")
    out = {j.checker: j for j in
           _capability(world).check_journey(journey=_journey(), project_id=world["p"])}
    assert out["keyboard"].verdict == "uncertain"
    assert NOT_ASKED in out["keyboard"].evidence


def test_the_capability_never_starts_a_walk(world, monkeypatch):
    """D-A11Y-4, and harder here than for an element: a walk drives a real browser on the
    companion for as long as the journey takes."""
    calls = []
    monkeypatch.setattr("apps.a11y.journey.start_journey_check",
                        lambda **k: calls.append(k))
    _capability(world).check_journey(journey=_journey(), project_id=world["p"])
    assert calls == []


# ── selection edges ──────────────────────────────────────────────────────────

def _test_case(world, title, body, monkeypatch_target=None):
    from apps.registry.models import Artifact

    return Artifact.objects.create(
        tenant=world["tenant"], project=world["project"], phase="testing",
        type="test_case", status="internal", title=title,
    )


def test_a_test_case_with_no_declared_type_is_never_walked():
    """A body without agent 09's `Type:` line is either hand-written or from another producer.
    Assuming "journey" about an unknown document is how a login smoke test gets walked as a
    critical path."""
    assert declared_type("## TC-050\n\n### Test Steps\n1. Do a thing\n2. Do another") == ""
    assert is_journey("## TC-050\n\n### Test Steps\n1. Do a thing") is False


def test_steps_can_come_from_a_table_when_the_body_uses_one():
    body = (
        "**Type:** E2E\n\n### Test Steps\n\n"
        "| Step | Action | Expected |\n|---|---|---|\n"
        "| 1 | Open /login | the form renders |\n"
        "| 2 | Submit valid credentials | the dashboard loads |\n"
    )
    steps = parse_steps(body)
    assert [s.text for s in steps] == ["Open /login", "Submit valid credentials"]
    assert steps[0].route == "/login"


def test_a_test_case_whose_body_cannot_be_read_is_reported_not_ignored(world, monkeypatch):
    from mcp_platform_state import tools

    _test_case(world, "TC-041 — E2E: Unreadable", "")
    monkeypatch.setattr(tools, "get_artifact_body",
                        lambda *a, **k: {"body": "", "error": "the object store is unreachable"})
    found = journeys_for_project(world["t"], world["p"])
    assert found["journeys"] == []
    assert found["skipped"][0]["reason"] == "the object store is unreachable"


def test_journeys_past_the_cap_are_named_rather_than_dropped(world, monkeypatch):
    """A walk drives a real browser for as long as the journey takes, so the cap is small.
    What it excludes is reported — a silent truncation reads as "we covered everything"."""
    from mcp_platform_state import tools

    from apps.a11y.journeys import MAX_JOURNEYS

    for n in range(MAX_JOURNEYS + 2):
        _test_case(world, f"TC-{n:03d} — E2E: Journey {n}", "")
    monkeypatch.setattr(
        tools, "get_artifact_body",
        lambda tid, aid, **k: {"body": "**Type:** E2E\n\n### Test Steps\n1. Open /a\n2. Click"})
    found = journeys_for_project(world["t"], world["p"])
    assert len(found["journeys"]) == MAX_JOURNEYS
    assert len(found["over_cap"]) == 2


def test_a_named_journey_can_be_asked_for_by_its_tc_id(world, monkeypatch):
    from mcp_platform_state import tools

    _test_case(world, "TC-031 — E2E: Registration", "")
    monkeypatch.setattr(tools, "get_artifact_body", lambda *a, **k: {"body": JOURNEY_BODY})
    # The TC-ID lives on the artifact's external_ref in production; matching also falls back
    # to the title, which is what a person actually types.
    journey = journey_for(world["t"], world["p"], "TC-031")
    assert len(journey.steps) == 4


def test_starting_a_named_journey_uses_it(world, monkeypatch):
    from apps.a11y import journey as journey_mod
    from apps.a11y import journeys as journeys_mod
    from integrations.types import A11yJourney

    wanted = A11yJourney(test_ref="TC-077", title="Checkout",
                         steps=tuple(parse_steps(JOURNEY_BODY)))
    monkeypatch.setattr(journeys_mod, "journey_for", lambda *a, **k: wanted)
    monkeypatch.setattr(journey_mod, "journey_available", lambda *a, **k: "")
    out = start_journey_check(
        tenant_id=world["t"], project_id=world["p"], work_item_id=world["w"],
        base_url=APP_URL, test_ref="TC-077", trigger=_trigger(world))
    assert out["started"] is True and out["test_ref"] == "TC-077"


def test_asking_for_a_journey_that_is_not_there_is_a_reason_not_a_crash(world, monkeypatch):
    from apps.a11y import journeys as journeys_mod

    def _raise(*a, **k):
        raise JourneyError("no walkable journey 'TC-999' in this project — available: none")

    monkeypatch.setattr(journeys_mod, "journey_for", _raise)
    out = start_journey_check(
        tenant_id=world["t"], project_id=world["p"], work_item_id=world["w"],
        base_url=APP_URL, test_ref="TC-999", trigger=_trigger(world))
    assert out["started"] is False and "TC-999" in out["reason"]


def test_a_step_number_that_is_not_a_number_is_refused(world, monkeypatch):
    result, _ = _start(world, monkeypatch=monkeypatch)
    with pytest.raises(JourneyRunError, match="whole number"):
        record_step(tenant_id=world["t"], run_id=result["run_id"], number="two",
                    outcome=A11Y_STEP_WALKED)
    with pytest.raises(JourneyRunError, match="whole number"):
        record_journey_finding(
            tenant_id=world["t"], run_id=result["run_id"], step="two", checker="trap",
            verdict="fail", confidence=0.9, evidence="x")


def test_a_malformed_verdict_is_refused_with_a_message_the_agent_can_act_on(world, monkeypatch):
    result, _ = _start(world, monkeypatch=monkeypatch)
    with pytest.raises(JourneyRunError, match="invalid a11y verdict"):
        record_journey_finding(
            tenant_id=world["t"], run_id=result["run_id"], step=1, checker="trap",
            verdict="broken", confidence=0.9, evidence="x")


# ── G6a: the address, and the pass that closes itself ────────────────────────

@pytest.mark.django_db
def test_a_journey_with_nowhere_to_go_is_refused_before_anything_is_read(world, monkeypatch):
    """The check that costs nothing and matters most.

    A journey is a real browser operating a running application. Without an address there is
    nowhere to walk AND nothing to bound the browser to, so this is refused first — before the
    registry is read, before a companion is looked for, and above all before an agent run is
    dispatched to discover the problem for itself.
    """
    from apps.a11y import journeys as journeys_mod

    def _never(*a, **k):
        raise AssertionError("the address is checked before anything is read")

    monkeypatch.setattr(journeys_mod, "journeys_for_project", _never)
    trigger = _trigger(world)
    for nothing in ("", "   ", None):
        out = start_journey_check(tenant_id=world["t"], project_id=world["p"],
                                  work_item_id=world["w"], base_url=nothing, trigger=trigger)
        assert out["started"] is False
        assert out["reason"] == NO_ADDRESS
        assert "start the application" in out["reason"], "it says what to do, not just no"
    assert trigger.calls == [], "nothing was dispatched to walk nowhere"


@pytest.mark.django_db
def test_the_agents_contract_says_where_to_go(world, monkeypatch):
    """G6a's core. Before this the agent got its steps, its preconditions and the eight checks —
    and no application, so it would have started and honestly reported every step blocked."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    contract = journey_for_run(world["t"], result["run_id"])
    assert contract["base_url"] == APP_URL
    assert contract["total_steps"] == len(contract["steps"])


@pytest.mark.django_db
def test_the_address_is_stored_as_walked_not_looked_up_later(world, monkeypatch):
    """A journey result is a claim about the thing that was walked, so the address is recorded
    on the pass. A trailing slash is trimmed because it is joined to a step's path."""
    from apps.a11y import journey as journey_mod
    from apps.a11y import journeys as journeys_mod
    from integrations.types import A11yJourney

    parsed = A11yJourney(test_ref="TC-031", title="Checkout",
                         steps=tuple(parse_steps(JOURNEY_BODY)))
    monkeypatch.setattr(journeys_mod, "journeys_for_project",
                        lambda *a, **k: {"journeys": [parsed], "skipped": [], "over_cap": []})
    monkeypatch.setattr(journey_mod, "journey_available", lambda *a, **k: "")
    out = start_journey_check(
        tenant_id=world["t"], project_id=world["p"], work_item_id=world["w"],
        base_url="http://127.0.0.1:5173/", trigger=_trigger(world))

    assert out["base_url"] == "http://127.0.0.1:5173"
    row = A11yJourneyRun.objects.get(id=out["journey_run_id"])
    assert row.base_url == "http://127.0.0.1:5173"


@pytest.mark.django_db
def test_a_walk_whose_run_died_is_closed_by_the_platform(world, monkeypatch):
    """`finish_journey` has exactly one caller — the agent — and an agent that died is not
    still running to call it. Without this the walk reads `walking` for ever."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    record_step(tenant_id=world["t"], run_id=run_id, number=1, outcome=A11Y_STEP_WALKED)
    assert A11yJourneyRun.objects.get(run_id=run_id).status == A11yJourneyRun.Status.WALKING

    out = close_unfinished_journey(tenant_id=world["t"], run_id=run_id,
                                   reason="the engine ended abnormally")
    assert out["closed"] is True
    row = A11yJourneyRun.objects.get(run_id=run_id)
    assert row.status == A11yJourneyRun.Status.COMPLETE, "one step WAS walked, so it is a result"
    assert "the engine ended abnormally" in row.summary["closed_by_platform"]
    # And the honesty that makes closing it safe: the steps nobody spoke about are accounted for.
    assert row.summary["not_reached"], "the unreported steps are recorded as never walked"
    never = A11yJourneyStepResult.objects.filter(journey_run=row, outcome=A11Y_STEP_NOT_REACHED)
    assert never.exists()


@pytest.mark.django_db
def test_closing_a_walk_keeps_what_the_agent_already_recorded(world, monkeypatch):
    """The expensive half is the browser having really walked the application. A run that died
    at the end must not cost the steps and findings it produced on the way."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    record_journey_finding(
        tenant_id=world["t"], run_id=run_id, step=1, checker="trap", verdict="fail",
        confidence=0.95, evidence="tab never leaves the date picker", route="/checkout")

    close_unfinished_journey(tenant_id=world["t"], run_id=run_id)
    assert A11yFinding.objects.filter(tenant_id=world["t"], checker="trap").count() == 1


@pytest.mark.django_db
def test_closing_is_idempotent_and_never_touches_a_pass_the_agent_finished(world, monkeypatch):
    """It is called from the orchestrator's generic success AND failure paths, which see every
    phase, so it has to be safe to call on a finished pass and on a run with no journey at all."""
    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    record_step(tenant_id=world["t"], run_id=run_id, number=1, outcome=A11Y_STEP_WALKED)
    finish_journey(tenant_id=world["t"], run_id=run_id)
    before = A11yJourneyRun.objects.get(run_id=run_id).summary

    assert close_unfinished_journey(tenant_id=world["t"], run_id=run_id) == {"closed": False}
    after = A11yJourneyRun.objects.get(run_id=run_id).summary
    assert after == before, "the agent's own accounting is untouched"
    assert "closed_by_platform" not in after

    # A run that is not a journey at all — every other phase in the platform takes this path.
    assert close_unfinished_journey(
        tenant_id=world["t"], run_id="22222222-2222-4222-8222-222222222222") == {"closed": False}


@pytest.mark.django_db
def test_the_journey_phase_is_never_asked_for_a_document_it_does_not_write(world, monkeypatch):
    """Without this branch a journey that walked a whole application perfectly would reach the
    write-completeness gate, be asked for an `a11y_journey` document it was never meant to
    write, and park the run. The same branch the judging pass needed, for the same reason."""
    from orchestration.activities import A11Y_JOURNEY_PHASE, verify_write_completeness_core
    from orchestration.types import AgentRunInput

    assert A11Y_JOURNEY_PHASE == JOURNEY_PHASE == "a11y_journey"
    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    record_step(tenant_id=world["t"], run_id=run_id, number=1, outcome=A11Y_STEP_WALKED)

    out = verify_write_completeness_core(
        AgentRunInput(run_id=run_id, tenant_id=world["t"], project_id=world["p"],
                      work_item_id=world["w"], agent_spec_id="", phase=JOURNEY_PHASE),
        expected_types=[],
    )
    assert out["expected"] == [f"{result['steps']} steps asked"]
    assert out["present"] == ["1 steps reported"]
    # …and the pass is closed on the way past, so it never reads `walking` for ever.
    assert A11yJourneyRun.objects.get(run_id=run_id).status == A11yJourneyRun.Status.COMPLETE


@pytest.mark.django_db
def test_a_journey_blocked_half_way_is_reported_not_failed(world, monkeypatch):
    """The whole point of freezing the step list is to be able to say "three of these were never
    reached". That is an honest, valuable outcome — this check must never turn it into an error.
    """
    from orchestration.activities import verify_write_completeness_core
    from orchestration.types import AgentRunInput

    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    record_step(tenant_id=world["t"], run_id=run_id, number=1, outcome=A11Y_STEP_WALKED)
    record_step(tenant_id=world["t"], run_id=run_id, number=2, outcome=A11Y_STEP_BLOCKED,
                reason="the Continue button cannot be reached with the keyboard")

    out = verify_write_completeness_core(     # no raise — that is the assertion
        AgentRunInput(run_id=run_id, tenant_id=world["t"], project_id=world["p"],
                      work_item_id=world["w"], agent_spec_id="", phase=JOURNEY_PHASE),
        expected_types=[],
    )
    assert out["present"] == ["2 steps reported"]
    summary = A11yJourneyRun.objects.get(run_id=run_id).summary
    assert summary["blocked"][0]["reason"].startswith("the Continue button")
    assert summary["not_reached"], "the steps after the block are never-reached, not passed"


@pytest.mark.django_db
def test_a_failed_run_closes_its_walk_on_the_way_out(world, monkeypatch):
    """The path a crashed agent takes. It never reaches the completeness check above, so the
    closure has to be on both — otherwise exactly the runs that died stay `walking` for ever."""
    from orchestration.activities import fail_run_core
    from orchestration.types import AgentRunInput

    result, _ = _start(world, monkeypatch=monkeypatch)
    run_id = result["run_id"]
    record_step(tenant_id=world["t"], run_id=run_id, number=1, outcome=A11Y_STEP_WALKED)

    fail_run_core(
        AgentRunInput(run_id=run_id, tenant_id=world["t"], project_id=world["p"],
                      work_item_id=world["w"], agent_spec_id="", phase=JOURNEY_PHASE),
        "engine ended abnormally (error_during_execution)")

    row = A11yJourneyRun.objects.get(run_id=run_id)
    assert row.status != A11yJourneyRun.Status.WALKING
    assert "error_during_execution" in row.summary["closed_by_platform"]


def test_the_phase_the_companion_hardcodes_is_the_phase_the_catalog_gives_09d():
    """The companion runs on a developer's machine with no Django, so `guardrails` repeats this
    string rather than importing it. This is what keeps the two honest."""
    from runner.companion.guardrails import BROWSER_PHASES

    from apps.registry.catalog import ACTIVE_AGENT_CATALOG

    agent = next(a for a in ACTIVE_AGENT_CATALOG if a.key == JOURNEY_AGENT_KEY)
    assert agent.phase_label == JOURNEY_PHASE
    assert JOURNEY_PHASE in BROWSER_PHASES, "…and that phase is the one granted a browser"


# ── G6b: starting several journeys, each on a work item of its own ───────────

def _journeys(*refs):
    """N walkable journeys, differing only in the test case they came from."""
    from integrations.types import A11yJourney

    return [A11yJourney(test_ref=ref, title=f"Journey {ref}",
                        steps=tuple(parse_steps(JOURNEY_BODY)), artifact_id=f"a-{ref}")
            for ref in refs]


def _queue_world(world, monkeypatch, journeys, *, skipped=None, over_cap=None, role="qa_lead"):
    """Everything `queue_journeys` reaches, stubbed: the test-case scan, the availability check,
    and a reviewer who is allowed to press the button."""
    from apps.a11y import journey as journey_mod
    from apps.a11y import journeys as journeys_mod
    from apps.tenancy.models import Membership, User

    monkeypatch.setattr(journeys_mod, "journeys_for_project",
                        lambda *a, **k: {"journeys": list(journeys),
                                         "skipped": list(skipped or []),
                                         "over_cap": list(over_cap or [])})
    monkeypatch.setattr(journey_mod, "journey_available", lambda *a, **k: "")
    user = User.objects.create_user(email="aisha@acme.test", name="Aisha", tenant=world["tenant"])
    if role:
        Membership.objects.create(tenant=world["tenant"], project=world["project"],
                                  user=user, role=role)
    return user


def _each_run(world):
    """A trigger that behaves like the real one in the way this slice depends on: a fresh run
    per call, and a REFUSAL when a work item already has one in flight."""
    import uuid

    from apps.runs.models import Run
    from orchestration.trigger import ActiveRunError

    live: set = set()

    def _fn(**kwargs):
        _fn.calls.append(kwargs)
        item = kwargs["work_item_id"]
        if item in live:
            raise ActiveRunError("a run is already in progress for this work item")
        live.add(item)
        spec = AgentSpec.objects.get(tenant=world["tenant"], key=JOURNEY_AGENT_KEY)
        run = Run.objects.create(
            id=uuid.uuid4(), tenant=world["tenant"], agent_spec=spec,
            work_item_id=item, status="running")
        return _Outcome(str(run.id))
    _fn.calls = []
    return _fn


@pytest.mark.django_db
def test_three_journeys_start_three_runs_on_three_work_items(world, monkeypatch):
    """The fix. Every agent run hangs off a work item, and the platform refuses a second run on
    one that is already busy — so sharing a work item would start the first journey and have the
    other two turned away by a rule that was never about them."""
    from apps.a11y.journey import queue_journeys

    user = _queue_world(world, monkeypatch, _journeys("TC-031", "TC-044", "TC-052"))
    trigger = _each_run(world)
    out = queue_journeys(tenant_id=world["t"], project_id=world["p"], base_url=APP_URL,
                         user_id=user.id, trigger=trigger)

    assert [j["name"] for j in out["started"]] == ["TC-031", "TC-044", "TC-052"]
    assert out["refused"] == []
    items = [c["work_item_id"] for c in trigger.calls]
    assert len(set(items)) == 3, "one work item each, or the second and third are refused"
    assert A11yJourneyRun.objects.count() == 3


@pytest.mark.django_db
def test_a_journeys_work_item_never_appears_on_anybodys_board(world, monkeypatch):
    """The judging carrier shipped without this marking and left an 'Accessibility judging' task
    on the user's board after every test run. Marked from the start here, and checked against the
    platform's one definition of a carrier rather than against a copy of the string."""
    from apps.a11y.journey import queue_journeys
    from apps.workitems.models import WorkItem
    from integrations.onboarding import CARRIER_SOURCES, carrier_q

    user = _queue_world(world, monkeypatch, _journeys("TC-031"))
    queue_journeys(tenant_id=world["t"], project_id=world["p"], base_url=APP_URL,
                   user_id=user.id, trigger=_each_run(world))

    carrier = WorkItem.objects.get(external_ref__test_ref="TC-031")
    assert carrier.external_ref["source"] in CARRIER_SOURCES
    # `tc_id` too, and not as a duplicate: it is the key the review console reads to say WHERE a
    # finding came from (G3). Without it a keyboard finding is attributed to "WI-84" — the number
    # of a work item deliberately hidden from every board — instead of to TC-031.
    assert carrier.external_ref["tc_id"] == "TC-031"
    visible = WorkItem.objects.filter(tenant_id=world["t"]).exclude(carrier_q())
    assert carrier.id not in {w.id for w in visible}
    assert world["item"].id in {w.id for w in visible}, "the real story is still there"


@pytest.mark.django_db
def test_two_journeys_from_unstamped_test_cases_do_not_collide(world, monkeypatch):
    """Found by cross-checking the whole path, not by a test failing.

    A test case is only USUALLY stamped with a `TC-031`; `journey_from` leaves the ref blank when
    the producer wrote none. Keying the work item on that ref meant two unstamped journeys shared
    one — so the second was refused as "already being walked" by the first, and the panel showed
    each of them the other's last walk. Keyed on the artifact, which is always there.
    """
    from apps.a11y.journey import queue_journeys, walkable_journeys
    from integrations.types import A11yJourney

    unstamped = [A11yJourney(test_ref="", title=f"Journey {n}", artifact_id=f"art-{n}",
                             steps=tuple(parse_steps(JOURNEY_BODY))) for n in (1, 2)]
    user = _queue_world(world, monkeypatch, unstamped)
    out = queue_journeys(tenant_id=world["t"], project_id=world["p"], base_url=APP_URL,
                         user_id=user.id, trigger=_each_run(world))

    assert len(out["started"]) == 2, "the second is not refused by the first"
    assert out["refused"] == []
    rows = walkable_journeys(world["t"], world["p"])["journeys"]
    assert {r["id"] for r in rows} == {"art-1", "art-2"}
    assert all(r["last_walked"] is not None for r in rows), "each shows its OWN walk"


@pytest.mark.django_db
def test_the_screen_selects_by_the_id_the_list_gave_it(world, monkeypatch):
    """The panel sends the handle back, because it is the only identifier always present."""
    from apps.a11y.journey import queue_journeys, walkable_journeys

    _queue_world(world, monkeypatch, _journeys("TC-031", "TC-044"), role=None)
    rows = walkable_journeys(world["t"], world["p"])["journeys"]
    picked = next(r["id"] for r in rows if r["test_ref"] == "TC-044")

    from apps.tenancy.models import Membership, User

    lead = User.objects.create_user(email="lead@acme.test", name="Lead", tenant=world["tenant"])
    Membership.objects.create(tenant=world["tenant"], project=world["project"],
                              user=lead, role="qa_lead")
    out = queue_journeys(tenant_id=world["t"], project_id=world["p"], base_url=APP_URL,
                         user_id=lead.id, trigger=_each_run(world), test_refs=[picked])
    assert [j["name"] for j in out["started"]] == ["TC-044"]


@pytest.mark.django_db
def test_starting_the_same_journey_twice_says_so_and_does_not_stop_the_others(
        world, monkeypatch):
    """Team decision: refused, in words, not a second browser walking the same path."""
    from apps.a11y.journey import queue_journeys

    user = _queue_world(world, monkeypatch, _journeys("TC-031", "TC-044"))
    trigger = _each_run(world)
    queue_journeys(tenant_id=world["t"], project_id=world["p"], base_url=APP_URL,
                   user_id=user.id, trigger=trigger, test_refs=["TC-031"])
    out = queue_journeys(tenant_id=world["t"], project_id=world["p"], base_url=APP_URL,
                         user_id=user.id, trigger=trigger)

    assert [j["name"] for j in out["started"]] == ["TC-044"], "the other one still starts"
    (again,) = out["refused"]
    assert again["name"] == "TC-031"
    assert "already being walked" in again["reason"]


@pytest.mark.django_db
def test_what_the_cap_left_out_is_named_never_dropped(world, monkeypatch):
    """`journeys_for_project` stops at ten and hands back what it left. That travels out of the
    queue untouched, because a journey silently not run reads exactly like one that passed."""
    from apps.a11y.journey import queue_journeys

    user = _queue_world(world, monkeypatch, _journeys(*[f"TC-{n:03d}" for n in range(10)]),
                        over_cap=["TC-999"])
    out = queue_journeys(tenant_id=world["t"], project_id=world["p"], base_url=APP_URL,
                         user_id=user.id, trigger=_each_run(world))

    assert len(out["started"]) == 10
    assert out["over_cap"] == ["TC-999"]


@pytest.mark.django_db
def test_a_reader_can_look_and_cannot_start(world, monkeypatch):
    from apps.a11y.journey import JourneyRoleError, queue_journeys, walkable_journeys

    user = _queue_world(world, monkeypatch, _journeys("TC-031"), role="engineer")
    with pytest.raises(JourneyRoleError, match="accessibility reviewer"):
        queue_journeys(tenant_id=world["t"], project_id=world["p"], base_url=APP_URL,
                       user_id=user.id, trigger=_each_run(world))
    # …and looking is unaffected: the list is not the thing being gated.
    assert len(walkable_journeys(world["t"], world["p"])["journeys"]) == 1


@pytest.mark.django_db
def test_a_name_this_project_does_not_have_comes_back_named(world, monkeypatch):
    """A stale row on a screen, or a person typing one. Not an error, and not a silence either."""
    from apps.a11y.journey import queue_journeys

    user = _queue_world(world, monkeypatch, _journeys("TC-031"))
    out = queue_journeys(tenant_id=world["t"], project_id=world["p"], base_url=APP_URL,
                         user_id=user.id, trigger=_each_run(world),
                         test_refs=["TC-031", "TC-404"])

    assert [j["name"] for j in out["started"]] == ["TC-031"]
    assert [r["name"] for r in out["refused"]] == ["tc-404"]
    assert 'can be walked in this project' in out["refused"][0]["reason"]


@pytest.mark.django_db
def test_queueing_with_no_address_starts_nothing_and_says_why(world, monkeypatch):
    from apps.a11y.journey import NO_ADDRESS, queue_journeys

    user = _queue_world(world, monkeypatch, _journeys("TC-031"))
    trigger = _each_run(world)
    out = queue_journeys(tenant_id=world["t"], project_id=world["p"], base_url="  ",
                         user_id=user.id, trigger=trigger)
    assert out["started"] == [] and out["reason"] == NO_ADDRESS
    assert trigger.calls == []


@pytest.mark.django_db
def test_the_panel_shows_the_e2e_cases_it_could_not_walk_and_why(world, monkeypatch):
    """A case marked E2E whose steps cannot be read is not the same fact as a project with no
    journeys. Omitting it is how an application with no keyboard coverage comes to look like one
    with no keyboard problems."""
    from apps.a11y.journey import walkable_journeys

    _queue_world(world, monkeypatch, _journeys("TC-031"), skipped=[
        {"artifact_id": "a-9", "title": "TC-077 Checkout", "test_ref": "TC-077",
         "reason": "the test case declares Type: E2E but no steps could be read from it"}])
    out = walkable_journeys(world["t"], world["p"])

    assert [j["test_ref"] for j in out["journeys"]] == ["TC-031"]
    (blocked,) = out["unwalkable"]
    assert blocked["test_ref"] == "TC-077" and "no steps could be read" in blocked["reason"]
    assert out["max_journeys"] == 10


@pytest.mark.django_db
def test_the_list_says_when_each_journey_was_last_walked(world, monkeypatch):
    from apps.a11y.journey import queue_journeys, walkable_journeys

    user = _queue_world(world, monkeypatch, _journeys("TC-031", "TC-044"))
    queue_journeys(tenant_id=world["t"], project_id=world["p"], base_url=APP_URL,
                   user_id=user.id, trigger=_each_run(world), test_refs=["TC-031"])

    rows = {j["test_ref"]: j for j in walkable_journeys(world["t"], world["p"])["journeys"]}
    assert rows["TC-031"]["last_walked"] is not None
    assert rows["TC-031"]["status"] == A11yJourneyRun.Status.WALKING
    assert rows["TC-044"]["last_walked"] is None, "never walked reads as never walked"


@pytest.mark.django_db
def test_the_address_is_suggested_from_the_last_audit_then_the_repository(world):
    """One answer to "where is this application", never two that can disagree."""
    from apps.a11y.journey import suggested_address
    from apps.a11y.models import A11yBaselineAudit
    from apps.projects.models import Repository

    # Nothing known at all: it says what to go and set rather than inventing an address.
    empty = suggested_address(world["t"], world["p"])
    assert empty.url == "" and "no application address on record" in empty.reason

    Repository.objects.create(tenant=world["tenant"], project=world["project"], name="acme/web",
                              is_default=True, preview_url="http://127.0.0.1:3000")
    from_repo = suggested_address(world["t"], world["p"])
    assert from_repo.url == "http://127.0.0.1:3000" and "acme/web" in from_repo.source

    # An audit still running is not "your last audit" yet (recon 2026-10-10, finding 9).
    running = A11yBaselineAudit.objects.create(tenant=world["tenant"], project=world["project"],
                                               base_url="http://localhost:4180/", routes=["/"])
    assert suggested_address(world["t"], world["p"]).url == "http://127.0.0.1:3000"
    running.status = A11yBaselineAudit.Status.COMPLETE
    running.save(update_fields=["status"])
    from_audit = suggested_address(world["t"], world["p"])
    assert from_audit.url == "http://localhost:4180", "the audit wins, and the slash is trimmed"
    assert from_audit.source == "your last audit"


@pytest.mark.django_db
def test_a_test_case_stamped_as_something_else_is_never_opened(world):
    """G6b's cost fix. A project with ninety test cases and three journeys used to read all
    ninety out of the object store to find the three."""
    from mcp_platform_state import tools

    from apps.a11y.journeys import journeys_for_project
    from apps.registry.models import Artifact

    opened = []

    def _spy(tenant_id, artifact_id, object_store=None):
        opened.append(artifact_id)
        return {"body": JOURNEY_BODY}

    for i in range(3):
        Artifact.objects.create(
            tenant=world["tenant"], project=world["project"], phase="testing", type="test_case",
            title=f"TC-{i:03d} Functional", sor="internal", content_hash=f"h{i}",
            external_ref={"type": "Functional", "tc_id": f"TC-{i:03d}"})
    journey = Artifact.objects.create(
        tenant=world["tenant"], project=world["project"], phase="testing", type="test_case",
        title="TC-031 Checkout", sor="internal", content_hash="h9",
        external_ref={"type": "E2E", "tc_id": "TC-031"})
    unstamped = Artifact.objects.create(
        tenant=world["tenant"], project=world["project"], phase="testing", type="test_case",
        title="TC-050 Unstamped", sor="internal", content_hash="h8", external_ref={})

    original = tools.get_artifact_body
    tools.get_artifact_body = _spy
    try:
        found = journeys_for_project(world["t"], world["p"])
    finally:
        tools.get_artifact_body = original

    assert sorted(opened) == sorted([str(journey.id), str(unstamped.id)]), (
        "the three stamped Functional cases were never read")
    assert len(found["journeys"]) == 2, "the E2E one and the unstamped one that turned out to be"


# ── tenant isolation, at the database ────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_rls_hides_one_tenants_journeys_from_another():
    """Proven on a connection opened as the non-superuser app role — the Django test connection
    is the privileged migration role and bypasses RLS entirely.

    The step table is the most legible row in the whole accessibility schema: a journey's steps
    are a written description of how a product is used, lifted verbatim from the client's own
    test case. One tenant reading another's would hand over the flow of an unreleased product
    in plain English.
    """
    import psycopg
    from django.conf import settings
    from django.db import connection

    from apps.a11y.models import A11yJourneyRun, A11yJourneyStepResult

    for name, secret in (("A", "Open /A-secret and pay"), ("B", "Open /B-secret and pay")):
        tenant = Tenant.objects.create(name=name)
        project = Project.objects.create(tenant=tenant, name="p")
        run = A11yJourneyRun.objects.create(
            tenant=tenant, project=project, test_ref="TC-1", title=name,
            steps=[{"number": 1, "text": secret, "route": "/x"}])
        A11yJourneyStepResult.objects.create(
            tenant=tenant, project=project, journey_run=run, number=1,
            text=secret, route="/x", outcome=A11Y_STEP_WALKED)
    first = Tenant.objects.get(name="A")

    sd = connection.settings_dict
    with connection.cursor() as cur:
        cur.execute("SELECT current_database()")
        dbname = cur.fetchone()[0]
    raw = psycopg.connect(
        host=sd["HOST"], port=sd["PORT"], dbname=dbname,
        user=settings.APP_DB_USER, password=settings.APP_DB_PASSWORD, autocommit=True,
    )
    try:
        with raw.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [str(first.id)])
            cur.execute("SELECT text FROM a11y_a11yjourneystepresult")
            assert cur.fetchall() == [("Open /A-secret and pay",)]
            cur.execute("SELECT title FROM a11y_a11yjourneyrun")
            assert cur.fetchall() == [("A",)]

            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [""])
            for table in ("a11y_a11yjourneyrun", "a11y_a11yjourneystepresult"):
                cur.execute(f"SELECT count(*) FROM {table}")
                assert cur.fetchone()[0] == 0     # no tenant context -> fail closed
    finally:
        raw.close()
