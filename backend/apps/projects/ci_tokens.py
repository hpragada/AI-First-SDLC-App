"""Per-project CI ingest tokens (P3-09bX-1 / spec §1).

The client's CI posts automated-test results (JUnit) to the ingestion endpoint authenticated by a
per-project token. Only the SHA-256 hash is stored — the secret is returned **once** on issue and
never recoverable. Scoped to results ingestion; distinct from a runner enrollment (CI is not a
Claude Code companion). The tenant+project scope every lookup, so a token issued for one project
cannot post to another. Mirrors `apps.runs.enrollment` for the token lifecycle.
"""
from __future__ import annotations

import hashlib
import secrets


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_ci_token(*, tenant_id, project_id, label: str = "", created_by_id=None):
    """Create an active CI token; return (token_row, raw_token). The secret is shown once to the
    caller and is never recoverable from storage (only its hash is kept)."""
    from apps.projects.models import ProjectCIToken
    from apps.tenancy.context import tenant_context

    token = secrets.token_urlsafe(32)
    with tenant_context(tenant_id):
        row = ProjectCIToken.objects.create(
            tenant_id=tenant_id, project_id=project_id, label=label,
            token_hash=_hash(token), created_by_id=created_by_id,
            status=ProjectCIToken.Status.ACTIVE,
        )
    return row, token


def authenticate_ci_token(*, tenant_id, project_id, token):
    """Resolve an active CI token by (tenant, project, token-hash), or None. Touches last_used_at.
    The tenant+project scope the lookup, so a token issued for project A presented against B fails —
    and a revoked token stops authenticating."""
    from django.utils import timezone

    from apps.projects.models import ProjectCIToken
    from apps.tenancy.context import tenant_context

    if not token or not tenant_id or not project_id:
        return None
    digest = _hash(token)
    with tenant_context(tenant_id):
        row = (
            ProjectCIToken.objects
            .filter(tenant_id=tenant_id, project_id=project_id, token_hash=digest,
                    status=ProjectCIToken.Status.ACTIVE)
            .first()
        )
        if row is not None:
            now = timezone.now()
            ProjectCIToken.objects.filter(id=row.id, tenant_id=tenant_id).update(last_used_at=now)
            row.last_used_at = now      # reflect the write on the returned instance
    return row


def revoke_ci_token(*, tenant_id, token_id) -> bool:
    """Revoke a CI token (it stops authenticating). Returns True if one changed."""
    from apps.projects.models import ProjectCIToken
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        changed = (
            ProjectCIToken.objects
            .filter(id=token_id, tenant_id=tenant_id)
            .update(status=ProjectCIToken.Status.REVOKED)
        )
    return bool(changed)


def list_ci_tokens(*, tenant_id, project_id):
    """The project's CI tokens (newest first) — metadata only; the secret is never stored."""
    from apps.projects.models import ProjectCIToken
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        return list(
            ProjectCIToken.objects
            .filter(tenant_id=tenant_id, project_id=project_id)
            .order_by("-created_at")
        )
