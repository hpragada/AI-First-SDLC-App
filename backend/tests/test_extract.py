"""P1 — static-file extraction adapters (Word/Excel/PDF → markdown)."""
import io

import pytest

from integrations.extract import ExtractionError, extract


def _docx_bytes() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading("Product Requirements", level=1)
    doc.add_paragraph("The system shall let a user log in.")
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "ID"
    table.rows[0].cells[1].text = "Title"
    table.rows[1].cells[0].text = "US-1"
    table.rows[1].cells[1].text = "Login"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _xlsx_bytes() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Stories"
    ws.append(["ID", "Title"])
    ws.append(["US-1", "Login"])
    ws.append(["US-2", "Logout"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_extract_docx_headings_paragraphs_tables():
    title, body = extract(filename="PRD.docx", mime="", content=_docx_bytes())
    assert title == "PRD"
    assert "# Product Requirements" in body
    assert "The system shall let a user log in." in body
    assert "| ID | Title |" in body and "| US-1 | Login |" in body


def test_extract_xlsx_sheets_as_tables():
    title, body = extract(filename="backlog.xlsx", mime="", content=_xlsx_bytes())
    assert title == "backlog"
    assert "## Stories" in body
    assert "| ID | Title |" in body
    assert "US-1" in body and "US-2" in body


def test_extract_txt_returns_body_as_is():
    title, body = extract(
        filename="context.txt", mime="text/plain",
        content=b"# Notes\n\nThe billing service handles invoices.\n",
    )
    assert title == "context"
    assert "# Notes" in body
    assert "The billing service handles invoices." in body


def test_extract_html_strips_tags_keeps_structure():
    html = (
        b"<html><head><style>.x{color:red}</style><title>t</title></head>"
        b"<body><h1>Design</h1><p>Screens for <b>login</b>.</p>"
        b"<ul><li>Home</li><li>Profile</li></ul>"
        b"<script>alert('x')</script></body></html>"
    )
    title, body = extract(filename="ux.html", mime="text/html", content=html)
    assert title == "ux"
    assert "# Design" in body
    assert "Screens for login." in body
    assert "- Home" in body and "- Profile" in body
    # script/style contents are dropped
    assert "alert" not in body and "color:red" not in body


def test_extract_pdf_preserves_line_structure(monkeypatch):
    """BF-BUG-3a: PDF text arrives one line per visual line. The extractor must keep each line
    on its own line (markdown hard break) so the preview doesn't collapse a page into one
    wall-of-text paragraph, and must not inject '## Page N' noise."""
    import pypdf

    class _FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class _FakeReader:
        def __init__(self, *_a, **_k):
            self.pages = [
                _FakePage("System Architecture\nExecutive Summary\nPattern: SPA"),
                _FakePage("Second page opening line"),
            ]

    monkeypatch.setattr(pypdf, "PdfReader", _FakeReader)
    _title, body = extract(filename="arch.pdf", mime="application/pdf", content=b"%PDF-1.4")
    assert "## Page" not in body  # no page-number noise
    # each visual line stays on its own line via a markdown hard break (trailing two spaces)
    assert "System Architecture  \nExecutive Summary  \nPattern: SPA" in body
    # the lines are NOT space-joined into one paragraph (the wall-of-text failure)
    assert "System Architecture Executive Summary" not in body


def test_extract_pdf_empty_when_no_text(monkeypatch):
    """An image-only PDF yields no text — the extractor returns '' (the ingest layer turns that
    into a helpful note; BF-BUG-3b)."""
    import pypdf

    class _BlankReader:
        def __init__(self, *_a, **_k):
            self.pages = [type("P", (), {"extract_text": lambda self: ""})()]

    monkeypatch.setattr(pypdf, "PdfReader", _BlankReader)
    _title, body = extract(filename="scan.pdf", mime="application/pdf", content=b"%PDF-1.4")
    assert body == ""


def test_unsupported_type_raises():
    with pytest.raises(ExtractionError):
        extract(filename="logo.png", mime="image/png", content=b"\x89PNG\r\n")


def test_corrupt_pdf_wrapped_as_extraction_error():
    # routes to the pdf adapter (by extension), which fails on garbage bytes.
    with pytest.raises(ExtractionError):
        extract(filename="broken.pdf", mime="application/pdf", content=b"not a real pdf")
