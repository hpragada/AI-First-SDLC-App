"""API routes (P0-T11). Collection viewsets via a router; tenant-create is a plain
APIView (it runs before any tenant context exists)."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .runner_views import (
    RunnerBuildFetchView,
    RunnerBuildReportView,
    RunnerEnrollmentView,
    RunnerRevokeView,
    RunnerStateView,
)
from .views import (
    ApprovalViewSet,
    ArtifactViewSet,
    EventViewSet,
    ProjectViewSet,
    RunViewSet,
    SourceDocumentViewSet,
    TenantCreateView,
    TraceEdgeViewSet,
    WorkItemViewSet,
)

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("work-items", WorkItemViewSet, basename="workitem")
router.register("runs", RunViewSet, basename="run")
router.register("artifacts", ArtifactViewSet, basename="artifact")
router.register("trace-edges", TraceEdgeViewSet, basename="traceedge")
router.register("events", EventViewSet, basename="event")
router.register("approvals", ApprovalViewSet, basename="approval")
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
    path("", include(router.urls)),
]
