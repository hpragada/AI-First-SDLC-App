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
        # A draft whose gate was REJECTED. It is kept (it is the record of what the agent
        # produced, and the revision's manifest cites it by id) but it is no longer the
        # project's answer for its type, so `get_context` stops serving it. Without this a
        # rejected draft was still handed to every downstream phase as authoritative — the
        # reviewer said no and the platform kept passing it on.
        SUPERSEDED = "superseded", "Superseded"

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
    # Human-readable, context-carrying name the phase agent authors at registration
    # (e.g. "Wireframe — Login Page", "ADR-003 — Event Sourcing"). Distinguishes per-item
    # artifacts that share a `type`, and is what every UI surface displays (Bugs S.No 120).
    # Blank falls back to a humanized `type` at the display layer for back-compat.
    title = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    sor = models.CharField(max_length=16, choices=SoR.choices, default=SoR.INTERNAL)
    external_ref = models.JSONField(null=True, blank=True)
    s3_key = models.CharField(max_length=1024, blank=True)
    content_hash = models.CharField(max_length=128, blank=True)
    version = models.IntegerField(default=1)
    # When this artifact was PUBLISHED — as distinct from when it was registered (Bugs S.No 224).
    #
    # The dashboard's "published this week" count and its recent-publishes list both filtered on
    # `created_at`, which is when the agent drafted the thing. Drafting and publishing are
    # separated by a review gate, so they are routinely days apart: something drafted last week
    # and published this morning never appeared in a list of this week's publishes, while
    # something drafted today and never published did. There was no publish timestamp to filter
    # on — `updated_at` is `auto_now` and moves on any later edit, so it cannot stand in.
    #
    # Nullable, and deliberately so: a NOT NULL column with no database-level default breaks a
    # rolling deploy, which is the lesson already written down on `Approval.external_merge`
    # (S.No 185). Null means "not published", which is exactly what it means.
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    embedding = VectorField(dimensions=EMBEDDING_DIM, null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.title or self.type}#{self.version} ({self.status})"


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
