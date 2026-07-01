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

from apps.registry.catalog import seed_agent_specs
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
