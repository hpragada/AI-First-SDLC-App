"""Transactional auth email (P4.7-T3).

Thin wrappers over Django's mail framework — the pluggable seam is `EMAIL_BACKEND`
(SendGrid over SMTP when `SENDGRID_API_KEY` is set, otherwise the console backend, which
prints to the server terminal), so nothing here takes a hard mail dependency. The raw token
is passed in and embedded in a frontend link; it is never logged or stored (only its hash
lives in the DB).

2026-10-09 (team-approved mockup 1): plain words for a person — who invited them, to which
project and role, one button, the date the link stops working (a date, not "UTC"), and what
to do if they weren't expecting it. Each email carries a plain-text body and a simple HTML one.
"""
from __future__ import annotations

from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _frontend_url(path: str) -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}{path}"


def _day(dt) -> str:
    """'15 Oct 2026' — the same month wording the app's screens use."""
    return f"{dt.day} {MONTHS[dt.month - 1]} {dt.year}"


def _html(paragraphs: list[str], button: tuple[str, str], footer: str) -> str:
    label, link = button
    body = "".join(
        f'<p style="margin:0 0 16px;font-size:15px;line-height:1.5;color:#1f2937">{p}</p>'
        for p in paragraphs
    )
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;'
        'padding:24px">'
        f"{body}"
        f'<p style="margin:24px 0"><a href="{escape(link)}" style="background:#f26a21;color:#ffffff;'
        'padding:12px 20px;border-radius:6px;text-decoration:none;font-weight:bold;'
        f'display:inline-block">{escape(label)}</a></p>'
        f'<p style="margin:0;font-size:13px;line-height:1.5;color:#6b7280">{footer}</p>'
        "</div>"
    )


def _send(*, subject: str, text: str, html: str, to: str) -> None:
    msg = EmailMultiAlternatives(subject=subject, body=text, from_email=None, to=[to])
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)


def _and_list(items: list[str]) -> str:
    """'A', 'A and B', 'A, B and C' — the same rule as the app's screens (roles.ts)."""
    if len(items) <= 1:
        return items[0] if items else ""
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _invite_details(invitation) -> tuple[str, str | None]:
    """(inviter name, 'PeopleDesk as Engineer and Architect') — every role the invite grants,
    in the order the admin added them (team-approved 2026-10-09; it named only the first).
    Read inside the invite's own tenant (RLS)."""
    from apps.base import Role
    from apps.projects.models import Project
    from apps.tenancy.context import tenant_context

    with tenant_context(invitation.tenant_id):
        inviter = (invitation.invited_by.name if invitation.invited_by_id else "") or "Your team"
        if not invitation.grants:
            return inviter, None
        names = {
            str(p.id): p.name
            for p in Project.objects.filter(id__in=[g["project_id"] for g in invitation.grants])
        }
        by_project: dict[str, list[str]] = {}
        for g in invitation.grants:
            try:
                role = Role(g["role"]).label
            except ValueError:
                role = g["role"]
            roles = by_project.setdefault(names.get(str(g["project_id"]), ""), [])
            if role not in roles:
                roles.append(role)
        if len(by_project) == 1:  # "PeopleDesk as Engineer and Architect"
            project, roles = next(iter(by_project.items()))
            return inviter, (f"{project} as {_and_list(roles)}" if project
                             else f"as {_and_list(roles)}")
        # Several projects, worded as the screens do (mockup D): "as Engineer on PeopleDesk
        # and as Designer on Payroll".
        return inviter, _and_list([
            f"as {_and_list(roles)} on {project}" if project else f"as {_and_list(roles)}"
            for project, roles in by_project.items()
        ])


def send_invitation_email(invitation, raw_token: str) -> None:
    """Email an invitee the accept link (S-03)."""
    link = _frontend_url(f"/accept-invite?token={raw_token}")
    workspace = invitation.tenant.name
    inviter, joining = _invite_details(invitation)
    subject = f"{inviter} invited you to {workspace}"
    second = (
        f"You'll join {joining}. Set a password to get started."
        if joining else "Set a password to get started."
    )
    footer = (
        f"This invite works until {_day(invitation.expires_at)}. "
        "If you weren't expecting it, you can ignore this email."
    )
    text = (
        f"{subject}.\n\n{second}\n\nJoin the workspace:\n{link}\n\n{footer}\n"
    )
    html = _html(
        [f"<strong>{escape(subject)}</strong>", escape(second)],
        ("Join the workspace", link),
        escape(footer),
    )
    _send(subject=subject, text=text, html=html, to=invitation.email)


def send_password_reset_email(user, raw_token: str) -> None:
    """Email a user a password-reset link (S-04)."""
    # 2026-10-09: was "/reset-password", a page that does not exist (the app's is "/reset"), so
    # every reset link fell through to the dashboard redirect and never reached the form.
    link = _frontend_url(f"/reset?token={raw_token}")
    subject = "Reset your SDLC app password"
    first = "We got a request to reset your password. Choose a new one with the button below."
    footer = (
        "The link works for one hour. If you didn't ask for this, you can ignore this email — "
        "your password stays the same."
    )
    text = f"{first}\n\nSet a new password:\n{link}\n\n{footer}\n"
    html = _html([escape(first)], ("Set a new password", link), escape(footer))
    _send(subject=subject, text=text, html=html, to=user.email)
