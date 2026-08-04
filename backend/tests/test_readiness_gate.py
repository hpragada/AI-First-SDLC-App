"""Deployment readiness gate — the deployment Approval's control-plane checklist.

The deployment gate is seeded with the pre-deployment readiness checklist (mirroring the 12
Deployment agent's Step 1), and an APPROVED decision is blocked while any required item is
unsatisfied — so "never deploy without a completed readiness checklist" is enforced by the
control plane, not just narrated by the agent. Reviewer-attested, like the WCAG design gate.
"""
import pytest

from apps.gates.conditions import conditions_for_phase
from apps.gates.models import Approval
from apps.gates.readiness import readiness_checklist
from apps.gates.services import GateConditionsError, decide_gate
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from orchestration.activities import open_gate_core
from orchestration.types import AgentRunInput


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, workflow_id, decision, approver_id, comment, revise=False):
        self.calls.append((workflow_id, decision, approver_id, comment))


# ── readiness gate: checklist seeding (pure) ────────────────────────
def test_conditions_for_phase_seeds_readiness_only_for_deployment():
    deploy = conditions_for_phase("deployment")
    keys = {c["key"] for c in deploy}
    assert {"code_quality", "testing", "security", "rollback"} <= keys
    assert all(c["required"] and not c["satisfied"] for c in deploy)
    # No other phase carries the readiness checklist.
    assert not any(c["key"] in keys for c in conditions_for_phase("cicd"))
    assert conditions_for_phase("prd") == []


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=t, key="12_deployment", body_ref="x")
    run = Run.objects.create(
        tenant=t, work_item=wi, agent_spec=spec, temporal_workflow_id="wf-dep-1"
    )
    devops = User.objects.create_user(
        email="ops@acme.test", name="Ops", tenant=t, password="pw"
    )
    Membership.objects.create(tenant=t, user=devops, project=project, role="devops")
    return {"t": t, "project": project, "wi": wi, "run": run,
            "devops_id": str(devops.id)}


def _inp(world, phase):
    return AgentRunInput(
        run_id=str(world["run"].id), tenant_id=str(world["t"].id),
        project_id=str(world["project"].id), work_item_id=str(world["wi"].id),
        agent_spec_id="s", phase=phase, required_role="devops",
    )


def test_open_gate_core_seeds_readiness_checklist_for_deployment(world):
    approval = Approval.objects.get(id=open_gate_core(_inp(world, "deployment")))
    assert len(approval.conditions) == len(readiness_checklist())
    assert {c["key"] for c in approval.conditions} >= {"security", "rollback", "on_call"}
    assert all(not c["satisfied"] for c in approval.conditions)


# ── readiness gate: enforcement on decide ───────────────────────────
def test_decide_gate_blocks_approve_until_readiness_satisfied(world):
    approval_id = open_gate_core(_inp(world, "deployment"))
    sender = _Recorder()

    # Approving with the readiness checklist unmet is blocked — nothing is signaled.
    with pytest.raises(GateConditionsError):
        decide_gate(tenant_id=str(world["t"].id), approval_id=approval_id,
                    user_id=world["devops_id"], decision="approved", signal_sender=sender)
    assert Approval.objects.get(id=approval_id).decision == Approval.Decision.PENDING
    assert sender.calls == []

    # Mark every item satisfied → the gate becomes grantable.
    satisfied = [{"key": c["key"], "satisfied": True} for c in readiness_checklist()]
    result = decide_gate(tenant_id=str(world["t"].id), approval_id=approval_id,
                         user_id=world["devops_id"], decision="approved",
                         conditions=satisfied, signal_sender=sender)
    assert result["decision"] == "approved"
    assert all(c["satisfied"] for c in result["conditions"])
    assert sender.calls and sender.calls[0][1] == "approved"
