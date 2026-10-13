"""P4.7 hotfix — RLS on tenancy_user blocked authentication itself.

Every other platform table is correctly scoped by `0002_rls.py`'s strict
`tenant_id = app.tenant_id` predicate: you must already know the tenant to read a row.
But *finding out which tenant a user belongs to* is exactly what login (`authenticate()`
by email) and session re-auth (`AuthenticationMiddleware` resolving `request.user` by id)
have to do — before any tenant is known. Under the strict predicate, run as the
RLS-enforced `sdlc_app` role (not the Postgres-superuser role the test suite runs as,
which bypasses RLS entirely and never exercised this path), those lookups always return
zero rows: nobody can log in.

Fix: widen `tenancy_user`'s policy so a row is also visible when no tenant is scoped yet
(`app.tenant_id` unset — the pre-auth bootstrap window). Once a tenant *is* scoped
(normal authenticated operation, set by `TenantContextMiddleware` from the session — see
that middleware's docstring), the widened clause is false and the strict per-tenant match
is all that applies, same as before. Every other table's policy is untouched.
"""
from django.db import migrations

_STRICT_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_BOOTSTRAP_PREDICATE = (
    f"({_STRICT_PREDICATE}) OR NULLIF(current_setting('app.tenant_id', true), '') IS NULL"
)


def widen_user_policy(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        cur.execute('DROP POLICY IF EXISTS tenant_isolation ON "tenancy_user"')
        # WITH CHECK stays strict (writes must still name a real tenant) — only the
        # read-side USING clause gets the auth-bootstrap carve-out.
        cur.execute(
            'CREATE POLICY tenant_isolation ON "tenancy_user" '
            f"USING ({_BOOTSTRAP_PREDICATE}) WITH CHECK ({_STRICT_PREDICATE})"
        )


def revert_user_policy(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        cur.execute('DROP POLICY IF EXISTS tenant_isolation ON "tenancy_user"')
        cur.execute(
            'CREATE POLICY tenant_isolation ON "tenancy_user" '
            f"USING ({_STRICT_PREDICATE}) WITH CHECK ({_STRICT_PREDICATE})"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0004_user_reset_token_expires_user_reset_token_hash_and_more"),
    ]

    operations = [migrations.RunPython(widen_user_policy, revert_user_policy)]
