"""Temporal worker entrypoint: registers AgentRunWorkflow + activities on the task queue.

Run as: `python -m orchestration.worker` (from backend/, with Django configured).

Before it polls for anything, the worker stamps itself with a badge for the code
it is actually running and asks whether a newer worker already owns the queue —
see `worker_election`. A worker running older code stands down instead of
quietly serving work with stale behaviour. Deploying is therefore just "start
the new worker": the old one finishes what it holds and exits on its own.
"""
import asyncio
import os
import sys
from pathlib import Path


def _bootstrap_django() -> None:
    # mcp_platform_state lives at the repo root (sibling of backend/).
    repo_root = str(Path(__file__).resolve().parents[2])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


#: Exit status for "somebody newer owns this queue, so I served nothing" (Bugs S.No 247).
#: Deliberately not 0 (nothing was done) and not 1 (nothing failed) — this is a third outcome,
#: and an operator needs to be able to see which one they got.
_STAND_DOWN_EXIT = 3


def _log(message: str) -> None:
    """Worker lifecycle goes to stdout, where the container logs already are."""
    print(f"[worker] {message}", flush=True)


async def _run() -> None:
    from django.conf import settings
    from temporalio.client import Client
    from temporalio.worker import Worker

    from . import activities, worker_election
    from .build_activities import BUILD_ACTIVITIES, set_review_provider
    from .build_workflow import BuildWorkflow
    from .review_provider import build_companion_provider
    from .version import build_badge
    from .workflows import AgentRunWorkflow

    # Wire the migrated Code Review agent (08) into the 07<->08 remediation loop (§6), run on
    # the user's enrolled companion (local Claude Code — req #1). Tests script the reviewer via
    # set_review_provider; the default stub stands in only when nothing is registered.
    set_review_provider(build_companion_provider())

    client = await Client.connect(settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE)
    task_queue = settings.TEMPORAL_TASK_QUEUE

    badge, badge_source = build_badge()
    outcome, serving_as = worker_election.UNVERSIONED, badge
    if settings.WORKER_VERSIONING_ENABLED:
        _log(f"build badge {badge} (from {badge_source})")
        outcome, serving_as = await worker_election.elect(
            client, task_queue, badge, log=_log
        )
        if outcome == worker_election.STAND_DOWN:
            # Bugs S.No 247. This was a bare `return`, so a fenced-out worker exited 0 and the
            # container looked like it had finished normally — while the person watching saw
            # only "my worker will not stay up", restarted it, and got the same three-second
            # exit again. A distinct status code lets `docker compose ps` tell "running older
            # code" apart from "crashed", and `elect` has already printed what to do about it.
            raise SystemExit(_STAND_DOWN_EXIT)
    else:
        _log("WORKER_VERSIONING_ENABLED is off; running unversioned")

    # Not always our own badge: a worker whose code is identical to the build
    # already serving joins that build rather than replacing it.
    badge = serving_as
    versioned = outcome == worker_election.VERSIONED
    with worker_election.TrackingExecutor(max_workers=8) as executor:
        worker = Worker(
            client,
            task_queue=task_queue,
            workflows=[AgentRunWorkflow, BuildWorkflow],
            activities=activities.ALL_ACTIVITIES + BUILD_ACTIVITIES,
            activity_executor=executor,
            **({"build_id": badge, "use_worker_versioning": True} if versioned else {}),
        )
        if not versioned:
            await worker.run()
            return

        # Serve work and watch for a successor at the same time. Whichever
        # finishes first ends the process: the worker stopping on its own (a
        # signal, a crash), or the drain deciding a newer build has taken over.
        serving = asyncio.ensure_future(worker.run())
        draining = asyncio.ensure_future(
            worker_election.drain_when_superseded(
                client,
                task_queue,
                badge,
                executor=executor,
                on_drained=worker.shutdown,
                log=_log,
                idle_seconds=settings.WORKER_DRAIN_IDLE_SECONDS,
                max_seconds=settings.WORKER_DRAIN_MAX_SECONDS,
                poll_seconds=settings.WORKER_DRAIN_POLL_SECONDS,
                sleep=asyncio.sleep,
            )
        )
        try:
            await serving
        finally:
            draining.cancel()


def main() -> None:
    _bootstrap_django()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
