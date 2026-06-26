"""P1 — brownfield-lite onboarding: static-file extraction + review gate, and
Atlassian register-don't-recreate."""
import io

import pytest
from mcp_platform_state import tools

from apps.integrations.models import SourceDocument
from apps.projects.models import Project
from apps.registry.models import Artifact, TraceEdge
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from integrations.extract import ExtractionError
from integrations.onboarding import (
    OnboardingRoleError,
    adopt_source_document,
    build_gap_report,
    ingest_source_document,
    register_atlassian,
)
from integrations.types import DocHit, Issue, IssueHit
from storage import InMemoryObjectStore


def _docx_bytes() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading("PRD", level=1)
    doc.add_paragraph("The system shall let a user log in.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Legacy App")
    po = User.objects.create_user(email="po@acme.test", name="PO", tenant=t, password="p")
    Membership.objects.create(tenant=t, user=po, project=project, role="product_owner")
    eng = User.objects.create_user(email="e@acme.test", name="E", tenant=t, password="p")
    Membership.objects.create(tenant=t, user=eng, project=project, role="engineer")
    return {"t": t, "project": project, "po": po, "eng": eng, "store": InMemoryObjectStore()}


# ── static-file extraction → draft artifact → review gate ───────────
def test_ingest_creates_draft_artifact_with_provenance(world):
    out = ingest_source_document(
        tenant_id=str(world["t"].id), project_id=str(world["project"].id),
        filename="PRD.docx", mime="", content=_docx_bytes(),
        artifact_type="prd", object_store=world["store"],
    )
    assert out["status"] == "extracted"

    src = SourceDocument.objects.get(id=out["source_document_id"])
    assert src.status == SourceDocument.Status.EXTRACTED
    assert src.provenance["filename"] == "PRD.docx"

    artifact = Artifact.objects.get(id=out["artifact_ids"][0])
    assert artifact.status == Artifact.Status.DRAFT       # awaiting review (#5)
    assert artifact.sor == Artifact.SoR.INTERNAL and artifact.type == "prd"
    assert artifact.external_ref["source"] == "static_file"
    body = world["store"].get(artifact.s3_key).decode("utf-8")
    assert "# PRD" in body and "log in" in body           # extracted, not the original bytes


def test_adopt_publishes_after_role_check_and_is_idempotent(world):
    out = ingest_source_document(
        tenant_id=str(world["t"].id), project_id=str(world["project"].id),
        filename="PRD.docx", mime="", content=_docx_bytes(), object_store=world["store"],
    )
    res = adopt_source_document(
        tenant_id=str(world["t"].id), source_document_id=out["source_document_id"],
        user_id=str(world["po"].id),
    )
    assert res["status"] == "adopted"
    assert Artifact.objects.get(id=out["artifact_ids"][0]).status == Artifact.Status.PUBLISHED
    assert SourceDocument.objects.get(id=out["source_document_id"]).status == \
        SourceDocument.Status.ADOPTED

    again = adopt_source_document(
        tenant_id=str(world["t"].id), source_document_id=out["source_document_id"],
        user_id=str(world["po"].id),
    )
    assert again.get("idempotent") is True


def test_adopt_wrong_role_is_blocked(world):
    out = ingest_source_document(
        tenant_id=str(world["t"].id), project_id=str(world["project"].id),
        filename="PRD.docx", mime="", content=_docx_bytes(), object_store=world["store"],
    )
    with pytest.raises(OnboardingRoleError):
        adopt_source_document(
            tenant_id=str(world["t"].id), source_document_id=out["source_document_id"],
            user_id=str(world["eng"].id),
        )
    assert Artifact.objects.get(id=out["artifact_ids"][0]).status == Artifact.Status.DRAFT


def test_ingest_unsupported_marks_failed(world):
    with pytest.raises(ExtractionError):
        ingest_source_document(
            tenant_id=str(world["t"].id), project_id=str(world["project"].id),
            filename="notes.txt", mime="text/plain", content=b"hi", object_store=world["store"],
        )
    assert SourceDocument.objects.get(project=world["project"]).status == \
        SourceDocument.Status.FAILED


# ── Atlassian register-don't-recreate ───────────────────────────────
class _FakeDocStore:
    def __init__(self, hits):
        self._hits = hits

    def search(self, *, query, space=None):
        return self._hits


class _FakeTaskTracker:
    def __init__(self, hits, issues):
        self._hits = hits
        self._issues = issues

    def search(self, *, jql):
        return self._hits

    def get_issue(self, *, issue_ref):
        return self._issues[issue_ref]


def test_register_atlassian_indexes_pointers_idempotently(world):
    docstore = _FakeDocStore([
        DocHit(id="100", title="Existing PRD", url="https://x/wiki/100"),
        DocHit(id="101", title="Notes", url="https://x/wiki/101"),
    ])
    tasktracker = _FakeTaskTracker(
        [IssueHit(key="ST-1", summary="Login"), IssueHit(key="ST-2", summary="Logout")],
        {"ST-1": Issue(key="ST-1", summary="Login", status="To Do", issue_type="Story",
                       url="https://x/browse/ST-1"),
         "ST-2": Issue(key="ST-2", summary="Logout", status="To Do", issue_type="Task",
                       url="https://x/browse/ST-2")},
    )
    kw = dict(tenant_id=str(world["t"].id), project_id=str(world["project"].id),
              docstore=docstore, tasktracker=tasktracker, space="SDLC", project_key="ST")

    out = register_atlassian(**kw)
    assert len(out["registered_pages"]) == 2 and len(out["registered_issues"]) == 2

    # Pages → published Confluence-pointer artifacts; issues → accepted WorkItems.
    pages = Artifact.objects.filter(project=world["project"], sor="confluence")
    assert pages.count() == 2 and all(p.status == "published" for p in pages)
    issues = WorkItem.objects.filter(project=world["project"], external_ref__isnull=False)
    assert issues.count() == 2 and {w.external_ref["id"] for w in issues} == {"ST-1", "ST-2"}
    assert all(w.state == WorkItem.State.ACCEPTED for w in issues)

    # Register-don't-recreate: a second run adds nothing.
    again = register_atlassian(**kw)
    assert again == {"registered_pages": [], "registered_issues": []}
    assert Artifact.objects.filter(project=world["project"], sor="confluence").count() == 2
    assert WorkItem.objects.filter(project=world["project"]).count() == 2


# ── full onboarding: reconcile → gap report → resume (D7) ───────────
def _published(world, type_):
    art = tools.register_artifact(
        str(world["t"].id), str(world["project"].id), None,
        phase="onboarding", type=type_, sor="internal", content_hash="h")
    tools.update_artifact(str(world["t"].id), art["id"], status="published")
    return art["id"]


def _draft(world, type_):
    return tools.register_artifact(
        str(world["t"].id), str(world["project"].id), None,
        phase="onboarding", type=type_, sor="internal", content_hash="h")["id"]


def test_gap_report_empty_project_resumes_at_ideation(world):
    out = build_gap_report(tenant_id=str(world["t"].id), project_id=str(world["project"].id),
                           object_store=world["store"])
    assert out["resume_phase"] == "ideation"
    assert out["blockers"] == ["ideation"]
    assert all(p["status"] == "missing" for p in out["phases"])
    # the report itself is a DRAFT internal artifact (published only on the gate, #5)
    report = Artifact.objects.get(id=out["gap_report_id"])
    assert report.type == "gap_report" and report.sor == "internal"
    assert report.status == Artifact.Status.DRAFT
    assert report.external_ref["resume_phase"] == "ideation"


def test_gap_report_picks_first_incomplete_phase_and_links_evidence(world):
    ideation = _published(world, "ideation")
    requirements = _published(world, "requirements")
    prd = _published(world, "prd")
    architecture = _draft(world, "architecture")           # registered, not yet adopted

    out = build_gap_report(tenant_id=str(world["t"].id), project_id=str(world["project"].id),
                           object_store=world["store"])
    status = {p["phase"]: p["status"] for p in out["phases"]}
    assert status["prd"] == "complete" and status["architecture"] == "partial"
    assert out["resume_phase"] == "architecture"           # first non-complete phase
    assert out["blockers"] == []                            # nothing Missing up to the resume

    # the gap report derives from every evidence artifact it weighed
    edges = {str(e.to_artifact_id) for e in TraceEdge.objects.filter(
        from_artifact_id=out["gap_report_id"])}
    assert edges == {ideation, requirements, prd, architecture}


def test_gap_report_intel_marks_implementation_assessed(world):
    tools.register_artifact(str(world["t"].id), str(world["project"].id), None,
                            phase="onboarding", type="codebase_intelligence",
                            sor="internal", content_hash="h")
    out = build_gap_report(tenant_id=str(world["t"].id), project_id=str(world["project"].id),
                           object_store=world["store"])
    assert out["intel_present"] is True
    status = {p["phase"]: p["status"] for p in out["phases"]}
    # code exists (intelligence proves it) → Implementation is assessed Complete, not Missing
    assert status["implementation"] == "complete"
    assert out["resume_phase"] == "ideation"               # docs still missing up front


# ── live Atlassian discovery (read-only; runs only with creds) ──────
def _live_config():
    from integrations.atlassian.config import AtlassianConfig

    cfg = AtlassianConfig.from_settings()
    return cfg if cfg.configured else None


@pytest.mark.skipif(_live_config() is None, reason="Atlassian creds not configured in .env")
@pytest.mark.django_db
def test_register_atlassian_live_discovers_existing_space():
    from django.conf import settings

    from integrations.atlassian.config import AtlassianConfig
    from integrations.atlassian.docstore import AtlassianDocStore
    from integrations.atlassian.tasktracker import AtlassianTaskTracker

    cfg = AtlassianConfig.from_settings()
    t = Tenant.objects.create(name="Brownfield Co")
    project = Project.objects.create(tenant=t, name="Existing")

    out = register_atlassian(
        tenant_id=str(t.id), project_id=str(project.id),
        docstore=AtlassianDocStore(cfg),
        tasktracker=AtlassianTaskTracker(cfg, project=settings.JIRA_PROJECT_KEY),
        space=settings.CONFLUENCE_SPACE_KEY, project_key=settings.JIRA_PROJECT_KEY,
    )
    # The SDLC space has pages → at least one registered, each a Confluence pointer.
    assert len(out["registered_pages"]) >= 1
    for art in Artifact.objects.filter(project=project, sor="confluence"):
        assert art.external_ref["id"] and art.external_ref["url"]
    # Idempotent: re-running registers nothing new.
    again = register_atlassian(
        tenant_id=str(t.id), project_id=str(project.id),
        docstore=AtlassianDocStore(cfg),
        tasktracker=AtlassianTaskTracker(cfg, project=settings.JIRA_PROJECT_KEY),
        space=settings.CONFLUENCE_SPACE_KEY, project_key=settings.JIRA_PROJECT_KEY,
    )
    assert again["registered_pages"] == []
