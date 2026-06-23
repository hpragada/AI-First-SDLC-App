"""Tenancy services — tenant bootstrap (the RLS chicken-and-egg).

`tenancy_tenant` carries FORCE RLS with `WITH CHECK (tenant_id = app.tenant_id)`
like every platform table, so an INSERT under the non-superuser app role only
passes if `app.tenant_id` already equals the new row's id. Django assigns the
`id` uuid default at instantiation, so we know the id before the INSERT and can
set the DB session context to it first. This is the one place a tenant is created
without an existing tenant context — every other write rides the per-request
context set by `TenantContextMiddleware`.
"""
from __future__ import annotations

from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant


def create_tenant(*, name: str, config: dict | None = None,
                  model_routing: dict | None = None) -> Tenant:
    """Create a Tenant, bootstrapping the RLS context to its own (pre-assigned) id."""
    tenant = Tenant(name=name, config=config or {}, model_routing=model_routing or {})
    # `id` is populated by the field default at instantiation; mirror it now so the
    # RLS WITH CHECK predicate (tenant_id = app.tenant_id) is satisfiable.
    tenant.tenant_id = tenant.id
    with tenant_context(tenant.id):
        tenant.save(force_insert=True)
    return tenant
