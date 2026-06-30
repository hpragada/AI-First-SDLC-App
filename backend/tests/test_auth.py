"""P4.7-T1 — server-session auth (login / logout / me) + tenant-from-user.

Exercises the HTTP layer with a real Django session. The test DB connection is
superuser (RLS bypassed), so the explicit `tenant_id` scoping is what's under test
here; RLS itself is covered by test_rls.py.
"""
import pytest
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from apps.projects.models import Project
from apps.tenancy.auth import IsTenantAdmin
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


# ── P4.7-T2: self-serve signup → new tenant + first admin ───────────
def test_signup_creates_tenant_admin_and_session(client, db):
    resp = client.post(
        "/api/auth/signup/",
        {
            "name": "Sarah Chen",
            "email": "founder@newco.com",
            "password": "s3cret-pass!",
            "org_name": "NewCo",
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["user"]["is_tenant_admin"] is True
    assert resp.data["tenant"]["name"] == "NewCo"
    # tenant + admin persisted
    user = User.objects.get(email="founder@newco.com")
    assert user.is_tenant_admin is True
    assert user.tenant.name == "NewCo"
    # session is live (me round-trips)
    me = client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.data["user"]["is_tenant_admin"] is True


def test_signup_duplicate_email_rejected(client, user):
    resp = client.post(
        "/api/auth/signup/",
        {
            "name": "Imposter",
            "email": "sarah@acme.com",  # already exists (fixture)
            "password": "another-pass!",
            "org_name": "Imposter Inc",
        },
        format="json",
    )
    assert resp.status_code == 409
    # no second tenant created
    assert not Tenant.objects.filter(name="Imposter Inc").exists()


class _AdminOnlyView(APIView):
    permission_classes = [IsTenantAdmin]

    def get(self, request):
        return Response({"ok": True})


def test_is_tenant_admin_permission_gates_admin_endpoints(user, tenant):
    """The is_tenant_admin flag is the gate for admin endpoints: a non-admin gets 403,
    a tenant-admin passes."""
    factory = APIRequestFactory()
    view = _AdminOnlyView.as_view()

    # the fixture user is a normal member → 403
    req = factory.get("/admin-only")
    force_authenticate(req, user=user)
    assert view(req).status_code == 403

    admin = User.objects.create_user(
        email="admin@acme.com", name="Admin", tenant=tenant,
        password="p4ssw0rd!", is_tenant_admin=True,
    )
    req2 = factory.get("/admin-only")
    force_authenticate(req2, user=admin)
    assert view(req2).status_code == 200
