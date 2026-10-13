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


def test_provision_discards_a_stale_directory_left_by_a_failed_teardown(tmp_path):
    """A directory that is no longer a worktree must never be reused.

    Build worktrees are named `<worktrees_root>/<work_item_key>`, so every run and every
    remediation cycle for a work item targets the same path. When a teardown cannot finish (a
    locked file under node_modules on Windows), the files stay but the `.git` link goes. The
    agent then works happily against ordinary files, registers its artifact, and only the closing
    `git status` fails — the whole run wasted. Observed live on WI-54/PeopleDesk:
    `git status --porcelain failed: fatal: not a git repository`.
    """
    repo = _init_repo(tmp_path / "repo")
    wt_path = tmp_path / "wt" / "ST-STALE"
    wt = provision_worktree(repo_path=repo, branch="feature/ST-STALE", base="main",
                            worktree_path=wt_path)
    (wt / "left-behind.txt").write_text("from the previous cycle\n")

    # Exactly what a half-finished teardown leaves: the files, without the git link.
    (wt / ".git").unlink()
    assert wt_path.exists() and not (wt_path / ".git").exists()

    again = provision_worktree(repo_path=repo, branch="feature/ST-STALE", base="main",
                               worktree_path=wt_path)

    assert again == wt_path
    # Re-provisioned for real: git works again, and the orphaned file is gone.
    assert (wt_path / ".git").exists()
    assert changed_files(wt_path) == []
    assert not (wt_path / "left-behind.txt").exists()
    teardown_worktree(repo_path=repo, worktree_path=wt_path)


def test_provision_rejects_a_stale_directory_it_cannot_clear(tmp_path, monkeypatch):
    """If the stale directory cannot be removed, fail loudly BEFORE the agent runs.

    The point of the guard is that the run costs nothing when it trips. Silently continuing is
    what produced the eight-minute build that died at the final git step.
    """
    import runner.companion.worktree as wt_mod

    repo = _init_repo(tmp_path / "repo")
    wt_path = tmp_path / "wt" / "ST-LOCKED"
    wt = provision_worktree(repo_path=repo, branch="feature/ST-LOCKED", base="main",
                            worktree_path=wt_path)
    (wt / ".git").unlink()

    # Stand in for a Windows lock: removal does nothing, so the directory survives.
    monkeypatch.setattr(wt_mod.shutil, "rmtree", lambda *a, **k: None)

    with pytest.raises(WorktreeError, match="could not be removed"):
        provision_worktree(repo_path=repo, branch="feature/ST-LOCKED", base="main",
                           worktree_path=wt_path)


def test_teardown_reports_a_removal_it_could_not_complete(tmp_path, capsys):
    """A swallowed teardown failure poisons the NEXT run, so it must at least be visible."""
    repo = _init_repo(tmp_path / "repo")
    wt_path = tmp_path / "wt" / "ST-NOISY"
    provision_worktree(repo_path=repo, branch="feature/ST-NOISY", base="main",
                       worktree_path=wt_path)
    (wt_path / ".git").unlink()          # git can no longer remove it as a worktree

    teardown_worktree(repo_path=repo, worktree_path=wt_path)   # must not raise

    assert wt_path.exists()
    assert "could not remove worktree" in capsys.readouterr().err


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


def test_playwright_headed_toggle(monkeypatch):
    # Default (unattended): headless so no window pops up on the dev laptop.
    monkeypatch.delenv("SDLC_COMPANION_HEADED", raising=False)
    assert "--headless" in build_mcp_servers(_task(phase="test_automation"))["playwright"]["args"]
    # SDLC_COMPANION_HEADED=1 (attended local run): drop --headless to watch the agent drive
    # the browser live.
    monkeypatch.setenv("SDLC_COMPANION_HEADED", "1")
    args = build_mcp_servers(_task(phase="test_automation"))["playwright"]["args"]
    assert "--headless" not in args
    assert "@playwright/mcp@latest" in args


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


def test_manifest_headed_instruction_only_when_enabled(monkeypatch):
    manifest = "# Project\nNavigate to [base_url].\n"
    # Default (unattended): no headed instruction — the generated config stays headless.
    monkeypatch.delenv("SDLC_COMPANION_HEADED", raising=False)
    assert "headed" not in manifest_with_preview(manifest, "http://127.0.0.1:5173").lower()
    # Attended: the agent is told to generate a headed (env-keyed) Playwright config.
    monkeypatch.setenv("SDLC_COMPANION_HEADED", "1")
    out = manifest_with_preview(manifest, "http://127.0.0.1:5173")
    assert "headless: !process.env.SDLC_COMPANION_HEADED" in out


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


def test_to_build_report_carries_the_findings_as_structured_data():
    """D6: the prose `message` is capped at 8, so on a large block the platform used to know the
    COUNT and only 8 identities — findings 9-N existed nowhere. The structured list travels too,
    so a block is diagnosable after the fact and can seed the retry's prior-attempt context."""
    from runner.companion.runner import to_build_report
    findings = [{"kind": "high_entropy_secret", "path": f"f{i}.py", "line": i,
                 "preview": "ab***cd"} for i in range(12)]
    rep = to_build_report({"status": "secret_blocked", "branch": "b",
                           "secret_findings": findings})
    assert len(rep["secret_findings"]) == 12          # all 12, not the 8 the prose shows
    assert rep["secret_findings"][11]["path"] == "f11.py"
    assert "f11.py:11" not in rep["message"]          # ...while the prose stays bounded


def test_the_carried_findings_are_bounded_and_never_hold_a_raw_value():
    """The payload rides a Temporal signal, so it is capped — and it carries only the previews the
    companion already redacted, never a value."""
    from runner.companion.runner import _MAX_CARRIED_FINDINGS, to_build_report
    findings = [{"kind": "high_entropy_secret", "path": f"f{i}.py", "line": i,
                 "preview": "ab***cd"} for i in range(_MAX_CARRIED_FINDINGS + 25)]
    rep = to_build_report({"status": "secret_blocked", "branch": "b",
                           "secret_findings": findings})
    assert len(rep["secret_findings"]) == _MAX_CARRIED_FINDINGS
    assert f"{_MAX_CARRIED_FINDINGS + 25} finding(s)" in rep["message"]   # true count survives
    assert all("***" in f["preview"] for f in rep["secret_findings"])


def test_a_clean_build_carries_no_secret_findings_key():
    """The new field is scoped to the block path — an ok build's report is unchanged."""
    from runner.companion.runner import to_build_report
    rep = to_build_report({"status": "ok", "branch": "b", "head_sha": "abc"})
    assert "secret_findings" not in rep


def test_state_mcp_server_builds_with_a_client():
    from runner.companion.state_mcp import build_server

    server = build_server(RemoteStateClient(api_url="http://x", tenant_id="T", token="t"))
    assert server is not None                                     # FastMCP wired, no import error


# ── the base must come from the remote, not a stale local ref (PeopleDesk, 2026-08-15) ───────
# A companion clone is only ever used to create feature branches — nobody checks `main` out in
# it, and `git fetch` does not move a local branch. So local `main` sits at whatever commit the
# clone was made at, forever. Observed in the pilot: local `main` was still the repository's
# FIRST commit, thirteen merged PRs behind, so the agent scaffolded a frontend that already
# existed. The build "succeeded" — only the merge revealed it was built against the wrong world.
def _advance_origin(bare: Path, tmp_path: Path, filename: str = "landed.py") -> str:
    """Simulate another PR merging into main while this clone isn't looking."""
    other = tmp_path / "other-clone"
    subprocess.run(["git", "clone", str(bare), str(other)], check=True, capture_output=True)
    for cfg in (("user.email", "o@o.test"), ("user.name", "Other")):
        subprocess.run(["git", "-C", str(other), "config", *cfg], check=True, capture_output=True)
    (other / filename).write_text("# merged by someone else\n")
    subprocess.run(["git", "-C", str(other), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(other), "commit", "-m", "another PR merged"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(other), "push", "origin", "main"],
                   check=True, capture_output=True)
    return filename


def test_a_new_branch_is_based_on_the_remote_not_a_stale_local_main(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    bare = _add_remote(repo)
    landed = _advance_origin(bare, tmp_path)

    # This clone never pulls — exactly the companion's real state.
    behind = subprocess.run(["git", "-C", str(repo), "rev-parse", "main"],
                            capture_output=True, text=True).stdout.strip()

    wt = provision_worktree(repo_path=repo, branch="feature/ST-FRESH", base="main",
                            worktree_path=tmp_path / "wt" / "ST-FRESH")

    assert (wt / landed).exists(), (
        "the worktree was based on the stale local main — the agent would build without seeing "
        "what has already merged")
    head = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert head != behind


def test_the_stale_base_bug_is_real_without_the_fetch(tmp_path):
    """Guards the guard: prove the scenario above genuinely fails when the base is taken from
    the local ref, so the test above cannot quietly stop testing anything."""
    repo = _init_repo(tmp_path / "repo")
    bare = _add_remote(repo)
    landed = _advance_origin(bare, tmp_path)

    # What the old code did: branch straight from the local `main`.
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-B", "feature/OLD",
                    str(tmp_path / "wt" / "OLD"), "main"], check=True, capture_output=True)

    assert not (tmp_path / "wt" / "OLD" / landed).exists()


def test_an_offline_companion_still_builds_from_its_local_base(tmp_path):
    """A fetch that cannot reach the remote must not fail the run — it falls back to the local
    ref, which is what this did before. A developer on a train keeps working."""
    repo = _init_repo(tmp_path / "repo")
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                    str(tmp_path / "nonexistent-remote.git")], check=True, capture_output=True)

    wt = provision_worktree(repo_path=repo, branch="feature/ST-OFFLINE", base="main",
                            worktree_path=tmp_path / "wt" / "ST-OFFLINE")

    assert wt.exists() and (wt / "README.md").exists()


def test_a_repo_with_no_remote_at_all_still_provisions(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    wt = provision_worktree(repo_path=repo, branch="feature/ST-NOREMOTE", base="main",
                            worktree_path=tmp_path / "wt" / "ST-NOREMOTE")
    assert wt.exists() and (wt / "README.md").exists()


def test_an_existing_remote_branch_still_wins_over_the_base(tmp_path):
    """The other half of the rule is unchanged: when a prior cycle already pushed the feature
    branch, we continue from ITS tip, not from base — however fresh base now is."""
    repo = _init_repo(tmp_path / "repo")
    bare = _add_remote(repo)

    first = provision_worktree(repo_path=repo, branch="feature/ST-CYCLE", base="main",
                               worktree_path=tmp_path / "wt" / "ST-CYCLE")
    (first / "cycle1.py").write_text("x = 1\n")
    commit_all(first, "cycle 1")
    push_branch(first, "feature/ST-CYCLE")
    teardown_worktree(repo_path=repo, worktree_path=first)

    _advance_origin(bare, tmp_path)          # main moves on underneath it

    second = provision_worktree(repo_path=repo, branch="feature/ST-CYCLE", base="main",
                                worktree_path=tmp_path / "wt" / "ST-CYCLE")
    assert (second / "cycle1.py").exists(), "a remediation cycle lost the prior cycle's work"


# ── the companion must write down what the engine said (Bugs S.No 146, second pass) ──────────
# Nine engine-exit builds, eight undiagnosable, because the companion kept no log file and the
# SDK's diagnostics are emitted through `logging` that nobody had configured.
def test_the_engine_log_captures_what_the_sdk_would_otherwise_discard(tmp_path):
    import logging

    from runner.companion.enginelog import setup_engine_log

    path = setup_engine_log(tmp_path)
    assert path is not None and path.parent == tmp_path
    try:
        # exactly the two records that carried the cause and went nowhere
        sdk = logging.getLogger("claude_agent_sdk._internal.transport.subprocess_cli")
        sdk.debug("Skipping non-JSON line from CLI stdout: %s", "Claude AI usage limit reached|1")
        logging.getLogger("claude_agent_sdk._internal.query").error(
            "Fatal error in message reader: Command failed with exit code 1")
        for h in logging.getLogger("claude_agent_sdk").handlers:
            h.flush()
        written = path.read_text(encoding="utf-8")
        assert "Claude AI usage limit reached" in written   # the DEBUG one — previously discarded
        assert "Fatal error in message reader" in written   # terminal-only before
    finally:
        lg = logging.getLogger("claude_agent_sdk")
        for h in list(lg.handlers):
            if getattr(h, "_sdlc_tag", ""):
                h.close()
                lg.removeHandler(h)


def test_setting_up_the_engine_log_twice_does_not_double_write(tmp_path):
    import logging

    from runner.companion.enginelog import setup_engine_log

    try:
        first = setup_engine_log(tmp_path)
        second = setup_engine_log(tmp_path)
        assert first == second
        tagged = [h for h in logging.getLogger("claude_agent_sdk").handlers
                  if getattr(h, "_sdlc_tag", "")]
        assert len(tagged) == 1, "serving twice in one process would duplicate every line"
    finally:
        lg = logging.getLogger("claude_agent_sdk")
        for h in list(lg.handlers):
            if getattr(h, "_sdlc_tag", ""):
                h.close()
                lg.removeHandler(h)


def test_an_unwritable_log_location_never_stops_the_companion(tmp_path):
    """A companion that cannot open its log must still run builds."""
    from runner.companion.enginelog import setup_engine_log

    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")            # a FILE where the log directory would go
    assert setup_engine_log(path=blocker / "sub" / "engine.log") is None


# ── Every granted tool must actually EXIST on the MCP server ────────────────────
#
# The gap this closes cost the accessibility judge and the keyboard journey their entire
# existence: seven tools were granted in `runner.BUILD_STATE_TOOLS` and routed in the platform's
# `_BUILD_STATE_TOOLS`, and never defined in `state_mcp.py` — the only file that puts a tool in
# front of an agent. A name in `allowed_tools` is a PERMISSION, not a tool. Both phases were
# dispatched, claimed, and ran to a standstill against a tool set that did not contain their
# work, their rulebook, or any way to answer.
#
# Nothing caught it because every layer was tested on its own and the seam between them was not.
# This is that seam, asserted as a set difference so a tool added to one list and forgotten in
# the other fails here rather than on somebody's first live run.


def _exposed_tool_names() -> set:
    from runner.companion.state_client import RemoteStateClient
    from runner.companion.state_mcp import build_server

    server = build_server(
        RemoteStateClient(api_url="http://x", tenant_id="T", token="t"),
        run_id="R1", phase="a11y_judge", project_id="P1",
    )
    return {t.name for t in server._tool_manager.list_tools()}


def test_every_granted_tool_is_actually_exposed_by_the_mcp_server():
    from runner.companion.runner import BUILD_STATE_TOOLS, REVIEW_ONLY_STATE_TOOLS

    # The review-only extras are checked by the SAME rule as the shared base. Granting a tool to
    # one agent and forgetting to expose it is the identical failure as forgetting it for all of
    # them — the allowlist says yes and the agent still cannot call it.
    granted = (set(BUILD_STATE_TOOLS) | set(REVIEW_ONLY_STATE_TOOLS)) - {"ask_human"}
    missing = sorted(granted - _exposed_tool_names())
    assert not missing, (
        f"granted in BUILD_STATE_TOOLS but never defined in state_mcp.py: {missing}. "
        f"The agent cannot call a tool the server does not expose, whatever the allowlist says."
    )


def test_the_judge_and_the_journey_can_reach_every_tool_their_bodies_name():
    """Named explicitly, not just covered by the set difference above.

    These are the seven that were missing. Spelling them out means a future edit that drops one
    fails with the phase it breaks in the message, rather than as an anonymous set element.
    """
    exposed = _exposed_tool_names()
    judge = {"get_a11y_batch", "get_wcag_grounding", "record_a11y_finding",
             "get_a11y_screenshots"}
    journey = {"get_a11y_journey", "record_a11y_journey_step",
               "record_a11y_journey_finding", "finish_a11y_journey"}
    assert judge <= exposed, f"09c_a11y_judge cannot work: {sorted(judge - exposed)}"
    assert journey <= exposed, f"09d_a11y_journey cannot work: {sorted(journey - exposed)}"


def test_the_agent_never_names_its_own_run_the_platform_binds_it():
    """`run_id` is bound at launch and must never be a parameter the agent supplies.

    Two reasons, and the second is the one that matters. The agent has no way to know its run id
    — nothing in the manifest carries it — so a tool that demanded it could only ever 400, which
    is exactly what `get_a11y_screenshots` did: its wrapper dropped `run_id_bound` and the
    platform rejected the call as `bad arguments`. And if the agent COULD name a run, it could
    file verdicts against a different one.
    """
    from runner.companion.state_client import RemoteStateClient
    from runner.companion.state_mcp import build_server

    calls = []

    class _Client(RemoteStateClient):
        def call(self, tool, **kw):
            calls.append((tool, kw))
            return {}

    server = build_server(_Client(api_url="http://x", tenant_id="T", token="t"),
                          run_id="RUN-42", project_id="PROJ-7")
    by_name = {t.name: t for t in server._tool_manager.list_tools()}

    run_bound = ["get_a11y_batch", "get_a11y_journey", "finish_a11y_journey"]
    for name in run_bound:
        params = set((by_name[name].parameters or {}).get("properties", {}))
        assert "run_id" not in params, f"{name} must not ask the agent for run_id"
        assert "tenant_id" not in params, f"{name} must not ask the agent for tenant_id"

    # And what it actually sends is the launch-bound run.
    import asyncio
    for name in run_bound:
        asyncio.run(server._tool_manager.call_tool(name, {}))
    assert [kw.get("run_id") for _, kw in calls] == ["RUN-42"] * len(run_bound)


def test_a_recorded_verdict_carries_the_run_and_project_it_belongs_to():
    """`record_a11y_finding` writes the result. Sent without the run, the platform has no way to
    attribute a verdict to the batch that asked for it."""
    from runner.companion.state_client import RemoteStateClient
    from runner.companion.state_mcp import build_server

    sent = {}

    class _Client(RemoteStateClient):
        def call(self, tool, **kw):
            sent[tool] = kw
            return {"ok": True}

    server = build_server(_Client(api_url="http://x", tenant_id="T", token="t"),
                          run_id="RUN-42", project_id="PROJ-7")
    import asyncio
    asyncio.run(server._tool_manager.call_tool("record_a11y_finding", {
        "element_id": "e1", "criteria": ["1.1.1"], "verdict": "fail",
        "confidence": 0.9, "evidence": "img with no alt", "suggested_fix": "add alt",
    }))
    kw = sent["record_a11y_finding"]
    assert kw["run_id"] == "RUN-42" and kw["project_id"] == "PROJ-7"
    assert kw["element_id"] == "e1" and kw["verdict"] == "fail"


def test_the_screenshot_tool_sends_the_run_it_was_launched_for():
    """The 400 the judge hit: the wrapper called the platform without `run_id`, whose signature
    is `get_a11y_screenshots(tenant_id, run_id, start=0)`, so every call came back as bad
    arguments — which the agent reported, accurately, as the run id not being injected."""
    from runner.companion.state_client import RemoteStateClient
    from runner.companion.state_mcp import build_server

    sent = {}

    class _Client(RemoteStateClient):
        def call(self, tool, **kw):
            sent[tool] = kw
            return {"images": [], "unseen": [], "total": 0, "returned": 0, "start": 0}

    server = build_server(_Client(api_url="http://x", tenant_id="T", token="t"),
                          run_id="RUN-42", project_id="PROJ-7")
    import asyncio
    asyncio.run(server._tool_manager.call_tool("get_a11y_screenshots", {"start": 0}))
    assert sent["get_a11y_screenshots"]["run_id"] == "RUN-42"


def test_the_batch_tool_pages_and_carries_the_cursor():
    """`get_a11y_batch` was a single call returning every screen — 80,000 characters on our own
    reference app's ten pages, which the judge could not hold and correctly refused to judge in
    part. It pages now, and the wrapper has to actually forward `start` or the judge loops on
    screen one forever."""
    from runner.companion.state_client import RemoteStateClient
    from runner.companion.state_mcp import build_server

    sent = {}

    class _Client(RemoteStateClient):
        def call(self, tool, **kw):
            sent[tool] = kw
            return {"screens": [], "total_elements": 0, "next_start": None}

    server = build_server(_Client(api_url="http://x", tenant_id="T", token="t"),
                          run_id="RUN-42", project_id="PROJ-7")
    by_name = {t.name: t for t in server._tool_manager.list_tools()}
    params = set((by_name["get_a11y_batch"].parameters or {}).get("properties", {}))
    assert params == {"start"}, f"the judge supplies only its cursor, got {params}"

    import asyncio
    asyncio.run(server._tool_manager.call_tool("get_a11y_batch", {"start": 25}))
    assert sent["get_a11y_batch"] == {"run_id": "RUN-42", "start": 25}
