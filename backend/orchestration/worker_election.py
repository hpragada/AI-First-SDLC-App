"""Who owns the task queue: the newest worker, and only the newest worker.

The rule is decided *before* the worker polls for anything, because a worker
that has already taken a task has already done the damage. Three outcomes:

    VERSIONED    - I am the newest code; I registered my badge as the queue
                   default and I will poll carrying it.
    UNVERSIONED  - the Temporal server has worker versioning switched off. Log
                   it loudly and behave exactly as the platform did before this
                   module existed. Degrading is deliberate: a safety feature
                   that takes every worker offline when a server flag is missing
                   would be worse than the problem it prevents.
    STAND_DOWN   - someone newer already owns this queue. Do not poll at all.

Two measured facts shape this (proved against Temporal 1.25.2, our own server):

  * Registering a default build ID fences out **unversioned** workers too, not
    just older versioned ones. That is what makes this work against a worker
    deployed before this code existed.
  * A version-set change takes a few seconds to reach the matching service.
    During that window an old worker can still receive a task. Nothing here can
    close that window, which is one reason a superseded worker drains rather
    than being assumed idle the instant it is superseded.

Draining is by self-observation, not by asking Temporal. `get_worker_task_
reachability` reported a *non-default* build as still reachable for new
workflows, so a drain loop built on it would never let go.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, NamedTuple

from temporalio.service import RPCError, RPCStatusCode

from .version import is_newer, same_code

VERSIONED = "versioned"
UNVERSIONED = "unversioned"
STAND_DOWN = "stand_down"

# The server answers this way when the two dynamic-config flags are absent.
_VERSIONING_OFF = (RPCStatusCode.PERMISSION_DENIED, RPCStatusCode.UNIMPLEMENTED)


class TrackingExecutor(ThreadPoolExecutor):
    """A thread pool that knows whether the worker is busy.

    Temporal runs each activity on this executor, so counting submissions and
    completions tells us when the worker is genuinely idle. Workflow tasks run
    on the event loop rather than here, so they are not counted — they complete
    in milliseconds, and a drain that waited on them would be waiting on noise.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._lock = threading.Lock()
        self._in_flight = 0
        self._last_idle_at = time.monotonic()

    def submit(self, fn: Callable, /, *args: Any, **kwargs: Any):  # type: ignore[override]
        with self._lock:
            self._in_flight += 1
        future = super().submit(fn, *args, **kwargs)
        future.add_done_callback(self._on_done)
        return future

    def _on_done(self, _future: Any) -> None:
        with self._lock:
            self._in_flight -= 1
            if self._in_flight <= 0:
                self._in_flight = 0
                self._last_idle_at = time.monotonic()

    @property
    def in_flight(self) -> int:
        with self._lock:
            return self._in_flight

    def idle_seconds(self) -> float:
        """How long the worker has had nothing in hand. 0.0 while busy."""
        with self._lock:
            if self._in_flight > 0:
                return 0.0
            return time.monotonic() - self._last_idle_at


async def _current_default(client: Any, task_queue: str) -> str | None:
    """The build ID that currently owns the queue, or None if nobody does.

    A queue nobody has ever claimed comes back with an empty set list, and the
    SDK's `default_build_id()` indexes into it unguarded — so "no owner yet",
    the very first case any new queue hits, arrives as an IndexError rather than
    an empty answer.
    """
    sets = await client.get_worker_build_id_compatibility(task_queue)
    if sets is None or not getattr(sets, "version_sets", True):
        return None
    try:
        default = sets.default_build_id()
    except IndexError:
        return None
    return default or None


class Election(NamedTuple):
    """The verdict, plus the build ID the worker should actually poll under.

    These are two different things whenever a worker joins a build that is
    already serving — see the identical-code case in `elect`.
    """

    outcome: str
    build_id: str


async def elect(
    client: Any, task_queue: str, badge: str, *, log: Callable[[str], None]
) -> Election:
    """Decide whether this worker may serve `task_queue`, before it polls."""
    try:
        current = await _current_default(client, task_queue)
    except RPCError as exc:
        if exc.status in _VERSIONING_OFF:
            log(
                "worker versioning is OFF on this Temporal server "
                f"({exc.status.name}); running UNVERSIONED, which means a stale "
                "worker on this queue can still take work. To turn it on, add "
                "frontend.workerVersioningDataAPIs and "
                "frontend.workerVersioningWorkflowAPIs to the server's dynamic config."
            )
            return Election(UNVERSIONED, badge)
        if exc.status is RPCStatusCode.NOT_FOUND:
            current = None
        else:
            raise

    if current is not None and current == badge:
        log(f"build {badge} already owns queue {task_queue}; serving it")
        return Election(VERSIONED, badge)

    if current is not None and same_code(badge, current):
        # Same code, different clock. Two developers who pulled the same commit
        # at different times date their files differently, and the runbook has
        # them sharing this queue deliberately. Treating that as a newer build
        # would evict a perfectly good worker and quietly halve the team's
        # capacity, so join the build that is already serving instead.
        log(
            f"my code is identical to build {current} already serving "
            f"{task_queue} (only the file dates differ); joining it rather than "
            "replacing it, so both workers keep serving"
        )
        return Election(VERSIONED, current)

    if current is not None and not is_newer(badge, current):
        # Bugs S.No 247: this said what had happened and not what to do about it, so the
        # person reading it saw a container that would not stay up and no way to act. The
        # instruction is the whole point of the message.
        log(
            f"STANDING DOWN: somebody on {task_queue} is running newer code than you "
            f"({current} is newer than {badge}), so this worker will not take any work — "
            "that is deliberate, not a crash. Pull the latest code and restart to serve "
            "again, or set TEMPORAL_TASK_QUEUE in your .env to your own queue name to stop "
            "sharing one. Any task you started on the old code is picked up by the newer "
            "worker; nothing is lost."
        )
        return Election(STAND_DOWN, badge)

    try:
        await _claim(client, task_queue, badge)
    except RPCError as exc:
        if exc.status in _VERSIONING_OFF:
            log(
                f"could not register build {badge} ({exc.status.name}); "
                "running UNVERSIONED"
            )
            return Election(UNVERSIONED, badge)
        raise

    if current is None:
        log(f"queue {task_queue} had no owner; registered build {badge} as default")
    else:
        log(f"build {badge} is newer than {current}; took ownership of {task_queue}")
    return Election(VERSIONED, badge)


async def _claim(client: Any, task_queue: str, badge: str) -> None:
    """Take ownership of the queue with this badge, as a SUCCESSOR of the build already there.

    Bugs S.No 244/245. This used `BuildIdOpAddNewDefault` for every badge, which makes each one
    a new INCOMPATIBLE generation. Temporal pins a running workflow to its starting build for
    life, so a badge that changes on every code edit — while a build runs for hours — meant any
    worker restart permanently orphaned every build in flight, silently. The same growth also
    filled the queue: ten sets is Temporal's cap, and `sdlc-brown` hit it, at which point the
    worker could not start at all.

    `AddNewCompatible` puts the new badge in the SAME set as a successor, and the SDK's own
    words for what that buys are the fix: "new workflow tasks for workflows which have been
    executing on workers in that set will now start on this new Build Id". So a restart hands
    the in-flight builds to the incoming worker instead of stranding them, and the set count
    stops growing.

    `promote_set=True` is not optional: without it the new build serves the old workflows but
    NOT newly started ones, which is half a claim and worse than either whole answer.

    What this trades: a newer worker may now replay a workflow that started on older code. Only
    the workflow files can break that (`workflows.py`, `build_workflow.py` — activities are
    never replayed), it changed 21 times in 203 code changes over two months, and it fails LOUD
    with a named non-determinism error. The alternative was a silent permanent orphan every
    time, which is not a better trade.
    """
    from temporalio.client import BuildIdOpAddNewCompatible, BuildIdOpAddNewDefault

    current = await _current_default(client, task_queue)
    if current is None:
        # Nothing to be a successor OF. A fresh queue's first badge has to open the set —
        # `AddNewCompatible` needs an existing build id and is rejected without one.
        await client.update_worker_build_id_compatibility(
            task_queue, BuildIdOpAddNewDefault(badge)
        )
        return
    await client.update_worker_build_id_compatibility(
        task_queue,
        BuildIdOpAddNewCompatible(
            badge, existing_compatible_build_id=current, promote_set=True
        ),
    )


async def drain_when_superseded(
    client: Any,
    task_queue: str,
    badge: str,
    *,
    executor: TrackingExecutor,
    on_drained: Callable[[], Any],
    log: Callable[[str], None],
    idle_seconds: float,
    max_seconds: float,
    poll_seconds: float,
    sleep: Callable[[float], Any],
    now: Callable[[], float] = time.monotonic,
) -> str:
    """Watch for a newer worker taking over, then leave once the work is done.

    A superseded worker must not exit immediately: workflows already assigned to
    its build keep running on it, and killing it mid-activity would strand
    exactly the kind of run this whole change exists to protect. So it holds on
    until it has been idle for `idle_seconds`, with `max_seconds` as a backstop
    against a worker that never goes quiet.

    Returns why it stopped, so the caller (and the tests) can tell the cases
    apart.
    """
    superseded_at: float | None = None
    while True:
        await sleep(poll_seconds)
        try:
            current = await _current_default(client, task_queue)
        except RPCError as exc:  # transient, or versioning switched off mid-life
            log(f"could not read queue ownership ({exc.status.name}); will retry")
            continue

        if current is None or current == badge:
            if superseded_at is not None:
                log(f"build {badge} owns {task_queue} again; cancelling drain")
                superseded_at = None
            continue

        if superseded_at is None:
            superseded_at = now()
            log(
                f"build {current} has taken over {task_queue}. This worker "
                f"({badge}) will finish what it is holding and then exit."
            )

        idle = executor.idle_seconds()
        if executor.in_flight == 0 and idle >= idle_seconds:
            log(f"drained after {idle:.0f}s idle; shutting down build {badge}")
            await on_drained()
            return "drained"

        if now() - superseded_at >= max_seconds:
            log(
                f"superseded for over {max_seconds:.0f}s with "
                f"{executor.in_flight} still in flight; shutting down anyway"
            )
            await on_drained()
            return "forced"
