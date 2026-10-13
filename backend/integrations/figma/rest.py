"""Authenticated JSON client for the Figma REST API.

Shares the connector-neutral `Transport` (so the rate governor wraps it) and raises the
vendor-free `CapabilityError` on >=400, exactly like the GitHub/Atlassian clients. Figma
authenticates a PAT with the `X-Figma-Token` header.
"""
from __future__ import annotations

import urllib.parse

from integrations.transport import Transport, default_transport
from integrations.types import CapabilityError

from .config import FigmaConfig


class FigmaRest:
    """`path` is relative to the API root (e.g. `/v1/files/{file_key}`)."""

    def __init__(self, config: FigmaConfig, transport: Transport | None = None):
        self._cfg = config
        self._transport = transport or default_transport

    def request(self, method: str, path: str, *, body: object | None = None,
                query: dict | None = None) -> object:
        url = self._cfg.api_url + path
        if query:
            clean = {k: v for k, v in query.items() if v is not None}
            url += "?" + urllib.parse.urlencode(clean)
        headers = {
            "X-Figma-Token": self._cfg.token,
            "Accept": "application/json",
            "User-Agent": "sdlc-platform",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        status, data = self._transport(method, url, headers, body)
        if status >= 400:
            raise CapabilityError(
                f"Figma {method} {path} -> {status}", status=status, detail=data
            )
        return data
