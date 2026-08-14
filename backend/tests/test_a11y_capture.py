"""QA-11b — capture AI candidate bundles in the companion, and ingest them.

The AI accessibility pass was fully built and had never seen a real page: `select` and
`dispatch_judgments` were called from tests and from nowhere else. This is the chain that
closes that — the suite writes down what was on each screen, the companion collects it before
the worktree is destroyed, the platform selects what is worth judging, cuts a picture of each
selected element, and the judge can finally look at them.

Four things these tests are here to hold in place:

  * **Selection happens before cropping.** That ordering is the whole cost argument, and it is
    invisible in the output — a test that only counts rows would pass either way. So the object
    store is watched: an element no checker applies to must produce no crop and no write.
  * **A missing picture is stored, never dropped.** An element the platform decided not to look
    at, silently, is the failure mode a conformance report cannot survive.
  * **No capture is not a clean page.** Same rule as the JUnit path: no file ⇒ nothing imported.
  * **The three tool surfaces agree.** A tool the platform exposes but never grants is one the
    agent cannot call — proven the hard way in QA-02a.
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import psycopg
import pytest
from django.conf import settings
from django.db import connection
from PIL import Image as PILImage
from rest_framework.test import APIClient

from apps.a11y.capture import (
    CAPTURE_VERSION,
    MAX_ELEMENTS_PER_SCREEN,
    MAX_SCREENS,
    MAX_SCREENSHOT_BYTES,
    CaptureError,
    parse_capture,
    screenshot_bytes,
    summarize,
)
from apps.a11y.ingest import ingest_capture, ingest_screen, requests_for
from apps.a11y.models import A11yCandidateBundle
from apps.projects.ci_tokens import issue_ci_token
from apps.projects.models import Project
from apps.tenancy.models import Tenant
from storage.object_store import InMemoryObjectStore

_AGENTS = Path(__file__).resolve().parents[2] / "agents"
_RUNNER = Path(__file__).resolve().parents[2] / "runner"


# ── fixtures: a page with one image, one fake button, and one plain div ─────────────

def _png(width: int = 400, height: int = 300, colour=(200, 40, 40)) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (width, height), colour).save(buf, format="PNG")
    return buf.getvalue()


_STYLES = {
    "color": "rgb(0, 0, 0)", "background-color": "transparent",
    "text-decoration-line": "none", "font-size": "16px", "font-weight": "400",
    "border-style": "none",
}


def _element(**over) -> dict:
    base = {
        "selector": "img.hero", "tag": "img", "role": "", "attrs": {"alt": "IMG_1234"},
        "text": "", "accessible_name": "IMG_1234", "interactive": False, "rendered": True,
        "styles": dict(_STYLES), "parent_styles": dict(_STYLES),
        "html": '<img class="hero" alt="IMG_1234">', "context": "Our new range",
        "box": {"x": 10, "y": 20, "width": 120, "height": 80},
    }
    base.update(over)
    return base


def _screen(**over) -> dict:
    base = {
        "route": "/home", "url": "http://localhost:5173/home",
        "screenshot_base64": base64.b64encode(_png()).decode("ascii"),
        "elements": [
            _element(),
            # A div with a click handler — `semantics` applies (it behaves like a control).
            _element(selector="div.fake-btn", tag="div", attrs={}, text="Buy now",
                     accessible_name="Buy now", interactive=True, html="<div>Buy now</div>",
                     box={"x": 200, "y": 100, "width": 80, "height": 30}),
            # A plain paragraph — no checker applies. This is the one that must cost nothing.
            _element(selector="p.blurb", tag="p", attrs={}, text="Some prose",
                     accessible_name="", interactive=False, html="<p>Some prose</p>",
                     box={"x": 0, "y": 200, "width": 300, "height": 20}),
        ],
    }
    base.update(over)
    return base


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="App")
    return {"t": str(tenant.id), "p": str(project.id), "tenant": tenant, "project": project}


def _make_run(world, workflow_id: str, inputs=None):
    """A real `Run` for this project — used wherever a test needs two runs to be genuinely
    different rather than pretended to be."""
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from apps.workitems.models import WorkItem

    wi = WorkItem.objects.filter(project=world["project"]).first() or WorkItem.objects.create(
        tenant=world["tenant"], project=world["project"], type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.filter(tenant=world["tenant"], key="09c_a11y_judge").first() \
        or AgentSpec.objects.create(tenant=world["tenant"], key="09c_a11y_judge", body_ref="x")
    return Run.objects.create(
        tenant=world["tenant"], work_item=wi, agent_spec=spec,
        temporal_workflow_id=workflow_id, inputs=inputs or {},
    )


class _WatchingStore(InMemoryObjectStore):
    """An object store that remembers every key written, so "was a crop cut?" is checkable."""

    def __init__(self):
        super().__init__()
        self.writes: list[str] = []

    def put(self, key, body, content_type="text/markdown"):
        self.writes.append(key)
        return super().put(key, body, content_type=content_type)


# ── the parser: what a capture document means ───────────────────────────────────────

def test_parse_reads_a_whole_document():
    screens = parse_capture(json.dumps({"version": 1, "screens": [_screen()]}))
    assert [s["route"] for s in screens] == ["/home"]
    assert len(screens[0]["elements"]) == 3


def test_parse_reads_a_single_screen_object():
    """The companion posts one screen per call; a CI job posts the file. Both are captures."""
    screens = parse_capture(json.dumps(_screen()))
    assert len(screens) == 1 and screens[0]["route"] == "/home"


def test_parse_reads_a_bare_list_of_screens():
    assert len(parse_capture(json.dumps([_screen(), _screen(route="/two")]))) == 2


@pytest.mark.parametrize("body", ["", "   ", "not json at all", "[[[", json.dumps("a string")])
def test_an_unreadable_body_is_no_screens_not_an_error(body):
    """`[]` is the honest answer for "no capture" — the caller stores nothing, and a scan that
    captured nothing can never be read as a page with nothing wrong on it."""
    assert parse_capture(body) == []


def test_a_document_with_no_screens_key_and_no_elements_is_empty():
    assert parse_capture(json.dumps({"version": 1})) == []


def test_a_newer_format_version_is_refused_by_name():
    with pytest.raises(CaptureError) as exc:
        parse_capture(json.dumps({"version": CAPTURE_VERSION + 1, "screens": [_screen()]}))
    assert "version" in str(exc.value) and "update the platform" in str(exc.value)


def test_a_non_numeric_version_is_refused():
    with pytest.raises(CaptureError):
        parse_capture(json.dumps({"version": "two", "screens": []}))


def test_too_many_screens_is_refused_rather_than_clipped():
    body = json.dumps({"screens": [_screen(route=f"/r{i}") for i in range(MAX_SCREENS + 1)]})
    with pytest.raises(CaptureError) as exc:
        parse_capture(body)
    assert "Nothing was stored" in str(exc.value)


def test_too_many_elements_on_one_screen_is_refused_rather_than_clipped():
    """Clipping would leave a conformance report claiming the dropped elements were fine."""
    screen = _screen(elements=[_element() for _ in range(MAX_ELEMENTS_PER_SCREEN + 1)])
    with pytest.raises(CaptureError) as exc:
        parse_capture(json.dumps(screen))
    assert "/home" in str(exc.value) and "Nothing was stored" in str(exc.value)


def test_a_screen_with_no_route_is_refused():
    with pytest.raises(CaptureError):
        parse_capture(json.dumps({"screens": [{"elements": []}]}))


def test_a_screen_with_no_elements_list_is_refused():
    with pytest.raises(CaptureError):
        parse_capture(json.dumps({"screens": [{"route": "/x"}]}))


def test_screens_must_be_a_list():
    with pytest.raises(CaptureError):
        parse_capture(json.dumps({"screens": {"route": "/x"}}))


@pytest.mark.parametrize("box", [
    {"width": 0, "height": 10, "x": 0, "y": 0},      # zero area
    {"width": -5, "height": 10, "x": 0, "y": 0},     # negative
    {"x": 1},                                         # incomplete
    {"x": "left", "y": 0, "width": 10, "height": 10},  # not a number
    "not a box",
])
def test_a_degenerate_rectangle_is_dropped_rather_than_repaired(box):
    """Cropping a zero-area box yields a blank image, and a blank image shown as evidence is
    worse than none — it looks like something was seen."""
    screens = parse_capture(json.dumps(_screen(elements=[_element(box=box)])))
    assert screens[0]["elements"][0]["box"] == {}


def test_rendered_defaults_to_true_when_the_capture_forgot_it():
    """The same default `CapturedElement.from_dict` takes: a forgotten field must not make
    every element invisible to every checker."""
    raw = _element()
    raw.pop("rendered")
    assert parse_capture(json.dumps(_screen(elements=[raw])))[0]["elements"][0]["rendered"]


def test_oversized_markup_and_context_are_bounded():
    screen = _screen(elements=[_element(html="x" * 50_000, context="y" * 50_000)])
    element = parse_capture(json.dumps(screen))[0]["elements"][0]
    assert len(element["html"]) == 8_000 and len(element["context"]) == 4_000


def test_attribute_names_are_lowercased_like_the_rules_read_them():
    element = parse_capture(json.dumps(_screen(
        elements=[_element(attrs={"ARIA-Label": "Go"})])))[0]["elements"][0]
    assert element["attrs"] == {"aria-label": "Go"}


# ── the page screenshot: a picture, or a reason there is none ───────────────────────

def test_screenshot_bytes_decodes_a_real_png():
    raw, reason = screenshot_bytes(_screen())
    assert raw.startswith(b"\x89PNG") and reason == ""


def test_a_capture_reported_error_wins_over_everything():
    raw, reason = screenshot_bytes({"screenshot_error": "the page never finished loading"})
    assert raw == b"" and reason == "the page never finished loading"


@pytest.mark.parametrize("value,fragment", [
    ("", "no page screenshot"),
    ("!!!not base64!!!", "could not be decoded"),
    (base64.b64encode(b"").decode(), "no page screenshot"),
])
def test_an_unusable_screenshot_is_a_reason_not_an_exception(value, fragment):
    raw, reason = screenshot_bytes({"screenshot_base64": value})
    assert raw == b"" and fragment in reason


def test_an_oversized_screenshot_is_refused_with_advice():
    huge = base64.b64encode(b"\x00" * (MAX_SCREENSHOT_BYTES + 1)).decode("ascii")
    raw, reason = screenshot_bytes({"screenshot_base64": huge})
    assert raw == b"" and "viewport width" in reason


def test_the_screenshot_limit_fits_inside_what_a_request_body_may_hold():
    """The number is not a taste judgement. A screen is one request body, and Django refuses a
    body over `DATA_UPLOAD_MAX_MEMORY_SIZE` (2.5 MiB by default) *before* the parser runs — so a
    limit above that would turn this module's clear sentence into an opaque 500."""
    from django.conf import settings

    encoded = MAX_SCREENSHOT_BYTES * 4 / 3
    limit = getattr(settings, "DATA_UPLOAD_MAX_MEMORY_SIZE", 2_621_440)
    assert encoded < limit * 0.85       # room for the elements and the JSON envelope


def test_summarize_says_what_was_taken():
    assert summarize([]) == "no accessibility capture"
    assert summarize([_screen()]) == "3 element(s) captured on 1 screen(s)"
    assert "no page image" in summarize([_screen(screenshot_base64="")])


# ── ingest: select first, then crop ─────────────────────────────────────────────────

def test_only_selected_elements_are_stored(world):
    out = ingest_screen(tenant_id=world["t"], project_id=world["p"],
                        screen=parse_capture(json.dumps(_screen()))[0],
                        object_store=InMemoryObjectStore())
    assert out["captured"] == 3 and out["selected"] == 2 and out["skipped"] == 1
    stored = {b.selector: b.checkers for b in A11yCandidateBundle.objects.all()}
    assert stored == {"img.hero": ["alt"], "div.fake-btn": ["semantics"]}


def test_the_unselected_element_costs_no_crop_and_no_write(world):
    """This is the ordering decision, and it is invisible in the row count: a crop cut for an
    element no checker applies to is work spent on a question nobody will ever ask."""
    store = _WatchingStore()
    ingest_screen(tenant_id=world["t"], project_id=world["p"],
                  screen=parse_capture(json.dumps(_screen()))[0], object_store=store)
    # One page image + exactly one crop per SELECTED element. Never three.
    assert len(store.writes) == 3
    assert sum(1 for k in store.writes if "/elements/" in k) == 2
    # ...and the plain <p>'s own region was never cut, so its pixels are nowhere in the store.
    page = store.get([k for k in store.writes if "/pages/" in k][0])
    with PILImage.open(io.BytesIO(page)) as im:
        blurb = im.crop((0, 200 - 12, 300 + 12, 220 + 12))
    buf = io.BytesIO()
    blurb.save(buf, format="PNG")
    assert not any(store.get(k) == buf.getvalue()
                   for k in store.writes if "/elements/" in k)


def test_the_crop_is_the_elements_own_region_of_the_page_image(world):
    store = InMemoryObjectStore()
    ingest_screen(tenant_id=world["t"], project_id=world["p"],
                  screen=parse_capture(json.dumps(_screen()))[0], object_store=store)
    bundle = A11yCandidateBundle.objects.get(selector="img.hero")
    with PILImage.open(io.BytesIO(store.get(bundle.screenshot_ref))) as im:
        # box (10,20) 120x80, padded by 12 and CLIPPED to the page: the left padding is only
        # 10px because the element sits 10px from the edge, so 142 wide rather than 144.
        assert im.size == (10 + 120 + 12, 12 + 80 + 12)


def test_a_crop_is_padded_so_the_surroundings_are_visible(world):
    """1.4.1 asks about an element *against its surroundings*; a status dot cropped to its own
    bounding box is a coloured circle with nothing to compare it to."""
    store = InMemoryObjectStore()
    ingest_screen(tenant_id=world["t"], project_id=world["p"],
                  screen=parse_capture(json.dumps(_screen()))[0], object_store=store)
    bundle = A11yCandidateBundle.objects.get(selector="div.fake-btn")
    with PILImage.open(io.BytesIO(store.get(bundle.screenshot_ref))) as im:
        assert im.width > 80 and im.height > 30


def test_an_element_with_no_rectangle_is_stored_uncapturable_not_dropped(world):
    screen = parse_capture(json.dumps(_screen(elements=[_element(box={"width": 0})])))[0]
    out = ingest_screen(tenant_id=world["t"], project_id=world["p"], screen=screen,
                        object_store=InMemoryObjectStore())
    bundle = A11yCandidateBundle.objects.get()
    assert out["uncapturable"] == 1 and bundle.screenshot_ref == ""
    assert "no on-screen rectangle" in bundle.uncapturable_reason


def test_a_screen_with_no_page_image_still_stores_its_elements(world):
    screen = parse_capture(json.dumps(
        _screen(screenshot_base64="", screenshot_error="the browser crashed")))[0]
    out = ingest_screen(tenant_id=world["t"], project_id=world["p"], screen=screen,
                        object_store=InMemoryObjectStore())
    assert out["selected"] == 2 and out["uncapturable"] == 2 and out["page_image"] is False
    assert all(b.uncapturable_reason == "the browser crashed"
               for b in A11yCandidateBundle.objects.all())


def test_an_element_whose_box_falls_off_the_page_says_so(world):
    screen = parse_capture(json.dumps(_screen(
        elements=[_element(box={"x": 9000, "y": 9000, "width": 10, "height": 10})])))[0]
    ingest_screen(tenant_id=world["t"], project_id=world["p"], screen=screen,
                  object_store=InMemoryObjectStore())
    assert "outside the page screenshot" in A11yCandidateBundle.objects.get().uncapturable_reason


def test_an_undecodable_page_image_costs_the_pictures_not_the_screen(world):
    screen = parse_capture(json.dumps(_screen(
        screenshot_base64=base64.b64encode(b"this is not a png").decode())))[0]
    out = ingest_screen(tenant_id=world["t"], project_id=world["p"], screen=screen,
                        object_store=InMemoryObjectStore())
    assert out["selected"] == 2 and out["uncapturable"] == 2


def test_an_object_store_that_refuses_the_page_image_never_loses_the_elements(world):
    class _Broken(InMemoryObjectStore):
        def put(self, key, body, content_type="text/markdown"):
            raise RuntimeError("the bucket is unreachable")

    out = ingest_screen(tenant_id=world["t"], project_id=world["p"],
                        screen=parse_capture(json.dumps(_screen()))[0], object_store=_Broken())
    assert out["selected"] == 2 and out["page_image"] is False
    assert "could not be stored" in A11yCandidateBundle.objects.first().uncapturable_reason


def test_a_large_crop_is_downscaled_before_it_is_stored(world):
    """What the judge is sent has to survive the agent transport — the same ceiling the vision
    pipe hit and the same fix."""
    from apps.a11y.ingest import CROP_MAX_PX

    store = InMemoryObjectStore()
    screen = parse_capture(json.dumps(_screen(
        screenshot_base64=base64.b64encode(_png(3000, 2000)).decode("ascii"),
        elements=[_element(box={"x": 0, "y": 0, "width": 2800, "height": 1800})])))[0]
    ingest_screen(tenant_id=world["t"], project_id=world["p"], screen=screen,
                  object_store=store)
    ref = A11yCandidateBundle.objects.get().screenshot_ref
    with PILImage.open(io.BytesIO(store.get(ref))) as im:
        assert max(im.size) == CROP_MAX_PX


def test_a_store_that_refuses_one_crop_still_stores_the_element(world):
    class _RefusesCrops(InMemoryObjectStore):
        def put(self, key, body, content_type="text/markdown"):
            if "/elements/" in key:
                raise RuntimeError("the bucket is full")
            return super().put(key, body, content_type=content_type)

    out = ingest_screen(tenant_id=world["t"], project_id=world["p"],
                        screen=parse_capture(json.dumps(_screen()))[0],
                        object_store=_RefusesCrops())
    assert out["selected"] == 2 and out["uncapturable"] == 2 and out["page_image"] is True
    assert "could not be stored" in A11yCandidateBundle.objects.first().uncapturable_reason


def test_axe_findings_travel_with_the_element(world):
    axe = {"rule": "image-alt", "impact": "critical", "criteria": ["1.1.1"]}
    screen = parse_capture(json.dumps(_screen(elements=[_element(axe=axe)])))[0]
    ingest_screen(tenant_id=world["t"], project_id=world["p"], screen=screen,
                  object_store=InMemoryObjectStore())
    assert A11yCandidateBundle.objects.get().axe == axe


def test_reposting_the_same_screen_updates_rather_than_doubling(world):
    for _ in range(2):
        ingest_screen(tenant_id=world["t"], project_id=world["p"],
                      screen=parse_capture(json.dumps(_screen()))[0],
                      object_store=InMemoryObjectStore())
    assert A11yCandidateBundle.objects.count() == 2      # the two selected, once each


def test_ingest_capture_reports_nothing_imported_for_an_unreadable_body(world):
    out = ingest_capture(tenant_id=world["t"], project_id=world["p"], text="garbage")
    assert out["imported"] is False and A11yCandidateBundle.objects.count() == 0


def test_ingest_capture_stores_every_screen_in_the_document(world):
    body = json.dumps({"screens": [_screen(), _screen(route="/two")]})
    out = ingest_capture(tenant_id=world["t"], project_id=world["p"], text=body,
                         object_store=InMemoryObjectStore())
    assert out["imported"] and out["selected"] == 4 and out["skipped"] == 2
    assert {b.route for b in A11yCandidateBundle.objects.all()} == {"/home", "/two"}


# ── what dispatch reads back ────────────────────────────────────────────────────────

def test_requests_carry_the_platforms_crop_pointer_not_the_captures_claim(world):
    """The crop is ours; the capture has no way to know its key, and a stale one would hand the
    judge a picture of something else."""
    store = InMemoryObjectStore()
    screen = parse_capture(json.dumps(_screen(
        elements=[_element(screenshot_ref="whatever-the-capture-said")])))[0]
    ingest_screen(tenant_id=world["t"], project_id=world["p"], screen=screen,
                  object_store=store)
    request = requests_for(world["t"], world["p"])[0]
    assert request.checker == "alt"
    assert request.candidate.screenshot_ref.startswith("a11y/") and store.get(
        request.candidate.screenshot_ref)


def test_an_unchanged_element_keeps_its_cache_key_on_a_later_run(world):
    """The defect this test exists for, and it was live and invisible.

    `dispatch.content_hash` fingerprints everything the judge looks at — including the pointer
    to the element's picture — so a cached verdict can never be stale. Naming a crop after the
    run that took it gave the same untouched element a new pointer every run, so the
    fingerprint changed every run and **the cache could never hit**: every run would re-judge
    every element of every screen. Nothing dispatches yet, so nothing failed; it would have
    surfaced as a first real audit that was inexplicably enormous.
    """
    store = InMemoryObjectStore()
    parsed = parse_capture(json.dumps(_screen()))[0]
    keys = []
    for run in (_make_run(world, "wf-1"), _make_run(world, "wf-2")):
        ingest_screen(tenant_id=world["t"], project_id=world["p"], screen=parsed,
                      run_id=str(run.id), object_store=store)
        request = next(r for r in requests_for(world["t"], world["p"], str(run.id))
                       if r.candidate.selector == "img.hero")
        keys.append((request.candidate.screenshot_ref, request.content_hash))
    assert keys[0] == keys[1]


def test_a_changed_element_gets_a_new_cache_key(world):
    """The other direction, and it is the half that makes caching safe: different pixels are a
    different picture, and the visual question may have a different answer."""
    store = InMemoryObjectStore()
    hashes = []
    for colour in ((200, 40, 40), (40, 200, 40)):
        screen = parse_capture(json.dumps(_screen(
            screenshot_base64=base64.b64encode(_png(colour=colour)).decode("ascii"))))[0]
        ingest_screen(tenant_id=world["t"], project_id=world["p"], screen=screen,
                      object_store=store)
        hashes.append(next(r.content_hash for r in requests_for(world["t"], world["p"])
                           if r.candidate.selector == "img.hero"))
    assert hashes[0] != hashes[1]


def test_the_cache_key_reads_exactly_the_four_things_the_judge_looks_at(world):
    """Pinned so a field cannot be added to the fingerprint without someone deciding to.

    Every input added here is a new way for two identical elements to look different, and the
    cost of getting that wrong is silent: the cache stops hitting and nobody is told."""
    import inspect

    from apps.a11y import dispatch

    source = inspect.getsource(dispatch.content_hash)
    assert "parts = (checker, candidate.html, candidate.screenshot_ref, candidate.context)" \
        in source


def test_requests_are_in_a_stable_order(world):
    ingest_screen(tenant_id=world["t"], project_id=world["p"],
                  screen=parse_capture(json.dumps(_screen()))[0],
                  object_store=InMemoryObjectStore())
    first = [(r.checker, r.candidate.selector) for r in requests_for(world["t"], world["p"])]
    second = [(r.checker, r.candidate.selector) for r in requests_for(world["t"], world["p"])]
    assert first == second == [("alt", "img.hero"), ("semantics", "div.fake-btn")]


def test_the_order_is_the_pages_order_not_the_rows_order(world):
    """Caught by a test that passed alone and failed in the suite: the primary key is a UUID,
    so `order_by("id")` looks like insertion order and is not. The element's position on the
    page is stored precisely so the batch comes out the same way twice."""
    elements = [
        _element(selector=f"img.n{i}", attrs={"alt": f"IMG_{i}"}, html=f"<img alt=IMG_{i}>")
        for i in range(6)
    ]
    ingest_screen(tenant_id=world["t"], project_id=world["p"],
                  screen=parse_capture(json.dumps(_screen(elements=elements)))[0],
                  object_store=InMemoryObjectStore())
    order = [r.candidate.selector for r in requests_for(world["t"], world["p"])]
    assert order == [f"img.n{i}" for i in range(6)]


def test_a_palette_image_is_converted_before_it_is_stored(world):
    """A PNG does not have to be RGB. An unconverted palette crop saves as something the vision
    transport may not read, and the failure would look like a missing screenshot."""
    buf = io.BytesIO()
    PILImage.new("P", (400, 300)).save(buf, format="PNG")
    store = InMemoryObjectStore()
    screen = parse_capture(json.dumps(_screen(
        screenshot_base64=base64.b64encode(buf.getvalue()).decode("ascii"))))[0]
    ingest_screen(tenant_id=world["t"], project_id=world["p"], screen=screen,
                  object_store=store)
    ref = A11yCandidateBundle.objects.get(selector="img.hero").screenshot_ref
    with PILImage.open(io.BytesIO(store.get(ref))) as im:
        assert im.mode in ("RGB", "RGBA", "L")


def test_one_element_can_produce_a_request_per_checker(world):
    """A div-as-button that is also only distinguished by colour is two different questions."""
    element = _element(
        selector="span.status", tag="span", attrs={}, text="Overdue", accessible_name="Overdue",
        interactive=True, html="<span>Overdue</span>",
        styles={**_STYLES, "color": "rgb(200, 0, 0)"},
        parent_styles={**_STYLES, "color": "rgb(0, 0, 0)"},
    )
    ingest_screen(tenant_id=world["t"], project_id=world["p"],
                  screen=parse_capture(json.dumps(_screen(elements=[element])))[0],
                  object_store=InMemoryObjectStore())
    assert [r.checker for r in requests_for(world["t"], world["p"])] == ["semantics", "color"]


def test_another_projects_bundles_are_not_returned(world):
    other = Project.objects.create(tenant=world["tenant"], name="Other")
    ingest_screen(tenant_id=world["t"], project_id=world["p"],
                  screen=parse_capture(json.dumps(_screen()))[0],
                  object_store=InMemoryObjectStore())
    assert requests_for(world["t"], str(other.id)) == []


# ── the judge's eyes ────────────────────────────────────────────────────────────────

def _run_with_batch(world, elements):
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from apps.workitems.models import WorkItem

    wi = WorkItem.objects.create(tenant=world["tenant"], project=world["project"],
                                 type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=world["tenant"], key="09c_a11y_judge", body_ref="x")
    return Run.objects.create(
        tenant=world["tenant"], work_item=wi, agent_spec=spec, temporal_workflow_id="wf-a11y",
        inputs={"a11y_batches": [{"route": "/home", "elements": elements}]},
    )


def test_screenshot_pointers_label_each_image_with_its_element(world):
    from apps.a11y.judge import screenshot_pointers

    run = _run_with_batch(world, [
        {"id": "1-aaaaaaaa", "content_hash": "a" * 64, "checker": "alt",
         "criteria": ["1.1.1"], "screenshot_ref": "a11y/x/element-0000.png"},
        {"id": "2-bbbbbbbb", "content_hash": "b" * 64, "checker": "color",
         "criteria": ["1.4.1"], "screenshot_ref": ""},
    ])
    pointers, unseen = screenshot_pointers(world["t"], str(run.id))
    assert pointers == [{"name": "1-aaaaaaaa", "page": 0, "s3_key": "a11y/x/element-0000.png"}]
    assert unseen[0]["id"] == "2-bbbbbbbb" and "no image" in unseen[0]["reason"]


def test_get_a11y_screenshots_returns_the_picture_and_names_what_it_could_not_show(world):
    from mcp_platform_state import tools

    store = InMemoryObjectStore()
    store.put("a11y/x/element-0000.png", _png(), content_type="image/png")
    run = _run_with_batch(world, [
        {"id": "1-aaaaaaaa", "content_hash": "a" * 64, "checker": "alt",
         "criteria": ["1.1.1"], "screenshot_ref": "a11y/x/element-0000.png"},
        {"id": "2-bbbbbbbb", "content_hash": "b" * 64, "checker": "color",
         "criteria": ["1.4.1"], "screenshot_ref": ""},
    ])
    out = tools.get_a11y_screenshots(world["t"], str(run.id), object_store=store)
    assert out["returned"] == 1 and out["images"][0]["name"] == "1-aaaaaaaa"
    assert base64.b64decode(out["images"][0]["data_base64"]).startswith(b"\x89PNG")
    assert [u["id"] for u in out["unseen"]] == ["2-bbbbbbbb"]


def test_ingest_a11y_candidates_tool_stores_a_screen(world):
    from mcp_platform_state import tools

    out = tools.ingest_a11y_candidates(
        world["t"], world["p"], parse_capture(json.dumps(_screen()))[0])
    assert out["selected"] == 2 and A11yCandidateBundle.objects.count() == 2


# ── the endpoint ────────────────────────────────────────────────────────────────────

@pytest.fixture
def ci(world):
    _, token = issue_ci_token(tenant_id=world["t"], project_id=world["p"], label="CI")
    return {**world, "token": token, "client": APIClient(),
            "url": f"/api/projects/{world['p']}/a11y-candidates/"}


def _post(ci, body, token=None):
    return ci["client"].post(
        ci["url"], data=body, content_type="application/json",
        HTTP_AUTHORIZATION=f"CI {token or ci['token']}", HTTP_X_TENANT_ID=ci["t"],
    )


def test_the_endpoint_refuses_a_bad_token(ci):
    assert _post(ci, json.dumps(_screen()), token="nope").status_code == 401


def test_the_endpoint_refuses_an_empty_body(ci):
    assert _post(ci, "  ").status_code == 400


def test_the_endpoint_reports_an_unreadable_capture_as_unprocessable(ci):
    """A silent 200 would tell a CI pipeline its accessibility capture landed when it did not."""
    assert _post(ci, "not a capture").status_code == 422


def test_the_endpoint_names_the_bound_a_capture_broke(ci):
    body = json.dumps({"version": CAPTURE_VERSION + 99, "screens": [_screen()]})
    response = _post(ci, body)
    assert response.status_code == 422 and "version" in response.json()["detail"]


def test_the_endpoint_stores_a_posted_screen(ci):
    response = _post(ci, json.dumps(_screen()))
    assert response.status_code == 200 and response.json()["selected"] == 2
    assert A11yCandidateBundle.objects.count() == 2


def test_a_ci_capture_is_filed_against_no_run(ci):
    """A CI token must not be able to name one of our agent runs to file candidates against."""
    _post(ci, json.dumps(_screen()))
    assert all(b.run_id is None and b.run_key == ""
               for b in A11yCandidateBundle.objects.all())


# ── the companion side ──────────────────────────────────────────────────────────────

def test_the_companion_finds_the_conventional_capture_path(tmp_path):
    from runner.companion.a11ycapture import find_captures

    (tmp_path / "test-results").mkdir()
    (tmp_path / "test-results" / "a11y-candidates.json").write_text("{}", encoding="utf-8")
    assert [p.name for p in find_captures(tmp_path)] == ["a11y-candidates.json"]


def test_no_capture_file_means_no_candidates(tmp_path, db):
    """Same rule as the JUnit path: no report ⇒ no results ⇒ no import. A scan that captured
    nothing must never read as a page with nothing wrong on it."""
    from runner.companion.a11ycapture import collect_a11y_candidates

    assert collect_a11y_candidates(tmp_path) == []


def test_the_companion_collects_what_the_suite_wrote(tmp_path, db):
    from runner.companion.a11ycapture import collect_a11y_candidates
    from runner.companion.a11ycapture import summarize as _sum

    (tmp_path / "test-results").mkdir()
    (tmp_path / "test-results" / "a11y-candidates.json").write_text(
        json.dumps({"version": 1, "screens": [_screen()]}), encoding="utf-8")
    screens = collect_a11y_candidates(tmp_path)
    assert len(screens) == 1 and _sum(screens) == "3 element(s) captured on 1 screen(s)"


def test_a_capture_that_breaks_a_bound_is_skipped_with_its_reason(tmp_path, db, capsys):
    """The file is saying something wrong. The honest outcome is fewer screens — never a build
    that dies after the suite already ran."""
    from runner.companion.a11ycapture import collect_a11y_candidates

    (tmp_path / "test-results").mkdir()
    (tmp_path / "test-results" / "a11y-candidates.json").write_text(
        json.dumps({"version": 99, "screens": [_screen()]}), encoding="utf-8")
    assert collect_a11y_candidates(tmp_path) == []
    assert "was not stored" in capsys.readouterr().out


class _Client:
    def __init__(self, fail_on=()):
        self.calls: list[dict] = []
        self._fail_on = fail_on

    def call(self, tool, **kwargs):
        if kwargs.get("screen", {}).get("route") in self._fail_on:
            raise RuntimeError("the platform said no")
        self.calls.append({"tool": tool, **kwargs})
        return {"selected": 1}


def test_screens_are_posted_one_per_call():
    """A screen carries a full-page PNG; ten in one body is past what the request layer takes."""
    from runner.companion.a11ycapture import post_a11y_candidates

    client = _Client()
    out = post_a11y_candidates([_screen(), _screen(route="/two")], client=client,
                               project_id="p", run_id="r")
    assert out["posted"] == 2 and len(client.calls) == 2
    assert {c["tool"] for c in client.calls} == {"ingest_a11y_candidates"}
    assert [c["screen"]["route"] for c in client.calls] == ["/home", "/two"]


def test_one_screen_failing_to_post_never_costs_the_others_or_the_build():
    from runner.companion.a11ycapture import post_a11y_candidates

    client = _Client(fail_on=("/home",))
    out = post_a11y_candidates([_screen(), _screen(route="/two")], client=client,
                               project_id="p", run_id="r")
    assert out["posted"] == 1 and len(out["failed"]) == 1 and "/home" in out["failed"][0]


# ── the tool surfaces agree ─────────────────────────────────────────────────────────

def test_the_judges_eyes_are_granted_on_every_surface():
    """A tool the platform exposes but never GRANTS is one the agent cannot call — the failure
    QA-02a hit when three surfaces had to be edited together."""
    from mcp_platform_state import tools
    from runner.companion.runner import BUILD_STATE_TOOLS

    from api.runner_views import _BUILD_STATE_TOOLS

    assert hasattr(tools, "get_a11y_screenshots")
    assert "get_a11y_screenshots" in _BUILD_STATE_TOOLS
    assert "get_a11y_screenshots" in BUILD_STATE_TOOLS
    for path in ("runner/companion/state_mcp.py", "mcp_platform_state/server.py"):
        body = (Path(__file__).resolve().parents[2] / path).read_text(encoding="utf-8")
        assert "def get_a11y_screenshots(" in body


def test_the_ingest_tool_is_reachable_by_the_companion_but_not_by_the_engine():
    """The capture is machine truth from the suite's own run. An agent able to write candidate
    bundles could describe a page instead of one having been captured."""
    from runner.companion.runner import BUILD_STATE_TOOLS

    from api.runner_views import _BUILD_STATE_TOOLS

    assert "ingest_a11y_candidates" in _BUILD_STATE_TOOLS
    assert "ingest_a11y_candidates" not in BUILD_STATE_TOOLS


# ── the agent bodies teach what the platform expects ────────────────────────────────

def test_09b_tells_the_suite_where_to_write_the_capture():
    from runner.companion.a11ycapture import CAPTURE_GLOBS

    body = (_AGENTS / "09b_test_automation/agent.md").read_text(encoding="utf-8")
    assert CAPTURE_GLOBS[0] in body            # the first path the companion checks
    assert "screenshot_base64" in body and "screenshot_error" in body


def test_09b_names_every_style_key_the_rules_read():
    """A style key missing from the capture reads as "no" and silently stops a whole rule —
    so the body has to name all six, not "the relevant computed styles"."""
    from apps.a11y.checkers.rules import STYLE_KEYS

    body = (_AGENTS / "09b_test_automation/agent.md").read_text(encoding="utf-8")
    for key in STYLE_KEYS:
        assert key in body, key


def test_09b_forbids_approximating_the_accessible_name():
    """2.5.3 exists to catch the case where the computed name and the visible text disagree; an
    approximation makes them agree by construction and the check stops working."""
    body = (_AGENTS / "09b_test_automation/agent.md").read_text(encoding="utf-8")
    assert "accessible_name" in body and "Never approximate it" in body
    assert "page.accessibility.snapshot" in body


def test_09b_takes_one_screenshot_per_screen_not_per_element():
    body = (_AGENTS / "09b_test_automation/agent.md").read_text(encoding="utf-8")
    assert "One screenshot per screen, not one per element" in body


def test_09b_states_the_platforms_own_capture_bounds():
    body = (_AGENTS / "09b_test_automation/agent.md").read_text(encoding="utf-8")
    assert str(MAX_ELEMENTS_PER_SCREEN) in body and str(MAX_SCREENS) in body


def test_09c_is_told_to_look_before_judging_something_visual():
    body = (_AGENTS / "09c_a11y_judge/agent.md").read_text(encoding="utf-8")
    assert "get_a11y_screenshots" in body
    assert "your eyes" in body
    # The judge must still say so when there is nothing to look at (its Rule 2).
    assert "no captured image" in body or "no captured picture" in body


def test_09c_still_refuses_to_infer_a_visual_fact_from_markup():
    body = (_AGENTS / "09c_a11y_judge/agent.md").read_text(encoding="utf-8")
    assert "Never infer a visual fact from" in body


@pytest.mark.parametrize("agent", ["09b_test_automation", "09c_a11y_judge"])
def test_the_edited_bodies_still_pass_the_platform_reference_sweep(agent):
    """AGENT_MIGRATION_SPEC §8: a migrated body naming a local file is a failed migration. The
    capture path is the one exception and it is the *worktree*, not platform state — it is
    named as a file the suite writes, which is exactly what it is."""
    body = (_AGENTS / agent / "agent.md").read_text(encoding="utf-8")
    for banned in ("tasks.md", "requirements.md", "CLAUDE.md", ".claude/", "docs/"):
        assert banned not in body, banned


def test_the_companion_module_mirrors_the_junit_collectors_discipline():
    """One reader of a compliance format, and the platform owns it. Two is two formats."""
    body = (_RUNNER / "companion/a11ycapture.py").read_text(encoding="utf-8")
    assert "from apps.a11y.capture import" in body        # the platform's parser, imported
    assert "def parse_capture" not in body                # never a second copy of it


# ── isolation ───────────────────────────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_rls_hides_one_tenants_captured_screens_from_another():
    """Proven on a connection opened as the non-superuser app role — the Django test connection
    is the privileged migration role and bypasses RLS entirely. These rows carry a client's own
    markup and the text on their pages."""
    a = Tenant.objects.create(name="A")
    b = Tenant.objects.create(name="B")
    for tenant, mark in ((a, "A-secret"), (b, "B-secret")):
        project = Project.objects.create(tenant=tenant, name="p")
        ingest_screen(
            tenant_id=str(tenant.id), project_id=str(project.id),
            screen=parse_capture(json.dumps(_screen(route=f"/{mark}")))[0],
            object_store=InMemoryObjectStore(),
        )

    sd = connection.settings_dict
    with connection.cursor() as cur:
        cur.execute("SELECT current_database()")
        dbname = cur.fetchone()[0]
    raw = psycopg.connect(
        host=sd["HOST"], port=sd["PORT"], dbname=dbname,
        user=settings.APP_DB_USER, password=settings.APP_DB_PASSWORD, autocommit=True,
    )
    try:
        with raw.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [str(a.id)])
            cur.execute("SELECT DISTINCT route FROM a11y_a11ycandidatebundle")
            assert cur.fetchall() == [("/A-secret",)]

            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [""])
            cur.execute("SELECT count(*) FROM a11y_a11ycandidatebundle")
            assert cur.fetchone()[0] == 0        # no tenant context -> fail closed
    finally:
        raw.close()
