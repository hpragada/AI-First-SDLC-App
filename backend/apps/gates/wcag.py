"""WCAG 2.2 AA design-gate checklist — derived from the loaded standard (PG21 / D6 · QA-11).

The accessibility gate is **not** a prompt rule and **not** an engine hook (#2): it is a
checklist attached to the design-phase `Approval`. A required criterion the reviewer has not
marked satisfied **blocks approval** — the design cannot be gated past until a11y is met.

**What QA-11 changed.** The list used to be nine criteria typed by hand against WCAG 2.1
(W3C, 2018). It is now built from the 2.2 standard the platform actually loaded (QA-04): the
numbers below choose *which questions to ask*, and each criterion's own number, title and
level are read from the loaded rows. A future release of the standard is therefore a data
reload, not an edit here — which is the whole reason QA-04 stored the standard as data.

**Which criteria (D-A11Y-7, team decision 2026-08-14).** The task text said "the human-owned
criteria" — the 30 the QA-05 registry records a *person* as deciding. Built literally that
asks a designer thirty questions, nine of which are about video that has not been filmed and
behaviour that has not been built, and it drops contrast and alt text, because a rule or the
AI is recorded as deciding those. But those automatic checks run on the **built page**, weeks
after this gate, and a checklist nobody can answer honestly gets ticked without being read.

So this list answers a deliberately different question from the registry's. The registry asks
*"who decides this criterion in a test run?"*; this asks *"what can a person settle by
looking at the design?"*. The two are related but not the same, and conflating them is what
produced the thirty-question list.

**Nothing is silently left out.** Every one of the 55 Level A/AA criteria is either asked
here or recorded in `NOT_ASKED` with the reason it is not; `verify_complete()` proves there is
no third category, and `explain()` answers "why isn't X on this list?" for any criterion. Two
of the old nine leave the checklist and both are named there: 1.4.4 Resize Text (measured by
zooming the built page) and 4.1.2 Name, Role, Value (a drawing cannot expose a name or a role
to assistive technology — it is one of the AI pass's own POC checks).
"""
from __future__ import annotations

from dataclasses import dataclass

from apps.a11y.wcag import DEFAULT_VERSION, WcagNotLoaded


class ChecklistGap(RuntimeError):
    """A criterion is neither asked at the design gate nor recorded as deliberately not asked.

    Raised rather than tolerated: a criterion that falls through both lists is one nobody
    decided about, and it would disappear from the gate without anyone choosing that.
    """


@dataclass(frozen=True)
class DesignCheck:
    """One question the designer answers, as a reviewable record rather than a bare string.

    `question` is the wording the reviewer reads; `why` is the reason it belongs at design
    time rather than after the build. `describe_checklist()` prints both, which is how this
    set gets reviewed by someone who does not read Python.
    """

    number: str
    question: str
    why: str


#: The questions a designer can settle from the design itself. Numeric order — the order of
#: the standard, and the order the old hand-typed list used.
DESIGN_CHECKS: tuple[DesignCheck, ...] = (
    DesignCheck(
        "1.1.1",
        "every image has intended alt text, or is deliberately marked decorative",
        "the designer is the one who knows what an image is for; nobody can recover that "
        "intent from the built page afterwards",
    ),
    DesignCheck(
        "1.4.1",
        "no status or meaning is carried by colour alone",
        "whether a red dot means anything is a design decision, and the second cue has to be "
        "drawn before it can be built",
    ),
    DesignCheck(
        "1.4.3",
        "text contrast is at least 4.5:1, or 3:1 for large text",
        "contrast comes out of the palette, so it is settled in the design system — the rule "
        "scanner only confirms it weeks later on the built page",
    ),
    DesignCheck(
        "1.4.11",
        "icons, borders and control edges have at least 3:1 contrast",
        "same decision as text contrast, on the parts of the design that are not text",
    ),
    DesignCheck(
        "1.4.13",
        "tooltips and pop-ups can be dismissed, and stay open while the pointer is on them",
        "how a hover panel behaves is specified in the design, not discovered in the code",
    ),
    DesignCheck(
        "2.1.1",
        "every action has a path without a mouse — nothing is hover-only or drag-only",
        "a design that offers an action only on hover cannot be made keyboard-operable later "
        "without redesigning it",
    ),
    DesignCheck(
        "2.2.2",
        "nothing auto-plays, auto-scrolls or animates without a way to stop it",
        "carousels and motion are put there by the design, so the pause control belongs there "
        "too",
    ),
    DesignCheck(
        "2.4.3",
        "the focus order follows the visual reading order",
        "the visual order *is* the design; a mismatch is created here and only detected later",
    ),
    DesignCheck(
        "2.4.5",
        "there is more than one way to reach a page — for example a menu and a search",
        "an information architecture decision, made once, at design time",
    ),
    DesignCheck(
        "2.4.6",
        "headings and labels describe what follows them",
        "the words are chosen in the design; renaming them after the build is a code change "
        "for a writing problem",
    ),
    DesignCheck(
        "2.4.7",
        "the design system defines a visible focus indicator",
        "if the design never draws a focus style, the build has nothing to implement",
    ),
    DesignCheck(
        "2.4.11",
        "a sticky header, footer or cookie bar never covers the item that has focus",
        "sticky regions are a layout decision, and this is the failure they cause",
    ),
    DesignCheck(
        "2.5.1",
        "nothing needs a multi-finger or path-based gesture with no simple alternative",
        "the gesture is invented in the design; the alternative has to be drawn beside it",
    ),
    DesignCheck(
        "2.5.7",
        "anything that is dragged can also be done with a single tap or click",
        "drag-and-drop is a design pattern, and the non-drag path is a design affordance",
    ),
    DesignCheck(
        "2.5.8",
        "tap targets are at least 24 by 24, or spaced far enough apart",
        "target size is a measurement of the design, available before any code exists",
    ),
    DesignCheck(
        "3.2.3",
        "navigation sits in the same place, in the same order, on every screen",
        "consistency across screens is visible only when the screens are seen together — "
        "which is the design review, not a per-page scan",
    ),
    DesignCheck(
        "3.2.6",
        "help sits in the same place on every screen that offers it",
        "same reason as navigation, and it is one of the rules WCAG 2.2 added",
    ),
    DesignCheck(
        "3.3.1",
        "every screen has an error state, and the error is described in words",
        "the platform already requires a designed error state per screen — this asks that the "
        "error is readable, not just red",
    ),
    DesignCheck(
        "3.3.2",
        "every field has a visible label — a placeholder standing in for one is not a label",
        "a form drawn with placeholders instead of labels produces exactly that in code",
    ),
    DesignCheck(
        "3.3.3",
        "an error message says how to fix the problem, not only that there is one",
        "the message text is written in the design",
    ),
    DesignCheck(
        "3.3.7",
        "the flow never asks for the same information twice",
        "a property of the flow the designer laid out; new in WCAG 2.2",
    ),
    DesignCheck(
        "3.3.8",
        "signing in never depends on remembering or transcribing something",
        "the sign-in journey is designed before it is built; new in WCAG 2.2",
    ),
)

#: The questions a project can **switch on** in its accessibility policy (QA-08). A designer can
#: answer all five; they are off by default for the reason `NOT_ASKED_REASONS` gives — a
#: twenty-eight-question checklist gets ticked in bulk rather than read. A project that wants a
#: stricter design gate turns them on in `ProjectProfile.a11y.gate.design_checks.extra_criteria`,
#: with no code change. They stay recorded in `NOT_ASKED` because "not asked" remains true of the
#: default gate, and `verify_complete()` still has to account for them either way.
OPTIONAL_DESIGN_CHECKS: tuple[DesignCheck, ...] = (
    DesignCheck(
        "2.2.1",
        "any time limit can be turned off, adjusted, or extended before it expires",
        "the timeout is invented in the design — a session warning or a countdown has to be "
        "drawn before it can be built, and adding the extend control afterwards is a redesign",
    ),
    DesignCheck(
        "2.3.1",
        "nothing flashes more than three times a second",
        "flashing is a property of the animation the design specifies, and this one can cause a "
        "seizure — it is the cheapest possible thing to catch at design time",
    ),
    DesignCheck(
        "2.5.4",
        "nothing is triggered only by tilting, shaking or moving the device",
        "a motion gesture is a design decision; the button that does the same thing has to be "
        "drawn beside it",
    ),
    DesignCheck(
        "3.2.4",
        "the same function is named and iconed the same way on every screen",
        "consistency across screens is visible only when the screens are seen together — the "
        "design review, not a per-page scan",
    ),
    DesignCheck(
        "3.3.4",
        "anything legal, financial or irreversible can be reviewed, corrected or undone",
        "whether a confirm step exists is a flow decision, made here; retrofitting one changes "
        "the journey",
    ),
)

#: Why each remaining criterion is not asked here, in plain words. Keyed by bucket so the
#: reason is written once and every criterion in it inherits the same, checkable claim.
NOT_ASKED_REASONS: dict[str, str] = {
    "checked_on_the_built_page": (
        "a rule scanner or the AI pass decides this on the built page and one of them is "
        "BUILT AND RUNNING today; the design cannot demonstrate it either way"
    ),
    "deferred_to_a_later_phase": (
        "the registry gives this to an engine that has not been built yet, so nothing checks it "
        "at any stage right now — it is left off the design list because it is a question about "
        "the built page rather than about a drawing, and it will be answered when that engine "
        "ships rather than by adding it here"
    ),
    "needs_media_that_does_not_exist_yet": (
        "it is a question about recorded audio or video, which is produced after the design — "
        "there is nothing yet to caption or describe"
    ),
    "only_visible_when_the_app_runs": (
        "you have to operate the built app to know: a drawing cannot show what happens on "
        "focus, on typing, or when a status message fires"
    ),
    "answerable_at_design_but_not_asked": (
        "a designer could answer it, and it is left off the default list to keep the list short "
        "enough to be read honestly rather than ticked in bulk; a project that wants it can "
        "switch it on in its accessibility policy (QA-08), and the question is written and "
        "waiting in OPTIONAL_DESIGN_CHECKS"
    ),
}

#: The other 33 criteria, each in exactly one bucket above. A criterion in no bucket and on no
#: check is a gap, and `verify_complete()` fails on it.
#:
#: **A bucket is a claim, and a claim can go stale.** `verify_complete()` proves every criterion
#: is in exactly one of them; it has never proved that the bucket's stated reason is TRUE. That
#: gap is what let 1.4.10 sit in `checked_on_the_built_page` for four tasks while nothing checked
#: it on the built page or anywhere else. `test_a11y_owner_capability` closes it by checking the
#: two machine buckets against the engines that exist.
NOT_ASKED: dict[str, tuple[str, ...]] = {
    # Something built and running answers each of these on the built page. Proven, not asserted:
    # `test_a11y_owner_capability` checks every number here against the engines that actually
    # exist. That assertion did not exist while this bucket was skipping 1.4.10 on the strength
    # of a scanner rule nobody had written, and it is the reason that cannot recur.
    #
    # 1.4.11 is deliberately NOT here even though the platform now measures it: it is asked of
    # the designer as well, because a palette that fails 3:1 is cheaper to change in the design
    # system than on every screen it was already used on.
    "checked_on_the_built_page": (
        "1.3.1", "1.3.4", "1.3.5", "1.4.2", "1.4.4", "1.4.10", "1.4.12", "2.4.1",
        "2.4.2", "2.4.4", "2.5.3", "3.1.1", "3.1.2", "4.1.2",
    ),
    # **Split out of the bucket above on 27 August, because that bucket's reason had become a
    # false statement about three of its members** (#3). It said a scanner or the AI pass decides
    # these on the built page. For 1.3.2 Meaningful Sequence, 1.3.3 Sensory Characteristics and
    # 1.4.5 Images of Text, the registry names an owner and defers the work to Phase 2 — so
    # nothing checks them at any stage today, and the design gate was skipping them on the
    # strength of a check that does not exist. That is the same shape of error as 1.4.10, caught
    # by looking for others of its kind rather than by waiting for one to surface.
    #
    # Less severe than 1.4.10 was, and the difference is worth keeping: these are honestly
    # recorded as `tier=phase_2`, so no report claims them as covered. 1.4.10 was recorded as
    # shipping in the POC.
    "deferred_to_a_later_phase": ("1.3.2", "1.3.3", "1.4.5"),
    "needs_media_that_does_not_exist_yet": ("1.2.1", "1.2.2", "1.2.3", "1.2.4", "1.2.5"),
    "only_visible_when_the_app_runs": (
        "2.1.2", "2.1.4", "2.5.2", "3.2.1", "3.2.2", "4.1.3",
    ),
    "answerable_at_design_but_not_asked": (
        "2.2.1", "2.3.1", "2.5.4", "3.2.4", "3.3.4",
    ),
}

#: Phases whose gate carries the WCAG checklist (the design review — 05 UX, gate role designer).
_WCAG_GATED_PHASES = {"ux_design"}

_CHECKS_BY_NUMBER: dict[str, DesignCheck] = {check.number: check for check in DESIGN_CHECKS}
_OPTIONAL_BY_NUMBER: dict[str, DesignCheck] = {c.number: c for c in OPTIONAL_DESIGN_CHECKS}


def _sort_key(check: DesignCheck) -> tuple[int, ...]:
    """Numeric order of the standard — so 2.4.11 follows 2.4.7 rather than preceding it."""
    return tuple(int(part) for part in check.number.split("."))


def _checks_for(extra) -> tuple[DesignCheck, ...]:
    """The default questions plus whichever optional ones this project switched on.

    An unknown number raises rather than being skipped: a project that believes it asks about
    flashing must not have that question silently dropped. The policy validator rejects these
    first, so reaching here means something wrote the profile without going through the API.
    """
    numbers = [str(n).strip() for n in (extra or []) if str(n).strip()]
    if unknown := sorted(set(numbers) - set(_OPTIONAL_BY_NUMBER)):
        raise ChecklistGap(
            f"the project's accessibility policy switches on design-gate questions that do not "
            f"exist: {', '.join(unknown)} — the optional ones are "
            f"{', '.join(sorted(_OPTIONAL_BY_NUMBER))}"
        )
    chosen = [_OPTIONAL_BY_NUMBER[n] for n in sorted(set(numbers))]
    return tuple(sorted(DESIGN_CHECKS + tuple(chosen), key=_sort_key))


def _bucket_of(number: str) -> str | None:
    for bucket, numbers in NOT_ASKED.items():
        if number in numbers:
            return bucket
    return None


def wcag_aa_checklist(*, version: str = DEFAULT_VERSION, extra=()) -> list[dict]:
    """A fresh WCAG 2.2 AA design checklist (all required, none yet satisfied).

    The wording of each item is assembled from the loaded standard, so the criterion's number,
    title and level are the published ones rather than a copy that can drift out of date.

    `extra` is the project's switched-on optional questions (QA-08); empty — the default —
    produces exactly the checklist this function produced before that policy existed.

    Raises `WcagNotLoaded` when the standard has not been loaded on this database, and
    `ChecklistGap` when a question here names a criterion the loaded standard does not have —
    both loudly, because a design gate that silently opens with a short checklist is a gate
    that approves designs nobody checked.
    """
    from apps.a11y.models import WcagCriterion

    checks = _checks_for(extra)
    asked = {check.number: check for check in checks}
    rows = {
        row.number: row
        for row in WcagCriterion.objects.filter(version=version, number__in=list(asked))
    }
    if not rows:
        raise WcagNotLoaded(
            f"no WCAG {version} criteria are loaded on this database, so the design gate "
            f"checklist cannot be built; run `python manage.py load_wcag` (as the migration "
            f"role)"
        )
    if missing := sorted(set(asked) - set(rows)):
        raise ChecklistGap(
            f"the design checklist asks about criteria the loaded WCAG {version} set does not "
            f"contain: {', '.join(missing)}. Either the standard moved or a question here has "
            f"a wrong number — decide which before this gate opens again."
        )

    return [
        {
            "key": check.number,
            "label": (
                f"{check.number} {rows[check.number].handle} · Level "
                f"{rows[check.number].level} — {check.question}"
            ),
            "required": True,
            "satisfied": False,
            "note": check.why,
        }
        for check in checks
    ]


def conditions_for_wcag_phase(phase: str, *, version: str = DEFAULT_VERSION,
                              extra=()) -> list[dict]:
    """The WCAG checklist for the design review (PG21), empty for every other phase.
    Composed with the other phases' conditions in `apps.gates.conditions`, which is where the
    project's policy is read and turned into `extra`."""
    return wcag_aa_checklist(version=version, extra=extra) if phase in _WCAG_GATED_PHASES else []


def explain(number: str) -> str:
    """Why this criterion is — or is not — a question at the design gate.

    Here so "why wasn't captions on the checklist?" has an answer that does not require
    reading this file, for a reviewer, an auditor, or the conformance report in E11.
    """
    if check := _CHECKS_BY_NUMBER.get(number):
        return f"asked at the design gate: {check.question} — {check.why}"
    if check := _OPTIONAL_BY_NUMBER.get(number):
        return (
            f"not asked at the design gate by default, but a project can switch it on in its "
            f"accessibility policy (QA-08), and it then asks: {check.question} — {check.why}"
        )
    if bucket := _bucket_of(number):
        return f"not asked at the design gate: {NOT_ASKED_REASONS[bucket]}"
    raise ChecklistGap(
        f"{number!r} is neither asked at the design gate nor recorded as deliberately not "
        f"asked — it is a gap, not an answer"
    )


def describe_checklist() -> str:
    """The whole set in plain words — what is asked, and what is not, with the reasons."""
    lines = [f"Asked at the design gate ({len(DESIGN_CHECKS)} criteria, WCAG 2.2 AA):"]
    lines.extend(f"  {c.number}  {c.question}\n        why: {c.why}" for c in DESIGN_CHECKS)
    lines.append(
        f"Available to switch on per project ({len(OPTIONAL_DESIGN_CHECKS)} criteria, "
        f"accessibility policy):"
    )
    lines.extend(
        f"  {c.number}  {c.question}\n        why: {c.why}" for c in OPTIONAL_DESIGN_CHECKS
    )
    for bucket, numbers in NOT_ASKED.items():
        lines.append(f"Not asked — {NOT_ASKED_REASONS[bucket]}:")
        lines.append(f"  {', '.join(numbers)}")
    return "\n".join(lines)


def verify_complete(*, version: str = DEFAULT_VERSION) -> int:
    """Every loaded criterion is either asked here or recorded as not asked. Returns the count.

    Checks the **database**, not just the lists in this file: a criterion the standard has and
    this module has never heard of is one that would vanish from the design gate without
    anyone deciding it should. Mirrors `apps.a11y.ownership.verify_complete`, for the same
    reason and with the same bias — loud rather than tidy.
    """
    from apps.a11y.models import WcagCriterion

    loaded = set(
        WcagCriterion.objects.filter(version=version).values_list("number", flat=True)
    )
    if not loaded:
        raise WcagNotLoaded(
            f"no WCAG {version} criteria are loaded, so the design checklist cannot be "
            f"verified; run `python manage.py load_wcag` first"
        )
    accounted = set(_CHECKS_BY_NUMBER) | {n for ns in NOT_ASKED.values() for n in ns}
    if unaccounted := sorted(loaded - accounted):
        raise ChecklistGap(
            f"{len(unaccounted)} WCAG {version} criteria are neither asked at the design gate "
            f"nor recorded as deliberately not asked: {', '.join(unaccounted)}"
        )
    if stale := sorted(accounted - loaded):
        raise ChecklistGap(
            f"this module names criteria the loaded WCAG {version} set does not contain: "
            f"{', '.join(stale)}"
        )
    return len(loaded)
