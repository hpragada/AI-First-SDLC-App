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
import logging
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
    # `in_scope` is the same fact under the name most route exports actually use — our own
    # reference brownfield app writes it for all 69 of its routes. Without the alias every one
    # of them came back as an unrecognised column and every page was registered in scope,
    # including the one its author had deliberately excluded. The warning that named the column
    # was honest and still fired; it was the alias that was missing.
    "in_scope": "enabled",
    "notes": "notes",
    "example": "example_path",
    "example_path": "example_path",
}


logger = logging.getLogger(__name__)


class RouteError(ValueError):
    """A registered route the platform cannot audit. Carries what was wrong, for a human."""


def _reject(message: str) -> NoReturn:
    raise RouteError(message)


def normalise_path(raw) -> str:
    """One route path, checked. Raises `RouteError` rather than guessing what was meant."""
    path = str(raw or "").strip()
    if not path:
        _reject("A page has no path. Give the page's path, for example /checkout.")
    if "://" in path or path.startswith("//"):
        _reject(
            f"{path} looks like a full web address. Enter the page's path only, such as "
            f"/checkout — where the app is running is set on the audit, because it changes "
            f"between machines and the page does not."
        )
    if not path.startswith("/"):
        _reject(f"{path} must start with a slash, such as /checkout — pages are listed from "
                f"the app's root.")
    if len(path) > MAX_PATH_CHARS:
        _reject(f"The page {path[:60]}… is longer than {MAX_PATH_CHARS} characters. Shorten it.")
    if any(ch in path for ch in ("\n", "\r", "\t")):
        _reject("One of the pages contains a line break. Put each page on its own line.")
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
        _reject("The pages must be given as a list.")

    seen: dict[str, dict] = {}
    ignored: dict[str, int] = {}
    for index, raw in enumerate(routes, start=1):
        if isinstance(raw, dict):
            entry = raw
        elif isinstance(raw, str):
            entry = {"path": raw}
        else:
            _reject(f"Page {index} of {len(routes)} in the list isn't a path. Give each page "
                    f"as a path, such as /checkout.")
        for key in entry:
            if key not in ENTRY_KEYS:
                ignored[str(key)] = ignored.get(str(key), 0) + 1
        if not str(entry.get("path") or "").strip():
            # Named, because "a route has no path" is unactionable on a list of 69 and the
            # usual cause is an export that calls it something else. The keys it DOES have are
            # the answer, so they are handed back rather than described.
            keys = ", ".join(f"`{k}`" for k in entry) or "none"
            _reject(
                f"Page {index} of {len(routes)} in the list has no path. Its fields are: {keys}. "
                f"Name the field that holds the page's address `path`. Nothing was added."
            )
        path = normalise_path(entry.get("path"))
        # Last one wins rather than raising: a list naming the same page twice is a
        # duplicate, not a contradiction, and the unique constraint would refuse the write
        # with a database error nobody can read.
        # `enabled` / `in_scope` read through ENTRY_KEYS' own aliases rather than a second list
        # of names kept in step by hand. That is exactly how the alias nearly shipped as a
        # silence: `ENTRY_KEYS` fed the ignored-keys warning and nothing else, so a recognised
        # key that no field read would have been dropped without even a warning.
        seen[path] = {
            "label": str(_field(entry, "label") or "")[:200],
            "notes": str(_field(entry, "notes") or ""),
            "enabled": bool(_field(entry, "enabled", default=True)),
            "example_path": _example(entry, path),
        }
    return {"seen": seen,
            "ignored": [{"key": k, "entries": n} for k, n in sorted(ignored.items())]}


def _field(entry: dict, name: str, *, default=None):
    """One page property, read through every alias `ENTRY_KEYS` accepts for it.

    Aliases are declared once, in `ENTRY_KEYS`, and read here — so a key the ignored-keys
    warning treats as recognised is a key something actually reads. The two used to be separate
    lists, which is a silence waiting to happen: `in_scope` was accepted by the warning and read
    by nothing, so a page marked out of scope would have been audited with nothing said.

    First alias present wins, in the order the caller's data has them; absent everywhere gives
    `default`.
    """
    for key, target in ENTRY_KEYS.items():
        if target == name and key in entry and entry[key] is not None:
            return entry[key]
    return default


def _example(entry: dict, path: str) -> str:
    """A real page standing for a pattern route, checked like any other path.

    `/events/:id` is how a developer writes "any event" and no browser can open it, so an
    example is what makes the page auditable at all. It is checked with the same rules as the
    route itself — an example that is not a path would send the audit somewhere nobody asked
    for, which is the failure this module exists to refuse.
    """
    raw = str(_field(entry, "example_path") or "").strip()
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
        _reject("That isn't a way pages can be added. Nothing was added.")

    read = _read_entries(routes)
    seen, ignored = read["seen"], read["ignored"]
    if len(seen) > MAX_ROUTES:
        _reject(
            f"{len(seen)} pages were given, over the limit of {MAX_ROUTES}. Nothing was "
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
    # In the screen's own words (mockup M8): "pages listed", not "route(s) registered" — and
    # "excluded", the word the page list's own filter uses for a page taken out of scope.
    if not rows:
        return "No pages are listed for this project"
    enabled = [row for row in rows if row.enabled]
    line = f"{len(enabled)} page{'s' if len(enabled) != 1 else ''} listed"
    off = len(rows) - len(enabled)
    return f"{line}, {off} excluded" if off else line


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
            project_id=project_id,      # S.No 230 — this path bypasses tools.log_event
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


def _read_lines(raw: str) -> list:
    """One path per line. Blank lines ignored; `#` comments ignored; spaces refused."""
    paths = []
    for number, line in enumerate(raw.splitlines(), start=1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        # Trailing commas and quotes are what a half-converted JSON list looks like. Stripping
        # them is not "repairing a bad path" — the path itself is untouched and still checked
        # by `normalise_path`; this only removes punctuation that belongs to the other format.
        entry = entry.rstrip(",").strip().strip('"').strip("'").strip()
        if not entry:
            continue
        if any(ch.isspace() for ch in entry):
            _reject(
                f"Line {number} ({entry}) contains a space, so it is not a single path. One "
                f"path per line — `/checkout` — or paste a JSON list if you also want to give "
                f"each page a name."
            )
        paths.append(entry)
    if not paths:
        _reject("Nothing was pasted, so there are no pages to add.")
    return paths


def parse_routes_text(text) -> list:
    """One pasted list, read here rather than in the browser.

    **Why the platform parses it and not the screen.** A refusal has to say the same thing
    however the list arrived — pasted into the app, or PUT by a script — and a message written
    twice is a message that will differ. The browser would also report a syntax error in its own
    words, which are about JSON rather than about pages.

    Accepts a list of paths, or a list of objects carrying `path`. A bare object is accepted as
    a list of one, because pasting a single entry without its brackets is an easy thing to do
    and an unambiguous thing to mean.

    **And one path per line**, which is what most people paste first. It used to be refused,
    with a message that explained JSON to somebody who had just pasted a perfectly clear list of
    pages. Line mode is entered only when the text does not open with `[` or `{`, so nothing
    about the JSON path changes — a malformed JSON list still gets the JSON error rather than
    being silently re-read as one long path.

    **Line mode refuses a line containing a space, and that is the point of having it here.**
    `normalise_path` rejects an empty path, a full URL, a path not starting with `/` and a line
    break — but not a space. A line like `Home /catalogue` would otherwise register a page that
    cannot exist and be reported unreachable on every audit forever. That exact hole is why the
    earlier line-per-path form was dropped; it is closed here rather than reopened.
    """
    if isinstance(text, list):
        return text
    raw = str(text or "").strip()
    if not raw:
        _reject("Nothing was pasted, so there are no pages to add.")
    if raw[0] not in "[{":
        return _read_lines(raw)
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        # Screen Words group 8: the parser's own words ("Expecting value: line 1 column 1")
        # went to the screen. They go to the log; the person gets what to paste instead.
        logger.info("A pasted page list was not valid JSON: %s", exc)
        _reject(
            "This couldn't be read as a list of pages. Paste a list of paths — "
            '["/", "/catalogue"] — or a list of entries carrying `path`.'
        )
    if isinstance(parsed, dict):
        return [parsed]
    if not isinstance(parsed, list):
        _reject(
            "This is a single value, not a list of pages. Paste a list of "
            'paths — ["/", "/catalogue"] — or a list of entries carrying `path`.'
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


def history_for(tenant_id, project_id) -> dict:
    """{path: {"open_findings": n, "visits": n}} — what each page has accumulated.

    What a rename would leave behind, in one query pair rather than one per row. A finding is
    identified by *(route + element + rule)*, so the page's path is part of the identity of every
    problem recorded on it: change the path and the problems stay with the old address while the
    new one starts empty. That is correct — the platform cannot tell a rename from a new page —
    but it is not obvious from where a person sits, so the screen has to be able to say it before
    they commit.
    """
    from .models import A11yFinding, A11yScreenScan

    out: dict[str, dict] = {}
    with tenant_context(tenant_id):
        for route in (
            A11yFinding.objects
            .filter(tenant_id=tenant_id, project_id=project_id,
                    status=A11yFinding.Status.OPEN)
            .values_list("route", flat=True)
        ):
            out.setdefault(route, {"open_findings": 0, "visits": 0})["open_findings"] += 1
        for route in (
            A11yScreenScan.objects
            .filter(tenant_id=tenant_id, project_id=project_id, load_error="")
            .values_list("route", flat=True)
        ):
            out.setdefault(route, {"open_findings": 0, "visits": 0})["visits"] += 1
    return out


#: What one row may be edited to. `source` and `id` are deliberately absent: who put a page here
#: is a fact about how it arrived, and a row's identity is not a thing a person edits.
EDITABLE = ("path", "label", "enabled", "notes", "example_path")


def update_route(*, tenant_id, project_id, route_id, fields: dict, actor=None) -> dict:
    """Edit ONE registered page, on a row the platform already knows.

    **This is what makes a correction a correction.** Registering works by path, because a pasted
    list carries no identities — so re-pasting a corrected path adds a page and leaves the old one
    in scope. Here the row is named, so changing its path changes that page and nothing else. The
    entire ghost-page problem is absent rather than warned about.

    What it still cannot do is move the page's history: a finding is keyed on the route it was
    found at, and rewriting those keys would edit records the ledger treats as permanent. So a
    rename is allowed, recorded, and the caller is expected to have said what it costs — which is
    what `history_for` is for.

    Returns what changed, `{}` when nothing did — the same shape and the same reason as
    `register_routes`.
    """
    from .models import A11yRoute

    unknown = sorted(set(fields) - set(EDITABLE))
    if unknown:
        _reject(
            f"{', '.join(unknown)} can't be changed on a page. You can change: "
            f"{', '.join(k.replace('_', ' ') for k in EDITABLE)}. Nothing was changed."
        )

    with tenant_context(tenant_id):
        row = A11yRoute.objects.filter(
            tenant_id=tenant_id, project_id=project_id, id=route_id).first()
        if row is None:
            _reject("That page isn't listed on this project.")

        before = {key: getattr(row, key) for key in EDITABLE}
        after = dict(before)
        if "path" in fields:
            after["path"] = normalise_path(fields["path"])
        if "example_path" in fields:
            after["example_path"] = _example(
                {"example": fields["example_path"]}, after["path"])
        if "label" in fields:
            after["label"] = str(fields["label"] or "")[:200]
        if "notes" in fields:
            after["notes"] = str(fields["notes"] or "")
        if "enabled" in fields:
            after["enabled"] = bool(fields["enabled"])

        if after["path"] != before["path"]:
            clash = A11yRoute.objects.filter(
                tenant_id=tenant_id, project_id=project_id, path=after["path"],
            ).exclude(id=row.id).first()
            if clash is not None:
                # Refused rather than merged. Two rows becoming one would silently discard
                # whichever page's name and scope lost, and the audit would then be visiting a
                # page under a description nobody wrote for it.
                _reject(
                    f"{after['path']} is already registered on this project"
                    f"{f' as “{clash.label}”' if clash.label else ''}. Edit that page instead, "
                    f"or take this one out of scope."
                )

        changed = {k: {"from": before[k], "to": after[k]} for k in EDITABLE
                   if before[k] != after[k]}
        if not changed:
            return {}
        for key, value in after.items():
            setattr(row, key, value)
        row.save(update_fields=[*EDITABLE, "updated_at"])

    _record_change(tenant_id=tenant_id, project_id=project_id, actor=actor,
                   source=row.source, changed={"edited": row.path, "fields": changed})
    return changed


def delete_route(*, tenant_id, project_id, route_id, actor=None) -> dict:
    """Remove a page that has no history. Anything else is taken out of scope instead.

    **The rule this module has always had is that a page is disabled, never deleted** — a page
    that stopped existing is a fact about the application worth keeping, and a deleted row invites
    someone to add it back next month with no record of why it went. Its past findings would then
    point at a page nothing explains.

    That rule is about pages that were REAL. A path typed by mistake was never a page: it has
    never been opened and nothing has ever been recorded against it, so there is no history to
    protect and keeping the row forever is noise on a screen people have to read. So a row with no
    visits and no findings can go, and every other row is excluded and stays visible as excluded.
    """
    from .models import A11yRoute

    with tenant_context(tenant_id):
        row = A11yRoute.objects.filter(
            tenant_id=tenant_id, project_id=project_id, id=route_id).first()
        if row is None:
            _reject("That page isn't listed on this project.")
        path, source = row.path, row.source

    history = history_for(tenant_id, project_id).get(path) or {}
    if history.get("open_findings") or history.get("visits"):
        update_route(tenant_id=tenant_id, project_id=project_id, route_id=route_id,
                     fields={"enabled": False}, actor=actor)
        return {"removed": False, "excluded": True, "path": path,
                "reason": (
                    f"{path} has been audited, so it is kept and taken out of scope rather than "
                    f"deleted. What was found there stays on the record."
                )}

    with tenant_context(tenant_id):
        A11yRoute.objects.filter(
            tenant_id=tenant_id, project_id=project_id, id=route_id).delete()
    _record_change(tenant_id=tenant_id, project_id=project_id, actor=actor, source=source,
                   changed={"deleted": path})
    return {"removed": True, "excluded": False, "path": path, "reason": ""}
