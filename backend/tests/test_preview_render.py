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


# ── S.No 187: machine-readable bodies, rendered for a human ─────────
import json  # noqa: E402

from integrations.preview import _detect_content_type, _render_sbom  # noqa: E402

BACKSLASH = chr(92)   # written this way so no tool between here
                      # and the file can eat the escape

_SBOM = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.5",
    "metadata": {
        "timestamp": "2026-09-04T11:22:08Z",
        "tools": {"components": [{"name": "syft", "version": "1.9.0"}]},
    },
    "components": [
        {"type": "library", "name": "django", "version": "5.1.4",
         "licenses": [{"license": {"id": "BSD-3-Clause"}}]},
        {"type": "library", "name": "psycopg", "version": "3.2.3",
         "licenses": [{"license": {"name": "LGPL-3.0"}}]},
        {"type": "library", "name": "boto3", "version": "1.35.42",
         "licenses": [{"expression": "Apache-2.0"}]},
    ],
}


def test_sbom_renders_as_a_summary_and_a_table():
    """Bugs S.No 187: the security phase's CycloneDX SBOM previewed as one unbroken run of
    characters, because every internal body was announced as markdown whatever was in it."""
    out, summary = _render_sbom(json.dumps(_SBOM))
    # The headline figures come back STRUCTURED, so the screen can lay them out as labelled
    # numbers. They used to be a run-on line of bold prose, which is not what was approved.
    assert summary == {"components": 3, "licences": 3, "tool": "syft 1.9.0",
                       "taken": "2026-09-04T11:22:08Z", "spec_version": "1.5"}
    # ...and the timestamp stays ISO: only the browser knows the reader's locale.
    assert summary["taken"].endswith("Z")
    # a GFM table the preview screen already knows how to render
    assert "| Package | Version | Licence | Type |" in out
    assert "| django | 5.1.4 | BSD-3-Clause | library |" in out
    # every shape CycloneDX allows a licence to take
    assert "LGPL-3.0" in out and "Apache-2.0" in out
    assert "Showing all 3 components." in out


def test_a_large_sbom_is_summarised_never_silently_cut_short():
    """The count line must always state the TRUE total, so a reader is never shown a partial
    inventory believing it is the whole one."""
    big = {**_SBOM, "components": [
        {"type": "library", "name": f"pkg-{i}", "version": "1.0.0"} for i in range(640)
    ]}
    out, summary = _render_sbom(json.dumps(big))
    assert summary["components"] == 640
    assert "Showing the first 200 of 640 components" in out
    assert "View raw" in out          # and it says how to see the rest
    assert out.count("| pkg-") == 200


def test_vulnerabilities_are_surfaced_when_present():
    doc = {**_SBOM, "vulnerabilities": [{
        "id": "CVE-2026-1234",
        "ratings": [{"severity": "high"}],
        "affects": [{"ref": "pkg:pypi/django@5.1.4"}],
        "description": "Header injection via the admin login form.",
    }]}
    out, _ = _render_sbom(json.dumps(doc))
    assert "## Vulnerabilities" in out
    assert "CVE-2026-1234" in out and "high" in out
    assert "pkg:pypi/django@5.1.4" in out


def test_a_pipe_in_a_value_cannot_break_the_table():
    doc = {**_SBOM, "components": [
        {"type": "library", "name": "odd|name", "version": "1.0", "licenses": []}]}
    out, _ = _render_sbom(json.dumps(doc))
    row = next(line for line in out.splitlines() if "odd" in line)
    escaped = BACKSLASH + "|"
    assert escaped in row                                   # the value's pipe is escaped
    assert row.replace(escaped, "").count("|") == 5         # 4 cells, not 5
    assert "odd" + escaped + "name" in row


def test_a_body_that_is_not_an_sbom_is_left_alone():
    """A malformed or unexpected file degrades to plain text rather than raising."""
    assert _render_sbom("not json at all") == ("", {})
    assert _render_sbom('{"just": "some json"}') == ("", {})
    assert _render_sbom('{"bomFormat": "SPDX"}') == ("", {})
    assert _render_sbom("") == ("", {})


def test_format_detection_is_conservative():
    """Detection recognises only what the first character makes unambiguous. A markdown
    document full of `Key: value` lines is valid YAML and one with commas looks like CSV, so
    guessing at those would break far more documents than it would fix."""
    assert _detect_content_type('{"a": 1}') == "application/json"
    assert _detect_content_type("[1, 2, 3]") == "application/json"
    assert _detect_content_type('<?xml version="1.0"?><a/>') == "application/xml"
    # everything else stays markdown
    assert _detect_content_type("# A heading\n\nSome prose.") == "text/markdown"
    assert _detect_content_type("Name: Ada\nRole: engineer") == "text/markdown"   # valid YAML
    assert _detect_content_type("a,b,c\n1,2,3") == "text/markdown"                # looks like CSV
    assert _detect_content_type("123") == "text/markdown"                # valid JSON, not JSON
    assert _detect_content_type("{ not really json") == "text/markdown"
    assert _detect_content_type("") == "text/markdown"
