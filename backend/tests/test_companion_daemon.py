"""Companion daemon (req #1): claim work → run the phase on local Claude Code → report.

Pure unit tests — the HTTP transport and the engine driver are injected, so no network and
no real engine. They prove the loop claims/dispatches/reports correctly and that the daemon
forces the *local* engine login (drops ANTHROPIC_API_KEY).
"""
import os
from types import SimpleNamespace

import pytest
from runner.companion import daemon as daemon_mod
from runner.companion.daemon import (
    CompanionDaemon,
    DaemonError,
    EngineAuthError,
    ensure_local_engine_auth,
)

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
        sleep=kw.pop("sleep", lambda _s: None),
        # Heartbeat is off by default in tests so its background POSTs don't perturb the
        # report/claim call assertions; the heartbeat has its own focused test below.
        heartbeat_interval=kw.pop("heartbeat_interval", 0), **kw)


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


def test_empty_engine_result_reports_ok_with_honest_message():
    """Incident (run 7f67d88a): the engine ended with no final text and the daemon reported
    a silently empty phase draft. The work already done (MCP-registered artifacts) still
    reports ok, but with an explicit message instead of a blank body going unnoticed."""
    transport = _Transport([(200, _PLAN_TASK), (204, None)])
    driver = _FakeDriver()

    async def _empty(**kwargs):
        return SimpleNamespace(outputs={"result": "", "text": "", "result_subtype": ""},
                               cost_usd=0.0)

    driver.run_planning_task = _empty
    d = _daemon(transport, driver)
    d.serve(max_iterations=2)
    url, body = transport.reports()[0]
    assert body["status"] == "ok" and body["body"] == ""
    assert "no final text" in body["message"]


def test_abnormal_engine_subtype_is_reported_in_message():
    transport = _Transport([(200, _PLAN_TASK), (204, None)])
    driver = _FakeDriver()

    async def _truncated(**kwargs):
        return SimpleNamespace(
            outputs={"result": "partial", "text": "partial",
                     "result_subtype": "error_max_turns"}, cost_usd=0.5)

    driver.run_planning_task = _truncated
    d = _daemon(transport, driver)
    d.serve(max_iterations=2)
    url, body = transport.reports()[0]
    assert body["status"] == "ok" and body["body"] == "partial"
    assert "error_max_turns" in body["message"]


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


def _build_task(repo: str):
    return {"kind": "build", "run_id": "rb", "payload": {
        "run_id": "rb", "tenant_id": "t1", "project_id": "p1", "work_item_id": "w1",
        "work_item_key": "ST-1", "repo": repo, "base": "main",
        "manifest": "# Project\nm", "agent_body": "BODY"}}


def test_build_routes_to_the_mapped_clone_for_this_repo(monkeypatch):
    """Multi-repo: a work item assigned to acme/web must build against acme/web's clone, not
    whichever clone happens to be first — the whole point of Hybrid Option C routing."""
    transport = _Transport([(200, _build_task("acme/web")), (204, None)])
    seen = {}

    async def _fake_run_build(task, *, driver, repo_path, worktrees_root, keep_worktree=False):
        seen["repo_path"] = repo_path
        return {"status": "ok", "branch": "feature/ST-1", "head_sha": "d", "changed_files": []}

    monkeypatch.setattr(daemon_mod, "run_build", _fake_run_build)
    d = _daemon(transport, _FakeDriver(), worktrees_root="/wt",
                repo_paths={"acme/api": "/repos/api", "acme/web": "/repos/web"})
    d.serve(max_iterations=2)
    assert seen["repo_path"] == "/repos/web"


def test_build_for_unmapped_repo_fails_loud_never_wrong_clone():
    """A work item routed to a repo with no local clone must raise — never silently fall back to
    another repo's clone (which would push code to the wrong GitHub repo)."""
    d = _daemon(_Transport([]), _FakeDriver(), worktrees_root="/wt",
                repo_paths={"acme/api": "/repos/api"})
    with pytest.raises(DaemonError, match="no local clone configured for repo 'acme/web'"):
        d._run_build(_build_task("acme/web"))


def test_build_agent_error_is_reported_not_crash_daemon(monkeypatch):
    """Bugs S.No 133: a build-agent error must fail THIS build (post a failed report) and let
    the long-lived companion keep polling — not propagate out of serve and crash the process
    (which stopped polling and left the run dangling). Mirrors the plan/review path."""
    transport = _Transport([(200, _build_task("acme/api")), (204, None)])

    async def _boom(task, *, driver, repo_path, worktrees_root, keep_worktree=False):
        raise RuntimeError("agent exploded mid-build")

    monkeypatch.setattr(daemon_mod, "run_build", _boom)
    d = _daemon(transport, _FakeDriver(), repo_path="/repos/api", worktrees_root="/wt")
    processed = d.serve(max_iterations=2)   # must NOT raise

    assert processed == 1
    url, body = transport.reports()[0]
    assert url.endswith("/api/runner/builds/rb/report/")
    assert body["status"] == "failed" and "agent exploded" in body["message"]


def test_build_engine_auth_error_still_halts(monkeypatch):
    """The S.No 133 generic catch must NOT swallow a fail-closed auth halt surfaced mid-build —
    EngineAuthError still propagates out of serve, never downgraded to a failed report."""
    transport = _Transport([(200, _build_task("acme/api")), (204, None)])

    async def _auth(task, *, driver, repo_path, worktrees_root, keep_worktree=False):
        raise EngineAuthError("subscription required")

    monkeypatch.setattr(daemon_mod, "run_build", _auth)
    d = _daemon(transport, _FakeDriver(), repo_path="/repos/api", worktrees_root="/wt")
    with pytest.raises(EngineAuthError):
        d.serve(max_iterations=2)


def test_single_repo_shorthand_still_serves_any_repo():
    """Backward compat: with only --repo-path (no --repo map), the single clone serves the
    build regardless of the task's repo label (single-repo projects, unchanged behaviour)."""
    d = _daemon(_Transport([]), _FakeDriver(), worktrees_root="/wt", repo_path="/repos/only")
    assert d._resolve_repo_path("acme/api") == "/repos/only"


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


def test_nonzero_engine_cost_is_reported_not_halted():
    """Current Claude Code reports a computed subscription-equivalent cost even when correctly
    billing the subscription, so a non-zero cost is NOT an API-billing signal. The daemon must
    keep running and report the figure (surfaced in the UI for the team's reference), relying on
    ensure_local_engine_auth for subscription-only enforcement."""
    transport = _Transport([(200, _PLAN_TASK), (204, None)])
    driver = _FakeDriver()

    async def _billed(**kwargs):
        return SimpleNamespace(outputs={"result": "# body"}, cost_usd=1.23)

    driver.run_planning_task = _billed
    d = _daemon(transport, driver)
    assert d.serve(max_iterations=2) == 1   # ran + idled, no DaemonError
    url, body = transport.reports()[0]
    assert body["status"] == "ok" and body["cost_usd"] == 1.23


def test_zero_cost_run_does_not_halt():
    transport = _Transport([(200, _PLAN_TASK), (204, None)])
    d = _daemon(transport, _FakeDriver())
    assert d.serve(max_iterations=2) == 1   # ran + idled, no DaemonError


# ── liveness heartbeat (RC-2: companion stayed "online" while busy running a phase) ──
def test_heartbeat_posts_to_heartbeat_endpoint():
    """The heartbeat touches last_seen out-of-band of the claim/report loop, so a long phase
    doesn't let the enrollment go stale and flip the UI to 'offline / daemon stopped'."""
    transport = _Transport([])
    d = _daemon(transport, _FakeDriver())
    d._heartbeat_once()
    posts = [(url, body) for (m, url, body) in transport.calls if m == "POST"]
    assert posts and posts[0][0].endswith("/api/runner/heartbeat/")


def test_heartbeat_failure_never_raises():
    """A network hiccup on the keep-alive must not crash the daemon — the next tick retries."""
    def _boom(*a, **k):
        raise RuntimeError("network down")

    d = _daemon(_Transport([]), _FakeDriver())
    d._transport = _boom
    d._heartbeat_once()   # swallowed, no exception


# ── one bad report must not take down the whole daemon (RC-3 follow-up: v2-duplicate crash) ──
class _ReportFailsTransport:
    """Scripted /work/ responses; the report POST returns 500 (e.g. a late report to a
    workflow that already finished), every other POST is 200."""

    def __init__(self, work_responses):
        self._work = list(work_responses)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        if method == "GET" and url.endswith("/api/runner/work/"):
            return self._work.pop(0) if self._work else (204, None)
        if url.endswith("/report/"):
            return 500, "workflow execution already completed"
        return 200, {"ok": True}


def test_failed_report_does_not_crash_daemon():
    transport = _ReportFailsTransport([(200, _PLAN_TASK), (204, None)])
    d = _daemon(transport, _FakeDriver())
    # The report 500s, but serve must keep going (log + continue), not raise.
    assert d.serve(max_iterations=2) == 0   # task attempted, report failed → not counted
    assert any(u.endswith("/api/runner/phases/r1/report/") for (_m, u, _b) in transport.calls)


# ── S.No 105: a backend restart must never kill the companion — retry with backoff ──
class _FlakyBackendTransport:
    """Backend down for the first N calls (connection refused, an OSError — how a docker
    restart actually presents, NOT an HTTP status), then healthy and scripted like _Transport."""

    def __init__(self, outage_calls, work_responses):
        self._outage = outage_calls
        self._work = list(work_responses)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        if len(self.calls) <= self._outage:
            raise ConnectionRefusedError("backend restarting")
        if method == "GET" and url.endswith("/api/runner/work/"):
            return self._work.pop(0) if self._work else (204, None)
        return 200, {"ok": True}


def test_claim_survives_backend_outage_and_resumes(capsys):
    """S.No 105: previously a connection error in claim() propagated out of serve() and the
    companion silently died — every later dispatch sat unclaimed until a human restarted it.
    Now the loop backs off, reconnects, and still runs the task once the backend returns."""
    transport = _FlakyBackendTransport(3, [(200, _PLAN_TASK), (204, None)])
    slept = []
    d = _daemon(transport, _FakeDriver(), sleep=slept.append)

    assert d.serve(max_iterations=5) == 1          # 3 outage polls + claim + idle
    assert any(u.endswith("/api/runner/phases/r1/report/")
               for (_m, u, _b) in transport.calls)
    # backoff grew (poll_interval 5 → 10 → 20), then the idle 204 slept the normal interval
    assert slept[:3] == [5.0, 10.0, 20.0] and slept[-1] == 5.0
    err = capsys.readouterr().err
    assert "backend unreachable" in err and "reconnected" in err


def test_report_retries_through_transient_outage():
    """A finished phase must not be lost because the backend restarted right at report time:
    the report POST retries with backoff until the backend is back."""
    calls = []

    def transport(method, url, headers, body):
        calls.append((method, url))
        if len(calls) <= 2:
            raise ConnectionResetError("backend restarting")
        return 200, {"ok": True}

    slept = []
    d = _daemon(transport, _FakeDriver(), sleep=slept.append)
    d._report("/api/runner/phases/r1/report/", {"status": "ok"})
    assert len(calls) == 3 and slept == [5.0, 10.0]


def test_report_gives_up_after_bounded_retries():
    """The retry is bounded: if the backend never comes back the failure still surfaces as a
    DaemonError (which serve() logs per-task without dying)."""
    def transport(method, url, headers, body):
        raise ConnectionRefusedError("still down")

    d = _daemon(transport, _FakeDriver(), sleep=lambda _s: None)
    with pytest.raises(DaemonError, match="backend unreachable"):
        d._report("/api/runner/phases/r1/report/", {"status": "ok"})


def test_engine_auth_error_still_halts_the_loop():
    """Auth failures remain fail-closed — EngineAuthError propagates out of serve even though
    it subclasses DaemonError (which the loop otherwise swallows per-task)."""
    from runner.companion.daemon import EngineAuthError

    assert issubclass(EngineAuthError, DaemonError)
    transport = _Transport([(200, _PLAN_TASK), (204, None)])
    d = _daemon(transport, _FakeDriver())

    def _auth_boom(task):
        raise EngineAuthError("api key appeared mid-run")

    d.run_task = _auth_boom
    with pytest.raises(EngineAuthError):
        d.serve(max_iterations=2)
