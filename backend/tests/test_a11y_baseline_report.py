"""QA-18 — where this application stands, and what to fix first.

Against the task's acceptance criteria:

  AC1  a completed baseline audit leaves a per-criterion baseline report AND a prioritised
       defect backlog
  AC2  running the audit a second time creates no duplicate defects
  AC3  fixes landed between runs show closed, and only the still-broken ones stay open
  AC4  report generation and the no-duplicate rule are covered

**The two-audit tests are the ones that matter.** QA-14 already proved no-duplicates and
self-closing for a *build's* findings; the audit path differs in a way that could have broken
both — its findings have no `Run` behind them, so they take a different branch for parenting
and their coverage is reconciled rather than reported. AC2 and AC3 are therefore proven here
end to end over two real audits with a fix in between, not by trusting the earlier proof.
"""
from __future__ import annotations

import base64
import io
import json

import pytest
from PIL import Image as PILImage

from apps.a11y.backlog import (
    BACKLOG_STREAM,
    BACKLOG_TITLE,
    backlog_container,
    breadth_by_criterion,
    in_fix_order,
    open_findings,
    prioritised,
    ranks,
)
from apps.a11y.baseline import finish_baseline_audit, ingest_audit_capture, start_baseline_audit
from apps.a11y.baseline_report import (
    BASELINE_TYPE,
    MAX_BACKLOG_ROWS,
    baseline_body,
    criterion_rows,
    movement,
    previous_counts,
    publish_baseline,
)
from apps.a11y.defects import record_a11y_findings
from apps.a11y.models import A11yFinding, WcagCriterion
from apps.a11y.report import merge_run, report_body, severity_of
from apps.a11y.routes import register_routes
from apps.projects.models import Project
from apps.registry.models import Artifact
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from storage.object_store import InMemoryObjectStore

_STYLES = {
    "color": "rgb(20, 20, 20)", "background-color": "rgb(255, 255, 255)",
    "text-decoration-line": "none", "font-size": "16px", "font-weight": "400",
    "border-style": "none",
}


def _png(colour=(200, 40, 40)) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (40, 30), colour).save(buf, format="PNG")
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


def _violation(rule="image-alt", criteria=("1.1.1",), impact="critical", nodes=("img.hero",)):
    return {"rule": rule, "impact": impact, "criteria": list(criteria),
            "help": f"{rule} must be satisfied", "nodes": list(nodes)}


_MISSING_ALT = _violation()


def _screen(route="/login", violations=(_MISSING_ALT,), **over) -> dict:
    base = {
        "route": route, "url": f"http://localhost:5173{route}",
        "screenshot_base64": base64.b64encode(_png()).decode("ascii"),
        "elements": [_element()],
        "axe_violations": [dict(v) for v in violations],
    }
    base.update(over)
    return base


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Imported App")
    # The standard, so severity comes from the conformance level rather than the fallback.
    for number, handle, level in (("1.1.1", "Non-text Content", "A"),
                                  ("1.4.3", "Contrast (Minimum)", "AA"),
                                  ("2.4.7", "Focus Visible", "AA")):
        WcagCriterion.objects.get_or_create(
            version="2.2", number=number,
            defaults={"handle": handle, "level": level, "slug": handle.lower(),
                      "text": f"{number} {handle}"})
    return {"t": str(tenant.id), "p": str(project.id), "tenant": tenant, "project": project}


def _audit(world, *paths):
    if paths:
        register_routes(tenant_id=world["t"], project_id=world["p"], routes=list(paths))
    return start_baseline_audit(tenant_id=world["t"], project_id=world["p"],
                                base_url="http://localhost:5173")


def _post(world, audit, screen):
    return ingest_audit_capture(tenant_id=world["t"], audit_id=str(audit.id),
                                text=json.dumps(screen), object_store=InMemoryObjectStore())


def _run_audit(world, screens, *, routes=None):
    """One whole audit: open it, post these screens, close it. Returns the finish result."""
    audit = _audit(world, *(routes or [s["route"] for s in screens]))
    for screen in screens:
        _post(world, audit, screen)
    return finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id))


def _finding(world, **over):
    base = {
        "tenant_id": world["t"], "project_id": world["p"], "route": "/login",
        "selector": "button.pay", "criterion": "1.1.1", "criteria": ["1.1.1"],
        "wcag_level": "A", "severity": "critical", "source": A11yFinding.Source.AI,
        "outcome": "failure", "status": A11yFinding.Status.OPEN, "evidence": "no name",
        "suggested_fix": "give it a name",
    }
    base.update(over)
    base.setdefault("fingerprint", f"{base['criterion']}-{base['route']}-{base['selector']}")
    return A11yFinding.objects.create(**base)


# ══ severity finally reaches the document a person reads ═════════════════════════════

def test_severity_comes_off_a_stored_finding(world):
    finding = _finding(world, severity="high")
    assert severity_of(finding) == "high"


def test_severity_is_derived_for_a_row_that_has_not_reached_the_ledger():
    """A merge row carries the criterion, not the severity. One mapping, used in both places."""
    from apps.a11y.report import ReportRow

    row = ReportRow(source="AI", outcome="failure", criteria=("1.4.3",), route="/x",
                    selector="a", evidence="e")
    assert severity_of(row, {"1.4.3": {"level": "AA"}}) == "high"
    assert severity_of(row, {"1.4.3": {"level": "A"}}) == "critical"


def test_an_unknown_level_errs_toward_surfacing_not_burying():
    from apps.a11y.report import ReportRow

    row = ReportRow(source="AI", outcome="failure", criteria=("9.9.9",), route="/x",
                    selector="a", evidence="e")
    assert severity_of(row, {}) == "high"


def test_the_run_report_now_says_how_bad_each_finding_is(world):
    """The gap this task closed: severity decided the gate and appeared nowhere a person could
    see it."""
    result = _run_audit(world, [_screen("/login")])
    assert result["report"]["failures"] >= 1

    report = merge_run(tenant_id=world["t"], project_id=world["p"],
                       run_id=result["audit_id"])
    body = report_body(report)
    assert "| Source | Severity |" in body
    assert "Critical" in body


def test_the_passed_table_carries_no_severity_column(world):
    """A row that passed has nothing to weigh, and a severity beside it reads as work left."""
    from apps.a11y.report import MergedReport, ReportRow

    passed = ReportRow(source="AI", outcome="pass", criteria=("1.1.1",), route="/x",
                       selector="img", evidence="fine", confidence=0.9)
    body = report_body(MergedReport(rows=[passed], routes=["/x"]))
    assert "## Passed" in body
    assert "| Source | Criteria |" in body, "no Severity column in this table"


# ══ the fix order ════════════════════════════════════════════════════════════════════

def test_severity_decides_first(world):
    _finding(world, criterion="1.4.3", severity="high", fingerprint="a")
    _finding(world, criterion="1.1.1", severity="critical", fingerprint="b")
    assert [item["criterion"] for item in prioritised(world["t"], world["p"])] == \
        ["1.1.1", "1.4.3"]


def test_breadth_breaks_the_tie(world):
    """One criterion broken on three pages is usually one component fixed once; three
    criteria broken on one page each are three separate pieces of work."""
    for route in ("/a", "/b", "/c"):
        _finding(world, criterion="1.4.3", severity="high", route=route,
                 fingerprint=f"wide-{route}")
    _finding(world, criterion="2.4.7", severity="high", route="/a", fingerprint="narrow")

    order = [item["criterion"] for item in prioritised(world["t"], world["p"])]
    assert order[0] == "1.4.3"
    assert order[-1] == "2.4.7"


def test_breadth_never_outranks_severity(world):
    """The order has to agree with the gate — the top of the backlog is what unblocks a
    release, so a widespread High must not sit above a single Critical."""
    for route in ("/a", "/b", "/c", "/d"):
        _finding(world, criterion="1.4.3", severity="high", route=route,
                 fingerprint=f"wide-{route}")
    _finding(world, criterion="1.1.1", severity="critical", route="/z", fingerprint="one")
    assert prioritised(world["t"], world["p"])[0]["criterion"] == "1.1.1"


def test_the_order_is_the_same_twice(world):
    for index, route in enumerate(("/a", "/b", "/c")):
        _finding(world, criterion="1.4.3", severity="high", route=route,
                 fingerprint=f"f{index}")
    first = [i["fingerprint"] for i in prioritised(world["t"], world["p"])]
    assert first == [i["fingerprint"] for i in prioritised(world["t"], world["p"])]


def test_positions_start_at_one_and_do_not_repeat(world):
    for index in range(4):
        _finding(world, route=f"/r{index}", fingerprint=f"f{index}")
    positions = [item["priority"] for item in prioritised(world["t"], world["p"])]
    assert positions == [1, 2, 3, 4]


def test_breadth_counts_pages_not_findings(world):
    _finding(world, criterion="1.4.3", route="/a", selector="x", fingerprint="1")
    _finding(world, criterion="1.4.3", route="/a", selector="y", fingerprint="2")
    assert breadth_by_criterion(open_findings(world["t"], world["p"]))["1.4.3"] == 1


def test_breadth_counts_items_awaiting_review_too(world):
    """One definition of the number, used in the listing and on the ticket alike."""
    _finding(world, criterion="1.4.3", route="/a", fingerprint="1")
    _finding(world, criterion="1.4.3", route="/b", outcome="needs_review", fingerprint="2")
    assert breadth_by_criterion(open_findings(world["t"], world["p"]))["1.4.3"] == 2


def test_a_resolved_finding_is_not_in_the_backlog(world):
    _finding(world, status=A11yFinding.Status.RESOLVED, fingerprint="gone")
    assert prioritised(world["t"], world["p"]) == []


def test_the_narrow_list_holds_only_what_the_policy_blocks_on(world):
    _finding(world, criterion="1.1.1", severity="critical", fingerprint="blocks")
    _finding(world, criterion="2.4.7", severity="medium", route="/b", fingerprint="reported")
    _finding(world, criterion="1.4.3", severity="high", route="/c",
             outcome="needs_review", fingerprint="review")

    narrow = [i["fingerprint"] for i in prioritised(world["t"], world["p"],
                                                    blocking_only=True)]
    wide = [i["fingerprint"] for i in prioritised(world["t"], world["p"])]
    assert narrow == ["blocks"]
    assert sorted(wide) == ["blocks", "reported", "review"]


def test_ranks_are_taken_over_the_set_it_is_given(world):
    findings = [_finding(world, route=f"/r{i}", fingerprint=f"f{i}") for i in range(3)]
    breadth = breadth_by_criterion(findings)
    assert set(ranks(findings, breadth)) == {"f0", "f1", "f2"}
    assert [f.fingerprint for f in in_fix_order(findings, breadth)][0] == "f0"


# ══ the backlog container ════════════════════════════════════════════════════════════

def test_the_container_is_one_per_project(world):
    first = backlog_container(world["t"], world["p"])
    assert backlog_container(world["t"], world["p"]).id == first.id


def test_the_container_is_visible_and_not_a_carrier(world):
    """Carriers are hidden from every user-facing backlog. This is the opposite kind of thing —
    a client is meant to see it, work through it and watch it shrink."""
    from integrations.onboarding import carrier_q

    backlog_container(world["t"], world["p"])
    visible = WorkItem.objects.filter(tenant_id=world["t"]).exclude(carrier_q())
    assert [item.title for item in visible] == [BACKLOG_TITLE]


def test_audit_defects_hang_off_the_container(world):
    _run_audit(world, [_screen("/login")])
    defects = WorkItem.objects.filter(tenant_id=world["t"], type=WorkItem.Type.DEFECT)
    assert defects.exists()
    assert all(d.parent and d.parent.feature_stream == BACKLOG_STREAM for d in defects)


def test_a_defect_carries_its_position_and_breadth(world):
    _run_audit(world, [_screen("/login"), _screen("/cart")])
    refs = [d.external_ref for d in
            WorkItem.objects.filter(tenant_id=world["t"], type=WorkItem.Type.DEFECT)]
    assert refs and all(r.get("priority") for r in refs)
    assert all(r.get("pages_affected", 0) >= 1 for r in refs)


def test_a_position_is_restamped_as_neighbours_are_fixed(world):
    """A priority nobody maintains is worse than none at all."""
    _finding(world, criterion="1.1.1", severity="critical", route="/a", fingerprint="worst")
    later = _finding(world, criterion="1.4.3", severity="high", route="/b",
                     fingerprint="second")
    record_a11y_findings(tenant_id=world["t"], project_id=world["p"])
    item = WorkItem.objects.get(tenant_id=world["t"], external_ref__a11y_finding="second")
    assert item.external_ref["priority"] == 2

    A11yFinding.objects.filter(fingerprint="worst").update(
        status=A11yFinding.Status.RESOLVED)
    record_a11y_findings(tenant_id=world["t"], project_id=world["p"])
    item.refresh_from_db()
    assert item.external_ref["priority"] == 1, "it moved up when the one above it closed"
    assert later.fingerprint == item.external_ref["a11y_finding"]


# ══ AC1 — the baseline document ══════════════════════════════════════════════════════

def test_one_criterion_is_one_row_however_many_findings(world):
    for index, route in enumerate(("/a", "/b", "/c")):
        _finding(world, criterion="1.4.3", severity="high", route=route,
                 fingerprint=f"f{index}")
    [row] = criterion_rows(world["t"], world["p"])
    assert row["criterion"] == "1.4.3"
    assert row["pages"] == 3 and row["failures"] == 3


def test_a_row_counts_failures_and_review_items_apart(world):
    _finding(world, criterion="1.4.3", route="/a", fingerprint="1")
    _finding(world, criterion="1.4.3", route="/b", outcome="needs_review", fingerprint="2")
    [row] = criterion_rows(world["t"], world["p"])
    assert row["failures"] == 1 and row["needs_review"] == 1


def test_the_worst_severity_wins_a_criterions_row(world):
    """A criterion whose level could not be read falls back to High; one such row must not make
    a genuinely Critical criterion look milder than it is."""
    _finding(world, criterion="1.1.1", severity="high", route="/a", fingerprint="1")
    _finding(world, criterion="1.1.1", severity="critical", route="/b", fingerprint="2")
    [row] = criterion_rows(world["t"], world["p"])
    assert row["severity"] == "critical"


def test_a_row_recovers_the_level_from_a_sibling_finding(world):
    _finding(world, criterion="1.4.3", wcag_level="", route="/a", fingerprint="1")
    _finding(world, criterion="1.4.3", wcag_level="AA", route="/b", fingerprint="2")
    [row] = criterion_rows(world["t"], world["p"])
    assert row["wcag_level"] == "AA"


def test_criterion_rows_lead_with_the_same_thing_the_backlog_does(world):
    _finding(world, criterion="1.4.3", severity="high", route="/a", fingerprint="1")
    _finding(world, criterion="1.1.1", severity="critical", route="/b", fingerprint="2")
    assert criterion_rows(world["t"], world["p"])[0]["criterion"] == \
        prioritised(world["t"], world["p"])[0]["criterion"]


def test_the_baseline_says_where_you_stand_and_what_to_fix(world):
    _finding(world, criterion="1.1.1", severity="critical", route="/login",
             fingerprint="one")
    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    assert "# Accessibility baseline" in body
    assert "## Where we stand, by criterion" in body
    assert "## What to fix first" in body
    assert "1.1.1 Non-text Content" in body
    assert "Critical" in body


def test_the_baseline_states_the_bar_before_any_number(world):
    _finding(world, fingerprint="one")
    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    assert body.index("## What this is measured against") < \
        body.index("## What to fix first")
    assert "Target: WCAG 2.2 AA" in body


def test_the_baseline_says_how_much_was_looked_at_first(world):
    """D-A11Y-3 at the scale of a whole document: a standing is unreadable without knowing how
    much of the application it is about."""
    result = _run_audit(world, [_screen("/login")])
    assert result["baseline"]["artifact_id"]
    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    assert "## What has been looked at" in body
    assert body.index("## What has been looked at") < body.index("## What to fix first")


def test_the_baseline_names_pages_the_audit_could_not_open(world):
    audit = _audit(world, "/login", "/admin")
    _post(world, audit, _screen("/login"))
    _post(world, audit, _screen("/admin", load_error="HTTP 403", elements=[],
                                violations=()))
    finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id))
    audit.refresh_from_db()

    body = baseline_body(tenant_id=world["t"], project_id=world["p"], audit=audit)
    assert "could not be opened" in body and "/admin" in body


def test_a_project_with_nothing_open_does_not_read_as_a_clean_bill_of_health(world):
    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    assert "No accessibility problems are open" in body
    assert "only good news if something has actually looked" in body


def test_an_unreadable_policy_is_stated_rather_than_applied_silently(world):
    from apps.projects.models import ProjectProfile

    ProjectProfile.objects.create(tenant=world["tenant"], project=world["project"],
                                  a11y={"gate": {"nonsense": True}})
    _finding(world, fingerprint="one")
    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    assert "could not be read" in body


def test_a_long_backlog_admits_it_was_cut_short(world):
    for index in range(MAX_BACKLOG_ROWS + 5):
        _finding(world, route=f"/r{index}", fingerprint=f"f{index}")
    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    assert "and 5 more" in body


def test_a_short_backlog_makes_no_such_claim(world):
    _finding(world, fingerprint="one")
    assert "more. This document shows" not in baseline_body(
        tenant_id=world["t"], project_id=world["p"])


def test_nothing_tracked_is_said_plainly_rather_than_shown_as_an_empty_table(world):
    _finding(world, severity="medium", fingerprint="reported-only")
    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    assert "Nothing in this project currently clears the bar" in body


# ══ the baseline as an artifact ══════════════════════════════════════════════════════

def test_publishing_registers_the_baseline_against_the_project(world):
    _finding(world, fingerprint="one")
    out = publish_baseline(tenant_id=world["t"], project_id=world["p"])
    artifact = Artifact.objects.get(id=out["artifact_id"])
    assert artifact.type == BASELINE_TYPE
    assert artifact.run_id is None and artifact.version == 1


def test_a_second_baseline_is_the_next_version_of_one_document(world):
    _finding(world, fingerprint="one")
    publish_baseline(tenant_id=world["t"], project_id=world["p"])
    second = publish_baseline(tenant_id=world["t"], project_id=world["p"])
    assert second["version"] == 2
    assert Artifact.objects.filter(tenant_id=world["t"], type=BASELINE_TYPE).count() == 2


def test_closing_one_audit_twice_updates_its_baseline_instead_of_stacking_a_version(world):
    """9.26.C. The closing path is not called exactly once: on 31 August the judging phase's
    write-completeness step published, was cancelled on its timeout, and the failure path
    published again — four versions of one document in two minutes, so the version history said
    this project had been baselined four times when it had been baselined once."""
    audit = _audit(world, "/login")
    _finding(world, fingerprint="one")

    first = publish_baseline(tenant_id=world["t"], project_id=world["p"], audit=audit)
    # A body that CHANGES between the two calls, which is what actually happened — findings were
    # still being written. A guard keyed on the content hash would have let this straight through.
    _finding(world, criterion="1.4.3", route="/other", fingerprint="two")
    second = publish_baseline(tenant_id=world["t"], project_id=world["p"], audit=audit)

    assert second["artifact_id"] == first["artifact_id"], "the same document, brought up to date"
    assert second["updated"] is True and first["updated"] is False
    assert Artifact.objects.filter(tenant_id=world["t"], type=BASELINE_TYPE).count() == 1


def test_a_different_audit_still_produces_the_next_version(world):
    """The guard must not cost the thing versioning exists for — comparing where this application
    stood at one audit against where it stands at the next."""
    audit_one = _audit(world, "/login")
    _finding(world, fingerprint="one")
    first = publish_baseline(tenant_id=world["t"], project_id=world["p"], audit=audit_one)

    audit_two = _audit(world, "/login")
    second = publish_baseline(tenant_id=world["t"], project_id=world["p"], audit=audit_two)

    assert second["artifact_id"] != first["artifact_id"]
    assert second["version"] == 2 and second["updated"] is False
    # Two versions of ONE document, which is what `supersedes` buys: same identity, next number.
    rows = Artifact.objects.filter(tenant_id=world["t"], type=BASELINE_TYPE)
    assert {r.version for r in rows} == {1, 2}
    assert len({r.title for r in rows}) == 1


def test_each_version_keeps_its_own_body(world):
    """A baseline you cannot compare against the last one is not a baseline."""
    _finding(world, criterion="1.1.1", fingerprint="one")
    first = Artifact.objects.get(id=publish_baseline(
        tenant_id=world["t"], project_id=world["p"])["artifact_id"])
    _finding(world, criterion="1.4.3", route="/other", fingerprint="two")
    second = Artifact.objects.get(id=publish_baseline(
        tenant_id=world["t"], project_id=world["p"])["artifact_id"])
    assert first.s3_key and second.s3_key and first.s3_key != second.s3_key


def test_the_baseline_is_not_the_per_run_report(world):
    """Two documents answering two questions. Collapsing them would give "where we stand" the
    other one's run-shaped identity."""
    from apps.a11y.report import REPORT_TYPE

    assert BASELINE_TYPE != REPORT_TYPE


def test_a_baseline_is_still_registered_when_the_object_store_blinks(world, monkeypatch):
    """Registered from its own hash rather than not at all — the same trade `publish_report`
    makes. A pointer-less baseline is worse than one with a body and far better than none."""
    from mcp_platform_state import tools

    monkeypatch.setattr(tools, "stage_artifact_body",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("s3 down")))
    _finding(world, fingerprint="one")
    out = publish_baseline(tenant_id=world["t"], project_id=world["p"])
    artifact = Artifact.objects.get(id=out["artifact_id"])
    assert artifact.content_hash and not artifact.s3_key


def test_a_baseline_that_cannot_be_written_does_not_lose_the_audit(world, monkeypatch):
    monkeypatch.setattr("apps.a11y.baseline_report.criterion_rows",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    result = _run_audit(world, [_screen("/login")])
    assert result["baseline"]["error"] == "boom"
    assert A11yFinding.objects.filter(tenant_id=world["t"]).exists(), \
        "the findings and their defects survived"


# ══ AC3 — movement between baselines ═════════════════════════════════════════════════

def test_the_first_baseline_says_it_has_nothing_to_compare_against(world):
    _finding(world, fingerprint="one")
    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    assert "This is the first baseline" in body


def test_the_previous_counts_come_from_the_last_published_baseline(world):
    _finding(world, criterion="1.1.1", fingerprint="one")
    assert previous_counts(world["t"], world["p"]) == {}
    publish_baseline(tenant_id=world["t"], project_id=world["p"])
    assert previous_counts(world["t"], world["p"]) == {"1.1.1": 1}


def test_movement_names_what_closed_and_what_is_new():
    change = movement([{"criterion": "1.4.3", "failures": 2, "needs_review": 0}],
                      {"1.1.1": 3, "1.4.3": 1})
    assert change["fixed_criteria"] == ["1.1.1"]
    assert change["new_criteria"] == []
    assert change["open_before"] == 4 and change["open_now"] == 2


def test_movement_reports_a_standstill_rather_than_saying_nothing():
    change = movement([{"criterion": "1.1.1", "failures": 1, "needs_review": 0}],
                      {"1.1.1": 1})
    assert not change["fixed_criteria"] and not change["new_criteria"]


def test_the_second_baseline_shows_what_moved(world):
    _finding(world, criterion="1.1.1", fingerprint="one")
    publish_baseline(tenant_id=world["t"], project_id=world["p"])
    A11yFinding.objects.filter(fingerprint="one").update(
        status=A11yFinding.Status.RESOLVED)
    _finding(world, criterion="1.4.3", route="/other", severity="high", fingerprint="two")

    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    assert "## Movement since the last baseline" in body
    assert "**Fully fixed:** 1.1.1" in body
    assert "**Newly breached:** 1.4.3" in body


# ══ AC2 + AC3 end to end — two real audits with a fix in between ═════════════════════

def test_a_second_audit_creates_no_duplicate_defects(world):
    """AC2, over the audit path rather than the build path QA-14 proved."""
    _run_audit(world, [_screen("/login")])
    before = list(WorkItem.objects.filter(
        tenant_id=world["t"], type=WorkItem.Type.DEFECT).values_list("id", flat=True))
    assert before

    _run_audit(world, [_screen("/login")])
    after = list(WorkItem.objects.filter(
        tenant_id=world["t"], type=WorkItem.Type.DEFECT).values_list("id", flat=True))
    assert sorted(after) == sorted(before), "the same tickets, not a second set"


def test_a_fix_between_audits_closes_its_ticket_and_leaves_the_rest_open(world):
    """AC3, the whole loop: audit an app, fix one page, audit again."""
    broken_cart = _screen("/cart", violations=(_violation(rule="link-name",
                                                          criteria=("2.4.7",),
                                                          nodes=("a.more",)),))
    _run_audit(world, [_screen("/login"), broken_cart])
    opened = {d.external_ref["criterion"]: d for d in WorkItem.objects.filter(
        tenant_id=world["t"], type=WorkItem.Type.DEFECT)}
    assert set(opened) == {"1.1.1", "2.4.7"}

    # `/login` was fixed; `/cart` was not. Both pages are visited again — resolution is only
    # ever claimed where a later check actually looked.
    _run_audit(world, [_screen("/login", violations=()), broken_cart])

    opened["1.1.1"].refresh_from_db()
    opened["2.4.7"].refresh_from_db()
    assert opened["1.1.1"].state == WorkItem.State.DONE, "the fixed one closed itself"
    assert opened["2.4.7"].state == WorkItem.State.IN_PROGRESS, "the broken one stayed open"


def test_the_second_baseline_records_the_fix(world):
    """A fix closes the *proven* breach. An element nobody could judge stays open as a question
    for a person — which is the distinction the two columns exist for, and the reason a
    baseline counts failures and review items separately instead of totalling them."""
    broken_cart = _screen("/cart", violations=(_violation(rule="link-name",
                                                          criteria=("2.4.7",),
                                                          nodes=("a.more",)),))
    _run_audit(world, [_screen("/login"), broken_cart])
    before = {row["criterion"]: row for row in criterion_rows(world["t"], world["p"])}
    assert before["1.1.1"]["failures"] == 1

    _run_audit(world, [_screen("/login", violations=()), broken_cart])

    latest = Artifact.objects.filter(
        tenant_id=world["t"], type=BASELINE_TYPE).order_by("-version").first()
    assert latest.version == 2

    after = {row["criterion"]: row for row in criterion_rows(world["t"], world["p"])}
    assert after["1.1.1"]["failures"] == 0, "the measured breach is gone"
    # Two, not one: both pages carry the same `alt="IMG_1234"` image, and with no judge in this
    # tenant neither could be answered. They stay open as questions on two pages, which is the
    # honest result — "we could not tell" is not "it is fine".
    assert after["1.1.1"]["needs_review"] == 2
    assert after["2.4.7"]["failures"] == 1, "and the page nobody fixed is untouched"


def test_a_reopened_problem_reuses_its_own_ticket(world):
    _run_audit(world, [_screen("/login")])
    [defect] = WorkItem.objects.filter(tenant_id=world["t"], type=WorkItem.Type.DEFECT)
    _run_audit(world, [_screen("/login", violations=())])
    defect.refresh_from_db()
    assert defect.state == WorkItem.State.DONE

    _run_audit(world, [_screen("/login")])
    defect.refresh_from_db()
    assert defect.state == WorkItem.State.IN_PROGRESS
    assert WorkItem.objects.filter(
        tenant_id=world["t"], type=WorkItem.Type.DEFECT).count() == 1


# ══ the REST surface ═════════════════════════════════════════════════════════════════

def test_the_backlog_endpoint_exists():
    from api.views import ProjectViewSet

    assert hasattr(ProjectViewSet, "a11y_backlog")
    assert ProjectViewSet.a11y_backlog.mapping.keys() >= {"get"}


# ══ a scope that moved is stated in the document, not only on the screen ═════
#
# The Movement section below compares this audit's findings with the last one's and calls the
# difference progress. That is only true if both audits looked at the same application. Twelve
# failing pages taken out of scope improve the numbers on their own, and a reader holding the
# document alone would have no way to know.


def test_the_report_says_when_the_page_list_moved_since_the_last_audit(world):
    _run_audit(world, [_screen("/"), _screen("/login")], routes=["/", "/login"])
    register_routes(tenant_id=world["t"], project_id=world["p"],
                    routes=["/", "/checkout"], replace=True)

    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    assert "The page list changed since the previous audit" in body
    assert "1 page(s) added" in body and "1 page(s) taken out of scope" in body
    assert "Taken out of scope: /login" in body


def test_a_report_whose_scope_did_not_move_says_nothing_about_it(world):
    """Every audit would otherwise carry a paragraph saying nothing changed, which is how a
    warning stops being read."""
    _run_audit(world, [_screen("/"), _screen("/login")], routes=["/", "/login"])

    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    assert "The page list changed" not in body


# ══ The backlog prints the whole instruction ═════════════════════════════════════════
#
# This column was cut at 160 characters — under half of what the per-run report allowed —
# and it held whichever of the fix or the evidence existed, never both. On the audit that
# prompted this, thirteen of twenty-six rows stopped mid-sentence; one of them stopped inside
# the quoted alt text it was telling somebody to write.

_LONG_FIX = (
    'Replace alt="" with descriptive alt text conveying the chart\'s data: alt="Bar chart: '
    "Loans per month in 2026. Lending rose from approximately 1,050 in January to a peak of "
    'approximately 1,225 in May, then declined to approximately 1,050 by August." For richer '
    "access to the underlying data, also consider adding a linked data table beneath the chart."
)


def test_the_backlog_prints_the_whole_fix_not_the_first_160_characters(world):
    _finding(world, suggested_fix=_LONG_FIX, fingerprint="long-fix")
    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    assert _LONG_FIX in body
    assert "declined to approximately 1,050 by August." in body


def test_the_backlog_table_still_scans_in_one_line_per_item(world):
    _finding(world, suggested_fix=_LONG_FIX, fingerprint="long-fix")
    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    row = next(x for x in body.splitlines() if x.startswith("| 1 | Critical |"))
    assert "declined to approximately 1,050 by August." not in row
    assert row.rstrip().endswith("|")


def test_the_backlog_gives_the_reason_as_well_as_the_fix(world):
    """The single bounded cell had to choose one. A document has room for both, and the fix
    without its reason is an instruction a developer cannot check."""
    _finding(world, suggested_fix="give it a name", evidence="the button announces nothing",
             fingerprint="both")
    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    assert "**What to change.** give it a name" in body
    assert "**Why.** the button announces nothing" in body


def test_the_detail_is_numbered_the_same_as_the_row_it_belongs_to(world):
    _finding(world, route="/a", fingerprint="a")
    _finding(world, route="/b", fingerprint="b")
    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    numbers = [x.split(".")[0].removeprefix("**") for x in body.splitlines()
               if x.startswith("**") and "` on `" in x]
    assert numbers == ["1", "2"]


def test_a_cut_short_backlog_says_so_before_the_detail_not_after_it(world):
    """A reader who stops at the table has still been told. The notice moved above the detail
    when the detail was added underneath it."""
    for index in range(MAX_BACKLOG_ROWS + 5):
        _finding(world, route=f"/r{index}", fingerprint=f"f{index}")
    lines = baseline_body(tenant_id=world["t"], project_id=world["p"]).splitlines()
    assert lines.index(next(x for x in lines if "and 5 more" in x)) < \
        lines.index(next(x for x in lines if x.startswith("### The same list")))


def test_a_backlog_item_with_no_words_gets_no_empty_detail(world):
    _finding(world, suggested_fix="", evidence="", fingerprint="silent")
    body = baseline_body(tenant_id=world["t"], project_id=world["p"])
    assert "| 1 | Critical |" in body
    assert "### The same list" not in body


# ── the silences a page count cannot express (21 August) ──────────────────────────────────────
#
# The per-run report has stated an incomplete check since D-A11Y-3. The baseline — the document
# a client is actually shown, and the one a conformance statement is built on — did not: it
# opened "2 criteria breached across 6 pages" over a check that had never looked at part of what
# it captured, and said nothing anywhere. The asymmetry was the dangerous half round.

def _audit_with(world, ai_pass=None, names=None):
    from apps.a11y.models import A11yBaselineAudit

    return A11yBaselineAudit.objects.create(
        tenant=world["tenant"], project=world["project"], routes=["/login"],
        status=A11yBaselineAudit.Status.COMPLETE,
        summary={"asked": 1, "opened": 1, "unreachable": [], "never_reported": [],
                 "ai_pass": ai_pass or {}, **({"names": names} if names else {})})


def test_the_baseline_says_when_part_of_the_check_never_happened(world):
    _finding(world, fingerprint="one")
    audit = _audit_with(world, ai_pass={"filed_unjudged": 0, "deferred_distinct": 6})
    body = baseline_body(tenant_id=world["t"], project_id=world["p"], audit=audit)
    assert "**This check is incomplete.**" in body
    assert "6 element(s)" in body
    assert "not counted as passing and not counted as failing" in body


def test_a_complete_check_says_nothing_rather_than_reassuring_anybody(world):
    _finding(world, fingerprint="one")
    audit = _audit_with(world, ai_pass={"filed_unjudged": 0, "deferred_distinct": 0})
    body = baseline_body(tenant_id=world["t"], project_id=world["p"], audit=audit)
    assert "incomplete" not in body


def test_the_baseline_counts_the_same_elements_the_button_offers(world):
    """One definition, not two. A document and a screen disagreeing about how much of the
    application was checked is this capability's own worst failure, in public."""
    from apps.a11y.baseline import unanswered_counts

    _finding(world, fingerprint="one")
    audit = _audit_with(world, ai_pass={"filed_unjudged": 3, "deferred_distinct": 4})
    counted = unanswered_counts(world["t"], [audit])[str(audit.id)]
    body = baseline_body(tenant_id=world["t"], project_id=world["p"], audit=audit)
    assert f"{counted} element(s) on the pages that were opened" in body


def test_a_re_judge_that_finished_the_job_clears_the_documents_warning_too(world):
    """`nothing_left` is the authoritative recount. The screen honours it; so must the document,
    or asking again would fix the button and leave the baseline claiming an incomplete check."""
    _finding(world, fingerprint="one")
    audit = _audit_with(world, ai_pass={"filed_unjudged": 0, "deferred_distinct": 6,
                                        "nothing_left": True})
    body = baseline_body(tenant_id=world["t"], project_id=world["p"], audit=audit)
    assert "incomplete" not in body


def test_the_baseline_says_when_a_whole_check_could_not_run(world):
    """The name check needs the browser to answer what each element is called. When the
    toolchain breaks it selects nothing — every element still arrives, three checks run
    perfectly, and one reports nothing. Silence from a check that never ran is
    indistinguishable from a clean result unless the document says which it was."""
    _finding(world, fingerprint="one")
    audit = _audit_with(
        world, ai_pass={"filed_unjudged": 0, "deferred_distinct": 0},
        names={"named": 0, "nameable": 91,
               "reason": "the browser did not answer when asked what each element is called."})
    body = baseline_body(tenant_id=world["t"], project_id=world["p"], audit=audit)
    assert "**One of the checks could not run at all.**" in body
    assert "its silence is not a clean result" in body


def test_a_clean_looking_baseline_still_states_an_incomplete_check(world):
    """The case that matters most and is easiest to miss. With no findings at all the document
    opens by saying nothing is open — which is exactly when "part of this was never checked"
    has to be on the page."""
    audit = _audit_with(world, ai_pass={"filed_unjudged": 0, "deferred_distinct": 6})
    body = baseline_body(tenant_id=world["t"], project_id=world["p"], audit=audit)
    assert "No accessibility problems are open" in body
    assert "**This check is incomplete.**" in body
