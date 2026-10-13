# Artifact-Body Persistence & the UX Wireframe Fix — decision record for team review (2026-07-09)

**Author:** Claude (Opus) session · **Branch:** `develop` (uncommitted at time of writing).
**Scope:** how large artifact bodies (UX wireframe HTML, big specs) are now persisted, previewed,
and read by downstream agents. **This is a decision record, not a findings list** — it exists so a
teammate who later changes a capability (Figma write, a new connector, the wireframe model, chunked
storage) knows what the current mechanism guarantees and where the extension points are.

Recorded in `docs/Bugs.xlsx` as **S.No 68 (P1, Fixed)**. Related same-day fixes at the bottom.

---

## 1. The problem we hit (greenfield UX Design run)

The UX Design agent generated ~25 self-contained HTML wireframe documents (one per screen × state)
exactly as its `agent.md` instructs — but **the HTML was never stored.** Each `wireframe` artifact
ended up as an empty pointer carrying only a prose `layout_notes` string. Nobody could preview the
screens, and the implementation phase had nothing to read.

**Root cause (three locked constraints colliding):**
1. `register_artifact` is **pointers-only** by design (non-negotiables #1/#3: platform owns STATE as
   pointers/provenance; CONTENT bodies live in the object store / SoR — never in the DB or the state
   call). Correct — but it means the tool cannot carry a body.
2. Passing the HTML inline in `external_ref.body` blows the **MCP token cap** — a single ~401K-char
   `register_artifact` call was rejected. One MCP round-trip cannot carry hundreds of KB.
3. The planning/review agents are **sandboxed** (no `Write`/`Bash`/S3) so they cannot stage a
   snapshot themselves. Correct for safety — but it left large bodies with no home.

So the agent's central deliverable degraded to prose. `get_artifact` also returned pointers only, so
even a build agent could not read a screen's HTML. `agent.md` *promised* "the platform persists each
artifact body" — but **nothing implemented that promise.**

---

## 2. The decision — add the missing persistence primitive (don't weaken the invariants)

We did **not** relax "register_artifact is pointers-only" and did **not** give the sandbox local
write access. Instead we added the one primitive the system was missing: a **platform capability** to
hand a body to the platform for storage.

### `stage_artifact_body(filename, body, content_type)` → `{s3_key, content_hash, bytes}`
- Streams **one** body to the object store as a **run/phase-scoped draft**:
  `drafts/{tenant}/{project}/{run}/{phase}/{safe-filename}`.
- It is a platform-state MCP tool, so it works **inside the sandbox** (a capability call, not a local
  `Write`) and preserves #1/#3 — the body lands in S3, the state row still only ever holds pointers.
- **One document per call.** One HTML state ≈ 5–15 KB ≈ a few K tokens, safely under the MCP cap.
  This is the deliberate answer to constraint #2: never carry the whole screen set at once.

### `get_artifact_body(artifact_id, state=None)` → `{state, body, content_type, available_states, truncated}`
- The read counterpart. `get_artifact` stays pointers-only; this returns the **actual body**,
  read-through from S3, **one state at a time** (so the implementation/task-breakdown agents can read
  a screen's HTML without blowing the token cap). Caps a single body at 400 KB and flags `truncated`
  rather than silently cutting.

### Wireframe container model (team decision, 2026-07-09)
**One `wireframe` artifact per screen**, holding its states in `external_ref.states`:
```jsonc
external_ref = {
  "screen_id": "SCR-001", "screen_name": "Login", "route": "/auth/login", "persona": "...",
  "states": [
    {"name": "state-1-default", "s3_key": "drafts/.../SCR-001-login-state-1-default.html", "content_hash": "sha256:..."},
    {"name": "state-4-error",   "s3_key": "drafts/.../SCR-001-login-state-4-error.html",   "content_hash": "sha256:..."}
  ]
}
```
Primary `artifact.s3_key` = the **default** state, so single-body callers still see a screen.
Rejected alternative: one artifact per state (25+ rows) — floods the registry and the approval gate.

### End-to-end flow now
`agent stages each state → registers one wireframe/screen with states[] → preview reads every state
through S3 and shows a state switcher (each screen in an isolated <iframe>) → user approves the gate
→ export rides the existing export-policy seam where a connector capability exists.`

---

## 3. Invariants this preserves (do not break these when you change things)

- **State = pointers only.** `register_artifact` never carries a body; `stage_artifact_body` is the
  only body-write path, and it writes to the object store, not the DB. (#1/#3)
- **Sandbox stays closed.** Planning/review agents still have no `Write`/`Bash`/S3 — they persist
  bodies **only** through the capability. Don't "fix" a future large-body need by opening the sandbox.
- **Read-through, never copied back.** Preview and `get_artifact_body` read the body on demand and
  never write it onto the registry row.
- **No auto-publish.** Staged bodies are `sor="internal"` drafts. They reach a system-of-record only
  through an approved gate + the manual export policy (#5).

---

## 4. Extension points — read this before changing a capability

- **Figma (or any design tool) write export.** Wireframes are now real S3 drafts (`sor="internal"`).
  When a Figma **write** capability lands, wire it into `integrations/export_policy.py` (the
  `generate_figma_design` seam) so a wireframe artifact can be pushed on gate approval / manual
  export. No change to staging is needed — the bodies are already there. The `states[]` list is the
  natural unit to translate to Figma frames.
- **Read-as-SoR mode (client already has a design tool).** Unchanged: in that mode the agent does
  **not** stage HTML — it registers the `wireframe` pointing at the client's design
  (`sor="figma"`, `external_ref` = the design pointer). Staging is a GENERATE-mode concern only.
- **Other large bodies (big PRDs, journey maps, test suites).** `stage_artifact_body` is
  type-agnostic — any phase/agent can stage a large body and reference it. `agent.md` already tells
  the UX agent "when in doubt, stage the body." If another phase starts losing content, point its
  agent at the same protocol rather than inventing a second mechanism.
- **Versioning.** Draft keys are run/phase-scoped, so a **re-run overwrites its own** snapshot (by
  design — the registry row's `version` counter is the revision history, not S3). If you ever need
  immutable per-run snapshots, include a version/hash segment in the key — but weigh it against the
  registry version counter that already exists.
- **Chunking / very large single documents.** Today a single body is capped at 400 KB on read
  (`_MAX_BODY_READ_BYTES` in `tools.py`, `_cap_body` in `preview.py`) and flagged `truncated`. If a
  legitimate single document exceeds that, add range/chunked reads rather than raising the cap blindly
  (the cap protects the MCP token budget).
- **New object store / provider.** All staging goes through `storage.object_store.ObjectStore`
  (S3/MinIO/InMemory). Swap the provider there; nothing else changes.

---

## 5. Constraints & gotchas

- **One document per `stage_artifact_body` call.** Concatenating states re-introduces the token-cap
  crash. The agent prompt enforces this; keep it that way.
- **Primary `s3_key` must be the default state**, or the artifact's top-level preview body is empty
  (the switcher still works via `states[]`, and preview falls back to the default state, but set it).
- **Preview renders wireframes in an `<iframe srcDoc>`**, not `dangerouslySetInnerHTML` — the HTML is
  a full Tailwind-CDN document; injecting it into the app DOM would neither run its script nor contain
  its styles. `sandbox="allow-scripts"` on the iframe.
- **`get_context`/`list_artifacts` now bind the project UUID from the launch** (agents were passing
  the project *name* → backend 500). If you add a cross-project read, thread an explicit id — the
  default is now "the run's own project."

---

## 6. Files touched + tests

**Platform state:** `mcp_platform_state/tools.py` (both tools + `_obj_store`), `mcp_platform_state/server.py`
(`stage_artifact_body`/`get_artifact_body` + `_resolve_project` bind-first).
**Companion:** `runner/companion/state_mcp.py` (both tools, bind-first get_context/list_artifacts),
`runner/companion/runner.py` (`BUILD_STATE_TOOLS`).
**Allowlists:** `backend/api/runner_views.py` (build), `backend/orchestration/activities.py`
(`_PLATFORM_TOOL_NAMES`, planning/review).
**Read/preview:** `backend/integrations/preview.py` (`render_states`, `artifact_body_for_agent`,
`_cap_body`, states in payload, default-state fallback).
**UI:** `frontend/src/features/observability/ArtifactPreviewScreen.tsx` (`WireframeStates` iframe
switcher), `frontend/src/types.ts` (`ArtifactState`).
**Agent:** `agents/05_ux_design/agent.md` (staging protocol in Step 4b + Output).

**Tests (pass):** `test_mcp_platform_state.py` — `stage_artifact_body_persists_and_returns_pointer`,
`get_artifact_body_returns_one_wireframe_state`, `server_registers_all_tools` (updated);
`test_artifact_preview_rest.py` — `preview_multistate_wireframe_returns_states_and_default_body`.
*Note:* 4 preview REST tests fail locally only because MinIO (`minio:9000`) is unreachable from
host-run pytest — environmental, not a regression.

**Live verification pending:** restart backend + worker (companion picks up new code on next
`serve`), re-run UX Design on SpendLog-Test-2.1; confirm wireframe artifacts carry `states` with real
HTML and the preview switcher renders each screen.

---

## 7. Related fixes landed the same day (context)

For a teammate skimming "what changed 2026-07-09", the earlier engine-seam fixes (committed at
`98200ae`, Bugs S.No 63/65/66/67) are the backdrop this fix builds on:
- **S.No 65 (P1):** agent role body + manifest now delivered as a true file-based system prompt via
  `--system-prompt-file` (the old AGENTS.md channel was never auto-loaded — 7 agents ran with no role).
- **S.No 63 (P2):** planning/review agents sandboxed (`disallowed_tools` + `setting_sources`) so they
  stop wandering; build keeps its filesystem/shell tools.
- **S.No 66 (P1):** resilient message parser — unknown engine message types (e.g. `rate_limit_event`
  from a newer CLI) no longer crash a run.
- **S.No 67 (P1):** generic structured-`external_ref` preview renderer (pointer-only artifacts preview
  their own content).

Together with **S.No 68** (this doc), the UX Design phase should now run sandboxed, receive its role,
tolerate CLI skew, and **persist + preview its actual HTML screens.**
