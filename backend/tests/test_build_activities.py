"""P2 — BuildWorkflow activity cores (idempotent; CodeHost via the capability seam).

Pure activity-core tests (no Temporal): dispatch, open-PR, merge, gate, takeover/fail
compensation. CodeHost is a fake injected through `get_capability`.
"""
from types import SimpleNamespace

import pytest

from apps.gates.models import Approval
from apps.projects.models import Project, ProjectProfile
from apps.registry.models import AgentSpec, Artifact, TraceEdge
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from integrations.types import PullRequest, PullRequestRef
from orchestration import build_activities as ba
from orchestration.build_types import BuildInput, BuildReport


class _FakeCodeHost:
    def __init__(self):
        self.merged = False
        self.statuses = []

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
        self.statuses.append(kw)


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    ProjectProfile.objects.create(tenant=t, project=p, important_context="Ship it.")
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY, title="Add login",
                                 state=WorkItem.State.ACCEPTED, feature_stream="ST-1")
    spec = AgentSpec.objects.create(tenant=t, key="07_implementation", body_ref="",
                                    recommended_model="claude-x", phase_label="implementation")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec, engine="claude",
                             status=Run.Status.PENDING)
    return SimpleNamespace(t=t, p=p, wi=wi, spec=spec, run=run)


def _inp(world, **over):
    base = dict(run_id=str(world.run.id), tenant_id=str(world.t.id), project_id=str(world.p.id),
                work_item_id=str(world.wi.id), agent_spec_id=str(world.spec.id),
                work_item_key="ST-1", repo="acme/api", base="main")
    base.update(over)
    return BuildInput(**base)


def _use_fake_codehost(monkeypatch, fake):
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: fake)


def test_dispatch_assembles_payload_and_marks_running(world):
    ba.dispatch_build_core(_inp(world))
    world.run.refresh_from_db()
    assert world.run.status == Run.Status.RUNNING
    payload = world.run.inputs["build_task"]
    assert payload["repo"] == "acme/api" and payload["work_item_key"] == "ST-1"
    assert payload["manifest"]                       # composed manifest shipped to the companion
    # G2: WorkItem title/type travel so the companion derives the Conventional-Commit message.
    assert payload["work_item_title"] == "Add login" and payload["work_item_type"] == "story"


def test_dispatch_sets_claim_block_for_companion(world):
    ba.dispatch_build_core(_inp(world, enrollment_id="enr-9"))
    world.run.refresh_from_db()
    assert world.run.inputs["dispatch"] == {
        "kind": "build", "enrollment_id": "enr-9", "status": "pending"}


def test_open_pr_registers_code_pointer_and_is_idempotent(world, monkeypatch):
    fake = _FakeCodeHost()
    _use_fake_codehost(monkeypatch, fake)
    report = BuildReport(status="ok", branch="feature/ST-1", head_sha="abc",
                         changed_files=["login.py"])
    out = ba.open_build_pr_core(_inp(world), report)
    assert out["pr"]["number"] == 7
    art = Artifact.objects.get(run_id=world.run.id, type="code")
    assert art.sor == "git" and art.status == Artifact.Status.STAGED
    assert art.external_ref["number"] == 7
    assert fake.statuses and fake.statuses[0]["state"] == "pending"

    again = ba.open_build_pr_core(_inp(world), report)
    assert again.get("idempotent") is True
    assert Artifact.objects.filter(run_id=world.run.id, type="code").count() == 1


def test_merge_publishes_pointer_and_completes_run(world, monkeypatch):
    fake = _FakeCodeHost()
    _use_fake_codehost(monkeypatch, fake)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    out = ba.merge_build_pr_core(_inp(world))
    assert out["merged"] is True and fake.merged is True
    assert Artifact.objects.get(run_id=world.run.id, type="code").status == \
        Artifact.Status.PUBLISHED
    world.run.refresh_from_db()
    assert world.run.status == Run.Status.COMPLETED
    # Idempotent: a second merge on an already-merged PR is a no-op.
    assert ba.merge_build_pr_core(_inp(world))["merged"] is True


def test_open_merge_gate_creates_reviewer_approval(world):
    approval_id = ba.open_merge_gate_core(_inp(world))
    ap = Approval.objects.get(id=approval_id)
    assert ap.required_role == "reviewer" and ap.gate_type == "merge_gate"
    assert ap.decision == Approval.Decision.PENDING
    world.run.refresh_from_db()
    assert world.run.status == Run.Status.AWAITING_GATE


def test_takeover_flags_workitem_and_fails_run(world):
    ba.mark_takeover_core(_inp(world))
    world.wi.refresh_from_db()
    world.run.refresh_from_db()
    assert world.wi.takeover_flag is True and world.run.status == Run.Status.FAILED


def test_build_failed_returns_workitem_to_in_progress(world):
    world.wi.state = WorkItem.State.IN_REVIEW
    world.wi.save(update_fields=["state"])
    ba.mark_build_failed_core(_inp(world), "compiler error")
    world.wi.refresh_from_db()
    world.run.refresh_from_db()
    assert world.run.status == Run.Status.FAILED
    assert world.wi.state == WorkItem.State.IN_PROGRESS


# ── code review + remediation loop (07<->08) ────────────────────────
class _ScriptedReviewer:
    """Returns successive finding lists per review call (last one repeats)."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self._i = 0

    def review(self, inp, pr_ref):
        out = self._scripts[min(self._i, len(self._scripts) - 1)]
        self._i += 1
        return out


def _open_pr(world, monkeypatch):
    _use_fake_codehost(monkeypatch, _FakeCodeHost())
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))


def test_review_opens_remediation_child_then_resolves_it(world, monkeypatch):
    _open_pr(world, monkeypatch)
    reviewer = _ScriptedReviewer([
        [ba.Finding(rem="REM-C1", severity="critical", title="SQLi", file="db.py", line=10)],
        [],   # second review: the finding is gone (fixed by the remediation build)
    ])
    monkeypatch.setattr(ba, "get_review_provider", lambda: reviewer)

    first = ba.run_code_review_core(_inp(world))
    assert first["open_blocking"] == 1
    child = WorkItem.objects.get(parent_id=world.wi.id, type=WorkItem.Type.TASK)
    assert child.external_ref["rem"] == "REM-C1" and child.state == WorkItem.State.IN_PROGRESS
    review_art = Artifact.objects.get(run_id=world.run.id, type="code_review")
    assert TraceEdge.objects.filter(from_artifact=review_art, rel="tests").exists()

    second = ba.run_code_review_core(_inp(world))
    assert second["open_blocking"] == 0
    child.refresh_from_db()
    assert child.state == WorkItem.State.DONE        # resolved → closed


def test_review_suggestions_are_non_blocking(world, monkeypatch):
    _open_pr(world, monkeypatch)
    monkeypatch.setattr(ba, "get_review_provider", lambda: _ScriptedReviewer([
        [ba.Finding(rem="REM-S1", severity="suggestion", title="rename var")],
    ]))
    out = ba.run_code_review_core(_inp(world))
    assert out["findings"] == 1 and out["open_blocking"] == 0   # REM-S never blocks
    assert not WorkItem.objects.filter(parent_id=world.wi.id, type=WorkItem.Type.TASK).exists()


def test_dispatch_remediation_briefs_the_open_items(world, monkeypatch):
    _open_pr(world, monkeypatch)
    monkeypatch.setattr(ba, "get_review_provider", lambda: _ScriptedReviewer([
        [ba.Finding(rem="REM-W1", severity="warning", title="naming")],
    ]))
    ba.run_code_review_core(_inp(world))
    out = ba.dispatch_remediation_core(_inp(world))
    assert out["items"] == 1
    world.run.refresh_from_db()
    assert world.run.inputs["remediation"]["items"][0]["rem"] == "REM-W1"
    assert world.run.status == Run.Status.RUNNING
