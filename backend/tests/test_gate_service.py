"""P0-T9 — gate decision service (spec §6): role check, decision record, signal."""
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from apps.gates import services
from apps.gates.models import Approval
from apps.gates.services import GateError, GateRoleError, decide_gate
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from orchestration.types import AgentRunInput
from orchestration.workflows import AgentRunWorkflow


@pytest.fixture
def gate_world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="x")
    run = Run.objects.create(
        tenant=t, work_item=wi, agent_spec=spec, temporal_workflow_id="wf-x"
    )
    po = User.objects.create_user(email="po@acme.test", name="PO", tenant=t, password="pw")
    Membership.objects.create(tenant=t, user=po, project=project, role="product_owner")
    eng = User.objects.create_user(email="eng@acme.test", name="Eng", tenant=t, password="pw")
    Membership.objects.create(tenant=t, user=eng, project=project, role="engineer")
    approval = Approval.objects.create(
        tenant=t, run=run, work_item=wi, required_role="product_owner",
        decision=Approval.Decision.PENDING,
    )
    return {
        "tenant_id": str(t.id), "approval_id": str(approval.id),
        "po_id": str(po.id), "eng_id": str(eng.id),
    }


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, workflow_id, decision, approver_id, comment, revise=False):
        self.calls.append((workflow_id, decision, approver_id, comment, revise))


def test_decide_gate_approved_records_and_signals(gate_world):
    sender = _Recorder()
    result = decide_gate(
        tenant_id=gate_world["tenant_id"], approval_id=gate_world["approval_id"],
        user_id=gate_world["po_id"], decision="approved", comment="lgtm", signal_sender=sender,
    )
    assert result["decision"] == "approved"
    approval = Approval.objects.get(id=gate_world["approval_id"])
    assert approval.decision == Approval.Decision.APPROVED
    assert str(approval.approver_id) == gate_world["po_id"]
    assert approval.decided_at is not None
    assert sender.calls == [("wf-x", "approved", gate_world["po_id"], "lgtm", False)]


def test_decide_gate_rejected(gate_world):
    sender = _Recorder()
    decide_gate(
        tenant_id=gate_world["tenant_id"], approval_id=gate_world["approval_id"],
        user_id=gate_world["po_id"], decision="rejected", comment="needs work",
        signal_sender=sender,
    )
    assert Approval.objects.get(id=gate_world["approval_id"]).decision == Approval.Decision.REJECTED
    assert sender.calls[0][1] == "rejected"


def test_request_changes_carries_the_flag_and_the_note_to_the_workflow(gate_world):
    """"Request changes" is still recorded as a REJECTION — that is the audit truth — but the
    signal carries `revise` so the workflow re-runs the phase instead of just stopping."""
    sender = _Recorder()
    result = decide_gate(
        tenant_id=gate_world["tenant_id"], approval_id=gate_world["approval_id"],
        user_id=gate_world["po_id"], decision="rejected",
        comment="Use a single column and drop the hero image.", revise=True,
        signal_sender=sender,
    )
    assert result["decision"] == "rejected" and result["revise"] is True
    approval = Approval.objects.get(id=gate_world["approval_id"])
    assert approval.decision == Approval.Decision.REJECTED
    assert approval.comment == "Use a single column and drop the hero image."
    assert sender.calls[0][3] == "Use a single column and drop the hero image."
    assert sender.calls[0][4] is True


def test_request_changes_without_a_note_is_refused(gate_world):
    """There would be nothing for the agent to act on, so it must fail loudly rather than
    re-run the phase with the same inputs and produce the same thing again."""
    sender = _Recorder()
    for blank in ("", "   "):
        with pytest.raises(GateError):
            decide_gate(
                tenant_id=gate_world["tenant_id"], approval_id=gate_world["approval_id"],
                user_id=gate_world["po_id"], decision="rejected", comment=blank, revise=True,
                signal_sender=sender,
            )
    assert Approval.objects.get(id=gate_world["approval_id"]).decision == Approval.Decision.PENDING
    assert sender.calls == []


def test_request_changes_on_an_approval_is_refused(gate_world):
    """An approved run publishes and completes; there is nothing to revise. Silently ignoring
    the flag would leave the reviewer believing a revision was requested."""
    sender = _Recorder()
    with pytest.raises(GateError):
        decide_gate(
            tenant_id=gate_world["tenant_id"], approval_id=gate_world["approval_id"],
            user_id=gate_world["po_id"], decision="approved", comment="also do X", revise=True,
            signal_sender=sender,
        )
    assert Approval.objects.get(id=gate_world["approval_id"]).decision == Approval.Decision.PENDING
    assert sender.calls == []


def test_decide_gate_wrong_role_is_blocked(gate_world):
    sender = _Recorder()
    with pytest.raises(GateRoleError):
        decide_gate(
            tenant_id=gate_world["tenant_id"], approval_id=gate_world["approval_id"],
            user_id=gate_world["eng_id"], decision="approved", signal_sender=sender,
        )
    # Unchanged + not signaled.
    assert Approval.objects.get(id=gate_world["approval_id"]).decision == Approval.Decision.PENDING
    assert sender.calls == []


def test_decide_gate_already_decided(gate_world):
    sender = _Recorder()
    decide_gate(
        tenant_id=gate_world["tenant_id"], approval_id=gate_world["approval_id"],
        user_id=gate_world["po_id"], decision="approved", signal_sender=sender,
    )
    with pytest.raises(GateError):
        decide_gate(
            tenant_id=gate_world["tenant_id"], approval_id=gate_world["approval_id"],
            user_id=gate_world["po_id"], decision="rejected", signal_sender=sender,
        )


def test_decide_gate_invalid_decision(gate_world):
    with pytest.raises(GateError):
        decide_gate(
            tenant_id=gate_world["tenant_id"], approval_id=gate_world["approval_id"],
            user_id=gate_world["po_id"], decision="maybe", signal_sender=_Recorder(),
        )


# ── real signal path against Temporal ───────────────────────────────
def _patch_cores(monkeypatch, calls):
    def rec(name, ret):
        def fn(*a, **k):
            calls.append(name)
            return ret

        return fn

    from orchestration import activities

    monkeypatch.setattr(activities, "compose_manifest_core", rec("compose", "# Project\nm"))
    monkeypatch.setattr(activities, "execute_agent_core", rec("execute", {"artifact_ids": ["a"]}))
    monkeypatch.setattr(
        activities, "verify_write_completeness_core", rec("verify", {"present": ["prd"]})
    )
    monkeypatch.setattr(activities, "open_gate_core", rec("open", "ap"))
    monkeypatch.setattr(activities, "publish_artifacts_core", rec("publish", {"published": ["a"]}))
    monkeypatch.setattr(
        activities, "transition_work_item_core", rec("transition", {"state": "done"})
    )
    monkeypatch.setattr(activities, "reject_run_core", rec("reject", {"status": "rejected"}))


@pytest.mark.usefixtures("real_gate_signal")   # the REAL sender is what is under test
async def test_default_signal_sender_resumes_real_workflow(monkeypatch):
    from django.conf import settings
    from temporalio.client import Client
    from temporalio.worker import Worker

    from orchestration import activities

    monkeypatch.setattr(settings, "TEMPORAL_HOST", "localhost:7233")
    monkeypatch.setattr(settings, "TEMPORAL_NAMESPACE", "default")
    _patch_cores(monkeypatch, [])

    try:
        client = await Client.connect("localhost:7233", namespace="default")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Temporal not reachable: {exc}")

    task_queue = f"test-{uuid.uuid4()}"
    workflow_id = f"wf-{uuid.uuid4()}"
    inp = AgentRunInput(
        run_id="r1", tenant_id="t1", project_id="p1", work_item_id="w1",
        agent_spec_id="s1", phase="prd",
    )
    with ThreadPoolExecutor(max_workers=4) as executor:
        async with Worker(
            client, task_queue=task_queue, workflows=[AgentRunWorkflow],
            activities=activities.ALL_ACTIVITIES, activity_executor=executor,
        ):
            handle = await client.start_workflow(
                AgentRunWorkflow.run, inp, id=workflow_id, task_queue=task_queue
            )
            # decide_gate's real sender uses asyncio.run internally -> run it in a thread.
            await asyncio.to_thread(
                services._default_signal_sender, workflow_id, "approved", None, ""
            )
            result = await handle.result()
    assert result["status"] == "completed"
