"""Root URL config. The Phase-0 REST surface (P0-T11) is mounted under /api/."""
from django.contrib import admin
from django.http import HttpRequest, JsonResponse
from django.urls import include, path


def health(_request: HttpRequest) -> JsonResponse:
    """Liveness probe — intentionally DB-free so it works before RLS role exists."""
    return JsonResponse({"status": "ok", "service": "sdlc-platform-backend"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/", include("api.urls")),
]
