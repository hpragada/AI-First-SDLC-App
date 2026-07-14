"""BuildWorkflow (Phase-2 §4) — the durable build saga.

Deterministic orchestration only; all side effects are activities called BY NAME. The
companion runs the build on the dev machine and **reports back** via the `build_reported`
signal; if it never does (offline laptop) the run parks for human takeover (PG10). On the
report, the platform opens the draft PR and waits on the **merge gate** (a reviewer
Approval, signalled via `gate_decision`); on approval it merges (the gated SoR write, #5/#8).
Activities are idempotent by run_id (safe Temporal retries); failures compensate to a
failed run with the WorkItem returned to in_progress (the branch/PR left for disposition).
"""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from .build_types import BuildInput, BuildReport
    from .types import GateDecision

_RETRY = RetryPolicy(maximum_attempts=3)
_COMPENSATE = RetryPolicy(maximum_attempts=2)


@workflow.defn
class BuildWorkflow:
    def __init__(self) -> None:
        self._report: BuildReport | None = None
        self._decision: GateDecision | None = None

    @workflow.signal(name="build_reported")
    def build_reported(self, report: BuildReport) -> None:
        self._report = report

    @workflow.signal(name="gate_decision")
    def gate_decision(self, decision: GateDecision) -> None:
        self._decision = decision

    @workflow.query(name="status")
    def status(self) -> str:
        if self._decision is not None:
            return "decided"
        return "reported" if self._report is not None else "awaiting_report"

    @workflow.run
    async def run(self, inp: BuildInput) -> dict:
        await workflow.execute_activity(
            "dispatch_build", inp,
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
        )

        # Await the companion's report; an offline runner → human takeover (never hang).
        try:
            await workflow.wait_condition(
                lambda: self._report is not None,
                timeout=timedelta(seconds=inp.report_timeout_seconds),
            )
        except TimeoutError:
            await workflow.execute_activity(
                "mark_takeover", inp,
                start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
            )
            return {"status": "takeover", "run_id": inp.run_id}

        report = self._report
        if report.status != "ok":
            await workflow.execute_activity(
                "mark_build_failed", args=[inp, report.message or "build reported failed"],
                start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
            )
            return {"status": "build_failed", "run_id": inp.run_id}

        # Open the draft PR, run the 07<->08 remediation loop, then the merge gate. On
        # exhausted retries → compensate (dead-letter).
        try:
            await workflow.execute_activity(
                "open_build_pr", args=[inp, report],
                start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
            )

            # Build phases (§5): review → remediate → re-review until no blocking findings.
            # The review activity waits (inside itself) up to inp.review_timeout_seconds for the
            # companion's 08 verdict, so its Temporal start_to_close MUST comfortably exceed that
            # window — otherwise Temporal kills the activity mid-poll and retries, re-dispatching
            # the review and never seeing the report (Bugs S.No 110). Keep them consistent here.
            review_activity_timeout = timedelta(seconds=inp.review_timeout_seconds + 600)
            cycle = 0
            while True:
                review = await workflow.execute_activity(
                    "run_code_review", inp,
                    start_to_close_timeout=review_activity_timeout, retry_policy=_RETRY,
                )
                if review["open_blocking"] == 0:
                    break
                cycle += 1
                if cycle > inp.max_remediation_cycles:
                    await workflow.execute_activity(
                        "mark_build_failed", args=[inp, "remediation cycles exhausted"],
                        start_to_close_timeout=timedelta(minutes=1), retry_policy=_COMPENSATE,
                    )
                    return {"status": "remediation_exhausted", "run_id": inp.run_id}
                # Implementation re-runs in remediation mode on the same branch; await report.
                await workflow.execute_activity(
                    "dispatch_remediation", inp,
                    start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
                )
                self._report = None
                try:
                    await workflow.wait_condition(
                        lambda: self._report is not None,
                        timeout=timedelta(seconds=inp.report_timeout_seconds),
                    )
                except TimeoutError:
                    await workflow.execute_activity(
                        "mark_takeover", inp,
                        start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
                    )
                    return {"status": "takeover", "run_id": inp.run_id}
                if self._report.status != "ok":
                    await workflow.execute_activity(
                        "mark_build_failed",
                        args=[inp, self._report.message or "remediation build failed"],
                        start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
                    )
                    return {"status": "build_failed", "run_id": inp.run_id}

            await workflow.execute_activity(
                "open_merge_gate", inp,
                start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
            )
        except ActivityError as exc:
            await workflow.execute_activity(
                "mark_build_failed", args=[inp, f"pr/gate setup failed: {exc}"],
                start_to_close_timeout=timedelta(minutes=1), retry_policy=_COMPENSATE,
            )
            return {"status": "build_failed", "run_id": inp.run_id}

        # Block until a reviewer decides the merge gate (human-paced; no timeout).
        await workflow.wait_condition(lambda: self._decision is not None)
        decision = self._decision

        if decision.decision == "approved":
            try:
                await workflow.execute_activity(
                    "merge_build_pr", inp,
                    start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
                )
            except ActivityError as exc:
                await workflow.execute_activity(
                    "mark_build_failed", args=[inp, f"merge failed: {exc}"],
                    start_to_close_timeout=timedelta(minutes=1), retry_policy=_COMPENSATE,
                )
                return {"status": "build_failed", "run_id": inp.run_id}
            await workflow.execute_activity(
                "transition_build_work_item", args=[inp, "done"],
                start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
            )
            return {"status": "completed", "run_id": inp.run_id}

        await workflow.execute_activity(
            "reject_build", args=[inp, decision.comment],
            start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
        )
        return {"status": "rejected", "run_id": inp.run_id}
