"""Publish-to-SoR (spec §3) — on gate APPROVED, push an artifact to its system of record.

Resolves an artifact *type* to a capability (requirements/prd/architecture/adr →
docstore; everything else → internal, where the platform/S3 *is* the SoR). The DocStore
push is **idempotent**: re-publishing an artifact that already carries an `external_ref`
updates the same page (via `base_version`) instead of creating a duplicate.

`backlog → tasktracker` is intentionally not here — a backlog reconciles into Jira via
the Reconciliation service (next task), which is register-don't-recreate, not a 1:1 page.
"""
from __future__ import annotations

from .registry import get_capability, get_connection
from .types import ExternalRef

# artifact.type -> capability. Missing => internal SoR (no external push). The spec's
# default mapping; tenant/profile overrides can extend it later.
_TYPE_TO_CAPABILITY = {
    "requirements": "docstore",
    "prd": "docstore",
    "architecture": "docstore",
    "adr": "docstore",
}


def resolve_capability(artifact_type: str) -> str | None:
    return _TYPE_TO_CAPABILITY.get(artifact_type)


def render_html(body_md: str) -> str:
    """Artifact bodies are markdown; Confluence storage format is HTML (decision D4)."""
    import markdown

    return markdown.markdown(body_md or "", extensions=["fenced_code", "tables"])


def publish_doc(docstore, *, space: str, title: str, body_md: str,
                external_ref: dict | None = None) -> ExternalRef:
    """Pure create-or-update against a DocStore (idempotent on `external_ref`)."""
    html = render_html(body_md)
    if external_ref and external_ref.get("id"):
        return docstore.update_page(
            page_ref=external_ref["id"], title=title, body_html=html,
            base_version=int(external_ref.get("version") or 1),
        )
    return docstore.create_page(space=space, title=title, body_html=html)


def publish_to_docstore(*, tenant_id, artifact, body_md: str, title: str) -> ExternalRef:
    """Resolve the tenant's DocStore + space and publish. Raises CapabilityUnavailable
    when no connector is configured (the caller falls back to internal — blueprint B3)."""
    from django.conf import settings

    docstore = get_capability(tenant_id, "docstore")
    conn = get_connection(tenant_id, "docstore")
    space = (conn.scopes or {}).get("space_key") if conn else None
    space = space or settings.CONFLUENCE_SPACE_KEY
    return publish_doc(
        docstore, space=space, title=title, body_md=body_md,
        external_ref=artifact.external_ref,
    )
