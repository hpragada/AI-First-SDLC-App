# TS-02 · Workspace Admin & Roles

Workspace administration: the user list, the invitation lifecycle (send, resend, revoke), the
per-project role matrix, gate-role coverage, and the guards that keep all of it away from
non-admins. Owned by **Tester A**. No companion and no phase runs are needed.

**Run these in order, and mind two cross-suite dependencies.** TC-024 sends the invitation that
TS-01 TC-021 accepts — run TC-024, then go and run TS-01 TC-021 to create **P10 Engineer**, then
come back for TC-034 to TC-036, which need a signed-in non-admin. The role matrix cases (TC-029
onward) need the project `Payment Gateway v2` from TS-03 TC-037 to exist and be the selected
project, so run TS-03 TC-037 before them.

---

### TC-023 · The users table lists everyone in the workspace

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | Functional |
| Priority | High |
| Screen | `/admin/users` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin.

**Steps**
1. In the sidebar, open the **Admin** group and click **Workspace Admin**.
2. Confirm the browser lands on `/admin/users`.
3. Read the page heading, the sub-line, and the table.

**Expected**
- The heading is `Users & invitations` and the sub-line names your workspace (`QA Alpha`).
- The table headers read `Name`, `Email`, `Status`, `Projects & roles` (plus a trailing actions
  column with no header).
- Your own admin account is listed with the status badge `Active`, its email, and a
  `Projects & roles` value that includes `Tenant-admin`.
- A **+ Invite** button is present in the page header.

**Pass / Fail**
- PASS if the table renders with those headers and the admin's own row is present and Active.
- FAIL if the table is missing, headers differ, or the signed-in admin is not listed.

**Test data**
- *(none)*

**Notes**
- `/admin` on its own redirects to `/admin/users`; check that once here.

---

### TC-024 · Invite a teammate with a project and role grant

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | Functional |
| Priority | Critical |
| Screen | `/admin/users` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin.
- The project `Payment Gateway v2` exists (TS-03 TC-037).
- `qa+a.eng@edvensoft.com` is not yet a member.

**Steps**
1. On `/admin/users`, click **+ Invite**.
2. In the `Invite teammate` drawer, enter Work email `qa+a.eng@edvensoft.com` and
   Name (optional) `QA Alpha Engineer`.
3. Under `Initial project & role grants`, set the Project select to `Payment Gateway v2` and the
   Role select to `Engineer`.
4. Click **+ Add another grant** and confirm a second grant row appears, then remove it again with
   its `✕` button.
5. Click **Send invite**.

**Expected**
- The drawer is titled `Invite teammate` with fields `Work email *` and `Name (optional)` and a
  section labelled `Initial project & role grants`; the footer holds **Cancel** and **Send invite**.
- Step 4 adds and then removes a grant row without affecting the first one.
- After step 5 the drawer closes and a message appears above the table: with SendGrid on, green
  `Invite emailed to qa+a.eng@edvensoft.com`; without it, blue
  `Invite created. The link is in the server terminal.` (TC-951 covers all three messages.)
- A new row appears at the top of the table for `qa+a.eng@edvensoft.com` with the badge
  `Invited · waiting to join`, the line `sent just now` under it, a highlighted background, and
  `Projects & roles` reading `Engineer @ Payment Gateway v2`.
- **Resend** and **Revoke** buttons are present on that row.

**Pass / Fail**
- PASS if the invitation is created and appears as a pending row with the correct grant summary.
- FAIL if the drawer errors, the row does not appear until a manual refresh, or the grant summary
  shows a raw project UUID instead of `Payment Gateway v2`.

**Test data**
- `qa+a.eng@edvensoft.com` · role `Engineer` · project `Payment Gateway v2`

**Notes**
- With SendGrid on, the invite arrives by email; without it, the link is printed to the backend log
  (`docker compose logs backend`). **Go and run TS-01 TC-021 now** to accept it and create P10
  Engineer — TC-034 to TC-036 need that account.

---

### TC-025 · Inviting an address that is already a member is refused

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | Negative |
| Priority | High |
| Screen | `/admin/users` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin.
- `qa+a.eng@edvensoft.com` has already accepted its invitation (TS-01 TC-021).

**Steps**
1. On `/admin/users`, click **+ Invite**.
2. Enter Work email `qa+a.eng@edvensoft.com`.
3. Click **Send invite**.
4. Click **Cancel** to close the drawer.

**Expected**
- No second invitation is created — the table gains no new row.
- An inline error appears under `Work email *` reading
  `qa+a.eng@edvensoft.com is already a member of this workspace.`
- The **Send invite** button becomes disabled, and the Name / grants section is hidden while the
  error is showing.
- **Cancel** closes the drawer cleanly.

**Pass / Fail**
- PASS if the duplicate is refused with that exact copy and **Send invite** is disabled.
- FAIL if a duplicate invitation is created, or the error is generic / shows a raw 409.

**Test data**
- `qa+a.eng@edvensoft.com` (already a member)

**Notes**
- Once the error latches, the only way back is **Cancel** and re-opening the drawer — that is the
  current design, not a defect.

---

### TC-026 · Resend a pending invitation

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | Functional |
| Priority | Medium |
| Screen | `/admin/users` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1 Owner-Admin.
- A pending invitation exists — create one for `qa+a.po@edvensoft.com` via TC-024's steps if needed.

**Steps**
1. Copy the **current** invite link for `qa+a.po@edvensoft.com` (from its email, or from
   `docker compose logs backend` without SendGrid). Keep it — you need it in step 5.
2. On `/admin/users`, find the row badged `Invited · waiting to join` for that address and click
   **Resend**.
3. Read the message above the table and the row, then copy the **new** link.
4. In a private window, open the new link.
5. In the same private window, open the link you saved in step 1.

**Expected**
- The message above the table reads `Invite emailed to qa+a.po@edvensoft.com` (SendGrid on) or
  `Invite created. The link is in the server terminal.` (off).
- The row stays in the table with the badge `Invited · waiting to join`, and its line now reads
  `sent just now` — resending does not remove or duplicate it.
- The newly issued link opens the `Join QA Alpha` form.
- The **previous** link (step 5) now reads `This link doesn't work any more` / `A newer invite may
  have replaced it. Open the most recent invite email, or ask your workspace admin.`

**Pass / Fail**
- PASS if exactly one pending row survives, the message says what happened, the new link opens the
  join form, and the old link is dead.
- FAIL if the row disappears or is duplicated, no message appears, the resent link does not work,
  or the old link still works.

**Test data**
- `qa+a.po@edvensoft.com`

**Notes**
- **The old link going dead is the oracle, not a defect.** Resending rotates the token and extends
  the expiry by design.
- The old link's page cannot tell "replaced" from "damaged", so it says both, without blaming the
  reader (Bugs S.No 357).

---

### TC-027 · Revoke a pending invitation

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | Functional |
| Priority | High |
| Screen | `/admin/users` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1 Owner-Admin.
- The pending invitation for `qa+a.po@edvensoft.com` from TC-026 exists, and you still have its
  most recent link.

**Steps**
1. On `/admin/users`, find the `Invited · pending` row for `qa+a.po@edvensoft.com`.
2. Click **Revoke**.
3. Watch the table.
4. In a private window, open the invite link you saved for that address.
5. Reload `/admin/users` and read the table once more.

**Expected**
- The pending row disappears from the table without a manual page refresh.
- No `Invited · waiting to join` badge remains for that address, and it does not come back after the
  reload in step 5.
- Step 4 shows `This invite was cancelled` / `Ask {your name} if you still need access.` — the
  revoked link no longer works.

**Pass / Fail**
- PASS if the row is removed, stays removed after a reload, and the link is dead.
- FAIL if the row stays, reappears on refresh, or the revoked link still creates an account.

**Test data**
- `qa+a.po@edvensoft.com`

**Notes**
- **The reload in step 5 and the dead link in step 4 are the real oracles.** The row vanishing on
  its own is not proof the revoke reached the server: **Revoke** has no error handler and the screen
  has no error surface, so a revoke that fails server-side is completely silent. Only the reload
  (does the row come back?) and the link test (does it still work?) can tell the two apart.
- If the row comes back on reload, or the revoked link still opens the join form, raise it as a
  **High** defect — a revoked invitation that still works is an access-control failure — and include
  the missing error feedback in the same row rather than raising it separately.
- There is no confirmation dialog on **Revoke**; a single click is destructive. Note it if you think
  that is worth a Low defect, but it matches the current design.

---

### TC-028 · The users empty state

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | UX |
| Priority | Low |
| Screen | `/admin/users` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1 Owner-Admin.

**Steps**
1. Go to `/admin/users`.
2. Look for the empty state panel titled `It's just you so far`.
3. Confirm what is rendered instead.

**Expected**
- The empty state is **not** shown in a live workspace: the signed-in admin is always at least one
  row, so the table renders instead.
- The table shows the admin's own row rather than an empty panel.

**Pass / Fail**
- PASS if the table renders and the `It's just you so far` panel is absent.
- FAIL if a solo admin sees `It's just you so far` and their own row is hidden behind it.

**Test data**
- *(none)*

**Notes**
- The empty state was deliberately narrowed to a truly empty list, which is effectively unreachable
  once an admin exists (Bugs.xlsx row 31.1). The `It's just you so far` copy and its **+ Invite**
  action still exist in the design gallery at `/dev/components`. If you *do* see the empty state on
  `/admin/users`, that is a regression of that fix.

---

### TC-029 · The role matrix renders with a column per role

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | Functional |
| Priority | High |
| Screen | `/admin/roles` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin.
- The project `Payment Gateway v2` exists and is the selected project.
- P10 Engineer has joined (TS-01 TC-021), so there are at least two rows.

**Steps**
1. Go to `/admin/users` and click **Manage** on any active row (or navigate to `/admin/roles`).
2. Read the heading and the matrix.
3. Hover over each column abbreviation.

**Expected**
- The heading is `Roles & memberships`.
- The matrix has a `User` column followed by ten role columns abbreviated
  `PO`, `Arch`, `Design`, `Lead`, `Eng`, `Rev`, `QA`, `Sec`, `DevOps`, `Admin`.
- Each abbreviation has a tooltip with the underlying role key (e.g. `Lead` → `tech_lead`).
- Every user in the workspace has a row with a toggle in each role column; the `Admin` toggle is on
  for the owner account.

**Pass / Fail**
- PASS if all ten columns render in that order and every user has a row of toggles.
- FAIL if columns are missing, the matrix is empty, or a user is absent.

**Test data**
- *(none)*

**Notes**
- The matrix scrolls horizontally on a narrow window — that is expected.

---

### TC-030 · Toggling a role grants it and updates gate-role coverage

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | Functional |
| Priority | Critical |
| Screen | `/admin/roles` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin, on `/admin/roles` with `Payment Gateway v2` selected.
- P10 Engineer (`qa+a.eng@edvensoft.com`) is listed and holds no `Rev` (reviewer) role.

**Steps**
1. In the `Gate-role coverage` panel, note that `Reviewer` shows a red `✗` and read its line in full.
2. Throttle the network to "Slow 3G" in DevTools — the saving banner is otherwise a single frame.
3. In the matrix, click the `Rev` toggle on the `QA Alpha Engineer` row and read the banner that
   replaces the matrix while the save is in flight.
4. Wait for the save to settle, then read the `Gate-role coverage` panel again.
5. Reload the page and confirm the `Rev` toggle is still on.
6. Remove the throttle. Click the same `Rev` toggle again to remove the grant, and read the coverage
   panel once more.

**Expected**
- At step 1 the `Reviewer` line reads, in full:
  `Reviewer — nobody (no Reviewer assigned — an admin can approve the merge gate)`.
- At step 1 a single yellow warning line sits above the matrix, because at least one gate role
  (`Reviewer`) has nobody. Its bold opening depends on how many gate roles are empty on the project:
  one → `Nobody holds Reviewer on Payment Gateway v2.`; two → `Nobody holds {Role} or {Role} on
  Payment Gateway v2.`; three or more → `{N} roles have nobody on Payment Gateway v2.` It continues
  `That gate falls to an admin meanwhile —` (one role) or `Those gates fall to an admin meanwhile —`
  (two or more), followed by a link button **see gate-role coverage**. It is one line, never a list.
- Clicking **see gate-role coverage** scrolls the page to the `Gate-role coverage` panel.
- At step 3 the matrix, the warning line and the coverage panel are **replaced** by an info banner reading
  `Saving role change for QA Alpha Engineer (Reviewer @ Payment Gateway v2)…` — naming the real user
  and role, not a sample. The matrix returns when the save settles.
- After step 4 the coverage panel shows `Reviewer` with a green `✓` and
  `Reviewer — QA Alpha Engineer` (no parenthetical once the role is covered).
- After step 5 the toggle is still on — the grant persisted.
- After step 6 the toggle is off and the `Reviewer` line is back to the full step-1 text.

**Pass / Fail**
- PASS if the toggle grants and revokes the role, the grant survives a reload, and the coverage
  panel follows both ways with the copy above.
- FAIL if the toggle does not persist across the reload, the banner names a hardcoded user such as
  `Tom Reyes`, or coverage never updates.

**Test data**
- User `QA Alpha Engineer` · role column `Rev` (`reviewer`)

**Notes**
- **The parenthetical is expected.** An uncovered gate role always carries the admin-fallback note
  (`— an admin can approve the {gate}`) because a tenant admin can decide any gate. A bare
  `Reviewer — nobody` with no parenthetical would be the defect.
- **The banner and the matrix are mutually exclusive** — while saving, the screen renders only the
  saving banner (no matrix, no gate-role warning line, no coverage panel). That is why step 2
  throttles: without it the banner is one frame and you will report it missing.
- **The warning line appears whenever any gate role is empty**, even though you (an admin) are the
  backup. A red variant exists for the case where nobody holds the role **and** no admin could
  approve it: it reads `That gate cannot be approved by anyone until someone holds the role.` (or
  `Those gates cannot be approved by anyone until someone holds the roles.`) and has **no**
  **see gate-role coverage** link. A workspace always keeps at least one admin (TC-031), so you
  should not see the red variant here — raise it if you do.
- The warning's count follows the coverage panel, not the matrix's ten columns: only the gate roles
  listed in `Gate-role coverage` are counted. After step 4 the count drops by one (or the line
  disappears entirely if `Reviewer` was the only empty role); after step 6 it returns.
- If P1's top-bar project selector shows `Payment Gateway v2` more than once, that is the known
  duplicate-option defect covered by TC-521 — do not raise it here.
- Leave the reviewer role **off** at the end so the workspace's role state matches what TS-03 and
  TS-09 expect.

---

### TC-031 · The last admin cannot remove their own admin role

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | Negative |
| Priority | Critical |
| Screen | `/admin/roles` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin.
- You are the **only** tenant admin in the workspace (no one else has the `Admin` toggle on).

**Steps**
1. Go to `/admin/roles`.
2. On your own row, click the `Admin` toggle to switch it off.
3. Read the dialog that appears.
4. Click **Cancel**.
5. Reload the page.

**Expected**
- A modal appears titled `Can't remove the last admin`, with a red banner reading
  `You're the only tenant-admin. Promote another member to admin before removing your own admin
  role, or the workspace would be left unmanageable.`
- The modal has **Cancel** and **Promote a member** buttons.
- After **Cancel** and the reload, your `Admin` toggle is still **on** — the demotion did not happen.
- `/admin/users` still shows your row with `Tenant-admin` in `Projects & roles`.

**Pass / Fail**
- PASS if the demotion is blocked and the guard modal is shown with that copy.
- FAIL if the last admin can demote themselves — that is a **Critical** defect (the workspace would
  become unmanageable).

**Test data**
- *(none)*

**Notes**
- **`Promote a member` is a known inert control** — it just closes the modal (plan §10 known-inert
  list). Confirm and move on; do not raise a new defect.

---

### TC-033 · The roles screen names its project as plain text, following the top-bar selector

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | UX |
| Priority | Low |
| Screen | `/admin/roles` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin.
- At least two projects exist in the workspace (create a second one via TS-03 TC-037's steps if you
  only have one).

**Steps**
1. With `Payment Gateway v2` selected in the top-bar project selector, go to `/admin/roles`.
2. Read the line at the right of the page header, and try clicking it.
3. Switch the top-bar project selector to the other project.
4. Read the header line again.
5. Switch the top-bar selector back to `Payment Gateway v2`.

**Expected**
- At step 2 the header shows the plain text `Project Payment Gateway v2` (the project name in
  bold). It is **not** a dropdown: clicking it opens nothing.
- There is no second project picker anywhere on the page — the top-bar selector is the only one.
- After step 3 the header line names the other project, and the matrix and coverage panel follow it.

**Pass / Fail**
- PASS if the project is shown as non-interactive text and it changes only with the top-bar selector.
- FAIL if a project dropdown or select is rendered on the roles screen, or if the header line names
  a different project from the one selected in the top bar.

**Test data**
- *(none)*

**Notes**
- This case used to check a project select that listed only one project and did nothing. That
  control was replaced by this plain line; the plan §10 "known inert" entry for it is superseded.
- If the top-bar selector lists `Payment Gateway v2` twice, that is TC-521 — do not raise it here.

---

### TC-034 · A non-admin deep-linking to /admin/users is refused

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | Permission |
| Priority | Critical |
| Screen | `/admin/users` |
| Persona | P10 Engineer |
| Automation | Yes |

**Preconditions**
- P10 Engineer exists (TS-01 TC-021) and holds no admin role.
- Sign out of the admin account and log in as `qa+a.eng@edvensoft.com` / `QaTest-2026!`.

**Steps**
1. While signed in as P10 Engineer, paste `http://localhost:5173/admin/users` into the address bar.
2. Read the page.
3. Click **← Back to the dashboard**.
4. Repeat step 1 with `http://localhost:5173/admin/roles`.

**Expected**
- A panel titled `Admin access needed` is shown with the body
  `This page manages workspace users and roles, and is available to workspace admins only. Ask an
  admin to grant you the admin role if you need it.`
- No user list, no email addresses, and no role matrix are rendered at any point.
- **← Back to the dashboard** returns to `/`.
- `/admin/roles` shows the same panel.

**Pass / Fail**
- PASS if both admin routes show the panel and leak no user data.
- FAIL if the user list or role matrix renders for a non-admin — that is a **Critical** defect.

**Test data**
- `qa+a.eng@edvensoft.com` / `QaTest-2026!`

**Notes**
- Reach this state by signing out and signing in as the engineer — never by editing storage.

---

### TC-035 · Admin navigation is hidden from a non-admin

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | Permission |
| Priority | High |
| Screen | app shell (sidebar) |
| Persona | P10 Engineer |
| Automation | Yes |

**Preconditions**
- Signed in as P10 Engineer (`qa+a.eng@edvensoft.com`).

**Steps**
1. Look at the full sidebar as P10 Engineer and list every item.
2. Sign out, sign back in as P1 Owner-Admin, and list the sidebar again.
3. Compare the two.

**Expected**
- As P10 Engineer there is no `Admin` section heading and no **Workspace Admin** item.
- As P10 Engineer there is no **Test Reporting** item in the setup group.
- As P1 Owner-Admin both the `Admin` section with **Workspace Admin** and the **Test Reporting**
  item are present.

**Pass / Fail**
- PASS if both items are hidden for the engineer and present for the admin.
- FAIL if a non-admin sees admin navigation (even if clicking it is blocked) — navigation that leads
  only to a refusal is still a defect.

**Test data**
- P10 `qa+a.eng@edvensoft.com` · P1 `qa+a.owner@edvensoft.com`

**Notes**
- The rest of the sidebar (work items, runs, gates, artifacts, profile, repositories, integrations,
  connect machine) should be identical between the two personas.

---

### TC-036 · A non-admin on /test-reporting gets the workspace-admin refusal

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | Permission |
| Priority | Medium |
| Screen | `/test-reporting` |
| Persona | P10 Engineer |
| Automation | Yes |

**Preconditions**
- Signed in as P10 Engineer (`qa+a.eng@edvensoft.com`).

**Steps**
1. Paste `http://localhost:5173/test-reporting` into the address bar.
2. Read the panel title and body carefully.
3. Click **← Back to the dashboard**.

**Expected**
- The screen shows the panel `Admin access needed` — a non-admin cannot reach test reporting.
- The body is the users-and-roles copy: `This page manages workspace users and roles, and is
  available to workspace admins only. Ask an admin to grant you the admin role if you need it.`
- No CI tokens or test-reporting data are rendered.

**Pass / Fail**
- PASS if access is refused and nothing about CI tokens is exposed.
- FAIL if the test reporting screen renders for a non-admin.

**Test data**
- `qa+a.eng@edvensoft.com`

**Notes**
- The **copy is wrong for this route**: `/test-reporting` is a project resource (CI tokens), not
  user/role management, but it reuses the admin-users refusal panel because it sits inside the same
  route guard. The gating itself is correct and mirrors the backend's tenant-admin check on
  `/ci-tokens/`. Raise the misleading copy once as a **Low** defect against this case; do not raise
  the gating as a defect.

---

### TC-521 · A user with two roles on one project sees that project twice in the selector

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | Functional |
| Priority | Medium |
| Screen | `/admin/roles` → app shell top bar |
| Persona | P10 Engineer |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin on `/admin/roles` with `Payment Gateway v2` selected.
- P10 Engineer (`qa+a.eng@edvensoft.com`) exists and holds exactly **one** role on
  `Payment Gateway v2` (`Eng`).

**Steps**
1. As P1, open the top-bar project selector and count how many times `Payment Gateway v2` appears.
2. On `/admin/roles`, click the `Rev` toggle on the `QA Alpha Engineer` row so the engineer now holds
   two roles on the same project. Wait for the save to settle.
3. Sign out and log in as `qa+a.eng@edvensoft.com` / `QaTest-2026!`.
4. Open the top-bar project selector and count the options.
5. Pick the second `Payment Gateway v2` option and note whether anything on screen changes.
6. Sign out, log back in as P1, and turn the engineer's `Rev` toggle back off.

**Expected**
- Each project the user can reach should appear in the selector **exactly once**, however many roles
  they hold on it.
- Actual behaviour today: at step 4 `Payment Gateway v2` is listed **twice** — one option per role
  grant — and step 5 changes nothing, because both options point at the same project.

**Pass / Fail**
- **Expect this case to fail today.**
- PASS only if the project appears exactly once for a user holding two roles on it.
- FAIL if the project is listed once per role grant — which is what the current build does.

**Test data**
- `qa+a.eng@edvensoft.com` holding both `engineer` and `reviewer` on `Payment Gateway v2`

**Notes**
- Raise once, **Medium** severity, against this case. It is not cosmetic: the duplicate options are
  indistinguishable, so a user cannot tell whether they picked the right one, and any case that says
  "switch the project selector back to `Payment Gateway v2`" (TS-03 TC-040 among them) becomes
  ambiguous. Do not re-raise it from those cases — reference this one.
- Step 6 is mandatory cleanup. Leaving the engineer with a reviewer role would break TC-030 and the
  gate-role assumptions in TS-09.

---

### TC-522 · An unknown /admin/* URL goes to Users & invitations

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | Negative |
| Priority | Low |
| Screen | `/admin/<anything>` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin.

**Steps**
1. Paste `http://localhost:5173/admin/billing` into the address bar and press Enter.
2. Read the address bar and the page heading.
3. Repeat with `http://localhost:5173/admin/does-not-exist`.
4. Repeat with `http://localhost:5173/admin` (nothing after it).
5. Click the browser Back button once.

**Expected**
- Steps 1, 3 and 4 each land on `/admin/users` — the address bar changes to `/admin/users` and the
  users screen (TC-023) renders.
- No developer placeholder is shown at any point: no `Foundation route mounted`, no `T2-T5`, no
  `Ready for screen implementation`, no `No screen built yet`.
- At step 5 Back does not return to the mistyped address — the redirect replaced it in history.

**Pass / Fail**
- PASS if every unknown or bare `/admin` address redirects to `/admin/users` with no placeholder copy.
- FAIL if any placeholder or internal build language renders, if the page is blank, or if you land
  anywhere other than `/admin/users`.

**Test data**
- `/admin/billing` · `/admin/does-not-exist` · `/admin`

**Notes**
- The destination is deliberately the admin landing page, not `/`: someone who mistyped an admin
  address stays inside admin. This replaces the earlier expectation of a redirect to `/`; the
  placeholder page was deleted.
- A non-admin still gets the `Admin access needed` panel (TC-034) for these addresses — the admin
  guard is checked first.

---

### TC-951 · Send invite says what happened to the email

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | Functional |
| Priority | High |
| Screen | `/admin/users` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Why this case exists.** The invite link only ever appeared in the server terminal and the admin
was told nothing (Bugs S.No 192). Invites now go out through SendGrid. Bugs S.No 355.

**Preconditions**
- Signed in as P1 Owner-Admin. An inbox you own.

**Steps**
1. **SendGrid off** (`SENDGRID_API_KEY` empty, backend restarted): send an invite.
2. **SendGrid on**: send an invite to your own inbox.
3. **Failure**: change one character of `SENDGRID_API_KEY`, restart the backend, send an invite.
   Then restore the key and restart.

**Expected**
- Step 1: blue `Invite created. The link is in the server terminal.`; the link is in
  `docker compose logs backend`.
- Step 2: green `Invite emailed to {address}`. The email `{your name} invited you to {workspace}`
  arrives with a **Join the workspace** button and `This invite works until {date}.` — a date, no
  `UTC`.
- Step 3: red `The invite was saved but the email couldn't be sent. Try Resend in a few minutes.`
  The invite **is** in the table. After restoring the key, **Resend** delivers it.

**Pass / Fail**
- **FAIL if a failed email loses the invite, or the screen claims an email was sent when it was
  not.**

**Notes**
- Outlook may mark the email `Unverified` until edvensoft.com is authenticated in SendGrid (a
  SendGrid setting, not the app).

---

### TC-952 · A second invite to someone already waiting is refused

| Field | Value |
|---|---|
| Suite | TS-02 Workspace Admin & Roles |
| Type | Negative |
| Priority | Medium |
| Screen | `/admin/users` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Why this case exists.** Two pending invites for one person were allowed; accepting the second then
failed with a server error. Bugs S.No 365.

**Steps**
1. Invite `qa+a.twice@edvensoft.com`.
2. Open **+ Invite** again and invite the same address (try `QA+A.Twice@edvensoft.com`).

**Expected**
- Step 2 stays in the drawer with, under `Work email`:
  `qa+a.twice@edvensoft.com already has an invite waiting. Use Resend on their row instead.`
- The table still holds one row for that address.

**Pass / Fail**
- **FAIL if a second pending row appears.**
