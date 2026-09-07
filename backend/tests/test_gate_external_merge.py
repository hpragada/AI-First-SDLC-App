"""Bugs S.No 88 — the sweep that finds merge gates whose PR was merged elsewhere.

The webhook is the fast path and is not a guarantee: a delivery can be missed, and a webhook
that FAILS is never redelivered (the dedup row is written before the handler runs). Nor does
any webhook fire retroactively for a merge that happened before this existed — so the sweep is
the only thing that will ever recover a run stranded today.

Throughout: it ANNOTATES, it never decides.
"""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone
from mcp_platform_state import tools

from apps.gates.models import Approval
from apps.gates.reconcile import sweep
from apps.ledger.models import Event
from apps.projects.models import Project
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    spec = AgentSpec.objects.create(tenant=t, key="07_implementation", body_ref="",
                                    recommended_model="claude-x", phase_label="implementation")
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY, title="Login",
                                 state=WorkItem.State.IN_REVIEW)
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec, engine="claude",
                             status=Run.Status.AWAITING_GATE)
    tools.register_artifact(
        str(t.id), str(p.id), str(run.id), "implementation", "code", "git",
        content_hash="sha", external_ref={"sor": "git", "repo": "acme/api", "number": 7},
    )
    approval = Approval.objects.create(
        tenant=t, run=run, work_item=wi, gate_type="merge_gate",
        required_role="tech_lead", decision=Approval.Decision.PENDING)
    # Age it past the cutoff — a reviewer still thinking about a gate is not stranded.
    Approval.objects.filter(id=approval.id).update(
        updated_at=timezone.now() - timedelta(hours=4))
    return SimpleNamespace(t=t, p=p, wi=wi, run=run, approval=approval)


class _CodeHost:
    def __init__(self, merged=True, raises=False):
        self._merged, self._raises = merged, raises
        self.asked: list[str] = []

    def get_pull_request(self, *, pr_ref):
        self.asked.append(pr_ref)
        if self._raises:
            raise RuntimeError("github is unreachable")
        return SimpleNamespace(merged=self._merged, merged_by="alex-w",
                               merged_at="2026-09-07T09:41:00Z")


def _with_codehost(monkeypatch, host):
    import apps.gates.reconcile as mod

    monkeypatch.setattr("integrations.registry.get_capability",
                        lambda tenant_id, cap: host)
    return mod


def test_the_sweep_finds_and_notes_a_stranded_gate(world, monkeypatch):
    host = _CodeHost(merged=True)
    _with_codehost(monkeypatch, host)

    out = sweep(str(world.t.id))

    assert out["noted"] == [str(world.approval.id)]
    world.approval.refresh_from_db()
    assert world.approval.external_merge["merged_by"] == "alex-w"
    assert world.approval.external_merge["pr_ref"] == "acme/api#7"
    assert world.approval.external_merge["detected_by"] == "reconciler"
    assert host.asked == ["acme/api#7"]
    assert Event.objects.filter(tenant=world.t,
                                action="webhook.pr_merged_while_gated").exists()


def test_the_sweep_never_decides_the_gate(world, monkeypatch):
    """THE PROPERTY THAT MATTERS. Detection annotates; a person decides. If this ever fails,
    the platform has started approving its own gates."""
    _with_codehost(monkeypatch, _CodeHost(merged=True))

    sweep(str(world.t.id))

    world.approval.refresh_from_db()
    world.wi.refresh_from_db()
    world.run.refresh_from_db()
    assert world.approval.decision == Approval.Decision.PENDING
    assert world.approval.approver_id is None
    assert world.approval.decided_at is None
    assert world.wi.state == WorkItem.State.IN_REVIEW
    assert world.run.status == Run.Status.AWAITING_GATE
    assert not Event.objects.filter(tenant=world.t, action="gate.decided").exists()


def test_an_unmerged_pull_request_is_left_alone(world, monkeypatch):
    _with_codehost(monkeypatch, _CodeHost(merged=False))
    out = sweep(str(world.t.id))
    world.approval.refresh_from_db()
    assert out["noted"] == [] and world.approval.external_merge is None


def test_a_code_host_that_will_not_answer_is_swallowed(world, monkeypatch):
    """A safety net that raises is not a safety net — this rides on a page load."""
    _with_codehost(monkeypatch, _CodeHost(raises=True))
    out = sweep(str(world.t.id))
    world.approval.refresh_from_db()
    assert out["noted"] == [] and "error" not in out
    assert world.approval.external_merge is None      # "could not tell" is never "merged"


def test_a_fresh_gate_is_not_probed(world, monkeypatch):
    """Age-gated: every candidate costs a network call, and a reviewer who is simply still
    thinking about a gate must never be mistaken for a stranded one."""
    host = _CodeHost(merged=True)
    _with_codehost(monkeypatch, host)
    Approval.objects.filter(id=world.approval.id).update(updated_at=timezone.now())

    out = sweep(str(world.t.id))

    assert host.asked == [] and out["noted"] == []


def test_an_already_noted_gate_is_not_probed_again(world, monkeypatch):
    host = _CodeHost(merged=True)
    _with_codehost(monkeypatch, host)
    Approval.objects.filter(id=world.approval.id).update(
        external_merge={"merged_by": "someone", "pr_ref": "acme/api#7",
                        "merged_at": "", "detected_by": "webhook"})

    sweep(str(world.t.id))

    assert host.asked == []


def test_a_decided_gate_is_not_probed(world, monkeypatch):
    host = _CodeHost(merged=True)
    _with_codehost(monkeypatch, host)
    Approval.objects.filter(id=world.approval.id).update(
        decision=Approval.Decision.APPROVED)

    sweep(str(world.t.id))

    assert host.asked == []


def test_a_run_with_no_pull_request_yet_is_skipped(world, monkeypatch):
    """No PR pointer means there is nothing to ask about — never guess."""
    host = _CodeHost(merged=True)
    _with_codehost(monkeypatch, host)
    Artifact.objects.filter(run_id=world.run.id).update(
        external_ref={"sor": "git", "branch": "feat/login"})   # pre-PR pointer

    out = sweep(str(world.t.id))

    assert host.asked == [] and out["noted"] == []
