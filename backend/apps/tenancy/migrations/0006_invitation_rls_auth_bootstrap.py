"""Bug fix — RLS on tenancy_invitation blocked the pre-auth accept-invitation lookup.

Same root cause `0005_user_rls_auth_bootstrap.py` fixed for `tenancy_user`: every other
platform table is correctly scoped by `0002_rls.py`'s (and `0004_...`'s) strict
`tenant_id = app.tenant_id` predicate, but *looking up an invitation by its token* is,
like login, exactly the kind of pre-auth read that has to work before any tenant is
known. Under the strict predicate, run as the RLS-enforced app role (not the
Postgres-superuser role the test suite runs as, which bypasses RLS entirely), the
token-hash lookup in `accept_invitation()` always returned zero rows — every accept
attempt 410'd as "not valid", regardless of whether the token was actually valid,
expired, or used.

Fix: widen `tenancy_invitation`'s policy the same way — a row is also visible when no
tenant is scoped yet (`app.tenant_id` unset). The caller still narrows to exactly one
row via the unique `token_hash` filter, so this doesn't expose a tenant's invitation
list pre-auth, only the single matching invitation, same tradeoff already accepted for
`tenancy_user` + email lookup on login.
"""
from django.db import migrations

_STRICT_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_BOOTSTRAP_PREDICATE = (
    f"({_STRICT_PREDICATE}) OR NULLIF(current_setting('app.tenant_id', true), '') IS NULL"
)


def widen_invitation_policy(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        cur.execute('DROP POLICY IF EXISTS tenant_isolation ON "tenancy_invitation"')
        # WITH CHECK stays strict (writes must still name a real tenant) — only the
        # read-side USING clause gets the auth-bootstrap carve-out.
        cur.execute(
            'CREATE POLICY tenant_isolation ON "tenancy_invitation" '
            f"USING ({_BOOTSTRAP_PREDICATE}) WITH CHECK ({_STRICT_PREDICATE})"
        )


def revert_invitation_policy(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        cur.execute('DROP POLICY IF EXISTS tenant_isolation ON "tenancy_invitation"')
        cur.execute(
            'CREATE POLICY tenant_isolation ON "tenancy_invitation" '
            f"USING ({_STRICT_PREDICATE}) WITH CHECK ({_STRICT_PREDICATE})"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0005_user_rls_auth_bootstrap"),
    ]

    operations = [migrations.RunPython(widen_invitation_policy, revert_invitation_policy)]
