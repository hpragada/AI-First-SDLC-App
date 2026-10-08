"""Companion-side Platform-State MCP server (Phase-2 §3).

Same `platform-state` tool names the agent already knows, but each tool **proxies to the
platform over HTTP** (via `RemoteStateClient`) instead of touching a DB. Launched by the
build driver on the dev machine; the tenant + RLS scoping live on the platform, resolved
from the enrollment token the client carries. Exposes only the build-phase tool subset.
"""
from __future__ import annotations

import base64
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp import Image as McpImage

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
    def get_artifact_body(artifact_id: str, state: str | None = None, start: int = 0) -> dict:
        """Read the actual BODY of an artifact (get_artifact returns pointers only). For a
        multi-state wireframe, pass `state` (e.g. "state-1-default") for one document; omit it
        to get the default body plus `available_states` to fetch the rest one call at a time.

        Paginated: when the result's `next_start` is not null, call again with
        `get_artifact_body(artifact_id, start=<next_start>)` and join the pieces, or you are
        working from only the beginning of the document."""
        return client.call("get_artifact_body", artifact_id=artifact_id, state=state,
                           start=start)

    @server.tool()
    def get_pr_file(pr_ref: str, path: str, start: int = 0) -> dict:
        """Read one file from the pull request under review, straight from the repository.

        Use this whenever the inlined diff in your briefing is marked as truncated, or says the
        diff is unavailable. Reviewing only the part of a file that happened to fit, and
        reporting that review as complete, is what this exists to prevent.

        Paginated: when `next_start` is not null, call again with `start=<next_start>`."""
        return client.call("get_pr_file", pr_ref=pr_ref, path=path, start=start)

    @server.tool()
    def get_source_extraction(source_document_id: str, start: int = 0) -> dict:
        """Read the text already extracted from an uploaded document, straight from the document
        itself. Use this when your work item names a SOURCE DOCUMENT rather than an artifact — the
        document has no artifact until your run registers one, so `get_artifact_body` has nothing
        to read. Your transcription must preserve this text and add what the pages hold.

        Paginated: a long document arrives in pieces. Call again with
        `get_source_extraction(id, start=<next_start>)` until `next_start` is null, and
        concatenate — otherwise you are transcribing from only the first part of the document."""
        return client.call("get_source_extraction",
                           source_document_id=source_document_id, start=start)

    @server.tool()
    def get_page_images(artifact_id: str, start: int = 0) -> list:
        """SEE the original uploaded pages of a document artifact as images — the diagrams,
        screenshots, wireframes, scanned pages and tables-as-pictures that the extracted
        markdown (get_artifact_body) can't carry. Returns a one-line text summary followed by
        the page images themselves as viewable image blocks.

        Use this on an onboarding source document whose extraction is image-only, or whose
        diagrams/tables matter for your assessment: read the images, then transcribe what you
        see into faithful text. Paginated — a few pages per call; the summary gives a
        `next_start`, so call get_page_images(artifact_id, start=<next_start>) until it says
        this is the last batch. Downscaled to a sane size already; nothing else to configure."""
        res = client.call("get_page_images", artifact_id=artifact_id, start=start) or {}
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
                fmt = (im.get("mime") or "image/png").split("/")[-1]
                blocks.append(McpImage(data=raw, format=fmt))
        return blocks

    @server.tool()
    def get_a11y_screenshots(start: int = 0) -> list:
        """SEE the elements you are judging. Returns a one-line summary, then a picture of each
        element in this run's batch as a viewable image block, labelled with the element `id`
        you echo back to `record_a11y_finding`.

        Call this before judging anything visual — `color` is a question about what a thing
        looks like, and `alt` often is too. Paginated: a few elements per call; the summary
        gives a `next_start`, so call get_a11y_screenshots(start=<next_start>) until it says
        this is the last batch. Elements with no captured picture are named in the summary —
        for those, judge from the markup or record `uncertain` saying it could not be seen."""
        res = client.call("get_a11y_screenshots",
                          run_id=run_id_bound or None, start=start) or {}
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
                fmt = (im.get("mime") or "image/png").split("/")[-1]
                blocks.append(McpImage(data=raw, format=fmt))
        return blocks

    # ── Accessibility judging (09c, QA-02a) and journeys (09d, QA-20) ──────────────
    #
    # These seven were granted in `runner.BUILD_STATE_TOOLS` and routed in the platform's
    # `_BUILD_STATE_TOOLS`, but never DEFINED here — and this file is the only thing that puts a
    # tool in front of an agent. A name in `allowed_tools` is a permission, not a tool: it cannot
    # conjure one the server never exposed. So both phases were unrunnable from the day they were
    # written. The judge said so in its own words on its first real run — "the three tools this
    # phase depends on are not registered in this session's tool set at all" — and it was right.
    #
    # `run_id` is bound at launch and never asked of the agent, exactly as `register_artifact`
    # and `submit_gap_report` bind it: the agent is told which elements to judge by the platform,
    # so letting it name the run would let it answer for a different one.

    @server.tool()
    def get_a11y_batch(start: int = 0) -> dict:
        """YOUR WORK: the elements this run must judge, ONE SCREEN per call (QA-02a).

        Read `total_elements` on the first call — that is your contract for the WHOLE run, and
        every element in it needs one `record_a11y_finding`. It stays the same on every page;
        it is never the size of the page you are holding.

        Paged so a large audit cannot exceed what you can hold: judge this screen, record its
        verdicts, then call `get_a11y_batch(start=<next_start>)` for the next. Stop when
        `next_start` comes back null. A crowded screen is split across calls —
        `screen.continues` is true when the page you were given has more to come, so do not read
        a partial screen as the whole of it. `screen.index` / `screen.of` say where you are.

        Each element carries the short `id` you echo back; the run is bound at launch, so you
        never name it."""
        return client.call("get_a11y_batch", run_id=run_id_bound or None, start=start)

    @server.tool()
    def get_wcag_grounding(criteria: list[str]) -> dict:
        """THE RULEBOOK: the exact WCAG 2.2 wording for these criteria, plus the glossary terms
        they hinge on. Judge against the standard's own words rather than your recollection of
        them. Collect the distinct `criteria` across your batch and ask once."""
        return client.call("get_wcag_grounding", criteria=criteria)

    @server.tool()
    def record_a11y_finding(element_id: str, criteria: list[str], verdict: str,
                            confidence: float, evidence: str,
                            suggested_fix: str = "") -> dict:
        """YOUR ANSWER: one verdict for one element. Call it per element as you go, never in a
        batch at the end.

        `verdict` is "pass" | "fail" | "uncertain"; `confidence` is 0.0-1.0; `evidence` is what
        you saw. A `fail` must carry `suggested_fix`. The platform validates and rejects with a
        reason you can act on — a rejection is yours to correct, not a reason to stop."""
        return client.call("record_a11y_finding",
                           run_id=run_id_bound or None,
                           project_id=project_id_bound or None,
                           element_id=element_id, criteria=criteria, verdict=verdict,
                           confidence=confidence, evidence=evidence,
                           suggested_fix=suggested_fix)

    @server.tool()
    def get_a11y_journey() -> dict:
        """YOUR CONTRACT: the journey to operate with a keyboard, read once at the start (QA-20).

        `steps` are frozen and their numbering here is what you report against — never the
        numbering printed in the test case body. Check yourself against `total_steps`."""
        return client.call("get_a11y_journey", run_id=run_id_bound or None)

    @server.tool()
    def record_a11y_journey_step(step: int, outcome: str, reason: str = "") -> dict:
        """What became of ONE step: `walked` or `blocked`. Call it for EVERY step, including the
        ones that went fine — the platform cannot tell "I walked it and it was clean" from "I
        never got there" unless you say which. `reason` is what stopped you, on a block."""
        return client.call("record_a11y_journey_step", run_id=run_id_bound or None,
                           step=step, outcome=outcome, reason=reason)

    @server.tool()
    def record_a11y_journey_finding(step: int, checker: str, verdict: str, confidence: float,
                                    evidence: str, criteria: list[str] | None = None,
                                    suggested_fix: str = "", route: str = "",
                                    selector: str = "",
                                    measurement: dict | None = None) -> dict:
        """One check's answer about one step. `checker` is one of the eight from
        `get_a11y_journey().checks`; leave `criteria` unset to use that check's own criterion.

        Leave `selector` out when the finding is about the screen rather than one element —
        focus order is a property of the page, and pinning it to an arbitrary element files the
        problem against something that is not what is wrong."""
        return client.call("record_a11y_journey_finding", run_id=run_id_bound or None,
                           step=step, checker=checker, verdict=verdict, confidence=confidence,
                           evidence=evidence, criteria=criteria, suggested_fix=suggested_fix,
                           route=route, selector=selector, measurement=measurement)

    @server.tool()
    def finish_a11y_journey() -> dict:
        """Close the pass: every frozen step you never reported on is recorded as *not reached*,
        so a journey that walked two of six says so instead of reading as keyboard-clean."""
        return client.call("finish_a11y_journey", run_id=run_id_bound or None)

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
                          external_ref: dict | None = None, repo_id: str | None = None,
                          format: str | None = None) -> dict:
        """Register a generated artifact (pointer/provenance only, never the body). You do NOT
        need to know or ask for the project id or run id — the platform fills them in from the
        run this phase is executing under (Bugs.xlsx row 25). Only pass project_id/run_id to
        override the current run (rare).

        ALWAYS pass a `title`: a short, human-readable, context-carrying name for THIS artifact
        that a person can tell apart from its siblings — e.g. "Wireframe — Login Page",
        "TC-014 — Login rejects a bad password". A bare type is not enough when a phase produces
        several of the same type; the title is what every UI surface shows (Bugs S.No 120).

        Pass `format` when the body you staged is NOT prose — "json", "yaml", "xml" or "csv".
        Without it the platform assumes markdown, which turns a structured document (a
        CycloneDX SBOM, say) into an unreadable wall of text on the preview screen."""
        # Binding FIRST (S.No 313). This read `project_id or project_id_bound`, so an agent's
        # own answer beat the one the platform launched the run with — while
        # stage_artifact_body six lines up already used the binding alone. That asymmetry is
        # how a body came to be staged under the real project and its row registered under a
        # different one. The docstring above has always told the agent it does not need to
        # know these; now it is true.
        return client.call("register_artifact",
                           project_id=project_id_bound or project_id,
                           run_id=run_id_bound or run_id,
                           phase=phase or phase_bound,
                           type=type, sor=sor, content_hash=content_hash, title=title,
                           s3_key=s3_key, external_ref=external_ref, repo_id=repo_id,
                           format=format)

    @server.tool()
    def update_artifact(artifact_id: str, status: str | None = None, sor: str | None = None,
                        external_ref: dict | None = None, content_hash: str | None = None,
                        version: int | None = None, title: str | None = None) -> dict:
        return client.call("update_artifact", artifact_id=artifact_id, status=status, sor=sor,
                           external_ref=external_ref, content_hash=content_hash, version=version,
                           title=title)

    @server.tool()
    def add_trace_edge(from_artifact_id: str, to_artifact_id: str, rel: str) -> dict:
        """Record a traceability link FROM one artifact TO another. Direction matters: `from` is
        the artifact you just produced, `to` is what it came from or acts upon.

        `rel` must be exactly one of four values — there are no others:

        - **derives** — `from` was derived/synthesised from `to`. The right choice for any
          analysis, report or summary pointing at its source (e.g. a dependency graph derived
          from a code-intelligence index). If unsure, this is almost always the one.
        - **implements** — `from` is code or design fulfilling the specification in `to`.
        - **tests** — `from` is a test covering `to`.
        - **deploys** — `from` is a deployment artifact shipping `to`.

        Anything else is rejected as a caller error and changes nothing."""
        return client.call("add_trace_edge", from_artifact_id=from_artifact_id,
                           to_artifact_id=to_artifact_id, rel=rel)

    @server.tool()
    def submit_gap_report(phases: list, resume_phase: str | None = None,
                          blockers: list | None = None) -> dict:
        """Submit your Onboarding Gap Report: your Complete/Partial/Missing assessment of each
        SDLC phase and the recommended resume phase. Call this ONCE, at the end, instead of
        writing the gap report into a document. Each `phases` item:
        {phase: <lifecycle key>, status: "complete"|"partial"|"missing", evidence?: [...]}.
        `resume_phase` = the first phase that is not complete; `blockers` = phase keys still
        missing that gate progress. The platform fills the project from this run and guarantees
        the report's shape — you provide the reasoning, not the format."""
        # `or project_id` / `or run_id` mirrors get_context and list_artifacts (S5-21). Without
        # the fallback an unset binding posted an empty string, which reaches the server as a
        # blank project id instead of failing here where the cause is obvious.
        return client.call("submit_gap_report",
                           project_id=project_id_bound or None,
                           run_id=run_id_bound or None,
                           phases=phases, resume_phase=resume_phase, blockers=blockers)

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
