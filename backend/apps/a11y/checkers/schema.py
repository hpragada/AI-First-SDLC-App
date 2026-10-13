"""What a complete answer from each checker has to contain (QA-03).

`record_a11y_finding` already enforces the things that are true of *every* judgment: a real
verdict, a confidence that is a probability, evidence behind anything that is not a pass, and
only criteria the element was actually queued against. This module adds the part that differs
per checker — the one or two facts that turn "this is broken" into something a developer can
act on without going and looking for themselves.

**How strict, and why** (team decision D-A11Y-5, 2026-08-14): reject only what makes a failure
*unusable*. Every rejection costs the judge a round trip, and a requirement it has no way to
satisfy would strand an element instead of letting it fall to human review. So:

  * it applies to `fail` only. An `uncertain` verdict is the judge saying it could not see
    enough to answer — demanding a fix from it would be demanding the answer it just said it
    did not have, and the element is going to a person anyway.
  * `semantics` adds nothing. "Which of 1.3.1 / 4.1.2 broke" is already enforced, because
    `record_finding` requires the criteria and rejects any the element was not queued for, and
    evidence is already required for every failure. A second rule there would be ceremony.

The exceptions raised are `ValueError`s on purpose: `RunnerStateView` turns those into a 400
carrying the message, not a 500. An agent reading "500" concludes the platform is broken and
repeats the identical call; one reading "name the replacement alt text" fixes it and moves on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: Quoted spans in the evidence. Deliberately generous — straight, curly and back quotes all
#: count — because this exists to check that two strings were *named*, not to police typography.
_QUOTED = re.compile(r"""["'“”‘’`]([^"'“”‘’`]+)["'“”‘’`]""")


class AnswerIncomplete(ValueError):
    """A failure was reported without the one thing that makes it actionable.

    A `ValueError` so the transport returns it as a 400 with the message intact — see the
    module docstring. Distinct type so a caller (and a test) can tell "the judge left something
    out" apart from "the judge said something invalid".
    """


@dataclass(frozen=True)
class AnswerRequirement:
    """One checker's extra requirement on a `fail`, and how to explain it when it is missing."""

    checker: str
    needs: str                   # what a reviewer would say is missing, in plain words
    message: str                 # what the judge is told, including how to fix the call

    def check(self, *, evidence: str, suggested_fix: str) -> None:
        raise NotImplementedError                     # pragma: no cover - abstract


@dataclass(frozen=True)
class _NeedsFix(AnswerRequirement):
    """The failure is only actionable if it says what to put there instead."""

    def check(self, *, evidence: str, suggested_fix: str) -> None:
        if not suggested_fix.strip():
            raise AnswerIncomplete(self.message)


@dataclass(frozen=True)
class _NeedsTwoQuotedStrings(AnswerRequirement):
    """The failure is a mismatch between two strings, so it has to name both of them."""

    def check(self, *, evidence: str, suggested_fix: str) -> None:
        quoted = {match.strip() for match in _QUOTED.findall(evidence) if match.strip()}
        if len(quoted) < 2:
            raise AnswerIncomplete(self.message)


#: checker -> what a `fail` from it must also carry. A checker absent from this map has no
#: extra requirement, which is a deliberate answer and not an omission (see `semantics`).
REQUIREMENTS: dict[str, AnswerRequirement] = {
    "alt": _NeedsFix(
        checker="alt",
        needs="the alternative text to use instead",
        message=(
            "a failing `alt` finding must supply the replacement alt text in suggested_fix — "
            "knowing the current alt is wrong does not tell a developer what to write, and "
            "proposing the alternative is the whole reason this check is done by AI. Give the "
            "text itself, e.g. suggested_fix='Chart: revenue grew from £1.2m to £3.4m in 2025'"
        ),
    ),
    "structure": _NeedsFix(
        checker="structure",
        needs="the markup that is missing",
        message=(
            "a failing `structure` finding must say what markup to add in suggested_fix — "
            "1.3.1 is breached because the arrangement is visible and not written down, so the "
            "finding is not complete until it names what to write. e.g. suggested_fix='make "
            "the first row header cells: <th scope=\'col\'>Subject</th>' or 'wrap the three "
            "delivery options in a <fieldset> with <legend>Delivery</legend>'"
        ),
    ),
    "color": _NeedsFix(
        checker="color",
        needs="the second visual cue that is missing",
        message=(
            "a failing `color` finding must name the missing second cue in suggested_fix — "
            "1.4.1 is breached only because colour is the *only* visual means, so the finding "
            "is not complete until it says what else to show. e.g. suggested_fix='add the word "
            "Overdue next to the red dot' or 'underline links inside body text'"
        ),
    ),
    "graphics": _NeedsFix(
        checker="graphics",
        needs="which part of the graphic is too faint, and what to change",
        message=(
            "a failing `graphics` finding must say what to change in suggested_fix — 1.4.11 is "
            "breached by a specific part of the picture being too faint against a specific "
            "background, and 'the icon has low contrast' tells a designer nothing about which "
            "part or how much. Name the part and the target. e.g. suggested_fix='darken the "
            "warning triangle's outline from #d9d9d9 to at least #767676 so it reaches 3:1 "
            "against the white card behind it'"
        ),
    ),
    "label": _NeedsTwoQuotedStrings(
        checker="label",
        needs="both strings — the visible label and the accessible name",
        message=(
            "a failing `label` finding must quote BOTH strings in evidence — the visible label "
            "and the accessible name it disagrees with. One of them alone is not a mismatch "
            "anyone can check. e.g. evidence='visible label \"Buy now\", accessible name "
            "\"Purchase\"'"
        ),
    ),
}


def requirements_for(checker: str) -> AnswerRequirement | None:
    """What a `fail` from this checker must carry beyond the universal rules, if anything."""
    return REQUIREMENTS.get(str(checker or "").strip().lower())


def verify_answer(*, checker: str, verdict: str, evidence: str = "",
                  suggested_fix: str = "") -> None:
    """Raise `AnswerIncomplete` if this failure is missing what makes it actionable.

    Silent for a `pass`, for an `uncertain`, and for any checker with no extra requirement.
    """
    if str(verdict or "").strip().lower() != "fail":
        return
    requirement = requirements_for(checker)
    if requirement is not None:
        requirement.check(evidence=str(evidence or ""), suggested_fix=str(suggested_fix or ""))
