# Research Corrections — what the reports got wrong about the platform

**What this is.** The six research PDFs under `Web-accessibility-research-evidence/` are the *why* behind this build, and they stay exactly as written — they are client-facing reports and a historical record. But several of their claims about **what the platform already does** turned out to be wrong when checked against the source. This file is the record of those corrections, so nobody plans against a claim that isn't true.

**The one sentence that explains almost all of them.** The reports were written against the **legacy agent suite** (`/legacy_suite/`), not the **migrated platform agents** (`/agents/`). The Journeys report says so itself — its evidence base cites `legacy_suite/agents/05_ux_design_agent.md`, `legacy_suite/agents/08_code_review_agent.md` and `legacy_suite/agents/00_onboarding_agent.md`. Those are the un-migrated v6 sources we keep for reference, not the agents the platform runs.

Think of it as planning a renovation from the *original* blueprint after the house was rebuilt to a new one. The rooms moved. Most of the plan still stands — but the steps to the back door lead nowhere, because there is no longer a back door there.

**Status:** all nine corrections below are agreed team decisions (2026‑08‑12). Where a correction changed the build, the affected tasks are named.

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

## Two things worth recording that the reports got *right*

- **The core architecture is sound.** "Deterministic core, AI on top; grounded in the real criterion text; confidence-gated; never auto-certify" survives contact with the codebase completely intact. Nothing in this correction touches it.
- **The platform really is a good host for this.** Every guardrail the reports insist on — human sign-off, tenant isolation, audit trails, swappable engines — is machinery the platform already has, not something this build must invent.

---

**Cross-refs:** the corrected tasks are in `TASK_BACKLOG_QA.md` and `TASK_BACKLOG_OTHER_PHASES.md`; build order in `BUILD_PLAN_QA.md`; the journeys these serve in `USER_JOURNEYS.md`.
