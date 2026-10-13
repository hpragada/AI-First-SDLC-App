"""Brownfield B4 — code-intelligence dispatch seam (Option C).

The web endpoint DISPATCHES a `CodeIntelJob`; the companion claims it (Runner-token auth) and
reports the real index back, where the server-side sink persists the `codebase_intelligence`
artifact. No WorkItem/AgentSpec — code intelligence is mechanical, repo-scoped analysis, not an
agent run, so it rides its own dispatch channel and never touches the Run/gate machinery.
"""
import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project, Repository
from apps.registry.models import Artifact
from apps.runs.enrollment import enroll_runner
from apps.runs.models import CodeIntelJob
from apps.tenancy.models import Tenant
from orchestration.trigger import trigger_code_intel


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Legacy", track=Project.Track.BROWNFIELD)
    repo = Repository.objects.create(tenant=t, project=project, name="acme/legacy",
                                     default_base="main")
    enrollment, token = enroll_runner(tenant_id=str(t.id), project_id=str(project.id), label="l")
    return {"t": str(t.id), "project": project, "repo": repo,
            "enrollment_id": str(enrollment.id), "token": token}


def _auth(world):
    return {"HTTP_AUTHORIZATION": f"Runner {world['token']}", "HTTP_X_TENANT_ID": world["t"]}


def _dispatch(world):
    return trigger_code_intel(tenant_id=world["t"], project_id=str(world["project"].id),
                              repo_id=str(world["repo"].id))


def test_trigger_creates_a_pending_job(world):
    out = _dispatch(world)
    assert out["status"] == "dispatched"
    job = CodeIntelJob.objects.get(id=out["job_id"])
    assert job.status == CodeIntelJob.Status.PENDING and job.repo_id == world["repo"].id


def test_companion_claims_the_job_then_204(world):
    _dispatch(world)
    client = APIClient()
    r = client.get("/api/runner/code-intel/", **_auth(world))
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["repo"] == "acme/legacy" and body["base"] == "main" and body["job_id"]
    # Bound to the claiming runner + claimed exactly once → the next poll is idle.
    assert client.get("/api/runner/code-intel/", **_auth(world)).status_code == 204


def test_claim_requires_a_runner_token(world):
    _dispatch(world)
    r = APIClient().get("/api/runner/code-intel/", HTTP_X_TENANT_ID=world["t"])
    assert r.status_code == 401


def test_report_persists_the_artifact_and_marks_indexed(world):
    out = _dispatch(world)
    job_id = out["job_id"]
    client = APIClient()
    client.get("/api/runner/code-intel/", **_auth(world))              # claim
    reported = client.post(
        f"/api/runner/code-intel/{job_id}/report/",
        {"index": {"file_count": 1284, "commits": 412, "hotspots": 3}, "summary": "billing svc"},
        format="json", **_auth(world))
    assert reported.status_code == 200, reported.content
    art = Artifact.objects.get(id=reported.json()["artifact_id"])
    assert art.type == "codebase_intelligence" and art.repo_id == world["repo"].id
    assert CodeIntelJob.objects.get(id=job_id).status == CodeIntelJob.Status.INDEXED


def test_failed_report_marks_the_job_failed_without_persisting(world):
    out = _dispatch(world)
    job_id = out["job_id"]
    client = APIClient()
    client.get("/api/runner/code-intel/", **_auth(world))              # claim
    reported = client.post(f"/api/runner/code-intel/{job_id}/report/",
                           {"status": "failed", "error": "no clone configured for repo"},
                           format="json", **_auth(world))
    assert reported.status_code == 200 and reported.json()["status"] == "failed"
    job = CodeIntelJob.objects.get(id=job_id)
    assert job.status == CodeIntelJob.Status.FAILED and "no clone" in job.error
    assert not Artifact.objects.filter(
        project=world["project"], type="codebase_intelligence").exists()


def test_report_to_unknown_job_is_404(world):
    r = APIClient().post(
        "/api/runner/code-intel/00000000-0000-0000-0000-000000000000/report/",
        {"index": {}}, format="json", **_auth(world))
    assert r.status_code == 404
