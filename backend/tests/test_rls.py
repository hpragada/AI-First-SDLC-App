"""P0-T4 — RLS enforcement (non-negotiable #6).

These connect AS THE non-superuser app role (the Django test connection is the
privileged migration role, which bypasses RLS — so it cannot prove isolation).
`transaction=True` makes the ORM seed data committed and thus visible to the
separate app-role connection.
"""
import psycopg
import pytest
from django.conf import settings
from django.db import connection

from apps.projects.models import Project
from apps.tenancy.models import Tenant
from apps.tenancy.services import create_invitation


def _app_role_connection():
    """A fresh connection as the RLS-subject app role, to the active (test) DB."""
    sd = connection.settings_dict
    with connection.cursor() as cur:
        cur.execute("SELECT current_database()")
        dbname = cur.fetchone()[0]
    return psycopg.connect(
        host=sd["HOST"],
        port=sd["PORT"],
        dbname=dbname,
        user=settings.APP_DB_USER,
        password=settings.APP_DB_PASSWORD,
        autocommit=True,
    )


def _set_tenant(cur, tenant_id):
    cur.execute("SELECT set_config('app.tenant_id', %s, false)", [str(tenant_id)])


@pytest.mark.django_db(transaction=True)
def test_rls_blocks_cross_tenant_reads():
    a = Tenant.objects.create(name="A")
    b = Tenant.objects.create(name="B")
    Project.objects.create(tenant=a, name="A-proj")
    Project.objects.create(tenant=b, name="B-proj-1")
    Project.objects.create(tenant=b, name="B-proj-2")

    raw = _app_role_connection()
    try:
        with raw.cursor() as cur:
            _set_tenant(cur, a.id)
            cur.execute("SELECT count(*), array_agg(name) FROM projects_project")
            count_a, names_a = cur.fetchone()
            assert count_a == 1 and names_a == ["A-proj"]

            _set_tenant(cur, b.id)
            cur.execute("SELECT count(*) FROM projects_project")
            assert cur.fetchone()[0] == 2

            # No tenant context -> fail closed (sees nothing).
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [""])
            cur.execute("SELECT count(*) FROM projects_project")
            assert cur.fetchone()[0] == 0
    finally:
        raw.close()


@pytest.mark.django_db(transaction=True)
def test_rls_with_check_blocks_cross_tenant_write():
    a = Tenant.objects.create(name="A")
    b = Tenant.objects.create(name="B")

    raw = _app_role_connection()
    try:
        with raw.cursor() as cur:
            _set_tenant(cur, a.id)
            # Scoped to A, attempt to write a row owned by B -> WITH CHECK violation.
            with pytest.raises(psycopg.Error):
                cur.execute(
                    "INSERT INTO projects_project "
                    "(id, tenant_id, name, track, repo_topology, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), %s, 'evil', 'greenfield', 'single', 'active', "
                    "now(), now())",
                    [str(b.id)],
                )
    finally:
        raw.close()


@pytest.mark.django_db(transaction=True)
def test_rls_invitation_lookup_works_pre_auth():
    """Regression: accept-invitation looks up an invitation by token hash BEFORE any
    tenant is known (like login by email) — this must not be silently zero-rowed by
    RLS under the real app role. See 0006_invitation_rls_auth_bootstrap.py."""
    tenant = Tenant.objects.create(name="Acme")
    other = Tenant.objects.create(name="Globex")
    inv, raw_token = create_invitation(tenant=tenant, invited_by=None, email="new@acme.com")
    create_invitation(tenant=other, invited_by=None, email="alien@globex.com")
    token_hash = inv.token_hash

    raw = _app_role_connection()
    try:
        with raw.cursor() as cur:
            # No tenant context set — the pre-auth window.
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [""])
            cur.execute(
                "SELECT email FROM tenancy_invitation WHERE token_hash = %s", [token_hash]
            )
            row = cur.fetchone()
            assert row is not None and row[0] == "new@acme.com"
    finally:
        raw.close()


@pytest.mark.django_db(transaction=True)
def test_ledger_db_trigger_blocks_mutation():
    from apps.ledger.models import Event

    a = Tenant.objects.create(name="A")
    e = Event.objects.create(tenant=a, actor="sys", action="x", target_type="run")

    raw = _app_role_connection()
    try:
        with raw.cursor() as cur:
            _set_tenant(cur, a.id)
            with pytest.raises(psycopg.Error):
                cur.execute("UPDATE ledger_event SET action='y' WHERE id = %s", [str(e.id)])
            with pytest.raises(psycopg.Error):
                cur.execute("DELETE FROM ledger_event WHERE id = %s", [str(e.id)])
    finally:
        raw.close()
