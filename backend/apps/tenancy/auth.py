"""Authenticated-user helpers + DRF permissions (P4.7-T1).

Server-session auth (DECISION-3): the browser logs in, Django's session carries the
user, and `TenantContextMiddleware` already resolves the tenant from `request.user`
(falling back to `X-Tenant-ID` only for the runner/pre-auth paths). These helpers give
views a single way to read the current user and the canonical `/me` payload that the
AppShell + every authed screen consume.
"""
from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission

from apps.tenancy.models import User


def current_user(request) -> User | None:
    """The authenticated session user, or None (anonymous / pre-auth / runner token)."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user
    return None


def serialize_me(user: User) -> dict[str, Any]:
    """The canonical `/me` payload: user + tenant + per-project role memberships.

    `is_tenant_admin` is read defensively so this works before P4.7-T2 adds the field
    (it returns False until then); reused verbatim by signup/accept-invitation later.
    """
    memberships = (
        user.memberships.select_related("project").all()
        if hasattr(user, "memberships")
        else []
    )
    return {
        "user": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "is_tenant_admin": bool(getattr(user, "is_tenant_admin", False)),
        },
        "tenant": {"id": str(user.tenant_id), "name": user.tenant.name},
        "memberships": [
            {
                "project_id": str(m.project_id),
                "project_name": m.project.name,
                "role": m.role,
                # Bugs S.No 221: the sidebar has to decide whether to offer the brownfield
                # onboarding wizard, and this payload is the only place the frontend learns
                # anything about a project it is not currently looking at. Carried here for
                # the same reason `role` is — it travels with the selected project for free.
                # `select_related("project")` above means this costs no extra query.
                "track": m.project.track,
            }
            for m in memberships
        ],
    }


class IsAuthenticatedMember(BasePermission):
    """Any authenticated (session) user. Tenant scoping is enforced separately by RLS +
    the explicit `tenant_id` filter; this only gates 'is there a logged-in user'."""

    def has_permission(self, request, view) -> bool:
        return current_user(request) is not None


class IsTenantAdmin(BasePermission):
    """The tenant-level admin (`User.is_tenant_admin`). The flag lands in P4.7-T2; until
    then this denies everyone (no admin exists yet), which is the safe default."""

    def has_permission(self, request, view) -> bool:
        user = current_user(request)
        return bool(user and getattr(user, "is_tenant_admin", False))
