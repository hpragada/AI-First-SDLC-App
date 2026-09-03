"""AgentRunWorkflow (spec §5). Deterministic orchestration only — all side effects are
activities, called BY NAME so this module never imports the Django/ORM activity module
into the workflow sandbox. The gate is a control-plane wait on the `gate_decision`
signal (#2/#5): the engine never decides; a human does, out of band.
"""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from .build_types import (
        LONG_VERIFY_PHASES,
        failure_reason,
        is_activity_timeout,
        is_engine_exit,
    )
    from .types import AgentRunInput, GateDecision, PhaseReport

_RETRY = RetryPolicy(maximum_attempts=3)


@workflow.defn
class AgentRunWorkflow:
    def __init__(self) -> None:
        self._decision: GateDecision | None = None
        self._report: PhaseReport | None = None
        self._abandoned: bool = False
        self._resume: bool = False
        self._parked: bool = False

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

    @workflow.signal(name="resume_run")
    def resume_run(self) -> None:
        # A human resumed a run parked by an error (Bugs S.No 157) — retry the failed step
        # instead of re-running the whole phase.
        self._resume = True

    @workflow.query(name="status")
    def status(self) -> str:
        if self._parked:
            return "parked"
        if self._decision is not None:
            return "decided"
        return "awaiting_gate" if self._report is not None else "running"

    async def _park(self, inp: AgentRunInput, reason: str, resume_from: str) -> bool:
        """Park the run on an error and wait for a human (Bugs S.No 157). Returns True to RESUME
        (retry `resume_from`), False to ABANDON (the caller ends the run terminally).

        Replaces crashing or failing-and-returning: both closed the Temporal history, and a closed
        workflow can never be signalled — so the only way forward was re-running the whole phase.
        Human-paced with no timeout, exactly like the gate."""
        await workflow.execute_activity(
            "park_run", args=[inp, reason, resume_from],
            start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
        )
        self._parked = True
        await workflow.wait_condition(lambda: self._resume or self._abandoned)
        self._parked = False
        if self._abandoned:
            await workflow.execute_activity(
                "fail_run", args=[inp, reason],
                start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
            )
            return False
        self._resume = False        # consume: each park waits for a fresh resume
        await workflow.execute_activity(
            "resume_run_state", inp,
            start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
        )
        return True

    @workflow.run
    async def run(self, inp: AgentRunInput) -> dict:
        manifest: str = await workflow.execute_activity(
            "compose_manifest", inp,
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
        )

        if inp.execution_mode == "companion":
            # Run on the user's enrolled local Claude Code: dispatch, then wait for the
            # companion's report (human-paced if it asks clarifications). Offline → takeover.
            #
            # Looping for the reason BuildWorkflow loops (S.No 240 / S.No 182): when the ENGINE
            # went away — a Claude subscription session or usage limit hit mid-phase — this used
            # to call `fail_run` and RETURN, which closes the Temporal history for good. A closed
            # workflow can never be signalled, so "Resume from where it stopped" became impossible
            # for ever afterwards and the only recourse the console could offer was a brand-new
            # run from zero. On the 21 July security scan that threw away four findings already
            # registered. Park instead; on Resume this loop re-dispatches the phase. Bounded by
            # the human: every pass waits on Resume or Take over, exactly like the gate.
            while True:
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
                # `wait_condition` returned, so the signal has landed — narrow for the type
                # checker, which cannot see that through the lambda.
                assert report is not None
                if report.status == "ok":
                    await workflow.execute_activity(
                        "register_phase_result", args=[inp, report],
                        start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
                    )
                    break
                # The engine going away is not the phase failing. Park, and re-dispatch on Resume.
                # A genuine phase failure still ends the run terminally below, which is right:
                # waiting does not fix a bad run, and offering a Resume that cannot work is worse
                # than a clear failure. `is_engine_exit` is deliberately narrow about the
                # difference — see its docstring in build_types.
                if is_engine_exit(report.message):
                    self._report = None     # consume, so the next pass awaits a FRESH report
                    if await self._park(inp, report.message, "dispatch_phase"):
                        continue
                    return {"status": "phase_failed", "run_id": inp.run_id}
                await workflow.execute_activity(
                    "fail_run", args=[inp, report.message or "phase reported failed"],
                    start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
                )
                return {"status": "phase_failed", "run_id": inp.run_id}
        else:
            # Server-side fallback (CI/tests/headless): run the engine in the worker.
            await workflow.execute_activity(
                "execute_agent", args=[inp, manifest],
                start_to_close_timeout=timedelta(minutes=30), retry_policy=_RETRY,
            )
        # Rule 11 write-completeness gate-precondition: the phase must have registered its
        # expected artifact — and that it has a BODY — before a human is asked to review.
        # Deterministic -> no retry.
        #
        # A failure here used to CRASH the workflow (maximum_attempts=1 with nothing catching it),
        # so `fail_run` never ran and nothing ever wrote `run.outputs.error` — the run console,
        # which reads exactly that field, showed a failed run with NO reason at all. Now the run
        # parks with the real reason (always recorded) and a human can Resume to re-check once the
        # missing artifact is registered, instead of re-running the entire phase (Bugs S.No 157).
        while True:
            try:
                await workflow.execute_activity(
                    "verify_writes", args=[inp, [inp.phase]],
                    # One minute is right for what this check usually is: look the phase's
                    # artifact up and confirm it has a body. For the phases in
                    # LONG_VERIFY_PHASES it is not that check at all — it writes a fallback
                    # verdict for every unanswered element and then publishes a report, which
                    # is the same class of work this workflow already gives five minutes to.
                    # Cancelled half-way it leaves the accounting it exists to guarantee
                    # half-done; see the note on the constant.
                    #
                    # **Sized by the caller, not fixed here.** A flat five minutes was the same
                    # mistake as the flat sixty seconds it replaced, one order of magnitude up:
                    # it is a guess about how much work the check will find, made by the one
                    # place that cannot know. The dispatcher knows — it counted the elements —
                    # so it says, and this reads what it said. An input that does not set it
                    # carries the dataclass default of 300 s, which is the five minutes this
                    # line used to hard-code.
                    start_to_close_timeout=timedelta(
                        seconds=(getattr(inp, "verify_timeout_seconds", 300) or 300)
                        if inp.phase in LONG_VERIFY_PHASES else 60),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                break
            except ActivityError as exc:
                # **"It could not finish" and "it found a gap" are different facts.** They were
                # sharing one sentence, and the one they shared was the alarming one: a run whose
                # work was complete and correct was recorded as having FAILED its completeness
                # check when all that happened was that the check ran out of its own time. Say
                # which it was, in words, so the console does not raise a false alarm about the
                # single guarantee this capability exists to make.
                reason = (
                    f"write-completeness check did not finish in time "
                    f"({failure_reason(exc)}) — it ran out of its own budget rather than "
                    f"finding anything missing, so what the phase wrote has not been checked "
                    f"either way"
                    if is_activity_timeout(exc)
                    else f"write-completeness check failed: {failure_reason(exc)}"
                )
                # Parking waits for a human to fix the run and resume it. That is right for a
                # gated phase, and wrong for an auto-apply one: nobody is watching a document
                # vision run — its work item is hidden from the backlog — so parking left the
                # document adopted with nothing in the registry, silently, forever. Fail it
                # instead, which runs the recovery that registers the document's extracted text.
                if getattr(inp, "auto_approve", False):
                    await workflow.execute_activity(
                        "fail_run", args=[inp, reason],
                        start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
                    )
                    return {"status": "failed", "run_id": inp.run_id}
                if not await self._park(inp, reason, "verify_writes"):
                    return {"status": "failed", "run_id": inp.run_id}
                continue        # resumed → re-check (the phase itself is NOT re-run)
        # Auto-apply (Part B, 00e document vision): the human already adopted the document these
        # pages came from, so the faithful transcription is published WITHOUT a second human gate.
        # No Approval is opened; publish + complete directly. Default is False for every other
        # phase, so their gated path below is byte-for-byte unchanged.
        if inp.auto_approve:
            await workflow.execute_activity(
                "publish_artifacts", inp,
                start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
            )
            await workflow.execute_activity(
                "transition_work_item", args=[inp, "done"],
                start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
            )
            return {"status": "completed", "run_id": inp.run_id, "auto_approved": True}

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
        if not getattr(decision, "revise", False):
            return {"status": "rejected", "run_id": inp.run_id}

        # "Request changes": re-run the phase with the reviewer's direction. This MUST come after
        # `reject_run` — that activity is what moves the run out of AWAITING_GATE, and a new run
        # for the same work item is refused while the old one still looks active.
        #
        # One attempt, and failure is swallowed on purpose. The Approval is decided and the run is
        # already terminal; a lost re-trigger must degrade to "rejected, revision not started" and
        # say so, never leave the workflow Failed over work that is finished.
        try:
            out = await workflow.execute_activity(
                "retrigger_revision", args=[inp, decision.comment],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ActivityError:
            return {"status": "rejected", "run_id": inp.run_id, "revision_run_id": None}
        return {"status": "rejected", "run_id": inp.run_id,
                "revision_run_id": (out or {}).get("revision_run_id")}
