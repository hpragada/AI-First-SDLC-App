"""Multi-repo project model (Phase 4 / D5) — one project, N repositories.

A project owns 0..N `Repository` rows (frontend / backend / service / …). `add_repository`
registers a repo under a project (idempotent by name) and keeps `Project.repo_topology`
consistent with the repo count: 0–1 → single, 2 → split, ≥3 → multi. The registry,
traceability, and Knowledge Index stay project-scoped shared memory across these repos; only
the *manifest* is scoped per repo (see `mcp_platform_state.tools.get_context`).

REST layer (P4.7-T7, backs S-13): `repositories_for`/`add_repository`/`remove_repository`/
`set_default_repository` back `GET/POST/DELETE /api/projects/{id}/repositories/` +
`.../set-default/`. `require_repo_manage_role` gates the mutating ones (tech_lead/admin, or a
tenant-admin fallback — the same two-tier model as `gates.services.decide_gate`).
"""
from __future__ import annotations

from mcp_platform_state import tools

from apps.base import Role
from apps.integrations.models import IntegrationConnection
from apps.projects.models import Project, Repository
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Membership, User


class RepositoryError(Exception):
    """A repository-management operation was rejected. `status` maps to the HTTP code
    (403 wrong role, 404 unknown repository)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def require_repo_manage_role(*, tenant_id, project_id, user_id,
                             what: str = "manage this project's repositories") -> None:
    """Role check for add/remove/set-default (S-13): the acting user must hold `tech_lead`
    or project-admin on this project, or be a tenant-admin fallback.

    `what` finishes the refusal sentence, because the screen puts that sentence in front of the
    person verbatim (S.No 212). It used to name the role by its internal key — "You need the
    tech_lead or admin role…" — which is our word, not theirs."""
    if user_id and Membership.objects.filter(
        tenant_id=tenant_id, user_id=user_id, project_id=project_id,
        role__in=[Role.TECH_LEAD, Role.ADMIN],
    ).exists():
        return
    if user_id and User.objects.filter(
        id=user_id, tenant_id=tenant_id, is_tenant_admin=True
    ).exists():
        return
    raise RepositoryError(f"Only a tech lead or an admin can {what}.", status=403)


def _codehost_status(tenant_id) -> str:
    """Repos ride on the tenant's single `codehost` capability (capabilities-not-vendors,
    P4.7-T6) — "connected" once that capability is wired + configured. Tenant-wide, so every
    repo row in a project shares the same status."""
    conn = IntegrationConnection.objects.filter(
        tenant_id=tenant_id, capability="codehost"
    ).first()
    return "connected" if conn is not None and conn.is_configured else "unlinked"


def _topology_for(count: int) -> str:
    if count >= 3:
        return Project.RepoTopology.MULTI
    if count == 2:
        return Project.RepoTopology.SPLIT
    return Project.RepoTopology.SINGLE


def _recompute_topology(project: Project) -> str:
    """Set `repo_topology` from the project's current repo count; returns the new value."""
    count = Repository.objects.filter(
        tenant_id=project.tenant_id, project_id=project.id).count()
    topology = _topology_for(count)
    if project.repo_topology != topology:
        project.repo_topology = topology
        project.save(update_fields=["repo_topology", "updated_at"])
    return topology


def add_repository(*, tenant_id, project_id, name, role="", default_base="main",
                   connector="", scopes=None, stack_overrides=None, provenance=None,
                   preview_url="") -> dict:
    """Register a repo under a project (idempotent by name) and reconcile the topology. The
    first repo registered on a project becomes its default (S-13) until reassigned.

    Returns the repository + whether it was created and the resulting `repo_topology`."""
    with tenant_context(tenant_id):
        project = Project.objects.get(id=project_id, tenant_id=tenant_id)
        is_first = not Repository.objects.filter(
            tenant_id=tenant_id, project_id=project_id).exists()
        repo, created = Repository.objects.get_or_create(
            tenant_id=tenant_id, project=project, name=name,
            defaults={"role": role, "default_base": default_base, "connector": connector,
                      "scopes": scopes or {}, "stack_overrides": stack_overrides or {},
                      "provenance": provenance or {}, "is_default": is_first,
                      "preview_url": preview_url or ""},
        )
        topology = _recompute_topology(project)
        if created:
            tools.log_event(tenant_id, "platform", "repository.registered", "repository",
                            str(repo.id), {"name": name, "role": role, "topology": topology})
    return {"repository_id": str(repo.id), "name": repo.name, "role": repo.role,
            "created": created, "repo_topology": topology, "is_default": repo.is_default}


def repositories_for(*, tenant_id, project_id) -> list[dict]:
    """The project's repositories (shared-memory siblings in the cross-repo DAG), in the S-13
    wire shape: `id/name/role/default_base/status/is_default` + `preview_url` (P3-09bR)."""
    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        status = _codehost_status(tenant_id)
        return [
            {"id": str(r.id), "name": r.name, "role": r.role,
             "default_base": r.default_base, "connector": r.connector,
             "status": status, "is_default": r.is_default, "preview_url": r.preview_url}
            for r in Repository.objects.filter(
                tenant_id=tenant_id, project_id=project_id).order_by("created_at")
        ]


def update_repository(*, tenant_id, project_id, repository_id, preview_url=None) -> dict:
    """Edit an existing repo's settings (S-13 follow-up). Currently `preview_url` — the manual
    app-exploration target for 09b. Only the fields passed (non-None) are changed; others are left
    untouched. 404s if the repo isn't this project's."""
    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        try:
            repo = Repository.objects.get(
                id=repository_id, tenant_id=tenant_id, project_id=project_id)
        except Repository.DoesNotExist as exc:
            raise RepositoryError("Unknown repository for this project.", status=404) from exc
        fields = []
        if preview_url is not None:
            repo.preview_url = preview_url
            fields.append("preview_url")
        if fields:
            repo.save(update_fields=[*fields, "updated_at"])
            tools.log_event(tenant_id, "platform", "repository.updated", "repository",
                            str(repo.id), {"fields": fields})
    return {"id": str(repo.id), "name": repo.name, "preview_url": repo.preview_url}


def remove_repository(*, tenant_id, project_id, repository_id) -> dict:
    """Remove a repo (S-13 "Remove") and reconcile topology + default. If the removed repo
    was the default and others remain, the oldest remaining repo is promoted — a project with
    any repos always has exactly one default."""
    with tenant_context(tenant_id):
        project = Project.objects.get(id=project_id, tenant_id=tenant_id)
        try:
            repo = Repository.objects.get(
                id=repository_id, tenant_id=tenant_id, project_id=project_id)
        except Repository.DoesNotExist as exc:
            raise RepositoryError("Unknown repository for this project.", status=404) from exc
        was_default, name = repo.is_default, repo.name
        repo.delete()
        topology = _recompute_topology(project)
        if was_default:
            successor = Repository.objects.filter(
                tenant_id=tenant_id, project_id=project_id
            ).order_by("created_at").first()
            if successor is not None:
                successor.is_default = True
                successor.save(update_fields=["is_default", "updated_at"])
        tools.log_event(tenant_id, "platform", "repository.removed", "repository",
                        str(repository_id), {"name": name, "topology": topology})
    return {"repo_topology": topology}


def set_default_repository(*, tenant_id, project_id, repository_id) -> dict:
    """Mark one repo as the project's default base (S-13 "Set default") — unsets every other
    repo's flag so exactly one stays default."""
    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)
        try:
            repo = Repository.objects.get(
                id=repository_id, tenant_id=tenant_id, project_id=project_id)
        except Repository.DoesNotExist as exc:
            raise RepositoryError("Unknown repository for this project.", status=404) from exc
        Repository.objects.filter(
            tenant_id=tenant_id, project_id=project_id
        ).exclude(id=repo.id).update(is_default=False)
        repo.is_default = True
        repo.save(update_fields=["is_default", "updated_at"])
    return {"id": str(repo.id), "name": repo.name, "is_default": True}
