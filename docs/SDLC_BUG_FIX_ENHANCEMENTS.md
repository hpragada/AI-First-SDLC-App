# Bug-fix batch — `SDLC_Bug_Fix_Enhancements` (2026-09-03)

**Status:** built and pushed; one migration outstanding; two items need a live run to confirm.
**Branch:** `SDLC_Bug_Fix_Enhancements`, cut from `develop` at `04e204f`.
**Scope as agreed:** the eight P1 defects, plus the platform-wide "a link drops its context"
problem the team widened (referred to below as **N2** — it has no Bugs.xlsx row; this document is
its record).

Per-item detail lives where it belongs: Bugs.xlsx rows carry the fix text, and
`truncation_issues_resolve.md` carries T2's build note. This file is the batch view — what shipped
together, what was deliberately held, and what is not yet proven.

---

## What shipped

| Item | Row | Ships as |
|---|---|---|
| Nine anonymous write endpoints | S.No 214 | Two-layer authorization — see [ADR 0004](decisions/0004-authorization-membership-not-role.md) |
| Failed request renders as an empty workspace | S.No 220 | Shared `ErrorState` primitive on five screens |
| Engine exit is terminal for planning/scan phases | S.No 182 | `AgentRunWorkflow` parks and re-dispatches |
| Security phase runs no real scanner | S.No 185 | Egress declaration + provisioning + honesty |
| Security report overstates what ran | S.No 186 | Scan Provenance table in agent 10 |
| Acceptance criterion dropped and passed | S.No 243 | Per-criterion verdict contract, failing closed |
| Work-item description silently cut | T2 | Description rendered outside the token cap |
| Six agents write for engineers | S.No 121-126 | Writing / clarity standards with worked examples |
| A link's text is a promise | **N2** | See below |

---

## N2 — the link that drops its context

Recorded here because it is not in Bugs.xlsx. The team spotted one instance on the Gates screen and
asked for the blast radius widened; it turned out to be roughly **fifty navigations across ~20
files**, and it is a conformance gap against a signed-off spec rather than a new requirement —
`UX_JOURNEYS_AND_IA_SPEC.md:247` already specifies that a gate carries "a link to preview the
artifact under review" (J19), and `:304` that a traceability node deep-links. The preview endpoint
was built and signed off. The link to it never was.

**The convention, now in `frontend/src/links.ts`:**

> A link's text is a promise. If the id of the thing promised is in hand, link to its **detail
> route**. If only a *scope* is in hand (a run, a work item, a phase, a type), link to the **list
> route carrying that scope as a query param**, and the list must honour it. Never link to a bare
> list from text that names one thing.

**Four instances were worse than landing on a list:**

1. **A dead link.** `OnboardingHub` linked to `/gates/:id`, a route that does not exist, so the
   catch-all bounced the user to the Dashboard without a word — the primary action on a *blocking*
   onboarding step went nowhere.
2. **Twelve links opened a different item than the one clicked**, because `/gates` and
   `/clarifications` select `pending[0]`. Clicking "Answer" beside a question you have just read
   could open a different question, which invites the wrong answer into the wrong box.
3. **`/recovery?run=` was a dead end at both ends** — nothing produced the URL, and the destination
   forced the run to `undefined` whenever the param was present and then said "No parked runs".
4. **Five screens were built and reachable by nobody.**

### The vocabulary trap — read this before touching artifact filters

`Approval.phase` returns the **agent key** (`06_task_breakdown`) and the phase-specific gate panels
depend on that. `Artifact.phase` stores the catalog's **phase label** (`task_breakdown`). So
`/artifacts?phase=<approval.phase>` returns **zero rows** — a silent empty list, worse than the
wrong-but-populated one it replaces.

The client-side workaround was to strip the `NN_` prefix. Measured across the catalog that is right
for 10 of the 11 agents and **wrong for `00c_intelligent_context_extractor`**, whose label is
`context_extraction` — which is exactly what makes it dangerous. Rather than fix the heuristic, the
platform now serves the fact: `ApprovalSerializer.phase_label`, mirroring
`RunSerializer.get_agent_phase`. `phase` is unchanged.

### Rules that must survive a later refactor

- **`latest` is off when a run scope is present.** A run-scoped view is a *provenance* view; `v1`
  belongs in it. With `latest` on, a deep link into the run that produced v1 finds nothing as soon
  as a later run makes v2. Pinned by a test, because it is the first thing a refactor will undo.
- **A stale deep link selects nothing and says so.** Falling back to the first pending item would
  re-introduce the original bug one level down. On the accessibility queue this matters more than
  elsewhere: opening a finding *claims* it server-side for 15 minutes.
- **`artifactsForPhase` takes a phase LABEL, never an agent key.** Two `string`s are
  indistinguishable to the type system, so the parameter name and its comment are the only guard.

### Why `/gates/:id` is a redirect, not a screen

The Gates screen holds the selection state and every phase-specific panel. A real detail screen
would mean extracting that JSX and would create a **third** gate-decision UI (`CriteriaGate` is
already a second, partial one) — exactly the drift this pass removes. It would also discard the
master-detail layout, and a reviewer with five pending gates wants to see the other four. The
redirect exists so URLs already in the wild resolve.

### Two guards, because they cover different moments

All 40 raw `<a href="/…">` are now `<Link>`; each was a full page reload that dropped the SPA's
state. `GapReportScreen.tsx` carries a comment saying this exact bug was found and fixed once, in
that one file — it came back in eight others.

- an **ESLint rule** (`no-restricted-syntax`, no new dependency) for the editor, and
- a **vitest source scan** (`src/noRawAnchors.test.ts`), because nothing runs ESLint automatically:
  `make lint` executes ruff and mypy only — it names eslint in its own doc comment and never
  invokes it — and the repo has no CI. `npm test` is the only guard that will actually run.

---

## Deliberately held

- **`POST /api/runners/` stays open to anonymous callers.** Gating it breaks the documented CLI
  onboarding, which has no session to present. Recorded against **S.No 35** with its three siblings;
  see ADR 0004.
- **S.No 183** (artifact registration has no natural-key idempotency) is untouched. It means a
  resumed planning run can register a second version of what the failed run produced. Untidy, not
  corrupting — `register_artifact` versions rather than duplicates. Losing three hours of a security
  scan was the worse outcome, so S.No 182 shipped ahead of it.
- **`/a11y/finding/:findingId`** is built and still has no inbound link. There is no findings list
  in the UI to link it from, so where it belongs is a product decision.

## Not yet proven

- **S.No 185 parts A and B** need one live security run on a project that declares
  `scan.registries`, to confirm the report carries a real Bandit exit status. Part C (the honesty
  half) needs nothing and is already in effect.
- Everything else is covered by test: 449 frontend tests, and the backend files run individually.

## Before this runs anywhere

```bash
docker compose run --rm backend python manage.py migrate projects
```

Adds `ProjectProfile.scan` (`projects/0012`). Safe to run in any order relative to any branch — see
[ADR 0003](decisions/0003-additive-columns-keep-a-database-default.md) for why that is a property of
the migration and not a scheduling habit.

## Still stale, and not touched by this batch

Found during the inventory that preceded this work, reported, and **not** actioned — the team scoped
today to P1 + N2:

- `TESTING_PHASE_BUGS_HANDOFF.md` header still says `**Status:** open`; all four bugs in it verify
  as fixed.
- Roughly a dozen Bugs.xlsx rows record work that is already done (S.No 181, 189, 104, 81, 197
  among them), plus brownfield S4-10 and S4-25 and one QA audit case.
- `multi_project_recon.md` §2.6 overstates its finding: the track *is* read, at `tools.py:175`.
