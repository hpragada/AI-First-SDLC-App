# TS-12 · Shell, Navigation & Dashboard

The frame every other suite is tested inside: the sidebar, the top bar, the account menu, and the
workspace dashboard at `/`. If this suite is broken, everyone else's cases are unreliable — which is
why it runs on **day 1**. **Owner: Tester B.**

**Run these in order.** TC-167 to TC-173 cover the shell and must pass before the dashboard cases
are meaningful. TC-169 needs a non-admin persona (P10 Engineer) and TC-170 needs two projects, so
have both ready before you start.

Most cases run as **P1 Owner-Admin**; the permission case is explicit about its persona. No case
here triggers a phase run, so no companion is required — but the companion pill is still checked
(TC-173), and it is expected to read `Companion: Offline` in Tester B's workspace.

**ID note.** The plan reserves TC-167 – TC-180 for this suite and that range is fully used. Cases
added by the pack audit continue at **TC-261**, which collides with nothing.

---

### TC-167 · Every sidebar item navigates to its route and takes the active highlight

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | Functional |
| Priority | High |
| Screen | All (app shell) |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1 (a workspace admin, so every sidebar item is visible) with a project selected.
- **Note which track the selected project is.** `Onboarding` is shown only on a **brownfield**
  project. On `Payment Gateway v2` (greenfield) it is correctly absent — see the Notes.

**Steps**
1. Read the sidebar top to bottom and note the brand text, the group headers and every item label.
2. Click each item in turn and record the resulting URL and which item is highlighted:
   `Workspace Dashboard`, `Work Items`, `Phases & Runs`, `Gates`, `Clarifications`,
   `Artifacts & Traceability`, `Accessibility`, `Project Profile`, `Integrations`, `Repositories`,
   `Test Reporting`, `Connect Machine`, `Workspace Admin` — plus `Onboarding` if the selected
   project is brownfield.
3. Now type these routes into the address bar one at a time and note which sidebar item is
   highlighted for each: `/transcripts`, `/traceability`, `/contracts`, `/setup`.

**Expected**
- The brand reads `edvensoft` in lowercase.
- The first group has **no** section header. The second group is headed `Project`. The third group is
  headed `Admin`.
- Each item lands on its route and becomes the highlighted item:
  `/`, `/work-items`, `/runs`, `/gates`, `/clarifications`, `/artifacts`, `/a11y/pages`, `/profile`,
  `/integrations`, `/repositories`, `/test-reporting`, `/connect`, and `Workspace Admin` →
  `/admin/users`. On a brownfield project, `Onboarding` → `/onboarding`.
- **`Accessibility` is always present**, on every project and before any audit has ever run, and it
  lands on `/a11y/pages` — the Pages & audit tab, **not** `/a11y` and not the review queue.
- Exactly one item is highlighted at a time.
- On the four routes in step 3 the highlight falls on the parent item: `/transcripts` highlights
  `Phases & Runs`; `/traceability` highlights `Artifacts & Traceability`; `/contracts` highlights
  `Repositories`; `/setup` highlights `Connect Machine`.

**Pass / Fail**
- PASS if all thirteen items on a greenfield project (fourteen on brownfield, with `Onboarding`)
  navigate correctly and the four parent-highlight routes behave as listed.
- FAIL if any item 404s, lands on the wrong route, or leaves no item highlighted; or if two items are
  highlighted at once.
- FAIL — **High** — if `Accessibility` is missing, or if it lands on the review queue rather than
  Pages & audit.
- FAIL — **Medium** — if `Onboarding` appears on a greenfield project.

**Notes**
- **Corrected 2026-09-17.** This case previously omitted `Accessibility` and listed `Onboarding` as
  always present. Both are wrong against the shipped shell: `Accessibility` is a permanent item
  (`AppShell.tsx:80`) and `Onboarding` is now conditional on `track !== "greenfield"`
  (`AppShell.tsx:96`, S.No 221). A tester following the old text would have raised a defect for the
  missing Onboarding item and missed the Accessibility one entirely.
- The `Onboarding` condition is written as **not greenfield** rather than **is brownfield** on
  purpose, so a project whose track is unknown still shows the item rather than hiding it from the
  people who need it. If you see it on a project with no track set, that is intended.
- `/traceability`, `/transcripts`, `/contracts`, `/recovery`, `/setup`, `/projects/new`,
  `/gates/:id/criteria` and `/admin/roles` deliberately have **no** sidebar entry. Their absence
  from the sidebar is not a defect.
- The `Workspace Admin` item's own href is `/admin`, which immediately redirects to `/admin/users`.
  Landing on `/admin/users` with the item highlighted is correct.

---

### TC-168 · The Gates, Clarifications and bell badges count what the signed-in person can act on

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | Functional |
| Priority | Medium |
| Screen | All (app shell) · `/gates` · `/clarifications` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Tester C has at least one gate awaiting decision and, ideally, one open clarification on a project
  P1 is a member of. Otherwise run the zero-state half only.

**Steps**
1. On any screen, read the number badge on the sidebar's `Gates` item and on `Clarifications`.
2. Read the badge on the top-bar notification bell.
3. Click `Gates` and read the **Pending** tab's own header count — it renders as `Pending (n)`.
   Count the rows in the pending table too.
4. Click `Clarifications` and count the open questions on the screen.
5. Answer one clarification (or have Tester C's gate decided) and watch the badges without
   reloading.

**Expected**
- As P1 (a workspace admin, who may decide every gate), the `Gates` badge equals the `Pending (n)`
  count on `/gates`.
- The `Clarifications` badge equals the number of open questions on this project (P1 is a member of
  the project).
- The bell badge equals the sum of the two.
- Each badge is the true total — a project with more than 20 open gates shows the real number, not
  `20`.
- When a count is zero, no badge is rendered at all on that item — not a `0`.
- After an item is cleared, the badges drop without a manual page reload (they refresh on a poll —
  allow up to a minute).

**Pass / Fail**
- PASS if, for P1, all three badges match the counts described above.
- FAIL if a badge shows a hardcoded or stale number, if a `0` badge is rendered, or if the bell
  badge is not the sum of the other two.
- FAIL if a badge counts gates from a project other than the one selected in the top bar.

**Notes**
- **Personalised since commit 4ac75f9.** The `Gates` badge counts only the pending gates the
  signed-in person may decide: the gate's required role on this project, or the project `admin` role,
  or workspace admin. The `Clarifications` badge counts open questions only on a project the person
  is a member of. Neither is capped any more.
- So for a persona who is not an admin, the `Gates` badge can legitimately be **lower** than
  `Pending (n)`, because `/gates` lists every pending gate on the project. To check that half, sign in
  as P10 Engineer (who holds no gate role) with a gate pending: the `Gates` badge must be absent.
- The bell is no longer inert — clicking it opens the dashboard's `Needs me` queue (TC-266). Only its
  *badge* is under test here.

---

### TC-169 · A non-admin sees neither `Test Reporting` nor the `Admin` group

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | Permission |
| Priority | High |
| Screen | All (app shell) · `/admin/users` · `/test-reporting` |
| Persona | P10 Engineer |
| Automation | No |

**Preconditions**
- P10 Engineer (`qa+b.eng@…`) exists, has accepted their invitation, holds the `engineer` role on
  the project and is **not** a workspace admin.

**Steps**
1. Sign out of P1 and sign in as P10.
2. Read the whole sidebar top to bottom.
3. Confirm what appears under the `Project` group.
4. Type `/test-reporting` into the address bar.
5. Type `/admin/users` into the address bar.

**Expected**
- The `Project` group ends at `Connect Machine` — there is **no** `Test Reporting` item.
- There is **no** `Admin` section header and no `Workspace Admin` item; the sidebar ends after the
  `Project` group.
- Both deep links render a panel titled `Admin access needed` explaining the page is for workspace
  admins, with a `← Back to the dashboard` link — not a blank screen and not the real screen.
- Signing back in as P1 restores both `Test Reporting` and the `Admin` group.

**Pass / Fail**
- PASS if both are hidden for P10 and both deep links are refused with the admin panel.
- FAIL — severity **High** — if a non-admin can see or reach either surface.

---

### TC-170 · The top-bar project select switches project and the screens re-scope

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | Functional |
| Priority | High |
| Screen | All (app shell) · `/` · `/work-items` · `/artifacts` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- P1 is a member of at least two projects: `Payment Gateway v2` (populated by Tester C) and a second
  project such as `QA Empty Project`.

**Steps**
1. With `Payment Gateway v2` selected, open `/work-items` and note the items listed; open
   `/artifacts` and note the rows.
2. Open the top-bar project select and read its options.
3. Choose the second project.
4. Re-read `/work-items`, `/artifacts` and the dashboard sub-heading at `/`.
5. Switch back to `Payment Gateway v2`.

**Expected**
- The select lists exactly the projects P1 is a member of, by name.
- After switching, `/work-items` shows the second project's items (none, for a fresh project) and
  `/artifacts` shows its registry — no rows from the first project remain.
- The dashboard sub-heading now names the second project:
  `{project} · your runs, gates, and questions in one place.`
- Switching back restores the original lists.

**Pass / Fail**
- PASS if the select changes the selected project and every screen re-scopes to it.
- FAIL if the select is inert, if data from the previous project is still shown after switching
  (that is **High** — a cross-project data leak in the UI), or if switching logs you out.

**Notes**
- A user with no memberships sees a single option reading `No project yet`. That is the expected
  fallback, not a defect.

---

### TC-171 · The avatar menu shows name and email, and `Sign out` works

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | Functional |
| Priority | High |
| Screen | All (app shell) → `/login` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1.

**Steps**
1. Click the circular avatar button at the far right of the top bar.
2. Read the two lines at the top of the menu that opens.
3. Click **Sign out**.
4. After the redirect, try to go back to `/` in the address bar.

**Expected**
- The avatar shows the user's initials, and the menu opens below it.
- The menu's first line is the signed-in user's full name; the second is their email
  (`qa+b.owner@edvensoft.com`).
- The menu contains exactly one action: **Sign out**.
- While signing out the item reads `Signing out…`, then the app lands on `/login`.
- Going back to `/` afterwards redirects to `/login` — the session is genuinely gone.

**Pass / Fail**
- PASS if the menu shows the correct name and email and **Sign out** ends at the login screen with
  no session.
- FAIL if the wrong identity is shown, if the menu shows placeholder text such as `You` while a real
  user is signed in, or if `/` is still reachable after signing out (**High** — the session survived).

---

### TC-172 · The account menu closes on Escape and on an outside click

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | UX |
| Priority | Medium |
| Screen | All (app shell) |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1. Do **not** click `Sign out` during this case.

**Steps**
1. Click the avatar to open the account menu.
2. Press `Escape`.
3. Open it again, then click on an empty area of the page canvas well away from the menu.
4. Open it again, then click a sidebar item to navigate.
5. Open it once more and, **without pressing any key**, note which control carries the focus ring.
   Then press `Escape` to close it again.

**Expected**
- `Escape` closes the menu; the avatar remains on screen and no navigation occurs.
- Clicking outside the menu closes it, and that click does not also trigger whatever was underneath
  in a surprising way.
- Navigating to another screen dismisses the menu automatically — it is never left hanging open over
  the new screen.
- Step 5: the moment the menu opens, focus has already moved onto the `Sign out` item — the focus
  ring is on `Sign out`, not on the avatar and not lost on the page body. A keyboard user is not
  stranded.

**Pass / Fail**
- PASS if all three dismissal paths close the menu and focus lands on `Sign out` the moment the
  menu opens.
- FAIL if the menu stays open after `Escape` or an outside click, or persists across navigation.
- FAIL if focus stays on the avatar or goes nowhere when the menu opens — severity **Medium**, an
  accessibility defect.

**Notes**
- Do not press `Enter` or `Space` while `Sign out` holds the focus, or you will end the session
  mid-case.

---

### TC-173 · The companion pill appears in both the sidebar footer and the top bar

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | UX |
| Priority | Low |
| Screen | All (app shell) |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1. Tester B runs no companion, so the expected reading is `Companion: Offline`.

**Steps**
1. Look at the bottom of the sidebar.
2. Look at the right of the top bar, between the project select and the notification bell.
3. Navigate to three different screens and confirm both pills stay in place.

**Expected**
- A companion pill is rendered in the sidebar footer **and** a second one in the top bar.
- Both read the same text — `Companion: Offline` in a workspace with no running companion, or
  `Companion: Ready` when one is checked in — and both carry a status dot.
- The two never disagree with each other, and both persist on every screen.

**Pass / Fail**
- PASS if both pills are present, agree, and persist across navigation.
- FAIL if only one is rendered, or if the two show different states at the same time.

**Notes**
- The pill is duplicated by design. If you think one of the two is redundant, that is a **Low**
  usability observation, not a defect.
- The separate Companion card was removed from the dashboard **for a workspace that has a project
  selected** — its absence at `/` is intended there. It was *not* removed from the no-project
  dashboard, which still renders a `Companion` card (see TC-177). Both are current behaviour;
  neither is a defect, and the inconsistency between them is already tracked.

---

### TC-174 · The dashboard greeting changes when something needs you

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | UX |
| Priority | High |
| Screen | `/` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Access to both a busy state (Tester C has a gate or clarification waiting on P1) and a quiet state
  (a project with nothing pending — `QA Empty Project` works).

**Steps**
1. With the busy project selected, go to `/` and read the `h1`.
2. Read the sub-heading below it.
3. Switch the project select to the quiet project and read the `h1` again.
4. Read the two header buttons on the right of the page head.

**Expected**
- With anything pending, the heading reads exactly
  `Good morning — here's what needs you`.
- With nothing pending, the heading reads exactly `Good morning` — no dash, no trailing clause.
- The sub-heading always reads `{project name} · your runs, gates, and questions in one place.` and
  names the currently selected project.
- The header buttons are **Trigger phase** (→ `/runs`) and **+ New Work Item** (→ `/work-items`).

**Pass / Fail**
- PASS if the heading switches between the two exact strings according to whether anything is
  pending, and both header buttons navigate.
- FAIL if the long heading shows on a completely quiet dashboard (or vice versa), or if either
  header button is inert.

**Notes**
- The greeting is fixed to "Good morning" regardless of the time of day. That is current behaviour;
  raise it as **Low** if you like, but only once.

---

### TC-175 · The three tiles and the `Needs me` rows, and their actions, navigate correctly

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | Functional |
| Priority | High |
| Screen | `/` → `/gates` · `/clarifications` · `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Tester C has at least one gate awaiting P1 and, ideally, one open clarification on the selected
  project.

**Steps**
1. Go to `/` and read the labels, numbers and sub-lines on the three tiles.
2. Read the `Needs me` panel's title badge.
3. Count the rows inside `Needs me`, and read each row's title, its grey line underneath and its
   action button.
4. Click **Review** on a gate row.
5. Return to `/` and click **Answer** on a question row.
6. Return to `/` and, if a run row is present, click **View**.

**Expected**
- The three tiles are labelled `Gates need your approval`, `Questions awaiting you` and
  `My runs in flight`, each showing a number.
- The first two tiles' sub-line reads `{n} waiting on you`, or `nothing waiting on you` at zero. The
  third reads `{n} running`, or `none` when you have no run in flight.
- The `Needs me` panel's badge reads `{n} items`, where `n` is the total of the three tiles and
  equals the number of rows in the panel.
- Every row names its work item by number and title — never by a string of letters and digits from an
  internal id:
  - a gate row's title reads `{gate} · {WI key} {work item title}` (for example
    `Phase gate · WI-12 Stripe Webhook Integration`), with the grey line `required role: {Role}`;
  - a question row's title reads `Question · {WI key} {work item title}`, with the grey line
    `"{the question}" · waiting {n}m`;
  - a run row's title reads `{Phase} run · {WI key} {work item title}`, with a grey line that starts
    `just started · ` (under a minute) or `started {n}m ago · `, followed by the run's status.
- Gate rows carry a **Review** button, question rows an **Answer** button, and run rows a **View**
  button.
- **Review** opens `/gates` with **that** gate selected (its id is in the address as `gate=`);
  **Answer** opens `/clarifications` with that question selected (`clarification=` in the address);
  **View** navigates to that run's console at `/runs/{id}`.

**Pass / Fail**
- PASS if the tile numbers match the row counts, every row names its work item as above, and all
  three actions land on the right item.
- FAIL if a tile number disagrees with the rows below it, if a row names its work item by an
  eight-character id, or if any action button is inert or lands on a different item.

**Notes**
- **Row wording changed in commit b40c557**, and the tile sub-lines in commit 4ac75f9 (they used to
  name a required role and read `all clear` / `all answered`). A row whose work item has no number
  reads `a work item` in place of the name — note it, but it is not this case's failure.
- The gates and questions tiles count only what **you** can act on (see TC-168). The row lists are
  trimmed (20 gates, 20 questions, 10 runs) while the tiles show true totals, so on a very busy
  project the badge can exceed the rows. Below those sizes they must agree.
- `My runs in flight` counts only runs that **the currently signed-in user triggered**, and only
  those that are running or awaiting a gate. A run Tester C triggered will not appear on Tester B's
  dashboard, and a completed or failed run never appears. Verify this deliberately — it is the
  easiest number on the dashboard to misread as broken.

---

### TC-176 · The calm dashboard: all caught up, health rows, and nothing published

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | UX |
| Priority | Medium |
| Screen | `/` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A project with nothing pending for you and nothing published yet — `QA Empty Project`, or
  `Payment Gateway v2` once every gate has been decided.

**Steps**
1. Select that project and go to `/`.
2. Read the `Needs me` panel.
3. Read the `Project health` card in the right column.
4. Read the `Recent publishes` card below it.

**Expected**
- `Needs me` shows an empty state titled `You're all caught up` with the text
  `No gates or questions need you right now. Trigger a phase or start a new work item.` and two
  buttons, **Trigger phase** and **+ New Work Item**, both of which navigate.
- `Project health` lists exactly four rows, in order: `Work items`, `Phases in progress`,
  `Awaiting gate`, `Published this week`, each with a number.
- The `Work items` number matches the number of work items visible on `/work-items` for this
  project.
- `Recent publishes` reads `Nothing published yet.` when nothing has been **published** in the last 7
  days; otherwise it lists a `Published` badge with each artifact's name, newest publish first.

**Pass / Fail**
- PASS if the all-caught-up empty state, the four health rows and the correct publishes state all
  render.
- FAIL if a health row is missing or renamed, if `Work items` disagrees with `/work-items`, or if
  `Recent publishes` claims a publish that did not happen.
- FAIL if an artifact published within the last 7 days is missing from `Recent publishes` (within its
  limit of 5) or from the `Published this week` number, because it was **drafted** more than 7 days
  earlier.

**Notes**
- **Both surfaces count by publish date since commit 4ac75f9.** They used to filter on the date the
  artifact was registered, so something drafted 8 days ago and published today never appeared. That
  defect is fixed: an artifact drafted long ago and approved today now appears in both, and one
  drafted today but not yet published appears in neither.
- A re-publish from the Export screen does not move an artifact's publish date — the date is set the
  first time it is published.
- Both surfaces are bounded — `Published this week` counts the last 7 days and `Recent publishes`
  lists at most 5 artifacts. A sixth publish not appearing in the list is not a defect.

---

### TC-177 · With no project selected the dashboard shows the `Get started` panel

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | UX |
| Priority | Medium |
| Screen | `/` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A freshly signed-up workspace with no project yet. Sign up a throwaway account through `/signup`
  rather than deleting an existing project.

**Steps**
1. Sign in to the project-less workspace and land on `/`.
2. Read the top-bar project select.
3. Read the panel on the dashboard and each of its four steps.
4. Read the card in the right column beside that panel.
5. Click **Create a project**, then come back to `/` without completing the form.

**Expected**
- The project select shows `No project yet`.
- A panel titled `Get started` lists four numbered steps:
  1 `Create your first project`, 2 `Connect your machine`, 3 `Invite your team & assign roles`,
  4 `Connect integrations`.
- Step 1 has a **Create a project** button (→ `/projects/new`) and step 2 has a **Connect** button
  (→ `/connect`). **Steps 3 and 4 have no action buttons at all** — that is the current design.
- Beside the panel, a card titled `Companion` renders, showing an offline status reading
  `Not connected yet` and the help text `Connect your machine to run your first phase.`
- No tiles, no `Needs me` panel and no `Project health` card are rendered in this state.

**Pass / Fail**
- PASS if the four-step `Get started` panel renders with buttons on steps 1 and 2 only, alongside
  the `Companion` card.
- FAIL if the dashboard errors, renders empty tiles, or shows a dead button on step 3 or 4.
- FAIL if the `Companion` card is missing — its presence here is the current behaviour, not a
  leftover.

**Notes**
- The missing buttons on steps 3 and 4 are known. If you think a dead-end step is a usability
  problem, raise it once as **Low** — do not raise it as two separate defects.
- The `Companion` card is rendered **only** in this no-project state; once a project is selected the
  dashboard drops it and the companion status lives in the shell pills instead (TC-173). That
  inconsistency is already tracked — do not raise it, and do not treat TC-173's note as
  contradicting this case.
- This state renders the same fixed panel for everyone: it takes no data from the server, so unlike
  the rest of the dashboard it looks identical whether the backend is healthy or not (contrast
  TC-261).

---

### TC-178 · An unknown URL redirects to `/` — there is no 404 page

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | UX |
| Priority | Medium |
| Screen | any unknown route → `/` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 with a project selected.

**Steps**
1. Type `http://localhost:5173/this-route-does-not-exist` into the address bar and press Enter.
2. Observe the address bar and the screen.
3. Repeat with a plausible typo of a real route, e.g. `/artifact` (singular) and `/workitems`.
4. Sign out and repeat step 1 while logged out.

**Expected**
- Every unknown route silently redirects to `/` and the workspace dashboard renders.
- The address bar ends up showing `/`, not the bad path.
- No 404 page, no error message and no explanation that the URL was wrong is ever shown.
- Logged out, an unknown route ends at `/login` (the redirect to `/` is then caught by the auth
  gate).

**Pass / Fail**
- PASS if unknown routes always land on the dashboard (or the login screen when signed out) with no
  crash.
- FAIL if a bad URL blanks the screen or throws.

**Notes**
- The absence of a 404 page is deliberate today, but it means a mistyped or stale deep link looks
  exactly like a successful navigation to the dashboard — a user who follows a broken link from a
  colleague gets no signal that anything was wrong. Raise that once as a **Low** usability
  observation with this TC-ID; do not raise the redirect itself as a functional defect.

---

### TC-179 · The tenant switcher is inert

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | UX |
| Priority | Low |
| Screen | All (app shell) |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1.

**Steps**
1. Click the left-most top-bar button — it shows the workspace name and a caret.
2. Press `Enter` on it with the keyboard.
3. Confirm nothing opened, navigated or changed after either of the above.

**Expected**
- The tenant button shows the workspace initials and name with a caret, but clicking it opens no
  menu and changes nothing.
- The control throws no visible error and does not navigate.

**Pass / Fail**
- PASS if the control is visibly present and does nothing at all, with no error.
- FAIL only if clicking it produces an error, a broken half-rendered panel, or an unexpected
  navigation.

**Notes**
- The tenant switcher is on the plan's **known inert controls** list (§10) — confirm and reference
  it. Do **not** raise a new defect for it. That it *looks* clickable while doing nothing is the known
  complaint and is already captured.
- **This case used to cover the notification bell as well.** Since commit 4ac75f9 the bell opens the
  `Needs me` queue, so it moved to its own case, TC-266. The bell is no longer an inert control.

---

### TC-180 · `/dev/components` is reachable without logging in and is linked from nowhere

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | Permission |
| Priority | Low |
| Screen | `/dev/components` |
| Persona | Any |
| Automation | No |

**Preconditions**
- A private/incognito window with no session.

**Steps**
1. In the incognito window, go to `http://localhost:5173/dev/components`.
2. Read the heading and confirm whether the sidebar and top bar are present.
3. Back in your normal signed-in window, search the sidebar, the top bar, the dashboard and the
   account menu for any link to `/dev/components`.
4. While you are on the gallery, note the sample data it renders.

**Expected**
- The page loads without a login and shows the heading `S-00 Component Library`.
- No sidebar, no top bar and no project context render — it is a bare page.
- Nothing anywhere in the product links to it; it is only reachable by typing the URL.
- The gallery renders hardcoded demo data — `WI-492`, `Sarah Chen`, `Payment Gateway v2`, `RUN-42`,
  `PR #218`, `acme/payments-api`.

**Pass / Fail**
- PASS if the gallery loads unauthenticated, renders no app shell, and is linked from nowhere.
- FAIL if any product screen links to it, or if it exposes real workspace data rather than the
  hardcoded demo values.

**Notes**
- The gallery is out of scope this cycle apart from this case. It renders every feature screen in a
  forced demo mode, which is why the fake names appear here legitimately.
- **The corollary is worth watching all cycle:** those same strings must never appear on a *live*
  route. If you ever see `WI-492`, `Sarah Chen`, `RUN-42`, `PR #218` or `acme/payments-api` on a
  real screen in your own workspace, that is a demo-data leak — raise it as **High** against the
  screen where you saw it and reference this TC.

---

### TC-261 · A failed dashboard request shows an error panel with `Try again`, not a calm dashboard

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | UX |
| Priority | High |
| Screen | `/` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A project with something genuinely pending on it — Tester C has a gate or a clarification open, so
  the dashboard is in its busy state.
- You can stop and restart the backend process. It will be down for about a minute.
- **Do not reload the browser tab during this case.** A reload re-requests your session, which fails
  with the backend down and bounces you to `/login`, and you observe nothing.

**Steps**
1. Go to `/` with the busy project selected. Record the `h1`, the three tile numbers and their
   sub-lines (`{n} waiting on you` / `nothing waiting on you`, and `{n} running` / `none`), the
   `Needs me` badge, the four `Project health` numbers and the `Recent publishes` contents.
2. Stop the backend.
3. Stay on `/` and **do not reload**. The dashboard re-requests its data every few seconds on its
   own; wait about 30 seconds for the requests to fail and the screen to re-render.
4. Read the whole dashboard area.
5. Also read the sidebar `Gates` and `Clarifications` badges and the bell badge.
6. **Cleanup — mandatory.** Restart the backend, wait for it to come up, and click **Try again**
   (or wait a few seconds for the next automatic refresh). Confirm the dashboard returns to the
   step 1 readings without a page reload.

**Expected**
- Step 4: the whole dashboard — greeting, tiles, `Needs me`, `Project health` and
  `Recent publishes` — is replaced by a danger banner titled `Can't reach the SDLC app right now`
  reading `Your browser couldn't connect.`, a **Try again** button, and the line
  `This screen is empty because it didn't load — not because there is nothing here.`
- The dashboard does **not** show `Good morning`, zero tiles, `0 items`, `You're all caught up` or
  `Nothing published yet.` at any point while the backend is down.
- No status code or raw error text is visible.
- Step 5: the sidebar and bell badges keep the numbers they last showed; they do not drop to zero.
- Step 6 restores every step 1 reading.

**Pass / Fail**
- PASS if the failed dashboard shows the `Can't reach the SDLC app right now` panel with
  **Try again**, and never a calm or all-zero dashboard.
- FAIL if a failed request renders as the calm dashboard (zero tiles, `You're all caught up`), if
  the panel has no **Try again**, or if the app blanks, crashes, shows a raw error body, or redirects
  to `/login`.

**Notes**
- **Rewritten for commit 6d85ec9.** This case used to record that a failed request looked exactly
  like a quiet project, so TC-174 and TC-176 passed on a broken backend. The dashboard now checks for
  a failure before anything else (`Dashboard.tsx:84-94`). The tile sub-lines in step 1 are from
  commit 4ac75f9; the old `all clear` / `all answered` wording no longer exists.
- The badges keep their last values because the app holds on to the last successful answer while
  it keeps retrying. The dashboard itself does not reuse those numbers. That difference is current
  behaviour — note it, but it is not this case's failure.
- Stopping the backend is a lost connection, which gives the copy above. A server fault would read
  `Something went wrong on our side` / `The app couldn't load this. Nothing you did caused it.`

---

### TC-262 · Onboarding is hidden on greenfield, and the screen behind it is still brownfield-only

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | UX |
| Priority | Medium |
| Screen | `/onboarding` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A **greenfield** project is selected in the top bar. `Payment Gateway v2` was created as
  Greenfield in TS-03; confirm on `/profile` that its track reads Greenfield before you start.

**Steps**
1. With the greenfield project selected, read the sidebar's `Project` group and confirm
   `Onboarding` is **not** listed.
2. Type `/onboarding` directly into the address bar and load it.
3. Read the page heading, the sub-heading and the badge on the right of the page head.
4. Read the numbered steps in the card below.
5. Return to `/` and confirm nothing about the project changed as a result of visiting the screen.
6. Switch the top bar to a **brownfield** project and confirm `Onboarding` reappears in the sidebar.

**Expected**
- `Onboarding` is **absent** from the sidebar on a greenfield project, and present again as soon as a
  brownfield project is selected.
- Typing the route directly still loads the screen — it is hidden from navigation, not blocked — and
  the screen still renders brownfield copy:
  - heading `Onboarding — {project name}`
  - sub-heading `Brownfield project. Let's assess what already exists, then resume the lifecycle at
    the right phase. We store analysis + pointers — never your source.`
  - a `Brownfield` badge on the right of the page head
  - steps describing uploading existing resources and assessing an existing codebase.
- Nothing on the project changed merely from opening the screen — the track on `/profile` is still
  Greenfield, and the dashboard is unchanged.

**Pass / Fail**
- PASS if the item is hidden on greenfield, returns on brownfield, and the directly-loaded screen is
  **inert** — visiting it changes nothing about the project.
- FAIL — severity **High** — if opening the screen, or any control on it, changes the project's
  track, creates an onboarding record, or alters anything visible on `/profile` or `/`.
- FAIL — severity **Medium** — if `Onboarding` still appears in the sidebar on a greenfield project.
- FAIL if the screen errors or blanks.

**Notes**
- **Corrected 2026-09-17.** This case was written before `ae34363`, when `Onboarding` was in the
  sidebar for every project. Half of it is now fixed and half is not, and the case has been split to
  match: **the sidebar item is now conditional** (`AppShell.tsx:96`, S.No 221), but **the screen
  itself still has no track check** — `OnboardingHub.tsx:572` hardcodes "Brownfield project." and the
  `Brownfield` badge, and there is no route guard. So the confusing copy is now only reachable by
  typing the URL.
- **The remaining half is still a tracked defect.** Do not raise it again. Record what you saw and
  move on. Its severity is about user confusion, not data corruption — which is exactly why step 5
  exists: this case's real job is to confirm the screen is *inert* for a greenfield project.
- Do not click through the wizard's actions (upload, connect, index) on a greenfield project. This
  case observes the landing screen only. Brownfield onboarding as a feature is out of scope this
  cycle.

---

### TC-263 · The project selector lists one option per role grant, so a two-role user sees duplicates

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | UX |
| Priority | Medium |
| Screen | All (app shell) |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A user who holds **two different roles on the same project**. Create this through the product: as
  P1, go to `/admin/roles` and, in the role matrix, tick a second role cell — for example
  `reviewer` on top of `engineer` — for the same person on `Payment Gateway v2`.
- Use P10 Engineer as that person if they already hold `engineer`; otherwise grant both roles to
  P10.

**Steps**
1. As P1, tick the second role cell on `/admin/roles` and confirm both role cells are now ticked
   for that user.
2. Sign out and sign in as that user.
3. Open the top-bar project select and read every option, top to bottom.
4. Count how many options carry the project's name.
5. Pick the second occurrence of the project and confirm the screens still scope correctly — open
   `/work-items` and `/artifacts` and compare with the first occurrence.
6. Sign back in as P1 and untick the second role cell on `/admin/roles` to restore the workspace.

**Expected**
- The select shows the project's name **twice** — once per role grant — with no role shown to tell
  the two apart.
- Both options select the same project: `/work-items` and `/artifacts` show identical contents
  whichever one is chosen. There is no data difference and no error.
- The rest of the shell is unaffected.

**Pass / Fail**
- PASS if the duplicate option appears and both entries behave identically. That is the current
  behaviour and this case pins it down.
- FAIL — severity **High** — if the two options scope to *different* data, or if selecting one
  produces an error, an empty screen, or a different project's contents. That would turn a cosmetic
  duplicate into a real scoping bug.
- FAIL if the select renders the project once, in which case this case's premise no longer holds —
  record it and check the finding has not been fixed since.

**Notes**
- **The duplicate itself is already tracked as a product defect** (the selector is built one option
  per role grant rather than one per distinct project). Do not raise it again. This case's job is
  to establish that the duplication is *cosmetic only*.
- This matters beyond the selector: any case that says "open the project select and read its
  options" — TC-170 among them — must expect a repeated name for a multi-role user, not treat it as
  a data leak.
- Do not skip step 6. Leaving a second role grant in place changes what other suites see on the
  roles matrix.

---

### TC-264 · An unknown `/admin/*` route redirects to Users & invitations

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | Negative |
| Priority | Medium |
| Screen | `/admin/:anything` → `/admin/users` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Signed in as P1, a workspace admin.

**Steps**
1. Type `http://localhost:5173/admin/users` into the address bar and note the screen that renders —
   this is the admin landing screen.
2. Now type `http://localhost:5173/admin/this-does-not-exist` and press Enter.
3. Read the address bar and the screen.
4. Note which sidebar item is highlighted and whether the app shell is intact.
5. Repeat with `/admin/settings` and `/admin/billing`.

**Expected**
- The address bar changes to `/admin/users` — the bad path is replaced, not kept.
- The screen is the same admin users screen you saw in step 1.
- The sidebar's `Workspace Admin` item is highlighted and the full app shell renders.
- Nowhere on the screen do the words `Foundation route mounted`, `Ready for screen implementation`,
  `No screen built yet`, `T2-T5` or `Phase 4.8` appear.
- Every `/admin/<anything>` path behaves the same way.

**Pass / Fail**
- PASS if every unknown admin path lands on `/admin/users` inside the normal shell.
- FAIL if any unknown admin path shows the old developer placeholder, keeps the bad path in the
  address bar with a blank or different screen, blanks, or throws.

**Notes**
- **Changed in commit 4ac75f9.** An unknown admin address used to render a developer's placeholder
  page with internal build language ("T2-T5", "Phase 4.8"). That page was deleted; unknown admin
  addresses now go to the admin landing screen, the same way an unknown address elsewhere goes to the
  dashboard (TC-178).
- Going back in the browser after the redirect does not return to the bad path — the redirect
  replaces it in history.
- A **non-admin** who visits the same URL gets the `Admin access needed` panel instead — that half is
  covered by TC-265.

---

### TC-265 · The `Admin access needed` panel also guards `/test-reporting`, and its copy does not say so

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | Permission |
| Priority | Medium |
| Screen | `/test-reporting` · `/admin/users` · `/admin/roles` |
| Persona | P10 Engineer |
| Automation | No |

**Preconditions**
- P10 Engineer exists, has accepted their invitation, holds the `engineer` role on the project and
  is **not** a workspace admin.
- TC-169 has passed, so you already know the sidebar hides both surfaces from P10.

**Steps**
1. Sign in as P10.
2. Type `/admin/users` into the address bar and read the panel word for word.
3. Type `/admin/roles` and confirm the same panel renders.
4. Type `/admin/this-does-not-exist` and confirm the same panel renders — a non-admin is refused
   before the redirect in TC-264 applies.
5. Type `/test-reporting` and read the panel word for word. Compare it with what you read in step 2.
6. Click **← Back to the dashboard** and confirm where you land.

**Expected**
- All four routes render the identical panel, titled `Admin access needed`, reading
  `This page manages workspace users and roles, and is available to workspace admins only. Ask an admin to grant you the admin role if you need it.`
  with a `← Back to the dashboard` link below it.
- On `/test-reporting` the copy is **word-for-word the same** — it still says "manages workspace
  users and roles", which is not what that page does. The tester's job is to confirm this, not to
  find different copy.
- **← Back to the dashboard** navigates to `/` and the dashboard renders for P10.
- At no point does the real `Test Reporting` screen, the real user list or the roles matrix render
  for P10.

**Pass / Fail**
- PASS if all four routes are refused with that exact panel and the back link works.
- FAIL — severity **High** — if any of the four renders the real screen or a blank page for a
  non-admin.
- Do **not** fail this case for the wrong copy on `/test-reporting` — see Notes.

**Notes**
- **The mismatched copy is already tracked as a product defect**: the same panel guards
  `/test-reporting`, which manages CI reporting tokens rather than users and roles, so a non-admin
  is told the wrong reason they were refused. Record it against this TC-ID and do not raise a
  duplicate.
- `/test-reporting` being admin-only is intentional and mirrors the backend — do not raise the
  restriction itself, only note that its explanation is wrong.
- This case is the negative twin of TC-169, which covers the sidebar visibility. Keep the verdicts
  separate: TC-169 fails if the *item* is visible, this one fails if the *route* is reachable.

---

### TC-266 · The notification bell opens the dashboard's `Needs me` queue

| Field | Value |
|---|---|
| Suite | TS-12 Shell, Navigation & Dashboard |
| Type | Functional |
| Priority | Medium |
| Screen | All (app shell) → `/#needs-me` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1 with `Payment Gateway v2` selected.
- For the busy half: Tester C has at least one gate or question waiting that P1 can act on, so the
  bell shows a badge. For the zero half: a project with nothing waiting (`QA Empty Project`).

**Steps**
1. Go to `/work-items` (any screen other than the dashboard) and read the bell's badge.
2. Click the bell icon to the right of the companion pill.
3. Read the address bar, note which part of the dashboard is in view, and note where the keyboard
   focus is.
4. Scroll back to the top of the dashboard and click the bell again.
5. Switch the project select to the quiet project, go to `/work-items`, and click the bell.

**Expected**
- Step 1: the bell shows a numeric badge equal to the sidebar `Gates` badge plus the
  `Clarifications` badge (TC-168).
- Step 2 navigates to the dashboard with `#needs-me` at the end of the address (`/#needs-me`).
- Step 3: the page scrolls so the `Needs me` panel is in view, and focus moves to that queue — a
  keyboard user lands on the queue, not at the top of the page. The panel's badge reads `{n} items`
  and matches the bell's number.
- Step 4: clicking the bell while already on the dashboard brings the `Needs me` panel back into view.
- Step 5: at zero the bell has no badge but **still** navigates to the dashboard, where the `Needs me`
  panel shows `You're all caught up`.
- No panel or dropdown opens from the bell, and no error appears.

**Pass / Fail**
- PASS if the bell always lands on the `Needs me` queue on the dashboard — busy or empty, from another
  screen or from the dashboard itself.
- FAIL if clicking the bell does nothing, lands at the top of the dashboard without bringing
  `Needs me` into view, or does nothing when the count is zero.

**Notes**
- **New behaviour in commit 4ac75f9.** The bell used to show a count and ignore clicks, and it sat on
  the plan's known inert controls list. It now opens the existing `Needs me` queue rather than a
  separate notifications panel — do not raise the absence of a notifications drop-down.
- The bell's screen-reader name is `Notifications, {n} unread`.

---

### TC-953 · The dashboard greeting follows the clock

| Field | Value |
|---|---|
| Suite | TS-12 Shell & Dashboard |
| Type | UX |
| Priority | Low |
| Screen | `/` |
| Persona | Any |
| Automation | Yes |

**Why this case exists.** It said `Good morning` at every hour. Bugs S.No 367.

**Steps**
1. Open the dashboard at any time of day.

**Expected**
- Before 12:00 `Good morning`, until 17:00 `Good afternoon`, after that `Good evening` — by your own
  computer's clock. With something waiting on you, the same greeting is followed by
  `— here's what needs you`.

**Pass / Fail**
- FAIL if the greeting does not match the time of day.
