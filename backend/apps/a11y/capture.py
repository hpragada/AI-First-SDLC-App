"""Reading a capture document — the platform's ONE parser for what a screen looked like (QA-11b).

The app under test runs on the developer's machine, at a `localhost` address this server cannot
reach. A rendered page — its DOM, its computed styles, the name a screen reader would announce,
a picture of it — exists there for the few minutes the suite runs, and then the app is stopped
and the worktree deleted. Everything the AI pass will ever look at has to be taken during that
window and sent here.

This module owns **what a capture means**. The companion owns only **where the file is**
(`runner/companion/a11ycapture.py`), exactly as `runner/companion/testresults.py` knows where a
JUnit report lives while `apps.quality.junit` knows what one says. Two readers of a compliance
format is two formats.

**Nothing here decides what gets judged.** Selection is `checkers.rules`, run at ingest, and
deliberately after this: a capture is a record of what was on the page, and narrowing it is a
separate decision made in one place that a reviewer can read.

**Bounds are refusals, not truncations.** A document over the limits is rejected with its
reason rather than quietly clipped — a capture that silently lost half a page would produce a
conformance report claiming those elements were fine.
"""
from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from hashlib import sha256

#: The format version the companion writes and this parser reads. Bumped only for a change a
#: reader must know about; a *new field* is not one — `CapturedElement.from_dict` ignores what
#: it does not read, on purpose, so the capture can grow without a lockstep release.
CAPTURE_VERSION = 1

#: What one document may carry. Sized from the header's ~10 screens/run and ~50 screens/app
#: assumption, with room above it: a run that captures 60 screens has gone wrong in a way that
#: should be said out loud, not absorbed.
MAX_SCREENS = 60
MAX_ELEMENTS_PER_SCREEN = 600

#: One page screenshot's decoded size, and the number is not a taste judgement. A screen is
#: posted as ONE request body, and Django's `DATA_UPLOAD_MAX_MEMORY_SIZE` defaults to 2.5 MiB —
#: base64 adds a third, so anything much past this is refused by the *request layer* before this
#: parser ever runs, and that refusal is a 500 with no useful message rather than the sentence
#: below. 1.5 MB decoded is ~2.0 MB encoded, leaving room for the elements and the JSON envelope
#: travelling in the same body. A full-page PNG of a long page at viewport width is 200-400 KB,
#: so this is generous; what it actually catches is a capture taken at full device-pixel
#: resolution, which is the mistake that produces a 6 MB screenshot.
MAX_SCREENSHOT_BYTES = 1_500_000

#: How much markup and surrounding text travel per element. Long enough to carry a real
#: component, short enough that 600 of them is not a runaway document.
MAX_HTML_CHARS = 8_000
MAX_CONTEXT_CHARS = 4_000
MAX_SELECTOR_CHARS = 512


class CaptureError(ValueError):
    """A capture document could not be read. Carries what was wrong, for a human."""


def _text(value, limit: int) -> str:
    out = "" if value is None else str(value)
    return out[:limit]


def _mapping(value) -> dict:
    return {str(k): v for k, v in value.items()} if isinstance(value, Mapping) else {}


def _box(value) -> dict:
    """An element's rectangle in the page screenshot's own pixel space, or {} if unusable.

    Rejected rather than repaired when it is not a positive-area rectangle: cropping from a
    degenerate box produces a blank image, and a blank image shown to the judge as evidence is
    worse than no image at all — it looks like something was seen.
    """
    raw = _mapping(value)
    try:
        box = {k: float(raw.get(k, 0) or 0) for k in ("x", "y", "width", "height")}
    except (TypeError, ValueError):
        return {}
    if box["width"] <= 0 or box["height"] <= 0:
        return {}
    return box


def _element(raw) -> dict:
    """One captured element, bounded and normalised.

    Every key `rules.CapturedElement` reads is passed straight through — this does not decide
    what is present, only what is too big. A missing key is the capture's problem to answer for
    (`rules.STYLE_KEYS` says why a missing style is dangerous), and inventing a default here
    would hide exactly that.
    """
    data = _mapping(raw)
    return {
        "selector": _text(data.get("selector"), MAX_SELECTOR_CHARS),
        "tag": _text(data.get("tag"), 64).strip().lower(),
        "role": _text(data.get("role"), 64).strip().lower(),
        "attrs": {str(k).lower(): _text(v, 2_000) for k, v in _mapping(data.get("attrs")).items()},
        "text": _text(data.get("text"), MAX_CONTEXT_CHARS),
        "accessible_name": _text(data.get("accessible_name"), MAX_CONTEXT_CHARS),
        "interactive": bool(data.get("interactive")),
        # Absent means rendered, matching `CapturedElement.from_dict`: a capture that forgot the
        # field must not make every element invisible to every checker.
        "rendered": bool(data.get("rendered", True)),
        "styles": {str(k).lower(): _text(v, 256) for k, v in _mapping(data.get("styles")).items()},
        "parent_styles": {
            str(k).lower(): _text(v, 256)
            for k, v in _mapping(data.get("parent_styles")).items()
        },
        "html": _text(data.get("html"), MAX_HTML_CHARS),
        "context": _text(data.get("context"), MAX_CONTEXT_CHARS),
        "box": _box(data.get("box")),
        "axe": _mapping(data.get("axe")),
    }


def _screen(raw) -> dict:
    data = _mapping(raw)
    route = _text(data.get("route") or data.get("url"), 512)
    if not route:
        raise CaptureError("a captured screen has no route — name the path it was taken on")
    elements = data.get("elements")
    if not isinstance(elements, list):
        raise CaptureError(f"screen {route!r} has no `elements` list")
    if len(elements) > MAX_ELEMENTS_PER_SCREEN:
        raise CaptureError(
            f"screen {route!r} captured {len(elements)} elements, over the limit of "
            f"{MAX_ELEMENTS_PER_SCREEN}. Nothing was stored for it — capture the elements the "
            f"four checks look at, not every node on the page."
        )
    return {
        "route": route,
        "url": _text(data.get("url"), 1_000),
        "screenshot_base64": _text(data.get("screenshot_base64"), MAX_SCREENSHOT_BYTES * 2),
        # Why there is no picture, in the capture's own words. Carried through to the judge, so
        # "could not be seen" is a reported fact rather than an absence someone has to infer.
        "screenshot_error": _text(data.get("screenshot_error"), 1_000),
        "elements": [_element(e) for e in elements],
    }


def screenshot_bytes(screen: Mapping) -> tuple[bytes, str]:
    """The screen's page image as bytes, or (b"", reason). Never raises.

    A screenshot that will not decode is a missing screenshot with an explanation, not a failed
    ingest: the elements on that page are still worth judging from their markup, and the ones
    that needed to be seen will come back `uncertain` naming this reason.
    """
    if error := str(screen.get("screenshot_error") or "").strip():
        return b"", error
    encoded = str(screen.get("screenshot_base64") or "")
    if not encoded:
        return b"", "no page screenshot was captured for this screen"
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        return b"", f"the page screenshot could not be decoded ({exc})"
    # No "decoded to nothing" branch: a non-empty string either decodes to bytes or fails
    # validation above, and an empty one was already answered. A branch nothing can reach is a
    # branch nobody can test, which is worse than not having it.
    if len(raw) > MAX_SCREENSHOT_BYTES:
        return b"", (
            f"the page screenshot is {len(raw)} bytes, over the {MAX_SCREENSHOT_BYTES}-byte "
            f"limit — capture it at the viewport width, not at full device-pixel resolution"
        )
    return raw, ""


def parse_capture(text: str) -> list[dict]:
    """Every screen in a capture document, in the order it was captured.

    Accepts the whole document (`{"version": 1, "screens": [...]}`) or a single screen object,
    because the two posters send different things for a good reason: the companion posts one
    screen per call so a page's screenshot never has to share an HTTP body with nine others,
    while a CI job posts the file it was left.

    `[]` for an empty or unreadable body — the honest answer for "no capture", and the caller
    stores nothing rather than recording a screen with no elements as a clean page. A document
    that IS readable but breaks a bound raises `CaptureError`, because that is a real capture
    saying something that must not be silently narrowed.
    """
    body = (text or "").strip()
    if not body:
        return []
    try:
        data = json.loads(body)
    except ValueError:
        return []
    if isinstance(data, list):
        data = {"screens": data}
    if not isinstance(data, Mapping):
        return []

    version = data.get("version", CAPTURE_VERSION)
    try:
        # Parsed on its own line, NOT around the raise below: `CaptureError` is a `ValueError`
        # subclass, so a `try` wrapping both would catch the version-too-new error and report
        # it as "not a number" — the wrong message for the one case that needs the right one.
        number = int(version)
    except (TypeError, ValueError) as exc:
        raise CaptureError(f"capture `version` must be a number, got {version!r}") from exc
    if number > CAPTURE_VERSION:
        raise CaptureError(
            f"this capture is format version {number}; this platform reads up to "
            f"{CAPTURE_VERSION}. Nothing was stored — update the platform rather than "
            f"reading a format it does not know."
        )

    screens = data.get("screens")
    if screens is None:
        screens = [data] if data.get("elements") is not None else []
    if not isinstance(screens, list):
        raise CaptureError("`screens` must be a list of captured screens")
    if len(screens) > MAX_SCREENS:
        raise CaptureError(
            f"this capture holds {len(screens)} screens, over the limit of {MAX_SCREENS}. "
            f"Nothing was stored — post them in smaller batches."
        )
    return [_screen(screen) for screen in screens]


def fingerprint(screen: Mapping) -> str:
    """One screen's identity — everything about it that could change what gets judged (QA-07).

    Two captures of a screen nobody touched produce the same string, which is what lets the
    platform skip the work of cropping and storing it again. So this has to cover **every**
    fact downstream reads: the selection rules read the tag, role, attributes, text, accessible
    name, interactivity and computed styles; the judge reads the markup, the surrounding text
    and the picture. Leave one out and an unchanged-looking screen would be skipped after a
    change that mattered — a stale verdict in a compliance report, which is the one failure
    this whole layer exists to prevent.

    So it hashes the elements **whole**, rather than a chosen subset. A capture that grows a
    new field therefore changes the fingerprint and costs one re-judgment, which is the safe
    direction: re-doing work is expensive, and skipping work that needed doing is wrong.

    The page image is hashed by its bytes, so a re-render that shifted a pixel is a different
    screen. That is deliberate for the same reason, and it means this saving lands on stable
    screens rather than on animated ones.
    """
    digest = sha256()
    digest.update(str(screen.get("route") or "").encode("utf-8"))
    image, reason = screenshot_bytes(screen)
    digest.update(sha256(image).digest() if image else reason.encode("utf-8"))
    digest.update(
        json.dumps(list(screen.get("elements") or []), sort_keys=True,
                   separators=(",", ":"), default=str).encode("utf-8")
    )
    return digest.hexdigest()


def summarize(screens: list[dict]) -> str:
    """One line for the run console — the platform's single summarizer for a capture."""
    if not screens:
        return "no accessibility capture"
    elements = sum(len(s.get("elements") or []) for s in screens)
    unseen = sum(1 for s in screens if not (s.get("screenshot_base64") or "").strip())
    line = f"{elements} element(s) captured on {len(screens)} screen(s)"
    return f"{line}, {unseen} with no page image" if unseen else line
