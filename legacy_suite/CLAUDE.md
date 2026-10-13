> **⚠️ MANDATORY — READ RULES BEFORE THIS FILE:** Before reading any section below, load `rules/RULE-BEHAVIOR.md` then `rules/RULE-EXECUTION.md` in full. Apply all rules from both files to every action taken in this project. This instruction overrides all other context.

<!-- SESSION SNAPSHOT REFERENCE — auto-updated by /sdlc:snapshot -->
<!-- Latest snapshot: [YYYY-MM-DD HH:MM] — Phase: [N] — Next: [command] -->
<!-- To resume: say "Load SESSION-SNAPSHOT.md and continue" -->

# CLAUDE.md — AI First SDLC Suite · Project Context

> **Priority:** Highest. Overrides Claude's built-in defaults for this project.

> **Agent Behavior Rules:** All phase agents (01–14) and entry agents (00–00d) are governed by two rule files in `rules/`:
> - `rules/RULE-BEHAVIOR.md` — Pre-execution rules
> - `rules/RULE-EXECUTION.md` — Execution rules
> Both rule files are pre-loaded via the mandatory preamble above. All agents apply these rules from the moment they read this file — no per-agent re-reading required.
> **Do not modify either rule file without team review — changes affect all SDLC phase agents.**
> **You Must:** With each SDLC phase completion or modification made during execution, update this CLAUDE.md file accordingly so it remains perfectly aligned. Any `[TBD]` or placeholder value determined by an agent during a phase **must** be written back here before the Human Gate (Rule 12).

---

## ⚙️ Suite Setup Status

<!-- Fill this table before running any agent. Agents use it to skip setup steps. -->

| Tool | Status | Notes |
|------|--------|-------|
| Codebase Intelligence Engine | `[ ] Not run / [ ] Indexed / [ ] MCP Active` | Dashboard at [URL if running] |
| Claude Code | `[x] Active` | Primary AI coding assistant |
| Context Bridge | `[ ] Not applicable — single repo / [ ] Exported / [ ] Imported` | N/A for single-repo projects |

---

## Project Identity

**Project Name:** [Your Project Name]

**Project Type:**
```
[ ] Greenfield — new project from scratch → start with /sdlc:ideate
[ ] Brownfield / Midline Entry — existing project, resuming from a specific phase → start with /sdlc:analyze then /sdlc:onboard
```

**Repository Architecture:**
```
[ ] Single Repo (Monorepo)
[ ] Multi-Repo (specify below)
    Repos: [list all repos and their roles — e.g., frontend, backend, mobile]
```

**Current Phase:** [Phase Name — auto-updated by agents]

**Repository URL(s):**
- Primary: [repo URL]
- [Additional repos if multi-repo]

**Start Date:** [YYYY-MM-DD]
**Target Completion:** [YYYY-MM-DD — milestone description]

---

## Project Description

<!-- 3–5 sentences covering: what the product does, who it serves, domain, and scale.
     Agents use this to apply correct domain reasoning and tailor outputs appropriately.
     Be specific — generic descriptions produce generic outputs. -->

> [Write a concrete product description here. Include: the domain (e.g., healthcare, logistics, SaaS),
> the primary user action the product enables, the business model context, and approximate user scale.
> Example: "MedSlot is a web-first healthcare appointment platform for the Indian market enabling
> patients to book time-slotted consultations and doctors to manage availability, with 200–800 active users."]

---

## Target Users

<!-- Define the 1–3 primary user roles. Agents use this for UX, requirements, and testing.
     For each role: who they are, their technical proficiency, and their critical use cases. -->

**[Role 1 — e.g., End User / Patient / Customer / Buyer]:**
[2–3 sentences: who they are, what they need from the product, what frustrates them]

**[Role 2 — e.g., Admin / Doctor / Seller / Manager]:**
[2–3 sentences: who they are, workflow needs, technical proficiency level]

**User Scale:** [N–M active users] ([market segment — e.g., mid-market / enterprise / consumer])

---

## Technology Stack

### Current Stack

<!-- For brownfield projects: fill in what is ACTUALLY RUNNING TODAY.
     For greenfield projects: this section may start empty and be filled by /sdlc:architecture.
     Leave [TBD] for layers not yet determined — agents will resolve them at the appropriate phase. -->

| Layer | Technology | Version | Status / Notes |
|-------|-----------|---------|----------------|
| Frontend Language | [e.g., TypeScript / JavaScript] | [version] | [Active / TBD] |
| Frontend Framework | [e.g., Next.js / React / Vue] | [version] | [Active / TBD] |
| UI Library | [e.g., Tailwind CSS / MUI] | [version] | [Active / TBD] |
| State Management | [TBD] | [TBD] | Determined by Architecture Agent — Phase 4 |
| Backend Language | [e.g., Python / Node.js / Go] | [version] | [Active / TBD] |
| Backend Framework | [e.g., Django + DRF / FastAPI / Express] | [version] | [Active / TBD] |
| Database | [e.g., PostgreSQL / MongoDB] | [version] | [Active / TBD] |
| Cache | [TBD] | [TBD] | Determined by Architecture Agent — Phase 4 |
| Object Storage | [TBD] | [TBD] | Determined by Architecture Agent — Phase 4 |
| CDN | [TBD] | [TBD] | Determined by Architecture Agent — Phase 4 |
| Cloud Provider | [TBD] | — | Determined by Architecture Agent — Phase 4 |
| Compute | [TBD] | — | Determined by Architecture Agent — Phase 4 |
| Email / Notifications | [TBD] | [TBD] | Determined by Architecture Agent — Phase 4 |
| Payment Gateway | [TBD — or N/A] | — | [If applicable] |
| CI/CD | [TBD] | — | Determined by CI/CD Agent — Phase 11 |

> **For brownfield onboarding:** Populate from `package.json`, `requirements.txt`, `pom.xml`, `go.mod`, or equivalent dependency files. Mark status as `Active` for running tech, `Planned` for intended changes. The Codebase Intelligence Agent (`/sdlc:analyze`) will verify and supplement this table from the actual codebase.

---

## Repository Structure

```
[Project root]/
├── [primary source directory]/      ← [description of what lives here]
│   ├── [key subdirectory]/          ← [DONE / IN PROGRESS / NOT STARTED]
│   └── [key subdirectory]/
├── [secondary source directory]/    ← [description]
│   ├── [key subdirectory]/
│   └── [key subdirectory]/
├── [config files — e.g., docker-compose.yml, .github/]
└── CLAUDE.md
```

<!-- For brownfield projects: fill in the actual structure observed.
     Mark each top-level directory with DONE / IN PROGRESS / NOT STARTED.
     The Codebase Intelligence Agent will enrich this with hotspot and architecture data.
     For greenfield projects: leave [TBD — to be scaffolded by /sdlc:architecture]. -->

---

## Key Commands

```bash
# ── [Frontend / Primary Application] ──────────────────────
# Install dependencies
[command]

# Start dev server
[command]         # → http://localhost:[port]

# Run unit tests
[command]

# Run tests with coverage
[command]

# Run linter
[command]

# Build for production
[command]

# ── [Backend / API] ────────────────────────────────────────
# Install dependencies
[command]

# Start dev server
[command]         # → http://localhost:[port]

# Run migrations (if applicable)
[command]

# Create/apply new migration (if applicable)
[command]

# Run tests
[command]

# Run tests with coverage
[command]

# Format code
[command]

# ── Full stack local (Docker Compose) ──────────────────────
[command]         # Start all services

# ── Deploy ─────────────────────────────────────────────────
# Staging
[command]

# Production
[command]         # Manual approval required
```

<!-- Agents fill in [TBD] entries as they work. Key Commands filled by:
     Architecture Agent (Phase 4), CI/CD Agent (Phase 11).
     For brownfield: extract from existing Makefile, package.json scripts, README, or Dockerfile. -->

---

## Codebase Intelligence

<!-- This section is auto-populated by /sdlc:analyze (Intelligent Context Extractor).
     Do NOT fill this manually — run /sdlc:analyze to generate accurate intelligence.
     For greenfield projects with no existing code: this section is N/A and can be removed. -->

```
Intelligence Engine Status: [ ] Not run / [ ] Indexed YYYY-MM-DD / [ ] MCP Active
Dashboard: [URL if running — http://localhost:[port]]

Intelligence Layers:
  Dependency Graph:        [ ] Available — [N] nodes, [N] edges
  Git Analytics:           [ ] Available — [N] commits analyzed
  Auto-Generated Docs:     [ ] Available — [N] modules documented
  Architectural Decisions: [ ] Available — [N] decisions found

Key Findings (auto-filled by /sdlc:analyze):
  Hotspots:        [paths and commit frequencies — e.g., src/payments/processor.ts — 47 commits/month]
  Dead Code:       [N] files / symbols flagged — see docs/intelligence/DEAD-CODE-REPORT.md
  Bus Factor Risk: [N] files with single-owner concentration
  Architecture Communities: [N] major clusters identified

⚠️ HOTSPOT WARNINGS (auto-filled — pay attention before modifying these files):
  [path/to/hotspot.ext] — [N] commits/[period] — [risk description]
  [path/to/hotspot.ext] — [co-changes with: other/file.ext]
```

---

## Cross-Repository Context

<!-- This section is populated by /sdlc:context-bridge (Import mode).
     Applicable when this repository depends on context from another repo
     (e.g., this is the backend and the frontend is in a separate repo).
     For single-repo or greenfield projects where context-bridge is not used: REMOVE THIS SECTION. -->

**This repository is:** [backend / mobile / service-name]
**It depends on context from:** [source repo name and location]
**Context file:** `CONTEXT-BRIDGE.md` (in root of this repository — generated by /sdlc:context-bridge)
**Last Bridge Sync:** [YYYY-MM-DD] — Contract version [vX.Y.Z]

> **IMPORTANT for all agents:** Before acting on any API endpoint, data model, or business rule,
> read `CONTEXT-BRIDGE.md` in addition to this CLAUDE.md. The API contract in CONTEXT-BRIDGE.md
> is the authoritative specification — it supersedes any local assumptions. Do NOT invent API
> endpoints, field names, or error codes not present in the contract.

---

## Architecture Decisions

<!-- This section is populated by the Architecture Agent (Phase 4) and updated by all subsequent agents.
     Each decision that affects downstream phase choices should be captured here or in docs/design/adrs/.
     For brownfield projects: populate from existing ADRs, architecture documents, or README. -->

Key decisions already made:
- [Decision 1: e.g., "Modular monolith chosen over microservices — team size and scale do not justify distributed complexity"]
- [Decision 2: e.g., "JWT authentication — 15min access token, 7-day refresh token"]
- [Decision N: e.g., "UUID primary keys throughout — no integer auto-increment IDs"]

[Link to docs/design/ARCHITECTURE.md once created]
[Link to docs/design/adrs/ for Architecture Decision Records]

> **For brownfield projects:** The Codebase Intelligence Agent will auto-discover existing architectural
> decisions from git history and code comments. Review `docs/intelligence/ARCHITECTURE-DECISIONS-REGISTER.md`
> after running /sdlc:analyze to seed this section.

---

## Non-Functional Requirements

| Requirement | Target | Current |
|-------------|--------|---------|
| API Response Time (P95) | [< Nms] | TO BE MEASURED |
| Page Load — LCP (primary user flow) | [< Xs] | TO BE MEASURED |
| Uptime SLA | [99.X%] | TO BE MEASURED |
| Concurrent Users | [N] | TO BE LOAD TESTED |
| [Domain-specific NFR — e.g., Transaction Processing Time] | [target] | TO BE MEASURED |
| [Domain-specific NFR — e.g., File Upload Limit] | [target] | TO BE MEASURED |
| Test Coverage Minimum | [80% / 90%] | [N]% current |
| Mobile Responsiveness | [375px minimum] | TO BE VERIFIED |

<!-- Quantified targets are required — "fast" or "acceptable" are not targets.
     Source targets from the client brief, industry benchmarks, or SLA commitments.
     The Testing Agent (Phase 9) fills the "Current" column with measured values.
     The Monitoring Agent (Phase 13) derives SLOs directly from this table. -->

---

## Constraints

- **Budget:** [$/month cloud budget or "Not defined"]
- **Timeline:** [target release date] — [scope description]
- **Compliance:** [applicable standards — e.g., HIPAA, PCI-DSS, GDPR, SOC 2, or "None currently required"]
- **Team Size:** [N developers — role breakdown, e.g., 1 full-stack lead, 1 frontend, 1 backend]
- **Payment Provider:** [e.g., Stripe / Razorpay / N/A — card data never stored on our servers]
- **Authentication:** [e.g., Email + password with JWT / OAuth / SSO]
- **Parallel operation required:** [Yes — legacy system must remain live during migration / No — greenfield]
- **Rollback window:** [N days post-release to keep previous version available]
- **Other constraints:** [team skills, regulatory geography, infrastructure vendor lock-in, etc.]

---

## Coding Standards

<!-- These standards are enforced in CI and reviewed in Phase 8 (Code Review).
     Agents reference this section to determine linting, formatting, and review criteria. -->

- **Style Guide (Frontend):** [e.g., Airbnb TypeScript ESLint config / Standard / None yet]
- **Style Guide (Backend):** [e.g., PEP 8 + Black + isort / Google Java Style / Standard Go]
- **Commit Convention:** [e.g., Conventional Commits (feat:, fix:, docs:, chore:) / None]
- **Branch Strategy:** [e.g., feature/xxx → develop → main / trunk-based / gitflow]
- **PR Requirements:** [e.g., 1 peer approval + CI green / 2 approvals for main]
- **Test Coverage Minimum:** [80% / 90%] for all new code
- **Code Review:** Mandatory — no direct commits to [develop / main]
- **API Style:** [e.g., RESTful, versioned at /api/v1/, snake_case JSON / GraphQL / gRPC]
- **Domain-specific rule 1:** [e.g., "No raw SQL — use ORM exclusively"]
- **Domain-specific rule 2:** [e.g., "No PII in application logs — mask before logging"]

---

## Phase Artifacts Index

<!-- Phase statuses:
     [ ] Pending — not started
     [~] In Progress — actively being worked
     [x] Complete — approved at Human Gate
     [S] Skipped — intentionally skipped with reason
     [P] Partial — exists but not in SDLC-standard format (brownfield onboarding state) -->

| Phase | Status | Primary Artifact | Last Updated |
|-------|--------|-----------------|--------------|
| 0a. Codebase Intelligence | `[ ] Pending` | `docs/intelligence/CODEBASE-INTELLIGENCE.md` | — |
| 0b. Onboarding | `[ ] Pending` | `ONBOARDING-REPORT.md` | — |
| 1. Ideation | `[ ] Pending` | `docs/ideation/PROJECT-CONCEPT.md` | — |
| 2. Requirements | `[ ] Pending` | `docs/requirements/REQUIREMENTS.md` | — |
| 3. PRD | `[ ] Pending` | `docs/prd/PRD.md` | — |
| 4. Architecture | `[ ] Pending` | `docs/design/ARCHITECTURE.md` | — |
| 5. UX Design | `[ ] Pending` | `docs/ux/USER-JOURNEYS.md` | — |
| 6. Task Breakdown | `[ ] Pending` | `docs/planning/TASKS.md` | — |
| 7. Implementation | `[ ] Pending` | `src/` | — |
| 8. Code Review | `[ ] Pending` | PRs in repository | — |
| 9. Testing | `[ ] Pending` | `docs/qa/TEST-RESULTS.md` | — |
| 10. Security | `[ ] Pending` | `docs/security/SECURITY-REVIEW.md` | — |
| 11. CI/CD | `[ ] Pending` | `.github/workflows/` | — |
| 12. Deployment | `[ ] Pending` | `docs/releases/` | — |
| 13. Monitoring | `[ ] Pending` | `docs/ops/MONITORING-SETUP.md` | — |
| 14. Retrospective | `[ ] Pending` | `docs/retros/` | — |

<!-- For brownfield onboarding: the Onboarding Agent updates this table with accurate statuses
     after the Discovery Report is confirmed. Agents read this table before running to determine
     whether their prerequisite phases are complete. -->

---

## Open Questions

| Question | Owner | Due Date | Status |
|----------|-------|----------|--------|
| [Question requiring human decision before it affects a phase] | [Role] | [YYYY-MM-DD] | Open |
| [Question] | [Role] | [YYYY-MM-DD] | Open |

---

## Human Gates Log

> Every phase requires explicit human approval (reply: `APPROVED`) before the next phase begins.
> Agents write approval here automatically after receiving APPROVED. Do not edit manually.

- The human is monitoring Claude Code in an IDE. They can see everything. They will catch mistakes. The agent's job is to **minimise the mistakes they need to catch** while maximising useful work.
- Unlimited AI stamina, limited human attention. Loop on hard problems — don't loop on the wrong problem.

| Phase | Status | Approved By | Date | Conditions |
|-------|--------|-------------|------|------------|
| [Phase N — Name] | ⏳ Pending | — | — | — |

---

## Important Context for Agents

<!-- This section is the most-read section by every agent. Keep it accurate and current.
     For brownfield: fill this in after running /sdlc:analyze and /sdlc:onboard.
     This section overrides general assumptions — agents must read it before executing any step. -->

### What Is Done (Do Not Redo)

<!-- List completed, approved work that must NOT be regenerated or modified.
     Be specific — agents need to know exactly what to skip. -->

- [e.g., "Phases 1–4 complete and approved. Do NOT re-run ideation, requirements, PRD, or architecture phases."]
- [e.g., "Products app: CRUD, search, and categories are complete and deployed to staging."]
- [e.g., "Authentication: JWT with 15-min access token / 7-day refresh token is deployed and live."]

### What Is In Progress

<!-- What is actively being built or is partially complete. Agents pick up from here. -->

- [e.g., "Cart app: add/remove operations working. Cart totals calculation in progress."]
- [e.g., "Sprint N of M. Next task: [TASK-XXX — description]."]

### What Is NOT Started

<!-- What still needs to be built. Agents must not assume these exist. -->

- [e.g., "Orders app, payments integration, checkout page — not started."]

### Resume Instructions

<!-- The single most important directive for implementation agents.
     Auto-updated by the Onboarding Agent and Implementation Agent. -->

**Resume from:** [exact command and task — e.g., "/sdlc:implement → next task is TASK-048: POST /api/orders endpoint"]

### Platform & Layout Philosophy

<!-- Agents reference this for every UX, implementation, and testing decision. -->

[e.g., "Web-first application. Primary experience is desktop at 1280px+. All screens must also work
at 375px minimum. Do NOT default to mobile-first CSS. Base (unprefixed) Tailwind styles are desktop;
sm: and md: adapt downward."]

### Architecture Constraints (Locked)

<!-- Decisions the team has locked and that agents must not deviate from. -->

- [e.g., "Modular monolith — not microservices. Do not introduce service boundaries without raising an ADR."]
- [e.g., "UUID primary keys on all models — no integer auto-increment IDs."]
- [e.g., "No raw SQL — use ORM exclusively unless the query cannot be expressed in ORM."]
- [e.g., "No PII in application logs — mask email, phone, and health data before logging."]

### Hotspot Warnings (Auto-Filled by /sdlc:analyze)

<!-- COPY FROM Codebase Intelligence section above after /sdlc:analyze runs. -->

⚠️ **High-Churn Files — extra care before modifying:**
- [path/to/file.ext] — [N commits/month] — [risk note]

---

*This file is the source of truth for the project. Update it whenever architectural decisions change,
new decisions are made, or phase completions occur.*
*It is a living document — accuracy matters more than completeness.*
