"""Companion-side Platform-State MCP server (Phase-2 §3).

Same `platform-state` tool names the agent already knows, but each tool **proxies to the
platform over HTTP** (via `RemoteStateClient`) instead of touching a DB. Launched by the
build driver on the dev machine; the tenant + RLS scoping live on the platform, resolved
from the enrollment token the client carries. Exposes only the build-phase tool subset.
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from runner.companion.state_client import RemoteStateClient


def build_server(client: RemoteStateClient) -> FastMCP:
    server = FastMCP("platform-state")

    @server.tool()
    def get_context(project_id: str, phase: str, work_item_id: str | None = None) -> dict:
        return client.call("get_context", project_id=project_id, phase=phase,
                           work_item_id=work_item_id)

    @server.tool()
    def get_artifact(artifact_id: str) -> dict:
        return client.call("get_artifact", artifact_id=artifact_id)

    @server.tool()
    def list_artifacts(project_id: str, phase: str | None = None,
                       status: str | None = None) -> list:
        return client.call("list_artifacts", project_id=project_id, phase=phase, status=status)

    @server.tool()
    def register_artifact(project_id: str, run_id: str, phase: str, type: str, sor: str,
                          content_hash: str, s3_key: str | None = None,
                          external_ref: dict | None = None, repo_id: str | None = None) -> dict:
        return client.call("register_artifact", project_id=project_id, run_id=run_id,
                           phase=phase, type=type, sor=sor, content_hash=content_hash,
                           s3_key=s3_key, external_ref=external_ref, repo_id=repo_id)

    @server.tool()
    def update_artifact(artifact_id: str, status: str | None = None, sor: str | None = None,
                        external_ref: dict | None = None, content_hash: str | None = None,
                        version: int | None = None) -> dict:
        return client.call("update_artifact", artifact_id=artifact_id, status=status, sor=sor,
                           external_ref=external_ref, content_hash=content_hash, version=version)

    @server.tool()
    def add_trace_edge(from_artifact_id: str, to_artifact_id: str, rel: str) -> dict:
        return client.call("add_trace_edge", from_artifact_id=from_artifact_id,
                           to_artifact_id=to_artifact_id, rel=rel)

    @server.tool()
    def log_event(actor: str, action: str, target_type: str, target_id: str | None = None,
                  payload: dict | None = None) -> dict:
        return client.call("log_event", actor=actor, action=action, target_type=target_type,
                           target_id=target_id, payload=payload)

    @server.tool()
    def list_work_items(project_id: str, state: str | None = None) -> list:
        return client.call("list_work_items", project_id=project_id, state=state)

    @server.tool()
    def create_work_item(project_id: str, type: str, title: str, description: str = "",
                         parent_id: str | None = None, feature_stream: str = "",
                         depends_on: list | None = None) -> dict:
        return client.call("create_work_item", project_id=project_id, type=type, title=title,
                           description=description, parent_id=parent_id,
                           feature_stream=feature_stream, depends_on=depends_on)

    @server.tool()
    def transition_work_item(work_item_id: str, to_state: str) -> dict:
        return client.call("transition_work_item", work_item_id=work_item_id, to_state=to_state)

    return server


def _client_from_env() -> RemoteStateClient:
    return RemoteStateClient(
        api_url=os.environ["RUNNER_API_URL"],
        tenant_id=os.environ["RUNNER_TENANT_ID"],
        token=os.environ["RUNNER_TOKEN"],
    )


def main() -> None:
    build_server(_client_from_env()).run()  # stdio transport


if __name__ == "__main__":
    main()
