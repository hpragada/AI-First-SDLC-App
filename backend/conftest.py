"""Pytest bootstrap: put the repo root on sys.path so tests can import the
sibling `mcp_platform_state` package (the Platform-State MCP server)."""
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture(autouse=True)
def _noop_gate_signal_sender(monkeypatch):
    """Bypass real Temporal signal in every test.

    decide_gate() defaults to _default_signal_sender which connects to
    a live Temporal cluster. In CI there is no cluster, so we swap it
    for a no-op so gate decision tests run without Temporal.
    The signal pathway itself is covered by orchestration-level tests.
    """
    import apps.gates.services as _gate_svc
    _REAL["gate_signal"] = _REAL.get("gate_signal") or _gate_svc._default_signal_sender
    monkeypatch.setattr(_gate_svc, "_default_signal_sender", lambda *a, **kw: None)


#: The real functions the autouse no-ops above replace, captured before the first swap.
_REAL: dict = {}


@pytest.fixture
def real_gate_signal(_noop_gate_signal_sender, monkeypatch):
    """OPT-IN: a gate decision really signals its workflow.

    For tests that drive a real workflow on a LOCAL Temporal and approve a gate through
    `decide_gate`. Without it the autouse no-op swallows the approval and the workflow waits for
    ever — which is what every such test did whenever a local Temporal was up (they skip when it
    is not, which is how it went unnoticed). Use it only where the test has pointed
    `settings.TEMPORAL_HOST` at the local server; never against the shared one in `.env`."""
    import apps.gates.services as _gate_svc
    monkeypatch.setattr(_gate_svc, "_default_signal_sender", _REAL["gate_signal"])


@pytest.fixture(autouse=True)
def object_store(monkeypatch):
    """Give every test an IN-MEMORY object store, so no test can reach real storage.

    `s3_from_settings()` is not a local stub. With `S3_ENDPOINT_URL` empty — which `.env` leaves it,
    and which settings documents as meaning "PROD/cloud -> AWS S3" — it builds a LIVE AWS S3 client
    from the credentials in `.env` and writes to the team's own bucket. The MinIO container that was
    meant to serve local work has been stopped since early September 2026, so until this fixture
    existed, every test that staged an artifact body put real objects into shared storage, failed
    intermittently on `EndpointConnectionError` when AWS was slow, and ran roughly three times
    slower for the round trip.

    The seam is `S3ObjectStore` itself rather than `s3_from_settings`, deliberately: most callers
    import `s3_from_settings` lazily inside a function, but `orchestration/activities.py` binds it
    at module level, so patching the factory would miss that one. Everything funnels through the
    class, which `s3_from_settings` looks up in its own module at call time.

    The same instance is returned every time, because a test that stages a body in one call and
    reads it back in another is relying on one store, which is how real storage behaves.

    Request it by name (`def test_x(object_store)`) to stage a body. A test that genuinely needs to
    talk to real storage does not belong in this suite — that is the team's own pass against the
    shared server.
    """
    from storage import InMemoryObjectStore
    from storage import object_store as _store_module

    fake = InMemoryObjectStore()
    monkeypatch.setattr(_store_module, "S3ObjectStore", lambda **kwargs: fake)
    return fake
