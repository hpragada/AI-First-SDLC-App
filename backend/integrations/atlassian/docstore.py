"""AtlassianDocStore — the DocStore capability over Confluence Cloud.

Confluence REST v2 for pages (create/get/update), v1 CQL for search. Bodies are
storage-format HTML (decision D4). Returns vendor-free ExternalRef/DocPage/DocHit so
callers stay Confluence-unaware (#9). Pointers only — bodies are read through, never
copied into platform state (#1/#3).
"""
from __future__ import annotations

from integrations.types import CapabilityError, DocHit, DocPage, ExternalRef

from .config import AtlassianConfig
from .rest import AtlassianRest, Transport

_SOR = "confluence"


class AtlassianDocStore:
    def __init__(self, config: AtlassianConfig, transport: Transport | None = None):
        self._cfg = config
        self._rest = AtlassianRest(config, transport)
        self._space_ids: dict[str, str] = {}  # key -> numeric space id (cached)

    def ping(self) -> str:
        """Live reachability + auth check (Bugs S.No 156): who are we authenticated as? Cheap,
        read-only, and touches no space content."""
        me = self._rest.request("GET", "/wiki/rest/api/user/current") or {}
        who = me.get("displayName") or me.get("email") or "the account"
        return f"Signed in to Confluence at {self._cfg.site_url} as {who}."

    # ── helpers ─────────────────────────────────────────────────────
    def _space_id(self, space_key: str) -> str:
        if space_key not in self._space_ids:
            data = self._rest.request("GET", "/wiki/api/v2/spaces", query={"keys": space_key})
            results = (data or {}).get("results", [])
            if not results:
                raise CapabilityError(f"Confluence space not found: {space_key!r}")
            self._space_ids[space_key] = str(results[0]["id"])
        return self._space_ids[space_key]

    def _web_url(self, page: dict) -> str:
        webui = (page.get("_links") or {}).get("webui", "")
        return f"{self._cfg.site_url}/wiki{webui}" if webui else self._cfg.site_url

    def _ref(self, page: dict) -> ExternalRef:
        return ExternalRef(
            sor=_SOR, id=str(page["id"]), url=self._web_url(page),
            version=int((page.get("version") or {}).get("number", 1)),
        )

    # ── DocStore capability ─────────────────────────────────────────
    def create_page(self, *, space: str, title: str, body_html: str,
                    parent_ref: str | None = None) -> ExternalRef:
        body = {
            "spaceId": self._space_id(space),
            "status": "current",
            "title": title,
            "body": {"representation": "storage", "value": body_html},
        }
        if parent_ref:
            body["parentId"] = str(parent_ref)
        page = self._rest.request("POST", "/wiki/api/v2/pages", body=body)
        return self._ref(page)

    def update_page(self, *, page_ref: str, title: str, body_html: str,
                    base_version: int) -> ExternalRef:
        body = {
            "id": str(page_ref),
            "status": "current",
            "title": title,
            "body": {"representation": "storage", "value": body_html},
            "version": {"number": base_version + 1},
        }
        page = self._rest.request("PUT", f"/wiki/api/v2/pages/{page_ref}", body=body)
        return self._ref(page)

    def get_page(self, *, page_ref: str) -> DocPage:
        page = self._rest.request(
            "GET", f"/wiki/api/v2/pages/{page_ref}", query={"body-format": "storage"}
        )
        body_html = ((page.get("body") or {}).get("storage") or {}).get("value", "")
        return DocPage(
            id=str(page["id"]), title=page.get("title", ""), body_html=body_html,
            version=int((page.get("version") or {}).get("number", 1)),
            url=self._web_url(page),
        )

    def delete_page(self, *, page_ref: str) -> None:
        """Not part of the DocStore capability; used for test cleanup."""
        self._rest.request("DELETE", f"/wiki/api/v2/pages/{page_ref}")

    def search(self, *, query: str, space: str | None = None) -> list[DocHit]:
        # Empty query => list all pages in the space (used for brownfield discovery).
        clauses = []
        if space:
            clauses.append(f'space="{space}"')
        clauses.append("type=page")
        if query:
            clauses.append(f'title ~ "{query}"')
        cql = " and ".join(clauses)
        data = self._rest.request("GET", "/wiki/rest/api/search", query={"cql": cql, "limit": 100})
        hits: list[DocHit] = []
        for entry in (data or {}).get("results", []):
            content = entry.get("content") or {}
            rel = entry.get("url", "")
            hits.append(DocHit(
                id=str(content.get("id", "")),
                title=entry.get("title", content.get("title", "")),
                url=f"{self._cfg.site_url}/wiki{rel}" if rel else self._cfg.site_url,
            ))
        return hits
