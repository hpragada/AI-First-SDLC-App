"""Part B1 — the vision pipe: a document's stored page images are read from the object store,
downscaled to a vision-sane size, and assembled as image blocks the onboarding/vision agent can
SEE. Pure/unit coverage (no DB): the DB read in get_page_images is verified live against the
platform. See onboarding_fidelity_plan Part B."""
import base64
import io

import pymupdf
from PIL import Image as PILImage

from storage.object_store import InMemoryObjectStore


def _png(w: int = 200, h: int = 80, text: str = "X") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=w, height=h)
    page.insert_text((20, 50), text, fontsize=20)
    return page.get_pixmap().tobytes("png")


def _big_png(long_edge: int = 4000) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=long_edge, height=long_edge // 2)
    page.insert_text((60, 120), "DIAGRAM", fontsize=80)
    return page.get_pixmap(dpi=150).tobytes("png")


def test_downscale_shrinks_big_image_to_vision_ceiling():
    from integrations.extract import _VISION_MAX_PX, downscale_image_for_vision

    big = _big_png()
    out = downscale_image_for_vision(big)
    w, h = PILImage.open(io.BytesIO(out)).size
    assert max(w, h) <= _VISION_MAX_PX
    assert len(out) < len(big)  # payload actually trimmed


def test_downscale_leaves_small_image_within_ceiling():
    from integrations.extract import _VISION_MAX_PX, downscale_image_for_vision

    out = downscale_image_for_vision(_png())
    w, h = PILImage.open(io.BytesIO(out)).size
    assert max(w, h) <= _VISION_MAX_PX
    assert out[:8] == b"\x89PNG\r\n\x1a\n"


def test_downscale_passes_through_undecodable_bytes():
    from integrations.extract import downscale_image_for_vision

    assert downscale_image_for_vision(b"not an image") == b"not an image"


def test_build_window_paginates_and_base64_encodes():
    from mcp_platform_state.tools import (
        _MAX_VISION_IMAGES_PER_CALL,
        _build_page_image_window,
    )

    store = InMemoryObjectStore()
    pages = []
    for i in range(1, 7):  # a 6-page upload
        key = f"views/page{i}.png"
        store.put(key, _png(text=str(i)))
        pages.append({"name": f"page{i}.png", "s3_key": key, "mime": "image/png", "page": i})

    first = _build_page_image_window(pages, store, 0)
    assert first["total"] == 6
    assert first["returned"] == _MAX_VISION_IMAGES_PER_CALL
    assert first["start"] == 0 and first["next_start"] == _MAX_VISION_IMAGES_PER_CALL
    for im in first["images"]:
        assert im["mime"] == "image/png"
        assert base64.b64decode(im["data_base64"])[:8] == b"\x89PNG\r\n\x1a\n"

    second = _build_page_image_window(pages, store, first["next_start"])
    assert second["returned"] == 2 and second["next_start"] is None  # last batch


def test_build_window_skips_missing_object_and_keyless_pointer():
    from mcp_platform_state.tools import _build_page_image_window

    store = InMemoryObjectStore()
    store.put("views/ok.png", _png())
    pages = [
        {"name": "ok.png", "s3_key": "views/ok.png", "page": 1},
        {"name": "gone.png", "s3_key": "views/missing.png", "page": 2},  # not in the store
        {"name": "noref", "page": 3},                                    # no s3_key at all
    ]
    res = _build_page_image_window(pages, store, 0)
    assert res["total"] == 3 and res["returned"] == 1
    assert res["images"][0]["name"] == "ok.png"


def test_build_window_empty_when_no_pages():
    from mcp_platform_state.tools import _build_page_image_window

    res = _build_page_image_window([], InMemoryObjectStore(), 0)
    assert res == {"images": [], "total": 0, "start": 0, "returned": 0, "next_start": None}


def test_encoded_image_reconstructs_as_mcp_image_block():
    """The MCP wrappers (companion state_mcp + backend server) decode `data_base64` into a
    FastMCP Image → ImageContent. Lock that exact round-trip so the pipe the B0 spike proved
    stays intact."""
    from mcp.server.fastmcp import Image as McpImage
    from mcp_platform_state.tools import _build_page_image_window

    store = InMemoryObjectStore()
    store.put("v/p1.png", _png())
    res = _build_page_image_window(
        [{"name": "p1.png", "s3_key": "v/p1.png", "page": 1}], store, 0)
    im = res["images"][0]
    block = McpImage(data=base64.b64decode(im["data_base64"]), format=im["mime"].split("/")[-1])
    content = block.to_image_content()
    assert content.type == "image" and content.mimeType == "image/png" and content.data
