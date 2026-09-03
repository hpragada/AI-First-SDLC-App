"""G4 — mark accessibility-judging work items as the carriers they always were.

The accessibility judge cannot run on the story (`_guard_no_active_run` refuses a second run on
a work item that already has a live one, and the build's own run is live for the whole build),
so `apps.a11y.aipass` creates a throwaway work item per test run to host it. It wrote that fact
as `external_ref.kind`, and every carrier filter in the platform reads `external_ref.source` —
so each test run left an "Accessibility judging" task on the user's board and an extra run in
Phases & Runs.

`aipass` now writes `source` too, but only on items it creates from here on. This backfills the
ones already on a board — which are exactly the boards that have the problem.

Runs as the privileged migration role, like `a11y/0005_load_wcag_for_existing_tenants`: work
items are FORCE ROW LEVEL SECURITY, so a merely-owner role would read zero rows and the
backfill would quietly do nothing. `app.tenant_id` is set per tenant and reset afterwards so no
later migration inherits it.

Narrow on purpose: only rows whose `external_ref.kind` is exactly `a11y_judging`, and only the
one key is added — everything else in the `external_ref` is preserved, `kind` included.
"""
from django.db import migrations

JUDGING_KIND = "a11y_judging"
CARRIER_SOURCE = "a11y_judging_carrier"


def _set_tenant(connection, value: str) -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', %s, false)", [value])


def mark(apps, schema_editor):
    Tenant = apps.get_model("tenancy", "Tenant")
    WorkItem = apps.get_model("workitems", "WorkItem")
    connection = schema_editor.connection

    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _set_tenant(connection, str(tenant_id))
            rows = WorkItem.objects.filter(
                tenant_id=tenant_id, external_ref__kind=JUDGING_KIND)
            for item in rows:
                ref = dict(item.external_ref or {})
                if ref.get("source") == CARRIER_SOURCE:
                    continue
                ref["source"] = CARRIER_SOURCE
                item.external_ref = ref
                item.save(update_fields=["external_ref"])
    finally:
        _set_tenant(connection, "")


def unmark(apps, schema_editor):
    """Take the marker back off, leaving `kind` and everything else as it was."""
    Tenant = apps.get_model("tenancy", "Tenant")
    WorkItem = apps.get_model("workitems", "WorkItem")
    connection = schema_editor.connection

    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _set_tenant(connection, str(tenant_id))
            rows = WorkItem.objects.filter(
                tenant_id=tenant_id, external_ref__source=CARRIER_SOURCE)
            for item in rows:
                ref = dict(item.external_ref or {})
                ref.pop("source", None)
                item.external_ref = ref
                item.save(update_fields=["external_ref"])
    finally:
        _set_tenant(connection, "")


class Migration(migrations.Migration):

    dependencies = [
        ("workitems", "0005_alter_workitem_type"),
        ("tenancy", "0002_rls"),
    ]

    operations = [migrations.RunPython(mark, unmark)]
