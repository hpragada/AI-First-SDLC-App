"""QA-21 — the keyboard agent's findings reach the bug loop and the review queue.

Against the task's acceptance criteria:

  AC1  an agentic failure opens a defect with the right severity
  AC2  an uncertain agentic finding goes to the SME queue, and opens no defect
  AC3  the same problem found by the agent and a static check is ONE defect, not two
  AC4  routing and de-duplication covered, ≥ 90% on new code

**The three sharpest things in this file.**

  * `test_a_group_closes_only_when_every_member_has_resolved` — one of two checks going quiet
    while the other still fails is not a fix. Closing on the first silence would tell a team a
    live Level A defect had been dealt with.

  * `test_a_measurement_never_lets_the_journey_close_a_scanner_finding` — QA-21 widens
    `_resolve_walked` to cover `rule` rows, because a measured journey finding IS one. That
    widening must not reopen D-A11Y-49: a keyboard walk still has nothing to say about the page
    scan, and the checker filter is what keeps it out. Asserted in both directions.

  * `test_a_reading_that_proves_nothing_leaves_the_verdict_alone` — the override runs ONE way.
    A visible outline does not prove the indicator is *sufficient*, and a live region does not
    prove anything is announced into it. Those are the judgment halves and they stay with the
    agent; a measurement that only ever fails is the whole reason it can be trusted at all.
"""
from __future__ import annotations

import pytest

from apps.a11y.defects import record_a11y_findings
from apps.a11y.findings import fingerprint, record_run_findings, review_queue
from apps.a11y.journey import (
    JOURNEY_AGENT_KEY,
    finish_journey,
    record_journey_finding,
    record_step,
    start_journey_check,
)
from apps.a11y.journey_rules import (
    MEASURED_CHECKERS,
    RULE_NO_LIVE_REGION,
    RULE_OUTLINE_SUPPRESSED,
    focus_indicator_failure,
    live_region_failure,
    rule_failures_for,
)
from apps.a11y.journeys import parse_preconditions, parse_steps
from apps.a11y.models import A11yFinding, WcagCriterion
from apps.a11y.report import SOURCE_RULE, MergedReport, ReportRow
from apps.a11y.triage import TRIAGE_FAILURE, TRIAGE_REVIEW
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from integrations.types import A11Y_FAIL, A11Y_PASS, A11Y_STEP_WALKED, A11Y_UNCERTAIN

RUN_ID = "22222222-2222-4222-8222-222222222222"
#: A second pass is a second run. Reusing one id would leave the first pass's findings carrying
#: `last_seen_run = this run`, so the second pass would treat them as reported again and could
#: never resolve anything — a test that passes while proving nothing.
RUN_ID_2 = "33333333-3333-4333-8333-333333333333"

JOURNEY_BODY = """## TC-031: Complete Registration to First Expense
**Type:** E2E

### Test Steps
1. Navigate to /register and create an account
2. Log in and open /dashboard
3. Add an expense of 12.50 from /expenses/new
"""

#: The two criteria the journey checks reach that a page scan also reaches, and the two that
#: carry a measurement. Seeded so severity comes from the standard rather than the fallback —
#: an "A" criterion must open a Critical defect, and asserting that needs the level to be real.
LEVELS = {"2.1.1": "A", "2.1.2": "A", "2.4.7": "AA", "4.1.3": "AA"}


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="SpendLog")
    AgentSpec.objects.create(tenant=tenant, key=JOURNEY_AGENT_KEY, semver="1.0.0")
    item = WorkItem.objects.create(tenant=tenant, project=project, type=WorkItem.Type.STORY,
                                   title="Log an expense")
    for number, level in LEVELS.items():
        WcagCriterion.objects.get_or_create(
            version="2.2", number=number,
            defaults={"handle": number, "level": level, "slug": number, "text": "…"})
    return {"t": str(tenant.id), "p": str(project.id), "w": str(item.id),
            "tenant": tenant, "project": project, "item": item}


class _Outcome:
    def __init__(self, run_id):
        self.run_id = run_id


def _trigger(world, run_id=RUN_ID):
    """Stands in for `trigger_phase`. Never reaches Temporal — an unpatched trigger here would
    start a REAL workflow on the team's shared server — and creates the `Run` row the real
    dispatch would, because `A11yJourneyRun.run` is a genuine foreign key."""
    from apps.runs.models import Run

    def _fn(**kwargs):
        spec = AgentSpec.objects.get(tenant=world["tenant"], key=JOURNEY_AGENT_KEY)
        Run.objects.get_or_create(
            id=run_id, defaults={"tenant": world["tenant"], "agent_spec": spec,
                                 "work_item": world["item"], "status": "running"})
        return _Outcome(run_id)
    return _fn


def _start(world, monkeypatch, run_id=RUN_ID):
    from apps.a11y import journey as journey_mod
    from apps.a11y import journeys as journeys_mod
    from integrations.types import A11yJourney

    parsed = A11yJourney(test_ref="TC-031", title="Registration to first expense",
                         steps=tuple(parse_steps(JOURNEY_BODY)),
                         preconditions=tuple(parse_preconditions(JOURNEY_BODY)),
                         artifact_id="a-1")
    monkeypatch.setattr(journeys_mod, "journeys_for_project",
                        lambda *a, **k: {"journeys": [parsed], "skipped": [], "over_cap": []})
    monkeypatch.setattr(journey_mod, "journey_available", lambda *a, **k: "")
    start_journey_check(tenant_id=world["t"], project_id=world["p"],
                        work_item_id=world["w"], base_url="http://127.0.0.1:5173",
                        trigger=_trigger(world, run_id))


def _report(world, **over):
    """A static finding, as a page scan would produce it — no checker, source `rule`."""
    base = {"source": SOURCE_RULE, "outcome": TRIAGE_FAILURE, "criteria": ("2.1.1",),
            "route": "/dashboard", "selector": "div.scroll-area", "checker": "",
            "evidence": "the region scrolls but is not focusable",
            "rule_id": "scrollable-region-focusable", "confidence": None}
    base.update(over)
    return record_run_findings(
        tenant_id=world["t"], project_id=world["p"], run_id=None,
        report=MergedReport(rows=[ReportRow(**base)], routes=["/dashboard"], unjudged=[]))


def _judge(world, **over):
    base = {"tenant_id": world["t"], "run_id": RUN_ID, "step": 2, "checker": "keyboard",
            "verdict": A11Y_FAIL, "confidence": 0.95,
            "evidence": "tabbing never reached the scrolling region",
            "suggested_fix": "give the region tabindex=0", "route": "/dashboard",
            "selector": "div.scroll-area"}
    base.update(over)
    return record_journey_finding(**base)


def _finish(world, run_id=RUN_ID):
    return finish_journey(tenant_id=world["t"], run_id=run_id)


def _a11y_defects(world):
    return [item for item in WorkItem.objects.filter(
        tenant_id=world["t"], type=WorkItem.Type.DEFECT).order_by("title")
        if (item.external_ref or {}).get("a11y_finding")]


# ── the two measurements, as pure rules (D-A11Y-72, closed here) ─────────────

def test_the_registry_and_the_code_agree_on_which_checks_can_be_measured():
    """The criterion ownership registry names these two secondary checks independently of this
    build — *"Rule detects outline:none"* and *"Rule detects aria-live presence"*. If a future
    edit adds a measurable check to one and not the other, this is where it shows up."""
    import json
    import pathlib

    data = json.loads(
        (pathlib.Path(__file__).resolve().parents[1] / "apps/a11y/data/ownership.json")
        .read_text(encoding="utf-8"))
    with_rule = {row["number"] for row in data["criteria"]
                 if any(check["engine"] == "rule" for check in row["secondary_checks"])}
    assert set(MEASURED_CHECKERS.values()) <= with_rule


def test_an_outline_switched_off_with_nothing_in_its_place_is_a_proven_failure():
    found = focus_indicator_failure(
        route="/dashboard", selector="button.save",
        measurement={"outline_style": "none", "outline_width": "0px", "box_shadow": "none"})
    assert found is not None
    assert found.criterion == "2.4.7"
    assert found.rule_id == RULE_OUTLINE_SUPPRESSED
    assert found.key == ("/dashboard", "button.save", "2.4.7")


def test_a_zero_width_outline_proves_it_too():
    """Two ways to switch an outline off, and a page can use either."""
    assert focus_indicator_failure(
        route="/x", selector="a", measurement={"outline_style": "solid", "outline_width": "0px",
                                               "box_shadow": "none"}) is not None


def test_a_design_system_that_replaced_the_outline_with_a_shadow_is_not_a_failure():
    """The single most common custom focus style there is. Firing here would hand a team a
    Level AA defect they cannot argue with, for a focus ring that works perfectly."""
    assert focus_indicator_failure(
        route="/x", selector="a",
        measurement={"outline_style": "none", "outline_width": "0px",
                     "box_shadow": "0 0 0 3px #2563eb"}) is None


def test_a_reading_we_did_not_get_proves_nothing():
    """Absent, empty, malformed and half-reported all mean the same thing: no ruling. The
    alternative is inventing a Level AA failure out of a probe that did not run."""
    for measurement in (None, {}, "outline: none", [],
                        {"outline_style": "none"},                       # no shadow reported
                        {"outline_width": "", "box_shadow": "none"}):    # no width reported
        assert focus_indicator_failure(route="/x", selector="a",
                                       measurement=measurement) is None


def test_a_screen_with_no_live_region_at_all_is_a_proven_failure():
    found = live_region_failure(route="/dashboard", selector="step:2",
                                measurement={"live_region_count": 0})
    assert found is not None
    assert found.criterion == "4.1.3"
    assert found.rule_id == RULE_NO_LIVE_REGION


def test_a_live_region_existing_proves_nothing_at_all():
    """Counting is not judging. Whether the right text reaches the region at the right moment
    is the whole of 4.1.3, and it stays with the agent."""
    assert live_region_failure(route="/x", selector="s",
                               measurement={"live_region_count": 3}) is None
    assert live_region_failure(route="/x", selector="s",
                               measurement={"live_region_count": "lots"}) is None
    assert live_region_failure(route="/x", selector="s", measurement={}) is None


def test_a_measurement_is_only_applied_to_the_check_it_belongs_to():
    """A live-region count sent alongside a focus verdict proves nothing about 2.4.7, and
    stretching it to cover a criterion it does not measure is how a measurement becomes a
    guess with a rule id on it."""
    assert rule_failures_for(checker="focus_visible", route="/x", selector="a",
                             measurement={"live_region_count": 0}) == ()
    assert rule_failures_for(checker="trap", route="/x", selector="a",
                             measurement={"outline_style": "none", "outline_width": "0",
                                          "box_shadow": "none"}) == ()


def test_what_the_rules_hand_to_triage_is_re_readable():
    """`triage()` refuses a one-shot iterator, and for a good reason — a drained generator
    would silently switch the override off for every judgment after the first."""
    proven = rule_failures_for(checker="status", route="/x", selector="s",
                               measurement={"live_region_count": 0})
    assert isinstance(proven, tuple)
    assert len(list(proven)) == len(list(proven)) == 1


# ── the measurement inside a real journey pass ───────────────────────────────

def test_a_measurement_overrules_the_agent_saying_it_is_fine(world, monkeypatch):
    """QA-06 rule 2, reaching the journey checks for the first time. The agent looked at the
    focus ring and called it fine; the browser says the outline is off and nothing replaced
    it. The measurement stands."""
    _start(world, monkeypatch)
    out = _judge(world, step=2, checker="focus_visible", verdict=A11Y_PASS, confidence=0.99,
                 evidence="the focus ring looked fine to me", suggested_fix="",
                 selector="button.save",
                 measurement={"outline_style": "none", "outline_width": "0px",
                              "box_shadow": "none"})
    assert out["outcome"] == TRIAGE_FAILURE
    assert out["measured"] is True

    row = A11yFinding.objects.get(tenant_id=world["t"], id=out["finding_id"])
    assert row.source == A11yFinding.Source.RULE
    assert row.rule_id == RULE_OUTLINE_SUPPRESSED
    assert row.verdict == A11Y_PASS          # what the AI said is still recorded, unchanged
    assert row.confidence is None            # a measurement has no confidence to doubt
    assert "outline" in row.evidence


def test_a_measurement_rescues_a_finding_the_confidence_gate_would_have_parked(world,
                                                                              monkeypatch):
    """The agent was only 30% sure there was no live region. The count says there is not one,
    and a count is not a thing to be 30% sure about."""
    _start(world, monkeypatch)
    out = _judge(world, step=2, checker="status", verdict=A11Y_FAIL, confidence=0.30,
                 evidence="I think the toast is not announced", selector="",
                 measurement={"live_region_count": 0})
    assert out["outcome"] == TRIAGE_FAILURE
    assert out["measured"] is True


def test_a_reading_that_proves_nothing_leaves_the_verdict_alone(world, monkeypatch):
    """The override runs ONE way. A visible outline is not proof of a *sufficient* indicator,
    so the agent's `uncertain` survives intact and still reaches a person."""
    _start(world, monkeypatch)
    out = _judge(world, step=2, checker="focus_visible", verdict=A11Y_UNCERTAIN, confidence=0.0,
                 evidence="a 1px grey ring — I cannot tell if that is enough",
                 suggested_fix="", selector="button.save",
                 measurement={"outline_style": "solid", "outline_width": "1px",
                              "box_shadow": "none"})
    assert out["outcome"] == TRIAGE_REVIEW
    assert out["measured"] is False
    row = A11yFinding.objects.get(tenant_id=world["t"], id=out["finding_id"])
    assert row.source == A11yFinding.Source.AGENTIC
    assert row.confidence == 0.0


def test_a_measured_finding_still_resolves_when_the_journey_walks_it_clean(world, monkeypatch):
    """QA-21 makes a journey row `rule`-sourced when a measurement decided it, so the
    resolution query had to widen to match. If it had not, a fixed focus ring would leave its
    defect open for ever with nothing able to close it."""
    _start(world, monkeypatch)
    record_step(tenant_id=world["t"], run_id=RUN_ID, number=2,
                outcome=A11Y_STEP_WALKED)
    _judge(world, step=2, checker="focus_visible", verdict=A11Y_PASS, confidence=0.99,
           evidence="looked fine", suggested_fix="", selector="button.save",
           measurement={"outline_style": "none", "outline_width": "0px",
                        "box_shadow": "none"})
    _finish(world)
    assert A11yFinding.objects.get(tenant_id=world["t"], checker="focus_visible").status == \
        A11yFinding.Status.OPEN

    # Second pass, a second run: the ring is back, so nothing is reported for it.
    _start(world, monkeypatch, RUN_ID_2)
    record_step(tenant_id=world["t"], run_id=RUN_ID_2, number=2, outcome=A11Y_STEP_WALKED)
    _finish(world, RUN_ID_2)
    assert A11yFinding.objects.get(tenant_id=world["t"], checker="focus_visible").status == \
        A11yFinding.Status.RESOLVED


def test_a_measurement_never_lets_the_journey_close_a_scanner_finding(world, monkeypatch):
    """D-A11Y-49, held while the source filter widens. The journey now resolves `rule` rows —
    but only ones carrying a journey checker. A page scan's row has no checker at all, so it
    cannot be reached, and a keyboard walk of `/dashboard` still says nothing about it."""
    _report(world)                                    # a scanner finding on /dashboard
    _start(world, monkeypatch)
    record_step(tenant_id=world["t"], run_id=RUN_ID, number=2,
                outcome=A11Y_STEP_WALKED)
    _judge(world, step=2, checker="focus_visible", verdict=A11Y_PASS, confidence=0.99,
           evidence="fine", suggested_fix="", selector="button.save",
           measurement={"outline_style": "none", "outline_width": "0", "box_shadow": "none"})
    _finish(world)

    _start(world, monkeypatch, RUN_ID_2)
    record_step(tenant_id=world["t"], run_id=RUN_ID_2, number=2, outcome=A11Y_STEP_WALKED)
    _finish(world, RUN_ID_2)
    scanner = A11yFinding.objects.get(tenant_id=world["t"], checker="")
    assert scanner.status == A11yFinding.Status.OPEN
    # …and the journey's own row DID resolve, so this is not passing by doing nothing.
    assert A11yFinding.objects.get(tenant_id=world["t"], checker="focus_visible").status == \
        A11yFinding.Status.RESOLVED


def test_a_page_scan_never_closes_a_keyboard_finding(world, monkeypatch):
    """**D-A11Y-71 in the opposite — and more dangerous — direction, found by QA-21's own
    tests.** `record_run_findings` closes findings by absence across the routes a run covered.
    A journey check is never in that report, because a captured page cannot answer "does
    tabbing ever reach this region". So a perfectly ordinary AI pass over `/dashboard` would
    have marked every keyboard finding on `/dashboard` as fixed — and a static pass happens far
    more often than a journey does, so it would have happened first and often.

    Coverage is by screen *and* by kind. Only a journey pass that walked the route may close
    one of these."""
    _start(world, monkeypatch)
    record_step(tenant_id=world["t"], run_id=RUN_ID, number=2, outcome=A11Y_STEP_WALKED)
    _judge(world, checker="trap", criteria=("2.1.2",), selector="div.picker")
    _finish(world)

    # A later static run over the same screen that says nothing about the picker.
    _report(world)
    assert A11yFinding.objects.get(tenant_id=world["t"], checker="trap").status == \
        A11yFinding.Status.OPEN
    # …while a static finding it genuinely did cover still resolves, so this is not passing by
    # having switched resolution off.
    _report(world, criteria=("2.1.1",), selector="div.other", evidence="…")
    assert A11yFinding.objects.get(
        tenant_id=world["t"], checker="", selector="div.scroll-area").status == \
        A11yFinding.Status.RESOLVED


# ── AC1 / AC2: the routing ───────────────────────────────────────────────────

def test_an_agentic_failure_opens_a_defect_with_the_right_severity(world, monkeypatch):
    """AC1. Before QA-21 the agent could prove a Level A keyboard trap and no ticket existed."""
    _start(world, monkeypatch)
    record_step(tenant_id=world["t"], run_id=RUN_ID, number=2,
                outcome=A11Y_STEP_WALKED)
    _judge(world, checker="trap", criteria=("2.1.2",),
           evidence="focus cycled inside the date picker; Escape did nothing")
    out = _finish(world)

    defects = _a11y_defects(world)
    assert len(defects) == 1
    assert out["defects"]["opened"] == [str(defects[0].id)]
    ref = defects[0].external_ref
    assert ref["severity"] == "critical"          # 2.1.2 is Level A
    assert ref["criterion"] == "2.1.2"
    assert ref["found_by_sources"] == ["agentic"]
    assert "2.1.2" in defects[0].title
    assert "the keyboard journey agent" in defects[0].description


def test_an_uncertain_agentic_finding_goes_to_the_reviewer_and_opens_nothing(world,
                                                                            monkeypatch):
    """AC2. The queue is source-agnostic by construction — it asks what needs deciding, not
    who raised it — so this asserts the property rather than new plumbing."""
    _start(world, monkeypatch)
    record_step(tenant_id=world["t"], run_id=RUN_ID, number=2,
                outcome=A11Y_STEP_WALKED)
    out = _judge(world, checker="focus_order", criteria=("2.4.3",), verdict=A11Y_UNCERTAIN,
                 confidence=0.0, evidence="the order is odd but may still be meaningful",
                 suggested_fix="")
    assert out["outcome"] == TRIAGE_REVIEW
    _finish(world)

    queued = review_queue(world["t"], world["p"])
    assert [f.checker for f in queued] == ["focus_order"]
    assert _a11y_defects(world) == []


def test_a_journey_that_walked_nothing_opens_no_defects(world, monkeypatch):
    """The loopback reconciles the whole project ledger. Running it after a journey that
    tested nothing would open tickets from other runs' findings and hang them off a journey
    that never started — and report them as this journey's result."""
    _report(world)                                    # a real, blocking, static finding
    _start(world, monkeypatch)
    out = _finish(world)
    assert out["status"] == "failed"
    assert "defects" not in out
    assert _a11y_defects(world) == []


def test_a_loopback_that_falls_over_does_not_lose_the_journey(world, monkeypatch):
    """A real browser walked a real application to produce this. Losing it because a ticket
    could not be written is the wrong way round — the same trade `aipass._publish` makes."""
    _start(world, monkeypatch)
    record_step(tenant_id=world["t"], run_id=RUN_ID, number=2,
                outcome=A11Y_STEP_WALKED)
    _judge(world, checker="trap", criteria=("2.1.2",))

    from apps.a11y import defects as defects_mod

    def _boom(**kwargs):
        raise RuntimeError("the tracker is down")
    monkeypatch.setattr(defects_mod, "record_a11y_findings", _boom)

    out = _finish(world)
    assert out["status"] == "complete"
    assert out["walked"] == 1
    assert out["defects"] == {"error": "the tracker is down"}


# ── AC3: one problem, one ticket ─────────────────────────────────────────────

def _both(world, monkeypatch):
    """The same broken element, seen by the page scan and by the keyboard agent."""
    _report(world)
    _start(world, monkeypatch)
    record_step(tenant_id=world["t"], run_id=RUN_ID, number=2,
                outcome=A11Y_STEP_WALKED)
    _judge(world, checker="keyboard", criteria=("2.1.1",))
    return _finish(world)


def test_the_same_problem_found_twice_is_one_defect(world, monkeypatch):
    """AC3. 2.1.1 is the one criterion where this collides today — axe covers it with
    `scrollable-region-focusable`, and it is exactly the sort of thing a keyboard walk also
    trips over. Two ledger rows, because the checker is part of a finding's identity and
    QA-10 grades a named checker on its own record. One ticket, because it is one fix."""
    _both(world, monkeypatch)

    rows = A11yFinding.objects.filter(tenant_id=world["t"], criterion="2.1.1")
    assert rows.count() == 2
    assert {r.checker for r in rows} == {"", "keyboard"}

    defects = _a11y_defects(world)
    assert len(defects) == 1


def test_the_measurement_owns_the_ticket_and_names_the_other_finder(world, monkeypatch):
    """A developer opening the ticket should read what was proven, not what was judged — and
    should still be told the keyboard agent found it independently, because that is the
    strongest thing that can be said about an accessibility defect."""
    _both(world, monkeypatch)
    ref = _a11y_defects(world)[0].external_ref

    scanner = A11yFinding.objects.get(tenant_id=world["t"], checker="")
    agent = A11yFinding.objects.get(tenant_id=world["t"], checker="keyboard")
    assert ref["a11y_finding"] == scanner.fingerprint
    assert ref["also_found_by"] == [agent.fingerprint]
    assert ref["found_by_sources"] == ["agentic", "rule"]

    description = _a11y_defects(world)[0].description
    assert "found by the rule scanner" in description
    assert "Also found independently by: the keyboard journey agent" in description
    # The measurement carries no suggested fix; the agent's is borrowed rather than lost.
    assert "tabindex=0" in description


def test_a_group_closes_only_when_every_member_has_resolved(world, monkeypatch):
    """One check going quiet is not a fix. Closing here would tell a team a live Level A
    defect had been dealt with, on the strength of the *other* check still failing."""
    _both(world, monkeypatch)
    defect = _a11y_defects(world)[0]

    A11yFinding.objects.filter(tenant_id=world["t"], checker="").update(
        status=A11yFinding.Status.RESOLVED)
    record_a11y_findings(tenant_id=world["t"], project_id=world["p"])
    defect.refresh_from_db()
    assert defect.state != WorkItem.State.DONE

    A11yFinding.objects.filter(tenant_id=world["t"], checker="keyboard").update(
        status=A11yFinding.Status.RESOLVED)
    record_a11y_findings(tenant_id=world["t"], project_id=world["p"])
    defect.refresh_from_db()
    assert defect.state == WorkItem.State.DONE


def test_the_ticket_changes_hands_without_duplicating(world, monkeypatch):
    """A defect opened by the agent alone, before the scanner ever saw the element. When the
    scan arrives the measurement takes the ticket over — the SAME ticket, re-stamped, because
    a second one would give a developer two tickets for one fix."""
    _start(world, monkeypatch)
    record_step(tenant_id=world["t"], run_id=RUN_ID, number=2,
                outcome=A11Y_STEP_WALKED)
    _judge(world, checker="keyboard", criteria=("2.1.1",))
    _finish(world)
    first = _a11y_defects(world)
    assert len(first) == 1
    assert first[0].external_ref["also_found_by"] == []

    _report(world)
    record_a11y_findings(tenant_id=world["t"], project_id=world["p"])
    after = _a11y_defects(world)
    assert len(after) == 1
    assert after[0].id == first[0].id
    assert after[0].external_ref["a11y_finding"] != first[0].external_ref["a11y_finding"]
    assert first[0].external_ref["a11y_finding"] in after[0].external_ref["also_found_by"]


def test_a_defect_from_before_grouping_existed_is_recognised_not_duplicated(world):
    """Every defect already in a client's tracker was written with an owner and no group.
    Reading the group from the ticket rather than recomputing it is what stops this build
    opening a second ticket for every accessibility defect that already exists."""
    _report(world)
    record_a11y_findings(tenant_id=world["t"], project_id=world["p"])
    defect = _a11y_defects(world)[0]
    ref = dict(defect.external_ref)
    ref.pop("also_found_by")                          # the pre-QA-21 shape
    ref.pop("found_by_sources")
    WorkItem.objects.filter(id=defect.id).update(external_ref=ref)

    record_a11y_findings(tenant_id=world["t"], project_id=world["p"])
    assert [d.id for d in _a11y_defects(world)] == [defect.id]


def test_two_different_elements_are_never_one_ticket(world, monkeypatch):
    """The grouping is `(route, selector, criterion)` and nothing looser. Collapsing on route
    and criterion alone would hide a second broken element behind the first."""
    _report(world)
    _start(world, monkeypatch)
    record_step(tenant_id=world["t"], run_id=RUN_ID, number=2,
                outcome=A11Y_STEP_WALKED)
    _judge(world, checker="keyboard", criteria=("2.1.1",), selector="div.other-region")
    _finish(world)
    assert len(_a11y_defects(world)) == 2


def test_one_element_failing_two_criteria_is_still_two_tickets(world, monkeypatch):
    """Two criteria are two fixes and two conformance failures, whatever the element."""
    _report(world)
    _start(world, monkeypatch)
    record_step(tenant_id=world["t"], run_id=RUN_ID, number=2,
                outcome=A11Y_STEP_WALKED)
    _judge(world, checker="trap", criteria=("2.1.2",))
    _finish(world)
    assert len(_a11y_defects(world)) == 2


def test_the_fix_order_counts_tickets_not_rows(world, monkeypatch):
    """QA-18 writes the position onto the ticket, where a tracker cannot re-derive it. If a
    problem found twice took two places, every ticket below it would carry a number that does
    not match its own place in the list a person reads."""
    _report(world)
    _report(world, criteria=("2.1.2",), selector="div.picker",
            evidence="focus cannot leave the picker")
    _start(world, monkeypatch)
    record_step(tenant_id=world["t"], run_id=RUN_ID, number=2,
                outcome=A11Y_STEP_WALKED)
    _judge(world, checker="keyboard", criteria=("2.1.1",))
    _finish(world)

    defects = _a11y_defects(world)
    assert len(defects) == 2
    assert sorted(d.external_ref["priority"] for d in defects) == [1, 2]


def test_one_tenants_journey_defects_never_reach_another(world, monkeypatch):
    """The loopback is the first thing in this chain that writes work items, which is the row
    a second tenant would most notice appearing in their backlog."""
    other = Tenant.objects.create(name="Other")
    other_project = Project.objects.create(tenant=other, name="Theirs")
    _both(world, monkeypatch)

    assert len(_a11y_defects(world)) == 1
    out = record_a11y_findings(tenant_id=str(other.id), project_id=str(other_project.id))
    assert out["opened"] == [] and out["closed"] == []
    assert WorkItem.objects.filter(tenant_id=str(other.id),
                                   type=WorkItem.Type.DEFECT).count() == 0


def test_the_group_key_is_the_finding_identity_minus_the_checker(world):
    """Stated as a test because it is the whole design in one line: the group key is exactly
    `A11yRuleFailure.key`, so "the same element failing the same criterion" means one thing in
    triage, in the merge and in the tracker."""
    from apps.a11y.defects import _group_key
    from integrations.types import A11yRuleFailure

    _report(world)
    row = A11yFinding.objects.get(tenant_id=world["t"], checker="")
    failure = A11yRuleFailure(criterion=row.criterion, selector=row.selector, route=row.route)
    assert _group_key(row) == failure.key
    assert fingerprint(route=row.route, selector=row.selector, criterion=row.criterion,
                       checker="keyboard") != row.fingerprint
