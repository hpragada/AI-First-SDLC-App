from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    """IntegrationConnection — capability connectors (capabilities not vendors — #9)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations"
