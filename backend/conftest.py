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
    monkeypatch.setattr(_gate_svc, "_default_signal_sender", lambda *a, **kw: None)
