"""RLS for the conformance-statement table (non-negotiable #6).

Mirrors 0018/0020/0023. This is the most sensitive accessibility table in the platform: it holds
a client's external-facing compliance claim together with the name of the person who signed it.
One tenant reading another's would hand over both a legal position and an individual's
professional attestation.
"""
from django.conf import settings
from django.db import migrations

_TABLES = ("a11y_a11yconformancestatement",)
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
    dependencies = [("a11y", "0024_conformance_statement")]
    operations = [migrations.RunPython(apply_rls, revert_rls)]
