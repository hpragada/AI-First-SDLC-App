# SETUP & KICKOFF — Building the SDLC Platform with Claude Code

This is the exact path from empty repo to building. Follow it top to bottom once.

---

## 0. Prerequisites (install once)
- **Claude Code** (latest) + an Anthropic plan/API key with Agent SDK access.
- **Docker Desktop** (for Postgres, Temporal, MinIO).
- **Python 3.12** and **Node 20+** (Claude Code can install project deps, but these runtimes should exist).
- **Git**.
- (Phase 1, not now) An **Atlassian Cloud** site with Jira + Confluence, and an API token for headless auth.

## 1. Create the repo and drop in the kit
```bash
mkdir sdlc-platform && cd sdlc-platform && git init
mkdir docs
```
Place the files from this kit:
```
sdlc-platform/
├── CLAUDE.md                                   # repo root
├── BUILD_PLAN.md                               # repo root
├── SETUP_AND_KICKOFF.md                        # repo root (this file)
├── legacy_suite/                               # the v6 SDLC suite VERBATIM — source intelligence to migrate
│   ├── agents/  (17)  ├── commands/  (17)  ├── rules/  (2)  ├── CLAUDE.md  └── settings.json
└── docs/
    ├── PHASE_0_BUILD_SPEC.md
    ├── AGENT_MIGRATION_SPEC.md                      # how to migrate the legacy suite
    ├── SDLC_Platform_Master_Build_Blueprint.md      # from the prior session
    └── SESSION_SUMMARY_and_Continuation_Brief.md    # from the prior session
```
Commit: `git add -A && git commit -m "Bootstrap: docs + CLAUDE.md + build plan + legacy suite"`.

> **Verify before committing:** confirm `/legacy_suite/` holds *your latest v6* agents/rules/commands. If the team has newer edits than this bundle, swap them in — Claude Code migrates whatever is in `/legacy_suite/`.

> That's the entire manual setup. **Everything else is built by Claude Code** — including the scaffold, docker-compose, and dependencies (task P0-T1). You do not hand-create the project tree.

## 2. Open in Claude Code and orient it
From the repo root: `claude`. Then give it this first message verbatim:

> Read `CLAUDE.md`, then `docs/PHASE_0_BUILD_SPEC.md`, then `docs/AGENT_MIGRATION_SPEC.md`, then `BUILD_PLAN.md`. Then list the files in `legacy_suite/agents/`. Summarize back to me: the 11 non-negotiables, the Phase 0 goal, the P0 task list, and — in your own words — how our existing agents get migrated using the **75/15/10 buckets**: which content is the ~75% reasoning kept verbatim, which is the ~15% data references that get rerouted, and (critically) **where those references live**. Do not write any code yet — confirm your understanding first.

Verify its summary matches the docs. The **make-or-break check:** it must say that the **~15% data references are scattered throughout the agent — including inside Process steps — not confined to a top/bottom section**, and that a migrated agent still naming a local file (`tasks.md`, `requirements.md`, `docs/...`) is a FAILED migration. If it describes the 15% as just a "Context Loading header + Post-Phase Writes footer," correct it now — that misread is what would silently break the agents at runtime.

## 3. Build Phase 0, one task at a time
Drive it task by task (don't say "build everything"). For each task:

> Do **P0-T1** from `BUILD_PLAN.md`, following `docs/PHASE_0_BUILD_SPEC.md`. Implement only this task. When done: run it, add a test, show me how to verify, then update the checkbox. Stop and ask if any contract is ambiguous.

Then `P0-T2`, `P0-T3`, … in order. After the data + RLS tasks (T3–T4), explicitly verify isolation:

> Prove RLS works: create two tenants with rows in each, then show that a query scoped to tenant A cannot read tenant B's rows.

After the Temporal + driver + manifest tasks (T6–T8), run a dry agent execution before wiring the UI. Finish with the acceptance slice:

> Do **P0-T14**: run ideation→requirements→prd→architecture end-to-end as WorkItems. Show the Temporal run, the composed AGENTS.md, each draft artifact in S3, the gate approval, publication as `sor=internal`, the work-item transitions, and the traceability chain in the UI.

## 4. Working rhythm that keeps Claude Code on-rails
- **One task per turn.** Long "do it all" prompts cause drift and unreviewable diffs.
- **Commit after every green task.** Small commits = easy rollback.
- **Re-anchor when needed:** "Check this against the non-negotiables in CLAUDE.md" if a change smells off (e.g., state going into a file, a gate in an engine hook, a missing `tenant_id`).
- **Keep `/docs` authoritative.** If you change a decision mid-build, have Claude Code update the relevant `/docs` file in the same commit.
- **Use subagents for isolated work** (e.g., a review subagent) once the SDK is wired — but keep gates in the platform, never in hooks.

## 5. Moving to the next phase
When a phase's acceptance slice is green and committed:

> Generate `docs/PHASE_1_BUILD_SPEC.md` from `docs/SDLC_Platform_Master_Build_Blueprint.md` (Phase 1 section), at the same build-grade contract level as the Phase 0 spec. Then we'll work P1 tasks from `BUILD_PLAN.md`.

Repeat the task-by-task rhythm. The blueprint already carries every phase; you just translate each into a build-grade spec as you reach it.

## 6. Phase 1 readiness note
Before Phase 1, have the Atlassian Cloud API token ready and store it via the platform's `IntegrationConnection` + secret handling — **never** hardcode it. The Atlassian Rovo MCP endpoint is `https://mcp.atlassian.com/v1/mcp` with headless API-token auth; the remote connector works from your local stack.

---

### What you now have
A repo where **CLAUDE.md** sets the rules, **PHASE_0_BUILD_SPEC** fixes the contracts (so Claude Code implements, not re-derives), **BUILD_PLAN** sequences the work, and the **blueprint/brief** carry the full reasoning. That's the complete, sufficient kit — Claude Code can build Phase 0 through Phase 6 from here without losing your locked decisions.