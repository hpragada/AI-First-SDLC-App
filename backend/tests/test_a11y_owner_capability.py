"""The question two completeness proofs never asked: can the named owner actually check it? (#4)

**This file is the fix for a class of bug, not for two instances of it.**

`ownership.verify_complete()` proves every one of the 55 criteria has an owner.
`gates.wcag.verify_complete()` proves every criterion is asked at design review or recorded as
deliberately not asked. Both were kept faithfully. Neither asks whether the owner is *able* — and
for 1.4.10 Reflow and 1.4.11 Non-text Contrast the answer was no for four tasks, silently, while
both were reported as covered.

The chain that produced it is worth keeping written down, because every link was reasonable:

  1. The research report defines RULE as *"a deterministic engine can decide the typical case
     with high confidence"*. True of reflow and of contrast maths, in principle.
  2. The registry was derived from that report by a parser with eight cross-checks — every one
     comparing the parse to the report, not one comparing the report to the scanner.
  3. The scanner was fixed as `@axe-core/playwright`. From that moment "the deterministic
     engine" and "axe" were the same phrase, and the fourteen were never re-checked against what
     axe ships.
  4. The conformance statement printed both as "Not evaluated" — correctly — alongside some
     thirty genuinely human criteria, where two more were indistinguishable.

So the assertions below are deliberately about capability and nothing else. They do not check
that a check is GOOD, or that it ran, or that it found anything. They check that something
exists which could, in principle, answer the question the registry says this owner answers.

No database: every input is a committed file or a module constant.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from apps.a11y import scanner_coverage as sc

_REPO = Path(__file__).resolve().parents[2]
_OWNERSHIP = json.loads(
    (_REPO / "backend/apps/a11y/data/ownership.json").read_text(encoding="utf-8"))
_BY_NUMBER = {row["number"]: row for row in _OWNERSHIP["criteria"]}


def _numbers(**match) -> list[str]:
    return sorted(
        (n for n, row in _BY_NUMBER.items() if all(row[k] == v for k, v in match.items())),
        key=lambda n: [int(p) for p in n.split(".")],
    )


# ── the assertion that was missing ─────────────────────────────────────────────────

def test_every_rule_owned_criterion_has_something_that_can_actually_decide_it():
    """**The guard.** Run before QA-25 this failed on exactly 1.4.10 and 1.4.11.

    "Something" is axe's own rules or the platform's own deterministic rules, together — the
    platform is not obliged to use axe, only to have *a* deterministic answer for a criterion it
    tells a client is machine-checked.
    """
    deterministic = sc.deterministic_criteria()
    unbacked = [n for n in _numbers(owner="rule") if n not in deterministic]
    assert not unbacked, (
        f"{len(unbacked)} criteria are recorded as decided by a deterministic engine and "
        f"NOTHING checks them: {', '.join(unbacked)}. Either write the rule (see "
        f"`apps.a11y.page_rules` for how 1.4.10 and 1.4.11 were done), or change the owner in "
        f"the registry and say why. Scanner in use: {sc.describe()}."
    )


def test_every_ai_owned_criterion_has_a_checker_that_judges_it():
    """The same question of the AI half. `tier` matters here: a criterion the registry defers to
    Phase 2 is not expected to have a checker yet, and asserting otherwise would turn a plan into
    a failure."""
    judged = set(sc.ai_criteria()) | set(sc.agentic_criteria())
    unbacked = [n for n in _numbers(owner="ai", tier="in_poc") if n not in judged]
    assert not unbacked, (
        f"{len(unbacked)} criteria are recorded as AI-decided and shipping in the POC, and no "
        f"checker judges them: {', '.join(unbacked)}"
    )


def test_every_criterion_the_registry_defers_to_phase_two_is_reached_or_still_pending():
    """A `phase_2` criterion may legitimately have nothing yet — that is what the tier means.
    What it may NOT do is be reported as covered, which is `conformance._can_claim_positive`'s
    job and is proven in `test_a11y_conformance_guard`. This test records which of them have in
    fact arrived, so the number in a status report comes from the code."""
    reachable = set(sc.ai_criteria()) | set(sc.agentic_criteria()) | set(
        sc.platform_rule_criteria())
    arrived = [n for n in _numbers(tier="phase_2") if n in reachable]
    # The eight journey checks landed in QA-20; nothing else from Phase 2 has.
    assert set(arrived) == {"2.1.1", "2.1.2", "2.4.3", "2.4.7", "2.4.11", "3.2.1", "3.2.2",
                            "4.1.3"}


# ── the design gate's own excuses have to be true (#3) ─────────────────────────────

def test_every_criterion_the_design_gate_skips_as_machine_checked_really_is():
    """**The assertion that was missing at the other end of the same bug.**

    The design review does not ask a designer about 1.4.10 Reflow. The written reason is *"a rule
    scanner or the AI pass decides this on the built page"*. That was a reasonable sentence when
    somebody wrote it and it had quietly become false, so Reflow was the one criterion in the
    whole standard that every net was built to let through: skipped at design because the scanner
    had it, absent from the scanner because nobody had written it.

    `gates.wcag.verify_complete()` proves every criterion is in exactly one bucket. It has never
    proved a bucket's REASON is true. This does.
    """
    from apps.gates.wcag import NOT_ASKED

    checked = set(sc.axe_criteria()) | set(sc.platform_rule_criteria()) | set(
        sc.ai_criteria()) | set(sc.agentic_criteria())
    unbacked = sorted(
        (n for n in NOT_ASKED["checked_on_the_built_page"] if n not in checked),
        key=lambda n: [int(p) for p in n.split(".")],
    )
    assert not unbacked, (
        f"the design gate skips {', '.join(unbacked)} on the written grounds that something "
        f"checks them on the built page, and nothing does. Either build the check, or move them "
        f"to the `deferred_to_a_later_phase` bucket, which says what is actually true."
    )


def test_the_deferred_bucket_holds_exactly_what_nothing_checks_yet():
    """The other half: a criterion parked as "later" must not silently already be covered, or
    the gate would go on skipping a question it could be answering today."""
    from apps.gates.wcag import NOT_ASKED

    checked = set(sc.axe_criteria()) | set(sc.platform_rule_criteria()) | set(
        sc.ai_criteria()) | set(sc.agentic_criteria())
    already = [n for n in NOT_ASKED["deferred_to_a_later_phase"] if n in checked]
    assert not already, (
        f"{', '.join(already)} are parked as not-built and something now checks them — move "
        f"them to `checked_on_the_built_page`"
    )
    # These three came out of `checked_on_the_built_page` on 27 August because that bucket's
    # reason was false about them. Pinned so the split is a decision, not a drift.
    assert set(NOT_ASKED["deferred_to_a_later_phase"]) == {"1.3.2", "1.3.3", "1.4.5"}
    assert all(_BY_NUMBER[n]["tier"] == "phase_2"
               for n in NOT_ASKED["deferred_to_a_later_phase"])


# ── the criteria we now check ourselves, and why they need their own rules ─────────

@pytest.mark.parametrize("number", ["1.4.10", "1.4.11"])
def test_the_two_criteria_axe_has_no_rule_for_are_checked_by_the_platform_instead(number):
    """The regression test for the original bug, stated as its two halves."""
    assert number not in sc.axe_criteria(), (
        f"axe now covers {number}; that is good news, and this test and "
        f"`apps.a11y.page_rules` should be revisited rather than left duplicating it"
    )
    assert number in sc.platform_rule_criteria()


def test_non_text_contrast_is_covered_by_a_rule_AND_a_judge_and_needs_both():
    """1.4.11 is a criterion in two halves and only one of them is arithmetic.

    The registry's own rationale said so before either half was built — *"computable, but 'which
    graphics matter' needs some review"* — and then recorded the owner as `rule` anyway. That is
    how the judged half went unbuilt while the criterion was reported as covered.

    **Correction R14 settled that on 27 August and the registry was not changed until
    1 September**, and this test is one of the places that noticed. In between, the map of what
    the AI owns and the routing registry disagreed, five guards said so daily, and the check was
    briefly held back — at which point the criterion would have fallen back on the arithmetic
    alone. Both failure modes have a guard here now.
    """
    from apps.a11y.checkers import HELD_BACK_SELECTION_RULES
    from apps.a11y.conformance import suggest
    from integrations.types import A11Y_HELD_BACK_CLAIMS

    assert _BY_NUMBER["1.4.11"]["rationale"].count("review") >= 1, (
        "the registry's own words are the evidence this criterion is not rule-only; if they "
        "change, this test's reasoning has to be re-argued rather than quietly updated"
    )

    # Both halves exist and both are running.
    deciders = sc.deciders_for("1.4.11")
    assert sc.ENGINE_PLATFORM in deciders, "the measurable half: control edges, in page_rules"
    assert sc.ENGINE_AI in deciders, "the judged half: which parts of a graphic carry meaning"
    assert deciders[sc.ENGINE_AI] == ("graphics",)
    assert HELD_BACK_SELECTION_RULES == (), "the judged half is built and is not running"

    # And the routing registry agrees the judge decides it, which is the step that was missing
    # for five days while every layer above it already assumed so.
    from apps.a11y.ownership import ENGINEERING_OVERRIDES

    assert ENGINEERING_OVERRIDES["1.4.11"]["owner"] == "ai"
    assert [c["engine"] for c in ENGINEERING_OVERRIDES["1.4.11"]["secondary_checks"]] == ["rule"]

    # The other end: if the judged half is ever held back, the measured half must NOT pick the
    # criterion up. Guarded while nothing is held, because the day something is held is exactly
    # the day nobody re-derives this.
    assert "1.4.11" not in A11Y_HELD_BACK_CLAIMS, "nothing is held today"
    clean = {"routes": {"/a": "passed"}, "engines": {"rule"}}
    assert suggest(clean, 0, owner="rule", held_back=True) is None, (
        "a clean sweep of control edges just claimed a criterion whose judge is paused"
    )
    assert suggest({"routes": {"/a": "failed"}, "engines": {"rule"}}, 0, owner="rule",
                   held_back=True) == "does_not_support", (
        "a hold must never soften a proven failure — only the positive direction is unsafe"
    )


def test_reflow_is_rule_only_and_deliberately_has_no_judge():
    """1.4.10's test is objective and its one exception is a fixed list of container kinds, so
    adding an AI opinion would add cost and uncertainty to a settled measurement."""
    deciders = sc.deciders_for("1.4.10")
    assert set(deciders) == {sc.ENGINE_PLATFORM}


# ── the inventory has to stay honest ───────────────────────────────────────────────

def test_the_inventory_scans_with_exactly_the_tags_the_companion_scans_with():
    """The one way this guard could give a false assurance: an inventory generated over a wider
    tag set than the audit actually runs would credit the platform with rules that never fire."""
    audit = (_REPO / "runner/companion/assets/a11y_audit.mjs").read_text(encoding="utf-8")
    block = re.search(r'values:\s*\[([^\]]*)\]', audit)
    assert block, "could not find the scan's tag list in a11y_audit.mjs"
    assert [t.strip().strip('"') for t in block.group(1).split(",") if t.strip()] == \
        sc.inventory()["tags"]


def test_the_inventory_opts_in_to_exactly_the_rules_the_companion_opts_in_to():
    """The second half of the same guarantee, and the half that was missing.

    A tag filter is not the only way an inventory can claim a rule the scan never runs. axe holds
    `experimental` rules out of a tag selection **silently** — they match the tags, they are
    enabled, and they do not run. This file counted them, so it reported 24 criteria against a
    scan that decided 22, and 1.3.4 Orientation sat recorded as machine-checked with nothing
    checking it. The same shape as 1.4.10 and 1.4.11, found the same way, and missed by the guard
    above because that guard trusts this data.

    The companion now names them in a `rules` block. The two lists have to stay identical: name a
    rule here that the scan does not run and the platform is credited with a check that never
    fires; run one there and omit it here and the inventory understates what we do.
    """
    audit = (_REPO / "runner/companion/assets/a11y_audit.mjs").read_text(encoding="utf-8")
    block = re.search(r"rules:\s*\{(.*?)\n\s*\},", audit, re.S)
    assert block, "could not find the scan's opt-in rules block in a11y_audit.mjs"
    in_audit = sorted(re.findall(r'"([^"]+)":\s*\{\s*enabled:\s*true', block.group(1)))
    in_inventory = sorted(sc.inventory().get("opted_in", []))
    assert in_audit == in_inventory, (
        f"the scan opts in to {in_audit} and the inventory records {in_inventory}. "
        f"Regenerate it with `{sc.REBUILD_COMMAND}`."
    )
    assert in_audit, (
        "the opt-in block is empty. 1.3.4 Orientation and 2.5.3 Label in Name have no other rule, "
        "so an empty block means neither is machine-checked."
    )


def test_the_inventory_names_the_scanner_and_version_it_was_taken_from():
    """A conformance claim that cannot name what produced it cannot be re-examined."""
    data = sc.inventory()
    assert data["scanner"] == "axe-core"
    assert re.fullmatch(r"\d+\.\d+\.\d+", data["version"])
    assert data["rules_selected"] <= data["rules_total"]


def test_the_inventory_matches_the_axe_the_companion_actually_pins():
    """A stale inventory is the only way this guard lies. The pinned version lives in one file
    and is asserted against the one it was generated from."""
    package = json.loads(
        (_REPO / "runner/package.json").read_text(encoding="utf-8"))
    assert package["dependencies"]["axe-core"] == sc.inventory()["version"], (
        f"runner/package.json pins axe-core {package['dependencies']['axe-core']} but the "
        f"committed inventory was taken from {sc.inventory()['version']}. Run "
        f"`{sc.REBUILD_COMMAND}` and commit the result."
    )


# ── what the inventory says about DEPTH, recorded rather than assumed (#5, #7) ─────

#: Rule-owned criteria whose axe backing is one narrow rule rather than the criterion's whole
#: test. **Not a defect and not a hole** — a rule fires and can fail the page — but the registry's
#: rationale describes more than the rule does, and a coverage number that treats these as equal
#: to 1.4.3's full contrast maths is overstating what the scanner did.
#:
#: Written down here, with the rule that backs each, so the difference is a documented fact
#: somebody can act on rather than something rediscovered every few months by reading axe's
#: source. See `docs/web-accessibility/RESEARCH_CORRECTIONS.md` R15.
THIN_SCANNER_COVERAGE = {
    "1.3.5": "autocomplete-valid checks tokens that are PRESENT; a field with no autocomplete "
             "at all raises nothing",
    "1.4.4": "meta-viewport checks only that zoom is not disabled — nothing renders the page at "
             "200% or looks for clipping",
    "1.4.12": "avoid-inline-spacing checks only for inline !important that would block a "
              "spacing override — the overrides are never applied",
    "2.4.2": "document-title checks the title is present and non-empty, never that it describes "
             "the page",
    "3.1.2": "valid-lang validates lang values that exist; a foreign-language passage with no "
             "lang at all raises nothing",
    "3.3.2": "form-field-multiple-labels is the only rule tagged to 3.3.2. A missing label IS "
             "caught, by the `label` rule — which axe tags to 4.1.2, so the failure is filed "
             "under a different criterion than the registry's rationale implies",
}


def test_the_thin_spots_are_still_where_we_recorded_them():
    """Each of these criteria still has axe backing, and still only the narrow rule named.

    The test is here so that an axe upgrade which DEEPENS one of them shows up as a failure and
    the entry gets removed — a list of known limitations nobody revisits becomes a list of
    limitations that were fixed years ago and are still being apologised for.
    """
    axe = sc.axe_criteria()
    for number in THIN_SCANNER_COVERAGE:
        assert number in axe, f"{number} lost its scanner backing entirely"
    assert len(axe["3.3.2"]) == 1 and axe["3.3.2"][0] == "form-field-multiple-labels"
    assert axe["1.4.4"] == ("meta-viewport",)
    assert axe["1.4.12"] == ("avoid-inline-spacing",)
    assert axe["3.1.2"] == ("valid-lang",)
    assert axe["2.4.2"] == ("document-title",)
    assert axe["1.3.5"] == ("autocomplete-valid",)


def test_a_missing_form_label_is_caught_even_though_it_is_filed_under_4_1_2():
    """The nuance behind #5, pinned so nobody "fixes" it by re-tagging a vendor's rule.

    The registry's 3.3.2 rationale says the rule catches a missing programmatic label. It does —
    axe's `label` rule — but axe tags that rule to 4.1.2, so the finding arrives under Name, Role,
    Value. Nothing is missed; the attribution differs. Re-tagging axe's own rule inside our
    reader would be the platform quietly disagreeing with the scanner it cites.
    """
    assert "label" in sc.axe_criteria()["4.1.2"]
    assert "label" not in sc.axe_criteria()["3.3.2"]


def test_axe_reports_a_criterion_outside_the_level_we_audit_and_it_is_filtered_out():
    """#9. axe tags `scrollable-region-focusable` to 2.1.3, which is Level AAA and not one of the
    55. It is kept in the inventory as axe reports it — narrowing a vendor's statement inside the
    reader of it hides differences — and dropped by `coverage.record`, which is the layer that
    knows what the audit is about."""
    assert "2.1.3" in sc.axe_criteria()
    assert "2.1.3" not in _BY_NUMBER
