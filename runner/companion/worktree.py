"""Managed git-worktree provisioning (Phase-2 §3, decision D9).

The companion edits a **dedicated worktree** off the developer's existing clone — a clean
`feature/<key>` branch isolated from their working copy — so the agent's change has a clean
base and the developer's uncommitted work is never touched. Platform scratch (`.sdlc/`) is
kept out of the diff via the worktree's local git exclude.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class WorktreeError(Exception):
    """A git worktree operation failed."""


def _git(cwd, *args, check=True) -> str:
    res = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True
    )
    if check and res.returncode != 0:
        raise WorktreeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout


def provision_worktree(*, repo_path, branch: str, base: str, worktree_path,
                       remote: str = "origin") -> Path:
    """Create (or reuse) a worktree at `worktree_path` on `branch`. Idempotent: an existing
    worktree path is returned as-is.

    Branch base selection (Bugs S.No 162 — cross-companion remediation continuity):
    a remediation cycle can be claimed by a DIFFERENT companion than the one that ran the
    original build (builds are claimable by any enrolled companion). That other clone either
    lacks the feature branch — so it would be recreated from `base` (main) — or holds a stale
    copy, either way MISSING the commits the earlier cycle already pushed. Building on that
    wrong base then gets the push rejected non-fast-forward (or silently diverges). So when the
    branch already exists on the REMOTE (a prior cycle pushed it), base the worktree on the
    remote tip `<remote>/<branch>` — the true shared source of the work-in-progress — so ANY
    companion continues exactly where the last cycle left off. This also subsumes the stale
    local-branch empty-build case (#145): we no longer trust a leftover local branch. Only when
    the remote has NO such branch (the very first build, or offline) do we branch from `base`."""
    repo_path = Path(repo_path)
    worktree_path = Path(worktree_path)
    if worktree_path.exists():
        return worktree_path
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    # Best-effort sync of the remote-tracking ref (force, so it always matches the remote). If the
    # remote has no such branch — first build — or we are offline, this is a no-op and we fall back.
    _git(repo_path, "fetch", remote, f"+{branch}:refs/remotes/{remote}/{branch}", check=False)
    remote_ref = f"refs/remotes/{remote}/{branch}"
    remote_sha = _git(repo_path, "rev-parse", "--verify", "--quiet", remote_ref,
                      check=False).strip()
    if remote_sha:
        # Continue from the remote tip: `-B` creates the local branch or RESETS a stale one to
        # `<remote>/<branch>`, checking it out in the fresh worktree (all prior cycles' commits,
        # whichever companion pushed them).
        _git(repo_path, "worktree", "add", "-B", branch, str(worktree_path), remote_ref)
    else:
        branch_exists = bool(_git(repo_path, "branch", "--list", branch).strip())
        if branch_exists:
            _git(repo_path, "worktree", "add", str(worktree_path), branch)
        else:
            _git(repo_path, "worktree", "add", "-b", branch, str(worktree_path), base)
    _exclude_platform_scratch(worktree_path)
    return worktree_path


def teardown_worktree(*, repo_path, worktree_path) -> None:
    """Remove the worktree (best-effort; the branch is left for the platform to dispose)."""
    _git(repo_path, "worktree", "remove", "--force", str(worktree_path), check=False)


def changed_files(worktree_path) -> list[str]:
    """The paths the agent changed in the worktree (porcelain, excludes platform scratch)."""
    out = _git(worktree_path, "status", "--porcelain")
    return [line[3:] for line in out.splitlines() if line.strip()]


def head_sha(worktree_path) -> str:
    """The current commit sha of the worktree's branch."""
    return _git(worktree_path, "rev-parse", "HEAD").strip()


def commit_all(worktree_path, message: str) -> str | None:
    """Stage and commit every change on the worktree's feature branch (D2: the platform owns
    Git side-effects — the agent never runs git). `.sdlc/` scratch is already git-excluded, so
    it never enters the commit. Returns the new commit sha, or None if there was nothing to
    commit (the agent produced no change)."""
    _git(worktree_path, "add", "-A")
    if not _git(worktree_path, "status", "--porcelain").strip():
        return None
    _git(worktree_path, "commit", "--no-verify", "-m", message)
    return head_sha(worktree_path)


def assert_remote_matches(worktree_path, repo: str, *, remote: str = "origin") -> None:
    """Defense in depth for multi-repo: fail before pushing if the clone's `origin` isn't the
    repo the platform routed this work item to (`task.repo`). A mis-mapped `--repo NAME=PATH`
    would otherwise push a work item's branch to the wrong GitHub repo, where the platform then
    can't find the head ref when it opens the PR. Matches `owner/name` against the remote URL in
    both HTTPS (`.../owner/name(.git)`) and SSH (`git@host:owner/name(.git)`) forms. Only *hosted*
    remotes are checked — a local filesystem remote (e.g. a test bare repo) carries no owner/name
    and is left alone."""
    url = _git(worktree_path, "remote", "get-url", remote, check=False).strip()
    if not url:
        return  # no origin at all — nothing to verify against
    is_hosted = url.startswith(("http://", "https://", "ssh://")) or "@" in url
    if not is_hosted:
        return  # local/path remote — can't carry an owner/name to compare
    norm = url[:-4] if url.endswith(".git") else url
    slug = repo.strip("/")
    if not (norm.endswith("/" + slug) or norm.endswith(":" + slug)):
        raise WorktreeError(
            f"repo mismatch: work item routed to {repo!r} but the clone's {remote} remote is "
            f"{url!r}. Check the --repo {repo}=<path> mapping points at the right clone.")


def push_branch(worktree_path, branch: str, *, remote: str = "origin") -> None:
    """Push the committed feature branch to the remote so the platform can open the PR against
    a real ref (D2). Uses the developer clone's own remote/credentials — the platform's token
    is only for the CodeHost REST surface (open/merge/status)."""
    _git(worktree_path, "push", "-u", remote, branch)


def diff(worktree_path) -> str:
    return _git(worktree_path, "diff")


def _exclude_platform_scratch(worktree_path) -> None:
    """Keep `.sdlc/` (the rendered manifest etc.) out of the diff via the worktree's local
    exclude — never committed, never shown to the developer's review."""
    rel = _git(worktree_path, "rev-parse", "--git-path", "info/exclude").strip()
    excl = Path(rel)
    if not excl.is_absolute():
        excl = Path(worktree_path) / excl
    excl.parent.mkdir(parents=True, exist_ok=True)
    existing = excl.read_text() if excl.exists() else ""
    if ".sdlc/" not in existing:
        with excl.open("a", encoding="utf-8") as f:
            f.write("\n.sdlc/\n")
