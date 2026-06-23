"""Static-file extraction (B4) — Word/Excel/PDF → markdown text.

Best-effort structural extraction so an uploaded document becomes a reviewable internal
artifact body. Word headings/paragraphs/tables, Excel sheets-as-tables, PDF text per
page. The output is markdown (the artifact body format used everywhere else).
"""
from __future__ import annotations

import io


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
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            parts.append(f"## Page {i}\n\n{text}")
    return "\n\n".join(parts)


def _kind(mime: str, ext: str) -> str | None:
    mime = (mime or "").lower()
    if ext == "docx" or "wordprocessingml" in mime:
        return "docx"
    if ext == "xlsx" or "spreadsheetml" in mime:
        return "xlsx"
    if ext == "pdf" or mime == "application/pdf":
        return "pdf"
    return None


def extract(*, filename: str, mime: str, content: bytes) -> tuple[str, str]:
    """Return (title, markdown_body) for a supported static file."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    kind = _kind(mime, ext)
    if kind is None:
        raise ExtractionError(f"unsupported file type: {filename!r} ({mime!r})")
    extractor = {"docx": _extract_docx, "xlsx": _extract_xlsx, "pdf": _extract_pdf}[kind]
    try:
        body = extractor(content)
    except ExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface any parse failure as ExtractionError
        raise ExtractionError(f"failed to extract {filename!r}: {exc}") from exc
    title = filename.rsplit(".", 1)[0] if "." in filename else filename
    return title, body
