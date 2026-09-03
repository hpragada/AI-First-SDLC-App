"""Thin REST transport for Atlassian Cloud (Confluence + Jira share auth/host).

The transport is injectable so connectors are unit-testable without the network and so
the rate governor can wrap one choke point per (tenant, capability). The generic urllib
transport now lives in `integrations.transport` (shared with the GitHub connector);
re-exported here so existing imports (`from .rest import Transport`) keep working.
"""
from __future__ import annotations

import urllib.parse

from integrations.transport import Transport, default_transport
from integrations.types import CapabilityError

from .config import AtlassianConfig

__all__ = ["AtlassianRest", "Transport", "default_transport"]


class AtlassianRest:
    """Authenticated JSON client. `path` is relative to the site root."""

    def __init__(self, config: AtlassianConfig, transport: Transport | None = None):
        self._cfg = config
        self._transport = transport or default_transport

    def request(self, method: str, path: str, *, body: object | None = None,
                query: dict | None = None) -> object:
        url = self._cfg.site_url + path
        if query:
            clean = {k: v for k, v in query.items() if v is not None}
            url += "?" + urllib.parse.urlencode(clean)
        headers = {
            "Authorization": self._cfg.basic_auth_header(),
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        status, data = self._transport(method, url, headers, body)
        if status >= 400:
            raise CapabilityError(
                f"Atlassian {method} {path} -> {status}", status=status, detail=data
            )
        return data
