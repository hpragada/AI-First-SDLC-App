"""P4 — Knowledge Index: chunking, the no-cost BM25 baseline, the optional embedding
blend, RLS isolation, provider selection, and get_context wiring (§2 / D3)."""
import psycopg
import pytest
from django.conf import settings
from django.db import connection
from mcp_platform_state import tools

from apps.knowledge import index
from apps.knowledge.embeddings import (
    GeminiEmbeddings,
    NullEmbeddings,
    get_embedding_provider,
)
from apps.knowledge.models import KnowledgeChunk
from apps.projects.models import Project
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    return t, p


def _artifact(t, p, type_="code_intel"):
    return tools.register_artifact(t.id, p.id, None, "onboarding", type_, "internal", "h")["id"]


# ── chunking ────────────────────────────────────────────────────────
def test_chunk_text_packs_paragraphs():
    text = "\n\n".join([f"para {i} " + "x" * 400 for i in range(5)])
    chunks = index.chunk_text(text, max_chars=1200)
    assert len(chunks) >= 2 and all(c.strip() for c in chunks)


# ── BM25 baseline (no embeddings, no keys) ──────────────────────────
def test_index_and_retrieve_bm25_baseline(world):
    t, p = world
    a1 = _artifact(t, p)
    a2 = _artifact(t, p)
    index.index_artifact(tenant_id=t.id, project_id=p.id, artifact_id=a1,
                         text="The payment service handles refunds and chargebacks.",
                         provider=NullEmbeddings())
    index.index_artifact(tenant_id=t.id, project_id=p.id, artifact_id=a2,
                         text="The notification service sends emails and push alerts.",
                         provider=NullEmbeddings())

    hits = index.retrieve(t.id, project_id=p.id, query="refund payment", provider=NullEmbeddings())
    assert hits and hits[0]["artifact_id"] == a1            # payment chunk ranks first
    assert all(h["score"] > 0 for h in hits)
    # an unrelated query returns nothing from the baseline
    assert index.retrieve(t.id, project_id=p.id, query="kubernetes helm",
                          provider=NullEmbeddings()) == []


def test_index_artifact_is_idempotent(world):
    t, p = world
    a = _artifact(t, p)
    index.index_artifact(tenant_id=t.id, project_id=p.id, artifact_id=a,
                         text="alpha beta gamma", provider=NullEmbeddings())
    index.index_artifact(tenant_id=t.id, project_id=p.id, artifact_id=a,
                         text="delta epsilon", provider=NullEmbeddings())   # re-index replaces
    assert KnowledgeChunk.objects.filter(artifact_id=a).count() == 1
    assert "delta" in KnowledgeChunk.objects.get(artifact_id=a).text


# ── optional embedding blend (deterministic fake provider) ──────────
class _FakeEmb:
    name = "fake"
    dim = settings.EMBEDDING_DIM

    def embed(self, texts, *, kind="document"):
        # one-hot-ish dim-correct vectors: "auth" docs point one way, "billing" another
        out = []
        for s in texts:
            v = [0.0] * self.dim
            v[1] = 1.0 if "auth" in s.lower() else 0.0
            v[2] = 1.0 if "billing" in s.lower() else 0.0
            out.append(v)
        return out


def test_embedding_blend_lifts_semantic_match(world):
    t, p = world
    a = _artifact(t, p)
    fake = _FakeEmb()
    index.index_artifact(tenant_id=t.id, project_id=p.id, artifact_id=a,
                         text="auth login flow\n\nbilling invoice flow", provider=fake)
    rows = KnowledgeChunk.objects.filter(artifact_id=a)
    assert any(r.embedding is not None for r in rows)        # vectors stored
    hits = index.retrieve(t.id, project_id=p.id, query="auth", provider=fake)
    assert hits and "auth" in hits[0]["text"].lower()        # vector + bm25 fuse to the auth chunk


# ── provider selection ──────────────────────────────────────────────
def test_get_embedding_provider_defaults_to_null(settings):
    settings.EMBEDDING_PROVIDER = "null"
    assert isinstance(get_embedding_provider(), NullEmbeddings)


def test_get_embedding_provider_selects_gemini_when_keyed(settings):
    settings.EMBEDDING_PROVIDER = "gemini"
    settings.GEMINI_API_KEY = "k"
    settings.EMBEDDING_DIM = 1536
    prov = get_embedding_provider()
    assert isinstance(prov, GeminiEmbeddings) and prov.dim == 1536


def test_embedding_dim_is_provider_driven():
    assert KnowledgeChunk._meta.get_field("embedding").dimensions == settings.EMBEDDING_DIM


# ── get_context wiring ──────────────────────────────────────────────
def test_get_context_returns_retrieved_knowledge(world):
    t, p = world
    a = _artifact(t, p)
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY,
                                 title="payment refunds", description="handle chargebacks")
    index.index_artifact(tenant_id=t.id, project_id=p.id, artifact_id=a,
                         text="The payment service handles refunds and chargebacks.",
                         provider=NullEmbeddings())
    ctx = tools.get_context(t.id, p.id, phase="implementation", work_item_id=str(wi.id))
    assert ctx["retrieved_knowledge"]
    assert "refund" in ctx["retrieved_knowledge"][0]["text"].lower()


# ── RLS isolation (DB-level, via the app role) ──────────────────────
@pytest.mark.django_db(transaction=True)
def test_rls_isolates_knowledge_chunks():
    a = Tenant.objects.create(name="A")
    b = Tenant.objects.create(name="B")
    pa = Project.objects.create(tenant=a, name="A")
    pb = Project.objects.create(tenant=b, name="B")
    aa = tools.register_artifact(a.id, pa.id, None, "x", "code_intel", "internal", "h")["id"]
    ab = tools.register_artifact(b.id, pb.id, None, "x", "code_intel", "internal", "h")["id"]
    index.index_artifact(tenant_id=a.id, project_id=pa.id, artifact_id=aa, text="alpha",
                         provider=NullEmbeddings())
    index.index_artifact(tenant_id=b.id, project_id=pb.id, artifact_id=ab, text="beta",
                         provider=NullEmbeddings())

    sd = connection.settings_dict
    with connection.cursor() as cur:
        cur.execute("SELECT current_database()")
        dbname = cur.fetchone()[0]
    raw = psycopg.connect(host=sd["HOST"], port=sd["PORT"], dbname=dbname,
                          user=settings.APP_DB_USER, password=settings.APP_DB_PASSWORD,
                          autocommit=True)
    try:
        with raw.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [str(a.id)])
            cur.execute("SELECT count(*) FROM knowledge_knowledgechunk")
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [""])
            cur.execute("SELECT count(*) FROM knowledge_knowledgechunk")
            assert cur.fetchone()[0] == 0          # no tenant context -> fail closed
    finally:
        raw.close()
