"""Artifact preview read-through (P4.7-T10, backs S-28 list / S-29 preview, DECISION-5).

List payloads (`ArtifactSerializer`) only ever carry pointers — id/type/status/sor/version/
s3_key/content_hash. The body itself is fetched **on demand, read-through** here and never
persisted back onto the registry row (#1/#3: the platform owns state, not content):
  - `sor="internal"` (draft/staged, not yet pushed anywhere) → the S3 body at `s3_key`.
  - an external SoR (confluence/jira) → live through its capability (`DocStore.get_page` /
    `TaskTracker.get_issue`, themselves documented "read-through, not stored"), never the
    stored hash/pointer — if the connector is unavailable the pointer/version still return,
    just without a body (mirrors S-29's "Preview unavailable" state).
  - any other SoR (figma/xray/git/...) → no body capability yet; the SoR deep-link is
    still returned so the user can jump to the source.

`versions` is the artifact's sibling rows sharing (project, phase, type) — i.e. the distinct
registrations across runs/remediation loops — newest first. Note: only the single-instance
`api_contract` pattern (D4) bumps `version` on one row in place; most artifact types register
a fresh row per run with `version=1`, so today "versions" is a time-ordered list of revisions
rather than one row with a monotonically incrementing version — a real per-artifact version
counter across re-registrations is a future model change, not something this read-through
wrapper invents.
"""
from __future__ import annotations

_DOC_CONTENT_TYPE = "text/html"
_ISSUE_CONTENT_TYPE = "text/plain"
_INTERNAL_CONTENT_TYPE = "text/markdown"


def _object_store(injected):
    if injected is not None:
        return injected
    from storage import s3_from_settings

    return s3_from_settings()


def _versions(*, tenant_id, artifact) -> list[dict]:
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        siblings = Artifact.objects.filter(
            tenant_id=tenant_id, project_id=artifact.project_id,
            phase=artifact.phase, type=artifact.type,
        ).order_by("-created_at")
        return [
            {"artifact_id": str(a.id), "version": a.version, "status": a.status,
             "run_id": str(a.run_id) if a.run_id else None,
             "created_at": a.created_at.isoformat()}
            for a in siblings
        ]


_FORMAT_CONTENT_TYPE = {
    "markdown": "text/markdown",
    "md": "text/markdown",
    "html": "text/html",
    "text": "text/plain",
    "plain": "text/plain",
}


def _read_internal(artifact, object_store) -> tuple[str, str]:
    if artifact.s3_key:
        store = _object_store(object_store)
        body = store.get(artifact.s3_key).decode("utf-8")
        return body, _INTERNAL_CONTENT_TYPE
    # Some internal drafts are registered with the body inline in external_ref.body and no
    # s3_key yet (the agent hasn't staged a snapshot to S3). Read that draft body through
    # here — we don't copy it anywhere, it stays where it was registered (#1/#3).
    ref = artifact.external_ref or {}
    body = ref.get("body")
    if body:
        fmt = str(ref.get("format", "")).lower()
        return body, _FORMAT_CONTENT_TYPE.get(fmt, _INTERNAL_CONTENT_TYPE)
    return "", ""


def _read_confluence(tenant_id, artifact, get_capability) -> tuple[str, str, str | None]:
    ref = artifact.external_ref or {}
    link = ref.get("url")
    page_ref = ref.get("id")
    if not page_ref:
        return "", "", link
    try:
        docstore = get_capability(tenant_id, "docstore")
        page = docstore.get_page(page_ref=page_ref)
    except Exception:  # noqa: BLE001 — read-through is best-effort (S-29 "Preview unavailable")
        return "", "", link
    return page.body_html, _DOC_CONTENT_TYPE, page.url or link


def _read_jira(tenant_id, artifact, get_capability) -> tuple[str, str, str | None]:
    ref = artifact.external_ref or {}
    link = ref.get("url")
    issue_ref = ref.get("id") or ref.get("key")
    if not issue_ref:
        return "", "", link
    try:
        tasktracker = get_capability(tenant_id, "tasktracker")
        issue = tasktracker.get_issue(issue_ref=issue_ref)
    except Exception:  # noqa: BLE001 — read-through is best-effort
        return "", "", link
    body = f"{issue.summary}\n\nStatus: {issue.status}"
    return body, _ISSUE_CONTENT_TYPE, issue.url or link


def read_artifact_preview(*, tenant_id, artifact_id, object_store=None,
                          get_capability=None) -> dict | None:
    """The S-29 preview payload for one artifact, or `None` when it doesn't exist / has
    no body to show at all (internal with no `s3_key` ever stored)."""
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    if get_capability is None:
        from integrations.registry import get_capability as _gc
        get_capability = _gc

    with tenant_context(tenant_id):
        try:
            artifact = Artifact.objects.get(id=artifact_id, tenant_id=tenant_id)
        except Artifact.DoesNotExist:
            return None

        sor_link = None
        if artifact.sor == "internal":
            body, content_type = _read_internal(artifact, object_store)
            if not body:
                return None
        elif artifact.sor == "confluence":
            body, content_type, sor_link = _read_confluence(tenant_id, artifact, get_capability)
        elif artifact.sor == "jira":
            body, content_type, sor_link = _read_jira(tenant_id, artifact, get_capability)
        else:
            body, content_type = "", ""
            sor_link = (artifact.external_ref or {}).get("url")

        return {
            "body": body, "content_type": content_type, "status": artifact.status,
            "version": artifact.version,
            "versions": _versions(tenant_id=tenant_id, artifact=artifact),
            "sor_link": sor_link,
        }
