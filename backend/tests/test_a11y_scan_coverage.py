"""QA-16 — accessibility coverage stops depending on who remembered to ask for it.

Against the task's acceptance criteria:

  AC1  a generated script runs axe AND supplies the AI checks' inputs, for every screen
       (*corrected*: a script cannot run the AI checks — see D-A11Y-42)
  AC2  the generated script still passes the agent's run/compile step
  AC3  existing scaffolding is never overwritten

**Why there is backend code in an "agent edit" task.** `capture.py` carried this comment:
*"Absent is 'the scan reported nothing here' … It is NOT read as 'no scan ran': that distinction
belongs to the test report, which says whether the accessibility case executed at all."* That was
true only while a capture existed solely for a dedicated accessibility case. QA-16 captures every
screen the suite visits — including on a stack with no scanner wired — so an empty violation list
would be indistinguishable from a clean page, and the report would claim the rules found nothing
wrong on a screen the rules never looked at. That is D-A11Y-3's failure exactly, so the fact needs
a home that travels with the screen: `axe_error`.
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import pytest
from PIL import Image as PILImage

from apps.a11y.capture import fingerprint, parse_capture
from apps.a11y.ingest import ingest_screen
from apps.a11y.models import A11yScreenScan
from apps.a11y.report import merge_run, report_body
from apps.a11y.scanner import rule_findings_for
from apps.projects.models import Project
from apps.tenancy.models import Tenant
from storage.object_store import InMemoryObjectStore

_AGENTS = Path(__file__).resolve().parents[2] / "agents"


def _body(key: str) -> str:
    return (_AGENTS / key / "agent.md").read_text(encoding="utf-8")


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


def _screen(**over) -> dict:
    base = {
        "route": "/login", "url": "http://localhost:5173/login",
        "screenshot_base64": base64.b64encode(_png()).decode("ascii"),
        "elements": [_element()],
    }
    base.update(over)
    return base


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="App")
    return {"t": str(tenant.id), "p": str(project.id), "tenant": tenant, "project": project}


def _ingest(world, screen):
    return ingest_screen(
        tenant_id=world["t"], project_id=world["p"],
        screen=parse_capture(json.dumps(screen))[0],
        run_id=None, object_store=InMemoryObjectStore())


# ══ the capture format carries "no scan ran here" ════════════════════════════════

def test_a_screen_can_say_the_scanner_never_ran_on_it():
    [screen] = parse_capture(json.dumps(_screen(
        axe_error="no axe integration is installed for Playwright Python")))
    assert screen["axe_error"] == "no axe integration is installed for Playwright Python"
    assert screen["axe_violations"] == []


def test_a_scanned_screen_carries_no_error():
    [screen] = parse_capture(json.dumps(_screen(axe_violations=[])))
    assert screen["axe_error"] == ""


def test_the_reason_is_bounded_like_every_other_captured_string():
    [screen] = parse_capture(json.dumps(_screen(axe_error="x" * 5_000)))
    assert len(screen["axe_error"]) <= 1_000


def test_whether_the_scanner_ran_changes_the_screens_identity():
    """QA-07 carries an unchanged screen forward. A screen carried forward from a scanned run
    must not silently inherit "scanned" when this run could not scan it."""
    scanned = parse_capture(json.dumps(_screen()))[0]
    unscanned = parse_capture(json.dumps(_screen(axe_error="no scanner on this stack")))[0]
    assert fingerprint(scanned) != fingerprint(unscanned)


def test_two_identically_unscanned_screens_still_match():
    a = parse_capture(json.dumps(_screen(axe_error="no scanner")))[0]
    b = parse_capture(json.dumps(_screen(axe_error="no scanner")))[0]
    assert fingerprint(a) == fingerprint(b)


# ══ it survives the ingest and reaches the scan record ═══════════════════════════

def test_the_reason_is_stored_on_the_screen_scan(world):
    _ingest(world, _screen(axe_error="no axe integration for this stack"))
    scan = A11yScreenScan.objects.get(tenant_id=world["t"], route="/login")
    assert scan.scan_error == "no axe integration for this stack"
    assert scan.violations == []


def test_a_normal_scan_stores_no_reason(world):
    _ingest(world, _screen(axe_violations=[{
        "rule": "image-alt", "impact": "critical", "criteria": ["1.1.1"],
        "help": "Images must have alternate text", "nodes": ["img.hero"]}]))
    scan = A11yScreenScan.objects.get(tenant_id=world["t"], route="/login")
    assert scan.scan_error == ""
    assert len(scan.violations) == 1


def test_rescanning_a_screen_clears_a_stale_reason(world):
    """The stack got its scanner wired between runs — the screen must stop claiming otherwise."""
    _ingest(world, _screen(axe_error="no axe integration"))
    _ingest(world, _screen(axe_violations=[]))
    assert A11yScreenScan.objects.get(tenant_id=world["t"], route="/login").scan_error == ""


# ══ the scanner reports it, and the report says it out loud ══════════════════════

def test_the_scan_result_lists_screens_it_could_not_scan(world):
    _ingest(world, _screen(axe_error="no axe integration"))
    _ingest(world, _screen(route="/cart", url="http://localhost:5173/cart"))

    scan = rule_findings_for(world["t"], world["p"], None)
    assert scan.unscanned == [{"route": "/login", "reason": "no axe integration"}]
    assert sorted(scan.routes) == ["/cart", "/login"], "both were captured"


def test_a_fully_scanned_run_reports_nothing_unscanned(world):
    _ingest(world, _screen())
    assert rule_findings_for(world["t"], world["p"], None).unscanned == []


def test_the_report_names_the_screens_the_rules_never_looked_at(world):
    _ingest(world, _screen(axe_error="no axe integration for Playwright Python"))
    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=None)
    body = report_body(report)

    assert "The rule scanner did not run on every screen" in body
    assert "/login" in body
    assert "no axe integration for Playwright Python" in body


def test_a_clean_run_makes_no_such_claim(world):
    _ingest(world, _screen())
    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=None)
    assert report.unscanned == []
    assert "The rule scanner did not run on every screen" not in report_body(report)


def test_an_unscanned_screen_is_not_confused_with_an_unjudged_element(world):
    """Two different silences. The rule half and the AI half fail independently, and a reader
    acting on one must not be told the other."""
    _ingest(world, _screen(axe_error="no scanner"))
    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=None)
    assert report.unscanned and report.unjudged, "this run has both, and they are separate lists"
    assert report.unscanned[0]["route"] == "/login"
    assert all("scanner" not in (item.get("reason") or "") for item in report.unjudged)


# ══ AC1/AC3 — what the agent body now teaches ════════════════════════════════════

def test_09b_captures_on_every_script_not_only_accessibility_cases():
    body = _body("09b_test_automation")
    assert "Step 5b: Every Script" in body
    assert "This step applies to every script you generate, not only an `Accessibility` case" \
        in body


def test_09b_is_told_it_does_not_run_the_ai_checks_itself():
    """D-A11Y-42: the checks are server-side; a script on a laptop cannot reach them, and
    orchestration in a test script would break non-negotiable #2."""
    body = _body("09b_test_automation")
    assert "You do not run the AI checks and you must not try to" in body


def test_09b_never_fails_a_functional_test_on_an_accessibility_finding():
    """D-A11Y-8's trap again: one screen alternating between a functional failure and an
    accessibility failure reads as a flaky test, and a quarantined test blocks nothing."""
    body = _body("09b_test_automation")
    assert "A functional test never fails because of what the capture found" in body
    assert "quarantined" in body


def test_09b_captures_each_route_once_per_run():
    body = _body("09b_test_automation")
    assert "Capture each distinct route once per run" in body


def test_09b_says_so_when_the_scanner_cannot_run_rather_than_leaving_it_blank():
    body = _body("09b_test_automation")
    assert "axe_error" in body
    assert "an empty violation list is the same shape as a clean page" in body


def test_09b_still_captures_on_a_stack_with_no_scanner():
    """The AI half works wherever a browser can be driven; only the scan is missing."""
    body = _body("09b_test_automation")
    assert "the AI half works on every stack that can drive a browser" in body


def test_09b_still_refuses_to_guess_a_package_for_an_unwired_stack():
    """QA-11a's rule survives the rewrite — a wrong import reads as a scan that ran."""
    body = _body("09b_test_automation")
    assert "Never guess a package name" in body
    assert "Not supported on this stack" in body


def test_09b_still_never_overwrites_scaffolding():
    body = _body("09b_test_automation")
    assert "No existing file overwritten" in body


def test_09b_quality_gate_now_asks_for_the_capture_on_every_script():
    body = _body("09b_test_automation")
    gate = body.split("## Quality Gate")[1]
    assert "For **every** script: `test-results/a11y-candidates.json` was written" in gate
    assert "No functional test was failed by an accessibility finding" in gate


def test_09b_keeps_its_accessibility_case_behaviour():
    """QA-11a's pass/fail scan is unchanged — this task added coverage, it did not move it."""
    body = _body("09b_test_automation")
    assert "Step 5a: Accessibility Cases" in body
    assert "impact `critical` or `serious` fails it" in body


# ══ G1 — the greenfield producer records what PASSED, not only what failed ═══════
#
# QA-24 taught the platform to keep all four of axe's channels and updated the BROWNFIELD
# scanner (`runner/companion/assets/a11y_audit.mjs`) to write them. It never updated the
# greenfield producer — this agent — so a greenfield capture carried violations only, and
# `_rule_list` correctly read that as "no positive evidence": every criterion the scan touched
# reported as *not evaluated* and the conformance statement said "Nothing checked this."
#
# These tests hold BOTH sides of that seam together. The first one is the load-bearing one: it
# takes the example document out of the agent body and runs it through the platform's own
# parser, so the instruction cannot drift from the format the platform accepts without a test
# going red.


def _capture_example(key: str) -> dict:
    """The Step 5b capture example, lifted verbatim out of the agent body."""
    body = _body(key).split("## Step 5b")[1]
    return json.loads(body.split("```json")[1].split("```")[0])


def test_09b_capture_example_is_a_document_the_platform_actually_parses():
    """The seam itself: the shape the agent is shown is the shape `capture.py` reads."""
    screen = parse_capture(json.dumps(_capture_example("09b_test_automation")))[0]
    assert screen["route"] == "/checkout"
    assert screen["scanner_version"] == "axe-core 4.9.1"
    for channel in ("axe_violations", "axe_passes", "axe_inapplicable", "axe_incomplete"):
        assert screen[channel], f"{channel} did not survive the parser"


def test_09b_capture_example_produces_coverage_and_not_only_failures():
    """What G1 is for: a criterion the scan found clean is recorded as examined."""
    from apps.a11y import coverage

    screen = parse_capture(json.dumps(_capture_example("09b_test_automation")))[0]
    outcomes = {outcome for _criterion, outcome, _rule in coverage.from_scan(screen)}
    assert outcomes == {"failed", "passed", "not_applicable", "needs_human"}


def test_09b_says_inapplicable_is_not_a_pass():
    """The two facts a merged channel would destroy: 'there was no video here' and 'the
    captions were checked and were fine' are different things to tell a client."""
    body = _body("09b_test_automation")
    assert "Keep them apart: inapplicable is not a pass" in body
    assert "never move one between them" in body


def test_09b_says_an_absent_channel_is_not_a_claim_that_nothing_passed():
    """`_rule_list`'s rule, stated where the producer can act on it."""
    body = _body("09b_test_automation")
    assert 'An absent array means "this capture carries no positive evidence"' in body
    assert 'it never means "nothing passed"' in body


def test_09b_scopes_the_capture_scan_to_the_standard():
    """An unscoped scan fills the channels with best-practice rules that map to no criterion —
    and `_rule_list`'s own refusal message tells the author to use the tag filter."""
    step = _body("09b_test_automation").split("## Step 5b")[1].split("## Step 6")[0]
    assert "Scope the capture's scan to the standard" in step
    assert "'wcag22a', 'wcag22aa'" in step


def test_09b_quality_gate_asks_for_all_four_channels():
    gate = _body("09b_test_automation").split("## Quality Gate")[1]
    for channel in ("axe_passes", "axe_inapplicable", "axe_incomplete", "scanner_version"):
        assert channel in gate, channel


def test_09b_omits_every_scan_field_when_no_scan_ran():
    """`axe_error` means the screen was seen and not measured — so nothing from the scan may
    be written, not just the violations."""
    body = _body("09b_test_automation")
    assert ("omit every field the scan would have produced — `axe`, `axe_violations`, "
            "`axe_passes`, `axe_inapplicable`, `axe_incomplete` and `scanner_version`") in body


def test_the_edited_body_still_passes_the_platform_reference_sweep():
    """AGENT_MIGRATION_SPEC §8 — a migrated body naming a local file is a failed migration."""
    body = _body("09b_test_automation")
    for banned in ("tasks.md", "requirements.md", "CLAUDE.md", ".claude/", "docs/"):
        assert banned not in body, banned
