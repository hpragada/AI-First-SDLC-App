"""Part B2 — document-vision (00e): per-document carrier, auto-apply run path, and the adopt
trigger. DB-backed (the platform's cloud DB); these run in CI, not against the local no-DB env."""
import pytest

from apps.projects.models import Project
from apps.registry.catalog import seed_agent_specs
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run, RunnerEnrollment
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from integrations.onboarding import (
    CARRIER_SOURCES,
    ensure_onboarding_work_item,
    ensure_vision_work_item,
)
from orchestration import activities
from orchestration.activities import WriteCompletenessError, verify_write_completeness_core
from orchestration.trigger import NoCompanionError, trigger_vision
from orchestration.types import AgentRunInput
from storage.object_store import content_hash


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
    """The user-facing list applies exclude(external_ref__source__in=CARRIER_SOURCES); both the
    onboarding and vision carriers are hidden, a normal story is not."""
    t, p = _tenant_project()
    ensure_onboarding_work_item(tenant_id=str(t.id), project_id=str(p.id))
    ensure_vision_work_item(tenant_id=str(t.id), project_id=str(p.id), source_document_id="d",
                            artifact_id="a", filename="f.pdf")
    story = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY, title="real")
    visible = list(
        WorkItem.objects.filter(tenant_id=t.id, project_id=p.id)
        .exclude(external_ref__source__in=CARRIER_SOURCES)
    )
    assert visible == [story]


# ── trigger_vision ──────────────────────────────────────────────────
@pytest.mark.django_db
def test_trigger_vision_without_companion_raises():
    t, p = _tenant_project()
    seed_agent_specs(t)
    with pytest.raises(NoCompanionError):
        trigger_vision(
            tenant_id=str(t.id), project_id=str(p.id), source_document_id="d",
            artifact_id="a", filename="f.pdf", triggered_by="user-1",
            workflow_starter=lambda *a: None,
        )


@pytest.mark.django_db
def test_trigger_vision_creates_auto_approve_companion_run():
    t, p = _tenant_project()
    seed_agent_specs(t)
    RunnerEnrollment.objects.create(
        tenant=t, project=p, developer_id="user-1", status=RunnerEnrollment.Status.ACTIVE)
    calls = []
    result = trigger_vision(
        tenant_id=str(t.id), project_id=str(p.id), source_document_id="doc-9",
        artifact_id="art-9", filename="11_UX_Wireframes.pdf", triggered_by="user-1",
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
