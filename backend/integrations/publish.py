"""Publish-to-SoR (spec §3) — push a gate-approved artifact to its system of record.

Export is USER-triggered (team flow decision, 2026-07-07): gate approval publishes
internally only; the manual publish endpoint pushes on demand, governed by the
phase-scoped export policy in `integrations.export_policy`. The DocStore push is
**idempotent**: re-publishing an artifact that already carries an `external_ref`
updates the same page (via `base_version`) instead of creating a duplicate.

`backlog → tasktracker` is intentionally not here — a backlog reconciles into Jira via
the Reconciliation service, which is register-don't-recreate, not a 1:1 page.
"""
from __future__ import annotations

from .registry import get_capability, get_connection
from .types import ExternalRef


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


def publish_to_docstore(*, tenant_id, artifact, body_md: str, title: str,
                        space: str | None = None) -> ExternalRef:
    """Resolve the tenant's DocStore + space and publish. Raises CapabilityUnavailable
    when no connector is configured (the caller falls back to internal — blueprint B3).
    `space` overrides the connector/default space (S-34 manual publish destination)."""
    from django.conf import settings

    docstore = get_capability(tenant_id, "docstore")
    conn = get_connection(tenant_id, "docstore")
    resolved = space or ((conn.scopes or {}).get("space_key") if conn else None)
    resolved = resolved or settings.CONFLUENCE_SPACE_KEY
    return publish_doc(
        docstore, space=resolved, title=title, body_md=body_md,
        external_ref=artifact.external_ref,
    )
