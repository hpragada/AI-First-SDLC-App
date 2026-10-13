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

#: Statuses the "nobody is serving this run" check LOOKS at (S.No 246). Wider than
#: `LIVE_STATUSES` by exactly one: a `stalled` run is parked for a human and must never be
#: repaired from here, but it is also the precise shape TASK-039 wore — parked, orphaned, and
#: indistinguishable from a companion that merely went quiet. Telling somebody is not repairing,
#: so detection may look where repair may not; the loop keeps repair to `LIVE_STATUSES`.
WATCHED_STATUSES = (*LIVE_STATUSES, Run.Status.STALLED)

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
    """What Temporal says about a workflow, reduced to what we act on.

    `build_id` / `versioned` carry the code version the workflow is pinned to (Bugs S.No 246).
    Temporal pins a running workflow to the build that started it for life, and says nothing
    when no worker carries that build any more — so a workflow can be RUNNING, healthy on every
    surface, and served by nobody. Reading the stamp costs nothing here: `describe()` already
    returns it.
    """

    def __init__(
        self, closed: bool, name: str, build_id: str = "", versioned: bool = False
    ) -> None:
        self.closed = closed
        self.name = name
        self.build_id = build_id
        self.versioned = versioned


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
        stamp = described.raw_description.workflow_execution_info.most_recent_worker_version_stamp
        # CONTINUED_AS_NEW is a handover, not an ending: the work carries on under
        # a new execution, so the run is still legitimately live.
        return WorkflowState(
            name not in ("RUNNING", "CONTINUED_AS_NEW"), name,
            build_id=stamp.build_id or "", versioned=bool(stamp.use_versioning),
        )

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


#: Where "nobody is serving this run" is recorded on a Run. `Run.outputs` is already a JSON field
#: the API returns whole, so the UI reads this for free and no migration is needed (ADR 0003 is
#: not even in play). Written only while the condition holds and REMOVED as soon as it stops, so
#: the notice the UI draws from it closes itself.
STALL_KEY = "worker_stalled"

_UNASKED = object()


def _queue_versions(queue: str) -> tuple[frozenset[str], int] | None:
    """Every code version a worker on `queue` would answer for, plus how many version sets it
    holds. `None` means "could not tell".

    Asked once per pass, never per run. `None` must not be read as "nothing is served": that
    would mark every run in the project the first time Temporal is briefly unreachable, which is
    the same mistake as reading a 500 from Jira as "the issue was deleted" (S.No 236).

    The set count rides along because it is free here and it is the number that filled up
    silently on 2026-09-08 (S.No 245). It goes into the ledger event rather than onto a screen:
    once badges chain as compatible successors the count stops growing, so there is nothing for a
    person to watch — but there is something for an engineer to find afterwards.
    """
    import asyncio

    from django.conf import settings
    from temporalio.client import Client

    async def _ask() -> tuple[frozenset[str], int]:
        client = await Client.connect(
            settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE
        )
        sets = await client.get_worker_build_id_compatibility(queue)
        version_sets = list(getattr(sets, "version_sets", None) or [])
        return (
            frozenset(b for vs in version_sets for b in vs.build_ids),
            len(version_sets),
        )

    try:
        return asyncio.run(_ask())
    except Exception:  # noqa: BLE001 — unreachable, or versioning off: say nothing about anything
        return None


def _can_tell(versions: tuple[frozenset[str], int] | None) -> bool:
    """Whether we actually learned which code versions are being served.

    Found in a browser, not by a test, and it is the more dangerous half of "could not tell is
    never gone". The absence of an answer is easy to remember on the way IN — do not mark a run
    you know nothing about. It is easy to forget on the way OUT: `_stall_note` returns None both
    for "this run is fine" and for "I have no idea", and `_remember_stall` reads None as "take
    the note off". So one unreachable moment, or a queue with no versions registered at all,
    silently erased a real warning about a genuinely dead task.

    Nothing is written in either direction unless this is true.
    """
    return versions is not None and bool(versions[0])


def _stall_note(state: WorkflowState, versions: tuple[frozenset[str], int]) -> dict | None:
    """What to record about a RUNNING workflow nobody serves — or None when it is fine.

    Only called once `_can_tell` says the answer is real. An unversioned workflow belongs to no
    version set, so its stamp is a plain code fingerprint and means nothing here — that counts
    as fine, because it is not pinned to anything that could go out of service.
    """
    served, set_count = versions
    if not state.versioned or not state.build_id:
        return None
    if state.build_id in served:
        return None
    # Badges sort chronologically by construction (`<stamp>-<fingerprint>`), so the last one is
    # the newest code anybody is running — the version a person would be told to move to.
    return {
        "pinned_build": state.build_id,
        "newest_served": sorted(served)[-1],
        "version_sets": set_count,
        "noticed_at": timezone.now().isoformat(),
    }


def _remember_stall(tenant_id: str, run: Run, note: dict | None) -> str | None:
    """Put the note on the run, or take it off. Returns what changed, or None if nothing did.

    Writing only on a CHANGE is what makes this quiet: the pass runs on a page load, and a run
    that is still stuck must not produce a fresh ledger event every time somebody looks.

    Written with a queryset `update()` rather than `save()`, and that is not a style choice:
    `updated_at` is `auto_now`, and a `save()` moves it even when it is left out of
    `update_fields` — measured, not assumed. Two things break if observing a run bumps its
    clock. The run drops out of this pass's own `updated_at < cutoff` window, so the note would
    still be on screen a quarter of an hour after the problem was fixed — and the team's rule is
    that a notice closes itself. And `updated_at` is what other machinery reads to decide whether
    a run has gone quiet, which a detector must never be able to influence.
    """
    outputs = dict(run.outputs or {})
    had = outputs.get(STALL_KEY)
    if note is None:
        if not had:
            return None
        outputs.pop(STALL_KEY, None)
        Run.objects.filter(pk=run.pk).update(outputs=outputs)
        run.outputs = outputs
        tools.log_event(
            tenant_id, "reconciler", "run.worker_recovered", "run", str(run.id),
            {"was_pinned_to": had.get("pinned_build", "")},
        )
        return "recovered"
    if had and had.get("pinned_build") == note["pinned_build"]:
        return None                      # same stall, already recorded — stay silent
    outputs[STALL_KEY] = note
    Run.objects.filter(pk=run.pk).update(outputs=outputs)
    run.outputs = outputs
    tools.log_event(
        tenant_id, "reconciler", "run.worker_stalled", "run", str(run.id),
        {"pinned_build": note["pinned_build"], "newest_served": note["newest_served"],
         "version_sets": note["version_sets"], "status": run.status},
    )
    return "stalled"


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
    out: dict = {"checked": 0, "repaired": [], "undetermined": 0, "stalled": [], "recovered": []}
    # Asked at most once per pass, and only if a running workflow actually turns up.
    versions: Any = _UNASKED

    try:
        with tenant_context(tenant_id):
            candidates = list(
                Run.objects.filter(
                    tenant_id=tenant_id,
                    status__in=WATCHED_STATUSES,
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
                    # A running workflow is normally the healthy case and there is nothing to
                    # do — UNLESS nobody is serving the code version it is pinned to, which is
                    # the failure that looked healthy on every surface for 46 days (S.No 246).
                    #
                    # Annotate, never repair. Whether to take the task over, merge the versions
                    # or re-trigger is a person's call with different consequences each way, and
                    # this module's own rule is that a wrong repair is worse than a late one.
                    if versions is _UNASKED:
                        from django.conf import settings
                        versions = _queue_versions(settings.TEMPORAL_TASK_QUEUE)
                    if not _can_tell(versions):
                        out["undetermined"] += 1
                        continue
                    changed = _remember_stall(tenant_id, run, _stall_note(state, versions))
                    if changed:
                        out[changed].append(str(run.id))
                    continue
                if run.status not in LIVE_STATUSES:
                    # Only `stalled` reaches here, and repairing it would undo S.No 89's whole
                    # point: a companion that merely slept can still come back and reconcile
                    # itself. It was watched for the stall check above; that is all.
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
