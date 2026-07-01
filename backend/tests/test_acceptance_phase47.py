"""P4.7 acceptance slice — the productized control plane, from scratch, **no shell/manage.py
step**: every human/admin action in this test is a real REST call against T1-T11's surface
(signup, invite+accept, membership grants, companion connect, project/work-item create, phase
trigger, clarification answer, gate decide, artifact preview). The only direct calls are the
orchestrator's own internal activities (`dispatch_phase_core`, `register_phase_result_core`,
`verify_write_completeness_core`, `open_gate_core`, `publish_artifacts_core`) — those are
Temporal *activities* a live workflow would invoke, not a human shortcut; no live Temporal/engine
broker runs in tests (same pattern as `test_acceptance_phase45.py`), so they're driven directly
and their signal senders are no-op'd.

Sequencing note: BUILD_PLAN.md's prose lists "grant gate roles" before "create project", but a
project-scoped Membership requires the project to exist first — this test creates the project
before granting the role on it (the only order that's actually possible).
"""
from __future__ import annotations

import re
from decimal import Decimal

from rest_framework.test import APIClient

import storage
from apps.gates import services as gate_services
from apps.gates.models import Approval
from apps.registry.catalog import gate_role_for
from apps.registry.models import Artifact
from apps.runs.models import Run, RunnerEnrollment
from apps.tenancy.models import Invitation
from orchestration import activities, phase_report, trigger
from orchestration.types import PhaseReport
from storage import InMemoryObjectStore


def _login(client, email, password):
    resp = client.post("/api/auth/login/", {"email": email, "password": password},
                       format="json")
    assert resp.status_code == 200, resp.content
    return resp.data


def _extract_invite_token(mailoutbox) -> str:
    body = mailoutbox[-1].body
    m = re.search(r"token=([\w-]+)", body)
    assert m, f"no invite token found in email body: {body!r}"
    return m.group(1)


def test_p47_acceptance_slice(db, monkeypatch, mailoutbox):
    store = InMemoryObjectStore()
    monkeypatch.setattr(activities, "get_object_store", lambda: store)
    # `integrations.preview` resolves `storage.s3_from_settings` lazily (per-call), so
    # patching the factory itself (not just the orchestrator's own binding) covers T10's
    # read-through preview reading from the same in-memory store the phase wrote its body to.
    monkeypatch.setattr(storage, "s3_from_settings", lambda: store)
    monkeypatch.setattr(phase_report, "_default_signal_sender", lambda wf, rep: None)
    monkeypatch.setattr(gate_services, "_default_signal_sender", lambda *a, **k: None)
    captured = {}
    monkeypatch.setattr(trigger, "_default_workflow_starter",
                        lambda wf, inp: captured.update(inp=inp))

    admin_client = APIClient()

    # 1. Self-serve signup → new tenant + first admin, session established (DECISIONS 1 & 2).
    signup = admin_client.post(
        "/api/auth/signup/",
        {"name": "Ada Admin", "email": "ada@acme.test", "password": "admin-pass!",
         "org_name": "Acme"},
        format="json",
    )
    assert signup.status_code == 201, signup.content
    tenant_id = signup.data["tenant"]["id"]
    assert signup.data["user"]["is_tenant_admin"] is True

    # 2. Admin invites a developer (J2) — the raw token is never in the REST payload; it's
    # only ever delivered by email, so we read it the way the invitee would.
    invite = admin_client.post(
        "/api/invitations/", {"email": "dev@acme.test", "name": "Dev Dan"}, format="json",
    )
    assert invite.status_code == 201, invite.content
    assert "token" not in invite.data
    raw_token = _extract_invite_token(mailoutbox)
    assert Invitation.objects.get(id=invite.data["id"]).status == "pending"

    # 3. The developer accepts + sets their own password (J3) — a fresh session, no admin
    # involvement beyond the invite.
    dev_client = APIClient()
    accept = dev_client.post(
        "/api/auth/accept-invitation/", {"token": raw_token, "password": "dev-pass!"},
        format="json",
    )
    assert accept.status_code == 200, accept.content
    dev_id = accept.data["user"]["id"]
    assert accept.data["user"]["is_tenant_admin"] is False

    # 4. Admin creates the greenfield project.
    project = admin_client.post(
        "/api/projects/", {"name": "Payments Platform"}, format="json",
        HTTP_X_TENANT_ID=tenant_id,
    )
    assert project.status_code == 201, project.content
    project_id = project.data["id"]
    assert project.data["track"] == "greenfield"

    # 5. Admin grants the developer the PRD gate's role (J6/S-08) — the two-tier admin model
    # means the *admin* could also decide this gate, but granting the real role proves S-08's
    # matrix toggle end-to-end.
    gate_role = gate_role_for("03_prd")  # "product_owner"
    grant = admin_client.post(
        f"/api/projects/{project_id}/memberships/", {"user_id": dev_id, "role": gate_role},
        format="json", HTTP_X_TENANT_ID=tenant_id,
    )
    assert grant.status_code == 201, grant.content
    # (AgentSpec catalog, incl. "03_prd", is already seeded by `create_tenant` on signup.)

    # 6. The developer connects their machine (S-06) — enrolling binds to the *session* user
    # (T11), not a hand-entered developer_id.
    enroll = dev_client.post(
        "/api/runners/", {"project_id": project_id, "label": "Dev's MacBook"},
        format="json", HTTP_X_TENANT_ID=tenant_id,
    )
    assert enroll.status_code == 201, enroll.content
    runner_token = enroll.data["token"]
    enrollment = RunnerEnrollment.objects.get(id=enroll.data["id"])
    assert str(enrollment.developer_id) == dev_id
    runner_hdr = {"HTTP_AUTHORIZATION": f"Runner {runner_token}", "HTTP_X_TENANT_ID": tenant_id}

    status_before = dev_client.get("/api/runners/", HTTP_X_TENANT_ID=tenant_id)
    assert status_before.data[0]["machine"] == "Dev's MacBook"
    assert status_before.data[0]["online"] is False  # never called in yet

    # 7. The developer creates a work item and triggers the PRD phase — it routes to *their*
    # companion because they're the authenticated session user (T5 + T11's enrollment).
    wi = dev_client.post(
        "/api/work-items/", {"project": project_id, "type": "story", "feature_stream": "auth",
                             "title": "Design the auth + billing MVP"},
        format="json", HTTP_X_TENANT_ID=tenant_id,
    )
    assert wi.status_code == 201, wi.content
    work_item_id = wi.data["id"]

    trig = dev_client.post(
        f"/api/work-items/{work_item_id}/trigger/", {"agent_key": "03_prd"},
        format="json", HTTP_X_TENANT_ID=tenant_id,
    )
    assert trig.status_code == 202, trig.content
    inp = captured["inp"]
    assert inp.execution_mode == "companion" and inp.enrollment_id == str(enrollment.id)
    run_id = trig.data["run_id"]
    assert str(Run.objects.get(id=run_id).triggered_by_id) == dev_id

    # 8. The platform dispatches the phase task; the companion claims it via /runner/work/ —
    # which also bumps last_seen, so the connect-machine status now flips online (S-06).
    activities.dispatch_phase_core(inp, manifest="# Project\nPayments Platform\n")
    work = dev_client.get("/api/runner/work/", **runner_hdr)
    assert work.status_code == 200
    assert work.json()["kind"] == "plan" and work.json()["run_id"] == run_id

    status_after = dev_client.get("/api/runners/", HTTP_X_TENANT_ID=tenant_id)
    assert status_after.data[0]["online"] is True

    # 9. The agent hits a context gap → ask_human opens a Clarification (zero cost while idle).
    asked = dev_client.post(
        "/api/runner/clarifications/",
        {"run_id": run_id, "phase": "prd",
         "questions": [{"id": "scope", "text": "MVP scope?", "required": True}]},
        format="json", **runner_hdr,
    )
    assert asked.status_code == 201, asked.content
    clar_id = asked.json()["id"]
    assert Run.objects.get(id=run_id).cost_usd is None

    # 10. It's visible in the web app's pending list; the developer answers it there — the
    # session resolves the answering user, no hand-entered user_id (T5).
    pending = dev_client.get(
        f"/api/clarifications/?status=pending&work_item={work_item_id}",
        HTTP_X_TENANT_ID=tenant_id,
    )
    assert [c["id"] for c in pending.data] == [clar_id]
    answered = dev_client.post(
        f"/api/clarifications/{clar_id}/answer/", {"answers": {"scope": "auth + billing"}},
        format="json", HTTP_X_TENANT_ID=tenant_id,
    )
    assert answered.status_code == 200, answered.content

    # 11. The companion's poll sees the answer and the run continues in-session.
    polled = dev_client.get(f"/api/runner/clarifications/{clar_id}/", **runner_hdr)
    assert polled.json()["status"] == "answered"

    # 12. The companion reports the produced PRD; the platform registers the draft artifact.
    reported = dev_client.post(
        f"/api/runner/phases/{run_id}/report/",
        {"status": "ok", "body": "# PRD\nAuth + billing MVP.", "cost_usd": 0.05},
        format="json", **runner_hdr,
    )
    assert reported.status_code == 200, reported.content
    activities.register_phase_result_core(
        inp, PhaseReport(status="ok", body="# PRD\nAuth + billing MVP.", cost_usd=0.05))
    artifact = Artifact.objects.get(run_id=run_id, type="prd")
    assert store.get(artifact.s3_key) == b"# PRD\nAuth + billing MVP."
    assert Run.objects.get(id=run_id).cost_usd == Decimal("0.0500")

    # 13. Write-completeness → the gate opens → the developer (product_owner) decides it via
    # the real REST endpoint (T9's DriftRecordViewSet sibling, ApprovalViewSet.decide).
    activities.verify_write_completeness_core(inp, ["prd"])
    approval_id = activities.open_gate_core(inp)
    decide = dev_client.post(
        f"/api/approvals/{approval_id}/decide/", {"decision": "approved"},
        format="json", HTTP_X_TENANT_ID=tenant_id,
    )
    assert decide.status_code == 200, decide.content
    assert Approval.objects.get(id=approval_id).decision == Approval.Decision.APPROVED

    # 14. Publish (internal — no docstore connector configured, so it stays sor=internal) →
    # the developer previews the published artifact read-through (T10).
    activities.publish_artifacts_core(inp)
    artifact.refresh_from_db()
    assert artifact.status == Artifact.Status.PUBLISHED

    preview = dev_client.get(f"/api/artifacts/{artifact.id}/preview/", HTTP_X_TENANT_ID=tenant_id)
    assert preview.status_code == 200, preview.content
    assert preview.data["body"] == "# PRD\nAuth + billing MVP."
    assert preview.data["status"] == "published"
