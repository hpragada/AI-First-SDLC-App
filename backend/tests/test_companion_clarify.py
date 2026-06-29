"""Companion-side `ask_human` flow (req #2): create a clarification, poll until answered,
return the answers — with the model idle (no cost) during the wait. No network, no real
sleep: a fake client drives the state transitions and sleep is a no-op recorder.
"""
import pytest
from runner.companion.clarify import (
    ClarificationClient,
    ClarificationError,
    ask_human,
)


class _FakeClient:
    """Stands in for ClarificationClient. `poll_states` is the sequence of statuses returned
    by successive polls; `create_status` is what create() returns first."""

    def __init__(self, *, poll_states, answers=None, create_status="pending"):
        self._poll_states = list(poll_states)
        self._answers = answers or {"q": "yes"}
        self._create_status = create_status
        self.created = None
        self.polls = 0

    def create(self, *, run_id, questions, context="", phase="", signature=""):
        self.created = {"run_id": run_id, "questions": questions, "phase": phase}
        return {"id": "clar-1", "status": self._create_status, "answers": self._answers}

    def poll(self, clarification_id):
        self.polls += 1
        status = self._poll_states.pop(0)
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
