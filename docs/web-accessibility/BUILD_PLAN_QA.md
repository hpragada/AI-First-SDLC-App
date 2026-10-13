# Build Plan — Web Accessibility QA (POC + Phase 2)

**What this plan is for.** This is the *order* to build the accessibility QA capability in, and how the 31 tasks depend on each other. The full detail of each task — what to build, edge cases, and how to know it's done — lives in `TASK_BACKLOG_QA.md`; this plan tells you what to do first, what can run in parallel, and which chain of tasks decides the timeline. Estimates and sprints are deliberately not included (team decision).

> **Read `RESEARCH_CORRECTIONS.md` before working this plan.** A source-level review of the platform (2026‑08‑12) found several "already exists" claims in the research to be untrue — above all, **the testing agent has never run an accessibility scan**. Seven tasks were added and five re-scoped, and the critical path changed. The plan below is the corrected one.

**How to work it.** Pick the next unblocked task from the current milestone, open its block in `TASK_BACKLOG_QA.md`, build it, and tick its box to `🟢` in the backlog with a one‑line "what shipped". A task is only ready to start when everything in its **Depends On** is `🟢`.

---

## The five milestones, in order

**M0 — Foundation: the shared judgment engine.**
Goal: a working, swappable, grounded `a11yai` capability the testing flow can call, with the guardrails and volume controls around it. Nothing else can run until this exists.
Tasks: QA‑01, QA‑02, **QA‑02a**, QA‑03, QA‑04, QA‑05, QA‑06, QA‑07, QA‑08 — plus the internal‑only accuracy tasks **QA‑10a**, ~~QA‑09~~, QA‑10 (local `make`, run alongside).
*Prerequisite before QA‑01:* ~~add `pytest-cov` + a module-scoped `make cov`~~ — **done**.
> **QA‑09 is ⏸ parked (team, 2026‑08‑17).** It is expert labelling work, not code, and the screens do not exist yet. **QA‑10a and QA‑10 are not parked**: the harness scores from whatever label sources exist, and one — the reviewer verdicts stored on every finding since QA‑12a — exists already. See `TASK_BACKLOG_QA.md` D‑A11Y‑62 … D‑A11Y‑66.

**M1 — Testing POC: the core deliverable.**
Goal: a test run scans with the rules **and** judges with the AI at WCAG 2.2, reports both together with confidence, opens/closes defects automatically, and blocks the gate on real failures.
Tasks: QA‑11, **QA‑11a**, **QA‑11b**, QA‑12, **QA‑12a**, QA‑13, QA‑14, **QA‑15a**, QA‑15, QA‑16.
*QA‑11a is where an accessibility scan executes for the first time in this platform.*

**M2 — Brownfield baseline audit: run the engine on an existing app.**
Goal: point the testing engine at an onboarded, already‑built app and produce a WCAG‑2.2 baseline + fix backlog, with no prior design phase.
Tasks: QA‑17, QA‑18, QA‑19. *(Needs the onboarding hook OP‑06 from the other plan to supply the route list; QA‑17 can be built against a hand‑provided route list until OP‑06 lands.)*
*This is the highest-volume run in the whole build — the whole app, first pass, empty cache. Do not run it before QA‑02's cap and QA‑07's caching are `🟢`.*

**M3 — Phase 2, agentic testing: operate the app, don't just scan it.**
Goal: an AI agent that keyboard‑ and interaction‑tests a journey, feeding the same bug loop — ~~kept advisory until it's proven accurate~~ **advisory always, so it never stands in a client's way (D‑A11Y‑83)**.
Tasks: QA‑20, QA‑21, QA‑22.

**M4 — Phase 2, governance: human review + a signed conformance report.**
Goal: a human expert reviews uncertain findings and produces a defensible, human‑signed conformance/VPAT — the platform never auto‑certifies.
Tasks: **QA‑23a**, QA‑23, QA‑24.

> **Do M0 → M1 first.** M2, M3, and M4 all build on M1 and can then be done in any order (or in parallel by different people). ~~QA‑09/QA‑10 run alongside so we can prove accuracy before release — but note the golden-set screens are **not ready yet**, and those two gate only QA‑22 (Phase 2), so they never hold up M0 or M1.~~
> **Superseded 2026‑08‑17:** **QA‑09 is ⏸ parked** and now gates nothing. ~~**QA‑10a → QA‑10** run alongside and gate only **QA‑22** (Phase 2)~~
> **Superseded again 2026‑08‑18 (D‑A11Y‑82):** the internal accuracy evaluation is **decoupled from the platform entirely** — it is our report card, and nothing in the product reads it. **QA‑10a and QA‑10 now gate NOTHING**, and QA‑22 depends only on QA‑20. The whole of E‑EVAL can be scheduled whenever it suits; it is no longer on anyone's critical path.

**Status at 2026‑08‑18:** M0 complete except the E‑EVAL tasks · M1 complete · M2 complete · **M3 complete: QA‑20 and QA‑21 built (🟡), QA‑22 🟢 done** · **M4 complete — QA‑23a 🟢, QA‑23 🟡, QA‑24 🟡** (console + signed conformance statement; 115 new tests green). **All 24 QA tasks are now built.** Six of them (QA‑11a, QA‑12, QA‑20, QA‑21, QA‑23, QA‑24) are 🟡 waiting on one live session against a real application; the E‑EVAL tasks remain parked and gate nothing.

> **2026‑08‑18 — E‑EVAL is off the critical path for good (D‑A11Y‑82).** The internal accuracy evaluation no longer feeds anything in the product, so QA‑10a and QA‑10 gate nothing and QA‑22 depends only on QA‑20.
> **2026‑08‑24 — QA‑10a and QA‑10 are built** (`evaluation/scorer/`, `make a11y-eval`). Still off the critical path, still read by nothing in the product. The half that needs no answer key — counting what was dropped — works today; the half that scores accuracy waits on the golden set (QA‑09), and says so rather than printing a number it does not have.

> **Four tasks share one live checkpoint: QA‑11a, QA‑12, QA‑20 and QA‑21.** All four are built and fully tested, and none has driven a real browser. One session against a running application closes all four. **QA‑22 is not among them** — it is proven against the gate itself, which needs no browser.

---

## Live status — 2026‑08‑21

**The live checkpoint has happened, and it did NOT close all six.** Five runs against Meridian Library (20–21 August) proved the **brownfield** chain end to end and left the rest exactly where it was. The single-session assumption above was wrong: the runs were all baseline audits, and a baseline audit does not exercise the greenfield capture, the keyboard journey, the review console, or signing.

| Task | What five live runs actually did to it |
|---|---|
| **QA‑12** — the AI‑checks pass | **Ran live, repeatedly.** Real verdicts, real findings, real defects, report and baseline published. Proven through the *brownfield* entry point; the greenfield feature run in its AC5 has still not happened |
| **QA‑11a** — generated axe assertions | **Untouched.** Greenfield only, and every live run was brownfield |
| **QA‑20 / QA‑21** — the keyboard journey | **Untouched.** Zero journey runs exist. It has never opened a page |
| **QA‑23** — the review console | **Untouched in the way that matters.** The queue has been **empty on all five runs** — every check answered on its own. No reviewer has opened a real finding, so the lock, the claim/release and confirm‑raises‑a‑defect are still unexercised |
| **QA‑24** — conformance / VPAT | **Half.** The statement has been *rendered from a real audit's findings* and names the run it came from. **Nobody has signed one live**, and signing is what registers and approves the artifact |

**Status markers are deliberately not changed here.** Which of these is now 🟢 is the team's call, not mine — this note records what the runs did so that call can be made on evidence. The per‑task blocks in `TASK_BACKLOG_QA.md` still read 🟡.

**What is also true, and is not in the 24 tasks at all:** **thirty-five further findings** — seventeen out of those five runs, six more on 24 August, four from tracking a live seventeen-page audit from asking whether we capture every element WCAG puts in scope, and eight on 25 August from the team reading the screens as a user meets them. **All thirty-five are built** — one of them, the 1.3.1 scope gap, was a design decision rather than a defect and is written up on its own in `SCOPE_GAP_INFO_AND_RELATIONSHIPS.md`. They live in `GAP_FIX_BUILD_PLAN.md` §9 (twenty-four sections) and are numbered #19–#53 in `TESTING_GUIDE.md` §9 — a section nobody planned for, now larger than the plan it was appended to.

---

## Dependency map (what must be `🟢` before what)

```
M0 FOUNDATION
  QA-01 ──► QA-02 ──► QA-02a ──► QA-03 ──► QA-06
              │         ▲                    │
              └► QA-07  │                    └► QA-09 ─┐
  QA-04 ────────────────┘                              ├► QA-10
  QA-04 ──► QA-05                            QA-10a ───┘
  QA-08   (no dependencies)
  QA-15a  (no dependencies)

M1 TESTING POC
  capture chain :  QA-04 ──► QA-11 ──► QA-11a ──► QA-11b ─┐
  judgment chain:  QA-03, QA-06, QA-07 ───────────────────┴──► QA-12
  findings ledger: QA-06 ──► QA-12a

  QA-12 + QA-12a ──► QA-13
  QA-12 + QA-12a ──► QA-14 ──► QA-15      (QA-15 also needs QA-08 + QA-15a)
  QA-12 ──────────► QA-16

M2 BROWNFIELD          M3 AGENTIC (P2)          M4 GOVERNANCE (P2)
  QA-12 ──► QA-17        QA-16 ──► QA-20        QA-23a ────────┐
  QA-17,14 ► QA-18       QA-20 ──► QA-21        QA-06, QA-12a ─┴► QA-23
  QA-15 ──► QA-19        QA-20 ──► QA-22       QA-13, QA-23 ───► QA-24
  (QA-17 consumes OP-06)
```

## Critical path (the chain that sets the timeline)
**QA‑01 → QA‑02 → QA‑02a → QA‑03 → QA‑06 → QA‑12 → QA‑14 → QA‑15**

Two feeder chains must land before their join points, and a slip in either slips the same amount:
- **capture:** QA‑04 → QA‑11 → QA‑11a → QA‑11b, all `🟢` before QA‑12
- **ledger:** QA‑06 → QA‑12a, `🟢` before QA‑14

Read as a sentence: build the front door, the dispatch layer, the judge agent, the checkers and the safety valve; get a real scan running and its candidates captured; join the two into one report; open self-closing defects; enforce the gate. Protect this chain — everything off it has slack.

## What can run in parallel (assign to different people)
- **QA‑04 + QA‑05** (WCAG knowledge base + criterion registry) run alongside QA‑01/QA‑02. QA‑04 is needed early — it feeds QA‑02a, QA‑03 **and** QA‑11.
- **QA‑08** (gate policy, reviewer role, WCAG target) has no dependencies — any time before QA‑15.
- **QA‑15a** (the `refresh_derived` fix) has no dependencies — any time before QA‑15. Small; good first task for someone new.
- **QA‑07** needs only QA‑02 — build alongside QA‑02a/QA‑03, and it must be `🟢` before QA‑12 touches anything real.
- **QA‑10a** has no dependencies. **QA‑10** needs only QA‑10a — it no longer waits on the golden set (D‑A11Y‑63). **QA‑09** is ⏸ parked and blocks nothing. ~~The QA‑10a → QA‑10 pair gates only QA‑22.~~ **2026‑08‑18 (D‑A11Y‑82): the pair gates nothing at all** — the evaluation is internal and no part of the product reads it. Schedule E‑EVAL whenever; it holds up nobody.
- **The capture chain (QA‑11 → QA‑11a → QA‑11b) is fully parallel to the judgment chain** — it only needs QA‑04. This is the biggest parallelisation win in the plan: one person on capture, one on judgment, joining at QA‑12.
- **QA‑23a** (mockups) has no dependencies and is a different skill — start it any time.
- Within M1, **QA‑13** and **QA‑16** branch off QA‑12, parallel to the QA‑14 → QA‑15 chain.
- **M2, M3, M4** are three independent branches off M1 — three people can take one each.

---

## Definition of Done (every task — binary, no "mostly done")
- [ ] Behaviour matches the task's Description and every Acceptance Criterion in `TASK_BACKLOG_QA.md` is demonstrated on a real screen/run.
- [ ] Unit + integration tests written; **≥ 90% coverage on new code**; any new tenant‑scoped table proves RLS isolation with a test.
- [ ] `make test` / `make lint` (backend) and `npm run lint` + `tsc -b` (frontend) pass.
- [ ] Any agent‑file edit (09/09b/09c) passes the platform **reference sweep** (no leftover local paths; inputs/outputs go through platform capabilities) — the 75/15/10 rule.
- [ ] An AI finding never asserts conformance on its own; low confidence routes to a human; axe failures always stand.
- [ ] **No fixture-only completion.** If the behaviour can only be shown with fabricated data, say so at review and name what would prove it for real.
- [ ] The task box is ticked `🟢` in the backlog with a one‑line "what shipped" note.

**Milestone done‑checks:** M1 is done when a **real feature run** shows axe + AI findings in one report, a defect auto‑opens and auto‑closes, and the gate blocks a planted AI‑confirmed critical — demonstrated on a live run, not fixtures. The whole QA plan is done when an onboarded app can be audited (M2), a critical journey is keyboard‑tested by the agent (M3), and an SME can export a signed conformance report (M4).

**An earlier checkpoint worth naming:** **QA‑11a is the first moment an accessibility scan actually executes in this platform.** Treat it as a hard checkpoint — if axe violations don't appear there as real, self-closing defects, nothing downstream will work, and finding that out at QA‑11a costs a fraction of finding it out at QA‑15.

---

## Cross‑references
- **What the research got wrong about the platform (read first):** `RESEARCH_CORRECTIONS.md`.
- **Task detail (read before building any task):** `TASK_BACKLOG_QA.md`.
- **The user journeys these serve:** `USER_JOURNEYS.md` (J1, J4, J5‑audit, J8, J9).
- **How we prove the checkers are accurate (E‑EVAL, Edvensoft‑internal):** `evaluation/` —
  `PROVING_GROUND_APP_SPEC.md` is the fixture app with deliberately planted WCAG defects, and
  `GOLDEN_DATASET_SPEC.md` is the hand‑labelled answer key over it. Read both before QA‑09/QA‑10. **Both describe QA‑09, which is ⏸ parked (2026‑08‑17)** — they stay in the repo as the spec to build to when it is un-parked, and QA‑10 must not be built to assume the golden set is present.
  The same fixture serves the M2 brownfield audit, the M3 keyboard journeys, and the client demo.
- **The other phases (build after this):** `BUILD_PLAN_OTHER_PHASES.md`.
- **Why / the accessibility facts:** Report 1 + Addendum A (Rule/AI/Human split), Addendum B (LLM vs VLM + tech stack), Feasibility Assessment (reuse vs new) — all read **subject to** `RESEARCH_CORRECTIONS.md`.
