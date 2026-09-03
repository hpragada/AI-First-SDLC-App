"""Backfill the accessibility journey agent (09d) onto every EXISTING tenant (QA-20).

Identical in shape and reasoning to `0006_seed_a11y_judge`, one phase later. Adding an agent to
the catalog only reaches tenants created *after* it exists (the tenant-creation hook calls
`seed_agent_specs`), so tenants created earlier need this one-time backfill. It re-seeds each
tenant's AgentSpec rows from the current catalog, which is idempotent per entry, so it only ADDS
what is missing — `09d_a11y_journey` — without touching or duplicating the specs already there.

**Why it matters as much as 09c's did.** `journey.journey_available` reports the check as
unavailable while no `09d_a11y_journey` spec exists for the workspace, and QA-20's whole design
is that an unavailable check is *reported* rather than skipped. Without this backfill, keyboard
testing would work on new workspaces and be permanently "not available" on every current one —
including the shared development database — which is a silence, not a failure, and therefore the
kind that goes unnoticed.

This is DATA, not schema. It runs as the privileged migration role, which sees across tenants
despite FORCE ROW LEVEL SECURITY; the app role never could.
"""
from __future__ import annotations

from django.db import migrations


def seed_a11y_journey(apps, schema_editor):
    # Real catalog + models on purpose: a catalog-seed operation on the current code, run once
    # at deploy. `seed_agent_specs` is idempotent and scopes each write with tenant_context.
    from apps.registry.catalog import ACTIVE_AGENT_CATALOG, seed_agent_specs
    from apps.tenancy.models import Tenant

    tenants = list(Tenant.objects.all())
    seeded = 0
    for tenant in tenants:
        try:
            seed_agent_specs(tenant)
            seeded += 1
        except Exception as exc:  # noqa: BLE001 — one bad tenant must not abort the backfill
            print(f"  seed_a11y_journey: tenant {tenant.id} skipped — {exc}")
    print(
        f"  seed_a11y_journey: (re)seeded {len(ACTIVE_AGENT_CATALOG)} catalog agents for "
        f"{seeded}/{len(tenants)} tenant(s). If this is 0/0, run migrations as the privileged "
        f"role (the app role sees no tenants under FORCE RLS)."
    )


def unseed_noop(apps, schema_editor):
    # Seeding is additive and idempotent; other phases' specs share the same rows, so there is
    # nothing safe or meaningful to un-seed. Reverse is a deliberate no-op.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0006_seed_a11y_judge"),
        ("tenancy", "0002_rls"),
    ]

    operations = [
        migrations.RunPython(seed_a11y_journey, unseed_noop),
    ]
