"""P0-T3 model tests: Phase 0 entities, tenant_id invariant, append-only ledger.

DB-backed (pytest-django creates a throwaway test DB and runs the migrations,
which also exercises the pgvector extension migration).
"""
import uuid

import pytest
from django.apps import apps as django_apps

from apps.base import Role
from apps.gates.models import Approval
from apps.integrations.models import IntegrationConnection
from apps.ledger.models import AppendOnlyError, Event
from apps.projects.models import Project, ProjectProfile, Repository
from apps.registry.models import AgentSpec, Artifact, TraceEdge
from apps.runs.models import Run
from apps.tenancy.models import Tenant, User
from apps.workitems.models import WorkItem

PLATFORM_APP_LABELS = {
    "tenancy", "projects", "workitems", "registry",
    "ledger", "runs", "gates", "integrations",
}


def test_every_platform_model_has_tenant_id():
    """Non-negotiable #6 prerequisite: every platform domain table carries tenant_id."""
    missing = []
    for label in PLATFORM_APP_LABELS:
        for model in django_apps.get_app_config(label).get_models():
            attnames = {f.attname for f in model._meta.concrete_fields}
            if "tenant_id" not in attnames:
                missing.append(f"{label}.{model.__name__}")
    assert not missing, f"models missing tenant_id: {missing}"


@pytest.mark.django_db
def test_tenant_mirrors_its_id_into_tenant_id():
    t = Tenant.objects.create(name="Acme")
    assert isinstance(t.id, uuid.UUID)
    assert t.tenant_id == t.id  # RLS root scopes to itself


@pytest.mark.django_db
def test_full_planning_chain_with_traceability():
    t = Tenant.objects.create(name="Acme")
    User.objects.create_user(email="po@acme.test", name="PO", tenant=t, password="pw")

    project = Project.objects.create(
        tenant=t, name="Platform", track=Project.Track.GREENFIELD
    )
    ProjectProfile.objects.create(tenant=t, project=project, important_context="ctx")
    Repository.objects.create(tenant=t, project=project, role="backend")

    epic = WorkItem.objects.create(
        tenant=t, project=project, type=WorkItem.Type.EPIC, feature_stream="auth"
    )
    task = WorkItem.objects.create(
        tenant=t, project=project, type=WorkItem.Type.TASK,
        parent=epic, depends_on=[epic.id],
    )
    assert task.parent_id == epic.id
    assert epic.id in task.depends_on  # DAG edge (#4)

    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="agents/03_prd/agent.md")
    run = Run.objects.create(
        tenant=t, work_item=epic, agent_spec=spec, status=Run.Status.AWAITING_GATE
    )

    a_req = Artifact.objects.create(
        tenant=t, project=project, run=run, phase="requirements",
        type="requirements", content_hash="h1",
    )
    a_prd = Artifact.objects.create(
        tenant=t, project=project, run=run, phase="prd", type="prd", content_hash="h2",
    )
    # draft + internal defaults; body lives in S3, registry holds the pointer (#1/#3)
    assert a_req.status == Artifact.Status.DRAFT
    assert a_prd.sor == Artifact.SoR.INTERNAL
    assert a_prd.embedding is None

    edge = TraceEdge.objects.create(
        tenant=t, from_artifact=a_req, to_artifact=a_prd, rel=TraceEdge.Rel.DERIVES
    )
    assert edge.rel == "derives"

    approval = Approval.objects.create(
        tenant=t, run=run, work_item=epic, required_role=Role.PRODUCT_OWNER
    )
    assert approval.decision == Approval.Decision.PENDING  # no auto-publish (#5)

    conn = IntegrationConnection.objects.create(
        tenant=t, capability="tasktracker", connector="jira"
    )
    assert conn.health == IntegrationConnection.Health.UNKNOWN  # table exists P0, used P1+


@pytest.mark.django_db
def test_agentspec_version_unique_per_tenant():
    from django.db import IntegrityError

    t = Tenant.objects.create(name="Acme")
    AgentSpec.objects.create(tenant=t, key="03_prd", semver="1.0.0", body_ref="x")
    with pytest.raises(IntegrityError):
        AgentSpec.objects.create(tenant=t, key="03_prd", semver="1.0.0", body_ref="y")


@pytest.mark.django_db
def test_event_is_append_only():
    t = Tenant.objects.create(name="Acme")
    e = Event.objects.create(
        tenant=t, actor="system", action="run.completed", target_type="run", target_id=t.id
    )
    with pytest.raises(AppendOnlyError):
        e.action = "tampered"
        e.save()
    with pytest.raises(AppendOnlyError):
        e.delete()
