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

# These tests approve gates on a real LOCAL workflow, so a decision must really signal it (see
# `real_gate_signal` in conftest.py). `_skip_if_no_temporal` points TEMPORAL_HOST at localhost.
pytestmark = pytest.mark.usefixtures("real_gate_signal")


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


class _ConflictThenCleanCodeHost:
    """Merge is 'dirty' (conflict) on the FIRST attempt, then 'clean' after the reviewer
    re-approves — models resolving the conflict in GitHub between approvals (S.No 141 ENH-2)."""

    def __init__(self):
        self.merged = False
        self.attempt = 0

    def open_pull_request(self, *, repo, head, base, title, body, draft=True):
        return PullRequestRef(sor="git", repo=repo, number=7, head=head,
                              url=f"https://github.com/{repo}/pull/7", sha="abc")

    def get_pull_request(self, *, pr_ref):
        repo, number = pr_ref.split("#")
        return PullRequest(repo=repo, number=int(number), title="t", state="open",
                           head="feature/ST-1", base="main", url="u", sha="abc",
                           merged=self.merged)

    def mark_ready_for_review(self, *, pr_ref):
        pass

    def ensure_mergeable(self, *, pr_ref):
        self.attempt += 1
        dirty = self.attempt == 1
        return PullRequest(repo="acme/api", number=7, title="t", state="open",
                           head="feature/ST-1", base="main", url="u", sha="abc",
                           merged=self.merged, mergeable=not dirty,
                           mergeable_state="dirty" if dirty else "clean")

    def merge_pull_request(self, *, pr_ref, method="squash"):
        self.merged = True
        return self.get_pull_request(pr_ref=pr_ref)

    def set_commit_status(self, **kw):
        pass


class _MergeErrorThenOkCodeHost(_FakeCodeHost):
    """The merge fails with a NON-conflict error on the first attempt, then succeeds — models a
    transient upstream/permission failure the user fixes before hitting Resume (S.No 157)."""

    def __init__(self):
        super().__init__()
        self.attempt = 0

    def mark_ready_for_review(self, *, pr_ref):
        pass

    def ensure_mergeable(self, *, pr_ref):
        return PullRequest(repo="acme/api", number=7, title="t", state="open",
                           head="feature/ST-1", base="main", url="u", sha="abc",
                           merged=self.merged, mergeable=True, mergeable_state="clean")

    def merge_pull_request(self, *, pr_ref, method="squash"):
        self.attempt += 1
        if self.attempt == 1:
            raise RuntimeError("GitHub PUT /pulls/7/merge -> 403 (branch protection)")
        self.merged = True
        return self.get_pull_request(pr_ref=pr_ref)


def _parked(run_id):
    """The run is parked at a resumable error (S.No 157)."""
    from django.db import connection

    try:
        run = Run.objects.get(id=run_id)
        return (run.status == Run.Status.STALLED
                and bool((run.outputs or {}).get("resumable")))
    finally:
        connection.close()


def _merge_conflict_recorded(run_id):
    from django.db import connection

    try:
        return bool((Run.objects.get(id=run_id).outputs or {}).get("merge_conflict"))
    finally:
        connection.close()


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


def _remediation_dispatched(run_id):
    from django.db import connection

    try:
        return "remediation" in (Run.objects.get(id=run_id).inputs or {})
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


def _request_changes(tenant_id, approval_id, user_id, direction):
    """"Request changes" on the merge gate: recorded as a rejection, but the build revises in
    place instead of ending."""
    from django.db import connection

    from apps.gates.services import decide_gate

    try:
        decide_gate(tenant_id=tenant_id, approval_id=approval_id, user_id=user_id,
                    decision="rejected", comment=direction, revise=True)
    finally:
        connection.close()


def _review_history(run_id):
    from django.db import connection

    try:
        run = Run.objects.filter(id=run_id).only("inputs").first()
        return list((run.inputs or {}).get("review_history") or []) if run else []
    finally:
        connection.close()


def _use_a_real_gate_signal(monkeypatch):
    """Undo the project-wide no-op gate signal for a saga test.

    `conftest._noop_gate_signal_sender` is autouse and replaces the Temporal signal with a no-op
    so gate tests can run without a cluster. That is right for unit tests and fatal here: these
    tests drive the REAL workflow, so a swallowed `gate_decision` leaves the saga waiting at the
    merge gate forever and `handle.result()` never returns. Restore a sender that actually
    signals the cluster this test is talking to.
    """
    import apps.gates.services as _gate_svc
    from orchestration.types import GateDecision

    def _send(workflow_id, decision, approver_id, comment, revise=False):
        async def _go():
            from temporalio.client import Client

            client = await Client.connect(_TEMPORAL, namespace="default")
            await client.get_workflow_handle(workflow_id).signal(
                "gate_decision",
                GateDecision(decision=decision, approver_id=approver_id, comment=comment,
                             revise=revise),
            )

        asyncio.run(_go())

    monkeypatch.setattr(_gate_svc, "_default_signal_sender", _send)


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
def test_build_workflow_remediation_loop(monkeypatch):
    """Review finds a critical → remediation build → re-review clean → merge gate → merged."""
    _skip_if_no_temporal(monkeypatch)
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: _FakeCodeHost())

    from orchestration import build_activities as ba

    scripts = [[ba.Finding(rem="REM-C1", severity="critical", title="bug")], []]
    state = {"i": 0}

    class _Rev:
        def review(self, inp, pr_ref):
            out = scripts[min(state["i"], len(scripts) - 1)]
            state["i"] += 1
            return out

    monkeypatch.setattr(ba, "get_review_provider", lambda: _Rev())
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
                    status="ok", branch="feature/ST-1", head_sha="abc"))
                # Review #1 finds a critical → remediation dispatched; report the fix.
                await _poll(lambda: _remediation_dispatched(str(run.id)))
                await handle.signal("build_reported", BuildReport(
                    status="ok", branch="feature/ST-1", head_sha="def"))
                # Review #2 is clean → merge gate.
                approval_id = await _poll(lambda: _pending_merge_approval(str(run.id)))
                await asyncio.to_thread(_approve, str(tenant.id), approval_id, str(reviewer.id))
                return await handle.result()

    result = asyncio.run(_drive())
    assert result["status"] == "completed"
    child = WorkItem.objects.get(parent_id=wi.id, type=WorkItem.Type.TASK)
    assert child.external_ref["rem"] == "REM-C1" and child.state == WorkItem.State.DONE


@pytest.mark.django_db(transaction=True)
def test_build_workflow_a_review_that_never_ran_parks_then_resumes_only_the_review(monkeypatch):
    """Bugs S.No 266: a review the companion reports as FAILED (the engine died before a verdict)
    must never pass as a clean review. The run parks, resumable, with no merge gate opened; Resume
    re-runs ONLY the review — the build is not re-dispatched — and a clean re-review then reaches
    the merge gate as normal."""
    _skip_if_no_temporal(monkeypatch)
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: _FakeCodeHost())

    from orchestration import build_activities as ba
    from orchestration.review_provider import ReviewUnavailableError

    calls = {"review": 0}

    class _DiesOnceThenClean:
        def review(self, inp, pr_ref):
            calls["review"] += 1
            if calls["review"] == 1:
                raise ReviewUnavailableError("code review did not complete: session limit")
            return []

    monkeypatch.setattr(ba, "get_review_provider", lambda: _DiesOnceThenClean())
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
                await _poll(lambda: _parked(str(run.id)))
                assert await handle.query("status") == "parked"
                # Parked on the review: no merge gate was opened over the review that never ran.
                assert await asyncio.to_thread(_pending_merge_approval, str(run.id)) is None
                await handle.signal("resume_run")
                approval_id = await _poll(lambda: _pending_merge_approval(str(run.id)))
                await asyncio.to_thread(_approve, str(tenant.id), approval_id, str(reviewer.id))
                return await handle.result()

    result = asyncio.run(_drive())
    assert result["status"] == "completed"
    assert calls["review"] == 2          # the review ran again on resume, once
    run.refresh_from_db()
    assert run.status == Run.Status.COMPLETED
    # Resume did not rebuild: exactly one code artifact, from the one build.
    assert Artifact.objects.filter(run_id=run.id, type="code").count() == 1


@pytest.mark.django_db(transaction=True)
def test_build_workflow_merge_conflict_reopens_gate_then_retries(monkeypatch):
    """S.No 141 ENH-2: a merge conflict does NOT end the build. The merge gate re-opens; after the
    reviewer 'resolves' (fake flips clean) and approves AGAIN, the merge retries and completes —
    no rebuild, no re-review."""
    _skip_if_no_temporal(monkeypatch)
    codehost = _ConflictThenCleanCodeHost()
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: codehost)
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
                # 1st approval → merge hits a conflict → gate re-opens (not failed).
                approval_id = await _poll(lambda: _pending_merge_approval(str(run.id)))
                await asyncio.to_thread(_approve, str(tenant.id), approval_id, str(reviewer.id))
                await _poll(lambda: _merge_conflict_recorded(str(run.id)))
                assert _run_status(str(run.id)) == Run.Status.AWAITING_GATE   # recoverable
                # Reviewer resolved it in GitHub (fake now clean) + approves AGAIN → merge retries.
                approval_id = await _poll(lambda: _pending_merge_approval(str(run.id)))
                await asyncio.to_thread(_approve, str(tenant.id), approval_id, str(reviewer.id))
                return await handle.result()

    result = asyncio.run(_drive())
    assert result["status"] == "completed"
    run.refresh_from_db()
    wi.refresh_from_db()
    assert run.status == Run.Status.COMPLETED and wi.state == WorkItem.State.DONE
    assert codehost.merged is True and codehost.attempt == 2   # conflicted once, then merged


@pytest.mark.django_db(transaction=True)
def test_build_workflow_request_changes_revises_in_place_then_merges(monkeypatch):
    """"Request changes" on the MERGE gate must NOT end the build and must NOT start a second one.

    At this point the branch is pushed and the draft PR is open. Cutting a fresh build would open
    a SECOND pull request and orphan the first (nothing closes it), and tear down the preview the
    reviewer is looking at. So the revision rides the same run/branch/PR: re-dispatch → new report
    → PR reconciled → code review re-run → gate re-opened → approve → merge.

    Re-running review is the point. The reviewer asked for a change; a change nobody reviewed is
    exactly what the merge gate exists to prevent."""
    _skip_if_no_temporal(monkeypatch)
    _use_a_real_gate_signal(monkeypatch)
    codehost = _FakeCodeHost()
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: codehost)
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
                # First gate: the reviewer wants something changed.
                approval_id = await _poll(lambda: _pending_merge_approval(str(run.id)))
                await asyncio.to_thread(
                    _request_changes, str(tenant.id), approval_id, str(reviewer.id),
                    "Use the shared session helper instead of rolling a new one.")
                # The build goes back to RUNNING on the SAME run — not rejected, not a new run.
                await _poll(lambda: _run_status(str(run.id)) == Run.Status.RUNNING)
                await handle.signal("build_reported", BuildReport(
                    status="ok", branch="feature/ST-1", head_sha="def",
                    changed_files=["login.py"]))
                # Gate re-opens on the same run; approve for real this time.
                approval_id = await _poll(lambda: _pending_merge_approval(str(run.id)))
                await asyncio.to_thread(_approve, str(tenant.id), approval_id, str(reviewer.id))
                return await handle.result()

    result = asyncio.run(_drive())
    assert result["status"] == "completed"
    run.refresh_from_db()
    assert run.status == Run.Status.COMPLETED
    # Exactly ONE run for this work item — a revision must never fork a second build.
    assert Run.objects.filter(work_item_id=wi.id).count() == 1
    # The reviewer's words are carried on the run so the next dispatch can put them in the manifest.
    history = _review_history(str(run.id))
    assert len(history) == 1
    assert "shared session helper" in history[0]["direction"]


@pytest.mark.django_db(transaction=True)
def test_build_workflow_merge_error_parks_then_resumes_without_rebuilding(monkeypatch):
    """S.No 157: a NON-conflict merge error no longer ends the build. The run parks (STALLED +
    resumable + a reason) with the workflow still alive; `resume_run` retries the merge under the
    same approval and completes — the build is never re-dispatched."""
    _skip_if_no_temporal(monkeypatch)
    codehost = _MergeErrorThenOkCodeHost()
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: codehost)
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
                # The merge errors → parked, NOT failed, and the workflow is still alive.
                await _poll(lambda: _parked(str(run.id)))
                assert await handle.query("status") == "parked"
                await handle.signal("resume_run")
                return await handle.result()

    result = asyncio.run(_drive())
    assert result["status"] == "completed"
    run.refresh_from_db()
    wi.refresh_from_db()
    assert run.status == Run.Status.COMPLETED and wi.state == WorkItem.State.DONE
    assert codehost.merged is True and codehost.attempt == 2   # errored once, then merged
    # The park markers are cleared on resume, so the console shows no stale failure.
    assert "error" not in (run.outputs or {}) and "resumable" not in (run.outputs or {})


@pytest.mark.django_db(transaction=True)
def test_build_workflow_parked_build_abandons_terminally(monkeypatch):
    """S.No 157: Take over on a parked run ends it exactly as the old fail-and-return did —
    FAILED, with the reason kept and the WorkItem handed back for human disposition."""
    _skip_if_no_temporal(monkeypatch)
    codehost = _MergeErrorThenOkCodeHost()
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: codehost)
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
                await _poll(lambda: _parked(str(run.id)))
                await handle.signal("abandon_run")
                return await handle.result()

    result = asyncio.run(_drive())
    assert result["status"] == "build_failed"
    run.refresh_from_db()
    wi.refresh_from_db()
    assert run.status == Run.Status.FAILED
    # The reason is kept and classified (S.No 139) — plain language, not a raw 403.
    assert "branch protection" in (run.outputs or {}).get("error", "")
    assert wi.state == WorkItem.State.IN_PROGRESS               # handed back, as before


@pytest.mark.django_db(transaction=True)
def test_build_workflow_empty_build_fails_terminally_and_is_never_parked(monkeypatch):
    """S.No 157: an EMPTY BUILD is not resumable — the agent produced no changes, so resuming
    would fail identically forever. It must stay a terminal failure with its clear reason, never
    park and offer a Resume that cannot work."""
    _skip_if_no_temporal(monkeypatch)
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: _FakeCodeHost())
    _tenant, _project, wi, run, _reviewer, inp = _seed()

    async def _drive():
        client = await _temporal_client()
        task_queue = f"build-{uuid.uuid4()}"
        with ThreadPoolExecutor(max_workers=8) as executor:
            async with await _worker_ctx(client, task_queue, executor):
                handle = await client.start_workflow(
                    BuildWorkflow.run, inp, id=f"build-run-{run.id}", task_queue=task_queue,
                )
                await _poll(lambda: _run_status(str(run.id)) == Run.Status.RUNNING)
                # No head_sha / no changed files → open_build_pr raises EmptyBuild.
                await handle.signal("build_reported", BuildReport(
                    status="ok", branch="feature/ST-1", head_sha="", changed_files=[]))
                return await handle.result()

    result = asyncio.run(_drive())
    assert result["status"] == "build_failed"
    run.refresh_from_db()
    assert run.status == Run.Status.FAILED                       # terminal, not STALLED
    assert not (run.outputs or {}).get("resumable")              # no Resume offered
    assert "no changes" in (run.outputs or {}).get("error", "").lower()


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


@pytest.mark.django_db(transaction=True)
def test_dispatch_reviewer_revision_rearms_the_build_in_place(monkeypatch):
    """The activity behind "Request changes" on a merge gate, without Temporal: it must re-arm
    the companion claim, put the run back to RUNNING, reset the gate to PENDING, and record the
    reviewer's words on the run."""
    from apps.gates.models import Approval
    from orchestration.build_activities import dispatch_reviewer_revision_core

    tenant, _project, wi, run, reviewer, inp = _seed()
    Approval.objects.create(
        tenant_id=tenant.id, run_id=run.id, work_item_id=wi.id, gate_type="merge_gate",
        required_role=inp.required_role, decision=Approval.Decision.REJECTED,
        comment="Use the shared session helper.",
    )
    out = dispatch_reviewer_revision_core(inp, "Use the shared session helper.")
    assert out["dispatched"] is True and out["revision"] == 1

    run.refresh_from_db()
    assert run.status == Run.Status.RUNNING
    assert (run.inputs or {}).get("dispatch", {}).get("status") == "pending"
    history = (run.inputs or {}).get("review_history") or []
    assert len(history) == 1 and "shared session helper" in history[0]["direction"]
    assert "# Reviewer Direction" in run.inputs["build_task"]["manifest"]
    # The gate must be re-opened, or decide_gate refuses the next decision and the reviewer is
    # locked out of their own gate for good.
    assert Approval.objects.get(run_id=run.id).decision == Approval.Decision.PENDING
