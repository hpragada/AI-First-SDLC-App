"""P4.7-T7 — repositories REST (J10): CRUD over `Repository` behind
`GET/POST/DELETE /api/projects/{id}/repositories/` (+ set-default), backing S-13.

Mutations (add/remove/set-default) require `tech_lead` or project-`admin` on the project,
or a tenant-admin fallback (`require_repo_manage_role`); reads are open to any authenticated
member. `status` mirrors the tenant's `codehost` capability (P4.7-T6) — tenant-wide, so every
row shares it.
"""
import pytest
from rest_framework.test import APIClient

from apps.integrations.crypto import encrypt_secrets
from apps.integrations.models import IntegrationConnection
from apps.projects.models import Project, Repository
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
def admin(tenant):
    return User.objects.create_user(
        email="boss@acme.com", name="Boss", tenant=tenant,
        password="admin-pass!", is_tenant_admin=True,
    )


@pytest.fixture
def tech_lead(tenant, project):
    u = User.objects.create_user(
        email="lead@acme.com", name="Lead", tenant=tenant, password="lead-pass!"
    )
    Membership.objects.create(tenant=tenant, user=u, project=project, role="tech_lead")
    return u


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


def _url(project, suffix=""):
    return f"/api/projects/{project.id}/repositories/{suffix}"


# ── list + topology ───────────────────────────────────────────────────
def test_member_can_list_repositories_and_topology(client, project, member):
    Repository.objects.create(tenant=project.tenant, project=project, name="acme/api",
                              role="backend", is_default=True)
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_url(project))
    assert resp.status_code == 200
    assert resp.data["repo_topology"] == Project.RepoTopology.SINGLE
    assert len(resp.data["repositories"]) == 1
    row = resp.data["repositories"][0]
    assert row["name"] == "acme/api" and row["is_default"] is True
    assert row["status"] == "unlinked"  # no codehost integration connected yet


def test_status_reflects_connected_codehost_capability(client, project, member):
    Repository.objects.create(tenant=project.tenant, project=project, name="acme/api")
    IntegrationConnection.objects.create(
        tenant=project.tenant, capability="codehost", connector="github",
        secret_encrypted=encrypt_secrets({"token": "gh-token"}),
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_url(project))
    assert resp.data["repositories"][0]["status"] == "connected"


def test_unauthenticated_cannot_list_repositories(client, project):
    resp = client.get(_url(project))
    assert resp.status_code == 403


# ── add ────────────────────────────────────────────────────────────────
def test_tech_lead_adds_repository_reconciles_topology(client, project, tech_lead):
    _login(client, "lead@acme.com", "lead-pass!")
    resp = client.post(
        _url(project),
        {"name": "acme/web", "role": "frontend", "base_branch": "main"}, format="json",
    )
    assert resp.status_code == 201
    assert resp.data["name"] == "acme/web" and resp.data["is_default"] is True
    project.refresh_from_db()
    assert project.repo_topology == Project.RepoTopology.SINGLE

    resp2 = client.post(
        _url(project), {"name": "acme/api", "role": "backend"}, format="json",
    )
    assert resp2.status_code == 201
    assert resp2.data["is_default"] is False  # first repo keeps the default flag
    project.refresh_from_db()
    assert project.repo_topology == Project.RepoTopology.SPLIT


def test_admin_can_add_repository(client, project, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.post(_url(project), {"name": "acme/web"}, format="json")
    assert resp.status_code == 201


def test_member_cannot_add_repository(client, project, member):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.post(_url(project), {"name": "acme/web"}, format="json")
    assert resp.status_code == 403


def test_add_duplicate_name_is_409(client, project, tech_lead):
    _login(client, "lead@acme.com", "lead-pass!")
    payload = {"name": "acme/web"}
    assert client.post(_url(project), payload, format="json").status_code == 201
    resp = client.post(_url(project), payload, format="json")
    assert resp.status_code == 409


# ── remove ───────────────────────────────────────────────────────────
def test_tech_lead_removes_repository_reconciles_topology_and_default(
    client, project, tech_lead
):
    _login(client, "lead@acme.com", "lead-pass!")
    r1 = client.post(_url(project), {"name": "acme/web"}, format="json").data
    r2 = client.post(_url(project), {"name": "acme/api"}, format="json").data
    project.refresh_from_db()
    assert project.repo_topology == Project.RepoTopology.SPLIT

    resp = client.delete(_url(project, f"{r1['id']}/"))
    assert resp.status_code == 204
    project.refresh_from_db()
    assert project.repo_topology == Project.RepoTopology.SINGLE
    # r1 was default — removing it promotes the remaining repo (r2)
    remaining = Repository.objects.get(id=r2["id"])
    assert remaining.is_default is True


def test_member_cannot_remove_repository(client, project, member):
    repo = Repository.objects.create(tenant=project.tenant, project=project, name="acme/web")
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.delete(_url(project, f"{repo.id}/"))
    assert resp.status_code == 403


def test_remove_unknown_repository_is_404(client, project, tech_lead):
    _login(client, "lead@acme.com", "lead-pass!")
    resp = client.delete(_url(project, "00000000-0000-0000-0000-000000000000/"))
    assert resp.status_code == 404


# ── set-default ────────────────────────────────────────────────────────
def test_tech_lead_sets_default_repository(client, project, tech_lead):
    _login(client, "lead@acme.com", "lead-pass!")
    r1 = client.post(_url(project), {"name": "acme/web"}, format="json").data
    r2 = client.post(_url(project), {"name": "acme/api"}, format="json").data
    assert r1["is_default"] is True and r2["is_default"] is False

    resp = client.post(_url(project, f"{r2['id']}/set-default/"))
    assert resp.status_code == 200
    by_id = {row["id"]: row for row in resp.data}
    assert by_id[r2["id"]]["is_default"] is True
    assert by_id[r1["id"]]["is_default"] is False


def test_member_cannot_set_default_repository(client, project, member):
    repo = Repository.objects.create(tenant=project.tenant, project=project, name="acme/web")
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.post(_url(project, f"{repo.id}/set-default/"))
    assert resp.status_code == 403


def test_a_refusal_says_who_can_in_words(client, project, member):
    """S.No 212: the Repositories screen puts this sentence in front of the person verbatim. It
    used to name the role by its internal key — "You need the tech_lead or admin role…"."""
    repo = Repository.objects.create(tenant=project.tenant, project=project, name="acme/web")
    _login(client, "dev@acme.com", "dev-pass!")

    resp = client.post(_url(project, f"{repo.id}/set-default/"))
    assert resp.status_code == 403
    assert resp.data["detail"] == (
        "Only a tech lead or an admin can change which repository is the default for this "
        "project.")

    for resp in (client.post(_url(project), {"name": "acme/api"}, format="json"),
                 client.delete(_url(project, f"{repo.id}/")),
                 client.patch(_url(project, f"{repo.id}/"), {"preview_url": ""},
                              format="json")):
        assert resp.status_code == 403
        assert resp.data["detail"].startswith("Only a tech lead or an admin can ")
        assert "tech_lead" not in resp.data["detail"]


def test_the_sibling_project_write_rule_speaks_the_same_way(project, member):
    """The same role rule guards cancelling a work item and editing the profile; its sentence
    carried the same internal key, so it is fixed with the class rather than left behind."""
    from rest_framework.exceptions import PermissionDenied

    from apps.tenancy.services import require_project_write_role

    with pytest.raises(PermissionDenied) as exc:
        require_project_write_role(tenant_id=str(project.tenant_id), project_id=str(project.id),
                                   user_id=member.id, what="close or cancel a work item")
    assert str(exc.value.detail) == (
        "Only a tech lead or an admin on this project can close or cancel a work item.")


# ── preview URL (P3-09bR): create + inline edit ─────────────────────────
def test_add_repository_accepts_preview_url(client, project, tech_lead):
    _login(client, "lead@acme.com", "lead-pass!")
    resp = client.post(
        _url(project),
        {"name": "acme/web", "preview_url": "http://127.0.0.1:5173"}, format="json",
    )
    assert resp.status_code == 201
    listing = client.get(_url(project)).data["repositories"]
    assert listing[0]["preview_url"] == "http://127.0.0.1:5173"


def test_tech_lead_edits_preview_url(client, project, tech_lead):
    _login(client, "lead@acme.com", "lead-pass!")
    r = client.post(_url(project), {"name": "acme/web"}, format="json").data
    assert client.get(_url(project)).data["repositories"][0]["preview_url"] == ""

    resp = client.patch(
        _url(project, f"{r['id']}/"), {"preview_url": "http://localhost:3000"}, format="json")
    assert resp.status_code == 200
    # PATCH returns the refreshed list with the new URL.
    assert resp.data[0]["preview_url"] == "http://localhost:3000"
    # And clearing it back to empty works.
    resp2 = client.patch(_url(project, f"{r['id']}/"), {"preview_url": ""}, format="json")
    assert resp2.data[0]["preview_url"] == ""


def test_member_cannot_edit_preview_url(client, project, member):
    repo = Repository.objects.create(tenant=project.tenant, project=project, name="acme/web")
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.patch(
        _url(project, f"{repo.id}/"), {"preview_url": "http://x"}, format="json")
    assert resp.status_code == 403


def test_patch_unknown_repository_is_404(client, project, tech_lead):
    _login(client, "lead@acme.com", "lead-pass!")
    resp = client.patch(
        _url(project, "00000000-0000-0000-0000-000000000000/"),
        {"preview_url": "http://x"}, format="json")
    assert resp.status_code == 404


# ── tenant isolation ────────────────────────────────────────────────────
def test_repositories_are_tenant_isolated(client, db):
    t1 = Tenant.objects.create(name="Acme")
    t2 = Tenant.objects.create(name="Globex")
    p1 = Project.objects.create(tenant=t1, name="P1")
    p2 = Project.objects.create(tenant=t2, name="P2")
    User.objects.create_user(
        email="a1@acme.com", name="A1", tenant=t1, password="pw!", is_tenant_admin=True
    )
    User.objects.create_user(
        email="a2@globex.com", name="A2", tenant=t2, password="pw!", is_tenant_admin=True
    )
    Repository.objects.create(tenant=t1, project=p1, name="acme/web")
    Repository.objects.create(tenant=t2, project=p2, name="globex/web")

    c = APIClient()
    _login(c, "a1@acme.com", "pw!")
    resp = c.get(_url(p1))
    assert resp.status_code == 200
    assert len(resp.data["repositories"]) == 1
    assert resp.data["repositories"][0]["name"] == "acme/web"

    # cross-tenant project id is invisible under this admin's session (RLS/tenant scoping)
    cross = c.get(_url(p2))
    assert cross.status_code == 404
