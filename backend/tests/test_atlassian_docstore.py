"""P1 — Atlassian DocStore (Confluence) connector.

Contract tests drive a mocked transport (no network — CI-safe) to pin the requests the
connector builds and the vendor-free objects it returns. A live round-trip
(create→get→update→delete) runs only when Atlassian creds are configured in .env.
"""
import uuid

import pytest

from integrations.atlassian.config import AtlassianConfig
from integrations.atlassian.docstore import AtlassianDocStore
from integrations.types import CapabilityError, DocHit, DocPage, ExternalRef

_CFG = AtlassianConfig(site_url="https://x.atlassian.net", email="e@x.test", api_token="tok")


class _Router:
    """Routes a transport call by (method, url-substring) to a canned (status, data)."""

    def __init__(self):
        self.calls: list[dict] = []
        self._routes: list[tuple[str, str, int, object]] = []

    def add(self, method, contains, status, data):
        self._routes.append((method, contains, status, data))
        return self

    def __call__(self, method, url, headers, body):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body})
        for m, c, status, data in self._routes:
            if m == method and c in url:
                return status, data
        raise AssertionError(f"no route for {method} {url}")


def _page(pid="123", version=1, title="PRD", body="<p>x</p>"):
    return {
        "id": pid, "title": title, "spaceId": "99",
        "version": {"number": version},
        "body": {"storage": {"value": body, "representation": "storage"}},
        "_links": {"webui": f"/spaces/SDLC/pages/{pid}/{title}"},
    }


# ── contract tests (mock transport) ─────────────────────────────────
def test_create_page_posts_storage_body_and_returns_ref():
    t = (_Router()
         .add("GET", "/wiki/api/v2/spaces", 200, {"results": [{"id": "99", "key": "SDLC"}]})
         .add("POST", "/wiki/api/v2/pages", 200, _page()))
    ds = AtlassianDocStore(_CFG, transport=t)

    ref = ds.create_page(space="SDLC", title="PRD", body_html="<p>hello</p>")

    assert ref == ExternalRef(
        sor="confluence", id="123",
        url="https://x.atlassian.net/wiki/spaces/SDLC/pages/123/PRD", version=1,
    )
    post = next(c for c in t.calls if c["method"] == "POST")
    assert post["body"]["spaceId"] == "99"
    assert post["body"]["body"] == {"representation": "storage", "value": "<p>hello</p>"}
    assert post["body"]["title"] == "PRD"
    assert post["headers"]["Authorization"].startswith("Basic ")


def test_update_page_increments_version():
    t = _Router().add("PUT", "/wiki/api/v2/pages/123", 200, _page(version=3))
    ds = AtlassianDocStore(_CFG, transport=t)

    ref = ds.update_page(page_ref="123", title="PRD", body_html="<p>v3</p>", base_version=2)

    assert ref.version == 3
    put = t.calls[0]
    assert put["body"]["version"] == {"number": 3}  # base_version + 1
    assert put["body"]["id"] == "123"


def test_get_page_parses_storage_body():
    t = _Router().add("GET", "/wiki/api/v2/pages/123", 200, _page(version=2, body="<p>doc</p>"))
    ds = AtlassianDocStore(_CFG, transport=t)

    page = ds.get_page(page_ref="123")

    assert isinstance(page, DocPage)
    assert page.body_html == "<p>doc</p>"
    assert page.version == 2
    assert t.calls[0]["url"].endswith("body-format=storage")


def test_search_builds_scoped_cql():
    t = _Router().add("GET", "/wiki/rest/api/search", 200, {
        "results": [{"content": {"id": "55"}, "title": "PRD", "url": "/spaces/SDLC/pages/55"}]
    })
    ds = AtlassianDocStore(_CFG, transport=t)

    hits = ds.search(query="PRD", space="SDLC")

    assert hits == [DocHit(id="55", title="PRD",
                           url="https://x.atlassian.net/wiki/spaces/SDLC/pages/55")]
    url = t.calls[0]["url"]
    # CQL is url-encoded; `~` is RFC-3986 unreserved so urlencode leaves it literal.
    assert "space%3D%22SDLC%22" in url and "title+~+%22PRD%22" in url


def test_http_error_raises_capability_error():
    t = _Router().add("GET", "/wiki/api/v2/spaces", 404, {"message": "nope"})
    ds = AtlassianDocStore(_CFG, transport=t)
    with pytest.raises(CapabilityError) as exc:
        ds.create_page(space="SDLC", title="x", body_html="<p/>")
    assert exc.value.status == 404


# ── live round-trip (runs only with real creds) ─────────────────────
def _live_config() -> AtlassianConfig | None:
    cfg = AtlassianConfig.from_settings()
    return cfg if cfg.configured else None


@pytest.mark.skipif(_live_config() is None, reason="Atlassian creds not configured in .env")
def test_confluence_live_create_get_update_delete():
    from django.conf import settings

    cfg = _live_config()
    space = settings.CONFLUENCE_SPACE_KEY
    assert space, "CONFLUENCE_SPACE_KEY must be set for the live test"
    ds = AtlassianDocStore(cfg)
    title = f"sdlc-platform smoke {uuid.uuid4().hex[:8]}"

    ref = ds.create_page(space=space, title=title, body_html="<p>platform-smoke v1</p>")
    try:
        assert ref.sor == "confluence" and ref.id and ref.version == 1

        fetched = ds.get_page(page_ref=ref.id)
        assert fetched.title == title
        assert "platform-smoke v1" in fetched.body_html

        updated = ds.update_page(
            page_ref=ref.id, title=title, body_html="<p>platform-smoke v2</p>",
            base_version=fetched.version,
        )
        assert updated.version == 2
        assert "platform-smoke v2" in ds.get_page(page_ref=ref.id).body_html
    finally:
        ds.delete_page(page_ref=ref.id)  # keep the test space clean
