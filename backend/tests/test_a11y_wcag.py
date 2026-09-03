"""QA-04 — the platform's copy of WCAG 2.2 + ACT, and the grounding helper checkers use.

What these prove, against the task's acceptance criteria:

  AC1  a criterion number returns that criterion's exact WCAG 2.2 text — asserted against
       the committed dataset AND against wording quoted from w3.org, so a parser regression
       that silently truncated a criterion could not pass
  AC2  the text is present as grounding in the block a checker drops into its prompt
  AC3  a reload with a newer version needs no checker code change — proven by loading a
       second version alongside the first and reading both back
  AC4  an unknown criterion raises a clear error, never an empty string; plus coverage ≥90%

Beyond the ACs, and deliberately:

  * the dataset is complete and internally consistent — exactly 55 Level A/AA criteria, the
    exact expected numbers, no obsolete 4.1.1, every one carrying an explicit ACT answer
  * `no_act_rule` is a recorded fact for the 25 criteria with no ACT rule (team decision,
    2026-08-13), so a later phase reads "none exists" instead of guessing from an empty list
  * the standard is **one copy for the whole platform** and the app role cannot write it, so
    "no tenant amends the standard" is a database guarantee rather than a convention
  * a row that is not in the published set stops a reload and is named, rather than being
    deleted quietly or surviving unnoticed
"""
import json
import re

import psycopg
import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from apps.a11y import wcag_build
from apps.a11y.management.commands.build_wcag_dataset import _drift
from apps.a11y.models import ActRule, WcagCriterion, WcagTerm
from apps.a11y.wcag import (
    DEFAULT_VERSION,
    UnknownCriterion,
    UnpublishedRows,
    WcagNotLoaded,
    criterion,
    criterion_text,
    dataset,
    grounding,
    load_wcag,
    terms_for,
)

# The 55 Level A/AA success criteria of WCAG 2.2. Written out rather than derived from the
# dataset, so a parser that dropped or invented a criterion fails here instead of agreeing
# with itself. Source: W3C Recommendation, https://www.w3.org/TR/WCAG22/
EXPECTED_55 = [
    "1.1.1",
    "1.2.1", "1.2.2", "1.2.3", "1.2.4", "1.2.5",
    "1.3.1", "1.3.2", "1.3.3", "1.3.4", "1.3.5",
    "1.4.1", "1.4.2", "1.4.3", "1.4.4", "1.4.5", "1.4.10", "1.4.11", "1.4.12", "1.4.13",
    "2.1.1", "2.1.2", "2.1.4",
    "2.2.1", "2.2.2",
    "2.3.1",
    "2.4.1", "2.4.2", "2.4.3", "2.4.4", "2.4.5", "2.4.6", "2.4.7", "2.4.11",
    "2.5.1", "2.5.2", "2.5.3", "2.5.4", "2.5.7", "2.5.8",
    "3.1.1", "3.1.2",
    "3.2.1", "3.2.2", "3.2.3", "3.2.4", "3.2.6",
    "3.3.1", "3.3.2", "3.3.3", "3.3.4", "3.3.7", "3.3.8",
    "4.1.2", "4.1.3",
]

# The POC checkers judge against these (QA-01 `A11Y_CHECKER_CRITERIA`).
POC_CRITERIA = ["1.1.1", "1.3.1", "1.4.1", "2.5.3", "4.1.2"]


@pytest.fixture
def loaded(db):
    """The standard, loaded — no tenant involved, which is the point.

    Migration `0006_wcag_platform_wide` loads it, so it is already present on a migrated
    database; calling it explicitly keeps these tests independent of that and exercises the
    reload path at the same time.
    """
    return load_wcag()


# ── the committed dataset ────────────────────────────────────────────
def test_dataset_holds_exactly_the_55_level_a_aa_criteria():
    numbers = [c["number"] for c in dataset()["criteria"]]
    assert numbers == sorted(EXPECTED_55, key=lambda n: [int(p) for p in n.split(".")])
    assert len(numbers) == 55


def test_dataset_excludes_obsolete_and_aaa_criteria():
    numbers = {c["number"] for c in dataset()["criteria"]}
    assert "4.1.1" not in numbers          # retired in WCAG 2.2
    assert "1.4.6" not in numbers          # Contrast (Enhanced) is AAA
    assert {c["level"] for c in dataset()["criteria"]} == {"A", "AA"}


def test_every_criterion_carries_its_full_context():
    for crit in dataset()["criteria"]:
        assert crit["text"].strip(), f"{crit['number']} has no normative text"
        assert crit["handle"].strip()
        assert crit["guideline"]["handle"], f"{crit['number']} has no guideline"
        assert crit["principle"]["handle"], f"{crit['number']} has no principle"
        assert crit["added_in"] in ("2.0", "2.1", "2.2")
        assert crit["url"].startswith("https://www.w3.org/TR/WCAG22/#")


def test_version_dating_adds_up():
    """37 from 2.0 + 12 from 2.1 + 6 new in 2.2 = 55 — an independent check on the parse."""
    by_version = {}
    for crit in dataset()["criteria"]:
        by_version[crit["added_in"]] = by_version.get(crit["added_in"], 0) + 1
    assert by_version == {"2.0": 37, "2.1": 12, "2.2": 6}


def test_every_criterion_answers_the_act_question_explicitly():
    """30 have ACT rules, 25 have none — and the 25 say so rather than leaving a blank.

    ACT rules only exist for machine-testable criteria, so "no rule" is the correct answer
    for the rest. Recording it is what stops a later phase reading a missing key as a gap.
    """
    with_rules = [c for c in dataset()["criteria"] if not c["no_act_rule"]]
    without = [c for c in dataset()["criteria"] if c["no_act_rule"]]
    assert len(with_rules) == 30
    assert len(without) == 25
    for crit in dataset()["criteria"]:
        assert crit["no_act_rule"] == (not crit["act_rules"])
    # 1.4.1 Use of Color is one of the POC checkers and has no ACT rule at all —
    # exactly why it needs an AI judge rather than a deterministic scan.
    assert next(c for c in dataset()["criteria"] if c["number"] == "1.4.1")["no_act_rule"]


def test_referenced_act_rules_all_exist_and_are_w3c_published():
    rules = dataset()["act_rules"]
    for crit in dataset()["criteria"]:
        for rule_id in crit["act_rules"]:
            assert rule_id in rules, f"{crit['number']} cites unknown ACT rule {rule_id}"
            assert rules[rule_id]["w3c_published"], (
                f"{crit['number']} cites draft rule {rule_id}")
            assert rules[rule_id]["name"] and rules[rule_id]["applicability"]


def test_secondary_act_mappings_are_kept_out_of_the_primary_list():
    """A rule the ACT authors call stricter/looser than a criterion must not be presented
    as a conformance test for it — it is recorded separately."""
    rules = dataset()["act_rules"]
    role_valid = rules["674b10"]                        # maps to 1.3.1/4.1.2 as secondary
    assert role_valid["primary_criteria"] == []
    assert set(role_valid["secondary_criteria"]) == {"1.3.1", "4.1.2"}
    assert "674b10" not in next(
        c for c in dataset()["criteria"] if c["number"] == "1.3.1")["act_rules"]


def test_glossary_holds_every_defined_term():
    """The criteria are written in defined terms; a missing one grounds a judge in less
    than it appears to."""
    glossary = dataset()["glossary"]
    assert len(glossary) == 101
    for term_id, term in glossary.items():
        assert term_id.startswith("dfn-")
        assert term["term"].strip() and term["definition"].strip()
    assert glossary["dfn-cognitive-function-test"]["term"] == "cognitive function test"
    assert glossary["dfn-cognitive-function-test"]["definition"].startswith(
        "A task that requires the user to remember, manipulate, or transcribe information.")


def test_every_term_a_criterion_cites_is_defined():
    """The check that would have caught the 11 terms the first parser silently skipped."""
    glossary = dataset()["glossary"]
    for crit in dataset()["criteria"]:
        for term_id in crit["terms"]:
            assert term_id in glossary, f"{crit['number']} cites undefined {term_id}"


def test_criteria_link_to_the_terms_they_are_written_in():
    by_number = {c["number"]: c for c in dataset()["criteria"]}
    assert "dfn-cognitive-function-test" in by_number["3.3.8"]["terms"]
    assert "dfn-non-text-content" in by_number["1.1.1"]["terms"]
    # 1.4.1's wording uses no defined term — an empty list here is the correct answer.
    assert by_number["1.4.1"]["terms"] == []


def test_no_orphan_bullets_anywhere():
    """`<li><p>x</p></li>` used to put the bullet and its text on separate lines."""
    for crit in dataset()["criteria"]:
        for line in crit["text"].splitlines():
            assert line.strip() not in ("-", "*"), f"{crit['number']} has an orphan bullet"
    for term_id, term in dataset()["glossary"].items():
        for line in term["definition"].splitlines():
            assert line.strip() not in ("-", "*"), f"{term_id} has an orphan bullet"


def test_dataset_records_its_provenance():
    data = dataset()
    assert data["version"] == "2.2"
    assert "W3C Document License" in data["license"]
    assert "W3C" in data["attribution"]
    urls = {s["url"] for s in data["sources"]}
    assert "https://www.w3.org/TR/WCAG22/" in urls
    for source in data["sources"]:
        assert len(source["sha256"]) == 64 and source["bytes"] > 0
    assert data["counts"]["criteria"] == 55


# ── the exact text (AC1) ─────────────────────────────────────────────
def test_criterion_text_is_the_exact_published_wording(loaded):
    """Quoted from w3.org, not from our own file — so a truncating parser cannot pass."""
    assert criterion_text("1.4.1").splitlines()[0] == (
        "Color is not used as the only visual means of conveying information, indicating an"
    )
    assert criterion_text("2.5.3").startswith(
        "For user interface components with labels that include text or images of text, "
        "the name contains the text that is presented visually."
    )
    assert criterion_text("1.3.1") == (
        "Information, structure, and relationships conveyed through presentation can be "
        "programmatically determined or are available in text."
    )


def test_criterion_text_matches_the_committed_dataset_for_every_criterion(loaded):
    by_number = {c["number"]: c for c in dataset()["criteria"]}
    for number, expected in by_number.items():
        assert criterion_text(number) == expected["text"]


def test_criterion_keeps_the_exceptions_and_notes(loaded):
    """The parts most easily lost in extraction — a bare first sentence is not the rule."""
    non_text = criterion_text("1.1.1")
    for exception in ("Controls, Input", "Time-Based Media", "Test", "Sensory",
                      "CAPTCHA", "Decoration, Formatting, Invisible"):
        assert exception in non_text, f"1.1.1 lost its {exception!r} exception"
    assert "Note" in criterion_text("1.4.1")


def test_criterion_returns_the_whole_row_not_just_text(loaded):
    row = criterion("2.5.3")
    assert (row.handle, row.level, row.added_in) == ("Label in Name", "A", "2.1")
    assert row.guideline_handle == "Input Modalities"
    assert row.principle_handle == "Operable"
    assert row.act_rules == ["2ee8b8"]


# ── grounding a checker's prompt (AC2) ───────────────────────────────
def test_grounding_carries_the_criterion_into_the_prompt(loaded):
    block = grounding(["1.4.1"])
    assert "WCAG 2.2 Success Criterion 1.4.1 Use of Color (Level A)" in block
    assert criterion_text("1.4.1") in block
    assert "Intent:" in block


def test_grounding_can_omit_the_informative_intent(loaded):
    block = grounding(["1.4.1"], include_intent=False)
    assert criterion_text("1.4.1") in block
    assert "Intent:" not in block


def test_grounding_carries_the_defined_terms_the_rule_hinges_on(loaded):
    """3.3.8 is meaningless without W3C's definition of "cognitive function test"."""
    block = grounding(["3.3.8"])
    assert "Defined terms used above (WCAG glossary):" in block
    assert "cognitive function test: A task that requires the user to remember" in block


def test_grounding_can_omit_the_terms(loaded):
    block = grounding(["3.3.8"], include_terms=False)
    assert "Defined terms used above" not in block


def test_grounding_omits_the_terms_block_when_a_rule_uses_none(loaded):
    """1.4.1 cites no defined term — no empty "Defined terms" heading should appear."""
    assert "Defined terms used above" not in grounding(["1.4.1"])


def test_terms_are_deduplicated_across_criteria(loaded):
    """Two criteria sharing a term must not repeat its definition in one prompt."""
    ids = [t.term_id for t in terms_for(["1.1.1", "4.1.2"])]
    assert len(ids) == len(set(ids))
    assert "dfn-non-text-content" in ids


def test_terms_for_returns_nothing_when_no_criterion_defines_one(loaded):
    assert terms_for(["1.4.1"]) == []


def test_grounding_covers_every_poc_checker_criterion(loaded):
    """The four QA-03 checkers must all be groundable, or a checker ships un-grounded."""
    block = grounding(POC_CRITERIA)
    for number in POC_CRITERIA:
        assert criterion_text(number) in block


def test_grounding_fails_whole_block_on_one_unknown_criterion(loaded):
    """Better to fail than to hand back a prompt quietly missing one of its rules."""
    with pytest.raises(UnknownCriterion):
        grounding(["1.4.1", "9.9.9"])


def test_grounding_rejects_an_empty_request(loaded):
    with pytest.raises(ValueError):
        grounding([])


# ── the unknown-criterion case (AC4) ─────────────────────────────────
def test_unknown_criterion_raises_with_a_readable_message(loaded):
    with pytest.raises(UnknownCriterion) as err:
        criterion_text("9.9.9")
    assert "9.9.9" in str(err.value) and "WCAG 2.2" in str(err.value)


def test_a_aaa_criterion_is_unknown_not_empty(loaded):
    """1.4.6 is a real criterion but AAA — out of scope, and it must say so, not return ''."""
    with pytest.raises(UnknownCriterion):
        criterion_text("1.4.6")


def test_a_database_without_the_standard_loaded_is_told_so(db):
    """Distinguished from "unknown criterion": nothing is loaded, so nothing is knowable."""
    WcagCriterion.objects.all().delete()
    with pytest.raises(WcagNotLoaded) as err:
        criterion_text("1.1.1")
    assert "load_wcag" in str(err.value)


# ── loading, reloading, versioning (AC3) ─────────────────────────────
def test_load_writes_every_criterion_and_rule(loaded):
    assert WcagCriterion.objects.count() == 55
    assert ActRule.objects.count() == len(dataset()["act_rules"])
    assert ActRule.objects.filter(w3c_published=True).count() == 87
    assert WcagTerm.objects.count() == 101


def test_reloading_updates_in_place_and_never_duplicates(loaded):
    counts = load_wcag()
    assert counts["criteria_created"] == 0 and counts["criteria_updated"] == 55
    assert counts["rules_created"] == 0 and counts["terms_created"] == 0
    assert counts["terms_updated"] == 101
    assert WcagCriterion.objects.count() == 55


def test_reload_repairs_a_locally_edited_criterion(loaded):
    WcagCriterion.objects.filter(number="1.4.1").update(text="broken")
    load_wcag()
    assert criterion_text("1.4.1").startswith("Color is not used")


def test_a_newer_version_loads_alongside_the_old_one_with_no_code_change(loaded):
    """AC3: a WCAG release is a data reload. Checkers keep reading 2.2 until asked not to."""
    future = json.loads(json.dumps(dataset()))
    future["version"] = "2.3"
    future["criteria"][0]["text"] = "Revised wording for the next version."
    load_wcag(version="2.3", data=future)

    number = future["criteria"][0]["number"]
    assert criterion_text(number, version="2.3") == (
        "Revised wording for the next version.")
    assert criterion_text(number) == dataset()["criteria"][0]["text"]
    assert WcagCriterion.objects.count() == 110


def test_loading_a_version_the_dataset_does_not_hold_is_refused(loaded):
    with pytest.raises(ValueError) as err:
        load_wcag(version="9.9")
    assert "2.2" in str(err.value)


def test_default_version_matches_the_dataset():
    assert DEFAULT_VERSION == dataset()["version"]


# ── one copy for everyone, and nobody may amend it ───────────────────
@pytest.mark.django_db(transaction=True)
def test_the_app_role_can_read_the_standard_but_never_write_it():
    """"No tenant amends the standard" is a database guarantee, not a convention.

    Checked on a connection opened as the real app role — the Django test connection is the
    privileged migration role and could write regardless, so it could never show this.
    `transaction=True` so the rows are committed and the second connection can see them.
    """
    load_wcag()

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
            cur.execute("SELECT count(*) FROM a11y_wcagcriterion")
            assert cur.fetchone()[0] == 55
            cur.execute("SELECT count(*) FROM a11y_wcagterm")
            assert cur.fetchone()[0] == 101

            for statement in (
                "UPDATE a11y_wcagcriterion SET text = 'amended' WHERE number = '1.4.1'",
                "DELETE FROM a11y_wcagterm",
                "INSERT INTO a11y_actrule (id, created_at, updated_at, version, rule_id, "
                "name, description, applicability, expectation, background, url, "
                "w3c_published, primary_criteria, secondary_criteria) VALUES "
                "(gen_random_uuid(), now(), now(), '2.2', 'zzzzzz', 'x', '', '', '', '', "
                "'', false, '{}', '{}')",
            ):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cur.execute(statement)

            # Unchanged after every attempt.
            cur.execute("SELECT text FROM a11y_wcagcriterion WHERE number = '1.4.1'")
            assert cur.fetchone()[0].startswith("Color is not used")
    finally:
        raw.close()


def test_the_standard_is_one_copy_shared_by_every_tenant(db):
    """Two workspaces, one rulebook — the row count does not grow with tenants.

    This is the storage decision made visible: per tenant it was 250 rows each (2.5 million
    at 10,000 tenants); platform-wide it is 250, full stop.
    """
    from apps.tenancy.services import create_tenant

    load_wcag()
    before = WcagCriterion.objects.count() + WcagTerm.objects.count() + ActRule.objects.count()
    create_tenant(name="Alpha Co")
    create_tenant(name="Beta Co")
    after = WcagCriterion.objects.count() + WcagTerm.objects.count() + ActRule.objects.count()
    assert before == after == 250


def test_a_new_workspace_can_ground_a_checker_immediately(db):
    """The standard exists before any tenant does, so a checker is never un-grounded."""
    from apps.tenancy.services import create_tenant

    load_wcag()
    create_tenant(name="Fresh Co")
    assert criterion_text("1.1.1").startswith("All non-text content")


# ── a row that is not in the published set ───────────────────────────
def test_a_stray_row_stops_a_reload_and_is_named(loaded):
    """Nothing in the platform writes these. If one appears, a person decides — it is the
    only row that cannot be rebuilt from the committed file, so it is never auto-deleted."""
    WcagCriterion.objects.create(
        version="2.2", number="1.4.99", handle="House rule", level="AA", slug="x",
        text="Our own addition.",
    )
    with pytest.raises(UnpublishedRows) as err:
        load_wcag()
    assert "1.4.99" in str(err.value) and "criteria" in str(err.value)


def test_a_stray_row_is_not_deleted_by_the_refused_reload(loaded):
    """A refused load leaves the database exactly as it found it."""
    WcagCriterion.objects.create(
        version="2.2", number="1.4.99", handle="House rule", level="AA", slug="x", text="x")
    WcagCriterion.objects.filter(number="1.4.1").update(text="edited")
    with pytest.raises(UnpublishedRows):
        load_wcag()
    assert WcagCriterion.objects.filter(number="1.4.99").exists()
    assert criterion_text("1.4.1") == "edited"      # not half-applied either


def test_stray_glossary_terms_and_act_rules_are_caught_too(loaded):
    WcagTerm.objects.create(version="2.2", term_id="dfn-made-up", term="made up",
                            definition="x")
    ActRule.objects.create(version="2.2", rule_id="zzzzzz", name="Invented")
    with pytest.raises(UnpublishedRows) as err:
        load_wcag()
    assert "dfn-made-up" in str(err.value) and "zzzzzz" in str(err.value)


def test_load_command_loads_and_reports(db, capsys):
    WcagCriterion.objects.all().delete()
    WcagTerm.objects.all().delete()
    ActRule.objects.all().delete()
    call_command("load_wcag")
    assert "55 criteria created" in capsys.readouterr().out
    assert WcagCriterion.objects.count() == 55


def test_load_command_check_reports_what_is_loaded(loaded, capsys):
    call_command("load_wcag", "--check")
    out = capsys.readouterr().out
    assert "55 criteria, 101 glossary terms, 94 ACT rules" in out
    assert "matches the committed dataset" in out


def test_load_command_check_fails_when_something_is_missing(loaded):
    WcagTerm.objects.filter(term_id="dfn-non-text-content").delete()
    with pytest.raises(CommandError, match="does not match the committed dataset"):
        call_command("load_wcag", "--check")


def test_load_command_surfaces_a_stray_row(loaded):
    ActRule.objects.create(version="2.2", rule_id="zzzzzz", name="Invented")
    with pytest.raises(CommandError, match="zzzzzz"):
        call_command("load_wcag")


def test_an_older_version_is_not_treated_as_a_stray(loaded):
    """Loading 2.2 must not object to 2.1 rows kept deliberately alongside it."""
    WcagCriterion.objects.create(
        version="2.1", number="4.1.1", handle="Parsing", level="A", slug="parsing", text="x")
    load_wcag()                                     # must not raise
    assert WcagCriterion.objects.filter(version="2.1").count() == 1


# ── the build: parsing and its completeness proof ────────────────────
SECTION_HTML = """<p>A rule with an exception.</p>
   <dl><dt>Controls</dt><dd><p>Then it has a name.</p></dd></dl>
   <ul><li>first</li><li>second</li></ul>
   <div class="note"><div class="note-title"><span>Note</span></div><p>A note.</p></div>"""


def test_to_text_keeps_structure_and_every_word():
    text = wcag_build.to_text(SECTION_HTML)
    assert "* Controls" in text and "- first" in text and "Note" in text
    assert wcag_build.words(SECTION_HTML) == wcag_build._WORD.findall(text)


def test_to_text_drops_screenreader_only_markup():
    assert wcag_build.to_text('<p>a<span class="screenreader">|</span>b</p>') == "ab"


def test_completeness_check_catches_a_dropped_clause():
    crit = {"number": "1.1.1", "_body_html": SECTION_HTML, "text": "A rule with an exception."}
    with pytest.raises(ValueError) as err:
        wcag_build.verify_nothing_lost(crit)
    assert "1.1.1" in str(err.value) and "Controls" in str(err.value)


def test_completeness_check_catches_an_invented_word():
    crit = {"number": "1.4.1", "_body_html": "<p>Color is not used.</p>",
            "text": "Color is never used."}
    with pytest.raises(ValueError) as err:
        wcag_build.verify_nothing_lost(crit)
    assert "unexpected" in str(err.value)


def test_completeness_check_passes_on_a_faithful_extraction():
    crit = {"number": "1.4.1", "_body_html": SECTION_HTML,
            "text": wcag_build.to_text(SECTION_HTML)}
    wcag_build.verify_nothing_lost(crit)          # must not raise


ACT_MD = """---
id: abc123
name: Image has accessible name
description: |
  This rule checks that each image has an accessible name.
accessibility_requirements:
  wcag20:1.1.1: # Non-text Content (A)
    forConformance: true
    failed: not satisfied
  wcag20:4.1.2: # Name, Role, Value (A)
    secondary: This success criterion is less strict than this rule.
  wcag-technique:ARIA6: # Using aria-label
    forConformance: false
---

## Applicability

This rule applies to every HTML `img` element.

## Expectation

Each test target has an accessible name that is not empty.

## Background

Images need names.
"""


def test_act_rule_markdown_parses_into_its_parts():
    rule = wcag_build.parse_act_rule(ACT_MD)
    assert rule["id"] == "abc123"
    assert rule["name"] == "Image has accessible name"
    assert rule["description"] == "This rule checks that each image has an accessible name."
    assert "every HTML `img` element" in rule["applicability"]
    assert "accessible name that is not empty" in rule["expectation"]
    assert rule["background"] == "Images need names."


def test_act_rule_splits_primary_from_secondary_criteria():
    body = ACT_MD.split("---")[1]
    requirements = {}
    for key, block in re.findall(r"^  (wcag[\w-]*:[\d.\w]+):(.*?)(?=^  \S|\Z)",
                                 body, re.M | re.S):
        requirements[key] = {"secondary": ""} if "secondary:" in block else {
            "forConformance": True}
    primary, secondary = wcag_build.act_criteria(requirements)
    assert primary == ["1.1.1"]           # techniques are not criteria and are dropped
    assert secondary == ["4.1.2"]


def test_act_criteria_handles_no_requirements():
    assert wcag_build.act_criteria({}) == ([], [])
    assert wcag_build.act_criteria(None) == ([], [])


def test_multi_part_expectations_are_all_captured():
    md = ACT_MD.replace("## Expectation\n", "## Expectation 1\n") + (
        "\n## Expectation 2\n\nThe name describes the image.\n")
    rule = wcag_build.parse_act_rule(md)
    assert "not empty" in rule["expectation"]
    assert "describes the image" in rule["expectation"]


# ── the build's own validation gates ─────────────────────────────────
def _valid_criteria() -> list[dict]:
    return json.loads(json.dumps(dataset()["criteria"]))


def _guidelines() -> dict:
    return {c["guideline"]["number"]: c["guideline"]["handle"] for c in _valid_criteria()}


def _principles() -> dict:
    return {c["principle"]["number"]: c["principle"]["handle"] for c in _valid_criteria()}


def test_validate_passes_on_the_committed_dataset():
    wcag_build.validate(_valid_criteria(), _guidelines(), _principles())


@pytest.mark.parametrize(
    "break_it, expected",
    [
        (lambda cs: cs.pop(), "expected 55"),
        (lambda cs: cs.__setitem__(0, {**cs[0], "text": "  "}), "no normative text"),
        (lambda cs: cs.__setitem__(0, {**cs[0], "handle": ""}), "no handle"),
        (lambda cs: cs.__setitem__(
            0, {**cs[0], "guideline": {"number": "1.1", "handle": ""}}), "no guideline name"),
        (lambda cs: cs.__setitem__(
            0, {**cs[0], "principle": {"number": "1", "handle": ""}}), "no principle name"),
        (lambda cs: cs.__setitem__(0, {**cs[0], "level": "AAA"}), "has level"),
        (lambda cs: cs.__setitem__(0, {**cs[0], "number": "4.1.1"}), "obsolete"),
        (lambda cs: cs.__setitem__(0, {**cs[0], "no_act_rule": True}), "no_act_rule"),
        (lambda cs: cs.__setitem__(1, {**cs[0]}), "duplicate"),
    ],
)
def test_validate_fails_loudly_on_every_kind_of_gap(break_it, expected):
    criteria = _valid_criteria()
    break_it(criteria)
    with pytest.raises(ValueError) as err:
        wcag_build.validate(criteria, _guidelines(), _principles())
    assert expected in str(err.value)


def _glossary() -> dict:
    return json.loads(json.dumps(dataset()["glossary"]))


def test_validate_passes_on_the_committed_glossary():
    wcag_build.validate(_valid_criteria(), _guidelines(), _principles(), _glossary())


def test_validate_catches_a_criterion_citing_an_undefined_term():
    """The failure the first glossary parser would have caused, now caught at build time."""
    glossary = _glossary()
    glossary.pop("dfn-non-text-content")
    with pytest.raises(ValueError, match="cites undefined terms"):
        wcag_build.validate(_valid_criteria(), _guidelines(), _principles(), glossary)


@pytest.mark.parametrize("field, expected", [("term", "has no term"),
                                             ("definition", "has no definition")])
def test_validate_catches_an_empty_glossary_entry(field, expected):
    glossary = _glossary()
    glossary["dfn-non-text-content"][field] = "  "
    with pytest.raises(ValueError, match=expected):
        wcag_build.validate(_valid_criteria(), _guidelines(), _principles(), glossary)


def test_validate_checks_the_guideline_and_principle_counts():
    with pytest.raises(ValueError, match="guidelines"):
        wcag_build.validate(_valid_criteria(), {"1.1": "Text Alternatives"}, _principles())
    with pytest.raises(ValueError, match="principles"):
        wcag_build.validate(_valid_criteria(), _guidelines(), {"1": "Perceivable"})


# ── --check: is the committed file still what W3C publishes? ─────────
def test_drift_reports_nothing_when_the_dataset_is_current():
    assert _drift(dataset(), json.loads(json.dumps(dataset()))) == []


def test_drift_ignores_the_build_date():
    fresh = json.loads(json.dumps(dataset()))
    fresh["built_on"] = "2099-01-01"
    assert _drift(dataset(), fresh) == []


def test_drift_names_what_changed_upstream():
    fresh = json.loads(json.dumps(dataset()))
    fresh["version"] = "2.3"
    fresh["criteria"][0]["text"] = "reworded"
    fresh["criteria"][1]["act_rules"] = ["zzzzzz"]
    dropped = fresh["criteria"].pop()["number"]
    notes = "\n".join(_drift(dataset(), fresh))
    assert "version" in notes
    assert f"criterion {fresh['criteria'][0]['number']}: text changed" in notes
    assert f"criterion {fresh['criteria'][1]['number']}: act_rules changed" in notes
    assert f"criterion {dropped} no longer published" in notes


def test_drift_reports_a_new_upstream_criterion():
    fresh = json.loads(json.dumps(dataset()))
    fresh["criteria"].append({**fresh["criteria"][0], "number": "2.4.14"})
    assert _drift(dataset(), fresh) == ["criterion 2.4.14 is new upstream"]


# ── the whole build pipeline, offline ────────────────────────────────
# A miniature of the real documents: one principle, one guideline, two criteria (one of them
# AAA so the level filter has something to drop), a Note, an exception list and a change
# badge. Structurally identical to w3.org's markup — criteria nested inside their guideline,
# which is what made the parser attribute a child's text to its parent the first time.
MINI_WCAG22 = """<html><body>
<section class="principle" id="perceivable">
  <div class="header-wrapper"><h2 id="x1"><bdi class="secno">1. </bdi> Perceivable </h2></div>
  <section class="guideline" id="text-alternatives">
    <div class="header-wrapper"><h3 id="x11"><bdi class="secno">Guideline 1.1 </bdi>Text
      Alternatives</h3></div>
    <section id="non-text-content" class="guideline">
      <div class="header-wrapper"><h4 id="x111"><bdi class="secno">Success Criterion 1.1.1
        </bdi>Non-text Content</h4></div>
      <div class="doclinks"><a href="u">Understanding</a>
        <span class="screenreader">|</span></div>
      <p class="conformance-level">(Level A)</p>
      <p>All <a href="#dfn-non-text-content">non-text content</a> has a text
        alternative.</p>
      <dl><dt>Controls</dt><dd><p>Then it has a name.</p></dd></dl>
      <div class="note"><div class="note-title"><span>Note</span></div><p>A note.</p></div>
    </section>
    <section id="brand-new" class="guideline">
      <div class="header-wrapper"><h4 id="x112"><bdi class="secno">Success Criterion 1.1.2
        </bdi>Brand New</h4></div>
      <p class="conformance-level">(Level AA)</p>
      <p class="change">New</p>
      <p>Something added in 2.2.</p>
    </section>
    <section id="gold-plated" class="guideline">
      <div class="header-wrapper"><h4 id="x113"><bdi class="secno">Success Criterion 1.1.3
        </bdi>Gold Plated</h4></div>
      <p class="conformance-level">(Level AAA)</p>
      <p>Out of scope.</p>
    </section>
  </section>
</section>
<section id="conformance"><div class="header-wrapper"><h2 id="x5"><bdi class="secno">5.
  </bdi>Conformance</h2></div><p>Not a principle.</p></section>
<section id="glossary"><div class="header-wrapper"><h2 id="x6"><bdi class="secno">6.
  </bdi>Glossary</h2></div>
  <dl>
    <dt><dfn id="dfn-non-text-content" data-dfn-type="dfn">non-text content</dfn></dt>
    <dd><p>any content that is not a sequence of characters.</p></dd>
    <dt class="new"><dfn id="dfn-brand-new-thing" data-dfn-type="dfn">brand new thing</dfn></dt>
    <dd class="new"><p class="change">New</p><p>A thing added in 2.2.</p></dd>
    <dt><dfn id="dfn-pair-a">pair a</dfn> <dfn id="dfn-pair-b">pair b</dfn></dt>
    <dd><p>Two terms sharing one definition.</p>
      <ul><li><p>a bulleted clause</p></li></ul></dd>
    <dt><dfn id="dfn-last-one">last one</dfn></dt>
    <dd><p>Defined after the two-term entry.</p></dd>
  </dl>
</section>
</body></html>"""

MINI_UNDERSTANDING = """<html><body>
<section id="intent"><h2>Intent</h2><p>The intent is to help everyone.</p></section>
<section id="sufficient"><h3>Sufficient</h3>
  <a href="https://www.w3.org/WAI/WCAG22/Techniques/general/G94">G94</a></section>
<section id="failure"><h3>Failure</h3>
  <a href="https://www.w3.org/WAI/WCAG22/Techniques/failures/F30">F30</a></section>
</body></html>"""


def _mini_corpus(tmp_path):
    """Write a cache directory `build()` can run against without touching the network."""
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "wcag22.html").write_text(MINI_WCAG22, encoding="utf-8")
    # 1.1.1 exists in 2.0; 1.1.2 in neither, so it dates to 2.2.
    (cache / "wcag20.html").write_text(
        '<bdi class="secno">Success Criterion 1.1.1 </bdi>', encoding="utf-8")
    (cache / "wcag21.html").write_text(
        '<bdi class="secno">Success Criterion 1.1.1 </bdi>', encoding="utf-8")
    (cache / "act_testcases.json").write_text(json.dumps({"testcases": [
        {"ruleId": "abc123", "ruleName": "Image has accessible name",
         "ruleAccessibilityRequirements": {
             "wcag20:1.1.1": {"forConformance": True},
             "wcag20:4.1.2": {"secondary": "less strict"},
             "wcag-technique:ARIA6": {"forConformance": False}}},
    ]}), encoding="utf-8")
    (cache / "act_rules_dir.json").write_text(json.dumps([
        {"name": "image-accessible-name-abc123.md", "download_url": "https://example/x.md"},
        {"name": "__tests__", "download_url": "https://example/ignored"},
    ]), encoding="utf-8")
    (cache / "act_md__image-accessible-name-abc123.md").write_text(ACT_MD, encoding="utf-8")
    for slug in ("non-text-content", "brand-new"):
        (cache / f"und__{slug}.html").write_text(MINI_UNDERSTANDING, encoding="utf-8")
    return cache


@pytest.fixture
def mini_thresholds(monkeypatch):
    """Point the completeness gates at the miniature corpus's shape.

    The real thresholds (55 / 13 / 4) are asserted against the committed dataset elsewhere;
    relaxing them here is what lets the whole pipeline run on two criteria instead of
    committing a 512 KB copy of the standard as a fixture.
    """
    monkeypatch.setattr(wcag_build, "EXPECTED_IN_SCOPE", 2)
    monkeypatch.setattr(wcag_build, "EXPECTED_GUIDELINES", 1)
    monkeypatch.setattr(wcag_build, "EXPECTED_PRINCIPLES", 1)


def test_build_runs_end_to_end_from_cache(tmp_path, mini_thresholds):
    data = wcag_build.build(cache=_mini_corpus(tmp_path), log=lambda *a: None)

    assert data["version"] == "2.2"
    assert [c["number"] for c in data["criteria"]] == ["1.1.1", "1.1.2"]
    assert data["counts"] == {"criteria": 2, "act_rules": 1,
                              "act_rules_w3c_published": 1, "criteria_with_act_rules": 1,
                              "glossary_terms": 5}

    first = data["criteria"][0]
    assert first["level"] == "A" and first["added_in"] == "2.0"
    assert first["guideline"] == {"number": "1.1", "handle": "Text Alternatives"}
    assert first["principle"] == {"number": "1", "handle": "Perceivable"}
    assert "Controls" in first["text"] and "Note" in first["text"]
    assert first["intent"] == "The intent is to help everyone."
    assert first["techniques"] == {"sufficient": ["G94"], "advisory": [], "failure": ["F30"]}
    assert first["act_rules"] == ["abc123"] and first["no_act_rule"] is False

    assert first["terms"] == ["dfn-non-text-content"]

    second = data["criteria"][1]
    assert second["added_in"] == "2.2"
    assert "New" not in second["text"]          # the change badge is not criterion text
    assert second["no_act_rule"] is True
    assert len(data["sources"]) == 5


def test_build_parses_every_glossary_shape(tmp_path, mini_thresholds):
    """The two shapes that silently swallowed terms: a `<dt class="new">`, and a `<dt>`
    holding two `<dfn>`s (which made the old paired regex backtrack past what followed)."""
    glossary = wcag_build.build(cache=_mini_corpus(tmp_path),
                                log=lambda *a: None)["glossary"]
    assert set(glossary) == {"dfn-non-text-content", "dfn-brand-new-thing",
                             "dfn-pair-a", "dfn-pair-b", "dfn-last-one"}
    assert glossary["dfn-brand-new-thing"]["definition"] == "A thing added in 2.2."
    assert glossary["dfn-pair-a"]["term"] == "pair a"
    assert glossary["dfn-pair-b"]["term"] == "pair b"
    assert (glossary["dfn-pair-a"]["definition"]
            == glossary["dfn-pair-b"]["definition"])
    assert "- a bulleted clause" in glossary["dfn-pair-a"]["definition"]
    # The entry after the two-term one must survive — that is what used to be swallowed.
    assert glossary["dfn-last-one"]["definition"] == "Defined after the two-term entry."


def test_build_refuses_a_glossary_term_it_could_not_parse(tmp_path, mini_thresholds):
    cache = _mini_corpus(tmp_path)
    html = (cache / "wcag22.html").read_text(encoding="utf-8")
    # A dfn that is not inside a <dt> — declared but unreachable by the parser.
    html = html.replace("</dl>", '<p><dfn id="dfn-stray">stray</dfn></p></dl>')
    (cache / "wcag22.html").write_text(html, encoding="utf-8")
    with pytest.raises(ValueError, match="dfn-stray"):
        wcag_build.build(cache=cache, log=lambda *a: None)


def test_build_refuses_when_the_glossary_is_missing(tmp_path, mini_thresholds):
    cache = _mini_corpus(tmp_path)
    html = (cache / "wcag22.html").read_text(encoding="utf-8")
    (cache / "wcag22.html").write_text(
        html.replace('<section id="glossary">', '<section id="not-the-glossary">'),
        encoding="utf-8")
    with pytest.raises(ValueError, match="no glossary section"):
        wcag_build.build(cache=cache, log=lambda *a: None)


def test_build_keeps_a_guidelines_criteria_out_of_the_guidelines_own_text(
        tmp_path, mini_thresholds):
    """The bug that made a guideline section claim its first criterion's wording."""
    data = wcag_build.build(cache=_mini_corpus(tmp_path), log=lambda *a: None)
    assert "Something added in 2.2" not in data["criteria"][0]["text"]


def test_build_refuses_when_w3c_publishes_a_rule_with_no_source(tmp_path, mini_thresholds):
    cache = _mini_corpus(tmp_path)
    testcases = json.loads((cache / "act_testcases.json").read_text(encoding="utf-8"))
    testcases["testcases"].append({"ruleId": "ghost1", "ruleName": "Missing",
                                   "ruleAccessibilityRequirements": {}})
    (cache / "act_testcases.json").write_text(json.dumps(testcases), encoding="utf-8")
    with pytest.raises(ValueError, match="ghost1"):
        wcag_build.build(cache=cache, log=lambda *a: None)


def test_build_refuses_an_act_rule_with_no_id(tmp_path, mini_thresholds):
    cache = _mini_corpus(tmp_path)
    (cache / "act_md__image-accessible-name-abc123.md").write_text(
        ACT_MD.replace("id: abc123", "name_only: x"), encoding="utf-8")
    with pytest.raises(ValueError, match="no id"):
        wcag_build.build(cache=cache, log=lambda *a: None)


def test_build_writes_a_readable_file(tmp_path, mini_thresholds):
    data = wcag_build.build(cache=_mini_corpus(tmp_path), log=lambda *a: None)
    out = tmp_path / "nested" / "wcag.json"
    size = wcag_build.write(data, out)
    assert size > 0
    assert json.loads(out.read_text(encoding="utf-8"))["counts"]["criteria"] == 2


def test_fetch_uses_the_cache_and_only_downloads_once(tmp_path, monkeypatch):
    calls = []

    class _Response:
        def read(self):
            return b"payload"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        return _Response()

    monkeypatch.setattr(wcag_build.urllib.request, "urlopen", fake_urlopen)
    cache = tmp_path / "c"
    assert wcag_build.fetch("https://example/x", cache, name="x.html") == b"payload"
    assert wcag_build.fetch("https://example/x", cache, name="x.html") == b"payload"
    assert calls == ["https://example/x"]         # second call served from disk

    # Without a cache directory every call goes to the network.
    assert wcag_build.fetch("https://example/x", None, name="x.html") == b"payload"
    assert len(calls) == 2


def test_criterion_numbers_falls_back_to_the_wcag20_markup():
    assert wcag_build.criterion_numbers(
        '<bdi class="secno">Success Criterion 1.4.3 </bdi>') == {"1.4.3"}
    assert wcag_build.criterion_numbers(
        "<h4>Success Criterion 2.4.7 Focus Visible</h4>") == {"2.4.7"}
    assert wcag_build.criterion_numbers("<p>nothing here</p>") == set()


def _stub_build(monkeypatch, data):
    """Run the command against a known dataset instead of the network."""
    monkeypatch.setattr(wcag_build, "build", lambda *, cache, log: data)


def test_command_writes_the_dataset(tmp_path, monkeypatch, capsys):
    _stub_build(monkeypatch, json.loads(json.dumps(dataset())))
    out = tmp_path / "wcag22.json"
    call_command("build_wcag_dataset", "--out", str(out), "--cache", str(tmp_path / "c"))
    assert json.loads(out.read_text(encoding="utf-8"))["counts"]["criteria"] == 55
    assert "55 criteria" in capsys.readouterr().out


def test_command_check_passes_when_the_committed_file_is_current(tmp_path, monkeypatch,
                                                                 capsys):
    fresh = json.loads(json.dumps(dataset()))
    fresh["built_on"] = "2099-01-01"          # a rebuild always changes this; it is ignored
    _stub_build(monkeypatch, fresh)
    out = tmp_path / "wcag22.json"
    out.write_text(json.dumps(dataset()), encoding="utf-8")
    call_command("build_wcag_dataset", "--check", "--out", str(out))
    assert "matches the published sources" in capsys.readouterr().out


def test_command_check_fails_and_names_the_drift(tmp_path, monkeypatch):
    fresh = json.loads(json.dumps(dataset()))
    fresh["criteria"][0]["text"] = "W3C reworded this."
    _stub_build(monkeypatch, fresh)
    out = tmp_path / "wcag22.json"
    out.write_text(json.dumps(dataset()), encoding="utf-8")
    with pytest.raises(CommandError) as err:
        call_command("build_wcag_dataset", "--check", "--out", str(out))
    assert "out of date" in str(err.value) and "text changed upstream" in str(err.value)


def test_command_check_needs_an_existing_file(tmp_path, monkeypatch):
    _stub_build(monkeypatch, json.loads(json.dumps(dataset())))
    with pytest.raises(CommandError, match="does not exist"):
        call_command("build_wcag_dataset", "--check", "--out", str(tmp_path / "absent.json"))


def test_command_surfaces_a_build_failure(tmp_path, monkeypatch):
    def boom(*, cache, log):
        raise ValueError("expected 55 Level A/AA criteria, parsed 54")

    monkeypatch.setattr(wcag_build, "build", boom)
    with pytest.raises(CommandError, match="parsed 54"):
        call_command("build_wcag_dataset", "--out", str(tmp_path / "x.json"))


def test_sections_handles_nesting_and_an_unclosed_tag():
    nested = "<section id='a'>A<section id='b'>B</section>tail</section>"
    found = {re.search(r"id='(\w+)'", attrs).group(1): inner
             for attrs, inner in wcag_build.sections(nested)}
    assert found["a"] == "A<section id='b'>B</section>tail"
    assert found["b"] == "B"
    # A truncated document must not hang or raise — it yields what it can.
    assert list(wcag_build.sections("<section id='a'>A")) != []


# ── What the element checkers actually cover, pinned ────────────────────────
#
# Not a behaviour test — a guard on a number people quote. The build was described for weeks as
# "the AI half covers 11 of 55", which is what the ownership REGISTRY classifies as AI-owned.
# Five checkers are built and they cover five criteria; the other six are Phase 2. The gap
# between the two numbers reached a testing guide and could as easily have reached a proposal.
#
# So: change either list and this test fails, and whoever changes it has to restate the coverage
# rather than leave a stale figure standing somewhere nobody is looking.
#
# This heading said "three" and this paragraph said "four" while the assertion below said five —
# the count going stale in the prose OF THE TEST THAT GUARDS THE COUNT. The heading no longer
# carries a number at all; the one number that matters is asserted, where it cannot rot quietly.

def test_built_coverage_is_what_the_documents_claim():
    from apps.a11y.checkers.rules import CHECKERS
    from integrations.types import A11Y_CHECKER_CRITERIA, A11Y_JOURNEY_CRITERIA

    assert set(CHECKERS) == set(A11Y_CHECKER_CRITERIA), (
        "every built checker must appear in the criteria map, and vice versa"
    )
    ai = {c for pair in A11Y_CHECKER_CRITERIA.values() for c in pair}
    journey = {c for pair in A11Y_JOURNEY_CRITERIA.values() for c in pair}
    # Six checkers over six criteria, and NOT one each - the numbers matching is a coincidence
    # that has misled this team twice, so read the map rather than the count.
    #
    # `semantics` covers two criteria. 1.3.1 is covered twice over, by `semantics` and by
    # `structure`, because it is two different questions: one asks whether an element is
    # pretending to be a control or a heading, the other whether a container's visible
    # arrangement exists in the markup at all. Adding `structure` (24 Aug) did not widen what
    # the POC claims - it closed a hole inside a criterion already claimed
    # (SCOPE_GAP_INFO_AND_RELATIONSHIPS.md).
    #
    # `graphics` (QA-25) DID widen it, and deliberately: 1.4.11 Non-text Contrast was recorded
    # as rule-decided and checked by nothing at all, because axe-core ships no rule tagged
    # `wcag1411`. It is covered by this checker AND by `apps.a11y.page_rules` together - the
    # rule measures the controls, the judge looks at the pictures - and by neither alone.
    #
    # It was held back for part of 1 September, while the ownership registry was brought into
    # line with correction R14. The widening had been agreed on 27 August and recorded only in
    # prose; `ownership.json` still gave 1.4.11 to `rule`, and this map is what the AI owns.
    # `ownership.ENGINEERING_OVERRIDES` is where that decision now lives, and the count is six.
    #
    # This is the document-facing count, so it is the number a client-facing claim is read
    # against: the platform judges SIX things about a page, and 1.4.11 is both measured (by
    # page_rules) and judged (by graphics). `test_a11y_owner_capability` holds the other end -
    # that neither half may carry the criterion on its own.
    assert len(CHECKERS) == 6
    assert ai == {"1.1.1", "1.3.1", "1.4.1", "1.4.11", "2.5.3", "4.1.2"}

    from integrations.types import A11Y_HELD_BACK_CRITERIA
    assert A11Y_HELD_BACK_CRITERIA == {}, (
        "a check is held back and this count has not been told which, so the number above is "
        "a claim about coverage the platform is not making"
    )
    assert journey == {"2.1.1", "2.1.2", "2.4.3", "2.4.7", "2.4.11", "3.2.1", "3.2.2", "4.1.3"}


def test_ownership_registry_and_the_built_half_do_not_drift():
    """The registry's classification, and how much of it is actually built.

    `2.4.7` is the one that catches people out: the registry classifies it `ai`, no AI checker
    covers it, and the keyboard journey does. Count it in both and the human-only remainder comes
    out one too small — which is exactly how "22 criteria only a person can assess" was published
    when the answer is 23.
    """
    import json
    from pathlib import Path

    from apps.a11y import wcag

    data = json.loads(
        (Path(wcag.__file__).parent / "data" / "ownership.json").read_text(encoding="utf-8"))
    assert data["counts"]["by_owner"] == {"ai": 11, "human": 30, "rule": 14}
    assert data["counts"]["criteria"] == 55

    from integrations.types import A11Y_CHECKER_CRITERIA, A11Y_JOURNEY_CRITERIA

    rows = data["criteria"]
    owner = {n: rows[n]["owner"] for n in rows} if isinstance(rows, dict) else {
        r["number"]: r["owner"] for r in rows}
    journey = {c for pair in A11Y_JOURNEY_CRITERIA.values() for c in pair}
    ai_built = {c for pair in A11Y_CHECKER_CRITERIA.values() for c in pair}

    # Seven of the eight journey criteria are human-owned; 2.4.7 is the ai-owned one.
    assert sum(1 for c in journey if owner[c] == "human") == 7
    assert [c for c in sorted(journey) if owner[c] == "ai"] == ["2.4.7"]
    # 30 human-owned, 7 of them now reachable by the journey ⇒ 23 only a person can assess.
    assert sum(1 for c, o in owner.items() if o == "human" and c not in journey) == 23
    # And the distinct automated total the guide states.
    assert len({c for c, o in owner.items() if o == "rule"} | ai_built | journey) == 27
