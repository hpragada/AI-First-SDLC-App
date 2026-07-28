"""Companion-side CodeIntel MCP server (agent-driven onboarding).

Exposes the built-in code-intelligence engine (git analytics, dependency graph, PageRank
modules, churn×complexity hotspots, dead code, decision archaeology) to a planning agent as
`codeintel.*` tools — the exact 8-tool surface the `00c` / `00_onboarding` agent bodies already
describe. The agent runs inside a THROWAWAY read-only git worktree (its cwd); this server wraps
ONE `BuiltinCodeIntel` bound to that workspace + repo, so the agent just calls `index()` then
the read tools without ever handling a filesystem path or a repo name it can't know.

Pure static analysis over the local clone — no source leaves the machine, no network. Mirrors
`state_mcp.py`'s launch pattern; launched by the daemon only for a `reads_code` planning run.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# The 8-tool surface + index — the names the daemon adds to the planning allowlist.
CODEINTEL_TOOL_NAMES = (
    "index", "get_overview", "get_context", "get_risk", "get_why",
    "search_codebase", "get_dependency_path", "get_dead_code", "get_architecture_diagram",
)


def _ensure_backend_importable() -> None:
    """Put the repo's `backend/` on sys.path so `integrations.codeintel.builtin` resolves in
    this subprocess (the daemon does the same for its own process; this server is separate)."""
    backend = Path(__file__).resolve().parents[2] / "backend"
    if backend.is_dir() and str(backend) not in sys.path:
        sys.path.insert(0, str(backend))


def build_server(*, workspace: str, repo: str) -> FastMCP:
    _ensure_backend_importable()
    from integrations.codeintel.builtin import BuiltinCodeIntel

    server = FastMCP("codeintel")
    engine = BuiltinCodeIntel()
    ws_bound = workspace
    repo_bound = repo

    @server.tool()
    def index(repo: str | None = None) -> dict:
        """Analyse the checked-out repository ONCE — git history, import graph, hotspots, dead
        code, decisions. CALL THIS FIRST; every other tool reads its cached result. Returns a
        summary (file_count, languages, commits, hotspots)."""
        idx = engine.index(workspace=ws_bound, repo=repo or repo_bound)
        return {
            "repo": idx.repo, "indexed_at": idx.indexed_at, "file_count": idx.file_count,
            "languages": idx.languages, "commits": idx.commits, "hotspots": idx.hotspots,
        }

    @server.tool()
    def get_overview(repo: str | None = None) -> dict:
        """Repo shape: file_count, languages, commits, author count, top PageRank modules,
        entry points, community count, and the top hotspots."""
        return engine.get_overview(repo=repo or repo_bound)

    @server.tool()
    def get_context(targets: list, repo: str | None = None) -> dict:
        """Per-file lines/complexity/language/churn/owner/bus-factor for each path in `targets`."""
        return engine.get_context(repo=repo or repo_bound, targets=targets)

    @server.tool()
    def get_risk(targets: list, repo: str | None = None) -> dict:
        """Per-file hotspot score, dependents, co-change partners, and blast radius."""
        return engine.get_risk(repo=repo or repo_bound, targets=targets)

    @server.tool()
    def get_why(query: str = "", repo: str | None = None) -> list:
        """Decision archaeology — ADR markers + commit-message decisions, optionally filtered."""
        return engine.get_why(repo=repo or repo_bound, query=query)

    @server.tool()
    def search_codebase(query: str, repo: str | None = None) -> list:
        """Keyword search over file paths; returns scored matches."""
        return engine.search_codebase(repo=repo or repo_bound, query=query)

    @server.tool()
    def get_dependency_path(frm: str, to: str, repo: str | None = None) -> list:
        """Shortest import path between two files (BFS over the dependency graph)."""
        return engine.get_dependency_path(repo=repo or repo_bound, frm=frm, to=to)

    @server.tool()
    def get_dead_code(repo: str | None = None) -> list:
        """Files with no inbound import edge that are not entry points (low-confidence)."""
        return engine.get_dead_code(repo=repo or repo_bound)

    @server.tool()
    def get_architecture_diagram(module: str | None = None, repo: str | None = None) -> str:
        """A Mermaid `graph TD` of the dependency graph, optionally scoped to a module prefix."""
        return engine.get_architecture_diagram(repo=repo or repo_bound, module=module)

    return server


def main() -> None:
    workspace = os.environ.get("RUNNER_WORKSPACE", ".")
    repo = os.environ.get("RUNNER_REPO", "repo")
    build_server(workspace=workspace, repo=repo).run()  # stdio transport


if __name__ == "__main__":
    main()
