"""P1 — reconciliation service (proposed→accepted; idempotent, no duplicates)."""
import uuid

import pytest

from apps.projects.models import Project
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from integrations.reconcile import reconcile_backlog
from integrations.types import ExternalRef, Issue, IssueHit


class _FakeTracker:
    """In-memory TaskTracker: records creates; `existing` summaries register-don't-recreate."""

    def __init__(self, existing: dict | None = None):
        self._existing = existing or {}   # summary -> key
        self.created: list[dict] = []
        self._n = 0

    def search(self, *, jql):
        return [IssueHit(key=k, summary=s) for s, k in self._existing.items() if s in jql]

    def get_issue(self, *, issue_ref):
        return Issue(key=issue_ref, summary="", status="To Do", issue_type="Task",
                     url=f"https://x.atlassian.net/browse/{issue_ref}")

    def create_issue(self, *, kind, summary, description, parent_ref=None, fields=None):
        self._n += 1
        key = f"ST-{self._n}"
        self.created.append({"kind": kind, "summary": summary, "parent_ref": parent_ref})
        return ExternalRef(sor="jira", id=key, url=f"https://x.atlassian.net/browse/{key}")


class _SubtaskTracker(_FakeTracker):
    """A tracker that reports its sub-task issue-type name, like the real Atlassian one."""

    def subtask_type_name(self):
        return "Sub-task"


class _TaskFailsTracker(_FakeTracker):
    """Rejects Task/Sub-task creates (mimics Jira's 'invalid parent' 400) but lets epics/stories
    through — to prove per-item failures are captured, not aborting the whole backlog."""

    def create_issue(self, *, kind, summary, description, parent_ref=None, fields=None):
        if kind not in ("Epic", "Story"):
            raise RuntimeError("Please select valid parent issue.")
        return super().create_issue(kind=kind, summary=summary, description=description,
                                    parent_ref=parent_ref, fields=fields)


@pytest.fixture
def project(db):
    t = Tenant.objects.create(name="Acme")
    return Project.objects.create(tenant=t, name="Platform")


def _wi(project, *, type, title, state=WorkItem.State.PROPOSED, parent=None):
    return WorkItem.objects.create(
        tenant=project.tenant, project=project, type=type, title=title, state=state, parent=parent
    )


def test_reconcile_creates_issues_in_hierarchy_order(project):
    epic = _wi(project, type=WorkItem.Type.EPIC, title="Checkout epic")
    story = _wi(project, type=WorkItem.Type.STORY, title="Add to cart", parent=epic)
    tracker = _FakeTracker()

    out = reconcile_backlog(
        tenant_id=str(project.tenant_id), project_id=str(project.id),
        tracker=tracker, project_key="ST",
    )

    assert out == {"reconciled": 2, "created": 2, "failed": [], "items": out["items"]}
    # Epic created before the story; the story references the epic's new key.
    assert [c["kind"] for c in tracker.created] == ["Epic", "Story"]
    assert tracker.created[1]["parent_ref"] == "ST-1"

    epic.refresh_from_db()
    story.refresh_from_db()
    assert epic.state == WorkItem.State.ACCEPTED and epic.external_ref["id"] == "ST-1"
    assert story.state == WorkItem.State.ACCEPTED and story.external_ref["id"] == "ST-2"


def test_task_under_story_becomes_a_subtask(project):
    """Bugs S.No 142: a platform task with a story parent must be created as a Jira SUB-TASK under
    that story (Jira rejects a plain Task parented to a Story), using the project's sub-task type."""
    epic = _wi(project, type=WorkItem.Type.EPIC, title="E")
    story = _wi(project, type=WorkItem.Type.STORY, title="S", parent=epic)
    task = _wi(project, type=WorkItem.Type.TASK, title="T", parent=story)
    tracker = _SubtaskTracker()

    reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                      tracker=tracker, project_key="ST")

    created = {c["summary"]: c for c in tracker.created}
    assert created["T"]["kind"] == "Sub-task"          # resolved sub-task type
    assert created["T"]["parent_ref"] == created["S"]["parent_ref"] or created["T"]["parent_ref"]
    # the task's parent is the story's key (ST-2), not the epic
    assert created["T"]["parent_ref"] == "ST-2"
    task.refresh_from_db()
    assert task.state == WorkItem.State.ACCEPTED


def test_parentless_task_stays_a_task_with_no_parent(project):
    """A top-level task (no reconciled parent) can't be a sub-task (Jira sub-tasks require a
    parent) — it's created as a plain Task with no parent."""
    task = _wi(project, type=WorkItem.Type.TASK, title="Standalone")
    tracker = _SubtaskTracker()

    reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                      tracker=tracker, project_key="ST")

    assert tracker.created[0]["kind"] == "Task"
    assert tracker.created[0]["parent_ref"] is None


def test_repo_assigned_task_is_not_mistaken_for_already_reconciled(project):
    """Bugs S.No 142 (real root cause): a multi-repo task carries external_ref.repo_assignment
    (the planner's repo pick) with NO SoR id. Reconcile must still push it (not treat it as
    already-reconciled), and must PRESERVE the repo_assignment alongside the new Jira ref."""
    epic = _wi(project, type=WorkItem.Type.EPIC, title="E")
    story = _wi(project, type=WorkItem.Type.STORY, title="S", parent=epic)
    task = _wi(project, type=WorkItem.Type.TASK, title="T", parent=story)
    task.external_ref = {"repo_assignment": {"suggested_repo_id": "repo-1", "source": "agent"}}
    task.save(update_fields=["external_ref"])
    tracker = _SubtaskTracker()

    out = reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                            tracker=tracker, project_key="ST")

    assert out["created"] == 3          # epic + story + the task (NOT skipped)
    task.refresh_from_db()
    assert task.external_ref.get("id")                       # got a Jira key
    assert task.external_ref["repo_assignment"]["suggested_repo_id"] == "repo-1"  # preserved
    assert task.state == WorkItem.State.ACCEPTED


def test_per_item_failure_is_captured_not_aborted(project):
    """Bugs S.No 143: one item's SoR rejection must not abort the backlog or be swallowed — the
    epic/story still land and the failed task is reported in `failed`."""
    epic = _wi(project, type=WorkItem.Type.EPIC, title="E")
    story = _wi(project, type=WorkItem.Type.STORY, title="S", parent=epic)
    _wi(project, type=WorkItem.Type.TASK, title="T", parent=story)
    tracker = _TaskFailsTracker()

    out = reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                            tracker=tracker, project_key="ST")

    assert out["created"] == 2 and out["reconciled"] == 2      # epic + story landed
    assert len(out["failed"]) == 1 and out["failed"][0]["type"] == "task"
    assert "valid parent" in out["failed"][0]["error"]


def test_reconcile_is_idempotent(project):
    _wi(project, type=WorkItem.Type.STORY, title="A story")
    tracker = _FakeTracker()

    first = reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                              tracker=tracker, project_key="ST")
    second = reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                               tracker=tracker, project_key="ST")

    assert first["created"] == 1
    # Re-run finds nothing proposed (all accepted) and creates nothing new.
    assert second == {"reconciled": 0, "created": 0, "failed": [], "items": []}
    assert len(tracker.created) == 1


def test_reconcile_registers_existing_without_duplicating(project):
    _wi(project, type=WorkItem.Type.STORY, title="Existing story")
    tracker = _FakeTracker(existing={"Existing story": "ST-77"})

    out = reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                            tracker=tracker, project_key="ST")

    assert out["created"] == 0           # registered, not created
    assert tracker.created == []         # never called create_issue
    wi = WorkItem.objects.get(title="Existing story")
    assert wi.external_ref["id"] == "ST-77" and wi.state == WorkItem.State.ACCEPTED


def test_reconcile_only_touches_proposed(project):
    _wi(project, type=WorkItem.Type.STORY, title="Already done",
        state=WorkItem.State.IN_PROGRESS)
    tracker = _FakeTracker()

    out = reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                            tracker=tracker, project_key="ST")

    assert out["reconciled"] == 0 and tracker.created == []


# ── live reconciliation against real Jira (runs only with creds) ────
def _live_config():
    from integrations.atlassian.config import AtlassianConfig

    cfg = AtlassianConfig.from_settings()
    return cfg if cfg.configured else None


@pytest.mark.skipif(_live_config() is None, reason="Atlassian creds not configured in .env")
@pytest.mark.django_db
def test_reconcile_backlog_live_creates_real_issues():
    from django.conf import settings

    from integrations.atlassian.tasktracker import AtlassianTaskTracker

    cfg = _live_config()
    project_key = settings.JIRA_PROJECT_KEY
    tracker = AtlassianTaskTracker(cfg, project=project_key)

    t = Tenant.objects.create(name="Reconcile Co")
    project = Project.objects.create(tenant=t, name="Greenfield")
    marker = uuid.uuid4().hex[:8]
    epic = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.EPIC,
                                   title=f"smoke epic {marker}", state=WorkItem.State.PROPOSED)
    WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY,
                            title=f"smoke story {marker}", state=WorkItem.State.PROPOSED,
                            parent=epic)

    created_keys: list[str] = []
    try:
        out = reconcile_backlog(tenant_id=str(t.id), project_id=str(project.id),
                                tracker=tracker, project_key=project_key)
        assert out["reconciled"] == 2 and out["created"] == 2
        for wi in WorkItem.objects.filter(project=project):
            wi.refresh_from_db()
            assert wi.state == WorkItem.State.ACCEPTED
            assert wi.external_ref["id"].startswith(f"{project_key}-")
            created_keys.append(wi.external_ref["id"])

        # Idempotent: a second run creates nothing new.
        again = reconcile_backlog(tenant_id=str(t.id), project_id=str(project.id),
                                  tracker=tracker, project_key=project_key)
        assert again["created"] == 0
    finally:
        for key in reversed(created_keys):  # children before parents
            try:
                tracker.delete_issue(issue_ref=key, delete_subtasks=True)
            except Exception:  # noqa: BLE001  (best-effort cleanup)
                pass
