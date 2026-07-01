"""P4.7-T10 — artifact preview read-through (J19, DECISION-5): wraps `read_artifact_preview`
behind `GET /api/artifacts/{id}/preview/`, backing S-28 (list, pointers only) / S-29 (preview).

The body is fetched **on demand** — never persisted onto the registry row: internal (draft/
staged, not yet pushed) reads its S3 body; confluence/jira read live through their capability
(`DocStore.get_page`/`TaskTracker.get_issue` — themselves "read-through, not stored"); any
other SoR (or an unavailable connector) still returns the pointer/version + a deep-link, no body.
"""
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.integrations.models import IntegrationConnection
from apps.projects.models import Project
from apps.registry.models import Artifact
from apps.tenancy.models import Membership, Tenant, User
from integrations.registry import _BUILDERS, register_connector
from storage import s3_from_settings


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


@pytest.fixture
def project(tenant):
    return Project.objects.create(tenant=tenant, name="Payments")


@pytest.fixture
def member(tenant, project):
    u = User.objects.create_user(
        email="dev@acme.com", name="Dev", tenant=tenant, password="dev-pass!"
    )
    Membership.objects.create(tenant=tenant, user=u, project=project, role="engineer")
    return u


def _login(client, email, password):
    assert client.post(
        "/api/auth/login/", {"email": email, "password": password}, format="json"
    ).status_code == 200


def _preview_url(artifact_id):
    return f"/api/artifacts/{artifact_id}/preview/"


def _list_url():
    return "/api/artifacts/"


# ── internal (S3 read-through) ───────────────────────────────────────
def test_preview_internal_artifact_returns_stored_body(client, project, member):
    store = s3_from_settings()
    key = f"test-preview/{project.tenant_id}/{project.id}/prd.md"
    store.put(key, "# PRD\nSome content.")
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="prd", type="prd",
        sor="internal", status="draft", s3_key=key, version=1,
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(artifact.id))
    assert resp.status_code == 200
    assert resp.data["body"] == "# PRD\nSome content."
    assert resp.data["content_type"] == "text/markdown"
    assert resp.data["status"] == "draft"
    assert resp.data["version"] == 1
    assert resp.data["sor_link"] is None


def test_preview_missing_internal_body_is_404(client, project, member):
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="prd", type="prd",
        sor="internal", status="draft", s3_key="", version=1,
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(artifact.id))
    assert resp.status_code == 404


def test_preview_unknown_artifact_is_404(client, project, member):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url("00000000-0000-0000-0000-000000000000"))
    assert resp.status_code == 404


# ── external SoR (read-through via capability) ───────────────────────
def test_preview_confluence_artifact_reads_through_docstore(client, project, member):
    page = SimpleNamespace(
        id="123", title="Multi-Currency Requirements", body_html="<p>Live body</p>",
        version=2, url="https://acme.atlassian.net/wiki/123", space_key="SDLC",
    )
    register_connector("docstore", "test_fake", lambda conn: SimpleNamespace(
        get_page=lambda *, page_ref: page
    ))
    try:
        IntegrationConnection.objects.create(
            tenant=project.tenant, capability="docstore", connector="test_fake",
        )
        artifact = Artifact.objects.create(
            tenant=project.tenant, project=project, phase="onboarding", type="document",
            sor="confluence", status="published", version=2,
            external_ref={"sor": "confluence", "id": "123", "url": "https://old-link/123"},
        )
        _login(client, "dev@acme.com", "dev-pass!")
        resp = client.get(_preview_url(artifact.id))
        assert resp.status_code == 200
        assert resp.data["body"] == "<p>Live body</p>"
        assert resp.data["content_type"] == "text/html"
        # the live page's URL wins over the stored external_ref url
        assert resp.data["sor_link"] == "https://acme.atlassian.net/wiki/123"
    finally:
        _BUILDERS.pop(("docstore", "test_fake"), None)


def test_preview_falls_back_to_link_when_capability_unavailable(client, project, member):
    """No docstore connector configured for this tenant → graceful degrade (S-29 'Preview
    unavailable'): the pointer/version/link still return, just without a body."""
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="onboarding", type="document",
        sor="confluence", status="published", version=1,
        external_ref={"sor": "confluence", "id": "999", "url": "https://acme.atlassian.net/999"},
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(artifact.id))
    assert resp.status_code == 200
    assert resp.data["body"] == ""
    assert resp.data["sor_link"] == "https://acme.atlassian.net/999"


def test_preview_other_sor_returns_link_only(client, project, member):
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="implementation", type="code",
        sor="git", status="published", version=1,
        external_ref={"sor": "git", "repo": "acme/payments-api", "number": 42,
                      "url": "https://github.com/acme/payments-api/pull/42"},
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(artifact.id))
    assert resp.status_code == 200
    assert resp.data["body"] == ""
    assert resp.data["sor_link"] == "https://github.com/acme/payments-api/pull/42"


# ── version history (sibling revisions) ──────────────────────────────
def test_preview_versions_lists_sibling_revisions(client, project, member):
    store = s3_from_settings()
    ids = []
    for v in (1, 2, 3):
        key = f"test-preview/{project.tenant_id}/{project.id}/prd-v{v}.md"
        store.put(key, f"v{v} body")
        art = Artifact.objects.create(
            tenant=project.tenant, project=project, phase="prd", type="prd",
            sor="internal", status="draft", s3_key=key, version=v,
        )
        ids.append(str(art.id))
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(ids[-1]))
    assert resp.status_code == 200
    versions = resp.data["versions"]
    assert len(versions) == 3
    assert {v["artifact_id"] for v in versions} == set(ids)
    # newest-first
    assert versions[0]["created_at"] >= versions[-1]["created_at"]


# ── access control ────────────────────────────────────────────────────
def test_preview_unauthenticated_is_403(client, project):
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="prd", type="prd",
        sor="internal", status="draft", s3_key="", version=1,
    )
    assert client.get(_preview_url(artifact.id)).status_code == 403


def test_artifact_list_payload_carries_no_body(client, project, member):
    store = s3_from_settings()
    key = f"test-preview/{project.tenant_id}/{project.id}/list-check.md"
    store.put(key, "body should never leak into the list")
    Artifact.objects.create(
        tenant=project.tenant, project=project, phase="prd", type="prd",
        sor="internal", status="draft", s3_key=key, version=1,
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_list_url())
    assert resp.status_code == 200
    for row in resp.data:
        assert "body" not in row
        assert "versions" not in row
        assert "sor_link" not in row


def test_preview_is_tenant_isolated(client, db):
    t1 = Tenant.objects.create(name="Acme")
    t2 = Tenant.objects.create(name="Globex")
    p1 = Project.objects.create(tenant=t1, name="P1")
    p2 = Project.objects.create(tenant=t2, name="P2")
    u2 = User.objects.create_user(email="dev@globex.com", name="Dev2", tenant=t2, password="pw!")
    Membership.objects.create(tenant=t2, user=u2, project=p2, role="engineer")
    artifact = Artifact.objects.create(
        tenant=t1, project=p1, phase="prd", type="prd",
        sor="internal", status="draft", s3_key="", version=1,
    )

    c = APIClient()
    _login(c, "dev@globex.com", "pw!")
    resp = c.get(_preview_url(artifact.id))
    assert resp.status_code == 404  # cross-tenant artifact is invisible under this session
