"""Preview-start config resolution (P3-09bR-1 / spec §1).

The single source of truth for *how a build brings the app up* so 09b's Live Application
Exploration + E2E have a live target (D7). Repo-first (the served thing is a repo — the frontend
repo runs the UI), ProjectProfile as the single-serve-target fallback. `{}` when neither is set —
the caller (the companion, for a test-automation build) turns that into a **fail-loud**, never a
silent no-locator run.
"""
from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class ResolvedAppUrl:
    """Where a project's application answers, and how the platform came to think so.

    `source` exists so a screen can say *"from the repository acme/web"* next to a pre-filled
    field rather than presenting an address out of nowhere, and `reason` so a refusal can name
    the thing to go and set. Exactly one of `url` / `reason` is ever non-empty.
    """

    url: str = ""
    source: str = ""
    reason: str = ""


#: What to tell someone when the platform holds no address for this project at all.
NO_APP_URL = (
    "this project has no application address on record, so there is nothing to check. Set the "
    "repository's Preview URL to where the running application answers (e.g. "
    "http://127.0.0.1:5173), or give an address for this pass."
)


@dataclass(frozen=True)
class ResolvedRepo:
    """Which repository an audit runs FROM. Exactly one of `name` / `reason` is non-empty."""

    name: str = ""
    reason: str = ""


def resolve_audit_repo(*, tenant_id, project_id) -> ResolvedRepo:
    """The repository whose local clone a baseline audit is run from (task 8a).

    **Why an audit needs a folder at all**, when it only visits URLs: the browser and the page
    scanner are resolved out of the audited project's own `node_modules`, so that the version
    stamped on every scan is the version that project actually uses. No folder, nowhere to
    resolve them from, and the platform never installs anything into a client's project.

    **The same repository the address comes from, by construction.** This walks the identical
    order as `resolve_app_base_url` — default repo, else the only one claiming to serve the
    application — because two separate rules for "which project is this" could disagree and
    audit one application from inside another's folder. A single repo with no preview URL is
    still the answer: it cannot be the wrong one.

    Never raises. When no single repository can be named, `reason` says what to go and set, and
    the machine that asked reports it against the audit rather than guessing a folder.
    """
    with tenant_context(tenant_id):
        repos = list(
            Repository.objects
            .filter(tenant_id=tenant_id, project_id=project_id)
            .order_by("-is_default", "name")
        )

    if not repos:
        return ResolvedRepo(reason=(
            "this project has no repository registered, so there is no project folder to run "
            "the audit from. Register the repository that serves the application first."
        ))

    default = next((r for r in repos if r.is_default), None)
    if default is not None:
        return ResolvedRepo(name=default.name or "")

    serving = [r for r in repos if r.preview_url]
    if len(serving) == 1:
        return ResolvedRepo(name=serving[0].name or "")
    if len(repos) == 1:
        return ResolvedRepo(name=repos[0].name or "")

    named = ", ".join(r.name or "(unnamed)" for r in repos)
    return ResolvedRepo(reason=(
        f"this project has several repositories — {named} — and none is marked as the default, "
        f"so the platform cannot tell which one serves the application. Mark the default "
        f"repository, or set a Preview URL on the one that does."
    ))


def resolve_app_base_url(*, tenant_id, project_id) -> ResolvedAppUrl:
    """Where this project's application is reachable, without anyone typing it again (B3).

    **This is an application address, never a repository address.** A repo's git identity is its
    `name`/`code_host_ref`; `preview_url` is the separate fact "the application this repo serves
    answers here". It lives on the repo because the served thing IS a repo — the frontend repo
    runs the UI and a backend-only repo has no UI to preview.

    The order, and why each step is reading data rather than guessing:

      1. the **default** repo's `preview_url` — the project's own answer to "which repo serves
         the app", already maintained by `apps.projects.repos`;
      2. else the `preview_url` of the **only** repo that has one. A `preview_url` is a claim
         that this repo serves the application, and normally exactly one repo makes it. Two or
         more is a project with two applications, and only a person knows which to check — so
         that is refused **naming them**, never resolved by picking the first (the same rule
         `orchestration.trigger` applies to an unpinned work item on a multi-repo project);
      3. else the port from `preview_start`, as `http://127.0.0.1:{port}`. That is the address
         the companion itself uses when a build brings the app up (`runner.py`), so it is
         derived from the platform's own behaviour rather than invented. Nothing is started
         here: if the app is not up, whoever is checking gets "nothing answered at that
         address", which is the honest outcome and never a pass.

    Never raises, matching this module: emptiness is an answer, and the caller decides whether
    it is fatal. When there is no address, `reason` says what to go and set.
    """
    with tenant_context(tenant_id):
        repos = list(
            Repository.objects
            .filter(tenant_id=tenant_id, project_id=project_id)
            .order_by("-is_default", "name")
        )

    default = next((r for r in repos if r.is_default), None)
    if default is not None and default.preview_url:
        return ResolvedAppUrl(
            url=default.preview_url.rstrip("/"),
            source=f"the default repository {default.name or '(unnamed)'}",
        )

    serving = [r for r in repos if r.preview_url]
    if len(serving) == 1:
        repo = serving[0]
        return ResolvedAppUrl(
            url=repo.preview_url.rstrip("/"),
            source=f"the repository {repo.name or '(unnamed)'}",
        )
    if len(serving) > 1:
        named = ", ".join(r.name or "(unnamed)" for r in serving)
        return ResolvedAppUrl(reason=(
            f"this project has more than one application address — {named} each carry a Preview "
            f"URL, and only you know which application to check. Give the address for this pass."
        ))

    # `resolve_preview_start` is repo-first then ProjectProfile, so passing the repo that would
    # serve the app gets the profile-level fallback for free.
    chosen = default.name if default is not None else (repos[0].name if len(repos) == 1 else None)
    port = (resolve_preview_start(
        tenant_id=tenant_id, project_id=project_id, repo_name=chosen) or {}).get("port")
    if port:
        return ResolvedAppUrl(
            url=f"http://127.0.0.1:{port}",
            source=f"the preview-start port ({port}) this project builds with",
        )
    return ResolvedAppUrl(reason=NO_APP_URL)
