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
