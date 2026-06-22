"""AgentRunWorkflow (spec §5). Deterministic orchestration only — all side effects are
activities, called BY NAME so this module never imports the Django/ORM activity module
into the workflow sandbox. The gate is a control-plane wait on the `gate_decision`
signal (#2/#5): the engine never decides; a human does, out of band.
"""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .types import AgentRunInput, GateDecision

_RETRY = RetryPolicy(maximum_attempts=3)


@workflow.defn
class AgentRunWorkflow:
    def __init__(self) -> None:
        self._decision: GateDecision | None = None

    @workflow.signal(name="gate_decision")
    def gate_decision(self, decision: GateDecision) -> None:
        self._decision = decision

    @workflow.query(name="status")
    def status(self) -> str:
        return "decided" if self._decision is not None else "awaiting_gate"

    @workflow.run
    async def run(self, inp: AgentRunInput) -> dict:
        manifest: str = await workflow.execute_activity(
            "compose_manifest", inp,
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            "execute_agent", args=[inp, manifest],
            start_to_close_timeout=timedelta(minutes=30), retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            "open_gate", inp,
            start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
        )

        # Block until a human decides (no timeout — gates are human-paced).
        await workflow.wait_condition(lambda: self._decision is not None)
        decision = self._decision

        if decision.decision == "approved":
            await workflow.execute_activity(
                "publish_artifacts", inp,
                start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
            )
            await workflow.execute_activity(
                "transition_work_item", args=[inp, "done"],
                start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
            )
            return {"status": "completed", "run_id": inp.run_id}

        await workflow.execute_activity(
            "reject_run", args=[inp, decision.comment],
            start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
        )
        return {"status": "rejected", "run_id": inp.run_id}
