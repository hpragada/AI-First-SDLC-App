# BUILD_PLAN.md — Ordered Task Backlog

**Working agreement:** Build **phase by phase, slice by slice.** Do one task, run it, test it, commit, tick the box. Don't start a later phase's modules early. Read `/docs/PHASE_<n>_BUILD_SPEC.md` before starting each phase. (Only Phase 0's spec exists now; generate the next phase's build spec at the start of that phase, from the blueprint.)

**Agent/rules/commands work:** every task that migrates a legacy asset follows `/docs/AGENT_MIGRATION_SPEC.md`. The **reasoning** in `/legacy_suite/` is reused **verbatim**; **every data reference (incl. those inside Process steps) is rerouted** to a platform source-of-truth, and the **§8 reference sweep** must pass (no leftover `.md`/`docs/`/`tasks.md` paths) before an agent is considered migrated.

### Legacy-suite coverage map (every asset is accounted for)
- **Agents (17):** 01–04 → P0 · 06 → P1 · 07,08,11,12 → P2 · 05,09,09b,10 → P3 · 00,00b,00c,00d → P4. (13,14 built new in P6.)
- **Rules (2):** RULE-BEHAVIOR + RULE-EXECUTION → P0-T10a.
- **Commands (17) + settings.json:** → P0-T10b (phase-trigger pattern + AgentSpec seed; one per agent).
- **Original CLAUDE.md:** → ProjectProfile model + Manifest Composer (P0-T3, T7).

### 🎯 First usable product (Final Team Goal met at MVP)
After **Phase 2**, a user can run a **greenfield** project end-to-end (idea → PRD → architecture → backlog in Jira → implemented PR) and **onboard an existing single-repo** project (local docs *or* Atlassian via MCP, from Phase 1). Phases 3–4 add design/test/security depth and brownfield-full/multi-repo; 5–6 add hardening, cloud, and engine choice. **Stop and ship/dogfood at end of P2.**

---

## Phase 0 — Platform Spine  ✅ COMPLETE
- [x] **P0-T1** Scaffold repo per CLAUDE.md structure: `backend/`, `mcp_platform_state/`, `agents/`, `frontend/`, `runner/`, `docs/`. Add `docker-compose.yml` (postgres+pgvector, temporal, minio), `.env.example`, `Makefile`, lockfiles, `.gitignore`.
- [x] **P0-T2** Django project + apps (`tenancy, projects, workitems, registry, ledger, runs, gates, integrations`). Wire DRF, settings, ASGI.
- [x] **P0-T3** Models + migrations for all Phase 0 entities (spec §1). Add `tenant_id` to every table.
- [x] **P0-T4** **RLS:** create non-superuser app DB role; RLS policies on every table; middleware/util that sets `app.tenant_id` per request and per Temporal activity. Test: tenant B cannot read tenant A's rows.
- [x] **P0-T5** Platform-State MCP server (spec §2): all tools, tenant-scoped, stdio. Integration test each tool.
- [x] **P0-T6** ExecutionDriver interface + ClaudeDriver (planning) using `claude-agent-sdk` (spec §3). `run_build_task` raises NotImplementedError for now.
- [x] **P0-T7** Manifest Composer (spec §4): get_context → AGENTS.md with section order + token budget.
- [x] **P0-T8** Temporal `AgentRunWorkflow` + activities (spec §5): compose → execute → gate(wait signal) → publish/transition. Idempotent by run_id.
- [x] **P0-T9** Gate/Approval (spec §6): Approval model, signal on decision, role check.
- [x] **P0-T10a** **Rules migration** (`/legacy_suite/rules/` → `backend/manifest/rules/` + enforcement hooks) per `docs/AGENT_MIGRATION_SPEC.md` §4: distill prompt-rules into the manifest `# Rules` section; wire platform-enforced rules (8, 11, 12, 5) into the workflow.
- [x] **P0-T10b** **AgentSpec + command/settings migration scaffolding** per spec §5: seed AgentSpec registry from `/legacy_suite/settings.json`; build the phase-trigger pattern that replaces command files; normalize agent keys; fix known v6 inconsistencies.
- [x] **P0-T10c** Migrate agents **01, 02, 03, 04** per `AGENT_MIGRATION_SPEC.md` §2–§3 + §8 checklist. **Preserve reasoning verbatim; reroute every data reference (incl. inside Process steps); pass the §8 reference sweep** (no leftover local paths). Store in `/agents/<key>/agent.md`; register AgentSpecs; add per-agent run tests that read inputs from the platform.
- [x] **P0-T11** REST API: create tenant/project/profile, list/trigger work items, list runs/artifacts/events, decide gates.
- [x] **P0-T12** Minimal React UI: project create, Project Profile editor, phase console (trigger + run timeline), gate-approval screen, artifact view, traceability view.
- [x] **P0-T13** Seed script (demo tenant/project/profile/agentspecs) + `make dev`.
- [x] **P0-T14** **Acceptance slice** (spec §8): ideation→requirements→prd→architecture run end-to-end, gated, `sor=internal`, traceability shown, RLS verified. Demo + tests green.

## Phase 1 — Atlassian SoR + Brownfield-lite  ✅ COMPLETE
- [x] Generate `docs/PHASE_1_BUILD_SPEC.md` from the blueprint.
- [x] DocStore connector (Confluence read/write; headless API-token REST per decision D1 — Rovo MCP stays the optional agent-side transport).
- [x] TaskTracker connector (Jira: epics/stories/subtasks, transitions, comments, search; headless API-token REST). Sprints deferred (decision D3).
- [x] Capability abstraction layer (`docstore.*`, `tasktracker.*`) + connector selection per tenant (`get_capability` over IntegrationConnection; demo tenant connections seeded).
- [x] Artifact publish path to live SoR (gate→publish→pointer+version) — DocStore/Confluence; type→capability resolution; idempotent; internal fallback. (Backlog→Jira via reconciliation, next.)
- [x] Traceability viewer (requirement→PRD→epic→story) — `GET /projects/{id}/traceability/` (nodes+edges with SoR deep-links) + React lineage tree.
- [x] Reconciliation service (proposed→accepted; idempotent, no dup of existing issues) — `reconcile_backlog` into Jira; external_ref idempotency + register-don't-recreate; epic→story→task order. WorkItem gained title/description/external_ref.
- [x] **Migrate agent 06 Task Breakdown** — reasoning verbatim, §8-clean; output rerouted to proposed WorkItems (new `create_work_item` MCP tool) + `backlog`/`sprint_plan`/`definition_of_done`/`dependency_map` artifacts; reconciliation publishes to Jira on approval. (Jira sprints deferred — D3.)
- [x] Brownfield-lite onboarding (single-repo): register-don't-recreate against Atlassian + **static-file extraction** (Word/PDF/Excel → internal artifacts, provenance, review gate). SourceDocument model (RLS) + extraction adapters + onboarding service + API; static-file adopt is product_owner-gated.
- [x] Rate governor (queue/backoff/cache) v1 — per-`(tenant, capability)` token bucket + 429/5xx full-jitter backoff + short-TTL read cache (GET/HEAD), injected at connector-build time so it's the single choke point all connector I/O routes through; settings-tunable; de-flakes live Atlassian runs.
- [x] Slice: greenfield PRD→Confluence + backlog→Jira + implement-by-issue-key; brownfield onboard from Word/Excel or existing Jira. `tests/test_acceptance_phase1.py` — **live greenfield** (PRD publishes to Confluence only on the post-gate publish step, read-through + idempotent re-publish; proposed backlog reconciles into Jira epics/stories, idempotent; live get-issue-by-key + transition round-trips to the ledger; traceability API shows requirements→PRD→backlog with Confluence deep-link; RLS isolation) and **offline brownfield** (Word PRD + Excel backlog → gated adoption with provenance; register-don't-recreate, no duplicates). Self-cleaning; skips greenfield without creds. **Phase 1 complete.**

## Phase 2 — Build Execution  ← CURRENT
- [x] Generate `docs/PHASE_2_BUILD_SPEC.md` from the blueprint. **Execution model decided (D1–D10):** **local-companion runner only** (developer's machine), **managed git-worktree** edit surface (run/test locally before PR), platform owns the PR/merge SoR surface, **split gate roles** (07→`tech_lead`, 08/merge→`reviewer`), **light repo-per-WorkItem** multi-repo now (full multi-repo → P4).
- [x] CodeHost connector (GitHub: PR/branch/status/comment/merge/file; headless REST per D1; idempotent `open_pull_request` register-don't-recreate; rate-governed) + `IntegrationConnection(codehost→github)` seeded. Generic urllib transport lifted into `integrations/transport.py` (shared, governor stays connector-agnostic). Unit tests via fake transport + per-tenant selection + a live round-trip (skips without creds). Webhooks land in the takeover/reconcile task.
- [x] Data-model deltas: `Repository` extended (name/default_base/connector/scopes/provenance — N per project); `RunnerEnrollment` (runs) + `WebhookDelivery` (integrations, dedup unique per tenant) added, each with its own RLS migration (forced + tenant_isolation, verified). `WorkItem.repo`/`takeover_flag` already in the P0 scaffold (no migration); `code`/`code_review`/`test_report` are free-text artifact types (no migration). Tests incl. DB-level RLS isolation of the new tables.
- [x] Local-companion runner: enrollment/auth (`RunnerEnrollment` + `enroll`/`authenticate`/`revoke`, one-time token, only its hash stored; `/api/runners/` + Runner-token auth); managed **git-worktree** provisioning (`runner/companion/worktree.py` — clean `feature/<key>` off base, `.sdlc/` excluded; secrets-as-env injection + provisioning-command hook); **remote Platform-State serving** (`/api/runner/state/<tool>/` build-tool allowlist, **tenant bound server-side from the enrollment**, no DB on the dev machine; `RemoteStateClient` + `state_mcp` proxy); `ClaudeDriver.run_build_task` scoped to the worktree (manifest→`.sdlc/AGENTS.md`, FS/Bash + platform-state tools, **no CodeHost/network** per PG12). Tests: enrollment/auth, remote-state tenant binding + cross-tenant isolation + allowlist, worktree lifecycle, build orchestration, driver build path.
- [x] Temporal `BuildWorkflow` saga: dispatch-to-companion (assemble BuildTask payload, fetch/report API) → **await `build_reported` signal** (offline runner → **takeover** on timeout) → open draft PR (CodeHost) → **merge gate** (reviewer Approval, `gate_decision`) → merge (gated SoR write). Activities idempotent by run_id; `ActivityError` → **compensation** (run failed, WorkItem→in_progress); registered on the worker alongside `AgentRunWorkflow`. `trigger_build` entry. Tests: activity cores + report API (deterministic) and **two live Temporal runs** (happy path + takeover).
- [x] Build phases (implementation/review/test) with the 07↔08 remediation loop preserved — `BuildWorkflow` now runs **open PR → review → remediate → re-review until no blocking findings → merge gate**. `run_code_review` records a `code_review` artifact (+TraceEdge→code) and reconciles **remediation child WorkItems** (REM-C/REM-W open/close; REM-S non-blocking); `dispatch_remediation` briefs the open items back to the companion (07 remediation mode); cycle-capped (`max_remediation_cycles`) → escalate. Review provider is a seam (`get_review_provider`/`set_review_provider`) — a no-findings stub now, the migrated **08** plugs in next. Tests: review core (open→resolve, suggestions non-blocking, brief) + a **live Temporal remediation loop** (critical → remediate → clean → merge). Tests run in the companion build (≥90% coverage); a failed report fails the build.
- [ ] **Migrate agents 07 Implementation + 08 Code Review** (preserve REM-C/REM-W remediation loop as child WorkItems + TraceEdges; migration spec §6; gate roles `tech_lead`/`reviewer`).
- [ ] **Migrate agents 11 CI/CD + 12 Deployment** (pipeline + release artifacts) — **after** the 07/08 core (D5; placement adjustable).
- [ ] Secret scanning + egress allowlist + per-phase tool allowlist (injection guardrails v1; developer-trusted runner — full sandbox is P5).
- [ ] Human takeover + signed Git-webhook commit reconciliation (the primary collaboration path in companion mode).
- [ ] Slice: WorkItem→worktree→local build→PR→CI→review→remediation→**reviewer merge gate**→merge, with a recovered mid-run failure; webhook reconcile of a human commit; light multi-repo (two repos, one project).

## Phase 3 — Design & Test Loops
- [ ] DesignSource (Figma read; write beta) + Design-System/tokens artifact + Code Connect.
- [ ] **Migrate agent 05 UX Design** (→ Figma / HTML wireframes; read client-designed Figma as SoR).
- [ ] a11y (WCAG) gate; design↔code round-trip; responsive; per-tenant theming.
- [ ] TestMgmt (Xray) tests + result import; NFR tests; test-impact selection; ephemeral preview env per PR; flaky quarantine; defect loopback.
- [ ] **Migrate agents 09 Testing + 09b Test Automation** (TC-XXX → Xray; Playwright-MCP locator discovery + Page Object Model preserved; spec §6).
- [ ] **Migrate agent 10 Security** (findings + SBOM; SOTA benchmark — hold its quality bar). *(Adjustable: move to P2 for pre-merge gating.)*
- [ ] Slice: implementation reads current Figma; results→Xray; failing test→linked bug.

## Phase 4 — Brownfield-Full & Multi-Repo
- [ ] CodeIntel (Repowise) per repo + Knowledge Index; **migrate agent 00c Intelligent Context Extractor** (MCP :7337, 8 tools).
- [ ] **Migrate agent 00 Onboarding (full)** (discover→register→reconcile→gap-fill across all SoRs + intel; gap report).
- [ ] **Migrate agent 00b Context Bridge → API-Contract artifact** (registry-based, not a copied file).
- [ ] **Agent 00d Snapshot:** migrate only unique reconciliation logic, else mark retired (continuity now = DB + Temporal resumable runs).
- [ ] API-Contract artifact + cross-repo DAG edges.
- [ ] Multi-repo project model (one project, N repos, per-repo manifest).
- [ ] Live drift detection (webhooks→ledger→drift gates); change-impact via traceability.
- [ ] Slice: onboard split FE/BE, resume mid-pipeline, contract change → drift gates.

## Phase 5 — Enterprise Hardening + Cloud Migration
- [ ] RBAC + segregation of duties; secrets vault + token broker.
- [ ] Prompt-injection hardening; immutable audit + compliance evidence; data-governance/ZDR/model routing; GDPR erasure.
- [ ] Platform DevOps: CI/CD, IaC, DR/backups, OTel observability; cost metering/quotas.
- [ ] Eval/quality harness (gate AgentSpec promotion on regression).
- [ ] **Cloud migration:** cloud runner fleet (autoscaling) + sandbox hardening (gVisor/Firecracker, egress allowlist); managed Postgres/Temporal/object store.
- [ ] Slice: SOC2-style walkthrough; run in cloud.

## Phase 6 — Engine Pluggability & Scale
- [ ] CodexDriver + CopilotDriver; AGENTS.md routing; per-phase engine/model selection + override.
- [ ] DAG parallelism + concurrency limits.
- [ ] Notification plane (Slack/Teams/email); PM/PO dashboards (burn-up, traceability, release notes).
- [ ] **Build agents 13 Monitoring + 14 Retrospective** (net-new — these never existed in v6; author them to the suite skeleton + migration-spec I/O contract).
- [ ] Slice: same project on a 2nd engine; concurrent features through different phases.
