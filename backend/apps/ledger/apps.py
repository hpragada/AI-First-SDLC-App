from django.apps import AppConfig


class LedgerConfig(AppConfig):
    """Append-only Event ledger (provenance/events — #3)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ledger"
