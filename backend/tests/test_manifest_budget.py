"""The model-derived manifest budget, and the promise that nothing it touches got smaller.

Background. Every phase run hands its agent one composed document — the manifest. Each section had
a FIXED token cap, written on 2026-06-22 against an assumed 200k context window, and anything past
the cap was deleted before the agent ever saw it. The lowest model in use today carries ~1M, and a
real manifest measures 5,353 tokens — half a percent of it. We were destroying content an agent
needed to protect a budget that had not been scarce for months.

The caps now become FLOORS and the total is derived from the dispatched model's window. Two tests
in this file carry the whole safety argument:

  * `test_the_manifest_is_byte_identical_when_no_budget_is_supplied` — the golden set. No existing
    caller passes `total_budget`, so `None` must render exactly what it rendered before. This is
    what makes a change across ten renderers safe to ship in one commit.
  * `test_a_section_is_never_allocated_less_than_its_floor` — the property test. The one outcome
    that must be impossible is a manifest SMALLER than today's for some input nobody thought of.
"""
from __future__ import annotations

import os
import random
from pathlib import Path

import pytest

from manifest import compose_manifest
from manifest.budget import (
    FALLBACK_WINDOW,
    MAX_BUDGET,
    MAX_CHUNKS,
    MIN_CHUNKS,
    MIN_PR_FILE_CHARS,
    chunks_for_budget,
    pr_file_chars,
    review_direction_tokens,
    total_for_model,
)
from manifest.composer import allocate
from tests.manifest_fixtures import CASES

GOLDEN_DIR = Path(__file__).parent / "golden" / "manifest"
_UPDATING = os.environ.get("UPDATE_MANIFEST_GOLDENS") == "1"


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_manifest_is_byte_identical_when_no_budget_is_supplied(name):
    """`total_budget=None` renders what the composer rendered before the budget existed.

    The goldens include the cases that TRUNCATE — eight knowledge chunks over the cap, thirty
    artifacts, five review rounds — on purpose. A refactor that splits every renderer in two shows
    up first in the shape of a cut, not in the happy path, and a golden set made only of tidy
    inputs would have waved it through.
    """
    produced = compose_manifest(**CASES[name])
    path = GOLDEN_DIR / f"{name}.md"
    if _UPDATING:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(produced, encoding="utf-8")
        pytest.skip(f"golden rewritten: {path.name}")
    assert path.exists(), (
        f"no golden for '{name}' — run UPDATE_MANIFEST_GOLDENS=1 pytest {Path(__file__).name}"
    )
    assert produced == path.read_text(encoding="utf-8")


# ── the allocator ───────────────────────────────────────────────────
# `allocate` is pure, so it is tested directly rather than through a composed manifest. The two
# properties below are the ones that make the whole change safe to ship; everything else is
# detail.

_FLOORS = {
    "rules": 3000, "project": 2000, "important_context": 2000, "review_direction": 3000,
    "current_work_item": 650, "answered_clarifications": 1200, "relevant_artifacts": 1200,
    "recent_events": 600, "retrieved_knowledge": 1500,
}


def _demands(**over) -> dict[str, int]:
    d = {k: 10 for k in _FLOORS}        # everything tiny unless a test says otherwise
    d.update(over)
    return d


@pytest.mark.parametrize("total", [None, 0, -1, 1, 10, 5_000, 10_000, 15_150, 50_000, 60_000])
def test_a_section_is_never_allocated_less_than_its_floor(total):
    """The one outcome that must be impossible: a manifest SMALLER than today's.

    Every cap in `TokenBudget` became a floor, and the promise made to the team was "never worse
    than today, on any input". A plausible implementation gets this wrong by asserting the
    tempting invariant `sum(allowance) <= total` — which is FALSE here, because a section that
    needs 31 tokens keeps its 2,000 floor while only reserving 31. Someone then "fixes" the
    failing assert by clamping, and sections start coming back below their floor on exactly the
    inputs nobody tried by hand. Hence 0, negative, and a total far below the floors' sum.
    """
    allowances = allocate(total, _FLOORS, _demands(retrieved_knowledge=99_999))
    for section, floor in _FLOORS.items():
        assert allowances[section] >= floor, f"{section} fell below its floor"


def test_the_allocation_does_not_depend_on_the_order_it_was_handed():
    """Shuffling the input must not change a single number.

    Determinism is not decoration here: the allocation decides what an agent reads, so the same
    run composed twice has to brief it identically. Dict iteration order and float arithmetic are
    the two usual ways that quietly stops being true.
    """
    demands = _demands(relevant_artifacts=9_000, recent_events=4_000, retrieved_knowledge=7_000)
    baseline = allocate(50_000, _FLOORS, demands)
    rng = random.Random(7)
    for _ in range(25):
        keys = list(_FLOORS)
        rng.shuffle(keys)
        shuffled_floors = {k: _FLOORS[k] for k in keys}
        shuffled_demands = {k: demands[k] for k in keys}
        assert allocate(50_000, shuffled_floors, shuffled_demands) == baseline


def test_the_allocator_uses_integer_arithmetic_only():
    """Read as source, because a float that only shows up on one project is not findable later.

    Proportional sharing is where a `/` creeps in, and float division makes the result depend on
    rounding the reader cannot see — two sections swapping a token between runs for no reason
    anybody could explain.
    """
    import inspect

    from manifest import composer

    body = inspect.getsource(composer.allocate)
    assert "//" in body, "the proportional share should be integer division"
    code = body.replace("//", "")
    assert "/" not in code, "allocate must not use floating-point division"
    assert "float(" not in body


def test_no_budget_at_all_means_exactly_the_caps_the_platform_always_had():
    """`total=None` is the path every caller outside the orchestrator takes."""
    assert allocate(None, _FLOORS, _demands(project=999_999)) == _FLOORS


def test_when_every_section_is_already_full_a_small_budget_changes_nothing():
    """Sections that genuinely fill their floors leave no spare, and nothing moves.

    Note what this does NOT say. Reserving a section's WHOLE floor regardless of need would make
    the fallback budget (10,000) smaller than the floors' sum (15,150), so spare would always be
    zero and an unrecognised model could never improve on today — the arithmetic flaw found while
    designing this. Charging `min(floor, demand)` is what fixes it, which is why the sibling test
    below shows a *small* budget still helping when the other sections are nearly empty.
    """
    full = {k: v for k, v in _FLOORS.items()}
    assert allocate(5_000, _FLOORS, full) == _FLOORS


def test_even_the_fallback_budget_helps_when_its_neighbours_are_nearly_empty():
    """The fallback path still fixes the live failure, which is the point of charging by need.

    On the measured run the sections together needed 5,351 tokens, so even the 10,000 an
    unrecognised model is given leaves 4,649 of spare — enough for the one section that was
    1,000 short. Reserved-by-floor would have left exactly nothing.
    """
    demands = _demands(project=31, important_context=7, current_work_item=366,
                       relevant_artifacts=997, recent_events=443,
                       retrieved_knowledge=2_478, rules=2_028)
    allowances = allocate(10_000, _FLOORS, demands)
    assert allowances["retrieved_knowledge"] >= 2_478


def test_the_section_that_is_short_gets_the_headroom_its_neighbours_are_not_using():
    """The measured failure, in one test.

    On live run `6a7ae08e` the sections held 31 / 7 / 366 / 997 / 443 / 1,479 / 2,028 tokens
    against caps of 2,000 / 2,000 / 650 / 1,200 / 600 / 1,500 / 3,000. Retrieved knowledge was cut
    while **5,597 tokens sat idle beside it** in sections needing a fraction of their allowance.
    """
    demands = _demands(project=31, important_context=7, current_work_item=366,
                       relevant_artifacts=997, recent_events=443,
                       retrieved_knowledge=2_478, rules=2_028)
    allowances = allocate(50_000, _FLOORS, demands)
    assert allowances["retrieved_knowledge"] >= 2_478, "the short section is still short"


def test_a_greedy_grower_cannot_starve_the_rules():
    """`# Rules` is the only section with NO recovery path — no tool returns it.

    So it is satisfied before any grower is considered. Without the priority tiers, a project with
    thousands of events would take the spare proportionally and the rules would be cut on every
    run of every phase, unrecoverably, because of a project's age.
    """
    demands = _demands(rules=5_000, relevant_artifacts=500_000, recent_events=500_000,
                       retrieved_knowledge=500_000, answered_clarifications=500_000)
    allowances = allocate(20_000, _FLOORS, demands)
    assert allowances["rules"] >= 5_000


def test_the_work_item_metadata_stays_non_elastic():
    """Only the work item's DESCRIPTION is exempt from its cap, and that is deliberate (T2).

    The metadata lines are bounded and repetitive, so a runaway title must still be cut visibly
    rather than quietly handed ten thousand tokens — which would also delete the guarantee
    `test_the_metadata_lines_still_obey_the_cap` exists to make.
    """
    allowances = allocate(60_000, _FLOORS, _demands(current_work_item=40_000))
    assert allowances["current_work_item"] == _FLOORS["current_work_item"]


def test_nothing_is_allocated_to_a_section_that_is_not_present():
    """A repo-less run has no `# Repository`; a phase nobody sent back has no direction.

    The present-set is computed from what actually rendered, so a floor for an absent section must
    never be reserved — that is the arithmetic that would silently shrink everyone else's share.
    """
    present = {k: _FLOORS[k] for k in ("rules", "project", "retrieved_knowledge")}
    allowances = allocate(50_000, present, _demands(retrieved_knowledge=9_000))
    assert set(allowances) == set(present)


# ── the budget derived from the model ───────────────────────────────

def test_the_model_in_production_gets_a_budget_nothing_can_overflow():
    """`claude-sonnet-4-6` is `DEFAULT_MODEL`, so this is what every run gets today.

    The whole manifest with every section simultaneously at its floor is 15,150 tokens. Three
    times that is the point of the exercise: not "a bigger cap" but a budget under which the
    question of cutting does not arise.
    """
    total, used_fallback = total_for_model("claude-sonnet-4-6")
    assert (total, used_fallback) == (50_000, False)
    assert total > 15_150 * 3


def test_a_dated_or_regional_model_id_resolves_to_its_family():
    """Nobody should have to add a row every time a model gains a date suffix or a cloud prefix."""
    for model in ("claude-sonnet-4-6-20260115", "claude-sonnet-4-6@20260115"):
        assert total_for_model(model) == (50_000, False)


@pytest.mark.parametrize("model", ["", "   ", "gpt-9", "claude-something-unreleased", None])
def test_an_unfamiliar_model_falls_back_to_the_assumption_every_cap_was_built_on(model):
    """200,000 is not a guess — it is the window the original caps were sized against in June.

    So an unrecognised engine reproduces the platform's long-standing behaviour exactly, rather
    than inventing a number. It is flagged, never silent: the caller logs an event, because the
    first anyone should learn that a model needs adding is from the console, not from a client
    asking why their agents seem less informed.
    """
    total, used_fallback = total_for_model(model)
    assert used_fallback is True
    assert total == FALLBACK_WINDOW // 20


def test_a_very_large_window_still_stops_at_the_ceiling():
    """"Nothing is lost" and "use the whole window" are different goals, and only the first is
    worth having. A huge briefing costs latency and attention on every dispatch — seven of them
    in one remediation loop — for headroom there is no evidence of needing."""
    from manifest import budget as budget_mod

    original = dict(budget_mod.CONTEXT_WINDOWS)
    budget_mod.CONTEXT_WINDOWS["test-enormous"] = 10_000_000
    try:
        assert total_for_model("test-enormous") == (MAX_BUDGET, False)
    finally:
        budget_mod.CONTEXT_WINDOWS.clear()
        budget_mod.CONTEXT_WINDOWS.update(original)


def test_retrieval_fetches_more_when_there_is_room_and_never_fewer_than_before():
    """Eight chunks was the old hardcoded number; it is now the floor, not the rule.

    The failure this replaces: retrieval ranked eight chunks (~2,400 tokens), the composer kept
    1,500, and the rest was binned — a third of the work thrown away on every dispatch, with one
    chunk cut mid-sentence. The cure is to stop fetching what we were about to discard.
    """
    assert chunks_for_budget(None) == MIN_CHUNKS
    assert chunks_for_budget(10_000) == MIN_CHUNKS          # fallback budget: unchanged
    assert chunks_for_budget(50_000) > MIN_CHUNKS           # production: more context
    assert chunks_for_budget(10_000_000) == MAX_CHUNKS      # ranked best-first; the tail is noise
    for total in (None, 0, 1, 10_000, 50_000, 60_000):
        assert MIN_CHUNKS <= chunks_for_budget(total) <= MAX_CHUNKS


def test_a_review_never_sees_less_of_a_file_than_it_used_to():
    """The per-file window grows with the model but can never shrink.

    A budget-derived number coming out below 16,000 would mean this change had made a code review
    read LESS of the code than before — the one direction it must never move.
    """
    assert pr_file_chars(None) == MIN_PR_FILE_CHARS
    assert pr_file_chars(10_000) == MIN_PR_FILE_CHARS
    assert pr_file_chars(50_000) > MIN_PR_FILE_CHARS
    for total in (None, 0, 1, 5_000, 10_000, 50_000, 60_000):
        assert pr_file_chars(total) >= MIN_PR_FILE_CHARS


def test_the_reviewers_own_words_grow_with_the_model_too():
    """A reviewer-revision build renders this section itself, outside the composer.

    It passed a bare default, so while every other path went elastic, the one section carrying
    what a human had just typed stayed pinned at 3,000 forever — on the single path whose entire
    purpose is to deliver it.
    """
    floor = 3000
    assert review_direction_tokens(None, floor) == floor
    assert review_direction_tokens(10_000, floor) == floor      # fallback: unchanged
    assert review_direction_tokens(50_000, floor) > floor       # production: room to grow
    for total in (None, 0, 1, 10_000, 50_000, 60_000):
        assert review_direction_tokens(total, floor) >= floor


# ── the composer, end to end ────────────────────────────────────────

def test_nothing_retrieved_is_ever_discarded():
    """The headline. Eight chunks in, eight chunks rendered, no truncation marker.

    This is the exact shape QA saw: `Manifest truncated` on almost every phase, seven times in a
    single run, alternating implementation and code_review. The cause was arithmetic, not an edge
    case — retrieval fetched eight chunks of ~1,200 characters (~2,400 tokens) into a section
    capped at 1,500, so roughly a third went in the bin every single dispatch and one chunk was
    cut mid-sentence. The same input now renders whole.
    """
    from manifest.composer import TRUNCATION_MARKER

    produced = compose_manifest(total_budget=50_000, **CASES["knowledge_over_cap"])
    section = produced.split("# Retrieved Knowledge")[1].split("# Rules")[0]
    assert len([ln for ln in section.splitlines() if ln.startswith("- ")]) == 8
    assert TRUNCATION_MARKER not in section


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_budget_never_removes_anything_the_old_caps_kept(name):
    """Every section is at least as long with a budget as without one, for every fixture.

    The golden test pins `total_budget=None`; this pins the other direction. Together they say
    the change can only ever add. A single section coming back shorter would mean the allocator
    had handed something less than its floor, which is the one failure mode that matters.
    """
    without = compose_manifest(**CASES[name])
    with_budget = compose_manifest(total_budget=50_000, **CASES[name])
    for header in [ln for ln in without.splitlines() if ln.startswith("# ")]:
        assert header in with_budget, f"{name}: {header} disappeared"
    assert len(with_budget) >= len(without), name


def test_the_report_says_what_each_section_was_allowed_and_what_it_asked_for():
    """With a fixed cap, naming the cut section was enough. With an allowance that moves, it is
    not: "Retrieved Knowledge was shortened" no longer distinguishes a starved section from an
    enormous one, and that difference is the whole of what anyone tuning this needs."""
    from manifest.composer import compose_manifest_with_report

    _, report = compose_manifest_with_report(total_budget=50_000, **CASES["knowledge_over_cap"])
    assert report["retrieved_knowledge"]["allowance"] >= report["retrieved_knowledge"]["demand"]
    assert set(report) >= {"project", "rules", "retrieved_knowledge", "current_work_item"}


def test_the_repository_sections_do_not_double_count_the_project_floor():
    """`# Project` and `# Repository` share one cap, as they always have.

    Counted as two entries, the floors' sum would be 2,000 higher than it really is and every
    other section's share would quietly shrink — a bug that only shows on multi-repo projects,
    which is to say on exactly the clients least able to spare the context.
    """
    from manifest.composer import compose_manifest_with_report

    for case in ("repo_scoped", "multi_repo_project_level"):
        _, report = compose_manifest_with_report(total_budget=50_000, **CASES[case])
        assert "project" in report
        assert len([k for k in report if k == "project"]) == 1
