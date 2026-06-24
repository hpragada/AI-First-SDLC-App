"""P2 — remote Platform-State serving (§3): build agent → HTTP → platform-state tools.

The tenant is bound server-side from the authenticated enrollment (never the body), so RLS
scoping stays on the platform; only the build-phase tool subset is reachable.
"""
import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.registry.models import Artifact
from apps.tenancy.models import Tenant


@pytest.fixture
def client():
    return APIClient()


def _enroll(client, tenant, project):
    r = client.post("/api/runners/", {"project_id": str(project.id), "label": "l"},
                    format="json", HTTP_X_TENANT_ID=str(tenant.id))
    assert r.status_code == 201, r.content
    return r.json()["token"]


def _state(client, tenant, token, tool, **args):
    return client.post(f"/api/runner/state/{tool}/", args, format="json",
                       HTTP_X_TENANT_ID=str(tenant.id), HTTP_AUTHORIZATION=f"Runner {token}")


def test_enroll_then_register_artifact_binds_tenant_server_side(db, client):
    t = Tenant.objects.create(name="A")
    p = Project.objects.create(tenant=t, name="App")
    token = _enroll(client, t, p)

    r = _state(client, t, token, "register_artifact", project_id=str(p.id), run_id=None,
               phase="implementation", type="code", sor="internal", content_hash="h")
    assert r.status_code == 200, r.content
    art = r.json()["result"]
    assert Artifact.objects.filter(id=art["id"], tenant=t, type="code").exists()


def test_unauthenticated_call_is_401(db, client):
    t = Tenant.objects.create(name="A")
    r = client.post("/api/runner/state/log_event/",
                    {"actor": "x", "action": "y", "target_type": "run"},
                    format="json", HTTP_X_TENANT_ID=str(t.id))   # no Runner token
    assert r.status_code == 401


def test_tool_outside_build_allowlist_is_403(db, client):
    t = Tenant.objects.create(name="A")
    p = Project.objects.create(tenant=t, name="App")
    token = _enroll(client, t, p)
    r = _state(client, t, token, "detect_drift", artifact_id="x")  # planning-only tool
    assert r.status_code == 403


def test_token_with_mismatched_tenant_is_401(db, client):
    a = Tenant.objects.create(name="A")
    pa = Project.objects.create(tenant=a, name="A")
    b = Tenant.objects.create(name="B")
    token_a = _enroll(client, a, pa)
    # Present A's token but claim tenant B → cannot authenticate.
    r = _state(client, b, token_a, "log_event", actor="x", action="y", target_type="run")
    assert r.status_code == 401


def test_runner_cannot_read_another_tenants_artifacts(db, client):
    a = Tenant.objects.create(name="A")
    pa = Project.objects.create(tenant=a, name="A")
    token_a = _enroll(client, a, pa)
    _state(client, a, token_a, "register_artifact", project_id=str(pa.id), run_id=None,
           phase="implementation", type="code", sor="internal", content_hash="h")

    b = Tenant.objects.create(name="B")
    pb = Project.objects.create(tenant=b, name="B")
    token_b = _enroll(client, b, pb)
    # B asks for A's project — its enrollment binds tenant=B, so it sees nothing.
    r = _state(client, b, token_b, "list_artifacts", project_id=str(pa.id))
    assert r.status_code == 200 and r.json()["result"] == []
