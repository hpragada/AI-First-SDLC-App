"""QA-13 — source, confidence and fix on the report, rendered from the ledger.

Against the task's acceptance criteria:

  AC1  every row shows source, confidence, criterion and suggested fix — **already true**
       from QA-12; pinned here so it stays true now the rows come from somewhere else
  AC2  (D-A11Y-2) a finding breaching several criteria shows all of them on one row —
       **already true**; pinned for the same reason
  AC3  (D-A11Y-3) a run where the judge was unavailable says so at the top, and says how many
       items went to a person because of it — **the real work of this task**
  AC4  a report saved before this change still opens
  AC5  ≥ 90% coverage on the new code

**Two of the five were already met before this task started, and saying so is the delivery.**
QA-12's table already carried all four fields and already rendered every criterion of a
multi-criterion finding on one row. What this task adds is where the rows come from (the
ledger), how they are arranged (by criterion), and the thing that was genuinely missing: the
report could not say *why* an item went unchecked.
"""
from __future__ import annotations

import base64
import io
import json

import pytest
from PIL import Image as PILImage

from apps.a11y.capture import parse_capture
from apps.a11y.dispatch import DISPATCH_FAILED, record_verdict
from apps.a11y.findings import describe_criteria, open_findings_for_run
from apps.a11y.ingest import ingest_screen, requests_for
from apps.a11y.models import A11yFinding, WcagCriterion
from apps.a11y.report import (
    SOURCE_AI,
    SOURCE_RULE,
    MergedReport,
    ReportRow,
    merge_run,
    publish_report,
    report_body,
)
from apps.a11y.triage import TRIAGE_FAILURE, TRIAGE_REVIEW
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from integrations.types import A11Y_FAIL, A11Y_PASS, A11Y_UNCERTAIN, A11yJudgment
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
    WcagCriterion.objects.get_or_create(
        version="2.2", number="1.1.1",
        defaults={"handle": "Non-text Content", "level": "A", "slug": "n", "text": "…"})
    return {"t": str(tenant.id), "p": str(project.id), "tenant": tenant, "project": project,
            "story": story, "spec": spec}


def _run(world, workflow_id="w1") -> Run:
    return Run.objects.create(tenant=world["tenant"], work_item=world["story"],
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


def _png() -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (400, 300), (200, 40, 40)).save(buf, format="PNG")
    return buf.getvalue()


def _screen(**over) -> dict:
    base = {
        "route": "/checkout", "url": "http://localhost:5173/checkout",
        "screenshot_base64": base64.b64encode(_png()).decode("ascii"),
        "axe_violations": [],
        "elements": [{
            "selector": "img.hero", "tag": "img", "role": "", "attrs": {"alt": "IMG_1234"},
            "text": "", "accessible_name": "IMG_1234", "interactive": False, "rendered": True,
            "styles": dict(_STYLES), "parent_styles": dict(_STYLES),
            "html": '<img class="hero" alt="IMG_1234">', "context": "Our new range",
            "box": {"x": 10, "y": 20, "width": 120, "height": 80},
        }],
    }
    base.update(over)
    return base


def _ingest(world, run):
    return ingest_screen(tenant_id=world["t"], project_id=world["p"],
                         screen=parse_capture(json.dumps(_screen()))[0], run_id=str(run.id),
                         object_store=InMemoryObjectStore())


def _judge(world, request, verdict, confidence, evidence="quoted markup", fix="a fix"):
    from integrations.types import A11Y_CHECKER_CRITERIA

    record_verdict(
        tenant_id=world["t"], project_id=world["p"], run_id=None,
        content_hash=request.content_hash,
        judgment=A11yJudgment(criteria=A11Y_CHECKER_CRITERIA[request.checker], verdict=verdict,
                              confidence=confidence, evidence=evidence, suggested_fix=fix,
                              checker=request.checker))


# ══ AC1 / AC2 — already true, pinned so they stay true ════════════════════════════
#
# These take `world` because rendering now reads the standard for its criterion headings —
# a deliberate consequence of grouping by criterion, and the reason the renderer is no longer
# a pure function.

def test_every_row_still_shows_source_confidence_criterion_and_fix(world):
    """The table carries where it came from and how sure it was; the fix is in the document.

    The fix left the table when it stopped being truncated — a paragraph cannot live in a
    markdown cell. What this guards is that none of the four was *dropped*, which is the only
    way that move could have gone wrong.
    """
    body = report_body(MergedReport(rows=[_row()], routes=["/checkout"]))
    line = next(line for line in body.splitlines() if line.startswith("|")
                and "img.hero" in line)
    assert SOURCE_AI in line
    assert "93%" in line
    assert "1.1.1" in body
    assert "describe what the image shows" in body


def test_a_finding_breaching_two_criteria_shows_both_on_one_row(world):
    """D-A11Y-2. One broken thing, one fix, one row — never split into duplicates and never
    silently reduced to the first criterion."""
    body = report_body(MergedReport(
        rows=[_row(criteria=("1.3.1", "4.1.2"), checker="semantics", selector="div.btn")],
        routes=["/checkout"]))
    rows = [x for x in body.splitlines() if x.startswith("|") and "div.btn" in x]
    assert len(rows) == 1
    assert "1.3.1, 4.1.2" in rows[0]


def test_a_measurement_is_still_shown_as_measured_not_as_a_percentage(world):
    body = report_body(MergedReport(
        rows=[_row(source=SOURCE_RULE, confidence=None, verdict="")], routes=["/checkout"]))
    assert "measured" in body


# ══ grouped by criterion ══════════════════════════════════════════════════════════

def test_findings_are_grouped_under_the_criterion_they_breach(world):
    body = report_body(MergedReport(rows=[
        _row(criteria=("1.1.1",), selector="img.hero"),
        _row(criteria=("1.4.3",), selector=".btn", checker="color"),
    ], routes=["/checkout"]))
    assert "### 1.1.1 Non-text Content — Level A" in body, "named and levelled, not a bare number"
    assert "### 1.4.3" in body


def test_the_failure_and_review_split_stays_above_the_grouping(world):
    """A reader's first question is what is broken; the second is which rule it breaks. Folding
    both onto one axis would put a blocking failure and a low-confidence question in one block."""
    body = report_body(MergedReport(rows=[
        _row(outcome=TRIAGE_FAILURE, selector="img.hero"),
        _row(outcome=TRIAGE_REVIEW, confidence=0.4, selector="img.other"),
    ], routes=["/checkout"]))
    assert body.index("## Failures") < body.index("## Needs human review")
    assert body.index("## Failures") < body.index("### 1.1.1")


def test_a_criterion_the_standard_does_not_hold_is_still_given_a_heading(world):
    body = report_body(MergedReport(rows=[_row(criteria=("9.9.9",))], routes=["/checkout"]))
    assert "### 9.9.9" in body, "unknown to us is not a reason to hide the finding"


def test_criteria_headings_come_from_the_loaded_standard(world):
    assert describe_criteria(["1.1.1"])["1.1.1"] == {"handle": "Non-text Content", "level": "A"}
    assert describe_criteria(["9.9.9"]) == {}
    assert describe_criteria([]) == {}


# ══ AC3 — the report says why a check did not run ═════════════════════════════════

def test_a_run_the_judge_could_not_be_asked_says_so_at_the_top(world):
    reason = DISPATCH_FAILED.format(detail="temporal is down")
    body = report_body(MergedReport(rows=[
        _row(outcome=TRIAGE_REVIEW, verdict=A11Y_UNCERTAIN, confidence=0.0, evidence=reason),
        _row(outcome=TRIAGE_REVIEW, verdict=A11Y_UNCERTAIN, confidence=0.0, evidence=reason,
             selector="div.btn"),
    ], routes=["/checkout"]))
    assert "The AI checks did not fully run" in body
    assert "2 item(s) were sent for human review" in body
    assert "temporal is down" in body, "the real reason, verbatim"
    assert body.index("did not fully run") < body.index("## Needs human review")


def test_the_reason_is_told_apart_structurally_not_by_reading_the_wording(world):
    """A low-confidence item carries a real `fail` the confidence gate held back; an unanswered
    one carries `uncertain`. Matching on the sentence would break the moment somebody improved
    the wording of a reason."""
    body = report_body(MergedReport(rows=[
        _row(outcome=TRIAGE_REVIEW, verdict=A11Y_FAIL, confidence=0.4, evidence="might be"),
    ], routes=["/checkout"]))
    assert "did not fully run" not in body, "unsure is not the same as unanswered"
    assert "## Needs human review" in body


def test_each_distinct_reason_is_listed_once(world):
    body = report_body(MergedReport(rows=[
        _row(outcome=TRIAGE_REVIEW, verdict=A11Y_UNCERTAIN, confidence=0.0, evidence="no judge"),
        _row(outcome=TRIAGE_REVIEW, verdict=A11Y_UNCERTAIN, confidence=0.0, evidence="no judge",
             selector="b"),
        _row(outcome=TRIAGE_REVIEW, verdict=A11Y_UNCERTAIN, confidence=0.0,
             evidence="no machine", selector="c"),
    ], routes=["/checkout"]))
    assert body.count("> - no judge") == 1
    assert body.count("> - no machine") == 1


def test_the_two_kinds_of_silence_are_reported_separately(world):
    """"No verdict was reached, and here is why" is a different fact from "this element was
    never asked about at all", and a reader has to act differently on each."""
    body = report_body(MergedReport(
        rows=[_row(outcome=TRIAGE_REVIEW, verdict=A11Y_UNCERTAIN, confidence=0.0,
                   evidence="no judge")],
        routes=["/checkout"],
        unjudged=[{"route": "/checkout", "selector": "x", "checker": "alt", "reason": "…"}]))
    assert "The AI checks did not fully run" in body
    assert "This check is incomplete" in body


# ══ rendered from the ledger ══════════════════════════════════════════════════════

def test_the_report_is_rendered_from_the_stored_findings(world):
    run = _run(world)
    _ingest(world, run)
    _judge(world, requests_for(world["t"], world["p"], str(run.id))[0], A11Y_FAIL, 0.94,
           evidence='alt="IMG_1234" is a filename', fix="describe the image")

    publish_report(tenant_id=world["t"], project_id=world["p"], run_id=str(run.id))
    stored = open_findings_for_run(world["t"], world["p"], str(run.id))
    assert len(stored) == 1

    body = report_body(merge_run(tenant_id=world["t"], project_id=world["p"],
                                 run_id=str(run.id)), findings=stored)
    assert "img.hero" in body and "describe the image" in body


def test_a_problem_first_seen_earlier_and_still_open_appears_in_this_runs_report(world):
    """The reason the ledger is the source rather than the merge: `last_seen_run` is "what this
    run found", which includes a problem that has been open for three runs."""
    first, second = _run(world, "w1"), _run(world, "w2")
    for run in (first, second):
        _ingest(world, run)
        _judge(world, requests_for(world["t"], world["p"], str(run.id))[0], A11Y_FAIL, 0.94)
        publish_report(tenant_id=world["t"], project_id=world["p"], run_id=str(run.id))

    assert A11yFinding.objects.filter(tenant_id=world["t"]).count() == 1, "one problem"
    assert len(open_findings_for_run(world["t"], world["p"], str(second.id))) == 1, \
        "and the later run's report still shows it"


def test_what_this_run_fixed_is_counted(world):
    body = report_body(MergedReport(rows=[], routes=["/checkout"]), resolved=3)
    assert "3 finding(s) open before this run were not found again." in body


def test_the_document_falls_back_to_the_merge_when_the_ledger_could_not_be_written(
        world, monkeypatch):
    """A report from slightly different data beats no report at all."""
    run = _run(world)
    _ingest(world, run)
    _judge(world, requests_for(world["t"], world["p"], str(run.id))[0], A11Y_FAIL, 0.94)
    monkeypatch.setattr(
        "apps.a11y.findings.record_run_findings",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("ledger is unreachable")))

    out = publish_report(tenant_id=world["t"], project_id=world["p"], run_id=str(run.id))
    assert out["artifact_id"]
    assert out["ledger"]["error"] == "ledger is unreachable"
    assert out["failures"] == 1, "the merge still knows what was found"


def test_passes_are_shown_from_the_merge_because_the_ledger_does_not_hold_them(world):
    """A `pass` is not a finding — its absence from a later run is how a fixed problem resolves
    — so it can only come from the run's own merge."""
    run = _run(world)
    _ingest(world, run)
    _judge(world, requests_for(world["t"], world["p"], str(run.id))[0], A11Y_PASS, 0.97,
           evidence="", fix="")
    publish_report(tenant_id=world["t"], project_id=world["p"], run_id=str(run.id))

    assert open_findings_for_run(world["t"], world["p"], str(run.id)) == []
    body = report_body(merge_run(tenant_id=world["t"], project_id=world["p"],
                                 run_id=str(run.id)), findings=None)
    assert "## Passed" in body and "img.hero" in body


def test_the_ledger_is_not_read_for_a_report_with_no_run(world):
    assert open_findings_for_run(world["t"], world["p"], None) == []


# ══ AC4 — an older report still opens ═════════════════════════════════════════════

def test_a_report_written_before_this_change_still_renders(world):
    """The bodies live in the object store as markdown and are never re-parsed, so an older one
    opens through the same generic preview. The real backward-compatibility risk is the
    *renderer* — a row missing the fields this task leans on must render blank, never raise."""
    bare = ReportRow(source=SOURCE_AI, outcome=TRIAGE_FAILURE, criteria=("1.1.1",),
                     route="/checkout", selector="img.hero", evidence="")
    body = report_body(MergedReport(rows=[bare], routes=["/checkout"]))
    assert "img.hero" in body
    assert "did not fully run" not in body


def test_the_test_report_is_untouched_by_this_task():
    """"Keeping every existing `test_report` field intact" is the half of AC4 that can actually
    break, so it is asserted rather than assumed."""
    from pathlib import Path

    services = (Path(__file__).resolve().parents[1] / "apps/quality/services.py").read_text(
        encoding="utf-8")
    for field in ("test_execution_id", "test_report_id", "flaky", "quarantined",
                  "defects_opened", "defects_closed", "external_ref"):
        assert f'"{field}"' in services


def test_an_empty_run_still_says_a_scan_may_not_have_happened(world):
    assert "only a clean result if a scan actually ran" in report_body(MergedReport())


# ══ The whole finding, printed ════════════════════════════════════════════════════
#
# The team read an audit's report and found the two sentences that mattered were the two the
# document had cut. A markdown cell cannot hold a line break, so bounding it was never a
# formatting choice — prose in a table stops wherever the limit lands, and on that run it
# landed mid-sentence inside the alt text the document was telling somebody to write.
#
# Raising the limit moves the cut; it does not remove it. So the paragraphs left the table.

_LONG_EVIDENCE = (
    'Screenshot shows a bar chart titled "Loans per month, 2026" with eight monthly bars '
    '(Jan-Aug) ranging from approximately 1,050 to 1,225 loans. The element carries alt="", '
    'hiding all chart data from assistive technology. The adjacent text ("Loans rose in the '
    'spring and fell back over the summer holidays") provides only a narrative trend summary '
    "- not the specific monthly figures the chart displays. Those figures are unavailable to "
    "screen-reader users."
)
_LONG_FIX = (
    'Replace alt="" with descriptive alt text conveying the chart\'s data: alt="Bar chart: '
    "Loans per month in 2026. Lending rose from approximately 1,050 in January to a peak of "
    'approximately 1,225 in May, then declined to approximately 1,050 by August." For richer '
    "access to the underlying data, also consider adding a linked data table beneath the chart."
)


def _table_row(body: str, selector: str) -> str:
    return next(x for x in body.splitlines() if x.startswith("| ") and selector in x)


def test_a_long_finding_is_printed_whole_somewhere_in_the_document(world):
    """The sentence that says *why it fails* is the one the old limit cut. Both halves whole."""
    body = report_body(MergedReport(
        rows=[_row(evidence=_LONG_EVIDENCE, suggested_fix=_LONG_FIX)], routes=["/checkout"]))
    assert _LONG_EVIDENCE in body
    assert _LONG_FIX in body
    assert "Those figures are unavailable to screen-reader users." in body


def test_the_table_summarises_and_the_number_is_what_joins_the_two_halves(world):
    """A reader scanning the table has to be able to name the row they want in full."""
    body = report_body(MergedReport(
        rows=[_row(evidence=_LONG_EVIDENCE, suggested_fix=_LONG_FIX)], routes=["/checkout"]))
    row = _table_row(body, "img.hero")
    assert row.startswith("| 1 | ")
    # The cell holds the opening and stops on a sentence; the sentence that decides the finding
    # is further down the paragraph, and is not in the table at all.
    assert "ranging from approximately 1,050 to 1,225 loans." in row
    assert "Those figures are unavailable" not in row
    assert "**1. `img.hero` on `/checkout`**" in body


def test_the_fix_column_is_gone_from_the_table_rather_than_widened(world):
    """A wider cell is the same defect further along. The column is not there at all."""
    body = report_body(MergedReport(rows=[_row()], routes=["/checkout"]))
    head = next(x for x in body.splitlines() if x.startswith("| # | Source |"))
    assert "Suggested fix" not in head
    assert "What was found" in head


def test_the_detail_says_which_check_how_sure_and_how_bad(world):
    body = report_body(MergedReport(rows=[_row()], routes=["/checkout"]))
    line = next(x for x in body.splitlines() if x.startswith("**1. "))
    assert "1.1.1" in line
    assert "`alt`" in line
    assert "93% confident" in line
    assert "Critical" in line


def test_numbering_runs_across_the_whole_document_not_per_section(world):
    """Three sections each numbering from 1 would give this report three number 1s, and "have
    a look at 4" would be a question rather than a reference."""
    from apps.a11y.triage import TRIAGE_PASS

    body = report_body(MergedReport(
        rows=[
            _row(selector="img.a"),
            _row(selector="img.b", outcome=TRIAGE_REVIEW, verdict=A11Y_UNCERTAIN,
                 confidence=0.4),
            _row(selector="img.c", outcome=TRIAGE_PASS, verdict=A11Y_PASS),
        ],
        routes=["/checkout"]))
    assert _table_row(body, "img.a").split("|")[1].strip() == "1"
    assert _table_row(body, "img.b").split("|")[1].strip() == "2"
    assert _table_row(body, "img.c").split("|")[1].strip() == "3"


def test_a_row_with_nothing_written_about_it_gets_no_empty_detail(world):
    """A scanner rule with no remediation text. A numbered heading with nothing under it reads
    as text that failed to render."""
    body = report_body(MergedReport(
        rows=[_row(source=SOURCE_RULE, confidence=None, verdict="", evidence="",
                   suggested_fix="")],
        routes=["/checkout"]))
    assert "img.hero" in body
    assert "**1. `img.hero`" not in body
    assert "#### Details" not in body


def test_a_reason_in_the_incomplete_notice_is_no_longer_bounded_either(world):
    """A blockquote line is not a table cell. It was cut only because `_cell` was the tool at
    hand."""
    reason = "The judge was unavailable. " + (
        "The queue held it for retry and never got one. " * 12)
    body = report_body(MergedReport(
        rows=[_row(outcome=TRIAGE_REVIEW, verdict=A11Y_UNCERTAIN, confidence=None,
                   evidence=reason)],
        routes=["/checkout"]))
    assert f"> - {' '.join(reason.split())}" in body


# ── the gist itself ───────────────────────────────────────────────────────────────

def test_a_short_finding_is_not_marked_as_shortened():
    from apps.a11y.report import _gist

    assert _gist('alt="IMG_1234" is a filename') == 'alt="IMG_1234" is a filename'


def test_a_gist_ends_on_a_sentence_when_there_is_one_to_end_on():
    from apps.a11y.report import _gist

    text = ("The element carries an empty alt attribute. " + "Everything after this is more "
            "detail that the column has no room for. " * 4)
    gist = _gist(text)
    assert gist.endswith("no room for.")
    assert not gist.endswith("…")


def test_a_gist_never_stops_in_the_middle_of_a_word():
    from apps.a11y.report import _gist

    gist = _gist("supercalifragilistic " * 40)
    assert gist.endswith("…")
    assert "supercalifragilisti…" not in gist


def test_a_gist_keeps_a_table_a_table():
    from apps.a11y.report import _gist

    assert "|" not in _gist("a | b").replace("\\|", "")


def test_prose_keeps_every_character_of_the_finding():
    from apps.a11y.report import _prose

    assert _prose("  a\n\n  b  ") == "a b"
    assert _prose(_LONG_FIX) == _LONG_FIX
