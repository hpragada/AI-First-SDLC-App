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

from django.db import transaction

from apps.registry.catalog import seed_agent_specs
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant, User


class SignupError(Exception):
    """Self-serve signup was rejected (e.g. the email already exists)."""


def create_tenant(*, name: str, config: dict | None = None,
                  model_routing: dict | None = None) -> Tenant:
    """Create a Tenant, bootstrapping the RLS context to its own (pre-assigned) id."""
    tenant = Tenant(name=name, config=config or {}, model_routing=model_routing or {})
    # `id` is populated by the field default at instantiation; mirror it now so the
    # RLS WITH CHECK predicate (tenant_id = app.tenant_id) is satisfiable.
    tenant.tenant_id = tenant.id
    with tenant_context(tenant.id):
        tenant.save(force_insert=True)

    # New tenants need the agent registry seeded so phase triggers like 01_ideation
    # are available immediately after tenant creation.
    seed_agent_specs(tenant)
    return tenant


def signup(*, name: str, email: str, password: str, org_name: str) -> User:
    """Self-serve signup (DECISIONS 1 & 2): create a new Tenant + its first user as the
    tenant-admin, atomically. The signer-up owns the workspace; everyone else joins by
    invitation. Email is globally unique — a duplicate is rejected before any write.
    """
    if User.objects.filter(email__iexact=email).exists():
        raise SignupError("An account with this email already exists.")
    with transaction.atomic():
        tenant = create_tenant(name=org_name)
        with tenant_context(tenant.id):
            user = User.objects.create_user(
                email=email, name=name, tenant=tenant, password=password,
                is_tenant_admin=True,
            )
    return user
