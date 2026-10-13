# TS-05 · Companion Machine

Covers `/connect` — enrolling the local companion daemon that every phase run executes on — and the
companion status pills that the app shell shows on every screen. **Owner: Tester C**, working as
**P1 Owner-Admin** in workspace `QA Charlie`. This is the first suite of the cycle: nothing in
TS-07 to TS-15 can run until TC-072 passes.

> **Run these in order.** The screen is a state machine — no-project → not-started → token-generated
> → connected → offline — and each case leaves the machine in the state the next one needs. TC-078
> disconnects the machine, so run it last and re-enrol afterwards before starting TS-07.

> **Re-baselined 2026-09-29 — read this before running the suite.** Three defects this suite was
> written to confirm **have been fixed** (commit `76b6475`), so the cases that told you to expect
> them would now have you log failures against correct behaviour:
>
> - **The fake token `rnr_3f9a…b2` is gone.** There is no placeholder anywhere on the screen. A
>   token you see is a token the server issued. **TC-077 is inverted** — it now asserts the failure
>   is surfaced properly; seeing `rnr_3f9a…b2` is a regression, not the expected result.
> - **The `Project` control works.** It is a single-choice picker, wired up, defaulting to the
>   project the rest of the app is on. It was a decorative multi-select. **TC-069 and TC-581 are
>   rewritten** — TC-581 now proves the picker binds the enrollment, instead of proving it is inert.
> - **A workspace with no project now has its own screen** rather than silently sending a broken
>   request. **TC-583 is new** and covers it.
>
> Everything else in the suite is unchanged. The Connect Machine redesign (Bugs S.No 35) will
> require this suite to be re-baselined again when pairing ships.

You will need a terminal with Python 3.12, `git` on PATH, and Claude Code already signed in
(`claude`). Keep the companion in its own terminal window for the whole cycle.

---

### TC-069 · The not-started state shows Step A and a greyed-out Step B

| Field | Value |
|---|---|
| Suite | TS-05 Companion Machine |
| Type | UX |
| Priority | High |
| Screen | `/connect` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 in workspace `QA Charlie`, with at least one project (`Payment Gateway v2`).
- No companion has ever been enrolled for this account.

**Steps**
1. Click **Connect Machine** in the sidebar's setup section (or go to `http://localhost:5173/connect`).
2. Read the heading and the two step cards.
3. Look at the `Project` control in Step A.
4. Look at the commands shown in Step B and the help line underneath them.

**Expected**
- The h1 reads `Connect your machine`.
- Step A is titled `In the app — generate an enrollment token` and contains a **single-choice**
  `Project` dropdown listing your projects, plus a button labelled **Generate enrollment token**.
- The dropdown has a project already selected when the page loads — the one the rest of the app is
  currently on — not a blank first entry.
- Each project appears **once**, even if you hold more than one role on it.
- Step B is titled `In your terminal — sign in & start the companion` and is visibly greyed out.
- Step B's commands are placeholders — `claude` and
  `python -m runner.companion serve --api-url … --tenant … --token …` — with the literal ellipses.
- Below them the help line reads `Generate the token in Step A to reveal these commands.`

**Pass / Fail**
- PASS if both steps render as described and Step B is clearly the inactive one.
- FAIL if Step B looks active, if the placeholder command already contains a real token or tenant
  id, if the help line is missing, if the `Project` control allows more than one selection, or if a
  project is listed twice.

**Test data**
- None.

**Notes**
- **Changed 2026-09-29.** This case used to expect a `Projects` **multi-select** and described it as
  **inert** — the token was always issued for your first project membership whatever you chose. Both
  are fixed (commit `76b6475`): it is a real single-choice picker and it binds the enrollment.
  TC-581 now proves that binding rather than confirming the control is decorative.
- If you hold two roles on one project you have two membership records for it. The picker lists
  **projects**, so it must still show that project once.

---

### TC-070 · Generating an enrollment token shows it exactly once

| Field | Value |
|---|---|
| Suite | TS-05 Companion Machine |
| Type | Functional |
| Priority | Critical |
| Screen | `/connect` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-069 passed; you are on `/connect` in the not-started state.
- The backend is up (`docker compose --profile app ps` shows it running).

**Steps**
1. Click **Generate enrollment token**.
2. Read the card that replaces Step A.
3. Copy the token with the **Copy** button and paste it somewhere safe — you will need it in TC-071.
4. Reload the page (F5) and look for the token again.

**Expected**
- The button shows `Generating…` while the request is in flight.
- Step A is replaced by a card marked with a `✓` reading `Token generated`, with the warning
  `Copy it now — for security it's shown only once.`
- A token is shown that starts with real characters — **not** the literal string `rnr_3f9a…b2`.
- Clicking **Copy** flips the button to `✓ Copied!` and the clipboard holds the token.
- At the bottom of the page a waiting status reads
  `Waiting for first check-in — run the command above…`
- After the reload the token is gone from the screen.

**Pass / Fail**
- PASS if a real one-time token is issued, the warning is shown, and the token disappears on reload.
- FAIL if the token shown is `rnr_3f9a…b2` (a regression of the defect TC-077 now guards), if no warning
  is shown, or if the token survives a reload.

**Test data**
- Record the token in your own notes only. Never paste a token into the tracker or a defect.

**Notes**
- Only the token's hash is stored, so a lost token genuinely cannot be recovered — generating a new
  one is the only remedy.

---

### TC-071 · Step B reveals the two real commands to run

| Field | Value |
|---|---|
| Suite | TS-05 Companion Machine |
| Type | Functional |
| Priority | High |
| Screen | `/connect` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-070 passed; the token-generated state is on screen (do not reload).

**Steps**
1. Read the second card on the page.
2. Read both command rows in it.
3. Click **Copy** on the second command row.
4. Paste it into a text editor and inspect the `--api-url`, `--tenant` and `--token` values.

**Expected**
- The second card is titled `Run these in your terminal` with the note
  `Leave the second command running in the background.` and is no longer greyed out.
- The first command row reads `claude`.
- The second reads `python -m runner.companion serve --api-url … --tenant … --token …` with the
  ellipses replaced by real values: `--api-url http://localhost:8000`, `--tenant` followed by your
  workspace id, and `--token` followed by the token from TC-070.
- Each row has its own **Copy** button.

**Pass / Fail**
- PASS if both commands are shown with real, copyable values.
- FAIL if any placeholder ellipsis remains, if the tenant id is blank, or if the token in the
  command does not match the one displayed above it.

**Test data**
- None.

**Notes**
- The command intentionally omits `--worktrees` and `--repo-path`. Add them yourself per the plan's
  §2 before running it; the missing flags are not a defect.

---

### TC-072 · The companion connects and the screen flips to Connected

| Field | Value |
|---|---|
| Suite | TS-05 Companion Machine |
| Type | E2E |
| Priority | Critical |
| Screen | `/connect` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-071 passed; the token-generated state is on screen with the waiting status showing.
- A local clone of your test repo exists and Claude Code is signed in.

**Steps**
1. In a terminal, run `claude` and confirm you are signed in.
2. In a second terminal, run the copied `serve` command, adding
   `--worktrees ~/sdlc --repo-path ~/repos/<your-test-repo>`.
3. Leave that terminal running and switch back to the browser on `/connect`.
4. Wait up to 30 seconds without reloading.

**Expected**
- The waiting status is replaced by a connected status reading
  `Connected — {machine} · last seen {…}`, where `{machine}` is your machine name (or
  `your machine` if the companion reported no label) and `{…}` is a relative time such as
  `just now`.
- Explanatory copy appears telling you phases will run here and to keep the `serve` command running.
- Two buttons are shown: **Go to Work Items** and **Disconnect machine**.
- The screen reaches this state on its own — no manual reload is required.

**Pass / Fail**
- PASS if the screen flips to the connected state by itself and both buttons render.
- FAIL if the companion terminal reports an auth error, if the screen stays on
  `Waiting for first check-in — run the command above…` for more than a minute, or if the last-seen
  time is obviously wrong (e.g. `5m ago` immediately after connecting).

**Test data**
- None.

**Notes**
- If the companion rejects the token, check first that you pasted the whole token from TC-070 and
  that the `--tenant` value matches your workspace. *(Until 2026-09-29 this note said to check
  whether you had been handed a fake placeholder token — that defect is fixed, so a rejected token
  now means a real mismatch worth raising.)*
- This is the cycle's entry criterion. If it fails, TS-07 to TS-15 are all Blocked against the
  defect you raise here.

---

### TC-073 · Both companion pills read `Companion: Ready`

| Field | Value |
|---|---|
| Suite | TS-05 Companion Machine |
| Type | UX |
| Priority | High |
| Screen | Any screen (app shell) |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-072 passed and the companion is still running.

**Steps**
1. Look at the bottom of the left sidebar.
2. Look at the right-hand end of the top bar.
3. Navigate to `/work-items`, then to `/`, and check both pills again on each screen.

**Expected**
- The sidebar footer shows a pill reading `Companion: Ready` with a status dot.
- The top bar shows a second pill reading `Companion: Ready` — the same text appears twice on every
  page.
- Both pills keep reading `Companion: Ready` as you navigate; neither flickers to `Companion: Offline`
  while the companion is running.

**Pass / Fail**
- PASS if both pills read `Companion: Ready` on every screen visited.
- FAIL if either pill reads `Companion: Offline` while the companion is up, if the two disagree, or
  if a pill is missing on some screens.

**Test data**
- None.

**Notes**
- The shell refreshes the pill roughly every 15 seconds, so give it a moment after a state change
  before calling it wrong. `/connect` refreshes faster.
- The pill appearing twice is the current design, not a duplication bug.

---

### TC-074 · Stopping the companion turns the pills to `Companion: Offline` after the 2-minute window

| Field | Value |
|---|---|
| Suite | TS-05 Companion Machine |
| Type | Functional |
| Priority | High |
| Screen | Any screen (app shell) |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-073 passed; both pills read `Companion: Ready`.
- No phase run is in progress — stopping the companion mid-run is TS-14's case, not this one.

**Steps**
1. Note the wall-clock time, then stop the companion with `Ctrl+C` in its terminal.
2. Stay on `/work-items` and watch both pills for the first minute. Do not reload.
3. **Wait past three minutes from the time you noted.** The online window is **2 minutes**, not 5 —
   some docs say 5; the app uses 2 — but the observable flip lands later than that (see Notes).
4. Check both pills at roughly 1 minute, then again at roughly 3 minutes.
5. If either pill still reads `Companion: Ready` at 3 minutes, keep watching until **4 minutes**
   from the time you noted. Four minutes is the maximum wait for this case.

**Expected**
- At ~1 minute both pills still read `Companion: Ready` — a machine is online until its last
  check-in is more than 2 minutes old.
- By ~3 minutes both pills read `Companion: Offline`.
- Both pills change together; no reload is needed.

**Pass / Fail**
- PASS if the pills stay `Companion: Ready` at the 1-minute check and both read
  `Companion: Offline` by the 3-minute check.
- PASS also if both flip between 3 and 4 minutes — record the observed time in the tracker.
- FAIL if a pill flips to offline within the first minute, if either pill is still
  `Companion: Ready` at **4 minutes**, or if only one of the two pills updates.

**Test data**
- None.

**Notes**
- **Why the window is wider than 2 minutes.** Three delays stack: the companion heartbeats every
  30 s, so its last check-in can already be up to 30 s old when you press `Ctrl+C`; the server then
  needs that timestamp to age past the 2-minute threshold; and the app shell only re-polls the
  companion status every 15 s. Worst case is therefore ≈ 2 min 45 s before the pills can possibly
  change. A flip at 2 m 40 s is correct behaviour, not a slow one — do not fail it.
- `/connect` polls faster (every 4 s) than the shell, so that screen may show the change a few
  seconds before the pills do. That is expected, not a disagreement between surfaces.

---

### TC-075 · The offline state on `/connect` explains how to restart and offers a new token

| Field | Value |
|---|---|
| Suite | TS-05 Companion Machine |
| Type | UX |
| Priority | Medium |
| Screen | `/connect` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-074 passed — the companion is stopped and the pills read `Companion: Offline`.

**Steps**
1. Go to `/connect`.
2. Read the status line at the top of the card.
3. Read the explanatory copy and the command block below it.
4. Read the `--token` value inside that command block.
5. Read the help line underneath the command block.
6. Read the button in the card's footer.

**Expected**
- The status line reads `Offline — {machine} · last seen {…}` with a relative time such as `3m ago`.
- The copy explains the companion is not reachable and tells you to restart it in your terminal.
- A command block shows a `python -m runner.companion serve …` line.
- **The `--token` value reads the literal `<your-token>`** — a visible blank for you to fill in, not
  a real-looking token and **not** `rnr_3f9a…b2`.
- Underneath, a help line explains that you should use the token you saved when you connected, that
  it is shown only once and the platform keeps no copy, and that generating a new one stops the old
  one working.
- A single button labelled **Generate new token** is shown. There is no **Disconnect machine**
  button in this state.

**Pass / Fail**
- PASS if the offline status, the restart command, the `<your-token>` placeholder, the help line and
  the **Generate new token** button all render.
- FAIL if the screen still claims the machine is connected, if the last-seen time does not move as
  time passes, if the literal `rnr_3f9a…b2` appears anywhere (that is a regression — raise it), or
  if a real-looking token is shown without the help line explaining where to get one.

**Test data**
- None.

**Notes**
- **Changed 2026-09-29.** This case used to carry a "known trap": the `--token` value was the fake
  constant `rnr_3f9a…b2` and testers were told not to raise it. **That is fixed** (commit `76b6475`).
  A returning user has no token in the page's memory — it is shown once and never stored — so the
  screen now says so honestly instead of printing a command that cannot work.

---

### TC-076 · `Generate new token` on the offline screen issues a working token

| Field | Value |
|---|---|
| Suite | TS-05 Companion Machine |
| Type | Functional |
| Priority | Medium |
| Screen | `/connect` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-075 passed; you are on `/connect` in the offline state.

**Steps**
1. Click **Generate new token**.
2. Read the `--token` value in the command block again.
3. Copy that command, add `--worktrees ~/sdlc --repo-path ~/repos/<your-test-repo>`, and run it.
4. Watch `/connect` for up to 30 seconds.

**Expected**
- After clicking, the `--token` value in the command block changes from the `<your-token>`
  placeholder to a real token, and the help line about the one-time token disappears.
- Running the command starts the companion without an auth error.
- `/connect` flips back to `Connected — {machine} · last seen just now` on its own, and both pills
  return to `Companion: Ready`.

**Pass / Fail**
- PASS if the new token authenticates and the screen returns to the connected state.
- FAIL if the token in the command block does not change, if the companion is rejected with the
  newly generated token, or if the literal `rnr_3f9a…b2` appears (a regression — raise it).

**Test data**
- None.

**Notes**
- The screen stays in the offline layout after generating — the new token only appears inside the
  command block, never in a `Token generated` card. That is the current design; the copy warning
  about one-time visibility is not repeated here, which is worth a Low UX note but is not a
  functional failure.

---

### TC-077 · A failed token request says so, and shows no token

| Field | Value |
|---|---|
| Suite | TS-05 Companion Machine |
| Type | Negative |
| Priority | Critical |
| Screen | `/connect` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- The companion is running and `/connect` shows the connected state (from TC-076).
- You can stop and start the backend container.

**Steps**
1. Stop the companion with `Ctrl+C`, then wait past 2 minutes so `/connect` reaches the offline
   state.
2. Stop the backend: `docker compose --profile app stop backend`.
3. On `/connect`, click **Generate new token**.
4. Read the whole card: the `--token` value in the command block, and anything that appears above or
   below the button.
5. Confirm the screen has **not** advanced to a `✓ Token generated` card.
6. Restart the backend: `docker compose --profile app start backend`. Reload `/connect` and wait
   until the page renders (up to 60 seconds while the container comes up).
7. **Recover the companion before you leave this case.** On `/connect`, still in the offline state,
   click **Generate new token** again and confirm the `--token` value is now a real token.
8. Copy that command, add `--worktrees ~/sdlc --repo-path ~/repos/<your-test-repo>`, run it, and
   wait up to 60 seconds for `/connect` to flip to `Connected — {machine} · last seen just now`
   and both pills to read `Companion: Ready`. TC-078 starts from that state.

**Expected**
- An error is shown, titled `Could not generate a token`, with a readable sentence explaining the
  failure. It names no error codes, no URLs and no status numbers.
- **No token appears anywhere.** The `--token` value is still the `<your-token>` placeholder.
- The screen stays in the offline state. It does **not** advance to the `✓ Token generated` card.
- Repeating this from the not-started state behaves the same way: the error appears above the
  button and Step B stays greyed out.

**Pass / Fail**
- PASS if the failure is surfaced in words and no token is shown.
- FAIL if no error appears, if the screen advances to a success state after a failed request, or if
  any token-shaped value appears — **especially the literal `rnr_3f9a…b2`, which is the old defect
  returning.**
- Steps 6–8 are recovery, not assertions: if the companion will not come back online within
  4 minutes of running the command, mark this case **Blocked** on the environment rather than
  logging a second defect, and do not start TC-078.

**Test data**
- The old fake token, which must **not** appear: `rnr_3f9a…b2` (note the single-character
  ellipsis `…`).

**Notes**
- **This case was inverted on 2026-09-29.** It used to document a Critical known defect: the
  create-runner error path substituted a hardcoded placeholder token and let the screen continue as
  if enrollment had worked, so a tester or a customer ended up with a companion that could not
  authenticate and no indication why. **It is fixed** (commit `76b6475`) — there is no fallback token
  in the code at all, and the failure is surfaced instead. The case now guards the fix rather than
  recording the bug.
- Severity stays Critical, because what it now protects is the same thing: a person must never be
  handed a credential that cannot work.

---

### TC-078 · `Disconnect machine` stops the running companion's token from authenticating

| Field | Value |
|---|---|
| Suite | TS-05 Companion Machine |
| Type | Functional |
| Priority | High |
| Screen | `/connect` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-077 step 7 is complete: the backend is up, the companion is running on the token generated
  there, `/connect` shows the connected state, and both pills read `Companion: Ready`.
- **Run this case last in the suite** — it tears down the enrollment TS-07 onwards depends on.

**Steps**
1. On `/connect`, click **Disconnect machine**.
2. Watch the button, then the screen, for up to 30 seconds.
3. Switch to the companion's terminal and watch its next few calls (up to 60 seconds — it heartbeats
   every 30 s).
4. Go back to `/connect` and reload.

**Expected**
- The button shows `Disconnecting…` while the request is in flight.
- **The still-running companion can no longer authenticate** — within about a minute its terminal
  reports rejected calls instead of continuing to work. This is the assertion that matters.
- The screen leaves the connected state. What it lands on is the **offline** layout —
  `Offline — {machine} · last seen {…}`, the restart copy, a `serve` command block and a single
  **Generate new token** button. It does **not** return to the Step A / Step B not-started layout.
- Both companion pills read `Companion: Offline`.
- After the reload the screen is still in the offline layout, not the connected one.

**Pass / Fail**
- PASS if the revoked token stops authenticating and the screen leaves the connected state for the
  offline layout.
- FAIL if the connected state persists after a reload, if the companion keeps working normally for
  more than 60 seconds after the disconnect, or if the revoked token still authenticates.

**Test data**
- None.

**Notes**
- **Why the machine does not vanish.** Every **Generate…** press creates a *new* enrollment row, and
  this suite has created several for the same project (TC-070, TC-076, TC-077). **Disconnect
  machine** revokes only the single most-recently-active row — the earlier rows stay active and keep
  the same machine card on screen, now showing a stale `last seen`, which is why you get the offline
  layout rather than a clean not-started screen. Confirm this and move on: the "disconnect leaves
  older enrollments alive" defect is **tracked separately**, so do not raise it again here.
- **Re-enrol before TS-07.** Stop the companion, then from the offline screen click **Generate new
  token**, copy the command, add `--worktrees ~/sdlc --repo-path ~/repos/<your-test-repo>`, and run
  it. Wait up to 4 minutes for both pills to read `Companion: Ready`. If they do not, mark TS-07
  onwards **Blocked**, not Failed. Do **not** look for the Step A "Generate enrollment token"
  button — it is not on this screen.
- If the disconnect fails, the screen shows `Couldn't disconnect this machine.` in red beneath the
  buttons — note the straight apostrophe there, in contrast with Integrations' `Couldn’t save`
  (TC-068).

---

### TC-581 · The `Project` picker decides which project the machine is enrolled for

| Field | Value |
|---|---|
| Suite | TS-05 Companion Machine |
| Type | Functional |
| Priority | High |
| Screen | `/connect` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1 in workspace `QA Charlie`.
- **Two** projects exist and P1 is a member of both. If only `Payment Gateway v2` exists, create a
  second one from `/projects/new` — Name `Refunds Service`, Track `Greenfield` — before starting.
- No companion is currently enrolled, or you are willing to generate one more token (generating is
  harmless and this case does not start a companion).

**Steps**
1. Open your browser's developer tools, go to the **Network** tab, and leave it recording. You will
   need it in step 6 — see the Notes for why.
2. Go to `/connect`. If the screen is in the connected or offline layout, that layout has no
   `Project` control — read the Notes and mark the case Blocked rather than disconnecting.
3. In Step A, read which project the `Project` dropdown has **already selected** when the page loads.
4. Change it to the **other** project.
5. Click **Generate enrollment token**.
6. In the Network tab, find the request the button sent and read the `project_id` it carried, then
   read the `project_id` in the response.

**Expected**
- The dropdown loads with the project the rest of the app is currently on already chosen — not blank,
  and not simply the first in the list.
- It accepts a single choice. There is no way to select two projects at once.
- The token is issued and the screen advances to the `✓ Token generated` card.
- **The request carries the `project_id` of the project you chose in step 4, and the response returns
  the same one.** Choosing the other project changed what was sent.

**Pass / Fail**
- PASS if the picker defaults sensibly, accepts one choice, and the enrollment is created for the
  project you actually selected.
- FAIL if the request carries a different project from the one you chose, if the dropdown loads
  blank, if it allows multiple selection, or if changing it has no effect on what is sent.

**Test data**
- Second project: `Refunds Service`, Track `Greenfield`.

**Notes**
- **Rewritten 2026-09-29, and its meaning is now the opposite.** This case used to exist to *confirm
  a defect*: the control was a decorative multi-select whose value was never read, and the enrollment
  was always created against your first project membership whatever you chose. It was written so
  that it **failed if the picker worked**. The picker was fixed in commit `76b6475`, so the case now
  proves the binding instead. If you are working from an older printed copy of this suite, discard it.
- **Why step 6 needs developer tools.** The screen still does not *say* which project the machine was
  bound to — the `Token generated` card shows only the token, and the `serve` command carries no
  project argument. So the network request is the only place a tester can see the binding. That is a
  genuine gap in the screen rather than a defect in the fix; it is recorded against the Connect
  Machine redesign (Bugs S.No 35), so **do not raise it separately**.
- Generating a token here does not disturb a running companion — an existing companion keeps working
  on its own token. The extra enrollment row is harmless, though it is one of the rows that makes
  TC-078 land on the offline layout.

---

### TC-582 · A non-admin engineer can enrol a companion machine

| Field | Value |
|---|---|
| Suite | TS-05 Companion Machine |
| Type | Permission |
| Priority | High |
| Screen | `/connect` |
| Persona | P10 Engineer |
| Automation | No |

**Preconditions**
- P10 (`qa+c.eng@…`, role `engineer` on `Payment Gateway v2`, **not** a tenant admin) exists in
  `QA Charlie`.
- Run this **after TC-078**, so P1's own enrollment work is finished and an extra machine record
  cannot confuse the earlier cases.

**Steps**
1. Log out and log back in as P10 with password `QaTest-2026!`.
2. Look at the sidebar's setup section for **Connect Machine**, and go to
   `http://localhost:5173/connect`.
3. Read Step A.
4. Click **Generate enrollment token**.
5. Read the resulting card and the Step B command block.
6. Log out and log back in as P1, then go to `/connect`.

**Expected**
- P10 reaches `/connect` — the route is not blocked and no permission message is shown.
- Step A renders normally, listing P10's project membership.
- **Generate enrollment token succeeds**: the `✓ Token generated` card appears with a real token
  (not `rnr_3f9a…b2`) and Step B reveals a `serve` command carrying the workspace's real tenant id.
- Back as P1, `/connect` shows **only P1's own machine** — P10's new enrollment does not appear on
  P1's screen.

**Pass / Fail**
- PASS if P10 successfully mints a working enrollment token — confirming the endpoint applies no
  role check — **and** P1's screen does not list P10's machine.
- FAIL if P1's `/connect` lists a machine P10 enrolled (that would be a separate, higher-severity
  isolation problem, so raise it as its own defect).
- Record the *expected* product behaviour in your defect note: a non-admin should not be able to
  attach a run host to the workspace at all.

**Test data**
- P10 login: `qa+c.eng@edvensoft.com` / `QaTest-2026!`

**Notes**
- **This case passes by demonstrating a missing permission check**, which is why its PASS criterion
  reads oddly: the enrollment endpoint inherits the project-wide default of "any signed-in member",
  so an engineer can attach their own machine as a run host. The defect is **tracked separately** —
  confirm the behaviour, reference the existing entry, and do not raise a duplicate.
- The matching *revoke* gap — the revoke endpoint checks only the workspace, not who owns the
  machine — is **not testable from the browser**, because `/connect` only ever lists the signed-in
  user's own enrollments and there is no other disconnect control. Do not attempt to construct it;
  it is covered by the same tracked entry.
- Do not start a companion with P10's token. Generating it is the whole test.

---

### TC-583 · A workspace with no project explains itself instead of failing

| Field | Value |
|---|---|
| Suite | TS-05 Companion Machine |
| Type | Negative |
| Priority | Medium |
| Screen | `/connect` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- A **brand-new workspace** with **no project at all**, and no companion ever enrolled. Sign up a
  fresh workspace for this — do **not** delete `QA Charlie`'s projects to create the condition.
- Logged in as that workspace's owner.

**Steps**
1. Go to `/connect`.
2. Read the whole card.
3. Look for a `Project` dropdown and a **Generate enrollment token** button.
4. Click the button that *is* offered.

**Expected**
- The page heading is still `Connect your machine`.
- A message titled `Create a project first` explains that a machine runs phases for one project and
  this workspace does not have one yet.
- **There is no `Project` dropdown and no Generate button** — there is nothing to enrol against, so
  nothing invites you to try.
- The only action offered is **Create a project**, and it takes you to the new-project screen.
- Nothing is sent to the server, and no error appears.

**Pass / Fail**
- PASS if the screen explains the situation in plain words and offers the one action that helps.
- FAIL if the Step A / Step B layout renders with an empty project dropdown, if a Generate button is
  offered, or if pressing anything produces a server error.

**Test data**
- None.

**Notes**
- **New case, added 2026-09-29.** This state exists in the product but the suite never covered it.
  Before commit `76b6475` the screen rendered Step A with an empty dropdown, sent an enrollment
  request with no project, and the server rejected it — which the screen then displayed as a
  **success**, complete with a fake token. Both halves of that are fixed; this case guards the first
  half, and TC-077 guards the second.
- This is the first state in the suite's state machine (no-project → not-started → token-generated →
  connected → offline), but it needs its own empty workspace, so it is placed last to avoid
  disturbing the ordered run above.

---

### TC-941 · Disconnect really disconnects, and the page says when

**Why this case exists.** Disconnect cancelled only the newest of the machine's keys. Older keys
kept working, and the page fell back to one of them: "Offline · last seen 16m ago" was an old key's
heartbeat, not the disconnect (2026-10-08). Bugs S.No 348.

**Setup.** On one project, click **Generate token** at least twice (two keys), and run the companion
with the newest.

**Steps**
1. On **Connect Machine**, click **Disconnect machine**.
2. Try starting the companion with the OLDER token.
3. Reload the page. Come back the next day.

**Expected**
- Straight after the click: a green line **Your machine was disconnected just now. It can't run
  phases until you connect it again.**, and the setup steps below it. No "Offline", no "last seen".
- The older token is refused too.
- On reload and later visits: a grey note, e.g. **Your machine was disconnected today at 2:46 PM**,
  later **yesterday at …**, **on Monday at …**, **on 8 Sep**, **on 8 Jul 2025**.
- Hovering the time shows the full date, time and your zone, e.g. `8 Oct 2026, 2:46 PM IST`.
- After connecting again, the note is gone.

**Pass / Fail**
- **FAIL if any older token still works, or the time shown is not the moment you clicked.**

---

### TC-942 · Times on Connect Machine are in your own time zone

**Steps**
1. With the companion connected, read the **last seen** line. Hover it.
2. Change the computer's time zone and reload.
3. Read the sub-heading under **Connect your machine**.

**Expected**
- Last seen reads **just now** while it is live, then **today at …** (never "16m ago").
- The hover names the zone, and it changes with the computer's time zone.
- The sub-heading reads: "Phases run on your computer using your Claude Code subscription. Two
  one-time steps, like pairing a device." — no mention of API keys or billing.

**Pass / Fail**
- **FAIL if any time on the page is in UTC rather than the viewer's zone.**
