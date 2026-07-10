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


def _resolve_enrollment(tenant_id, project_id, user_id):
    """The triggering user's active companion for this project (req #1 — run on their own
    local Claude Code). None ⇒ no companion enrolled ⇒ server fallback."""
    from apps.runs.models import RunnerEnrollment

    if not user_id:
        return None
    return (
        RunnerEnrollment.objects.filter(
            tenant_id=tenant_id, project_id=project_id, developer_id=user_id,
            status=RunnerEnrollment.Status.ACTIVE,
        )
        .order_by("-created_at").first()
    )


def trigger_phase(
    *,
    tenant_id: str,
    project_id: str,
    work_item_id: str,
    agent_key: str,
    gate_type: str = "phase_gate",
    required_role: str | None = None,
    triggered_by: str | None = None,
    execution_mode: str | None = None,
    workflow_starter=None,
) -> TriggerResult:
    """Start an agent run for a work item and kick off its Temporal workflow. The phase runs
    on the triggering user's enrolled local companion when one exists (`execution_mode`
    auto-resolves to "companion"), else server-side (the CI/test fallback)."""
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
        enrollment = _resolve_enrollment(tenant_id, project_id, triggered_by)
        mode = execution_mode or ("companion" if enrollment is not None else "server")
        run = Run.objects.create(
            tenant_id=tenant_id, work_item=work_item, agent_spec=spec,
            engine=spec.recommended_engine, model=spec.recommended_model,
            prompt_version=spec.prompt_version, status=Run.Status.PENDING,
            triggered_by_id=triggered_by,
        )
        workflow_id = f"agent-run-{run.id}"
        run.temporal_workflow_id = workflow_id
        run.save(update_fields=["temporal_workflow_id", "updated_at"])

        inp = AgentRunInput(
            run_id=str(run.id), tenant_id=str(tenant_id), project_id=str(project_id),
            work_item_id=str(work_item_id), agent_spec_id=str(spec.id), phase=phase,
            gate_type=gate_type, required_role=role, execution_mode=mode,
            enrollment_id=str(enrollment.id) if enrollment is not None else None,
        )
        tools.log_event(
            tenant_id, "platform", "run.triggered", "run", str(run.id),
            {"agent_key": agent_key, "workflow_id": workflow_id, "execution_mode": mode},
        )

    workflow_starter(workflow_id, inp)
    return TriggerResult(run_id=str(run.id), workflow_id=workflow_id)


def _default_build_starter(workflow_id: str, inp) -> None:
    import asyncio

    from django.conf import settings
    from temporalio.client import Client

    from .build_workflow import BuildWorkflow

    async def _start() -> None:
        client = await Client.connect(
            settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE
        )
        await client.start_workflow(
            BuildWorkflow.run, inp, id=workflow_id, task_queue=settings.TEMPORAL_TASK_QUEUE
        )

    asyncio.run(_start())


def trigger_build(
    *,
    tenant_id: str,
    project_id: str,
    work_item_id: str,
    agent_key: str = "07_implementation",
    repo: str | None = None,
    base: str | None = None,
    work_item_key: str | None = None,
    required_role: str = "reviewer",
    triggered_by: str | None = None,
    workflow_starter=None,
) -> TriggerResult:
    """Start a BuildWorkflow for a WorkItem (resolves repo/base from its Repository). The build
    runs on the triggering user's enrolled companion (claimable via /api/runner/work/)."""
    from .build_types import BuildInput

    workflow_starter = workflow_starter or _default_build_starter

    with tenant_context(tenant_id):
        spec = (
            AgentSpec.objects.filter(tenant_id=tenant_id, key=agent_key)
            .order_by("-semver").first()
        )
        if spec is None:
            raise TriggerError(f"no AgentSpec registered for key {agent_key!r}")
        work_item = WorkItem.objects.select_related("repo").get(
            id=work_item_id, tenant_id=tenant_id
        )
        repo = repo or (work_item.repo.name if work_item.repo else None)
        base = base or (work_item.repo.default_base if work_item.repo else None)
        if not repo:
            # Fall back to the project's default repository (S-13) so a task can be built from
            # the UI without first pinning a repo to the work item (proposed items have none).
            from apps.projects.models import Repository

            default_repo = Repository.objects.filter(
                tenant_id=tenant_id, project_id=project_id, is_default=True
            ).first()
            if default_repo is not None:
                repo = default_repo.name
                base = base or default_repo.default_base
        base = base or "main"
        if not repo:
            raise TriggerError(
                "no target repository for this build — add a repository to the project "
                "(Repositories) or set the work item's repo."
            )
        work_item_key = (
            work_item_key or (work_item.external_ref or {}).get("id")
            or f"WI-{str(work_item.id)[:8]}"
        )
        enrollment = _resolve_enrollment(tenant_id, project_id, triggered_by)
        run = Run.objects.create(
            tenant_id=tenant_id, work_item=work_item, agent_spec=spec,
            engine=spec.recommended_engine, model=spec.recommended_model,
            prompt_version=spec.prompt_version, status=Run.Status.PENDING,
            triggered_by_id=triggered_by,
        )
        workflow_id = f"build-run-{run.id}"
        run.temporal_workflow_id = workflow_id
        run.save(update_fields=["temporal_workflow_id", "updated_at"])

        inp = BuildInput(
            run_id=str(run.id), tenant_id=str(tenant_id), project_id=str(project_id),
            work_item_id=str(work_item_id), agent_spec_id=str(spec.id),
            work_item_key=work_item_key, repo=repo, base=base, required_role=required_role,
            enrollment_id=str(enrollment.id) if enrollment is not None else None,
        )
        tools.log_event(
            tenant_id, "platform", "build.triggered", "run", str(run.id),
            {"workflow_id": workflow_id, "repo": repo, "work_item_key": work_item_key},
        )

    workflow_starter(workflow_id, inp)
    return TriggerResult(run_id=str(run.id), workflow_id=workflow_id)
