# EXECUTION_AND_CLARIFICATIONS_SPEC.md — Local-Engine Execution + Interactive Clarifications (Phase 4.5)

Two production-blocking needs surfaced during end-to-end testing, both now built:

1. **Every engine-invoking phase runs on the client's own Claude Code**, not the platform's API key.
2. **Agents can ask the human questions mid-run** and get answers in the web app, **at zero idle cost**.

This spec is the authoritative "what/why/how" for both. It honors the locked non-negotiables: the
platform owns STATE + ORCHESTRATION; the engine only **executes**; gates (and now clarifications) are
control-plane objects, never engine hooks; runs are durable/resumable.

---

## 1. Requirement #1 — local-engine execution (per-user companion)

### Diagnosis
The `ClaudeDriver` already drives the Claude Code **CLI** (via the Agent SDK subprocess). The defect
was **where** planning/review ran: server-side, in the Temporal worker, whose env carried
`ANTHROPIC_API_KEY` → Anthropic **API billing**. Builds already ran correctly on the developer's
**local companion** using their logged-in `claude` (subscription). So the fix was to route *every*
phase through the build path's seam.

### Decision (team-confirmed)
- **Execution locus:** the **per-end-user companion**. Each web user enrolls their own companion; their
  phase runs dispatch to their own machine's logged-in Claude Code. No `ANTHROPIC_API_KEY` in that
  process — `ensure_local_engine_auth()` drops it and preflights `claude` on PATH.
- **Interaction surface:** **web app only.** The companion is a headless background daemon; the user
  triggers phases, answers questions, and decides gates entirely in the browser.

### The unified dispatch seam (`kind ∈ {plan, review, build}`)
```
Web app ──trigger phase──▶ trigger_phase (records triggered_by → resolves the user's enrollment;
                            execution_mode="companion" when one exists, else "server" fallback)
AgentRunWorkflow (server) ── compose_manifest ─▶ dispatch_phase (stash phase_task + a `dispatch`
                                                  claim block on run.inputs)
   companion daemon  ◀── GET /api/runner/work/ (atomic claim, skip-locked, scoped to its enrollment)
        runs run_planning_task / run_review_task / run_build LOCALLY (local claude, no API key)
        └─▶ POST /api/runner/{phases|reviews|builds}/<run>/report/  ─▶ phase_reported / build_reported signal
   register_phase_result (server: S3 body + registry pointer) ─ verify_writes ─ open_gate ─ gate ─ publish
```
- **State stays server-side.** The companion ships back the produced text/findings; the platform writes
  S3 + registers the pointer. The companion holds no DB/S3 credentials — it calls platform-state tools
  over the runner-token HTTP seam, tenant bound from the enrollment.
- **Server fallback.** `execution_mode="server"` keeps the in-worker `ClaudeDriver` path for CI/tests/
  headless; it is the dataclass default so existing tests are unchanged. Real runs default to companion.
- **Offline companion → takeover.** If a laptop never reports within `report_timeout_seconds`, the
  workflow parks the WorkItem for human takeover and fails the run (never hangs).

### Scope
**All** engine-invoking phases: planning/analysis/doc (`AgentRunWorkflow`), build + remediation (07),
and code review (08, via `CompanionReviewProvider` — dispatch + poll for findings). The only thing that
stays server-side is the control plane (manifest compose, S3/registry writes, gates, publishing).

---

## 2. Requirement #2 — interactive clarifications (zero-cost wait)

### Object
`Clarification` (`apps/clarifications`) — a control-plane sibling of `Approval`. RLS-isolated from the
first migration. Fields: `run`, `work_item`, `phase`, `status` (pending/answered/cancelled),
`questions` (`[{id,text,kind:text|choice|confirm,options?,required}]`), `answers`, `context`,
`signature` (idempotency hash), `answered_by`, `answered_at`.

### The `ask_human` tool (the zero-cost insight)
The agent calls `ask_human(questions, context)` (an MCP tool in the companion's platform-state server).
Its handler:
1. `POST /api/runner/clarifications/` → opens a **pending** Clarification (idempotent by question
   `signature`).
2. **Polls** `GET /api/runner/clarifications/<id>/` until answered. **While a tool call is in flight the
   model generates nothing — so no tokens accrue during the wait.** This is the fix for "the run stalls
   and burns cost": instead of looping/guessing, the agent waits for free.
3. Returns the answers as the tool result; the agent continues **in the same session**.

Covers context-gap, mid-process decisions, and pre-gate confirmations — any agent step.

### Answer surface (web)
- `GET /api/clarifications/?status=pending&work_item=&run=` and
  `POST /api/clarifications/<id>/answer/ {user_id, answers}` (project-membership check; required-answer
  validation; a `confirm` False still counts).
- Frontend: a **Clarifications** tab (`Clarifications.tsx`, 4s poll, per-kind answer field) + a
  **"needs answer" badge** on the Phase Console run timeline.

### Durability (re-dispatch never re-asks)
- `ask_human` is **idempotent by question signature** — a re-ask (even one already answered) returns the
  same record; answered ones return the answer immediately.
- `get_context` returns the work item's **answered** clarifications, and the Manifest Composer renders an
  optional **`# Answered Clarifications`** section ("use these; do NOT ask again"). A companion that
  crashes mid-wait and re-dispatches resumes without re-prompting the human.

---

## 3. REST surface (added this phase)

| Method + path | Auth | Purpose |
|---|---|---|
| `GET /api/runner/work/` | Runner | Companion claims the next dispatched task for its enrollment |
| `GET /api/runner/phases/<run>/` | Runner | Fetch the dispatched phase task (manifest + body) |
| `POST /api/runner/phases/<run>/report/` | Runner | Report a planning result → `phase_reported` |
| `POST /api/runner/reviews/<run>/report/` | Runner | Report an 08 review verdict (findings) |
| `POST /api/runner/clarifications/` | Runner | `ask_human` opens a clarification |
| `GET /api/runner/clarifications/<id>/` | Runner | `ask_human` poll until answered |
| `GET /api/clarifications/?status=&work_item=&run=` | X-Tenant-ID | Web: list clarifications |
| `POST /api/clarifications/<id>/answer/` | X-Tenant-ID | Web: a project member answers |

(Build endpoints `/api/runner/builds/<run>/[report/]` and the merge/phase gates are unchanged.)

---

## 4. Companion daemon

`python -m runner.companion serve --api-url … --tenant … --token … [--repo-path … --worktrees …]`

Long-polls `/api/runner/work/`, dispatches by `kind` (plan/review → `run_planning_task`/`run_review_task`
→ phase/review report; build → `run_build` → build report), forces the **local** engine login (drops
`ANTHROPIC_API_KEY`, requires `claude` on PATH), and reports failures so a run never hangs. Enrollment is
unchanged (`enroll` returns a one-time token; only its hash is stored).

---

## 5. Definition of Done (met)

Runs locally; planning + review + build all execute on the user's local Claude Code; clarifications are
answerable in the web app with zero idle cost and survive re-dispatch; `tenant_id`/RLS on the new table;
gates + clarifications are control-plane; server fallback keeps CI green. Acceptance:
`backend/tests/test_acceptance_phase45.py` (end-to-end clarification loop + offline takeover) and
`test_phase_dispatch.py` (live-Temporal companion branch).
