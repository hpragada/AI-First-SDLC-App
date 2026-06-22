"""Platform-State MCP server (spec §2) — server name `platform-state`, stdio transport.

The ONLY way agents read/write platform state. The tenant is bound from the launch
context (`PLATFORM_TENANT_ID`, set by the ClaudeDriver per run) — agents never pass a
tenant, so they cannot reach another tenant's rows. Tool signatures mirror spec §2.
"""
import os

from mcp.server.fastmcp import FastMCP

from mcp_platform_state.bootstrap import setup_django

setup_django()

from mcp_platform_state import tools  # noqa: E402  (after Django is configured)

server = FastMCP("platform-state")


def _tenant() -> str:
    tenant_id = os.environ.get("PLATFORM_TENANT_ID")
    if not tenant_id:
        raise RuntimeError("PLATFORM_TENANT_ID is not set; cannot scope platform state.")
    return tenant_id


@server.tool()
def get_context(project_id: str, phase: str, work_item_id: str | None = None) -> dict:
    return tools.get_context(_tenant(), project_id, phase, work_item_id)


@server.tool()
def register_artifact(
    project_id: str,
    run_id: str,
    phase: str,
    type: str,
    sor: str,
    content_hash: str,
    s3_key: str | None = None,
    external_ref: dict | None = None,
    repo_id: str | None = None,
) -> dict:
    return tools.register_artifact(
        _tenant(), project_id, run_id, phase, type, sor,
        content_hash, s3_key, external_ref, repo_id,
    )


@server.tool()
def update_artifact(
    artifact_id: str,
    status: str | None = None,
    sor: str | None = None,
    external_ref: dict | None = None,
    content_hash: str | None = None,
    version: int | None = None,
) -> dict:
    return tools.update_artifact(
        _tenant(), artifact_id, status, sor, external_ref, content_hash, version
    )


@server.tool()
def add_trace_edge(from_artifact_id: str, to_artifact_id: str, rel: str) -> dict:
    return tools.add_trace_edge(_tenant(), from_artifact_id, to_artifact_id, rel)


@server.tool()
def log_event(
    actor: str, action: str, target_type: str,
    target_id: str | None = None, payload: dict | None = None,
) -> dict:
    return tools.log_event(_tenant(), actor, action, target_type, target_id, payload)


@server.tool()
def list_work_items(project_id: str, state: str | None = None) -> list[dict]:
    return tools.list_work_items(_tenant(), project_id, state)


@server.tool()
def transition_work_item(work_item_id: str, to_state: str) -> dict:
    return tools.transition_work_item(_tenant(), work_item_id, to_state)


@server.tool()
def get_artifact(artifact_id: str) -> dict:
    return tools.get_artifact(_tenant(), artifact_id)


@server.tool()
def list_artifacts(
    project_id: str, phase: str | None = None, status: str | None = None
) -> list[dict]:
    return tools.list_artifacts(_tenant(), project_id, phase, status)


@server.tool()
def detect_drift(artifact_id: str) -> dict:
    return tools.detect_drift(_tenant(), artifact_id)


def main() -> None:
    server.run()  # stdio transport by default


if __name__ == "__main__":
    main()
