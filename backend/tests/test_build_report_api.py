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


def test_secret_findings_survive_ingestion_and_reach_the_workflow(dispatched):
    """D6: `report_build` admits only fields declared on `BuildReport`, so the findings would be
    silently dropped at this boundary if the field were missing. Pin that they are persisted on
    the run (making a block diagnosable after the fact) AND reach the signalled report, which is
    what lets the workflow seed the retry with them."""
    from dataclasses import asdict

    from orchestration.build_report import report_build

    t, run, _token = dispatched
    sent = {}
    findings = [{"kind": "high_entropy_secret",
                 "path": "packages/backend/src/auth/jwt.strategy.ts",
                 "line": 73, "preview": "conf***ow (24 chars)"}]
    report_build(
        tenant_id=str(t.id), run_id=str(run.id),
        report={"status": "failed", "branch": "feature/ST-1",
                "message": "secret scan blocked the push: 1 finding(s)",
                "secret_findings": findings},
        signal_sender=lambda wf, rep: sent.update(report=asdict(rep)),
    )
    run.refresh_from_db()
    assert run.outputs["report"]["secret_findings"] == findings
    assert sent["report"]["secret_findings"] == findings


def test_report_scrubs_nul_bytes_before_persisting(dispatched):
    """A NUL (\\x00) in companion-reported text — 09b captures live browser/app output that can
    carry one — must be stripped at ingestion. Otherwise the Postgres JSON write ("run.outputs"
    here, and later the defect brief / run.inputs the workflow derives) fails with "\\u0000
    cannot be converted to text" and parks the run after the real work already landed."""
    from dataclasses import asdict

    from orchestration.build_report import report_build

    t, run, _token = dispatched
    sent = {}
    report = {
        "status": "ok",
        "branch": "feature/ST-1",
        "message": "assertion failed:\x00 dashboard error\x00",
        "test_results": [
            {"test_ref": "TC-001", "status": "failed",
             "evidence": "snapshot bytes \x00\x01\x18 here"},
        ],
        "test_summary": "0 passed, 1 failed\x00",
    }
    out = report_build(
        tenant_id=str(t.id), run_id=str(run.id), report=report,
        signal_sender=lambda wf, rep: sent.update(report=asdict(rep)),
    )
    assert out["signaled"] is True

    # Nothing persisted or signalled may still carry a NUL.
    run.refresh_from_db()
    persisted = run.outputs["report"]
    assert "\x00" not in persisted["message"]
    assert "\x00" not in persisted["test_summary"]
    assert "\x00" not in persisted["test_results"][0]["evidence"]
    # The non-NUL control byte (\x01/\x18) is valid Postgres text and is left intact.
    assert "\x18" in persisted["test_results"][0]["evidence"]
    assert "\x00" not in sent["report"]["message"]
    assert "\x00" not in sent["report"]["test_results"][0]["evidence"]
