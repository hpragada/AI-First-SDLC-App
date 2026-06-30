"""P4.7-T1 — server-session auth (login / logout / me) + tenant-from-user.

Exercises the HTTP layer with a real Django session. The test DB connection is
superuser (RLS bypassed), so the explicit `tenant_id` scoping is what's under test
here; RLS itself is covered by test_rls.py.
"""
import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.tenancy.models import Membership, Tenant, User


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


@pytest.fixture
def project(tenant):
    return Project.objects.create(tenant=tenant, name="Payment Gateway v2")


@pytest.fixture
def user(tenant, project):
    u = User.objects.create_user(
        email="sarah@acme.com", name="Sarah Chen", tenant=tenant, password="s3cret-pass!"
    )
    Membership.objects.create(
        tenant=tenant, user=u, project=project, role="product_owner"
    )
    return u


# ── login / me / logout round-trip ──────────────────────────────────
def test_login_success_returns_me_shape(client, user, project):
    resp = client.post(
        "/api/auth/login/",
        {"email": "sarah@acme.com", "password": "s3cret-pass!"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["user"]["email"] == "sarah@acme.com"
    assert resp.data["user"]["name"] == "Sarah Chen"
    assert resp.data["user"]["is_tenant_admin"] is False  # flag arrives in T2
    assert resp.data["tenant"]["name"] == "Acme"
    assert resp.data["memberships"] == [
        {
            "project_id": str(project.id),
            "project_name": "Payment Gateway v2",
            "role": "product_owner",
        }
    ]


def test_login_invalid_credentials(client, user):
    resp = client.post(
        "/api/auth/login/",
        {"email": "sarah@acme.com", "password": "wrong"},
        format="json",
    )
    assert resp.status_code == 401


def test_login_validation_error(client, db):
    resp = client.post("/api/auth/login/", {"email": "not-an-email"}, format="json")
    assert resp.status_code == 400


def test_me_unauthenticated_401(client, db):
    assert client.get("/api/auth/me/").status_code == 401


def test_me_after_login(client, user):
    client.post(
        "/api/auth/login/",
        {"email": "sarah@acme.com", "password": "s3cret-pass!"},
        format="json",
    )
    me = client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.data["user"]["email"] == "sarah@acme.com"


def test_logout_clears_session(client, user):
    client.post(
        "/api/auth/login/",
        {"email": "sarah@acme.com", "password": "s3cret-pass!"},
        format="json",
    )
    assert client.get("/api/auth/me/").status_code == 200
    assert client.post("/api/auth/logout/").status_code == 204
    assert client.get("/api/auth/me/").status_code == 401


# ── tenant is derived from the user, not the header ─────────────────
def test_tenant_scoping_comes_from_the_session_user(client, user, project):
    """An authenticated request with NO X-Tenant-ID still scopes to the user's tenant,
    and never leaks another tenant's rows."""
    other = Tenant.objects.create(name="Globex")
    Project.objects.create(tenant=other, name="Other Co Project")

    client.post(
        "/api/auth/login/",
        {"email": "sarah@acme.com", "password": "s3cret-pass!"},
        format="json",
    )
    resp = client.get("/api/projects/")  # no X-Tenant-ID header
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.data]
    assert ids == [str(project.id)]  # only the user's tenant's project


def test_header_fallback_preserved_without_session(client, tenant, project):
    """Pre-auth / runner path: no session → X-Tenant-ID still scopes existing endpoints."""
    resp = client.get("/api/projects/", HTTP_X_TENANT_ID=str(tenant.id))
    assert resp.status_code == 200
    assert [p["id"] for p in resp.data] == [str(project.id)]


# ── CSRF: app endpoints are protected once session-authenticated ────
def test_session_authed_post_requires_csrf(user, project):
    """After login the SPA must send X-CSRFToken on unsafe requests (login/logout are
    exempt; real app POSTs are not). /me issues the csrftoken cookie."""
    client = APIClient(enforce_csrf_checks=True)
    assert client.post(
        "/api/auth/login/",
        {"email": "sarah@acme.com", "password": "s3cret-pass!"},
        format="json",
    ).status_code == 200  # login is CSRF-exempt

    client.get("/api/auth/me/")  # sets the csrftoken cookie
    token = client.cookies["csrftoken"].value

    # A session-authed create without the token is rejected…
    no_token = client.post(
        "/api/work-items/",
        {"project": str(project.id), "type": "epic"},
        format="json",
    )
    assert no_token.status_code == 403
    # …and accepted with it.
    with_token = client.post(
        "/api/work-items/",
        {"project": str(project.id), "type": "epic"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert with_token.status_code == 201
