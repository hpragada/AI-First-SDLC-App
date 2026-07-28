"""Phase-0 REST views.

Every resource except tenant-create is tenant-scoped: the tenant is resolved by
`TenantContextMiddleware` (which sets the RLS GUC and stashes `request.tenant_id`),
and each queryset *also* filters on `tenant_id` explicitly — defense-in-depth, and
the actual enforcement under the local superuser connection where RLS is bypassed.
Custom actions delegate to the domain services (`trigger_phase`, `decide_gate`).
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ParseError, PermissionDenied, ValidationError
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
from apps.integrations.models import DriftRecord, IntegrationConnection, SourceDocument
from apps.integrations.services import (
    IntegrationError,
    create_integration,
    test_credentials,
    test_integration_connection,
    update_integration,
)
from apps.ledger.models import Event
from apps.projects.models import Project, Repository
from apps.projects.repos import (
    RepositoryError,
    add_repository,
    remove_repository,
    repositories_for,
    require_repo_manage_role,
    set_default_repository,
    update_repository,
)
from apps.registry.catalog import gate_role_for
from apps.registry.catalog import rides_build as catalog_rides_build
from apps.registry.models import AgentSpec, Artifact, TraceEdge
from apps.runs.models import Run
from apps.tenancy.auth import IsAuthenticatedMember, IsTenantAdmin, current_user
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
from integrations.api_contract import list_api_contracts, read_api_contract_body
from integrations.drift import DriftError, DriftRoleError, decide_drift, drift_queue
from integrations.extract import ExtractionError
from integrations.onboarding import (
    OnboardingError,
    OnboardingRoleError,
    adopt_source_document,
    build_gap_report,
    ingest_source_document,
    link_confluence_pages,
    onboarding_hub,
    read_gap_report,
    register_atlassian,
)
from integrations.preview import read_artifact_preview
from integrations.types import CapabilityUnavailable
from orchestration.takeover import (
    ResumeError,
    TakeoverError,
    abandon_stalled_run,
    release_takeover,
    request_takeover,
    resume_stalled_run,
)
from orchestration.trigger import (
    ActiveRunError,
    NoCompanionError,
    TriggerError,
    trigger_build,
    trigger_code_intel,
    trigger_onboarding_agent,
    trigger_phase,
)

from .serializers import (
    AdoptSerializer,
    ApprovalSerializer,
    ArtifactSerializer,
    BuildTriggerSerializer,
    ClarificationAnswerSerializer,
    ClarificationSerializer,
    CodeIntelDispatchSerializer,
    DriftDecisionSerializer,
    DriftRecordSerializer,
    EventSerializer,
    GateDecisionSerializer,
    IntegrationCreateSerializer,
    IntegrationSerializer,
    IntegrationTestCredentialsSerializer,
    IntegrationUpdateSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
    LinkConfluenceSerializer,
    MembershipCreateSerializer,
    MembershipSerializer,
    ProjectCITokenSerializer,
    ProjectProfileSerializer,
    ProjectSerializer,
    RepositoryCreateSerializer,
    RepositoryUpdateSerializer,
    RunSerializer,
    SourceDocumentSerializer,
    TenantAdminSerializer,
    TenantSerializer,
    TraceEdgeSerializer,
    TriggerSerializer,
    WorkItemPatchSerializer,
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
        if self.action in {"memberships", "delete_membership", "role_coverage",
                           "ci_tokens", "revoke_ci_token"}:
            return [IsTenantAdmin()]
        # Repositories (P4.7-T7): any authenticated member may read; add/remove/set-default
        # are further gated per-project (tech_lead/admin) inside the action itself.
        if self.action in {"repositories", "repository_detail", "set_repository_default"}:
            return [IsAuthenticatedMember()]
        # Brownfield onboarding (P4.7-T8): any authenticated member may read/build; code-intel
        # is further gated per-project (tech_lead/admin) inside the action itself. link_confluence
        # (B3-4) is a new mutating endpoint — gate it from the start rather than ship a new hole.
        if self.action in {"onboarding", "code_intel", "gap_report", "link_confluence"}:
            return [IsAuthenticatedMember()]
        # API contracts & drift (P4.7-T9): any authenticated member may read.
        if self.action in {"api_contracts", "api_contract_detail", "drift"}:
            return [IsAuthenticatedMember()]
        # Dashboard rollup (S-31): authenticated member.
        if self.action == "dashboard":
            return [IsAuthenticatedMember()]
        return super().get_permissions()

    def perform_create(self, serializer):
        project = serializer.save(tenant_id=self.tenant_id)
        # Any authenticated tenant member may create a project (see get_permissions above),
        # but the frontend only ever offers a project as "selectable" via the creator's own
        # Membership rows (there's no unscoped project-list call) — without this grant, the
        # creator could never see or select the project they just made.
        user = current_user(self.request)
        if user is not None:
            try:
                grant_membership(
                    tenant=project.tenant, project=project, user_id=str(user.id), role="admin",
                )
            except RoleError:
                pass  # already holds the role somehow — not worth failing project creation over

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

    @action(detail=True, methods=["get", "post"], url_path="ci-tokens")
    def ci_tokens(self, request, pk=None):
        """GET the project's CI ingest tokens (metadata only) / POST to issue a new one (admin,
        P3-09bX-1). The raw secret is returned **once** on issue and never again — the client
        copies it into their CI secret store; only its hash is stored."""
        from apps.projects.ci_tokens import issue_ci_token, list_ci_tokens

        project = self.get_object()
        if request.method == "GET":
            rows = list_ci_tokens(tenant_id=self.tenant_id, project_id=str(project.id))
            return Response(ProjectCITokenSerializer(rows, many=True).data)

        user = current_user(request)
        row, token = issue_ci_token(
            tenant_id=self.tenant_id, project_id=str(project.id),
            label=request.data.get("label", ""),
            created_by_id=str(user.id) if user is not None else None,
        )
        data = ProjectCITokenSerializer(row).data
        data["token"] = token       # shown ONCE — never stored, never returned again
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"ci-tokens/(?P<token_id>[^/.]+)")
    def revoke_ci_token(self, request, pk=None, token_id=None):
        """Revoke a CI ingest token (admin). It stops authenticating immediately; the row is kept
        for the audit trail (status=revoked)."""
        from apps.projects.ci_tokens import revoke_ci_token

        self.get_object()       # tenant-scopes + 404s if the project isn't the caller's
        if not revoke_ci_token(tenant_id=self.tenant_id, token_id=token_id):
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

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

    @action(detail=True, methods=["get"], url_path="export-policy")
    def export_policy(self, request, pk=None):
        """The project's phase-scoped manual-export policy (team flow decision
        2026-07-07): code defaults overlaid with ProjectProfile.export_policy overrides,
        plus which export capabilities have a connector bound — so the UI can drive the
        Export modal / profile matrix and pre-warn 'no connector configured'."""
        from integrations.export_policy import DEFAULT_EXPORT_POLICY, effective_policy
        from integrations.registry import get_connection

        project = self.get_object()
        profile = getattr(project, "profile", None)
        return Response({
            "defaults": DEFAULT_EXPORT_POLICY,
            "overrides": (profile.export_policy if profile else {}) or {},
            "effective": effective_policy(profile),
            "connected": {
                cap: get_connection(self.tenant_id, cap) is not None
                for cap in ("docstore", "tasktracker", "testmgmt")
            },
        })

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
                "title": a.title, "status": a.status, "sor": a.sor,
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
        """Import the existing Jira backlog (register-don't-recreate, spec §6). B3-1: graceful —
        if Jira isn't connected the service skips it and returns 200 (`tasktracker_connected:
        false`); no dead-end 400. The hub drives the connect affordance from the connection
        status, and Confluence docs are linked separately + typed via `link-confluence`."""
        project = self.get_object()
        out = register_atlassian(tenant_id=self.tenant_id, project_id=str(project.id))
        return Response(out)

    @action(detail=True, methods=["post"], url_path="link-confluence")
    def link_confluence(self, request, pk=None):
        """B3-4 — register user-provided Confluence pages as *typed* pointers so they feed the
        gap report (unlike the old untyped whole-space crawl). Body: `{"links": [{"page":
        <url-or-id>, "type": <canonical lifecycle type>}, ...]}`. Returns per-row `linked` +
        `errors`. A missing docstore connector surfaces as a friendly 400 (no tenant id)."""
        project = self.get_object()
        ser = LinkConfluenceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            out = link_confluence_pages(
                tenant_id=self.tenant_id, project_id=str(project.id),
                links=ser.validated_data["links"],
            )
        except CapabilityUnavailable as exc:
            raise ValidationError(str(exc)) from exc
        return Response(out)

    # ── Brownfield onboarding (P4.7-T8, backs S-24/S-25/S-26) ────────
    @action(detail=True, methods=["get"])
    def onboarding(self, request, pk=None):
        """GET the onboarding hub state (S-24): upload/adopt/register/index/gap in one read."""
        project = self.get_object()
        return Response(onboarding_hub(tenant_id=self.tenant_id, project_id=str(project.id)))

    @action(detail=True, methods=["post"], url_path="code-intel")
    def code_intel(self, request, pk=None):
        """POST — **dispatch** a code-intelligence indexing job for a repo (B4; tech_lead/admin).
        The enrolled companion claims it, runs the built-in analyzer in a read-only worktree, and
        reports the real index back (the companion report sink persists the `codebase_intelligence`
        artifact + Knowledge-Index chunk). B4-2: this endpoint no longer accepts a client-supplied
        index — the fabrication path is closed; only the companion can write a real analysis."""
        project = self.get_object()
        ser = CodeIntelDispatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        actor = resolve_actor(request, ser.validated_data.get("user_id"))
        repo_id = ser.validated_data["repo_id"]
        try:
            require_repo_manage_role(
                tenant_id=self.tenant_id, project_id=str(project.id), user_id=actor
            )
            try:
                # Agent-driven (primary): the 00c agent runs on the triggering user's companion,
                # analyses the repo in a read-only worktree via the CodeIntel MCP, and registers
                # the intelligence artifacts (gated).
                res = trigger_onboarding_agent(
                    tenant_id=self.tenant_id, project_id=str(project.id),
                    agent_key="00c_intelligent_context_extractor", repo_id=repo_id,
                    triggered_by=actor,
                )
                out = {"mode": "agent", "run_id": res.run_id, "workflow_id": res.workflow_id}
            except NoCompanionError:
                # No companion enrolled for this user → the mechanical CodeIntelJob dispatch
                # (broadcast; any tenant companion may claim) so onboarding never dead-ends.
                out = {"mode": "mechanical", **trigger_code_intel(
                    tenant_id=self.tenant_id, project_id=str(project.id),
                    repo_id=repo_id, triggered_by=actor,
                )}
        except ActiveRunError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except RepositoryError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        except Repository.DoesNotExist:
            return Response({"detail": "unknown repository for this project"},
                            status=status.HTTP_404_NOT_FOUND)
        return Response(out, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["get", "post"], url_path="gap-report")
    def gap_report(self, request, pk=None):
        """GET the latest gap report (read-through, no recompute; `404` if none built yet) /
        POST to (re)build one from the currently registered evidence (S-26)."""
        project = self.get_object()
        if request.method == "GET":
            out = read_gap_report(tenant_id=self.tenant_id, project_id=str(project.id))
            if out is None:
                return Response(status=status.HTTP_404_NOT_FOUND)
            return Response(out)
        # POST — (re)build the gap report. Agent-driven (primary): the 00_onboarding agent runs on
        # the companion, reasons over every phase's evidence + the code intelligence, and submits
        # the report through the shape-safe writer (async → 202). No companion → the deterministic
        # build_gap_report fallback runs inline and returns the report (200), so onboarding never
        # dead-ends.
        try:
            res = trigger_onboarding_agent(
                tenant_id=self.tenant_id, project_id=str(project.id),
                agent_key="00_onboarding", triggered_by=resolve_actor(request, None),
            )
            return Response(
                {"mode": "agent", "run_id": res.run_id, "workflow_id": res.workflow_id},
                status=status.HTTP_202_ACCEPTED)
        except ActiveRunError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except NoCompanionError:
            build_gap_report(tenant_id=self.tenant_id, project_id=str(project.id))
            # Re-read through the same shape GET returns — one representation for this resource.
            out = read_gap_report(tenant_id=self.tenant_id, project_id=str(project.id))
            return Response({"mode": "deterministic", **(out or {})}, status=status.HTTP_200_OK)

    # ── API contracts & drift (P4.7-T9, backs S-27) ──────────────────
    @action(detail=True, methods=["get"], url_path="api-contracts")
    def api_contracts(self, request, pk=None):
        """GET the project's registered API contract(s) (S-27 Contracts tab)."""
        project = self.get_object()
        return Response(list_api_contracts(tenant_id=self.tenant_id, project_id=str(project.id)))

    @action(detail=True, methods=["get"], url_path=r"api-contracts/(?P<aid>[^/.]+)")
    def api_contract_detail(self, request, pk=None, aid=None):
        """GET the contract's current rendered body, read-through from S3 (S-27 → S-29)."""
        project = self.get_object()
        out = read_api_contract_body(
            tenant_id=self.tenant_id, project_id=str(project.id), artifact_id=aid
        )
        if out is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(out)

    @action(detail=True, methods=["get"])
    def drift(self, request, pk=None):
        """GET the open drift queue with cross-repo change-impact (S-27 Drift queue tab)."""
        project = self.get_object()
        return Response(drift_queue(tenant_id=self.tenant_id, project_id=str(project.id)))

    @action(detail=True, methods=["get"])
    def dashboard(self, request, pk=None):
        """S-31 dashboard rollup: needs-me items (pending gates, clarifications, my runs)
        + health counters + recent publishes — all scoped to this project and current user."""
        project = self.get_object()
        user = current_user(request)
        tid = self.tenant_id
        one_week_ago = timezone.now() - timedelta(days=7)

        pending_gates = (
            Approval.objects.filter(tenant_id=tid, work_item__project=project, decision="pending")
            .select_related("work_item")[:20]
        )
        pending_clarifications = (
            Clarification.objects.filter(tenant_id=tid, work_item__project=project, status="pending")
            .select_related("work_item")[:20]
        )
        my_runs = []
        if user:
            my_runs = list(
                Run.objects.filter(
                    tenant_id=tid, work_item__project=project,
                    triggered_by=user, status__in=["running", "awaiting_gate"],
                ).select_related("agent_spec")[:10]
            )

        recent_published = list(
            Artifact.objects.filter(
                tenant_id=tid, project=project,
                status=Artifact.Status.PUBLISHED, created_at__gte=one_week_ago,
            ).order_by("-created_at")[:5]
        )

        return Response({
            "needs_me": {
                "gates": [
                    {
                        "approval_id": str(a.id),
                        "gate": a.gate_type,
                        "work_item": str(a.work_item_id),
                        "role": a.required_role,
                    }
                    for a in pending_gates
                ],
                "clarifications": [
                    {
                        "id": str(c.id),
                        "work_item": str(c.work_item_id),
                        "question": (c.questions[0]["text"] if c.questions else ""),
                        "waiting_s": int((timezone.now() - c.created_at).total_seconds()),
                    }
                    for c in pending_clarifications
                ],
                "my_runs": [
                    {
                        "run_id": str(r.id),
                        "phase": r.agent_spec.key if r.agent_spec_id else "",
                        "work_item": str(r.work_item_id),
                        "status": r.status,
                    }
                    for r in my_runs
                ],
            },
            "health": {
                "work_items": WorkItem.objects.filter(tenant_id=tid, project=project).count(),
                "phases_in_progress": Run.objects.filter(
                    tenant_id=tid, work_item__project=project, status="running"
                ).count(),
                "awaiting_gate": Approval.objects.filter(
                    tenant_id=tid, work_item__project=project, decision="pending"
                ).count(),
                "published_week": Artifact.objects.filter(
                    tenant_id=tid, project=project,
                    status=Artifact.Status.PUBLISHED, created_at__gte=one_week_ago,
                ).count(),
            },
            "recent_publishes": [
                {"title": a.title or f"{a.type} — {a.phase}"} for a in recent_published
            ],
        })

    # ── Repositories (P4.7-T7, backs S-13) ───────────────────────────
    @action(detail=True, methods=["get", "post"])
    def repositories(self, request, pk=None):
        """GET the project's repos + topology (any member) / POST to register one
        (tech_lead/admin; `409` on a duplicate name)."""
        project = self.get_object()
        if request.method == "GET":
            return Response({
                "repo_topology": project.repo_topology,
                "repositories": repositories_for(
                    tenant_id=self.tenant_id, project_id=str(project.id)
                ),
            })

        ser = RepositoryCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        actor = resolve_actor(request, request.data.get("user_id"))
        try:
            require_repo_manage_role(
                tenant_id=self.tenant_id, project_id=str(project.id), user_id=actor
            )
            result = add_repository(
                tenant_id=self.tenant_id, project_id=str(project.id),
                name=ser.validated_data["name"], role=ser.validated_data["role"],
                default_base=ser.validated_data["base_branch"],
                preview_url=ser.validated_data["preview_url"],
            )
        except RepositoryError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        if not result["created"]:
            return Response(
                {"detail": f"{ser.validated_data['name']} is already registered on this "
                           f"project."},
                status=status.HTTP_409_CONFLICT,
            )
        rows = repositories_for(tenant_id=self.tenant_id, project_id=str(project.id))
        created_row = next(r for r in rows if r["id"] == result["repository_id"])
        return Response(created_row, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete", "patch"], url_path=r"repositories/(?P<rid>[^/.]+)")
    def repository_detail(self, request, pk=None, rid=None):
        """DELETE a repository (reconciles topology + default) or PATCH its settings — currently the
        manual preview URL for 09b (tech_lead/admin either way)."""
        project = self.get_object()
        actor = resolve_actor(request, request.data.get("user_id"))
        try:
            require_repo_manage_role(
                tenant_id=self.tenant_id, project_id=str(project.id), user_id=actor
            )
            if request.method == "PATCH":
                ser = RepositoryUpdateSerializer(data=request.data)
                ser.is_valid(raise_exception=True)
                update_repository(
                    tenant_id=self.tenant_id, project_id=str(project.id), repository_id=rid,
                    preview_url=ser.validated_data.get("preview_url"),
                )
                return Response(
                    repositories_for(tenant_id=self.tenant_id, project_id=str(project.id))
                )
            remove_repository(
                tenant_id=self.tenant_id, project_id=str(project.id), repository_id=rid
            )
        except RepositoryError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"],
            url_path=r"repositories/(?P<rid>[^/.]+)/set-default")
    def set_repository_default(self, request, pk=None, rid=None):
        """POST to make this repo the project's default base (tech_lead/admin)."""
        project = self.get_object()
        actor = resolve_actor(request, request.data.get("user_id"))
        try:
            require_repo_manage_role(
                tenant_id=self.tenant_id, project_id=str(project.id), user_id=actor
            )
            set_default_repository(
                tenant_id=self.tenant_id, project_id=str(project.id), repository_id=rid
            )
        except RepositoryError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(
            repositories_for(tenant_id=self.tenant_id, project_id=str(project.id))
        )


# ── Source documents + onboarding review gate ───────────────────────
class SourceDocumentViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = SourceDocumentSerializer
    queryset = SourceDocument.objects.all().order_by("-created_at")

    @action(detail=True, methods=["post"])
    def adopt(self, request, pk=None):
        """Review gate: a product_owner publishes the extracted draft artifacts, classifying the
        document into its lifecycle type (Brownfield B2-1). The acting user is the session user
        when present (Brownfield B2-2), falling back to the `user_id` body for pre-auth/test
        callers; the service still enforces the product_owner/admin gate role on that actor.
        (Hard authentication-gating of this endpoint is tracked separately as X-1, not this batch.)"""
        src = self.get_object()
        ser = AdoptSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        actor = resolve_actor(request, ser.validated_data.get("user_id"))
        if not actor:
            raise ValidationError({"user_id": "an authenticated session or user_id is required"})
        target_type = ser.validated_data.get("target_type") or None
        try:
            out = adopt_source_document(
                tenant_id=self.tenant_id, source_document_id=str(src.id),
                user_id=actor, target_type=target_type,
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


# ── Integrations (admin — P4.7-T6) ──────────────────────────────────
class IntegrationViewSet(
    TenantScopedMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Admin CRUD over the tenant's per-capability connections (S-11 grid, S-12 drawer). One
    connection per (tenant, capability). Secrets are write-only (DECISION-4): accepted on
    create/update, never serialized back — responses expose `configured` only."""

    permission_classes = [IsTenantAdmin]
    serializer_class = IntegrationSerializer
    queryset = IntegrationConnection.objects.all().order_by("capability")

    def create(self, request, *args, **kwargs):
        ser = IntegrationCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        tenant = Tenant.objects.get(id=self.tenant_id)
        try:
            conn = create_integration(tenant=tenant, **ser.validated_data)
        except IntegrationError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(IntegrationSerializer(conn).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        """PATCH — partial: only the fields actually supplied are changed (omitting `secrets`
        leaves the stored credential untouched)."""
        conn = self.get_object()
        ser = IntegrationUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        conn = update_integration(conn=conn, **ser.validated_data)
        return Response(IntegrationSerializer(conn).data)

    @action(detail=True, methods=["post"], url_path="test-connection")
    def test_connection(self, request, pk=None):
        """Probe a SAVED connection live and record the outcome on `health`."""
        conn = self.get_object()
        return Response(test_integration_connection(conn))

    @action(detail=False, methods=["post"], url_path="test-credentials")
    def test_credentials_action(self, request):
        """Test credentials BEFORE saving them (Bugs S.No 156).

        `test-connection` is detail-routed, so it structurally requires a saved row — which is
        why an admin had to commit credentials to the tenant before they could find out the
        token was wrong. This probes an in-memory connection that is never saved."""
        ser = IntegrationTestCredentialsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        tenant = Tenant.objects.get(id=self.tenant_id)
        try:
            return Response(test_credentials(tenant=tenant, **ser.validated_data))
        except IntegrationError as exc:
            return Response({"detail": str(exc)}, status=exc.status)

    @action(detail=False, methods=["get"], url_path="catalog")
    def catalog(self, request):
        """The per-capability vendor + field catalog that drives the S-12 connect form
        (Bugs.xlsx #40). Static wiring metadata — no tenant data — so it's safe for any
        admin; keeps the frontend from hardcoding vendors."""
        from apps.integrations.catalog import catalog_payload

        return Response(catalog_payload())


# ── WorkItems + phase trigger ───────────────────────────────────────
def humanize_gate(gate_type: str | None) -> str:
    """A human gate label from a gate type, e.g. "phase_gate" -> "Phase gate": one lowercase
    "gate", no underscores, never doubled. Mirrors the frontend gateLabel so the board card
    reads the same as the Gates/Dashboard panels (Bugs.xlsx rows 54/56/57/58)."""
    words = [w for w in (gate_type or "").replace("_", " ").split() if w]
    if words and words[-1].lower() == "gate":
        words = words[:-1]
    base = " ".join(w[:1].upper() + w[1:] for w in words)
    return f"{base} gate" if base else "Gate"


class WorkItemViewSet(
    TenantScopedMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = WorkItemSerializer
    queryset = WorkItem.objects.all().order_by("-created_at")

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return WorkItemPatchSerializer
        return WorkItemSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        project = self.request.query_params.get("project")
        state = self.request.query_params.get("state")
        type_ = self.request.query_params.get("type")
        parent = self.request.query_params.get("parent")
        if project:
            qs = qs.filter(project_id=project)
        if state:
            qs = qs.filter(state=state)
        if type_:
            qs = qs.filter(type=type_)
        if parent:
            qs = qs.filter(parent_id=parent)
        return qs

    def perform_create(self, serializer):
        project_id = self.request.data.get("project")
        if not Project.objects.filter(id=project_id, tenant_id=self.tenant_id).exists():
            raise ValidationError({"project": "unknown project for this tenant"})
        # A manually-added test case carries its priority in external_ref (the model has no
        # priority column); the steps live in `description` (rendered into the 09b manifest).
        extra = {}
        priority = self.request.data.get("priority")
        if serializer.validated_data.get("type") == WorkItem.Type.TEST_CASE and priority:
            extra["external_ref"] = {"priority": priority}
        serializer.save(tenant_id=self.tenant_id, project_id=project_id, **extra)

    def perform_update(self, serializer):
        """Hybrid Option C: a work item may only target a repository on its OWN project — reject
        a repo from another project (RLS already blocks another tenant's). Clearing (null) is ok."""
        repo = serializer.validated_data.get("repo")
        if repo is not None and str(repo.project_id) != str(serializer.instance.project_id):
            raise ValidationError({"repo": "repository is not on this work item's project"})
        serializer.save()

    @action(detail=True, methods=["get"], url_path="test-cases")
    def test_cases(self, request, pk=None):
        """The story's child `test_case` work items + each one's automation status (P3-09b) —
        backs the Test cases coverage screen. `tc_id`/`priority` come from `external_ref`."""
        from apps.workitems.test_cases import automation_status_for

        story = self.get_object()
        kids = WorkItem.objects.filter(
            tenant_id=self.tenant_id, parent_id=story.id, type=WorkItem.Type.TEST_CASE
        ).order_by("created_at")
        return Response([
            {
                "id": str(w.id), "key": w.key, "title": w.title, "state": w.state,
                "tc_id": (w.external_ref or {}).get("tc_id", ""),
                "priority": (w.external_ref or {}).get("priority", ""),
                "automation_status": automation_status_for(w),
            }
            for w in kids
        ])

    def _card_fields(self, work_items):
        """P4.8-T1 bucket-B gap B: artifact_count/owner/needs the board + detail cards render,
        computed here rather than on the plain model serializer (they aren't columns). Keyed
        by str(id) throughout — serializer output carries string ids, model FK attributes UUIDs."""
        ids = [w.id for w in work_items]
        counts = {
            str(row["id"]): row["artifact_count"]
            for row in WorkItem.objects.filter(tenant_id=self.tenant_id, id__in=ids)
            .annotate(artifact_count=Count("runs__artifacts", distinct=True))
            .values("id", "artifact_count")
        }
        needs_clarification = {
            str(wid)
            for wid in Clarification.objects.filter(
                tenant_id=self.tenant_id, work_item_id__in=ids, status="pending"
            ).values_list("work_item_id", flat=True)
        }
        needs_gate = {
            str(a.work_item_id): a.gate_type
            for a in Approval.objects.filter(
                tenant_id=self.tenant_id, work_item_id__in=ids, decision="pending"
            )
        }
        # The item's CURRENT lifecycle phase = its latest run's agent phase (Bugs.xlsx
        # rows 49/50: the board/list showed the feature stream as "Phase"). One query,
        # newest run per work item.
        current_phase = {}
        for r in (
            Run.objects.filter(tenant_id=self.tenant_id, work_item_id__in=ids)
            .select_related("agent_spec")
            .order_by("work_item_id", "-created_at")
            .distinct("work_item_id")
        ):
            spec = r.agent_spec
            current_phase[str(r.work_item_id)] = (
                (spec.key or spec.phase_label) if spec else ""
            )
        out = {}
        for w in work_items:
            wid = str(w.id)
            if wid in needs_clarification:
                needs = {"clarification": True, "label": "Needs answer"}
            elif wid in needs_gate:
                needs = {"gate": True, "label": humanize_gate(needs_gate[wid])}
            else:
                needs = None
            out[wid] = {
                "artifact_count": counts.get(wid, 0),
                "owner": w.assignee.name if w.assignee_id else None,
                "needs": needs,
                "current_phase": current_phase.get(wid, ""),
            }
        return out

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset()).select_related("assignee")
        page = self.paginate_queryset(qs)
        work_items = page if page is not None else list(qs)
        card_fields = self._card_fields(work_items)
        data = WorkItemSerializer(work_items, many=True).data
        empty_card = {"artifact_count": 0, "owner": None, "needs": None, "current_phase": ""}
        for row in data:
            row.update(card_fields.get(row["id"], empty_card))
        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        work_item = self.get_object()
        data = WorkItemSerializer(work_item).data
        data.update(self._card_fields([work_item])[str(work_item.id)])
        return Response(data)

    @action(detail=True, methods=["post"])
    def trigger(self, request, pk=None):
        """Start a phase run for this work item (replaces the legacy command). Build phases
        (07_implementation / 09b_test_automation / 11_cicd — the ones that produce a PR) route
        to the BuildWorkflow via `trigger_build`; every other phase runs as an agent-run. This
        keeps a single UI trigger correct for both plan and build phases (routing lives here,
        keyed off the catalog's `rides_build`, so a new build agent needs no UI change)."""
        work_item = self.get_object()
        ser = TriggerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        agent_key = ser.validated_data["agent_key"]
        try:
            # Actor = the session user when present (routes the phase to *their* companion
            # enrollment), else the pre-auth/runner `user_id` body param (T5).
            triggered_by = resolve_actor(request, ser.validated_data.get("user_id"))
            if catalog_rides_build(agent_key):
                result = trigger_build(
                    tenant_id=self.tenant_id,
                    project_id=str(work_item.project_id),
                    work_item_id=str(work_item.id),
                    agent_key=agent_key,
                    required_role=ser.validated_data["required_role"]
                    or gate_role_for(agent_key),
                    triggered_by=triggered_by,
                )
            else:
                result = trigger_phase(
                    tenant_id=self.tenant_id,
                    project_id=str(work_item.project_id),
                    work_item_id=str(work_item.id),
                    agent_key=agent_key,
                    gate_type=ser.validated_data["gate_type"],
                    required_role=ser.validated_data["required_role"],
                    triggered_by=triggered_by,
                )
        except ActiveRunError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except TriggerError as exc:
            raise ValidationError({"agent_key": str(exc)}) from exc
        return Response(
            {"run_id": result.run_id, "workflow_id": result.workflow_id},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def build(self, request, pk=None):
        """Start the implementation BuildWorkflow saga for this work item (G1 — the REST
        surface for `trigger_build`). The build claims onto the triggering user's enrolled
        companion; `repo`/`base` default to the work item's Repository."""
        work_item = self.get_object()
        ser = BuildTriggerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            triggered_by = resolve_actor(request, ser.validated_data.get("user_id"))
            result = trigger_build(
                tenant_id=self.tenant_id,
                project_id=str(work_item.project_id),
                work_item_id=str(work_item.id),
                agent_key=ser.validated_data["agent_key"],
                repo=ser.validated_data.get("repo"),
                base=ser.validated_data.get("base"),
                required_role=ser.validated_data["required_role"],
                triggered_by=triggered_by,
            )
        except ActiveRunError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except TriggerError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
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

    @action(detail=True, methods=["get"])
    def lifecycle(self, request, pk=None):
        """S-17 lifecycle rail: per-phase state derived from runs + pending gates/clarifications.
        Tier is determined by work-item type; nodes come from the tenant's AgentSpec registry."""
        work_item = self.get_object()

        # Tier mapping by work-item type
        tier_map = {"epic": "plan", "story": "plan", "task": "build", "defect": "remediation"}
        tier = tier_map.get(work_item.type, "plan")

        # All runs for this work-item indexed by agent_spec key
        runs_by_key: dict[str, Run] = {}
        for run in (
            Run.objects.filter(tenant_id=self.tenant_id, work_item=work_item)
            .select_related("agent_spec")
            .order_by("-created_at")
        ):
            if run.agent_spec_id and run.agent_spec.key not in runs_by_key:
                runs_by_key[run.agent_spec.key] = run

        # Pending clarification and gate keys
        clarification_run_ids = set(
            Clarification.objects.filter(
                tenant_id=self.tenant_id, work_item=work_item, status="pending"
            ).values_list("run_id", flat=True)
        )
        gate_run_ids = set(
            Approval.objects.filter(
                tenant_id=self.tenant_id, work_item=work_item, decision="pending"
            ).values_list("run_id", flat=True)
        )

        # Build nodes from the registered AgentSpecs for this tenant
        specs = list(
            AgentSpec.objects.filter(tenant_id=self.tenant_id).order_by("key")
        )
        # Fallback: full ACTIVE_AGENT_CATALOG when no specs are seeded yet
        if not specs:
            specs_data = [
                {"key": d.key, "label": d.phase_label}
                for d in _ACTIVE_CATALOG
            ]
        else:
            specs_data = [{"key": s.key, "label": s.phase_label or s.key} for s in specs]

        run_status_to_node_state = {
            "running": "running",
            "awaiting_gate": "awaiting_gate",
            "approved": "done",
            "completed": "done",
            "rejected": "failed",
            "failed": "failed",
        }
        nodes = []
        for spec in specs_data:
            key = spec["key"]
            run = runs_by_key.get(key)
            if run is None:
                node_state = "not_started"
                run_id = None
            elif run.id in clarification_run_ids:
                node_state = "needs_answer"
                run_id = str(run.id)
            elif run.id in gate_run_ids:
                node_state = "awaiting_gate"
                run_id = str(run.id)
            else:
                node_state = run_status_to_node_state.get(run.status, "running")
                run_id = str(run.id)
            nodes.append({
                "phase": key,
                "label": spec["label"],
                "state": node_state,
                "run_id": run_id,
                "triggerable": node_state in ("not_started", "failed"),
            })

        # Children work-items
        children = [
            {"id": str(c.id), "title": c.title, "type": c.type, "phase": c.feature_stream}
            for c in work_item.children.all()[:20]
        ]
        # Parent
        parent = None
        if work_item.parent_id:
            p = work_item.parent
            parent = {"id": str(p.id), "title": p.title}

        return Response({
            "tier": tier,
            "nodes": nodes,
            "loops": [],
            "children": children,
            "parent": parent,
        })


# ── Runs (read-only + transcript/takeover) ─────────────────────────
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

    @action(detail=True, methods=["get"])
    def transcript(self, request, pk=None):
        """S-33 run transcript: read-only replay of the agent conversation stored in
        run.outputs. Returns an empty turns list when no transcript has been recorded yet."""
        run = self.get_object()
        # Prefetch agent_spec for key access (avoids extra query after get_object)
        if run.agent_spec_id:
            run.agent_spec  # noqa: B018 — triggers deferred FK load
        outputs = run.outputs or {}
        # Agent SDK stores the conversation under outputs["report"]["transcript"]
        # or directly under outputs["transcript"] — check both.
        report = outputs.get("report") or {}
        raw_turns = (
            report.get("transcript")
            or outputs.get("transcript")
            or []
        )
        turns = [
            {
                "role": t.get("role", "agent"),
                "body": t.get("content") or t.get("body") or "",
                "meta": t.get("meta"),
            }
            for t in raw_turns
            if isinstance(t, dict)
        ]
        return Response({
            "run_id": str(run.id),
            "phase": run.agent_spec.key if run.agent_spec_id else "",
            "engine": run.engine,
            "cost": str(run.cost_usd) if run.cost_usd is not None else None,
            "turns": turns,
        })

    @action(detail=True, methods=["post"], url_path="take-over")
    def take_over(self, request, pk=None):
        """S-32 offline takeover via run ID: delegates to the work-item's takeover service
        (the run is the entry point the UI knows; the work-item owns the flag).

        If this run is a report-timeout-parked (STALLED) run, an explicit human takeover —
        whether "Take over manually" or "Reconnect & re-run" (release) — also ends the old
        still-waiting AgentRunWorkflow terminally (Bugs S.No 89), so it does not linger after
        the operator has decided to hand-work the item or re-run from a clean dispatch."""
        run = self.get_object()
        try:
            if request.data.get("release"):
                out = release_takeover(
                    tenant_id=self.tenant_id,
                    work_item_id=str(run.work_item_id),
                    actor=request.data.get("actor", "developer"),
                )
            else:
                out = request_takeover(
                    tenant_id=self.tenant_id,
                    work_item_id=str(run.work_item_id),
                    actor=request.data.get("actor", "developer"),
                    reason=request.data.get("reason", ""),
                )
            abandon_stalled_run(tenant_id=self.tenant_id, run_id=str(run.id))
        except TakeoverError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(out)

    @action(detail=True, methods=["post"], url_path="resume")
    def resume(self, request, pk=None):
        """Resume a run parked at an error, from the step that failed (Bugs S.No 157).

        The counterpart to "Take over": takeover ends a parked run terminally, resume continues
        it. Everything already done (the build, the branch, the PR) is kept — only the failed
        step is retried, so the user never re-runs a whole phase because of one error."""
        run = self.get_object()
        try:
            out = resume_stalled_run(tenant_id=self.tenant_id, run_id=str(run.id))
        except ResumeError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(out)


# ── Artifacts (read-only — pointers/provenance) ─────────────────────
class _ExportImpossible(Exception):
    """A manual export can't reach its SoR (no connector / no body). The publish action
    maps this to the B3 internal fallback for a first publish, or an honest 400 on
    re-export."""


class ArtifactViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ArtifactSerializer
    queryset = Artifact.objects.all().order_by("-created_at")

    def get_permissions(self):
        # Preview (P4.7-T10) reads a body read-through — any authenticated member.
        # List/retrieve keep the existing pointer-only default.
        if self.action == "preview":
            return [IsAuthenticatedMember()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        for field in ("project", "phase", "status"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{("project_id" if field == "project" else field): value})
        return qs

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        """S-29: read-through body (S3 draft/snapshot or SoR), never an editor, never
        copied into the registry (#1/#3). `404` when there's truly no body to show."""
        artifact = self.get_object()
        result = read_artifact_preview(tenant_id=self.tenant_id, artifact_id=str(artifact.id))
        if result is None:
            raise NotFound("artifact has no body to preview")
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """S-34 manual gate-respecting publish (DECISION-8): push a gate-approved artifact
        to a SoR through its capability — a REAL export, not a status flip. Export is
        always user-triggered (team flow decision 2026-07-07) and governed by the
        project's phase-scoped export policy: docstore transfers the SoR (page holds the
        body); tasktracker/testmgmt are projections (issues/tests derived from the body;
        the artifact stays internal SoR with the export recorded in external_ref).
        Never bypasses a gate (#5): drafts/pending stay rejected. Published-internal
        artifacts may be re-exported once a connector exists — their gate already passed."""
        from integrations.export_policy import export_target_for
        from integrations.preview import read_artifact_preview

        artifact = self.get_object()
        # APPROVED = first publish; PUBLISHED = re-export (its gate already passed —
        # docstore re-exports update the same page idempotently, projections re-run
        # register-don't-recreate). Drafts/pending/staged/rejected never export (#5).
        exportable = artifact.status in (
            Artifact.Status.APPROVED, Artifact.Status.PUBLISHED,
        )
        if not exportable:
            raise ValidationError(
                "Artifact must be gate-approved before publishing. "
                f"Current status: {artifact.status}"
            )
        target_capability = request.data.get("target_capability", "internal")
        destination = request.data.get("destination", "")
        # Legacy/vendor spelling: "confluence" is the docstore capability (#9 — the API
        # speaks capabilities; the vendor is whatever connector is bound).
        if target_capability == "confluence":
            target_capability = "docstore"

        if target_capability == "internal":
            artifact.status = Artifact.Status.PUBLISHED
            artifact.save(update_fields=["status", "updated_at"])
            return Response({"status": "published", "sor_link": None})

        # Phase-scoped export policy (defaults + ProjectProfile overrides).
        profile = getattr(artifact.project, "profile", None)
        allowed = export_target_for(profile, artifact.phase)
        if target_capability != allowed:
            raise ValidationError(
                f"Export policy for phase '{artifact.phase}' allows "
                + (f"only '{allowed}'" if allowed else "internal publishing only")
                + f"; requested '{target_capability}'. Adjust the project profile's "
                "export policy to change this."
            )

        # Body via the same read-through the preview uses (own S3 draft → inline draft →
        # the run's staged/reported body) — never stored back on the row (#1/#3).
        preview = read_artifact_preview(
            tenant_id=self.tenant_id, artifact_id=str(artifact.id))
        body_md = (preview or {}).get("body") or ""

        try:
            if target_capability == "docstore":
                return self._publish_docstore(artifact, body_md, destination)
            if target_capability == "tasktracker":
                return self._publish_tasktracker(artifact, destination)
            if target_capability == "testmgmt":
                return self._publish_testmgmt(artifact, body_md, destination)
        except _ExportImpossible as exc:
            if artifact.status == Artifact.Status.APPROVED:
                # First publish that can't reach a SoR → internal fallback (blueprint B3):
                # the publish is still recorded, sor stays internal (provenance never
                # claims a push that didn't happen).
                artifact.status = Artifact.Status.PUBLISHED
                artifact.save(update_fields=["status", "updated_at"])
                return Response({"status": "published", "sor_link": None})
            # Re-export of an already-published-internal artifact: succeeding without an
            # actual push would be a no-op lie — fail honestly with guidance.
            raise ValidationError(str(exc)) from exc
        raise ValidationError(f"Unknown export capability '{target_capability}'.")

    def _publish_docstore(self, artifact, body_md, destination):
        """Docstore transfers the SoR: the page holds the full body → sor + external_ref
        point at it. Idempotent — an existing page updates in place (base_version)."""
        from integrations.publish import publish_to_docstore
        from integrations.types import CapabilityUnavailable

        if not body_md:
            raise _ExportImpossible("Artifact has no body to export.")
        work_item = artifact.run.work_item if artifact.run_id else None
        title_base = (
            (work_item.feature_stream if work_item else "")
            or artifact.project.name
        )
        # Humanized phase in the page title — no raw "03_prd" ordinals (Bugs.xlsx rows
        # 54-58 established the no-raw-keys rule for user-facing text).
        from integrations.export_policy import normalize_phase

        phase_label = normalize_phase(artifact.phase).replace("_", " ").title() or "Artifact"
        # Prefer the artifact's own human-readable title (Bugs S.No 120); fall back to the
        # feature-stream/project + humanized phase for artifacts registered without one.
        title = artifact.title or f"{title_base} — {phase_label}"
        try:
            ref = publish_to_docstore(
                tenant_id=self.tenant_id, artifact=artifact, body_md=body_md,
                title=title, space=destination or None,
            )
        except CapabilityUnavailable as exc:
            raise _ExportImpossible(
                "No documentation-store connector is configured for this workspace. "
                "Connect one on the Integrations page first."
            ) from exc
        artifact.status = Artifact.Status.PUBLISHED
        artifact.sor = ref.sor
        artifact.external_ref = {
            "sor": ref.sor, "id": ref.id, "url": ref.url, "version": ref.version,
        }
        artifact.save(update_fields=["status", "sor", "external_ref", "updated_at"])
        return Response({"status": "published", "sor_link": ref.url})

    def _publish_tasktracker(self, artifact, destination):
        """Task-breakdown export = reconcile the project's proposed backlog into the
        tracker (register-don't-recreate — the artifact's stories ARE the project's
        proposed WorkItems). A projection: the artifact stays internal SoR; the export is
        merged into external_ref (never overwriting the inline draft body)."""
        from integrations.reconcile import reconcile_backlog
        from integrations.types import CapabilityUnavailable

        try:
            result = reconcile_backlog(
                tenant_id=self.tenant_id, project_id=str(artifact.project_id),
                project_key=(destination or None),
            )
        except CapabilityUnavailable as exc:
            raise _ExportImpossible(
                "No task-tracker connector is configured for this workspace. "
                "Connect one on the Integrations page first."
            ) from exc
        items = [
            {"work_item_id": r["work_item_id"],
             "key": (r["external_ref"] or {}).get("id", ""),
             "url": (r["external_ref"] or {}).get("url", "")}
            for r in result["items"]
        ]
        failed = result.get("failed", [])
        artifact.status = Artifact.Status.PUBLISHED
        artifact.external_ref = {
            **(artifact.external_ref or {}),
            "export": {"sor": "jira", "reconciled": result["reconciled"],
                       "created": result["created"], "failed": len(failed)},
        }
        artifact.save(update_fields=["status", "external_ref", "updated_at"])
        return Response({
            # A partial push is not a clean success — say so honestly (Bugs S.No 143) so the UI can
            # warn instead of showing an all-green "Published" while items silently didn't land.
            "status": "partial" if failed else "published",
            "sor_link": next((i["url"] for i in items if i["url"]), None),
            "reconciled": result["reconciled"], "created": result["created"],
            "failed": failed,
            "items": items,
        })

    def _publish_testmgmt(self, artifact, body_md, destination):
        """Test-case export → testmgmt.create_test (idempotent by summary). A projection:
        the artifact stays internal SoR; the created test is merged into external_ref."""
        from integrations.export_tests import parse_test_case
        from integrations.registry import get_capability, get_connection
        from integrations.types import CapabilityUnavailable

        if artifact.type != "test_case":
            raise ValidationError(
                "Only test_case artifacts export to the test-management system; "
                "test plans and reports stay internal."
            )
        if not body_md and not (artifact.external_ref or {}).get("steps"):
            raise _ExportImpossible("Artifact has no body to export.")
        try:
            tm = get_capability(self.tenant_id, "testmgmt")
        except CapabilityUnavailable as exc:
            raise _ExportImpossible(
                "No test-management connector is configured for this workspace. "
                "Connect one on the Integrations page first."
            ) from exc
        conn = get_connection(self.tenant_id, "testmgmt")
        project_key = destination or ((conn.scopes or {}).get("project_key") if conn else None)
        summary, steps = parse_test_case(artifact, body_md)
        ref = tm.create_test(project=project_key, summary=summary, steps=steps)
        artifact.status = Artifact.Status.PUBLISHED
        artifact.external_ref = {
            **(artifact.external_ref or {}),
            "export": {"sor": ref.sor, "id": ref.id, "url": ref.url},
        }
        artifact.save(update_fields=["status", "external_ref", "updated_at"])
        return Response({"status": "published", "sor_link": ref.url, "test_key": ref.id})


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

    @action(detail=True, methods=["get"])
    def criteria(self, request, pk=None):
        """S-22 generalized criteria-gate checklist (DECISION-6): exposes the approval's
        conditions JSONField as typed GateCriterion objects with computed approve_enabled."""
        approval = self.get_object()
        raw = approval.conditions or []
        criteria_list = [
            {
                "id": c.get("key", str(i)),
                "text": c.get("label", f"Criterion {i + 1}"),
                "required": bool(c.get("required", True)),
                "satisfied": bool(c.get("satisfied", False)),
                "note": c.get("note"),
            }
            for i, c in enumerate(raw)
        ]
        met = sum(1 for c in criteria_list if c["satisfied"])
        required_unmet = any(c for c in criteria_list if c["required"] and not c["satisfied"])
        return Response({
            "criteria": criteria_list,
            "met": met,
            "total": len(criteria_list),
            "approve_enabled": approval.decision == "pending" and not required_unmet,
        })

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


# ── Drift (P4.7-T9, backs S-27) — the Approval-analog for run-less changes ──
class DriftRecordViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Read + decide a drift record. Role check (the record's `required_role` — architect for
    contract, tech_lead for pointer/hash — or idempotent once already decided) lives in
    `decide_drift`, not here."""

    serializer_class = DriftRecordSerializer
    queryset = DriftRecord.objects.all().order_by("-created_at")

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        """Decide a drift gate (spec §6/D6): role check → record → reconcile-or-flag."""
        rec = self.get_object()
        ser = DriftDecisionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user_id = resolve_actor(request, ser.validated_data.get("user_id"))
        if user_id is None:
            raise ValidationError({"user_id": "required when not authenticated"})
        try:
            result = decide_drift(
                tenant_id=self.tenant_id, drift_id=str(rec.id), user_id=user_id,
                decision=ser.validated_data["decision"], comment=ser.validated_data["comment"],
            )
        except DriftRoleError as exc:
            raise PermissionDenied(str(exc)) from exc
        except DriftError as exc:
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


# ── Phase catalog (S-18 trigger picker, gap C) ──────────────────────
from apps.registry.catalog import ACTIVE_AGENT_CATALOG as _ACTIVE_CATALOG
from apps.registry.catalog import get_by_key as _catalog_get

# Tier bucket membership — derived from ACTIVE_AGENT_CATALOG so it never drifts.
# Plan  : onboarding/context phases (00_*) + strategy phases (01_–04_).
# Build : implementation, quality, ops phases (05_–12_).
# Remediation: reserved (none in current catalog — defect/hotfix phases added later).
_PLAN_KEYS = frozenset(
    d.key for d in _ACTIVE_CATALOG
    if d.key[:2] in ("00", "01", "02", "03", "04")
)
_BUILD_KEYS = frozenset(
    d.key for d in _ACTIVE_CATALOG
    if d.key[:2] in ("05", "06", "07", "08", "09", "10", "11", "12")
)


def _catalog_entry(key: str, label: str, gate_role: str) -> dict:
    return {"key": key, "label": label, "agent_key": key, "gate_role": gate_role}


def _full_catalog_from_db(tenant_id: str) -> tuple[list, list, list]:
    """Return (plan, build, remediation) lists built from the tenant's AgentSpec rows."""
    plan: list[dict] = []
    build: list[dict] = []
    remediation: list[dict] = []
    specs = list(AgentSpec.objects.filter(tenant_id=tenant_id).order_by("key"))
    for s in specs:
        defn = _catalog_get(s.key)
        gate_role = defn.gate_role if defn else "product_owner"
        entry = _catalog_entry(s.key, s.phase_label or s.key, gate_role)
        if s.key in _PLAN_KEYS:
            plan.append(entry)
        elif s.key in _BUILD_KEYS:
            build.append(entry)
        else:
            remediation.append(entry)
    return plan, build, remediation


def _full_catalog_from_code() -> tuple[list, list, list]:
    """Fallback: build catalog from ACTIVE_AGENT_CATALOG when DB has no AgentSpecs yet."""
    plan: list[dict] = []
    build: list[dict] = []
    for d in _ACTIVE_CATALOG:
        entry = _catalog_entry(d.key, d.phase_label, d.gate_role)
        if d.key in _PLAN_KEYS:
            plan.append(entry)
        elif d.key in _BUILD_KEYS:
            build.append(entry)
    return plan, build, []


class PhaseCatalogView(APIView):
    """GET /api/phases/ — tenant-scoped phase catalog (bucket B, gap C).

    Returns plan / build / remediation buckets ordered by agent key. Each entry carries:
    - ``agent_key``  – the value to send in the trigger POST body
    - ``gate_role``  – the Membership role that must approve the phase gate

    Source of truth is the tenant's AgentSpec rows (seeded by ``seed_agent_specs`` on
    tenant creation). Falls back to the in-code ACTIVE_AGENT_CATALOG if the DB is empty
    (e.g. test environments that skip the seed step).

    Greenfield and brownfield share the same catalog: the 00_* onboarding agents are in
    the plan bucket so brownfield projects can trigger them before ideation."""

    permission_classes = []  # Allow-any; tenant resolved from session or X-Tenant-ID

    def get(self, request):
        tenant_id = getattr(request, "tenant_id", None)

        if tenant_id:
            plan, build, remediation = _full_catalog_from_db(tenant_id)
            if not plan and not build and not remediation:
                plan, build, remediation = _full_catalog_from_code()
        else:
            plan, build, remediation = _full_catalog_from_code()

        return Response({"plan": plan, "build": build, "remediation": remediation})
