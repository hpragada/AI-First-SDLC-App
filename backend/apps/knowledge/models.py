"""Knowledge Index store (Phase 4 §2/§3) — chunk-level, RLS-aware (#6).

A `KnowledgeChunk` is a retrievable slice of a registered artifact's body (or code-intel
output) — a pointer/index entry, never the artifact's authoritative content (#1/#3). The
embedding column is optional and its dimension is **provider-driven** (`settings.EMBEDDING_DIM`,
default 1536 for Gemini; 1024 for Voyage requires re-migrating). Retrieval works with zero
embeddings via the BM25 baseline; embeddings only sharpen ranking.
"""
from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from apps.base import TenantScopedModel


class KnowledgeChunk(TenantScopedModel):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="knowledge_chunks"
    )
    artifact = models.ForeignKey(
        "registry.Artifact", null=True, blank=True, on_delete=models.CASCADE,
        related_name="chunks",
    )
    repo = models.ForeignKey(
        "projects.Repository", null=True, blank=True, on_delete=models.SET_NULL
    )
    ordinal = models.IntegerField(default=0)
    text = models.TextField()
    token_count = models.IntegerField(default=0)
    source = models.CharField(max_length=64, blank=True)        # "artifact" | "code_intel" | ...
    embedding = VectorField(dimensions=settings.EMBEDDING_DIM, null=True, blank=True)

    def __str__(self) -> str:
        return f"chunk:{self.artifact_id}#{self.ordinal}"
