"""Storing a captured screen as candidate bundles (QA-11b).

One screen arrives as a capture document: what was on the page, and one image of the whole
page. This turns it into the rows the AI pass reads — and does the two things that keep the
scan affordable and honest, in this order:

  1. **Select, then crop** (team decision, 2026-08-14). The rules in `checkers.rules` decide
     which elements any of the four checks apply to, and only those get an image cut for them.
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

from apps.tenancy.context import tenant_context

from .capture import screenshot_bytes

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


def _slug(value: str) -> str:
    """A route as a safe object-key segment. `/` becomes `_` so the key stays one level."""
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(value or ""))
    return safe.strip("_")[:120] or "root"


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


def _page_key(tenant_id, project_id, run_key: str, route: str) -> str:
    return f"a11y/{tenant_id}/{project_id}/{run_key or 'norun'}/{_slug(route)}/page.png"


def _crop_key(tenant_id, project_id, run_key: str, route: str, index: int) -> str:
    return (
        f"a11y/{tenant_id}/{project_id}/{run_key or 'norun'}/{_slug(route)}/"
        f"element-{index:04d}.png"
    )


def ingest_screen(*, tenant_id, project_id, screen: dict, run_id=None, object_store=None) -> dict:
    """Store one captured screen's candidate bundles. Idempotent per (run, route, selector).

    Returns what happened in numbers a person can check: how many elements the capture offered,
    how many the rules selected, how many were dropped and how many have no image. Those
    numbers are the answer to "was this screen really checked?", so they are reported rather
    than inferred from a row count.
    """
    from .checkers.rules import CapturedElement, checkers_for
    from .models import A11yCandidateBundle

    route = str(screen.get("route") or "")
    elements = list(screen.get("elements") or [])
    run_key = str(run_id or "")
    store = _object_store(object_store)

    page_png, page_reason = screenshot_bytes(screen)
    if page_png:
        try:
            store.put(_page_key(tenant_id, project_id, run_key, route), page_png,
                      content_type="image/png")
        except Exception as exc:  # noqa: BLE001 — the elements still matter without the picture
            page_png, page_reason = b"", f"the page screenshot could not be stored ({exc})"

    stored = 0
    uncapturable = 0
    with tenant_context(tenant_id):
        for index, raw in enumerate(elements):
            element = CapturedElement.from_dict(raw)
            # SELECTION FIRST — this is the line the ordering decision is about. Everything
            # below it (a crop, an object write, a row) happens only for an element at least
            # one of the four checks actually applies to.
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
                    key = _crop_key(tenant_id, project_id, run_key, route, index)
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
        "page_image_reason": page_reason,
    }


def ingest_capture(*, tenant_id, project_id, text: str, run_id=None, object_store=None) -> dict:
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
                      run_id=run_id, object_store=object_store)
        for screen in screens
    ]
    return {
        "imported": True,
        "screens": results,
        "captured": sum(r["captured"] for r in results),
        "selected": sum(r["selected"] for r in results),
        "skipped": sum(r["skipped"] for r in results),
        "uncapturable": sum(r["uncapturable"] for r in results),
        "summary": summarize(screens),
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
