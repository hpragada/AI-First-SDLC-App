from django.apps import AppConfig


class WorkitemsConfig(AppConfig):
    """WorkItem DAG — the unit of work (non-negotiable #4)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workitems"
