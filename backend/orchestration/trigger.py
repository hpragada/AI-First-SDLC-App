"""Phase trigger (AGENT_MIGRATION_SPEC §5).

In the platform there are no slash commands: a legacy command becomes a *phase trigger* —
a UI/API action that creates a Run for a WorkItem and starts its AgentRunWorkflow. This
replaces the `commands/*.md` files. The workflow starter is injectable for testing.
"""
from __future__ import annotations

from dataclasses import dataclass

from mcp_platform_state import tools

from apps.registry.catalog import gate_role_for
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.context import tenant_context
from apps.workitems.models import WorkItem

from .types import AgentRunInput


class TriggerError(Exception):
    """Could not start a phase run (e.g. no matching AgentSpec)."""


@dataclass
class TriggerResult:
    run_id: str
    workflow_id: str


def _default_workflow_starter(workflow_id: str, inp: AgentRunInput) -> None:
    import asyncio

    from django.conf import settings
    from temporalio.client import Client

    from .workflows import AgentRunWorkflow

    async def _start() -> None:
        client = await Client.connect(
            settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE
        )
        await client.start_workflow(
            AgentRunWorkflow.run, inp, id=workflow_id, task_queue=settings.TEMPORAL_TASK_QUEUE
        )

    asyncio.run(_start())


def trigger_phase(
    *,
    tenant_id: str,
    project_id: str,
    work_item_id: str,
    agent_key: str,
    gate_type: str = "phase_gate",
    required_role: str | None = None,
    workflow_starter=None,
) -> TriggerResult:
    """Start an agent run for a work item and kick off its Temporal workflow."""
    workflow_starter = workflow_starter or _default_workflow_starter

    with tenant_context(tenant_id):
        spec = (
            AgentSpec.objects.filter(tenant_id=tenant_id, key=agent_key)
            .order_by("-semver")
            .first()
        )
        if spec is None:
            raise TriggerError(f"no AgentSpec registered for key {agent_key!r}")
        work_item = WorkItem.objects.get(id=work_item_id, tenant_id=tenant_id)

        phase = spec.phase_label or agent_key
        role = required_role or gate_role_for(agent_key)
        run = Run.objects.create(
            tenant_id=tenant_id, work_item=work_item, agent_spec=spec,
            engine=spec.recommended_engine, model=spec.recommended_model,
            prompt_version=spec.prompt_version, status=Run.Status.PENDING,
        )
        workflow_id = f"agent-run-{run.id}"
        run.temporal_workflow_id = workflow_id
        run.save(update_fields=["temporal_workflow_id", "updated_at"])

        inp = AgentRunInput(
            run_id=str(run.id), tenant_id=str(tenant_id), project_id=str(project_id),
            work_item_id=str(work_item_id), agent_spec_id=str(spec.id), phase=phase,
            gate_type=gate_type, required_role=role,
        )
        tools.log_event(
            tenant_id, "platform", "run.triggered", "run", str(run.id),
            {"agent_key": agent_key, "workflow_id": workflow_id},
        )

    workflow_starter(workflow_id, inp)
    return TriggerResult(run_id=str(run.id), workflow_id=workflow_id)
