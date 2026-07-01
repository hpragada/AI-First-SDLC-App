"""P4.7-T6 — integrations management REST + secret store (J9, DECISION-4).

Admin CRUD over IntegrationConnection per capability, with a write-only secret store:
POST/PATCH accept `secrets`, no response ever echoes them back (`configured: bool` only).
`test-connection` checks the chosen vendor is wired + configured and flips `health`.
"""
import pytest
from rest_framework.test import APIClient

from apps.integrations.crypto import decrypt_secrets
from apps.integrations.models import IntegrationConnection
from apps.tenancy.models import Tenant, User


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


@pytest.fixture
def admin(tenant):
    return User.objects.create_user(
        email="boss@acme.com", name="Boss", tenant=tenant,
        password="admin-pass!", is_tenant_admin=True,
    )


@pytest.fixture
def member(tenant):
    return User.objects.create_user(
        email="dev@acme.com", name="Dev", tenant=tenant, password="dev-pass!"
    )


def _login(client, email, password):
    assert client.post(
        "/api/auth/login/", {"email": email, "password": password}, format="json"
    ).status_code == 200


# ── admin-only ───────────────────────────────────────────────────────
def test_non_admin_cannot_list_integrations(client, member):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get("/api/integrations/")
    assert resp.status_code == 403


def test_non_admin_cannot_create_integration(client, member):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.post(
        "/api/integrations/",
        {"capability": "docstore", "vendor": "confluence"}, format="json",
    )
    assert resp.status_code == 403


# ── create ───────────────────────────────────────────────────────────
def test_admin_creates_integration_secret_never_returned(client, admin, tenant):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.post(
        "/api/integrations/",
        {
            "capability": "docstore", "vendor": "confluence",
            "binding": {"space_key": "ENG"},
            "secrets": {"api_token": "sekret-abc"},
        },
        format="json",
    )
    assert resp.status_code == 201
    body = resp.data
    assert body["capability"] == "docstore"
    assert body["vendor"] == "confluence"
    assert body["binding"] == {"space_key": "ENG"}
    assert body["configured"] is True
    assert "secret" not in body and "secrets" not in body and "secret_encrypted" not in body

    conn = IntegrationConnection.objects.get(tenant_id=tenant.id, capability="docstore")
    assert decrypt_secrets(conn.secret_encrypted) == {"api_token": "sekret-abc"}


def test_create_unsupported_capability_400(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.post(
        "/api/integrations/",
        {"capability": "not-a-capability", "vendor": "x"}, format="json",
    )
    assert resp.status_code == 400


def test_create_duplicate_capability_409(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    payload = {"capability": "codehost", "vendor": "github", "secrets": {"token": "t"}}
    assert client.post("/api/integrations/", payload, format="json").status_code == 201
    resp = client.post("/api/integrations/", payload, format="json")
    assert resp.status_code == 409


def test_create_without_secrets_is_unconfigured(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.post(
        "/api/integrations/", {"capability": "designsource", "vendor": "figma"}, format="json"
    )
    assert resp.status_code == 201
    assert resp.data["configured"] is False


# ── list is tenant-isolated ──────────────────────────────────────────
def test_integrations_are_tenant_isolated(client, db):
    t1 = Tenant.objects.create(name="Acme")
    t2 = Tenant.objects.create(name="Globex")
    admin1 = User.objects.create_user(
        email="a1@acme.com", name="A1", tenant=t1, password="pw!", is_tenant_admin=True
    )
    User.objects.create_user(
        email="a2@globex.com", name="A2", tenant=t2, password="pw!", is_tenant_admin=True
    )
    IntegrationConnection.objects.create(tenant=t1, capability="codeintel", connector="builtin")
    IntegrationConnection.objects.create(tenant=t2, capability="codeintel", connector="builtin")

    c = APIClient()
    _login(c, admin1.email, "pw!")
    resp = c.get("/api/integrations/")
    assert resp.status_code == 200
    assert len(resp.data) == 1


# ── update ───────────────────────────────────────────────────────────
def test_patch_updates_binding_without_touching_secret(client, admin, tenant):
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/",
        {
            "capability": "tasktracker", "vendor": "jira",
            "binding": {"project_key": "OLD"}, "secrets": {"api_token": "orig-secret"},
        },
        format="json",
    )
    conn_id = create.data["id"]

    resp = client.patch(
        f"/api/integrations/{conn_id}/", {"binding": {"project_key": "NEW"}}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["binding"] == {"project_key": "NEW"}
    assert resp.data["configured"] is True

    conn = IntegrationConnection.objects.get(id=conn_id)
    assert decrypt_secrets(conn.secret_encrypted) == {"api_token": "orig-secret"}


def test_patch_replaces_secret_when_supplied(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/",
        {"capability": "testmgmt", "vendor": "xray", "secrets": {"client_secret": "old"}},
        format="json",
    )
    conn_id = create.data["id"]

    resp = client.patch(
        f"/api/integrations/{conn_id}/",
        {"secrets": {"client_secret": "new"}}, format="json",
    )
    assert resp.status_code == 200
    conn = IntegrationConnection.objects.get(id=conn_id)
    assert decrypt_secrets(conn.secret_encrypted) == {"client_secret": "new"}


# ── delete ───────────────────────────────────────────────────────────
def test_delete_integration(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/", {"capability": "codeintel", "vendor": "builtin"}, format="json"
    )
    conn_id = create.data["id"]

    resp = client.delete(f"/api/integrations/{conn_id}/")
    assert resp.status_code == 204
    assert not IntegrationConnection.objects.filter(id=conn_id).exists()


# ── test-connection ──────────────────────────────────────────────────
def test_test_connection_ok_for_builtin_no_secret_needed(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/", {"capability": "codeintel", "vendor": "builtin"}, format="json"
    )
    conn_id = create.data["id"]

    resp = client.post(f"/api/integrations/{conn_id}/test-connection/")
    assert resp.status_code == 200
    assert resp.data["ok"] is True

    conn = IntegrationConnection.objects.get(id=conn_id)
    assert conn.health == IntegrationConnection.Health.HEALTHY


def test_test_connection_fails_without_secret(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/", {"capability": "docstore", "vendor": "confluence"}, format="json"
    )
    conn_id = create.data["id"]

    resp = client.post(f"/api/integrations/{conn_id}/test-connection/")
    assert resp.status_code == 200
    assert resp.data["ok"] is False
    assert "fix_hint" in resp.data

    conn = IntegrationConnection.objects.get(id=conn_id)
    assert conn.health == IntegrationConnection.Health.DOWN


def test_test_connection_fails_for_unregistered_vendor(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/",
        {"capability": "docstore", "vendor": "notion", "secrets": {"token": "t"}},
        format="json",
    )
    conn_id = create.data["id"]

    resp = client.post(f"/api/integrations/{conn_id}/test-connection/")
    assert resp.status_code == 200
    assert resp.data["ok"] is False
    assert "no connector registered" in resp.data["detail"].lower()
