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
    SELECTION_RULES,
    STYLE_KEYS,
    AnswerIncomplete,
    CapturedElement,
    checkers_for,
    describe_rules,
    explain,
    requirements_for,
    select,
    to_candidate,
    verify_answer,
)
from integrations.types import A11Y_CHECKER_CRITERIA, A11yCandidate

AGENT_BODY = Path(__file__).resolve().parents[2] / "agents" / "09c_a11y_judge" / "agent.md"


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


def test_the_poc_judges_five_criteria_and_no_others():
    """R7 / team decision D5: the POC ships 1.1.1, 1.3.1, 4.1.2, 1.4.1 and 2.5.3. 2.4.6 is
    Phase 2 — a rule quietly claiming it would put a Phase-2 criterion in a POC report."""
    covered = {c for rule in SELECTION_RULES for c in rule.criteria}
    assert covered == {"1.1.1", "1.3.1", "4.1.2", "1.4.1", "2.5.3"}


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
    {"styles": {"border-style": "solid"}},
    {"html": "<span><svg aria-hidden='true'/>Overdue</span>"},
    {"text": "Overdue *"},
])
def test_color_skips_anything_that_already_carries_a_second_visual_cue(second_cue):
    """1.4.1 is breached only when colour is the ONLY visual means. An underline, a border, an
    icon or a marker character is that second means, and the criterion is met."""
    assert "color" not in checkers_for(_coloured(**second_cue))


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
    assert once == [("alt", "img.a"), ("semantics", "div.b"), ("color", "div.b")]
    assert once == [(r.checker, r.candidate.selector) for r in select(page)]


def test_selection_accepts_the_companion_json_as_well_as_objects():
    raw = [{"tag": "img", "attrs": {"alt": "chart"}, "selector": "img.a", "route": "/home"}]
    assert [r.checker for r in select(raw)] == ["alt"]


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
    assert proof.stdout.strip() == "1"


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
    for phrase in ("replacement alt text", "second cue", "both strings"):
        assert phrase in body.lower(), f"the agent body never mentions {phrase!r}"


def test_the_agent_body_covers_all_four_checks_and_their_criteria():
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
