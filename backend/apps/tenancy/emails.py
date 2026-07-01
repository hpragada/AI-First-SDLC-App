"""Transactional auth email (P4.7-T3).

Thin wrappers over Django's mail framework — the pluggable seam is `EMAIL_BACKEND`
(console backend in dev, a real SMTP/API backend in prod), so nothing here takes a
hard mail dependency. The raw token is passed in and embedded in a frontend link; it
is never logged or stored (only its hash lives in the DB).
"""
from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail


def _frontend_url(path: str) -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}{path}"


def send_invitation_email(invitation, raw_token: str) -> None:
    """Email an invitee the accept link (S-03)."""
    link = _frontend_url(f"/accept-invite?token={raw_token}")
    send_mail(
        subject=f"You've been invited to {invitation.tenant.name}",
        message=(
            f"You've been invited to join {invitation.tenant.name} on the SDLC platform.\n\n"
            f"Accept your invitation and set a password:\n{link}\n\n"
            f"This link expires on {invitation.expires_at:%Y-%m-%d %H:%M UTC}."
        ),
        from_email=None,  # DEFAULT_FROM_EMAIL
        recipient_list=[invitation.email],
        fail_silently=False,
    )


def send_password_reset_email(user, raw_token: str) -> None:
    """Email a user a password-reset link (S-04)."""
    link = _frontend_url(f"/reset-password?token={raw_token}")
    send_mail(
        subject="Reset your SDLC platform password",
        message=(
            "We received a request to reset your password.\n\n"
            f"Set a new password:\n{link}\n\n"
            "If you didn't request this, you can safely ignore this email. "
            "The link expires shortly."
        ),
        from_email=None,  # DEFAULT_FROM_EMAIL
        recipient_list=[user.email],
        fail_silently=False,
    )
