"""QA-05 — the "who checks which criterion" registry.

What these prove, against the task's acceptance criteria:

  AC1  a criterion number returns its owner (rule/AI/human) and tier
  AC2  the loaded set is exactly 55, each with exactly one owner and one tier — no gaps,
       no duplicates — and a load that would leave a gap fails instead of half-applying
  AC3  the spot checks the task names: 1.4.3 = rule, 1.1.1 = AI, 1.2.2 = human
  AC4  the count and the spot checks are asserted, with ≥90% coverage on new code

Beyond the ACs, and deliberately:

  * the registry is **derived from the committed report and re-derivable**, so "does this
    still say what Addendum A says?" is a test rather than a code review — the build runs
    against the real PDF here, which QA-04's network-bound equivalent could not do
  * the completeness proof is shown to be **non-vacuous**: planting a dropped row and an
    invented word each fail the build
  * every one of the report's own cross-checks is exercised, including the ones that caught
    a four-row parser bug
  * decision D5 (2.4.6 is Phase 2) is guarded by name, so it cannot silently regress
  * **hybrids are queryable, not just readable** — 3.3.2 is rule-owned yet the AI judges part
    of it, and 1.2.2 is human-owned yet a rule can flag a missing caption track
  * **partial flagging never becomes a verdict** — the 6 flaggable criteria are all still
    human-decided, and the live checker map is pinned to the registry so the two cannot drift
  * **tier is not redundant with owner** — the 30 human-owned criteria split 15 / 15, and a
    report built on owner alone would double the manual burden it states
  * the registry is one platform-wide copy the app role cannot write, so "a tenant cannot
    decide a criterion needs less checking" is a database guarantee
"""
import copy
import json
import re

import psycopg
import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from apps.a11y import ownership_build as ob
from apps.a11y.management.commands.build_ownership_dataset import _drift
from apps.a11y.models import CriterionOwnership, Owner, Tier, WcagCriterion
from apps.a11y.ownership import (
    IncompleteOwnership,
    OwnershipNotLoaded,
    UnknownCriterion,
    UnpublishedRows,
    criteria_for,
    criteria_touched_by,
    dataset,
    is_in_poc,
    load_ownership,
    needs_human_always,
    ownership,
    partially_flaggable,
    verify_complete,
)
from apps.a11y.wcag import DEFAULT_VERSION, load_wcag

# The report's own enumerations, transcribed here a second time and independently of
# `ownership_build`, so a typo in one place cannot be validated by itself.
# Source: Report 1 — Addendum A §3.3 and §4.1.
RULE_PRIMARY_14 = [
    "1.3.4", "1.3.5", "1.4.2", "1.4.3", "1.4.4", "1.4.10", "1.4.11", "1.4.12",
    "2.4.1", "2.4.2", "2.5.8", "3.1.1", "3.1.2", "3.3.2",
]
AI_IN_POC_5 = ["1.1.1", "1.3.1", "1.4.1", "2.5.3", "4.1.2"]

# What the platform actually ROUTES, which is the report plus correction R14 and nothing else.
# Written as the report's list — one criterion rather than as a second hand-typed list, so the
# departure is one visible line and cannot quietly grow to two.
#
# R14 (agreed 2026-08-27): Addendum A gives 1.4.11 to `rule` and its own rationale in the same
# cell says why it should not — "computable, but 'which graphics matter' needs some review".
# The judged half decides, so the platform routes it to the AI and records the rule half as a
# secondary check. See `ownership.ENGINEERING_OVERRIDES` and RESEARCH_CORRECTIONS.md R14.
ROUTED_RULE_PRIMARY_13 = [c for c in RULE_PRIMARY_14 if c != "1.4.11"]
ROUTED_AI_IN_POC_6 = [*AI_IN_POC_5, "1.4.11"]
AI_PHASE_2_6 = ["1.3.2", "1.3.3", "1.4.5", "2.4.4", "2.4.6", "2.4.7"]
HUMAN_REACHED_BY_PHASE_2_15 = [
    "1.4.13", "2.1.1", "2.1.2", "2.2.2", "2.4.3", "2.4.11", "3.2.1", "3.2.2", "3.2.3",
    "3.2.4", "3.2.6", "3.3.1", "3.3.3", "3.3.8", "4.1.3",
]
HUMAN_ALWAYS_15 = [
    "1.2.1", "1.2.2", "1.2.3", "1.2.4", "1.2.5", "2.1.4", "2.2.1", "2.3.1", "2.4.5",
    "2.5.1", "2.5.2", "2.5.4", "2.5.7", "3.3.4", "3.3.7",
]


def numerically(numbers):
    return sorted(numbers, key=lambda n: [int(p) for p in n.split(".")])


@pytest.fixture
def loaded(db):
    """The registry, loaded — no tenant involved, which is the point.

    Migration `0007_criterion_ownership` loads it, so it is already present on a migrated
    database; calling it explicitly keeps these tests independent of that and exercises the
    reload path at the same time.
    """
    return load_ownership()


@pytest.fixture(scope="module")
def built():
    """The registry re-derived from the committed report — parsed once for the module."""
    return ob.build(log=lambda *a, **k: None)


# ── the committed dataset ────────────────────────────────────────────
def test_dataset_covers_exactly_the_55_criteria_of_the_standard():
    """The registry's numbers are the standard's numbers — not its own idea of them."""
    from apps.a11y.wcag import dataset as wcag_dataset

    assert [c["number"] for c in dataset()["criteria"]] == numerically(
        c["number"] for c in wcag_dataset()["criteria"])
    assert dataset()["counts"]["criteria"] == 55


def test_dataset_gives_every_criterion_exactly_one_owner_and_one_tier():
    seen = set()
    for row in dataset()["criteria"]:
        assert row["number"] not in seen, f"{row['number']} appears twice"
        seen.add(row["number"])
        assert row["owner"] in Owner.values
        assert row["tier"] in Tier.values
        assert row["rationale"].strip()


def test_dataset_counts_match_the_reports_headline():
    """§3.3: RULE 14 · AI 11 · HUMAN 30, across all 55."""
    assert dataset()["counts"]["by_owner"] == {"rule": 14, "ai": 11, "human": 30}
    assert sum(dataset()["counts"]["by_owner"].values()) == 55


def test_dataset_tier_counts_are_the_post_d5_split():
    """19 in the POC / 21 in Phase 2 / 15 always human.

    Not 20 / 20 / 15 — that figure predates decision D5, which moved 2.4.6 to Phase 2. See
    the correction recorded in RESEARCH_CORRECTIONS.md R8.
    """
    assert dataset()["counts"]["by_tier"] == {"in_poc": 19, "phase_2": 21, "human": 15}


def test_dataset_records_where_it_came_from():
    sources = dataset()["sources"]
    assert [s["path"].rsplit("/", 1)[-1] for s in sources] == [
        "Report1-Addendum-A-WCAG2.2-Coverage-and-Ownership_1.pdf",
        "Report1-Addendum-B-Models-Automatability-TechStack_1.pdf",
    ]
    assert all(re.fullmatch(r"[0-9a-f]{64}", s["sha256"]) for s in sources)
    assert [s["pages"] for s in sources] == [9, 8]
    # Our judgment, not the standard — the distinction has to travel with the data.
    assert "not W3C text" in dataset()["classification"]


# ── secondary checks: what another engine contributes ────────────────
def test_dataset_records_the_hybrid_contributions():
    """3.3.2 is rule-owned, and the report has the AI judging part of it."""
    rows = {r["number"]: r for r in dataset()["criteria"]}
    assert rows["3.3.2"]["owner"] == "rule"
    assert rows["3.3.2"]["secondary_checks"] == [
        {"engine": "ai", "note": "AI judges adequacy of instructions."}]
    assert rows["2.4.2"]["secondary_checks"][0]["engine"] == "ai"
    assert dataset()["counts"]["with_secondary_checks"] == 16


def test_a_secondary_check_is_never_the_primary_owner():
    for row in dataset()["criteria"]:
        for check in row["secondary_checks"]:
            assert check["engine"] != row["owner"], row["number"]
            assert check["engine"] in {"rule", "ai"}


def test_every_secondary_note_is_the_reports_own_words():
    """Derived from the rationale, so the completeness proof already covers the wording."""
    for row in dataset()["criteria"]:
        for check in row["secondary_checks"]:
            assert check["note"] in row["rationale"], row["number"]


def test_the_table_beats_the_hybrid_note_where_they_disagree():
    """§2.3's parenthetical omits 2.4.7 and names 2.4.6, which its own row does not support.

    Same precedent as corrections R7 and R8: the per-criterion table wins over prose.
    """
    rows = {r["number"]: r for r in dataset()["criteria"]}
    with_rule = {n for n, r in rows.items() if r["owner"] == "ai"
                 and any(c["engine"] == "rule" for c in r["secondary_checks"])}
    assert with_rule == {"1.1.1", "1.3.1", "2.4.4", "2.4.7", "4.1.2"}
    # 2.4.7's row: "Rule detects outline:none; AI/visual confirms a visible focus indicator."
    assert any(c["engine"] == "rule" for c in rows["2.4.7"]["secondary_checks"])
    # 2.4.6's row names no rule — only the POC semantics checker, which is the AI.
    assert rows["2.4.6"]["secondary_checks"] == []


# ── partial auto-flagging on human-led criteria ──────────────────────
def test_dataset_records_which_human_criteria_can_be_partly_flagged():
    rows = {r["number"]: r for r in dataset()["criteria"]}
    assert {n for n, r in rows.items() if r["partial_auto_flag"]} == {
        "1.2.1", "1.2.2", "1.2.3", "1.2.4", "1.2.5", "2.3.1"}
    assert dataset()["counts"]["partial_auto_flag"] == 6
    # 1.2.2: a rule can see a caption track is missing; whether captions are *accurate*
    # is the conformance question, and it stays human.
    assert rows["1.2.2"]["tier"] == "human"
    assert rows["1.2.2"]["secondary_checks"] == [
        {"engine": "rule", "note": "Rule can flag a missing caption track"}]


def test_partial_flagging_only_ever_applies_to_human_led_criteria():
    """A flag anywhere else would claim automation that does not exist."""
    for row in dataset()["criteria"]:
        if row["partial_auto_flag"]:
            assert row["tier"] == "human", row["number"]
    # The other 9 of the 15 have little-to-no automation, and say so by omission.
    human = [r for r in dataset()["criteria"] if r["tier"] == "human"]
    assert sum(1 for r in human if not r["partial_auto_flag"]) == 9


def test_dataset_carries_the_definitions_of_its_own_words():
    assert dataset()["tier_definitions"] == {
        "in_poc": "shipped in the Scope-A POC",
        "phase_2": "AI-extendable later (incl. agentic)",
        "human": "human-led with human sign-off",
    }
    assert set(dataset()["owner_definitions"]) == {"rule", "ai", "human"}


# ── re-deriving the registry from the report ─────────────────────────
def test_build_reproduces_the_committed_registry(built):
    """The committed file is what the report says — checked, not asserted.

    This is the test QA-04 could not have: the source is committed, so no network is
    involved and drift is caught on every run.
    """
    assert _drift(dataset(), built) == []


def test_build_finds_all_55_rows_with_the_expected_split(built):
    assert len(built["criteria"]) == 55
    assert built["counts"]["by_owner"] == {"rule": 14, "ai": 11, "human": 30}
    assert built["counts"]["by_tier"] == {"in_poc": 19, "phase_2": 21, "human": 15}


def test_build_check_passes_against_the_committed_file():
    call_command("build_ownership_dataset", "--check")


def test_build_check_reports_drift(tmp_path):
    stale = copy.deepcopy(dataset())
    stale["criteria"][0]["owner"] = "human"
    out = tmp_path / "ownership.json"
    out.write_text(json.dumps(stale), encoding="utf-8")
    with pytest.raises(CommandError, match="out of date with the report"):
        call_command("build_ownership_dataset", "--check", "--out", str(out))


def test_build_check_needs_the_file_to_exist(tmp_path):
    with pytest.raises(CommandError, match="does not exist"):
        call_command("build_ownership_dataset", "--check",
                     "--out", str(tmp_path / "nope.json"))


def test_build_writes_the_dataset(tmp_path):
    out = tmp_path / "ownership.json"
    call_command("build_ownership_dataset", "--out", str(out))
    assert len(json.loads(out.read_text(encoding="utf-8"))["criteria"]) == 55


def test_build_refuses_a_missing_report(tmp_path):
    with pytest.raises(CommandError, match="source report not found"):
        call_command("build_ownership_dataset", "--source", str(tmp_path / "gone.pdf"))


def test_drift_notices_a_changed_wcag_version():
    stale = copy.deepcopy(dataset())
    stale["version"] = "2.1"
    assert any("version '2.1' ->" in note for note in _drift(stale, dataset()))


def test_drift_notices_a_changed_source_report():
    stale = copy.deepcopy(dataset())
    stale["sources"][1]["sha256"] = "0" * 64
    assert any("source report itself has changed" in note
               for note in _drift(stale, dataset()))


def test_drift_notices_changed_secondary_checks_and_flags():
    stale = copy.deepcopy(dataset())
    rows = {r["number"]: r for r in stale["criteria"]}
    rows["3.3.2"]["secondary_checks"] = []
    rows["1.2.2"]["partial_auto_flag"] = False
    notes = _drift(stale, dataset())
    assert any("3.3.2: secondary_checks" in n for n in notes)
    assert any("1.2.2: partial_auto_flag" in n for n in notes)


def test_drift_notices_added_and_removed_criteria():
    fresh = copy.deepcopy(dataset())
    fresh["criteria"] = fresh["criteria"][1:] + [
        {"number": "9.9.9", "owner": "ai", "tier": "in_poc", "rationale": "x"}]
    notes = _drift(dataset(), fresh)
    assert any("9.9.9 is in the report but not the committed registry" in n for n in notes)
    assert any("is in the committed registry but not the report" in n for n in notes)


def test_drift_notices_a_changed_definition():
    fresh = copy.deepcopy(dataset())
    fresh["tier_definitions"]["human"] = "whatever"
    assert "tier_definitions changed" in _drift(dataset(), fresh)


# ── the completeness proof, shown to be non-vacuous ──────────────────
def test_completeness_proof_catches_a_dropped_row():
    """Prove the proof works: remove a row and the build must refuse."""
    text, _pages, _blob = ob.read_pdf()
    lines, _principles = ob.clean_region(ob.table_region(text))
    parsed = ob.rows(lines, {c["number"] for c in _wcag_numbers()})
    with pytest.raises(ValueError, match="lost .* character"):
        ob.verify_nothing_lost(lines, parsed[:-1])


def test_completeness_proof_catches_an_invented_word():
    text, _pages, _blob = ob.read_pdf()
    lines, _principles = ob.clean_region(ob.table_region(text))
    parsed = ob.rows(lines, {c["number"] for c in _wcag_numbers()})
    tampered = copy.deepcopy(parsed)
    tampered[0]["rationale"] += " and definitely always accessible"
    with pytest.raises(ValueError, match="lost .* character"):
        ob.verify_nothing_lost(lines, tampered)


def test_completeness_proof_catches_a_swapped_owner():
    text, _pages, _blob = ob.read_pdf()
    lines, _principles = ob.clean_region(ob.table_region(text))
    parsed = ob.rows(lines, {c["number"] for c in _wcag_numbers()})
    tampered = copy.deepcopy(parsed)
    tampered[0]["owner"] = "human"
    with pytest.raises(ValueError, match="lost .* character"):
        ob.verify_nothing_lost(lines, tampered)


def _wcag_numbers():
    from apps.a11y.wcag import dataset as wcag_dataset

    return wcag_dataset()["criteria"]


# ── the report's own cross-checks ────────────────────────────────────
def test_validate_rejects_a_criterion_the_standard_does_not_publish():
    """A criterion WCAG retired, still listed here — nobody would notice by counting."""
    parsed, principles = _parsed_and_principles()
    shrunk = copy.deepcopy(_wcag())
    shrunk["criteria"] = [c for c in shrunk["criteria"] if c["number"] != "1.4.13"]
    with pytest.raises(ValueError, match=r"WCAG does not publish: \['1.4.13'\]"):
        ob.validate(parsed, principles, shrunk)


def test_validate_rejects_a_missing_criterion():
    """55 rows and no duplicates, but one of them is for a criterion that does not exist."""
    parsed, principles = _parsed_and_principles()
    parsed[0]["number"] = "9.9.9"
    with pytest.raises(ValueError, match="no owner"):
        ob.validate(parsed, principles, _wcag())


def test_validate_rejects_a_duplicate():
    parsed, principles = _parsed_and_principles()
    parsed.append(dict(parsed[0]))
    with pytest.raises(ValueError, match="duplicate criteria"):
        ob.validate(parsed, principles, _wcag())


def test_validate_rejects_a_level_that_disagrees_with_the_standard():
    parsed, principles = _parsed_and_principles()
    parsed[0]["_level"] = "AA" if parsed[0]["_level"] == "A" else "A"
    with pytest.raises(ValueError, match="in the ownership table"):
        ob.validate(parsed, principles, _wcag())


def test_validate_rejects_a_row_with_no_rationale():
    parsed, principles = _parsed_and_principles()
    parsed[0]["rationale"] = ""
    with pytest.raises(ValueError, match="no rationale"):
        ob.validate(parsed, principles, _wcag())


def test_validate_rejects_a_principle_count_the_report_contradicts():
    parsed, principles = _parsed_and_principles()
    principles["ROBUST"]["total"] = 3
    with pytest.raises(ValueError, match="ROBUST"):
        ob.validate(parsed, principles, _wcag())


def test_validate_rejects_owner_counts_the_report_contradicts():
    parsed, principles = _parsed_and_principles()
    by_number = {row["number"]: row for row in parsed}
    by_number["1.4.3"]["owner"] = "ai"          # rule -> ai: 13 / 12 / 30, not 14 / 11 / 30
    with pytest.raises(ValueError, match="§3.3 says"):
        ob.validate(parsed, principles, _wcag())


def test_validate_rejects_an_enumeration_the_report_contradicts():
    parsed, principles = _parsed_and_principles()
    by_number = {row["number"]: row for row in parsed}
    # Swap two criteria between the always-human and Phase-2 lists: counts stay 14/11/30
    # and 19/21/15, so only the enumerations can catch it.
    by_number["1.2.1"]["tier"] = "phase_2"
    by_number["2.1.1"]["tier"] = "human"
    with pytest.raises(ValueError, match="§3.3's 15"):
        ob.validate(parsed, principles, _wcag())


def test_validate_rejects_a_short_table():
    parsed, principles = _parsed_and_principles()
    with pytest.raises(ValueError, match="expected 55 Level A/AA criteria, parsed 54"):
        ob.validate(parsed[:-1], principles, _wcag())


def test_validate_guards_decision_d5_by_name():
    """2.4.6 back in the POC must fail — the POC ships 5 AI-judged criteria, not 6."""
    parsed, principles = _parsed_and_principles()
    by_number = {row["number"]: row for row in parsed}
    by_number["2.4.6"]["tier"] = "in_poc"
    with pytest.raises(ValueError, match=r"POC's AI-judged criteria"):
        ob.validate(parsed, principles, _wcag())


def test_validate_guards_decision_d5_even_when_the_enumerations_still_agree():
    """Moving 2.4.6 out of Phase 2 altogether is caught by the D5 guard, by name."""
    parsed, principles = _parsed_and_principles()
    by_number = {row["number"]: row for row in parsed}
    by_number["2.4.6"]["tier"] = "human"
    with pytest.raises(ValueError, match="decision D5 fixed it at 'phase_2'"):
        ob.validate(parsed, principles, _wcag())


def test_validate_rejects_a_sixteenth_permanently_human_criterion():
    """The number a conformance report must not overstate."""
    parsed, principles = _parsed_and_principles()
    by_number = {row["number"]: row for row in parsed}
    by_number["2.4.7"]["tier"] = "human"       # AI-owned, so no enumeration notices
    with pytest.raises(ValueError, match="expected 15 permanently-human criteria, found 16"):
        ob.validate(parsed, principles, _wcag())


def test_validate_rejects_a_secondary_check_that_is_the_primary_owner():
    parsed, principles = _parsed_and_principles()
    by_number = {row["number"]: row for row in parsed}
    by_number["3.3.2"]["secondary_checks"] = [{"engine": "rule", "note": "Rule catches"}]
    with pytest.raises(ValueError, match="cannot also be a secondary check"):
        ob.validate(parsed, principles, _wcag())


def test_validate_rejects_a_secondary_note_that_is_not_the_reports_words():
    parsed, principles = _parsed_and_principles()
    by_number = {row["number"]: row for row in parsed}
    by_number["3.3.2"]["secondary_checks"] = [
        {"engine": "ai", "note": "the AI handles this one entirely"}]
    with pytest.raises(ValueError, match="not the report's own words"):
        ob.validate(parsed, principles, _wcag())


def test_validate_rejects_a_changed_set_of_hybrids():
    parsed, principles = _parsed_and_principles()
    by_number = {row["number"]: row for row in parsed}
    by_number["2.4.7"]["secondary_checks"] = []
    with pytest.raises(ValueError, match="rule sub-part changed"):
        ob.validate(parsed, principles, _wcag())


def test_validate_rejects_a_changed_partial_flag_set():
    parsed, principles = _parsed_and_principles()
    by_number = {row["number"]: row for row in parsed}
    by_number["1.2.2"]["partial_auto_flag"] = False
    with pytest.raises(ValueError, match="partially-flaggable criteria changed"):
        ob.validate(parsed, principles, _wcag())


def test_validate_rejects_partial_flagging_outside_the_human_tier(monkeypatch):
    """Guarded separately from the transcribed list, so editing that list cannot bypass it.

    1.4.3 Contrast is rule-decided outright — "partially flaggable" is meaningless there, and
    claiming it would overstate what a human still has to do.
    """
    monkeypatch.setattr(ob, "PARTIAL_AUTO_FLAG", ob.PARTIAL_AUTO_FLAG | {"1.4.3"})
    parsed, principles = _parsed_and_principles()
    {row["number"]: row for row in parsed}["1.4.3"]["partial_auto_flag"] = True
    with pytest.raises(ValueError, match="defined only for the human-led tier"):
        ob.validate(parsed, principles, _wcag())


def test_validate_rejects_a_hybrid_note_that_no_longer_differs_as_expected(monkeypatch):
    """If the report is corrected, the build stops rather than quietly adopting the change."""
    monkeypatch.setattr(ob, "HYBRID_NOTE_AI_WITH_RULE", ob.TABLE_AI_WITH_RULE)
    parsed, principles = _parsed_and_principles()
    with pytest.raises(ValueError, match="rather than the two known discrepancies"):
        ob.validate(parsed, principles, _wcag())


def test_verify_partial_auto_flag_source_rejects_a_changed_report():
    with pytest.raises(ValueError, match="must be corrected, not the check relaxed"):
        ob.verify_partial_auto_flag_source("Addendum B saying something else")


def test_build_refuses_a_missing_addendum_b(tmp_path):
    with pytest.raises(CommandError, match="source report not found"):
        call_command("build_ownership_dataset", "--source-b", str(tmp_path / "gone.pdf"))


def test_verify_definitions_rejects_a_changed_report():
    with pytest.raises(ValueError, match="must be corrected, not the check relaxed"):
        ob.verify_definitions("a report that says something else entirely")


def test_table_region_refuses_an_unrecognisable_report():
    with pytest.raises(ValueError, match="could not locate"):
        ob.table_region("no mapping table here")


def test_clean_region_refuses_missing_principle_headers():
    with pytest.raises(ValueError, match="4 principle headers"):
        ob.clean_region("PERCEIVABLE — 20 criteria (9 A + 11 AA)\n1.1.1 x A AI IN POC y")


def test_rows_refuses_text_before_the_first_row():
    with pytest.raises(ValueError, match="before the first criterion row"):
        ob.rows(["stray heading"], {"1.1.1"})


def test_rows_refuses_a_row_it_cannot_read():
    with pytest.raises(ValueError, match="could not read an ownership row"):
        ob.rows(["1.1.1 Non-text Content A MAGIC IN POC because"], {"1.1.1"})


def test_build_refuses_a_wcag_dataset_of_another_version(monkeypatch):
    from apps.a11y import wcag

    monkeypatch.setattr(wcag, "dataset", lambda: {"version": "3.0", "criteria": []})
    with pytest.raises(ValueError, match="stated for WCAG 2.2"):
        ob.build(log=lambda *a, **k: None)


def _wcag():
    from apps.a11y.wcag import dataset as wcag_dataset

    return wcag_dataset()


def _parsed_and_principles():
    text, _pages, _blob = ob.read_pdf()
    lines, principles = ob.clean_region(ob.table_region(text))
    return ob.rows(lines, {c["number"] for c in _wcag()["criteria"]}), principles


# ── the registry at runtime ──────────────────────────────────────────
def test_lookup_returns_owner_and_tier(loaded):
    """AC1."""
    row = ownership("1.4.1")
    assert (row.owner, row.tier) == (Owner.AI, Tier.IN_POC)
    assert row.rationale.startswith("AI detects info conveyed by colour alone")


def test_the_spot_checks_the_task_names(loaded):
    """AC3 — 1.4.3 = rule, 1.1.1 = AI, 1.2.2 = human."""
    assert ownership("1.4.3").owner == Owner.RULE
    assert ownership("1.1.1").owner == Owner.AI
    assert ownership("1.2.2").owner == Owner.HUMAN


def test_exactly_55_criteria_each_with_one_owner_and_one_tier(loaded):
    """AC2."""
    rows = list(CriterionOwnership.objects.filter(version=DEFAULT_VERSION))
    assert len(rows) == 55
    assert len({row.number for row in rows}) == 55
    assert all(row.owner in Owner.values and row.tier in Tier.values for row in rows)


def test_unknown_criterion_raises_rather_than_returning_nothing(loaded):
    """A caller handed `None` would route no check and report a pass."""
    with pytest.raises(UnknownCriterion, match="1.1.9"):
        ownership("1.1.9")
    # AAA criteria are outside the conformance target, so they are unknown here too.
    with pytest.raises(UnknownCriterion):
        ownership("1.4.6")


def test_an_unloaded_registry_says_so_and_names_the_fix(db):
    CriterionOwnership.objects.all().delete()
    with pytest.raises(OwnershipNotLoaded, match="manage.py load_ownership"):
        ownership("1.4.1")


def test_criteria_for_answers_which_engine_owns_what(loaded):
    assert criteria_for(owner=Owner.RULE) == numerically(ROUTED_RULE_PRIMARY_13)
    assert criteria_for(owner=Owner.AI, tier=Tier.IN_POC) == numerically(ROUTED_AI_IN_POC_6)
    assert criteria_for(owner=Owner.AI, tier=Tier.PHASE_2) == numerically(AI_PHASE_2_6)
    assert criteria_for(tier=Tier.HUMAN) == numerically(HUMAN_ALWAYS_15)
    assert len(criteria_for()) == 55


def test_criteria_for_sorts_numerically_not_alphabetically(loaded):
    """1.4.2 before 1.4.10 — sorting the column would put them the other way round."""
    rule = criteria_for(owner=Owner.RULE)
    assert rule.index("1.4.2") < rule.index("1.4.10")


def test_tier_is_not_redundant_with_owner(loaded):
    """The reason this column exists: the 30 human-owned criteria split 15 / 15.

    Fifteen are reached once Phase-2 interaction testing lands; fifteen need a person
    forever. `owner` cannot tell them apart, so a coverage report built on `owner` alone
    would state 30 criteria as permanently manual when the honest answer is 15.
    """
    human_owned = criteria_for(owner=Owner.HUMAN)
    assert len(human_owned) == 30
    assert criteria_for(owner=Owner.HUMAN, tier=Tier.PHASE_2) == numerically(
        HUMAN_REACHED_BY_PHASE_2_15)
    assert criteria_for(owner=Owner.HUMAN, tier=Tier.HUMAN) == numerically(HUMAN_ALWAYS_15)
    assert len(criteria_for(tier=Tier.HUMAN)) == 15


def test_what_the_finished_backlog_covers(loaded):
    """19 in the POC + 21 in Phase 2 = 40 checked; 15 genuinely human. Nothing left over."""
    assert len(criteria_for(tier=Tier.IN_POC)) == 19
    assert len(criteria_for(tier=Tier.PHASE_2)) == 21
    assert len(criteria_for(tier=Tier.HUMAN)) == 15
    assert 19 + 21 + 15 == 55


def test_is_in_poc_and_needs_human_always(loaded):
    assert is_in_poc("1.4.3") is True                  # rule engine, ships in the POC
    assert is_in_poc("2.4.6") is False                 # Phase 2, per decision D5
    assert needs_human_always("1.2.2") is True         # caption accuracy, forever
    assert needs_human_always("2.1.1") is False        # keyboard — Phase 2 reaches it
    assert needs_human_always("1.4.3") is False


def test_decision_d5_is_what_is_loaded(loaded):
    """2.4.6 is Phase 2, so it is not one of the criteria the POC judges with AI.

    The count moved from five to six on 1 September, and NOT because D5 changed: 1.4.11 joined
    under correction R14. Stated as the routed list rather than a number, because "the POC
    judges five" was a fact about two independent decisions and reading it as one is how a
    later change looks like a regression.
    """
    assert ownership("2.4.6").tier == Tier.PHASE_2
    assert "2.4.6" not in criteria_for(owner=Owner.AI, tier=Tier.IN_POC)
    assert criteria_for(owner=Owner.AI, tier=Tier.IN_POC) == numerically(ROUTED_AI_IN_POC_6)


def test_criteria_touched_by_finds_the_hybrid_contributions(loaded):
    """The routing question `criteria_for` cannot answer.

    The label checker's own criterion is 2.5.3, but the report also has it speaking to
    3.3.2 — which the rule engine owns. Asking only "what does the AI own?" misses it.
    """
    touched_by_ai = criteria_touched_by(Owner.AI)
    assert "3.3.2" in touched_by_ai
    assert "2.4.2" in touched_by_ai
    assert "2.5.3" not in touched_by_ai          # the AI owns it outright, nothing secondary
    # 1.4.11 is here because correction R14 moved the criterion to the AI and recorded the
    # measuring half where a contributing engine belongs. The committed file still counts 16
    # hybrids because the file is the report; the routed view has 17, and the one extra is the
    # override. Asserted as 16 + 1 so a second override cannot arrive unnoticed.
    assert criteria_touched_by(Owner.RULE) == numerically(
        ["1.1.1", "1.2.2", "1.3.1", "1.4.11", "2.2.2", "2.4.4", "2.4.7", "4.1.2", "4.1.3"])
    assert len(touched_by_ai) + len(criteria_touched_by(Owner.RULE)) == 16 + 1


def test_the_committed_file_still_says_what_the_report_says(loaded):
    """The override is a layer, never an edit — and this is the half that proves it.

    `data/ownership.json` is a *derivation*: `ownership_build` rebuilds it from the committed
    research PDF and proves it against eight independent cross-checks, including the report's
    own headline counts. Editing a row there to record a decision would make the file disagree
    with its own source, and `build_ownership_dataset --check` would fail — correctly, and for
    a reason nobody would be able to act on six months later.

    So the file keeps saying `rule` for 1.4.11, and the routing table says `ai`. Both are true
    statements about different things: what the report concluded, and what we decided after it.
    """
    from apps.a11y.ownership import dataset

    on_file = {row["number"]: row for row in dataset()["criteria"]}
    assert on_file["1.4.11"]["owner"] == "rule", (
        "the committed registry has been edited to record a decision. It is derived from the "
        "research PDF and must keep matching it — put the decision in ENGINEERING_OVERRIDES "
        "and record it in RESEARCH_CORRECTIONS.md instead"
    )
    assert dataset()["counts"]["by_owner"] == {"ai": 11, "human": 30, "rule": 14}
    # And the routed view differs from it by exactly the override.
    assert ownership("1.4.11").owner == Owner.AI


def test_every_ownership_override_is_one_the_team_recorded(loaded):
    """A place to disagree with the research is necessary and is also the most dangerous file
    in this app: it can make any criterion read as checked by anyone.

    Three things are held here. **The set itself**, so an addition is a decision somebody takes
    rather than a line that appears. **Its size**, because "one recorded correction" and "a
    growing list of exceptions" are different objects and only the first is defensible to a
    client. And **that it is written down in prose a person can argue with** — the whole failure
    of 27 August to 1 September was a correction agreed in a document and never carried into the
    data, so an override with no matching entry in RESEARCH_CORRECTIONS.md is the same mistake
    pointing the other way.
    """
    from pathlib import Path

    from apps.a11y import ownership as ownership_module

    assert set(ownership_module.ENGINEERING_OVERRIDES) == {"1.4.11"}

    corrections = (Path(ownership_module.__file__).resolve().parents[3]
                   / "docs" / "web-accessibility" / "RESEARCH_CORRECTIONS.md")
    text = corrections.read_text(encoding="utf-8")
    for number in ownership_module.ENGINEERING_OVERRIDES:
        assert number in text, (
            f"{number}'s ownership is overridden in code and RESEARCH_CORRECTIONS.md does not "
            f"mention it. Write down what was decided and why, or drop the override."
        )


def test_an_override_naming_a_criterion_that_does_not_exist_is_refused():
    """A typo in a criterion number would otherwise be a silent no-op — the override would
    simply never apply, and the platform would go on routing the old way while the code read
    as though it had been changed. That is the failure mode this whole area keeps producing."""
    from apps.a11y.ownership import UnknownCriterion, applied_overrides

    data = {"criteria": [{"number": "1.1.1", "owner": "ai"}]}
    with pytest.raises(UnknownCriterion, match="1.4.11"):
        applied_overrides(data)


def test_a_secondary_check_never_claims_the_criterion(loaded):
    """3.3.2 stays rule-owned even though the AI contributes to it."""
    assert ownership("3.3.2").owner == Owner.RULE
    assert [c["engine"] for c in ownership("3.3.2").secondary_checks] == [Owner.AI]


def test_partially_flaggable_lists_the_six_human_criteria(loaded):
    assert partially_flaggable() == ["1.2.1", "1.2.2", "1.2.3", "1.2.4", "1.2.5", "2.3.1"]
    # Every one is still human-decided — flagging is a head start, never a verdict.
    assert all(needs_human_always(n) for n in partially_flaggable())
    # And the other nine get nothing automated at all.
    assert len(set(criteria_for(tier=Tier.HUMAN)) - set(partially_flaggable())) == 9


def test_the_poc_checkers_and_the_registry_cannot_drift_apart(loaded):
    """The live checker map must say exactly what the registry says the AI owns in the POC.

    `integrations.types.A11Y_CHECKER_CRITERIA` is enforced at runtime — a judgment naming a
    criterion its checker does not own raises. If that map and this registry ever disagree,
    one of them is wrong about what the POC covers, and the conformance report is the thing
    that suffers. Extending the map to cover secondary touches (3.3.2, 2.4.6) is QA-12's
    job, and should fail here first so it is a decision rather than a side effect.
    """
    from integrations.types import A11Y_CHECKER_CRITERIA

    claimed = {number for owned in A11Y_CHECKER_CRITERIA.values() for number in owned}
    assert claimed == set(criteria_for(owner=Owner.AI, tier=Tier.IN_POC))
    assert "2.4.6" not in claimed                # Phase 2, per decision D5
    assert "3.3.2" not in claimed                # a secondary touch, not owned — see QA-12


def test_str_is_readable(loaded):
    assert str(ownership("1.4.1")) == "WCAG 2.2 1.4.1: ai / in_poc"


# ── loading ─────────────────────────────────────────────────────────
def test_reload_updates_in_place_and_never_duplicates(loaded):
    assert loaded == {"created": 0, "updated": 55} or loaded == {"created": 55,
                                                                 "updated": 0}
    again = load_ownership()
    assert again == {"created": 0, "updated": 55}
    assert CriterionOwnership.objects.filter(version=DEFAULT_VERSION).count() == 55


def test_load_refuses_a_version_the_dataset_does_not_hold(db):
    with pytest.raises(ValueError, match="asked to load '9.9'"):
        load_ownership(version="9.9")


def test_a_second_version_loads_alongside_the_first(loaded):
    """A revised report is a reload, not a migration — and never disturbs the live one."""
    future = copy.deepcopy(dataset())
    future["version"] = "2.3"
    future["criteria"][0]["owner"] = "human"
    load_ownership(version="2.3", data=future)

    assert ownership(future["criteria"][0]["number"], version="2.3").owner == Owner.HUMAN
    assert ownership(future["criteria"][0]["number"]).owner == dataset(
    )["criteria"][0]["owner"]
    assert CriterionOwnership.objects.count() == 110


def test_a_stray_row_stops_a_reload_and_is_named(loaded):
    """Nothing in the platform writes this table, so a row we did not put there matters."""
    CriterionOwnership.objects.create(
        version=DEFAULT_VERSION, number="9.9.9", owner=Owner.AI, tier=Tier.IN_POC,
        rationale="reached the database out of band")
    with pytest.raises(UnpublishedRows, match="9.9.9"):
        load_ownership()


def test_a_refused_reload_changes_nothing(loaded):
    """Checked before anything is written, so a refusal leaves the table as it found it."""
    CriterionOwnership.objects.filter(number="1.4.1").update(owner=Owner.HUMAN)
    CriterionOwnership.objects.create(
        version=DEFAULT_VERSION, number="9.9.9", owner=Owner.AI, tier=Tier.IN_POC,
        rationale="stray")
    with pytest.raises(UnpublishedRows):
        load_ownership()
    assert ownership("1.4.1").owner == Owner.HUMAN      # untouched, not half-repaired


# ── nothing is ever silently unowned ────────────────────────────────
def test_verify_complete_passes_on_a_migrated_database(loaded):
    load_wcag()
    assert verify_complete() == 55


def test_verify_complete_names_a_criterion_with_no_owner(loaded):
    load_wcag()
    CriterionOwnership.objects.filter(number="1.4.1").delete()
    with pytest.raises(IncompleteOwnership, match="1.4.1"):
        verify_complete()


def test_verify_complete_names_an_ownership_row_with_no_criterion(loaded):
    load_wcag()
    WcagCriterion.objects.filter(number="1.4.1").delete()
    with pytest.raises(IncompleteOwnership, match="not loaded"):
        verify_complete()


def test_verify_complete_says_so_when_no_standard_is_loaded(loaded):
    WcagCriterion.objects.all().delete()
    with pytest.raises(OwnershipNotLoaded, match="load_wcag"):
        verify_complete()


# ── the management command ──────────────────────────────────────────
def test_load_command_loads_the_registry(db):
    CriterionOwnership.objects.all().delete()
    call_command("load_ownership")
    assert CriterionOwnership.objects.count() == 55


def test_load_command_check_reports_and_writes_nothing(loaded):
    load_wcag()
    call_command("load_ownership", "--check")
    assert CriterionOwnership.objects.count() == 55


def test_load_command_check_fails_when_the_count_is_wrong(loaded):
    CriterionOwnership.objects.filter(number="1.4.1").delete()
    with pytest.raises(CommandError, match="does not match the committed registry"):
        call_command("load_ownership", "--check")


def test_load_command_check_fails_on_a_criterion_with_no_owner(loaded):
    """The count can be right and the coverage still wrong."""
    load_wcag()
    CriterionOwnership.objects.filter(number="1.4.1").update(number="9.9.9")
    with pytest.raises(CommandError, match="would never be checked"):
        call_command("load_ownership", "--check")


def test_load_command_reports_a_stray_row(loaded):
    CriterionOwnership.objects.create(
        version=DEFAULT_VERSION, number="9.9.9", owner=Owner.AI, tier=Tier.IN_POC,
        rationale="stray")
    with pytest.raises(CommandError, match="9.9.9"):
        call_command("load_ownership")


# ── one platform-wide copy, and the app role cannot write it ────────
def test_the_registry_has_no_tenant_column(db):
    assert "tenant_id" not in [f.name for f in CriterionOwnership._meta.get_fields()]
    with connection.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'a11y_criterionownership'")
        assert "tenant_id" not in {row[0] for row in cur.fetchall()}


@pytest.mark.django_db(transaction=True)
def test_the_app_role_can_read_the_registry_but_never_write_it():
    """"A tenant cannot decide a criterion needs less checking" as a database guarantee.

    Checked on a connection opened as the real app role — the Django test connection is the
    privileged migration role and could write regardless, so it could never show this.
    `transaction=True` so the rows are committed and the second connection can see them.
    """
    load_ownership()

    sd = connection.settings_dict
    with connection.cursor() as cur:
        cur.execute("SELECT current_database()")
        dbname = cur.fetchone()[0]
    raw = psycopg.connect(
        host=sd["HOST"], port=sd["PORT"], dbname=dbname,
        user=settings.APP_DB_USER, password=settings.APP_DB_PASSWORD, autocommit=True,
    )
    try:
        with raw.cursor() as cur:
            # Readable with no tenant context at all — there is no tenant to be in.
            cur.execute("SELECT count(*) FROM a11y_criterionownership")
            assert cur.fetchone()[0] == 55

            for statement in (
                "UPDATE a11y_criterionownership SET owner = 'rule' WHERE number = '1.2.2'",
                "DELETE FROM a11y_criterionownership",
                "INSERT INTO a11y_criterionownership (id, created_at, updated_at, version, "
                "number, owner, tier, rationale) VALUES (gen_random_uuid(), now(), now(), "
                "'2.2', '9.9.9', 'ai', 'in_poc', '')",
            ):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cur.execute(statement)

            # Unchanged after every attempt.
            cur.execute("SELECT owner, tier FROM a11y_criterionownership "
                        "WHERE number = '1.2.2'")
            assert cur.fetchone() == ("human", "human")
    finally:
        raw.close()
