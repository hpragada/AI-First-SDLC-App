"""P4.7-T4 — user & role management (J6): users list, project memberships, tenant-admin
toggle + last-admin guard, gate-role coverage, and the admin-approves-any-gate rule.

The test DB connection is superuser (RLS bypassed), so the explicit `tenant_id` scoping +
the admin permission are what's under test here; RLS itself is covered by test_rls.py.
"""
import pytest
from rest_framework.test import APIClient

from apps.gates.models import Approval
from apps.gates.services import GateRoleError, decide_gate
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem


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
def admin(tenant):
    return User.objects.create_user(
        email="boss@acme.com", name="Boss", tenant=tenant,
        password="admin-pass!", is_tenant_admin=True,
    )


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


# ── GET /api/users/ ─────────────────────────────────────────────────
def test_list_users_returns_admin_flag_and_memberships(client, admin, member, project):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.get("/api/users/")
    assert resp.status_code == 200
    by_email = {u["email"]: u for u in resp.data}
    assert by_email["boss@acme.com"]["is_tenant_admin"] is True
    assert by_email["boss@acme.com"]["status"] == "active"
    dev = by_email["dev@acme.com"]
    assert dev["is_tenant_admin"] is False
    assert len(dev["memberships"]) == 1
    membership = dev["memberships"][0]
    assert membership["project_id"] == str(project.id)
    assert membership["project_name"] == project.name
    assert membership["role"] == "engineer"
    assert "id" in membership  # needed by the UI to revoke a specific grant


def test_list_users_admin_only(client, member):
    _login(client, "dev@acme.com", "dev-pass!")  # a plain member
    assert client.get("/api/users/").status_code == 403


# ── project memberships ─────────────────────────────────────────────
def test_grant_membership(client, admin, member, project):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.post(
        f"/api/projects/{project.id}/memberships/",
        {"user_id": str(member.id), "role": "reviewer"},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["role"] == "reviewer"
    assert str(resp.data["user_id"]) == str(member.id)
    assert Membership.objects.filter(user=member, project=project, role="reviewer").exists()


def test_list_memberships(client, admin, member, project):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.get(f"/api/projects/{project.id}/memberships/")
    assert resp.status_code == 200
    assert {m["role"] for m in resp.data} == {"engineer"}
    assert str(resp.data[0]["user_id"]) == str(member.id)


def test_grant_membership_duplicate_409(client, admin, member, project):
    _login(client, "boss@acme.com", "admin-pass!")
    body = {"user_id": str(member.id), "role": "engineer"}  # member already has engineer
    assert client.post(
        f"/api/projects/{project.id}/memberships/", body, format="json"
    ).status_code == 409


def test_grant_membership_unknown_user_404(client, admin, project):
    _login(client, "boss@acme.com", "admin-pass!")
    import uuid
    resp = client.post(
        f"/api/projects/{project.id}/memberships/",
        {"user_id": str(uuid.uuid4()), "role": "reviewer"},
        format="json",
    )
    assert resp.status_code == 404


def test_grant_membership_admin_only(client, member, project):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.post(
        f"/api/projects/{project.id}/memberships/",
        {"user_id": str(member.id), "role": "reviewer"},
        format="json",
    )
    assert resp.status_code == 403


def test_revoke_membership(client, admin, member, project):
    _login(client, "boss@acme.com", "admin-pass!")
    m = Membership.objects.create(
        tenant=project.tenant, user=member, project=project, role="reviewer"
    )
    assert client.delete(
        f"/api/projects/{project.id}/memberships/{m.id}/"
    ).status_code == 204
    assert not Membership.objects.filter(id=m.id).exists()


# ── tenant-admin toggle + last-admin guard ──────────────────────────
def test_set_tenant_admin_promotes(client, admin, member):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.patch(
        f"/api/users/{member.id}/", {"is_tenant_admin": True}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["is_tenant_admin"] is True
    member.refresh_from_db()
    assert member.is_tenant_admin is True


def test_last_admin_guard_blocks_demoting_sole_admin(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.patch(
        f"/api/users/{admin.id}/", {"is_tenant_admin": False}, format="json"
    )
    assert resp.status_code == 409
    admin.refresh_from_db()
    assert admin.is_tenant_admin is True  # unchanged


def test_demote_allowed_once_a_second_admin_exists(client, admin, member):
    _login(client, "boss@acme.com", "admin-pass!")
    # promote member, then the original admin can step down
    client.patch(f"/api/users/{member.id}/", {"is_tenant_admin": True}, format="json")
    resp = client.patch(
        f"/api/users/{admin.id}/", {"is_tenant_admin": False}, format="json"
    )
    assert resp.status_code == 200
    admin.refresh_from_db()
    assert admin.is_tenant_admin is False


# ── role coverage (S-08) ────────────────────────────────────────────
def test_role_coverage_hard_block_when_no_holder_and_no_admin(client, admin, member, project):
    """A tenant/project with no admin fallback: an uncovered gate role is truly blocked.
    (Use a separate admin-less tenant so no tenant-admin fallback exists.)"""
    plain = Tenant.objects.create(name="NoAdminCo")
    proj = Project.objects.create(tenant=plain, name="Solo")
    dev = User.objects.create_user(
        email="solo@noadmin.com", name="Solo", tenant=plain, password="pw"
    )
    Membership.objects.create(tenant=plain, user=dev, project=proj, role="product_owner")
    # No tenant-admin and no project-admin exist for `plain`, so there is no fallback. Assert
    # on the service directly to isolate the no-fallback case.
    from apps.tenancy.services import project_role_coverage
    cov = project_role_coverage(tenant=plain, project=proj)
    assert cov["admin_fallback"] is False
    by_role = {r["role"]: r for r in cov["roles"]}
    assert by_role["product_owner"]["covered"] is True
    assert by_role["product_owner"]["gate_blocked"] is False
    rev = by_role["reviewer"]
    assert rev["covered"] is False
    assert rev["gate_blocked"] is True
    # The human-readable role label, never the raw key — coverage notes used to leak
    # "reviewer" into copy the user reads (Bugs.xlsx). This asserts the fixed behaviour.
    assert rev["note"] == "merge gate unactionable — no Reviewer"


def test_role_coverage_admin_fallback_softens_gap(client, admin, project):
    """When a tenant-admin (or project-admin) exists, an uncovered gate role is NOT blocked —
    an admin can approve any gate — and the note reflects the fallback."""
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.get(f"/api/projects/{project.id}/role-coverage/")
    assert resp.status_code == 200
    assert resp.data["admin_fallback"] is True  # `admin` is a tenant-admin
    rev = {r["role"]: r for r in resp.data["roles"]}["reviewer"]
    assert rev["covered"] is False
    assert rev["gate_blocked"] is False
    assert "admin can approve" in rev["note"]


def test_role_coverage_admin_only(client, member, project):
    _login(client, "dev@acme.com", "dev-pass!")
    assert client.get(f"/api/projects/{project.id}/role-coverage/").status_code == 403


# ── admin approves any gate (gates.services.decide_gate) ────────────
@pytest.fixture
def gate(tenant, project):
    wi = WorkItem.objects.create(tenant=tenant, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=tenant, key="08_code_review", body_ref="x")
    run = Run.objects.create(
        tenant=tenant, work_item=wi, agent_spec=spec, temporal_workflow_id="wf-x"
    )
    return Approval.objects.create(
        tenant=tenant, run=run, work_item=wi, required_role="reviewer",
        decision=Approval.Decision.PENDING,
    )


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, workflow_id, decision, approver_id, comment, revise=False):
        self.calls.append((workflow_id, decision, approver_id, comment))


def test_tenant_admin_can_approve_any_gate(tenant, project, admin, gate):
    """`admin` holds no reviewer membership, but is a tenant-admin → may approve the merge gate."""
    sender = _Recorder()
    result = decide_gate(
        tenant_id=str(tenant.id), approval_id=str(gate.id), user_id=str(admin.id),
        decision="approved", signal_sender=sender,
    )
    assert result["decision"] == "approved"
    assert sender.calls and sender.calls[0][1] == "approved"


def test_project_admin_can_approve_any_gate(tenant, project, gate):
    """A Membership(role="admin") on the project can approve a gate for any other role."""
    padmin = User.objects.create_user(
        email="padmin@acme.com", name="PAdmin", tenant=tenant, password="pw"
    )
    Membership.objects.create(tenant=tenant, user=padmin, project=project, role="admin")
    result = decide_gate(
        tenant_id=str(tenant.id), approval_id=str(gate.id), user_id=str(padmin.id),
        decision="approved", signal_sender=_Recorder(),
    )
    assert result["decision"] == "approved"


def test_non_admin_without_role_still_blocked(tenant, project, member, gate):
    """The bypass is admin-only: a plain engineer still can't approve a reviewer gate."""
    with pytest.raises(GateRoleError):
        decide_gate(
            tenant_id=str(tenant.id), approval_id=str(gate.id), user_id=str(member.id),
            decision="approved", signal_sender=_Recorder(),
        )
