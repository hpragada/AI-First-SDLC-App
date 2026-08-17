"""Running a baseline accessibility audit from the machine that can see the app (QA-17).

A sibling of `a11ycapture.py`, and held to the same rule for the same reason: **this module
knows only where things are and how to run them; the platform owns what any of it means.** The
capture format belongs to `apps.a11y.capture`, the route list and the reconciliation belong to
`apps.a11y.baseline`, and nothing here decides whether a page is accessible.

The shape of a pass:

    platform  →  open the audit, hand back the routes to visit  (start_a11y_audit)
    here      →  run `assets/a11y_audit.mjs` against the running app
    here      →  post each captured screen, one per call        (ingest_a11y_audit_screen)
    platform  →  account for every route asked for, then judge  (finish_a11y_audit)

**Every step reports rather than assumes.** A route that would not open is written into the
capture by the script; a route that never appears at all is caught by the platform's
reconciliation. Between the two there is no way for a page to be quietly missed, which is the
only property that makes a baseline worth reading.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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


def run_baseline_audit(*, client, project_id: str, base_url: str, workdir,
                       routes=None, node: str = "node",
                       timeout: float = DEFAULT_TIMEOUT_S) -> dict:
    """Open an audit, visit its routes, post what was seen, and close it.

    Returns everything a person needs to judge the pass without opening a database: which
    routes were asked for, how many screens came back, what the script said on the way, and
    what the platform made of it.
    """
    opened = client.call("start_a11y_audit", project_id=project_id, base_url=base_url,
                         routes=routes)
    manifest = opened["manifest"]
    ran = run_audit_script(manifest, workdir=workdir, node=node, timeout=timeout)
    if ran["stderr"]:
        print(ran["stderr"], file=sys.stderr)
    post = post_audit_screens(ran["screens"], client=client, audit_id=opened["audit_id"])
    finished = client.call("finish_a11y_audit", audit_id=opened["audit_id"])
    return {
        "audit_id": opened["audit_id"],
        "routes": manifest["routes"],
        "captured": len(ran["screens"]),
        "posted": post["posted"],
        "post_failures": post["failed"],
        "script_returncode": ran["returncode"],
        "result": finished,
    }
