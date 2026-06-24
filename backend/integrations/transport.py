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

# transport(method, url, headers, body) -> (status, parsed_json_or_None)
Transport = Callable[[str, str, dict, object | None], "tuple[int, object]"]


def urllib_transport(method: str, url: str, headers: dict, body: object | None):
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


# The default network path the rate governor wraps before it reaches a connector.
default_transport: Transport = urllib_transport
