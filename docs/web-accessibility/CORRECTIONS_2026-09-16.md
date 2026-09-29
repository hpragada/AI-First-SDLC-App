# Corrections made on 2026-09-16 — what changed, and why

**Why this file exists.** These changes fix statements that were already wrong in the repository. They are **not** part of the shift-left accessibility work proposed in [`WCAG_ACROSS_THE_LIFECYCLE.md`](WCAG_ACROSS_THE_LIFECYCLE.md) — that work has not been approved and none of it is built here. The team asked for the inconsistencies to be settled first, so that whenever the larger work does start, it starts from a base that says true things. This file records each change and the evidence behind it, so that nobody later has to guess why an agent or a document was edited.

**Approved by the team on 2026-09-16.** Three items were deliberately **excluded** and remain open — see §6.

---

## 1. Every agent now names WCAG 2.2, not 2.1

**The problem.** The platform works to **WCAG 2.2 AA** everywhere that matters: the criteria dataset (`backend/apps/a11y/data/wcag22.json`), the design gate's checklist (`backend/apps/gates/wcag.py`), the default standard version (`backend/apps/a11y/wcag.py:42`, `DEFAULT_VERSION = "2.2"`), and agents 09, 09b, 09c and 09d. But five agent bodies still taught **WCAG 2.1**, the 2018 edition. The platform contradicted itself, and the contradiction reached client-visible output: a live greenfield project on the shared server (PeopleDesk, QA-C tenant) has an `accessibility` artifact whose recorded standard is `"WCAG 2.1"`, produced by today's agent, while its gate asked WCAG 2.2 questions.

**Why 2.2 is the correct target.** WCAG 2.2 contains everything in 2.1 and 2.0, so building to 2.2 satisfies every regime a client is likely to face — EN 301 549 (the EU standard behind the European Accessibility Act, moving to 2.2 in v4.1.1), the US ADA Title II rule (2.1 AA), and Section 508 (2.0 AA). It also adds six Level A/AA criteria that are decided in design: 2.4.11 Focus Not Obscured, 2.5.7 Dragging Movements, 2.5.8 Target Size, 3.2.6 Consistent Help, 3.3.7 Redundant Entry and 3.3.8 Accessible Authentication.

**What changed.**

| File | Line | Was | Now |
|---|---|---|---|
| `agents/05_ux_design/agent.md` | 10 | "produces a WCAG 2.1 AA accessibility compliance…" | 2.2 |
| | 15 | "Grounded in WCAG 2.1 AA (W3C, 2018)" | "WCAG 2.2 AA (W3C, 2023; current edition 2024)" |
| | 29 | "WCAG 2.1 AA is the floor, not the ceiling" | 2.2 |
| | 448 | "meets WCAG 2.1 AA contrast ratios" | 2.2 |
| | 506 | "**Framework:** WCAG 2.1 AA (W3C, 2018)" | "WCAG 2.2 AA (W3C, 2023; current edition 2024)" |
| | 548 | "WCAG 2.1 AA compliance specification…" | 2.2 |
| | 567, 571 | two quality-gate lines | 2.2 |
| `agents/08_code_review/agent.md` | 34 | evidence base "WCAG 2.1 AA (W3C, 2018)" | 2.2 |
| `agents/03_prd/agent.md` | 250 | NFR example row "WCAG 2.1 AA" | 2.2 |
| `agents/02_requirements/agent.md` | 265 | "Accessibility standard: WCAG 2.1 Level AA" | 2.2 |
| `agents/00e_document_vision/agent.md` | 27 | "WCAG 2.1 text-alternative principles" | 2.2 |
| `docs/DESIGN_SYSTEM.md` | 148 | our own product's accessibility section headed 2.1 | 2.2 |
| `docs/SCREEN_PROMPT_TEMPLATE.md` | 40 | "WCAG 2.1 AA: …≥40px hit targets" | 2.2, and the target rule now states the standard's own minimum (24×24, criterion 2.5.8) alongside the house style of 40px |

**What this change does NOT do — read this before assuming more.** Naming 2.2 does not make 05 *teach* 2.2. Its Step 7 table still covers nine criteria (1.1.1, 1.4.3, 1.4.4, 2.1.1, 2.4.3, 2.4.7, 3.3.1, 3.3.2, 4.1.2) and none of the six new in 2.2. Those six are asked of the designer at the UX gate, which has covered them since 14 August, so nothing is unasked — but widening the agent's own table is part of the proposed shift-left work, not of this correction. This limitation is written into the test docstring so the next reader finds it.

**Deliberately not changed:** `docs/PHASE_3_BUILD_SPEC.md:145` still says "WCAG 2.1 AA" when describing what 05's migration was to keep verbatim. That is a **historical record of a completed phase**; editing it would rewrite what the team decided at the time. `backend/apps/a11y/data/wcag22.json` and `wcag_build.py` mention "WCAG 2.1 Recommendation" inside quoted normative text and a source URL — those are correct citations of W3C's own wording and must not be touched.

---

## 2. Two tests were pinning the old standard, and were updated with it

**`backend/tests/test_wcag22_design_checklist.py`** — `test_the_design_agent_is_deliberately_untouched` asserted that 05 *contains* "WCAG 2.1 AA". That assertion was correct when written: it existed so that uplifting 05 would be somebody's decision rather than an accident. **The team made that decision on 2026-09-16.** The test is now `test_the_design_agent_names_the_current_standard`: it asserts 2.2 is present and 2.1 is absent, so the guard still fails if anyone puts 2.1 back. Its docstring records the decision and the limitation in §1.

**`backend/tests/test_design_test_agents_migration.py:54`** — the list of reasoning that must survive 05's migration verbatim included the literal string `"WCAG 2.1 AA"`. Changed to `"WCAG"`. The reason is already written in that file for agent 09: **the version of a standard is a data reference (the 15% that gets rerouted), not reasoning (the 75% that survives verbatim)**. Pinning the edition as reasoning is what makes a legitimate uplift look like a broken migration. 05 now follows the rule 09 already followed.

**A third test needed tightening, and this one is worth knowing about.** `test_09_testing_carries_no_wcag_21_reference` asserted the bare string `"2.1"` was absent from agent 09. That search cannot tell a *version* from a *criterion number*: **2.1.1 Keyboard and 2.1.2 No Keyboard Trap are current WCAG 2.2 criteria.** The blunt check survived only because no accessibility agent body happened to cite them. When 09 was corrected (§3) to point keyboard cases at the journey agent — which checks exactly 2.1.1 and 2.1.2 — the test failed on correct content. It now checks for the version strings themselves (`WCAG 2.1`, `2.1 AA`, `2.1 Level AA`, `WCAG 2.0`).

**Test result after all changes:** `test_wcag22_design_checklist.py` and `test_design_test_agents_migration.py` — **56 passed**.

---

## 3. Wrong statements corrected in the testing agents

### 3.1 `agents/09_testing/agent.md` — axe's impact words are not WCAG levels

**The problem, and it is a real defect.** The agent told testers that axe's `critical` impact means WCAG Level A and `serious` means Level AA, and gave colour contrast as a Level A example. All of that is wrong:
- axe's `critical / serious / moderate / minor` are the scanner's estimate of **user impact**. They are not conformance levels and do not map to them.
- **1.4.3 Contrast is Level AA**, and axe usually reports it as `serious`.
- The platform's own policy already takes severity from the criterion's level and **refuses the word "serious"** as a severity input.

So the agent was teaching a mapping the platform rejects, which would have produced defects at the wrong severity and an inconsistent quality gate.

**What changed:** the scan requirements now say to take the level from the criterion the finding cites, never from the impact word, and state the blocking rule as the project's policy expresses it (by default every confirmed Level A and Level AA failure).

### 3.2 `agents/09_testing/agent.md` — one severity scheme instead of three

The agent contained three different schemes: test-case priority (A→Critical, AA→High), a defect line saying Critical and Serious violations are all "severity High", and a severity table mixing Level AA on a non-core screen (Medium) with the axe word "Moderate" (Low). All three are now the platform's single rule: **Level A → Critical, Level AA → High, Level AAA → Medium.**

### 3.3 `agents/09_testing/agent.md` — keyboard testing is not manual any more

The agent said keyboard checks must be written as manual cases "because they genuinely cannot be automated". The platform's journey agent `09d_a11y_journey` walks an end-to-end case with the keyboard alone and checks eight criteria: 2.1.1, 2.1.2, 2.4.3, 2.4.7, 2.4.11, 3.2.1, 3.2.2 and 4.1.3. The instruction now tells the agent to write these as `Type: E2E` cases so the journey agent can walk them, and names the eight criteria.

### 3.4 `agents/09_testing/agent.md` — two smaller corrections

- It claimed WCAG 2.2 was "defined as the compliance target in the UX design phase". Until today that was false (05 said 2.1). It now refers to the project's accessibility target carried forward from the UX design phase's specification, which is both true and independent of any one project's setting.
- It said the judge answers "those four questions". The judge has had **six** checks since 1 September: alt text, real versus faked semantics, whether visible structure exists in the markup, colour as the only cue, label in name, and graphics contrast. All six are now named.

### 3.5 `agents/09b_test_automation/agent.md` — two stale references

- A note pointed at "`a11y-candidates.json` from Step 5a"; that file is written in **Step 5b**.
- A checklist item demanded "all six `styles` / `parent_styles` keys". There are **eleven** (`backend/apps/a11y/checkers/rules.py:57-75`). Rather than hardcode a number that will drift again, the item now refers to every key listed in Step 5b — the list the agent is already given.

### 3.6 `agents/09c_a11y_judge/agent.md` — missing evidence rules

The table of what a failure must carry had rows for `alt`, `color`, `label` and `semantics`, but none for `structure` or `graphics`, although both have been live checks since 24 and 27 August and the body already demands (in prose) that a structure failure carry the markup to add. Both rows are now in the table: `structure` must give the markup that would carry the structure, and `graphics` must give the measured colour pair and ratio.

---

## 4. Documents corrected

- **`docs/web-accessibility/USER_JOURNEYS.md`** and **`TESTING_GUIDE.md`** — "four AI checks covering five criteria" corrected to six and six, everywhere it appeared; the claim that design-time accessibility does not exist replaced with what is actually built (the 22-question gate checklist plus five optional criteria) and what is not (any automated check on a design); the greenfield map now distinguishes "accessibility enters" from "automated accessibility **evidence** enters". The coverage total stays 27, and the reason is now stated: 1.4.11 is one criterion checked in two halves, and 1.3.1 is shared by two checkers.
- **`TESTING_GUIDE.md` §10.3** — the note saying 14 tests were failing and "there is no `check_graphics`" was superseded on 1 September: the sweep found 21, not 14; `check_graphics` exists; the suite was reported at 1,765 passing, 0 failing. Corrected in place with the supersession dated.
- **`WCAG_COVERAGE_REFERENCE.md`** — the ownership counts now state **both** figures honestly: the registry file says rule 14 / AI 11, and effective routing is rule 13 / AI 12 because an engineering override moved 1.4.11 to the judge on 27 August. The data file itself was **not** changed (§6).
- **`RESEARCH_CORRECTIONS.md`** — eight new entries, R23 to R30, recording where the six research PDFs are now wrong: the "~16 of ~50 criteria" denominator (WCAG 2.2 A+AA is 55), the caveat on Deque's 57% figure, the disputed "67% originate in design" claim, EN 301 549 v4.1.1 moving to WCAG 2.2, the extended ADA Title II dates, the contradiction between two reports over whether the accessibility gate was built, agent 09's actual standard plus the uplift recorded here, and the "temperature 0 means determinism" claim. The file's status line stopped at R18 although R19–R22 existed; that is fixed too. The PDFs themselves cannot be edited, which is exactly why that file exists.
- **`docs/USER_JOURNEY_GREENFIELD.md`** and **`docs/USER_JOURNEY_BROWNFIELD.md`** — both were last updated on 1 July and had drifted: agent counts, artifact type names, the code-review gate's role, the missing 09c/09d and WCAG checklist, the missing build/PR/merge flow, and — in the brownfield document — the false claim that brownfield has no design phase. Both now also carry a short, factual note on where accessibility sits in the journey.

---

## 5. One thing in the original list turned out to be wrong

`WCAG_ACROSS_THE_LIFECYCLE.md` §12 listed the "not asked" reasons in `backend/apps/gates/wcag.py:274-293` as stale, on the grounds that 1.4.10, 2.1.2, 3.2.1, 3.2.2 and 4.1.3 have since become checkable.

**On reading the code, that entry was mistaken and nothing was changed.** The buckets are accurate:
- 1.4.10 sits in `checked_on_the_built_page`, which is **true** — the platform's own reflow rule measures it at 320 px on the built page.
- 2.1.2, 3.2.1, 3.2.2 and 4.1.3 sit in `only_visible_when_the_app_runs`, which is also **true**: the journey agent checks them precisely *because* they can only be seen when the app is running.

The file even carries a guard (`test_a11y_owner_capability`) that checks the machine buckets against the engines that really exist, and a comment explaining that a bucket's stated reason is a claim that can go stale. It had not. §12 of the main document has been corrected.

---

## 6. Deliberately left open, by the team's decision

| Item | Why it is not in this commit |
|---|---|
| **The ownership registry** (`backend/apps/a11y/data/ownership.json`) still marks the journey criteria as "phase 2" although 09d checks them today | This feeds what the conformance report is allowed to claim, so changing it changes client-facing output and needs its own tests. It is a behaviour change dressed as a data fix, and it belongs with the build |
| **05's Step 7 table** still covers nine criteria and none of the six new in 2.2 | Widening it is part of the proposed shift-left work (§6 of the main document), not a correction |
| **`A11yRoute.Source.ONBOARDING`** exists in the model and nothing ever writes it | This is an unbuilt feature, not a stale statement |

---

## 7. What was verified, and how

- **Tests run:** `backend/tests/test_wcag22_design_checklist.py` and `backend/tests/test_design_test_agents_migration.py` — **56 passed**, against the local database on port 5433. The full backend suite was not run, per the standing rule.
- **Reference sweep:** the §8 sweep assertions in both test files pass on every edited agent body, so no correction introduced a local file path or a legacy reference.
- **Search:** no `WCAG 2.1`, `2.1 AA` or `WCAG 2.0` string remains anywhere in `agents/`. The only `2.1.x` strings left are the criterion numbers 2.1.1 and 2.1.2, which are correct.
- **Not run:** no migrations, no workflows, no writes to the shared server. Everything read from the shared server during this work was read-only.
