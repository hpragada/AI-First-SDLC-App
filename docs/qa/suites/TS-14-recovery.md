# TS-14 · Recovery & Takeover

This suite covers what happens when a run stops reporting back: the platform parks it for human
takeover instead of hanging or losing the work. It exercises the parked state in the run console,
the `/recovery` screen (reconnect, manual takeover, the empty state), the in-console
`Resume from where it stopped` path for a run paused at a resumable error, and the rule that a
parked run may be re-triggered where a live run may not. **Owner: Tester C** — every case needs a
real companion you can stop and start.

**Run these in order — the order matters more here than anywhere else in the pack.** TC-193 creates
the parked run that TC-194, TC-216 and TC-195 inspect and clear. TC-196 is deliberately placed
**after** them because it creates a permanently `FAILED` run that `/recovery` will latch onto for
the rest of the cycle. TC-197 and TC-198 cover the two parked-console variants, TC-199 and TC-217
cover the trigger guard, and TC-200 confirms the empty state — run it last, in the scratch project
it names.

**How `/recovery` picks its run — read this before TC-194.** The screen does **not** take a run
id. It renders **the first `stalled` or `failed` run in the selected project**, whichever the runs
list returns first (`frontend/src/features/observability/OfflineTakeover.tsx:28-31`). Two
consequences you must plan around:

- Keep **exactly one** stalled-or-failed run in the project while running TC-194 → TC-196. Always
  confirm the `Run` key/value row matches the run id you recorded before clicking anything.
- **`/recovery?run=<id>` is dead.** With `?run=` set the screen forces its run to undefined and
  renders `No parked runs` (`:47-56`). Never use it, and never treat that empty state as a defect
  in a case that navigated with a query parameter. There is no way to take over a *named* run;
  that is a product defect (audit Part 6, item 7), raise it once.

**Waiting on runs.** Every case below has an explicit **max wait**. Exceeding it is verdict
**Blocked** with the run id recorded — never **Fail**. A silent console is not evidence of a hang
(`docs/TESTING_PHASE_BUGS_HANDOFF.md` Bug 3).

---

### TC-193 · Stopping the companion mid-run parks the run for takeover

| Field | Value |
|---|---|
| Suite | TS-14 Recovery & Takeover |
| Type | Functional |
| Priority | Critical |
| Screen | `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Companion running in its own terminal; the sidebar pill reads `Companion: Ready`.
- Project `Payment Gateway v2` selected, epic `Stripe Webhook Integration` exists with no live run.

**Steps**
1. Go to `/runs`, select the epic, and trigger **Ideation**.
2. Open the run console for the new run and confirm it reaches `Running`.
3. In the companion's terminal, stop the process with `Ctrl-C`. Leave it stopped.
4. Watch the sidebar companion pill until it stops reporting the machine as online (the online
   window is 2 minutes).
5. Leave the run console open and reload it periodically until the report timeout elapses.
6. **Record for the rest of the suite:** the run id (from the URL), the work item, and the phase.
   TC-194, TC-216, TC-195, TC-198 and TC-199 all refer back to this run id.

**Expected**
- Before the stop, the console status badge reads `Running`.
- After the companion is stopped and the report timeout elapses, the badge changes to
  `Parked for takeover`.
- No artifact for this phase appears in `/artifacts` for the run.
- No gate for this phase appears on `/gates`.
- The run row on `/runs` no longer shows a live status.

**Pass / Fail**
- PASS if the run ends in `Parked for takeover` with no artifact and no gate created.
- FAIL if the console hangs on `Running` indefinitely, the run is marked `Completed`, or an artifact
  or gate is created from a run that never reported.

**Test data**
- Epic: `Stripe Webhook Integration` · Phase: `Ideation`

**Notes**
- **Max wait: 30 minutes** from stopping the companion to the badge reading `Parked for takeover`.
  If it is still `Running` after that, record **Blocked** with the run id.
- The park is deliberately **non-terminal** — a companion that only slept can still come back and
  reconcile the same run. That is what TC-216 tests.
- A silent console is not evidence of a hang (Bug 3). Use the Temporal UI at `:8080` only to attach
  evidence to a defect, never as the pass condition.
- Do not restart the companion until TC-194 is recorded — the parked state is the fixture for the
  next cases.
- This park is a **report timeout**, which is *not* resumable: it sets no `resumable` flag, so the
  console offers no **Resume from where it stopped** button. That is correct, and TC-198 asserts it.

---

### TC-194 · `/recovery` renders the parked run

| Field | Value |
|---|---|
| Suite | TS-14 Recovery & Takeover |
| Type | UX |
| Priority | High |
| Screen | `/recovery` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-193 passed and the Ideation run is still parked. The companion is still stopped.
- **The run from TC-193 must be the only `stalled` or `failed` run in `Payment Gateway v2`.** The
  screen picks the first one it finds; it does not take a run id. If earlier work left another
  stalled or failed run in this project, clear it first or use a fresh project — otherwise this
  case will describe the wrong run and produce a false verdict.

**Steps**
1. Go to `http://localhost:5173/recovery` — type the bare path, with **no `?run=` parameter**.
2. Read the heading, banner, key/value rows and buttons. Do not click any action.
3. Compare the `Run` key/value row against the run id you recorded in TC-193.

**Expected**
- The breadcrumb reads `Phases & Runs / Recovery`.
- The heading reads `Run recovery — Stripe Webhook Integration · Ideation`.
- The sub-heading reads `When your machine goes offline mid-run, the platform parks the run for
  takeover rather than letting it hang.`
- A danger banner titled `This run is parked for takeover` states that the run id `did not report
  back. Nothing was lost: no artifact is published, and any answered clarifications are remembered.`
- Three key/value rows are shown, labelled `Run`, `Status` and `Created`; `Status` reads `stalled`.
- The `Run` row's id **matches the run recorded in TC-193**, formatted
  `<run id> · Ideation · <work item id prefix>`.
- Three actions are present: **Reconnect & re-run**, **Take over manually**, and a
  **Connect your machine** link.
- An informational banner explains that bringing the companion back online lets it finish this same
  run, and that reconnect-and-re-run starts from a clean dispatch instead.

**Pass / Fail**
- PASS if the screen resolves the parked run, the `Run` row is the TC-193 run, the right work item
  and phase are named, and all three actions and all three Kv rows render.
- FAIL if the screen shows `No parked runs` while a parked run exists, the heading shows a raw UUID
  instead of the work item title, the `Run` row is a *different* run, or any action is missing.
- **Blocked** if more than one stalled/failed run exists in the project — the precondition was not
  met and the screen's choice is not this case's to judge.

**Test data**
- None.

**Notes**
- While the run list is loading, the panel shows `Checking for parked runs…` — that is the loading
  state, not the empty state.
- `Status` renders the raw value `stalled`. It is not title-cased on this screen; do not raise that
  as a copy defect here.
- **Do not append `?run=<id>` to reach a specific run.** With that parameter the screen renders
  `No parked runs`. The screen is project-scoped by construction; the inert `?run=` is a tracked
  product defect (audit Part 6, item 7), not something to discover here.

---

### TC-195 · `Reconnect & re-run` starts a fresh run and leaves the parked one in history

| Field | Value |
|---|---|
| Suite | TS-14 Recovery & Takeover |
| Type | Functional |
| Priority | Critical |
| Screen | `/recovery`, `/runs/:id`, `/runs` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-216 passed (or was recorded), so TC-193's park is resolved and the project has no other
  stalled or failed run.
- A **fresh** report-timeout park to act on: with the companion running, trigger **Requirements**
  on `Stripe Webhook Integration`, wait until the console reads `Running`, stop the companion with
  `Ctrl-C`, and wait for the badge to reach `Parked for takeover` (as in TC-193).
- **Record:** this parked run's id. Call it the *old* run.
- `/recovery` shows this run in its `Run` row — confirm before clicking anything.

**Steps**
1. In the companion's terminal, start it again with the same command from the plan §2.
2. Wait until the sidebar pill reads `Companion: Ready`.
3. Return to `/recovery` and reload. Re-confirm the `Run` row is the old run id.
4. Click **Reconnect & re-run**.
5. **Record:** the run id in the URL you land on. Call it the *new* run. If you are interrupted,
   **resume at step 6** with these two ids.
6. Follow the new run's console.
7. Go to `/runs`, select `Stripe Webhook Integration`, and read the Requirements run rows.

**Expected**
- While the request is in flight, the **Reconnect & re-run** button shows a spinner and both actions
  are disabled.
- No `Couldn't update takeover state` banner appears.
- The app navigates to a run console whose run id is **different from the old run id**, for the same
  work item and phase (`Run console — Requirements · … Stripe Webhook Integration`).
- The new run's badge progresses from `Dispatched · waiting` to `Running`.
- The new run reaches `Awaiting gate` and a Requirements gate appears on `/gates` (reload `/gates`
  — it does not poll).
- On `/runs`, **two** Requirements runs are listed for the epic: the old one and the new one. The
  old one is not deleted and does not silently change into the new one.

**Pass / Fail**
- PASS if a distinct new run is dispatched to the reconnected companion, reaches its gate, and the
  old parked run is still in history.
- FAIL if the button errors, no new run is created, the new run reuses the old run id, the new run
  parks immediately, or the parked run disappears from history.
- **Blocked** (not Fail) if the new run has not reached `Awaiting gate` within **30 minutes**.

**Test data**
- Epic: `Stripe Webhook Integration` · Phase: `Requirements`

**Notes**
- **Max wait: 30 minutes** to `Awaiting gate` on the new run.
- **What this case asserts, precisely:** a *new, distinct* run is dispatched and the old one is
  preserved. That is the whole observable contract of this button.
- **Do not treat a successful dispatch as proof that any "takeover flag" was released.** The button
  does clear `WorkItem.takeover_flag`, but that flag guards nothing: trigger admission is decided
  purely by run status (`backend/orchestration/trigger.py:43-57`), and the flag's only backend
  reader is the manifest renderer (`backend/manifest/composer.py:162-163`). The dispatch would
  succeed whether or not the flag was cleared, so it proves nothing about it. The inert flag is a
  tracked product defect (audit Part 6, item 6) — do not raise it here.
- If a clarification was answered on the parked run, it should not be asked again. If it is, raise it
  against TS-08 rather than here.

---

### TC-196 · Take over manually ends the parked run

| Field | Value |
|---|---|
| Suite | TS-14 Recovery & Takeover |
| Type | Functional |
| Priority | High |
| Screen | `/recovery`, `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- **Run this case second-to-last in the suite, after TC-199 and before TC-200.** It creates a
  permanently `FAILED` run, and `/recovery` surfaces `failed` runs as well as `stalled` ones — so
  from this point on, `/recovery` in this project will show *this* run forever. That is why TC-200
  uses a different project.
- A parked run to act on. Reproduce TC-193 on a **third** work item — create the story
  `Webhook Retries` on `/work-items`, trigger **Ideation**, stop the companion mid-run and wait for
  `Parked for takeover` — so TC-195's and TC-199's results are not disturbed.
- **Record:** this parked run's id, and confirm it is the id shown in `/recovery`'s `Run` row.

**Steps**
1. Go to `/recovery` and confirm the `Run` row matches the run id you recorded.
2. Click **Take over manually**.
3. Wait for the request to complete, then open `/runs/<the recorded run id>` directly.
4. Reload `/gates` and `/artifacts` and look for anything belonging to this run.
5. Go to `/runs`, select `Webhook Retries`, and confirm the run is still listed.

**Expected**
- No `Couldn't update takeover state` banner appears.
- The run console badge for that run no longer reads `Parked for takeover` — it reads `Failed`,
  because an explicit takeover ends the still-waiting run rather than leaving it hanging.
- The console shows a danger banner titled `Run failed` carrying a `Reason:` line.
- No **Resume from where it stopped** button is offered — the run is terminal.
- No artifact for that phase appears in `/artifacts` and no gate for it appears on `/gates`.
- The run stays visible in `/runs` history with its events intact.

**Pass / Fail**
- PASS if the takeover completes without an error banner and the run moves from parked to `Failed`
  without producing an artifact or a gate.
- FAIL if an error banner appears, the run stays `Parked for takeover` after a reload, the run
  disappears from history, or taking over silently publishes or gates anything.

**Test data**
- Work item: `Webhook Retries` · Phase: `Ideation`

**Notes**
- **Max wait: 2 minutes** for the takeover request itself.
- Takeover is **terminal and irreversible**. There is no button that un-fails this run; the way
  forward for the work item is a fresh trigger of the phase (TC-199 proves that is allowed).
- **Do not run `Reconnect & re-run` afterwards "to release the flag".** An earlier version of this
  case said to. It is pointless: `takeover_flag` guards nothing — trigger admission is decided
  purely by run status (`backend/orchestration/trigger.py:43-57`), and the flag's only backend
  reader is the manifest renderer. Clicking it here would just spawn an unwanted extra run. The
  inert flag is a tracked product defect (audit Part 6, item 6).
- **Consequence to plan for:** this `FAILED` run is now permanent, and `/recovery` for
  `Payment Gateway v2` will keep rendering it. Do not raise that as an empty-state defect later.

---

### TC-197 · `Resume from where it stopped` continues a run paused on an error

| Field | Value |
|---|---|
| Suite | TS-14 Recovery & Takeover |
| Type | Functional |
| Priority | High |
| Screen | `/runs/:id` |
| Persona | P5 Tech Lead |
| Automation | No |

**Preconditions**
- **This is an opportunistic case — you cannot reliably induce it, so watch for it.** A resumable
  park happens when a build-tier run fails **after** the companion has reported its build, at one
  of exactly four steps: opening the build PR, the code-review remediation loop, merging the PR
  (`backend/orchestration/build_workflow.py:205, 264, 311`), or the write-completeness check on a
  planning phase (`backend/orchestration/workflows.py:157`).
- The realistic way to meet it: run the build-tier cases (TS-15 TC-208, TS-13 TC-213) and take this
  case the first time any run shows `Parked for takeover` **with** a
  `Paused on an error — you can carry on from here` banner. Merge and PR failures are the common
  ones — a repo the companion can clone but not push to, or a branch that already has a conflicting
  PR, will produce one.
- **Record:** the parked run id before doing anything.

**Steps**
1. Open `/runs/<the parked run id>`.
2. Read the badge and the banner, and record the `Reason:` text.
3. Fix the cause outside the app if the reason names something fixable (push permissions on
   `/repositories`, a conflicting PR in the git host).
4. Click **Resume from where it stopped**.
5. Watch the console.

**Expected**
- The badge reads `Parked for takeover`.
- A warning banner titled `Paused on an error — you can carry on from here` is shown, quoting a
  concrete `Reason:` and explaining that resuming continues from the step that failed rather than
  starting the phase over.
- Two actions are present: **Resume from where it stopped** and **Take over instead**.
- After clicking resume, the button shows a spinner and no `Couldn't resume` banner appears.
- The run leaves `Parked for takeover` and continues — new console lines appear and the badge moves
  on (`Running`, then `Awaiting gate` if the phase completes).
- No second run is created for the work item — the run id in the URL is unchanged.

**Pass / Fail**
- PASS if the same run continues from the failed step, with no new run id.
- FAIL if resume spawns a fresh run, the banner or buttons are missing, or the run re-does work it
  had already completed.
- **Blocked** if no resumable park occurred anywhere in the cycle, or if the resumed run has not
  left `Parked for takeover` within **15 minutes**. Record it as Blocked with the reason
  "no resumable park observed" — do not fabricate one, and do not Fail.

**Test data**
- Work item: whichever build-tier work item actually parked · record the phase and the `Reason:`

**Notes**
- **Max wait: 15 minutes** after clicking resume for the run to leave `Parked for takeover`.
- **The previous repro in this case was wrong and has been removed.** Registering a base branch
  that does not exist does *not* produce a resumable park: the companion fails during clone /
  checkout and reports a failed build, which the workflow turns into a **terminal** `FAILED` run
  via `mark_build_failed` (`build_workflow.py:128-135`) with no resume affordance at all. An
  "empty build" is likewise terminal by design. Only the four call sites listed in the
  preconditions park resumably.
- **Take over instead** navigates to `/recovery` — check it renders as a button, but do not click
  it in this case. Note that it navigates with **no run parameter**, so `/recovery` will show
  whichever stalled-or-failed run it finds first in the project, not necessarily this one.
- A report-timeout park (TC-193) is *not* resumable and correctly shows no resume banner. TC-198
  asserts that boundary.

---

### TC-198 · A report-timeout park offers no resume action

| Field | Value |
|---|---|
| Suite | TS-14 Recovery & Takeover |
| Type | Negative |
| Priority | High |
| Screen | `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A run parked by a **report timeout** — the companion was stopped mid-run, exactly as in TC-193.
  Use TC-193's run while TC-194 still holds it, or TC-195's fresh Requirements park before you
  click **Reconnect & re-run**. This case clicks nothing destructive, so it is safe to slot into
  either window.
- **Record:** the run id being read.

**Steps**
1. Open `/runs/<the parked run id>`.
2. Read the status badge.
3. Read every banner on the panel.
4. Read every button in the actions row below the console.
5. Leave the page open for a full minute without touching it, then re-read the actions row.

**Expected**
- The status badge reads `Parked for takeover`.
- **No** banner titled `Paused on an error — you can carry on from here` is shown.
- **No** **Resume from where it stopped** button and **no** **Take over instead** button are
  rendered anywhere on the screen.
- The actions row offers no way to continue this run in place — recovery is `/recovery`
  (**Reconnect & re-run** / **Take over manually**), which TC-195 and TC-196 cover.
- After the idle minute the screen is unchanged — the console self-refreshes, and it does not
  spontaneously grow a resume affordance.

**Pass / Fail**
- PASS if a report-timeout park shows the parked badge with **no** resume banner and **no** resume
  or take-over-instead buttons.
- FAIL if a **Resume from where it stopped** button is offered on this run. Clicking it would be
  refused by the backend (`this run is not paused at a resumable error, so there is nothing to
  resume`), so offering it is a **High** severity defect: a dead control on a recovery screen.
- FAIL if the badge reads anything other than `Parked for takeover`.

**Test data**
- None.

**Notes**
- **Why this replaced the old case.** The previous TC-198 asked the tester to hold a stale parked
  view in a second tab and click resume after another tab ended the workflow. That is unreachable:
  the run console polls every 3 seconds
  (`frontend/src/features/lifecycle/hooks.ts:111-119`), so no stale view survives long enough to
  click. And after a manual takeover the backend returns a *different* message than the one the old
  case quoted — the run is `FAILED`, so it answers `this run is not paused at a resumable error…`,
  never `this run's workflow is no longer running…`. The case could not have passed as written.
- The distinction being tested is real and load-bearing: a resumable park sets a `resumable` flag on
  the run and the console keys the whole resume UI off it, while a report-timeout park sets no such
  flag (`backend/orchestration/activities.py:588-590` vs `:613`). Offering resume on the wrong kind
  of park is precisely the bug this case guards.
- The `Couldn't resume` banner itself is asserted negatively by TC-197 ("no `Couldn't resume` banner
  appears"). There is no browser-reachable way to force it, so nothing in this pack drives it
  positively — that is a documented gap, not an omission to fix by inventing a repro.

---

### TC-199 · A parked run can be re-triggered where a live run cannot

| Field | Value |
|---|---|
| Suite | TS-14 Recovery & Takeover |
| Type | Functional |
| Priority | High |
| Screen | `/runs` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A work item whose latest run is parked (`Parked for takeover`) — reproduce TC-193 if none is
  available.
- A second work item with a run currently `Running` or `Awaiting gate`.

**Steps**
1. Go to `/runs` and select the work item whose latest run is **parked**.
2. Trigger **the same phase** that parked.
3. Now select the work item whose run is **live** (`Running` / `Awaiting gate`).
4. Trigger **the same phase that is live** — not a different one. (Triggering a *different* phase
   on a live work item behaves differently; that is TC-217.)

**Expected**
- For the parked work item, the trigger is accepted: a new run row appears for that phase with
  status `Dispatched · waiting`, and no blocking modal is shown.
- For the live work item, the trigger is refused: a modal titled `{Phase} is already running` opens.
- The modal body states that the work item already has a run **in progress** for this phase and that
  a new one cannot start until it finishes.
- The modal offers **Close** and **Open current run**; **Open current run** navigates to the live
  run's console.
- No second run is created for the live work item.

**Pass / Fail**
- PASS if a parked run is re-triggerable and a live run is blocked by the modal.
- FAIL if the parked run is also blocked (leaving no way forward), or the live work item spawns a
  second concurrent run.

**Test data**
- Parked work item: from TC-193 · Live work item: any epic with a run in flight.

**Notes**
- **Max wait: 2 minutes** for each trigger request to return.
- The blocking statuses are `pending`, `running`, `awaiting_gate` and `approved`. `stalled` (what
  the console calls `Parked for takeover`) is deliberately excluded so a parked run always has a
  restart path. If a parked run is blocked with a 409, that is a High severity finding — it means a
  stalled item can never move again.
- **The modal is a front-end pre-check only, and it matches on the phase you clicked.** The backend
  guard is broader — it blocks on *any* live run for the work item. That mismatch is what TC-217
  covers; keep this case strictly same-phase so the two guards agree and the modal really fires.

---

### TC-200 · `/recovery` empty state when nothing is parked

| Field | Value |
|---|---|
| Suite | TS-14 Recovery & Takeover |
| Type | UX |
| Priority | Medium |
| Screen | `/recovery` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- **Do not attempt this in `Payment Gateway v2`.** TC-196 leaves a permanently `FAILED` run there,
  and `/recovery` renders `failed` runs as well as `stalled` ones, so that project can never show
  the empty state again. The old precondition ("no run is parked or failed") is unachievable once
  this suite has run.
- Instead, create a clean project through the product: on `/projects/new` create
  `Recovery Empty State`, track **Greenfield**. Trigger nothing in it — a project with no runs at
  all trivially has no parked runs.
- Select `Recovery Empty State` in the top-bar project switcher before starting.
- The companion is running and the sidebar pill reads `Companion: Ready`.

**Steps**
1. Confirm the project switcher reads `Recovery Empty State`.
2. Go to `http://localhost:5173/recovery` — bare path, **no `?run=` parameter**.
3. Wait for the screen to finish loading.

**Expected**
- The breadcrumb reads `Phases & Runs / Recovery`.
- A panel shows the empty state title `No parked runs`.
- The body reads `Nothing needs human takeover right now.`
- No banner, no key/value rows and none of **Reconnect & re-run**, **Take over manually** or
  **Connect your machine** are rendered.

**Pass / Fail**
- PASS if the empty state renders with both strings and no takeover actions.
- FAIL if the copy differs, a run is shown in a project that has none, or the takeover buttons
  render with no run behind them.
- **Blocked** if the project switcher will not hold `Recovery Empty State` — the screen is
  project-scoped, so a wrong selection invalidates the case.

**Test data**
- Project: `Recovery Empty State` (no runs)

**Notes**
- While loading, the panel briefly shows a spinner with `Checking for parked runs…` — wait for it to
  settle before judging.
- The screen surfaces both `stalled` and **`failed`** runs, and `failed` is terminal. In any project
  that has ever had a takeover or a hard run failure, this empty state is permanently unreachable —
  which is why this case uses a fresh project. Do not raise that as an empty-state defect; the real
  finding is the absence of any way to dismiss or target a specific run (audit Part 6, item 7).
- `Recovery Empty State` also serves as a clean fixture if a later cycle needs an unpolluted
  `/recovery`. Leave it empty.

---

### TC-216 · A late report reconciles the same parked run, with no button pressed

| Field | Value |
|---|---|
| Suite | TS-14 Recovery & Takeover |
| Type | Functional |
| Priority | Critical |
| Screen | `/runs/:id`, `/gates`, `/artifacts` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- **Run this immediately after TC-194, before TC-195.** It resolves TC-193's park.
- TC-193's Ideation run is parked (`Parked for takeover`) and is the only stalled-or-failed run in
  the project. The companion is still stopped.
- **Record before starting:** the parked run id from TC-193, and the count of Ideation runs
  currently listed for the epic on `/runs`.

**Steps**
1. Open `/runs/<the parked run id>` and confirm the badge reads `Parked for takeover`.
2. **Do not open `/recovery`, and do not click any button anywhere.**
3. In the companion's terminal, start it again with the same command from the plan §2.
4. Wait until the sidebar companion pill reads `Companion: Ready`.
5. Leave the run console open and watch it. If you are interrupted, **resume at step 5** with the
   recorded run id.
6. When the badge changes, reload `/gates` (it does not poll) and open `/artifacts`.
7. Go to `/runs`, select the epic, and count the Ideation runs again.

**Expected**
- The run id in the URL never changes — everything below happens on the **same** run.
- The badge leaves `Parked for takeover` on its own, with no user action, and progresses to
  `Awaiting gate` (or `Needs answer` first, if the agent asks something).
- New console lines appear continuing the same phase — the run is not restarted from scratch.
- An Ideation gate for the epic appears on `/gates` after a manual reload.
- An ideation artifact for this run appears in `/artifacts`.
- The Ideation run count on `/runs` is **unchanged** from the count recorded before step 1 — no
  second run was created.

**Pass / Fail**
- PASS if bringing the companion back online lets the **same** run finish and reach its gate, with
  no new run and no button pressed.
- FAIL if a second run is created, if the run restarts the phase from the beginning, or if the run
  reaches a gate but the artifact is missing.
- FAIL — **High** — if the badge stays `Parked for takeover` indefinitely after the companion is
  `Ready`. That is the headline promise of `/recovery` ("bringing it back online lets it finish this
  same run") not being kept, and the only remaining routes would be re-run or takeover.
- **Blocked** if the badge has not moved within **30 minutes** of the companion reaching `Ready`.

**Test data**
- Epic: `Stripe Webhook Integration` · Phase: `Ideation`

**Notes**
- **Max wait: 30 minutes** after `Companion: Ready`.
- **Why this case exists.** The `/recovery` screen's most prominent claim is the info banner: *"If
  your companion simply went to sleep, bringing it back online lets it finish this same run — it
  reconciles automatically and moves to its gate."* Nothing else in the pack tested it — TC-195
  tests the *other* button on that screen. This is the only case that exercises the reconciliation
  path itself.
- The mechanism is real on the backend: a report-timeout park marks the run `STALLED` but keeps the
  Temporal workflow **alive and waiting** for the companion's report
  (`backend/orchestration/activities.py:582-596`, `workflows.py:105-119`). Only an explicit human
  takeover ends it terminally. So the workflow will accept a late report; whether the restarted
  companion actually re-reports the run it was executing is exactly the open question this case
  answers.
- If the companion's own terminal shows it did not pick the run back up, attach that output to the
  defect — it distinguishes a companion-side gap from a platform-side one.

---

### TC-217 · Triggering a different phase while a run is live fails with a red banner, not a modal

| Field | Value |
|---|---|
| Suite | TS-14 Recovery & Takeover |
| Type | Negative |
| Priority | High |
| Screen | `/runs` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A work item with a run currently `Running` or `Awaiting gate` — TC-195's new Requirements run,
  or any live run, will do.
- **Record:** the work item and the phase that is live.
- The companion is running.

**Steps**
1. Go to `/runs` and select the work item whose run is live.
2. Confirm in the Runs table that its latest run for that phase is `Running` or `Awaiting gate`.
3. Click the trigger button for a **different** phase that has never run on this work item — for
   example **PRD** while **Requirements** is live.
4. Read what appears. Do not reload yet.
5. Reload `/runs` and re-read the Runs table for this work item.

**Expected**
- **No modal opens.** The front-end guard only checks the phase you clicked, and that phase has no
  prior run, so nothing intercepts the click.
- The trigger button briefly reads `Triggering…`.
- A **red banner titled `Trigger failed`** appears below the phase buttons.
- Its body is the backend's own 409 text: `a run is already in progress for this work item (status:
  running). Wait for it to finish or take it over before starting a new one.` — the status word
  reflects the live run (`running` or `awaiting_gate`).
- **No** run row for the phase you clicked appears in the Runs table, before or after the reload.
- The live run is untouched — same run id, same status progression.

**Pass / Fail**
- PASS if the cross-phase trigger is refused, the refusal is a readable `Trigger failed` banner, and
  no second run is created.
- FAIL — **Critical** — if a second concurrent run is created for the work item.
- FAIL if the app shows a raw stack trace or JSON body, blanks out, or silently does nothing with no
  banner at all.

**Test data**
- Live phase: `Requirements` · Clicked phase: `PRD` (any never-run phase works)

**Notes**
- **Max wait: 2 minutes** for the trigger request to return.
- **This is the most likely real trigger failure in the product and nothing else covered it.** The
  two guards disagree by design-accident: the UI blocks per **phase**
  (`frontend/src/features/lifecycle/PhasesAndRuns.tsx:82-92` — it looks up the latest run *for the
  phase you clicked*), while the backend blocks per **work item**
  (`backend/orchestration/trigger.py:43-57`). So any cross-phase trigger sails past the modal and
  lands on the 409.
- Do **not** expect a modal reading `{Live phase} is already running` here. The modal's title is
  built from the phase you *clicked*, not the one that is live, and it does not fire at all in this
  scenario. TC-199 covers the same-phase case where the modal does fire.
- The refusal itself is correct behaviour — one active run per work item is the platform's rule.
  The finding, if you want to raise one, is the **UX**: the user gets a raw backend sentence in a
  danger banner instead of the friendly modal the same situation gets one phase over. Raise that
  once, as Medium.
- **Scheduling consequence worth carrying into TS-09 and TS-15:** because the guard is per work
  item, every gate-producing run on a shared epic must be run **sequentially**. Phases cannot be
  prepared in parallel on the same work item.

---

### TC-218 · When the app can't be reached, the accessibility screens say so in plain words

| Field | Value |
|---|---|
| Suite | TS-14 Recovery & Takeover |
| Type | Negative |
| Priority | Medium |
| Screen | Pages & audit, Review queue, Conformance statement |
| Persona | P4 QA Lead |
| Automation | Partly |

**Preconditions**
- Somebody who can stop the platform for a few seconds — or simply turn off your network adapter,
  which is easier and proves the same thing.

**Steps**
1. On **Pages & audit**, open **Add a page** and fill it in. **Do not submit yet.**
2. Disconnect the network (or have the platform stopped).
3. Press **Add page**.
4. Reconnect, then repeat the same two steps for: starting an audit, saving a decision on a finding
   in the **Review queue**, saving the **Conformance statement** draft, and signing it.
5. Reconnected, deliberately provoke a real refusal: submit a page list containing the same route
   twice.

**Expected**
- At step 3 the red banner reads **"Your browser couldn't connect, so nothing was saved. Try
  again."**
- It never reads **"Failed to fetch"**, "NetworkError", "Unexpected token", or anything about JSON.
- The same for every screen in step 4.
- At step 5 the banner shows the **platform's own refusal, word for word** — the sentence naming the
  duplicate route. That one must NOT be replaced with a general message.

**Pass / Fail**
- PASS if a lost connection reads as a lost connection, and a real refusal still explains itself.
- FAIL on any browser or programming text, and equally on a real refusal being flattened into
  "something went wrong".

**Notes**
- Bugs S.No 303. Ten places across these three screens. S.No 248 fixed this on the rest of the
  product; these were missed, and the distinction in step 5 is the reason that fix is not simply
  "replace the message" — a refusal in words is the most useful thing a screen can show.

---

### TC-219 · Companion status answers about the project you are in, and says what to do

**Why this case exists.** The status used to ask "is any machine of mine alive, on any project?" A
machine connected for a second project kept the badge green while the one running your phase was
dead. **This is the one defect in the group that never corrected itself with time**, so it is the
case that must not be skipped — and it needs two projects to show up at all, which is why it was
missed.

**Setup**
- One person, **two projects**, a companion connected for each. (Connect Machine, once per project.)
- Something a phase can run on in the first project.

**Steps**
1. With both machines running, read the status in the **top bar** and at the foot of the
   **sidebar**.
2. Stop **only the first project's** companion. Leave the second running. Wait about a minute,
   watching the status.
3. Keep waiting until it settles, then read the status and the line under it.
4. Switch the project selector to the **second** project and read the status again.
5. Switch back to the first, and start its companion again.

**Expected**
- Step 1: both read **"Companion: Ready"** in green.
- Step 2: within about **40 seconds** it turns amber and reads **"Companion: checking…"**. This is a
  warning, not a fault — nothing is disabled.
- Step 3: it turns red and reads **"Companion: not connected"**, and under the sidebar badge a link
  reads **"Reconnect to run phases on <the first project's name>"**. Clicking either the badge in
  the top bar or that link opens Connect Machine.
- **Step 4 is the point of this case: the status turns green again**, because that project's machine
  really is connected. The same data, two honest answers.
- Step 5: back to green within about 15 seconds.

**Pass / Fail**
- PASS if the status follows the project in the selector, including green at step 4 and red at
  step 3 **at the same moment**.
- FAIL if the first project ever reads Ready while its machine is stopped. That is the reported bug.
- FAIL if the amber state never appears, or if it appears while the machine is healthy.

**Notes**
- Bugs S.No 306 (the project scoping) and S.No 307 (the amber state). The two-minute rule the
  platform uses to declare a machine gone was deliberately **not** changed — it also decides which
  machine a phase is sent to and how long a machine holds claimed work (S.No 84, 111, 134). The
  amber band is what buys the earlier warning without touching any of that.
- Step 2's timing is measured from the server, not your computer's clock, so a device with the wrong
  time still shows the right colour.

---

### TC-220 · A dropped machine interrupts you — but only when something is actually stuck

**Why this case exists.** With the badge corrected you could still work for a long time without
looking at it. The opposite failure matters just as much: a message that fires every time a laptop
sleeps is one nobody reads by the week it matters.

**Setup**
- A project with a companion that has connected before.

**Steps**
1. With **nothing running**, stop the companion. Wait two minutes and move around the app.
2. Start the companion, trigger a phase, and stop the companion again **before** it picks the work
   up.
3. Move to a different screen — Work Items, Gates, anywhere.
4. Press **Dismiss**, then navigate away and back.
5. Start the companion again, let the phase run, and look once more.

**Expected**
- **Step 1 shows nothing.** The badge goes red, and that is all — nothing was waiting, so nothing
  was wrong.
- Step 2–3: a red message appears across the top of **whatever screen you are on**, reading **"Your
  machine stopped responding"** and naming the phase: "<Phase> hasn't started, and it won't until
  your machine is back", with **Reconnect your machine** and **Open the run** links.
- Step 4: it goes and stays gone while you keep working.
- Step 5: nothing reappears.

**Pass / Fail**
- PASS if it appears only when a phase is genuinely waiting, follows you between screens, and
  dismisses.
- **FAIL if step 1 produces a message.** A closed laptop with no work pending is not a problem, and
  warning about it is how a warning stops being read.

**Notes**
- Bugs S.No 311. The message names the phase, never the run's identifier — the standing rule.
- It also only looks for stuck work while your machine is actually missing, so it adds no background
  checking to ordinary use (the concern behind S.No 12).

---

### TC-221 · Disconnecting a machine ends the companion with a sentence, not a crash

**Why this case exists.** Reported live on 2026-10-05, during the first pass over the companion
status fixes. The tester pressed **Disconnect** on Connect Machine — the app behaved perfectly —
and the companion's own terminal died with a Python stack trace ending
`DaemonError: claim work -> 401: {'detail': 'invalid or missing Runner token'}`. Two things were
wrong at once: a deliberate, requested outcome was presented as a crash, and the message named an
HTTP status code and a server field while never saying the one useful thing — reconnect it. The
standing "no machine words in front of a person" rule had been applied to every screen in the app
and never to the terminal, which is the only screen a developer has while the companion runs.

**Setup**
- A project with a companion connected and running in a terminal you can see.
- **Nothing needs to be running.** This case costs no engine usage — do not trigger a phase for it.

**Steps**
1. Watch the companion terminal. Confirm it is idle and polling.
2. In the app, open **Connect Machine** and press **Disconnect**.
3. Watch the terminal for up to a minute (it reacts on its next poll).
4. Read the app's status badge in the top bar and at the foot of the sidebar.
5. In the same terminal, check the exit code — `echo $LASTEXITCODE` on PowerShell, `echo $?` on a
   Unix shell.

**Expected**
- The companion stops, printing exactly three lines and **no stack trace**:
  - "This machine was disconnected in the SDLC app, so it can no longer pick up work."
  - "To run phases on this machine again, open Connect Machine in the app and connect it."
  - "Stopping."
- The app shows **Companion: not connected**, with the reconnect link naming the project.
- The exit code is **2** — it did not keep running, and a wrapper script can tell without reading
  the words.

**Pass / Fail**
- PASS if the ending is those sentences, there is no traceback anywhere in the output, and the exit
  code is 2.
- **FAIL on any traceback**, and FAIL if the ending names a status code, an HTTP verb, a token or a
  server field.
- FAIL if the companion keeps polling instead of stopping.

**Notes**
- Bugs S.No 312.
- **Stopping is correct, not a shortcoming.** Reconnecting issues a *new* token, which this process
  could never pick up — a companion that sat waiting would look alive while being permanently
  useless, which is the same kind of lie S.No 306–311 were about.
- The message cannot name the project: the companion is started with a workspace and a token only,
  and never learns the project's name. Naming it would need a new field from the server. Left out
  rather than guessed.
- An **unexpected** failure still ends on one plain line that keeps its detail — there the detail is
  the useful part, because nobody asked for it. Only the disconnect case is given fixed wording.
