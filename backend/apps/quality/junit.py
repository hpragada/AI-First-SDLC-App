"""JUnit XML → the platform's vendor-free test results — the ONE parser (P3-09bX-2 / D4).

Framework-agnostic: JUnit XML is the interchange format every framework in 09b's matrix emits
(pytest `--junitxml`, jest-junit, Playwright's `junit` reporter, NUnit, TestNG, Cypress), so
parsing it keeps result handling stack-agnostic — no per-framework output scraping.

**Django-free on purpose.** Both callers import this single module so the `<testcase>` → `TC-ID`
mapping can never drift:
  - the companion's worktree collection (`runner.companion.testresults`, lazily — the companion
    puts `backend/` on its path at build time via `ensure_backend_importable`);
  - the server-side CI results-ingestion endpoint (P3-09bX-3).

**A malformed/empty document yields `[]`, never a partial or false-green** — `import_test_results`
refuses an empty set, so a run that emitted nothing can never register a green execution.
"""
from __future__ import annotations

import re
from xml.etree import ElementTree

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

# A **safety valve, not a display limit** (QA-11a). Evidence used to be cut to 2000 characters
# right here — the earliest possible moment — which meant the full text never entered the
# platform at all and no store downstream could ever hold it. A developer then read four of a
# screen's eighteen accessibility violations and had no way to see the rest: re-running locally
# is a *different* execution against different state, so it is not the same evidence.
#
# The full text is now parsed and filed as the run's `test_report` artifact body in the object
# store (`apps.quality.services`), which is where bodies belong (#1/#3); the short summary that
# stays on the row — and goes to the tracker, which has its own hard field limit — is bounded
# there, where the limit is actually imposed.
#
# What remains here is protection against a runaway log: a single test whose failure text runs
# past a quarter of a megabyte is emitting a log, not evidence. Raising this number is not how
# you fix a truncated report — the report body is uncapped by design.
_MAX_EVIDENCE = 256_000


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

    Tolerant by design: a malformed document yields no results (never a partial/false green),
    and both root shapes are handled — `<testsuites>` wrapping many suites, or a bare
    `<testsuite>` (pytest and jest-junit differ here).
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    results = []
    for case in root.iter("testcase"):
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


def summarize(results: list[dict]) -> str:
    """One line for a run console / build message: `12 passed, 1 failed, 2 skipped`."""
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
