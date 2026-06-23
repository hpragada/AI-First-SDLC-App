"""API routes (P0-T11). Collection viewsets via a router; tenant-create is a plain
APIView (it runs before any tenant context exists)."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ApprovalViewSet,
    ArtifactViewSet,
    EventViewSet,
    ProjectViewSet,
    RunViewSet,
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

urlpatterns = [
    path("tenants/", TenantCreateView.as_view(), name="tenant-create"),
    path("", include(router.urls)),
]
