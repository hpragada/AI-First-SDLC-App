"""BuildWorkflow activities (Phase-2 §4). Each is a thin @activity.defn over an idempotent
*core* (idempotent by run_id so Temporal retries are safe). Side effects only here, never in
the workflow. CodeHost goes through the capability seam (`get_capability`); the engine never
touches Git — the platform opens/merges the PR (D2).
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from mcp_platform_state import tools
from temporalio import activity

from apps.gates.models import Approval
from apps.registry.models import Artifact
from apps.runs.models import Run
from apps.tenancy.context import tenant_context
from apps.workitems.models import WorkItem

from .activities import _boundary, compose_manifest_core
from .build_types import BuildInput, BuildReport


def _load_agent_body(agent_spec_id: str, tenant_id: str) -> tuple[str, str]:
    """Read the migrated build agent's body (+ model) to ship to the companion. Tolerant —
    the agent is migrated in §8; an absent body is empty, not fatal, so dispatch works now."""
    from apps.registry.models import AgentSpec

    with tenant_context(tenant_id):
        spec = AgentSpec.objects.filter(id=agent_spec_id, tenant_id=tenant_id).first()
        body_ref = spec.body_ref if spec else ""
        model = spec.recommended_model if spec else ""
    if not body_ref:
        return "", model
    path = Path(body_ref)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / body_ref
    try:
        return path.read_text(encoding="utf-8"), model
    except OSError:
        return "", model


# ── cores (idempotent by run_id) ────────────────────────────────────
def dispatch_build_core(inp: BuildInput) -> dict:
    """Assemble the self-contained BuildTask payload (manifest + agent body) for the companion
    to fetch, mark the run RUNNING, and announce the dispatch. Idempotent."""
    from django.conf import settings

    manifest = compose_manifest_core(inp)            # duck-typed: reads work_item/project/phase
    agent_body, model = _load_agent_body(inp.agent_spec_id, inp.tenant_id)
    payload = {
        "run_id": inp.run_id, "tenant_id": inp.tenant_id, "project_id": inp.project_id,
        "work_item_id": inp.work_item_id, "work_item_key": inp.work_item_key,
        "repo": inp.repo, "base": inp.base, "phase": inp.phase,
        "manifest": manifest, "agent_body": agent_body, "model": model,
        "api_url": getattr(settings, "PLATFORM_API_URL", ""),
    }
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.inputs = {**(run.inputs or {}), "build_task": payload}
        if run.status not in (Run.Status.RUNNING, Run.Status.AWAITING_GATE, Run.Status.COMPLETED):
            run.status = Run.Status.RUNNING
        run.save(update_fields=["inputs", "status", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "build.dispatched", "run", inp.run_id,
                        {"repo": inp.repo, "work_item": inp.work_item_key})
    return {"dispatched": True}


def _code_artifact(inp: BuildInput) -> Artifact | None:
    with tenant_context(inp.tenant_id):
        return (
            Artifact.objects
            .filter(run_id=inp.run_id, tenant_id=inp.tenant_id, type="code").first()
        )


def open_build_pr_core(inp: BuildInput, report: BuildReport) -> dict:
    """Open the draft PR for the companion-pushed branch and register the `code` pointer.
    Idempotent — an existing code artifact / open PR for the head is reused (B1)."""
    from integrations.registry import get_capability

    existing = _code_artifact(inp)
    if existing is not None and existing.external_ref:
        return {"pr": existing.external_ref, "artifact_id": str(existing.id), "idempotent": True}

    codehost = get_capability(inp.tenant_id, "codehost")
    ref = codehost.open_pull_request(
        repo=inp.repo, head=report.branch, base=inp.base,
        title=f"{inp.work_item_key}: build", body=f"Build for WorkItem {inp.work_item_id}.",
        draft=True,
    )
    external_ref = {"sor": "git", "repo": ref.repo, "number": ref.number,
                    "head": ref.head, "url": ref.url, "sha": ref.sha}
    artifact = tools.register_artifact(
        inp.tenant_id, inp.project_id, inp.run_id, inp.phase, "code", "git",
        content_hash=report.head_sha or "", external_ref=external_ref,
    )
    tools.update_artifact(inp.tenant_id, artifact["id"], status=Artifact.Status.STAGED)
    if report.head_sha:
        try:
            codehost.set_commit_status(repo=inp.repo, sha=report.head_sha, state="pending",
                                       context="sdlc/build")
        except Exception:  # noqa: BLE001 — status is best-effort
            pass
    with tenant_context(inp.tenant_id):
        tools.log_event(inp.tenant_id, "orchestrator", "build.pr_opened", "run", inp.run_id,
                        {"pr": ref.url, "artifact_id": artifact["id"]})
    return {"pr": external_ref, "artifact_id": artifact["id"]}


def open_merge_gate_core(inp: BuildInput) -> str:
    """Open the merge gate (a reviewer Approval) — the gated SoR write is the merge (#5/#8)."""
    with tenant_context(inp.tenant_id):
        approval, created = Approval.objects.get_or_create(
            run_id=inp.run_id, gate_type=inp.gate_type, tenant_id=inp.tenant_id,
            defaults={"work_item_id": inp.work_item_id, "required_role": inp.required_role,
                      "decision": Approval.Decision.PENDING},
        )
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        if run.status != Run.Status.AWAITING_GATE:
            run.status = Run.Status.AWAITING_GATE
            run.save(update_fields=["status", "updated_at"])
        if created:
            tools.log_event(inp.tenant_id, "orchestrator", "gate.opened", "approval",
                            str(approval.id), {"required_role": inp.required_role,
                                               "gate": "merge"})
    return str(approval.id)


def merge_build_pr_core(inp: BuildInput) -> dict:
    """On approval, merge the PR (the gated SoR write). Idempotent — an already-merged PR is
    a no-op; the code artifact becomes published and the run completes."""
    from integrations.registry import get_capability

    artifact = _code_artifact(inp)
    if artifact is None or not artifact.external_ref:
        raise RuntimeError(f"no code artifact/PR to merge for run {inp.run_id}")
    ref = artifact.external_ref
    pr_ref = f"{ref['repo']}#{ref['number']}"
    codehost = get_capability(inp.tenant_id, "codehost")
    pr = codehost.get_pull_request(pr_ref=pr_ref)
    if not pr.merged:
        pr = codehost.merge_pull_request(pr_ref=pr_ref)
    with tenant_context(inp.tenant_id):
        tools.update_artifact(inp.tenant_id, str(artifact.id), status=Artifact.Status.PUBLISHED)
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.COMPLETED
        run.save(update_fields=["status", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "build.merged", "run", inp.run_id,
                        {"pr": pr_ref})
    return {"merged": True, "pr_ref": pr_ref}


def transition_build_work_item_core(inp: BuildInput, to_state: str) -> dict:
    with tenant_context(inp.tenant_id):
        tools.transition_work_item(inp.tenant_id, inp.work_item_id, to_state)
        tools.log_event(inp.tenant_id, "orchestrator", "workitem.transitioned", "work_item",
                        inp.work_item_id, {"to_state": to_state})
    return {"work_item_id": inp.work_item_id, "state": to_state}


def mark_takeover_core(inp: BuildInput) -> dict:
    """Offline-runner path (PG10): the companion never reported → park the WorkItem for human
    takeover and flag the run failed (never silently hang)."""
    with tenant_context(inp.tenant_id):
        WorkItem.objects.filter(id=inp.work_item_id, tenant_id=inp.tenant_id).update(
            takeover_flag=True
        )
        Run.objects.filter(id=inp.run_id, tenant_id=inp.tenant_id).update(
            status=Run.Status.FAILED
        )
        tools.log_event(inp.tenant_id, "orchestrator", "build.takeover", "run", inp.run_id,
                        {"reason": "runner offline / no report before timeout"})
    return {"status": "takeover"}


def mark_build_failed_core(inp: BuildInput, reason: str) -> dict:
    """Dead-letter / failed-build compensation: flag the run failed, return the WorkItem to
    in_progress (the branch/draft PR are left for human disposition — register-don't-recreate)."""
    with tenant_context(inp.tenant_id):
        Run.objects.filter(id=inp.run_id, tenant_id=inp.tenant_id).update(
            status=Run.Status.FAILED
        )
        tools.transition_work_item(inp.tenant_id, inp.work_item_id, WorkItem.State.IN_PROGRESS)
        tools.log_event(inp.tenant_id, "orchestrator", "build.failed", "run", inp.run_id,
                        {"reason": reason})
    return {"status": "build_failed"}


def reject_build_core(inp: BuildInput, comment: str) -> dict:
    with tenant_context(inp.tenant_id):
        Run.objects.filter(id=inp.run_id, tenant_id=inp.tenant_id).update(
            status=Run.Status.REJECTED
        )
        tools.transition_work_item(inp.tenant_id, inp.work_item_id, WorkItem.State.IN_PROGRESS)
        tools.log_event(inp.tenant_id, "orchestrator", "build.rejected", "run", inp.run_id,
                        {"comment": comment})
    return {"status": "rejected"}


# ── activity wrappers (close the DB connection at the boundary) ─────
@activity.defn(name="dispatch_build")
def dispatch_build_activity(inp: BuildInput) -> dict:
    return _boundary(dispatch_build_core, inp)


@activity.defn(name="open_build_pr")
def open_build_pr_activity(inp: BuildInput, report: BuildReport) -> dict:
    return _boundary(open_build_pr_core, inp, report)


@activity.defn(name="open_merge_gate")
def open_merge_gate_activity(inp: BuildInput) -> str:
    return _boundary(open_merge_gate_core, inp)


@activity.defn(name="merge_build_pr")
def merge_build_pr_activity(inp: BuildInput) -> dict:
    return _boundary(merge_build_pr_core, inp)


@activity.defn(name="transition_build_work_item")
def transition_build_work_item_activity(inp: BuildInput, to_state: str) -> dict:
    return _boundary(transition_build_work_item_core, inp, to_state)


@activity.defn(name="mark_takeover")
def mark_takeover_activity(inp: BuildInput) -> dict:
    return _boundary(mark_takeover_core, inp)


@activity.defn(name="mark_build_failed")
def mark_build_failed_activity(inp: BuildInput, reason: str) -> dict:
    return _boundary(mark_build_failed_core, inp, reason)


@activity.defn(name="reject_build")
def reject_build_activity(inp: BuildInput, comment: str) -> dict:
    return _boundary(reject_build_core, inp, comment)


BUILD_ACTIVITIES = [
    dispatch_build_activity,
    open_build_pr_activity,
    open_merge_gate_activity,
    merge_build_pr_activity,
    transition_build_work_item_activity,
    mark_takeover_activity,
    mark_build_failed_activity,
    reject_build_activity,
]


# Convenience for the report path (used by the report service when building the signal).
def report_to_dict(report: BuildReport) -> dict:
    return asdict(report)
