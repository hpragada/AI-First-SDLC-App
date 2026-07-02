"""P4.8-T1 bucket-B gaps A/B (screen-audit) — closed while wiring the Phase 4.8 UI to live
data: `PATCH /api/work-items/{id}/` (title/description/type only, S-15/S-16 "Edit"), the
`type`/`parent` list filters (S-14 board level filter, S-23 fan-out), and the
`artifact_count`/`owner`/`needs` card fields the board/detail screens render — none of which
the `WorkItemViewSet` actually served despite the frontend already sending/expecting them.
"""
import pytest
from rest_framework.test import APIClient

from apps.clarifications.models import Clarification
from apps.gates.models import Approval
from apps.projects.models import Project
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem


def _login(client, email, password):
    assert client.post(
        "/api/auth/login/", {"email": email, "password": password}, format="json"
    ).status_code == 200


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


@pytest.fixture
def project(tenant):
    return Project.objects.create(tenant=tenant, name="Payments")


@pytest.fixture
def dev(tenant, project):
    u = User.objects.create_user(
        email="dev@acme.com", name="Dev Patel", tenant=tenant, password="dev-pass!"
    )
    Membership.objects.create(tenant=tenant, user=u, project=project, role="tech_lead")
    return u


@pytest.fixture
def epic(tenant, project, dev):
    return WorkItem.objects.create(
        tenant=tenant, project=project, type="epic", title="Stripe Webhook Integration",
        feature_stream="payments", assignee=dev,
    )


def _agent_spec(tenant, key="04_architecture"):
    return AgentSpec.objects.create(tenant=tenant, key=key, body_ref=f"agents/{key}.md")


def _run(tenant, work_item, agent_spec):
    return Run.objects.create(tenant=tenant, work_item=work_item, agent_spec=agent_spec)


def _list(client, tenant, project):
    return client.get(
        "/api/work-items/", {"project": str(project.id)}, HTTP_X_TENANT_ID=str(tenant.id)
    )


def test_patch_updates_title_description_type_only(client, tenant, project, dev, epic):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.patch(
        f"/api/work-items/{epic.id}/",
        {"title": "Renamed", "description": "New desc", "type": "story",
         "state": "done", "takeover_flag": True},
        format="json", HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert resp.status_code == 200
    epic.refresh_from_db()
    assert epic.title == "Renamed"
    assert epic.description == "New desc"
    assert epic.type == "story"
    # Not patchable via this endpoint — untouched.
    assert epic.state == "proposed"
    assert epic.takeover_flag is False


def test_type_filter(client, tenant, project, dev, epic):
    task = WorkItem.objects.create(
        tenant=tenant, project=project, type="task", title="Sub-task", parent=epic
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(
        "/api/work-items/", {"project": str(project.id), "type": "task"},
        HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.data}
    assert ids == {str(task.id)}


def test_parent_filter_returns_children(client, tenant, project, dev, epic):
    child1 = WorkItem.objects.create(
        tenant=tenant, project=project, type="task", title="Task 1", parent=epic
    )
    child2 = WorkItem.objects.create(
        tenant=tenant, project=project, type="task", title="Task 2", parent=epic
    )
    WorkItem.objects.create(tenant=tenant, project=project, type="task", title="Unrelated")
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(
        "/api/work-items/", {"project": str(project.id), "parent": str(epic.id)},
        HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.data}
    assert ids == {str(child1.id), str(child2.id)}


def test_artifact_count_and_owner_on_list_and_retrieve(client, tenant, project, dev, epic):
    spec = _agent_spec(tenant)
    run = _run(tenant, epic, spec)
    Artifact.objects.create(tenant=tenant, project=project, run=run, phase="04_architecture",
                            type="architecture_doc", status="draft", version=1)
    Artifact.objects.create(tenant=tenant, project=project, run=run, phase="04_architecture",
                            type="architecture_doc", status="draft", version=2)
    _login(client, "dev@acme.com", "dev-pass!")

    list_resp = _list(client, tenant, project)
    row = next(r for r in list_resp.data if r["id"] == str(epic.id))
    assert row["artifact_count"] == 2
    assert row["owner"] == "Dev Patel"

    detail_resp = client.get(f"/api/work-items/{epic.id}/", HTTP_X_TENANT_ID=str(tenant.id))
    assert detail_resp.data["artifact_count"] == 2
    assert detail_resp.data["owner"] == "Dev Patel"


def test_needs_reflects_pending_clarification_over_gate(client, tenant, project, dev, epic):
    spec = _agent_spec(tenant)
    run = _run(tenant, epic, spec)
    Approval.objects.create(tenant=tenant, run=run, work_item=epic, gate_type="architecture",
                            required_role="architect", decision="pending")
    Clarification.objects.create(tenant=tenant, run=run, work_item=epic, phase="04_architecture",
                                 status="pending", questions=[{"id": "q1", "text": "?"}])
    _login(client, "dev@acme.com", "dev-pass!")
    resp = _list(client, tenant, project)
    row = next(r for r in resp.data if r["id"] == str(epic.id))
    assert row["needs"] == {"clarification": True, "label": "Needs answer"}


def test_needs_reflects_pending_gate_when_no_clarification(client, tenant, project, dev, epic):
    spec = _agent_spec(tenant)
    run = _run(tenant, epic, spec)
    Approval.objects.create(tenant=tenant, run=run, work_item=epic, gate_type="architecture",
                            required_role="architect", decision="pending")
    _login(client, "dev@acme.com", "dev-pass!")
    resp = _list(client, tenant, project)
    row = next(r for r in resp.data if r["id"] == str(epic.id))
    assert row["needs"] == {"gate": True, "label": "architecture gate"}


def test_needs_is_none_when_nothing_pending(client, tenant, project, dev, epic):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = _list(client, tenant, project)
    row = next(r for r in resp.data if r["id"] == str(epic.id))
    assert row["needs"] is None
    assert row["artifact_count"] == 0


def test_card_fields_are_tenant_isolated(client, db):
    t1 = Tenant.objects.create(name="Acme")
    t2 = Tenant.objects.create(name="Globex")
    p1 = Project.objects.create(tenant=t1, name="P1")
    p2 = Project.objects.create(tenant=t2, name="P2")
    u1 = User.objects.create_user(email="a@acme.com", name="A", tenant=t1, password="pw!")
    Membership.objects.create(tenant=t1, user=u1, project=p1, role="engineer")
    wi1 = WorkItem.objects.create(tenant=t1, project=p1, type="epic", title="E1")
    WorkItem.objects.create(tenant=t2, project=p2, type="epic", title="E2")

    _login(client, "a@acme.com", "pw!")
    resp = client.get("/api/work-items/", {"project": str(p1.id)}, HTTP_X_TENANT_ID=str(t1.id))
    assert resp.status_code == 200
    assert {r["id"] for r in resp.data} == {str(wi1.id)}
