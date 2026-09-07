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

---
---

# P2 batch — same branch (2026-09-07)

**Status:** all ten waves built; three migrations outstanding; the team's own live pass is still to
come. **Scope as agreed:** the P2 rows the team selected from Bugs.xlsx, in ten waves, one commit
each. Per-item detail is in the Bugs.xlsx rows; this is the batch view.

## What shipped

| Wave | Item | Row | Ships as | Commit |
|---|---|---|---|---|
| 0 | Three rows already fixed in code | S.No 181, 189, 217 | Verification note only, no code | `dbd6fc5` |
| 1 | A bill of materials shown as a wall of text | S.No 187 | Format detection + a rendered view, preview only | `3bdb017`, `8a583b2` |
| 2 | Connect Machine showed a fake token, ignored the picker | S.No 198, 223 | Placeholder deleted; the picker is real | `76b6475` |
| 3 | A Jira pointer was never re-checked; most items could never be exported | S.No 236, 237 | Pointer validation (404-only) + candidate selection by "has no id" | `92c3d18` |
| 4 | A PR merged on GitHub stranded the platform | S.No 88 | Detect and annotate; a human still decides — [ADR 0005](decisions/0005-the-platform-observes-the-code-host-it-does-not-police-it.md) | `411d96a` |
| 5 | Two projects could share a name | S.No 211 | Case-insensitive constraint + the 409 the screen already waited for | `8355f94` |
| 6 | Actions that failed with no message | S.No 219 | One shared write-failure surface, on seven sites | `93f05d0`, `403060f` |
| 7 | A new project offered an existing-codebase wizard | S.No 221 | Project kind reaches the browser; nav gate generalised | `ae34363` |
| 8 | The build agent could move the main work item | S.No 87 | Blocklist inverted to an allowlist | `dcfb579` |
| 9 | No human way to close work that cannot be built | S.No 140 | A terminal `cancelled` state, and everything that must respect it | `41b9068`, `76de57b` |
| 10 | Connect Machine redesign | S.No 35 (+138) | [Spec only](CONNECT_MACHINE_REDESIGN_SPEC.md), by team decision | `96803a6`, `bb7cae6` |

## Decisions the team took, so they are not re-opened

- **An archived project keeps its name reserved** (S.No 211). Un-archiving a project to find its
  name taken by something else is the worse surprise.
- **Cancelling a defect releases the gate it was blocking** (S.No 140) — and the gate says so. The
  release and the disclosure ship together; releasing silently would let "we won't fix this"
  quietly become "this passed".
- **Tech lead or admin may cancel**, and cancelled items are **hidden from the board by default**
  with a filter to show them.
- **The platform observes the code host; it never polices it** (S.No 88). Detection annotates; only
  a human decides. ADR 0005 records why that matters given a globally-shared webhook secret.
- **Onboarding is hidden, not greyed out**, on a project with no code (S.No 221) — including
  `/onboarding/documents`, for now.
- **Connect Machine is specified, not built** (S.No 35), and S.No 138 is folded into it.

## Deliberately out of scope

Recorded so the scope decision is not re-litigated:

- **S.No 213** (the lifecycle rail) is **dropped from this batch.** The Work Items dashboard
  redesign will own it; fixing it here would build something that redesign then replaces.
- **Group C — S.No 75, 78, 79, 210 — is parked untouched.**
- **S.No 178** is **approved and sequenced after one live security run**, so the change is made
  against real observed output rather than an assumption about it.

## Three things I told the team that were wrong, corrected in the rows

- **S.No 88:** I said an approval on an externally-merged PR would hit GitHub's merge API, get a
  405 and park in a retry loop. It would not — the merge step already short-circuits on an
  already-merged PR and says so in its own docstring. The real bug was that nobody ever approves.
  This made the fix much smaller and safer than described.
- **S.No 87:** the row did not record that commit `83a2036` had already blocked the agent from
  setting `done`. Half of it was fixed before this batch began.
- **S.No 221:** I described project kinds as greenfield / brownfield / multi. There are **two**.
  "Multi" is a different field, about how many repositories a project has.
- **S.No 35:** the spec recorded three shared modules between the platform and the companion. There
  are **four** — code intelligence brought its own, along with a second copy of the import
  bootstrap. Corrected in `bb7cae6`; the conclusion is unchanged.

## Not yet proven

- **The team's own live pass has not happened.** Everything below was verified by me, by test and
  in a browser against a local stack; none of it has been exercised by the people who reported the
  bugs. That is the step that closes these rows in practice.
- **S.No 88 needs webhook delivery configured** — a reachable URL and `GITHUB_WEBHOOK_SECRET` — to
  work end to end. The sweep is also the only thing that will recover the run stranded today; no
  webhook fires retroactively.
- Everything else is covered by test: **499 frontend tests** and the backend files run per wave.
  Waves 1–9 were also driven in a browser against a local stack with seeded data.

## Before this runs anywhere

Three migrations, **written but not run** — the team runs them.

```bash
docker compose run --rm backend python manage.py migrate projects   # 0013
docker compose run --rm backend python manage.py migrate gates      # 0004
docker compose run --rm backend python manage.py migrate workitems  # 0007
```

- **`projects/0013` will FAIL if two projects already share a name.** Run the pre-check as the
  `postgres` owner and rename any duplicates first. Running it as the application user reports zero
  rows whether or not duplicates exist, because row-level security hides them — that is no result,
  not a clean one.
- **`gates/0004`** adds one nullable column. Safe in any order relative to any branch, for the
  reason in [ADR 0003](decisions/0003-additive-columns-keep-a-database-default.md).
- **`workitems/0007`** changes a list of allowed values only. It touches no table and the SQL it
  generates is empty, so it is safe to run at any time, including while an older release serves.

## One lesson worth keeping

`403060f` exists because of a screenshot. The test for the failed test-script message asserted it
appears, and it did — but it sat in an unbounded table cell and sprawled to the table edge, reading
as loose text rather than something attached to the button that had failed. **A passing test says
the thing is there; only looking says it is right.** Every UI wave in this batch was checked in a
browser afterwards for that reason, and doing so also turned up the two Wave 1 design deviations and
the multi-role defect below.

## Found while working, reported, not fixed

- **A person with several roles on one project only ever gets the first one.** The selected project
  is found by matching the project id, so a tech lead who is also product owner is treated as
  whichever role happens to come back first — and cannot decide a gate that requires the other.
  Pre-existing; not touched.
- **The project switcher lists the same project once per role**, for the same reason. Deduplicated
  on the Connect Machine screen (S.No 198) but not in the top bar.
- **"Set default" on the Repositories screen does nothing.** There is no endpoint behind it yet.
- **The Jira reconciler matches an existing issue by exact title**, so two work items with identical
  titles would both adopt the same issue (S.No 236).
