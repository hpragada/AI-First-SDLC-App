"""Bugs S.No 224 — record WHEN an artifact was published, and backfill what is already published.

The dashboard's "published this week" count and its recent-publishes list both filtered on
`created_at`, which is when the agent DRAFTED the artifact. Drafting and publishing are separated
by a review gate, so they are routinely days apart: something drafted eight days ago and published
this morning never appeared in a list of this week's publishes, while something drafted today and
never published did. There was no publish timestamp to filter on, and `updated_at` is `auto_now`
so it moves on any later edit and cannot stand in.

The backfill uses `updated_at` as the honest approximation for rows that are ALREADY published:
that is when the row's status last changed, so for an artifact published and not touched since it
is exactly right, and for one edited afterwards it is late rather than invented. Recorded here as
an approximation so nobody later reads a backfilled date as an exact publication time.

Runs per tenant with `app.tenant_id` set, like `integrations/0010_a11yai_autoprovision`: the
platform tables are FORCE ROW LEVEL SECURITY, so a backfill that does not set it would read zero
rows and quietly do nothing while reporting success.

Idempotent: only rows that are published AND have no timestamp yet are touched, so re-running
never re-dates a publication.
"""
from django.db import migrations, models
from django.db.models import F


def _set_tenant(connection, value: str) -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', %s, false)", [value])


def backfill(apps, schema_editor):
    Tenant = apps.get_model("tenancy", "Tenant")
    Artifact = apps.get_model("registry", "Artifact")
    connection = schema_editor.connection

    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _set_tenant(connection, str(tenant_id))
            Artifact.objects.filter(
                tenant_id=tenant_id, status="published", published_at__isnull=True,
            ).update(published_at=F("updated_at"))
    finally:
        _set_tenant(connection, "")


def unbackfill(apps, schema_editor):
    """Deliberately does nothing — the column itself is dropped by reversing the AddField."""


class Migration(migrations.Migration):

    dependencies = [
        ("registry", "0007_seed_a11y_journey"),
        ("tenancy", "0002_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="artifact",
            name="published_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(backfill, unbackfill),
    ]
