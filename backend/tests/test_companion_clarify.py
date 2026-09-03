"""Companion-side `ask_human` flow (req #2): create a clarification, poll until answered,
return the answers — with the model idle (no cost) during the wait. No network, no real
sleep: a fake client drives the state transitions and sleep is a no-op recorder.
"""
import pytest
from runner.companion.clarify import (
    ClarificationClient,
    ClarificationError,
    TransientClarificationError,
    ask_human,
)


class _FakeClient:
    """Stands in for ClarificationClient. `poll_states` is the sequence of statuses returned
    by successive polls; `create_status` is what create() returns first.

    A poll state may also be an Exception INSTANCE, which is raised instead of returned —
    that is how the transient-failure paths are driven without a network.
    """

    def __init__(self, *, poll_states, answers=None, create_status="pending",
                 create_raises=None):
        self._poll_states = list(poll_states)
        self._answers = answers or {"q": "yes"}
        self._create_status = create_status
        self._create_raises = list(create_raises or [])
        self.created = None
        self.polls = 0
        self.creates = 0

    def create(self, *, run_id, questions, context="", phase="", signature=""):
        self.creates += 1
        if self._create_raises:
            raise self._create_raises.pop(0)
        self.created = {"run_id": run_id, "questions": questions, "phase": phase}
        return {"id": "clar-1", "status": self._create_status, "answers": self._answers}

    def poll(self, clarification_id):
        self.polls += 1
        status = self._poll_states.pop(0)
        if isinstance(status, Exception):
            raise status
        return {"id": clarification_id, "status": status, "answers": self._answers}


_QS = [{"id": "q", "text": "ok?", "kind": "confirm", "required": True}]


def test_ask_human_returns_answers_after_polling():
    sleeps = []
    client = _FakeClient(poll_states=["pending", "pending", "answered"], answers={"q": "react"})
    out = ask_human(client, run_id="r1", questions=_QS, context="why",
                    poll_interval=3.0, sleep=sleeps.append)
    assert out == {"q": "react"}
    assert client.polls == 3           # polled until answered
    assert sleeps == [3.0, 3.0, 3.0]   # idle between polls (no cost), real wait stubbed
    assert client.created["run_id"] == "r1" and client.created["questions"] == _QS


def test_ask_human_returns_immediately_when_already_answered():
    # Idempotent re-ask / crash recovery: create() already answered -> no polling.
    client = _FakeClient(poll_states=[], answers={"q": "vue"}, create_status="answered")
    out = ask_human(client, run_id="r1", questions=_QS, sleep=lambda _s: None)
    assert out == {"q": "vue"} and client.polls == 0


def test_ask_human_raises_on_cancelled():
    client = _FakeClient(poll_states=["pending", "cancelled"])
    with pytest.raises(ClarificationError):
        ask_human(client, run_id="r1", questions=_QS, sleep=lambda _s: None)


def test_ask_human_times_out():
    client = _FakeClient(poll_states=["pending", "pending", "pending"])
    with pytest.raises(ClarificationError):
        ask_human(client, run_id="r1", questions=_QS, poll_interval=5.0, timeout=10.0,
                  sleep=lambda _s: None)


def test_client_create_and_poll_use_injected_transport():
    calls = []

    def transport(method, url, headers, body):
        calls.append((method, url, body))
        if method == "POST":
            return 201, {"id": "c1", "status": "pending", "answers": {}}
        return 200, {"id": "c1", "status": "answered", "answers": {"q": "x"}}

    client = ClarificationClient(api_url="http://p", tenant_id="t1", token="tok",
                                 transport=transport)
    created = client.create(run_id="r1", questions=_QS)
    assert created["id"] == "c1"
    polled = client.poll("c1")
    assert polled["status"] == "answered"
    assert calls[0][0] == "POST" and calls[0][1].endswith("/api/runner/clarifications/")
    assert calls[1][0] == "GET" and calls[1][1].endswith("/api/runner/clarifications/c1/")


# ── riding out platform blips (run fad927a2) ────────────────────────
# A clarification that is already on screen must survive a transient failure: the wait is
# free, and ending it strands a human mid-answer. Only terminal outcomes stop the wait.


def _client_for(status_code, payload=None):
    def transport(method, url, headers, body):
        return status_code, (payload if payload is not None else {"detail": "x"})
    return ClarificationClient(api_url="http://p", tenant_id="t1", token="tok",
                               transport=transport)


@pytest.mark.parametrize("code", [500, 502, 503, 504, 408, 429])
def test_client_classifies_retryable_statuses_as_transient(code):
    with pytest.raises(TransientClarificationError):
        _client_for(code).poll("c1")


@pytest.mark.parametrize("code", [400, 401, 403, 404, 409])
def test_client_keeps_terminal_statuses_terminal(code):
    with pytest.raises(ClarificationError) as exc:
        _client_for(code).poll("c1")
    assert not isinstance(exc.value, TransientClarificationError)


def test_client_maps_connection_failure_to_transient():
    # A refused/reset connection arrives as OSError, not as a status code — it used to
    # escape poll() entirely and kill the wait by a path the status check never saw.
    def transport(method, url, headers, body):
        raise OSError("connection reset by peer")

    client = ClarificationClient(api_url="http://p", tenant_id="t1", token="tok",
                                 transport=transport)
    with pytest.raises(TransientClarificationError):
        client.poll("c1")


def test_ask_human_survives_transient_poll_failure():
    # The exact shape of run fad927a2: the platform 500s mid-wait, then recovers.
    client = _FakeClient(poll_states=[
        "pending",
        TransientClarificationError("poll clarification -> 500: OperationalError"),
        "pending",
        "answered",
    ], answers={"q": "kept waiting"})
    out = ask_human(client, run_id="r1", questions=_QS, poll_interval=3.0,
                    sleep=lambda _s: None)
    assert out == {"q": "kept waiting"}
    assert client.polls == 4


def test_ask_human_gives_up_after_sustained_outage():
    client = _FakeClient(poll_states=[
        TransientClarificationError("boom") for _ in range(50)
    ])
    with pytest.raises(ClarificationError) as exc:
        ask_human(client, run_id="r1", questions=_QS, poll_interval=3.0,
                  transient_grace=9.0, sleep=lambda _s: None)
    assert "unreachable" in str(exc.value)
    assert client.polls == 4          # 3 within grace, the 4th exceeds it


def test_successful_poll_resets_the_outage_window():
    # 2 failures, a good poll, then 2 more: no run of failures exceeds a 9s grace, so the
    # wait survives even though 4 of 5 polls failed.
    t = TransientClarificationError("blip")
    client = _FakeClient(poll_states=["pending", t, t, "pending", t, t, "answered"])
    out = ask_human(client, run_id="r1", questions=_QS, poll_interval=3.0,
                    transient_grace=9.0, sleep=lambda _s: None)
    assert out == {"q": "yes"}


def test_ask_human_does_not_retry_a_terminal_poll_error():
    client = _FakeClient(poll_states=[ClarificationError("poll clarification -> 404: gone")])
    with pytest.raises(ClarificationError) as exc:
        ask_human(client, run_id="r1", questions=_QS, sleep=lambda _s: None)
    assert "404" in str(exc.value)
    assert client.polls == 1          # failed fast, no retry


def test_ask_human_still_times_out_while_unreachable():
    # A caller-supplied timeout still wins over the transient grace.
    client = _FakeClient(poll_states=[TransientClarificationError("boom")] * 10)
    with pytest.raises(ClarificationError) as exc:
        ask_human(client, run_id="r1", questions=_QS, poll_interval=5.0, timeout=10.0,
                  transient_grace=600.0, sleep=lambda _s: None)
    assert "not answered within" in str(exc.value)


def test_ask_human_retries_a_transient_create():
    client = _FakeClient(poll_states=["answered"],
                         create_raises=[TransientClarificationError("create -> 503")])
    out = ask_human(client, run_id="r1", questions=_QS, poll_interval=3.0,
                    sleep=lambda _s: None)
    assert out == {"q": "yes"}
    assert client.creates == 2        # retried, then succeeded

def test_ask_human_gives_up_on_a_permanently_failing_create():
    client = _FakeClient(poll_states=[],
                         create_raises=[TransientClarificationError("create -> 503")] * 50)
    with pytest.raises(ClarificationError) as exc:
        ask_human(client, run_id="r1", questions=_QS, poll_interval=3.0,
                  transient_grace=9.0, sleep=lambda _s: None)
    assert "could not open a clarification" in str(exc.value)
