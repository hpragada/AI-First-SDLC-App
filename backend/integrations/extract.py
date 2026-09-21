"""Static-file extraction (B4) — Word/Excel/PDF/Text/HTML → markdown text + images.

Best-effort **high-fidelity** extraction so an uploaded document becomes a reviewable internal
artifact body without losing content (onboarding_fidelity_plan Part A). Each adapter returns
``(markdown_body, images)`` where ``images`` is a list of ``{name, bytes, mime, page}`` for the
raster pictures embedded in the source — the ingest layer persists those and renders page images
so nothing pictorial is silently dropped. PDFs use PyMuPDF (text+layout, tables reconstructed as
markdown, embedded images); Word pulls headings/paragraphs/tables + embedded images; Excel gives
sheets-as-tables; plain text passes through; HTML is stripped to text with `<img>` captured. The
body is markdown (the artifact-body format used everywhere else).
"""
from __future__ import annotations

import base64
import io
import logging
import re
from html.parser import HTMLParser

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """The file could not be extracted (unsupported type or corrupt content)."""


# One extracted raster image: name (stable-ish), raw bytes, mime, and source page (PDF) or None.
Image = dict


def _table_md(rows: list[list]) -> str:
    rows = [[("" if c is None else str(c)) for c in r] for r in rows]
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [r + [""] * (width - len(r)) for r in rows]
    out = [
        "| " + " | ".join(norm[0]) + " |",
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]
    for r in norm[1:]:
        out.append("| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in r) + " |")
    return "\n".join(out)


def _extract_docx(content: bytes) -> tuple[str, list[Image]]:
    from docx import Document

    doc = Document(io.BytesIO(content))
    parts: list[str] = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        style = (p.style.name or "").lower() if p.style else ""
        if style.startswith("heading"):
            level = "".join(ch for ch in style if ch.isdigit())
            parts.append("#" * (int(level) if level else 2) + " " + text)
        else:
            parts.append(text)
    for table in doc.tables:
        md = _table_md([[c.text.strip() for c in row.cells] for row in table.rows])
        if md:
            parts.append(md)
    # Embedded images live as document relationships (Part A: don't drop pictures).
    images: list[Image] = []
    for rel in doc.part.rels.values():
        try:
            if "image" not in rel.reltype:
                continue
            part = rel.target_part
            ct = getattr(part, "content_type", "") or "image/png"
            ext = (ct.split("/")[-1].split("+")[0] or "png").lower()
            images.append({"name": f"docx-img{len(images) + 1}.{ext}", "bytes": part.blob,
                           "mime": ct, "page": None})
        except Exception:  # noqa: BLE001 — a bad rel must not fail the whole extraction
            continue
    return "\n\n".join(parts), images


def _extract_xlsx(content: bytes) -> tuple[str, list[Image]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    parts: list[str] = []
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        md = _table_md(rows)
        if md:
            parts.append(f"## {ws.title}\n\n{md}")
    return "\n\n".join(parts), []


def _clean_pdf_markdown(md: str) -> str:
    """Tidy pymupdf4llm output for the markdown preview + downstream agents:
    - `<br>` (used for in-cell line breaks) renders as *literal* text in the preview
      (react-markdown escapes raw HTML), so flatten it to a space.
    - Drop fully-empty tables and bare `#` headings — an image-only page (e.g. wireframes)
      yields only an empty table skeleton, which otherwise renders as blank grids and is
      mistaken for real text. Real tables (any cell with word content) are kept.
    """
    md = re.sub(r"<br\s*/?>", " ", md)
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            block = lines[i:j]
            has_content = any(
                re.search(r"[A-Za-z0-9]", row) and not re.fullmatch(r"[\s|:\-]+", row.strip())
                for row in block
            )
            if has_content:
                out.extend(block)
            i = j
            continue
        if re.fullmatch(r"#+\s*", lines[i].strip()):  # bare heading, no title
            i += 1
            continue
        out.append(lines[i].rstrip())
        i += 1
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _extract_pdf(content: bytes) -> tuple[str, list[Image]]:
    """PDF → markdown via pymupdf4llm (clean paragraphs + reconstructed tables, far better than
    hand-rolled block extraction) + the embedded raster images (captured, never dropped)."""
    import pymupdf
    import pymupdf4llm

    images: list[Image] = []
    with pymupdf.open(stream=content, filetype="pdf") as doc:
        body = _clean_pdf_markdown(pymupdf4llm.to_markdown(doc, show_progress=False) or "")
        for pno, page in enumerate(doc, start=1):
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    base = doc.extract_image(xref)
                except Exception:  # noqa: BLE001
                    continue
                ext = (base.get("ext") or "png").lower()
                images.append({"name": f"page{pno}-img{xref}.{ext}", "bytes": base["image"],
                               "mime": f"image/{ext}", "page": pno})
    return body.strip(), images


def pdf_page_pngs(content: bytes, *, dpi: int = 130) -> list[Image]:
    """Render each PDF page to a PNG — the faithful visual of the upload, for the 'see your
    original' viewer (A3) and the vision step (Part B). Best-effort per page; `dpi` kept modest
    so storage + downstream vision cost stay sane."""
    import pymupdf

    out: list[Image] = []
    with pymupdf.open(stream=content, filetype="pdf") as doc:
        for pno, page in enumerate(doc, start=1):
            try:
                pix = page.get_pixmap(dpi=dpi)
                out.append({"name": f"page{pno}.png", "bytes": pix.tobytes("png"),
                            "mime": "image/png", "page": pno})
            except Exception:  # noqa: BLE001 — one bad page must not lose the rest
                continue
    return out


# Long-edge ceiling for images handed to the vision engine (Part B). Claude downsamples anything
# larger than ~1568px on the long edge before it ever reaches the model, so shrinking to this only
# trims upload size + tokens — it never costs the model any detail. Guards the on-adopt vision
# volume the plan calls for (onboarding_fidelity_plan Part B guards).
_VISION_MAX_PX = 1568


def downscale_image_for_vision(data: bytes, *, max_px: int = _VISION_MAX_PX) -> bytes:
    """Shrink an image so its long edge is ≤ ``max_px``, re-encoded as PNG (lossless — keeps a
    diagram's / screenshot's text crisp for the reader model). Only ever downscales; a smaller
    image is returned unchanged. Best-effort: if the bytes can't be decoded, they pass through
    untouched so the pipe never fails on one odd image."""
    try:
        try:
            from PIL import Image as PILImage
        except ImportError as exc:
            # Pillow absent means NOTHING is ever downscaled — every page render travels at full
            # size and eventually overruns the MCP transport's message limit, killing the run with
            # an error that names the transport and never mentions the real cause. That is exactly
            # how this went unnoticed: image-light documents squeaked through, image-heavy ones
            # failed intermittently, and the pass-through below hid the reason. A dependency this
            # load-bearing must fail loudly, not degrade into a puzzle.
            raise RuntimeError(
                "Pillow is not installed, so page images cannot be downscaled for the vision "
                "agent. Full-size renders overrun the agent transport and fail the run. Install "
                "Pillow (it is in requirements.txt — the image is likely stale and needs "
                "rebuilding)."
            ) from exc

        with PILImage.open(io.BytesIO(data)) as im:
            if im.mode not in ("RGB", "RGBA", "L"):
                im = im.convert("RGB")
            long_edge = max(im.size)
            if long_edge > max_px:
                ratio = max_px / long_edge
                im = im.resize(
                    (max(1, round(im.width * ratio)), max(1, round(im.height * ratio))),
                    PILImage.LANCZOS,
                )
            out = io.BytesIO()
            im.save(out, format="PNG")
            return out.getvalue()
    except RuntimeError:
        raise           # a missing Pillow is a deployment fault, not "one odd image"
    except Exception:  # noqa: BLE001 — a bad image must not break the vision pipe
        return data


def _extract_txt(content: bytes) -> tuple[str, list[Image]]:
    """Plain text is already the artifact-body format — decode and return as-is."""
    return content.decode("utf-8", "replace").strip(), []


class _HTMLTextExtractor(HTMLParser):
    """Strip HTML to readable text: skip script/style, keep headings (as markdown #), list items
    (as '- '), block boundaries (as blank lines), and capture `<img>` (Part A: keep pictures —
    data-URI images carry bytes; external ones keep their src). Stdlib only."""

    _SKIP = {"script", "style", "head", "noscript", "template"}
    _HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    _BLOCK = {"p", "div", "section", "article", "header", "footer", "br",
              "ul", "ol", "table", "tr", "blockquote", "pre"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.images: list[Image] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._HEADINGS:
            self.parts.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "img":
            self._capture_img(dict(attrs))
        elif tag in self._BLOCK:
            self.parts.append("\n\n")

    def _capture_img(self, attrs: dict) -> None:
        src = attrs.get("src") or ""
        alt = attrs.get("alt") or ""
        n = len(self.images) + 1
        m = re.match(r"data:(image/[\w.+-]+);base64,(.*)$", src, re.DOTALL)
        if m:
            mime = m.group(1)
            try:
                raw = base64.b64decode(m.group(2), validate=False)
            except Exception:  # noqa: BLE001
                raw = b""
            if raw:
                ext = mime.split("/")[-1].split("+")[0] or "png"
                self.images.append({"name": f"html-img{n}.{ext}", "bytes": raw,
                                    "mime": mime, "page": None})
        elif src:
            # External image — keep the reference (no bytes to persist without a fetch).
            self.images.append({"name": alt or f"html-img{n}", "src": src,
                                "mime": None, "bytes": None, "page": None})

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._HEADINGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = " ".join(data.split())
        if text:
            self.parts.append(text + " ")


def _extract_html(content: bytes) -> tuple[str, list[Image]]:
    parser = _HTMLTextExtractor()
    parser.feed(content.decode("utf-8", "replace"))
    parser.close()
    lines = [ln.rstrip() for ln in "".join(parser.parts).splitlines()]
    out = "\n".join(lines)
    # Inline tags (<b>, <a>, …) split text into chunks each padded with a trailing space,
    # which leaves a gap before punctuation ("login ."). Close those gaps.
    out = re.sub(r"[ \t]+([.,;:!?)])", r"\1", out)
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out.strip(), parser.images


def _kind(mime: str, ext: str) -> str | None:
    mime = (mime or "").lower()
    if ext == "docx" or "wordprocessingml" in mime:
        return "docx"
    if ext == "xlsx" or "spreadsheetml" in mime:
        return "xlsx"
    if ext == "pdf" or mime == "application/pdf":
        return "pdf"
    if ext in ("html", "htm") or mime == "text/html":
        return "html"
    if ext == "txt" or mime == "text/plain":
        return "txt"
    return None


def extract(*, filename: str, mime: str, content: bytes) -> tuple[str, str, list[Image]]:
    """Return ``(title, markdown_body, images)`` for a supported static file. ``images`` holds the
    embedded raster pictures ({name, bytes, mime, page}); it's empty for text-only sources."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    kind = _kind(mime, ext)
    if kind is None:
        # Screen Words group 5. A person who drags a .zip onto the dropzone saw
        # "file: unsupported file type: 'x.zip' ('application/zip')" — the field key, the quoted
        # filename, the MIME type, and no hint of what WOULD work. Naming the accepted kinds is
        # the whole point of the message.
        raise ExtractionError(
            "That file type can't be read. Upload a Word document, a PDF, a spreadsheet, "
            "a text file or an HTML page."
        )
    extractor = {
        "docx": _extract_docx, "xlsx": _extract_xlsx, "pdf": _extract_pdf,
        "txt": _extract_txt, "html": _extract_html,
    }[kind]
    try:
        body, images = extractor(content)
    except ExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface any parse failure as ExtractionError
        # Screen Words group 5. A corrupt upload is reachable by anyone, and this handed the
        # reader the library's own exception text — "Package not found", "invalid literal for
        # int()" — which tells them nothing about their own file. The detail belongs in the log,
        # where a developer will look; the sentence belongs to the person who uploaded it.
        logger.warning("Extraction failed for %r (%s): %s", filename, mime, exc)
        raise ExtractionError(
            "That file couldn't be read — it may be corrupt, password-protected, or saved in "
            "an unusual format. Try re-saving it and uploading again."
        ) from exc
    title = filename.rsplit(".", 1)[0] if "." in filename else filename
    return title, body, images
