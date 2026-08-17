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
    from .build_types import (
        BuildInput,
        BuildReport,
        failure_reason,
        is_empty_build,
        is_engine_exit,
        is_merge_conflict,
    )
    from .types import GateDecision

_RETRY = RetryPolicy(maximum_attempts=3)
_COMPENSATE = RetryPolicy(maximum_attempts=2)


@workflow.defn
class BuildWorkflow:
    def __init__(self) -> None:
        self._report: BuildReport | None = None
        self._decision: GateDecision | None = None
        self._resume: bool = False
        self._abandoned: bool = False
        self._parked: bool = False

    @workflow.signal(name="build_reported")
    def build_reported(self, report: BuildReport) -> None:
        self._report = report

    @workflow.signal(name="gate_decision")
    def gate_decision(self, decision: GateDecision) -> None:
        self._decision = decision

    @workflow.signal(name="resume_run")
    def resume_run(self) -> None:
        # A human resumed a build parked by an error (Bugs S.No 157) — retry the failed step
        # instead of rebuilding from scratch.
        self._resume = True

    @workflow.signal(name="abandon_run")
    def abandon_run(self) -> None:
        # A human gave up on a parked build (Bugs S.No 157) — end it terminally, exactly as the
        # old fail-and-return path did.
        self._abandoned = True

    @workflow.query(name="status")
    def status(self) -> str:
        if self._parked:
            return "parked"
        if self._decision is not None:
            return "decided"
        return "reported" if self._report is not None else "awaiting_report"

    async def _park(self, inp: BuildInput, reason: str, resume_from: str) -> bool:
        """Park the build on an error and wait for a human (Bugs S.No 157). Returns True to
        RESUME (retry `resume_from`), False to ABANDON (the caller ends the run terminally).

        This is what replaces "mark_build_failed then return". That return CLOSED the Temporal
        history, and a closed workflow can never be signalled — so the only way forward was a
        brand-new run that redid the expensive build from step 1. Parking keeps the workflow
        alive and waiting, so the work already done (the build, the branch, the PR) is kept.
        Human-paced with no timeout, exactly like the merge gate."""
        await workflow.execute_activity(
            "park_build", args=[inp, reason, resume_from],
            start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
        )
        self._parked = True
        await workflow.wait_condition(lambda: self._resume or self._abandoned)
        self._parked = False
        if self._abandoned:
            await workflow.execute_activity(
                "mark_build_failed", args=[inp, reason],
                start_to_close_timeout=timedelta(minutes=1), retry_policy=_COMPENSATE,
            )
            return False
        self._resume = False        # consume: each park waits for a fresh resume
        await workflow.execute_activity(
            "resume_build", inp,
            start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
        )
        return True

    async def _teardown_preview(self, inp: BuildInput) -> None:
        """Best-effort: mark the run's preview env torn down at a terminal state (P3-09bR-5).
        Idempotent + a no-op when no preview was recorded (07/11). Never lets preview cleanup fail
        or delay the terminal transition."""
        try:
            await workflow.execute_activity(
                "teardown_preview", inp,
                start_to_close_timeout=timedelta(minutes=1), retry_policy=_COMPENSATE,
            )
        except ActivityError:
            pass

    @workflow.run
    async def run(self, inp: BuildInput) -> dict:
        # Dispatch, await the report, and — when the ENGINE (not the build) went away — park for a
        # human and re-dispatch on Resume. Looping is what makes the run survive a transient
        # engine failure: `mark_build_failed` + `return` closes the Temporal history for good, and
        # a closed workflow can never be signalled, so the only way forward was a fresh run that
        # rebuilt everything (S.No 146 second pass; the recourse S.No 157 gave every OTHER
        # recoverable failure). Bounded by the human: each pass waits on Resume or Take over.
        while True:
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
            # `wait_condition` returned, so the signal has landed — narrow for the type checker,
            # which cannot see that through the lambda.
            assert report is not None
            if report.status == "ok":
                break

            # A pre-push SECRET BLOCK gets one bounded auto-retry seeded with the redacted
            # findings, instead of dying here with the agent never told what tripped. Same
            # two-tier shape as remediation-exhaustion (S.No 161); see handle_secret_block_core.
            if report.secret_findings:
                outcome = await workflow.execute_activity(
                    "handle_secret_block",
                    args=[inp, report.message or "secret scan blocked the push",
                          report.secret_findings],
                    start_to_close_timeout=timedelta(minutes=2), retry_policy=_RETRY,
                )
                if outcome["action"] == "retried":
                    # The retry is its OWN run/workflow — this one is already marked failed.
                    return {"status": "secret_blocked_retried", "run_id": inp.run_id,
                            "retry_run_id": outcome["retry_run_id"]}
            # The engine going away is not the build failing. Park; on Resume the loop
            # re-dispatches. An empty build and a secret block are excluded (`is_engine_exit`).
            elif is_engine_exit(report.message):
                self._report = None       # consume, so the next pass awaits a FRESH report
                if await self._park(inp, report.message, "dispatch_build"):
                    continue
                return {"status": "build_failed", "run_id": inp.run_id}

            await workflow.execute_activity(
                "mark_build_failed", args=[inp, report.message or "build reported failed"],
                start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
            )
            return {"status": "build_failed", "run_id": inp.run_id}

        # Open the draft PR, run the 07<->08 remediation loop, then the merge gate.
        #
        # An error here no longer ends the build (Bugs S.No 157): it PARKS for a human, who can
        # Resume to retry this block or Take over to end it. Retrying the whole block is safe and
        # cheap because every step is idempotent — open_build_pr is register-don't-recreate,
        # open_merge_gate is get_or_create, and run_code_review re-dispatches correctly. Crucially
        # `dispatch_build` sits OUTSIDE this loop, so the expensive build itself is never redone.
        while True:
            try:
                # D4: the worktree ran the suite — import its results BEFORE the PR, so a failing
                # test's `defect` exists (and the qa_lead gate is already blocked) from the moment
                # the work becomes reviewable. A no-op for phases that don't import (07) and for a
                # build that reported no results. Idempotent by (run, work_item), so a Resume that
                # retries this block re-reconciles the defects rather than duplicating them.
                await workflow.execute_activity(
                    "import_build_test_results", args=[inp, report],
                    start_to_close_timeout=timedelta(minutes=2), retry_policy=_RETRY,
                )
                await workflow.execute_activity(
                    "open_build_pr", args=[inp, report],
                    start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
                )
                # D7: record the companion-local preview env the build reported and link it on the
                # PR. Best-effort — linking a preview must never fail (or park) the build. No-op
                # unless the build reported a preview URL (only 09b brings an app up).
                try:
                    await workflow.execute_activity(
                        "provision_preview", args=[inp, report],
                        start_to_close_timeout=timedelta(minutes=2), retry_policy=_RETRY,
                    )
                except ActivityError:
                    pass

                # Build phases (§5): review → remediate → re-review until no blocking findings.
                # The review activity waits (inside itself) up to inp.review_timeout_seconds for
                # the companion's 08 verdict, so its Temporal start_to_close MUST comfortably
                # exceed that window — otherwise Temporal kills the activity mid-poll and retries,
                # re-dispatching the review and never seeing the report (Bugs S.No 110). Keep them
                # consistent here.
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
                        # Bugs S.No 161: remediation exhaustion used to be the ONE recoverable
                        # failure in this workflow with no second chance — every other error here
                        # (merge conflict, other merge errors) gets a retry or a park; this just
                        # hard-failed with zero diagnostics. Now: auto-retry with a fresh agent
                        # context seeded with what blocked this attempt (still fully automated),
                        # and only park for a human after auto-retries are ALSO exhausted.
                        outcome = await workflow.execute_activity(
                            "handle_remediation_exhausted", inp,
                            start_to_close_timeout=timedelta(minutes=2),
                            retry_policy=_COMPENSATE,
                        )
                        if outcome["action"] == "retried":
                            await self._teardown_preview(inp)
                            return {"status": "remediation_exhausted_retried",
                                    "run_id": inp.run_id,
                                    "retry_run_id": outcome["retry_run_id"]}
                        # Auto-retries exhausted too — park exactly like other recoverable
                        # failures (S.No 157), so a human is the last resort, not the first.
                        if not await self._park(inp, outcome["reason"], "run_code_review"):
                            await self._teardown_preview(inp)
                            return {"status": "build_failed", "run_id": inp.run_id}
                        cycle = 0        # give the resumed attempt a fresh remediation budget
                        continue
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
                        await self._teardown_preview(inp)
                        return {"status": "takeover", "run_id": inp.run_id}
                    remediation_report = self._report
                    assert remediation_report is not None      # wait_condition returned
                    if remediation_report.status != "ok":
                        # This is where TASK-014 died: the engine exited during remediation and
                        # took a run that already had a working PR and a completed code review
                        # with it. Park instead, so Resume re-dispatches the remediation and none
                        # of that work is thrown away.
                        if is_engine_exit(remediation_report.message):
                            self._report = None    # consume, so the retry awaits a FRESH report
                            if await self._park(inp, remediation_report.message,
                                                "dispatch_remediation"):
                                # Give the cycle back: the engine going away is not the agent
                                # failing review, and must not eat the remediation budget.
                                cycle -= 1
                                continue
                            await self._teardown_preview(inp)
                            return {"status": "build_failed", "run_id": inp.run_id}
                        await workflow.execute_activity(
                            "mark_build_failed",
                            args=[inp, remediation_report.message or "remediation build failed"],
                            start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
                        )
                        await self._teardown_preview(inp)
                        return {"status": "build_failed", "run_id": inp.run_id}
                    # The remediation re-ran the suite: re-import so a test fixed this cycle
                    # closes its defect (and one newly broken opens one) instead of the loop
                    # reasoning from the first build's stale results.
                    await workflow.execute_activity(
                        "import_build_test_results", args=[inp, self._report],
                        start_to_close_timeout=timedelta(minutes=2), retry_policy=_RETRY,
                    )

                await workflow.execute_activity(
                    "open_merge_gate", inp,
                    start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
                )
            except ActivityError as exc:
                # Unwrap the ActivityError to the real cause (S.No 139) so the classifier sees the
                # actual error, not the generic "Activity task failed".
                reason = f"pr/gate setup failed: {failure_reason(exc)}"
                # An EMPTY BUILD is terminal, never parked (S.No 157): the agent produced no
                # changes, so there is nothing to open a PR for and resuming would fail
                # identically forever. Fail it with its clear reason instead of offering a
                # Resume that cannot work.
                if is_empty_build(exc):
                    await workflow.execute_activity(
                        "mark_build_failed", args=[inp, reason],
                        start_to_close_timeout=timedelta(minutes=1), retry_policy=_COMPENSATE,
                    )
                    await self._teardown_preview(inp)
                    return {"status": "build_failed", "run_id": inp.run_id}
                if not await self._park(inp, reason, "open_build_pr"):
                    await self._teardown_preview(inp)
                    return {"status": "build_failed", "run_id": inp.run_id}
                continue        # resumed → retry the PR/review/gate block (build NOT redone)

            # Merge gate: block until a reviewer decides (human-paced; no timeout). On a MERGE
            # CONFLICT the build is NOT ended (Bugs S.No 141 / ENH-2): the gate re-opens so the
            # reviewer can resolve the conflict in GitHub and approve again to retry the merge —
            # no full rebuild. Only a non-conflict merge error, or a rejection, ends the build.
            #
            # This sits INSIDE the PR/review block on purpose: "Request changes" re-enters that
            # block from the top, so a reviewer revision gets the same treatment as the first
            # build — PR reconciled to the new head, full 07<->08 remediation loop, gate re-opened.
            # Re-running review matters: the reviewer asked for a change, and a change nobody
            # reviewed is exactly what the merge gate exists to prevent.
            revise_requested = False
            while True:
                await workflow.wait_condition(lambda: self._decision is not None)
                decision = self._decision
                self._decision = None   # consume: each loop waits for a fresh decision

                if decision.decision != "approved":
                    if getattr(decision, "revise", False):
                        # Do NOT reject and do NOT tear down the preview — the reviewer is
                        # looking at it, and the branch/PR they reviewed are what gets updated.
                        await workflow.execute_activity(
                            "dispatch_reviewer_revision", args=[inp, decision.comment],
                            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
                        )
                        self._report = None     # no consume on _report — reset or the wait
                        try:                    # below returns instantly on the stale one
                            await workflow.wait_condition(
                                lambda: self._report is not None,
                                timeout=timedelta(seconds=inp.report_timeout_seconds),
                            )
                        except TimeoutError:
                            await workflow.execute_activity(
                                "mark_takeover", inp,
                                start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
                            )
                            await self._teardown_preview(inp)
                            return {"status": "takeover", "run_id": inp.run_id}
                        if self._report.status != "ok":
                            await workflow.execute_activity(
                                "mark_build_failed",
                                args=[inp, self._report.message or "revision build failed"],
                                start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
                            )
                            await self._teardown_preview(inp)
                            return {"status": "build_failed", "run_id": inp.run_id}
                        report = self._report
                        revise_requested = True
                        break
                    await workflow.execute_activity(
                        "reject_build", args=[inp, decision.comment],
                        start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
                    )
                    await self._teardown_preview(inp)
                    return {"status": "rejected", "run_id": inp.run_id}

                # Retry the merge until it succeeds, needs a fresh decision (conflict), or the
                # human abandons a parked failure.
                needs_new_decision = False
                while True:
                    try:
                        await workflow.execute_activity(
                            "merge_build_pr", inp,
                            start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
                        )
                    except ActivityError as exc:
                        # Unwrap to the real cause (S.No 139) — surfaces the S.No 136 "merge
                        # conflict" message instead of the generic "Activity task failed".
                        reason = failure_reason(exc)
                        if is_merge_conflict(exc):
                            # Non-terminal (ENH-2): re-open the gate for a resolve-then-retry (no
                            # rebuild), then wait for the reviewer's next decision.
                            await workflow.execute_activity(
                                "reopen_merge_gate", args=[inp, reason],
                                start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
                            )
                            needs_new_decision = True
                            break
                        # Any OTHER merge error parks instead of ending the build (S.No 157). On
                        # resume the merge is retried under the SAME approval — the reviewer
                        # already approved, and clicking Resume IS the human action.
                        if not await self._park(inp, f"merge failed: {reason}", "merge_build_pr"):
                            await self._teardown_preview(inp)
                            return {"status": "build_failed", "run_id": inp.run_id}
                        continue

                    # Publish EVERY artifact of the run now the gate is approved and the PR is
                    # merged (Bugs S.No 152) — the mirror of the planning path's
                    # publish_artifacts. Without this the Assumptions/Code Review artifacts
                    # stayed Draft forever; only the `code` artifact was ever published.
                    await workflow.execute_activity(
                        "publish_build_artifacts", inp,
                        start_to_close_timeout=timedelta(minutes=5), retry_policy=_RETRY,
                    )
                    await workflow.execute_activity(
                        "transition_build_work_item", args=[inp, "done"],
                        start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY,
                    )
                    await self._teardown_preview(inp)  # PR merged → close the preview env (D7)
                    return {"status": "completed", "run_id": inp.run_id}

                if needs_new_decision:
                    continue

            if revise_requested:
                continue        # back through PR → review → gate with the revised head
