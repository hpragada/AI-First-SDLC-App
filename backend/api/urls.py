"""API routes (P0-T11). Collection viewsets via a router; tenant-create is a plain
APIView (it runs before any tenant context exists)."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .auth_views import (
    AcceptInvitationView,
    InvitationPreviewView,
    LoginView,
    LogoutView,
    MeView,
    RequestResetView,
    ResetView,
    SignupView,
)
from .ci_views import CIA11yCandidatesView, CITestResultsView
from .runner_views import (
    RunnerA11yAuditClaimView,
    RunnerBuildFetchView,
    RunnerBuildReportView,
    RunnerClarificationCreateView,
    RunnerClarificationPollView,
    RunnerCodeIntelClaimView,
    RunnerCodeIntelReportView,
    RunnerEnrollmentView,
    RunnerHeartbeatView,
    RunnerPhaseFetchView,
    RunnerPhaseReportView,
    RunnerReviewReportView,
    RunnerLastDisconnectView,
    RunnerRevokeView,
    RunnerStateView,
    RunnerWorkClaimView,
)
from .views import (
    ApprovalViewSet,
    ArtifactViewSet,
    ClarificationViewSet,
    DriftRecordViewSet,
    EventViewSet,
    IntegrationViewSet,
    InvitationViewSet,
    PhaseCatalogView,
    ProjectViewSet,
    RunViewSet,
    SourceDocumentViewSet,
    TenantCreateView,
    TraceEdgeViewSet,
    UserViewSet,
    WorkItemViewSet,
)
from .webhook_views import GithubWebhookView

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("work-items", WorkItemViewSet, basename="workitem")
router.register("runs", RunViewSet, basename="run")
router.register("artifacts", ArtifactViewSet, basename="artifact")
router.register("trace-edges", TraceEdgeViewSet, basename="traceedge")
router.register("events", EventViewSet, basename="event")
router.register("approvals", ApprovalViewSet, basename="approval")
router.register("clarifications", ClarificationViewSet, basename="clarification")
router.register("source-documents", SourceDocumentViewSet, basename="sourcedocument")
router.register("invitations", InvitationViewSet, basename="invitation")
router.register("users", UserViewSet, basename="user")
router.register("integrations", IntegrationViewSet, basename="integration")
router.register("drift", DriftRecordViewSet, basename="drift")

urlpatterns = [
    path("tenants/", TenantCreateView.as_view(), name="tenant-create"),
    # CI results ingestion (P3-09bX-3): CI-token authenticated, project-scoped. Explicit path
    # (before the router include) so it wins over the projects viewset, and its non-session auth
    # stays isolated from the session-authed project actions.
    path("projects/<uuid:project_id>/test-results/", CITestResultsView.as_view(),
         name="ci-test-results"),
    # Accessibility capture ingestion (QA-11b): the same CI-token front door, for what a run
    # saw on each screen. Explicit path before the router include, for the same reason.
    path("projects/<uuid:project_id>/a11y-candidates/", CIA11yCandidatesView.as_view(),
         name="ci-a11y-candidates"),
    # Phase catalog (S-18 trigger picker, gap C): tenant-scoped via session / header.
    path("phases/", PhaseCatalogView.as_view(), name="phases"),
    # Server-session auth (P4.7-T1, DECISION-3). Tenant is resolved from the session
    # user by TenantContextMiddleware; the runner-token path is untouched.
    path("auth/signup/", SignupView.as_view(), name="auth-signup"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    # Invitation preview + accept + password reset (P4.7-T3) — public, pre-auth (CSRF-exempt).
    path("auth/invitations/preview/", InvitationPreviewView.as_view(),
         name="auth-invitation-preview"),
    path("auth/accept-invitation/", AcceptInvitationView.as_view(), name="auth-accept-invitation"),
    path("auth/request-reset/", RequestResetView.as_view(), name="auth-request-reset"),
    path("auth/reset/", ResetView.as_view(), name="auth-reset"),
    # Local-companion runner (Phase 2): enrollment (tenant-scoped) + remote Platform-State.
    path("runners/", RunnerEnrollmentView.as_view(), name="runner-enroll"),
    path("runners/<uuid:pk>/revoke/", RunnerRevokeView.as_view(), name="runner-revoke"),
    path("runners/last-disconnect/", RunnerLastDisconnectView.as_view(), name="runner-last-disconnect"),
    path("runner/state/<str:tool>/", RunnerStateView.as_view(), name="runner-state"),
    path("runner/builds/<uuid:run_id>/", RunnerBuildFetchView.as_view(), name="runner-build-fetch"),
    path("runner/builds/<uuid:run_id>/report/", RunnerBuildReportView.as_view(),
         name="runner-build-report"),
    # Interactive Q&A (req #2): an agent opens a clarification + the companion polls it.
    path("runner/clarifications/", RunnerClarificationCreateView.as_view(),
         name="runner-clarification-create"),
    path("runner/clarifications/<uuid:clarification_id>/", RunnerClarificationPollView.as_view(),
         name="runner-clarification-poll"),
    # Companion liveness: a cheap keep-alive so the companion stays "online" while it is busy
    # running a phase and not polling /work/ (RC-2).
    path("runner/heartbeat/", RunnerHeartbeatView.as_view(), name="runner-heartbeat"),
    # Companion phase execution (req #1): claim work, fetch the phase task, report the result.
    path("runner/work/", RunnerWorkClaimView.as_view(), name="runner-work-claim"),
    path("runner/phases/<uuid:run_id>/", RunnerPhaseFetchView.as_view(),
         name="runner-phase-fetch"),
    path("runner/phases/<uuid:run_id>/report/", RunnerPhaseReportView.as_view(),
         name="runner-phase-report"),
    path("runner/reviews/<uuid:run_id>/report/", RunnerReviewReportView.as_view(),
         name="runner-review-report"),
    # Code-intelligence dispatch (B4): claim a job + report the analysis (companion-token auth).
    path("runner/a11y-audits/", RunnerA11yAuditClaimView.as_view(), name="runner-a11y-claim"),
    path("runner/code-intel/", RunnerCodeIntelClaimView.as_view(), name="runner-codeintel-claim"),
    path("runner/code-intel/<uuid:job_id>/report/", RunnerCodeIntelReportView.as_view(),
         name="runner-codeintel-report"),
    # Signed Git-webhook ingestion (Phase 2 §7) — tenant in the path, signature-authenticated.
    path("webhooks/github/<uuid:tenant_id>/", GithubWebhookView.as_view(), name="github-webhook"),
    path("", include(router.urls)),
]
