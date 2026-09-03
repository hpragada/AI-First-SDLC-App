"""The two page-level things a browser can *measure* that axe has no rule for (QA-25).

**Why this module exists at all.** The criterion ownership registry records fourteen criteria as
decided by a deterministic engine. The platform's deterministic engine is axe-core. axe-core
4.13.0, under the six WCAG tags this platform selects, ships **no rule tagged `wcag1410` and no
rule tagged `wcag1411`** — so two of those fourteen were owned by an engine that cannot check
them, from the day the scanner was wired until this module.

Nothing caught it, and the reason is worth writing down where the fix lives. `ownership.py`'s
`verify_complete()` proves every criterion has an owner; `gates.wcag.verify_complete()` proves
every criterion is either asked of a designer or recorded as deliberately not asked. Neither asks
the third question — *can the owner we named actually perform the check?* — and that question is
now `test_a11y_owner_capability`, which fails by name the moment a rule-owned criterion has
nothing behind it.

**What each half is, and what it is not.**

  * **1.4.10 Reflow** is measured whole. The criterion has an objective test — 320 CSS pixels
    wide, no two-dimensional scrolling — and its one exception (content that genuinely requires a
    second dimension: data tables, code, maps, drawing surfaces) is a fixed list of container
    kinds rather than a judgement. So this decides it, deterministically, with no AI involved.

  * **1.4.11 Non-text Contrast** is a criterion in two halves and only one of them is arithmetic.
    *Can you see where the controls are?* is colours and a threshold, and it is here. *Are the
    meaningful parts of the icons and diagrams visible enough?* needs somebody to know which
    parts of a picture carry meaning, and that is the `graphics` checker in `checkers/rules.py`.
    Neither half is the criterion on its own, and the registry itself said so before either was
    built — its own rationale reads *"computable, but 'which graphics matter' needs some
    review."* The file then recorded the owner as `rule` anyway, which is how the second half
    went unbuilt.

**The reading is the browser's, the ruling is the platform's.** The companion narrows a window
and reports two numbers; it reads computed colours and reports them unblended. Every ratio, every
threshold and every exception is applied here, where it can be unit-tested against known colours
instead of trusted inside a string that came back from a page. This is the same boundary
`journey_rules` keeps for the keyboard walk, kept for the same reason.

**These rules only ever produce a failure, never a pass.** A page that reflows cleanly proves
nothing about the parts a narrow window happened not to reveal; a button whose border clears 3:1
has not thereby been proven identifiable. Positive observations are recorded as coverage by
`observations_for()` below, which is a different and weaker statement — *this was measured and
nothing was proven wrong* — and it is the one a conformance statement is entitled to.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from integrations.types import A11yRuleFailure

#: Rule ids for what this module proves. Namespaced exactly as `journey_rules` is, and for the
#: same reason: the defect ticket prints the rule id, and an axe-shaped id would send a developer
#: looking for a rule that does not exist in any scanner they can run.
RULE_REFLOW = "a11y-page/reflow-320"
RULE_FIELD_BOUNDARY = "a11y-page/field-boundary-invisible"
RULE_COMPONENT_BOUNDARY = "a11y-page/component-boundary-contrast"

#: WCAG 1.4.11's threshold for anything that is not text. Not configurable: it is the number in
#: the standard, and a project that could lower it could claim a conformance it does not have.
MIN_NON_TEXT_RATIO = 3.0

#: The width the criterion names. Mirrored from the companion, and mirrored on purpose — a
#: measurement taken at some other width would be evidence for a criterion nobody asked about,
#: and `reflow_failure` refuses one rather than reporting it as if it were this.
REFLOW_WIDTH = 320

#: What a browser paints where a page sets nothing. Every engine's default canvas is white, and
#: a stack of fully transparent ancestors therefore resolves to white rather than to "unknown" —
#: declining to rule on the most common case of all (an unstyled body) would switch this check
#: off for most pages.
CANVAS_WHITE = (255.0, 255.0, 255.0)

_RGB = re.compile(
    r"rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:\s*[,/]\s*([\d.%]+))?\s*\)",
    re.IGNORECASE,
)
_HEX = re.compile(r"^#(?:([0-9a-f]{3})|([0-9a-f]{6}))$", re.IGNORECASE)

#: Outline and border styles that draw nothing, so an element carrying one has no boundary from
#: it. `hidden` is here with `none` because it is `none` with a different table-border meaning.
_INVISIBLE_LINE_STYLES = frozenset({"", "none", "hidden"})


# ---------------------------------------------------------------------------------------
# Colour arithmetic — the whole of it, in one place, testable against known values
# ---------------------------------------------------------------------------------------

def parse_color(text) -> tuple[float, float, float, float] | None:
    """`rgb()`, `rgba()` or a hex string as (r, g, b, alpha), or None if it is not a colour.

    `None` and "fully transparent" are deliberately different answers. A value we could not read
    must never be treated as a colour we measured — the first produces no ruling, the second is a
    real fact about the page that the compositing below depends on.
    """
    raw = str(text or "").strip().lower()
    if not raw or raw == "none":
        return None
    if raw == "transparent":
        return (0.0, 0.0, 0.0, 0.0)
    if match := _HEX.match(raw):
        short, full = match.groups()
        digits = "".join(c * 2 for c in short) if short else full
        return (
            float(int(digits[0:2], 16)),
            float(int(digits[2:4], 16)),
            float(int(digits[4:6], 16)),
            1.0,
        )
    if not (match := _RGB.search(raw)):
        return None
    red, green, blue, alpha = match.groups()
    try:
        channels = [min(255.0, max(0.0, float(v))) for v in (red, green, blue)]
        if alpha is None:
            opacity = 1.0
        elif alpha.endswith("%"):
            opacity = float(alpha[:-1]) / 100.0
        else:
            opacity = float(alpha)
    except ValueError:
        return None
    return (channels[0], channels[1], channels[2], min(1.0, max(0.0, opacity)))


def composite(top: tuple[float, float, float, float],
              bottom: tuple[float, float, float]) -> tuple[float, float, float]:
    """`top` painted over an opaque `bottom` — the colour an eye actually receives.

    Straight source-over alpha compositing, which is what a browser does and therefore what the
    ratio has to be computed on. A half-transparent black border over white is grey, and reading
    it as black would report a contrast the page does not have.
    """
    alpha = top[3]
    return tuple(top[i] * alpha + bottom[i] * (1.0 - alpha) for i in range(3))  # type: ignore[return-value]


def flatten(stack: Sequence | None, *, default: tuple[float, float, float] = CANVAS_WHITE
            ) -> tuple[float, float, float]:
    """What is really behind an element, from the ancestor backgrounds nearest-first.

    Walked from the far end back towards the element, because that is the order the paint lands
    in: the root paints first and each descendant paints over it. An unreadable entry is skipped
    rather than ending the walk — one malformed value should cost that layer, not the reading.
    """
    result = default
    for raw in reversed(list(stack or [])):
        colour = parse_color(raw)
        if colour is None or colour[3] <= 0.0:
            continue
        result = composite(colour, result)
    return result


def relative_luminance(colour: tuple[float, float, float]) -> float:
    """WCAG relative luminance. The formula from the standard, not an approximation of it."""
    channels = []
    for value in colour:
        srgb = value / 255.0
        channels.append(srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: tuple[float, float, float],
                   second: tuple[float, float, float]) -> float:
    """The WCAG contrast ratio between two opaque colours, lighter over darker."""
    a, b = relative_luminance(first), relative_luminance(second)
    lighter, darker = (a, b) if a >= b else (b, a)
    return (lighter + 0.05) / (darker + 0.05)


def _ratio_text(value: float) -> str:
    return f"{value:.2f}:1"


def _rgb_text(colour: tuple[float, float, float]) -> str:
    return "rgb({}, {}, {})".format(*(round(c) for c in colour))


# ---------------------------------------------------------------------------------------
# 1.4.10 Reflow
# ---------------------------------------------------------------------------------------

def reflow_failure(*, route: str, measurement: Mapping | None) -> A11yRuleFailure | None:
    """1.4.10 — this page needs sideways scrolling at 320 pixels wide.

    **Silence, never a guess, for every reason a measurement can be absent.** A capture from an
    older companion carries no measurement; a page that threw during the narrow pass carries one
    that says so; a measurement taken at some other width is evidence about a different question.
    All three produce `None`, and the criterion is then reported as *not evaluated* — which is
    what we actually know about it.

    **The standard's own exception is applied, and only it.** 1.4.10 exempts "parts of the
    content which require two-dimensional layout for usage or meaning", so an overflow caused
    entirely by a data table, a code block, a map, a drawing surface or a region the author
    deliberately made scrollable is not a failure. The companion records *why* each offender is
    exempt; this decides. An overflow with even one non-exempt offender is a failure, and the
    exempt ones are left out of the evidence so a developer is not sent to a table that is fine.

    **A measured overflow with no offender named is still a failure.** The two numbers are the
    criterion's own test and they do not depend on attributing the cause — a page whose content
    is wider than the window fails whether or not we could point at the element responsible, and
    reporting nothing there would lose the clearest evidence we have.
    """
    if not isinstance(measurement, Mapping) or not measurement.get("measured"):
        return None
    try:
        requested = int(measurement.get("requested_width") or 0)
        viewport = int(measurement.get("viewport_width") or 0)
        content = int(measurement.get("content_width") or 0)
        overflow = int(measurement.get("overflow_px") or 0)
    except (TypeError, ValueError):
        # Numbers we cannot read are not numbers proving anything.
        return None
    if requested != REFLOW_WIDTH:
        return None
    if overflow <= 0 or content <= viewport:
        return None

    offenders = [o for o in (measurement.get("offenders") or []) if isinstance(o, Mapping)]
    blamed = [o for o in offenders if not str(o.get("two_d_reason") or "").strip()]
    exempt = [o for o in offenders if str(o.get("two_d_reason") or "").strip()]
    if offenders and not blamed:
        # Everything sticking out is content the criterion allows to be two-dimensional.
        return None

    if blamed:
        named = ", ".join(
            f"`{str(o.get('selector') or o.get('tag') or 'an element')}` "
            f"({int(o.get('overflow_px') or 0)}px past the edge)"
            for o in blamed[:5]
        )
        cause = f" The widest things sticking out: {named}."
    else:
        cause = (
            " No single element could be identified as the cause, so the overflow is coming "
            "from the page's own layout rather than from one component."
        )
    if exempt:
        cause += (
            f" {len(exempt)} further element(s) overflow but are content the criterion allows "
            f"to scroll in two directions, and are not counted."
        )
    return A11yRuleFailure(
        criterion="1.4.10", selector=str((blamed[0].get("selector") if blamed else "") or "")[:512],
        route=route, rule_id=RULE_REFLOW,
        evidence=(
            f"At {REFLOW_WIDTH} pixels wide — the width WCAG 1.4.10 is written against, and what "
            f"a 1280px screen becomes at 400% zoom — this page's content is {content}px across in "
            f"a {viewport}px window, so it has to be scrolled sideways to be read.{cause}"
        ),
    )


# ---------------------------------------------------------------------------------------
# 1.4.11 Non-text Contrast — the measurable half
# ---------------------------------------------------------------------------------------

#: The two kinds of edge a component can have, and they are NOT interchangeable.
#:
#: `DRAWN` is an authored boundary — somebody wrote a border or an outline to say where this
#: component is — and 1.4.11 is written about exactly that. `FILL` is weaker evidence: a
#: background colour may be the thing identifying the control, or it may be decoration on a
#: control whose text already identifies it, and no computed style can tell those apart.
#:
#: Kept as a tag on every signal rather than recovered from the wording, because the rule below
#: turns on the distinction — a `str.endswith` on a human-readable label would put the whole
#: difference between the two rules at the mercy of an edit to a sentence.
SIGNAL_DRAWN = "drawn"
SIGNAL_FILL = "fill"


def _boundary_signals(component: Mapping, behind: tuple[float, float, float]
                      ) -> list[tuple[str, str, float]]:
    """Every edge of this component, as (kind, what it is, contrast against `behind`)."""
    signals: list[tuple[str, str, float]] = []

    for border in component.get("borders") or []:
        if not isinstance(border, Mapping):
            continue
        if str(border.get("style") or "").strip().lower() in _INVISIBLE_LINE_STYLES:
            continue
        colour = parse_color(border.get("color"))
        if colour is None or colour[3] <= 0.0:
            continue
        side = str(border.get("side") or "").strip()
        signals.append((
            SIGNAL_DRAWN,
            f"its {side} border" if side else "its border",
            contrast_ratio(composite(colour, behind), behind),
        ))

    outline = component.get("outline")
    if isinstance(outline, Mapping):
        style = str(outline.get("style") or "").strip().lower()
        try:
            width = float(str(outline.get("width") or "0").replace("px", "").strip() or 0)
        except ValueError:
            width = 0.0
        colour = parse_color(outline.get("color"))
        if style not in _INVISIBLE_LINE_STYLES and width > 0 and colour and colour[3] > 0.0:
            signals.append((
                SIGNAL_DRAWN, "its outline",
                contrast_ratio(composite(colour, behind), behind),
            ))

    fill = parse_color(component.get("background"))
    if fill is not None and fill[3] > 0.0:
        # A fill identical to what is behind it is not an edge at all — it is the same colour,
        # and reporting a 1.00:1 "edge" would describe a line nobody drew.
        ratio = contrast_ratio(composite(fill, behind), behind)
        if ratio > 1.0:
            signals.append((SIGNAL_FILL, "its own background", ratio))

    return signals


def _unreadable(component: Mapping) -> str:
    """Why this component's colours cannot honestly be measured, or "" when they can.

    Each of these is a picture where a colour is expected, and a picture has no single colour.
    Sampling one pixel and calling it the background is how a contrast checker reports a
    confident wrong number, so the reading is declined and the component goes to a person.
    """
    if str(component.get("background_image") or "none").strip().lower() != "none":
        return "it is painted with an image or a gradient rather than a flat colour"
    if component.get("behind_images"):
        return "what sits behind it is an image or a gradient rather than a flat colour"
    return ""


def contrast_failures(*, route: str, measurement: Mapping | None
                      ) -> tuple[tuple[A11yRuleFailure, ...], tuple[dict, ...]]:
    """1.4.11's measurable half: (failures, components a person still has to look at).

    Two rules, and the difference between them is the difference between a control you cannot
    find and a line somebody drew too faintly.

    **`field-boundary-invisible` — a form field with no perceivable edge.** A text box, a
    dropdown or a text area is not identified by its label: the label says what to type, and the
    *box* says where. A field with no border, no outline and a fill indistinguishable from the
    page around it is a field a partially-sighted user cannot find, and that is the clearest
    failure this criterion has. It fires when the strongest edge the field has — any border, its
    outline, or its own fill — is under 3:1, and when it has no edge at all.

    **`component-boundary-contrast` — an authored boundary that is too faint.** A border or an
    outline is somebody's decision to draw the edge of a control; 1.4.11 requires that edge to
    reach 3:1. This fires only on those two, never on a fill alone.

    **What deliberately does NOT fire, because over-firing is the worse error.** A button
    identified by its own words with no border drawn round it is not a 1.4.11 defect — the text
    identifies it and 1.4.3 governs whether the text can be read. Firing there would put every
    borderless text button on every page into a compliance report as a Level AA failure a team
    cannot argue with, and would be wrong about the standard as well as unhelpful.

    **A box-shadow suppresses a failure and asks a person instead.** A shadow is how a great many
    design systems draw the edge they did not draw with a border, its colour cannot be read
    reliably from the computed value, and a component whose only weak signal is accompanied by
    one has an edge we cannot measure rather than no edge at all.
    """
    if not isinstance(measurement, Mapping) or not measurement.get("measured"):
        return (), ()

    failures: list[A11yRuleFailure] = []
    review: list[dict] = []
    for component in measurement.get("components") or []:
        if not isinstance(component, Mapping):
            continue
        selector = str(component.get("selector") or "")[:512]
        if reason := _unreadable(component):
            review.append({"selector": selector, "reason": reason})
            continue

        behind = flatten(component.get("behind_stack"))
        signals = _boundary_signals(component, behind)
        has_shadow = str(component.get("box_shadow") or "none").strip().lower() != "none"
        drawn = [s for s in signals if s[0] == SIGNAL_DRAWN]
        best = max(signals, key=lambda s: s[2]) if signals else None

        if component.get("is_field"):
            if best is not None and best[2] >= MIN_NON_TEXT_RATIO:
                continue
            if has_shadow:
                review.append({
                    "selector": selector,
                    "reason": "its edge is drawn with a shadow, whose colour cannot be read "
                              "from the page reliably enough to measure",
                })
                continue
            if best is None:
                evidence = (
                    f"This form field has no visible edge at all — no border, no outline, and a "
                    f"fill identical to the {_rgb_text(behind)} behind it. There is nothing to "
                    f"show a user where the field is or that there is a field here."
                )
            else:
                evidence = (
                    f"The strongest edge this form field has is {best[1]}, which contrasts "
                    f"{_ratio_text(best[2])} against the {_rgb_text(behind)} behind it. WCAG "
                    f"1.4.11 requires at least 3:1 so the field can be found."
                )
            failures.append(A11yRuleFailure(
                criterion="1.4.11", selector=selector, route=route,
                rule_id=RULE_FIELD_BOUNDARY, evidence=evidence,
            ))
            continue

        if not drawn:
            # No border and no outline: nothing was drawn to identify this control, so there is
            # no authored boundary for this criterion to be about.
            continue
        weakest = min(drawn, key=lambda s: s[2])
        if weakest[2] >= MIN_NON_TEXT_RATIO:
            continue
        if has_shadow:
            review.append({
                "selector": selector,
                "reason": "its faint border sits alongside a shadow, and a shadow's colour "
                          "cannot be read from the page reliably enough to measure",
            })
            continue
        failures.append(A11yRuleFailure(
            criterion="1.4.11", selector=selector, route=route,
            rule_id=RULE_COMPONENT_BOUNDARY,
            evidence=(
                f"This control's edge is drawn — {weakest[1]} — but it contrasts only "
                f"{_ratio_text(weakest[2])} against the {_rgb_text(behind)} behind it. WCAG "
                f"1.4.11 requires at least 3:1 for anything drawn to identify a control."
            ),
        ))
    return tuple(failures), tuple(review)


# ---------------------------------------------------------------------------------------
# What the platform stores about a screen
# ---------------------------------------------------------------------------------------

def failures_for(*, route: str, measurements: Mapping | None) -> tuple[A11yRuleFailure, ...]:
    """Every page-level rule failure one screen's measurements prove."""
    if not isinstance(measurements, Mapping):
        return ()
    out: list[A11yRuleFailure] = []
    if found := reflow_failure(route=route, measurement=measurements.get("reflow")):
        out.append(found)
    proven, _ = contrast_failures(
        route=route, measurement=measurements.get("non_text_contrast"))
    out.extend(proven)
    return tuple(out)


def observations_for(measurements: Mapping | None) -> list[tuple[str, str, str]]:
    """One screen's measurements as criterion coverage — `(criterion, outcome, detail)`.

    **This is where a clean measurement becomes something a conformance statement may cite**, and
    it is a weaker claim than the failures above deliberately: `passed` here means *this was
    measured on this page and nothing was proven wrong*, which is exactly what a rule can say.

    A screen with no measurement produces **nothing at all** — not a pass, not a failure. That is
    the same discipline `coverage.from_scan` keeps for a screen the scanner could not run on, and
    it is what stops an older companion's captures reading as pages that reflowed cleanly.

    `needs_human` is a first-class outcome here rather than a rounding of `passed`. A page whose
    every measurable component sat behind a gradient was not checked, and a criterion nobody
    could measure must not arrive in the statement wearing a pass.
    """
    if not isinstance(measurements, Mapping):
        return []
    out: list[tuple[str, str, str]] = []

    reflow = measurements.get("reflow")
    if isinstance(reflow, Mapping) and reflow.get("measured"):
        failed = reflow_failure(route="", measurement=reflow) is not None
        out.append(("1.4.10", "failed" if failed else "passed", RULE_REFLOW))

    contrast = measurements.get("non_text_contrast")
    if isinstance(contrast, Mapping) and contrast.get("measured"):
        components = [c for c in (contrast.get("components") or []) if isinstance(c, Mapping)]
        proven, review = contrast_failures(route="", measurement=contrast)
        if proven:
            outcome = "failed"
        elif not components:
            # The pass ran and this page has no user interface components on it. The rule had
            # nothing to apply to, which is a real and different answer from "it was fine".
            outcome = "not_applicable"
        elif len(review) == len(components):
            outcome = "needs_human"
        else:
            outcome = "passed"
        out.append(("1.4.11", outcome, RULE_COMPONENT_BOUNDARY))
    return out
