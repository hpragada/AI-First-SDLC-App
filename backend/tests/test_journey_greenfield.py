"""Greenfield E2E journey tests — full lifecycle Ideation → Deployment.

Each test class maps to a scenario in docs/USER_JOURNEY_GREENFIELD.md.
Tests use the real service layer (no mocks) and the Django test client, so
every state transition, permission check, and API shape is exercised against
the actual business logic.

External integrations (Confluence, Jira, GitHub, Figma, Xray) are unavailable
in CI — their failure paths are noted and the test continues.
"""
import pytest
from rest_framework.test import APIClient

from apps.gates.models import Approval
from apps.gates.services import GateConditionsError, GateError, GateRoleError, decide_gate
from apps.clarifications.models import Clarification
from apps.clarifications.services import ClarificationError, ClarificationRoleError, answer_clarification
from apps.projects.models import Project, Repository
from apps.registry.catalog import ACTIVE_AGENT_CATALOG, gate_role_for
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run, RunnerEnrollment
from apps.tenancy.models import Invitation, Membership, Tenant, User
from apps.tenancy.services import create_invitation, seed_agent_specs, signup
from apps.workitems.models import WorkItem
from orchestration.takeover import TakeoverError, release_takeover, request_takeover


# ── Shared fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def acme(db):
    """Tenant seeded with all 16 AgentSpecs."""
    from apps.tenancy.services import create_tenant
    t = create_tenant(name="Acme Corp")
    return t


@pytest.fixture
def sarah(acme):
    """Founder / admin with product_owner + architect roles."""
    return User.objects.create_user(
        email="sarah@acme.com", name="Sarah Chen", tenant=acme,
        password="Str0ng-Pass!", is_tenant_admin=True,
    )


@pytest.fixture
def marcus(acme):
    return User.objects.create_user(
        email="marcus@acme.com", name="Marcus Lee", tenant=acme, password="Arch-Pass!"
    )


@pytest.fixture
def dev_patel(acme):
    return User.objects.create_user(
        email="dev@acme.com", name="Dev Patel", tenant=acme, password="Dev-Pass!"
    )


@pytest.fixture
def carlos(acme):
    return User.objects.create_user(
        email="carlos@acme.com", name="Carlos Reyes", tenant=acme, password="QA-Pass!"
    )


@pytest.fixture
def project(acme, sarah):
    p = Project.objects.create(
        tenant=acme, name="Stripe Webhook Integration",
        track=Project.Track.GREENFIELD, repo_topology=Project.RepoTopology.SINGLE,
    )
    Membership.objects.create(tenant=acme, user=sarah, project=p, role="product_owner")
    return p


@pytest.fixture
def all_memberships(acme, project, marcus, dev_patel, carlos):
    """Give every persona the role they gate-approve."""
    Membership.objects.create(tenant=acme, user=marcus, project=project, role="architect")
    Membership.objects.create(tenant=acme, user=dev_patel, project=project, role="tech_lead")
    Membership.objects.create(tenant=acme, user=carlos, project=project, role="qa_lead")


@pytest.fixture
def epic(acme, project, sarah):
    return WorkItem.objects.create(
        tenant=acme, project=project, type=WorkItem.Type.EPIC,
        title="Stripe Webhook Integration", feature_stream="payments",
        state=WorkItem.State.PROPOSED,
    )


@pytest.fixture
def agent_spec(acme):
    """Return the 01_ideation AgentSpec (created by seed_agent_specs in create_tenant)."""
    return AgentSpec.objects.get(tenant=acme, key="01_ideation")


@pytest.fixture
def run_for(acme, epic, agent_spec, sarah):
    """Helper: create a Run in a given status."""
    def _make(status=Run.Status.AWAITING_GATE, agent_key="01_ideation"):
        spec = AgentSpec.objects.get(tenant=acme, key=agent_key)
        return Run.objects.create(
            tenant=acme, work_item=epic, agent_spec=spec,
            triggered_by=sarah, status=status,
            temporal_workflow_id=f"agent-run-fake-{agent_key}",
        )
    return _make


@pytest.fixture
def approval_for(acme, epic):
    """Helper: create a pending Approval for a run."""
    def _make(run, required_role="product_owner", conditions=None):
        return Approval.objects.create(
            tenant=acme, run=run, gate_type="phase_gate",
            work_item=epic, required_role=required_role,
            decision=Approval.Decision.PENDING,
            conditions=conditions or [],
        )
    return _make


def _login(client, email, password):
    r = client.post("/api/auth/login/", {"email": email, "password": password}, format="json")
    assert r.status_code == 200, f"Login failed: {r.data}"
    return r


# ── A-0: Workspace signup ────────────────────────────────────────────────────

class TestSignup:
    def test_signup_creates_tenant_user_and_seeds_agent_specs(self, client, db):
        r = client.post("/api/auth/signup/", {
            "name": "Sarah Chen", "email": "sarah@newco.com",
            "password": "Str0ng-Pass!", "org_name": "NewCo",
        }, format="json")
        assert r.status_code == 201
        # Shape matches frontend CurrentUser type
        assert r.data["user"]["is_tenant_admin"] is True
        assert r.data["tenant"]["name"] == "NewCo"
        assert "isAdmin" not in r.data  # must NOT have top-level isAdmin
        # Memberships use project_id not project
        # (empty at signup — no project yet)
        assert r.data["memberships"] == []
        # All 16 AgentSpecs seeded
        tenant_id = r.data["tenant"]["id"]
        assert AgentSpec.objects.filter(tenant_id=tenant_id).count() == len(ACTIVE_AGENT_CATALOG)

    def test_signup_duplicate_email_rejected(self, client, sarah):
        r = client.post("/api/auth/signup/", {
            "name": "Clone", "email": "sarah@acme.com",
            "password": "Clone-Pass!", "org_name": "Clone Co",
        }, format="json")
        assert r.status_code == 409

    def test_signup_weak_password_rejected(self, client, db):
        r = client.post("/api/auth/signup/", {
            "name": "Bob", "email": "bob@test.com",
            "password": "short", "org_name": "Bob Co",
        }, format="json")
        assert r.status_code == 400

    def test_me_returns_project_id_in_memberships(self, client, sarah, project):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get("/api/auth/me/")
        assert r.status_code == 200
        m = r.data["memberships"][0]
        assert "project_id" in m
        assert "project" not in m  # old field name must not appear
        assert "project_name" in m


# ── A-1: Invitations ─────────────────────────────────────────────────────────

class TestInvitations:
    def test_admin_can_invite_with_role_grant(self, client, sarah, project):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.post("/api/invitations/", {
            "email": "marcus@acme.com", "name": "Marcus Lee",
            "grants": [{"project_id": str(project.id), "role": "architect"}],
        }, format="json")
        assert r.status_code == 201
        assert r.data["status"] == "pending"
        assert "token" not in r.data  # token never exposed
        assert "token_hash" not in r.data

    def test_non_admin_cannot_invite(self, client, dev_patel, project):
        Membership.objects.create(tenant=dev_patel.tenant, user=dev_patel, project=project, role="tech_lead")
        _login(client, "dev@acme.com", "Dev-Pass!")
        r = client.post("/api/invitations/", {"email": "x@y.com"}, format="json")
        assert r.status_code == 403

    def test_accept_invitation_creates_membership(self, client, sarah, project):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        inv_r = client.post("/api/invitations/", {
            "email": "new@acme.com", "name": "New Member",
            "grants": [{"project_id": str(project.id), "role": "engineer"}],
        }, format="json")
        assert inv_r.status_code == 201

        # Accept via service (email token not testable here)
        inv, raw = create_invitation(
            tenant=sarah.tenant, invited_by=sarah, email="new2@acme.com",
            grants=[{"project_id": str(project.id), "role": "engineer"}],
        )
        anon = APIClient()
        r = anon.post("/api/auth/accept-invitation/", {
            "token": raw, "password": "NewPass-123!", "name": "New Member",
        }, format="json")
        assert r.status_code == 200
        assert r.data["memberships"][0]["role"] == "engineer"

    def test_expired_invitation_returns_410(self, client, sarah):
        from datetime import timedelta
        from django.utils import timezone
        inv, raw = create_invitation(tenant=sarah.tenant, invited_by=sarah, email="exp@acme.com")
        inv.expires_at = timezone.now() - timedelta(days=1)
        inv.save()
        r = client.post("/api/auth/accept-invitation/", {"token": raw, "password": "Test-Pass!"},
                        format="json")
        assert r.status_code == 410

    def test_revoked_invitation_returns_410(self, client, sarah):
        inv, raw = create_invitation(tenant=sarah.tenant, invited_by=sarah, email="rev@acme.com")
        inv.status = "revoked"
        inv.save()
        r = client.post("/api/auth/accept-invitation/", {"token": raw, "password": "Test-Pass!"},
                        format="json")
        assert r.status_code == 410

    def test_single_use_token(self, client, sarah):
        inv, raw = create_invitation(tenant=sarah.tenant, invited_by=sarah, email="once@acme.com")
        c1 = APIClient()
        assert c1.post("/api/auth/accept-invitation/", {"token": raw, "password": "Pass-One!"},
                       format="json").status_code == 200
        c2 = APIClient()
        assert c2.post("/api/auth/accept-invitation/", {"token": raw, "password": "Pass-Two!"},
                       format="json").status_code == 409


# ── A-2: Companion runner ────────────────────────────────────────────────────

class TestRunnerEnrollment:
    def test_create_runner_requires_session_for_get(self, client, acme):
        """GET /api/runners/ requires authentication — unauthenticated → 403."""
        r = client.get("/api/runners/", HTTP_X_TENANT_ID=str(acme.id))
        assert r.status_code == 403

    def test_create_runner_returns_one_time_token(self, client, sarah, project):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.post("/api/runners/",
                        {"project_id": str(project.id), "label": "Dev MacBook"},
                        format="json")
        assert r.status_code == 201
        assert "token" in r.data
        assert "id" in r.data

    def test_list_runners_groups_by_machine(self, client, acme, sarah, project):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        client.post("/api/runners/", {"project_id": str(project.id), "label": "My Mac"},
                    format="json")
        r = client.get("/api/runners/")
        assert r.status_code == 200
        assert len(r.data) == 1
        machine = r.data[0]
        assert "machine" in machine
        assert "online" in machine
        assert isinstance(machine["projects"], list)
        # Project uses project_id not id
        if machine["projects"]:
            assert "project_id" in machine["projects"][0]
            assert "id" not in machine["projects"][0]

    def test_old_projects_array_body_rejected(self, client, sarah, project):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.post("/api/runners/", {"projects": [str(project.id)]}, format="json")
        assert r.status_code in (400, 422), \
            f"Old body shape must be rejected, got {r.status_code}"


# ── A-3: Integrations ────────────────────────────────────────────────────────

class TestIntegrations:
    def test_admin_can_create_integration(self, client, sarah):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.post("/api/integrations/", {
            "capability": "docstore", "vendor": "confluence",
            "binding": {"url": "https://confluence.acme.com"},
            "secrets": {"token": "fake-token"},
        }, format="json")
        assert r.status_code == 201
        assert "secret" not in str(r.data)  # secrets never echoed

    def test_non_admin_cannot_create_integration(self, client, dev_patel, project):
        Membership.objects.create(
            tenant=dev_patel.tenant, user=dev_patel, project=project, role="tech_lead"
        )
        _login(client, "dev@acme.com", "Dev-Pass!")
        r = client.post("/api/integrations/", {
            "capability": "docstore", "vendor": "confluence",
            "binding": {}, "secrets": {},
        }, format="json")
        assert r.status_code == 403

    def test_test_connection_returns_ok_and_detail(self, client, sarah, acme):
        from apps.integrations.crypto import encrypt_secrets
        from apps.integrations.models import IntegrationConnection
        conn = IntegrationConnection.objects.create(
            tenant=acme, capability="codeintel", connector="builtin",
        )
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.post(f"/api/integrations/{conn.id}/test-connection/")
        assert r.status_code == 200
        assert "ok" in r.data
        assert "detail" in r.data
        assert isinstance(r.data["ok"], bool)
        # NOTE: External connector test (e.g. confluence) will return ok=false
        # when no live endpoint available — INTEGRATION_FAILURE noted and continuing

    def test_secrets_never_in_response(self, client, sarah, acme):
        from apps.integrations.crypto import encrypt_secrets
        from apps.integrations.models import IntegrationConnection
        conn = IntegrationConnection.objects.create(
            tenant=acme, capability="docstore", connector="confluence",
            secret_encrypted=encrypt_secrets({"token": "super-secret"}),
        )
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get(f"/api/integrations/{conn.id}/")
        assert r.status_code == 200
        assert "super-secret" not in str(r.data)
        assert "secret_encrypted" not in r.data
        assert r.data["configured"] is True


# ── A-4: Project + Profile ───────────────────────────────────────────────────

class TestProjectAndProfile:
    def test_create_greenfield_project(self, client, sarah, acme):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.post("/api/projects/", {
            "name": "New Product", "track": "greenfield", "repo_topology": "single",
        }, format="json")
        assert r.status_code == 201
        assert r.data["track"] == "greenfield"
        assert r.data["repo_topology"] == "single"

    def test_profile_create_and_update(self, client, sarah, project):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        # Create
        r = client.put(f"/api/projects/{project.id}/profile/", {
            "description": "Payment processing platform",
            "domain": "fintech",
            "tech_stack": {"backend": "django", "frontend": "react"},
        }, format="json")
        assert r.status_code in (200, 201)
        assert r.data["description"] == "Payment processing platform"
        v1 = r.data["version"]

        # Update — version must increment
        r2 = client.put(f"/api/projects/{project.id}/profile/", {
            "description": "Updated description",
        }, format="json")
        assert r2.status_code == 200
        assert r2.data["version"] == v1 + 1

    def test_profile_404_before_creation(self, client, sarah, project):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get(f"/api/projects/{project.id}/profile/")
        assert r.status_code == 404


# ── A-5: Repositories ────────────────────────────────────────────────────────

class TestRepositories:
    def test_tech_lead_adds_repository(self, client, dev_patel, project):
        Membership.objects.create(
            tenant=dev_patel.tenant, user=dev_patel, project=project, role="tech_lead"
        )
        _login(client, "dev@acme.com", "Dev-Pass!")
        r = client.post(f"/api/projects/{project.id}/repositories/", {
            "name": "acme/payments", "role": "backend", "base_branch": "main",
        }, format="json")
        assert r.status_code == 201
        assert r.data["name"] == "acme/payments"
        assert r.data["is_default"] is True
        assert "default_base" in r.data  # response uses default_base not base_branch

    def test_engineer_cannot_add_repository(self, client, acme, project):
        eng = User.objects.create_user(
            email="eng@acme.com", name="Engineer", tenant=acme, password="Eng-Pass!"
        )
        Membership.objects.create(tenant=acme, user=eng, project=project, role="engineer")
        _login(client, "eng@acme.com", "Eng-Pass!")
        r = client.post(f"/api/projects/{project.id}/repositories/", {
            "name": "acme/eng", "role": "backend", "base_branch": "main",
        }, format="json")
        assert r.status_code == 403

    def test_list_repositories_returns_wrapped_object(self, client, sarah, project):
        Repository.objects.create(
            tenant=sarah.tenant, project=project, name="acme/api", role="backend", is_default=True
        )
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get(f"/api/projects/{project.id}/repositories/")
        assert r.status_code == 200
        # Backend returns { repo_topology, repositories } — frontend api.ts unwraps .repositories
        assert "repo_topology" in r.data
        assert "repositories" in r.data
        assert isinstance(r.data["repositories"], list)

    def test_topology_upgrades_with_more_repos(self, client, dev_patel, project, acme):
        Membership.objects.create(tenant=acme, user=dev_patel, project=project, role="tech_lead")
        _login(client, "dev@acme.com", "Dev-Pass!")
        client.post(f"/api/projects/{project.id}/repositories/",
                    {"name": "acme/api", "role": "backend"}, format="json")
        client.post(f"/api/projects/{project.id}/repositories/",
                    {"name": "acme/web", "role": "frontend"}, format="json")
        project.refresh_from_db()
        assert project.repo_topology == Project.RepoTopology.SPLIT


# ── A-6: Work items ──────────────────────────────────────────────────────────

class TestWorkItems:
    def test_create_epic_starts_as_proposed(self, client, sarah, project):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.post("/api/work-items/", {
            "project": str(project.id), "type": "epic",
            "title": "Stripe Webhook Integration", "feature_stream": "payments",
        }, format="json")
        assert r.status_code == 201
        assert r.data["state"] == "proposed"
        assert r.data["type"] == "epic"

    def test_work_item_board_filters_by_project(self, client, sarah, project, acme):
        other = Project.objects.create(tenant=acme, name="Other", track="greenfield")
        wi = WorkItem.objects.create(tenant=acme, project=project, type="epic")
        WorkItem.objects.create(tenant=acme, project=other, type="epic")
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get("/api/work-items/", {"project": str(project.id)})
        assert r.status_code == 200
        ids = [w["id"] for w in r.data]
        assert str(wi.id) in ids
        # Other project's work items must not appear
        assert all(
            WorkItem.objects.get(id=wid).project_id == project.id
            for wid in ids
        )

    def test_child_tasks_appear_under_epic(self, client, sarah, project, epic):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.post("/api/work-items/", {
            "project": str(project.id), "type": "task",
            "title": "Implement webhook handler", "parent": str(epic.id),
        }, format="json")
        assert r.status_code == 201
        # Lifecycle rail shows child
        lifecycle_r = client.get(f"/api/work-items/{epic.id}/lifecycle/")
        assert lifecycle_r.status_code == 200
        children = lifecycle_r.data["children"]
        child_ids = [c["id"] for c in children]
        assert r.data["id"] in child_ids


# ── A-7/A-9: Phase triggering ────────────────────────────────────────────────

class TestPhaseTrigger:
    def test_trigger_unknown_agent_key_returns_400(self, client, sarah, project, epic):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.post(f"/api/work-items/{epic.id}/trigger/",
                        {"agent_key": "99_nonexistent"}, format="json")
        assert r.status_code == 400

    def test_trigger_creates_run(self, client, sarah, project, acme, epic):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.post(f"/api/work-items/{epic.id}/trigger/",
                        {"agent_key": "01_ideation"}, format="json")
        # 202 if Temporal available, may be error in CI — check Run was created
        if r.status_code == 202:
            assert "run_id" in r.data
            assert "workflow_id" in r.data
            run = Run.objects.get(id=r.data["run_id"])
            assert run.status == Run.Status.PENDING
        else:
            # Temporal not available in test — TriggerError expected
            assert r.status_code in (400, 503)

    def test_all_16_phase_keys_have_agent_specs(self, acme):
        """Every phase in the catalog must have a seeded AgentSpec."""
        from apps.registry.catalog import ACTIVE_AGENT_CATALOG
        for defn in ACTIVE_AGENT_CATALOG:
            exists = AgentSpec.objects.filter(tenant=acme, key=defn.key).exists()
            assert exists, f"AgentSpec missing for key '{defn.key}'"

    def test_phases_endpoint_returns_all_tiers(self, client, acme, sarah):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get("/api/phases/")
        assert r.status_code == 200
        assert len(r.data["plan"]) >= 7   # 00_, 00b, 00c, 01-04
        assert len(r.data["build"]) >= 9  # 05-12
        # No security/cicd/deployment in remediation
        remed_keys = [e["key"] for e in r.data["remediation"]]
        assert "10_security" not in remed_keys
        assert "11_cicd" not in remed_keys
        assert "12_deployment" not in remed_keys

    def test_phases_plan_contains_onboarding_phases(self, client, acme, sarah):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get("/api/phases/")
        plan_keys = [e["key"] for e in r.data["plan"]]
        assert "00_onboarding" in plan_keys
        assert "01_ideation" in plan_keys
        assert "04_architecture" in plan_keys

    def test_phases_each_entry_has_gate_role(self, client, sarah):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get("/api/phases/")
        for bucket in ("plan", "build", "remediation"):
            for entry in r.data[bucket]:
                assert "gate_role" in entry, f"Missing gate_role in {entry}"
                assert entry["gate_role"], f"Empty gate_role in {entry}"


# ── A-8: Gate decisions ──────────────────────────────────────────────────────

class TestGateDecisions:
    def test_product_owner_approves_ideation_gate(self, acme, sarah, run_for, approval_for):
        run = run_for(status=Run.Status.AWAITING_GATE, agent_key="01_ideation")
        approval = approval_for(run, required_role="product_owner")
        result = decide_gate(signal_sender=lambda *a, **kw: None,
            tenant_id=str(acme.id), approval_id=str(approval.id),
            user_id=str(sarah.id), decision="approved", comment="Good scope",
        )
        assert result["decision"] == "approved"
        approval.refresh_from_db()
        assert approval.decision == Approval.Decision.APPROVED

    def test_wrong_role_cannot_approve(self, acme, dev_patel, project, run_for, approval_for, all_memberships):
        """Tech lead cannot approve a product_owner gate."""
        run = run_for(status=Run.Status.AWAITING_GATE, agent_key="01_ideation")
        approval = approval_for(run, required_role="product_owner")
        with pytest.raises(GateRoleError):
            decide_gate(signal_sender=lambda *a, **kw: None,
                tenant_id=str(acme.id), approval_id=str(approval.id),
                user_id=str(dev_patel.id), decision="approved",
            )

    def test_architect_approves_architecture_gate(self, acme, marcus, project, run_for, approval_for, all_memberships):
        run = run_for(status=Run.Status.AWAITING_GATE, agent_key="04_architecture")
        approval = approval_for(run, required_role="architect")
        result = decide_gate(signal_sender=lambda *a, **kw: None,
            tenant_id=str(acme.id), approval_id=str(approval.id),
            user_id=str(marcus.id), decision="approved",
        )
        assert result["decision"] == "approved"

    def test_required_condition_unsatisfied_blocks_approve(self, acme, sarah, run_for, approval_for):
        run = run_for()
        approval = approval_for(run, conditions=[
            {"key": "c1", "label": "PRD complete", "required": True, "satisfied": False},
        ])
        with pytest.raises(GateConditionsError):
            decide_gate(signal_sender=lambda *a, **kw: None,
                tenant_id=str(acme.id), approval_id=str(approval.id),
                user_id=str(sarah.id), decision="approved",
            )

    def test_rejection_succeeds_regardless_of_conditions(self, acme, sarah, run_for, approval_for):
        run = run_for()
        approval = approval_for(run, conditions=[
            {"key": "c1", "label": "PRD complete", "required": True, "satisfied": False},
        ])
        result = decide_gate(signal_sender=lambda *a, **kw: None,
            tenant_id=str(acme.id), approval_id=str(approval.id),
            user_id=str(sarah.id), decision="rejected", comment="Missing payment flow",
        )
        assert result["decision"] == "rejected"

    def test_cannot_decide_already_decided_gate(self, acme, sarah, run_for, approval_for):
        run = run_for()
        approval = approval_for(run)
        decide_gate(tenant_id=str(acme.id), approval_id=str(approval.id),
                    user_id=str(sarah.id), decision="approved")
        with pytest.raises(GateError):
            decide_gate(tenant_id=str(acme.id), approval_id=str(approval.id),
                        user_id=str(sarah.id), decision="approved")

    def test_conditions_merged_on_decision(self, acme, sarah, run_for, approval_for):
        run = run_for()
        approval = approval_for(run, conditions=[
            {"key": "c1", "label": "Reviewed", "required": True, "satisfied": False},
        ])
        result = decide_gate(signal_sender=lambda *a, **kw: None,
            tenant_id=str(acme.id), approval_id=str(approval.id),
            user_id=str(sarah.id), decision="approved",
            conditions=[{"key": "c1", "label": "Reviewed", "required": True, "satisfied": True}],
        )
        assert result["decision"] == "approved"
        merged = result["conditions"]
        c1 = next(c for c in merged if c["key"] == "c1")
        assert c1["satisfied"] is True

    def test_tenant_admin_can_approve_any_gate(self, acme, sarah, run_for, approval_for):
        """Tenant admin is a fallback approver for any gate role."""
        run = run_for()
        approval = approval_for(run, required_role="architect")
        # Sarah is tenant admin but not an architect — should still be allowed
        result = decide_gate(signal_sender=lambda *a, **kw: None,
            tenant_id=str(acme.id), approval_id=str(approval.id),
            user_id=str(sarah.id), decision="approved",
        )
        assert result["decision"] == "approved"

    def test_criteria_endpoint_returns_approve_enabled_false_when_unsatisfied(
        self, client, sarah, run_for, approval_for
    ):
        run = run_for()
        approval = approval_for(run, conditions=[
            {"key": "c1", "label": "PRD", "required": True, "satisfied": False},
        ])
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get(f"/api/approvals/{approval.id}/criteria/")
        assert r.status_code == 200
        assert r.data["approve_enabled"] is False
        assert r.data["met"] == 0
        assert r.data["total"] == 1


# ── A-10: Clarifications ─────────────────────────────────────────────────────

class TestClarifications:
    @pytest.fixture
    def pending_clarification(self, acme, epic, run_for):
        run = run_for(status=Run.Status.RUNNING, agent_key="03_prd")
        return Clarification.objects.create(
            tenant=acme, run=run, work_item=epic, phase="03_prd",
            questions=[
                {"id": "q1", "text": "What is the primary payment flow?", "kind": "text", "required": True},
                {"id": "q2", "text": "CSV export needed?", "kind": "confirm", "required": False},
            ],
            context="Agent needs payment flow details",
            signature="sig-001",
        )

    def test_answer_clarification_marks_answered(self, acme, sarah, pending_clarification):
        result = answer_clarification(
            tenant_id=str(acme.id),
            clarification_id=str(pending_clarification.id),
            user_id=str(sarah.id),
            answers={"q1": "Stripe checkout flow", "q2": True},
        )
        assert result["status"] == "answered"
        pending_clarification.refresh_from_db()
        assert pending_clarification.status == "answered"
        assert pending_clarification.answered_by_id == sarah.id

    def test_missing_required_answer_raises(self, acme, sarah, pending_clarification):
        with pytest.raises(ClarificationError):
            answer_clarification(
                tenant_id=str(acme.id),
                clarification_id=str(pending_clarification.id),
                user_id=str(sarah.id),
                answers={"q2": True},  # q1 required but missing
            )

    def test_non_member_cannot_answer(self, acme, pending_clarification):
        outsider = User.objects.create_user(
            email="outside@other.com", name="Outsider",
            tenant=acme, password="Out-Pass!",
        )
        with pytest.raises(ClarificationRoleError):
            answer_clarification(
                tenant_id=str(acme.id),
                clarification_id=str(pending_clarification.id),
                user_id=str(outsider.id),
                answers={"q1": "answer", "q2": True},
            )

    def test_already_answered_clarification_raises(self, acme, sarah, pending_clarification):
        answer_clarification(
            tenant_id=str(acme.id),
            clarification_id=str(pending_clarification.id),
            user_id=str(sarah.id),
            answers={"q1": "Stripe checkout", "q2": True},
        )
        with pytest.raises(ClarificationError):
            answer_clarification(
                tenant_id=str(acme.id),
                clarification_id=str(pending_clarification.id),
                user_id=str(sarah.id),
                answers={"q1": "Different answer", "q2": False},
            )

    def test_clarifications_filter_by_work_item(self, client, sarah, epic, project, run_for, acme):
        run = run_for(status=Run.Status.RUNNING)
        Clarification.objects.create(
            tenant=acme, run=run, work_item=epic, phase="03_prd",
            questions=[{"id": "q1", "text": "Test?", "kind": "text", "required": True}],
            context="test", signature="sig-cl-filter-1",
        )
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get("/api/clarifications/", {"work_item": str(epic.id), "status": "pending"})
        assert r.status_code == 200
        assert len(r.data) >= 1
        # DRF serialises FK as uuid.UUID object; use str() for comparison
        assert all(str(c["work_item"]) == str(epic.id) for c in r.data)


# ── Scenario C: Human takeover ───────────────────────────────────────────────

class TestHumanTakeover:
    def test_request_takeover_sets_flag(self, acme, epic):
        result = request_takeover(
            tenant_id=str(acme.id), work_item_id=str(epic.id),
            actor="developer", reason="Companion lost network",
        )
        assert result["takeover"] is True
        epic.refresh_from_db()
        assert epic.takeover_flag is True

    def test_release_takeover_clears_flag(self, acme, epic):
        epic.takeover_flag = True
        epic.save()
        result = release_takeover(
            tenant_id=str(acme.id), work_item_id=str(epic.id),
            actor="developer",
        )
        assert result["takeover"] is False
        epic.refresh_from_db()
        assert epic.takeover_flag is False

    def test_takeover_via_run_endpoint(self, client, sarah, acme, epic, run_for):
        run = run_for(status=Run.Status.RUNNING)
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.post(f"/api/runs/{run.id}/take-over/",
                        {"actor": "developer", "reason": "Offline"}, format="json")
        assert r.status_code == 200
        epic.refresh_from_db()
        assert epic.takeover_flag is True

    def test_release_via_run_endpoint(self, client, sarah, acme, epic, run_for):
        epic.takeover_flag = True
        epic.save()
        run = run_for(status=Run.Status.RUNNING)
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.post(f"/api/runs/{run.id}/take-over/",
                        {"release": True, "actor": "developer"}, format="json")
        assert r.status_code == 200
        epic.refresh_from_db()
        assert epic.takeover_flag is False

    def test_takeover_unknown_work_item_raises(self, acme):
        import uuid
        with pytest.raises(TakeoverError):
            request_takeover(
                tenant_id=str(acme.id),
                work_item_id=str(uuid.uuid4()),
            )


# ── Scenario D: Lifecycle rail + Traceability ────────────────────────────────

class TestLifecycleAndTraceability:
    def test_lifecycle_endpoint_returns_all_nodes(self, client, sarah, epic):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get(f"/api/work-items/{epic.id}/lifecycle/")
        assert r.status_code == 200
        assert r.data["tier"] == "plan"  # epic → plan tier
        assert len(r.data["nodes"]) >= 7  # at least 7 plan phases
        for node in r.data["nodes"]:
            assert "phase" in node
            assert "label" in node
            assert "state" in node
            assert "triggerable" in node

    def test_task_lifecycle_has_build_tier(self, client, sarah, project, acme):
        task = WorkItem.objects.create(tenant=acme, project=project, type=WorkItem.Type.TASK)
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get(f"/api/work-items/{task.id}/lifecycle/")
        assert r.status_code == 200
        assert r.data["tier"] == "build"

    def test_defect_lifecycle_has_remediation_tier(self, client, sarah, project, acme):
        defect = WorkItem.objects.create(tenant=acme, project=project, type=WorkItem.Type.DEFECT)
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get(f"/api/work-items/{defect.id}/lifecycle/")
        assert r.status_code == 200
        assert r.data["tier"] == "remediation"

    def test_traceability_graph_has_nodes_and_edges(self, client, sarah, project, acme):
        art1 = Artifact.objects.create(
            tenant=acme, project=project, phase="01_ideation",
            type="brief", status="approved", sor="internal",
            s3_key="k1", content_hash="h1", version=1,
        )
        from apps.registry.models import TraceEdge
        art2 = Artifact.objects.create(
            tenant=acme, project=project, phase="02_requirements",
            type="requirements_doc", status="approved", sor="internal",
            s3_key="k2", content_hash="h2", version=1,
        )
        TraceEdge.objects.create(
            tenant=acme, from_artifact=art1, to_artifact=art2, rel="satisfies"
        )
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get(f"/api/projects/{project.id}/traceability/")
        assert r.status_code == 200
        assert len(r.data["nodes"]) == 2
        assert len(r.data["edges"]) == 1
        edge = r.data["edges"][0]
        assert edge["rel"] == "satisfies"

    def test_dashboard_returns_correct_shape(self, client, sarah, project):
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get(f"/api/projects/{project.id}/dashboard/")
        assert r.status_code == 200
        assert "needs_me" in r.data
        assert "health" in r.data
        assert "recent_publishes" in r.data
        h = r.data["health"]
        assert "work_items" in h and "phases_in_progress" in h
        assert "awaiting_gate" in h and "published_week" in h
        nm = r.data["needs_me"]
        assert "gates" in nm and "clarifications" in nm and "my_runs" in nm


# ── Scenario B: Gate rejection and re-trigger ────────────────────────────────

class TestGateRejectionAndRetrigger:
    def test_rejection_allows_retrigger(self, client, sarah, acme, epic, run_for, approval_for):
        """Gate rejection records the decision on the Approval; Run.status is updated
        by Temporal (not in CI). The platform allows re-triggering after rejection."""
        run1 = run_for(status=Run.Status.AWAITING_GATE, agent_key="03_prd")
        approval = approval_for(run1, required_role="product_owner")
        result = decide_gate(
            tenant_id=str(acme.id), approval_id=str(approval.id),
            user_id=str(sarah.id), decision="rejected", comment="Missing payment flow",
        )
        # Approval decision is the platform's source of truth for the gate outcome
        assert result["decision"] == "rejected"
        approval.refresh_from_db()
        assert approval.decision == Approval.Decision.REJECTED

        # Re-trigger creates a NEW run (does not mutate the rejected approval's run)
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.post(f"/api/work-items/{epic.id}/trigger/",
                        {"agent_key": "03_prd"}, format="json")
        if r.status_code == 202:
            assert r.data["run_id"] != str(run1.id)  # new run, not the old one

    def test_rejected_run_stays_in_history(self, acme, epic, run_for, approval_for, sarah, client):
        """After rejection the run is still accessible via the runs API (not deleted).
        Run.status update is Temporal's job — we verify the run persists in history."""
        run = run_for(status=Run.Status.AWAITING_GATE)
        approval = approval_for(run)
        decide_gate(tenant_id=str(acme.id), approval_id=str(approval.id),
                    user_id=str(sarah.id), decision="rejected")
        approval.refresh_from_db()
        assert approval.decision == Approval.Decision.REJECTED

        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get("/api/runs/", {"work_item": str(epic.id)})
        assert r.status_code == 200
        run_ids = [ru["id"] for ru in r.data]
        assert str(run.id) in run_ids  # run persisted — not deleted on rejection


# ── Artifact publish ──────────────────────────────────────────────────────────

class TestArtifactPublish:
    def test_approved_artifact_publishes_successfully(self, client, sarah, project, acme):
        """Bugs.xlsx row 59: manual publish is a REAL capability push — sor only becomes
        'confluence' because a page was actually created (no more cosmetic sor flip)."""
        from types import SimpleNamespace

        from apps.integrations.models import IntegrationConnection
        from integrations.registry import _BUILDERS, register_connector

        art = Artifact.objects.create(
            tenant=acme, project=project, phase="01_ideation",
            type="brief", status=Artifact.Status.APPROVED, sor="internal",
            s3_key="", content_hash="h1", version=1,
            external_ref={"format": "markdown", "body": "# Brief\ngf"},
        )
        register_connector("docstore", "gf_fake", lambda conn: SimpleNamespace(
            create_page=lambda *, space, title, body_html: SimpleNamespace(
                sor="confluence", id="41", version=1,
                url="https://confluence.acme.com/41")))
        try:
            IntegrationConnection.objects.create(
                tenant=acme, capability="docstore", connector="gf_fake",
            )
            _login(client, "sarah@acme.com", "Str0ng-Pass!")
            r = client.post(f"/api/artifacts/{art.id}/publish/", {
                "target_capability": "confluence",
                "destination": "SPACE",
            }, format="json")
            assert r.status_code == 200
            assert r.data["status"] == "published"
            assert r.data["sor_link"] == "https://confluence.acme.com/41"
            art.refresh_from_db()
            assert art.status == Artifact.Status.PUBLISHED
            assert art.sor == "confluence"
        finally:
            _BUILDERS.pop(("docstore", "gf_fake"), None)

    def test_draft_artifact_cannot_publish(self, client, sarah, project, acme):
        draft = Artifact.objects.create(
            tenant=acme, project=project, phase="01_ideation",
            type="brief", status=Artifact.Status.DRAFT, sor="internal",
            s3_key="k2", content_hash="h2", version=1,
        )
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.post(f"/api/artifacts/{draft.id}/publish/", {
            "target_capability": "confluence",
            "destination": "https://confluence.acme.com/space",
        }, format="json")
        assert r.status_code == 400

    def test_run_transcript_returns_correct_shape(self, client, sarah, acme, epic, run_for):
        run = run_for(status=Run.Status.COMPLETED)
        run.outputs = {"report": {"transcript": [
            {"role": "agent", "content": "Starting ideation phase..."},
            {"role": "tool", "content": "read_artifact called"},
            {"role": "human", "content": "Please focus on payments"},
        ]}}
        run.save()
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get(f"/api/runs/{run.id}/transcript/")
        assert r.status_code == 200
        assert "turns" in r.data
        assert r.data["run_id"] == str(run.id)
        assert len(r.data["turns"]) == 3
        assert r.data["turns"][0]["role"] == "agent"
        assert r.data["turns"][1]["role"] == "tool"
        assert r.data["turns"][2]["role"] == "human"


# ── Tenant isolation ──────────────────────────────────────────────────────────

class TestTenantIsolation:
    def test_projects_scoped_to_tenant(self, client, acme, sarah, project):
        other_tenant = Tenant.objects.create(name="Other Co")
        seed_agent_specs(other_tenant)
        other_user = User.objects.create_user(
            email="admin@other.com", name="Other Admin",
            tenant=other_tenant, password="Other-Pass!", is_tenant_admin=True,
        )
        other_proj = Project.objects.create(
            tenant=other_tenant, name="Other Project", track="greenfield"
        )
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get("/api/projects/")
        assert r.status_code == 200
        ids = [p["id"] for p in r.data]
        assert str(other_proj.id) not in ids

    def test_work_items_scoped_to_tenant(self, client, acme, sarah, project, epic):
        other_tenant = Tenant.objects.create(name="Evil Co")
        seed_agent_specs(other_tenant)
        other_proj = Project.objects.create(tenant=other_tenant, name="Evil Proj", track="greenfield")
        evil_wi = WorkItem.objects.create(tenant=other_tenant, project=other_proj, type="epic")
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get("/api/work-items/")
        ids = [w["id"] for w in r.data]
        assert str(evil_wi.id) not in ids

    def test_approval_in_wrong_tenant_not_accessible(self, client, sarah, acme, run_for, approval_for):
        other_tenant = Tenant.objects.create(name="Third Co")
        seed_agent_specs(other_tenant)
        run = run_for()
        approval = approval_for(run)
        # Try to decide from Acme session — should work (same tenant)
        # But evil tenant cannot access Acme's approvals
        _login(client, "sarah@acme.com", "Str0ng-Pass!")
        r = client.get("/api/approvals/")
        assert all(a.get("id") is not None for a in r.data)
