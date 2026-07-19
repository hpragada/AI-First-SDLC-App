"""P3/D4 — the shared JUnit parser (`apps.quality.junit`) + the companion's worktree collection.

Results are read from the suite's own report file (machine truth), never from the agent's
account of its run. The parser must be framework-agnostic (pytest / jest / Playwright / NUnit
all emit JUnit) and, above all, must never manufacture a green result: no report, an
unreadable report, or a malformed one all yield `[]`, which the platform declines to import.
The parsing lives in one Django-free module (P3-09bX-2) so the companion collection and the CI
ingestion endpoint can never drift; the companion module only adds worktree report discovery.
"""
from runner.companion.testresults import collect_test_results

# `test_ref_for` is imported under a private alias on purpose: as a module-level `test_*` name
# pytest would collect the production function itself as a test case and error on its arguments.
from apps.quality.junit import parse_junit, summarize
from apps.quality.junit import test_ref_for as _ref_for

_PYTEST = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="4" failures="1" errors="1" skipped="1">
    <testcase classname="tests.test_login" name="test_ok" time="0.01"/>
    <testcase classname="tests.test_login" name="test_bad_password" time="0.02">
      <failure message="AssertionError: expected 401">assert 200 == 401</failure>
    </testcase>
    <testcase classname="tests.test_cart" name="test_boom" time="0.03">
      <error message="RuntimeError: boom">Traceback...</error>
    </testcase>
    <testcase classname="tests.test_cart" name="test_wip" time="0.0">
      <skipped message="not implemented"/>
    </testcase>
  </testsuite>
</testsuites>
"""

# jest-junit / Playwright emit a bare <testsuite> root rather than <testsuites>.
_BARE_SUITE = """<testsuite name="jest" tests="1" failures="0">
  <testcase classname="checkout" name="renders the cart" time="0.5"/>
</testsuite>
"""


def test_parses_pass_fail_error_and_skip():
    results = parse_junit(_PYTEST)
    by_ref = {r["test_ref"]: r for r in results}
    assert by_ref["tests.test_login.test_ok"]["status"] == "PASS"
    assert by_ref["tests.test_login.test_bad_password"]["status"] == "FAIL"
    assert by_ref["tests.test_cart.test_boom"]["status"] == "FAIL"      # an error is a failure
    assert by_ref["tests.test_cart.test_wip"]["status"] == "SKIP"       # skip is not a pass
    assert "expected 401" in by_ref["tests.test_login.test_bad_password"]["evidence"]


def test_parses_a_bare_testsuite_root():
    assert parse_junit(_BARE_SUITE) == [
        {"test_ref": "checkout.renders the cart", "status": "PASS", "evidence": ""}
    ]


def test_malformed_xml_yields_no_results_never_a_green_run():
    assert parse_junit("<testsuite>truncated...") == []
    assert parse_junit("") == []


# ── TC-ID recovery: 09b names its output after the test case it automates ──
def test_tc_id_is_recovered_from_09b_naming_conventions():
    assert _ref_for("TC001LoginTests", "LoginRejectsBadPassword") == "TC-001"    # C#/NUnit
    assert _ref_for("TC007-checkout.spec.ts", "completes an order") == "TC-007"  # Playwright
    assert _ref_for("tests.test_tc014_login", "test_expired_session") == "TC-014"  # pytest
    assert _ref_for("suite", "TC-42 rejects a bad password") == "TC-42"


def test_digits_are_preserved_not_repadded():
    """The `test_case` artifact's own id is the authority on padding — re-padding here would
    silently break the match and cost the defect its real severity."""
    assert _ref_for("TC001Tests", "x") == "TC-001"
    assert _ref_for("TC1Tests", "x") == "TC-1"


def test_unmapped_tests_keep_their_junit_identity():
    """An ordinary unit test carries no TC — say so honestly rather than invent a TC-ID."""
    assert _ref_for("tests.test_login", "test_ok") == "tests.test_login.test_ok"
    # `match123` contains "tc" mid-word — it must not be mistaken for a TC-ID.
    assert _ref_for("suite", "match123 works") == "suite.match123 works"


# ── discovery in the worktree ───────────────────────────────────────
def test_collects_from_a_conventional_report_path(tmp_path):
    (tmp_path / "test-results").mkdir()
    (tmp_path / "test-results" / "junit.xml").write_text(_PYTEST, encoding="utf-8")
    results = collect_test_results(tmp_path)
    assert len(results) == 4
    assert {r["status"] for r in results} == {"PASS", "FAIL", "SKIP"}


def test_no_report_in_the_worktree_yields_no_results(tmp_path):
    """The build ran no tests (or emitted no report) — that must never read as a pass."""
    assert collect_test_results(tmp_path) == []


def test_merges_per_suite_reports(tmp_path):
    """maven/gradle emit one file per suite — all of them count."""
    reports = tmp_path / "target" / "surefire-reports"
    reports.mkdir(parents=True)
    (reports / "TEST-a.xml").write_text(_BARE_SUITE, encoding="utf-8")
    (reports / "TEST-b.xml").write_text(_BARE_SUITE, encoding="utf-8")
    assert len(collect_test_results(tmp_path)) == 2


def test_summarize_counts():
    assert summarize(parse_junit(_PYTEST)) == "1 passed, 2 failed, 1 skipped"
    assert summarize([]) == "no test report found"
