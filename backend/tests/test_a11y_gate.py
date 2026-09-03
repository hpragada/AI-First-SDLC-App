"""QA-15 — the accessibility gate actually stops the pipeline.

Against the task's acceptance criteria:

  AC1  a run with an AI-confirmed Critical blocks
  AC2  a run with only low-confidence findings passes
  AC3  a run with a rule-scanner failure blocks
  AC4  a run that did not complete blocks with an "incomplete run" reason
  AC5  ≥ 90% coverage on the new code

**What makes this gate different from every earlier task.** Everything before it observed; this
one refuses. So the tests that matter most are the ones about *not* blocking: a low-confidence
finding must never hold a gate shut (QA-06's guardrail), a failing test or an open security
finding must never hold *this* condition shut (three defect families, three keys — D-A11Y-29),
and another story's problem must not block this story.

**Three states that all look like "no failures" are told apart**, because collapsing them is how
an incomplete check comes to read as a clean one (D-A11Y-3):

  judged, nothing blocks      -> satisfied, no detail
  captured but never judged   -> BLOCKED, "the check did not complete"
  never checked at all        -> satisfied, and the condition says exactly that
"""
from __future__ import annotations

import pytest

from apps.a11y.defects import record_a11y_findings
from apps.a11y.findings import record_run_findings
from apps.a11y.models import A11yScreenScan, WcagCriterion
from apps.a11y.report import SOURCE_AI, SOURCE_RULE, MergedReport, ReportRow
from apps.a11y.triage import TRIAGE_FAILURE, TRIAGE_REVIEW
from apps.gates.a11ygate import (
    A11Y_GATE_KEY,
    NOT_CHECKED_DETAIL,
    a11y_condition,
    has_been_checked,
    open_a11y_defects,
    unanswered_checks,
)
from apps.gates.a11ygate import evaluate as evaluate_a11y
from apps.gates.conditions import ConditionContext, conditions_for_phase, derived_evaluators
from apps.gates.models import Approval
from apps.gates.services import GateConditionsError, decide_gate
from apps.gates.testgate import BLOCKING_TESTS_KEY
from apps.projects.models import Project, ProjectProfile
from apps.quality.services import record_security_findings
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from integrations.types import A11Y_FAIL, A11Y_UNCERTAIN
from orchestration.activities import open_gate_core
from orchestration.types import AgentRunInput


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, workflow_id, decision, approver_id, comment, revise=False):
        self.calls.append((workflow_id, decision, approver_id, comment))


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Shop")
    story = WorkItem.objects.create(tenant=tenant, project=project, type=WorkItem.Type.STORY,
                                    feature_stream="ST-1", title="Checkout")
    spec = AgentSpec.objects.create(tenant=tenant, key="09b_test_automation", body_ref="x",
                                    semver="1.0.0", phase_label="testing")
    run = Run.objects.create(tenant=tenant, work_item=story, agent_spec=spec,
                             temporal_workflow_id="wf-a11y-gate")
    qa = User.objects.create_user(email="qa@acme.test", name="Carlos", tenant=tenant,
                                  password="pw")
    Membership.objects.create(tenant=tenant, user=qa, project=project, role="qa_lead")
    WcagCriterion.objects.get_or_create(
        version="2.2", number="1.1.1",
        defaults={"handle": "Non-text Content", "level": "A", "slug": "n", "text": "…"})
    WcagCriterion.objects.get_or_create(
        version="2.2", number="1.4.3",
        defaults={"handle": "Contrast (Minimum)", "level": "AA", "slug": "c", "text": "…"})
    return {"tenant": tenant, "t": str(tenant.id), "project": project, "p": str(project.id),
            "story": story, "w": str(story.id), "run": run, "spec": spec, "qa_id": str(qa.id)}


# ── helpers ───────────────────────────────────────────────────────────

def _row(**over) -> ReportRow:
    base = {
        "source": SOURCE_AI, "outcome": TRIAGE_FAILURE, "criteria": ("1.1.1",),
        "route": "/checkout", "selector": "img.hero",
        "evidence": 'alt="IMG_1234" is a filename', "confidence": 0.93,
        "suggested_fix": "describe what the image shows", "checker": "alt",
        "verdict": A11Y_FAIL,
    }
    base.update(over)
    return ReportRow(**base)


def _record(world, rows, *, run=None, routes=("/checkout",)):
    record_run_findings(
        tenant_id=world["t"], project_id=world["p"], run_id=str(run or world["run"].id),
        report=MergedReport(rows=list(rows), routes=list(routes), unjudged=[]))


def _reconcile(world):
    return record_a11y_findings(tenant_id=world["t"], project_id=world["p"],
                                run_id=str(world["run"].id))


def _scanned(world, route="/checkout", run=None):
    """A screen the scanner actually looked at — what tells 'clean' from 'never checked'."""
    used = run or world["run"]
    return A11yScreenScan.objects.create(
        tenant=world["tenant"], project=world["project"], run=used,
        run_key=str(used.id), route=route, url=f"http://localhost:5173{route}", violations=[])


def _ctx(world, **over):
    kwargs = {"tenant_id": world["t"], "work_item_id": world["w"],
              "run_id": str(world["run"].id), "project_id": world["p"]}
    kwargs.update(over)
    return ConditionContext(**kwargs)


def _evaluate(world, **over) -> dict:
    return evaluate_a11y(a11y_condition(), _ctx(world, **over))


def _inp(world, phase="testing"):
    return AgentRunInput(
        run_id=str(world["run"].id), tenant_id=world["t"], project_id=world["p"],
        work_item_id=world["w"], agent_spec_id=str(world["spec"].id), phase=phase,
        required_role="qa_lead",
    )


# ══ seeding — the condition exists, on the right gate, and is computed ════════════

def test_the_testing_gate_carries_the_accessibility_rule(db):
    keys = [c["key"] for c in conditions_for_phase("testing")]
    assert A11Y_GATE_KEY in keys
    assert BLOCKING_TESTS_KEY in keys, "it joins the blocking-test rule rather than replacing it"


def test_the_rule_is_derived_and_starts_unsatisfied(db):
    condition = next(c for c in conditions_for_phase("testing") if c["key"] == A11Y_GATE_KEY)
    assert condition["derived"] is True
    assert condition["required"] is True
    assert condition["satisfied"] is False


@pytest.mark.parametrize("phase", ["prd", "ux_design", "deployment", "implementation"])
def test_no_other_gate_carries_it(db, phase):
    assert A11Y_GATE_KEY not in {c["key"] for c in conditions_for_phase(phase)}


def test_the_design_gate_keeps_its_own_checklist_and_gains_no_a11y_rule(db):
    keys = {c["key"] for c in conditions_for_phase("ux_design")}
    assert "1.4.3" in keys, "the reviewer-attested design checklist is untouched"
    assert A11Y_GATE_KEY not in keys


def test_it_is_registered_with_an_evaluator(db):
    """QA-15a's completeness rule: a derived condition with no evaluator deadlocks its gate."""
    assert derived_evaluators()[A11Y_GATE_KEY] is evaluate_a11y


def test_a_foreign_condition_passes_through_untouched(world):
    other = {"key": "something_else", "required": True, "satisfied": False, "derived": True}
    assert evaluate_a11y(other, _ctx(world)) == other


# ══ AC1 — an AI-confirmed Critical blocks ════════════════════════════════════════

def test_an_ai_confirmed_critical_blocks_the_gate(world):
    _scanned(world)
    _record(world, [_row()])                      # 1.1.1 is Level A ⇒ critical
    _reconcile(world)

    result = _evaluate(world)
    assert result["satisfied"] is False
    assert "1 accessibility failure(s) still open" in result["detail"]
    assert "1.1.1" in result["detail"] and "/checkout" in result["detail"]
    assert "img.hero" in result["detail"], "the reviewer is told which element"


def test_a_level_aa_failure_blocks_too(world):
    _scanned(world)
    _record(world, [_row(criteria=("1.4.3",), selector="button.pay", checker="color")])
    _reconcile(world)
    assert _evaluate(world)["satisfied"] is False


def test_the_gate_reopens_clean_once_the_failure_is_fixed(world):
    _scanned(world)
    _record(world, [_row()])
    _reconcile(world)
    assert _evaluate(world)["satisfied"] is False

    # A later run where the element passes: the ledger resolves it, the defect closes.
    _record(world, [_row(outcome="pass", verdict="pass")])
    _reconcile(world)
    clean = _evaluate(world)
    assert clean["satisfied"] is True
    assert "detail" not in clean, "last week's failures must not linger on a green gate"


def test_a_resolved_defect_does_not_hold_the_gate(world):
    _scanned(world)
    _record(world, [_row()])
    _reconcile(world)
    defect = next(d for d in WorkItem.objects.filter(tenant_id=world["t"],
                                                     type=WorkItem.Type.DEFECT)
                  if (d.external_ref or {}).get("a11y_finding"))
    defect.state = WorkItem.State.DONE
    defect.save(update_fields=["state"])
    assert _evaluate(world)["satisfied"] is True


def test_many_failures_are_summarised_rather_than_listed_in_full(world):
    _scanned(world)
    _record(world, [
        _row(selector=f"img.n{i}", route="/checkout", criteria=("1.1.1",)) for i in range(8)
    ])
    _reconcile(world)
    detail = _evaluate(world)["detail"]
    assert "8 accessibility failure(s) still open" in detail
    assert "and 3 more" in detail, "the first five are named, the rest counted"


# ══ AC2 — low-confidence findings never block ════════════════════════════════════

def test_a_low_confidence_finding_never_blocks(world):
    """QA-06's guardrail at the gate: an unsure judgment goes to a person, not to a stop sign."""
    _scanned(world)
    _record(world, [_row(outcome=TRIAGE_REVIEW, confidence=0.41)])
    _reconcile(world)

    result = _evaluate(world)
    assert result["satisfied"] is True
    assert "detail" not in result


def test_a_finding_below_the_projects_confidence_bar_does_not_block(world):
    """QA-08's `min_confidence` reaches the gate through the defect loop, not a second rule."""
    ProjectProfile.objects.create(tenant=world["tenant"], project=world["project"],
                                  a11y={"gate": {"min_confidence": 0.99}})
    _scanned(world)
    _record(world, [_row(confidence=0.93)])
    _reconcile(world)
    assert _evaluate(world)["satisfied"] is True


def test_a_severity_the_project_does_not_block_on_does_not_block(world):
    ProjectProfile.objects.create(tenant=world["tenant"], project=world["project"],
                                  a11y={"gate": {"block_severities": ["critical"]}})
    _scanned(world)
    _record(world, [_row(criteria=("1.4.3",), checker="color")])   # Level AA ⇒ high
    _reconcile(world)
    assert _evaluate(world)["satisfied"] is True


# ══ AC3 — a rule-scanner failure blocks ══════════════════════════════════════════

def test_a_rule_scanner_failure_blocks(world):
    """A measurement, with no confidence to doubt — QA-06's "measurement beats opinion"."""
    _scanned(world)
    _record(world, [_row(source=SOURCE_RULE, confidence=None, checker="",
                         verdict="", evidence="axe reported image-alt (Critical)")])
    _reconcile(world)

    result = _evaluate(world)
    assert result["satisfied"] is False
    assert "1.1.1" in result["detail"]


def test_a_scanner_failure_blocks_even_under_a_high_confidence_bar(world):
    """A project must not be able to silence the scanner with a confidence dial."""
    ProjectProfile.objects.create(tenant=world["tenant"], project=world["project"],
                                  a11y={"gate": {"min_confidence": 0.99}})
    _scanned(world)
    _record(world, [_row(source=SOURCE_RULE, confidence=None, checker="", verdict="")])
    _reconcile(world)
    assert _evaluate(world)["satisfied"] is False


# ══ AC4 — an incomplete check blocks, and says so ════════════════════════════════

def test_an_element_that_never_got_a_verdict_blocks_with_an_incomplete_reason(world):
    _scanned(world)
    _record(world, [_row(outcome=TRIAGE_REVIEW, verdict=A11Y_UNCERTAIN, confidence=0.0,
                         evidence="no judge is registered in this workspace")])

    result = _evaluate(world)
    assert result["satisfied"] is False
    assert "did not complete" in result["detail"]
    assert "no verdict was recorded" in result["detail"]
    assert "/checkout" in result["detail"]


def test_an_unanswered_element_is_not_confused_with_an_unsure_one(world):
    """The discriminator is `verdict`. Both are `needs_review`; only one means nobody answered."""
    _scanned(world)
    _record(world, [
        _row(outcome=TRIAGE_REVIEW, verdict=A11Y_FAIL, confidence=0.4, selector="a.unsure"),
    ])
    assert unanswered_checks(tenant_id=world["t"], project_id=world["p"],
                             work_item_id=world["w"]) == []
    assert _evaluate(world)["satisfied"] is True


def test_a_project_can_choose_not_to_block_on_an_incomplete_check(world):
    ProjectProfile.objects.create(tenant=world["tenant"], project=world["project"],
                                  a11y={"gate": {"block_on_incomplete_run": False}})
    _scanned(world)
    _record(world, [_row(outcome=TRIAGE_REVIEW, verdict=A11Y_UNCERTAIN, confidence=0.0)])
    assert _evaluate(world)["satisfied"] is True


def test_a_real_failure_is_reported_ahead_of_an_incomplete_check(world):
    """Both wrong at once: the reviewer is shown the thing they can actually fix."""
    _scanned(world)
    _record(world, [
        _row(),
        _row(selector="a.skip", outcome=TRIAGE_REVIEW, verdict=A11Y_UNCERTAIN, confidence=0.0),
    ])
    _reconcile(world)
    detail = _evaluate(world)["detail"]
    assert "still open" in detail and "did not complete" not in detail


# ══ Silence — checked-and-clean vs never-checked ═════════════════════════════════

def test_a_work_item_nobody_checked_passes_but_says_so(world):
    result = _evaluate(world)
    assert result["satisfied"] is True
    assert result["detail"] == NOT_CHECKED_DETAIL


def test_a_screen_scanned_clean_passes_with_no_caveat(world):
    _scanned(world)
    result = _evaluate(world)
    assert result["satisfied"] is True
    assert "detail" not in result


def test_has_been_checked_reads_the_scan_not_the_findings(world):
    """A clean screen produces no findings, so findings cannot answer 'did we look?'."""
    assert has_been_checked(tenant_id=world["t"], project_id=world["p"],
                            work_item_id=world["w"]) is False
    _scanned(world)
    assert has_been_checked(tenant_id=world["t"], project_id=world["p"],
                            work_item_id=world["w"]) is True


# ══ Scoping — this story's problems, and only accessibility ══════════════════════

def test_another_storys_failure_does_not_block_this_gate(world):
    other = WorkItem.objects.create(tenant=world["tenant"], project=world["project"],
                                    type=WorkItem.Type.STORY, feature_stream="ST-2",
                                    title="Cart")
    other_run = Run.objects.create(tenant=world["tenant"], work_item=other,
                                   agent_spec=world["spec"], temporal_workflow_id="wf-2")
    _scanned(world, run=other_run, route="/cart")
    _record(world, [_row(route="/cart")], run=other_run.id, routes=("/cart",))
    _reconcile(world)

    assert _evaluate(world)["satisfied"] is True, "the defect hangs off the other story"
    assert evaluate_a11y(a11y_condition(),
                         ConditionContext(tenant_id=world["t"], work_item_id=str(other.id),
                                          project_id=world["p"]))["satisfied"] is False


def test_a_failing_test_does_not_hold_the_accessibility_condition_shut(world):
    """Three defect families, three keys (D-A11Y-29). A red suite has its own condition."""
    _scanned(world)
    WorkItem.objects.create(
        tenant=world["tenant"], project=world["project"], type=WorkItem.Type.DEFECT,
        parent=world["story"], title="TC-9 failing", state=WorkItem.State.IN_PROGRESS,
        external_ref={"test_ref": "TC-9"})
    assert _evaluate(world)["satisfied"] is True
    assert open_a11y_defects(tenant_id=world["t"], work_item_id=world["w"]) == []


def test_an_open_security_finding_does_not_hold_it_shut(world):
    _scanned(world)
    record_security_findings(
        tenant_id=world["t"], project_id=world["p"], work_item_id=world["w"],
        findings=[{"id": "SEC-1", "title": "Hardcoded secret", "severity": "critical",
                   "description": "key in source"}])
    assert _evaluate(world)["satisfied"] is True


def test_the_project_is_resolved_from_the_work_item_when_the_context_omits_it(world):
    _scanned(world)
    _record(world, [_row()])
    _reconcile(world)
    assert evaluate_a11y(
        a11y_condition(),
        ConditionContext(tenant_id=world["t"], work_item_id=world["w"]),
    )["satisfied"] is False


# ══ A policy nobody can read must not stop the gate being decided ═══════════════

def test_an_unreadable_policy_falls_back_to_the_default_rather_than_raising(world):
    ProjectProfile.objects.create(tenant=world["tenant"], project=world["project"],
                                  a11y={"gate": {"block_severities": ["serious"]}})
    _scanned(world)
    _record(world, [_row(outcome=TRIAGE_REVIEW, verdict=A11Y_UNCERTAIN, confidence=0.0)])
    result = _evaluate(world)
    assert result["satisfied"] is False, "the default blocks on an incomplete check"
    assert "did not complete" in result["detail"]


# ══ End to end through the real gate ════════════════════════════════════════════

def test_a_reviewer_cannot_approve_past_a_real_accessibility_failure(world):
    _scanned(world)
    _record(world, [_row()])
    _reconcile(world)
    approval_id = open_gate_core(_inp(world))
    sender = _Recorder()

    with pytest.raises(GateConditionsError) as exc:
        decide_gate(tenant_id=world["t"], approval_id=approval_id, user_id=world["qa_id"],
                    decision="approved", signal_sender=sender,
                    conditions=[{"key": A11Y_GATE_KEY, "satisfied": True}])

    assert A11Y_GATE_KEY in str(exc.value)
    assert "1.1.1" in str(exc.value), "the reason travels in the error, not just a refusal"
    assert sender.calls == [], "the workflow was never signalled"
    assert Approval.objects.get(id=approval_id).decision == Approval.Decision.PENDING


def test_the_same_gate_opens_once_the_failure_is_fixed(world):
    _scanned(world)
    _record(world, [_row()])
    _reconcile(world)
    approval_id = open_gate_core(_inp(world))

    _record(world, [_row(outcome="pass", verdict="pass")])
    _reconcile(world)

    sender = _Recorder()
    decide_gate(tenant_id=world["t"], approval_id=approval_id, user_id=world["qa_id"],
                decision="approved", signal_sender=sender)
    assert Approval.objects.get(id=approval_id).decision == Approval.Decision.APPROVED
    assert sender.calls and sender.calls[0][1] == "approved"


def test_a_rejection_is_never_blocked_by_the_accessibility_rule(world):
    _scanned(world)
    _record(world, [_row()])
    _reconcile(world)
    approval_id = open_gate_core(_inp(world))

    decide_gate(tenant_id=world["t"], approval_id=approval_id, user_id=world["qa_id"],
                decision="rejected", comment="fix the alt text first",
                signal_sender=_Recorder())
    assert Approval.objects.get(id=approval_id).decision == Approval.Decision.REJECTED


def test_the_gate_records_why_it_was_blocked_on_the_approval_when_it_opens(world):
    """The seeded condition is unsatisfied until it is computed — the QA-15a rule that this
    condition MUST have an evaluator, exercised through the real gate rather than asserted."""
    _scanned(world)
    approval_id = open_gate_core(_inp(world))
    stored = Approval.objects.get(id=approval_id)
    assert A11Y_GATE_KEY in {c["key"] for c in stored.conditions}

    sender = _Recorder()
    decide_gate(tenant_id=world["t"], approval_id=approval_id, user_id=world["qa_id"],
                decision="approved", signal_sender=sender)
    stored.refresh_from_db()
    condition = next(c for c in stored.conditions if c["key"] == A11Y_GATE_KEY)
    assert condition["satisfied"] is True, "computed at decide time, not left as seeded"
