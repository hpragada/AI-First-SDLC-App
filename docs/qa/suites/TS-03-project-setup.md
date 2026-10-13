# TS-03 · Project Setup

Creating the project under test, filling in the project profile that every agent reads, registering
repositories, and the first-run setup checklist that ties the three together. Owned by
**Tester A**. No companion and no phase runs are needed.

**Run these in order.** TC-037 creates `Payment Gateway v2`, which the rest of this suite — and
TS-02's role-matrix cases — work inside. The repository cases build on each other: TC-046 must be
observed before any repo exists, and TC-051 needs the two repos added by TC-047 and TC-050 before
TC-052 removes one.

Use the exact test data from the plan (§3, *The project under test*). Three testers reporting the
same defect with the same values is what collapses three reports into one.

---

### TC-037 · Create a greenfield project

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Functional |
| Priority | Critical |
| Screen | `/projects/new` → `/profile` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin.
- No project named `Payment Gateway v2` exists yet.

**Steps**
1. Go to `/setup` and click **Create project** on step 1 (or navigate to `/projects/new`).
2. Confirm the heading reads `Create a project`.
3. Enter Project name `Payment Gateway v2`.
4. Leave the Track segmented control on **Greenfield**.
5. Click **Create project**.

**Expected**
- The `Track` control offers exactly two options, **Greenfield** and **Brownfield**, with Greenfield
  selected by default.
- The primary button is labelled `Create project` while Greenfield is selected.
- After step 5 the browser lands on `/profile?project=…&setup=1` and the heading reads
  `Project profile`.
- The top-bar project selector now shows `Payment Gateway v2` as the active project.

**Pass / Fail**
- PASS if the project is created and you land on the project profile editor for it.
- FAIL if creation errors, the new project is not selected, or you land anywhere other than
  `/profile`.

**Test data**
- Project name: `Payment Gateway v2` · Track: `Greenfield`

**Notes**
- There is **no repository topology picker** on this screen. Topology is derived from how many repos
  you register (0–1 single · 2 split · 3+ multi) and reconciled server-side. Some design docs are
  stale on this point — do not raise its absence as a defect.
- The **Create project** button stays disabled until the name field has content; that is intended.

---

### TC-038 · A duplicate project name is accepted, creating two identical projects

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Negative |
| Priority | High |
| Screen | `/projects/new` → `/profile` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin.
- TC-037 has passed, so `Payment Gateway v2` already exists in this workspace.
- **Read the cleanup note before you start** — this case leaves a second project behind that will
  confuse every later case in the suite if you do not deal with it.

**Steps**
1. Go to `/projects/new`.
2. Enter Project name `Payment Gateway v2 DUPLICATE-TC038`.
3. Click **Create project** and note where you land.
4. Open the top-bar project selector and read the options.
5. Go back to `/projects/new`, enter the **exact** existing name `Payment Gateway v2`, and click
   **Create project**.
6. Read the screen, then open the top-bar project selector again and read the options.

**Expected**
- Steps 2–3 are the control: a genuinely new name is accepted and lands you on
  `/profile?project=…&setup=1`. This proves the create path works before the duplicate is tried.
- At step 5 the duplicate name is **also** accepted. No inline error appears under `Project name *`,
  the Track control stays visible, and you land on `/profile?project=…&setup=1` for a brand-new,
  empty project.
- At step 6 the selector lists `Payment Gateway v2` **twice**, with nothing to tell the two apart.
- The project you land on after step 5 has an empty profile — it is **not** the one you filled in
  during TC-041.

**Pass / Fail**
- **Expect this case to fail today.** There is no uniqueness constraint on project name anywhere in
  the product.
- PASS only if the duplicate name is refused and no second project is created.
- FAIL if a second `Payment Gateway v2` is created and appears in the selector — which is what the
  current build does.

**Test data**
- Control name: `Payment Gateway v2 DUPLICATE-TC038` · duplicate name: `Payment Gateway v2`

**Notes**
- Raise once, **Medium** severity, against this case: two projects with the same name are
  indistinguishable in the only control that switches between them, so a tester (or a user) can
  spend a phase run pointed at the wrong one.
- **Cleanup is not optional.** There is no delete-project control in the UI, so you cannot remove the
  duplicates. Instead: **rename them so you can tell them apart.** There is no rename control either
  — so the practical mitigation is to identify the real project by its profile content
  (`/profile` shows the description you saved in TC-041) and to select it by walking both selector
  options until `/profile` shows that description. Record which selector position is the real one
  and use it for the rest of the suite.
- If picking the wrong one is costing you time, the safest recovery is to run the rest of TS-03
  against the **control** project from step 2 instead — it has a unique name, so the selector is
  unambiguous. Say so in the tracker if you do.
- The duplicate selector entries are compounded by TS-02 TC-521 (one option per role grant). Two
  distinct defects, both visible in the same control.

---

### TC-039 · The Track control explains itself via a tooltip

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | UX |
| Priority | Low |
| Screen | `/projects/new` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1 Owner-Admin, on `/projects/new` with the name field empty.

**Steps**
1. Hover over the `ⓘ` icon next to the `Track` label and wait for the tooltip.
2. Hover over the **Greenfield** button, then the **Brownfield** button.
3. Tab to the `ⓘ` icon with the keyboard and confirm it can take focus.

**Expected**
- The tooltip text is
  `Greenfield starts from a blank profile. Brownfield opens onboarding to assess what already
  exists.`
- The same text appears when hovering either segmented button.
- The `ⓘ` icon is keyboard-focusable and carries the same text as its accessible label.

**Pass / Fail**
- PASS if the tooltip appears with exactly that copy from all three affordances.
- FAIL if no tooltip appears, or the copy differs.

**Test data**
- *(none)*

**Notes**
- The explainer used to be a wall of help text on the form (Bugs.xlsx row 9); the tooltip is the
  intended replacement, so its absence would be a regression.

---

### TC-040 · Brownfield routes to onboarding

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Functional |
| Priority | Medium |
| Screen | `/projects/new` → `/onboarding` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin.

**Steps**
1. Go to `/projects/new`.
2. Enter Project name `QA Brownfield Probe`.
3. Click **Brownfield** on the Track control.
4. Read the button label and the banner, then click **Create & start onboarding**.
5. Note the URL you land on, then switch the top-bar project selector back to `Payment Gateway v2`.

**Expected**
- Selecting Brownfield changes the primary button label to `Create & start onboarding`.
- An info banner titled `Next: Onboarding` appears above the buttons.
- After step 4 the browser lands on `/onboarding`.

**Pass / Fail**
- PASS if the button label changes, the banner appears, and creation lands on `/onboarding`.
- FAIL if a brownfield project lands on `/profile`, or the label never changes.

**Test data**
- Project name: `QA Brownfield Probe` · Track: `Brownfield`

**Notes**
- **Stop at the first onboarding screen.** The entire brownfield track is out of scope for this
  cycle (plan §1) — do not upload documents, register tools, or run a gap report, and do not raise
  defects against anything past this landing.
- Remember to switch the active project back to `Payment Gateway v2` before continuing, or every
  later case in this suite will target the wrong project.
- **`Payment Gateway v2` may appear more than once in the selector** — once per duplicate project
  created by TC-038, and once per role grant you hold on it (TS-02 TC-521). Both are known defects
  raised elsewhere; do **not** raise them here. To confirm you picked the right one, open `/profile`
  and check the description matches the text you saved in TC-041. If it is blank, you are on a
  duplicate — go back and pick the other option.

---

### TC-041 · Save the project profile and return to the setup checklist

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | E2E |
| Priority | Critical |
| Screen | `/profile?setup=1` → `/setup` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin.
- You arrived at `/profile?project=…&setup=1` from TC-037 (re-run TC-037's navigation if you have
  since left the screen).

**Steps**
1. Confirm the save-state indicator next to the **Save** button reads `Draft · not saved yet`.
2. Enter Description
   `A card payment gateway that accepts Stripe webhooks, reconciles charges, and exposes a refunds API.`
3. Enter Domain `Payments`, Tech stack `Django 5, React 18, Postgres 16`, and NFRs
   `P95 API latency under 200ms. 99.9% uptime. PCI-DSS SAQ-A scope.`
4. Click **Save**.

**Expected**
- The save-state indicator moves from `Draft · not saved yet` to `● Unsaved changes` as soon as you
  type, and settles on `✓ Saved · v1` after the save.
- Because the URL carried `setup=1`, the browser navigates to `/setup` once the save completes.
- Returning to `/profile` from the sidebar shows the saved values still in the fields.

**Pass / Fail**
- PASS if the profile saves as v1 and the screen returns to `/setup`.
- FAIL if the save errors, the values are lost on reload, or the setup redirect does not happen.

**Test data**
- The exact profile values from the plan §3 (*The project under test*).

**Notes**
- Reaching `/profile` from the sidebar has no `setup=1`, so saving there stays on the profile — that
  is the intended difference, checked in TC-042.

---

### TC-042 · Re-saving the profile creates a new version

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Functional |
| Priority | High |
| Screen | `/profile` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-041 has passed — the profile is saved at v1.
- Logged in as P1 Owner-Admin, on `/profile` reached from the sidebar (no `setup=1` in the URL).

**Steps**
1. Confirm the indicator reads `✓ Saved · v1` and the **Save** button is disabled.
2. Append ` Handles refunds and chargebacks.` to the Description.
3. Read the indicator and the hint below the form.
4. Click **Save** and watch the indicator.

**Expected**
- With no edits the **Save** button is disabled and the indicator reads `✓ Saved · v1`.
- After step 2 the indicator changes to `● Unsaved changes`, **Save** becomes enabled, and a hint
  below the form reads `Saving will create v2.`
- During the save the indicator reads `⟳ Saving…` and the button label becomes `Saving…`.
- After the save the indicator reads `✓ Saved · v2` and the browser stays on `/profile`.

**Pass / Fail**
- PASS if the version increments v1 → v2 and all three indicator states are seen.
- FAIL if the version does not increment, the hint names the wrong version, or the screen navigates
  away.

**Test data**
- Appended text: ` Handles refunds and chargebacks.`

**Notes**
- Every save creates a version — saving five times gets you to v6. Do not raise the version count as
  a defect; it is the designed behaviour.

---

### TC-043 · The profile will not save without a description, and says why

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Negative |
| Priority | High |
| Screen | `/profile` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin, on `/profile` for `Payment Gateway v2`.

**Steps**
1. Note the current version in the save-state indicator (e.g. `✓ Saved · v2`), and note the
   `Description` label.
2. Type `Node 20` at the end of the `Tech stack` field.
3. Select all the text in the Description field and delete it.
4. Confirm the indicator reads `● Unsaved changes` and **Save** is enabled.
5. Click something outside the form so the cursor is not in Description, then click **Save**. Watch
   the indicator, the Description field and where the cursor goes.
6. Type `Payments service` into Description.
7. Delete the Description text again, then reload the page.

**Expected**
- The `Description` label is followed by a required marker `*`; no other field on the form has one.
- At step 5 the save does not go through: the indicator stays on `● Unsaved changes`. It never shows
  `⟳ Saving…` and never advances to `✓ Saved · v{n+1}`.
- At step 5 the Description field is marked in error with the message
  `A description is required — agents rely on it for every phase.` and the cursor is placed in the
  Description field.
- Every other field stays on screen with what you typed — `Tech stack` still ends with `Node 20`.
- At step 6 the error message clears as soon as Description has text.
- After the reload in step 7 the previously saved description is back in the field and the version
  number is the same one you noted in step 1 — the stored profile was never touched.

**Pass / Fail**
- PASS if the empty description is refused with that exact message, the cursor moves to Description,
  the other fields keep their values, and the stored profile and its version are untouched after the
  reload.
- FAIL if a profile with an empty description **is** saved, if the version increments, if Save stops
  with no message (the old silent behaviour), if the other fields disappear or lose their text, or if
  the app errors.

**Test data**
- Description: *(empty)* · Tech stack addition: `Node 20`

**Notes**
- The server enforces the same rule in the same words, so a blank description cannot be saved by any
  route. From the browser you will only ever see the on-screen message above.
- A description of only spaces counts as empty.
- Step 7's reload discards your unsaved `Tech stack` edit — that is expected.

---

### TC-044 · Export policy offers a row per exportable phase

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Functional |
| Priority | Medium |
| Screen | `/profile` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin, on `/profile` for `Payment Gateway v2` with a saved profile.

**Steps**
1. Scroll to the `Export policy` field and read its help text.
2. List the phase rows shown.
3. On the `PRD` row, change the select to `Confluence — Documentation store`.
4. Click **Save**, then reload the page and return to `/profile`.

**Expected**
- The help text reads `Where each phase's artifacts may be exported by the user. Exports are always
  manual — gate approval never auto-publishes to external tools.`
- There is one row per exportable phase: `Ideation`, `Requirements`, `PRD`, `Architecture`,
  `UX Design`, `Task Breakdown`, `Testing`, `Test Automation`, `Security`, `CI/CD`.
- Each row's select offers a `Default — …` option plus `Internal only`,
  `Confluence — Documentation store`, `Jira — Task tracker` and `Xray — Test management`.
- After step 4 the `PRD` row still reads `Confluence — Documentation store` — the override
  persisted with the profile save.

**Pass / Fail**
- PASS if all ten phase rows render and an override survives a save and reload.
- FAIL if rows are missing, the options differ, or the override is lost on reload.

**Test data**
- PRD export target: `Confluence — Documentation store`

**Notes**
- Changing an export target marks the profile dirty and will create a new version on save — that is
  expected.
- Setting a target here does not publish anything; exports stay manual and gated (TS-10).

---

### TC-045 · UX Design export is locked to internal

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | UX |
| Priority | Low |
| Screen | `/profile` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin, on `/profile` for `Payment Gateway v2`.

**Steps**
1. Scroll to the `Export policy` field and find the `UX Design` row.
2. Open its select and read every option.
3. Read the text beside the select.

**Expected**
- The `UX Design` select offers only the `Default — …` option and `Internal only`. Confluence, Jira
  and Xray are **not** offered on this row.
- The note `Figma export coming later` is shown next to the select.
- Every other phase row still offers all four targets.

**Pass / Fail**
- PASS if UX Design is limited to internal and carries the note.
- FAIL if an external target can be chosen for UX Design, or the note is missing.

**Test data**
- *(none)*

**Notes**
- The restriction is deliberate — the Figma connector is not built. Do not raise the missing options
  as a defect; only a *missing restriction* is one.

---

### TC-046 · The repositories empty state

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | UX |
| Priority | Medium |
| Screen | `/repositories` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin with `Payment Gateway v2` selected.
- No repositories have been registered on the project yet — **run this before TC-047**.

**Steps**
1. Click **Repositories** in the sidebar.
2. Read the heading and the panel.

**Expected**
- The heading is `Repositories` with the sub-line
  `Where build PRs open. Multi-repo drives API-contract & drift checks.`
- An empty state is shown titled `No repositories yet` with the text
  `Add a repository so build phases know where to open pull requests.` and a **+ Add repository**
  action.
- No table and no `Topology:` chip are rendered while the list is empty.

**Pass / Fail**
- PASS if the empty state renders with that exact title and copy.
- FAIL if an empty table renders instead, or the screen errors.

**Test data**
- *(none)*

**Notes**
- Once TC-047 adds a repo, this state is unreachable without removing every repository again.

---

### TC-047 · Add a repository

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Functional |
| Priority | Critical |
| Screen | `/repositories` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin with `Payment Gateway v2` selected, on `/repositories`.

**Steps**
1. Click **+ Add repository**.
2. Enter Repository (owner/repo) `acme/payments-api`.
3. Open the `Role` select and confirm it offers `backend`, `frontend` and `infra`; leave it on
   `backend`.
4. Set `Base branch` to `main` and leave `Preview URL (optional)` empty.
5. Click **Add**.

**Expected**
- The add form shows the fields `Repository (owner/repo)`, `Role`, `Base branch` and
  `Preview URL (optional)`, plus the help line explaining that a preview URL lets the testing phase
  open the running app.
- After step 5 a table appears with headers `Repository`, `Role`, `Default base`, `Preview URL`,
  `Status`.
- The new row reads `acme/payments-api`, role chip `backend`, default base `main`, Preview URL
  `Not set`, and a status badge.
- A chip above the table reads `Topology: single`.

**Pass / Fail**
- PASS if the repository is registered and appears in the table with the values entered.
- FAIL if the add errors, the row does not appear without a manual refresh, or the role/base branch
  are not what you chose.

**Test data**
- `acme/payments-api` · role `backend` · base branch `main`

**Notes**
- The **Add** button stays disabled until the repository name has content; that is intended.

---

### TC-048 · Adding the same repository twice is refused

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Negative |
| Priority | High |
| Screen | `/repositories` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-047 has passed — `acme/payments-api` is registered on `Payment Gateway v2`.
- Logged in as P1 Owner-Admin on `/repositories`.

**Steps**
1. Click **+ Add repository**.
2. Enter Repository (owner/repo) `acme/payments-api` (identical to the existing one).
3. Click **Add**.
4. Read the screen.

**Expected**
- No duplicate row is created.
- The add form collapses to a single field showing the error
  `acme/payments-api is already registered on this project.`
- The repositories table and the `Topology:` chip stay visible below the error, still listing
  `acme/payments-api` once.

**Pass / Fail**
- PASS if the duplicate is refused with that exact copy.
- FAIL if a second row for the same repository appears, or a raw `409` is shown.

**Test data**
- `acme/payments-api` (already registered)

**Notes**
- The collapsed error form has no **Cancel** button. Navigating away and back to `/repositories`
  clears it. Note that as a Low usability observation at most.

---

### TC-049 · Set and save a repository's preview URL

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Functional |
| Priority | Medium |
| Screen | `/repositories` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- `acme/payments-api` is registered and the table is visible.
- Logged in as P1 Owner-Admin on `/repositories`.

**Steps**
1. In the `Preview URL` column of the `acme/payments-api` row, confirm it reads `Not set` and click
   **Edit**.
2. Type `http://127.0.0.1:5173` into the field.
3. Click **Save**.
4. Reload the page.
5. Click **Edit** again, clear the field, and click **Cancel**.

**Expected**
- **Edit** swaps the cell for a text input with **Save** and **Cancel** buttons.
- After step 3 the cell shows `http://127.0.0.1:5173` with an **Edit** button again.
- After the reload the value is still `http://127.0.0.1:5173` — it persisted.
- **Cancel** in step 5 discards the change: the cell still shows `http://127.0.0.1:5173`.

**Pass / Fail**
- PASS if the preview URL saves, survives a reload, and Cancel discards.
- FAIL if the value is lost on reload, or Cancel commits the edit.

**Test data**
- Preview URL: `http://127.0.0.1:5173`

**Notes**
- The preview URL is what the testing phase opens to write tests against a live app (TS-13); it has
  no effect on this screen beyond being stored.

---

### TC-050 · The topology chip changes once a second repository exists

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Functional |
| Priority | Medium |
| Screen | `/repositories` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Exactly one repository (`acme/payments-api`) is registered.
- Logged in as P1 Owner-Admin on `/repositories`.

**Steps**
1. Note the chip above the table — it should read `Topology: single`.
2. Click **+ Add repository**, enter `acme/payments-web`, set Role to `frontend`, Base branch
   `main`, and click **Add**.
3. Without reloading, read the chip and the table again.
4. Reload the page and read the chip and the table once more.

**Expected**
- With one repository the chip reads `Topology: single`.
- At step 3, straight after **Add**: the add form has closed, both rows are in the table, and the
  chip reads `Topology: split` — no reload needed.
- Each row now offers **Set default** except the row carrying the `default` badge.
- At step 4 the table and the chip are unchanged: two rows, `Topology: split`.

**Pass / Fail**
- PASS if the form closes on a successful add and the chip reads `Topology: split` with two
  repositories, both before and after the reload.
- FAIL if the form stays open after a successful add, if the chip needs a reload to change, if it
  reads anything other than `Topology: split` at two repositories (e.g. `Topology: multi`), or if the
  second row is missing.

**Test data**
- Second repo: `acme/payments-web` · role `frontend` · base branch `main`

**Notes**
- The chip shows the platform's own topology, which is set by repository count: 0–1 `single` ·
  2 `split` · 3 or more `multi`. A third repository would read `Topology: multi`.
- The add form also has a **Cancel** button that closes it without adding anything.

---

### TC-051 · Set default moves the default marker to the chosen repository

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Functional |
| Priority | Medium |
| Screen | `/repositories` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Two repositories are registered (TC-050), so the row actions include **Set default**.
- Logged in as P1 Owner-Admin on `/repositories`.

**Steps**
1. Note which row's `Default base` cell carries the green `default` badge, and that this row has
   only **Remove** in its actions.
2. Click **Set default** on the *other* row.
3. Read the table.
4. Reload the page and read it again.
5. Click **Set default** on the original row to put the default back.

**Expected**
- After step 2, without a reload, the `default` badge has moved to the row you clicked; that row's
  **Set default** button is gone and the other row now shows **Set default**.
- Exactly one row carries the `default` badge at any time.
- No banner or dialog appears on success — the badge moving is the confirmation.
- After the reload the row you chose in step 2 is still the default.
- Step 5 moves the badge back the same way.

**Pass / Fail**
- PASS if **Set default** changes which repository is the default, the marker moves at once, and the
  change survives the reload.
- FAIL if the button does nothing, if two rows show `default`, if the change is lost on reload, or if
  a raw error is shown.

**Test data**
- *(none)*

**Notes**
- **Set default** appears only when two or more repositories exist — with a single repo the row shows
  only **Remove**.
- The plan §10 "known inert" entry for `Set default` is superseded: the button is wired.
- If the change is refused (for example a user without the tech lead or admin role), a red banner
  titled `Couldn't set the default repository` appears above the table with the server's reason. That
  path is not exercised here.

---

### TC-052 · Remove a repository

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Functional |
| Priority | Medium |
| Screen | `/repositories` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Two repositories are registered (TC-050).
- Logged in as P1 Owner-Admin on `/repositories`.

**Steps**
1. Click **Remove** on the `acme/payments-web` row.
2. Read the table.
3. Read the topology chip.
4. Reload the page.

**Expected**
- The `acme/payments-web` row disappears without a manual refresh; `acme/payments-api` remains.
- The chip returns to `Topology: single`.
- After the reload only `acme/payments-api` is listed.

**Pass / Fail**
- PASS if the repository is removed, the survivor is untouched, and the topology chip reverts.
- FAIL if the row returns after a reload, or the wrong repository is removed.

**Test data**
- Removed: `acme/payments-web`

**Notes**
- There is no confirmation dialog on **Remove** — one click deletes. Worth at most a Low defect;
  it matches the current design.
- Leave `acme/payments-api` registered — TS-07 and TS-15 need it.

---

### TC-053 · Only a tech lead or admin can register a repository

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Permission |
| Priority | Critical |
| Screen | `/repositories` |
| Persona | P10 Engineer / P5 Tech Lead |
| Automation | No |

**Preconditions**
- P10 Engineer (`qa+a.eng@edvensoft.com`) exists and holds only the `engineer` role on
  `Payment Gateway v2`.
- P5 Tech Lead (`qa+a.lead@edvensoft.com`) exists and holds `tech_lead` on the same project — invite
  and grant it via TS-02 TC-024 and TC-030 if you have not already.

**Steps**
1. Sign out and log in as P10 Engineer. Go to `/repositories`.
2. Confirm the existing repository list is readable.
3. Click **+ Add repository**, enter `acme/payments-jobs`, role `backend`, base branch `main`, and
   click **Add**.
4. Reload the page and check whether `acme/payments-jobs` is listed.
5. Sign out, log in as P5 Tech Lead, and repeat step 3 with the same values.
6. Reload and check the table again.

**Expected**
- Step 2: the engineer can *read* the repository list (read access is open to any project member).
- Steps 3–4: the repository is **not** created — after the reload `acme/payments-jobs` is absent.
- Steps 5–6: the tech lead's add succeeds and `acme/payments-jobs` appears in the table.

**Pass / Fail**
- PASS if the engineer's add is refused and the tech lead's succeeds.
- FAIL if the engineer can register a repository — that is a **Critical** permission defect.

**Test data**
- `acme/payments-jobs` · role `backend` · base branch `main`

**Notes**
- The engineer's rejected add is **not** silent: a red banner titled
  `Couldn't add that repository` appears inside the add form, carrying the server's reason in plain
  words. Record the wording you saw. Raise a defect if the refusal is silent, or if the banner shows
  a raw status code or an internal role key.
- Removing a repository and editing a preview URL are gated the same way — spot-check **Remove** as
  the engineer and record it in the same row.
- Clean up afterwards: as the tech lead or admin, remove `acme/payments-jobs`.

---

### TC-054 · The setup checklist reflects completed steps

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Functional |
| Priority | High |
| Screen | `/setup` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin.
- At least step 1 is complete (`Payment Gateway v2` exists) and step 3 is complete (P10 Engineer has
  joined), but no machine has been connected yet.

**Steps**
1. Go to `http://localhost:5173/setup`.
2. Read the heading and the four step cards.
3. Read the badge or action on each card.

**Expected**
- Because some steps are done, the header reads `Setup · 2 of 4 complete` (the count matching what
  you have actually finished).
- Four cards are listed: `Create your first project`, `Connect your machine`,
  `Invite your team & assign roles`, and `Connect integrations` marked `(optional)`.
- Completed steps show a `✓` numeral and a `Done` badge instead of their action button; step 1's
  description names your project, e.g. `Payment Gateway v2 created.`
- Incomplete steps still show their action button (**Connect**, **Invite team**).

**Pass / Fail**
- PASS if the completed steps show `Done` and the count in the heading matches them.
- FAIL if a finished step still shows its action button, or the count is wrong.

**Test data**
- *(none)*

**Notes**
- On a brand-new workspace with nothing done, the header is instead the welcome heading
  `Welcome to QA Alpha 👋` — that variant was already checked in TS-01 TC-001.

---

### TC-055 · Setup step 4 never completes, however many integrations you connect

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | UX |
| Priority | Medium |
| Screen | `/setup` → `/integrations` → `/setup` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1 Owner-Admin.
- `Payment Gateway v2` exists (TC-037) and P10 Engineer has joined (TS-01 TC-021), so steps 1 and 3
  of the checklist are complete.
- **No machine has been connected to your workspace**, so step 2 is still incomplete and the
  checklist itself is still on screen. Tester A never connects one — if the checklist has been
  replaced by a completion card, see the Notes.

**Steps**
1. Go to `http://localhost:5173/setup`. Confirm the header reads `Setup · 2 of 4 complete` and all
   four step cards are listed.
2. Read step 4 (`Connect integrations (optional)`) and note its badge or action.
3. Go to `/integrations` and connect one integration.
4. Return to `/setup` and read step 4 again, and the count in the header.
5. Connect a second integration, return to `/setup`, and read step 4 once more.

**Expected**
- Step 4 should show a `✓` numeral and a `Done` badge once at least one integration is connected,
  and the header count should rise to `3 of 4`.
- Actual behaviour today: step 4 keeps its numeral `4` and its **Connect** button at every one of
  steps 2, 4 and 5. The header count never moves past `2 of 4` on account of integrations.
- Steps 1 and 3 do show `✓` and `Done`, proving the checklist can render a completed step — so this
  is specific to step 4, not a broken checklist.

**Pass / Fail**
- **Expect this case to fail today.**
- PASS only if step 4 reaches `Done` after an integration is connected.
- FAIL if step 4 keeps its **Connect** button with integrations connected — which is what the
  current build does.

**Test data**
- Any one integration from `/integrations` (TS-04 owns the connect flow itself; here it is only a
  fixture — a successfully connected capability is all this case needs).

**Notes**
- Raise once, **Medium** severity, against this case: step 4's completion is never computed, so the
  checklist permanently understates progress and tells a finished user to go and do something they
  have already done.
- **The second half of this defect is unobservable from Tester A's workspace, and that is
  deliberate.** Once steps 1–3 are all complete the checklist is *replaced* by a card reading
  `Setup complete — you're ready to run phases` / `All four steps done. This checklist won't show
  again.` — which is untrue twice over (step 4 is not done, and **Dismiss** does not survive a
  reload). Reaching that card needs a connected machine, which Tester A does not have. Do **not**
  chase Tester C for one and do not mark this case Blocked on it. Add a line to the defect saying
  the completion card asserts "all four steps done" while step 4 can never complete, and leave the
  verification of that card to whoever runs the checklist with a companion attached.
- If you arrive and the completion card is already showing — someone enrolled a machine on your
  workspace — you cannot run this case as written. Mark it **Blocked**, note that the checklist was
  unreachable, and say who has a companion on your tenant.

---

### TC-541 · A plain engineer can create a project

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Permission |
| Priority | High |
| Screen | `/projects/new` |
| Persona | P10 Engineer |
| Automation | Yes |

**Preconditions**
- P10 Engineer (`qa+a.eng@edvensoft.com`) exists and holds only the `engineer` role on
  `Payment Gateway v2` — no admin role, no tech lead role.
- Sign out of the admin account and log in as `qa+a.eng@edvensoft.com` / `QaTest-2026!`.

**Steps**
1. As P10 Engineer, paste `http://localhost:5173/projects/new` into the address bar.
2. Note whether the screen renders or refuses.
3. Enter Project name `QA Engineer Probe TC541`, leave the Track on **Greenfield**, and click
   **Create project**.
4. Note where you land.
5. Open the top-bar project selector and read the options.
6. Sign out, log back in as P1 Owner-Admin, and open the project selector again.

**Expected**
- Creating a project should be reserved to a workspace admin: `/projects/new` should refuse the
  engineer, or the create should be rejected.
- Actual behaviour today: the form renders, the create succeeds, the engineer lands on
  `/profile?project=…&setup=1` for the new project, and `QA Engineer Probe TC541` is listed in their
  project selector.
- At step 6 the admin sees the engineer's project too — a non-admin has permanently added a project
  to the workspace that the admin cannot delete from the UI.

**Pass / Fail**
- **Expect this case to fail today.**
- PASS only if the engineer is refused — either the route shows an access panel, or **Create
  project** produces a refusal and no project is created.
- FAIL if the project is created by a plain engineer — which is what the current build does.

**Test data**
- `qa+a.eng@edvensoft.com` / `QaTest-2026!` · project name `QA Engineer Probe TC541`

**Notes**
- Raise once, **High** severity, against this case. Project creation is unauthenticated-by-default
  on the server — the project endpoint has no permission class of its own, so it inherits the API's
  permissive default. The creating user is additionally granted the `admin` role **on the project
  they just made**, so an engineer can mint themselves a project they fully control.
- **Do not raise TC-542's profile hole as part of this defect** — they share a root cause but are
  separate reachable behaviours and should be re-tested independently.
- The probe project cannot be deleted from the UI. Leave it and name it in the tracker so nobody
  mistakes it for a real fixture; its distinctive name keeps it out of the way of the
  `Payment Gateway v2` selector confusion in TC-038.
- Reach this state by signing out and signing in as the engineer — never by editing storage.

---

### TC-542 · A plain engineer can rewrite the project profile every agent reads

| Field | Value |
|---|---|
| Suite | TS-03 Project Setup |
| Type | Permission |
| Priority | Critical |
| Screen | `/profile` |
| Persona | P10 Engineer |
| Automation | Yes |

**Preconditions**
- TC-041 has passed — `Payment Gateway v2` has a saved profile with the plan §3 description, at a
  known version number.
- P10 Engineer exists and holds only the `engineer` role on `Payment Gateway v2`.
- As P1 Owner-Admin, open `/profile` for `Payment Gateway v2` and **write down the current version
  number** from the save-state indicator (e.g. `✓ Saved · v2`) and the current description.

**Steps**
1. Sign out and log in as `qa+a.eng@edvensoft.com` / `QaTest-2026!`.
2. Confirm `Payment Gateway v2` is the selected project, then click **Project profile** in the
   sidebar.
3. Note whether the profile renders read-only or editable.
4. Replace the whole Description with `Overwritten by an engineer — TC-542.`
5. Click **Save** and watch the save-state indicator.
6. Reload the page and read the Description and the version.
7. Sign out, log back in as P1 Owner-Admin, open `/profile`, and read the Description and version.
8. Restore the original description from the plan §3 and click **Save**.

**Expected**
- The project profile is the document every agent reads before every phase. A plain engineer should
  get a read-only view, or the save should be refused.
- Actual behaviour today: the fields are editable, **Save** succeeds, the indicator advances to
  `✓ Saved · v{n+1}`, and the change survives the reload.
- At step 7 the admin sees the engineer's text and the incremented version — the overwrite is
  workspace-wide, not local to the engineer.

**Pass / Fail**
- **Expect this case to fail today.**
- PASS only if the engineer cannot change the stored profile — read-only fields, a disabled
  **Save**, or a refused save leaving the version unchanged.
- FAIL if the engineer's text is visible to the admin at step 7 — which is what the current build
  does.

**Test data**
- Overwrite text: `Overwritten by an engineer — TC-542.`

**Notes**
- Raise once, **Critical** severity, against this case. This is not a cosmetic permission gap: the
  profile is the source of truth injected into every agent run, so anyone who can edit it can
  silently redirect what every future phase produces, with no gate and no approval in the way. Same
  root cause as TC-541 (the projects endpoint inherits the API's permissive default) but a far
  higher blast radius — file it separately so it is triaged on its own merits.
- **Step 8 is mandatory.** Leaving the overwritten description in place would corrupt the fixture
  that TS-07, TS-09 and TS-15 all depend on. Confirm after step 8 that `/profile` shows the plan §3
  description again, and note the final version number in the tracker.
- The profile keeps every version, so the restore creates yet another version rather than reverting
  to the old one. That is designed behaviour (TC-042) — do not raise it.
