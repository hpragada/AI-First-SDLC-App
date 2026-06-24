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


def provision_worktree(*, repo_path, branch: str, base: str, worktree_path) -> Path:
    """Create (or reuse) a worktree at `worktree_path` on `branch` (off `base`). Idempotent:
    an existing worktree path is returned as-is; an existing branch is attached, not recreated."""
    repo_path = Path(repo_path)
    worktree_path = Path(worktree_path)
    if worktree_path.exists():
        return worktree_path
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
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
