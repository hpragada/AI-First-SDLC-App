"""Companion daemon (req #1): claim work → run the phase on local Claude Code → report.

Pure unit tests — the HTTP transport and the engine driver are injected, so no network and
no real engine. They prove the loop claims/dispatches/reports correctly and that the daemon
forces the *local* engine login (drops ANTHROPIC_API_KEY).
"""
import os
from types import SimpleNamespace

import pytest
from runner.companion import daemon as daemon_mod
from runner.companion.daemon import CompanionDaemon, DaemonError, ensure_local_engine_auth

_PLAN_TASK = {"kind": "plan", "run_id": "r1", "payload": {
    "phase": "prd", "work_item_id": "w1", "project_id": "proj-1", "model": "claude-x",
    "agent_body": "BODY", "manifest": "# Project\nm"}}


class _FakeDriver:
    def __init__(self):
        self.calls = []
        self.mcp_servers = None

    async def run_planning_task(self, *, manifest, agent_spec, mcp_servers, allowed_tools,
                               work_item):
        self.calls.append(("plan", manifest, agent_spec.phase_label, allowed_tools))
        self.mcp_servers = mcp_servers
        # Subscription billing reports $0.00 (a non-zero cost trips the API-billing halt).
        return SimpleNamespace(outputs={"result": "# PRD body"}, cost_usd=0.0)

    async def run_review_task(self, **kwargs):
        self.calls.append(("review",))
        return SimpleNamespace(outputs={"text": "findings"}, cost_usd=0.0)


class _Transport:
    """Scripted GET /work/ responses; every other call (the report POST) returns 200."""

    def __init__(self, work_responses):
        self._work = list(work_responses)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        if method == "GET" and url.endswith("/api/runner/work/"):
            return self._work.pop(0) if self._work else (204, None)
        return 200, {"ok": True}

    def reports(self):
        return [(url, body) for (m, url, body) in self.calls if m == "POST"]


@pytest.fixture(autouse=True)
def _claude_on_path(monkeypatch, tmp_path):
    """A healthy local engine: `claude` on PATH + a valid subscription login in a fake
    HOME (ensure_local_engine_auth is fail-closed and reads ~/.claude.json +
    ~/.claude/.credentials.json — tests must never depend on the real machine's state)."""
    import json as _json
    from pathlib import Path

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/claude")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / ".credentials.json").write_text(
        _json.dumps({"claudeAiOauth": {"accessToken": "oat-test"}}), encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    return tmp_path


def _daemon(transport, driver, **kw):
    return CompanionDaemon(
        api_url="http://platform", tenant_id="t1", token="tok",
        transport=transport, driver_factory=lambda body: driver,
        sleep=kw.pop("sleep", lambda _s: None), **kw)


def test_serve_runs_plan_then_idles():
    transport = _Transport([(200, _PLAN_TASK), (204, None)])
    driver = _FakeDriver()
    slept = []
    d = _daemon(transport, driver, sleep=slept.append)
    processed = d.serve(max_iterations=2)

    assert processed == 1
    assert driver.calls and driver.calls[0][0] == "plan"
    assert "mcp__platform-state__ask_human" in driver.calls[0][3]   # ask_human offered
    reports = transport.reports()
    assert len(reports) == 1
    url, body = reports[0]
    assert url.endswith("/api/runner/phases/r1/report/")
    assert body == {"status": "ok", "body": "# PRD body", "cost_usd": 0.0}
    assert slept == [5.0]   # slept once (the default poll interval) on the idle (204) iteration


def test_plan_binds_project_id_into_state_mcp_env():
    """Regression (Bugs.xlsx row 53): the companion planning/review launch must bind the
    project id from the dispatched payload, so register_artifact fills it in rather than
    500-ing and forcing the agent to ask the user for a project UUID (row 25's missed seam)."""
    transport = _Transport([(200, _PLAN_TASK), (204, None)])
    driver = _FakeDriver()
    d = _daemon(transport, driver, sleep=lambda _s: None)
    d.serve(max_iterations=2)
    env = driver.mcp_servers["platform-state"]["env"]
    assert env["RUNNER_PROJECT_ID"] == "proj-1"


def test_engine_failure_is_reported_not_swallowed():
    transport = _Transport([(200, _PLAN_TASK)])
    driver = _FakeDriver()

    async def _boom(**kwargs):
        raise RuntimeError("engine exploded")

    driver.run_planning_task = _boom
    d = _daemon(transport, driver)
    d.serve(max_iterations=1)
    url, body = transport.reports()[0]
    assert url.endswith("/api/runner/phases/r1/report/")
    assert body["status"] == "failed" and "engine exploded" in body["message"]


def test_build_kind_delegates_to_run_build(monkeypatch):
    build_task = {"kind": "build", "run_id": "rb", "payload": {
        "run_id": "rb", "tenant_id": "t1", "project_id": "p1", "work_item_id": "w1",
        "work_item_key": "ST-1", "repo": "acme/api", "base": "main",
        "manifest": "# Project\nm", "agent_body": "BODY"}}
    transport = _Transport([(200, build_task), (204, None)])

    seen = {}

    async def _fake_run_build(task, *, driver, repo_path, worktrees_root, keep_worktree=False):
        seen["repo_path"] = repo_path
        return {"status": "ok", "branch": "feature/ST-1", "head_sha": "deadbeef",
                "changed_files": ["a.py"]}

    monkeypatch.setattr(daemon_mod, "run_build", _fake_run_build)
    d = _daemon(transport, _FakeDriver(), repo_path="/repos/api", worktrees_root="/wt")
    d.serve(max_iterations=2)

    assert seen["repo_path"] == "/repos/api"
    url, body = transport.reports()[0]
    assert url.endswith("/api/runner/builds/rb/report/")
    assert body["status"] == "ok" and body["branch"] == "feature/ST-1"


def test_ensure_local_engine_auth_drops_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-be-dropped")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-should-be-dropped")
    ensure_local_engine_auth()
    assert "ANTHROPIC_API_KEY" not in os.environ   # forced to the local subscription
    assert "ANTHROPIC_AUTH_TOKEN" not in os.environ


def test_ensure_local_engine_auth_requires_claude(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    with pytest.raises(DaemonError):
        ensure_local_engine_auth()
    assert "ANTHROPIC_API_KEY" not in os.environ   # dropped even though claude is missing


# ── fail-closed subscription guarantee (incident 2026-07-07: phases billed the API) ──
def test_auth_refuses_api_key_stored_in_cli_config(_claude_on_path):
    """A key persisted in ~/.claude.json (primaryApiKey) bills the API regardless of env
    scrubbing — the daemon must refuse to run, with removal instructions."""
    import json as _json

    (_claude_on_path / ".claude.json").write_text(
        _json.dumps({"primaryApiKey": "sk-ant-oops"}), encoding="utf-8")
    with pytest.raises(DaemonError, match="primaryApiKey"):
        ensure_local_engine_auth()


def test_auth_refuses_approved_api_key_prompt(_claude_on_path):
    import json as _json

    (_claude_on_path / ".claude.json").write_text(
        _json.dumps({"customApiKeyResponses": {"approved": ["somehash"]}}), encoding="utf-8")
    with pytest.raises(DaemonError, match="API key"):
        ensure_local_engine_auth()


def test_auth_refuses_when_no_subscription_login(_claude_on_path):
    """No OAuth token and no setup-token → refuse rather than let the CLI fall back to
    any API key source (fail-closed)."""
    import json as _json

    (_claude_on_path / ".claude" / ".credentials.json").write_text(
        _json.dumps({"claudeAiOauth": {}}), encoding="utf-8")
    with pytest.raises(DaemonError, match="claude /login"):
        ensure_local_engine_auth()


def test_auth_accepts_setup_token_without_credentials_file(_claude_on_path, monkeypatch):
    (_claude_on_path / ".claude" / ".credentials.json").unlink()
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-from-setup-token")
    ensure_local_engine_auth()   # no raise — setup-token is subscription auth


def test_nonzero_engine_cost_halts_daemon_after_reporting():
    """Last line of defense: subscription usage reports $0.00, so a non-zero cost means an
    API key slipped through — the daemon reports the finished phase, then HALTS so at most
    one run can ever bill the API."""
    transport = _Transport([(200, _PLAN_TASK)])
    driver = _FakeDriver()

    async def _billed(**kwargs):
        return SimpleNamespace(outputs={"result": "# body"}, cost_usd=1.23)

    driver.run_planning_task = _billed
    d = _daemon(transport, driver)
    with pytest.raises(DaemonError, match="non-zero API cost"):
        d.serve(max_iterations=1)
    url, body = transport.reports()[0]     # the work was still reported first
    assert body["status"] == "ok" and body["cost_usd"] == 1.23


def test_zero_cost_run_does_not_halt():
    transport = _Transport([(200, _PLAN_TASK), (204, None)])
    d = _daemon(transport, _FakeDriver())   # fake reports $0.00 (subscription)
    assert d.serve(max_iterations=2) == 1   # ran + idled, no DaemonError
