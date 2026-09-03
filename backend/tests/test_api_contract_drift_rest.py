"""P4.7-T9 — API-contract & drift REST (J18): wraps the Phase-4 services behind
`/api/projects/{id}/{api-contracts,drift}/` + `/api/drift/{id}/decide/`, backing S-27.

Read endpoints reshape the existing services (`list_api_contracts`/`read_api_contract_body`/
`drift_queue`) to the wire contract; `decide` reuses `decide_drift` verbatim (role check +
idempotent-once-decided already live there).
"""
import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project, Repository
from apps.registry.models import Artifact
from apps.tenancy.models import Membership, Tenant, User
from integrations.api_contract import export_api_contract, record_implements
from integrations.drift import detect_contract_drift, detect_pointer_hash_drift


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


@pytest.fixture
def project(tenant):
    return Project.objects.create(tenant=tenant, name="Payments",
                                  repo_topology=Project.RepoTopology.SPLIT)


@pytest.fixture
def provider_repo(project):
    return Repository.objects.create(tenant=project.tenant, project=project,
                                     name="acme/payments-api", role="backend")


@pytest.fixture
def consumer_repo(project):
    return Repository.objects.create(tenant=project.tenant, project=project,
                                     name="acme/payments-web", role="frontend")


@pytest.fixture
def architect(tenant, project):
    u = User.objects.create_user(
        email="arch@acme.com", name="Architect", tenant=tenant, password="arch-pass!"
    )
    Membership.objects.create(tenant=tenant, user=u, project=project, role="architect")
    return u


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


def _contracts_url(project):
    return f"/api/projects/{project.id}/api-contracts/"


def _drift_url(project):
    return f"/api/projects/{project.id}/drift/"


def _decide_url(drift_id):
    return f"/api/drift/{drift_id}/decide/"


# ── api-contracts ────────────────────────────────────────────────────
def test_api_contracts_list_empty_when_none_registered(client, project, member):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_contracts_url(project))
    assert resp.status_code == 200
    assert resp.data == []


def test_api_contracts_list_and_detail_read_through(client, project, provider_repo, member):
    out = export_api_contract(
        tenant_id=str(project.tenant_id), project_id=str(project.id),
        body="# Payments API\nGET /charges", change="minor",
        provider_repo_id=str(provider_repo.id), target="Payments API",
    )
    _login(client, "dev@acme.com", "dev-pass!")

    listing = client.get(_contracts_url(project))
    assert listing.status_code == 200
    assert len(listing.data) == 1
    row = listing.data[0]
    assert row["artifact_id"] == out["artifact_id"]
    assert row["name"] == "Payments API"
    assert row["version"] == 1 and row["semver"] == "1.0.0"
    assert row["provider_repo"] == "acme/payments-api"
    assert row["status"] == "draft"

    detail = client.get(f"{_contracts_url(project)}{out['artifact_id']}/")
    assert detail.status_code == 200
    assert detail.data["body"] == "# Payments API\nGET /charges"
    assert detail.data["semver"] == "1.0.0"


def test_api_contract_detail_unknown_id_is_404(client, project, member):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(
        f"{_contracts_url(project)}00000000-0000-0000-0000-000000000000/"
    )
    assert resp.status_code == 404


def test_api_contracts_unauthenticated_is_403(client, project):
    assert client.get(_contracts_url(project)).status_code == 403


# ── drift queue ──────────────────────────────────────────────────────
def test_drift_queue_shows_open_record_with_cross_repo_impact(
    client, project, provider_repo, consumer_repo, member
):
    contract = export_api_contract(
        tenant_id=str(project.tenant_id), project_id=str(project.id),
        body="v1", provider_repo_id=str(provider_repo.id),
    )
    consumer_artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, repo=consumer_repo,
        phase="implementation", type="code", sor="git", status="published",
    )
    record_implements(
        tenant_id=str(project.tenant_id), from_artifact_id=str(consumer_artifact.id),
        contract_artifact_id=contract["artifact_id"],
    )
    detect_contract_drift(
        tenant_id=str(project.tenant_id), contract_artifact_id=contract["artifact_id"],
        new_semver="2.0.0", source="test",
    )

    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_drift_url(project))
    assert resp.status_code == 200
    assert len(resp.data) == 1
    rec = resp.data[0]
    assert rec["kind"] == "contract" and rec["required_role"] == "architect"
    assert len(rec["impacted"]) == 1
    assert rec["impacted"][0]["node"] == str(consumer_artifact.id)
    assert rec["impacted"][0]["repo_id"] == str(consumer_repo.id)


def test_drift_queue_empty_when_nothing_open(client, project, member):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_drift_url(project))
    assert resp.status_code == 200
    assert resp.data == []


# ── decide drift ─────────────────────────────────────────────────────
def test_architect_accepts_contract_drift(client, project, provider_repo, architect):
    contract = export_api_contract(
        tenant_id=str(project.tenant_id), project_id=str(project.id),
        body="v1", provider_repo_id=str(provider_repo.id),
    )
    result = detect_contract_drift(
        tenant_id=str(project.tenant_id), contract_artifact_id=contract["artifact_id"],
        new_semver="2.0.0",
    )
    _login(client, "arch@acme.com", "arch-pass!")
    resp = client.post(_decide_url(result["drift_id"]), {"decision": "accept"}, format="json")
    assert resp.status_code == 200
    assert resp.data["status"] == "accepted"


def test_tech_lead_accepts_pointer_hash_drift_and_reconciles(
    client, project, provider_repo, tech_lead
):
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, repo=provider_repo,
        phase="onboarding", type="document", sor="confluence", status="published",
        content_hash="old-hash",
    )
    result = detect_pointer_hash_drift(
        tenant_id=str(project.tenant_id), artifact_id=str(artifact.id),
        observed_hash="new-hash",
    )
    _login(client, "lead@acme.com", "lead-pass!")
    resp = client.post(_decide_url(result["drift_id"]), {"decision": "accept"}, format="json")
    assert resp.status_code == 200
    assert resp.data["status"] == "accepted"
    artifact.refresh_from_db()
    assert artifact.content_hash == "new-hash"   # reconciled — the observed hash is adopted


def test_wrong_role_cannot_decide_contract_drift(client, project, provider_repo, member):
    contract = export_api_contract(
        tenant_id=str(project.tenant_id), project_id=str(project.id),
        body="v1", provider_repo_id=str(provider_repo.id),
    )
    result = detect_contract_drift(
        tenant_id=str(project.tenant_id), contract_artifact_id=contract["artifact_id"],
        new_semver="2.0.0",
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.post(_decide_url(result["drift_id"]), {"decision": "reject"}, format="json")
    assert resp.status_code == 403


def test_decide_is_idempotent_once_decided(client, project, provider_repo, architect):
    contract = export_api_contract(
        tenant_id=str(project.tenant_id), project_id=str(project.id),
        body="v1", provider_repo_id=str(provider_repo.id),
    )
    result = detect_contract_drift(
        tenant_id=str(project.tenant_id), contract_artifact_id=contract["artifact_id"],
        new_semver="2.0.0",
    )
    _login(client, "arch@acme.com", "arch-pass!")
    first = client.post(_decide_url(result["drift_id"]), {"decision": "reject"}, format="json")
    assert first.status_code == 200 and first.data["status"] == "rejected"

    second = client.post(_decide_url(result["drift_id"]), {"decision": "accept"}, format="json")
    assert second.status_code == 200
    assert second.data["status"] == "rejected"   # unchanged — first decision stands
    assert second.data.get("idempotent") is True


# ── tenant isolation ─────────────────────────────────────────────────
def test_api_contracts_and_drift_are_tenant_isolated(client, db):
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
    export_api_contract(tenant_id=str(t1.id), project_id=str(p1.id), body="v1")

    c = APIClient()
    _login(c, "a1@acme.com", "pw!")
    resp = c.get(_contracts_url(p1))
    assert resp.status_code == 200 and len(resp.data) == 1
    # cross-tenant project id is invisible under this admin's session (RLS/tenant scoping)
    assert c.get(_contracts_url(p2)).status_code == 404
