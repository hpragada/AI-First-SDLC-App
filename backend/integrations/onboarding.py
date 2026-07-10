"""Brownfield-lite onboarding (spec §6 / B4) — bring an existing single-repo project
onto the platform two ways, register-don't-recreate:

1. **Static-file extraction:** upload Word/Excel/PDF → store the original in S3 → extract
   to markdown → register a *draft* internal artifact (provenance to the original) →
   **review gate** (`adopt`, product_owner) publishes it. Extraction is lossy/untrusted,
   so adoption is human-gated (#5).
2. **Atlassian register-don't-recreate:** discover existing Confluence pages + Jira issues
   and register *pointers* (never create) — they're already the live SoR, so they're
   indexed as published artifacts / accepted work items. Idempotent by external_ref.

**Full onboarding gap report (Phase 4 §5 / D7):** after discovery has registered what exists
(via the two paths above) and 00c has produced code intelligence, `build_gap_report` does the
**reconcile → gap-detect → report** step the 00 agent reasons over: it assesses each lifecycle
phase Complete / Partial / Missing from the registered artifacts + code-intel + work items,
picks the **resume phase**, and registers a *draft* `gap_report` artifact (published only on the
product_owner gate, #5). Gap-*fill* generation is then the normal phase agents, each gated.
"""
from __future__ import annotations

from mcp_platform_state import tools

from .extract import extract
from .registry import get_capability, get_connection


class OnboardingError(Exception):
    """Onboarding could not proceed (e.g. document not ready for adoption)."""


class OnboardingRoleError(OnboardingError):
    """The adopting user lacks the required role for the review gate."""


def _object_store(injected):
    if injected is not None:
        return injected
    from storage import s3_from_settings

    return s3_from_settings()


# ── static-file extraction ──────────────────────────────────────────
def ingest_source_document(*, tenant_id, project_id, filename, mime, content,
                           artifact_type="document", object_store=None) -> dict:
    """Store + extract an uploaded file into a draft internal artifact (provenance kept)."""
    from apps.integrations.models import SourceDocument
    from apps.projects.models import Project
    from apps.tenancy.context import tenant_context
    from storage import content_hash

    store = _object_store(object_store)
    with tenant_context(tenant_id):
        project = Project.objects.get(id=project_id, tenant_id=tenant_id)
        src = SourceDocument.objects.create(
            tenant_id=tenant_id, project=project, filename=filename, mime=mime,
            status=SourceDocument.Status.EXTRACTING,
        )
    src_key = f"onboarding/{tenant_id}/{project_id}/{src.id}/source/{filename}"
    store.put(src_key, content)

    try:
        title, body = extract(filename=filename, mime=mime, content=content)
    except Exception:
        with tenant_context(tenant_id):
            SourceDocument.objects.filter(id=src.id, tenant_id=tenant_id).update(
                status=SourceDocument.Status.FAILED, s3_key=src_key
            )
        raise

    body_key = f"onboarding/{tenant_id}/{project_id}/{src.id}/extracted.md"
    store.put(body_key, body)
    artifact = tools.register_artifact(
        tenant_id, project_id, None, phase="onboarding", type=artifact_type,
        sor="internal", content_hash=content_hash(body.encode("utf-8")), s3_key=body_key,
        external_ref={"source": "static_file", "filename": filename,
                      "source_document_id": str(src.id), "source_s3_key": src_key},
    )
    with tenant_context(tenant_id):
        src = SourceDocument.objects.get(id=src.id, tenant_id=tenant_id)
        src.s3_key = src_key
        src.status = SourceDocument.Status.EXTRACTED
        src.extracted_artifact_ids = [artifact["id"]]
        src.provenance = {"filename": filename, "mime": mime, "source_s3_key": src_key,
                          "title": title}
        src.save(update_fields=["s3_key", "status", "extracted_artifact_ids",
                                "provenance", "updated_at"])
        tools.log_event(tenant_id, "onboarding", "source_document.extracted",
                        "source_document", str(src.id),
                        {"artifact_id": artifact["id"], "filename": filename})
    return {"source_document_id": str(src.id), "status": "extracted",
            "artifact_ids": [artifact["id"]], "title": title}


def adopt_source_document(*, tenant_id, source_document_id, user_id) -> dict:
    """Review gate: a product_owner publishes the extracted draft artifacts (idempotent)."""
    from apps.integrations.models import SourceDocument
    from apps.tenancy.context import tenant_context
    from apps.tenancy.models import Membership, User

    with tenant_context(tenant_id):
        src = SourceDocument.objects.get(id=source_document_id, tenant_id=tenant_id)
        artifact_ids = [str(x) for x in src.extracted_artifact_ids]
        if src.status == SourceDocument.Status.ADOPTED:
            return {"source_document_id": str(src.id), "status": "adopted",
                    "artifact_ids": artifact_ids, "idempotent": True}
        if src.status != SourceDocument.Status.EXTRACTED:
            raise OnboardingError(f"not ready for adoption (status={src.status})")
        # Adoption is a review gate: the product_owner decides — OR an admin who can approve
        # any gate (project-admin = Membership(role="admin"), or tenant-admin =
        # User.is_tenant_admin), mirroring decide_gate's role check (P4.7-T4).
        has_role = Membership.objects.filter(
            tenant_id=tenant_id, user_id=user_id, project_id=src.project_id,
            role__in=["product_owner", "admin"],
        ).exists()
        if not has_role:
            has_role = User.objects.filter(
                id=user_id, tenant_id=tenant_id, is_tenant_admin=True
            ).exists()
        if not has_role:
            raise OnboardingRoleError(
                f"user {user_id} lacks role 'product_owner' for this project"
            )

    for aid in artifact_ids:
        tools.update_artifact(tenant_id, aid, status="published")
    with tenant_context(tenant_id):
        src = SourceDocument.objects.get(id=source_document_id, tenant_id=tenant_id)
        src.status = SourceDocument.Status.ADOPTED
        src.save(update_fields=["status", "updated_at"])
        tools.log_event(tenant_id, f"user:{user_id}", "source_document.adopted",
                        "source_document", str(src.id), {"artifact_ids": artifact_ids})
    return {"source_document_id": str(source_document_id), "status": "adopted",
            "artifact_ids": artifact_ids}


# ── Atlassian register-don't-recreate ───────────────────────────────
_ISSUE_TYPE = {"Epic": "epic", "Story": "story", "Task": "task",
               "Sub-task": "task", "Subtask": "task"}


def register_atlassian(*, tenant_id, project_id, docstore=None, tasktracker=None,
                       space=None, project_key=None) -> dict:
    """Index existing Confluence pages + Jira issues as pointers, creating nothing (B1)."""
    from apps.projects.models import Project
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    if docstore is None:
        docstore = get_capability(tenant_id, "docstore")
    if tasktracker is None:
        tasktracker = get_capability(tenant_id, "tasktracker")
    if space is None:
        conn = get_connection(tenant_id, "docstore")
        space = (conn.scopes or {}).get("space_key") if conn else None
    if project_key is None:
        conn = get_connection(tenant_id, "tasktracker")
        project_key = (conn.scopes or {}).get("project_key") if conn else None

    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        existing_pages = {
            (a.external_ref or {}).get("id")
            for a in Artifact.objects.filter(
                tenant_id=tenant_id, project_id=project_id, sor="confluence")
        }
        existing_issues = {
            (w.external_ref or {}).get("id")
            for w in WorkItem.objects.filter(tenant_id=tenant_id, project_id=project_id)
            if w.external_ref
        }

    registered_pages: list[str] = []
    for hit in (docstore.search(query="", space=space) if space else []):
        if hit.id in existing_pages:
            continue
        art = tools.register_artifact(
            tenant_id, project_id, None, phase="onboarding", type="document",
            sor="confluence", content_hash="",
            external_ref={"sor": "confluence", "id": hit.id, "url": hit.url, "title": hit.title},
        )
        tools.update_artifact(tenant_id, art["id"], status="published")
        registered_pages.append(art["id"])

    registered_issues: list[str] = []
    for hit in (tasktracker.search(jql=f'project = "{project_key}"') if project_key else []):
        if hit.key in existing_issues:
            continue
        issue = tasktracker.get_issue(issue_ref=hit.key)
        with tenant_context(tenant_id):
            project = Project.objects.get(id=project_id, tenant_id=tenant_id)
            wi = WorkItem.objects.create(
                tenant_id=tenant_id, project=project,
                type=_ISSUE_TYPE.get(issue.issue_type, "task"), title=issue.summary,
                state=WorkItem.State.ACCEPTED,
                external_ref={"sor": "jira", "id": issue.key, "url": issue.url},
            )
            tools.log_event(tenant_id, "onboarding", "issue.registered", "work_item",
                            str(wi.id), {"issue": issue.key})
        registered_issues.append(hit.key)

    return {"registered_pages": registered_pages, "registered_issues": registered_issues}


# ── full onboarding: reconcile → gap report → resume (D7) ────────────
# The lifecycle, in order, with the registered artifact types that evidence each phase.
# Resume = the first phase that is not Complete; the report names what is missing before it.
_LIFECYCLE: list[tuple[str, str, tuple[str, ...]]] = [
    ("ideation", "1. Ideation", ("ideation",)),
    ("requirements", "2. Requirements", ("requirements",)),
    ("prd", "3. PRD", ("prd",)),
    ("architecture", "4. Architecture",
     ("architecture", "adr", "data_model", "api_spec", "tech_stack", "security_architecture")),
    ("ux_design", "5. UX Design",
     ("ux_design", "user_journey", "wireframe", "design_system", "accessibility")),
    ("task_breakdown", "6. Task Breakdown", ("task_breakdown",)),
    ("implementation", "7. Implementation", ("code",)),
    ("code_review", "8. Code Review", ("code_review",)),
    ("testing", "9. Testing & QA", ("test_case", "test_report")),
    ("security", "10. Security",
     ("security_review", "security_finding", "threat_model", "sbom")),
    ("cicd", "11. CI/CD", ("cicd", "pipeline")),
    ("deployment", "12. Deployment", ("deployment", "release")),
]
_BACKLOG_TYPES = ("epic", "story", "task")


def _assess_phase(phase, types, by_type, *, has_backlog, intel_present):
    """Complete / Partial / Missing for one lifecycle phase, with its evidence artifacts.

    Published artifacts (or strong non-artifact evidence) → Complete; only drafts → Partial
    (registered, not yet adopted); nothing → Missing. Two phases carry non-document evidence
    the legacy agent assesses rather than generates: Task Breakdown from the accepted backlog,
    Implementation from the code itself (code intelligence proves the codebase exists)."""
    evidence = [a for t in types for a in by_type.get(t, [])]
    published = [a for a in evidence if a.status == "published"]
    strong = (phase == "task_breakdown" and has_backlog) or \
             (phase == "implementation" and intel_present)
    weak = (phase == "implementation" and intel_present)  # code exists but unverified vs docs
    if published or strong:
        status = "complete"
    elif evidence or weak:
        status = "partial"
    else:
        status = "missing"
    return status, evidence


def build_gap_report(*, tenant_id, project_id, object_store=None) -> dict:
    """Reconcile what onboarding discovered into a **gap report** (D7) and pick the resume
    phase. Assesses every lifecycle phase from the registered artifacts + code-intel + work
    items, then registers a *draft* `gap_report` artifact (published on the product_owner
    gate, #5) linked to the evidence it weighed. Builds on `register_atlassian` /
    `ingest_source_document` / 00c — it never re-creates content, only reports on it."""
    from apps.projects.models import Project
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem
    from storage import content_hash

    store = _object_store(object_store)
    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        artifacts = list(
            Artifact.objects.filter(tenant_id=tenant_id, project_id=project_id)
            .exclude(type="gap_report")  # don't assess prior reports as evidence
        )
        work_items = list(WorkItem.objects.filter(tenant_id=tenant_id, project_id=project_id))

    by_type: dict[str, list] = {}
    for a in artifacts:
        by_type.setdefault(a.type, []).append(a)
    has_backlog = any(w.type in _BACKLOG_TYPES for w in work_items)
    intel_present = bool(by_type.get("codebase_intelligence"))

    phases: list[dict] = []
    evidence_ids: list[str] = []
    for phase, label, types in _LIFECYCLE:
        status, evidence = _assess_phase(
            phase, types, by_type, has_backlog=has_backlog, intel_present=intel_present)
        # Light refs (id/type/sor/status), capped — enough for the REST read-through (T8) to
        # render "Evidence" without re-querying; never the artifact body.
        refs = [{"artifact_id": str(a.id), "type": a.type, "sor": a.sor, "status": a.status}
                for a in evidence[:10]]
        phases.append({"phase": phase, "label": label, "status": status,
                       "evidence_count": len(evidence), "evidence": refs})
        evidence_ids.extend(str(a.id) for a in evidence)

    resume = next((p["phase"] for p in phases if p["status"] != "complete"), "done")
    resume_label = next((p["label"] for p in phases if p["phase"] == resume), "Pipeline complete")
    # Blockers: phases still Missing at or before the resume point — they gate forward progress.
    resume_idx = next((i for i, p in enumerate(phases) if p["phase"] == resume), len(phases))
    blockers = [p["phase"] for p in phases[: resume_idx + 1] if p["status"] == "missing"]

    body = _render_gap_report(phases, resume_label, blockers, intel_present)
    body_key = f"onboarding/{tenant_id}/{project_id}/gap_report.md"
    store.put(body_key, body)
    report = tools.register_artifact(
        tenant_id, project_id, None, phase="onboarding", type="gap_report",
        sor="internal", content_hash=content_hash(body.encode("utf-8")), s3_key=body_key,
        external_ref={"source": "onboarding", "resume_phase": resume,
                      "phases": [{"phase": p["phase"], "label": p["label"], "status": p["status"],
                                 "evidence": p["evidence"]} for p in phases],
                      "blockers": blockers, "intel_present": intel_present},
    )
    # The report derives from the evidence it weighed (dedup; cap to keep the graph sane).
    for aid in list(dict.fromkeys(evidence_ids))[:200]:
        tools.add_trace_edge(tenant_id, report["id"], aid, "derives")
    tools.log_event(tenant_id, "onboarding", "gap_report.built", "artifact", report["id"],
                    {"resume_phase": resume, "blockers": blockers})
    return {"gap_report_id": report["id"], "resume_phase": resume, "phases": phases,
            "blockers": blockers, "intel_present": intel_present}


def _render_gap_report(phases, resume_label, blockers, intel_present) -> str:
    icon = {"complete": "Complete", "partial": "Partial", "missing": "Missing"}
    lines = [
        "# Onboarding Gap Report",
        "",
        "> Generated by the Onboarding Agent — what existed, what was registered, "
        "and what is still missing before the pipeline resumes.",
        "",
        f"**Code intelligence:** {'available' if intel_present else 'not run'}",
        f"**Recommended resume phase:** {resume_label}",
        "",
        "## Phase Completion Assessment",
        "",
        "| Phase | Status | Evidence |",
        "|-------|--------|----------|",
    ]
    lines += [f"| {p['label']} | {icon[p['status']]} | {p['evidence_count']} artifact(s) |"
              for p in phases]
    lines += ["", "## Blockers (resolve before resuming)", ""]
    lines += ([f"- **{b}** — no evidence found; generate via its phase agent (gated) "
               "or provide the source." for b in blockers] or ["- None."])
    return "\n".join(lines) + "\n"


# ── REST layer (P4.7-T8, backs S-24/S-25/S-26) ───────────────────────
def read_gap_report(*, tenant_id, project_id) -> dict | None:
    """Read-through the latest registered `gap_report` (S-26) — no recompute; `None` when
    none has been built yet. `POST .../gap-report/` (`build_gap_report`) is what (re)builds
    it; re-running after new evidence is registered is how the resume point moves."""
    from apps.projects.models import Project
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        report = (
            Artifact.objects.filter(tenant_id=tenant_id, project_id=project_id, type="gap_report")
            .order_by("-created_at").first()
        )
    if report is None:
        return None
    ext = report.external_ref or {}
    return {
        "gap_report_id": str(report.id),
        "resume_phase": ext.get("resume_phase"),
        "intel_present": ext.get("intel_present", False),
        "phases": [
            # assessment values are lowercase to match the frontend GapPhaseAssessment type:
            # "complete" | "partial" | "missing"  (never capitalised in the REST response)
            {"phase": p["phase"], "assessment": p["status"],
             "evidence": p.get("evidence", [])}
            for p in ext.get("phases", [])
        ],
        "blocking": ext.get("blockers", []),
    }


def record_code_intel_index(*, tenant_id, project_id, repo_id, index=None, summary="",
                            object_store=None) -> dict:
    """Persist a code-intel analysis as a `codebase_intelligence` artifact + Knowledge-Index
    chunk (S-24 step 3). The built-in analyzer runs in the companion worktree (D2); this call
    persists an **already-computed** result — it never touches the source (#1/#3). Real
    companion-side dispatch (claim → analyze → report) is deferred; see PHASE_4.7_BUILD_SPEC.md
    T8 implementation notes."""
    from apps.knowledge.index import index_artifact
    from apps.projects.models import Project, Repository
    from apps.tenancy.context import tenant_context
    from storage import content_hash

    index = index or {}
    store = _object_store(object_store)
    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        repo = Repository.objects.get(id=repo_id, tenant_id=tenant_id, project_id=project_id)

    text = summary.strip() if summary else f"Code intelligence index for {repo.name}."
    body = _render_code_intel_summary(repo.name, index, text)
    body_key = f"onboarding/{tenant_id}/{project_id}/code_intel/{repo.id}.md"
    store.put(body_key, body)
    artifact = tools.register_artifact(
        tenant_id, project_id, None, phase="context_extraction", type="codebase_intelligence",
        sor="internal", content_hash=content_hash(body.encode("utf-8")), s3_key=body_key,
        external_ref={"source": "code_intel", "repo": repo.name, **index}, repo_id=str(repo.id),
    )
    index_artifact(tenant_id=tenant_id, project_id=project_id, artifact_id=artifact["id"],
                   text=text, repo_id=str(repo.id), source="code_intel")
    tools.log_event(tenant_id, "onboarding", "code_intel.indexed", "artifact", artifact["id"],
                    {"repo_id": str(repo.id), "file_count": index.get("file_count")})
    return {"artifact_id": artifact["id"], "repo_id": str(repo.id), "status": "indexed"}


def _render_code_intel_summary(repo_name: str, index: dict, summary: str) -> str:
    return "\n".join([
        f"# Code Intelligence — {repo_name}", "", summary, "",
        f"- files: {index.get('file_count', '—')}",
        f"- commits: {index.get('commits', '—')}",
        f"- hotspots: {index.get('hotspots', '—')}",
        f"- languages: {index.get('languages', {})}",
    ]) + "\n"


def onboarding_hub(*, tenant_id, project_id) -> dict:
    """Hub state across upload/adopt/register/index/gap (S-24) — the one read the onboarding
    screen needs; every step's action already exists as its own endpoint."""
    from apps.integrations.models import IntegrationConnection, SourceDocument
    from apps.projects.models import Project
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        docs = list(SourceDocument.objects.filter(
            tenant_id=tenant_id, project_id=project_id).order_by("-created_at"))
        pages_registered = Artifact.objects.filter(
            tenant_id=tenant_id, project_id=project_id, sor="confluence").count()
        issues_registered = sum(
            1 for w in WorkItem.objects.filter(tenant_id=tenant_id, project_id=project_id)
            if (w.external_ref or {}).get("sor") == "jira"
        )
        intel_artifact = Artifact.objects.filter(
            tenant_id=tenant_id, project_id=project_id, type="codebase_intelligence"
        ).order_by("-created_at").first()
        connected = {
            cap: IntegrationConnection.objects.filter(
                tenant_id=tenant_id, capability=cap).first()
            for cap in ("docstore", "tasktracker")
        }

    gap = read_gap_report(tenant_id=tenant_id, project_id=project_id)
    return {
        "upload": [{"id": str(d.id), "filename": d.filename, "status": d.status} for d in docs],
        "adopt": [{"id": str(d.id), "filename": d.filename}
                 for d in docs if d.status == SourceDocument.Status.EXTRACTED],
        "register": {
            "docstore_connected": bool(
                connected["docstore"] and connected["docstore"].is_configured),
            "tasktracker_connected": bool(
                connected["tasktracker"] and connected["tasktracker"].is_configured),
            "pages_registered": pages_registered, "issues_registered": issues_registered,
        },
        "index": {
            "status": "indexed" if intel_artifact else "not_started",
            "artifact_id": str(intel_artifact.id) if intel_artifact else None,
        },
        "gap": {"ready": True, "resume_phase": gap["resume_phase"]} if gap else {"ready": False},
    }
