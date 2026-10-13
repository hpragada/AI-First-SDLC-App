"""RLS for the new integrations_sourcedocument table (non-negotiable #6).

Mirrors the P0-T4 policy: FORCE row-level security + a tenant-isolation policy so the
non-superuser app role only sees its own tenant's rows. (DML grants come automatically
from the P0-T4 `ALTER DEFAULT PRIVILEGES`, since migrations run as the owner.)
"""
from django.conf import settings
from django.db import migrations

_TABLE = "integrations_sourcedocument"
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def apply_rls(apps, schema_editor):
    quser = f'"{settings.APP_DB_USER}"'
    with schema_editor.connection.cursor() as cur:
        cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{_TABLE}" TO {quser}')
        cur.execute(f'ALTER TABLE "{_TABLE}" ENABLE ROW LEVEL SECURITY')
        cur.execute(f'ALTER TABLE "{_TABLE}" FORCE ROW LEVEL SECURITY')
        cur.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{_TABLE}"')
        cur.execute(
            f'CREATE POLICY tenant_isolation ON "{_TABLE}" '
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def revert_rls(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        cur.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{_TABLE}"')
        cur.execute(f'ALTER TABLE "{_TABLE}" NO FORCE ROW LEVEL SECURITY')
        cur.execute(f'ALTER TABLE "{_TABLE}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("integrations", "0003_sourcedocument")]
    operations = [migrations.RunPython(apply_rls, revert_rls)]
