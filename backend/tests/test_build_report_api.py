"""P2 — companion build fetch + report API (§4): closes the dispatch→await loop."""
import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.runs.enrollment import enroll_runner
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem


@pytest.fixture
def dispatched(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY, title="x",
                                 state=WorkItem.State.ACCEPTED)
    spec = AgentSpec.objects.create(tenant=t, key="07_implementation", body_ref="")
    run = Run.objects.create(
        tenant=t, work_item=wi, agent_spec=spec, engine="claude", status=Run.Status.RUNNING,
        temporal_workflow_id="build-run-x", inputs={"build_task": {"repo": "acme/api",
                                                                   "work_item_key": "ST-1"}},
    )
    _enrollment, token = enroll_runner(tenant_id=t.id, project_id=p.id)
    return t, run, token


def _hdr(t, token):
    return {"HTTP_X_TENANT_ID": str(t.id), "HTTP_AUTHORIZATION": f"Runner {token}"}


def test_companion_fetches_its_build_task(dispatched):
    t, run, token = dispatched
    client = APIClient()
    r = client.get(f"/api/runner/builds/{run.id}/", **_hdr(t, token))
    assert r.status_code == 200 and r.json()["repo"] == "acme/api"


def test_fetch_requires_runner_token(dispatched):
    t, run, _token = dispatched
    r = APIClient().get(f"/api/runner/builds/{run.id}/", HTTP_X_TENANT_ID=str(t.id))
    assert r.status_code == 401


def test_report_records_and_signals_the_workflow(dispatched, monkeypatch):
    t, run, token = dispatched
    sent = {}
    monkeypatch.setattr(
        "orchestration.build_report._default_signal_sender",
        lambda workflow_id, report: sent.update(workflow_id=workflow_id, status=report.status,
                                                branch=report.branch),
    )
    client = APIClient()
    r = client.post(f"/api/runner/builds/{run.id}/report/",
                    {"status": "ok", "branch": "feature/ST-1", "head_sha": "abc",
                     "changed_files": ["login.py"]},
                    format="json", **_hdr(t, token))
    assert r.status_code == 200 and r.json()["signaled"] is True
    assert sent == {"workflow_id": "build-run-x", "status": "ok", "branch": "feature/ST-1"}
    run.refresh_from_db()
    assert run.outputs["report"]["branch"] == "feature/ST-1"
