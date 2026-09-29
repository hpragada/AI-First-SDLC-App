# AI-First SDLC Platform — Master Build Blueprint & Context Anchor

> **What this document is.** The single source of truth for building the enterprise SDLC platform. It captures (a) every problem/concern/question raised and its resolved solution, (b) the target architecture, (c) a phase-by-phase build plan naming every component, and (d) the open decisions to confirm before coding. Any session can resume from this file with full context.
>
> **Status (2026-09-17):** Decisions LOCKED (see Part E). **Phases 0 through 4.7 are complete; 4.8 is in progress.** This line said "Ready to build Phase 0" until today. The architecture below is still the governing design — what changed is that most of it is now built, so where a section describes a future intention, check `BUILD_PLAN.md` before believing it is still ahead of us.
> **Stack baseline:** Django + React + Postgres. Engine-agnostic across Claude (Agent SDK, **default**), Codex (`codex exec`/Agents SDK), Copilot (CLI/coding agent). Integration via MCP. Durable workflow via **Temporal**. Tenant isolation via **Postgres RLS (shared DB)**.
> **Delivery mode:** **Local-first** — Phases 0–4 run in a local `docker-compose` stack; cloud runner fleet + sandbox hardening are a Cloud-Migration workstream in Phase 5. Remote MCP connectors (Atlassian/Figma/GitHub) are reachable from local during testing.

---

# PART A — Context Anchor

## A1. Vision
Transform the existing local/Git-coupled SDLC command suite (17 agents + rules + gates, built for Claude Code) into a **multi-tenant, web-delivered, engine-agnostic agentic SDLC platform** that operates the client's real tools-of-record (Confluence, Jira, Figma, Xray, Git) bidirectionally, runs the full lifecycle (ideation → deploy) for greenfield and brownfield, single- and multi-repo, with human review gates, RBAC, audit, and durable memory.

## A2. Governing principles (settled across prior sessions)
1. **Platform owns *state*; external tools own *content*; local files are ephemeral.**
2. **Platform owns *orchestration*; the engine only *executes*** → engines stay interchangeable.
3. **Memory = index + provenance + events, never copied content** → enables drift detection & conflict cross-verification.
4. **Work is a graph (per-work-item DAG), not a linear pipeline** → phases run concurrently per feature/repo.
5. **Every state-change is gated, attributed, logged.** Review precedes publication.
6. **Capabilities, not vendors** → `tasktracker.create_epic()`, swappable connector underneath.
7. **Assess before act** → agents surface, ask, and gate; they never silently re-create or overwrite.

## A3. Concern → Resolution Ledger (the "cover everything" map)

| # | Concern / Question raised | Resolved solution | Plane / Component | Built in |
|---|---|---|---|---|
| G1 | Push PRD to Confluence | DocStore connector; gate-then-publish lifecycle | Integration / DocStore | Ph1 |
| G2 | Push UX to Figma; implementation reads *current* Figma | DesignSource connector (read `get_design_context`/`get_variable_defs`; write `use_figma`/`generate_figma_design`); read-through at run time | Integration / DesignSource | Ph3 |
| G3 | Read client-designed wireframes for implementation | Read-Figma-as-SoR mode; UX agent ingests instead of generating | DesignSource + UX agent | Ph3 |
| G4 | Push tasks/epics/sprints to Jira; implement by task id from platform | TaskTracker connector; `implement ISSUE-KEY` reads live issue | Integration / TaskTracker | Ph1 |
| G5 | Track progress dynamically | Jira transitions + Event Ledger + Work DAG state + Run History | State + Control | Ph1–2 |
| B1 | Don't re-create what live SoR already has | Onboarding = discover→register→reconcile→gap-fill (pointers, not copies) | Onboarding service | Ph4 |
| B2 | Onboarding maintains logs/memory | Registry + Ledger + Knowledge Index (DB memory) | State plane | Ph0/Ph4 |
| B3 | Same dynamic integrations after onboarding | Brownfield resumes onto same pipeline | Control + Integration | Ph4 |
| B4 | Onboard static files (Word/PDF/Excel) | Extract → structure → adopt as `sor=internal`; provenance to originals; review gate | Onboarding (extraction) | Ph4 |
| M1 | How other repos know artifacts/context | Central Artifact Registry (global store) | State / Registry | Ph0 |
| M2 | Fate of context-bridge | Survives as a versioned **API-Contract artifact** in the registry, not a copied file | Registry + Architecture agent | Ph4 |
| M3 | Onboard & continue split FE/BE | One Project, N Repositories, shared memory, per-repo manifest | Project/Repo model | Ph4 |
| M4 | Cross-repo contract & dependencies | API-Contract artifact + cross-repo edges in Work DAG; drift gates | State + Drift service | Ph4 |
| P1 | User invokes agents from app, not Claude Code | Control plane runs agents in runners; UI invokes via API | Control + Execution | Ph0 |
| P2 | Store project/progress/work in DB | Project Profile + Work DAG + Run History | State plane | Ph0 |
| P3 | Need a memory? | **Yes** — the State plane *is* the memory | State plane | Ph0 |
| P4 | RBAC by expertise | Role→phase→gate matrix; segregation of duties | Security / RBAC | Ph5 |
| P5 | Bidirectional integrations (Jira/Xray/Figma) | Read-through / write-through + webhooks | Integration plane | Ph1–3 |
| P6 | Web app can't reach local machine | Cloud runner **[REC]**, customer-hosted runner (enterprise), local companion (narrow) | Execution / Runners | Ph2 |
| P7 | Store artifacts in S3 + export; how to push pre-review | Artifact lifecycle draft→staged→approved→published; S3 = staging+snapshot+internal-SoR | State / Artifact Store | Ph0–1 |
| P8 | What replaces CLAUDE.md | Project Profile (DB record) + Composed Manifest (rendered per run → AGENTS.md) | State + Control | Ph0 |
| C1 | Engine-agnostic (Codex/Copilot/Cursor) | ExecutionDriver interface + MCP + AGENTS.md; gates in platform not engine | Execution / Drivers | Ph0 design, Ph6 drivers |
| PG1 | Traceability matrix | Traceability Graph (requirement→…→release, bidirectional) | State / Traceability | Ph1 |
| PG2 | Proposed vs accepted scope; reconciliation | `proposed→accepted` states; idempotent reconcile (no dup) | Control + Registry | Ph1 |
| PG3 | Linear phases too coarse | Per-work-item DAG | Control / State machine | Ph0 |
| PG4 | Notifications/comms | Notification service (Slack/Teams/email) | Control / Notify | Ph6 |
| PG5 | RAID / change mgmt / impact analysis | Change-impact via traceability graph + drift | State + Drift | Ph4 |
| PG6 | Failure/durability/saga | Durable workflow engine (Temporal **[REC]**); retries, idempotency, dead-letter, compensation | Execution / Orchestration | Ph2 |
| PG7 | Reproducibility / agent versioning | AgentSpec Registry (semver + prompt + model pinned in provenance) | State / AgentSpec | Ph0 |
| PG8 | Orchestrator token explosion | Manifest budgeting + retrieval + subagent isolation | Control / Manifest composer | Ph0 |
| PG9 | Env provisioning / private registries | Runner image profiles; toolchains, registries, test DB, secrets inject | Execution / Runner provisioning | Ph2 |
| PG10 | Human takeover; reconcile human commits | Takeover state on work items; Git webhooks update registry | Control + Integration | Ph2 |
| PG11 | NFR tests, test-impact, preview envs, flaky quarantine, defect loopback | Test orchestration features in test phases | Execution + TestMgmt | Ph3 |
| PG12 | Prompt injection via SoR content | Untrusted-data handling; per-phase tool allowlist; platform-enforced egress; human approval on sensitive writes | Security plane | Ph2/Ph5 |
| PG13 | Credential honeypot / tenant isolation | Secrets vault + token broker; RLS or DB-per-tenant | Security plane | Ph5 |
| PG14 | Sandbox / RCE | gVisor/Firecracker runners; no prod net; egress allowlist | Execution / Sandbox | Ph2/Ph5 |
| PG15 | Audit / compliance | Immutable audit log; evidence export | Security / Audit | Ph5 |
| PG16 | Data governance / ZDR / model routing | Per-tenant ZDR/Bedrock/Vertex routing; PII; GDPR erasure incl. embeddings | Security / Governance | Ph5 |
| PG17 | Platform's own CI/CD, observability, DR | Platform DevOps; OTel; backups/DR of State plane | Observability + Ops | Ph5 |
| PG18 | External API rate limits | Connector queue/backoff/cache per tenant | Integration / Rate governor | Ph1+ |
| PG19 | Cost metering / quotas / chargeback | Per-run cost → per-tenant/project metering & quotas | Observability / Cost | Ph5 |
| PG20 | Design system/tokens as artifact | Design-System artifact + Code Connect mapping | State + DesignSource | Ph3 |
| PG21 | a11y gate | WCAG gate in UX/test phases | Control / Gates | Ph3 |
| PG22 | Design↔code round-trip | `generate_figma_design` code-to-canvas back to Figma | DesignSource | Ph3 |
| PG23 | Responsive / multi-brand | Responsive wireframes; per-tenant theming | UX agent | Ph3 |
| PG24 | Eval / quality harness | Golden datasets + regression evals; gate agent promotion | Observability / Quality | Ph5 |
| PG25 | Migration of existing 17 agents | 75/15/10 buckets: ~75% reasoning verbatim, ~15% data references rerouted (**anywhere in the agent**), ~10% glue + reference-sweep gate | Agent Migration (Part D) | Ph0 |
| PG26 | A worker running **stale code** takes work, does less than current code would, and reports success — PG6's durable engine cannot see this (the workflow genuinely succeeded) | Build badge = content fingerprint + orderable date; only the newest code may serve a queue, identical code joins it, older code stands down without polling; reconcile-on-read as the second line. See `docs/INCIDENT_2026-08-26_stale_worker.md` | Execution / Orchestration | Ph4.7 |

---

# PART B — Target Architecture

## B1. The seven planes
1. **Experience (React):** project workspace, phase consoles, gate approvals, traceability viewer, dashboards/reports, integration & RBAC admin, cost/audit views.
2. **Control (Django services):** Work-DAG state machine, Gate/Approval service, Run scheduler, Manifest composer, Drift & reconciliation, Policy engine (RBAC + guardrails), Notification, Execution-driver router.
3. **Execution (sandboxed runners):** ExecutionDriver interface → Claude/Codex/Copilot drivers; planning runners (no repo) & build runners (repo+toolchain); rewritten agent specs; per-run AGENTS.md.
4. **Integration (capability-abstracted MCP):** DocStore, TaskTracker, DesignSource, TestMgmt, CodeHost, CodeIntel connectors + **Platform-State MCP** + Webhook ingestion + Rate governor.
5. **Memory/State (Postgres + pgvector + object store):** Project Profile, Artifact Registry, Traceability Graph, Work DAG, Event Ledger, Run History, Knowledge Index, Users/Roles, Integration Connections, AgentSpec Registry, S3 artifact store.
6. **Security & Governance:** Secrets vault, Token broker, Tenant isolation, Prompt-injection defense, Egress control, Immutable audit, Compliance evidence, Data-residency/model routing.
7. **Observability & Quality:** OTel tracing, Cost metering/quotas, SLOs, Failure/dead-letter dashboards, Evaluation/quality harness.

## B2. Core data model

> **RLS (LOCKED):** every table carries `tenant_id` and a Postgres Row-Level-Security policy from Phase 0. Shared DB, tenant-scoped rows. Richer RBAC/SoD layers on top in Phase 5.

| Entity | Key fields | Purpose |
|---|---|---|
| **Tenant** | id, config, residency policy, model-routing policy | Isolation boundary |
| **Project** | id, tenant_id, track, repo_topology(single/split/multi) | Top unit |
| **Project Profile** | description, domain, tech_stack, coding_standards, NFRs, constraints, glossary, **important_context (freeform)**, version | Durable record replacing CLAUDE.md facts (per-repo overrides allowed) |
| **Repository** | id, project_id, role, code_host_ref, stack_overrides | Multi-repo |
| **WorkItem** | id, project_id, repo_id?, feature_stream, type(epic/story/task), **state**, dependencies[], assignee, takeover_flag | Drives the DAG |
| **Artifact Registry** | id, project_id, repo_id?, phase, type, **status(draft/staged/approved/published)**, **sor(internal/confluence/jira/figma/xray/git)**, external_ref, s3_ref, content_hash, version, produced_by_run_id, embedding | Global store / index |
| **Traceability Graph** | edge(from, to, rel: derives/implements/tests/deploys) | Bidirectional lineage |
| **Event Ledger** | append-only(actor, action, target, ts, payload) | Progress + conflict substrate |
| **Run History** | id, work_item_id, agent_id+ver, engine, model, prompt_ver, inputs, outputs, cost, gate_decision, approver, ts | Audit + reproducibility |
| **Knowledge Index** | pgvector embeddings over artifacts | Retrieval / token control |
| **User/Role/Membership** | user, role, project scope | RBAC |
| **IntegrationConnection** | tenant_id, capability, connector, scopes, token_ref(vault), health | Per-tenant connectors |
| **AgentSpec Registry** | agent_id, semver, prompt_version, body_ref, recommended engine/model | Reproducible agents |
| **Approval** | id, gate_type, work_item_id, required_role, approver, decision, ts | Gates as objects |

## B3. Artifact lifecycle & SoR strategy
`generated(draft) → staged → reviewed → APPROVED → published`
- **Pre-gate:** artifact in **S3**, `status=draft`; human reviews it rendered in React. *Never auto-pushed.*
- **On APPROVED:** publish to live SoR (or keep `sor=internal` if no SoR exists); store immutable snapshot in S3 for audit/rollback.
- **Three source classes:**
  - **Live API SoR** (Jira/Confluence/Figma/Git): register pointer, **read-through**, don't re-create.
  - **Internal SoR** (small client, no external tool): platform/S3 *is* the SoR; export-on-demand.
  - **Static files** (Word/PDF/Excel at onboarding): extract → structure → adopt as internal SoR, provenance to originals, review gate. Upgrade path = re-point `sor` later, no agent change.
- **Gate policy (LOCKED):** **every** artifact type is `gate-then-publish` — all artifacts are reviewed, gated, and only then published. No `auto-publish` in v1.

### B3.1 Export policy — exports are user-triggered and phase-scoped *(team flow decision, 2026-07-07; LOCKED)*

Gate approval publishes artifacts **internal-only** (S3 snapshot + `published` status). **It never
pushes to an external tool.** The user exports manually via `POST /artifacts/{id}/publish/` (screen
S-34), governed by a **phase-scoped export policy**: defaults in
`backend/integrations/export_policy.py`, per-project overrides in `ProjectProfile.export_policy`,
editable on S-10.

| Phase | Export target |
|---|---|
| Ideation · Requirements · PRD · Architecture · Security · CI-CD | **docstore** (Confluence today; SharePoint/Drive later) |
| Task Breakdown | **tasktracker** (backlog reconciliation into Jira) |
| Testing / Test Automation `test_case` artifacts | **testmgmt** (Xray today; TestRail/Zephyr later) |
| UX Design | **internal**, until the Figma write seam ships — this narrows the earlier "Figma write" decision to that one deferred seam. Figma **read** is unaffected |
| Everything else | internal |

A **docstore** export transfers the system of record. **tasktracker** and **testmgmt** exports are
*projections*: the artifact keeps `sor=internal` and the export is recorded under
`external_ref.export`.

*Moved here on 2026-09-17 from the continuation brief's §3, which is now a historical record.*

## B4. Context model (CLAUDE.md replacement)
**Project Profile (DB record, human-maintained)** → **Manifest Composer** assembles per-run context `{profile core + relevant registry pointers + recent ledger events + retrieved knowledge}` → rendered to **AGENTS.md** (+ thin CLAUDE.md for Claude-specifics) inside the runner → agent reads it → discarded after run. Always current (generated, not maintained); scoped (per phase/repo); governed (versioned). Freeform `important_context` always flows in verbatim.

## B5. Execution model
**ExecutionDriver interface** (`run_planning_task`, `run_build_task`) with drivers: **ClaudeDriver** (Agent SDK), **CodexDriver** (`codex exec`/Agents SDK), **CopilotDriver** (CLI in own runner). Same composed context + same MCP set across drivers; only the driver differs.
**Runner topologies (LOCKED — local-first):** **Planning** phases run **server-side** (no repo). **Build** execution (Phase 2+) runs on a **local-companion runner on the developer's own machine**, editing a **platform-managed git worktree** (a clean `feature/<key>` branch) so the developer runs/tests locally before any PR — the daily dev loop is unchanged. The companion connects **outbound** to the platform (the platform never reaches into the dev machine; state tools are served remotely so the machine needs no DB — tenant binding + RLS stay server-side). A **server-side/container build runner** is an optional later topology behind the same `run_build_task` seam; the **cloud runner fleet** + sandbox hardening (gVisor/Firecracker, autoscaling) is the Phase-5 Cloud-Migration workstream. (Detail: `docs/PHASE_2_BUILD_SPEC.md` D8–D9.)
**Default engine (LOCKED):** **ClaudeDriver (Agent SDK)**; interface built so Codex/Copilot drivers drop in at Phase 6.
**Gates live in the control plane**, never in engine hooks → identical behavior across engines.

## B6. Integration model
Capability abstraction (DocStore/TaskTracker/DesignSource/TestMgmt/CodeHost/CodeIntel) + Platform-State MCP. Per-tenant headless auth (API token/OAuth-app) brokered from vault. Webhooks → ingestion → ledger → drift detection. Rate governor (queue/backoff/cache) per tenant.

| Capability | Default connector | Read | Write |
|---|---|---|---|
| DocStore | Atlassian **REST** → Confluence | ✅ | ✅ |
| TaskTracker | Atlassian **REST** → Jira | ✅ | ✅ |
| DesignSource | Figma **REST** | ✅ | ⚠️ beta, Full seat |
| TestMgmt | Xray REST/GraphQL | ✅ | ✅ |
| CodeHost | GitHub | ✅ | ✅ |
| CodeIntel | **Built-in analyzer** (`BuiltinCodeIntel`) | ✅ | indexes |
| Platform-State | Custom MCP | ✅ | ✅ |

> **This table was corrected on 2026-09-17; it described intentions, not what shipped.** Two
> differences matter. **(1) Atlassian and Figma shipped as direct REST clients, not MCP** —
> `backend/integrations/atlassian/rest.py` and `figma/rest.py`. The *capability* abstraction held
> exactly as designed (`docstore.*` / `tasktracker.* `/ `designsource.*`), which is the point of
> principle 9; only the transport underneath differs. **(2) The CodeIntel default is the built-in
> analyzer, not Repowise** — `backend/integrations/codeintel/builtin.py`, which reaches the same
> algorithmic target from the standard library and git. Repowise remains the *optional* connector
> (D1), not the default. **Platform-State is genuinely MCP** and is the one that had to be.

## B7. Security & governance
Prompt-injection defense (untrusted tool output, per-phase allowlists, platform-enforced egress, human approval on sensitive writes); secrets vault + token broker; tenant isolation (RLS/DB-per-tenant); sandboxed runners (gVisor/Firecracker, no prod net); immutable audit + compliance evidence; data-residency & ZDR/Bedrock/Vertex model routing; GDPR erasure across registry **and** embeddings.

## B8. Observability & quality
OTel spans per run/tool-call; per-tenant cost metering + quotas; durable workflow (retries/idempotency/dead-letter/saga); evaluation harness (golden datasets, regression evals) gating AgentSpec promotion.

---

# PART C — Phase-by-Phase Build Plan (every component)

> Each phase ends in a **thin vertical slice** proving the plane before breadth is added.

## Phase 0 — Platform Spine
**Goal:** Move source-of-truth off the filesystem; run the existing agents through the platform with state, gates, and provenance — no external SoR yet.
**Components:**
- **State plane (Postgres):** Tenant, Project, **Project Profile**, Repository, **WorkItem (+DAG)**, **Artifact Registry**, **Event Ledger**, **Run History**, **AgentSpec Registry**, S3 artifact store (draft/staged/snapshot).
- **Platform-State MCP server:** tools `get_context`, `register_artifact`, `update_artifact`, `log_event`, `list_work_items`, `transition_work_item`, `detect_drift (stub)`.
- **Control plane:** Work-DAG state machine; **Temporal run orchestration** (durable runs, retries, visibility — Temporal arrives here, not Phase 2); **Manifest Composer** (profile→AGENTS.md, with budgeting); Gate/Approval service; Execution-driver router (1 driver).
- **Execution plane:** **ClaudeDriver** (Agent SDK, default), **local runner**, planning runner; AGENTS.md rendering; subagent loading from AgentSpec.
- **Local dev stack:** `docker-compose` — Django, React, Postgres (with RLS), Temporal, Platform-State MCP, local runner.
- **Tenancy:** `tenant_id` + RLS policies on every table from the first migration.
- **Experience plane (minimal):** project create, Project Profile editor, phase console, gate-approval UI, run/event timeline.
- **Agent Migration (Part D):** rewrite I/O contract of agents 01–03 first (locked/SOTA) as the template.
**Thin slice:** ideation → PRD → architecture run fully off platform state; artifacts registered in S3 as drafts; gates enforced; runs attributed; manifest rendered per run.
**Defer:** external SoRs, build execution, RBAC depth, multi-engine.

## Phase 1 — First System of Record (Atlassian)
**Goal:** Real bidirectional Confluence + Jira; progress tracking; traceability.
**Components:**
- **DocStore connector** (Confluence: create/update pages, versioned, read-through).
- **TaskTracker connector** (Jira: epics/stories/sprints, transitions, comments, read-through).
- **Artifact lifecycle** publish step (draft→approved→published) + per-type gate policy.
- **Traceability Graph** + viewer (requirement→PRD→epic→story).
- **Reconciliation service** (`proposed→accepted`; idempotent — never duplicate existing issues).
- **Brownfield-lite onboarding (single-repo):** discover→register→reconcile against Atlassian (register-don't-recreate) **+ static-file extraction** (Word/PDF/Excel → structured artifacts as `sor=internal`, provenance to originals, review gate). Lets **both greenfield and brownfield single-repo** be tested from Phase 1.
- **Rate governor** (queue/backoff/cache) v1.
**Thin slice:** greenfield PRD→Confluence on approval; backlog→Jira; `implement ISSUE-KEY` reads live issue; status round-trips; lineage visible. **Brownfield:** onboard a project whose PRD is a Word doc + stories in Excel → review-gated adoption; onboard a project already in Jira → register without duplicating.
**Defer:** code execution, Figma/Xray.

## Phase 2 — Build Execution
**Goal:** Real code: implementation/review/test producing PRs, durably.
**Components:**
- **CodeHost connector** (GitHub: branches, PRs, status, webhooks; headless REST, per-tenant). Platform owns the PR/merge SoR surface; the engine never calls GitHub directly.
- **Local-companion build runner** (developer's machine; **managed git-worktree** edit surface — run/test locally before PR; provisioning: toolchain, test DB, secrets inject; **remote Platform-State serving**, no DB on the dev machine). Server-side runner is a later optional topology.
- **Light multi-repo** (repo-per-WorkItem: `WorkItem.repo`, N repos/project, per-repo CodeHost). Full multi-repo (cross-repo DAG, API-contract, drift) stays Phase 4.
- **Durable workflow** (Temporal — introduced Phase 0; here extended for long-running build sagas): dispatch-to-companion + await, retries, idempotency, dead-letter, compensation/saga.
- **Build phases** (implementation, code review, testing) via Remediation loop preserved. Gate roles split: 07→`tech_lead`, 08+merge→`reviewer`.
- **Secret scanning** + **egress allowlist** + per-phase tool allowlist (initial prompt-injection guardrails on a developer-trusted runner; full sandbox → Phase 5).
- **Human takeover** state + **Git-webhook reconciliation** (human commits update registry — the primary collaboration path in companion mode).
**Thin slice:** WorkItem→**companion worktree**→local build/test→PR→CI status round-trip, with a forced mid-run failure recovered idempotently; a human commit reconciles via webhook; two repos in one project build independently.
**Defer:** design/test-mgmt loops, multi-repo.

## Phase 3 — Design & Test Loops
**Goal:** Close the UX and QA loops.
**Components:**
- **DesignSource connector** (Figma read-first; write opt-in; `get_variable_defs` tokens).
- **Design-System artifact** + Code Connect mapping; responsive wireframes; per-tenant theming.
- **a11y (WCAG) gate**; **design↔code round-trip** (`generate_figma_design`).
- **TestMgmt connector** (Xray: tests, executions, result import).
- **Test orchestration:** NFR tests, test-impact selection, **ephemeral preview env per PR**, flaky quarantine, **defect loopback** (failing test → linked bug).
**Thin slice:** UX read/write Figma; implementation reads *current* design; results→Xray; failing test opens a traced bug.
**Defer:** brownfield, multi-engine.

## Phase 4 — Brownfield-Full & Multi-Repo
**Goal:** Deep onboarding (code intelligence) and microservices/split-repo support. (Brownfield-*lite* single-repo onboarding already shipped in Phase 1.)
**Components:**
- **Onboarding service (full):** adds **gap-fill** generation for genuinely missing artifacts on top of Phase 1's discover→register→reconcile.
- **CodeIntel connector** (Repowise) per repo; Knowledge Index population; entry agents (00-series) reworked here.
- **API-Contract artifact** (context-bridge's surviving job) + cross-repo edges in Work DAG.
- **Multi-repo project model — full** (cross-repo DAG edges, API-Contract artifact, shared memory, per-repo manifest). *(Light repo-per-WorkItem — `WorkItem.repo`, N repos/project — already shipped in Phase 2.)*
- **Drift detection live** (webhooks → ledger → drift gates; change-impact via traceability).
**Thin slice:** onboard split FE/BE, resume mid-pipeline, change contract → both repos get drift gates.

## Phase 5 — Enterprise Hardening
**Goal:** Make it sellable to regulated enterprises.
**Components:**
- **RBAC + segregation of duties** (role→phase→gate matrix).
- **Secrets vault + token broker**; **tenant isolation** (RLS/DB-per-tenant).
- **Prompt-injection defenses hardened**; sandbox hardening.
- **Immutable audit + compliance evidence export**; **data-governance/ZDR/model routing**; GDPR erasure.
- **Platform DevOps:** CI/CD, IaC, DR/backups of State plane, OTel observability.
- **Cost metering/quotas/chargeback.**
- **Evaluation/quality harness** (gate AgentSpec promotion on regression).
- **Cloud-Migration workstream:** move from the local stack to cloud — **cloud runner fleet** (autoscaling), **sandbox hardening** (gVisor/Firecracker, no prod net, egress allowlist), managed Postgres/Temporal, object store.
**Thin slice:** pass a SOC2-style walkthrough; per-tenant isolation demo; block a release on an eval regression; run the platform in the cloud with a runner fleet.

## Phase 6 — Engine Pluggability & Scale-Out
**Goal:** Prove interchangeability and scale.
**Components:**
- **CodexDriver + CopilotDriver**; AGENTS.md routing; per-phase engine/model selection + override.
- **DAG parallelism** + concurrency limits.
- **Notification plane** (Slack/Teams/email); PM/PO **dashboards** (burn-up, traceability, release notes).
- **Monitoring (13) + Retrospective (14) agents** (the deferred suite tracks).
**Thin slice:** run the same project on a second engine with no agent rewrite; two features progress concurrently through different phases.

---

# PART D — Agent Migration Plan (existing 17 agents → platform)

**Reuse profile per agent — the 75 / 15 / 10 buckets (by content kind, not file position):**
- **~75% REUSE VERBATIM — the reasoning** (Role, Evidence Base, Process how-to, three-part teaching pattern, quality gates). Preserved word-for-word.
- **~15% REWRITE — the data references** (where inputs are read / outputs written). These appear **throughout the body, including inside Process steps** — *all* are rerouted to platform sources-of-truth. **Not** two bookend sections.
- **~10% REPLACE — invocation glue** (frontmatter/tools/model, command file, Human Gate).

*(The percentages estimate volume, not position — the 15% is interleaved with the 75%, often in the same sentence. See `AGENT_MIGRATION_SPEC.md` §2.)*

**The ~15% rewrite, applied to every reference anywhere in the agent:**
1. **Every input read** (`requirements.md`, user stories, the current design, the codebase, "next task from `tasks.md`") → `platform.get_context()` / `get_artifact()` / `tasktracker.get_issue()` / `designsource.*` per the §3 mapping.
2. **Every output write** (`prd.md`, `tasks.md`, epics, test cases) → SoR write tool + `register_artifact()` + `log_event()`.
3. **Human Gate** → control-plane Approval.
A **mandatory reference sweep** (grep the migrated agent for any leftover `.md`/`docs/`/`tasks.md`/`CLAUDE.md`) gates each migration — a leftover local path = failed migration.

**Tooling:** a **migration script** that rewrites those three sections against a template; bodies stored in AgentSpec Registry (semver + prompt_version). `commands/*.md` + `settings.json` retired in favor of UI/API + AgentSpec.
**Order:** 01–03 (locked, as template) → 04–10 (SOTA, incl. security benchmark) → 11–12 → entry agents (00-series) reworked as Onboarding service (Ph4).
**Dual-mode preserved:** agent bodies remain runnable in `.claude/` locally *and* via the platform — prior work is an asset, not sunk cost.
**Cleanups to fold in:** fix the known pointer/naming/line-ending/model-string inconsistencies during migration.

---

# PART E — Confirmed Decisions (LOCKED)

| # | Decision | Confirmed choice | Architecture impact |
|---|---|---|---|
| 1 | Delivery mode | **Local-first**, cloud later | Phases 0–4 in local `docker-compose`; cloud runner fleet + sandbox hardening → Phase 5 Cloud-Migration |
| 2 | First connector | **Atlassian Cloud** | DocStore+TaskTracker via Atlassian Rovo MCP (Cloud), headless API-token/OAuth-app auth |
| 3 | Connector capabilities | **Read + write** (incl. Figma write) | All connectors bidirectional; Figma write = beta + Full seat (HTML wireframe preview kept as fallback) |
| 4 | Durable workflow | **Temporal** | Pulled forward to **Phase 0** as run-orchestration backbone |
| 5 | Tenant isolation | **RLS (shared DB)** | `tenant_id` + RLS on every table from Phase 0; DB-per-tenant not used in v1 |
| 6 | Default engine | **Claude Code (Agent SDK)**, switchable | ClaudeDriver default; ExecutionDriver interface built Phase 0; Codex/Copilot Phase 6 |
| 7 | Project tracks to test | **Both greenfield & brownfield** | Brownfield-**lite** (single-repo: Atlassian register + static-file extract) added to **Phase 1**; brownfield-**full** (codeintel + multi-repo + drift) stays Phase 4 |
| 8 | Gate policy | **All artifacts reviewed, gated, published** | Single policy: every artifact `gate-then-publish`; no auto-publish in v1 |
| 9 | Build execution model | **Local-companion runner + managed worktree** | Phase 2: build runs on the developer's machine in a platform-managed git worktree (run/test locally before PR); platform owns the PR/merge SoR surface + gates (07→`tech_lead`, 08+merge→`reviewer`); **light repo-per-WorkItem** multi-repo in P2 (full → P4); server-side/cloud runners later. See `docs/PHASE_2_BUILD_SPEC.md` D8–D10 |

> **Next deliverables (Phase 0 kickoff):** (1) Phase 0 Postgres schema (with `tenant_id`+RLS), (2) Platform-State MCP tool contract, (3) Manifest Composer spec, (4) Temporal workflow/activity shapes for a run, (5) worked before/after migration of one agent (PRD or Implementation), (6) local `docker-compose` topology.
