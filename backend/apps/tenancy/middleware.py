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
"""
from apps.tenancy.context import clear_current_tenant, set_current_tenant


class TenantContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant_id = self._resolve_tenant(request)
        # Expose the resolved tenant to views (None when unresolved) for explicit
        # query scoping — defense-in-depth alongside RLS (which the local superuser
        # connection bypasses).
        request.tenant_id = tenant_id
        # No tenant resolved (e.g. health checks, pre-auth): don't touch the DB.
        if not tenant_id:
            return self.get_response(request)
        set_current_tenant(tenant_id)
        try:
            return self.get_response(request)
        finally:
            clear_current_tenant()

    @staticmethod
    def _resolve_tenant(request):
        session = getattr(request, "session", None)
        tenant_id = session.get("tenant_id") if session is not None else None
        if tenant_id:
            return tenant_id
        # Pre-auth dev/testing path (RBAC + real auth arrive in later phases).
        return request.headers.get("X-Tenant-ID")
