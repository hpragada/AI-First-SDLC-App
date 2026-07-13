"""E1 (Hybrid Option C test enabler) — clone a project's UPSTREAM artifacts (everything up to
and including UX Design) + their object-store bodies from one tenant/project into another.

Why: to test the multi-repo Task Breakdown flow, the new multi-repo tenant needs the prior
phases' outputs present so UX/Task-Breakdown have their inputs — WITHOUT re-running them. This
copies the registry pointers (new UUIDs), copies each body to a fresh object-store key, and
re-links the trace edges. It is **write-only to the target** — the source tenant is only read,
never modified — so a mistake can't corrupt real work.

Downstream outputs (Task Breakdown's backlog/sprint plan, and any build artifacts) are
deliberately EXCLUDED, so Task Breakdown runs fresh in the target and assigns repos there.

Run as the MIGRATION role (bypasses RLS for the cross-tenant write), like `migrate`:
  docker compose --profile app run --rm --no-deps \
    -e DATABASE_URL=postgres://sdlc_migrator:...@host:5432/sdlc_platform \
    backend python manage.py clone_upstream \
      --from-tenant <A> --from-project <PA> --to-tenant <B> --to-project <PB> [--dry-run]
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.projects.models import Project
from apps.registry.models import Artifact, TraceEdge
from apps.tenancy.context import tenant_context

# Task-Breakdown-and-later outputs — never cloned (the target regenerates these).
DOWNSTREAM_TYPES = {
    "backlog", "sprint_plan", "definition_of_done", "dependency_map",
    "code", "code_review", "test_plan", "test_case", "test_run",
}
DOWNSTREAM_PHASES = {
    "task_breakdown", "06_task_breakdown", "implementation", "07_implementation",
    "testing", "test_automation", "09_testing", "09b_test_automation",
    "cicd", "11_cicd", "security", "10_security",
}


def _is_upstream(a: Artifact) -> bool:
    return a.type not in DOWNSTREAM_TYPES and a.phase not in DOWNSTREAM_PHASES


def _new_body_key(to_tenant_id, to_project_id, src_id, s3_key: str) -> str:
    base = (s3_key or "body").rstrip("/").split("/")[-1] or "body"
    # keyed by the SOURCE artifact id → unique + traceable; run/phase-agnostic (imported).
    return f"imported/{to_tenant_id}/{to_project_id}/{src_id}/{base}"


def clone_upstream_core(*, from_tenant_id, from_project_id, to_tenant_id, to_project_id,
                        store, dry_run=False) -> dict:
    """Clone upstream artifacts + bodies + trace edges from source → target. Read-only on the
    source; all writes land in the target tenant. Cross-tenant, so the DB session's RLS scope
    (`app.tenant_id`) is switched to the SOURCE for the reads and the TARGET for the writes —
    that's why materialized rows (not lazy querysets) cross the boundary. Returns a report."""
    # ── read the source (RLS scoped to the source tenant) ──
    with tenant_context(from_tenant_id):
        if not Project.objects.filter(id=from_project_id, tenant_id=from_tenant_id).exists():
            raise CommandError("source project not found for that tenant")
        source = list(Artifact.objects.filter(tenant_id=from_tenant_id, project_id=from_project_id))
        upstream = [a for a in source if _is_upstream(a)]
        up_ids = {a.id for a in upstream}
        rows = [{
            "src_id": a.id, "phase": a.phase, "type": a.type, "status": a.status,
            "sor": a.sor, "external_ref": a.external_ref, "s3_key": a.s3_key,
            "content_hash": a.content_hash, "version": a.version,
        } for a in upstream]
        edges = list(TraceEdge.objects.filter(
            tenant_id=from_tenant_id, from_artifact_id__in=up_ids, to_artifact_id__in=up_ids
        ).values_list("from_artifact_id", "to_artifact_id", "rel"))
        candidates = len(source)

    report = {
        "candidates": candidates,
        "to_copy": len(rows),
        "skipped_downstream": candidates - len(rows),
        "artifacts_copied": 0,
        "bodies_copied": 0,
        "body_copy_failures": 0,
        "edges_copied": 0,
        "dry_run": dry_run,
    }

    # ── write the target (RLS scoped to the target tenant) ──
    with tenant_context(to_tenant_id):
        if not Project.objects.filter(id=to_project_id, tenant_id=to_tenant_id).exists():
            raise CommandError("target project not found for that tenant (create it first)")
        if dry_run:
            return report
        with transaction.atomic():
            id_map: dict = {}
            for r in rows:
                new_key = (_new_body_key(to_tenant_id, to_project_id, r["src_id"], r["s3_key"])
                           if r["s3_key"] else "")
                new = Artifact.objects.create(
                    tenant_id=to_tenant_id, project_id=to_project_id, repo=None, run=None,
                    phase=r["phase"], type=r["type"], status=r["status"], sor=r["sor"],
                    external_ref=r["external_ref"], s3_key=new_key,
                    content_hash=r["content_hash"], version=r["version"],
                )
                id_map[r["src_id"]] = new
                report["artifacts_copied"] += 1
                if r["s3_key"] and new_key:
                    try:
                        store.copy(r["s3_key"], new_key)
                        report["bodies_copied"] += 1
                    except Exception:  # body missing/unreadable — keep the pointer, flag it
                        report["body_copy_failures"] += 1
            for from_id, to_id, rel in edges:
                if from_id in id_map and to_id in id_map:
                    TraceEdge.objects.create(
                        tenant_id=to_tenant_id, from_artifact=id_map[from_id],
                        to_artifact=id_map[to_id], rel=rel)
                    report["edges_copied"] += 1
    return report


class Command(BaseCommand):
    help = ("Clone upstream (through UX Design) artifacts + bodies from one tenant/project to "
            "another (multi-repo test enabler). Write-only to the target; run as the migration role.")

    def add_arguments(self, parser):
        parser.add_argument("--from-tenant", required=True)
        parser.add_argument("--from-project", required=True)
        parser.add_argument("--to-tenant", required=True)
        parser.add_argument("--to-project", required=True)
        parser.add_argument("--dry-run", action="store_true",
                            help="report what would be copied without writing")

    def handle(self, *args, **o):
        from storage import s3_from_settings

        report = clone_upstream_core(
            from_tenant_id=o["from_tenant"], from_project_id=o["from_project"],
            to_tenant_id=o["to_tenant"], to_project_id=o["to_project"],
            store=s3_from_settings(), dry_run=o["dry_run"],
        )
        verb = "Would copy" if report["dry_run"] else "Copied"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {report['to_copy']} upstream artifact(s), "
            f"{report['bodies_copied']} body/bodies, {report['edges_copied']} edge(s); "
            f"skipped {report['skipped_downstream']} downstream. {report}"))
