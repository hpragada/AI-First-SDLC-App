# AGENTS.md — parallel-build operating manual

**Read this first, every session.** It tells any coding assistant (Claude Code, Cursor, Copilot, …)
**what to read, how to claim work, and which files you may touch** so several people can build the SDLC
platform **in parallel without integration bugs**. The project constitution is **`CLAUDE.md`** — its 10
**non-negotiables** (platform owns STATE / external tools own CONTENT; nothing reaches a system-of-record
without an approved gate; per-table `tenant_id` + RLS; capabilities-not-vendors; go through
`ExecutionDriver`/capability interfaces; durable runs via Temporal) **override everything**, including
this file. If a task would violate one, stop and flag it.

## Active phases (the only ones open for work)

| Phase | What | Stream | Spec |
|---|---|---|---|
| **4.7** | Auth & admin **backend** (design-invariant) | backend | `docs/PHASE_4.7_BUILD_SPEC.md` |
| **4.8** | Hi-fi **React UI** + design-sensitive backend (bucket B) | frontend + backend | `docs/PHASE_4.8_BUILD_SPEC.md` |

**Phases 5 & 6 are CLOSED** — do not start them (team decision; built on client demand). Phases 0–4.5
are **complete** — read them for context, don't modify.

## Context-consumption read-order (do this before writing any code)

1. **`CLAUDE.md`** — the non-negotiables + tech stack + guardrails.
2. **`BUILD_PLAN.md`** — pick **one** unchecked `[ ]` task in an active phase; honour its dependency
   markers (foundation tasks first — see below).
3. **`docs/PHASE_<n>_BUILD_SPEC.md`** for that phase — **the contract** (endpoint shapes, response
   schemas, FE architecture, component list). Build to it; do **not** re-decide it. If it's genuinely
   wrong/missing, update the spec in the same PR and say so.
4. Then, by task type:
   - **UI task** → the screen file(s) **`docs/design/screens/S-NN.html`** (the visual + the exact
     **states** to build) · `docs/design/README.md` (component catalog) ·
     `docs/design/{design-system,components}.css` + `shell.js` · **`docs/SCREEN_BUILD_MAP.md`** (the
     screen→component→endpoint row).
   - **Backend task** → `docs/UX_JOURNEYS_AND_IA_SPEC.md` (the journey + §9 decisions) · the endpoint
     contract in the phase spec · the **existing app/pattern you extend** (e.g. `backend/api/views.py`
     `TenantScopedMixin` + a domain service; an existing RLS migration to mirror).

That chain takes you from "which task" to a **complete contract + state list with no guesswork** — that
is the test for "can an assistant consume context and build."

## Claiming a task (so two people never collide)

1. In a **tiny dedicated commit**, flip the task's box in `BUILD_PLAN.md` from `[ ]` to **`[~] (init/branch)`**
   (e.g. `[~] (AK/feat-4.7-t6-integrations)`). Push it. That is your claim.
2. **One task at a time.** Finish (merge) before claiming another.
3. On merge, flip it to `[x]` with a one-line "what shipped" note (match the style of completed tasks).
4. If a task is already `[~]`, pick a different one — or coordinate with the owner.

## Work-streams & file ownership (the conflict-avoidance rules)

**Foundations land first (serialize only these):**
- Backend: **4.7 T1 → T2** (auth core, then signup + `is_tenant_admin`/`CurrentUser`). T3–T11 depend on them.
- Frontend: **4.8 T0** (router + `<AppShell>` + component library + api/auth client). All UI depends on it.

**Then fan out — parallel-safe, one assistant per task, each owning a disjoint module:**
- Backend 4.7 **T3–T11** + bucket-B (4.8 **T1**) — each owns its **own app/views module**
  (`apps/tenancy`, `apps/integrations`, `apps/projects`, `apps/registry`, `apps/runs`, services).
- Frontend 4.8 **T2–T5** — each owns its **own `frontend/src/features/<group>/` folder** (identity /
  setup / lifecycle / brownfield / observability).
- **BE and FE run concurrently:** FE builds against the spec contracts via Query hooks over the typed
  client, mocking an endpoint until it lands. Never block on the other stream.

**Shared files — append-only / coordinate (never rewrite; add your slice at the end):**
`backend/api/urls.py`, `backend/api/serializers.py`, `backend/config/settings.py` ·
`frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/routes.tsx`,
`frontend/src/components/ui/index.ts`, `frontend/src/auth/AuthContext.tsx` · `BUILD_PLAN.md`
(claim markers) · `docs/SCREEN_BUILD_MAP.md`. Everything else is task-owned. The specs being fixed up
front is what makes append-only safe — no shape renegotiation mid-stream.

## Branch / PR / Definition of Done

- Branch **off `develop`**: `feat/<phase>-<task>-<slug>` (e.g. `feat/4.7-t6-integrations`). PR → `develop`.
- **DoD:** matches the spec contract **and** (UI) every labelled state of the screen with visual parity;
  tests added (backend: service + REST + DB-level RLS for new tables; FE: each state renders + happy
  path); **`make test` / `make lint`** green (backend), **`npm run lint` + `tsc -b`** green (frontend);
  `/docs` updated in the **same PR** if a contract changed; `BUILD_PLAN.md` box → `[x]`.
- Migrations are **RLS-aware** and run as the **postgres** owner (the `sdlc_app` role can't ALTER).
- Honour the non-negotiables: no artifact bodies as source-of-truth; no SoR write before an approved
  gate; go through capability interfaces / `ExecutionDriver`; secrets are write-only.

## Verify before you open the PR

- **Backend:** `cd backend && pytest -q` (or `make test`); `make lint`. New table → prove RLS isolation.
- **Frontend:** `cd frontend && npm run lint && tsc -b`; run the dev server and put your screen
  **side-by-side with `docs/design/screens/S-NN.html`** — every state must match (tokens/classes,
  a11y: focus rings, labelled fields, ≥4.5:1, status never colour-alone).
- **Contract integrity:** the endpoint(s) you touched read the same in `BUILD_PLAN.md`, the phase spec,
  and (UI) `SCREEN_BUILD_MAP.md`. Fix all three together.

## Keep `/docs` authoritative

The specs are the shared truth. If you change a contract, update `docs/PHASE_4.<7|8>_BUILD_SPEC.md`
(+ `SCREEN_BUILD_MAP.md` for UI) in the same PR so the next assistant inherits the change. Don't let
code and spec drift — that is exactly where the "unexpected bugs" come from.
