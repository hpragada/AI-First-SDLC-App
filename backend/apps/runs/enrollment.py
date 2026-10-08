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
    """Disconnect the machine this enrollment belongs to. Returns True if anything changed.

    2026-10-08: this used to revoke the ONE row it was given. A machine is every active
    enrollment the Connect Machine card groups together (same developer, same label — or, for
    the label-less tokens the web app generates, same project; see `list_developer_enrollments`),
    and each "Generate token" adds another. So Disconnect cancelled the newest key and left the
    older ones working: the page then showed an older key's last heartbeat as "last seen", and a
    companion started with any of those keys could still pick up phases. It now revokes the
    whole group, which is what the person clicking Disconnect meant.

    The moment is recorded as a ledger event, which `last_disconnect` reads back so the page can
    say when it happened on any later visit. An event rather than the row's `updated_at`: revokes
    before this change left no trace of their time, and an event either exists or does not — there
    is no old row whose timestamp could be mistaken for a disconnect."""
    from mcp_platform_state.tools import log_event

    from apps.runs.models import RunnerEnrollment
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        row = RunnerEnrollment.objects.filter(id=enrollment_id, tenant_id=tenant_id).first()
        if row is None:
            return False
        group = RunnerEnrollment.objects.filter(
            tenant_id=tenant_id, developer_id=row.developer_id, label=row.label,
            status=RunnerEnrollment.Status.ACTIVE,
        )
        if not row.label:
            group = group.filter(project_id=row.project_id)
        project_ids = sorted({str(p) for p in group.values_list("project_id", flat=True)})
        changed = group.update(status=RunnerEnrollment.Status.REVOKED)
    if changed:
        payload = {"developer_id": str(row.developer_id) if row.developer_id else None,
                   "machine": row.label, "keys_revoked": changed}
        for project_id in project_ids:
            log_event(str(tenant_id), "user", "runner.disconnected", "runner_enrollment",
                      str(row.id), {**payload, "project_id": project_id})
    return bool(changed)


def last_disconnect(*, tenant_id, developer_id, project_id) -> str | None:
    """When this developer's machine was last disconnected from this project (ISO, UTC), or None
    when there is no recorded disconnect (including every one from before 2026-10-08)."""
    from apps.ledger.models import Event
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        event = (
            Event.objects.filter(
                tenant_id=tenant_id, action="runner.disconnected",
                payload__project_id=str(project_id),
                payload__developer_id=str(developer_id) if developer_id else None,
            )
            .order_by("-ts")
            .first()
        )
    return event.ts.isoformat() if event else None


def list_developer_enrollments(*, tenant_id, developer_id) -> list[dict]:
    """P4.7-T11 (backs S-05 checklist tick, S-06 connect-machine): the calling developer's
    **active** enrollments, grouped by machine (`label`) — one `RunnerEnrollment` row exists
    per project a machine is bound to, so a machine connected to several projects surfaces as
    one entry with `projects: [...]`. `online` is derived from the freshest `last_seen` across
    the group against `ONLINE_THRESHOLD`; a revoked enrollment (disconnected) simply drops out.
    `age_s` rides along for the UI's intermediate "checking..." band — see the comment on it."""
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
        # Labelled machines group by label (one card spanning their projects). Label-less
        # enrollments — the default when a token is generated from the web app — group by
        # PROJECT instead of by id, so generating a fresh token for the same project (or
        # re-connecting) collapses into ONE card rather than N phantom "machines" that each
        # look offline (Bugs.xlsx row 61 / RC-4). The most-recently-seen row represents it.
        key = e.label or f"project:{e.project_id}"
        if key not in groups:
            groups[key] = {"id": str(e.id), "machine": e.label, "last_seen": e.last_seen,
                           "projects": []}
            order.append(key)
        g = groups[key]
        if e.last_seen and (g["last_seen"] is None or e.last_seen > g["last_seen"]):
            g["last_seen"] = e.last_seen
            g["id"] = str(e.id)  # representative row = the group's most recently active one
        if not any(p["project_id"] == str(e.project_id) for p in g["projects"]):
            g["projects"].append({"project_id": str(e.project_id), "project_name": e.project.name})

    now = timezone.now()
    out = []
    for key in order:
        g = groups[key]
        last_seen = g["last_seen"]
        # `age_s` (whole seconds since this machine last called in, None when it never has) is
        # computed HERE rather than subtracted in the browser, and that is not a convenience.
        # The UI shows an intermediate "checking..." state once a companion has gone quiet but
        # is not yet past ONLINE_THRESHOLD, which is a judgement about elapsed time — and a
        # browser clock off by minutes would paint a healthy companion as dying, or a dead one
        # as fine. `online` was already immune because the server decides it; this extends the
        # same immunity to the band inside it. Purely additive: callers that ignore it behave
        # exactly as before.
        out.append({
            "id": g["id"], "machine": g["machine"],
            "last_seen": last_seen.isoformat() if last_seen else None,
            "age_s": int((now - last_seen).total_seconds()) if last_seen else None,
            "online": bool(last_seen and (now - last_seen) <= ONLINE_THRESHOLD),
            "projects": g["projects"],
        })
    out.sort(key=lambda r: r["last_seen"] or "", reverse=True)
    return out
