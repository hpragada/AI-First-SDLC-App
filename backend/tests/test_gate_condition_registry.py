"""QA-15a — derived gate conditions are refreshed by their own evaluator, not all by one.

Against the task's acceptance criteria:

  AC1  a gate carrying two derived conditions refreshes each by its own evaluator
  AC2  a derived condition with no registered evaluator passes through, nothing raises
  AC3  the existing test gate is unchanged
  AC4  ≥ 90% coverage on the new code

**The bug this fixes, stated exactly.** `refresh_derived` used to hand *every* derived
condition to the **test** evaluator, which returns anything it does not recognise untouched.
One derived condition existed, so nothing was wrong. Add a second and it would be handed to the
wrong evaluator, returned as-is, and keep the value it was seeded with when the gate opened.

That is not a subtly wrong answer, and the two tests at the bottom of this file are here to say
why: a fresh derived condition is seeded `satisfied: False`, and `_merge_conditions` refuses a
reviewer's attestation on a derived condition **on purpose** — so a derived condition that never
refreshes is a gate **nobody in the platform can ever approve**. QA-15 would have shipped that
on every story in every project.

**The test that outlives this task** is `test_every_derived_condition_has_an_evaluator`. It walks
every phase the platform can open a gate for, collects the derived conditions, and fails if any
key is unregistered. The original bug was invisible precisely because nothing checked that a
derived condition was connected to anything.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from apps.gates import conditions as conditions_mod
from apps.gates.conditions import (
    ConditionContext,
    conditions_for_phase,
    derived_evaluators,
    refresh_derived,
)
from apps.gates.models import Approval
from apps.gates.services import GateConditionsError, decide_gate
from apps.gates.testgate import BLOCKING_TESTS_KEY, blocking_tests_condition
from apps.gates.testgate import evaluate as evaluate_blocking_tests
from apps.projects.models import Project
from apps.quality import services as quality_services
from apps.registry.catalog import ACTIVE_AGENT_CATALOG
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem

#: A stand-in for the accessibility condition QA-15 adds. Deliberately NOT the real one: this
#: task's job is the dispatch, and building the a11y evaluator here would be building QA-15.
DEMO_KEY = "demo_derived_condition"


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, workflow_id, decision, approver_id, comment, revise=False):
        self.calls.append((workflow_id, decision, approver_id, comment))


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="App")
    story = WorkItem.objects.create(tenant=tenant, project=project, type=WorkItem.Type.STORY,
                                    feature_stream="ST-1", title="Login")
    spec = AgentSpec.objects.create(tenant=tenant, key="09_testing", body_ref="x",
                                    phase_label="testing")
    run = Run.objects.create(tenant=tenant, work_item=story, agent_spec=spec,
                             temporal_workflow_id="wf-t")
    qa = User.objects.create_user(email="qa@acme.test", name="Carlos", tenant=tenant,
                                  password="pw")
    Membership.objects.create(tenant=tenant, user=qa, project=project, role="qa_lead")
    return {"tenant": tenant, "t": str(tenant.id), "project": project, "story": story,
            "run": run, "qa_id": str(qa.id)}


def _derived(key=DEMO_KEY, **over) -> dict:
    base = {"key": key, "label": "a second computed rule", "required": True,
            "satisfied": False, "derived": True}
    base.update(over)
    return base


def _register(monkeypatch, key, evaluator):
    """Add one evaluator for the duration of a test. The registry is module state, so it is
    patched rather than mutated — a leak here would silently change every later test."""
    monkeypatch.setitem(conditions_mod._DERIVED_EVALUATORS, key, evaluator)


def _approval(world, conditions):
    return Approval.objects.create(
        tenant=world["tenant"], run=world["run"], work_item=world["story"],
        required_role="qa_lead", conditions=conditions)


# ══ AC1 — two derived conditions, each by its own evaluator ═══════════════════════

def test_two_derived_conditions_are_each_refreshed_by_their_own_evaluator(world, monkeypatch):
    seen = []

    def demo(condition, context):
        seen.append(context)
        return {**condition, "satisfied": True, "detail": "computed by the demo evaluator"}

    _register(monkeypatch, DEMO_KEY, demo)
    out = refresh_derived([blocking_tests_condition(), _derived()],
                          tenant_id=world["t"], work_item_id=str(world["story"].id))

    blocking, demo_out = out
    assert blocking["key"] == BLOCKING_TESTS_KEY and blocking["satisfied"] is True, \
        "no open test defects ⇒ the test rule refreshed to satisfied"
    assert demo_out["satisfied"] is True
    assert demo_out["detail"] == "computed by the demo evaluator"
    assert len(seen) == 1, "the demo evaluator ran exactly once"


def test_the_test_evaluator_no_longer_sees_a_condition_that_is_not_its_own(world, monkeypatch):
    """The bug itself. Before QA-15a every derived condition went through this function."""
    routed = []

    def spy(condition, context):
        routed.append(condition["key"])
        return evaluate_blocking_tests(condition, context)

    _register(monkeypatch, BLOCKING_TESTS_KEY, spy)
    _register(monkeypatch, DEMO_KEY, lambda c, ctx: {**c, "satisfied": True})
    refresh_derived([blocking_tests_condition(), _derived()],
                    tenant_id=world["t"], work_item_id=str(world["story"].id))

    assert routed == [BLOCKING_TESTS_KEY]


def test_each_evaluator_gets_the_same_context_shape(world, monkeypatch):
    got = {}

    def demo(condition, context):
        got["ctx"] = context
        return condition

    _register(monkeypatch, DEMO_KEY, demo)
    refresh_derived([_derived()], tenant_id=world["t"], work_item_id=str(world["story"].id),
                    run_id=world["run"].id, project_id=world["project"].id)

    ctx = got["ctx"]
    assert isinstance(ctx, ConditionContext)
    assert ctx.tenant_id == world["t"]
    assert ctx.work_item_id == str(world["story"].id)
    assert ctx.run_id == str(world["run"].id), "QA-15 needs the run whose findings it judges"
    assert ctx.project_id == str(world["project"].id), "QA-15 needs the project's a11y policy"


def test_the_context_is_optional_where_a_caller_has_no_run_or_project(world, monkeypatch):
    got = {}

    def demo(condition, context):
        got["ctx"] = context
        return condition

    _register(monkeypatch, DEMO_KEY, demo)
    refresh_derived([_derived()], tenant_id=world["t"], work_item_id=str(world["story"].id))
    assert got["ctx"].run_id is None and got["ctx"].project_id is None


def test_the_context_cannot_be_edited_by_an_evaluator(world):
    """Frozen: one evaluator must not be able to change what a later one is told."""
    ctx = ConditionContext(tenant_id=world["t"], work_item_id=str(world["story"].id))
    with pytest.raises(FrozenInstanceError):
        ctx.tenant_id = "somebody-else"  # type: ignore[misc]


# ══ AC2 — an unregistered derived condition passes through ═══════════════════════

def test_a_derived_condition_with_no_evaluator_passes_through_untouched(world):
    condition = _derived(key="nobody_owns_this")
    out = refresh_derived([condition], tenant_id=world["t"],
                          work_item_id=str(world["story"].id))
    assert out == [condition], "unchanged, and nothing raised"


def test_a_reviewer_attested_condition_is_never_handed_to_an_evaluator(world, monkeypatch):
    called = []
    _register(monkeypatch, "1.4.3", lambda c, ctx: called.append(c) or c)
    attested = {"key": "1.4.3", "label": "contrast", "required": True, "satisfied": True}
    assert refresh_derived([attested], tenant_id=world["t"],
                           work_item_id=str(world["story"].id)) == [attested]
    assert called == [], "no `derived` flag ⇒ not the platform's to compute"


@pytest.mark.parametrize("empty", [None, []])
def test_a_gate_with_no_conditions_costs_nothing(world, empty):
    assert refresh_derived(empty, tenant_id=world["t"],
                           work_item_id=str(world["story"].id)) == []


# ══ The registry itself ══════════════════════════════════════════════════════════

def test_every_derived_condition_has_an_evaluator(db):
    """The test that outlives this task.

    Walks every phase the platform can open a gate for, collects the conditions marked
    derived, and fails if one has no registered evaluator. A derived condition is seeded
    unsatisfied and no reviewer may attest it, so an unregistered one is a gate that can
    never be approved — this fails in CI instead.
    """
    phases = {definition.phase_label for definition in ACTIVE_AGENT_CATALOG}
    registry = derived_evaluators()
    unregistered = {
        condition["key"]
        for phase in sorted(phases)
        for condition in conditions_for_phase(phase)
        if condition.get("derived") and condition["key"] not in registry
    }
    assert not unregistered, (
        f"derived gate conditions with no evaluator: {sorted(unregistered)} — each would be "
        f"seeded unsatisfied and never refresh, so its gate could never be approved"
    )


def test_the_phases_walked_are_not_an_empty_set(db):
    """Guards the test above from passing vacuously if the catalog were ever empty."""
    phases = {definition.phase_label for definition in ACTIVE_AGENT_CATALOG}
    assert "testing" in phases and "ux_design" in phases and len(phases) > 5


def test_the_registry_is_handed_out_as_a_copy():
    registry = derived_evaluators()
    registry["invented"] = lambda c, ctx: c
    assert "invented" not in derived_evaluators()


def test_the_blocking_test_rule_is_registered_under_its_own_key():
    assert derived_evaluators()[BLOCKING_TESTS_KEY] is evaluate_blocking_tests


# ══ AC3 — the existing test gate is unchanged ════════════════════════════════════

def _import(world, results):
    return quality_services.import_test_results(
        tenant_id=world["tenant"].id, project_id=world["project"].id,
        work_item_id=world["story"].id, run_id=world["run"].id, results=results)


def test_an_open_test_defect_still_holds_the_gate_shut_and_says_which(world):
    _import(world, [{"test_ref": "TC-9", "status": "FAIL"}])
    [refreshed] = refresh_derived([blocking_tests_condition()], tenant_id=world["t"],
                                  work_item_id=str(world["story"].id))
    assert refreshed["satisfied"] is False
    assert "TC-9" in refreshed["detail"]


def test_a_green_suite_still_clears_the_rule_and_drops_the_stale_detail(world):
    _import(world, [{"test_ref": "TC-9", "status": "FAIL"}])
    [red] = refresh_derived([blocking_tests_condition()], tenant_id=world["t"],
                            work_item_id=str(world["story"].id))
    _import(world, [{"test_ref": "TC-9", "status": "PASS"}])
    [green] = refresh_derived([red], tenant_id=world["t"],
                              work_item_id=str(world["story"].id))
    assert green["satisfied"] is True
    assert "detail" not in green, "the old 'open test defects: TC-9' must not linger"


def test_the_evaluator_still_refuses_a_condition_that_is_not_its_own(world):
    """Belt and braces — the registry already routes by key, and this guard stays anyway."""
    foreign = _derived(key="something_else")
    ctx = ConditionContext(tenant_id=world["t"], work_item_id=str(world["story"].id))
    assert evaluate_blocking_tests(foreign, ctx) == foreign


# ══ Why it matters — the deadlock the fix prevents ═══════════════════════════════

def test_an_unrefreshed_derived_condition_would_deadlock_the_gate(world):
    """The failure mode in full, proven rather than asserted in prose.

    A derived condition with no evaluator keeps its seeded `satisfied: False`, and a reviewer
    is not permitted to attest a derived condition — so the gate cannot be approved by anyone.
    This is what a second derived condition did before QA-15a.
    """
    approval = _approval(world, [_derived(key="unregistered_on_purpose")])
    sender = _Recorder()
    with pytest.raises(GateConditionsError) as exc:
        decide_gate(tenant_id=world["t"], approval_id=str(approval.id), user_id=world["qa_id"],
                    decision="approved", signal_sender=sender,
                    conditions=[{"key": "unregistered_on_purpose", "satisfied": True}])
    assert "unregistered_on_purpose" in str(exc.value)
    assert sender.calls == [], "the workflow was never signalled"
    approval.refresh_from_db()
    assert approval.decision == Approval.Decision.PENDING


def test_the_same_condition_with_an_evaluator_opens_the_gate(world, monkeypatch):
    """Same gate, same reviewer, one registered evaluator — the deadlock is gone."""
    _register(monkeypatch, DEMO_KEY, lambda c, ctx: {**c, "satisfied": True})
    approval = _approval(world, [_derived()])
    sender = _Recorder()
    decide_gate(tenant_id=world["t"], approval_id=str(approval.id), user_id=world["qa_id"],
                decision="approved", signal_sender=sender)
    approval.refresh_from_db()
    assert approval.decision == Approval.Decision.APPROVED
    assert sender.calls and sender.calls[0][1] == "approved"


def test_the_platform_beats_the_reviewer_on_a_second_derived_condition_too(world, monkeypatch):
    """The guarantee that made derived conditions worth having, now holding for every one of
    them rather than only the first: a reviewer ticking it while the platform says otherwise
    must not open the gate."""
    _register(monkeypatch, DEMO_KEY, lambda c, ctx: {**c, "satisfied": False,
                                                     "detail": "still failing"})
    approval = _approval(world, [_derived()])
    with pytest.raises(GateConditionsError) as exc:
        decide_gate(tenant_id=world["t"], approval_id=str(approval.id), user_id=world["qa_id"],
                    decision="approved", signal_sender=_Recorder(),
                    conditions=[{"key": DEMO_KEY, "satisfied": True}])
    assert "still failing" in str(exc.value), "the reviewer is told why, not just no"


def test_a_rejection_is_never_blocked_by_a_derived_condition(world, monkeypatch):
    """Conditions gate approval only. A reviewer must always be able to say no."""
    _register(monkeypatch, DEMO_KEY, lambda c, ctx: {**c, "satisfied": False})
    approval = _approval(world, [_derived()])
    sender = _Recorder()
    decide_gate(tenant_id=world["t"], approval_id=str(approval.id), user_id=world["qa_id"],
                decision="rejected", comment="not yet", signal_sender=sender)
    approval.refresh_from_db()
    assert approval.decision == Approval.Decision.REJECTED
