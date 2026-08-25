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


# ── a result is not knowledge ────────────────────────────────────────
def test_an_accessibility_verdict_is_never_indexed_as_knowledge(world, monkeypatch):
    """The judge must not be able to find its own previous answer in its own briefing.

    **The live failure, 24 August.** Every artifact with a body is indexed when registered, and
    each run's briefing is filled by searching that index for what the run is about. So an
    accessibility judging run searched for accessibility judging knowledge and the best match in
    the whole project was the PREVIOUS accessibility judgement. Its body — findings table, gate
    outcome, per-element verdicts — landed in the briefing of the run whose job was to produce
    that document. Retrieval returned, among the top eight, a verdict about
    `#loans-table > tbody > tr:nth-of-type(3)` — one of the very elements that run had been
    asked to judge.

    That run recorded **zero** verdicts and reported "Gate outcome: PASS — 33 elements, all
    pass", every word lifted from the document it had been handed. The completeness check caught
    it, but a check that catches a fabricated answer is a worse place to be than never inviting
    one. It read as an unreliable model and was not: the same agent judged 128 elements
    correctly an hour later, on a tenant whose retrieval happened to return summaries instead.

    These documents stay fully reachable by name — `list_artifacts` then `get_artifact_body` —
    which the briefing tells every agent about. What they are not is lying in its pocket.
    """
    t, p = world
    from mcp_platform_state.tools import _NOT_KNOWLEDGE_TYPES

    stored: dict[str, bytes] = {}

    class _Store:
        def get(self, key):
            return stored[key]

    monkeypatch.setattr(tools, "_obj_store", lambda: _Store())

    for kind in sorted(_NOT_KNOWLEDGE_TYPES):
        stored[f"{kind}.md"] = b"## Gate outcome\n\n**PASS** across all 33 judged elements."
        tools.register_artifact(t.id, p.id, None, "a11y_judge", kind, "internal", "h",
                                s3_key=f"{kind}.md", title=kind)

    assert KnowledgeChunk.objects.filter(tenant_id=t.id).count() == 0, (
        "an accessibility verdict was indexed; the judge can now retrieve its own last answer"
    )


def test_an_ordinary_artifact_is_still_indexed(world, monkeypatch):
    """The exclusion is a short list of results, not a switch that turns retrieval off.

    Without this, deleting the whole indexing call would pass the test above.
    """
    t, p = world
    stored = {"prd.md": b"The payment service handles refunds and chargebacks."}

    class _Store:
        def get(self, key):
            return stored[key]

    monkeypatch.setattr(tools, "_obj_store", lambda: _Store())
    tools.register_artifact(t.id, p.id, None, "requirements", "prd", "internal", "h",
                            s3_key="prd.md", title="PRD")

    assert KnowledgeChunk.objects.filter(tenant_id=t.id).exists()


def test_a_judging_runs_own_reasoning_note_is_not_indexed(world, monkeypatch):
    """The second document a judging run writes, which the type list above does not name.

    Excluding the verdicts left this open. Every `a11y_judge` run also registers an `assumption`
    note on how it reasoned, and both such notes in the shared database contained a live element
    of a page under audit with its verdict attached:

        '**1.4.1 vs 1.4.3 independence** — … the `#hours-note` element exhibits exactly this
         combination.'

    Same class as a findings table, one sentence instead, and retrieved by the same recency-blind
    search. It is excluded by PHASE because `assumption` is a type most phases write and the rest
    are worth keeping — see the next test, which is what stops this becoming a wider ban.
    """
    t, p = world
    from mcp_platform_state.tools import _NOT_KNOWLEDGE_PHASES

    stored: dict[str, bytes] = {}

    class _Store:
        def get(self, key):
            return stored[key]

    monkeypatch.setattr(tools, "_obj_store", lambda: _Store())

    for phase in sorted(_NOT_KNOWLEDGE_PHASES):
        stored[f"{phase}.md"] = (
            b"4. **1.4.1 vs 1.4.3 independence** - the `#hours-note` element exhibits "
            b"exactly this combination."
        )
        tools.register_artifact(t.id, p.id, None, phase, "assumption", "internal", "h",
                                s3_key=f"{phase}.md", title=f"Assumptions - {phase}")

    assert KnowledgeChunk.objects.filter(tenant_id=t.id).count() == 0, (
        "a judging run's reasoning note was indexed; the next run can retrieve last "
        "run's answer about a named element"
    )


def test_an_assumption_note_from_another_phase_is_still_indexed(world, monkeypatch):
    """The exclusion is about WHICH RUN wrote the note, never about the word `assumption`.

    Architecture's assumptions are the kind of thing a later phase should find. Without this,
    excluding the type outright would pass the test above while quietly emptying the index for
    every phase that writes one.
    """
    t, p = world
    stored = {"arch.md": b"We assume single-region Postgres until the second tenant lands."}

    class _Store:
        def get(self, key):
            return stored[key]

    monkeypatch.setattr(tools, "_obj_store", lambda: _Store())
    tools.register_artifact(t.id, p.id, None, "architecture", "assumption", "internal", "h",
                            s3_key="arch.md", title="Assumptions - architecture")

    assert KnowledgeChunk.objects.filter(tenant_id=t.id).exists()


def test_a_journey_definition_is_still_indexed(world, monkeypatch):
    """What a run was asked to WALK is not what a run concluded, and only the second is excluded.

    Journeys are read from `testing`/`test_case` artifacts (`journeys._test_case_artifacts`), not
    from the `a11y_journey` phase — so excluding that phase must not reach them. Pinned because
    the two names are one word apart and a later widening of the phase list would look harmless.
    """
    t, p = world
    stored = {"j.md": b"Journey: open the date picker, tab to the end, press Escape."}

    class _Store:
        def get(self, key):
            return stored[key]

    monkeypatch.setattr(tools, "_obj_store", lambda: _Store())
    tools.register_artifact(t.id, p.id, None, "testing", "test_case", "internal", "h",
                            s3_key="j.md", title="Book a room")

    assert KnowledgeChunk.objects.filter(tenant_id=t.id).exists()


# ── the cleanup, and the way it silently failed the first time ───────
@pytest.mark.django_db(transaction=True)
def test_the_verdict_cleanup_reaches_rows_it_cannot_see_by_default():
    """Migration 0004 removes verdict chunks across every tenant. 0003 removed none.

    **The failure this is written against.** `0003_drop_verdict_chunks` filtered with the ORM
    and no tenant scope, on the strength of a convention stated elsewhere in the codebase: the
    migration role *"sees across tenants despite FORCE ROW LEVEL SECURITY"*. True of `postgres`,
    which is `BYPASSRLS`. Not true of `sdlc_migrator`, which merely OWNS the tables — and FORCE
    applies to the owner too. The filter matched nothing, the delete removed nothing, and the
    migration recorded itself as applied and can never run again. 87 and 221 chunks in the
    shared database, unchanged, every one of them older than the migration that claimed to
    remove them.

    Two tenants here, because one tenant would pass under the broken version as easily as the
    fixed one — a scope bug only shows itself across a boundary.
    """
    import importlib

    _mod = importlib.import_module(
        "apps.knowledge.migrations.0004_drop_verdict_chunks_for_real")

    a = Tenant.objects.create(name="A")
    b = Tenant.objects.create(name="B")
    pa = Project.objects.create(tenant=a, name="A")
    pb = Project.objects.create(tenant=b, name="B")
    for tenant, project, kind in ((a, pa, "a11y_judge"), (b, pb, "a11y_report"),
                                  (a, pa, "code_intel")):
        art = tools.register_artifact(tenant.id, project.id, None, "x", kind, "internal", "h")
        index.index_artifact(tenant_id=tenant.id, project_id=project.id,
                             artifact_id=art["id"], text=f"{kind} body",
                             provider=NullEmbeddings())

    assert KnowledgeChunk.objects.count() == 3

    class _SchemaEditor:
        pass

    editor = _SchemaEditor()
    editor.connection = connection
    _mod.drop_verdict_chunks(None, editor)

    remaining = list(KnowledgeChunk.objects.all())
    assert len(remaining) == 1, "both tenants' verdict chunks must go, not just one"
    assert remaining[0].text == "code_intel body", "ordinary knowledge must survive"


def test_the_cleanup_does_not_assume_the_role_it_runs_as():
    """It must lift FORCE itself rather than trusting whoever runs it — and put it back.

    This is the assertion that would have caught 0003. The functional test above passes under a
    superuser connection whether or not the migration handles row-level security, because a
    superuser bypasses it; every local test database is exactly that. Only reading the code
    distinguishes "works here" from "works where it will be run".
    """
    import importlib
    import inspect

    _mod = importlib.import_module(
        "apps.knowledge.migrations.0004_drop_verdict_chunks_for_real")

    source = inspect.getsource(_mod.drop_verdict_chunks)
    assert source.count("NO FORCE ROW LEVEL SECURITY") == 1
    assert source.count("FORCE ROW LEVEL SECURITY") == 2, "lifted once, restored once"
    assert "finally:" in source, "restored even if the delete raises"
    # And it says what it did. 0003 failed by being silent about doing nothing.
    assert "print(" in source


# ── the note the verdict cleanup did not reach ──────────────────────
@pytest.mark.django_db(transaction=True)
def test_the_run_note_cleanup_removes_run_notes_and_nothing_else():
    """Migration 0005 removes chunks made from an accessibility RUN's own documents.

    `0004` removed the verdicts by artifact type. It could not reach the reasoning note, which is
    typed `assumption` like every other phase's — so the note is identified by the PHASE that
    wrote it instead.

    Three artifacts, because this migration has two ways to be wrong and one tenant would show
    neither: too narrow (the `a11y_journey` note survives, and the channel is still open), or too
    wide (architecture's assumptions go too, and every phase quietly loses its notes). Two
    tenants because a scope bug only shows itself across a boundary — the failure that made
    `0003` a no-op.
    """
    import importlib

    _mod = importlib.import_module(
        "apps.knowledge.migrations.0005_drop_a11y_run_note_chunks")

    a = Tenant.objects.create(name="A")
    b = Tenant.objects.create(name="B")
    pa = Project.objects.create(tenant=a, name="A")
    pb = Project.objects.create(tenant=b, name="B")
    for tenant, project, phase in ((a, pa, "a11y_judge"),
                                   (b, pb, "a11y_journey"),
                                   (a, pa, "architecture")):
        art = tools.register_artifact(tenant.id, project.id, None, phase, "assumption",
                                      "internal", "h")
        index.index_artifact(tenant_id=tenant.id, project_id=project.id,
                             artifact_id=art["id"], text=f"{phase} body",
                             provider=NullEmbeddings())

    assert KnowledgeChunk.objects.count() == 3

    class _SchemaEditor:
        pass

    editor = _SchemaEditor()
    editor.connection = connection
    _mod.drop_a11y_run_note_chunks(None, editor)

    survivors = sorted(KnowledgeChunk.objects.values_list("text", flat=True))
    assert survivors == ["architecture body"], survivors


def test_the_run_note_cleanup_restores_only_the_force_it_found():
    """It lifts FORCE itself rather than trusting whoever runs it — and puts back what was there.

    The functional test above passes under a superuser connection whether or not the migration
    handles row-level security, because a superuser bypasses it and every local test database is
    exactly that. Only reading the code distinguishes "works here" from "works where it runs".

    Beyond what `0004` asserts: FORCE is **read** before being lifted and restored only where it
    was on. `0004` restored unconditionally, which on a database where FORCE happened to be off
    would have turned it on — a migration quietly tightening a table it was only passing through.
    """
    import importlib
    import inspect

    _mod = importlib.import_module(
        "apps.knowledge.migrations.0005_drop_a11y_run_note_chunks")

    lift = inspect.getsource(_mod._unforced)
    assert "relforcerowsecurity" in lift, "must read the prior state, not assume it"
    assert "if was_forced:" in lift, "lifted only where it was actually on"
    assert lift.count("NO FORCE ROW LEVEL SECURITY") == 1

    drop = inspect.getsource(_mod.drop_a11y_run_note_chunks)
    assert "finally:" in drop, "restored even if the delete raises"
    assert "if was_forced:" in drop, "restored only where it was on to begin with"
    assert drop.count("FORCE ROW LEVEL SECURITY") == 1, "restored once, never lifted here"
    # And it says what it did. 0003 failed by being silent about doing nothing.
    assert "print(" in drop
