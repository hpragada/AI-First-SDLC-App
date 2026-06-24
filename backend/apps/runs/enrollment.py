"""Local-companion runner enrollment + auth (Phase-2 §3).

A developer enrolls a companion for a tenant+project+repos and receives a **one-time
token**; only its SHA-256 hash is stored (`enroll_token_hash`). The companion then presents
that token (plus its tenant) on every call; `authenticate_runner` resolves it back to the
active enrollment. The tenant is therefore established **server-side from the enrollment**,
never trusted from the agent — RLS scoping stays on the platform (#6).
"""
from __future__ import annotations

import hashlib
import secrets


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def enroll_runner(*, tenant_id, project_id, developer_id=None, label="", repos=None):
    """Create an active enrollment; return (enrollment, raw_token). The token is shown
    once to the caller and never recoverable from storage."""
    from apps.runs.models import RunnerEnrollment
    from apps.tenancy.context import tenant_context

    token = secrets.token_urlsafe(32)
    with tenant_context(tenant_id):
        enrollment = RunnerEnrollment.objects.create(
            tenant_id=tenant_id, project_id=project_id, developer_id=developer_id,
            label=label, repos=list(repos or []), enroll_token_hash=_hash(token),
            status=RunnerEnrollment.Status.ACTIVE,
        )
    return enrollment, token


def authenticate_runner(*, tenant_id, token):
    """Resolve an active enrollment by (tenant, token-hash), or None. Updates last_seen.
    The tenant scopes the lookup, so a token for tenant A presented as tenant B fails."""
    from django.utils import timezone

    from apps.runs.models import RunnerEnrollment
    from apps.tenancy.context import tenant_context

    if not token or not tenant_id:
        return None
    digest = _hash(token)
    with tenant_context(tenant_id):
        enrollment = (
            RunnerEnrollment.objects
            .filter(tenant_id=tenant_id, enroll_token_hash=digest,
                    status=RunnerEnrollment.Status.ACTIVE)
            .first()
        )
        if enrollment is not None:
            now = timezone.now()
            RunnerEnrollment.objects.filter(id=enrollment.id, tenant_id=tenant_id).update(
                last_seen=now
            )
            enrollment.last_seen = now  # reflect the write on the returned instance
    return enrollment


def revoke_runner(*, tenant_id, enrollment_id) -> bool:
    """Revoke an enrollment (its token stops authenticating). Returns True if one changed."""
    from apps.runs.models import RunnerEnrollment
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        changed = (
            RunnerEnrollment.objects
            .filter(id=enrollment_id, tenant_id=tenant_id)
            .update(status=RunnerEnrollment.Status.REVOKED)
        )
    return bool(changed)
