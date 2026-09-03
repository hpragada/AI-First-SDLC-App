"""P3-09bX-1 — per-project CI ingest tokens: issue/authenticate/revoke + admin API.

The token authenticates the client's CI when it posts JUnit results (P3-09bX-3). Only the hash is
stored; the secret is shown once. Scoped to (tenant, project) so a token can't cross either.
"""
import pytest
from rest_framework.test import APIClient

from apps.projects.ci_tokens import (
    authenticate_ci_token,
    issue_ci_token,
    list_ci_tokens,
    revoke_ci_token,
)
from apps.projects.models import Project, ProjectCIToken
from apps.tenancy.models import Tenant, User


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    admin = User.objects.create_user(email="boss@acme.com", name="Boss", tenant=t,
                                     password="admin-pass!", is_tenant_admin=True)
    member = User.objects.create_user(email="dev@acme.com", name="Dev", tenant=t,
                                      password="dev-pass!")
    return {"t": t, "p": p, "admin": admin, "member": member}


def _login(client, email, password):
    assert client.post("/api/auth/login/", {"email": email, "password": password},
                       format="json").status_code == 200


# ── token lifecycle (unit) ──────────────────────────────────────────
def test_issue_then_authenticate_roundtrip(world):
    row, token = issue_ci_token(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                                label="GitHub Actions")
    # The secret is never stored — only its hash.
    assert row.token_hash and row.token_hash != token
    resolved = authenticate_ci_token(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                                     token=token)
    assert resolved is not None and resolved.id == row.id
    assert resolved.last_used_at is not None        # touched on auth


def test_wrong_token_and_revoked_do_not_authenticate(world):
    _, token = issue_ci_token(tenant_id=str(world["t"].id), project_id=str(world["p"].id))
    assert authenticate_ci_token(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                                 token="not-the-token") is None

    revoke_ci_token(tenant_id=str(world["t"].id),
                    token_id=str(list_ci_tokens(tenant_id=str(world["t"].id),
                                                project_id=str(world["p"].id))[0].id))
    assert authenticate_ci_token(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                                 token=token) is None


def test_token_cannot_cross_project_or_tenant(world):
    other_p = Project.objects.create(tenant=world["t"], name="Other")
    other_t = Tenant.objects.create(name="Globex")
    _, token = issue_ci_token(tenant_id=str(world["t"].id), project_id=str(world["p"].id))

    assert authenticate_ci_token(tenant_id=str(world["t"].id), project_id=str(other_p.id),
                                 token=token) is None        # project A's token, project B
    assert authenticate_ci_token(tenant_id=str(other_t.id), project_id=str(world["p"].id),
                                 token=token) is None        # tenant A's token, tenant B


# ── admin management API ────────────────────────────────────────────
def _url(p, suffix=""):
    return f"/api/projects/{p.id}/ci-tokens/{suffix}"


def test_admin_issues_a_token_shown_once(client, world):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.post(_url(world["p"]), {"label": "CI"}, format="json")
    assert resp.status_code == 201
    body = resp.json()
    assert body["token"]                     # raw secret returned ONCE
    assert "token_hash" not in body          # never the hash
    # and it actually authenticates.
    assert authenticate_ci_token(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                                 token=body["token"]) is not None


def test_list_returns_metadata_without_the_secret(client, world):
    issue_ci_token(tenant_id=str(world["t"].id), project_id=str(world["p"].id), label="CI")
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.get(_url(world["p"]))
    assert resp.status_code == 200
    row = resp.json()[0]
    assert row["label"] == "CI" and "token" not in row and "token_hash" not in row


def test_non_admin_cannot_manage_tokens(client, world):
    _login(client, "dev@acme.com", "dev-pass!")
    assert client.get(_url(world["p"])).status_code == 403
    assert client.post(_url(world["p"]), {"label": "x"}, format="json").status_code == 403


def test_revoke_stops_authentication(client, world):
    row, token = issue_ci_token(tenant_id=str(world["t"].id), project_id=str(world["p"].id))
    _login(client, "boss@acme.com", "admin-pass!")
    assert client.delete(_url(world["p"], f"{row.id}/")).status_code == 204
    assert authenticate_ci_token(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                                 token=token) is None
    assert ProjectCIToken.objects.get(id=row.id).status == ProjectCIToken.Status.REVOKED
