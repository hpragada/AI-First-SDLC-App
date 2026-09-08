"""P1 — reconciliation service (proposed→accepted; idempotent, no duplicates)."""
import uuid

import pytest

from apps.projects.models import Project
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from integrations.reconcile import reconcile_backlog
from integrations.types import CapabilityError, ExternalRef, Issue, IssueHit


class _FakeTracker:
    """In-memory TaskTracker: records creates; `existing` summaries register-don't-recreate.

    `gone` is the set of issue keys the tracker reports as deleted (404), and `unreachable`
    the status it raises for every key instead — the two halves of the S.No 236 pointer check.
    """

    def __init__(self, existing: dict | None = None, gone: set | None = None,
                 unreachable: int | None = None):
        self._existing = existing or {}   # summary -> key
        self._gone = gone or set()
        self._unreachable = unreachable
        self.created: list[dict] = []
        self.get_calls: list[str] = []
        self._n = 0

    def search(self, *, jql):
        return [IssueHit(key=k, summary=s) for s, k in self._existing.items() if s in jql]

    def get_issue(self, *, issue_ref):
        self.get_calls.append(issue_ref)
        if self._unreachable is not None:
            raise CapabilityError(f"Atlassian GET -> {self._unreachable}",
                                  status=self._unreachable)
        if issue_ref in self._gone:
            raise CapabilityError("Atlassian GET -> 404", status=404)
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

    assert out == {"reconciled": 2, "created": 2, "skipped": 0, "failed": [],
                   "items": out["items"]}
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
    # The item is a candidate again (it is no longer filtered out by state), its recorded key is
    # re-checked against the tracker, still resolves — so it is SKIPPED, not re-created.
    assert second["created"] == 0 and second["skipped"] == 1 and second["failed"] == []
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


# ── S.No 237: an item's lifecycle stage no longer decides whether it can be tracked ────


def test_item_past_proposed_is_still_exportable(project):
    """Bugs S.No 237: candidates were selected on `state=proposed`, so the moment work started an
    item became permanently un-exportable — 70 of SpendLog's 109 items could never reach Jira."""
    wi = _wi(project, type=WorkItem.Type.STORY, title="Under way",
             state=WorkItem.State.IN_PROGRESS)
    tracker = _FakeTracker()

    out = reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                            tracker=tracker, project_key="ST")

    assert out["created"] == 1
    wi.refresh_from_db()
    assert wi.external_ref["id"] == "ST-1"


def test_export_never_moves_an_item_backwards(project):
    """THE PINNED RULE (team decision, 2026-09-07): a re-export must never move an item that is
    already past `accepted`. Reconcile forced state=ACCEPTED on every success, which was harmless
    only while proposed items were the sole candidates. With S.No 237 in place that same line
    would rewrite live history — the exact damage the July recovery needed a rewind script to
    undo. Deleting the `if wi.state == PROPOSED` guard must fail this test loudly."""
    tracker = _FakeTracker()
    kept = {}
    for state in (WorkItem.State.IN_PROGRESS, WorkItem.State.IN_REVIEW,
                  WorkItem.State.BLOCKED, WorkItem.State.DONE):
        kept[state] = _wi(project, type=WorkItem.Type.STORY, title=f"Story {state}", state=state)
    promoted = _wi(project, type=WorkItem.Type.STORY, title="Fresh",
                   state=WorkItem.State.PROPOSED)

    reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                      tracker=tracker, project_key="ST")

    for state, wi in kept.items():
        wi.refresh_from_db()
        assert wi.state == state, f"export moved a {state} item to {wi.state}"
        assert wi.external_ref["id"]      # still exported — only the state is left alone
    # `proposed → accepted` is the one promotion this service still makes.
    promoted.refresh_from_db()
    assert promoted.state == WorkItem.State.ACCEPTED


def test_defects_and_test_cases_are_not_swept_into_the_tracker(project):
    """Dropping the state filter must not turn a task-breakdown export into a dump of every
    defect and test case in the project — the QA loop creates those directly in `in_progress`,
    so they were never in scope, and `_KIND` would mislabel them all as a generic 'Task'."""
    _wi(project, type=WorkItem.Type.DEFECT, title="Contrast too low",
        state=WorkItem.State.IN_PROGRESS)
    _wi(project, type=WorkItem.Type.TEST_CASE, title="TC-1 login",
        state=WorkItem.State.IN_PROGRESS)
    _wi(project, type=WorkItem.Type.STORY, title="A real story")
    tracker = _FakeTracker()

    out = reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                            tracker=tracker, project_key="ST")

    assert out["created"] == 1
    assert [c["summary"] for c in tracker.created] == ["A real story"]


def test_a_cancelled_item_is_never_filed_in_the_tracker(project):
    """Team decision, 8 Sep 2026. Two fixes in one batch disagreed about the same query: S.No 237
    stopped filtering candidates on state, and S.No 140 then added a state that means "we have
    decided this is not happening". Without this exclusion the next task-breakdown export files a
    brand-new ticket for work the team just took OFF its own board — landing in the sprint backlog
    indistinguishable from real new work, ready for somebody to pick up.

    The two other stories here are the guard on the guard: excluding `cancelled` must not quietly
    become excluding everything terminal. `done` with no tracker id is precisely what S.No 237
    exists to let through, and `in_progress` is the case that motivated it.
    """
    cancelled = _wi(project, type=WorkItem.Type.STORY, title="Duplicate of WI-402",
                    state=WorkItem.State.CANCELLED)
    done = _wi(project, type=WorkItem.Type.STORY, title="Shipped last sprint",
               state=WorkItem.State.DONE)
    tracker = _FakeTracker()

    out = reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                            tracker=tracker, project_key="ST")

    assert [c["summary"] for c in tracker.created] == ["Shipped last sprint"]
    assert out["created"] == 1
    # Nothing was written to the cancelled item either — no pointer, no state change.
    cancelled.refresh_from_db()
    assert cancelled.state == WorkItem.State.CANCELLED
    assert not (cancelled.external_ref or {}).get("id")
    done.refresh_from_db()
    assert done.state == WorkItem.State.DONE          # exported, and still done
    assert done.external_ref["id"] == "ST-1"


def test_a_cancelled_item_with_a_pointer_is_left_completely_alone(project):
    """An item exported BEFORE it was cancelled keeps the pointer it already had. The export does
    not re-validate it, does not re-create it, and does not touch its state — a cancellation is
    not the export's business to act on.

    KNOWN GAP, logged separately rather than solved here: the Jira ticket this item already has
    stays open, and nothing in the platform closes it. Excluding cancelled items stops NEW tickets
    being created; the stale-ticket half is a different problem with a different risk (it means the
    platform writing to a system of record on its own) and is not in this change.
    """
    wi = _wi(project, type=WorkItem.Type.STORY, title="Abandoned mid-flight",
             state=WorkItem.State.CANCELLED)
    wi.external_ref = {"id": "ST-77", "key": "ST-77"}
    wi.save(update_fields=["external_ref"])
    tracker = _FakeTracker()

    reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                      tracker=tracker, project_key="ST")

    assert tracker.created == []
    wi.refresh_from_db()
    assert wi.external_ref["id"] == "ST-77"           # pointer intact
    assert wi.state == WorkItem.State.CANCELLED


# ── S.No 236: a pointer is only trusted while the issue it names still exists ────


def test_deleted_issue_is_detected_and_the_item_is_recreated(project):
    """Bugs S.No 236: an issue deleted in Jira left the platform holding a dead key for ever —
    the item was skipped on every future pass, so the work silently fell out of the tracker with
    no detection and no repair path."""
    wi = _wi(project, type=WorkItem.Type.STORY, title="Orphaned",
             state=WorkItem.State.IN_PROGRESS)
    wi.external_ref = {"sor": "jira", "id": "ST-99", "url": "https://x/browse/ST-99"}
    wi.save(update_fields=["external_ref"])
    tracker = _FakeTracker(gone={"ST-99"})

    out = reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                            tracker=tracker, project_key="ST")

    assert out["created"] == 1
    wi.refresh_from_db()
    assert wi.external_ref["id"] == "ST-1"        # a NEW key — Jira never reuses a deleted one
    assert wi.state == WorkItem.State.IN_PROGRESS  # and the state is still preserved


def test_an_outage_never_clears_pointers(project):
    """The single most dangerous line in this fix. Only 404/410 mean 'gone'. If a 401 (expired
    token), 403, 429 or 5xx were read as deletion, one export during an outage would clear every
    pointer in the project and re-create the entire backlog as duplicate issues."""
    for status in (401, 403, 429, 500, 503):
        wi = _wi(project, type=WorkItem.Type.STORY, title=f"Tracked {status}")
        wi.external_ref = {"sor": "jira", "id": f"ST-{status}", "url": "https://x"}
        wi.save(update_fields=["external_ref"])
        tracker = _FakeTracker(unreachable=status)

        out = reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                                tracker=tracker, project_key="ST")

        assert tracker.created == [], f"a {status} caused a duplicate issue to be created"
        assert out["created"] == 0
        wi.refresh_from_db()
        assert wi.external_ref["id"] == f"ST-{status}", f"a {status} wiped the pointer"
        wi.delete()


def test_export_without_a_project_key_refuses_instead_of_duplicating(project):
    """`_find_existing` returns None for everything when the project key is unset, so
    register-don't-recreate is silently off and the export creates blind. Refuse the whole run
    rather than make a second copy of a backlog that is already in Jira."""
    _wi(project, type=WorkItem.Type.STORY, title="A story")
    tracker = _FakeTracker()

    out = reconcile_backlog(tenant_id=str(project.tenant_id), project_id=str(project.id),
                            tracker=tracker, project_key="")

    assert out["created"] == 0 and tracker.created == []
    assert "project key" in out["failed"][0]["error"]


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
