"""P0-T2 smoke tests: the Django/DRF/ASGI spine boots and serves.

Intentionally DB-free — the RLS app role and models arrive in P0-T3/T4.
"""
from django.apps import apps as django_apps


def test_health_endpoint(client):
    resp = client.get("/api/health/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "sdlc-platform-backend"}


def test_all_platform_apps_loaded():
    expected = {
        "tenancy", "projects", "workitems", "registry",
        "ledger", "runs", "gates", "integrations",
    }
    loaded = {cfg.label for cfg in django_apps.get_app_configs()}
    assert expected <= loaded


def test_drf_and_asgi_wired():
    # DRF installed
    assert django_apps.is_installed("rest_framework")
    # ASGI application importable
    from config.asgi import application
    assert application is not None
