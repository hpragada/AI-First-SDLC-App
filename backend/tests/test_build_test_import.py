"""P3/D4 — the missing seam: a build report's suite results feed the test loop.

`import_build_test_results_core` is what connects the companion's worktree run to machinery
that was fully built but had no production caller: `TestExecution` + `test_report`, the defect
loopback, the flaky quarantine, and (via #1) the qa_lead gate's blocking-test rule.

Bounds under test: only phases the catalog marks `imports_test_results` import; an empty
report is never a green run; results stay internal (Xray export stays user-triggered).
"""
import pytest

from apps.gates.testgate import BLOCKING_TESTS_KEY
from apps.projects.models import Project
from apps.quality.models import TestExecution
from apps.registry.models import AgentSpec, Artifact
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from orchestration.build_activities import import_build_test_results_core
from orchestration.build_types import BuildInput, BuildReport


def _world(db, agent_key="09b_test_automation"):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="App")
    story = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY,
                                    feature_stream="ST-1", title="Login")
    spec = AgentSpec.objects.create(tenant=t, key=agent_key, body_ref="x")
    from apps.runs.models import Run

    run = Run.objects.create(tenant=t, work_item=story, agent_spec=spec,
                             temporal_workflow_id="wf-b")
    qa = User.objects.create_user(email="qa@acme.test", name="Carlos", tenant=t, password="pw")
    Membership.objects.create(tenant=t, user=qa, project=project, role="qa_lead")
    inp = BuildInput(
        run_id=str(run.id), tenant_id=str(t.id), project_id=str(project.id),
        work_item_id=str(story.id), agent_spec_id=str(spec.id), work_item_key="WI-1",
        repo="acme/api", base="main",
    )
    return {"t": t, "project": project, "story": story, "run": run, "inp": inp,
            "qa_id": str(qa.id)}


@pytest.fixture
def world(db):
    return _world(db)


def _report(results, **kw):
    return BuildReport(status="ok", branch="feature/WI-1", head_sha="abc",
                       test_results=results, **kw)


# ── registration: the workflow calls this activity by name ──────────
def test_the_import_activity_is_registered_on_the_build_worker():
    """`build_workflow` executes "import_build_test_results" by name. If it were missing from
    BUILD_ACTIVITIES the worker would fail the activity as unregistered — breaking EVERY build,
    not just a test one. The live-Temporal workflow tests skip without a broker, so assert the
    registration directly."""
    from orchestration.build_activities import BUILD_ACTIVITIES

    names = {getattr(a, "__temporal_activity_definition").name for a in BUILD_ACTIVITIES}
    assert "import_build_test_results" in names


# ── the seam ────────────────────────────────────────────────────────
def test_build_results_open_a_defect_and_record_an_execution(world):
    out = import_build_test_results_core(world["inp"], _report(
        [{"test_ref": "TC-7", "status": "PASS", "evidence": ""},
         {"test_ref": "TC-9", "status": "FAIL", "evidence": "AssertionError: expected 401"}],
        test_summary="1 passed, 1 failed",
    ))
    assert out["imported"] is True and out["status"] == "failed"
    assert len(out["defects_opened"]) == 1

    execution = TestExecution.objects.get(run_id=world["run"].id)
    assert execution.status == TestExecution.Status.FAILED
    assert Artifact.objects.filter(run_id=world["run"].id, type="test_report").count() == 1
    defect = WorkItem.objects.get(parent_id=world["story"].id, type=WorkItem.Type.DEFECT)
    assert defect.external_ref["test_ref"] == "TC-9"


def test_a_later_build_reporting_the_test_passing_closes_the_defect(world):
    import_build_test_results_core(world["inp"], _report(
        [{"test_ref": "TC-9", "status": "FAIL", "evidence": "boom"}]))
    defect = WorkItem.objects.get(parent_id=world["story"].id, type=WorkItem.Type.DEFECT)

    out = import_build_test_results_core(world["inp"], _report(
        [{"test_ref": "TC-9", "status": "PASS", "evidence": ""}]))
    assert out["status"] == "passed" and len(out["defects_closed"]) == 1
    defect.refresh_from_db()
    assert defect.state == WorkItem.State.DONE
    # Idempotent by (run, work_item): the remediation re-import updates, never duplicates.
    assert TestExecution.objects.filter(run_id=world["run"].id).count() == 1


def test_the_defect_blocks_the_qa_gate_until_the_test_passes(world):
    """The whole point of the seam: a red suite from a real build now holds the QA gate shut."""
    from apps.gates.models import Approval
    from apps.gates.services import GateConditionsError, decide_gate
    from orchestration.activities import open_gate_core
    from orchestration.types import AgentRunInput

    import_build_test_results_core(world["inp"], _report(
        [{"test_ref": "TC-9", "status": "FAIL", "evidence": "boom"}]))
    gate_inp = AgentRunInput(
        run_id=str(world["run"].id), tenant_id=str(world["t"].id),
        project_id=str(world["project"].id), work_item_id=str(world["story"].id),
        agent_spec_id="s", phase="testing", required_role="qa_lead",
    )
    approval_id = open_gate_core(gate_inp)
    conditions = Approval.objects.get(id=approval_id).conditions
    # Since QA-15 the testing gate also carries the accessibility rule. This test is about the
    # blocking-test rule, so it asserts that rule is there rather than that it is alone; the
    # accessibility one is satisfied here (nothing was ever scanned for this story).
    assert BLOCKING_TESTS_KEY in {c["key"] for c in conditions}

    with pytest.raises(GateConditionsError, match="TC-9"):
        decide_gate(tenant_id=str(world["t"].id), approval_id=approval_id,
                    user_id=world["qa_id"], decision="approved",
                    signal_sender=lambda *a, **k: None)

    import_build_test_results_core(world["inp"], _report(
        [{"test_ref": "TC-9", "status": "PASS", "evidence": ""}]))
    res = decide_gate(tenant_id=str(world["t"].id), approval_id=approval_id,
                      user_id=world["qa_id"], decision="approved",
                      signal_sender=lambda *a, **k: None)
    assert res["decision"] == "approved"


# ── bounds ──────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_an_implementation_build_does_not_import_its_unit_test_results():
    """07's own red unit test fails its build (as always) — it must not open a QA defect."""
    world = _world(None, agent_key="07_implementation")
    out = import_build_test_results_core(world["inp"], _report(
        [{"test_ref": "tests.test_login.test_ok", "status": "FAIL", "evidence": "boom"}]))
    assert out["imported"] is False and "does not import" in out["reason"]
    assert not WorkItem.objects.filter(parent_id=world["story"].id,
                                       type=WorkItem.Type.DEFECT).exists()
    assert not TestExecution.objects.filter(run_id=world["run"].id).exists()


def test_a_build_that_reported_no_results_is_a_no_op(world):
    """No report is not a pass: no execution recorded, nothing closed."""
    out = import_build_test_results_core(world["inp"], _report([]))
    assert out["imported"] is False and "no test results" in out["reason"]
    assert not TestExecution.objects.filter(run_id=world["run"].id).exists()


def test_import_never_pushes_to_the_sor(world, monkeypatch):
    """Xray export is user-triggered (2026-07-07) — a build report must never auto-push."""
    def _boom(*a, **k):
        raise AssertionError("import must not reach the SoR capability")

    monkeypatch.setattr("integrations.registry.get_capability", _boom)
    out = import_build_test_results_core(world["inp"], _report(
        [{"test_ref": "TC-9", "status": "FAIL", "evidence": "boom"}]))
    assert out["imported"] is True
    assert TestExecution.objects.get(run_id=world["run"].id).external_ref is None
