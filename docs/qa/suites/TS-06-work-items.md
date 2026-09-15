# TS-06 · Work Items

Covers `/work-items` — the lifecycle board, the list view, the filters, the create drawer — and the
three type-adaptive detail screens at `/work-items/:id` (epic, task, defect). **Owner: Tester B**,
working as **P1 Owner-Admin** in workspace `QA Bravo` on project `Payment Gateway v2`. No phase is
triggered anywhere in this suite; the cases that need a work item with real phase history read
Tester C's data and say so.

> **Run these in order.** TC-079 needs a project with **no** work items, so it must run before
> TC-080 creates the first one. TC-081 onwards all reuse the epic created in TC-080.

**Cross-suite dependencies:** only **TC-096** needs a work item that has actually moved through
phases, which only exists once **Tester C has completed TS-07** in `QA Charlie`. Hold TC-096 until C
confirms; mark it Blocked, not Failed, if C is behind. TC-086 and TC-089 used to carry the same
dependency — they no longer do, and are now executable in `QA Bravo` on day one.

**One case triggers a run.** TC-603 (last in the file) deliberately starts one implementation run on
a throwaway task so the re-trigger confirmation modal is reachable. It is the only case in this suite
that does, it runs last, and it needs no companion — see the case for what to expect.

---

### TC-079 · A project with no work items shows the empty state

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | UX |
| Priority | Medium |
| Screen | `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 in workspace `QA Bravo`, with project `Payment Gateway v2` selected in the top bar.
- No work item has been created in this project yet.

**Steps**
1. Click **Work Items** in the sidebar.
2. Read the page heading and the panel below it.
3. Look for the search box, the filter dropdowns and the Board/List toggle.

**Expected**
- The h1 reads `Work Items` and the header has a **+ New Work Item** button.
- The body shows an empty-state panel titled `No work items yet` with the explanatory line
  `Create your first work item to start the lifecycle. Epics run the plan tier; Task Breakdown fans out the build tier.`
- The empty state has its own **+ New Work Item** button.
- The filter row (search box, `Phase: All`, level chips, `Role: All`, `Status: All`, Board/List) is
  **not** rendered while the board is empty.
- No board columns are drawn.

**Pass / Fail**
- PASS if the empty state renders with that exact title and no filter row is shown.
- FAIL if empty columns are drawn instead, if the copy differs, or if the empty state has no way to
  create a work item.

**Test data**
- None.

**Notes**
- Once you create anything, this state is unreachable in the project. If you need to re-run it, do
  so in a second, empty project.

---

### TC-080 · Create an epic from the drawer (happy path)

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Functional |
| Priority | Critical |
| Screen | `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-079 passed; you are on `/work-items` in the empty state.

**Steps**
1. Click **+ New Work Item**.
2. Read the drawer's title and its two fields.
3. Open the `Type` select and read its options.
4. Enter Title `Stripe Webhook Integration`, leave Type as `Epic`.
5. Click **Create**.

**Expected**
- A drawer titled `New work item` opens with a `Title` field marked required (`*`) and placeholder
  `e.g. Stripe Webhook Integration`, and a `Type` select.
- The `Type` select offers exactly four options: `Epic`, `Story`, `Task`, `Defect` — with `Epic`
  preselected.
- The footer has **Cancel** and **Create**; **Create** shows `Creating…` while the request is in
  flight.
- On success the drawer closes and the browser navigates to the new item's detail screen, whose h1
  reads `⚡ Stripe Webhook Integration`.

**Pass / Fail**
- PASS if the epic is created and you land on its detail screen with the title you typed.
- FAIL if the drawer stays open, if the red message `Couldn't create this work item.` appears, or if
  the `Type` select offers a different set of options.

**Test data**
- Title: `Stripe Webhook Integration` · Type: `Epic`

**Notes**
- `test_case` is a fifth work-item type in the system, but it is deliberately not offered here —
  test cases are created from the Test cases screen (TS-13). Its absence is not a defect.
- Note the epic's key (e.g. `WI-1`) from the breadcrumb; later cases refer to it.

---

### TC-081 · The create drawer will not submit without a title

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Negative |
| Priority | High |
| Screen | `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-080 passed. You are back on `/work-items`.

**Steps**
1. Click **+ New Work Item**.
2. With `Title` empty, try to click **Create**.
3. Type three spaces into `Title` and try **Create** again.
4. Type `A`, then delete it, and watch the **Create** button.
5. Click **Cancel**.

**Expected**
- With `Title` empty, **Create** is disabled and clicking it does nothing — no work item is created
  and the drawer stays open.
- Whitespace-only input does not enable **Create**.
- **Create** enables as soon as a non-whitespace character is typed and disables again when it is
  removed.
- **Cancel** closes the drawer, and the board still shows only the epic from TC-080.

**Pass / Fail**
- PASS if submission is blocked for empty and whitespace-only titles and no item is created.
- FAIL if a work item with a blank or whitespace title is created, or if **Create** is enabled with
  an empty title.

**Test data**
- Title: `` (empty), then `   ` (three spaces)

**Notes**
- The required title is enforced by disabling the button, not by showing a validation message. There
  is no inline error text to look for — that is the current design.

---

### TC-082 · The board renders the full lifecycle as columns, in order

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Functional |
| Priority | High |
| Screen | `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-080 passed — at least one work item exists, so the board is no longer empty.
- The `All levels` chip is active and `Board` is selected.

**Steps**
1. Go to `/work-items`.
2. Read the column headings left to right, scrolling the board horizontally to the end.
3. Note the count badge on each column heading.

**Expected**
- Fourteen columns render in this exact order: `Backlog` (first, with no number), then the thirteen
  lifecycle phases `1. Ideation`, `2. Requirements`, `3. PRD`, `4. Architecture`, `5. UX Design`,
  `6. Task Breakdown`, `7. Implementation`, `8. Code Review`, `9. Testing`, `10. Test Automation`,
  `11. Security`, `12. CI/CD`, `13. Deployment`.
- The board scrolls horizontally to reach the later columns; the page itself does not break layout.
- Each column heading carries a count of the cards in it.

**Pass / Fail**
- PASS if `Backlog` comes first, followed by all thirteen phase columns with those labels, numbers
  and order.
- FAIL if `Backlog` is missing or not first, if a phase column is missing, renumbered, out of order,
  or shows a raw key such as `06_task_breakdown` or `task_breakdown`.

**Test data**
- None.

**Notes**
- The three brownfield onboarding phases (`Onboarding`, `Context Bridge`, `Context Extraction`) are
  intentionally excluded from a work item's board. Their absence is correct.

---

### TC-083 · A newly created work item lands in Backlog as not started

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Functional |
| Priority | High |
| Screen | `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-082 passed. The epic `Stripe Webhook Integration` exists and no phase has been run on it.

**Steps**
1. Go to `/work-items` with `All levels` and `Board` active.
2. Find the card for `Stripe Webhook Integration`.
3. Read the card's id, status pill, title and chips.
4. Click the card.

**Expected**
- The card sits in the `Backlog` column — a work item nothing has run on yet is in Backlog, not in
  `1. Ideation`, and it is not hidden.
- The card shows its key (e.g. `WI-1`), the status pill `Not started`, the title
  `Stripe Webhook Integration`, a chip reading `Epic`, and a footer reading `0 artifacts`.
- Clicking the card opens `/work-items/{id}`.

**Pass / Fail**
- PASS if the new epic appears in `Backlog` with the `Not started` pill and the `Epic` chip.
- FAIL if the card is missing from the board, appears in `1. Ideation` or any later column, or shows
  `Running`, `Done` or any `Waiting…` pill before anything has run.

**Test data**
- None.

**Notes**
- Every work item is created in state `proposed`. The **card** pill describes what its phase is doing
  (`Not started` until a phase runs); the **List** view's `Status` column shows the work item's state
  badge, which reads `Draft` for `proposed` (TC-084). There is no UI anywhere for changing a work
  item's state by hand — state only moves as phases run. Do not look for a state control on the
  detail screen.
- The item stays in `Backlog` whichever level chip is active — it does not jump columns when you
  filter to `Tasks` (TC-088).

---

### TC-084 · The Board/List toggle switches views and the list shows the right columns

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Functional |
| Priority | Medium |
| Screen | `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-083 passed.

**Steps**
1. On `/work-items`, click **List** in the segmented control at the right of the filter row.
2. Read the table headers.
3. Read the row for `Stripe Webhook Integration`.
4. Click **Board** to switch back.

**Expected**
- **List** renders a table with exactly these headers, in order: `ID`, `Title`, `Level`, `Phase`,
  `Status`, `Artifacts`, `Owner`.
- The epic's row shows its key under `ID`, `Stripe Webhook Integration` under `Title`, a chip `Epic`
  under `Level`, `Not started` under `Phase`, the badge `Draft` under `Status`, `0` under
  `Artifacts` and `—` under `Owner`.
- Clicking **Board** restores the fourteen-column board (`Backlog` plus the thirteen phases) with
  the same item.

**Pass / Fail**
- PASS if both views render as described and the toggle switches cleanly in both directions.
- FAIL if a header is missing or misnamed, if `Phase` shows something other than `Not started` for
  an item that has never run a phase, or if the toggle does not switch.

**Test data**
- None.

---

### TC-085 · The search box filters the board

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Functional |
| Priority | Medium |
| Screen | `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-084 passed.
- At least two work items exist. If only the epic exists, create a second one first: **+ New Work
  Item** → Title `Refunds API`, Type `Task`.

**Steps**
1. On `/work-items`, click into the box with placeholder `Search work items…`.
2. Type `stripe`.
3. Clear the box and type `zzzznothing`.
4. Clear the box again.

**Expected**
- With `stripe` typed, only `Stripe Webhook Integration` remains on the board; `Refunds API`
  disappears and the column counts drop accordingly.
- The match is case-insensitive — lower-case `stripe` matches the capitalised title.
- With `zzzznothing` typed, no cards remain on the board (the column headings stay, all showing 0).
- Clearing the box restores both cards.

**Pass / Fail**
- PASS if typing filters the board live and clearing restores it.
- FAIL if the search box has no effect, requires an Enter press to apply, or filters case-sensitively.

**Test data**
- Search terms: `stripe`, `zzzznothing`

**Notes**
- Search matches the key, title, type and feature stream — a search for `epic` will legitimately
  match on type, not only on title text.

---

### TC-086 · The Phase filter offers only phases items are actually in

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Functional |
| Priority | Medium |
| Screen | `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-085 passed. `Payment Gateway v2` in `QA Bravo` holds at least two work items and no phase has
  ever been run on any of them.
- No cross-tester dependency: this case is fully executable in your own workspace.

**Steps**
1. Go to `/work-items` with `All levels` and `Board` active.
2. Open the dropdown labelled `Phase: All` and read **every** option in it, top to bottom.
3. Close it, then read the board's column headings.
4. Compare the two lists.

**Expected**
- The dropdown contains **exactly one option**: `Phase: All`. It is not populated with the thirteen
  lifecycle phases, and it is not empty.
- No option anywhere in it reads a raw key such as `01_ideation`, `03_prd` or `ux_design`.
- The board still shows all fourteen columns behind it (`Backlog` plus the thirteen phases), with
  every card in `Backlog` — the *columns* are fixed, the *filter options* are derived from the items.

**Pass / Fail**
- PASS if `Phase: All` is the only option while no item has phase history.
- FAIL if the dropdown lists phases no item is in (e.g. all thirteen), if any option shows a raw
  underscored key, or if the dropdown is absent from the filter row.

**Test data**
- None.

**Notes**
- **What this case really tests** is that the Phase options are *derived from the items on the
  board* rather than hardcoded from the lifecycle — and a board where nothing has run is the
  cleanest possible proof of that, because a hardcoded list would immediately show thirteen entries.
  It no longer waits on Tester C.
- The multi-option behaviour — human labels like `Ideation` / `PRD`, and selecting one to filter the
  board — is verified in **TC-096**, which is the case that legitimately depends on TS-07. Do not
  duplicate that check here.
- The `Phase`, `Role` and `Status` filter boxes size themselves to their longest option, so the longest
  phase a greenfield board can show, `Test Automation`, is never cut off in the closed box. A cut-off
  label in a closed filter box is a defect.

---

### TC-087 · The level chips filter by work-item level

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Functional |
| Priority | High |
| Screen | `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-085 passed. The project has at least one Epic and one Task. Create a Defect too if there is
  none: **+ New Work Item** → Title `Webhook signature check fails`, Type `Defect`.

**Steps**
1. On `/work-items`, read the four chips: `All levels`, `Epics`, `Tasks`, `Defects`.
2. Click **Epics** and read the board.
3. Click **Defects** and read the board.
4. Click **All levels**.

**Expected**
- The four chips read exactly `All levels`, `Epics`, `Tasks`, `Defects`, and the selected one is
  visibly pressed.
- `Epics` shows only the epic; the task and defect cards are gone.
- `Defects` shows only the defect card, and the chip on that card reads `Defect` in the same
  **navy** treatment the `Epic` chip uses. Only the `Task` chip is styled differently.
- `All levels` restores every card.

**Pass / Fail**
- PASS if each chip filters to its own level and `All levels` restores everything.
- FAIL if a chip has no effect, if two chips appear active at once, or if an item of the wrong level
  is shown.

**Test data**
- Defect title: `Webhook signature check fails`

**Notes**
- Stories are shown under `All levels` but have no chip of their own — there is no `Stories` filter.
  That is the current design.
- **The board's `Defect` chip is navy, not orange.** Orange is used for the `Defect` chip on the
  *detail* screen only (TC-095). If you were expecting an orange chip on the board, that expectation
  was wrong — do not raise a defect for the navy one.

---

### TC-088 · The `Tasks` chip switches the board to the build columns

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Functional |
| Priority | High |
| Screen | `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-087 passed and at least one Task exists (`Refunds API` from TC-085).

**Steps**
1. On `/work-items`, click the **Tasks** chip.
2. Read the column headings.
3. Read the line of text above the board.
4. Click **All levels** again.

**Expected**
- The board redraws with exactly three columns, in order: `Backlog`, `Implementation`, `Review` —
  the fourteen-column lifecycle board is replaced, not appended to.
- The note above the board reads
  `Showing tasks from the build tier — fanned out by Task Breakdown.`
- The task card (`Refunds API`, never run) appears in `Backlog`, with the pill `Not started`.
- Clicking `All levels` restores the fourteen columns (`Backlog` plus the thirteen phases), hides
  the note, and the task card is still in `Backlog`.

**Pass / Fail**
- PASS if the columns swap to `Backlog` / `Implementation` / `Review` under `Tasks`, the never-run
  task sits in `Backlog` in both views, and the board swaps back under `All levels`.
- FAIL if the lifecycle columns remain, if the note is missing, if the task card vanishes, or if a
  never-run task lands in `Implementation`.

**Test data**
- None.

**Notes**
- `Defects` does **not** change the columns — only `Tasks` does. That asymmetry is intentional.
- A task in code review sits in `Review`, and a task in implementation sits in `Implementation`.
  Checking that needs a task that has run (TS-07 / TS-14 data); it is not required here.
- If a task is in a later build phase that has no column in this view (e.g. Testing), the board adds
  a column named after that phase, in lifecycle order, rather than misplacing the card.

---

### TC-089 · The Role filter offers only roles that own a phase an item is in

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Functional |
| Priority | Medium |
| Screen | `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-086 passed, in the same state: `Payment Gateway v2` in `QA Bravo` holds at least two work items
  and no phase has ever been run on any of them.
- No cross-tester dependency: this case is fully executable in your own workspace.

**Steps**
1. Go to `/work-items` with `All levels` and `Board` active.
2. Open the dropdown labelled `Role: All` and read **every** option in it.
3. Close it and confirm all your work-item cards are still on the board.

**Expected**
- The dropdown contains **exactly one option**: `Role: All`. It is not pre-populated with the ten
  project roles.
- No option reads a raw value such as `product_owner` or `tech_lead`.
- The board is unchanged — opening and closing the dropdown filters nothing.

**Pass / Fail**
- PASS if `Role: All` is the only option while no item has phase history.
- FAIL if the dropdown lists roles no item's phase belongs to, if any option shows a raw underscored
  value, or if the dropdown is missing from the filter row.

**Test data**
- None.

**Notes**
- Same reasoning as TC-086: the Role options are *derived* from the phase each item is currently in,
  via the phase→role mapping. A board with no phase history is the strongest evidence the list is
  derived and not hardcoded, and it removes this case's old dependency on Tester C.
- The populated variant — human labels like `Product Owner` / `Architect`, and selecting one to
  filter — belongs to **TC-096**. Cross-check any mismatch there against the phase→role table in the
  test plan's §10 before calling it a defect.

---

### TC-090 · The Status filter narrows the board by work-item state

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Functional |
| Priority | Medium |
| Screen | `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-088 passed; at least three items exist, all newly created.

**Steps**
1. On `/work-items`, open the dropdown labelled `Status: All` and read its options.
2. Choose `Proposed`.
3. Reset to `Status: All`.

**Expected**
- The dropdown holds **exactly two** options, in this order: `Status: All` and `Proposed` — one per
  state the items on this board are actually in, and every item you have created is `proposed`.
- `Proposed` is shown capitalised, not as a raw token.
- Choosing `Proposed` leaves every card on the board and removes none of them; the column counts do
  not change.
- Resetting to `Status: All` leaves the board identical.

**Pass / Fail**
- PASS if the dropdown offers exactly `Status: All` and `Proposed`, and selecting `Proposed` keeps
  every card.
- FAIL if the dropdown lists states no item is in (e.g. all six work-item states), if `Proposed`
  is rendered lower-case or underscored, if selecting it empties the board, or if the dropdown is
  missing.

**Test data**
- None.

**Notes**
- The old FAIL criterion ("shows underscored raw values") could not fire: the screen humanises every
  option before rendering it, so an underscore would have to be in the data itself. The option-count
  assertion above is what actually distinguishes a derived list from a hardcoded one.
- Once Tester C's items reach later states, re-open this dropdown on their project to confirm
  multi-state filtering. That extra check is optional.

---

### TC-091 · The epic detail screen shows the plan-tier lifecycle

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Functional |
| Priority | High |
| Screen | `/work-items/:id` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- The epic `Stripe Webhook Integration` from TC-080 exists and has never run a phase.

**Steps**
1. On `/work-items`, click the `Stripe Webhook Integration` card.
2. Read the breadcrumb, heading and meta row.
3. Read the panel below the header.
4. Read the left column, then the right-hand card.

**Expected**
- The breadcrumb reads `Work Items` / the epic's key (e.g. `WI-1`), and `Work Items` links back to
  the board.
- The h1 reads `⚡ Stripe Webhook Integration`, with a chip reading `Epic` and a `Created` date in
  the meta row.
- A panel titled `Lifecycle — Plan tier` renders, annotated `Epic · one pass through plan phases`.
- Inside it a **rail of phase steps** is drawn — one step per lifecycle phase, all of them in the
  not-started treatment, because nothing has run. The panel does **not** read `No phases run yet.`
- The left column has a panel `Description & context` reading `No description yet.` plus a
  `Feature stream` row.
- The right column has a card titled `At a glance` with the rows `Artifacts`, `Open gates`,
  `Clarifications` and `Children` — all `0` for a new epic.

**Pass / Fail**
- PASS if all of those panels render with those exact titles and the Plan-tier panel draws a rail of
  not-started phase steps.
- FAIL if the task or defect layout renders instead, if the `⚡` is missing from the title, if a
  named panel is absent, or if any rail step is drawn as done/running before anything has run.

**Test data**
- None.

**Notes**
- **`No phases run yet.` is unreachable — do not expect it.** The screen only shows that sentence
  when the lifecycle rail comes back with zero phases, and the API always returns one node per
  registered phase whether or not it has run. An earlier version of this case asserted that string;
  it would have failed every time. The dead empty-state is a Low product defect and is **tracked
  separately** — do not raise it.
- The `Latest run` panel is absent until a run exists — that is correct here and is verified in
  TC-096 against an item that has actually run.

---

### TC-092 · The `Test cases` button on an epic opens its test-case screen

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Functional |
| Priority | Medium |
| Screen | `/work-items/:id` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-091 passed; you are on the epic's detail screen.

**Steps**
1. Look at the top-right of the page header.
2. Click **Test cases**.
3. Read the screen you land on.
4. Use the browser Back button.

**Expected**
- A header button labelled `Test cases` is present on the epic screen.
- Clicking it navigates to `/work-items/{id}/test-cases` and a test-cases screen renders — not a
  404 or a blank page.
- Back returns to the epic detail screen.

**Pass / Fail**
- PASS if the button is present and routes to a rendering test-cases screen.
- FAIL if the button is missing, does nothing, or lands on an error page.

**Test data**
- None.

**Notes**
- The contents of the test-cases screen are TS-13's subject. Here you are only proving the entry
  point works.

---

### TC-093 · The task detail screen shows the build-tier lifecycle and its parent

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Functional |
| Priority | High |
| Screen | `/work-items/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A Task exists. Ideally use a task fanned out by Tester C's Task Breakdown (TS-07) so it has a
  parent; otherwise use `Refunds API` from TC-085, which has none.

**Steps**
1. Open the task from `/work-items` (use the `Tasks` chip to find it quickly).
2. Read the heading and meta row.
3. Read the panel below the header — including **every step drawn inside it**, left to right.
4. Read the left column and the right-hand card.

**Expected**
- The h1 is the task's title with **no** `⚡` prefix, and the meta row carries a chip reading `Task`.
- If the task has a parent, the meta row shows `Parent ↖ {first 8 characters of the parent id}` as a
  link back to the parent work item.
- A header button labelled `Trigger phase` is present.
- A panel titled `Lifecycle — Build tier` renders, annotated `Task · build phases only`.
- **Inside that panel the rail draws the full plan-tier lifecycle** — `Ideation`, `Requirements`,
  `PRD`, `Architecture`, `UX Design` and the rest — not the build phases the panel title promises.
  Record the steps you actually see.
- The left column shows a panel titled `Description`; the right column shows `At a glance` with the
  rows `State`, `Artifacts` and `Open gates`.
- A `Related work items` panel appears only if this task has children.

**Pass / Fail**
- PASS if the build-tier layout renders with those exact panel titles, the parent backlink navigates
  to the parent, and the rail's contents match the description above.
- FAIL if the panel title reads `Lifecycle — Plan tier` on a task, if the `Trigger phase` button is
  missing, or if the parent backlink is broken.

**Test data**
- None.

**Notes**
- **The rail contents are wrong and that is a known, separately tracked defect.** The panel is
  correctly titled and annotated for the build tier, but the endpoint behind it works out which tier
  the item belongs to and then never applies it — so every work item, task included, gets the same
  full list of phases. An earlier version of this case checked only the panel *title*, which meant it
  passed while a task displayed plan phases. You are now asked to look inside the panel. **Confirm
  it, note the steps you saw, and do not raise a duplicate defect.**
- **`No phases run yet.` is unreachable here too** — the rail always has phases to draw. Do not
  expect that sentence.
- Do **not** click **Trigger phase** on this task. Triggering is covered by TC-603, which uses a
  throwaway task and runs last.
- The parent backlink shows a truncated id, not the parent's title or key. Slightly unhelpful, but
  known and intentional today.

---

### TC-094 · The `Repository` card appears only on multi-repo projects

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Negative |
| Priority | Medium |
| Screen | `/work-items/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- `Payment Gateway v2` currently has one repository, `acme/payments-api` (Tester A's TS-03 setup).
- You can add repositories on `/repositories`.

**Steps**
1. Open the task from TC-093 and check the right-hand column for a `Repository` card.
2. Go to `/repositories` and add a second repository, e.g. `acme/payments-web`, role `frontend`.
3. Return to the task and reload the page.
4. Read the `Repository` card and open its select.

**Expected**
- With one repository, **no** `Repository` card is rendered — there is nothing to choose between.
- With two repositories, a card titled `Repository` appears with a labelled select
  `Target repository`.
- The select's first option reads `— default repository —`, followed by each repository as
  `{name} · {role}`.
- Under the select a line reads `You can redirect this task until its build starts.`

**Pass / Fail**
- PASS if the card is absent on a single-repo project and present with those exact labels once a
  second repository exists.
- FAIL if the card shows on a single-repo project, if the first option is missing or worded
  differently, or if the select is empty.

**Test data**
- Second repository: `acme/payments-web`, role `frontend`

**Notes**
- Repo topology is derived from repository count (0–1 = single, 2 = split, 3+ = multi); there is no
  topology picker to set.
- Once a build has started on the task the select is disabled and the line changes to
  `Locked — the build has started.` — that variant needs a run, so leave it to TS-07.

---

### TC-095 · The defect detail screen shows the remediation lifecycle

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Functional |
| Priority | High |
| Screen | `/work-items/:id` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- The defect `Webhook signature check fails` from TC-087 exists and is not closed.

**Steps**
1. On `/work-items`, click the **Defects** chip and open the defect card.
2. Read the heading and meta row.
3. Read the panel below the header.
4. Read the left column and the right-hand card.

**Expected**
- The meta row carries an orange chip reading `Defect`.
- A header button labelled `Trigger Fix` is present (note the capital F).
- A panel titled `Lifecycle — Remediation` renders, annotated `minimal rail`. Like the task screen it
  draws a rail of lifecycle steps rather than the `No phases run yet.` line — see the Notes.
- The left column shows a `Description` panel containing a red banner titled `Open` — a defect that
  is running its fix shows `Fix running on your companion`, and a closed one shows `Defect closed`.
- The meta row's `Defect` chip is **orange** on this screen (unlike the navy chip the board uses —
  TC-087).
- The right-hand card `At a glance` lists `Parent` and `Status`.

**Pass / Fail**
- PASS if the remediation layout, the `Trigger Fix` button, the orange `Defect` chip and the `Open`
  banner all render.
- FAIL if the task or epic layout renders for a defect, if the button reads `Trigger phase`, or if
  the banner is missing.

**Test data**
- None.

**Notes**
- **`No phases run yet.` is unreachable** — the lifecycle endpoint always returns one node per
  registered phase, so the rail is never empty and the empty-state sentence never renders. Same
  root cause as TC-091 and TC-093, and **already tracked**; do not raise a duplicate.
- Do **not** click **Trigger Fix** — it starts a run (TS-07 / TS-14 territory).
- On a closed defect the `Trigger Fix` button disappears entirely; that variant needs C's data.

---

### TC-096 · The board reflects a work item that has moved through phases

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | E2E |
| Priority | High |
| Screen | `/work-items`, `/work-items/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- **Depends on TS-07.** Tester C has run at least one phase to completion and approved its gate on
  an epic in `QA Charlie` — confirm with C before starting.
- Either C runs these steps in their own workspace and hands you the screenshots, or you pair with C
  at their machine. You cannot see another tenant's work items from `QA Bravo`, and you must not
  trigger a run yourself.

**Steps**
1. On `/work-items` in the workspace that has the phased epic, find its card.
2. Note which column the card sits in and what status pill it shows.
3. Switch to **List** and read that item's `Phase` and `Status` cells.
4. Open the item and read the `Lifecycle — Plan tier` panel and the `Latest run` panel.
5. Open the `Phase: All` and `Role: All` dropdowns and read their options (the populated half of
   TC-086 / TC-089).
6. Have C trigger the item's next phase. **Wait at most 40 minutes** for it to reach its gate, then
   return to `/work-items` and re-check the column.

**Expected**
- The card sits in the column matching its current phase — e.g. an item whose latest phase is
  Requirements sits under `2. Requirements`, not under `1. Ideation` and not under `Backlog`.
- Its status pill describes the latest run of that phase and reads one of exactly these:
  `Running`, `Done`, `Failed`, `Cancelled`, or a waiting pill. A waiting pill reads
  `Waiting for you` **only** when the open question or gate is one you (P1) may answer or decide;
  otherwise it reads, in grey, `Waiting for an answer` (open question), `Waiting for review` (open
  gate) or `Waiting for approval` (the run is at its gate but no approval has reached the card).
  `Not started` must not appear once a phase has run.
- In **List**, `Phase` shows the same human-readable phase name (never `Not started`, never a raw
  key). `Status` shows the work item's state badge — the same badge as before this change, not the
  card's pill — so it may read e.g. `Draft`, `Needs answer` or `Phase gate` while the card says
  `Waiting for you` or `Done`.
- `Phase: All` is now followed by one human-labelled option per phase items are in (`Ideation`,
  `PRD`, `UX Design` — never `03_prd`), and `Role: All` by human role labels (`Product Owner`,
  `Architect` — never `product_owner`). Selecting one filters the board; resetting restores it.
- On the detail screen the `Lifecycle — Plan tier` rail shows the completed phases as done and the
  current one as current, and a `Latest run` panel appears with a `Phase` row, a `Status` row and a
  link reading `View run console ↗`.
- After the next phase reaches its gate, the card has moved to the next column without a manual
  reload of the browser tab beyond revisiting the board.

**Pass / Fail**
- PASS if the board column, the card pill, the list `Phase` cell, the two filter dropdowns and the
  detail rail all agree with the item's real current phase, before and after it advances.
- FAIL if the card stays in `Backlog` or `1. Ideation` after a later phase completes, if the board
  column and the list `Phase` cell disagree, if the card reads `Waiting for you` on a gate or
  question you may not decide or answer, if a dropdown shows a raw underscored key, or if
  `View run console ↗` does not open the run.
- **Blocked, not Failed**, if step 6's run has not reached its gate within 40 minutes, or if C has
  no completed phase to show you at all.

**Test data**
- C's epic `Stripe Webhook Integration` in `QA Charlie`.

**Notes**
- **Card pill vs list badge.** The card's pill comes from the latest run; the list's `Status` badge
  comes from the work item's own state. `Awaiting gate` is never rendered on either — an open gate
  reads `Waiting for you` / `Waiting for review` on the card and `Phase gate` in the list. And
  `Phase complete` cannot appear in the list for a plan-tier epic: nothing in the plan tier ever
  moves an epic to the `done` state, so the list badge stays `Draft` between runs. That is known and
  separately tracked; do not raise it.
- **Whose turn it is.** The `Waiting for you` rule matches the **Approve** and **Answer** buttons:
  if P1 would see **Approve** on the gate or **Answer** on the question, the card says
  `Waiting for you`. To see the grey variant, look at the same card while signed in as a user who
  cannot decide that gate (e.g. an engineer).
- The board reads the item's *current phase*, not its feature stream. If you see items grouped by
  something that looks like a stream name, that is a regression worth a defect.
- Agent phases take 20–30 minutes and the console can be silent for long stretches (a known issue
  in the plan's §1). Silence is not evidence of a hang — only the 40-minute cap is.

---

### TC-601 · An unknown work-item id shows a not-found panel, not a broken epic screen

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Negative |
| Priority | Medium |
| Screen | `/work-items/:id` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 in workspace `QA Bravo` with `Payment Gateway v2` selected.
- TC-091 passed, so you know what a real epic detail screen looks like.

**Steps**
1. Open a real work item from `/work-items` and copy its URL from the address bar.
2. Edit the address bar so the id is replaced with `00000000-0000-0000-0000-000000000000`,
   and press Enter.
3. Read the whole page.
4. Repeat with a non-UUID id: `/work-items/not-a-real-id`.
5. Use the browser Back button to return to a working screen.

**Expected**
- A brief loading panel may flash, then the page settles on a single panel whose entire content is
  the sentence `Work item not found.`
- **No epic content is rendered around it**: no `⚡` heading, no `Work Items /` breadcrumb, no
  `Lifecycle — Plan tier` panel, no `At a glance` card, no `Test cases` button.
- The app does not crash, does not show a blank white page, and does not show a raw error or a
  stack trace.
- Both the UUID-shaped and the non-UUID id behave the same way.
- Back returns to a working screen with the sidebar intact.

**Pass / Fail**
- PASS if both bad ids land on the bare `Work item not found.` panel with no partial epic layout.
- FAIL if the screen renders any part of an epic layout, shows a blank page, spins forever, or
  surfaces a raw error.

**Test data**
- Bad ids: `00000000-0000-0000-0000-000000000000` and `not-a-real-id`.

**Notes**
- Typing a URL by hand is fair game here — it is the only way a user reaches this state (a stale
  bookmark, a link to an item they cannot see), and it needs no tooling beyond the address bar.
- An unknown id is routed to the *epic* screen internally, because the router picks the layout from
  the item's type and an unknown id has none. That is harmless — the epic screen checks for a
  missing item before it renders anything — but it is why this case asks you to confirm that **no**
  epic furniture appears alongside the message.
- The message is deliberately plain: there is no "back to the board" link on this panel. Note that
  as a Low UX observation if you like; the case passes without one.

---

### TC-602 · The Task Breakdown screen's greenfield default state

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | UX |
| Priority | Medium |
| Screen | `/work-items/:id/breakdown` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- The epic `Stripe Webhook Integration` from TC-080 exists and has **no** child work items (no Task
  Breakdown phase has been run on it).
- No task tracker is connected in `QA Bravo`.

**Steps**
1. Open the epic from `/work-items` and note its id from the address bar.
2. Search the epic detail screen — header, both columns, the `At a glance` card — and the sidebar
   for any link or button leading to a task-breakdown screen.
3. Type the URL by hand: `/work-items/{that id}/breakdown`.
4. Read the whole card: the large number, the heading, the space where a banner would be, and the
   footer buttons.
5. Click **Connect a task tracker**, then use the browser Back button.

**Expected**
- **There is no in-app link to this screen anywhere** — not on the epic, not in the sidebar. The URL
  is the only way in.
- The screen renders a breadcrumb reading the epic's title, then `Task Breakdown`.
- A large `0` is shown above the heading `No task work items yet`.
- With zero tasks, **no** explanatory paragraph and **no** banner render — the card is just the
  count, the heading and the buttons.
- Two footer buttons render: **Go to board** and **Connect a task tracker**.
- **Connect a task tracker** navigates to `/integrations`.

**Pass / Fail**
- PASS if the screen renders that exact zero-task layout and the CTA reaches `/integrations`.
- FAIL if the screen 404s or renders blank, if the heading is pluralised wrongly, if a banner or
  paragraph appears with zero tasks, or if the CTA is inert.

**Test data**
- None.

**Notes**
- **The missing navigation is the finding, not an execution problem.** Record "no in-app entry
  point to `/work-items/:id/breakdown`" as a Medium UX defect if it is not already logged — a screen
  no user can reach is a screen that will rot.
- Once tasks exist the card changes shape: the count, an explanatory paragraph, a banner
  (`Saved in the platform` with no tracker connected, `Pushed to Jira backlog` with one), and the
  second button becomes **Back to epic**. That populated variant needs a Task Breakdown run — leave
  it to Tester C and do not try to produce it here.
- If Tester B's TS-04 pass left a task tracker connected in `QA Bravo`, the banner behaviour above
  still holds at zero tasks (no banner renders either way). Only the populated variant differs.

---

### TC-603 · Re-triggering a phase on a task asks for confirmation first

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Functional |
| Priority | High |
| Screen | `/work-items/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- **Run this case last in the suite.** It is the only TS-06 case that starts a run, and the run it
  starts changes the throwaway task's badge on the board.
- A disposable Task exists in `QA Bravo` that no other case asserts against. Create one now:
  **+ New Work Item** → Title `Re-trigger probe`, Type `Task`.
- No companion is enrolled in `QA Bravo` — expected, and fine; see the Notes.

**Steps**
1. Open the `Re-trigger probe` task and click **Trigger phase**.
2. Note what happens: the button briefly shows a spinner and a run is created. Do **not** wait for
   the run and do **not** open the run console.
3. Reload the page, then click **Trigger phase** a second time.
4. Read the modal's title and body in full.
5. Read the modal's footer buttons.
6. Dismiss the modal with **Close** — do not press the other button.
7. Reload the page and confirm no additional run was started.

**Expected**
- The **first** click starts a run with no confirmation at all.
- The **second** click opens a modal instead of starting anything. With the first run still in an
  active state the modal is titled `A run is already in progress`, and its body reads
  `This work item already has a run in progress. Wait for it to finish, or open the run to take it
  over, before starting a new one.`
- That modal's footer offers **Close** and **Open current run**. There is no "start anyway" control.
- Dismissing the modal starts nothing: after the reload the task still has exactly one run.

**Pass / Fail**
- PASS if the second trigger is intercepted by a confirmation modal that starts no run, and
  dismissing it leaves the task with a single run.
- FAIL if the second click silently starts a second run, if no modal appears, if the modal offers a
  control that starts a run while one is in progress, or if dismissing it triggers anyway.
- **Blocked, not Failed**, if the first trigger returns a red error banner instead of starting a run
  — that is a trigger defect, not a modal defect, and it leaves this case with nothing to observe.

**Test data**
- Task title: `Re-trigger probe`

**Notes**
- **You need no companion and you must not wait for the run.** With none enrolled the run sits in an
  active state and eventually parks or fails on its own; either outcome is fine, because this case
  only tests what the *button* does. Cap any waiting at **2 minutes** — nothing here requires a
  completed run.
- There is a **second** variant of this modal, titled `Re-run implementation?`, with the body
  `This task has already run. Running it again starts over and replaces this phase's artifacts — it
  does not create duplicates. The previous run stays in the history. Continue?` and a **Re-run
  phase** button. It appears only once the task's latest run has left its active states. If your
  probe run settles inside your session, click **Trigger phase** again, confirm that copy, and
  dismiss with **Cancel**; otherwise record that variant as not covered and move on.
- Leave the probe task in place afterwards. There is no delete control, and its presence changes
  the card counts — take it into account if you re-run TC-085 or TC-090.

---

### TC-604 · A non-admin engineer can create work items

| Field | Value |
|---|---|
| Suite | TS-06 Work Items |
| Type | Permission |
| Priority | High |
| Screen | `/work-items`, `/work-items/:id` |
| Persona | P10 Engineer |
| Automation | No |

**Preconditions**
- P10 (`qa+b.eng@…`, role `engineer` on `Payment Gateway v2`, **not** a tenant admin) exists in
  `QA Bravo` — invited by Tester A's TS-02 flow or by you from `/admin/users`.
- TC-080 passed, so the board is not empty.

**Steps**
1. Log out and log back in as P10 with password `QaTest-2026!`.
2. Go to `/work-items` and look for the **+ New Work Item** button.
3. Click it, enter Title `Engineer-created item`, leave Type as `Epic`, and click **Create**.
4. Note where you land and whether the item exists.
5. Go back to `/work-items` and confirm the new card is on the board.
6. Log out, log back in as P1, and confirm the same card is visible to the admin.

**Expected**
- P10 reaches `/work-items` and the **+ New Work Item** button is **not** hidden.
- The create drawer opens and **Create** succeeds: the drawer closes and P10 lands on the new item's
  detail screen with the h1 `⚡ Engineer-created item`.
- The card appears on the board for P10 **and** for P1 — the work item is real, not a local
  illusion.
- At no point is a permission message shown.

**Pass / Fail**
- PASS if a role-`engineer` account creates a work item that persists and is visible to the admin —
  confirming the endpoint applies no role check.
- FAIL if the item is created for P10 but is **not** visible to P1, or vice versa. That is a
  data-scoping problem, not a permission one — raise it as its own, higher-severity defect.
- Record the *expected* product behaviour in your note: work-item creation should be limited to the
  roles that own the plan tier, not open to every signed-in member.

**Test data**
- P10 login: `qa+b.eng@edvensoft.com` / `QaTest-2026!`
- Title: `Engineer-created item`

**Notes**
- **This case passes by demonstrating a missing permission check**, which is why its PASS criterion
  reads backwards. Work-item create and patch inherit the project-wide default of "any signed-in
  member", so an engineer can add and edit items freely. The gap is **already tracked** — confirm
  it, reference the existing entry, and do not raise a duplicate.
- The same root cause covers the *patch* path (the repository select on a task, TC-094). Do not
  write it up twice; note in the tracker that create and patch share one defect.
- Delete nothing afterwards — the product has no delete control, so `Engineer-created item` stays on
  the board. Take it into account if you re-run TC-085 or TC-090.
