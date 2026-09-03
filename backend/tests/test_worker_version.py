"""The worker must know what code it is running, and stand down when it is old.

Background: two workers polled one queue, one of them running older code. The
old one took real work, did less than the current code would, reported success,
and left an audit stranded with no error anywhere. These tests pin the two
halves of the fix — the badge that identifies the running code, and the election
that keeps an older worker off the queue entirely.
"""
from __future__ import annotations

import asyncio
import re

import pytest
from temporalio.service import RPCError, RPCStatusCode

from orchestration import version, worker_election

# ─────────────────────────── the badge ───────────────────────────


def _rpc(status: RPCStatusCode) -> RPCError:
    return RPCError("nope", status, b"")


@pytest.fixture()
def fake_tree(tmp_path, monkeypatch):
    """A small source tree standing in for backend/, so we can edit it."""
    root = tmp_path / "backend"
    (root / "apps").mkdir(parents=True)
    (root / "apps" / "one.py").write_text("print('one')\n", encoding="utf-8")
    (root / "two.py").write_text("print('two')\n", encoding="utf-8")
    monkeypatch.setattr(version, "_source_roots", lambda: [("backend", root)])
    return root


def test_the_badge_names_the_time_and_the_code():
    badge, source = version.build_badge()
    assert re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{12}", badge), badge
    assert source


def test_the_same_code_always_fingerprints_the_same(fake_tree):
    assert version.code_fingerprint() == version.code_fingerprint()


def test_changing_one_line_changes_the_fingerprint(fake_tree):
    before = version.code_fingerprint()
    (fake_tree / "two.py").write_text("print('two!')\n", encoding="utf-8")
    assert version.code_fingerprint() != before


def test_line_endings_do_not_count_as_a_code_change(fake_tree):
    """A Windows checkout and a Linux container must agree on the badge."""
    before = version.code_fingerprint()
    (fake_tree / "two.py").write_bytes(b"print('two')\r\n")
    assert version.code_fingerprint() == before


def test_test_files_do_not_move_the_badge(fake_tree):
    before = version.code_fingerprint()
    (fake_tree / "tests").mkdir()
    (fake_tree / "tests" / "test_thing.py").write_text("assert True\n", encoding="utf-8")
    assert version.code_fingerprint() == before


def test_newer_badges_sort_after_older_ones():
    old = "20260101T000000Z-aaaaaaaaaaaa"
    new = "20260102T000000Z-000000000000"
    assert version.is_newer(new, old)
    assert not version.is_newer(old, new)
    assert not version.is_newer(old, old)


def test_badges_are_compared_on_code_not_on_clocks():
    same = ("20260601T090000Z-abcabcabcabc", "20260601T170000Z-abcabcabcabc")
    different = ("20260601T090000Z-abcabcabcabc", "20260601T090000Z-zzzzzzzzzzzz")
    assert version.same_code(*same)
    assert not version.same_code(*different)


def test_two_builds_stamped_the_same_second_still_get_one_winner():
    """Whatever the tie-break is, both workers must reach the SAME verdict —
    otherwise each thinks it is newer and they take turns evicting each other."""
    a = "20260101T000000Z-aaaaaaaaaaaa"
    b = "20260101T000000Z-bbbbbbbbbbbb"
    assert version.is_newer(b, a) != version.is_newer(a, b)


def test_the_build_stamp_is_used_when_the_image_is_what_is_running(tmp_path, monkeypatch):
    manifest = tmp_path / ".sdlc_build"
    manifest.write_text("20260101T101010Z\ndeadbeefdeadbeef\n", encoding="utf-8")
    monkeypatch.setenv(version._MANIFEST_ENV, str(manifest))
    monkeypatch.setattr(version, "code_fingerprint", lambda: "deadbeefdeadbeef")

    badge, source = version.build_badge()

    assert badge == "20260101T101010Z-deadbeefdead"
    assert "image" in source


def test_the_build_stamp_is_ignored_when_the_mount_overrides_the_image(tmp_path, monkeypatch):
    """compose mounts the repo over /app, so the image stamp would otherwise
    describe code that is not the code being executed."""
    manifest = tmp_path / ".sdlc_build"
    manifest.write_text("20260101T101010Z\nSOMETHINGELSE\n", encoding="utf-8")
    monkeypatch.setenv(version._MANIFEST_ENV, str(manifest))
    monkeypatch.setattr(version, "code_fingerprint", lambda: "deadbeefdeadbeef")

    badge, source = version.build_badge()

    assert not badge.startswith("20260101T101010Z")
    assert "differs from image" in source


# ───────────────────────── the election ─────────────────────────


class FakeSets:
    """Mimics the real SDK object, including how it behaves when empty.

    The real `default_build_id()` raises IndexError on a queue nobody has
    claimed yet — found by running the shipped code against a live server, after
    a friendlier fake had let it through.
    """

    def __init__(self, default):
        self._default = default
        self.version_sets = [] if default is None else [object()]

    def default_build_id(self):
        if not self.version_sets:
            raise IndexError("list index out of range")
        return self._default


class FakeClient:
    def __init__(self, *, default=None, read_error=None, write_error=None):
        self._default = default
        self._read_error = read_error
        self._write_error = write_error
        self.claimed: list[str] = []

    async def get_worker_build_id_compatibility(self, task_queue, **_kw):
        if self._read_error:
            raise self._read_error
        return FakeSets(self._default)

    async def update_worker_build_id_compatibility(self, task_queue, operation, **_kw):
        if self._write_error:
            raise self._write_error
        self.claimed.append(operation.build_id)
        self._default = operation.build_id


def _elect(client, badge="20260601T000000Z-abcabcabcabc"):
    logs: list[str] = []
    election = asyncio.run(
        worker_election.elect(client, "q", badge, log=logs.append)
    )
    return election, logs


def test_an_older_worker_stands_down_and_never_polls():
    """The whole point: old code must not serve the queue at all."""
    client = FakeClient(default="20260801T000000Z-newnewnewnew")

    election, logs = _elect(client, "20260101T000000Z-oldoldoldold")

    assert election.outcome == worker_election.STAND_DOWN
    assert client.claimed == []
    assert "STANDING DOWN" in "\n".join(logs)


def test_a_newer_worker_takes_ownership():
    client = FakeClient(default="20260101T000000Z-oldoldoldold")

    election, _ = _elect(client, "20260801T000000Z-newnewnewnew")

    assert election.outcome == worker_election.VERSIONED
    assert client.claimed == ["20260801T000000Z-newnewnewnew"]


def test_the_first_worker_on_an_unowned_queue_claims_it():
    client = FakeClient(default=None)

    election, _ = _elect(client)

    assert election.outcome == worker_election.VERSIONED
    assert client.claimed == ["20260601T000000Z-abcabcabcabc"]


def test_a_restart_of_the_same_build_does_not_re_register():
    badge = "20260601T000000Z-abcabcabcabc"
    client = FakeClient(default=badge)

    election, _ = _elect(client, badge)

    assert election.outcome == worker_election.VERSIONED
    assert client.claimed == []


def test_two_developers_on_one_commit_both_keep_serving():
    """The runbook has two devs sharing a queue on purpose.

    Their machines date the same files differently, so the same commit produces
    two different badges. Reading that as "newer" would evict a healthy worker
    and quietly halve the team's capacity for no safety gain — identical code is
    the same build, not a later one.
    """
    incumbent = "20260601T090000Z-abcabcabcabc"
    mine_same_code = "20260601T170000Z-abcabcabcabc"   # pulled later, same commit
    client = FakeClient(default=incumbent)

    election, logs = _elect(client, mine_same_code)

    assert election.outcome == worker_election.VERSIONED
    # Polls under the build already serving, so the two share one build ID.
    assert election.build_id == incumbent
    assert client.claimed == []          # nothing re-registered, nobody evicted
    assert "joining it" in "\n".join(logs)


def test_an_older_clock_with_identical_code_is_also_fine():
    """The same case with the clocks the other way round — a dev who pulled
    EARLIER must not stand down either, since the code is the same."""
    incumbent = "20260601T170000Z-abcabcabcabc"
    mine_same_code = "20260601T090000Z-abcabcabcabc"
    client = FakeClient(default=incumbent)

    election, _ = _elect(client, mine_same_code)

    assert election.outcome == worker_election.VERSIONED
    assert election.build_id == incumbent


def test_genuinely_different_code_is_still_kept_off_the_queue():
    """The guard above must not become a way for old code to sneak back on."""
    client = FakeClient(default="20260801T000000Z-newnewnewnew")

    election, _ = _elect(client, "20260101T000000Z-oldoldoldold")

    assert election.outcome == worker_election.STAND_DOWN


@pytest.mark.parametrize(
    "status", [RPCStatusCode.PERMISSION_DENIED, RPCStatusCode.UNIMPLEMENTED]
)
def test_a_server_without_versioning_still_gets_a_working_worker(status):
    """Measured: our Temporal answers PERMISSION_DENIED until two dynamic-config
    flags are set. Shipping this must not take every worker offline until then."""
    client = FakeClient(read_error=_rpc(status))

    election, logs = _elect(client)

    assert election.outcome == worker_election.UNVERSIONED
    assert "workerVersioningDataAPIs" in "\n".join(logs)


def test_versioning_switched_off_between_read_and_write_still_degrades():
    client = FakeClient(default=None, write_error=_rpc(RPCStatusCode.PERMISSION_DENIED))

    election, _ = _elect(client)

    assert election.outcome == worker_election.UNVERSIONED


def test_a_real_server_fault_is_not_mistaken_for_versioning_being_off():
    """UNAVAILABLE means the server is sick, not that the feature is disabled.
    Swallowing it would silently drop the protection whenever Temporal hiccups."""
    client = FakeClient(read_error=_rpc(RPCStatusCode.UNAVAILABLE))

    with pytest.raises(RPCError):
        _elect(client)


# ─────────────────────────── the drain ───────────────────────────


class FakeExecutor:
    def __init__(self, in_flight=0, idle=9999.0):
        self.in_flight = in_flight
        self._idle = idle

    def idle_seconds(self):
        return 0.0 if self.in_flight else self._idle


class StopLoop(Exception):
    pass


def _drain(client, executor, *, badge="20260101T000000Z-oldoldoldold", ticks=5, max_seconds=86400):
    shutdowns: list[int] = []
    logs: list[str] = []
    clock = {"t": 0.0}

    async def on_drained():
        shutdowns.append(1)

    async def sleep(seconds):
        clock["t"] += seconds
        if clock["t"] > ticks * seconds:
            raise StopLoop

    outcome = None
    try:
        outcome = asyncio.run(
            worker_election.drain_when_superseded(
                client, "q", badge,
                executor=executor,
                on_drained=on_drained,
                log=logs.append,
                idle_seconds=300,
                max_seconds=max_seconds,
                poll_seconds=60,
                sleep=sleep,
                now=lambda: clock["t"],
            )
        )
    except StopLoop:
        pass
    return outcome, shutdowns, logs


def test_a_superseded_idle_worker_leaves():
    client = FakeClient(default="20260801T000000Z-newnewnewnew")

    outcome, shutdowns, _ = _drain(client, FakeExecutor(in_flight=0, idle=600))

    assert outcome == "drained"
    assert shutdowns == [1]


def test_a_superseded_worker_holding_work_does_NOT_get_killed():
    """A deploy must not strand the run that is mid-flight — that is the exact
    failure this whole change exists to prevent."""
    client = FakeClient(default="20260801T000000Z-newnewnewnew")

    outcome, shutdowns, logs = _drain(client, FakeExecutor(in_flight=1))

    assert outcome is None
    assert shutdowns == []
    assert "will finish what it is holding" in "\n".join(logs)


def test_the_current_worker_is_left_alone():
    badge = "20260801T000000Z-newnewnewnew"
    client = FakeClient(default=badge)

    outcome, shutdowns, _ = _drain(client, FakeExecutor(in_flight=0, idle=9999), badge=badge)

    assert outcome is None
    assert shutdowns == []


def test_a_worker_that_never_goes_quiet_is_eventually_stopped():
    client = FakeClient(default="20260801T000000Z-newnewnewnew")

    outcome, shutdowns, _ = _drain(
        client, FakeExecutor(in_flight=1), ticks=10, max_seconds=120
    )

    assert outcome == "forced"
    assert shutdowns == [1]


def test_a_temporal_hiccup_during_drain_does_not_kill_the_worker():
    client = FakeClient(read_error=_rpc(RPCStatusCode.UNAVAILABLE))

    outcome, shutdowns, logs = _drain(client, FakeExecutor(in_flight=0, idle=9999))

    assert outcome is None
    assert shutdowns == []
    assert "will retry" in "\n".join(logs)


# ────────────────────── knowing when it is busy ──────────────────────


def test_the_executor_reports_busy_then_idle():
    done = asyncio.Event()

    with worker_election.TrackingExecutor(max_workers=2) as executor:
        started = __import__("threading").Event()

        def work():
            started.set()
            while not done.is_set():
                pass

        future = executor.submit(work)
        started.wait(timeout=5)
        assert executor.in_flight == 1
        assert executor.idle_seconds() == 0.0

        done.set()
        future.result(timeout=5)
        assert executor.in_flight == 0
        assert executor.idle_seconds() >= 0.0
