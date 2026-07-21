"""P2 — companion runner: remote-state client, worktree provisioning, build orchestration.

No Django/DB needed (the companion runs on the dev machine). Worktree tests use a real
temporary git repo; the build run uses a fake driver so no live engine is required.
"""
import subprocess
from pathlib import Path

import pytest
import runner.companion.__main__ as companion_main
from runner.companion.guardrails import (
    PLAYWRIGHT_MCP_TOOLS,
    AllowlistViolation,
    EgressPolicy,
    assert_phase_allowlist,
)
from runner.companion.runner import (
    BUILD_ALLOWED_TOOLS,
    BuildTask,
    PreviewError,
    PreviewHandle,
    allowed_tools_for,
    build_mcp_servers,
    inject_environment,
    manifest_with_preview,
    provision_preview_app,
    run_build,
    teardown_preview_app,
    to_build_report,
)
from runner.companion.state_client import RemoteStateClient, RemoteStateError
from runner.companion.worktree import (
    WorktreeError,
    assert_remote_matches,
    changed_files,
    commit_all,
    commits_ahead_of_base,
    provision_worktree,
    push_branch,
    teardown_worktree,
)

from drivers.base import RunResult


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)

    def git(*a):
        subprocess.run(["git", "-C", str(path), *a], check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "t@t.test")
    git("config", "user.name", "Tester")
    (path / "README.md").write_text("hi\n")
    git("add", "-A")
    git("commit", "-m", "init")
    return path


def _add_remote(repo: Path) -> Path:
    """Give a clone a bare `origin` so the companion's push (G2) has somewhere to go."""
    bare = repo.parent / (repo.name + "-origin.git")
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(bare)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "push", "-u", "origin", "main"],
                   check=True, capture_output=True)
    return bare


# ── engine-env startup guard (Bugs S.No 135) ────────────────────────
def test_engine_env_guard_raises_on_broken_anyio(monkeypatch):
    """serve/run must fail fast at startup — not mid-build — when anyio can't launch Claude Code
    (the recurring global-python downgrade to anyio 4.4.0)."""
    monkeypatch.setattr(companion_main, "_engine_launch_supported", lambda: (False, "4.4.0"))
    with pytest.raises(SystemExit) as exc:
        companion_main._assert_engine_env()
    assert exc.value.code == 2


def test_engine_env_guard_passes_on_good_anyio(monkeypatch):
    monkeypatch.setattr(companion_main, "_engine_launch_supported", lambda: (True, "4.14.2"))
    companion_main._assert_engine_env()   # no raise


def test_engine_env_guard_gates_serve_and_run_not_enroll(monkeypatch):
    """The guard runs for serve/run (they launch the engine) but never for enroll (no engine)."""
    called = {"n": 0}
    monkeypatch.setattr(companion_main, "_assert_engine_env",
                        lambda: called.__setitem__("n", called["n"] + 1))
    # enroll dispatches to _enroll; stub it so we don't hit the network — the point is the guard.
    monkeypatch.setattr(companion_main, "_enroll", lambda args: 0)
    companion_main.main(["enroll", "--api-url", "http://x", "--tenant", "T", "--project", "P"])
    assert called["n"] == 0        # enroll never triggers the engine check
    monkeypatch.setattr(companion_main, "_run", lambda args: 0)
    companion_main.main(["run", "--task", "t.json", "--repo-path", "r", "--worktrees", "w"])
    assert called["n"] == 1        # run does


def test_engine_launch_supported_reports_real_anyio():
    """On this (test) environment the predicate returns a (bool, version) tuple without raising."""
    ok, ver = companion_main._engine_launch_supported()
    assert isinstance(ok, bool) and isinstance(ver, str)


# ── remote state client ─────────────────────────────────────────────
def test_state_client_posts_token_tenant_and_returns_result():
    seen = {}

    def transport(url, headers, body):
        seen.update(url=url, headers=headers, body=body)
        return 200, {"result": {"id": "art-1"}}

    c = RemoteStateClient(api_url="http://plat/", tenant_id="T", token="tok", transport=transport)
    out = c.call("register_artifact", project_id="p", type="code")
    assert out == {"id": "art-1"}
    assert seen["url"] == "http://plat/api/runner/state/register_artifact/"
    assert seen["headers"]["Authorization"] == "Runner tok"
    assert seen["headers"]["X-Tenant-ID"] == "T"
    assert seen["body"] == {"project_id": "p", "type": "code"}  # tenant never in the body


def test_state_client_raises_on_http_error():
    c = RemoteStateClient(api_url="http://x", tenant_id="T", token="tok",
                          transport=lambda u, h, b: (403, {"detail": "no"}))
    with pytest.raises(RemoteStateError):
        c.call("detect_drift", artifact_id="x")


# ── worktree provisioning ───────────────────────────────────────────
def test_provision_creates_isolated_branch_and_excludes_scratch(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    wt = provision_worktree(repo_path=repo, branch="feature/ST-1", base="main",
                            worktree_path=tmp_path / "wt" / "ST-1")
    assert wt.exists() and (wt / "README.md").exists()

    (wt / "impl.py").write_text("x = 1\n")          # the "agent" edits a file
    (wt / ".sdlc").mkdir()
    (wt / ".sdlc" / "AGENTS.md").write_text("manifest")
    files = changed_files(wt)
    assert "impl.py" in files
    assert not any(".sdlc" in f for f in files)      # platform scratch stays out of the diff

    # Idempotent: re-provisioning returns the same worktree.
    assert provision_worktree(repo_path=repo, branch="feature/ST-1", base="main",
                              worktree_path=tmp_path / "wt" / "ST-1") == wt
    teardown_worktree(repo_path=repo, worktree_path=wt)
    assert not wt.exists()


def _sha(repo: Path, ref: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "rev-parse", ref],
                          check=True, capture_output=True, text=True).stdout.strip()


def test_provision_continues_from_remote_tip_across_companions(tmp_path):
    """Bugs S.No 162: a remediation cycle claimed by a DIFFERENT companion than the original
    build must continue from the branch's REMOTE tip — not recreate it from `main` and lose the
    prior cycle's pushed commit (which got the push rejected non-fast-forward). Simulate two
    clones sharing one bare origin: clone A pushes cycle 1; clone B (which has never seen the
    branch) must provision a worktree that already contains A's commit."""
    bare = subprocess.run(["git", "init", "--bare", "-b", "main", str(tmp_path / "origin.git")],
                          check=True, capture_output=True)
    origin = tmp_path / "origin.git"

    def clone(name: str) -> Path:
        subprocess.run(["git", "clone", str(origin), str(tmp_path / name)],
                       check=True, capture_output=True)
        for k, v in (("user.email", "t@t.test"), ("user.name", "Tester")):
            subprocess.run(["git", "-C", str(tmp_path / name), "config", k, v],
                           check=True, capture_output=True)
        return tmp_path / name

    # Seed origin/main from clone A.
    a = clone("cloneA")
    (a / "README.md").write_text("hi\n")
    subprocess.run(["git", "-C", str(a), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(a), "commit", "-m", "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(a), "push", "-u", "origin", "main"],
                   check=True, capture_output=True)
    b = clone("cloneB")

    # Cycle 1 on clone A: build + commit + push the feature branch.
    wt_a = provision_worktree(repo_path=a, branch="feature/ST-9", base="main",
                              worktree_path=tmp_path / "wtA")
    (wt_a / "impl.py").write_text("cycle1 = True\n")
    cycle1_sha = commit_all(wt_a, "cycle 1")
    push_branch(wt_a, "feature/ST-9")
    teardown_worktree(repo_path=a, worktree_path=wt_a)

    # Cycle 2 (remediation) lands on clone B, which has NEVER seen this branch. Before the fix it
    # would branch feature/ST-9 from its local main (no cycle-1 commit); now it bases on the remote
    # tip, so the worktree already carries cycle 1 and the next push is a clean fast-forward.
    subprocess.run(["git", "-C", str(b), "fetch", "origin", "main"], check=True, capture_output=True)
    wt_b = provision_worktree(repo_path=b, branch="feature/ST-9", base="main",
                              worktree_path=tmp_path / "wtB")
    assert (wt_b / "impl.py").read_text() == "cycle1 = True\n"   # cycle 1's work is present
    assert _sha(wt_b, "HEAD") == cycle1_sha                      # based on the remote tip, not main
    (wt_b / "impl2.py").write_text("cycle2 = True\n")
    commit_all(wt_b, "cycle 2")
    push_branch(wt_b, "feature/ST-9")                            # must NOT be rejected
    assert _sha(origin, "feature/ST-9") == _sha(wt_b, "HEAD")    # remote advanced cleanly


def test_provision_ignores_a_stale_remote_tracking_ref(tmp_path):
    """Bugs S.No 162 (hardening): the remote check must be AUTHORITATIVE (`ls-remote`), not the
    local `origin/<branch>` ref. Clone A pushes a branch, clone B fetches it, then the branch is
    deleted on the remote — B still holds a stale `origin/<branch>`. Provisioning on B must branch
    fresh from `main`, never resurrect the dead branch at its old commit (which would rebuild stale
    or already-merged work)."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   check=True, capture_output=True)

    def clone(name):
        subprocess.run(["git", "clone", str(origin), str(tmp_path / name)],
                       check=True, capture_output=True)
        for k, v in (("user.email", "t@t.test"), ("user.name", "Tester")):
            subprocess.run(["git", "-C", str(tmp_path / name), "config", k, v],
                           check=True, capture_output=True)
        return tmp_path / name

    a = clone("cloneA")
    (a / "README.md").write_text("hi\n")
    subprocess.run(["git", "-C", str(a), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(a), "commit", "-m", "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(a), "push", "-u", "origin", "main"],
                   check=True, capture_output=True)
    b = clone("cloneB")

    wt = provision_worktree(repo_path=a, branch="feature/DEAD", base="main",
                            worktree_path=tmp_path / "wt1")
    (wt / "x.py").write_text("stale\n")
    stale_sha = commit_all(wt, "stale work")
    push_branch(wt, "feature/DEAD")
    teardown_worktree(repo_path=a, worktree_path=wt)
    # B fetches the branch (gaining a remote-tracking ref), then A deletes it on the remote.
    subprocess.run(["git", "-C", str(b), "fetch", "origin",
                    "feature/DEAD:refs/remotes/origin/feature/DEAD"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(a), "push", "origin", "--delete", "feature/DEAD"],
                   check=True, capture_output=True)
    assert _sha(b, "refs/remotes/origin/feature/DEAD") == stale_sha   # B's stale ref lingers

    subprocess.run(["git", "-C", str(b), "fetch", "origin", "main"], check=True, capture_output=True)
    wt2 = provision_worktree(repo_path=b, branch="feature/DEAD", base="main",
                             worktree_path=tmp_path / "wt2")
    assert _sha(wt2, "HEAD") == _sha(b, "origin/main")   # fresh from main, NOT the stale commit
    assert not (wt2 / "x.py").exists()                   # stale work never leaked in


# ── multi-repo remote guard ─────────────────────────────────────────
def test_assert_remote_matches_accepts_matching_hosted_remote(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                    "https://github.com/acme/web.git"], check=True, capture_output=True)
    assert_remote_matches(repo, "acme/web")                     # no raise
    subprocess.run(["git", "-C", str(repo), "remote", "set-url", "origin",
                    "git@github.com:acme/web.git"], check=True, capture_output=True)
    assert_remote_matches(repo, "acme/web")                     # ssh form also accepted


def test_assert_remote_matches_rejects_wrong_hosted_remote(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                    "https://github.com/acme/api.git"], check=True, capture_output=True)
    with pytest.raises(WorktreeError, match="repo mismatch"):
        assert_remote_matches(repo, "acme/web")                 # clone is api, task routed to web


def test_assert_remote_matches_skips_local_path_remote(tmp_path):
    """A local bare-repo remote (tests, air-gapped setups) carries no owner/name — the guard is
    a no-op rather than a false positive."""
    repo = _init_repo(tmp_path / "repo")
    _add_remote(repo)                                           # origin is a filesystem path
    assert_remote_matches(repo, "acme/web")                     # no raise


# ── CLI repo-map parsing ────────────────────────────────────────────
def test_parse_repo_map_builds_name_to_path():
    from runner.companion.__main__ import _parse_repo_map

    m = _parse_repo_map(["acme/api=/repos/api", "acme/web=/repos/web"])
    assert m == {"acme/api": "/repos/api", "acme/web": "/repos/web"}


def test_parse_repo_map_rejects_malformed():
    from runner.companion.__main__ import _parse_repo_map

    with pytest.raises(SystemExit):
        _parse_repo_map(["acme/api"])                           # no =PATH


# ── build orchestration ─────────────────────────────────────────────
def test_build_allowlist_excludes_codehost_and_network():
    assert {"Read", "Write", "Edit", "Bash"} <= set(BUILD_ALLOWED_TOOLS)
    assert any(t.startswith("mcp__platform-state__") for t in BUILD_ALLOWED_TOOLS)
    assert not any("codehost" in t.lower() for t in BUILD_ALLOWED_TOOLS)
    assert "WebFetch" not in BUILD_ALLOWED_TOOLS and "WebSearch" not in BUILD_ALLOWED_TOOLS


def _task(**over) -> BuildTask:
    base = dict(run_id="r", tenant_id="T", project_id="p", work_item_id="w",
                work_item_key="ST-7", repo="o/r", base="main", manifest="M", agent_body="B",
                model="claude-x", api_url="http://plat", runner_token="tok")
    base.update(over)
    return BuildTask(**base)


def test_build_mcp_servers_points_at_remote_proxy():
    cfg = build_mcp_servers(_task())["platform-state"]
    assert cfg["args"] == ["-m", "runner.companion.state_mcp"]
    assert cfg["env"]["RUNNER_TOKEN"] == "tok"
    assert cfg["env"]["RUNNER_TENANT_ID"] == "T"
    assert cfg["env"]["RUNNER_API_URL"] == "http://plat"


# ── P3-09bR-3: Playwright MCP is phase-scoped to 09b ─────────────────
def test_build_mcp_servers_adds_playwright_only_for_test_automation():
    # 07 implementation build: no browser.
    assert "playwright" not in build_mcp_servers(_task(phase="implementation"))
    # 09b test-automation build: a headless Playwright stdio server is added.
    servers = build_mcp_servers(_task(phase="test_automation"))
    assert "platform-state" in servers        # still there
    pw = servers["playwright"]
    assert pw["command"] == "npx"
    assert "@playwright/mcp@latest" in pw["args"] and "--headless" in pw["args"]


def test_allowed_tools_for_extends_only_test_automation():
    impl = allowed_tools_for("implementation")
    assert impl == BUILD_ALLOWED_TOOLS                     # unchanged for 07/11
    assert not any(t.startswith("mcp__playwright__") for t in impl)
    auto = allowed_tools_for("test_automation")
    assert set(BUILD_ALLOWED_TOOLS) <= set(auto)           # superset
    assert set(PLAYWRIGHT_MCP_TOOLS) <= set(auto)          # + the browser surface


def test_phase_allowlist_permits_playwright_for_09b_only():
    nav = "mcp__playwright__browser_navigate"
    # Allowed when the phase is test-automation…
    assert_phase_allowlist([*BUILD_ALLOWED_TOOLS, nav],
                           allowed=BUILD_ALLOWED_TOOLS, phase="test_automation")   # no raise
    # …and rejected for any other phase (default/07).
    with pytest.raises(AllowlistViolation):
        assert_phase_allowlist([*BUILD_ALLOWED_TOOLS, nav], allowed=BUILD_ALLOWED_TOOLS)


def test_phase_allowlist_still_blocks_codehost_and_network_in_09b():
    # The 09b exception is ONLY the curated Playwright surface — CodeHost / arbitrary network
    # stay forbidden even in the test-automation phase.
    for rogue in ("mcp__codehost__merge_pull_request", "WebFetch",
                  "mcp__playwright__browser_network_requests"):  # network tool NOT on the surface
        with pytest.raises(AllowlistViolation):
            assert_phase_allowlist([*BUILD_ALLOWED_TOOLS, rogue],
                                   allowed=BUILD_ALLOWED_TOOLS, phase="test_automation")


# ── P3-09bR-2: preview app bring-up ─────────────────────────────────
class _FakeStdout:
    def __init__(self, lines):
        self._lines = list(lines)

    def readline(self):
        return self._lines.pop(0) if self._lines else ""


class _FakePopen:
    """A stand-in for a preview server process: yields `lines` on stdout, `poll()` returns
    `returncode` (None ⇒ still running)."""

    def __init__(self, *, lines=(), returncode=None):
        self.stdout = _FakeStdout(lines)
        self.returncode = returncode        # real Popen exposes this after poll()
        self.pid = 999_999

    def poll(self):
        return self.returncode


def _pol(task):
    return EgressPolicy.for_task(task)


def test_provision_preview_none_for_non_test_automation():
    task = _task(phase="implementation", preview_start={"command": "npm run dev", "port": 5173})
    assert provision_preview_app(Path("."), task, _pol(task)) is None


def test_provision_preview_fails_loud_without_config():
    task = _task(phase="test_automation", preview_start={})
    with pytest.raises(PreviewError):
        provision_preview_app(Path("."), task, _pol(task))


def test_provision_preview_uses_manual_url_and_starts_nothing(monkeypatch):
    # A configured preview URL wins over auto-start: the URL is used as-is and NO process starts.
    import runner.companion.runner as runner_mod

    monkeypatch.setattr(runner_mod, "_http_ok", lambda url: True)

    def _no_start(*a, **k):
        raise AssertionError("must not start a process when a preview URL is set")

    monkeypatch.setattr(subprocess, "Popen", _no_start)
    task = _task(phase="test_automation", preview_url="http://127.0.0.1:4000/",
                 preview_start={"command": "npm run dev", "port": 5173})
    handle = provision_preview_app(Path("."), task, _pol(task))
    assert handle.proc is None                       # borrowed, nothing to tear down
    assert handle.url == "http://127.0.0.1:4000" and handle.port == 4000
    teardown_preview_app(handle)                     # no-op, must not raise


def test_provision_preview_manual_url_fails_loud_when_unreachable(monkeypatch):
    import runner.companion.runner as runner_mod

    monkeypatch.setattr(runner_mod, "_http_ok", lambda url: False)   # app not running
    task = _task(phase="test_automation", preview_url="http://127.0.0.1:4000")
    with pytest.raises(PreviewError, match="not reachable"):
        provision_preview_app(Path("."), task, _pol(task))


def test_provision_preview_ready_via_log(monkeypatch):
    import subprocess

    monkeypatch.setattr(
        subprocess, "Popen",
        lambda *a, **k: _FakePopen(lines=["starting…", "Local: http://127.0.0.1:5173/"]))
    task = _task(phase="test_automation",
                 preview_start={"command": "npm run dev", "port": 5173,
                                "ready_log": "Local:", "ready_timeout_s": 5})
    handle = provision_preview_app(Path("."), task, _pol(task))
    assert isinstance(handle, PreviewHandle)
    assert handle.url == "http://127.0.0.1:5173" and handle.port == 5173


def test_provision_preview_raises_on_early_exit(monkeypatch):
    import subprocess

    monkeypatch.setattr(
        subprocess, "Popen",
        lambda *a, **k: _FakePopen(lines=["boom: address already in use"], returncode=1))
    task = _task(phase="test_automation",
                 preview_start={"command": "npm run dev", "port": 5173,
                                "ready_log": "Local:", "ready_timeout_s": 5})
    with pytest.raises(PreviewError, match="exited before becoming ready"):
        provision_preview_app(Path("."), task, _pol(task))


def test_teardown_preview_app_stops_a_real_process():
    import os
    import subprocess
    import sys

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                            start_new_session=(os.name == "posix"))
    teardown_preview_app(PreviewHandle(url="http://127.0.0.1:1", proc=proc, port=1))
    assert proc.poll() is not None                 # actually stopped


def test_teardown_preview_app_is_noop_on_none():
    teardown_preview_app(None)                      # no raise


def test_to_build_report_carries_preview_url():
    out = to_build_report({"status": "ok", "branch": "b",
                           "preview_url": "http://127.0.0.1:5173"})
    assert out["preview_url"] == "http://127.0.0.1:5173"


# ── P3-09bR-4: base_url injection + Playwright origin scoping ────────
def test_manifest_with_preview_injects_url_and_substitutes_tokens():
    manifest = "# Project\nNavigate to [base_url]/login and [app_url].\n"
    out = manifest_with_preview(manifest, "http://127.0.0.1:5173")
    assert out.startswith("# Preview Environment")
    assert "Base URL: http://127.0.0.1:5173" in out
    assert "[base_url]" not in out and "[app_url]" not in out
    assert "http://127.0.0.1:5173/login" in out          # token substituted in place


def test_manifest_with_preview_is_noop_without_url():
    manifest = "# Project\nNavigate to [base_url].\n"
    assert manifest_with_preview(manifest, "") == manifest


def test_build_mcp_servers_scopes_playwright_to_the_preview_origin():
    task = _task(phase="test_automation")
    # No URL yet → no origin restriction flag.
    args_no_url = build_mcp_servers(task)["playwright"]["args"]
    assert "--allowed-origins" not in args_no_url
    # URL known → the browser is origin-scoped to exactly that preview host.
    args = build_mcp_servers(task, preview_url="http://127.0.0.1:5173")["playwright"]["args"]
    assert args[args.index("--allowed-origins") + 1] == "http://127.0.0.1:5173"


def test_inject_environment_sets_and_restores(monkeypatch):
    import os

    monkeypatch.delenv("DB_PW", raising=False)
    task = _task(secrets={"DB_PW": "s3cret"})
    with inject_environment(task):
        assert os.environ["DB_PW"] == "s3cret"
    assert "DB_PW" not in os.environ           # restored; secret never persisted to a file


class _FakeDriver:
    def __init__(self):
        self.captured = {}

    async def run_build_task(self, *, manifest, agent_spec, repo_workspace, mcp_servers,
                             allowed_tools, work_item):
        self.captured.update(workspace=repo_workspace, allowed=allowed_tools,
                             manifest=manifest, model=agent_spec.recommended_model,
                             wi=work_item.id)
        (Path(repo_workspace) / "impl.py").write_text("x = 1\n")   # the agent's change
        return RunResult(outputs={"result": "done"}, artifacts=[], cost_usd=0.02,
                         raw_messages=[])


async def test_run_build_provisions_runs_in_worktree_and_tears_down(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    bare = _add_remote(repo)
    driver = _FakeDriver()
    out = await run_build(_task(work_item_key="ST-7"), driver=driver, repo_path=repo,
                          worktrees_root=tmp_path / "wt")
    assert out["branch"] == "feature/ST-7"
    assert "impl.py" in out["changed_files"] and out["cost_usd"] == 0.02
    assert str(driver.captured["workspace"]).endswith("ST-7")     # ran in the worktree
    assert "Bash" in driver.captured["allowed"]
    assert not any("codehost" in t.lower() for t in driver.captured["allowed"])
    assert not (tmp_path / "wt" / "ST-7").exists()                # worktree torn down
    # G2: the agent's change is committed and pushed to origin/feature/ST-7 (head_sha reported).
    assert out["status"] == "ok" and len(out["head_sha"]) == 40
    pushed = subprocess.run(
        ["git", "-C", str(bare), "log", "-1", "--format=%H %s", "feature/ST-7"],
        check=True, capture_output=True, text=True).stdout.strip()
    sha, _, subject = pushed.partition(" ")
    assert sha == out["head_sha"]
    assert subject == "feat(ST-7): ST-7"                          # derived Conventional Commit


async def test_run_build_derives_commit_subject_from_title(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    bare = _add_remote(repo)
    task = _task(work_item_key="WI-18", work_item_title="TASK-001: venv setup",
                 work_item_type="task")
    out = await run_build(task, driver=_FakeDriver(), repo_path=repo,
                          worktrees_root=tmp_path / "wt")
    subject = subprocess.run(
        ["git", "-C", str(bare), "log", "-1", "--format=%s", "feature/WI-18"],
        check=True, capture_output=True, text=True).stdout.strip()
    assert subject == "feat(WI-18): TASK-001: venv setup"
    assert out["head_sha"]


async def test_run_build_secret_block_does_not_commit_or_push(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path / "repo")
    bare = _add_remote(repo)
    import dataclasses

    import runner.companion.runner as runner_mod

    @dataclasses.dataclass
    class _Finding:
        rule: str = "aws_key"
        path: str = "impl.py"
        line: int = 1
    monkeypatch.setattr(runner_mod, "scan_worktree", lambda wt: [_Finding()])
    out = await run_build(_task(work_item_key="ST-9"), driver=_FakeDriver(), repo_path=repo,
                          worktrees_root=tmp_path / "wt")
    assert out["status"] == "secret_blocked" and "head_sha" not in out
    # nothing was pushed — the feature branch never reaches the remote
    branches = subprocess.run(["git", "-C", str(bare), "branch", "--list", "feature/ST-9"],
                              check=True, capture_output=True, text=True).stdout.strip()
    assert branches == ""


class _NoOpDriver:
    """An agent that makes NO file change — e.g. a retry onto a branch whose work is already done."""

    async def run_build_task(self, *, manifest, agent_spec, repo_workspace, mcp_servers,
                             allowed_tools, work_item):
        return RunResult(outputs={"result": "noop"}, artifacts=[], cost_usd=0.01, raw_messages=[])


def test_commits_ahead_of_base_counts_branch_work(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    wt = provision_worktree(repo_path=repo, branch="feature/ST-1", base="main",
                            worktree_path=tmp_path / "wt" / "ST-1")
    assert commits_ahead_of_base(wt, "main") == 0          # fresh branch off main
    (wt / "impl.py").write_text("x = 1\n")
    commit_all(wt, "work")
    assert commits_ahead_of_base(wt, "main") == 1          # one commit beyond base


async def test_retry_onto_already_built_branch_reports_tip_not_empty(tmp_path):
    """A build re-dispatched onto a branch a prior attempt already pushed must NOT fail as an
    empty build just because THIS run added nothing. The worktree continues from the branch's
    remote tip (S.No 162), the agent makes no new change, but the branch already carries real
    work — so the companion reports the branch tip as head_sha and the saga opens the PR against
    it (reproduces the 'Empty build' seen on Retry run)."""
    repo = _init_repo(tmp_path / "repo")
    bare = _add_remote(repo)

    # Attempt 1: a real build commits + pushes feature/ST-7.
    first = await run_build(_task(work_item_key="ST-7"), driver=_FakeDriver(), repo_path=repo,
                            worktrees_root=tmp_path / "wt1")
    assert first["status"] == "ok" and len(first["head_sha"]) == 40
    tip = first["head_sha"]

    # Retry: the agent makes NO change; the worktree continues from origin/feature/ST-7.
    out = await run_build(_task(work_item_key="ST-7"), driver=_NoOpDriver(), repo_path=repo,
                          worktrees_root=tmp_path / "wt2")
    assert out["changed_files"] == []                      # nothing new this run
    assert out["status"] == "ok"
    assert out["head_sha"] == tip                          # reports the existing branch tip …
    # … so the saga's empty-build guard (head_sha or changed_files) does NOT trip.
    assert bool(out["head_sha"] or out["changed_files"])


def test_to_build_report_surfaces_redacted_secret_findings():
    """Observability: a secret block must carry the redacted findings (kind + path:line +
    redacted preview) in `message` so they reach the build.failed reason / run console — never
    the raw secret value, and bounded no matter how many findings there are."""
    from runner.companion.runner import to_build_report
    result = {"status": "secret_blocked", "branch": "feature/ST-9", "secret_findings": [
        {"kind": "jwt", "path": "app/tests/test_auth.py", "line": 14,
         "preview": "eyJ0***9a (148 chars)"},
        {"kind": "high_entropy_secret", "path": "app/core/config.py", "line": 8,
         "preview": "Xy3K***2p (44 chars)"},
    ]}
    rep = to_build_report(result)
    assert rep["status"] == "failed"
    msg = rep["message"]
    assert "2 finding(s)" in msg
    assert "[jwt] app/tests/test_auth.py:14" in msg           # kind + path:line surfaced
    assert "[high_entropy_secret] app/core/config.py:8" in msg
    assert "eyJ0***9a" in msg and "Xy3K***2p" in msg          # redacted previews travel


def test_to_build_report_caps_secret_findings_at_eight():
    from runner.companion.runner import to_build_report
    findings = [{"kind": "high_entropy_secret", "path": f"f{i}.py", "line": i,
                 "preview": "ab***cd"} for i in range(12)]
    msg = to_build_report({"status": "secret_blocked", "branch": "b",
                           "secret_findings": findings})["message"]
    assert "12 finding(s)" in msg and "(+4 more)" in msg      # 8 shown + overflow marker
    assert "f11.py:11" not in msg                              # beyond the cap, not listed


def test_state_mcp_server_builds_with_a_client():
    from runner.companion.state_mcp import build_server

    server = build_server(RemoteStateClient(api_url="http://x", tenant_id="T", token="t"))
    assert server is not None                                     # FastMCP wired, no import error
