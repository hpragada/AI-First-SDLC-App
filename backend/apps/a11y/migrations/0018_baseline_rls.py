"""RLS for the two baseline-audit tables (non-negotiable #6).

Mirrors 0014_a11yfinding_rls. Both hold client-identifying material: the route list is a map
of an application's pages, and an audit records where that application was reachable and what
a pass over it found. One tenant reading another's would hand over the shape of an unreleased
product.
"""
from django.conf import settings
from django.db import migrations

_TABLES = ("a11y_a11yroute", "a11y_a11ybaselineaudit")
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
    dependencies = [("a11y", "0017_a11yroute_a11ybaselineaudit")]
    operations = [migrations.RunPython(apply_rls, revert_rls)]
