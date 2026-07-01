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

from apps.clarifications.models import Clarification
from apps.clarifications.services import (
    ClarificationError,
    ClarificationRoleError,
    answer_clarification,
)
from apps.gates.models import Approval
from apps.gates.services import GateError, GateRoleError, decide_gate
from apps.integrations.models import SourceDocument
from apps.ledger.models import Event
from apps.projects.models import Project
from apps.registry.models import Artifact, TraceEdge
from apps.runs.models import Run
from apps.tenancy.auth import IsTenantAdmin, current_user
from apps.tenancy.models import Invitation, Membership, Tenant, User
from apps.tenancy.services import (
    InvitationError,
    RoleError,
    create_invitation,
    create_tenant,
    grant_membership,
    list_tenant_users,
    project_role_coverage,
    resend_invitation,
    revoke_invitation,
    revoke_membership,
    set_tenant_admin,
)
from apps.workitems.models import WorkItem
from integrations.extract import ExtractionError
from integrations.onboarding import (
    OnboardingError,
    OnboardingRoleError,
    adopt_source_document,
    ingest_source_document,
    register_atlassian,
)
from integrations.types import CapabilityUnavailable
from orchestration.takeover import TakeoverError, release_takeover, request_takeover
from orchestration.trigger import TriggerError, trigger_phase

from .serializers import (
    AdoptSerializer,
    ApprovalSerializer,
    ArtifactSerializer,
    ClarificationAnswerSerializer,
    ClarificationSerializer,
    EventSerializer,
    GateDecisionSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
    MembershipCreateSerializer,
    MembershipSerializer,
    ProjectProfileSerializer,
    ProjectSerializer,
    RunSerializer,
    SourceDocumentSerializer,
    TenantAdminSerializer,
    TenantSerializer,
    TraceEdgeSerializer,
    TriggerSerializer,
    WorkItemSerializer,
)


def resolve_actor(request, body_user_id) -> str | None:
    """The user acting on this request (P4.7-T5). Prefer the authenticated session user —
    UI-driven `trigger`/`decide`/`answer` attribute to *that* user (and route phases to their
    companion); the `user_id` body param is ignored under a session and kept only as the
    pre-auth/runner/test fallback. Returns the id as a str, or None when neither is present."""
    user = current_user(request)
    if user is not None:
        return str(user.id)
    return str(body_user_id) if body_user_id else None


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

    def get_permissions(self):
        # Admin-only surfaces for user/role management (P4.7-T4). Everything else keeps the
        # project viewset's default (AllowAny + tenant scoping / RLS).
        if self.action in {"memberships", "delete_membership", "role_coverage"}:
            return [IsTenantAdmin()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.tenant_id)

    @action(detail=True, methods=["get", "post"])
    def memberships(self, request, pk=None):
        """GET the project's role grants / POST a new one (admin). `role="admin"` grants a
        project-admin who can approve any gate on this project (P4.7-T4)."""
        project = self.get_object()
        if request.method == "GET":
            qs = Membership.objects.filter(
                tenant_id=self.tenant_id, project=project
            ).order_by("role")
            return Response(MembershipSerializer(qs, many=True).data)

        ser = MembershipCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            membership = grant_membership(
                tenant=project.tenant, project=project,
                user_id=str(ser.validated_data["user_id"]),
                role=ser.validated_data["role"],
            )
        except RoleError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(
            MembershipSerializer(membership).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["delete"],
            url_path=r"memberships/(?P<mid>[^/.]+)")
    def delete_membership(self, request, pk=None, mid=None):
        """DELETE a project-role grant (admin). The tenant-admin population is guarded on the
        user endpoint, not here — project-role grants carry no last-admin guard."""
        project = self.get_object()
        try:
            revoke_membership(
                tenant=project.tenant, project=project, membership_id=mid
            )
        except RoleError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path="role-coverage")
    def role_coverage(self, request, pk=None):
        """Gate-role coverage for the project (S-08): per gate role → holders, covered,
        gate_blocked (+ note), and whether an admin fallback exists (admin approves any gate)."""
        project = self.get_object()
        return Response(project_role_coverage(tenant=project.tenant, project=project))

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

    @action(detail=True, methods=["get"])
    def traceability(self, request, pk=None):
        """Lineage graph for the viewer (spec §5): artifact nodes + their TraceEdges,
        each node carrying its SoR pointer/url so the UI can deep-link to the live
        Confluence page / Jira issue. The requirement→PRD→epic→story chain walks these."""
        project = self.get_object()
        artifacts = Artifact.objects.filter(tenant_id=self.tenant_id, project=project)
        nodes = []
        for a in artifacts:
            ext = a.external_ref or {}
            nodes.append({
                "id": str(a.id), "kind": "artifact", "phase": a.phase, "type": a.type,
                "status": a.status, "sor": a.sor,
                "external_ref": ext or None, "url": ext.get("url"),
            })
        edges = TraceEdge.objects.filter(
            tenant_id=self.tenant_id, from_artifact__project=project
        )
        edge_list = [
            {"from": str(e.from_artifact_id), "to": str(e.to_artifact_id), "rel": e.rel}
            for e in edges
        ]
        return Response({"nodes": nodes, "edges": edge_list})

    @action(detail=True, methods=["get", "post"], url_path="source-documents")
    def source_documents(self, request, pk=None):
        """GET list / POST upload a static file for brownfield-lite extraction (spec §6)."""
        project = self.get_object()
        if request.method == "GET":
            qs = (
                SourceDocument.objects
                .filter(tenant_id=self.tenant_id, project=project).order_by("-created_at")
            )
            return Response(SourceDocumentSerializer(qs, many=True).data)

        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "a multipart 'file' is required"})
        try:
            out = ingest_source_document(
                tenant_id=self.tenant_id, project_id=str(project.id),
                filename=upload.name, mime=upload.content_type or "", content=upload.read(),
                artifact_type=request.data.get("artifact_type", "document"),
            )
        except ExtractionError as exc:
            raise ValidationError({"file": str(exc)}) from exc
        return Response(out, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="onboard-atlassian")
    def onboard_atlassian(self, request, pk=None):
        """Register-don't-recreate against the tenant's Confluence/Jira (spec §6)."""
        project = self.get_object()
        try:
            out = register_atlassian(tenant_id=self.tenant_id, project_id=str(project.id))
        except CapabilityUnavailable as exc:
            raise ValidationError(str(exc)) from exc
        return Response(out)


# ── Source documents + onboarding review gate ───────────────────────
class SourceDocumentViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = SourceDocumentSerializer
    queryset = SourceDocument.objects.all().order_by("-created_at")

    @action(detail=True, methods=["post"])
    def adopt(self, request, pk=None):
        """Review gate: a product_owner publishes the extracted draft artifacts."""
        src = self.get_object()
        ser = AdoptSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            out = adopt_source_document(
                tenant_id=self.tenant_id, source_document_id=str(src.id),
                user_id=str(ser.validated_data["user_id"]),
            )
        except OnboardingRoleError as exc:
            raise PermissionDenied(str(exc)) from exc
        except OnboardingError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(out)


# ── Users & tenant-admin (admin — P4.7-T4) ──────────────────────────
class UserViewSet(TenantScopedMixin, viewsets.GenericViewSet):
    """Admin surface for the tenant's users (S-07 table) + the tenant-admin toggle (S-08).
    Roles per project are managed via `/projects/{id}/memberships/`; this is the tenant-wide
    admin flag only."""

    permission_classes = [IsTenantAdmin]
    queryset = User.objects.all()

    def list(self, request):
        tenant = Tenant.objects.get(id=self.tenant_id)
        return Response(list_tenant_users(tenant))

    def partial_update(self, request, pk=None):
        """PATCH /api/users/{id}/ {is_tenant_admin} — promote/demote. Guards the tenant's
        last admin (409)."""
        ser = TenantAdminSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        tenant = Tenant.objects.get(id=self.tenant_id)
        try:
            user = set_tenant_admin(
                tenant=tenant, user_id=str(pk),
                is_admin=ser.validated_data["is_tenant_admin"],
            )
        except RoleError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response({
            "id": str(user.id), "name": user.name, "email": user.email,
            "is_tenant_admin": user.is_tenant_admin,
        })


# ── Invitations (admin — P4.7-T3) ───────────────────────────────────
class InvitationViewSet(
    TenantScopedMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Admin-managed tenant invitations. Create emails an accept link; resend rotates the
    token; revoke disables it. The raw token is never returned in any payload."""

    permission_classes = [IsTenantAdmin]
    serializer_class = InvitationSerializer
    queryset = Invitation.objects.all().order_by("-created_at")

    def create(self, request, *args, **kwargs):
        ser = InvitationCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        tenant = Tenant.objects.get(id=self.tenant_id)
        try:
            invitation, _raw = create_invitation(
                tenant=tenant, invited_by=request.user,
                email=ser.validated_data["email"],
                name=ser.validated_data.get("name", ""),
                grants=ser.validated_data.get("grants", []),
            )
        except InvitationError as exc:
            raise ValidationError({"email": str(exc)}) from exc
        return Response(
            InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def resend(self, request, pk=None):
        invitation = self.get_object()
        try:
            resend_invitation(invitation)
        except InvitationError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(InvitationSerializer(invitation).data)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        invitation = self.get_object()
        try:
            revoke_invitation(invitation)
        except InvitationError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(InvitationSerializer(invitation).data)


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
            # Actor = the session user when present (routes the phase to *their* companion
            # enrollment), else the pre-auth/runner `user_id` body param (T5).
            triggered_by = resolve_actor(request, ser.validated_data.get("user_id"))
            result = trigger_phase(
                tenant_id=self.tenant_id,
                project_id=str(work_item.project_id),
                work_item_id=str(work_item.id),
                agent_key=ser.validated_data["agent_key"],
                gate_type=ser.validated_data["gate_type"],
                required_role=ser.validated_data["required_role"],
                triggered_by=triggered_by,
            )
        except TriggerError as exc:
            raise ValidationError({"agent_key": str(exc)}) from exc
        return Response(
            {"run_id": result.run_id, "workflow_id": result.workflow_id},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"], url_path="take-over")
    def take_over(self, request, pk=None):
        """Human takeover (PG10, §7): the developer takes this WorkItem over to hand-work the
        worktree branch; automation pauses and their commits reconcile via the GitHub webhook.
        `release=true` hands it back to automation."""
        work_item = self.get_object()
        try:
            if request.data.get("release"):
                out = release_takeover(
                    tenant_id=self.tenant_id, work_item_id=str(work_item.id),
                    actor=request.data.get("actor", "developer"),
                )
            else:
                out = request_takeover(
                    tenant_id=self.tenant_id, work_item_id=str(work_item.id),
                    actor=request.data.get("actor", "developer"),
                    reason=request.data.get("reason", ""),
                )
        except TakeoverError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(out)


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
        user_id = resolve_actor(request, ser.validated_data.get("user_id"))
        if user_id is None:
            raise ValidationError({"user_id": "required when not authenticated"})
        try:
            result = decide_gate(
                tenant_id=self.tenant_id,
                approval_id=str(approval.id),
                user_id=user_id,
                decision=ser.validated_data["decision"],
                comment=ser.validated_data["comment"],
                conditions=ser.validated_data.get("conditions"),
            )
        except GateRoleError as exc:
            raise PermissionDenied(str(exc)) from exc
        except GateError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(result, status=status.HTTP_200_OK)


# ── Clarifications + answer (interactive Q&A — req #2) ───────────────
class ClarificationViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    """List clarifications (filter by status/run/work_item) and answer a pending one. A
    pending Clarification blocks the agent on its `ask_human` tool call (model idle → no
    cost); answering here records the answer and the companion's poll resumes the run."""

    serializer_class = ClarificationSerializer
    queryset = Clarification.objects.all().order_by("-created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        for field in ("status", "run", "work_item"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{("run_id" if field == "run" else
                                   "work_item_id" if field == "work_item" else field): value})
        return qs

    @action(detail=True, methods=["post"])
    def answer(self, request, pk=None):
        """Answer a pending clarification: project-membership check → required-answer check
        → record. The blocked agent resumes in the same session."""
        clarification = self.get_object()
        ser = ClarificationAnswerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user_id = resolve_actor(request, ser.validated_data.get("user_id"))
        if user_id is None:
            raise ValidationError({"user_id": "required when not authenticated"})
        try:
            result = answer_clarification(
                tenant_id=self.tenant_id,
                clarification_id=str(clarification.id),
                user_id=user_id,
                answers=ser.validated_data.get("answers") or {},
            )
        except ClarificationRoleError as exc:
            raise PermissionDenied(str(exc)) from exc
        except ClarificationError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(result, status=status.HTTP_200_OK)
