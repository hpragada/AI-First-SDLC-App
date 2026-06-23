"""Integrations: IntegrationConnection — capabilities not vendors (#9). Used Phase 1+."""
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.base import TenantScopedModel


class SourceDocument(TenantScopedModel):
    """An uploaded static file (Word/Excel/PDF) for brownfield-lite onboarding (B4).
    Extracted into internal artifacts (provenance kept), then adopted via a review gate."""

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        EXTRACTING = "extracting", "Extracting"
        EXTRACTED = "extracted", "Extracted"   # artifacts drafted, awaiting review
        ADOPTED = "adopted", "Adopted"          # review gate passed → published
        FAILED = "failed", "Failed"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="source_documents"
    )
    filename = models.CharField(max_length=512)
    mime = models.CharField(max_length=128)
    s3_key = models.CharField(max_length=1024, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UPLOADED)
    extracted_artifact_ids = ArrayField(models.UUIDField(), default=list, blank=True)
    provenance = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"{self.filename} ({self.status})"


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
