"""Companion daemon (req #1): claim work → run the phase on local Claude Code → report.

Pure unit tests — the HTTP transport and the engine driver are injected, so no network and
no real engine. They prove the loop claims/dispatches/reports correctly and that the daemon
forces the *local* engine login (drops ANTHROPIC_API_KEY).
"""
import os
from pathlib import Path
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
        self.mcp_config = None      # the config's CONTENTS, captured while the file still exists

    async def run_planning_task(self, *, manifest, agent_spec, mcp_servers, allowed_tools,
                               work_item):
        self.calls.append(("plan", manifest, agent_spec.phase_label, allowed_tools))
        self.mcp_servers = mcp_servers
        # The daemon deletes the config file as soon as the run ends (it carries the runner
        # token), so read it HERE — at the moment the engine would have — not after serve().
        if isinstance(mcp_servers, str) and mcp_servers:
            import json as _json
            from pathlib import Path as _Path
            self.mcp_config = _json.loads(_Path(mcp_servers).read_text(encoding="utf-8"))
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
    # The config now travels as a FILE path, not an inline dict (it carries an inherited
    # environment, which must never reach the command line). The driver captured its contents.
    assert isinstance(driver.mcp_servers, str), "mcp_servers must be a config FILE path"
    env = driver.mcp_config["mcpServers"]["platform-state"]["env"]
    assert env["RUNNER_PROJECT_ID"] == "proj-1"
    # Inherited, so the interpreter can actually start (Windows needs SYSTEMROOT for Winsock).
    assert len(env) > 7
    # And the file is gone once the run ended — it carried the runner token.
    assert not Path(driver.mcp_servers).exists()


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


# ── B8: a 5xx from the platform is transient, not fatal ─────────────
class _FlakyWorkTransport:
    """`/work/` answers 500 twice (the backend's own database blinked), then behaves."""

    def __init__(self):
        self.work_calls = 0
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        if method == "GET" and url.endswith("/api/runner/work/"):
            self.work_calls += 1
            if self.work_calls <= 2:
                return 500, "OperationalError: SSL SYSCALL error: EOF detected"
            return 204, None
        return 200, {"ok": True}


def test_backend_5xx_on_claim_does_not_kill_the_companion():
    """The shared Postgres dropped ONE connection, `/api/runner/work/` returned 500, and the
    companion exited — leaving a developer with a button that silently stops working, minutes
    after a blip they never saw. A connection that never lands was already retried forever; a
    connection that lands on a briefly-broken backend was fatal (B8)."""
    transport = _FlakyWorkTransport()
    d = _daemon(transport, _FakeDriver())
    assert d.serve(max_iterations=4) == 0     # survived; no exception escaped
    assert transport.work_calls >= 3          # kept polling past both 500s


def test_claim_4xx_is_still_fatal():
    """A 4xx is a real rejection — a revoked or invalid token. Retrying cannot fix it, and
    quietly looping forever on one would hide a genuine misconfiguration."""
    def _unauthorized(method, url, headers, body):
        return 403, "enrollment revoked"

    d = _daemon(_unauthorized, _FakeDriver())
    with pytest.raises(DaemonError):
        d.serve(max_iterations=1)


def test_report_retries_a_5xx_before_giving_up():
    """A finished phase is too expensive to lose to a database blip: the platform answered, but
    never recorded the report."""
    attempts = {"n": 0}

    def _flaky(method, url, headers, body):
        if url.endswith("/report/"):
            attempts["n"] += 1
            return (500, "db blinked") if attempts["n"] == 1 else (200, {"ok": True})
        return 200, {"ok": True}

    d = _daemon(_flaky, _FakeDriver())
    d._report("/api/runner/phases/r1/report/", {"status": "completed"})
    assert attempts["n"] == 2                 # retried once, then succeeded


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


# ── Security scan: read-only worktree on the planning path (Bugs S.No 176) ──
_SCAN_TASK = {"kind": "plan", "run_id": "rsec", "payload": {
    "phase": "security", "work_item_id": "w1", "project_id": "p1", "model": "claude-x",
    "agent_body": "BODY", "manifest": "# Project\nm",
    "repo": "acme/api", "base": "main", "reads_code": True}}


class _ScanDriver:
    """Records the repo_workspace it was handed (the read-only worktree) for a security scan."""

    def __init__(self):
        self.repo_workspace = "unset"
        self.mcp_servers = {}
        self.mcp_config = None      # config CONTENTS, captured while the file still exists
        self.allowed_tools = []

    async def run_planning_task(self, *, manifest, agent_spec, mcp_servers, allowed_tools,
                                work_item, repo_workspace=None):
        self.repo_workspace = repo_workspace
        self.mcp_servers = mcp_servers
        self.allowed_tools = allowed_tools
        # The config is a FILE path now and the daemon deletes it when the run ends, so read it
        # here — at the moment the engine would have.
        if isinstance(mcp_servers, str) and mcp_servers:
            import json as _json
            self.mcp_config = _json.loads(Path(mcp_servers).read_text(encoding="utf-8"))
        return SimpleNamespace(outputs={"result": "# Security Review"}, cost_usd=0.0)

    async def run_review_task(self, **kwargs):
        return SimpleNamespace(outputs={"text": "x"}, cost_usd=0.0)


def test_security_scan_provisions_readonly_worktree_and_tears_it_down(monkeypatch):
    """A reads_code plan task provisions a scan worktree, runs the agent inside it, tears it
    down after, and NEVER commits or pushes (read-only)."""
    import runner.companion.worktree as wt

    seen = {}

    def _fake_provision(*, repo_path, branch, base, worktree_path):
        seen["provision"] = {"repo_path": repo_path, "branch": branch, "base": base,
                             "worktree_path": str(worktree_path)}
        return worktree_path

    def _fake_teardown(*, repo_path, worktree_path):
        seen["teardown"] = str(worktree_path)

    def _explode(*a, **k):  # any git-write helper must never be called on a scan
        raise AssertionError("a security scan must never commit or push")

    monkeypatch.setattr(wt, "provision_worktree", _fake_provision)
    monkeypatch.setattr(wt, "teardown_worktree", _fake_teardown)
    monkeypatch.setattr(wt, "commit_all", _explode)
    monkeypatch.setattr(wt, "push_branch", _explode)

    transport = _Transport([(200, _SCAN_TASK), (204, None)])
    driver = _ScanDriver()
    d = _daemon(transport, driver, worktrees_root="/wt", repo_path="/repos/api")
    d.serve(max_iterations=2)

    assert seen["provision"]["repo_path"] == "/repos/api"
    assert seen["provision"]["branch"] == "sdlc-scan/rsec"   # disjoint from build's feature/*
    assert seen["provision"]["base"] == "main"
    # the driver ran inside the provisioned worktree
    assert str(driver.repo_workspace).endswith("scan-rsec")
    # torn down afterwards
    assert seen["teardown"].endswith("scan-rsec")
    # a reads_code run with a worktree also wires the CodeIntel MCP bound to that worktree, and
    # adds its tools to the planning allowlist (agent-driven onboarding reuses this seam).
    # Both servers must reach the engine in the SAME config file: the codeintel server is added
    # after the worktree is provisioned, so the file has to be written once the set is final.
    servers = driver.mcp_config["mcpServers"]
    assert "platform-state" in servers and "codeintel" in servers
    assert servers["codeintel"]["env"]["RUNNER_WORKSPACE"].endswith("scan-rsec")
    assert servers["codeintel"]["env"]["RUNNER_REPO"] == "acme/api"
    assert "mcp__codeintel__index" in driver.allowed_tools
    assert "mcp__codeintel__get_overview" in driver.allowed_tools
    # the phase result was still reported
    url, body = transport.reports()[0]
    assert url.endswith("/api/runner/phases/rsec/report/") and body["status"] == "ok"


def test_security_scan_degrades_when_no_worktree_configured():
    """No --worktrees/clone: the scan degrades to a manifest-only planning run (no worktree
    passed to the driver) rather than failing — the phase still produces a document."""
    transport = _Transport([(200, _SCAN_TASK), (204, None)])
    driver = _ScanDriver()
    d = _daemon(transport, driver)  # no worktrees_root, no repo_path
    d.serve(max_iterations=2)
    assert driver.repo_workspace is None            # ran without a worktree
    url, body = transport.reports()[0]
    assert url.endswith("/api/runner/phases/rsec/report/") and body["status"] == "ok"


# ── Code intelligence dispatch (B4): read-only worktree → analyze → report ──
_CI_JOB = {"job_id": "ci1", "repo": "acme/api", "base": "main"}


class _CodeIntelTransport:
    """No /work/ tasks; one code-intel job on the first /code-intel/ poll, then idle. Records
    every call so the report POST can be asserted."""

    def __init__(self):
        self._ci = [(200, _CI_JOB), (204, None)]
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        if method == "GET" and url.endswith("/api/runner/work/"):
            return 204, None
        if method == "GET" and url.endswith("/api/runner/code-intel/"):
            return self._ci.pop(0) if self._ci else (204, None)
        return 200, {"artifact_id": "art1", "status": "indexed"}

    def reports(self):
        return [(url, body) for (m, url, body) in self.calls if m == "POST"]


def test_code_intel_job_analyzes_in_readonly_worktree_and_reports(monkeypatch):
    """B4: a claimed code-intel job provisions a throwaway read-only worktree, runs the built-in
    analyzer inside it, reports the index, and tears the worktree down — the source never leaves
    the machine (only the index is posted)."""
    import runner.companion.worktree as wt

    seen = {}

    def _fake_provision(*, repo_path, branch, base, worktree_path):
        seen["provision"] = {"repo_path": repo_path, "branch": branch, "base": base}
        return worktree_path

    def _fake_teardown(*, repo_path, worktree_path):
        seen["teardown"] = str(worktree_path)

    monkeypatch.setattr(wt, "provision_worktree", _fake_provision)
    monkeypatch.setattr(wt, "teardown_worktree", _fake_teardown)

    class _FakeIntel:  # stub the analyzer so the test needs no real repo/git
        def index(self, *, workspace, repo):
            seen["workspace"] = str(workspace)
            seen["repo"] = repo
            return SimpleNamespace(file_count=4, commits=1, hotspots=1,
                                   languages={".py": 4}, indexed_at="2026-07-27")

        def get_overview(self, *, repo):
            return {"authors": 2, "communities": 1, "entry_points": ["main.py"],
                    "top_modules": ["pkg/a.py"],
                    "hotspots": [{"file": "pkg/a.py", "score": 9, "churn": 3, "complexity": 3}]}

        def get_dead_code(self, *, repo):
            return [{"file": "pkg/dead.py"}]

        def get_why(self, *, repo):
            return [{"title": "Switch to X", "ref": "ADR-1"}]

    import integrations.codeintel.builtin as builtin_mod
    monkeypatch.setattr(builtin_mod, "BuiltinCodeIntel", _FakeIntel)

    transport = _CodeIntelTransport()
    d = _daemon(transport, _FakeDriver(), worktrees_root="/wt", repo_path="/repos/api")
    d.serve(max_iterations=2)

    assert seen["provision"]["repo_path"] == "/repos/api"
    assert seen["provision"]["branch"] == "sdlc-codeintel/ci1"   # disjoint from scan/build branches
    assert seen["repo"] == "acme/api"
    url, body = transport.reports()[0]
    assert url.endswith("/api/runner/code-intel/ci1/report/")
    assert body["status"] == "ok" and body["index"]["file_count"] == 4
    # The enrichment: the companion reports the analyzer's deep layers, not just counts.
    assert body["index"]["communities"] == 1 and body["index"]["hotspot_files"]
    assert body["index"]["dead_code"] and body["index"]["decisions"]
    assert seen["teardown"]                                       # torn down after


def test_code_intel_without_worktrees_reports_failed(monkeypatch):
    """No --worktrees configured → the job is reported failed (never left hanging)."""
    transport = _CodeIntelTransport()
    d = _daemon(transport, _FakeDriver())   # no worktrees_root / repo_path
    d.serve(max_iterations=2)
    url, body = transport.reports()[0]
    assert url.endswith("/api/runner/code-intel/ci1/report/")
    assert body["status"] == "failed" and "worktrees" in body["error"]


def test_serve_headed_flag_exports_env(monkeypatch):
    """`serve --headed` exports SDLC_COMPANION_HEADED=1 for the process so both the Playwright MCP
    and the agent's `npx playwright test` run inherit it and go headed — no separate shell export
    or .env needed (the companion never loads the backend .env)."""
    from runner.companion import __main__ as cli

    monkeypatch.delenv("SDLC_COMPANION_HEADED", raising=False)
    monkeypatch.setattr(cli, "_assert_engine_env", lambda: None)

    class _FakeDaemon:
        def __init__(self, **kw):
            pass

        def serve(self):
            return None

    monkeypatch.setattr(daemon_mod, "CompanionDaemon", _FakeDaemon)

    # Without --headed: not set.
    cli.main(["serve", "--api-url", "http://x", "--tenant", "t", "--token", "tok"])
    assert os.environ.get("SDLC_COMPANION_HEADED") is None

    # With --headed: exported for this process.
    cli.main(["serve", "--api-url", "http://x", "--tenant", "t", "--token", "tok", "--headed"])
    assert os.environ.get("SDLC_COMPANION_HEADED") == "1"
    # …and undone by hand. `cli.main` sets it on the REAL os.environ, and monkeypatch cannot
    # roll that back: the `delenv` above found the var ABSENT, so it recorded nothing to
    # restore. The flag therefore leaked into every later test in the session, making
    # `test_build_mcp_servers_adds_playwright_only_for_test_automation` fail in a full run and
    # pass alone — the exact signature of a phantom regression. Popped directly, because
    # `monkeypatch.delenv` here would record "1" and put it BACK at teardown.
    os.environ.pop("SDLC_COMPANION_HEADED", None)


def test_both_mcp_servers_inherit_the_environment():
    """Neither MCP server may be launched with a hand-built environment.

    `codeintel` shipped with exactly three variables and it corrupted the analysis silently: the
    engine shells out to `git` for history, and with no PATH there is no git to find. Measured on
    the live test repo — the same index returned **commits=0** under the 3-var env and
    **commits=22** under an inherited one. No error, no warning; just a repo that looks like it
    has no history, feeding a gap report that reasons from it. (On Windows a minimal env is worse
    still: without SYSTEMROOT the interpreter dies in `import asyncio`, WinError 10106, before any
    of our code can log it.) Both servers must inherit.
    """
    from runner.companion.daemon import codeintel_mcp_servers, state_mcp_servers

    ci = codeintel_mcp_servers(workspace="/wt", repo="acme/api", repo_root="/repo")["codeintel"]
    st = state_mcp_servers(api_url="http://x", tenant_id="t", token="tok",
                           run_id="r", phase="p", project_id="pr")["platform-state"]
    for name, cfg in (("codeintel", ci), ("platform-state", st)):
        # A real inherited environment is dozens of vars; a hand-built one is a handful.
        assert len(cfg["env"]) > 10, f"{name} env looks hand-built: {sorted(cfg['env'])}"
        # Case-insensitively: Windows' os.environ answers to both "PATH" and "Path", but the
        # copied dict keeps only whichever spelling the OS actually stores.
        have = {k.lower() for k in cfg["env"]}
        for key in ("path", "systemroot"):
            if key in {k.lower() for k in os.environ}:
                assert key in have, f"{name} dropped {key}"
    # The run-specific values still override the inherited ones.
    assert ci["env"]["RUNNER_WORKSPACE"] == "/wt"
    assert ci["env"]["RUNNER_REPO"] == "acme/api"
    assert ci["env"]["PYTHONPATH"] == "/repo"


# ── G6a: the keyboard journey is the one planning phase with a browser ───────
#
# Eight WCAG criteria cannot be answered by reading a page standing still — whether tabbing ever
# traps you, whether focus stays visible, whether a status message is announced. The only way to
# answer them is to operate the application, and this is where 09d gets the browser to do it.

_JOURNEY_TASK = {"kind": "plan", "run_id": "r9", "payload": {
    "phase": "a11y_journey", "work_item_id": "w9", "project_id": "proj-9",
    "agent_body": "BODY", "manifest": "# Project\nm",
    "app_base_url": "http://127.0.0.1:5173"}}


def test_a_journey_gets_a_browser_locked_to_the_address_it_was_given():
    transport = _Transport([(200, _JOURNEY_TASK), (204, None)])
    driver = _FakeDriver()
    _daemon(transport, driver, sleep=lambda _s: None).serve(max_iterations=2)

    servers = driver.mcp_config["mcpServers"]
    assert "platform-state" in servers, "the state tools it reports through are still there"
    args = servers["playwright"]["args"]
    assert "@playwright/mcp@latest" in args and "--headless" in args
    # The origin list IS the bound — not the tool name, and not EgressPolicy, which gates shell
    # commands on the build path and says nothing at all about a browser.
    assert args[args.index("--allowed-origins") + 1] == "http://127.0.0.1:5173"
    # And the tools to drive it, on top of everything a planning run already had.
    tools = driver.calls[0][3]
    assert "mcp__playwright__browser_press_key" in tools
    assert "mcp__platform-state__get_a11y_journey" in tools


def test_every_other_planning_phase_still_has_no_browser():
    transport = _Transport([(200, _PLAN_TASK), (204, None)])
    driver = _FakeDriver()
    _daemon(transport, driver, sleep=lambda _s: None).serve(max_iterations=2)

    assert "playwright" not in driver.mcp_config["mcpServers"]
    assert not any(t.startswith("mcp__playwright__") for t in driver.calls[0][3])


def test_a_journey_with_no_address_is_reported_failed_and_never_run():
    """The bound on the browser is the origin list, so a launch with no address is an UNBOUNDED
    browser. The build path writes this as `if preview_url:` and quietly launches one anyway;
    that is not repeated here. Refused, with a sentence a person can act on."""
    task = {**_JOURNEY_TASK, "payload": {**_JOURNEY_TASK["payload"], "app_base_url": ""}}
    transport = _Transport([(200, task), (204, None)])
    driver = _FakeDriver()
    _daemon(transport, driver, sleep=lambda _s: None).serve(max_iterations=2)

    assert driver.calls == [], "the engine was never started"
    (url, body), = transport.reports()
    assert url.endswith("/api/runner/phases/r9/report/")
    assert body["status"] == "failed"
    assert "without an address" in body["message"]


def test_playwright_servers_is_empty_for_a_phase_that_does_not_operate_an_app():
    from runner.companion.daemon import NoAddressError, playwright_servers

    assert playwright_servers(phase="prd", base_url="http://x") == {}
    assert playwright_servers(phase="onboarding", base_url="") == {}
    with pytest.raises(NoAddressError):
        playwright_servers(phase="a11y_journey", base_url="   ")


def test_a_watched_journey_drops_headless_like_a_watched_build(monkeypatch):
    from runner.companion.daemon import playwright_servers

    monkeypatch.delenv("SDLC_COMPANION_HEADED", raising=False)
    assert "--headless" in playwright_servers(
        phase="a11y_journey", base_url="http://x")["playwright"]["args"]
    monkeypatch.setenv("SDLC_COMPANION_HEADED", "1")
    assert "--headless" not in playwright_servers(
        phase="a11y_journey", base_url="http://x")["playwright"]["args"]
