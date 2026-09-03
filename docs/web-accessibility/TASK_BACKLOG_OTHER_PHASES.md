# Task Backlog — Web Accessibility, Other Phases (Shift‑Left)

**Total Tasks:** 9 (OP‑01 … OP‑09)
**Estimates:** deferred by team decision — detail + dependencies only.
**Prerequisite:** the QA build (`BUILD_PLAN_QA.md` / `TASK_BACKLOG_QA.md`) is done first. Every task here reuses the `a11yai` capability, the WCAG 2.2 knowledge base, and the confidence gate built there; dependencies on QA tasks are named (e.g. "Depends On: QA‑03").

> **How to read a task:** same as the QA backlog — a plain intent sentence, then "In build terms:" with concrete behaviour and edge cases, then given/when/then acceptance criteria you can hand‑check.

## Status legend
⬜ Pending · 🟡 In Progress · 🟢 Done · 🔴 Blocked

## Epics in this backlog
- **E3 — Catch accessibility problems in the design, before code**
- **E4 — Catch accessibility problems at code review, before testing**
- **E8 — Know an imported app's accessibility state when it's onboarded**
- **E‑COMP — The two brownfield end‑to‑end flows (remediate / keep building)**

---

## EPIC E3 — Catch accessibility problems in the design, before code
The cheapest place to fix an accessibility problem is while it's still a wireframe. This epic runs the accessibility spec and the AI checks in the design phase and gates the design on serious issues.

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| OP‑01 | Move the design accessibility spec to WCAG 2.2 | Agent edit | QA‑04 | ⬜ |
| OP‑02 | Run the AI design checks on the wireframes | Agent edit + Backend | QA‑03 | ⬜ |
| OP‑03 | Add the accessibility design gate | Backend | QA‑08, OP‑02 | ⬜ |

**OP‑01 — Move the design accessibility spec to WCAG 2.2**
- **Epic:** E3 · **Story:** US‑C1 · **Type:** Agent edit · **Status:** ⬜ Pending · **Depends On:** QA‑04 · **Blocks:** OP‑02, OP‑07
- **Description:** Accessibility should start in the design, and the design phase currently writes its accessibility spec against WCAG 2.1 — this task moves the design spec up to 2.2 so designers and everyone downstream work to the same target the tests use. In build terms: in the design agent (`agents/05_ux_design`), change Step 7 (Accessibility Requirements) and the Step 5a contrast checks from WCAG 2.1 AA to 2.2 AA, so the generated `docs/ux/ACCESSIBILITY.md` lists the 2.2 criteria with project‑specific guidance; treat this as a "data‑reference" edit under the 75/15/10 rule (don't rewrite the design reasoning) and run the reference sweep. Edge case: don't miss 2.1 references outside Step 7 (the Evidence Base, the DESIGN‑SYSTEM component notes, the quality gate).
- **Acceptance Criteria:**
  - [ ] Given the design agent runs, when it generates the spec, then `ACCESSIBILITY.md` lists WCAG 2.2 criteria with project‑specific guidance.
  - [ ] Given the agent body, when searched, then no "WCAG 2.1" references remain in the accessibility content.
  - [ ] Given the reference sweep, when run, then it passes.

**OP‑02 — Run the AI design checks on the wireframes**
- **Epic:** E3 · **Story:** US‑C2 · **Type:** Agent edit + Backend · **Status:** ⬜ Pending · **Depends On:** QA‑03 · **Blocks:** OP‑03
- **Description:** If we can spot an accessibility problem while it's still a wireframe, it's far cheaper to fix than after it's built — this task runs the AI checks that make sense on a design against the wireframes. In build terms: extend the design agent to call the `a11yai` checks that apply to a static design — alt‑text intent, colour‑only meaning, heading/label descriptiveness, and target size — against the rendered wireframe states (`docs/design/screens/S‑NN.html`), and surface the findings in the design phase console with confidence and a cited criterion. Edge case: a wireframe state that is intentionally a placeholder (e.g. an empty state with no real content) shouldn't generate noise — skip checks that don't apply to it.
- **Acceptance Criteria:**
  - [ ] Given a set of wireframe states, when the design phase runs, then AI findings are produced against them with a criterion + confidence.
  - [ ] Given a wireframe with a colour‑only status indicator, when checked, then a 1.4.1 finding is raised.
  - [ ] Tests cover a sample wireframe (good and bad), with ≥ 90% coverage on new code.

**OP‑03 — Add the accessibility design gate**
- **Epic:** E3 · **Story:** US‑C3 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑08, OP‑02 · **Blocks:** OP‑09
- **Description:** A design with a serious accessibility flaw shouldn't move into build — this task adds the checkpoint that holds the design phase until such flaws are resolved. In build terms: add an accessibility design gate (a control‑plane Approval) that blocks the design phase while there's an unresolved AI‑confirmed Level‑A design issue; reuse the QA‑08 policy shape; route low‑confidence findings to the SME rather than blocking. Edge case: a design issue the designer consciously accepts (with a recorded reason) can be marked accepted so it doesn't block indefinitely — the acceptance is audit‑logged.
- **Acceptance Criteria:**
  - [ ] Given an unresolved AI‑confirmed Level‑A design issue, when the gate evaluates, then design cannot pass.
  - [ ] Given only low‑confidence findings, when the gate evaluates, then design can pass and the findings go to review.
  - [ ] Given an explicitly accepted issue with a reason, when the gate evaluates, then it does not block and the acceptance is logged.
  - [ ] Tests cover block, pass, and accepted, with ≥ 90% coverage on new code.

---

## EPIC E4 — Catch accessibility problems at code review, before testing
By the time code exists, some problems (a fake button, a mislabelled field) are best caught at review. This epic adds the AI "meaning" checks to the review step and sends criticals into the existing fix loop.

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| OP‑04 | Add the AI semantic checks to code review | Agent edit + Backend | QA‑03 | ⬜ |
| OP‑05 | Send AI‑confirmed criticals into the remediation loop | Backend | OP‑04, QA‑06 | ⬜ |

**OP‑04 — Add the AI semantic checks to code review**
- **Epic:** E4 · **Story:** US‑D1 · **Type:** Agent edit + Backend · **Status:** ⬜ Pending · **Depends On:** QA‑03 · **Blocks:** OP‑05
- **Description:** By the time code is written, some accessibility problems are best caught at review, before testing — this task adds the AI "meaning" checks to the code‑review step that already checks accessibility basics. In build terms: extend the code‑review agent's Step 11 so that, on a pull request, the platform runs the `a11yai` semantic checks (fake‑semantics, label) against the rendered PR preview + accessibility tree, in addition to the existing rule checks, and merges the findings into the `code_review` artifact with a criterion + confidence. Edge case: a backend‑only PR with no UI changes produces no a11y findings (the checks are scoped to changed front‑end files, matching how Step 11 already scopes itself).
- **Acceptance Criteria:**
  - [ ] Given a PR that changes UI, when review runs, then AI a11y findings appear in the `code_review` alongside the existing checks.
  - [ ] Given a PR that introduces a div‑as‑button, when reviewed, then a 4.1.2 finding is raised.
  - [ ] Given a backend‑only PR, when reviewed, then no a11y findings are raised.
  - [ ] Tests cover a UI PR (good and bad) and a backend‑only PR, with ≥ 90% coverage on new code.

**OP‑05 — Send AI‑confirmed criticals into the remediation loop**
- **Epic:** E4 · **Story:** US‑D2 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** OP‑04, QA‑06 · **Blocks:** OP‑08, OP‑09
- **Description:** An accessibility problem found at review should be fixed before the code merges, using the same fix‑and‑recheck loop the platform already runs — this task connects AI review findings to that loop. In build terms: wire AI‑confirmed accessibility criticals from OP‑04 into the existing 07↔08 remediation loop — a critical opens a REM‑C child WorkItem and blocks the merge gate; the fix re‑runs through the targeted re‑review; the item closes when the check passes. Reuse the loop; add no new mechanism. Edge case: a warning‑level (non‑critical) a11y finding becomes a REM‑W that is tracked but doesn't block the merge, matching how the loop already treats warnings.
- **Acceptance Criteria:**
  - [ ] Given an AI‑confirmed a11y critical at review, when recorded, then a REM‑C item opens and the merge gate is blocked.
  - [ ] Given the fix passes re‑review, when recorded, then the item closes and the gate can pass.
  - [ ] Given an AI a11y warning, when recorded, then a REM‑W is tracked but the merge is not blocked.
  - [ ] Tests cover the critical block/close cycle and the warning case, with ≥ 90% coverage on new code.

---

## EPIC E8 — Know an imported app's accessibility state when it's onboarded
When a team imports an existing app, we should immediately tell them where it stands on accessibility and hand its screen list to the audit.

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| OP‑06 | Assess accessibility posture during onboarding | Agent edit | QA‑04 | ⬜ |
| OP‑07 | Offer to generate a missing accessibility spec | Agent edit | OP‑01, OP‑06 | ⬜ |

**OP‑06 — Assess accessibility posture during onboarding**
- **Epic:** E8 · **Story:** US‑H1 · **Type:** Agent edit · **Status:** ⬜ Pending · **Depends On:** QA‑04 · **Blocks:** QA‑17, OP‑07
- **Description:** When a team imports an existing app, we should immediately tell them where it stands on accessibility and hand the list of its screens to the audit — this task adds that assessment to onboarding. In build terms: add a step to the onboarding agent that records, in the Discovery Report, whether the project has a `docs/ux/ACCESSIBILITY.md`, what WCAG level (if any) it claims, and whether axe currently passes; flag a missing spec as a gap; and register the app's screens/routes so the baseline audit (QA‑17) can consume them. Edge case: if the app can't be run/reached during onboarding, record posture as "unknown — app not reachable" rather than guessing, and still register any routes discovered from the code/config.
- **Acceptance Criteria:**
  - [ ] Given an onboarded project, when onboarding runs, then the Discovery Report contains an accessibility‑posture section and a gap flag if no spec exists.
  - [ ] Given onboarding completes, when the baseline audit starts, then it can read the registered route list.
  - [ ] Given the app can't be reached, when onboarding runs, then posture is recorded as "unknown — not reachable", not a false pass/fail.
  - [ ] Tests cover the posture section, route registration, and the unreachable case, with ≥ 90% coverage on new code.

**OP‑07 — Offer to generate a missing accessibility spec**
- **Epic:** E8 · **Story:** US‑H2 · **Type:** Agent edit · **Status:** ⬜ Pending · **Depends On:** OP‑01, OP‑06 · **Blocks:** —
- **Description:** If an imported app has no accessibility spec, teams should be able to generate one so future work has a target — this task offers that, review‑gated. In build terms: when OP‑06 flags a missing `ACCESSIBILITY.md`, offer to generate one at WCAG 2.2 using the design agent's spec generator (OP‑01), registered as a normal review‑gated artifact. Edge case: if the user declines, onboarding continues cleanly and the gap flag stays, so it's visible later.
- **Acceptance Criteria:**
  - [ ] Given an onboarded project with no spec, when the user opts in, then a WCAG 2.2 `ACCESSIBILITY.md` is generated behind a review gate.
  - [ ] Given the user declines, when onboarding continues, then no spec is created and the gap flag remains.
  - [ ] Tests cover the opt‑in and decline paths, with ≥ 90% coverage on new code.

---

## EPIC E‑COMP — The two brownfield end‑to‑end flows
Wires the earlier pieces into the full "remediate an existing app" and "keep building it accessibly" journeys.

| ID | Title | Type | Depends On | Status |
|----|-------|------|-----------|--------|
| OP‑08 | Run a remediation campaign from the baseline backlog | Backend | QA‑18, OP‑05 | ⬜ |
| OP‑09 | Hold new work on an onboarded app to WCAG 2.2 | Backend | OP‑03, OP‑05, QA‑15 | ⬜ |

**OP‑08 — Run a remediation campaign from the baseline backlog**
- **Epic:** E‑COMP · **Story:** US‑M1 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** QA‑18, OP‑05 · **Blocks:** —
- **Description:** Fixing an inherited app's accessibility debt should be a managed campaign — the audit's backlog becomes prioritised fixes that flow through fix → review → re‑test with visible progress — and this task wires that end to end. In build terms: turn the QA‑18 baseline defect backlog into prioritised remediation child WorkItems that flow through the existing loop (07 fix → 08 re‑review → 09 re‑test), track progress against the baseline, and rely on the regression suite to catch new breakage; reuse the loop and add a simple progress view. Edge case: an item that can't be auto‑fixed (needs a design decision) is flagged for human triage instead of looping forever.
- **Acceptance Criteria:**
  - [ ] Given a baseline backlog, when the campaign runs, then its items flow through fix → review → re‑test and close on pass.
  - [ ] Given items are being fixed, when viewed, then progress against the baseline is visible.
  - [ ] Given a fix breaks something else, when the regression suite runs, then it is caught.
  - [ ] Given an item that needs a design decision, when reached, then it is flagged for human triage, not looped.
  - [ ] Tests cover an item's full close cycle and the triage flag, with ≥ 90% coverage on new code.

**OP‑09 — Hold new work on an onboarded app to WCAG 2.2**
- **Epic:** E‑COMP · **Story:** US‑M2 · **Type:** Backend · **Status:** ⬜ Pending · **Depends On:** OP‑03, OP‑05, QA‑15 · **Blocks:** —
- **Description:** Once an existing app is onboarded, any new feature on it should be held to the same accessibility standard as a brand‑new project — this task makes the new‑work path run through the full shift‑left spine. In build terms: let an onboarded project resume the pipeline so new features flow through design (OP‑01/02/03) → review (OP‑04/05) → test (the QA plan), with the a11y gate applied to new PRs and legacy debt tracked separately from new‑work conformance. Edge case: a new feature that touches an old, not‑yet‑remediated screen is judged only on what it changes, so old debt doesn't block unrelated new work.
- **Acceptance Criteria:**
  - [ ] Given a new feature on an onboarded project, when it goes through the pipeline, then it passes the same a11y gates as greenfield.
  - [ ] Given legacy debt exists, when new work is tracked, then the two are reported separately.
  - [ ] Given a new feature touches an old screen, when gated, then it is judged on its changes, not the pre‑existing debt.
  - [ ] Tests cover a new‑feature pass through the gates and the old‑screen case, with ≥ 90% coverage on new code.

---

## Definition of Done (every task)
Same as the QA backlog: behaviour matches the Description and every Acceptance Criterion is demonstrated; tests + ≥ 90% coverage + RLS where relevant; lint/type‑check green; agent‑file edits pass the reference sweep; AI never asserts conformance alone; box ticked `🟢` with a one‑line note. **Additionally:** every design/review finding must cite the same WCAG 2.2 criterion the QA phase uses (one criterion registry, QA‑05 — no divergence between phases).

**Cross‑refs:** build order + dependencies = `BUILD_PLAN_OTHER_PHASES.md`; the QA engine this depends on = `BUILD_PLAN_QA.md`; journeys = `USER_JOURNEYS.md`.
