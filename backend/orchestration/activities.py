"""Temporal activities (spec §5). All DB/engine/S3 side effects live here, never in
the workflow. Each activity is a thin @activity.defn wrapper over a sync *core* function
that is directly unit-testable; cores are idempotent by run_id so Temporal retries are safe.

`get_driver` / `get_object_store` are module-level factories so tests can swap in fakes.
Every DB touch runs inside `tenant_context` so RLS scopes it when the worker connects as
the non-superuser app role.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from mcp_platform_state import tools
from temporalio import activity

from apps.gates.models import Approval
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.context import tenant_context
from apps.workitems.models import WorkItem
from drivers import ClaudeDriver
from manifest import compose_manifest
from manifest.rules import get_prompt_rules
from storage import content_hash, s3_from_settings

from .types import AgentRunInput


class WriteCompletenessError(Exception):
    """Rule 11: a run reached completion without registering an expected artifact."""

_PLATFORM_TOOL_NAMES = [
    "get_context", "register_artifact", "update_artifact", "add_trace_edge", "log_event",
    "list_work_items", "create_work_item", "transition_work_item", "get_artifact",
    "list_artifacts", "detect_drift",
]
PLATFORM_TOOLS = [f"mcp__platform-state__{name}" for name in _PLATFORM_TOOL_NAMES]


# ── injectable factories (tests monkeypatch these) ──────────────────
def get_driver():
    return ClaudeDriver()


def get_object_store():
    return s3_from_settings()


def load_rules() -> str:
    # Distilled prompt-enforced rules (RULE-BEHAVIOR / RULE-EXECUTION), AGENT_MIGRATION_SPEC §4.
    return get_prompt_rules()


def _now() -> datetime:
    return datetime.now(UTC)


def _mcp_servers(tenant_id: str) -> dict:
    """Config the engine uses to launch the platform-state MCP server, with the tenant
    bound from the control plane (the agent never passes a tenant)."""
    repo_root = str(Path(__file__).resolve().parents[2])
    return {
        "platform-state": {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "mcp_platform_state.server"],
            "env": {
                "PLATFORM_TENANT_ID": str(tenant_id),
                "DJANGO_SETTINGS_MODULE": "config.settings",
                "DATABASE_URL": settings.DATABASES["default"].get("URL", ""),
                "PYTHONPATH": repo_root,
            },
        }
    }


# ── cores (idempotent by run_id) ────────────────────────────────────
def compose_manifest_core(inp: AgentRunInput) -> str:
    with tenant_context(inp.tenant_id):
        work_item = WorkItem.objects.get(id=inp.work_item_id, tenant_id=inp.tenant_id)
        context = tools.get_context(inp.tenant_id, inp.project_id, inp.phase)
        return compose_manifest(
            context=context, work_item=tools._work_item(work_item),
            phase=inp.phase, rules=load_rules(),
        )


_EXECUTED_STATES = {Run.Status.AWAITING_GATE, Run.Status.APPROVED, Run.Status.COMPLETED}


def execute_agent_core(inp: AgentRunInput, manifest: str) -> dict:
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        existing = list(Artifact.objects.filter(run_id=inp.run_id, tenant_id=inp.tenant_id))
        if existing and run.status in _EXECUTED_STATES:
            return {"artifact_ids": [str(a.id) for a in existing], "idempotent": True}
        run.status = Run.Status.RUNNING
        run.started_at = _now()
        run.save(update_fields=["status", "started_at", "updated_at"])
        agent_spec = AgentSpec.objects.get(id=inp.agent_spec_id, tenant_id=inp.tenant_id)
        work_item = WorkItem.objects.get(id=inp.work_item_id, tenant_id=inp.tenant_id)

    # Engine call is outside the tenant_context cursor (it may be long).
    driver = get_driver()
    result = asyncio.run(
        driver.run_planning_task(
            manifest=manifest, agent_spec=agent_spec,
            mcp_servers=_mcp_servers(inp.tenant_id), allowed_tools=PLATFORM_TOOLS,
            work_item=work_item,
        )
    )
    body = result.outputs.get("result") or result.outputs.get("text") or ""
    s3_key = f"drafts/{inp.tenant_id}/{inp.project_id}/{inp.run_id}/{inp.phase}.md"
    get_object_store().put(s3_key, body)
    digest = content_hash(body.encode("utf-8"))

    artifact = tools.register_artifact(
        inp.tenant_id, inp.project_id, inp.run_id, inp.phase, inp.phase,
        "internal", digest, s3_key=s3_key,
    )
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.AWAITING_GATE
        run.cost_usd = Decimal(str(result.cost_usd))
        run.outputs = {
            "artifact_s3_key": s3_key, "content_hash": digest, "cost_usd": result.cost_usd,
        }
        run.ended_at = _now()
        run.save(update_fields=["status", "cost_usd", "outputs", "ended_at", "updated_at"])
        tools.log_event(
            inp.tenant_id, "orchestrator", "run.executed", "run", inp.run_id,
            {"artifact_id": artifact["id"]},
        )
    return {"artifact_ids": [artifact["id"]], "cost_usd": result.cost_usd}


def open_gate_core(inp: AgentRunInput) -> str:
    from apps.gates.wcag import conditions_for_phase

    with tenant_context(inp.tenant_id):
        approval, created = Approval.objects.get_or_create(
            run_id=inp.run_id, gate_type=inp.gate_type, tenant_id=inp.tenant_id,
            defaults={
                "work_item_id": inp.work_item_id,
                "required_role": inp.required_role,
                "decision": Approval.Decision.PENDING,
                # a11y/WCAG gate (D6): the design phase's gate carries the WCAG checklist.
                "conditions": conditions_for_phase(inp.phase),
            },
        )
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        if run.status != Run.Status.AWAITING_GATE:
            run.status = Run.Status.AWAITING_GATE
            run.save(update_fields=["status", "updated_at"])
        if created:
            tools.log_event(
                inp.tenant_id, "orchestrator", "gate.opened", "approval", str(approval.id),
                {"required_role": inp.required_role},
            )
    return str(approval.id)


def publish_artifacts_core(inp: AgentRunInput) -> dict:
    """On APPROVED: snapshot to S3, push to the live SoR where a connector is configured
    (gate→publish→pointer+version, spec §3), else keep sor=internal. Idempotent — already
    -published artifacts are skipped, and a docstore re-publish updates the same page."""
    from apps.projects.models import Project
    from integrations.publish import publish_to_docstore, resolve_capability
    from integrations.types import CapabilityUnavailable

    store = get_object_store()
    with tenant_context(inp.tenant_id):
        project = Project.objects.get(id=inp.project_id, tenant_id=inp.tenant_id)
        work_item = WorkItem.objects.get(id=inp.work_item_id, tenant_id=inp.tenant_id)
        title_base = work_item.feature_stream or project.name
        artifacts = list(Artifact.objects.filter(run_id=inp.run_id, tenant_id=inp.tenant_id))

    published: list[str] = []
    for artifact in artifacts:
        if artifact.status == Artifact.Status.PUBLISHED:
            published.append(str(artifact.id))
            continue

        if artifact.s3_key:  # immutable audit snapshot regardless of SoR
            snap = (
                f"snapshots/{inp.tenant_id}/{inp.project_id}/{inp.run_id}/"
                f"{artifact.phase}.v{artifact.version}.md"
            )
            store.copy(artifact.s3_key, snap)

        ref = None
        if resolve_capability(artifact.type) == "docstore":
            body_md = store.get(artifact.s3_key).decode("utf-8") if artifact.s3_key else ""
            title = f"{title_base} — {artifact.phase.title()}"
            try:
                ref = publish_to_docstore(
                    tenant_id=inp.tenant_id, artifact=artifact, body_md=body_md, title=title,
                )
            except CapabilityUnavailable:
                ref = None  # no connector configured → internal SoR fallback (blueprint B3)

        if ref is not None:
            tools.update_artifact(
                inp.tenant_id, str(artifact.id),
                status=Artifact.Status.PUBLISHED, sor=ref.sor,
                external_ref={"sor": ref.sor, "id": ref.id, "url": ref.url, "version": ref.version},
            )
        else:
            tools.update_artifact(
                inp.tenant_id, str(artifact.id),
                status=Artifact.Status.PUBLISHED, sor=Artifact.SoR.INTERNAL,
            )
        published.append(str(artifact.id))

    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.COMPLETED
        run.save(update_fields=["status", "updated_at"])
        # The Approval decision is recorded by the gate service (decide_gate, T9),
        # not here — that path owns the approver + decided_at.
        tools.log_event(
            inp.tenant_id, "orchestrator", "artifacts.published", "run", inp.run_id,
            {"artifact_ids": published},
        )
    return {"published": published}


def transition_work_item_core(inp: AgentRunInput, to_state: str) -> dict:
    with tenant_context(inp.tenant_id):
        tools.transition_work_item(inp.tenant_id, inp.work_item_id, to_state)
        tools.log_event(
            inp.tenant_id, "orchestrator", "workitem.transitioned", "work_item",
            inp.work_item_id, {"to_state": to_state},
        )
    return {"work_item_id": inp.work_item_id, "state": to_state}


def reject_run_core(inp: AgentRunInput, comment: str) -> dict:
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.REJECTED
        run.save(update_fields=["status", "updated_at"])
        tools.transition_work_item(inp.tenant_id, inp.work_item_id, WorkItem.State.IN_PROGRESS)
        # Approval decision/comment recorded by the gate service (decide_gate, T9).
        tools.log_event(
            inp.tenant_id, "orchestrator", "run.rejected", "run", inp.run_id, {"comment": comment}
        )
    return {"status": "rejected"}


def verify_write_completeness_core(inp: AgentRunInput, expected_types: list[str]) -> dict:
    """Rule 11 (platform-enforced): before the gate opens, confirm the run actually
    registered the artifacts its phase was supposed to produce."""
    with tenant_context(inp.tenant_id):
        present = set(
            Artifact.objects.filter(run_id=inp.run_id, tenant_id=inp.tenant_id)
            .values_list("type", flat=True)
        )
    missing = [t for t in expected_types if t not in present]
    if missing:
        raise WriteCompletenessError(
            f"run {inp.run_id} reached the gate without expected artifact types {missing}"
        )
    return {"present": sorted(present), "expected": list(expected_types)}


# ── activity wrappers (sync → run in the worker's thread pool) ──────
# Activities run in worker threads with no request/response cycle, so close the
# thread's Django connection at the boundary — otherwise long-running workers (and
# multi-activity tests) leak a DB connection per thread. Reopened lazily next use.
def _boundary(core, *args):
    from django.db import connection

    try:
        return core(*args)
    finally:
        connection.close()


@activity.defn(name="compose_manifest")
def compose_manifest_activity(inp: AgentRunInput) -> str:
    return _boundary(compose_manifest_core, inp)


@activity.defn(name="execute_agent")
def execute_agent_activity(inp: AgentRunInput, manifest: str) -> dict:
    return _boundary(execute_agent_core, inp, manifest)


@activity.defn(name="open_gate")
def open_gate_activity(inp: AgentRunInput) -> str:
    return _boundary(open_gate_core, inp)


@activity.defn(name="publish_artifacts")
def publish_artifacts_activity(inp: AgentRunInput) -> dict:
    return _boundary(publish_artifacts_core, inp)


@activity.defn(name="transition_work_item")
def transition_work_item_activity(inp: AgentRunInput, to_state: str) -> dict:
    return _boundary(transition_work_item_core, inp, to_state)


@activity.defn(name="reject_run")
def reject_run_activity(inp: AgentRunInput, comment: str) -> dict:
    return _boundary(reject_run_core, inp, comment)


@activity.defn(name="verify_writes")
def verify_writes_activity(inp: AgentRunInput, expected_types: list[str]) -> dict:
    return _boundary(verify_write_completeness_core, inp, expected_types)


ALL_ACTIVITIES = [
    compose_manifest_activity,
    execute_agent_activity,
    open_gate_activity,
    publish_artifacts_activity,
    transition_work_item_activity,
    reject_run_activity,
    verify_writes_activity,
]
