"""Companion phase report → resume the AgentRunWorkflow (req #1).

The companion POSTs the planning/review result it produced locally; we record it on the run
and send the `phase_reported` signal so the waiting workflow proceeds (mirrors
`report_build`'s signal pattern). The signal sender is injectable for unit tests.
"""
from __future__ import annotations

from dataclasses import asdict

from .types import PhaseReport


class PhaseReportError(Exception):
    """The report could not be applied (e.g. run has no workflow to signal)."""


def _default_signal_sender(workflow_id: str, report: PhaseReport) -> None:
    import asyncio

    from django.conf import settings
    from temporalio.client import Client

    async def _send() -> None:
        client = await Client.connect(
            settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE
        )
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal("phase_reported", report)

    asyncio.run(_send())


def report_phase(*, tenant_id, run_id, report, signal_sender=None) -> dict:
    """Record the companion's phase report on the run + signal the workflow to resume."""
    from mcp_platform_state import tools

    from apps.runs.models import Run
    from apps.tenancy.context import tenant_context

    signal_sender = signal_sender or _default_signal_sender
    if isinstance(report, dict):
        report = PhaseReport(
            **{k: report[k] for k in report if k in PhaseReport.__annotations__})

    with tenant_context(tenant_id):
        run = Run.objects.get(id=run_id, tenant_id=tenant_id)
        run.outputs = {**(run.outputs or {}), "report": asdict(report)}
        # Close the claim SYNCHRONOUSLY, here, before the (async) workflow flips it. The daemon
        # polls /api/runner/work/ again the instant this report returns; if the dispatch were
        # still "claimed" and the phase had outrun CLAIM_LEASE, the work-claim lease would judge
        # it stale and re-claim + re-run this very phase (the duplicate-v2 regression). Marking
        # the dispatch terminal now removes it from the claimable set immediately.
        inputs = dict(run.inputs or {})
        dispatch = dict(inputs.get("dispatch") or {})
        if dispatch:
            dispatch["status"] = "reported"
            inputs["dispatch"] = dispatch
            run.inputs = inputs
            run.save(update_fields=["outputs", "inputs", "updated_at"])
        else:
            run.save(update_fields=["outputs", "updated_at"])
        workflow_id = run.temporal_workflow_id
        tools.log_event(tenant_id, "companion", "phase.reported", "run", str(run_id),
                        {"status": report.status})

    if not workflow_id:
        raise PhaseReportError("run has no temporal_workflow_id; cannot resume the workflow")
    try:
        signal_sender(workflow_id, report)
    except Exception as exc:  # noqa: BLE001
        # A late or duplicate report can land after the workflow already finished (e.g. the
        # phase was reported once, gated, and completed). That's not a server error — the
        # result is recorded — so acknowledge it instead of 500-ing, which would otherwise
        # crash the companion daemon on an unfatal condition.
        if "already completed" in str(exc).lower():
            return {"run_id": str(run_id), "signaled": False, "status": report.status,
                    "note": "workflow already completed"}
        raise
    return {"run_id": str(run_id), "signaled": True, "status": report.status}
