"""`python manage.py seed_agents --tenant <id>` — (re)seed a tenant's AgentSpec rows from the
catalog.

Seeding = inserting the catalog's agent rows for a tenant; it is NOT a schema migration (it
changes DATA, not table structure). Run this for an existing tenant whenever a NEW agent is added
to the catalog — e.g. `00e_document_vision` (Part B) — so a tenant created before that agent
existed gets the new row. It is idempotent (`update_or_create` per catalog entry), so re-running
it never duplicates or disturbs the specs already there; it only fills in what's missing.

Because the platform enforces Postgres row-level security (the app role sees a tenant's rows only
inside that tenant's context), you pass the tenant id explicitly — the one you paste into the UI's
`X-Tenant-ID` field. The command sets that tenant's context, then seeds within it.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.registry.catalog import ACTIVE_AGENT_CATALOG, seed_agent_specs
from apps.registry.models import AgentSpec
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant


class Command(BaseCommand):
    help = "(Re)seed a tenant's AgentSpec rows from the catalog (idempotent). --tenant <id>."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--tenant", required=True, metavar="TENANT_ID",
            help="The tenant id to seed (the value you paste into the UI's X-Tenant-ID field).",
        )

    def handle(self, *args, **options) -> None:
        tid = str(options["tenant"]).strip()
        with tenant_context(tid):
            try:
                tenant = Tenant.objects.get(id=tid)
            except (Tenant.DoesNotExist, ValidationError, ValueError) as exc:
                raise CommandError(
                    f"no tenant '{tid}' visible in its own context — check the id is the full "
                    f"tenant UUID from the UI's X-Tenant-ID field. ({type(exc).__name__})"
                ) from exc

            before = set(
                AgentSpec.objects.filter(tenant=tenant).values_list("key", flat=True)
            )
            seed_agent_specs(tenant)
            after = set(
                AgentSpec.objects.filter(tenant=tenant).values_list("key", flat=True)
            )

        added = sorted(after - before)
        added_line = ", ".join(added) if added else "(none — already up to date)"
        self.stdout.write(
            self.style.SUCCESS(f"Seeded agent specs for tenant {tenant.name} ({tid}):"))
        self.stdout.write(f"  catalog agents : {len(ACTIVE_AGENT_CATALOG)}")
        self.stdout.write(f"  specs now      : {len(after)}")
        self.stdout.write(f"  newly added    : {added_line}")
        if "00e_document_vision" in after:
            self.stdout.write(self.style.SUCCESS("  document vision (00e): present"))
        else:
            self.stdout.write(self.style.WARNING(
                "  document vision (00e): NOT present — is the catalog updated?"))
