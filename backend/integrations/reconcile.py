"""Reconciliation (spec §4) — turn proposed WorkItems into SoR issues, idempotently.

`proposed → accepted`, **never duplicating**:
- a WorkItem already carrying `external_ref` is skipped (the primary idempotency guard);
- otherwise we search the tracker for an existing issue with the same summary and
  **register-don't-recreate** (blueprint B1), creating only when none exists.
Epics are reconciled before their stories before tasks so a child can reference its
parent's issue key. Each item is independent, so a partial failure is safe to re-run.
"""
from __future__ import annotations

from mcp_platform_state import tools

from .registry import get_capability, get_connection
from .types import ExternalRef

# WorkItem.type -> Jira issue type name.
_KIND = {"epic": "Epic", "story": "Story", "task": "Task"}
# Reconcile parents before children (epic → story → task) for parent linking.
_ORDER = {"epic": 0, "story": 1, "task": 2}


def _summary(work_item) -> str:
    return work_item.title or work_item.feature_stream or f"{work_item.type} {work_item.id}"


def _find_existing(tracker, project_key: str | None, summary: str) -> ExternalRef | None:
    """Register-don't-recreate: an existing issue with the exact summary (B1)."""
    if not project_key:
        return None
    safe = summary.replace('"', '\\"')
    hits = tracker.search(jql=f'project = "{project_key}" AND summary ~ "{safe}"')
    match = next((h for h in hits if h.summary == summary), None)
    if match is None:
        return None
    issue = tracker.get_issue(issue_ref=match.key)
    return ExternalRef(sor="jira", id=issue.key, url=issue.url)


def reconcile_work_item(*, tenant_id, tracker, work_item_id, project_key=None) -> dict:
    """Reconcile one WorkItem into a SoR issue (idempotent on external_ref)."""
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    with tenant_context(tenant_id):
        wi = WorkItem.objects.get(id=work_item_id, tenant_id=tenant_id)
        if wi.external_ref:  # already reconciled
            return {"work_item_id": str(wi.id), "external_ref": wi.external_ref,
                    "created": False, "skipped": True}
        summary, description = _summary(wi), wi.description or ""
        wi_type, kind = wi.type, _KIND.get(wi.type, "Task")
        parent_ref = None
        if wi.parent_id:
            parent = WorkItem.objects.get(id=wi.parent_id, tenant_id=tenant_id)
            parent_ref = (parent.external_ref or {}).get("id")

    # Jira hierarchy (Bugs S.No 142): a standard Task cannot be a child of a Story — only a
    # Sub-task can. So a platform task WITH a reconciled parent (its story) is created as a Sub-task
    # under it; a task with no (reconciled) parent stays a top-level Task with no parent. Epics and
    # stories are unaffected (Story-under-Epic via `parent` is valid).
    if wi_type == "task":
        if parent_ref:
            resolve = getattr(tracker, "subtask_type_name", None)
            kind = resolve() if callable(resolve) else "Subtask"
        else:
            parent_ref = None

    # Network calls happen outside the DB cursor.
    existing = _find_existing(tracker, project_key, summary)
    if existing is not None:
        ref, created = existing, False
    else:
        ref = tracker.create_issue(
            kind=kind, summary=summary, description=description, parent_ref=parent_ref
        )
        created = True

    with tenant_context(tenant_id):
        wi = WorkItem.objects.get(id=work_item_id, tenant_id=tenant_id)
        wi.external_ref = {"sor": ref.sor, "id": ref.id, "url": ref.url}
        wi.state = WorkItem.State.ACCEPTED
        wi.save(update_fields=["external_ref", "state", "updated_at"])
        tools.log_event(
            tenant_id, "reconciler", "workitem.reconciled", "work_item", str(wi.id),
            {"issue": ref.id, "created": created},
        )
    return {"work_item_id": str(work_item_id), "external_ref": wi.external_ref,
            "created": created, "skipped": False}


def reconcile_backlog(*, tenant_id, project_id, tracker=None, project_key=None) -> dict:
    """Reconcile every proposed WorkItem in a project into the tenant's TaskTracker."""
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    if tracker is None:
        tracker = get_capability(tenant_id, "tasktracker")
    if project_key is None:
        conn = get_connection(tenant_id, "tasktracker")
        project_key = (conn.scopes or {}).get("project_key") if conn else None

    with tenant_context(tenant_id):
        items = list(
            WorkItem.objects.filter(
                tenant_id=tenant_id, project_id=project_id,
                state=WorkItem.State.PROPOSED,
            )
        )
    items.sort(key=lambda w: _ORDER.get(w.type, 9))

    # Per-item isolation (Bugs S.No 143): a single item's SoR failure (e.g. a rejected Jira create)
    # must NOT abort the whole backlog or be silently swallowed — record it and keep going, so the
    # caller can report "N created, M failed: <reason>" honestly instead of a false "all published".
    results: list = []
    failed: list = []
    for w in items:
        try:
            results.append(reconcile_work_item(
                tenant_id=tenant_id, tracker=tracker,
                work_item_id=str(w.id), project_key=project_key,
            ))
        except Exception as exc:  # noqa: BLE001 — any connector/SoR error, reported not raised
            reason = str(getattr(exc, "detail", None) or exc) or exc.__class__.__name__
            failed.append({"work_item_id": str(w.id), "type": w.type, "error": reason[:300]})
            tools.log_event(
                tenant_id, "reconciler", "workitem.reconcile_failed", "work_item", str(w.id),
                {"error": reason[:300], "type": w.type},
            )
    return {
        "reconciled": len(results),
        "created": sum(1 for r in results if r["created"]),
        "failed": failed,
        "items": results,
    }
