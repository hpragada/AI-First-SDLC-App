"""P4.7-T8 — brownfield onboarding REST (J17): wraps the existing onboarding services behind
`/api/projects/{id}/{onboarding,code-intel,gap-report}/`, backing S-24/S-25/S-26.

`code-intel` persists an **already-computed** analysis result (real companion-side dispatch is
deferred — see PHASE_4.7_BUILD_SPEC.md T8 notes) as a `codebase_intelligence` artifact +
Knowledge-Index chunk; `gap-report` POST (re)builds via `build_gap_report`, GET reads through the
latest one without recomputing; `onboarding` is the hub-state rollup.
"""
import pytest
from rest_framework.test import APIClient

from apps.integrations.models import SourceDocument
from apps.knowledge.models import KnowledgeChunk
from apps.projects.models import Project, Repository
from apps.registry.models import Artifact
from apps.tenancy.models import Membership, Tenant, User


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


@pytest.fixture
def project(tenant):
    return Project.objects.create(tenant=tenant, name="Legacy Billing",
                                  track=Project.Track.BROWNFIELD)


@pytest.fixture
def repo(project):
    return Repository.objects.create(tenant=project.tenant, project=project, name="acme/legacy")


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


def _hub_url(project):
    return f"/api/projects/{project.id}/onboarding/"


def _ci_url(project):
    return f"/api/projects/{project.id}/code-intel/"


def _gap_url(project):
    return f"/api/projects/{project.id}/gap-report/"


def _publish(project, type_):
    Artifact.objects.create(tenant=project.tenant, project=project, phase="onboarding",
                            type=type_, sor="internal", status="published")


# ── code-intel ──────────────────────────────────────────────────────
def test_tech_lead_indexes_code_creates_artifact_and_knowledge_chunk(client, project, repo,
                                                                     tech_lead):
    _login(client, "lead@acme.com", "lead-pass!")
    resp = client.post(
        _ci_url(project),
        {"repo_id": str(repo.id), "index": {"file_count": 1284, "commits": 412},
         "summary": "A legacy billing service exposing invoice + payment endpoints."},
        format="json",
    )
    assert resp.status_code == 202
    assert resp.data["status"] == "indexed"
    artifact = Artifact.objects.get(id=resp.data["artifact_id"])
    assert artifact.type == "codebase_intelligence"   # never "code" (no source copied)
    assert artifact.repo_id == repo.id
    chunks = KnowledgeChunk.objects.filter(artifact_id=artifact.id)
    assert chunks.exists()
    assert chunks.first().source == "code_intel"


def test_code_intel_without_summary_still_indexes_a_chunk(client, project, repo, tech_lead):
    _login(client, "lead@acme.com", "lead-pass!")
    resp = client.post(_ci_url(project), {"repo_id": str(repo.id)}, format="json")
    assert resp.status_code == 202
    assert KnowledgeChunk.objects.filter(artifact_id=resp.data["artifact_id"]).exists()


def test_admin_can_index_code(client, project, repo, tenant):
    User.objects.create_user(
        email="boss@acme.com", name="Boss", tenant=tenant,
        password="admin-pass!", is_tenant_admin=True,
    )
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.post(_ci_url(project), {"repo_id": str(repo.id)}, format="json")
    assert resp.status_code == 202


def test_member_cannot_index_code(client, project, repo, member):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.post(_ci_url(project), {"repo_id": str(repo.id)}, format="json")
    assert resp.status_code == 403


def test_code_intel_unknown_repo_is_404(client, project, tech_lead):
    _login(client, "lead@acme.com", "lead-pass!")
    resp = client.post(
        _ci_url(project),
        {"repo_id": "00000000-0000-0000-0000-000000000000"}, format="json",
    )
    assert resp.status_code == 404


# ── gap report ───────────────────────────────────────────────────────
def test_gap_report_get_404_before_any_build(client, project, member):
    _login(client, "dev@acme.com", "dev-pass!")
    assert client.get(_gap_url(project)).status_code == 404


def test_gap_report_resume_point_moves_as_evidence_is_added(client, project, repo, tech_lead):
    _login(client, "lead@acme.com", "lead-pass!")

    # nothing registered -> resume at the very first phase
    build0 = client.post(_gap_url(project))
    assert build0.status_code == 200
    assert build0.data["resume_phase"] == "ideation"
    get0 = client.get(_gap_url(project))
    assert get0.status_code == 200
    assert get0.data["resume_phase"] == "ideation"
    assert get0.data["phases"][0]["assessment"] == "Missing"
    assert get0.data["intel_present"] is False

    # +requirements (ideation still missing) -> resume unchanged
    _publish(project, "ideation")
    _publish(project, "requirements")
    build1 = client.post(_gap_url(project))
    assert build1.data["resume_phase"] == "prd"
    by_phase = {p["phase"]: p["assessment"] for p in build1.data["phases"]}
    assert by_phase["ideation"] == "Complete" and by_phase["requirements"] == "Complete"

    # +prd -> resume moves to architecture
    _publish(project, "prd")
    build2 = client.post(_gap_url(project))
    assert build2.data["resume_phase"] == "architecture"
    assert "architecture" in build2.data["blocking"]

    # +intel (code-intel indexed) -> intel_present flips true on the next read-through
    ci = client.post(_ci_url(project), {"repo_id": str(repo.id)}, format="json")
    assert ci.status_code == 202
    build3 = client.post(_gap_url(project))
    assert build3.data["intel_present"] is True

    get3 = client.get(_gap_url(project))
    assert get3.data["resume_phase"] == build3.data["resume_phase"]
    assert get3.data["intel_present"] is True


def test_gap_report_evidence_carries_artifact_refs(client, project, member):
    _login(client, "dev@acme.com", "dev-pass!")
    _publish(project, "ideation")
    client.post(_gap_url(project))
    resp = client.get(_gap_url(project))
    ideation = next(p for p in resp.data["phases"] if p["phase"] == "ideation")
    assert ideation["assessment"] == "Complete"
    assert ideation["evidence"] and ideation["evidence"][0]["type"] == "ideation"


# ── onboarding hub ───────────────────────────────────────────────────
def test_onboarding_hub_shape_before_anything(client, project, member):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_hub_url(project))
    assert resp.status_code == 200
    assert set(resp.data.keys()) == {"upload", "adopt", "register", "index", "gap"}
    assert resp.data["upload"] == [] and resp.data["adopt"] == []
    assert resp.data["index"] == {"status": "not_started", "artifact_id": None}
    assert resp.data["gap"] == {"ready": False}
    assert resp.data["register"]["pages_registered"] == 0


def test_onboarding_hub_reflects_uploads_index_and_gap(client, project, repo, tech_lead):
    SourceDocument.objects.create(tenant=project.tenant, project=project, filename="spec.docx",
                                  mime="application/msword",
                                  status=SourceDocument.Status.EXTRACTED)
    SourceDocument.objects.create(tenant=project.tenant, project=project, filename="nfrs.xlsx",
                                  mime="application/vnd.ms-excel",
                                  status=SourceDocument.Status.ADOPTED)
    _login(client, "lead@acme.com", "lead-pass!")

    client.post(_ci_url(project), {"repo_id": str(repo.id)}, format="json")
    client.post(_gap_url(project))

    resp = client.get(_hub_url(project))
    assert len(resp.data["upload"]) == 2
    assert len(resp.data["adopt"]) == 1 and resp.data["adopt"][0]["filename"] == "spec.docx"
    assert resp.data["index"]["status"] == "indexed"
    assert resp.data["gap"]["ready"] is True and resp.data["gap"]["resume_phase"] == "ideation"


# ── tenant isolation ─────────────────────────────────────────────────
def test_onboarding_surfaces_are_tenant_isolated(client, db):
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
    _publish(p1, "ideation")

    c = APIClient()
    _login(c, "a1@acme.com", "pw!")
    assert c.get(_hub_url(p1)).status_code == 200
    # cross-tenant project id is invisible under this admin's session (RLS/tenant scoping)
    assert c.get(_hub_url(p2)).status_code == 404
