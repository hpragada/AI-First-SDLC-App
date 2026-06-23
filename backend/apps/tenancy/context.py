"""Tenant DB-session context for RLS (#6).

Sets the `app.tenant_id` GUC on the connection so Postgres RLS policies scope every
query. Used by the request middleware AND (from P0-T8) by Temporal activities — any
code path that issues tenant-scoped DB queries must establish this context first.
"""
from contextlib import contextmanager

from django.conf import settings
from django.db import connection

_SETTING = settings.RLS_TENANT_SETTING


def set_current_tenant(tenant_id) -> None:
    """Set app.tenant_id for the current DB session (session-scoped, not local)."""
    value = str(tenant_id) if tenant_id else ""
    with connection.cursor() as cur:
        cur.execute("SELECT set_config(%s, %s, false)", [_SETTING, value])


def get_current_tenant() -> str:
    """Read the current app.tenant_id GUC ('' when unset)."""
    with connection.cursor() as cur:
        cur.execute("SELECT current_setting(%s, true)", [_SETTING])
        return cur.fetchone()[0] or ""


def clear_current_tenant() -> None:
    """Reset app.tenant_id to empty (RLS then matches no rows — fail-closed)."""
    with connection.cursor() as cur:
        cur.execute("SELECT set_config(%s, %s, false)", [_SETTING, ""])


@contextmanager
def tenant_context(tenant_id):
    """Scope a block of DB work to a tenant, restoring the prior scope on exit.

    Restoring (rather than blanket-clearing) makes the context re-entrant: a nested
    `tenant_context` returns control to its caller's tenant instead of clobbering it
    to empty. The outermost context restores to '' (fail-closed), as before.
    """
    previous = get_current_tenant()
    set_current_tenant(tenant_id)
    try:
        yield
    finally:
        set_current_tenant(previous)
