"""The two page-level rules axe has no rule for (QA-25) — 1.4.10 Reflow, 1.4.11 Non-text Contrast.

Pure functions over measurements, so every test here is a known input and a known answer with no
database, no browser and no fixture. That is the whole reason the arithmetic lives in the platform
rather than in the page: a contrast claim on a signed conformance statement has to be re-checkable
against numbers somebody can read.
"""
from __future__ import annotations

import pytest

from apps.a11y import page_rules as pr

WHITE = "rgb(255, 255, 255)"
BLACK = "rgb(0, 0, 0)"
# 3.03:1 against white — just over the line. #767676 is the canonical "lowest passing grey".
GREY_PASS = "rgb(118, 118, 118)"
# 1.36:1 against white — the pale grey border a great many design systems ship, and which
# 1.4.11 has forbidden since 2018. Measured, not assumed: see the ratio assertions below.
GREY_FAIL = "rgb(221, 221, 221)"


# ── colour arithmetic ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("rgb(1, 2, 3)", (1.0, 2.0, 3.0, 1.0)),
    ("rgba(1, 2, 3, 0.5)", (1.0, 2.0, 3.0, 0.5)),
    ("rgb(1 2 3 / 50%)", (1.0, 2.0, 3.0, 0.5)),
    ("transparent", (0.0, 0.0, 0.0, 0.0)),
    ("#fff", (255.0, 255.0, 255.0, 1.0)),
    ("#010203", (1.0, 2.0, 3.0, 1.0)),
])
def test_parse_color_reads_every_form_a_browser_returns(text, expected):
    assert pr.parse_color(text) == expected


@pytest.mark.parametrize("text", ["", "none", "banana", "rgb(", None])
def test_parse_color_returns_none_for_anything_that_is_not_a_colour(text):
    """`None` and transparent are different answers, and the difference is load-bearing.

    A value we could not read must never be treated as a colour we measured; only `transparent`
    means "measured, and it paints nothing".
    """
    assert pr.parse_color(text) is None


def test_contrast_ratio_matches_the_standards_own_extremes():
    assert pr.contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0, abs=0.01)
    assert pr.contrast_ratio((255, 255, 255), (255, 255, 255)) == pytest.approx(1.0)


def test_the_canonical_lowest_passing_grey_is_on_the_right_side_of_three_to_one():
    ratio = pr.contrast_ratio((118, 118, 118), (255, 255, 255))
    assert ratio >= pr.MIN_NON_TEXT_RATIO
    assert pr.contrast_ratio((221, 221, 221), (255, 255, 255)) < pr.MIN_NON_TEXT_RATIO


def test_a_translucent_border_is_measured_at_the_colour_an_eye_receives():
    """Half-transparent black over white is grey, and reading it as black would report a
    contrast the page does not have."""
    blended = pr.composite((0.0, 0.0, 0.0, 0.5), (255.0, 255.0, 255.0))
    assert blended == pytest.approx((127.5, 127.5, 127.5))
    assert pr.contrast_ratio(blended, (255, 255, 255)) < 21.0


def test_flatten_paints_ancestors_root_first_and_skips_what_it_cannot_read():
    # Nearest-first as the companion reports it: a transparent parent over a white page.
    assert pr.flatten(["rgba(0, 0, 0, 0)", WHITE]) == pytest.approx((255.0, 255.0, 255.0))
    # An unreadable layer costs that layer, not the reading.
    assert pr.flatten(["rgba(0, 0, 0, 0)", "banana", BLACK]) == pytest.approx((0.0, 0.0, 0.0))


def test_a_stack_that_paints_nothing_resolves_to_the_browsers_white_canvas():
    """An unstyled body is the commonest page there is; declining to rule on it would switch
    the whole check off for most sites."""
    assert pr.flatten(["rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"]) == pr.CANVAS_WHITE


# ── 1.4.10 Reflow ──────────────────────────────────────────────────────────────────

def _reflow(**over):
    base = {
        "measured": True, "requested_width": 320, "viewport_width": 320,
        "content_width": 320, "overflow_px": 0, "offenders": [],
    }
    return {**base, **over}


def test_a_page_that_fits_at_320_produces_no_failure():
    assert pr.reflow_failure(route="/x", measurement=_reflow()) is None


def test_a_page_that_overflows_fails_and_names_what_stuck_out():
    found = pr.reflow_failure(route="/x", measurement=_reflow(
        content_width=980, overflow_px=660,
        offenders=[{"selector": "div#wide", "tag": "div", "overflow_px": 660,
                    "two_d_reason": ""}],
    ))
    assert found is not None
    assert found.criterion == "1.4.10"
    assert found.rule_id == pr.RULE_REFLOW
    assert found.selector == "div#wide"
    assert "320 pixels wide" in found.evidence
    assert "div#wide" in found.evidence


@pytest.mark.parametrize("measurement", [
    None,
    {},
    {"measured": False, "error": "the narrow-viewport pass did not run (boom)"},
])
def test_a_missing_measurement_proves_nothing_at_all(measurement):
    """The single most important property of this module: an absent measurement is not a page
    that reflowed cleanly. Every capture taken before QA-25 lands here."""
    assert pr.reflow_failure(route="/x", measurement=measurement) is None


def test_a_measurement_taken_at_some_other_width_is_not_evidence_about_this_criterion():
    assert pr.reflow_failure(route="/x", measurement=_reflow(
        requested_width=768, content_width=2000, overflow_px=1232,
        offenders=[{"selector": "div", "tag": "div", "overflow_px": 1232, "two_d_reason": ""}],
    )) is None


def test_an_overflow_caused_only_by_a_data_table_is_the_standards_own_exception():
    """1.4.10 exempts "parts of the content which require two-dimensional layout"."""
    assert pr.reflow_failure(route="/x", measurement=_reflow(
        content_width=1400, overflow_px=1080,
        offenders=[{"selector": "table#rates", "tag": "table", "overflow_px": 1080,
                    "two_d_reason": "table"}],
    )) is None


def test_one_non_exempt_offender_beside_an_exempt_one_still_fails_and_blames_the_right_element():
    found = pr.reflow_failure(route="/x", measurement=_reflow(
        content_width=1400, overflow_px=1080,
        offenders=[
            {"selector": "table#rates", "tag": "table", "overflow_px": 1080,
             "two_d_reason": "table"},
            {"selector": "nav#top", "tag": "nav", "overflow_px": 120, "two_d_reason": ""},
        ],
    ))
    assert found is not None
    assert found.selector == "nav#top"
    assert "table#rates" not in found.evidence      # a developer is not sent to the table
    assert "1 further element" in found.evidence    # but it is not hidden either


def test_a_measured_overflow_nobody_could_attribute_is_still_a_failure():
    """The two numbers are the criterion's own test; they do not depend on naming a culprit."""
    found = pr.reflow_failure(route="/x", measurement=_reflow(
        content_width=900, overflow_px=580, offenders=[]))
    assert found is not None
    assert found.selector == ""
    assert "No single element" in found.evidence


# ── 1.4.11 Non-text Contrast ───────────────────────────────────────────────────────

def _component(**over):
    base = {
        "selector": "button#go", "tag": "button", "type": "", "role": "",
        "has_text": True, "is_field": False,
        "background": "rgba(0, 0, 0, 0)", "background_image": "none",
        "borders": [], "outline": {"style": "none", "width": "0px", "color": BLACK},
        "box_shadow": "none", "behind_stack": [WHITE], "behind_images": False,
    }
    return {**base, **over}


def _measure(*components):
    return {"measured": True, "components": list(components), "counted": len(components),
            "capped": False}


def _border(colour, side="bottom"):
    return [{"side": side, "style": "solid", "width": "1px", "color": colour}]


def test_a_faint_border_on_a_control_fails():
    failures, review = pr.contrast_failures(
        route="/x", measurement=_measure(_component(borders=_border(GREY_FAIL))))
    assert review == ()
    assert len(failures) == 1
    assert failures[0].criterion == "1.4.11"
    assert failures[0].rule_id == pr.RULE_COMPONENT_BOUNDARY
    assert "1.36:1" in failures[0].evidence


def test_a_border_that_clears_three_to_one_does_not():
    failures, _ = pr.contrast_failures(
        route="/x", measurement=_measure(_component(borders=_border(GREY_PASS))))
    assert failures == ()


def test_a_text_button_with_no_drawn_boundary_is_deliberately_not_a_failure():
    """The words identify the control and 1.4.3 governs whether they can be read. Firing here
    would put every borderless text button on every page into a report as a Level AA defect."""
    failures, review = pr.contrast_failures(
        route="/x", measurement=_measure(_component(background="rgb(250, 250, 250)")))
    assert failures == ()
    assert review == ()


def test_a_form_field_with_no_visible_edge_at_all_fails():
    failures, _ = pr.contrast_failures(route="/x", measurement=_measure(_component(
        selector="input#email", tag="input", type="email", is_field=True, has_text=False,
        background=WHITE, behind_stack=[WHITE],
    )))
    assert len(failures) == 1
    assert failures[0].rule_id == pr.RULE_FIELD_BOUNDARY
    assert "no visible edge at all" in failures[0].evidence


def test_a_form_field_with_a_faint_edge_fails_and_prints_the_ratio_and_the_colour():
    failures, _ = pr.contrast_failures(route="/x", measurement=_measure(_component(
        selector="input#email", tag="input", type="email", is_field=True, has_text=False,
        borders=_border(GREY_FAIL, side="top"), background=WHITE,
    )))
    assert len(failures) == 1
    assert "1.36:1" in failures[0].evidence
    assert "rgb(255, 255, 255)" in failures[0].evidence


def test_a_form_field_whose_own_fill_stands_out_is_perceivable_and_passes():
    """A white box on a dark page has a visible edge without drawing one."""
    failures, _ = pr.contrast_failures(route="/x", measurement=_measure(_component(
        tag="input", type="text", is_field=True, has_text=False,
        background=WHITE, behind_stack=["rgb(20, 20, 20)"],
    )))
    assert failures == ()


def test_a_shadow_asks_a_person_rather_than_failing_a_component_it_cannot_measure():
    """A shadow is how most design systems draw the edge they did not draw with a border, and
    its colour cannot be read reliably from the computed value."""
    failures, review = pr.contrast_failures(route="/x", measurement=_measure(_component(
        tag="input", type="text", is_field=True, has_text=False,
        background=WHITE, behind_stack=[WHITE], box_shadow="rgba(0,0,0,0.2) 0px 1px 2px 0px",
    )))
    assert failures == ()
    assert len(review) == 1
    assert "shadow" in review[0]["reason"]


@pytest.mark.parametrize("field,value", [
    ("background_image", "linear-gradient(rgb(255,255,255), rgb(200,200,200))"),
    ("behind_images", True),
])
def test_a_colour_read_from_behind_a_picture_is_declined_not_guessed(field, value):
    """Sampling one pixel and calling it the background is how a contrast checker reports a
    confident wrong number."""
    failures, review = pr.contrast_failures(route="/x", measurement=_measure(
        _component(borders=_border(GREY_FAIL), **{field: value})))
    assert failures == ()
    assert len(review) == 1


def test_a_translucent_border_is_judged_on_what_it_actually_looks_like():
    """Black at 10% opacity over white is a very pale grey — the ratio has to reflect that."""
    failures, _ = pr.contrast_failures(route="/x", measurement=_measure(
        _component(borders=_border("rgba(0, 0, 0, 0.1)"))))
    assert len(failures) == 1


@pytest.mark.parametrize("measurement", [None, {}, {"measured": False, "error": "boom"}])
def test_no_contrast_measurement_proves_nothing(measurement):
    assert pr.contrast_failures(route="/x", measurement=measurement) == ((), ())


# ── what the criteria are recorded as, per page ────────────────────────────────────

def test_a_screen_with_no_measurements_records_no_coverage_whatsoever():
    """Not a pass, not a failure. The same discipline `coverage.from_scan` keeps for a screen
    the scanner could not run on — and what stops an older companion's captures reading as
    pages that reflowed cleanly."""
    assert pr.observations_for(None) == []
    assert pr.observations_for({}) == []
    assert pr.observations_for({"reflow": {"measured": False, "error": "boom"}}) == []


def test_a_clean_page_records_a_pass_for_both_criteria():
    observed = dict((c, o) for c, o, _ in pr.observations_for({
        "reflow": _reflow(),
        "non_text_contrast": _measure(_component(borders=_border(GREY_PASS))),
    }))
    assert observed == {"1.4.10": "passed", "1.4.11": "passed"}


def test_a_broken_page_records_a_failure_for_both_criteria():
    observed = dict((c, o) for c, o, _ in pr.observations_for({
        "reflow": _reflow(content_width=900, overflow_px=580),
        "non_text_contrast": _measure(_component(borders=_border(GREY_FAIL))),
    }))
    assert observed == {"1.4.10": "failed", "1.4.11": "failed"}


def test_a_page_with_no_controls_records_not_applicable_rather_than_a_pass():
    observed = dict((c, o) for c, o, _ in pr.observations_for({
        "non_text_contrast": _measure()}))
    assert observed == {"1.4.11": "not_applicable"}


def test_a_page_whose_every_control_sits_behind_a_gradient_asks_a_person():
    """A criterion nobody could measure must not arrive in the statement wearing a pass."""
    observed = dict((c, o) for c, o, _ in pr.observations_for({
        "non_text_contrast": _measure(_component(behind_images=True))}))
    assert observed == {"1.4.11": "needs_human"}


def test_failures_for_gathers_both_criteria_from_one_screen():
    found = pr.failures_for(route="/x", measurements={
        "reflow": _reflow(content_width=900, overflow_px=580),
        "non_text_contrast": _measure(_component(borders=_border(GREY_FAIL))),
    })
    assert {f.criterion for f in found} == {"1.4.10", "1.4.11"}
    assert all(f.route == "/x" for f in found)


def test_every_rule_id_this_module_raises_is_namespaced_away_from_axe():
    """A defect ticket prints the rule id, and an axe-shaped id would send a developer looking
    for a rule that does not exist in any scanner they can run."""
    for rule_id in (pr.RULE_REFLOW, pr.RULE_FIELD_BOUNDARY, pr.RULE_COMPONENT_BOUNDARY):
        assert rule_id.startswith("a11y-page/")
