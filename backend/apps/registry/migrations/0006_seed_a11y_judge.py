"""Backfill the accessibility judge (09c) onto every EXISTING tenant (QA-02a).

Adding an agent to the catalog only reaches tenants created *after* it exists — the
tenant-creation hook calls `seed_agent_specs`. Tenants created earlier need this one-time
backfill. It (re)seeds each tenant's AgentSpec rows from the current catalog, which is
idempotent (`update_or_create` per entry), so it only ADDS what is missing — `09c_a11y_judge`
— without touching or duplicating the specs already there.

**Why it matters more here than for a normal agent.** `dispatch.judge_available()` reports the
judge as unavailable and routes every element to human review while no `09c_a11y_judge` spec
exists for the workspace. Without this backfill, accessibility judging would work on new
workspaces and be silently unavailable on every current one — including the shared development
database — which is exactly the failure mode D-A11Y-3 exists to make visible rather than quiet.

This is DATA, not schema: no table changes, just rows. It runs as the privileged migration
role, which sees across tenants despite FORCE ROW LEVEL SECURITY; the app role never could.

Mirrors `0004_seed_document_vision` deliberately — same operation, same reasoning, and any
future native agent should copy it rather than invent a third shape.
"""
from __future__ import annotations

from django.db import migrations


def seed_a11y_judge(apps, schema_editor):
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
            print(f"  seed_a11y_judge: tenant {tenant.id} skipped — {exc}")
    print(
        f"  seed_a11y_judge: (re)seeded {len(ACTIVE_AGENT_CATALOG)} catalog agents for "
        f"{seeded}/{len(tenants)} tenant(s). If this is 0/0, run migrations as the privileged "
        f"role (the app role sees no tenants under FORCE RLS)."
    )


def unseed_noop(apps, schema_editor):
    # Seeding is additive and idempotent; other phases' specs share the same rows, so there is
    # nothing safe or meaningful to un-seed. Reverse is a deliberate no-op.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0005_alter_artifact_status"),
        ("tenancy", "0002_rls"),
    ]

    operations = [
        migrations.RunPython(seed_a11y_judge, unseed_noop),
    ]
