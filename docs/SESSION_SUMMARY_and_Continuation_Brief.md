# SDLC Platform — Session Summary & Continuation Brief

> ## ⚠️ Historical record — do not resume from this file
>
> **Status as of 2026-09-17.** This is the hand-off note from the **architecture sessions that ran
> before any platform code existed**. It is kept because it records how the design was reached and
> what was locked. It is **not** a description of where the project is now.
>
> **Still binding:** **§3 Locked decisions** and **§9 Key principles** — though both are now also
> carried in `/CLAUDE.md` (the twelve non-negotiables) and, for decision 9's export policy, in the
> blueprint's **§B3.1**. **§6** is superseded in detail by `docs/AGENT_MIGRATION_SPEC.md`.
>
> **Out of date, and left unedited on purpose:** **§1** ("No platform code has been written yet"),
> **§5** ("about to start Phase 0"), **§7** (deliverables, all long since built) and **§8** (an open
> question answered in July 2026). Phases 0 through 4.7 are complete and 4.8 is in progress.
>
> **To resume work, read instead:** `/CLAUDE.md` → `/AGENTS.md` → `/BUILD_PLAN.md` → the current
> phase's build spec. For the architecture and the "why", open
> **`SDLC_Platform_Master_Build_Blueprint.md`**; **`Enterprise_SDLC_Platform_Architecture.md`** is
> the earlier architecture doc.

*Everything below this line is the file as written at the time, kept unedited as the record.*

---

## 1. Where we are in one paragraph
We are transforming the team's existing **AI-First SDLC Command Suite v6** (17 Claude Code agents + rules + gates + CLAUDE.md + settings.json, all local/Git-file based) into a **multi-tenant, web-delivered, engine-agnostic agentic SDLC platform** (Django + React + Postgres). All architecture reasoning and decisions are complete and **locked**. The next step is to **start building Phase 0 (the platform spine)**. No platform code has been written yet.

## 2. What was accomplished this session
1. **Full read & analysis** of the shipped v6 suite (every agent, rule, command, CLAUDE.md, settings.json); understood the universal agent skeleton, the rules system, the human-gate model, and the 07↔08 remediation loop / 09→09b test handoff.
2. **Diagnosed the core problem:** the suite treats the local filesystem as the system of record, which breaks for enterprise clients who use Confluence/Jira/Figma/Xray/Git as live, human-edited tools-of-record.
3. **Designed the target architecture** (7 planes) and resolved every concern the team raised (greenfield push-to-SoR, brownfield no-recreate, multi-repo, progress tracking, memory, RBAC, bidirectional integrations).
4. **Verified the 2026 capability landscape** (grounded, not assumed): Claude Agent SDK; Atlassian Rovo MCP (GA, read+write, headless auth); Figma MCP (read + beta write); Xray REST/GraphQL; Codex (`codex exec`, MCP, can be an MCP server); Copilot (MCP across surfaces, caveats); AGENTS.md as the cross-tool context standard.
5. **Answered the cross-assistant question:** the approach is engine-agnostic because the portable substrate is MCP + AGENTS.md + the platform; only a thin per-engine ExecutionDriver differs. Gates live in the platform, never in engine hooks.
6. **Ran a multi-persona gap analysis** (PO/PM/Tech Lead/Dev/QA/Security/DevOps/UX) and surfaced the "big six" corrections — most importantly: **work is a per-WorkItem DAG, not a linear pipeline**, plus traceability graph, prompt-injection/credential security, durable failure handling, engine-driver abstraction, and an eval/quality harness.
7. **Resolved the deep questions:** artifact lifecycle (draft→staged→reviewed→approved→published) with S3 as staging/snapshot/internal-SoR; web app can't reach local machines → resolved via a **local-companion build runner that connects *outbound*** (Phase 2; the platform never reaches in; the dev edits a managed git worktree and runs/tests locally before PR); agent migration is mechanical (~75% reused); multi-repo solved by central memory + per-repo manifest (**light repo-per-WorkItem in P2; full multi-repo P4**); **CLAUDE.md replaced by Project Profile (DB) + Composed Manifest (rendered per run → AGENTS.md)**; static-file onboarding = extract→structure→adopt as internal SoR with a review gate.
8. **Produced two reference docs** (the architecture doc and the master blueprint) and **locked the 8 open decisions** (below).

## 3. Locked decisions (confirmed by the team)
1. **Local-first** build & test; cloud later (cloud runner fleet + sandbox hardening → Phase 5).
2. **Atlassian Cloud** as the first connector (Confluence + Jira via Rovo MCP, headless auth).
3. **Read + write** for all connectors, including **Figma write** (beta, Full-seat; HTML preview kept as fallback).
4. **Temporal** as the durable workflow engine — **introduced in Phase 0**.
5. **Postgres RLS (shared DB)** for tenant isolation — `tenant_id` + RLS on every table from Phase 0.
6. **Claude Code (Agent SDK)** as default engine, **switchable** (driver interface built Phase 0; Codex/Copilot Phase 6).
7. **Test both greenfield and brownfield** — brownfield-**lite** single-repo onboarding moved into **Phase 1**; brownfield-**full** (code intelligence + multi-repo + drift) stays Phase 4.
8. **All artifacts reviewed, gated, then published** — single `gate-then-publish` policy, no auto-publish.
9. **Exports are user-triggered and phase-scoped** *(team flow decision, 2026-07-07)*: gate approval publishes artifacts **internal-only** (S3 snapshot + published status) — it never pushes to an external tool. The user exports manually (`POST /artifacts/{id}/publish/`, S-34), governed by a **phase-scoped export policy** (`backend/integrations/export_policy.py` defaults + per-project `ProjectProfile.export_policy` overrides, editable on S-10): Ideation/Requirements/PRD/Architecture/Security/CI-CD → **docstore** (Confluence today; SharePoint/Drive later), Task Breakdown → **tasktracker** (backlog reconciliation into Jira), Testing/Test-Automation `test_case` artifacts → **testmgmt** (Xray today; TestRail/Zephyr later), **UX Design → internal** until the Figma write seam ships (Figma READ unaffected; narrows decision 3's "Figma write" to that deferred seam), everything else internal. Docstore export transfers the SoR; tasktracker/testmgmt exports are projections (artifact keeps `sor=internal`, the export recorded under `external_ref.export`).

## 4. The architecture in brief (see blueprint for full detail)
- **7 planes:** Experience (React) · Control (Django: Work-DAG state machine, Temporal orchestration, Manifest Composer, Gate/Approval, Policy, Driver router) · Execution (ExecutionDriver → ClaudeDriver default; local runner) · Integration (capability-abstracted MCP connectors + Platform-State MCP + webhooks) · Memory/State (Postgres+pgvector+S3) · Security/Governance · Observability/Quality.
- **Source-of-truth model:** platform owns *state* (pointers/provenance/events, never copied content); external tools own *content*; local files are ephemeral.
- **Context model:** Project Profile (durable DB record) → Manifest Composer → AGENTS.md rendered per run, discarded after.
- **Capability abstraction:** agents call `tasktracker.*`/`docstore.*`/`designsource.*`, swappable connectors underneath.
- **Key data entities:** Tenant, Project, Project Profile, Repository, WorkItem(+DAG), Artifact Registry (status + sor + pointers), Traceability Graph, Event Ledger, Run History, Knowledge Index, AgentSpec Registry, Approval, IntegrationConnection.

## 5. Phase roadmap (current status: about to start Phase 0)
- **Phase 0 — Platform Spine** ← NEXT. State plane (Postgres+RLS), Platform-State MCP, Temporal run orchestration, Manifest Composer, Gate/Approval, ClaudeDriver + local runner, minimal React UI, migrate agents 01–03 as the template. *Slice:* ideation→PRD→architecture off platform state, gated, no external SoR yet.
- **Phase 1 — Atlassian SoR + Brownfield-lite.** Confluence+Jira read/write, lifecycle publish, traceability, reconciliation, single-repo brownfield onboarding (register + static-file extract). *Slice:* greenfield PRD→Confluence + backlog→Jira + implement-by-issue-key; brownfield onboard from Word/Excel or existing Jira.
- **Phase 2 — Build Execution.** CodeHost (GitHub) connector; **local-companion runner + managed git-worktree** (dev builds/tests locally before PR); Temporal build sagas; secret scanning/egress; human takeover + webhook commit reconciliation; **light repo-per-WorkItem** multi-repo. *Slice:* WorkItem→worktree→PR→CI with a recovered mid-run failure.
- **Phase 3 — Design & Test Loops.** Figma read/write + design-system artifact + a11y gate + round-trip; Xray + NFR/test-impact/preview-envs/flaky/defect-loopback. *Slice:* implementation reads current Figma; results→Xray; failing test→linked bug.
- **Phase 4 — Brownfield-Full & Multi-Repo.** Repowise code intel, API-contract artifact, multi-repo model, live drift detection. *Slice:* onboard split FE/BE, resume mid-pipeline, contract change → drift gates.
- **Phase 5 — Enterprise Hardening + Cloud Migration.** RBAC/SoD, secrets vault, audit/compliance, data-governance/ZDR, cost quotas, eval harness, **cloud runner fleet + sandbox hardening**. *Slice:* SOC2-style walkthrough; run in cloud.
- **Phase 6 — Engine Pluggability & Scale.** Codex+Copilot drivers, DAG parallelism, notifications, dashboards, Monitoring(13)+Retrospective(14) agents. *Slice:* same project on a 2nd engine; concurrent features.

## 6. Agent migration approach (existing 17 agents → platform)
- **~75% reused** (Role, Evidence Base, Process, three-part teaching pattern, quality gates, Rules) → becomes the subagent system prompt.
- **The migration rule — 75 / 15 / 10 by content kind (same for all 17):** **~75% REUSE VERBATIM** the *reasoning*; **~15% REWRITE** every *data reference* to a platform source-of-truth **wherever it appears — including inside Process steps** (input reads → `get_context()`/`get_artifact()`/`tasktracker.get_issue()`; output writes → SoR write + `register_artifact()` + `log_event()`); **~10% REPLACE** invocation glue (incl. Human Gate → control-plane Approval). The 15% is interleaved through the body, not two bookend sections. A **reference sweep** (no leftover `.md`/`docs/`/`tasks.md` paths) gates each agent. "Verbatim" protects the thinking, never a dead file path. See `AGENT_MIGRATION_SPEC.md`.
- A **migration script** applies the 3 edits against a template; bodies stored in AgentSpec Registry (semver + prompt_version). `commands/*.md` + `settings.json` retired. Fix the known naming/pointer/line-ending/model-string inconsistencies during migration. Agents stay runnable in `.claude/` locally too (dual-mode).

## 7. Exact next deliverables (start of next session)
1. **Phase 0 Postgres schema** — all core entities with `tenant_id` + RLS policies.
2. **Platform-State MCP tool contract** — `get_context`, `register_artifact`, `update_artifact`, `log_event`, `list_work_items`, `transition_work_item`, `detect_drift` (stub).
3. **Manifest Composer spec** — Project Profile + registry + ledger + retrieval → AGENTS.md, with token budgeting.
4. **Temporal workflow/activity shapes** for one agent run (compose context → run driver → gate → write-back).
5. **Worked before/after migration of one agent** (recommend PRD or Implementation) to lock the template.
6. **Local `docker-compose` topology** (Django, React, Postgres+RLS, Temporal, Platform-State MCP, local runner).

## 8. Open question carried into next session
Whether the next session should produce a **working Phase 0 code scaffold** (Django app + models + Platform-State MCP server + ClaudeDriver + docker-compose) **or detailed written specs** the team implements. This was asked but not yet answered — confirm at the start of the build session.

## 9. Key principles to carry forward (don't drift from these)
- Platform owns state & orchestration; engine only executes; gates live in the platform.
- Memory = index + provenance + events, never copied content.
- Capabilities, not vendors. Assess before act; agents never silently re-create or overwrite.
- Domain-agnostic across all client domains. Reuse the existing agent bodies — they are an asset, not a rewrite-from-scratch.
- Every artifact: reviewed → gated → published. Work is a per-WorkItem DAG.
