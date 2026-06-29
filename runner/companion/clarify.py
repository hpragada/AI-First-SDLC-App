"""Companion-side interactive clarification (req #2).

`ask_human` is the agent's question channel. When the agent calls it, we open a
Clarification on the platform and then **poll until a human answers it in the web app**,
returning the answers as the tool result so the agent continues in the same session.

The crucial property: while this is running the **model is idle** on the open tool call —
it generates no tokens — so a clarification that waits minutes (or hours) costs nothing. The
HTTP transport and the sleep are injectable so the flow is unit-testable without a network
or a real wait. Pure stdlib, like the rest of the companion.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable


class ClarificationError(Exception):
    """A clarification call failed, was cancelled, or timed out."""


def _urllib_transport(method: str, url: str, headers: dict, body: dict | None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
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


class ClarificationClient:
    """Talks to the platform's runner-clarification endpoints with the enrollment token.
    `transport(method, url, headers, body) -> (status, parsed)` is injectable for tests."""

    def __init__(self, *, api_url: str, tenant_id: str, token: str,
                 transport: Callable[..., tuple[int, object]] | None = None):
        self._base = api_url.rstrip("/")
        self._tenant = tenant_id
        self._token = token
        self._transport = transport or _urllib_transport

    def _headers(self) -> dict:
        return {
            "Authorization": f"Runner {self._token}",
            "X-Tenant-ID": self._tenant,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def create(self, *, run_id: str, questions: list, context: str = "",
               phase: str = "", signature: str = "") -> dict:
        url = f"{self._base}/api/runner/clarifications/"
        body = {"run_id": run_id, "questions": questions, "context": context,
                "phase": phase, "signature": signature}
        status, data = self._transport("POST", url, self._headers(), body)
        if status >= 400:
            raise ClarificationError(f"create clarification -> {status}: {data}")
        return data or {}

    def poll(self, clarification_id: str) -> dict:
        url = f"{self._base}/api/runner/clarifications/{clarification_id}/"
        status, data = self._transport("GET", url, self._headers(), None)
        if status >= 400:
            raise ClarificationError(f"poll clarification -> {status}: {data}")
        return data or {}


def ask_human(
    client: ClarificationClient, *, run_id: str, questions: list, context: str = "",
    phase: str = "", signature: str = "", poll_interval: float = 3.0,
    timeout: float | None = None, sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Open a clarification and block until it is answered, returning the answers dict.

    The agent's model is idle while we poll, so no cost accrues during the wait. If the
    clarification is already answered (idempotent re-ask / crash recovery) we return at once.
    A cancelled clarification or an exceeded `timeout` raises `ClarificationError`."""
    created = client.create(run_id=run_id, questions=questions, context=context,
                            phase=phase, signature=signature)
    clarification_id = created["id"]
    if created.get("status") == "answered":
        return created.get("answers") or {}

    waited = 0.0
    while True:
        sleep(poll_interval)          # model idle here — zero token cost
        state = client.poll(clarification_id)
        status = state.get("status")
        if status == "answered":
            return state.get("answers") or {}
        if status == "cancelled":
            raise ClarificationError(f"clarification {clarification_id} was cancelled")
        waited += poll_interval
        if timeout is not None and waited >= timeout:
            raise ClarificationError(
                f"clarification {clarification_id} not answered within {timeout}s"
            )
