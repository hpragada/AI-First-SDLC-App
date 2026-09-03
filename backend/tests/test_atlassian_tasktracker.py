"""P1 — Atlassian TaskTracker (Jira) connector.

Contract tests drive a mocked transport (no network) to pin the requests built and the
vendor-free objects returned; a live round-trip (create→get→comment→transition→search→
delete) runs only when Atlassian creds + JIRA_PROJECT_KEY are configured.
"""
import time
import uuid

import pytest

from integrations.atlassian.config import AtlassianConfig
from integrations.atlassian.tasktracker import AtlassianTaskTracker, _adf
from integrations.types import CapabilityError, ExternalRef, Issue, IssueHit

_CFG = AtlassianConfig(site_url="https://x.atlassian.net", email="e@x.test", api_token="tok")


class _Router:
    def __init__(self):
        self.calls: list[dict] = []
        self._routes: list[tuple[str, str, int, object]] = []

    def add(self, method, contains, status, data):
        self._routes.append((method, contains, status, data))
        return self

    def __call__(self, method, url, headers, body):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body})
        for m, c, status, data in self._routes:
            if m == method and c in url:
                return status, data
        raise AssertionError(f"no route for {method} {url}")


def _tt(router):
    return AtlassianTaskTracker(_CFG, project="ST", transport=router)


# ── contract tests ──────────────────────────────────────────────────
def test_create_issue_posts_fields_and_adf_description():
    t = _Router().add("POST", "/rest/api/3/issue", 201, {"id": "1", "key": "ST-1"})
    ref = _tt(t).create_issue(kind="Story", summary="Login", description="as a user…",
                              parent_ref="ST-9")

    assert ref == ExternalRef(sor="jira", id="ST-1", url="https://x.atlassian.net/browse/ST-1")
    f = t.calls[0]["body"]["fields"]
    assert f["project"] == {"key": "ST"}
    assert f["issuetype"] == {"name": "Story"}
    assert f["parent"] == {"key": "ST-9"}
    assert f["description"] == _adf("as a user…")


def test_get_issue_parses_fields():
    t = _Router().add("GET", "/rest/api/3/issue/ST-1", 200, {
        "key": "ST-1",
        "fields": {"summary": "Login", "status": {"name": "To Do"},
                   "issuetype": {"name": "Story"}, "parent": {"key": "ST-9"}},
    })
    issue = _tt(t).get_issue(issue_ref="ST-1")
    assert issue == Issue(key="ST-1", summary="Login", status="To Do", issue_type="Story",
                          url="https://x.atlassian.net/browse/ST-1", parent_ref="ST-9")


def test_transition_issue_resolves_id_by_target_name():
    t = (_Router()
         .add("GET", "/transitions", 200,
              {"transitions": [{"id": "31", "name": "Start", "to": {"name": "In Progress"}},
                               {"id": "41", "name": "Done", "to": {"name": "Done"}}]})
         .add("POST", "/transitions", 204, None)
         .add("GET", "/rest/api/3/issue/ST-1", 200,
              {"key": "ST-1", "fields": {"summary": "x", "status": {"name": "In Progress"},
                                         "issuetype": {"name": "Story"}}}))
    issue = _tt(t).transition_issue(issue_ref="ST-1", to_state="In Progress")

    assert issue.status == "In Progress"
    post = next(c for c in t.calls if c["method"] == "POST")
    assert post["body"] == {"transition": {"id": "31"}}  # matched by to.name


def test_transition_issue_unknown_state_raises():
    t = _Router().add("GET", "/transitions", 200, {"transitions": [
        {"id": "41", "name": "Done", "to": {"name": "Done"}}]})
    with pytest.raises(CapabilityError):
        _tt(t).transition_issue(issue_ref="ST-1", to_state="In Review")


def test_add_comment_sends_adf():
    t = _Router().add("POST", "/comment", 201, {"id": "10"})
    _tt(t).add_comment(issue_ref="ST-1", body="looks good")
    assert t.calls[0]["body"] == {"body": _adf("looks good")}


def test_search_parses_issue_hits():
    t = _Router().add("POST", "/rest/api/3/search/jql", 200, {
        "issues": [{"key": "ST-1", "fields": {"summary": "Login"}},
                   {"key": "ST-2", "fields": {"summary": "Logout"}}]})
    hits = _tt(t).search(jql="project = ST")
    assert hits == [IssueHit(key="ST-1", summary="Login"), IssueHit(key="ST-2", summary="Logout")]
    assert t.calls[0]["body"]["jql"] == "project = ST"


def test_http_error_raises_capability_error():
    t = _Router().add("POST", "/rest/api/3/issue", 400, {"errorMessages": ["bad"]})
    with pytest.raises(CapabilityError) as exc:
        _tt(t).create_issue(kind="Story", summary="x", description="y")
    assert exc.value.status == 400


# ── live round-trip (real Jira, runs only with creds) ───────────────
def _live_config() -> AtlassianConfig | None:
    cfg = AtlassianConfig.from_settings()
    return cfg if cfg.configured else None


@pytest.mark.skipif(_live_config() is None, reason="Atlassian creds not configured in .env")
def test_jira_live_create_get_comment_transition_search_delete():
    from django.conf import settings

    cfg = _live_config()
    project = settings.JIRA_PROJECT_KEY
    assert project, "JIRA_PROJECT_KEY must be set for the live test"
    tt = AtlassianTaskTracker(cfg, project=project)
    marker = uuid.uuid4().hex[:8]
    summary = f"sdlc-platform smoke {marker}"

    ref = tt.create_issue(kind="Task", summary=summary, description="created by smoke test")
    try:
        assert ref.sor == "jira" and ref.id.startswith(f"{project}-")

        issue = tt.get_issue(issue_ref=ref.id)
        assert issue.summary == summary and issue.issue_type == "Task"

        tt.add_comment(issue_ref=ref.id, body="hello from the platform smoke test")

        # Transition to whatever the project's workflow offers first (config-agnostic).
        targets = tt.available_transitions(issue_ref=ref.id)
        if targets:
            moved = tt.transition_issue(issue_ref=ref.id, to_state=targets[0])
            assert moved.status  # status is now some named state

        # JQL search is index-backed (eventually consistent) — poll until the new
        # issue is indexed, so this verifies the real search endpoint without flaking.
        # Jira's index can lag well past 30s, so give it a generous window.
        hits = []
        for _ in range(30):
            hits = tt.search(jql=f"key = {ref.id}")
            if hits:
                break
            time.sleep(2)
        assert [h.key for h in hits] == [ref.id]
    finally:
        tt.delete_issue(issue_ref=ref.id, delete_subtasks=True)  # keep the project clean
