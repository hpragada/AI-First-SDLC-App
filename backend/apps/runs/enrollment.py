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
from datetime import timedelta

# A machine is "online" if any of its enrollments have called in within this window —
# comfortably above the companion daemon's default 5s poll interval (P4.7-T11, backs S-05/S-06).
ONLINE_THRESHOLD = timedelta(minutes=2)


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


def list_developer_enrollments(*, tenant_id, developer_id) -> list[dict]:
    """P4.7-T11 (backs S-05 checklist tick, S-06 connect-machine): the calling developer's
    **active** enrollments, grouped by machine (`label`) — one `RunnerEnrollment` row exists
    per project a machine is bound to, so a machine connected to several projects surfaces as
    one entry with `projects: [...]`. `online` is derived from the freshest `last_seen` across
    the group against `ONLINE_THRESHOLD`; a revoked enrollment (disconnected) simply drops out."""
    from django.utils import timezone

    from apps.runs.models import RunnerEnrollment
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        rows = list(
            RunnerEnrollment.objects
            .filter(tenant_id=tenant_id, developer_id=developer_id,
                    status=RunnerEnrollment.Status.ACTIVE)
            .select_related("project")
        )

    groups: dict[str, dict] = {}
    order: list[str] = []
    for e in rows:
        key = e.label or str(e.id)
        if key not in groups:
            groups[key] = {"id": str(e.id), "machine": e.label, "last_seen": e.last_seen,
                           "projects": []}
            order.append(key)
        g = groups[key]
        if e.last_seen and (g["last_seen"] is None or e.last_seen > g["last_seen"]):
            g["last_seen"] = e.last_seen
            g["id"] = str(e.id)  # representative row = the group's most recently active one
        g["projects"].append({"project_id": str(e.project_id), "project_name": e.project.name})

    now = timezone.now()
    out = []
    for key in order:
        g = groups[key]
        last_seen = g["last_seen"]
        out.append({
            "id": g["id"], "machine": g["machine"],
            "last_seen": last_seen.isoformat() if last_seen else None,
            "online": bool(last_seen and (now - last_seen) <= ONLINE_THRESHOLD),
            "projects": g["projects"],
        })
    out.sort(key=lambda r: r["last_seen"] or "", reverse=True)
    return out
