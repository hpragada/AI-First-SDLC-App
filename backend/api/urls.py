"""API routes (P0-T11). Collection viewsets via a router; tenant-create is a plain
APIView (it runs before any tenant context exists)."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .runner_views import (
    RunnerBuildFetchView,
    RunnerBuildReportView,
    RunnerClarificationCreateView,
    RunnerClarificationPollView,
    RunnerEnrollmentView,
    RunnerRevokeView,
    RunnerStateView,
)
from .views import (
    ApprovalViewSet,
    ArtifactViewSet,
    ClarificationViewSet,
    EventViewSet,
    ProjectViewSet,
    RunViewSet,
    SourceDocumentViewSet,
    TenantCreateView,
    TraceEdgeViewSet,
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

urlpatterns = [
    path("tenants/", TenantCreateView.as_view(), name="tenant-create"),
    # Local-companion runner (Phase 2): enrollment (tenant-scoped) + remote Platform-State.
    path("runners/", RunnerEnrollmentView.as_view(), name="runner-enroll"),
    path("runners/<uuid:pk>/revoke/", RunnerRevokeView.as_view(), name="runner-revoke"),
    path("runner/state/<str:tool>/", RunnerStateView.as_view(), name="runner-state"),
    path("runner/builds/<uuid:run_id>/", RunnerBuildFetchView.as_view(), name="runner-build-fetch"),
    path("runner/builds/<uuid:run_id>/report/", RunnerBuildReportView.as_view(),
         name="runner-build-report"),
    # Interactive Q&A (req #2): an agent opens a clarification + the companion polls it.
    path("runner/clarifications/", RunnerClarificationCreateView.as_view(),
         name="runner-clarification-create"),
    path("runner/clarifications/<uuid:clarification_id>/", RunnerClarificationPollView.as_view(),
         name="runner-clarification-poll"),
    # Signed Git-webhook ingestion (Phase 2 §7) — tenant in the path, signature-authenticated.
    path("webhooks/github/<uuid:tenant_id>/", GithubWebhookView.as_view(), name="github-webhook"),
    path("", include(router.urls)),
]
