"""The two things a keyboard walk can *measure* rather than judge (QA-21, closing D-A11Y-72).

QA-06's second rule is "a measurement beats an opinion", and QA-20 shipped without it: a journey
pass ran no deterministic check of its own, so all eight criteria were pure judgment. Two of them
do not have to be. The criterion ownership registry says so itself, and independently of this
build — `2.4.7` carries *"Rule detects outline:none"* and `4.1.3` carries *"Rule detects aria-live
presence"* as secondary checks.

**Neither is an axe rule.** Of the eight journey criteria, axe-core covers exactly one (`2.1.1`,
via `frame-focusable-content` / `scrollable-region-focusable` / `server-side-image-map`) under the
six WCAG tags this platform selects. So these two are not a scan being re-used — they are two
small DOM facts, read at the moment the agent has the element focused, which is the only moment
they are true. That is also why QA-20 could not reach for another run's scan: a measurement taken
on a page this agent has since interacted with is a measurement of a different page.

**How the trust boundary is kept.** The agent runs a *prescribed* snippet and reports the raw
values it read. It does not decide what they mean — this module does, deterministically, and the
result is fed to `triage()` as an `A11yRuleFailure` exactly as a scanner failure is. The agent can
report a wrong raw value, which is the same trust boundary as it reporting whether it walked a
step at all; what it cannot do is talk the platform out of a failure the values prove. Say this
plainly at review rather than calling it a scanner measurement: the *reading* is the agent's, the
*ruling* is the platform's.

**These rules only ever produce a failure, never a pass.** That is QA-06's rule 2 running one way
only, and it matters more here than anywhere. An element with a visible outline has not thereby
been proven to have a *sufficient* focus indicator, and a page containing an `aria-live` region
has not thereby been proven to *announce* anything into it — those are the judgment halves, and
they stay with the agent. A missing measurement, a malformed one, or one that does not prove a
failure all produce nothing at all, and the agent's verdict stands untouched.
"""
from __future__ import annotations

from integrations.types import A11yRuleFailure

#: The checks that have a measurable half, and the criterion each measures.
FOCUS_VISIBLE = "focus_visible"      # 2.4.7
STATUS = "status"                    # 4.1.3
MEASURED_CHECKERS = {FOCUS_VISIBLE: "2.4.7", STATUS: "4.1.3"}

#: Rule ids for what this module proves. Namespaced so a reader of the defect can see at a glance
#: that this did not come from axe — the ticket prints the rule id, and a made-up axe-shaped id
#: would send a developer looking for a rule that does not exist.
RULE_OUTLINE_SUPPRESSED = "a11y-journey/focus-indicator-suppressed"
RULE_NO_LIVE_REGION = "a11y-journey/no-live-region"

#: The exact snippet the agent runs while the element is focused. Prescribed rather than described
#: so two runs of the same journey read the same values — a probe the agent composes itself is a
#: different probe every time, and nothing could be compared across runs.
FOCUS_INDICATOR_PROBE = (
    "(() => { const el = document.activeElement; if (!el) return null; "
    "const s = getComputedStyle(el); return {outline_style: s.outlineStyle, "
    "outline_width: s.outlineWidth, box_shadow: s.boxShadow}; })()"
)
LIVE_REGION_PROBE = (
    "(() => ({live_region_count: document.querySelectorAll("
    "'[aria-live], [role=status], [role=alert], [role=log], output').length}))()"
)

#: What the reading proved, written for the developer who gets the ticket.
EVIDENCE_OUTLINE = (
    "With this element focused, the browser reported outline-style `{outline_style}` and "
    "outline-width `{outline_width}` with no box-shadow — the focus outline is switched off and "
    "nothing was drawn in its place, so there is no focus indicator to see."
)
EVIDENCE_NO_LIVE_REGION = (
    "This screen contains no live region at all: no element with `aria-live`, and none with "
    "role `status`, `alert` or `log`. A status message here cannot be announced to a screen "
    "reader user, because there is nowhere for it to be announced from."
)

#: Outline widths that mean "no outline". A blank or absent value is deliberately NOT in here:
#: "the agent did not report a width" and "the width is zero" are different facts, and only the
#: second one proves anything.
_NO_WIDTH = {"0", "0px", "0em", "0rem", "0%"}


def _text(value) -> str:
    return str(value or "").strip().lower()


def _outline_is_off(measurement: dict) -> bool:
    """Whether the browser reported no outline. Either half proves it — `outline-style: none`
    is the common way, and `outline-width: 0` is the other, and a page can use either."""
    if _text(measurement.get("outline_style")) in {"none", "hidden"}:
        return True
    return _text(measurement.get("outline_width")) in _NO_WIDTH


def focus_indicator_failure(*, route: str, selector: str,
                            measurement: dict | None) -> A11yRuleFailure | None:
    """2.4.7 — the outline is off and nothing replaced it.

    **Deliberately narrow, and the narrowness is the point.** This fires only for the
    unambiguous case: the author switched the outline off and drew no box-shadow. A page that
    indicates focus with a border, a background change or an underline produces *no* failure
    here and the agent's own judgment stands — which is the correct outcome, because a single
    computed style read while the element is focused cannot tell a focus border from a border
    the element always had. Over-firing would be worse than not firing: it would turn a
    perfectly good custom focus style into a Level AA defect a team cannot argue with.
    """
    if not isinstance(measurement, dict):
        return None
    if not _outline_is_off(measurement):
        return None
    # A shadow is how nearly every design system replaces the outline it removed. `none` is the
    # only value that proves nothing was drawn; anything else, including a value we cannot
    # parse, means something is there and this rule stays out of it.
    if "box_shadow" not in measurement or _text(measurement.get("box_shadow")) != "none":
        return None
    return A11yRuleFailure(
        criterion="2.4.7", selector=selector, route=route, rule_id=RULE_OUTLINE_SUPPRESSED,
        evidence=EVIDENCE_OUTLINE.format(
            outline_style=measurement.get("outline_style") or "(not reported)",
            outline_width=measurement.get("outline_width") or "(not reported)"),
    )


def live_region_failure(*, route: str, selector: str,
                        measurement: dict | None) -> A11yRuleFailure | None:
    """4.1.3 — there is no live region on the screen, so nothing can be announced.

    Counts, not judges. A screen with zero live regions cannot announce a status message under
    any reading of the criterion, and that is a fact rather than an opinion. A screen *with* one
    proves nothing at all — whether the right text reaches it at the right moment is the whole
    judgment, and it stays with the agent.
    """
    if not isinstance(measurement, dict) or "live_region_count" not in measurement:
        return None
    try:
        count = int(measurement["live_region_count"])
    except (TypeError, ValueError):
        # A count we cannot read is not a count of zero. Silence, not a failure.
        return None
    if count != 0:
        return None
    return A11yRuleFailure(
        criterion="4.1.3", selector=selector, route=route, rule_id=RULE_NO_LIVE_REGION,
        evidence=EVIDENCE_NO_LIVE_REGION,
    )


def rule_failures_for(*, checker: str, route: str, selector: str,
                      measurement: dict | None) -> tuple[A11yRuleFailure, ...]:
    """What this reading proves, if anything, for this check.

    Returns a tuple — `triage()` refuses a one-shot iterator, and for a good reason (a drained
    generator would silently switch the override off), so this hands back something re-readable
    by construction rather than by discipline.

    A measurement is only ever applied to the check it belongs to. A `live_region_count` sent
    alongside a `focus_visible` verdict proves nothing about 2.4.7 and is ignored, rather than
    being stretched to cover a criterion it does not measure.
    """
    if checker == FOCUS_VISIBLE:
        found = focus_indicator_failure(route=route, selector=selector, measurement=measurement)
    elif checker == STATUS:
        found = live_region_failure(route=route, selector=selector, measurement=measurement)
    else:
        return ()
    return (found,) if found is not None else ()
