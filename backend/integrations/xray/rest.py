"""Authenticated JSON client for the Xray Cloud API.

Two-step auth: POST the client_id/client_secret to `/api/v2/authenticate`, which returns a
bearer token (a bare JSON string); subsequent calls carry it as `Authorization: Bearer`.
The token is cached and refreshed once on a 401. Shares the connector-neutral `Transport`
(so the rate governor wraps it) and raises the vendor-free `CapabilityError` on >=400.
"""
from __future__ import annotations

import urllib.parse

from integrations.transport import Transport, default_transport
from integrations.types import CapabilityError

from .config import XrayConfig


class XrayRest:
    def __init__(self, config: XrayConfig, transport: Transport | None = None):
        self._cfg = config
        self._transport = transport or default_transport
        self._token: str | None = None

    def _authenticate(self) -> str:
        status, data = self._transport(
            "POST", f"{self._cfg.api_url}/api/v2/authenticate",
            {"Content-Type": "application/json", "Accept": "application/json",
             "User-Agent": "sdlc-platform"},
            {"client_id": self._cfg.client_id, "client_secret": self._cfg.client_secret},
        )
        if status >= 400:
            raise CapabilityError(
                f"Xray authenticate -> {status}", status=status, detail=data
            )
        # Xray returns the token as a bare JSON string; tolerate a dict for forward-compat.
        return data if isinstance(data, str) else (data or {}).get("token", "")

    def request(self, method: str, path: str, *, body: object | None = None,
                query: dict | None = None, _retry: bool = True) -> object:
        if self._token is None:
            self._token = self._authenticate()
        url = self._cfg.api_url + path
        if query:
            clean = {k: v for k, v in query.items() if v is not None}
            url += "?" + urllib.parse.urlencode(clean)
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "User-Agent": "sdlc-platform",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        status, data = self._transport(method, url, headers, body)
        if status == 401 and _retry:                 # token expired — re-auth once
            self._token = self._authenticate()
            return self.request(method, path, body=body, query=query, _retry=False)
        if status >= 400:
            raise CapabilityError(
                f"Xray {method} {path} -> {status}", status=status, detail=data
            )
        return data
