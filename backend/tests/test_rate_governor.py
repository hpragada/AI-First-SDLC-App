"""P1 — Rate governor v1 (spec §7 / PG18).

The governor wraps the connector transport (the single network choke point) with a
per-(tenant, capability) token bucket, 429/5xx backoff, and a short-TTL read cache.
Time/sleep/randomness are injected so the policy is tested without real waits or network.
"""
import pytest

from apps.integrations.models import IntegrationConnection
from apps.tenancy.models import Tenant
from integrations.rate_governor import (
    GovernorConfig,
    RateGovernor,
    get_governor,
    governed_transport,
    reset_governors,
)
from integrations.registry import get_capability


class FakeClock:
    """Monotonic clock whose `sleep` advances time instead of blocking."""

    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, d):
        self.t += d


def _governor(clock, *, rand=lambda: 1.0, **cfg):
    base = dict(rate=1000.0, capacity=1000.0, base_delay=1.0, max_delay=8.0,
                max_attempts=5, cache_ttl=5.0)
    base.update(cfg)
    return RateGovernor(
        "t1", "docstore", GovernorConfig(**base),
        now=clock.now, sleep=clock.sleep, rand=rand,
    )


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_governors()
    yield
    reset_governors()


# ── token bucket ────────────────────────────────────────────────────
def test_token_bucket_serializes_bursts():
    clock = FakeClock()
    gov = _governor(clock, rate=1.0, capacity=2.0, cache_ttl=0.0)
    times = []

    def base(method, url, headers, body):
        times.append(clock.now())
        return 200, None

    transport = gov.wrap(base)
    for _ in range(4):
        transport("POST", "/x", {}, None)  # POST => not cached, isolates the bucket

    # Capacity 2 lets the first two through at t=0; then one token/sec.
    assert times == [0.0, 0.0, 1.0, 2.0]


# ── backoff / retry ─────────────────────────────────────────────────
def test_retries_on_429_then_succeeds():
    clock = FakeClock()
    gov = _governor(clock)
    seq = [429, 429, 200]
    calls = {"n": 0}

    def base(method, url, headers, body):
        status = seq[calls["n"]]
        calls["n"] += 1
        return status, {"ok": status == 200}

    status, data = gov.wrap(base)("POST", "/x", {}, None)
    assert status == 200 and calls["n"] == 3
    # full-jitter delays (rand=1.0): base*2^0 + base*2^1 = 1 + 2 = 3s slept.
    assert clock.t == 3.0


def test_retries_on_5xx():
    clock = FakeClock()
    gov = _governor(clock)
    seq = [503, 200]
    calls = {"n": 0}

    def base(method, url, headers, body):
        status = seq[calls["n"]]
        calls["n"] += 1
        return status, None

    status, _ = gov.wrap(base)("POST", "/x", {}, None)
    assert status == 200 and calls["n"] == 2


def test_gives_up_after_max_attempts_and_surfaces_last():
    clock = FakeClock()
    gov = _governor(clock, max_attempts=3)
    calls = {"n": 0}

    def base(method, url, headers, body):
        calls["n"] += 1
        return 503, {"err": "down"}

    status, data = gov.wrap(base)("POST", "/x", {}, None)
    assert status == 503 and calls["n"] == 3  # exactly max_attempts network calls
    assert data == {"err": "down"}            # last response surfaced (connector raises)


@pytest.mark.parametrize("status", [400, 401, 404])
def test_does_not_retry_4xx(status):
    clock = FakeClock()
    gov = _governor(clock)
    calls = {"n": 0}

    def base(method, url, headers, body):
        calls["n"] += 1
        return status, None

    got, _ = gov.wrap(base)("POST", "/x", {}, None)
    assert got == status and calls["n"] == 1  # client errors are not retryable


def test_backoff_delay_is_capped():
    clock = FakeClock()
    gov = _governor(clock, base_delay=1.0, max_delay=3.0, max_attempts=6)
    calls = {"n": 0}

    def base(method, url, headers, body):
        calls["n"] += 1
        return 429 if calls["n"] < 5 else 200, None

    gov.wrap(base)("POST", "/x", {}, None)
    # delays: 1, 2, min(4,3)=3, min(8,3)=3 → 9s; cap holds beyond max_delay.
    assert clock.t == 9.0


# ── read cache ──────────────────────────────────────────────────────
def test_read_cache_collapses_safe_reads():
    clock = FakeClock()
    gov = _governor(clock)
    calls = {"n": 0}

    def base(method, url, headers, body):
        calls["n"] += 1
        return 200, {"v": calls["n"]}

    transport = gov.wrap(base)
    a = transport("GET", "/page/1", {}, None)
    b = transport("GET", "/page/1", {}, None)
    assert a == b == (200, {"v": 1}) and calls["n"] == 1  # served from cache


def test_cache_keys_on_request_and_skips_writes():
    clock = FakeClock()
    gov = _governor(clock)
    calls = {"n": 0}

    def base(method, url, headers, body):
        calls["n"] += 1
        return 200, None

    transport = gov.wrap(base)
    transport("GET", "/page/1", {}, None)
    transport("GET", "/page/2", {}, None)   # different url → miss
    transport("POST", "/page/1", {}, None)  # writes are never cached
    transport("POST", "/page/1", {}, None)
    assert calls["n"] == 4


def test_cache_expires_after_ttl():
    clock = FakeClock()
    gov = _governor(clock, cache_ttl=5.0)
    calls = {"n": 0}

    def base(method, url, headers, body):
        calls["n"] += 1
        return 200, None

    transport = gov.wrap(base)
    transport("GET", "/page/1", {}, None)
    clock.t += 6.0  # past the TTL
    transport("GET", "/page/1", {}, None)
    assert calls["n"] == 2


def test_errors_are_not_cached():
    clock = FakeClock()
    gov = _governor(clock)
    seq = [404, 200]
    calls = {"n": 0}

    def base(method, url, headers, body):
        status = seq[calls["n"]]
        calls["n"] += 1
        return status, None

    transport = gov.wrap(base)
    assert transport("GET", "/page/1", {}, None)[0] == 404
    assert transport("GET", "/page/1", {}, None)[0] == 200  # not served from cache
    assert calls["n"] == 2


def test_cache_disabled_when_ttl_zero():
    clock = FakeClock()
    gov = _governor(clock, cache_ttl=0.0)
    calls = {"n": 0}

    def base(method, url, headers, body):
        calls["n"] += 1
        return 200, None

    transport = gov.wrap(base)
    transport("GET", "/page/1", {}, None)
    transport("GET", "/page/1", {}, None)
    assert calls["n"] == 2


# ── registry: one governor per (tenant, capability) ─────────────────
def test_governor_is_shared_per_tenant_capability():
    g1 = get_governor("tenant-a", "docstore")
    g2 = get_governor("tenant-a", "docstore")
    g3 = get_governor("tenant-a", "tasktracker")
    g4 = get_governor("tenant-b", "docstore")
    assert g1 is g2          # same bucket/cache reused across connector instances
    assert g1 is not g3 and g1 is not g4


def test_governed_transport_wraps_an_explicit_base():
    calls = {"n": 0}

    def base(method, url, headers, body):
        calls["n"] += 1
        return 200, None

    transport = governed_transport("t", "docstore", base=base)
    transport("GET", "/x", {}, None)
    transport("GET", "/x", {}, None)  # cached
    assert calls["n"] == 1


# ── wiring: connectors built via get_capability are governed ────────
def test_get_capability_injects_governed_transport(db, monkeypatch):
    calls = []

    def base(method, url, headers, body):
        calls.append((method, url))
        return 200, {"results": []}

    monkeypatch.setattr("integrations.transport.default_transport", base)
    tenant = Tenant.objects.create(name="Acme")
    IntegrationConnection.objects.create(
        tenant=tenant, capability="docstore", connector="confluence",
        scopes={"space_key": "SDLC"}, token_ref="settings:atlassian",
    )
    ds = get_capability(tenant.id, "docstore")
    ds.search(query="", space="SDLC")
    ds.search(query="", space="SDLC")  # identical read → governed cache collapses it
    assert len(calls) == 1
