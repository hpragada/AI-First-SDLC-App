# TS-13 · Test Cases & Test Reporting

This suite covers the two screens that sit either side of automated testing: the story-level
**Test cases** screen (`/work-items/:id/test-cases`) where child `test_case` work items are listed,
added by hand and handed to the Test Automation (09b) phase for script generation; and the
admin-only **Test reporting** screen (`/test-reporting`) where CI tokens are issued and revoked so a
pipeline can post JUnit results back into the project. **Owner: Tester B.**

**Run these in order.** TC-181 → TC-187 build on each other — the story created in TC-181 is the one
you add cases to, and the badge/counter checks in TC-186 need the case you add in TC-183. TC-188 →
TC-192 are the CI-token half and also run in sequence: the token issued in TC-191 is the one you
revoke in TC-192. TC-213 → TC-215 were added by the QA audit and run **last**, after TC-192:
TC-213 needs Tester C's companion, and TC-214/TC-215 need a freshly issued token (TC-192 revokes
the first one, and revocation is one-way).

**Waiting on agent runs.** Any step in this suite that waits on a run has an explicit **max wait**.
If the run has not reached the state the case names within that window, record the case as
**Blocked** with the run id — never **Fail**. "Failed" is reserved for the app doing the wrong
thing, not for the app being slow. A silent console is not evidence of a hang
(`docs/TESTING_PHASE_BUGS_HANDOFF.md` Bug 3).

---

### TC-181 · The `Test cases` button on an epic opens the story's test-case screen

| Field | Value |
|---|---|
| Suite | TS-13 Test Cases & Test Reporting |
| Type | Functional |
| Priority | High |
| Screen | `/work-items/:id`, `/work-items/:id/test-cases` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in to workspace `QA Bravo` as P1 with project `Payment Gateway v2` selected.
- At least one work item exists on the board (create `Stripe Webhook Integration` from
  `/work-items` if the board is empty).

**Steps**
1. Go to `http://localhost:5173/work-items`.
2. Open the work item `Stripe Webhook Integration`.
3. In the page header, click **Test cases**.

**Expected**
- The URL becomes `/work-items/<the work item id>/test-cases`.
- The breadcrumb reads `Work items / Story / Test cases`.
- The page heading is `Test cases`.
- The sub-heading reads exactly `Child work items. Trigger Test Automation (09b) on one to generate
  its script — here or from Phases & Runs.`
- A primary button **+ Add test case** is visible in the header.

**Pass / Fail**
- PASS if the button navigates to the test-cases route and all four strings render as quoted.
- FAIL if the button is inert, routes elsewhere, 404s, or any of the strings differ.

**Test data**
- Work item: `Stripe Webhook Integration`

**Notes**
- The breadcrumb's middle crumb is the literal word `Story` regardless of the item's real type — it
  is not the work item's title. That is current behaviour, not a defect.

---

### TC-182 · Empty state on a story with no test cases

| Field | Value |
|---|---|
| Suite | TS-13 Test Cases & Test Reporting |
| Type | UX |
| Priority | Medium |
| Screen | `/work-items/:id/test-cases` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-181 passed. The work item has no child `test_case` items yet (a freshly created work item).

**Steps**
1. From the work item, click **Test cases**.
2. Do not open the add form.

**Expected**
- A panel shows the empty state title `No test cases yet`.
- The body text reads `Run the Testing phase on this story to create them automatically, or add one
  by hand.`
- A **+ Add test case** button is shown inside the empty state as well as in the page header.
- No table is rendered, and the `of ... automated` counter line is absent.

**Pass / Fail**
- PASS if both strings render exactly and no empty table/counter is drawn.
- FAIL if a zero-row table appears, the counter shows `0 of 0 automated`, or the copy differs.

**Test data**
- None.

**Notes**
- The counter line is only rendered when at least one case exists — an absent counter here is
  correct.

---

### TC-183 · Add a test case by hand and see it in the table

| Field | Value |
|---|---|
| Suite | TS-13 Test Cases & Test Reporting |
| Type | Functional |
| Priority | High |
| Screen | `/work-items/:id/test-cases` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-182 passed; you are on the empty test-cases screen for `Stripe Webhook Integration`.

**Steps**
1. Click **+ Add test case**.
2. In `Title`, enter `Checkout with saved card`.
3. In `Priority`, select `High`.
4. In `Steps / spec`, enter:
   `1. Sign in`
   `2. Pay with saved card`
   `Expected: order confirmed`
5. Click **Add test case**.
6. **Without reloading**, read the screen. Record what you see.
7. Now reload the page (F5) and read the screen again.

**Expected**
- While the request is in flight the button label reads `Adding…`.
- The form closes and no error text is shown.
- **At step 6, without any reload,** the `No test cases yet` empty state is replaced by the table,
  with headers `TC-ID`, `Title`, `Priority`, `Automation` and one trailing blank header cell.
- A row shows the title `Checkout with saved card` and priority `High`.
- The `+ Add test case` button is visible again in the header.
- After the reload at step 7 the same row is still there — it was saved, not only drawn.

**Pass / Fail**
- PASS if the new row appears straight away without a reload, with the title and priority entered,
  survives the reload, and the form closed cleanly with no error.
- FAIL if the row only appears after a manual reload, the case is not created at all, the form stays
  open, the priority shows as `—`, or an error is displayed.

**Test data**
- Title: `Checkout with saved card` · Priority: `High`

**Notes**
- **Fixed in commit 4ac75f9.** A hand-added case used to be saved but not shown until a manual
  reload, which made it look like the add had failed. The table now refreshes as soon as the case is
  created. A row that needs a reload to appear is a regression — raise it.
- The `Priority` select offers exactly `High`, `Medium`, `Low` and defaults to `Medium` — confirm
  the three options while the form is open.
- A hand-added case has no TC-ID stamped by the Testing agent, so the `TC-ID` cell falls back to the
  work item key. A key rather than a `TC-nnn` value here is expected.

---

### TC-184 · Add test case is blocked with an empty Title

| Field | Value |
|---|---|
| Suite | TS-13 Test Cases & Test Reporting |
| Type | Negative |
| Priority | Medium |
| Screen | `/work-items/:id/test-cases` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-183 passed; the test-cases screen has at least one row.

**Steps**
1. Click **+ Add test case**.
2. Leave `Title` empty.
3. Select `Priority` = `Low` and type `1. Do nothing` in `Steps / spec`.
4. Attempt to click **Add test case**.
5. Now type three spaces into `Title` and attempt to click **Add test case** again.

**Expected**
- The `Title` field is marked required in the form.
- The **Add test case** button is disabled and cannot be clicked in both step 4 and step 5.
- No new row is added to the table and the row count is unchanged.
- Clicking **Cancel** closes the form without adding anything.

**Pass / Fail**
- PASS if submission is impossible with an empty or whitespace-only title and nothing is created.
- FAIL if the button is clickable, a row with a blank title is created, or a raw 400 is shown.

**Test data**
- Title: `` (empty), then `   ` (three spaces)

**Notes**
- The title is trimmed before the enabled check, which is why whitespace alone must also keep the
  button disabled.

---

### TC-185 · A failing create shows `Couldn't add the test case.`

| Field | Value |
|---|---|
| Suite | TS-13 Test Cases & Test Reporting |
| Type | Negative |
| Priority | Medium |
| Screen | `/work-items/:id/test-cases` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-183 passed.
- You can stop and start the backend container (`docker compose stop backend` /
  `docker compose start backend`).

**Steps**
1. Open the test-cases screen for `Stripe Webhook Integration` and click **+ Add test case**.
2. Enter `Title` = `Refund a settled charge`.
3. In a terminal, stop the backend: `docker compose stop backend`.
4. Click **Add test case**.
5. Restart the backend: `docker compose start backend`, wait for it to come up, then reload the page.

**Expected**
- The form stays open with the typed title intact.
- An error line in danger colour appears under the fields — either the API's own message or the
  fallback `Couldn't add the test case.`
- The app does not crash, navigate away, or show a raw stack trace / JSON error body.
- After the reload in step 5, no `Refund a settled charge` row exists in the table.

**Pass / Fail**
- PASS if the failure is surfaced inline as readable copy and nothing is created.
- FAIL if the page blanks out, the error is a raw payload, or a phantom row appears.

**Test data**
- Title: `Refund a settled charge`

**Notes**
- Stopping the backend is the only UI-reachable way to force this branch. Take the screenshot before
  restarting the backend — the message clears on reload.

---

### TC-186 · Automation badges, row actions and the `N of M automated` counter

| Field | Value |
|---|---|
| Suite | TS-13 Test Cases & Test Reporting |
| Type | UX |
| Priority | High |
| Screen | `/work-items/:id/test-cases` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-183 passed; the story has at least one test case that has never been automated.

**Steps**
1. Open the test-cases screen for `Stripe Webhook Integration`.
2. Read the counter line above the table.
3. Read the `Automation` cell and the last (unlabelled) cell of each row.
4. Compare the counter's first number against the number of rows badged `Script ready`.

**Expected**
- A counter line reads `N of M automated`, with `N` in bold, where `M` equals the number of rows in
  the table.
- A row that has never run 09b shows the badge `Not automated` and its last cell is a
  **Generate script** button.
- A row with a 09b run in flight shows the badge `Generating…` and its last cell is a **View run**
  link.
- A row whose 09b run has reached its gate or beyond shows the badge `Script ready` and its last
  cell is a **View** link.
- `N` equals exactly the count of `Script ready` rows — `Not automated` and `Generating…` rows are
  not counted.

**Pass / Fail**
- PASS if every badge matches its row action and the counter equals the `Script ready` count.
- FAIL if a badge and its action disagree (e.g. `Script ready` with a **Generate script** button),
  or the counter counts in-flight rows as automated.

**Test data**
- None.

**Notes**
- You will normally only see `Not automated` on a first pass. Re-run this case after TC-187 to
  observe `Generating…`, and again once Tester C's Test Automation run reaches its gate to observe
  `Script ready`.
- While any row reads `Generating…`, the table refreshes itself every few seconds, so a row moves on
  to `Script ready` without a reload once its run reaches that point (since commit 4ac75f9). When no
  row is generating, the table does not refresh on its own.
- Badge text `Generating…` and `Script ready` use a real ellipsis character — check the copy, not
  just the presence of a badge.

---

### TC-187 · Generate script triggers a Test Automation run for that test case

| Field | Value |
|---|---|
| Suite | TS-13 Test Cases & Test Reporting |
| Type | Functional |
| Priority | High |
| Screen | `/work-items/:id/test-cases`, `/runs` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-183 passed and the row `Checkout with saved card` is badged `Not automated`.
- Note: Tester B has no companion, so the dispatched run will queue rather than execute. That is
  expected and sufficient for this case.

**Steps**
1. Open the test-cases screen for `Stripe Webhook Integration`.
2. On the `Checkout with saved card` row, click **Generate script**.
3. Wait for the request to complete **without reloading**, and read the row. Then reload the page and
   read it again.
4. Open `/runs` in the sidebar (`Phases & Runs`).
5. **The `/runs` screen filters to one selected work item, and it defaults to the first work item
   in the project — not the test case you just triggered.** In the work-item selector, select the
   test case `Checkout with saved card` before reading the Runs table.
6. **Record for later cases:** the test case's work item id (from the `View run` link's URL) and
   the run's short id. TC-213 continues from exactly this run.

**Expected**
- While the trigger is in flight the button label changes to `Starting…`.
- As soon as the request completes — before any reload — the row's `Automation` badge reads
  `Generating…` and its last cell is a **View run** link. It still reads that after the reload.
- The counter line's first number has **not** increased (an in-flight run is not "automated").
- On `/runs`, **with the test case selected**, a run row exists for phase `Test Automation` with
  status `Dispatched · waiting`.
- With the parent story selected instead, no `Test Automation` run is listed — the run belongs to
  the test case.
- Clicking **View run** opens the test case's work item, from which the run console is reachable.

**Pass / Fail**
- PASS if a Test Automation run is created for that test case and the badge flips to `Generating…`.
- FAIL if nothing happens, the run is created against the parent story instead of the test case, or
  the badge stays `Not automated` after a reload.
- FAIL if the badge flips only after a manual reload — since commit 4ac75f9 the table refreshes as
  soon as generation starts.
- **Blocked** (not Fail) if the trigger request itself never returns within **2 minutes**.

**Test data**
- Test case: `Checkout with saved card`

**Notes**
- **Max wait: 2 minutes** for the dispatch. This case asserts the *dispatch* only — with no
  companion the run stays `Dispatched · waiting` indefinitely, which is correct here. The run
  actually executing end-to-end is TC-213 (Tester C).
- This is the 09b Test Automation phase riding the ordinary **build** path (`rides_build` in
  `backend/apps/registry/catalog.py`) — there is no special endpoint for it. Its gate role is
  QA Lead, so it will sit at `Awaiting gate` once a companion actually executes it.
- If the trigger is refused (for example no machine connected, no permission, or the phase already
  running), the button returns to `Generate script` and a red line appears under it with the
  server's reason, or `Couldn't start the run.` when the server gave none
  (`TestCases.tsx:101-106`). A refusal with no red line is a defect — raise it.
- Do not kill the run if the console stays silent — a long run producing no output for 20+ minutes
  is known behaviour (`docs/TESTING_PHASE_BUGS_HANDOFF.md` Bug 3).

---

### TC-188 · `/test-reporting` is admin-only

| Field | Value |
|---|---|
| Suite | TS-13 Test Cases & Test Reporting |
| Type | Permission |
| Priority | High |
| Screen | `/test-reporting` |
| Persona | P10 Engineer |
| Automation | Yes |

**Preconditions**
- P10 (`qa+b.eng@…`) exists in `QA Bravo` with the `engineer` role only — no `admin`, not a tenant
  admin.

**Steps**
1. Log out of P1.
2. Log in as P10 with password `QaTest-2026!`.
3. Inspect the sidebar.
4. Type `http://localhost:5173/test-reporting` directly into the address bar.

**Expected**
- No `Test reporting` item appears in the sidebar for P10.
- Navigating directly renders a panel titled `Admin access needed`.
- The panel body reads `This page manages workspace users and roles, and is available to workspace
  admins only. Ask an admin to grant you the admin role if you need it.`
- No token table, no **+ New token** button, and no token value is rendered anywhere on the page.

**Pass / Fail**
- PASS if the route is blocked by the admin panel and no CI token data is exposed.
- FAIL if the screen renders for P10, or the guard is only the hidden sidebar item with the route
  still reachable.

**Test data**
- Persona: P10 `qa+b.eng@edvensoft.com` / `QaTest-2026!`

**Notes**
- A CI token can post results into the project, so leaking the list to a non-admin would be a High
  severity finding. Hiding the nav item alone is not sufficient — the route guard is the assertion.

---

### TC-189 · No-project guard on `/test-reporting`

| Field | Value |
|---|---|
| Suite | TS-13 Test Cases & Test Reporting |
| Type | Negative |
| Priority | Medium |
| Screen | `/test-reporting` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- A workspace where the signed-in admin has **no** project selected. The cleanest way to reach this
  through the product is to sign up a throwaway workspace (`QA Bravo Scratch`,
  `qa+b.scratch@edvensoft.com`) and not create a project.

**Steps**
1. Log in as the admin of the project-less workspace.
2. Go to `http://localhost:5173/test-reporting`.

**Expected**
- The heading `Test reporting` and its sub-heading `Tokens let your CI post automated-test results
  back to this project. Failing tests become tracked defects.` still render.
- A panel shows the title `No project selected`.
- The body reads `Select or create a project first — CI tokens are issued per project.`
- The **+ New token** button is disabled (or the form is unreachable) — a token cannot be issued.

**Pass / Fail**
- PASS if the guard panel renders and no token can be created without a project.
- FAIL if the screen tries to load tokens, shows an error, or lets you submit the form.

**Test data**
- Workspace: `QA Bravo Scratch`

**Notes**
- Tokens are scoped per project, which is why this guard exists rather than a global token list.

---

### TC-190 · `No tokens yet` empty state

| Field | Value |
|---|---|
| Suite | TS-13 Test Cases & Test Reporting |
| Type | UX |
| Priority | Medium |
| Screen | `/test-reporting` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 in `QA Bravo` with `Payment Gateway v2` selected.
- No CI token has been issued for this project yet.

**Steps**
1. Go to `http://localhost:5173/test-reporting`.
2. Do not open the add form.

**Expected**
- A panel shows the empty state title `No tokens yet`.
- The body reads `Generate one so your CI can report test results back to this project.`
- A **+ New token** button is shown inside the empty state and in the page header.
- No table headers are rendered.

**Pass / Fail**
- PASS if both strings render exactly and no empty table is drawn.
- FAIL if the copy differs, a zero-row table appears, or the screen shows `Couldn't load tokens`.

**Test data**
- None.

**Notes**
- If the panel reads `Couldn't load tokens` instead, that is a load failure, not the empty state —
  raise it as a defect and mark this case Blocked.

---

### TC-191 · Issue a CI token — shown once, with the copy-now warning and the CI snippet

| Field | Value |
|---|---|
| Suite | TS-13 Test Cases & Test Reporting |
| Type | Functional |
| Priority | Critical |
| Screen | `/test-reporting` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-190 passed; you are on `/test-reporting` for `Payment Gateway v2` as P1.

**Steps**
1. Click **+ New token**.
2. In `Label`, enter `GitHub Actions`.
3. Click **Generate token**.
4. Read the issued-token card in full, then click **Done**.
5. Reload the page and look for the token value again.

**Expected**
- The `Label` field shows the placeholder `GitHub Actions` and the help text `A name to recognize
  this token later — e.g. your CI system.`
- While submitting, the button label reads `Generating…`.
- A card appears headed with a `✓` and `Token created`.
- A warning line reads `Copy it now — for security it's shown only once and can't be retrieved
  later.`
- The card shows a labelled `Token` value with a copy control, and a section labelled `Add this step
  to your CI pipeline` containing a copyable `curl` snippet that posts `results.xml` and references
  `$SDLC_CI_TOKEN` and `$SDLC_URL`.
- After **Done**, the table lists a row with `Label` = `GitHub Actions`, a `active` badge (lowercase),
  `Last used` = `never`, and a `Created` date of today.
- The table headers are `Label`, `Status`, `Last used`, `Created` plus one trailing blank cell.
- After the reload the token value is nowhere on the screen — only the row remains.

**Pass / Fail**
- PASS if the token is issued, revealed exactly once with the warning and the snippet, and the row
  renders as described.
- FAIL if the token is retrievable after reload, the warning is missing, the snippet embeds the
  literal token instead of `$SDLC_CI_TOKEN`, or the status badge is capitalised.

**Test data**
- Label: `GitHub Actions`

**Notes**
- Do not paste the token value into the tracker or a defect — record that a token was issued, not
  its value.
- An unlabelled token renders as `unlabeled` in the `Label` column. `Last used` renders as `never`,
  `just now`, `Nm ago`, `Nh ago` or `Nd ago` — a never-used token must read `never`, not `—`.

---

### TC-192 · Revoke a token through the `Revoke token?` modal

| Field | Value |
|---|---|
| Suite | TS-13 Test Cases & Test Reporting |
| Type | Functional |
| Priority | High |
| Screen | `/test-reporting` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-191 passed; the `GitHub Actions` token exists with status `active`.

**Steps**
1. On `/test-reporting`, click **Revoke** on the `GitHub Actions` row.
2. Read the modal, then click **Cancel**.
3. Click **Revoke** again, then click **Revoke token**.
4. Reload the page.

**Expected**
- The modal title is `Revoke token?`.
- The modal body reads `Revoking **GitHub Actions** stops its CI from reporting results
  immediately. This can't be undone — you'd have to issue a new token.` with the label in bold.
- The modal has **Cancel** and **Revoke token** buttons; **Cancel** closes it with the row still
  `active`.
- While revoking, the button label reads `Revoking…`.
- After confirming, the row's `Status` badge reads `revoked` (lowercase) and the row is visually
  muted.
- The revoked row no longer offers a **Revoke** action — its last cell is empty.
- The state survives the reload.

**Pass / Fail**
- PASS if Cancel is non-destructive, confirming flips the badge to `revoked`, and the action is gone
  from the row.
- FAIL if Cancel revokes, the row disappears entirely, the badge stays `active`, or a revoked token
  can be revoked again.

**Test data**
- Token label: `GitHub Actions`

**Notes**
- Revocation is one-way by design. Issue a fresh token if a later case needs an active one.
- TC-214 needs an **active** token. Issue a second one (label `CI ingest`) after this case —
  do not try to un-revoke `GitHub Actions`.

---

### TC-213 · 09b Test Automation runs end-to-end — build PR and QA Lead merge gate

| Field | Value |
|---|---|
| Suite | TS-13 Test Cases & Test Reporting |
| Type | E2E |
| Priority | Critical |
| Screen | `/work-items/:id/test-cases`, `/runs/:id`, `/gates`, `/artifacts` |
| Persona | P1 Owner-Admin, P7 QA Lead |
| Automation | No |

**Preconditions**
- **Owner: Tester C** (needs a live companion) — Tester B pairs to read the result. TC-187 proves
  the dispatch; this case is the only one in the pack that carries 09b through to its gate.
- A test case work item exists under a story whose repository is registered and clonable by the
  companion. The cleanest fixture is TS-15's chain: run this against a `test_case` child produced
  by TC-209.
- The sidebar companion pill reads `Companion: Ready`.
- No other run is live on that test case work item (one active run per work item).

**Steps**
1. Open `/work-items/<the story id>/test-cases` and click **Generate script** on a test case that
   is badged `Not automated`.
2. **Record now:** the test case work item id and, once `/runs` shows it, the run id. If you are
   interrupted, **resume at step 3** with this run id — do not re-trigger.
3. Open `/runs/<the run id>` and follow the console.
4. When the badge reaches `Awaiting gate`, log out and log in as **P7 QA Lead**.
5. Open `/gates`. **This screen does not poll — reload it manually** to see the gate appear.
6. Select the Test Automation gate, read the panel, and click **Approve**.
7. Reload `/gates`, then open `/artifacts` and filter to the test case work item.
8. Return to `/work-items/<the story id>/test-cases` and reload.

**Expected**
- The run console header names the **test case** work item and the phase `Test Automation`.
- The badge progresses `Dispatched · waiting` → `Running` → `Awaiting gate`.
- On `/gates`, the gate is listed for that work item and is **decidable by P7** — enabled
  **Approve** and **Reject** buttons and a `Comment (optional to approve or reject)` field.
- The gate panel shows **no criteria checklist** — the blocking-test condition binds to the
  `testing` phase only, never to `test_automation`.
- After approving, the gate leaves the `Pending (N)` tab (reload to confirm) and the run console
  badge reads `Completed`.
- `/artifacts` lists a `code` artifact for the run whose `SoR` cell carries the pull-request
  reference — the generated script reached a real PR.
- Back on the test-cases screen, the row's badge now reads `Script ready` and its last cell is a
  **View** link; the `N of M automated` counter's first number has increased by one.

**Pass / Fail**
- PASS if 09b executes, opens a PR, gates to QA Lead, and the test case flips to `Script ready`.
- FAIL if the gate is decidable by a non-`qa_lead`, no PR reference is recorded, the badge stays
  `Generating…` after the gate is approved, or the counter does not move.
- **Blocked** (not Fail) if the run has not reached `Awaiting gate` within **45 minutes**, or if
  the companion cannot clone/push the repository. Record the run id.

**Test data**
- Phase: `Test Automation` (`09b_test_automation`) · Gate role: `qa_lead`

**Notes**
- **Max wait: 45 minutes** to `Awaiting gate`. Build-tier runs are the longest in the pack. A
  silent console is not evidence of a hang (Bug 3).
- 09b is a **build** phase: it rides the worktree → commit → push → PR → review → merge-gate path,
  so its gate is the **merge gate**, opened with `required_role = qa_lead` (from the catalog). This
  is why TC-187's dispatch alone is not coverage — the PR and the gate only exist here.
- If the run **parks** (`Parked for takeover` with a `Paused on an error` banner), that is TS-14's
  resume path — use TC-197 and continue rather than re-triggering.

---

### TC-214 · CI posts a JUnit report — `Last used` flips and failing tests open defects

| Field | Value |
|---|---|
| Suite | TS-13 Test Cases & Test Reporting |
| Type | E2E |
| Priority | Critical |
| Screen | `/test-reporting`, `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1 in `QA Bravo` with `Payment Gateway v2` selected.
- An **active** CI token exists. Issue one on `/test-reporting` labelled `CI ingest` and keep the
  revealed value in your clipboard/CI secret only. Its row reads `Last used` = `never`.
- A terminal is available. This case runs the snippet **the product itself hands you** — the same
  step a real pipeline pastes — because there is no in-app upload control. Everything asserted is
  read back in the browser.

**Steps**
1. On `/test-reporting`, click **+ New token**, label it `CI ingest`, and **Generate token**.
2. On the reveal card, copy the `Add this step to your CI pipeline` snippet with its copy control,
   then click **Done**. **Record:** the token label and the time you issued it.
3. In a terminal, save this file as `results.xml`:
   ```xml
   <testsuite name="regression" tests="2" failures="1">
     <testcase classname="checkout" name="TC-9001 pays with saved card"/>
     <testcase classname="checkout" name="TC-9002 refunds a settled charge">
       <failure message="expected 200, got 500">AssertionError</failure>
     </testcase>
   </testsuite>
   ```
4. Export the token you copied as `SDLC_CI_TOKEN`, set `SDLC_URL` to `http://localhost:8000` and
   `CI_RUN_ID` to `qa-ci-1`, then run the copied snippet **unmodified** from the folder holding
   `results.xml`.
5. Read the HTTP response.
6. Back in the browser, reload `/test-reporting` and read the `CI ingest` row.
7. Go to `/work-items` and find the work item titled `CI Regression`. Open it and read its children.
8. Open the `defect` child and read its evidence text to the end.
9. Go to `/artifacts` and look for a `test_report` artifact created by this import. Preview it.

**Expected**
- The snippet runs as copied — the project id and tenant id are already substituted, and the token
  is referenced as `$SDLC_CI_TOKEN`, never baked in.
- The request returns **200** with a JSON body reporting `imported`, `defects_opened` and
  `unmapped`.
- After the reload, the `CI ingest` row's `Last used` no longer reads `never` — it reads
  `just now` (or `Nm ago`).
- A work item titled `CI Regression` exists on the board.
- Under it, exactly **one** `defect` child exists — for the failing `TC-9002`. The passing
  `TC-9001` opens no defect.
- The defect's evidence ends with a pointer line reading
  `Full evidence: this run's test report (artifact <id>).` — the row carries a short summary, and
  names where the whole thing lives.
- A **`test_report` artifact exists** in `/artifacts` for this import, and previewing it shows a
  readable report body listing both tests with the failure message for `TC-9002`.

**Pass / Fail**
- PASS if the post is accepted, `Last used` flips in the UI, exactly one defect is opened for the
  one failing test, and the `test_report` artifact previews with the full evidence in it.
- FAIL if the post is rejected with a valid active token, `Last used` stays `never`, no
  `CI Regression` container appears, or a defect is opened for the **passing** test.
- FAIL — **Medium** — if no `test_report` artifact is registered, or if it previews empty while the
  defect claims the full evidence is there. A pointer to a report that does not exist is worse than
  no pointer.
- **Blocked** if the backend is not reachable from your terminal.

**Test data**
- Token label: `CI ingest` · `execution_ref` = `qa-ci-1` · JUnit above (1 pass, 1 fail)

**Notes**
- The terminal step is fixture setup, exactly as `docker compose stop backend` is in TC-185. Every
  assertion in Expected is made in the browser.
- CI results are **project-level regression**: they attach to a stable `CI Regression` container
  work item, not to your story. So this ingest does **not** move the Testing gate's derived
  condition on any story — that condition is fed only by the build-tier 09b import. Do not expect
  TC-209's gate to change because of this case.
- Do not paste the token value into the tracker or a defect — record that a token was used.
- **The report body is new (August 2026).** Failure evidence used to be cut to 2000 characters on
  the way in, so the full text never entered the platform at all. It is now filed as the run's
  `test_report` artifact body in the object store, and the defect row keeps only a short summary
  plus the pointer line above. So a long failure being abbreviated **on the defect row** is correct
  behaviour, not truncation — check the artifact before raising anything about lost evidence.

---

### TC-215 · A revoked CI token is rejected and does not update `Last used`

| Field | Value |
|---|---|
| Suite | TS-13 Test Cases & Test Reporting |
| Type | Negative |
| Priority | Critical |
| Screen | `/test-reporting` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-214 passed; the `CI ingest` token is `active` and its `Last used` shows a recent value.
- You still have that token value and the `results.xml` file from TC-214.

**Steps**
1. On `/test-reporting`, note the `Last used` value on the `CI ingest` row. **Record it.**
2. Click **Revoke** on that row and confirm with **Revoke token**. The badge flips to `revoked`.
3. In the terminal, re-run the **same** snippet from TC-214 with the **same** token, changing only
   `CI_RUN_ID` to `qa-ci-2`.
4. Read the HTTP response.
5. Reload `/test-reporting` and re-read the `CI ingest` row.
6. Go to `/work-items`, open `CI Regression` and count its `defect` children.

**Expected**
- The request is refused with **401** and the body `{"detail": "invalid or missing CI token"}`.
- No JUnit content is accepted — the response is not a 200 and reports no import.
- After the reload, the `CI ingest` row still reads `revoked`, and its `Last used` value is
  **unchanged** from the value recorded at step 1.
- `CI Regression` still has exactly the one defect from TC-214 — nothing new was opened or closed.

**Pass / Fail**
- PASS if a revoked token is rejected with 401, `Last used` does not move, and no work items change.
- FAIL if the post is accepted, `Last used` advances, a defect is opened or closed, or the refusal
  is anything other than a 401 (a 500 or a stack trace is a defect worth raising).

**Test data**
- Token label: `CI ingest` (revoked) · `execution_ref` = `qa-ci-2`

**Notes**
- This is the whole point of revocation: it must stop the CI **immediately**, not just grey out a
  row. A revoked token that still ingests is a **Critical** security finding.
- Revocation is one-way. If a later cycle needs ingestion again, issue a fresh token.
