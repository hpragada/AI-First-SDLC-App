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
def get_source_extraction(source_document_id: str, start: int = 0) -> dict:
    """Read the text already extracted from an uploaded document, straight from the document
    itself. Use this when your work item names a SOURCE DOCUMENT rather than an artifact — the
    document has no artifact until your run registers one, so `get_artifact_body` has nothing to
    read. Your transcription must preserve this text and add what the pages hold.

    Paginated: a long document arrives in pieces. Call again with
    `get_source_extraction(id, start=<next_start>)` until `next_start` is null, and concatenate —
    otherwise you are transcribing from only the first part of the document."""
    return tools.get_source_extraction(_tenant(), source_document_id, start)


@server.tool()
def get_page_images(artifact_id: str, start: int = 0) -> list:
    """SEE the original uploaded pages of a document as images — the diagrams, screenshots,
    wireframes, scanned pages and tables-as-pictures the extracted markdown can't carry. Accepts
    either a SOURCE DOCUMENT id or an artifact id, whichever your work item names. Returns a
    one-line text summary then the page images as viewable image blocks. Paginated: a few pages
    per call; the summary gives a `next_start`, so call get_page_images(id, start=<next_start>)
    until it is the last batch. Read the images, then transcribe what you see into faithful
    text."""
    import base64

    from mcp.server.fastmcp import Image as McpImage

    res = tools.get_page_images(_tenant(), artifact_id, start) or {}
    images = res.get("images") or []
    total = res.get("total", 0)
    nxt = res.get("next_start")
    summary = (
        f"{res.get('returned', len(images))} of {total} page image(s) for artifact "
        f"{artifact_id}, starting at index {res.get('start', start)}. "
        + (f"Call get_page_images(artifact_id, start={nxt}) for the next batch."
           if nxt is not None else "This is the last batch.")
    )
    blocks: list = [summary]
    for im in images:
        try:
            raw = base64.b64decode(im.get("data_base64") or "")
        except Exception:  # noqa: BLE001 — skip one unreadable image, keep the rest
            continue
        if raw:
            blocks.append(McpImage(data=raw, format=(im.get("mime") or "image/png").split("/")[-1]))
    return blocks


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
    supersedes: str | None = None,
) -> dict:
    """Register a generated artifact (pointer/provenance only, never the body). You do NOT
    need to know or ask for the project id or run id — the platform fills them from the run
    this phase is executing under (Bugs.xlsx row 25). Only pass them to override (rare).

    ALWAYS pass a `title`: a short, human-readable, context-carrying name for THIS artifact that
    a person can tell apart from its siblings — e.g. "Wireframe — Login Page", "ADR-003 — Event
    Sourcing", "TC-014 — Login rejects a bad password". A bare type ("wireframe") is NOT enough
    when a phase produces several of the same type; the title is what every UI surface displays
    and how the platform distinguishes per-item artifacts (Bugs S.No 120).

    Pass `supersedes=<artifact id>` when this registration is the NEXT VERSION of an artifact
    that already exists (e.g. a faithful re-transcription of an adopted document). The platform
    then takes `phase`, `type` and `title` from that artifact, so the new row versions it
    correctly — you do not have to restate them, and a mistyped title cannot fork a duplicate."""
    resolved_project = project_id or _bound_project()
    resolved_run = run_id or _bound_run()
    if not resolved_project:
        raise RuntimeError("project_id not provided and no PLATFORM_PROJECT_ID bound.")
    return tools.register_artifact(
        _tenant(), resolved_project, resolved_run, phase, type, sor,
        content_hash, s3_key, external_ref, repo_id, title, supersedes,
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
    """Record a traceability link FROM one artifact TO another. Direction matters: `from` is the
    artifact you just produced, `to` is what it came from or acts upon.

    `rel` must be exactly one of four values — there are no others:

    - **derives** — `from` was derived/synthesised from `to`. The right choice for any analysis,
      report or summary pointing at its source (e.g. a dependency graph derived from a code
      intelligence index). If you are unsure, this is almost always the one.
    - **implements** — `from` is code or design that fulfils the specification in `to`.
    - **tests** — `from` is a test covering `to`.
    - **deploys** — `from` is a deployment artifact shipping `to`.

    Passing anything else is rejected as a caller error and changes nothing."""
    return tools.add_trace_edge(_tenant(), from_artifact_id, to_artifact_id, rel)


@server.tool()
def get_a11y_batch() -> dict:
    """The accessibility elements THIS run must judge, one screen at a time. Each element
    carries a short `id` — echo that exact id back to `record_a11y_finding`. Call this first:
    it is the only list of what you are being asked to judge."""
    return tools.get_a11y_batch(_tenant(), _bound_run())


@server.tool()
def get_a11y_screenshots(start: int = 0) -> list:
    """SEE the elements you are judging — a picture of each element in this run's batch, as
    viewable image blocks labelled with the element `id`. Call this before judging anything
    visual: `color` asks what a thing looks like, and `alt` often does too. Paginated; the
    summary gives a `next_start` and names any element that has no captured image."""
    import base64

    from mcp.server.fastmcp import Image as McpImage

    res = tools.get_a11y_screenshots(_tenant(), _bound_run(), start) or {}
    images = res.get("images") or []
    unseen = res.get("unseen") or []
    nxt = res.get("next_start")
    summary = (
        f"{res.get('returned', len(images))} of {res.get('total', 0)} element image(s), "
        f"starting at index {res.get('start', start)}. "
        + (f"Call get_a11y_screenshots(start={nxt}) for the next batch."
           if nxt is not None else "This is the last batch.")
        + (f" {len(unseen)} element(s) have no captured image: "
           f"{', '.join(u.get('id', '') for u in unseen[:12])}." if unseen else "")
    )
    blocks: list = [summary]
    for im in images:
        try:
            raw = base64.b64decode(im.get("data_base64") or "")
        except Exception:  # noqa: BLE001 — skip one unreadable image, keep the rest
            continue
        if raw:
            blocks.append(f"element {im.get('name')}:")
            blocks.append(McpImage(data=raw, format=(im.get("mime") or "image/png").split("/")[-1]))
    return blocks


@server.tool()
def get_wcag_grounding(criteria: list[str]) -> dict:
    """The exact WCAG 2.2 wording for these success criteria, with the glossary definitions
    they depend on. Judge against THIS text, not your recollection of the standard."""
    return tools.get_wcag_grounding(_tenant(), criteria)


@server.tool()
def record_a11y_finding(
    element_id: str,
    criteria: list[str],
    verdict: str,
    confidence: float,
    evidence: str,
    suggested_fix: str = "",
) -> dict:
    """Record your verdict for ONE element. `verdict` is pass | fail | uncertain, `confidence`
    is 0-1, `criteria` lists every criterion this element actually breaches (a div-as-button
    breaches 1.3.1 AND 4.1.2), and `evidence` quotes what led you there. Call it exactly once
    per element in the batch — an element you never report on is recorded as unjudged and
    fails the run."""
    return tools.record_a11y_finding(
        _tenant(), element_id, criteria, verdict, confidence, evidence,
        suggested_fix=suggested_fix, run_id=_bound_run(),
    )


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
    project_id: str, phase: str | None = None, status: str | None = None,
    type: str | None = None,
) -> list[dict]:
    return tools.list_artifacts(_tenant(), _resolve_project(project_id), phase, status, type)


@server.tool()
def detect_drift(artifact_id: str) -> dict:
    return tools.detect_drift(_tenant(), artifact_id)


def main() -> None:
    server.run()  # stdio transport by default


if __name__ == "__main__":
    main()
