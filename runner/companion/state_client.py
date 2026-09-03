"""Remote Platform-State client (companion side).

Calls the platform's `/api/runner/state/<tool>/` endpoints with the enrollment token. The
companion never holds DB credentials and never sends a tenant in the body — the platform
derives the tenant from the authenticated enrollment (#6). Pure stdlib so the companion
stays lightweight; the HTTP transport is injectable for tests.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable


class RemoteStateError(Exception):
    """A remote platform-state call failed."""


def _urllib_post(url: str, headers: dict, body: dict) -> tuple[int, object]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        raw = exc.read()
        try:
            return exc.code, (json.loads(raw) if raw else None)
        except ValueError:
            return exc.code, raw.decode("utf-8", "replace")


class RemoteStateClient:
    # transport(url, headers, body) -> (status, parsed)
    def __init__(self, *, api_url: str, tenant_id: str, token: str,
                 transport: Callable[[str, dict, dict], tuple[int, object]] | None = None):
        self._base = api_url.rstrip("/")
        self._tenant = tenant_id
        self._token = token
        self._transport = transport or _urllib_post

    def call(self, tool: str, **kwargs):
        url = f"{self._base}/api/runner/state/{tool}/"
        headers = {
            "Authorization": f"Runner {self._token}",
            "X-Tenant-ID": self._tenant,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        status, data = self._transport(url, headers, kwargs)
        if status >= 400:
            raise RemoteStateError(f"{tool} -> {status}: {data}")
        return (data or {}).get("result")
