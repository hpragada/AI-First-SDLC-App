"""AgentRunWorkflow (spec §5). Deterministic orchestration only — all side effects are
activities, called BY NAME so this module never imports the Django/ORM activity module
into the workflow sandbox. The gate is a control-plane wait on the `gate_decision`
signal (#2/#5): the engine never decides; a human does, out of band.
"""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .types import AgentRunInput, GateDecision, PhaseReport

_RETRY = RetryPolicy(maximum_attempts=3)


@workflow.defn
class AgentRunWorkflow:
    def __init__(self) -> None:
        self._decision: GateDecision | None = None
        self._report: PhaseReport | None = None
        self._abandoned: bool = False

    @workflow.signal(name="gate_decision")
    def gate_decision(self, decision: GateDecision) -> None:
        self._decision = decision

    @workflow.signal(name="phase_reported")
    def phase_reported(self, report: PhaseReport) -> None:
        self._report = report

    @workflow.signal(name="abandon_run")
    def abandon_run(self) -> None:
        # A human explicitly took the parked run over (Bugs S.No 89). Only meaningful after a
        # report-timeout soft-takeover: it ends the still-waiting run terminally so it does not
        # linger once the operator has decided to hand-work it or re-run from a clean dispatch.
        self._abandoned = True

    @workflow.query(name="status")
    def status(self) -> str:
        if self._decision is not None:
            return "decided"
        return "awaiting_gate" if self._report is not None else "running"

    @workflow.run
    async def run(self, inp: AgentRunInput) -> dict:
        manifest: str = await workflow.execute_activity(
            "compose_manifest", inp,
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
        )

        if inp.execution_mode == "companion":
            # Run on the user's enrolled local Claude Code: dispatch, then wait for the
            # companion's report (human-paced if it asks clarifications). Offline → takeover.
            await workflow.execute_activity(
                "dispatch_phase", args=[inp, manifest],
                start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
            )
            try:
                await workflow.wait_condition(
                    lambda: self._report is not None,
                    timeout=timedelta(seconds=inp.report_timeout_seconds),
                )
            except TimeoutError:
                # Soft, RECONCILABLE takeover (Bugs S.No 89): surface "companion appears
                # offline" and let a human take over, but do NOT terminate — a companion that
                # only slept can still return and complete this very run. Keep waiting for the
                # report; an explicit human takeover sends `abandon_run` to end it terminally.
                await workflow.execute_activity(
                    "mark_phase_takeover", inp,
                    start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
                )
                await workflow.wait_condition(
                    lambda: self._report is not None or self._abandoned
                )
                if self._abandoned:
                    await workflow.execute_activity(
                        "fail_run", args=[inp, "run abandoned by human takeover"],
                        start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
                    )
                    return {"status": "abandoned", "run_id": inp.run_id}
            report = self._report
            if report.status != "ok":
                await workflow.execute_activity(
                    "fail_run", args=[inp, report.message or "phase reported failed"],
                    start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
                )
                return {"status": "phase_failed", "run_id": inp.run_id}
            await workflow.execute_activity(
                "register_phase_result", args=[inp, report],
                start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
            )
        else:
            # Server-side fallback (CI/tests/headless): run the engine in the worker.
            await workflow.execute_activity(
                "execute_agent", args=[inp, manifest],
                start_to_close_timeout=timedelta(minutes=30), retry_policy=_RETRY,
            )
        # Rule 11 write-completeness gate-precondition: the phase must have registered its
        # expected artifact before a human is asked to review. Deterministic -> no retry.
        await workflow.execute_activity(
            "verify_writes", args=[inp, [inp.phase]],
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(maximum_attempts=1),
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
