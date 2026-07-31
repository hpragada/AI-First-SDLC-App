"""Companion CodeIntel MCP server (agent-driven onboarding) — tool surface + construction.

The live `index()` path needs the `git` binary (exercised end-to-end on the companion); here we
verify the module imports, exposes the index + 8-tool surface the agent bodies expect, and
constructs a server bound to a given workspace + repo without touching the filesystem."""
from runner.companion.codeintel_mcp import CODEINTEL_TOOL_NAMES, build_server


def test_tool_names_cover_index_plus_eight_surface():
    assert CODEINTEL_TOOL_NAMES[0] == "index"
    for name in ("get_overview", "get_context", "get_risk", "get_why", "search_codebase",
                 "get_dependency_path", "get_dead_code", "get_architecture_diagram"):
        assert name in CODEINTEL_TOOL_NAMES
    # `index_report` joins the surface (B5): the agent must be able to ask what the index could
    # NOT see, since a healthy file count survives a git read that failed completely.
    assert "index_report" in CODEINTEL_TOOL_NAMES
    assert len(CODEINTEL_TOOL_NAMES) == 10


def test_build_server_constructs_bound_to_workspace_and_repo(tmp_path):
    # No git needed to construct; index() (which shells out to git) is exercised live.
    server = build_server(workspace=str(tmp_path), repo="acme/api")
    assert server is not None
