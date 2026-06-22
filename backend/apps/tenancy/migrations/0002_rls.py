"""P0-T4 — Row-Level Security (non-negotiable #6).

Creates the non-superuser app role, grants it DML, and enables FORCE RLS with a
tenant-isolation policy on every platform table. Also installs the ledger
append-only DB guard. Runs as the privileged migration role (DATABASE_URL); the
running app/worker connect as the app role and are subject to these policies.
"""
from django.conf import settings
from django.db import migrations

# The 14 platform domain tables. Django's framework/auth tables are intentionally
# excluded (no tenant business data; same category as auth_group/django_session).
PLATFORM_TABLES = [
    "tenancy_tenant",
    "tenancy_user",
    "tenancy_membership",
    "projects_project",
    "projects_projectprofile",
    "projects_repository",
    "workitems_workitem",
    "registry_agentspec",
    "registry_artifact",
    "registry_traceedge",
    "runs_run",
    "gates_approval",
    "integrations_integrationconnection",
    "ledger_event",
]

# RLS predicate: NULLIF guards the unset/empty case so it fails closed (no rows),
# instead of erroring on ''::uuid.
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def apply_rls(apps, schema_editor):
    app_user = settings.APP_DB_USER
    app_pw = settings.APP_DB_PASSWORD
    quser = f'"{app_user}"'
    with schema_editor.connection.cursor() as cur:
        # 1) App role — idempotent. Default CREATE ROLE is NOSUPERUSER NOBYPASSRLS,
        #    so RLS genuinely applies to it.
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [app_user])
        if not cur.fetchone():
            cur.execute(f"CREATE ROLE {quser} LOGIN PASSWORD %s", [app_pw])

        # 2) Grants on the current database.
        cur.execute("SELECT current_database()")
        dbname = cur.fetchone()[0]
        cur.execute(f'GRANT CONNECT ON DATABASE "{dbname}" TO {quser}')
        cur.execute(f"GRANT USAGE ON SCHEMA public TO {quser}")
        cur.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {quser}"
        )
        cur.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {quser}")
        cur.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {quser}"
        )

        # 3) RLS + tenant-isolation policy on every platform table.
        for table in PLATFORM_TABLES:
            cur.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            cur.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            cur.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cur.execute(
                f'CREATE POLICY tenant_isolation ON "{table}" '
                f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
            )

        # 4) Ledger append-only DB guard (complements the model-level guard, #3).
        cur.execute(
            """
            CREATE OR REPLACE FUNCTION ledger_event_append_only() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'ledger_event is append-only (% blocked)', TG_OP;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        cur.execute("DROP TRIGGER IF EXISTS ledger_event_no_mutate ON ledger_event")
        cur.execute(
            """
            CREATE TRIGGER ledger_event_no_mutate
            BEFORE UPDATE OR DELETE ON ledger_event
            FOR EACH ROW EXECUTE FUNCTION ledger_event_append_only();
            """
        )


def revert_rls(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        cur.execute("DROP TRIGGER IF EXISTS ledger_event_no_mutate ON ledger_event")
        cur.execute("DROP FUNCTION IF EXISTS ledger_event_append_only()")
        for table in PLATFORM_TABLES:
            cur.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cur.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
            cur.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        # The role is cluster-level and may be shared; leave it in place.


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0001_initial"),
        ("projects", "0002_initial"),
        ("workitems", "0001_initial"),
        ("registry", "0002_initial"),
        ("runs", "0002_initial"),
        ("gates", "0002_initial"),
        ("integrations", "0002_initial"),
        ("ledger", "0002_initial"),
    ]

    operations = [migrations.RunPython(apply_rls, revert_rls)]
