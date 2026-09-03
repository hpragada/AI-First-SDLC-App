"""Pure rendering of the structured `external_ref` preview (no DB)."""
from integrations.preview import render_structured_ref


def test_ingest_provenance_never_renders_as_body():
    """BF-BUG-3b: an image-only PDF has no extractable body, so the ONLY thing in external_ref
    is ingest provenance (source/filename/source_document_id/source_s3_key). Those are pointers,
    not content — they must not be rendered as the document body (which showed 'Source:
    static_file Filename: …' in the preview)."""
    ref = {
        "source": "static_file",
        "filename": "11_UX_Wireframes.pdf",
        "source_document_id": "abc-123",
        "source_s3_key": "onboarding/t/p/d/source/11_UX_Wireframes.pdf",
    }
    assert render_structured_ref(ref) == ""


def test_real_structured_content_still_renders():
    """Guard: the pointer-key exclusion must not swallow genuine agent content."""
    ref = {"filename": "x.pdf", "findings": ["SEC-1 open", "SEC-2 closed"]}
    body = render_structured_ref(ref)
    assert "## Findings" in body
    assert "SEC-1 open" in body
    assert "x.pdf" not in body  # the pointer key is still excluded
