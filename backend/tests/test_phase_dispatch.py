"""Companion execution of planning phases (req #1): the dispatch→report seam generalized
to planning. Covers the new activity cores, the report service, the runner work-claim /
phase fetch / phase report endpoints, and the AgentRunWorkflow companion branch (against a
real Temporal server, skipped when unreachable — mirrors test_orchestration_workflow).
"""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project, ProjectProfile
from apps.registry.models import AgentSpec, Artifact
from apps.runs.enrollment import enroll_runner
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from orchestration import activities
from orchestration.types import AgentRunInput, PhaseReport
from storage import InMemoryObjectStore


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    ProjectProfile.objects.create(tenant=t, project=project, important_context="ctx")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="x", phase_label="prd")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec,
                             temporal_workflow_id="wf-x")
    enrollment, token = enroll_runner(tenant_id=str(t.id), project_id=str(project.id), label="l")
    inp = AgentRunInput(
        run_id=str(run.id), tenant_id=str(t.id), project_id=str(project.id),
        work_item_id=str(wi.id), agent_spec_id=str(spec.id), phase="prd",
        required_role="product_owner", execution_mode="companion",
        enrollment_id=str(enrollment.id),
    )
    return {"inp": inp, "tenant_id": str(t.id), "project_id": str(project.id),
            "run_id": str(run.id), "enrollment_id": str(enrollment.id), "token": token}


# ── activity cores ──────────────────────────────────────────────────
def test_dispatch_phase_core_stashes_task_and_dispatch(world):
    out = activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    assert out["dispatched"] is True
    run = Run.objects.get(id=world["run_id"])
    assert run.status == Run.Status.RUNNING
    assert run.inputs["phase_task"]["manifest"] == "# Project\nm"
    assert run.inputs["phase_task"]["phase"] == "prd"
    assert run.inputs["dispatch"] == {"kind": "plan", "enrollment_id": world["enrollment_id"],
                                      "status": "pending"}


def test_register_phase_result_core_drafts_and_is_idempotent(monkeypatch, world):
    store = InMemoryObjectStore()
    monkeypatch.setattr(activities, "get_object_store", lambda: store)
    report = PhaseReport(status="ok", body="# PRD\nbody", cost_usd=0.05)

    out = activities.register_phase_result_core(world["inp"], report)
    art_id = out["artifact_ids"][0]
    art = Artifact.objects.get(id=art_id)
    assert art.type == "prd" and art.s3_key and store.get(art.s3_key) == b"# PRD\nbody"
    run = Run.objects.get(id=world["run_id"])
    assert float(run.cost_usd) == 0.05
    assert run.inputs.get("dispatch", {}).get("status") == "reported" or run.inputs == {}

    again = activities.register_phase_result_core(world["inp"], report)
    assert again.get("idempotent") is True and again["artifact_ids"] == [art_id]


def test_register_phase_result_backfills_agent_registered_artifact(monkeypatch, world):
    """Bugs.xlsx row 59: when the agent registered the phase artifact itself mid-run
    (pointer-only — content_hash, no s3_key), the report step must still stage the body
    to S3 and attach it to that row, not skip as 'idempotent' and leave every artifact
    of the run body-less (the preview 404)."""
    from mcp_platform_state import tools

    store = InMemoryObjectStore()
    monkeypatch.setattr(activities, "get_object_store", lambda: store)
    pre = tools.register_artifact(
        world["tenant_id"], world["project_id"], world["run_id"], "prd", "prd",
        "internal", "sha256:agent",
    )
    report = PhaseReport(status="ok", body="# PRD\nstaged body", cost_usd=0.01)

    out = activities.register_phase_result_core(world["inp"], report)
    assert out["artifact_ids"] == [pre["id"]]          # reused the agent's row
    art = Artifact.objects.get(id=pre["id"])
    assert art.s3_key and store.get(art.s3_key) == b"# PRD\nstaged body"

    again = activities.register_phase_result_core(world["inp"], report)
    assert again.get("idempotent") is True and again["artifact_ids"] == [pre["id"]]


def test_mark_phase_takeover_core_parks_run(world):
    activities.mark_phase_takeover_core(world["inp"])
    run = Run.objects.get(id=world["run_id"])
    assert run.status == Run.Status.FAILED
    assert WorkItem.objects.get(id=world["inp"].work_item_id).takeover_flag is True


def test_fail_run_core(world):
    activities.fail_run_core(world["inp"], "boom")
    run = Run.objects.get(id=world["run_id"])
    assert run.status == Run.Status.FAILED and run.outputs["error"] == "boom"


# ── report service ──────────────────────────────────────────────────
def test_report_phase_records_and_signals(world):
    from orchestration.phase_report import report_phase

    calls = []
    report = {"status": "ok", "body": "x", "cost_usd": 0.0}
    result = report_phase(tenant_id=world["tenant_id"], run_id=world["run_id"], report=report,
                          signal_sender=lambda wf, rep: calls.append((wf, rep.status)))
    assert result["signaled"] is True
    assert calls == [("wf-x", "ok")]
    assert Run.objects.get(id=world["run_id"]).outputs["report"]["body"] == "x"


# ── runner endpoints ────────────────────────────────────────────────
def _auth(world):
    return {"HTTP_AUTHORIZATION": f"Runner {world['token']}",
            "HTTP_X_TENANT_ID": world["tenant_id"]}


def test_work_claim_returns_dispatched_plan_then_204(world):
    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    client = APIClient()
    r = client.get("/api/runner/work/", **_auth(world))
    assert r.status_code == 200, r.content
    assert r.json()["kind"] == "plan" and r.json()["run_id"] == world["run_id"]
    assert r.json()["payload"]["phase"] == "prd"
    # Claimed -> the next poll finds nothing.
    assert client.get("/api/runner/work/", **_auth(world)).status_code == 204


def test_work_claim_scoped_to_enrollment(world):
    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    # A different enrollment in the same tenant must not see this run.
    _, other_token = enroll_runner(tenant_id=world["tenant_id"],
                                   project_id=world["project_id"], label="other")
    client = APIClient()
    r = client.get("/api/runner/work/", HTTP_AUTHORIZATION=f"Runner {other_token}",
                   HTTP_X_TENANT_ID=world["tenant_id"])
    assert r.status_code == 204


def test_stale_claim_is_reclaimed_after_lease(world):
    """RC-3: if the companion that claimed a run dies before reporting, the claim goes stale and
    a later poll re-claims it. Without this the run stays 'running' with no artifacts, no gate."""
    from datetime import timedelta

    from django.utils import timezone

    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    client = APIClient()
    assert client.get("/api/runner/work/", **_auth(world)).status_code == 200   # first claim
    assert client.get("/api/runner/work/", **_auth(world)).status_code == 204   # fresh lease held

    # Age the claim past the lease — the companion "died" mid-run without reporting.
    run = Run.objects.get(id=world["run_id"])
    dispatch = dict(run.inputs["dispatch"])
    dispatch["claimed_at"] = (timezone.now() - timedelta(minutes=30)).isoformat()
    run.inputs = {**run.inputs, "dispatch": dispatch}
    run.save(update_fields=["inputs"])

    r = client.get("/api/runner/work/", **_auth(world))
    assert r.status_code == 200 and r.json()["run_id"] == world["run_id"]       # re-dispatched
    assert Run.objects.get(id=world["run_id"]).inputs["dispatch"]["claim_count"] == 2


def test_heartbeat_refreshes_last_seen_and_rejects_bad_token(world):
    """RC-2: the heartbeat resolves the runner (stamping last_seen), keeping the companion
    'online' while a phase runs and the loop isn't polling /work/."""
    from apps.runs.models import RunnerEnrollment

    RunnerEnrollment.objects.filter(id=world["enrollment_id"]).update(last_seen=None)
    client = APIClient()
    ok = client.post("/api/runner/heartbeat/", **_auth(world))
    assert ok.status_code == 200 and ok.json()["ok"] is True
    assert RunnerEnrollment.objects.get(id=world["enrollment_id"]).last_seen is not None

    bad = client.post("/api/runner/heartbeat/", HTTP_AUTHORIZATION="Runner nope",
                      HTTP_X_TENANT_ID=world["tenant_id"])
    assert bad.status_code == 401


# ── RC-3 follow-up: kill the duplicate-v2 re-run (a long phase re-claimed after it reported) ──
def test_report_phase_flips_dispatch_to_reported_synchronously(world):
    """The report must mark the dispatch 'reported' in the SAME request, so the daemon's next
    /work/ poll can never re-claim a just-reported (possibly lease-stale) run and re-run it."""
    from orchestration.phase_report import report_phase

    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    report_phase(tenant_id=world["tenant_id"], run_id=world["run_id"],
                 report={"status": "ok", "body": "# draft"}, signal_sender=lambda *a, **k: None)
    run = Run.objects.get(id=world["run_id"])
    assert run.inputs["dispatch"]["status"] == "reported"


def test_report_phase_tolerates_already_completed_workflow(world):
    """A late/duplicate report to a finished workflow returns benignly — no 500 that would
    crash the companion daemon."""
    from orchestration.phase_report import report_phase

    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")

    def _completed(*a, **k):
        raise RuntimeError("workflow execution already completed")

    out = report_phase(tenant_id=world["tenant_id"], run_id=world["run_id"],
                       report={"status": "ok", "body": "x"}, signal_sender=_completed)
    assert out["signaled"] is False and "already completed" in out["note"]


def test_stale_claim_not_reclaimed_once_run_left_running(world):
    """Even a lease-stale 'claimed' dispatch must NOT be re-claimed once the run advanced past
    running (gated/completed) — exactly the condition that produced the duplicate-v2 artifact."""
    from datetime import timedelta

    from django.utils import timezone

    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    client = APIClient()
    assert client.get("/api/runner/work/", **_auth(world)).status_code == 200   # first claim

    run = Run.objects.get(id=world["run_id"])
    dispatch = dict(run.inputs["dispatch"])
    dispatch["claimed_at"] = (timezone.now() - timedelta(minutes=30)).isoformat()  # past lease
    run.inputs = {**run.inputs, "dispatch": dispatch}
    run.status = Run.Status.AWAITING_GATE                       # phase finished, at its gate
    run.save(update_fields=["inputs", "status"])

    # Must NOT re-run it, despite the stale claim.
    assert client.get("/api/runner/work/", **_auth(world)).status_code == 204


def test_phase_fetch_then_report(monkeypatch, world):
    from orchestration import phase_report

    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    client = APIClient()
    fetched = client.get(f"/api/runner/phases/{world['run_id']}/", **_auth(world))
    assert fetched.status_code == 200 and fetched.json()["phase"] == "prd"

    sent = []
    monkeypatch.setattr(phase_report, "_default_signal_sender",
                        lambda wf, rep: sent.append((wf, rep.status)))
    reported = client.post(f"/api/runner/phases/{world['run_id']}/report/",
                           {"status": "ok", "body": "# PRD\nx", "cost_usd": 0.01},
                           format="json", **_auth(world))
    assert reported.status_code == 200 and reported.json()["signaled"] is True
    assert sent == [("wf-x", "ok")]


def test_work_claim_requires_token(world):
    r = APIClient().get("/api/runner/work/", HTTP_X_TENANT_ID=world["tenant_id"])
    assert r.status_code == 401


# ── workflow companion branch (real Temporal; skipped if unreachable) ─
async def _client():
    from temporalio.client import Client

    try:
        return await Client.connect("localhost:7233", namespace="default")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Temporal not reachable at localhost:7233: {exc}")


def _patch_cores(monkeypatch, calls):
    def rec(name, ret):
        def fn(*args, **kwargs):
            calls.append(name)
            return ret
        return fn

    monkeypatch.setattr(activities, "compose_manifest_core", rec("compose", "# Project\nm"))
    monkeypatch.setattr(activities, "dispatch_phase_core", rec("dispatch", {"dispatched": True}))
    monkeypatch.setattr(activities, "register_phase_result_core",
                        rec("register", {"artifact_ids": ["a1"]}))
    monkeypatch.setattr(activities, "mark_phase_takeover_core",
                        rec("takeover", {"status": "takeover"}))
    monkeypatch.setattr(activities, "fail_run_core", rec("fail", {"status": "failed"}))
    monkeypatch.setattr(activities, "verify_write_completeness_core",
                        rec("verify", {"present": ["prd"], "expected": ["prd"]}))
    monkeypatch.setattr(activities, "open_gate_core", rec("open", "appr1"))
    monkeypatch.setattr(activities, "publish_artifacts_core",
                        rec("publish", {"published": ["a1"]}))
    monkeypatch.setattr(activities, "transition_work_item_core",
                        rec("transition", {"state": "done"}))
    monkeypatch.setattr(activities, "reject_run_core", rec("reject", {"status": "rejected"}))
    return calls


def _companion_input():
    return AgentRunInput(
        run_id="r1", tenant_id="t1", project_id="p1", work_item_id="w1",
        agent_spec_id="s1", phase="prd", execution_mode="companion",
        report_timeout_seconds=2,
    )


@pytest.mark.asyncio
async def test_workflow_companion_branch_approved(monkeypatch):
    from temporalio.worker import Worker

    from orchestration.workflows import AgentRunWorkflow

    calls: list[str] = []
    _patch_cores(monkeypatch, calls)
    client = await _client()
    tq = f"test-{uuid.uuid4()}"
    with ThreadPoolExecutor(max_workers=4) as executor:
        async with Worker(client, task_queue=tq, workflows=[AgentRunWorkflow],
                          activities=activities.ALL_ACTIVITIES, activity_executor=executor):
            handle = await client.start_workflow(
                AgentRunWorkflow.run, _companion_input(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal(AgentRunWorkflow.phase_reported,
                                PhaseReport(status="ok", body="x"))
            from orchestration.types import GateDecision
            await handle.signal(AgentRunWorkflow.gate_decision, GateDecision(decision="approved"))
            result = await handle.result()
    assert result["status"] == "completed"
    assert calls == ["compose", "dispatch", "register", "verify", "open", "publish", "transition"]


@pytest.mark.asyncio
async def test_workflow_companion_offline_takeover(monkeypatch):
    from temporalio.worker import Worker

    from orchestration.workflows import AgentRunWorkflow

    calls: list[str] = []
    _patch_cores(monkeypatch, calls)
    client = await _client()
    tq = f"test-{uuid.uuid4()}"
    with ThreadPoolExecutor(max_workers=4) as executor:
        async with Worker(client, task_queue=tq, workflows=[AgentRunWorkflow],
                          activities=activities.ALL_ACTIVITIES, activity_executor=executor):
            handle = await client.start_workflow(
                AgentRunWorkflow.run, _companion_input(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            # Never report -> the 2s report timeout fires -> takeover.
            result = await handle.result()
    assert result["status"] == "takeover"
    assert calls == ["compose", "dispatch", "takeover"]
