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

---

## R2 — "Rendered capture + accessibility tree — ALREADY EXISTS" — **TRUE BUT NARROW**

*Claimed in:* Feasibility Assessment §2.1.

**What's actually true.** Playwright MCP is real, but it is handed **only to the `test_automation` phase** (`runner/companion/guardrails.py:282`), and it runs **on the developer's machine** inside the companion. The live application it drives comes up from `preview_start` config, and `PreviewEnv.Provider` has exactly one value: `companion_local`.

**Why this matters more than it sounds.** The app under test runs at a **localhost URL on a developer's laptop**. The server cannot reach it. Any design that assumes the platform can open a browser and visit the app is wrong. Browser work belongs in the companion; judgment, triage, findings and gates belong server-side.

---

## R3 — "WCAG gate / merge gate — ALREADY EXISTS" — **MISLEADING**

*Claimed in:* Feasibility Assessment §2.1.

**What's actually true.** `backend/apps/gates/wcag.py` is a **hand-typed checklist of 9 WCAG 2.1 criteria** that a human reviewer ticks, attached to the **design** gate (`_WCAG_GATED_PHASES = {"ux_design"}`). It is a person confirming they looked. It is not a machine deciding pass/fail from findings, and it is not on the test gate.

**The pattern we actually need already exists elsewhere.** `backend/apps/gates/testgate.py` is a **derived** condition — the platform evaluates it from live state at decide time, and its own comment explains why that matters: *"a reviewer can never tick past a red suite."* Accessibility deserves the same protection.

**Also caught:** no task in either backlog touched `gates/wcag.py`, so it would have silently stayed at WCAG 2.1 while everything else moved to 2.2.

**Tasks:** **QA‑11** expanded to include the `gates/wcag.py` uplift; **QA‑15** adds a derived a11y condition; new **QA‑15a** fixes a latent bug in `refresh_derived` (it hardcodes the *test* evaluator for every derived condition, so a second derived condition would silently never refresh).

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
| "register the app's screens/routes" | nothing — no route registry exists |

This is exactly the failure the migration spec warns about (*"a migrated agent still naming a local file is a FAILED migration"*) — except here it is the **plans** naming dead files, not the agents.

**Tasks:** OP‑01, OP‑02, OP‑06, OP‑07 and QA‑17 updated to name artifact types instead of file paths.

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

The prose rounds; the **lists are exact and internally consistent**: 15 + 15 = 30 human-primary, and 20 + 20 + 15 = 55 total. Where prose and list disagree, **the enumerated lists are authoritative** — QA‑05 is built from the lists.

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
