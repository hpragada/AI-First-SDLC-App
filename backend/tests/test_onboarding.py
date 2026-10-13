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
    ensure_onboarding_work_item,
    ingest_source_document,
    link_confluence_pages,
    read_gap_report,
    register_atlassian,
    submit_agent_gap_report,
    write_gap_report_artifact,
)
from integrations.types import DocPage, Issue, IssueHit
from orchestration.trigger import NoCompanionError, trigger_onboarding_agent
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


# ── static-file extraction → adopt registers the artifact → review gate ─────
# PB-7 (`b97f804`): the UPLOAD no longer registers an artifact — it extracts into the
# SourceDocument. ADOPT is what registers the artifact, at v1, published. So the artifact id
# comes from the adopt result; the upload result's `artifact_ids` is empty by contract.
def test_ingest_extracts_into_the_source_document_and_adopt_registers_the_artifact(world):
    out = ingest_source_document(
        tenant_id=str(world["t"].id), project_id=str(world["project"].id),
        filename="PRD.docx", mime="", content=_docx_bytes(),
        artifact_type="prd", object_store=world["store"],
    )
    assert out["status"] == "extracted"
    assert out["artifact_ids"] == []                      # PB-7: nothing registered at upload

    src = SourceDocument.objects.get(id=out["source_document_id"])
    assert src.status == SourceDocument.Status.EXTRACTED
    assert src.provenance["filename"] == "PRD.docx"
    # The extraction itself lives on the source document from the moment the file lands.
    body = world["store"].get(src.provenance["extracted_s3_key"]).decode("utf-8")
    assert "# PRD" in body and "log in" in body           # extracted, not the original bytes
    assert Artifact.objects.filter(project=world["project"]).count() == 0

    res = adopt_source_document(
        tenant_id=str(world["t"].id), source_document_id=out["source_document_id"],
        user_id=str(world["po"].id),
    )
    artifact = Artifact.objects.get(id=res["artifact_ids"][0])
    assert artifact.version == 1 and artifact.status == Artifact.Status.PUBLISHED
    assert artifact.sor == Artifact.SoR.INTERNAL and artifact.type == "prd"
    assert artifact.external_ref["source"] == "static_file"
    assert artifact.s3_key == src.provenance["extracted_s3_key"]


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
    assert Artifact.objects.get(id=res["artifact_ids"][0]).status == Artifact.Status.PUBLISHED
    assert SourceDocument.objects.get(id=out["source_document_id"]).status == \
        SourceDocument.Status.ADOPTED

    again = adopt_source_document(
        tenant_id=str(world["t"].id), source_document_id=out["source_document_id"],
        user_id=str(world["po"].id),
    )
    assert again.get("idempotent") is True
    # Re-adopting must never mint a second artifact for the document.
    assert Artifact.objects.filter(project=world["project"]).count() == 1


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
    # The gate held: adopt is what registers the artifact, so a blocked adopt registers nothing
    # and leaves the document awaiting review.
    assert Artifact.objects.filter(project=world["project"]).count() == 0
    assert SourceDocument.objects.get(id=out["source_document_id"]).status == \
        SourceDocument.Status.EXTRACTED


def test_ingest_unsupported_marks_failed(world):
    with pytest.raises(ExtractionError):
        ingest_source_document(
            tenant_id=str(world["t"].id), project_id=str(world["project"].id),
            filename="logo.png", mime="image/png", content=b"\x89PNG", object_store=world["store"],
        )
    assert SourceDocument.objects.get(project=world["project"]).status == \
        SourceDocument.Status.FAILED


def test_ingest_carries_title_onto_artifact(world):
    """Brownfield B1-2: the extracted document title is threaded onto the artifact (was blank).

    Post-PB-7 the title is read at upload and parked on the source document; adopt carries it
    onto the artifact it registers. The title must survive that hand-off."""
    out = ingest_source_document(
        tenant_id=str(world["t"].id), project_id=str(world["project"].id),
        filename="PRD.docx", mime="", content=_docx_bytes(), object_store=world["store"],
    )
    assert out["title"]
    src = SourceDocument.objects.get(id=out["source_document_id"])
    assert src.provenance["title"] == out["title"]

    res = adopt_source_document(
        tenant_id=str(world["t"].id), source_document_id=out["source_document_id"],
        user_id=str(world["po"].id),
    )
    assert Artifact.objects.get(id=res["artifact_ids"][0]).title == out["title"]


def test_adopt_with_target_type_reclassifies_so_gap_report_sees_it(world):
    """Brownfield B2-1 / B5-1 (headline): an uploaded doc is typed `document`; adopting it AS
    `requirements` reclassifies + publishes it so the gap report counts it as requirements
    evidence. Before the fix the doc was invisible and every phase read 'missing'."""
    tid, pid = str(world["t"].id), str(world["project"].id)
    out = ingest_source_document(
        tenant_id=tid, project_id=pid, filename="Reqs.docx", mime="",
        content=_docx_bytes(), object_store=world["store"],  # default artifact_type -> "document"
    )
    assert SourceDocument.objects.get(
        id=out["source_document_id"]).provenance["artifact_type"] == "document"

    # Blind before classification: requirements has no matching-typed evidence.
    before = build_gap_report(tenant_id=tid, project_id=pid, object_store=world["store"])
    assert next(p for p in before["phases"] if p["phase"] == "requirements")["status"] == "missing"

    res = adopt_source_document(
        tenant_id=tid, source_document_id=out["source_document_id"],
        user_id=str(world["po"].id), target_type="requirements",
    )
    assert res["target_type"] == "requirements"
    art = Artifact.objects.get(id=res["artifact_ids"][0])
    assert art.type == "requirements" and art.status == Artifact.Status.PUBLISHED

    # Now the gap report recognises it as complete evidence for requirements.
    after = build_gap_report(tenant_id=tid, project_id=pid, object_store=world["store"])
    req = next(p for p in after["phases"] if p["phase"] == "requirements")
    assert req["status"] == "complete"
    assert res["artifact_ids"][0] in [e["artifact_id"] for e in req["evidence"]]


def test_adopt_rejects_invalid_target_type(world):
    """Brownfield B2-1: only canonical document-authored types may be chosen at adopt."""
    from integrations.onboarding import OnboardingError

    out = ingest_source_document(
        tenant_id=str(world["t"].id), project_id=str(world["project"].id),
        filename="PRD.docx", mime="", content=_docx_bytes(), object_store=world["store"],
    )
    with pytest.raises(OnboardingError):
        adopt_source_document(
            tenant_id=str(world["t"].id), source_document_id=out["source_document_id"],
            user_id=str(world["po"].id), target_type="not_a_phase",
        )


# ── Atlassian register-don't-recreate ───────────────────────────────
class _FakeDocStore:
    """B3-4: Confluence is no longer crawled — pages are resolved by id via get_page for typed
    linking. `pages` maps page id → DocPage."""

    def __init__(self, pages):
        self._pages = pages

    def get_page(self, *, page_ref):
        return self._pages[page_ref]


class _FakeTaskTracker:
    def __init__(self, hits, issues):
        self._hits = hits
        self._issues = issues

    def search(self, *, jql):
        return self._hits

    def get_issue(self, *, issue_ref):
        return self._issues[issue_ref]


def test_register_atlassian_imports_jira_backlog_idempotently(world):
    tasktracker = _FakeTaskTracker(
        [IssueHit(key="ST-1", summary="Login"), IssueHit(key="ST-2", summary="Logout")],
        {"ST-1": Issue(key="ST-1", summary="Login", status="To Do", issue_type="Story",
                       url="https://x/browse/ST-1"),
         "ST-2": Issue(key="ST-2", summary="Logout", status="To Do", issue_type="Task",
                       url="https://x/browse/ST-2")},
    )
    kw = dict(tenant_id=str(world["t"].id), project_id=str(world["project"].id),
              tasktracker=tasktracker, project_key="ST")

    out = register_atlassian(**kw)
    assert out["registered_issues"] == ["ST-1", "ST-2"] and out["tasktracker_connected"] is True

    # Issues → accepted WorkItems (register-don't-recreate; B3-4 no longer crawls Confluence).
    issues = WorkItem.objects.filter(project=world["project"], external_ref__isnull=False)
    assert issues.count() == 2 and {w.external_ref["id"] for w in issues} == {"ST-1", "ST-2"}
    assert all(w.state == WorkItem.State.ACCEPTED for w in issues)

    # Register-don't-recreate: a second run adds nothing.
    again = register_atlassian(**kw)
    assert again["registered_issues"] == []
    assert WorkItem.objects.filter(project=world["project"]).count() == 2


def test_jira_import_carries_the_issue_description(world):
    """The summary is a label; the DESCRIPTION is the specification. A brownfield backlog
    imported without it reaches the build agent as a bare one-line title, so the agent has to
    invent the requirement it was asked to implement."""
    tasktracker = _FakeTaskTracker(
        [IssueHit(key="ST-9", summary="ExpenseService")],
        {"ST-9": Issue(key="ST-9", summary="ExpenseService", status="To Do", issue_type="Task",
                       url="https://x/browse/ST-9",
                       description=(
                           "Every query MUST filter by user_id.\n- reject cross-user reads"))},
    )
    register_atlassian(tenant_id=str(world["t"].id), project_id=str(world["project"].id),
                       tasktracker=tasktracker, project_key="ST")
    wi = WorkItem.objects.get(project=world["project"], external_ref__id="ST-9")
    assert "filter by user_id" in wi.description
    assert "reject cross-user reads" in wi.description


def test_reimport_backfills_a_description_that_was_never_imported(world):
    """The create loop SKIPS an already-registered issue, so without a repair pass a backlog
    imported before descriptions were read could never be fixed — the user re-runs the import,
    sees '0 new issues', and still has a backlog with no specifications in it."""
    tasktracker = _FakeTaskTracker(
        [IssueHit(key="ST-9", summary="ExpenseService")],
        {"ST-9": Issue(key="ST-9", summary="ExpenseService", status="To Do", issue_type="Task",
                       url="https://x/browse/ST-9")},          # first import: no description
    )
    kw = dict(tenant_id=str(world["t"].id), project_id=str(world["project"].id),
              tasktracker=tasktracker, project_key="ST")
    register_atlassian(**kw)
    wi = WorkItem.objects.get(project=world["project"], external_ref__id="ST-9")
    assert wi.description == ""

    tasktracker._issues["ST-9"] = Issue(
        key="ST-9", summary="ExpenseService", status="To Do", issue_type="Task",
        url="https://x/browse/ST-9", description="Every query MUST filter by user_id.")
    out = register_atlassian(**kw)
    assert out["registered_issues"] == []            # nothing new — this is a repair, not an add
    assert out["descriptions_backfilled"] == 1
    wi.refresh_from_db()
    assert "filter by user_id" in wi.description


def test_reimport_never_overwrites_a_description_a_human_edited(world):
    """Only an EMPTY description is filled. A description edited in the platform is the human's
    and Jira does not get to overwrite it — the same rule the parent-repair pass follows."""
    tasktracker = _FakeTaskTracker(
        [IssueHit(key="ST-9", summary="ExpenseService")],
        {"ST-9": Issue(key="ST-9", summary="ExpenseService", status="To Do", issue_type="Task",
                       url="https://x/browse/ST-9", description="from jira")},
    )
    kw = dict(tenant_id=str(world["t"].id), project_id=str(world["project"].id),
              tasktracker=tasktracker, project_key="ST")
    register_atlassian(**kw)
    wi = WorkItem.objects.get(project=world["project"], external_ref__id="ST-9")
    wi.description = "the human's own words"
    wi.save(update_fields=["description"])

    out = register_atlassian(**kw)
    assert out["descriptions_backfilled"] == 0
    wi.refresh_from_db()
    assert wi.description == "the human's own words"


def test_register_atlassian_skips_gracefully_when_jira_not_connected(world):
    # B3-1: no tasktracker connected → graceful skip (no error), so onboarding never dead-ends.
    out = register_atlassian(
        tenant_id=str(world["t"].id), project_id=str(world["project"].id))
    assert out == {"registered_issues": [], "tasktracker_connected": False}
    assert WorkItem.objects.filter(project=world["project"]).count() == 0


def _docpage(pid, title):
    return DocPage(id=pid, title=title, body_html="<p/>", version=1,
                   url=f"https://x/wiki/spaces/BILL/pages/{pid}")


def _confluence_doc(world, page_id):
    return next(d for d in SourceDocument.objects.filter(project=world["project"])
                if str((d.provenance or {}).get("confluence_page_id") or "") == str(page_id))


def test_link_confluence_pages_registers_typed_pointers_idempotently(world):
    # B3-4 + S3-6 (two-step, team decision 2026-07-29): a linked page is snapshotted into a
    # SourceDocument awaiting adoption — the same journey as an upload — so the agents can
    # actually READ it. No artifact exists until someone adopts it.
    docstore = _FakeDocStore({"100": _docpage("100", "Billing PRD"),
                              "200": _docpage("200", "Arch Overview")})
    out = link_confluence_pages(
        tenant_id=str(world["t"].id), project_id=str(world["project"].id), docstore=docstore,
        links=[{"page": "https://x/wiki/spaces/BILL/pages/100/Billing-PRD", "type": "prd"},
               {"page": "200", "type": "architecture"}],
    )
    assert len(out["linked"]) == 2 and out["errors"] == []

    docs = list(SourceDocument.objects.filter(project=world["project"]))
    assert len(docs) == 2
    assert all(d.status == SourceDocument.Status.EXTRACTED for d in docs)
    assert all(d.provenance["origin"] == "confluence" for d in docs)
    by_type = {d.provenance["artifact_type"]: d for d in docs}
    assert set(by_type) == {"prd", "architecture"}
    assert by_type["prd"].provenance["confluence_page_id"] == "100"
    assert by_type["prd"].provenance["title"] == "Billing PRD"
    assert Artifact.objects.filter(project=world["project"]).count() == 0   # not yet adopted

    # Idempotent by page id: re-linking updates the declared type in place, never duplicates.
    again = link_confluence_pages(
        tenant_id=str(world["t"].id), project_id=str(world["project"].id), docstore=docstore,
        links=[{"page": "100", "type": "requirements"}],
    )
    assert len(again["linked"]) == 1
    assert again["linked"][0]["status"] == "awaiting_adoption"
    assert again["linked"][0]["artifact_id"] is None
    # Idempotency is proven here: the re-link updated page 100 in place, it did not add a third.
    assert SourceDocument.objects.filter(project=world["project"]).count() == 2
    assert _confluence_doc(world, "100").provenance["artifact_type"] == "requirements"


def test_link_confluence_bad_input_returns_per_row_errors(world):
    docstore = _FakeDocStore({})
    out = link_confluence_pages(
        tenant_id=str(world["t"].id), project_id=str(world["project"].id), docstore=docstore,
        links=[{"page": "https://x/wiki/no-page-id-here", "type": "prd"},   # unparseable link
               {"page": "100", "type": "code"}],                            # non-adoptable type
    )
    assert out["linked"] == [] and len(out["errors"]) == 2
    assert Artifact.objects.filter(project=world["project"], sor="confluence").count() == 0


def test_code_intel_summary_renders_a_deep_readable_report():
    # B4 enrichment: the persisted code-intel artifact shows the analyzer's real depth (the five
    # layers), rendered readably — not just raw counts / a Python-dict repr.
    from integrations.onboarding import _render_code_intel_summary

    body = _render_code_intel_summary("acme/api", {
        "file_count": 1284, "commits": 412, "authors": 7,
        "languages": {".py": 900, ".ts": 384},
        "communities": 5, "top_modules": ["core/app.py"], "entry_points": ["main.py"],
        "hotspot_files": [
            {"file": "billing/charge.py", "score": 88, "churn": 40, "complexity": 22}],
        "dead_code": [{"file": "legacy/unused.py"}],
        "decisions": [{"title": "Move to Stripe", "ref": "ADR-004"}],
    }, "acme/api overview")
    assert "## Risk hotspots" in body and "billing/charge.py" in body
    assert "## Architecture" in body and "core/app.py" in body
    assert "## Likely dead code" in body and "legacy/unused.py" in body
    assert "## Decisions found" in body and "ADR-004" in body
    assert "Python (900)" in body and "TypeScript (384)" in body   # readable, not a raw dict
    assert "{'.py'" not in body                                    # never a bare dict repr


def test_code_intel_summary_degrades_for_a_thin_payload():
    from integrations.onboarding import _render_code_intel_summary

    body = _render_code_intel_summary(
        "acme/api", {"file_count": 10, "commits": 3, "hotspots": 2, "languages": {".py": 10}}, "")
    assert "Files analysed:** 10" in body and "Hotspots:** 2" in body
    assert "Python (10)" in body


def test_linked_confluence_page_feeds_gap_report(world):
    # B3-4 headline (Q-1 sibling for Confluence): a typed linked page is real gap-report evidence,
    # so the resume point moves off the phase it covers — the whole point of typed linking.
    # Post-S3-6 that evidence exists once the page is ADOPTED, exactly like an uploaded file:
    # linking alone must not mark a phase complete on a document nobody has reviewed.
    docstore = _FakeDocStore({"300": _docpage("300", "Requirements")})
    link_confluence_pages(
        tenant_id=str(world["t"].id), project_id=str(world["project"].id), docstore=docstore,
        links=[{"page": "300", "type": "requirements"}],
    )
    linked_only = build_gap_report(
        tenant_id=str(world["t"].id), project_id=str(world["project"].id),
        object_store=world["store"])
    assert next(p for p in linked_only["phases"]
                if p["phase"] == "requirements")["status"] == "missing"

    adopt_source_document(
        tenant_id=str(world["t"].id),
        source_document_id=str(_confluence_doc(world, "300").id),
        user_id=str(world["po"].id),
    )
    report = build_gap_report(tenant_id=str(world["t"].id), project_id=str(world["project"].id),
                              object_store=world["store"])
    status = {p["phase"]: p["status"] for p in report["phases"]}
    assert status["requirements"] == "complete"
    assert report["resume_phase"] != "requirements"


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
def test_register_atlassian_live_imports_jira_backlog():
    from django.conf import settings

    from integrations.atlassian.config import AtlassianConfig
    from integrations.atlassian.tasktracker import AtlassianTaskTracker

    cfg = AtlassianConfig.from_settings()
    t = Tenant.objects.create(name="Brownfield Co")
    project = Project.objects.create(tenant=t, name="Existing")

    # B3-4: register_atlassian is Jira-only now (Confluence is linked + typed separately).
    out = register_atlassian(
        tenant_id=str(t.id), project_id=str(project.id),
        tasktracker=AtlassianTaskTracker(cfg, project=settings.JIRA_PROJECT_KEY),
        project_key=settings.JIRA_PROJECT_KEY,
    )
    assert out["tasktracker_connected"] is True
    # Any imported issue is a Jira-pointer WorkItem (register-don't-recreate; no body copied).
    for wi in WorkItem.objects.filter(project=project, external_ref__isnull=False):
        assert wi.external_ref["id"] and wi.external_ref["url"]
    # Idempotent: re-running imports nothing new.
    again = register_atlassian(
        tenant_id=str(t.id), project_id=str(project.id),
        tasktracker=AtlassianTaskTracker(cfg, project=settings.JIRA_PROJECT_KEY),
        project_key=settings.JIRA_PROJECT_KEY,
    )
    assert again["registered_issues"] == []


# ── Agent-driven onboarding (Slices 3–5) ─────────────────────────────
def test_write_gap_report_artifact_produces_readable_external_ref(world):
    """The ONE writer of the gap_report external_ref (shared by build_gap_report AND the agent
    path): read_gap_report must parse exactly what it writes."""
    tid, pid = str(world["t"].id), str(world["project"].id)
    phases = [{"phase": "ideation", "label": "1. Ideation", "status": "complete", "evidence": []},
              {"phase": "requirements", "label": "2. Requirements", "status": "missing",
               "evidence": []}]
    out = write_gap_report_artifact(
        tenant_id=tid, project_id=pid, phases=phases, resume="requirements",
        blockers=["requirements"], intel_present=False, object_store=world["store"])
    art = Artifact.objects.get(id=out["gap_report_id"])
    assert set(art.external_ref) == {
        "source", "resume_phase", "phases", "blockers", "intel_present"}
    assert set(art.external_ref["phases"][0]) >= {"phase", "label", "status", "evidence"}
    read = read_gap_report(tenant_id=tid, project_id=pid)
    assert read["resume_phase"] == "requirements"
    assert read["phases"][0]["assessment"] == "complete"


def test_submit_agent_gap_report_normalizes_and_reads_back(world):
    """The agent supplies a loose per-phase assessment; the tool coerces it to the full 12-phase
    canonical shape (omitted → missing, unknown phase ignored) and derives the resume phase."""
    tid, pid = str(world["t"].id), str(world["project"].id)
    submit_agent_gap_report(
        tenant_id=tid, project_id=pid,
        phases=[{"phase": "ideation", "status": "complete"},
                {"phase": "requirements", "status": "complete"},
                {"phase": "bogus_phase", "status": "complete"}],  # unknown → ignored
        resume_phase=None, blockers=None, object_store=world["store"])
    read = read_gap_report(tenant_id=tid, project_id=pid)
    assert len(read["phases"]) == 12                        # every lifecycle phase present
    by = {p["phase"]: p["assessment"] for p in read["phases"]}
    assert by["ideation"] == "complete" and by["requirements"] == "complete"
    assert by["prd"] == "missing"                           # omitted → missing
    assert read["resume_phase"] == "prd"                    # first non-complete
    assert "bogus_phase" not in by


def test_carrier_work_items_do_not_count_as_a_backlog(world):
    """S5-27 — the team's scenario: a project that finished Ideation..UX Design outside the
    platform, with NO backlog yet. Task Breakdown is assessed from work items, not documents, and
    every onboarding/vision carrier is an `epic`. Counted, they made `has_backlog` true on any
    project that had ever run an onboarding step — clicking Index code was enough, and the gap
    report corrupted its own input because the carrier is created before the run starts.

    Task Breakdown then read `complete` for a project with no backlog at all, and the resume point
    jumped past the phase the team actually needed next: "go write code" instead of "break the
    work down". A failed run is obvious; a confidently wrong resume point is not."""
    tid, pid = str(world["t"].id), str(world["project"].id)
    for t in ("ideation", "requirements", "prd", "architecture", "ux_design"):
        _published(world, t)
    # exactly what Index code / Gap report leave behind — and nothing else
    ensure_onboarding_work_item(tenant_id=tid, project_id=pid)

    out = build_gap_report(tenant_id=tid, project_id=pid, object_store=world["store"])
    by = {p["phase"]: p["status"] for p in out["phases"]}
    assert by["ux_design"] == "complete"
    assert by["task_breakdown"] == "missing", "a carrier epic was counted as the project's backlog"
    assert out["resume_phase"] == "task_breakdown"
    assert out["blockers"] == ["task_breakdown"]


def test_a_real_backlog_item_still_completes_task_breakdown(world):
    """The guard on the exclusion above: hiding carriers must not hide genuine backlog. A real
    story — the thing a Jira import or the Task-Breakdown agent creates — still counts."""
    tid, pid = str(world["t"].id), str(world["project"].id)
    for t in ("ideation", "requirements", "prd", "architecture", "ux_design"):
        _published(world, t)
    ensure_onboarding_work_item(tenant_id=tid, project_id=pid)          # carrier: ignored
    WorkItem.objects.create(tenant=world["t"], project=world["project"],
                            type=WorkItem.Type.STORY, title="US-001 login",
                            external_ref={"sor": "jira", "id": "ST-447"})

    out = build_gap_report(tenant_id=tid, project_id=pid, object_store=world["store"])
    by = {p["phase"]: p["status"] for p in out["phases"]}
    assert by["task_breakdown"] == "complete"
    assert out["resume_phase"] == "implementation"


def test_gap_report_is_bound_to_the_run_that_submitted_it(world):
    """S5-3 — the report used to be registered run-unbound, and both `verify_writes` and
    `publish_artifacts` filter on `run_id`. Unbound it counted as NO write, so an agent that
    assessed correctly and submitted once failed write-completeness and its run was marked failed;
    and the gate could never publish it, so it stayed draft forever.

    The deterministic REST path has no run and must still work — hence the None case."""
    from apps.registry.catalog import seed_agent_specs
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run

    tid, pid = str(world["t"].id), str(world["project"].id)
    seed_agent_specs(world["t"])
    spec = AgentSpec.objects.get(tenant=world["t"], key="00_onboarding")
    wi = ensure_onboarding_work_item(tenant_id=tid, project_id=pid)
    run = Run.objects.create(tenant=world["t"], work_item=wi,
                             agent_spec=spec, status=Run.Status.RUNNING)

    out = submit_agent_gap_report(
        tenant_id=tid, project_id=pid, run_id=str(run.id),
        phases=[{"phase": "ideation", "status": "complete"}],
        object_store=world["store"])
    report = Artifact.objects.get(id=out["gap_report_id"])
    assert str(report.run_id) == str(run.id)

    # …and the deterministic path, which has no run, still registers it unbound
    det = build_gap_report(tenant_id=tid, project_id=pid, object_store=world["store"])
    assert Artifact.objects.get(id=det["gap_report_id"]).run_id is None


def test_a_carrier_runs_artifact_is_not_named_twice(world):
    """Caught on the FIRST live gated run (448b8d21), not by any test: the phase artifact came
    back titled "Onboarding — Onboarding — project assessment".

    The phase prefix was suppressed by `auto_approve`, which only ever worked by coincidence —
    every carrier run happened to be headless. Making the gap report gated broke the coincidence,
    and the stutter landed on the very document a reviewer opens at the gate. The real condition
    is whether the work item is a CARRIER: its title already names the step (or, for a vision run,
    the user's own filename, which must not be renamed into platform vocabulary either)."""
    from uuid import uuid4

    from orchestration.activities import _phase_artifact_title
    from orchestration.types import AgentRunInput

    tid, pid = str(world["t"].id), str(world["project"].id)
    carrier = ensure_onboarding_work_item(tenant_id=tid, project_id=pid)
    normal = WorkItem.objects.create(tenant=world["t"], project=world["project"],
                                     type=WorkItem.Type.STORY, title="Add login")

    def _title(work_item, auto_approve):
        return _phase_artifact_title(AgentRunInput(
            run_id=str(uuid4()), tenant_id=tid, project_id=pid,
            work_item_id=str(work_item.id), agent_spec_id=str(uuid4()), phase="onboarding",
            required_role="product_owner", execution_mode="companion",
            auto_approve=auto_approve))

    # the carrier already says "Onboarding — …"; it is not prefixed again, gated or headless
    assert _title(carrier, False) == "Onboarding — project assessment"
    assert _title(carrier, True) == "Onboarding — project assessment"
    # a real work item still gets the phase prefix — that is what makes it readable in a list
    assert _title(normal, False) == "Onboarding — Add login"


def test_the_gap_report_artifact_is_named(world):
    """Also from run 448b8d21: the report registered with `title=''`, so the artifact a Product
    Owner opens at the gate had no name in any list. `register_artifact`'s contract tells agents
    to ALWAYS pass a title; the platform has to hold itself to what it tells agents."""
    tid, pid = str(world["t"].id), str(world["project"].id)
    _published(world, "ideation")
    out = build_gap_report(tenant_id=tid, project_id=pid, object_store=world["store"])
    title = Artifact.objects.get(id=out["gap_report_id"]).title
    assert title, "the gap report registered with no title"
    assert "Gap Report" in title and "Requirements" in title   # names what it decides


def test_a_hallucinated_evidence_id_does_not_destroy_the_report(world):
    """S5-20 — found while writing the end-to-end test for the runner endpoint, not by review.

    Artifact ids are exactly the kind of token a model reconstructs from memory. A cited id that
    isn't a UUID used to raise out of `add_trace_edge` (Django validates the field before any
    lookup), so ONE bad id threw away the entire submitted assessment — minutes of agent work,
    and the user sees nothing. Losing one provenance link is a small visible loss; losing the
    report is not. Also guards the cross-project case: a well-formed id belonging to somewhere
    else is not this report's provenance."""
    tid, pid = str(world["t"].id), str(world["project"].id)
    real = _published(world, "ideation")
    other_project = Project.objects.create(tenant=world["t"], name="Other")
    stranger = tools.register_artifact(
        tid, str(other_project.id), None, phase="onboarding", type="ideation",
        sor="internal", content_hash="h")["id"]

    out = submit_agent_gap_report(
        tenant_id=tid, project_id=pid, object_store=world["store"],
        phases=[{"phase": "ideation", "status": "complete", "evidence": [
            {"artifact_id": real},
            {"artifact_id": "PRD-2024-final"},        # invented, not even a UUID
            {"artifact_id": stranger},                # real, but another project's
            "bare-string-not-a-dict",                 # shorthand the normalizer accepts
        ]}])

    assert out["gap_report_id"]                                    # the report SURVIVED
    edges = {str(e.to_artifact_id) for e in TraceEdge.objects.filter(
        from_artifact_id=out["gap_report_id"])}
    assert edges == {real}                                         # only what resolves is linked


def test_ensure_onboarding_work_item_idempotent_per_repo(world):
    from apps.projects.models import Repository

    tid, pid = str(world["t"].id), str(world["project"].id)
    a = ensure_onboarding_work_item(tenant_id=tid, project_id=pid)
    b = ensure_onboarding_work_item(tenant_id=tid, project_id=pid)
    assert a.id == b.id and a.type == WorkItem.Type.EPIC     # one repo-agnostic carrier
    repo = Repository.objects.create(tenant=world["t"], project=world["project"], name="acme/api")
    r1 = ensure_onboarding_work_item(tenant_id=tid, project_id=pid, repo_id=str(repo.id))
    r2 = ensure_onboarding_work_item(tenant_id=tid, project_id=pid, repo_id=str(repo.id))
    assert r1.id == r2.id and r1.id != a.id and r1.repo_id == repo.id  # a separate pinned carrier


def test_trigger_onboarding_agent_fails_closed_without_companion(world):
    """No companion enrolled → NoCompanionError (never a silent server-mode run that lacks the
    worktree + ask_human tools)."""
    tid, pid = str(world["t"].id), str(world["project"].id)
    with pytest.raises(NoCompanionError):
        trigger_onboarding_agent(
            tenant_id=tid, project_id=pid, agent_key="00_onboarding",
            triggered_by=str(world["po"].id), workflow_starter=lambda *a, **k: None)


def test_trigger_onboarding_agent_dispatches_companion_run_when_enrolled(world):
    from apps.registry.catalog import seed_agent_specs
    from apps.runs.enrollment import enroll_runner
    from apps.runs.models import Run

    tid, pid = str(world["t"].id), str(world["project"].id)
    seed_agent_specs(world["t"])
    enroll_runner(tenant_id=tid, project_id=pid, developer_id=str(world["po"].id), label="l")
    seen = {}
    res = trigger_onboarding_agent(
        tenant_id=tid, project_id=pid, agent_key="00_onboarding",
        triggered_by=str(world["po"].id),
        workflow_starter=lambda wf_id, inp: seen.update(inp=inp))
    assert seen["inp"].execution_mode == "companion"        # fail-closed to the companion
    carrier = WorkItem.objects.get(
        tenant=world["t"], project=world["project"], type=WorkItem.Type.EPIC)
    assert seen["inp"].work_item_id == str(carrier.id)      # ran against the carrier WI
    assert Run.objects.filter(id=res.run_id).exists()


# ── Headless onboarding steps (Index code / Gap report) ───────────────────────
def test_index_code_runs_headless_without_opening_a_gate(world):
    """Index code is a setup step, not a lifecycle phase anyone signs off. Its run is hosted on a
    carrier hidden from the backlog and from Phases & Runs, and its output is a mechanical index —
    so it publishes without a gate. (The Gap report is the deliberate exception; see below.)"""
    from apps.projects.models import Repository
    from apps.registry.catalog import seed_agent_specs
    from apps.runs.enrollment import enroll_runner

    tid, pid = str(world["t"].id), str(world["project"].id)
    seed_agent_specs(world["t"])
    enroll_runner(tenant_id=tid, project_id=pid, developer_id=str(world["po"].id), label="l")
    repo = Repository.objects.create(tenant=world["t"], project=world["project"],
                                     name="acme/legacy")
    seen = {}
    trigger_onboarding_agent(
        tenant_id=tid, project_id=pid, agent_key="00c_intelligent_context_extractor",
        repo_id=str(repo.id), triggered_by=str(world["po"].id),
        workflow_starter=lambda wf_id, inp: seen.update(inp=inp))
    assert seen["inp"].auto_approve is True


def test_gap_report_opens_a_product_owner_gate(world):
    """Team decision 2026-08-03. The gap report is NOT a mechanical setup step like Index code: it
    is a judgement about the client's project — which phases are done, where to resume — and the
    pipeline acts on it. So it runs GATED and a Product Owner owns the call.

    The old "a gate here could never be found" reasoning does not apply: only the backlog
    (WorkItemViewSet) and Phases & Runs (RunViewSet) hide carriers. ApprovalViewSet and the
    dashboard's pending-gates query do not, so the gate is reachable the moment it opens.

    Approval is also the report's ONLY publish route — `publish_artifacts` runs on the approved
    path and the report is bound to its run, so headless would have left it draft forever."""
    from apps.registry.catalog import seed_agent_specs
    from apps.runs.enrollment import enroll_runner

    tid, pid = str(world["t"].id), str(world["project"].id)
    seed_agent_specs(world["t"])
    enroll_runner(tenant_id=tid, project_id=pid, developer_id=str(world["po"].id), label="l")
    seen = {}
    trigger_onboarding_agent(
        tenant_id=tid, project_id=pid, agent_key="00_onboarding",
        triggered_by=str(world["po"].id),
        workflow_starter=lambda wf_id, inp: seen.update(inp=inp))
    assert seen["inp"].auto_approve is False

    from apps.registry.catalog import get_by_key

    assert get_by_key("00_onboarding").gate_role == "product_owner"


def test_a_normal_phase_still_opens_its_gate(world):
    """The guard on the change above: `auto_approve` must stay False for every ordinary phase, or
    this fix would silently publish lifecycle work with no human review (#5)."""
    from orchestration.trigger import trigger_phase

    from apps.registry.catalog import seed_agent_specs
    from apps.workitems.models import WorkItem as WI

    tid, pid = str(world["t"].id), str(world["project"].id)
    seed_agent_specs(world["t"])
    wi = WI.objects.create(tenant=world["t"], project=world["project"],
                           type=WI.Type.STORY, title="a real story")
    seen = {}
    trigger_phase(
        tenant_id=tid, project_id=pid, work_item_id=str(wi.id), agent_key="01_ideation",
        triggered_by=str(world["po"].id),
        workflow_starter=lambda wf_id, inp: seen.update(inp=inp))
    assert seen["inp"].auto_approve is False


def test_step_state_reports_running_and_a_pending_question(world):
    """The hub is the ONLY surface these runs appear on, so it must distinguish 'working' from
    'blocked on you' — a run waiting on ask_human is still running, but the user must act."""
    from apps.clarifications.models import Clarification
    from apps.registry.catalog import seed_agent_specs
    from apps.runs.enrollment import enroll_runner
    from apps.runs.models import Run
    from integrations.onboarding import onboarding_step_state

    tid, pid = str(world["t"].id), str(world["project"].id)
    seed_agent_specs(world["t"])
    enroll_runner(tenant_id=tid, project_id=pid, developer_id=str(world["po"].id), label="l")

    idle = onboarding_step_state(tenant_id=tid, project_id=pid, agent_key="00_onboarding")
    # nothing dispatched yet. Asserted by MEANING, not by dict equality — this state gains keys as
    # the hub learns to show more (S5-18: `approval_id` for the gate), and a strict `==` fails on
    # additions that are correct.
    assert idle["running"] is False and idle["run_id"] is None
    assert idle["question"] is None and idle["approval_id"] is None

    res = trigger_onboarding_agent(
        tenant_id=tid, project_id=pid, agent_key="00_onboarding",
        triggered_by=str(world["po"].id), workflow_starter=lambda *a, **k: None)
    run = Run.objects.get(id=res.run_id)
    live = onboarding_step_state(tenant_id=tid, project_id=pid, agent_key="00_onboarding")
    assert live["running"] is True and live["run_id"] == str(run.id) and live["question"] is None

    Clarification.objects.create(
        tenant=world["t"], run=run, work_item=run.work_item, phase="onboarding",
        status=Clarification.Status.PENDING, questions=[{"id": "q1", "text": "which repo?"}])
    blocked = onboarding_step_state(tenant_id=tid, project_id=pid, agent_key="00_onboarding")
    assert blocked["running"] is True and blocked["question"]["count"] == 1

    run.status = Run.Status.COMPLETED
    run.save(update_fields=["status"])
    assert onboarding_step_state(
        tenant_id=tid, project_id=pid, agent_key="00_onboarding")["running"] is False


def test_step_state_surfaces_the_gap_reports_pending_gate(world):
    """S5-8 — the gap report is gated, so its run ends at `awaiting_gate`. That status counts as
    "still in flight", which alone made the hub show "working…" for as long as the user took to
    approve — with no way to reach the gate from the one page they were looking at. `approval_id`
    is what lets the hub say "waiting for your approval" and link to it."""
    from apps.gates.models import Approval
    from apps.registry.catalog import seed_agent_specs
    from apps.runs.enrollment import enroll_runner
    from apps.runs.models import Run
    from integrations.onboarding import onboarding_step_state

    tid, pid = str(world["t"].id), str(world["project"].id)
    seed_agent_specs(world["t"])
    enroll_runner(tenant_id=tid, project_id=pid, developer_id=str(world["po"].id), label="l")
    res = trigger_onboarding_agent(
        tenant_id=tid, project_id=pid, agent_key="00_onboarding",
        triggered_by=str(world["po"].id), workflow_starter=lambda *a, **k: None)
    run = Run.objects.get(id=res.run_id)

    # running, but no gate yet
    assert onboarding_step_state(
        tenant_id=tid, project_id=pid, agent_key="00_onboarding")["approval_id"] is None

    run.status = Run.Status.AWAITING_GATE
    run.save(update_fields=["status"])
    approval = Approval.objects.create(
        tenant=world["t"], run=run, work_item=run.work_item,
        gate_type="phase_gate", required_role="product_owner", decision="pending")

    parked = onboarding_step_state(tenant_id=tid, project_id=pid, agent_key="00_onboarding")
    assert parked["running"] is True                       # the run is not finished…
    assert parked["approval_id"] == str(approval.id)       # …it is waiting on the user


def test_carrier_q_never_hides_a_work_item_without_a_source_key(world):
    """S3-13 regression guard. `carrier_q` must match ONLY when `source` EXISTS and names a
    carrier: an imported Jira item's external_ref has no `source` key, and dropping the has_key
    half makes Postgres evaluate NULL IN (…) → NULL → NOT NULL → NULL and delete the row from
    the list. That emptied the backlog for every project."""
    from integrations.onboarding import carrier_q

    from apps.workitems.models import WorkItem as WI

    jira = WI.objects.create(tenant=world["t"], project=world["project"], type=WI.Type.STORY,
                             title="imported", external_ref={"sor": "jira", "id": "ST-447"})
    plain = WI.objects.create(tenant=world["t"], project=world["project"], type=WI.Type.STORY,
                              title="hand written", external_ref=None)
    carrier = ensure_onboarding_work_item(
        tenant_id=str(world["t"].id), project_id=str(world["project"].id))
    visible = set(WI.objects.exclude(carrier_q()).values_list("id", flat=True))
    assert jira.id in visible and plain.id in visible and carrier.id not in visible


def test_hub_index_repos_carry_both_running_and_status(world):
    """The hub payload — not just `onboarding_step_state` — must carry BOTH keys. Shipped once
    with `status` only: the button (switching on `status`) worked while the progress line
    (reading `running`) silently rendered nothing, so a dispatched run showed a locked button
    and no explanation. Testing the state helper alone did not catch it; test the wiring."""
    from apps.projects.models import Repository
    from apps.registry.catalog import seed_agent_specs
    from apps.runs.enrollment import enroll_runner
    from integrations.onboarding import onboarding_hub

    tid, pid = str(world["t"].id), str(world["project"].id)
    seed_agent_specs(world["t"])
    enroll_runner(tenant_id=tid, project_id=pid, developer_id=str(world["po"].id), label="l")
    repo = Repository.objects.create(tenant=world["t"], project=world["project"], name="acme/api")

    idle = onboarding_hub(tenant_id=tid, project_id=pid)["index"]["repos"][0]
    assert idle["running"] is False and idle["status"] == "not_started"

    trigger_onboarding_agent(
        tenant_id=tid, project_id=pid, agent_key="00c_intelligent_context_extractor",
        repo_id=str(repo.id), triggered_by=str(world["po"].id),
        workflow_starter=lambda *a, **k: None)
    live = onboarding_hub(tenant_id=tid, project_id=pid)["index"]["repos"][0]
    assert live["running"] is True and live["status"] == "running" and live["run_id"]
    # The gap step shares the component, so it must expose the same keys.
    assert set(onboarding_hub(tenant_id=tid, project_id=pid)["gap"]) >= {
        "running", "run_id", "question"}
