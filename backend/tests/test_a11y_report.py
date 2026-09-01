"""QA-12 — the AI-checks pass joined to the testing flow, and the merged report.

Everything the accessibility feature has built since QA-01 was idle until this task: three
finished, tested functions — `requests_for`, `dispatch_judgments`, `triage` — were referenced by
nobody outside their own tests. These prove the join.

Against the task's acceptance criteria:

  AC1  one run's report carries the rule scanner's findings and the AI's, in one place
  AC2  every AI finding says it is an AI finding, how sure it was, and which WCAG 2.2 criteria
  AC3  a low-confidence AI finding appears as "needs review" and never as a failure
  AC4  where the scanner and the AI disagree on one element and criterion, the scanner stands —
       proven END TO END here for the first time, from stored scan output rather than a fixture
       hand-built in the test (which is all QA-06 could do, and said so)
  AC5  a live run on a real feature — NOT provable here; see the module note below
  AC6  ≥ 90% coverage on the new code

**On AC5, stated rather than skipped.** The milestone requires a real feature run, and no test
can produce one: it needs a companion, a running application and a browser. What these tests
establish is that everything either side of that run is correct, so the live run is a check of
the capture rules against a real DOM and not a first assembly.

**Two structural claims are asserted, not assumed:**

  * the judge runs on a work item of its OWN. `_guard_no_active_run` refuses a second run on a
    work item that already has a live one, and the test run's own run is live for the whole
    build — so dispatching against the story would fail every time in production and never once
    in a test that fakes the trigger. The work item the dispatch names is checked directly.
  * the pass never fails the build. Each entry point is driven into failure on purpose.
"""
from __future__ import annotations

import base64
import io

import pytest
from PIL import Image as PILImage

from apps.a11y.aipass import (
    JUDGING_STREAM,
    SOURCE_RUN_KEY,
    finish_ai_pass,
    judging_work_item,
    start_ai_pass,
)
from apps.a11y.baseline import unanswered_counts
from apps.a11y.capture import (
    MAX_AXE_NODES,
    MAX_AXE_VIOLATIONS,
    CaptureError,
    fingerprint,
    parse_capture,
)
from apps.a11y.dispatch import JUDGE_AGENT_KEY, record_verdict
from apps.a11y.ingest import ingest_screen, requests_for
from apps.a11y.models import A11yCandidateBundle, A11yScreenScan
from apps.a11y.report import (
    REPORT_TYPE,
    SOURCE_AI,
    SOURCE_RULE,
    merge_run,
    publish_report,
    report_body,
)
from apps.a11y.scanner import rule_findings_for
from apps.a11y.triage import TRIAGE_FAILURE, TRIAGE_PASS, TRIAGE_REVIEW
from apps.integrations.models import IntegrationConnection
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.runs.enrollment import enroll_runner
from apps.runs.models import Run
from apps.tenancy.models import Tenant, User
from apps.workitems.models import WorkItem
from integrations.types import A11Y_FAIL, A11Y_PASS, A11Y_UNCERTAIN, A11yJudgment
from orchestration.activities import WriteCompletenessError
from storage.object_store import InMemoryObjectStore

# ── a page with an image, a fake button and a real button ──────────────────────────

_STYLES = {
    "color": "rgb(0, 0, 0)", "background-color": "transparent",
    "text-decoration-line": "none", "font-size": "16px", "font-weight": "400",
    "border-style": "none",
}


def _png(colour=(200, 40, 40)) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (400, 300), colour).save(buf, format="PNG")
    return buf.getvalue()


def _element(**over) -> dict:
    base = {
        "selector": "img.hero", "tag": "img", "role": "", "attrs": {"alt": "IMG_1234"},
        "text": "", "accessible_name": "IMG_1234", "interactive": False, "rendered": True,
        "styles": dict(_STYLES), "parent_styles": dict(_STYLES),
        "html": '<img class="hero" alt="IMG_1234">', "context": "Our new range",
        "box": {"x": 10, "y": 20, "width": 120, "height": 80},
    }
    base.update(over)
    return base


def _fake_button(**over) -> dict:
    """A `div` behaving like a control — the `semantics` check applies to it."""
    base = _element(
        selector="div.fake-btn", tag="div", attrs={}, text="Buy now",
        accessible_name="Buy now", interactive=True, html="<div>Buy now</div>",
        box={"x": 200, "y": 100, "width": 80, "height": 30},
    )
    base.update(over)
    return base


def _screen(**over) -> dict:
    base = {
        "route": "/checkout", "url": "http://localhost:5173/checkout",
        "screenshot_base64": base64.b64encode(_png()).decode("ascii"),
        "axe_violations": [
            {"rule": "color-contrast", "impact": "serious", "criteria": ["1.4.3"],
             "help": "Elements must meet contrast thresholds",
             "nodes": [".btn-secondary", "footer a"]},
            {"rule": "region", "impact": "moderate", "criteria": [],
             "help": "All content should be contained by landmarks", "nodes": ["body > div"]},
        ],
        "elements": [_element(), _fake_button()],
    }
    base.update(over)
    return base


@pytest.fixture
def world(db):
    """A tenant that can dispatch: judge agent registered, machine connected."""
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Shop")
    user = User.objects.create_user(email="qa@acme.com", name="QA", tenant=tenant, password="pw")
    story = WorkItem.objects.create(tenant=tenant, project=project, title="Checkout")
    spec = AgentSpec.objects.create(
        tenant=tenant, key=JUDGE_AGENT_KEY, semver="1.0.0", prompt_version="a11y-judge-1",
        body_ref="agents/09c_a11y_judge.md", recommended_engine="claude",
        recommended_model="claude-opus-5", phase_label="a11y_judge",
    )
    enroll_runner(tenant_id=str(tenant.id), project_id=str(project.id),
                  developer_id=str(user.id), label="qa-laptop")
    IntegrationConnection.objects.create(
        tenant=tenant, capability="a11yai", connector="builtin", token_ref="builtin")
    build_run = Run.objects.create(
        tenant=tenant, work_item=story, agent_spec=spec, triggered_by=user,
        temporal_workflow_id="build-1",
    )
    return {"t": str(tenant.id), "p": str(project.id), "tenant": tenant, "project": project,
            "user": user, "story": story, "spec": spec, "run": build_run,
            "run_id": str(build_run.id)}


class FakeTrigger:
    """Stands in for `trigger_phase`, recording which work item it was asked to run on.

    The work item is the point. Faking the trigger is what lets a test dispatch without
    Temporal — and it is also what would hide the guard collision this task had to solve, so
    the call is inspected rather than only counted.
    """

    def __init__(self, world, fail: Exception | None = None):
        self._world = world
        self._fail = fail
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self._fail is not None:
            raise self._fail
        run = Run.objects.create(
            tenant=self._world["tenant"],
            work_item=WorkItem.objects.get(id=kwargs["work_item_id"]),
            agent_spec=self._world["spec"], engine="claude", model="claude-opus-5",
            prompt_version="a11y-judge-1", temporal_workflow_id=f"judge-{len(self.calls)}",
        )

        class _Outcome:
            run_id = str(run.id)
            workflow_id = f"agent-run-{run.id}"

        return _Outcome()


def _ingest(world, screen=None, store=None):
    return ingest_screen(
        tenant_id=world["t"], project_id=world["p"], screen=parse_capture(
            __import__("json").dumps(screen or _screen()))[0],
        run_id=world["run_id"], object_store=store or InMemoryObjectStore(),
    )


def _judge(world, request, verdict, confidence, *, criteria=None, evidence="quoted markup",
           fix="do the thing"):
    """Store one verdict for one request, the way the judge's own tool does."""
    from integrations.types import A11Y_CHECKER_CRITERIA

    record_verdict(
        tenant_id=world["t"], project_id=world["p"], run_id=None,
        content_hash=request.content_hash,
        judgment=A11yJudgment(
            criteria=tuple(criteria or A11Y_CHECKER_CRITERIA[request.checker]),
            verdict=verdict, confidence=confidence, evidence=evidence,
            suggested_fix=fix, checker=request.checker,
        ),
    )


def _by_checker(world, checker):
    return next(r for r in requests_for(world["t"], world["p"], world["run_id"])
                if r.checker == checker)


def _selected(world):
    """Every element-check this page produced — one row per (element, checker) pair.

    **Use this instead of a literal count.** The page below has two selected elements, and
    the number of REQUESTS they produce is one per check that applies, which moves whenever
    a checker is added: it was 2 before 27 August and is 3 now, because `img.hero` is asked
    both whether its alt text SAYS what it means and whether the image can be SEEN. Six
    tests here hard-coded that 2, none of them was about it, and all six were red for five
    days as a result.
    """
    return requests_for(world["t"], world["p"], world["run_id"])


def _judge_everything(world, verdict=A11Y_PASS, confidence=0.97):
    """Answer every selected check, so "complete" means complete rather than "the two I
    happened to name". Naming checkers by hand is what made a complete run read as
    incomplete the moment a sixth check started selecting elements."""
    for request in _selected(world):
        _judge(world, request, verdict, confidence, evidence="", fix="")


# ══ the capture carries the whole scan, not only what got selected ═════════════════

def test_a_screens_whole_scan_is_read_and_stored(world):
    """The completeness half of AC1. A row only exists for an element one of the AI checks
    applies to, so a violation on anything else would have no record anywhere — which is why
    the scan reports itself at screen level."""
    out = _ingest(world)
    assert out["violations"] == 2
    scan = A11yScreenScan.objects.get(tenant_id=world["t"], run_key=world["run_id"])
    assert scan.route == "/checkout"
    assert {v["rule"] for v in scan.violations} == {"color-contrast", "region"}


def test_a_violation_on_no_captured_element_still_reaches_the_report(world):
    """`.btn-secondary` is not one of the two captured elements — and this is most of a real
    scan. Without the screen-level list it would be in the test report as prose and nowhere in
    the platform as data."""
    _ingest(world)
    scan = rule_findings_for(world["t"], world["p"], world["run_id"])
    assert ("/checkout", ".btn-secondary", "1.4.3") in {f.key for f in scan.failures}


def test_a_scanner_rule_with_no_wcag_criterion_is_kept_and_counted(world):
    """axe ships best-practice rules that map to no criterion. They cannot be conformance
    findings — and dropping them would make the report claim the scan found less than it did."""
    _ingest(world)
    scan = rule_findings_for(world["t"], world["p"], world["run_id"])
    assert [v["rule"] for v in scan.without_criterion] == ["region"]
    assert all(f.rule_id != "region" for f in scan.failures)


def test_a_violation_naming_no_element_becomes_a_finding_against_the_route(world):
    screen = _screen(axe_violations=[
        {"rule": "html-has-lang", "impact": "serious", "criteria": ["3.1.1"], "nodes": []}])
    _ingest(world, screen)
    scan = rule_findings_for(world["t"], world["p"], world["run_id"])
    assert [(f.route, f.selector, f.criterion) for f in scan.failures] == \
        [("/checkout", "", "3.1.1")]


def test_a_malformed_violation_costs_that_violation_and_not_the_report(world):
    """Machine output that reached us through an agent. One bad entry must not take the run's
    whole accessibility report with it."""
    _ingest(world)
    scan_row = A11yScreenScan.objects.get(tenant_id=world["t"], run_key=world["run_id"])
    scan_row.violations = ["not a dict", {"rule": "image-alt", "criteria": ["1.1.1"],
                                          "nodes": ["img.x"]}]
    scan_row.save(update_fields=["violations"])
    scan = rule_findings_for(world["t"], world["p"], world["run_id"])
    assert [f.rule_id for f in scan.failures] == ["image-alt"]


def test_the_elements_own_selector_wins_when_both_sources_describe_it(world):
    """The scan reports axe's `nodes[].target`; the candidate carries the spelling the capture
    used. `triage` matches on the selector textually, so the candidate's has to be the one that
    survives — otherwise the two engines would never be recognised as talking about one
    element, and rule 2 would silently stop applying."""
    screen = _screen(
        elements=[_fake_button()],
        axe_violations=[{"rule": "button-name", "impact": "critical", "criteria": ["4.1.2"],
                         "nodes": ["div.fake-btn"]}],
    )
    screen["elements"][0]["axe"] = {"rule": "button-name", "impact": "critical",
                                    "criteria": ["4.1.2"]}
    _ingest(world, screen)
    scan = rule_findings_for(world["t"], world["p"], world["run_id"])
    keys = [f.key for f in scan.failures]
    assert keys == [("/checkout", "div.fake-btn", "4.1.2")], "one element, not two"


# ══ capture format: bounds are refusals ════════════════════════════════════════════

def test_a_capture_with_no_scan_list_is_read_as_nothing_reported(world):
    """Absent means "the scan said nothing here" — the same shape as a clean page. Whether a
    scan RAN at all is the test report's question, not this one's."""
    screen = _screen()
    del screen["axe_violations"]
    assert parse_capture(__import__("json").dumps(screen))[0]["axe_violations"] == []


def test_too_many_violations_is_refused_rather_than_trimmed():
    screen = _screen(axe_violations=[{"rule": f"r{i}", "criteria": ["1.1.1"]}
                                     for i in range(MAX_AXE_VIOLATIONS + 1)])
    with pytest.raises(CaptureError) as exc:
        parse_capture(__import__("json").dumps(screen))
    assert "over the limit" in str(exc.value)


def test_too_many_elements_on_one_rule_is_refused_and_names_the_rule():
    screen = _screen(axe_violations=[
        {"rule": "color-contrast", "criteria": ["1.4.3"],
         "nodes": [f".n{i}" for i in range(MAX_AXE_NODES + 1)]}])
    with pytest.raises(CaptureError) as exc:
        parse_capture(__import__("json").dumps(screen))
    assert "color-contrast" in str(exc.value)


def test_a_scan_list_that_is_not_a_list_is_refused():
    with pytest.raises(CaptureError):
        parse_capture(__import__("json").dumps(_screen(axe_violations={"rule": "x"})))


def test_the_screen_fingerprint_changes_when_only_the_scan_changed():
    """QA-07 skips a screen nobody touched. A screen whose scan changed WAS touched in the only
    way that matters to this report — carrying it forward would quote a scan that is no longer
    true of the page."""
    before = parse_capture(__import__("json").dumps(_screen()))[0]
    after = parse_capture(__import__("json").dumps(_screen(axe_violations=[])))[0]
    assert fingerprint(before) != fingerprint(after)


def test_a_carried_forward_screen_still_records_its_scan(world):
    """The bug QA-07 opened with, in a new place: work that only happens on the expensive path
    disappears the second time a screen is captured."""
    _ingest(world)
    second = Run.objects.create(
        tenant=world["tenant"], work_item=world["story"], agent_spec=world["spec"],
        temporal_workflow_id="build-2")
    out = ingest_screen(tenant_id=world["t"], project_id=world["p"],
                        screen=parse_capture(__import__("json").dumps(_screen()))[0],
                        run_id=str(second.id), object_store=InMemoryObjectStore())
    assert out["reused"] is True, "the screen was unchanged, so no image work should happen"
    assert out["violations"] == 2
    assert A11yScreenScan.objects.filter(
        tenant_id=world["t"], run_key=str(second.id)).exists()


# ══ AC1 — both engines in one report ═══════════════════════════════════════════════

def test_one_report_carries_both_the_rule_findings_and_the_ai_findings(world):
    _ingest(world)
    alt = _by_checker(world, "alt")
    _judge(world, alt, A11Y_FAIL, 0.93, evidence='alt="IMG_1234" is a filename')

    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    sources = {row.source for row in report.rows}
    assert sources == {SOURCE_AI, SOURCE_RULE}
    assert any(row.source == SOURCE_AI and "1.1.1" in row.criteria for row in report.failures)
    assert any(row.source == SOURCE_RULE and "1.4.3" in row.criteria for row in report.failures)


def test_a_screen_with_no_candidate_for_a_check_is_not_an_error(world):
    """The task's own edge case. A screen where no element the `color` check applies to exists
    simply produces no colour finding."""
    _ingest(world)
    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    assert all(row.checker != "color" for row in report.rows)
    assert report.rows, "the rest of the report is unaffected"


# ══ AC2 — an AI finding says it is one, how sure, and against what ═════════════════

def test_every_ai_finding_carries_its_source_confidence_and_criteria(world):
    _ingest(world)
    semantics = _by_checker(world, "semantics")
    _judge(world, semantics, A11Y_FAIL, 0.91, criteria=("1.3.1", "4.1.2"),
           evidence="<div> with a click handler and no role")

    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    row = next(r for r in report.rows if r.checker == "semantics")
    assert row.source == SOURCE_AI
    assert row.confidence == pytest.approx(0.91)
    assert row.criteria == ("1.3.1", "4.1.2"), "D-A11Y-2: every criterion, on one row"
    assert "1.3.1, 4.1.2" in report_body(report), "and both are rendered, not just the first"


def test_a_rule_finding_reports_a_measurement_rather_than_a_confidence(world):
    """A scanner did not guess. Showing "100% sure" against a measurement invites a reader to
    compare it with an AI's 0.9 as though they were the same kind of number."""
    _ingest(world)
    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    row = next(r for r in report.rows if r.source == SOURCE_RULE)
    assert row.confidence is None
    assert "measured" in report_body(report)


# ══ AC3 — not sure enough is never a failure ═══════════════════════════════════════

def test_a_low_confidence_ai_failure_appears_as_needs_review(world):
    _ingest(world)
    alt = _by_checker(world, "alt")
    _judge(world, alt, A11Y_FAIL, 0.42, evidence="might be a filename")

    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    row = next(r for r in report.rows if r.checker == "alt")
    assert row.outcome == TRIAGE_REVIEW
    assert row.blocks is False
    assert row not in report.failures
    assert "Needs human review" in report_body(report)


def test_a_confident_ai_pass_is_reported_as_a_pass(world):
    _ingest(world)
    alt = _by_checker(world, "alt")
    _judge(world, alt, A11Y_PASS, 0.97, evidence="", fix="")
    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    assert next(r for r in report.rows if r.checker == "alt").outcome == TRIAGE_PASS


# ══ AC4 — the measurement stands, proven end to end ════════════════════════════════

def test_the_scanner_wins_when_it_and_the_ai_disagree_on_one_element(world):
    """QA-06 built this rule and could only unit-test it: structured scanner output did not
    reach the platform until QA-11b, and nothing constructed an `A11yRuleFailure` until this
    task. Here the failure comes out of a stored capture, and the AI's `pass` loses to it."""
    screen = _screen(elements=[_fake_button()], axe_violations=[
        {"rule": "button-name", "impact": "critical", "criteria": ["4.1.2"],
         "help": "Buttons must have discernible text", "nodes": ["div.fake-btn"]}])
    _ingest(world, screen)
    semantics = _by_checker(world, "semantics")
    _judge(world, semantics, A11Y_PASS, 0.99, criteria=("4.1.2",), evidence="", fix="")

    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    row = next(r for r in report.rows if r.selector == "div.fake-btn")
    assert row.outcome == TRIAGE_FAILURE, "a measurement is not overturned by an opinion"
    assert row.source == SOURCE_RULE, "and the report says which engine decided it"
    assert row.rule_id == "button-name"


def test_a_scanner_failure_elsewhere_does_not_settle_this_element(world):
    """The one-way rule, from the other side: rule 2 is exact on (route, selector, criterion),
    so a failure on a different element must leave this judgment alone."""
    screen = _screen(elements=[_fake_button()], axe_violations=[
        {"rule": "button-name", "impact": "critical", "criteria": ["4.1.2"],
         "nodes": ["header button"]}])
    _ingest(world, screen)
    semantics = _by_checker(world, "semantics")
    _judge(world, semantics, A11Y_PASS, 0.99, criteria=("4.1.2",), evidence="", fix="")

    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    assert next(r for r in report.rows
                if r.selector == "div.fake-btn").outcome == TRIAGE_PASS


def test_the_ai_still_stands_where_the_scanner_said_nothing(world):
    """Rule 2 runs ONE way. Reading it as "the scanner always wins" would delete the entire
    value of the AI layer — the whole point is catching what a scanner is blind to."""
    _ingest(world)
    alt = _by_checker(world, "alt")
    _judge(world, alt, A11Y_FAIL, 0.95, evidence='alt="IMG_1234" is a filename')
    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    row = next(r for r in report.rows if r.checker == "alt")
    assert row.outcome == TRIAGE_FAILURE
    assert row.source == SOURCE_AI


# ══ silence is reported, never inferred (D-A11Y-3) ═════════════════════════════════

def test_an_element_that_was_never_judged_is_named_in_the_report(world):
    _ingest(world)
    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    assert len(report.unjudged) == len(_selected(world)), "nothing was judged"
    assert {u["selector"] for u in report.unjudged} == {"img.hero", "div.fake-btn"}, (
        "both captured elements were selected and both must be named"
    )
    assert report.complete is False
    body = report_body(report)
    assert "This check is incomplete" in body
    assert "Selected but not judged" in body


def test_a_complete_check_carries_no_incompleteness_warning(world):
    _ingest(world)
    _judge_everything(world)
    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    assert report.complete is True
    assert "This check is incomplete" not in report_body(report)


def test_an_empty_run_says_so_rather_than_reading_as_clean(world):
    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    body = report_body(report)
    assert "only a clean result if a scan actually ran" in body


def test_a_cell_containing_a_pipe_cannot_break_the_table(world):
    """A selector or an evidence string is arbitrary text from a page we did not write."""
    _ingest(world)
    alt = _by_checker(world, "alt")
    _judge(world, alt, A11Y_FAIL, 0.95, evidence="alt|text\nwith a newline")
    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    for line in report_body(report).splitlines():
        if line.startswith("|"):
            assert line.count("|") - line.count("\\|") >= 2


# ══ publishing the report ══════════════════════════════════════════════════════════

def test_the_report_is_registered_against_the_run_that_did_the_testing(world):
    from apps.registry.models import Artifact

    _ingest(world)
    _judge(world, _by_checker(world, "alt"), A11Y_FAIL, 0.95, evidence="filename")
    out = publish_report(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])

    artifact = Artifact.objects.get(id=out["artifact_id"])
    assert artifact.type == REPORT_TYPE
    assert str(artifact.run_id) == world["run_id"], "next to that run's test report"
    assert out["failures"] >= 1


def test_publishing_twice_updates_the_same_report(world):
    from apps.registry.models import Artifact

    _ingest(world)
    first = publish_report(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    _judge(world, _by_checker(world, "alt"), A11Y_FAIL, 0.95, evidence="filename")
    second = publish_report(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    assert first["artifact_id"] == second["artifact_id"]
    assert Artifact.objects.filter(tenant_id=world["t"], type=REPORT_TYPE).count() == 1


def test_a_report_is_still_registered_when_its_body_cannot_be_filed(world, monkeypatch):
    """Mirrors `_register_test_report`: a report registered from its hash alone is worse than
    one with a body, and far better than no report because the object store blinked."""
    from apps.registry.models import Artifact

    _ingest(world)
    monkeypatch.setattr(
        "mcp_platform_state.tools.stage_artifact_body",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("object store is down")))
    out = publish_report(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    artifact = Artifact.objects.get(id=out["artifact_id"])
    assert artifact.content_hash, "registered from the hash alone"
    assert not artifact.s3_key


def test_the_summary_line_never_calls_an_incomplete_check_clean(world):
    _ingest(world)
    out = publish_report(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    assert "not judged" in out["summary"]
    assert out["complete"] is False


# ══ starting the pass ══════════════════════════════════════════════════════════════

def test_the_judge_runs_on_its_own_work_item_not_the_story(world):
    """The structural claim. `_guard_no_active_run` refuses a second run on a work item that
    already has a live one, and the build's own run is live for the whole build workflow — so
    dispatching against the story would be refused in production every time, and never once in
    a test that fakes the trigger. Hence this assertion on the call itself."""
    _ingest(world)
    trigger = FakeTrigger(world)
    out = start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"],
                        work_item_id=str(world["story"].id), trigger=trigger)

    assert out["started"] is True
    dispatched_to = trigger.calls[0]["work_item_id"]
    assert dispatched_to != str(world["story"].id)
    item = WorkItem.objects.get(id=dispatched_to)
    assert item.feature_stream == f"{JUDGING_STREAM}{world['run_id']}"
    assert str(item.parent_id) == str(world["story"].id)


def test_the_judging_work_item_is_per_run_so_two_builds_cannot_collide(world):
    """Per run rather than per project on purpose: a project-wide container would itself have a
    live run whenever any build was judging, and two builds finishing together would collide on
    exactly the guard this avoids."""
    other = Run.objects.create(tenant=world["tenant"], work_item=world["story"],
                               agent_spec=world["spec"], temporal_workflow_id="build-2")
    a = judging_work_item(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    b = judging_work_item(tenant_id=world["t"], project_id=world["p"], run_id=str(other.id))
    assert a.id != b.id


def test_asking_twice_for_one_runs_work_item_returns_the_same_one(world):
    a = judging_work_item(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    b = judging_work_item(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    assert a.id == b.id


def test_a_run_that_captured_nothing_starts_no_judgment(world):
    trigger = FakeTrigger(world)
    out = start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"],
                        trigger=trigger)
    assert out["started"] is False
    assert trigger.calls == []
    assert "no accessibility candidates" in out["reason"]


def test_the_judge_run_remembers_which_capture_it_is_judging(world):
    _ingest(world)
    trigger = FakeTrigger(world)
    out = start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"],
                        trigger=trigger)
    judge_run = Run.objects.get(id=out["judge_run_id"])
    assert judge_run.inputs[SOURCE_RUN_KEY] == world["run_id"]


def test_when_every_answer_is_already_known_the_report_is_published_at_once(world):
    """No run starts when the cache answers everything — so if the report waited for a run it
    would wait forever, and a re-run of an unchanged screen would produce no report at all."""
    _ingest(world)
    _judge_everything(world)

    trigger = FakeTrigger(world)
    out = start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"],
                        trigger=trigger)
    assert out["started"] is False
    assert trigger.calls == [], "nothing needed judging"
    assert out["report"]["artifact_id"]
    assert out["report"]["complete"] is True


def test_a_judge_that_cannot_be_started_still_produces_a_report(world):
    """D-A11Y-3 end to end: an outage that produced nothing would read downstream as "no
    accessibility problems found".

    Note what `complete` now means here, and why it flipped in QA-13. Every element DID get an
    answer — a well-formed `uncertain` naming the outage — so coverage is complete and the
    report is not missing anything. What makes the run untrustworthy is the *reason* those
    answers say, which is why the outage banner is asserted separately below rather than being
    inferred from a missing verdict.
    """
    _ingest(world)
    trigger = FakeTrigger(world, fail=RuntimeError("temporal is down"))
    out = start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"],
                        trigger=trigger)
    assert out["started"] is False
    assert "temporal is down" in out["reason"]
    assert out["report"]["artifact_id"], "the report exists"
    asked = len(_selected(world))
    assert out["filed_unjudged"] == asked, "every check it could not ask about was FILED"
    assert out["report"]["needs_review"] == asked, "each one routed to a person, not lost"


def test_an_uncertain_verdict_is_never_served_back_to_a_later_dispatch(world):
    """The repair QA-13 opened with, and the more serious half of it.

    `verify_judgment_completeness` has stored an `uncertain` for every element a judge finished
    without reporting on since QA-02a, and the dispatch cache served ANY stored verdict back.
    So one judge run that fell over would answer that element "sent for human review" **for
    ever** — never re-asked, on any future run, with nothing anywhere saying why. A transient
    failure became a permanent hole in a compliance report.

    Nothing was saved by caching it either: no judgment was ever made to reuse.
    """
    from apps.a11y.dispatch import dispatch_judgments

    _ingest(world)
    request = _by_checker(world, "alt")
    _judge(world, request, A11Y_UNCERTAIN, 0.0, evidence="the judge was unavailable")

    result = dispatch_judgments(
        tenant_id=world["t"], project_id=world["p"], work_item_id=str(world["story"].id),
        requests=[request], triggered_by=str(world["user"].id), trigger=FakeTrigger(world))
    assert result.from_cache == [], "an 'I could not tell' is not an answer to reuse"
    assert len(result.dispatched) == 1, "so it gets asked again"


def test_a_real_verdict_is_still_served_from_the_cache(world):
    """The saving QA-07 exists for is untouched — only `uncertain` is excluded."""
    from apps.a11y.dispatch import dispatch_judgments

    _ingest(world)
    request = _by_checker(world, "alt")
    _judge(world, request, A11Y_FAIL, 0.95, evidence="filename")

    trigger = FakeTrigger(world)
    result = dispatch_judgments(
        tenant_id=world["t"], project_id=world["p"], work_item_id=str(world["story"].id),
        requests=[request], triggered_by=str(world["user"].id), trigger=trigger)
    assert len(result.from_cache) == 1 and trigger.calls == []


def test_the_capability_still_reports_why_it_could_not_tell(world):
    """The read path keeps its uncertains. "We could not tell, because …" is a real answer a
    reader needs — it is only the *dispatch decision* that must ignore it."""
    from apps.a11y.dispatch import stored_judgment

    _ingest(world)
    request = _by_checker(world, "alt")
    _judge(world, request, A11Y_UNCERTAIN, 0.0, evidence="no machine was connected")
    held = stored_judgment(tenant_id=world["t"], checker="alt",
                           candidate=request.candidate, project_id=world["p"])
    assert held is not None and held.verdict == A11Y_UNCERTAIN
    assert "no machine was connected" in held.evidence


def test_what_could_not_be_asked_about_reaches_the_review_queue(world):
    """The half that made the queue empty exactly when it should be fullest."""
    from apps.a11y.findings import review_queue

    _ingest(world)
    start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"],
                  trigger=FakeTrigger(world, fail=RuntimeError("temporal is down")))
    queue = review_queue(world["t"], world["p"])
    assert len(queue) == len(_selected(world))
    assert all("could not be started" in f.evidence for f in queue), \
        "and each one says WHY, not just that no verdict was recorded"


def test_starting_the_pass_never_raises_at_the_build(world, monkeypatch):
    """The build has its branch, its tests and its defects. Losing those to a failed
    accessibility report would be the worse trade by a wide margin."""
    _ingest(world)
    monkeypatch.setattr("apps.a11y.report.merge_run",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("merge exploded")))
    trigger = FakeTrigger(world, fail=RuntimeError("no judge"))
    out = start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"],
                        trigger=trigger)
    assert out["report"]["error"] == "merge exploded"


# ══ finishing the pass ═════════════════════════════════════════════════════════════

def test_the_report_is_published_when_the_judgment_run_ends(world):
    _ingest(world)
    trigger = FakeTrigger(world)
    started = start_ai_pass(tenant_id=world["t"], project_id=world["p"],
                            run_id=world["run_id"], trigger=trigger)
    for checker in ("alt", "semantics"):
        _judge(world, _by_checker(world, checker), A11Y_FAIL, 0.95, evidence="bad")

    out = finish_ai_pass(tenant_id=world["t"], judge_run_id=started["judge_run_id"])
    assert out["published"] is True
    assert out["report"]["failures"] >= 2


def test_a_run_that_is_not_a_judgment_run_publishes_nothing(world):
    out = finish_ai_pass(tenant_id=world["t"], judge_run_id=world["run_id"])
    assert out["published"] is False


def test_an_unknown_run_is_answered_rather_than_raising(world):
    import uuid

    out = finish_ai_pass(tenant_id=world["t"], judge_run_id=str(uuid.uuid4()))
    assert out["published"] is False


# ══ the build only runs the pass where the test loop runs ══════════════════════════

def test_a_phase_that_imports_no_test_results_starts_no_accessibility_pass(world):
    """Copied deliberately from the test-import bound: a 07 implementation build captures
    nothing and must not start a judgment run."""
    from orchestration.build_activities import run_a11y_ai_pass_core
    from orchestration.build_types import BuildInput

    spec = AgentSpec.objects.create(tenant=world["tenant"], key="07_implementation",
                                    body_ref="x", semver="1.0.0")
    out = run_a11y_ai_pass_core(BuildInput(
        run_id=world["run_id"], tenant_id=world["t"], project_id=world["p"],
        work_item_id=str(world["story"].id), agent_spec_id=str(spec.id),
        work_item_key="wi", repo="o/r", base="main",
    ))
    assert out["started"] is False
    assert "does not run accessibility checks" in out["reason"]


def test_the_test_automation_phase_does_run_the_pass(world, monkeypatch):
    """The activity has no `trigger` argument to inject, so the trigger is patched at its
    source. That is not tidiness: unpatched, `trigger_phase` starts a real Temporal workflow
    against whatever `TEMPORAL_HOST` names, which in this repo is a server shared with other
    developers. A test must never reach it."""
    from orchestration.build_activities import run_a11y_ai_pass_core
    from orchestration.build_types import BuildInput

    _ingest(world)
    trigger = FakeTrigger(world)
    monkeypatch.setattr("orchestration.trigger.trigger_phase", trigger)
    spec = AgentSpec.objects.create(tenant=world["tenant"], key="09b_test_automation",
                                    body_ref="x", semver="1.0.0")
    out = run_a11y_ai_pass_core(BuildInput(
        run_id=world["run_id"], tenant_id=world["t"], project_id=world["p"],
        work_item_id=str(world["story"].id), agent_spec_id=str(spec.id),
        work_item_key="wi", repo="o/r", base="main",
    ))
    assert out["started"] is True
    assert out["dispatched"] == len(_selected(world))
    assert trigger.calls[0]["agent_key"] == JUDGE_AGENT_KEY


def test_the_build_workflow_calls_the_pass_without_letting_it_fail_the_build():
    """Read from the source, because the alternative is a Temporal test that would prove the
    same thing far more slowly. The call must sit inside a try/except, like `provision_preview`
    — an accessibility judgment is not worth a build."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] /
              "orchestration/build_workflow.py").read_text(encoding="utf-8")
    index = source.index("run_a11y_ai_pass")
    window = source[index - 400:index + 400]
    assert "try:" in window and "except ActivityError" in window


def test_the_judgment_run_publishes_its_report_even_when_it_ends_badly():
    """`finally`, not "after". The incomplete run is exactly the one whose report matters most:
    its unjudged elements have just been recorded as `uncertain` for a human, and without a
    report nobody can see them."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] /
              "orchestration/activities.py").read_text(encoding="utf-8")
    index = source.index("finish_ai_pass(tenant_id=")
    assert "finally:" in source[index - 600:index]


# ══ the pass is wired to nothing it should not be ══════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_rls_hides_one_tenants_scan_from_another():
    """Non-negotiable #6 on the new table, proven on a connection opened as the non-superuser
    app role — the Django test connection is the privileged migration role and bypasses RLS
    entirely. A scan names the routes of a client's application and quotes the selectors on
    them, which is a map of an unreleased product."""
    import json

    import psycopg
    from django.conf import settings
    from django.db import connection

    from apps.a11y.capture import parse_capture as _parse

    a = Tenant.objects.create(name="A")
    b = Tenant.objects.create(name="B")
    for tenant, mark in ((a, "A-secret"), (b, "B-secret")):
        project = Project.objects.create(tenant=tenant, name="p")
        ingest_screen(
            tenant_id=str(tenant.id), project_id=str(project.id),
            screen=_parse(json.dumps(_screen(route=f"/{mark}")))[0],
            object_store=InMemoryObjectStore(),
        )

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
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [str(a.id)])
            cur.execute("SELECT DISTINCT route FROM a11y_a11yscreenscan")
            assert cur.fetchall() == [("/A-secret",)]

            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [""])
            cur.execute("SELECT count(*) FROM a11y_a11yscreenscan")
            assert cur.fetchone()[0] == 0        # no tenant context -> fail closed
    finally:
        raw.close()


def test_only_the_accessibility_gate_reads_these_findings():
    """This used to assert that NO gate read the findings — QA-08 and QA-15 owned blocking, and
    saying so as a test kept the scope honest. QA-15 has since landed, so the assertion is
    inverted rather than deleted: `apps/gates/a11ygate.py` is allowed to read them, and no other
    gate module may.

    Still deliberately narrow. `apps/gates/wcag.py` is QA-11's design-phase WCAG checklist and
    reads the criteria tables legitimately; what must not spread is a *second* gate reasoning
    about these findings, which is exactly how two definitions of "failing" drift apart.
    """
    from pathlib import Path

    gates = Path(__file__).resolve().parents[1] / "apps/gates"
    watched = ("a11y_report", "apps.a11y.report", "merge_run", "A11yFinding")
    hits = {
        p.name: [w for w in watched if w in p.read_text(encoding="utf-8")]
        for p in gates.glob("*.py")
        if p.name != "a11ygate.py"
    }
    early = {name: found for name, found in hits.items() if found}
    assert early == {}, f"accessibility findings reached another gate module: {early}"


# ══ asking again about what nothing ever looked at (task R1) ═══════════════════════════
#
# A judging run that dies part-way files every element it never reached as `uncertain — not
# judged`, so nothing dispatched vanishes. That is right, and it leaves those elements sitting
# on a person for a reason that has nothing to do with them: not "a check looked and could not
# decide", but "nothing looked". These are about telling those two apart and offering only the
# second back to the machine — and about the fact that doing so visits no page at all.


def _dispatched_run(world):
    """A judging run over this capture, with the batches a judge would be handed."""
    from apps.a11y.aipass import start_ai_pass

    _ingest(world)
    out = start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"],
                        trigger=FakeTrigger(world))
    assert out["started"] is True
    return out["judge_run_id"]


def _element_ids(world, judge_run_id):
    """Every dispatched element as (id, criteria) — paging through, the way the judge does."""
    from apps.a11y import judge as judge_mod

    out, start = [], 0
    while start is not None:
        batch = judge_mod.batch_for_run(world["t"], judge_run_id, start=start)
        out += [(e["id"], list(e.get("criteria") or []))
                for screen in batch["screens"] for e in screen["elements"]]
        start = batch["next_start"]
    return out


def test_an_answered_uncertain_is_never_offered_back_to_the_machine(world):
    """The one piece of real design in this task. *"A check looked at this and could not
    decide"* is a verdict, it belongs to the person in the review queue, and re-asking about it
    would quietly recycle the queue's own contents through the machine. *"Nothing looked at
    this"* is work that did not happen."""
    from apps.a11y import judge as judge_mod
    from apps.a11y.aipass import unanswered_for_capture

    judge_run_id = _dispatched_run(world)
    ids = _element_ids(world, judge_run_id)
    assert len(ids) > 1, "the fixture needs at least two elements for this to mean anything"

    # The agent looks at the first and honestly cannot decide. Recorded the way its own tool
    # records it — against the run, which is what separates it from a platform fallback.
    judge_mod.record_finding(
        tenant_id=world["t"], run_id=judge_run_id, project_id=world["p"],
        element_id=ids[0][0], criteria=ids[0][1], verdict="uncertain", confidence=0.2,
        evidence="the image may be decorative; the page does not say",
    )
    # …and then the run dies. Everything it never reached is filed, and remembered.
    with pytest.raises(WriteCompletenessError):
        judge_mod.verify_judgment_completeness(tenant_id=world["t"], run_id=judge_run_id)

    offered = unanswered_for_capture(
        tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    assert len(offered) == len(ids) - 1, "everything except the one a check actually answered"


def test_asking_again_dispatches_only_those_and_visits_no_page(world):
    """No browser, no companion, no route re-opened: the markup, the styles and the screenshot
    crop were all stored when the pages were captured."""
    from apps.a11y import judge as judge_mod
    from apps.a11y.aipass import rejudge_capture, unanswered_for_capture

    judge_run_id = _dispatched_run(world)
    ids = _element_ids(world, judge_run_id)
    judge_mod.record_finding(
        tenant_id=world["t"], run_id=judge_run_id, project_id=world["p"],
        element_id=ids[0][0], criteria=ids[0][1], verdict="pass", confidence=0.95,
        evidence="the alt text describes the image",
    )
    with pytest.raises(WriteCompletenessError):
        judge_mod.verify_judgment_completeness(tenant_id=world["t"], run_id=judge_run_id)
    expected = unanswered_for_capture(
        tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])

    again = FakeTrigger(world)
    out = rejudge_capture(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"],
                          triggered_by=str(world["user"].id), trigger=again)
    # It goes through the ordinary dispatch, so the second run is a real judging run on the same
    # carrier work item — not a path of its own.
    assert out["asked"] == len(expected)
    assert out["started"] is True
    second = Run.objects.get(id=out["judge_run_id"])
    assert second.id != judge_run_id
    asked_now = {e["content_hash"]
                 for batch in (second.inputs or {}).get("a11y_batches", [])
                 for e in batch["elements"]}
    assert asked_now == set(expected), "exactly the ones nothing looked at, and nothing else"
    assert len(again.calls) == 1, "one more judging run, and nothing else started"


def test_asking_again_when_everything_has_been_looked_at_starts_nothing(world):
    """Said in words rather than starting an engine run that would judge nothing."""
    from apps.a11y.aipass import rejudge_capture

    _ingest(world)
    out = rejudge_capture(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"],
                          trigger=FakeTrigger(world))
    assert out["started"] is False and out["asked"] == 0
    assert "has been looked at" in out["reason"]


def test_asking_again_puts_the_audit_back_to_checking_what_was_found(world):
    """Because that is what is happening. The running panel and the audit's own row then say so
    in the words they already use, and it completes through the ordinary closing step."""
    from apps.a11y import judge as judge_mod
    from apps.a11y.aipass import _remember_source_run, rejudge_capture
    from apps.a11y.models import A11yBaselineAudit

    audit = A11yBaselineAudit.objects.create(
        tenant=world["tenant"], project=world["project"], routes=["/checkout"],
        status=A11yBaselineAudit.Status.COMPLETE)
    _ingest(world)
    # The capture belongs to the audit, exactly as a baseline audit's does.
    A11yCandidateBundle.objects.filter(
        tenant=world["tenant"], run_key=world["run_id"]).update(run_key=str(audit.id))

    from apps.a11y.aipass import start_ai_pass

    started = start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id),
                            trigger=FakeTrigger(world),
                            # An audit has no Run to read the user off, so the caller says who —
                            # exactly as `finish_baseline_audit` does.
                            triggered_by=str(world["user"].id))
    _remember_source_run(world["t"], started["judge_run_id"], str(audit.id))
    audit.summary = {"ai_pass": {"judge_run_id": started["judge_run_id"],
                                 "dispatched": started["dispatched"]}}
    audit.save(update_fields=["summary"])
    with pytest.raises(WriteCompletenessError):
        judge_mod.verify_judgment_completeness(tenant_id=world["t"],
                                               run_id=started["judge_run_id"])

    out = rejudge_capture(tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id),
                          trigger=FakeTrigger(world), triggered_by=str(world["user"].id))
    assert out["started"] is True
    audit.refresh_from_db()
    assert audit.status == A11yBaselineAudit.Status.JUDGING


def test_the_count_on_the_button_matches_what_asking_again_would_ask(world):
    """The screen counts from what each pass recorded about itself; the re-judge recomputes the
    real set. Two roads to one number, and a screen that offers to check twelve things and then
    checks nine is a screen nobody trusts again."""
    from apps.a11y import judge as judge_mod
    from apps.a11y.aipass import _remember_source_run, start_ai_pass, unanswered_for_capture
    from apps.a11y.models import A11yBaselineAudit

    audit = A11yBaselineAudit.objects.create(
        tenant=world["tenant"], project=world["project"], routes=["/checkout"],
        status=A11yBaselineAudit.Status.COMPLETE)
    _ingest(world)
    A11yCandidateBundle.objects.filter(
        tenant=world["tenant"], run_key=world["run_id"]).update(run_key=str(audit.id))
    started = start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id),
                            trigger=FakeTrigger(world),
                            # An audit has no Run to read the user off, so the caller says who —
                            # exactly as `finish_baseline_audit` does.
                            triggered_by=str(world["user"].id))
    _remember_source_run(world["t"], started["judge_run_id"], str(audit.id))
    audit.summary = {"ai_pass": {"judge_run_id": started["judge_run_id"],
                                 "dispatched": started["dispatched"],
                                 "filed_unjudged": started["filed_unjudged"]}}
    audit.save(update_fields=["summary"])
    with pytest.raises(WriteCompletenessError):
        judge_mod.verify_judgment_completeness(tenant_id=world["t"],
                                               run_id=started["judge_run_id"])

    counted = unanswered_counts(world["t"], [audit])[str(audit.id)]
    actual = unanswered_for_capture(
        tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id))
    assert counted == len(actual) > 0


def test_losing_the_record_of_what_was_never_looked_at_no_longer_loses_the_fact(world):
    """The 31 August failure, reproduced by deleting the record outright.

    `_remember_unanswered` writes the list of never-reported-on elements into one JSON field on
    the run, and that list is the ONLY thing separating *"a check looked and could not decide"*
    from *"nothing ever looked at this"* once the fallback verdicts are stored — same verdict,
    same confidence, same run. On 31 August a closing path that ran three times overlapping
    itself had a later, partial count overwrite the true one and 170 became 65.

    The union fix stops a shorter write from shrinking it. This is the other half: the same
    answer read off the verdicts themselves, where the platform's own `NOT_JUDGED` text marks
    each fallback it filed. Deleting the record entirely is a harsher test than the overwrite
    that actually happened, and the answer must not move.
    """
    from apps.a11y import judge as judge_mod
    from apps.a11y.aipass import _remember_source_run, start_ai_pass, unanswered_for_capture
    from apps.a11y.models import A11yBaselineAudit
    from apps.runs.models import Run

    audit = A11yBaselineAudit.objects.create(
        tenant=world["tenant"], project=world["project"], routes=["/checkout"],
        status=A11yBaselineAudit.Status.COMPLETE)
    _ingest(world)
    A11yCandidateBundle.objects.filter(
        tenant=world["tenant"], run_key=world["run_id"]).update(run_key=str(audit.id))
    started = start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id),
                            trigger=FakeTrigger(world), triggered_by=str(world["user"].id))
    _remember_source_run(world["t"], started["judge_run_id"], str(audit.id))
    audit.summary = {"ai_pass": {"judge_run_id": started["judge_run_id"]}}
    audit.save(update_fields=["summary"])
    with pytest.raises(WriteCompletenessError):
        judge_mod.verify_judgment_completeness(tenant_id=world["t"],
                                               run_id=started["judge_run_id"])

    with_record = unanswered_for_capture(
        tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id))
    assert with_record, "nothing was dispatched — the fixture proves nothing"

    # Now destroy the side-record, which is what a repeated close did a partial version of.
    run = Run.objects.get(id=started["judge_run_id"])
    outputs = dict(run.outputs or {})
    assert outputs.pop(judge_mod.UNANSWERED_KEY, None), "the record must have been there to lose"
    run.outputs = outputs
    run.save(update_fields=["outputs"])

    without_record = unanswered_for_capture(
        tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id))
    assert without_record == with_record, (
        "what nothing looked at must be derivable from the verdicts, not only from a field"
    )


def test_an_answer_the_judge_actually_gave_is_still_never_offered_back(world):
    """The guard on the fix above, and the more important half of it.

    Reading `uncertain` rows to find never-looked-at work is one keystroke away from reading
    EVERY `uncertain` — which would hand the review queue's own contents back to the machine and
    quietly recycle a person's job list. What makes it safe is that the match is on the
    platform's own `NOT_JUDGED` sentence, which `record_finding` cannot produce: it requires
    evidence the judge itself supplies, and refuses an `uncertain` with none.
    """
    from apps.a11y import judge as judge_mod
    from apps.a11y.aipass import _remember_source_run, start_ai_pass, unanswered_for_capture
    from apps.a11y.models import A11yBaselineAudit, A11yJudgmentCache

    audit = A11yBaselineAudit.objects.create(
        tenant=world["tenant"], project=world["project"], routes=["/checkout"],
        status=A11yBaselineAudit.Status.COMPLETE)
    _ingest(world)
    A11yCandidateBundle.objects.filter(
        tenant=world["tenant"], run_key=world["run_id"]).update(run_key=str(audit.id))
    started = start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id),
                            trigger=FakeTrigger(world), triggered_by=str(world["user"].id))
    _remember_source_run(world["t"], started["judge_run_id"], str(audit.id))
    audit.summary = {"ai_pass": {"judge_run_id": started["judge_run_id"]}}
    audit.save(update_fields=["summary"])
    with pytest.raises(WriteCompletenessError):
        judge_mod.verify_judgment_completeness(tenant_id=world["t"],
                                               run_id=started["judge_run_id"])

    # Read the verdicts on their own, with the side-record out of the way — otherwise the record
    # would answer for them and this would prove nothing about the new reading.
    from apps.runs.models import Run

    run = Run.objects.get(id=started["judge_run_id"])
    run.outputs = {k: v for k, v in (run.outputs or {}).items() if k != judge_mod.UNANSWERED_KEY}
    run.save(update_fields=["outputs"])

    # One of them is now a real judgement that happens to also be `uncertain` — the judge looked
    # and said, in its own words, that it could not decide. That is a person's job, not the
    # machine's, and the only thing separating it from the row beside it is the evidence text.
    rows = list(A11yJudgmentCache.objects.filter(
        tenant=world["tenant"], run_id=started["judge_run_id"]).order_by("content_hash"))
    assert len(rows) > 1, "need at least two, so the test can tell them apart"
    answered, untouched = rows[0], rows[1]
    answered.evidence = "the contrast could not be measured from the crop supplied"
    answered.save(update_fields=["evidence"])

    offered = unanswered_for_capture(
        tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id))
    assert answered.content_hash not in offered, (
        "an answer a person owns must never be handed back to the machine"
    )
    assert untouched.content_hash in offered, (
        "…while the fallbacks beside it, which nothing ever looked at, still are"
    )


def test_a_verdict_with_no_run_against_it_is_only_ever_the_platforms_own(world):
    """The marker this all rests on, asserted rather than assumed. `unanswered_for_capture`
    reads a null run as *"nothing looked at this"*, which is only true while the agent's own
    tool always records against its run. Three call sites write a verdict; this pins the one
    that must never write a null."""
    import inspect

    from apps.a11y import judge as judge_mod

    source = inspect.getsource(judge_mod.record_finding)
    assert "run_id=run_id" in source, (
        "record_finding must stamp the judge's run on every verdict — a null run is the "
        "platform's way of saying nothing ever looked"
    )
    assert "run_id=None" not in source


def test_a_second_asking_never_offers_up_what_the_first_one_answered(world):
    """The failure mode a re-judge invites: the audit goes on pointing at the run that gave up,
    its recorded list is read again, and the machine is asked to re-decide what it has already
    decided — for ever. Guarded twice: the audit is re-pointed at the new run, and anything with
    a real verdict against it drops out whoever answered it."""
    from apps.a11y import judge as judge_mod
    from apps.a11y.aipass import (
        _remember_source_run,
        rejudge_capture,
        start_ai_pass,
        unanswered_for_capture,
    )
    from apps.a11y.models import A11yBaselineAudit

    audit = A11yBaselineAudit.objects.create(
        tenant=world["tenant"], project=world["project"], routes=["/checkout"],
        status=A11yBaselineAudit.Status.COMPLETE)
    _ingest(world)
    A11yCandidateBundle.objects.filter(
        tenant=world["tenant"], run_key=world["run_id"]).update(run_key=str(audit.id))
    first = start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id),
                          trigger=FakeTrigger(world), triggered_by=str(world["user"].id))
    _remember_source_run(world["t"], first["judge_run_id"], str(audit.id))
    audit.summary = {"ai_pass": {"judge_run_id": first["judge_run_id"],
                                 "dispatched": first["dispatched"],
                                 "filed_unjudged": first["filed_unjudged"]}}
    audit.save(update_fields=["summary"])
    with pytest.raises(WriteCompletenessError):
        judge_mod.verify_judgment_completeness(tenant_id=world["t"],
                                               run_id=first["judge_run_id"])

    out = rejudge_capture(tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id),
                          trigger=FakeTrigger(world), triggered_by=str(world["user"].id))
    assert out["started"] is True

    # The audit now points at the SECOND run, not the one that gave up.
    audit.refresh_from_db()
    assert audit.summary["ai_pass"]["judge_run_id"] == out["judge_run_id"]

    # This time the judge answers everything it was given.
    for element_id, criteria in _element_ids(world, out["judge_run_id"]):
        judge_mod.record_finding(
            tenant_id=world["t"], run_id=out["judge_run_id"], project_id=world["p"],
            element_id=element_id, criteria=criteria, verdict="pass", confidence=0.9,
            evidence="the alt text describes the image")
    judge_mod.verify_judgment_completeness(tenant_id=world["t"], run_id=out["judge_run_id"])

    assert unanswered_for_capture(
        tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id)) == []
    assert unanswered_counts(world["t"], [audit])[str(audit.id)] == 0, (
        "and the button that offers it is gone too")


# ── and what the dispatch never reached at all ──────────────────────────────────────
#
# A pass stops at its own limit and hands the remainder back as `deferred`. Those requests were
# never dispatched and never filed, so neither of the two sources above knew about them: on the
# live run of 21 August an audit closed as COMPLETE with five element-slots never asked about,
# no button offering them, and no sentence anywhere saying so. A quiet success, which is the
# worst failure this capability has.


def test_an_element_the_cap_never_reached_is_offered_back(world):
    """The whole of D1. Not "was it filed" or "did a run drop it" — the direct question: is
    there a verdict for this element anywhere? No verdict means nothing looked at it, whatever
    the reason nothing did."""
    from apps.a11y.aipass import start_ai_pass, unanswered_for_capture
    from apps.a11y.models import A11yJudgmentCache

    _ingest(world)
    out = start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"],
                        trigger=FakeTrigger(world))
    assert out["started"] is True

    # The judge answers everything it was given except one element, and nothing files that one:
    # the shape a cap leaves behind, where the request never reached a run at all.
    from apps.a11y import judge as judge_mod

    ids = _element_ids(world, out["judge_run_id"])
    assert len(ids) > 1
    for element_id, criteria in ids[1:]:
        judge_mod.record_finding(
            tenant_id=world["t"], run_id=out["judge_run_id"], project_id=world["p"],
            element_id=element_id, criteria=criteria, verdict="pass", confidence=0.95,
            evidence="the accessible name describes the image",
        )
    A11yJudgmentCache.objects.filter(
        tenant_id=world["t"], project_id=world["p"]).count()

    offered = unanswered_for_capture(
        tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"])
    assert len(offered) == 1, "the one element nothing ever recorded an answer for"


def test_an_element_that_was_answered_is_not_offered_back_as_never_looked_at(world):
    """The other half of the same rule, and the one that stops it recycling the review queue.
    A verdict — including an `uncertain` a check genuinely reached — means something DID look."""
    from apps.a11y import judge as judge_mod
    from apps.a11y.aipass import start_ai_pass, unanswered_for_capture

    _ingest(world)
    out = start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"],
                        trigger=FakeTrigger(world))
    for element_id, criteria in _element_ids(world, out["judge_run_id"]):
        judge_mod.record_finding(
            tenant_id=world["t"], run_id=out["judge_run_id"], project_id=world["p"],
            element_id=element_id, criteria=criteria, verdict="uncertain", confidence=0.2,
            evidence="the page does not say whether this is decorative",
        )

    assert unanswered_for_capture(
        tenant_id=world["t"], project_id=world["p"], run_id=world["run_id"]) == [], (
        "every one of these belongs to a person; re-asking would recycle the queue"
    )


def test_the_button_counts_what_the_cap_left_behind(world):
    """`unanswered_counts` is the cheap screen count, read from what each pass recorded about
    itself. Before this it read `filed_unjudged` alone, which is zero for a capped pass — so the
    button never appeared for the one case that produced it on the live run."""
    from apps.a11y.baseline import unanswered_counts

    class _Audit:
        id = "0f1e2d3c-4b5a-4967-8899-aabbccddeeff"
        summary = {"ai_pass": {"filed_unjudged": 0, "deferred": 9,
                               "deferred_distinct": 5,
                               "judge_run_id": "", "dispatched": 200}}

    assert unanswered_counts(world["t"], [_Audit()])[_Audit.id] == 5


def test_a_stopped_pass_whose_tail_was_all_repeats_offers_nothing(world):
    """The 21 August audit stopped 5 requests short and lost NOTHING: every one was chrome
    already dispatched earlier in the same run, so one verdict answered it. Counting the raw
    number put a "check the rest" button on an audit with nothing left to check."""
    from apps.a11y.baseline import unanswered_counts

    class _Audit:
        id = "0f1e2d3c-4b5a-4967-8899-aabbccddee03"
        summary = {"ai_pass": {"filed_unjudged": 0, "deferred": 5, "deferred_distinct": 0}}

    assert unanswered_counts(world["t"], [_Audit()])[_Audit.id] == 0


def test_an_audit_from_before_the_distinct_count_existed_claims_nothing(world):
    """No honest number is available for it, and the misleading one is worse than none — the
    same choice the "elements judged" tile made for the same reason."""
    from apps.a11y.baseline import unanswered_counts

    class _Audit:
        id = "0f1e2d3c-4b5a-4967-8899-aabbccddee04"
        summary = {"ai_pass": {"filed_unjudged": 0, "deferred": 5}}

    assert unanswered_counts(world["t"], [_Audit()])[_Audit.id] == 0


def test_the_two_kinds_of_never_asked_are_added_not_confused(world):
    """`filed_unjudged` (there was no judge to ask) and `deferred` (we stopped at the limit) are
    different reasons for the same fact, and both are work that did not happen."""
    from apps.a11y.baseline import unanswered_counts

    class _Audit:
        id = "0f1e2d3c-4b5a-4967-8899-aabbccddee01"
        summary = {"ai_pass": {"filed_unjudged": 3, "deferred": 5,
                               "deferred_distinct": 5}}

    assert unanswered_counts(world["t"], [_Audit()])[_Audit.id] == 8


def test_a_pass_that_reached_everything_still_counts_nothing(world):
    from apps.a11y.baseline import unanswered_counts

    class _Audit:
        id = "0f1e2d3c-4b5a-4967-8899-aabbccddee02"
        summary = {"ai_pass": {"filed_unjudged": 0, "deferred": 0,
                               "deferred_distinct": 0}}

    assert unanswered_counts(world["t"], [_Audit()])[_Audit.id] == 0


def test_a_second_pass_never_describes_itself_in_the_first_ones_words(world):
    """The 21 August live failure, pinned.

    A re-judge merged four keys onto the pass that stopped and inherited everything else, so
    `distinct`, `deferred`, `deferred_distinct` and `reason` went on describing the run that
    gave up. Every screen reading them then described THIS pass in the last one's words: a
    re-judge of six elements reported "0 of 126"; a pass that hit no limit said it had stopped
    at one; and the stale `deferred_distinct` kept the Check-the-rest button on an audit with
    nothing left, offering elements it had just answered.

    Asserted on the fields rather than on any sentence, because the sentence is the symptom.
    """
    from apps.a11y import judge as judge_mod
    from apps.a11y.aipass import _remember_source_run, rejudge_capture, start_ai_pass
    from apps.a11y.models import A11yBaselineAudit

    audit = A11yBaselineAudit.objects.create(
        tenant=world["tenant"], project=world["project"], routes=["/checkout"],
        status=A11yBaselineAudit.Status.COMPLETE)
    _ingest(world)
    A11yCandidateBundle.objects.filter(
        tenant=world["tenant"], run_key=world["run_id"]).update(run_key=str(audit.id))
    first = start_ai_pass(tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id),
                          trigger=FakeTrigger(world), triggered_by=str(world["user"].id))
    _remember_source_run(world["t"], first["judge_run_id"], str(audit.id))
    # A first pass that stopped at its own limit, written exactly as the dispatcher writes it,
    # plus the audit-level facts that belong to the CAPTURE and must survive.
    audit.summary = {
        "asked": 12, "opened": 12, "never_reported": [],
        "ai_pass": {"judge_run_id": first["judge_run_id"],
                    "dispatched": 200, "distinct": 126,
                    "deferred": 12, "deferred_distinct": 6,
                    "filed_unjudged": 0,
                    "reason": "Stopped at this run's limit of 200 — 12 item(s) still need "
                              "judging. Run the check again to continue from here."},
    }
    audit.save(update_fields=["summary"])
    with pytest.raises(WriteCompletenessError):
        judge_mod.verify_judgment_completeness(tenant_id=world["t"],
                                               run_id=first["judge_run_id"])

    out = rejudge_capture(tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id),
                          trigger=FakeTrigger(world), triggered_by=str(world["user"].id))
    assert out["started"] is True
    audit.refresh_from_db()
    second = audit.summary["ai_pass"]

    # Nothing of the pass that stopped survives into the account of the one that ran.
    assert 0 < second["distinct"] <= out["asked"], (
        "the denominator on the running panel is THIS pass's element count, not the last one's"
    )
    assert second["deferred"] == 0
    assert second["deferred_distinct"] == 0
    assert not second["reason"], "the stopped-at-the-limit sentence belonged to the first pass"
    assert second["dispatched"] != 200

    # It says what it is, and when — the screen has no other way to tell a second pass from an
    # audit that has started over, and the audit's own `created_at` is the first pass's.
    assert second["rejudged"] is True
    assert second["rejudged_at"]
    assert second["rejudged_asked"] == out["asked"] > 0

    # And the facts about the CAPTURE are untouched: a second judging pass visits no page.
    assert audit.summary["asked"] == 12
    assert audit.summary["opened"] == 12


def test_asking_again_and_finding_nothing_left_takes_the_button_away(world):
    """A control that cannot be cleared by using it is worse than no control.

    The screen's count is a cheap sum of what each pass recorded about itself; the re-judge
    recomputes the real set from the capture. They can legitimately disagree — an element may
    since have been answered by another run, or have dropped out of the capture. Before this,
    that disagreement was permanent: the button offered work that did not exist, pressing it
    wrote nothing (only the started path touched the summary), so it offered the same work
    again for ever.
    """
    from apps.a11y.aipass import rejudge_capture, unanswered_for_capture
    from apps.a11y.models import A11yBaselineAudit

    audit = A11yBaselineAudit.objects.create(
        tenant=world["tenant"], project=world["project"], routes=["/checkout"],
        status=A11yBaselineAudit.Status.COMPLETE)
    _ingest(world)
    A11yCandidateBundle.objects.filter(
        tenant=world["tenant"], run_key=world["run_id"]).update(run_key=str(audit.id))
    # Everything in the capture already has a verdict, so there is genuinely nothing to ask.
    for request in requests_for(world["t"], world["p"], str(audit.id)):
        record_verdict(
            tenant_id=world["t"], project_id=world["p"], run_id=None,
            content_hash=request.content_hash,
            judgment=A11yJudgment(verdict=A11Y_PASS, criteria=["1.1.1"], confidence=0.9,
                                  evidence="answered", suggested_fix=""))
    # …but the audit's own summary still says six were left behind, which is what the badge and
    # the button read.
    audit.summary = {"ai_pass": {"filed_unjudged": 0, "deferred": 12, "deferred_distinct": 6,
                                 "reason": "Stopped at this run's limit of 200."}}
    audit.save(update_fields=["summary"])
    assert unanswered_counts(world["t"], [audit])[str(audit.id)] == 6
    assert unanswered_for_capture(
        tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id)) == []

    out = rejudge_capture(tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id),
                          trigger=FakeTrigger(world), triggered_by=str(world["user"].id))
    assert out["started"] is False
    assert "every element" in out["reason"]

    audit.refresh_from_db()
    assert audit.summary["ai_pass"]["nothing_left"] is True
    assert unanswered_counts(world["t"], [audit])[str(audit.id)] == 0, (
        "pressing the button has to be able to make it go away"
    )
    assert not audit.summary["ai_pass"]["reason"], (
        "and the sentence explaining the count goes with the count"
    )
    # No screen reads these two on a closed audit — they are only asked for while one is in
    # flight, and this path only runs on one that has finished. They are cleared anyway: one
    # pass's numbers left inside another pass's record is the exact shape of the bug that put
    # "0 of 126" on a re-judge of six, and that one was unreachable right up until it wasn't.
    assert audit.summary["ai_pass"]["distinct"] == 0
    assert audit.summary["ai_pass"]["dispatched"] == 0
