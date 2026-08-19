"""Part B2 — document-vision (00e): per-document carrier, auto-apply run path, and the adopt
trigger. DB-backed (the platform's cloud DB); these run in CI, not against the local no-DB env."""
import pytest
from django.db.models import Q
from mcp_platform_state import tools

from apps.integrations.models import SourceDocument
from apps.projects.models import Project
from apps.registry.catalog import seed_agent_specs
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run, RunnerEnrollment
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from integrations.onboarding import (
    CARRIER_SOURCES,
    VISION_STATES,
    adopt_source_document,
    ensure_onboarding_work_item,
    ensure_vision_work_item,
    vision_states_for_documents,
)
from orchestration import activities
from orchestration.activities import WriteCompletenessError, verify_write_completeness_core
from orchestration.trigger import NoCompanionError, trigger_vision
from orchestration.types import AgentRunInput
from storage.object_store import InMemoryObjectStore, content_hash


def _tenant_project():
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="Platform")
    return t, p


def _vision_input(t, p, run, *, auto_approve=True):
    return AgentRunInput(
        run_id=str(run.id), tenant_id=str(t.id), project_id=str(p.id),
        work_item_id=str(run.work_item_id), agent_spec_id=str(run.agent_spec_id),
        phase="document_vision", auto_approve=auto_approve,
    )


# ── verify_writes: auto-apply requires real content ─────────────────
@pytest.mark.django_db
def test_verify_writes_auto_approve_passes_with_nonempty_artifact():
    t, p = _tenant_project()
    seed_agent_specs(t)
    spec = AgentSpec.objects.get(tenant=t, key="00e_document_vision")
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.EPIC)
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)
    Artifact.objects.create(
        tenant_id=t.id, project=p, run=run, phase="onboarding", type="architecture",
        title="08_Architecture", sor="internal", content_hash=content_hash(b"faithful body"),
        s3_key="k", version=2,
    )
    out = verify_write_completeness_core(_vision_input(t, p, run), ["document_vision"])
    assert out["present"] == ["non-empty artifact"]


@pytest.mark.django_db
def test_verify_writes_auto_approve_raises_when_only_empty():
    t, p = _tenant_project()
    seed_agent_specs(t)
    spec = AgentSpec.objects.get(tenant=t, key="00e_document_vision")
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.EPIC)
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)
    # An artifact staged from no text carries the empty-body hash → nothing to apply.
    Artifact.objects.create(
        tenant_id=t.id, project=p, run=run, phase="onboarding", type="architecture",
        sor="internal", content_hash=activities._EMPTY_BODY_HASH, s3_key="k", version=2,
    )
    with pytest.raises(WriteCompletenessError):
        verify_write_completeness_core(_vision_input(t, p, run), ["document_vision"])


# ── per-document carrier ────────────────────────────────────────────
@pytest.mark.django_db
def test_ensure_vision_work_item_is_hidden_carrier_and_idempotent():
    t, p = _tenant_project()
    a = ensure_vision_work_item(
        tenant_id=str(t.id), project_id=str(p.id), source_document_id="doc-1",
        artifact_id="art-1", filename="08_Architecture.pdf")
    b = ensure_vision_work_item(
        tenant_id=str(t.id), project_id=str(p.id), source_document_id="doc-1",
        artifact_id="art-1b", filename="08_Architecture.pdf")
    assert a.id == b.id  # idempotent by (project, source, source_document_id)
    assert a.external_ref["source"] == "vision_carrier"
    b.refresh_from_db()
    assert b.external_ref["artifact_id"] == "art-1b"  # pointer refreshed on re-adopt
    assert "art-1b" in b.description  # target named in the manifest-rendered description


@pytest.mark.django_db
def test_carriers_excluded_by_hide_filter():
    """The user-facing list hides both carriers and shows everything else (S3-13).

    The third item is the whole point of this test. `external_ref` is nullable, so the earlier
    version — one story with a NULL ref — exercised the ONLY shape the old filter got right, and
    passed while the backlog was empty in the running product. A Jira import carries a REAL dict
    with no `source` key, and for that row `NULL IN (…)` → NULL → `NOT NULL` → NULL, so Postgres
    dropped it. Keep a dict-without-`source` row here or this test proves nothing.
    """
    t, p = _tenant_project()
    ensure_onboarding_work_item(tenant_id=str(t.id), project_id=str(p.id))
    ensure_vision_work_item(tenant_id=str(t.id), project_id=str(p.id), source_document_id="d",
                            artifact_id="a", filename="f.pdf")
    story = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY, title="real")
    imported = WorkItem.objects.create(
        tenant=t, project=p, type=WorkItem.Type.TASK, title="ST-447",
        external_ref={"sor": "jira", "id": "ST-447", "url": "https://x/browse/ST-447"},
    )
    visible = list(
        WorkItem.objects.filter(tenant_id=t.id, project_id=p.id)
        .exclude(Q(external_ref__has_key="source")
                 & Q(external_ref__source__in=CARRIER_SOURCES))
        .order_by("created_at")
    )
    assert visible == [story, imported]


# ── trigger_vision ──────────────────────────────────────────────────
@pytest.mark.django_db
def test_trigger_vision_without_companion_raises():
    t, p = _tenant_project()
    seed_agent_specs(t)
    # A real user id: `RunnerEnrollment.developer` is a foreign key, so the enrollment lookup
    # `trigger_vision` does is a UUID comparison. A placeholder string never reaches "no
    # companion" — it fails in the query first, which tests the wrong thing.
    dev = User.objects.create(tenant=t, email="dev@example.com")
    with pytest.raises(NoCompanionError):
        trigger_vision(
            tenant_id=str(t.id), project_id=str(p.id), source_document_id="d",
            artifact_id="a", filename="f.pdf", triggered_by=str(dev.id),
            workflow_starter=lambda *a: None,
        )


@pytest.mark.django_db
def test_trigger_vision_creates_auto_approve_companion_run():
    t, p = _tenant_project()
    seed_agent_specs(t)
    dev = User.objects.create(tenant=t, email="dev@example.com")
    RunnerEnrollment.objects.create(
        tenant=t, project=p, developer=dev, status=RunnerEnrollment.Status.ACTIVE)
    calls = []
    result = trigger_vision(
        tenant_id=str(t.id), project_id=str(p.id), source_document_id="doc-9",
        artifact_id="art-9", filename="11_UX_Wireframes.pdf", triggered_by=str(dev.id),
        workflow_starter=lambda wf, inp: calls.append(inp),
    )
    run = Run.objects.get(id=result.run_id)
    assert run.status == Run.Status.PENDING
    assert len(calls) == 1
    inp = calls[0]
    assert inp.auto_approve is True
    assert inp.phase == "document_vision"
    assert inp.execution_mode == "companion"
    carrier = WorkItem.objects.get(id=inp.work_item_id)
    assert carrier.external_ref["source"] == "vision_carrier"
    assert carrier.external_ref["source_document_id"] == "doc-9"


# ── Fix 1: an auto-applied version may not LOSE the content it replaces ──
def _doc_artifact(t, p, *, run=None, version, s3_key, title="08_Architecture"):
    return Artifact.objects.create(
        tenant_id=t.id, project=p, run=run, phase="onboarding", type="architecture",
        title=title, sor="internal", content_hash=content_hash(s3_key.encode()),
        s3_key=s3_key, version=version,
    )


@pytest.mark.django_db
def test_auto_apply_rejects_a_version_that_shrank():
    """A vision pass that returned only the diagram text — dropping the prose it was told to
    keep — is non-empty, so the emptiness check passes it. This is the guard that doesn't."""
    t, p = _tenant_project()
    seed_agent_specs(t)
    spec = AgentSpec.objects.get(tenant=t, key="00e_document_vision")
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.EPIC)
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)
    _doc_artifact(t, p, version=1, s3_key="v1")
    _doc_artifact(t, p, run=run, version=2, s3_key="v2")
    store = InMemoryObjectStore()
    store.put("v1", b"x" * 5000)        # the adopted extraction
    store.put("v2", b"x" * 400)         # diagrams only — the prose is gone
    with pytest.raises(WriteCompletenessError, match="shorter rendering"):
        verify_write_completeness_core(
            _vision_input(t, p, run), ["document_vision"], object_store=store)


@pytest.mark.django_db
def test_auto_apply_accepts_a_version_that_grew():
    t, p = _tenant_project()
    seed_agent_specs(t)
    spec = AgentSpec.objects.get(tenant=t, key="00e_document_vision")
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.EPIC)
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)
    _doc_artifact(t, p, version=1, s3_key="v1")
    _doc_artifact(t, p, run=run, version=2, s3_key="v2")
    store = InMemoryObjectStore()
    store.put("v1", b"x" * 1000)
    store.put("v2", b"x" * 4000)        # extraction preserved + diagrams transcribed
    out = verify_write_completeness_core(
        _vision_input(t, p, run), ["document_vision"], object_store=store)
    assert out["present"] == ["non-empty artifact"]


@pytest.mark.django_db
def test_auto_apply_guard_ignores_a_first_registration():
    """Nothing to compare against ⇒ nothing to prove ⇒ the guard must not block."""
    t, p = _tenant_project()
    seed_agent_specs(t)
    spec = AgentSpec.objects.get(tenant=t, key="00e_document_vision")
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.EPIC)
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)
    _doc_artifact(t, p, run=run, version=1, s3_key="only")
    store = InMemoryObjectStore()
    store.put("only", b"short")
    out = verify_write_completeness_core(
        _vision_input(t, p, run), ["document_vision"], object_store=store)
    assert out["present"] == ["non-empty artifact"]


# ── Fix 2: `supersedes` anchors the new version to the target ────────
@pytest.mark.django_db
def test_supersedes_versions_the_target_even_when_the_title_drifts():
    t, p = _tenant_project()
    target = _doc_artifact(t, p, version=1, s3_key="v1", title="08_Architecture")
    out = tools.register_artifact(
        str(t.id), str(p.id), None, "wrong_phase", "wrong_type", "internal",
        content_hash(b"body"), s3_key="v2", title="Architecture (transcribed)",
        supersedes=str(target.id),
    )
    assert out["version"] == 2                     # a new VERSION, not a second artifact
    assert out["type"] == "architecture"           # identity taken from the target,
    assert out["title"] == "08_Architecture"       # not from what the caller restated
    assert Artifact.objects.filter(tenant_id=t.id, type="architecture").count() == 2
    assert Artifact.objects.filter(tenant_id=t.id, type="wrong_type").count() == 0


@pytest.mark.django_db
def test_supersedes_rejects_a_target_in_another_project():
    t, p = _tenant_project()
    other = Project.objects.create(tenant=t, name="Other")
    target = _doc_artifact(t, p, version=1, s3_key="v1")
    with pytest.raises(ValueError, match="same project"):
        tools.register_artifact(
            str(t.id), str(other.id), None, "onboarding", "architecture", "internal",
            content_hash(b"b"), s3_key="v2", title="x", supersedes=str(target.id),
        )


# ── Fix 3: adopt reports what the vision pass did, in plain words ────
def _adopted_doc(t, p, *, with_images=True, user=None):
    """A source document sitting at the adopt gate, with a published extraction to supersede."""
    art = Artifact.objects.create(
        tenant_id=t.id, project=p, phase="onboarding", type="document",
        title="08_Architecture", sor="internal", content_hash=content_hash(b"text"),
        s3_key="v1", version=1,
        external_ref={"page_images": [{"name": "p1.png", "page": 1}]} if with_images else {},
    )
    return SourceDocument.objects.create(
        tenant=t, project=p, filename="08_Architecture.pdf", mime="application/pdf",
        status=SourceDocument.Status.EXTRACTED, extracted_artifact_ids=[str(art.id)],
    )


def _product_owner(t, p):
    u = User.objects.create(tenant=t, email="po@example.com")
    Membership.objects.create(tenant=t, project=p, user=u, role="product_owner")
    return u


@pytest.mark.django_db
def test_adopt_reports_no_companion_with_the_actionable_message():
    """The message exists and tells the user exactly what to do — it must reach them."""
    t, p = _tenant_project()
    seed_agent_specs(t)
    user = _product_owner(t, p)
    src = _adopted_doc(t, p)
    out = adopt_source_document(
        tenant_id=str(t.id), source_document_id=str(src.id), user_id=str(user.id),
        target_type="architecture",
    )
    assert out["status"] == "adopted"          # adoption still succeeds — vision is a bonus
    assert out["vision"]["state"] == "no_companion"
    # The product calls it "your machine" everywhere the user can see; "companion" is internal
    # vocabulary and must not leak into the message.
    assert "your machine" in out["vision"]["message"].lower()
    assert "companion" not in out["vision"]["message"].lower()
    assert "_" not in out["vision"]["message"]  # a sentence, never a raw code


@pytest.mark.django_db
def test_adopt_reports_no_visuals_for_a_text_only_document():
    t, p = _tenant_project()
    seed_agent_specs(t)
    user = _product_owner(t, p)
    src = _adopted_doc(t, p, with_images=False)
    out = adopt_source_document(
        tenant_id=str(t.id), source_document_id=str(src.id), user_id=str(user.id),
        target_type="architecture",
    )
    assert out["vision"]["state"] == "no_visuals"


@pytest.mark.django_db
def test_every_vision_message_is_a_human_sentence():
    """Guards the team rule: nothing the user reads may be a raw identifier."""
    for state, message in VISION_STATES.items():
        assert "_" not in message, state
        assert message[0].isupper() and message.rstrip().endswith("."), state


# ── Fix 4: a run that fails AFTER dispatch is still visible ──────────
@pytest.mark.django_db
def test_failed_vision_run_surfaces_on_the_document():
    t, p = _tenant_project()
    seed_agent_specs(t)
    spec = AgentSpec.objects.get(tenant=t, key="00e_document_vision")
    carrier = ensure_vision_work_item(
        tenant_id=str(t.id), project_id=str(p.id), source_document_id="doc-1",
        artifact_id="art-1", filename="08_Architecture.pdf",
    )
    Run.objects.create(tenant=t, work_item=carrier, agent_spec=spec,
                       status=Run.Status.FAILED)
    states = vision_states_for_documents(
        tenant_id=str(t.id), project_id=str(p.id), source_document_ids=["doc-1"])
    assert states["doc-1"]["state"] == "failed"
    assert "_" not in states["doc-1"]["message"]


@pytest.mark.django_db
def test_completed_vision_run_reads_as_done():
    t, p = _tenant_project()
    seed_agent_specs(t)
    spec = AgentSpec.objects.get(tenant=t, key="00e_document_vision")
    carrier = ensure_vision_work_item(
        tenant_id=str(t.id), project_id=str(p.id), source_document_id="doc-2",
        artifact_id="art-2", filename="wireframes.pdf",
    )
    Run.objects.create(tenant=t, work_item=carrier, agent_spec=spec,
                       status=Run.Status.COMPLETED)
    states = vision_states_for_documents(
        tenant_id=str(t.id), project_id=str(p.id), source_document_ids=["doc-2"])
    assert states["doc-2"]["state"] == "done"


@pytest.mark.django_db
def test_document_with_no_vision_run_has_no_state():
    t, p = _tenant_project()
    states = vision_states_for_documents(
        tenant_id=str(t.id), project_id=str(p.id), source_document_ids=["doc-none"])
    assert states == {}
