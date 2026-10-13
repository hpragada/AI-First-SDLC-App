"""QA-03 — the four accessibility AI checkers: what each looks at, and what a usable answer is.

What these prove, against the task's acceptance criteria:

  AC1  a meaningless alt returns `fail` on 1.1.1 with a reason and a suggested alt
  AC2  a `<div>` wired up as a button returns `fail` on 4.1.2 / 1.3.1 naming that element
  AC3  a control whose visible label differs from its accessible name returns `fail` on 2.5.3
  AC4  every stored finding conforms to the schema and cites a criterion the element was
       queued against; an incomplete one is rejected with a correctable message
  AC5  each checker is run against a known-good and a known-bad sample, ≥90% coverage
       (`make cov MOD=apps/a11y/checkers TESTS=tests/test_a11y_checkers.py`)

The task text says "a prompt plus a Pydantic schema the model must fill", wrapped around a
direct model call. Correction R4 replaced that before QA-01: there is no direct model call
anywhere on this path (#7). The prompts live in the `09c_a11y_judge` agent body and the schema
is enforced by `record_a11y_finding` — so AC1-AC4 are proven where they actually happen, at
the tool the judge writes through, and the selection rules are proven directly.

Beyond the ACs, and deliberately:

  * **the two skips that were NOT made** — `alt=""` and `role="presentation"` on an image are
    candidates, because an informative image silenced either way is the failure the check
    exists to find. A test pins each, so neither can be "optimised" away later.
  * **selection is stable** — the same page produces the same batch in the same order, which
    is what makes a run comparable against the golden set (QA-09).
  * **an `uncertain` is never held to a `fail`'s requirements** (D-A11Y-5) — demanding a fix
    from a judge that just said it could not see enough would strand the element instead of
    letting it reach a person.
"""
from pathlib import Path

import pytest

from apps.a11y.checkers import (
    CHECKERS,
    HELD_BACK_SELECTION_RULES,
    SELECTION_RULES,
    STYLE_KEYS,
    AnswerIncomplete,
    CapturedElement,
    checkers_for,
    describe_rules,
    explain,
    requirements_for,
    select,
    settled,
    to_candidate,
    verify_answer,
)
from integrations.types import A11Y_CHECKER_CRITERIA, A11yCandidate

AGENT_BODY = Path(__file__).resolve().parents[2] / "agents" / "09c_a11y_judge" / "agent.md"
COMPANION_CAPTURE = (Path(__file__).resolve().parents[2]
                     / "runner" / "companion" / "assets" / "a11y_audit.mjs")


def element(**kwargs) -> CapturedElement:
    """A captured element with everything the rules read present and inert by default, so a
    test only has to state the one fact it is about."""
    base = {
        "selector": "main > *", "tag": "div", "role": "", "attrs": {}, "text": "",
        "accessible_name": "", "interactive": False, "rendered": True,
        "styles": {key: "" for key in STYLE_KEYS},
        "parent_styles": {key: "" for key in STYLE_KEYS},
        "html": "", "context": "", "screenshot_ref": "", "route": "/home",
    }
    base.update(kwargs)
    return CapturedElement(**base)


# ── the rule set holds together ──────────────────────────────────────
def test_there_is_exactly_one_rule_per_checker():
    assert tuple(rule.checker for rule in SELECTION_RULES) == CHECKERS


def test_each_rule_claims_the_criteria_its_checker_actually_owns():
    """The rules table and the runtime guard in `A11yJudgment` must agree about which criteria
    a checker may report against — two tables disagreeing would let a selection be made for a
    criterion the judgment layer then refuses."""
    for rule in SELECTION_RULES:
        assert rule.criteria == A11Y_CHECKER_CRITERIA[rule.checker]


def test_the_rule_set_can_be_read_by_someone_who_does_not_read_python():
    described = describe_rules()
    for rule in SELECTION_RULES:
        assert rule.checker in described
        assert rule.covers in described and rule.skips in described


def test_the_element_checkers_judge_these_criteria_and_no_others():
    """R7 / team decision D5: 1.1.1, 1.3.1, 4.1.2, 1.4.1 and 2.5.3 shipped in the POC, and 2.4.6
    is Phase 2 — a rule quietly claiming it would put a Phase-2 criterion in a POC report.

    **1.4.11 joined the set in QA-25, and it is the one entry here that is only half a
    criterion.** The other half is `apps.a11y.page_rules`, which measures whether a control's
    edge reaches 3:1 deterministically; `graphics` judges the part no rule can — which parts
    of an icon or a chart carry the meaning, and whether they can be made out. Neither half
    covers 1.4.11 alone, and this test says nothing about whether the other half exists;
    `test_a11y_owner_capability` is what proves that.

    It was held back for part of 1 September, while the ownership registry was brought into
    line with correction R14 — the registry gave 1.4.11 to `rule` and this map is what the AI
    owns, and the two disagreeing is what five guards reported for five days. Nothing here
    should be held now, and the second assertion says so rather than leaving it unsaid.
    """
    covered = {c for rule in SELECTION_RULES for c in rule.criteria}
    assert covered == {"1.1.1", "1.3.1", "4.1.2", "1.4.1", "2.5.3", "1.4.11"}
    assert HELD_BACK_SELECTION_RULES == (), (
        "a check is held back and this test has not been told which or why"
    )


# ── alt: WCAG 1.1.1 ──────────────────────────────────────────────────
@pytest.mark.parametrize("el", [
    element(tag="img", attrs={"src": "/chart.png", "alt": "chart"}),
    element(tag="area", attrs={"alt": "Region"}),
    element(tag="input", attrs={"type": "image", "alt": "Search"}),
    element(tag="div", role="img", attrs={"aria-label": "Logo"}),
    element(tag="svg", html="<svg><title>Sales trend</title></svg>"),
    element(tag="svg", attrs={"aria-label": "Sales trend"}),
])
def test_alt_selects_non_text_content_presented_to_the_user(el):
    assert "alt" in checkers_for(el)


@pytest.mark.parametrize("el", [
    element(tag="p", text="ordinary prose"),
    element(tag="svg", html="<svg><path d='M0 0'/></svg>"),      # never announced at all
    element(tag="img", attrs={"src": "/x.png"}, rendered=False),  # not on the page
    element(tag="input", attrs={"type": "text"}),
])
def test_alt_skips_what_is_not_non_text_content(el):
    assert "alt" not in checkers_for(el)


def test_an_empty_alt_is_judged_not_skipped():
    """The failure this check exists to find runs BOTH ways: a decorative image wrongly
    described, and an informative one left empty. Skipping `alt=""` would remove half of it."""
    informative = element(tag="img", attrs={"src": "/revenue-chart.png", "alt": ""},
                          context="The figures appear nowhere else on the page.")
    assert "alt" in checkers_for(informative)


def test_an_image_marked_presentational_is_still_judged():
    """`role="presentation"` is the author's *claim* that the image carries no information.
    Whether that claim is true is exactly what 1.1.1 asks."""
    assert "alt" in checkers_for(
        element(tag="img", role="presentation", attrs={"src": "/chart.png"}))


# ── semantics: WCAG 1.3.1 + 4.1.2 ────────────────────────────────────
@pytest.mark.parametrize("el", [
    element(tag="div", interactive=True, text="Buy", html="<div onclick='buy()'>Buy</div>"),
    element(tag="span", attrs={"tabindex": "0"}, text="Next"),
    element(tag="a", text="Open", html="<a>Open</a>"),          # no href: not a link
    element(tag="button", role="link", text="Buy"),             # role overrides the tag
    element(tag="div", role="button", text="Buy"),
])
def test_semantics_selects_structure_that_may_be_drawn_rather_than_real(el):
    assert "semantics" in checkers_for(el)


def test_semantics_selects_text_merely_styled_as_a_heading():
    fake_heading = element(
        tag="div", text="Quarterly results",
        styles={**{k: "" for k in STYLE_KEYS}, "font-size": "24px", "font-weight": "700"},
        parent_styles={**{k: "" for k in STYLE_KEYS}, "font-size": "16px"},
    )
    assert "semantics" in checkers_for(fake_heading)


@pytest.mark.parametrize("el", [
    element(tag="button", text="Buy", interactive=True),
    element(tag="a", attrs={"href": "/next"}, text="Next", interactive=True),
    element(tag="input", attrs={"type": "checkbox"}, interactive=True),
    element(tag="ul", role="list"),                     # a role that only restates the tag
    element(tag="h2", role="heading", text="Results"),
    element(tag="p", text="ordinary prose"),
])
def test_semantics_skips_structure_that_is_already_real(el):
    assert "semantics" not in checkers_for(el)


def _sized(weight: str) -> CapturedElement:
    return element(
        tag="div", text="Quarterly results",
        styles={**{k: "" for k in STYLE_KEYS}, "font-size": "24px", "font-weight": weight},
        parent_styles={**{k: "" for k in STYLE_KEYS}, "font-size": "16px"},
    )


def test_a_keyword_font_weight_counts_the_same_as_a_number():
    """Browsers report `font-weight` either way; reading only numbers would silently stop
    selecting every heading-shaped element styled with the keyword."""
    assert "semantics" in checkers_for(_sized("bold"))
    assert "semantics" in checkers_for(_sized("bolder"))
    assert "semantics" not in checkers_for(_sized("normal"))


def test_an_unreadable_font_weight_does_not_make_something_a_heading():
    """A capture that returned nonsense must not invent a finding out of it."""
    assert "semantics" not in checkers_for(_sized("very-heavy"))


def test_bold_text_no_larger_than_its_surroundings_is_not_a_heading_candidate():
    """Otherwise every bold lead paragraph on every page costs a judgment."""
    emphasis = element(
        tag="strong", text="Note",
        styles={**{k: "" for k in STYLE_KEYS}, "font-size": "16px", "font-weight": "700"},
        parent_styles={**{k: "" for k in STYLE_KEYS}, "font-size": "16px"},
    )
    assert "semantics" not in checkers_for(emphasis)


# ── color: WCAG 1.4.1 ────────────────────────────────────────────────
def _coloured(**kwargs) -> CapturedElement:
    styles = {**{k: "" for k in STYLE_KEYS}, "color": "rgb(200, 0, 0)"}
    styles.update(kwargs.pop("styles", {}))
    return element(
        text=kwargs.pop("text", "Overdue"), styles=styles,
        parent_styles={**{k: "" for k in STYLE_KEYS}, "color": "rgb(20, 20, 20)"},
        **kwargs,
    )


def test_color_selects_text_singled_out_by_colour_alone():
    assert "color" in checkers_for(_coloured())


def test_color_selects_a_filled_indicator_with_no_text():
    dot = element(
        selector="span.status-dot",
        styles={**{k: "" for k in STYLE_KEYS}, "background-color": "rgb(0, 160, 0)"},
        parent_styles={**{k: "" for k in STYLE_KEYS}, "background-color": "transparent"},
    )
    assert "color" in checkers_for(dot)


def test_color_selects_an_indicator_drawn_only_as_a_coloured_ring():
    """The third way to colour a thing, after a background and a series stroke.

    On `/loans/renewals` three status markers sit in adjacent rows of one table. Two carry
    their colour in `background`; one is a `.ring`, drawn with `border: 3px solid`. The two
    were offered to the colour rule and the third was not — `border-color` was never captured,
    so an empty span with no background read as carrying no colour at all.
    """
    ring = element(
        selector="#renew-tidewater",
        styles={**{k: "" for k in STYLE_KEYS},
                "border-style": "solid", "border-color": "rgb(196, 106, 20)"},
        parent_styles={**{k: "" for k in STYLE_KEYS}, "background-color": "rgb(255, 255, 255)"},
    )
    assert "color" in checkers_for(ring)


def test_a_border_colour_with_no_border_drawn_is_not_colour():
    """`border-color` computes to the element's own `color` on anything that never set one, so
    a painted colour with `border-style: none` describes a border that is not there. Counting
    it would make every element on the page a colour candidate."""
    plain = element(
        styles={**{k: "" for k in STYLE_KEYS},
                "border-style": "none", "border-color": "rgb(196, 106, 20)"},
    )
    assert "color" not in checkers_for(plain)


def test_the_companion_captures_exactly_the_styles_the_rules_read():
    """The two `STYLE_KEYS` lists are written out at both ends and nothing compared them.

    A key the rules read and the browser never sends arrives empty, and an empty style is
    indistinguishable from a style that paints nothing — so the loss is silent everywhere, by
    design. It has now happened twice: `stroke`/`fill`, which left every chart series colourless
    to the one rule that asks about colour, and `border-color`, which did the same to anything
    outlined rather than filled. The companion's own comment says a missing key is not an error
    anywhere. This is that error.
    """
    source = COMPANION_CAPTURE.read_text(encoding="utf-8")
    block = source.split("const STYLE_KEYS = [", 1)[1].split("];", 1)[0]
    captured = [line.split('"')[1] for line in block.splitlines()
                if line.strip().startswith('"')]

    assert captured == list(STYLE_KEYS), (
        "the browser captures a different set of computed styles than the rules read — "
        f"only in the capture: {sorted(set(captured) - set(STYLE_KEYS))}; "
        f"only in the rules: {sorted(set(STYLE_KEYS) - set(captured))}"
    )


def test_color_selects_a_chart_series_drawn_in_a_stroke_colour():
    """The same shape as the tinted-row case, one level further in.

    `/reports/branch-comparison` draws three branches as three `<polyline>` elements told apart
    by stroke colour and nothing else. Two things had to be true before that could ever be
    judged and neither was: the shapes were not offered by the capture, and `stroke` was not a
    style key, so even offered they carried no colour any rule could read. A `<polyline>` has no
    text and no background, so both earlier tests here would have passed while the page's only
    1.4.1 failure went unreported and the page was recorded as checked.
    """
    series = element(
        selector="#chart-branches polyline:nth-of-type(2)",
        tag="polyline",
        styles={**{k: "" for k in STYLE_KEYS}, "stroke": "rgb(214, 69, 65)"},
        parent_styles={**{k: "" for k in STYLE_KEYS}, "stroke": "none"},
    )
    assert "color" in checkers_for(series)


def test_color_selects_an_area_series_drawn_in_a_fill_colour():
    """A filled area chart carries its series colour in `fill` rather than `stroke`."""
    band = element(
        selector="#chart-branches polygon:nth-of-type(1)",
        tag="polygon",
        styles={**{k: "" for k in STYLE_KEYS}, "fill": "rgb(31, 119, 180)"},
        parent_styles={**{k: "" for k in STYLE_KEYS}, "fill": "none"},
    )
    assert "color" in checkers_for(band)


def test_color_does_not_claim_every_icon_because_fill_has_a_default():
    """**The reason `fill` is read for two tags and not for all of them.**

    `getComputedStyle` reports `fill` as opaque black on any SVG element that never set it, so a
    rule treating a painted fill as meaningful in general would claim every icon on every page,
    spend the run's judgment budget on decoration, and push real candidates out of the pass. An
    `<svg>` with the default fill and nothing else is not a colour question.
    """
    icon = element(
        selector="span.bookmark svg",
        tag="svg",
        styles={**{k: "" for k in STYLE_KEYS}, "fill": "rgb(0, 0, 0)"},
        parent_styles={**{k: "" for k in STYLE_KEYS}, "fill": "rgb(0, 0, 0)"},
    )
    assert "color" not in checkers_for(icon)


def test_a_series_shape_with_no_colour_of_its_own_is_not_claimed():
    """A shape inheriting its parent's stroke is not singled out by colour, so there is nothing
    for 1.4.1 to be about."""
    plain = element(
        selector="#chart-branches polyline",
        tag="polyline",
        styles={**{k: "" for k in STYLE_KEYS}, "stroke": "rgb(0, 0, 0)"},
        parent_styles={**{k: "" for k in STYLE_KEYS}, "stroke": "rgb(0, 0, 0)"},
    )
    assert "color" not in checkers_for(plain)


def test_color_selects_a_table_row_tinted_to_carry_a_status():
    """The shape that went unreported on a real page for a whole audit.

    `/loans/current` tints each row of the loans table to say overdue / due soon / on loan,
    with a colour key underneath and the status written nowhere else. The rule has always
    claimed such a row — this test says so — but the capture never offered `tr`, so the one
    element on that page which fails 1.4.1 was never judged and the page was recorded as
    checked. The companion side of this pairing is pinned in `test_a11y_baseline.py`; neither
    half is any use alone, which is exactly how the gap survived.
    """
    row = element(
        tag="tr", selector="#loans-table > tbody > tr:nth-of-type(2)", text="Tidewater 12 Aug",
        styles={**{k: "" for k in STYLE_KEYS}, "background-color": "rgb(255, 224, 224)"},
        parent_styles={**{k: "" for k in STYLE_KEYS}, "background-color": "rgb(255, 255, 255)"},
    )
    assert "color" in checkers_for(row)


def test_color_leaves_the_cells_inside_a_tinted_row_to_the_row_itself():
    """One question, asked once. A cell inherits the tint rather than painting it, so the rule
    declines it — correctly, and now harmlessly, since the row that does own the colour is
    offered. Before that it was the whole failure: everything that arrived was declined."""
    cell = element(
        tag="td", selector="#loans-table > tbody > tr:nth-of-type(2) > td", text="Tidewater",
        styles={**{k: "" for k in STYLE_KEYS}, "background-color": "rgba(0, 0, 0, 0)"},
        parent_styles={**{k: "" for k in STYLE_KEYS}, "background-color": "rgb(255, 224, 224)"},
    )
    assert "color" not in checkers_for(cell)


@pytest.mark.parametrize("second_cue", [
    {"styles": {"text-decoration-line": "underline"}},
    {"html": "<span><svg aria-hidden='true'/>Overdue</span>"},
    {"text": "Overdue *"},
])
def test_color_skips_anything_that_already_carries_a_second_visual_cue(second_cue):
    """1.4.1 is breached only when colour is the ONLY visual means. An underline, an icon or a
    marker character is that second means, and the criterion is met."""
    assert "color" not in checkers_for(_coloured(**second_cue))


def test_color_does_not_treat_a_border_as_a_second_cue():
    """**A border used to be on that list and had to come off** (RESEARCH_CORRECTIONS R19).

    The reasoning was that a border is visual and is not colour, which is true in general and
    wrong in the case that matters most. A field marked invalid by turning its border red
    **already had a border** — every field on the page has one — and only its colour changed.
    Treating the border as a second cue meant the rule read the presence of the thing being
    coloured as proof that colour was not the only cue, and declined to look. That is the
    commonest way on the web to mark a field invalid, and nothing else covers it: 1.4.1 has one
    scanner rule and it is about links in prose.

    Nothing narrower was available, and that was measured rather than assumed. Comparing the
    border's colour against the parent's saves four candidates out of three hundred, because a
    parent almost never has a border to compare against.
    """
    invalid_field = _coloured(styles={"border-style": "solid"})
    assert "color" in checkers_for(invalid_field)


@pytest.mark.parametrize("el", [
    element(tag="p", text="same colour as everything around it"),
    element(tag="div", rendered=False),
    element(tag="div"),                                  # no text, no fill
])
def test_color_skips_what_colour_could_not_be_carrying(el):
    assert "color" not in checkers_for(el)


def test_a_missing_screenshot_does_not_remove_an_element_from_the_colour_check():
    """It becomes an `uncertain` verdict from the judge, which reaches a person. Deciding it
    here would put the platform in the business of pre-judging what it never looked at."""
    assert "color" in checkers_for(_coloured(screenshot_ref=""))


# ── label: WCAG 2.5.3 ────────────────────────────────────────────────
def test_semantics_selects_an_in_page_link_because_it_does_not_navigate():
    """**The tab strip case** (golden/README gap 2). The rule skips an `<a>` that has an href,
    on the reasoning that a real link with real semantics needs no judgment. That holds for a
    link that goes somewhere. An in-page link does not navigate — it may be a tab, a disclosure
    or a toggle wearing an anchor — and the case this was found on is three of them styled as a
    tab strip, announced as links, with nothing saying which one is showing.

    Measured before it was widened: the whole fixture holds four in-page links against 228
    ordinary ones, so this asks about 1.7% of the anchors and leaves real navigation alone.
    """
    tab = element(tag="a", text="Loans", attrs={"href": "#panel-loans"}, interactive=True,
                  html='<a href="#panel-loans">Loans</a>')
    assert "semantics" in checkers_for(tab)


def test_semantics_still_skips_a_link_that_actually_goes_somewhere():
    ordinary = element(tag="a", text="Borrowing guide", attrs={"href": "/help/borrowing-guide"},
                       interactive=True, html='<a href="/help/borrowing-guide">Borrowing guide</a>')
    assert "semantics" not in checkers_for(ordinary)


def test_semantics_selects_the_container_holding_a_row_of_in_page_links():
    """One tab cannot tell you whether it is part of a tab list, and the relationship between
    the strip and the panels below it lives on the container or nowhere. So the strip is asked
    about as well as the tabs in it."""
    strip = element(
        tag="div", text="Loans Members Stock",
        html=('<div class="tabstrip" id="report-tabs">'
              '<a class="is-current" href="#panel-loans">Loans</a>'
              '<a href="#panel-members">Members</a>'
              '<a href="#panel-stock">Stock</a></div>'),
    )
    assert "semantics" in checkers_for(strip)


def test_semantics_leaves_prose_that_happens_to_contain_an_anchor_alone():
    """Two of anything is a pair. A paragraph with a couple of in-page references is prose, and
    claiming it would spend a judgment on every footnote in the application."""
    prose = element(
        tag="div", text="See the notes and the summary.",
        html=('<div class="panel"><p>See the <a href="#notes">notes</a> and the '
              '<a href="#summary">summary</a>.</p></div>'),
    )
    assert "semantics" not in checkers_for(prose)


def test_a_dropdown_is_out_of_scope_because_its_options_are_not_its_label():
    """A `<select>`'s inner text is every option it holds, and a closed one displays none of
    them. Read as the visible label, this compared the announced name against the option list,
    found no match, and reported a possible mismatch — on all 13 dropdowns in the 31 August
    Meridian audit, every one of which then reached the AI and came back "cannot determine".

    There was never anything to compare: a dropdown is named by its `<label for=…>`, so its
    visible label IS its accessible name. Out of scope, and out of scope is not a pass — the
    same distinction `test_out_of_scope_is_not_the_same_as_satisfied` turns on.
    """
    dropdown = element(
        tag="select", accessible_name="Home branch",
        text="Fenner Road\nAshcombe\nNorth Quay",
        html="<select id='settings-branch'><option>Fenner Road</option></select>",
    )
    assert "label" not in checkers_for(dropdown)
    assert settled(dropdown) == {}


def test_a_textarea_is_out_of_scope_for_the_same_reason():
    """Its inner text is what somebody typed into it, which is content and not a label."""
    box = element(tag="textarea", accessible_name="Notes for staff",
                  text="Left at the Fenner Road desk")
    assert "label" not in checkers_for(box)


def test_label_selects_a_control_whose_name_does_not_contain_its_visible_text():
    mismatch = element(tag="button", text="Buy now", accessible_name="Purchase",
                       html="<button aria-label='Purchase'>Buy now</button>")
    assert "label" in checkers_for(mismatch)


def test_label_skips_a_control_whose_name_already_contains_the_visible_text():
    """"Contains", not "equals" — the criterion's own wording. A name that adds words after
    the visible label satisfies it as a matter of fact, so there is nothing left to judge."""
    fine = element(tag="button", text="Buy now",
                   accessible_name="Buy now — opens in a new window")
    assert "label" not in checkers_for(fine)


# ── a criterion ANSWERED by the rules is a decision, not a silence ───────────
#
# The skip above used to be the end of the story: the checker was left out of the batch and
# nothing anywhere recorded that a question had been settled. So a control the platform had
# correctly cleared was indistinguishable from one nothing had ever looked at — and on the
# 31 August audit that covered 22 of the 42 labelled 2.5.3 controls. Every one of them right;
# every one of them reported by the accuracy harness as "never looked at" and counted wrong,
# with `label` unable to reach its sample floor no matter how much data was added, because the
# dataset pairs every AI-judged failure with a rule-settled pass and always will.


def test_a_criterion_met_as_a_matter_of_fact_is_reported_as_answered():
    fine = element(tag="button", text="Buy now",
                   accessible_name="Buy now — opens in a new window")
    assert settled(fine) == {"label": "pass"}


def test_out_of_scope_is_not_the_same_as_satisfied():
    """The distinction the whole change turns on, and the one a single boolean could not carry.

    2.5.3 applies to "components with labels that include text". A control with no visible text
    is outside the criterion — nothing was decided about it, and claiming a pass would be
    inventing a result. A control with no accessible name at all is 4.1.2's problem. Neither is
    an answer, and neither may be reported as one.
    """
    no_visible_text = element(tag="button", text="", accessible_name="Submit")
    assert settled(no_visible_text) == {}
    assert "label" not in checkers_for(no_visible_text)

    no_name = element(tag="button", text="Submit", accessible_name="")
    assert settled(no_name) == {}
    assert "label" not in checkers_for(no_name)


def test_a_real_mismatch_is_never_settled_it_is_dispatched():
    """The failure case must reach the AI. A rule that quietly passed this would be worse than
    no rule at all — it would clear the exact thing the check exists to find."""
    mismatch = element(tag="button", text="Buy now", accessible_name="Purchase")
    assert settled(mismatch) == {}
    assert "label" in checkers_for(mismatch)


@pytest.mark.parametrize("el", [
    element(tag="button", text="Buy now", accessible_name="Purchase"),          # dispatched
    element(tag="button", text="Buy now", accessible_name="Buy now, please"),   # settled
    element(tag="button", text="", accessible_name="Submit"),                   # out of scope
    element(tag="div", text="Buy now", accessible_name="Purchase"),             # not a control
])
def test_a_checker_never_both_asks_and_answers(el):
    """**The invariant that keeps the two halves from paying twice.**

    An element the rules have already answered must not also be dispatched: we would spend the
    engine budget being told what we already know, and then hold two answers to one question
    with no rule for which wins. Asserted across every checker rather than only `label`, so the
    next rule that learns to settle something inherits the guarantee instead of re-deriving it.
    """
    answered = settled(el)
    asked = checkers_for(el)
    assert not (set(answered) & set(asked)), (
        f"{sorted(set(answered) & set(asked))} both dispatched and settled"
    )


def test_every_settled_verdict_is_one_the_platform_recognises():
    """A rule may only return a verdict the rest of the platform can store and read. A typo here
    would travel silently into a conformance report."""
    from integrations.types import A11Y_VERDICTS

    fine = element(tag="button", text="Buy now", accessible_name="Buy now — new window")
    assert set(settled(fine).values()) <= A11Y_VERDICTS


def test_label_compares_whole_words_and_not_letters():
    """**The bug this replaced was silent and it lost real failures** (RESEARCH_CORRECTIONS
    R20b). The rule asked whether the visible label appeared inside the accessible name as a run
    of characters. The letters of *search* sit inside *research*, so a button reading "Search"
    announced as "Research tools" was read as already satisfying the criterion and never
    reached anybody.

    It is not satisfied. A speech-input user looks at the button, says "Search", and nothing
    happens, because the name the software matches against contains no such word. Both the
    criterion's ACT rule and axe compare whole words; so does this now.
    """
    hidden_failure = element(tag="button", text="Search", accessible_name="Research tools",
                             html="<button aria-label='Research tools'>Search</button>")
    assert "label" in checkers_for(hidden_failure)


def test_label_treats_punctuation_as_a_separator_rather_than_as_a_character():
    """A trailing ellipsis is the standard way to say a control opens a dialog, and it is not
    part of the label. Both implementations of this comparison ignore punctuation, so a name
    that is the visible words without the mark satisfies the criterion and needs no judgment."""
    settled = element(tag="button", text="Update details…", accessible_name="Update details")
    assert "label" not in checkers_for(settled)


def test_label_keeps_letters_that_are_not_english():
    """`str.isalnum()` rather than a naive a-z filter. Stripping accented and non-Latin letters
    would empty the label of any application not written in English, and every control on the
    page would then look like a mismatch."""
    fine = element(tag="button", text="Caf\u00e9", accessible_name="Caf\u00e9 list")
    assert "label" not in checkers_for(fine)


def test_label_ignores_case_and_spacing_when_deciding_there_is_nothing_to_judge():
    assert "label" not in checkers_for(
        element(tag="button", text="  Buy   Now ", accessible_name="buy now"))


@pytest.mark.parametrize("el", [
    element(tag="button", text="", accessible_name="Close"),        # no visible text label
    element(tag="button", text="Buy now", accessible_name=""),      # that is 4.1.2, not 2.5.3
    element(tag="p", text="Buy now", accessible_name="Purchase"),   # not a control
    element(tag="a", text="Buy now", accessible_name="Purchase"),   # <a> with no href
    element(tag="button", text="Buy now", accessible_name="Purchase", rendered=False),
])
def test_label_skips_what_the_criterion_does_not_reach(el):
    assert "label" not in checkers_for(el)


def test_a_link_with_an_href_is_a_control_for_label_purposes():
    link = element(tag="a", attrs={"href": "/buy"}, text="Buy now",
                   accessible_name="Purchase")
    assert "label" in checkers_for(link)


def test_a_submit_button_is_labelled_by_its_value_not_by_text_it_can_never_have():
    """An `<input>` has no inner text — not "usually none", none, ever.

    Reading only inner text meant the rule found no visible label, concluded from that silence
    that 2.5.3 did not apply, and moved on. That put every submit and reset button in every
    form permanently out of scope for the criterion, without once saying so.
    """
    button = element(tag="input", attrs={"type": "submit", "value": "Search",
                                         "aria-label": "Go"},
                     text="", accessible_name="Go",
                     html='<input type="submit" value="Search" aria-label="Go">')
    assert "label" in checkers_for(button)


@pytest.mark.parametrize("input_type", ["submit", "reset", "button"])
def test_every_input_type_whose_value_is_its_face_is_read_that_way(input_type):
    el = element(tag="input", attrs={"type": input_type, "value": "Search"},
                 text="", accessible_name="Go")
    assert "label" in checkers_for(el)


def test_what_a_person_typed_into_a_field_is_never_read_as_that_fields_label():
    """The reason the three types are named rather than every `<input>` taken as labelled.

    On a text field `value` is the user's own data. Reading it as a visible label would compare
    what somebody typed against the field's accessible name and report the difference as a
    defect — a finding against a real person's name, raised on every filled-in form.
    """
    typed_in = element(tag="input", attrs={"type": "text", "value": "Ada Lovelace"},
                       text="", accessible_name="Full name")
    assert "label" not in checkers_for(typed_in)


def test_a_submit_button_with_no_value_of_its_own_stays_out_of_scope():
    """The browser draws its own word there, in its own language. It is not in the markup, so
    there is nothing to compare the accessible name against and nothing honest to report."""
    bare = element(tag="input", attrs={"type": "submit"}, text="", accessible_name="Go")
    assert "label" not in checkers_for(bare)


def test_a_submit_button_whose_name_already_holds_its_value_is_not_asked_about():
    met = element(tag="input", attrs={"type": "submit", "value": "Search"},
                  text="", accessible_name="Search the catalogue")
    assert "label" not in checkers_for(met)


# ── structure: WCAG 1.3.1, the container question ────────────────────
@pytest.mark.parametrize("tag", ["table", "ul", "ol", "dl", "fieldset"])
def test_structure_selects_every_container_that_carries_an_arrangement(tag):
    """Including the ones that look correct.

    Whether a table's headers are the RIGHT cells, whether a list's items are really items,
    whether a legend names its group — none of that is decidable from the tag, and the rule
    engine already covers the cases where markup contradicts itself. What is left is the
    judgment this check exists for.
    """
    assert "structure" in checkers_for(element(tag=tag, text="Subject Shelf"))


def test_structure_selects_a_table_with_no_header_cells():
    """The failure that went unreported on eleven pages: not pretending to be anything, so
    `semantics` never reached it, and the page was recorded as satisfying 1.3.1 regardless."""
    table = element(tag="table", selector="#subject-index", text="Subject Shelf Botany 4B",
                    html="<table id=subject-index><tr><td>Subject</td><td>Shelf</td></tr>"
                         "<tr><td>Botany</td><td>4B</td></tr></table>")
    assert checkers_for(table) == ("structure",)


def test_a_layout_table_is_still_asked_about_rather_than_assumed_harmless():
    """`role=presentation` is an author's CLAIM that there is no structure here. Whether that
    is true is the question 1.3.1 asks — the same reasoning that keeps `alt=""` in scope for
    the alt check. A layout table announced as one is a `pass`, and saying so costs one
    judgment."""
    assert "structure" in checkers_for(
        element(tag="table", role="presentation", text="left right"))


def test_structure_selects_a_run_of_identically_classed_children():
    """A list drawn without being one. To a screen reader it is an undifferentiated run of
    text with no count, no beginning and no end."""
    grid = element(tag="div", attrs={"class": "card-grid"}, text="one two three",
                   html='<div class="card-grid"><div class="card">one</div>'
                        '<div class="card">two</div><div class="card">three</div></div>')
    assert "structure" in checkers_for(grid)


def test_two_panels_are_a_layout_and_are_left_alone():
    """Two of anything is a pair, not a list, and a two-panel arrangement is far more often a
    layout. The threshold is named (`REPEATED_CHILD_MINIMUM`) so it can be raised on evidence
    rather than argued about."""
    split = element(tag="div", attrs={"class": "split"}, text="left right",
                    html='<div class="split"><div class="pane">left</div>'
                         '<div class="pane">right</div></div>')
    assert "structure" not in checkers_for(split)


def test_the_containers_own_class_is_never_counted_as_one_of_its_children():
    """Otherwise a container with two same-class children would reach three by counting
    itself, and every two-panel layout would be judged."""
    assert "structure" not in checkers_for(element(
        tag="div", attrs={"class": "pane"}, text="left right",
        html='<div class="pane"><div class="pane">left</div><div class="pane">right</div></div>'))


def test_structure_selects_a_form_whose_grouped_fields_have_no_grouping():
    """Radio buttons under a heading that is only text tell a screen-reader user the options
    and never the question they answer."""
    form = element(tag="form", text="Delivery",
                   html='<form><input type="radio" name="d"><input type="radio" name="d"></form>')
    assert "structure" in checkers_for(form)


@pytest.mark.parametrize("markup", [
    '<form><fieldset><legend>Delivery</legend><input type="radio" name="d"></fieldset></form>',
    '<form><div role="radiogroup" aria-label="Delivery"><input type="radio" name="d"></div></form>',
    '<form><div role="group" aria-label="Delivery"><input type="checkbox" name="d"></div></form>',
])
def test_a_form_that_already_groups_its_fields_is_not_asked_about(markup):
    """Correct is correct, whether it is carried by a native element or by ARIA."""
    assert "structure" not in checkers_for(element(tag="form", text="Delivery", html=markup))


def test_a_form_with_no_fields_that_need_grouping_is_left_alone():
    """A search box is not a set of related options. Anything else about a form is another
    checker's business, or nobody's."""
    assert "structure" not in checkers_for(element(
        tag="form", text="Search", html='<form><input type="search" name="q"></form>'))


def test_structure_skips_a_container_that_never_rendered():
    assert "structure" not in checkers_for(element(tag="table", rendered=False))


def test_the_two_halves_of_1_3_1_are_separate_checks_that_may_both_apply():
    """`semantics` answers for one element; `structure` answers for the arrangement. Both own
    1.3.1, and coverage takes the worst outcome reported for it — so a correct table holding a
    fake button does not let either answer hide the other."""
    from integrations.types import A11Y_CHECKER_CRITERIA

    assert "1.3.1" in A11Y_CHECKER_CRITERIA["semantics"]
    assert A11Y_CHECKER_CRITERIA["structure"] == ("1.3.1",)


def test_a_failing_structure_finding_must_name_the_markup_to_add():
    """"This table has no headers" does not tell anyone what to write, and writing it is the
    whole reason this question is answered by judgment rather than by a rule."""
    with pytest.raises(AnswerIncomplete, match="markup to add"):
        verify_answer(checker="structure", verdict="fail",
                      evidence="the first row is <td> cells", suggested_fix="")


def test_a_structure_failure_that_names_the_markup_is_accepted():
    verify_answer(checker="structure", verdict="fail",
                  evidence="the first row is <td> cells",
                  suggested_fix="make the first row <th scope='col'>Subject</th> ...")


# ── the container's shape, which is what makes the container checks work ─────
OUTLINE = {"kind": "table", "rows": 401, "columns": 2, "header_cells": 0,
           "first_row": [{"text": "Title", "header": False},
                         {"text": "Status", "header": False}]}


def test_a_containers_shape_travels_to_the_judge():
    """The whole point of the outline: a table's markup is bounded and its shape is not.

    Measured on a real 401-row table in a real browser: 31,985 characters of markup against 906
    of outline, with nothing about the shape lost. The markup would have been cut at 8,000 —
    three quarters of the table gone, and the judge answering as though it had seen all of it.
    """
    element = CapturedElement.from_dict(
        {"tag": "table", "selector": "#orders", "structure": OUTLINE})
    assert to_candidate(element).structure["rows"] == 401


def test_an_element_that_is_not_a_container_carries_no_shape():
    """`null` from the capture means "not one of those", and must not read as an empty table."""
    assert CapturedElement.from_dict({"tag": "button", "structure": None}).structure == {}
    assert to_candidate(element(tag="button")).structure == {}


def test_the_judge_is_handed_the_shape_along_with_the_markup():
    from apps.a11y.dispatch import _group_by_screen

    requests = select([{"tag": "table", "selector": "#orders", "route": "/r",
                        "html": "<table>...</table>", "structure": OUTLINE}])
    element = _group_by_screen(requests)[0]["elements"][0]
    assert element["structure"]["header_cells"] == 0
    assert element["checker"] == "structure"


def test_a_table_that_grew_is_not_answered_from_the_old_verdict():
    """The reason the shape is part of the cache key, and it is not hypothetical.

    A container's markup is bounded, so a table can gain three hundred rows while the first
    eight thousand characters stay identical. Keyed on markup alone, that table keeps its old
    answer for ever — the cache answering about a page that no longer exists.
    """
    from apps.a11y.dispatch import content_hash

    markup = "<table id=orders><tr><td>Title</td></tr>"      # identical either side
    small = to_candidate(CapturedElement.from_dict(
        {"tag": "table", "html": markup, "structure": {**OUTLINE, "rows": 3}}))
    grown = to_candidate(CapturedElement.from_dict(
        {"tag": "table", "html": markup, "structure": {**OUTLINE, "rows": 401}}))

    assert small.html == grown.html
    assert content_hash("structure", small) != content_hash("structure", grown)


def test_the_same_page_twice_produces_the_same_key():
    """A run that cannot be reproduced cannot be compared against the golden set, and a key
    that moved on its own would re-judge every element of every unchanged page."""
    from apps.a11y.dispatch import content_hash

    def built():
        return to_candidate(CapturedElement.from_dict(
            {"tag": "table", "html": "<table></table>",
             "structure": {"columns": 2, "rows": 9, "kind": "table"}}))

    assert content_hash("structure", built()) == content_hash("structure", built())


def test_a_container_the_capture_could_not_describe_says_so_rather_than_going_quiet():
    """"We could not look" and "there is no structure here" are different answers, and an
    absent outline would collapse them into one."""
    unreadable = CapturedElement.from_dict(
        {"tag": "table", "structure": {"kind": "unreadable", "reason": "detached node"}})
    assert to_candidate(unreadable).structure["kind"] == "unreadable"


def test_the_agent_is_taught_to_read_the_shape_before_the_markup():
    body = AGENT_BODY.read_text(encoding="utf-8")
    assert "`structure`" in body
    assert "unreadable" in body


# ── markup the judge was only shown part of ──────────────────────────
def test_a_truncated_container_travels_to_the_judge_saying_so():
    """A judge shown the first part of a long table and not told so would answer about the
    whole of it. Silently — which is the shape of every other silence found this week."""
    cut = element(tag="table", selector="#big", html="<table id=big><tr><td>a</td></tr>")
    cut = CapturedElement(**{**cut.__dict__, "markup_truncated": True})
    assert to_candidate(cut).markup_truncated is True


def test_markup_that_fitted_is_never_reported_as_truncated():
    """Never inferred from length: a container that happens to sit exactly at the limit is not
    truncated, and guessing would make the judge hedge on a complete answer."""
    assert to_candidate(element(tag="table", html="<table></table>")).markup_truncated is False


def test_the_capture_reports_truncation_rather_than_the_platform_guessing_at_it():
    assert CapturedElement.from_dict({"tag": "table", "markup_truncated": True}).markup_truncated
    assert not CapturedElement.from_dict({"tag": "table"}).markup_truncated


def test_the_agent_is_told_what_to_do_with_markup_it_only_half_received():
    body = AGENT_BODY.read_text(encoding="utf-8")
    assert "markup_truncated" in body
    assert "uncertain" in body.lower()


# ── selecting a whole page ───────────────────────────────────────────
def test_one_element_can_be_selected_by_more_than_one_check():
    """A fake button styled only in colour is two different questions with two answers."""
    both = _coloured(tag="div", role="button", text="Overdue")
    assert checkers_for(both) == ("semantics", "color")


def test_selection_is_stable_and_in_page_then_checker_order():
    """A run that is not reproducible cannot be compared against the golden set (QA-09)."""
    page = [
        element(tag="img", attrs={"alt": "chart"}, selector="img.a"),
        _coloured(tag="div", role="button", text="Overdue", selector="div.b"),
    ]
    once = [(r.checker, r.candidate.selector) for r in select(page)]
    # The image is queued twice, and that is the design rather than a duplicate: `alt` asks
    # whether it SAYS what it means (1.1.1), `graphics` asks whether it can be SEEN (1.4.11).
    # An icon passes one and fails the other routinely.
    #
    # The order is not incidental either: within one element it follows `CHECKERS` order, so a
    # second run over the same page produces the same batch and the result stays comparable
    # against the golden set.
    assert once == [
        ("alt", "img.a"), ("graphics", "img.a"),
        ("semantics", "div.b"), ("color", "div.b"),
    ]
    assert once == [(r.checker, r.candidate.selector) for r in select(page)]


def test_selection_accepts_the_companion_json_as_well_as_objects():
    raw = [{"tag": "img", "attrs": {"alt": "chart"}, "selector": "img.a", "route": "/home"}]
    assert [r.checker for r in select(raw)] == ["alt", "graphics"]


def test_an_unknown_capture_field_never_breaks_selection():
    """The capture format will grow — an accessibility-tree node, axe's own result — and a new
    key arriving must not stop a page being judged."""
    el = CapturedElement.from_dict(
        {"tag": "img", "attrs": {"alt": "x"}, "axe_result": {"id": "image-alt"}})
    assert "alt" in checkers_for(el)


def test_a_capture_that_omits_rendered_is_treated_as_rendered():
    """The safe direction: a forgotten field must not silently make a whole page invisible."""
    assert CapturedElement.from_dict({"tag": "img"}).rendered is True


def test_the_candidate_carries_pointers_not_bodies():
    """#1/#3: the screenshot travels as an object-store key, never as image bytes."""
    candidate = to_candidate(element(
        tag="img", selector="img.hero", html="<img src='h.png'>",
        screenshot_ref="s3://shots/hero.png", context="hero banner", route="/home"))
    assert isinstance(candidate, A11yCandidate)
    assert candidate.screenshot_ref == "s3://shots/hero.png"
    assert candidate.selector == "img.hero" and candidate.route == "/home"


def test_why_an_element_was_never_judged_is_a_question_with_an_answer():
    reasons = explain(element(tag="button", text="Buy now", accessible_name="Purchase"))
    assert set(reasons) == set(CHECKERS)
    assert reasons["label"] is True and reasons["alt"] is False


def test_the_rules_import_and_run_with_no_django_settings():
    """D-A11Y-6: the companion imports this same module on the developer's machine, where
    there is no configured Django. Proven by importing it in a subprocess with the settings
    variable removed rather than by reading the imports and hoping — a Django import added
    anywhere in this package's chain would break capture on every machine at once, and it
    would not show up in a test suite that always has settings loaded.
    """
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "DJANGO_SETTINGS_MODULE"}
    backend = Path(__file__).resolve().parents[1]
    proof = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.');"
         "from apps.a11y.checkers import select;"
         "print(len(select([{'tag': 'img', 'attrs': {'alt': 'x'}}])))"],
        cwd=backend, env=env, capture_output=True, text=True,
    )
    assert proof.returncode == 0, proof.stderr
    # Two, not one: an <img> is queued for `alt` and for `graphics`. The number is incidental —
    # what this proves is that the rules ran at all with no Django on the path.
    assert proof.stdout.strip() == "2"


# ── what a complete answer has to contain (D-A11Y-5) ─────────────────
def test_an_alt_failure_must_propose_the_replacement_text():
    with pytest.raises(AnswerIncomplete, match="replacement alt text"):
        verify_answer(checker="alt", verdict="fail",
                      evidence="alt is 'IMG_1234', a filename", suggested_fix="")


def test_an_alt_failure_that_proposes_text_is_accepted():
    verify_answer(checker="alt", verdict="fail", evidence="alt is 'IMG_1234', a filename",
                  suggested_fix="Revenue grew from £1.2m to £3.4m across 2025")


def test_a_colour_failure_must_name_the_missing_second_cue():
    with pytest.raises(AnswerIncomplete, match="second cue"):
        verify_answer(checker="color", verdict="fail",
                      evidence="status shown only as a green dot", suggested_fix="")


def test_a_label_failure_must_quote_both_strings():
    with pytest.raises(AnswerIncomplete, match="BOTH strings"):
        verify_answer(checker="label", verdict="fail",
                      evidence="the accessible name is 'Purchase'")


def test_a_label_failure_quoting_both_strings_is_accepted():
    verify_answer(checker="label", verdict="fail",
                  evidence="visible label \"Buy now\", accessible name \"Purchase\"")


def test_a_semantics_failure_needs_nothing_beyond_the_universal_rules():
    """Deliberate, not an omission: which criteria broke is already enforced by the criteria
    check, and evidence is already required for every failure. A third rule would be ceremony
    that costs the judge a round trip."""
    assert requirements_for("semantics") is None
    verify_answer(checker="semantics", verdict="fail",
                  evidence="<div onclick='buy()'>Buy</div> — no role, not focusable")


@pytest.mark.parametrize("verdict", ["pass", "uncertain"])
@pytest.mark.parametrize("checker", CHECKERS)
def test_only_failures_are_held_to_these_requirements(checker, verdict):
    """An `uncertain` is the judge saying it could not see enough to answer. Demanding a fix
    from it would strand the element on a requirement it just said it could not meet — the
    element must be free to fall through to human review."""
    verify_answer(checker=checker, verdict=verdict, evidence="no image was available")


def test_an_unknown_checker_has_no_extra_requirement():
    assert requirements_for("nonsense") is None
    verify_answer(checker="nonsense", verdict="fail", evidence="e")


# ── the agent body teaches what the tool enforces ────────────────────
def test_the_agent_body_states_every_requirement_the_tool_enforces():
    """A rule enforced at the tool but never taught in the body is a rejection the judge has
    no way to anticipate — it learns it one wasted round trip at a time."""
    body = AGENT_BODY.read_text(encoding="utf-8")
    for phrase in ("replacement alt text", "second cue", "both strings", "markup to add"):
        assert phrase in body.lower(), f"the agent body never mentions {phrase!r}"


def test_the_agent_body_covers_all_five_checks_and_their_criteria():
    body = AGENT_BODY.read_text(encoding="utf-8")
    for checker, criteria in A11Y_CHECKER_CRITERIA.items():
        assert f"`{checker}`" in body
        for criterion in criteria:
            assert criterion in body


def test_the_deepened_body_still_passes_the_reference_sweep():
    """Non-negotiable #11 §8: a migrated or authored agent naming a local file is a failed
    migration. Re-run here because QA-03 rewrote a third of this body."""
    body = AGENT_BODY.read_text(encoding="utf-8")
    for banned in ("tasks.md", "requirements.md", "docs/", "CLAUDE.md", ".claude/", "./"):
        assert banned not in body, f"the agent body names a local path: {banned!r}"


# ── the schema is enforced where the judge actually writes ───────────
@pytest.fixture
def judged(db):
    """A dispatched judgment run, one element per checker, as QA-02 would have created it."""
    from apps.a11y.dispatch import A11yRequest, _group_by_screen
    from apps.integrations.services import provision_builtin_capabilities
    from apps.projects.models import Project
    from apps.registry.catalog import seed_agent_specs
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from apps.tenancy.models import Tenant
    from apps.workitems.models import WorkItem

    tenant = Tenant.objects.create(name="Checker Co")
    proj = Project.objects.create(tenant=tenant, name="Storefront")
    seed_agent_specs(tenant)
    provision_builtin_capabilities(tenant)      # a11yai, as `create_tenant` does (D-A11Y-1)

    page = [
        element(tag="img", selector="img.hero", attrs={"alt": "IMG_1234.jpg"},
                html="<img src='hero.png' alt='IMG_1234.jpg'>",
                context="The only chart of 2025 revenue.", route="/home"),
        element(tag="div", selector="div.cta", interactive=True, text="Buy",
                html="<div class='cta' onclick='buy()'>Buy</div>", route="/home"),
        _coloured(tag="span", selector="span.status", text="Overdue", route="/home"),
        element(tag="button", selector="button#pay", text="Buy now",
                accessible_name="Purchase",
                html="<button aria-label='Purchase'>Buy now</button>", route="/home"),
        element(tag="table", selector="table#orders", text="Order Status 1041 Shipped",
                html="<table id='orders'><tr><td>Order</td><td>Status</td></tr>"
                     "<tr><td>1041</td><td>Shipped</td></tr></table>", route="/home"),
    ]
    requests: list[A11yRequest] = select(page)
    run = Run.objects.create(
        tenant=tenant, work_item=WorkItem.objects.create(
            tenant=tenant, project=proj, title="Judge a11y"),
        agent_spec=AgentSpec.objects.get(tenant=tenant, key="09c_a11y_judge"),
        engine="claude", model="claude-sonnet-4-6", prompt_version="v6-migrated",
        inputs={"a11y_batches": _group_by_screen(requests)},
    )
    return tenant, proj, run, requests


def handle_for(judged, checker: str) -> str:
    from apps.a11y import judge as judge_module

    tenant, _proj, run, _ = judged
    batch = judge_module.batch_for_run(tenant.id, run.id)
    for screen in batch["screens"]:
        for el in screen["elements"]:
            if el["checker"] == checker:
                return el["id"]
    raise AssertionError(f"no {checker} element in the batch")


def file_finding(judged, checker: str, **kwargs):
    from apps.a11y import judge as judge_module

    tenant, proj, run, _ = judged
    criteria = kwargs.pop("criteria", None) or list(A11Y_CHECKER_CRITERIA[checker])
    payload = {"verdict": "fail", "confidence": 0.9, "evidence": "e", "suggested_fix": ""}
    payload.update(kwargs)
    return judge_module.record_finding(
        tenant_id=tenant.id, project_id=proj.id, run_id=run.id,
        element_id=handle_for(judged, checker), criteria=criteria, **payload,
    )


def test_the_page_produced_one_candidate_per_checker(judged):
    _tenant, _proj, _run, requests = judged
    assert sorted({r.checker for r in requests}) == sorted(CHECKERS)


# AC1 — a meaningless alt fails 1.1.1 with a reason and a suggested alt
def test_a_meaningless_alt_is_recorded_as_a_failure_with_a_proposed_alternative(judged):
    result = file_finding(
        judged, "alt",
        evidence="alt is 'IMG_1234.jpg', a filename — it says nothing about the chart",
        suggested_fix="Revenue grew from £1.2m to £3.4m across 2025",
    )
    assert result == {"element_id": handle_for(judged, "alt"), "checker": "alt",
                      "criteria": ["1.1.1"], "verdict": "fail", "recorded": True}


def test_an_alt_failure_with_no_proposed_alternative_is_refused_at_the_tool(judged):
    """The rejection is a ValueError, which the runner returns as a correctable 400 — so the
    judge is told what to add rather than concluding the platform is broken."""
    with pytest.raises(ValueError, match="replacement alt text"):
        file_finding(judged, "alt", evidence="alt is 'IMG_1234.jpg', a filename")


def test_nothing_is_stored_when_the_answer_is_refused(judged):
    from apps.a11y.models import A11yJudgmentCache

    with pytest.raises(ValueError):
        file_finding(judged, "alt", evidence="alt is a filename")
    assert not A11yJudgmentCache.objects.filter(checker="alt").exists()


# AC2 — a div acting as a button fails 1.3.1 / 4.1.2, naming that element
def test_a_div_acting_as_a_button_fails_both_of_its_criteria(judged):
    result = file_finding(
        judged, "semantics", criteria=["1.3.1", "4.1.2"],
        evidence="<div class='cta' onclick='buy()'>Buy</div> — no role, not focusable, "
                 "nothing announces it as a control",
        suggested_fix="use a <button>, or add role=button, tabindex=0 and key handling",
    )
    assert result["criteria"] == ["1.3.1", "4.1.2"]
    assert result["element_id"] == handle_for(judged, "semantics")


def test_a_real_button_with_no_name_may_be_recorded_against_4_1_2_alone(judged):
    """D-A11Y-2 in the other direction: naming both when only one broke would put a breach in
    the conformance report that was never found."""
    result = file_finding(
        judged, "semantics", criteria=["4.1.2"],
        evidence="the control is a real <button> but has no accessible name",
        suggested_fix="give it a visible text label",
    )
    assert result["criteria"] == ["4.1.2"]


# AC3 — a visible label that differs from the accessible name fails 2.5.3
def test_a_label_mismatch_is_recorded_as_a_failure_on_2_5_3(judged):
    result = file_finding(
        judged, "label",
        evidence="visible label \"Buy now\", accessible name \"Purchase\" — a voice-control "
                 "user saying 'click Buy now' cannot reach it",
        suggested_fix="change aria-label to 'Buy now'",
    )
    assert result["criteria"] == ["2.5.3"] and result["verdict"] == "fail"


def test_a_label_failure_naming_only_one_string_is_refused_at_the_tool(judged):
    with pytest.raises(ValueError, match="BOTH strings"):
        file_finding(judged, "label", evidence="the accessible name is wrong")


# AC4 — an uncertain verdict is never stranded on a fail's requirements
@pytest.mark.parametrize("checker", CHECKERS)
def test_an_uncertain_verdict_is_recorded_without_a_fix(judged, checker):
    result = file_finding(
        judged, checker, verdict="uncertain", confidence=0.0,
        evidence="no image of this element was available, so it could not be seen",
    )
    assert result["verdict"] == "uncertain" and result["recorded"] is True


# ── D-A11Y-4: the capability answers from what has been judged ───────
def test_the_capability_returns_the_stored_verdict_for_an_element(judged):
    from integrations.registry import get_capability

    tenant, proj, _run, requests = judged
    file_finding(judged, "alt",
                 evidence="alt is 'IMG_1234.jpg', a filename",
                 suggested_fix="Revenue grew from £1.2m to £3.4m across 2025")

    candidate = next(r.candidate for r in requests if r.checker == "alt")
    judgment = get_capability(tenant.id, "a11yai").check_alt(
        candidate=candidate, project_id=proj.id)

    assert judgment.verdict == "fail"
    assert judgment.criteria == ("1.1.1",)
    assert judgment.suggested_fix.startswith("Revenue grew")


def test_the_capability_says_not_judged_yet_rather_than_inventing_a_pass(judged):
    """An unjudged element must never come back as a pass — downstream that reads as "no
    problem here", which is the one wrong answer an accessibility check can give."""
    from integrations.a11yai.builtin import NOT_JUDGED_YET
    from integrations.registry import get_capability

    tenant, proj, _run, requests = judged
    candidate = next(r.candidate for r in requests if r.checker == "label")
    judgment = get_capability(tenant.id, "a11yai").check_label(
        candidate=candidate, project_id=proj.id)

    assert judgment.verdict == "uncertain"
    assert judgment.evidence == NOT_JUDGED_YET


def test_a_stored_verdict_is_never_visible_to_another_tenant(judged):
    """The lookup may search across a tenant's projects; it may never cross a tenant."""
    from apps.a11y.dispatch import stored_judgment
    from apps.tenancy.models import Tenant

    tenant, _proj, _run, requests = judged
    file_finding(judged, "alt", evidence="alt is a filename",
                 suggested_fix="Revenue grew from £1.2m to £3.4m across 2025")
    candidate = next(r.candidate for r in requests if r.checker == "alt")

    assert stored_judgment(tenant_id=tenant.id, checker="alt", candidate=candidate) is not None
    other = Tenant.objects.create(name="Someone Else")
    assert stored_judgment(tenant_id=other.id, checker="alt", candidate=candidate) is None
