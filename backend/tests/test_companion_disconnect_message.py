"""Pressing Disconnect must end the companion with a sentence, not a Python traceback.

Reported live 2026-10-05: the team revoked an enrollment from Connect Machine and the companion
died with

    runner.companion.daemon.DaemonError: claim work -> 401: {'detail': 'invalid or missing
    Runner token'}

under a full stack trace. Two faults in one: a deliberate, requested outcome presented as a
crash, and a message naming an HTTP verb, a status code and a server field while never saying
"reconnect the machine". These tests pin both halves.

Pure unit tests — the transport is injected, so no network.
"""
import pytest
from runner.companion import __main__ as cli
from runner.companion.daemon import DaemonError, RunnerRejectedError

from .test_companion_daemon import _claude_on_path, _daemon, _Transport  # noqa: F401

# The words a person must never be shown. Deliberately includes the exact fragments from the
# reported traceback, so this test fails if that wording ever comes back.
MACHINE_WORDS = [
    "401", "http", "traceback", "claim work", "runner token", "detail",
    "daemonerror", "exception", "status", "raise", "none",
]


def _rejecting_transport():
    """Everything answers 401, as it does the moment an enrollment is revoked."""
    def transport(method, url, headers, body):
        return 401, {"detail": "invalid or missing Runner token"}
    return transport


def test_a_revoked_token_is_not_an_ordinary_failure():
    d = _daemon(_rejecting_transport(), None)
    with pytest.raises(RunnerRejectedError):
        d.claim()


def test_the_daemon_stops_rather_than_retrying_a_revoked_token():
    """It must STOP. Reconnecting issues a NEW token this process can never pick up, so a
    daemon that waited would look alive while being permanently useless."""
    d = _daemon(_rejecting_transport(), None)
    with pytest.raises(RunnerRejectedError):
        d.serve(max_iterations=50)


def test_other_four_hundreds_still_behave_as_before():
    """Only 401 changes meaning. A different rejection is still an unexpected problem and
    keeps its detail, which is the useful part when nobody asked for it."""
    def transport(method, url, headers, body):
        return 422, {"detail": "nope"}
    d = _daemon(transport, None)
    with pytest.raises(DaemonError) as exc:
        d.claim()
    assert not isinstance(exc.value, RunnerRejectedError)


def test_the_ending_is_three_plain_sentences_and_exit_two(monkeypatch, capsys, tmp_path):
    """The whole point of the bug report: what the developer actually reads."""
    monkeypatch.setattr(cli, "_assert_engine_env", lambda: None)

    from runner.companion import daemon as daemon_mod
    monkeypatch.setattr(
        daemon_mod.CompanionDaemon, "serve",
        lambda self, **kw: (_ for _ in ()).throw(RunnerRejectedError("x")))

    code = cli.main([
        "serve", "--api-url", "http://platform", "--tenant", "t1", "--token", "tok",
        "--worktrees", str(tmp_path),
    ])

    assert code == 2, "a companion that stopped must not report success"
    err = capsys.readouterr().err
    assert "disconnected in the SDLC app" in err
    assert "Connect Machine" in err
    assert "Stopping." in err
    assert "Traceback" not in err

    # Only the lines about the ending are judged; the startup engine-log line is not ours.
    ending = "\n".join(ln for ln in err.splitlines() if "Stopping" in ln
                       or "disconnected" in ln or "Connect Machine" in ln).lower()
    for word in MACHINE_WORDS:
        assert word not in ending, f"the ending says {word!r} to a person"


def test_an_unexpected_problem_still_ends_on_one_line_not_a_traceback(
        monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "_assert_engine_env", lambda: None)
    from runner.companion import daemon as daemon_mod
    monkeypatch.setattr(
        daemon_mod.CompanionDaemon, "serve",
        lambda self, **kw: (_ for _ in ()).throw(DaemonError("the disk filled up")))

    code = cli.main([
        "serve", "--api-url", "http://platform", "--tenant", "t1", "--token", "tok",
        "--worktrees", str(tmp_path),
    ])
    err = capsys.readouterr().err
    assert code == 2
    assert "the disk filled up" in err   # unexpected ⇒ the detail IS the useful part
    assert "Traceback" not in err
