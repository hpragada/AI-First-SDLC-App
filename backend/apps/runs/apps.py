from django.apps import AppConfig


class RunsConfig(AppConfig):
    """Agent Runs (each = a Temporal workflow — #8)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.runs"
