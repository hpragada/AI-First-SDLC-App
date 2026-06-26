"""Multi-repo project model (Phase 4 / D5) — one project, N repositories.

A project owns 0..N `Repository` rows (frontend / backend / service / …). `add_repository`
registers a repo under a project (idempotent by name) and keeps `Project.repo_topology`
consistent with the repo count: 0–1 → single, 2 → split, ≥3 → multi. The registry,
traceability, and Knowledge Index stay project-scoped shared memory across these repos; only
the *manifest* is scoped per repo (see `mcp_platform_state.tools.get_context`).
"""
from __future__ import annotations

from mcp_platform_state import tools

from apps.projects.models import Project, Repository
from apps.tenancy.context import tenant_context


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
                   connector="", scopes=None, stack_overrides=None, provenance=None) -> dict:
    """Register a repo under a project (idempotent by name) and reconcile the topology.

    Returns the repository + whether it was created and the resulting `repo_topology`."""
    with tenant_context(tenant_id):
        project = Project.objects.get(id=project_id, tenant_id=tenant_id)
        repo, created = Repository.objects.get_or_create(
            tenant_id=tenant_id, project=project, name=name,
            defaults={"role": role, "default_base": default_base, "connector": connector,
                      "scopes": scopes or {}, "stack_overrides": stack_overrides or {},
                      "provenance": provenance or {}},
        )
        topology = _recompute_topology(project)
        if created:
            tools.log_event(tenant_id, "platform", "repository.registered", "repository",
                            str(repo.id), {"name": name, "role": role, "topology": topology})
    return {"repository_id": str(repo.id), "name": repo.name, "role": repo.role,
            "created": created, "repo_topology": topology}


def repositories_for(*, tenant_id, project_id) -> list[dict]:
    """The project's repositories (shared-memory siblings in the cross-repo DAG)."""
    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        return [
            {"repository_id": str(r.id), "name": r.name, "role": r.role,
             "default_base": r.default_base, "connector": r.connector}
            for r in Repository.objects.filter(
                tenant_id=tenant_id, project_id=project_id).order_by("created_at")
        ]
