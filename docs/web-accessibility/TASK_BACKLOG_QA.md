# Task Backlog — Web Accessibility QA (POC + Phase 2)

**Total Tasks:** 24 (QA‑01 … QA‑24)
**Estimates:** deferred by team decision — this backlog carries detail + dependencies, not story points or sprints.

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
| QA‑01 | Create the `a11yai` capability front door | Backend | — | ⬜ |
| QA‑02 | Build the model switchboard behind `a11yai` | Backend | QA‑01 | ⬜ |
| QA‑03 | Build the four accessibility AI checkers | Backend (AI) | QA‑01, QA‑02, QA‑04 | ⬜ |

**QA‑01 — Create the `a11yai` capability front door** *(critical path)*
- **Epic:** E1 · **Story:** US‑A1 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** — · **Blocks:** QA‑02, QA‑03
- **Description:** Right now nothing in the platform can ask an AI "is this screen accessible?", and we want that request to work the same way as every other integration — through a named capability so the AI model underneath can be swapped without touching the callers. This task creates that front door, called `a11yai`. In build terms: add a new capability contract `a11yai` alongside the existing ones in `backend/integrations/capabilities.py`, with four methods — `check_alt`, `check_semantics`, `check_color`, `check_label` — each accepting the element / screenshot / surrounding context it needs and returning **one standard result object**: the WCAG criterion it judged, a verdict (`pass` / `fail` / `uncertain`), a confidence from 0 to 1, the evidence it used, and a suggested fix. Wire it so `get_capability(tenant, "a11yai")` returns the right implementation for that tenant, exactly like `get_capability(tenant, "codehost")` does today, and keep it tenant‑scoped so one tenant's checks can never read another's data. Edge cases: an unconfigured tenant returns a clear "capability not configured" error, not a crash; a method called with missing inputs returns an `uncertain` result with a reason, never a partial object.
- **Acceptance Criteria:**
  - [ ] Given a tenant with `a11yai` configured, when code calls `get_capability(tenant, "a11yai")`, then it returns a working object exposing all four methods.
  - [ ] Given any of the four methods runs on a sample element, when it returns, then the result always contains criterion, verdict, confidence, evidence, and suggested_fix — no field missing.
  - [ ] Given a second tenant, when it uses the capability, then it cannot read the first tenant's inputs or results (proven by an RLS test).
  - [ ] Unit + integration tests cover capability resolution and the result shape, with ≥ 90% coverage on the new code.

**QA‑02 — Build the model switchboard behind `a11yai`** *(critical path)*
- **Epic:** E1 · **Story:** US‑A2 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑01 · **Blocks:** QA‑03
- **Description:** The checks will use different AI models for different jobs — a cheaper text model to read code and a vision model to "look" at screenshots — and we must be able to change those models (hosted or self‑hosted) without rewriting the checkers, and never pay to re‑analyse a screen that hasn't changed. This task builds the one switchboard every check goes through. In build terms: create `backend/a11y/gateway.py` with a single function the checkers call to run a model request. It routes text‑only checks (label, semantics) to the configured text model and vision checks (alt, colour) to the configured vision model; it reads *which* concrete model/endpoint to use from tenant config, so "hosted vs self‑hosted" is a setting, not code; it forces temperature 0 and pins the exact model version so results are repeatable; and it caches every result under a hash of its inputs, so an identical request returns the stored answer instead of calling the model again. Every call records the model name, model version, and prompt version for the audit log. Edge cases: a model timeout or error returns an `uncertain` result (never a hard fail from an outage); a cache hit must never be stale for changed input because the key includes the input hash.
- **Acceptance Criteria:**
  - [ ] Given a text check (label), when it runs, then the gateway sends it to the configured text model; given a vision check (colour), then it sends it to the vision model.
  - [ ] Given the same input checked twice, when the second call runs, then it is served from cache and no model call is made.
  - [ ] Given a tenant configured for a self‑hosted model, when a check runs, then it uses that model with zero change to checker code.
  - [ ] Given any completed check, when inspected, then the model name, version, and prompt version were recorded.
  - [ ] Tests cover routing, caching, timeout‑to‑uncertain, and the audit record, with ≥ 90% coverage on new code.

**QA‑03 — Build the four accessibility AI checkers** *(critical path)*
- **Epic:** E1 · **Story:** US‑A3 · **Type:** Backend (AI) · **Status:** ⬜ Pending · **Depends On:** QA‑01, QA‑02, QA‑04 · **Blocks:** QA‑12, QA‑16, QA‑20
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
| QA‑04 | Load WCAG 2.2 + ACT into the knowledge base | Backend | — | ⬜ |
| QA‑05 | Build the "who checks which criterion" registry | Backend | QA‑04 | ⬜ |

**QA‑04 — Load WCAG 2.2 + ACT into the knowledge base** *(critical path)*
- **Epic:** E2 · **Story:** US‑B1 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** — · **Blocks:** QA‑03, QA‑05, QA‑11, OP‑01, OP‑06
- **Description:** For the AI to judge against the real rules (and cite them), it needs the exact wording of each WCAG 2.2 success criterion on hand — this task loads the standard into the platform's existing search index and gives the checkers a way to pull the precise rule they're judging. In build terms: ingest the WCAG 2.2 success criteria text (and the matching ACT rule text) into the existing pgvector Knowledge Index, and add a small helper that, given a criterion number like "1.4.1", returns that criterion's exact text to drop into a checker's prompt. Version the loaded set so a future WCAG update is a data reload, not a code change. Edge case: a request for a criterion not in the set returns a clear "unknown criterion" result, never an empty string that silently weakens a prompt.
- **Acceptance Criteria:**
  - [ ] Given a criterion number, when the helper is called, then it returns that criterion's exact WCAG 2.2 text.
  - [ ] Given a checker builds its prompt, when it runs, then the relevant criterion text is present as grounding.
  - [ ] Given the knowledge base is reloaded with a newer version, when checks run, then no checker code changes.
  - [ ] Tests cover retrieval for a sample of criteria and the unknown‑criterion case, with ≥ 90% coverage on new code.

**QA‑05 — Build the "who checks which criterion" registry**
- **Epic:** E2 · **Story:** US‑B2 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑04 · **Blocks:** QA‑12
- **Description:** The platform needs to know, for each of the 55 WCAG A/AA criteria, whether the rule scanner, our AI, or a human is responsible for it — and whether it's a POC or a Phase‑2 item — so it can route each check correctly and never silently skip one. This task builds that lookup. In build terms: create a registry (a config table) of the 55 Level A/AA criteria, each row tagged with its **owner** (rule / AI / human) and its **tier** (POC / Phase 2), taken from Report 1 Addendum A; expose a lookup that returns owner + tier for any criterion. The testing flow uses it to decide which engine runs each criterion. Edge case: loading must fail loudly if the set isn't exactly 55 or a criterion has no owner — a silent gap here means an un‑checked criterion later.
- **Acceptance Criteria:**
  - [ ] Given a criterion number, when the registry is queried, then it returns the owner (rule/AI/human) and tier (POC/Phase 2).
  - [ ] Given the loaded set, when validated, then there are exactly 55 criteria and every one has exactly one owner and one tier (no gaps, no duplicates).
  - [ ] Given spot checks, when queried, then 1.4.3 = rule, 1.1.1 = AI, and 1.2.2 = human.
  - [ ] Tests assert the count and the spot checks, with ≥ 90% coverage on new code.

---

## EPIC E‑COST — Keep AI findings trustworthy and affordable
An AI can be confidently wrong and expensive at scale. This epic makes sure an unsure AI verdict never blocks a team or overrides a hard rule, and that checks stay cheap and fully auditable.

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| QA‑06 | Add the confidence gate & "AI never overrides a rule" safety valve | Backend | QA‑03 | ⬜ |
| QA‑07 | Only check what changed; meter cost; log the model per finding | Backend | QA‑02 | ⬜ |

**QA‑06 — Add the confidence gate & "AI never overrides a rule" safety valve** *(critical path)*
- **Epic:** E‑COST · **Story:** US‑L0 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑03 · **Blocks:** QA‑12, QA‑14, OP‑05
- **Description:** In a compliance setting a confidently wrong "fail" is as damaging as a miss, so the platform must never let an unsure AI verdict block a team or overturn a definite rule result — this task builds the safety valve between raw AI output and anything shown or acted on. In build terms: create `backend/a11y/triage.py`. For every AI finding, compare its confidence to a per‑checker threshold — high confidence becomes a real finding, medium or low becomes "**needs human review**" rather than "fail". Enforce a hard rule that an AI result can never overturn a deterministic axe failure (axe always wins where they disagree). Require an "evidence" value on every finding and refuse to treat an evidence‑less finding as a hard failure. Thresholds are configurable per checker. Edge case: exactly‑at‑threshold rounds toward "review" (be conservative).
- **Acceptance Criteria:**
  - [ ] Given an AI finding below its checker's threshold, when triaged, then it is marked "needs human review", not "fail".
  - [ ] Given axe reports a failure and the AI disagrees, when triaged, then the axe failure stands.
  - [ ] Given a finding with no evidence, when triaged, then it is never reported as a hard failure.
  - [ ] Tests cover the threshold split, the axe‑wins rule, and the evidence rule, with ≥ 90% coverage on new code.

**QA‑07 — Only check what changed; meter cost; log the model per finding**
- **Epic:** E‑COST · **Story:** US‑L1 / US‑L2 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑02 · **Blocks:** —
- **Description:** With many tenants checking many screens, unbounded AI calls would be slow and costly, and every compliance result must be traceable to the exact model that produced it — this task keeps cost down and makes every finding auditable. In build terms: run AI checks only on the screens/elements that changed since the last run (diff‑scope), reusing the gateway's content‑hash cache; record the AI cost per tenant per run in the platform's existing metering; and make sure the model name + version + prompt version is written onto every finding in Run History. Edge case: the very first run of a project has no prior state, so it checks everything once and caches for next time.
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
| QA‑08 | Create the accessibility gate policy + reviewer role | Backend | — | ⬜ |
| QA‑15 | Enforce the accessibility test gate at the end of testing | Backend | QA‑08, QA‑14 | ⬜ |

**QA‑08 — Create the accessibility gate policy + reviewer role**
- **Epic:** E‑GATE · **Story:** US‑F1 / US‑F2 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** — · **Blocks:** QA‑15, QA‑19, OP‑03
- **Description:** Teams need one clear, adjustable checkpoint for "is this accessible enough to move on?", and someone accountable for accessibility sign‑off — this task creates that gate policy and role without enforcing anything yet. In build terms: add an accessibility gate policy object to the Gate/Approval service with configurable thresholds — which severities block, and the confidence bar below which findings never block — editable per project; and add an "Accessibility SME / reviewer" role to the RBAC role→phase→gate matrix (for the POC it may map onto the existing QA Lead). This task only makes the policy and role exist and be editable; enforcement is QA‑15. Edge case: a project with no explicit policy inherits a sensible default (block on Critical/Serious, confidence bar at the checker default).
- **Acceptance Criteria:**
  - [ ] Given a project, when an admin opens the a11y gate policy, then they can set which severities block and the confidence threshold, and save it.
  - [ ] Given the RBAC matrix, when inspected, then the Accessibility reviewer role exists and can be assigned (or mapped to QA Lead).
  - [ ] Given a project with no explicit policy, when read, then it returns the documented default.
  - [ ] Tests cover policy read/write, the default, and role assignment, with ≥ 90% coverage on new code.

**QA‑15 — Enforce the accessibility test gate at the end of testing** *(critical path)*
- **Epic:** E‑GATE · **Story:** US‑F1 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑08, QA‑14 · **Blocks:** QA‑19, OP‑09
- **Description:** The pipeline must actually stop when a screen has a real accessibility failure and let it through when it doesn't — this task makes the gate enforce the QA‑08 policy on the merged findings. In build terms: at the end of the testing phase, evaluate the merged axe + AI findings against the project's policy — set the gate Approval to *blocked* when there is any axe or AI‑confirmed Critical/Serious at WCAG 2.2, and *passable* when there are none; low‑confidence‑only findings never block. Keep it a control‑plane Approval, consistent with every other gate. Edge case: a run that errored (couldn't complete) blocks with an "incomplete run" reason rather than passing by default.
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
| QA‑10 | Build the internal accuracy harness (team‑only) | Internal | QA‑09 | ⬜ |

**QA‑09 — Build the internal golden set (team‑only)**
- **Epic:** E‑EVAL · **Story:** US‑G1 · **Type:** Internal (not a tenant feature) · **Status:** ⬜ Pending · **Depends On:** QA‑03 · **Blocks:** QA‑10
- **Description:** Before we put these AI checks in front of tenants, we (Edvensoft) need an answer‑key to measure how often they're right — a set of real screens we've labelled by hand against WCAG 2.2. This is our internal quality control and must never ship to tenants. In build terms: assemble a labelled dataset of screens/components with the correct WCAG 2.2 verdict per relevant criterion, adjudicated by an accessibility expert; store it inside Edvensoft's own repo/CI, versioned; keep it entirely out of tenant databases and the platform UI. Edge case: any disagreement between two labellers is resolved by a third adjudication and the final call recorded — the golden set must be trustworthy or the numbers it produces are meaningless.
- **Acceptance Criteria:**
  - [ ] Given the dataset, when inspected, then each item has an expert‑adjudicated verdict per relevant criterion and a version tag.
  - [ ] Given the platform code, when searched, then the golden set is never referenced by tenant‑facing code or stored in tenant data.
  - [ ] Given a new dataset version, when added, then the previous version is retained.

**QA‑10 — Build the internal accuracy harness (team‑only)**
- **Epic:** E‑EVAL · **Story:** US‑G2 · **Type:** Internal (not a tenant feature) · **Status:** ⬜ Pending · **Depends On:** QA‑09 · **Blocks:** QA‑22
- **Description:** We need to know, in numbers, how accurate each checker is, and to stop a model or prompt change from quietly degrading it — this task builds the scorer that runs in our CI. In build terms: build a scorer that runs each checker over the golden set and reports precision, recall, and F1 per checker; wire it into Edvensoft CI so that promoting a new model or prompt version is blocked if any checker's accuracy drops below the last accepted numbers. Edge case: a new checker with no prior baseline records its first numbers as the baseline rather than blocking.
- **Acceptance Criteria:**
  - [ ] Given the golden set, when the harness runs, then it reports precision/recall/F1 per checker.
  - [ ] Given a model/prompt change that lowers a checker's accuracy, when CI runs, then promotion is blocked.
  - [ ] Given no regression, when CI runs, then promotion is allowed.

---

## EPIC E5 — Test every screen for accessibility (rules + AI)
This epic upgrades the testing phase so one run scans with the rules **and** the AI at WCAG 2.2, reports both together, and the automated suite runs both.

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| QA‑11 | Move the testing agent's scan to WCAG 2.2 | Agent edit | QA‑04 | ⬜ |
| QA‑12 | Add the AI‑checks pass to the testing agent | Agent edit + Backend | QA‑03, QA‑06, QA‑11 | ⬜ |
| QA‑13 | Add source/confidence/fix columns to the report | Backend | QA‑12 | ⬜ |
| QA‑16 | Make the test‑automation agent script the AI checks | Agent edit | QA‑12 | ⬜ |

**QA‑11 — Move the testing agent's scan to WCAG 2.2**
- **Epic:** E5 · **Story:** US‑E1 · **Type:** Agent edit · **Status:** ⬜ Pending · **Depends On:** QA‑04 · **Blocks:** QA‑12
- **Description:** The testing agent currently scans against the older WCAG 2.1, but the whole POC targets 2.2, so the scan and the agent's wording need to move up one version — a small, careful edit that leaves the agent's testing method untouched. In build terms: in `agents/09_testing/agent.md`, change the axe scan configuration and every standard reference in Step 9 (plus the Evidence Base and gate wording) from "WCAG 2.1 AA" to "WCAG 2.2 AA". Treat this as a "data‑reference" edit under the platform's 75/15/10 migration rule — do not rewrite the agent's reasoning — and run the platform's reference sweep afterward. Edge case: don't miss references outside Step 9 (Evidence Base, quality gate, severity notes) — a stray "2.1" there causes confusion downstream.
- **Acceptance Criteria:**
  - [ ] Given the testing agent runs, when Step 9 executes, then axe scans at WCAG 2.2.
  - [ ] Given the agent body, when searched, then no "WCAG 2.1" references remain in the accessibility content.
  - [ ] Given the reference sweep, when run on the edited agent, then it passes.

**QA‑12 — Add the AI‑checks pass to the testing agent** *(critical path)*
- **Epic:** E5 · **Story:** US‑E2 · **Type:** Agent edit + Backend · **Status:** ⬜ Pending · **Depends On:** QA‑03, QA‑06, QA‑11 · **Blocks:** QA‑13, QA‑14, QA‑16, QA‑17
- **Description:** Today the testing phase only runs the rule scanner; this task adds the AI checks right after it, so a single test run reports both the rule findings and the "meaning" findings the rules can't see, side by side. In build terms: extend Step 9 of the testing agent so that, after axe runs on a screen, the platform calls `a11yai.check_*` on that screen's candidate elements — images for alt, controls for semantics/label, coloured status indicators for colour — and merges the returned findings into the same accessibility report, each tagged with its source (rule or AI), confidence, and cited criterion. AI findings pass through the QA‑06 triage before they land in the report, so low‑confidence ones show as "needs review". Edge case: a screen with no candidate elements for a given checker simply produces no AI finding for it (not an error).
- **Acceptance Criteria:**
  - [ ] Given a screen, when Step 9 runs, then the report contains both axe findings and AI findings in one place.
  - [ ] Given each AI finding, when shown, then it carries source = AI, a confidence, and a cited WCAG 2.2 criterion.
  - [ ] Given a low‑confidence AI finding, when merged, then it appears as "needs review", not a failure.
  - [ ] Tests cover the merged report on a sample screen, with ≥ 90% coverage on new code.

**QA‑13 — Add source/confidence/fix columns to the report**
- **Epic:** E5 · **Story:** US‑E2 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑12 · **Blocks:** QA‑24
- **Description:** A reader of the accessibility report should be able to tell at a glance which findings came from the rules vs the AI, how sure the AI is, and what fix is suggested — this task adds those columns without disturbing the existing report. In build terms: extend the `test_report` / `a11y_report` artifact to carry `source` (rule/AI/human), `confidence`, `criterion`, and `suggested_fix` per finding, keep every existing field, and make the finding render readably in the platform UI/preview. Edge case: an older report saved before this change must still open (backward compatible — missing fields render as blank, not an error).
- **Acceptance Criteria:**
  - [ ] Given a report with mixed findings, when viewed, then each row shows source, confidence, criterion, and suggested fix.
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
| QA‑14 | Route accessibility findings into the defect loopback | Backend | QA‑12, QA‑06 | ⬜ |

**QA‑14 — Route accessibility findings into the defect loopback** *(critical path)*
- **Epic:** E9 · **Story:** US‑I1 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑12, QA‑06 · **Blocks:** QA‑15, QA‑18, QA‑21
- **Description:** When a real accessibility problem is found it should automatically become a tracked bug that a developer fixes and that closes itself once the fix passes — exactly the loop the platform already uses for other test failures — so this task connects accessibility findings to that loop. In build terms: wire the merged findings into the existing defect loopback (PG11): a high‑confidence AI‑confirmed finding or an axe violation opens a `defect` with severity mapped from the WCAG level (the mapping already lives in agent 09); a low‑confidence finding instead goes to the SME review queue (QA‑23), not a defect; and when a later run shows the check passing, the defect auto‑closes. Edge case: a finding that flips between runs (present, then absent, then present) must not spawn duplicate defects — reopen the same one.
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
- **Description:** A user who imports an existing app should be able to point the accessibility tests straight at it, even though it never went through our design phase and has no accessibility spec — this task lets the testing engine run against an already‑built app's live pages. In build terms: add an entry point that runs axe + the `a11yai` checks against an onboarded project's registered routes/screens (the route list comes from onboarding, OP‑06) without requiring a `docs/ux/ACCESSIBILITY.md`; reuse the same Step‑9 machinery, changing only where the screen list comes from. Edge case: a route that fails to load (auth wall, 404, timeout) is reported as an audit error for that route, never silently skipped.
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
| QA‑23 | Build the SME review console for uncertain findings | Frontend + Backend | QA‑06 | ⬜ |
| QA‑24 | Draft, sign, and export a conformance / VPAT report | Frontend + Backend | QA‑13, QA‑23 | ⬜ |

**QA‑23 — Build the SME review console for uncertain findings**
- **Epic:** E11 · **Story:** US‑K1 · **Type:** Frontend + Backend · **Status:** ⬜ Pending · **Depends On:** QA‑06 · **Blocks:** QA‑24
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
- [ ] Any agent‑file edit (09/09b) passes the platform reference sweep (no leftover local paths; I/O via platform capabilities).
- [ ] An AI finding never asserts conformance on its own; low confidence routes to a human; axe failures always stand.
- [ ] The task box is ticked `🟢` here with a one‑line "what shipped" note.

**Cross‑refs:** build order + dependency map = `BUILD_PLAN_QA.md`; journeys = `USER_JOURNEYS.md`; the other phases = `TASK_BACKLOG_OTHER_PHASES.md`.
