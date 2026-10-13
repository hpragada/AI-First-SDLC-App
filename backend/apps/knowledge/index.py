"""Knowledge Index population + retrieval (Phase 4 §2 / D3).

`index_artifact` chunks a body and stores `KnowledgeChunk` rows (embedding only if a provider
is configured). `retrieve` ranks chunks for a query with an **always-on BM25 baseline** (zero
cost, no keys); when chunks carry embeddings it **blends** vector cosine via reciprocal-rank
fusion. Tenant-scoped throughout (RLS + explicit `tenant_id`).
"""
from __future__ import annotations

import math
import re
from collections import Counter

from apps.tenancy.context import tenant_context

_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "is", "it", "for", "on", "with",
         "this", "that", "as", "by", "be", "are", "at", "from"}
_K1, _B = 1.5, 0.75


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"\W+", text.lower()) if len(t) > 1 and t not in _STOP]


def chunk_text(text: str, *, max_chars: int = 1200) -> list[str]:
    """Pack paragraphs into ~max_chars chunks (keeps related lines together)."""
    chunks, buf, size = [], [], 0
    for para in re.split(r"\n\s*\n", text.strip()):
        para = para.strip()
        if not para:
            continue
        if size + len(para) > max_chars and buf:
            chunks.append("\n\n".join(buf))
            buf, size = [], 0
        buf.append(para)
        size += len(para) + 2
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks or ([text.strip()] if text.strip() else [])


def index_artifact(*, tenant_id, project_id, artifact_id, text, repo_id=None,
                   source="artifact", provider=None) -> int:
    """Chunk + (re)index an artifact's body. Idempotent: replaces the artifact's chunks."""
    from .embeddings import get_embedding_provider
    from .models import KnowledgeChunk

    provider = provider or get_embedding_provider()
    pieces = chunk_text(text)
    vectors = []
    if getattr(provider, "dim", 0):
        try:
            vectors = provider.embed(pieces, kind="document")
        except Exception:  # noqa: BLE001 — embeddings are optional; baseline still indexes
            vectors = []

    with tenant_context(tenant_id):
        KnowledgeChunk.objects.filter(
            tenant_id=tenant_id, artifact_id=artifact_id).delete()       # re-index cleanly
        rows = []
        for i, piece in enumerate(pieces):
            rows.append(KnowledgeChunk(
                tenant_id=tenant_id, project_id=project_id, artifact_id=artifact_id,
                repo_id=repo_id, ordinal=i, text=piece, token_count=len(_tokens(piece)),
                source=source, embedding=(vectors[i] if i < len(vectors) else None),
            ))
        KnowledgeChunk.objects.bulk_create(rows)
    return len(rows)


def _bm25(query_terms, docs: list[tuple]) -> dict:
    """docs: [(id, tokens)]. Returns {id: score} (Robertson/Sparck-Jones BM25)."""
    n = len(docs)
    if not n:
        return {}
    avg_len = sum(len(toks) for _id, toks in docs) / n
    df = Counter()
    for _id, toks in docs:
        for t in set(toks):
            df[t] += 1
    scores = {}
    for cid, toks in docs:
        tf = Counter(toks)
        dl = len(toks) or 1
        s = 0.0
        for t in set(query_terms):
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * (tf[t] * (_K1 + 1)) / (tf[t] + _K1 * (1 - _B + _B * dl / avg_len))
        scores[cid] = s
    return scores


def _cosine(a, b) -> float:
    if a is None or b is None:
        return 0.0
    a = list(a)
    b = list(b)
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def retrieve(tenant_id, *, project_id, query, repo=None, k=8, provider=None) -> list[dict]:
    """Top-k chunks for a query. BM25 baseline always; embedding cosine blended (reciprocal
    rank fusion) when both the chunks and an embedding provider supply vectors."""
    from .embeddings import get_embedding_provider
    from .models import KnowledgeChunk

    with tenant_context(tenant_id):
        qs = KnowledgeChunk.objects.filter(tenant_id=tenant_id, project_id=project_id)
        if repo is not None:
            qs = qs.filter(repo_id=repo)
        chunks = list(qs)
    if not chunks:
        return []

    q_terms = _tokens(query)
    bm = _bm25(q_terms, [(c.id, _tokens(c.text)) for c in chunks])
    ranked = sorted(chunks, key=lambda c: bm.get(c.id, 0.0), reverse=True)
    rank_pos = {c.id: i for i, c in enumerate(ranked)}
    fused = {c.id: 1.0 / (60 + rank_pos[c.id]) for c in chunks if bm.get(c.id, 0.0) > 0}

    provider = provider or get_embedding_provider()
    if getattr(provider, "dim", 0) and any(c.embedding is not None for c in chunks):
        try:
            qvec = provider.embed([query], kind="query")
        except Exception:  # noqa: BLE001
            qvec = []
        if qvec:
            cos = sorted(chunks, key=lambda c: _cosine(c.embedding, qvec[0]), reverse=True)
            for i, c in enumerate(cos):
                if _cosine(c.embedding, qvec[0]) > 0:
                    fused[c.id] = fused.get(c.id, 0.0) + 1.0 / (60 + i)

    top = sorted(chunks, key=lambda c: fused.get(c.id, 0.0), reverse=True)
    top = [c for c in top if fused.get(c.id, 0.0) > 0][:k]
    # `token_count` has been stored at index time since this module was written and was dropped
    # on the way out, so the composer had to re-estimate a size the database already knew. It is
    # carried now because the manifest budget sizes this section from it (truncation register T3).
    return [{"text": c.text, "artifact_id": str(c.artifact_id) if c.artifact_id else None,
             "repo_id": str(c.repo_id) if c.repo_id else None,
             "source": c.source, "score": round(fused[c.id], 6),
             "token_count": c.token_count} for c in top]
