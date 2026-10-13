# Research Corrections — what the reports got wrong about the platform

**What this is.** The six research PDFs under `Web-accessibility-research-evidence/` are the *why* behind this build, and they stay exactly as written — they are client-facing reports and a historical record. But several of their claims about **what the platform already does** turned out to be wrong when checked against the source. This file is the record of those corrections, so nobody plans against a claim that isn't true.

**The one sentence that explains almost all of them.** The reports were written against the **legacy agent suite** (`/legacy_suite/`), not the **migrated platform agents** (`/agents/`). The Journeys report says so itself — its evidence base cites `legacy_suite/agents/05_ux_design_agent.md`, `legacy_suite/agents/08_code_review_agent.md` and `legacy_suite/agents/00_onboarding_agent.md`. Those are the un-migrated v6 sources we keep for reference, not the agents the platform runs.

Think of it as planning a renovation from the *original* blueprint after the house was rebuilt to a new one. The rooms moved. Most of the plan still stands — but the steps to the back door lead nowhere, because there is no longer a back door there.

**Status:** R1–R12 are agreed team decisions (2026‑08‑12). **R13–R17 were added on 2026‑08‑27, R18 on 2026‑08‑28** and are a different kind of correction: R1–R12 are places the reports described *the platform* wrongly, while R13–R18 are places **we** read the reports wrongly, or where the reports contradict themselves. R13 is the one to read first — it is the root cause of two criteria being reported as machine-checked while nothing checked them, and of the guard that now makes that impossible. Where a correction changed the build, the affected tasks are named.

**R19–R22 (2026‑08‑28 to 2026‑08‑31)** are a third kind again: none of them is a claim in a report at all. They are defects in **our own checks and our own answer key**, found while building the accuracy evidence, and they are kept here because each one changes what an earlier audit result is evidence of. **R23–R30 were added on 2026‑09‑16**, and are a fourth kind: places the reports are out of date about **the outside world** — the standard's own numbering, a vendor statistic, a European standard and a US compliance date — plus two places where they describe platform work that did not exist when they were written and does now. *(This line previously stopped at R18 while R19–R22 were already in the file; corrected on 2026‑09‑16 in the same pass.)*

---

## R1 — "The testing agent already runs axe-core WCAG scans" — **FALSE**

*Claimed in:* Feasibility Assessment §1.2 and §2.1 ("ALREADY EXISTS — axe-core WCAG 2.1 AA per screen").

**What's actually true.** Agent 09's Step 9 is *prose telling a reader to run axe* — a `npx axe …` snippet inside a markdown body. Nothing executes it. In the agent catalog, `09_testing` is registered with `rides_build=False, reads_code=False` (`backend/apps/registry/catalog.py:99`), which means the platform gives it **no working folder, no shell and no browser**. It writes test *plans*.

A search for axe across every `.py`, `.ts`, `.tsx` and `.json` in `backend/`, `runner/`, `frontend/src/` and `mcp_platform_state/` returns **one hit** — a string inside a test that checks the agent body's wording. **No accessibility scan has ever executed in this platform.**

**But there is a route the reports missed.** Agent **09b** already generates Playwright tests, runs them in the worktree, and its JUnit output flows through `collect_test_results` → `import_test_results` → defects that open and close themselves. `@axe-core/playwright` assertions are just Playwright tests. So getting axe violations in as tracked defects is an **agent-body edit to 09b, with no platform code at all**.

**What JUnit cannot carry** (`backend/apps/quality/junit.py`): a screenshot, an accessibility-tree node, an element selector, a confidence, or a structured WCAG criterion. It carries `test_ref`, `status`, and free text capped at 2000 characters. So the AI half needs its own path.

**Tasks:** new **QA‑11a** (09b generates axe assertions) and **QA‑11b** (capture AI candidate bundles). QA‑12 consumes the bundles rather than hooking a scan that doesn't exist.

> **Amended while building QA‑11a (2026‑08‑14) — this entry was itself too generous about 09b.**
> "09b already generates Playwright tests, **runs them in the worktree**, and its JUnit output already flows through" is two-thirds true. The road from a JUnit report to self-closing defects is real and works. But **09b did not run what it generated** — its step was called *Dry Run Attempt* and compiled or type-checked only, telling one stack in as many words not to execute the test — and **nothing configured a JUnit reporter**, so no report existed for the companion to collect. "No platform code at all" was therefore wrong in three ways, each now fixed in QA‑11a:
> 1. **The suite has to actually run**, and the report has to land where the companion looks (`test-results/junit.xml`).
> 2. **An accessibility result needs its own test case.** Naming the scan after the screen's *functional* test id — as the task text said — would make one pass and one failure share an id, which the platform reads as a **flaky test**: quarantined, and quarantined tests do not block the gate. A real accessibility failure would have disappeared from the gate while looking like correct behaviour. (D‑A11Y‑8.)
> 3. **Evidence was being destroyed at the door.** The failure text was cut to 2000 characters *at parse time*, because the `test_report` artifact had no body and a database column was the only place it could live. Eighteen violations arrived as four. The artifact now carries its full body in the object store, which is what #1/#3 prescribed all along. (D‑A11Y‑11.)

> **Amended again while building QA‑12 (2026‑08‑14) — "the scan's findings are in the test report" is true and not enough.**
> The full axe output does reach the platform, as the `test_report` artifact's body. But that body is **prose an agent wrote**, and a merged accessibility report may not be built by parsing it: a text format an LLM produces is exactly the input that degrades silently, and this is the one document a client or auditor reads. The structured half only covered elements the AI checks applied to, because a `A11yCandidateBundle` row exists only for those — so a violation on a missing `lang`, a duplicate id or a landmark had **no structured record anywhere in the platform**. QA‑12 therefore added a screen-level `axe_violations` list to the capture format (D‑A11Y‑20). Both halves are kept and neither is redundant: the per-element one makes a rule finding and an AI finding *comparable on one element*, the screen-level one makes the report *complete*.

> **Amended a third time while building QA‑08 (2026‑08‑15) — the backlog inherited axe's vocabulary and used it for things axe never touches.**
> QA‑08 and QA‑15 both said the gate blocks on "Critical/**Serious**". `serious` is one of axe's four `impact` words (`critical`/`serious`/`moderate`/`minor`); it reaches the platform only on a **scanner** finding, and it is kept beside the finding as `impact`, never conflated with severity. What every finding in the ledger carries — scanner and AI alike — is a `severity` derived from the **WCAG conformance level**: Level A → Critical, AA → High, AAA → Medium. `serious` is a value that column can never hold, so a gate written literally against "Critical/Serious" would have blocked on scanner findings only and let **every AI‑confirmed failure through**. The gate policy therefore names severities (D‑A11Y‑30), a policy naming `serious` is refused with a message saying where that word does belong, and QA‑15's task text is corrected in the backlog. The lesson generalises: the research reports describe an axe-shaped world, and non‑negotiable #9 applies to vocabulary as much as to connectors.

---

## R2 — "Rendered capture + accessibility tree — ALREADY EXISTS" — **TRUE BUT NARROW**

*Claimed in:* Feasibility Assessment §2.1.

**What's actually true.** Playwright MCP is real, but it is handed **only to the `test_automation` phase** (`runner/companion/guardrails.py:282`), and it runs **on the developer's machine** inside the companion. The live application it drives comes up from `preview_start` config, and `PreviewEnv.Provider` has exactly one value: `companion_local`.

**Why this matters more than it sounds.** The app under test runs at a **localhost URL on a developer's laptop**. The server cannot reach it. Any design that assumes the platform can open a browser and visit the app is wrong. Browser work belongs in the companion; judgment, triage, findings and gates belong server-side.

> **Amendment (2026‑08‑14, while building QA‑11b).** That split has a consequence the backlog's own task text did not survive. QA‑11b asked for **a cropped screenshot per element** *and* for **selection to run before cropping** ("that is most of the saving"). Both are right, and on one machine they are incompatible: cropping happens in the browser, on the laptop; the selection rules are Python and live on the platform; by the time Python can run them the browser is closed and the worktree is deleted. Read literally the task needs two browser passes with a network round trip in the middle of a test run.
>
> **Resolution (D‑A11Y‑12):** the capture takes **one full-page image per screen** plus each element's rectangle in it, and the platform crops — after selection, from an image it already holds. The ordering the task asked for is preserved exactly; it just happens on the other side of the wall this correction is about. ~10 images per run instead of ~300.
>
> A second consequence of the same wall: the capture must **not** ride the build report. That report is a Temporal signal payload, and a screen carries a full-page PNG. The companion posts each screen over the runner-token route it already authenticates on, one screen per call, and only a summary line travels on the report (D‑A11Y‑15).
>
> **Third consequence, found while building QA‑16 (2026‑08‑15).** That task's acceptance criterion says *"the script runs both axe and the AI checks"*. It cannot. The AI checks are a server-side capability reached through `ExecutionDriver`, the generated script runs in the companion on a developer's laptop, and putting orchestration into a test script would break non‑negotiable #2 as well as this wall. The buildable form is the one the platform already implements: the script runs axe and **captures what the AI checks judge**, and the platform runs them after the suite finishes. Corrected in the backlog as **D‑A11Y‑42**, and the agent body now states it outright so a later edit cannot reintroduce the idea. The general lesson is the same one R2 opened with: any task text that has the companion *doing* platform work is describing something the architecture forbids, however reasonable it sounds.
>
> **Fourth consequence, found while building QA‑17 (2026‑08‑17).** The brownfield baseline audit reads as a server-side job — "point the platform at an app and audit it" — and it cannot be one, for this wall and for a second reason: there is no browser in the platform's containers at all. So the audit is split the same way everything else is. The platform owns the plan (which routes), the reconciliation (what came back against what was asked for) and the judgment; the machine that can see the application does the visiting. The visiting itself is **not an agent**: driving a browser to a fixed list of URLs needs no intelligence, so it is a reviewed script the companion ships (`runner/companion/assets/a11y_audit.mjs`) rather than JavaScript synthesised per audit or an engine run spending subscription usage on `page.goto`. Recorded as **D‑A11Y‑47** and the "who visits the routes" note on QA‑17.

---

## R3 — "WCAG gate / merge gate — ALREADY EXISTS" — **MISLEADING**

*Claimed in:* Feasibility Assessment §2.1.

**What's actually true.** `backend/apps/gates/wcag.py` is a **hand-typed checklist of 9 WCAG 2.1 criteria** that a human reviewer ticks, attached to the **design** gate (`_WCAG_GATED_PHASES = {"ux_design"}`). It is a person confirming they looked. It is not a machine deciding pass/fail from findings, and it is not on the test gate.

**The pattern we actually need already exists elsewhere.** `backend/apps/gates/testgate.py` is a **derived** condition — the platform evaluates it from live state at decide time, and its own comment explains why that matters: *"a reviewer can never tick past a red suite."* Accessibility deserves the same protection.

**Also caught:** no task in either backlog touched `gates/wcag.py`, so it would have silently stayed at WCAG 2.1 while everything else moved to 2.2.

**Tasks:** **QA‑11** expanded to include the `gates/wcag.py` uplift; **QA‑15** adds a derived a11y condition; new **QA‑15a** fixes a latent bug in `refresh_derived` (it hardcodes the *test* evaluator for every derived condition, so a second derived condition would silently never refresh).

> **Two things this entry got slightly wrong, found while building QA‑11 (2026‑08‑14).**
> 1. **The 2.1 references were not only in `gates/wcag.py`.** Four more surfaces named the version and no task owned any of them: the gate screen's **design‑gallery** subtitle, the NFR example a project owner copies in project setup, and developer comments in `gates/models.py`, `gates/services.py` and `gates/conditions.py`. The team approved fixing all four inside QA‑11 rather than logging them — same reasoning that put the gate file in scope. Worth noting for accuracy: the **live** gate screen never named a version; it reads "every required criterion is ticked". Only the demo variant said 2.1.
> 2. **"Filtered to the human-owned criteria" does not survive contact with the registry** — see **D‑A11Y‑7** in `TASK_BACKLOG_QA.md`. Nine of the 30 human-owned criteria cannot be answered from a design at all, and the filter would have removed contrast and alt text from the design gate while their automatic checks do not run until the page is built. The design gate now asks a deliberately different question — *what can a person settle by looking at the design?* — and the registry is used to **cross-check every exclusion reason** instead. QA‑15's computed test gate is unaffected: it routes by owner, which is the registry's own question.

---

## R4 — "A model gateway (LiteLLM-style) in front of all models" — **CONFLICTS WITH NON-NEGOTIABLE #7**

*Claimed in:* Feasibility Assessment §3.2; Addendum B §3.1.

**What's actually true.** `ExecutionDriver` (`backend/drivers/base.py`) has exactly two methods — `run_planning_task` and `run_build_task`. There is no "send a prompt and an image, get JSON back" primitive. And **no connector in `backend/integrations/` makes a single model call** — they all make ordinary HTTP calls to Jira, Confluence, GitHub, Figma and Xray.

So business logic calling a model directly — even from inside a capability connector — *is* "calling the engine directly from business logic," which CLAUDE.md non-negotiable #7 forbids.

**The corrected design.** `a11yai` stays a capability for its **shape** (callers say `a11yai.check_alt(...)` and never name a vendor — non-negotiable #9), and runs **through `ExecutionDriver`** for its **execution** (non-negotiable #7). Judgment is a constrained run of a platform-native agent, on the Claude Code subscription. Both rules satisfied; no API key, no billing decision, no exception.

**Two precedents made this the obvious answer:**
- `00e_document_vision` (`catalog.py:125`, `native=True`) is a working platform-native agent that **reads images and produces structured output**. An accessibility judge is the same shape pointed at a different kind of image.
- `submit_gap_report` (`mcp_platform_state/tools.py:550`) shows schema enforcement at the MCP tool layer — its docstring: *"coerces it to the exact shape … so a model typo can never degrade the screen."*

**Tasks:** **QA‑02** re-scoped from "model switchboard" to "judgment dispatch, cache & audit"; new **QA‑02a** builds the `09c_a11y_judge` native agent, the `record_a11y_finding` MCP tool, and a write-completeness check. Model routing (cheap text model vs vision model) becomes a later cost optimisation, not POC scope.

**Known risk, mitigated.** An agent can be told to call a tool and not do it — we have a verified instance of this in the ideation agent. For a compliance feature, silent under-reporting is the worst possible failure, so the write-completeness check is part of the first version, not a follow-up: if 40 candidates went in and 31 findings came back, the run fails loudly.

---

## R5 — The file paths in the plans are dead — **ALL OF THEM**

*Claimed in:* Feasibility §1.1 and Journeys §1.1 (evidence base), and inherited by OP‑01, OP‑02, OP‑06, OP‑07, QA‑17.

**What's actually true.** A search across every migrated agent body for `docs/ux/` and `docs/design/screens` returns **zero hits**. Those paths exist only in the legacy suite.

| The plans say | The platform actually has |
|---|---|
| `docs/ux/ACCESSIBILITY.md` | an artifact of type **`accessibility`** |
| `docs/design/screens/S-NN.html` | **`wireframe`** artifacts — one per screen, state HTML in S3 via `external_ref.states` |
| "register the app's screens/routes" | **`A11yRoute`** — built by QA‑17 (2026‑08‑17); was *nothing* until then |

This is exactly the failure the migration spec warns about (*"a migrated agent still naming a local file is a FAILED migration"*) — except here it is the **plans** naming dead files, not the agents.

**Tasks:** OP‑01, OP‑02, OP‑06, OP‑07 and QA‑17 updated to name artifact types instead of file paths.

> **Closed for QA‑17 (2026‑08‑17).** Two halves, and only one of them needed code. The `docs/ux/ACCESSIBILITY.md` half was already fine: nothing in the accessibility chain reads an `accessibility` artifact either, so "audit an app without an accessibility spec" needed verifying, not building — a test now proves it against a project holding **zero artifacts**. The route-registry half was the real gap, and is now `A11yRoute` (**D‑A11Y‑46**). **OP‑06 writes the same table** rather than inventing its own — it sets `source: onboarding` and nothing else about the audit changes.

---

## R6 — "Eval harness (PG24)" and "cost metering plane" are available — **NEITHER EXISTS**

*Claimed in:* Journeys §2.2 and §5.

**What's actually true.** There is **no CI pipeline in this repository** — no `.github/`, no `Jenkinsfile`, no `.gitlab-ci.yml`. Only `docker-compose.yml`. `make test` runs pytest in a local container. There is no eval harness, and `pytest-cov` is not installed, so the "≥ 90% coverage" in both backlogs' Definition of Done is currently unmeasurable.

QA‑10 says to *"wire it into Edvensoft CI so that promoting a new model or prompt version is blocked."* There is nothing to wire into — and QA‑10 blocks QA‑22, the only thing that ever lets the agentic tester gate a merge.

**Cost is the exception — it turned out to be a non-issue.** Because judgment is a Run, `Run.cost_usd` already covers it, and every existing cost display works unchanged.

**Decision (D4):** for the POC the accuracy harness runs **locally via `make`**, not in CI. A real pipeline comes when a client depends on it.

**Tasks:** new **QA‑10a** (stand up the local harness entry point); `pytest-cov` + a module-scoped `make cov` added as a prerequisite before QA‑01.

---

## R7 — 2.4.6 is in two different tiers — **RESOLVED: Phase 2**

*Conflict between:* Addendum A §3 (per-criterion table: **Phase 2**) and Addendum B §2.2 (Tier‑1 POC checker list: **POC**). Addendum B flags it itself as a judgement call.

This is not cosmetic: QA‑05 must load exactly 55 criteria and **fail loudly** if any criterion lacks exactly one owner and one tier. One criterion with two tiers stops the loader.

**Decision (D5): 2.4.6 (Headings and Labels) is Phase 2.** Addendum A's per-criterion table is the more detailed source and wins. The POC therefore ships **5** AI-judged criteria (1.1.1, 1.3.1, 4.1.2, 1.4.1, 2.5.3), not 6.

---

## R8 — "~16 agentic / ~14 human" — **the enumerated lists say 15 and 15**

*Claimed in:* Addendum A §3.3.

The prose rounds; the **lists are exact and internally consistent**: 15 + 15 = 30 human-primary. Where prose and list disagree, **the enumerated lists are authoritative** — QA‑05 is built from the lists. (Same rule, same section: §4.2's "~5 remaining AI-primary criteria" lists 6.)

> **Corrected while building QA‑05 (2026‑08‑13).** This entry previously said the tier split was "20 + 20 + 15 = 55". The authoritative per-criterion table gives **19 IN POC + 21 PHASE 2 + 15 HUMAN**. The 20 / 20 figure is the count from *before* decision D5 (R7 above) moved 2.4.6 Headings and Labels out of the POC — recomputing with 2.4.6 back in the POC reproduces 20 / 20 / 15 exactly, which is how it was traced. Addendum A's own table already reflects D5, so there is no source conflict left; only this summary line was stale. The registry is loaded from the table and **fails to build** if the split is not 19 / 21 / 15.

---

## R11 — What happens to a *low*-confidence finding — **the sources disagree; nothing is dropped**

*Conflict between:* Report 1 §④ ("TRIAGE, DEDUPE & CONFIDENCE GATING") and the User Journeys document. Found while building QA‑06 (2026‑08‑13).

| Source | Low-confidence finding → |
|---|---|
| **Report 1 §④** | *"high-confidence → report as a failure; mid-confidence → report as 'review'; **low-confidence → drop** (logged for tuning)"* — three bands |
| **User Journeys** (twice: §"low-confidence items route to the SME, not to a hard fail" and §"low-confidence → SME queue") | routed to a person — two bands |
| **QA‑06's own task text** | *"medium or **low** becomes 'needs human review'"* — two bands |

**Decision (D7): two bands. Nothing is ever dropped.** Dropping is the only option here that can make the platform **silently miss a real accessibility defect**, and it would be the first place in this build that discards rather than routes — everything else refuses to (an unanswerable judgment becomes `uncertain`, an unowned criterion stops a load, a stray row stops a reload).

Report 1's counter-argument is real and recorded rather than dismissed: *"low noise protects adoption."* If the review queue proves noisy once ~~QA‑09/QA‑10~~ **QA‑10** measures it, a floor can be added **with evidence**. It is not being added on a guess.

> **Update 2026‑08‑17.** QA‑09 is ⏸ parked; QA‑10 is not, and it measures **precision** from the reviewer verdicts the queue itself produces (`A11yFinding.adjudication`) — which is exactly the "is this queue noisy?" question. So this decision still has a route to evidence. What parking does cost is **recall**: nothing can tell us what the checkers stayed silent about until the golden set exists. See `TASK_BACKLOG_QA.md` D‑A11Y‑62 … D‑A11Y‑66.

---

## R12 — No source specifies a confidence threshold — **0.80, provisional**

*Claimed in:* nowhere. Searched all four research documents while building QA‑06 (2026‑08‑13).

There is **no confidence threshold in any source.** The one number that looks like one — Report 1's *"≥85% on high-confidence findings"* — is a **precision target for the accuracy harness** (QA‑09/QA‑10), not a confidence cutoff. Using 0.85 because it appears in the report would conflate two different measurements.

**Decision (D8): 0.80 for all four checkers to start, per-checker configurable per tenant.** Explicitly provisional: the correct values are unknowable until the golden set exists, which is exactly why the thresholds are configuration and not code — tuning them is a settings change, never a release.

> **Update 2026‑08‑17 — 0.80 stays provisional for longer than planned.** With QA‑09 ⏸ parked, the golden set that D8 said would settle these numbers does not exist and has no date. **0.80 is therefore an unmeasured placeholder in production, not a tuned value**, and that must be said out loud rather than allowed to harden into a fact by age. Note also that the *precision target* this correction distinguishes it from — the 85% — **is** measurable without the golden set, from live reviewer verdicts (D‑A11Y‑63). ~~So the accuracy bar QA‑22 reads has a route to evidence; this threshold does not.~~ **Amended 2026‑08‑18 (D‑A11Y‑82): QA‑22 reads no accuracy bar at all** — the evaluation is internal and decides nothing in the product. The 85% is still worth measuring, as our own evidence and a client's; this threshold still has no route to one.

---

## R10 — Addendum A's "Hybrid note" list disagrees with its own table — **the table wins**

*Conflict inside:* Addendum A §2.3's hybrid note vs the §3 per-criterion table. Found while building QA‑05 (2026‑08‑13).

The hybrid note reads *"criteria marked AI where a rule also contributes (1.1.1, 1.3.1, 2.4.4, **2.4.6**, 4.1.2)"*. The table supports a different set, differing by exactly two:

- **2.4.7 Focus Visible is missing from the note.** Its row reads *"Rule detects outline:none; AI/visual confirms a visible focus indicator"* — plainly a rule contribution.
- **2.4.6 Headings and Labels should not be in it.** Its row names no rule at all: *"AI judges if headings/labels are descriptive (partially touched by POC semantics checker)"* — and the POC semantics checker is the AI, not a rule.

**Decision (D6): the per-criterion table wins**, the same precedent as R7 and R8 — the table is the more detailed source and the prose rounds. The hybrid set is therefore **{1.1.1, 1.3.1, 2.4.4, 2.4.7, 4.1.2}**.

This is not cosmetic: QA‑05 stores hybrid contributions as `secondary_checks` so routing can act on them. The build **asserts the difference is exactly these two** — if the report is ever corrected, the build stops and a person decides, rather than the registry changing unnoticed.

---

## R9 — "~70% reuse / ~30% net-new" — **directionally right, misleading in shape**

*Claimed in:* Feasibility Assessment §4.3.

The reuse is real and substantial — the defect loopback, the gate/Approval machinery, the Knowledge Index, the capability seam, artifact registration and traceability all land cleanly, and two of them (the security-findings reconciliation pattern and generic artifact preview) turned out to save more work than the report claimed.

But the new portion is **concentrated in things that do not exist at all**, not spread thinly across things that mostly do:

- candidate capture in the companion
- the findings ledger and SME review queue
- the `09c_a11y_judge` native agent
- a derived accessibility test gate
- the accuracy harness (and something to run it in)

A truer figure is **roughly 60% reuse / 40% new**, and the useful statement is not the percentage but the list above — that is where the risk and the time actually sit.

---

## R13 — "RULE" in Addendum A never meant "axe-core" — **and we read it as though it did**

**Agreed 2026‑08‑27.** This is the root cause of the two criteria that were reported as covered and checked by nobody, and it is the most useful correction in this file because it is about *how* we read the reports rather than about one claim inside them.

Addendum A defines its `RULE` owner as: *"A deterministic engine can decide the typical case with high confidence."* That is a statement about what is **possible in principle**, and it is true of both 1.4.10 Reflow and 1.4.11 Non-text Contrast — resizing a window and comparing two colours are arithmetic. **It is not a statement that any particular scanner does it.**

Then QA‑11a fixed the deterministic engine as Deque's `@axe-core/playwright`. From that point "the rule engine" and "axe" were the same phrase in every conversation, and the registry's fourteen rule-owned criteria were never re-checked against what axe actually ships. Measured against the version we pin:

```
axe-core 4.13.0 — 105 rules, 70 selected by our six WCAG tags, touching 24 criteria
wcag1410 (Reflow)             — NO RULE EXISTS
wcag1411 (Non-text Contrast)  — NO RULE EXISTS
```

Both are well-known gaps in the free axe library; non-text contrast is in Deque's paid product.

**Why no proof caught it.** `ownership_build.py` validates the registry eight ways — every one comparing our parse to the report, not one comparing the report to the scanner. `ownership.verify_complete()` proves every criterion has an owner. `gates.wcag.verify_complete()` proves every criterion is asked at design or recorded as not asked. **None of them asks whether the named owner is *able*.**

**Fixed 2026‑08‑27 (QA‑25).** Both criteria are now measured by the platform itself (`backend/apps/a11y/page_rules.py` plus the two browser passes in `a11y_audit.mjs`), and the missing question is now `backend/tests/test_a11y_owner_capability.py`, which fails by name against a generated inventory of what the pinned scanner really covers (`apps/a11y/data/scanner_coverage.json`, regenerated by `python manage.py build_scanner_coverage`). Run against axe alone it reports exactly `['1.4.10', '1.4.11']`.

**The registry itself is deliberately NOT edited.** It is derived wholly from the committed report and regenerating it would revert any hand edit; the correction belongs here, and the enforcement belongs in the guard.

---

## R14 — Addendum A calls 1.4.11 rule-owned while its own rationale says otherwise — **the rationale is right**

**Agreed 2026‑08‑27.** The registry row for 1.4.11 reads:

> `"owner": "rule"` … `"rationale": "UI/graphic contrast ≥3:1 — computable, but 'which graphics matter' needs some review."`

The rationale is correct and the owner is not. 1.4.11 is a criterion in two halves:

| Half | The question | Who can answer it |
|---|---|---|
| **User interface components** | can you see where the controls are? | a rule — colours and a 3:1 threshold |
| **Graphical objects** | are the meaningful parts of icons, charts and diagrams visible? | a judge — you must know which parts carry meaning before any ratio means anything |

Recording it as rule-only is how the second half went unbuilt for four tasks while the criterion was reported as covered. **Neither half is the criterion on its own.**

**Fixed 2026‑08‑27 (QA‑25).** The measurable half is `page_rules.contrast_failures`; the judged half is the sixth element checker, `graphics`, whose scope is deliberately *wider* than `alt`'s — 1.4.11 is about what can be **seen**, not about what assistive technology is **told**, so a graphic that is never announced is still in scope. `test_a11y_owner_capability` asserts both halves exist and would fail if either were removed.

> **Amended 2026‑09‑01 — the correction was agreed, and for five days nothing carried it into the data.**
> Everything above was written and agreed on 27 August, and both halves were built the same day. What was never done is the step that makes a decision operative: **`ownership.json` still said `"owner": "rule"`.**
>
> That mattered more than it sounds. `integrations.types.A11Y_CHECKER_CRITERIA` is the map of what the **AI** owns, and it had 1.4.11 in it from the day `graphics` shipped. The registry did not. Five separate guards reported the disagreement every single day for five days — the ownership drift test, the registry/map equality test, the POC element-check list, the capability-surface check, and both halves of the selection corpus — and were read as background red. On 1 September `graphics` was briefly held back to make the code agree with the registry, which was the wrong half to move.
>
> **What that half-day exposed is worth more than the fix.** With the judge paused, 1.4.11's measurable half is recorded under the `rule` engine — the engine the registry named as owner — so the conformance guard would have found an entitled engine had looked and answered **"Supports 1.4.11"** for a page whose buttons all had visible edges and whose icons nothing had judged. Pausing the check would have recreated the exact bug the check was built to fix. Holding a check back now **withdraws its criterion from positive claims** rather than leaving it to whatever else touches the criterion (`A11Y_HELD_BACK_CLAIMS`).
>
> **Carried into the data on 1 September**, and deliberately *not* by editing the registry file. `data/ownership.json` is a derivation — `ownership_build` rebuilds it from the committed PDF and proves it against eight cross-checks including the report's own headline counts — so an edit there would make the file disagree with its own source. The decision lives in `ownership.ENGINEERING_OVERRIDES` instead, applied at load, so the file keeps saying what the report says and `CriterionOwnership` carries what we decided. `test_a11y_ownership` holds three things about it: the file is unedited, the override set is exactly `{1.4.11}`, and every override names a criterion that appears in this document.
>
> Also completed the same day, both missing since 27 August: **`check_graphics` on the capability** (without it the criterion could be selected, dispatched and judged in an audit but never asked about directly), and **seven selection-corpus rows for 1.4.11** — five failure shapes it must reach and two it must leave alone, drawn from the rule's own `covers` and `skips` prose. Two of the five are reachable by nothing else in the platform: a bare `<svg>` with no name, and an icon painted as a CSS background image.
>
> **The lesson, and it is the third time this document has recorded a version of it:** a correction agreed in prose and not carried into the data is not a correction. The registry is what routes; everything else is commentary.

---

## R15 — Six rule-owned criteria have thinner scanner coverage than their rationale describes — **real, but not holes**

**Agreed 2026‑08‑27.** A rule fires for each of these and can fail the page, so none is a gap of the 1.4.10 kind. But the registry's rationale describes more than the rule does, and a coverage number that counts these as equal to 1.4.3's full contrast maths is overstating what the scanner did:

| Criterion | Rationale says | The rule actually does |
|---|---|---|
| **1.3.5** Identify Input Purpose | "check autocomplete tokens on common inputs" | `autocomplete-valid` checks tokens that are **present**; a field with no `autocomplete` at all raises nothing |
| **1.4.4** Resize Text | "render at 200% & detect loss/clipping" | `meta-viewport` checks only that zoom is not disabled — nothing renders at 200% |
| **1.4.12** Text Spacing | "apply spacing overrides & detect clipping" | `avoid-inline-spacing` checks only for inline `!important` that would block an override — the overrides are never applied |
| **2.4.2** Page Titled | "title present & non-empty" (already honest) | `document-title` — presence only; descriptiveness is the unbuilt AI enhancement |
| **3.1.2** Language of Parts | "detect lang on parts in other languages" | `valid-lang` validates values that exist; a foreign passage with **no** `lang` raises nothing |
| **3.3.2** Labels or Instructions | "rule catches missing programmatic label (dominant failure)" | `form-field-multiple-labels` is the only rule tagged to 3.3.2. **The missing label IS caught** — by axe's `label` rule — but axe tags that to **4.1.2**, so it is filed under a different criterion |

**Deliberately not "fixed" in code.** Re-tagging a vendor's own rule inside our reader would be the platform quietly disagreeing with the scanner it cites in a signed statement. The six are recorded instead in `THIN_SCANNER_COVERAGE` in `backend/tests/test_a11y_owner_capability.py`, with a test that fails if an axe upgrade **deepens** one — so this list shrinks when reality improves, rather than becoming a list of limitations that were fixed years ago and are still being apologised for.

---

## R16 — OP‑02 names an AI check that was never built — **corrected in place**

**Agreed 2026‑08‑27.** OP‑02 said to reuse "alt‑text intent, colour‑only meaning, heading/label descriptiveness, and target size". Two of those four do not exist to reuse: **2.4.6 descriptiveness has no checker** (the registry defers it to Phase 2 — see R7), and **2.5.8 target size is geometry, not an AI check**. Corrected in `TASK_BACKLOG_OTHER_PHASES.md`, which now lists what OP‑02 can actually call and says that adding either of the other two is its own task.

---

## R17 — Three more criteria were skipped at design on the strength of a check that does not exist

**Agreed 2026‑08‑27.** Found by looking for others of 1.4.10's kind rather than waiting for one to surface. The design gate's `checked_on_the_built_page` bucket carried **1.3.2 Meaningful Sequence, 1.3.3 Sensory Characteristics and 1.4.5 Images of Text** under the reason *"a rule scanner or the AI pass decides this on the built page"*. Nothing checks any of the three, at any stage, today.

**Less severe than 1.4.10 was**, and the difference matters: all three are honestly recorded as `tier=phase_2`, so no report claims them as covered — whereas 1.4.10 was recorded as shipping in the POC. They were being *skipped* on a false reason, not *claimed* on one.

**Fixed 2026‑08‑27.** Split into a new `deferred_to_a_later_phase` bucket whose stated reason is true, and `test_a11y_owner_capability` now checks both machine buckets against the engines that actually exist — so a bucket's reason can no longer quietly become false.

---

## R18 — Five axe rules matched our filter and never ran, and two criteria rested on nothing

**Agreed 2026‑08‑28.** Found while aligning the Meridian fixture's scan configuration with the
platform's, for the accuracy harness.

**What is true.** The scan asks axe for everything tagged WCAG 2.0/2.1/2.2 A and AA. **axe holds
`experimental` rules out of a tag-selected run and reports nothing about having done so.** Five
rules match our tags and are experimental, so five rules never ran. Two criteria have no other
rule at all:

| Criterion | Its only rule | Consequence |
|---|---|---|
| **1.3.4** Orientation | `css-orientation-lock` | recorded `owner: rule`, `tier: in_poc`, skipped at design review on the grounds that a scanner decides it — and nothing did |
| **2.5.3** Label in Name | `label-content-name-mismatch` | correctly `owner: ai`, so no false claim; the scanner simply added nothing |

The other three — `p-as-heading`, `table-fake-caption`, `td-has-header` — are 1.3.1 rules, and
1.3.1 keeps other rules, so the criterion never looked uncovered while three real checks were off.

**Measured, not reasoned.** axe-core 4.13.0, `/account/card-services`, which carries seven
violations of `label-content-name-mismatch`:

```
six tags, no rules block        63 rules ran    0 violations reported
same tags + an explicit opt-in  64 rules ran    7 violations reported
```

`target-size` looks like the same case and is not. It ships `enabled: false`, but that flag
governs only what axe does when given no instructions — a tag selection runs it anyway. The
distinction matters: one of these two needs naming and it is not the one it looks like.

**This is the third instance of R13's failure mode, and the guard R13 produced did not catch it.**
`test_a11y_owner_capability` asks whether a rule-owned criterion has an engine behind it, and
answers from `scanner_coverage.json` — which was generated by filtering `axe.getRules()` on tag
membership, never on whether a tag-selected run executes them. The guard was sound; its evidence
was not. **A guard is only as true as the thing it reads**, and that is the lesson worth keeping
from this one.

**Fixed 2026‑08‑28.**
1. `runner/companion/assets/a11y_audit.mjs` names all five rules in a `rules` block. Naming them
   is the narrow way in; adding `experimental` to the tag list would pull in every experimental
   rule axe ships, including ones outside WCAG A/AA.
2. `scanner_inventory.mjs` mirrors that list and excludes any other experimental rule, so the
   inventory records what the scan runs rather than what it selects.
3. A new parity test asserts the two lists are identical — verified to fail when one drifts.
4. The fixture harness opts in to the same five, and `/catalogue/subject-index` now reports
   `td-has-header`. That page keeps its AI label: the scorer drops rule-scanner rows entirely, so
   neither engine can be credited with what the other found.

**What it changes for a client.** Audits run after this date report findings on 1.3.4, 2.5.3 and
three more 1.3.1 rules that earlier audits could not have reported. An earlier clean result on
those criteria was never evidence of anything.

---

## R19 — An element with a border is invisible to the colour check, and a coloured border is the commonest error cue there is

**Found 2026‑08‑28**, while planting 1.4.1 material for the accuracy dataset.
**Fixed the same day**, once the team had ruled on it — see the end of this entry.

**What is true.** `_applies_color` skips any element `_has_second_cue` returns true for, and one
of the things that returns true is a `border-style` other than `none`:

```python
if str(element.styles.get("border-style", "")).strip().lower() not in {"", "none"}:
    return True
```

The reasoning is sound in general — a border is a visual cue that is not colour — and it is wrong
in the case it matters most. **A field marked invalid by turning its border red already had a
border.** The border is not the cue; the border's *colour* is. So the rule reads the presence of
the thing being coloured as proof that colour is not the only cue, and declines to look.

**The answer key already contained this and it read as a coverage miss.** `g-141-0019`
(`/help/report-a-problem` `#problem-detail`) is labelled a clear 1.4.1 failure — "a rejected
field marked by a red border and nothing else, no aria-invalid, no message". The colour rule
declines it **because it has a border**. Its clean twin `g-141-0020` is declined for the same
reason. One shows up as a false negative and the other cannot score at all.

**Measured across the whole fixture**, 6,885 captured elements on 78 routes. Elements that would
be colour candidates but for a second cue:

```
selected as colour candidates          747
declined for a second cue              328
    of those, declined for a border    219   <-- this correction
    declined for an underline           79   (a real second cue; correct)
    declined for a nested img or svg    30   (a real second cue; correct)
```

The 219 by tag: 72 `button`, 49 `input`, 20 `li`, 20 `th`, 13 `select`, 11 `div`, 10 `a`,
9 `span`, 6 `textarea`, 5 `td`, 4 `ul`. Every form control in the application is in there,
because the stylesheet gives every form control a border.

**Nothing else covers it either.** 1.4.1 has exactly one axe rule in our tag selection,
`link-in-text-block`, and it is about links in prose. A red border on an invalid field is
therefore decided by no engine the platform runs — not the scanner, and not the AI check that
was built to catch what the scanner cannot.

**Same failure mode as R13 and R18, for the third and fourth time: a guard reading a proxy
instead of the thing.** R18's lesson was "a guard is only as true as the thing it reads". This
one is narrower and worth stating on its own: **the presence of a property is not evidence about
its value.** A border, an underline and an icon are cues only when they distinguish this element
from its neighbours — which is what `_colour_differs_from_surroundings` already does for colour,
and what `_has_second_cue` does not do for anything.

**Every narrower option was measured and none of them work.** The obvious idea is to compare
the border against something rather than merely noticing it exists. Measured across 94 routes,
against the 901 elements the colour check already selects:

| Option | Extra candidates |
|---|---|
| drop the border test entirely | **+300** |
| a cue unless the border's colour differs from the parent's | +296 |
| a cue unless the border's colour differs from the element's own text colour | +300 |
| a cue only when the border's *style* differs and its colour matches | +0 — never fires |

The middle two save four candidates out of three hundred and cost a new captured property,
because a parent almost never has a border to compare against. There is no way to tell a
decorative border from a signalling one from what a single element carries.

**Fixed 2026‑08‑28 by removing the border from the second-cue test**, on the team's ruling. The
judge now decides, which is the trade `_repeats_a_child_class` already makes and states in as
many words: it costs a judgment on things that turn out to be fine, and that is the direction
worth being wrong in. The two golden records on `/help/report-a-problem` and its twin are now
both selected, and `color`'s reachable sample went from 31 to 32.

**What it changed for a client.** Audits from this date report a field whose only error
indication is a red border. Before it, they could not — and that is the single most common way
applications signal an invalid field, so a clean 1.4.1 result from an earlier audit is not
evidence about it.

---

## R20 — A balanced answer key was producing a one-sided scored sample, and every check was green

**Found 2026‑08‑28**, while growing the golden set so the accuracy numbers could be produced at
all. **Fixed the same day**, in the dataset and with a new check.

**What is true.** The golden set is deliberately balanced — 45 clear failures against 45 clear
passes at v0.1.0, because "flag everything" is the failure mode a compliance tool falls into
naturally and an unbalanced key would not catch it. That balance is real in the file and was not
real in the scoring, because `accuracy._record` does not treat the two sides alike:

```
expected `fail`       always counts — a true positive if found, a false negative if not
expected `pass`       counts ONLY if the checker actually SELECTS the element
expected `uncertain`  never counts; scored on calibration instead
```

A `pass` record whose element the selection rules skip is **inert**: it can never contribute to
any figure in either direction, and it looks exactly like a healthy record in every other check.

**Where it bit hardest.** `label` / 2.5.3 had 19 clear records and could reach a scored sample of
**9**. All ten pass twins name a control whose accessible name already contains its visible text,
and `_applies_label` skips precisely those — correctly, because the criterion is then met as a
matter of fact and there is nothing left to judge. So the only 2.5.3 records the checker could
ever be scored on were failures. Measured ceilings at v0.1.0, against the 30 the scorer requires:

| Checker | Records | Could ever score | Short by |
|---|---|---|---|
| `alt` | 22 | 20 | 10 |
| `color` | 23 | 19 | 11 |
| `label` | 20 | **9** | 21 |
| `semantics` | 27 | 25 | 5 |
| `structure` | 7 | 6 | 24 |

The plan written before this was measured budgeted 60 new records on the assumption that
"records minus the arguable ones" was the ceiling. The real figure was 74, and `label` needed
more than three times what the plan allowed for it.

**Why no existing check saw it.** `verify-golden.js` proves every label's `(route, selector)`
resolves on the running page and re-derives under the companion's own `cssPath()`. That is
necessary and it is not the same question. Resolving is about the page; scoring is about the
selection rules, and nothing compared the answer key against them.

**Fixed 2026‑08‑28.**
1. The 74 records added for v0.2.0 were each checked against the real selection rules **before**
   their label was written. All 74 are claimed by the checker they name, including all 37 pass
   records.
2. Where a checker's pass side is structurally hard to reach, the records are the cases that do
   reach it. For `label` that meant pass twins whose name differs from the visible label by a
   typographic mark — which both axe and the W3C rule treat as a separator, so the criterion is
   met while the strings still differ and the element is still judged.
3. `harness/verify-selectable.js` + `scorer/selectable.py` now assert this, in `npm run check`.
   It captures in Node and decides in Python using `rules.py` itself, never a copy.

**The general lesson, and it is not about accessibility.** *An answer key is only balanced with
respect to the questions the system is actually asked.* A checker that filters its own inputs —
which every one of ours does, deliberately — reshapes the distribution it is measured on, and a
key balanced before that filter can be lopsided after it. Any evaluation set for a component
that selects its own work needs to be balanced **downstream** of the selection, and needs a check
that says so.

---

## R21 — The label check compared letters where the standard compares words

**Found 2026‑08‑28**, while building pass examples for 2.5.3. **Fixed the same day.**

**What was true.** Before asking the AI about a control, `_applies_label` checked whether the
accessible name already contained the visible label — and did it with a plain substring test.

A button reading **"Search"** whose accessible name is **"Research tools"** passed that test,
because the letters of *search* sit inside *research*. The rule concluded the criterion was
already satisfied and never asked anybody. It is not satisfied: a speech-input user looks at the
button, says "Search", and nothing happens, because there is no such **word** in the name.

Both the criterion's own ACT rule (`2ee8b8`) and axe-core compare **whole words**, treating
punctuation as a separator. We compared characters.

**Two opposite errors that cancelled out on a scoreboard.** The same test also asked about
controls it should have left alone. A button reading "Update details…" named "Update details"
differs by one character, so the rule sent it to the judge — when by the standard it is
provably fine and there is nothing to judge.

**Fixed** by comparing word sequences after replacing punctuation with spaces, Unicode-aware so
that accented and non-Latin labels survive (a naive `[a-z0-9]` filter would empty every label in
any language but English and make every control look like a mismatch).

**What it cost, and why the cost was accepted.** Eleven of the golden set's `label` pass records
were exactly the "differs by a typographic mark" shape. Under the corrected rule they are
provably-fine controls the checker rightly skips, so they stopped scoring and `label` fell from
31 reachable records to **20** — below the 30 the scorer requires.

**That gap cannot be closed by writing more records, and the reason is worth understanding.**
After the fix, the only controls that reach the judge are ones where the words genuinely differ
— and those are either real failures or genuinely arguable cases. **A clearly-correct example
is, by definition, one the check skips.** So 2.5.3 cannot have a balanced scored sample at all.
Recall for that checker is meaningful; precision is not, because no correct examples remain that
it could get wrong. Recorded in `scorer/selectable.py`'s `KNOWN_SHORTFALL` with that reasoning,
so the harness reports it rather than failing, and an *unrecorded* shortfall still fails.

**The general shape, and it is the same as R20's.** A component that filters its own inputs
decides what it can be measured on. Fixing the filter changed the measurable population — and
keeping the defect to protect a number would have been exactly backwards.

**What it changes for a client.** Audits from this date report controls whose accessible name
merely contains the visible label's letters rather than its words. Earlier audits could not.

---

## R22 — The check that guards the answer key could not see the failure it exists to find

**Found 2026‑08‑31**, by a live audit rather than by the check. **Fixed the same day.** This is
R20 one level deeper, and it is the more uncomfortable of the two.

**What R20 built.** `verify-selectable.js` + `scorer/selectable.py`, to prove that every
hand-written record can actually reach the checker it names — because a record can resolve
perfectly on the page and still be structurally incapable of contributing a number.

**What it could not see.** Selection is **two steps**, and R20's check only ran the second:

```
the capture COLLECTS what matches its OFFER list   <- never checked
the rules then CLAIM what they want                <- this is what was checked
```

The check reached each recorded element with `document.querySelector`, which finds anything on
the page whether an audit would collect it or not. So the one failure it could never detect was
**an element the capture does not offer** — and that is the failure a capture-side gap produces.

**What that hid, and the asymmetry is why it stayed hidden.** `accuracy._record` counts an
expected-`fail` record toward a checker's ceiling **whether or not anything ever reaches it** — a
miss is still a scored outcome. So three `structure` records on class-less container divs sat
unreachable while:

| | |
|---|---|
| `structure`'s reported reachable sample | **30** — over the floor, healthy |
| `structure`'s failure records that no judge could ever find | **3 of 15** |
| Its best achievable recall, therefore | **80%**, and nothing said so |

A ceiling is not a floor. R20's check measured the sample a checker could reach and never asked
whether the elements in it would arrive.

**Fixed** by making the two steps distinguishable and reporting them as different problems:

1. The `OFFER` list is **exported** from `runner/companion/assets/a11y_audit.mjs` and imported by
   the harness — one definition, the same discipline R20 already applied by importing `rules.py`
   rather than restating it.
2. The check compares **element identity**, not selector strings. The companion writes its own
   `cssPath`; comparing that against a hand-written golden selector would call two spellings of
   one element a miss.
3. `selectable.py` reports *collected then declined* separately from *never collected*, and only
   the second fails the run. The first is a rule's decision and is sometimes a property of the
   criterion (that is what `KNOWN_SHORTFALL` is for); the second is a gap no answer key can
   compensate for.

**Proved rather than asserted:** with the capture-side fix temporarily removed, the check names
all three records by id and exits non-zero.

**The general lesson, and it is not about accessibility.** *A guard is only as wide as the
pipeline it models.* R20's guard modelled selection as one step because that is how it is usually
described; the system does it in two, and the guard was blind to the whole of the first. Any check
that certifies inputs to a multi-stage pipeline has to run **every** stage, or it certifies the
stages it happens to know about and stays green about the rest.

**What it changes for a client.** Nothing directly — this is an internal measurement guard. What
it changes for us is that a capture-side coverage gap can no longer sit behind a green harness,
which is how this one survived for a week.

---

## R23 — "~16 of ~50 success criteria are automatable" — **the denominator is the wrong standard**

**Found 2026‑09‑16.** *Claimed in:* Report 1 p2 and p6; Deep Research p12.

**What is true.** "~50" is WCAG **2.1** Level A + AA. The platform conforms to **2.2**, and 2.2 A + AA
is **55 criteria — 31 Level A and 24 Level AA**. That is not an estimate: it is the platform's own
dataset, `backend/apps/a11y/data/wcag22.json:4` (levels A and AA) and
`backend/apps/a11y/data/wcag22.json:12` (`"criteria": 55`), and the level split is derived from the
55 entries in the same file.

**Addendum A already corrected this** — it is written against 55 throughout, and every guard in the
build fails loudly if the registry is not exactly 55 (R7, R8). The other two reports were never
updated, so the same build is described with two different denominators depending on which PDF a
reader opens.

**Why it matters more than a rounding.** A ratio quoted against 50 makes automated coverage look
better than it is, and the criteria 2.2 added are ones **no scanner decides** — they are judgement
or geometry. So the correct denominator moves in the direction that makes the number worse, which
is exactly why it must be the one used. Use **55** in any coverage statement, and take the coverage
figure itself from [`WCAG_COVERAGE_REFERENCE.md`](WCAG_COVERAGE_REFERENCE.md) rather than from a
report.

---

## R24 — Deque's "57% of issues are found automatically" — **2021 data, and it counted a criterion that no longer exists**

**Found 2026‑09‑16.** *Claimed in:* the reports quote the figure as a current property of automated
testing. Source: https://www.deque.com/automated-accessibility-coverage-report/

**What is true.** The figure is from Deque's 2021 coverage report, and **4.1.1 Parsing is among the
issue categories it counts**. 4.1.1 is obsolete and **removed in WCAG 2.2**
(https://www.w3.org/WAI/WCAG22/Understanding/parsing.html) — the working group's own reasoning is
that browsers recover from the markup errors it described, so the failures it produced were not user
impact. Duplicate ids and unclosed elements are a large, cheap, entirely machine-detectable
category, and taking it out removes findings from the **automated** side of the ratio and nothing
from the human side.

**So the honest statement is that the true figure against WCAG 2.2 is lower, and nobody has
published what it is.** We do not know by how much, and estimating it ourselves would be inventing a
number to replace a stale one.

**What to do with it.** Quote it only as *"Deque measured 57% in 2021, against WCAG 2.1 and
including a criterion 2.2 has since removed — the figure against 2.2 is lower"*, or do not quote it.
It is not a floor, it is not a target, and it is not the basis of any decision in this build: what
the platform actually detects is measured, not cited (R13, R15, R18).

---

## R25 — "67% of accessibility issues originate in design" — **it was a 67% reduction, not an origin**

**Found 2026‑09‑16.** Widely quoted in the industry and reproduced in the reports as a fact about
where defects come from.

**What is true.** The number traces to Deque's own post on auditing design systems
(https://www.deque.com/blog/auditing-design-systems-for-accessibility/), and the analysis at
https://audreefletcher.co.uk/blog/67-of-accessibility-issues-originate-in-design shows what it
actually measured: a **67% reduction in automatically detected defects** after a team changed its
design-system practice. That is a statement about **what improved**, not about **where problems
start** — and it is measured on the automatically detectable slice only, which R24 has just finished
saying is the smaller and easier half. The analysis puts the adjusted figure at roughly **38%**.

**The two claims are not even the same shape.** "67% of issues originate in design" is a census of
causes. "Fixing design removed 67% of what a scanner could see" is a before-and-after on one team,
one product, one class of defect. The first cannot be derived from the second.

**Decision: we do not use this number in client-facing material** — not the 67%, and not the 38%
either, because the corrected figure inherits the same single-team, scanner-only basis. The argument
for shifting accessibility left does not need it and is not weakened without it: R1 through R22
above are our own evidence that a defect is cheaper to prevent than to find, and they are evidence
about this platform rather than somebody else's.

---

## R26 — EN 301 549 has moved to WCAG 2.2, and the legal reference has not

**Found 2026‑09‑16.** *Claimed in:* the reports state that EN 301 549 maps to WCAG 2.1 AA.

**What is true, and both halves must be said together.** **EN 301 549 v4.1.1 was published in
September 2026 and adopts WCAG 2.2.** It is **not yet cited in the EU Official Journal**, and until
it is, **v3.2.1 — WCAG 2.1 AA — remains the legal reference** for the presumption of conformity.
Source: https://accessible-eu-centre.ec.europa.eu/content-corner/news/european-accessibility-standard-en-301-549-has-been-updated-2026-09-07_en

| | |
|---|---|
| What a client is legally measured against today | EN 301 549 **v3.2.1** → WCAG 2.1 AA |
| What the standard body has already published | EN 301 549 **v4.1.1** → WCAG 2.2 |
| What the platform checks against | **WCAG 2.2 AA** (R23) |

**This is the comfortable direction to be wrong in, and it should still be stated rather than
enjoyed.** Checking against 2.2 satisfies a 2.1 obligation, because 2.2 keeps every 2.1 criterion
except 4.1.1 (R24) and adds to it. So a client who passes our audit passes the current legal
reference too, and is ready for the citation when it lands. What we must **not** say is that the
reports were simply wrong: they were correct when written, and "EN 301 549 means 2.1" will be
correct until the Journal citation, which has no announced date.

---

## R27 — The US ADA Title II dates in the Deep Research report are inconsistent, and all of them are superseded

**Found 2026‑09‑16.** *Claimed in:* Deep Research — one client profile still refers to a 2026
deadline while other passages give different dates.

**What is true.** The April 2026 interim final rule **extended** the compliance dates. The current
dates are **26 April 2027** for public entities with a population of 50,000 or more, and **26 April
2028** for smaller entities and special district governments. Source:
https://www.federalregister.gov/documents/2026/04/20/2026-07663/extension-of-compliance-dates-for-nondiscrimination-on-the-basis-of-disability-accessibility-of-web

**Why an internal contradiction is worse here than a stale date.** A single wrong date is corrected
once. A document that carries two makes every reader's answer depend on which page they opened, and
this is the class of claim a client plans budget against. The dates above are the ones to quote, and
they should be re-checked against the Federal Register rather than against this file before they go
into anything a client reads — a date that moved once can move again.

**Note also what the extension does not change.** The rule's technical standard is **WCAG 2.1 AA**,
same as R26's, and the same reasoning applies: checking against 2.2 satisfies it.

---

## R28 — "Already built" and "on the roadmap" were both wrong, and the truthful answer is now "built, in August"

**Found 2026‑09‑16.** *Conflict between:* the Feasibility report — the accessibility gate is *"a
locked, built feature (Phase 3)"* and the eval harness *"EXISTS"* — and the Journeys report, which
puts both *"on the roadmap"*.

**Both reports were written before the work existed**, so the disagreement is not between a right
source and a wrong one; it is between two guesses. R3 and R6 above already record what was true at
the time the corrections were written: there was a reviewer-ticked checklist on the **design** gate
and nothing on the test gate, and there was no eval harness and no pipeline to run one in.

**What has changed since, and this is the part neither R3 nor R6 can say.** The derived accessibility
condition on the **testing** gate was built in **August 2026** and is
`backend/apps/gates/a11ygate.py:77` (`a11y_condition`), marked platform-evaluated at
`backend/apps/gates/a11ygate.py:93` (`"derived": True`) so that, in `testgate.py`'s words, a reviewer
can never tick past it. Its history confirms the date and shows it has been extended four times
since: `git log --oneline -- backend/apps/gates/a11ygate.py` → `b2a1636` (2026‑08‑17, the gate
itself), `cc6fec4` (2026‑08‑17, inherited debt), `5162514` and `1c5798f` (2026‑08‑18), `41b9068`
(2026‑09‑07).

**So the Feasibility report's sentence is accidentally true today and still must not be cited.** It
was not true when written, it names the wrong phase, and a claim that happens to become true later
is not evidence of anything. **R6's half has not changed**: the harness runs locally via `make`, by
decision D4, and there is still no CI pipeline in this repository.

**The general point, and it is the only one worth carrying forward.** A research report cannot state
what a codebase contains — not because these authors were careless, but because the codebase moves
and the PDF does not. Every "ALREADY EXISTS" in all six reports should be read as a *hypothesis to
check*, and the place that answers it is the repository, with a file and a line.

---

## R29 — "Agent 09 runs axe at WCAG 2.1 AA" — **09 targets 2.2, and no agent in the repo targets 2.1 any more**

**Found 2026‑09‑16.** *Claimed in:* the Feasibility Assessment.

**Two separate errors in one sentence, and R1 only corrected the first.** R1 above establishes that
agent 09 does not *run* anything — its axe snippet is prose, and the running is 09b's (QA‑11a). The
**version** half went uncorrected until now: `agents/09_testing/agent.md:13` states the agent tests
*"against WCAG 2.2 AA"*, its evidence base cites WCAG 2.2 AA at `agents/09_testing/agent.md:36`, and
its own traceability example carries `WCAG 2.2 AA` at `agents/09_testing/agent.md:186`.

**Wider than agent 09, as of this commit.** The five agents that still named 2.1 have been uplifted
to 2.2:

| Agent | Where it names the standard now |
|---|---|
| `05_ux_design` | `agents/05_ux_design/agent.md:10`, `:15`, `:29`, `:448`, `:506` |
| `08_code_review` | `agents/08_code_review/agent.md:34` |
| `03_prd` | `agents/03_prd/agent.md:250` |
| `02_requirements` | `agents/02_requirements/agent.md:265` |
| `00e_document_vision` | `agents/00e_document_vision/agent.md:27` |

A grep for `WCAG 2.1` across `agents/` now returns two hits and **neither is a version**: they are
`agents/09d_a11y_journey/agent.md:140` and `:153`, which name **criteria** 2.1.1 Keyboard and 2.1.2
No Keyboard Trap. So no agent in the repository targets WCAG 2.1.

**Why this needed doing rather than noting.** R3 already caught `gates/wcag.py` about to be left at
2.1 while everything around it moved, and made the point that a version reference nobody owns is a
version reference that goes stale. The agents are the same case: 05 writes the accessibility spec a
whole project is built against, and a spec written to 2.1 would have quietly under-specified every
criterion 2.2 added — the same criteria R23 says are the ones no scanner can recover for you.

---

## R30 — "Near-deterministic via temperature 0" — **temperature 0 does not promise that**

**Found 2026‑09‑16.** *Claimed in:* Report 1 and Addendum B, as the mechanism by which repeated runs
give repeatable findings.

**What is true.** Temperature 0 makes sampling greedy. It does not make a model's output identical
across runs: floating-point non-associativity in batched inference, model and serving-stack
versions, and context differences all move the result, and none of them is a setting a caller
controls. Treating it as a determinism guarantee promises a client something no vendor offers — and
it is the wrong promise anyway, because our judgement runs go through `ExecutionDriver` on the
subscription (R4), not through an API where such a parameter is even ours to set.

**The platform's own framing is the honest one, and it is already built.** Non-determinism here is
**managed, not eliminated**, and every piece of the management is a thing in the repository rather
than a claim: the deterministic engine decides what it can decide and the judge is asked only what a
rule cannot answer (R13, R14); a judgement below the confidence threshold is routed to a person and
never dropped (R11, D7); a run that captures elements and returns no verdict **blocks the gate**
rather than reading as clean (`backend/apps/gates/a11ygate.py`); a finding that went in and did not
come back fails the run loudly (R4's write-completeness check); and the checkers are measured against
a golden set rather than asserted (R20, R21, R22).

**What a client should be told**, and the difference matters when an auditor asks: not *"the same
page always produces the same findings"*, but *"the same page always produces findings decided by
the same rules, with anything uncertain shown to a person, and nothing discarded."* The first is a
claim we cannot keep. The second is stronger, it is what the build actually does, and it is the one
that survives being checked.

---

## Two things worth recording that the reports got *right*

- **The core architecture is sound.** "Deterministic core, AI on top; grounded in the real criterion text; confidence-gated; never auto-certify" survives contact with the codebase completely intact. Nothing in this correction touches it.
- **The platform really is a good host for this.** Every guardrail the reports insist on — human sign-off, tenant isolation, audit trails, swappable engines — is machinery the platform already has, not something this build must invent.

---

**Cross-refs:** **what we actually check today, with the commands to re-derive every number = [`WCAG_COVERAGE_REFERENCE.md`](WCAG_COVERAGE_REFERENCE.md)** (read that first if you need a coverage figure); the corrected tasks are in `TASK_BACKLOG_QA.md` and `TASK_BACKLOG_OTHER_PHASES.md`; build order in `BUILD_PLAN_QA.md`; the journeys these serve in `USER_JOURNEYS.md`.
