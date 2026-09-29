# WCAG 2.2 AA Across the Whole Lifecycle — Findings, Answers and Build Steps

**Date:** 2026-09-16 · **Branch read:** `SDLC_Bug_Fix_Enhancements` @ `7dbf501` (contains all of `web-accessibility-build` and `brownfield-agent-onboarding`)
**Status:** RESEARCH + PROPOSAL. **Nothing is built.** Every change below waits for the team's decision.
**Target:** WCAG 2.2 Level AA — 55 success criteria (31 Level A + 24 Level AA). Level AAA optional, per project.
**Scope:** greenfield, and both brownfield cases — new screens on an existing app, and bringing existing screens up to standard.
**Evidence base:** the six research PDFs, all 12 accessibility docs, all 19 agent bodies, the platform source, git history, 46 outside sources, and a read-only review of three real tenants on the shared server (§4).

**How to read this document.** It is written so that nobody has to open another file. Where it refers to code or an agent, it quotes the relevant line. Where it proposes a change, it gives the wording or the shape of the change, the files it touches, how it is proved, and what it still cannot do.

| Section | What it answers |
|---|---|
| §1 | The assignment, restated |
| §2 | Plain-language primer: what WCAG 2.2 AA actually is, and the one rule that shapes the whole design |
| §3 | How the platform works today, end to end |
| §4 | What three real tenants show — the problem, on live data |
| §5 | **Question 3** — what the team already built, agent by agent, and how much is reusable |
| §6 | **Question 1** — UX Design: how far it can go, and the ten steps in full |
| §7 | **Question 2** — the phases before UX Design, with the exact content each one gains |
| §8 | Every phase after UX Design |
| §9 | **Question 4** — greenfield and brownfield |
| §10 | Build order, task by task, with files, tests and effort |
| §11 | The decisions the team has to make, with options and a recommendation |
| §12 | Docs and code found out of date |
| §13 | Every source |
| Companion file | [`CORRECTIONS_2026-09-16.md`](CORRECTIONS_2026-09-16.md) — the out-of-date statements in §12, now corrected in the repo, with the evidence and reasoning for each |
| **§14** | **The team's follow-up questions (2026-09-16): logged-in pages and other gaps the audit cannot reach, tech-stack and dynamic-page support, the `<td>` history and what else may surprise us, Figma designs, ideation, architecture, the greenfield conformance report, and splitting the UX agent** |

---

## 1. The assignment, restated

**Where we are.** The platform finds accessibility problems **after the product exists**. There are two places it does this:
1. **Brownfield audit** — a client's already-running application is crawled and judged. This is proven: 94 pages, 1,068 questions, 410 problems found (2 Sep 2026).
2. **Testing phase** — after code is built, `09b` runs the scanner, `09c` judges elements it cannot decide mechanically, and `09d` walks keyboard journeys.

**What the client asked for.** Start at UX Design, so the product is *built* accessible instead of audited and repaired afterwards.

**What the team wants on top of that.** Put accessibility into *every* phase where it is required, where it should be, or where it is worth having — and reuse what has already been built rather than starting again.

**The four questions, and where each is answered.**

| # | Question | Section |
|---|---|---|
| 1 | Can WCAG 2.2 be built into UX Design so every screen it generates is compliant? To what extent, and in what detailed steps? | §6 |
| 2 | Which phases *before* UX Design should carry accessibility, and why are they truly needed? | §7 |
| 3 | How much of the team's existing accessibility work can be used, and how good is it? | §5 |
| 4 | Does the answer work for both greenfield and brownfield? | §9 |

---

## 2. Primer: what WCAG 2.2 AA is, and the one rule that shapes everything

This section exists so nobody has to read the six research PDFs to follow the rest.

### 2.1 The structure of the standard

- WCAG is organised under four principles — **Perceivable, Operable, Understandable, Robust** — then 13 guidelines, then **success criteria**, which are the testable statements.
- Each criterion has a level: **A** (most basic), **AA** (the usual legal target), **AAA** (not expected across a whole product; W3C itself says so).
- **WCAG 2.2** was published 5 October 2023, current edition 12 December 2024 ([W3C](https://www.w3.org/TR/WCAG22/)).
- **A + AA = 55 criteria** (31 A + 24 AA). I counted these from the specification's own table. This is the number our platform uses, and it is correct. The older "~50" figure in the research PDFs is WCAG 2.1 and should not be quoted again.

### 2.2 What WCAG 2.2 added over 2.1 — the nine new criteria

These matter because **six of the nine are things a designer decides**, which is precisely why shift-left pays.

| Criterion | Level | In plain words | Who really decides it |
|---|---|---|---|
| 2.4.11 Focus Not Obscured (Minimum) | AA | When you tab to something, a sticky header or cookie bar must not hide it | Design (sticky elements) |
| 2.4.12 Focus Not Obscured (Enhanced) | AAA | Nothing may hide it at all | Design |
| 2.4.13 Focus Appearance | AAA | The focus ring must be big and contrasting enough | Design tokens |
| 2.5.7 Dragging Movements | AA | Anything you can drag must also work without dragging | Design (interaction) |
| 2.5.8 Target Size (Minimum) | AA | Clickable targets at least 24×24 CSS pixels | Design (component sizes) |
| 3.2.6 Consistent Help | A | Help/contact appears in the same place on every page | Design (information architecture) |
| 3.3.7 Redundant Entry | A | Don't make people type the same thing twice in one process | Requirements + design (flow) |
| 3.3.8 Accessible Authentication (Min) | AA | No memory or puzzle test to log in; allow paste and password managers | Requirements + architecture + security |
| 3.3.9 Accessible Authentication (Enhanced) | AAA | Even stricter | Same |

**Also:** criterion **4.1.1 Parsing is obsolete and removed** in 2.2 ([W3C Understanding](https://www.w3.org/WAI/WCAG22/Understanding/parsing.html)). Real markup faults now fail 1.3.1 or 4.1.2 instead. Our agent bodies do not mention 4.1.1, which is correct.

### 2.3 The one rule that shapes the entire solution

> **WCAG conformance is judged on the rendered page, not on a design.**
> The specification requires *full pages*, *complete processes*, *accessibility-supported techniques* and *non-interference* ([WCAG 2.2 §5](https://www.w3.org/TR/WCAG22/#conformance)).

A wireframe is not a web page, so **no design can "be compliant"**. Two consequences:

1. **UX Design cannot be the end of the story.** It can remove the *causes* of most failures, and the platform can machine-check a large part of that at design time — but the claim "this conforms" can only be made after the product is built and tested, with a human sign-off. The team's existing testing layer is therefore not replaced; it becomes the proof.
2. **We must be careful what we tell the client.** The FTC fined accessiBe $1,000,000 for over-claiming automated accessibility ([FTC, Jan 2025](https://www.ftc.gov/news-events/news/press-releases/2025/01/ftc-order-requires-online-marketer-pay-1-million-deceptive-claims-its-ai-product-could-make-websites)). Our platform's existing conformance module already behaves correctly here — it *suggests* a level and refuses to claim conformance without human signature.

**The honest wording at each stage — recommended for client-facing text:**

| Stage | What we may say |
|---|---|
| Requirements / PRD | "WCAG 2.2 AA is a stated, measurable requirement of this product" |
| UX Design | "Every screen is designed to WCAG 2.2 AA intent, and machine-checked for everything a design can be checked for" |
| Implementation + code review | "Built to that specification, and passing automated accessibility checks" |
| Testing | "Verified by scanner, AI judgment and keyboard journeys" |
| Release | "Conforms to WCAG 2.2 AA for the pages and processes listed, signed by *name*, on *date*" |

### 2.4 How much can be automated — and the two figures not to quote

- Deque's widely quoted "**57% of issues** are found automatically" comes from 2021 data across ~300,000 issues ([Deque](https://www.deque.com/automated-accessibility-coverage-report/)). **Caveat:** 4.1.1 Parsing — now removed from the standard — was among its top categories, so the real figure against WCAG 2.2 is likely lower. Quote it with that caveat or not at all.
- "**67% of accessibility issues originate in design**" is widely repeated and **disputed**. The original was a *67% reduction* in automatically detected defects after design practice changed, not a measure of where issues start ([Deque's post](https://www.deque.com/blog/auditing-design-systems-for-accessibility/) vs [Audree Fletcher's analysis](https://audreefletcher.co.uk/blog/67-of-accessibility-issues-originate-in-design), which puts the adjusted figure near 38%). **Do not put this number in a client deck.**
- What *is* safe to say, from [WebAIM's Million, Feb 2026](https://webaim.org/projects/million/) (an annual scan of 1,000,000 home pages): **95.9% of home pages had detectable failures**, averaging 56.1 errors per page. The top five are all design or markup decisions: low contrast 83.9%, missing alt text 53.1%, missing form labels 51%, empty links 46.3%, empty buttons 30.6%. Every one of those five is preventable at design and build time.

### 2.5 The legal picture (why clients ask)

| Law or standard | Version it requires | Dates |
|---|---|---|
| **European Accessibility Act** (Directive 2019/882) | via EN 301 549 | In force for products/services placed on the market from **28 June 2025**; everything in scope by 2030 |
| **EN 301 549** (the EU technical standard) | v3.2.1 = WCAG 2.1 AA today. **v4.1.1, published September 2026, moves to WCAG 2.2** but is not yet cited in the EU Official Journal, so 2.1 remains the legal reference for now | [AccessibleEU, 7 Sep 2026](https://accessible-eu-centre.ec.europa.eu/content-corner/news/european-accessibility-standard-en-301-549-has-been-updated-2026-09-07_en) |
| **US ADA Title II** (state and local government) | WCAG 2.1 AA | Deadlines **extended in April 2026** to 26 Apr 2027 (population 50,000+) and 26 Apr 2028 (smaller) — [Federal Register](https://www.federalregister.gov/documents/2026/04/20/2026-07663/extension-of-compliance-dates-for-nondiscrimination-on-the-basis-of-disability-accessibility-of-web) |
| **US Section 508** (federal procurement) | WCAG 2.0 AA | In force |
| **UK Equality Act 2010** | No version named; WCAG 2.1/2.2 AA is the accepted practice | In force |

**Conclusion:** building to **WCAG 2.2 AA covers all of them**, because 2.2 includes everything in 2.1 and 2.0. That is why 2.2 AA is the right platform default — and why the UX agent still teaching 2.1 is a real problem, not a cosmetic one.

### 2.6 What the research says about AI agents writing accessible code

This is the evidence behind the most important design decision in this document.

- **"Human or LLM?"** ([arXiv 2503.15885](https://arxiv.org/abs/2503.15885)) compared model-generated web code with human code. Models did well on contrast and alt text, **badly on ARIA**. Zero-shot, few-shot and self-critique prompting gave limited gains and sometimes **introduced new ARIA faults**. What worked was **FeedA11y**: let the model read a real checker's output and repair. Inaccessibility rate fell to 0.300, against 0.425 for human code and 0.348 for plain generation.
- **CodeA11y** (CHI 2025, [ACM](https://dl.acm.org/doi/10.1145/3706598.3713335)) studied 16 developers using AI assistants and found three failures: they never ask for accessibility, they skip manual follow-ups such as replacing placeholder alt text, and they cannot verify what they got.
- **A11yN** ([arXiv 2510.13914](https://arxiv.org/abs/2510.13914)) trained against a reward derived from a real testing engine and reports up to 87.5% lower inaccessibility rate. **AccessGuru** ([arXiv 2507.19549](https://arxiv.org/abs/2507.19549)) and **A11YRepair** ([arXiv 2606.21926](https://arxiv.org/abs/2606.21926)) report the same pattern.

> **The lesson for us:** telling an agent "follow WCAG 2.2 AA" does not work. **Generate → run a real checker → repair → re-check** does. Our platform already owns the checkers. The work is connecting them to the earlier phases. Every proposal in §6–§8 follows this shape.

---

## 3. How the platform works today, end to end

### 3.1 The phases and their gates

From `backend/apps/registry/catalog.py:88-169` — 19 agent specs. "Build" means the phase runs through `BuildWorkflow` (worktree → commit → PR → review → merge gate); everything else is a planning run that ends at a gate.

| Phase | Agent | Kind | Main artifacts | Gate approved by |
|---|---|---|---|---|
| Onboarding (brownfield only) | `00_onboarding` | planning | `gap_report` | product_owner |
| Context extraction | `00c_intelligent_context_extractor` | reads code | `codebase_intelligence`, `dependency_graph`, `git_analytics`, `dead_code`, `architecture_decisions` | tech_lead |
| Document vision | `00e_document_vision` | native | new version of a document | product_owner |
| 01 Ideation | `01_ideation` | planning | `ideation`, `feasibility_report`, `stakeholder_map` | product_owner |
| 02 Requirements | `02_requirements` | planning | `requirements`, `user_stories`, `use_cases`, `traceability_matrix` | product_owner |
| 03 PRD | `03_prd` | planning | `prd`, `glossary` | product_owner |
| 04 Architecture | `04_architecture` | planning | `architecture`, `adr`, `api_spec`, `data_model`, `security_architecture`, `tech_stack` | architect |
| **05 UX Design** | `05_ux_design` | planning | `ux_design`, `user_journey`, **`wireframe` (one per screen)**, `design_system`, **`accessibility`** | **designer** |
| 06 Task Breakdown | `06_task_breakdown` | planning | `backlog`, `definition_of_done`, proposed work items | tech_lead |
| 07 Implementation | `07_implementation` | **build** | code, pull request | tech_lead |
| 08 Code Review | `08_code_review` | inside the build loop | `code_review` + REM findings | reviewer |
| 09 Testing | `09_testing` | planning | `test_plan`, `test_case` | qa_lead |
| 09b Test Automation | `09b_test_automation` | **build** | test scripts, `test_report`, **`a11y-candidates.json`** | qa_lead |
| 09c A11y Judge | `09c_a11y_judge` | native | accessibility findings | qa_lead |
| 09d A11y Journey | `09d_a11y_journey` | native | keyboard journey results | qa_lead |
| 10 Security | `10_security` | reads code | `security_review`, `security_finding`, `threat_model` | security_engineer |
| 11 CI/CD | `11_cicd` | **build** | pipeline config | devops |
| 12 Deployment | `12_deployment` | planning | `release_notes`, `rollback_runbook` | devops |

**Gate mechanics that matter later.** A gate can carry two kinds of condition:
- **Attested** — a person ticks it. The UX gate's WCAG checklist is of this kind.
- **Derived** — the platform computes it and *refuses a reviewer's tick*. `services._merge_conditions` rejects a `satisfied` update on a derived condition (`a11ygate.py:78-88`). Three exist today: `no_blocking_test_failures`, `no_blocking_a11y_failures`, `no_blocking_security_findings`.

This distinction is the hinge of the whole proposal: **§6 adds a derived condition to the UX gate**, so the design can no longer be waved through — which is exactly what happened on a real project (§4).

### 3.2 The accessibility subsystem the team built

81 commits on `backend/apps/a11y` between 12 August and 11 September 2026.

**The knowledge base.** `data/wcag22.json` holds all 55 A/AA criteria with their normative text, 94 ACT rules and 101 glossary terms. `wcag.py` exposes `criterion()`, `criterion_text()`, `terms_for()` and `grounding()`. The judge is handed the real wording rather than relying on the model's memory (`09c:39-41`). These tables are platform-wide, not per tenant (migration `0006_wcag_platform_wide`).

**Who checks what.** `data/ownership.json` classifies every criterion as rule / AI / human, with a tier (built now / phase 2 / always human). Effective routing today is 13 rule-owned and 12 AI-owned after `ENGINEERING_OVERRIDES` moves 1.4.11 to the judge.

**Three kinds of engine:**
1. **axe-core 4.13.0 in Playwright** — `runner/companion/assets/a11y_audit.mjs`, a reviewed script (not generated per run), and `@axe-core/playwright` inside 09b's generated tests. Tags `wcag2a` … `wcag22aa`; 70 of 105 rules selected, touching 24 criteria.
2. **The platform's own measured rules** — `page_rules.py`: reflow at 320 px (1.4.10), control-edge contrast at 3:1 (1.4.11), and a complete contrast maths set (`parse_color`, `composite`, `relative_luminance`, `contrast_ratio`, lines 88-170) that **has no Django dependency and can be called on anything**. `journey_rules.py` measures focus outlines (2.4.7) and live regions (4.1.3).
3. **AI judgment** — `09c` answers six questions per element: alt (1.1.1), semantics (1.3.1 + 4.1.2), structure (1.3.1), colour (1.4.1), label (2.5.3), graphics (1.4.11). `09d` walks a journey and checks eight criteria: 2.1.1, 2.1.2, 2.4.3, 2.4.7, 2.4.11, 3.2.1, 3.2.2, 4.1.3.

**Coverage today, counted from code:** 27 of 55 criteria have an engine that actually runs; 5 more get a partial flag for a human; 23 have nothing. Of those 23, 12 are asked at the UX design gate as human questions, 4 are optional and off by default, and 7 are asked nowhere.

**How honest it is.** Notable, and worth preserving in everything we add:
- Silence is reported, never guessed — an unscanned page records `axe_error` rather than counting as clean.
- Judging caps (`max_judgments_per_run`, default 200) are recorded so a truncated run cannot masquerade as complete.
- A positive conformance claim is refused unless an entitled engine actually looked, and it is never allowed for the 15 always-human criteria.
- The conformance statement is signed by a qa_lead through a gate, bound to a hash of the wording; any edit clears the signature and new evidence marks it stale.

**Where it is wired in:** testing gate (yes), 09b (yes), brownfield audit (yes, started by a person from a screen), UX design (a manual checklist only), code review (prompt text only), CI/CD (nothing), deployment (nothing).

### 3.3 The gap that blocks everything else

`ProjectProfile.a11y` (`backend/apps/projects/models.py:83`) already stores the project's accessibility policy — for example `{"target": "wcag_2.2_aa", "gate": {...}}`.

But `_profile()` in `mcp_platform_state/tools.py:176-193` builds the dictionary every agent sees, and its keys are: `project_id, name, track, repo_topology, description, domain, tech_stack, coding_standards, nfrs, constraints, glossary, theme, important_context, version`. **`a11y` is not among them**, and `backend/manifest/composer.py` does not render it.

**So no agent is ever told the project's accessibility target.** ~~Five agents hardcode WCAG 2.1 (05, 08, 03, 02, 00e); four hardcode 2.2 (09, 09b, 09c, 09d).~~ **Corrected 2026-09-17: those five were fixed by commit `db3be69` — the same commit that added this document — so every agent now names WCAG 2.2.** The version contradiction is closed; **the finding that matters is not.** A client who needs AAA for one product, or AA for another, still has no way to say so, because the target never reaches any agent — every one of them names a *hardcoded* version rather than the project's own. **This is a two-line fix and it is the prerequisite for everything else** (§6 Step U1).

---

## 4. What three real tenants show — the problem, on live data

Read directly from the shared server's database and object store on 2026-09-15, read-only. No logins, no runs, nothing changed. I did not view the UI: my safety rules forbid me from entering passwords, so a team member would have to sign in once in the app's built-in browser for screen-level checks.

### 4.1 Which code version each tenant ran (the team's cross-check)

`agents/05_ux_design/agent.md` was last modified on **2026-07-22** (`ef37bf9`). Every UX run below therefore used **today's** agent body — its findings are current, not historical. The WCAG 2.2 design checklist landed on 14 August (`1632cba`) and the sixth judge check on 1 September, both **after** the greenfield runs.

| Tenant | Project | What it actually ran | Useful for |
|---|---|---|---|
| **QA-C** | PeopleDesk, greenfield, created 31 Jul | 01–04 on 31 Jul · **05 completed 3 Aug** · 06 on 3–4 Aug · 07 ×85 builds (8 Aug – 10 Sep, 54 completed / 30 failed / 1 rejected) · 158 `code_review` artifacts. **No 09, 09b, 09c, 09d, 10, 11 or 12** | The best available evidence of what UX Design produces today |
| **wcag2** | WCAG-Audit-2, brownfield, 2 Sep | One completed baseline audit · `09c` ×3 (1 completed, 2 failed) · **411 open findings** (335 rule, 77 AI) plus 99 resolved. **No onboarding agents and no lifecycle phases at all** | Confirms the audit runs standalone, disconnected from onboarding and from the phases |
| **test** | SpendLog, greenfield, Jul | All phases 01–12 between 12 and 23 July, including 09, 09b, 10, 11, 12 | Shows the full chain once ran end to end — but it predates every WCAG 2.2 change, so its content is not evidence about today |

### 4.2 What PeopleDesk's UX Design phase actually produced

22 `wireframe` artifacts; **80 HTML state documents** read from the object store and scanned.

**The `accessibility` artifact it registered, in full:**
```json
{ "scope": "SCR-001 through SCR-022 (all 22 screens)",
  "standard": "WCAG 2.1",
  "conformance_level": "AA",
  "key_patterns": ["Skip-to-main-content link", "Focus trap in modals",
                   "aria-live regions for dynamic content",
                   "Explicit confirmation for irreversible operations",
                   "Color never used as sole status indicator"],
  "manual_testing": ["Keyboard navigation", "NVDA+Chrome / VoiceOver+Safari",
                     "200% zoom reflow", "Colour Contrast Analyser"],
  "automated_testing": "axe-core via @axe-core/react + jest-axe in CI" }
```
Two things to notice. It says **WCAG 2.1**, live, on a project running today's agent. And it names **no criterion and no screen** — there is nothing here that a later phase or a check could be measured against.

**What the 80 screen documents contain:**

| Check | Result | What it means |
|---|---|---|
| `min-width: 1280px` | **80 / 80** | Every screen is authored desktop-only, so it cannot satisfy 1.4.10 Reflow (content must work at 320 px). The agent *mandates* this (`05:411`) while its own quality gate demands 375/768/1440 breakpoints (`05:568`) |
| `<html lang>` | 80 / 80 | Good — 3.1.1 satisfied |
| `<main>` and `<nav>` | 70 / 80 | Mostly good |
| `<header>` landmark | 0 / 80 | Missing |
| **Skip link** | **0 / 80** | Missing — although the spec above lists it as a "key pattern" |
| `<h1>` | 60 / 80 | 20 states have no page heading (1.3.1, 2.4.6) |
| `<label>` | **18 / 80** | Most forms have no labels in the markup (3.3.2, 1.3.1, 4.1.2) |
| Live region (`aria-live` / `role="status"`) | 4 / 80 | Missing — although the spec lists it as a key pattern (4.1.3) |
| `autocomplete` | 3 / 80 | 1.3.5 Identify Input Purpose unspecified |
| Visible focus styling | 17 / 80 | 2.4.7 largely unspecified |
| `prefers-reduced-motion` | 0 / 80 | Motion preferences not considered |
| `@a11y` annotations | **0 / 80** | There is no hand-off contract to the developer at all |

**The gate that let this through.** The PeopleDesk UX gate was **approved on 3 August with 9 of 9 conditions ticked**: 1.1.1, 1.4.3, 1.4.4, 2.1.1, 2.4.3, 2.4.7, 3.3.1, 3.3.2, 4.1.2 — the older WCAG 2.1 checklist. A reviewer ticked **2.4.7 focus visible** and **3.3.2 labels** while 63 of 80 screens had no focus styling and 62 of 80 had no labels.

This is not carelessness. A reviewer looking at a picture cannot see markup, and nothing on the screen told them otherwise. **It is the strongest argument in this document for the derived condition in Step U8: put machine evidence beside each question, so a tick means something.**

### 4.3 What happened next

PeopleDesk ran **85 implementation builds and 158 code reviews** on top of these wireframes. Because `07_implementation` copies wireframe HTML and its classes (`07:172-178`), the missing labels, headings, skip link and live regions are very likely now in the product.

**This is an inference, not a measurement** — the code was not scanned, and no 09b capture exists for this project. The honest statement is: the platform currently has **no way to know**, because accessibility does not enter the chain until a testing phase this project has not reached in six weeks of building.

That is the cost of starting at testing, shown on a live project.

---

## 5. Question 3 — what exists, agent by agent, and how much is reusable

### 5.1 The scoring, with evidence

Scores are for accessibility content only, 0–10, from reading all 19 bodies in full.

**`09c_a11y_judge` — 9/10. Keep as is.**
Six checks, each tied to exact criteria, each with boundary cases written out (`09c:176-183`, `09c:346-371`). It is given the normative WCAG text rather than trusting memory (`09c:39-41`). It separates 1.3.1 (structure exists in markup) from 4.1.2 (this control has a name and role) — a distinction most tools blur (`09c:194-208`). Uncertain answers are routed to a human instead of guessed (`09c:422-425`), and a fail is refused unless the required evidence fields are present (`09c:398-407`). Measured precision and recall on the golden set: 1.0/1.0 for alt, label and semantics; 0.833/1.0 for structure; 0.938/0.938 for colour.
*Loses a point for:* only six checks, and the required-fields table has no rows for `structure` or `graphics` although the body demands markup for a structure failure.

**`09d_a11y_journey` — 8.5/10. Keep, extend.**
Eight criteria with reproducible evidence. Good detail: the keyboard-only rule (`09d:107-116`), traps confirmed in both directions (`09d:163-164`), the difference between 2.4.11 minimum and 2.4.12 enhanced (`09d:213-214`), the live-region pitfall where a region added at the same moment as its text is not announced (`09d:246-247`), and measurement kept separate from judgement (`09d:350-353`).
*Loses points for:* it already has `browser_resize` and `browser_hover` tools (`09d:61`) but does not use them for 1.4.10, 1.4.13, 2.5.7 or 2.5.8; and it never reads what the design specified, so it cannot say "this was required and is missing".

**`09b_test_automation` — 8/10. Keep, extend.**
A rigorous capture contract: four separate axe result channels (violations, passes, incomplete, inapplicable), an `axe_error` field so a page that failed to scan is never read as clean, the pinned scanner version recorded with the results, explicit caps (400/600/60), and accessibility findings deliberately kept out of functional pass/fail (`09b:455`).
*Loses points for:* Playwright only — Python projects get capture but no scan (`09b:416-418`); and two stale numbers (`09b:447` says the judge answers "four questions" when it is six; `09b:649` says "all six style keys" when eleven are listed at `09b:515`).

**`09_testing` — 6/10. Good bones, wrong wiring.**
Genuinely enforceable structure: one accessibility test case per screen with a reconciliation step (`09:443`), plain `TC-XXX` identifiers, defined result columns, and clear rules for reading an `a11y_report`.
*Problems, each a real defect:*
- `09:437-438` equates axe's impact word "Critical" with WCAG Level A and "Serious" with Level AA, and gives colour contrast as a Level A example. **axe impact is not a WCAG level**, and 1.4.3 is AA. The platform's own policy already rejects this (severity comes from the level: A→Critical, AA→High).
- Three different severity schemes appear in one agent (`09:450`, `09:469`, `09:509-512`).
- `09:453` says keyboard testing "genuinely cannot be automated" — `09d` automates exactly that.
- `09:432` claims WCAG 2.2 "was defined as the compliance target in the UX design phase". It was not; 05 says 2.1 (§4.2 proves it live).
- It does not declare `accessibility` as an input, so the design spec can fall out of its context.

**`05_ux_design` — 4/10. The one that matters most.**
It is the only pre-testing agent with any concrete content: nine criterion IDs in a Step 7 table, a contrast rule (`05:448`), a per-component "Accessibility requirement — ARIA attributes, keyboard interaction, focus behavior" line (`05:475`), and — most valuable of all — it produces **real, renderable HTML per screen state**, which is a machine-checkable artifact most design tools cannot offer.
*What is wrong:*
- **Wrong standard.** WCAG 2.1 at lines 10, 15, 29, 448, 506, 548, 567 and 571.
- **Nine of 55 criteria** (1.1.1, 1.4.3, 1.4.4, 2.1.1, 2.4.3, 2.4.7, 3.3.1, 3.3.2, 4.1.2) and **none of the six new 2.2 A/AA criteria**.
- **It mandates a 1.4.10 failure**: `html, body { min-width: 1280px }` is required at `05:258`, `05:284` and `05:411`, and 375 px layouts are explicitly forbidden — while its own gate asks for 375/768/1440 breakpoints (`05:568`). Confirmed on all 80 live documents.
- **Its own template fails contrast**: the state header uses `#64748b` on `#1e3a5f` (`05:306`), about 2.4:1.
- **Loading patterns** (`05:231-238`) use pulsing skeletons and spinners with no reduced-motion guidance, no `aria-busy`, and no announcement of "Processing…"; success toasts (`05:405`) say nothing about being announced or how long they stay.
- **No developer annotations.** It has `@component`, `@data-source`, `@interaction` and `@impl-note` comment annotations (`05:345-374`) but no `@a11y` — so nothing tells the implementer what name, role, focus order or live region each element needs.
- **Its output is prose.** The `accessibility` artifact cannot be reconciled against anything (§4.2 shows the result).

**`08_code_review` — 3.5/10.**
It has an accessibility dimension (`08:7`) with a seven-item Step 11 checklist (`08:164-172`) covering alt/aria-label, contrast via tokens, keyboard, focus visible, error identification, labels ("placeholder is not a label substitute" — the only item with a severity) and name/role/value. Its findings become blocking remediation items, which is the right mechanism.
*Wrong:* WCAG 2.1 (`08:34`); only one item carries a severity; and critically, **it only runs the check when the task is `Frontend` *and* references a wireframe** (`08:166`) — so a brownfield pull request, which usually has no wireframe, receives **no accessibility review at all**.

**The rest:**

| Agent | Score | What is there | What is missing |
|---|---|---|---|
| `02_requirements` | 2 | "accessibility needs" in elicitation (`02:141`); one NFR line "WCAG 2.1 Level AA… AAA if regulated" (`02:265`) | Wrong version; no measurement method; not in the quality gate; no accessibility acceptance criteria on stories; "AAA if regulated" is bad advice — W3C does not recommend AAA as a blanket target |
| `00e_document_vision` | 2 | "WCAG 2.1 text-alternative principles" (`00e:27`); good fidelity rules for describing screenshots and wireframes (`00e:107-110`) | Version; does not capture accessibility annotations present in uploaded designs |
| `07_implementation` | 1.5 | "Preserve the DOM hierarchy… carry semantic and accessibility meaning" (`07:176`); an accessibility scan **only on the UI Modernization track** (`07:253`) | Never reads the `accessibility` artifact; no check on the normal track; nothing in its quality gate |
| `03_prd` | 1 | One example NFR row "Usability · Accessibility · WCAG 2.1 AA" (`03:250`) | It is an example, not a rule; not in the gate |
| `00_onboarding` | 1 | Lists `accessibility` as a UX artifact type (`00:140`) | Never assesses accessibility as a gap in a brownfield codebase |
| `01, 04, 06, 10, 11, 12, 00b, 00c` | **0** | Nothing at all | 04 holds the component-library and focus-management decisions; 06 holds the Definition of Done; 11 holds CI; 12 holds the release gate. These four are the costly ones |

### 5.2 The plumbing gap

05 registers an `accessibility` artifact — but **no downstream agent declares it** in `needs_artifacts` (`catalog.py`). 08 fetches "the accessibility-requirements artifact" only in prose (`08:168`). On a busy project, with many artifacts competing for the context window, it can simply be absent. The same is true of `design_system` for 07 and 09.

### 5.3 The answer to "how much can we use?"

| Layer | Reusable | Notes |
|---|---|---|
| **Machinery** (data, engines, gates, reports) | **~70% directly** | WCAG 2.2 dataset and grounding; ownership registry; contrast maths; axe runner; reflow rule; capture format; judge dispatch and caching; triage thresholds; finding ledger and auto-closing defects; derived-gate framework; project policy block; conformance statement |
| **Agent content** | **~20%** | 09c and 09d verbatim; 09b's capture contract; 09's structure once its mappings are fixed; 05's HTML-wireframe mechanism as the carrier for annotations |
| **Early-phase content** | **~0%** | It largely does not exist. *(This row also said "where it does, it teaches the wrong version" — no longer true as of `db3be69`, 2026-09-16: every agent now names WCAG 2.2. What is missing is the content itself, not the version on it.)* |

**Verdict on quality.** The testing and audit layer is genuinely strong — more honest than most commercial tools, because it reports silence instead of guessing, refuses claims it cannot support, and makes a human sign. The early-lifecycle layer scores 4/10 at best and is absent in eight agents. *(It no longer teaches the wrong standard — that was corrected on 2026-09-16.)* **The missing piece is wiring, not intelligence.** The team built the hard part.

---

## 6. Question 1 — UX Design: how far it can go, and the ten steps in full

### 6.1 All 55 criteria, and what UX Design can do about each

This is my own classification, built from the [WCAG 2.2 criteria](https://www.w3.org/TR/WCAG22/) and the [ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/), cross-checked against what our engines can actually measure. It is not a published W3C mapping — W3C does not publish one by role.

Columns: **Design decides** = the design determines whether it passes. **Checkable on the design** = one of our engines can measure it on the wireframe HTML or on the tokens. **Proven at** = where the final evidence comes from.

#### Perceivable

| SC | Level | Plain meaning | Design decides | Checkable on the design | Proven at |
|---|---|---|---|---|---|
| 1.1.1 Non-text Content | A | Images have meaningful alternatives | Yes — the intent | Partly (judge: alt intent) | 09c + human |
| 1.2.1–1.2.5 Media | A/AA | Captions, audio description, transcripts | Content decision | No | Human |
| 1.3.1 Info and Relationships | A | Visible structure exists in the markup | Yes — annotation | **Yes** (judge `structure`, axe) | 09c |
| 1.3.2 Meaningful Sequence | A | Reading order matches meaning | Yes — annotation | Partly | 09c |
| 1.3.3 Sensory Characteristics | A | Not "click the round button on the right" | **Yes** — copy | AI review of copy | Human |
| 1.3.4 Orientation | AA | Works in portrait and landscape | Yes | **Yes** (axe orientation rule) | 09b |
| 1.3.5 Identify Input Purpose | AA | Fields declare their `autocomplete` purpose | Yes — annotation | Partly (axe, thin) | 09b |
| 1.4.1 Use of Colour | A | Colour is never the only cue | **Yes** | **Yes** (judge `color`) | 09c |
| 1.4.2 Audio Control | A | Auto-playing audio can be stopped | Yes | Partly | Human |
| 1.4.3 Contrast (Minimum) | AA | Text 4.5:1, large text 3:1 | **Yes — tokens** | **Yes** (our contrast maths + axe) | Platform, at design time |
| 1.4.4 Resize Text | AA | Readable at 200% | Yes — no fixed text boxes | Partly | 09b |
| 1.4.5 Images of Text | AA | Use text, not pictures of text | **Yes** | AI review | Human |
| 1.4.10 Reflow | AA | Works at 320 px with no sideways scrolling | **Yes — layout** | **Yes** (`page_rules` at 320 px) | Platform, at design time |
| 1.4.11 Non-text Contrast | AA | Icons, borders, control edges 3:1 | **Yes — tokens** | **Yes** (rule + judge `graphics`) | Platform, at design time |
| 1.4.12 Text Spacing | AA | Survives increased spacing | Yes — no cramped boxes | Partly (axe inline-spacing) | 09b |
| 1.4.13 Content on Hover or Focus | AA | Tooltips dismissible, hoverable, persistent | **Yes — behaviour spec** | Possible via 09d hover tool | 09d |

#### Operable

| SC | Level | Plain meaning | Design decides | Checkable on the design | Proven at |
|---|---|---|---|---|---|
| 2.1.1 Keyboard | A | Everything works without a mouse | **Yes** — nothing hover-only | Partly (static check for hover-only) | 09d |
| 2.1.2 No Keyboard Trap | A | You can always tab out | Partly (modals) | No | 09d |
| 2.1.4 Character Key Shortcuts | A | Single-letter shortcuts can be turned off | Yes — if specified | No | Human |
| 2.2.1 Timing Adjustable | A | Timeouts warned and extendable | **Yes — flow** | No | Human |
| 2.2.2 Pause, Stop, Hide | A | Motion can be stopped | **Yes** | Partly | 09b / human |
| 2.3.1 Three Flashes | A | Nothing flashes dangerously | **Yes** | No | Human |
| 2.4.1 Bypass Blocks | A | Skip link or landmarks | **Yes** | **Yes** (axe + structure) | Platform, at design time |
| 2.4.2 Page Titled | A | Each page has a real title | **Yes** | **Yes** (axe) | Platform, at design time |
| 2.4.3 Focus Order | A | Tab order follows the visual order | **Yes — annotation** | Partly | 09d |
| 2.4.4 Link Purpose (in Context) | A | "Read more" is not enough | **Yes — copy** | AI review | 09c / human |
| 2.4.5 Multiple Ways | AA | More than one route to a page | **Yes — IA** | Across the sitemap | Human |
| 2.4.6 Headings and Labels | AA | Headings describe what follows | **Yes — copy** | AI review (planned checker) | 09c / human |
| 2.4.7 Focus Visible | AA | You can see where focus is | **Yes — token** | **Yes** (focus token contrast) | 09d |
| 2.4.11 Focus Not Obscured | AA | Sticky bars do not hide focus | **Yes — layout** | Partly (sticky elements flagged) | 09d |
| 2.5.1 Pointer Gestures | A | No pinch or multi-finger-only action | **Yes** | No | Human |
| 2.5.2 Pointer Cancellation | A | Action fires on release, not press | Rarely | No | Human |
| 2.5.3 Label in Name | A | The accessible name contains the visible text | **Yes — annotation** | **Yes** (judge `label`) | 09c |
| 2.5.4 Motion Actuation | A | No shake-to-undo without an alternative | Yes | No | Human |
| 2.5.7 Dragging Movements | AA | Drag has a click alternative | **Yes — interaction** | Partly (drag interactions flagged) | 09d / human |
| 2.5.8 Target Size (Minimum) | AA | Targets at least 24×24 px | **Yes — component sizes** | **Yes** (geometry from capture) | Platform, at design time |

#### Understandable and Robust

| SC | Level | Plain meaning | Design decides | Checkable on the design | Proven at |
|---|---|---|---|---|---|
| 3.1.1 Language of Page | A | `lang` is set | Template | **Yes** (axe) | Platform, at design time |
| 3.1.2 Language of Parts | AA | Foreign phrases marked | Content | Partly | 09b |
| 3.2.1 On Focus | A | Focusing something does not change the page | Yes — behaviour | No | 09d |
| 3.2.2 On Input | A | Choosing an option does not submit unexpectedly | **Yes — behaviour** | No | 09d |
| 3.2.3 Consistent Navigation | AA | Navigation in the same place everywhere | **Yes — IA** | **Yes** (compare wireframes) | Platform, at design time |
| 3.2.4 Consistent Identification | AA | The same thing is named the same way | **Yes — copy** | **Yes** (compare wireframes) | Platform, at design time |
| 3.2.6 Consistent Help | A | Help always in the same place | **Yes — IA** | **Yes** (compare wireframes) | Platform, at design time |
| 3.3.1 Error Identification | A | Errors are stated in text | **Yes — annotation** | Partly | 09c / 09d |
| 3.3.2 Labels or Instructions | A | Every field has a label | **Yes** | **Yes** (axe + judge) | Platform, at design time |
| 3.3.3 Error Suggestion | AA | Say how to fix it | **Yes — copy** | AI review | 09c / human |
| 3.3.4 Error Prevention | AA | Reversible, checked or confirmed for legal or financial actions | **Yes — flow** | No | Human |
| 3.3.7 Redundant Entry | A | Do not ask twice in one process | **Yes — flow** | Across the journey map | Human |
| 3.3.8 Accessible Authentication | AA | No cognitive test to log in; paste allowed | **Yes — with requirements and security** | Partly | 09d / human |
| 4.1.2 Name, Role, Value | A | Every control has a name and a role | **Yes — annotation** | **Yes** (judge `semantics`) | 09c |
| 4.1.3 Status Messages | AA | Updates are announced | **Yes — annotation** | Partly (live regions present) | 09d |

#### The totals

| Group | Count | Criteria |
|---|---|---|
| **A — decided in design *and* machine-checkable on the design** | **17** | 1.3.1, 1.3.4, 1.4.1, 1.4.3, 1.4.10, 1.4.11, 2.4.1, 2.4.2, 2.4.7, 2.5.3, 2.5.8, 3.1.1, 3.2.3, 3.2.4, 3.2.6, 3.3.2, 4.1.2 |
| **B — decided in design, checked by review (AI or the designer)** | **14** | 1.3.3, 1.4.5, 1.4.13, 2.1.1, 2.2.1, 2.2.2, 2.3.1, 2.4.4, 2.4.5, 2.4.6, 2.5.1, 2.5.4, 2.5.7, 3.3.4 |
| **C — design specifies, code must deliver** (the annotations) | **12** | 1.1.1, 1.3.2, 1.3.5, 2.1.2, 2.4.3, 2.4.11, 3.2.2, 3.3.1, 3.3.3, 3.3.7, 3.3.8, 4.1.3 |
| **D — only provable on built, running code** | **6** | 1.4.4, 1.4.12, 2.1.4, 2.5.2, 3.1.2, 3.2.1 |
| **E — content and media** | **6** | 1.2.1, 1.2.2, 1.2.3, 1.2.4, 1.2.5, 1.4.2 |

> **The answer, in one line.** UX Design can **determine 43 of the 55 criteria** (A + B + C). The platform can **machine-check 17 of them on the design itself**, review a further 14 with the AI judge or the designer, and hand the remaining 12 forward as **written, testable obligations**. Six can only be proven on built code, and six are content. **No criterion is left with nobody responsible.**

### 6.2 The ten steps in detail

Each step gives: **the problem** with its evidence, **what changes**, **the actual content or shape of the change**, **how it is proved**, and **what it still cannot do**.

---

#### Step U1 — Tell every agent the project's accessibility target

**The problem.** `ProjectProfile.a11y` stores the target; `_profile()` never passes it on (§3.3). So five agents say WCAG 2.1 and four say 2.2, and a client cannot ask for AAA on a criterion or set a stricter gate.

**What changes.**
1. `mcp_platform_state/tools.py`, in `_profile()` — add one key, `"a11y": policy_for(project)`, using the existing `apps/a11y/policy.py` resolver so defaults and project overrides are applied in one place.
2. `backend/manifest/composer.py:110-126` — add `a11y` to the rendered `# Project` block, so it appears in every run's `AGENTS.md`.
3. Every agent body then reads the target from the project instead of hardcoding it. The line each agent receives is short and unambiguous:
   > *Accessibility target: WCAG 2.2 Level AA. Criteria raised to AAA for this project: none. Blocking severities at the gate: Critical, High.*

**Two workarounds exist today and should not be mistaken for the answer.** `nfrs` and `important_context` are both rendered, so a target can be typed into either by hand. That is a per-project manual step nobody will remember, and it does not reach the gate logic.

**Proved by:** a unit test that `_profile()` includes `a11y` and the composer renders it, plus a test that a project set to `wcag_2.2_aaa` produces a manifest containing that target.

**Cannot do:** on its own it changes no agent's behaviour. It is what makes the other nine steps possible.

**Touches:** 2 files. No migration, no frontend. Effort: very small.

---

#### Step U2 — Rewrite 05's accessibility content to WCAG 2.2 and fix the template defects

**The problem.** Evidence in §5.1, and live in §4.2: the wrong standard in eight places, a mandated reflow failure on 80 of 80 real documents, a template header at about 2.4:1 contrast, no landmarks, no skip link, no reduced-motion handling.

**What changes, precisely.**

| Where | Today | Becomes |
|---|---|---|
| `05:10, 15, 29, 448, 506, 548, 567, 571` | "WCAG 2.1 AA (W3C, 2018)" | "WCAG 2.2 AA (W3C, 2023; current edition 2024)" — or the project's target from U1 |
| `05:258, 284, 411` | `min-width: 1280px` mandatory; 375 px forbidden | Each state document renders at **1440, 768, 375 and 320 CSS px**. The 320 px case is what 1.4.10 Reflow actually requires |
| `05:568` (quality gate) | breakpoints 375 / 768 / 1440 | unchanged — but now consistent with the template instead of contradicting it |
| `05:306` (template) | `#64748b` on `#1e3a5f`, about 2.4:1 | a pair from the token table that passes 4.5:1. The template is checked by the same engine as the product |
| `05:248-341` (template) | no landmarks | `<header>`, `<nav>`, `<main>`, `<footer>`; one `<h1>` per screen; a skip link as the first focusable element; `lang` from the project |
| `05:231-238` (loading states) | pulsing skeletons and spinners | the same patterns, plus a `prefers-reduced-motion` alternative, `aria-busy` on the region being loaded, and a live region announcing "Loading…" and "Loaded" |
| `05:405` (toasts) | success toast | announced through a live region, dismissible, and not disappearing before it can be read |

**The 75/15/10 migration rule is respected.** The *reasoning* in 05 — Double Diamond, atomic design, journey mapping, the cognitive walkthrough, the loading-state classification — is untouched. What changes is the standard it cites, the template it emits, and the data it hands on.

**Proved by:** a body-text test (no database needed) asserting that no "WCAG 2.1" remains in 05 and that the responsive rule names 320; then the live re-run check in U6, which fails if a generated state document still carries `min-width: 1280px`.

**Cannot do:** it does not make existing projects' wireframes correct. PeopleDesk's 80 documents stay as they are unless the phase is run again.

---

#### Step U3 — Design tokens with computed contrast pairs

**The problem.** `design_system` today is prose with hex values — confirmed live: PeopleDesk registered colours and a component list with no ratio anywhere. `05:448` asks the agent to "verify" contrast, an instruction with no output and no check. The research is explicit that model self-verification is the weak link (§2.6).

**What changes.** `design_system` gains a **machine-readable token block**, and the platform — not the agent — computes every ratio with `page_rules.contrast_ratio`, which already exists and needs no Django context.

Required rows: every foreground/background pair actually used; the focus ring against both the component and the page behind it; borders and control edges; icons; disabled and placeholder text; and each interactive state (hover, active, selected, error), because a state is a different pair.

```json
{ "contrast_pairs": [
    {"name": "body text",      "fg": "#1F2937", "bg": "#FFFFFF", "use": "text", "claimed": 12.6},
    {"name": "primary button", "fg": "#FFFFFF", "bg": "#0F2D5E", "use": "text", "claimed": 11.8},
    {"name": "focus ring",     "fg": "#2563EB", "bg": "#FFFFFF", "use": "ui",   "claimed": 4.2},
    {"name": "disabled label", "fg": "#9CA3AF", "bg": "#FFFFFF", "use": "text", "claimed": 2.5},
    {"name": "input border",   "fg": "#6B7280", "bg": "#FFFFFF", "use": "ui",   "claimed": 4.8}],
  "focus_indicator": {"width_px": 2, "offset_px": 2, "token": "focus ring"},
  "target_size":     {"minimum_px": 24, "recommended_px": 44},
  "motion":          {"default_ms": 200, "reduced_motion": "no transition"} }
```

The platform recomputes each `claimed` value and raises a finding where it disagrees or where the pair fails its threshold — 4.5:1 for text, 3:1 for large text and for user-interface components. In the example above, **"disabled label" at 2.5 is reported as advisory, not blocking**: disabled controls are exempt under 1.4.3. That exemption has to be in the rule, or the report cries wolf and people stop reading it.

**Why the platform recomputes instead of trusting the agent:** "Human or LLM?" found models do well on contrast *when checked* and unreliably otherwise. A claimed ratio is not evidence.

**Proved by:** unit tests over a fixture token block with known-good and known-bad pairs, including the disabled-text exemption and a semi-transparent colour, which exercises the existing `composite` path.

**Cannot do:** it cannot see a pair the design never declared, or text sitting on a photograph. Those stay with the judge and 09b.

---

#### Step U4 — `@a11y` annotations: the contract between design and code

**The problem.** 05 already has an annotation convention — `@component`, `@data-source`, `@interaction`, `@impl-note` (`05:345-374`) — and the implementation agent copies wireframe HTML wholesale (`07:172-178`). There is **no `@a11y`**, so nothing tells the developer what an element must be called, what role it plays, or what gets announced. Live evidence: **0 of 80** documents carry any such annotation, 62 of 80 have no labels, and only 4 of 80 have a live region despite the spec naming them as a key pattern.

This is the highest-leverage change in the document: semantic HTML written into a wireframe becomes semantic HTML in the product.

**What changes.** Every interactive or structural element carries an `@a11y` comment. The vocabulary follows the established annotation kits — [CVS Health](https://github.com/cvs-health/annotations) and [Indeed](https://www.figma.com/community/file/953682768192596304/a11y-annotation-kit) — and the [ARIA APG](https://www.w3.org/WAI/ARIA/apg/) for named patterns.

```html
<!-- @a11y landmark=main heading="Employee Directory" level=1 -->
<main>
  <!-- @a11y name="Search employees" role=searchbox label=visible
       autocomplete=off announce="N results" live=polite -->
  <label for="q">Search employees</label><input id="q">

  <!-- @a11y pattern=APG/combobox name="Department" keys="Up,Down,Enter,Esc"
       focus-return=trigger -->
  <div class="combobox">…</div>

  <!-- @a11y img=informative alt="Bar chart: headcount by department, 2026" -->
  <img src="…">

  <!-- @a11y img=decorative alt="" -->
  <img src="…">

  <!-- @a11y error-for=email text="Enter an email address like name@example.com"
       associated=aria-describedby focus-on-error=true -->
  <p class="error">…</p>
</main>
```

**What each key is for, and the criterion it serves:** `landmark` / `heading` / `level` → 1.3.1, 2.4.1, 2.4.6 · `name` with `label=visible` → 4.1.2, 3.3.2 and **2.5.3** (the accessible name must contain the visible words) · `pattern` + `keys` + `focus-return` → 2.1.1, 2.1.2, 2.4.3, 4.1.2 · `autocomplete` → 1.3.5 · `live` + `announce` → 4.1.3 · `img` + `alt` → 1.1.1 · `error-for` + `associated` + `focus-on-error` → 3.3.1, 3.3.3 · `obscured-by` on sticky elements → 2.4.11 · `drag-alternative` → 2.5.7 · `target` → 2.5.8.

**Every annotation carries a stable identifier** (screen plus element). That identifier is what makes the rest of the lifecycle verifiable: 06 turns it into acceptance criteria, 08 reconciles the pull request against it, 09 generates one test per obligation, and 09c/09d can report "specified but missing" rather than only "missing".

**Proved by:** a checker in U6 that fails the phase when an interactive element has no name and role, when a screen has no landmark set or no `h1`, or when a form control has no label annotation. Plus an end-to-end test that an annotated wireframe produces matching acceptance criteria in 06.

**Cannot do:** annotations are instructions, not proof. If 07 ignores them, only 08 and 09 will catch it — which is why U9 and §8 matter.

---

#### Step U5 — Flow rules for the criteria decided before a pixel is drawn

**The problem.** Six of the nine criteria new in WCAG 2.2 are flow or information-architecture decisions, and 05's journey and IA steps (`05:59-102`) say nothing about any of them. These cannot be retrofitted: an authentication flow that requires remembering a code is a product decision, not a styling bug.

**What changes — added to 05's journey mapping and IA steps, each with a required output.**

| Criterion | The rule the agent applies | What it must produce |
|---|---|---|
| **3.2.6 Consistent Help** | If the product offers help, contact or chat, it sits in the same relative position on every screen that has it | One IA decision, repeated in every wireframe — checkable by comparing screens |
| **3.3.7 Redundant Entry** | Nothing is asked twice within one process, unless it is deliberate re-confirmation such as a password | The journey map lists each data item and where it is captured; a second request must be pre-filled or selectable |
| **3.3.8 Accessible Authentication** | No memory test, no puzzle, no transcription test. Paste allowed in every field. Password managers work. Any CAPTCHA has an alternative | A short authentication decision in the spec, raised with 04 and 10 (§7, §8) |
| **3.3.4 Error Prevention** | For legal, financial or data-deleting submissions: reversible, checked, or confirmed | A confirm or review step designed into the flow |
| **2.2.1 Timing Adjustable** | Any timeout is warned before it expires and can be extended | The warning dialog, drawn in the wireframes |
| **2.2.2 Pause, Stop, Hide** | Anything that moves, scrolls or auto-updates has a control to stop it | That control, drawn in the wireframes |
| **2.3.1 Three Flashes** | Nothing flashes more than three times a second | A stated constraint on any animation spec |
| **2.4.5 Multiple Ways** | More than one route to each page — for example navigation and search | Recorded once, in the sitemap |
| **1.3.3 Sensory Characteristics** | Instructions never depend only on shape, position or colour | A copy rule applied across the screens |

**Proved by:** these already appear as questions on the UX gate (`wcag.py` asks 3.2.6, 3.3.7 and 3.3.8 among its 22) — but now with the design's own evidence attached: the journey map's data table for 3.3.7, the authentication decision for 3.3.8, the sitemap for 2.4.5.

**Cannot do:** most of this group cannot be machine-verified on a design. That is expected. The value is that the decision is made, written down and reviewable, instead of being discovered during testing.

---

#### Step U6 — Machine-check every screen before the gate

**The problem.** Nothing checks a design today. The gate asks a person to confirm things they cannot see — §4.2 shows a reviewer ticking "focus visible" and "labels" on screens that had neither.

**What changes.** When 05 finishes, **the platform** — not the agent, since this is control-plane work — runs six checks over every wireframe state document.

| # | Check | Engine | Criteria it answers |
|---|---|---|---|
| 1 | axe-core at 1440, 768, 375 and 320 px | existing companion runner `a11y_audit.mjs` | 1.3.1 markup faults, 2.4.1, 2.4.2, 3.1.1, 3.3.2, 1.3.4, part of 1.4.3 and 1.4.12 |
| 2 | Reflow at 320×256 | `page_rules` | 1.4.10 |
| 3 | Target geometry | the `box` field already in the capture format (`09b:505`) | 2.5.8 |
| 4 | Token contrast recomputation | `page_rules.contrast_ratio` (U3) | 1.4.3, 1.4.11, and the focus ring for 2.4.7 |
| 5 | The 09c judge on captured elements | existing judge | 1.1.1, 1.3.1, 1.4.1, 2.5.3, 4.1.2 |
| 6 | Annotation completeness | new, small | the structural rules from U4 |

Two judge checks are deliberately excluded at design time: **2.4.6** heading quality (the copy is still placeholder at this stage) and design-time **2.5.8** (covered mechanically at check 3). This exclusion is the team's own earlier decision, recorded as correction R16 in the accessibility docs.

**Where the results go.** Findings are written to the existing `A11yFinding` ledger with a **new source value `design`**, so everything already built works unchanged: severity from the WCAG level (A → Critical, AA → High), deduplication by fingerprint, the review queue for uncertain answers, and automatic closing when a later run shows the problem gone.

**The one genuinely new piece.** Nothing has ever pointed the runner at a stored wireframe instead of a live application. It should work — the script needs only a URL and a route list, and the accessibility docs already established a capture route for localhost previews — but **it is unproven, and it should be the first thing spiked** before the team commits to the rest of this step.

**Proved by:** run it against PeopleDesk's existing 22 wireframes. From §4.2 the expected result is reflow failures on every screen, missing labels on most, and no skip link anywhere. If the check reports exactly that, it works.

**Cannot do:** it cannot judge behaviour. Nothing in a wireframe is clickable, so keyboard traps, focus order in practice and status announcements stay with 09d.

---

#### Step U7 — Let the agent repair what the checker found

**The problem.** A check that only produces a list moves the work to a human. The research (§2.6) shows the repair loop is where the gain is.

**What changes.** The findings from U6 go back to 05 in structured form; it revises the affected screens; the check runs again. Capped at **N rounds — recommend 2** — after which whatever remains is surfaced to the designer with its evidence. Every round is recorded, so nobody can mistake "repaired on the second attempt" for "right first time".

Each returned finding carries: the criterion, the screen, the element selector, what is wrong, and what the standard requires — using the grounding text the platform already holds.

**Two ways to run it, for the team to choose (§11):**
- **(a) Inside the same 05 run** — faster, no extra gate traffic, and the designer sees only the finished result.
- **(b) As a "request changes" re-run** — slower, but every round is visible in the run history and a person can step in.

**Proved by:** a test with a wireframe containing a known fault — an unlabelled input — asserting the loop produces a labelled input, and that a second, unfixable fault is surfaced rather than quietly dropped.

**Cannot do:** it cannot fix what it cannot see, such as a contrast problem inside an image, or a flow decision from U5.

---

#### Step U8 — A computed condition on the UX gate

**The problem.** §4.2: nine of nine conditions ticked on a design that failed several of them. The checklist is good content asked of someone with no way to answer it.

**What changes.**
1. A new module `backend/apps/gates/designa11ygate.py`, mirroring `a11ygate.py` almost exactly: one **derived** condition `no_blocking_design_a11y_findings` on the `ux_design` phase, with an evaluator registered in `conditions._DERIVED_EVALUATORS`. Derived means the platform computes it and **a reviewer cannot tick past it** — the same protection the testing gate already has.
2. The 22 attested questions stay, but each now shows the machine evidence beside it. Where an engine answered the question, the answer is shown and the reviewer confirms rather than guesses. Where no engine can answer — most of U5's flow rules — the question is asked exactly as it is today, which is correct.
3. The blocking threshold comes from `ProjectProfile.a11y.gate`, defaulting to confirmed Level A and AA failures. Uncertain judgments never block; they go to the review queue, as they already do at the testing gate.
4. `wcag.py:274-293` records why certain criteria are "not asked". Several of those reasons are out of date — 1.4.10, 2.1.2, 3.2.1, 3.2.2 and 4.1.3 became checkable when the reflow rule and 09d were built. They are corrected in the same change.

**A safeguard that already exists and must be respected.** Conditions are seeded when a gate is created, so a gate opened before this ships would carry none. The platform already tops up missing **derived** conditions at decision time and deliberately does not top up attested ones — a reviewer must never be credited with a checklist they were never shown. The same rule applies here.

**Proved by:** tests that a reviewer's attempt to tick the derived condition is refused; that a project with an empty blocking list can still approve with findings open; and that a UX gate opened before the change gains the condition at decision time.

**Cannot do:** it cannot stop a determined team — the policy allows an empty blocking list, by design. The gate makes the position explicit; it does not take away the team's authority.

**This step changes the gate screen, so it needs mockups and approval before any UI work** (rule 11).

---

#### Step U9 — Make the hand-off binding

**The problem.** §5.2: the `accessibility` artifact is declared as an input by nobody, and its content is prose that nothing can be measured against.

**What changes.**
1. `catalog.py` — add `accessibility` and `design_system` to `needs_artifacts` for **06, 07, 08 and 09**. The catalog's own comments (lines 105-112) already describe this failure mode for 09.
2. The `accessibility` artifact changes shape. Instead of five generic patterns it carries **per-criterion, per-screen decisions** with the annotation identifiers from U4, the token table from U3, and the flow decisions from U5. It becomes the thing 09 generates tests from and 08 reviews against.
3. `08:168`'s vague "the accessibility-requirements artifact" is replaced by the declared input.

**Proved by:** a test that a run manifest for 06, 07, 08 and 09 contains the `accessibility` artifact, and an end-to-end check that an annotation identifier appears in a generated test case.

---

#### Step U10 — The connected-design-tool path (Figma)

**The problem.** In read-as-source-of-truth mode (`05:51`) the client's Figma file is the source and **05 authors no HTML**, so there is nothing for U6 to scan. This is common for brownfield clients and design-led teams.

**What changes.**
- **U3 still applies.** Tokens come from `designsource.get_variable_defs()`, and the contrast recomputation works on imported tokens exactly as on authored ones.
- **U4 and U5 become a reviewed annotation artifact** rather than HTML comments — same vocabulary, same identifiers, registered as `accessibility`, so the rest of the chain is unchanged.
- **The judge can run on exported frame images** for the visual checks: colour-only meaning, images of text, contrast in context.
- **Writing annotations back into Figma is out of scope.** The platform's export policy defers writes to a system of record, and this feature is not the place to reopen that.

**Recommendation:** build the HTML path first — it covers greenfield and most brownfield new work — and treat Figma as a follow-on, since it serves a smaller population and gives a weaker check.

### 6.3 What UX Design still cannot do, stated plainly

Even with all ten steps in place:
- **Screen-reader announcement quality** — whether a name makes sense when heard — needs a person.
- **Real keyboard behaviour** of built widgets: 09d, on the running product.
- **Runtime focus management** on route changes in a single-page app: 09d.
- **Text resize and spacing** (1.4.4, 1.4.12): 09b, on real CSS.
- **Media and content quality** (1.2.x, 1.4.5, and the wording behind 2.4.4): human.
- **Conformance itself** (§2.3): only after build, test and signature.

So the honest claim at the end of UX Design is: *"Designed to WCAG 2.2 AA intent. Seventeen criteria machine-verified on the designs, twelve more specified as build obligations, the rest scheduled for verification in testing."* That is specific, defensible and true.

---

## 7. Question 2 — the phases before UX Design

A phase belongs on this list only if UX Design does its job worse without it. Each entry below states the problem today, exactly what the agent gains, and what would go wrong if we skipped it.

### 7.1 Project setup — **truly needed**

**Today.** The policy block exists but reaches nobody (§3.3). There is also no settings screen: the accessibility docs record that the toggle "belongs on a settings screen" and that none was ever built, so a project's accessibility policy can currently only be changed in the database.

**What it gains.**
- A project-level accessibility policy: target (2.2 AA by default), any criteria raised to AAA, the legal driver (EAA, ADA Title II, Section 508, none), the assistive-technology and browser matrix to test against, blocking severities, and whether inherited brownfield debt blocks.
- That policy delivered to every agent (U1) and read by every gate.
- A place in the UI for a person to set it. **This is frontend work and needs mockups first.**

**If skipped:** every agent keeps guessing, the platform keeps contradicting itself, and a client with an AAA requirement or a strict legal deadline cannot express it.

### 7.2 01 Ideation — **only when a duty or the audience requires it** (see §14.5)

**Today.** Nothing. The stakeholder map (`01:131-138`) never names disabled users; business viability never mentions accessibility law.

**What it gains.**
1. **One question, always asked: does an accessibility duty apply to this product, and in which markets?** That answer sets the standard, the deadline and how strict every later gate is.
2. **Disabled people named as stakeholders — but only where the law requires it or the product's audience plainly includes them** (the team's correction, §14.5), by the barriers that matter to this product, not as a generic "accessibility" line. For a payments product that is screen-reader users completing a transfer; for a scheduling product it is keyboard-only and low-vision users.
2. **The legal driver, decided once**: which markets, and therefore which standard and deadline (§2.5).
3. **Accessibility in the business case** where it belongs: market reach, procurement (public-sector buyers ask for a VPAT), and the cost asymmetry — fixing at design is far cheaper than after release.

**If skipped:** accessibility arrives as a technical constraint rather than a product goal, and nobody knows whether it is legally required, which changes how strict every later gate should be.

### 7.3 02 Requirements — **truly needed**

**Today.** Two lines: "accessibility needs" in elicitation (`02:141`) and "WCAG 2.1 Level AA (minimum for public-facing products); AAA if regulated" (`02:265`). Wrong version, and the AAA advice is wrong — W3C does not recommend AAA as a blanket target, because some AAA criteria cannot be met for some content.

**What it gains.**
1. **An `NFR-A11Y` block** with the shape every other NFR has, so it can be traced by 04 and tested by 09:
   > *NFR-A11Y-1 — The product conforms to WCAG 2.2 Level AA for all user-facing pages and complete processes. Verified by: axe scan with zero blocking violations, AI judgment pass on captured elements, keyboard journey pass on every critical journey, and human confirmation of the criteria no engine can decide. Assistive technology matrix: NVDA + Chrome, VoiceOver + Safari, keyboard only. Driver: European Accessibility Act.*
2. **Personas that include disabled users**, carried into 05's journey mapping.
3. **An accessibility acceptance criterion on every user-facing story.** Example, on "Employee searches the directory":
   > *Given I am using only a keyboard, when I tab to the search field and type, then the result count is announced, and I can reach every result and open one without a mouse.*
   These become 06's tasks and 09's tests.
4. **The three cognitive criteria stated as requirements, not visuals**: 3.3.7 Redundant Entry, 3.3.8 Accessible Authentication, 3.2.6 Consistent Help. They constrain the product, so they belong here.
5. **A quality-gate line**, which does not exist today.

**If skipped:** UX designs to taste, 09 has nothing to trace tests to, and 3.3.7 / 3.3.8 surface during testing, by which point the flow is built.

### 7.4 03 PRD — **truly needed**

**Today.** One example NFR row (`03:250`), still on 2.1.

**What it gains.**
1. **An accessibility acceptance criterion inside each feature's template** (`03:266-269`). This matters mechanically: 03's per-feature acceptance criteria are copied into 06's tasks and verified by 08 (`03:34-37`), so a criterion written here is automatically enforced twice downstream.
2. **The usability risk row citing accessibility evidence** (`03:104`) rather than mentioning standards in passing.
3. **A gate line.**

**If skipped:** the requirement exists at product level but never reaches a single feature, which is exactly the state PeopleDesk is in.

### 7.5 04 Architecture — **truly needed**

**Today.** Nothing at all.

**What it gains** — four decisions, each an ADR:
1. **Component strategy — see §14.6 for the corrected, fuller wording.** This is not a call to abandon React, Angular, MUI or Tailwind. Prefer components that **render real HTML elements** in whatever framework the project uses (a React button should be a `<button>`), choose one component library and record the choice with its accessibility documentation, and where the library has no suitable component, build it to a named [ARIA APG](https://www.w3.org/WAI/ARIA/apg/) pattern and say which pattern in the design annotation. The APG's own rule is blunt: *"No ARIA is better than bad ARIA"*, and a role is a promise — if you claim it, you must build its keyboard behaviour. [WebAIM's Million 2026](https://webaim.org/projects/million/) found pages using ARIA averaged **59.1 errors against 42** for pages without it.
2. **Focus management for a single-page app.** On route change, focus moves to the new page's heading, the page title updates, and the change is announced. Without a decision here, every screen invents its own and 2.4.3 fails at runtime.
3. **A status-announcement service** — one live region owned by the app shell — so 4.1.3 is implemented once rather than per component.
4. **Language and internationalisation** — `lang` on the document, and marking parts in other languages (3.1.1, 3.1.2); right-to-left support if in scope.
5. **Accessible authentication** (3.3.8), decided jointly with `security_architecture`: what protects the login, whether a CAPTCHA exists, whether paste and password managers work.
6. **Test tooling in `tech_stack`** — axe and Playwright. This decides early the problem 09b hits late: its accessibility scan only exists for Playwright, and a Python-only stack gets capture without a scan (`09b:416-418`).

**If skipped:** UX annotations name patterns the build cannot deliver, focus management is reinvented per screen, and the 3.3.8 decision lands during testing when changing it is expensive.

### 7.6 Why not simply start at UX Design?

Two concrete failures if we did:
- 05 annotates a combobox as `pattern=APG/combobox`, but 04 chose a component library with no accessible combobox. The annotation is unbuildable, and the problem surfaces in 07 or 08.
- 05 designs a login that allows paste and password managers, but requirements never said so and security later adds a puzzle CAPTCHA. 3.3.8 fails, and the fix is a product change, not a design tweak.

---

## 8. Every phase after UX Design

### 8.1 06 Task Breakdown

**Today:** nothing; no accessibility item in the Definition of Done (`06:299-311`).
**Gains:**
- A DoD item: *"No blocking accessibility findings on the screens this task touches, and every `@a11y` annotation on the linked wireframe is implemented."* The DoD is registered as its own artifact and read by 07 and 08, so one line propagates to both.
- An accessibility acceptance criterion on every Frontend task, generated from U4's annotation identifiers — so the task says what it must do, not "be accessible".
- `accessibility` and `design_system` declared as inputs.

### 8.2 07 Implementation

**Today:** one semantic hint (`07:176`) and a scan only on the UI Modernization track (`07:253`). It never reads the accessibility artifact.
**Gains:**
- It reads the spec and the annotations, and implements them.
- **It runs a real checker on the routes it touched and repairs before opening the pull request** — axe through the existing companion runner, plus `eslint-plugin-jsx-a11y` where the stack is React. On every track, not just UI Modernization. This is the FeedA11y loop from §2.6, applied to the coding agent, and it is where most of the measured benefit in the research comes from.
- A quality-gate line.

**Tooling choice for the team (§11):** our own companion runner needs no new dependency and is already pinned and reviewed. [Deque's axe MCP server](https://www.deque.com/axe/mcp-server/) is the commercial alternative, ships with Axe DevTools, and Deque claims 20–30% fewer remediation hours — a vendor figure, unverified by us.

### 8.3 08 Code Review

**Today:** a seven-item checklist (`08:164-172`) that only runs when the task is Frontend **and** references a wireframe (`08:166`).
**Gains:**
- **It runs on every frontend diff.** The current condition means brownfield pull requests — which usually have no wireframe — get no accessibility review at all. That is the single biggest gap on the build side.
- WCAG 2.2, with the new criteria added: target sizes (2.5.8), sticky elements against focus (2.4.11), authentication code (3.3.8), redundant entry (3.3.7).
- A severity on every item, taken from the WCAG level, instead of one item carrying "(Critical)" and the rest carrying nothing.
- Reconciliation against the annotations: *specified name and role vs what the diff actually implements.*
- Optionally, capture-and-judge on the pull request preview. This was already planned by the team as OP-04 and OP-05 and never built.

### 8.4 The merge gate

Today it carries no accessibility condition, and `a11ygate.py:63-65` says so deliberately: whether it should was left as a product decision. **Recommendation:** carry it, but only for **new** confirmed Level A and AA failures, so inherited debt on a brownfield project never blocks an unrelated merge. This is a decision for §11.

### 8.5 09 Testing

**Gains:** the corrections listed in §5.1 — axe impact is not a WCAG level; one severity scheme, matching the platform policy; use 09d for keyboard rather than declaring it impossible; drop the false claim about the UX phase; declare `accessibility` as an input; and generate one test per annotation obligation so "specified but never tested" becomes visible.

### 8.6 09b, 09c, 09d

- **09b:** scan at 320 px and at 200% zoom as well as at full size; capture target-size boxes (the field already exists); extend beyond Playwright if a project's stack needs it; fix the two stale numbers.
- **09c:** add checkers for 2.4.6 (headings and labels describe what follows) and 3.3.1 / 3.3.3 (error text identifies the problem and suggests a fix). Add the missing required-field rows for `structure` and `graphics`.
- **09d:** it already has resize and hover tools — use them for 1.4.10, 1.4.13, 2.5.7 and 2.5.8; add 3.3.7 and 3.3.8 checks on authentication journeys; and let it read the design's annotations so it can report a missing obligation, not just an observed failure.

### 8.7 10 Security

**Gains:** a joint finding with accessibility whenever authentication uses a CAPTCHA, a memory test or a code the user must transcribe (3.3.8), and a flag when a session timeout has no warning (2.2.1). Security and accessibility genuinely collide here, and today neither agent raises it.

### 8.8 11 CI/CD

**Today:** nothing; the repository has no CI at all, and the platform's capture endpoint accepts a CI token but has no caller.
**Gains:** an accessibility stage in the generated pipeline that runs 09b's accessibility specs against the preview or Storybook build, using the same policy threshold as the gate, plus a nightly run on the main branch. Where there is no preview environment, the stage says so rather than passing silently.

### 8.9 12 Deployment

**Gains:**
- A readiness line: *"No open blocking accessibility defects; the conformance statement is signed and current."* The readiness gate already exists and is attested, so this is one more checklist item with evidence behind it.
- Accessibility changes in the release notes.
- The accessibility statement or ACR published as a release deliverable. The platform's conformance module already produces the 55-row statement with VPAT wording and a human signature; [VPAT 2.5 INT](https://www.itic.org/policy/accessibility/vpat) is the right edition when a client sells into both the US and the EU.

### 8.10 Maintenance

A scheduled re-audit on a [WCAG-EM 2.0](https://www.w3.org/TR/WCAG-EM/) sample, and the signed statement going stale when new evidence arrives — the staleness mechanism is already built.

---

## 9. Question 4 — greenfield and brownfield, explained from the beginning

The team asked for this section in plainer words, so it starts from first principles. Nothing here assumes you have read §6 or §8.

### 9.1 What the two words mean in our platform

- **Greenfield** = a brand-new product. Nothing exists yet: no code, no screens, no users. The platform takes it from an idea through requirements, design, build and testing.
- **Brownfield** = a product that already exists and is running. The client already has screens, code and users, and comes to us to keep building it, to fix it, or both.

In the code these are just a label on the project — `Project.track`, set once when the project is created and changeable later on the project profile.

### 9.2 The single most important fact

**The phases are identical for both.** The platform defines one set of 19 agents, and **nothing anywhere decides which phases run based on whether a project is greenfield or brownfield**. I checked this specifically, because an older document claims brownfield has no design phase — it does.

What brownfield adds is a beginning: an onboarding stretch where the platform learns what already exists. After that, both tracks run the same 01 → 12 lifecycle.

**Why this matters for accessibility:** everything proposed in §6, §7 and §8 — the target reaching every agent, the accessibility requirement, the architecture decisions, the design annotations, the checks at design time, the build-side checking, the gates, the conformance report — **applies to both tracks without change.** There is no second solution to build. What differs is the starting condition, and that needs three specific additions.

### 9.3 Brownfield case 1 — new screens on an existing application

This is a client who says: *"our app is live; build us the new billing section."*

**What is different:** the new screens must fit an app that already exists, with its own patterns, components, colours and problems. So the platform has to learn the app first — that is what onboarding is for.

**What we add, in order:**

1. **Learn the accessibility posture during onboarding.** The code-reading agent (00c) already examines the codebase. It should record five things it can already see: is an accessibility testing tool present (axe, jsx-a11y, Pa11y); which component library is in use; does an accessibility statement or VPAT exist; do pages set a language; are landmarks used. *Why:* these tell us whether the new work is being added to a healthy or unhealthy base, which changes how strict the gate should be.
2. **Rate accessibility in the gap report.** The onboarding agent produces a report of what is missing. A brownfield project whose design phase is judged complete but which has **no accessibility specification** should be flagged as a gap — that is precisely the condition that produces inaccessible new work.
3. **Register the app's pages automatically.** The audit needs a list of pages. Today somebody types them in by hand. The model already has a field meaning "this page came from onboarding" — and **nothing has ever written to it**. Route discovery from the code, confirmed by a person, should fill it.
4. **Then build the new screens through the normal flow** — the whole of §6 applies, unchanged.
5. **Code review matters more here than anywhere else.** Our code-review agent only performs its accessibility check when a task is a frontend task **and** names a wireframe. Brownfield work frequently has no wireframe, so **most brownfield pull requests get no accessibility review at all today.** Fixing that single condition is the highest-value change on the build side for these clients.
6. **The honesty rule — the part clients most often get wrong.** A new, perfectly accessible screen sitting inside an old, broken checkout flow **cannot be called conformant**, because the standard is judged over *complete processes*, not single pages. So the conformance report has to say which processes it covers. Our platform already supports this correctly: the testing gate can separate new failures from inherited problems, and by default inherited problems do not block new work.

### 9.4 Brownfield case 2 — bringing the existing screens up to standard

This is a client who says: *"our app is live and it is not accessible; fix it."* This is what the platform already does best, and it has been proven at scale.

**How it works today, and it is genuinely built:**

1. **Someone registers the pages** and starts an audit.
2. **The companion opens each page in a real browser**, runs the scanner, measures things the scanner cannot (how the page behaves at 320 px, the contrast of control edges), and photographs each page.
3. **The AI judge answers the questions a scanner cannot** — is this alt text meaningful, is this colour the only cue, does this look like a table but is not one.
4. **Uncertain answers go to a person**, never guessed.
5. **The result is a prioritised backlog** — ordered by severity, then by how many pages are affected — and an "Accessibility backlog" epic in the project.

Proven on 2 September: **94 pages, 1,068 questions asked, 968 passes, 100 failures, 410 open problems.** The wcag2 tenant still holds that run.

**What we add:**

1. **Reverse the design step.** For each existing screen being remediated, the design agent produces an **as-is** description from what the audit already captured (it holds each element's accessible name, role, styles and position) and then a **to-be** specification. *Why:* this gives an old screen the same clear contract a new screen gets, which is what lets the build phases act on it precisely instead of guessing.
2. **Fix the design system before the pages.** One colour pair or one shared component usually clears dozens of findings at once. The evidence for this is external and strong: across a million home pages, low contrast affects 83.9% and missing form labels 51% — these are shared-component problems far more often than per-page ones.
3. **Then the normal loop** — tasks, build, review, test — per epic. Findings close by themselves when a later run shows the problem gone. That is already built.
4. **Report two numbers, never one:** inherited debt, and new work. Added together they hide whether things are getting better. A remediation programme runs for months, and this is what keeps the reporting honest.

### 9.5 Where the brownfield audit currently cannot look

This is the answer to the team's own finding about logged-in pages, and it belongs here too, because it changes what a brownfield client can be promised. The full list and the fixes are in §14.1. In short:

- **It cannot log in.** The browser is opened with no session and no credentials, and nothing in the platform can supply them. Every page behind a sign-in is recorded as unreachable.
- **It only sees each page as it first loads.** No clicking, no typing, no hovering, no scrolling. So modals, wizard steps, hover menus, and anything an infinite-scroll list has not yet fetched are invisible.
- **It only sees the outer page.** Content inside an iframe, or inside a web component's shadow DOM, is not judged.
- **It only sees desktop width.**
- **A cookie banner is captured along with every page**, because nothing dismisses it.

**None of this is dishonest — that is the important part.** Unreachable pages are recorded as unreachable and excluded from the coverage figures, so nothing is ever reported as clean because we could not look at it. But it does mean that today, for a typical logged-in product, **the audit covers the public pages and the sign-in screen, and little else.** For most business applications that is the smaller half of the product.

**The single change that unlocks the most:** let the keyboard-journey agent, which already logs in and clicks through the app, **save what it sees** as ordinary captured screens. That one change reaches logged-in pages, modals, wizard steps and hover-revealed content at once, and it feeds the judge, the crops and the report that already exist.

### 9.6 The two tracks side by side

| | Greenfield | Brownfield |
|---|---|---|
| Phases 01–12 | Same | Same |
| Accessibility target | From the project profile | From the project profile |
| Before the lifecycle starts | Nothing | Onboarding: read the code, adopt the documents, rate the gaps, register the pages |
| Design phase | Designs new screens | Designs new screens **and** writes as-is/to-be specs for screens being remediated |
| Starting position | Clean — nothing exists to be wrong | A measured baseline of existing problems |
| Code review | A wireframe usually exists | Often no wireframe — so today, no accessibility review. Must be fixed |
| Audit of the running app | Only after something is built | The first thing that happens |
| What can be claimed at the end | The product conforms, for the pages and processes tested | The processes actually remediated conform; the rest is listed as known debt |

---

## 10. Build order, task by task

Each wave is independently useful. Waves W0 and W1 are the cheapest and unblock everything else.

| ID | Task | Files | Tests | Frontend? | Size |
|---|---|---|---|---|---|
| **W0-1** | Accessibility target reaches every agent (U1) | `mcp_platform_state/tools.py`, `backend/manifest/composer.py` | profile + manifest tests | No | XS |
| **W0-2** | Correct the stale ownership registry and the out-of-date "not asked" reasons | `apps/a11y/data/ownership.json`, `ownership.py`, `gates/wcag.py` | registry consistency test | No | S |
| **W0-3** | One severity scheme everywhere; remove axe-impact-as-WCAG-level | `agents/09_testing/agent.md` | body-text test | No | S |
| **W0-4** | Declare `accessibility` + `design_system` as inputs for 06, 07, 08, 09 (U9) | `apps/registry/catalog.py` | manifest test | No | XS |
| **W0-5** | Fix stale counts in 09b and the missing judge field rows in 09c | two agent bodies | body-text tests | No | XS |
| **W1-1** | 02 Requirements: NFR-A11Y, personas, story criteria, gate line (§7.3) | `agents/02_requirements/agent.md` | body-text test | No | S |
| **W1-2** | 03 PRD: per-feature criterion, risk row, gate line (§7.4) | `agents/03_prd/agent.md` | body-text test | No | S |
| **W1-3** | 04 Architecture: the six decisions (§7.5) | `agents/04_architecture/agent.md` | body-text test | No | M |
| **W1-4** | 01 Ideation: stakeholders and legal driver (§7.2) | `agents/01_ideation/agent.md` | body-text test | No | XS |
| **W2-1** | 05: WCAG 2.2, responsive template, landmarks, skip link, motion (U2) | `agents/05_ux_design/agent.md` | body-text test | No | M |
| **W2-2** | 05: token contrast block (U3) | same + `apps/a11y` validator | contrast unit tests | No | M |
| **W2-3** | 05: `@a11y` annotations (U4) | same | annotation parser tests | No | M |
| **W2-4** | 05: flow rules for the 2.2 cognitive criteria (U5) | same | body-text test | No | S |
| **W3-0** | **Spike:** point the existing runner at a stored wireframe and scan it | none (throwaway) | manual | No | S |
| **W3-1** | Design-time check pipeline, `source=design` findings (U6) | `apps/a11y/` new module, migration for the source value | integration tests against PeopleDesk's 22 wireframes | No | L |
| **W3-2** | Repair loop (U7) | orchestration | loop tests | No | M |
| **W3-3** | Derived condition on the UX gate (U8) | `apps/gates/designa11ygate.py`, `conditions.py` | gate tests | **Yes — gate screen** | M |
| **W3-4** | Accessibility settings on the project profile (§7.1) | frontend + API | component tests | **Yes** | M |
| **W4-1** | 06 DoD and task criteria (§8.1) | `agents/06_task_breakdown/agent.md` | body-text test | No | S |
| **W4-2** | 07 check-and-repair before the pull request (§8.2) | `agents/07_implementation/agent.md` | body + build tests | No | M |
| **W4-3** | 08 on every frontend diff, 2.2, severities, reconciliation (§8.3) | `agents/08_code_review/agent.md` | body-text test | No | M |
| **W4-4** | Merge-gate decision, if the team says yes | `apps/gates/a11ygate.py` | gate tests | Maybe | S |
| **W5-1** | 09 corrections (§8.5) | `agents/09_testing/agent.md` | body-text test | No | S |
| **W5-2** | 09c new checkers; 09d new criteria (§8.6) | two agent bodies + `types.py` | judge tests | No | L |
| **W5-3** | 11 CI accessibility stage (§8.8) | `agents/11_cicd/agent.md` | body-text test | No | S |
| **W5-4** | 12 readiness line and statement as a deliverable (§8.9) | `agents/12_deployment/agent.md`, `readiness.py` | gate tests | Maybe | S |
| **W6-1** | 00c posture, 00 gap rating, 00e to 2.2 (§9.1) | three agent bodies | body-text tests | No | M |
| **W6-2** | Onboarding route registration (§9.1) | `integrations/onboarding.py`, `apps/a11y/routes.py` | route tests | Maybe | M |
| **W6-3** | As-is / to-be remediation design (§9.2) | `agents/05_ux_design/agent.md` | integration test | No | L |

**Sequence.** W0 first — it is small and everything depends on it. W1 and W2 can run in parallel (different agent bodies, no shared files). **W3-0 is a gate on W3**: if the runner cannot scan a stored wireframe, the whole design-time check needs rethinking, and it is better to find that out in a day than after W2. W4 needs W2's annotations. W5 and W6 are independent of each other.

**Testing rules that apply throughout** (from the project's standing practice): run only the test files touched by the change, never the full backend suite; body-text and pure-function tests need no database; frontend tests run under Vitest with their own cleanup.

---

## 11. The decisions the team has to make

| # | Decision | Options | My recommendation |
|---|---|---|---|
| 1 | **UX gate strictness** | (a) block on machine-confirmed Level A and AA failures · (b) block on Level A only · (c) advisory for the first release | **(a)**, with the policy switch available per project. The live PeopleDesk gate is the argument: advisory is what we effectively have now |
| 2 | **Where the repair loop runs** | (a) inside the same 05 run · (b) a "request changes" re-run | **(a)** with 2 rounds, and every round recorded |
| 3 | **Wireframe widths** | (a) render 1440/768/375/320 · (b) keep desktop-only | **(a)** — (b) makes 1.4.10 unachievable and contradicts 05's own gate |
| 4 | **Merge gate** | (a) carry new Level A and AA failures · (b) leave testing as the only accessibility gate | **(a)**, new failures only |
| 5 | **Checker for 07** | (a) our companion axe runner · (b) Deque axe MCP server | **(a)** — no new dependency, already pinned and reviewed. Revisit (b) only if a client asks for Deque |
| 6 | **Figma path (U10)** | (a) now · (b) after the HTML path | **(b)** |
| 7 | **Accessibility settings screen** | (a) build in W3 · (b) defer, database-only for now | **(a)** — without it the policy is unusable by the client, and it needs mockups first |
| 8 | **AAA** | (a) per-criterion opt-in only · (b) not supported | **(a)** — the profile already has room for it, and some clients ask for 2.4.13 or 3.3.9 specifically |
| 9 | **Client wording** | The stage-by-stage claims in §2.3 | Adopt them verbatim, and never say "guaranteed compliant" |
| 10 | **Old projects** | (a) re-run 05 on PeopleDesk and others · (b) leave them, apply to new work only | Team's call — (a) is honest but will regenerate 22 screens' worth of design |

---

## 12. Docs and code found out of date — **closed on 2026-09-16**

Everything in this table has now been corrected, except the three rows the team deliberately deferred to the build. The full record of what changed and why is in [`CORRECTIONS_2026-09-16.md`](CORRECTIONS_2026-09-16.md); this table is the index.

| Where | Was | Status |
|---|---|---|
| `agents/05_ux_design/agent.md` ×8 lines | WCAG 2.1 AA | **Fixed** — 2.2, with the limitation recorded (its Step 7 table still covers 9 criteria) |
| `agents/08_code_review:34`, `03_prd:250`, `02_requirements:265`, `00e_document_vision:27` | WCAG 2.1 | **Fixed** — 2.2 |
| `docs/DESIGN_SYSTEM.md:148`, `docs/SCREEN_PROMPT_TEMPLATE.md:40` | our own product's design rules at 2.1 | **Fixed** — 2.2; the target-size line now also states the standard's own 24×24 minimum (2.5.8) |
| `backend/tests/test_wcag22_design_checklist.py`, `test_design_test_agents_migration.py` | two tests pinned 05 at WCAG 2.1 | **Fixed** — they now pin 2.2 and still fail if anyone reverts it. A third test, which forbade the bare string "2.1", was tightened: it could not tell the standard's version from criterion numbers 2.1.1 and 2.1.2 |
| `agents/09_testing:437-438` | axe "Critical"/"Serious" presented as WCAG Levels A/AA | **Fixed** — impact words are not levels; the level comes from the criterion |
| `agents/09_testing` (three places) | three conflicting severity schemes | **Fixed** — one scheme: A → Critical, AA → High, AAA → Medium |
| `agents/09_testing:453` | keyboard testing "cannot be automated" | **Fixed** — points at 09d and names the eight criteria it checks |
| `agents/09_testing:432` | "2.2 was defined as the target in the UX design phase" | **Fixed** — and, after the 05 uplift, now true as well |
| `agents/09_testing:473` | the judge answers "four questions" | **Fixed** — six, and all six are named |
| `agents/09b:603`, `:649` | wrong step reference; "all six style keys" (there are 11) | **Fixed** — Step 5b, and it now refers to the list the agent is given rather than a number that drifts |
| `agents/09c_a11y_judge` | no required-evidence rows for `structure` or `graphics` | **Fixed** — both rows added |
| `USER_JOURNEYS.md`, `TESTING_GUIDE.md` | "four AI checks covering five criteria"; "design accessibility does not exist"; a stale "no `check_graphics`, 14 failing tests" note | **Fixed** — six checks, the design gate described as it is, the §10.3 note superseded with the real figures |
| `WCAG_COVERAGE_REFERENCE.md:15` | ownership as rule 14 / AI 11 | **Fixed in the document** — it now states both the file's counts and the effective routing (13 / 12), and says the data file will be reconciled during the build |
| `docs/USER_JOURNEY_GREENFIELD.md` (1 Jul) | 16 agent specs; `brief` / `requirements_doc` / `architecture_doc`; code-review gate = tech_lead; no 09c/09d, no WCAG checklist, no build-and-merge flow; `stalled` missing | **Fixed** — and it now says where accessibility sits in the journey |
| `docs/USER_JOURNEY_BROWNFIELD.md` (1 Jul) | no 00c/00e/00 agents; gap report ungated; adopted document "staged"; "brownfield has no design phase" | **Fixed** — including the correction that both tracks run the same twelve phases |
| The six research PDFs | "~16 of ~50 criteria"; EN 301 549 = WCAG 2.1; the gate "already built" vs "on the roadmap"; Addendum A's internal contradictions; "temperature 0" determinism | **Recorded** as corrections R23–R30 in `RESEARCH_CORRECTIONS.md`, since the PDFs cannot be edited. Its status line, which stopped at R18, was also fixed |
| Widely quoted | "67% of issues originate in design" | **Recorded** — disputed, and not to be used in client-facing material |
| Team memory notes | brownfield work lives on its own branch | **Fixed** — it is fully merged into this branch |

### Still open, by the team's decision

| Item | Why it waits |
|---|---|
| `backend/apps/a11y/data/ownership.json` still marks the journey criteria as "phase 2" although 09d checks them today | It feeds what the conformance report may claim, so it changes client-facing output and needs its own tests. A behaviour change, not a text fix |
| 05's Step 7 table covers 9 criteria and none of the six new in 2.2 | Widening it is part of §6, not a correction |
| `A11yRoute.Source.ONBOARDING` is never written | An unbuilt feature (§9.3), not a stale statement |

### One row that turned out to be wrong

The earlier version of this table listed the "not asked" reasons in `backend/apps/gates/wcag.py:274-293` as stale. **On reading the code, they are accurate and nothing was changed.** 1.4.10 sits in "checked on the built page", which is true — our own reflow rule measures it there. 2.1.2, 3.2.1, 3.2.2 and 4.1.3 sit in "only visible when the app runs", which is also true, and is precisely why the journey agent is the thing that checks them. That file even carries a test holding its machine buckets against the engines that exist.

---

## 13. Sources

### 13.1 Research evidence, read in full (`docs/web-accessibility/Web-accessibility-research-evidence/`)
1. `AI-Driven-Web-Accessibility-and-WCAG-Compliance.pdf` — Deep Research Report, Aug 2026, 33 pp
2. `AI-Assisted-QA-for-Web-Accessibility-POC-Report_1.pdf` — Report 1, Aug 2026, 22 pp
3. `Report1-Addendum-A-WCAG2.2-Coverage-and-Ownership_1.pdf` — 9 pp
4. `Report1-Addendum-B-Models-Automatability-TechStack_1.pdf` — 8 pp
5. `AI-Accessibility-POC-into-SDLC-Platform-Feasibility_1.pdf` — 9 pp
6. `A11y-POC-Phase2-User-Journeys-and-Backlog_1.pdf` — 15 pp

External sources cited **inside** those PDFs, as printed: W3C WCAG 2 Overview, What's New in 2.2, WCAG 3 intro and the March 2026 draft news, the WCAG 2.1 announcement, WCAG 2.2 TR, Quick Reference, Understanding, ACT Rules, Evaluating Accessibility, WCAG-EM, ARIA APG; WHO disability fact sheet; Jackson Lewis and UsableNet on Title II and lawsuit trends; Level Access on the EAA; TestParty; Kaleidoscope; Deque's coverage report, axe-core, Top 5 Rules of ARIA, axe AI, machine-learning blog and Axe MCP Server; WebAIM Screen Reader Survey #10; Section508.gov ACR/VPAT FAQ; Deque on EN 301 549; eslint-plugin-jsx-a11y; Be My Eyes; Microsoft Azure Vision and Speech; Google image descriptions and Live Caption; Evinced; Siteimprove; 3Play; Verbit; the Overlay Fact Sheet; the FTC accessiBe orders of January and April 2025; AudioEye; UserWay; Lainey Feingold; Signapse; Hand Talk; SignAll; WFD/WASLI on signing avatars; TechCrunch on SLAIT; Immersive Reader; Everway; Recite Me; Aira; Voiceflow; the GitHub accessibility agent blog; Playwright; SARIF; Whisper; PEAT; Model Context Protocol.

### 13.2 Platform docs read
`docs/web-accessibility/`: `Audit_Live_Check_Reasoning.md`, `BUILD_PLAN_OTHER_PHASES.md`, `BUILD_PLAN_QA.md`, `GAP_FIX_BUILD_PLAN.md`, `RESEARCH_CORRECTIONS.md`, `SCOPE_GAP_INFO_AND_RELATIONSHIPS.md`, `TASK_BACKLOG_OTHER_PHASES.md`, `TASK_BACKLOG_QA.md`, `TESTING_GUIDE.md`, `USER_JOURNEYS.md`, `WCAG_COVERAGE_REFERENCE.md`, `evaluation/GOLDEN_DATASET_SPEC.md`, `evaluation/PROVING_GROUND_APP_SPEC.md`, `evaluation/golden/README.md`, `evaluation/harness/README.md`, `evaluation/scorer/README.md`, `evaluation/meridian-onboarding-pack/README.md`.
Elsewhere in `docs/`: `USER_JOURNEY_GREENFIELD.md`, `USER_JOURNEY_BROWNFIELD.md`, `SCREEN_INVENTORY.md`, `UX_JOURNEYS_AND_IA_SPEC.md`.

### 13.3 Source code and git read
All 19 `agents/*/agent.md`; `backend/apps/registry/catalog.py`; `backend/apps/a11y/` (models, policy, dispatch, triage, judge, capture, ingest, scanner, report, findings, page_rules, journey, journey_rules, conformance, ownership, wcag, baseline, backlog, coverage, `checkers/rules.py`, `data/*.json`); `backend/apps/gates/` (`a11ygate.py`, `wcag.py`, `testgate.py`, `securitygate.py`, `readiness.py`, `conditions.py`, `services.py`); `backend/orchestration/` (`trigger.py`, `activities.py`, `build_workflow.py`, `build_activities.py`); `backend/integrations/` (`types.py`, `onboarding.py`, `a11yai/builtin.py`, `design.py`); `backend/apps/projects/models.py`; `mcp_platform_state/tools.py`; `backend/manifest/composer.py`; `runner/companion/` (`daemon.py`, `a11ycapture.py`, `assets/a11y_audit.mjs`); `frontend/src/routes.tsx`, `frontend/src/features/a11y/`; git history on all accessibility paths, branch list and merge-base checks.

### 13.4 Live data read (read-only, 2026-09-15)
Shared server: tenants QA-C (PeopleDesk), wcag2 (WCAG-Audit-2) and test (SpendLog) — projects, runs, artifacts, gate conditions, accessibility findings and audits, plus 80 wireframe HTML documents from the object store.

### 13.5 Outside research (2026-09-15)
⚠ marks a source seen only as a search result summary, not fetched in full.

1. WCAG 2.2 — W3C, 12 Dec 2024 — https://www.w3.org/TR/WCAG22/
2. What's New in WCAG 2.2 — https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/
3. Understanding 4.1.1 Parsing (obsolete) — https://www.w3.org/WAI/WCAG22/Understanding/parsing.html
4. WCAG 2 at a Glance — https://www.w3.org/WAI/standards-guidelines/wcag/glance/
5. Planning and Managing Web Accessibility ⚠ — https://www.w3.org/WAI/planning-and-managing/
6. Developing for Web Accessibility tips ⚠ — https://w3c.github.io/wai-website/tips/developing/
7. Accessibility Maturity Model (draft) ⚠ — https://www.w3.org/TR/maturity-model
8. ACT Rules Format 1.1 Recommendation, Feb 2026 ⚠ — https://www.w3.org/WAI/news/2026-02-05/act-rules-11
9. axe-core ACT implementation report ⚠ — https://www.w3.org/WAI/standards-guidelines/act/implementations/axe-core
10. WCAG-EM 2.0, Jul 2026 ⚠ — https://www.w3.org/TR/WCAG-EM/
11. ARIA Authoring Practices, "Read Me First" — https://www.w3.org/WAI/ARIA/apg/practices/read-me-first/
12. ISO/IEC 30071-1:2019 ⚠ (paywalled) — https://www.iso.org/standard/70913.html
13. EN 301 549 has been updated — AccessibleEU (European Commission), 7 Sep 2026 — https://accessible-eu-centre.ec.europa.eu/content-corner/news/european-accessibility-standard-en-301-549-has-been-updated-2026-09-07_en
14. EN 301 549 v4.1.1: what changes — AxAll ⚠ — https://www.axall.digital/insights/en301549-version-4-1-1-what-changes-and-when-it-applies
15. Section 508 ICT Testing Baseline for Web ⚠ — https://ictbaseline.access-board.gov/web-baselines/
16. Trusted Tester — DHS ⚠ — https://www.dhs.gov/trusted-tester
17. Extension of Compliance Dates (ADA Title II) — Federal Register, 20 Apr 2026 ⚠ — https://www.federalregister.gov/documents/2026/04/20/2026-07663/extension-of-compliance-dates-for-nondiscrimination-on-the-basis-of-disability-accessibility-of-web
18. DOJ extends compliance dates — SBA Office of Advocacy ⚠ — https://advocacy.sba.gov/2026/04/27/doj-extends-compliance-dates-for-state-and-local-governments-to-make-their-websites-accessible/
19. The European Accessibility Act now applies — Travers Smith ⚠ — https://www.traverssmith.com/knowledge/knowledge-container/a-new-milestone-for-accessibility-the-european-accessibility-act-now-applies/
20. VPAT — ITI ⚠ — https://www.itic.org/policy/accessibility/vpat
21. VPAT 2.5: what's new — BarrierBreak ⚠ — https://www.barrierbreak.com/voluntary-product-accessibility-template-vpat-2-5-whats-new/
22. Automated Accessibility Coverage Report — Deque, 2021 — https://www.deque.com/automated-accessibility-coverage-report/
23. Automated testing identifies 57% of issues — Deque, Mar 2021 — https://www.deque.com/blog/automated-testing-study-identifies-57-percent-of-digital-accessibility-issues/
24. Auditing Design Systems for Accessibility (the 67% claim) — Deque, May 2021 — https://www.deque.com/blog/auditing-design-systems-for-accessibility/
25. "67% of accessibility issues originate in design" — rebuttal, Audree Fletcher — https://audreefletcher.co.uk/blog/67-of-accessibility-issues-originate-in-design
26. The WebAIM Million 2026 — WebAIM, Feb 2026 — https://webaim.org/projects/million/
27. Intopia launches the WCAG 2.2 Map — Intopia, 2023 — https://intopia.digital/articles/intopia-launches-wcag-2-2-map/
28. Web Accessibility Annotation Kit — CVS Health ⚠ — https://github.com/cvs-health/annotations
29. A11y Annotation Kit — Indeed, Figma Community — https://www.figma.com/community/file/953682768192596304/a11y-annotation-kit
30. Axe for Designers — Deque — https://www.deque.com/axe/design-beta/
31. Include — Accessibility Annotations, Figma Community — https://www.figma.com/community/plugin/1208180794570801545/include-accessibility-annotations
32. Meet Sidekick — Stark ⚠ — https://www.getstark.co/blog/meet-sidekick-ai-powered-accessibility-assistant/
33. eslint-plugin-jsx-a11y ⚠ — https://github.com/jsx-eslint/eslint-plugin-jsx-a11y
34. Lighthouse accessibility scoring ⚠ — https://developer.chrome.com/docs/lighthouse/accessibility/scoring
35. IBM Equal Access Accessibility Checker ⚠ — https://github.com/IBMa/equal-access
36. Managing focus and visible focus indicators — Vispero ⚠ — https://vispero.com/resources/managing-focus-and-visible-focus-indicators-practical-accessibility-guidance-for-the-web/
37. Human or LLM? A Comparative Study on Accessible Code Generation (FeedA11y) ⚠ — https://arxiv.org/abs/2503.15885
38. CodeA11y — ACM CHI 2025 — https://dl.acm.org/doi/10.1145/3706598.3713335
39. A11yN: Aligning LLMs for Accessible Web UI Code Generation ⚠ — https://arxiv.org/abs/2510.13914
40. A11YRepair ⚠ — https://arxiv.org/abs/2606.21926
41. AccessGuru ⚠ — https://arxiv.org/abs/2507.19549
42. From Code to Compliance (ChatGPT case study) ⚠ — https://arxiv.org/abs/2501.03572
43. WebAccessVL ⚠ — https://arxiv.org/abs/2602.03850
44. Axe MCP Server — Deque — https://www.deque.com/axe/mcp-server/
45. axe-mcp-server-public — Deque, GitHub ⚠ — https://github.com/dequelabs/axe-mcp-server-public
46. Axe MCP Server remediation claim (vendor figure) ⚠ — https://www.deque.com/axe-mcp-server-faster-accessibility-remediation/

**Could not verify:** whether the Accessibility Maturity Model 1.0 is final; the EU Official Journal citation date for EN 301 549 v4.1.1; the clauses of ISO 30071-1; the publication venue of "Human or LLM?"; Microsoft's annotation kit URL; and the research PDFs' claims of "5,000+ lawsuits in 2025" and an HHS May 2026 deadline, both of which rest on secondary blogs.

---

## 14. The team's follow-up questions, answered with evidence

Added 2026-09-16 after a second recon pass over the audit runner, the capture pipeline, the git history, the Figma connector, the conformance module and the agent bodies.

### 14.1 Pages behind a login, and every other page the audit cannot reach

**Confirmed: the audit cannot open a page that needs a login, and the reason is one line of code.**

`runner/companion/assets/a11y_audit.mjs:1115-1122` opens the browser like this:

```js
const browser = await chromium.launch();
const context = await browser.newContext();     // ← no options at all
```

Playwright's `newContext()` accepts a saved session (`storageState`), passwords (`httpCredentials`), custom headers, a viewport, a language and a colour scheme. **We pass none of them.** Nothing upstream could supply them either: the job sheet the platform sends the companion has exactly six fields — version, audit id, project id, base URL, routes, visit map, output (`baseline.py:170-178`) — and the page registration screen offers four inputs: path, label, example path, in scope (`A11yAudit.tsx:452-554`).

**The good news: it fails honestly.** A login-walled page is recorded as unreachable and is excluded from the coverage set (`scanner.py:168-177`), so it is never counted as clean or as fixed. The report says so plainly: *"a route that 404s or sits behind a login produces no findings at all"* (`report.py:579`). The gap was even anticipated — the route model's own example note is *"needs a signed-in session"* (`models.py:606`).

**One thing to watch.** If the app answers a logged-out request with a **200** login page rather than a 401, the audit captures the login page *as though it were the route* — only a status of 400 or more counts as a failure (`:952-958`). So a badly configured app produces findings about the login screen, repeated across every route.

**Does anything already get in?** Two partial paths:
- **09d journeys** drive a real browser and can log in — but only by typing the credentials written in the test case, and they store no page capture, only step verdicts. Nothing behind that login reaches the element judge.
- **09b capture** already covers logged-in pages *incidentally*, because the generated tests log in and the capture rides inside the test's own browser session. But it only sees whatever that one test walked; you cannot say "while you are logged in, also visit these 40 pages".

#### Every other case, checked one by one

| Case | Status | Why |
|---|---|---|
| **Pages needing login** | **Not covered** | No session or credentials anywhere |
| **Form POST / wizard steps** | **Not covered** | The audit only ever does `page.goto`; it never clicks or types |
| **Modals, dialogs, drawers** | **Not covered** | One snapshot after load. 09d sees them but stores no capture |
| **Hover-revealed content** (menus, tooltips) | **Not covered** | Nothing hovers. 09d is deliberately keyboard-only |
| **Tab panels and accordions** | **Partly — and this one is misleading** | Hidden panels are captured but every rule skips elements that are not visible, so they are **captured and never judged**. The page still reads as checked |
| **Infinite scroll** | **Not covered** | There is no scrolling anywhere in the script. A feed is audited on its first screenful of items |
| **Virtualised lists** (react-window and similar) | **Not covered, and unfixable by scrolling** | Off-screen rows are not in the DOM at any moment |
| **Lazy-loaded images** | Partly | Captured as elements, but images below the fold never decode, so the judge gets a blank crop |
| **Pagination** | **Works, but by hand** | `?page=2` is accepted and treated as a separate route. Nothing enumerates pages, and 40 registered pages burn 40 of the 200-route budget |
| **Single-page-app routes** | **Covered** if each has its own URL. Hash routes are a risk: a second `#/route` on an already-loaded page fires no navigation, so it may be captured before it re-renders |
| **iframes** | **Split, and this matters** | axe scans same-origin frames, but element collection never enters a frame, so **nothing inside an iframe is ever judged, cropped or stored**. An app rendered inside an iframe is effectively unaudited |
| **Shadow DOM / web components** | **Mostly not covered** | Element collection does not pierce shadow roots. A web-components app yields almost no elements to judge, while axe still reports — so the page looks "checked, nothing to judge" |
| **Canvas** | Partly | The element and its crop are seen; what is painted inside cannot be |
| **PDFs and other non-HTML** | **Not covered** | No content-type check: the browser's PDF viewer is captured as if it were a page |
| **Video and audio** | **Not covered, but guarded** | Nothing plays media. The platform already refuses to turn "a caption track exists" into a claim that captions are correct (`conformance.py:174-183`) |
| **Mobile and other viewports** | **Desktop only** | No viewport is set, so Playwright's 1280×720 default applies. There is one 320 px reflow measurement, which takes numbers, not a second capture. Mobile-only menus are never audited |
| **Cookie consent banners** | **Not handled, and actively harmful** | Nothing dismisses the banner, so every route's elements, colours and screenshot are captured *through* the overlay |
| **Error and empty states** | Not reachable | 4xx/5xx pages are refused on purpose; empty states need seeded data |
| **Other languages** | Not covered | No language is set; a `/fr/` path must be registered separately |
| **Rate limiting / WAF** | Not handled | Routes are visited in a tight loop; no delay, no retry. A challenge page that answers 200 is captured as the page |
| **Self-signed HTTPS certificates** | **Hard stop** | `ignoreHTTPSErrors` is not set, so a staging URL with a bad certificate fails to load |
| **Multiple subdomains** | Not covered | One base URL per audit |

#### Limits that quietly reduce coverage

| Limit | Default | Reported? |
|---|---|---|
| Routes visited per pass | 60 | Yes (the companion batches) |
| Registered routes per project | 200 | Yes |
| **Elements captured per page** | **600, then it stops** | **No — a page cut at exactly 600 arrives looking complete.** This is the one place the codebase breaks its own "truncation is reported, never silent" rule |
| Judgments per run | 200 distinct elements | Yes, as `OVER_CAP` |
| Element markup sent to the judge | 8,000 characters | Yes |
| Page screenshot | 1.5 MB, else dropped | Yes |
| Wait for the page to settle | 5 seconds | **No** — a slow app can be captured mid-skeleton with no flag |

#### How to close them, cheapest first

1. **Logged-in pages (about a day).** Thread three optional fields through the job sheet into `newContext()`: a saved session, or a login recipe (path, username field, password field, submit), plus `ignoreHTTPSErrors`. The session persists across all routes because one page object is reused. **The real work is secrets** — credentials must go to a credential store, never into a route note, and the job sheet is written to disk on the developer's machine.
2. **Cookie banner (half a day).** One "dismiss" selector per project, clicked once. High payoff, because today a banner contaminates every route.
3. **Headers, delays and retries (half a day).** Fixes WAFs and rate limits.
4. **Viewport and language (half a day)**, with one wrinkle: a route is identified by its path, so a second mobile pass needs the profile in the key.
5. **PDF detection (an hour).** Check the content type and record an honest "not an HTML page".
6. **Infinite scroll (about 20 lines).** Scroll to the bottom in steps before capturing, stop when the page stops growing, and record how many passes it took.
7. **Report what was skipped (small).** Two changes that turn silence into information: flag a page whose element list was cut at 600, and say "N elements were present but hidden, so they were not judged" — which stops a tabbed page reading as fully checked.
8. **iframes and shadow DOM (several days).** Walk into open shadow roots and same-origin frames. The hard part is not the walk, it is that our element identifiers are document-rooted CSS paths, which do not survive a shadow or frame boundary — and those identifiers are what every stored finding is matched on.
9. **Interactive states — modals, wizards, hover (the biggest, and the most valuable).** Do **not** teach the audit script to click. Instead let **09d capture what it walks**: it already reaches these states, so having it post a capture per state feeds the existing judge, crop and report chain unchanged. That single change covers logged-in pages, modals, wizard steps and hover-revealed content at once.

### 14.2 Any tech stack? Any kind of page?

**Short answer: the brownfield audit is stack-agnostic. The greenfield test path is not.**

**The audit works on any stack, and the code shows why.** It needs a URL and a rendered page, nothing else — `page.goto(url)` and then plain CSS selectors over the live DOM. It does not know or ask what built the page. It even carries **its own** axe and browser: it prefers the audited project's copies, and falls back to the companion's pinned versions so that *"every application that is not a Node project is scanned with ours rather than not scanned at all"* (`a11y_audit.mjs:31-55`). So a Java, .NET, PHP, Rails, Django or WordPress application is audited identically.

Its real requirements are environmental, not technological:
1. A companion machine that can reach the app (the server cannot).
2. Node on the PATH, and a Chromium browser installed — both are pre-checked before an audit starts.
3. A reachable URL with a valid certificate (see 14.1).

**The greenfield path is where the stack matters**, and 09b states it plainly (`09b:416-418`):

| Project's test stack | What it gets today |
|---|---|
| **Playwright, TypeScript or JavaScript** | Everything: axe scan plus the capture the AI judge needs |
| **Playwright, Python** | Capture yes, axe scan usually no — reported honestly with the reason attached, never as a clean page |
| **Selenium (Java or C#), Cypress, anything else** | **Neither.** The report says "not supported on this stack" and names it |

The tie is the accessible name: the capture must use the browser's own computed name, and that comes from Playwright's accessibility API. The agent is explicitly forbidden from approximating it.

**There is a good answer for those clients that nobody has written down yet.** The audit carries its own browser and scanner, so a Java/Selenium project can get the full accessibility check today **through the platform audit path**, even though its own test suite cannot. The fix is one row in that table: "not supported in your test suite — use the platform audit", instead of a flat refusal.

**Dynamic pages:** mostly yes, with one weakness. The audit waits for the page load and then up to 5 seconds of network quiet. A normal React or Angular app that fetches and renders is fine. An app with a permanent socket or a long poll never goes quiet, so after 5 seconds it is captured **as-is, possibly mid-skeleton, with no warning**. The fix is small: before scanning, check that the page actually has content, and flag the screen when it does not.

**Infinite scroll:** not covered at all — there is no scrolling in the script (14.1).

**Pagination:** each page must be registered as its own route. Query strings work. There is a better mechanism already built and unused for this: **pattern routes**, where `/events/:id` is registered once with an example page, and findings file against the pattern. Pagination fits that shape exactly, with no new machinery.

### 14.3 The `<td>` tables problem — and what else could surprise us

**What actually happened.** It was not one bug but a chain of four, over five days:

| Commit | Date | The problem |
|---|---|---|
| `5af4c53` | 24 Aug | **Containers were never collected at all** — `table`, `tr`, `ul`, `ol`, `fieldset`, `form`, `canvas`, `iframe`. Found live: on `/loans/current`, loan status was a colour tint on each `<tr>`; the cells inside correctly declined the question (they inherit the colour) and the row that owned it was never offered. The only real failure on the page was never judged — and the page was recorded as checked |
| `755b8ab` | 24 Aug | **The `<td>` fix proper.** The `semantics` check asked "is this pretending to be a control?" A table whose header row is plain `<td>`s is not pretending to be anything, so **no rule selected it**. Every page of the 21 Aug audit was recorded as satisfying 1.3.1 with its tables unexamined. A new `structure` check was added, judging the table as a whole |
| `d16ebd7` | 24 Aug | A long table was judged from its **top 40 rows**, because markup is capped at 8,000 characters. Replaced with a compact shape summary: rows, columns, header cells, scopes, caption, first row and column. On a 401-row table, 31,985 characters of markup became 906 |
| `98b556b` | 28 Aug | axe silently drops "experimental" rules, so **`td-has-header` and `table-fake-caption` never ran** even though both were assumed covered |

**This is a recurring class, not a one-off.** The same shape — *the element was never collected, or was collected and claimed by nobody* — appears **eleven** times in the history:

- **21 Aug:** every element's accessible name came back blank because Playwright had removed the API we called, and a catch block swallowed it. The label check (2.5.3) had selected **zero elements in its entire life**.
- **24 Aug:** `<input type=submit>` buttons were outside 2.5.3, because the code read inner text and an `<input>` has none.
- **27 Aug:** reflow (1.4.10) and non-text contrast (1.4.11) have **no axe rule at all**, yet were recorded as scanner-decided. Also: icons drawn purely in CSS were invisible until `background-image` was captured.
- **27 Aug:** bare `<svg>` with no name reached no check — the `graphics` check was added.
- **28 Aug:** chart lines told apart by colour alone were missed twice over: the shapes were not collected **and** their stroke colours were not captured. Both halves were needed.
- **28 Aug:** three rules skipping real failures — 2.5.3 compared letters instead of words ("Search" inside "Research tools"); a border counted as a valid non-colour cue, skipping the commonest way to mark a field invalid; in-page links were skipped as "real links", so three tabs built as anchors went unjudged.
- **31 Aug:** container `<div>`s without a class were never collected, so three answer-key items were unmeasured — found only by the first 94-page audit.
- **1 Sep:** the accessible name **was not in the batch sent to the judge**, so 13 of 19 items in the human queue were dropdowns answering "I cannot determine the name". Also `border-color` was never captured — the third missing style key after stroke and fill.

**So: yes, there will be more.** Here is the ranked list, with reasoning.

| Risk | Construct | Why |
|---|---|---|
| **1 — near-certain** | **Definition lists (`<dl>`)** | The rule claims them, the shape parser handles them, **and they are not in the collection list**. The check is built, wired and can never be handed one. Exactly the `<td>` shape, sitting in the tree today. One-word fix |
| **2 — highest impact** | **ARIA widget state** — tabs, accordions, comboboxes, trees, menus | The element is collected and claimed, but `aria-expanded`, `aria-selected`, `aria-controls` and `aria-activedescendant` are **not part of what the judge receives**. So it can answer "is this pretending to be a control?" but not the state-and-relationship question 4.1.2 actually asks. Modern applications are mostly this |
| **3 — worse than silence** | **Merged table cells (`colspan`/`rowspan`)** | Column count is taken from the first row's child count, so a merged header row reports the wrong width and the judge reasons from a wrong shape — a confident wrong answer, in the construct just fixed |
| **4** | **Shadow DOM / web components** | Not a single construct: on a component-library app, most of the page reports as clean |
| **5** | **Implicit landmarks** (`<nav>`, `<main>`, `<header>`, `<footer>`, `<aside>`) | Only reachable when an explicit `role` is present — so correctly written HTML5 is invisible while older `role="navigation"` markup is seen. Backwards |
| **6** | **`<details>`/`<summary>` and `<dialog>`** | `details` is collected then declined as a native control; `dialog` is never collected. Disclosure and modal labelling are unchecked |
| **7** | **Media elements** | Not collected; covered only by axe's narrow "a caption track exists" rule. The platform already refuses to turn that into a claim — the risk is a report that *reads* as though media was assessed |
| **8** | **`<legend>`, `<optgroup>`, input types (`date`, `range`, `file`, `color`), `autocomplete`** | Never separable, so a mis-scoped legend or a missing `autocomplete` (1.3.5) is invisible |

**What guards us today, and why it did not catch these.** There are three:
- A **corpus test** that proves every criterion has a working path to a check. But it runs on hand-built elements and **never touches the collection list** — which is exactly why `<dl>` passes green while being unreachable.
- A **selectable check** in the evaluation harness that loads the real fixture in a browser and uses the real collection list. This is the only guard that can see a collection gap — but only for elements someone wrote an answer-key record for. Nothing in the answer key names a `<dl>`, a `<dialog>` or a `<details>`.
- A **completeness scorer** that tracks expected → captured → judged per page.

**The one cheap fix that closes the whole class:** a **construct census**. List the HTML constructs that matter, and assert that each is either in the collection list or explicitly recorded as out of scope with a reason — the same ratchet the scorer already uses for known shortfalls. Today **nothing anywhere holds the collection list and the rule list against each other**, and that single comparison would have caught `<dl>` and would have caught `<td>`.

### 14.4 Designs imported from Figma

**The blunt finding: connecting Figma removes the very thing we can check.** In generate mode, 05 authors self-contained HTML that a browser can render and axe can scan. In read-as-source-of-truth mode it registers a **pointer** to the Figma file instead (`05:542`). There is no HTML, so there is nothing to scan.

**What we can actually read from Figma today** — five REST calls, all JSON, no images:

| Data | Available? |
|---|---|
| Design tokens (variables), colours resolved to hex | **Yes** |
| Published component names and links | **Yes** |
| Top-level frame names and ids | **Yes** |
| Everything below the top level — nested layers, layer order, text content, font sizes, element sizes, auto-layout | **Fetched and then thrown away** by our own code |
| Text styles, images or PNG exports, dev-mode annotations, comments, which token is used where | **Not fetched at all** |
| Multi-mode variables (light/dark, high contrast) | **Only the first mode is kept** — a dark palette is currently invisible |

**And we cannot write back.** Pushing anything into Figma is a deliberately deferred seam, and UX artifacts are excluded from the export policy. So remediation of a design is always a **report a designer applies by hand**. That shapes the deliverable: it must be a per-frame, per-criterion list with exact replacement values — the failing colour pair and a passing one, the measured target size and how short it falls — not a promise to fix.

**What is already true and easy to miss:** the platform *already has* a design-time WCAG 2.2 mechanism, and it works whether or not Figma is connected — the 22-question checklist on the UX gate. So the answer to "how do we check a Figma design" is not "build a design scanner"; it is **"make that checklist evidence-backed instead of opinion-backed"**.

**Recommended, in order:**

1. **Token contrast analysis — verifiable, cheap, works on today's data.** Colours already resolve to hex; compute every pair's ratio and attach the numbers to the gate's 1.4.3 and 1.4.11 questions so the designer ticks against evidence. **Fix the single-mode bug first**, or a dark-mode palette is silently unchecked.
2. **Keep the frame detail we already fetch and discard — small change, big return.** Node sizes, child order and text sizes are in the response we already receive. Keeping them makes **2.5.8 target size measurable rather than advisory**, makes reading order (1.3.2, 2.4.3) a real proposal, and lets us flag text that is too small.
3. **Add a frame image export — advisory only.** One new call, stored the way uploaded document pages already are, read through the existing image pipe. That gives an AI reviewer eyes for colour-only meaning (1.4.1), images of text (1.4.5) and whether a focus state was drawn. **Do not route this through the 09c judge** — its contract is a captured DOM element written only by the companion, and loosening that would let an agent *describe* a page instead of one having been captured.
4. **Do not build a Figma-to-HTML converter and scan that.** It would invent the very things WCAG asks about — heading levels, landmarks, labels, tab order, roles — so every pass would be unfounded and every failure ambiguous between "the design is wrong" and "the converter is wrong".
5. **Accept what stays human, permanently:** alt-text intent, error wording, gesture alternatives, cross-screen consistency, and the authentication and redundant-entry decisions. No export contains intent.

**Brownfield variant — a client uploads design PDFs rather than connecting Figma.** Today those are extracted, their page images preserved, and transcribed by the document-vision agent — with **no accessibility check**. The image pipe is the leverage point: the same path could serve a design review for the visual criteria. It cannot measure contrast ratios or target sizes from a page render, and must not be asked to.

### 14.5 Ideation — you are right, make it conditional

Agreed, and I will change it. Naming disabled users as stakeholders should **not** be a blanket instruction. It applies when:
- **the law requires it** — the product is sold or operated in a market with an accessibility duty, or a public-sector buyer will ask for a conformance report; or
- **the product's own audience demands it** — the user base plainly includes the affected groups, or accessibility is a stated goal.

Otherwise, the accessibility target set in the project profile is enough, and Ideation adds nothing. The right single question for 01 is not "who are the disabled users" but **"does an accessibility duty apply to this product, and in which markets?"** — because that answer sets the standard, the deadline and the gate strictness for everything downstream.

### 14.6 Architecture — my wording was wrong, and here is the correct rule

You are right to push back, and the current phrasing is misleading. **Nobody should go back to hand-written HTML.** The rule is about **what a component renders**, not which framework you use.

**The corrected decision, which will replace the "native HTML first" line:**

> **Prefer components that render real HTML elements, in whatever framework the project uses.** A React or Angular button should end up as `<button>`, not `<div onClick>`. Most mature libraries already do this — MUI, Radix, React Aria, Angular Material and Ark all render real elements and implement the keyboard behaviour. Tailwind is a styling tool and is unaffected: it changes how something looks, not what it is.
>
> **Choose one component library and record the choice as an architecture decision**, including its accessibility documentation. The three questions to answer for it: does it render real elements; does it document its keyboard behaviour; does it manage focus for overlays, menus and dialogs?
>
> **Where the library has no suitable component**, build it to a named pattern from the [ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/) and say which pattern in the design annotation. The APG's own rule is worth quoting to a team: *"No ARIA is better than bad ARIA"* — a role is a promise, and if you claim `role="tablist"` you must implement arrow-key behaviour too. [WebAIM's 2026 scan](https://webaim.org/projects/million/) found pages using ARIA averaged **59.1 errors against 42** for pages without it — not because ARIA is bad, but because it is usually added instead of using the right element.

**Does that answer the team's question?** Yes, and it matters concretely for us: our own design annotations name a pattern (`pattern=APG/combobox`), and that only works if architecture picked a library that can deliver it. Without the decision, the annotation is unbuildable and the problem surfaces in code review.

### 14.7 Greenfield: how you actually get the conformance report

The machinery exists and works. Here is the path, and the three places it currently falls short.

**The path today, step by step:**

1. **09 Testing** writes the test cases, marking end-to-end ones.
2. **09b Test Automation** runs the suite. Each screen writes a candidates file; the companion collects it and posts it. **This is where the automatic evidence comes from** — every axe result, including passes, becomes a coverage record saying "this criterion was examined on this page".
3. **The AI pass fires automatically** at the end of the 09b build, dispatching the 09c judge. Its verdicts become coverage records too, including "a person must decide this".
4. **09d keyboard journeys** — and here is the first problem: **nothing triggers these automatically.** A qa_lead has to press a button. Eight criteria depend on somebody remembering.
5. **Compile.** The conformance screen joins the coverage records, the open failures, any human decisions and the ownership registry, producing all 55 rows.
6. **A qa_lead reviews, fills the gaps, and signs.** The signature *is* the gate: it is bound to a hash of the wording and of the evidence, any edit clears it, and new evidence marks it stale. Export is refused while unsigned or stale.

**The artifact** is a Markdown document, `a11y-conformance.md`, with: scope, a plain disclaimer that this is risk reduction and not certification, what the statement is based on, a summary of evaluated versus not evaluated, and a row per criterion — criterion, level, conformance, established by, what was checked.

**So a greenfield project can produce a report. But it cannot produce a complete one today**, for three structural reasons:

1. **Reflow (1.4.10) and non-text contrast (1.4.11) are brownfield-only in practice.** Their only evidence is a browser measurement written by the **audit** script. The 09b agent never asks for it, and axe has no rule for either. Both read "Not evaluated" on every greenfield statement.
2. **The design gate's answers are thrown away.** The UX gate is where a person genuinely answers the human-only criteria — and it writes **no coverage record at all**. The same questions are then asked again at signing, with no memory of the design gate's answer.
3. **Journeys are manual** (step 4), so eight criteria are lost if nobody presses the button.

**Also worth fixing:** there is no accessibility item on the deployment gate, so a release can ship with an unsigned or stale statement; the statement is one row per project and re-signing overwrites it, so there is no "the statement as at release 2.3"; and the conformance screen shows a red "no completed audit — nothing was checked" banner to greenfield projects **even when the backend counted their development-run evidence**, which is simply a wrong message.

**What makes the report a natural end of the lifecycle (five changes):**
1. Have 09b record the two page measurements the audit script already produces, so reflow and non-text contrast stop being brownfield-only.
2. Queue the keyboard journeys automatically at the end of the testing build, the way the AI pass is already queued.
3. Write a human coverage record when a design-gate question is attested, so the human-only criteria arrive at signing pre-answered, with provenance.
4. Bind a signed statement to a release, instead of mutating one row.
5. Add a **derived** condition to the deployment gate: a signed, non-stale statement exists for this release. That is the piece that turns the report from a screen someone visits into the end of the lifecycle.

### 14.8 Splitting the UX agent — the answer is yes, but not by adding an agent

**Your instinct is right that 05 will get big; the evidence says size is not the risk.**

The numbers: 05 is 40 KB today (third largest, behind 09 at 51 KB and 09b at 46 KB). The accessibility work would make it the largest, perhaps 50–60 KB — around 13–15 thousand tokens. For comparison, the *whole* context the platform assembles for a run — project, artifacts, events, clarifications, rules — is about **3,600 tokens typically and 12,150 in the worst case**, measured in the composer's own documentation and confirmed on a live run. **The agent body is already three times the platform context, and would become four times.**

What the repository actually records about failures is telling. There is **no incident of an agent ignoring an instruction because it sat deep in a long file.** The one incident that looked like it — the July clarifications gate — explicitly concluded the truncation was *not* the cause; the decisive sentences survived, and the real cause was that the agent's tools were unreachable. What the evidence does show, repeatedly, is the other thing: **an instruction with no checker behind it is not reliably followed at any length.** 05's own line "Color contrast ratios verified for all combinations" is exactly that, and §4.2 shows the result on a live project.

**So the split is worth doing — but along the right seam.** Not "a long file, cut in half", but "who is responsible for what":

| Goes where | What |
|---|---|
| **Stays in 05** (authoring guidance) | WCAG 2.2 in place of 2.1; the template with landmarks, one `h1`, skip link, language, motion handling and four widths; the token block; the `@a11y` annotations; the flow rules; the spec artifact. Everything the agent must *know while designing* |
| **Moves into platform code** (deterministic, no prompt) | Contrast arithmetic; the axe pass over stored wireframes; target-size geometry; annotation completeness; the derived gate condition. These are calculations, and a calculation in a prompt is a wish |
| **Goes to an agent — the one we already have** | Judgment that rules cannot settle: alt intent, fake semantics, structure, colour-only meaning, label-in-name. **Use the existing 09c judge**, which already runs as a separate, gate-less, batched agent with caps and de-duplication |

**Why not a new accessibility design agent?** Because it would restate 09c's judging reasoning in a second file — the exact duplication the migration rule exists to prevent — and add a phase key, a dispatch path and per-screen batching that all already exist. The judge does not care whether the HTML came from a wireframe or a running app; it judges captured elements.

**And splitting does not conflict with the 75/15/10 rule.** That rule governs migrating a legacy agent body: keep the reasoning, reroute the data references, replace the glue. 09c and 09d are `native` agents with no legacy source, so the rule has nothing to bind — the catalog says so explicitly. Two constraints do survive: what stays in 05 must not be paraphrased or reordered, and we must not move 05's *design reasoning* out. Moving the *checking* out is not moving reasoning, because the checking does not exist in 05 as reasoning today — it exists as an unverifiable sentence.

**Net effect on the build plan in §10:** no new agent, no new phase. W3-1 gains a design-source path in the existing dispatch, and W5-2 (new judge checks) covers the judging side.
