"""Companion-side interactive clarification (req #2).

`ask_human` is the agent's question channel. When the agent calls it, we open a
Clarification on the platform and then **poll until a human answers it in the web app**,
returning the answers as the tool result so the agent continues in the same session.

The crucial property: while this is running the **model is idle** on the open tool call —
it generates no tokens — so a clarification that waits minutes (or hours) costs nothing. The
HTTP transport and the sleep are injectable so the flow is unit-testable without a network
or a real wait. Pure stdlib, like the rest of the companion.

Because the wait is free, it is also **patient about failure**. A poll that fails for a
reason expected to clear — a 5xx from the platform, a dropped connection — is not an answer
about the clarification, so it must not end the wait. Run fad927a2 (requirements) lost its
whole phase to a single `500 OperationalError` on one poll: the clarification had
been created and was sitting in the web app waiting to be answered, but the loop had already
raised, the agent was unblocked with no answers, and — obeying Rule 1 — it registered nothing
and closed with a status message instead of the spec. Only genuinely terminal outcomes
(cancelled, 404, an auth rejection) end the wait early.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable


class ClarificationError(Exception):
    """A clarification call failed, was cancelled, or timed out."""


class TransientClarificationError(ClarificationError):
    """A clarification call failed for a reason expected to clear on its own — a 5xx from
    the platform, a refused/reset connection, a timeout.

    Subclasses `ClarificationError` on purpose: callers that already catch the base class
    keep working unchanged, and still see a plain `ClarificationError` if the wait loop
    exhausts its patience and gives up for real.
    """


#: Statuses worth retrying. Everything else (401/403/404/409/…) is the platform stating
#: something about the clarification itself, which the next poll would only restate.
_TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

#: How long a run of consecutive transient failures may last before the wait gives up.
#: Generous because waiting is free and the human on the other end is real: a blip costs
#: nothing to ride out, whereas ending the wait strands a clarification that is already
#: on screen. Reset by any successful poll.
DEFAULT_TRANSIENT_GRACE = 900.0


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

    def _call(self, method: str, url: str, body: dict | None):
        """Run the transport, classifying connection-level failures as transient.

        `_urllib_transport` turns an HTTPError into a `(status, payload)` pair, but a
        refused connection, a reset, or a timeout arrives as `OSError` (`URLError`'s base)
        and used to escape straight through `poll` — killing the wait by a second path that
        the `status >= 400` check never saw.
        """
        try:
            return self._transport(method, url, self._headers(), body)
        except OSError as exc:
            raise TransientClarificationError(f"{method} {url} -> {exc}") from exc

    @staticmethod
    def _raise_for_status(status: int, data, what: str) -> None:
        if status in _TRANSIENT_STATUSES:
            raise TransientClarificationError(f"{what} -> {status}: {data}")
        if status >= 400:
            raise ClarificationError(f"{what} -> {status}: {data}")

    def create(self, *, run_id: str, questions: list, context: str = "",
               phase: str = "", signature: str = "") -> dict:
        url = f"{self._base}/api/runner/clarifications/"
        body = {"run_id": run_id, "questions": questions, "context": context,
                "phase": phase, "signature": signature}
        status, data = self._call("POST", url, body)
        self._raise_for_status(status, data, "create clarification")
        return data or {}

    def poll(self, clarification_id: str) -> dict:
        url = f"{self._base}/api/runner/clarifications/{clarification_id}/"
        status, data = self._call("GET", url, None)
        self._raise_for_status(status, data, "poll clarification")
        return data or {}


def _note(message: str) -> None:
    """Surface a retry in the companion's own log — a silent retry is how a long outage
    looks identical to a hung run."""
    print(f"[companion] {message}", file=sys.stderr, flush=True)


def ask_human(
    client: ClarificationClient, *, run_id: str, questions: list, context: str = "",
    phase: str = "", signature: str = "", poll_interval: float = 3.0,
    timeout: float | None = None, transient_grace: float = DEFAULT_TRANSIENT_GRACE,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Open a clarification and block until it is answered, returning the answers dict.

    The agent's model is idle while we poll, so no cost accrues during the wait. If the
    clarification is already answered (idempotent re-ask / crash recovery) we return at once.
    A cancelled clarification or an exceeded `timeout` raises `ClarificationError`.

    Platform blips are ridden out rather than raised: a transient failure (5xx, dropped
    connection) is retried at the same cadence as a normal poll, and only gives up after
    `transient_grace` seconds of *consecutive* failure. Any successful poll resets that.
    The retry cadence deliberately matches `poll_interval` — the loop is already polling at
    that rate while pending, so riding out an outage adds no load the platform wasn't
    already seeing.
    """
    # Record every invocation. Diagnosing run 75adb0ec — where the agent emitted two ask_human
    # calls in one turn — rested entirely on two database timestamps a second apart, because
    # nothing anywhere logged the calls themselves. A double-ask is agent behaviour, so it will
    # recur; this is the line that will name it next time instead of leaving it to inference.
    _note(f"ask_human run={run_id} phase={phase or '-'} "
          f"questions={len(questions or [])} ids={[q.get('id') for q in (questions or [])]}")
    outage = 0.0
    while True:
        try:
            created = client.create(run_id=run_id, questions=questions, context=context,
                                    phase=phase, signature=signature)
            break
        except TransientClarificationError as exc:
            outage += poll_interval
            if outage > transient_grace:
                raise ClarificationError(
                    f"could not open a clarification for run {run_id} — the platform was "
                    f"unreachable for over {transient_grace:.0f}s: {exc}"
                ) from exc
            _note(f"clarification create failed ({exc}); retrying")
            sleep(poll_interval)

    clarification_id = created["id"]
    if created.get("status") == "answered":
        # The platform deduped onto an already-answered clarification, so the human is spared a
        # repeat and we return their earlier answers straight away. Worth a line: from the
        # agent's side this is indistinguishable from an instant reply, and it is exactly what
        # a double-ask or a re-dispatch looks like when the safety net works.
        _note(f"ask_human answered from an existing clarification {clarification_id} "
              f"(re-ask deduped) — returning the answers already given")
        return created.get("answers") or {}

    waited = 0.0
    outage = 0.0
    while True:
        sleep(poll_interval)          # model idle here — zero token cost
        try:
            state = client.poll(clarification_id)
        except TransientClarificationError as exc:
            # Not an answer about the clarification — the question is still on screen and a
            # human may be answering it right now. Keep the wait alive; ending it here is
            # what cost run fad927a2 its phase.
            outage += poll_interval
            if outage > transient_grace:
                raise ClarificationError(
                    f"clarification {clarification_id} was unreachable for over "
                    f"{transient_grace:.0f}s: {exc}"
                ) from exc
            _note(f"clarification poll failed ({exc}); still waiting for an answer")
            waited += poll_interval
            if timeout is not None and waited >= timeout:
                raise ClarificationError(
                    f"clarification {clarification_id} not answered within {timeout}s"
                ) from exc
            continue
        outage = 0.0                  # reachable again — the grace window starts over
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
