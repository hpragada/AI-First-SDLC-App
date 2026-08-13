# Task Backlog — Web Accessibility QA (POC + Phase 2)

**Total Tasks:** 31 (QA‑01 … QA‑24, plus QA‑02a, QA‑10a, QA‑11a, QA‑11b, QA‑12a, QA‑15a, QA‑23a)
**Estimates:** deferred by team decision — this backlog carries detail + dependencies, not story points or sprints.

> **Read `RESEARCH_CORRECTIONS.md` first.** A source-level check of the platform (2026‑08‑12) found that several things the research reports said "already exist" do not — most importantly, **the testing agent has never run an accessibility scan**. Seven tasks were added and five re-scoped as a result. Every affected block below says so in its Description. Building to an uncorrected block will produce a task that passes its tests and demonstrates nothing.

**Sizing assumption (team decision, 2026‑08‑12):** design for roughly **10 screens per run and 50 screens per app**, with a configurable cap on judgments per run and a run that **pauses and resumes** at the cap rather than failing. A wrong estimate then costs a slower first audit, never a lost run.

> **How to read a task.** Each task block is written so you can implement it by reading that block alone. The **Description** starts with one plain sentence saying what the task delivers and why, then "In build terms:" gives the concrete behaviour, inputs/outputs, states, and edge cases, then the **Acceptance Criteria** are hand‑checkable given/when/then statements. If a block ever leaves you guessing how to start, that's a bug in the block — raise it.

## Status legend
⬜ Pending · 🟡 In Progress · 🟢 Done · 🔴 Blocked

## Epics in this backlog
- **E1 — Ask the platform "is this accessible?" (the AI checking capability)**
- **E2 — Ground the AI in the real WCAG 2.2 rules**
- **E‑COST — Keep AI findings trustworthy and affordable**
- **E‑GATE — Decide pass/fail with a clear accessibility gate**
- **E‑EVAL — Prove the AI is accurate (Edvensoft‑internal only)**
- **E5 — Test every screen for accessibility (rules + AI)**
- **E9 — Turn accessibility findings into tracked, self‑closing fixes**
- **E‑BF — Audit an already‑built (onboarded) app for accessibility**
- **E10 — Test keyboard & interaction journeys with an AI agent (Phase 2)**
- **E11 — Human review & a signed conformance report (Phase 2)**

---

## EPIC E1 — Ask the platform "is this accessible?" (the AI checking capability)
This epic gives the platform a single, model‑agnostic way to ask an AI to judge the accessibility things the rule scanner can't — is the alt text meaningful, is this really a button, is meaning carried by colour alone, does the label match what a screen reader says. Everything else in the QA build calls this capability.

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| QA‑01 | Create the `a11yai` capability front door | Backend | — | 🟢 |
| QA‑02 | Judgment dispatch, cache & audit behind `a11yai` | Backend | QA‑01 | 🟢 |
| QA‑02a | The `09c_a11y_judge` agent + `record_a11y_finding` tool | Agent + Backend | QA‑02, QA‑04 | ⬜ |
| QA‑03 | Build the four accessibility AI checkers | Backend (AI) | QA‑01, QA‑02, QA‑02a, QA‑04 | ⬜ |

**QA‑01 — Create the `a11yai` capability front door** *(critical path)*
- **Epic:** E1 · **Story:** US‑A1 · **Type:** Backend · **Status:** 🟢 Done (2026‑08‑12) · **Depends On:** — · **Blocks:** QA‑02, QA‑03
- **Description:** Right now nothing in the platform can ask an AI "is this screen accessible?", and we want that request to work the same way as every other integration — through a named capability so the AI model underneath can be swapped without touching the callers. This task creates that front door, called `a11yai`. In build terms: add a new capability contract `a11yai` alongside the existing ones in `backend/integrations/capabilities.py`, with four methods — `check_alt`, `check_semantics`, `check_color`, `check_label` — each accepting the element / screenshot / surrounding context it needs and returning **one standard result object**: the WCAG criterion it judged, a verdict (`pass` / `fail` / `uncertain`), a confidence from 0 to 1, the evidence it used, and a suggested fix. Wire it so `get_capability(tenant, "a11yai")` returns the right implementation for that tenant, exactly like `get_capability(tenant, "codehost")` does today, and keep it tenant‑scoped so one tenant's checks can never read another's data. Edge cases: an unconfigured tenant returns a clear "capability not configured" error, not a crash; a method called with missing inputs returns an `uncertain` result with a reason, never a partial object.
  > **Correction (R4).** `a11yai` is a capability for its **shape** — so callers never name a vendor (non‑negotiable #9) — but it must **never call a model directly**. Its implementation dispatches a constrained agent run through `ExecutionDriver` (non‑negotiable #7); that agent is built in QA‑02a. No API key is involved anywhere in this build.
  > **What this task honestly delivers:** the seam only. All four methods return a well-formed `uncertain` result until QA‑02a and QA‑03 fill them in. That is the backlog's intended dependency order, not a shortcut — but say so at review so nobody mistakes a working front door for a working check.
- **Acceptance Criteria:**
  - [x] Given a tenant with `a11yai` configured, when code calls `get_capability(tenant, "a11yai")`, then it returns a working object exposing all four methods.
  - [x] Given any of the four methods runs on a sample element, when it returns, then the result always contains criterion, verdict, confidence, evidence, and suggested_fix — no field missing.
  - [x] Given a second tenant, when it uses the capability, then it cannot read the first tenant's inputs or results (proven by an RLS test). *Partial by construction — see the scope note below.*
  - [x] Unit + integration tests cover capability resolution and the result shape, with ≥ 90% coverage on the new code.
- **Delivered (2026‑08‑12):**
  - `integrations/types.py` — `A11yCandidate` (what gets judged: selector/html/screenshot_ref/context/route, pointer-not-body) and `A11yJudgment` (the result). **Named "judgment", not "verdict" or "finding"**: `verdict` is a *field* on it, and `A11yFinding` is QA‑12a's stored ledger row — three different things needed three different names. Validates on construction (verdict in {pass,fail,uncertain}, confidence 0–1, criterion present), so a malformed judgment can never reach a reviewer. Plus `uncertain()` — the one well-formed "could not answer" result — and `A11Y_CHECKER_CRITERIA` mapping the four checkers to their criteria.
  - `integrations/capabilities.py` — the `A11yAI` Protocol (`check_alt` / `check_semantics` / `check_color` / `check_label`), carrying both guardrails in its docstring: an AI judgment never overrides a deterministic axe failure, and a check that cannot answer returns `uncertain` for human review.
  - `integrations/a11yai/builtin.py` — `BuiltinA11yAI`, tenant-bound, all four checks through one `_judge` path so the guarantees hold by construction rather than in four copies.
  - `integrations/registry.py` — `("a11yai", "builtin")` builder registered; `get_capability`'s return union widened.
  - **Connector slug is `builtin`, not a model name.** "Built-in" = the platform's own agent through the `ExecutionDriver`, exactly as `codeintel:builtin` is the platform's own analyzer. Naming it `claude` would state a vendor the driver is free to switch (#7) and would also fail `NO_SECRET_CONNECTORS`, so the connection could never report as configured. A third-party a11y-AI service becomes a second slug behind the same capability, with no caller change.
  - **Beyond the original task text, so that "configured" is a real state and not a fixture:** added `a11yai` to `apps/integrations/catalog.py` (a `no_secret` vendor — there is no model API key in this build) and to `CAPABILITIES` in `apps/integrations/services.py`, and seeded the connection in `apps/projects/seed.py` alongside `codeintel`. Without these, a tenant could only be "configured" by an ORM insert inside a test — `create_integration` would have rejected the capability outright. The existing `test_every_catalog_vendor_saves_and_is_wired` now exercises a11yai end-to-end through the real admin API for free.
  - Tests: `backend/tests/test_a11yai_capability.py` — 40 tests, **100% coverage** on `integrations/a11yai`, 99% on `integrations/types.py`. Regression: 149 + 116 passed across seed / integrations-admin / capability-registry / auth / roles / onboarding / RLS / greenfield-journey. Three assertions in existing tests were updated in the same change because they pin the seed's and catalog's contents (6 → 7 connections).
- **Team decisions taken during QA‑01 (2026‑08‑12) — these bind the later tasks:**
  - **D‑A11Y‑1 — every tenant is auto-provisioned; a11yai never appears on the Integrations page.** A capability with no credentials and no vendor choice has nothing for a human to connect, so presenting it on a "connect your tools" screen would be a control that only looks like a control. `create_tenant` now calls `provision_builtin_capabilities` (alongside `seed_agent_specs`, for the same reason), and migration `integrations/0010_a11yai_autoprovision` backfills tenants that already exist — without it, accessibility checking would work on new workspaces and be silently "not configured" on every current one, including the shared development database. Provisioning is idempotent and never overwrites a connection a tenant already has. **`codeintel` is deliberately left as-is** (credential-free but user-connected today); changing it would alter a journey currently under test, and a test guards that this exclusion stays a decision rather than a drift.
  - **D‑A11Y‑2 — one judgment carries every WCAG criterion it breaches.** A `div` dressed up as a button breaks 1.3.1 (the structure doesn't say a control is there) *and* 4.1.2 (assistive tech can't tell what it is or what it's called), and one fix repairs both. One criterion per finding would leave the conformance report claiming the other is clean; two findings would show a reviewer the same broken button twice and give a developer two tickets for one fix. So `A11yJudgment.criteria` is a list, `criterion` remains as the primary-criterion view for QA‑12a's fingerprint, and the checker reports which criteria actually apply — never all of them by default, because a *real* button with no readable name breaches only 4.1.2. A construction-time guard rejects a checker reporting against a criterion it does not own. **QA‑03 and QA‑12a must carry the list through to the conformance report.**
  - **D‑A11Y‑3 — readiness is surfaced where the work happens, not on a setup screen.** Two parts, both outside QA‑01: **QA‑02** checks the judge is available when a scan is dispatched and reports plainly if it is not (items route to human review rather than a silently empty result); **QA‑13** states judge availability at the top of the accessibility report, with the count of items sent to human review because of it. *Refinement on the option as presented:* I said "a status line on the results screen", but QA‑13's own note establishes there is no new accessibility screen — the report renders generically through `ArtifactPreviewScreen`. Putting the status **inside the report** is better anyway: it travels with the artifact, it is visible to anyone the report is shared with, and it needs no frontend work. The `test-connection` probe stays wiring-only for a11yai and says so honestly, because there is no credential for it to catch a mistake in.
- **Scope note (say this at review):** QA‑01 delivers the **seam only**. Every check returns a well-formed `uncertain` carrying `BuiltinA11yAI.NOT_WIRED` until QA‑02 builds dispatch and QA‑02a the `09c_a11y_judge` agent. `NOT_WIRED` is greppable on purpose, and a test asserts every check still returns it — so when the judge lands, the stub's removal is *provable*, not assumed. On AC3: the capability stores no inputs or results yet, so what is proven today (under the real non-superuser RLS role, not the superuser test connection) is that one tenant's a11yai **configuration** is invisible to another. The stored-results half is proven on the `A11yFinding` ledger in QA‑12a, where those rows first exist.

**QA‑02 — Judgment dispatch, cache & audit behind `a11yai`** *(critical path)* — **RE‑SCOPED (R4)**
- **Epic:** E1 · **Story:** US‑A2 · **Type:** Backend · **Status:** 🟢 Done (2026‑08‑12) · **Depends On:** QA‑01 · **Blocks:** QA‑02a, QA‑03
- **Was:** "Build the model switchboard" — routing text checks to a cheap text model and vision checks to a VLM through a LiteLLM-style gateway. **That is not buildable here and would break non‑negotiable #7:** the platform has no one-shot model-call primitive, no API credential (the companion deliberately drops `ANTHROPIC_API_KEY`), and no connector anywhere makes model calls. Model routing becomes a **later cost optimisation**, not POC scope.
- **Description:** Judgment costs time and subscription usage, so the platform must decide *what actually needs judging*, ask for it once, reuse the answer, and be able to prove afterwards which model produced which verdict. This task builds that decision layer — the one path every check goes through. In build terms: create `backend/apps/a11y/dispatch.py`. Given a set of candidates it (1) drops any whose content hash already has a stored verdict, (2) groups the remainder into per-screen batches, (3) starts **one `09c_a11y_judge` run per dispatch through `ExecutionDriver`** (built in QA‑02a) — never a direct model call, (4) stores each returned verdict against its content hash, and (5) stamps engine, model and prompt version (read from the `Run`) onto every finding.
  > **Two corrections made while building (2026‑08‑12).**
  > 1. **Path.** The task said `backend/a11y/dispatch.py`, but every module in this codebase lives under `backend/apps/` and a Django app has to be registered in `INSTALLED_APPS`. The real path is **`backend/apps/a11y/`**. Same correction applies to QA‑06's `triage.py`.
  > 2. **One run per dispatch, not one per batch.** `orchestration.trigger._guard_no_active_run` refuses to start a second run while one is live for the same work item — so per-screen runs would have collided on the second screen, every time. The screens are still grouped: they travel as separate batches inside the one run's inputs, so the judge reads a page at a time without the platform trying to run N concurrent agents against one work item. Apply a configurable **cap on judgments per run**; when a batch would exceed it, stop at the cap and report what remains rather than failing or silently truncating — runs are Temporal workflows, so the remainder resumes. Default sizing per the header: ~10 screens/run. Edge cases: a run that errors or times out returns `uncertain` for its candidates, never a hard failure from an outage; a cache hit can never be stale because the key is the input hash.
- **Acceptance Criteria:**
  - [x] Given a batch of candidates, when dispatch runs, then judgment happens via an `ExecutionDriver` run — a search of the dispatch path finds **no direct model/API call**.
  - [x] Given the same candidate judged twice, when the second dispatch runs, then it is served from the stored verdict and no run is started for it.
  - [x] Given any stored finding, when inspected, then the engine, model and prompt version that produced it are recorded.
  - [x] Given a judgment run errors or times out, when handled, then its candidates come back `uncertain` — never a hard failure.
  - [x] Given a batch that exceeds the per‑run cap, when dispatch runs, then it stops at the cap and reports the remainder rather than truncating silently.
  - [x] **(D‑A11Y‑3)** Given the judge is unavailable — no `09c_a11y_judge` spec for the workspace, or no engine to run it — when a scan is dispatched, then the run says so in plain words and its candidates route to human review, rather than returning a silently empty result that reads as "no problems found".
  - [x] Tests cover dispatch, caching, the cap, timeout‑to‑uncertain, the unavailable‑judge path and the audit record, with ≥ 90% coverage on new code.
- **Delivered (2026‑08‑12):**
  - `backend/apps/a11y/` — a new Django app (registered in `INSTALLED_APPS`), holding `dispatch.py` and the `A11yJudgmentCache` model with its own **FORCE RLS** migration (`0002_a11yjudgmentcache_rls`), mirroring the P0‑T4 policy.
  - **The cache key is the input, not the element's address.** `content_hash` covers the checker plus the element's markup, screenshot pointer and surrounding context — so a hit can never be stale: anything that could change the answer changes the key. The CSS selector and route are deliberately excluded, because selectors churn constantly and re-judging unchanged elements costs money for nothing. This is a *different* key from QA‑12a's finding fingerprint (route + selector + criterion + checker): one identifies identical **input**, the other the same **problem**. Do not merge them.
  - **The audit stamp is read from the `Run`, never from the agent's own claim** — which model produced a verdict is exactly the fact that must not be self-declared. A test proves changing the run's model changes what gets recorded.
  - **The cap works in two dimensions, both configurable per tenant via the a11yai connection's `scopes`:** `max_judgments_per_run` (default **200**, comfortably above ten ordinary screens) and `max_screens_per_run` (off by default). Whichever is reached first stops the run, and the remainder is handed back in order so a re-run continues from exactly where it stopped. **Switching to a 10‑screens cap is a config change, not a code change** (team requirement). A configured cap of **0** is honoured as a kill-switch rather than silently falling back to the default.
  - **Nothing ever comes back empty and quiet (D‑A11Y‑3).** No judge agent, no connected machine, a refused trigger, or an error — each returns complete `uncertain` judgments plus a sentence a person can act on. An accessibility scan that half-worked must never read as "no problems found".
  - **Non-negotiable #7 is asserted, not assumed:** a test scans `dispatch.py` for model/SDK imports and calls and fails naming the line. Proven non-vacuous by planting an `api_key` line, watching it fail, and removing it.
  - Tests: `backend/tests/test_a11y_dispatch.py` — **26 tests**, **100% coverage** on `dispatch.py`, 99% across the app. Regression: 81 passed (a11y + capability + RLS + seed + registry) and 87 passed (greenfield journey, code-intel dispatch, API).
  - **Known limitation to state at review:** dispatch does not yet time out a *hung* run. The error path is proven for a refused or failed trigger; a judge that starts and never reports is Temporal's timeout to own, and is picked up with the judge agent in QA‑02a.

**QA‑02a — The `09c_a11y_judge` agent + `record_a11y_finding` tool** *(critical path)* — **NEW (R4)**
- **Epic:** E1 · **Story:** US‑A2 · **Type:** Agent + Backend · **Status:** ⬜ Pending · **Depends On:** QA‑02, QA‑04 · **Blocks:** QA‑03
- **Description:** Something has to actually look at a screenshot and form a judgement, and in this platform the thing that can do that is an agent — Claude is already multimodal and already runs on the subscription, so no new model plumbing and no API bill. This task builds the judge. In build terms: author a **platform-native agent** `agents/09c_a11y_judge/agent.md` and register it in the catalog with `native=True`, following the precedent of `00e_document_vision` (which already reads page images and writes structured output). Its body takes a batch of candidate bundles and, for each one, judges it against the exact WCAG 2.2 criterion text from QA‑04 and calls a new MCP tool **`record_a11y_finding(criterion, verdict, confidence, evidence, suggested_fix, element, source)`**. That tool validates against a strict schema and rejects anything malformed — the same "coerce it so a model typo can never degrade the screen" discipline `submit_gap_report` already uses. Add a **write-completeness check** after the run: if 40 candidates were dispatched and 31 findings came back, the run **fails loudly**. Edge cases: a malformed tool call is retried once then recorded as `uncertain`; a candidate whose screenshot could not be captured is recorded `uncertain` with a reason, never a verdict.
  > **Why the completeness check is not optional.** We have a verified instance of an agent being told to call a tool and not doing it (the ideation agent skipping `ask_human`). For a compliance feature, silently reporting 31 of 40 results is the worst possible failure — worse than reporting none, because it looks like a pass.
- **Acceptance Criteria:**
  - [ ] Given a batch of candidates, when the judge runs, then one finding is recorded per candidate via `record_a11y_finding`.
  - [ ] Given a malformed tool call, when it is received, then it is retried once and then recorded as `uncertain` — never stored malformed.
  - [ ] Given fewer findings return than candidates dispatched, when the run completes, then it fails with a clear "incomplete judgment" reason naming the count.
  - [ ] Given the agent body, when checked, then it passes the platform reference sweep (no local file paths; all I/O through platform capabilities).
  - [ ] Tests cover a full batch, a malformed call, and the under-reporting case, with ≥ 90% coverage on new code.

**QA‑03 — Build the four accessibility AI checkers** *(critical path)*
- **Epic:** E1 · **Story:** US‑A3 · **Type:** Backend (AI) · **Status:** ⬜ Pending · **Depends On:** QA‑01, QA‑02, QA‑02a, QA‑04 · **Blocks:** QA‑12, QA‑16, QA‑20
  > **Correction (R4).** Each checker is still a prompt + strict schema pair, but the **prompts live in the `09c_a11y_judge` agent body** (QA‑02a) and the **schema is enforced by `record_a11y_finding`**, not by a Pydantic model wrapped around a direct API call. `backend/a11y/checkers/` holds the schema definitions and the candidate-selection rules (which elements each checker applies to); the judging text belongs with the agent.
  > **Scope note (R7).** The POC ships **five** AI-judged criteria — 1.1.1, 1.3.1, 4.1.2, 1.4.1, 2.5.3. **2.4.6 is Phase 2** (team decision D5), so it is not in this task.
- **Description:** This is the heart of the POC — the four checks that judge what the rule scanner can't. It delivers a checker for each of: *is the alt text meaningful*, *is this thing that looks like a button really one*, *is information carried by colour alone*, and *does the visible label match the name a screen reader announces*. In build terms: create `backend/a11y/checkers/` with four checkers, each a prompt plus a strict result schema (Pydantic) the model must fill. (1) **meaningful‑alt** looks at the image + its current alt + nearby text and judges whether the alt conveys the image's purpose, and whether a decorative image was wrongly given alt or an informative one left empty. (2) **fake‑semantics** reads the accessibility tree + DOM + screenshot and flags an element that looks or behaves like a control (button, heading, link) but isn't exposed as one. (3) **colour‑only** looks at the rendered region + its text and flags meaning carried by colour with no text / icon / pattern backup. (4) **label** compares a form control's visible label text against its programmatic accessible name and flags a mismatch or a placeholder used as the label. Each returns the standard result object from QA‑01, grounded in the exact WCAG 2.2 criterion text from QA‑04. Edge cases: if the model returns malformed JSON, retry once, then return `uncertain`; if an image/region can't be captured, return `uncertain` with a reason rather than a false verdict.
- **Acceptance Criteria:**
  - [ ] Given an image with a meaningless alt ("IMG_1234"), when meaningful‑alt runs, then it returns `fail` on 1.1.1 with a reason and a suggested alt.
  - [ ] Given a `<div>` wired up to act as a button, when fake‑semantics runs, then it returns `fail` on 4.1.2 / 1.3.1 naming that element.
  - [ ] Given a form field whose visible label differs from its accessible name, when label runs, then it returns `fail` on 2.5.3.
  - [ ] Given any checker returns, when validated, then the JSON conforms to the schema and the cited criterion is correct; a malformed model response is retried once then returned as `uncertain`.
  - [ ] Tests run each checker against a known‑good and a known‑bad sample, with ≥ 90% coverage on new code.

---

## EPIC E2 — Ground the AI in the real WCAG 2.2 rules
So the AI judges against the actual standard instead of guessing, this epic loads the WCAG 2.2 rules into the platform's search index and records which engine owns each criterion.

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| QA‑04 | Load WCAG 2.2 + ACT into the knowledge base | Backend | — | 🟢 |
| QA‑05 | Build the "who checks which criterion" registry | Backend | QA‑04 | 🟢 |

**QA‑04 — Load WCAG 2.2 + ACT into the knowledge base** *(critical path)*
- **Epic:** E2 · **Story:** US‑B1 · **Type:** Backend · **Status:** 🟢 Done (2026‑08‑13) · **Depends On:** — · **Blocks:** QA‑03, QA‑05, QA‑11, OP‑01, OP‑06
- **Description:** For the AI to judge against the real rules (and cite them), it needs the exact wording of each WCAG 2.2 success criterion on hand — this task loads the standard into the platform's existing search index and gives the checkers a way to pull the precise rule they're judging. In build terms: ingest the WCAG 2.2 success criteria text (and the matching ACT rule text) into the existing pgvector Knowledge Index, and add a small helper that, given a criterion number like "1.4.1", returns that criterion's exact text to drop into a checker's prompt. Version the loaded set so a future WCAG update is a data reload, not a code change. Edge case: a request for a criterion not in the set returns a clear "unknown criterion" result, never an empty string that silently weakens a prompt.
- **Acceptance Criteria:**
  > **Three corrections made while building (2026‑08‑13) — each is the code disagreeing with the task text, not a change of scope.**
  > 1. **A keyed table, not the Knowledge Index.** The task said "ingest into the existing pgvector Knowledge Index". The Knowledge Index **cannot answer this question at all**: `apps/knowledge/index._tokens` drops tokens shorter than two characters, so the query `"1.4.1"` tokenizes to `[]`, scores nothing, and `retrieve()` returns an empty list — verified by running it, not reasoned about. Criterion lookup is an exact key lookup, so it is a keyed, tenant-scoped table (`WcagCriterion`). Semantic search over the criteria is **not** built: no acceptance criterion needs it and inventing it would be scope we were not given. It remains available later.
  > 2. **ACT rules exist for 30 of the 55, not all 55.** ACT rules are machine-testable checks; 25 A/AA criteria have none because they turn on human judgement (captions being accurate, headings being *descriptive*). The team's requirement — full coverage with no silent gaps — is met by recording an explicit answer for every criterion: the mapping, or `no_act_rule: true`. A later phase reads "none exists", never a missing key. Notably **1.4.1 Use of Color, one of the four POC checkers, has no ACT rule** — which is precisely why it needs an AI judge.
  > 3. **There is no machine-readable export of WCAG to load.** The obvious candidate (`guidelines/wcag.json` in the `w3c/wcag` repo) 404s — verified. The normative Recommendation is parsed directly, which is the right source anyway.
  > **Team decision (2026‑08‑13), REVISED the same day — read this one.** The standard is **platform-wide: one copy the whole platform reads**, and **tenants never amend it**. The first decision (a copy per tenant, so a client could carry an amended set) was reversed: an amended rulebook may or may not be accurate, and a conformance product should not offer the choice. It also cost 250 duplicate rows per tenant — 2.5 million rows and ~5.6 GB of identical public text at 10,000 tenants — to support a capability that will never exist. **Tenant amendment is deliberately not supported. Do not build it.**
- **Acceptance Criteria:**
  - [x] Given a criterion number, when the helper is called, then it returns that criterion's exact WCAG 2.2 text.
  - [x] Given a checker builds its prompt, when it runs, then the relevant criterion text is present as grounding.
  - [x] Given the knowledge base is reloaded with a newer version, when checks run, then no checker code changes.
  - [x] Tests cover retrieval for a sample of criteria and the unknown‑criterion case, with ≥ 90% coverage on new code.
- **Delivered (2026‑08‑13):**
  - `backend/apps/a11y/data/wcag22.json` (694 KB) — the **committed dataset**: all 55 Level A/AA success criteria with their exact normative text, guideline + principle, the WCAG version each was introduced in, Understanding intent, technique ids, and the ACT mapping; all 94 ACT rules (87 W3C-published) with description, applicability and expectation; and the **complete 101-term WCAG glossary**, with each criterion linked to the terms its own wording leans on. Carries its W3C Document License attribution, source URLs and a sha256 per source.
  - **The glossary (team decision, 2026‑08‑13).** The criteria are *written in defined terms* — 3.3.8 turns on "cognitive function test", 1.1.1 on "non-text content". Without them a judge reads those as ordinary English rather than as W3C defines them. `grounding()` now appends the definitions for exactly the terms the requested criteria use, de-duplicated, and omits the block entirely when a criterion uses none (1.4.1 uses none). Building it caught a third parser bug: a paired `<dt>…</dt><dd>…</dd>` regex silently skipped **11 terms** — including `cognitive-function-test`, the very example that motivated the request — because some entries carry attributes (`<dt class="new">`) and one `<dt>` holds two `<dfn>`s, which made the match backtrack forward and swallow the entries after it. Now parsed by splitting on `<dt>` boundaries, and **validated**: every term W3C declares must be parsed, and every term a criterion cites must exist, or the build refuses.
  - `backend/apps/a11y/wcag_build.py` + `manage.py build_wcag_dataset` — the **offline authoring tool** that produces that file from w3.org. Never runs in a request, an agent run or a deployment. `--check` re-derives the dataset and fails naming what drifted, so "is our copy still what W3C publishes?" is a command, not a code review.
  - **"Not a single word missing" is checked, not asserted.** Every criterion's extracted text is compared **word-for-word against the raw HTML of its own section**; a dropped bullet, exception or Note — or an invented word — fails the build naming the criterion. Proven non-vacuous by tests that plant both a dropped clause and an invented word.
  - **The parser caught two real bugs before the data was trusted:** guideline sections *contain* their criteria, so an unanchored header search attributed a child criterion's text to its parent (104 criteria parsed instead of 87); and numbered appendices ("5. Conformance", "6. Glossary") were being filed as principles (7 instead of 4). Both are now regression tests.
  - **The count is corroborated three ways**, not taken on trust: the standard itself yields exactly 55 at A/AA; the version arithmetic adds up independently (37 from 2.0 + 12 from 2.1 + 6 new in 2.2 = 55); and the expected 55 numbers are written out in the test rather than derived from the dataset, so a parser that dropped one cannot agree with itself.
  - **One copy for the whole platform** (`0006_wcag_platform_wide`), loaded by that migration and refreshable with `manage.py load_wcag`. It exists before any workspace does, so a checker is never un-grounded. The three tables are the first in the platform without `tenant_id`, under a **narrow, named carve-out from non-negotiable #6** recorded in the migration: *reference data that contains no tenant data, is derived wholly from a committed file, and is never tenant-writable may be platform-wide.* Anything failing any of those three stays tenant-scoped.
  - **The app database role has SELECT only on these tables**, so "no tenant amends the standard" is a database guarantee rather than a convention. A test opens a connection as the real app role and proves UPDATE, DELETE and INSERT are all refused while reads work.
  - **A row that is not in the published set stops a reload and is named** (`UnpublishedRows`), checked *before* anything is written so a refused load leaves the database untouched rather than half-applied. Not auto-deleted: every other row can be rebuilt from the committed file, so a stray is the one thing that cannot, and a person decides. Rows of an *older* version are not strays — they are a deliberate second version.
  - **The upgrade was verified on a populated database, not just an empty one:** a scratch database was taken to the per-tenant state, filled with two tenants' duplicate copies, then migrated forward — 110 rows collapsed to 55, the `tenant_id` column and RLS policies were gone, and the text was intact. The migration reverses cleanly too.
  - **`version` is a column, so a WCAG release is a reload, not a migration** — a test loads a second version alongside 2.2 and reads both back with no code change.
  - **An unknown criterion raises `UnknownCriterion`; it never returns an empty string.** A prompt builder can silently interpolate a falsy value and produce a confident judgment grounded in nothing; an exception cannot be interpolated. A tenant with nothing loaded gets a distinct `WcagNotLoaded` naming the fix.
  - Tests: `backend/tests/test_a11y_wcag.py` — **90 tests**, **100%** on `wcag.py` and both management commands, **99%** on `wcag_build.py`. Regression: **223 passed** across a11y, capability, dispatch, auth, seed, RLS, users/roles and the API. ruff + mypy clean. `--check` re-verified against the **live** W3C sources after the glossary landed.
  - **Known limitations to state at review:** (1) `--check` needs network, so it is a developer/CI command, not a test. (2) The four checkers do not consume `grounding()` yet — that is QA‑03, and this task deliberately stops at the seam. (3) **A tenant's amendment does not survive a reload** — see the open question below.
  > **Resolved (2026‑08‑13), previously logged as an open question.** The earlier note asked how a tenant's amendment should survive a reload. It no longer applies: amendments are not supported, so a reload restoring W3C's text is the *correct* behaviour, not a gap. What replaced it is the stray-row guard below.

**QA‑05 — Build the "who checks which criterion" registry**
- **Epic:** E2 · **Story:** US‑B2 · **Type:** Backend · **Status:** 🟢 Done (2026‑08‑13) · **Depends On:** QA‑04 · **Blocks:** QA‑12
- **Description:** The platform needs to know, for each of the 55 WCAG A/AA criteria, whether the rule scanner, our AI, or a human is responsible for it — and whether it's a POC or a Phase‑2 item — so it can route each check correctly and never silently skip one. This task builds that lookup. In build terms: create a registry (a config table) of the 55 Level A/AA criteria, each row tagged with its **owner** (rule / AI / human) and its **tier** (POC / Phase 2), taken from Report 1 Addendum A; expose a lookup that returns owner + tier for any criterion. The testing flow uses it to decide which engine runs each criterion. Edge case: loading must fail loudly if the set isn't exactly 55 or a criterion has no owner — a silent gap here means an un‑checked criterion later.
  > **Two source conflicts you must not re-litigate (R7, R8) — both already decided:**
  > 1. **2.4.6 Headings and Labels is Phase 2** (Addendum A's per-criterion table wins over Addendum B's Tier‑1 list). Team decision D5. Without this the loader hits one criterion with two tiers and refuses to start.
  > 2. Where Addendum A's **prose** ("~16 agentic / ~14 human") disagrees with its **enumerated lists** (15 and 15), **the lists are authoritative** — they are internally consistent: 15 + 15 = 30 human-primary. Build the registry from the lists.
- **Acceptance Criteria:**
  > **Two corrections made while building (2026‑08‑13) — each is the source disagreeing with the task text, not a change of scope. Both approved by the team before building.**
  > 1. **Tier has three values, not two.** The acceptance criterion below said "tier (POC / Phase 2)". Addendum A §3 defines **three**, verbatim: *"IN POC = shipped in the Scope-A POC; PHASE 2 = AI-extendable later (incl. agentic); HUMAN = human-led with human sign-off."* The third is the one that matters most: the 30 human-owned criteria split **15 reached by Phase 2 / 15 human forever**, and `owner` alone cannot tell them apart. A two-value tier would have forced 15 criteria into a wrong bucket, and a coverage report built on `owner` alone would tell a client **30** criteria need a person when the honest answer is **15**. All three values are stored.
  > 2. **The tier split is 19 / 21 / 15, not 20 / 20 / 15** — see the correction added to `RESEARCH_CORRECTIONS.md` R8. The 20 / 20 figure predates decision D5; Addendum A's per-criterion table already reflects D5, so nothing had to be re-decided.
- **Acceptance Criteria:**
  - [x] Given a criterion number, when the registry is queried, then it returns the owner (rule/AI/human) and tier (in POC / Phase 2 / human).
  - [x] Given the loaded set, when validated, then there are exactly 55 criteria and every one has exactly one owner and one tier (no gaps, no duplicates).
  - [x] Given spot checks, when queried, then 1.4.3 = rule, 1.1.1 = AI, and 1.2.2 = human.
  - [x] Tests assert the count and the spot checks, with ≥ 90% coverage on new code.
- **Delivered (2026‑08‑13):**
  - `backend/apps/a11y/data/ownership.json` — the **committed registry**: all 55 Level A/AA criteria with their owner, tier and the report's own one-line reason, plus the verbatim definitions of what "owner" and "tier" mean and a sha256 of the source report. Marked as *Edvensoft engineering judgment, not W3C text*, because unlike QA‑04's data it is our opinion about our own coverage and must never be mistaken for the standard.
  - `backend/apps/a11y/ownership_build.py` + `manage.py build_ownership_dataset` — the **offline authoring tool** that derives that file from the committed PDF. A hand-typed table is a claim; a parsed one is a derivation that can be re-checked. Because the source is committed in this repo, **`--check` needs no network and runs in the test suite** — so "does the registry still say what Addendum A says?" is proven on every run, which QA‑04's network-bound equivalent could not do.
  - **"Not a single row lost" is checked, not asserted.** Every letter and digit of the source table is compared, in order, against the parsed rows. Proven non-vacuous by tests that plant a dropped row, an invented word and a swapped owner. This exists because the first parser **silently dropped four rows — including 1.4.1 Use of Color, one of the four POC checkers** — where the PDF prints `Sensory CharacteristicsA` with no space and the pattern had nowhere to anchor. It is the same class of bug that cost 11 glossary terms in QA‑04, caught the same way.
  - **Eight independent cross-checks**, most from *different sections of the reports than the table itself*, so a mis-parsed table cannot agree with all of them: the table's own per-principle headers (20 / 20 / 13 / 2); §3.3's headline owner counts (RULE 14 · AI 11 · HUMAN 30); §4.1's enumeration of the 14 rule-primary criteria; §3.3's enumeration of the 15 criteria Phase 2 reaches; §3.3's enumeration of the 15 that always need sign-off; against QA‑04, the same 55 numbers at the same A/AA levels as the standard published by W3C; §2.3's hybrid note against the derived hybrids; and Addendum B §2.2's six partially-flaggable criteria.
  - **Decision D5 is guarded by name.** 2.4.6 must be `phase_2` or the build refuses, so the POC ships **5** AI-judged criteria and cannot silently drift back to 6.
  - **What the finished backlog covers, stated honestly:** 19 criteria checked in the POC + 21 in Phase 2 = **40 with an automated or AI check**, and **15 that genuinely need a person no matter how far the AI goes**. Both numbers come from `tier`; neither is derivable from `owner`.
  - **One platform-wide copy** (`0007_criterion_ownership`), loaded by that migration and refreshable with `manage.py load_ownership`, under the same narrow carve-out from non-negotiable #6 that QA‑04 recorded — no tenant data, derived wholly from a committed file, never tenant-writable. **The app role has SELECT only**, so "a tenant cannot decide a criterion needs less checking than it does" is a database guarantee. A test opens a connection as the real app role and watches UPDATE, DELETE and INSERT all be refused while reads work.
  - **Nothing is ever silently unowned.** `verify_complete()` checks the *database* — not just the committed file — in both directions: a criterion with no owner, and an owner row for a criterion that is not loaded. `manage.py load_ownership --check` runs it, because a count can be right while the coverage is wrong.
  - **A stray row stops a reload and is named**, checked before anything is written, exactly as in QA‑04. An unknown criterion raises `UnknownCriterion`; a caller handed `None` would route no check and report a pass.
  - Kept as a **separate table** from `WcagCriterion` rather than columns on it: that table is the standard and is true regardless of what we build; this one changes the day agentic testing lands. Keyed on (version, number) rather than a foreign key — a foreign key only prevents an owner row without a criterion, and the dangerous direction is the opposite one, which no key can prevent.
  - **`secondary_checks` — the hybrids, made queryable (team decision, 2026‑08‑13).** Almost no criterion belongs to one engine outright. 3.3.2 is rule-owned yet the report has the AI *"judging adequacy of instructions"*; 1.2.2 is human-owned yet a rule *"can flag a missing caption track"*. **16 of the 55** carry such a contribution. Without this they existed only as English prose in `rationale`, where routing could not act on them — so `criteria_touched_by("ai")` answers the question `criteria_for(owner="ai")` cannot. Each note is **derived from the row's own clauses**, not re-typed, so it is text the completeness proof has already checked character-for-character; the build refuses a note that is not the report's own words, or a "secondary" engine that is actually the primary owner.
  - **`partial_auto_flag` — what a reviewer gets a head start on.** Addendum B §2.2 records that **6 of the 15** human-led criteria still get partial machine flagging (a missing caption track, a flash rate); the other 9 get nothing. It never licenses a verdict — Addendum B is explicit that *"the conformance decision — are the captions accurate, is the audio description adequate — stays human"* — and the build refuses the flag on any criterion that is not human-led. Addendum B is now a **second verified source**, with its own sha256 and a verbatim check on the sentence the six come from.
  - **The live checker map is pinned to the registry.** `integrations.types.A11Y_CHECKER_CRITERIA` is enforced at runtime — a judgment naming a criterion its checker does not own raises — and a test now asserts it says exactly what the registry says the AI owns in the POC. **The secondary touches are deliberately *not* added to it here:** letting a POC checker report against 3.3.2 or 2.4.6 before routing knows how to present a contribution (as distinct from a verdict) would weaken a live safety guard for no benefit. That reconciliation is QA‑12's, and the test fails first so it is a decision rather than a side effect.
  - **A third source conflict found and recorded as D6** (`RESEARCH_CORRECTIONS.md` R10): Addendum A §2.3's hybrid-note list disagrees with its own table by exactly two — it omits 2.4.7 and names 2.4.6, which its own row does not support. The table wins, same precedent as R7/R8, and the build **asserts the difference is exactly those two** so a corrected report stops the build instead of silently changing the registry.
  - Tests: `backend/tests/test_a11y_ownership.py` — **85 tests**, **100%** coverage on all four new modules. ruff clean; mypy reports nothing new in `apps/a11y`. The migration was verified forward, in reverse, and re-applied on a scratch database: 55 rows, no `tenant_id` column, `sdlc_app` holding SELECT and nothing else.
  - **Known limitation to state at review:** nothing consumes the registry yet — routing by owner is QA‑12, and this task deliberately stops at the seam.

---

## EPIC E‑COST — Keep AI findings trustworthy and affordable
An AI can be confidently wrong and expensive at scale. This epic makes sure an unsure AI verdict never blocks a team or overrides a hard rule, and that checks stay cheap and fully auditable.

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| QA‑06 | Add the confidence gate & "AI never overrides a rule" safety valve | Backend | QA‑03 | ⬜ |
| QA‑07 | Only check what changed; meter cost; log the model per finding | Backend | QA‑02 | ⬜ |

**QA‑06 — Add the confidence gate & "AI never overrides a rule" safety valve** *(critical path)*
- **Epic:** E‑COST · **Story:** US‑L0 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑03 · **Blocks:** QA‑12, QA‑14, OP‑05
- **Description:** In a compliance setting a confidently wrong "fail" is as damaging as a miss, so the platform must never let an unsure AI verdict block a team or overturn a definite rule result — this task builds the safety valve between raw AI output and anything shown or acted on. In build terms: create `backend/apps/a11y/triage.py` (path corrected — see QA‑02). For every AI finding, compare its confidence to a per‑checker threshold — high confidence becomes a real finding, medium or low becomes "**needs human review**" rather than "fail". Enforce a hard rule that an AI result can never overturn a deterministic axe failure (axe always wins where they disagree). Require an "evidence" value on every finding and refuse to treat an evidence‑less finding as a hard failure. Thresholds are configurable per checker. Edge case: exactly‑at‑threshold rounds toward "review" (be conservative).
  > **Honest note on "axe always wins" (R1).** Matching an AI verdict to a *specific* axe failure needs axe output with element + criterion attached. The JUnit path (QA‑11a) does not preserve that — it carries only pass/fail and free text. The structured axe result arrives with the candidate bundles in **QA‑11b**. So this task builds and unit-tests the rule; it is only **proven end-to-end at QA‑12**. Say that at review rather than presenting a fixture-only test as a working guarantee.
- **Acceptance Criteria:**
  - [ ] Given an AI finding below its checker's threshold, when triaged, then it is marked "needs human review", not "fail".
  - [ ] Given axe reports a failure and the AI disagrees, when triaged, then the axe failure stands.
  - [ ] Given a finding with no evidence, when triaged, then it is never reported as a hard failure.
  - [ ] Tests cover the threshold split, the axe‑wins rule, and the evidence rule, with ≥ 90% coverage on new code.

**QA‑07 — Only check what changed; meter cost; log the model per finding** — **PROMOTED to a prerequisite of the first real run**
- **Epic:** E‑COST · **Story:** US‑L1 / US‑L2 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑02 · **Blocks:** **QA‑12**
- **Why it moved.** Judgment runs on the Claude Code **subscription**, which is free per token but **capped in usage**. Without diff-scoping and caching, one brownfield baseline audit of a 50-screen app would do the work of fifty normal runs in a single pass, on an empty cache. This is no longer a "keep costs tidy" task — it is what stops the first real audit exhausting the subscription. It must be `🟢` before QA‑12 runs against anything real.
- **Description:** With many tenants checking many screens, unbounded judgment would be slow and would burn subscription usage, and every compliance result must be traceable to the exact model that produced it — this task keeps the volume down and makes every finding auditable. In build terms: judge only the screens/elements that changed since the last run (diff‑scope), reusing the content‑hash cache from QA‑02; and make sure model name + version + prompt version is written onto every finding in Run History. Edge case: the very first run of a project has no prior state, so it judges everything once and caches for next time — which is exactly the brownfield baseline case, so pair it with QA‑02's per-run cap and resume.
  > **Correction (R6).** "Record the AI cost in the platform's existing metering" — there is no separate metering plane, but this turned out to be a **non-issue**: judgment is a `Run`, so `Run.cost_usd` already carries it and every existing cost display works unchanged. Do not build a metering table.
- **Acceptance Criteria:**
  - [ ] Given a run where only one screen changed, when checks run, then only that screen is sent to the AI and the rest are cache‑served.
  - [ ] Given any run, when it finishes, then its AI cost is recorded against the tenant.
  - [ ] Given any stored finding, when inspected, then it shows the exact model and prompt version that produced it.
  - [ ] Tests cover diff‑scoping, cost recording, and the audit field, with ≥ 90% coverage on new code.

---

## EPIC E‑GATE — Decide pass/fail with a clear accessibility gate
Teams need a clear, configurable checkpoint that decides whether a screen's accessibility is good enough to proceed, owned by a named person.

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| QA‑08 | Create the accessibility gate policy + reviewer role + WCAG target | Backend | — | ⬜ |
| QA‑15a | Fix `refresh_derived` to dispatch derived conditions by key | Backend | — | ⬜ |
| QA‑15 | Enforce the accessibility test gate at the end of testing | Backend | QA‑08, QA‑14, QA‑15a | ⬜ |

**QA‑08 — Create the accessibility gate policy + reviewer role + WCAG target** — **SCOPE ADDED**
- **Epic:** E‑GATE · **Story:** US‑F1 / US‑F2 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** — · **Blocks:** QA‑15, QA‑19, OP‑03
  > **Added scope — the WCAG target had no home.** Journey J1 says the owner sets the project's target to WCAG 2.2 AA, but `ProjectProfile` has no such field. Add an **`a11y` JSON block** to `ProjectProfile` (`{"target": "wcag_2.2_aa", "gate": {…}}`), matching how `theme`, `export_policy` and `preview_start` already work there — a policy block, not a scalar column, so later settings need no migration.
  > **Role decision (D7): map the Accessibility SME onto the existing `qa_lead` role for the POC.** Do **not** add a value to the shared `Role` enum — it is used by both `Membership.role` and `Approval.required_role`, and touching it drags in a migration, the RBAC matrix and the UI for no POC benefit. Add a real role only when a client needs the separation.
- **Description:** Teams need one clear, adjustable checkpoint for "is this accessible enough to move on?", and someone accountable for accessibility sign‑off — this task creates that gate policy and role without enforcing anything yet. In build terms: add an accessibility gate policy object to the Gate/Approval service with configurable thresholds — which severities block, and the confidence bar below which findings never block — editable per project; and add an "Accessibility SME / reviewer" role to the RBAC role→phase→gate matrix (for the POC it may map onto the existing QA Lead). This task only makes the policy and role exist and be editable; enforcement is QA‑15. Edge case: a project with no explicit policy inherits a sensible default (block on Critical/Serious, confidence bar at the checker default).
- **Acceptance Criteria:**
  - [ ] Given a project, when an admin opens the a11y gate policy, then they can set which severities block and the confidence threshold, and save it.
  - [ ] Given the RBAC matrix, when inspected, then the Accessibility reviewer role exists and can be assigned (or mapped to QA Lead).
  - [ ] Given a project with no explicit policy, when read, then it returns the documented default.
  - [ ] Tests cover policy read/write, the default, and role assignment, with ≥ 90% coverage on new code.

**QA‑15a — Fix `refresh_derived` to dispatch derived conditions by key** — **NEW (R3)**
- **Epic:** E‑GATE · **Story:** US‑F1 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** — · **Blocks:** QA‑15
- **Description:** There is a latent bug in the gate machinery that will silently break our accessibility gate the moment we add it, so it has to be fixed first. `backend/apps/gates/conditions.py::refresh_derived` hands **every** derived condition to the *test* evaluator (`_evaluate_test_condition`). Today that is harmless — `testgate.evaluate()` returns any condition it doesn't recognise untouched — but it means the platform can only ever have **one** derived condition. Add a second and it is passed to the wrong evaluator and silently never refreshes, so the gate reads a stale value seeded when it opened. For an accessibility gate that would mean a gate that never notices findings were fixed, or worse, never notices they exist. In build terms: replace the hardcoded call with a small registry mapping condition key → evaluator, so each derived condition is refreshed by its own evaluator and an unknown key is returned untouched (today's safe behaviour, kept). Edge case: a condition marked `derived` with no registered evaluator must pass through unchanged rather than raising — a gate must never crash on an unknown condition.
- **Acceptance Criteria:**
  - [ ] Given a gate carrying both the blocking-test and an a11y derived condition, when refreshed, then each is evaluated by its own evaluator and both update.
  - [ ] Given a derived condition with no registered evaluator, when refreshed, then it passes through unchanged and nothing raises.
  - [ ] Given the existing test gate, when refreshed, then its behaviour is unchanged (regression proven by the existing test-gate tests still passing).
  - [ ] Tests cover two derived conditions together, the unknown-key case, and the no-regression case, with ≥ 90% coverage on new code.

**QA‑15 — Enforce the accessibility test gate at the end of testing** *(critical path)*
- **Epic:** E‑GATE · **Story:** US‑F1 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑08, QA‑14, QA‑15a · **Blocks:** QA‑19, OP‑09
- **Description:** The pipeline must actually stop when a screen has a real accessibility failure and let it through when it doesn't — this task makes the gate enforce the QA‑08 policy on the merged findings. In build terms: add `backend/apps/gates/a11ygate.py` as a **derived** condition on the `testing` phase, cloned from the existing `testgate.py` pattern, and compose it in `conditions.py`. At decide time it evaluates the merged axe + AI findings against the project's policy — *blocked* when there is any axe or AI‑confirmed Critical/Serious at WCAG 2.2, *passable* when there are none; low‑confidence‑only findings never block. Its `detail` line names the findings holding the gate shut, so the reviewer sees why. Edge case: a run that errored (couldn't complete) blocks with an "incomplete run" reason rather than passing by default.
  > **Build it derived, not reviewer-attested (R3).** `testgate.py`'s own comment says why: *"a reviewer can never tick past a red suite."* The existing WCAG checklist is reviewer-attested and on the **design** gate — that is correct for design judgement calls, and it is **not** this. A reviewer must not be able to tick past a real accessibility failure.
- **Acceptance Criteria:**
  - [ ] Given a run with an AI‑confirmed Critical, when the gate evaluates, then it blocks.
  - [ ] Given a run with only low‑confidence findings, when the gate evaluates, then it passes.
  - [ ] Given a run with an axe Serious failure, when the gate evaluates, then it blocks.
  - [ ] Given a run that failed to complete, when the gate evaluates, then it blocks with an "incomplete run" reason.
  - [ ] Tests cover each case, with ≥ 90% coverage on new code.

---

## EPIC E‑EVAL — Prove the AI is accurate (Edvensoft‑internal only)
Before we trust these checks in front of tenants, *we* need to measure how often they're right and stop a model change from quietly making them worse. **This epic is Edvensoft‑internal — it is never exposed to tenants or stored in tenant data.**

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| QA‑09 | Build the internal golden set (team‑only) | Internal | QA‑03 | ⬜ |
| QA‑10a | Create the local accuracy-harness entry point | Internal | — | ⬜ |
| QA‑10 | Build the internal accuracy harness (team‑only) | Internal | QA‑09, QA‑10a | ⬜ |

**QA‑09 — Build the internal golden set (team‑only)**
- **Epic:** E‑EVAL · **Story:** US‑G1 · **Type:** Internal (not a tenant feature) · **Status:** ⬜ Pending · **Depends On:** QA‑03 · **Blocks:** QA‑10
- **Description:** Before we put these AI checks in front of tenants, we (Edvensoft) need an answer‑key to measure how often they're right — a set of real screens we've labelled by hand against WCAG 2.2. This is our internal quality control and must never ship to tenants. In build terms: assemble a labelled dataset of screens/components with the correct WCAG 2.2 verdict per relevant criterion, adjudicated by an accessibility expert; store it inside Edvensoft's own repo/CI, versioned; keep it entirely out of tenant databases and the platform UI. Edge case: any disagreement between two labellers is resolved by a third adjudication and the final call recorded — the golden set must be trustworthy or the numbers it produces are meaningless.
  > **Status (2026‑08‑12).** The SME is a **QA Lead team member**; the screens to label are **not ready yet (in progress)**. This does **not** block the critical path — QA‑09 and QA‑10 gate only **QA‑22** (Phase 2). M0 and M1 proceed without them. Start this task when the screens exist.
- **Acceptance Criteria:**
  - [ ] Given the dataset, when inspected, then each item has an expert‑adjudicated verdict per relevant criterion and a version tag.
  - [ ] Given the platform code, when searched, then the golden set is never referenced by tenant‑facing code or stored in tenant data.
  - [ ] Given a new dataset version, when added, then the previous version is retained.

**QA‑10a — Create the local accuracy-harness entry point** — **NEW (R6)**
- **Epic:** E‑EVAL · **Story:** US‑G2 · **Type:** Internal (not a tenant feature) · **Status:** ⬜ Pending · **Depends On:** — · **Blocks:** QA‑10
- **Description:** QA‑10 says to wire the accuracy scorer "into Edvensoft CI" — but **this repository has no CI**: no `.github/`, no `Jenkinsfile`, no `.gitlab-ci.yml`, only `docker-compose.yml`. So the thing QA‑10 plugs into has to exist first. Team decision **D4**: for the POC the harness runs **locally via `make`**, not in a pipeline; a real pipeline comes when a client depends on it. In build terms: add a `make a11y-eval` target that runs the scorer against the golden set and writes a versioned results file, plus a stored **baseline** of the last accepted numbers it compares against. Keep it entirely inside Edvensoft's own repo/CI space — never tenant data, never the platform UI. Edge case: with no stored baseline the first run **records** its numbers as the baseline rather than failing.
  > **Related prerequisite (also R6):** `pytest-cov` is not installed and no coverage config exists, so the "≥ 90% coverage on new code" in this backlog's Definition of Done is currently **unmeasurable**. Add `pytest-cov` and a **module-scoped** `make cov` before QA‑01 — module-scoped deliberately, because running the full backend suite is known to be killed.
- **Acceptance Criteria:**
  - [ ] Given the golden set, when `make a11y-eval` runs, then it prints per-checker numbers and writes a versioned results file.
  - [ ] Given no prior baseline, when it runs, then it records the first numbers as the baseline instead of failing.
  - [ ] Given the repository, when searched, then the harness and its data are never referenced by tenant-facing code.

**QA‑10 — Build the internal accuracy harness (team‑only)** — **RE‑SCOPED (R6)**
- **Epic:** E‑EVAL · **Story:** US‑G2 · **Type:** Internal (not a tenant feature) · **Status:** ⬜ Pending · **Depends On:** QA‑09, QA‑10a · **Blocks:** QA‑22
- **Description:** We need to know, in numbers, how accurate each checker is, and to stop a model or prompt change from quietly degrading it — this task builds the scorer. In build terms: build a scorer that runs each checker over the golden set and reports precision, recall, and F1 per checker, and make **promotion of a new model or prompt version fail** when any checker drops below the stored baseline from QA‑10a. Edge case: a new checker with no prior baseline records its first numbers as the baseline rather than blocking.
  > **Correction (R6).** "Wire it into CI" — there is no CI. It runs through the local `make` entry point from QA‑10a (decision D4). The *rule* is unchanged: an accuracy regression blocks promotion. Only where it runs changed.
- **Acceptance Criteria:**
  - [ ] Given the golden set, when the harness runs, then it reports precision/recall/F1 per checker.
  - [ ] Given a model/prompt change that lowers a checker's accuracy below baseline, when the harness runs, then promotion is blocked with the failing checker named.
  - [ ] Given no regression, when it runs, then promotion is allowed and the baseline updates.

---

## EPIC E5 — Test every screen for accessibility (rules + AI)
This epic upgrades the testing phase so one run scans with the rules **and** the AI at WCAG 2.2, reports both together, and the automated suite runs both.

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| QA‑11 | Move the accessibility standard to WCAG 2.2 (agents **+ gate**) | Agent edit + Backend | QA‑04 | ⬜ |
| QA‑11a | Make 09b generate axe assertions | Agent edit | QA‑11 | ⬜ |
| QA‑11b | Capture AI candidate bundles in the companion + ingest them | Runner + Backend | QA‑11a | ⬜ |
| QA‑12 | Add the AI‑checks pass to the testing flow | Agent edit + Backend | QA‑03, QA‑06, QA‑07, QA‑11b | ⬜ |
| QA‑13 | Add source/confidence/fix fields to the report | Backend | QA‑12, QA‑12a | ⬜ |
| QA‑16 | Make the test‑automation agent script the AI checks | Agent edit | QA‑12 | ⬜ |

**QA‑11 — Move the accessibility standard to WCAG 2.2 (agents + gate)** — **SCOPE EXPANDED (R3)**
- **Epic:** E5 · **Story:** US‑E1 · **Type:** Agent edit + Backend · **Status:** ⬜ Pending · **Depends On:** QA‑04 · **Blocks:** QA‑11a
- **Description:** Everything in the platform still says WCAG 2.1 while the whole POC targets 2.2, so the standard has to move up one version **everywhere it is written down** — a careful data-reference edit that leaves reasoning untouched. In build terms, three places: (1) `agents/09_testing/agent.md` — Step 9, the Evidence Base, the quality gate and the severity notes; (2) `agents/09b_test_automation/agent.md` — any standard reference it carries; and (3) **`backend/apps/gates/wcag.py`** — replace its hardcoded 9-criterion WCAG **2.1** checklist with one derived from the QA‑05 criterion registry, filtered to the **human-owned** criteria, at 2.2. Treat the agent edits as "data-reference" edits under the 75/15/10 rule and run the reference sweep afterward. Edge case: a stray "2.1" outside Step 9 causes silent confusion downstream — sweep the whole body, not the step.
  > **Why the gate file is now in scope (R3).** `gates/wcag.py` is real, live, and **no task in either backlog touched it**. Left alone it would sit at WCAG 2.1 forever while every other surface moved to 2.2 — a split-brain nobody would notice until an audit. It stays **reviewer-attested on the design gate**, which is correct: those are genuine human judgement calls. The *computed* test gate is a separate thing and is QA‑15.
  > **Honest scope (R1).** This task changes what the platform *says*, not what it *does* — agent 09 has never executed a scan. The first executable accessibility check is **QA‑11a**. Do not claim this task "moved the scan to 2.2."
- **Acceptance Criteria:**
  - [ ] Given the 09 and 09b agent bodies, when searched, then no "WCAG 2.1" reference remains in their accessibility content.
  - [ ] Given `gates/wcag.py`, when read, then its checklist is derived from the QA‑05 registry at 2.2 and lists the human-owned criteria.
  - [ ] Given an existing design gate approval, when opened after the change, then it still functions (regression proven by the existing gate tests).
  - [ ] Given the reference sweep, when run on both edited agents, then it passes.
  - [ ] Tests cover the derived checklist and the design-gate regression, with ≥ 90% coverage on new code.

**QA‑11a — Make 09b generate axe assertions** *(critical path)* — **NEW (R1)**
- **Epic:** E5 · **Story:** US‑E1 · **Type:** Agent edit · **Status:** ⬜ Pending · **Depends On:** QA‑11 · **Blocks:** QA‑11b, QA‑12
- **Description:** This is the task that makes an accessibility scan actually *run* for the first time — and it needs no platform code at all, because the path already exists. Agent 09b already generates Playwright tests, runs them in the companion's worktree against the live preview app, and its JUnit output already flows through `collect_test_results` → `import_test_results` → **defects that open and close themselves**. `@axe-core/playwright` assertions are simply Playwright tests. In build terms: extend `agents/09b_test_automation/agent.md` so that, alongside the functional scripts it already writes, it generates an **axe assertion per screen** at WCAG 2.2, named so the JUnit `<testcase>` carries the screen's test-case id (the parser recovers `TC-###` from the test name — see `backend/apps/quality/junit.py`). Follow the agent's existing rule never to overwrite scaffolding — extend, don't clobber. Edge case: a screen the preview cannot serve is reported as a failing test with the reason, never skipped silently.
  > **What this buys, and what it does not.** It buys real axe violations arriving as tracked, self-closing defects with zero platform change. It does **not** buy structured per-element axe data — JUnit carries only `test_ref`, `status` and free text capped at 2000 characters, so no screenshot, no accessibility-tree node, no element selector, no criterion as data. That is QA‑11b's job.
- **Acceptance Criteria:**
  - [ ] Given a screen, when 09b generates its scripts, then an axe assertion for that screen is among them, at WCAG 2.2.
  - [ ] Given the generated scripts, when the suite runs, then axe violations appear as failing tests in the JUnit report.
  - [ ] Given those failures are imported, when the run completes, then a defect opens per failing screen and closes on a later passing run.
  - [ ] Given existing scaffolding, when 09b runs, then it is not overwritten.
  - [ ] Given a screen the preview cannot serve, when the suite runs, then it fails with a reason rather than being skipped.

**QA‑11b — Capture AI candidate bundles in the companion + ingest them** *(critical path)* — **NEW (R1, R2)**
- **Epic:** E5 · **Story:** US‑E2 · **Type:** Runner + Backend · **Status:** ⬜ Pending · **Depends On:** QA‑11a · **Blocks:** QA‑12
- **Description:** The AI cannot judge what it cannot see, and the only place a rendered page, a screenshot and an accessibility tree exist is the companion — the app under test runs from `preview_start` at a **localhost URL on the developer's machine that the server cannot reach**. This task captures what the AI needs and gets it to the platform. In build terms: add `runner/companion/a11ycapture.py` as a sibling of `runner/companion/testresults.py`, following its exact discipline — *the companion only knows **where** to look; the platform owns the parsing; no report ⇒ no results ⇒ no import*. During the 09b run it captures, per screen, a **candidate bundle** for each element worth judging: element selector, its accessibility-tree node, a cropped screenshot (staged to S3, pointer only in state — #1/#3), the surrounding text, and **axe's structured result for that element**. Add an ingestion endpoint `POST /api/projects/<id>/a11y-candidates/`, mirroring the proven `POST /api/projects/<id>/test-results/` — CI-token auth, raw body, provenance query params. Edge cases: an absent or unreadable capture is **never** an empty pass (mirror `collect_test_results` — the platform declines to import it); a screen whose screenshot fails to capture yields a bundle marked uncapturable so QA‑02a records `uncertain` rather than a false verdict.
  > **Candidate selection is what keeps this affordable.** Bundle only elements worth asking about — images for alt, controls for semantics/label, coloured indicators for colour-only — not every node. With ~10 screens per run this is the difference between a viable run and exhausting the subscription.
- **Acceptance Criteria:**
  - [ ] Given a screen with images, controls and a coloured status indicator, when capture runs, then a bundle is produced for each with selector, a11y-tree node, screenshot pointer, context text and axe's result.
  - [ ] Given bundles are posted, when ingested, then they are stored tenant-scoped and readable by the dispatch layer.
  - [ ] Given no capture file, when the run completes, then nothing is imported and no run reports a false green.
  - [ ] Given a screenshot that cannot be captured, when bundled, then it is marked uncapturable rather than dropped.
  - [ ] Given a second tenant, when it ingests, then it cannot read the first tenant's bundles (proven by an RLS test).
  - [ ] Tests cover capture, ingestion, the no-file case, the uncapturable case and isolation, with ≥ 90% coverage on new code.

**QA‑12 — Add the AI‑checks pass to the testing flow** *(critical path)* — **CORRECTED (R1)**
- **Epic:** E5 · **Story:** US‑E2 · **Type:** Agent edit + Backend · **Status:** ⬜ Pending · **Depends On:** QA‑03, QA‑06, QA‑07, QA‑11b · **Blocks:** QA‑13, QA‑14, QA‑16, QA‑17
- **Was:** "after axe runs on a screen, the platform calls `a11yai.check_*`" — **there was no point at which axe ran.** Agent 09 has no browser, shell or worktree. The scan now runs in 09b (QA‑11a) and the candidates arrive as ingested bundles (QA‑11b), so this task joins the two halves rather than hooking a scan that never existed.
- **Description:** A single test run should report both the rule findings and the "meaning" findings the rules can't see, side by side, in one place. In build terms: when a run's candidate bundles have been ingested, hand them to the QA‑02 dispatch layer, put every returned verdict through the QA‑06 triage, and merge the results with that run's axe findings into one accessibility report — each entry tagged with its source (rule or AI), confidence and cited WCAG 2.2 criterion. Low-confidence verdicts appear as "needs review", never as failures. Update `agents/09_testing/agent.md` Step 9 so the agent's report format reflects the merged view it will now receive. Edge case: a screen with no candidate elements for a given checker simply produces no AI finding for it — not an error.
  > **This is the milestone proof point.** M1 is only done when a **real feature run** shows axe and AI findings in one report. Demonstrate it on a live run, not fixtures — a fixture-only demonstration here is precisely the failure this whole correction pass exists to prevent.
- **Acceptance Criteria:**
  - [ ] Given a screen, when a test run completes, then the report contains both axe findings and AI findings in one place.
  - [ ] Given each AI finding, when shown, then it carries source = AI, a confidence, and a cited WCAG 2.2 criterion.
  - [ ] Given a low‑confidence AI finding, when merged, then it appears as "needs review", not a failure.
  - [ ] Given axe and the AI disagree on the same element and criterion, when merged, then the axe verdict stands (QA‑06's rule, now provable end-to-end).
  - [ ] Given a **live run on a real feature**, when it completes, then the merged report is demonstrated from that run — not from fixtures.
  - [ ] Tests cover the merged report on a sample screen, with ≥ 90% coverage on new code.

**QA‑13 — Add source/confidence/fix fields to the report** — **SHRUNK**
- **Epic:** E5 · **Story:** US‑E2 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑12, QA‑12a · **Blocks:** QA‑24
- **Description:** A reader of the accessibility report should be able to tell at a glance which findings came from the rules vs the AI, how sure the AI is, and what fix is suggested — this task adds those fields without disturbing the existing report. In build terms: render an `a11y_report` artifact from the QA‑12a findings ledger carrying `source` (rule/AI/human), `confidence`, `criterion` and `suggested_fix` per finding, grouped by criterion, keeping every existing `test_report` field intact. Register it as **markdown**. Edge case: an older report saved before this change must still open — missing fields render blank, never an error.
  > **No new UI needed here.** `ArtifactPreviewScreen` already renders artifacts **generically by `content_type`** (markdown, HTML, mermaid), and `Artifact.type` is a free-form field — so an `a11y_report` registered as markdown displays with **no frontend work at all**. My earlier assessment that this needed new screens was wrong. The only genuinely new accessibility UI in this backlog is the SME console (QA‑23).
- **Acceptance Criteria:**
  - [ ] Given a report with mixed findings, when viewed, then each row shows source, confidence, criterion, and suggested fix.
  - [ ] **(D‑A11Y‑2)** Given a finding that breaches more than one criterion, when viewed, then every criterion it breaches is shown on that one row — not split into duplicate rows, and not silently reduced to the first.
  - [ ] **(D‑A11Y‑3)** Given the AI judge was unavailable or partly unavailable for the run, when the report is viewed, then it says so at the top and states how many items were sent for human review because of it — so an incomplete run can never be mistaken for a clean one.
  - [ ] Given a pre‑change report, when opened, then it still renders.
  - [ ] Tests cover the new fields and backward compatibility, with ≥ 90% coverage on new code.

**QA‑16 — Make the test‑automation agent script the AI checks**
- **Epic:** E5 · **Story:** US‑E3 · **Type:** Agent edit · **Status:** ⬜ Pending · **Depends On:** QA‑12 · **Blocks:** QA‑20
- **Description:** The automated test suite should run the accessibility AI checks too, not just the rule scan, so accessibility is verified automatically on every relevant screen — this task teaches the test‑automation agent to generate those scripts. In build terms: extend `agents/09b_test_automation/agent.md` so that, using its existing Playwright‑MCP flow and Page‑Object conventions, it generates automation that runs **both** axe and the `a11yai` checks against a screen and writes the scripts into the companion worktree. Edge case: follow the agent's existing rule to never overwrite existing scaffolding — extend, don't clobber.
- **Acceptance Criteria:**
  - [ ] Given a screen, when 09b generates a script, then the script runs both axe and the AI checks.
  - [ ] Given the generated script, when dry‑run/compiled, then it passes the agent's existing dry‑run step.
  - [ ] Given existing scaffolding, when 09b runs, then it is not overwritten.

---

## EPIC E9 — Turn accessibility findings into tracked, self‑closing fixes
Reuses the platform's existing bug loop so a real accessibility finding becomes a tracked defect that a developer fixes and that closes itself when the fix passes.

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| QA‑12a | The accessibility findings ledger + review queue | Backend | QA‑06 | ⬜ |
| QA‑14 | Route accessibility findings into the defect loopback | Backend | QA‑12, QA‑12a, QA‑06 | ⬜ |

**QA‑12a — The accessibility findings ledger + review queue** *(critical path)* — **NEW (R3)**
- **Epic:** E9 · **Story:** US‑I1 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑06 · **Blocks:** QA‑13, QA‑14, QA‑18, QA‑21, QA‑23
- **Description:** Accessibility findings currently have nowhere to live — results are prose inside a report document, and the platform's bug loop keys everything on a *test case id*, which a finding like "the submit button on /checkout has no accessible name" simply doesn't have. Without an identity for a finding, four separate acceptance criteria elsewhere in this backlog are unimplementable. This task gives findings a home. In build terms: create a `backend/apps/a11y/` app with an `A11yFinding` model, **RLS-scoped from its first migration** (non-negotiable #6), holding criterion, source (rule/AI/human/agentic), verdict, confidence, severity, evidence, suggested fix, element selector, screenshot **pointer** (body stays in S3 — #1/#3), model/prompt version, adjudication status, and first/last-seen run. The load-bearing field is a stable **`fingerprint`** = hash of *(route + normalised element selector + criterion + checker)*. Edge case: a finding whose element selector cannot be normalised falls back to a positional key and is flagged low-stability, so it is never silently merged with a different element.
  > **Why the fingerprint is the whole point.** It is what turns four "impossible" criteria into one-liners: same fingerprint ⇒ a re-run **updates** instead of duplicating (QA‑18), a finding that vanishes and returns **reopens** instead of twinning (QA‑14), and the same problem found by both the static check and the keyboard agent collapses into **one** bug (QA‑21).
  > **Why a table and not something that already exists.** I checked the alternatives. Defect WorkItems are right for *blocking* findings (QA‑14 uses them) but a WorkItem per uncertain finding would flood the board, which QA‑14 explicitly forbids. `Clarification` looks like a review queue but **blocks the agent** — `ask_human` holds the engine open until answered — while an SME queue must be asynchronous and outlive the run. An artifact is a document and cannot carry adjudication state. Hence a small, purpose-built table.
  > **This is state, not content.** A finding is a pointer, a provenance record and a verdict — exactly what non-negotiables #1 and #3 say the platform should own. The screenshot body lives in S3.
- **Acceptance Criteria:**
  - [ ] Given the same problem seen on two runs, when recorded, then one finding row exists with an updated last-seen run — not two rows.
  - [ ] Given a finding that disappears and returns, when recorded, then the original row is reused rather than a new one created.
  - [ ] Given two different elements on one screen failing the same criterion, when recorded, then they are two distinct findings.
  - [ ] Given an unnormalisable selector, when recorded, then it uses the fallback key and is flagged low-stability.
  - [ ] Given a second tenant, when it queries findings, then it cannot see the first tenant's rows (proven by a DB-level RLS test).
  - [ ] Tests cover dedupe, reopen, distinctness, the fallback key and isolation, with ≥ 90% coverage on new code.

**QA‑14 — Route accessibility findings into the defect loopback** *(critical path)* — **RE‑SCOPED (R3)**
- **Epic:** E9 · **Story:** US‑I1 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑12, QA‑12a, QA‑06 · **Blocks:** QA‑15, QA‑18, QA‑21
- **Description:** When a real accessibility problem is found it should automatically become a tracked bug that a developer fixes and that closes itself once the fix passes — exactly the loop the platform already uses — so this task connects accessibility findings to it. In build terms: **copy `record_security_findings` (`backend/apps/quality/services.py`)**, which already does this whole reconciliation for security: it keys child defect WorkItems on `external_ref.finding`, reopens one that had been closed, closes one no longer blocking, and is deliberately scoped so it "never touches test defects." Do the same for accessibility, keyed on the QA‑12a **fingerprint** with `kind: "a11y"`, severity mapped from the WCAG level (the mapping already lives in agent 09). A low-confidence finding goes to the SME queue (QA‑23), **never** a defect. Edge case: a finding that flips between runs must reopen the same defect, never spawn a duplicate — which the copied pattern already handles.
  > **Much smaller than originally written.** I first reported that "no duplicates" and "reopen a flapper" were unimplementable. They are not — this is a copy of a ~60-line function that already works in production for security findings. The only genuinely new part is the fingerprint key, which QA‑12a provides.
  > **One difference from security you must keep.** Security *drops* its non-blocking findings — only Critical/High become WorkItems. Accessibility **cannot**: the uncertain ones must persist in the QA‑12a ledger for the SME queue. Blocking ⇒ defect **and** ledger row. Non-blocking ⇒ ledger row only.
- **Acceptance Criteria:**
  - [ ] Given a failing a11y check, when the run is recorded, then a defect opens with the correct severity.
  - [ ] Given a later run where that check passes, when recorded, then the defect auto‑closes.
  - [ ] Given a low‑confidence finding, when recorded, then it goes to the SME queue, not a defect.
  - [ ] Given a flapping finding, when re‑recorded, then the same defect reopens rather than a duplicate opening.
  - [ ] Tests cover open, close, low‑confidence routing, and no‑duplicate, with ≥ 90% coverage on new code.

---

## EPIC E‑BF — Audit an already‑built (onboarded) app for accessibility
Lets a user point the accessibility tests straight at an imported app that never went through our design phase, and get a clear baseline + a fix backlog.

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| QA‑17 | Run the accessibility checks against an onboarded app | Backend | QA‑12 (consumes OP‑06) | ⬜ |
| QA‑18 | Produce the baseline report + fix backlog | Backend | QA‑17, QA‑14 | ⬜ |
| QA‑19 | Make the first baseline run informational, not blocking | Backend | QA‑15 | ⬜ |

**QA‑17 — Run the accessibility checks against an onboarded app**
- **Epic:** E‑BF · **Story:** US‑BF1 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑12 · (consumes **OP‑06**) · **Blocks:** QA‑18
- **Description:** A user who imports an existing app should be able to point the accessibility tests straight at it, even though it never went through our design phase and has no accessibility spec — this task lets the testing engine run against an already‑built app's live pages. In build terms: add an entry point that runs axe + the `a11yai` checks against an onboarded project's registered routes/screens (the route list comes from onboarding, OP‑06) **without requiring an `accessibility` artifact to exist**; reuse the same capture-and-judge machinery from QA‑11a/11b/12, changing only where the screen list comes from. Edge case: a route that fails to load (auth wall, 404, timeout) is reported as an audit error for that route, never silently skipped.
  > **Path correction (R5).** The original block said "without requiring a `docs/ux/ACCESSIBILITY.md`". **That file does not exist in this platform** — the design phase registers an artifact of type **`accessibility`**. Never reintroduce the file path.
  > **Sizing warning.** This is the worst case for judgment volume: the whole app, first run, empty cache. QA‑02's per-run cap and QA‑07's caching are what keep it viable — do not run this before both are `🟢`.
- **Acceptance Criteria:**
  - [ ] Given an onboarded app with a registered route list and no accessibility spec, when the baseline audit runs, then it produces findings for those routes.
  - [ ] Given a route that fails to load, when audited, then it is reported as an error, not skipped.
  - [ ] Tests cover a run against a sample route list including a failing route, with ≥ 90% coverage on new code.

**QA‑18 — Produce the baseline report + fix backlog**
- **Epic:** E‑BF · **Story:** US‑BF1 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑17, QA‑14 · **Blocks:** OP‑08
- **Description:** The output of auditing an existing app should be a clear "here's where you stand" report and a ready‑to‑work list of fixes, without creating duplicate tickets each time it's re‑run — this task produces both. In build terms: from the baseline audit findings, produce a WCAG‑2.2 baseline report grouped by criterion with severity, and open a prioritised defect backlog, using register‑don't‑recreate so re‑running the audit updates existing items instead of duplicating them. Edge case: re‑running after some fixes should show those items closed and only the still‑broken ones open.
- **Acceptance Criteria:**
  - [ ] Given a completed baseline audit, when it finishes, then a per‑criterion baseline report and a prioritised defect backlog exist.
  - [ ] Given the audit is run a second time, when it finishes, then no duplicate defects are created.
  - [ ] Given fixes landed between runs, when re‑run, then fixed items show closed and only remaining ones stay open.
  - [ ] Tests cover report generation and the no‑duplicate rule, with ≥ 90% coverage on new code.

**QA‑19 — Make the first baseline run informational, not blocking**
- **Epic:** E‑BF · **Story:** US‑BF1 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑15 · **Blocks:** —
- **Description:** The very first audit of an inherited app shouldn't block anything — it's a health‑check, not a pass/fail exam — but later runs should be able to hold the line once the team commits to fixing, so this task makes the first baseline informational. In build terms: configure the a11y gate so a project's first baseline run is informational (reported, never blocking), while subsequent runs can be switched to enforce the target per the QA‑08 policy. Edge case: "first run" is per project — a second project's first baseline is also informational, independently.
- **Acceptance Criteria:**
  - [ ] Given a project's first baseline run, when the gate evaluates, then it does not block.
  - [ ] Given a later run with enforcement enabled, when the gate evaluates, then it blocks on real failures.
  - [ ] Tests cover both states per project, with ≥ 90% coverage on new code.

---

## EPIC E10 — Test keyboard & interaction journeys with an AI agent (Phase 2)
Some of the most important checks — full keyboard use, focus order, screen‑reader announcements — need the app to be *operated*, not just scanned. This epic builds an AI agent that does that, and keeps it advisory until it's proven reliable.

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| QA‑20 | Build the agent that keyboard‑tests a journey | Backend (AI) | QA‑03, QA‑16 | ⬜ |
| QA‑21 | Send the agent's findings into the bug loop & review queue | Backend | QA‑20, QA‑14 | ⬜ |
| QA‑22 | Keep the agent advisory until it passes the accuracy bar | Backend | QA‑20, QA‑10 | ⬜ |

**QA‑20 — Build the agent that keyboard‑tests a journey**
- **Epic:** E10 · **Story:** US‑J1 · **Type:** Backend (AI) · **Status:** ⬜ Pending · **Depends On:** QA‑03, QA‑16 · **Blocks:** QA‑21, QA‑22
- **Description:** Some of the most important accessibility checks — can you use the whole thing with only a keyboard, does focus land in the right place, does a screen reader get told when something changes — can't be judged from one static page; you have to operate the app, and this task builds an AI agent that does exactly that. In build terms: build an agent that drives the running app through Playwright MCP (already wired into 09b) to test keyboard/interaction criteria on a critical journey — tabbing through in order, checking nothing traps focus, checking focus stays visible and isn't hidden behind sticky headers, watching for unexpected changes when an element gets focus or a field is typed in, confirming a modal traps focus and returns it on close, and watching (via a DOM MutationObserver) that status messages are announced. Expose it as a new `a11yai.check_journey` method that returns findings in the standard result shape with confidence. Edge case: if a journey step can't be reached (a precondition fails), the agent reports that step as "could not test" rather than passing or failing it.
- **Acceptance Criteria:**
  - [ ] Given a critical journey, when the agent runs, then it reports pass/fail per keyboard/interaction criterion with a confidence.
  - [ ] Given a page with a keyboard trap, when the agent runs, then it reports `fail` on 2.1.2.
  - [ ] Given a status message that never announces, when the agent runs, then it reports `fail` on 4.1.3.
  - [ ] Given an unreachable step, when the agent runs, then it reports "could not test" for that step.
  - [ ] Tests cover a journey with a planted keyboard trap, with ≥ 90% coverage on new code.

**QA‑21 — Send the agent's findings into the bug loop & review queue**
- **Epic:** E10 · **Story:** US‑J1 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑20, QA‑14 · **Blocks:** —
- **Description:** Whatever the agent discovers should flow into the same bug loop and review queue as every other finding, so nothing it finds is lost — this task wires that up. In build terms: route agentic failures into the defect loopback (QA‑14) and uncertain ones into the SME queue (QA‑23), using the same triage and WCAG‑level severity mapping as the static checks. Edge case: an agentic finding and a static finding for the same element/criterion should be de‑duplicated into one defect, not two.
- **Acceptance Criteria:**
  - [ ] Given an agentic failure, when recorded, then a defect opens with the right severity.
  - [ ] Given an uncertain agentic finding, when recorded, then it goes to the SME queue.
  - [ ] Given the same issue found by both the agent and a static check, when recorded, then one defect exists, not two.
  - [ ] Tests cover routing and de‑duplication, with ≥ 90% coverage on new code.

**QA‑22 — Keep the agent advisory until it passes the accuracy bar**
- **Epic:** E10 · **Story:** US‑J2 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑20, QA‑10 · **Blocks:** —
- **Description:** A brand‑new AI agent shouldn't be allowed to block a team's merge until we've proven it's reliable, or a flaky agent will erode trust — so this task keeps it advisory until it earns the right to gate. In build terms: keep agentic results out of the blocking gate until they clear a reliability threshold measured by the internal eval harness (QA‑10); until then, surface them as advisory findings / SME‑review only; once the threshold is met, allow them to feed the a11y gate. Edge case: the reliability status is read per checker/journey‑type, so a proven keyboard check can gate even while a newer check is still advisory.
- **Acceptance Criteria:**
  - [ ] Given the agent is below the reliability threshold, when a run completes, then its findings do not block the gate.
  - [ ] Given the agent has met the threshold, when a run completes, then its findings can block the gate per policy.
  - [ ] Tests cover both states, with ≥ 90% coverage on new code.

---

## EPIC E11 — Human review & a signed conformance report (Phase 2)
A human expert reviews the AI's uncertain calls, and produces a defensible, human‑signed WCAG conformance report — the platform never claims compliance on its own.

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| QA‑23a | Design the SME console + report screens (mockups) | Design | — | ⬜ |
| QA‑23 | Build the SME review console for uncertain findings | Frontend + Backend | QA‑06, QA‑12a, QA‑23a | ⬜ |
| QA‑24 | Draft, sign, and export a conformance / VPAT report | Frontend + Backend | QA‑13, QA‑23 | ⬜ |

**QA‑23a — Design the SME console + report screens (mockups)** — **NEW**
- **Epic:** E11 · **Story:** US‑K1 · **Type:** Design · **Status:** ⬜ Pending · **Depends On:** — · **Blocks:** QA‑23
- **Description:** The SME review console is the only genuinely new screen in this backlog, and the platform's own UI discipline says a screen is not done until it matches its mockup state for state — *"put your screen side-by-side with `docs/design/screens/S-NN.html`; every state must match."* Neither backlog had a task to produce that mockup, so the UI tasks were unbuildable to the platform's own standard. In build terms: produce the `S-NN.html` mockup(s) for the SME review queue — with every state the console needs (loading, empty queue, an item under review, decision submitted, error) — using the existing design system and component catalog, and add the screen→component→endpoint row to `docs/SCREEN_BUILD_MAP.md`. Edge case: the review item shows a screenshot of a real page, so the mockup must show how a wide or tall screenshot is contained without breaking layout.
- **Acceptance Criteria:**
  - [ ] Given the design system, when the mockup is produced, then it uses existing tokens and components and adds no new one-off styles.
  - [ ] Given the console's states, when the mockup is reviewed, then every state listed above is present and labelled.
  - [ ] Given `SCREEN_BUILD_MAP.md`, when read, then it carries the row for this screen.
  - [ ] Given the mockup, when checked for accessibility itself, then it meets the bar we are selling — focus rings, labelled controls, ≥ 4.5:1, status never colour-alone.

**QA‑23 — Build the SME review console for uncertain findings**
- **Epic:** E11 · **Story:** US‑K1 · **Type:** Frontend + Backend · **Status:** ⬜ Pending · **Depends On:** QA‑06, QA‑12a, QA‑23a · **Blocks:** QA‑24
  > **Build it as its own feature folder** — `frontend/src/features/a11y/` — matching the platform's one-owner-per-folder rule in `AGENTS.md`. It reads and writes the QA‑12a findings ledger.
- **Description:** A human accessibility expert needs a simple place to look at the AI's uncertain calls and say "yes, that's a real problem" or "no, that's fine" — both to keep the platform honest and to make our checks smarter over time — and this task builds that review screen. In build terms: build a queue UI that lists each uncertain/low‑confidence AI finding with everything needed to judge it — the element, a screenshot, the cited criterion, and the AI's draft verdict — and lets the reviewer confirm or reject it; record each decision to telemetry (and, internally, to Edvensoft's eval set) and update the finding's status. Edge case: two reviewers opening the same item shouldn't double‑decide — lock an item to the reviewer who opens it, or last‑write‑wins with an audit trail.
- **Acceptance Criteria:**
  - [ ] Given an uncertain finding, when the SME opens the console, then they see the element, screenshot, criterion, and AI draft verdict.
  - [ ] Given the SME confirms or rejects, when they submit, then the finding's status updates and the decision is recorded.
  - [ ] Given two reviewers on one item, when both act, then the outcome is unambiguous and audit‑logged.
  - [ ] Tests cover the adjudication flow and the concurrency rule, with ≥ 90% coverage on new code.

**QA‑24 — Draft, sign, and export a conformance / VPAT report**
- **Epic:** E11 · **Story:** US‑K2 · **Type:** Frontend + Backend · **Status:** ⬜ Pending · **Depends On:** QA‑13, QA‑23 · **Blocks:** —
- **Description:** Clients often need a formal accessibility conformance statement (a VPAT), but no automated tool may claim compliance on its own — so the platform should draft one from the evidence and let a human expert check and sign it. In build terms: create a `conformance` artifact that compiles, per WCAG 2.2 criterion, what was found and by whom (rule/AI/human provenance) from the project's accessibility reports; have the platform generate a draft conformance/VPAT statement from it; let the SME edit and sign it (the platform never marks it "compliant" by itself); export it through the existing gate‑then‑publish flow with the model + prompt versions in the audit log; and keep the wording "risk reduction, not certification". Edge case: attempting to export without a human signature is refused with a clear message.
- **Acceptance Criteria:**
  - [ ] Given a project's reports, when the SME opens conformance, then they see a per‑criterion view with rule/AI/human provenance.
  - [ ] Given the SME edits and signs the draft, when they export, then a signed conformance artifact is produced and audit‑logged with model + prompt versions.
  - [ ] Given no human signature, when export is attempted, then it is refused (the platform never auto‑certifies).
  - [ ] Tests cover draft, sign, export, and the no‑auto‑certify rule, with ≥ 90% coverage on new code.

---

## Definition of Done (every task)
A task is **Done** only when all of these pass — no "mostly done":
- [ ] Behaviour matches the Description and every Acceptance Criterion is demonstrated on a real screen/run.
- [ ] Unit + integration tests written; ≥ 90% coverage on the new code; new tenant‑scoped tables prove RLS isolation.
- [ ] `make test` / `make lint` (backend) and `npm run lint` + `tsc -b` (frontend) pass.
- [ ] Any agent‑file edit (09/09b/09c) passes the platform reference sweep (no leftover local paths; I/O via platform capabilities).
- [ ] An AI finding never asserts conformance on its own; low confidence routes to a human; axe failures always stand.
- [ ] The task box is ticked `🟢` here with a one‑line "what shipped" note.

**Two additions after the 2026‑08‑12 source review:**
- [ ] **No fixture-only completions.** If a task's behaviour can only be shown with fabricated data, say so at review and name what would prove it for real. Several tasks in this backlog could be made to pass their tests while demonstrating nothing — that is the failure this correction pass exists to prevent.
- [ ] **Coverage must actually be measured.** `pytest-cov` is not installed today, so this bar is currently unverifiable. Add it plus a **module-scoped** `make cov` before QA‑01 — scoped deliberately, because running the full backend suite is known to be killed.

**Cross‑refs:** what the research got wrong = `RESEARCH_CORRECTIONS.md`; build order + dependency map = `BUILD_PLAN_QA.md`; journeys = `USER_JOURNEYS.md`; the other phases = `TASK_BACKLOG_OTHER_PHASES.md`.
