"""A narrow rule pass may not claim conformance a narrow rule cannot prove (#6, QA-25).

**The bug this file exists to keep fixed, in one sentence.** axe ships `video-caption`, which
proves a `<video>` carries a caption *track*. That pass was recorded as coverage for 1.2.2
Captions (Prerecorded); no failure existed; `suggest` returned **"Supports"**; and a conformance
statement went out telling a buyer that a product's captions met Level A when nobody had watched
a second of the video.

Nothing was broken in isolation. The scanner reported honestly, coverage recorded honestly, and
`suggest` applied its documented rules. What was missing was the question *is this engine
entitled to settle this criterion?* — and `ownership.needs_human_always` and
`ownership.partially_flaggable`, which exist precisely to answer it and whose own docstring
promised a partial flag "never licenses reporting a pass", were imported by the test suite and by
nothing else in the platform.

No database: `suggest` is a pure function and this is the level the rule lives at.
"""
from __future__ import annotations

import pytest

from apps.a11y.conformance import (
    DOES_NOT,
    NOT_APPLICABLE,
    NOT_EVALUATED,
    PARTIALLY,
    SUPPORTS,
    suggest,
)


def cover(outcome="passed", engines=("rule",), routes=("/a",)):
    return {"routes": {route: outcome for route in routes}, "engines": set(engines)}


# ── the fifteen criteria a person must always settle ───────────────────────────────

@pytest.mark.parametrize("outcome", ["passed", "not_applicable"])
def test_a_criterion_a_person_must_always_settle_gets_no_positive_suggestion(outcome):
    """The exact 1.2.2 case. A caption TRACK existing is not captions being ACCURATE, and
    accuracy is the whole of what the criterion turns on."""
    assert suggest(cover(outcome), 0, owner="human", always_human=True) is None


def test_a_proven_failure_on_such_a_criterion_is_still_reported():
    """Only the positive direction is guarded. A rule scanner that catches a missing caption
    track has found a real Level A defect, and nothing here may soften it."""
    assert suggest(cover("failed"), 0, owner="human", always_human=True) == DOES_NOT
    assert suggest(cover("failed"), 2, owner="human", always_human=True) == DOES_NOT
    assert suggest({"routes": {"/a": "failed", "/b": "passed"}, "engines": {"rule"}},
                   0, owner="human", always_human=True) == PARTIALLY


# ── the engine that can decide it has to be the engine that looked ─────────────────

def test_a_scanner_pass_cannot_claim_a_criterion_the_ai_decides():
    """2.4.4 Link Purpose. axe's `link-name` proves a link has SOME accessible name; whether
    that name says where the link goes is the criterion, and only the AI judge asks it."""
    assert suggest(cover(engines=("rule",)), 0, owner="ai") is None


def test_the_same_criterion_is_claimable_once_its_own_judge_has_looked():
    assert suggest(cover(engines=("AI",)), 0, owner="ai") == SUPPORTS
    assert suggest(cover(engines=("rule", "AI")), 0, owner="ai") == SUPPORTS


def test_a_scanner_pass_cannot_claim_a_criterion_the_keyboard_walk_decides():
    """2.1.1 Keyboard. axe has three narrow rules for it; whether every function can actually be
    operated from a keyboard is answered by walking the app."""
    assert suggest(cover(engines=("rule",)), 0, owner="human") is None
    assert suggest(cover(engines=("agentic",)), 0, owner="human") == SUPPORTS


def test_a_rule_owned_criterion_is_claimable_from_the_scanner_alone():
    """The common, correct case: 1.4.3 Contrast is arithmetic and axe does the arithmetic."""
    assert suggest(cover(engines=("rule",)), 0, owner="rule") == SUPPORTS


def test_an_ai_pass_alone_cannot_claim_a_rule_owned_criterion_either():
    """The guard runs both ways. An AI opinion is not a measurement, and 1.4.3 is measured."""
    assert suggest(cover(engines=("AI",)), 0, owner="rule") is None


# ── failing safe ───────────────────────────────────────────────────────────────────

def test_an_unknown_owner_claims_nothing():
    """A registry that has grown a value this code has not heard of. The row goes to a
    reviewer and is counted in `awaiting_a_person`, which is visible and obviously wrong to
    whoever opens the statement — the safe direction for an omission to fail in."""
    assert suggest(cover(), 0, owner="something-new") is None


def test_a_caller_that_names_no_owner_makes_no_positive_claim():
    """Also what happens when the ownership registry was never loaded on a database."""
    assert suggest(cover(), 0) is None


def test_coverage_with_no_engines_recorded_claims_nothing():
    assert suggest({"routes": {"/a": "passed"}}, 0, owner="rule") is None


# ── the guard changes nothing about the answers that were already right ────────────

@pytest.mark.parametrize("cov,failures,expected", [
    (None, 0, NOT_EVALUATED),
    ({}, 0, NOT_EVALUATED),
    (cover("needs_human"), 0, None),
    (cover("not_checked"), 0, None),
    (cover("failed"), 0, DOES_NOT),
    (cover(), 3, PARTIALLY),
])
def test_every_other_route_through_suggest_is_untouched(cov, failures, expected):
    assert suggest(cov, failures, owner="rule") == expected


def test_not_applicable_still_reaches_a_criterion_whose_own_engine_ran():
    assert suggest(cover("not_applicable"), 0, owner="rule") == NOT_APPLICABLE
