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
def test_build_endpoint_blocks_second_run_while_one_is_active(client, project, member, _no_temporal):
    """Bugs S.No 77, Case 2: re-triggering while a run is live must NOT spawn a second concurrent
    run — it returns 409 so the UI can offer 'wait / take over' instead."""
    _login(client)
    repo = Repository.objects.create(tenant=project.tenant, project=project, name="acme/api",
                                     default_base="main", is_default=True)
    wi = WorkItem.objects.create(tenant=project.tenant, project=project, repo=repo,
                                 type=WorkItem.Type.TASK, title="Implement POST /users")

    first = client.post(f"/api/work-items/{wi.id}/build/", {}, format="json")
    assert first.status_code == 202, first.data

    second = client.post(f"/api/work-items/{wi.id}/build/", {}, format="json")
    assert second.status_code == 409, second.data
    # Screen Words group 5 reworded this refusal: it no longer says "a run is already in progress
    # for this work item (status: pending)" with the stored status in brackets. What the test is
    # about is that the refusal EXPLAINS the clash and offers the way out, so that is what it now
    # checks — and that no stored key leaked into it.
    said = str(second.data).lower()
    assert "already has a run" in said, second.data
    assert "take it over" in said, second.data
    assert "awaiting_gate" not in said and "status:" not in said, second.data
    # still exactly one run — no duplicate created
    assert Run.objects.filter(work_item=wi).count() == 1


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
    # Screen Words group 5 reworded this refusal ("multiple repositories" -> "the project has
    # more than one"). What matters is unchanged: it says the repository is unchosen and points at
    # the two places it can be chosen, rather than picking one silently.
    said = str(r.data).lower()
    assert "repository" in said, r.data
    assert "more than one" in said, r.data
    assert "task breakdown gate" in said, r.data
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


# ── enrollment selection (Bugs S.No 84): dispatch must target the LIVE companion ──

def _enrollment(project, user, *, last_seen=None):
    from apps.runs.models import RunnerEnrollment
    e = RunnerEnrollment.objects.create(
        tenant=project.tenant, project=project, developer=user,
        status=RunnerEnrollment.Status.ACTIVE)
    if last_seen is not None:
        RunnerEnrollment.objects.filter(id=e.id).update(last_seen=last_seen)
        e.refresh_from_db()
    return e


@pytest.mark.django_db
def test_resolve_enrollment_prefers_newest_online_over_newer_dead_one(project, member):
    """S.No 84: a Connect-Machine visit can mint a NEWER enrollment that never connected;
    dispatching to it strands the run while the live companion polls 204s. The online
    (recently heartbeating) enrollment must win even when it is older."""
    from django.utils import timezone

    from orchestration.trigger import _resolve_enrollment

    now = timezone.now()
    stale = _enrollment(project, member, last_seen=now - timezone.timedelta(hours=3))
    live = _enrollment(project, member, last_seen=now - timezone.timedelta(seconds=30))
    dead_newest = _enrollment(project, member)   # newest, never checked in

    got = _resolve_enrollment(project.tenant_id, project.id, member.id)
    assert got.id == live.id, "must dispatch to the online companion, not the dead newest"
    assert got.id not in (dead_newest.id, stale.id)


@pytest.mark.django_db
def test_resolve_enrollment_falls_back_seen_then_newest(project, member):
    """No online enrollment: prefer one that has EVER checked in over a never-connected
    newer one; with no check-ins at all keep the old newest-first behavior (the user may
    trigger before starting the companion)."""
    from django.utils import timezone

    from orchestration.trigger import _resolve_enrollment

    now = timezone.now()
    seen_once = _enrollment(project, member, last_seen=now - timezone.timedelta(hours=5))
    never = _enrollment(project, member)          # newer but never connected
    got = _resolve_enrollment(project.tenant_id, project.id, member.id)
    assert got.id == seen_once.id

    seen_once.delete()
    got = _resolve_enrollment(project.tenant_id, project.id, member.id)
    assert got.id == never.id                     # nothing ever connected → newest overall


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
