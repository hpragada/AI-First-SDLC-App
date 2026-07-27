"""Local-companion runner API (Phase-2 §3).

Two surfaces:
1. **Enrollment** (`/api/runners/…`, tenant-scoped via X-Tenant-ID like every P0 route):
   a developer enrolls a companion and gets a one-time token; can list/revoke.
2. **Remote Platform-State serving** (`/api/runner/state/<tool>/`, Runner-token auth): the
   build agent on the dev machine calls the platform-state tools over HTTP — **no DB on the
   dev machine**. The tenant is taken from the authenticated enrollment (server-side), never
   from the request body, so RLS scoping stays on the platform (#6). Only the build-phase
   tool subset is exposed (per-phase allowlist, PG12).
"""
from __future__ import annotations

from datetime import timedelta

from mcp_platform_state import tools
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project
from apps.runs.enrollment import (
    authenticate_runner,
    enroll_runner,
    list_developer_enrollments,
    revoke_runner,
)
from apps.runs.models import Run, RunnerEnrollment
from apps.tenancy.auth import IsAuthenticatedMember, current_user
from apps.tenancy.context import tenant_context
from orchestration.build_report import BuildReportError, report_build

# A work claim is a *lease*. If the companion that claimed a run dies before reporting (crash,
# manual stop, laptop sleep), the run would otherwise stay "claimed" forever — status stuck at
# "running", no artifacts, no gate (Bugs.xlsx row 61 / RC-3). A later poll re-claims a run whose
# claim went stale (claimed_at older than this with no report).
#
# The lease detects a DEAD companion, so it must key off *liveness*, not task duration. It used
# to key off "time since the claim was stamped", which wrongly fired on a LIVE companion running
# a long phase (a genuine 19-min code review > this 15-min lease got re-claimed mid-flight →
# duplicate artifacts + a failed re-review → the merge gate opened blind — Bugs S.No 111, the
# S.No 110 follow-up). Fix: the heartbeat renews `claimed_at` while the companion is alive
# (_renew_claims_for), so a heartbeating companion's claim never goes stale no matter how long the
# phase runs, while a truly dead companion still gets re-claimed ~15 min after its LAST heartbeat.
CLAIM_LEASE = timedelta(minutes=15)

# The heartbeat renews the lease on *liveness*, which alone lets a wedged-but-heartbeating worker
# (agent hung, but the heartbeat thread still ticking) renew its claim forever — the run sits
# claimed, masked from recovery, until only the workflow's 2h report-timeout takeover (S.No 89)
# frees it (Bugs S.No 134). MAX_CLAIM_AGE caps how long a single continuous claim may be renewed:
# past it, the heartbeat STOPS renewing, so the lease ages out (CLAIM_LEASE) and the run is
# recoverable well before the 2h backstop. Set safely ABOVE the longest legitimate build so a
# healthy long build is never capped (which would reintroduce the S.No 111 mid-flight re-claim);
# the team confirmed builds stay well under 60 min.
MAX_CLAIM_AGE = timedelta(minutes=60)

# Build-phase platform-state tool allowlist (no detect_drift, no planning-only tools).
_BUILD_STATE_TOOLS = {
    "get_context": tools.get_context,
    "get_artifact": tools.get_artifact,
    "list_artifacts": tools.list_artifacts,
    "register_artifact": tools.register_artifact,
    "stage_artifact_body": tools.stage_artifact_body,
    "get_artifact_body": tools.get_artifact_body,
    "update_artifact": tools.update_artifact,
    "add_trace_edge": tools.add_trace_edge,
    "log_event": tools.log_event,
    "list_work_items": tools.list_work_items,
    "create_work_item": tools.create_work_item,
    "transition_work_item": tools.transition_work_item,
}

# The build agent may move a WorkItem forward through working states (e.g. -> in_progress at
# Step 1), but it must NEVER transition one to a gate-owned terminal state. Marking a WorkItem
# `done` is a control-plane action that only happens after an APPROVED merge gate, via the saga's
# transition_build_work_item activity (non-negotiables #2/#5). Letting the engine set `done`
# itself bypassed the gate and left the WorkItem done with no workitem.transitioned event while
# its run was still in review — the "state=done while awaiting_gate" mislabel. Blocked here at
# the single agent/companion entry point; the orchestrator calls tools.transition_work_item
# in-process (not through this view), so its legitimate `done` transition is unaffected.
_AGENT_FORBIDDEN_TRANSITIONS = {"done"}


def _tenant_id(request) -> str:
    tid = getattr(request, "tenant_id", None)
    if not tid:
        from rest_framework.exceptions import ParseError

        raise ParseError("X-Tenant-ID header is required.")
    return str(tid)


def _renew_claims_for(runner) -> int:
    """Refresh `claimed_at=now` on every in-flight run this companion currently holds, so its
    claim lease (CLAIM_LEASE) tracks the companion's liveness, not the phase duration. Called on
    each heartbeat: a live companion keeps its claim fresh no matter how long the phase runs, so
    a long-but-healthy review is never re-claimed out from under it (Bugs S.No 111). A dead
    companion stops heartbeating, so its claim ages out and the run is recovered as before.

    Only `claimed`, still-in-flight (PENDING/RUNNING) runs are touched — a run that already
    reported or reached a gate is left alone, so this can never revive finished work."""
    from django.db import transaction
    from django.utils import timezone

    now_dt = timezone.now()
    now = now_dt.isoformat()
    # Bugs S.No 134: a claim first held before this cutoff has been renewed for too long without
    # finishing — stop renewing it so the lease can age out (a wedged worker can't renew forever).
    max_age_before = (now_dt - MAX_CLAIM_AGE).isoformat()
    renewed = 0
    with tenant_context(str(runner.tenant_id)), transaction.atomic():
        runs = (
            Run.objects.select_for_update(skip_locked=True)
            .filter(tenant_id=runner.tenant_id,
                    inputs__dispatch__enrollment_id=str(runner.id),
                    inputs__dispatch__status="claimed",
                    status__in=(Run.Status.PENDING, Run.Status.RUNNING))
        )
        for run in runs:
            inputs = dict(run.inputs or {})
            dispatch = dict(inputs.get("dispatch") or {})
            if dispatch.get("status") != "claimed":
                continue
            first_claimed_at = dispatch.get("first_claimed_at")
            if first_claimed_at and first_claimed_at < max_age_before:
                # Held (and renewed) past MAX_CLAIM_AGE without reporting — likely wedged. Stop
                # renewing; the lease now ages out so the run is recoverable (re-claim / S.No 89
                # takeover) instead of masked indefinitely by mere process liveness.
                continue
            dispatch["claimed_at"] = now
            inputs["dispatch"] = dispatch
            run.inputs = inputs
            run.save(update_fields=["inputs", "updated_at"])
            renewed += 1
    return renewed


def _serialize(e: RunnerEnrollment) -> dict:
    return {
        "id": str(e.id), "project_id": str(e.project_id), "label": e.label,
        "repos": e.repos, "status": e.status,
        "developer_id": str(e.developer_id) if e.developer_id else None,
        "last_seen": e.last_seen.isoformat() if e.last_seen else None,
    }


class RunnerEnrollmentView(APIView):
    """GET the caller's companion enrollments (P4.7-T11, backs S-05/S-06) / POST enroll a
    local-companion runner for this tenant."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticatedMember()]
        return super().get_permissions()

    def get(self, request):
        tenant_id = _tenant_id(request)
        user = current_user(request)
        return Response(
            list_developer_enrollments(tenant_id=tenant_id, developer_id=str(user.id))
        )

    def post(self, request):
        tenant_id = _tenant_id(request)
        project_id = request.data.get("project_id")
        if not project_id:
            return Response({"project_id": "required"}, status=status.HTTP_400_BAD_REQUEST)
        # Validate the project is in this tenant (scoped read).
        if not Project.objects.filter(id=project_id, tenant_id=tenant_id).exists():
            return Response({"project_id": "not found in tenant"},
                            status=status.HTTP_404_NOT_FOUND)
        # The authenticated session user owns the enrollment; `developer_id` in the body is
        # only the pre-auth/runner/test fallback (mirrors `resolve_actor`, P4.7-T5).
        user = current_user(request)
        developer_id = str(user.id) if user is not None else request.data.get("developer_id")
        enrollment, token = enroll_runner(
            tenant_id=tenant_id, project_id=project_id,
            developer_id=developer_id,
            label=request.data.get("label", ""), repos=request.data.get("repos") or [],
        )
        body = _serialize(enrollment)
        body["token"] = token  # shown once — the companion stores it; only its hash persists
        return Response(body, status=status.HTTP_201_CREATED)


class RunnerRevokeView(APIView):
    """POST /api/runners/{id}/revoke/ — stop a companion's token from authenticating."""

    def post(self, request, pk):
        tenant_id = _tenant_id(request)
        if not revoke_runner(tenant_id=tenant_id, enrollment_id=pk):
            return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response({"id": str(pk), "status": "revoked"})


class RunnerStateView(APIView):
    """POST /api/runner/state/<tool>/ — a build agent's platform-state call, Runner-token
    authenticated. The tenant is the enrollment's (server-side), not from the body."""

    authentication_classes: list = []   # Runner-token auth is handled explicitly below
    permission_classes: list = []

    def post(self, request, tool):
        runner = self._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        fn = _BUILD_STATE_TOOLS.get(tool)
        if fn is None:
            return Response({"detail": f"tool '{tool}' is not in the build allowlist"},
                            status=status.HTTP_403_FORBIDDEN)
        args = request.data if isinstance(request.data, dict) else {}
        # Guard: the engine may not transition a WorkItem to a gate-owned terminal state (`done`).
        # That transition belongs to the control plane, after an approved merge gate (#2/#5).
        if tool == "transition_work_item" and args.get("to_state") in _AGENT_FORBIDDEN_TRANSITIONS:
            return Response(
                {"detail": f"transition to '{args.get('to_state')}' is not permitted from a build "
                           "agent — the platform transitions a WorkItem to done only after its "
                           "merge gate is approved."},
                status=status.HTTP_403_FORBIDDEN)
        try:
            result = fn(str(runner.tenant_id), **args)   # tenant bound server-side
        except TypeError as exc:
            return Response({"detail": f"bad arguments: {exc}"},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({"result": result})

    @staticmethod
    def _resolve_runner(request):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Runner "):
            return None
        token = auth[len("Runner "):].strip()
        return authenticate_runner(tenant_id=request.headers.get("X-Tenant-ID"), token=token)


class RunnerBuildFetchView(APIView):
    """GET /api/runner/builds/<run_id>/ — the companion fetches its dispatched BuildTask
    (manifest + agent body). The companion fills in its own runner token before running."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request, run_id):
        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        with tenant_context(str(runner.tenant_id)):
            run = Run.objects.filter(id=run_id, tenant_id=runner.tenant_id).first()
        if run is None:
            return Response({"detail": "run not found"}, status=status.HTTP_404_NOT_FOUND)
        payload = (run.inputs or {}).get("build_task")
        if not payload:
            return Response({"detail": "no build task dispatched"},
                            status=status.HTTP_409_CONFLICT)
        return Response(payload)


class RunnerClarificationCreateView(APIView):
    """POST /api/runner/clarifications/ — an agent (via its `ask_human` tool) opens a
    clarification for its run. Runner-token authenticated; tenant bound from the enrollment
    (never the body). Idempotent by question signature, so a re-ask reuses the same one."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        from apps.clarifications.services import create_clarification

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        data = request.data if isinstance(request.data, dict) else {}
        run_id = data.get("run_id")
        if not run_id:
            return Response({"detail": "run_id is required"},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            result = create_clarification(
                tenant_id=str(runner.tenant_id), run_id=str(run_id),
                questions=data.get("questions") or [], context=data.get("context", ""),
                phase=data.get("phase", ""), signature=data.get("signature", ""),
            )
        except Run.DoesNotExist:
            return Response({"detail": "run not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(result, status=status.HTTP_201_CREATED)


class RunnerClarificationPollView(APIView):
    """GET /api/runner/clarifications/<id>/ — the companion polls its clarification until the
    human answers it in the web app. While polling, the agent is idle on the open tool call,
    so no engine cost accrues during the wait."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request, clarification_id):
        from apps.clarifications.models import Clarification
        from apps.clarifications.services import get_clarification

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        try:
            result = get_clarification(
                tenant_id=str(runner.tenant_id), clarification_id=str(clarification_id))
        except Clarification.DoesNotExist:
            return Response({"detail": "clarification not found"},
                            status=status.HTTP_404_NOT_FOUND)
        return Response(result)


class RunnerWorkClaimView(APIView):
    """GET /api/runner/work/ — the companion daemon claims the next phase/build task dispatched
    to its enrollment. Atomically flips the run's dispatch to `claimed` (skip-locked so two
    daemons never grab the same run), returns `{kind, run_id, payload}`, or 204 when idle."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        from django.db import transaction
        from django.db.models import Q
        from django.utils import timezone

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        tid = str(runner.tenant_id)
        now = timezone.now()
        stale_before = (now - CLAIM_LEASE).isoformat()   # ISO8601 UTC sorts chronologically
        with tenant_context(tid), transaction.atomic():
            # A poll may claim a fresh `pending` dispatch OR re-claim one that a dead companion
            # left `claimed` past its lease (RC-3). Staleness is checked in Python on the ISO
            # claimed_at so we lean only on the proven exact JSON-key lookups in the query.
            #
            # Two kinds of dispatch are claimable by this runner:
            #   1. OWNED — dispatch.enrollment_id == this runner's id (the normal routed case:
            #      trigger resolved the triggering user's companion and pinned it).
            #   2. BROADCAST — dispatch.enrollment_id is null. A trigger issued while no companion
            #      was enrolled/available (e.g. the S.No 161 remediation auto-retry, which fires
            #      with no triggering user, or a user who triggers before starting their
            #      companion) stamps a null enrollment. Nothing matched enrollment_id, so the run
            #      sat RUNNING+unclaimable forever and blocked new triggers for the WorkItem (S.No
            #      169-adjacent build-dispatch binding bug). Let ANY active companion for the same
            #      tenant+project claim it and bind itself on claim, so the run self-heals the
            #      moment a companion is available. `=None` matches the JSON-null we store; the
            #      __isnull covers a dispatch that omitted the key entirely. Broadcast is scoped to
            #      the runner's project (via work_item) so a companion never steals another
            #      project's work; skip_locked + bind-on-claim keep it claimed exactly once.
            owned = Q(inputs__dispatch__enrollment_id=str(runner.id))
            broadcast = (
                Q(work_item__project_id=runner.project_id)
                & (Q(inputs__dispatch__enrollment_id=None)
                   | Q(inputs__dispatch__enrollment_id__isnull=True))
            )
            candidates = (
                Run.objects.select_for_update(skip_locked=True)
                .filter(tenant_id=tid)
                .filter(owned | broadcast)
                .filter(Q(inputs__dispatch__status="pending")
                        | Q(inputs__dispatch__status="claimed"))
                .order_by("created_at")
            )
            run = None
            reclaimed = False
            for cand in candidates:
                dispatch = (cand.inputs or {}).get("dispatch") or {}
                st = dispatch.get("status")
                if st == "pending":
                    run = cand
                    break
                claimed_at = dispatch.get("claimed_at")
                # Re-claim ONLY a still-in-flight run whose companion went silent past the
                # lease. Never re-run one that already reached a gate or a terminal state — a
                # long phase that just reported (dispatch flips to "reported" synchronously in
                # report_phase) or was gated/approved must not be re-run (the duplicate-v2
                # regression combined a stale lease with an already-finished phase).
                if (st == "claimed" and claimed_at and claimed_at < stale_before
                        and cand.status in (Run.Status.PENDING, Run.Status.RUNNING)):
                    run, reclaimed = cand, True
                    break
            if run is None:
                return Response(status=status.HTTP_204_NO_CONTENT)
            inputs = dict(run.inputs or {})
            dispatch = dict(inputs.get("dispatch") or {})
            # Bind a BROADCAST (null-enrollment) dispatch to the claiming runner so it is now
            # OWNED — subsequent polls, heartbeat claim-renewal and lease-reclaim all key off
            # enrollment_id, and only this companion should carry it from here.
            if dispatch.get("enrollment_id") in (None, ""):
                dispatch["enrollment_id"] = str(runner.id)
            dispatch["status"] = "claimed"
            dispatch["claimed_at"] = now.isoformat()
            # Bugs S.No 134: mark when THIS continuous claim started (reset on every fresh claim /
            # re-claim, never touched by heartbeat renewal) so the renewal cap can bound a claim
            # that is renewed forever without progressing.
            dispatch["first_claimed_at"] = now.isoformat()
            dispatch["claim_count"] = int(dispatch.get("claim_count") or 0) + 1
            inputs["dispatch"] = dispatch
            run.inputs = inputs
            run.save(update_fields=["inputs", "updated_at"])
            if reclaimed:
                tools.log_event(tid, "companion", "phase.reclaimed", "run", str(run.id),
                                {"claim_count": dispatch["claim_count"]})
            kind = dispatch.get("kind", "plan")
            key = {"plan": "phase_task", "review": "review_task",
                   "build": "build_task"}.get(kind, "phase_task")
            payload = inputs.get(key) or {}
            return Response({"kind": kind, "run_id": str(run.id), "payload": payload})


class RunnerHeartbeatView(APIView):
    """POST /api/runner/heartbeat/ — the companion pings this on a fixed cadence so the platform
    keeps the enrollment "online" even while a phase is running. The serve loop runs each phase
    synchronously (it is busy in run_task and not polling /work/), so without an independent
    heartbeat `last_seen` goes stale mid-phase and the UI falsely flips to "offline / daemon
    stopped" and disables triggers (Bugs.xlsx row 61 / RC-2). Resolving the runner refreshes
    last_seen; the body is otherwise trivial."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        renewed = _renew_claims_for(runner)
        return Response({"ok": True, "claims_renewed": renewed,
                         "last_seen": runner.last_seen.isoformat() if runner.last_seen else None})


class RunnerPhaseFetchView(APIView):
    """GET /api/runner/phases/<run_id>/ — the companion fetches its dispatched phase task
    (manifest + agent body), mirroring the build fetch."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request, run_id):
        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        with tenant_context(str(runner.tenant_id)):
            run = Run.objects.filter(id=run_id, tenant_id=runner.tenant_id).first()
        if run is None:
            return Response({"detail": "run not found"}, status=status.HTTP_404_NOT_FOUND)
        payload = (run.inputs or {}).get("phase_task")
        if not payload:
            return Response({"detail": "no phase task dispatched"},
                            status=status.HTTP_409_CONFLICT)
        return Response(payload)


class RunnerPhaseReportView(APIView):
    """POST /api/runner/phases/<run_id>/report/ — the companion reports its phase result;
    resumes the AgentRunWorkflow via the phase_reported signal."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, run_id):
        from orchestration.phase_report import PhaseReportError, report_phase

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        args = request.data if isinstance(request.data, dict) else {}
        try:
            out = report_phase(tenant_id=str(runner.tenant_id), run_id=str(run_id), report=args)
        except Run.DoesNotExist:
            return Response({"detail": "run not found"}, status=status.HTTP_404_NOT_FOUND)
        except PhaseReportError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out)


class RunnerReviewReportView(APIView):
    """POST /api/runner/reviews/<run_id>/report/ — the companion posts its 08 review verdict;
    the server-side CompanionReviewProvider's poll picks it up and parses the findings."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, run_id):
        from orchestration.review_provider import record_review_report

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        args = request.data if isinstance(request.data, dict) else {}
        try:
            out = record_review_report(
                tenant_id=str(runner.tenant_id), run_id=str(run_id),
                body=args.get("body", ""), status=args.get("status", "ok"))
        except Run.DoesNotExist:
            return Response({"detail": "run not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(out)


class RunnerBuildReportView(APIView):
    """POST /api/runner/builds/<run_id>/report/ — the companion reports its build result;
    resumes the BuildWorkflow via the build_reported signal."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, run_id):
        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        args = request.data if isinstance(request.data, dict) else {}
        try:
            out = report_build(tenant_id=str(runner.tenant_id), run_id=str(run_id), report=args)
        except Run.DoesNotExist:
            return Response({"detail": "run not found"}, status=status.HTTP_404_NOT_FOUND)
        except BuildReportError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out)


class RunnerCodeIntelClaimView(APIView):
    """GET /api/runner/code-intel/ — the companion claims the next pending code-intel job
    dispatched to its enrollment (Brownfield B4). Separate from the Run claim path (/work/) so
    the proven plan/review/build dispatch is untouched. Skip-locked so two daemons never grab the
    same job; a job a dead companion left `claimed` past the lease is re-claimable. Returns
    `{job_id, repo, base}` or 204 when idle."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        from django.db import transaction
        from django.db.models import Q
        from django.utils import timezone

        from apps.runs.models import CodeIntelJob

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        tid = str(runner.tenant_id)
        now = timezone.now()
        stale_before = now - CLAIM_LEASE
        with tenant_context(tid), transaction.atomic():
            # OWNED (routed here) OR BROADCAST (null enrollment, same project) — mirrors the Run
            # claim's self-healing so a job dispatched before a companion is up still runs.
            owned = Q(enrollment_id=runner.id)
            broadcast = Q(project_id=runner.project_id) & Q(enrollment__isnull=True)
            candidates = (
                CodeIntelJob.objects.select_for_update(skip_locked=True)
                .filter(tenant_id=tid)
                .filter(owned | broadcast)
                .filter(Q(status=CodeIntelJob.Status.PENDING)
                        | Q(status=CodeIntelJob.Status.CLAIMED))
                .order_by("created_at")
            )
            job = None
            for cand in candidates:
                if cand.status == CodeIntelJob.Status.PENDING:
                    job = cand
                    break
                if (cand.status == CodeIntelJob.Status.CLAIMED
                        and cand.claimed_at is not None and cand.claimed_at < stale_before):
                    job = cand   # a dead companion's stale claim → re-claim
                    break
            if job is None:
                return Response(status=status.HTTP_204_NO_CONTENT)
            if job.enrollment_id is None:
                job.enrollment_id = runner.id          # bind broadcast → owned on claim
            job.status = CodeIntelJob.Status.CLAIMED
            job.claimed_at = now
            job.save(update_fields=["enrollment", "status", "claimed_at", "updated_at"])
            return Response({
                "job_id": str(job.id),
                "repo": job.repo.name,
                "base": job.repo.default_base or "main",
            })


class RunnerCodeIntelReportView(APIView):
    """POST /api/runner/code-intel/<job_id>/report/ — the companion reports its code-intel result
    (B4). The server-side sink persists the `codebase_intelligence` artifact + Knowledge-Index
    chunk (`record_code_intel_index`). Only this companion-authenticated path can write a real
    index — the web dispatch endpoint no longer accepts one (B4-2). `{status:"failed", error}`
    marks the job failed without persisting anything."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, job_id):
        from apps.runs.models import CodeIntelJob
        from integrations.onboarding import record_code_intel_index

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        tid = str(runner.tenant_id)
        args = request.data if isinstance(request.data, dict) else {}
        with tenant_context(tid):
            job = CodeIntelJob.objects.filter(id=job_id, tenant_id=tid).first()
        if job is None:
            return Response({"detail": "job not found"}, status=status.HTTP_404_NOT_FOUND)

        if args.get("status") == "failed":
            with tenant_context(tid):
                job.status = CodeIntelJob.Status.FAILED
                job.error = str(args.get("error", ""))[:512]
                job.save(update_fields=["status", "error", "updated_at"])
            return Response({"status": "failed"})

        index = args.get("index") if isinstance(args.get("index"), dict) else {}
        out = record_code_intel_index(
            tenant_id=tid, project_id=str(job.project_id), repo_id=str(job.repo_id),
            index=index, summary=args.get("summary", ""))
        with tenant_context(tid):
            job.status = CodeIntelJob.Status.INDEXED
            job.result = {"artifact_id": out.get("artifact_id")}
            job.save(update_fields=["status", "result", "updated_at"])
        return Response(out)
