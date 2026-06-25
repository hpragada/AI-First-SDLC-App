"""EmbeddingProvider seam (Phase 4 §2 / D3).

The Knowledge Index works with **zero embeddings** (the BM25 baseline). When a provider is
configured it sharpens ranking. Two real adapters — **Voyage** (`voyage-code-3`, dim 1024;
best for code) and **Gemini** (`gemini-embedding-001`, dim 1536; fits the default column) —
plus a Null default. `EMBEDDING_DIM` is provider-driven; switching a provider whose dim
differs from the column requires re-migrating (documented).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from integrations.transport import default_transport
from integrations.types import CapabilityError


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str], *, kind: str = "document") -> list[list[float]]: ...


class NullEmbeddings:
    """No embeddings — the BM25 baseline carries retrieval. The zero-cost default."""

    name = "null"
    dim = 0

    def embed(self, texts: list[str], *, kind: str = "document") -> list[list[float]]:
        return []


class VoyageEmbeddings:
    """voyage-code-3 (code-optimized, dim 1024). Needs VOYAGE_API_KEY; rate-limited by Voyage."""

    name = "voyage"

    def __init__(self, *, api_url, api_key, model="voyage-code-3", dim=1024, transport=None):
        self.api_url = api_url.rstrip("/")
        self._key = api_key
        self.model = model
        self.dim = dim
        self._transport = transport or default_transport

    def embed(self, texts: list[str], *, kind: str = "document") -> list[list[float]]:
        if not texts:
            return []
        status, data = self._transport(
            "POST", f"{self.api_url}/v1/embeddings",
            {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
            {"model": self.model, "input": texts,
             "input_type": "query" if kind == "query" else "document"},
        )
        if status >= 400:
            raise CapabilityError(f"Voyage embeddings -> {status}", status=status, detail=data)
        return [row["embedding"] for row in (data or {}).get("data", [])]


class GeminiEmbeddings:
    """gemini-embedding-001 (dim configurable; 1536 fits the default column). Needs a key."""

    name = "gemini"

    def __init__(self, *, api_url, api_key, model="gemini-embedding-001", dim=1536,
                 transport=None):
        self.api_url = api_url.rstrip("/")
        self._key = api_key
        self.model = model
        self.dim = dim
        self._transport = transport or default_transport

    def embed(self, texts: list[str], *, kind: str = "document") -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:                                  # Gemini embeds one content per call
            url = f"{self.api_url}/v1beta/models/{self.model}:embedContent?key={self._key}"
            status, data = self._transport(
                "POST", url, {"Content-Type": "application/json"},
                {"model": f"models/{self.model}",
                 "content": {"parts": [{"text": text}]},
                 "outputDimensionality": self.dim},
            )
            if status >= 400:
                raise CapabilityError(f"Gemini embeddings -> {status}", status=status, detail=data)
            out.append(((data or {}).get("embedding") or {}).get("values", []))
        return out


def get_embedding_provider() -> EmbeddingProvider:
    """Select the configured provider (default Null — baseline-only, zero cost/keys)."""
    from django.conf import settings

    name = (getattr(settings, "EMBEDDING_PROVIDER", "") or "null").lower()
    if name == "voyage" and settings.VOYAGE_API_KEY:
        return VoyageEmbeddings(api_url=settings.VOYAGE_API_URL, api_key=settings.VOYAGE_API_KEY,
                                model=settings.VOYAGE_MODEL, dim=settings.EMBEDDING_DIM)
    if name == "gemini" and settings.GEMINI_API_KEY:
        return GeminiEmbeddings(api_url=settings.GEMINI_API_URL, api_key=settings.GEMINI_API_KEY,
                                model=settings.GEMINI_MODEL, dim=settings.EMBEDDING_DIM)
    return NullEmbeddings()
