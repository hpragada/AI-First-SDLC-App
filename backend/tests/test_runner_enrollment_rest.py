"""P4.7-T11 — companion status + connect surface REST (J5): `GET /api/runners/` returns the
*session user's* enrollments grouped by machine with `online` derived from `last_seen`, backing
S-05 (setup checklist tick) / S-06 (connect-machine). `POST /api/runners/` (enroll) now binds
`developer_id` to the authenticated session user — the body value is only the pre-auth/runner
fallback (mirrors `resolve_actor`, P4.7-T5).
"""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.runs.models import RunnerEnrollment
from apps.tenancy.models import Membership, Tenant, User


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
def project2(tenant):
    return Project.objects.create(tenant=tenant, name="Ledger")


@pytest.fixture
def dev(tenant, project, project2):
    u = User.objects.create_user(
        email="dev@acme.com", name="Dev", tenant=tenant, password="dev-pass!"
    )
    Membership.objects.create(tenant=tenant, user=u, project=project, role="engineer")
    Membership.objects.create(tenant=tenant, user=u, project=project2, role="engineer")
    return u


@pytest.fixture
def other_dev(tenant, project):
    u = User.objects.create_user(
        email="other@acme.com", name="Other", tenant=tenant, password="other-pass!"
    )
    Membership.objects.create(tenant=tenant, user=u, project=project, role="engineer")
    return u


def _login(client, email, password):
    assert client.post(
        "/api/auth/login/", {"email": email, "password": password}, format="json"
    ).status_code == 200


def _enroll(client, tenant, project, label="", **extra):
    return client.post(
        "/api/runners/", {"project_id": str(project.id), "label": label, **extra},
        format="json", HTTP_X_TENANT_ID=str(tenant.id),
    )


def test_get_requires_authentication(client, tenant):
    resp = client.get("/api/runners/", HTTP_X_TENANT_ID=str(tenant.id))
    assert resp.status_code == 403


def test_post_binds_developer_id_to_session_user(client, tenant, project, dev):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = _enroll(client, tenant, project, label="Sarah's MacBook", developer_id="bogus")
    assert resp.status_code == 201
    enrollment = RunnerEnrollment.objects.get(id=resp.data["id"])
    assert str(enrollment.developer_id) == str(dev.id)


def test_post_without_session_falls_back_to_body_developer_id(client, tenant, project, dev):
    """The CLI onboarding path: `python -m runner.companion enroll` (runner/README.md, Quick
    start step 1) sends an X-Tenant-ID header and a `developer_id` body param with no session,
    because it has no session to send.

    S.No 214 closed eight other anonymous writes and deliberately left this one open - see
    `RunnerEnrollmentView.get_permissions`. It is a real gap, and it is recorded against S.No 35
    with the rest of the Connect Machine credential model rather than half-closed here in a way
    that breaks the documented flow without fixing the model."""
    resp = _enroll(client, tenant, project, label="l", developer_id=str(dev.id))
    assert resp.status_code == 201
    enrollment = RunnerEnrollment.objects.get(id=resp.data["id"])
    assert str(enrollment.developer_id) == str(dev.id)


def test_post_binds_the_enrollment_to_the_signed_in_developer(client, tenant, project, dev):
    """The replacement for what the test above used to cover: the enrollment is owned by whoever
    is signed in, which is what made the body parameter unnecessary in the first place."""
    _login(client, "dev@acme.com", "dev-pass!")
    resp = _enroll(client, tenant, project, label="l")
    assert resp.status_code == 201
    assert str(RunnerEnrollment.objects.get(id=resp.data["id"]).developer_id) == str(dev.id)


def test_get_groups_enrollments_by_machine_across_projects(
    client, tenant, project, project2, dev
):
    _login(client, "dev@acme.com", "dev-pass!")
    assert _enroll(client, tenant, project, label="Sarah's MacBook").status_code == 201
    assert _enroll(client, tenant, project2, label="Sarah's MacBook").status_code == 201

    resp = client.get("/api/runners/", HTTP_X_TENANT_ID=str(tenant.id))
    assert resp.status_code == 200
    assert len(resp.data) == 1
    machine = resp.data[0]
    assert machine["machine"] == "Sarah's MacBook"
    assert {p["project_id"] for p in machine["projects"]} == {str(project.id), str(project2.id)}
    assert {p["project_name"] for p in machine["projects"]} == {"Payments", "Ledger"}


def test_get_collapses_labelless_reenrollments_for_same_project(client, tenant, project, dev):
    """RC-4: generating a fresh token (no machine label — the web-app default) for the same
    project must not spawn a new phantom 'machine' card each time. They collapse into one,
    represented by the most-recently-seen enrollment, so the card reflects the live daemon."""
    _login(client, "dev@acme.com", "dev-pass!")
    first = _enroll(client, tenant, project)    # no label
    second = _enroll(client, tenant, project)   # re-enroll for the same project, still no label
    assert first.status_code == 201 and second.status_code == 201
    RunnerEnrollment.objects.filter(id=first.data["id"]).update(
        last_seen=timezone.now() - timedelta(minutes=10))
    RunnerEnrollment.objects.filter(id=second.data["id"]).update(last_seen=timezone.now())

    resp = client.get("/api/runners/", HTTP_X_TENANT_ID=str(tenant.id))
    assert resp.status_code == 200
    assert len(resp.data) == 1                                    # one card, not two phantoms
    card = resp.data[0]
    assert card["online"] is True                                # freshest enrollment wins
    assert card["id"] == second.data["id"]                       # representative = most recent
    assert [p["project_id"] for p in card["projects"]] == [str(project.id)]  # project not duped


def test_get_online_derived_from_last_seen(client, tenant, project, dev):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = _enroll(client, tenant, project, label="Sarah's MacBook")
    RunnerEnrollment.objects.filter(id=resp.data["id"]).update(last_seen=timezone.now())

    listing = client.get("/api/runners/", HTTP_X_TENANT_ID=str(tenant.id))
    assert listing.data[0]["online"] is True

    RunnerEnrollment.objects.filter(id=resp.data["id"]).update(
        last_seen=timezone.now() - timedelta(minutes=10)
    )
    stale = client.get("/api/runners/", HTTP_X_TENANT_ID=str(tenant.id))
    assert stale.data[0]["online"] is False


def test_get_never_seen_is_offline_with_no_last_seen(client, tenant, project, dev):
    _login(client, "dev@acme.com", "dev-pass!")
    _enroll(client, tenant, project, label="Sarah's MacBook")
    resp = client.get("/api/runners/", HTTP_X_TENANT_ID=str(tenant.id))
    assert resp.data[0]["online"] is False
    assert resp.data[0]["last_seen"] is None


def test_get_excludes_other_developers_enrollments(client, tenant, project, dev, other_dev):
    _login(client, "other@acme.com", "other-pass!")
    _enroll(client, tenant, project, label="Other's laptop")

    c2 = APIClient()
    _login(c2, "dev@acme.com", "dev-pass!")
    resp = c2.get("/api/runners/", HTTP_X_TENANT_ID=str(tenant.id))
    assert resp.data == []


def test_get_excludes_revoked_enrollments(client, tenant, project, dev):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = _enroll(client, tenant, project, label="Sarah's MacBook")
    enrollment_id = resp.data["id"]

    assert client.post(f"/api/runners/{enrollment_id}/revoke/",
                       HTTP_X_TENANT_ID=str(tenant.id)).status_code == 200
    listing = client.get("/api/runners/", HTTP_X_TENANT_ID=str(tenant.id))
    assert listing.data == []


def test_get_is_tenant_isolated(client, db):
    t1 = Tenant.objects.create(name="Acme")
    t2 = Tenant.objects.create(name="Globex")
    p1 = Project.objects.create(tenant=t1, name="P1")
    p2 = Project.objects.create(tenant=t2, name="P2")
    u1 = User.objects.create_user(email="a@acme.com", name="A", tenant=t1, password="pw!")
    Membership.objects.create(tenant=t1, user=u1, project=p1, role="engineer")
    u2 = User.objects.create_user(email="b@globex.com", name="B", tenant=t2, password="pw!")
    Membership.objects.create(tenant=t2, user=u2, project=p2, role="engineer")

    c1 = APIClient()
    _login(c1, "a@acme.com", "pw!")
    assert _enroll(c1, t1, p1, label="A's machine").status_code == 201

    # A different tenant's session user sees none of tenant 1's enrollments — the session
    # binds the tenant server-side (TenantContextMiddleware), not the request header.
    c2 = APIClient()
    _login(c2, "b@globex.com", "pw!")
    resp = c2.get("/api/runners/", HTTP_X_TENANT_ID=str(t1.id))
    assert resp.status_code == 200
    assert resp.data == []
