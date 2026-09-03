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

#: What one DOCUMENT may carry, and deliberately not what an application may have (B5). A screen
#: carries a full-page screenshot, so a file with hundreds of them is refused here rather than
#: absorbed. An audit bigger than this runs in several passes against the same audit
#: (`runner.companion.a11yaudit.run_baseline_audit`) and posts screens one per call, so this
#: bound has never limited how many pages a project may check — it limits how big one file gets.
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

#: What the rule scanner said about the screen AS A WHOLE (QA-12). Generous, because these are
#: small objects and a genuinely bad page produces a lot of them: refusing a real scan would be
#: worse than carrying it. Over the limit is still a refusal rather than a trim, for the same
#: reason every other bound here is — a scan that quietly lost half its violations reads as a
#: page with half as much wrong with it.
MAX_AXE_VIOLATIONS = 400
MAX_AXE_NODES = 500

#: How many node-less rule results one screen may report per channel — `passes` and
#: `inapplicable` (QA-24). axe ships on the order of a hundred rules and our six WCAG tags
#: select a subset of them, which the four channels then partition, so a real page lands well
#: under this. Anything near it means the scan was run without the tag filter, and that is worth
#: refusing out loud rather than storing a document nobody meant to produce.
MAX_AXE_RULES = 400

#: What one screen's page-level measurements may carry (QA-25). Both are small by construction —
#: the companion already stops at these numbers and says so — so a document over the limit did
#: not come from our companion, and is refused rather than trimmed for the same reason every
#: other bound here is.
MAX_REFLOW_OFFENDERS = 20
MAX_CONTRAST_COMPONENTS = 200


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

    ⚠️ **That sentence is a promise, and it was broken silently** (24 Aug). `structure` and
    `markup_truncated` were added to the element contract, to the selection rules, to the cache
    key, to the batch the judge receives and to the judge's own instructions — and not to the
    list below, which is the only thing that decides what survives to storage. The browser
    measured every table's shape, the platform received it, and this function dropped it.
    Across 371 captured elements on a seventeen-page audit, elements carrying an outline: zero.
    The judge is told "start with the outline" and was handed the field name with nothing in it.

    Nothing failed, because nothing compared the two lists.
    `test_a11y_capture.test_every_field_the_contract_reads_is_actually_stored` does now, and it
    is the reason this can only go wrong once.
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
        # True when `html` above is only the beginning of the element's markup. A backstop for
        # detail further down a long container, not the answer to a question about its shape —
        # `structure` is that, and it is whole however large the container is.
        "markup_truncated": bool(data.get("markup_truncated")),
        # The container's shape as the browser measured it: rows, columns, which cells are
        # headers and what they are scoped to, whether a group of fields is grouped. Bounded by
        # how WIDE a container is rather than how long, so a 401-row table costs 906 characters
        # where its markup costs 31,985 and would be cut at 8,000.
        #
        # Absent for anything that is not a container, and that absence is meaningful: an empty
        # outline must never be readable as an empty table. A container the capture could not
        # describe arrives as `{"kind": "unreadable"}` with a reason instead — "we could not
        # look" and "there is no structure here" are different answers.
        "structure": _mapping(data.get("structure")),
        "context": _text(data.get("context"), MAX_CONTEXT_CHARS),
        # What the element sits inside — tag, role, href and its own text. Small and bounded,
        # because it is an identity and not a document. `context` above is the parent's words,
        # and an icon-only control's parent has none: both 1.1.1 and 1.4.11 ask what the parent
        # IS, and until 1 September nothing carried that.
        "parent": {str(k): _text(v, 400) for k, v in _mapping(data.get("parent")).items()},
        "box": _box(data.get("box")),
        "axe": _mapping(data.get("axe")),
    }


def _violation(raw, route: str) -> dict:
    """One thing the rule scanner proved about this screen, normalised (QA-12).

    Screen-level, and deliberately NOT derived from the captured elements. An element only gets
    stored if one of the AI checks applies to it, so a scanner failure on anything else —
    a missing `lang`, a duplicate id, a landmark problem — would have no record anywhere in the
    platform. Its text would still be in the test report, as prose an LLM wrote, which is not
    something the merge may parse and rely on. So the scan reports itself, whole.

    `criteria` may legitimately be empty: axe ships best-practice rules with no WCAG tag. Those
    are kept and counted rather than dropped — the merge reports them separately, because a
    finding with no criterion cannot become an `A11yRuleFailure` and must not silently vanish.
    """
    data = _mapping(raw)
    nodes = data.get("nodes")
    nodes = nodes if isinstance(nodes, list) else []
    rule = _text(data.get("rule") or data.get("id"), 128)
    if len(nodes) > MAX_AXE_NODES:
        raise CaptureError(
            f"screen {route!r} reports rule {rule or '(unnamed)'!r} against {len(nodes)} "
            f"elements, over the limit of {MAX_AXE_NODES}. Nothing was stored for this screen "
            f"— scan the region under test rather than the whole document."
        )
    return {
        "rule": rule,
        "impact": _text(data.get("impact"), 32).strip().lower(),
        "criteria": [_text(c, 16).strip() for c in (data.get("criteria") or [])
                     if _text(c, 16).strip()],
        "help": _text(data.get("help"), 1_000),
        "nodes": [_text(n, MAX_SELECTOR_CHARS) for n in nodes],
    }


def _bounded(data, key: str, route: str, limit: int) -> list:
    """A node-carrying channel, bounded. Same refusal discipline as `axe_violations`."""
    rows = data.get(key)
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise CaptureError(f"screen {route!r} has an `{key}` that is not a list")
    if len(rows) > limit:
        raise CaptureError(
            f"screen {route!r} reports {len(rows)} entries in `{key}`, over the limit of "
            f"{limit}. Nothing was stored for it."
        )
    return rows


def _rule_outcome(raw) -> dict:
    """One rule axe **did not** fail on: a pass, or a rule with nothing to apply to (QA-24).

    Deliberately node-less. "Every element that passed" is thousands of selectors nobody reads,
    and the question these answer — *was this criterion actually checked on this page?* — is
    answered by the rule and its WCAG tags alone. The two channels that DO carry nodes are
    `violations` and `incomplete`, because those are the ones a person has to go and look at.
    """
    data = _mapping(raw)
    return {
        "rule": _text(data.get("rule") or data.get("id"), 128),
        "criteria": [_text(c, 16).strip() for c in (data.get("criteria") or [])
                     if _text(c, 16).strip()],
        "help": _text(data.get("help"), 1_000),
    }


def _rule_list(data, key: str, route: str) -> list:
    """One node-less channel, bounded. Absent is an empty list, and that is honest.

    **Absent means "this capture carries no positive evidence", NOT "nothing passed".** An older
    companion sends only `axe_violations`, so its screens produce no coverage and every criterion
    it touched reads as *not evaluated* — which is exactly what we know about them. Inventing a
    pass from silence here is the one mistake that would make a signed conformance statement
    untrue, and it is the mistake this whole channel exists to prevent.
    """
    rows = data.get(key)
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise CaptureError(f"screen {route!r} has an `{key}` that is not a list")
    if len(rows) > MAX_AXE_RULES:
        raise CaptureError(
            f"screen {route!r} reports {len(rows)} entries in `{key}`, over the limit of "
            f"{MAX_AXE_RULES}. Nothing was stored for it — run the scan with the WCAG tag "
            f"filter rather than every rule axe ships."
        )
    return [_rule_outcome(row) for row in rows]


def _page_measurements(raw, route: str) -> dict:
    """The two page-level readings axe has no rule for, bounded (QA-25).

    **`measured` is the only field this function will invent, and it invents it as `False`.** A
    capture from a companion that predates these passes carries nothing here, and the whole
    contract of `page_rules` is that an absent measurement produces no ruling at all — so the
    absence has to survive parsing intact. Defaulting it the other way would turn every screen
    ever captured before today into a page that reflowed cleanly.

    Everything else is passed through with its types checked rather than interpreted. What the
    numbers mean is `page_rules`, on purpose and in one place: a parser that started deciding
    what an overflow was would be a second copy of the rule, in the layer least able to test it.
    """
    data = _mapping(raw)
    if not data:
        return {}

    reflow = _mapping(data.get("reflow"))
    offenders = reflow.get("offenders")
    offenders = offenders if isinstance(offenders, list) else []
    if len(offenders) > MAX_REFLOW_OFFENDERS:
        raise CaptureError(
            f"screen {route!r} reports {len(offenders)} elements overflowing at 320px, over "
            f"the limit of {MAX_REFLOW_OFFENDERS}. Nothing was stored for it."
        )

    contrast = _mapping(data.get("non_text_contrast"))
    components = contrast.get("components")
    components = components if isinstance(components, list) else []
    if len(components) > MAX_CONTRAST_COMPONENTS:
        raise CaptureError(
            f"screen {route!r} reports contrast readings for {len(components)} components, "
            f"over the limit of {MAX_CONTRAST_COMPONENTS}. Nothing was stored for it."
        )

    def _number(value) -> int:
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0

    return {
        "reflow": {
            "measured": bool(reflow.get("measured")),
            "error": _text(reflow.get("error"), 1_000),
            "requested_width": _number(reflow.get("requested_width")),
            "viewport_width": _number(reflow.get("viewport_width")),
            "content_width": _number(reflow.get("content_width")),
            "overflow_px": _number(reflow.get("overflow_px")),
            "offenders": [
                {
                    "selector": _text(_mapping(o).get("selector"), MAX_SELECTOR_CHARS),
                    "tag": _text(_mapping(o).get("tag"), 64).strip().lower(),
                    "overflow_px": _number(_mapping(o).get("overflow_px")),
                    # Why the criterion allows THIS element to scroll sideways, in the
                    # companion's words — blank when it does not. Kept verbatim: it is the
                    # difference between a defect and a data table, and paraphrasing it here
                    # would put half the exception in one file and half in another.
                    "two_d_reason": _text(_mapping(o).get("two_d_reason"), 128),
                }
                for o in offenders
            ],
        } if reflow else {},
        "non_text_contrast": {
            "measured": bool(contrast.get("measured")),
            "error": _text(contrast.get("error"), 1_000),
            "counted": _number(contrast.get("counted")),
            "capped": bool(contrast.get("capped")),
            "components": [_contrast_component(c) for c in components],
        } if contrast else {},
    }


def _contrast_component(raw) -> dict:
    """One component's colour readings, unblended and unjudged.

    Colours travel as the browser's own strings (`rgb(…)`, `rgba(…)`) rather than as numbers.
    That is deliberate: `page_rules.parse_color` is the single place a colour is turned into
    channels, and a parser that pre-converted here would be a second implementation of the one
    piece of arithmetic a contrast claim rests on.
    """
    data = _mapping(raw)
    borders = data.get("borders")
    stack = data.get("behind_stack")
    return {
        "selector": _text(data.get("selector"), MAX_SELECTOR_CHARS),
        "tag": _text(data.get("tag"), 64).strip().lower(),
        "type": _text(data.get("type"), 64).strip().lower(),
        "role": _text(data.get("role"), 64).strip().lower(),
        "has_text": bool(data.get("has_text")),
        "is_field": bool(data.get("is_field")),
        "background": _text(data.get("background"), 64),
        "background_image": _text(data.get("background_image"), 256),
        "borders": [
            {
                "side": _text(_mapping(b).get("side"), 16),
                "style": _text(_mapping(b).get("style"), 32),
                "width": _text(_mapping(b).get("width"), 32),
                "color": _text(_mapping(b).get("color"), 64),
            }
            for b in (borders if isinstance(borders, list) else [])[:4]
        ],
        "outline": {
            "style": _text(_mapping(data.get("outline")).get("style"), 32),
            "width": _text(_mapping(data.get("outline")).get("width"), 32),
            "color": _text(_mapping(data.get("outline")).get("color"), 64),
        },
        "box_shadow": _text(data.get("box_shadow"), 256),
        "behind_stack": [_text(s, 64) for s in (stack if isinstance(stack, list) else [])[:12]],
        "behind_images": bool(data.get("behind_images")),
    }


def _screen(raw) -> dict:
    data = _mapping(raw)
    route = _text(data.get("route") or data.get("url"), 512)
    if not route:
        raise CaptureError("a captured screen has no route — name the path it was taken on")
    # Why the page never opened at all — an auth wall, a 404, a timeout (QA-17). A DIFFERENT
    # fact from `axe_error` below, and the two must never be conflated: `axe_error` says a
    # screen was seen but not measured, this says the screen was never seen. A baseline audit
    # of an app nobody wrote tests for will hit this on real routes, and a route quietly
    # missing from the results would make the audit read as "we checked everything".
    load_error = _text(data.get("load_error"), 1_000)
    elements = data.get("elements")
    if elements is None and load_error:
        # A route that never opened has no elements by definition. Demanding the key would
        # lose the one fact the entry exists to carry.
        elements = []
    if not isinstance(elements, list):
        raise CaptureError(f"screen {route!r} has no `elements` list")
    if len(elements) > MAX_ELEMENTS_PER_SCREEN:
        raise CaptureError(
            f"screen {route!r} captured {len(elements)} elements, over the limit of "
            f"{MAX_ELEMENTS_PER_SCREEN}. Nothing was stored for it — capture the elements the "
            f"AI checks look at, not every node on the page."
        )
    violations = data.get("axe_violations")
    if violations is None:
        # Absent is "the scan reported nothing here", which is the same shape as a clean page.
        # It is NOT read as "no scan ran" — `axe_error` below is what says that.
        #
        # Until QA-16 that distinction lived in the test report, because a capture only existed
        # for a dedicated accessibility case and the case either executed or it did not. Now
        # every screen the suite visits is captured, including on a stack with no scanner
        # wired, so the fact has to travel with the screen it is about.
        violations = []
    if not isinstance(violations, list):
        raise CaptureError(f"screen {route!r} has an `axe_violations` that is not a list")
    if len(violations) > MAX_AXE_VIOLATIONS:
        raise CaptureError(
            f"screen {route!r} reports {len(violations)} scanner violations, over the limit "
            f"of {MAX_AXE_VIOLATIONS}. Nothing was stored for it."
        )
    return {
        "route": route,
        "url": _text(data.get("url"), 1_000),
        "axe_violations": [_violation(v, route) for v in violations],
        # The other three channels axe returns, kept from QA-24 onward. Until then only
        # `violations` survived, which made "checked and clean" and "nobody looked" identical —
        # the one distinction a conformance statement is made of.
        #
        # `incomplete` is the sharpest of them: axe saying *I looked at this and cannot decide,
        # a human must*. It carries its nodes for the same reason a violation does.
        "axe_passes": _rule_list(data, "axe_passes", route),
        "axe_inapplicable": _rule_list(data, "axe_inapplicable", route),
        "axe_incomplete": [_violation(v, route) for v in _bounded(
            data, "axe_incomplete", route, MAX_AXE_VIOLATIONS)],
        # Which scanner produced all of the above, and WHOSE copy of it. axe-core is imported
        # from the client's project when that project has one, so this differs per tenant and
        # per run; a statement that cannot name it cannot be re-examined against what produced
        # it (QA-24, D-A11Y-96). An application that is not a Node project has no copy to
        # import, and is scanned with the companion's own pinned one — which arrives here as
        # `axe-core 4.13.0 (companion)`. The suffix is carried on this string rather than in a
        # field of its own precisely so that every existing display of the version shows it
        # without being changed, and none of them can forget to.
        "scanner_version": _text(data.get("scanner_version"), 64),
        # Why the rule scanner did not run here, in the capture's own words — blank when it
        # did (QA-16). The same shape and the same reasoning as `screenshot_error` below.
        "axe_error": _text(data.get("axe_error"), 1_000),
        # Why the page could not be opened at all (QA-17); blank when it was.
        "load_error": load_error,
        "screenshot_base64": _text(data.get("screenshot_base64"), MAX_SCREENSHOT_BYTES * 2),
        # Why there is no picture, in the capture's own words. Carried through to the judge, so
        # "could not be seen" is a reported fact rather than an absence someone has to infer.
        "screenshot_error": _text(data.get("screenshot_error"), 1_000),
        # The two things the rule scanner has no rule for, measured in the browser and ruled on
        # by `page_rules` (QA-25): whether the page needs sideways scrolling at 320px, and what
        # colour every control's edge is actually drawn in. `{}` for a capture that carries
        # neither, which is what an older companion sends and what every reader must read as
        # "not measured" rather than as "nothing wrong".
        "page_measurements": _page_measurements(data.get("page_measurements"), route),
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
        # A lone screen object. Recognised by carrying elements — or, since QA-17, by saying
        # why it has none: a route that never opened is still a screen this document is about,
        # and reading it as "not a capture at all" would drop the very fact it exists to carry.
        looks_like_a_screen = (data.get("elements") is not None
                               or str(data.get("load_error") or "").strip())
        screens = [data] if looks_like_a_screen else []
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

    The scanner's own violations are hashed for exactly that reason (QA-12). A screen carried
    forward keeps the scan it was carried forward with, so anything that changes what the
    scanner said — a fix on a node this capture does not record, a scanner upgrade that adds a
    rule — has to change this hash, or the merged report would quote a scan that is no longer
    true of the page.

    The page image is hashed by its bytes, so a re-render that shifted a pixel is a different
    screen. That is deliberate for the same reason, and it means this saving lands on stable
    screens rather than on animated ones.
    """
    digest = sha256()
    digest.update(str(screen.get("route") or "").encode("utf-8"))
    image, reason = screenshot_bytes(screen)
    digest.update(sha256(image).digest() if image else reason.encode("utf-8"))
    # All four scanner channels, not just the failures (QA-24). A scanner upgrade that turns an
    # `inapplicable` into a `pass`, or a `pass` into an `incomplete`, changes what the
    # conformance statement may claim about this screen — so it has to change the screen's
    # identity, exactly as a new violation does. Adding these costs one re-judgment per screen
    # the first time a capture carries them, which is the safe direction this docstring argues
    # for two paragraphs above.
    for part in ("elements", "axe_violations", "axe_passes", "axe_inapplicable",
                 "axe_incomplete"):
        digest.update(
            json.dumps(list(screen.get(part) or []), sort_keys=True,
                       separators=(",", ":"), default=str).encode("utf-8")
        )
    # The page-level measurements, for exactly the reason the scanner channels are hashed
    # (QA-25). A screen carried forward keeps the readings it was carried forward with, so a
    # layout fix that stops a page overflowing at 320px — or a palette change that lifts a
    # button's border past 3:1 — has to change this screen's identity, or the merged report
    # would keep quoting a measurement that is no longer true of the page.
    digest.update(
        json.dumps(dict(screen.get("page_measurements") or {}), sort_keys=True,
                   separators=(",", ":"), default=str).encode("utf-8")
    )
    # Whether the scanner ran at all changes what the merged report may claim about this
    # screen, so it changes the identity too (QA-16) — same reasoning as the violations above.
    # A screen carried forward from a scanned run must not silently inherit "scanned" when
    # this run could not scan it, nor the reverse.
    digest.update(str(screen.get("axe_error") or "").encode("utf-8"))
    # And whether the page opened at all (QA-17), for the same reason one step further back:
    # a route that failed to load this time must not be carried forward from the run where it
    # worked, which would report a screen nobody could reach as freshly checked.
    digest.update(str(screen.get("load_error") or "").encode("utf-8"))
    return digest.hexdigest()


def summarize(screens: list[dict]) -> str:
    """One line for the run console — the platform's single summarizer for a capture."""
    if not screens:
        return "no accessibility capture"
    opened = [s for s in screens if not str(s.get("load_error") or "").strip()]
    unreachable = len(screens) - len(opened)
    elements = sum(len(s.get("elements") or []) for s in opened)
    unseen = sum(1 for s in opened if not (s.get("screenshot_base64") or "").strip())
    line = f"{elements} element(s) captured on {len(opened)} screen(s)"
    if unseen:
        line += f", {unseen} with no page image"
    if unreachable:
        line += f", {unreachable} screen(s) could not be opened"
    return line
