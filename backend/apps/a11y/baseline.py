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
                         started_by=None):
    """Freeze what this audit will visit and open it for capture. Returns the audit.

    `routes` overrides the registry for a one-off pass; left out, the project's enabled routes
    are used. Either way the list is **stored on the audit**, not re-read at the end: the audit
    has to be able to say "this was asked for and never came back", and a list re-read later
    would make a route added mid-pass indistinguishable from one that failed.

    Refuses an empty list rather than starting a pass that can only report nothing. An audit
    that finishes having checked no pages is the exact shape of a clean result, and producing
    one because nobody registered a route would be the worst kind of quiet success.
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

    with tenant_context(tenant_id):
        return A11yBaselineAudit.objects.create(
            tenant_id=tenant_id, project_id=project_id,
            base_url=str(base_url or "")[:512], routes=ordered,
            status=A11yBaselineAudit.Status.CAPTURING, started_by_id=started_by or None,
        )


def audit_manifest(audit) -> dict:
    """What the audit script is given: where the app is, and which paths to visit.

    A manifest rather than a generated script. The visiting logic — drive a browser to a URL,
    wait for it to settle, run the scanner if one is available, write down the elements and one
    picture — is the same for every audit of every project, so it lives in one reviewed file
    that ships with the companion (`runner/companion/assets/a11y_audit.mjs`). Only the inputs
    differ, and only the inputs are produced here. Synthesising JavaScript per audit would put
    a program nobody can test in the middle of a compliance chain.
    """
    return {
        "version": MANIFEST_VERSION,
        "audit_id": str(audit.id),
        "project_id": str(audit.project_id),
        "base_url": audit.base_url,
        "routes": list(audit.routes or []),
        "output": CAPTURE_FILENAME,
    }


def ingest_audit_capture(*, tenant_id, audit_id, text: str, object_store=None) -> dict:
    """Store one posted capture against this audit's own bucket.

    The audit's id is the `run_key`, so its screens sit apart from every build's and from the
    project-wide bucket a CI post lands in. Everything downstream reads that key as a string;
    see `models.A11yBaselineAudit` for why there is no `Run` behind it.
    """
    from .ingest import ingest_capture

    audit = _audit(tenant_id, audit_id)
    return ingest_capture(
        tenant_id=tenant_id, project_id=str(audit.project_id), text=text,
        run_key=str(audit.id), object_store=object_store,
    )


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


def finish_baseline_audit(*, tenant_id, audit_id, trigger=None) -> dict:
    """Close the capture window, account for every route, and ask the AI checks.

    Returns what happened in numbers a person can check — how many routes were asked for, how
    many reported, how many never opened, and what the judgment pass did with the rest. Those
    numbers are the audit's own honesty check: "we audited the app" is not a claim anyone should
    have to take on trust.

    The AI pass never fails this call (it swallows its own failures by design), and neither does
    the reconciliation: a route recorded as unreachable is a result, not an error. What *is*
    refused is finishing an audit that captured nothing at all, because there is no honest
    report to publish from an empty pass — the status goes to `failed` and says why.
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
        summary["reason"] = (
            "not one of this audit's routes could be opened, so there is nothing to report on. "
            "Check that the application was running and reachable from the machine that ran the "
            "audit, and that the routes registered are the ones it actually serves."
        )
        with tenant_context(tenant_id):
            audit.status = A11yBaselineAudit.Status.FAILED
            audit.summary = summary
            audit.save(update_fields=["status", "summary", "updated_at"])
        return {"audit_id": run_key, "status": audit.status, **summary}

    result = start_ai_pass(
        tenant_id=tenant_id, project_id=str(audit.project_id), run_id=run_key,
        title=_title(audit), trigger=trigger,
        triggered_by=str(audit.started_by_id) if audit.started_by_id else None,
    )
    summary["ai_pass"] = {k: v for k, v in result.items() if k != "report"}
    # A pass that dispatched nothing has already published its report (everything was cached, or
    # there was no judge to ask); one that dispatched is still in flight and completes when the
    # judge's run ends — see `aipass.finish_ai_pass`, which closes this audit from there.
    with tenant_context(tenant_id):
        audit.status = (A11yBaselineAudit.Status.JUDGING if result.get("started")
                        else A11yBaselineAudit.Status.COMPLETE)
        audit.summary = summary
        audit.save(update_fields=["status", "summary", "updated_at"])
    return {"audit_id": run_key, "status": audit.status, "report": result.get("report"),
            **summary}


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
    return True
