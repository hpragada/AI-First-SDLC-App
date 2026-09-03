"""Backfill the document-vision agent (00e) onto every EXISTING tenant (Part B).

Adding a new agent to the catalog only makes it available to tenants created *after* it exists
(the tenant-creation hook calls `seed_agent_specs`). Tenants created earlier need a one-time
backfill — this migration. On `make migrate` it (re)seeds each tenant's AgentSpec rows from the
current catalog, which is idempotent (`update_or_create` per entry) and so only ADDS what's
missing — i.e. `00e_document_vision` — without touching or duplicating the specs already there.

This is DATA, not schema: no table changes, just rows. It runs as the privileged migration role
(the same one that owns the RLS setup), which is a superuser and therefore sees across all tenants
even though every platform table enforces FORCE ROW LEVEL SECURITY; the app role never could.
Together with the tenant-creation hook, this makes the vision agent universal — every existing and
future tenant has it — so it is available to the whole team once this branch merges to develop.
"""
from __future__ import annotations

from django.db import migrations


def seed_document_vision(apps, schema_editor):
    # Real catalog + models on purpose: this is a catalog-seed operation on the current code, run
    # once at deploy time. seed_agent_specs is idempotent and scopes each write with tenant_context.
    from apps.registry.catalog import ACTIVE_AGENT_CATALOG, seed_agent_specs
    from apps.tenancy.models import Tenant

    tenants = list(Tenant.objects.all())
    seeded = 0
    for tenant in tenants:
        try:
            seed_agent_specs(tenant)
            seeded += 1
        except Exception as exc:  # noqa: BLE001 — one bad tenant must not abort the whole backfill
            print(f"  seed_document_vision: tenant {tenant.id} skipped — {exc}")
    print(
        f"  seed_document_vision: (re)seeded {len(ACTIVE_AGENT_CATALOG)} catalog agents for "
        f"{seeded}/{len(tenants)} tenant(s). If this is 0/0, run migrations as the privileged "
        f"role (the app role sees no tenants under FORCE RLS)."
    )


def unseed_noop(apps, schema_editor):
    # Seeding is additive and idempotent; there is nothing safe or meaningful to un-seed (other
    # phases' specs share the same rows). Reverse is a deliberate no-op.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0003_artifact_title"),
        ("tenancy", "0002_rls"),
    ]

    operations = [
        migrations.RunPython(seed_document_vision, unseed_noop),
    ]
