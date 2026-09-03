"""The worker's build badge — which code this worker is actually running.

Why this exists
---------------
A Temporal worker running stale code can still take work off a shared queue. It
does the older thing, reports success, and leaves the platform in a state nobody
audits. That is not an accessibility problem or a Phase-N problem: any activity
an older worker handles differently is silently wrong. The badge lets a worker
answer two questions before it polls for anything:

    "which exact code am I running?"   -> a content fingerprint
    "am I older than whoever is in charge?"  -> an orderable timestamp

Both are needed. The fingerprint alone cannot be ordered, so a worker could not
tell newer from older. A timestamp alone cannot identify code, so two different
checkouts made in the same second would collide.

Badge format: ``<YYYYmmddTHHMMSSZ>-<fingerprint12>``. Chosen so that a plain
string comparison is also the chronological comparison, with the fingerprint
acting as a deterministic tie-break (see `is_newer`).

Where the timestamp comes from
------------------------------
`docker-compose.yml` mounts the repo at ``/repo`` and sets ``working_dir:
/repo/backend``, while `backend/Dockerfile` bakes its own copy at ``/app``. **The
worker does not run the code in its own image.** So a build-time stamp alone
would confidently describe code that is not executing. The rule is therefore:

  * use the stamp recorded at image build **only if** the running code's
    fingerprint matches the fingerprint recorded alongside it;
  * otherwise fall back to the newest modification time of the running code.

That keeps cloud deploys (image == running code) on a real build timestamp, and
keeps volume-mounted dev machines honest about what is actually loaded.

This module deliberately imports nothing from Django, so `--emit` can be run
during the image build before any settings exist.
"""
from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

# Directories whose contents never change what a worker *does*. Excluding them
# stops the badge churning (and forcing a needless version bump) on a test-only
# or bytecode-only change.
_SKIP_DIRS = frozenset(
    {"__pycache__", "tests", ".venv", "node_modules", ".git", ".pytest_cache", ".mypy_cache"}
)

# Set at image build (see backend/Dockerfile). Holds two lines: the build
# timestamp, then the fingerprint of the code baked into the image.
_MANIFEST_ENV = "SDLC_BUILD_MANIFEST"
_DEFAULT_MANIFEST = "/app/.sdlc_build"

_STAMP_FMT = "%Y%m%dT%H%M%SZ"


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _source_roots() -> list[tuple[str, Path]]:
    """The trees whose contents define worker behaviour, as (label, path).

    The label — not the absolute path — is what goes into the hash, because the
    same code lives at different paths depending on how it was started: ``/app``
    in the built image, ``/repo/backend`` under the compose mount, a working
    copy on a developer's machine. Keying on the absolute path would make every
    one of those look like different code.
    """
    roots = [("backend", _backend_root())]
    # The Platform-State MCP server is imported by activities, so its code is
    # part of what this worker executes.
    mcp = _repo_root() / "mcp_platform_state"
    if mcp.is_dir():
        roots.append(("mcp_platform_state", mcp))
    return roots


def _iter_source_files() -> list[tuple[str, Path]]:
    """Every behaviour-defining .py file, as (stable key, path), sorted by key."""
    found: list[tuple[str, Path]] = []
    for label, root in _source_roots():
        for path in root.rglob("*.py"):
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            try:
                key = f"{label}/{path.relative_to(root).as_posix()}"
            except ValueError:  # pragma: no cover - path always sits under root
                key = f"{label}/{path.name}"
            found.append((key, path))
    found.sort(key=lambda item: item[0])
    return found


def code_fingerprint() -> str:
    """A stable hash of the code this process would execute.

    Line endings are normalised before hashing: the same checkout on a Windows
    host and in a Linux container must produce the same fingerprint, or every
    machine would think every other machine was running different code.
    """
    digest = hashlib.sha256()
    for key, path in _iter_source_files():
        try:
            body = path.read_bytes()
        except OSError:
            # A file we cannot read cannot be code we are running.
            continue
        body = body.replace(b"\r\n", b"\n")
        digest.update(key.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(body).digest())
    return digest.hexdigest()


def _newest_source_mtime() -> datetime:
    newest = 0.0
    for _key, path in _iter_source_files():
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        newest = max(newest, mtime)
    if newest == 0.0:  # pragma: no cover - only if the tree is unreadable
        newest = 0.0
    return datetime.fromtimestamp(newest, tz=UTC)


def _read_baked_manifest() -> tuple[str, str] | None:
    """(stamp, fingerprint) recorded at image build, or None if absent/unusable."""
    raw = os.environ.get(_MANIFEST_ENV, _DEFAULT_MANIFEST)
    try:
        lines = Path(raw).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if len(lines) < 2:
        return None
    stamp, fingerprint = lines[0].strip(), lines[1].strip()
    if not stamp or not fingerprint:
        return None
    return stamp, fingerprint


def build_badge() -> tuple[str, str]:
    """Return ``(badge, source)`` for the code this process is running.

    ``source`` is only for the log line, so an operator can see at a glance
    whether the badge came from the image build or from the mounted files.
    """
    fingerprint = code_fingerprint()
    short = fingerprint[:12]

    baked = _read_baked_manifest()
    if baked is not None and baked[1] == fingerprint:
        return f"{baked[0]}-{short}", "image build stamp"

    stamp = _newest_source_mtime().strftime(_STAMP_FMT)
    reason = "running code (differs from image)" if baked is not None else "running code"
    return f"{stamp}-{short}", reason


def fingerprint_of(badge: str) -> str:
    """The code-identity half of a badge (the timestamp half has no dashes)."""
    return badge.rpartition("-")[2]


def same_code(one: str, other: str) -> bool:
    """Do these two badges describe byte-identical code?

    Two developers who pull the same commit at different times get different
    timestamps for the same files, so their badges differ while their code does
    not. Without this, one of them would stand down for no reason and the team
    would silently lose a worker — the runbook has them sharing a queue on
    purpose. Identical code is not a newer or older build; it is the same build.
    """
    return fingerprint_of(one) == fingerprint_of(other)


def is_newer(candidate: str, incumbent: str) -> bool:
    """Is `candidate` strictly newer than `incumbent`?

    Plain string ordering, which works because the timestamp prefix is
    fixed-width and lexically ordered. When two badges share a timestamp but not
    a fingerprint the comparison falls through to the fingerprint — arbitrary,
    but *deterministic*, which is the property that matters: both workers reach
    the same verdict, so exactly one steps aside instead of the two of them
    taking turns promoting themselves forever.
    """
    return candidate > incumbent


def _emit() -> None:
    """Write the build manifest. Used by backend/Dockerfile at image build."""
    target = os.environ.get(_MANIFEST_ENV, _DEFAULT_MANIFEST)
    stamp = os.environ.get("SDLC_BUILD_STAMP", "").strip()
    if not stamp:
        stamp = datetime.now(tz=UTC).strftime(_STAMP_FMT)
    Path(target).write_text(f"{stamp}\n{code_fingerprint()}\n", encoding="utf-8")
    print(f"wrote {target}: {stamp}")


if __name__ == "__main__":  # pragma: no cover - build-time entrypoint
    _emit()
