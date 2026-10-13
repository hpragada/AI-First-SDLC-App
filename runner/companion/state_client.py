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


#: How long an ordinary platform call may take. Every tool here is a read or a single small
#: write, so a minute is already generous and a call still going after it is a real problem.
DEFAULT_TIMEOUT_S = 60.0

#: …and how long a call is allowed to take when the platform's own work behind it is the slow
#: part. **Not a tuning knob — the 60-second default caused a real failure** (31 Aug).
#:
#: `finish_a11y_audit` does the whole close synchronously: reconcile the route list, hash every
#: captured element, check each against the judgment cache, file what cannot be asked about and
#: start the judging run. On a 94-route audit holding 2,171 elements that is minutes, not
#: seconds. The socket gave up at 60; the server carried on regardless; the daemon read the
#: timeout as the audit having failed and ran its recovery close — so one audit was closed
#: twice, and the second close wrote off 1,065 elements that were being judged at that moment.
#:
#: The platform side is now safe to call twice (`apps.a11y.baseline.finish_baseline_audit`
#: returns a repeat untouched), so this is the second of two independent fixes rather than the
#: only one. It is here because a client that times out on a call whose documented job takes
#: minutes is wrong on its own terms, and would go on reporting healthy audits as failures.
SLOW_TIMEOUT_S = 900.0


def _urllib_post(url: str, headers: dict, body: dict,
                 timeout: float = DEFAULT_TIMEOUT_S) -> tuple[int, object]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        raw = exc.read()
        try:
            return exc.code, (json.loads(raw) if raw else None)
        except ValueError:
            return exc.code, raw.decode("utf-8", "replace")


class RemoteStateClient:
    # transport(url, headers, body, timeout) -> (status, parsed)
    def __init__(self, *, api_url: str, tenant_id: str, token: str,
                 transport: Callable[..., tuple[int, object]] | None = None):
        self._base = api_url.rstrip("/")
        self._tenant = tenant_id
        self._token = token
        self._transport = transport or _urllib_post

    def call(self, tool: str, _timeout: float = DEFAULT_TIMEOUT_S, **kwargs):
        """Call one platform-state tool.

        `_timeout` is underscored because everything else in `**kwargs` is forwarded to the tool
        as an argument: a plain `timeout=` would be indistinguishable from a tool that one day
        takes a `timeout` of its own, and would silently stop being sent. It is how long to wait
        for the platform, never something the platform is told.
        """
        url = f"{self._base}/api/runner/state/{tool}/"
        headers = {
            "Authorization": f"Runner {self._token}",
            "X-Tenant-ID": self._tenant,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        status, data = self._transport(url, headers, kwargs, _timeout)
        if status >= 400:
            raise RemoteStateError(f"{tool} -> {status}: {data}")
        return (data or {}).get("result")
