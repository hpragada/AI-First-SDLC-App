from django.apps import AppConfig


class QualityConfig(AppConfig):
    """Test/Quality plane (Phase 3): test executions, flaky quarantine, preview envs."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.quality"
