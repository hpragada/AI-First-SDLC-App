"""Running a baseline accessibility audit from the machine that can see the app (QA-17).

A sibling of `a11ycapture.py`, and held to the same rule for the same reason: **this module
knows only where things are and how to run them; the platform owns what any of it means.** The
capture format belongs to `apps.a11y.capture`, the route list and the reconciliation belong to
`apps.a11y.baseline`, and nothing here decides whether a page is accessible.

The shape of a pass:

    platform  →  open the audit, hand back the routes to visit  (start_a11y_audit)
    here      →  run `assets/a11y_audit.mjs` against the running app, once per PASS
    here      →  post each captured screen, one per call        (ingest_a11y_audit_screen)
    platform  →  account for every route asked for, then judge  (finish_a11y_audit)

**One audit, as many passes as it takes (B5).** `capture.MAX_SCREENS` bounds ONE capture
document, not an application: a screen carries a full-page screenshot, and a file with hundreds
of them is refused by the platform. Screens are posted one per HTTP call, so nothing downstream
knows or cares how many files there were — the audit is reconciled against its stored route
list, whatever produced the rows. So an audit larger than that bound runs in several passes
against the same audit, rather than visiting the first 60 pages and leaving the rest to a line
on a console nobody is watching.

**Every step reports rather than assumes.** A route that would not open is written into the
capture by the script; a route that never appears at all is caught by the platform's
reconciliation. Between the two there is no way for a page to be quietly missed, which is the
only property that makes a baseline worth reading.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

from runner.companion.state_client import SLOW_TIMEOUT_S

#: The audit script, shipped with the companion rather than generated per audit. See the file's
#: own header: driving a browser over a list of URLs is the same for every project, and a
#: program synthesised per run is a program nobody reviews.
AUDIT_SCRIPT = Path(__file__).resolve().parent / "assets" / "a11y_audit.mjs"

#: Long enough for a slow first paint on every route in a full manifest, short enough that a
#: wedged browser does not hold a developer's terminal for an afternoon.
DEFAULT_TIMEOUT_S = 1_800


def run_audit_script(manifest: dict, *, workdir, node: str = "node",
                     timeout: float = DEFAULT_TIMEOUT_S) -> dict:
    """Visit the manifest's routes and return `{screens, output, stderr, returncode}`.

    Never raises on a failed run. A script that dies halfway has still captured the routes it
    reached, and those screens are worth posting: the platform will record the rest as never
    reported, which is a far better outcome than throwing away real coverage because the pass
    did not finish cleanly.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    manifest_path = workdir / "a11y-audit-manifest.json"
    output_path = workdir / (manifest.get("output") or "test-results/a11y-candidates.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        completed = subprocess.run(  # noqa: S603 — fixed script, arguments are ours
            [node, str(AUDIT_SCRIPT), str(manifest_path), str(output_path)],
            cwd=str(workdir), capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        returncode, stderr = completed.returncode, completed.stderr or ""
    except FileNotFoundError:
        return {"screens": [], "output": str(output_path), "returncode": 127,
                "stderr": f"{node!r} is not on PATH, so the audit script could not be run"}
    except subprocess.TimeoutExpired:
        returncode, stderr = 124, f"the audit did not finish within {timeout:.0f}s"

    return {"screens": read_capture(output_path), "output": str(output_path),
            "returncode": returncode, "stderr": stderr}


def preflight(*, workdir, node: str = "node", timeout: float = 120.0) -> dict:
    """Can this folder run an audit at all? Asked BEFORE one starts.

    Without this the answer arrives the expensive way round: the audit is opened, every route
    is asked for, nothing can be visited, and the platform reports an application that failed
    to respond — when in truth no browser was ever installed. Two very different problems that
    looked identical from the outside.

    **The two tools are not equally fatal and the answer says so.** No browser means no page can
    be opened and there is nothing to do. No scanner means the pass still runs and only the
    measurable half is missing — every screen already carries its own `axe_error` saying that,
    and an audit with the AI checks alone is worth having.

    Never raises. A check that cannot run is reported as a browser we could not confirm, which
    is the same conclusion by a different road.
    """
    try:
        completed = subprocess.run(  # noqa: S603 — fixed script, arguments are ours
            [node, str(AUDIT_SCRIPT), "--check"],
            cwd=str(workdir), capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return {"ok": False, "cwd": str(workdir),
                "browser": {"ok": False,
                            "error": f"{node!r} is not on PATH, so nothing can be run here"},
                "scanner": {"ok": False, "version": "", "error": ""}}
    except subprocess.TimeoutExpired:
        return {"ok": False, "cwd": str(workdir),
                "browser": {"ok": False,
                            "error": f"checking this folder did not finish within {timeout:.0f}s"},
                "scanner": {"ok": False, "version": "", "error": ""}}
    try:
        out = json.loads(completed.stdout or "{}")
    except ValueError:
        out = {}
    if not isinstance(out, dict) or "browser" not in out:
        return {"ok": False, "cwd": str(workdir),
                "browser": {"ok": False,
                            "error": "the audit script could not report what this folder has "
                                     f"({(completed.stderr or '').strip()[:200]})"},
                "scanner": {"ok": False, "version": "", "error": ""}}
    out["ok"] = bool((out.get("browser") or {}).get("ok"))
    return out


def read_capture(path) -> list[dict]:
    """The screens the script left behind, through the platform's one parser.

    `[]` for an absent or unreadable file, which is the honest answer for "nothing was
    captured" — the platform then has an audit whose every route went unreported, and says so.
    """
    from apps.a11y.capture import CaptureError, parse_capture  # lazy: backend on path by now

    path = Path(path)
    if not path.is_file():
        return []
    try:
        return parse_capture(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, CaptureError) as exc:
        print(f"[companion] the audit capture was not stored: {exc}")
        return []


def post_audit_screens(screens: list[dict], *, client, audit_id: str) -> dict:
    """Send the captured screens to the platform, one screen per call.

    One call per screen for the reason `a11ycapture.post_a11y_candidates` gives: a screen
    carries a full-page PNG, and a body holding ten of them is past what the request layer
    accepts — a size limit is a bad place to discover a compliance capture was thrown away.

    Never raises. A screen that will not post costs that screen, is named, and the audit
    finishes: the platform will record it as never reported, which is exactly what happened.
    """
    posted, failed = 0, []
    for screen in screens:
        route = screen.get("route", "")
        try:
            client.call("ingest_a11y_audit_screen", audit_id=audit_id, screen=screen)
            posted += 1
        except Exception as exc:  # noqa: BLE001 — see the docstring: one screen, never the pass
            failed.append(f"{route}: {exc}")
            print(f"[companion] the capture for {route} was not posted: {exc}")
    return {"posted": posted, "failed": failed}


def pass_output(output: str, index: int, total: int) -> str:
    """Where pass `index` writes, given the manifest's output path.

    **Every pass writes its own file, and that is load-bearing.** `run_audit_script` reads the
    file the script was told to write. Share one filename between passes and a pass that dies
    before writing leaves the PREVIOUS pass's file in place — which would be read again and
    posted a second time, reporting pages as seen in a pass that never visited them. That is
    precisely the failure this whole feature exists to prevent, so it is designed out rather
    than guarded against: a pass that dies produces no screens, and its routes come back from
    the platform's reconciliation as never reported, which is what happened.

    A single-pass audit keeps the plain name, so nothing changes for a project that has always
    fitted in one.
    """
    if total <= 1:
        return output
    path = PurePosixPath(output)
    return str(path.with_name(f"{path.stem}-pass-{index}{path.suffix}"))


def run_baseline_audit(*, client, project_id: str, workdir, base_url: str = "",
                       routes=None, node: str = "node", audit_id: str = "",
                       timeout: float = DEFAULT_TIMEOUT_S) -> dict:
    """Open an audit, visit its routes in passes, post what was seen, and close it.

    `audit_id` is an audit this machine was HANDED rather than one it opens. The screen creates
    the audit and a companion claims it, so opening another here would leave two audits for one
    press of a button — one being visited and one waiting forever for a machine. Given an id,
    the manifest is fetched for that audit instead of a new one being started; everything after
    that point is identical, which is the point.

    Returns everything a person needs to judge the audit without opening a database: which
    routes were asked for, how it was divided, how many screens came back from each pass, what
    the script said on the way, and what the platform made of it.

    `base_url` is optional (B3). Left empty, the platform resolves the address it already holds
    for the project and sends it back on the manifest — which is what the script visits, so the
    address is never typed twice and never diverges from the one a build uses. The platform
    refuses the audit outright when it holds none, rather than handing back a manifest that
    cannot be visited.

    **A failed pass never abandons the audit.** The remaining passes still run and the audit is
    still closed: a pass that dies costs its own routes, which the reconciliation records as
    never reported, and throwing away the pages that DID come back would be the worse trade.
    """
    # One definition of the bound, imported rather than retyped: `capture.MAX_SCREENS` is what
    # the platform refuses a document for, so the companion must not drift from it.
    from apps.a11y.capture import MAX_SCREENS  # lazy: backend on path by now

    ready = preflight(workdir=workdir, node=node)
    if (ready.get("scanner") or {}).get("error"):
        print(f"[companion] {ready['scanner']['error']}", file=sys.stderr)

    if audit_id:
        opened = client.call("get_a11y_audit", audit_id=audit_id)
    else:
        opened = client.call("start_a11y_audit", project_id=project_id, base_url=base_url,
                             routes=routes)
    audit_id = opened["audit_id"]
    manifest = opened["manifest"]
    asked = list(manifest.get("routes") or [])
    output = manifest.get("output") or "test-results/a11y-candidates.json"

    if not ready["ok"]:
        # Opened and closed without visiting anything, ON PURPOSE. The audit still exists and
        # still accounts for every route it was asked for — the platform records them as never
        # reported — but it carries the REAL reason instead of the generic "the application did
        # not respond", which would send someone to check a server that was never contacted.
        reason = (ready.get("browser") or {}).get("error") or "this folder cannot run an audit"
        print(f"[companion] {reason}", file=sys.stderr)
        finished = client.call("finish_a11y_audit", _timeout=SLOW_TIMEOUT_S,
                               audit_id=audit_id, reason=reason)
        return {"audit_id": audit_id, "routes": asked, "passes": [], "captured": 0,
                "posted": 0, "post_failures": [], "script_returncode": 3,
                "preflight": ready, "finished": finished}

    batches = [asked[i:i + MAX_SCREENS] for i in range(0, len(asked), MAX_SCREENS)]
    print(f"[companion] {len(asked)} page(s) | {len(batches)} pass(es)")

    passes: list[dict] = []
    captured, posted, failures = 0, 0, []
    for index, batch in enumerate(batches, start=1):
        print(f"[companion] pass {index}/{len(batches)} - {len(batch)} page(s)")
        ran = run_audit_script(
            {**manifest, "routes": batch,
             "output": pass_output(output, index, len(batches))},
            workdir=workdir, node=node, timeout=timeout,
        )
        if ran["stderr"]:
            print(ran["stderr"], file=sys.stderr)
        post = post_audit_screens(ran["screens"], client=client, audit_id=audit_id)
        captured += len(ran["screens"])
        posted += post["posted"]
        failures += post["failed"]
        passes.append({
            "pass": index, "routes": len(batch), "captured": len(ran["screens"]),
            "posted": post["posted"], "script_returncode": ran["returncode"],
        })

    # The one call in this module whose work is measured in minutes: it reconciles the route
    # list, hashes every captured element and starts the judging run. See `SLOW_TIMEOUT_S`.
    finished = client.call("finish_a11y_audit", _timeout=SLOW_TIMEOUT_S, audit_id=audit_id)
    return {
        "audit_id": audit_id,
        "routes": asked,
        "preflight": ready,
        "passes": passes,
        "captured": captured,
        "posted": posted,
        "post_failures": failures,
        # Non-zero when ANY pass failed — a person reading one number must not be told the audit
        # was clean because the last pass happened to be.
        "script_returncode": max((p["script_returncode"] for p in passes), default=0),
        "result": finished,
    }
