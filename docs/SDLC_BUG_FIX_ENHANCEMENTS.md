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
- **S.No 183** (artifact registration has no natural-key idempotency) was held here, and S.No 182
  shipped ahead of it because losing three hours of a security scan was the worse outcome.
  **Update 2026-09-15: fixed in `4ac75f9` (P2/P3 batch, below).** `register_artifact` now counts
  versions by a stable id taken from the artifact's pointer (`external_ref`) — `identity`, then
  `finding_id`/`id` for security findings, `tc_id`/`id` for test cases — and only falls back to
  the title when no such id is present. A re-run that re-words a title no longer creates a
  duplicate (`mcp_platform_state/tools.py`, `_IDENTITY_REF_KEYS`).
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
  as fixed. **Update 2026-09-15:** the header now carries a dated status note (fixed in `e70fd9e`;
  S.No 132 fixed in `4ac75f9`).
- Roughly a dozen Bugs.xlsx rows record work that is already done (S.No 181, 189, 104, 81, 197
  among them), plus brownfield S4-10 and S4-25 and one QA audit case.
- `multi_project_recon.md` §2.6 overstates its finding: the track *is* read, at `tools.py:175`.

---
---

# P2 batch — same branch (2026-09-07)

**Status:** all ten waves built and **merged into `develop`** at `eab96e9` (`--no-ff`); **all three
migrations applied** to the shared database by the team; **the team's own live pass is still to
come — that is the only thing outstanding.** **Scope as agreed:** the P2 rows the team selected
from Bugs.xlsx, in ten waves, one commit each. Per-item detail is in the Bugs.xlsx rows; this is
the batch view.

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

### After the merge

Two passes ran once the batch was on `develop`. Both are recorded here rather than folded into the
table above, because neither was part of the approved scope and the distinction matters when
somebody asks later what the team actually signed off.

| What | Why it happened | Commit |
|---|---|---|
| A person with several roles on one project could not decide a gate, and appeared once per role in the project switcher | Fixed before QA pulled, at the team's instruction. Found during this batch's browser passes, originally reported as "not fixed" below | `a665757` |
| A backend test broken by Wave 5, and a format declaration that never reached the platform | Found by a full cross-verification of the batch after the merge — see **What the cross-verification found** below | `2723f7c` |
| A cancelled work item was still exported to Jira as a new ticket | The third cross-verification finding. Raised as a product call because Wave 3 exists to be *less* restrictive; team chose to skip cancelled items | this commit |

**The P2 batch closes here** (8 Sep 2026). Everything above is built, merged, migrated and
verified; the team's live pass is the only step outstanding, and it does not gate the next set of
work.

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
- **A cancelled work item is never exported to the tracker** (8 Sep 2026). Cancelled means "not
  happening", so a tracker should not be told about it. Only `cancelled` is excluded — `done` work
  with no ticket is still exportable, which is the whole point of S.No 237.

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
- **S.No 88 does NOT need the webhook configured.** `integrations_webhookdelivery` holds **zero
  rows** against 214 runs — the GitHub webhook has never delivered anything, and the platform has
  never needed it, because it merges its own pull requests. The **sweep** is the whole mechanism
  and it needs no configuration: it runs when anyone opens the Gates screen, over the same
  connection that already opens the pull requests. Configuring the webhook would change *seconds*
  versus *within the hour*, at the price of a public endpoint and a shared secret. **Team decision,
  7 Sep 2026: don't.** Revisit only if merging by hand becomes routine. The sweep is also the only
  thing that will recover the run stranded today; no webhook fires retroactively.
- Everything else is covered by test: **503 frontend tests** and the backend files run per wave,
  plus the post-merge cross-verification below. Waves 1–9 were also driven in a browser against a
  local stack with seeded data.

## Migrations — DONE

All three were applied to the shared database by the team on 7 Sep 2026, **before** the merge, and
verified afterwards (`showmigrations` reports `[X]` for each). Nothing here is outstanding; it is
kept as the record of what was run and what to watch for if it is ever replayed on another database.

```bash
docker compose run --rm backend python manage.py migrate projects   # 0013  ✅ applied
docker compose run --rm backend python manage.py migrate gates      # 0004  ✅ applied
docker compose run --rm backend python manage.py migrate workitems  # 0007  ✅ applied
```

- **`projects/0013` will FAIL if two projects already share a name.** It applied cleanly, which is
  itself the proof that no workspace had a clash. On any other database, run the pre-check as the
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

## Found while working, then fixed at the team's instruction (`a665757`)

Both were reported here as "not fixed" and the team asked for them before QA pulled. Both had one
root cause: **memberships are stored one row per role, and the frontend read them as one row per
project.** The question now lives in one place — the auth context exposes every role held on the
selected project and a `hasRole()` that honours the workspace-admin override, matching what
`decide_gate` already did on the server — so comparing a single role anywhere is now the thing that
looks wrong.

- **A person with several roles on one project only ever got the first one.** A tech lead who is
  also product owner was told *"you don't hold the tech_lead role"* and shown a disabled Approve —
  **on a gate the server would have accepted**, because `decide_gate` checks every one of their
  rows. A locked door with no lock in it: a UI lockout, never an authorisation failure. Sweeping for
  the pattern found **a second copy** on the contracts/drift screen that nobody had met yet.
- **The project switcher listed the same project once per role** — three roles, three identical
  entries, and a duplicate-key warning on every render.

## What the cross-verification found (7 Sep 2026)

A full read of all ten waves against this plan, plus 572 backend tests over 19 files, 503 frontend
tests, typecheck, eslint and ruff. Nine waves were clean. Three things were not, and the first two
are fixed in this commit.

- **A backend test broken by Wave 5, failing on `develop`.** Wave 5's "one project name per
  workspace" rule is correct and working. An older test's helper named its project after the
  workspace — *"B-proj"* — and the test calls that helper **twice for workspace B**; it wanted two
  clarifications, not two projects, and the new rule rightly refused the second. **The product was
  right and the test was wrong**, so the fix is the test.
  **Why it was missed, and the lesson:** each wave was verified against *its own* named test files,
  and this file belongs to no wave. **A database constraint is global — it can break any fixture in
  the suite, not only the files the wave touched.** When a wave adds a constraint, unique index or
  NOT NULL, grep the whole test tree for fixtures that would violate it and run those files too.
- **A declaration two agents were told to make, that never arrived.** Wave 1 gave the platform two
  ways to know what a file is: recognise it, or let the agent declare it. Recognition works — that
  is why the SBOM renders, and S.No 187's actual symptom was genuinely fixed. **The declaration half
  was never wired to the agent-facing tool.** `mcp_platform_state/server.py` did not list `format`
  among the arguments it accepts, and FastMCP **silently discards** anything missing from a tool's
  signature — no error, no warning, the declaration simply gone. Meanwhile agents 04 and 10 had both
  been told to pass it. Harmless for JSON, which is recognised anyway; **not** harmless for YAML and
  CSV, which the platform deliberately refuses to guess at (a markdown document full of `Key: value`
  lines parses as valid YAML), so a declared-but-discarded YAML body still rendered as the wall of
  text S.No 187 was about. One parameter, passed through. The regression test goes through the tool
  **an agent actually calls**, because the existing test called the function behind it and passed
  either way — which is exactly how this survived.
- **Two waves that disagreed — raised as a product call, decided, now fixed.** Wave 3 made every
  backlog item exportable to Jira whatever state it is in, because "being worked on is not a reason
  to be untracked." Wave 9 then added a state meaning "we decided not to do this." Nobody reconciled
  them, so on the next task-breakdown export a **cancelled** story with no Jira issue got a brand
  new one created — the platform filing a ticket for work the team had just taken off its own board,
  landing in the sprint backlog looking like any other new ticket, ready for somebody to pick up.
  **Team decision, 8 Sep 2026: skip cancelled items entirely** (option A of three offered).
  `reconcile_backlog`'s candidate query now excludes them.
  **`cancelled` only, deliberately not `TERMINAL_STATES`:** excluding `done` as well would undo
  S.No 237, since finished work with no tracker id is exactly what could never be exported before.

## Worth knowing before testing

- **Cancelling cannot be undone.** Not in the UI and not through the API — `ALLOWED_TRANSITIONS`
  gives a cancelled item nowhere to go. That is deliberate (reopening restarts gates and reporting,
  and was judged a separate decision with separate consequences), but a tester who cancels an item
  cannot put it back without a database edit.

## Found while working, reported, not fixed

- **Cancelling an item that was already exported leaves its tracker ticket open**, and nothing in
  the platform closes it. The 8 Sep fix stops NEW tickets being created for cancelled work; this is
  the other half, and it is a different problem with a different risk — closing a ticket means the
  platform **writing** to a system of record on its own initiative, which needs a gate under
  non-negotiable #5, not a one-line filter. Logged rather than folded in.
- **"Set default" on the Repositories screen does nothing.** There is no endpoint behind it yet.
  **Correction and update 2026-09-15:** the endpoint did exist (`set_default_repository`, behind
  the project's repositories API); the screen was not using it properly. **Fixed in `4ac75f9`
  (S.No 212):** Set default works and the default marker moves to the chosen row.
- **The Jira reconciler matches an existing issue by exact title**, so two work items with identical
  titles would both adopt the same issue (S.No 236).

---
---

# P2 / P3 batch — same branch (2026-09-11), commit `4ac75f9`

**Status:** built and committed; **all three migrations applied** to the shared database on
11 Sep 2026 (verified). **Scope as agreed:** 16 Bugs.xlsx rows plus "Show the whole registry", each
screen built as the team chose from the mockup pack. Per-item detail is in the Bugs.xlsx rows; this
is the batch view.

## What shipped — screens

| Row | What was wrong | What it does now |
|---|---|---|
| S.No 117 | Work items nothing had run on sat in the first phase column, and a card never said what its phase was doing | A new **Backlog** column holds them; code-review tasks land in **Review**; every card has a status pill (Not started, Running, Waiting for you, Done, Failed). The API adds `run_status` to each card |
| S.No 166 | Dropdowns and the Work Items row menu were cut off by the panel they opened in | Every popup is drawn above the page (a shared floating layer) and flips upwards near the bottom of the window |
| S.No 184 | Long clarification answer options overflowed the card | The answer dropdown is drawn by the app, so long options wrap inside the card; keyboard use and the "something else" box are unchanged |
| S.No 212 | Repositories: Set default did nothing, and refusals showed internal role names | Set default works and the marker moves; the topology shown is the platform's; the add form closes; refusals read "Only a tech lead or an admin can …" |
| S.No 218 | A document waiting at a gate showed a machine word, and a rejected build left its code waiting forever | Opening a gate marks its documents "Waiting for approval" on the Artifacts list, the preview and the traceability map; the preview says either "can't be found" or "preview unavailable", whichever is true; a rejected build supersedes its drafts |
| S.No 222, N2 | The needs-you tiles listed every pending gate and question, whoever they were for, and counted a list cut at 20 | The tiles count only what the reader can act on (the same rules as the Approve and Answer buttons), with true totals (`needs_me.counts`) and "N waiting on you". The bell opens the Needs-me queue |
| S.No 225 | An unknown admin address landed on a developer placeholder page | It goes to Users & invitations; the placeholder page is deleted |
| N1 | The Integrations grid showed Code intelligence as a card nobody could act on, and a real workspace could have no connection behind it | The card is removed. Code intelligence is now set up automatically for every workspace (like accessibility); old links to it go back to the grid |
| S.No 215 | A new test case did not appear until the page was reloaded | It appears straight away, and "Generating..." updates by itself |
| — | "Show the whole registry" left the filter a gate's Preview link had set | It clears that filter |

## What shipped — behind the scenes

| Row | What it does now |
|---|---|
| S.No 85 | The Testing agent (09) is **planning-only**: it writes the test plan and test cases and hands them to Test Automation (09b), which writes, runs and reports the tests. 09 never registers a `test_report`; 09b's run produces the only one |
| S.No 132 | The GitHub `sdlc/build` check now finishes as success or failure instead of staying pending forever |
| S.No 178 | The security gate cannot be approved while any Critical or High finding is open. The platform checks this itself when someone decides the gate (`apps/gates/securitygate.py`) |
| S.No 183 | Re-runs version documents by their stable id (from the pointer) before the title, so reworded titles no longer create duplicates |
| S.No 224 | "Published this week" counts by the date a document was **published** (new `published_at`), not the date it was drafted |
| S.No 230 | The agent briefing only shows events from its own project, and questions only from its own work item |

Also fixed along the way: a webhook crash on pull-request numbers, a resumed run's events never
refreshing, and refusal messages that showed the internal role name.

## Migrations — DONE

All three were applied to the shared database on **11 Sep 2026** and verified.

```bash
docker compose run --rm backend python manage.py migrate registry       # 0008_artifact_published_at          ✅ applied
docker compose run --rm backend python manage.py migrate ledger         # 0003_event_project_and_work_item    ✅ applied
docker compose run --rm backend python manage.py migrate integrations   # 0011_codeintel_autoprovision        ✅ applied
```

- **`registry/0008`** adds the publish date and fills it in for documents already published.
- **`ledger/0003`** adds the project and work-item columns to events, so a briefing can be scoped.
- **`integrations/0011`** gives every existing workspace the built-in Code intelligence connection.
  It skips workspaces that already have one, so it is safe to re-run.

---
---

# Nine follow-ups (2026-09-12), commit `b40c557`

**Status:** built and committed. **No migrations.** Each item was built as the team chose from the
mockups.

| Ref | What was wrong | What it does now |
|---|---|---|
| E1 | A work-item title too long for the picker was cut off with no way to read it | The row opens out over itself showing the whole title — on hover and on arrow-key highlight, and only when the text is really cut. Fixed in the shared dropdown, so the two history filters get it too |
| F1 | The Roles & memberships warning about roles nobody holds could never appear (it needed "no admin could approve", and only an admin can open the page) | It shows whenever a gate role is empty, in one line: it names the roles while one or two are missing and counts them beyond that (option B+) |
| F2 | Project profile: Save stopped silently while the description was empty | The field is marked required; Save says why and puts the cursor there; other typed fields stay. The server applies the same rule: a blank description returns 400 "A description is required — agents rely on it for every phase." |
| F3 | The board said "Waiting for you" on every pending gate and question | Only on gates this person may decide and questions they may answer (same rules as the Approve and Answer buttons). Other waiting work shows in grey as "Waiting for review" / "Waiting for an answer". The API adds `needs.yours` to each card |
| N | Filter boxes on Work Items and Artifacts cut their choice off | They size themselves to their longest choice (`.select--fit`) |
| P1 | Phases & Runs named one work item three different ways | All three places read "WI-159 · title" |
| P2 | The dashboard queue named its work by database id | Each row carries `work_item_key` and `work_item_title`; a run row says how long it has been going (`started_s`) |
| P3 | Traceability had no filters on the client's screen (only in the developer gallery, with an invented "WI-492") | The map filters by phase and type and can highlight one work item's chain, dimming the rest; documents adopted during onboarding are a group of their own, "Not tied to a work item". Each node now carries `work_item`, `work_item_key`, `work_item_title`. The dead gallery controls are deleted |
| P4 | Roles & memberships had a dead project dropdown beside the title | It is a plain line of text |

Found in passing: two runs created in the same clock tick left "the item's latest run" undefined,
so a card could take either run's phase and status. The query now has a stable tie-break.

---

# Screen Words Sweep (2026-09-18 and 2026-09-21), commits `014e4b7` and the follow-up

**Status:** built and committed. **No migrations.** Unit tests pass; **the live check is QA's** —
their rows are in `docs/qa/QA_Bug_Fix_Testing.xlsx`, combined with the P2/P3 batches' pass
(team decision 2026-09-21), so QA tests once.

**The rule behind all of it:** a client never reads a stored value, an internal key, an id or a
developer's sentence. One shared list of labels (`frontend/src/labels.ts`, `backend/apps/labels.py`)
is the only place a stored value becomes a word, and `backend/tests/test_refusal_wording.py` fails
on any new server refusal that breaks the rule.

| Group | Row | What it does now |
|---|---|---|
| 1 · Gate checklist | S.No 270 | **On hold** (team, 2026-09-21). Logged as open. |
| 1b · Counter sentence | S.No 271 | **On hold**, to be decided together with group 1. Logged as open. |
| 2 · Publish page | S.No 272 | Status in the Artifacts list's words; "Open its gate" opens this document's gate |
| 3 · Role names | S.No 273 | Every role named from the shared list |
| 4 · Stored values | S.No 274 | Every status, phase, drift kind, repository role and type through the shared map. **Option A**: the run console's engine line stays, as product + model |
| 5 · Server messages | S.No 275 | ~60 refusals rewritten; detail to the log; the wording check guards new ones |
| 6 · Silent failures | S.No 276 | Profile save, invitation and login-when-down each say what happened |
| 7 · Hidden screens | S.No 277 | **Option A.** Repositories links to Contracts & drift (split / multi-repo only); a completed or approved run links to its transcript; the pre-4.8 app tree (`App.tsx` + 7 components under `components/`) is deleted — nothing imported it since the app moved to `routes.tsx` |
| 8 · Accessibility product | S.No 278 | **Included in this batch.** Same rules for the pages list, audit, review, journeys and conformance statement; the wording check covers those modules |
| 9 · Where a story belongs | S.No 279 | **Option A: a story is a planning item.** The code was right; `UX_JOURNEYS_AND_IA_SPEC.md` §6.0, `SCREEN_INVENTORY.md` S-15/S-16 and `SCREEN_BUILD_MAP.md` were corrected. Rail headings read "Lifecycle — Planning" / "Lifecycle — Delivery" |
| Truncation T9 + T13 | S.No 280 | Answered clarifications replayed once each, newest first (`truncation_issues_resolve.md`) |

## Decisions the team took, so they are not re-opened

- **Companion messages stay technical (option A).** The ~32 refusals in `api/runner_views.py` are read
  by the companion program and the agent inside it — several are instructions to the agent — and by
  the developer running it. They are deliberately outside the wording check; the reason is written
  at the top of `test_refusal_wording.py`. The same applies to `apps/a11y/journey.py`'s raises,
  which answer the agent through its MCP tools, and `apps/a11y/policy.py`, which names the policy
  file's own settings to the admin who wrote it.
- **Design gallery drift: leave, and record.** The three differences in
  `docs/design/reviews/2026-09-17-post-P2-P3-gallery-drift.md` (the side menu, the gate panel's
  third button, the registry's five statuses) and the three screens a person compared (S-06, S-11,
  S-14 — the team confirmed they have drifted) are recorded there. The mockups were **not** edited:
  they are the approval record.

## Tracked task — 26 backend tests that fail on the committed code

**Owner: the team, later.** Not caused by this batch: each was checked against the commit before
it and fails there the same way. Re-verified on 2026-09-21 after pulling `7346321`: these
22 still fail, and the other tests in the same files that were run alongside them pass.

> ⚠️ **Read before running any of these.** The three journey tests and the five
> `test_orchestration_activities` tests **connect to Temporal for real**. The repo's `.env` points
> `TEMPORAL_HOST` at the server shared with the whole team, so running them as they are would start
> real workflows there. Run them only with `TEMPORAL_HOST=localhost:1` (a dead port), which is how
> they were checked here. The setting is `TEMPORAL_HOST`, not `TEMPORAL_ADDRESS`.

| Tests | How they fail | Likely cause (not investigated) |
|---|---|---|
| `test_journey_brownfield` ×2, `test_journey_greenfield::test_trigger_creates_run` | Cannot connect to Temporal | They trigger a phase without patching the workflow starter. **A safety fix, not just a red test** — see the warning above |
| `test_orchestration_activities` ×5 (retrigger / revision / conversation) | Cannot connect to Temporal | Same: the retrigger path starts a workflow and the tests do not inject a fake. May also hide a real change in how a revision run is started — worth a look, not a guess |
| `test_acceptance_phase1` ×3 | `Artifact has no body to export`; `IndexError`; `register_atlassian() got an unexpected keyword argument 'docstore'` | Written against an older connector-registration signature and a stored body that is not there (the greenfield one is the S3 `NoSuchKey` seen earlier — needs someone with bucket access) |
| `test_acceptance_phase3` ×1 | Expected gate conditions `['no_blocking_test_failures']`, got a longer list | An accessibility gate condition was added later and the test was never updated |
| `test_acceptance_phase45` ×3 | `WriteCompletenessError` (run registered no artifacts); `403 == 202`; `'stalled' == FAILED` | Written before the write-completeness check, the anonymous-endpoint authorization (S.No 214) and the "stalled" status |
| `test_acceptance_phase47::test_p47_acceptance_slice` | `WriteCompletenessError` | Same as above |
| `test_a11y_defects::test_exactly_one_gate_reads_these_defects` | Found `a11ygate.py` **and** `securitygate.py` | A source-scan assertion that predates the security gate |
| `test_companion_runner` ×2 | Fake transport takes 3 arguments, now called with 4 | `state_client` gained a parameter; the fakes did not |
| `test_guardrails::test_run_build_clean_change_reports_ok` | `git push -u origin` failed: no `origin` | Depends on the machine's clone having an `origin` remote |
| `test_a11y_axe_execution` (line 61) | Expects "Level A failure is `Critical`" in the Testing agent's instructions | The agent text was reworded in `db3be69` (WCAG 2.2 sweep) and the test was not; this batch changed no agent file |
| ~~`test_security_phase::test_classify_phase_failure_maps_bare_exit_code`~~ | **Fixed 2026-09-21** with the agent-run wording change — it now checks the new sentence | — |
| **Added 2026-09-21** — `test_build_workflow` ×3 (merge conflict re-opens the gate; merge error parks then resumes; parked build abandons) | Two time out waiting for the park; one raises `SynchronousOnlyOperation` (a database read from async code in the test's `_run_status`) | The park tests' 20-second poll may be shorter than the merge retry policy. Same result on `f870dea`, before the dev's commits |
| **Added 2026-09-21** — `test_acceptance_slice::test_phase0_acceptance_slice` | `WriteCompletenessError` — "gate never opened" | Same cause as the phase 4.5 / 4.7 acceptance tests above. It used to hang (see below), so this failure was never seen |
| **Added 2026-09-21** — `test_acceptance_phase2::test_acceptance_build_slice_two_repos` | `git push -u origin` failed: no `origin` | Same machine dependency as the guardrails test |

**How the build-workflow tests are run.** They need a **local** Temporal (`docker compose up -d
temporal`) and skip without one, which is why the three above went unnoticed. Until 2026-09-21 they
also hung: `backend/conftest.py` turns the gate-decision signal into a no-op in every test, so an
approved merge gate never reached the workflow. `test_build_workflow.py` now restores the real
signal for its own tests only (pointed at the local server, never the shared one), and gained
`test_build_workflow_a_review_that_never_ran_parks_then_resumes_only_the_review` for S.No 266.

**Flaky, not failing** (pass on rerun): `test_a11y_scope_rest` line 405 (below); the companion's
`test_the_engine_log_captures…` (failed once, only when run beside other files — order-dependent);
and `test_build_workflow_request_changes_revises_in_place_then_merges`, which timed out into
"takeover" once under load and passes on its own.

**The same hang, in four more places, fixed the same way.** `test_gate_service`'s real-signal
test and the live acceptance tests (`test_acceptance_phase2` two-repo slice,
`test_acceptance_slice`, `test_acceptance_phase3` live WCAG gate) approve gates through
`decide_gate` and hung whenever a local Temporal was up. `conftest.py` now offers an OPT-IN
`real_gate_signal` fixture; each of those tests — and `test_build_workflow.py` — opts in
individually, and every one of them points Temporal at the LOCAL server first. Nothing opts in
file-wide, so no other test can reach a Temporal server this way.

## Also found, not fixed

- **59 older ruff findings elsewhere in the backend** (`ruff check .` from `backend/`). The four the
  team asked for (`Gates.tsx:120`, three in `api/views.py`) and those in
  `tests/test_frontend_integration.py` are fixed; the rest are in files this batch did not touch.
- **`test_a11y_scope_rest::…older audit…` (line 405) is flaky**: it failed once in a 12-minute run
  and passed on two reruns. Two audits created in the same clock tick make "the newest" ambiguous —
  the same class as the board's tie-break fixed in `b40c557`.
- **The accessibility judge's failure reason was left as it is.** It carries the raw cause
  ("temporal is down") into the audit report on purpose — `test_a11y_report*` pin that the report
  says *why* — and it was outside group 8's approved scope.

## Run-console failure wording (2026-09-21, S.No 281) — team chose option A

Found while reviewing the dev's S.No 266 commit (`44ac215`), and on two screenshots the team shared.
`classify_build_failure` now returns a plain sentence and a short cause (`describe_build_failure`):
a rejected token (401), a usage or **session** limit with its reset time, an engine that closed
early, and a review with no reason each read as the approved sentence, and a stopped **review** is
named as the review — decided by the step being resumed (`run_code_review`), not by the message's
words. A failed (not paused) run is never told to Resume. The raw text is stored as
`outputs.error_detail` and shown under a closed "Technical details"; `outputs.kept` says what a
paused build keeps. **Agent runs, same day (team: "apply the same fix to the agent runs too").**
`classify_phase_failure` now uses the same sentences, naming the phase ("The PRD phase stopped
because the AI engine reached its usage limit (resets 1:20 AM, Asia/Kolkata). Resume once the limit
resets."). All three agent-run paths store `error_detail` for "Technical details" — including the
**park path, which had stored its reason exactly as raised, never rewritten at all**. Log lines
read "Run paused — stopped: …" and "Run failed — …".
