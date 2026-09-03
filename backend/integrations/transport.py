"""Connector-neutral HTTP transport (the single network choke point).

Every connector (Atlassian, GitHub, …) funnels its requests through a `Transport`
callable so it's unit-testable without the network and so the **Rate governor** can wrap
one place per `(tenant, capability)`. The default uses urllib; connectors never build
their own sockets.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable

# transport(method, url, headers, body) -> (status, parsed_json | bytes | None)
Transport = Callable[[str, str, dict, object | None], "tuple[int, object]"]


def _parse(raw: bytes):
    """JSON when it is JSON, raw bytes when it is not.

    Every REST call this transport carries returns JSON, so that stays the fast path. Binary
    responses became necessary once a connector had to DOWNLOAD something rather than describe it
    (Confluence attachments — the images a page's diagrams live in). Falling back to bytes is
    strictly additive: anything that parsed as JSON before still parses as JSON, and a payload
    that never could (a PNG) now arrives intact instead of raising inside the transport."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return raw


def urllib_transport(method: str, url: str, headers: dict, body: object | None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, _parse(resp.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        parsed = _parse(raw)
        if isinstance(parsed, bytes):
            parsed = raw.decode("utf-8", "replace")
        return exc.code, parsed


# The default network path the rate governor wraps before it reaches a connector.
default_transport: Transport = urllib_transport
