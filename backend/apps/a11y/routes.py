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

import json
from typing import NoReturn

from apps.tenancy.context import tenant_context

#: What one project may register. **Not** derived from `capture.MAX_SCREENS`: that bounds one
#: capture document, and since B5 an audit larger than it simply runs in more passes. This is a
#: scope judgement instead — a list past this is a sitemap dump rather than a considered audit
#: scope, and the honest answer is to say so rather than to start a pass whose judging will
#: defer most of itself (`dispatch.DEFAULT_MAX_JUDGMENTS_PER_RUN`). Team decision 2026-08-19:
#: left at 200 while the pass loop landed, so "any number of pages" honestly means "any number
#: up to the 200 a project may register".
MAX_ROUTES = 200

#: `A11yRoute.path` is a 512-char column and it sits in a unique index.
MAX_PATH_CHARS = 512

#: The keys one pasted entry may carry, and what each is called on the row. `title` is here
#: because that is what a route list exported from a project usually calls the human name, and
#: `label` because that is what this table calls it — one is an alias for the other, not a
#: second field. Anything NOT in here is reported back by name (see `register_routes`): a key
#: we silently ignored is a decision the client made that the audit then did not honour, and
#: the one that matters most — whether a page is in scope — is exactly the kind of thing an
#: export names differently.
ENTRY_KEYS = {
    "path": "path",
    "title": "label",
    "label": "label",
    "enabled": "enabled",
    "notes": "notes",
    "example": "example_path",
    "example_path": "example_path",
}


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


def _read_entries(routes) -> dict:
    """Turn a pasted list into `{path: fields}`, refusing what cannot be a page.

    One reader for the preview and the write, so what a person is shown before they commit is
    produced by the same code that commits it. Two readers would eventually disagree, and the
    disagreement would appear as a confirmation screen that did not describe what happened.
    """
    if not isinstance(routes, list | tuple):
        _reject(f"routes must be a list, not {type(routes).__name__}")

    seen: dict[str, dict] = {}
    ignored: dict[str, int] = {}
    for index, raw in enumerate(routes, start=1):
        if isinstance(raw, dict):
            entry = raw
        elif isinstance(raw, str):
            entry = {"path": raw}
        else:
            _reject(f"entry {index} of {len(routes)} is a {type(raw).__name__}, not a page")
        for key in entry:
            if key not in ENTRY_KEYS:
                ignored[str(key)] = ignored.get(str(key), 0) + 1
        if not str(entry.get("path") or "").strip():
            # Named, because "a route has no path" is unactionable on a list of 69 and the
            # usual cause is an export that calls it something else. The keys it DOES have are
            # the answer, so they are handed back rather than described.
            keys = ", ".join(f"`{k}`" for k in entry) or "none"
            _reject(
                f"entry {index} of {len(routes)} has no `path`. The keys on it are: {keys}. "
                f"Rename the one holding the page's path to `path`. Nothing was registered."
            )
        path = normalise_path(entry.get("path"))
        # Last one wins rather than raising: a list naming the same page twice is a
        # duplicate, not a contradiction, and the unique constraint would refuse the write
        # with a database error nobody can read.
        seen[path] = {
            "label": str(entry.get("title") or entry.get("label") or "")[:200],
            "notes": str(entry.get("notes") or ""),
            "enabled": bool(entry.get("enabled", True)),
            "example_path": _example(entry, path),
        }
    return {"seen": seen,
            "ignored": [{"key": k, "entries": n} for k, n in sorted(ignored.items())]}


def _example(entry: dict, path: str) -> str:
    """A real page standing for a pattern route, checked like any other path.

    `/events/:id` is how a developer writes "any event" and no browser can open it, so an
    example is what makes the page auditable at all. It is checked with the same rules as the
    route itself — an example that is not a path would send the audit somewhere nobody asked
    for, which is the failure this module exists to refuse.
    """
    raw = str(entry.get("example") or entry.get("example_path") or "").strip()
    if not raw:
        return ""
    example = normalise_path(raw)
    if example == path:
        return ""       # not an example of anything; the route is already a real page
    return example


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
                    replace: bool = False, actor=None) -> dict:
    """Add or update routes for a project. Idempotent per path.

    `replace=True` makes the given list the whole list — anything not named is **disabled**,
    never deleted. A route that has stopped existing is a fact about the application worth
    keeping: a deleted row invites someone to add it back next month with no record of why it
    went, and its past findings would then point at a page nothing explains.

    Returns what changed, because "did my import actually do anything?" should not need a
    database query to answer — and writes the same thing to the ledger, because what an audit
    measured is only meaningful next to what it was asked to measure. Take twelve failing pages
    out of scope and re-run, and the report improves; nothing about that is dishonest in any one
    place, and the whole of it is, unless the scope change is on the record beside the numbers.
    """
    from .models import A11yRoute

    if source not in A11yRoute.Source.values:
        _reject(f"`source` is {source!r} — it is one of {', '.join(A11yRoute.Source.values)}")

    read = _read_entries(routes)
    seen, ignored = read["seen"], read["ignored"]
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
    changed = {"added": added, "updated": updated, "disabled": disabled,
               # Every key we could not use, and how many entries carried it. NOT a warning to
               # be counted and forgotten: if an export calls the in-scope flag `inScope`, we
               # register 69 pages all in scope and audit twelve the client had excluded. This
               # is the sentence that turns that from a silent wrong audit into an obvious fix.
               "ignored_keys": ignored,
               "total": len(route_paths(tenant_id, project_id))}
    _record_change(tenant_id=tenant_id, project_id=project_id, actor=actor, source=source,
                   changed=changed)
    return changed


def describe_routes(tenant_id, project_id) -> str:
    """The route list in one line, for a console or an audit's summary."""
    rows = registered_routes(tenant_id, project_id, enabled_only=False)
    if not rows:
        return "no routes are registered for this project"
    enabled = [row for row in rows if row.enabled]
    line = f"{len(enabled)} route(s) registered for audit"
    off = len(rows) - len(enabled)
    return f"{line}, {off} disabled" if off else line


def _record_change(*, tenant_id, project_id, actor, source, changed: dict) -> None:
    """Append one ledger entry for a change to what an audit is asked to look at.

    This app already writes the ledger for the two things that need accountability — a
    reviewer's decision, and a signature on a conformance statement. Changing which pages get
    audited belongs with them: it decides what every later number is a number ABOUT, and it was
    the one change of that weight leaving no trace at all.

    Written even when nothing moved. "Somebody pasted the same list again" is a different fact
    from "nobody touched it", and only one of them is worth knowing when a report changes.
    """
    from apps.ledger.models import Event

    with tenant_context(tenant_id):
        Event.objects.create(
            tenant_id=tenant_id, actor=str(actor or "system"), action="a11y.routes.registered",
            target_type="project", target_id=project_id,
            payload={"source": source, **{k: v for k, v in changed.items()}},
        )


def scope_change_since(tenant_id, project_id) -> dict:
    """How the page list differs from the one the last finished audit actually used.

    Both sides already exist and neither is invented here: the audit froze its own list when it
    opened, and the registry holds today's. The comparison is what nothing did — the report
    compares FINDINGS between audits and calls it movement, so a scope that quietly shrank
    reads as an application that quietly improved.

    `{}` when there is nothing to compare against or nothing has moved, so a caller can put the
    whole thing behind one truthiness check and say nothing when there is nothing to say.
    """
    from .models import A11yBaselineAudit

    with tenant_context(tenant_id):
        last = (
            A11yBaselineAudit.objects
            .filter(tenant_id=tenant_id, project_id=project_id,
                    status__in=(A11yBaselineAudit.Status.COMPLETE,
                                A11yBaselineAudit.Status.JUDGING))
            .order_by("-created_at").first()
        )
    if last is None:
        return {}
    before = set(last.routes or [])
    now = set(route_paths(tenant_id, project_id))
    added = sorted(now - before)
    removed = sorted(before - now)
    if not added and not removed:
        return {}
    return {"audit_id": str(last.id), "audit_at": last.created_at,
            "added": added, "removed": removed,
            "before": len(before), "now": len(now)}


def parse_routes_text(text) -> list:
    """One pasted list, read here rather than in the browser.

    **Why the platform parses it and not the screen.** A refusal has to say the same thing
    however the list arrived — pasted into the app, or PUT by a script — and a message written
    twice is a message that will differ. The browser would also report a syntax error in its own
    words, which are about JSON rather than about pages.

    Accepts what the screen advertises and nothing else: a list of paths, or a list of objects
    carrying `path`. A bare object is accepted as a list of one, because pasting a single entry
    without its brackets is an easy thing to do and an unambiguous thing to mean.
    """
    if isinstance(text, list):
        return text
    raw = str(text or "").strip()
    if not raw:
        _reject("nothing was pasted, so there are no pages to register")
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        _reject(
            f"this could not be read as a list of pages ({exc}). Paste a list of paths — "
            f'["/", "/catalogue"] — or a list of entries carrying `path`.'
        )
    if isinstance(parsed, dict):
        return [parsed]
    if not isinstance(parsed, list):
        _reject(
            f"this is a single {type(parsed).__name__}, not a list of pages. Paste a list of "
            f'paths — ["/", "/catalogue"] — or a list of entries carrying `path`.'
        )
    return parsed


def preview_registration(*, tenant_id, project_id, routes) -> dict:
    """What registering this list WOULD do, without doing any of it.

    **The one screen that closes the whole class of scope accidents.** A page is identified by
    its path — there is no hidden id — so editing the text of a path does not edit a page, it
    points at a different one. Paste a corrected list and the old page is still registered, still
    in scope, and still audited: a page the user believes they renamed away. Equally, pasting
    three pages meaning "add these three" would, under a whole-list reading, take every other
    page out of scope.

    Neither can be guessed. Both are obvious the moment somebody is shown the difference before
    it is written, which is all this is: the same validation the write does, against what is
    already there, with nothing saved.

    `missing` is the load-bearing half — pages already registered that this list does not
    mention, each with what would be lost by excluding it, so "did you mean to remove it?" is a
    question with the facts attached.
    """
    from .models import A11yFinding, A11yRoute

    entries = _read_entries(routes)
    with tenant_context(tenant_id):
        existing = {
            row.path: row
            for row in A11yRoute.objects.filter(tenant_id=tenant_id, project_id=project_id)
        }
        open_by_route: dict[str, int] = {}
        for route in (
            A11yFinding.objects
            .filter(tenant_id=tenant_id, project_id=project_id,
                    status=A11yFinding.Status.OPEN)
            .values_list("route", flat=True)
        ):
            open_by_route[route] = open_by_route.get(route, 0) + 1

    adding = sorted(p for p in entries["seen"] if p not in existing)
    updating = sorted(p for p in entries["seen"] if p in existing)
    missing = [
        {"path": row.path, "label": row.label, "enabled": row.enabled,
         "open_findings": open_by_route.get(row.path, 0)}
        for path, row in sorted(existing.items())
        if path not in entries["seen"] and row.enabled
    ]
    return {
        "adding": adding,
        "updating": updating,
        "missing": missing,
        "ignored_keys": entries["ignored"],
        "total_now": sum(1 for r in existing.values() if r.enabled),
    }


def last_visited(tenant_id, project_id) -> dict:
    """{path: when an audit last actually opened it}. Computed, never stored.

    A visit is already recorded — every screen scan carries its route and the moment it was
    written — so keeping a second copy on the route row would be a number that could disagree
    with the evidence behind it. A route with no entry here has never been opened, and a route
    that was asked for but did not load has a scan carrying its `load_error`, which is not a
    visit and is deliberately not counted as one.
    """
    from .models import A11yScreenScan

    seen: dict[str, object] = {}
    with tenant_context(tenant_id):
        rows = (
            A11yScreenScan.objects
            .filter(tenant_id=tenant_id, project_id=project_id, load_error="")
            .order_by("created_at")
            .values_list("route", "created_at")
        )
        for route, when in rows:
            seen[route] = when       # ordered ascending, so the last write is the latest
    return seen
