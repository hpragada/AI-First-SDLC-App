"""RLS for the new quality tables (non-negotiable #6).

Mirrors the P0-T4 policy: FORCE row-level security + a tenant-isolation policy so the
non-superuser app role only sees its own tenant's rows.
"""
from django.conf import settings
from django.db import migrations

_TABLES = (
    "quality_testexecution",
    "quality_testquarantine",
    "quality_previewenv",
)
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def apply_rls(apps, schema_editor):
    quser = f'"{settings.APP_DB_USER}"'
    with schema_editor.connection.cursor() as cur:
        for table in _TABLES:
            cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO {quser}')
            cur.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            cur.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            cur.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cur.execute(
                f'CREATE POLICY tenant_isolation ON "{table}" '
                f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
            )


def revert_rls(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        for table in _TABLES:
            cur.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cur.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
            cur.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("quality", "0001_initial")]
    operations = [migrations.RunPython(apply_rls, revert_rls)]
