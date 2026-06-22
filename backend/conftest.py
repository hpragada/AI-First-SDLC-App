"""Pytest bootstrap: put the repo root on sys.path so tests can import the
sibling `mcp_platform_state` package (the Platform-State MCP server)."""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
