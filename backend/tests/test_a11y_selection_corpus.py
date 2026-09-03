"""The guard: does the check we built actually cover the criterion we say it covers?

**Why this file exists.** On 21 August the platform reported eleven pages as satisfying WCAG
1.3.1. It had looked at none of their tables. Nothing was broken: a check had been built to
answer one question well, the routing table recorded it against a criterion far broader than
that question, and **nothing anywhere ever compared the two**. It took a person reading a live
conformance statement to notice, and no test, report or type would ever have said a word.

That is not a bug you fix once. It is a hole in what the test suite can express — every other
test here asks *"does this rule do what it says?"*, and none asks *"does what it says amount to
the criterion it is filed under?"*. So this file asks the second question, in the only way it
can be asked mechanically: by holding the failures themselves.

**How it works.** Below is a corpus of real accessibility failures, each a shape that appears on
ordinary business software, and beside each the elements that are the same shape done
*correctly*. Three rules bind it:

  1. **Every criterion the checks claim must own at least one failing shape.** Register a
     criterion in `A11Y_CHECKER_CRITERIA` and forget to build selection for it, and there is no
     shape to add — which is precisely the failure of 21 August, and it now cannot pass.
  2. **Every failing shape must be selected by a check that claims its criterion.** A criterion
     with nothing that reaches it fails here rather than in a client's conformance statement.
  3. **Every criterion must also own at least one shape that must NOT be selected.** Without
     this, a rule that simply returned `True` would satisfy rule 2 for everything and this file
     would be a rubber stamp. The negatives come straight from the `skips` prose on each
     `SelectionRule`: this is that prose made executable.

**How to use it.** Add a row whenever a new failure shape is found in the wild — the same
ratchet as the secret scanner's false-positive corpus. A shape that ought to be caught and is
not belongs here **before** the fix, so the fix has something to prove itself against.

**What it cannot do**, stated so nobody reads more into a green run than is there: it proves a
criterion has *some* path to a check, not that the coverage is complete. A criterion could hold
one shape here and still miss ten others in the world. It converts an unbounded silence into a
list somebody can argue with, which is the most a test can do about this.
"""
from __future__ import annotations

import pytest

from apps.a11y.checkers import CHECKERS, STYLE_KEYS, CapturedElement, checkers_for
from integrations.types import A11Y_CHECKER_CRITERIA

#: Every criterion any of the checks claims to answer.
CLAIMED_CRITERIA = sorted({c for pair in A11Y_CHECKER_CRITERIA.values() for c in pair})


def el(**kwargs) -> CapturedElement:
    """A captured element with everything the rules read present and inert by default."""
    base = {
        "selector": "main > *", "tag": "div", "role": "", "attrs": {}, "text": "",
        "accessible_name": "", "interactive": False, "rendered": True,
        "styles": {key: "" for key in STYLE_KEYS},
        "parent_styles": {key: "" for key in STYLE_KEYS},
        "html": "", "context": "", "screenshot_ref": "", "route": "/page",
    }
    return CapturedElement(**{**base, **kwargs})


def coloured(**kwargs) -> CapturedElement:
    styles = {**{k: "" for k in STYLE_KEYS}, "color": "rgb(200, 0, 0)"}
    styles.update(kwargs.pop("styles", {}))
    return el(styles=styles,
              parent_styles={**{k: "" for k in STYLE_KEYS}, "color": "rgb(20, 20, 20)"},
              **kwargs)


#: (criterion, what this is, the element, must it be selected?)
#:
#: A `True` row is a real failure of that criterion that some check has to reach. A `False` row
#: is a documented skip — either the same shape done correctly, or a case another engine owns.
CORPUS: list[tuple[str, str, CapturedElement, bool]] = [

    # ══ 1.1.1 Non-text Content ═══════════════════════════════════════════════════════
    ("1.1.1", "an image whose alt is a filename",
     el(tag="img", attrs={"alt": "IMG_1234.jpg"}, html="<img alt='IMG_1234.jpg'>"), True),
    ("1.1.1", "an informative image left with an empty alt",
     el(tag="img", attrs={"alt": ""}, html="<img src='chart.png' alt=''>"), True),
    ("1.1.1", "an image hidden from assistive tech by an author's claim",
     el(tag="img", role="presentation", attrs={"alt": ""}, html="<img role=presentation>"), True),
    ("1.1.1", "an image map area",
     el(tag="area", attrs={"href": "/x"}, html="<area href=/x>"), True),
    ("1.1.1", "an image used as a submit button",
     el(tag="input", attrs={"type": "image", "src": "go.png"}, html="<input type=image>"), True),
    ("1.1.1", "an SVG exposed to assistive technology",
     el(tag="svg", attrs={"aria-label": "Sales trend"}, html="<svg aria-label='Sales trend'>"),
     True),
    ("1.1.1", "a <canvas> chart, whose content exists only as pixels",
     el(tag="canvas", html="<canvas id=revenue></canvas>"), True),
    ("1.1.1", "an icon drawn by a font at a Private Use codepoint",
     # Written as an escape, not as the character itself: U+E900 renders as an empty box
     # or as nothing at all in most editors, and a row nobody can see is a row somebody
     # deletes by accident.
     el(tag="span", text="\ue900",
        html="<span class=ico>\ue900</span>"), True),
    ("1.1.1", "an empty element whose class says an icon is drawn there",
     el(tag="span", attrs={"class": "icon-warning"}, html="<span class='icon-warning'></span>"),
     True),
    # — the same shapes, correctly —
    ("1.1.1", "a bare SVG with no role, no name and no <title>: never announced at all",
     el(tag="svg", html="<svg><path d='M0 0'/></svg>"), False),
    ("1.1.1", "an element that never rendered",
     el(tag="img", attrs={"alt": "x"}, rendered=False), False),
    ("1.1.1", "an <iframe> with no title — the rule scanner proves this one",
     el(tag="iframe", attrs={"src": "/v"}, html="<iframe src=/v></iframe>"), False),
    ("1.1.1", "an icon font using a real word as its ligature: poor, but announced",
     el(tag="i", attrs={"class": "material-icons"}, text="delete",
        html="<i class='material-icons'>delete</i>"), False),

    # ══ 1.3.1 Info and Relationships ═════════════════════════════════════════════════
    ("1.3.1", "a table whose header row is ordinary cells",
     el(tag="table", text="Subject Shelf",
        html="<table><tr><td>Subject</td><td>Shelf</td></tr>"
             "<tr><td>Botany</td><td>4B</td></tr></table>"), True),
    ("1.3.1", "a table with no header cells anywhere",
     el(tag="table", text="1041 Shipped", html="<table><tr><td>1041</td></tr></table>"), True),
    ("1.3.1", "a layout table announced as one — an author's claim, not a proven fact",
     el(tag="table", role="presentation", text="left right", html="<table></table>"), True),
    ("1.3.1", "a list of cards drawn from styled divs",
     el(tag="div", attrs={"class": "card-grid"}, text="one two three",
        html='<div class="card-grid"><div class="card">one</div>'
             '<div class="card">two</div><div class="card">three</div></div>'), True),
    ("1.3.1", "radio buttons in a form with nothing grouping them",
     el(tag="form", text="Delivery",
        html='<form><input type="radio" name="d"><input type="radio" name="d"></form>'), True),
    ("1.3.1", "a set of fields whose grouping element carries no name",
     el(tag="fieldset", text="Delivery", html="<fieldset><legend></legend></fieldset>"), True),
    ("1.3.1", "bold text standing in for a heading",
     el(tag="p", text="Opening hours",
        styles={**{k: "" for k in STYLE_KEYS}, "font-size": "22px", "font-weight": "700"},
        parent_styles={**{k: "" for k in STYLE_KEYS}, "font-size": "16px",
                       "font-weight": "400"}), True),
    # — the same shapes, correctly —
    ("1.3.1", "a two-panel layout: a pair is an arrangement, not a list",
     el(tag="div", attrs={"class": "split"}, text="left right",
        html='<div class="split"><div class="pane">left</div>'
             '<div class="pane">right</div></div>'), False),
    ("1.3.1", "a form whose radio buttons are already inside a named fieldset",
     el(tag="form", text="Delivery",
        html='<form><fieldset><legend>Delivery</legend>'
             '<input type="radio" name="d"></fieldset></form>'), False),
    ("1.3.1", "a form holding a single search box: not a set of related options",
     el(tag="form", text="Search", html='<form><input type="search" name="q"></form>'), False),
    ("1.3.1", "a container that never rendered",
     el(tag="table", rendered=False), False),

    # ══ 1.4.1 Use of Colour ══════════════════════════════════════════════════════════
    ("1.4.1", "a status carried by text colour alone",
     coloured(tag="span", text="Overdue"), True),
    ("1.4.1", "a filled indicator with no text at all",
     el(tag="span", attrs={"class": "dot"},
        styles={**{k: "" for k in STYLE_KEYS}, "background-color": "rgb(0, 160, 0)"},
        parent_styles={**{k: "" for k in STYLE_KEYS}, "background-color": "transparent"}), True),
    ("1.4.1", "a table row tinted to carry a status, with the status written nowhere",
     el(tag="tr", text="Tidewater 12 Aug",
        styles={**{k: "" for k in STYLE_KEYS}, "background-color": "rgb(255, 224, 224)"},
        parent_styles={**{k: "" for k in STYLE_KEYS},
                       "background-color": "rgb(255, 255, 255)"}), True),
    # — the same shapes, correctly —
    ("1.4.1", "the same colour, with an underline as a second visual cue",
     coloured(tag="a", attrs={"href": "/x"}, text="Overdue",
              styles={"text-decoration-line": "underline"}), False),
    ("1.4.1", "the same colour, with a marker character in the text itself",
     coloured(tag="span", text="Overdue *"), False),
    ("1.4.1", "a cell inheriting its row's tint: the row owns that question, asked once",
     el(tag="td", text="Tidewater",
        styles={**{k: "" for k in STYLE_KEYS}, "background-color": "rgba(0, 0, 0, 0)"},
        parent_styles={**{k: "" for k in STYLE_KEYS},
                       "background-color": "rgb(255, 224, 224)"}), False),

    # ══ 2.5.3 Label in Name ══════════════════════════════════════════════════════════
    ("2.5.3", "a button whose announced name shares nothing with its visible words",
     el(tag="button", text="Buy now", accessible_name="Purchase",
        html="<button aria-label='Purchase'>Buy now</button>"), True),
    ("2.5.3", "a submit button whose visible words live in its value attribute",
     el(tag="input", attrs={"type": "submit", "value": "Search", "aria-label": "Go"},
        accessible_name="Go", html="<input type=submit value=Search aria-label=Go>"), True),
    ("2.5.3", "a link whose announced name differs from its text",
     el(tag="a", attrs={"href": "/buy"}, text="Buy now", accessible_name="Purchase"), True),
    # — the same shapes, correctly —
    ("2.5.3", "a name that adds words after the visible label: the criterion is met",
     el(tag="button", text="Buy now", accessible_name="Buy now — opens in a new window"), False),
    ("2.5.3", "a control with no visible words: 2.5.3 does not reach it",
     el(tag="button", text="", accessible_name="Close"), False),
    ("2.5.3", "a control with no accessible name at all: that is 4.1.2's failure, not this one",
     el(tag="button", text="Buy now", accessible_name=""), False),
    ("2.5.3", "what a person typed into a text field is data, never that field's label",
     el(tag="input", attrs={"type": "text", "value": "Ada Lovelace"},
        accessible_name="Full name"), False),

    # ══ 4.1.2 Name, Role, Value ══════════════════════════════════════════════════════
    ("4.1.2", "a div wired up to behave like a button",
     el(tag="div", attrs={"class": "cta"}, interactive=True, text="Buy",
        html="<div class='cta' onclick='buy()'>Buy</div>"), True),
    ("4.1.2", "an element given a role that contradicts its tag",
     el(tag="button", role="link", text="Continue", html="<button role=link>Continue</button>"),
     True),
    ("4.1.2", "something put in the tab order without being a control",
     el(tag="span", attrs={"tabindex": "0"}, text="Open"), True),
    ("4.1.2", "an <a> with no href: not a link, whatever it looks like",
     el(tag="a", text="Next", html="<a>Next</a>"), True),
    # — the same shapes, correctly —
    ("4.1.2", "a native control with no overriding role: its semantics are already real",
     el(tag="button", text="Buy", accessible_name="Buy"), False),
    ("4.1.2", "a role that only restates the tag it sits on",
     el(tag="button", role="button", text="Buy", accessible_name="Buy"), False),
]


def _selected_by(element: CapturedElement) -> tuple[str, ...]:
    return checkers_for(element)


def _checkers_claiming(criterion: str) -> set[str]:
    return {checker for checker, criteria in A11Y_CHECKER_CRITERIA.items()
            if criterion in criteria}


# ══ rule 1: a claimed criterion must have a failure to answer for ════════════════════

@pytest.mark.parametrize("criterion", CLAIMED_CRITERIA)
def test_every_claimed_criterion_owns_at_least_one_real_failure(criterion):
    """Claim a criterion, build no selection for it, and there is nothing to put here.

    This is the 21 August failure, and it now cannot reach a client. 1.3.1 was claimed by a
    check that asked a narrower question; had this file existed, "a table whose header row is
    ordinary cells" would have had nowhere to go.
    """
    failures = [row for row in CORPUS if row[0] == criterion and row[3]]
    assert failures, (
        f"{criterion} is claimed in A11Y_CHECKER_CRITERIA but no failing shape is recorded "
        f"for it. Either a check does not really cover it, or the shape it covers has never "
        f"been written down. Both are how a criterion comes to be reported as checked when "
        f"nothing looked at it."
    )


# ══ rule 2: every recorded failure must reach a check that claims its criterion ══════

@pytest.mark.parametrize(
    "criterion,what,element",
    [(c, w, e) for c, w, e, expected in CORPUS if expected],
    ids=[f"{c}-{w[:44]}" for c, w, _e, expected in CORPUS if expected])
def test_every_recorded_failure_reaches_a_check_that_claims_its_criterion(
        criterion, what, element):
    selected = set(_selected_by(element))
    claiming = _checkers_claiming(criterion)
    assert selected & claiming, (
        f"{what!r} is a {criterion} failure and no check claiming {criterion} selects it.\n"
        f"  selected by: {sorted(selected) or 'nothing'}\n"
        f"  checks claiming {criterion}: {sorted(claiming)}\n"
        f"A page holding this would be reported as satisfying {criterion}."
    )


# ══ rule 3: and the same shape done correctly must be left alone ═════════════════════

@pytest.mark.parametrize(
    "criterion,what,element",
    [(c, w, e) for c, w, e, expected in CORPUS if not expected],
    ids=[f"{c}-{w[:44]}" for c, w, _e, expected in CORPUS if not expected])
def test_a_shape_that_is_already_correct_is_not_asked_about(criterion, what, element):
    """The half that stops this file becoming a rubber stamp.

    Without it, a rule that returned `True` for everything would satisfy rule 2 for every
    criterion at once, and a green run would mean nothing. These rows come from the `skips`
    prose on each `SelectionRule` — this is that prose made executable.
    """
    selected = set(_selected_by(element))
    claiming = _checkers_claiming(criterion)
    assert not (selected & claiming), (
        f"{what!r} should not be a {criterion} question, and "
        f"{sorted(selected & claiming)} selected it. Either the rule has widened past what it "
        f"documents, or this row is wrong and the corpus should say so."
    )


@pytest.mark.parametrize("criterion", CLAIMED_CRITERIA)
def test_every_claimed_criterion_also_records_something_it_must_leave_alone(criterion):
    """A criterion with only positive rows can be satisfied by a rule that claims everything."""
    assert [row for row in CORPUS if row[0] == criterion and not row[3]], (
        f"{criterion} records failures but nothing it must leave alone, so a rule that "
        f"selected every element would pass for it. Add the same shape done correctly."
    )


# ══ and the corpus itself has to stay honest ═════════════════════════════════════════

def test_the_corpus_covers_every_checker_that_exists():
    """A checker nothing exercises could stop selecting entirely and no test would notice."""
    exercised = {checker
                 for _c, _w, element, expected in CORPUS if expected
                 for checker in _selected_by(element)}
    assert set(CHECKERS) <= exercised, (
        f"no failing shape in the corpus reaches {sorted(set(CHECKERS) - exercised)}"
    )


def test_no_two_rows_describe_the_same_thing():
    descriptions = [(criterion, what) for criterion, what, _e, _x in CORPUS]
    assert len(descriptions) == len(set(descriptions))
