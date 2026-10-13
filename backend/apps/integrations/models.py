"""Integrations: IntegrationConnection — capabilities not vendors (#9). Used Phase 1+."""
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.base import Role, TenantScopedModel


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


# Connectors that need no per-tenant secret (built-in/local — P4.7-T6). Every other
# connector is "configured" only once a secret has been stored.
NO_SECRET_CONNECTORS = {"builtin"}


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
    # Write-only secret store (P4.7-T6, DECISION-4): a Fernet blob (apps.integrations.crypto),
    # never serialized back over the API. Empty string = no secret stored.
    secret_encrypted = models.TextField(blank=True, default="")

    @property
    def is_configured(self) -> bool:
        """Whether this connection has what it needs to be used — a stored secret, or none
        required (e.g. the built-in CodeIntel connector)."""
        return bool(self.secret_encrypted) or self.connector in NO_SECRET_CONNECTORS

    def __str__(self) -> str:
        return f"{self.capability}:{self.connector}"


class WebhookDelivery(TenantScopedModel):
    """Idempotent webhook-ingest ledger (Phase-2 §7). Dedups a provider's redeliveries by
    `delivery_id`; the Event Ledger records the actual reconciliation. The payload body is
    not stored — only what's needed to dedup/route (#3). RLS isolates per tenant."""

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        IGNORED = "ignored", "Ignored"
        FAILED = "failed", "Failed"

    provider = models.CharField(max_length=64)        # "github"
    delivery_id = models.CharField(max_length=255)    # e.g. X-GitHub-Delivery
    event = models.CharField(max_length=128)          # "pull_request" | "push" | "status"
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "delivery_id"],
                name="uniq_tenant_webhook_delivery",
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.event}:{self.delivery_id}"


class DriftRecord(TenantScopedModel):
    """Live drift on a registered artifact (Phase-4 §6 / D6) — the `Approval`-analog for
    **run-less** changes. Opened when an `api_contract` diverges (contract drift) or a SoR
    artifact's external content changed since we indexed it (pointer/hash drift). Carries the
    **change-impact** set computed from the traceability graph, and is decided by a control-
    plane gate (`decide_drift`): **architect** for contract, **tech_lead** for pointer/hash.
    Nothing is silently applied to a system of record — accept reconciles, reject flags revert.
    """

    class Kind(models.TextChoices):
        CONTRACT = "contract", "Contract"
        POINTER_HASH = "pointer_hash", "Pointer/Hash"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="drift_records"
    )
    artifact = models.ForeignKey(
        "registry.Artifact", on_delete=models.CASCADE, related_name="drift_records"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    required_role = models.CharField(max_length=32, choices=Role.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    detail = models.JSONField(default=dict, blank=True)      # hashes / semver / source
    impacted = models.JSONField(default=list, blank=True)    # change-impact (traceability)
    decided_by = models.ForeignKey(
        "tenancy.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"drift:{self.kind}:{self.artifact_id} ({self.status})"
