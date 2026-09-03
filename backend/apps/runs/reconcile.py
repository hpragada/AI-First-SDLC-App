"""The second line: notice when the platform's story and Temporal's disagree.

Part A stops an old worker taking work in the first place. This is what catches
the case where something went wrong anyway — because a detector only ever finds
the failures somebody thought of, and prevention is the half that does not need
to have predicted the fault.

The invariant, in plain terms: **a run the platform still shows as live, whose
workflow has already ended, is lying.** Both halves of that are already in the
database (`Run.status`, `Run.temporal_workflow_id`); nothing compared them.

Two deliberate design choices, both forced by things we measured:

**It runs when somebody looks, not on a timer.** The obvious build is a
background sweep, and it is not available to us: the app's database role is
subject to row-level security and cannot enumerate tenants at all (a count of
`tenancy_tenant` with no tenant context returns 0, by design). A sweeper would
need an elevated role — a security decision that should be taken deliberately,
not smuggled in as a side effect of a bug fix. So the check runs inside a path
that is already scoped to one tenant. In practice that is the moment it matters:
somebody is looking at something that appears stuck.

**Capabilities bring their own invariants.** The generic run check would NOT have
caught the incident that prompted all this: that run's status was `completed` and
its workflow had closed — entirely consistent. What was stranded was the audit
underneath it. Rather than bolt accessibility special-cases into this module,
each capability registers its own "is anything of mine stranded?" check, so the
next thing built registers its own instead of rediscovering this the hard way.

Nothing here repairs on a guess. If Temporal cannot be reached, or answers
something unexpected, the run is left exactly as it is: a wrong repair is worse
than a late one.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.utils import timezone
from mcp_platform_state import tools

from apps.runs.models import Run
from apps.tenancy.context import tenant_context

#: Statuses that claim the run is still going.
#:
#: STALLED is deliberately absent. It means "the companion went quiet, parked for
#: a human" — non-terminal ON PURPOSE (S.No 89), because a companion that merely
#: slept can still come back and reconcile itself through the normal path.
#: Repairing those here would take that away and fight a design decision already
#: made.
LIVE_STATUSES = (
    Run.Status.PENDING,
    Run.Status.RUNNING,
    Run.Status.AWAITING_GATE,
    Run.Status.APPROVED,
)

#: Leave a run alone until it has been untouched this long. A run is written to
#: several times as it starts, and its workflow is not instantly visible to a
#: describe() — without this the reconciler would race normal startup and
#: "repair" runs that are perfectly healthy.
DEFAULT_MIN_AGE_SECONDS = 900

#: Never examine more than this many in one pass. This runs on a page load.
DEFAULT_MAX_PER_PASS = 5

#: Capability-owned checks, resolved lazily so this module stays importable
#: anywhere. Each is `find_stranded(tenant_id, cutoff) -> list[Stranded]`.
_CAPABILITY_CHECKS = ("apps.a11y.reconcile.find_stranded",)


@dataclass
class Stranded:
    """Something left in a state its own machinery can no longer move it out of."""

    kind: str
    target_id: str
    detail: str
    repair: Callable[[], Any]


class WorkflowState:
    """What Temporal says about a workflow, reduced to what we act on."""

    def __init__(self, closed: bool, name: str) -> None:
        self.closed = closed
        self.name = name


def _describe_workflow(workflow_id: str) -> WorkflowState | None:
    """Ask Temporal about one workflow. None means "could not tell" — never repair on that."""
    import asyncio

    from django.conf import settings
    from temporalio.client import Client
    from temporalio.service import RPCError, RPCStatusCode

    async def _ask() -> WorkflowState | None:
        client = await Client.connect(
            settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE
        )
        handle = client.get_workflow_handle(workflow_id)
        try:
            described = await handle.describe()
        except RPCError as exc:
            if exc.status is RPCStatusCode.NOT_FOUND:
                # Retention expired, or it was never started. Either way nothing
                # is going to move this run along.
                return WorkflowState(True, "NOT_FOUND")
            raise
        status = described.status
        name = getattr(status, "name", str(status))
        # CONTINUED_AS_NEW is a handover, not an ending: the work carries on under
        # a new execution, so the run is still legitimately live.
        return WorkflowState(name not in ("RUNNING", "CONTINUED_AS_NEW"), name)

    try:
        return asyncio.run(_ask())
    except Exception:  # noqa: BLE001 — unreachable/unexpected: report nothing, repair nothing
        return None


def _reason_for(state: WorkflowState) -> str:
    if state.name == "NOT_FOUND":
        return (
            "The workflow behind this phase no longer exists on the server, so nothing "
            "was ever going to finish it. Re-trigger the phase to run it again."
        )
    return (
        f"The workflow behind this phase ended ({state.name}) without closing this run "
        "out, so the run was left showing as still going. Re-trigger the phase to run it again."
    )


def _repair_run(run: Run, state: WorkflowState) -> None:
    """Close the run out through the SAME path a reported failure uses.

    Reusing `fail_run_core` rather than writing a second closing routine is the
    point: it also runs the journey and judging close-outs, so a stranded run
    lands in exactly the state a normally-failed run reaches, and there is one
    place to change when that state changes.
    """
    from orchestration.activities import fail_run_core
    from orchestration.types import AgentRunInput

    inp = AgentRunInput(
        run_id=str(run.id),
        tenant_id=str(run.tenant_id),
        project_id=str(run.work_item.project_id),
        work_item_id=str(run.work_item_id),
        agent_spec_id=str(run.agent_spec_id or ""),
        phase="",
    )
    fail_run_core(inp, _reason_for(state))


def _capability_checks() -> list[Callable[[str, Any], list[Stranded]]]:
    from importlib import import_module

    found = []
    for path in _CAPABILITY_CHECKS:
        module_path, _, attr = path.rpartition(".")
        try:
            found.append(getattr(import_module(module_path), attr))
        except (ImportError, AttributeError):
            # A capability that is not installed simply has nothing stranded.
            continue
    return found


def reconcile_tenant(
    *,
    tenant_id: str,
    project_id: str | None = None,
    describe: Callable[[str], WorkflowState | None] | None = None,
    min_age_seconds: int = DEFAULT_MIN_AGE_SECONDS,
    limit: int = DEFAULT_MAX_PER_PASS,
) -> dict:
    """Find and repair anything this tenant has left stranded. Never raises.

    Called from a read path, so a fault in here must never be able to take down
    the page it is riding on — a safety net that breaks the thing it is under is
    not a safety net.
    """
    describe = describe or _describe_workflow
    cutoff = timezone.now() - timedelta(seconds=min_age_seconds)
    out: dict = {"checked": 0, "repaired": [], "undetermined": 0}

    try:
        with tenant_context(tenant_id):
            candidates = list(
                Run.objects.filter(
                    tenant_id=tenant_id,
                    status__in=LIVE_STATUSES,
                    updated_at__lt=cutoff,
                )
                .exclude(temporal_workflow_id="")
                .order_by("updated_at")[:limit]
            )
            if project_id:
                candidates = [
                    r for r in candidates if str(r.work_item.project_id) == str(project_id)
                ]

            for run in candidates:
                out["checked"] += 1
                state = describe(run.temporal_workflow_id)
                if state is None:
                    out["undetermined"] += 1
                    continue
                if not state.closed:
                    continue
                _repair_run(run, state)
                out["repaired"].append({"kind": "run", "id": str(run.id), "why": state.name})
                tools.log_event(
                    tenant_id, "reconciler", "run.reconciled", "run", str(run.id),
                    {"workflow_status": state.name, "was": run.status},
                )

            for check in _capability_checks():
                for item in check(tenant_id, cutoff):
                    out["checked"] += 1
                    item.repair()
                    out["repaired"].append(
                        {"kind": item.kind, "id": item.target_id, "why": item.detail}
                    )
                    tools.log_event(
                        tenant_id, "reconciler", "run.reconciled", item.kind, item.target_id,
                        {"detail": item.detail},
                    )
    except Exception as exc:  # noqa: BLE001 — see the docstring
        out["error"] = str(exc)[:300]
    return out
