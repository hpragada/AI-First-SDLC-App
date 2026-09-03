"""QA-11a — the first accessibility scan that actually executes, and the evidence it produces.

Three things are proven here, and the first two are the ones that would fail *silently*:

  1. **Evidence survives.** The full failure text is filed as the run's `test_report` artifact
     body in the object store before anything shortens it; the stored row keeps a bounded copy
     that says where the rest is. Until QA-11a the text was cut at parse time, so no store
     downstream could ever have held it.
  2. **An accessibility result has its own identity.** Agent 09 writes one accessibility test
     case per screen, with a plain `TC-XXX` number and a priority. Sharing a functional case's
     id would make one pass and one failure look like a single flapping test — which the
     platform quarantines, and a quarantined test does not block the gate.
  3. **09b actually runs the suite** and leaves the report where the companion collects it.
     A generated script that only type-checks produces no result, and no result means no
     defect, no gate and no loopback.
"""
from pathlib import Path

import pytest
from mcp_platform_state import tools

from apps.projects.models import Project
from apps.quality import services
from apps.quality.junit import _MAX_EVIDENCE, parse_junit
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem

_AGENTS = Path(__file__).resolve().parents[2] / "agents"


def _body(key: str) -> str:
    return (_AGENTS / key / "agent.md").read_text(encoding="utf-8")


# ── 1. agent 09: one accessibility case per screen, with its own identity ──
def test_09_writes_an_accessibility_case_per_screen():
    body = _body("09_testing")
    assert "Write one Accessibility test case per screen" in body
    assert "wireframe" in body


def test_09_forbids_a_decorated_test_case_id():
    """`TC-ACC-001` does not resolve to a test case, so its defect loses the case's priority
    and opens Critical whatever the finding was."""
    body = _body("09_testing")
    assert "TC-ACC-001" in body and "Never a decorated id" in body
    # …and the example in the traceability map no longer uses one.
    assert "| TC-ACC-001 |" not in body


def test_09_forbids_sharing_a_functional_cases_id():
    body = _body("09_testing")
    assert "Never attach the accessibility check to a screen's functional case" in body
    assert "quarantined" in body and "stops blocking the gate" in body


def test_09_maps_wcag_level_to_defect_priority():
    body = _body("09_testing")
    assert "Level A failure is `Critical`" in body and "Level AA failure is `High`" in body


# ── 2. agent 09b: a real scan, only where we can name the engine ───────────
def test_09b_generates_an_axe_scan_for_accessibility_cases():
    body = _body("09b_test_automation")
    assert "Step 5a: Accessibility Cases" in body
    assert "@axe-core/playwright" in body
    assert "wcag22aa" in body


def test_09b_fails_on_critical_and_serious_only():
    body = _body("09b_test_automation")
    assert "impact `critical` or `serious` fails it" in body
    assert "do **not** fail" in body


def test_09b_never_guesses_a_package_for_an_unwired_stack():
    """The two Playwright stacks are wired; everything else reports an honest gap. A
    plausible-looking wrong import reads as a scan that ran."""
    body = _body("09b_test_automation")
    assert "Never guess a package name" in body
    assert "Not supported on this stack" in body
    assert "Playwright Python" in body and "already** depends on" in body


def test_09b_runs_the_suite_and_emits_the_report_where_the_platform_looks():
    body = _body("09b_test_automation")
    assert "Then actually run the suite" in body
    assert "test-results/junit.xml" in body          # the first path the companion checks
    assert "npx playwright test" in body and "python -m pytest" in body
    assert "never remove or replace a reporter the project already configures" in body.lower()


def test_09b_never_makes_a_failure_go_away():
    body = _body("09b_test_automation")
    assert "A failing test is a result, not a problem to make go away." in body
    assert "do not skip a failing test" in body.lower()


def test_09b_message_leads_with_the_totals():
    body = _body("09b_test_automation")
    assert "18 violations on /checkout" in body
    assert "you are not writing to a size limit" in body.lower()


@pytest.mark.parametrize("key", ["09_testing", "09b_test_automation"])
def test_reference_sweep_is_clean(key):
    """§8: an agent body naming a local file is a failed migration."""
    forbidden = [".md", "docs/", "claude.md", "tasks.md", "reply approved", "/sdlc:"]
    lowered = _body(key).lower()
    assert not [token for token in forbidden if token in lowered]


# ── 3. the evidence: parsed in full, filed in full, bounded only on the row ─
def _junit(evidence: str, test_ref: str = "TC-031") -> str:
    return (
        '<testsuite name="a11y">'
        f'<testcase classname="a11y" name="{test_ref} accessibility">'
        f'<failure message="{evidence}"></failure>'
        "</testcase></testsuite>"
    )


def test_the_parser_no_longer_cuts_evidence_to_a_display_size():
    """The regression that started this: 18 accessibility violations arrived as 4."""
    long_evidence = "violation line that is quite wordy; " * 400        # ~14k chars
    parsed = parse_junit(_junit(long_evidence))
    assert len(parsed[0]["evidence"]) > 10_000
    assert parsed[0]["evidence"].startswith("violation line")


def test_a_runaway_log_still_hits_a_safety_valve():
    """A quarter of a megabyte from one test is a log, not evidence."""
    assert _MAX_EVIDENCE == 256_000
    parsed = parse_junit(_junit("x" * (_MAX_EVIDENCE + 5_000)))
    assert len(parsed[0]["evidence"]) == _MAX_EVIDENCE


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="App")
    story = WorkItem.objects.create(tenant=tenant, project=project, type=WorkItem.Type.STORY,
                                    feature_stream="ST-1", title="Checkout")
    spec = AgentSpec.objects.create(tenant=tenant, key="09_testing", body_ref="x",
                                    phase_label="testing")
    run = Run.objects.create(tenant=tenant, work_item=story, agent_spec=spec,
                             temporal_workflow_id="wf-a11y")
    return {"tenant": tenant, "project": project, "story": story, "run": run}


def _import(world, results):
    return services.import_test_results(
        tenant_id=world["tenant"].id, project_id=world["project"].id,
        work_item_id=world["story"].id, run_id=world["run"].id, results=results,
    )


def _report_body(world, report_id: str) -> str:
    from integrations.preview import internal_draft_body

    artifact = Artifact.objects.get(id=report_id, tenant_id=world["tenant"].id)
    return internal_draft_body(artifact)


def test_the_full_evidence_is_filed_as_the_report_body(world):
    """The fix itself: everything the suite said, kept, and reachable — no re-run needed."""
    evidence = "\n".join(f"1.4.3  serious  color-contrast  element-{i}" for i in range(400))
    out = _import(world, [{"test_ref": "TC-031", "status": "FAIL", "evidence": evidence}])

    body = _report_body(world, out["test_report_id"])
    assert "element-0" in body and "element-399" in body         # nothing dropped
    assert "# Test report" in body and "TC-031" in body


def test_the_stored_row_is_bounded_and_says_where_the_rest_is(world):
    evidence = "x" * 50_000
    out = _import(world, [{"test_ref": "TC-031", "status": "FAIL", "evidence": evidence}])

    from apps.quality.models import TestExecution
    row = TestExecution.objects.get(id=out["test_execution_id"]).results[0]
    assert len(row["evidence"]) <= services._ROW_EVIDENCE_CHARS
    assert f"artifact {out['test_report_id']}" in row["evidence"]
    assert "truncat" not in row["evidence"].lower()              # a destination, not a warning


def test_a_shortened_row_still_reads_sensibly_with_no_report_to_point_at():
    """The object store was unreachable, so there is no artifact id to name — the row still
    says where to look rather than trailing off mid-sentence."""
    rows = services._rows_for_state([{"test_ref": "TC-031", "status": "FAIL",
                                      "evidence": "q" * 50_000}], None)
    assert rows[0]["evidence"].endswith("Full evidence: this run's test report.")
    assert len(rows[0]["evidence"]) <= services._ROW_EVIDENCE_CHARS


def test_short_evidence_is_left_exactly_as_it_was(world):
    out = _import(world, [{"test_ref": "TC-031", "status": "FAIL", "evidence": "1 violation"}])
    from apps.quality.models import TestExecution
    assert TestExecution.objects.get(id=out["test_execution_id"]).results[0]["evidence"] == \
        "1 violation"


def test_the_artifact_carries_a_body_pointer_not_just_a_hash(world):
    out = _import(world, [{"test_ref": "TC-031", "status": "FAIL", "evidence": "boom"}])
    artifact = Artifact.objects.get(id=out["test_report_id"], tenant_id=world["tenant"].id)
    assert artifact.s3_key and artifact.content_hash


def test_a_re_import_of_the_same_run_updates_one_report(world):
    first = _import(world, [{"test_ref": "TC-031", "status": "FAIL", "evidence": "one"}])
    second = _import(world, [{"test_ref": "TC-031", "status": "FAIL", "evidence": "two"}])
    assert first["test_report_id"] == second["test_report_id"]
    assert "two" in _report_body(world, second["test_report_id"])     # body replaced in place
    assert Artifact.objects.filter(tenant_id=world["tenant"].id, run_id=world["run"].id,
                                   type="test_report").count() == 1


def test_an_unreachable_object_store_never_fails_the_import(world, monkeypatch):
    """A red suite's defects matter more than its prose. If the body cannot be filed, the
    import still records the execution, opens the defect, and keeps the row's summary."""
    def _boom(*args, **kwargs):
        raise OSError("object store unreachable")

    monkeypatch.setattr(tools, "stage_artifact_body", _boom)
    out = _import(world, [{"test_ref": "TC-031", "status": "FAIL", "evidence": "y" * 50_000}])
    assert out["test_execution_id"] and out["defects_opened"]
    artifact = Artifact.objects.get(id=out["test_report_id"], tenant_id=world["tenant"].id)
    assert not artifact.s3_key and artifact.content_hash          # hash-only, as before


def test_the_defect_still_points_at_the_report_that_holds_the_evidence(world):
    out = _import(world, [{"test_ref": "TC-031", "status": "FAIL", "evidence": "z" * 50_000}])
    defect = WorkItem.objects.get(id=out["defects_opened"][0])
    assert defect.external_ref["test_report"] == out["test_report_id"]


def test_a_passing_run_files_a_report_too(world):
    """So "what did this run actually check?" has an answer on a green run as well."""
    out = _import(world, [{"test_ref": "TC-031", "status": "PASS", "evidence": ""}])
    body = _report_body(world, out["test_report_id"])
    assert "TC-031" in body and "1 passed" in body


# ── 4. the npm registry the scan needs to install its engine ──────────────
def test_the_npm_registry_is_reachable_by_default():
    from runner.companion.guardrails import EgressPolicy

    class _Task:
        api_url = "https://platform.example"

    policy = EgressPolicy.for_task(_Task())
    assert policy.allows("https://registry.npmjs.org/@axe-core/playwright")
    assert policy.allows("registry.npmjs.org")


def test_an_unrelated_host_is_still_denied():
    from runner.companion.guardrails import EgressDenied, EgressPolicy

    class _Task:
        api_url = "https://platform.example"

    policy = EgressPolicy.for_task(_Task())
    assert not policy.allows("https://evil.example/exfiltrate")
    with pytest.raises(EgressDenied):
        policy.check("https://evil.example/exfiltrate")
