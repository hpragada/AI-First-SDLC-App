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
    return calls


def _input():
    return AgentRunInput(
        run_id="r1", tenant_id="t1", project_id="p1", work_item_id="w1",
        agent_spec_id="s1", phase="prd",
    )


async def _drive(monkeypatch, decision: str):
    from temporalio.worker import Worker

    calls: list[str] = []
    _patch_cores(monkeypatch, calls)
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
                AgentRunWorkflow.gate_decision, GateDecision(decision=decision, comment="c")
            )
            result = await handle.result()
    return result, calls


async def test_workflow_approved_path(monkeypatch):
    result, calls = await _drive(monkeypatch, "approved")
    assert result["status"] == "completed"
    assert calls == ["compose", "execute", "verify", "open", "publish", "transition"]


async def test_workflow_rejected_path(monkeypatch):
    result, calls = await _drive(monkeypatch, "rejected")
    assert result["status"] == "rejected"
    assert calls == ["compose", "execute", "verify", "open", "reject"]
