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


# Project / run this launch is bound to (set by the control plane per run). Agents never
# need to supply these — e.g. artifact registration fills them from here rather than asking
# the user for a project id they can't know (Bugs.xlsx row 25).
def _bound_project() -> str | None:
    return os.environ.get("PLATFORM_PROJECT_ID") or None


def _bound_run() -> str | None:
    return os.environ.get("PLATFORM_RUN_ID") or None


def _resolve_project(project_id: str | None) -> str:
    """Agents often pass the project *name* from their manifest (or nothing) — the platform
    knows the real UUID from the launch binding, so prefer it. Only fall back to the agent's
    arg when nothing is bound (e.g. a cross-project read in a tool that supports it)."""
    resolved = _bound_project() or project_id
    if not resolved:
        raise RuntimeError("project_id not provided and no PLATFORM_PROJECT_ID bound.")
    return resolved


@server.tool()
def get_context(project_id: str, phase: str, work_item_id: str | None = None) -> dict:
    return tools.get_context(_tenant(), _resolve_project(project_id), phase, work_item_id)


@server.tool()
def stage_artifact_body(
    filename: str,
    body: str,
    content_type: str = "text/html",
    phase: str = "",
    project_id: str | None = None,
    run_id: str | None = None,
) -> dict:
    """Persist a large DRAFT artifact body (e.g. one self-contained HTML wireframe state) to
    the object store and get back its pointer (`s3_key`, `content_hash`, `bytes`). Stage each
    big document here, then reference the returned `s3_key` from `register_artifact` —
    `register_artifact` never carries a body. project_id/run_id/phase are filled from this
    run; you only pass `filename` + `body`.

    **One body per artifact — never batch.** Call this once for EACH artifact you are about to
    register, so every artifact owns its own `s3_key` (filenames `tc-001`, `tc-002`, … — not
    one `tc-001-023` holding 23 test cases). Bodies are what the UI previews and what the SoR
    export parses, so several artifacts sharing one body means every one of them shows — and
    exports as — the wrong content. Registering a `test_case` whose body another test case in
    this run already claimed is rejected."""
    return tools.stage_artifact_body(
        _tenant(), project_id or _bound_project(), run_id or _bound_run(),
        phase, filename, body, content_type,
    )


@server.tool()
def get_artifact_body(artifact_id: str, state: str | None = None) -> dict:
    """Read the actual BODY of an artifact (get_artifact returns pointers only). For a
    multi-state wireframe, pass `state` (e.g. "state-1-default") to fetch one document; omit
    it to get the default body plus `available_states` to fetch the rest one call at a time."""
    return tools.get_artifact_body(_tenant(), artifact_id, state)


@server.tool()
def register_artifact(
    phase: str,
    type: str,
    sor: str,
    content_hash: str,
    title: str = "",
    project_id: str | None = None,
    run_id: str | None = None,
    s3_key: str | None = None,
    external_ref: dict | None = None,
    repo_id: str | None = None,
) -> dict:
    """Register a generated artifact (pointer/provenance only, never the body). You do NOT
    need to know or ask for the project id or run id — the platform fills them from the run
    this phase is executing under (Bugs.xlsx row 25). Only pass them to override (rare).

    ALWAYS pass a `title`: a short, human-readable, context-carrying name for THIS artifact that
    a person can tell apart from its siblings — e.g. "Wireframe — Login Page", "ADR-003 — Event
    Sourcing", "TC-014 — Login rejects a bad password". A bare type ("wireframe") is NOT enough
    when a phase produces several of the same type; the title is what every UI surface displays
    and how the platform distinguishes per-item artifacts (Bugs S.No 120)."""
    resolved_project = project_id or _bound_project()
    resolved_run = run_id or _bound_run()
    if not resolved_project:
        raise RuntimeError("project_id not provided and no PLATFORM_PROJECT_ID bound.")
    return tools.register_artifact(
        _tenant(), resolved_project, resolved_run, phase, type, sor,
        content_hash, s3_key, external_ref, repo_id, title,
    )


@server.tool()
def update_artifact(
    artifact_id: str,
    status: str | None = None,
    sor: str | None = None,
    external_ref: dict | None = None,
    content_hash: str | None = None,
    version: int | None = None,
    title: str | None = None,
) -> dict:
    return tools.update_artifact(
        _tenant(), artifact_id, status, sor, external_ref, content_hash, version, title
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
def create_work_item(
    project_id: str,
    type: str,
    title: str,
    description: str = "",
    parent_id: str | None = None,
    feature_stream: str = "",
    depends_on: list[str] | None = None,
    repo_id: str | None = None,
    assignment_rationale: str = "",
    assignment_confidence: str = "",
) -> dict:
    return tools.create_work_item(
        _tenant(), project_id, type, title, description, parent_id, feature_stream, depends_on,
        repo_id=repo_id, assignment_rationale=assignment_rationale,
        assignment_confidence=assignment_confidence,
    )


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
    return tools.list_artifacts(_tenant(), _resolve_project(project_id), phase, status)


@server.tool()
def detect_drift(artifact_id: str) -> dict:
    return tools.detect_drift(_tenant(), artifact_id)


def main() -> None:
    server.run()  # stdio transport by default


if __name__ == "__main__":
    main()
