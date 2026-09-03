from django.apps import AppConfig


class TenancyConfig(AppConfig):
    """Tenants, users, memberships, RLS tenant context."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenancy"
