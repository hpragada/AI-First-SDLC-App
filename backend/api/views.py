"""Phase-0 REST views.

Every resource except tenant-create is tenant-scoped: the tenant is resolved by
`TenantContextMiddleware` (which sets the RLS GUC and stashes `request.tenant_id`),
and each queryset *also* filters on `tenant_id` explicitly — defense-in-depth, and
the actual enforcement under the local superuser connection where RLS is bypassed.
Custom actions delegate to the domain services (`trigger_phase`, `decide_gate`).
"""
from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ParseError, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.gates.models import Approval
from apps.gates.services import GateError, GateRoleError, decide_gate
from apps.ledger.models import Event
from apps.projects.models import Project
from apps.registry.models import Artifact, TraceEdge
from apps.runs.models import Run
from apps.tenancy.services import create_tenant
from apps.workitems.models import WorkItem
from orchestration.trigger import TriggerError, trigger_phase

from .serializers import (
    ApprovalSerializer,
    ArtifactSerializer,
    EventSerializer,
    GateDecisionSerializer,
    ProjectProfileSerializer,
    ProjectSerializer,
    RunSerializer,
    TenantSerializer,
    TraceEdgeSerializer,
    TriggerSerializer,
    WorkItemSerializer,
)


class TenantScopedMixin:
    """Resolve the request tenant and scope every queryset to it."""

    @property
    def tenant_id(self) -> str:
        tid = getattr(self.request, "tenant_id", None)
        if not tid:
            raise ParseError("X-Tenant-ID header is required for this resource.")
        return str(tid)

    def get_queryset(self):
        return super().get_queryset().filter(tenant_id=self.tenant_id)


# ── Tenant (bootstrap — no tenant context exists yet) ───────────────
class TenantCreateView(APIView):
    """POST /api/tenants/ — create a tenant (the one un-scoped write)."""

    def post(self, request):
        ser = TenantSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        tenant = create_tenant(
            name=ser.validated_data["name"],
            config=ser.validated_data.get("config") or {},
            model_routing=ser.validated_data.get("model_routing") or {},
        )
        return Response(TenantSerializer(tenant).data, status=status.HTTP_201_CREATED)


# ── Projects + Profile ──────────────────────────────────────────────
class ProjectViewSet(
    TenantScopedMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ProjectSerializer
    queryset = Project.objects.all().order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.tenant_id)

    @action(detail=True, methods=["get", "put"])
    def profile(self, request, pk=None):
        """GET/PUT the project's 1:1 ProjectProfile (the manifest source)."""
        project = self.get_object()
        if request.method == "GET":
            profile = getattr(project, "profile", None)
            if profile is None:
                return Response(status=status.HTTP_404_NOT_FOUND)
            return Response(ProjectProfileSerializer(profile).data)

        # PUT — create or update (1:1), bumping version on each edit.
        profile = getattr(project, "profile", None)
        ser = ProjectProfileSerializer(instance=profile, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        if profile is None:
            profile = ser.save(tenant_id=self.tenant_id, project=project)
            created = True
        else:
            profile = ser.save()
            profile.version += 1
            profile.save(update_fields=["version", "updated_at"])
            created = False
        code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(ProjectProfileSerializer(profile).data, status=code)


# ── WorkItems + phase trigger ───────────────────────────────────────
class WorkItemViewSet(
    TenantScopedMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = WorkItemSerializer
    queryset = WorkItem.objects.all().order_by("-created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        project = self.request.query_params.get("project")
        state = self.request.query_params.get("state")
        if project:
            qs = qs.filter(project_id=project)
        if state:
            qs = qs.filter(state=state)
        return qs

    def perform_create(self, serializer):
        project_id = self.request.data.get("project")
        if not Project.objects.filter(id=project_id, tenant_id=self.tenant_id).exists():
            raise ValidationError({"project": "unknown project for this tenant"})
        serializer.save(tenant_id=self.tenant_id, project_id=project_id)

    @action(detail=True, methods=["post"])
    def trigger(self, request, pk=None):
        """Start a phase run for this work item (replaces the legacy command)."""
        work_item = self.get_object()
        ser = TriggerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            result = trigger_phase(
                tenant_id=self.tenant_id,
                project_id=str(work_item.project_id),
                work_item_id=str(work_item.id),
                agent_key=ser.validated_data["agent_key"],
                gate_type=ser.validated_data["gate_type"],
                required_role=ser.validated_data["required_role"],
            )
        except TriggerError as exc:
            raise ValidationError({"agent_key": str(exc)}) from exc
        return Response(
            {"run_id": result.run_id, "workflow_id": result.workflow_id},
            status=status.HTTP_202_ACCEPTED,
        )


# ── Runs (read-only) ────────────────────────────────────────────────
class RunViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = RunSerializer
    queryset = Run.objects.all().order_by("-created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        work_item = self.request.query_params.get("work_item")
        project = self.request.query_params.get("project")
        if work_item:
            qs = qs.filter(work_item_id=work_item)
        if project:
            qs = qs.filter(work_item__project_id=project)
        return qs


# ── Artifacts (read-only — pointers/provenance) ─────────────────────
class ArtifactViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ArtifactSerializer
    queryset = Artifact.objects.all().order_by("-created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        for field in ("project", "phase", "status"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{("project_id" if field == "project" else field): value})
        return qs


class TraceEdgeViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = TraceEdgeSerializer
    queryset = TraceEdge.objects.all().order_by("-created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        project = self.request.query_params.get("project")
        if project:
            qs = qs.filter(from_artifact__project_id=project)
        return qs


# ── Events (read-only, append-only ledger) ──────────────────────────
class EventViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = EventSerializer
    queryset = Event.objects.all().order_by("-ts")

    def get_queryset(self):
        qs = super().get_queryset()
        for field in ("actor", "action", "target_type", "target_id"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        return qs


# ── Approvals + gate decision ───────────────────────────────────────
class ApprovalViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ApprovalSerializer
    queryset = Approval.objects.all().order_by("-created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        for field in ("decision", "run", "work_item"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{("run_id" if field == "run" else
                                   "work_item_id" if field == "work_item" else field): value})
        return qs

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        """Decide a pending gate (spec §6): role check → record → signal workflow."""
        approval = self.get_object()
        ser = GateDecisionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            result = decide_gate(
                tenant_id=self.tenant_id,
                approval_id=str(approval.id),
                user_id=str(ser.validated_data["user_id"]),
                decision=ser.validated_data["decision"],
                comment=ser.validated_data["comment"],
            )
        except GateRoleError as exc:
            raise PermissionDenied(str(exc)) from exc
        except GateError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(result, status=status.HTTP_200_OK)
