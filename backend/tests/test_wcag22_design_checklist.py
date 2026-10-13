"""QA-11 — the design gate's checklist moves to WCAG 2.2 and is derived, not typed.

  AC1  no "WCAG 2.1" reference remains in 09 / 09b's accessibility content
  AC2  the checklist is built from the loaded 2.2 standard and asks the design-decidable set
  AC3  an approval opened before the change still functions (regression)
  AC4  the §8 reference sweep still passes on the edited agent body
  AC5  coverage — every one of the 55 criteria is asked or recorded as not asked

The load-bearing tests here are the ones that would fail *silently* otherwise: a criterion
that belongs to neither list (a question nobody decided to drop), a question naming a
criterion the standard does not have, and an exclusion whose stated reason contradicts the
QA-05 ownership registry. Each of those would leave a checklist that looks complete.
"""
from pathlib import Path

import pytest

from apps.a11y.models import CriterionOwnership, WcagCriterion
from apps.a11y.ownership import criteria_for
from apps.a11y.wcag import WcagNotLoaded
from apps.gates.models import Approval
from apps.gates.services import GateConditionsError, decide_gate
from apps.gates.wcag import (
    DESIGN_CHECKS,
    NOT_ASKED,
    NOT_ASKED_REASONS,
    ChecklistGap,
    describe_checklist,
    explain,
    verify_complete,
    wcag_aa_checklist,
)
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from orchestration.activities import open_gate_core
from orchestration.types import AgentRunInput

_AGENTS = Path(__file__).resolve().parents[2] / "agents"

#: The criteria the checklist asks about, restated here rather than imported from the module
#: under test — a list that agrees with itself proves nothing. Changing the checklist must be
#: a deliberate act that updates this line too.
_EXPECTED_ASKED = {
    "1.1.1", "1.4.1", "1.4.3", "1.4.11", "1.4.13", "2.1.1", "2.2.2", "2.4.3", "2.4.5",
    "2.4.6", "2.4.7", "2.4.11", "2.5.1", "2.5.7", "2.5.8", "3.2.3", "3.2.6", "3.3.1",
    "3.3.2", "3.3.3", "3.3.7", "3.3.8",
}


def _body(key: str) -> str:
    return (_AGENTS / key / "agent.md").read_text(encoding="utf-8")


# ── AC1: the agent bodies name 2.2, and nothing names 2.1 ──────────────
#: What "names an older standard" actually means. A bare `"2.1"` search cannot tell the version
#: of the standard from a criterion NUMBER: 2.1.1 Keyboard and 2.1.2 No Keyboard Trap are
#: current WCAG 2.2 criteria, and an agent that names them is right to. The blunt search stood
#: only while no accessibility agent body happened to cite them; on 2026-09-16, 09 was corrected
#: to point keyboard cases at the journey agent — which checks exactly 2.1.1 and 2.1.2 — and the
#: assertion failed on correct content. Tightened to the version strings themselves.
_OLD_STANDARD = ("WCAG 2.1", "2.1 AA", "2.1 Level AA", "WCAG 2.0")


def _names_an_older_standard(body: str) -> list[str]:
    return [token for token in _OLD_STANDARD if token in body]


def test_09_testing_carries_no_wcag_21_reference():
    assert _names_an_older_standard(_body("09_testing")) == []
    assert "WCAG 2.2 AA" in _body("09_testing")


def test_09_testing_cites_the_2_2_recommendation_by_its_published_year():
    """Verified against w3.org/TR/WCAG22/ while building: the current Recommendation is dated
    12 December 2024. The remembered answer was 2023 (the first Recommendation), which is why
    the year was checked rather than typed."""
    body = _body("09_testing")
    assert "W3C. (2024). *Web Content Accessibility Guidelines 2.2.*" in body
    assert "W3C, 2024" in body


def test_09b_names_the_current_standard_and_no_older_one():
    """**Retired and replaced (QA-12).** This asserted `"WCAG" not in 09b` because at QA-11 the
    agent had no accessibility content at all — and its own docstring named QA-11a as the task
    that would give it some. QA-11a duly did, and left this assertion behind, so it has been
    failing ever since against a body that is exactly right. What it was actually protecting is
    the same thing every other check in this file protects: 09b must name 2.2 and never 2.1.
    """
    body = _body("09b_test_automation")
    assert "WCAG 2.2 AA" in body
    assert "WCAG 2.1" not in body


def test_the_design_agent_names_the_current_standard():
    """**Uplifted on 2026-09-16, deliberately.** This used to pin 05 at WCAG 2.1 so that moving
    it would be somebody's decision rather than a side effect. The team made that decision: the
    platform, its gate and agents 09/09b/09c/09d all work to 2.2, and a live project was found
    registering an accessibility spec that said "WCAG 2.1" while the gate asked 2.2 questions.
    The guard is not weakened — it still fails if anyone puts 2.1 back.

    Note what this does NOT assert: 05 covers nine criteria in its own Step 7 table, and naming
    2.2 does not by itself make it teach the six criteria new in 2.2 (2.4.11, 2.5.7, 2.5.8,
    3.2.6, 3.3.7, 3.3.8). Those are asked of the designer at this gate, and widening the agent's
    own table is part of the shift-left work, not of this correction.
    """
    body = _body("05_ux_design")
    assert "WCAG 2.2 AA" in body
    assert "WCAG 2.1" not in body


# ── AC4: the §8 reference sweep stays clean on the edited body ─────────
def test_reference_sweep_is_clean_on_09():
    forbidden = [".md", "docs/", "claude.md", "tasks.md", "reply approved", "/sdlc:"]
    body = _body("09_testing").lower()
    assert not [token for token in forbidden if token in body]


# ── AC2: the checklist is derived from the loaded standard ────────────
def test_checklist_asks_the_design_decidable_set(db):
    assert {c["key"] for c in wcag_aa_checklist()} == _EXPECTED_ASKED


def test_labels_carry_the_published_title_and_level(db):
    by_key = {c["key"]: c["label"] for c in wcag_aa_checklist()}
    row = WcagCriterion.objects.get(version="2.2", number="1.4.3")
    assert row.handle in by_key["1.4.3"]           # the standard's own title, not a copy
    assert f"Level {row.level}" in by_key["1.4.3"]
    assert by_key["1.4.3"].startswith("1.4.3 ")


def test_every_item_is_required_unsatisfied_and_carries_its_reason(db):
    for item in wcag_aa_checklist():
        assert item["required"] and not item["satisfied"]
        assert item["note"]                        # why it belongs at design time


def test_the_checklist_follows_the_loaded_standard_not_a_hardcoded_string(db):
    """The point of deriving it: change the loaded title, and the gate says the new one."""
    row = WcagCriterion.objects.get(version="2.2", number="1.1.1")
    row.handle = "Non-text Content (revised wording)"
    row.save(update_fields=["handle"])
    label = next(c["label"] for c in wcag_aa_checklist() if c["key"] == "1.1.1")
    assert "revised wording" in label


def test_every_criterion_wcag_22_introduced_is_asked(db):
    """A version uplift that asked none of the new questions would be a rename, not an uplift.
    Derived from the data (`added_in`), so it cannot agree with a hand-typed list by accident."""
    new_in_22 = set(
        WcagCriterion.objects.filter(version="2.2", added_in="2.2")
        .values_list("number", flat=True)
    )
    assert new_in_22, "no criteria are marked as introduced in 2.2 — check the loaded dataset"
    assert new_in_22 <= {c["key"] for c in wcag_aa_checklist()}


def test_two_of_the_old_nine_leave_and_both_are_accounted_for(db):
    """1.4.4 and 4.1.2 were on the hand-typed 2.1 list and are not asked now. That is a
    decision (D-A11Y-7), so each must carry a recorded reason rather than just vanish."""
    asked = {c["key"] for c in wcag_aa_checklist()}
    for number in ("1.4.4", "4.1.2"):
        assert number not in asked
        assert "not asked at the design gate" in explain(number)


def test_seven_of_the_old_nine_survive(db):
    """The rest of the old checklist is still asked — this is an uplift, not a replacement."""
    asked = {c["key"] for c in wcag_aa_checklist()}
    assert {"1.1.1", "1.4.3", "2.1.1", "2.4.3", "2.4.7", "3.3.1", "3.3.2"} <= asked


# ── AC5: nothing falls between the two lists ──────────────────────────
def test_every_loaded_criterion_is_asked_or_recorded_as_not_asked(db):
    assert verify_complete() == WcagCriterion.objects.filter(version="2.2").count() == 55


def test_a_criterion_in_neither_list_is_a_loud_gap(db):
    """Proves the coverage check is not vacuous: plant a criterion, watch the check fail."""
    WcagCriterion.objects.create(
        version="2.2", number="9.9.9", handle="Planted", level="AA", slug="planted",
        text="planted for this test",
    )
    with pytest.raises(ChecklistGap) as exc:
        verify_complete()
    assert "9.9.9" in str(exc.value)


def test_a_question_naming_an_unknown_criterion_stops_the_gate(db):
    """The other direction: the standard moved and a question no longer matches anything."""
    WcagCriterion.objects.filter(version="2.2", number="2.5.8").delete()
    with pytest.raises(ChecklistGap) as exc:
        wcag_aa_checklist()
    assert "2.5.8" in str(exc.value)


def test_an_unloaded_standard_stops_the_gate_rather_than_opening_it_empty(db):
    """The failure that must never be quiet: no standard loaded would otherwise produce an
    empty checklist, and an empty checklist approves every design instantly."""
    WcagCriterion.objects.filter(version="2.2").delete()
    with pytest.raises(WcagNotLoaded) as exc:
        wcag_aa_checklist()
    assert "load_wcag" in str(exc.value)
    with pytest.raises(WcagNotLoaded):
        verify_complete()


def test_verify_complete_names_a_question_the_standard_no_longer_has(db):
    """A criterion this module knows about that the loaded standard dropped — the direction a
    version change would break in."""
    WcagCriterion.objects.filter(version="2.2", number="1.2.2").delete()
    with pytest.raises(ChecklistGap) as exc:
        verify_complete()
    assert "1.2.2" in str(exc.value)


def test_no_criterion_is_both_asked_and_excluded(db):
    excluded = [number for numbers in NOT_ASKED.values() for number in numbers]
    assert len(excluded) == len(set(excluded))              # no criterion in two buckets
    assert not _EXPECTED_ASKED & set(excluded)


def test_every_exclusion_bucket_has_a_stated_reason():
    assert set(NOT_ASKED) == set(NOT_ASKED_REASONS)
    assert all(reason.strip() for reason in NOT_ASKED_REASONS.values())


# ── the exclusion reasons are cross-checked against the QA-05 registry ─
def test_criteria_excluded_as_machine_checked_really_are_machine_owned(db):
    """The reason "a rule or the AI decides this on the built page" is a claim about the
    ownership registry. If the registry ever says a person owns one of these, the reason on
    the design gate has quietly become false — so it fails here rather than misleading a
    reviewer."""
    machine_owned = set(criteria_for(owner="rule")) | set(criteria_for(owner="ai"))
    assert set(NOT_ASKED["checked_on_the_built_page"]) <= machine_owned


def test_criteria_excluded_as_human_ones_really_are_human_owned(db):
    human_owned = set(criteria_for(owner="human"))
    for bucket in (
        "needs_media_that_does_not_exist_yet",
        "only_visible_when_the_app_runs",
        "answerable_at_design_but_not_asked",
    ):
        assert set(NOT_ASKED[bucket]) <= human_owned, bucket


def test_the_registry_is_loaded_so_those_cross_checks_are_not_vacuous(db):
    assert CriterionOwnership.objects.filter(version="2.2").count() == 55


# ── explain() / describe_checklist(): the reviewer-facing answers ──────
def test_explain_answers_for_an_asked_criterion(db):
    assert explain("1.4.3").startswith("asked at the design gate:")
    assert "4.5:1" in explain("1.4.3")


def test_explain_answers_for_a_criterion_that_is_not_asked():
    assert "recorded audio or video" in explain("1.2.2")
    assert "operate the built app" in explain("4.1.3")


def test_explain_refuses_a_criterion_nobody_decided_about():
    with pytest.raises(ChecklistGap):
        explain("9.9.9")


def test_describe_checklist_prints_the_whole_set_for_a_human_reader():
    text = describe_checklist()
    assert f"({len(DESIGN_CHECKS)} criteria, WCAG 2.2 AA)" in text
    for check in DESIGN_CHECKS:
        assert check.question in text
    for reason in NOT_ASKED_REASONS.values():
        assert reason in text


# ── AC3: an approval opened before the change still functions ─────────
@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Platform")
    item = WorkItem.objects.create(tenant=tenant, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=tenant, key="05_ux_design", body_ref="x")
    run = Run.objects.create(
        tenant=tenant, work_item=item, agent_spec=spec, temporal_workflow_id="wf-qa11"
    )
    designer = User.objects.create_user(
        email="d@acme.test", name="Dee", tenant=tenant, password="pw"
    )
    Membership.objects.create(tenant=tenant, user=designer, project=project, role="designer")
    return {"tenant": tenant, "project": project, "item": item, "run": run,
            "designer_id": str(designer.id)}


def _legacy_approval(world) -> Approval:
    """A design gate as it was opened before QA-11 — the hand-typed WCAG 2.1 nine."""
    return Approval.objects.create(
        tenant=world["tenant"], work_item=world["item"], run=world["run"],
        required_role="designer",
        conditions=[
            {"key": key, "label": label, "required": True, "satisfied": False}
            for key, label in [
                ("1.1.1", "Non-text content has text alternatives (alt / aria-label)"),
                ("1.4.3", "Contrast (minimum): text ≥ 4.5:1, large text & UI ≥ 3:1"),
                ("1.4.4", "Text resizes to 200% without loss of content or function"),
                ("2.1.1", "All functionality is keyboard operable"),
                ("2.4.3", "Focus order matches visual order"),
                ("2.4.7", "Keyboard focus indicator is visible"),
                ("3.3.1", "Form errors are identified in text (not color alone)"),
                ("3.3.2", "Form fields have visible labels or instructions"),
                ("4.1.2", "Components expose name, role, and value (ARIA)"),
            ]
        ],
    )


def test_a_gate_opened_before_the_change_still_blocks_and_still_approves(world):
    """The one thing a reviewer would notice if we got it wrong: a design already waiting for
    approval must keep the checklist it was opened with, including 1.4.4 and 4.1.2, which the
    new checklist no longer asks."""
    approval = _legacy_approval(world)
    assert {c["key"] for c in approval.conditions} & {"1.4.4", "4.1.2"}

    with pytest.raises(GateConditionsError):
        decide_gate(tenant_id=str(world["tenant"].id), approval_id=str(approval.id),
                    user_id=world["designer_id"], decision="approved",
                    signal_sender=lambda *a, **k: None)

    result = decide_gate(
        tenant_id=str(world["tenant"].id), approval_id=str(approval.id),
        user_id=world["designer_id"], decision="approved",
        conditions=[{"key": c["key"], "satisfied": True} for c in approval.conditions],
        signal_sender=lambda *a, **k: None,
    )
    assert result["decision"] == "approved"
    assert len(result["conditions"]) == 9          # its own nine, not the new checklist


def test_a_gate_opened_after_the_change_carries_the_new_checklist(world):
    approval_id = open_gate_core(AgentRunInput(
        run_id=str(world["run"].id), tenant_id=str(world["tenant"].id),
        project_id=str(world["project"].id), work_item_id=str(world["item"].id),
        agent_spec_id="s", phase="ux_design", required_role="designer",
    ))
    approval = Approval.objects.get(id=approval_id)
    assert {c["key"] for c in approval.conditions} == _EXPECTED_ASKED
    assert all(not c["satisfied"] for c in approval.conditions)
