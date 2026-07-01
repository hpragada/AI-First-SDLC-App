"""P4.7-T5 — the authenticated session user is the actor for trigger / decide / answer.

Under a session the `user_id` body param is ignored: UI-driven actions attribute to the
logged-in user and route phases to *their* companion. The pre-auth (`X-Tenant-ID` + body
`user_id`) path is preserved for the runner/test contexts (covered in test_api.py); here we
prove the session path and that role/membership enforcement still applies to the session user.
"""
import pytest
from rest_framework.test import APIClient

from apps.clarifications.models import Clarification
from apps.gates import services as gate_services
from apps.gates.models import Approval
from apps.projects.models import Project
from apps.registry.catalog import seed_agent_specs
from apps.registry.models import AgentSpec
from apps.runs.models import Run, RunnerEnrollment
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from orchestration import trigger as trigger_mod


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


@pytest.fixture
def project(tenant):
    return Project.objects.create(tenant=tenant, name="Platform")


@pytest.fixture
def po(tenant, project):
    """A product_owner — holds the gate role for the prd gate + is a project member."""
    u = User.objects.create_user(email="po@acme.com", name="PO", tenant=tenant, password="pw-po!")
    Membership.objects.create(tenant=tenant, user=u, project=project, role="product_owner")
    return u


@pytest.fixture
def eng(tenant, project):
    u = User.objects.create_user(
        email="eng@acme.com", name="Eng", tenant=tenant, password="pw-eng!"
    )
    Membership.objects.create(tenant=tenant, user=u, project=project, role="engineer")
    return u


def _login(client, email, password):
    assert client.post(
        "/api/auth/login/", {"email": email, "password": password}, format="json"
    ).status_code == 200


# ── trigger: session user is the actor + routing ────────────────────
def test_authenticated_trigger_attributes_to_session_user(client, project, po, monkeypatch):
    seed_agent_specs(project.tenant)
    wi = WorkItem.objects.create(tenant=project.tenant, project=project, type=WorkItem.Type.STORY)
    monkeypatch.setattr(trigger_mod, "_default_workflow_starter", lambda *a, **k: None)
    _login(client, "po@acme.com", "pw-po!")

    # No user_id in the body — the actor comes from the session.
    resp = client.post(
        f"/api/work-items/{wi.id}/trigger/", {"agent_key": "01_ideation"}, format="json"
    )
    assert resp.status_code == 202
    run = Run.objects.get(id=resp.data["run_id"])
    assert str(run.triggered_by_id) == str(po.id)


def test_authenticated_trigger_routes_to_user_companion(client, project, po, monkeypatch):
    seed_agent_specs(project.tenant)
    wi = WorkItem.objects.create(tenant=project.tenant, project=project, type=WorkItem.Type.STORY)
    enrollment = RunnerEnrollment.objects.create(
        tenant=project.tenant, project=project, developer=po,
        status=RunnerEnrollment.Status.ACTIVE,
    )
    captured = {}
    monkeypatch.setattr(
        trigger_mod, "_default_workflow_starter",
        lambda wf_id, inp: captured.update(mode=inp.execution_mode, enr=inp.enrollment_id),
    )
    _login(client, "po@acme.com", "pw-po!")

    resp = client.post(
        f"/api/work-items/{wi.id}/trigger/", {"agent_key": "01_ideation"}, format="json"
    )
    assert resp.status_code == 202
    # The phase routes to the session user's own companion enrollment.
    assert captured["mode"] == "companion"
    assert captured["enr"] == str(enrollment.id)


# ── decide: session user is the actor + role still enforced ─────────
@pytest.fixture
def gate(tenant, project):
    wi = WorkItem.objects.create(tenant=tenant, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=tenant, key="03_prd", body_ref="x")
    run = Run.objects.create(
        tenant=tenant, work_item=wi, agent_spec=spec, temporal_workflow_id="wf-x"
    )
    return Approval.objects.create(
        tenant=tenant, run=run, work_item=wi, required_role="product_owner",
        decision=Approval.Decision.PENDING,
    )


def test_session_decide_attributes_to_session_user(client, project, po, gate, monkeypatch):
    monkeypatch.setattr(gate_services, "_default_signal_sender", lambda *a, **k: None)
    _login(client, "po@acme.com", "pw-po!")

    resp = client.post(
        f"/api/approvals/{gate.id}/decide/", {"decision": "approved"}, format="json"
    )
    assert resp.status_code == 200
    gate.refresh_from_db()
    assert gate.decision == Approval.Decision.APPROVED
    assert str(gate.approver_id) == str(po.id)


def test_session_decide_role_still_enforced(client, project, eng, gate, monkeypatch):
    monkeypatch.setattr(gate_services, "_default_signal_sender", lambda *a, **k: None)
    _login(client, "eng@acme.com", "pw-eng!")  # engineer lacks the product_owner gate role

    resp = client.post(
        f"/api/approvals/{gate.id}/decide/", {"decision": "approved"}, format="json"
    )
    assert resp.status_code == 403
    gate.refresh_from_db()
    assert gate.decision == Approval.Decision.PENDING


def test_decide_without_session_or_user_id_is_400(client, tenant, gate):
    # Pre-auth path with no user_id supplied → 400 (the runner/test path must pass one).
    resp = client.post(
        f"/api/approvals/{gate.id}/decide/", {"decision": "approved"},
        format="json", HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert resp.status_code == 400


# ── answer: session user is the actor + membership still enforced ───
@pytest.fixture
def clarification(tenant, project):
    wi = WorkItem.objects.create(tenant=tenant, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=tenant, key="03_prd", body_ref="x")
    run = Run.objects.create(tenant=tenant, work_item=wi, agent_spec=spec)
    return Clarification.objects.create(
        tenant=tenant, run=run, work_item=wi, phase="prd", questions=[], context="ctx",
    )


def test_session_answer_attributes_to_session_user(client, project, po, clarification):
    _login(client, "po@acme.com", "pw-po!")
    resp = client.post(
        f"/api/clarifications/{clarification.id}/answer/", {"answers": {}}, format="json"
    )
    assert resp.status_code == 200
    clarification.refresh_from_db()
    assert clarification.status == Clarification.Status.ANSWERED
    assert str(clarification.answered_by_id) == str(po.id)


def test_session_answer_requires_project_membership(client, tenant, clarification):
    """A logged-in user who is NOT a member of the clarification's project is rejected."""
    outsider = User.objects.create_user(
        email="out@acme.com", name="Out", tenant=tenant, password="pw-out!"
    )
    assert outsider  # created
    _login(client, "out@acme.com", "pw-out!")
    resp = client.post(
        f"/api/clarifications/{clarification.id}/answer/", {"answers": {}}, format="json"
    )
    assert resp.status_code == 403
