"""Per-request tenant context for RLS.

Resolves the request's tenant from the session (set at login — see auth_views.py) or
an `X-Tenant-ID` header for dev/testing before full auth lands, and sets `app.tenant_id`
on the DB session for the duration of the request, clearing it afterward (fail-closed).

Deliberately does NOT resolve the tenant from `request.user`: this middleware must run
*before* `AuthenticationMiddleware` (see settings.MIDDLEWARE) so `app.tenant_id` is
already set by the time anything lazily evaluates `request.user` — `AuthenticationMiddleware`
looks the user up by id from the RLS-protected `tenancy_user` table, which would
otherwise deadlock: no tenant scope until the user resolves, no user resolves until
there's a tenant scope. Reading the tenant straight out of session data sidesteps that
entirely (no DB query needed to resolve it).

Connection reuse (`CONN_MAX_AGE` > 0) makes the release path load-bearing. `app.tenant_id`
is a SESSION GUC, so it outlives the request on a pooled connection — and the no-tenant
path below deliberately never touches the DB, so it would inherit whatever scope the previous
request left behind. The invariant this module maintains is therefore: **after a tenant-scoped
request the connection is either scoped to '' (fail-closed) or gone.**
"""
import logging

from django.db import OperationalError, connection

from apps.tenancy.context import clear_current_tenant, set_current_tenant

logger = logging.getLogger(__name__)


def _enter_tenant_scope(tenant_id) -> None:
    """Set the request's tenant scope, retrying once on a dead/failed connection.

    This is the FIRST database touch of every tenant-scoped request, so a single dropped
    TCP/TLS handshake used to become a user-facing 500 (Bugs S.No 235). `CONN_HEALTH_CHECKS`
    covers a reused connection that died between requests; this covers the rest — a genuine
    connect failure. One retry only: a real outage should still surface, not hang.
    """
    try:
        set_current_tenant(tenant_id)
    except OperationalError:
        _discard_connection()
        set_current_tenant(tenant_id)


def _release_tenant_scope() -> None:
    """Clear `app.tenant_id`; if that fails, DISCARD the connection rather than pool it.

    A failed release (typically the connection dying mid-request) would otherwise return a
    connection to the pool still scoped to this tenant, and the next request that resolves
    no tenant takes the early return below without setting one — inheriting the scope. Closing
    makes that leak impossible instead of merely unlikely.

    Never re-raises: the response has already been produced, and failing an otherwise-good
    request because its cleanup failed would be a worse outcome than logging it.
    """
    try:
        clear_current_tenant()
    except Exception:
        logger.warning(
            "could not clear app.tenant_id; discarding the connection so it cannot be "
            "reused while still scoped to a tenant", exc_info=True,
        )
        _discard_connection()


def _discard_connection() -> None:
    """Close the current connection, tolerating a close that itself fails (already-broken
    sockets raise here). Django opens a fresh one on next use."""
    try:
        connection.close()
    except Exception:  # noqa: BLE001 — a broken connection is exactly what we're discarding
        logger.debug("closing the database connection failed", exc_info=True)


class TenantContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant_id = self._resolve_tenant(request)
        # Expose the resolved tenant to views (None when unresolved) for explicit
        # query scoping — defense-in-depth alongside RLS (which the local superuser
        # connection bypasses).
        request.tenant_id = tenant_id
        # No tenant resolved (e.g. health checks, pre-auth): don't touch the DB. Safe under
        # connection reuse only because a tenant-scoped request always leaves the connection
        # at '' or discards it — see `_release_tenant_scope`.
        if not tenant_id:
            return self.get_response(request)
        _enter_tenant_scope(tenant_id)
        try:
            return self.get_response(request)
        finally:
            _release_tenant_scope()

    @staticmethod
    def _resolve_tenant(request):
        session = getattr(request, "session", None)
        tenant_id = session.get("tenant_id") if session is not None else None
        if tenant_id:
            return tenant_id
        # Pre-auth dev/testing path (RBAC + real auth arrive in later phases).
        return request.headers.get("X-Tenant-ID")
