"""Temporal worker entrypoint: registers AgentRunWorkflow + activities on the task queue.

Run as: `python -m orchestration.worker` (from backend/, with Django configured).
"""
import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _bootstrap_django() -> None:
    # mcp_platform_state lives at the repo root (sibling of backend/).
    repo_root = str(Path(__file__).resolve().parents[2])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


async def _run() -> None:
    from django.conf import settings
    from temporalio.client import Client
    from temporalio.worker import Worker

    from . import activities
    from .build_activities import BUILD_ACTIVITIES, set_review_provider
    from .build_workflow import BuildWorkflow
    from .review_provider import build_companion_provider
    from .workflows import AgentRunWorkflow

    # Wire the migrated Code Review agent (08) into the 07<->08 remediation loop (§6), run on
    # the user's enrolled companion (local Claude Code — req #1). Tests script the reviewer via
    # set_review_provider; the default stub stands in only when nothing is registered.
    set_review_provider(build_companion_provider())

    client = await Client.connect(settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE)
    with ThreadPoolExecutor(max_workers=8) as executor:
        worker = Worker(
            client,
            task_queue=settings.TEMPORAL_TASK_QUEUE,
            workflows=[AgentRunWorkflow, BuildWorkflow],
            activities=activities.ALL_ACTIVITIES + BUILD_ACTIVITIES,
            activity_executor=executor,
        )
        await worker.run()


def main() -> None:
    _bootstrap_django()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
