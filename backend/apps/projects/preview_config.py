"""Preview-start config resolution (P3-09bR-1 / spec §1).

The single source of truth for *how a build brings the app up* so 09b's Live Application
Exploration + E2E have a live target (D7). Repo-first (the served thing is a repo — the frontend
repo runs the UI), ProjectProfile as the single-serve-target fallback. `{}` when neither is set —
the caller (the companion, for a test-automation build) turns that into a **fail-loud**, never a
silent no-locator run.
"""
from __future__ import annotations

from apps.tenancy.context import tenant_context

from .models import ProjectProfile, Repository

# The keys a preview-start config may carry — used to normalize/validate without inventing values.
PREVIEW_START_KEYS = ("command", "port", "health_path", "ready_timeout_s", "ready_log")


def resolve_preview_start(*, tenant_id, project_id, repo_name: str | None) -> dict:
    """The effective preview-start config for a build: `Repository.preview_start` (matched by
    `repo_name`) if non-empty, else `ProjectProfile.preview_start`, else `{}`. Returns a plain copy
    so callers can mutate/ship it freely. Never raises on 'unset' — emptiness is a valid answer the
    caller decides how to treat (fail-loud only for phases that need a preview)."""
    with tenant_context(tenant_id):
        if repo_name:
            repo = (
                Repository.objects
                .filter(tenant_id=tenant_id, project_id=project_id, name=repo_name)
                .first()
            )
            if repo and repo.preview_start:
                return dict(repo.preview_start)
        profile = (
            ProjectProfile.objects
            .filter(tenant_id=tenant_id, project_id=project_id)
            .first()
        )
        if profile and profile.preview_start:
            return dict(profile.preview_start)
    return {}


def resolve_preview_url(*, tenant_id, project_id, repo_name: str | None) -> str:
    """The manual preview URL for a build: `Repository.preview_url` (matched by `repo_name`) if set,
    else `""`. This is the "point at an already-running app" path — when non-empty the companion
    explores it directly and skips auto-start (`preview_start`). One URL per repo; empty is a valid
    answer the caller falls back on (auto-start, then fail-loud)."""
    if not repo_name:
        return ""
    with tenant_context(tenant_id):
        repo = (
            Repository.objects
            .filter(tenant_id=tenant_id, project_id=project_id, name=repo_name)
            .first()
        )
        return (repo.preview_url or "") if repo else ""
