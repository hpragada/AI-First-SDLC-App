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


class ActiveRunError(TriggerError):
    """A run is already in progress for this work item (Bugs S.No 77, Case 2). The view maps
    this to HTTP 409 so the UI can offer 'wait / take over' rather than silently double-running."""


# Statuses that mean a run is still live for a work item — re-triggering while one of these is
# open would spawn a second concurrent run against the same branch/PR (Bugs S.No 77). STALLED is
# intentionally excluded: it is parked for human takeover (S.No 89) and a re-trigger is a valid
# restart there.
_ACTIVE_RUN_STATUSES = (
    Run.Status.PENDING,
    Run.Status.RUNNING,
    Run.Status.AWAITING_GATE,
    Run.Status.APPROVED,
)


def _guard_no_active_run(tenant_id: str, work_item_id: str) -> None:
    """Raise ActiveRunError if the work item already has a live run (must be called inside a
    tenant_context)."""
    active = (
        Run.objects.filter(
            tenant_id=tenant_id, work_item_id=work_item_id, status__in=_ACTIVE_RUN_STATUSES
        )
        .order_by("-created_at")
        .first()
    )
    if active is not None:
        raise ActiveRunError(
            f"a run is already in progress for this work item (status: {active.status}). "
            "Wait for it to finish or take it over before starting a new one."
        )


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
    local Claude Code). None ⇒ no companion enrolled ⇒ server fallback.

    Selection (Bugs S.No 84): a user often has several ACTIVE enrollments for one project
    (each Connect Machine visit mints one), and only ONE of them is the token the running
    companion actually polls with. Picking purely by recency could dispatch to an enrollment
    that never connected — the live companion then long-polls /work/ into 204s forever and
    the run sticks in pending. So prefer, in order:
      1. the newest enrollment that is ONLINE (last_seen within ONLINE_THRESHOLD — it is
         heartbeating/polling right now);
      2. else the newest that has EVER checked in (a companion held that token at some point);
      3. else the newest overall (nothing has connected yet — e.g. the user triggers before
         starting the companion; the dispatch waits for it, same as before).
    """
    from django.utils import timezone

    from apps.runs.enrollment import ONLINE_THRESHOLD
    from apps.runs.models import RunnerEnrollment

    if not user_id:
        return None
    candidates = list(
        RunnerEnrollment.objects.filter(
            tenant_id=tenant_id, project_id=project_id, developer_id=user_id,
            status=RunnerEnrollment.Status.ACTIVE,
        )
        .order_by("-created_at")
    )
    if not candidates:
        return None
    cutoff = timezone.now() - ONLINE_THRESHOLD
    online = [e for e in candidates if e.last_seen and e.last_seen >= cutoff]
    if online:
        return online[0]
    seen = [e for e in candidates if e.last_seen]
    if seen:
        return seen[0]
    return candidates[0]


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
        _guard_no_active_run(tenant_id, work_item_id)

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
        _guard_no_active_run(tenant_id, work_item_id)
        repo = repo or (work_item.repo.name if work_item.repo else None)
        base = base or (work_item.repo.default_base if work_item.repo else None)
        if not repo:
            from apps.projects.models import Repository

            project_repos = Repository.objects.filter(
                tenant_id=tenant_id, project_id=project_id
            )
            repo_count = project_repos.count()
            # Multi-repo (D5 / Hybrid Option C): NEVER silently default an unpinned work item —
            # its repo is chosen by the planner and confirmed at the Task Breakdown gate, so a
            # build with no repo means that assignment was missed. Fail loud rather than PR into
            # whatever happens to be the default repo (e.g. backend code into the frontend repo).
            if repo_count > 1:
                raise TriggerError(
                    "this work item has no repository assigned and the project has multiple "
                    "repositories — assign its repo (confirm it at the Task Breakdown gate or set "
                    "the work item's repo) before building."
                )
            # Single-repo: fall back to the project's default repository (S-13) so a task can be
            # built from the UI without first pinning a repo (proposed items have none).
            default_repo = project_repos.filter(is_default=True).first()
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
            # The human title, for what a PERSON reads (Bugs S.No 151) — artifact + PR titles.
            work_item_title=work_item.title or "",
            enrollment_id=str(enrollment.id) if enrollment is not None else None,
        )
        tools.log_event(
            tenant_id, "platform", "build.triggered", "run", str(run.id),
            {"workflow_id": workflow_id, "repo": repo, "work_item_key": work_item_key},
        )

    workflow_starter(workflow_id, inp)
    return TriggerResult(run_id=str(run.id), workflow_id=workflow_id)
