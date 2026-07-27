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

from urllib.parse import parse_qs, urlparse

from mcp_platform_state import tools

from .extract import extract
from .registry import get_capability, get_connection
from .types import CapabilityUnavailable


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
    # B1-3: register the artifact + flip the doc to EXTRACTED as one unit. If anything fails we
    # never leave a half-written ingest — the doc is marked FAILED and any orphaned artifact +
    # extracted body are removed, so a retry starts clean.
    artifact = None
    try:
        artifact = tools.register_artifact(
            tenant_id, project_id, None, phase="onboarding", type=artifact_type,
            sor="internal", content_hash=content_hash(body.encode("utf-8")), s3_key=body_key,
            title=title,  # B1-2: carry the extracted title onto the artifact
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
    except Exception:
        from apps.registry.models import Artifact
        with tenant_context(tenant_id):
            SourceDocument.objects.filter(id=src.id, tenant_id=tenant_id).update(
                status=SourceDocument.Status.FAILED, s3_key=src_key)
            if artifact is not None:
                Artifact.objects.filter(id=artifact["id"], tenant_id=tenant_id).delete()
        try:
            store.delete(body_key)
        except Exception:
            pass
        raise
    return {"source_document_id": str(src.id), "status": "extracted",
            "artifact_ids": [artifact["id"]], "title": title}


def adopt_source_document(*, tenant_id, source_document_id, user_id, target_type=None) -> dict:
    """Review gate: a product_owner publishes the extracted draft artifacts (idempotent).

    Brownfield B2-1 — the human classifies the document here: `target_type` (one of
    ``ADOPTABLE_ARTIFACT_TYPES``) reclassifies the generic extracted ``document`` into its real
    lifecycle type so the gap report recognises it as phase evidence. When omitted, the artifact
    keeps its current type (backward-compatible with pre-B2-1 callers)."""
    from apps.integrations.models import SourceDocument
    from apps.tenancy.context import tenant_context
    from apps.tenancy.models import Membership, User

    if target_type is not None and target_type not in ADOPTABLE_ARTIFACT_TYPES:
        raise OnboardingError(
            f"invalid target_type '{target_type}'; expected one of {ADOPTABLE_ARTIFACT_TYPES}"
        )

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
        tools.update_artifact(tenant_id, aid, status="published", type=target_type)
    with tenant_context(tenant_id):
        src = SourceDocument.objects.get(id=source_document_id, tenant_id=tenant_id)
        src.status = SourceDocument.Status.ADOPTED
        src.save(update_fields=["status", "updated_at"])
        tools.log_event(tenant_id, f"user:{user_id}", "source_document.adopted",
                        "source_document", str(src.id),
                        {"artifact_ids": artifact_ids, "target_type": target_type})
    return {"source_document_id": str(source_document_id), "status": "adopted",
            "artifact_ids": artifact_ids, "target_type": target_type}


# ── Atlassian register-don't-recreate ───────────────────────────────
_ISSUE_TYPE = {"Epic": "epic", "Story": "story", "Task": "task",
               "Sub-task": "task", "Subtask": "task"}


def register_atlassian(*, tenant_id, project_id, tasktracker=None, project_key=None) -> dict:
    """Import an existing **Jira backlog** as work-item pointers, creating nothing in Jira (B1).

    Brownfield redesign (B3-1/B3-4): this no longer crawls the whole Confluence space. A backlog
    is meant to arrive whole, so Jira stays a bulk import; but a Confluence space of hundreds of
    pages can't be auto-typed, and crawling it registered every page as an untyped `document`
    that the gap report ignores. Confluence docs are now linked individually + typed via
    `link_confluence_pages` (B3-4). Graceful (B3-1): if Jira isn't connected this **skips**
    (no error) and reports it — mirroring the publish path — so onboarding never hits a dead-end
    400; the hub drives the "connect Jira" affordance from the connection status instead."""
    from apps.projects.models import Project
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    if tasktracker is None:
        try:
            tasktracker = get_capability(tenant_id, "tasktracker")
        except CapabilityUnavailable:
            return {"registered_issues": [], "tasktracker_connected": False}
    if project_key is None:
        conn = get_connection(tenant_id, "tasktracker")
        project_key = (conn.scopes or {}).get("project_key") if conn else None

    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        existing_issues = {
            (w.external_ref or {}).get("id")
            for w in WorkItem.objects.filter(tenant_id=tenant_id, project_id=project_id)
            if w.external_ref
        }

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

    return {"registered_issues": registered_issues, "tasktracker_connected": True}


def _parse_confluence_page_id(raw: str) -> str | None:
    """Extract a Confluence page id from a pasted link or a bare id (B3-4). Handles Cloud
    (`/wiki/spaces/<SPACE>/pages/<id>/<slug>` or `.../pages/<id>`) and Server/DC
    (`viewpage.action?pageId=<id>`); a bare numeric id passes through. Returns `None` if no id
    can be found — the caller then shows a "paste the full URL or the page ID" error. "Tiny"
    share links (`/x/<code>`) can't be resolved offline, so those fall back to that message."""
    if not raw:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return raw
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    # Server/DC: ...viewpage.action?pageId=12345
    page_id_qs = parse_qs(parsed.query or "").get("pageId", [])
    if page_id_qs and page_id_qs[0].isdigit():
        return page_id_qs[0]
    # Cloud: .../pages/<id>/<slug> — the numeric segment immediately after "pages".
    segments = [s for s in (parsed.path or "").split("/") if s]
    for i, seg in enumerate(segments):
        if seg == "pages" and i + 1 < len(segments) and segments[i + 1].isdigit():
            return segments[i + 1]
    return None


def link_confluence_pages(*, tenant_id, project_id, links, docstore=None) -> dict:
    """B3-4 — register user-provided Confluence pages as **typed** pointers so the gap report
    sees them as phase evidence. Each `links` row = `{"page": <url-or-id>, "type": <canonical
    lifecycle type>}`. Register-don't-recreate: stores a pointer (id/url/title), never the page
    body; idempotent by page id (re-linking updates the declared type, never duplicates). Shares
    the canonical type set (`ADOPTABLE_ARTIFACT_TYPES`) + the typed-registration path with
    uploaded-doc adoption (B2-1) — one classification path, two sources. Per-row errors are
    collected, not raised, so one bad link doesn't fail the whole batch."""
    from apps.projects.models import Project
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    if docstore is None:
        # No docstore connector → CapabilityUnavailable, mapped to a friendly 4xx at the view.
        docstore = get_capability(tenant_id, "docstore")

    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        existing = {
            (a.external_ref or {}).get("id"): a
            for a in Artifact.objects.filter(
                tenant_id=tenant_id, project_id=project_id, sor="confluence")
        }

    linked: list[dict] = []
    errors: list[dict] = []
    for row in links:
        raw = (row or {}).get("page", "")
        target_type = (row or {}).get("type", "")
        if target_type not in ADOPTABLE_ARTIFACT_TYPES:
            errors.append({"page": raw, "error": f"unknown type {target_type!r}"})
            continue
        page_id = _parse_confluence_page_id(raw)
        if not page_id:
            errors.append({"page": raw,
                           "error": "couldn't find that page — paste the full URL or the page ID"})
            continue
        try:
            page = docstore.get_page(page_ref=page_id)
        except Exception:  # noqa: BLE001 — per-row error; don't fail the batch
            errors.append({"page": raw, "error": "couldn't read that page from Confluence"})
            continue
        existing_art = existing.get(page_id)
        if existing_art is not None:
            # Idempotent: update the declared type on the existing pointer, never duplicate.
            tools.update_artifact(tenant_id, str(existing_art.id),
                                  status="published", type=target_type)
            linked.append({"page_id": page_id, "artifact_id": str(existing_art.id),
                           "type": target_type, "title": page.title, "created": False})
            continue
        art = tools.register_artifact(
            tenant_id, project_id, None, phase="onboarding", type=target_type,
            sor="confluence", content_hash="",
            external_ref={"sor": "confluence", "id": page_id, "url": page.url,
                          "title": page.title},
        )
        tools.update_artifact(tenant_id, art["id"], status="published")
        linked.append({"page_id": page_id, "artifact_id": art["id"], "type": target_type,
                       "title": page.title, "created": True})

    return {"linked": linked, "errors": errors}


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

# Brownfield B2-1: the lifecycle phases a human can classify an *uploaded document* as at the
# adopt gate. Derived from _LIFECYCLE (the FIRST/primary type of each document-authored phase) so
# every adoptable type is one the gap-report assessor already recognises — a single source of
# truth, so the two can never drift apart. Code/test/security/cicd/deployment phases are produced
# by agent runs, not uploaded, so they are intentionally excluded.
_ADOPTABLE_DOC_PHASES = ("ideation", "requirements", "prd", "architecture", "ux_design")
ADOPTABLE_ARTIFACT_TYPES = tuple(
    types[0] for phase, _label, types in _LIFECYCLE if phase in _ADOPTABLE_DOC_PHASES
)


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
    # Keep the registry POINTER lean — scalar summary only; the rich detail (hotspot files, dead
    # code, decisions) lives in the body in S3, never bloating the external_ref (#3).
    ref_summary = {k: index[k] for k in ("file_count", "commits", "hotspots", "authors",
                                         "communities", "languages") if k in index}
    artifact = tools.register_artifact(
        tenant_id, project_id, None, phase="context_extraction", type="codebase_intelligence",
        sor="internal", content_hash=content_hash(body.encode("utf-8")), s3_key=body_key,
        external_ref={"source": "code_intel", "repo": repo.name, **ref_summary},
        repo_id=str(repo.id),
    )
    # Index the rich rendered body (not just the one-line summary) so the hotspot files, dead
    # code and decisions are retrievable knowledge for downstream agents.
    index_artifact(tenant_id=tenant_id, project_id=project_id, artifact_id=artifact["id"],
                   text=body, repo_id=str(repo.id), source="code_intel")
    tools.log_event(tenant_id, "onboarding", "code_intel.indexed", "artifact", artifact["id"],
                    {"repo_id": str(repo.id), "file_count": index.get("file_count")})
    return {"artifact_id": artifact["id"], "repo_id": str(repo.id), "status": "indexed"}


_LANG_NAMES = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript (React)", ".js": "JavaScript",
    ".jsx": "JavaScript (React)", ".go": "Go", ".java": "Java", ".rb": "Ruby",
    ".rs": "Rust", ".kt": "Kotlin",
}


def _fmt_languages(languages: dict) -> str:
    """A readable language breakdown from the analyzer's `{'.py': 4}` extension counts."""
    if not languages:
        return "—"
    return ", ".join(f"{_LANG_NAMES.get(ext, ext)} ({cnt})"
                     for ext, cnt in sorted(languages.items(), key=lambda kv: -kv[1]))


def _dead_name(entry) -> str:
    if isinstance(entry, dict):
        return entry.get("file") or entry.get("path") or next(iter(entry.values()), "?")
    return str(entry)


def _render_code_intel_summary(repo_name: str, index: dict, summary: str) -> str:
    """Render the code-intelligence index into a human-readable report that shows the analyzer's
    real depth — the five intelligence layers (git activity · architecture/dependency graph · risk
    hotspots · dead code · decision archaeology) — not just counts. Degrades gracefully to a basic
    summary when only counts were reported (older/thin payloads)."""
    g = index.get
    lines = [
        f"# Code Intelligence — {repo_name}", "",
        summary or ("Static analysis of the existing codebase — computed on your companion in a "
                    "read-only worktree; only this index is stored, never your source."),
        "",
        "## Overview", "",
        f"- **Files analysed:** {g('file_count', '—')}",
        (f"- **Commits:** {g('commits', '—')}"
         + (f" · **Authors:** {g('authors')}" if g("authors") is not None else "")),
        f"- **Languages:** {_fmt_languages(g('languages') or {})}",
    ]
    entry_points = g("entry_points") or []
    if entry_points:
        shown = ", ".join(f"`{e}`" for e in entry_points[:8])
        lines.append(f"- **Entry points:** {shown}" + (" …" if len(entry_points) > 8 else ""))

    # Architecture — dependency communities + the most-depended-on modules (PageRank).
    communities, top_modules = g("communities"), g("top_modules") or []
    if communities is not None or top_modules:
        lines += ["", "## Architecture", ""]
        if communities is not None:
            lines.append(f"- **Cohesive modules (dependency communities):** {communities}")
        if top_modules:
            lines.append("- **Most-depended-on files (PageRank):**")
            lines += [f"  - `{m}`" for m in top_modules[:8]]

    # Risk hotspots — churn × complexity (Tornhill), the highest-signal quality indicator.
    hotspots = g("hotspot_files") or []
    if hotspots:
        lines += ["", "## Risk hotspots (churn × complexity)", "",
                  "| File | Score | Churn | Complexity |", "|------|------:|------:|-----------:|"]
        lines += [f"| `{h.get('file', '?')}` | {h.get('score', '—')} | "
                  f"{h.get('churn', '—')} | {h.get('complexity', '—')} |" for h in hotspots[:10]]

    # Dead code — files nothing imports (excluding entry points).
    dead = g("dead_code") or []
    if dead:
        names = [_dead_name(d) for d in dead]
        lines += ["", f"## Likely dead code ({len(names)})", ""]
        lines += [f"- `{n}`" for n in names[:15]]
        if len(names) > 15:
            lines.append(f"- …and {len(names) - 15} more")

    # Decision archaeology — ADRs + notable commit messages.
    decisions = g("decisions") or []
    if decisions:
        lines += ["", f"## Decisions found ({len(decisions)})", ""]
        for d in decisions[:10]:
            title = d.get("title") or d.get("ref") or "decision"
            ref = d.get("ref", "")
            lines.append(f"- {title}" + (f" ({ref})" if ref and ref != title else ""))

    # Thin/older payload (counts only) — surface the hotspot count so the body is never bare.
    if not hotspots and g("hotspots") is not None:
        lines += ["", f"- **Hotspots:** {g('hotspots')}"]

    return "\n".join(lines) + "\n"


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
