"""Static-file extraction (B4) — Word/Excel/PDF/Text/HTML → markdown text.

Best-effort structural extraction so an uploaded document becomes a reviewable internal
artifact body. Word headings/paragraphs/tables, Excel sheets-as-tables, PDF text per
page, plain text as-is, and HTML stripped to text (headings/lists preserved). The output
is markdown (the artifact body format used everywhere else). Text and HTML use only the
standard library — no new dependency.
"""
from __future__ import annotations

import io
import re
from html.parser import HTMLParser


class ExtractionError(Exception):
    """The file could not be extracted (unsupported type or corrupt content)."""


def _table_md(rows: list[list[str]]) -> str:
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


def _extract_docx(content: bytes) -> str:
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
    return "\n\n".join(parts)


def _extract_xlsx(content: bytes) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    parts: list[str] = []
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        md = _table_md(rows)
        if md:
            parts.append(f"## {ws.title}\n\n{md}")
    return "\n\n".join(parts)


def _extract_pdf(content: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if not text.strip():
            continue
        # PDF text arrives one line per visual line, but CommonMark (react-markdown/remark-gfm,
        # no `breaks`) collapses single newlines into spaces — which turns a whole page into one
        # wall-of-text paragraph. Preserve the visual line structure: emit each line with a
        # markdown hard break (trailing two spaces) so headings/rows stay on their own line, and
        # keep blank lines as paragraph breaks. No "Page N" headers (page breaks are arbitrary).
        lines = [ln.rstrip() for ln in text.splitlines()]
        rendered = "\n".join(f"{ln}  " if ln else "" for ln in lines)
        parts.append(rendered.strip())
    return "\n\n".join(parts)


def _extract_txt(content: bytes) -> str:
    """Plain text is already the artifact-body format — decode and return as-is."""
    return content.decode("utf-8", "replace").strip()


class _HTMLTextExtractor(HTMLParser):
    """Strip HTML to readable text: skip script/style, keep headings (as markdown #),
    list items (as '- '), and block boundaries (as blank lines). Stdlib only."""

    _SKIP = {"script", "style", "head", "noscript", "template"}
    _HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    _BLOCK = {"p", "div", "section", "article", "header", "footer", "br",
              "ul", "ol", "table", "tr", "blockquote", "pre"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._HEADINGS:
            self.parts.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in self._BLOCK:
            self.parts.append("\n\n")

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


def _extract_html(content: bytes) -> str:
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
    return out.strip()


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


def extract(*, filename: str, mime: str, content: bytes) -> tuple[str, str]:
    """Return (title, markdown_body) for a supported static file."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    kind = _kind(mime, ext)
    if kind is None:
        raise ExtractionError(f"unsupported file type: {filename!r} ({mime!r})")
    extractor = {
        "docx": _extract_docx, "xlsx": _extract_xlsx, "pdf": _extract_pdf,
        "txt": _extract_txt, "html": _extract_html,
    }[kind]
    try:
        body = extractor(content)
    except ExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface any parse failure as ExtractionError
        raise ExtractionError(f"failed to extract {filename!r}: {exc}") from exc
    title = filename.rsplit(".", 1)[0] if "." in filename else filename
    return title, body
