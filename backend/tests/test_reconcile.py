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

    assert out == {"reconciled": 2, "created": 2, "items": out["items"]}
    # Epic created before the story; the story references the epic's new key.
    assert [c["kind"] for c in tracker.created] == ["Epic", "Story"]
    assert tracker.created[1]["parent_ref"] == "ST-1"

    epic.refresh_from_db()
    story.refresh_from_db()
    assert epic.state == WorkItem.State.ACCEPTED and epic.external_ref["id"] == "ST-1"
    assert story.state == WorkItem.State.ACCEPTED and story.external_ref["id"] == "ST-2"


def test_reconcile_is_idempotent(project):
    _wi(project, type=WorkItem.Type.STORY, title="A story")
    tracker = _FakeTracker()

    first = reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                              tracker=tracker, project_key="ST")
    second = reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                               tracker=tracker, project_key="ST")

    assert first["created"] == 1
    # Re-run finds nothing proposed (all accepted) and creates nothing new.
    assert second == {"reconciled": 0, "created": 0, "items": []}
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
