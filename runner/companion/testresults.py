"""JUnit XML → the platform's vendor-free test results (Phase-3 D4).

The companion reads results from the report file the suite itself emits — **machine truth**,
not the agent's narration of how its run went. Same reason the test gate's blocking-test rule
is platform-derived rather than reviewer-attested: an actor should not grade its own work.

JUnit XML is the one interchange format every framework in 09b's matrix emits (pytest
`--junitxml`, jest-junit, Playwright's `junit` reporter, NUnit, TestNG, Cypress), so parsing
it keeps the companion framework-agnostic — no per-stack output scraping.

**No report file ⇒ no results ⇒ no import.** An absent or unparseable report is never an
empty pass: `import_test_results` refuses an empty set precisely so a build that ran nothing
cannot register a green execution or close the defects it said nothing about.
"""
from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree

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

# 09b names its output after the test case it automates — `TC001LoginTests.cs`,
# `TC007-checkout.spec.ts`, `test_tc014_login.py` — so the TC-ID is recoverable from the JUnit
# identity. The digits are preserved exactly as written (TC001 → "TC-001", never re-padded):
# the `test_case` artifact's own id is the authority on padding, and inventing a different
# width would silently break the match and cost the defect its real severity.
#
# The lookbehind (rather than `\b`) is load-bearing in both directions: `\b` would miss
# `test_tc014_login` (an underscore is a word char, so there is no boundary before `tc`) while
# still matching the `tc` inside `match123`. Requiring a non-alphanumeric — or the start —
# before `TC` accepts the real conventions and rejects mid-word noise. There is deliberately no
# trailing boundary: `TC001LoginTests` must still yield 001.
_TC_ID = re.compile(r"(?<![A-Za-z0-9])TC[-_ ]?(\d+)", re.IGNORECASE)

_MAX_EVIDENCE = 2000


def test_ref_for(classname: str, name: str) -> str:
    """The `test_ref` a JUnit `<testcase>` maps to: its TC-ID when the name carries one (so the
    result lines up with the `test_case` artifact, its priority and its Xray key), else the
    fully-qualified JUnit id — honest about being un-mapped rather than guessing a TC."""
    for candidate in (name, classname):
        match = _TC_ID.search(candidate or "")
        if match:
            return f"TC-{match.group(1)}"
    return ".".join(part for part in (classname, name) if part) or "unknown"


def _evidence(case: ElementTree.Element) -> str:
    """The failure/error message + body, capped — enough to triage the defect from, without
    posting a whole traceback into platform state (#1/#3: state holds summaries, not bodies)."""
    parts = []
    for child in case:
        if child.tag not in ("failure", "error"):
            continue
        message = (child.get("message") or "").strip()
        body = (child.text or "").strip()
        parts.append("\n".join(p for p in (message, body) if p))
    return "\n\n".join(parts)[:_MAX_EVIDENCE]


def _status(case: ElementTree.Element) -> str:
    tags = {child.tag for child in case}
    if tags & {"failure", "error"}:
        return "FAIL"
    if "skipped" in tags:
        return "SKIP"
    return "PASS"


def parse_junit(xml_text: str) -> list[dict]:
    """Every `<testcase>` in a JUnit document → [{test_ref, status, evidence}].

    Tolerant by design: a malformed document yields no results (never a partial//false green),
    and both root shapes are handled — `<testsuites>` wrapping many suites, or a bare
    `<testsuite>` (pytest and jest-junit differ here).
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    cases = root.iter("testcase")
    results = []
    for case in cases:
        classname = case.get("classname") or case.get("class") or ""
        name = case.get("name") or ""
        if not (classname or name):
            continue
        results.append({
            "test_ref": test_ref_for(classname, name),
            "status": _status(case),
            "evidence": _evidence(case),
        })
    return results


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
    results: list[dict] = []
    for path in find_reports(Path(worktree)):
        try:
            xml_text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        results.extend(parse_junit(xml_text))
    return results


def summarize(results: list[dict]) -> str:
    """One line for the build report / run console: `12 passed, 1 failed, 2 skipped`."""
    if not results:
        return "no test report found"
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    parts = [f"{counts['PASS']} passed"]
    if counts["FAIL"]:
        parts.append(f"{counts['FAIL']} failed")
    if counts["SKIP"]:
        parts.append(f"{counts['SKIP']} skipped")
    return ", ".join(parts)
