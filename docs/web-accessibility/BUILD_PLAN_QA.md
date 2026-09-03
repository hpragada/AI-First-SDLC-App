# Build Plan — Web Accessibility QA (POC + Phase 2)

**What this plan is for.** This is the *order* to build the accessibility QA capability in, and how the 24 tasks depend on each other. The full detail of each task — what to build, edge cases, and how to know it's done — lives in `TASK_BACKLOG_QA.md`; this plan tells you what to do first, what can run in parallel, and which chain of tasks decides the timeline. Estimates and sprints are deliberately not included (team decision).

**How to work it.** Pick the next unblocked task from the current milestone, open its block in `TASK_BACKLOG_QA.md`, build it, and tick its box to `🟢` in the backlog with a one‑line "what shipped". A task is only ready to start when everything in its **Depends On** is `🟢`.

---

## The five milestones, in order

**M0 — Foundation: the shared AI engine.**
Goal: a working, swappable, grounded `a11yai` capability the testing agents can call, with the guardrails and cost controls around it. Nothing else can run until this exists.
Tasks: QA‑01, QA‑02, QA‑03, QA‑04, QA‑05, QA‑06, QA‑07, QA‑08 — plus the two internal‑only accuracy tasks QA‑09, QA‑10 (Edvensoft CI, run alongside).

**M1 — Testing POC: the core deliverable.**
Goal: the testing phase runs the rule scanner **and** the AI checks at WCAG 2.2, reports both together with confidence, opens/closes defects automatically, and blocks the gate on real failures.
Tasks: QA‑11, QA‑12, QA‑13, QA‑14, QA‑15, QA‑16.

**M2 — Brownfield baseline audit: run the engine on an existing app.**
Goal: point the testing engine at an onboarded, already‑built app and produce a WCAG‑2.2 baseline + fix backlog, with no prior design phase.
Tasks: QA‑17, QA‑18, QA‑19. *(Needs the onboarding hook OP‑06 from the other plan to supply the route list; QA‑17 can be built against a hand‑provided route list until OP‑06 lands.)*

**M3 — Phase 2, agentic testing: operate the app, don't just scan it.**
Goal: an AI agent that keyboard‑ and interaction‑tests a journey, feeding the same bug loop — kept advisory until it's proven accurate.
Tasks: QA‑20, QA‑21, QA‑22.

**M4 — Phase 2, governance: human review + a signed conformance report.**
Goal: a human expert reviews uncertain findings and produces a defensible, human‑signed conformance/VPAT — the platform never auto‑certifies.
Tasks: QA‑23, QA‑24.

> **Do M0 → M1 first.** M2, M3, and M4 all build on M1 and can then be done in any order (or in parallel by different people). The internal‑only QA‑09/QA‑10 run in Edvensoft CI alongside M0/M1 so we can prove accuracy before release.

---

## Dependency map (what must be `🟢` before what)

```
M0 FOUNDATION
  QA-01 ──► QA-02 ──►┐
  QA-04 ─────────────┤──► QA-03 ──► QA-06 ─────────────┐
  QA-04 ──► QA-05    │        │                        │
  QA-08 (independent)│        └──► (used by QA-12,14)   │
  QA-03 ──► QA-09 ──► QA-10                             │
                                                        ▼
M1 TESTING POC
  QA-04 ──► QA-11 ──►┐
                     ├──► QA-12 ──► QA-13
  QA-03, QA-06 ──────┘        │
                             ├──► QA-14 ──► QA-15   (QA-15 also needs QA-08)
                             └──► QA-16

M2 BROWNFIELD          M3 AGENTIC (P2)          M4 GOVERNANCE (P2)
  QA-12 ──► QA-17        QA-16 ──► QA-20          QA-06 ──► QA-23
  QA-17,14 ► QA-18       QA-20 ──► QA-21          QA-13,23 ► QA-24
  QA-15 ──► QA-19        QA-10,20 ► QA-22
  (QA-17 consumes OP-06)
```

## Critical path (the chain that sets the timeline)
**QA‑01 → QA‑02 → QA‑03 → QA‑06 → QA‑12 → QA‑14 → QA‑15.**
This is the spine of the POC: build the capability, its switchboard, the four checkers, the safety valve, wire the AI pass into testing, connect the defect loop, and enforce the gate. Protect this chain — a slip here slips the POC. Everything off it has slack.

## What can run in parallel (assign to different people)
- **QA‑04 + QA‑05** (the WCAG knowledge base + criterion registry) run alongside QA‑01/02, and only need to be `🟢` before QA‑03 (KB) and QA‑12 (registry).
- **QA‑08** (gate policy + reviewer role) has no dependencies — build it any time before QA‑15.
- **QA‑07** (cost/caching/audit) only needs QA‑02 — build it in parallel with QA‑03.
- **QA‑09 + QA‑10** (internal accuracy, Edvensoft CI) run in parallel with everything once QA‑03 exists.
- Within M1, **QA‑13** and **QA‑16** branch off QA‑12 and can be done in parallel with the QA‑14 → QA‑15 chain.
- **M2, M3, M4** are three independent branches off M1 — three people can take one each.

---

## Definition of Done (every task — binary, no "mostly done")
- [ ] Behaviour matches the task's Description and every Acceptance Criterion in `TASK_BACKLOG_QA.md` is demonstrated on a real screen/run.
- [ ] Unit + integration tests written; **≥ 90% coverage on new code**; any new tenant‑scoped table proves RLS isolation with a test.
- [ ] `make test` / `make lint` (backend) and `npm run lint` + `tsc -b` (frontend) pass.
- [ ] Any agent‑file edit (09/09b) passes the platform **reference sweep** (no leftover local paths; inputs/outputs go through platform capabilities) — the 75/15/10 rule.
- [ ] An AI finding never asserts conformance on its own; low confidence routes to a human; axe failures always stand.
- [ ] The task box is ticked `🟢` in the backlog with a one‑line "what shipped" note.

**Milestone done‑checks:** M1 is done when a real feature run shows axe + AI findings in one report, a defect auto‑opens and auto‑closes, and the gate blocks a planted AI‑confirmed critical. The whole QA plan is done when an onboarded app can be audited (M2), a critical journey is keyboard‑tested by the agent (M3), and an SME can export a signed conformance report (M4).

---

## Cross‑references
- **Task detail (read before building any task):** `TASK_BACKLOG_QA.md`.
- **The user journeys these serve:** `USER_JOURNEYS.md` (J1, J4, J5‑audit, J8, J9).
- **The other phases (build after this):** `BUILD_PLAN_OTHER_PHASES.md`.
- **Why / the accessibility facts:** Report 1 + Addendum A (Rule/AI/Human split), Addendum B (LLM vs VLM + tech stack), Feasibility Assessment (reuse vs new).
