from django.apps import AppConfig


class RegistryConfig(AppConfig):
    """Artifact Registry + AgentSpec + TraceEdges (pointers, not bodies — #3)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.registry"
