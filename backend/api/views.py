"""Phase-0 REST views.

Every resource except tenant-create is tenant-scoped: the tenant is resolved by
`TenantContextMiddleware` (which sets the RLS GUC and stashes `request.tenant_id`),
and each queryset *also* filters on `tenant_id` explicitly — defense-in-depth, and
the actual enforcement under the local superuser connection where RLS is bypassed.
Custom actions delegate to the domain services (`trigger_phase`, `decide_gate`).
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q, TextField
from django.db.models.functions import Cast
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ParseError, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from api.files import artifact_filename, attachment_response, inline_response
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
from apps.registry.catalog import ACTIVE_AGENT_CATALOG as _ACTIVE_CATALOG
from apps.registry.catalog import (
    BUILD_PHASE_KEYS,
    PHASE_KEYS_BY_TIER,
    PLAN_PHASE_KEYS,
    gate_role_for,
)
from apps.registry.catalog import get_by_key as _catalog_get
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
    require_project_member,
    require_project_write_role,
    resend_invitation,
    revoke_invitation,
    revoke_membership,
    set_tenant_admin,
)
from apps.workitems.cancel import transition as cancel_work_item
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
from integrations.preview import artifact_is_downloadable, read_artifact_preview
from integrations.types import CapabilityUnavailable
from orchestration.takeover import (
    PauseError,
    ResumeError,
    TakeoverError,
    abandon_stalled_run,
    pause_run,
    release_takeover,
    request_takeover,
    resume_stalled_run,
)
from orchestration.trigger import (
    ActiveRunError,
    NoCompanionError,
    TriggerError,
    companion_liveness_for,
    trigger_build,
    trigger_code_intel,
    trigger_onboarding_agent,
    trigger_phase,
)

from .pagination import OptInPageNumberPagination
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
    WorkItemTransitionSerializer,
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

    def get_object(self):
        """Screen Words group 5: DRF's own 404 text is written for whoever wrote the query.

        A deleted run, or a link pasted from another project, answered
        `No Run matches the given query.` — which names the Python model, says "query" to someone
        who typed no query, and gives them nothing to do next. One override here rather than a
        message per viewset, so every scoped resource says it the same way.

        Deliberately does NOT say "or you don't have access to it". That wording was tried and
        read as a permissions problem, sending people to ask an admin for access to something
        that simply no longer exists.
        """
        from django.http import Http404

        try:
            return super().get_object()
        except Http404 as exc:
            try:
                noun = str(self.get_queryset().model._meta.verbose_name)
            except Exception:  # noqa: BLE001 — never let the message-builder become the failure
                noun = "item"
            raise NotFound(
                f"That {noun} no longer exists. It may have been deleted, or the link may "
                "point at a different project."
            ) from exc


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


def _a11y_would_ticket(tenant_id, project_id, finding) -> bool:
    """Will confirming this finding actually raise a defect? (QA-23.)

    Asked rather than assumed, because a project may block on `critical` only — or on nothing
    at all, which `policy` has supported since QA-08. Telling a reviewer "a defect has been
    opened" when their project's bar means no ticket will ever exist would be the console
    lying about its own consequence, which is the one thing it cannot do and remain useful.
    """
    from apps.a11y.policy import blocks, policy_or_default

    if finding.outcome != "failure":
        return False
    policy, _ = policy_or_default(tenant_id, project_id)
    return blocks(policy, severity=finding.severity, confidence=finding.confidence,
                  source=finding.source)


# ── Projects + Profile ──────────────────────────────────────────────
#: Said the same way by all four page/audit endpoints, because a refusal worded three times is
#: a refusal that will differ.
PAGE_ROLE_DETAIL = (
    "You need the QA Lead, Tech Lead or Admin role on this project to change which pages are "
    "audited or to start an audit. Everything on this screen is readable by anyone on the "
    "project."
)


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
        # Bugs S.No 214 — the WRITE surfaces that were still falling through to the viewset
        # default, which is `AllowAny`: no session required at all. Tenant scoping and RLS still
        # applied, so this was never cross-tenant exposure; it was that INSIDE a tenant nothing
        # checked who you were. `create` is the sharpest of them — `perform_create` below already
        # says in prose "any authenticated tenant member may create a project (see get_permissions
        # above)", and that sentence was simply not true.
        #
        # `profile` is gated a second time, per project and per role, inside the action: it is
        # the briefing every agent on the project reads, so it is the most load-bearing text in
        # the platform and a plain member should not be able to rewrite it. The rest need only a
        # session — uploading a source document and reading the lineage graph are ordinary member
        # work, and raising their bar would break the ordinary journey.
        if self.action in {"create", "profile", "export_policy", "source_documents",
                           "traceability", "onboard_atlassian"}:
            return [IsAuthenticatedMember()]
        # Dashboard rollup (S-31): authenticated member.
        if self.action == "dashboard":
            return [IsAuthenticatedMember()]
        # Accessibility review console (QA-23): any authenticated member may READ the queue and
        # the captures — a developer wanting to see what a reviewer is looking at is exactly the
        # transparency this build is for. Only the accessibility reviewer may ANSWER, and that
        # is enforced per-project inside `review.adjudicate`, not here, because the role is a
        # project Membership and this class-level hook has no project in hand.
        if self.action in {"a11y_review", "a11y_review_item", "a11y_review_screenshot",
                           # Reading one finding (S-39) — the same read as the console's, minus
                           # the claim, so it is gated exactly the same way.
                           "a11y_finding",
                           "a11y_conformance", "a11y_conformance_sign",
                           "a11y_conformance_export", "a11y_journeys",
                           # The page list, the page editor and audits were missing from this
                           # set, so they fell through to the viewset default — `AllowAny`,
                           # which does not even require a session. Note what this class does
                           # and does not do: it gates "is somebody logged in", and tenant
                           # scoping + RLS do the rest; it is NOT a per-project membership
                           # check despite the name, and every other project surface uses it
                           # the same way. WRITING is gated properly, per project and per role,
                           # inside the action itself (`review.can_manage_pages`) — the same
                           # shape `repositories` uses.
                           #
                           # `a11y_policy` and `a11y_backlog` are deliberately NOT here. They
                           # are pure reads that leak nothing past the tenant, and their tests
                           # exercise tenant isolation through the header path with no session
                           # — which is a property worth keeping testable. Tightening them was
                           # not part of what the scope fix was asked to do.
                           "a11y_routes", "a11y_route_item", "a11y_audits",
                           # Re-judging spends a real engine run, so it is gated here as well as
                           # by role inside the action — the same pair of checks as starting an
                           # audit, which it is a second half of.
                           "a11y_audit_rejudge"}:
            return [IsAuthenticatedMember()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        """Refuse a duplicate project name with 409 (Bugs S.No 211).

        The Create Project screen has always had the collision state built — it branches on 409
        and says *"A project named X already exists in this workspace."* The backend simply never
        returned one, so the state was unreachable and two projects could sit in the switcher
        under the same name with no way to tell them apart. Checked here rather than left to the
        database constraint so the client gets 409 with a sentence, not a 500 from an
        IntegrityError. The constraint stays as the real guarantee against a race.
        """
        name = (request.data.get("name") or "").strip()
        if name and Project.objects.filter(tenant_id=self.tenant_id, name__iexact=name).exists():
            return Response(  # noqa: CLIENT-TEXT — repeats the name the person just typed
                {"detail": f'A project named "{name}" already exists in this workspace.'},
                status=status.HTTP_409_CONFLICT,
            )
        return super().create(request, *args, **kwargs)

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
        # Layer 2 of S.No 214: reading the briefing is ordinary member work; REWRITING it steers
        # every agent that runs on this project from here on, so it takes the same role as
        # managing repositories.
        require_project_write_role(
            tenant_id=self.tenant_id, project_id=str(project.id),
            user_id=getattr(current_user(request), "id", None),
            what="edit the project profile",
        )
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

    @action(detail=True, methods=["get"], url_path="a11y-policy")
    def a11y_policy(self, request, pk=None):
        """The project's accessibility policy (QA-08): what it aims at, and what blocks.

        Read-only, and shaped like `export-policy` on purpose — defaults, the project's own
        overrides, and the effective result, so a reader never has to merge two dicts in their
        head. Writes go through `PUT …/profile/`, which validates the block.

        `error` is non-empty only when the stored block cannot be honoured (which the profile
        endpoint refuses to create): the effective policy is then the documented default, and
        saying so beats showing a policy that is not the one in force.
        """
        from apps.a11y.policy import (
            DEFAULT_TARGET,
            default_policy,
            describe_policy,
            policy_or_default,
        )

        project = self.get_object()
        profile = getattr(project, "profile", None)
        policy, error = policy_or_default(self.tenant_id, str(project.id))
        return Response({
            "defaults": default_policy(DEFAULT_TARGET),
            "overrides": (profile.a11y if profile else {}) or {},
            "effective": policy,
            "summary": describe_policy(policy),
            "error": error,
        })

    @action(detail=True, methods=["get", "put"], url_path="a11y-routes")
    def a11y_routes(self, request, pk=None):
        """The pages a baseline accessibility audit should visit (QA-17).

        `GET` lists them, disabled ones included — a route that stopped being audited is a fact
        about the application, and hiding it would make the list look like the whole story.
        `PUT` registers a list; pass `replace: true` to make it the definitive one, which
        **disables** anything not named rather than deleting it (see `routes.register_routes`).

        Onboarding (OP-06) will write the same table with `source: onboarding`. Everything here
        is `manual`, because a person is the one typing it.
        """
        from apps.a11y.journey import suggested_address
        from apps.a11y.review import can_manage_pages
        from apps.a11y.routes import (
            RouteError,
            describe_routes,
            history_for,
            last_visited,
            parse_routes_text,
            preview_registration,
            register_routes,
            scope_change_since,
        )

        project = self.get_object()
        user_id = getattr(request.user, "id", None)
        # Checked HERE rather than inside `register_routes`, matching `repositories`: the same
        # function is what onboarding (OP-06) will use to write a discovered list with no acting
        # user at all, and a mandatory check inside it would have no honest answer for that.
        may_manage = can_manage_pages(tenant_id=self.tenant_id, project_id=str(project.id),
                                      user_id=user_id)
        result = None
        if request.method == "PUT":
            if not may_manage:
                return Response({"detail": PAGE_ROLE_DETAIL}, status=status.HTTP_403_FORBIDDEN)
            # `routes_text` is what the screen sends: the box's contents, read by the platform
            # so one refusal is worded once and reads the same however the list arrived.
            # `routes` stays for a caller that already has a list.
            given = (request.data.get("routes_text")
                     if request.data.get("routes_text") is not None
                     else request.data.get("routes", []))
            try:
                parsed = parse_routes_text(given)
                if request.query_params.get("preview") or request.data.get("preview"):
                    # Nothing is written. What WOULD happen is what a person confirms against
                    # — see `preview_registration` for why that step exists at all.
                    return Response({"preview": preview_registration(
                        tenant_id=self.tenant_id, project_id=str(project.id), routes=parsed)})
                result = register_routes(
                    tenant_id=self.tenant_id, project_id=str(project.id), routes=parsed,
                    replace=bool(request.data.get("replace")),
                    actor=getattr(request.user, "id", None),
                )
            except RouteError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        from apps.a11y.models import A11yRoute

        rows = list(A11yRoute.objects.filter(tenant_id=self.tenant_id, project_id=project.id))
        visited = last_visited(self.tenant_id, str(project.id))
        # What each page has accumulated. On the row rather than fetched when someone starts
        # editing, because the warning it powers — "renaming leaves this page's problems at the
        # old address" — has to be there the moment the path field is touched.
        history = history_for(self.tenant_id, str(project.id))
        address = suggested_address(self.tenant_id, str(project.id))
        payload = {
            "routes": [
                {"id": str(row.id), "path": row.path, "label": row.label,
                 "source": row.source, "enabled": row.enabled, "notes": row.notes,
                 "example_path": row.example_path,
                 # None means never opened, which is a fact about the page and not a gap in
                 # the screen — a pattern route with no example never can be.
                 "last_visited": visited.get(row.path),
                 "open_findings": (history.get(row.path) or {}).get("open_findings", 0),
                 "visits": (history.get(row.path) or {}).get("visits", 0)}
                for row in rows
            ],
            "summary": describe_routes(self.tenant_id, str(project.id)),
            # Empty when there is nothing to say, so the screen can hide the whole warning
            # behind one check rather than deciding for itself what counts as a change.
            "scope_change": scope_change_since(self.tenant_id, str(project.id)),
            # So the screen renders read-only rather than showing controls that 403 on click —
            # the ninth state S-36 established and the one this tab did not have.
            "can_manage": may_manage,
            # Where this application answers, so the run strip can SHOW the address it would use
            # instead of describing where the address comes from. `suggested_address` is the same
            # resolver the keyboard-journeys panel on this screen already reads, deliberately:
            # one answer to "where is this application", never two panels that can disagree.
            "base_url": address.url,
            "base_url_source": address.source,
            "base_url_reason": address.reason,
        }
        if result is not None:
            payload["changed"] = result
        return Response(payload)

    @action(detail=True, methods=["patch", "delete"],
            url_path=r"a11y-routes/(?P<route_id>[^/]+)")
    def a11y_route_item(self, request, pk=None, route_id=None):
        """Edit or remove ONE registered page (task 8b).

        `PUT …/a11y-routes/` registers by path, because a pasted list carries no identities —
        which is exactly why correcting a path there adds a page and leaves the old one in scope.
        Here the row is named, so an edit is an edit. The ghost page is absent rather than warned
        about.

        `DELETE` removes a page that was never real — never opened, nothing recorded — and takes
        any other page out of scope instead, keeping it visible. A page that stopped existing is
        a fact about the application; a path typed by mistake never was one.

        What neither can do is move a page's history. A finding is keyed on the route it was found
        at, so a rename leaves the problems at the old address and starts the new one empty. The
        row carries `open_findings` and `visits` so the screen can say that before it happens.
        """
        from apps.a11y.review import can_manage_pages
        from apps.a11y.routes import RouteError, delete_route, update_route

        project = self.get_object()
        if not can_manage_pages(tenant_id=self.tenant_id, project_id=str(project.id),
                                user_id=getattr(request.user, "id", None)):
            return Response({"detail": PAGE_ROLE_DETAIL}, status=status.HTTP_403_FORBIDDEN)
        try:
            if request.method == "DELETE":
                out = delete_route(
                    tenant_id=self.tenant_id, project_id=str(project.id), route_id=route_id,
                    actor=getattr(request.user, "id", None))
            else:
                out = {"changed": update_route(
                    tenant_id=self.tenant_id, project_id=str(project.id), route_id=route_id,
                    fields={k: v for k, v in (request.data or {}).items()},
                    actor=getattr(request.user, "id", None))}
        except RouteError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out)

    @action(detail=True, methods=["get", "post"], url_path="a11y-audits")
    def a11y_audits(self, request, pk=None):
        """Baseline audits of this project (QA-17). `POST` opens one and returns its manifest.

        Opening an audit does not visit anything — it cannot. The manifest is handed to whoever
        can reach the running application, which is never this server (R2). The audit stays
        `capturing` until that machine posts what it saw and closes it.
        """
        from django.utils import timezone

        from apps.a11y.baseline import (
            CLOSED_STATUSES,
            IN_FLIGHT_STATUSES,
            BaselineError,
            audit_manifest,
            audit_outcome,
            audit_progress,
            parked_judge_runs,
            stalled_audits,
            start_baseline_audit,
            unanswered_counts,
        )
        from apps.a11y.models import A11yBaselineAudit
        from apps.a11y.review import can_manage_pages

        from .runner_views import CLAIM_LEASE

        project = self.get_object()
        if request.method == "POST":
            # An audit spends a real browser on a real application for minutes. Same list as the
            # page scope it runs over, because they are one decision taken twice.
            if not can_manage_pages(tenant_id=self.tenant_id, project_id=str(project.id),
                                    user_id=getattr(request.user, "id", None)):
                return Response({"detail": PAGE_ROLE_DETAIL}, status=status.HTTP_403_FORBIDDEN)
            try:
                audit = start_baseline_audit(
                    tenant_id=self.tenant_id, project_id=str(project.id),
                    base_url=request.data.get("base_url", ""),
                    routes=request.data.get("routes"),
                    started_by=getattr(request.user, "id", None),
                    # Opened from the app, so NOBODY is standing at the machine yet: it has to
                    # wait as `pending` until a companion claims it. Without this it defaulted
                    # to `capturing` — "a machine is already visiting" — and the claim endpoint
                    # only offers `pending` (or a stale `claimed`), so no companion could ever
                    # see it. The audit sat forever while the screen showed "Visiting pages",
                    # which is this capability's own worst failure: a confident report of work
                    # that was not happening. The companion's own `audit` subcommand is the
                    # other caller and correctly leaves the default, because there the machine
                    # that opened the audit is already about to visit.
                    claimable=True,
                )
            except BaselineError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"audit_id": str(audit.id), "status": audit.status,
                             "manifest": audit_manifest(audit)},
                            status=status.HTTP_201_CREATED)

        audits = list(A11yBaselineAudit.objects.filter(
            tenant_id=self.tenant_id, project_id=project.id)[:50])
        # Live progress, for the audits that still have somewhere to get to. A finished audit's
        # numbers are frozen on its own `summary`; asking again would be a second source for one
        # answer. Two grouped queries for the whole set, however many are in flight — normally
        # one, and this list polls every 5 seconds while anything is running.
        progress = audit_progress(
            self.tenant_id,
            [str(a.id) for a in audits if a.status in IN_FLIGHT_STATUSES],
        )
        # What the newest audit CAME TO, if it has finished. The panel that showed it running
        # does not disappear when it stops — it changes what it says — so the numbers a person
        # was watching for have to be there when they arrive. Only the newest, because that is
        # the only one the panel shows; every other finished audit is a row under Past audits.
        outcome = (audit_outcome(self.tenant_id, str(project.id))
                   if audits and audits[0].status in CLOSED_STATUSES else None)
        # How many elements of each CLOSED audit nothing ever looked at — what the "Check the
        # rest" button counts. Only for closed ones: while a pass is running the answer is still
        # changing, and offering to re-ask about elements the judge is at that moment working
        # through would start a second pass over the same work.
        unanswered = unanswered_counts(
            self.tenant_id, [a for a in audits if a.status in CLOSED_STATUSES])
        # Which in-flight audits nothing has been heard from. DERIVED, never written: a machine
        # switched off for good never comes back to be swept, and the screen must not be the one
        # thing still claiming the audit is running. Reading a list has no business closing an
        # audit, so this says so and leaves the row alone.
        stalled = stalled_audits(
            self.tenant_id, audits, stale_before=timezone.now() - CLAIM_LEASE)
        # …and which of those can no longer recover on their own. A judging pass whose deadline
        # has fired is PARKED, and the claim lease will never offer it back — so "start the
        # machine again" stops being true and the screen needs a button instead. See
        # `parked_judge_runs`; this is the run that button acts on.
        parked = parked_judge_runs(self.tenant_id, audits)
        return Response({"audits": [
            {"id": str(a.id), "status": a.status, "base_url": a.base_url,
             "routes": list(a.routes or []), "summary": a.summary or {},
             "progress": progress.get(str(a.id)),
             # "this says it is running, and nothing has come back from it for a long while".
             "stalled": str(a.id) in stalled,
             # …and WHEN it last spoke. A count with no time beside it reads the same after one
             # second and after twenty-five minutes, which is exactly how a dead judging pass
             # went on describing itself as "in progress" (9.26.E1). Null unless stalled: on a
             # healthy audit the honest answer is "it is talking to us now".
             "stalled_since": stalled.get(str(a.id)),
             # The judging run to finish when this audit can no longer recover by itself. Null
             # on every audit that can — which is the point: its presence is what tells the
             # screen to stop saying "start the machine again" and offer a way out instead.
             "parked_run_id": parked.get(str(a.id)),
             # Only on the newest, because that is the only one the panel shows — and the
             # numbers are this PROJECT's current standing, not a per-audit tally, which is
             # what a finding can actually be attributed to. See `audit_outcome`.
             "outcome": outcome if a is audits[0] else None,
             "unanswered": unanswered.get(str(a.id), 0),
             "created_at": a.created_at,
             # When the audit last moved, which is NOT `created_at` once a second judging pass
             # has run over the same capture: a re-judge re-uses the audit row deliberately
             # (see `rejudge_capture`), so without this the only time on screen was the audit's
             # own start — an hour older than the work being watched.
             "updated_at": a.updated_at}
            for a in audits
        ]})

    @action(detail=True, methods=["post"],
            url_path=r"a11y-audits/(?P<audit_id>[^/.]+)/rejudge")
    def a11y_audit_rejudge(self, request, pk=None, audit_id=None):
        """Ask the machine again about the elements of one audit that nothing ever looked at.

        **Not a second audit.** No page is visited and no browser is opened: everything the judge
        needs was stored when the pages were captured, so this is a second pass over one capture.
        Re-running the audit instead would re-visit every page to re-ask about a handful of
        elements, and would then compare a fresh capture against a report drawn from the old one.

        **It never re-asks about an answered `uncertain`.** "A check looked at this and could not
        decide" is a real verdict and it belongs to the person in the review queue; only elements
        nothing ever looked at are offered back to the machine. See
        `aipass.unanswered_for_capture` for how the two are told apart.

        Same role as starting an audit, and for the same reason: it spends a real engine run.
        """
        from apps.a11y.aipass import rejudge_capture
        from apps.a11y.baseline import CLOSED_STATUSES
        from apps.a11y.models import A11yBaselineAudit
        from apps.a11y.review import can_manage_pages

        project = self.get_object()
        if not can_manage_pages(tenant_id=self.tenant_id, project_id=str(project.id),
                                user_id=getattr(request.user, "id", None)):
            return Response({"detail": PAGE_ROLE_DETAIL}, status=status.HTTP_403_FORBIDDEN)
        audit = A11yBaselineAudit.objects.filter(
            tenant_id=self.tenant_id, project_id=project.id, id=audit_id).first()
        if audit is None:
            return Response({"detail": "That audit wasn't found in this project."},
                            status=status.HTTP_404_NOT_FOUND)
        if audit.status not in CLOSED_STATUSES:
            return Response(
                {"detail": "This audit hasn't finished yet, so what it hasn't looked at is "
                           "still changing. Wait for it to finish, then try again."},
                status=status.HTTP_409_CONFLICT)
        out = rejudge_capture(
            tenant_id=self.tenant_id, project_id=str(project.id), run_id=str(audit.id),
            title=audit.base_url or "", triggered_by=str(getattr(request.user, "id", "")) or None,
        )
        return Response(out)

    @action(detail=True, methods=["get", "post"], url_path="a11y-journeys")
    def a11y_journeys(self, request, pk=None):
        """Keyboard journeys for this project (G6b). `GET` lists, `POST` starts.

        Eight WCAG criteria cannot be answered by reading a page standing still — whether tabbing
        ever traps you, whether focus stays visible, whether a status message is announced. The
        only way to answer them is to operate the application, which is what these start.

        **`GET` carries the address to pre-fill**, from the last audit or the repository, so the
        panel reads one payload rather than two. `POST` never starts more than the cap and never
        drops the excess: what it did not start comes back named, with a reason for each.

        **Anyone may look; only the accessibility reviewer may start one.** Enforced inside
        `queue_journeys` rather than here, the same way `conformance.sign` does it, because the
        role is a project Membership and this class-level hook has no project in hand.
        """
        from apps.a11y.journey import (
            JourneyRoleError,
            queue_journeys,
            walkable_journeys,
        )

        project = self.get_object()
        if request.method == "POST":
            refs = request.data.get("test_refs")
            if refs is not None and not isinstance(refs, list | tuple):
                return Response({"detail": "Choose the journeys to start as a list."},
                                status=status.HTTP_400_BAD_REQUEST)
            try:
                out = queue_journeys(
                    tenant_id=self.tenant_id, project_id=str(project.id),
                    base_url=request.data.get("base_url", ""), test_refs=refs,
                    user_id=getattr(request.user, "id", None),
                )
            except JourneyRoleError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
            # 200, not 201: a queue call can legitimately start nothing (everything already
            # walking, nothing walkable) and reporting that as "created" would be a lie the
            # screen then has to unpick.
            return Response(out)

        from apps.a11y.review import can_review

        return Response({
            **walkable_journeys(self.tenant_id, str(project.id)),
            "can_start": can_review(tenant_id=self.tenant_id, project_id=str(project.id),
                                    user_id=getattr(request.user, "id", None)),
        })

    @action(detail=True, methods=["get"], url_path="a11y-review")
    def a11y_review(self, request, pk=None):
        """The findings waiting on a person, worst first, with the evidence to judge them (QA-23).

        This is the queue `findings.review_queue` has always described and nothing has ever
        been able to open. Every row carries the element, the criterion, what the check saw and
        whether a picture exists — and, when one does not, the reason, because an empty frame
        with no explanation is the silence this build exists against.

        `can_review` says whether THIS user may answer. A reader without the role still sees
        everything; the console renders read-only rather than showing controls that fail on
        click (S-36's ninth state).
        """
        from apps.a11y.review import LOCK_MINUTES, can_review, ever_checked, queue

        project = self.get_object()
        user_id = getattr(request.user, "id", None)
        rows = queue(tenant_id=self.tenant_id, project_id=str(project.id), user_id=user_id)
        return Response({
            "queue": rows,
            "can_review": can_review(tenant_id=self.tenant_id, project_id=str(project.id),
                                     user_id=user_id),
            "lock_minutes": LOCK_MINUTES,
            # Which of the two empty states the screen should show. Only asked when the queue is
            # empty, because that is the only time the answer changes anything — and asking it
            # unconditionally would put two more queries on the busiest accessibility screen.
            "ever_checked": (True if rows else
                             ever_checked(tenant_id=self.tenant_id, project_id=str(project.id))),
        })

    @action(detail=True, methods=["get", "post"], url_path=r"a11y-review/(?P<finding_id>[^/]+)")
    def a11y_review_item(self, request, pk=None, finding_id=None):
        """`GET` opens one item (which claims it); `POST` records the reviewer's answer.

        Opening is what takes and renews the claim, so the lock follows what the reviewer is
        actually doing rather than needing a button nobody remembers to press. A `GET` that
        cannot claim still returns the item — `locked_out` carries the sentence to show, and
        the screen goes read-only. That is a state, not an error, and a 409 here would make an
        ordinary second reviewer look like a failure.

        `POST` refuses on three grounds and says which: wrong role, someone else holds it, or
        it was already decided. Each refusal states that nothing was changed, because the one
        thing a reviewer must never wonder is whether their answer half-landed.
        """
        from apps.a11y.review import (
            ReviewError,
            ReviewLockError,
            ReviewRoleError,
            adjudicate,
            open_item,
        )

        project = self.get_object()
        user_id = getattr(request.user, "id", None)
        if request.method == "POST":
            try:
                finding = adjudicate(
                    tenant_id=self.tenant_id, project_id=str(project.id),
                    finding_id=finding_id, user_id=user_id,
                    decision=request.data.get("decision", ""),
                    note=request.data.get("note", ""),
                )
            except ReviewRoleError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
            except ReviewLockError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
            except ReviewError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            return Response({
                "id": str(finding.id),
                "adjudication": finding.adjudication,
                "outcome": finding.outcome,
                "status": finding.status,
                "severity": finding.severity,
                # True only when this will actually raise a ticket, so the screen never promises
                # "a defect has been opened" for a finding under the project's blocking bar.
                "opens_defect": _a11y_would_ticket(self.tenant_id, str(project.id), finding),
            })

        try:
            return Response(open_item(
                tenant_id=self.tenant_id, project_id=str(project.id),
                finding_id=finding_id, user_id=user_id,
            ))
        except ReviewError as exc:
            raise NotFound(str(exc)) from exc

    @action(detail=True, methods=["get"], url_path=r"a11y-finding/(?P<finding_id>[^/]+)")
    def a11y_finding(self, request, pk=None, finding_id=None):
        """One finding, opened to be READ — no claim taken, no lock renewed (S-39).

        Every finding in an audit's report says "screenshot shows…", and until this endpoint
        there was nowhere to go and see that screenshot unless the finding happened to be
        awaiting a person. The queue holds only `needs_review`; a confirmed failure — which is
        what a report is mostly made of — could not be opened at all.

        **Deliberately not `a11y-review/<id>`.** That one claims the item as a side effect,
        which is right for a reviewer working the queue and wrong for anyone following a link
        out of a document: a failure nobody is reviewing must not acquire a reviewer's name
        because somebody looked at it. Same evidence, same picture, no side effect.
        """
        from apps.a11y.review import ReviewError, read_finding

        project = self.get_object()
        try:
            return Response(read_finding(
                tenant_id=self.tenant_id, project_id=str(project.id),
                finding_id=finding_id, user_id=getattr(request.user, "id", None),
            ))
        except ReviewError as exc:
            raise NotFound(str(exc)) from exc

    @action(detail=True, methods=["get"],
            url_path=r"a11y-review/(?P<finding_id>[^/]+)/screenshot")
    def a11y_review_screenshot(self, request, pk=None, finding_id=None):
        """Stream the page (or element) picture behind one finding — read-through (QA-23).

        `screenshot_ref` has always been an object-store key with nothing able to turn it into
        something a browser can show. A reviewer cannot judge what they cannot see, so this is
        the endpoint that makes the console possible at all. The key is validated against this
        project's own prefix before it is fetched, never trusted because it came out of a row.
        """
        from apps.a11y.review import ReviewError, screenshot

        project = self.get_object()
        try:
            data, mime = screenshot(
                tenant_id=self.tenant_id, project_id=str(project.id), finding_id=finding_id,
                kind=request.query_params.get("kind", "page"),
            )
        except ReviewError as exc:
            raise NotFound(str(exc)) from exc
        return inline_response(data, filename="a11y-capture.png", content_type=mime)

    @action(detail=True, methods=["get", "put"], url_path="a11y-conformance")
    def a11y_conformance(self, request, pk=None):
        """The WCAG conformance statement: all 55 criteria, the draft, and the signature (QA-24).

        `GET` compiles it. Every Level A and AA criterion is listed — including the ones nothing
        looked at, printed as **not evaluated** and never folded into a supporting result, which
        is the single easiest way for a document like this to become untrue.

        `PUT` saves the reviewer's scope, wording and per-criterion levels. **Any edit clears the
        signature**, because a signature on wording nobody signed is worse than none.

        The engine, model, prompt and scanner versions are deliberately NOT in this payload
        (D-A11Y-96). They are recorded on the signature's audit entry, where a statement can be
        traced back to what produced it without putting our implementation detail on a client's
        screen.
        """
        from apps.a11y.conformance import (
            ConformanceError,
            ConformanceRoleError,
            can_sign,
            save_draft,
            state,
        )

        project = self.get_object()
        user_id = getattr(request.user, "id", None)
        if request.method == "PUT":
            try:
                payload = save_draft(
                    tenant_id=self.tenant_id, project_id=str(project.id), user_id=user_id,
                    scope=request.data.get("scope"), body=request.data.get("body"),
                    verdicts=request.data.get("verdicts"),
                )
            except ConformanceRoleError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
            except ConformanceError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            payload = state(tenant_id=self.tenant_id, project_id=str(project.id))
        payload["can_sign"] = can_sign(tenant_id=self.tenant_id, project_id=str(project.id),
                                       user_id=user_id)
        return Response(payload)

    @action(detail=True, methods=["post"], url_path="a11y-conformance/sign")
    def a11y_conformance_sign(self, request, pk=None):
        """Sign the statement — which is also what unlocks export (team decision B1).

        The ordinary `Approval` model cannot carry this document: it requires a `Run` and
        `gates.services.decide` signals that run's Temporal workflow, and a statement compiled
        from the ledger across many runs has neither. So the signature does a gate's job — a
        role-checked person, named, timestamped, bound to the exact wording, audit-logged — and
        flips the artifact to `approved`, which is the state the existing publish endpoint
        already demands. Nothing reaches a system of record without a named human approval.
        """
        from apps.a11y.conformance import ConformanceError, ConformanceRoleError, sign

        project = self.get_object()
        try:
            payload = sign(
                tenant_id=self.tenant_id, project_id=str(project.id),
                user_id=getattr(request.user, "id", None),
                name=request.data.get("name", ""),
                acknowledged=bool(request.data.get("acknowledged")),
            )
        except ConformanceRoleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ConformanceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        # The screen writes this reply straight into its cache, so it must carry everything the
        # GET does. Without `can_sign` the Statement and Export boxes vanished after signing
        # until the page was reloaded (live retest 2026-10-12).
        from apps.a11y.conformance import can_sign
        payload["can_sign"] = can_sign(tenant_id=self.tenant_id, project_id=str(project.id),
                                       user_id=getattr(request.user, "id", None))
        return Response(payload)

    @action(detail=True, methods=["post"], url_path="a11y-conformance/export")
    def a11y_conformance_export(self, request, pk=None):
        """Export the signed statement. Refused unsigned, and refused stale (AC3, C1).

        Checked here as well as by the publish endpoint's gate, deliberately: that endpoint
        knows only that an artifact is approved, and the sentence a refused reviewer needs to
        read is about a signature, not a status.
        """
        from apps.a11y.conformance import ConformanceError, export_statement

        project = self.get_object()
        try:
            payload = export_statement(
                tenant_id=self.tenant_id, project_id=str(project.id), user_id=request.user.id)
        except ConformanceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        # The screen downloads the signed wording from this artifact right after.
        return Response({
            "artifact_id": payload["artifact_id"],
            "exported_at": payload["exported_at"],
            "signed_by": payload["signed_name"],
            "signed_at": payload["signed_at"],
        })

    @action(detail=True, methods=["get"], url_path="a11y-backlog")
    def a11y_backlog(self, request, pk=None):
        """What to fix first, worst first (QA-18), with where the project stands by criterion.

        `?all=1` widens it from the items that clear the project's blocking bar to every open
        finding, including the ones waiting on a reviewer. Narrow by default so the list a
        person opens is the list their tracker holds — the same items, the same order.

        Read-only. Deciding a finding's fate is the reviewer console's job (QA-23); this is the
        queue of work, not the queue of decisions.
        """
        from apps.a11y.backlog import backlog_container, prioritised
        from apps.a11y.baseline_report import BASELINE_TYPE, criterion_rows

        project = self.get_object()
        include_all = str(request.query_params.get("all", "")).strip().lower() in ("1", "true")
        items = prioritised(self.tenant_id, str(project.id), blocking_only=not include_all)
        baseline = (
            Artifact.objects
            .filter(tenant_id=self.tenant_id, project_id=project.id, type=BASELINE_TYPE)
            .order_by("-version", "-created_at").first()
        )
        container = backlog_container(self.tenant_id, str(project.id))
        return Response({
            "backlog": [
                {k: v for k, v in item.items() if k != "finding"} | {
                    "finding_id": str(item["finding"].id),
                }
                for item in items
            ],
            "by_criterion": [
                {k: v for k, v in row.items()} for row in
                criterion_rows(self.tenant_id, str(project.id))
            ],
            "container": {"id": str(container.id), "key": container.key,
                          "title": container.title},
            "baseline": None if baseline is None else {
                "artifact_id": str(baseline.id), "version": baseline.version,
                "updated_at": baseline.updated_at,
            },
        })

    @action(detail=True, methods=["get"])
    def traceability(self, request, pk=None):
        """Lineage graph for the viewer (spec §5): artifact nodes + their TraceEdges,
        each node carrying its SoR pointer/url so the UI can deep-link to the live
        Confluence page / Jira issue. The requirement→PRD→epic→story chain walks these."""
        project = self.get_object()
        # `run__work_item` so every node can say WHICH WORK ITEM it belongs to (P3). The map's
        # own question — "what came out of this piece of work" — could not be asked of it before:
        # a node carried its phase, type and status but nothing tying it to a work item, so the
        # screen had no way to follow one item's chain. The link already exists on every record
        # (an artifact names the run that produced it, and a run always has a work item); this
        # follows it in the same query instead of adding one per node.
        #
        # `run` is nullable, and that is not a fault: documents adopted during brownfield
        # onboarding were never produced by a run, so they genuinely belong to no work item.
        # They report empty values here, and the screen offers "Not tied to a work item" for
        # them rather than leaving them unreachable by the filter.
        artifacts = (
            Artifact.objects.filter(tenant_id=self.tenant_id, project=project)
            .select_related("run__work_item")
        )
        nodes = []
        for a in artifacts:
            ext = a.external_ref or {}
            work_item = a.run.work_item if a.run_id else None
            nodes.append({
                "id": str(a.id), "kind": "artifact", "phase": a.phase, "type": a.type,
                "title": a.title, "status": a.status, "sor": a.sor,
                "external_ref": ext or None, "url": ext.get("url"),
                "work_item": str(work_item.id) if work_item else None,
                "work_item_key": (work_item.key or "") if work_item else "",
                "work_item_title": (work_item.title or "") if work_item else "",
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
            raise ValidationError({"file": "Choose a file to upload."})
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
        """GET the onboarding hub state (S-24): upload/adopt/register/index/gap in one read.

        Brownfield only. Bugs S.No 221: the nav item is hidden for a greenfield project, but
        hiding a door is not locking it — `/onboarding` is still a URL anyone can type, and
        this endpoint would happily assess a project that has nothing to assess. The check
        lives here as well so the answer is the same however the screen is reached.
        """
        project = self.get_object()
        if project.track != Project.Track.BROWNFIELD:
            raise PermissionDenied(
                "Onboarding assesses an existing codebase, and this project was started "
                "from scratch. It is available on brownfield projects only."
            )
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
            return Response({"detail": "That repository isn't part of this project."},
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
        from integrations.onboarding import carrier_q

        project = self.get_object()
        user = current_user(request)
        tid = self.tenant_id
        one_week_ago = timezone.now() - timedelta(days=7)

        from apps.gates.services import gate_roles_decidable_by

        # Bugs S.No 222. The three tiles read "…your approval", "…awaiting you" and "My runs",
        # and only the third was filtered to the person reading it: the other two listed every
        # pending gate and question on the project, whoever they were for. The filters below are
        # the platform's own rules for who may act, not a second copy of them:
        #   gates — `gate_roles_decidable_by`, the function `decide_gate` enforces with, so this
        #     queue can never offer a gate the Approve button then refuses. Admins may decide any
        #     gate, so they still see every one.
        #   questions — project membership, which is exactly what `answer_clarification` checks.
        #     No admin fallback, because that function has none: a tenant admin who is not a
        #     member would be shown a question and then refused on answering it.
        pending_gates_q = Approval.objects.none()
        pending_clarifications_q = Clarification.objects.none()
        my_runs_q = Run.objects.none()
        if user:
            pending_gates_q = Approval.objects.filter(
                tenant_id=tid, work_item__project=project, decision="pending")
            decidable = gate_roles_decidable_by(
                tenant_id=tid, user_id=user.id, project_id=project.id)
            if decidable is not None:
                pending_gates_q = pending_gates_q.filter(required_role__in=decidable)
            if Membership.objects.filter(
                    tenant_id=tid, user_id=user.id, project=project).exists():
                pending_clarifications_q = Clarification.objects.filter(
                    tenant_id=tid, work_item__project=project, status="pending")
            my_runs_q = (
                Run.objects.filter(
                    tenant_id=tid, work_item__project=project,
                    triggered_by=user, status__in=["running", "awaiting_gate"],
                )
                # Headless onboarding runs (Index code / Gap report) report their progress on the
                # Onboarding hub, not here — counting them made the dashboard claim work needed
                # the user when the whole point is that it doesn't.
                .exclude(carrier_q("work_item__"))
            )
        # The lists stay trimmed; the COUNTS below do not. The tiles used to show the length of
        # a list cut at 20, so a busy project quietly under-reported — and the number is the one
        # thing on the screen that has to be right even when the list beside it is incomplete.
        # Oldest first: a queue is worked from the thing that has waited longest.
        pending_gates = list(
            pending_gates_q.select_related("work_item").order_by("created_at")[:20])
        pending_clarifications = list(
            pending_clarifications_q.select_related("work_item").order_by("created_at")[:20])
        # `work_item` as well as `agent_spec`: every row below now names its work item the way
        # the rest of the product does (P2), and the gates/questions lists above already load it.
        my_runs = list(my_runs_q.select_related("agent_spec", "work_item")[:10])

        # Filtered on when it was PUBLISHED, not when it was drafted (Bugs S.No 224). Drafting
        # and publishing are separated by a review gate, so they are routinely days apart: on
        # `created_at` this list omitted something published this morning because it was drafted
        # eight days ago, and included something drafted today that nobody has published at all.
        recent_published = list(
            Artifact.objects.filter(
                tenant_id=tid, project=project,
                status=Artifact.Status.PUBLISHED, published_at__gte=one_week_ago,
            ).order_by("-published_at")[:5]
        )

        # Every row carries its work item's NUMBER and TITLE, not only the internal id (P2). The
        # queue is the first thing a client reads each morning, and it used to name each item by
        # eight characters of a UUID — a string that matches nothing they can search for, quote or
        # recognise, and which the same row sometimes printed twice. The work item is already
        # loaded beside each row (`select_related` above), so this passes on what is in hand
        # rather than asking the database again.
        return Response({
            "needs_me": {
                "gates": [
                    {
                        "approval_id": str(a.id),
                        "gate": a.gate_type,
                        "work_item": str(a.work_item_id),
                        "work_item_key": a.work_item.key or "",
                        "work_item_title": a.work_item.title or "",
                        "role": a.required_role,
                    }
                    for a in pending_gates
                ],
                "clarifications": [
                    {
                        "id": str(c.id),
                        "work_item": str(c.work_item_id),
                        "work_item_key": c.work_item.key or "",
                        "work_item_title": c.work_item.title or "",
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
                        "work_item_key": r.work_item.key or "",
                        "work_item_title": r.work_item.title or "",
                        "status": r.status,
                        # How long it has been going, so the row can say that instead of
                        # reprinting an id nobody can read.
                        "started_s": int((timezone.now() - r.created_at).total_seconds()),
                    }
                    for r in my_runs
                ],
                # True totals for the tiles and the topbar bell (S.No 222) — see above.
                "counts": {
                    "gates": pending_gates_q.count(),
                    "clarifications": pending_clarifications_q.count(),
                    "my_runs": my_runs_q.count(),
                },
            },
            "health": {
                # Carriers are excluded from BOTH of these, because both have a list beside them
                # that already excludes carriers and a number that disagrees with the list it
                # summarises is worse than no number: the board shows 30 items and "Work items"
                # said 62, Phases & Runs shows nothing running and "Phases in progress" said 1.
                #
                # `awaiting_gate` deliberately does NOT exclude them. Gates are not carrier-
                # filtered anywhere, and the gap report has been gated since 2026-08-03 — its
                # approval sits on a carrier and is real work a person must do. Excluding it here
                # would hide a pending gate the Gates screen still lists, which is the same
                # disagreement pointing the other way.
                #
                # Cancelled items are excluded for exactly the same reason (S.No 140): the
                # board hides them by default, so counting them here would recreate the very
                # disagreement the paragraph above exists to prevent.
                "work_items": WorkItem.objects.filter(tenant_id=tid, project=project)
                .exclude(carrier_q())
                .exclude(state=WorkItem.State.CANCELLED).count(),
                "phases_in_progress": Run.objects.filter(
                    tenant_id=tid, work_item__project=project, status="running"
                ).exclude(carrier_q("work_item__")).count(),
                "awaiting_gate": Approval.objects.filter(
                    tenant_id=tid, work_item__project=project, decision="pending"
                ).count(),
                "published_week": Artifact.objects.filter(       # by publish date (S.No 224)
                    tenant_id=tid, project=project,
                    status=Artifact.Status.PUBLISHED, published_at__gte=one_week_ago,
                ).count(),
            },
            # N2: the title alone gave the browser nothing to link with, so "recently published"
            # was a list of names the user could look at and not open. Send the id too.
            "recent_publishes": [
                {"artifact_id": str(a.id), "title": a.title or f"{a.type} — {a.phase}"}
                for a in recent_published
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
                tenant_id=self.tenant_id, project_id=str(project.id), user_id=actor,
                what="add a repository to this project",
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
                tenant_id=self.tenant_id, project_id=str(project.id), user_id=actor,
                what=("change a repository's settings" if request.method == "PATCH"
                      else "remove a repository from this project"),
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
                tenant_id=self.tenant_id, project_id=str(project.id), user_id=actor,
                what="change which repository is the default for this project",
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

    def get_permissions(self):
        # A3: streaming the original file / captured page images is member-gated (these serve raw
        # uploaded bytes — never AllowAny).
        if self.action in {"original", "page"}:
            return [IsAuthenticatedMember()]
        return super().get_permissions()

    @action(detail=True, methods=["get"])
    def original(self, request, pk=None):
        """A3: stream the original uploaded file so the user sees exactly what they uploaded
        (the browser renders a PDF/image inline). Read-through from S3, never stored back."""
        from storage import s3_from_settings

        src = self.get_object()
        # Screen Words group 5: both of these reach a person who clicked "view my upload", so they
        # start with a capital and say which case it is. The two are genuinely different — one
        # document never had a file kept, the other had one that is now gone.
        if not src.s3_key:
            raise NotFound("The original file wasn't kept for this document.")
        try:
            data = s3_from_settings().get(src.s3_key)
        except Exception as exc:  # noqa: BLE001 — missing object → 404, not 500
            raise NotFound("That file isn't stored any more, so it can't be shown.") from exc
        # The filename is whatever the uploader called the file, so it goes through the sanitiser
        # rather than into an f-string — see api/files.py.
        return inline_response(data, filename=src.filename,
                               content_type=src.mime or "application/octet-stream")

    @action(detail=True, methods=["get"], url_path="page")
    def page(self, request, pk=None):
        """A3: stream one captured page render / embedded image (external_ref.page_images),
        selected by its `name`. Validates the name against the artifact so no arbitrary key can
        be read."""
        from storage import s3_from_settings

        src = self.get_object()
        name = request.query_params.get("name") or ""
        aids = list(src.extracted_artifact_ids or [])
        art = None
        if aids:
            art = Artifact.objects.filter(id=aids[0], tenant_id=self.tenant_id).first()
        images = ((art.external_ref or {}).get("page_images") if art else None) or []
        match = next((im for im in images if im.get("name") == name), None)
        if not match or not match.get("s3_key"):
            raise NotFound("That page image doesn't exist.")
        try:
            data = s3_from_settings().get(match["s3_key"])
        except Exception as exc:  # noqa: BLE001
            raise NotFound("That page image isn't stored any more, so it can't be shown.") from exc
        return inline_response(data, filename=name,
                               content_type=match.get("mime") or "image/png")

    @action(detail=True, methods=["post"])
    def adopt(self, request, pk=None):
        """Review gate: a product_owner publishes the extracted draft artifacts, classifying the
        document into its lifecycle type (Brownfield B2-1). The acting user is the session user
        when present (Brownfield B2-2), falling back to the `user_id` body for pre-auth/test
        callers; the service still enforces the product_owner/admin gate role on that actor.
        (Hard authentication-gating of this endpoint is tracked separately as X-1, not this
        batch.)"""
        src = self.get_object()
        ser = AdoptSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        actor = resolve_actor(request, ser.validated_data.get("user_id"))
        if not actor:
            raise ValidationError({"user_id": "Sign in to do this."})
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
def _email_outcome(invitation) -> dict:
    from django.conf import settings as dj_settings

    return {
        "email_sent": bool(getattr(invitation, "email_sent", False)),
        "email_delivery": "console" if "console" in dj_settings.EMAIL_BACKEND else "email",
    }


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
        # 2026-10-09: tell the admin whether the email actually went (SendGrid), or that this
        # copy of the app has no mail service and printed the link to the server terminal.
        return Response(
            {**InvitationSerializer(invitation).data, **_email_outcome(invitation)},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def resend(self, request, pk=None):
        invitation = self.get_object()
        try:
            resend_invitation(invitation)
        except InvitationError as exc:
            raise ValidationError(str(exc)) from exc
        return Response({**InvitationSerializer(invitation).data, **_email_outcome(invitation)})

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
    # `select_related("parent")` is load-bearing, not tidiness: `WorkItemSerializer.parent_key`
    # reads the parent's key, and this endpoint returns a whole project's backlog in one response
    # (there is no pagination on the board). Without it that is one extra query per card — a few
    # hundred on a real board — which is how a one-line serializer field becomes an outage.
    queryset = WorkItem.objects.select_related("parent").order_by("-created_at")

    def get_permissions(self):
        # Bugs S.No 214. This viewset had NO get_permissions at all, so every one of its writes
        # inherited the project-wide DRF default of `AllowAny` — creating and editing work items,
        # and starting phase runs, took no login whatsoever. Reads are left as they were.
        #
        # `trigger` and `build` are gated a second time by role inside the action: they spend real
        # Claude subscription time on the team's account. `take_over` seizes a work item somebody
        # else is building.
        # `transition` belongs on this list for the same reason as the rest: leaving it off
        # would hand it the project-wide AllowAny default, which is S.No 214 all over again —
        # anyone on the internet closing a team's work items.
        if self.action in {"create", "update", "partial_update", "trigger", "build",
                           "take_over", "transition"}:
            return [IsAuthenticatedMember()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return WorkItemPatchSerializer
        return WorkItemSerializer

    def get_queryset(self):
        from integrations.onboarding import carrier_q

        qs = super().get_queryset()
        # Carrier work items (onboarding + document-vision) are internal plumbing that only host
        # an agent run — never backlog items a human authored — so they are hidden from the
        # user-facing work-item LIST (backlog/board). Direct retrieval by id still resolves (in
        # case a run detail links to one), and the trigger/run machinery resolves them by their
        # external_ref markers regardless; this only affects what the backlog shows.
        # The S3-13 `has_key` guard lives in `carrier_q` — read its docstring before touching it.
        if self.action == "list":
            qs = qs.exclude(carrier_q())
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
            raise ValidationError({"project": "That project isn't in this workspace."})
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
            raise ValidationError({"repo": "That repository belongs to a different project."})
        serializer.save()

    @action(detail=True, methods=["get"], url_path="test-cases")
    def test_cases(self, request, pk=None):
        """The story's child `test_case` work items + each one's automation status (P3-09b) —
        backs the Test cases coverage screen. `tc_id`/`priority`/`type` come from `external_ref`,
        written there when the case was materialised from its artifact (G2) or typed in by hand.
        Blank means the case never said — never a default, because a guessed type on a screen a
        QA Lead filters by is worse than an empty cell."""
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
                "type": (w.external_ref or {}).get("type", ""),
                "automation_status": automation_status_for(w),
            }
            for w in kids
        ])

    def _card_fields(self, work_items):
        """P4.8-T1 bucket-B gap B: artifact_count/owner/needs the board + detail cards render,
        computed here rather than on the plain model serializer (they aren't columns). Keyed
        by str(id) throughout — serializer output carries string ids, model FK attributes UUIDs."""
        from apps.gates.services import gate_roles_decidable_by

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
        # The gate's REQUIRED ROLE travels with its type, so each card can say whether the
        # person looking may decide it (S.No 117 follow-up). Without it the board called every
        # pending gate "Waiting for you" — to a Designer looking at a build gate only a Tech Lead
        # can approve, and at the same moment the dashboard told them nothing was waiting.
        needs_gate = {
            str(a.work_item_id): (a.gate_type, a.required_role)
            for a in Approval.objects.filter(
                tenant_id=self.tenant_id, work_item_id__in=ids, decision="pending"
            )
        }
        # Who is looking, and what they may act on. Both answers come from the platform's own
        # rules — `gate_roles_decidable_by`, which `decide_gate` enforces with, and project
        # membership, which is exactly what `answer_clarification` checks — so the board, the
        # dashboard and the Approve/Answer buttons can never disagree. Resolved once per project
        # on the board (normally one), never per card.
        viewer = current_user(getattr(self, "request", None))
        decidable_cache: dict[str, frozenset[str] | None] = {}
        member_cache: dict[str, bool] = {}

        def _may_decide(project_id: str, required_role: str) -> bool:
            if viewer is None:
                return False
            if project_id not in decidable_cache:
                decidable_cache[project_id] = gate_roles_decidable_by(
                    tenant_id=self.tenant_id, user_id=viewer.id, project_id=project_id)
            roles = decidable_cache[project_id]
            return roles is None or required_role in roles

        def _may_answer(project_id: str) -> bool:
            if viewer is None:
                return False
            if project_id not in member_cache:
                member_cache[project_id] = Membership.objects.filter(
                    tenant_id=self.tenant_id, user_id=viewer.id, project_id=project_id).exists()
            return member_cache[project_id]
        # The item's CURRENT lifecycle phase = its latest run's agent phase (Bugs.xlsx
        # rows 49/50: the board/list showed the feature stream as "Phase"). One query,
        # newest run per work item.
        #
        # The same run's STATUS travels with it (Bugs S.No 117). The board placed a card by this
        # run's phase and then never said what that phase was doing, so "running", "waiting on a
        # reviewer" and "failed an hour ago" all looked identical — and a failed run left in its
        # column read as though it were still going.
        current_phase = {}
        run_status = {}
        for r in (
            Run.objects.filter(tenant_id=self.tenant_id, work_item_id__in=ids)
            .select_related("agent_spec")
            # `-id` is a tie-break, not a claim about recency: two runs created inside the same
            # clock tick (a double trigger, or a coarse system clock) otherwise left "the latest
            # run" undefined, so the card could take either run's phase and status from one page
            # load to the next. Arbitrary but stable beats arbitrary and changing.
            .order_by("work_item_id", "-created_at", "-id")
            .distinct("work_item_id")
        ):
            spec = r.agent_spec
            current_phase[str(r.work_item_id)] = (
                (spec.key or spec.phase_label) if spec else ""
            )
            run_status[str(r.work_item_id)] = r.status
        out = {}
        for w in work_items:
            wid = str(w.id)
            project_id = str(w.project_id)
            if wid in needs_clarification:
                needs = {"clarification": True, "label": "Needs answer",
                         "yours": _may_answer(project_id)}
            elif wid in needs_gate:
                gate_type, required_role = needs_gate[wid]
                needs = {"gate": True, "label": humanize_gate(gate_type),
                         "yours": _may_decide(project_id, required_role)}
            else:
                needs = None
            out[wid] = {
                "artifact_count": counts.get(wid, 0),
                "owner": w.assignee.name if w.assignee_id else None,
                "needs": needs,
                "current_phase": current_phase.get(wid, ""),
                "run_status": run_status.get(wid, ""),
            }
        return out

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset()).select_related("assignee")
        page = self.paginate_queryset(qs)
        work_items = page if page is not None else list(qs)
        card_fields = self._card_fields(work_items)
        data = WorkItemSerializer(work_items, many=True).data
        empty_card = {"artifact_count": 0, "owner": None, "needs": None, "current_phase": "",
                      "run_status": ""}
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
    def transition(self, request, pk=None):
        """Move a work item by hand — Bugs S.No 140: close what cannot be built, and (2026-09-30)
        reopen it if that was a mistake.

        The rules (which moves are legal, and that cancelling needs a reason) live in
        `apps.workitems.cancel` so the endpoint and any future caller cannot disagree about
        them. This does the two things that are the view's own: check who is asking, and
        attribute the decision to them.

        `tech_lead` or `admin`, per the team's decision, for both directions. Neither is an
        everyday edit: cancelling takes work off the board and — when the item is a blocking
        defect — releases the gate that defect was holding shut, and reopening puts both back.
        """
        work_item = self.get_object()
        # Named for the move being attempted, not for cancelling. The refusal sentence quotes
        # this, so a reviewer refused on a REOPEN was being told they may not "close or cancel"
        # something — a true sentence about a thing they were not doing, which reads as the
        # platform having misunderstood the click.
        requested = str(request.data.get("to_state") or "")
        require_project_write_role(
            tenant_id=self.tenant_id, project_id=str(work_item.project_id),
            user_id=getattr(current_user(request), "id", None),
            what=("reopen a cancelled work item"
                  if requested == WorkItem.State.PROPOSED
                  else "close or cancel a work item"),
        )
        ser = WorkItemTransitionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        out = cancel_work_item(
            tenant_id=self.tenant_id, work_item_id=str(work_item.id),
            to_state=ser.validated_data["to_state"],
            reason=ser.validated_data.get("reason", ""),
            actor_id=resolve_actor(request, ser.validated_data.get("user_id")),
        )
        data = WorkItemSerializer(out["work_item"]).data
        data["gates_notified"] = out["gates_notified"]
        return Response(data)

    @action(detail=True, methods=["post"])
    def trigger(self, request, pk=None):
        """Start a phase run for this work item (replaces the legacy command). Build phases
        (07_implementation / 09b_test_automation / 11_cicd — the ones that produce a PR) route
        to the BuildWorkflow via `trigger_build`; every other phase runs as an agent-run. This
        keeps a single UI trigger correct for both plan and build phases (routing lives here,
        keyed off the catalog's `rides_build`, so a new build agent needs no UI change)."""
        work_item = self.get_object()
        # Layer 2 of S.No 214. Membership rather than a lead role, deliberately: a phase run
        # spends engine time, but each ROLE drives its own phase — a Product Owner triggers
        # ideation, an Engineer triggers implementation — so a tech_lead-only bar would lock most
        # of the team out of the ordinary journey. What this closes is a signed-in user acting on
        # a project they are not on at all.
        require_project_member(
            tenant_id=self.tenant_id, project_id=str(work_item.project_id),
            user_id=getattr(current_user(request), "id", None),
            what="start a phase run",
        )
        ser = TriggerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        agent_key = ser.validated_data["agent_key"]
        # Don't dispatch work onto a machine that isn't there. A phase sent to a dead companion
        # is claimed by nobody: the run flips to RUNNING with `dispatch.status` still "pending"
        # and sits looking live until the 2h takeover. The screens now grey their trigger
        # buttons when the companion is offline, but the status they read can be up to
        # ONLINE_THRESHOLD stale, and a page left open since before the drop knows nothing at
        # all — so the refusal has to exist somewhere a stale screen cannot bypass.
        #
        # Here in the view and not in `trigger_phase`, deliberately. That function is also
        # called by the onboarding/vision hooks, by the CI server-mode fallback and by most of
        # the test suite — which enrolls companions that never check in — so guarding inside it
        # would refuse all of them and break its documented "trigger first, start your companion
        # second" path. This is the HUMAN boundary (it already carries the only other
        # human-only check, the membership one), which is where a guard about a human's own
        # machine belongs.
        #
        # Only "stale" is refused — a machine that WAS there and stopped answering, which is the
        # reported bug. The other two no-machine cases are deliberate flows and must keep
        # working: "never" is onboarding's mint-token-then-trigger-then-connect path, and "none"
        # resolves to a legitimate server-mode run.
        #
        # Raised INSIDE the try so it travels the `except TriggerError` path already below —
        # which files it as a non-field error (Screen Words group 5). Raised above the try it
        # would escape as a 500, since `NoCompanionError` is only handled in there.
        try:
            # Actor = the session user when present (routes the phase to *their* companion
            # enrollment), else the pre-auth/runner `user_id` body param (T5).
            triggered_by = resolve_actor(request, ser.validated_data.get("user_id"))
            # Resolved BEFORE the guard, and the guard reads it: on the pre-auth path the actor
            # is the body's `user_id`, not the session user, so asking about the session user
            # would check a different person's machine than the one the dispatch routes to.
            if companion_liveness_for(
                self.tenant_id, str(work_item.project_id), triggered_by,
            ) == "stale":
                raise NoCompanionError(
                    "Your machine isn't connected, so this can't start. Reconnect your machine "
                    "and try again."
                )
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
            # Screen Words group 5: filed as a non-field error. Under `agent_key` every trigger
            # refusal reached the screen with that key as a prefix — including the friendly
            # "start your companion" one — and `agent_key` is not a field anybody can see.
            raise ValidationError(str(exc)) from exc
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
        # Layer 2 of S.No 214 — same reasoning as `trigger` above.
        require_project_member(
            tenant_id=self.tenant_id, project_id=str(work_item.project_id),
            user_id=getattr(current_user(request), "id", None),
            what="start a build",
        )
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

        # Tier mapping by work-item type. `test_case` is delivered like a task; anything
        # unknown plans, because a rail showing too much is survivable and one showing nothing
        # is not.
        tier_map = {"epic": "plan", "story": "plan", "task": "build",
                    "test_case": "build", "defect": "remediation"}
        tier = tier_map.get(work_item.type, "plan")
        tier_keys = PHASE_KEYS_BY_TIER.get(tier, PLAN_PHASE_KEYS)

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

        # The line this endpoint has been missing since it was written: `tier` was worked out
        # from the work item's type and then never used, so every type rendered every phase
        # while each caption promised otherwise (2026-10-06). An epic plans, a task builds, a
        # defect repairs.
        specs_data = [sp for sp in specs_data if sp["key"] in tier_keys]

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

    def get_permissions(self):
        # Bugs S.No 214. A ReadOnlyModelViewSet with two POST actions bolted on — so despite the
        # class name both writes ran under `AllowAny`. Each one reaches into a run somebody else
        # started: takeover ends it terminally, resume re-dispatches work on their branch. Role is
        # checked inside the action, where the run's project is in hand.
        if self.action in {"take_over", "resume", "pause"}:
            return [IsAuthenticatedMember()]
        return super().get_permissions()

    def get_queryset(self):
        from integrations.onboarding import carrier_q

        qs = super().get_queryset()
        work_item = self.request.query_params.get("work_item")
        project = self.request.query_params.get("project")
        # A carrier's run is internal plumbing — the onboarding steps (Index code / Gap report)
        # run headless and report their own progress on the Onboarding hub, so their runs must
        # not surface in Phases & Runs or any project-wide run list. Hiding the carrier work item
        # alone was not enough: this list also filters by `project`, which reached them anyway.
        # Retrieval by id is untouched, so a direct link to a run detail still resolves.
        if self.action == "list":
            qs = qs.exclude(carrier_q("work_item__"))
        if work_item:
            qs = qs.filter(work_item_id=work_item)
        if project:
            qs = qs.filter(work_item__project_id=project)
        return qs

    def list(self, request, *args, **kwargs):
        """Before listing, check whether anything here is stuck and quietly unstick it.

        This is the platform's second line behind worker versioning: a run the UI
        still shows as live whose workflow has already ended cannot move itself,
        and nothing else would ever notice. The check hangs off a read rather
        than a timer because row-level security stops a background job from
        enumerating tenants at all — see `apps.runs.reconcile` for the full
        reasoning. It is bounded (only long-untouched runs, a handful per call)
        and swallows its own errors, so it can never break the list it rides on.
        """
        from apps.runs.reconcile import reconcile_tenant

        reconcile_tenant(
            tenant_id=self.tenant_id,
            project_id=request.query_params.get("project"),
        )
        return super().list(request, *args, **kwargs)

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
        # Layer 2 of S.No 214: this reaches into a run somebody else started. Membership, not a
        # lead role — the person who hit the error is usually the one who resumes it (S.No 157),
        # and making them wait for a tech_lead would defeat the recourse that fix exists to give.
        require_project_member(
            tenant_id=self.tenant_id, project_id=str(run.work_item.project_id),
            user_id=getattr(current_user(request), "id", None),
            what="take over another person's run",
        )
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

    @action(detail=True, methods=["post"], url_path="pause")
    def pause(self, request, pk=None):
        """Stop a run on purpose, to come back to it later — the emergency case ("I have to shut
        this laptop now"), as opposed to the crash case `resume` was built for.

        Resumed through the same `resume` action below: the workflow waits on one signal whether it
        parked at an error or was paused deliberately, which is why there is no second resume here.

        `was_claimed` in the response is what lets the screen tell the truth about timing. A run the
        companion has not picked up yet stops dead; one it is working on stops at the next
        checkpoint, because nothing can interrupt an agent already running on somebody's machine."""
        run = self.get_object()
        # Membership, matching `resume` deliberately. A pause that were harder to undo than to
        # create would let somebody leave a run in a state they cannot get it out of.
        require_project_member(
            tenant_id=self.tenant_id, project_id=str(run.work_item.project_id),
            user_id=getattr(current_user(request), "id", None),
            what="pause a run",
        )
        user = current_user(request)
        try:
            out = pause_run(
                tenant_id=self.tenant_id, run_id=str(run.id),
                paused_by=getattr(user, "name", "") or getattr(user, "email", "") or "a teammate",
            )
        except PauseError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(out)

    @action(detail=True, methods=["post"], url_path="resume")
    def resume(self, request, pk=None):
        """Resume a run parked at an error, from the step that failed (Bugs S.No 157).

        The counterpart to "Take over": takeover ends a parked run terminally, resume continues
        it. Everything already done (the build, the branch, the PR) is kept — only the failed
        step is retried, so the user never re-runs a whole phase because of one error."""
        run = self.get_object()
        # Layer 2 of S.No 214: this reaches into a run somebody else started. Membership, not a
        # lead role — the person who hit the error is usually the one who resumes it (S.No 157),
        # and making them wait for a tech_lead would defeat the recourse that fix exists to give.
        require_project_member(
            tenant_id=self.tenant_id, project_id=str(run.work_item.project_id),
            user_id=getattr(current_user(request), "id", None),
            what="resume a parked run",
        )
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


def _mark_published(artifact, *fields: str) -> None:
    """Mark an artifact published and stamp WHEN (Bugs S.No 224), then save.

    One helper rather than the same two lines at each of the publish action's exits, because
    the thing that is easy to get wrong is the same everywhere: `published_at` is set only on
    the TRANSITION, so a re-export of an already-published artifact keeps the date it was first
    published — which is what "published this week" has to mean, or a re-export would silently
    re-date history into the current week.

    `fields` are the caller's own changed columns (`sor`, `external_ref`).
    """
    if artifact.published_at is None:
        artifact.published_at = timezone.now()
    artifact.status = Artifact.Status.PUBLISHED
    artifact.save(update_fields=["status", "published_at", *fields, "updated_at"])


class ArtifactViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ArtifactSerializer
    queryset = Artifact.objects.all().order_by("-created_at")

    def get_permissions(self):
        # Preview (P4.7-T10) reads a body read-through — any authenticated member.
        # List/retrieve keep the existing pointer-only default.
        # `download` serves a document body as a file, for the same reason `preview` is gated —
        # and the same reason SourceDocumentViewSet gates its raw-bytes actions above.
        if self.action in {"preview", "download"}:
            return [IsAuthenticatedMember()]
        return super().get_permissions()

    #: Query params this list honours. Same idiom as `ApprovalViewSet._FILTERS` right below.
    #:
    #: `run` and `type` are new (N2): a link whose text names one thing must be able to open that
    #: thing, and without a run scope a gate could only ever send the reviewer to the whole
    #: registry to re-find what they were already looking at. `run` is the right scope for
    #: "the artifact under review" precisely because it does NOT require the platform to invent a
    #: notion of a run's *primary* artifact — a UX Design run registers several wireframes, and a
    #: "pick the first" rule would be a new lie in place of the old one.
    #:
    #: Note `phase` matches `Artifact.phase`, which stores the catalog's phase LABEL. An agent key
    #: (`06_task_breakdown`) matches nothing here; the label (`task_breakdown`) is what to send.
    #: `ApprovalSerializer.phase_label` exists so a caller holding an approval has the label.
    _FILTERS = {
        "project": "project_id",
        "phase": "phase",
        "status": "status",
        "type": "type",
        "run": "run_id",
        # An artifact has no direct work-item FK — it is reached through the run that produced
        # it. Named `work_item` so it reads the same as `ApprovalViewSet._FILTERS`, which is the
        # vocabulary the client already uses.
        "work_item": "run__work_item_id",
    }

    def get_queryset(self):
        from integrations.onboarding import RUN_RECORD_ARTIFACT_TYPES

        qs = super().get_queryset()
        # A run's own record is not a project deliverable — see RUN_RECORD_ARTIFACT_TYPES. Without
        # this, every document the vision agent rewrote appeared twice in the registry: the
        # document itself, and the phase blob holding the agent's closing message.
        #
        # Stays BEFORE the filter loop, exactly as before: the exclusion is about what the
        # registry is, not about what this request asked for.
        qs = qs.exclude(type__in=RUN_RECORD_ARTIFACT_TYPES)
        for field, lookup in self._FILTERS.items():
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{lookup: value})
        # `?latest=1` — one row per artifact identity (phase+type+title), newest version only
        # (Part B fix 5). Re-registration is how this platform records a revision: re-running a
        # phase makes v2, and document vision makes v2 of an adopted upload. Listing every row
        # meant 20 uploaded documents showed as 40 entries once vision had read them, which reads
        # as duplication rather than history. Superseded rows are never deleted — they stay
        # readable as prior versions on the artifact's own screen (that is the provenance the
        # registry exists to keep); this only changes what the list shows by default.
        # **`latest` is turned OFF by a run scope, deliberately.** A run-scoped view is a
        # PROVENANCE view — "what did this run produce" — where v1 belongs; collapsing to the
        # newest version there would hide the very row a deep link was pointing at whenever a
        # later run superseded it, which is the silent-empty-list failure this work exists to
        # remove. The unscoped registry is unchanged.
        if (self.request.query_params.get("latest") in ("1", "true", "yes")
                and not self.request.query_params.get("run")):
            newest = (
                qs.order_by("phase", "type", "title", "-version", "-created_at")
                .distinct("phase", "type", "title")
                .values_list("id", flat=True)
            )
            qs = qs.filter(id__in=list(newest))
        return qs

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        """S-29: read-through body (S3 draft/snapshot or SoR), never an editor, never
        copied into the registry (#1/#3). `404` when there's truly no body to show.

        `?raw=1` returns the stored body untouched, skipping the presentation layer that
        renders a machine-readable artifact (an SBOM) into something readable. That is what
        the preview screen's "View raw" control fetches — the raw file is kept, and this is
        how a person can actually see it (Bugs S.No 187). A second request rather than a
        second field on every payload, so an ordinary preview never carries the body twice.
        """
        artifact = self.get_object()
        raw = str(request.query_params.get("raw", "")).lower() in {"1", "true", "yes"}
        # `get_object` has already answered 404 for an artifact that doesn't exist or isn't
        # visible here. What remains is an artifact that exists, so a missing body comes back as
        # a normal answer with an empty `body` and the screen says "Preview unavailable" — the
        # true thing — instead of a 404 worded as though the document were gone (S.No 218).
        result = read_artifact_preview(
            tenant_id=self.tenant_id, artifact_id=str(artifact.id), raw=raw, allow_empty=True)
        if result is None:
            raise NotFound("This document has nothing to preview yet.")
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Hand this artifact's body over as a file, named after the document.

        **This is not Export.** Export (`publish`, below) pushes the document INTO Confluence or
        Jira — a gated write to a system of record. This reads a body and streams it: it writes
        nothing, records no export, touches no gate and changes no status. A test asserts exactly
        that, because the two controls sit a few pixels apart on the registry and the whole reason
        this endpoint exists is that people were clicking Export to get a copy.

        `raw=True` is load-bearing. The preview layer renders some machine-readable artifacts into
        something readable — an SBOM becomes a table — and a file called `SBOM-v1.json` must
        contain the SBOM, not a picture of it.
        """
        artifact = self.get_object()
        if not artifact_is_downloadable(artifact):
            # The button is hidden for these, so this is a deep link or a stale page. Name the
            # place the real copy lives rather than refusing flatly.
            raise NotFound(
                "This row points at a document kept somewhere else, so there is no file here to "
                "download. Open it with Preview to follow the link to it."
            )
        result = read_artifact_preview(
            tenant_id=self.tenant_id, artifact_id=str(artifact.id), raw=True, allow_empty=True)
        body = (result or {}).get("body") or ""
        if not body:
            # Never save an empty file. `_s3_body` degrades a missing or unreadable object to an
            # empty string by design (it is best-effort for the preview screen, which can say
            # "Preview unavailable"), and a download has no way to say that — it would just write
            # a 0-byte file named after the document, which reads as "the document is empty".
            raise NotFound(
                "That document has no content stored yet, so there is nothing to download."
            )
        content_type = (result or {}).get("content_type") or "text/markdown"
        return attachment_response(
            body.encode("utf-8"),
            filename=artifact_filename(artifact, content_type=content_type),
            # The charset matters: without it a browser guesses, and a document with an em dash in
            # it is where that guess shows up.
            content_type=f"{content_type}; charset=utf-8",
        )

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
            # Screen Words group 2: this sentence reaches a person, so it names the status in
            # the same words the Artifacts list and the publish screen use, not the stored key.
            from apps.labels import artifact_status_label

            raise ValidationError(
                "This document can't be published yet — it is "
                f"{artifact_status_label(artifact.status).lower()}. "
                "Publishing is possible once its gate is approved."
            )
        target_capability = request.data.get("target_capability", "internal")
        destination = request.data.get("destination", "")
        # Legacy/vendor spelling: "confluence" is the docstore capability (#9 — the API
        # speaks capabilities; the vendor is whatever connector is bound).
        if target_capability == "confluence":
            target_capability = "docstore"

        if target_capability == "internal":
            _mark_published(artifact)
            return Response({"status": "published", "sor_link": None})

        # Phase-scoped export policy (defaults + ProjectProfile overrides).
        profile = getattr(artifact.project, "profile", None)
        allowed = export_target_for(profile, artifact.phase)
        if target_capability != allowed:
            # Screen Words group 2: the phase and both capabilities get their own names. A
            # client reading this cannot act on "docstore" or "06_task_breakdown".
            from apps.labels import capability_label, phase_label

            where = phase_label(artifact.phase) or "this phase"
            allowed_text = (
                f"only to {capability_label(allowed)}" if allowed
                else "inside the platform only"
            )
            raise ValidationError(
                f"{where} documents can be published {allowed_text}, so they can't go to "
                f"{capability_label(target_capability)}. A Tech Lead can change this in the "
                "project profile's export policy."
            )

        # Body via the same read-through the preview uses (own S3 draft → inline draft →
        # the run's staged/reported body) — never stored back on the row (#1/#3).
        preview = read_artifact_preview(
            tenant_id=self.tenant_id, artifact_id=str(artifact.id))
        body_md = (preview or {}).get("body") or ""

        # S.No 317. The read-through falls back to the RUN's own report when a document has no
        # content of its own. On screen that is tolerable once it says so; pushed to a system of
        # record it is not. It would file one document's content under another document's name,
        # in the client's own Confluence or Jira, where our screens cannot add the caveat and
        # where whoever reads it next has no way to know. Refuse, and say what would fix it.
        if (preview or {}).get("body_from_run"):
            raise ValidationError(
                "This document has no content of its own — what you can see is the report from "
                "the run that created it. Publishing it would file that report under this "
                "document's name. Run the phase again to produce the document, then publish it."
            )

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
                _mark_published(artifact)
                return Response({"status": "published", "sor_link": None})
            # Re-export of an already-published-internal artifact: succeeding without an
            # actual push would be a no-op lie — fail honestly with guidance.
            raise ValidationError(str(exc)) from exc
        raise ValidationError("Documents can't be published to that destination.")

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
        artifact.sor = ref.sor
        artifact.external_ref = {
            "sor": ref.sor, "id": ref.id, "url": ref.url, "version": ref.version,
        }
        _mark_published(artifact, "sor", "external_ref")
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
        artifact.external_ref = {
            **(artifact.external_ref or {}),
            "export": {"sor": "jira", "reconciled": result["reconciled"],
                       "created": result["created"],
                       "skipped": result.get("skipped", 0), "failed": len(failed)},
        }
        _mark_published(artifact, "external_ref")
        return Response({
            # A partial push is not a clean success — say so honestly (Bugs S.No 143) so the UI can
            # warn instead of showing an all-green "Published" while items silently didn't land.
            "status": "partial" if failed else "published",
            "sor_link": next((i["url"] for i in items if i["url"]), None),
            # `reconciled` now counts items already in the tracker too, because they are re-checked
            # rather than filtered out (Bugs S.No 236/237) — `skipped` says how many were left
            # alone, so "12 reconciled" can never read as "12 pushed" when only 2 were.
            "reconciled": result["reconciled"], "created": result["created"],
            "skipped": result.get("skipped", 0),
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
                "Only test cases can be published to test management; "
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
        artifact.external_ref = {
            **(artifact.external_ref or {}),
            "export": {"sor": ref.sor, "id": ref.id, "url": ref.url},
        }
        _mark_published(artifact, "external_ref")
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
        # `project_id`/`work_item_id` join the filterable set with the columns themselves
        # (S.No 230). A filter name this list does not know is applied to nothing and returns
        # everything, which reads as "the filter did not work" rather than as an error — so a
        # new column that is never added here is a silently ignored query parameter.
        for field in ("actor", "action", "target_type", "target_id", "project_id",
                      "work_item_id"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        return qs


# ── Approvals + gate decision ───────────────────────────────────────
class ApprovalViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ApprovalSerializer
    queryset = Approval.objects.all().order_by("-created_at")
    # Opt-in: only a caller that passes ?page= gets an envelope. Every existing caller keeps
    # the bare array it has always received. See api/pagination.py.
    pagination_class = OptInPageNumberPagination

    #: query param -> ORM lookup. `phase` is the run's agent key (the same value the serializer
    #: exposes as `phase`), and `project` scopes through the work item — both needed by the
    #: decided-gate history, which spans months of gates across every phase of a project.
    _FILTERS = {
        "decision": "decision",
        "run": "run_id",
        "work_item": "work_item_id",
        "phase": "run__agent_spec__key",
        "project": "work_item__project_id",
    }

    def get_queryset(self):
        qs = super().get_queryset()
        # `project` filters server-side (Gates screen). The client used to fetch every approval and
        # keep only those whose work item appeared in the work-item LIST — but that list hides
        # carrier work items by design, so the onboarding gate was silently dropped: the sidebar
        # badge counted 1 (the dashboard doesn't cross-filter) while the page said "No gates need
        # you". A gate nobody can reach is worse than no gate, because the run sits waiting.
        for field, lookup in self._FILTERS.items():
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{lookup: value})
        # Bugs S.No 88 — before answering, notice any merge gate whose pull request was already
        # merged on GitHub. The webhook is the fast path but is not a guarantee (a delivery can
        # be missed, and a failed one is never redelivered), and no webhook fires retroactively
        # for a merge that happened before any of this existed.
        #
        # Deliberately hung off THIS read rather than registered in the run-list reconciler:
        # every candidate costs a network call to the code host, so the cost belongs on the
        # screen that wants the answer. Age-gated to an hour and capped at three per pass, so a
        # reviewer who is simply still thinking about a gate is never probed. Never raises.
        from apps.gates.reconcile import sweep

        sweep(self.tenant_id)
        return qs.select_related("approver", "work_item", "run", "run__agent_spec")

    @action(detail=True, methods=["get"])
    def criteria(self, request, pk=None):
        """S-22 generalized criteria-gate checklist (DECISION-6): exposes the approval's
        conditions as typed GateCriterion objects with computed approve_enabled.

        Read through `current_conditions` rather than straight off the column (S.No 178): a
        platform-evaluated rule is seeded unsatisfied and recomputed only at decide time, so the
        stored column shows every one of them as blocking even when nothing is — which greys out
        Approve on a gate the platform would happily let through. This shows the reviewer what is
        actually true, and it is what the decide path enforces."""
        from apps.gates.services import current_conditions

        approval = self.get_object()
        raw = current_conditions(approval, tenant_id=self.tenant_id)
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
            raise ValidationError({"user_id": "Sign in to do this."})
        try:
            result = decide_gate(
                tenant_id=self.tenant_id,
                approval_id=str(approval.id),
                user_id=user_id,
                decision=ser.validated_data["decision"],
                comment=ser.validated_data["comment"],
                conditions=ser.validated_data.get("conditions"),
                revise=ser.validated_data.get("revise", False),
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
            raise ValidationError({"user_id": "Sign in to do this."})
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
    # Opt-in: only a caller that passes ?page= gets an envelope. See api/pagination.py.
    pagination_class = OptInPageNumberPagination

    #: query param -> ORM lookup. `phase` and `project` serve the clarifications history, which
    #: spans every phase of every work item in a project; without `project` the client has to
    #: fetch the tenant's whole history and filter it in the browser.
    _FILTERS = {
        "status": "status",
        "run": "run_id",
        "work_item": "work_item_id",
        "phase": "phase",
        "project": "work_item__project_id",
    }

    def get_queryset(self):
        qs = super().get_queryset()
        for field, lookup in self._FILTERS.items():
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{lookup: value})
        # Free-text search across the questions, the answers and the agent's reason for asking.
        # Server-side on purpose: the history is paged, so searching in the browser would search
        # only the 25 rows on screen while appearing to search everything — which is worse than
        # having no search, because it answers "not found" without having looked.
        # `questions`/`answers` are JSONB, so cast to text and match a substring: crude, but it
        # searches question text, option lists and answers in one pass without a search index.
        search = (self.request.query_params.get("q") or "").strip()
        if search:
            qs = qs.annotate(
                _questions_text=Cast("questions", TextField()),
                _answers_text=Cast("answers", TextField()),
            ).filter(
                Q(_questions_text__icontains=search)
                | Q(_answers_text__icontains=search)
                | Q(context__icontains=search)
            )
        return qs.select_related("answered_by", "work_item", "run")

    @action(detail=True, methods=["post"])
    def answer(self, request, pk=None):
        """Answer a pending clarification: project-membership check → required-answer check
        → record. The blocked agent resumes in the same session."""
        clarification = self.get_object()
        ser = ClarificationAnswerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user_id = resolve_actor(request, ser.validated_data.get("user_id"))
        if user_id is None:
            raise ValidationError({"user_id": "Sign in to do this."})
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

# Tier bucket membership — derived from ACTIVE_AGENT_CATALOG so it never drifts.
# Plan  : onboarding/context phases (00_*) + strategy phases (01_–04_).
# Build : implementation, quality, ops phases (05_–12_).
# Remediation: reserved (none in current catalog — defect/hotfix phases added later).
# Was parsed from each key's leading digits here; now named in the catalog beside the agents
# themselves, because the same question is asked by the lifecycle rail and the two answers had
# already drifted. The prefix rule also mis-filed UX Design and Task Breakdown as build work —
# see the note on PLAN_PHASE_KEYS.
_PLAN_KEYS = PLAN_PHASE_KEYS
_BUILD_KEYS = BUILD_PHASE_KEYS


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
