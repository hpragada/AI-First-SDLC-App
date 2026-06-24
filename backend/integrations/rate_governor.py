"""Rate governor v1 (spec §7 / PG18) — the single choke point all connector I/O
routes through.

It wraps the `Transport` callable (the only network path; see `atlassian/rest.py`) with
three protections, keyed per `(tenant, capability)`:

1. **Token bucket** — serialize bursts at a configurable refill rate so one tenant can't
   hammer a SoR (or trip its rate limits).
2. **Backoff/retry** — on 429/5xx, jittered exponential backoff up to a max-attempts cap,
   then surface the last response so the connector raises as before.
3. **Short-TTL read cache** — idempotent reads (safe HTTP methods: GET/HEAD) are cached
   by `(tenant, capability, method, url, body)` for a few seconds, collapsing the read
   amplification of discovery/traceability into a single upstream call.

Connectors never build their own sockets; `registry.get_capability` injects the governed
transport at build time, so this is automatic for every per-tenant connector. Buckets and
caches are process-global and shared per `(tenant, capability)` across connector instances.

All time/sleep/randomness is injectable so the policy is unit-testable without real waits
or the network.
"""
from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

# transport(method, url, headers, body) -> (status, parsed_json_or_None)
Transport = Callable[[str, str, dict, object | None], "tuple[int, object]"]

_SAFE_METHODS = {"GET", "HEAD"}


def _is_retryable(status: int) -> bool:
    return status == 429 or 500 <= status < 600


@dataclass(frozen=True)
class GovernorConfig:
    rate: float = 5.0          # bucket refill, tokens/sec
    capacity: float = 10.0     # burst capacity (tokens)
    max_attempts: int = 5      # total network attempts before giving up
    base_delay: float = 0.5    # backoff base (sec)
    max_delay: float = 8.0     # backoff ceiling per attempt (sec)
    cache_ttl: float = 5.0     # read-cache TTL (sec); 0 disables caching

    @classmethod
    def from_settings(cls) -> GovernorConfig:
        try:
            from django.conf import settings
        except Exception:
            return cls()
        d = cls()
        return cls(
            rate=getattr(settings, "RATE_GOVERNOR_RATE", d.rate),
            capacity=getattr(settings, "RATE_GOVERNOR_CAPACITY", d.capacity),
            max_attempts=getattr(settings, "RATE_GOVERNOR_MAX_ATTEMPTS", d.max_attempts),
            base_delay=getattr(settings, "RATE_GOVERNOR_BASE_DELAY", d.base_delay),
            max_delay=getattr(settings, "RATE_GOVERNOR_MAX_DELAY", d.max_delay),
            cache_ttl=getattr(settings, "RATE_GOVERNOR_CACHE_TTL", d.cache_ttl),
        )


class TokenBucket:
    """Thread-safe token bucket. `acquire` blocks (serializing the bucket) until a token
    has refilled, so concurrent callers on the same `(tenant, capability)` take turns."""

    def __init__(self, rate: float, capacity: float, *,
                 now: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self._rate = rate
        self._capacity = capacity
        self._tokens = capacity
        self._now = now
        self._sleep = sleep
        self._updated = now()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> None:
        with self._lock:
            while True:
                t = self._now()
                self._tokens = min(
                    self._capacity, self._tokens + (t - self._updated) * self._rate
                )
                self._updated = t
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                self._sleep((tokens - self._tokens) / self._rate)


class _TTLCache:
    """Tiny thread-safe TTL cache. Stores `(status, data)` tuples for safe reads only."""

    def __init__(self, ttl: float, *, now: Callable[[], float] = time.monotonic):
        self._ttl = ttl
        self._now = now
        self._data: dict = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires, value = item
            if self._now() >= expires:
                self._data.pop(key, None)
                return None
            return value

    def put(self, key, value) -> None:
        with self._lock:
            self._data[key] = (self._now() + self._ttl, value)


def _body_key(body: object | None) -> str:
    return "" if body is None else repr(body)


class RateGovernor:
    """Bucket + backoff + read cache for one `(tenant, capability)`. `wrap` decorates a
    base transport, returning a transport with the identical signature."""

    def __init__(self, tenant_id, capability: str, config: GovernorConfig | None = None, *,
                 now: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 rand: Callable[[], float] = random.random):
        self._key = (str(tenant_id), capability)
        self._cfg = config or GovernorConfig.from_settings()
        self._sleep = sleep
        self._rand = rand
        self._bucket = TokenBucket(self._cfg.rate, self._cfg.capacity, now=now, sleep=sleep)
        self._cache = _TTLCache(self._cfg.cache_ttl, now=now)

    def wrap(self, base: Transport) -> Transport:
        def transport(method: str, url: str, headers: dict, body: object | None):
            cache_key = None
            if self._cfg.cache_ttl > 0 and method in _SAFE_METHODS:
                cache_key = (self._key, method, url, _body_key(body))
                cached = self._cache.get(cache_key)
                if cached is not None:
                    return cached
            result = self._call_with_backoff(base, method, url, headers, body)
            if cache_key is not None and result[0] < 400:
                self._cache.put(cache_key, result)
            return result

        return transport

    def _call_with_backoff(self, base, method, url, headers, body):
        attempt = 0
        while True:
            self._bucket.acquire()
            status, data = base(method, url, headers, body)
            if not _is_retryable(status):
                return status, data
            attempt += 1
            if attempt >= self._cfg.max_attempts:
                return status, data  # give up — let the connector raise on >=400
            cap = min(self._cfg.max_delay, self._cfg.base_delay * (2 ** (attempt - 1)))
            self._sleep(self._rand() * cap)  # full jitter


# ── process-global registry: one governor per (tenant, capability) ──────
_GOVERNORS: dict[tuple, RateGovernor] = {}
_REG_LOCK = threading.Lock()


def get_governor(tenant_id, capability: str) -> RateGovernor:
    key = (str(tenant_id), capability)
    with _REG_LOCK:
        gov = _GOVERNORS.get(key)
        if gov is None:
            gov = RateGovernor(tenant_id, capability)
            _GOVERNORS[key] = gov
        return gov


def governed_transport(tenant_id, capability: str, base: Transport | None = None) -> Transport:
    """The Transport a connector should use: `base` (default urllib) wrapped with this
    tenant+capability's bucket/backoff/cache. This is the §7 choke point wiring."""
    if base is None:
        from .transport import default_transport

        base = default_transport
    return get_governor(tenant_id, capability).wrap(base)


def reset_governors() -> None:
    """Clear all buckets/caches — for tests and config reloads."""
    with _REG_LOCK:
        _GOVERNORS.clear()
