"""Registry: AgentSpec, Artifact (pointers not bodies — #3), TraceEdge."""
from django.db import models
from pgvector.django import VectorField

from apps.base import TenantScopedModel

# Embedding dimensionality for the Knowledge Index (pgvector column width).
EMBEDDING_DIM = 1536


class AgentSpec(TenantScopedModel):
    """The migrated-agent registry (body lives in /agents, referenced by body_ref)."""

    key = models.CharField(max_length=64)  # e.g. "03_prd"
    semver = models.CharField(max_length=32, default="1.0.0")
    prompt_version = models.CharField(max_length=64, blank=True)
    body_ref = models.CharField(max_length=512)  # path in /agents
    recommended_engine = models.CharField(max_length=32, default="claude")
    recommended_model = models.CharField(max_length=64, blank=True)
    phase_label = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "key", "semver"], name="uniq_tenant_agentspec_version"
            )
        ]

    def __str__(self) -> str:
        return f"{self.key}@{self.semver}"


class Artifact(TenantScopedModel):
    """Registry entry: pointer + hash + version, never the body (#1, #3)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        STAGED = "staged", "Staged"
        APPROVED = "approved", "Approved"
        PUBLISHED = "published", "Published"

    class SoR(models.TextChoices):
        INTERNAL = "internal", "Internal"
        CONFLUENCE = "confluence", "Confluence"
        JIRA = "jira", "Jira"
        FIGMA = "figma", "Figma"
        XRAY = "xray", "Xray"
        GIT = "git", "Git"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="artifacts"
    )
    repo = models.ForeignKey(
        "projects.Repository", null=True, blank=True, on_delete=models.SET_NULL
    )
    run = models.ForeignKey(
        "runs.Run", null=True, blank=True, on_delete=models.SET_NULL, related_name="artifacts"
    )
    phase = models.CharField(max_length=64)
    type = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    sor = models.CharField(max_length=16, choices=SoR.choices, default=SoR.INTERNAL)
    external_ref = models.JSONField(null=True, blank=True)
    s3_key = models.CharField(max_length=1024, blank=True)
    content_hash = models.CharField(max_length=128, blank=True)
    version = models.IntegerField(default=1)
    embedding = VectorField(dimensions=EMBEDDING_DIM, null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.type}#{self.version} ({self.status})"


class TraceEdge(TenantScopedModel):
    """Provenance edge between artifacts (the traceability DAG)."""

    class Rel(models.TextChoices):
        DERIVES = "derives", "Derives"
        IMPLEMENTS = "implements", "Implements"
        TESTS = "tests", "Tests"
        DEPLOYS = "deploys", "Deploys"

    from_artifact = models.ForeignKey(
        Artifact, on_delete=models.CASCADE, related_name="edges_out"
    )
    to_artifact = models.ForeignKey(
        Artifact, on_delete=models.CASCADE, related_name="edges_in"
    )
    rel = models.CharField(max_length=16, choices=Rel.choices)

    def __str__(self) -> str:
        return f"{self.from_artifact_id}-{self.rel}->{self.to_artifact_id}"
