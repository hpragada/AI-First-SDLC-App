"""Candidate selection — which elements each of the four checkers applies to (QA-03).

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

from integrations.types import A11Y_CHECKER_CRITERIA, A11yCandidate

#: The four checkers, in the order a page's requests are emitted. Fixed so that two runs over
#: the same page produce the same batch in the same order — a judgment run that is not
#: reproducible cannot be compared against the golden set (QA-09).
CHECKERS: tuple[str, ...] = ("alt", "semantics", "color", "label")

#: The computed style properties the rules read. Named here because this is also the list the
#: companion has to capture (QA-11b): a property missing from the capture silently turns every
#: rule that reads it into "no". Keep the list short — each entry is a per-element cost in the
#: browser.
STYLE_KEYS: tuple[str, ...] = (
    "color",
    "background-color",
    "text-decoration-line",
    "font-size",
    "font-weight",
    "border-style",
)

#: Elements that are already controls. Their semantics are real, so `semantics` skips them
#: unless something overrides those semantics (an explicit contradictory `role`, or an `<a>`
#: with no `href`, which is not a link at all).
NATIVE_CONTROL_TAGS = frozenset({
    "a", "button", "input", "select", "textarea", "summary", "option", "details",
})

HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

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

#: Conventional non-colour markers. A required field flagged with a red asterisk carries a
#: second cue in the text itself, so colour is not the *only* visual means and 1.4.1 is met.
TEXT_CUE_MARKERS = ("*", "✓", "✗", "×", "!", "⚠")

#: Input types whose `value` attribute IS the control's visible label, because HTML renders it
#: as the button's face. For every other type `value` holds what the user typed — that is data,
#: not a label, and reading it as one would compare a person's own name against a field's
#: accessible name and call the difference a defect.
VALUE_LABEL_INPUT_TYPES = frozenset({"submit", "reset", "button"})

_WHITESPACE = re.compile(r"\s+")
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

    `html`, `context`, `screenshot_ref`, `selector` and `route` are not read by any rule; they
    are carried through onto the `A11yCandidate` the judge receives.
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
    html: str = ""
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
            context=str(raw.get("context") or ""),
            screenshot_ref=str(raw.get("screenshot_ref") or ""),
            route=str(raw.get("route") or ""),
        )


# ── small readers over the captured facts ──────────────────────────────────────────

def _normalise(text: str) -> str:
    """Lowercased, whitespace-collapsed — how two labels are compared for "the same words"."""
    return _WHITESPACE.sub(" ", str(text or "")).strip().lower()


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
    """
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


def _colour_differs_from_surroundings(element: CapturedElement) -> bool:
    """Something about this element's colour singles it out from what is around it."""
    styles, parent = element.styles, element.parent_styles
    if styles.get("color", "") and styles.get("color") != parent.get("color", ""):
        return True
    background = styles.get("background-color", "")
    return _paints(background) and background != parent.get("background-color", "")


def _has_second_cue(element: CapturedElement) -> bool:
    """A visual cue other than colour is already present, so 1.4.1 is satisfied.

    Only *visual* cues count. An `aria-label` is not one: 1.4.1 is about what a person who
    cannot distinguish the colours can still see, not about what assistive tech is told.
    """
    decoration = str(element.styles.get("text-decoration-line", "")).lower()
    if "underline" in decoration or "line-through" in decoration:
        return True
    if str(element.styles.get("border-style", "")).strip().lower() not in {"", "none"}:
        return True
    if _has_nested_graphic(element):
        return True
    return any(marker in element.text for marker in TEXT_CUE_MARKERS)


# ── the rules themselves ───────────────────────────────────────────────────────────

def _applies_alt(element: CapturedElement) -> bool:
    """Non-text content that is presented to the user — the scope of 1.1.1."""
    if not element.rendered:
        return False
    if element.role == "img" or element.tag in {"img", "area"}:
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


def _applies_semantics(element: CapturedElement) -> bool:
    """Structure or a control that may be drawn rather than real — 1.3.1 and 4.1.2."""
    if not element.rendered:
        return False
    if element.role and not _role_is_redundant(element):
        return True
    if element.tag == "a" and not element.attrs.get("href"):
        return True         # an <a> without href is not a link, whatever it looks like
    if element.tag in NATIVE_CONTROL_TAGS:
        return False        # a real control with no overriding role: the semantics are real
    if element.interactive:
        return True         # something non-native is behaving like a control
    if "tabindex" in element.attrs:
        return True         # put in the tab order without being a control
    return _looks_like_heading(element)


def _applies_color(element: CapturedElement) -> bool:
    """Meaning that may be carried by colour with nothing else to carry it — 1.4.1.

    Note what is *not* here: a missing screenshot is not a skip. An element with no image is
    still selected and the judge records `uncertain` naming the missing image (its Rule 2), so
    it reaches a human. Deciding it here would put the platform in the business of pre-judging
    an element it never looked at.
    """
    if not element.rendered:
        return False
    if not element.text.strip() and not _paints(element.styles.get("background-color", "")):
        return False        # no text and no fill: there is no colour carrying anything
    if _has_second_cue(element):
        return False
    return _colour_differs_from_surroundings(element)


def _applies_label(element: CapturedElement) -> bool:
    """A control whose announced name may not contain its visible label — 2.5.3.

    Two skips, both straight out of the criterion's own wording. It applies to "components
    with labels that include text", so a control with no visible text is out of scope
    entirely. And it requires that "the name contains the text that is presented visually" —
    when the name demonstrably does contain it, the criterion is met as a matter of fact and
    there is nothing left to judge. What reaches the AI is the remainder: the cases where the
    strings differ and only a person (or something reading like one) can say whether that
    difference is a real mismatch or a harmless suffix.
    """
    if not element.rendered or not _is_control(element):
        return False
    visible = _visible_text(element)
    if not visible:
        return False
    name = _normalise(element.accessible_name)
    if not name:
        return False        # no accessible name at all is 4.1.2's problem, not 2.5.3's
    return visible not in name


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

    def matches(self, element: CapturedElement) -> bool:
        return bool(self.applies(element))       # type: ignore[operator]


#: The whole rule set, one entry per checker. This is the table D-A11Y-6 keeps a single copy
#: of: the platform owns it, the companion imports it, nobody re-implements it.
SELECTION_RULES: tuple[SelectionRule, ...] = (
    SelectionRule(
        checker="alt",
        criteria=A11Y_CHECKER_CRITERIA["alt"],
        covers="images, image inputs, image maps, anything with role=img, and SVGs that are "
               "exposed to assistive technology",
        skips="elements with no rendered box, and bare SVGs with no role, no name and no "
              "<title> — those are never announced, so there is no alternative to judge. An "
              "empty alt is NOT skipped: an informative image left empty is the failure.",
        applies=_applies_alt,
    ),
    SelectionRule(
        checker="semantics",
        criteria=A11Y_CHECKER_CRITERIA["semantics"],
        covers="anything behaving like a control without being one, anything carrying a role "
               "that overrides its tag, anything put in the tab order, an <a> with no href, "
               "and text merely styled to look like a heading",
        skips="native controls and native structure with no overriding role — the semantics "
              "are already real — and a role that only restates the tag it sits on",
        applies=_applies_semantics,
    ),
    SelectionRule(
        checker="color",
        criteria=A11Y_CHECKER_CRITERIA["color"],
        covers="text or filled areas whose colour singles them out from their surroundings "
               "with no other visual cue — status dots, required-field markers, legend keys, "
               "links that are only a different colour",
        skips="elements that already carry a second visual cue (an underline, a border, an "
              "icon, a marker character like *) and elements with nothing colour could be "
              "carrying. A missing screenshot is NOT a skip — it becomes an uncertain verdict.",
        applies=_applies_color,
    ),
    SelectionRule(
        checker="label",
        criteria=A11Y_CHECKER_CRITERIA["label"],
        covers="controls whose visible text does not appear in their accessible name — "
               "including a submit, reset or button <input>, whose visible text is its "
               "`value` attribute rather than inner text it can never have",
        skips="controls with no visible text (2.5.3 does not apply to them), controls with no "
              "accessible name at all (that is 4.1.2), and controls whose name already "
              "contains the visible text — the criterion is met as a matter of fact",
        applies=_applies_label,
    ),
)

_RULES_BY_CHECKER: dict[str, SelectionRule] = {rule.checker: rule for rule in SELECTION_RULES}


def checkers_for(element: CapturedElement) -> tuple[str, ...]:
    """Which of the four checks this element should be judged by, in `CHECKERS` order.

    An element can legitimately be selected by more than one: a `<div role="button">` styled
    only in colour is both a semantics question and a colour question, and they are different
    questions with different answers.
    """
    return tuple(
        checker for checker in CHECKERS if _RULES_BY_CHECKER[checker].matches(element)
    )


def to_candidate(element: CapturedElement) -> A11yCandidate:
    """The captured element as the judge receives it (pointer-not-body: #1/#3)."""
    return A11yCandidate(
        selector=element.selector,
        html=element.html,
        screenshot_ref=element.screenshot_ref,
        context=element.context,
        route=element.route,
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


def describe_rules() -> str:
    """The rule set in plain words — what each checker covers and what it deliberately skips."""
    lines: list[str] = []
    for rule in SELECTION_RULES:
        lines.append(f"{rule.checker} (WCAG {', '.join(rule.criteria)})")
        lines.append(f"  covers: {rule.covers}")
        lines.append(f"  skips:  {rule.skips}")
    return "\n".join(lines)
