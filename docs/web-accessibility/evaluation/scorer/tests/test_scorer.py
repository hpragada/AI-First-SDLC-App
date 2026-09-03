"""What the accuracy harness must refuse to do (QA-10a, QA-10).

INTERNAL — Edvensoft accessibility evaluation.

Every test here pins a rule whose absence would produce a number that looks fine and is not.
That is the whole risk of this piece of work: nobody notices a scorer that is wrong, because
its output is a plausible percentage either way.

No database, no Django, no platform. `platformdata.py` is the only module that touches any of
those, and it is the only one not tested here — it does one read per model and returns plain
data, and the arithmetic that could be silently wrong all lives in the modules below.
"""
import json
from pathlib import Path

import pytest

import accuracy
import baseline as baseline_module
import completeness as completeness_module
import labels as labels_module
from accuracy import NOT_CAPTURED, NOT_JUDGED, Answer, score_all
from labels import GOLDEN, LIVE, DatasetError, Label


def label(**kwargs) -> Label:
    base = {"source": GOLDEN, "route": "/r", "selector": "#e", "checker": "alt",
            "criterion": "1.1.1", "expected": "fail", "truth": "fail", "difficulty": "clear"}
    return Label(**{**base, **kwargs})


def answer(verdict: str, *, route="/r", selector="#e", checker="alt") -> Answer:
    return Answer(route=route, selector=selector, checker=checker, verdict=verdict)


def one(labels, answers, captured=None):
    scores = score_all(labels, answers, captured=captured)
    assert len(scores) == 1
    return scores[0]


# ══ what gets scored, and against what ═══════════════════════════════════════════════

def test_an_arguable_record_answered_confidently_is_wrong_even_when_it_matches_the_truth():
    """The rule the whole dataset design turns on (GOLDEN_DATASET_SPEC §4).

    On a genuinely arguable element the right behaviour is to say so and route to a person. A
    checker that answers `pass` there got the right answer for the wrong reason and, more to
    the point, skipped the review queue. Scoring against `truth` would reward exactly the
    behaviour that empties the queue and breaks the product.
    """
    score = one([label(expected="uncertain", truth="pass", difficulty="ambiguous")],
                {("/r", "#e", "alt"): answer("pass")})
    assert score.over_confident == 1
    assert score.true_negative == 0          # it earned nothing for matching `truth`
    assert score.over_confidence_rate() == 1.0


def test_knowing_it_does_not_know_is_the_right_answer_on_an_arguable_record():
    score = one([label(expected="uncertain", difficulty="ambiguous")],
                {("/r", "#e", "alt"): answer("uncertain")})
    assert (score.calibrated_uncertain, score.over_confident) == (1, 0)


def test_arguable_records_stay_out_of_precision_and_recall():
    """They are a claim about calibration, not about finding failures. Mixing them in would
    make one number answer two questions and mean neither."""
    score = one([label(expected="uncertain")], {("/r", "#e", "alt"): answer("uncertain")})
    assert score.sample == 0
    assert score.precision() is None and score.recall() is None


# ══ the two silences, which are not the same silence ═════════════════════════════════

def test_an_element_nobody_looked_at_is_a_miss_not_a_pass():
    """The failure this harness exists to catch, in one assertion.

    Nothing was captured, so no check was ever asked. Reading that as "the checker said it was
    fine" would turn every gap in coverage into a free correct answer — which is precisely how
    a page whose only failure was never looked at came to be reported as checked.
    """
    score = one([label(expected="fail")], {}, captured=set())
    assert score.false_negative == 1
    assert score.never_looked == 1
    assert score.true_negative == 0
    assert score.recall() == 0.0


def test_never_looking_earns_no_credit_even_when_nothing_was_wrong():
    """A silence only ever counts against us. We did not give a right answer; we gave none."""
    score = one([label(expected="pass", truth="pass")], {}, captured=set())
    assert score.never_looked == 1
    assert score.sample == 0                 # excluded from every figure
    assert score.true_negative == 0


def test_an_element_captured_but_never_judged_is_excluded_rather_than_counted_wrong():
    """A run that hit its ceiling is incomplete, not inaccurate, and must read that way."""
    score = one([label(expected="fail")], {}, captured={("/r", "#e", "alt")})
    assert score.deferred == 1
    assert (score.sample, score.false_negative, score.never_looked) == (0, 0, 0)


def test_the_two_silences_are_told_apart_by_what_was_captured():
    labels = [label(selector="#a"), label(selector="#b")]
    score = one(labels, {}, captured={("/r", "#a", "alt")})
    assert (score.deferred, score.never_looked) == (1, 1)


def test_a_silence_handed_in_directly_reads_the_same_as_a_missing_answer():
    """The platform can report a silence explicitly rather than by omission — a run that says
    "captured, never judged" out loud must land in the same place as one that simply has no
    row for the element."""
    deferred = one([label()], {("/r", "#e", "alt"): answer(NOT_JUDGED)})
    assert deferred.deferred == 1 and deferred.sample == 0

    never = one([label()], {("/r", "#e", "alt"): answer(NOT_CAPTURED)})
    assert never.never_looked == 1 and never.false_negative == 1


def test_with_no_capture_set_every_missing_answer_counts_against_us():
    """The safe direction to be wrong in: it costs us a point rather than quietly awarding one."""
    score = one([label(expected="fail")], {})
    assert score.never_looked == 1 and score.deferred == 0


# ══ recall, and the one source that cannot produce it ════════════════════════════════

def test_recall_from_live_review_verdicts_is_reported_as_unmeasured_never_estimated():
    """Their universe is the findings we already reported, so the denominator would be "things
    we found" — precision wearing recall's name (D-A11Y-63)."""
    score = one([label(source=LIVE, expected="fail")],
                {("/r", "#e", "alt"): answer("fail")})
    assert score.recall() == accuracy.UNMEASURED
    assert score.f1() == accuracy.UNMEASURED
    assert score.precision() == 1.0          # precision IS measurable from them


def test_the_two_sources_are_never_added_together():
    scores = score_all(
        [label(selector="#a"), label(source=LIVE, selector="#b")],
        {("/r", "#a", "alt"): answer("fail", selector="#a"),
         ("/r", "#b", "alt"): answer("fail", selector="#b")})
    assert {s.source for s in scores} == {GOLDEN, LIVE}
    assert all(s.sample == 1 for s in scores)


def test_the_report_says_out_loud_which_checkers_have_no_recall_figure():
    note = baseline_module.unmeasured_note(
        [accuracy.Score(checker="alt", source=LIVE)])
    assert "unmeasured" in note and "alt" in note


# ══ ordinary arithmetic, and the confidence figures ══════════════════════════════════

def test_precision_and_recall_over_a_mixed_set():
    labels = [label(selector=f"#{i}", expected=e)
              for i, e in enumerate(["fail", "fail", "fail", "pass"])]
    answers = {("/r", "#0", "alt"): answer("fail", selector="#0"),
               ("/r", "#1", "alt"): answer("fail", selector="#1"),
               ("/r", "#2", "alt"): answer("pass", selector="#2"),
               ("/r", "#3", "alt"): answer("fail", selector="#3")}
    score = one(labels, answers, captured=set(answers))
    assert (score.true_positive, score.false_positive, score.false_negative) == (2, 1, 1)
    assert score.precision() == pytest.approx(2 / 3)
    assert score.recall() == pytest.approx(2 / 3)
    assert score.f1() == pytest.approx(2 / 3)


def test_saying_not_sure_about_a_clear_cut_record_is_tracked_but_is_not_an_error():
    score = one([label(expected="fail", difficulty="clear")],
                {("/r", "#e", "alt"): answer("uncertain")}, captured={("/r", "#e", "alt")})
    assert score.under_confident == 1
    assert score.false_negative == 1         # it still did not find the failure
    assert score.over_confident == 0


def test_difficulty_bands_are_kept_apart():
    """A checker at 95% on clear cases and 40% on borderline ones is a different product from
    one at 78% flat, and a single number hides which of the two we have."""
    labels = [label(selector="#a", difficulty="clear"),
              label(selector="#b", difficulty="borderline")]
    answers = {("/r", "#a", "alt"): answer("fail", selector="#a"),
               ("/r", "#b", "alt"): answer("pass", selector="#b")}
    score = one(labels, answers, captured=set(answers))
    assert score.by_difficulty["clear"] == {"right": 1, "wrong": 0}
    assert score.by_difficulty["borderline"] == {"right": 0, "wrong": 1}


def test_a_sample_below_the_minimum_says_so_rather_than_reporting_a_percentage():
    score = one([label()], {("/r", "#e", "alt"): answer("fail")})
    assert accuracy.NOT_MEASURABLE in score.verdict_line(accuracy.DEFAULT_MIN_SAMPLE)


# ══ completeness — counting, no answer key needed ════════════════════════════════════

def test_fewer_captured_than_expected_is_reported_as_never_offered_to_any_check():
    result = completeness_module.check(captured_by_route={"/loans/current": 11},
                                       judged_by_route={"/loans/current": 11},
                                       expected_by_route={"/loans/current": 14})
    assert completeness_module.DROPPED_BEFORE_CAPTURE in result.routes[0].problems
    assert not result.ok


def test_fewer_judged_than_captured_is_a_different_problem_with_a_different_name():
    result = completeness_module.check(captured_by_route={"/a": 20}, judged_by_route={"/a": 17})
    assert completeness_module.DROPPED_BEFORE_JUDGING in result.routes[0].problems
    assert not result.ok


def test_a_page_holding_nothing_is_fine_and_is_not_an_error():
    result = completeness_module.check(captured_by_route={"/about/terms": 0},
                                       judged_by_route={"/about/terms": 0},
                                       expected_by_route={"/about/terms": 0})
    assert result.ok


def test_more_captured_than_expected_is_surfaced_but_does_not_fail_the_check():
    """Not a defect on its own — the page may have grown, or a selection rule may have widened.
    Both are things somebody should hear about rather than discover when a label stops
    resolving."""
    result = completeness_module.check(captured_by_route={"/a": 30}, judged_by_route={"/a": 30},
                                       expected_by_route={"/a": 20})
    assert completeness_module.UNEXPECTED_SURPLUS in result.routes[0].problems
    assert result.ok


def test_a_page_the_manifest_expects_and_the_run_never_visited_still_gets_a_line():
    """Dropping it from the table would reproduce the very silence being looked for."""
    result = completeness_module.check(captured_by_route={}, judged_by_route={},
                                       expected_by_route={"/never/opened": 8})
    assert [r.route for r in result.routes] == ["/never/opened"]
    assert result.routes[0].captured == 0 and not result.ok


# ══ completeness — the names, not just the totals ════════════════════════════════════
#
# 1 September: `/help/membership-actions` printed `expected 11 · captured 29 · judged 29 · ok`
# on the same run where the accuracy half reported eleven records on that page as never looked
# at. Both halves were reading the same run, and neither noticed they disagreed — because the
# counting half only ever compared two integers. 29 is more than 11, so it passed.


def test_a_page_that_captured_plenty_of_the_wrong_things_no_longer_passes():
    """**The exact shape of the failure, with the exact numbers that produced it.**

    A packing list checked by weighing the bag: the page offered twenty-nine elements and not
    one of them was among the eleven the answer key names. Counting alone calls that a surplus
    and moves on.
    """
    wanted = {(f"#act-{n}", "label") for n in range(11)}
    result = completeness_module.check(
        captured_by_route={"/help/membership-actions": 29},
        judged_by_route={"/help/membership-actions": 29},
        expected_by_route={"/help/membership-actions": 11},
        expected_elements={"/help/membership-actions": wanted},
        captured_elements={("/help/membership-actions", "#something-else", "color")},
    )
    route = result.routes[0]
    assert completeness_module.NAMED_AND_MISSING in route.problems
    assert len(route.missing) == 11
    assert not result.ok, "a page that missed everything it was asked for must not read as ok"
    assert result.missing_named == 11


def test_the_page_says_WHICH_elements_are_missing_and_not_merely_how_many():
    """A count tells somebody a number is wrong. A name tells them where to look."""
    result = completeness_module.check(
        captured_by_route={"/account/card-options": 25},
        judged_by_route={"/account/card-options": 25},
        expected_elements={"/account/card-options": {("#card-renew", "label"),
                                                     ("#card-pay", "label")}},
        captured_elements={("/account/card-options", "#card-pay", "label")},
    )
    route = result.routes[0]
    assert route.missing == ("#card-renew [label]",)
    assert "#card-renew [label]" in route.line()
    # …and it survives into the results file, which is the record anyone reads next month.
    assert result.as_dict()["routes"][0]["missing"] == ["#card-renew [label]"]


def test_an_element_offered_to_ONE_check_is_not_offered_to_ANOTHER():
    """The identity is (page, element, check) — not (page, element).

    A button can be perfectly captured for the colour check and never put in front of the label
    check, which is exactly what happens when a rule settles one criterion and not another. The
    comparison has to be per check or it would call that page complete.
    """
    result = completeness_module.check(
        captured_by_route={"/x": 1}, judged_by_route={"/x": 1},
        expected_elements={"/x": {("#b", "label")}},
        captured_elements={("/x", "#b", "color")},
    )
    assert result.routes[0].missing == ("#b [label]",)


def test_every_named_element_present_is_the_quiet_pass():
    result = completeness_module.check(
        captured_by_route={"/x": 2}, judged_by_route={"/x": 2},
        expected_elements={"/x": {("#a", "label"), ("#b", "alt")}},
        captured_elements={("/x", "#a", "label"), ("/x", "#b", "alt")},
    )
    assert result.routes[0].missing == ()
    assert result.ok and result.missing_named == 0


def test_with_no_answer_key_this_is_exactly_the_check_it_always_was():
    """**The half that must keep working on any run, on any application, from day one.**

    Naming is an extra the golden set makes possible; it is not a dependency. Called with
    neither names nor counts, this still checks captured-against-judged — which needs no answer
    key and is why the spec says to build and trust this half first.
    """
    result = completeness_module.check(captured_by_route={"/a": 20}, judged_by_route={"/a": 17})
    assert completeness_module.DROPPED_BEFORE_JUDGING in result.routes[0].problems
    assert result.routes[0].missing == ()
    assert not result.ok


def test_a_long_list_of_missing_elements_stays_readable():
    """Twelve names on one line is a wall nobody reads. The line names a few and counts the
    rest; the results file keeps every one of them."""
    wanted = {(f"#e{n}", "label") for n in range(12)}
    result = completeness_module.check(
        captured_by_route={"/x": 0}, judged_by_route={"/x": 0},
        expected_elements={"/x": wanted}, captured_elements=set(),
    )
    line = result.routes[0].line()
    assert "and 9 more" in line
    assert len(result.as_dict()["routes"][0]["missing"]) == 12


# ══ the golden set: refuse to run rather than warn ═══════════════════════════════════

def test_a_missing_golden_directory_is_not_an_error():
    """The set is hand-labelled expert work and may legitimately not exist yet."""
    labels, manifest = labels_module.load_golden(Path("nowhere-at-all"))
    assert labels == [] and manifest == {}


def test_a_golden_directory_with_no_manifest_refuses_to_run(tmp_path):
    (tmp_path / "1.1.1.json").write_text("[]", encoding="utf-8")
    with pytest.raises(DatasetError, match="manifest"):
        labels_module.load_golden(tmp_path)


def test_counts_that_disagree_with_the_files_refuse_to_run(tmp_path):
    """Every dropped record inflates every score, and the inflation is invisible."""
    _write(tmp_path, records=[_record()], counts={"1.1.1": 7})
    with pytest.raises(DatasetError, match="inflates"):
        labels_module.load_golden(tmp_path)


def test_an_unknown_expected_verdict_refuses_to_run(tmp_path):
    _write(tmp_path, records=[_record(expected_verdict="probably")], counts={"1.1.1": 1})
    with pytest.raises(DatasetError, match="expected_verdict"):
        labels_module.load_golden(tmp_path)


def test_a_record_missing_the_element_it_names_refuses_to_run(tmp_path):
    _write(tmp_path, records=[_record(selector="")], counts={"1.1.1": 1})
    with pytest.raises(DatasetError, match="selector"):
        labels_module.load_golden(tmp_path)


def test_a_well_formed_set_loads(tmp_path):
    _write(tmp_path, records=[_record(), _record(id="g-2", selector="#other")],
           counts={"1.1.1": 2})
    loaded, manifest = labels_module.load_golden(tmp_path)
    assert len(loaded) == 2
    assert loaded[0].source == GOLDEN and loaded[0].checker == "alt"   # translated on the way in
    assert manifest["app_version"] == "1.4.0"


def test_the_specs_checker_names_are_translated_to_the_platforms(tmp_path):
    """The spec says `meaningful-alt`; the platform's stored verdicts say `alt`. Untranslated,
    no label would join to any verdict, every record would score as never-looked-at, and the
    report would announce that the checkers found nothing at all."""
    _write(tmp_path, records=[_record(checker="meaningful-alt"),
                              _record(id="g-2", selector="#x", checker="colour-only",
                                      criterion="1.4.1")],
           counts={"1.1.1": 1, "1.4.1": 1})
    loaded, _ = labels_module.load_golden(tmp_path)
    assert {label.checker for label in loaded} == {"alt", "color"}


def test_a_dataset_already_using_the_platforms_names_needs_no_translation(tmp_path):
    _write(tmp_path, records=[_record(checker="alt")], counts={"1.1.1": 1})
    loaded, _ = labels_module.load_golden(tmp_path)
    assert loaded[0].checker == "alt"


def test_scoring_against_a_different_version_of_the_app_refuses_to_run():
    """A label describes one element on one version of one page. Across a mismatch the numbers
    look completely normal and mean nothing (GOLDEN_DATASET_SPEC §7 rule 1)."""
    with pytest.raises(DatasetError, match="1.4.0"):
        labels_module.check_app_version({"app_version": "1.4.0"}, "1.5.0")


def test_an_answer_key_with_no_version_of_its_own_cannot_demand_one():
    """The original leniency, kept on the side it still applies to. A dataset that never states
    a version has nothing to compare against, and failing there would make the harness
    unbuildable before it declares one."""
    labels_module.check_app_version({}, "1.5.0")


def test_a_run_that_does_not_say_which_version_it_audited_refuses_to_score():
    """**This used to pass silently and that was the bug.** `run.py` defaults --app-version to
    an empty string, so the one hard stop protecting every number this tool produces did
    nothing unless somebody remembered a flag. Point a run at an older checkout and the report
    looks entirely normal."""
    with pytest.raises(DatasetError, match="--app-version"):
        labels_module.check_app_version({"app_version": "1.4.0"}, "")


def _record(**kwargs) -> dict:
    base = {"id": "g-1", "app_version": "1.4.0", "route": "/catalogue/new-arrivals",
            "selector": "#cover-tidewater", "checker": "meaningful-alt", "criterion": "1.1.1",
            "truth": "fail", "expected_verdict": "fail", "difficulty": "clear",
            "rationale": "alt=\"cover\" names nothing."}
    return {**base, **kwargs}


def _write(directory, *, records, counts) -> None:
    (directory / "1.1.1-non-text-content.json").write_text(
        json.dumps(records), encoding="utf-8")
    (directory / "manifest.json").write_text(
        json.dumps({"dataset_version": "0.1.0", "app_version": "1.4.0", "counts": counts}),
        encoding="utf-8")


# ══ the baseline, and what it is allowed to block ════════════════════════════════════

def _scored(**kwargs) -> accuracy.Score:
    score = accuracy.Score(checker="alt", source=GOLDEN)
    for field_name, value in kwargs.items():
        setattr(score, field_name, value)
    return score


def test_a_first_run_records_its_numbers_rather_than_failing():
    score = _scored(true_positive=30, false_positive=5, false_negative=5, true_negative=10)
    rows = baseline_module.compare([score], {})
    assert all(r.state == baseline_module.RECORDED for r in rows)
    assert baseline_module.blockers(rows) == []


def test_a_drop_beyond_the_tolerance_band_blocks_the_release():
    score = _scored(true_positive=20, false_positive=30, false_negative=0, true_negative=10)
    stored = {"min_sample": 10, "tolerance": 0.02,
              "checkers": {"alt": {GOLDEN: {"precision": 0.9, "recall": 1.0, "f1": 0.95}}}}
    blocked = baseline_module.blockers(baseline_module.compare([score], stored))
    assert [b.metric for b in blocked] == ["precision", "f1"]


def test_a_drop_inside_the_tolerance_band_is_noise_and_does_not_block():
    """A gate with no tolerance fires constantly and gets switched off, which is worse than no
    gate at all."""
    score = _scored(true_positive=49, false_positive=1, false_negative=0, true_negative=0)
    stored = {"min_sample": 10, "tolerance": 0.05,
              "checkers": {"alt": {GOLDEN: {"precision": 1.0, "recall": 1.0, "f1": 1.0}}}}
    rows = baseline_module.compare([score], stored)
    assert baseline_module.blockers(rows) == []
    assert {r.state for r in rows} == {baseline_module.STEADY}


def test_too_small_a_sample_never_gates_in_either_direction():
    score = _scored(true_positive=1, false_positive=2)
    stored = {"min_sample": 30, "checkers": {"alt": {GOLDEN: {"precision": 0.9}}}}
    rows = baseline_module.compare([score], stored)
    assert baseline_module.blockers(rows) == []
    assert all(r.state == baseline_module.TOO_SMALL for r in rows)


def test_a_checker_too_small_to_measure_is_left_out_of_the_stored_baseline():
    """So that a later run with enough records records a real first baseline, instead of
    comparing itself against a number that never meant anything."""
    stored = baseline_module.updated([_scored(true_positive=2)], {}, generated_on="now")
    assert stored["checkers"] == {}


def test_a_checker_that_got_worse_has_the_worse_number_written_down():
    """Keeping the flattering old one is how "proven once" becomes "trusted forever"."""
    score = _scored(true_positive=20, false_positive=20, false_negative=0, true_negative=10)
    stored = {"min_sample": 10, "tolerance": 0.02,
              "checkers": {"alt": {GOLDEN: {"precision": 0.99}}}}
    written = baseline_module.updated([score], stored, generated_on="now")
    assert written["checkers"]["alt"][GOLDEN]["precision"] == pytest.approx(0.5)


def test_the_stored_baseline_keeps_the_decisions_it_was_given():
    written = baseline_module.updated([], {"min_sample": 25, "tolerance": 0.03},
                                      generated_on="now")
    assert (written["min_sample"], written["tolerance"]) == (25, 0.03)
    assert "D-A11Y-82" in written["note"]


def test_an_unmeasured_recall_never_becomes_a_stored_figure():
    """`unmeasured` is a sentence, not a number, and a file full of strings would compare
    against them next run."""
    score = accuracy.Score(checker="alt", source=LIVE, true_positive=40, false_positive=10)
    written = baseline_module.updated([score], {"min_sample": 10}, generated_on="now")
    assert "recall" not in written["checkers"]["alt"][LIVE]
    assert written["checkers"]["alt"][LIVE]["precision"] == pytest.approx(0.8)


# ══ the silences, end to end ═════════════════════════════════════════════════════════

def test_a_run_that_never_captured_the_failing_element_scores_zero_recall_and_says_why():
    """The 21 August shape, scored. Eleven pages, a real failure on one of them, and the check
    reporting nothing because the element was never offered to it."""
    labels = [label(selector="#loans-table-row-2", checker="color", criterion="1.4.1")]
    score = one(labels, {}, captured=set())
    assert score.recall() == 0.0
    assert score.never_looked == 1
    assert score.deferred == 0
