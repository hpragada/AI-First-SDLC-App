# TS-05 · Companion Machine

Covers `/connect` — enrolling the local companion daemon that every phase run executes on — and the
companion status pills that the app shell shows on every screen. **Owner: Tester C**, working as
**P1 Owner-Admin** in workspace `QA Charlie`. This is the first suite of the cycle: nothing in
TS-07 to TS-15 can run until TC-072 passes.

> **Run these in order.** The screen is a state machine — not-started → token-generated → connected
> → offline — and each case leaves the machine in the state the next one needs. TC-078 disconnects
> the machine, so run it last and re-enrol afterwards before starting TS-07.

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
3. Look at the `Projects` control in Step A.
4. Look at the commands shown in Step B and the help line underneath them.

**Expected**
- The h1 reads `Connect your machine`.
- Step A is titled `In the app — generate an enrollment token` and contains a `Projects`
  multi-select listing your projects, plus a button labelled **Generate enrollment token**.
- Step B is titled `In your terminal — sign in & start the companion` and is visibly greyed out.
- Step B's commands are placeholders — `claude` and
  `python -m runner.companion serve --api-url … --tenant … --token …` — with the literal ellipses.
- Below them the help line reads `Generate the token in Step A to reveal these commands.`

**Pass / Fail**
- PASS if both steps render as described and Step B is clearly the inactive one.
- FAIL if Step B looks active, if the placeholder command already contains a real token or tenant
  id, or if the help line is missing.

**Test data**
- None.

**Notes**
- The `Projects` multi-select is **inert** — the token is always issued for your first project
  membership, whatever you highlight. TC-581 covers that specifically; the underlying defect is
  tracked separately, so do not raise it here or there a second time.

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
- FAIL if the token shown is `rnr_3f9a…b2` (that is the bug in TC-077 — log it there), if no warning
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
- If the companion rejects the token, check first whether you were handed the fake value from
  TC-077 before raising anything else.
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
5. Read the button in the card's footer.

**Expected**
- The status line reads `Offline — {machine} · last seen {…}` with a relative time such as `3m ago`.
- The copy explains the companion is not reachable and tells you to restart it in your terminal.
- A command block shows a `python -m runner.companion serve …` line.
- A single button labelled **Generate new token** is shown. There is no **Disconnect machine**
  button in this state.

**Pass / Fail**
- PASS if the offline status, the restart command and the **Generate new token** button all render.
- FAIL if the screen still claims the machine is connected, or if the last-seen time does not move
  as time passes.

**Test data**
- None.

**Notes**
- **Known trap:** the `--token` value in this offline restart command is the literal placeholder
  `rnr_3f9a…b2` until you press **Generate new token** — copying it as-is will not authenticate. It
  is the same fake constant as TC-077. Verify it, reference TC-077's defect, and do not raise a
  second one.

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
- After clicking, the `--token` value in the command block changes from `rnr_3f9a…b2` to a real
  token.
- Running the command starts the companion without an auth error.
- `/connect` flips back to `Connected — {machine} · last seen just now` on its own, and both pills
  return to `Companion: Ready`.

**Pass / Fail**
- PASS if the new token authenticates and the screen returns to the connected state.
- FAIL if the token in the command block does not change, or if the companion is rejected with the
  newly generated token.

**Test data**
- None.

**Notes**
- The screen stays in the offline layout after generating — the new token only appears inside the
  command block, never in a `Token generated` card. That is the current design; the copy warning
  about one-time visibility is not repeated here, which is worth a Low UX note but is not a
  functional failure.

---

### TC-077 · A failed token request silently shows a fake token and a success screen

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
4. Read the `--token` value in the command block character by character.
5. Restart the backend: `docker compose --profile app start backend`. Reload `/connect` and wait
   until the page renders (up to 60 seconds while the container comes up).
6. **Recover the companion before you leave this case** — the fake token from step 3 will never
   authenticate. On `/connect`, still in the offline state, click **Generate new token** again, and
   confirm the `--token` value in the command block is now a real token and **not** `rnr_3f9a…b2`.
7. Copy that command, add `--worktrees ~/sdlc --repo-path ~/repos/<your-test-repo>`, run it, and
   wait up to 60 seconds for `/connect` to flip to `Connected — {machine} · last seen just now`
   and both pills to read `Companion: Ready`. TC-078 starts from that state.

**Expected — what the app *should* do**
- The failure is surfaced: an error message telling you the token could not be generated, and no
  token shown.

**Actual — the known defect**
- No error is shown. The screen behaves as if the request succeeded and the `--token` value becomes
  the literal string `rnr_3f9a…b2`.
- If you were in the not-started state instead, the same failure advances the screen to the
  `✓ Token generated` card showing `rnr_3f9a…b2` as though it were a real credential.

**Pass / Fail**
- PASS if the app surfaces the failure and shows no token.
- FAIL if the literal `rnr_3f9a…b2` appears, or the screen advances to a success state, after a
  failed request.
- Steps 5–7 are recovery, not assertions: if the companion will not come back online within
  4 minutes of running the command, mark this case **Blocked** on the environment rather than
  logging a second defect, and do not start TC-078.

**Test data**
- The fake token to look for: `rnr_3f9a…b2` (note the single-character ellipsis `…`).

**Notes**
- **Known defect** — the create-runner error path substitutes a hardcoded placeholder token and lets
  the UI continue as if enrollment worked. It is already described in the test plan's §2 "Known
  trap". Log it once against this TC and reference it from TC-075 rather than raising a second
  defect there.
- Severity is Critical: a tester or a customer following the screen ends up with a companion that
  cannot authenticate and no indication why.

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

### TC-581 · The `Projects` multi-select on the enrollment screen has no effect on the token issued

| Field | Value |
|---|---|
| Suite | TS-05 Companion Machine |
| Type | UX |
| Priority | Medium |
| Screen | `/connect` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1 in workspace `QA Charlie`.
- **Two** projects exist and P1 is a member of both. If only `Payment Gateway v2` exists, create a
  second one from `/projects/new` — Name `Refunds Service`, Track `Greenfield` — before starting,
  and note which of the two the `Projects` list shows **first**.
- No companion is currently enrolled, or you are willing to generate one more token (generating is
  harmless and this case does not start a companion).

**Steps**
1. Go to `/connect`. If the screen is in the connected or offline layout, that layout has no
   `Projects` control — read the Notes and mark the case Blocked rather than disconnecting.
2. In Step A, read the `Projects` multi-select and note the order the projects are listed in.
3. Highlight **only the second** project in the list — leave the first one unselected.
4. Click **Generate enrollment token**.
5. Read the whole `Token generated` card and the whole Step B command block, top to bottom.

**Expected**
- The `Projects` control accepts your selection and visibly highlights the second project.
- The token is issued and the screen advances to the `✓ Token generated` card.
- **Nothing anywhere on the resulting screen names the project you selected.** The `Token generated`
  card shows only the token; the `serve` command carries `--api-url`, `--tenant` and `--token` and
  no project argument; no confirmation line states which project the machine was bound to.

**Pass / Fail**
- PASS if the selection is accepted but no part of the resulting screen or command reflects it —
  i.e. the control is confirmed inert.
- FAIL — meaning the behaviour has changed and there is nothing to confirm — if the generated
  command, the token card, or any confirmation copy names the project you chose.

**Test data**
- Second project: `Refunds Service`, Track `Greenfield`.

**Notes**
- **Known defect, tracked separately — do not raise it again.** The enrollment is always created
  against your *first* project membership; the multi-select's value is never read. The screen gives
  a tester no way to see which project a machine was actually bound to, which is why this case can
  only prove the control is decorative rather than prove the wrong binding directly.
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
