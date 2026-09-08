"""Collapse a task queue's accumulated worker version sets into one — Bugs S.No 245.

WHY THIS EXISTS. `worker_election._claim` registers every worker badge with
`BuildIdOpAddNewDefault`, which makes each badge a NEW INCOMPATIBLE version set rather than a
successor. The badge changes on every code change, so a queue gains one set per code change and
never loses one — build ids cannot be removed. Temporal caps a queue at ten sets
(`limit.versionCompatibleSetLimitPerQueue`), and `sdlc-brown` reached it on 2026-09-08: the
eleventh registration is refused with FAILED_PRECONDITION, which `elect()` does not catch, so the
worker dies at startup and the whole stack is down.

Merging every set into the one that currently owns the queue does two things at once: it frees the
ceiling, and — because a workflow is served by the DEFAULT of the set it belongs to — it can bring
workflows stranded on retired builds back to life instead of them having to be terminated
(Bugs S.No 244).

THE ONE THING THAT MAKES THIS UNSAFE. Merging declares the builds mutually compatible, so a
workflow started on an old build will be REPLAYED by a worker running today's code. Replay is
only sensitive to the WORKFLOW files — `orchestration/workflows.py` and
`orchestration/build_workflow.py`.
Activity, agent, API and frontend changes are never replayed. So before confirming a merge,
somebody must answer one question for each versioned running workflow: *has its workflow file
changed since the build it is pinned to?* If it has, replay can raise a non-determinism error and
terminate-and-re-trigger is the better recovery. The command prints exactly what it would touch so
that question can be answered; it deliberately cannot answer it itself, because it has no way to
know which commit a build id was cut from.

MERGING CANNOT BE UNDONE. There is no split operation. Hence: this prints its plan and changes
nothing unless `--confirm` is passed, and it refuses to run without an explicit `--queue`.

  # look, change nothing
  docker compose --profile app run --rm --no-deps backend \
    python manage.py merge_worker_versions --queue sdlc-brown

  # do it
  docker compose --profile app run --rm --no-deps backend \
    python manage.py merge_worker_versions --queue sdlc-brown --confirm
"""
import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

#: The only files whose changes can break a replay. Printed as guidance, not checked — see the
#: module docstring for why the command cannot answer the question itself.
REPLAY_SENSITIVE = (
    "backend/orchestration/workflows.py",
    "backend/orchestration/build_workflow.py",
)


class Command(BaseCommand):
    help = "Merge a task queue's worker version sets into one (Bugs S.No 245). Irreversible."

    def add_arguments(self, parser):
        parser.add_argument(
            "--queue", required=True,
            help="Exact task queue name. Required, with no default: this writes to the SHARED "
                 "Temporal server and must never act on a queue nobody named.",
        )
        parser.add_argument(
            "--confirm", action="store_true",
            help="Actually merge. Without this the command prints its plan and exits.",
        )

    def handle(self, *args, **opts):
        queue = opts["queue"].strip()
        if not queue:
            raise CommandError("--queue cannot be blank.")
        asyncio.run(self._run(queue, confirm=opts["confirm"]))

    async def _run(self, queue: str, *, confirm: bool) -> None:
        from temporalio.client import BuildIdOpMergeSets, Client

        client = await Client.connect(
            settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE
        )
        self.stdout.write(
            f"server   {settings.TEMPORAL_HOST}  namespace {settings.TEMPORAL_NAMESPACE}"
        )
        self.stdout.write(f"queue    {queue}")

        sets = await client.get_worker_build_id_compatibility(queue)
        version_sets = list(getattr(sets, "version_sets", []) or [])
        if not version_sets:
            raise CommandError(
                f"queue '{queue}' has no worker version sets — nothing to merge. Check the name."
            )
        try:
            default = sets.default_build_id()
        except IndexError:  # a queue whose last set is empty; the SDK indexes unguarded
            raise CommandError(f"queue '{queue}' has sets but no default build id.") from None

        self.stdout.write(f"\n{len(version_sets)} version set(s), default build {default}")
        for i, vs in enumerate(version_sets, 1):
            ids = list(vs.build_ids)
            owns = "  <- owns the queue" if default in ids else ""
            self.stdout.write(f"  set {i}: {', '.join(ids)}{owns}")

        if len(version_sets) == 1:
            self.stdout.write(self.style.SUCCESS("\nAlready one set. Nothing to do."))
            return

        # What a merge would touch: every RUNNING workflow on this queue that carries a build
        # stamp. An unversioned workflow sits in no set, so a merge cannot reach it.
        self.stdout.write("\nrunning workflows on this queue:")
        touched = 0
        async for wf in client.list_workflows(
            f'ExecutionStatus = "Running" AND TaskQueue = "{queue}"'
        ):
            info = (await client.get_workflow_handle(wf.id).describe()).raw_description
            stamp = info.workflow_execution_info.most_recent_worker_version_stamp
            if not stamp.use_versioning:
                self.stdout.write(f"  unversioned, not affected   {wf.workflow_type:18} {wf.id}")
                continue
            touched += 1
            state = "already on the default" if stamp.build_id == default else "WOULD BE REPLAYED"
            self.stdout.write(
                f"  {state:22} {wf.workflow_type:18} {wf.id}\n"
                f"      pinned to {stamp.build_id}, started {wf.start_time:%Y-%m-%d %H:%M} UTC"
            )
        if touched == 0:
            self.stdout.write("  (none versioned — this merge cannot disturb running work)")
        else:
            self.stdout.write(
                "\n  Before confirming, check whether these files changed between the build each\n"
                "  workflow is pinned to and today's build:\n"
                + "".join(f"    {p}\n" for p in REPLAY_SENSITIVE)
                + "  If they did, replay can fail and terminate-and-re-trigger is the safer route."
            )

        # Merge every other set INTO the set that owns the queue. MergeSets keeps the primary
        # set's default as the merged default, so the live build stays in charge throughout.
        others = [vs for vs in version_sets if default not in list(vs.build_ids)]
        self.stdout.write(f"\nplan: {len(others)} merge(s) into the set owning {default}")
        for vs in others:
            self.stdout.write(f"  merge set [{', '.join(vs.build_ids)}] -> {default}")

        if not confirm:
            self.stdout.write(self.style.WARNING(
                "\nNothing changed. Re-run with --confirm to apply. THIS CANNOT BE UNDONE."
            ))
            return

        for vs in others:
            secondary = list(vs.build_ids)[0]
            await client.update_worker_build_id_compatibility(
                queue,
                BuildIdOpMergeSets(primary_build_id=default, secondary_build_id=secondary),
            )
            self.stdout.write(f"  merged {secondary} -> {default}")

        after = await client.get_worker_build_id_compatibility(queue)
        remaining = len(list(getattr(after, "version_sets", []) or []))
        self.stdout.write(self.style.SUCCESS(
            f"\ndone: {queue} now has {remaining} version set(s), "
            f"default {after.default_build_id()}"
        ))
