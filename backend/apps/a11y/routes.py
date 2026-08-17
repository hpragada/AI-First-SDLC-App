"""The list of pages a baseline audit should look at (QA-17).

Everything the accessibility capability has done so far has been a side effect of *building
something*: a story ran through the pipeline, its generated suite drove some screens, and
whatever those screens happened to be got captured and judged. An app that was imported rather
than built here has no story, no suite and no design phase, so nothing anywhere says which
pages it even has. This module is where that gets written down.

**Paths, not URLs.** A route is `/checkout`. Where the app is running belongs to the machine
auditing it — a localhost port today, a staging host next week — and is recorded on the audit,
not on the route. Storing a full URL here would bake one developer's machine into the project's
own map of itself, and every later audit would either inherit it or quietly disagree with it.

**Onboarding will write this list, and a person can too.** OP-06 discovers routes while
importing an app; until it lands the list is entered by hand, which the build plan anticipated.
Either way it is the same table and the same rules, so nothing about the audit changes when
onboarding starts filling it in — only `source` differs, which is kept precisely so a
discovered list stays distinguishable from a typed one.

**Refusals, not repairs.** A bad path is rejected with its reason rather than normalised into
something plausible: a route the audit visits and a route the app actually serves have to be the
same string, and quietly "fixing" `checkout` into `/checkout` would produce an audit that reports
confidently on a page nobody asked about.
"""
from __future__ import annotations

from typing import NoReturn

from apps.tenancy.context import tenant_context

#: What one project may register. Sized against `capture.MAX_SCREENS` (60 per document) and the
#: research header's ~50-screen assumption for a whole application, with room above it. A list
#: past this is a sitemap dump rather than a considered audit scope, and the honest answer is to
#: say so rather than to start a pass that will hit the judgment cap on its first screen.
MAX_ROUTES = 200

#: `A11yRoute.path` is a 512-char column and it sits in a unique index.
MAX_PATH_CHARS = 512


class RouteError(ValueError):
    """A registered route the platform cannot audit. Carries what was wrong, for a human."""


def _reject(message: str) -> NoReturn:
    raise RouteError(message)


def normalise_path(raw) -> str:
    """One route path, checked. Raises `RouteError` rather than guessing what was meant."""
    path = str(raw or "").strip()
    if not path:
        _reject("a route has no path — give the page's path, for example `/checkout`")
    if "://" in path or path.startswith("//"):
        _reject(
            f"route {path!r} looks like a full URL. Register the path alone (`/checkout`); "
            f"where the app is running is recorded on the audit, not on the route, because it "
            f"changes between machines and the route does not."
        )
    if not path.startswith("/"):
        _reject(f"route {path!r} must start with `/` — paths are relative to the app's root")
    if len(path) > MAX_PATH_CHARS:
        _reject(f"route {path[:60]!r}… is longer than {MAX_PATH_CHARS} characters")
    if any(ch in path for ch in ("\n", "\r", "\t")):
        _reject(f"route {path!r} contains a line break")
    # A trailing slash is a different URL to a server and the same page to most routers. Kept
    # exactly as given for that reason — see the module docstring on refusals over repairs —
    # except for the root, where stripping it would leave an empty string.
    return path


def registered_routes(tenant_id, project_id, *, enabled_only: bool = True) -> list:
    """The project's registered routes, in path order."""
    from .models import A11yRoute

    with tenant_context(tenant_id):
        rows = A11yRoute.objects.filter(tenant_id=tenant_id, project_id=project_id)
        if enabled_only:
            rows = rows.filter(enabled=True)
        return list(rows)


def route_paths(tenant_id, project_id) -> list[str]:
    """Just the paths an audit would visit — what `baseline.start_baseline_audit` freezes."""
    return [row.path for row in registered_routes(tenant_id, project_id)]


def register_routes(*, tenant_id, project_id, routes, source: str = "manual",
                    replace: bool = False) -> dict:
    """Add or update routes for a project. Idempotent per path.

    `replace=True` makes the given list the whole list — anything not named is **disabled**,
    never deleted. A route that has stopped existing is a fact about the application worth
    keeping: a deleted row invites someone to add it back next month with no record of why it
    went, and its past findings would then point at a page nothing explains.

    Returns what changed, because "did my import actually do anything?" should not need a
    database query to answer.
    """
    from .models import A11yRoute

    if not isinstance(routes, list | tuple):
        _reject(f"routes must be a list, not {type(routes).__name__}")
    if source not in A11yRoute.Source.values:
        _reject(f"`source` is {source!r} — it is one of {', '.join(A11yRoute.Source.values)}")

    seen: dict[str, dict] = {}
    for raw in routes:
        entry = raw if isinstance(raw, dict) else {"path": raw}
        path = normalise_path(entry.get("path"))
        # Last one wins rather than raising: a list naming the same page twice is a
        # duplicate, not a contradiction, and the unique constraint would refuse the write
        # with a database error nobody can read.
        seen[path] = {
            "label": str(entry.get("label") or "")[:200],
            "notes": str(entry.get("notes") or ""),
            "enabled": bool(entry.get("enabled", True)),
        }
    if len(seen) > MAX_ROUTES:
        _reject(
            f"{len(seen)} routes were given, over the limit of {MAX_ROUTES}. Nothing was "
            f"stored — audit the pages that matter rather than every page that exists; the "
            f"judgment cap would stop the first pass long before it reached the end of this."
        )

    added: list[str] = []
    updated: list[str] = []
    disabled: list[str] = []
    with tenant_context(tenant_id):
        for path in sorted(seen):
            _, created = A11yRoute.objects.update_or_create(
                tenant_id=tenant_id, project_id=project_id, path=path,
                defaults={**seen[path], "source": source},
            )
            (added if created else updated).append(path)
        if replace:
            for row in A11yRoute.objects.filter(
                tenant_id=tenant_id, project_id=project_id, enabled=True,
            ).exclude(path__in=sorted(seen) or [""]):
                row.enabled = False
                row.save(update_fields=["enabled", "updated_at"])
                disabled.append(row.path)
    return {"added": added, "updated": updated, "disabled": disabled,
            "total": len(route_paths(tenant_id, project_id))}


def describe_routes(tenant_id, project_id) -> str:
    """The route list in one line, for a console or an audit's summary."""
    rows = registered_routes(tenant_id, project_id, enabled_only=False)
    if not rows:
        return "no routes are registered for this project"
    enabled = [row for row in rows if row.enabled]
    line = f"{len(enabled)} route(s) registered for audit"
    off = len(rows) - len(enabled)
    return f"{line}, {off} disabled" if off else line
