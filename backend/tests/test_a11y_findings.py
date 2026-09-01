"""QA-12a — the accessibility findings ledger + review queue.

A finding had nowhere to live. QA-12's report is rebuilt from scratch every time it is asked
for — a snapshot, not a record — so nothing could say "this is the same broken button we found
last week", and four acceptance criteria elsewhere in this backlog were unimplementable.

Against the task's acceptance criteria:

  AC1  the same problem on two runs is one row with an updated last-seen run
  AC2  a finding that disappears and returns reuses the original row
  AC3  two different elements failing one criterion stay two findings
  AC4  an unnormalisable selector uses the fallback key and is flagged low-stability
  AC5  a second tenant cannot see the first's rows, proven at the database
  AC6  ≥ 90% coverage on the new code

**The rule these tests exist to hold in place** is the one that is cheap to get wrong and
expensive to get wrong: *resolution is by absence, but only where we actually looked.* A finding
on a screen this run never visited must survive. So must a finding on an element that WAS
captured this run and never judged — "no answer" is not "fixed", and treating it as such would
close a real accessibility defect on the strength of a judgment run that fell over. Both are
asserted directly, because neither shows up in a row count.
"""
from __future__ import annotations

import base64
import io
import json

import pytest
from PIL import Image as PILImage

from apps.a11y.capture import parse_capture
from apps.a11y.dispatch import record_verdict
from apps.a11y.findings import (
    DEFAULT_SEVERITY,
    fingerprint,
    record_run_findings,
    review_queue,
    severity_for,
)
from apps.a11y.ingest import ingest_screen, requests_for
from apps.a11y.models import A11yFinding, WcagCriterion
from apps.a11y.report import (
    SOURCE_AI,
    SOURCE_RULE,
    MergedReport,
    ReportRow,
    merge_run,
    publish_report,
)
from apps.a11y.selectors import is_positional, normalise
from apps.a11y.triage import TRIAGE_FAILURE, TRIAGE_PASS, TRIAGE_REVIEW
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from integrations.types import A11Y_FAIL, A11Y_PASS, A11yJudgment
from storage.object_store import InMemoryObjectStore

_STYLES = {
    "color": "rgb(0, 0, 0)", "background-color": "transparent",
    "text-decoration-line": "none", "font-size": "16px", "font-weight": "400",
    "border-style": "none",
}


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Shop")
    story = WorkItem.objects.create(tenant=tenant, project=project, title="Checkout")
    spec = AgentSpec.objects.create(tenant=tenant, key="09b_test_automation", body_ref="x",
                                    semver="1.0.0")
    # The standard is platform-wide and already loaded by its own migration, so these are
    # `get_or_create` rather than `create` — the test wants the two levels present, not a second
    # copy of a table that is deliberately shared. 9.9.9 is left absent on purpose, so the
    # unknown-criterion fallback is exercised against a real absence rather than a mock.
    WcagCriterion.objects.get_or_create(
        version="2.2", number="1.1.1",
        defaults={"handle": "Non-text Content", "level": "A", "slug": "non-text-content",
                  "text": "…"})
    WcagCriterion.objects.get_or_create(
        version="2.2", number="1.4.3",
        defaults={"handle": "Contrast (Minimum)", "level": "AA", "slug": "contrast-minimum",
                  "text": "…"})
    return {"t": str(tenant.id), "p": str(project.id), "tenant": tenant, "project": project,
            "story": story, "spec": spec}


def _run(world, workflow_id: str) -> Run:
    return Run.objects.create(tenant=world["tenant"], work_item=world["story"],
                              agent_spec=world["spec"], temporal_workflow_id=workflow_id)


def _row(**over) -> ReportRow:
    base = {
        "source": SOURCE_AI, "outcome": TRIAGE_FAILURE, "criteria": ("1.1.1",),
        "route": "/checkout", "selector": "img.hero",
        "evidence": 'alt="IMG_1234" is a filename', "confidence": 0.93,
        "suggested_fix": "describe what the image shows", "checker": "alt",
        "verdict": A11Y_FAIL, "model": "claude-opus-5", "prompt_version": "a11y-judge-1",
    }
    base.update(over)
    return ReportRow(**base)


def _report(rows, *, routes=("/checkout",), unjudged=()) -> MergedReport:
    return MergedReport(rows=list(rows), routes=list(routes), unjudged=list(unjudged))


def _record(world, run, rows, **kw):
    return record_run_findings(tenant_id=world["t"], project_id=world["p"], run_id=str(run.id),
                               report=_report(rows, **kw))


def _findings(world):
    return list(A11yFinding.objects.filter(tenant_id=world["t"]).order_by("selector"))


# ══ the fingerprint ════════════════════════════════════════════════════════════════

def test_the_same_problem_hashes_the_same_however_it_is_spelled():
    assert fingerprint(route="/a", selector="button.pay", criterion="4.1.2", checker="semantics") \
        == fingerprint(route="/a", selector="  button.pay  ", criterion="4.1.2",
                       checker="semantics")


@pytest.mark.parametrize("changed", [
    {"route": "/other"},
    {"selector": "button.other"},
    {"criterion": "1.3.1"},
    {"checker": "alt"},
])
def test_changing_any_part_of_the_identity_makes_it_a_different_problem(changed):
    base = {"route": "/a", "selector": "button.pay", "criterion": "4.1.2",
            "checker": "semantics"}
    assert fingerprint(**base) != fingerprint(**{**base, **changed})


def test_moving_text_between_the_parts_cannot_collide():
    """Length-prefixed, like `dispatch.content_hash`. Without it `/ab` + `c` and `/a` + `bc`
    would be the same finding."""
    assert fingerprint(route="/ab", selector="c", criterion="1.1.1") != \
        fingerprint(route="/a", selector="bc", criterion="1.1.1")


def test_the_identity_uses_the_primary_criterion_not_the_whole_list(world):
    """A judgment can breach several criteria at once (D-A11Y-2) and all of them are stored —
    but a later run whose judge names 4.1.2 alone is reporting the same broken button and has
    to find the same row."""
    run_a, run_b = _run(world, "w1"), _run(world, "w2")
    _record(world, run_a, [_row(criteria=("4.1.2", "1.3.1"), checker="semantics",
                                selector="div.fake-btn")])
    _record(world, run_b, [_row(criteria=("4.1.2",), checker="semantics",
                                selector="div.fake-btn")])
    assert len(_findings(world)) == 1


def test_the_fingerprint_is_not_the_judgment_cache_key(world):
    """The two keys answer different questions and merging them would break both. Editing an
    element's markup gives it a new `content_hash` — the model must be asked again — while this
    stays the same, because it is still the same button on the same screen breaching the same
    criterion."""
    from apps.a11y.dispatch import content_hash
    from integrations.types import A11yCandidate

    before = A11yCandidate(selector="img.hero", html="<img alt='a'>", route="/checkout")
    after = A11yCandidate(selector="img.hero", html="<img alt='a photo'>", route="/checkout")
    assert content_hash("alt", before) != content_hash("alt", after)
    assert fingerprint(route="/checkout", selector="img.hero", criterion="1.1.1",
                       checker="alt") == \
        fingerprint(route="/checkout", selector="img.hero", criterion="1.1.1", checker="alt")


# ══ AC1 — the same problem twice is one row ════════════════════════════════════════

def test_the_same_problem_on_two_runs_is_one_row_with_a_new_last_seen(world):
    run_a, run_b = _run(world, "w1"), _run(world, "w2")
    first = _record(world, run_a, [_row()])
    second = _record(world, run_b, [_row()])

    rows = _findings(world)
    assert len(rows) == 1
    assert len(first["opened"]) == 1 and first["seen_again"] == []
    assert second["opened"] == [] and len(second["seen_again"]) == 1
    assert str(rows[0].first_seen_run_id) == str(run_a.id)
    assert str(rows[0].last_seen_run_id) == str(run_b.id)


def test_a_re_run_updates_what_the_finding_says(world):
    """The identity is stable; the detail is not. A second run whose judge is more confident,
    or whose evidence is better, must improve the row rather than be discarded."""
    run_a, run_b = _run(world, "w1"), _run(world, "w2")
    _record(world, run_a, [_row(confidence=0.81, evidence="probably a filename")])
    _record(world, run_b, [_row(confidence=0.97, evidence='alt="IMG_1234" is a filename')])
    row = _findings(world)[0]
    assert row.confidence == pytest.approx(0.97)
    assert "IMG_1234" in row.evidence


# ══ AC2 — a problem that comes back reuses its row ═════════════════════════════════

def test_a_finding_that_disappears_and_returns_reuses_the_original_row(world):
    run_a, run_b, run_c = _run(world, "w1"), _run(world, "w2"), _run(world, "w3")
    _record(world, run_a, [_row()])
    original = _findings(world)[0].id

    # Fixed: the element now passes, so nothing is recorded for it and its route was covered.
    _record(world, run_b, [_row(outcome=TRIAGE_PASS, verdict=A11Y_PASS)])
    assert _findings(world)[0].status == A11yFinding.Status.RESOLVED

    # ...and it regresses.
    out = _record(world, run_c, [_row()])
    rows = _findings(world)
    assert len(rows) == 1, "one problem, not two"
    assert rows[0].id == original
    assert rows[0].status == A11yFinding.Status.OPEN
    assert out["opened"] == [], "reopened, never opened again"


def test_a_passing_element_creates_no_row_at_all(world):
    _record(world, _run(world, "w1"), [_row(outcome=TRIAGE_PASS, verdict=A11Y_PASS)])
    assert _findings(world) == []


# ══ AC3 — two elements, one criterion, two findings ═══════════════════════════════

def test_two_elements_failing_the_same_criterion_are_two_findings(world):
    _record(world, _run(world, "w1"), [
        _row(selector="img.hero"),
        _row(selector="img.footer"),
    ])
    assert [f.selector for f in _findings(world)] == ["img.footer", "img.hero"]


def test_one_element_failing_two_criteria_is_two_findings(world):
    """Two different requirements, two different fixes, two rows. Distinct from D-A11Y-2's
    case, which is ONE judgment naming several criteria at once."""
    _record(world, _run(world, "w1"), [
        _row(criteria=("1.3.1",), checker="semantics", selector="div.fake-btn"),
        _row(criteria=("4.1.2",), checker="semantics", selector="div.fake-btn"),
    ])
    assert len(_findings(world)) == 2


# ══ AC4 — a weak handle is flagged, never dropped ═════════════════════════════════

def test_a_positional_selector_is_recorded_and_flagged_low_stability(world):
    """Ingest substitutes `/route#index` when a capture gave no selector. That row's identity is
    "where it sat on the page", so a reorder records the problem again — worth having, worth
    saying."""
    _record(world, _run(world, "w1"), [_row(selector="/checkout#12")])
    row = _findings(world)[0]
    assert row.stable is False
    assert row.selector == "/checkout#12", "recorded, not dropped"


def test_a_real_selector_is_not_flagged(world):
    _record(world, _run(world, "w1"), [_row(selector="img.hero")])
    assert _findings(world)[0].stable is True


@pytest.mark.parametrize("selector,route,expected", [
    ("/checkout#12", "/checkout", True),
    ("/checkout #12", "/checkout", False),          # a descendant selector, not our fallback
    ("img.hero", "/checkout", False),
    ("/checkout#hash", "/checkout", False),         # an anchor, not an index
    ("", "/checkout", False),
    ("/other#3", "/checkout", False),
])
def test_which_selectors_count_as_the_platforms_own_fallback(selector, route, expected):
    assert is_positional(selector, route) is expected


def test_a_page_given_selector_is_never_guessed_at():
    """Deliberately NOT flagged: a hashed class or an `nth-child` chain churns between builds
    and would be the better thing to catch — but which patterns are volatile is a guess until
    the rules have met real applications, and a wrong guess merges two different elements.
    Pinned so that changing it is a decision someone makes."""
    assert is_positional("div:nth-child(4) > button.css-1x2y3z", "/checkout") is False


# ══ severity comes from the standard ══════════════════════════════════════════════

def test_a_level_a_breach_is_critical_and_a_level_aa_breach_is_high(world):
    _record(world, _run(world, "w1"), [
        _row(criteria=("1.1.1",), selector="img.hero"),
        _row(criteria=("1.4.3",), checker="", source=SOURCE_RULE, confidence=None,
             selector=".btn-secondary", verdict=""),
    ])
    by_selector = {f.selector: f for f in _findings(world)}
    assert by_selector["img.hero"].severity == "critical"
    assert by_selector["img.hero"].wcag_level == "A"
    assert by_selector[".btn-secondary"].severity == "high"
    assert by_selector[".btn-secondary"].wcag_level == "AA"


def test_a_criterion_we_cannot_read_falls_back_to_high_and_says_the_level_is_unknown(world):
    """The safe direction. Severity is what decides whether a defect opens (QA-14), so an
    unknown must surface rather than be buried at Medium — and the blank level is what stops a
    reader believing it was measured."""
    _record(world, _run(world, "w1"), [_row(criteria=("9.9.9",), checker="alt")])
    row = _findings(world)[0]
    assert row.severity == DEFAULT_SEVERITY == "high"
    assert row.wcag_level == ""


def test_the_scanners_own_impact_is_kept_beside_our_severity_never_instead_of_it(world):
    _record(world, _run(world, "w1"), [
        _row(criteria=("1.4.3",), source=SOURCE_RULE, checker="", confidence=None,
             impact="serious", verdict="")])
    row = _findings(world)[0]
    assert row.severity == "high", "ours, from the conformance level"
    assert row.impact == "serious", "theirs, verbatim"


@pytest.mark.parametrize("level,expected", [
    ("A", "critical"), ("AA", "high"), ("aa", "high"), ("AAA", "medium"), ("", "high"),
])
def test_the_level_to_severity_mapping(level, expected):
    assert severity_for(level) == expected


# ══ the rule this file exists for: resolve only where we looked ═══════════════════

def test_a_finding_on_a_screen_this_run_never_visited_survives(world):
    run_a, run_b = _run(world, "w1"), _run(world, "w2")
    _record(world, run_a, [_row(route="/checkout"), _row(route="/cart", selector="img.cart")])
    # The second run only covered /checkout.
    _record(world, run_b, [_row(route="/checkout")], routes=("/checkout",))

    by_route = {f.route: f for f in _findings(world)}
    assert by_route["/checkout"].status == A11yFinding.Status.OPEN
    assert by_route["/cart"].status == A11yFinding.Status.OPEN, \
        "we did not look at /cart — its finding is not fixed"


def test_a_finding_on_an_element_that_was_captured_but_never_judged_survives(world):
    """The half that is easy to miss. The route WAS covered, so the route rule alone would
    resolve this — but the element got no answer, and no answer is not a fix."""
    run_a, run_b = _run(world, "w1"), _run(world, "w2")
    _record(world, run_a, [_row()])
    _record(world, run_b, [], unjudged=[
        {"route": "/checkout", "selector": "img.hero", "checker": "alt", "reason": "…"}])
    assert _findings(world)[0].status == A11yFinding.Status.OPEN


def test_a_finding_whose_element_was_judged_clean_does_resolve(world):
    run_a, run_b = _run(world, "w1"), _run(world, "w2")
    _record(world, run_a, [_row()])
    _record(world, run_b, [_row(outcome=TRIAGE_PASS, verdict=A11Y_PASS)])
    assert _findings(world)[0].status == A11yFinding.Status.RESOLVED


def test_a_run_that_found_nothing_anywhere_resolves_nothing_it_did_not_cover(world):
    run_a, run_b = _run(world, "w1"), _run(world, "w2")
    _record(world, run_a, [_row()])
    _record(world, run_b, [], routes=())
    assert _findings(world)[0].status == A11yFinding.Status.OPEN


# ══ the review queue ══════════════════════════════════════════════════════════════

def test_the_queue_holds_what_a_person_has_to_decide(world):
    _record(world, _run(world, "w1"), [
        _row(outcome=TRIAGE_REVIEW, confidence=0.42, selector="img.hero"),
        _row(outcome=TRIAGE_FAILURE, selector="img.footer"),
    ])
    queue = review_queue(world["t"], world["p"])
    assert [f.selector for f in queue] == ["img.hero"], "a failure is a defect, not a question"


def test_the_queue_puts_the_worst_first(world):
    _record(world, _run(world, "w1"), [
        _row(outcome=TRIAGE_REVIEW, criteria=("1.4.3",), selector="b.aa", checker="color"),
        _row(outcome=TRIAGE_REVIEW, criteria=("1.1.1",), selector="a.a"),
    ])
    assert [f.severity for f in review_queue(world["t"], world["p"])] == ["critical", "high"]


def test_a_resolved_finding_leaves_the_queue(world):
    run_a, run_b = _run(world, "w1"), _run(world, "w2")
    _record(world, run_a, [_row(outcome=TRIAGE_REVIEW, confidence=0.42)])
    _record(world, run_b, [_row(outcome=TRIAGE_PASS, verdict=A11Y_PASS)])
    assert review_queue(world["t"], world["p"]) == []


def test_a_decided_finding_leaves_the_queue(world):
    """Being in the queue IS "needs review and nobody has ruled on it" — a query, not a second
    table, so there is no state to keep in step. QA-23 owns the deciding (including two
    reviewers opening one item), which is why nothing here writes `adjudication`."""
    _record(world, _run(world, "w1"), [_row(outcome=TRIAGE_REVIEW, confidence=0.42)])
    found = _findings(world)[0]
    found.adjudication = A11yFinding.Adjudication.CONFIRMED
    found.save(update_fields=["adjudication"])
    assert review_queue(world["t"], world["p"]) == []


def test_the_queue_can_be_read_across_a_whole_workspace(world):
    other = Project.objects.create(tenant=world["tenant"], name="Second")
    _record(world, _run(world, "w1"), [_row(outcome=TRIAGE_REVIEW, confidence=0.42)])
    record_run_findings(tenant_id=world["t"], project_id=str(other.id), run_id=None,
                        report=_report([_row(outcome=TRIAGE_REVIEW, confidence=0.4,
                                             route="/other")], routes=("/other",)))
    assert len(review_queue(world["t"])) == 2
    assert len(review_queue(world["t"], world["p"])) == 1
    assert len(review_queue(world["t"], limit=1)) == 1


# ══ the audit trail rides along ═══════════════════════════════════════════════════

def test_a_finding_records_what_produced_it(world):
    _record(world, _run(world, "w1"), [_row()])
    row = _findings(world)[0]
    assert row.model == "claude-opus-5"
    assert row.prompt_version == "a11y-judge-1"
    assert row.verdict == A11Y_FAIL and row.outcome == TRIAGE_FAILURE


def test_a_measurement_carries_no_model_and_no_confidence(world):
    _record(world, _run(world, "w1"), [
        _row(source=SOURCE_RULE, checker="", confidence=None, verdict="",
             model="", prompt_version="", rule_id="color-contrast", criteria=("1.4.3",))])
    row = _findings(world)[0]
    assert row.model == "" and row.confidence is None
    assert row.rule_id == "color-contrast"


# ══ wired to the merge, from one pass over the data ═══════════════════════════════

def _png() -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (400, 300), (200, 40, 40)).save(buf, format="PNG")
    return buf.getvalue()


def _screen() -> dict:
    return {
        "route": "/checkout", "url": "http://localhost:5173/checkout",
        "screenshot_base64": base64.b64encode(_png()).decode("ascii"),
        "axe_violations": [
            {"rule": "color-contrast", "impact": "serious", "criteria": ["1.4.3"],
             "help": "Elements must meet contrast thresholds", "nodes": [".btn-secondary"]}],
        "elements": [{
            "selector": "img.hero", "tag": "img", "role": "", "attrs": {"alt": "IMG_1234"},
            "text": "", "accessible_name": "IMG_1234", "interactive": False, "rendered": True,
            "styles": dict(_STYLES), "parent_styles": dict(_STYLES),
            "html": '<img class="hero" alt="IMG_1234">', "context": "Our new range",
            "box": {"x": 10, "y": 20, "width": 120, "height": 80},
        }],
    }


def test_publishing_the_report_also_writes_the_ledger(world):
    """One merge, two destinations. Recording them separately would let the document and the
    rows drift into disagreeing about what was found."""
    run = _run(world, "w1")
    ingest_screen(tenant_id=world["t"], project_id=world["p"],
                  screen=parse_capture(json.dumps(_screen()))[0], run_id=str(run.id),
                  object_store=InMemoryObjectStore())
    request = requests_for(world["t"], world["p"], str(run.id))[0]
    record_verdict(
        tenant_id=world["t"], project_id=world["p"], run_id=None,
        content_hash=request.content_hash,
        judgment=A11yJudgment(criteria=("1.1.1",), verdict=A11Y_FAIL, confidence=0.94,
                              evidence='alt="IMG_1234" is a filename',
                              suggested_fix="describe the image", checker="alt"))

    out = publish_report(tenant_id=world["t"], project_id=world["p"], run_id=str(run.id))
    assert len(out["ledger"]["opened"]) == 2, "the AI finding and the scanner's, both filed"

    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=str(run.id))
    reported = {(r.route, normalise(r.selector), r.criteria[0]) for r in report.rows
                if r.outcome != TRIAGE_PASS}
    stored = {(f.route, f.selector, f.criterion) for f in _findings(world)}
    assert stored == reported, "the ledger says exactly what the document says"

    sources = {f.source for f in _findings(world)}
    assert sources == {SOURCE_AI, SOURCE_RULE}


def test_a_report_is_still_published_when_the_ledger_write_fails(world, monkeypatch):
    """Best-effort for the same reason the body is: the report is what a person reads now, and
    losing it because the ledger write failed is the worse trade. The failure is returned and
    logged rather than swallowed — a silent one would mean QA-14 opening no defects with
    nothing anywhere saying why."""
    run = _run(world, "w1")
    ingest_screen(tenant_id=world["t"], project_id=world["p"],
                  screen=parse_capture(json.dumps(_screen()))[0], run_id=str(run.id),
                  object_store=InMemoryObjectStore())
    monkeypatch.setattr(
        "apps.a11y.findings.record_run_findings",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("ledger is unreachable")))

    out = publish_report(tenant_id=world["t"], project_id=world["p"], run_id=str(run.id))
    assert out["artifact_id"], "the report still exists"
    assert out["ledger"]["error"] == "ledger is unreachable", "and the failure is visible"


# ══ AC5 — tenant isolation, at the database ═══════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_rls_hides_one_tenants_findings_from_another():
    """Proven on a connection opened as the non-superuser app role — the Django test connection
    is the privileged migration role and bypasses RLS entirely. This is the most sensitive of
    the three accessibility tables: a row names a route in a client's application, quotes the
    markup on it, and states a conformance failure against a published standard."""
    import psycopg
    from django.conf import settings
    from django.db import connection

    for name, mark in (("A", "/A-secret"), ("B", "/B-secret")):
        tenant = Tenant.objects.create(name=name)
        project = Project.objects.create(tenant=tenant, name="p")
        record_run_findings(
            tenant_id=str(tenant.id), project_id=str(project.id), run_id=None,
            report=MergedReport(rows=[_row(route=mark)], routes=[mark]))
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
            cur.execute("SELECT DISTINCT route FROM a11y_a11yfinding")
            assert cur.fetchall() == [("/A-secret",)]

            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [""])
            cur.execute("SELECT count(*) FROM a11y_a11yfinding")
            assert cur.fetchone()[0] == 0        # no tenant context -> fail closed
    finally:
        raw.close()


# ══ scope kept honest ═════════════════════════════════════════════════════════════

def test_no_defect_opens_from_a_finding_yet():
    """QA-14 owns the bug loop. Asserted so that wiring it is a decision someone makes, rather
    than something that arrives as a side effect."""
    from pathlib import Path

    quality = (Path(__file__).resolve().parents[1] / "apps/quality/services.py").read_text(
        encoding="utf-8")
    assert "A11yFinding" not in quality
    assert "a11y" not in quality.lower().replace("quality", "")


# ══ a page we stopped short of is never written down as clean ══════════════════════

def _coverage(world, *, route, criterion, engine="AI"):
    from apps.a11y.models import A11yCriterionCoverage

    row = A11yCriterionCoverage.objects.filter(
        tenant_id=world["t"], route=route, criterion=criterion, engine=engine).first()
    return row.outcome if row else None


def test_a_page_with_an_unasked_element_is_not_recorded_as_passing(world):
    """The live failure, reduced: borrowed passes plus a silence read as a clean page.

    **What happened on 24 August.** A seventeen-page audit stopped at its cap after eight pages.
    The other nine still collected passing verdicts, because a site's footer is the same markup
    everywhere and one verdict is written back against every page that markup appears on. Their
    own elements — including a table whose column headings are ordinary cells — were never asked
    about, and produced nothing. Eight passes and no failures is indistinguishable from a clean
    page, so `1.3.1` was recorded as **passed on all seventeen**, and the audit sat at status
    `complete` saying so.

    Here that is one page: a pass borrowed from shared markup, and one element of its own that
    nobody asked about. The page must not read as passed.
    """
    run = Run.objects.create(tenant=world["tenant"], work_item=world["story"],
                             agent_spec=world["spec"])

    _record(world, run, [_row(outcome=TRIAGE_PASS, criteria=("1.3.1",), checker="semantics",
                              route="/subject-index", selector="footer ul")],
            routes=("/subject-index",),
            unjudged=[{"route": "/subject-index", "selector": "#subject-table",
                       "checker": "structure", "reason": "the pass stopped at its cap"}])

    assert _coverage(world, route="/subject-index", criterion="1.3.1") == "not_checked", (
        "a page holding an element nobody asked about must not be recorded as passing"
    )


def test_a_page_where_everything_was_asked_still_records_its_passes(world):
    """The other half, and the one that keeps this fix honest.

    A guard that made every page read `not_checked` would satisfy the test above and destroy the
    thing coverage exists for. A finished page reports what it found.
    """
    run = Run.objects.create(tenant=world["tenant"], work_item=world["story"],
                             agent_spec=world["spec"])

    _record(world, run, [_row(outcome=TRIAGE_PASS, criteria=("1.3.1",), checker="semantics",
                              route="/done", selector="footer ul")],
            routes=("/done",))

    assert _coverage(world, route="/done", criterion="1.3.1") == "passed"


def test_a_real_failure_still_outranks_an_unasked_element(world):
    """Not knowing about one element never softens what we do know about another."""
    run = Run.objects.create(tenant=world["tenant"], work_item=world["story"],
                             agent_spec=world["spec"])

    _record(world, run, [_row(outcome=TRIAGE_FAILURE, criteria=("1.3.1",), checker="semantics",
                              route="/mixed", selector="div.fake-heading")],
            routes=("/mixed",),
            unjudged=[{"route": "/mixed", "selector": "#t", "checker": "structure",
                       "reason": "the pass stopped at its cap"}])

    assert _coverage(world, route="/mixed", criterion="1.3.1") == "failed"


def test_an_unasked_element_only_clouds_the_criteria_its_own_check_covers(world):
    """A deferred colour question says nothing about whether the structure was checked.

    Recording the silence against every criterion would be the same lie in the other direction —
    a page reported as unchecked for work that was finished.
    """
    run = Run.objects.create(tenant=world["tenant"], work_item=world["story"],
                             agent_spec=world["spec"])

    _record(world, run, [_row(outcome=TRIAGE_PASS, criteria=("1.3.1",), checker="structure",
                              route="/one-sided", selector="table#t")],
            routes=("/one-sided",),
            unjudged=[{"route": "/one-sided", "selector": "tr.tinted", "checker": "color",
                       "reason": "the pass stopped at its cap"}])

    assert _coverage(world, route="/one-sided", criterion="1.3.1") == "passed"
    assert _coverage(world, route="/one-sided", criterion="1.4.1") == "not_checked"


def test_not_checked_is_not_the_same_fact_as_needs_a_human(world):
    """The distinction the team insisted on, pinned so it cannot quietly collapse.

    `needs_human` means a check looked and could not decide — settled work belonging to a
    person, and a legitimate answer. `not_checked` means the platform has not asked yet, which
    is our own unfinished work and is cheap to finish. Labelling the second as the first hands
    somebody an element nobody looked at, dressed as a judgement that hesitated.
    """
    from apps.a11y.coverage import _RANK

    assert _RANK["not_checked"] < _RANK["passed"], "an unasked element cannot read as clean"
    assert _RANK["not_checked"] < _RANK["needs_human"], (
        "finish the pass before handing anyone a judgement to make"
    )
    assert _RANK["failed"] < _RANK["not_checked"], "a known failure still wins"


def test_a_criterion_still_waiting_on_a_check_claims_no_conformance(world):
    """The end of the chain: what the document a client reads actually says."""
    from apps.a11y.conformance import suggest

    # Owner and engines are named so the pair differs ONLY in whether a page is still
    # waiting, which is what this test is about. Left unnamed, the second call comes back
    # None for the unrelated reason that no engine entitled to settle the criterion was
    # recorded -- see `test_a11y_conformance_guard.py`.
    settled = {"engines": {"rule"}}
    assert suggest({"routes": {"/a": "passed", "/b": "not_checked"}, **settled}, 0,
                   owner="rule") is None, (
        "a criterion is a claim about the pages in scope, not about the ones we reached"
    )
    assert suggest({"routes": {"/a": "passed", "/b": "passed"}, **settled}, 0,
                   owner="rule") is not None
