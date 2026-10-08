# TS-07 · Phases & Runs

This is where the product's core promise starts: a phase is triggered from the browser, it executes
on **your** companion machine, and every state it passes through is visible in the run console. If
this suite fails, nothing downstream (clarifications, gates, artifacts) can be tested at all.

**Run these in order.** TC-097 → TC-112 build on each other: the first Ideation run created in
TC-100 is the run inspected in TC-101–TC-105, re-triggered in TC-106–TC-108, and handed to TS-08 and
TS-09. Skipping ahead loses the preconditions and you will spend 25 minutes re-creating them.

**Time budget.** A real phase run takes **20–30 minutes** from trigger to `Awaiting gate`. Plan
TC-100 as the first thing you do in a session, then work TC-101–TC-105 against the same run while it
progresses.

**Timeout policy — read before you run anything long.** Every case below that waits on a live run
states an explicit **max wait**. If the run has not reached the state the case expects by then,
stop and record the verdict **Blocked** with the reason `exceeded the stated max wait`. Do **not**
record Failed — a Failed verdict means the app rendered something wrong, not that it was slow.
Capture the run id, the last console line and its timestamp in the notes so the run can be
post-mortemed. The default max wait for a plan-phase run is **45 minutes** from trigger.

**One run per WORK ITEM, not per phase.** The backend admits a trigger only if the work item has
*no* live run at all (`pending` / `running` / `awaiting_gate` / `approved` / **`paused`**) — the
phase you pick is irrelevant to that check. `paused` joined that list on 2026-10-03 with the Pause
button (TC-706): a run somebody stopped on purpose still holds the work item, and the refusal you
get is a different sentence from the others — see TC-708. A **parked** run (`stalled`) is still
*not* on the list, and re-triggering over one is still valid; that difference is deliberate and
TC-708 pins both halves. The `/runs` screen, in contrast, only warns you about the *same* phase.
So while any run on the epic is live you cannot start **any** other phase on it; the second trigger
comes back as a red `Trigger failed` banner (TC-701). Practical consequence: **all runs on the
shared epic must be prepared sequentially** — never in parallel to save time.

---

### TC-097 · Trigger panel renders with the companion online

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Functional |
| Priority | Critical |
| Screen | `/runs` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1 with project `Payment Gateway v2` selected.
- The companion is running and the top-bar companion pill reads `Companion: Ready` (TS-05).
- At least one work item exists (the epic `Stripe Webhook Integration`).

**Steps**
1. Go to `http://localhost:5173/runs`.
2. Read the page heading and the panel titles.
3. Look at the `Work item` field and the row of phase buttons underneath it.

**Expected**
- The h1 is `Phases & Runs`.
- The first panel is titled `Trigger a phase` and shows a `Work item` field, not the offline warning.
- Below the field, the label reads `All phases — {work item key} · {title}` (e.g.
  `All phases — WI-1 · Stripe Webhook Integration`) — never eight characters of an internal id.
  With no work item selected it reads `All phases — No work item selected`.
- The work-item name at the right of the `Runs` panel header uses the same `{key} · {title}` form.
- A row of buttons is shown, one per phase, each labelled `▶ {Phase}` — including `▶ Ideation`,
  `▶ Requirements`, `▶ PRD`, `▶ Architecture`, `▶ UX Design`, `▶ Task Breakdown`.
- A second panel titled `Runs` is present below.

**Pass / Fail**
- PASS if the trigger panel is interactive and the full phase list renders.
- FAIL if the offline warning appears while the pill says `Companion: Ready`, if only a 3-phase
  placeholder list renders, or if the phase buttons never load.

**Notes**
- The phase list comes from the live phase catalog. A brief `Loading phases…` with a spinner before
  the buttons appear is expected, not a defect.

---

### TC-098 · Each phase button names the role that will decide its gate

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | UX |
| Priority | Medium |
| Screen | `/runs` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-097 passed; the trigger panel is interactive.

**Steps**
1. On `/runs`, hover over `▶ Ideation` and wait for the browser tooltip.
2. Hover over `▶ Architecture`.
3. Hover over `▶ UX Design`.
4. Hover over `▶ Testing`.

**Expected**
- `▶ Ideation` shows the tooltip `Trigger Ideation (gate: Product Owner)`.
- `▶ Architecture` shows `Trigger Architecture (gate: Architect)`.
- `▶ UX Design` shows `Trigger UX Design (gate: Designer)`.
- `▶ Testing` shows `Trigger Testing (gate: QA Lead)`.

**Pass / Fail**
- PASS if every tooltip names the phase and its gate role in the humanised form above.
- FAIL if a tooltip is missing, or shows a raw role key such as `product_owner` or `qa_lead`.

**Notes**
- Roles are humanised through a shared label map. A raw key leaking into the tooltip is a Low
  severity copy defect, not a functional one.

---

### TC-099 · The work-item picker is searchable and reports no matches

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Functional |
| Priority | Medium |
| Screen | `/runs` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- The project has at least two work items (the epic plus one task — create one on `/work-items` if
  needed).

**Steps**
1. On `/runs`, click into the `Work item` field.
2. Confirm the placeholder text before typing.
3. Type `Stripe`.
4. Clear the field and type `zzzzz`.
5. Clear it again and pick the epic `Stripe Webhook Integration` from the list.

**Expected**
- The empty field shows the placeholder `Search work items…`.
- Typing `Stripe` narrows the list to work items whose key or title contains `Stripe`.
- Typing `zzzzz` shows `No work items match`.
- Each option in the list reads `{key} · {title}`, e.g. `WI-1 · Stripe Webhook Integration`.
- Selecting the epic updates the label below to `All phases — {key} · Stripe Webhook Integration`
  and the work-item name on the right of the `Runs` panel header to `{key} · Stripe Webhook Integration`
  — the picker, the label and the header all name the item the same way.

**Test data**
- Search terms: `Stripe`, `zzzzz`

**Pass / Fail**
- PASS if the field filters as you type, shows `No work items match` for a non-matching term, and
  the selection drives the phase-list label.
- FAIL if the field is a plain non-filtering dropdown, if selecting an item does not change the
  label, or if the label or `Runs` header shows an 8-character id instead of the item's key.

**Notes**
- **Long titles.** If a work item's title is too long for the field, hovering its row in the open
  list — or moving the highlight onto it with ↑ / ↓ — shows the full title in a box drawn over that
  row. Hovering the closed field does the same for the chosen item. The box appears only when the
  text is actually cut off; short titles show nothing extra. To check it, create a work item with a
  long title (e.g. `ExpenseResponse is missing the created_at field on every list endpoint`) and
  narrow the browser window. A cut-off title with no way to read it in full is a defect.
- The same full-title box applies to the other searchable dropdowns built on this picker.

---

### TC-100 · Triggering Ideation on the epic starts a run

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Functional |
| Priority | Critical |
| Screen | `/runs` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Companion online (`Companion: Ready`).
- The epic `Stripe Webhook Integration` is selected in `Work item`.
- The epic has **no** prior Ideation run (this is a first trigger — otherwise TC-107's re-run modal
  intercepts and this case does not apply).
- The epic has **no** live run of *any* phase (see the one-run-per-work-item rule above) — otherwise
  the trigger is refused with a 409 (TC-701).
- Budget 20–30 minutes before the run reaches its gate. Start this early in the session.
- **Max wait for the assertions below: 2 minutes.** This case only asserts the trigger response, not
  the run. If neither banner has appeared after 2 minutes, record **Blocked**, not Failed.

**Steps**
1. On `/runs`, confirm `Work item` is the epic `Stripe Webhook Integration`.
2. Click `▶ Ideation`.
3. Watch the button while the request is in flight.
4. Read the banner that appears under the phase list.

**Expected**
- While the request is in flight the button shows a spinner and the text `Triggering…`.
- A green banner appears titled `Phase triggered` with the body
  `Run started — watch it appear in the Runs table below.`
- No `Trigger failed` banner appears.

**Pass / Fail**
- PASS if the `Phase triggered` banner appears and no error banner is shown.
- FAIL if a red `Trigger failed` banner appears, if nothing happens on click, or if the page shows a
  raw error payload.

**Notes**
- Keep this browser tab open — TC-101 through TC-105 all observe this same run.
- Do not click a second phase button. While this run is live the backend refuses **every** other
  phase on the same work item too (TC-701), and TC-106 needs exactly one run active.

---

### TC-101 · The new run appears in the Runs table with the correct columns

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Functional |
| Priority | High |
| Screen | `/runs` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-100 passed; an Ideation run was triggered on the epic within the last few minutes.

**Steps**
1. Stay on `/runs` with the epic selected. Wait a few seconds and refresh if needed.
2. Read the `Runs` panel table headers.
3. Read the row for the new run.
4. Hover over the `Run …` link and over the `Workflow` cell.

**Expected**
- The table headers are exactly `Run`, `Phase`, `Status`, `Engine / model`, `Workflow`, `Created` —
  six columns, with **no** cost column.
- One row is present for the new run: the `Run` cell is a link reading `Run {8-char ref} ↗`, `Phase`
  reads `Ideation`, `Status` shows a badge (`Pending`, `Running` or `Awaiting gate` depending on how
  fast you looked), `Engine / model` reads `claude · claude-sonnet-4-6`, and `Created` shows a
  formatted date and time — not a raw ISO timestamp.
- The `Workflow` cell reads `agent-run-{8 hex chars}` — shortened, not the full workflow id.
- Hovering the `Run` link and the `Workflow` cell reveals the full id as a tooltip.

**Pass / Fail**
- PASS if all six headers match and the run row renders with a shortened, hoverable id.
- FAIL if a `Cost (est.)` column is present, if a header is missing or renamed, if a raw UUID is
  printed in full, or if the row never appears.

**Notes**
- The table is polled (every ~4 s), not pushed. Up to a few seconds of lag between trigger and the
  row appearing is expected. **Max wait for the row: 2 minutes**, then record **Blocked**.
- `Engine / model` is the model recommended by the agent catalog, not a per-run choice. Every
  greenfield phase run today reads `claude · claude-sonnet-4-6`. A different model id here is not
  automatically a failure — a tenant can re-route models — but `claude · local` is gallery-only
  demo copy and would mean you are looking at the design gallery, not the live screen.

---

### TC-102 · The run console header identifies the run

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Functional |
| Priority | High |
| Screen | `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-101 passed; the Ideation run row is visible on `/runs`.

**Steps**
1. Click the `Run {ref} ↗` link in the Runs table.
2. Read the breadcrumb, the h1 and the meta row under it.
3. Hover over each meta item.

**Expected**
- The breadcrumb reads `Phases & Runs / Run {8-char id}`, and `Phases & Runs` navigates back.
- The h1 reads `Run console — Ideation · {work item key} Stripe Webhook Integration`.
- The meta row shows four items: `Work item` (the epic's key or title), `Run ID` (8 characters),
  `Engine` reading `claude · claude-sonnet-4-6`, and `Workflow` reading the first 16 characters of
  the workflow id (`agent-run-xxxxxx`).
- Hovering `Work item`, `Run ID` and `Workflow` reveals the full ids as tooltips.

**Pass / Fail**
- PASS if the h1 names the phase and the work item, and all four meta items render.
- FAIL if the h1 shows a raw phase key (e.g. `01_ideation`), if the work item is missing from the
  title, or if any meta item is blank when the run row showed a value.

**Notes**
- `Engine` must agree with the `Engine / model` cell in the Runs table (TC-101). `Claude · local
  companion` and `Triggered by You` are **gallery** copy — if you see those, you are on the design
  gallery route, not the live console.

---

### TC-103 · The run console walks the status sequence to Awaiting gate

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | E2E |
| Priority | Critical |
| Screen | `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-100's Ideation run is open in the run console.
- **This case needs the full run: 20–30 minutes typical, max wait 45 minutes** from the trigger.
  Leave the tab open and check it periodically.
- The companion must stay running for the whole window.

**Steps**
1. Immediately after the trigger, note the status badge at the top right of the `Run {id8}` panel.
2. Leave the console open. Re-check every few minutes (refresh the page if you are unsure the poll
   is live).
3. Note the badge once the companion has claimed the run.
4. Note the badge and the banner once the run finishes.

**Expected**
- Right after dispatch the badge reads `Dispatched · waiting` and an info banner reads
  `Queued. It will start as soon as your companion claims it.`
- Once the companion claims it the badge changes to `Running` and the queued banner is gone.
- When the phase finishes the badge reads `Awaiting gate` and a warning banner titled
  `Awaiting gate` reads `The artifact is a draft until its gate is approved.` with a link
  `Open gate ↗`.
- The badge never skips backwards (e.g. `Running` → `Dispatched · waiting`).

**Pass / Fail**
- PASS if the badge passes through `Dispatched · waiting` → `Running` → `Awaiting gate` and the
  awaiting-gate banner and `Open gate ↗` link render.
- FAIL if the badge goes backwards, if it reaches `Awaiting gate` with no banner, or if it goes to
  `Failed` with a `Run failed` banner.
- **BLOCKED** (not Failed) if 45 minutes elapse from the trigger and the badge is still
  `Dispatched · waiting` or `Running`. Record the run id and the last console line. A run that
  never leaves `Dispatched · waiting` usually means the companion is not claiming — check TS-05
  first and note that as the reason.

**Notes**
- **Other legitimate outcomes — none of these is a FAIL of this case:**
  - `Needs answer` — the agent asked a question. Answer it via TS-08 (TC-116); the run then
    continues to `Awaiting gate`. Resume this case afterwards; the 45-minute clock restarts from
    the answer.
  - `Parked for takeover` — the run stalled (companion offline, or a step errored). Record this
    case **Blocked** with the reason `run parked` and go to TC-702, which owns that state.
- **Known bug — do not raise:** the console can show no new output for 20+ minutes between
  `Phase dispatched` and `Phase reported` on a long run
  (`docs/TESTING_PHASE_BUGS_HANDOFF.md` Bug 3). Do not kill a silent run *inside* the 45-minute
  window — a silent `Running` badge is expected behaviour today. The 45-minute max wait is what
  distinguishes "still working" from "stuck"; use it rather than your own judgement, so two
  testers reach the same verdict on the same run.

---

### TC-104 · Log lines appear in the run console

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Functional |
| Priority | High |
| Screen | `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A run is open in the console (TC-100's Ideation run), in any state.

**Steps**
1. Open the run console immediately after triggering and read the console block.
2. Wait until the run is claimed and re-read the console block.
3. Check the formatting of each line.

**Expected**
- Before any event is recorded the console shows the single muted line `No log lines yet…`.
- Once events arrive, each line is prefixed with a local time stamp followed by the message text.
- Lines accumulate over the life of the run — earlier lines are not replaced by later ones.

**Pass / Fail**
- PASS if `No log lines yet…` renders on an empty feed and timestamped lines accumulate afterwards.
- FAIL if the console is permanently blank with no placeholder, if lines appear with no timestamp,
  or if the feed resets to empty while the run is still going.

**Notes**
- The feed is **polled**, not streamed — there is no SSE or WebSocket in the app. A few seconds of
  lag is expected; instant appearance is not the bar.
- See TC-103's note on Bug 3: long silent gaps between log lines are a known issue.

---

### TC-105 · The work item moves off `Not started` once its phase runs

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Functional |
| Priority | High |
| Screen | `/work-items` · `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Before triggering, the epic `Stripe Webhook Integration` shows `Not started` in the Phase column
  of the work-items list view.
- TC-100's Ideation run has been claimed (console badge `Running` or later).

**Steps**
1. Go to `/work-items` and switch to the list/table view.
2. Find the row for `Stripe Webhook Integration` and read the `Phase` column.
3. Open `/runs/{id}` for the Ideation run and confirm its status badge.
4. Return to `/work-items` and re-read the `Phase` column.

**Expected**
- Before the run was triggered the `Phase` column read `Not started`.
- With the run claimed, the `Phase` column reads `Ideation` — a humanised name, not `01_ideation`.
- The run console for the same work item shows `Running` or `Awaiting gate`, consistent with the
  board/list value.

**Pass / Fail**
- PASS if the Phase column moves from `Not started` to `Ideation` and agrees with the run console.
- FAIL if the work item stays on `Not started` after the run is claimed, or if the list shows a raw
  phase key.

---

### TC-106 · Triggering a phase that is already running is blocked

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Negative |
| Priority | Critical |
| Screen | `/runs` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-100's Ideation run is still active (console badge `Dispatched · waiting`, `Running`,
  `Needs answer` or `Awaiting gate`) on the epic.

**Steps**
1. Go to `/runs` with the epic `Stripe Webhook Integration` selected.
2. Click `▶ Ideation` a second time.
3. Read the modal.
4. Click `Close`.
5. Click `▶ Ideation` again, then click `Open current run`.

**Expected**
- A modal opens titled `Ideation is already running` with body text explaining the work item already
  has a run in progress for this phase.
- The modal footer has exactly two controls: `Close` and `Open current run`.
- `Close` dismisses the modal and **no** second run is created — the Runs table still shows one
  Ideation row.
- `Open current run` navigates to the run console of the existing run.

**Pass / Fail**
- PASS if the modal blocks the trigger, no `Phase triggered` banner appears, and the Runs table
  still has exactly one Ideation row afterwards.
- FAIL if a second Ideation run row appears, or if the click produces a raw `409` error instead of
  the modal.

**Notes**
- **The two guards are not the same guard, and this case only exercises the UI one.** The `/runs`
  screen looks for a live run of *the phase you clicked* and opens this modal. The backend looks for
  a live run of *any* phase on the work item and returns a 409. They happen to agree here because
  you clicked the phase that is running. Click a **different** phase and they disagree — no modal
  fires and the 409 surfaces raw in a red `Trigger failed` banner. That is TC-701; do not raise it
  from this case.
- Because the modal short-circuits the request, no 409 is produced in this scenario at all.

---

### TC-107 · The re-run modal can be cancelled without starting a run

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Negative |
| Priority | High |
| Screen | `/runs` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- The epic has a **finished** Ideation run — its gate has been decided, or the run shows `Completed`
  or `Failed`. (After TS-09 TC-127 approves the Ideation gate this precondition is satisfied.)
- Note the number of rows currently in the Runs table.

**Steps**
1. Go to `/runs` with the epic selected.
2. Click `▶ Ideation`.
3. Read the modal title, body and footer buttons.
4. Click `Cancel`.
5. Re-read the Runs table.

**Expected**
- A modal opens titled `Re-run Ideation?`.
- The body warns that running again starts over and **replaces this phase's artifacts**, does not
  create duplicates, and that the previous run stays in the history.
- The footer has exactly two buttons: `Cancel` and `Re-run phase`.
- After `Cancel` the modal closes, no `Phase triggered` banner appears, and the Runs table row count
  is unchanged.

**Pass / Fail**
- PASS if `Cancel` closes the modal with no new run.
- FAIL if `Cancel` triggers the phase anyway, or if the modal is skipped and the phase re-runs
  immediately on click.

---

### TC-108 · Confirming a re-run creates a new run and keeps the old one

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Functional |
| Priority | High |
| Screen | `/runs` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-107's preconditions (a finished Ideation run on the epic).
- Note the existing Ideation run's short reference from the Runs table.
- **Budget 20–30 minutes** if you intend to let the new run finish; the assertion below only needs
  the first minute.

**Steps**
1. On `/runs`, click `▶ Ideation`.
2. In the `Re-run Ideation?` modal, click `Re-run phase`.
3. Read the banner and then the Runs table.
4. Compare the short reference of the top row with the one you noted.

**Expected**
- The `Phase triggered` banner appears with `Run started — watch it appear in the Runs table below.`
- The Runs table now has **two** Ideation rows.
- The new row has a different `Run` reference from the earlier run and a newer `Created` value.
- The earlier Ideation run is still listed with its own status — it is not deleted or overwritten.

**Pass / Fail**
- PASS if a second Ideation row is added and the original row survives.
- FAIL if the original run row disappears, or if the re-run reuses the same run id.

---

### TC-109 · An offline companion blocks the trigger panel

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Negative |
| Priority | Critical |
| Screen | `/runs` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- No run is currently in flight (stopping the companion mid-run will strand it — see TS-14).
- You are able to stop and restart the companion daemon in its terminal.

**Steps**
1. Stop the companion (`Ctrl-C` in its terminal).
2. Wait ~2 minutes for the machine to fall outside the online window, then reload `/runs`.
3. Read the `Trigger a phase` panel.
4. Try to click `▶ Ideation`.
5. Restart the companion, wait for the top-bar pill to read `Companion: Ready`, and reload `/runs`.

**Expected**
- The panel shows a warning banner titled `Your machine isn't connected` with the body
  `Phases can't run until your companion is online.` and a link `Connect your machine ↗`.
- The **full** phase list is still shown underneath, greyed out — not a shortened placeholder list.
- Clicking a greyed phase button does nothing: no `Triggering…` state, no `Phase triggered` banner,
  no new row in the Runs table.
- The `Runs` panel header no longer shows the selected work-item name.
- After the companion is back and the page is reloaded, the trigger panel returns to the interactive
  state from TC-097.

**Pass / Fail**
- PASS if the warning renders, the phase list is visible but inert, and no run is created.
- FAIL if a phase can still be triggered from the offline panel, if only a 3-phase placeholder is
  shown, or if the panel stays blocked after the companion reconnects.

**Notes**
- This block is **UI-only**. The backend does not check companion liveness. Do not write this up as
  a backend enforcement gap — it is the documented design today. If a run does somehow get created
  while offline it will sit `pending` and later park as `stalled` at its report timeout (TS-14).

---

### TC-110 · A failed run shows the reason and offers a retry

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | UX |
| Priority | High |
| Screen | `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A run that ended in `Failed`. Reach it through the product — the reliable route is TS-09 TC-133
  (reject a gate), which puts its run into the failed family. A genuinely crashed run works too if
  you have one.

**Steps**
1. Open the failed run's console from the Runs table.
2. Read the status badge and the banner.
3. Read the button under the console block.
4. Read the console lines for an error entry.

**Expected**
- The status badge reads `Failed`.
- A red banner is shown. For a rejected gate its title is `Gate rejected`; for an engine failure the
  title is `Run failed` and the body is either `Reason: {…}` naming a concrete cause, or
  `The engine exited before reporting. No artifact was registered.` when no reason was captured.
- A `Retry run` button is shown below the console.
**Pass / Fail**
- PASS if the `Failed` badge, an explanatory banner and a `Retry run` button are all present.
- FAIL if the badge shows a raw status such as `failed`, if there is no banner explaining why, or if
  a failed run offers no way forward at all.

**Notes**
- If instead of `Retry run` you see an `Automatically retried` banner and a
  `Go to the retry run →` button, this run was auto-retried by the platform. That is the state
  TC-703 owns — record this case Blocked with the reason `run was auto-retried` and run TC-703.
  A gate rejection (TC-133) never auto-retries, so the reliable route above avoids it.

---

### TC-111 · The Runs table empty state

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | UX |
| Priority | Medium |
| Screen | `/runs` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- A work item that has never had a phase triggered on it. Create one on `/work-items` (a task named
  `QA — no runs`) if every existing item already has runs.
- The companion is online.

**Steps**
1. Go to `/runs`.
2. In the `Work item` field, select the work item that has no runs.
3. Read the `Runs` panel.

**Expected**
- The `Runs` panel shows the empty state: title `No runs yet`, text
  `Trigger the first phase for this work item to see runs appear here with live status.`
- No table headers and no rows are rendered.

**Pass / Fail**
- PASS if the empty state renders with the exact copy and no rows.
- FAIL if the table renders instead of the empty state, or if another work item's runs leak into
  this view.

**Notes**
- Earlier versions of this case also failed on demo rows (`RUN-42`, `RUN-41`). Those rows exist only
  behind the design-gallery route and cannot render on `/runs`, so that criterion could never fire
  and has been dropped. The leak this case can actually catch is **another work item's** runs.

---

### TC-112 · A run id that does not exist shows `Run not found`

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Negative |
| Priority | Medium |
| Screen | `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 with a project selected.

**Steps**
1. In the address bar, go to
   `http://localhost:5173/runs/00000000-0000-0000-0000-000000000000`.
2. Read the breadcrumb and the panel.

**Expected**
- The breadcrumb reads `Phases & Runs / Not found`, and `Phases & Runs` still navigates back
  to `/runs`.
- A red banner titled `Run not found` reads `This run doesn't exist or you don't have access to it.`
- The app shell (sidebar and top bar) still renders — the page does not white-screen.

**Pass / Fail**
- PASS if the `Run not found` banner renders inside the normal app shell.
- FAIL if the page crashes, spins forever, or shows a raw 404/500 payload.

---

### TC-701 · Triggering a different phase while a run is live fails with a 409 banner

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Negative |
| Priority | Critical |
| Screen | `/runs` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-100's Ideation run on the epic `Stripe Webhook Integration` is still live — its console badge
  reads `Dispatched · waiting`, `Running`, `Needs answer` or `Awaiting gate`.
- **Max wait: none.** This case asserts an immediate response; if neither a banner nor a modal
  appears within 60 seconds of the click, record **Blocked**.

**Steps**
1. Go to `/runs` with the epic selected.
2. Confirm the Runs table shows the live Ideation run.
3. Click `▶ Requirements` — a **different** phase from the one that is running.
4. Read what appears under the phase list.
5. Re-read the Runs table.

**Expected**
- **No modal opens.** The re-run / already-running modals only fire for the phase you clicked, and
  Requirements has never run.
- The button briefly shows `Triggering…`, then a red banner titled `Trigger failed` appears under
  the phase list.
- The banner body is the raw backend message, beginning
  `a run is already in progress for this work item (status: ` and naming the live run's status,
  followed by `Wait for it to finish or take it over before starting a new one.`
- No Requirements row is added to the Runs table — the row count is unchanged.
- The Ideation run is unaffected and keeps progressing.

**Pass / Fail**
- PASS if the second phase is refused, the `Trigger failed` banner renders, and no second run row
  appears.
- FAIL — **Critical** — if a second run row is created for the epic while the first is live, or if
  the page white-screens instead of showing the banner.

**Notes**
- This is the case the suite's one-run-per-work-item rule exists for. The admission guard is per
  **work item**, not per phase — the phase you clicked is irrelevant to it.
- **The raw backend sentence in the banner is the expected result today, not a defect to raise.**
  There is no friendly copy for this path and no modal covers it; that gap is tracked separately as
  a Medium UX defect. Assert the banner appears and the run is not created; do not re-file the
  wording.

---

### TC-702 · A parked run offers `Resume from where it stopped`

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | UX |
| Priority | High |
| Screen | `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A run whose console badge reads `Parked for takeover`. Reach it through the product: trigger a
  phase, then stop the companion (`Ctrl-C`) while it is `Running` and wait for the platform's report
  timeout to park it.
- **Max wait for the park: 2 hours** from stopping the companion (the report timeout is long). If
  the badge has not flipped by then, record **Blocked** with the reason `run never parked` — this
  case has no other route to its starting state.

**Steps**
1. Open the parked run's console from the Runs table.
2. Read the status badge in the top-right of the `Run {id8}` panel.
3. Read the banner, if one is shown.
4. Read the buttons below the console block.

**Expected**
- The status badge reads `Parked for takeover` — not `Failed` and not a raw status such as
  `stalled`.
- The console block still shows the run's accumulated log lines; they are not cleared by the park.
- **If the park was an error park** (the run stopped on a failing step rather than a lost
  companion): a warning banner titled `Paused on an error — you can carry on from here` is shown,
  with either `Reason: {…}` or `This run hit an error and paused.`, and two buttons are offered —
  `Resume from where it stopped` (primary) and `Take over instead` (secondary).
- **If the park was a companion-offline park**: the badge still reads `Parked for takeover`, but
  **no** banner and **no** buttons are rendered on this screen. Recovery for that park lives on
  `/recovery` (TS-14).

**Pass / Fail**
- PASS if the badge reads `Parked for takeover` and the console keeps its log lines, and — for an
  error park only — the banner and both buttons render.
- FAIL if a parked run is badged `Failed`, if the badge shows a raw status key, or if an error park
  offers `Resume from where it stopped` but clicking it produces neither a state change nor a
  `Couldn't resume` banner.

**Notes**
- The two park flavours are genuinely different states with different affordances. Record which one
  you got — a companion-offline park showing no buttons is **expected**, not a missing-control
  defect.
- `Take over instead` navigates to `/recovery` with **no run parameter**, so `/recovery` picks the
  first parked run in the project rather than this one. On a project with a single parked run they
  are the same run and you will not notice. That mis-targeting is tracked separately; do not raise
  it here.

---

### TC-703 · An auto-retried run links to its continuation run

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | UX |
| Priority | Medium |
| Screen | `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A **build-tier** run (Implementation, Test Automation or CI/CD) that exhausted its remediation
  attempts and was auto-retried by the platform. This is not directly inducible — you cannot make an
  agent fail on demand.
- **This case is opportunistic.** If no run in the workspace shows the `Automatically retried`
  banner by the end of the cycle, record it **Blocked** with the reason
  `no auto-retried run occurred`. Do not manufacture one, and do not record it Failed.

**Steps**
1. Open the failed run's console from the Runs table.
2. Read the status badge and both banners.
3. Read the button below the console block.
4. Click the link in the `Automatically retried` banner.

**Expected**
- The status badge reads `Failed` and a red `Run failed` banner is shown above.
- Below it, an info banner titled `Automatically retried` reads
  `The platform started a fresh attempt for this work item — you don't need to re-trigger.`
- The banner carries a link reading `Continued as run {8-char id} ({status}) ↗` where the status is
  the continuation run's own live status with underscores shown as spaces (e.g. `awaiting gate`).
- The button below the console reads `Go to the retry run →` — **not** `Retry run`.
- Following either the link or the button opens the continuation run's console, which is a
  different run id from the one you started on.

**Pass / Fail**
- PASS if the `Automatically retried` banner names the continuation run and both it and the button
  navigate to that run's console.
- FAIL if a `Retry run` button is offered alongside the auto-retry banner (which would let the user
  spawn a duplicate third run), if the link is dead, or if it navigates back to the same run.

**Notes**
- The point of this screen state is to stop the user re-triggering by hand while a retry is already
  running. `Retry run` and `Go to the retry run →` are mutually exclusive by design — seeing both is
  the failure this case is looking for.

---

### TC-704 · Any project member can trigger a phase, whatever their role

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Permission |
| Priority | High |
| Screen | `/runs` |
| Persona | P10 Engineer |
| Automation | No |

**Preconditions**
- P10 exists with the `engineer` role on `Payment Gateway v2` and holds no other role.
- The epic has **no** live run (otherwise the trigger is refused by the work-item guard and this
  case proves nothing). Wait for TC-100's run to reach a gate and be decided first.
- The companion is online.

**Steps**
1. Log out and log in as P10 (`qa+<x>.eng@edvensoft.com` / `QaTest-2026!`).
2. Go to `/runs` and select the epic `Stripe Webhook Integration`.
3. Read the `Trigger a phase` panel — is it interactive for this user?
4. Click `▶ Ideation` (or, if Ideation has already run, confirm the `Re-run Ideation?` modal and
   click `Re-run phase`).
5. Read the banner and the Runs table.

**Expected**
- The trigger panel renders exactly as it does for P1 — the phase buttons are enabled, with no
  permission banner and no read-only state.
- The trigger **succeeds**: the green `Phase triggered` banner appears with
  `Run started — watch it appear in the Runs table below.`
- A new run row appears in the Runs table.

**Pass / Fail**
- PASS if P10 can trigger a phase and the run is created.
- FAIL if the app white-screens, or if the trigger fails with a raw error payload rather than
  either succeeding or showing a clean permission message.

**Notes**
- **This case asserts the permissive behaviour the app actually has today, and that behaviour is a
  known product defect — do not raise a duplicate.** The trigger endpoint inherits the project-wide
  default permission (`AllowAny`), so no role check runs at all: any member can start a 20–30 minute
  run on any work item. It is already logged against the permission model. This case exists to
  detect the day the behaviour *changes*.
- If a future build starts refusing P10 here, that is a deliberate fix, not a failure — record the
  new behaviour in the notes and flag it for the plan owner rather than raising a defect.
- Clean up after this case: the run you started counts as the epic's live run and blocks every other
  trigger until it finishes or is decided.

---

### TC-705 · Any project member can take over a parked run

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Permission |
| Priority | Medium |
| Screen | `/recovery` |
| Persona | P10 Engineer |
| Automation | No |

**Preconditions**
- A parked run exists on `Payment Gateway v2` — TC-702's precondition. If you have no parked run,
  record this case **Blocked** with the reason `no parked run available`; do not park one solely for
  this case.
- P10 exists with the `engineer` role on the project and holds no other role.

**Steps**
1. Log out and log in as P10.
2. Go to `http://localhost:5173/recovery`.
3. Read the h1 and the card.
4. Read the buttons in the card.
5. Click `Take over manually`.
6. Read what changes on the screen.

**Expected**
- P10 sees the full recovery card, not a permission wall: the h1 reads
  `Run recovery — {work item} · {Phase}` and a red banner titled
  `This run is parked for takeover` is shown.
- `Reconnect & re-run` and `Take over manually` are both **enabled** for the Engineer.
- Clicking `Take over manually` **succeeds** — no `Couldn't update takeover state` banner appears.

**Pass / Fail**
- PASS if P10 reaches the recovery screen and the takeover is accepted.
- FAIL if the click produces a raw error payload, or if the screen white-screens.

**Notes**
- **Expected-and-known:** like the phase trigger (TC-704), the take-over endpoint inherits the
  project default `AllowAny`, so it applies no role check. This case pins the current behaviour so a
  change is noticed; the missing authorisation is already logged as a product defect. Do not raise
  it again.
- `/recovery` always targets the **first** stalled-or-failed run in the project, so on a project
  with several parked runs you may not be acting on the one you expected. Confirm the run id in the
  card before clicking. That mis-targeting is tracked separately.

---

### TC-706 · A run can be paused on purpose, and the dialog is honest about timing

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Functional |
| Priority | High |
| Screen | `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | Partly |

**Preconditions**
- A run you started that is **Queued** or **Running**. TC-100's Ideation run, caught early, is ideal.
- Your companion is connected.

**Steps**
1. Open the run console while the run still says **Queued** (before the companion picks it up).
2. Read the buttons beside the status chip.
3. Press **Pause run** and read the dialog **without confirming**. Note which wording you get.
4. Press **Keep running**.
5. Wait until the run says **Running**, then press **Pause run** again and read the dialog.
6. Confirm with **Pause run**.

**Expected**
- **Pause run** sits beside the status chip in both states.
- At step 3, while the run is Queued, the dialog says your companion **hasn't started this yet**,
  and that pausing stops it before any work begins.
- At step 5, while it is Running, the dialog says the companion **will finish the step it's on**,
  that this may take a few minutes to come to a stop, and that you can close the companion on your
  machine if you need it stopped right now. These are **two different messages** and you must get
  the matching one.
- At step 4 nothing happens — the run carries on.
- After step 6 the dialog closes, the chip reads **Paused by you**, and the banner names who paused
  it and when.

**Pass / Fail**
- PASS if both wordings appear in the right state and the run pauses on confirmation.
- FAIL if the dialog is missing; if a Queued run is told the step "may take a few minutes to come to
  a stop"; if a Running run is told nothing has started; or if **Keep running** pauses anything.

**Notes**
- Bugs S.No 290. The two messages are the point, not decoration. The platform has **no channel to
  your companion** — it pulls work from us — so an agent already working genuinely cannot be
  interrupted, and a single sentence implying an instant stop would be a promise the product breaks
  in front of a client.
- **Pause is not offered on a run waiting at its gate**, and that is correct: it is already stopped
  and costs nothing.

---

### TC-707 · A paused run is not handed to the companion, and resumes cleanly

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Functional |
| Priority | High |
| Screen | `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | Partly |

**Preconditions**
- TC-706 passed and the run is **Paused by you**. Your companion is connected and running.

**Steps**
1. Leave the run paused for **two minutes** with the companion connected. Watch the companion
   window, or its log.
2. Read the run console. Note the buttons offered.
3. Press **Resume run** and read the dialog.
4. Confirm with **Resume run**.
5. Watch the run console and the companion for the next two minutes.

**Expected**
- At step 1 the companion **never picks the run up**. It keeps polling and stays idle; no phase
  starts; nothing new appears in the run log.
- At step 2 the buttons are **Resume run** and **Discard this run**. The words *Take over* appear
  **nowhere**.
- At step 3 the dialog names the phase and says your companion needs to be running.
- After step 4 the chip returns to **Running** or **Queued**, and within about five seconds the
  companion **claims the run and carries on**.
- The work already done is still there — the run does not start from the beginning.

**Pass / Fail**
- PASS if a paused run is never claimed, and a resumed one is claimed again within ~5 seconds and
  continues rather than restarting.
- FAIL if the companion starts work on a paused run (**the most serious failure in this suite** —
  it means Pause is a button that changes a label and nothing else); if Resume leaves the run
  unclaimable; or if resuming restarts the phase from step 1.

**Notes**
- Bugs S.No 290. Holding the work out of the companion's reach is the **only** control the platform
  has over a machine it does not own, which is why step 1 is worth the two minutes.

---

### TC-708 · A paused run blocks starting that phase again; a parked one does not

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | Negative |
| Priority | High |
| Screen | `/runs`, `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- A run on a work item that is **Paused by you** (TC-706).
- Separately, a work item with a **parked** run — the one TC-702 left behind.

**Steps**
1. With the run paused, go to `/runs`, pick the **same work item**, and trigger **any** phase.
2. Read the refusal.
3. Go back to the paused run and press **Discard this run**. Read the dialog, then confirm.
4. Trigger that phase again.
5. Now repeat step 1 against the work item with the **parked** run from TC-702.

**Expected**
- At step 2 the trigger is refused, and the message says **you paused this work item's run** and
  tells you to open it and resume it. It does **not** say "wait for it to finish".
- At step 3 the dialog warns the run can't be resumed afterwards and you'd start the phase from the
  beginning. The second button reads **Keep it paused**.
- At step 4, after discarding, the phase starts normally.
- At step 5 the **parked** run does **not** block the trigger — it starts.

**Pass / Fail**
- PASS if a paused run refuses a second run with its own wording, a discard frees the work item, and
  a parked run still allows a re-trigger.
- FAIL if a **second run starts while one is paused** (two agents on one branch), if the refusal
  tells the reader to wait for a run that is not running, or if a parked run has stopped being
  re-triggerable.

**Notes**
- Bugs S.No 291. Step 5 is not padding: `stalled` is deliberately excluded from this guard so that a
  run parked by an error or an offline machine can be started again (S.No 89 / S.No 157). The two
  behaviours live in one tuple and the second is easy to lose while changing the first.

---

### TC-709 · Nothing starts a phase without asking first

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | UX |
| Priority | Medium |
| Screen | `/runs`, `/work-items/:id`, `/runs/:id`, `/recovery` |
| Persona | P1 Owner-Admin |
| Automation | Partly |

**Preconditions**
- A project with a task, a defect, and a test case that has no script yet.
- For the last step, a failed run (TS-14 leaves one) — or skip that step and note it.

**Steps**
1. On `/runs`, trigger a phase that has **never run** on this work item. Read what appears, then
   decline.
2. Trigger a phase that **has** run before. Read the dialog.
3. On a **task**, press **Trigger phase**. Decline.
4. On a **defect**, press **Trigger Fix**. Decline.
5. On a test case with no script, press **Generate script**. Decline.
6. On a **failed** run's console, press **Retry run**. Decline.

**Expected**
- **Every one** of steps 1–6 opens a confirmation first. None of them starts anything.
- Each dialog names what will run and says it runs on **your companion**.
- At step 2 the dialog **also** warns that running the phase again replaces what it produced last
  time — and the confirm button reads **Re-run phase** rather than **Start phase**.
- Declining any of them starts nothing: no new run appears on `/runs`.

**Pass / Fail**
- PASS if all six ask first and all six start nothing when declined.
- FAIL if **any** of them starts a run on a single click. Note which — a site that does not ask is a
  separate defect from a site that asks badly.

**Notes**
- Bugs S.No 293. Four of these six asked nothing at all before 2026-10-03, and the two that did only
  asked when the phase had run before — so a first-ever trigger never asked, anywhere.
- The "**a run is already in progress**" message is deliberately **not** one of these: it is a
  refusal, not a question, and it correctly has no confirm button. Do not log it as a missing
  confirmation.

---

### TC-710 · Paused and Stopped are told apart on screen

| Field | Value |
|---|---|
| Suite | TS-07 Phases & Runs |
| Type | UX |
| Priority | Medium |
| Screen | `/runs`, `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- One **paused** run (TC-706) and one **parked** run (TC-702), ideally both visible in the runs
  table.

**Steps**
1. Look at both rows in the runs table.
2. Open each run console and read the chip and the banner.
3. On the paused run, read the run log lines.

**Expected**
- The paused run reads **Paused by you**; the parked one reads **Stopped — your machine stopped
  reporting**. Never the same word for both.
- The paused run's banner says it is paused and what is kept. It shows **no error and no reason**,
  because nothing went wrong.
- The parked run's banner still **does** give a reason.
- No log line on the paused run contains code, a stack trace, a class name, or anything resembling
  `tonic::transport::Error`.

**Pass / Fail**
- PASS if the two states are distinguishable at a glance and the paused one shows no error.
- FAIL if both read "Paused"; if a paused run displays an error or failure reason; or if **any**
  technical text appears on screen.

**Notes**
- Bugs S.No 294 (the two labels) and S.No 292 (the technical text, which did reach the screen once
  during development and is now covered by a test). Standing rule: no machine words on a client's
  screen.

---

### TC-711 · The run console describes the task in words, not in our names for things

| Field | Value |
|---|---|
| Suite | TS-07 Runs & Console |
| Type | UX |
| Priority | High |
| Screen | `/runs/:id` |
| Persona | P1 Owner-Admin · P3 Engineer |
| Automation | Partly |

**Preconditions**
- A run that has progressed past its first step. A build run is best — it produces the most lines.
  A finished or failed run from a previous day works just as well.

**Steps**
1. Open the run console and **read every line in the progress list, top to bottom.**
2. Look specifically at the end of each line, after any dash.
3. Open a run that **failed**, and read the red banner above the list as well.
4. Open a run that is **still going** and watch a few new lines arrive.

**Expected**
- Every line is a sentence about the task. "Started on your machine." "Sent to your machine." "Your
  machine reported back." "Code review finished — 6 problems, 2 to fix before merging."
- **No line is a name with the spaces put in**: nothing like "Phase dispatched", "Review parse
  mismatch", "Phase empty result", "Build remediation exhausted retry", "Workitem transitioned".
- **Nothing after a dash is a machine value.** Not an identifier of any kind, not a branch name, not
  a word like `companion` or `06_task_breakdown` on its own, and not a programming error.
- Two lines that arrive seconds apart say **different** things.
- The red banner either explains the failure in a sentence, or says the task stopped and can be run
  again — never a command line, an exit code or the words "stderr".

**Pass / Fail**
- PASS if you could read the whole list aloud to a client without translating anything.
- FAIL on any line you would have to explain, any identifier, or any programming error.

**Notes**
- Bugs S.No 301 and 302. There are 43 different things that can appear here, and a given run shows
  only some of them, so this case is worth repeating on runs of different phases — a planning run, a
  build, one that paused, one that failed.
- The wording comes from the **platform**, not the browser, so the same words appear for everyone.
  A missing one is caught by a test before it ships, but a *badly worded* one is not — if a line is
  technically correct and still reads oddly, raise it.

---

### TC-712 · No identifier appears on the run console

| Field | Value |
|---|---|
| Suite | TS-07 Runs & Console |
| Type | UX |
| Priority | Medium |
| Screen | `/runs/:id`, `/recovery`, `/clarifications`, task breakdown |
| Persona | P1 Owner-Admin |
| Automation | Partly |

**Steps**
1. On a run console, read the trail at the very top, the heading, and the line beneath it.
2. **Hover over** the work item and the heading, and read any tooltip.
3. Open a **parked** run from `/recovery` and read its details list.
4. Open **Clarifications**, expand an answered question, and read the link at the bottom.
5. On a run that was **retried automatically**, read the blue "Automatically retried" box.
6. Open a **task breakdown** artifact and read the line under each task's name.

**Expected**
- None of these shows a 36-character identifier, or the first eight characters of one. In
  particular: no **"Run ID"** field anywhere, and the trail at the top reads like the heading —
  "Implementation · WI-18" — not "Run 3f9a1b2c".
- Each of the links names where it goes in words: "Open the run that asked this", "Open the new
  attempt — Running".
- The task list shows each task's **number** beside its status, or just the status.

**Pass / Fail**
- PASS if nothing on these screens is a machine identifier, including in tooltips.
- FAIL on any id fragment, under any label.

**Notes**
- Bugs S.No 304. The run's id is still in the **address bar**, which is where support takes it from.
- Step 2 matters: a second copy of the id used to be a tooltip, where it survived the first pass.

---

### TC-713 · A phase sent to a machine that isn't connected says so, instead of looking busy

**Why this case exists.** Dispatching a phase marks the run "running" immediately, while separately
recording that no machine has picked it up. The console used to read only the first of those, so a
run nobody had claimed showed a live progress panel — for up to the two hours until the timeout
parked it. Status alone cannot tell the two apart; this case checks the screen no longer tries to.

**Setup**
- A project with a companion that has connected at least once.
- **Stop the companion**, and wait until the status in the top bar reads "Companion: not connected"
  (up to about a minute — it passes through amber "checking…" first).

**Steps**
1. Trigger any phase for a work item in that project. If the trigger button is greyed, that is
   TC-714 working — use a run already dispatched before you stopped the machine.
2. Open that run's console.
3. Start the companion again and watch the same console.
4. Separately, open a run that the companion **had already picked up** before it was stopped.

**Expected**
- At step 2 a red box reads **"Your machine isn't connected — this hasn't started"**, with
  "Nothing is lost. Reconnect your machine and it will pick this up on its own." and a
  **Reconnect your machine** link to Connect Machine.
- The old line **"Waiting to start. This begins on its own — nothing to do."** does **not** appear
  while the machine is missing.
- At step 3 the red box disappears on its own, with nothing to dismiss.
- At step 4 there is **no** such box: that machine claimed the work and is doing it, it has just
  gone quiet. A companion only reports at the end of a phase.

**Pass / Fail**
- PASS if an unclaimed run on a missing machine says so, and a claimed one says nothing.
- FAIL if a stranded run shows as plainly running, or if a run already being worked on is described
  as not started — that one would invite somebody to discard work in progress.

**Notes**
- Bugs S.No 308. The wording is the banner that had existed in the internal design catalogue since
  S-19 was built; nothing had ever connected it to live data.

---

### TC-714 · You cannot start work on a machine that isn't connected

**Why this case exists.** Phases & Runs already refused, but three other screens did not and nor did
the server, so the same action was blocked in one place and accepted in three — each sending work
nowhere.

**Setup**
- As TC-713: a companion that has connected before, now stopped, and the status reading
  "Companion: not connected".

**Steps**
1. Open a **task** work item and look at **Trigger phase**.
2. Open a **defect** work item and look at **Trigger Fix**.
3. Open a story's **Test Cases** and look at **Generate script** on a case that is not automated.
4. Open **Phases & Runs** and look at the phase buttons.
5. Start the companion again and repeat steps 1–3.

**Expected**
- At steps 1–3 each button is **greyed**, with a line beside it reading **"Your machine isn't
  connected, so this can't start yet."** and a **Reconnect your machine** link.
- If no machine was ever connected for this project, that line instead reads **"You haven't
  connected a machine yet"** with **Connect your machine** — never "re-connect".
- Step 4 behaves as it already did.
- At step 5 all three work normally again, with no leftover message.

**Pass / Fail**
- PASS if all four screens agree, and all of them recover.
- FAIL if any one of them still offers to start work, and equally if a button stays greyed after the
  machine is back — a guard that blocks healthy work is not a fix.

**Notes**
- Bugs S.No 309. The server refuses this too, which a screen cannot demonstrate: the status a page
  holds can be up to two minutes old, and a page left open since before the machine dropped knows
  nothing. Starting a phase **before** starting your machine still works on purpose — the dispatch
  waits for it, which is how onboarding is meant to go.

---

### TC-934 · The run console no longer reports the briefing being shortened

**Why this exists.** Before 2026-10-07 a run showed **"Manifest truncated"** on almost every
phase — one build run recorded it seven times, alternating implementation and code review through
four remediation cycles. It was real: roughly a third of the knowledge retrieved for the agent was
deleted on every dispatch. This case is the headline proof that it has stopped.

**Setup.** A project with a connected machine and at least one work item that has produced a few
documents, so the knowledge index has something to retrieve.

**Steps**
1. Trigger **Implementation** on a task and open the run console.
2. Watch the console to completion (or to the first gate).
3. Repeat for a second phase on the same work item.

**Expected**
- **"The agent's briefing was shortened to fit" never appears.** Neither does the older wording,
  "Manifest truncated".
- Every other console line reads exactly as it did before.

**Pass / Fail**
- PASS if neither phase reports a shortened briefing.
- FAIL if either does. Note the phase and tell the team: the event payload now carries what each
  section was allowed and what it asked for, so the cause is in the record rather than needing a
  reconstruction.

**Notes**
- Bugs S.No 337. The message itself is not a bug and is deliberately kept — it is the instrument
  that proves this. Seeing it on a very large project is information, not a regression.

---

### TC-935 · A long document can be read all the way through

**Why this exists.** A document over the read limit used to come back with its beginning and a flag
saying it had been shortened, and **there was no way to ask for the rest** — for anybody. A long
PRD or architecture document is exactly what exceeds that limit, and every later phase reads it
through that one call.

**Setup.** A project with a document artifact larger than 400 KB (a long imported PRD, or a
wireframe set).

**Steps**
1. Open the document in the artifact registry and preview it.
2. Download it.
3. Run a downstream phase that consumes that document (e.g. Architecture after a long PRD).
4. Open the produced document and check it against the **end** of the source document.

**Expected**
- Preview and download are unchanged.
- The produced document reflects content from the **whole** source, including its final sections —
  not only its opening.

**Pass / Fail**
- PASS if requirements written at the END of the source are reflected downstream.
- FAIL if the agent's output consistently covers only the first part of a long source.

**Notes**
- Bugs S.No 338. The agent reads this in windows now and is told to keep asking until there is no
  more; a failure here looks like an agent that has simply not seen the later half.

---

### TC-936 · A code review reads a long file to the end

**Why this exists.** A file longer than the inlined limit had its tail cut, and the review still
reported as a **completed review**. Worse, when the diff could not be read at all the agent was
told to "fetch the PR via the platform tools" when no tool it had could read a repository file —
an impossible instruction, which most likely meant it reviewed nothing.

**Setup.** A task whose implementation changes a file of more than ~16,000 characters.

**Steps**
1. Let the task run through Implementation and into Code Review.
2. Open the review document and read the findings.
3. Check whether any finding references the **later** part of the long file.

**Expected**
- The review discusses the whole file, not only its opening.
- Where something was still too long to inline, the briefing names an exact position to resume
  from, and the agent fetches the remainder itself.

**Pass / Fail**
- PASS if the review covers the end of a long file.
- FAIL if findings stop consistently at the same point in long files — the signature of a cut tail.

**Notes**
- Bugs S.No 339 and 343. The reviewer is the only agent allowed to read repository files; if a
  PLANNING phase is ever seen reading repository source, that is a separate and more serious
  finding, so report it immediately.
