"""Companion-side accessibility capture collection from the build worktree (QA-11b).

A sibling of `testresults.py`, held to the same discipline for the same reason: **this module
knows only WHERE a capture lands; the platform owns WHAT it means** (`apps.a11y.capture`).
Two readers of a compliance format is two formats, and the second one is always the one nobody
remembers to update.

The app under test runs here, on the developer's machine, at a `localhost` address the platform
cannot reach. During its accessibility scan the generated suite writes down what was on each
screen and one picture of each screen; this reads that file before the worktree is torn down and
posts it — one screen per call, so a page's screenshot never shares an HTTP body with nine
others.

The `apps.a11y.capture` import is **lazy** (inside the functions), matching `testresults.py`:
the companion adds `backend/` to its path at build time, which is after this module is first
imported at CLI startup.

**No capture file ⇒ no candidates ⇒ nothing stored.** An absent or unreadable capture is never
an empty pass — the platform declines to import it, so a scan that captured nothing can never
be read as a page with nothing wrong on it.
"""
from __future__ import annotations

from pathlib import Path

# Where an accessibility capture conventionally lands, relative to the worktree. Checked in
# order; the first file that parses into at least one screen wins. `test-results/` is already
# gitignored by 09b's scaffolding step, so the capture reaches the platform without ever being
# committed — the same route the JUnit report takes.
CAPTURE_GLOBS = (
    "test-results/a11y-candidates.json",
    "test-results/a11y/*.json",
    "a11y-candidates.json",
)


def find_captures(worktree: Path) -> list[Path]:
    """Capture files present in the worktree, in CAPTURE_GLOBS order (deduped, stable)."""
    found: list[Path] = []
    for pattern in CAPTURE_GLOBS:
        for path in sorted(Path(worktree).glob(pattern)):
            if path.is_file() and path not in found:
                found.append(path)
    return found


def collect_a11y_candidates(worktree) -> list[dict]:
    """The captured screens for this build, or `[]` when nothing readable was written.

    A capture that breaks one of the platform's bounds (too many screens, too many elements on
    one page) raises there and is skipped here with the rest of the files still read — the file
    is saying something wrong, and the honest outcome is fewer screens rather than a build that
    dies after the suite already ran.
    """
    from apps.a11y.capture import CaptureError, parse_capture  # lazy: backend on path by now

    screens: list[dict] = []
    for path in find_captures(Path(worktree)):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            screens.extend(parse_capture(text))
        except CaptureError as exc:
            print(f"[companion] accessibility capture {path.name} was not stored: {exc}")
    return screens


def summarize(screens: list[dict]) -> str:
    """One line for the build report / run console — the platform's single summarizer."""
    from apps.a11y.capture import summarize as _summarize  # lazy (see module docstring)

    return _summarize(screens)


def post_a11y_candidates(screens: list[dict], *, client, project_id: str, run_id: str) -> dict:
    """Send the captured screens to the platform, one screen per call.

    One call per screen is not tidiness: a screen carries a full-page PNG, and ten of those in
    one JSON body is several megabytes — past what the request layer accepts, and a size limit
    is a bad place to discover that a compliance capture was thrown away. Posting per screen
    also means one screen that fails costs that screen and no other.

    Never raises. A capture that cannot be posted is reported and the build carries on: the
    suite's own results, the defects it opened and the branch it pushed all matter more than
    the AI pass's inputs, and losing them to a failed upload would be the worse trade.
    """
    posted, failed = 0, []
    for screen in screens:
        route = screen.get("route", "")
        try:
            client.call("ingest_a11y_candidates", project_id=project_id, run_id=run_id,
                        screen=screen)
            posted += 1
        except Exception as exc:  # noqa: BLE001 — see the docstring: never fail the build
            failed.append(f"{route}: {exc}")
            print(f"[companion] accessibility capture for {route} was not posted: {exc}")
    return {"posted": posted, "failed": failed}
