# AGENTS.md — parallel-build operating manual

**Read this first, every session.** It tells any coding assistant (Claude Code, Cursor, Copilot, …)
**what to read, how to claim work, and which files you may touch** so several people can build the SDLC
platform **in parallel without integration bugs**. The project constitution is **`CLAUDE.md`** — its 12
**non-negotiables** (platform owns STATE / external tools own CONTENT; nothing reaches a system-of-record
without an approved gate; per-table `tenant_id` + RLS; capabilities-not-vendors; go through
`ExecutionDriver`/capability interfaces; durable runs via Temporal; **mockups approved before any
frontend change**) **override everything**, including
this file. If a task would violate one, stop and flag it.

## STOP — before you touch the frontend

**Non-negotiable #11 in `CLAUDE.md`, repeated here because it is the easiest one to walk past.**

If the work you are about to do changes **any part of the SDLC frontend** — a task, a bug fix, an
enhancement, a flag, however small — you do **not** start by editing `frontend/`. You start by:

1. **Presenting high-level mockups in the chat** — an actual visual, not a description of one.
2. **Offering the best options**, with a recommendation and the trade-off for each.
3. **Waiting for the team to approve one.** Presenting and building in the same turn breaks the rule.
4. **Building exactly what was approved.** A shipped screen that differs from the chosen mockup —
   even if it is better — is a breach.

The team cannot read the frontend out of the source code. A screen nobody pictured in advance is a
screen nobody agreed to, and every correction then arrives as re-work.

## Active phases (the only ones open for work)

| Phase | What | Stream | Spec |
|---|---|---|---|
| **4.8** | Hi-fi **React UI** + design-sensitive backend (bucket B) | frontend + backend | `docs/PHASE_4.8_BUILD_SPEC.md` |
| **A11Y** | **Web-accessibility QA capability (WCAG 2.2)** — a new client-driven capability built *on top of* the platform | backend + runner + agents + frontend | `docs/web-accessibility/` |

**Phases 5 & 6 are CLOSED** — do not start them (team decision; built on client demand). Phases 0–4.7
are **complete** — read them for context, don't modify. *(Corrected 2026-09-17: **4.7 is finished**
and was removed from this table, where it was still listed as open.)*

**The A11Y workstream is different from the phase work above — read this before touching it.**
It carries its **own plans, backlog
and claim markers**, not `BUILD_PLAN.md`. Read in this order: `docs/web-accessibility/RESEARCH_CORRECTIONS.md`
(what the research got wrong about this platform — several "already exists" claims are untrue) →
`USER_JOURNEYS.md` → `BUILD_PLAN_QA.md` → `TASK_BACKLOG_QA.md`. **Build the QA plan to completion before
starting the other-phases plan.** Claim tasks by flipping the box to `🟡` in the relevant task backlog with
your initials, and to `🟢` with a one-line "what shipped" when done — same discipline as `BUILD_PLAN.md`,
different file.

> **Two things in this block changed and are corrected here on 2026‑09‑17.** The accessibility work
> no longer lives on its own branch — `web-accessibility-build` is **merged**, so read and build it
> in place. And the greenfield/brownfield bug backlogs are **no longer parked**: that pause was set
> on 2026‑08‑12, and the P2/P3 batches, the follow-up batch and the Bugs.xlsx rows have all been
> worked since. Treat both backlogs as live.

## Context-consumption read-order (do this before writing any code)

1. **`CLAUDE.md`** — the non-negotiables + tech stack + guardrails.
2. **`BUILD_PLAN.md`** — pick **one** unchecked `[ ]` task in an active phase; honour its dependency
   markers (foundation tasks first — see below).
3. **`docs/PHASE_<n>_BUILD_SPEC.md`** for that phase — **the contract** (endpoint shapes, response
   schemas, FE architecture, component list). Build to it; do **not** re-decide it. If it's genuinely
   wrong/missing, update the spec in the same PR and say so.
4. Then, by task type:
   - **UI task** → **first, the mockup-approval rule above — no `frontend/` edit before the team has
     approved an option.** Then the screen file(s) **`docs/design/screens/S-NN.html`** (the visual + the exact
     **states** to build) · `docs/design/README.md` (component catalog) ·
     `docs/design/{design-system,components}.css` + `shell.js` · **`docs/SCREEN_BUILD_MAP.md`** (the
     screen→component→endpoint row).
   - **Backend task** → `docs/UX_JOURNEYS_AND_IA_SPEC.md` (the journey + §9 decisions) · the endpoint
     contract in the phase spec · the **existing app/pattern you extend** (e.g. `backend/api/views.py`
     `TenantScopedMixin` + a domain service; an existing RLS migration to mirror).

That chain takes you from "which task" to a **complete contract + state list with no guesswork** — that
is the test for "can an assistant consume context and build."

## Claiming a task (so two people never collide)

1. On the **phase branch**, in a **tiny dedicated commit**, flip the task's box in `BUILD_PLAN.md` from
   `[ ]` to **`[~] (your-initials)`** (e.g. `[~] (AK)`). Push it. That is your claim — everyone pulls and sees it.
2. **One task at a time.** Finish (committed + tests green) before claiming another.
3. When done, flip it to `[x]` with a one-line "what shipped" note (match the style of completed tasks).
4. If a task is already `[~]`, pick a different one — or coordinate with the owner.

## Work-streams & file ownership (the conflict-avoidance rules)

**Each phase = one shared branch off `develop`** — `phase-4.7-backend` (all 4.7 tasks) and
`phase-4.8-ui` (all 4.8 tasks). Several assistants work the **same** phase branch on **disjoint
modules**, coordinating via the claim markers + the ownership rules below. The two phase branches are
independent (backend vs UI), so the streams never collide.

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

- **One shared branch per phase, created off `develop`:** `phase-4.7-backend` (all 4.7 tasks) and
  `phase-4.8-ui` (all 4.8 tasks). All work for a phase commits to its phase branch; **PR the phase
  branch → `develop`** at the phase milestone (or agreed checkpoints). The two branches are independent.
- **Shared-branch discipline (many of us push to the same phase branch):** `git pull --rebase` before
  you start *and* before every push; commit **small and often**; stay strictly inside your task-owned
  module; touch shared/append-only files in their own tiny commits. A conflict almost always means two
  people in one file — re-check ownership. (Optional: do a task on a short-lived local branch and merge
  it into the phase branch — keeps the phase branch the single integration point that PRs to `develop`.)
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
