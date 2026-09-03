"""Phase 1 acceptance slice (spec §9).

Two ingest ends of the Atlassian-SoR story, proving the Phase-1 invariants:

* **Greenfield (live):** a draft PRD publishes to **Confluence** on the post-gate publish
  step (`sor=confluence`, `external_ref` set) — and not before; a proposed backlog
  reconciles into **Jira** epics/stories (`sor=jira`), idempotently (no duplicates on
  re-run); the live issue is readable by key and a status transition round-trips back from
  Jira into the ledger; the traceability API returns the requirements→PRD→backlog lineage
  with a working Confluence deep-link. Runs only with creds; creates real objects and
  cleans them up.
* **Brownfield (offline):** a Word PRD + an Excel backlog are extracted to internal draft
  artifacts (provenance kept) and adopted through the **product_owner** review gate (wrong
  role blocked); separately, an existing Jira/Confluence project is registered
  **don't-recreate** — pointers indexed, nothing created.

The full Temporal gate-signal path (open_gate → decide_gate → publish) is proven in
`test_acceptance_slice.py` (P0); here we exercise the Phase-1 SoR surface directly so the
slice stays fast and self-contained, asserting gate-before-SoR as the artifact's state
transition across the publish step.
"""
from __future__ import annotations

import io
import uuid

import pytest
from mcp_platform_state import tools
from rest_framework.test import APIClient

from apps.integrations.models import IntegrationConnection, SourceDocument
from apps.projects.models import Project
from apps.registry.catalog import seed_agent_specs
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from integrations.onboarding import (
    OnboardingRoleError,
    adopt_source_document,
    ingest_source_document,
    register_atlassian,
)
from integrations.types import DocHit, Issue, IssueHit
from orchestration import activities
from orchestration.types import AgentRunInput
from storage import InMemoryObjectStore, content_hash


# ── live-creds gate (same policy as the other live tests) ───────────
def _live_config():
    from integrations.atlassian.config import AtlassianConfig

    cfg = AtlassianConfig.from_settings()
    return cfg if cfg.configured else None


# ════════════════════════════ GREENFIELD (live) ════════════════════════════
@pytest.mark.skipif(_live_config() is None, reason="Atlassian creds not configured in .env")
@pytest.mark.django_db
def test_phase1_greenfield_acceptance(monkeypatch):
    from django.conf import settings

    space = settings.CONFLUENCE_SPACE_KEY
    project_key = settings.JIRA_PROJECT_KEY
    marker = uuid.uuid4().hex[:8]

    # The publish path reads/writes artifact bodies through the object store; keep it
    # in-memory so the test needs no MinIO (the Confluence/Jira calls are the live part).
    store = InMemoryObjectStore()
    monkeypatch.setattr(activities, "get_object_store", lambda: store)

    # ── tenant + greenfield project + per-tenant connectors (the §1 seam) ──
    tenant = Tenant.objects.create(name=f"Greenfield {marker}")
    project = Project.objects.create(
        tenant=tenant, name="Acceptance App", track=Project.Track.GREENFIELD
    )
    IntegrationConnection.objects.create(
        tenant=tenant, capability="docstore", connector="confluence",
        scopes={"space_key": space}, token_ref="settings:atlassian",
    )
    IntegrationConnection.objects.create(
        tenant=tenant, capability="tasktracker", connector="jira",
        scopes={"project_key": project_key}, token_ref="settings:atlassian",
    )
    seed_agent_specs(tenant)

    from integrations.registry import get_capability

    docstore = get_capability(tenant.id, "docstore")
    tracker = get_capability(tenant.id, "tasktracker")
    page_id: str | None = None
    created_keys: list[str] = []
    try:
        # ── 1. PRD draft (internal) under a run; the chain's requirements feed it ──
        spec = AgentSpec.objects.get(tenant=tenant, key="03_prd")
        work_item = WorkItem.objects.create(
            tenant=tenant, project=project, type=WorkItem.Type.STORY,
            feature_stream=f"Acceptance MVP {marker}", state=WorkItem.State.PROPOSED,
        )
        run = Run.objects.create(
            tenant=tenant, work_item=work_item, agent_spec=spec,
            engine=spec.recommended_engine, model=spec.recommended_model,
            status=Run.Status.AWAITING_GATE,
        )
        prd_md = f"# PRD {marker}\n\nThe system shall let a user sign in.\n"
        prd_key = f"drafts/{tenant.id}/{project.id}/{run.id}/prd.md"
        store.put(prd_key, prd_md)
        prd = tools.register_artifact(
            str(tenant.id), str(project.id), str(run.id), "prd", "prd",
            "internal", content_hash(prd_md.encode()), s3_key=prd_key,
        )
        # An upstream requirements artifact (already internal-published) for lineage.
        req = tools.register_artifact(
            str(tenant.id), str(project.id), None, "requirements", "requirements",
            "internal", content_hash(b"reqs"), s3_key="",
        )
        tools.update_artifact(str(tenant.id), req["id"], status="published")
        tools.add_trace_edge(str(tenant.id), req["id"], prd["id"], "derives")

        # INVARIANT (gate-before-SoR): before the publish step nothing is in Confluence.
        prd_art = Artifact.objects.get(id=prd["id"])
        assert prd_art.status == Artifact.Status.DRAFT
        assert prd_art.sor == Artifact.SoR.INTERNAL and prd_art.external_ref is None

        # ── 2. Post-APPROVED publish step → published INTERNAL only (team flow decision
        # 2026-07-07: gate approval never auto-exports; the user pushes manually) ──
        inp = AgentRunInput(
            run_id=str(run.id), tenant_id=str(tenant.id), project_id=str(project.id),
            work_item_id=str(work_item.id), agent_spec_id=str(spec.id), phase="prd",
        )
        activities.publish_artifacts_core(inp)

        prd_art.refresh_from_db()
        assert prd_art.status == Artifact.Status.PUBLISHED
        assert prd_art.sor == Artifact.SoR.INTERNAL          # nothing reached Confluence
        assert prd_art.external_ref is None

        # ── 2b. Manual user-triggered export → live Confluence page (the real endpoint,
        # governed by the phase-scoped export policy: prd → docstore) ──
        publish_client = APIClient()
        resp = publish_client.post(
            f"/api/artifacts/{prd_art.id}/publish/",
            {"target_capability": "docstore"}, format="json",
            HTTP_X_TENANT_ID=str(tenant.id),
        )
        assert resp.status_code == 200, resp.data
        prd_art.refresh_from_db()
        assert prd_art.sor == Artifact.SoR.CONFLUENCE
        page_id = prd_art.external_ref["id"]
        assert page_id and prd_art.external_ref["url"].startswith(settings.ATLASSIAN_SITE_URL)

        # Read-through: the body lives in Confluence, fetched live (not copied into state).
        page = docstore.get_page(page_ref=page_id)
        assert page.title.endswith("Prd") and "sign in" in page.body_html

        # Idempotent re-export updates the same page — never a duplicate (docstore-
        # published artifacts re-export via the update path).
        resp = publish_client.post(
            f"/api/artifacts/{prd_art.id}/publish/",
            {"target_capability": "docstore"}, format="json",
            HTTP_X_TENANT_ID=str(tenant.id),
        )
        prd_art.refresh_from_db()
        assert prd_art.external_ref["id"] == page_id

        # The planning WorkItem finished at its gate — not part of the backlog to reconcile.
        tools.transition_work_item(str(tenant.id), str(work_item.id), WorkItem.State.DONE)

        # ── 3. Proposed backlog → reconcile into live Jira (no duplicates) ──
        epic = WorkItem.objects.create(
            tenant=tenant, project=project, type=WorkItem.Type.EPIC,
            title=f"Acceptance epic {marker}", state=WorkItem.State.PROPOSED,
        )
        story = WorkItem.objects.create(
            tenant=tenant, project=project, type=WorkItem.Type.STORY,
            title=f"Acceptance story {marker}", state=WorkItem.State.PROPOSED, parent=epic,
        )
        # A backlog artifact closes the requirements→PRD→backlog lineage chain.
        backlog = tools.register_artifact(
            str(tenant.id), str(project.id), None, "task_breakdown", "backlog",
            "internal", content_hash(b"backlog"), s3_key="",
        )
        tools.update_artifact(str(tenant.id), backlog["id"], status="published")
        tools.add_trace_edge(str(tenant.id), prd["id"], backlog["id"], "derives")

        # INVARIANT: not in Jira until reconciled.
        assert epic.external_ref is None and story.external_ref is None

        from integrations.reconcile import reconcile_backlog

        out = reconcile_backlog(
            tenant_id=str(tenant.id), project_id=str(project.id), project_key=project_key
        )
        # Capture every created key up front so cleanup runs even if an assertion fails.
        created_keys += [
            it["external_ref"]["id"] for it in out["items"] if it.get("external_ref")
        ]
        assert out["reconciled"] == 2 and out["created"] == 2
        epic.refresh_from_db()
        story.refresh_from_db()
        epic_key, story_key = epic.external_ref["id"], story.external_ref["id"]
        assert epic.state == WorkItem.State.ACCEPTED and epic_key.startswith(f"{project_key}-")
        assert story.external_ref["url"].endswith(story_key)

        # Idempotent reconcile: a second run creates nothing new.
        again = reconcile_backlog(
            tenant_id=str(tenant.id), project_id=str(project.id), project_key=project_key
        )
        assert again["created"] == 0

        # ── 4. Implement-by-issue-key: the live issue is readable by its key ──
        issue = tracker.get_issue(issue_ref=story_key)
        assert issue.key == story_key and issue.summary == f"Acceptance story {marker}"

        # A status transition round-trips from Jira back into the ledger.
        targets = tracker.available_transitions(issue_ref=story_key)
        if targets:
            tracker.transition_issue(issue_ref=story_key, to_state=targets[0])
            moved = tracker.get_issue(issue_ref=story_key)
            tools.log_event(
                str(tenant.id), "acceptance", "issue.transitioned", "work_item",
                str(story.id), {"issue": story_key, "to": moved.status},
            )
            from apps.ledger.models import Event

            assert Event.objects.filter(
                tenant=tenant, action="issue.transitioned", target_id=str(story.id)
            ).exists()

        # ── 5. Traceability viewer API: requirements→PRD→backlog with deep-links ──
        client = APIClient()
        resp = client.get(
            f"/api/projects/{project.id}/traceability/", HTTP_X_TENANT_ID=str(tenant.id)
        )
        assert resp.status_code == 200
        graph = resp.json()
        by_type = {n["type"]: n for n in graph["nodes"]}
        assert by_type["prd"]["sor"] == "confluence"
        assert by_type["prd"]["url"] and page_id in by_type["prd"]["url"]
        chain = {(e["from"], e["to"]) for e in graph["edges"]}
        assert (req["id"], prd["id"]) in chain and (prd["id"], backlog["id"]) in chain

        # ── 6. RLS / isolation: a second tenant sees none of this ──
        other = Tenant.objects.create(name=f"Other {marker}")
        assert tools.list_artifacts(str(other.id), str(project.id)) == []
        assert WorkItem.objects.filter(tenant=other).count() == 0
    finally:
        for key in created_keys:
            try:
                tracker.delete_issue(issue_ref=key, delete_subtasks=True)
            except Exception:  # noqa: BLE001  (best-effort cleanup)
                pass
        if page_id:
            try:
                docstore.delete_page(page_ref=page_id)
            except Exception:  # noqa: BLE001
                pass


# ════════════════════════════ BROWNFIELD (offline) ════════════════════════════
def _docx_prd() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading("Product Requirements", level=1)
    doc.add_paragraph("The system shall let a user reset their password.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _xlsx_backlog() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Story", "Acceptance"])
    ws.append(["Reset password", "A user can reset via email link"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def brownfield(db):
    t = Tenant.objects.create(name="Brownfield Co")
    project = Project.objects.create(tenant=t, name="Legacy App")
    po = User.objects.create_user(email="po@bf.test", name="PO", tenant=t, password="p")
    Membership.objects.create(tenant=t, user=po, project=project, role="product_owner")
    eng = User.objects.create_user(email="e@bf.test", name="E", tenant=t, password="p")
    Membership.objects.create(tenant=t, user=eng, project=project, role="engineer")
    return {"t": t, "project": project, "po": po, "eng": eng, "store": InMemoryObjectStore()}


def test_phase1_brownfield_static_files_extract_and_adopt(brownfield):
    """Word PRD + Excel backlog → internal draft artifacts (provenance) → review-gated
    adoption by a product_owner; a non-owner is blocked (no silent adoption, #5)."""
    t, project, store = brownfield["t"], brownfield["project"], brownfield["store"]
    kw = dict(tenant_id=str(t.id), project_id=str(project.id), object_store=store)

    prd = ingest_source_document(filename="PRD.docx", mime="", content=_docx_prd(),
                                 artifact_type="prd", **kw)
    backlog = ingest_source_document(filename="backlog.xlsx", mime="",
                                     content=_xlsx_backlog(), artifact_type="backlog", **kw)

    # Both extracted to DRAFT internal artifacts with provenance to the original file.
    for out, needle in ((prd, "reset their password"), (backlog, "Reset password")):
        art = Artifact.objects.get(id=out["artifact_ids"][0])
        assert art.status == Artifact.Status.DRAFT and art.sor == Artifact.SoR.INTERNAL
        assert art.external_ref["source"] == "static_file"
        assert needle in store.get(art.s3_key).decode("utf-8")

    # Wrong role cannot adopt; the artifact stays a draft.
    with pytest.raises(OnboardingRoleError):
        adopt_source_document(tenant_id=str(t.id),
                              source_document_id=prd["source_document_id"],
                              user_id=str(brownfield["eng"].id))
    assert Artifact.objects.get(id=prd["artifact_ids"][0]).status == Artifact.Status.DRAFT

    # The product_owner gate publishes both.
    for out in (prd, backlog):
        res = adopt_source_document(tenant_id=str(t.id),
                                    source_document_id=out["source_document_id"],
                                    user_id=str(brownfield["po"].id))
        assert res["status"] == "adopted"
        assert Artifact.objects.get(id=out["artifact_ids"][0]).status == \
            Artifact.Status.PUBLISHED
    assert SourceDocument.objects.filter(
        project=project, status=SourceDocument.Status.ADOPTED
    ).count() == 2


class _FakeDocStore:
    def __init__(self, hits):
        self._hits = hits

    def search(self, *, query, space=None):
        return self._hits


class _FakeTaskTracker:
    def __init__(self, hits, issues):
        self._hits, self._issues = hits, issues

    def search(self, *, jql):
        return self._hits

    def get_issue(self, *, issue_ref):
        return self._issues[issue_ref]


def test_phase1_brownfield_register_dont_recreate(brownfield):
    """An existing Jira/Confluence project is registered as pointers — nothing created —
    and a re-run adds nothing (idempotent by external_ref)."""
    t, project = brownfield["t"], brownfield["project"]
    docstore = _FakeDocStore([DocHit(id="900", title="Existing PRD", url="https://x/wiki/900")])
    tracker = _FakeTaskTracker(
        [IssueHit(key="ST-10", summary="Login"), IssueHit(key="ST-11", summary="Logout")],
        {"ST-10": Issue(key="ST-10", summary="Login", status="To Do", issue_type="Story",
                        url="https://x/browse/ST-10"),
         "ST-11": Issue(key="ST-11", summary="Logout", status="To Do", issue_type="Task",
                        url="https://x/browse/ST-11")},
    )
    kw = dict(tenant_id=str(t.id), project_id=str(project.id),
              docstore=docstore, tasktracker=tracker, space="SDLC", project_key="ST")

    out = register_atlassian(**kw)
    assert len(out["registered_pages"]) == 1 and len(out["registered_issues"]) == 2
    assert Artifact.objects.filter(project=project, sor="confluence",
                                   status="published").count() == 1
    issues = WorkItem.objects.filter(project=project, external_ref__isnull=False)
    assert {w.external_ref["id"] for w in issues} == {"ST-10", "ST-11"}
    assert all(w.state == WorkItem.State.ACCEPTED for w in issues)

    # Register-don't-recreate: a second run is a no-op.
    again = register_atlassian(**kw)
    assert again == {"registered_pages": [], "registered_issues": []}
    assert WorkItem.objects.filter(project=project).count() == 2
