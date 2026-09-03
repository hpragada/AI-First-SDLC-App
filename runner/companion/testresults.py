"""Companion-side JUnit collection from the build worktree (Phase-3 D4).

The companion reads results from the report file the suite itself emits — **machine truth**, not
the agent's narration of how its run went. The actual XML→results parsing is the platform's ONE
parser (`apps.quality.junit`, shared with the CI ingestion endpoint so the `<testcase>`→`TC-ID`
mapping can never drift); this module only knows *where* a suite drops its report in the worktree.

The `apps.quality.junit` import is **lazy** (inside the functions): the companion adds `backend/`
to its path at build time (`ensure_backend_importable`), which is after this module is first
imported at CLI startup — importing the shared parser at module top would fail then.

**No report file ⇒ no results ⇒ no import.** An absent or unparseable report is never an empty
pass: `import_test_results` refuses an empty set precisely so a build that ran nothing cannot
register a green execution or close the defects it said nothing about.
"""
from __future__ import annotations

from pathlib import Path

# Where suites conventionally drop a JUnit report, relative to the worktree. Checked in order;
# the first file that parses into at least one result wins. (A project-declared path from the
# Project Profile is a later refinement — the platform does not yet ship one to the companion.)
REPORT_GLOBS = (
    "test-results/junit.xml",
    "test-results/results.xml",
    "test-results.xml",
    "junit.xml",
    "reports/junit.xml",
    "reports/junit/*.xml",
    "build/test-results/**/*.xml",      # gradle
    "target/surefire-reports/TEST-*.xml",  # maven
    "TestResults/*.xml",                # dotnet
)


def find_reports(worktree: Path) -> list[Path]:
    """Report files present in the worktree, in REPORT_GLOBS order (deduped, stable)."""
    found: list[Path] = []
    for pattern in REPORT_GLOBS:
        for path in sorted(Path(worktree).glob(pattern)):
            if path.is_file() and path not in found:
                found.append(path)
    return found


def collect_test_results(worktree) -> list[dict]:
    """The suite's results for this build, or `[]` when it emitted no readable report.

    Reports found at the same conventional location are merged (maven/gradle emit one file per
    suite). `[]` is the honest answer for "no report" — the platform declines to import it, so
    a build that ran no tests never looks like one that passed.
    """
    from apps.quality.junit import parse_junit  # lazy: backend on path by build time

    results: list[dict] = []
    for path in find_reports(Path(worktree)):
        try:
            xml_text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        results.extend(parse_junit(xml_text))
    return results


def summarize(results: list[dict]) -> str:
    """One line for the build report / run console — the platform's single summarizer."""
    from apps.quality.junit import summarize as _summarize  # lazy (see module docstring)

    return _summarize(results)
