"""Phase 4.5 acceptance slice — Local-Engine Execution + Interactive Clarifications.

Proves the whole req #1/#2 loop end-to-end, from scratch (no seed tenant), deterministic and
offline (no Temporal/engine): trigger a planning phase in **companion** mode → the companion
claims it → the agent asks a question (`ask_human`) which surfaces as a pending Clarification
at **zero cost** → a human answers it via REST → the companion's poll resumes → it reports →
the platform registers the draft artifact → write-completeness → gate → approve → publish. Plus
the offline-companion → takeover path.

The Temporal workflow wiring itself is covered (against a live server) in test_phase_dispatch;
here we drive the real services/endpoints directly so the acceptance proof needs no broker.
"""
from decimal import Decimal

from rest_framework.test import APIClient

from apps.gates.models import Approval
from apps.gates.services import decide_gate
from apps.projects.models import Project, ProjectProfile
from apps.registry.catalog import gate_role_for
from apps.registry.models import AgentSpec, Artifact
from apps.runs.enrollment import enroll_runner
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from orchestration import activities, phase_report
from orchestration.trigger import trigger_phase
from orchestration.types import PhaseReport
from storage import InMemoryObjectStore


def _bootstrap(monkeypatch):
    """Everything a developer creates from scratch — no seed tenant."""
    store = InMemoryObjectStore()
    monkeypatch.setattr(activities, "get_object_store", lambda: store)
    monkeypatch.setattr(phase_report, "_default_signal_sender", lambda wf, rep: None)

    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Greenfield App")
    ProjectProfile.objects.create(tenant=t, project=project, important_context="Ship the MVP.")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY,
                                 feature_stream="auth")
    AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="agents/03_prd/agent.md",
                             phase_label="prd")
    user = User.objects.create_user(email="dev@acme.test", name="Dev", tenant=t, password="pw")
    Membership.objects.create(tenant=t, user=user, project=project, role=gate_role_for("03_prd"))
    enrollment, token = enroll_runner(tenant_id=str(t.id), project_id=str(project.id),
                                      developer_id=str(user.id), label="dev-laptop")
    return {
        "store": store, "t": t, "project": project, "wi": wi, "user": user,
        "enrollment": enrollment, "token": token,
    }


def test_companion_phase_with_clarification_end_to_end(db, monkeypatch):
    w = _bootstrap(monkeypatch)
    tid = str(w["t"].id)
    client = APIClient()
    hdr = {"HTTP_X_TENANT_ID": tid}
    runner_hdr = {"HTTP_AUTHORIZATION": f"Runner {w['token']}", **hdr}

    # 1. Trigger the PRD phase as the developer → routes to their companion (req #1).
    captured = {}
    trigger_phase(tenant_id=tid, project_id=str(w["project"].id), work_item_id=str(w["wi"].id),
                  agent_key="03_prd", triggered_by=str(w["user"].id),
                  workflow_starter=lambda wf, inp: captured.update(inp=inp))
    inp = captured["inp"]
    assert inp.execution_mode == "companion" and inp.enrollment_id == str(w["enrollment"].id)

    # 2. The platform composes + dispatches the phase task; the companion claims it via /work/.
    activities.dispatch_phase_core(inp, manifest="# Project\nGreenfield App\n")
    work = client.get("/api/runner/work/", **runner_hdr)
    assert work.status_code == 200
    assert work.json()["kind"] == "plan" and work.json()["run_id"] == inp.run_id

    # 3. The agent hits a context gap → ask_human opens a Clarification (the model is now idle).
    asked = client.post("/api/runner/clarifications/",
                        {"run_id": inp.run_id, "phase": "prd",
                         "questions": [{"id": "scope", "text": "MVP scope?", "required": True}]},
                        format="json", **runner_hdr)
    assert asked.status_code == 201
    clar_id = asked.json()["id"]
    # Zero cost while waiting — no engine tokens have been billed to the run yet.
    assert Run.objects.get(id=inp.run_id).cost_usd is None

    # 4. It shows up in the web app's pending list; the developer answers it there.
    pending = client.get(f"/api/clarifications/?status=pending&work_item={w['wi'].id}", **hdr)
    assert [c["id"] for c in pending.json()] == [clar_id]
    answered = client.post(f"/api/clarifications/{clar_id}/answer/",
                           {"user_id": str(w["user"].id), "answers": {"scope": "auth + billing"}},
                           format="json", **hdr)
    assert answered.status_code == 200

    # 5. The companion's ask_human poll sees the answer and the run continues in-session.
    polled = client.get(f"/api/runner/clarifications/{clar_id}/", **runner_hdr)
    assert polled.json()["status"] == "answered"
    assert polled.json()["answers"] == {"scope": "auth + billing"}

    # 6. The companion reports the produced PRD; the platform registers the draft (cost set now).
    reported = client.post(f"/api/runner/phases/{inp.run_id}/report/",
                           {"status": "ok", "body": "# PRD\nAuth + billing.", "cost_usd": 0.07},
                           format="json", **runner_hdr)
    assert reported.status_code == 200
    activities.register_phase_result_core(
        inp, PhaseReport(status="ok", body="# PRD\nAuth + billing.", cost_usd=0.07))
    art = Artifact.objects.get(run_id=inp.run_id, type="prd")
    assert w["store"].get(art.s3_key) == b"# PRD\nAuth + billing."
    assert Run.objects.get(id=inp.run_id).cost_usd == Decimal("0.0700")  # only the engine's cost

    # 7. Write-completeness → open the gate → the PO approves → publish.
    activities.verify_write_completeness_core(inp, ["prd"])
    approval_id = activities.open_gate_core(inp)
    decide_gate(tenant_id=tid, approval_id=approval_id, user_id=str(w["user"].id),
                decision="approved", signal_sender=lambda *a, **k: None)
    assert Approval.objects.get(id=approval_id).decision == Approval.Decision.APPROVED
    activities.publish_artifacts_core(inp)
    assert Artifact.objects.get(id=art.id).status == Artifact.Status.PUBLISHED


def test_rest_trigger_routes_to_the_users_companion(db, monkeypatch):
    """The web/REST trigger carries the user → the run routes to their enrolled companion
    (execution_mode=companion), so phases run on their local Claude Code (req #1)."""
    w = _bootstrap(monkeypatch)
    captured = {}
    monkeypatch.setattr("orchestration.trigger._default_workflow_starter",
                        lambda wf, inp: captured.update(inp=inp))
    r = APIClient().post(
        f"/api/work-items/{w['wi'].id}/trigger/",
        {"agent_key": "03_prd", "user_id": str(w["user"].id)},
        format="json", HTTP_X_TENANT_ID=str(w["t"].id))
    assert r.status_code == 202
    assert captured["inp"].execution_mode == "companion"
    assert captured["inp"].enrollment_id == str(w["enrollment"].id)
    assert str(Run.objects.get(id=r.json()["run_id"]).triggered_by_id) == str(w["user"].id)


def test_offline_companion_parks_for_takeover(db, monkeypatch):
    w = _bootstrap(monkeypatch)
    captured = {}
    trigger_phase(tenant_id=str(w["t"].id), project_id=str(w["project"].id),
                  work_item_id=str(w["wi"].id), agent_key="03_prd",
                  triggered_by=str(w["user"].id),
                  workflow_starter=lambda wf, inp: captured.update(inp=inp))
    inp = captured["inp"]
    activities.dispatch_phase_core(inp, manifest="# Project\n")
    # The companion never reports (laptop offline) → the workflow's report timeout fires the
    # takeover activity. Asserting the core here; the live-Temporal timeout path is in
    # test_phase_dispatch.
    activities.mark_phase_takeover_core(inp)
    assert Run.objects.get(id=inp.run_id).status == Run.Status.FAILED
    assert WorkItem.objects.get(id=w["wi"].id).takeover_flag is True
