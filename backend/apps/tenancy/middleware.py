"""Per-request tenant context for RLS.

Resolves the request's tenant (authenticated user's tenant, or an `X-Tenant-ID`
header for dev/testing before full auth lands) and sets `app.tenant_id` on the DB
session for the duration of the request, clearing it afterward (fail-closed).
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
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return getattr(user, "tenant_id", None)
        # Pre-auth dev/testing path (RBAC + real auth arrive in later phases).
        return request.headers.get("X-Tenant-ID")
