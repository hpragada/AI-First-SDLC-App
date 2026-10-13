"""Candidate selection — which elements each element checker applies to (QA-03).

Every rule here is a decision that an element **will** or **will not** be judged, and the
second half of that is the dangerous one: a skip rule is a promise that nothing this checker
looks for could ever be wrong with that element. So each skip below is justified from the
criterion's own wording rather than from "probably fine", and each has its own test.

**The two skips that were considered and deliberately NOT made**, because they would have
removed the very failures the checker exists to catch:

  * `alt=""` on an image. An empty alt is the correct way to mark decoration — and it is also
    exactly how an *informative* image gets hidden from a screen-reader user by accident. The
    task text names both directions ("a decorative image wrongly given alt, or an informative
    one left empty"), so an empty alt is a candidate, not an exemption.
  * `role="presentation"` / `role="none"` on an image, for the same reason: it is an author's
    claim that the image carries no information, and whether that claim is true is the whole
    question 1.1.1 asks.

An element the rules do not select is invisible to the AI pass for that criterion. It is not
invisible to the rule scanner, and it is not invisible to a human reviewer — but nothing here
may rely on that.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from integrations.types import A11Y_CHECKER_CRITERIA, A11Y_PASS, A11yCandidate

#: The element checkers, in the order a page's requests are emitted. Fixed so that two runs over
#: the same page produce the same batch in the same order — a judgment run that is not
#: reproducible cannot be compared against the golden set (QA-09).
#:
#: `structure` sits beside `semantics` because they are the two halves of one criterion: one
#: asks whether an element is pretending to be something, the other whether a container's
#: visible arrangement exists in the markup at all.
#:
#: `graphics` (QA-25) is the second half of a criterion in the same way, and its other half is
#: not a checker at all — it is `apps.a11y.page_rules`, which measures the controls while this
#: judges the pictures. 1.4.11 is covered by both together and by neither alone: correction R14
#: settled that on 27 August, and `ownership.ENGINEERING_OVERRIDES` carries it into routing.
#:
#: It sat in `HELD_BACK_SELECTION_RULES` for part of 1 September while that last step was taken.
#: Nothing about the check was wrong; what was missing was the registry agreeing with it.
CHECKERS: tuple[str, ...] = ("alt", "semantics", "structure", "color", "label", "graphics")

#: The computed style properties the rules read. Named here because this is also the list the
#: companion has to capture (QA-11b): a property missing from the capture silently turns every
#: rule that reads it into "no". Keep the list short — each entry is a per-element cost in the
#: browser.
#:
#: `background-image` was added for `graphics` (QA-25) and is the only key here that earns its
#: place by what it makes VISIBLE rather than by what it measures: a `<span>` whose entire
#: content is a CSS background image is a graphic that no tag, role or attribute can identify,
#: and without this key it was invisible to every check the platform has.
STYLE_KEYS: tuple[str, ...] = (
    "color",
    "background-color",
    "text-decoration-line",
    "font-size",
    "font-weight",
    "border-style",
    # ...and the colour that border is painted in. `border-style` alone says a border EXISTS
    # and never what it looks like, so the third way to colour a thing was invisible — after
    # `background-color` (the first) and `stroke`/`fill` (the second, below). On /loans/renewals
    # three status markers sit in adjacent rows of one table: two carry their colour in
    # `background`, one in `border: 3px solid`. The two were offered to the colour rule and the
    # third was not, because `_applies_color` looked for a painted background, found none on an
    # empty span, and concluded there was no colour here to ask about.
    "border-color",
    "outline-color",
    "background-image",
    # A shape inside a chart is not coloured by `background-color` — it is drawn in `stroke` or
    # filled with `fill`, and neither was captured. So a line chart whose three series are told
    # apart by colour alone arrived with every colour it uses invisible to the one rule that
    # asks about colour. Read only for `SERIES_SHAPES`; see `_series_colour` for why.
    "stroke",
    "fill",
)

#: The SVG shapes that draw a data series. Their colour IS their identity — that is the whole
#: reason `a11y_audit.mjs` offers them — so unlike an icon they are never decorative.
#:
#: **Read for these tags and no others, deliberately.** `fill` computes to opaque black on any
#: SVG element that never set it, so treating a painted `fill` as meaningful in general would
#: make every icon on every page a colour candidate and spend the run's judgment budget on
#: decoration. Restricting it to the two shapes offered for exactly this reason keeps the fix
#: the size of the bug.
SERIES_SHAPES = frozenset({"polyline", "polygon"})

#: Elements that are already controls. Their semantics are real, so `semantics` skips them
#: unless something overrides those semantics (an explicit contradictory `role`, or an `<a>`
#: with no `href`, which is not a link at all).
NATIVE_CONTROL_TAGS = frozenset({
    "a", "button", "input", "select", "textarea", "summary", "option", "details",
})

HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

#: Containers whose whole point is to carry a structure, so "is that structure real?" is always
#: a fair question to ask about one. The unit of work for `structure` is the container and not
#: the element inside it, because the question cannot be answered from a cell: whether a table
#: has headers is a fact about the table.
STRUCTURE_TAGS = frozenset({"table", "ul", "ol", "dl", "fieldset"})

#: How many in-page links sitting side by side in one container make it read as a set of
#: controls rather than as prose with anchors in it. Same number and same reasoning as
#: `REPEATED_CHILD_MINIMUM`: two of anything is a pair.
IN_PAGE_LINK_MINIMUM = 3

#: How many identically-classed children make a run of `div`s read as a list to the eye. Three
#: rather than two because two of anything is a pair, and a two-panel layout is far more often
#: a layout than a list. Named so the team can raise it if it turns out to cost more judgments
#: than it earns — which is a measurement now, not a guess (`evaluation/scorer/`).
REPEATED_CHILD_MINIMUM = 3

#: ARIA roles that make something a user interface component — the scope of 2.5.3 Label in
#: Name, and what `semantics` is asking about when it asks "is this really a control?".
CONTROL_ROLES = frozenset({
    "button", "link", "checkbox", "radio", "switch", "menuitem", "menuitemcheckbox",
    "menuitemradio", "tab", "option", "combobox", "slider", "spinbutton", "textbox",
    "searchbox", "treeitem",
})

#: The role a tag already has without anyone writing it down. Used only to tell a *redundant*
#: `role` (nothing to judge) from one that overrides the element's real semantics (very much
#: something to judge — `<button role="link">` is a control that announces itself as a link).
#: Deliberately partial: an unknown tag with an explicit role is selected, which is the safe
#: direction to be wrong in.
IMPLICIT_ROLES: dict[str, str] = {
    "article": "article", "aside": "complementary", "button": "button", "footer": "contentinfo",
    "form": "form", "header": "banner", "img": "img", "li": "listitem", "main": "main",
    "nav": "navigation", "ol": "list", "section": "region", "select": "combobox",
    "table": "table", "textarea": "textbox", "ul": "list",
    **{tag: "heading" for tag in HEADING_TAGS},
}

#: Text this large and this heavy, sitting above its surroundings, is what a sighted reader
#: takes for a heading. Below it, a "heading that is only bold text" is indistinguishable from
#: ordinary emphasis and selecting it would cost a judgment on every bold lead paragraph.
HEADING_MIN_PX = 18.0
HEADING_MIN_WEIGHT = 600.0

#: The Unicode Private Use Area. A font may put anything it likes at these codepoints, and an
#: icon font is exactly what does: the character has no meaning of its own, and what a sighted
#: person sees is a picture. So a single Private Use character IS non-text content presented to
#: the user — not a heuristic, a fact about what the codepoint means.
PRIVATE_USE_FIRST, PRIVATE_USE_LAST = 0xE000, 0xF8FF

#: How icon fonts name themselves in a class attribute. Only consulted for an element with **no
#: text and no image inside it** — something is being drawn there, and nothing in the markup
#: says what. A wrapper that turns out to be empty decoration comes back `pass`, which costs one
#: judgment and is the right direction to be wrong in.
ICON_CLASS_MARKERS = ("icon", "fa-", "glyphicon", "material-icons", "bi-", "ico-")

#: Conventional non-colour markers. A required field flagged with a red asterisk carries a
#: second cue in the text itself, so colour is not the *only* visual means and 1.4.1 is met.
TEXT_CUE_MARKERS = ("*", "✓", "✗", "×", "!", "⚠")

#: Input types whose `value` attribute IS the control's visible label, because HTML renders it
#: as the button's face. For every other type `value` holds what the user typed — that is data,
#: not a label, and reading it as one would compare a person's own name against a field's
#: accessible name and call the difference a defect.
VALUE_LABEL_INPUT_TYPES = frozenset({"submit", "reset", "button"})

#: Controls whose inner text is their CONTENT, not their label — the mirror image of
#: `VALUE_LABEL_INPUT_TYPES` (1 Sep). A `<select>`'s inner text is every one of its options; a
#: `<textarea>`'s is whatever is typed into it. Neither is "the words a sighted user reads on
#: the control", which is what 2.5.3 compares the announced name against, and a closed dropdown
#: does not display its options at all.
#:
#: Read as a label, this sent all 13 dropdowns in the 31 August Meridian audit to the AI: the
#: rule compared the announced name "Home branch" against the option list
#: "Fenner Road Ashcombe North Quay", found no match and reported a possible mismatch. There
#: was never anything to compare — a dropdown is named by its `<label for=…>`, so its visible
#: label IS its accessible name and 2.5.3 has no two strings to hold against each other. Out of
#: scope, exactly as `<input type="submit">` with no `value` is out of scope above, and for the
#: same reason: no visible label we can read means no comparison we can make.
VALUE_NOT_LABEL_TAGS = frozenset({"select", "textarea"})

_WHITESPACE = re.compile(r"\s+")
_CLASS_ATTR = re.compile(r'class="([^"]*)"')
_IN_PAGE_HREF = re.compile(r'<a[^>]+href="#[^"]*"', re.IGNORECASE)
#: A grouping the markup already carries, so a set of related fields is not ungrouped.
_GROUPING = re.compile(r'<fieldset|role="(?:group|radiogroup)"', re.IGNORECASE)
#: Fields that only mean anything as a set — one radio button on its own answers nothing.
_GROUPED_INPUT = re.compile(r'<input[^>]*type="(?:radio|checkbox)"', re.IGNORECASE)
_PX = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*px\s*$", re.IGNORECASE)
_NAMED_WEIGHTS = {"normal": 400.0, "bold": 700.0, "bolder": 700.0, "lighter": 100.0}
#: Colours that paint nothing, so "this element has a background colour" is false for them.
_NO_PAINT = frozenset({"", "transparent", "rgba(0, 0, 0, 0)", "rgba(0,0,0,0)", "none"})


@dataclass(frozen=True)
class CapturedElement:
    """One element as the companion captured it from a rendered page.

    **This shape is the contract QA-11b has to produce.** It is deliberately the smallest set
    of facts the rules below actually read — every field is a per-element cost in the browser,
    and a field nothing reads is a field that will quietly stop being captured correctly.

    `html`, `context`, `screenshot_ref`, `selector`, `route`, `markup_truncated` and
    `structure` are not read by any rule; they are carried through onto the `A11yCandidate`
    the judge receives.
    (`html` is the one exception: `structure` reads it, because whether a form already groups
    its fields is a fact about the markup and nothing else.)
    """

    selector: str = ""
    tag: str = ""                                   # lowercased tag name
    role: str = ""                                  # explicit role attribute, lowercased
    attrs: Mapping[str, str] = field(default_factory=dict)   # lowercased attribute names
    text: str = ""                                  # the text a sighted user sees
    accessible_name: str = ""                       # the name assistive tech announces
    interactive: bool = False                       # a click/key handler is bound to it
    rendered: bool = True                           # has a box: not display:none, not zero-size
    styles: Mapping[str, str] = field(default_factory=dict)          # see STYLE_KEYS
    parent_styles: Mapping[str, str] = field(default_factory=dict)   # same keys, on the parent
    #: What the element sits inside: {tag, role, href, text}. Carried for the judge, not read
    #: by any rule — an icon-only control's parent has no text, and "what is it inside" is the
    #: question 1.1.1 and 1.4.11 both actually turn on.
    parent: Mapping[str, str] = field(default_factory=dict)
    html: str = ""
    #: True when `html` is a fragment because the element's markup was longer than the capture
    #: sends. Never inferred from the length of what arrived — a container that happens to be
    #: exactly at the limit is not truncated, and guessing would make the judge hedge on a
    #: complete answer.
    markup_truncated: bool = False
    #: The container's shape, when it is a container: how many rows and columns, which cells
    #: are headers, whether a group of fields is grouped and what names it. Empty for
    #: everything else.
    #:
    #: **This is what makes the container checks work at any size.** Markup is bounded, and a
    #: five-column table row costs about 190 characters, so the bound holds roughly forty rows
    #: — past that the judge was being handed the top of a table and answering as though it
    #: were the whole of it. An outline is bounded by how WIDE a table is rather than how long,
    #: so ten rows and ten thousand cost the same. Measured on a 401-row table: 31,985
    #: characters of markup, 906 of outline, and nothing about the shape lost.
    structure: Mapping = field(default_factory=dict)
    context: str = ""
    screenshot_ref: str = ""
    route: str = ""

    @classmethod
    def from_dict(cls, raw: Mapping) -> CapturedElement:
        """Build from the companion's JSON, ignoring anything we do not read.

        Tolerant on purpose: the capture format will grow (an accessibility-tree node, axe's
        own result for the element), and a new key arriving must never break selection.
        """
        attrs = {str(k).lower(): str(v) for k, v in dict(raw.get("attrs") or {}).items()}
        return cls(
            selector=str(raw.get("selector") or ""),
            tag=str(raw.get("tag") or "").strip().lower(),
            role=str(raw.get("role") or attrs.get("role") or "").strip().lower(),
            attrs=attrs,
            text=str(raw.get("text") or ""),
            accessible_name=str(raw.get("accessible_name") or ""),
            interactive=bool(raw.get("interactive")),
            # Absent means rendered: a capture that forgot the field must not silently make
            # every element invisible to every checker.
            rendered=bool(raw.get("rendered", True)),
            styles={str(k).lower(): str(v) for k, v in dict(raw.get("styles") or {}).items()},
            parent_styles={
                str(k).lower(): str(v)
                for k, v in dict(raw.get("parent_styles") or {}).items()
            },
            html=str(raw.get("html") or ""),
            markup_truncated=bool(raw.get("markup_truncated")),
            # `null` for a non-container is the capture saying "not one of those", which is
            # not the same as a container it could not read — that arrives as
            # `{"kind": "unreadable", ...}` and reaches the judge as such.
            structure=dict(raw.get("structure") or {}),
            context=str(raw.get("context") or ""),
            parent={str(k): str(v) for k, v in dict(raw.get("parent") or {}).items()},
            screenshot_ref=str(raw.get("screenshot_ref") or ""),
            route=str(raw.get("route") or ""),
        )


# ── small readers over the captured facts ──────────────────────────────────────────

def _normalise(text: str) -> str:
    """Lowercased, whitespace-collapsed — how two labels are compared for "the same words"."""
    return _WHITESPACE.sub(" ", str(text or "")).strip().lower()


def _label_words(text: str) -> str:
    """A label reduced to its words, with punctuation acting as a separator rather than a
    character.

    **This is how 2.5.3 is actually compared**, by the criterion's own ACT rule and by axe, and
    the difference is not cosmetic. Comparing raw characters says the visible label "Search" is
    contained in the accessible name "Research tools" — because the letters of *search* sit
    inside *research* — so the rule concluded the criterion was already met and never asked
    anybody. A speech-input user saying "Search" activates nothing.

    Unicode-aware on purpose: `str.isalnum()` keeps accented and non-Latin letters, where a
    naive `[a-z0-9]` filter would shred every label in a language other than English and make
    every control on the page look like a mismatch.
    """
    lowered = _normalise(text)
    return " ".join("".join(c if c.isalnum() else " " for c in lowered).split())


def _name_contains_label(name: str, visible: str) -> bool:
    """Does the accessible name contain the visible label as a run of whole words?"""
    words, target = _label_words(name), _label_words(visible)
    if not target:
        return True         # nothing textual on the control, so nothing to contain
    return f" {target} " in f" {words} "


def _px(value: str) -> float:
    """A CSS px length as a number, or 0.0 for anything else (em, %, unset)."""
    match = _PX.match(str(value or ""))
    return float(match.group(1)) if match else 0.0


def _weight(value: str) -> float:
    raw = str(value or "").strip().lower()
    if raw in _NAMED_WEIGHTS:
        return _NAMED_WEIGHTS[raw]
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _paints(colour: str) -> bool:
    return str(colour or "").strip().lower() not in _NO_PAINT


#: Border styles that draw nothing, so their colour paints nothing either.
_NO_BORDER = frozenset({"", "none", "hidden"})


def _paints_border(element: CapturedElement) -> bool:
    """Is this element outlined in a colour you can actually see?

    Both halves are required and neither is enough alone. `border-color` computes to the
    element's own `color` on anything that never set one, so a painted colour with
    `border-style: none` describes a border that is not drawn — reading that as colour would
    make every element on the page a colour candidate.
    """
    style = str(element.styles.get("border-style", "")).strip().lower()
    if style and all(part in _NO_BORDER for part in style.split()):
        return False
    if not style:
        return False
    return _paints(element.styles.get("border-color", ""))


def _has_nested_graphic(element: CapturedElement) -> bool:
    lowered = element.html.lower()
    return "<img" in lowered or "<svg" in lowered


def _visible_text(element: CapturedElement) -> str:
    """The words a sighted person reads on this control, normalised.

    Almost always the element's own text. The exception is `<input>`, which has **no inner
    text, ever** — a submit button's face is its `value` attribute. Reading only inner text put
    every submit and reset button in every form permanently out of scope for 2.5.3: the rule
    found no visible label, concluded from that silence that the criterion did not apply, and
    moved on. `<input type="submit" value="Search">` announced as "Go" is a textbook Label in
    Name failure, and it could not be reported.

    A submit button with no `value` at all is still out of scope, and that skip is deliberate:
    the browser draws its own default word, that word is chosen by the user agent and its
    language, and it is not in the markup for us to compare anything against.

    The opposite exception is `VALUE_NOT_LABEL_TAGS`, whose inner text is the control's content
    rather than its label. That one returns nothing at all: there is no visible label on the
    control to read, so there is no comparison to make.
    """
    if element.tag in VALUE_NOT_LABEL_TAGS:
        return ""
    text = _normalise(element.text)
    if text or element.tag != "input":
        return text
    if element.attrs.get("type", "").strip().lower() in VALUE_LABEL_INPUT_TYPES:
        return _normalise(element.attrs.get("value", ""))
    return ""


def _is_control(element: CapturedElement) -> bool:
    """A user interface component — the scope 2.5.3 is written against."""
    if element.role:
        return element.role in CONTROL_ROLES
    if element.tag in {"button", "select", "textarea", "summary"}:
        return True
    if element.tag == "a":
        return bool(element.attrs.get("href"))
    if element.tag == "input":
        return element.attrs.get("type", "").strip().lower() not in {"hidden"}
    return False


def _role_is_redundant(element: CapturedElement) -> bool:
    """The role restates what the tag already means, so there is no mismatch to look for."""
    return bool(element.role) and IMPLICIT_ROLES.get(element.tag) == element.role


def _looks_like_heading(element: CapturedElement) -> bool:
    """Big, heavy text that stands above its surroundings — a heading to the eye."""
    if not element.text.strip():
        return False
    size = _px(element.styles.get("font-size", ""))
    return (
        size >= HEADING_MIN_PX
        and size > _px(element.parent_styles.get("font-size", ""))
        and _weight(element.styles.get("font-weight", "")) >= HEADING_MIN_WEIGHT
    )


def _series_colour(element: CapturedElement) -> tuple[str, str]:
    """The property and value a chart series is drawn in, or a pair of blanks.

    Blank for anything that is not a `SERIES_SHAPES` tag, which is what keeps `fill` from
    claiming every icon in the application — see the note on that constant.
    """
    if element.tag not in SERIES_SHAPES:
        return "", ""
    for key in ("stroke", "fill"):
        value = str(element.styles.get(key, "") or "")
        if _paints(value):
            return key, value
    return "", ""


def _colour_differs_from_surroundings(element: CapturedElement) -> bool:
    """Something about this element's colour singles it out from what is around it."""
    styles, parent = element.styles, element.parent_styles
    if styles.get("color", "") and styles.get("color") != parent.get("color", ""):
        return True
    key, value = _series_colour(element)
    if key and value != str(parent.get(key, "") or ""):
        return True
    background = styles.get("background-color", "")
    if _paints(background) and background != parent.get("background-color", ""):
        return True
    # A border is the whole of the colour ONLY when there is nothing else — no text and no
    # background. Kept that narrow deliberately: `_has_second_cue` measured that comparing a
    # border against its parent's saves four candidates in three hundred, because parents
    # almost never have one, so treating any painted border as a difference would make every
    # bordered input and card on the page a colour candidate and spend the run's judgment
    # budget on chrome. An element with no text and no fill is the case where it is not chrome
    # — it is the only thing being drawn.
    if element.text.strip() or _paints(background):
        return False
    return (_paints_border(element)
            and styles.get("border-color", "") != parent.get("border-color", ""))


def _has_second_cue(element: CapturedElement) -> bool:
    """A visual cue other than colour is already present, so 1.4.1 is satisfied.

    Only *visual* cues count. An `aria-label` is not one: 1.4.1 is about what a person who
    cannot distinguish the colours can still see, not about what assistive tech is told.

    **A border is not on this list, and used to be.** The reasoning was that a border is a
    visual cue and is not colour, which is true in general and wrong in the case that matters
    most: a field marked invalid by turning its border red **already had a border**. Only its
    colour changed. The rule was reading the presence of the thing being coloured as proof that
    colour was not the only cue, and declining to look — so the commonest way on the web to mark
    a field invalid was skipped by the one check built to catch it, and nothing else covers it
    (1.4.1 has a single scanner rule and it is about links in prose).

    **Nothing narrower works, and that was measured rather than assumed.** Comparing the
    border's colour against the parent's saves four candidates out of three hundred, because
    parents almost never have a border to compare with; comparing it against the element's own
    text colour saves none. There is no way to tell a decorative border from a signalling one
    from what a single element carries, so the honest move is to stop pretending and let the
    judge decide. That is the same trade `_repeats_a_child_class` already makes and states: it
    costs a judgment on things that turn out to be fine, which is the direction worth being
    wrong in.
    """
    decoration = str(element.styles.get("text-decoration-line", "")).lower()
    if "underline" in decoration or "line-through" in decoration:
        return True
    if _has_nested_graphic(element):
        return True
    return any(marker in element.text for marker in TEXT_CUE_MARKERS)


# ── the rules themselves ───────────────────────────────────────────────────────────

def _is_icon_glyph(element: CapturedElement) -> bool:
    """A picture drawn by a font rather than by an image — still non-text content (1.1.1).

    Two ways to know, and the first is not a guess. A single character from the **Private Use
    Area** has no meaning of its own; what the user sees is whatever picture the font puts
    there. The second is the empty-element case: nothing to read, no image inside, and a class
    naming an icon family — something is being drawn and nothing says what.

    **Deliberately not selected:** an icon font using a *word* as its ligature
    (`<i class="material-icons">delete</i>`). Its text is a real word, so it is announced as
    "delete" — a poor alternative, but an alternative. Selecting it would put every such icon
    on every page into the queue to be told it is mediocre.
    """
    text = element.text.strip()
    if len(text) == 1 and PRIVATE_USE_FIRST <= ord(text) <= PRIVATE_USE_LAST:
        return True
    if text or _has_nested_graphic(element):
        return False
    classes = str(element.attrs.get("class", "")).lower()
    return any(marker in classes for marker in ICON_CLASS_MARKERS)


def _applies_alt(element: CapturedElement) -> bool:
    """Non-text content that is presented to the user — the scope of 1.1.1.

    **`<iframe>` is not here on purpose.** A frame with no title is `frame-title`, which the
    rule scanner proves deterministically; adding it would buy a second opinion on something
    already measured and cost a judgment on every embed.
    """
    if not element.rendered:
        return False
    if element.role == "img" or element.tag in {"img", "area"}:
        return True
    if element.tag == "canvas":
        # A drawing surface, and nothing inside it is reachable: whatever it renders — a chart,
        # a signature, a game — exists only as pixels. There is no rule anywhere that can say
        # whether its fallback content describes what was drawn, because answering needs
        # somebody to look at it. That is the whole shape of a question this check exists for.
        return True
    if _is_icon_glyph(element):
        return True
    if element.tag == "input":
        return element.attrs.get("type", "").strip().lower() == "image"
    if element.tag == "svg":
        # A bare <svg> with no role, no name and no <title> is not exposed as an image at all —
        # assistive technology never announces it, so 1.1.1 has nothing to judge. Give it any
        # one of those three and it becomes non-text content presented to the user.
        return bool(
            element.accessible_name.strip()
            or element.attrs.get("aria-label")
            or element.attrs.get("aria-labelledby")
            or "<title" in element.html.lower()
        )
    return False


def _has_background_graphic(element: CapturedElement) -> bool:
    """A picture painted by CSS rather than placed in the markup.

    `background-image` covers gradients too, and a gradient is not a graphic — it is decoration
    behind something else. `url(` is what separates a picture somebody chose from a colour ramp
    a stylesheet computed, and it is the only form that means an image file was loaded.
    """
    value = str(element.styles.get("background-image", "")).strip().lower()
    return bool(value) and value != "none" and "url(" in value


def _applies_graphics(element: CapturedElement) -> bool:
    """A graphic whose meaningful parts must be visible enough to make out — 1.4.11.

    **This is the half of 1.4.11 no rule can decide**, and its scope is drawn from what a person
    can SEE rather than from what assistive technology is told. That makes it deliberately wider
    than `_applies_alt` in the two places the difference matters:

      * **A bare `<svg>` with no role, no name and no `<title>` IS selected here.** `alt` skips
        it because it is never announced, so there is no text alternative to judge — but it is
        drawn on the screen, a sighted user reads meaning off it, and whether those parts are
        distinguishable is exactly this criterion's question. The two checks disagree about this
        element on purpose.
      * **A CSS background image is selected**, which no other check can see at all.

    **What is skipped, and it is the standard's own exception rather than ours.** 1.4.11 exempts
    graphics where "a particular presentation is essential to the information being conveyed" —
    a photograph is the textbook case, because you cannot restyle a photograph to have more
    contrast without destroying what it is a photograph of. A rule cannot tell a photograph from
    a diagram, so this does NOT try: every raster image is still selected, and the judge is told
    in as many words that "this is a photograph" is a complete and correct answer of *not
    applicable*. Deciding it here would be the platform pre-judging an image it never looked at,
    which is the same mistake `_applies_color` refuses to make about a missing screenshot.

    **The cost is understood and accepted.** Most images on a page are now judged twice, once for
    1.1.1 and once for 1.4.11. They are different questions with different answers — an accurate
    alt text on an invisible icon passes one and fails the other — and merging them to save a
    call would produce a single verdict that is wrong about one of the two criteria.
    """
    if not element.rendered:
        return False
    if element.tag in {"img", "svg", "canvas"} or element.role == "img":
        return True
    if element.tag == "input":
        return element.attrs.get("type", "").strip().lower() == "image"
    if _is_icon_glyph(element):
        return True
    return _has_background_graphic(element)


def _applies_semantics(element: CapturedElement) -> bool:
    """Structure or a control that may be drawn rather than real — 1.3.1 and 4.1.2."""
    if not element.rendered:
        return False
    if element.role and not _role_is_redundant(element):
        return True
    if element.tag == "a" and not element.attrs.get("href"):
        return True         # an <a> without href is not a link, whatever it looks like
    if element.tag == "a" and str(element.attrs.get("href", "")).startswith("#"):
        # **An in-page link does not navigate**, so "a real link with real semantics needs no
        # judgment" is not safely true of it. It may be a tab, a disclosure or a toggle wearing
        # an anchor, and the tab case is the one this was found on: three <a href="#panel-…">
        # styled as a tab strip, announced as links, with nothing saying which is selected.
        #
        # Narrow by measurement, not by hope: the whole fixture holds four in-page links and
        # 228 ordinary ones, so this asks about 1.7% of the anchors on the site and leaves
        # every real navigation link exactly where it was.
        return True
    if element.tag in NATIVE_CONTROL_TAGS:
        return False        # a real control with no overriding role: the semantics are real
    if element.interactive:
        return True         # something non-native is behaving like a control
    if "tabindex" in element.attrs:
        return True         # put in the tab order without being a control
    if element.tag == "div" and _holds_in_page_links(element.html):
        # The strip itself, not just the tabs in it. Whether a row of anchors is a tab list is a
        # question about the container — one tab cannot tell you, and the relationship to the
        # panels below it lives here or nowhere.
        return True
    return _looks_like_heading(element)


def _holds_in_page_links(html: str) -> bool:
    """Three or more in-page links inside one container — a set of controls, or prose."""
    return len(_IN_PAGE_HREF.findall(_inside(html))) >= IN_PAGE_LINK_MINIMUM


def _inside(html: str) -> str:
    """Everything after the container's own opening tag, so its own class is not counted."""
    opening = html.find(">")
    return html[opening + 1:] if opening >= 0 else html


def _repeats_a_child_class(html: str) -> bool:
    """Three or more children carrying the same class — a list drawn without being one.

    A heuristic, and deliberately a conservative one. It is here because the failure it catches
    is common and completely invisible to a rule engine: a card grid or a "list" of styled
    `div`s reads as a list to the eye and, to a screen reader, is an undifferentiated run of
    text with no count, no start and no end.

    It costs a judgment on some containers that turn out to be fine — a footer with four
    identical columns, a nav with five links. That is the intended direction to be wrong in:
    the judge answers "this is a layout, and it says so", which is a cheap right answer, where
    the alternative is never asking and never finding the real ones.
    """
    counts: dict[str, int] = {}
    for value in _CLASS_ATTR.findall(_inside(html)):
        key = _normalise(value)
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
        if counts[key] >= REPEATED_CHILD_MINIMUM:
            return True
    return False


def _applies_structure(element: CapturedElement) -> bool:
    """Structure the page shows that the markup may not carry — 1.3.1.

    **The question `semantics` cannot reach.** That rule asks whether an element is pretending
    to be a control or a heading. A table with no header cells is not pretending to be
    anything; it is simply a table missing its headers. So nothing selected it, nothing judged
    it, and every page of the 21 August audit was recorded as satisfying 1.3.1 with its tables
    unexamined (`SCOPE_GAP_INFO_AND_RELATIONSHIPS.md`).

    **Every table, list and field group is selected, including the ones that look correct.**
    Not out of caution: whether a table's headers are the *right* cells, whether a list's items
    are really items, whether a legend actually names its group — none of that can be decided
    from the tag alone, and a rule engine already covers the cases where the markup contradicts
    itself. What is left is exactly the judgment this check exists for. There are few enough
    containers on a page for that to be affordable.

    **`role="presentation"` is not a skip**, for the same reason it is not one for an image: it
    is an author's claim that the thing carries no structure, and whether that claim is true is
    the whole question 1.3.1 asks. A layout table announced as a layout table is a `pass`, and
    saying so costs one judgment.
    """
    if not element.rendered:
        return False
    if element.tag in STRUCTURE_TAGS:
        return True
    if element.tag == "form":
        # A form is only a structure question when it holds fields that mean nothing alone.
        # Anything else about a form is another checker's business, or nobody's.
        return bool(_GROUPED_INPUT.search(element.html)
                    and not _GROUPING.search(element.html))
    if element.tag == "div":
        return _repeats_a_child_class(element.html)
    return False


def _applies_color(element: CapturedElement) -> bool:
    """Meaning that may be carried by colour with nothing else to carry it — 1.4.1.

    Note what is *not* here: a missing screenshot is not a skip. An element with no image is
    still selected and the judge records `uncertain` naming the missing image (its Rule 2), so
    it reaches a human. Deciding it here would put the platform in the business of pre-judging
    an element it never looked at.
    """
    if not element.rendered:
        return False
    if (not element.text.strip()
            and not _paints(element.styles.get("background-color", ""))
            and not _paints_border(element)
            and not _series_colour(element)[0]):
        return False        # no text, no fill, no border, no series colour: nothing to ask about
    if _has_second_cue(element):
        return False
    return _colour_differs_from_surroundings(element)


def _label_in_scope(element: CapturedElement) -> bool:
    """Is 2.5.3 a question that can be asked about this element at all?

    Two exclusions, both straight out of the criterion's own wording. It applies to "components
    with labels that include text", so a control with no visible text is out of scope entirely.
    And a control with no accessible name at all is 4.1.2's problem, not this one.

    **Out of scope is not the same as satisfied**, and keeping them apart is the whole point of
    splitting this function — see `_settles_label`.
    """
    if not element.rendered or not _is_control(element):
        return False
    if not _visible_text(element):
        return False
    return bool(_normalise(element.accessible_name))


def _applies_label(element: CapturedElement) -> bool:
    """A control whose announced name may not contain its visible label — 2.5.3.

    What reaches the AI is the remainder after `_settles_label`: the cases where the strings
    differ and only a person (or something reading like one) can say whether that difference is
    a real mismatch or a harmless suffix.
    """
    if not _label_in_scope(element):
        return False
    return not _name_contains_label(_normalise(element.accessible_name), _visible_text(element))


def _settles_label(element: CapturedElement) -> str | None:
    """2.5.3 answered here and now, by fact rather than by judgement. `"pass"`, or None.

    The criterion requires that "the name contains the text that is presented visually". When
    the name demonstrably does contain it, the criterion **is met** — that is a string
    comparison, not an opinion, and asking a model to confirm it would spend money to be told
    something we already know.

    **Why this had to become its own function.** The skip was previously folded into
    `_applies_label`, which returned one boolean for two completely different situations:
    *"this criterion does not apply here"* and *"this criterion applies and is satisfied"*. With
    both collapsed into `False`, nothing downstream could tell a decision from a silence — so a
    control the platform had correctly cleared was indistinguishable from one nothing had
    looked at. On the 31 August audit that was 22 of the 42 labelled 2.5.3 controls: every one
    of them right, every one of them recorded as though no check had happened, and the accuracy
    harness reporting them as "never looked at" and counting them wrong.

    Returning the verdict rather than a boolean because a future rule may settle a criterion as
    `"fail"` — a deterministic breach nobody needs to judge — and the caller should not have to
    assume which way a settled answer went.
    """
    if not _label_in_scope(element):
        return None
    if _name_contains_label(_normalise(element.accessible_name), _visible_text(element)):
        return A11Y_PASS
    return None


@dataclass(frozen=True)
class SelectionRule:
    """One checker's scope, as a reviewable record rather than a buried `if`.

    `applies` is the rule; `covers` and `skips` are what it is for and what it deliberately
    lets through, in the words a reviewer needs to argue with it. `describe_rules()` prints the
    whole set, which is how this gets reviewed by someone who does not read Python.
    """

    checker: str
    criteria: tuple[str, ...]
    covers: str
    skips: str
    applies: object          # Callable[[CapturedElement], bool]
    #: Optional. Callable[[CapturedElement], str | None] — a verdict this rule can reach on its
    #: own, without asking the AI, because the criterion's own wording makes the answer a matter
    #: of fact rather than of judgement. None (the default) means this checker never settles
    #: anything and every in-scope element goes to the AI.
    #:
    #: **`applies` and `settles` are mutually exclusive by construction**: an element the rule
    #: has already answered must not also be dispatched, or we would pay to be told what we
    #: know. `settled_verdict` asserts nothing here — the rules themselves are written so that
    #: `applies` returns False exactly where `settles` returns a verdict, and
    #: `test_a11y_checkers` holds them to it.
    settles: object | None = None

    def matches(self, element: CapturedElement) -> bool:
        return bool(self.applies(element))       # type: ignore[operator]

    def settled_verdict(self, element: CapturedElement) -> str | None:
        """The verdict this rule reaches without the AI, or None if it reaches none."""
        if self.settles is None:
            return None
        return self.settles(element)             # type: ignore[operator]


#: The whole rule set, one entry per checker. This is the table D-A11Y-6 keeps a single copy
#: of: the platform owns it, the companion imports it, nobody re-implements it.
SELECTION_RULES: tuple[SelectionRule, ...] = (
    SelectionRule(
        checker="alt",
        criteria=A11Y_CHECKER_CRITERIA["alt"],
        covers="images, image inputs, image maps, anything with role=img, SVGs that are "
               "exposed to assistive technology, <canvas> drawing surfaces, and icons drawn "
               "by a font rather than by an image",
        skips="elements with no rendered box, and bare SVGs with no role, no name and no "
              "<title> — those are never announced, so there is no alternative to judge. An "
              "empty alt is NOT skipped: an informative image left empty is the failure. "
              "<iframe> is left to the rule scanner, which proves a missing frame title "
              "deterministically. An icon font using a real word as its ligature is left "
              "alone — it has an alternative, even if a poor one.",
        applies=_applies_alt,
    ),
    SelectionRule(
        checker="semantics",
        criteria=A11Y_CHECKER_CRITERIA["semantics"],
        covers="anything behaving like a control without being one, anything carrying a role "
               "that overrides its tag, anything put in the tab order, an <a> with no href, "
               "an <a> whose href stays on the page (it does not navigate, so it may be a tab "
               "or a disclosure wearing an anchor), a container holding three or more such "
               "links, and text merely styled to look like a heading",
        skips="native controls and native structure with no overriding role — the semantics "
              "are already real — a role that only restates the tag it sits on, and links "
              "that actually navigate somewhere",
        applies=_applies_semantics,
    ),
    SelectionRule(
        checker="structure",
        criteria=A11Y_CHECKER_CRITERIA["structure"],
        covers="tables, lists and field groups — whether the arrangement a sighted person can "
               "see is written into the markup at all; a form holding radio buttons or "
               "checkboxes with no grouping around them; and a container repeating the same "
               "child class three or more times, which is how a list gets drawn without being "
               "one",
        skips="containers with no rendered box, and nothing else. A table that looks correct "
              "is still selected: whether its headers are the RIGHT cells cannot be decided "
              "from the tag. `role=presentation` is NOT a skip — it is an author's claim that "
              "there is no structure here, and whether that is true is the question.",
        applies=_applies_structure,
    ),
    SelectionRule(
        checker="color",
        criteria=A11Y_CHECKER_CRITERIA["color"],
        covers="text or filled areas whose colour singles them out from their surroundings "
               "with no other visual cue — status dots, required-field markers, legend keys, "
               "links that are only a different colour",
        skips="elements that already carry a second visual cue (an underline, an icon, a "
              "marker character like *) and elements with nothing colour could be carrying. "
              "A BORDER is not a second cue: a field marked invalid by turning its border red "
              "already had a border, and only its colour changed. A missing screenshot is not "
              "a skip either — it becomes an uncertain verdict.",
        applies=_applies_color,
    ),
    SelectionRule(
        checker="label",
        criteria=A11Y_CHECKER_CRITERIA["label"],
        covers="controls whose visible text does not appear in their accessible name — "
               "including a submit, reset or button <input>, whose visible text is its "
               "`value` attribute rather than inner text it can never have",
        skips="controls with no visible text (2.5.3 does not apply to them) and controls with "
              "no accessible name at all (that is 4.1.2). A control whose name already "
              "contains the visible text AS WHOLE WORDS is not skipped but SETTLED — the "
              "criterion is met as a matter of fact, and that is recorded as a pass rather "
              "than as a silence. Words, not letters: 'Search' is not contained in 'Research "
              "tools', and comparing characters made that failure invisible.",
        applies=_applies_label,
        settles=_settles_label,
    ),
    SelectionRule(
        checker="graphics",
        criteria=A11Y_CHECKER_CRITERIA["graphics"],
        covers="every graphic a sighted person reads meaning from — images, SVGs, drawing "
               "surfaces, anything with role=img, icons drawn by a font, and icons painted as "
               "a CSS background image; the question is whether the parts that carry the "
               "meaning stand out enough from what is around them to be made out",
        skips="graphics with no rendered box, and nothing else. A bare <svg> that assistive "
              "technology never announces is NOT skipped — 1.4.11 is about what can be seen, "
              "not about what is announced, which is why this scope is wider than `alt`'s. A "
              "photograph is not skipped either: the criterion exempts graphics whose exact "
              "presentation is essential, and whether an image is one of those is a judgment "
              "the judge makes and reports as not applicable.",
        applies=_applies_graphics,
    ),
)


#: Built, reviewed, and deliberately not running. **Empty today.**
#:
#: Kept as a mechanism rather than deleted, because a check belongs here when it is not wrong
#: but its claim cannot yet be supported — and the alternative, commenting it out, loses the
#: scope somebody argued for and leaves nothing for `describe_rules()` to show a reviewer.
#:
#: `graphics` sat here for part of 1 September, while the ownership registry was brought into
#: line with correction R14. What that taught is in `A11Y_HELD_BACK_CLAIMS`: a hold must
#: WITHDRAW its criterion from positive conformance claims, never leave it to whatever else
#: happens to touch that criterion.
#:
#: To hold a check: move its `SelectionRule` here, take its name out of `CHECKERS`, and move
#: its criteria from `A11Y_CHECKER_CRITERIA` into `A11Y_HELD_BACK_CRITERIA`. Leave it in
#: `A11Y_ALL_CHECKER_CRITERIA` so verdicts recorded before the hold still read back.
HELD_BACK_SELECTION_RULES: tuple[SelectionRule, ...] = ()

_RULES_BY_CHECKER: dict[str, SelectionRule] = {rule.checker: rule for rule in SELECTION_RULES}


def checkers_for(element: CapturedElement) -> tuple[str, ...]:
    """Which checks this element should be judged by, in `CHECKERS` order.

    An element can legitimately be selected by more than one: a `<div role="button">` styled
    only in colour is both a semantics question and a colour question, and they are different
    questions with different answers. An icon is routinely selected by both `alt` and
    `graphics` — *does it say what it means?* and *can you see it?* — and an icon can very
    easily pass one and fail the other.

    Deliberately not "the five checks" any more. That sentence was written when there were four,
    survived a fifth being added on 24 August, and would have survived a sixth: a count in prose
    is a fact nobody updates. `CHECKERS` is the count, and `test_a11y_wcag` holds it.
    """
    return tuple(
        checker for checker in CHECKERS if _RULES_BY_CHECKER[checker].matches(element)
    )


def to_candidate(element: CapturedElement) -> A11yCandidate:
    """The captured element as the judge receives it (pointer-not-body: #1/#3)."""
    return A11yCandidate(
        selector=element.selector,
        html=element.html,
        markup_truncated=element.markup_truncated,
        structure=dict(element.structure or {}),
        screenshot_ref=element.screenshot_ref,
        context=element.context,
        route=element.route,
        accessible_name=element.accessible_name,
        parent=dict(element.parent or {}),
    )


def select(elements: Sequence[CapturedElement | Mapping]) -> list:
    """Every (element, checker) pair worth judging on this page, ready for dispatch.

    Order is stable — page order, then `CHECKERS` order within an element — so the same page
    produces the same batch twice, which is what makes a run comparable against the golden set.

    Accepts raw dicts as well as `CapturedElement`s, because the companion posts JSON.
    """
    # Imported here, not at module level: `select` is the only thing in this module that needs
    # dispatch, and the rules have to stay importable on their own for the companion.
    from apps.a11y.dispatch import A11yRequest

    requests: list = []
    for raw in elements:
        element = raw if isinstance(raw, CapturedElement) else CapturedElement.from_dict(raw)
        candidate = to_candidate(element)
        requests.extend(
            A11yRequest(checker=checker, candidate=candidate)
            for checker in checkers_for(element)
        )
    return requests


def explain(element: CapturedElement) -> dict[str, bool]:
    """Which rules fired for this element, by checker.

    Here so that "why was this element never judged?" is a question with an answer — for
    QA-11b bringing the rules to a real page for the first time, and for anyone reviewing a
    conformance report who wants to know what the AI pass did and did not look at.
    """
    return {checker: _RULES_BY_CHECKER[checker].matches(element) for checker in CHECKERS}


def settled(element: CapturedElement | Mapping) -> dict[str, str]:
    """Criteria this element ANSWERS on the rules alone, as `{checker: verdict}`.

    The companion piece to `explain`, and the answer to a question that had none. `explain` says
    which checkers were dispatched; between them they separate the three states an element can
    be in for a given checker, which used to be two:

        dispatched      — the AI was asked (`explain` says True)
        settled here    — the criterion was answered by fact (this function)
        out of scope    — the criterion cannot be asked about this element at all

    **Why the middle one had to become visible.** A settled element carries no verdict row and
    no dispatch, so it looked exactly like an element nothing had examined. On the 31 August
    audit that covered 22 of the 42 labelled 2.5.3 controls — all answered correctly, none of
    them recorded as answered. The accuracy harness read them as "never looked at", counted
    them as wrong, and `label` could not reach the sample floor no matter how much data was
    added, because the dataset pairs every AI-judged failure with a rule-settled pass.

    Empty for every checker that settles nothing, which today is every checker but `label`. That
    is a statement about the rules as they stand, not a limit of this function.
    """
    if not isinstance(element, CapturedElement):
        element = CapturedElement.from_dict(element)
    out: dict[str, str] = {}
    for checker in CHECKERS:
        verdict = _RULES_BY_CHECKER[checker].settled_verdict(element)
        if verdict is not None:
            out[checker] = verdict
    return out


def describe_rules() -> str:
    """The rule set in plain words: what each checker covers and what it deliberately skips.

    **Held-back checks are printed too, and labelled.** Leaving them out would make this read
    as the whole rule set when it is not, and a reviewer comparing it against a conformance
    statement has to be able to see that something built is not running. Printing them WITHOUT
    the label would be worse: that is how a check nobody was running came to be described as
    covering a criterion for five days.
    """
    lines: list[str] = []
    for rule in SELECTION_RULES:
        lines.append(f"{rule.checker} (WCAG {', '.join(rule.criteria)})")
        lines.append(f"  covers: {rule.covers}")
        lines.append(f"  skips:  {rule.skips}")
    for rule in HELD_BACK_SELECTION_RULES:
        lines.append(
            f"{rule.checker} (WCAG {', '.join(rule.criteria)}) - HELD BACK, NOT RUNNING")
        lines.append(f"  covers: {rule.covers}")
        lines.append(f"  skips:  {rule.skips}")
        lines.append("  held:   this check does not run, and nothing it would have found is "
                     "reported. See A11Y_HELD_BACK_CRITERIA for why, and for what has to be "
                     "true before it runs again.")
    return "\n".join(lines)
