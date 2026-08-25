"""QA-22 — the keyboard agent's findings never stop anyone's work.

Against the task's acceptance criteria:

  AC1  a journey failure at any confidence does not block the gate
  AC2  a journey `uncertain` does not block either, and is not called an incomplete run
  AC3  the finding is still recorded, reported, ranked and ticketed — advisory ≠ invisible
  AC4  a static failure blocks exactly as it does today
  AC5  no setting, flag or stored record makes a journey check blocking
  AC6  a project that blocks on nothing does not block on accessibility at all

**There were two ways in, and only one was obvious.** The defect path is the one the task was
written about. The second is `unanswered_checks`, and it was a live bug: the word `uncertain`
meant "nobody answered" to the gate and "I looked and cannot tell" to the journey agent, so the
consequence ran backwards — an agent sure about a trap blocked through the first path, and an
agent *honest about not being sure* blocked through the second. Both are tested here, and both
are tested in the negative as well: an element check's `uncertain` must still block, or the fix
has reached further than it should.

**The other rule worth naming** is `test_the_scanner_still_blocks_when_the_agent_agrees`. A
ticket is advisory only when EVERY finding behind it is. The page scanner measuring a still page
blocks on its own merits, and the keyboard agent happening to agree cannot take that away.
"""
from __future__ import annotations

import pytest

from apps.a11y.backlog import prioritised
from apps.a11y.defects import record_a11y_findings
from apps.a11y.findings import fingerprint, record_run_findings
from apps.a11y.models import A11yFinding, A11yScreenScan, WcagCriterion
from apps.a11y.policy import (
    ADVISORY_CHECKERS,
    A11yPolicyError,
    describe_policy,
    is_advisory,
    validate_policy,
)
from apps.a11y.report import SOURCE_RULE, MergedReport, ReportRow
from apps.a11y.triage import TRIAGE_FAILURE
from apps.gates.a11ygate import (
    a11y_condition,
    advisory_a11y_defects,
    open_a11y_defects,
    unanswered_checks,
)
from apps.gates.a11ygate import evaluate as evaluate_a11y
from apps.gates.conditions import ConditionContext
from apps.projects.models import Project, ProjectProfile
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from integrations.types import (
    A11Y_CHECKER_CRITERIA,
    A11Y_FAIL,
    A11Y_JOURNEY_CRITERIA,
    A11Y_UNCERTAIN,
)

LEVELS = {"1.1.1": "A", "2.1.1": "A", "2.1.2": "A", "2.4.7": "AA"}


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="SpendLog")
    story = WorkItem.objects.create(tenant=tenant, project=project, type=WorkItem.Type.STORY,
                                    title="Checkout")
    spec = AgentSpec.objects.create(tenant=tenant, key="09b_test_automation", body_ref="x",
                                    semver="1.0.0", phase_label="testing")
    run = Run.objects.create(tenant=tenant, work_item=story, agent_spec=spec,
                             temporal_workflow_id="wf-a11y-advisory")
    for number, level in LEVELS.items():
        WcagCriterion.objects.get_or_create(
            version="2.2", number=number,
            defaults={"handle": number, "level": level, "slug": number, "text": "…"})
    return {"tenant": tenant, "t": str(tenant.id), "project": project, "p": str(project.id),
            "story": story, "w": str(story.id), "run": run}


def _journey_finding(world, **over):
    """One finding as a journey pass records it — agentic, carrying a journey checker."""
    fields = {
        "route": "/checkout", "selector": "div.picker", "checker": "trap",
        "criterion": "2.1.2", "criteria": ["2.1.2"], "wcag_level": "A",
        "source": A11yFinding.Source.AGENTIC, "verdict": A11Y_FAIL, "outcome": TRIAGE_FAILURE,
        "confidence": 0.97, "severity": "critical",
        "evidence": "focus cycled inside the date picker; Escape did nothing",
        "suggested_fix": "let Escape close the picker",
    }
    fields.update(over)
    return A11yFinding.objects.create(
        tenant=world["tenant"], project=world["project"],
        fingerprint=fingerprint(route=fields["route"], selector=fields["selector"],
                                criterion=fields["criterion"], checker=fields["checker"]),
        first_seen_run=world["run"], last_seen_run=world["run"], **fields)


def _static_finding(world, **over):
    """One finding as a page scan records it — a measurement, and no checker at all."""
    base = {"source": SOURCE_RULE, "outcome": TRIAGE_FAILURE, "criteria": ("1.1.1",),
            "route": "/checkout", "selector": "img.hero", "checker": "",
            "evidence": 'alt="IMG_1234" is a filename', "rule_id": "image-alt",
            "confidence": None}
    base.update(over)
    record_run_findings(
        tenant_id=world["t"], project_id=world["p"], run_id=str(world["run"].id),
        report=MergedReport(rows=[ReportRow(**base)], routes=["/checkout"], unjudged=[]))


def _reconcile(world):
    return record_a11y_findings(tenant_id=world["t"], project_id=world["p"],
                                run_id=str(world["run"].id))


def _evaluate(world):
    return evaluate_a11y(a11y_condition(), ConditionContext(
        tenant_id=world["t"], work_item_id=world["w"], run_id=str(world["run"].id),
        project_id=world["p"]))


def _scanned(world, route="/checkout"):
    """A screen the scanner looked at — what tells "clean" apart from "never checked"."""
    return A11yScreenScan.objects.create(
        tenant=world["tenant"], project=world["project"], run=world["run"],
        run_key=str(world["run"].id), route=route,
        url=f"http://localhost:5173{route}", violations=[])


def _a11y_defects(world):
    return [item for item in WorkItem.objects.filter(
        tenant_id=world["t"], type=WorkItem.Type.DEFECT)
        if (item.external_ref or {}).get("a11y_finding")]


# ── which checks are advisory, and how that is decided ───────────────────────

def test_exactly_the_journey_checks_are_advisory_and_nothing_else():
    """The element checks judge a captured page, the same way the scanner reads one, and
    they are not what this task holds back. If a future check joins either group, this fails
    first — which makes it a decision rather than a side effect.

    Deliberately not counted here: the assertion is that the two GROUPS do not overlap, which is
    true at any size, and a number in this docstring would only be one more copy to go stale (it
    said "four" from 24 to 25 August, after `structure` made it five). `test_a11y_wcag` is where
    the count is pinned."""
    assert ADVISORY_CHECKERS == frozenset(A11Y_JOURNEY_CRITERIA)
    assert not ADVISORY_CHECKERS & set(A11Y_CHECKER_CRITERIA)
    assert all(is_advisory(checker) for checker in A11Y_JOURNEY_CRITERIA)
    assert not any(is_advisory(checker) for checker in A11Y_CHECKER_CRITERIA)


def test_advisory_is_decided_by_the_checker_not_the_source():
    """Load-bearing. A journey finding settled by a measurement is stored as `source=rule`
    (D-A11Y-78) — the same source a page scan carries — so a source test would either let a
    journey measurement block or stop the scanner blocking. Both are wrong."""
    assert is_advisory("focus_visible") is True        # source=rule when a probe decided it
    assert is_advisory("") is False                    # a page scan carries no checker at all
    assert is_advisory("alt") is False
    assert is_advisory(None) is False


# ── AC1 + AC3: the defect path ───────────────────────────────────────────────

def test_a_journey_failure_is_ticketed_and_the_gate_still_passes(world):
    """AC1 and AC3 in one run, because they are the two halves of the same claim: the problem
    is genuinely tracked, and it genuinely does not stop anyone."""
    _journey_finding(world)
    _scanned(world)
    out = _reconcile(world)

    defects = _a11y_defects(world)
    assert len(defects) == 1                                   # tracked …
    assert out["opened"] == [str(defects[0].id)]
    assert defects[0].external_ref["severity"] == "critical"
    assert "2.1.2" in defects[0].title
    assert "Escape did nothing" in defects[0].description

    assert defects[0].external_ref["advisory"] is True          # … and barred from the gate
    assert open_a11y_defects(tenant_id=world["t"], work_item_id=world["w"]) == []
    assert _evaluate(world)["satisfied"] is True


def test_the_passing_gate_says_the_advisory_problems_are_there(world):
    """A green gate on a story whose keyboard journey found a focus trap must not read like a
    green gate on a story that found nothing — the rule QA-19 applies to inherited debt, and
    D-A11Y-3 states for every other silence in this build. The reviewer approving the story is
    the person who most needs to know, and nothing else puts it in front of them."""
    _journey_finding(world)
    _scanned(world)
    _reconcile(world)

    result = _evaluate(world)
    assert result["satisfied"] is True
    assert "keyboard journey found 1 accessibility problem" in result["detail"]
    assert "do not block" in result["detail"]
    assert "2.1.2" in result["detail"]


def test_a_clean_story_says_nothing_at_all(world):
    """The note must appear because there is something to say, not because the code path ran."""
    _scanned(world)
    _reconcile(world)
    # `_result` drops the key entirely rather than storing an empty one, so a reviewer never
    # reads last week's reason on a green gate.
    assert "detail" not in _evaluate(world)


def test_confidence_makes_no_difference(world):
    """There is no threshold to clear. A 99%-sure keyboard agent is exactly as advisory as a
    51%-sure one, because what is unproven is the agent, not any individual verdict."""
    _journey_finding(world, confidence=0.99)
    _scanned(world)
    _reconcile(world)
    assert _evaluate(world)["satisfied"] is True


# ── AC4: everything else is untouched ────────────────────────────────────────

def test_a_static_failure_blocks_exactly_as_before(world):
    """The narrowness of this change is the thing most worth protecting. A page scan finding a
    Level A failure stops the gate today and must stop it tomorrow."""
    _static_finding(world)
    _scanned(world)
    _reconcile(world)

    assert len(open_a11y_defects(tenant_id=world["t"], work_item_id=world["w"])) == 1
    result = _evaluate(world)
    assert result["satisfied"] is False
    assert "1.1.1" in result["detail"]


def test_the_scanner_still_blocks_when_the_agent_agrees(world):
    """A ticket is advisory only when EVERY finding behind it is. QA-21 collapses the scanner's
    row and the agent's row into one ticket; if that ticket inherited the agent's advisory
    status, a proven scanner failure would stop blocking **because a second check agreed with
    it** — which is the opposite of what agreement should do."""
    _static_finding(world, criteria=("2.1.1",), selector="div.scroll-area",
                    evidence="the region scrolls but is not focusable",
                    rule_id="scrollable-region-focusable")
    _journey_finding(world, checker="keyboard", criterion="2.1.1", criteria=["2.1.1"],
                     selector="div.scroll-area",
                     evidence="tabbing never reached the scrolling region")
    _scanned(world)
    _reconcile(world)

    defects = _a11y_defects(world)
    assert len(defects) == 1                                   # one problem, one ticket (QA-21)
    assert defects[0].external_ref["advisory"] is False
    assert _evaluate(world)["satisfied"] is False


def test_a_ticket_stops_being_advisory_once_the_scanner_confirms_it(world):
    """The stamp is recomputed on every reconciliation, so the day a scan catches up with the
    agent, the ticket starts holding the line. It must not keep the answer it opened with."""
    _journey_finding(world, checker="keyboard", criterion="2.1.1", criteria=["2.1.1"],
                     selector="div.scroll-area")
    _scanned(world)
    _reconcile(world)
    assert _a11y_defects(world)[0].external_ref["advisory"] is True

    _static_finding(world, criteria=("2.1.1",), selector="div.scroll-area",
                    evidence="the region scrolls but is not focusable")
    _reconcile(world)
    defects = _a11y_defects(world)
    assert len(defects) == 1
    assert defects[0].external_ref["advisory"] is False
    assert _evaluate(world)["satisfied"] is False


# ── AC2: the second path, which was a live bug ───────────────────────────────

def test_a_journey_uncertain_does_not_block_and_is_not_called_an_incomplete_run(world):
    """**D-A11Y-84.** For the journey agent `uncertain` means "I looked and cannot tell" — its
    body says so, and several of these criteria turn on judgement calls specialists dispute.
    The gate read the same word as "nobody answered, the judge was unavailable". So being
    honest about uncertainty stopped the team, under a message that was not even true."""
    _journey_finding(world, checker="focus_order", criterion="2.4.3", criteria=["2.4.3"],
                     verdict=A11Y_UNCERTAIN, confidence=0.0, outcome="needs_review",
                     evidence="the order is odd but may still be meaningful")
    _scanned(world)
    _reconcile(world)

    assert unanswered_checks(tenant_id=world["t"], project_id=world["p"],
                             work_item_id=world["w"]) == []
    result = _evaluate(world)
    assert result["satisfied"] is True
    assert "did not complete" not in result.get("detail", "")


def test_an_element_checks_uncertain_still_blocks(world):
    """The other direction, and the reason the fix is keyed on the checker rather than on the
    word. For the element checks `uncertain` really does mean nobody answered — the judge was
    unavailable, or the run hit its cap — and that must still stop the gate."""
    _journey_finding(world, checker="alt", criterion="1.1.1", criteria=["1.1.1"],
                     source=A11yFinding.Source.AI, selector="img.hero",
                     verdict=A11Y_UNCERTAIN, confidence=0.0, outcome="needs_review",
                     evidence="", wcag_level="A")
    _scanned(world)
    _reconcile(world)

    assert len(unanswered_checks(tenant_id=world["t"], project_id=world["p"],
                                 work_item_id=world["w"])) == 1
    result = _evaluate(world)
    assert result["satisfied"] is False
    assert "did not complete" in result["detail"]


# ── AC3 continued: advisory is not invisible ─────────────────────────────────

def test_the_finding_is_still_in_the_backlog_but_not_in_the_blocking_list(world):
    """Both halves matter. It is a real problem and belongs in the fix order; and the list
    whose whole promise is "this is what would stop you" must not name it."""
    _journey_finding(world)
    _scanned(world)
    _reconcile(world)

    everything = prioritised(world["t"], world["p"])
    blocking = prioritised(world["t"], world["p"], blocking_only=True)
    assert [item["criterion"] for item in everything] == ["2.1.2"]
    assert blocking == []


def test_the_advisory_ticket_is_a_real_tracked_defect(world):
    """Advisory means "does not stand in your way", never "hidden". A developer still gets a
    ticket on the story, with the evidence and the fix on it."""
    _journey_finding(world)
    _scanned(world)
    _reconcile(world)

    defect = _a11y_defects(world)[0]
    assert defect.parent_id == world["story"].id
    assert defect.state == WorkItem.State.IN_PROGRESS
    assert "let Escape close the picker" in defect.description
    assert advisory_a11y_defects(tenant_id=world["t"], work_item_id=world["w"])


# ── AC5 + AC6: nothing can switch this on, and the client still decides ──────

def test_no_setting_exists_that_would_make_a_journey_check_blocking():
    """AC5. A policy naming a setting that does not exist is rejected by name, so this proves
    the absence rather than asserting it: there is no configuration surface to find."""
    with pytest.raises(A11yPolicyError) as caught:
        validate_policy({"gate": {"advisory_checkers": []}})
    assert "settings that do not exist" in str(caught.value)

    with pytest.raises(A11yPolicyError):
        validate_policy({"gate": {"block_advisory": True}})


def test_the_policy_summary_says_it_in_plain_words(world):
    """Not part of the policy, but stated in its summary anyway. A rule that decides whether
    work stops has to be readable by the person whose work it is — "why did this keyboard
    failure not block?" is otherwise unanswerable without reading the source."""
    summary = describe_policy(validate_policy({}))
    assert "keyboard journey" in summary
    assert "never stop work" in summary
    assert "not configurable" in summary


def test_a_project_that_blocks_on_nothing_blocks_on_nothing(world):
    """AC6. The client decides, and always did — QA-08 made an empty list a supported choice.
    Asserted here so the thing the team was told is true is proven rather than assumed."""
    ProjectProfile.objects.update_or_create(
        tenant=world["tenant"], project=world["project"],
        defaults={"a11y": {"gate": {"block_severities": []}}})
    _static_finding(world)
    _journey_finding(world)
    _scanned(world)
    _reconcile(world)

    assert _a11y_defects(world) == []
    assert _evaluate(world)["satisfied"] is True
