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

import hashlib
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.base import Role
from apps.projects.models import Project
from apps.registry.catalog import gate_roles, seed_agent_specs
from apps.tenancy.context import tenant_context
from apps.tenancy.emails import send_invitation_email, send_password_reset_email
from apps.tenancy.models import Invitation, Membership, Tenant, User

# Token lifetimes.
INVITE_TTL = timedelta(days=7)
RESET_TTL = timedelta(hours=1)


class SignupError(Exception):
    """Self-serve signup was rejected (e.g. the email already exists)."""


class InvitationError(Exception):
    """An invitation could not be created or accepted. `status` maps to the HTTP code the
    view returns (409 conflict / used, 410 gone / expired-or-revoked, 400 otherwise)."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


class ResetError(Exception):
    """A password-reset token was invalid or expired (→ 410)."""


class RoleError(Exception):
    """A user/role-management operation was rejected. `status` maps to the HTTP code
    (409 for guard/duplicate conflicts, 404 for unknown target)."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def _new_token() -> tuple[str, str]:
    """Return (raw, sha256-hex). Only the hash is ever persisted."""
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


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


# ── Invitations (P4.7-T3, J2) ───────────────────────────────────────
def create_invitation(*, tenant, invited_by, email: str, name: str = "",
                      grants: list | None = None) -> tuple[Invitation, str]:
    """Create a pending invitation + email the accept link. Returns (invitation, raw_token).
    Runs inside the inviter's tenant context (set by middleware). Rejects an email that is
    already a user (they should log in / reset instead)."""
    email = email.strip().lower()
    if User.objects.filter(email__iexact=email).exists():
        raise InvitationError("A user with this email already exists.")
    # Normalize grants to JSON-safe primitives (UUIDField hands us UUID objects).
    norm_grants = [
        {"project_id": str(g["project_id"]), "role": str(g["role"])}
        for g in (grants or [])
    ]
    raw, token_hash = _new_token()
    invitation = Invitation.objects.create(
        tenant=tenant, email=email, name=name or "", grants=norm_grants,
        token_hash=token_hash, invited_by=invited_by,
        expires_at=timezone.now() + INVITE_TTL,
    )
    send_invitation_email(invitation, raw)
    return invitation, raw


def resend_invitation(invitation: Invitation) -> str:
    """Rotate the token + extend the expiry on a pending invite and re-send. Returns the new
    raw token. A revoked/accepted invite cannot be resent."""
    if invitation.status != Invitation.Status.PENDING:
        raise InvitationError(
            f"Cannot resend a {invitation.status} invitation.", status=409
        )
    raw, token_hash = _new_token()
    invitation.token_hash = token_hash
    invitation.expires_at = timezone.now() + INVITE_TTL
    invitation.save(update_fields=["token_hash", "expires_at", "updated_at"])
    send_invitation_email(invitation, raw)
    return raw


def revoke_invitation(invitation: Invitation) -> Invitation:
    """Mark a pending invitation revoked (its token stops working)."""
    if invitation.status == Invitation.Status.ACCEPTED:
        raise InvitationError("This invitation has already been accepted.", status=409)
    invitation.status = Invitation.Status.REVOKED
    invitation.save(update_fields=["status", "updated_at"])
    return invitation


def get_invitation_preview(token: str) -> dict:
    """Look up an invitation by its raw token for the pre-auth accept-invite page. Read-only —
    unlike `accept_invitation()`, this never transitions `status` (not even on an expired
    invite); it only reports what accepting would find. Same 409/410 semantics as accept.
    The tenant-scoped display fields (org name, inviter, project names) are read inside the
    invitation's own `tenant_context`, the same pre-auth-then-scoped pattern `accept_invitation()`
    uses — the RLS bootstrap carve-out (0006) is what makes the initial token-hash lookup
    itself possible before any tenant is known."""
    invitation = Invitation.objects.filter(token_hash=_hash_token(token)).first()
    if invitation is None:
        raise InvitationError("This invitation link is not valid.", status=410)
    if invitation.status == Invitation.Status.ACCEPTED:
        raise InvitationError("This invitation has already been used.", status=409)
    if invitation.status == Invitation.Status.REVOKED:
        raise InvitationError("This invitation has been revoked.", status=410)
    if invitation.is_expired:
        raise InvitationError("This invitation has expired.", status=410)

    with tenant_context(invitation.tenant_id):
        tenant_name = invitation.tenant.name
        inviter_name = invitation.invited_by.name if invitation.invited_by_id else None
        project_names = {
            str(p.id): p.name
            for p in Project.objects.filter(
                id__in=[g["project_id"] for g in invitation.grants]
            )
        }
        grants = [
            {
                "project_id": g["project_id"],
                "project_name": project_names.get(g["project_id"], ""),
                "role": g["role"],
                "role_label": Role(g["role"]).label,
            }
            for g in invitation.grants
        ]
    return {
        "tenant_name": tenant_name,
        "inviter_name": inviter_name,
        "email": invitation.email,
        "name": invitation.name,
        "grants": grants,
    }


def accept_invitation(*, token: str, password: str, name: str | None = None) -> User:
    """Accept an invitation: create the tenant-scoped User + queued Memberships + mark the
    invite accepted, atomically. Pre-auth lookup by token hash (like login, this rides the
    superuser/test path; production pre-auth RLS bootstrap is a separate concern)."""
    invitation = Invitation.objects.filter(token_hash=_hash_token(token)).first()
    if invitation is None:
        raise InvitationError("This invitation link is not valid.", status=410)
    if invitation.status == Invitation.Status.ACCEPTED:
        raise InvitationError("This invitation has already been used.", status=409)
    if invitation.status == Invitation.Status.REVOKED:
        raise InvitationError("This invitation has been revoked.", status=410)
    if invitation.is_expired:
        invitation.status = Invitation.Status.EXPIRED
        invitation.save(update_fields=["status", "updated_at"])
        raise InvitationError("This invitation has expired.", status=410)

    with transaction.atomic():
        with tenant_context(invitation.tenant_id):
            user = User.objects.create_user(
                email=invitation.email,
                name=(name or invitation.name or invitation.email),
                tenant=invitation.tenant,
                password=password,
            )
            for grant in invitation.grants:
                Membership.objects.create(
                    tenant=invitation.tenant, user=user,
                    project_id=grant["project_id"], role=grant["role"],
                )
            invitation.status = Invitation.Status.ACCEPTED
            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=["status", "accepted_at", "updated_at"])
    return user


# ── Password reset (P4.7-T3, J4) ────────────────────────────────────
def request_password_reset(*, email: str) -> str | None:
    """Issue a reset token for the account (if any) and email the link. Returns the raw
    token when a user exists, else None — the view responds 200 either way (no account
    enumeration)."""
    user = User.objects.filter(email__iexact=email.strip()).first()
    if user is None:
        return None
    raw, token_hash = _new_token()
    user.reset_token_hash = token_hash
    user.reset_token_expires = timezone.now() + RESET_TTL
    with tenant_context(user.tenant_id):
        user.save(update_fields=["reset_token_hash", "reset_token_expires", "updated_at"])
    send_password_reset_email(user, raw)
    return raw


def reset_password(*, token: str, password: str) -> User:
    """Consume a reset token and set the new password (single-use). Raises ResetError on an
    invalid or expired token."""
    user = User.objects.filter(reset_token_hash=_hash_token(token)).first()
    if (
        user is None
        or not user.reset_token_hash
        or user.reset_token_expires is None
        or timezone.now() >= user.reset_token_expires
    ):
        raise ResetError("This reset link is invalid or has expired.")
    with tenant_context(user.tenant_id):
        user.set_password(password)
        user.reset_token_hash = ""
        user.reset_token_expires = None
        user.save(update_fields=[
            "password", "reset_token_hash", "reset_token_expires", "updated_at",
        ])
    return user


# ── User & role management (P4.7-T4, J6) ────────────────────────────
# Two admin concepts (team decision, this phase):
#   • tenant-admin  = User.is_tenant_admin — tenant-wide; gates the admin REST surface;
#     can approve any gate in the tenant; a tenant must always keep ≥1 (guarded here).
#   • project-admin = Membership(role="admin") — per-project; can approve any gate on that
#     project (enforced in gates.services.decide_gate). Managed by the membership endpoints.
# A phase gate is therefore actionable when a holder of its required role OR an admin
# (project- or tenant-) exists — the coverage report below encodes exactly that.
_GATE_LABELS = {
    "product_owner": "planning gate",
    "architect": "architecture gate",
    "designer": "UX gate",
    "tech_lead": "build gate",
    "reviewer": "merge gate",
    "qa_lead": "testing gate",
    "security_engineer": "security gate",
    "devops": "deployment gate",
}


def _membership_summary(user: User) -> list[dict]:
    return [
        {
            "id": str(m.id), "project_id": str(m.project_id),
            "project_name": m.project.name, "role": m.role,
        }
        for m in user.memberships.select_related("project").all()
    ]


def list_tenant_users(tenant) -> list[dict]:
    """Every user in the tenant with their tenant-admin flag + per-project role grants
    (S-07 users table). Pending invitations are a separate list (see `Invitation`)."""
    users = (
        User.objects.filter(tenant_id=tenant.id)
        .order_by("name")
        .prefetch_related("memberships__project")
    )
    return [
        {
            "id": str(u.id),
            "name": u.name,
            "email": u.email,
            "status": "active" if u.is_active else "disabled",
            "is_tenant_admin": u.is_tenant_admin,
            "memberships": _membership_summary(u),
        }
        for u in users
    ]


def grant_membership(*, tenant, project, user_id: str, role: str) -> Membership:
    """Grant `role` on `project` to a tenant user (S-08 matrix toggle-on). Idempotency guard:
    a duplicate (user, project, role) is a 409. `role="admin"` grants project-admin."""
    user = User.objects.filter(id=user_id, tenant_id=tenant.id).first()
    if user is None:
        raise RoleError("Unknown user for this tenant.", status=404)
    if Membership.objects.filter(
        tenant_id=tenant.id, user_id=user_id, project_id=project.id, role=role
    ).exists():
        raise RoleError("This user already holds that role on this project.", status=409)
    return Membership.objects.create(
        tenant=tenant, user=user, project=project, role=role
    )


def revoke_membership(*, tenant, project, membership_id: str) -> None:
    """Remove a project-role grant (S-08 matrix toggle-off). The tenant-admin population is
    protected on the is_tenant_admin toggle, not here — project-role grants carry no guard."""
    membership = Membership.objects.filter(
        id=membership_id, tenant_id=tenant.id, project_id=project.id
    ).first()
    if membership is None:
        raise RoleError("Unknown membership for this project.", status=404)
    membership.delete()


def set_tenant_admin(*, tenant, user_id: str, is_admin: bool) -> User:
    """Promote/demote a user's tenant-admin flag (S-08 'Admin' toggle). Guard: a tenant must
    always keep at least one tenant-admin — demoting the last one (incl. your own, when
    you're the last) is a 409."""
    user = User.objects.filter(id=user_id, tenant_id=tenant.id).first()
    if user is None:
        raise RoleError("Unknown user for this tenant.", status=404)
    if not is_admin and user.is_tenant_admin:
        remaining = (
            User.objects.filter(tenant_id=tenant.id, is_tenant_admin=True)
            .exclude(id=user_id)
            .exists()
        )
        if not remaining:
            raise RoleError(
                "This is the tenant's only admin — promote another member before "
                "removing admin.",
                status=409,
            )
    user.is_tenant_admin = is_admin
    user.save(update_fields=["is_tenant_admin", "updated_at"])
    return user


def project_role_coverage(*, tenant, project) -> dict:
    """Gate-role coverage for a project (S-08). For each role that gates a phase: its holders,
    whether it's directly covered, and whether its gate is BLOCKED — i.e. no holder AND no
    admin fallback (a project- or tenant-admin can approve any gate). `note` carries the
    screen's warning copy; `admin_fallback` lets the UI distinguish a hard block from an
    admin-covered gap."""
    admin_fallback = (
        Membership.objects.filter(
            tenant_id=tenant.id, project_id=project.id, role=Role.ADMIN
        ).exists()
        or User.objects.filter(tenant_id=tenant.id, is_tenant_admin=True).exists()
    )
    rows = []
    for role in gate_roles():
        holders = [
            {"user_id": str(m.user_id), "name": m.user.name}
            for m in Membership.objects.filter(
                tenant_id=tenant.id, project_id=project.id, role=role
            ).select_related("user")
        ]
        covered = bool(holders)
        gate_blocked = not covered and not admin_fallback
        label = _GATE_LABELS.get(role, f"{role} gate")
        # Human-readable role name in the copy — never the raw key (e.g. "Product Owner",
        # not "product_owner"). Bugs.xlsx: coverage notes leaked raw role keys.
        role_label = Role(role).label
        if covered:
            note = None
        elif admin_fallback:
            note = f"no {role_label} assigned — an admin can approve the {label}"
        else:
            note = f"{label} unactionable — no {role_label}"
        rows.append({
            "role": role,
            "holders": holders,
            "covered": covered,
            "gate_blocked": gate_blocked,
            "note": note,
        })
    return {"admin_fallback": admin_fallback, "roles": rows}
