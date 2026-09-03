"""Managed git-worktree provisioning (Phase-2 §3, decision D9).

The companion edits a **dedicated worktree** off the developer's existing clone — a clean
`feature/<key>` branch isolated from their working copy — so the agent's change has a clean
base and the developer's uncommitted work is never touched. Platform scratch (`.sdlc/`) is
kept out of the diff via the worktree's local git exclude.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


class WorktreeError(Exception):
    """A git worktree operation failed."""


#: Upper bound on any single git operation here. Provisioning talks to the REMOTE (`ls-remote`,
#: `fetch`, `push`), so a slow or half-open network connection can leave it waiting with no end
#: — and until now there was NO timeout at all on this path, so "the companion is stuck" had no
#: floor. Generous enough for a large fetch over a poor link, finite enough that a wedged
#: operation surfaces as an error the developer can see instead of silence (B5).
_GIT_TIMEOUT = 300


def _git(cwd, *args, check=True) -> str:
    # `stdin=DEVNULL` for the same reason as `codeintel/builtin.py::_git` — `capture_output`
    # covers stdout/stderr only, so the child would otherwise inherit ours. A git that decides to
    # prompt (credentials, a stale lock) then blocks on a pipe nobody feeds, with no timeout here
    # to end it. Empty input makes it fail fast instead of hanging the companion.
    try:
        res = subprocess.run(
            ["git", "-C", str(cwd), *args],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=_GIT_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise WorktreeError(
            f"git {' '.join(args)} timed out after {_GIT_TIMEOUT}s in {cwd}") from exc
    if check and res.returncode != 0:
        raise WorktreeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout


def _is_live_worktree(worktree_path) -> bool:
    """Whether the path is still a real git worktree, not just a directory of files.

    Two stale states both look perfectly fine to the agent — it is writing ordinary files — and
    surface only when git is finally asked to act, by which point the whole run is wasted:

      1. the `.git` link is gone, but the files were left behind (a teardown that could not
         finish);
      2. the `.git` file survives but points at an admin directory that has since been pruned.

    The existence check catches (1), and also stops a worktrees root that happens to sit INSIDE
    another clone from reporting that parent's git dir as its own. Case (2) needs git itself:
    `rev-parse --git-dir` prints nothing on stdout when it cannot resolve one.
    """
    if not (Path(worktree_path) / ".git").exists():
        return False
    return bool(_git(worktree_path, "rev-parse", "--git-dir", check=False).strip())


def _ref_exists(repo_path, ref: str) -> bool:
    """Whether `ref` resolves in this repo.

    Used to decide whether a freshly-fetched remote base is actually available: an offline
    companion, or one whose remote refused the fetch, must still be able to build — so the
    caller falls back to the local ref rather than failing the run.
    """
    return bool(
        _git(repo_path, "rev-parse", "--verify", "--quiet", ref, check=False).strip()
    )


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
    the remote has NO such branch (the very first build, or offline) do we branch from `base` —
    and `base` is fetched from the remote first, for exactly the same reason: a local ref is
    whatever that one clone last happened to update, not the shared truth of the project."""
    repo_path = Path(repo_path)
    worktree_path = Path(worktree_path)
    if worktree_path.exists():
        if _is_live_worktree(worktree_path):
            return worktree_path
        # The directory is there but it is no longer a worktree — what a teardown that could not
        # finish leaves behind. Build worktrees are named `<worktrees_root>/<work_item_key>`, so
        # EVERY run and every remediation cycle for a work item targets this same path; on
        # Windows a single locked file under `node_modules` is enough to strand it (observed on
        # WI-54 "set up the pnpm monorepo workspace"). Reusing it silently is the whole bug: the
        # agent works happily for minutes, registers its artifact, and only the closing
        # `git status` fails — throwing the entire run away. Clear it and provision fresh.
        print(f"[companion] {worktree_path} exists but is not a git worktree (stale directory "
              f"from an earlier cycle) — discarding it and provisioning a fresh one",
              file=sys.stderr, flush=True)
        _git(repo_path, "worktree", "prune", check=False)   # drop any dangling admin entry
        shutil.rmtree(worktree_path, ignore_errors=True)
        if worktree_path.exists():
            raise WorktreeError(
                f"{worktree_path} is not a git worktree and could not be removed — something "
                f"is still holding files in it (a dev server or an editor?). Stop it, delete "
                f"the directory, and retry the run"
            )
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    # Ask the remote AUTHORITATIVELY whether the branch exists right now. `ls-remote` queries the
    # server directly, so a stale local remote-tracking ref (left when the branch was deleted on
    # the remote — `git fetch` does not prune it) can never resurrect a dead branch at an old
    # commit. Offline/no-remote → empty → treated as "no remote branch", we branch from `base`.
    ls = _git(repo_path, "ls-remote", "--heads", remote, branch, check=False).strip()
    if ls:
        # A prior cycle pushed this branch (possibly from another companion) — continue from its
        # remote tip. Refresh the remote-tracking ref, then `-B` creates-or-RESETS the local branch
        # to that tip and checks it out in the fresh worktree (all prior cycles' commits).
        _git(repo_path, "fetch", remote, f"+{branch}:refs/remotes/{remote}/{branch}", check=False)
        start = f"refs/remotes/{remote}/{branch}"
    else:
        # First build, or the branch was deleted. `base` names the developer's LOCAL branch — and
        # git NEVER moves a local branch on fetch, so a clone where nobody ever checks `main` out
        # stays at whatever commit it was cloned at, indefinitely. Observed on the PeopleDesk
        # pilot: a companion whose local `main` was still the repository's FIRST commit, thirteen
        # merged PRs behind, so the agent scaffolded a frontend that already existed and the PR
        # came back with 23 conflicted files and two rival auth contexts. The failure is silent —
        # the build succeeds, and only the merge reveals it was built against the wrong world.
        # Same reasoning as the branch path above: ask the remote, never trust a local ref.
        remote_base = f"refs/remotes/{remote}/{base}"
        _git(repo_path, "fetch", remote, f"+{base}:{remote_base}", check=False)
        # Offline, no remote, or a refused fetch → fall back to the local ref, which is what this
        # did before. A companion with no network must still be able to build.
        start = remote_base if _ref_exists(repo_path, remote_base) else base
    _git(repo_path, "worktree", "add", "-B", branch, str(worktree_path), start)
    _exclude_platform_scratch(worktree_path)
    # Fail HERE, not eight minutes from now. Everything downstream — `changed_files`,
    # `commit_all`, `head_sha` — assumes this is a worktree, and each only finds out at the very
    # end of the build. Checking once, before the agent is handed the path, turns a wasted run
    # into an immediate, legible error.
    if not _is_live_worktree(worktree_path):
        raise WorktreeError(
            f"provisioned {worktree_path} but it is not a usable git worktree — refusing to run "
            f"the build against it"
        )
    return worktree_path


def teardown_worktree(*, repo_path, worktree_path) -> None:
    """Remove the worktree (best-effort; the branch is left for the platform to dispose).

    Best-effort but NOT silent. A removal that fails leaves the files on disk without their git
    link, and the next cycle for this work item targets that exact path — so a swallowed failure
    here is what poisons the *next* run rather than this one. `provision_worktree` now detects
    and clears such a directory; this makes the original cause visible in the companion's own
    output instead of only ever surfacing later as a build that died on `git status`.

    Never raises: this runs in a `finally`, where raising would mask the real error.
    """
    _git(repo_path, "worktree", "remove", "--force", str(worktree_path), check=False)
    if Path(worktree_path).exists():
        print(f"[companion] could not remove worktree {worktree_path} - it is left on disk "
              f"without its git link. The next build for this work item will discard and "
              f"re-create it. Something may still be holding files in it (a dev server?)",
              file=sys.stderr, flush=True)


#: Directories a build *generates* — dependencies it installed, caches it wrote. They are
#: never the agent's work, they must never be committed to the client's repo, and the secret
#: scanner must never read them: 30,000 vendored files produce nothing but noise (a single
#: `npm install` yielded 535 "findings", every one of them a JavaScript variable name).
#:
#: **Only unambiguous names are listed here.** `dist`, `build`, `out`, `target`, `bin` and
#: `vendor` were considered and deliberately left out: each is a real source directory in some
#: ecosystem (Go commits `vendor/` on purpose), and excluding a directory means silently not
#: committing the work inside it — the safe direction to be wrong in is to include too little.
#: The general answer to generated output is a `.gitignore`, which is the project's to own;
#: this list is the backstop for the cases that are never anything else.
GENERATED_DIRS = frozenset({
    "node_modules", "bower_components",
    ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".next", ".nuxt", ".svelte-kit", ".turbo", ".parcel-cache", ".gradle",
})


def _segments(rel: str) -> list[str]:
    return rel.replace("\\", "/").strip("/").split("/")


def is_generated_path(rel: str) -> bool:
    """True when any segment of the path is a generated/vendored directory — so a nested
    `frontend/node_modules/...` is caught as surely as a top-level one."""
    return any(seg in GENERATED_DIRS for seg in _segments(rel))


def _porcelain(worktree_path) -> list[tuple[str, str]]:
    """(status, path) per changed entry.

    `--untracked-files=all` is load-bearing, not a tidy-up. Git's default collapses a brand-new
    directory to a single `dir/` entry, and the secret scanner — which asks "is this a file?"
    before reading it — then skips the whole directory in silence. A real credential in any
    newly created folder therefore passed the gate and was committed and pushed. Listing
    untracked files individually is what closes that hole; `GENERATED_DIRS` below is what stops
    the same change drowning the scan in vendored dependencies.
    """
    out = _git(worktree_path, "status", "--porcelain", "--untracked-files=all")
    return [(line[:2], line[3:]) for line in out.splitlines() if line.strip()]


def generated_roots(worktree_path) -> list[str]:
    """The generated directories present in this worktree but NOT tracked by git.

    Scoped to untracked on purpose: a repository that deliberately commits a vendored directory
    keeps working exactly as before, because its files never appear as untracked and so never
    reach this list. Returned as directory roots (`frontend/node_modules`), not the files under
    them — a command line carrying 30,000 paths would exceed the OS limit.
    """
    roots: set[str] = set()
    for status, rel in _porcelain(worktree_path):
        if status != "??":
            continue
        segments = _segments(rel)
        for index, segment in enumerate(segments):
            if segment in GENERATED_DIRS:
                roots.add("/".join(segments[: index + 1]))
                break
    return sorted(roots)


def changed_files(worktree_path) -> list[str]:
    """The paths the agent changed in the worktree (porcelain, excludes platform scratch).

    Untracked generated directories are omitted — they are the machine's output, not the
    agent's work, and reporting 30,000 dependency files as "changed" would be both useless and
    wrong. Tracked files are never filtered, whatever their path.
    """
    return [rel for status, rel in _porcelain(worktree_path)
            if not (status == "??" and is_generated_path(rel))]


def head_sha(worktree_path) -> str:
    """The current commit sha of the worktree's branch."""
    return _git(worktree_path, "rev-parse", "HEAD").strip()


def commits_ahead_of_base(worktree_path, base: str, *, remote: str = "origin") -> int:
    """How many commits the worktree's branch carries beyond `base`.

    Bugs (retry/empty-build): a build re-dispatched onto a branch a PRIOR attempt already
    pushed provisions from that branch's remote tip (S.No 162 continuity), so the agent — seeing
    the work already done — correctly produces NO new diff. `changed_files` is then empty and
    nothing new is committed, but the branch still carries real, reviewable work. The saga must
    not treat that as an empty build. This counts the branch's commits that are not in `base` so
    the caller can tell "already-built branch, no new change" apart from a genuinely empty build.

    Prefers the authoritative remote base ref (`<remote>/<base>`); falls back to a local `base`
    ref (offline). An unknown ref yields 0 rather than raising."""
    for ref in (f"{remote}/{base}", base):
        out = _git(worktree_path, "rev-list", "--count", f"{ref}..HEAD", check=False).strip()
        if out.isdigit():
            return int(out)
    return 0


def commit_all(worktree_path, message: str) -> str | None:
    """Stage and commit every change on the worktree's feature branch (D2: the platform owns
    Git side-effects — the agent never runs git). `.sdlc/` scratch is already git-excluded, so
    it never enters the commit. Returns the new commit sha, or None if there was nothing to
    commit (the agent produced no change).

    Untracked generated directories are unstaged again before committing. Without this a single
    `npm install` put ~30,000 dependency files into the client's repository — and from the next
    run onward those files were *tracked*, so every later build tripped the secret scanner on
    them and the branch could never be pushed again. Computed BEFORE `add -A`, because
    afterwards nothing is untracked any more."""
    generated = generated_roots(worktree_path)
    _git(worktree_path, "add", "-A")
    if generated:
        # By root directory, not by file: 30,000 paths would exceed the command-line limit.
        _git(worktree_path, "reset", "-q", "--", *generated)
    if not changed_files(worktree_path):
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
