"""P2 §7 — human takeover + signed Git-webhook reconciliation (companion collaboration path).

Verifies: signature gate (valid/invalid), idempotent dedup of redeliveries, register-don't-
recreate reconciliation (push moves the `code` pointer's sha; a human-merged PR transitions the
WorkItem and publishes the pointer; CI status round-trips to the ledger), human takeover
flag/Event, RLS isolation across tenants, and the signed HTTP endpoint end-to-end.
"""
import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest
from mcp_platform_state import tools
from rest_framework.test import APIClient

from apps.integrations.models import WebhookDelivery
from apps.ledger.models import Event
from apps.projects.models import Project, ProjectProfile
from apps.registry.models import Artifact
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from integrations.webhooks import reconcile_github, verify_github_signature
from orchestration.takeover import TakeoverError, release_takeover, request_takeover

_SECRET = "whsec_test"


def _sign(body: bytes, secret: str = _SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    ProjectProfile.objects.create(tenant=t, project=p, important_context="Ship it.")
    from apps.registry.models import AgentSpec

    spec = AgentSpec.objects.create(tenant=t, key="07_implementation", body_ref="",
                                    recommended_model="claude-x", phase_label="implementation")
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY, title="Login",
                                 state=WorkItem.State.IN_REVIEW, feature_stream="ST-1")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec, engine="claude",
                             status=Run.Status.AWAITING_GATE)
    art = tools.register_artifact(
        str(t.id), str(p.id), str(run.id), "implementation", "code", "git",
        content_hash="oldsha",
        external_ref={"sor": "git", "repo": "acme/api", "number": 7,
                      "head": "feature/ST-1", "url": "u", "sha": "oldsha"},
    )
    return SimpleNamespace(t=t, p=p, wi=wi, run=run, art_id=art["id"])


# ── signature gate ──────────────────────────────────────────────────
def test_verify_signature_valid_and_invalid():
    body = b'{"zen": "ok"}'
    assert verify_github_signature(_SECRET, body, _sign(body))
    assert not verify_github_signature(_SECRET, body, _sign(body, "wrong"))
    assert not verify_github_signature(_SECRET, body, None)
    assert not verify_github_signature("", body, _sign(body))          # no secret → never trust


# ── reconciliation: push moves the sha pointer (register-don't-recreate) ──
def test_push_updates_code_pointer_without_duplicating(world):
    payload = {"ref": "refs/heads/feature/ST-1", "after": "newsha123",
               "commits": [{"id": "newsha123"}], "repository": {"full_name": "acme/api"}}
    out = reconcile_github(tenant_id=str(world.t.id), event="push", delivery_id="d1",
                           payload=payload)
    assert out["status"] == "processed" and out["reconciled"] == 1
    art = Artifact.objects.get(id=world.art_id)
    assert art.external_ref["sha"] == "newsha123"                    # pointer moved
    assert Artifact.objects.filter(run_id=world.run.id, type="code").count() == 1  # not recreated
    assert Event.objects.filter(tenant=world.t, action="webhook.push_reconciled").exists()


def test_redelivery_is_idempotent(world):
    payload = {"ref": "refs/heads/feature/ST-1", "after": "s",
               "repository": {"full_name": "acme/api"}}
    first = reconcile_github(tenant_id=str(world.t.id), event="push", delivery_id="dup",
                             payload=payload)
    second = reconcile_github(tenant_id=str(world.t.id), event="push", delivery_id="dup",
                              payload=payload)
    assert first["status"] == "processed" and second["status"] == "duplicate"
    assert WebhookDelivery.objects.filter(tenant=world.t, delivery_id="dup").count() == 1


# ── reconciliation: a human-merged PR transitions the WorkItem ──────
def test_pull_request_merged_transitions_workitem_and_publishes(world):
    payload = {"action": "closed",
               "pull_request": {"number": 7, "merged": True, "merged_at": "2026-06-24T00:00:00Z"},
               "repository": {"full_name": "acme/api"}}
    out = reconcile_github(tenant_id=str(world.t.id), event="pull_request", delivery_id="pr1",
                           payload=payload)
    assert out["status"] == "processed" and out["merged"] is True
    world.wi.refresh_from_db()
    assert world.wi.state == WorkItem.State.DONE
    assert Artifact.objects.get(id=world.art_id).status == Artifact.Status.PUBLISHED
    assert Event.objects.filter(tenant=world.t, action="webhook.pr_merged").exists()


def test_pull_request_merged_logs_transition_event(world):
    """The webhook transition must emit the canonical workitem.transitioned event, so a
    state=done is never orphaned in the audit trail (the missing-event mislabel bug)."""
    payload = {"action": "closed",
               "pull_request": {"number": 7, "merged": True, "merged_at": "2026-06-24T00:00:00Z"},
               "repository": {"full_name": "acme/api"}}
    reconcile_github(tenant_id=str(world.t.id), event="pull_request", delivery_id="prX",
                     payload=payload)
    world.wi.refresh_from_db()
    assert world.wi.state == WorkItem.State.DONE
    ev = Event.objects.filter(tenant=world.t, action="workitem.transitioned").last()
    assert ev is not None and ev.payload["to_state"] == WorkItem.State.DONE
    assert ev.payload["via"] == "webhook_pr_merge"


def test_pull_request_merge_does_not_bypass_pending_merge_gate(world):
    """A merged-PR webhook must NOT mark the WorkItem done while its merge gate is still PENDING —
    the saga owns that transition through the control-plane gate (non-negotiable #2/#5). This is
    the root cause of the state=done-while-awaiting_gate mislabel."""
    from apps.gates.models import Approval

    Approval.objects.create(tenant=world.t, run=world.run, gate_type="merge_gate",
                            decision=Approval.Decision.PENDING)
    payload = {"action": "closed",
               "pull_request": {"number": 7, "merged": True, "merged_at": "2026-06-24T00:00:00Z"},
               "repository": {"full_name": "acme/api"}}
    out = reconcile_github(tenant_id=str(world.t.id), event="pull_request", delivery_id="prG",
                           payload=payload)
    world.wi.refresh_from_db()
    assert world.wi.state == WorkItem.State.IN_REVIEW              # gate not bypassed
    assert out["work_items"] == []                                # nothing transitioned
    # The merge is still observed/recorded, and the artifact still publishes.
    assert Event.objects.filter(tenant=world.t, action="webhook.pr_merged").exists()
    assert Artifact.objects.get(id=world.art_id).status == Artifact.Status.PUBLISHED
    assert not Event.objects.filter(tenant=world.t, action="workitem.transitioned").exists()


def test_pull_request_closed_unmerged_leaves_workitem(world):
    payload = {"action": "closed", "pull_request": {"number": 7, "merged": False},
               "repository": {"full_name": "acme/api"}}
    reconcile_github(tenant_id=str(world.t.id), event="pull_request", delivery_id="pr2",
                     payload=payload)
    world.wi.refresh_from_db()
    assert world.wi.state == WorkItem.State.IN_REVIEW                # not transitioned
    assert Event.objects.filter(tenant=world.t, action="webhook.pr_closed").exists()


def test_status_event_round_trips_to_ledger(world):
    payload = {"sha": "abc", "state": "success", "context": "ci/build",
               "repository": {"full_name": "acme/api"}}
    out = reconcile_github(tenant_id=str(world.t.id), event="status", delivery_id="st1",
                           payload=payload)
    assert out["state"] == "success"
    ev = Event.objects.get(tenant=world.t, action="webhook.ci_status")
    assert ev.payload["sha"] == "abc" and ev.payload["state"] == "success"


def test_unknown_event_is_ignored(world):
    out = reconcile_github(tenant_id=str(world.t.id), event="ping", delivery_id="pg1", payload={})
    assert out["status"] == "ignored"
    d = WebhookDelivery.objects.get(tenant=world.t, delivery_id="pg1")
    assert d.status == WebhookDelivery.Status.IGNORED


# ── RLS: another tenant's webhook cannot touch these artifacts ──────
def test_reconcile_is_tenant_isolated(world):
    other = Tenant.objects.create(name="Other")
    payload = {"ref": "refs/heads/feature/ST-1", "after": "evil",
               "repository": {"full_name": "acme/api"}}
    out = reconcile_github(tenant_id=str(other.id), event="push", delivery_id="x1",
                           payload=payload)
    assert out["reconciled"] == 0                                   # sees none of Acme's artifacts
    assert Artifact.objects.get(id=world.art_id).external_ref["sha"] == "oldsha"  # untouched


# ── human takeover ──────────────────────────────────────────────────
def test_request_and_release_takeover(world):
    out = request_takeover(tenant_id=str(world.t.id), work_item_id=str(world.wi.id),
                           reason="hand-finishing locally")
    assert out["takeover"] is True
    world.wi.refresh_from_db()
    assert world.wi.takeover_flag is True
    assert Event.objects.filter(tenant=world.t, action="workitem.takeover").exists()

    release_takeover(tenant_id=str(world.t.id), work_item_id=str(world.wi.id))
    world.wi.refresh_from_db()
    assert world.wi.takeover_flag is False
    assert Event.objects.filter(tenant=world.t, action="workitem.takeover_released").exists()


def test_takeover_unknown_work_item_raises(world):
    import uuid

    with pytest.raises(TakeoverError):
        request_takeover(tenant_id=str(world.t.id), work_item_id=str(uuid.uuid4()))


# ── signed HTTP endpoint end-to-end ─────────────────────────────────
def test_webhook_endpoint_verifies_signature_and_reconciles(world, settings):
    settings.GITHUB_WEBHOOK_SECRET = _SECRET
    client = APIClient()
    url = f"/api/webhooks/github/{world.t.id}/"
    payload = {"ref": "refs/heads/feature/ST-1", "after": "http_sha",
               "repository": {"full_name": "acme/api"}}
    body = json.dumps(payload).encode()

    # Wrong signature → 401, nothing reconciled.
    bad = client.post(url, data=body, content_type="application/json",
                      HTTP_X_HUB_SIGNATURE_256=_sign(body, "nope"),
                      HTTP_X_GITHUB_EVENT="push", HTTP_X_GITHUB_DELIVERY="h1")
    assert bad.status_code == 401
    assert Artifact.objects.get(id=world.art_id).external_ref["sha"] == "oldsha"

    # Valid signature → 200, pointer moved.
    ok = client.post(url, data=body, content_type="application/json",
                     HTTP_X_HUB_SIGNATURE_256=_sign(body),
                     HTTP_X_GITHUB_EVENT="push", HTTP_X_GITHUB_DELIVERY="h2")
    assert ok.status_code == 200 and ok.json()["status"] == "processed"
    assert Artifact.objects.get(id=world.art_id).external_ref["sha"] == "http_sha"


def test_take_over_endpoint(world):
    client = APIClient()
    resp = client.post(f"/api/work-items/{world.wi.id}/take-over/", {"reason": "manual"},
                       format="json", HTTP_X_TENANT_ID=str(world.t.id))
    assert resp.status_code == 200 and resp.json()["takeover"] is True
    world.wi.refresh_from_db()
    assert world.wi.takeover_flag is True
