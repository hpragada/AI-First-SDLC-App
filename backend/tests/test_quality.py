"""P3 — Test/Quality plane: models + RLS, result import, flaky quarantine, defect loopback,
test-impact selection, preview env (Phase 3 §3/§5/§6)."""
import psycopg
import pytest
from django.conf import settings
from django.db import IntegrityError, connection
from mcp_platform_state import tools

from apps.projects.models import Project
from apps.quality import preview, services
from apps.quality.models import PreviewEnv, TestExecution, TestQuarantine
from apps.registry.models import AgentSpec, Artifact, TraceEdge
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    story = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY,
                                    feature_stream="ST-1", title="Login")
    spec = AgentSpec.objects.create(tenant=t, key="09_testing", body_ref="x")
    run = Run.objects.create(tenant=t, work_item=story, agent_spec=spec)
    # A code artifact under the story so the test_report can trace to the code under test.
    code = tools.register_artifact(t.id, p.id, run.id, "implementation", "code", "git", "h",
                                   external_ref={"repo": "acme/api", "number": 7})
    return {"t": t, "p": p, "story": story, "run": run, "code_id": code["id"]}


# ── models + uniqueness ─────────────────────────────────────────────
def test_models_persist_and_quarantine_is_unique(world):
    t, p = world["t"], world["p"]
    TestQuarantine.objects.create(tenant=t, project=p, test_ref="PROJ-2", reason="flip")
    with pytest.raises(IntegrityError):
        TestQuarantine.objects.create(tenant=t, project=p, test_ref="PROJ-2")  # same (t,p,ref)


# ── result import: all-pass ─────────────────────────────────────────
def test_import_all_pass_registers_report_no_defects(world):
    out = services.import_test_results(
        tenant_id=world["t"].id, project_id=world["p"].id, work_item_id=world["story"].id,
        run_id=world["run"].id,
        results=[{"test_ref": "PROJ-2", "status": "PASS"},
                 {"test_ref": "PROJ-3", "status": "PASS"}],
    )
    assert out["status"] == "passed" and out["defects_opened"] == []
    assert Artifact.objects.filter(run_id=world["run"].id, type="test_report").count() == 1
    # test_report → code lineage edge (rel=tests)
    report = Artifact.objects.get(id=out["test_report_id"])
    assert TraceEdge.objects.filter(from_artifact=report, to_artifact_id=world["code_id"],
                                    rel="tests").exists()


# ── defect loopback: open on FAIL, close on subsequent PASS ─────────
def test_failing_test_opens_defect_then_closes_on_pass(world):
    t, p, story, run = world["t"], world["p"], world["story"], world["run"]
    out = services.import_test_results(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id, run_id=run.id,
        results=[{"test_ref": "PROJ-9", "status": "FAIL", "evidence": "boom"}],
    )
    assert out["status"] == "failed" and len(out["defects_opened"]) == 1
    defect = WorkItem.objects.get(parent_id=story.id, type=WorkItem.Type.DEFECT)
    assert defect.external_ref["test_ref"] == "PROJ-9"
    assert defect.external_ref["defect"] == "DEF-PROJ-9"
    assert defect.state == WorkItem.State.IN_PROGRESS

    # Re-import (same run) with the test now passing → the defect closes; no duplicate execution.
    out2 = services.import_test_results(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id, run_id=run.id,
        results=[{"test_ref": "PROJ-9", "status": "PASS"}],
    )
    assert out2["status"] == "passed" and len(out2["defects_closed"]) == 1
    defect.refresh_from_db()
    assert defect.state == WorkItem.State.DONE
    assert TestExecution.objects.filter(run_id=run.id, work_item_id=story.id).count() == 1
    assert WorkItem.objects.filter(parent_id=story.id, type=WorkItem.Type.DEFECT).count() == 1


# ── closing keys off a reported PASS, never off silence ─────────────
def test_a_partial_run_does_not_close_the_defect_of_a_test_it_never_ran(world):
    """The false-green test-impact selection (D9) would otherwise guarantee: a run reporting
    only SOME tests says nothing about the rest, and silence must never read as success."""
    t, p, story, run = world["t"], world["p"], world["story"], world["run"]
    services.import_test_results(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id, run_id=run.id,
        results=[{"test_ref": "PROJ-9", "status": "FAIL"}])
    defect = WorkItem.objects.get(parent_id=story.id, type=WorkItem.Type.DEFECT)

    # An impact-selected run covering only an unrelated test — PROJ-9 did not run at all.
    out = services.import_test_results(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id, run_id=run.id,
        results=[{"test_ref": "PROJ-2", "status": "PASS"}])
    assert out["defects_closed"] == []
    defect.refresh_from_db()
    assert defect.state == WorkItem.State.IN_PROGRESS       # still open — it was never re-run


def test_an_empty_report_is_not_a_green_run(world):
    """A build that ran no tests must not register a passing execution, and must not close
    the defects it said nothing about."""
    t, p, story, run = world["t"], world["p"], world["story"], world["run"]
    services.import_test_results(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id, run_id=run.id,
        results=[{"test_ref": "PROJ-9", "status": "FAIL"}])
    defect = WorkItem.objects.get(parent_id=story.id, type=WorkItem.Type.DEFECT)
    executions = TestExecution.objects.filter(run_id=run.id).count()

    out = services.import_test_results(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id, run_id=run.id, results=[])
    assert out["status"] == "skipped" and out["test_execution_id"] is None
    assert out["defects_closed"] == []
    defect.refresh_from_db()
    assert defect.state == WorkItem.State.IN_PROGRESS
    assert TestExecution.objects.filter(run_id=run.id).count() == executions  # nothing recorded


def test_a_quarantined_test_does_not_close_its_defect(world):
    """A flip-flopping test's result is ambiguous by definition — it neither blocks the gate
    nor counts as the PASS that resolves a defect."""
    t, p, story, run = world["t"], world["p"], world["story"], world["run"]
    services.import_test_results(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id, run_id=run.id,
        results=[{"test_ref": "FLIP", "status": "FAIL"}])
    defect = WorkItem.objects.get(parent_id=story.id, type=WorkItem.Type.DEFECT)

    out = services.import_test_results(     # flips within this execution → quarantined
        tenant_id=t.id, project_id=p.id, work_item_id=story.id, run_id=run.id,
        results=[{"test_ref": "FLIP", "status": "PASS"}, {"test_ref": "FLIP", "status": "FAIL"}])
    assert out["flaky"] == ["FLIP"] and out["defects_closed"] == []
    defect.refresh_from_db()
    assert defect.state == WorkItem.State.IN_PROGRESS


# ── flaky quarantine: conflicting statuses within one import ────────
def test_flaky_test_is_quarantined_and_does_not_open_a_defect(world):
    t, p, story, run = world["t"], world["p"], world["story"], world["run"]
    out = services.import_test_results(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id, run_id=run.id,
        results=[{"test_ref": "T1", "status": "PASS"}, {"test_ref": "T1", "status": "FAIL"}],
    )
    assert out["flaky"] == ["T1"]
    assert TestExecution.objects.get(run_id=run.id).flaky is True
    assert TestQuarantine.objects.filter(tenant=t, project=p, test_ref="T1", active=True).exists()
    # Quarantined → excluded from the blocking gate: no defect, status not failed.
    assert out["defects_opened"] == [] and out["status"] == "passed"
    assert not WorkItem.objects.filter(parent_id=story.id, type=WorkItem.Type.DEFECT).exists()


# ── security defect loopback (D8) ───────────────────────────────────
def test_record_security_findings_opens_then_closes_defects(world):
    t, p, story = world["t"], world["p"], world["story"]
    out = services.record_security_findings(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id,
        findings=[{"id": "SEC-001", "severity": "critical", "title": "SQLi"},
                  {"id": "SEC-002", "severity": "high", "title": "missing authz"},
                  {"id": "SEC-003", "severity": "medium", "title": "verbose error"}],
    )
    assert out["blocking"] == ["SEC-001", "SEC-002"]            # medium is not blocking
    assert len(out["opened"]) == 2
    defects = WorkItem.objects.filter(parent_id=story.id, type=WorkItem.Type.DEFECT)
    assert defects.count() == 2
    crit = defects.get(external_ref__finding="SEC-001")
    assert crit.external_ref["kind"] == "security" and crit.external_ref["defect"] == "DEF-SEC-001"
    assert crit.state == WorkItem.State.IN_PROGRESS

    # Re-run with the critical resolved → that defect closes; the high stays open.
    out2 = services.record_security_findings(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id,
        findings=[{"id": "SEC-002", "severity": "high", "title": "missing authz"}],
    )
    assert len(out2["closed"]) == 1
    crit.refresh_from_db()
    assert crit.state == WorkItem.State.DONE
    assert defects.count() == 2                                # no duplicates


# ── test-impact selection v1 (traceability graph) ───────────────────
def test_select_impacted_tests_walks_the_traceability_graph(world):
    t, p, run = world["t"], world["p"], world["run"]

    def art(type_):
        return tools.register_artifact(t.id, p.id, run.id, "x", type_, "internal", "h")["id"]

    req, req2 = art("requirement"), art("requirement")
    code, t1, t2 = art("code"), art("test_case"), art("test_case")
    tools.add_trace_edge(t.id, code, req, "derives")     # code implements/derives the requirement
    tools.add_trace_edge(t.id, t1, req, "tests")         # T1 covers that requirement
    tools.add_trace_edge(t.id, t2, req2, "tests")        # T2 covers an unrelated requirement

    impacted = services.select_impacted_tests(t.id, code_artifact_id=code)
    assert impacted == [t1]                              # only the test sharing the upstream req


# ── preview env (companion-local seam) ──────────────────────────────
def test_provision_and_teardown_preview_env(world):
    t, p, story, run = world["t"], world["p"], world["story"], world["run"]
    comments = []

    class _FakeHost:
        def add_pr_comment(self, *, pr_ref, body):
            comments.append((pr_ref, body))

    out = preview.provision_preview(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id, run_id=run.id,
        pr_ref="acme/api#7", url="http://localhost:5173",
        get_capability=lambda tid, cap: _FakeHost(),
    )
    env = PreviewEnv.objects.get(id=out["preview_id"])
    assert env.status == PreviewEnv.Status.READY and env.provider == "companion_local"
    assert comments and "http://localhost:5173" in comments[0][1]

    teardown = preview.teardown_preview(tenant_id=t.id, preview_id=out["preview_id"])
    assert teardown["status"] == "torn_down"


# ── RLS isolation on the new quality tables (proven via the app role) ─
def _app_role_connection():
    sd = connection.settings_dict
    with connection.cursor() as cur:
        cur.execute("SELECT current_database()")
        dbname = cur.fetchone()[0]
    return psycopg.connect(
        host=sd["HOST"], port=sd["PORT"], dbname=dbname,
        user=settings.APP_DB_USER, password=settings.APP_DB_PASSWORD, autocommit=True,
    )


@pytest.mark.django_db(transaction=True)
def test_rls_isolates_quality_tables():
    a = Tenant.objects.create(name="A")
    b = Tenant.objects.create(name="B")
    pa = Project.objects.create(tenant=a, name="A")
    pb = Project.objects.create(tenant=b, name="B")
    wa = WorkItem.objects.create(tenant=a, project=pa, type=WorkItem.Type.STORY)
    wb = WorkItem.objects.create(tenant=b, project=pb, type=WorkItem.Type.STORY)
    TestExecution.objects.create(tenant=a, project=pa, work_item=wa)
    TestExecution.objects.create(tenant=b, project=pb, work_item=wb)
    TestQuarantine.objects.create(tenant=a, project=pa, test_ref="A-1")
    PreviewEnv.objects.create(tenant=b, project=pb, work_item=wb, url="u")

    raw = _app_role_connection()
    try:
        with raw.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [str(a.id)])
            cur.execute("SELECT count(*) FROM quality_testexecution")
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT count(*) FROM quality_testquarantine")
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT count(*) FROM quality_previewenv")
            assert cur.fetchone()[0] == 0          # B's preview is invisible to A

            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [""])
            cur.execute("SELECT count(*) FROM quality_testexecution")
            assert cur.fetchone()[0] == 0          # no tenant context -> fail closed
    finally:
        raw.close()
