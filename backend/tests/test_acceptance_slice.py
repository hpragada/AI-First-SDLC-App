"""P0-T14 — Phase-0 acceptance slice (spec §8).

Drives the whole spine end-to-end for the four planning phases
(ideation → requirements → prd → architecture):

  trigger → real Temporal AgentRunWorkflow → compose manifest → execute agent
  → register a DRAFT artifact (body to the object store) → write-completeness check
  → open gate → human approves (role-checked, via the real gate service) → publish
  (status=published, sor=internal) → transition the WorkItem to done → events + trace edges.

Only the ENGINE seam is stubbed (`get_driver` → a canned-result driver) and the object
store is in-memory — so NO live Claude run and no MinIO are needed, but every other piece
runs for real: the workflow on the live Temporal server, the activity cores, the MCP
tools, the DB writes, RLS scoping, and the gate signal. The derivation edges that the
real agent would write via `add_trace_edge` are added here to represent that call.

Requires the local Temporal server (skips if unreachable). `transaction=True` so the
worker threads' own DB connections see the committed setup rows.
"""
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from mcp_platform_state import tools

from apps.gates.models import Approval
from apps.gates.services import decide_gate
from apps.ledger.models import Event
from apps.projects.models import Project, ProjectProfile
from apps.registry.catalog import gate_role_for, seed_agent_specs
from apps.registry.models import AgentSpec, Artifact, TraceEdge
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from drivers.base import RunResult
from orchestration import activities
from orchestration.types import AgentRunInput
from orchestration.workflows import AgentRunWorkflow
from storage.object_store import InMemoryObjectStore

_PHASES = ["01_ideation", "02_requirements", "03_prd", "04_architecture"]
_TEMPORAL = "localhost:7233"


class _StubDriver:
    """Stands in for the ClaudeDriver — returns a canned draft, makes no engine call."""

    async def run_planning_task(self, *, manifest, agent_spec, mcp_servers, allowed_tools,
                                work_item):
        body = (
            f"# {agent_spec.phase_label.title()}\n\n"
            f"Draft for '{work_item.feature_stream}' (manifest: {len(manifest)} chars)."
        )
        return RunResult(outputs={"result": body}, artifacts=[], cost_usd=0.01, raw_messages=[])

    async def run_build_task(self, **kwargs):  # pragma: no cover - planning-only in P0
        raise NotImplementedError


async def _temporal_client():
    from temporalio.client import Client

    return await Client.connect(_TEMPORAL, namespace="default")


def _pending_approval_id(run_id: str) -> str | None:
    # Runs in a helper thread; close its connection after so it doesn't linger.
    from django.db import connection

    try:
        ap = Approval.objects.filter(run_id=run_id, decision=Approval.Decision.PENDING).first()
        return str(ap.id) if ap else None
    finally:
        connection.close()


def _approve(tenant_id: str, approval_id: str, user_id: str) -> None:
    from django.db import connection

    try:
        decide_gate(
            tenant_id=tenant_id, approval_id=approval_id, user_id=user_id,
            decision="approved", comment="approved by reviewer",
        )
    finally:
        connection.close()


async def _await_approval(run_id: str) -> str:
    """Wait for open_gate to create the Approval (ORM read off the main loop)."""
    for _ in range(100):
        ap = await asyncio.to_thread(_pending_approval_id, run_id)
        if ap:
            return ap
        await asyncio.sleep(0.2)
    raise AssertionError(f"gate never opened for run {run_id}")


async def _run_phase_to_completion(inp: AgentRunInput, workflow_id: str, approver_id: str) -> dict:
    """Run one phase's workflow to completion: start → wait for gate → approve → result."""
    from temporalio.worker import Worker

    client = await _temporal_client()
    task_queue = f"acc-{uuid.uuid4()}"
    with ThreadPoolExecutor(max_workers=4) as executor:
        async with Worker(
            client, task_queue=task_queue, workflows=[AgentRunWorkflow],
            activities=activities.ALL_ACTIVITIES, activity_executor=executor,
        ):
            handle = await client.start_workflow(
                AgentRunWorkflow.run, inp, id=workflow_id, task_queue=task_queue
            )
            approval_id = await _await_approval(inp.run_id)
            # Real, role-checked human decision (sync service → run off the loop).
            await asyncio.to_thread(_approve, inp.tenant_id, approval_id, approver_id)
            return await handle.result()


@pytest.mark.usefixtures("real_gate_signal")  # approves a gate on a LOCAL workflow
@pytest.mark.django_db(transaction=True)
def test_phase0_acceptance_slice(monkeypatch):
    from django.conf import settings

    # The repo .env points TEMPORAL_HOST at the container name; from the host the gate
    # service must reach the published port. (Worker/start use _TEMPORAL directly.)
    monkeypatch.setattr(settings, "TEMPORAL_HOST", _TEMPORAL)

    # Skip cleanly when Temporal isn't up (same policy as the other workflow tests).
    try:
        asyncio.run(_temporal_client())
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Temporal not reachable at {_TEMPORAL}: {exc}")

    store = InMemoryObjectStore()
    monkeypatch.setattr(activities, "get_driver", lambda: _StubDriver())
    monkeypatch.setattr(activities, "get_object_store", lambda: store)

    # ── Tenant + project + profile + an approver holding the gate roles ──
    tenant = Tenant.objects.create(name="Acceptance Co")
    project = Project.objects.create(
        tenant=tenant, name="Greenfield App", track=Project.Track.GREENFIELD
    )
    ProjectProfile.objects.create(
        tenant=tenant, project=project, important_context="Ship the MVP; keep it simple."
    )
    seed_agent_specs(tenant)
    approver = User.objects.create_user(
        email="po@acc.test", name="Reviewer", tenant=tenant, password="pw"
    )
    # 01–03 gate on product_owner, 04 on architect — the reviewer holds both.
    Membership.objects.create(tenant=tenant, user=approver, project=project, role="product_owner")
    Membership.objects.create(tenant=tenant, user=approver, project=project, role="architect")

    # ── Run each planning phase end-to-end ──
    artifact_ids: list[str] = []
    for key in _PHASES:
        spec = AgentSpec.objects.get(tenant=tenant, key=key)
        work_item = WorkItem.objects.create(
            tenant=tenant, project=project, type=WorkItem.Type.STORY,
            feature_stream="Greenfield MVP", state=WorkItem.State.PROPOSED,
        )
        run = Run.objects.create(
            tenant=tenant, work_item=work_item, agent_spec=spec,
            engine=spec.recommended_engine, model=spec.recommended_model,
            status=Run.Status.PENDING,
        )
        workflow_id = f"acc-{run.id}"
        run.temporal_workflow_id = workflow_id
        run.save(update_fields=["temporal_workflow_id", "updated_at"])

        inp = AgentRunInput(
            run_id=str(run.id), tenant_id=str(tenant.id), project_id=str(project.id),
            work_item_id=str(work_item.id), agent_spec_id=str(spec.id),
            phase=spec.phase_label, gate_type="phase_gate", required_role=gate_role_for(key),
        )
        result = asyncio.run(_run_phase_to_completion(inp, workflow_id, str(approver.id)))
        assert result["status"] == "completed", f"{key} did not complete: {result}"

        # Per-phase outcomes.
        run.refresh_from_db()
        work_item.refresh_from_db()
        assert run.status == Run.Status.COMPLETED
        assert work_item.state == WorkItem.State.DONE

        artifact = Artifact.objects.get(run_id=run.id)
        assert artifact.status == Artifact.Status.PUBLISHED
        assert artifact.sor == Artifact.SoR.INTERNAL
        assert artifact.s3_key and artifact.content_hash  # pointer + provenance, not the body

        # The agent's derivation link (ideation→requirements→prd→architecture).
        if artifact_ids:
            tools.add_trace_edge(str(tenant.id), artifact_ids[-1], str(artifact.id), "derives")
        artifact_ids.append(str(artifact.id))

    # ── Acceptance assertions (spec §8) ──
    assert len(artifact_ids) == 4
    published = Artifact.objects.filter(tenant=tenant, status=Artifact.Status.PUBLISHED)
    assert published.count() == 4
    assert set(published.values_list("sor", flat=True)) == {"internal"}
    assert set(published.values_list("phase", flat=True)) == {
        "ideation", "requirements", "prd", "architecture"
    }

    # Traceability chain: 3 derive edges linking the 4 artifacts in order.
    assert TraceEdge.objects.filter(tenant=tenant, rel="derives").count() == 3

    # Every phase published + every gate decided by the correct role.
    assert Event.objects.filter(tenant=tenant, action="artifacts.published").count() == 4
    assert Approval.objects.filter(
        tenant=tenant, decision=Approval.Decision.APPROVED, approver=approver
    ).count() == 4

    # ── RLS / isolation: a second tenant sees none of the first's rows ──
    # (Application boundary via the tenant-scoped tools; the DB-level RLS policy
    # itself is proven separately in test_rls.py.)
    other = Tenant.objects.create(name="Other Co")
    assert tools.list_artifacts(str(other.id), str(project.id)) == []
    assert WorkItem.objects.filter(tenant=other).count() == 0
