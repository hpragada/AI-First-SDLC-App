"""Brownfield-lite onboarding (spec §6 / B4) — bring an existing single-repo project
onto the platform two ways, register-don't-recreate:

1. **Static-file extraction:** upload Word/Excel/PDF → store the original in S3 → extract
   to markdown → register a *draft* internal artifact (provenance to the original) →
   **review gate** (`adopt`, product_owner) publishes it. Extraction is lossy/untrusted,
   so adoption is human-gated (#5).
2. **Atlassian register-don't-recreate:** discover existing Confluence pages + Jira issues
   and register *pointers* (never create) — they're already the live SoR, so they're
   indexed as published artifacts / accepted work items. Idempotent by external_ref.
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
    from apps.tenancy.models import Membership

    with tenant_context(tenant_id):
        src = SourceDocument.objects.get(id=source_document_id, tenant_id=tenant_id)
        artifact_ids = [str(x) for x in src.extracted_artifact_ids]
        if src.status == SourceDocument.Status.ADOPTED:
            return {"source_document_id": str(src.id), "status": "adopted",
                    "artifact_ids": artifact_ids, "idempotent": True}
        if src.status != SourceDocument.Status.EXTRACTED:
            raise OnboardingError(f"not ready for adoption (status={src.status})")
        has_role = Membership.objects.filter(
            tenant_id=tenant_id, user_id=user_id, project_id=src.project_id,
            role="product_owner",
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
