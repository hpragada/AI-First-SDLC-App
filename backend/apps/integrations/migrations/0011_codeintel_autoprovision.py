"""Bugs S.No N1 — give every EXISTING tenant the credential-free `codeintel` capability.

New tenants get it from `create_tenant` (see `provision_builtin_capabilities`, which now lists
the pair). Tenants that already exist predate that, and were never auto-provisioned it at all —
only the demo seed created a codeintel row — so without this backfill a real workspace would have
no connection record while the Integrations page told it "Connected". Removing the card without
the backfill would leave nothing behind to be connected by.

Runs as the privileged migration role (like `tenancy/0002_rls` and `0010_a11yai_autoprovision`),
which is what makes reading across all tenants possible at all: the platform tables are FORCE ROW
LEVEL SECURITY, so a merely-owner role would read zero tenants here and the backfill would quietly
do nothing. `app.tenant_id` is still set per tenant before each insert so the policy's WITH CHECK
is satisfied under any role, and reset afterwards so no later migration inherits it.

Idempotent: re-running skips tenants that already have a codeintel connection, and it never
touches one a tenant configured differently.
"""
from django.db import migrations

CAPABILITY = "codeintel"
CONNECTOR = "builtin"


def _set_tenant(connection, value: str) -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', %s, false)", [value])


def backfill(apps, schema_editor):
    Tenant = apps.get_model("tenancy", "Tenant")
    IntegrationConnection = apps.get_model("integrations", "IntegrationConnection")
    connection = schema_editor.connection

    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _set_tenant(connection, str(tenant_id))
            if IntegrationConnection.objects.filter(
                tenant_id=tenant_id, capability=CAPABILITY
            ).exists():
                continue
            IntegrationConnection.objects.create(
                tenant_id=tenant_id, capability=CAPABILITY, connector=CONNECTOR,
                scopes={}, token_ref="builtin",
            )
    finally:
        _set_tenant(connection, "")


def unbackfill(apps, schema_editor):
    """Deliberately does nothing.

    Rolling this migration back must not delete a tenant's integration row: by the time anyone
    rolls back, that row may have been edited or re-pointed by an admin, and the connection is
    cheap to leave in place but destructive to remove.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0010_a11yai_autoprovision"),
        ("tenancy", "0002_rls"),
    ]

    operations = [migrations.RunPython(backfill, unbackfill)]
