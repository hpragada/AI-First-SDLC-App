# Build Plan — Web Accessibility, Other Phases (Shift‑Left)

**What this plan is for.** This is the *order* to push accessibility earlier in the lifecycle — into design, code review, and brownfield onboarding — after the QA capability exists. The full detail of each of the 9 tasks is in `TASK_BACKLOG_OTHER_PHASES.md`; this plan gives the order, the dependencies, and what runs in parallel. No estimates/sprints (team decision).

**Prerequisite: build the QA plan first.** Every task here reuses the `a11yai` capability (QA‑01/02/02a/03), the WCAG 2.2 knowledge base (QA‑04), the confidence gate (QA‑06), the gate policy (QA‑08), the **candidate-capture route (QA‑11b)** and the **findings ledger (QA‑12a)** from `BUILD_PLAN_QA.md`. Dependencies on QA tasks are named below.

> **Read `RESEARCH_CORRECTIONS.md` first.** Correction **R5** affects four of these nine tasks: OP‑01, OP‑02, OP‑06 and OP‑07 were written against the legacy agent suite and named local file paths that do not exist in this platform. They have been corrected in `TASK_BACKLOG_OTHER_PHASES.md`. Correction **R2** matters here too: any "rendered preview" is a **localhost URL on a developer's machine**, so design- and review-time checks reuse the QA‑11b capture route rather than rendering server-side.

**How to work it.** Pick the next unblocked task, open its block in `TASK_BACKLOG_OTHER_PHASES.md`, build it, tick it `🟢`. A task is ready only when everything in its **Depends On** (including any QA‑xx) is `🟢`.

---

## The four milestones, in order

**N1 — Design‑time accessibility.**
Goal: catch accessibility problems in the wireframes, before any code, and gate the design phase on serious ones.
Tasks: OP‑01 (spec to WCAG 2.2) → OP‑02 (AI design checks) → OP‑03 (design gate).

**N2 — Code‑review‑time accessibility.**
Goal: catch the "meaning" defects at code review, before testing, and route criticals into the existing fix loop.
Tasks: OP‑04 (AI semantic checks at review) → OP‑05 (criticals into the remediation loop).

**N3 — Brownfield onboarding: accessibility posture.**
Goal: when an existing app is imported, record where it stands on accessibility and hand its screen list to the QA baseline audit.
Tasks: OP‑06 (posture assessment) → OP‑07 (optional gap‑fill of the spec).

**N4 — The two brownfield end‑to‑end flows.**
Goal: wire the pieces into "remediate an existing app to WCAG" and "keep building it accessibly".
Tasks: OP‑08 (remediation campaign) and OP‑09 (hold new work to WCAG 2.2).

> **N1, N2, N3 are independent of each other** — each only needs the QA engine — so three people can take one milestone each. **N4 comes last** because it composes the others.

---

## Dependency map (what must be `🟢` before what)

```
(QA plan complete — QA-03, QA-04, QA-06, QA-08, QA-11b, QA-12a, QA-15, QA-18 available)

N1 DESIGN                              N2 REVIEW                           N3 ONBOARDING
  QA-04 ──────► OP-01 ──► OP-07*         QA-03, QA-11b ──► OP-04 ──► OP-05    QA-04 ──► OP-06 ──► OP-07
  QA-03, QA-11b ──► OP-02                                                     OP-06 feeds ► QA-17 (QA plan)
  QA-08, OP-02 ──► OP-03

N4 COMPOSITIONS
  QA-18, OP-05 ──────────► OP-08   (remediate an onboarded app)
  OP-03, OP-05, QA-15 ───► OP-09   (keep building it accessibly)

* OP-07 needs both OP-01 and OP-06.
```

## Critical path (the chain that sets the timeline)
**QA‑04 → OP‑01 → OP‑07** and **OP‑04 → OP‑05 → OP‑08 / OP‑09** are the two longest chains. In practice OP‑05 (criticals into the loop) and OP‑03 (design gate) are the prerequisites that unlock the N4 compositions, so protect those.

## What can run in parallel
- **N1, N2, N3** run fully in parallel once the QA engine is `🟢`.
- Within N1, **OP‑02** (AI design checks) can be built alongside **OP‑01** (spec to 2.2); **OP‑03** needs both OP‑02 and QA‑08.
- **OP‑06** should be prioritised early because the QA plan's brownfield audit (QA‑17) consumes its route list.

---

## Definition of Done (every task)
Same binary checklist as the QA plan: behaviour matches the Description; every Acceptance Criterion demonstrated; tests + **≥ 90% coverage** + RLS where relevant; lint/type‑check green; agent‑file edits pass the reference sweep; AI never asserts conformance alone; box ticked `🟢` with a one‑line note. **Additionally:** every design/review finding must cite the same WCAG 2.2 criterion the QA phase uses (one criterion registry, QA‑05) — no divergence between phases.

---

## Cross‑references
- **What the research got wrong about the platform (read first):** `RESEARCH_CORRECTIONS.md`.
- **Task detail (read before building any task):** `TASK_BACKLOG_OTHER_PHASES.md`.
- **The QA engine this depends on (build first):** `BUILD_PLAN_QA.md` / `TASK_BACKLOG_QA.md`.
- **The user journeys these serve:** `USER_JOURNEYS.md` (J2, J3, J5‑onboarding, J6, J7).
