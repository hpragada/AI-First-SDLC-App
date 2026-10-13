"""Reconciliation (spec §4) — turn planned WorkItems into SoR issues, idempotently.

**Never duplicating**, and never rewriting history:
- a WorkItem whose recorded issue key still RESOLVES in the tracker is skipped (the primary
  idempotency guard); a key naming an issue the tracker says is gone is treated as stale and
  the item is re-created (Bugs S.No 236);
- otherwise we search the tracker for an existing issue with the same summary and
  **register-don't-recreate** (blueprint B1), creating only when none exists;
- `proposed → accepted` is the only state promotion made here. An item already in progress,
  in review, blocked or done keeps its state (Bugs S.No 237).
Epics are reconciled before their stories before tasks so a child can reference its
parent's issue key. Each item is independent, so a partial failure is safe to re-run.
"""
from __future__ import annotations

from mcp_platform_state import tools

from .registry import get_capability, get_connection
from .types import CapabilityError, ExternalRef

# WorkItem.type -> Jira issue type name.
_KIND = {"epic": "Epic", "story": "Story", "task": "Task"}
# Reconcile parents before children (epic → story → task) for parent linking.
_ORDER = {"epic": 0, "story": 1, "task": 2}

# The ONLY upstream statuses that mean "this issue is gone" (Bugs S.No 236). Everything else —
# 401/403 (token expired, permission changed), 429 (throttled), 5xx (Jira is down) — means "we
# could not tell", and the pointer MUST be left alone. Reading an outage as "deleted" would
# clear every pointer in the project in a single pass and re-create the whole backlog as
# duplicate issues, which is far worse than the stale pointer this check exists to find.
_GONE_STATUSES = frozenset({404, 410})


def _summary(work_item) -> str:
    return work_item.title or work_item.feature_stream or f"{work_item.type} {work_item.id}"


def _pointer_is_gone(tracker, issue_ref: str) -> bool:
    """True only when the tracker positively reports the issue no longer exists.

    Any other failure returns False — "could not tell" is never "deleted". See _GONE_STATUSES.
    """
    try:
        tracker.get_issue(issue_ref=issue_ref)
    except CapabilityError as exc:
        return exc.status in _GONE_STATUSES
    except Exception:  # noqa: BLE001 — a transport/connection failure is not evidence of deletion
        return False
    return False


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
        # Idempotency = a real SoR issue key already recorded (external_ref.id). NOT just any
        # external_ref: a multi-repo work item carries external_ref.repo_assignment (the planner's
        # repo suggestion, Option C) with NO SoR id — treating that as "already reconciled" made
        # every repo-assigned task skip the Jira push entirely (Bugs S.No 142, real root cause).
        existing_id = (wi.external_ref or {}).get("id")
        summary, description = _summary(wi), wi.description or ""
        wi_type, kind = wi.type, _KIND.get(wi.type, "Task")
        parent_ref = None
        if wi.parent_id:
            parent = WorkItem.objects.get(id=wi.parent_id, tenant_id=tenant_id)
            parent_ref = (parent.external_ref or {}).get("id")

    # A recorded key is only idempotency evidence while the issue it names still EXISTS
    # (Bugs S.No 236). Deleting an issue in Jira used to leave the platform holding a dead key
    # for ever: nothing ever re-checked it, so the item was skipped on every future pass and the
    # work silently fell out of the tracker with no detection and no repair path. Ask the tracker
    # — through the vendor-free capability, never a Jira-specific call.
    if existing_id:
        if not _pointer_is_gone(tracker, existing_id):
            return {"work_item_id": str(work_item_id), "external_ref": wi.external_ref,
                    "created": False, "skipped": True}
        tools.log_event(
            tenant_id, "reconciler", "workitem.pointer_stale", "work_item", str(work_item_id),
            {"issue": existing_id, "reason": "issue no longer exists in the tracker"},
        )

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
        # Merge, don't overwrite — keep any repo_assignment (multi-repo) alongside the new SoR ref.
        wi.external_ref = {**(wi.external_ref or {}), "sor": ref.sor, "id": ref.id, "url": ref.url}
        # Exporting an item to the tracker must NEVER move it backwards (Bugs S.No 237, the rule
        # the team pinned). `proposed → accepted` is the only promotion this service makes; an
        # item already in progress, in review, blocked or done keeps the state it earned. Before
        # candidate selection stopped filtering on `state=proposed` this line could only ever see
        # proposed items, so forcing ACCEPTED was harmless; now it would rewrite live history —
        # which is exactly the damage the July recovery needed a snapshot/rewind script to undo.
        fields = ["external_ref", "updated_at"]
        if wi.state == WorkItem.State.PROPOSED:
            wi.state = WorkItem.State.ACCEPTED
            fields.append("state")
        wi.save(update_fields=fields)
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

    # Register-don't-recreate needs the project key to search with. Without it `_find_existing`
    # returns None for everything and the export creates blind — it would happily make a second
    # copy of every issue that already exists. Refuse rather than duplicate a whole backlog.
    if not project_key:
        return {
            "reconciled": 0, "created": 0, "skipped": 0, "items": [],
            "failed": [{"work_item_id": None, "type": None, "error": (
                "No Jira project key is configured for this workspace. Exporting without one "
                "cannot check whether an issue already exists, so it would create duplicates. "
                "Set the project key on the task-tracker connection and export again."
            )}],
        }

    with tenant_context(tenant_id):
        # Candidates are the backlog items, whatever state they are in (Bugs S.No 237).
        # Filtering on `state=proposed` meant that the moment work started, the item became
        # permanently un-exportable: 70 of SpendLog's 109 items could never reach Jira, because
        # being worked on is not a reason to be untracked. Exporting is safe at any stage now
        # that the state is preserved rather than forced (see reconcile_work_item).
        #
        # Restricted to the three planned types on purpose. WorkItem also holds DEFECTs and
        # TEST_CASEs, which are created directly in `in_progress` by the QA loop and were
        # therefore never in scope here; dropping the state filter without this one would push
        # every defect and test case in the project into Jira as a generic "Task" — hundreds of
        # rows nobody asked for, mislabelled, on the next task-breakdown export.
        #
        # `cancelled` is the ONE state that is still a reason to be untracked (S.No 140, team
        # decision 8 Sep 2026). It says "we have decided this is not happening", so filing a
        # tracker ticket for it creates work the team just took off its own board — arriving in
        # the sprint backlog looking like any other new ticket, with nothing on it saying it was
        # cancelled, ready for somebody to pick up. Two fixes in one batch disagreed here: this
        # query stopped filtering on state (S.No 237) before `cancelled` existed (S.No 140).
        #
        # `cancelled` ONLY — deliberately not `TERMINAL_STATES`. Excluding `done` too would undo
        # S.No 237: finished work with no tracker id is exactly what could never be exported
        # before, and `test_export_never_moves_an_item_backwards` pins that a done item may be
        # exported and stays done. Abandoned and finished are different facts (models.py:40).
        items = list(
            WorkItem.objects.filter(
                tenant_id=tenant_id, project_id=project_id, type__in=list(_KIND),
            ).exclude(state=WorkItem.State.CANCELLED)
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
        # Already-tracked items are now candidates too (their pointers get re-validated), so say
        # how many were left alone rather than letting them inflate "reconciled" silently.
        "skipped": sum(1 for r in results if r["skipped"]),
        "failed": failed,
        "items": results,
    }
