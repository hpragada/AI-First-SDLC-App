"""Storing a captured screen as candidate bundles (QA-11b).

One screen arrives as a capture document: what was on the page, and one image of the whole
page. This turns it into the rows the AI pass reads — and does the two things that keep the
scan affordable and honest, in this order:

  1. **Select, then crop** (team decision, 2026-08-14). The rules in `checkers.rules` decide
     which elements any of the AI checks apply to, and only those get an image cut for them.
     A screen offers a few hundred elements and yields a few dozen candidates, so cropping
     first would spend most of its work on elements nobody will ever ask about.

     The capture cannot do this itself: the rules are Python and live here, and by the time
     Python can run them the browser is closed and the app is gone. So the capture takes **one
     page screenshot** and each element's rectangle within it, and the crop happens here, from
     an image we already hold. That is the same ordering the backlog asked for, performed on
     the other machine — and it costs one image per screen instead of one per element.

  2. **An element with no picture is stored, not dropped.** `uncapturable_reason` records why,
     the judge is told, and its Rule 2 records `uncertain` naming the missing image. Dropping
     it would put the platform in the business of deciding an element it never looked at was
     fine — and that decision would be invisible in the conformance report.

Bodies live in the object store and state keeps pointers (#1/#3): the page image and every crop
are objects, and a bundle row carries only their keys.
"""
from __future__ import annotations

import io
from hashlib import sha256

from apps.tenancy.context import tenant_context

from . import coverage, page_rules
from .capture import fingerprint, screenshot_bytes

#: Long edge a stored crop is reduced to. Element crops are small already; this only catches a
#: full-width hero on a retina capture, and keeps what the judge is sent inside the transport
#: budget `_build_page_image_window` enforces on the way out.
CROP_MAX_PX = 1024

#: Padding around an element's rectangle, in the screenshot's own pixels. 1.4.1 is a question
#: about an element *against its surroundings* — a status dot cropped to its own bounding box
#: is a coloured circle with nothing to compare it to.
CROP_PADDING_PX = 12


def _object_store(injected=None):
    if injected is not None:
        return injected
    from storage import s3_from_settings

    return s3_from_settings()


def _crop(page_png: bytes, box: dict) -> tuple[bytes, str]:
    """The element's region of the page image, or (b"", reason).

    Best-effort by design: one element that will not crop must not cost the screen. Every
    failure returns a sentence the judge can quote as the reason it could not see something.
    """
    try:
        from PIL import Image as PILImage
    except ImportError as exc:  # pragma: no cover - deployment fault, same as the vision pipe
        raise RuntimeError(
            "Pillow is not installed, so accessibility element crops cannot be produced. It is "
            "in requirements.txt — the image is likely stale and needs rebuilding."
        ) from exc

    try:
        with PILImage.open(io.BytesIO(page_png)) as im:
            width, height = im.size
            left = max(0, int(box["x"]) - CROP_PADDING_PX)
            top = max(0, int(box["y"]) - CROP_PADDING_PX)
            right = min(width, int(box["x"] + box["width"]) + CROP_PADDING_PX)
            bottom = min(height, int(box["y"] + box["height"]) + CROP_PADDING_PX)
            if right <= left or bottom <= top:
                return b"", (
                    "the element's rectangle falls outside the page screenshot, so no image of "
                    "it could be cut"
                )
            region = im.crop((left, top, right, bottom))
            if region.mode not in ("RGB", "RGBA", "L"):
                region = region.convert("RGB")
            long_edge = max(region.size)
            if long_edge > CROP_MAX_PX:
                ratio = CROP_MAX_PX / long_edge
                region = region.resize(
                    (max(1, round(region.width * ratio)), max(1, round(region.height * ratio))),
                    # `Resampling.LANCZOS`, not the bare `PILImage.LANCZOS` the vision pipe
                    # uses: identical at runtime, and the only one of the two that type-checks.
                    PILImage.Resampling.LANCZOS,
                )
            out = io.BytesIO()
            region.save(out, format="PNG")
            return out.getvalue(), ""
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001 — one bad crop costs an element, never the screen
        return b"", f"the element's image could not be cut from the page screenshot ({exc})"


def _image_key(tenant_id, project_id, kind: str, data: bytes) -> str:
    """An image's key, derived from **its own bytes** rather than from the run that took it.

    This is load-bearing, and getting it wrong is silent. `dispatch.content_hash` fingerprints
    everything the judge looks at — the markup, the surrounding text, and *the pointer to the
    picture* — so that a cached verdict can never be stale. Naming a crop after its run gave the
    same untouched element a new pointer on every run, so the fingerprint changed every time and
    **the cache could never hit**: every run would re-judge every element of every screen, which
    is exactly the cost QA-07 exists to prevent. It was invisible because nothing dispatches yet.

    Content-addressing fixes both directions at once. An unchanged element re-renders to
    byte-identical pixels, so the same name, so the same fingerprint, so a cache hit. A changed
    element produces different pixels and a different name, so it is judged again — which is
    correct, and is the property the cache's own safety argument rests on.

    Consequence worth knowing: a screen whose pixels genuinely differ between runs (a clock, a
    rotating banner, a carousel mid-animation) will re-judge. That is the right answer rather
    than a defect — the visual question may have a different answer — but it means caching pays
    off on stable screens and not on animated ones.
    """
    return f"a11y/{tenant_id}/{project_id}/{kind}/{sha256(data).hexdigest()}.png"


def _carry_forward(tenant_id, project_id, run_key: str, run_id, route: str, screen_hash: str):
    """This run's rows for a screen already captured identically before, or None (QA-07).

    **Skip the work, never the coverage.** The obvious saving is to notice an unchanged screen
    and do nothing — and that would be wrong: a run's candidates are read by its own run key,
    so a screen that produced no rows for this run would simply be absent from what the AI pass
    covers, and absent from the conformance report, with nothing anywhere saying why. So the
    previous capture's rows are copied to this run instead. No decode, no crop, no object
    write; the crop pointers stay valid because a picture is named after its own bytes.

    Deliberately keyed on (project, route, screen_hash) and NOT on the run: the point is to
    recognise the screen across runs. Rows already filed under *this* run key are excluded, so
    re-posting a screen inside one run still takes the ordinary idempotent path.
    """
    from .models import A11yCandidateBundle

    with tenant_context(tenant_id):
        previous = list(
            A11yCandidateBundle.objects
            .filter(tenant_id=tenant_id, project_id=project_id, route=route,
                    screen_hash=screen_hash)
            .exclude(run_key=run_key)
            .order_by("-created_at", "position")
        )
        if not previous:
            return None
        # One prior capture, not a merge of several: rows from two different runs of the same
        # screen are the same rows, and taking the newest run's set keeps them consistent.
        source_run = previous[0].run_key
        rows = [row for row in previous if row.run_key == source_run]
        for row in sorted(rows, key=lambda r: r.position):
            A11yCandidateBundle.objects.update_or_create(
                tenant_id=tenant_id, project_id=project_id, run_key=run_key,
                route=route, selector=row.selector,
                defaults={
                    "run_id": run_id or None,
                    "position": row.position,
                    "url": row.url,
                    "checkers": list(row.checkers),
                    "element": row.element,
                    "axe": row.axe,
                    "screenshot_ref": row.screenshot_ref,
                    "uncapturable_reason": row.uncapturable_reason,
                    "screen_hash": screen_hash,
                },
            )
    uncapturable = sum(1 for row in rows if not row.screenshot_ref)
    return {
        "route": route,
        "captured": len(rows),
        "selected": len(rows),
        "skipped": 0,
        "uncapturable": uncapturable,
        "page_image": any(row.screenshot_ref for row in rows),
        # No image work happens on this path by design, so this run took no page screenshot —
        # but the review console still has one to show, because `_record_scan` inherited the
        # pointer from the earlier capture of this identical screen. Reported as blank because
        # that is the truth about THIS ingest; the scan row is where the pointer lives.
        "page_image_ref": "",
        "page_image_reason": "",
        "reused": True,
        "screen_hash": screen_hash,
    }


def _record_scan(tenant_id, project_id, run_key: str, run_id, screen: dict,
                 screen_hash: str) -> int:
    """Store what the rule scanner said about this whole screen (QA-12). Returns the count.

    Written on EVERY ingest, including one that carries its elements forward, and written
    before the carry-forward check rather than inside it. Two reasons, both learned from the
    bug QA-07 opened with: it costs nothing (a small JSON document, no decode, no crop, no
    object write), and a screen whose scan was only stored on the path that does the expensive
    work is a screen whose scan silently disappears the second time it is captured.
    """
    from .models import A11yScreenScan

    violations = list(screen.get("axe_violations") or [])
    route = str(screen.get("route") or "")
    with tenant_context(tenant_id):
        # An identical screen has identical pixels, and a picture is named after its own bytes
        # (`_image_key`) — so the page image a previous run stored for this exact screen_hash is
        # byte-for-byte the one this capture would produce, under the same key. Inheriting it
        # here is what gives the carry-forward path (QA-07, which deliberately does no image
        # work at all) a page to show the reviewer. Without it, every screen the cache saved
        # money on would be a screen with no picture in the review console.
        inherited = (
            A11yScreenScan.objects
            .filter(tenant_id=tenant_id, project_id=project_id, route=route,
                    screen_hash=screen_hash)
            .exclude(page_image_ref="")
            .order_by("-created_at")
            .values_list("page_image_ref", flat=True)
            .first()
        ) or ""
        A11yScreenScan.objects.update_or_create(
            tenant_id=tenant_id, project_id=project_id, run_key=run_key,
            route=route,
            defaults={
                "run_id": run_id or None,
                "url": str(screen.get("url") or "")[:200],
                "screen_hash": screen_hash,
                "violations": violations,
                "axe_passes": list(screen.get("axe_passes") or []),
                "axe_inapplicable": list(screen.get("axe_inapplicable") or []),
                "axe_incomplete": list(screen.get("axe_incomplete") or []),
                "scanner_version": str(screen.get("scanner_version") or "")[:64],
                "scan_error": str(screen.get("axe_error") or "")[:1_000],
                "load_error": str(screen.get("load_error") or "")[:1_000],
                "page_image_ref": inherited,
                # The narrow-viewport and control-edge readings (QA-25). Stored as they were
                # taken; `page_rules` is what turns them into failures and coverage, below.
                "page_measurements": dict(screen.get("page_measurements") or {}),
            },
        )
    # What the scan says about each CRITERION, not just what it failed (QA-24). Written on the
    # same path and for the same reason the scan row is: it costs nothing, and coverage recorded
    # only where the expensive work happens is coverage that silently disappears the second time
    # a screen is captured.
    # The scanner's own four channels, and — since QA-25 — the two criteria it has no rule for.
    # Recorded under the SAME `rule` engine, because that is what they are: a deterministic
    # measurement the platform took because axe does not take it. Giving them an engine of their
    # own would make a conformance statement read as though a third kind of tool had been
    # involved, and `_RANK` already collapses several engines' views of one criterion correctly.
    coverage.record(
        tenant_id=tenant_id, project_id=project_id, run_key=run_key, run_id=run_id,
        route=route, engine="rule",
        observations=[
            *coverage.from_scan(screen),
            *page_rules.observations_for(screen.get("page_measurements")),
        ],
    )
    return len(violations)


def ingest_screen(*, tenant_id, project_id, screen: dict, run_id=None, run_key=None,
                  object_store=None) -> dict:
    """Store one captured screen's candidate bundles. Idempotent per (run, route, selector).

    Returns what happened in numbers a person can check: how many elements the capture offered,
    how many the rules selected, how many were dropped and how many have no image. Those
    numbers are the answer to "was this screen really checked?", so they are reported rather
    than inferred from a row count.

    **`run_key` and `run_id` are two different things, and QA-17 is why.** The key is the
    partition every reader groups a capture by; the id is a foreign key to an actual agent run.
    They were the same string until a baseline audit needed a bucket of its own without
    inventing a `Run` nobody executed (see `models.A11yBaselineAudit`). Pass `run_key` alone
    for a capture that belongs to no run; pass `run_id` and the key follows from it, which is
    what every existing caller does.
    """
    from .checkers.rules import CapturedElement, checkers_for
    from .models import A11yCandidateBundle, A11yScreenScan

    route = str(screen.get("route") or "")
    elements = list(screen.get("elements") or [])
    run_key = str(run_id or "") if run_key is None else str(run_key)
    store = _object_store(object_store)

    # QA-07: has this exact screen already been captured for this project? If so, carry those
    # rows forward and do no image work at all. Checked before anything is decoded or cropped,
    # because everything below this line is the cost being avoided.
    screen_hash = fingerprint(screen)
    violations = _record_scan(tenant_id, project_id, run_key, run_id, screen, screen_hash)
    carried = _carry_forward(tenant_id, project_id, run_key, run_id, route, screen_hash)
    if carried is not None:
        return {**carried, "violations": violations}

    page_png, page_reason = screenshot_bytes(screen)
    page_ref = ""
    if page_png:
        try:
            page_ref = _image_key(tenant_id, project_id, "pages", page_png)
            store.put(page_ref, page_png, content_type="image/png")
        except Exception as exc:  # noqa: BLE001 — the elements still matter without the picture
            page_png, page_ref = b"", ""
            page_reason = f"the page screenshot could not be stored ({exc})"
    if page_ref:
        # The key was previously computed inline as an argument and never kept, so the page
        # image existed in the object store with nothing anywhere pointing at it (QA-23).
        with tenant_context(tenant_id):
            A11yScreenScan.objects.filter(
                tenant_id=tenant_id, project_id=project_id, run_key=run_key, route=route,
            ).update(page_image_ref=page_ref)

    stored = 0
    uncapturable = 0
    with tenant_context(tenant_id):
        for index, raw in enumerate(elements):
            element = CapturedElement.from_dict(raw)
            # SELECTION FIRST — this is the line the ordering decision is about. Everything
            # below it (a crop, an object write, a row) happens only for an element at least
            # one of the AI checks actually applies to.
            checkers = checkers_for(element)
            if not checkers:
                continue

            selector = element.selector or f"{route}#{index}"
            box = (raw or {}).get("box") or {}
            screenshot_ref, reason = "", ""
            if not page_png:
                reason = page_reason
            elif not box:
                reason = (
                    "the capture recorded no on-screen rectangle for this element, so no image "
                    "of it could be cut"
                )
            else:
                crop, reason = _crop(page_png, box)
                if crop:
                    key = _image_key(tenant_id, project_id, "elements", crop)
                    try:
                        store.put(key, crop, content_type="image/png")
                        screenshot_ref = key
                    except Exception as exc:  # noqa: BLE001
                        reason = f"the element's image could not be stored ({exc})"
            if not screenshot_ref:
                uncapturable += 1

            A11yCandidateBundle.objects.update_or_create(
                tenant_id=tenant_id, project_id=project_id, run_key=run_key,
                route=route, selector=selector[:512],
                defaults={
                    "run_id": run_id or None,
                    "position": index,
                    "url": str(screen.get("url") or "")[:200],
                    "checkers": list(checkers),
                    "element": raw,
                    "axe": (raw or {}).get("axe") or {},
                    "screenshot_ref": screenshot_ref,
                    "uncapturable_reason": reason,
                    "screen_hash": screen_hash,
                },
            )
            stored += 1

    return {
        "route": route,
        "captured": len(elements),
        "selected": stored,
        "skipped": len(elements) - stored,
        "uncapturable": uncapturable,
        "page_image": bool(page_png),
        "page_image_ref": page_ref,
        "page_image_reason": page_reason,
        "reused": False,
        "screen_hash": screen_hash,
        "violations": violations,
    }


def ingest_capture(*, tenant_id, project_id, text: str, run_id=None, run_key=None,
                   object_store=None) -> dict:
    """Parse a posted capture document and store every screen in it.

    `imported` is False when the body held no readable screen — the caller maps that to a 4xx,
    exactly as the CI JUnit endpoint does, so a capture that never ran is never a quiet 200.
    """
    from .capture import parse_capture, summarize

    screens = parse_capture(text)
    if not screens:
        return {"imported": False, "reason": "no readable screens in the capture body",
                "screens": [], "summary": "no accessibility capture"}
    results = [
        ingest_screen(tenant_id=tenant_id, project_id=project_id, screen=screen,
                      run_id=run_id, run_key=run_key, object_store=object_store)
        for screen in screens
    ]
    reused = sum(1 for r in results if r["reused"])
    summary = summarize(screens)
    if reused:
        # Said out loud, because "did the saving work?" is otherwise unanswerable — and the
        # cache defect this task opened with was invisible for exactly that reason.
        summary = f"{summary}; {reused} screen(s) unchanged and carried forward"
    return {
        "imported": True,
        "screens": results,
        "captured": sum(r["captured"] for r in results),
        "selected": sum(r["selected"] for r in results),
        "skipped": sum(r["skipped"] for r in results),
        "uncapturable": sum(r["uncapturable"] for r in results),
        "reused_screens": reused,
        "violations": sum(r["violations"] for r in results),
        "summary": summary,
    }


def requests_for(tenant_id, project_id, run_id=None) -> list:
    """The stored bundles as dispatch requests — what QA-12 hands to `dispatch_judgments`.

    Order is stable — route, then the element's own position on the page, then `CHECKERS` order
    within it — for the same reason `rules.select` is: a judgment run that cannot be reproduced
    cannot be compared against the golden set. Ordering by primary key would look right and be
    wrong; the key is a UUID and says nothing about sequence.
    """
    from .checkers.rules import CHECKERS, CapturedElement, to_candidate
    from .dispatch import A11yRequest
    from .models import A11yCandidateBundle

    with tenant_context(tenant_id):
        rows = list(
            A11yCandidateBundle.objects
            .filter(tenant_id=tenant_id, project_id=project_id, run_key=str(run_id or ""))
            .order_by("route", "position", "selector")
        )
    requests: list = []
    for row in rows:
        element = CapturedElement.from_dict({
            **(row.element or {}),
            # The pointer the platform produced, not whatever the capture claimed — the crop is
            # ours and the capture has no way to know its key.
            "screenshot_ref": row.screenshot_ref,
            "route": row.route,
            "selector": row.selector,
        })
        candidate = to_candidate(element)
        requests.extend(
            A11yRequest(checker=checker, candidate=candidate)
            for checker in CHECKERS if checker in (row.checkers or [])
        )
    return requests
