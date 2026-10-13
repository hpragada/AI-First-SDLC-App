"""Phase-2 acceptance slice (spec §9) — the build vertical end-to-end.

The headline (`test_acceptance_build_slice_two_repos`) runs the **real BuildWorkflow saga on a
live Temporal server** (skips if unreachable) across **two repos in one project**: for each
WorkItem a **real companion git-worktree build** (stub driver writes a clean diff; the guardrail
secret-scan + per-phase allowlist run for real) produces the report that drives
dispatch → draft PR → review → (repo A) REM-C remediation → clean re-review → **reviewer merge
gate** → merge → `done`. Along the way it asserts the load-bearing invariants: **gate-then-merge**
(no merge before APPROVED), the **CI status round-trip** and a **human-commit webhook reconcile**
(register-don't-recreate), and **multi-repo isolation** (distinct branch/PR/repo per WorkItem).

The remaining invariants are proven deterministically (no Temporal needed): idempotent recovery
of a mid-run failure, the secret-scan block, the per-phase allowlist, and tenant isolation.
"""
import asyncio
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from runner.companion.guardrails import AllowlistViolation, assert_phase_allowlist
from runner.companion.runner import BUILD_ALLOWED_TOOLS, BuildTask, run_build, to_build_report

from apps.gates.models import Approval
from apps.ledger.models import Event
from apps.projects.models import Project, ProjectProfile, Repository
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from drivers.base import RunResult
from integrations.types import PullRequest, PullRequestRef
from integrations.webhooks import reconcile_github
from orchestration import activities
from orchestration import build_activities as ba
from orchestration.build_activities import BUILD_ACTIVITIES
from orchestration.build_types import BuildInput, BuildReport
from orchestration.build_workflow import BuildWorkflow
from storage.object_store import InMemoryObjectStore

_TEMPORAL = "localhost:7233"


# ── a stateful multi-repo CodeHost fake (tracks PRs per repo, gate-then-merge) ──
class _FakeHub:
    def __init__(self):
        self._n = 0
        self.prs: dict = {}        # (repo, number) -> {"merged", "head", "base"}

    def open_pull_request(self, *, repo, head, base, title, body, draft=True):
        # Idempotent like the real connector: one open PR per (repo, head).
        for (r, n), st in self.prs.items():
            if r == repo and st["head"] == head and st["state"] == "open":
                return self._ref(r, n, head)
        self._n += 1
        self.prs[(repo, self._n)] = {"merged": False, "head": head, "base": base,
                                     "state": "open"}
        return self._ref(repo, self._n, head)

    def get_pull_request(self, *, pr_ref):
        repo, number = self._split(pr_ref)
        st = self.prs[(repo, number)]
        return PullRequest(repo=repo, number=number, title="t", state=st["state"],
                           head=st["head"], base=st["base"], url="u", sha="sha",
                           merged=st["merged"])

    def merge_pull_request(self, *, pr_ref, method="squash"):
        repo, number = self._split(pr_ref)
        self.prs[(repo, number)].update(merged=True, state="closed")
        return self.get_pull_request(pr_ref=pr_ref)

    def set_commit_status(self, **kw):
        pass

    def is_merged(self, repo, number) -> bool:
        return self.prs.get((repo, number), {}).get("merged", False)

    @staticmethod
    def _split(pr_ref):
        repo, number = pr_ref.rsplit("#", 1)
        return repo, int(number)

    def _ref(self, repo, number, head):
        return PullRequestRef(sor="git", repo=repo, number=number, head=head,
                              url=f"https://github.com/{repo}/pull/{number}", sha=f"sha-{head}")


class _ScriptedReviewer:
    """Per-WorkItem finding scripts (each key's list consumed call-by-call; last repeats)."""

    def __init__(self, scripts: dict):
        self._scripts = scripts
        self._i: dict = {}

    def review(self, inp, pr_ref):
        key = inp.work_item_key
        idx = self._i.get(key, 0)
        self._i[key] = idx + 1
        seq = self._scripts.get(key, [[]])
        return seq[min(idx, len(seq) - 1)]


class _CleanBuildDriver:
    """Stub build engine: writes a clean diff + a passing test into the worktree (no secrets)."""

    async def run_build_task(self, *, repo_workspace, **kw):
        ws = Path(repo_workspace)
        (ws / "feature.py").write_text("def add(a, b):\n    return a + b\n")
        (ws / "test_feature.py").write_text("from feature import add\n\n"
                                            "def test_add():\n    assert add(2, 3) == 5\n")
        return RunResult(outputs={"result": "built"}, artifacts=[], cost_usd=0.03,
                         raw_messages=[])


# ── git + Temporal helpers ──────────────────────────────────────────
def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)

    def git(*a):
        subprocess.run(["git", "-C", str(path), *a], check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "t@t.test")
    git("config", "user.name", "Tester")
    (path / "README.md").write_text("seed\n")
    git("add", "-A")
    git("commit", "-m", "init")
    return path


async def _temporal_client():
    from temporalio.client import Client

    return await Client.connect(_TEMPORAL, namespace="default")


def _skip_if_no_temporal(monkeypatch):
    from django.conf import settings

    monkeypatch.setattr(settings, "TEMPORAL_HOST", _TEMPORAL)
    try:
        asyncio.run(_temporal_client())
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Temporal not reachable at {_TEMPORAL}: {exc}")


def _in_conn(fn):
    from django.db import connection

    try:
        return fn()
    finally:
        connection.close()


def _run_status(run_id):
    return _in_conn(lambda: Run.objects.get(id=run_id).status)


def _pending_merge_approval(run_id):
    def q():
        ap = Approval.objects.filter(run_id=run_id, gate_type="merge_gate",
                                     decision=Approval.Decision.PENDING).first()
        return str(ap.id) if ap else None

    return _in_conn(q)


def _remediation_dispatched(run_id):
    return _in_conn(lambda: "remediation" in (Run.objects.get(id=run_id).inputs or {}))


def _approve(tenant_id, approval_id, user_id):
    from apps.gates.services import decide_gate

    _in_conn(lambda: decide_gate(tenant_id=tenant_id, approval_id=approval_id,
                                 user_id=user_id, decision="approved", comment="ship it"))


async def _poll(fn, *, tries=120, delay=0.2):
    for _ in range(tries):
        value = await asyncio.to_thread(fn)
        if value:
            return value
        await asyncio.sleep(delay)
    raise AssertionError("condition not met before timeout")


def _worker(client, task_queue, executor):
    from temporalio.worker import Worker

    return Worker(client, task_queue=task_queue, workflows=[BuildWorkflow],
                  activities=activities.ALL_ACTIVITIES + BUILD_ACTIVITIES,
                  activity_executor=executor)


# ── shared world (two repos, one project) ───────────────────────────
def _seed_two_repo_project():
    tenant = Tenant.objects.create(name="Build Co")
    project = Project.objects.create(tenant=tenant, name="App")
    ProjectProfile.objects.create(tenant=tenant, project=project, important_context="Ship it.")
    repo_a = Repository.objects.create(tenant=tenant, project=project, name="acme/api",
                                       default_base="main", connector="github")
    repo_b = Repository.objects.create(tenant=tenant, project=project, name="acme/web",
                                       default_base="main", connector="github")
    spec = AgentSpec.objects.create(tenant=tenant, key="07_implementation", body_ref="",
                                    recommended_model="claude-x", phase_label="implementation")
    reviewer = User.objects.create_user(email="rev@build.test", name="Rev", tenant=tenant,
                                        password="pw")
    Membership.objects.create(tenant=tenant, user=reviewer, project=project, role="reviewer")
    return tenant, project, repo_a, repo_b, spec, reviewer


def _work_item(tenant, project, repo, spec, key):
    wi = WorkItem.objects.create(tenant=tenant, project=project, repo=repo,
                                 type=WorkItem.Type.STORY, title=f"Story {key}",
                                 state=WorkItem.State.ACCEPTED, feature_stream=key)
    run = Run.objects.create(tenant=tenant, work_item=wi, agent_spec=spec, engine="claude",
                             status=Run.Status.PENDING)
    run.temporal_workflow_id = f"build-run-{run.id}"
    run.save(update_fields=["temporal_workflow_id"])
    inp = BuildInput(run_id=str(run.id), tenant_id=str(tenant.id), project_id=str(project.id),
                     work_item_id=str(wi.id), agent_spec_id=str(spec.id), work_item_key=key,
                     repo=repo.name, base="main", report_timeout_seconds=60)
    return wi, run, inp


def _companion_build(inp, tmp_root, idx) -> BuildReport:
    """Run the **real** companion worktree build (guardrails included) and return its report."""
    repo = _init_repo(tmp_root / f"clone{idx}")
    task = BuildTask(run_id=inp.run_id, tenant_id=inp.tenant_id, project_id=inp.project_id,
                     work_item_id=inp.work_item_id, work_item_key=inp.work_item_key,
                     repo=inp.repo, base="main", manifest="# manifest", agent_body="07 body",
                     api_url="https://platform.internal")
    out = asyncio.run(run_build(task, driver=_CleanBuildDriver(), repo_path=repo,
                                worktrees_root=tmp_root / f"wt{idx}"))
    assert out["status"] == "ok"                      # secret-scan + allowlist passed
    assert "api.github.com" in out["egress_allowed_hosts"]
    return BuildReport(**to_build_report(out))


# ── the acceptance slice (live Temporal) ────────────────────────────
@pytest.mark.usefixtures("real_gate_signal")  # approves a gate on a LOCAL workflow
@pytest.mark.django_db(transaction=True)
def test_acceptance_build_slice_two_repos(monkeypatch, tmp_path):
    _skip_if_no_temporal(monkeypatch)
    hub = _FakeHub()
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: hub)
    reviewer = _ScriptedReviewer({
        "ST-1": [[ba.Finding(rem="REM-C1", severity="critical", title="SQLi",
                             file="feature.py", line=1)], []],   # remediate, then clean
        "ST-2": [[]],                                            # clean on the first pass
    })
    monkeypatch.setattr(ba, "get_review_provider", lambda: reviewer)

    tenant, project, repo_a, repo_b, spec, rev = _seed_two_repo_project()
    wi_a, run_a, inp_a = _work_item(tenant, project, repo_a, spec, "ST-1")
    wi_b, run_b, inp_b = _work_item(tenant, project, repo_b, spec, "ST-2")

    # Real companion worktree builds (off-Temporal) → the reports that drive the saga.
    report_a = _companion_build(inp_a, tmp_path, 1)
    report_b = _companion_build(inp_b, tmp_path, 2)
    assert report_a.branch == "feature/ST-1" and report_b.branch == "feature/ST-2"

    async def _drive():
        client = await _temporal_client()
        tq = f"accept-{uuid.uuid4()}"
        with ThreadPoolExecutor(max_workers=8) as executor:
            async with _worker(client, tq, executor):
                # ---- WorkItem A (repo acme/api): build → PR → REM-C → remediate → merge ----
                ha = await client.start_workflow(BuildWorkflow.run, inp_a,
                                                 id=f"build-run-{run_a.id}", task_queue=tq)
                await _poll(lambda: _run_status(str(run_a.id)) == Run.Status.RUNNING)
                await ha.signal("build_reported", report_a)
                # Review #1 finds a critical → remediation child dispatched.
                await _poll(lambda: _remediation_dispatched(str(run_a.id)))
                # Gate-then-merge invariant: the draft PR exists but is NOT merged yet.
                assert (repo_a.name, 1) in hub.prs and not hub.is_merged(repo_a.name, 1)
                # Developer-in-the-loop: a human commit + a CI status reconcile via webhook
                # (ORM is sync — run it off the event loop).
                await asyncio.to_thread(
                    reconcile_github, tenant_id=str(tenant.id), event="push",
                    delivery_id="push-A",
                    payload={"ref": "refs/heads/feature/ST-1", "after": "human1",
                             "repository": {"full_name": repo_a.name}})
                await asyncio.to_thread(
                    reconcile_github, tenant_id=str(tenant.id), event="status",
                    delivery_id="ci-A",
                    payload={"sha": "human1", "state": "success", "context": "ci/build",
                             "repository": {"full_name": repo_a.name}})
                # Remediation build reports clean → review #2 clean → merge gate opens.
                await ha.signal("build_reported", BuildReport(status="ok", branch="feature/ST-1",
                                                              head_sha="fixed"))
                appr_a = await _poll(lambda: _pending_merge_approval(str(run_a.id)))
                assert not hub.is_merged(repo_a.name, 1)          # still gated
                await asyncio.to_thread(_approve, str(tenant.id), appr_a, str(rev.id))
                res_a = await ha.result()

                # ---- WorkItem B (repo acme/web): clean happy path (multi-repo isolation) ----
                hb = await client.start_workflow(BuildWorkflow.run, inp_b,
                                                 id=f"build-run-{run_b.id}", task_queue=tq)
                await _poll(lambda: _run_status(str(run_b.id)) == Run.Status.RUNNING)
                await hb.signal("build_reported", report_b)
                appr_b = await _poll(lambda: _pending_merge_approval(str(run_b.id)))
                await asyncio.to_thread(_approve, str(tenant.id), appr_b, str(rev.id))
                res_b = await hb.result()
                return res_a, res_b

    res_a, res_b = asyncio.run(_drive())
    assert res_a["status"] == "completed" and res_b["status"] == "completed"

    # Both WorkItems done; each merged its own repo's PR (multi-repo, no cross-contamination).
    wi_a.refresh_from_db()
    wi_b.refresh_from_db()
    assert wi_a.state == WorkItem.State.DONE and wi_b.state == WorkItem.State.DONE

    art_a = Artifact.objects.get(run_id=run_a.id, type="code")
    art_b = Artifact.objects.get(run_id=run_b.id, type="code")
    assert art_a.status == Artifact.Status.PUBLISHED and art_b.status == Artifact.Status.PUBLISHED
    assert art_a.external_ref["repo"] == "acme/api" and art_b.external_ref["repo"] == "acme/web"
    assert art_a.external_ref["number"] != art_b.external_ref["number"]   # distinct PRs
    assert hub.is_merged("acme/api", art_a.external_ref["number"])
    assert hub.is_merged("acme/web", art_b.external_ref["number"])

    # The remediation child WorkItem was opened then resolved (07<->08 loop).
    child = WorkItem.objects.get(parent_id=wi_a.id, type=WorkItem.Type.TASK)
    assert child.external_ref["rem"] == "REM-C1" and child.state == WorkItem.State.DONE

    # The human commit reconciled into A's pointer (register-don't-recreate) + CI round-tripped.
    art_a.refresh_from_db()
    assert art_a.external_ref["sha"] == "human1"
    assert Artifact.objects.filter(run_id=run_a.id, type="code").count() == 1
    assert Event.objects.filter(tenant=tenant, action="webhook.push_reconciled").exists()
    assert Event.objects.filter(tenant=tenant, action="webhook.ci_status").exists()


# ── deterministic invariants (no Temporal) ──────────────────────────
def _fake_codehost(monkeypatch):
    hub = _FakeHub()
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: hub)
    return hub


@pytest.mark.django_db
def test_acceptance_durability_idempotent_replay(monkeypatch):
    """A mid-run failure that replays the saga's steps duplicates no branch/PR/merge."""
    _fake_codehost(monkeypatch)
    tenant, project, repo_a, _b, spec, _rev = _seed_two_repo_project()
    _wi, run, inp = _work_item(tenant, project, repo_a, spec, "ST-1")
    report = BuildReport(status="ok", branch="feature/ST-1", head_sha="abc")

    ba.open_build_pr_core(inp, report)
    again = ba.open_build_pr_core(inp, report)                 # replay after a crash
    assert again.get("idempotent") is True
    assert Artifact.objects.filter(run_id=run.id, type="code").count() == 1   # no duplicate PR

    ba.open_merge_gate_core(inp)
    assert ba.merge_build_pr_core(inp)["merged"] is True
    assert ba.merge_build_pr_core(inp)["merged"] is True       # replayed merge is a no-op
    # Publishing is its own step (Bugs S.No 152) and is likewise replay-safe.
    monkeypatch.setattr(ba, "get_object_store", InMemoryObjectStore)
    ba.publish_build_artifacts_core(inp)
    ba.publish_build_artifacts_core(inp)                       # replayed publish is a no-op
    assert Artifact.objects.get(run_id=run.id, type="code").status == Artifact.Status.PUBLISHED


@pytest.mark.django_db
def test_acceptance_secret_scan_blocks_planted_credential(tmp_path):
    """A planted credential in the worktree blocks the push → reported as a failed build."""

    class _Leaky:
        async def run_build_task(self, *, repo_workspace, **kw):
            (Path(repo_workspace) / "cfg.py").write_text('AWS = "AKIAIOSFODNN7EXAMPLE"\n')
            return RunResult(outputs={}, artifacts=[], cost_usd=0.0, raw_messages=[])

    repo = _init_repo(tmp_path / "repo")
    task = BuildTask(run_id="r", tenant_id="T", project_id="p", work_item_id="w",
                     work_item_key="ST-9", repo="acme/api", base="main", manifest="m",
                     agent_body="b", api_url="https://platform.internal")
    out = asyncio.run(run_build(task, driver=_Leaky(), repo_path=repo,
                                worktrees_root=tmp_path / "wt"))
    assert out["status"] == "secret_blocked"
    assert to_build_report(out)["status"] == "failed"          # the saga dead-letters it


def test_acceptance_per_phase_allowlist_holds():
    """PG12: the build phase exposes only FS/Bash + Platform-State — never CodeHost/network."""
    assert_phase_allowlist(BUILD_ALLOWED_TOOLS, allowed=BUILD_ALLOWED_TOOLS)   # no raise
    assert not any("codehost" in t.lower() for t in BUILD_ALLOWED_TOOLS)
    with pytest.raises(AllowlistViolation):
        assert_phase_allowlist([*BUILD_ALLOWED_TOOLS, "mcp__codehost__merge_pull_request"],
                               allowed=BUILD_ALLOWED_TOOLS)


@pytest.mark.django_db
def test_acceptance_tenant_scoping_isolates_a_second_tenant(monkeypatch):
    """A second tenant sees none of the first's repos/runs/PRs (tenant-scoped reads; DB-level
    RLS enforcement is covered by test_rls.py / test_p2_data_model.py)."""
    _fake_codehost(monkeypatch)
    tenant, project, repo_a, _b, spec, _rev = _seed_two_repo_project()
    _wi, run, inp = _work_item(tenant, project, repo_a, spec, "ST-1")
    ba.open_build_pr_core(inp, BuildReport(branch="feature/ST-1", head_sha="abc"))
    owner_sha = Artifact.objects.get(run_id=run.id, type="code").external_ref["sha"]

    other = Tenant.objects.create(name="Intruder")
    assert Repository.objects.filter(tenant_id=other.id).count() == 0
    assert Run.objects.filter(tenant_id=other.id).count() == 0
    assert Artifact.objects.filter(tenant_id=other.id, type="code").count() == 0
    # The intruder's webhook for the same repo name reconciles nothing of the owner's.
    out = reconcile_github(tenant_id=str(other.id), event="push", delivery_id="x",
                           payload={"ref": "refs/heads/feature/ST-1", "after": "evil",
                                    "repository": {"full_name": "acme/api"}})
    assert out["reconciled"] == 0
    art = Artifact.objects.get(run_id=run.id, type="code")
    assert art.external_ref["sha"] == owner_sha and art.external_ref["sha"] != "evil"
