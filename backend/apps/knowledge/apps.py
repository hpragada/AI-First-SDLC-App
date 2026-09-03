from django.apps import AppConfig


class KnowledgeConfig(AppConfig):
    """The Knowledge Index (Phase 4): chunk-level retrieval over registered artifacts +
    code-intel, with a no-cost BM25 baseline and an optional embedding-provider seam."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.knowledge"
