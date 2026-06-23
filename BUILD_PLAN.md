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

## Phase 0 — Platform Spine  ← START HERE
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
- [ ] **P0-T13** Seed script (demo tenant/project/profile/agentspecs) + `make dev`.
- [ ] **P0-T14** **Acceptance slice** (spec §8): ideation→requirements→prd→architecture run end-to-end, gated, `sor=internal`, traceability shown, RLS verified. Demo + tests green.

## Phase 1 — Atlassian SoR + Brownfield-lite
- [ ] Generate `docs/PHASE_1_BUILD_SPEC.md` from the blueprint.
- [ ] DocStore connector (Confluence read/write via Atlassian Rovo MCP, headless auth).
- [ ] TaskTracker connector (Jira: epics/stories/sprints, transitions, comments).
- [ ] Capability abstraction layer (`docstore.*`, `tasktracker.*`) + connector selection per tenant.
- [ ] Artifact publish path to live SoR (gate→publish→pointer+version).
- [ ] Traceability viewer (requirement→PRD→epic→story).
- [ ] Reconciliation service (proposed→accepted; idempotent, no dup of existing issues).
- [ ] **Migrate agent 06 Task Breakdown** (→ Jira epics/stories/sprints) per migration spec.
- [ ] Brownfield-lite onboarding (single-repo): register-don't-recreate against Atlassian + **static-file extraction** (Word/PDF/Excel → internal artifacts, provenance, review gate). *(Delivers the "onboard existing project with local docs OR MCP tool" path for single-repo.)*
- [ ] Rate governor (queue/backoff/cache) v1.
- [ ] Slice: greenfield PRD→Confluence + backlog→Jira + implement-by-issue-key; brownfield onboard from Word/Excel or existing Jira.

## Phase 2 — Build Execution
- [ ] CodeHost connector (GitHub: branches/PRs/status/webhooks).
- [ ] Build runners + provisioning (toolchains, private registries, test DB, secrets inject); ClaudeDriver `run_build_task`.
- [ ] Temporal build sagas (long-running, compensation, dead-letter).
- [ ] Build phases (implementation/review/test) with the 07↔08 remediation loop preserved.
- [ ] **Migrate agents 07 Implementation + 08 Code Review** (preserve REM-C/REM-W remediation loop as WorkItem sub-tasks + TraceEdges; migration spec §6).
- [ ] **Migrate agents 11 CI/CD + 12 Deployment** (pipeline + release artifacts). *(See spec §7 note — 11/12 placement is adjustable.)*
- [ ] Secret scanning + egress allowlist (initial injection guardrails).
- [ ] Human takeover + Git-webhook commit reconciliation.
- [ ] Slice: WorkItem→PR→CI with a recovered mid-run failure.

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
