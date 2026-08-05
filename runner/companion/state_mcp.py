"""Companion-side Platform-State MCP server (Phase-2 §3).

Same `platform-state` tool names the agent already knows, but each tool **proxies to the
platform over HTTP** (via `RemoteStateClient`) instead of touching a DB. Launched by the
build driver on the dev machine; the tenant + RLS scoping live on the platform, resolved
from the enrollment token the client carries. Exposes only the build-phase tool subset.
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from runner.companion.clarify import ClarificationClient
from runner.companion.clarify import ask_human as _ask_human
from runner.companion.state_client import RemoteStateClient


def build_server(
    client: RemoteStateClient,
    *,
    clarify_client: ClarificationClient | None = None,
    run_id: str = "",
    phase: str = "",
    project_id: str = "",
) -> FastMCP:
    server = FastMCP("platform-state")
    # Launch-bound identifiers the agent never has to supply (see register_artifact).
    project_id_bound = project_id
    run_id_bound = run_id
    phase_bound = phase

    @server.tool()
    def get_context(project_id: str, phase: str, work_item_id: str | None = None) -> dict:
        # Prefer the launch-bound project UUID: agents often pass the project *name* from the
        # manifest, which is not a valid id (backend 500). The platform knows the real one.
        return client.call("get_context", project_id=project_id_bound or project_id,
                           phase=phase, work_item_id=work_item_id)

    @server.tool()
    def get_artifact(artifact_id: str) -> dict:
        return client.call("get_artifact", artifact_id=artifact_id)

    @server.tool()
    def get_artifact_body(artifact_id: str, state: str | None = None) -> dict:
        """Read the actual BODY of an artifact (get_artifact returns pointers only). For a
        multi-state wireframe, pass `state` (e.g. "state-1-default") for one document; omit it
        to get the default body plus `available_states` to fetch the rest one call at a time."""
        return client.call("get_artifact_body", artifact_id=artifact_id, state=state)

    @server.tool()
    def list_artifacts(project_id: str, phase: str | None = None,
                       status: str | None = None, type: str | None = None) -> list:
        """List artifact pointers, optionally filtered. Pass `type` to fetch a specific upstream
        input accurately — e.g. list_artifacts(type="architecture") → get_artifact_body(id) —
        when it isn't already in your manifest's # Relevant Artifacts (Bugs S.No 191)."""
        return client.call("list_artifacts", project_id=project_id_bound or project_id,
                           phase=phase, status=status, type=type)

    @server.tool()
    def stage_artifact_body(filename: str, body: str, content_type: str = "text/html",
                            phase: str | None = None) -> dict:
        """Persist a large DRAFT artifact body (e.g. one self-contained HTML wireframe state)
        to the object store; returns its pointer (`s3_key`, `content_hash`, `bytes`). Stage
        each big document here, then reference the returned `s3_key` from `register_artifact`
        — `register_artifact` never carries a body. project/run/phase are filled from this
        run.

        **One body per artifact — never batch.** Call this once for EACH artifact you are
        about to register, so every artifact owns its own `s3_key` (filenames `tc-001`,
        `tc-002`, … — not one `tc-001-023` holding 23 test cases). Bodies are what the UI
        previews and what the SoR export parses, so several artifacts sharing one body means
        every one of them shows — and exports as — the wrong content. Registering a
        `test_case` whose body another test case in this run already claimed is rejected."""
        return client.call("stage_artifact_body", project_id=project_id_bound,
                           run_id=run_id_bound, phase=phase or phase_bound,
                           filename=filename, body=body, content_type=content_type)

    @server.tool()
    def register_artifact(type: str, sor: str, content_hash: str,
                          title: str = "",
                          phase: str | None = None,
                          project_id: str | None = None, run_id: str | None = None,
                          s3_key: str | None = None,
                          external_ref: dict | None = None, repo_id: str | None = None) -> dict:
        """Register a generated artifact (pointer/provenance only, never the body). You do NOT
        need to know or ask for the project id or run id — the platform fills them in from the
        run this phase is executing under (Bugs.xlsx row 25). Only pass project_id/run_id to
        override the current run (rare).

        ALWAYS pass a `title`: a short, human-readable, context-carrying name for THIS artifact
        that a person can tell apart from its siblings — e.g. "Wireframe — Login Page",
        "TC-014 — Login rejects a bad password". A bare type is not enough when a phase produces
        several of the same type; the title is what every UI surface shows (Bugs S.No 120)."""
        return client.call("register_artifact",
                           project_id=project_id or project_id_bound,
                           run_id=run_id or run_id_bound,
                           phase=phase or phase_bound,
                           type=type, sor=sor, content_hash=content_hash, title=title,
                           s3_key=s3_key, external_ref=external_ref, repo_id=repo_id)

    @server.tool()
    def update_artifact(artifact_id: str, status: str | None = None, sor: str | None = None,
                        external_ref: dict | None = None, content_hash: str | None = None,
                        version: int | None = None, title: str | None = None) -> dict:
        return client.call("update_artifact", artifact_id=artifact_id, status=status, sor=sor,
                           external_ref=external_ref, content_hash=content_hash, version=version,
                           title=title)

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
                         depends_on: list | None = None, repo_id: str | None = None,
                         assignment_rationale: str = "", assignment_confidence: str = "") -> dict:
        """Multi-repo (Option C): pass `repo_id` to assign the work item to one of the project's
        repositories (from get_context `repositories`), plus a short `assignment_rationale` and
        `assignment_confidence` (high|low) — the reviewer confirms/overrides these at the gate."""
        return client.call("create_work_item", project_id=project_id, type=type, title=title,
                           description=description, parent_id=parent_id,
                           feature_stream=feature_stream, depends_on=depends_on,
                           repo_id=repo_id, assignment_rationale=assignment_rationale,
                           assignment_confidence=assignment_confidence)

    @server.tool()
    def transition_work_item(work_item_id: str, to_state: str) -> dict:
        return client.call("transition_work_item", work_item_id=work_item_id, to_state=to_state)

    @server.tool()
    def ask_human(questions: list, context: str = "") -> dict:
        """Ask the human one or more questions and BLOCK until they answer in the web app,
        then continue. Use this whenever you are missing information you need to proceed (a
        context gap, a decision between options, a pre-gate confirmation) — do NOT guess.
        While you wait, no cost is incurred. Each question: {id, text, kind: "text"|"choice"
        |"confirm", options?: [...], required?: bool, tier?: 1|2|3, suggestion?: <answer>}.
        Returns answers keyed by question id.

        Call this AT MOST ONCE per message. Never emit two `ask_human` calls in the same turn:
        the second queues behind the first and fires the moment the human answers the first,
        re-asking them minutes later. More questions go in the SAME call, not a second one.
        `id` must be a stable slug naming the gap (e.g. "leave_entitlements"); if you ever ask
        again, reuse the same id verbatim — that is how the platform recognises a re-ask and
        hands you the answer already given instead of troubling the human twice.

        Front-load ALL three tiers in ONE call (see `# Rules`): `tier: 1` = must-ask, keep it
        `required: true` with NO `suggestion`; `tier: 2`/`3` = set `required: false` and put
        your proposed answer in `suggestion` (for kind="choice", `suggestion` must be one of
        `options`). The human confirms/edits/overrides; any Tier-2/3 item left untouched falls
        back to your `suggestion`, so you always get a concrete value back.

        Authoring rules — the reader is a busy human, not an engineer (Bugs S.No 60):
        - `text` is ONE short, plain-language question in sentence case. No preamble dumps,
          no ALL-CAPS, no "CONTEXT GAP CHECK 1. ..." headers.
        - For kind="choice", put EVERY choice in `options` ONLY. Never also list the choices
          inside `text` (e.g. "... a) Free b) Freemium c) B2C") — the UI already renders the
          options as a picker, so inlining them shows each choice twice and reads as clutter.
        - Keep each option short. To let the user type a free-form answer, add an option that
          begins with the word "Other" (e.g. "Other (please specify)") — the UI reveals a
          text box for it; do NOT write "Other: ___" inside `text`.
        - `context` (separate arg) is where any short "why I'm asking" background goes."""
        if clarify_client is None:
            raise RuntimeError("ask_human is not configured (no clarification client)")
        return _ask_human(clarify_client, run_id=run_id, questions=questions,
                          context=context, phase=phase)

    return server


def _client_from_env() -> RemoteStateClient:
    return RemoteStateClient(
        api_url=os.environ["RUNNER_API_URL"],
        tenant_id=os.environ["RUNNER_TENANT_ID"],
        token=os.environ["RUNNER_TOKEN"],
    )


def _clarify_client_from_env() -> ClarificationClient:
    return ClarificationClient(
        api_url=os.environ["RUNNER_API_URL"],
        tenant_id=os.environ["RUNNER_TENANT_ID"],
        token=os.environ["RUNNER_TOKEN"],
    )


def main() -> None:
    # run_id/phase/project identify the run this launch is bound to (the agent never passes
    # them — artifact registration fills project_id/run_id from here, Bugs.xlsx row 25).
    build_server(
        _client_from_env(),
        clarify_client=_clarify_client_from_env(),
        run_id=os.environ.get("RUNNER_RUN_ID", ""),
        phase=os.environ.get("RUNNER_PHASE", ""),
        project_id=os.environ.get("RUNNER_PROJECT_ID", ""),
    ).run()  # stdio transport


if __name__ == "__main__":
    main()
