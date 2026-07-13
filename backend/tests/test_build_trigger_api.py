"""G1 — REST surface for the build trigger (POST /api/work-items/{id}/build/).

Before this, `trigger_build` (the BuildWorkflow entry) had no HTTP endpoint — it was only
callable from tests, so a user could not start implementation on a WorkItem from the platform.
These tests pin the endpoint contract: 202 + {run_id, workflow_id}, a PENDING Run created, the
`build.triggered` event logged, and a friendly 4xx when the WorkItem has no target repo.
"""
import pytest
from rest_framework.test import APIClient

from apps.ledger.models import Event
from apps.projects.models import Project, Repository
from apps.registry.catalog import seed_agent_specs
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tenant(db):
    t = Tenant.objects.create(name="Acme")
    seed_agent_specs(t)  # registers 07_implementation so trigger_build resolves a spec
    return t


@pytest.fixture
def project(tenant):
    return Project.objects.create(tenant=tenant, name="App", track="greenfield",
                                  repo_topology="single")


@pytest.fixture
def member(tenant, project):
    u = User.objects.create_user(email="sarah@acme.com", name="Sarah", tenant=tenant,
                                 password="s3cret-pass!")
    Membership.objects.create(tenant=tenant, user=u, project=project, role="tech_lead")
    return u


def _login(client):
    r = client.post("/api/auth/login/",
                    {"email": "sarah@acme.com", "password": "s3cret-pass!"}, format="json")
    assert r.status_code == 200, r.data
    return r


@pytest.fixture(autouse=True)
def _no_temporal(monkeypatch):
    """Capture the workflow instead of connecting to Temporal — the view calls trigger_build
    with no injectable starter, so patch the module defaults it falls back to."""
    calls = []
    monkeypatch.setattr("orchestration.trigger._default_build_starter",
                        lambda wf, inp: calls.append((wf, inp)))
    monkeypatch.setattr("orchestration.trigger._default_workflow_starter",
                        lambda wf, inp: None)
    return calls


@pytest.mark.django_db
def test_build_endpoint_starts_workflow(client, project, member, _no_temporal):
    _login(client)
    repo = Repository.objects.create(tenant=project.tenant, project=project, name="acme/api",
                                     default_base="main", is_default=True)
    wi = WorkItem.objects.create(tenant=project.tenant, project=project, repo=repo,
                                 type=WorkItem.Type.TASK, title="Implement POST /users")

    r = client.post(f"/api/work-items/{wi.id}/build/", {}, format="json")

    assert r.status_code == 202, r.data
    assert "run_id" in r.data and "workflow_id" in r.data
    run = Run.objects.get(id=r.data["run_id"])
    assert run.status == Run.Status.PENDING
    assert run.work_item_id == wi.id
    # default agent is the implementation agent
    assert run.agent_spec.key == "07_implementation"
    # the workflow was started (starter captured), and the trigger was logged
    assert _no_temporal and _no_temporal[0][1].repo == "acme/api"
    assert Event.objects.filter(tenant=project.tenant, action="build.triggered",
                                target_id=str(run.id)).exists()


@pytest.mark.django_db
def test_build_endpoint_rejects_workitem_without_repo(client, project, member):
    _login(client)
    wi = WorkItem.objects.create(tenant=project.tenant, project=project,
                                 type=WorkItem.Type.TASK, title="No repo task")

    r = client.post(f"/api/work-items/{wi.id}/build/", {}, format="json")

    assert r.status_code == 400, r.data
    assert "repository" in str(r.data).lower()
    assert not Run.objects.filter(work_item=wi).exists()


@pytest.mark.django_db
def test_multi_repo_unpinned_workitem_is_rejected_not_silently_defaulted(client, project, member):
    """D5 / Hybrid Option C: on a multi-repo project a work item with NO repo must NOT silently
    build into the default repo (backend code PR'd into the frontend repo). It fails loud so the
    assignment is confirmed at the Task Breakdown gate first."""
    _login(client)
    Repository.objects.create(tenant=project.tenant, project=project, name="acme/web",
                              default_base="main", is_default=True)
    Repository.objects.create(tenant=project.tenant, project=project, name="acme/api",
                              default_base="main", is_default=False)
    wi = WorkItem.objects.create(tenant=project.tenant, project=project,
                                 type=WorkItem.Type.TASK, title="Unassigned task")

    r = client.post(f"/api/work-items/{wi.id}/build/", {}, format="json")

    assert r.status_code == 400, r.data
    assert "multiple repositories" in str(r.data).lower()
    assert not Run.objects.filter(work_item=wi).exists()


@pytest.mark.django_db
def test_multi_repo_pinned_workitem_builds_into_its_own_repo(client, project, member, _no_temporal):
    """The pinned (non-default) repo is honoured — the build routes to acme/api even though
    acme/web is the project default."""
    _login(client)
    Repository.objects.create(tenant=project.tenant, project=project, name="acme/web",
                              default_base="main", is_default=True)
    api = Repository.objects.create(tenant=project.tenant, project=project, name="acme/api",
                                    default_base="develop", is_default=False)
    wi = WorkItem.objects.create(tenant=project.tenant, project=project, repo=api,
                                 type=WorkItem.Type.TASK, title="Backend task")

    r = client.post(f"/api/work-items/{wi.id}/build/", {}, format="json")

    assert r.status_code == 202, r.data
    assert _no_temporal and _no_temporal[0][1].repo == "acme/api"
    assert _no_temporal[0][1].base == "develop"


# ── the UI phase-trigger routing: build agents → BuildWorkflow, plan agents → agent-run ──

@pytest.mark.django_db
def test_ui_trigger_routes_build_agent_to_build_workflow(client, project, member, _no_temporal):
    """Clicking Implementation on a task (POST /trigger/ with 07_implementation) must run the
    BuildWorkflow, not an agent-run — the whole point of the single UI trigger."""
    _login(client)
    Repository.objects.create(tenant=project.tenant, project=project,
                              name="acme/api", default_base="main", is_default=True)
    wi = WorkItem.objects.create(tenant=project.tenant, project=project,
                                 type=WorkItem.Type.TASK, title="Build me")

    r = client.post(f"/api/work-items/{wi.id}/trigger/",
                    {"agent_key": "07_implementation"}, format="json")

    assert r.status_code == 202, r.data
    assert r.data["workflow_id"].startswith("build-run-")     # BuildWorkflow, not agent-run
    # repo resolved from the project's default repository (work item had none)
    assert _no_temporal and _no_temporal[0][1].repo == "acme/api"


@pytest.mark.django_db
def test_ui_trigger_routes_plan_agent_to_agent_run(client, project, member, _no_temporal):
    """A planning phase (e.g. 06_task_breakdown) must still run as an agent-run, not a build."""
    _login(client)
    wi = WorkItem.objects.create(tenant=project.tenant, project=project,
                                 type=WorkItem.Type.EPIC, title="Plan me")

    r = client.post(f"/api/work-items/{wi.id}/trigger/",
                    {"agent_key": "06_task_breakdown"}, format="json")

    assert r.status_code == 202, r.data
    assert r.data["workflow_id"].startswith("agent-run-")      # planning path
    assert _no_temporal == []                                  # build starter never called


def test_rides_build_flags_match_agent_execution_model():
    """The single source of truth: only the three agents whose body says the platform
    commits/pushes/opens a PR ride the build path."""
    from apps.registry.catalog import rides_build
    assert rides_build("07_implementation")
    assert rides_build("09b_test_automation")
    assert rides_build("11_cicd")
    for plan in ("01_ideation", "05_ux_design", "06_task_breakdown", "08_code_review",
                 "09_testing", "10_security", "12_deployment"):
        assert not rides_build(plan), f"{plan} should not ride the build path"
