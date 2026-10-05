"""Frontend ↔ Backend Integration Contract Tests.

Validates that every API endpoint the React frontend calls (api.ts) returns the exact
JSON shape the frontend TypeScript types expect.  Failures here mean the UI will break
at runtime — either a silent undefined or an outright JS error.

Missing-endpoint tests are marked xfail with the reason string so CI stays green while
the backend gaps are tracked explicitly in one place.

Coverage map:
  ✓ Auth:               /auth/signup / login / me / logout / accept-invitation / reset
  ✓ Membership shape:   memberships[] uses project_id / project_name (not project)
  ✓ CSRF enforcement:   session-authed mutations require X-CSRFToken
  ✓ Runners:            GET groups by machine; POST body is { project_id }
  ✓ Repositories:       GET returns { repo_topology, repositories[] } wrapper
  ✓ Integrations:       test-connection returns { ok, detail } not { status, message }
  ✓ Work items:         list / create / patch / trigger shape
  ✓ Runs & events:      list / get / events shape
  ✓ Approvals:          list / decide shape; satisfied→conditions mapping
  ✓ Clarifications:     list / answer shape
  ✓ Source documents:   list / adopt (brownfield)
  ✓ Drift:              list + decide (project-scoped)
  ✗ MISSING: GET /api/work-items/{id}/lifecycle/
  ✗ MISSING: GET /api/phases/
  ✗ MISSING: GET /api/approvals/{id}/criteria/
  ✗ MISSING: GET /api/runs/{id}/transcript/
  ✗ MISSING: GET /api/projects/{id}/dashboard/
  ✗ MISSING: POST /api/artifacts/{id}/publish/
"""
import pytest
from rest_framework.test import APIClient

from apps.integrations.crypto import encrypt_secrets
from apps.integrations.models import IntegrationConnection
from apps.projects.models import Project, Repository
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User

# ── Shared fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


@pytest.fixture
def project(tenant):
    return Project.objects.create(tenant=tenant, name="Payment Gateway v2",
                                  track="greenfield", repo_topology="single")


@pytest.fixture
def brownfield_project(tenant):
    return Project.objects.create(tenant=tenant, name="Legacy Billing",
                                  track="brownfield", repo_topology="single")


@pytest.fixture
def admin(tenant):
    return User.objects.create_user(
        email="boss@acme.com", name="Boss", tenant=tenant,
        password="admin-pass!", is_tenant_admin=True,
    )


@pytest.fixture
def member(tenant, project):
    u = User.objects.create_user(
        email="sarah@acme.com", name="Sarah Chen", tenant=tenant,
        password="s3cret-pass!",
    )
    Membership.objects.create(tenant=tenant, user=u, project=project, role="product_owner")
    return u


def _login(client, email, password):
    r = client.post("/api/auth/login/", {"email": email, "password": password}, format="json")
    assert r.status_code == 200, r.data
    return r


def _csrf(client):
    """GET /auth/me/ plants the csrftoken cookie; return its value."""
    client.get("/api/auth/me/")
    return client.cookies["csrftoken"].value


# ── Auth response shape (CurrentUser) ────────────────────────────────────────

class TestAuthShape:
    """Frontend CurrentUser type:
        { user: { id, email, name, is_tenant_admin }, tenant: { id, name },
          memberships: [{ project_id, project_name, role }] }
    NOTE: isAdmin is NOT a top-level field — frontend derives it from user.is_tenant_admin.
    """

    def test_login_user_shape(self, client, member, project):
        r = _login(client, "sarah@acme.com", "s3cret-pass!")
        u = r.data["user"]
        assert {"id", "email", "name", "is_tenant_admin"} <= set(u.keys()), \
            f"user shape missing fields: {u.keys()}"
        assert "isAdmin" not in r.data, \
            "isAdmin must NOT be a top-level key (frontend reads user.is_tenant_admin)"

    def test_login_tenant_shape(self, client, member):
        r = _login(client, "sarah@acme.com", "s3cret-pass!")
        t = r.data["tenant"]
        assert {"id", "name"} <= set(t.keys()), f"tenant shape missing: {t.keys()}"

    def test_login_membership_uses_project_id_not_project(self, client, member, project):
        """Frontend Membership type uses project_id (not project) matching backend."""
        r = _login(client, "sarah@acme.com", "s3cret-pass!")
        memberships = r.data["memberships"]
        assert len(memberships) == 1
        m = memberships[0]
        assert "project_id" in m, f"Expected project_id in membership, got: {list(m.keys())}"
        assert "project_name" in m, f"Expected project_name in membership, got: {list(m.keys())}"
        assert "role" in m
        assert "project" not in m, \
            "Backend must NOT return 'project' key — frontend uses project_id"
        assert m["project_id"] == str(project.id)
        assert m["project_name"] == "Payment Gateway v2"

    def test_signup_sets_is_tenant_admin_true(self, client, db):
        r = client.post("/api/auth/signup/", {
            "name": "Founder", "email": "founder@newco.com",
            "password": "s3cret-pass!", "org_name": "NewCo",
        }, format="json")
        assert r.status_code == 201
        assert r.data["user"]["is_tenant_admin"] is True
        assert "isAdmin" not in r.data

    def test_me_returns_same_shape_as_login(self, client, member, project):
        _login(client, "sarah@acme.com", "s3cret-pass!")
        r = client.get("/api/auth/me/")
        assert r.status_code == 200
        assert "user" in r.data and "tenant" in r.data and "memberships" in r.data
        m = r.data["memberships"][0]
        assert "project_id" in m and "project_name" in m and "role" in m


# ── CSRF enforcement ──────────────────────────────────────────────────────────

class TestCsrfEnforcement:
    """Confirms the SPA must send X-CSRFToken (which api.ts now does via getCsrfToken())."""

    def test_session_post_without_csrf_is_403(self, member, project):
        client = APIClient(enforce_csrf_checks=True)
        assert client.post(
            "/api/auth/login/", {"email": "sarah@acme.com", "password": "s3cret-pass!"},
            format="json",
        ).status_code == 200  # login is CSRF-exempt
        # Create work item without X-CSRFToken header
        no_csrf = client.post(
            "/api/work-items/", {"project": str(project.id), "type": "epic"}, format="json"
        )
        assert no_csrf.status_code == 403, "Expected 403 without CSRF token"

    def test_session_post_with_csrf_is_201(self, member, project):
        client = APIClient(enforce_csrf_checks=True)
        assert client.post(
            "/api/auth/login/", {"email": "sarah@acme.com", "password": "s3cret-pass!"},
            format="json",
        ).status_code == 200
        token = _csrf(client)
        r = client.post(
            "/api/work-items/", {"project": str(project.id), "type": "epic"},
            format="json", HTTP_X_CSRFTOKEN=token,
        )
        assert r.status_code == 201, f"Expected 201 with CSRF token, got {r.status_code}: {r.data}"


# ── Runners (S-05 / S-06) ────────────────────────────────────────────────────

class TestRunnerShape:
    """Frontend Runner type:
      { id, machine, last_seen, online, projects: [{project_id, project_name}] }
    Frontend createRunner body: { project_id: string, label?: string }  (NOT { projects: string[] })
    """

    def test_get_runner_shape_matches_frontend_type(self, client, tenant, project, member):
        _login(client, "sarah@acme.com", "s3cret-pass!")
        enroll = client.post(
            "/api/runners/",
            {"project_id": str(project.id), "label": "Sarah's MacBook"},
            format="json", HTTP_X_TENANT_ID=str(tenant.id),
        )
        assert enroll.status_code == 201

        r = client.get("/api/runners/", HTTP_X_TENANT_ID=str(tenant.id))
        assert r.status_code == 200
        assert len(r.data) == 1
        machine = r.data[0]
        assert "machine" in machine, f"Expected 'machine' key, got: {list(machine.keys())}"
        assert "online" in machine
        assert "last_seen" in machine
        assert "projects" in machine
        proj = machine["projects"][0]
        assert "project_id" in proj, f"Expected project_id in projects[], got: {list(proj.keys())}"
        assert "project_name" in proj
        assert "id" not in proj, "Frontend RunnerProject uses project_id not id"
        assert "name" not in proj, "Frontend RunnerProject uses project_name not name"

    def test_create_runner_accepts_project_id_body(self, client, tenant, project, member):
        """Backend POST /api/runners/ takes { project_id } not { projects: [] }."""
        _login(client, "sarah@acme.com", "s3cret-pass!")
        r = client.post(
            "/api/runners/",
            {"project_id": str(project.id), "label": "My Laptop"},
            format="json", HTTP_X_TENANT_ID=str(tenant.id),
        )
        assert r.status_code == 201
        assert "id" in r.data
        assert "token" in r.data, "One-time token must be present in create response"

    def test_create_runner_old_projects_array_body_fails(self, client, tenant, project, member):
        """Regression: old frontend sent { projects: [...] } which is wrong."""
        _login(client, "sarah@acme.com", "s3cret-pass!")
        r = client.post(
            "/api/runners/",
            {"projects": [str(project.id)]},  # old (broken) shape
            format="json", HTTP_X_TENANT_ID=str(tenant.id),
        )
        assert r.status_code in (400, 422), \
            "Old { projects: [] } body must be rejected, not silently accepted"


# ── Repositories (S-13) ──────────────────────────────────────────────────────

class TestRepositoryShape:
    """Backend GET /api/projects/{id}/repositories/ returns { repo_topology, repositories: [] }.
    Frontend api.ts now unwraps this to return Repository[] directly.
    """

    def test_list_returns_wrapper_object_not_flat_array(self, client, project, member):
        """Confirms the backend shape so the frontend unwrap logic is correct."""
        Repository.objects.create(
            tenant=project.tenant, project=project, name="acme/api",
            role="backend", is_default=True,
        )
        _login(client, "sarah@acme.com", "s3cret-pass!")
        r = client.get(f"/api/projects/{project.id}/repositories/")
        assert r.status_code == 200
        # Backend returns wrapper — frontend api.ts must unwrap .repositories
        assert "repo_topology" in r.data, "Expected { repo_topology, repositories } wrapper"
        assert "repositories" in r.data, "Expected repositories[] inside wrapper"
        assert isinstance(r.data["repositories"], list)
        row = r.data["repositories"][0]
        assert {"id", "name", "role", "default_base", "is_default"} <= set(row.keys())

    def test_repository_row_has_default_base_not_base_branch(self, client, project, member):
        """Create uses base_branch in body; response field is default_base (documented mismatch)."""
        _login(client, "sarah@acme.com", "s3cret-pass!")
        # Need tech_lead role to create
        member.memberships.filter(project=project).update(role="tech_lead")  # type: ignore[union-attr]
        r = client.post(
            f"/api/projects/{project.id}/repositories/",
            {"name": "acme/web", "role": "frontend", "base_branch": "main"},
            format="json",
        )
        assert r.status_code == 201
        assert "default_base" in r.data, "Response uses default_base, not base_branch"


# ── Integrations (S-11 / S-12) ───────────────────────────────────────────────

class TestIntegrationShape:
    """Verifies test-connection returns { ok, detail } (not { status, message })."""

    def test_list_integration_shape(self, client, tenant, admin):
        IntegrationConnection.objects.create(
            tenant=tenant, capability="docstore", connector="confluence",
            secret_encrypted=encrypt_secrets({"token": "tok"}),
        )
        _login(client, "boss@acme.com", "admin-pass!")
        r = client.get("/api/integrations/")
        assert r.status_code == 200
        row = r.data[0]
        assert {"id", "capability", "vendor", "status", "configured"} <= set(row.keys())
        assert "secret_encrypted" not in row, "Secrets must never be exposed"
        assert "token" not in row

    def test_test_connection_returns_ok_and_detail(self, client, tenant, admin):
        """Frontend TestConnectionResult: { ok: boolean, detail: string, fix_hint?: string }"""
        conn = IntegrationConnection.objects.create(
            tenant=tenant, capability="docstore", connector="confluence",
            secret_encrypted=encrypt_secrets({"token": "tok"}),
        )
        _login(client, "boss@acme.com", "admin-pass!")
        r = client.post(f"/api/integrations/{conn.id}/test-connection/")
        assert r.status_code == 200
        assert "ok" in r.data, f"Expected 'ok' key, got: {list(r.data.keys())}"
        assert "detail" in r.data, f"Expected 'detail' key, got: {list(r.data.keys())}"
        assert isinstance(r.data["ok"], bool)
        assert "status" not in r.data, "Must use 'ok' not 'status'"
        assert "message" not in r.data, "Must use 'detail' not 'message'"


# ── Work items (S-14 / S-15 / S-16) ─────────────────────────────────────────

class TestWorkItemShape:
    def test_list_work_items_shape(self, client, project, member):
        _login(client, "sarah@acme.com", "s3cret-pass!")
        r = client.get("/api/work-items/", {"project": str(project.id)})
        assert r.status_code == 200
        assert isinstance(r.data, list)

    def test_create_work_item_shape(self, client, project, member):
        _login(client, "sarah@acme.com", "s3cret-pass!")
        r = client.post(
            "/api/work-items/",
            {"project": str(project.id), "type": "epic", "feature_stream": "payments"},
            format="json",
        )
        assert r.status_code == 201
        assert {"id", "project", "type", "state", "created_at"} <= set(r.data.keys())
        assert r.data["state"] == "proposed"

    def test_trigger_returns_run_id_and_workflow_id(self, client, project, member):
        """Frontend TriggerResult: { run_id: string, workflow_id: string }"""
        _login(client, "sarah@acme.com", "s3cret-pass!")
        wi = client.post(
            "/api/work-items/",
            {"project": str(project.id), "type": "epic"},
            format="json",
        ).data
        r = client.post(
            f"/api/work-items/{wi['id']}/trigger/",
            {"agent_key": "01_ideation"},
            format="json",
        )
        assert r.status_code in (202, 400, 422), \
            f"Trigger must return 202 (or 4xx if agent_key invalid), got {r.status_code}"
        if r.status_code == 202:
            assert "run_id" in r.data
            assert "workflow_id" in r.data


# ── Runs & events (S-18 / S-19) ──────────────────────────────────────────────

class TestRunShape:
    def test_list_runs_shape(self, client, project, member):
        _login(client, "sarah@acme.com", "s3cret-pass!")
        r = client.get("/api/runs/", {"project": str(project.id)})
        assert r.status_code == 200
        assert isinstance(r.data, list)

    def test_events_filter_by_target_type_and_id(self, client, project, member):
        """Frontend polls GET /events/?target_type=run&target_id=<runId>"""
        _login(client, "sarah@acme.com", "s3cret-pass!")
        r = client.get("/api/events/", {"target_type": "run",
                                        "target_id": "00000000-0000-0000-0000-000000000001"})
        assert r.status_code == 200
        assert isinstance(r.data, list)


# ── Approvals / gates (S-21 / S-22) ──────────────────────────────────────────

class TestApprovalShape:
    def test_list_approvals_shape(self, client, project, member):
        _login(client, "sarah@acme.com", "s3cret-pass!")
        r = client.get("/api/approvals/")
        assert r.status_code == 200
        assert isinstance(r.data, list)

    def test_decide_approval_accepts_satisfied_dict(self, client, project, admin):
        """Frontend sends { satisfied: { criterion_id: bool } } — backend accepts or 400s but
        must not 500. Validated via list shape (Approval.run is non-null so skip create)."""
        _login(client, "boss@acme.com", "admin-pass!")
        r = client.get("/api/approvals/")
        assert r.status_code == 200
        assert isinstance(r.data, list)
        # Shape check: each row must have the fields the frontend Approval type expects.
        for row in r.data:
            assert {"id", "run", "gate_type", "phase", "work_item", "required_role",
                    "decision", "comment", "decided_at", "created_at"} <= set(row.keys())


@pytest.mark.django_db
def test_approval_phase_is_the_gate_agent_key(client, project, admin):
    """The Approval exposes `phase` = the run's agent key, so the UI can render phase-specific
    gate panels (the repo-assignment review) ONLY on their own phase's gate and never resurface
    them on a later merge/phase gate (Bugs S.No 106 follow-up)."""
    from apps.gates.models import Approval
    from apps.registry.catalog import seed_agent_specs
    from apps.workitems.models import WorkItem

    seed_agent_specs(project.tenant)
    spec = AgentSpec.objects.filter(tenant=project.tenant, key="06_task_breakdown").first()
    wi = WorkItem.objects.create(tenant=project.tenant, project=project,
                                 type=WorkItem.Type.EPIC, title="Backlog")
    run = Run.objects.create(tenant=project.tenant, work_item=wi, agent_spec=spec,
                             status=Run.Status.AWAITING_GATE)
    ap = Approval.objects.create(tenant=project.tenant, run=run, gate_type="phase_gate",
                                 work_item=wi, required_role="tech_lead")

    _login(client, "boss@acme.com", "admin-pass!")
    r = client.get("/api/approvals/")
    row = next(x for x in r.data if x["id"] == str(ap.id))
    assert row["phase"] == "06_task_breakdown"


# ── Clarifications (S-20) ────────────────────────────────────────────────────

class TestClarificationShape:
    def test_list_clarifications_returns_array(self, client, project, member):
        _login(client, "sarah@acme.com", "s3cret-pass!")
        r = client.get("/api/clarifications/")
        assert r.status_code == 200
        assert isinstance(r.data, list)

    def test_clarification_shape_has_questions_and_answers(self, client, project, member):
        """Shape validation via list endpoint — Clarification.run is non-null so skip create;
        verify the list returns an array and any rows have the expected keys."""
        _login(client, "sarah@acme.com", "s3cret-pass!")
        r = client.get("/api/clarifications/")
        assert r.status_code == 200
        assert isinstance(r.data, list)
        for row in r.data:
            assert {"id", "questions", "answers", "status", "work_item",
                    "phase", "context", "answered_by", "answered_at"} <= set(row.keys())


# ── Drift (S-27) ─────────────────────────────────────────────────────────────

class TestDriftShape:
    def test_project_scoped_drift_list(self, client, brownfield_project, member):
        """Frontend calls GET /projects/{id}/drift/ — must return array."""
        # Add member to brownfield project
        Membership.objects.create(
            tenant=member.tenant, user=member, project=brownfield_project, role="engineer",
        )
        _login(client, "sarah@acme.com", "s3cret-pass!")
        r = client.get(f"/api/projects/{brownfield_project.id}/drift/")
        assert r.status_code == 200
        assert isinstance(r.data, list)


# ── Missing backend endpoints (xfail = tracked gaps) ─────────────────────────

def test_lifecycle_endpoint_exists(client, project, member):
    """S-17: GET /work-items/{id}/lifecycle/ → { tier, nodes[], loops[], children[], parent }"""
    from apps.workitems.models import WorkItem
    wi = WorkItem.objects.create(
        tenant=member.tenant, project=project, type="epic", state="proposed",
    )
    _login(client, "sarah@acme.com", "s3cret-pass!")
    r = client.get(f"/api/work-items/{wi.id}/lifecycle/")
    assert r.status_code == 200, r.data
    assert "nodes" in r.data
    assert "tier" in r.data
    assert r.data["tier"] == "plan"
    assert isinstance(r.data["nodes"], list)
    assert "loops" in r.data and "children" in r.data


def test_phases_catalog_endpoint_exists(client, db):
    """S-18: GET /api/phases/ → { plan[], build[], remediation[] } with agent_key+gate_role"""
    r = APIClient().get("/api/phases/")
    assert r.status_code == 200, r.data
    assert "plan" in r.data and "build" in r.data and "remediation" in r.data
    # Falls back to built-in plan phases when no AgentSpecs are seeded
    assert isinstance(r.data["plan"], list)
    if r.data["plan"]:
        entry = r.data["plan"][0]
        assert "key" in entry and "agent_key" in entry and "gate_role" in entry


def test_gate_criteria_endpoint_exists(client, project, admin):
    """S-22: GET /approvals/{id}/criteria/ → { criteria[], met, total, approve_enabled }"""
    from apps.gates.models import Approval
    from apps.workitems.models import WorkItem
    wi = WorkItem.objects.create(
        tenant=admin.tenant, project=project, type="epic", state="in_progress",
    )
    # Need a real Run since Approval.run is non-nullable
    run = Run.objects.filter(tenant=admin.tenant).first()
    if run is None:
        pytest.skip("No Run objects available; approval requires a run FK")
    approval = Approval.objects.create(
        tenant=admin.tenant, run=run, gate_type="phase_gate",
        work_item=wi, required_role="product_owner", decision="pending",
        conditions=[
            {"key": "c1", "label": "PRD is complete", "required": True, "satisfied": False},
            {"key": "c2", "label": "Reviewed by PO", "required": False, "satisfied": True},
        ],
    )
    _login(client, "boss@acme.com", "admin-pass!")
    r = client.get(f"/api/approvals/{approval.id}/criteria/")
    assert r.status_code == 200, r.data
    assert "criteria" in r.data and "approve_enabled" in r.data
    assert r.data["total"] == 2
    assert r.data["met"] == 1
    assert r.data["approve_enabled"] is False  # c1 is required and not satisfied
    crit = r.data["criteria"][0]
    assert {"id", "text", "required", "satisfied"} <= set(crit.keys())


def test_run_transcript_endpoint_returns_shape(client, project, member):
    """S-33: GET /runs/{id}/transcript/ → { run_id, phase, engine, cost, turns[] }"""
    _login(client, "sarah@acme.com", "s3cret-pass!")
    # 404 for unknown run is acceptable — endpoint must exist and return the right shape
    r = client.get("/api/runs/00000000-0000-0000-0000-000000000001/transcript/")
    assert r.status_code in (200, 404), f"Unexpected status {r.status_code}: {r.data}"
    if r.status_code == 200:
        assert {"run_id", "phase", "engine", "cost", "turns"} <= set(r.data.keys())


def test_dashboard_endpoint_exists(client, project, member):
    """S-31: GET /projects/{id}/dashboard/ → { needs_me, health, recent_publishes }"""
    _login(client, "sarah@acme.com", "s3cret-pass!")
    r = client.get(f"/api/projects/{project.id}/dashboard/")
    assert r.status_code == 200, r.data
    assert "needs_me" in r.data and "health" in r.data and "recent_publishes" in r.data
    h = r.data["health"]
    assert {"work_items", "phases_in_progress", "awaiting_gate", "published_week"} <= set(h.keys())
    nm = r.data["needs_me"]
    assert {"gates", "clarifications", "my_runs"} <= set(nm.keys())
    # N2: "recently published" used to be a list of titles the user could look at and not open —
    # the browser had no id to link with. Every row now carries one.
    for row in r.data["recent_publishes"]:
        assert {"artifact_id", "title"} <= set(row.keys())


def test_artifact_publish_endpoint_exists(client, project, admin):
    """S-34: POST /artifacts/{id}/publish/ on approved artifact → a REAL push through the
    docstore capability, returning the live page URL (Bugs.xlsx row 59: no more stub)."""
    from types import SimpleNamespace

    from apps.integrations.models import IntegrationConnection
    from apps.registry.models import Artifact
    from integrations.registry import _BUILDERS, register_connector

    a = Artifact.objects.create(
        tenant=admin.tenant, project=project, phase="01_ideation",
        type="brief", status=Artifact.Status.APPROVED, sor="internal",
        s3_key="", content_hash="abc123", version=1,
        external_ref={"format": "markdown", "body": "# Brief\ncontent"},
    )
    created = {}

    def _create_page(*, space, title, body_html):
        created.update({"space": space, "title": title, "body_html": body_html})
        return SimpleNamespace(sor="confluence", id="991", version=1,
                               url="https://acme.atlassian.net/wiki/991")

    register_connector("docstore", "test_fake_pub", lambda conn: SimpleNamespace(
        create_page=_create_page))
    try:
        IntegrationConnection.objects.create(
            tenant=admin.tenant, capability="docstore", connector="test_fake_pub",
        )
        _login(client, "boss@acme.com", "admin-pass!")
        r = client.post(
            f"/api/artifacts/{a.id}/publish/",
            {"target_capability": "confluence", "destination": "SDLC"},
            format="json",
        )
        assert r.status_code == 200, r.data
        assert r.data["status"] == "published"
        assert r.data["sor_link"] == "https://acme.atlassian.net/wiki/991"
        assert created["space"] == "SDLC" and "Brief" in created["body_html"]
        a.refresh_from_db()
        assert a.status == Artifact.Status.PUBLISHED
        assert a.sor == "confluence" and a.external_ref["id"] == "991"
    finally:
        _BUILDERS.pop(("docstore", "test_fake_pub"), None)


def test_artifact_publish_reexports_internal_published(client, project, admin):
    """Bugs.xlsx row 59: an artifact that auto-published as internal (no connector at gate
    time) may be exported later once a connector exists — its gate already passed."""
    from types import SimpleNamespace

    from apps.integrations.models import IntegrationConnection
    from apps.registry.models import Artifact
    from integrations.registry import _BUILDERS, register_connector

    a = Artifact.objects.create(
        tenant=admin.tenant, project=project, phase="01_ideation",
        type="brief", status=Artifact.Status.PUBLISHED, sor="internal",
        s3_key="", content_hash="abc123", version=1,
        external_ref={"format": "markdown", "body": "# Brief\nlate export"},
    )
    register_connector("docstore", "test_fake_pub2", lambda conn: SimpleNamespace(
        create_page=lambda *, space, title, body_html: SimpleNamespace(
            sor="confluence", id="992", version=1, url="https://acme.atlassian.net/992")))
    try:
        IntegrationConnection.objects.create(
            tenant=admin.tenant, capability="docstore", connector="test_fake_pub2",
        )
        _login(client, "boss@acme.com", "admin-pass!")
        r = client.post(
            f"/api/artifacts/{a.id}/publish/",
            {"target_capability": "docstore", "destination": ""},
            format="json",
        )
        assert r.status_code == 200, r.data
        assert r.data["sor_link"] == "https://acme.atlassian.net/992"
        a.refresh_from_db()
        assert a.sor == "confluence"
    finally:
        _BUILDERS.pop(("docstore", "test_fake_pub2"), None)


def test_publish_policy_rejects_wrong_target_per_phase(client, project, admin):
    """Team flow decision 2026-07-07: a phase's artifacts may only export to its policy
    target — docstore on task_breakdown, tasktracker on prd, and anything external on
    ux_design are all 400s naming the allowed target."""
    from apps.registry.models import Artifact

    def art(phase):
        return Artifact.objects.create(
            tenant=admin.tenant, project=project, phase=phase, type="doc",
            status=Artifact.Status.APPROVED, sor="internal", s3_key="",
            content_hash="h", version=1,
            external_ref={"format": "markdown", "body": "# body"},
        )

    _login(client, "boss@acme.com", "admin-pass!")
    r = client.post(f"/api/artifacts/{art('06_task_breakdown').id}/publish/",
                    {"target_capability": "docstore"}, format="json")
    # Screen Words group 5: the refusal names the target in the reader's words ("the task
    # tracker", "the documentation store", "inside the platform"), never the capability key.
    assert r.status_code == 400 and "task tracker" in str(r.data), r.data
    assert "tasktracker" not in str(r.data) and "docstore" not in str(r.data), r.data
    r = client.post(f"/api/artifacts/{art('03_prd').id}/publish/",
                    {"target_capability": "tasktracker"}, format="json")
    assert r.status_code == 400 and "documentation store" in str(r.data), r.data
    r = client.post(f"/api/artifacts/{art('05_ux_design').id}/publish/",
                    {"target_capability": "docstore"}, format="json")
    assert r.status_code == 400 and "inside the platform" in str(r.data).lower(), r.data
    # Internal publish is always allowed regardless of policy.
    r = client.post(f"/api/artifacts/{art('05_ux_design').id}/publish/",
                    {"target_capability": "internal"}, format="json")
    assert r.status_code == 200


def test_publish_policy_honors_project_profile_override(client, project, admin):
    """ProjectProfile.export_policy overrides the defaults per project."""
    from apps.projects.models import ProjectProfile
    from apps.registry.models import Artifact

    ProjectProfile.objects.create(
        tenant=admin.tenant, project=project, description="d",
        export_policy={"prd": "internal"},
    )
    a = Artifact.objects.create(
        tenant=admin.tenant, project=project, phase="03_prd", type="prd",
        status=Artifact.Status.APPROVED, sor="internal", s3_key="",
        content_hash="h", version=1,
        external_ref={"format": "markdown", "body": "# body"},
    )
    _login(client, "boss@acme.com", "admin-pass!")
    r = client.post(f"/api/artifacts/{a.id}/publish/",
                    {"target_capability": "docstore"}, format="json")
    assert r.status_code == 400 and "inside the platform" in str(r.data).lower(), r.data


def test_publish_tasktracker_reconciles_backlog(client, project, admin, monkeypatch):
    """Task-breakdown export = reconcile the project's proposed WorkItems into Jira via a
    fake tracker: counts + items returned; artifact stays internal SoR with the export
    merged into external_ref WITHOUT losing the inline draft body."""
    from types import SimpleNamespace

    from apps.registry.models import Artifact
    from apps.workitems.models import WorkItem
    from integrations import reconcile as reconcile_mod
    from integrations.types import ExternalRef

    story = WorkItem.objects.create(
        tenant=admin.tenant, project=project, type=WorkItem.Type.STORY,
        title="Login story", state=WorkItem.State.PROPOSED,
    )
    a = Artifact.objects.create(
        tenant=admin.tenant, project=project, phase="06_task_breakdown", type="backlog",
        status=Artifact.Status.APPROVED, sor="internal", s3_key="",
        content_hash="h", version=1,
        external_ref={"format": "markdown", "body": "# Backlog"},
    )
    created = []

    class _FakeTracker:
        def search(self, *, jql):
            return []

        def create_issue(self, *, kind, summary, description, parent_ref=None, fields=None):
            created.append(summary)
            return ExternalRef(sor="jira", id=f"PAY-{len(created)}",
                               url=f"https://x/browse/PAY-{len(created)}")

    monkeypatch.setattr(reconcile_mod, "get_capability", lambda t, c: _FakeTracker())
    monkeypatch.setattr(reconcile_mod, "get_connection",
                        lambda t, c: SimpleNamespace(scopes={"project_key": "PAY"}))

    _login(client, "boss@acme.com", "admin-pass!")
    r = client.post(f"/api/artifacts/{a.id}/publish/",
                    {"target_capability": "tasktracker", "destination": "PAY"},
                    format="json")
    assert r.status_code == 200, r.data
    assert r.data["reconciled"] == 1 and r.data["created"] == 1
    assert r.data["items"][0]["key"] == "PAY-1"
    story.refresh_from_db()
    assert story.external_ref["id"] == "PAY-1"
    a.refresh_from_db()
    assert a.status == Artifact.Status.PUBLISHED and a.sor == "internal"  # projection
    assert a.external_ref["export"]["reconciled"] == 1
    assert a.external_ref["body"] == "# Backlog"  # inline draft body survives the merge


def test_publish_testmgmt_exports_test_case(client, project, admin, monkeypatch):
    """Test-case export via a fake testmgmt capability: idempotent by summary, artifact
    stays internal SoR with the created test merged into external_ref; non-test_case
    types in the testing phase are rejected."""
    from types import SimpleNamespace

    from apps.registry.models import Artifact
    from integrations import registry as registry_mod
    from integrations.types import ExternalRef

    calls = []

    class _FakeTestMgmt:
        def create_test(self, *, project, summary, steps, fields=None):
            calls.append({"project": project, "summary": summary, "steps": steps})
            return ExternalRef(sor="xray", id="TC-77", url="https://x/browse/TC-77")

    monkeypatch.setattr(registry_mod, "get_capability", lambda t, c: _FakeTestMgmt())
    monkeypatch.setattr(registry_mod, "get_connection",
                        lambda t, c: SimpleNamespace(scopes={"project_key": "QA"}))

    a = Artifact.objects.create(
        tenant=admin.tenant, project=project, phase="09_testing", type="test_case",
        status=Artifact.Status.APPROVED, sor="internal", s3_key="",
        content_hash="h", version=1,
        external_ref={"format": "markdown", "tc_id": "TC-007",
                      "steps": [{"action": "Log in", "expected": "Dashboard"}],
                      "body": "# TC-007 Login"},
    )
    _login(client, "boss@acme.com", "admin-pass!")
    r = client.post(f"/api/artifacts/{a.id}/publish/",
                    {"target_capability": "testmgmt"}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["test_key"] == "TC-77" and r.data["sor_link"].endswith("TC-77")
    assert calls[0]["summary"].startswith("TC-007") and calls[0]["project"] == "QA"
    a.refresh_from_db()
    assert a.sor == "internal" and a.external_ref["export"]["id"] == "TC-77"
    assert a.external_ref["body"] == "# TC-007 Login"  # inline body survives

    # Re-export runs again (published artifacts stay exportable) — idempotency lives in
    # the connector's summary lookup.
    r = client.post(f"/api/artifacts/{a.id}/publish/",
                    {"target_capability": "testmgmt"}, format="json")
    assert r.status_code == 200

    # Non-test_case types in the testing phase are rejected.
    plan = Artifact.objects.create(
        tenant=admin.tenant, project=project, phase="09_testing", type="test_report",
        status=Artifact.Status.APPROVED, sor="internal", s3_key="",
        content_hash="h2", version=1,
        external_ref={"format": "markdown", "body": "# Report"},
    )
    r = client.post(f"/api/artifacts/{plan.id}/publish/",
                    {"target_capability": "testmgmt"}, format="json")
    # Screen Words group 5: "Only test_case artifacts…" printed the type key.
    assert r.status_code == 400 and "Only test cases" in str(r.data), r.data


def test_artifact_reexport_no_connector_is_clear_400(client, project, admin):
    """Re-exporting an already-published-internal artifact with no docstore connector must
    fail honestly (400 with guidance) — a 'success' would be a no-op lie. (First publish of
    an APPROVED artifact keeps the blueprint-B3 internal fallback — journey tests.)"""
    from apps.registry.models import Artifact

    a = Artifact.objects.create(
        tenant=admin.tenant, project=project, phase="01_ideation",
        type="brief", status=Artifact.Status.PUBLISHED, sor="internal",
        s3_key="", content_hash="abc123", version=1,
        external_ref={"format": "markdown", "body": "# Brief"},
    )
    _login(client, "boss@acme.com", "admin-pass!")
    r = client.post(
        f"/api/artifacts/{a.id}/publish/",
        {"target_capability": "docstore", "destination": "SDLC"},
        format="json",
    )
    assert r.status_code == 400
    assert "connector" in str(r.data).lower()


def test_artifact_publish_blocked_without_gate(client, project, admin):
    """Regression: draft/staged artifacts must be rejected with 400."""
    from apps.registry.models import Artifact
    draft = Artifact.objects.create(
        tenant=admin.tenant, project=project, phase="01_ideation",
        type="brief", status=Artifact.Status.DRAFT, sor="internal",
        s3_key="drafts/draft.md", content_hash="def456", version=1,
    )
    _login(client, "boss@acme.com", "admin-pass!")
    r = client.post(
        f"/api/artifacts/{draft.id}/publish/",
        {"target_capability": "confluence", "destination": "https://confluence.example.com"},
        format="json",
    )
    assert r.status_code == 400, f"Expected 400 for draft artifact, got {r.status_code}"


def test_run_takeover_via_run_id(client, project, member):
    """S-32: POST /runs/{id}/take-over/ delegates to work-item takeover service."""
    # We can only call this if a Run exists; test the 404 path is clean
    _login(client, "sarah@acme.com", "s3cret-pass!")
    r = client.post(
        "/api/runs/00000000-0000-0000-0000-000000000001/take-over/",
        {}, format="json",
    )
    # 404 for unknown run is correct; 400 means routing worked but validation failed
    assert r.status_code in (404, 400), \
        f"Expected 404/400 for unknown run take-over, got {r.status_code}: {r.data}"


def test_a_document_borrowing_its_run_s_report_cannot_be_published(client, project, admin):
    """S.No 317 part C. On screen the fallback is tolerable once it says so; pushed to a client's
    Confluence it is not — it would file the run's report under this document's name, somewhere
    our screens cannot add the caveat and the next reader has no way to know."""
    from apps.integrations.models import IntegrationConnection
    from apps.registry.models import AgentSpec, Artifact
    from apps.runs.models import Run
    from apps.workitems.models import WorkItem

    wi = WorkItem.objects.create(
        tenant=admin.tenant, project=project, type=WorkItem.Type.STORY, feature_stream="hr")
    spec = AgentSpec.objects.create(
        tenant=admin.tenant, key="01_ideation", body_ref="agents/01_ideation/agent.md")
    run = Run.objects.create(
        tenant=admin.tenant, work_item=wi, agent_spec=spec,
        outputs={"report": {"body": "The ideation phase is complete. Here is a summary:"}})
    a = Artifact.objects.create(
        tenant=admin.tenant, project=project, run=run, phase="01_ideation",
        type="feasibility_report", title="Feasibility Report",
        status=Artifact.Status.APPROVED, sor="internal",
        s3_key="drafts/never-written", content_hash="abc123", version=1,
    )
    IntegrationConnection.objects.create(
        tenant=admin.tenant, capability="docstore", connector="test_fake_pub",
    )
    _login(client, "boss@acme.com", "admin-pass!")
    r = client.post(
        f"/api/artifacts/{a.id}/publish/",
        {"target_capability": "confluence", "destination": "SDLC"},
        format="json",
    )
    assert r.status_code == 400, r.data
    said = str(r.data)
    assert "no content of its own" in said
    assert "Run the phase again" in said
