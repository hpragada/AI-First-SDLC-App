from django.apps import AppConfig


class GatesConfig(AppConfig):
    """Approvals — control-plane gates (never in engine hooks — #2, #5)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.gates"
