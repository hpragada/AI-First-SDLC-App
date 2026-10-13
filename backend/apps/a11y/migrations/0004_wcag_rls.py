"""RLS for the WCAG criterion, glossary term + ACT rule tables (non-negotiable #6).

Same policy as 0002: FORCE row-level security plus a tenant-isolation policy, so the
non-superuser app role only ever reads its own tenant's copy of the standard.

The standard itself is public, so this is not about secrecy — it is about the decision to
load it **per tenant** so a client can carry an amended set. Without RLS, one tenant's
amendment would silently become everyone's, and a checker would ground its judgment in
another client's edits.
"""
from django.conf import settings
from django.db import migrations

_TABLES = ("a11y_wcagcriterion", "a11y_wcagterm", "a11y_actrule")
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
    dependencies = [("a11y", "0003_actrule_wcagcriterion_wcagterm")]
    operations = [migrations.RunPython(apply_rls, revert_rls)]
