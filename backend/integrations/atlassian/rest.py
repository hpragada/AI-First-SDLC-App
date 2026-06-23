"""Thin REST transport for Atlassian Cloud (Confluence + Jira share auth/host).

The transport is injectable so connectors are unit-testable without the network; the
default uses urllib. (The Phase-1 rate governor will later wrap this single choke
point — connectors never build their own sockets.)
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

from integrations.types import CapabilityError

from .config import AtlassianConfig

# transport(method, url, headers, body) -> (status, parsed_json_or_None)
Transport = Callable[[str, str, dict, object | None], "tuple[int, object]"]


def _urllib_transport(method: str, url: str, headers: dict, body: object | None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = raw.decode("utf-8", "replace")
        return exc.code, parsed


class AtlassianRest:
    """Authenticated JSON client. `path` is relative to the site root."""

    def __init__(self, config: AtlassianConfig, transport: Transport | None = None):
        self._cfg = config
        self._transport = transport or _urllib_transport

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
