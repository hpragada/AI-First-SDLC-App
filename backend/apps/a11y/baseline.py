"""Auditing an app the platform did not build (QA-17).

Every accessibility check up to here has ridden on a *build*: a story ran, its generated suite
drove some screens, and whatever it visited got captured and judged. A client who imports an
existing application has none of that — no story, no suite, no design phase and no accessibility
spec — and still needs an answer to "how bad is it?". This module is that answer: point the
platform at a registered list of routes and run the same capture-and-judge chain over them.

**Nothing about the checking changes; only where the screen list comes from.** The capture
format, the selection rules, the crop, the judge, the triage, the ledger and the report are all
QA-11b/12/12a/13's, unchanged. That is deliberate to the point of being the design: a second way
of deciding what "a failure" means would be a second standard, and the one that gets forgotten
is always the one nobody is currently looking at.

**The server never opens a browser, and this module never pretends otherwise** (R2). The app
under audit runs on a developer's machine — or on a host only they can reach — and the platform
cannot see it. So the audit is a plan plus a reconciliation: `start_baseline_audit` freezes the
route list and hands out a manifest, the companion visits the routes and posts what it saw, and
`finish_baseline_audit` compares what came back against what was asked for. The visiting is
mechanical and needs no agent; the judging is the agent's, dispatched exactly as a build's is.

**The reconciliation is the whole point of AC2.** A route that fails to load is reported as an
error for that route — and, crucially, so is a route that reports *nothing at all*, because a
capture that never mentions a page and a capture that says the page was fine look identical in
the database. A pass that quietly covered 38 of 50 screens and read as complete would be worse
than no baseline at all, so a route that was asked for and never came back is recorded as
unreachable with that as its stated reason.
"""
from __future__ import annotations

from typing import NoReturn

from apps.projects.preview_config import resolve_app_base_url
from apps.tenancy.context import tenant_context

from .routes import RouteError, normalise_path, route_paths

#: The manifest format the audit script reads. Bumped only for a change the script must know
#: about — the same discipline as `capture.CAPTURE_VERSION`, and for the same reason.
MANIFEST_VERSION = 1

#: Where the audit script leaves what it captured, relative to wherever it is run. Deliberately
#: one of `a11ycapture.CAPTURE_GLOBS`, so the collector that already exists finds it.
CAPTURE_FILENAME = "test-results/a11y-candidates.json"

#: What a route that was asked for and never reported gets as its reason. Wording matters: a
#: reader has to be able to tell this from a route that *did* report a failure to load, because
#: the two point at different problems — one is the application, the other is the audit itself.
NEVER_REPORTED = (
    "the audit finished without reporting this route at all, so nothing is known about it — "
    "the run may have stopped early, or the page may never have been reached"
)


class BaselineError(ValueError):
    """A baseline audit could not be started or finished. Carries the reason, for a human."""


def _reject(message: str) -> NoReturn:
    raise BaselineError(message)


def _audit(tenant_id, audit_id):
    from .models import A11yBaselineAudit

    with tenant_context(tenant_id):
        audit = A11yBaselineAudit.objects.filter(id=audit_id, tenant_id=tenant_id).first()
    if audit is None:
        _reject(f"no baseline audit {str(audit_id)!r} in this tenant")
    return audit


def start_baseline_audit(*, tenant_id, project_id, base_url: str = "", routes=None,
                         started_by=None, claimable: bool = False):
    """Freeze what this audit will visit and open it for capture. Returns the audit.

    `claimable` says nobody is standing at the machine yet: opened from the app, the audit waits
    as `pending` until a companion picks it up. Started from the companion's own command line it
    is left `capturing`, because the machine that opened it is already about to visit. This is
    not a mode the rest of the code has to know about — it only sets where the status starts,
    and `ingest_audit_capture` moves any audit to `capturing` the moment a screen arrives,
    whoever sent it.

    `routes` overrides the registry for a one-off pass; left out, the project's enabled routes
    are used. Either way the list is **stored on the audit**, not re-read at the end: the audit
    has to be able to say "this was asked for and never came back", and a list re-read later
    would make a route added mid-pass indistinguishable from one that failed.

    Refuses an empty list rather than starting a pass that can only report nothing. An audit
    that finishes having checked no pages is the exact shape of a clean result, and producing
    one because nobody registered a route would be the worst kind of quiet success.

    `base_url` left out is resolved from what the platform already knows (B3) — see
    `apps.projects.preview_config.resolve_app_base_url`. **An address given here always wins**:
    somebody deliberately checking a staging site must never be overridden by a stored
    development URL. With no address from either, the audit is refused rather than opened,
    because a manifest with an empty address cannot be visited — the script builds each page's
    URL relative to it — and an audit that reports nothing looks exactly like an application
    with nothing wrong.
    """
    from .models import A11yBaselineAudit

    if routes is None:
        paths = route_paths(tenant_id, project_id)
    else:
        if not isinstance(routes, list | tuple):
            _reject(f"routes must be a list, not {type(routes).__name__}")
        try:
            paths = [normalise_path(route) for route in routes]
        except RouteError as exc:
            _reject(str(exc))
    # Deduped, order preserved: the audit should visit `/checkout` once however many times it
    # was named, and the order a person listed their pages in is the order they want them back.
    ordered = list(dict.fromkeys(paths))
    if not ordered:
        _reject(
            "this project has no routes registered, so there is nothing to audit. Register the "
            "pages to check first — an audit that visits no pages would report no problems, "
            "which reads exactly like an application with none."
        )

    # After the route checks on purpose: a person with neither routes nor an address is told
    # about the routes first, which is the earlier thing to go and fix, and every existing
    # refusal keeps its own wording.
    address = str(base_url or "").strip()
    if not address:
        resolved = resolve_app_base_url(tenant_id=tenant_id, project_id=project_id)
        if not resolved.url:
            _reject(resolved.reason)
        address = resolved.url

    with tenant_context(tenant_id):
        return A11yBaselineAudit.objects.create(
            tenant_id=tenant_id, project_id=project_id,
            base_url=address[:512], routes=ordered,
            status=(A11yBaselineAudit.Status.PENDING if claimable
                    else A11yBaselineAudit.Status.CAPTURING),
            started_by_id=started_by or None,
        )


def audit_manifest(audit) -> dict:
    """What the audit script is given: where the app is, and which paths to visit.

    A manifest rather than a generated script. The visiting logic — drive a browser to a URL,
    wait for it to settle, run the scanner if one is available, write down the elements and one
    picture — is the same for every audit of every project, so it lives in one reviewed file
    that ships with the companion (`runner/companion/assets/a11y_audit.mjs`). Only the inputs
    differ, and only the inputs are produced here. Synthesising JavaScript per audit would put
    a program nobody can test in the middle of a compliance chain.

    `visit` names a real page to open for a route that is a PATTERN (`/events/:id` → the
    example someone gave for it). Only the routes that have one appear, so a project whose
    pages are all real addresses — nearly every project — gets an empty map and nothing to
    think about. The screen still comes back recorded against the pattern; see `captureRoute`.
    """
    from .models import A11yRoute

    routes = list(audit.routes or [])
    with tenant_context(audit.tenant_id):
        examples = {
            row.path: row.example_path.strip()
            for row in A11yRoute.objects.filter(
                tenant_id=audit.tenant_id, project_id=audit.project_id, path__in=routes,
            ).exclude(example_path="")
            if row.example_path.strip()
        }
    return {
        "version": MANIFEST_VERSION,
        "audit_id": str(audit.id),
        "project_id": str(audit.project_id),
        "base_url": audit.base_url,
        "routes": routes,
        "visit": examples,
        "output": CAPTURE_FILENAME,
    }


def audit_snapshot(*, tenant_id, audit_id) -> dict:
    """One audit as the machine running it needs to see it: its state and its manifest.

    Exists so a companion that reconnects mid-audit can ask what it was given instead of
    starting a second audit to find out. Reading it can never change what it was asked to
    visit — `routes` was frozen when it opened.
    """
    audit = _audit(tenant_id, audit_id)
    return {"audit_id": str(audit.id), "status": audit.status,
            "manifest": audit_manifest(audit)}


def ingest_audit_capture(*, tenant_id, audit_id, text: str, object_store=None) -> dict:
    """Store one posted capture against this audit's own bucket.

    The audit's id is the `run_key`, so its screens sit apart from every build's and from the
    project-wide bucket a CI post lands in. Everything downstream reads that key as a string;
    see `models.A11yBaselineAudit` for why there is no `Run` behind it.
    """
    from .ingest import ingest_capture
    from .models import A11yBaselineAudit

    audit = _audit(tenant_id, audit_id)
    out = ingest_capture(
        tenant_id=tenant_id, project_id=str(audit.project_id), text=text,
        run_key=str(audit.id), object_store=object_store,
    )
    # The one place an audit becomes `capturing`, and it is a fact rather than a declaration:
    # a screen arrived, so something is visiting. Whichever way the audit was opened, and
    # whoever posted it. Nothing else has to know how it started.
    if audit.status in (A11yBaselineAudit.Status.PENDING, A11yBaselineAudit.Status.CLAIMED):
        with tenant_context(tenant_id):
            audit.status = A11yBaselineAudit.Status.CAPTURING
            audit.save(update_fields=["status", "updated_at"])
    return out


def reconcile_routes(*, tenant_id, audit) -> list[dict]:
    """Record every asked-for route that never reported, and return what was recorded (AC2).

    This is the half of "never silently skipped" that the capture cannot do for itself. A script
    that dies halfway, a companion that loses its connection, a route removed from the app
    between registration and the pass — all of them end with a route in the plan and no row in
    the database, which is indistinguishable from a page that was fine. So the plan is compared
    against what arrived, and the difference is written down as unreachable with a reason saying
    exactly that.

    Idempotent: a second reconciliation of the same audit changes nothing, because a route
    recorded as unreachable is now a row like any other and is no longer missing.
    """
    from .models import A11yScreenScan

    run_key = str(audit.id)
    with tenant_context(tenant_id):
        reported = set(
            A11yScreenScan.objects
            .filter(tenant_id=tenant_id, project_id=audit.project_id, run_key=run_key)
            .values_list("route", flat=True)
        )
        missing = [route for route in (audit.routes or []) if route not in reported]
        for route in missing:
            A11yScreenScan.objects.update_or_create(
                tenant_id=tenant_id, project_id=audit.project_id, run_key=run_key, route=route,
                defaults={"run_id": None, "url": "", "screen_hash": "", "violations": [],
                          "scan_error": "", "load_error": NEVER_REPORTED},
            )
    return [{"route": route, "reason": NEVER_REPORTED} for route in missing]


def finish_baseline_audit(*, tenant_id, audit_id, trigger=None, reason: str = "") -> dict:
    """Close the capture window, account for every route, and ask the AI checks.

    Returns what happened in numbers a person can check — how many routes were asked for, how
    many reported, how many never opened, and what the judgment pass did with the rest. Those
    numbers are the audit's own honesty check: "we audited the app" is not a claim anyone should
    have to take on trust.

    The AI pass never fails this call (it swallows its own failures by design), and neither does
    the reconciliation: a route recorded as unreachable is a result, not an error. What *is*
    refused is finishing an audit that captured nothing at all, because there is no honest
    report to publish from an empty pass — the status goes to `failed` and says why.

    `reason` lets the machine that ran the audit say why nothing came back, and it is used in
    place of the generic explanation below. The generic one assumes the application was the
    problem; when the truth is that the auditing machine had no browser installed, sending
    someone to check a server that was never contacted wastes the one thing a failure report
    exists to save. Only used when nothing opened — a reason cannot overrule a real capture.
    """
    from .aipass import start_ai_pass
    from .models import A11yBaselineAudit, A11yScreenScan

    audit = _audit(tenant_id, audit_id)
    run_key = str(audit.id)
    unreachable = reconcile_routes(tenant_id=tenant_id, audit=audit)

    with tenant_context(tenant_id):
        scans = list(
            A11yScreenScan.objects
            .filter(tenant_id=tenant_id, project_id=audit.project_id, run_key=run_key)
            .values_list("route", "load_error")
        )
    # Queried AFTER the reconciliation, so the routes it just wrote are already in here — one
    # place that knows which routes failed, rather than two lists to keep in step.
    opened = [route for route, load_error in scans if not (load_error or "").strip()]
    summary: dict = {
        "asked": len(audit.routes or []),
        "opened": len(opened),
        "unreachable": sorted(route for route, err in scans if (err or "").strip()),
        "never_reported": sorted(item["route"] for item in unreachable),
    }
    if not opened:
        summary["reason"] = str(reason or "").strip() or (
            "not one of this audit's routes could be opened, so there is nothing to report on. "
            "Check that the application was running and reachable from the machine that ran the "
            "audit, and that the routes registered are the ones it actually serves."
        )
        with tenant_context(tenant_id):
            audit.status = A11yBaselineAudit.Status.FAILED
            audit.summary = summary
            audit.save(update_fields=["status", "summary", "updated_at"])
        return {"audit_id": run_key, "status": audit.status, **summary}

    # Before the judging, because it is a fact about the capture and belongs on the audit even
    # if the AI half never starts.
    summary["names"] = _name_coverage(tenant_id, str(audit.project_id), run_key)

    result = start_ai_pass(
        tenant_id=tenant_id, project_id=str(audit.project_id), run_id=run_key,
        title=_title(audit), trigger=trigger,
        triggered_by=str(audit.started_by_id) if audit.started_by_id else None,
    )
    summary["ai_pass"] = {k: v for k, v in result.items() if k != "report"}
    # A pass that dispatched nothing has already published its report (everything was cached, or
    # there was no judge to ask); one that dispatched is still in flight and completes when the
    # judge's run ends — see `aipass.finish_ai_pass`, which closes this audit from there.
    started = bool(result.get("started"))
    with tenant_context(tenant_id):
        audit.status = (A11yBaselineAudit.Status.JUDGING if started
                        else A11yBaselineAudit.Status.COMPLETE)
        audit.summary = summary
        audit.save(update_fields=["status", "summary", "updated_at"])
    out = {"audit_id": run_key, "status": audit.status, "report": result.get("report"),
           **summary}
    if not started:
        # Everything knowable is known, so the baseline is written now (QA-18). When a judge
        # IS dispatched it is written after that run ends instead — a baseline published while
        # half the verdicts are still in flight would state a position that is about to change.
        out["baseline"] = publish_baseline_for(tenant_id=tenant_id, audit=audit)
    return out


#: Tags whose elements essentially always have an accessible name — a link or a button with
#: visible text has one by definition, and a heading takes its name from its own text. If a whole
#: capture holds these and NOT ONE of them was named, the browser did not answer, and that is a
#: fact about the machine rather than about the application.
NAMEABLE_TAGS = ("a", "button", "input", "select", "textarea", "summary",
                 "h1", "h2", "h3", "h4", "h5", "h6")

NAMES_UNREAD = (
    "the browser returned no accessible name for any element on any page, so the "
    "**Label in Name** check (2.5.3) could not run — it compares the name a screen reader "
    "announces against the visible text, and had nothing to compare. Every other check ran "
    "normally. This is a fault on the machine that captured the pages, not in the application: "
    "update the companion and audit again."
)


def _name_coverage(tenant_id, project_id, run_key: str) -> dict:
    """Did the browser actually answer when asked what each element is called?

    **Why the platform checks its own input.** The capture asks the browser for every element's
    computed accessible name, and one element failing is normal and harmless — the label check
    skips it. *Every* element failing is a broken toolchain, and it is invisible: the elements
    all arrive, three of the four checks run perfectly, and the fourth simply never selects
    anything. That is exactly what happened. `page.accessibility` was removed from Playwright,
    the capture's per-element `catch` swallowed the failure on all of them, and **2.5.3 never
    selected a single element in the entire life of the feature** — found on the live audit of
    21 August, by noticing that one checker's count had always been zero.

    Checked here rather than trusted from the capture, because a capture written by an older
    companion cannot report a problem nobody knew to look for yet. Counted over the elements the
    platform kept, which is enough: a page with no links, buttons or headings at all is not a
    page anyone audits.
    """
    from .models import A11yCandidateBundle

    with tenant_context(tenant_id):
        rows = list(
            A11yCandidateBundle.objects
            .filter(tenant_id=tenant_id, project_id=project_id, run_key=str(run_key))
            .values_list("element", flat=True)
        )
    nameable = 0
    named = 0
    for element in rows:
        element = element or {}
        if str(element.get("tag") or "").lower() not in NAMEABLE_TAGS:
            continue
        nameable += 1
        if str(element.get("accessible_name") or "").strip():
            named += 1
    out = {"named": named, "nameable": nameable}
    if nameable and not named:
        out["reason"] = NAMES_UNREAD
    return out


def publish_baseline_for(*, tenant_id, audit) -> dict:
    """Write this project's baseline, with the audit's own coverage stated in it. Never raises.

    Best-effort like every other document on this path: an audit that found real problems, filed
    them and opened their defects has done its job, and losing the summary document is a smaller
    loss than losing any of that. The reason comes back rather than being swallowed.
    """
    from .baseline_report import publish_baseline

    try:
        return publish_baseline(tenant_id=tenant_id, project_id=str(audit.project_id),
                                audit=audit)
    except Exception as exc:  # noqa: BLE001 — see the docstring
        return {"artifact_id": None, "error": str(exc)}


def _title(audit) -> str:
    """What this audit's report is called. Distinct per audit, because a baseline you cannot
    tell apart from the next one is not a baseline."""
    return f"baseline audit {str(audit.id)[:8]}"


def complete_audit(tenant_id, capture_key) -> bool:
    """Mark the audit this capture key belongs to complete. False when the key is not an audit.

    Called when a judgment run ends. Kept here rather than in `aipass` so that module stays
    ignorant of what a capture key might name — it treats every key the same, which is exactly
    why a baseline audit could reuse it without changing anything.
    """
    from django.core.exceptions import ValidationError

    from .models import A11yBaselineAudit

    if not str(capture_key or "").strip():
        return False
    with tenant_context(tenant_id):
        try:
            audit = A11yBaselineAudit.objects.filter(id=capture_key, tenant_id=tenant_id).first()
        except (ValidationError, ValueError):
            # A capture key that is not a UUID at all — a CI post's empty key, or a future
            # caller's own scheme. Not an audit, and not an error either.
            return False
        if audit is None:
            return False
        audit.status = A11yBaselineAudit.Status.COMPLETE
        audit.save(update_fields=["status", "updated_at"])
    # Now, and not a moment earlier: the verdicts are in and the defects are reconciled, so the
    # baseline states a position that has actually settled (QA-18). Writing it when the audit's
    # capture closed would have published a standing that was still changing.
    publish_baseline_for(tenant_id=tenant_id, audit=audit)
    return True


#: The statuses an audit can be in while something is still happening to it. Progress is asked
#: for these and nobody else: a finished audit's numbers are already frozen on its `summary`,
#: and re-deriving them would be two sources for one answer.
IN_FLIGHT_STATUSES = ("pending", "claimed", "capturing", "judging")

#: The one state an audit can be in that NOTHING could recover it from, and so the only state
#: this module's abandonment applies to. An audit here is held by a machine on somebody's desk
#: that this server can never see, and it got here because a screen arrived.
#:
#: The other three are deliberately absent, each already answered somewhere better:
#:   * `pending`  — nobody has taken it; there is nothing wrong with it and the claim offers it.
#:   * `claimed`  — taken but nothing captured yet, and the claim lease hands a stale one to the
#:                  next machine that asks. RE-CLAIMING IS STRICTLY BETTER THAN FAILING IT: the
#:                  audit simply runs. Closing these here would have thrown that away.
#:   * `judging`  — a Temporal run, closed from the other end by `close_unfinished_ai_pass`.
ABANDONABLE_STATUSES = ("capturing",)

#: What a person is told when the machine holding their audit went away. In the audit's own
#: `summary["reason"]`, which is what the "Could not run" panel reads.
ABANDONED_REASON = (
    "the machine visiting the pages stopped reporting — it was closed, restarted or "
    "disconnected part-way through. What it had already captured is kept, but nothing is "
    "reported from a partial pass: a baseline written from some of the pages would state "
    "coverage this audit never had. Start the audit again."
)


def _last_screen_at(tenant_id, audits) -> dict:
    """The newest screen posted under each audit's key. One grouped query for the whole set."""
    from django.db.models import Max

    from .models import A11yScreenScan

    keys = [str(a.id) for a in audits]
    if not keys:
        return {}
    with tenant_context(tenant_id):
        rows = (
            A11yScreenScan.objects
            .filter(tenant_id=tenant_id, run_key__in=keys)
            .values("run_key").annotate(last=Max("created_at"))
        )
        return {row["run_key"]: row["last"] for row in rows}


def stalled_audit_ids(tenant_id, audits, *, stale_before) -> set[str]:
    """Which of these audits nothing has been heard from since `stale_before`. **Reads only.**

    **Why liveness is measured from the work and not only from the claim.** An audit is captured
    by a machine outside the platform, so the only evidence it is still there is that it is still
    talking to us — and it talks in two ways: the companion's heartbeat (which renews
    `claimed_at`, see `_renew_claims_for`) and the screens themselves. Either counts. Keying on
    the heartbeat alone would make this depend on a companion mode that might not heartbeat;
    keying on screens alone would kill an audit stuck on one very slow page. Whichever spoke
    last is the answer.

    `stale_before` is passed in rather than read from a constant here, because how long a
    machine may be silent is the runner's lease policy (`api.runner_views.CLAIM_LEASE`) and this
    module has no business deciding it.
    """
    held = [a for a in audits if a.status in ABANDONABLE_STATUSES]
    latest = _last_screen_at(tenant_id, held)
    out = set()
    for audit in held:
        spoke = [audit.claimed_at or audit.created_at]
        seen = latest.get(str(audit.id))
        if seen:
            spoke.append(seen)
        if max(spoke) < stale_before:
            out.add(str(audit.id))
    return out


def abandon_audit(*, tenant_id, audit_id, reason: str = "") -> dict:
    """Close ONE audit whose machine stopped reporting. Returns what it was closed as.

    **Failed, not resumed, and not judged.** Half a capture is in the database under this
    audit's key, and it is kept — but it is not sent to the judge and no baseline is published
    from it. A report from four of twelve pages would be this capability's own worst failure
    wearing a tick: a document stating a position about an application, most of which was never
    looked at. The pages that did report are cheap to visit again.

    **Not resumed either**, and that is a deliberate limit rather than an oversight. Re-visiting
    routes already captured under this key would need a resumption design that does not exist —
    what happens to the bundles already stored for a route being visited a second time — and a
    fresh audit costs minutes. Resumption is worth its own task if a capture ever gets long
    enough for the difference to matter.

    Idempotent, and only ever acts on an audit a companion is actually holding: an audit that
    has already closed, or is in `judging` (a Temporal run, closed from the other end), is
    returned untouched with `closed: False`.
    """
    from .models import A11yBaselineAudit, A11yScreenScan

    audit = _audit(tenant_id, audit_id)
    if audit.status not in ABANDONABLE_STATUSES:
        return {"audit_id": str(audit.id), "status": audit.status, "closed": False}

    run_key = str(audit.id)
    with tenant_context(tenant_id):
        scans = list(
            A11yScreenScan.objects
            .filter(tenant_id=tenant_id, project_id=audit.project_id, run_key=run_key)
            .values_list("route", "load_error")
        )
        seen = {route for route, _ in scans}
        summary = {
            "asked": len(audit.routes or []),
            "opened": len({r for r, err in scans if not (err or "").strip()}),
            "unreachable": sorted({r for r, err in scans if (err or "").strip()}),
            # What was asked for and never came back. Said plainly rather than folded into
            # `unreachable`: these pages were never attempted, which is not the same fact as a
            # page that would not open, and the difference is what somebody re-running needs.
            "never_reported": sorted(r for r in (audit.routes or []) if r not in seen),
            "reason": str(reason or "").strip() or ABANDONED_REASON,
            #: So a reader (and a test) can tell this apart from an audit that ran and found
            #: nothing openable — same status, entirely different thing to go and do.
            "abandoned": True,
        }
        audit.status = A11yBaselineAudit.Status.FAILED
        audit.summary = {**(audit.summary or {}), **summary}
        audit.save(update_fields=["status", "summary", "updated_at"])
    return {"audit_id": run_key, "status": audit.status, "closed": True, **summary}


def abandon_stale_audits(*, tenant_id, project_id=None, stale_before, reason: str = "") -> list:
    """Close every audit on this project that a machine stopped reporting on. Returns their ids.

    Called from the companion's own writes — its heartbeat and its audit claim — rather than
    from anything a screen asks for, so reading the audit list never writes to it. That also
    puts the sweep exactly where the evidence arrives: a machine that reboots comes back, says
    hello, and the audit it abandoned is closed within seconds of it doing so.
    """
    from .models import A11yBaselineAudit

    with tenant_context(tenant_id):
        rows = A11yBaselineAudit.objects.filter(
            tenant_id=tenant_id, status__in=ABANDONABLE_STATUSES)
        if project_id:
            rows = rows.filter(project_id=project_id)
        rows = list(rows)

    stale = stalled_audit_ids(tenant_id, rows, stale_before=stale_before)
    closed = []
    for row in rows:
        if str(row.id) in stale:
            abandon_audit(tenant_id=tenant_id, audit_id=str(row.id), reason=reason)
            closed.append(str(row.id))
    return closed


def audit_progress(tenant_id, audit_ids: list[str]) -> dict:
    """How far each of these audits has actually got, right now (S-38 running panel).

    **Why this is derived and not stored.** `summary` is written once, when the audit closes —
    so for the whole time an audit is running there is no count of anything anywhere, and the
    only thing a screen could say was the status word. Yesterday's live run spent forty minutes
    on `Checking what was found` with no way for the person who started it to see that the judge
    was at 81 of 144, or that it had stopped. The rows this reads are being written the whole
    time; nothing new has to be recorded to be able to say so.

    Two counts per audit, from two grouped queries over the whole set rather than a query per
    audit — the panel polls every 5 seconds:

      * **visited / unreachable** — screen scans posted under this audit's key. `unreachable` is
        a page the browser could not open, which is a RESULT and is counted as visited-and-known
        rather than as progress not yet made.
      * **judged / dispatched** — once the AI pass has started, how many of the elements it was
        given have a verdict recorded. `dispatched` comes off the audit's own summary, written
        when the pass was dispatched, so the denominator is the real one and not a guess.

    Returns `{audit_id: {...}}`, missing nothing and inventing nothing: an audit that has had no
    screen posted yet is `{"visited": 0, "unreachable": 0}` with no judging keys at all, which is
    what lets a screen tell "none yet" from "not that stage".
    """
    from django.db.models import Count, Q

    from .models import A11yBaselineAudit, A11yJudgmentCache, A11yScreenScan

    keys = [str(a) for a in audit_ids if str(a or "").strip()]
    if not keys:
        return {}
    out: dict[str, dict] = {key: {"visited": 0, "unreachable": 0} for key in keys}

    with tenant_context(tenant_id):
        scans = (
            A11yScreenScan.objects
            .filter(tenant_id=tenant_id, run_key__in=keys)
            .values("run_key")
            .annotate(
                visited=Count("id"),
                # A load error is stored as text, so "no error" is the empty string, not NULL.
                unreachable=Count("id", filter=~Q(load_error="")),
            )
        )
        for row in scans:
            out[str(row["run_key"])].update(
                visited=row["visited"], unreachable=row["unreachable"])

        # The judging half. Only for audits that actually dispatched a pass — the judge run id
        # and the element count are both on the summary written at dispatch.
        judge_runs = {}
        for audit in A11yBaselineAudit.objects.filter(tenant_id=tenant_id, id__in=keys):
            ai_pass = (audit.summary or {}).get("ai_pass") or {}
            run_id = str(ai_pass.get("judge_run_id") or "")
            if run_id:
                judge_runs[run_id] = str(audit.id)
                out[str(audit.id)].update(
                    judged=0, dispatched=_distinct_dispatched(tenant_id, run_id, ai_pass))
        if judge_runs:
            judged = (
                A11yJudgmentCache.objects
                .filter(tenant_id=tenant_id, run_id__in=list(judge_runs))
                .values("run_id").annotate(n=Count("id"))
            )
            for row in judged:
                out[judge_runs[str(row["run_id"])]]["judged"] = row["n"]
    return out


def _distinct_dispatched(tenant_id, judge_run_id, ai_pass: dict) -> int:
    """How many DISTINCT elements this judging pass was asked about.

    **Not the number of requests, and the difference is not a rounding error.** The same markup
    on ten pages — a site header, a footer link — is one thing to judge: it hashes identically,
    one verdict answers all ten, and the completeness check counts it once. On our own reference
    application 144 requests were 81 distinct elements, so a tile counting verdicts against
    requests reported a finished, correct audit as two-thirds done. A screen saying a third of
    the checking did not happen when it did is the exact failure this whole capability exists to
    refuse, so the denominator has to be the same unit as the numerator.

    Recorded at dispatch (`aipass.start_ai_pass`) and read from there. Derived from the run's
    own batches only for a pass dispatched before that was recorded, so an audit that predates
    this still shows a true number rather than the old misleading one.
    """
    distinct = ai_pass.get("distinct")
    if isinstance(distinct, int) and distinct > 0:
        return distinct
    from apps.runs.models import Run

    with tenant_context(tenant_id):
        run = Run.objects.filter(id=judge_run_id, tenant_id=tenant_id).first()
    batches = ((run.inputs or {}).get("a11y_batches") or []) if run else []
    hashes = {element.get("content_hash")
              for screen in batches for element in (screen.get("elements") or [])
              if element.get("content_hash")}
    return len(hashes) or int(ai_pass.get("dispatched") or 0)


def passes_for(route_count: int) -> int:
    """How many capture passes a route count takes. One document holds `capture.MAX_SCREENS`
    pages, so a bigger audit runs in more passes rather than visiting the first 60 (D-B5)."""
    from .capture import MAX_SCREENS

    return max(1, -(-int(route_count or 0) // MAX_SCREENS))


#: The statuses an audit is CLOSED in. A re-judge is only offered for these: while a pass is
#: still running, "how many were never looked at" has no settled answer.
CLOSED_STATUSES = ("complete", "failed")


def unanswered_counts(tenant_id, audits) -> dict:
    """How many elements of each audit NOTHING ever looked at — for the button that offers to
    ask again (task R1).

    Counted from what each pass already recorded about itself, in one extra query for the whole
    list rather than a walk through every audit's stored elements:

      * `summary.ai_pass.filed_unjudged` — elements the dispatch could not ask about at all,
        because there was no judge registered or no machine connected;
      * `summary.ai_pass.deferred_distinct` — elements the dispatch **stopped short of**,
        having reached this run's limit. Neither filed nor handed to a run, so before this they
        were counted nowhere and an audit closed as complete with them silently unchecked;
      * the judge run's own `outputs[UNANSWERED_KEY]` — elements it was given and never reported
        on. Written by `judge._remember_unanswered` at the only moment the two kinds of
        `uncertain` are still distinguishable.

    The three are disjoint by construction: the first two were never dispatched (for different
    reasons), the third was.

    Both are counted in DISTINCT ELEMENTS, which is what the screen has to say and what a
    re-judge would actually ask about. `deferred` on its own is element-and-check *slots*, and
    the tail of a capped pass is usually markup dispatched earlier in the same run — counting it
    raw put a "check the rest" button on an audit with nothing left to check.

    ⚠️ **This is the count for a screen, not the list a re-judge acts on.** The authoritative set
    is recomputed by `aipass.unanswered_for_capture`, which also intersects with what the capture
    still holds — so an audit whose stored elements have since gone shows a number here and asks
    about nothing, saying so. Doing that intersection for fifty audits on every poll would mean
    reading every bundle of every audit to draw a badge.
    """
    from apps.runs.models import Run

    from .judge import UNANSWERED_KEY

    out: dict[str, int] = {}
    judge_runs: dict[str, str] = {}
    for audit in audits:
        ai_pass = (audit.summary or {}).get("ai_pass") or {}
        filed = ai_pass.get("filed_unjudged")
        # `deferred_distinct`, never `deferred`: the raw number is request slots, and the tail of
        # a capped pass is usually markup already dispatched earlier in the same run. An audit
        # from before this key existed has no honest count available, so it reports none rather
        # than the misleading one — the same choice the "elements judged" tile made.
        deferred = ai_pass.get("deferred_distinct")
        out[str(audit.id)] = ((int(filed) if isinstance(filed, int) else 0)
                              + (int(deferred) if isinstance(deferred, int) else 0))
        run_id = str(ai_pass.get("judge_run_id") or "")
        if run_id:
            judge_runs[run_id] = str(audit.id)
    if judge_runs:
        with tenant_context(tenant_id):
            rows = Run.objects.filter(
                tenant_id=tenant_id, id__in=list(judge_runs)).values_list("id", "outputs")
        for run_id, outputs in rows:
            recorded = (outputs or {}).get(UNANSWERED_KEY) or []
            out[judge_runs[str(run_id)]] += len(recorded)
    return out


def audit_outcome(tenant_id, project_id) -> dict:
    """Where this project stands, for the panel that stays on screen after a run ends.

    The panel does not disappear when the audit finishes — it changes what it says. A person who
    started an audit and watched it work must not have the answer vanish at the moment it
    arrives; that is the same silence the running panel was built against, one step later.

    **Project-wide, and that is the honest scope rather than a convenience.** A finding carries
    no audit key: `last_seen_run` is a foreign key to a real `Run`, and a baseline audit
    deliberately manufactures none (QA-17), so for every brownfield audit that column is NULL.
    Counting on it would have reported **0 problems on an audit that found three** — the exact
    kind of confident, wrong, reassuring number this whole capability exists to refuse.

    Project scope is also the right question. The **Accessibility baseline** this panel points at
    is itself scoped to the project rather than to one audit, precisely so an audit that reached
    38 of 50 routes does not silently drop what is already known about the other 12. "Where does
    this application stand?" is the question a baseline answers, and this is that number.

    Two counts, kept apart on purpose: a problem the platform is sure about, and a question it is
    asking a person. Folding the second into the first would inflate the problem count with
    things nobody has decided yet.
    """
    from django.db.models import Count, Q

    from .models import A11yFinding
    from .triage import TRIAGE_REVIEW

    with tenant_context(tenant_id):
        row = (
            A11yFinding.objects
            .filter(tenant_id=tenant_id, project_id=project_id,
                    status=A11yFinding.Status.OPEN)
            .aggregate(
                problems=Count("id", filter=~Q(outcome=TRIAGE_REVIEW)),
                critical=Count("id", filter=Q(severity="critical") & ~Q(outcome=TRIAGE_REVIEW)),
                high=Count("id", filter=Q(severity="high") & ~Q(outcome=TRIAGE_REVIEW)),
                waiting=Count("id", filter=Q(outcome=TRIAGE_REVIEW)),
            )
        )
    return {k: int(v or 0) for k, v in row.items()}
