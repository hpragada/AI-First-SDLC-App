"""Companion build report → resume the BuildWorkflow (Phase-2 §4).

The companion POSTs its result; we record it on the run and send the `build_reported`
signal so the waiting workflow proceeds (mirrors `decide_gate`'s signal pattern). The
signal sender is injectable so this is unit-testable without Temporal.
"""
from __future__ import annotations

from dataclasses import asdict

from .build_types import BuildReport


class BuildReportError(Exception):
    """The report could not be applied (e.g. run has no workflow to signal)."""


def _scrub_nul(value):
    """Recursively strip NUL (``\\x00``) from every string in a report payload.

    Postgres ``text``/``jsonb`` cannot store ``\\u0000`` ("unsupported Unicode escape
    sequence — \\u0000 cannot be converted to text"), and companion-reported text can carry
    stray NUL bytes: 09b captures live browser/app/terminal output (a failing Playwright
    assertion's diagnostic, a snapshot, a log tail), and any NUL in there later flows into a
    Postgres JSON write (run.outputs here, and the defect brief / run.inputs the workflow
    derives from this report). One NUL then fails the whole write and parks the run for
    takeover — after the real work (PR, artifacts) already landed. Scrubbing at this single
    ingestion funnel keeps the run recording cleanly. Only NUL is removed; every other byte
    (including the U+FFFD replacement char) is valid in Postgres text and left untouched."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {k: _scrub_nul(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_nul(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_scrub_nul(v) for v in value)
    return value


def _default_signal_sender(workflow_id: str, report: BuildReport) -> None:
    import asyncio

    from django.conf import settings
    from temporalio.client import Client

    async def _send() -> None:
        client = await Client.connect(
            settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE
        )
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal("build_reported", report)

    asyncio.run(_send())


def report_build(*, tenant_id, run_id, report, signal_sender=None) -> dict:
    """Record the companion's report on the run + signal the workflow to resume."""
    from mcp_platform_state import tools

    from apps.runs.models import Run
    from apps.tenancy.context import tenant_context

    signal_sender = signal_sender or _default_signal_sender
    # Scrub NUL before the report touches the DB or the workflow signal — see _scrub_nul.
    if isinstance(report, dict):
        fields = {k: report[k] for k in report if k in BuildReport.__annotations__}
        report = BuildReport(**_scrub_nul(fields))
    else:
        report = BuildReport(**_scrub_nul(asdict(report)))

    with tenant_context(tenant_id):
        run = Run.objects.get(id=run_id, tenant_id=tenant_id)
        run.outputs = {**(run.outputs or {}), "report": asdict(report)}
        run.save(update_fields=["outputs", "updated_at"])
        workflow_id = run.temporal_workflow_id
        tools.log_event(tenant_id, "companion", "build.reported", "run", str(run_id),
                        {"status": report.status, "branch": report.branch})

    if not workflow_id:
        raise BuildReportError("run has no temporal_workflow_id; cannot resume the workflow")
    signal_sender(workflow_id, report)
    return {"run_id": str(run_id), "signaled": True, "status": report.status}
