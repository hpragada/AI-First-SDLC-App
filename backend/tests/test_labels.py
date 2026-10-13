"""Screen Words groups 2/3/5 — the words the backend puts in a refusal.

`apps.labels` exists because a refusal reaches a person's screen exactly as the backend wrote it.
These tests pin the two things that made the old messages unusable: a stored key where a name
belonged, and a sentence that named nothing the reader could act on.

Needs no database — the label maps read from the model enums, not from rows.
"""
import pytest

from apps.base import Role
from apps.labels import (
    artifact_status_label,
    capability_label,
    humanize,
    phase_label,
    role_label,
    run_status_label,
    work_item_state_label,
    work_item_type_label,
)


@pytest.mark.parametrize("key,expected", [
    ("product_owner", "Product Owner"),
    ("tech_lead", "Tech Lead"),
    ("qa_lead", "QA Lead"),
    ("security_engineer", "Security Engineer"),
    ("devops", "DevOps"),
])
def test_a_role_is_named_never_keyed(key, expected):
    assert role_label(key) == expected


def test_every_role_the_platform_has_is_covered():
    """Reads from `Role.choices`, so a role added to the enum cannot be forgotten here."""
    for key, label in Role.choices:
        assert role_label(key) == label
        assert "_" not in role_label(key)


def test_an_unknown_role_is_title_cased_not_dropped():
    # A key from an older row, or one added to the DB before this deploy.
    assert role_label("release_manager") == "Release Manager"


def test_no_role_ever_renders_empty():
    # The publish and drift refusals interpolate this mid-sentence; an empty string there would
    # read as "Only a  on this project can decide this."
    assert role_label(None)
    assert role_label("")


@pytest.mark.parametrize("status,expected", [
    # The one that matters: `staged` means a named person has been asked to decide, and the
    # platform's own word says nothing about anyone needing to act.
    ("staged", "Waiting for approval"),
    ("approved", "Approved"),
    ("published", "Published"),
    ("draft", "Draft"),
    ("superseded", "Superseded"),
])
def test_a_document_status_says_what_it_means(status, expected):
    assert artifact_status_label(status) == expected


def test_the_document_status_words_match_the_screen():
    """These must stay identical to frontend/src/features/observability/artifactStatus.tsx, or a
    document reads one way in a refusal and another way in the list behind it."""
    assert artifact_status_label("staged") == "Waiting for approval"


@pytest.mark.parametrize("status,expected", [
    ("awaiting_gate", "Waiting for approval"),
    ("running", "Running"),
    ("failed", "Failed"),
    ("rejected", "Changes requested"),
    # The one a first pass missed. A run is PENDING the moment it is created, so this is the
    # status the "this work item already has a run" refusal quotes most often.
    ("pending", "Queued"),
])
def test_a_run_status_reads_as_a_state_not_a_token(status, expected):
    assert run_status_label(status) == expected


def test_every_run_status_the_platform_has_is_covered():
    """Reads `Run.Status` itself. A first pass wrote this map from memory and got the set wrong in
    both directions — invented `queued` and `cancelled`, omitted `pending` and `stalled` — so a
    refusal quoted a humanized key instead of a label. This is the check that would have caught it.
    """
    from apps.labels import _RUN_STATUS_LABELS
    from apps.runs.models import Run

    enum_members = {status for status, _ in Run.Status.choices}
    # Membership, not the words: "Running" is both the right label and what `humanize` would
    # produce, so comparing against the fallback would fail on a perfectly good entry.
    missing = enum_members - set(_RUN_STATUS_LABELS)
    assert not missing, f"run statuses with no label: {sorted(missing)}"
    invented = set(_RUN_STATUS_LABELS) - enum_members
    assert not invented, f"labels for statuses that do not exist: {sorted(invented)}"

    for status in sorted(enum_members):
        label = run_status_label(status)
        assert label, status
        assert "_" not in label, f"{status} fell through to the raw key"


@pytest.mark.parametrize("capability,expected", [
    ("internal", "the platform"),
    ("docstore", "the documentation store"),
    ("tasktracker", "the task tracker"),
    ("testmgmt", "test management"),
])
def test_a_capability_is_named_by_what_it_does_not_by_its_vendor(capability, expected):
    # Non-negotiable #9: the API speaks capabilities, and so does the refusal. The vendor behind
    # each one is whatever connector the tenant bound, so it is deliberately not named.
    assert capability_label(capability) == expected
    for vendor in ("confluence", "jira", "xray", "figma"):
        assert vendor not in capability_label(capability).lower()


@pytest.mark.parametrize("state", [
    "proposed", "accepted", "in_progress", "in_review", "blocked", "done", "cancelled",
])
def test_a_work_item_state_is_the_board_column_name(state):
    label = work_item_state_label(state)
    assert "_" not in label
    assert label[0].isupper()


def test_work_item_types_and_states_come_from_the_model():
    assert work_item_state_label("in_progress") == "In Progress"
    assert work_item_type_label("test_case") == "Test Case"


@pytest.mark.parametrize("phase,expected", [
    ("06_task_breakdown", "Task Breakdown"),
    ("task_breakdown", "Task Breakdown"),
    # The ones plain title-casing got wrong — a refusal read "Prd documents can be published…".
    # Each must match frontend/src/types.ts PLANNING_PHASES exactly.
    ("03_prd", "PRD"),
    ("prd", "PRD"),
    ("05_ux_design", "UX Design"),
    ("11_cicd", "CI/CD"),
    ("09b_test_automation", "Test Automation"),
])
def test_a_phase_key_loses_its_ordinal_and_underscores(phase, expected):
    assert phase_label(phase) == expected


def test_every_catalog_phase_matches_the_frontends_spelling():
    """The backend has no display names of its own, so this reads the frontend's phase list and
    checks every phase the two share. A new acronym phase added to the frontend without a word in
    `_PHASE_WORDS` fails here instead of reaching a refusal misspelled."""
    import re
    from pathlib import Path

    types_ts = Path(__file__).resolve().parents[2] / "frontend" / "src" / "types.ts"
    pairs = re.findall(r'key: "([0-9a-z_]+)",\s*label: "([^"]+)"', types_ts.read_text("utf-8"))
    assert pairs, "found no phases in types.ts — the pattern needs updating"
    for key, label in pairs:
        assert phase_label(key) == label, (key, phase_label(key), label)


def test_humanize_is_the_floor_not_a_label():
    assert humanize("pointer_hash") == "Pointer hash"
    assert humanize(None) == ""
    assert humanize("") == ""
