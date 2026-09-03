"""P0-T8 — AgentRunWorkflow orchestration test (spec §5).

Runs the real workflow against the running Temporal server with the activity *cores*
mocked, so it verifies the orchestration: activity sequence, the gate_decision signal
wait, and the approved vs rejected branches. (Activity DB logic is covered separately
in test_orchestration_activities.py.)
"""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from orchestration import activities
from orchestration.types import AgentRunInput, GateDecision
from orchestration.workflows import AgentRunWorkflow

pytestmark = pytest.mark.asyncio


async def _client():
    from temporalio.client import Client

    try:
        return await Client.connect("localhost:7233", namespace="default")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Temporal not reachable at localhost:7233: {exc}")


def _patch_cores(monkeypatch, calls):
    def rec(name, ret):
        def fn(*args, **kwargs):
            calls.append(name)
            return ret

        return fn

    monkeypatch.setattr(activities, "compose_manifest_core", rec("compose", "# Project\nm"))
    monkeypatch.setattr(activities, "execute_agent_core", rec("execute", {"artifact_ids": ["a1"]}))
    monkeypatch.setattr(
        activities, "verify_write_completeness_core",
        rec("verify", {"present": ["prd"], "expected": ["prd"]}),
    )
    monkeypatch.setattr(activities, "open_gate_core", rec("open", "appr1"))
    monkeypatch.setattr(activities, "publish_artifacts_core", rec("publish", {"published": ["a1"]}))
    monkeypatch.setattr(
        activities, "transition_work_item_core", rec("transition", {"state": "done"})
    )
    monkeypatch.setattr(activities, "reject_run_core", rec("reject", {"status": "rejected"}))
    monkeypatch.setattr(
        activities, "retrigger_revision_core", rec("retrigger", {"revision_run_id": "r2"})
    )
    return calls


def _input():
    return AgentRunInput(
        run_id="r1", tenant_id="t1", project_id="p1", work_item_id="w1",
        agent_spec_id="s1", phase="prd",
    )


async def _drive(monkeypatch, decision: str, revise: bool = False,
                 retrigger_raises: bool = False):
    from temporalio.worker import Worker

    calls: list[str] = []
    _patch_cores(monkeypatch, calls)
    if retrigger_raises:      # after _patch_cores, or it would be overwritten by the recorder
        def _boom(*args, **kwargs):
            raise RuntimeError("temporal is having a day")

        monkeypatch.setattr(activities, "retrigger_revision_core", _boom)
    client = await _client()
    task_queue = f"test-{uuid.uuid4()}"
    with ThreadPoolExecutor(max_workers=4) as executor:
        async with Worker(
            client,
            task_queue=task_queue,
            workflows=[AgentRunWorkflow],
            activities=activities.ALL_ACTIVITIES,
            activity_executor=executor,
        ):
            handle = await client.start_workflow(
                AgentRunWorkflow.run, _input(), id=f"wf-{uuid.uuid4()}", task_queue=task_queue
            )
            await handle.signal(
                AgentRunWorkflow.gate_decision,
                GateDecision(decision=decision, comment="c", revise=revise),
            )
            result = await handle.result()
    return result, calls


async def test_an_old_shape_gate_signal_still_deserializes():
    """Deploy-ordering guard. A signal payload written before `revise` existed (an in-flight
    workflow replaying, or an older API talking to a newer worker) must decode as a PLAIN
    rejection — not blow up, and certainly not re-run the phase nobody asked to re-run.

    The reverse direction is NOT safe and is why the worker deploys first: a NEW api sending
    `revise` to an OLD worker fails to deserialize."""
    from temporalio.converter import default

    payload = default().payload_converter.to_payload({"decision": "rejected", "comment": "no"})
    decoded = default().payload_converter.from_payload(payload, GateDecision)
    assert decoded.decision == "rejected"
    assert decoded.comment == "no"
    assert decoded.revise is False


async def test_workflow_approved_path(monkeypatch):
    result, calls = await _drive(monkeypatch, "approved")
    assert result["status"] == "completed"
    assert calls == ["compose", "execute", "verify", "open", "publish", "transition"]


async def test_workflow_rejected_path(monkeypatch):
    result, calls = await _drive(monkeypatch, "rejected")
    assert result["status"] == "rejected"
    # Regression guard: a plain rejection must NOT re-trigger anything. "Reject" and "Request
    # changes" are different intents and the workflow has to keep them apart.
    assert calls == ["compose", "execute", "verify", "open", "reject"]


async def test_workflow_request_changes_rejects_then_retriggers(monkeypatch):
    """"Request changes": the run is rejected FIRST, then the revision starts. The order is
    load-bearing — the re-trigger is refused while the old run still looks active."""
    result, calls = await _drive(monkeypatch, "rejected", revise=True)
    assert result["status"] == "rejected"
    assert result["revision_run_id"] == "r2"
    assert calls == ["compose", "execute", "verify", "open", "reject", "retrigger"]
    assert calls.index("reject") < calls.index("retrigger")


async def test_workflow_survives_a_failed_retrigger(monkeypatch):
    """The Approval is decided and the run is already terminal. A re-trigger that cannot run
    must degrade to "rejected, no revision" — never fail the workflow over finished work."""
    result, _ = await _drive(monkeypatch, "rejected", revise=True, retrigger_raises=True)
    assert result["status"] == "rejected"
    assert result["revision_run_id"] is None
