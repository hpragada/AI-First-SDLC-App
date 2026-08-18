"""RLS for the criterion-coverage table (non-negotiable #6).

Mirrors 0018_baseline_rls and 0020_journey_rls. This table is the evidence a conformance
statement is compiled from — which pages of a client's product were checked, against what, and
what came back. One tenant reading another's would hand over the route map of an unreleased
product together with an assessment of where it is weakest.
"""
from django.conf import settings
from django.db import migrations

_TABLES = ("a11y_a11ycriterioncoverage",)
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
    dependencies = [("a11y", "0022_criterion_coverage")]
    operations = [migrations.RunPython(apply_rls, revert_rls)]
