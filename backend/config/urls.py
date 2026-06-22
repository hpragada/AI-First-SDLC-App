"""Root URL config. App routers are added as their REST surfaces land (P0-T11)."""
from django.contrib import admin
from django.http import HttpRequest, JsonResponse
from django.urls import path


def health(_request: HttpRequest) -> JsonResponse:
    """Liveness probe — intentionally DB-free so it works before RLS role exists."""
    return JsonResponse({"status": "ok", "service": "sdlc-platform-backend"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
]
