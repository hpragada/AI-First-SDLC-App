"""Integrations: IntegrationConnection — capabilities not vendors (#9). Used Phase 1+."""
from django.db import models

from apps.base import TenantScopedModel


class IntegrationConnection(TenantScopedModel):
    class Health(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        HEALTHY = "healthy", "Healthy"
        DEGRADED = "degraded", "Degraded"
        DOWN = "down", "Down"

    capability = models.CharField(max_length=64)  # e.g. "tasktracker", "docstore"
    connector = models.CharField(max_length=64)  # e.g. "jira", "confluence"
    scopes = models.JSONField(default=dict, blank=True)
    token_ref = models.CharField(max_length=512, blank=True)
    health = models.CharField(
        max_length=16, choices=Health.choices, default=Health.UNKNOWN
    )

    def __str__(self) -> str:
        return f"{self.capability}:{self.connector}"
