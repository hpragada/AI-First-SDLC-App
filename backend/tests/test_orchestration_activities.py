"""P0-T8 — activity-core tests (spec §5).

Each core is exercised against the real DB with a fake driver + in-memory object store,
covering the happy path, idempotency by run_id, and the approve/reject branches.
"""
import pytest

from apps.gates.models import Approval
from apps.projects.models import Project, ProjectProfile
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from drivers import RunResult
from orchestration import activities
from orchestration.types import AgentRunInput
from storage import InMemoryObjectStore


class _FakeDriver:
    def __init__(self, body="# PRD\nThe PRD body.", cost=0.0731):
        self.body = body
        self.cost = cost

    async def run_planning_task(
        self, *, manifest, agent_spec, mcp_servers, allowed_tools, work_item
    ):
        assert "# Project" in manifest  # got the composed manifest
        return RunResult(
            outputs={"result": self.body, "text": self.body},
            artifacts=[], cost_usd=self.cost, raw_messages=[],
        )


@pytest.fixture
def store():
    return InMemoryObjectStore()


@pytest.fixture
def wired(monkeypatch, store):
    monkeypatch.setattr(activities, "get_driver", lambda: _FakeDriver())
    monkeypatch.setattr(activities, "get_object_store", lambda: store)
    return store


@pytest.fixture
def run_input(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    ProjectProfile.objects.create(tenant=t, project=project, important_context="ctx")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="x", phase_label="prd")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)
    return AgentRunInput(
        run_id=str(run.id), tenant_id=str(t.id), project_id=str(project.id),
        work_item_id=str(wi.id), agent_spec_id=str(spec.id), phase="prd",
        required_role="product_owner",
    )


def test_compose_manifest_core(run_input):
    md = activities.compose_manifest_core(run_input)
    assert "# Project" in md and "# Current Work Item" in md and "- phase: prd" in md


def test_execute_agent_core_drafts_and_registers(wired, store, run_input):
    out = activities.execute_agent_core(run_input, manifest="# Project\nx")
    assert out["cost_usd"] == 0.0731

    artifact = Artifact.objects.get(id=out["artifact_ids"][0])
    assert artifact.status == Artifact.Status.DRAFT  # not published yet (#5)
    assert artifact.sor == Artifact.SoR.INTERNAL
    assert artifact.content_hash.startswith("sha256:")
    # Body is in the object store, only the pointer is in the registry (#1/#3).
    assert store.get(artifact.s3_key) == b"# PRD\nThe PRD body."

    run = Run.objects.get(id=run_input.run_id)
    assert run.status == Run.Status.AWAITING_GATE
    assert float(run.cost_usd) == 0.0731


def test_execute_agent_core_is_idempotent(wired, run_input):
    first = activities.execute_agent_core(run_input, manifest="# Project\nx")
    second = activities.execute_agent_core(run_input, manifest="# Project\nx")
    assert second.get("idempotent") is True
    assert second["artifact_ids"] == first["artifact_ids"]
    assert Artifact.objects.filter(run_id=run_input.run_id).count() == 1  # no duplicate


def test_open_gate_core_creates_pending_and_is_idempotent(wired, run_input):
    activities.execute_agent_core(run_input, manifest="# Project\nx")
    approval_id = activities.open_gate_core(run_input)
    again = activities.open_gate_core(run_input)
    assert approval_id == again
    approval = Approval.objects.get(id=approval_id)
    assert approval.decision == Approval.Decision.PENDING
    assert approval.required_role == "product_owner"
    assert Approval.objects.filter(run_id=run_input.run_id).count() == 1


def test_publish_artifacts_core(wired, store, run_input):
    activities.execute_agent_core(run_input, manifest="# Project\nx")
    activities.open_gate_core(run_input)
    result = activities.publish_artifacts_core(run_input)

    artifact = Artifact.objects.get(id=result["published"][0])
    assert artifact.status == Artifact.Status.PUBLISHED and artifact.sor == Artifact.SoR.INTERNAL
    # Snapshot copied in the store.
    snap = next(k for k in store._data if k.startswith("snapshots/"))
    assert store.get(snap) == store.get(artifact.s3_key)
    assert Run.objects.get(id=run_input.run_id).status == Run.Status.COMPLETED
    # The Approval decision is recorded by the gate service (T9), not publish.


def test_transition_work_item_core(wired, run_input):
    activities.transition_work_item_core(run_input, "done")
    assert WorkItem.objects.get(id=run_input.work_item_id).state == WorkItem.State.DONE


def test_reject_run_core(wired, run_input):
    activities.execute_agent_core(run_input, manifest="# Project\nx")
    activities.open_gate_core(run_input)
    activities.reject_run_core(run_input, comment="needs more detail")

    assert Run.objects.get(id=run_input.run_id).status == Run.Status.REJECTED
    assert WorkItem.objects.get(id=run_input.work_item_id).state == WorkItem.State.IN_PROGRESS
    # Approval decision recorded by the gate service (T9), verified there.
