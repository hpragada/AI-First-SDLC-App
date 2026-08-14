"""RLS for the new a11y_a11yfinding table (non-negotiable #6).

Mirrors 0012_a11yscreenscan_rls. This is the most sensitive of the three accessibility tables:
a row names a route in a client's application, quotes the markup on it, points at a picture of
it, and states a conformance failure against a published standard. One tenant reading another's
would be handing over both an unreleased product and its compliance exposure.
"""
from django.conf import settings
from django.db import migrations

_TABLE = "a11y_a11yfinding"
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
    dependencies = [("a11y", "0013_a11yfinding")]
    operations = [migrations.RunPython(apply_rls, revert_rls)]
