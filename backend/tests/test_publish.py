"""P1 — publish-to-SoR resolution + idempotent DocStore push (pure, no DB/network)."""
from integrations.publish import publish_doc, render_html, resolve_capability
from integrations.types import ExternalRef


class _FakeDocStore:
    def __init__(self):
        self.created: list[dict] = []
        self.updated: list[dict] = []

    def create_page(self, *, space, title, body_html, parent_ref=None):
        self.created.append({"space": space, "title": title, "body_html": body_html})
        return ExternalRef(sor="confluence", id="PAGE-1",
                           url="https://x.atlassian.net/wiki/PAGE-1", version=1)

    def update_page(self, *, page_ref, title, body_html, base_version):
        self.updated.append({"page_ref": page_ref, "base_version": base_version})
        return ExternalRef(sor="confluence", id=page_ref,
                           url=f"https://x.atlassian.net/wiki/{page_ref}", version=base_version + 1)


def test_resolve_capability_maps_doc_types_to_docstore():
    assert resolve_capability("prd") == "docstore"
    assert resolve_capability("requirements") == "docstore"
    assert resolve_capability("architecture") == "docstore"
    assert resolve_capability("ideation") is None       # internal
    assert resolve_capability("backlog") is None         # reconciliation, not publish


def test_render_html_converts_markdown():
    html = render_html("# Title\n\nHello **world**")
    assert "<h1>" in html and "Title" in html
    assert "<strong>world</strong>" in html


def test_publish_doc_creates_when_no_external_ref():
    ds = _FakeDocStore()
    ref = publish_doc(ds, space="SDLC", title="PRD", body_md="# PRD\nbody")
    assert ref == ExternalRef(sor="confluence", id="PAGE-1",
                              url="https://x.atlassian.net/wiki/PAGE-1", version=1)
    assert ds.created and "<h1>" in ds.created[0]["body_html"]
    assert not ds.updated


def test_publish_doc_updates_when_external_ref_present():
    ds = _FakeDocStore()
    ref = publish_doc(ds, space="SDLC", title="PRD", body_md="# PRD v2",
                      external_ref={"id": "PAGE-9", "version": 3})
    assert ref.id == "PAGE-9" and ref.version == 4  # base_version + 1
    assert ds.updated == [{"page_ref": "PAGE-9", "base_version": 3}]
    assert not ds.created
