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

from mcp_platform_state import tools
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project
from apps.runs.enrollment import authenticate_runner, enroll_runner, revoke_runner
from apps.runs.models import Run, RunnerEnrollment
from apps.tenancy.context import tenant_context
from orchestration.build_report import BuildReportError, report_build

# Build-phase platform-state tool allowlist (no detect_drift, no planning-only tools).
_BUILD_STATE_TOOLS = {
    "get_context": tools.get_context,
    "get_artifact": tools.get_artifact,
    "list_artifacts": tools.list_artifacts,
    "register_artifact": tools.register_artifact,
    "update_artifact": tools.update_artifact,
    "add_trace_edge": tools.add_trace_edge,
    "log_event": tools.log_event,
    "list_work_items": tools.list_work_items,
    "create_work_item": tools.create_work_item,
    "transition_work_item": tools.transition_work_item,
}


def _tenant_id(request) -> str:
    tid = getattr(request, "tenant_id", None)
    if not tid:
        from rest_framework.exceptions import ParseError

        raise ParseError("X-Tenant-ID header is required.")
    return str(tid)


def _serialize(e: RunnerEnrollment) -> dict:
    return {
        "id": str(e.id), "project_id": str(e.project_id), "label": e.label,
        "repos": e.repos, "status": e.status,
        "developer_id": str(e.developer_id) if e.developer_id else None,
        "last_seen": e.last_seen.isoformat() if e.last_seen else None,
    }


class RunnerEnrollmentView(APIView):
    """GET list / POST enroll a local-companion runner for this tenant."""

    def get(self, request):
        tenant_id = _tenant_id(request)
        qs = RunnerEnrollment.objects.filter(tenant_id=tenant_id).order_by("-created_at")
        return Response([_serialize(e) for e in qs])

    def post(self, request):
        tenant_id = _tenant_id(request)
        project_id = request.data.get("project_id")
        if not project_id:
            return Response({"project_id": "required"}, status=status.HTTP_400_BAD_REQUEST)
        # Validate the project is in this tenant (scoped read).
        if not Project.objects.filter(id=project_id, tenant_id=tenant_id).exists():
            return Response({"project_id": "not found in tenant"},
                            status=status.HTTP_404_NOT_FOUND)
        enrollment, token = enroll_runner(
            tenant_id=tenant_id, project_id=project_id,
            developer_id=request.data.get("developer_id"),
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

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        tid = str(runner.tenant_id)
        with tenant_context(tid), transaction.atomic():
            run = (
                Run.objects.select_for_update(skip_locked=True)
                .filter(tenant_id=tid, inputs__dispatch__status="pending",
                        inputs__dispatch__enrollment_id=str(runner.id))
                .order_by("created_at").first()
            )
            if run is None:
                return Response(status=status.HTTP_204_NO_CONTENT)
            inputs = dict(run.inputs or {})
            dispatch = dict(inputs.get("dispatch") or {})
            dispatch["status"] = "claimed"
            inputs["dispatch"] = dispatch
            run.inputs = inputs
            run.save(update_fields=["inputs", "updated_at"])
            kind = dispatch.get("kind", "plan")
            key = {"plan": "phase_task", "review": "review_task",
                   "build": "build_task"}.get(kind, "phase_task")
            payload = inputs.get(key) or {}
            return Response({"kind": kind, "run_id": str(run.id), "payload": payload})


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
