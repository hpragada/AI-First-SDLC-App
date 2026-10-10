"""QA-14 — accessibility findings become tracked defects that close themselves.

Against the task's acceptance criteria:

  AC1  a failing check opens a defect with the right severity
  AC2  a later run where it passes closes that defect automatically
  AC3  a low-confidence finding goes to the SME queue and never becomes a defect
  AC4  a finding that flips between runs reopens the SAME defect, never a duplicate
  AC5  ≥ 90% coverage on the new code

**The one rule these tests exist for.** Security closes a defect when its finding is absent from
the current list. Copied literally, that would close every accessibility defect on a screen the
run did not happen to visit — a defect "fixed" because nobody looked. So the reconciliation reads
the LEDGER's status, which already carries QA-12a's "only where we looked" rule, and the test
that matters most here is the one that tests `/checkout` and asserts `/cart`'s defect survives.

**Three defect families share one table**, keyed on three different `external_ref` keys —
`test_ref`, `finding`, `a11y_finding`. A shared key would let one reconciliation quietly close
another's rows, so the isolation is asserted in both directions rather than trusted.
"""
from __future__ import annotations

import pytest

from apps.a11y.defects import (
    A11Y_BLOCKING,
    DEFECT_KIND,
    _element_words,
    record_a11y_findings,
)
from apps.a11y.findings import record_run_findings, review_queue
from apps.a11y.models import A11yFinding, WcagCriterion
from apps.a11y.report import SOURCE_AI, SOURCE_RULE, MergedReport, ReportRow
from apps.a11y.triage import TRIAGE_FAILURE, TRIAGE_PASS, TRIAGE_REVIEW
from apps.projects.models import Project
from apps.quality.services import record_security_findings
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from integrations.types import A11Y_FAIL, A11Y_PASS


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Shop")
    story = WorkItem.objects.create(tenant=tenant, project=project, title="Checkout")
    spec = AgentSpec.objects.create(tenant=tenant, key="09b_test_automation", body_ref="x",
                                    semver="1.0.0")
    WcagCriterion.objects.get_or_create(
        version="2.2", number="1.1.1",
        defaults={"handle": "Non-text Content", "level": "A", "slug": "n", "text": "…"})
    WcagCriterion.objects.get_or_create(
        version="2.2", number="1.4.3",
        defaults={"handle": "Contrast (Minimum)", "level": "AA", "slug": "c", "text": "…"})
    return {"t": str(tenant.id), "p": str(project.id), "tenant": tenant, "project": project,
            "story": story, "spec": spec}


def _run(world, workflow_id="w1", story=None) -> Run:
    return Run.objects.create(tenant=world["tenant"], work_item=story or world["story"],
                              agent_spec=world["spec"], temporal_workflow_id=workflow_id)


def _row(**over) -> ReportRow:
    base = {
        "source": SOURCE_AI, "outcome": TRIAGE_FAILURE, "criteria": ("1.1.1",),
        "route": "/checkout", "selector": "img.hero",
        "evidence": 'alt="IMG_1234" is a filename', "confidence": 0.93,
        "suggested_fix": "describe what the image shows", "checker": "alt",
        "verdict": A11Y_FAIL,
    }
    base.update(over)
    return ReportRow(**base)


def _record(world, run, rows, *, routes=("/checkout",), unjudged=()):
    return record_run_findings(
        tenant_id=world["t"], project_id=world["p"], run_id=str(run.id),
        report=MergedReport(rows=list(rows), routes=list(routes), unjudged=list(unjudged)))


def _reconcile(world, run=None):
    return record_a11y_findings(tenant_id=world["t"], project_id=world["p"],
                                run_id=str(run.id) if run else None)


def _defects(world):
    return list(WorkItem.objects.filter(
        tenant_id=world["t"], type=WorkItem.Type.DEFECT).order_by("title"))


def _a11y_defects(world):
    return [d for d in _defects(world) if (d.external_ref or {}).get("a11y_finding")]


# ══ AC1 — a failing check opens a defect with the right severity ══════════════════

def test_a_failing_check_opens_a_defect(world):
    run = _run(world)
    _record(world, run, [_row()])
    out = _reconcile(world, run)

    assert len(out["opened"]) == 1
    defect = _a11y_defects(world)[0]
    assert defect.type == WorkItem.Type.DEFECT
    assert defect.state == WorkItem.State.IN_PROGRESS
    assert defect.external_ref["kind"] == DEFECT_KIND
    assert defect.external_ref["severity"] == "critical", "Level A breach"
    assert "1.1.1" in defect.title and "/checkout" in defect.title


def test_a_level_aa_breach_opens_a_high_defect(world):
    run = _run(world)
    _record(world, run, [_row(criteria=("1.4.3",), checker="color", source=SOURCE_RULE,
                              confidence=None, verdict="", selector=".btn")])
    _reconcile(world, run)
    assert _a11y_defects(world)[0].external_ref["severity"] == "high"


def test_the_defect_says_enough_to_act_on_without_opening_anything_else(world):
    run = _run(world)
    _record(world, run, [_row()])
    _reconcile(world, run)
    body = _a11y_defects(world)[0].description
    assert "WCAG 2.2 1.1.1" in body and "Level A" in body
    assert "/checkout" in body and "img.hero" in body
    assert "IMG_1234" in body, "the evidence"
    assert "describe what the image shows" in body, "and the fix"
    assert "93%" in body


def test_a_defect_carries_the_scanner_rule_the_other_criteria_and_a_weak_handle_warning(world):
    """Three lines that only appear when they apply — the scanner's own rule id, the other
    criteria one fix would also repair (D-A11Y-2), and the warning that this element is
    identified by its position because the capture gave it no selector of its own."""
    run = _run(world)
    _record(world, run, [_row(
        source=SOURCE_RULE, checker="semantics", confidence=None, verdict="",
        criteria=("1.3.1", "4.1.2"), rule_id="button-name", selector="/checkout#12")])
    _reconcile(world, run)
    body = _a11y_defects(world)[0].description
    assert "`button-name`" in body
    assert "Also breaches: 4.1.2" in body
    assert "identified by its position" in body
    assert "Confidence" not in body, "a measurement is not a guess"


def test_a_defect_hangs_off_the_story_the_problem_was_first_seen_on(world):
    """First rather than last: a finding still open when a second story's run sees it would
    otherwise migrate between stories, and a developer would lose a bug that kept moving."""
    other = WorkItem.objects.create(tenant=world["tenant"], project=world["project"],
                                    title="Cart")
    first, second = _run(world, "w1"), _run(world, "w2", story=other)
    _record(world, first, [_row()])
    _record(world, second, [_row()])
    _reconcile(world, second)
    assert str(_a11y_defects(world)[0].parent_id) == str(world["story"].id)


def test_a_finding_with_no_run_behind_it_hangs_off_the_accessibility_backlog(world):
    """A CI post and a baseline audit both have no run to parent a defect to.

    Until QA-18 these defects were deliberately **parentless** — trackable, but loose in the
    project with nothing naming them as one body of work. They now hang off the project's
    accessibility backlog instead, which is what OP-08's remediation campaign picks up.
    """
    from apps.a11y.backlog import BACKLOG_TITLE

    record_run_findings(tenant_id=world["t"], project_id=world["p"], run_id=None,
                        report=MergedReport(rows=[_row()], routes=["/checkout"]))
    _reconcile(world)
    parent = _a11y_defects(world)[0].parent
    assert parent is not None and parent.title == BACKLOG_TITLE


def test_a_project_whose_findings_all_come_from_builds_grows_no_container(world):
    """The container is created lazily. A greenfield project that never audits anything must
    not sprout an empty epic in its backlog."""
    from apps.a11y.backlog import BACKLOG_STREAM
    from apps.workitems.models import WorkItem

    run = _run(world)
    _record(world, run, [_row()])
    _reconcile(world)
    assert not WorkItem.objects.filter(
        tenant_id=world["t"], feature_stream=BACKLOG_STREAM).exists()


def test_a_low_severity_failure_opens_no_defect(world):
    """Deliberately narrower than "any failure". A Level AAA breach is reported and tracked in
    the ledger, but nobody is held to AAA, so it does not open work."""
    run = _run(world)
    _record(world, run, [_row()])
    A11yFinding.objects.filter(tenant_id=world["t"]).update(severity="medium")
    out = _reconcile(world, run)
    assert out["opened"] == [] and _a11y_defects(world) == []


def test_the_blocking_bar_is_the_same_one_security_uses(world):
    from apps.quality.services import _SECURITY_BLOCKING

    assert A11Y_BLOCKING == _SECURITY_BLOCKING


# ══ AC2 — a defect closes itself when the problem is gone ════════════════════════

def test_a_defect_closes_when_a_later_run_finds_the_problem_fixed(world):
    first, second = _run(world, "w1"), _run(world, "w2")
    _record(world, first, [_row()])
    _reconcile(world, first)
    defect = _a11y_defects(world)[0]

    _record(world, second, [_row(outcome=TRIAGE_PASS, verdict=A11Y_PASS)])
    out = _reconcile(world, second)

    defect.refresh_from_db()
    assert out["closed"] == [str(defect.id)]
    assert defect.state == WorkItem.State.DONE


def test_a_defect_closes_when_a_finding_is_downgraded_to_needs_review(world):
    """Not only "resolved". A finding a later run is no longer confident about must not keep a
    developer's bug open — it belongs to the reviewer now."""
    first, second = _run(world, "w1"), _run(world, "w2")
    _record(world, first, [_row()])
    _reconcile(world, first)
    _record(world, second, [_row(outcome=TRIAGE_REVIEW, confidence=0.4)])
    _reconcile(world, second)

    assert _a11y_defects(world)[0].state == WorkItem.State.DONE
    assert len(review_queue(world["t"], world["p"])) == 1, "and it is in the queue instead"


# ══ THE rule: a screen nobody looked at keeps its defect ═════════════════════════

def test_a_defect_on_a_screen_this_run_never_visited_stays_open(world):
    """The whole risk of this task in one test. Security closes a defect whose finding is absent
    from the current list; a run covers only the screens it captured, so copying that literally
    would mark `/cart` fixed because the run happened to test `/checkout`."""
    first, second = _run(world, "w1"), _run(world, "w2")
    _record(world, first, [_row(route="/checkout"), _row(route="/cart", selector="img.cart")],
            routes=("/checkout", "/cart"))
    _reconcile(world, first)
    assert len(_a11y_defects(world)) == 2

    _record(world, second, [_row(route="/checkout")], routes=("/checkout",))
    out = _reconcile(world, second)

    assert out["closed"] == [], "nothing was proven fixed"
    states = {d.external_ref["route"]: d.state for d in _a11y_defects(world)}
    assert states == {"/checkout": WorkItem.State.IN_PROGRESS,
                      "/cart": WorkItem.State.IN_PROGRESS}


def test_a_defect_whose_element_was_captured_but_never_judged_stays_open(world):
    """The subtler half of the same rule — the route WAS covered, but we got no answer."""
    first, second = _run(world, "w1"), _run(world, "w2")
    _record(world, first, [_row()])
    _reconcile(world, first)
    _record(world, second, [], unjudged=[
        {"route": "/checkout", "selector": "img.hero", "checker": "alt", "reason": "…"}])
    out = _reconcile(world, second)
    assert out["closed"] == []
    assert _a11y_defects(world)[0].state == WorkItem.State.IN_PROGRESS


# ══ AC3 — low confidence goes to a person, never to a developer ══════════════════

def test_a_low_confidence_finding_goes_to_the_queue_and_opens_no_defect(world):
    run = _run(world)
    _record(world, run, [_row(outcome=TRIAGE_REVIEW, confidence=0.42)])
    out = _reconcile(world, run)

    assert out["opened"] == [] and _a11y_defects(world) == []
    assert len(review_queue(world["t"], world["p"])) == 1, "kept, not dropped"


def test_a_non_blocking_finding_is_still_recorded_in_the_ledger(world):
    """The one difference from security that must be kept: security DROPS its non-blocking
    findings; accessibility cannot, because the uncertain ones are the SME's work."""
    run = _run(world)
    _record(world, run, [_row(outcome=TRIAGE_REVIEW, confidence=0.42)])
    _reconcile(world, run)
    assert A11yFinding.objects.filter(tenant_id=world["t"]).count() == 1


# ══ AC4 — a flapping finding reopens its own defect ══════════════════════════════

def test_a_flapping_finding_reopens_the_same_defect(world):
    first, second, third = _run(world, "w1"), _run(world, "w2"), _run(world, "w3")
    _record(world, first, [_row()])
    _reconcile(world, first)
    original = _a11y_defects(world)[0].id

    _record(world, second, [_row(outcome=TRIAGE_PASS, verdict=A11Y_PASS)])
    _reconcile(world, second)
    assert _a11y_defects(world)[0].state == WorkItem.State.DONE

    _record(world, third, [_row()])
    out = _reconcile(world, third)

    defects = _a11y_defects(world)
    assert len(defects) == 1, "one problem, one defect"
    assert defects[0].id == original
    assert defects[0].state == WorkItem.State.IN_PROGRESS
    assert out["reopened"] == [str(original)] and out["opened"] == []


def test_reconciling_twice_changes_nothing_the_second_time(world):
    run = _run(world)
    _record(world, run, [_row()])
    first = _reconcile(world, run)
    second = _reconcile(world, run)
    assert len(first["opened"]) == 1
    assert second["opened"] == [] and second["closed"] == [] and second["reopened"] == []
    assert len(_a11y_defects(world)) == 1


def test_two_elements_failing_one_criterion_open_two_defects(world):
    run = _run(world)
    _record(world, run, [_row(selector="img.hero"), _row(selector="img.footer")])
    assert len(_reconcile(world, run)["opened"]) == 2


# ══ three defect families, one table, no crossing over ═══════════════════════════

def test_a_security_run_cannot_close_an_accessibility_defect(world):
    """Test defects are keyed on `test_ref`, security on `finding`, these on `a11y_finding`.
    A shared key would have let one reconciliation quietly close another's rows."""
    run = _run(world)
    _record(world, run, [_row()])
    _reconcile(world, run)
    defect = _a11y_defects(world)[0]

    record_security_findings(tenant_id=world["t"], project_id=world["p"],
                             work_item_id=str(world["story"].id), findings=[])
    defect.refresh_from_db()
    assert defect.state == WorkItem.State.IN_PROGRESS


def test_an_accessibility_run_cannot_close_a_security_defect(world):
    """And the other direction, which is the one a reviewer would not think to check."""
    record_security_findings(
        tenant_id=world["t"], project_id=world["p"], work_item_id=str(world["story"].id),
        findings=[{"id": "SEC-1", "severity": "critical", "title": "SQL injection"}])
    security = WorkItem.objects.get(external_ref__finding="SEC-1")

    run = _run(world)
    _record(world, run, [_row()])
    _reconcile(world, run)

    security.refresh_from_db()
    assert security.state == WorkItem.State.IN_PROGRESS


def test_the_test_gate_does_not_see_accessibility_defects(world):
    """`open_test_defect_refs` scopes on `test_ref`; an accessibility defect carries none, so it
    cannot hold the *test* gate shut. Accessibility gets its own gate in QA-08/QA-15."""
    from apps.gates.testgate import open_test_defect_refs

    run = _run(world)
    _record(world, run, [_row()])
    _reconcile(world, run)
    assert open_test_defect_refs(tenant_id=world["t"],
                                 work_item_id=str(world["story"].id)) == []


# ══ wired into the pass, and never able to fail a build ══════════════════════════

def test_the_pass_records_defects_after_publishing_the_report(world, monkeypatch):
    """dispatch → report → defects, in that order, and the loopback lives outside
    `publish_report` so a function called "publish report" does not quietly create work items."""
    from apps.a11y import aipass

    calls: list[str] = []
    monkeypatch.setattr(aipass, "publish_report",
                        lambda **kw: calls.append("report") or {"artifact_id": "a"})
    monkeypatch.setattr(aipass, "record_a11y_findings",
                        lambda **kw: calls.append("defects") or {"opened": []})
    out = aipass._publish(tenant_id=world["t"], project_id=world["p"], run_id=None, title="")
    assert calls == ["report", "defects"]
    assert out["defects"] == {"opened": []}


def test_a_failing_loopback_never_takes_the_build_with_it(world, monkeypatch):
    from apps.a11y import aipass

    monkeypatch.setattr(aipass, "publish_report", lambda **kw: {"artifact_id": "a"})
    monkeypatch.setattr(aipass, "record_a11y_findings",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("loopback broke")))
    out = aipass._publish(tenant_id=world["t"], project_id=world["p"], run_id=None, title="")
    assert out["artifact_id"] == "a"
    assert out["defects"]["error"] == "loopback broke"


def test_a_failing_report_does_not_stop_a_real_failure_being_tracked(world, monkeypatch):
    """The two steps are independent on purpose: neither is a reason to skip the other."""
    from apps.a11y import aipass

    run = _run(world)
    _record(world, run, [_row()])
    monkeypatch.setattr(aipass, "publish_report",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("no object store")))
    out = aipass._publish(tenant_id=world["t"], project_id=world["p"], run_id=str(run.id),
                          title="")
    assert out["error"] == "no object store"
    assert len(out["defects"]["opened"]) == 1, "the failure is still tracked"


# ══ scope kept honest ════════════════════════════════════════════════════════════

def test_exactly_one_gate_reads_these_defects(world):
    """Until QA-15 this asserted that *no* gate read them, so that switching blocking on would
    be a decision somebody made rather than a side effect. QA-15 made that decision: the
    accessibility gate reads them, and nothing else does.

    The guard keeps its value inverted — it still fails if a second gate quietly starts closing
    or blocking on accessibility defects, which is the drift `testgate.py` warns about."""
    from pathlib import Path

    gates = Path(__file__).resolve().parents[1] / "apps/gates"
    hits = {p.name for p in gates.glob("*.py")
            if "a11y_finding" in p.read_text(encoding="utf-8")}
    assert hits == {"a11ygate.py"}


# ══ the title a person actually reads ═══════════════════════════════════════════
#
# It used to read `Accessibility: 1.4.1 on /loans/current — #loans-table > tbody >
# tr:nth-of-type(2)`: a rule named by a number nobody has memorised, an element named by a CSS
# path nobody can read, and the whole thing truncated on a board card. Both halves now say what
# they mean, and both facts somebody navigates by — the number and the address — are still there.

def test_the_title_names_the_rule_rather_than_only_numbering_it(world):
    run = _run(world)
    _record(world, run, [_row()])
    _reconcile(world, run)

    title = _a11y_defects(world)[0].title
    assert "Non-text Content (1.1.1)" in title, title
    # The number stays. A developer looking a criterion up searches for 1.1.1, and the name
    # without it would cost them that.
    assert "1.1.1" in title and "/checkout" in title


def test_the_title_describes_the_element_instead_of_pasting_the_selector(world):
    run = _run(world)
    _record(world, run, [_row(selector="#loans-table > tbody > tr:nth-of-type(2)")])
    _reconcile(world, run)

    defect = _a11y_defects(world)[0]
    assert "row 2 in the loans table" in defect.title, defect.title
    assert "tbody" not in defect.title
    # And the exact selector is NOT lost — it is on the ticket, verbatim, where somebody fixing
    # it goes looking. The title is a summary; the description is the record.
    assert "#loans-table > tbody > tr:nth-of-type(2)" in defect.description


def test_a_title_names_the_page_by_its_name_when_it_has_one(world):
    """Recon 2026-10-10, finding 4: "on /checkout" is an address. A page listed with a name is
    called by it; the address stays on the ticket as Screen."""
    from apps.a11y.routes import register_routes

    register_routes(tenant_id=world["t"], project_id=world["p"],
                    routes=[{"path": "/checkout", "label": "Checkout"}])
    run = _run(world)
    _record(world, run, [_row()])
    _reconcile(world, run)

    defect = _a11y_defects(world)[0]
    assert " on the Checkout page — " in defect.title
    assert "/checkout" not in defect.title
    assert "/checkout" in defect.description


def test_a_title_still_says_which_page_and_which_rule_without_the_standard_loaded(world):
    # A project whose WCAG set has not been loaded still gets tickets. Losing the rule's NAME is
    # a small cost; failing to open a defect because a lookup table is missing would be absurd.
    WcagCriterion.objects.filter(version="2.2").delete()
    run = _run(world)
    _record(world, run, [_row()])
    _reconcile(world, run)

    title = _a11y_defects(world)[0].title
    assert "1.1.1" in title and "/checkout" in title
    assert "(1.1.1)" not in title, "no empty brackets where the name would have been"


@pytest.mark.parametrize("selector,expected", [
    # An id is the name its own developer chose — quoted in words, never shown as CSS (recon
    # 2026-10-10, finding 4). A landmark id is the region it names.
    ("#photo-interior", 'the "photo-interior" element'),
    ("main#main", "main content"),
    ("#save-entry", 'the "save-entry" element'),
    ("#loans-table > tbody > tr:nth-of-type(2)", "row 2 in the loans table"),
    ("form#signup > input.email", "field in the signup"),
    # A named thing beats a region — "in the loans table" says more than "in the main content".
    ("#main > #loans-table > tr:nth-of-type(1)", "row 1 in the loans table"),
    # A landmark is a region, never a name: "of the main" told nobody anything.
    ("#main > p:nth-of-type(1)", "paragraph 1 in the main content"),
    # The link has no position of its own; the list item it sits in does, and carrying it
    # is what tells the third nav link from the first.
    ("nav > ul > li:nth-of-type(3) > a", "link (list item 3) in the navigation"),
    ("main > div.card > button", "button in the main content"),
    # A tag with no word for it falls back to the selector rather than to nothing. A gap in the
    # list is a gap in the list; a title that says less than the old one is not an improvement.
    ("div.wrapper > span", "div.wrapper > span"),
    ("", ""),
])
def test_the_element_is_put_into_words_or_left_exactly_as_it_was(selector, expected):
    assert _element_words(selector) == expected


# ══ and it has to tell siblings apart ═════════════════════════════════════════════
#
# The first version of this named the nearest ancestor with an id and threw away the number that
# distinguished one element from its siblings. Three labels in three rows of one form all came
# out "label of the main" — three tickets on one board wearing one title, which is worse than
# the unreadable selector it replaced. Found by checking the real data after a migration, not by
# a test, which is why these exist.

@pytest.mark.parametrize("selectors", [
    # Same element, different repeat of the same block: the position has to survive.
    ["#main > form > div:nth-of-type(1) > label",
     "#main > form > div:nth-of-type(2) > label",
     "#main > form > div:nth-of-type(5) > label"],
    # Same element, same position, different REGION of the page.
    ["#main > p:nth-of-type(1)",
     "html > body > footer > div:nth-of-type(1) > p:nth-of-type(1)"],
    # Two headings of different levels in one region. Both used to be "heading"; a screen reader
    # says "heading level 2", and so do we.
    ["#main > div > h1", "#main > h2"],
])
def test_siblings_never_come_out_reading_the_same(selectors):
    phrases = [_element_words(s) for s in selectors]
    assert len(set(phrases)) == len(selectors), phrases


def test_the_position_is_kept_even_when_the_element_has_none_of_its_own(world):
    """The exact three that collided, as tickets, end to end."""
    run = _run(world)
    _record(world, run, [
        _row(criteria=("1.4.1",), checker="color", source=SOURCE_RULE, confidence=None,
             verdict="", route="/account/join",
             selector=f"#main > form > div:nth-of-type({n}) > label")
        for n in (1, 2, 5)
    ], routes=("/account/join",))
    _reconcile(world, run)

    titles = [d.title for d in _a11y_defects(world)]
    assert len(titles) == 3
    assert len(set(titles)) == 3, titles
    assert all("(group " in t for t in titles), titles

