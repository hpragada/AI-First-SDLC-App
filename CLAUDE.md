# CLAUDE.md — AI-First SDLC Platform

This repo builds a multi-tenant, web-delivered, **engine-agnostic agentic SDLC platform** (Django + React + Postgres) that operates clients' real tools-of-record (Confluence/Jira/Figma/Xray/Git) and runs the full lifecycle with human review gates.

**Before writing any code, read `/docs/PHASE_4.8_BUILD_SPEC.md` for the current phase, and follow `/BUILD_PLAN.md` task by task.** (Phases 0 through 4.7 are complete — their specs, `/docs/PHASE_0_BUILD_SPEC.md` through `/docs/PHASE_4.7_BUILD_SPEC.md`, are finished-phase references. *Corrected 2026-09-17: this line still named Phase 2 as current, while the "How we work" section below correctly named 4.7 and 4.8.*) The "why" lives in `/docs/SDLC_Platform_Master_Build_Blueprint.md`. Keep this file lean — detail belongs in `/docs`.

---

## Non-negotiables (LOCKED decisions — never violate)
1. **Platform owns STATE; external tools own CONTENT; local files are ephemeral.** Never make a local file the source of truth. State = pointers/provenance/events in Postgres.
2. **Platform owns ORCHESTRATION; the engine only executes.** Gates live in the control plane, **never** in engine hooks.
3. **Memory = index + provenance + events, never copied content.** The Artifact Registry stores pointers + hashes + versions, not artifact bodies.
4. **Work is a per-WorkItem DAG**, not a linear pipeline. The unit of work is the `WorkItem`.
5. **Every artifact: draft → reviewed → gated → published.** No auto-publish. Nothing reaches a system-of-record without an approved gate.
6. **Tenant isolation via Postgres RLS (shared DB).** Every table has `tenant_id` + an RLS policy from the first migration.
7. **Default engine = Claude (Agent SDK), switchable.** Always go through the `ExecutionDriver` interface — never call the engine directly from business logic.
8. **Durable execution via Temporal** from Phase 0. Agent runs are Temporal workflows.
9. **Capabilities, not vendors.** Call `tasktracker.*` / `docstore.*`, never `jira.*` directly, so connectors are swappable.
10. **Domain-agnostic.** No client-domain assumptions baked into platform code or agents.
11. **Mockups before ANY frontend change — present, get approval, then build exactly what was approved.** Any work that touches **any part of the SDLC frontend** — a task, a bug fix, an enhancement, a flag — starts by presenting **high-level mockups in the chat**, with the **best options** and a recommendation, and then **stops and waits for the team to choose one**. Presenting and building in the same turn breaks this rule; so does shipping something that differs from the approved mockup. The team cannot see the frontend from the source code, so a change nobody pictured in advance is a change nobody agreed to, and every correction arrives as re-work. This is stricter than the "wireframe for genuine design decisions" practice it replaces — it covers **every** frontend change, bug fixes included.
12. **The agents are the product's intelligence** — migrate them by the **75 / 15 / 10 buckets** (content kind, not file position): **~75% REUSE VERBATIM** the *reasoning* (Role/Evidence/Process how-to/teaching pattern/quality gate) — never re-invented or "improved"; **~15% REWRITE** every *data reference* (file paths, `tasks.md`/`requirements.md`/`docs/`/`CLAUDE.md` reads & writes) to a platform source-of-truth **wherever it appears, including inside Process steps** — the 15% is interleaved through the body, not two bookend sections, and verbatim never protects a dead file path; **~10% REPLACE** invocation glue. A migrated agent still naming a local file is a FAILED migration — run the §8 reference sweep. See `/docs/AGENT_MIGRATION_SPEC.md`.

## Tech stack
- **Backend:** Python 3.12, Django 5 + Django REST Framework, Postgres 16 (RLS, pgvector), Temporal (`temporalio`).
- **Agent runtime:** `claude-agent-sdk` (Python) via `ClaudeDriver`.
- **MCP:** custom Platform-State MCP server (Python MCP SDK); remote connectors added Phase 1+.
- **Frontend:** React + Vite + TypeScript.
- **Object store:** S3-compatible (MinIO locally).
- **Local stack:** Docker Compose. Pin exact versions in lockfiles; use current stable.

## Repository structure (scaffold this first — BUILD_PLAN P0-T1)
```
backend/        Django: control + state planes, REST API
  config/       Django project (settings, urls, asgi)
  apps/         tenancy · projects · workitems · registry · ledger · runs · gates · integrations
                · a11y · clarifications · knowledge · quality        (12 today; the first 8 are P0's)
  orchestration/  Temporal workflows + activities
  drivers/      ExecutionDriver interface + ClaudeDriver
  manifest/     Manifest Composer (Project Profile → AGENTS.md)
mcp_platform_state/  Platform-State MCP server
agents/         migrated agent bodies (AgentSpec registry source)
legacy_suite/   the v6 SDLC suite VERBATIM (agents/commands/rules/CLAUDE.md/settings.json) — SOURCE intelligence to migrate, never deleted
frontend/       React app (Experience plane)
runner/         local runner harness (planning runner in P0)
docs/           blueprint, continuation brief, per-phase build specs
```

## How we work (read this — it prevents drift)
- **Parallel / multi-assistant execution:** read **`/AGENTS.md`** first — context read-order, task-claim protocol, work-stream + file-ownership rules, branch/PR/DoD. (Active phases: 4.7 backend + 4.8 UI; specs `/docs/PHASE_4.7_BUILD_SPEC.md` + `/docs/PHASE_4.8_BUILD_SPEC.md`; per-screen map `/docs/SCREEN_BUILD_MAP.md`.)
- **Phase by phase, slice by slice.** Do the current phase's "thin vertical slice" end-to-end before adding breadth. Don't build Phase N+1 modules early.
- **Implement contracts, don't re-decide them.** The build spec fixes schemas, interfaces, and tool signatures. If something is genuinely undecided, ask — don't silently invent.
- **One task at a time from `/BUILD_PLAN.md`.** After each task: run it, write/pass a test, commit, tick the checkbox.
- **Migrations are RLS-aware from day one.** Every model gets `tenant_id`; every table gets an RLS policy.
- **Tests + types required.** No task is "done" without a passing test and a runnable demo of its slice.
- **Keep `/docs` authoritative.** If a design decision changes, update the relevant `/docs` file in the same PR.

## Dev commands (target — Claude Code wires these up in P0)
```
docker compose up -d            # postgres, temporal, minio, mcp server
make migrate                    # django migrations (RLS policies included)
make seed                       # demo tenant + project + agent specs
make dev                        # backend API + frontend + worker
make test                       # backend + frontend tests
make lint                       # ruff + mypy + eslint
```

## Guardrails — do NOT
- Do NOT store artifact content as the source of truth in files or in the DB (store pointers; bodies live in S3 as drafts/snapshots or in the SoR).
- Do NOT push anything to a system-of-record before its gate is APPROVED.
- Do NOT call the Anthropic API / Claude Code directly from app code — go through `ExecutionDriver`.
- Do NOT put gate logic in Agent SDK hooks — gates are control-plane Approval objects.
- Do NOT hardcode Jira/Confluence/Figma — go through capability interfaces.
- Do NOT skip `tenant_id`/RLS on any table.
- Do NOT bloat this file — link to `/docs`.

## Definition of Done (per slice)
Runs locally via `docker compose up` + `make dev`; the phase's thin-slice demo works end-to-end; tests pass; `tenant_id`/RLS enforced; gates enforced; `/BUILD_PLAN.md` checkboxes updated; `/docs` updated if a decision changed.

## Reference docs
- `/docs/PHASE_4.8_BUILD_SPEC.md` — build-grade contracts for the **current** phase (**read before coding**), with `/docs/SCREEN_BUILD_MAP.md` for the per-screen map.
- `/docs/PHASE_4.7_BUILD_SPEC.md` — Phase 4.7 contracts (complete).
- `/docs/PHASE_2_BUILD_SPEC.md` — Phase 2 contracts (complete; build execution + local companion).
- `/docs/PHASE_1_BUILD_SPEC.md` — Phase 1 contracts (complete; Atlassian SoR + brownfield-lite + rate governor).
- `/docs/PHASE_0_BUILD_SPEC.md` — Phase 0 contracts (complete; the spine these phases build on).
- `/docs/AGENT_MIGRATION_SPEC.md` — **how to migrate the `/legacy_suite/` agents, rules, commands (read before any agent task)**.
- `/BUILD_PLAN.md` — the ordered task backlog across all phases (with legacy-suite coverage map).
- `/docs/SDLC_Platform_Master_Build_Blueprint.md` — full architecture + concern→resolution ledger (the "why/what").
- `/docs/SESSION_SUMMARY_and_Continuation_Brief.md` — **historical**: the pre-build architecture sessions. Its §3 locked decisions still bind (and are mirrored here + in the blueprint's §B3.1); its "where we are" and "next steps" sections describe July 2026 and are superseded by `/BUILD_PLAN.md`. Do not resume from it.
