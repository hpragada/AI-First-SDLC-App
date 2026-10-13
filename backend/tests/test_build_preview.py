"""P3-09bR-5 — the build saga records/tears-down the companion-local preview env (D7).

`provision_preview_core` records the `PreviewEnv` the build reported (+ PR link); the workflow
calls `teardown_preview_core` at terminal states. Both are best-effort + idempotent, and a no-op
for phases that bring no app up (07/11, or a build that reported no preview URL).
"""
import pytest

from apps.projects.models import Project
from apps.quality.models import PreviewEnv
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from orchestration.build_activities import provision_preview_core, teardown_preview_core
from orchestration.build_types import BuildInput, BuildReport


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="App")
    story = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY,
                                    feature_stream="ST-1", title="Login")
    spec = AgentSpec.objects.create(tenant=t, key="09b_test_automation", body_ref="x")
    run = Run.objects.create(tenant=t, work_item=story, agent_spec=spec,
                             temporal_workflow_id="wf-b")
    inp = BuildInput(
        run_id=str(run.id), tenant_id=str(t.id), project_id=str(project.id),
        work_item_id=str(story.id), agent_spec_id=str(spec.id), work_item_key="WI-1",
        repo="acme/api", base="main", phase="test_automation",
    )
    return {"t": t, "project": project, "story": story, "run": run, "inp": inp}


def _report(**kw):
    return BuildReport(status="ok", branch="feature/WI-1", head_sha="abc", **kw)


def test_activities_registered_on_the_build_worker():
    from orchestration.build_activities import BUILD_ACTIVITIES

    names = {getattr(a, "__temporal_activity_definition").name for a in BUILD_ACTIVITIES}
    assert {"provision_preview", "teardown_preview"} <= names


def test_provision_records_a_ready_preview_env(world):
    out = provision_preview_core(world["inp"], _report(preview_url="http://127.0.0.1:5173"))
    assert out["provisioned"] is True

    env = PreviewEnv.objects.get(run_id=world["run"].id)
    assert env.status == PreviewEnv.Status.READY
    assert env.url == "http://127.0.0.1:5173"
    assert env.provider == PreviewEnv.Provider.COMPANION_LOCAL


def test_provision_is_a_noop_without_a_preview_url(world):
    # 07/11, or a 09b build that brought no app up → nothing recorded.
    out = provision_preview_core(world["inp"], _report(preview_url=""))
    assert out["provisioned"] is False
    assert not PreviewEnv.objects.filter(run_id=world["run"].id).exists()


def test_teardown_marks_the_preview_torn_down(world):
    provision_preview_core(world["inp"], _report(preview_url="http://127.0.0.1:5173"))
    out = teardown_preview_core(world["inp"])
    assert out["torn_down"] is True
    assert PreviewEnv.objects.get(run_id=world["run"].id).status == PreviewEnv.Status.TORN_DOWN


def test_teardown_is_a_noop_when_no_preview_recorded(world):
    out = teardown_preview_core(world["inp"])
    assert out["torn_down"] is False
