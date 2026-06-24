"""P2 — BuildWorkflow saga end-to-end on the live Temporal server (skips if unreachable).

Drives the durable build saga with only the CodeHost seam faked (a stub connector) — every
other piece runs for real: the workflow, the activities, the merge-gate signal, the
companion's report signal. Two paths: happy (report → PR → merge gate → merge → done) and
offline-runner takeover (no report before the timeout).
"""
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from apps.projects.models import Project, ProjectProfile, Repository
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from integrations.types import PullRequest, PullRequestRef
from orchestration import activities
from orchestration.build_activities import BUILD_ACTIVITIES
from orchestration.build_types import BuildInput, BuildReport
from orchestration.build_workflow import BuildWorkflow

_TEMPORAL = "localhost:7233"


class _FakeCodeHost:
    def __init__(self):
        self.merged = False

    def open_pull_request(self, *, repo, head, base, title, body, draft=True):
        return PullRequestRef(sor="git", repo=repo, number=7, head=head,
                              url=f"https://github.com/{repo}/pull/7", sha="abc")

    def get_pull_request(self, *, pr_ref):
        repo, number = pr_ref.split("#")
        return PullRequest(repo=repo, number=int(number), title="t", state="open",
                           head="feature/ST-1", base="main", url="u", sha="abc",
                           merged=self.merged)

    def merge_pull_request(self, *, pr_ref, method="squash"):
        self.merged = True
        return self.get_pull_request(pr_ref=pr_ref)

    def set_commit_status(self, **kw):
        pass


async def _temporal_client():
    from temporalio.client import Client

    return await Client.connect(_TEMPORAL, namespace="default")


def _run_status(run_id):
    from django.db import connection

    try:
        return Run.objects.get(id=run_id).status
    finally:
        connection.close()


def _pending_merge_approval(run_id):
    from django.db import connection

    from apps.gates.models import Approval

    try:
        ap = Approval.objects.filter(run_id=run_id, gate_type="merge_gate",
                                     decision=Approval.Decision.PENDING).first()
        return str(ap.id) if ap else None
    finally:
        connection.close()


def _approve(tenant_id, approval_id, user_id):
    from django.db import connection

    from apps.gates.services import decide_gate

    try:
        decide_gate(tenant_id=tenant_id, approval_id=approval_id, user_id=user_id,
                    decision="approved", comment="lgtm")
    finally:
        connection.close()


async def _poll(fn, *, tries=100, delay=0.2):
    for _ in range(tries):
        value = await asyncio.to_thread(fn)
        if value:
            return value
        await asyncio.sleep(delay)
    raise AssertionError("condition not met before timeout")


def _seed(report_timeout=60):
    tenant = Tenant.objects.create(name="Build Co")
    project = Project.objects.create(tenant=tenant, name="App")
    ProjectProfile.objects.create(tenant=tenant, project=project, important_context="Ship it.")
    repo = Repository.objects.create(tenant=tenant, project=project, name="acme/api",
                                     default_base="main", connector="github")
    wi = WorkItem.objects.create(tenant=tenant, project=project, repo=repo,
                                 type=WorkItem.Type.STORY, title="Add login",
                                 state=WorkItem.State.ACCEPTED, feature_stream="ST-1")
    spec = AgentSpec.objects.create(tenant=tenant, key="07_implementation", body_ref="",
                                    recommended_model="claude-x", phase_label="implementation")
    reviewer = User.objects.create_user(email="rev@build.test", name="Rev", tenant=tenant,
                                        password="pw")
    Membership.objects.create(tenant=tenant, user=reviewer, project=project, role="reviewer")
    run = Run.objects.create(tenant=tenant, work_item=wi, agent_spec=spec, engine="claude",
                             status=Run.Status.PENDING)
    run.temporal_workflow_id = f"build-run-{run.id}"
    run.save(update_fields=["temporal_workflow_id"])
    inp = BuildInput(
        run_id=str(run.id), tenant_id=str(tenant.id), project_id=str(project.id),
        work_item_id=str(wi.id), agent_spec_id=str(spec.id), work_item_key="ST-1",
        repo="acme/api", base="main", report_timeout_seconds=report_timeout,
    )
    return tenant, project, wi, run, reviewer, inp


async def _worker_ctx(client, task_queue, executor):
    from temporalio.worker import Worker

    return Worker(
        client, task_queue=task_queue, workflows=[BuildWorkflow],
        activities=activities.ALL_ACTIVITIES + BUILD_ACTIVITIES, activity_executor=executor,
    )


def _skip_if_no_temporal(monkeypatch):
    from django.conf import settings

    monkeypatch.setattr(settings, "TEMPORAL_HOST", _TEMPORAL)
    try:
        asyncio.run(_temporal_client())
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Temporal not reachable at {_TEMPORAL}: {exc}")


@pytest.mark.django_db(transaction=True)
def test_build_workflow_happy_path(monkeypatch):
    _skip_if_no_temporal(monkeypatch)
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: _FakeCodeHost())
    tenant, _project, wi, run, reviewer, inp = _seed()

    async def _drive():
        client = await _temporal_client()
        task_queue = f"build-{uuid.uuid4()}"
        with ThreadPoolExecutor(max_workers=8) as executor:
            async with await _worker_ctx(client, task_queue, executor):
                handle = await client.start_workflow(
                    BuildWorkflow.run, inp, id=f"build-run-{run.id}", task_queue=task_queue,
                )
                await _poll(lambda: _run_status(str(run.id)) == Run.Status.RUNNING)
                await handle.signal("build_reported", BuildReport(
                    status="ok", branch="feature/ST-1", head_sha="abc",
                    changed_files=["login.py"]))
                approval_id = await _poll(lambda: _pending_merge_approval(str(run.id)))
                await asyncio.to_thread(_approve, str(tenant.id), approval_id, str(reviewer.id))
                return await handle.result()

    result = asyncio.run(_drive())
    assert result["status"] == "completed"
    run.refresh_from_db()
    wi.refresh_from_db()
    assert run.status == Run.Status.COMPLETED and wi.state == WorkItem.State.DONE
    art = Artifact.objects.get(run_id=run.id, type="code")
    assert art.status == Artifact.Status.PUBLISHED and art.external_ref["number"] == 7


@pytest.mark.django_db(transaction=True)
def test_build_workflow_takeover_when_runner_never_reports(monkeypatch):
    _skip_if_no_temporal(monkeypatch)
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: _FakeCodeHost())
    _tenant, _project, wi, run, _reviewer, inp = _seed(report_timeout=2)

    async def _drive():
        client = await _temporal_client()
        task_queue = f"build-{uuid.uuid4()}"
        with ThreadPoolExecutor(max_workers=4) as executor:
            async with await _worker_ctx(client, task_queue, executor):
                handle = await client.start_workflow(
                    BuildWorkflow.run, inp, id=f"build-run-{run.id}", task_queue=task_queue,
                )
                return await handle.result()   # no report → times out → takeover

    result = asyncio.run(_drive())
    assert result["status"] == "takeover"
    wi.refresh_from_db()
    run.refresh_from_db()
    assert wi.takeover_flag is True and run.status == Run.Status.FAILED
