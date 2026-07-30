# TS-01 · Identity & Access

Everything a person does before they have a workspace to work in: creating one, logging into it,
getting locked out of it, resetting a password, joining by invitation, and the route guards that
decide where an authenticated (or anonymous) visitor lands. Owned by **Tester A**. No companion and
no phase runs are needed — every case here finishes in minutes.

**Run these in order.** TC-001 creates the workspace that every later case in this suite (and in
TS-02 and TS-03) logs into. TC-021 creates the P10 Engineer account that TS-02's permission cases
and TS-03's repository permission case depend on.

**Getting one-time links.** The dev stack uses Django's console email backend, so invitation and
password-reset emails are printed to the backend log rather than delivered. Where a case needs a
link, read it from `docker compose logs backend` and paste it into the browser. That is a *step*,
not an oracle — every Expected Result below is still something you see in the browser.

---

### TC-001 · Create a workspace and land on the setup checklist

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | E2E |
| Priority | Critical |
| Screen | `/signup` → `/setup` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Not logged in (use a private/incognito window).
- No account exists for your tester email yet.

**Steps**
1. Go to `http://localhost:5173/signup`.
2. Enter Full name `QA Alpha Owner`, Work email `qa+a.owner@edvensoft.com`, Password `QaTest-2026!`,
   Workspace / org name `QA Alpha`.
3. Click **Create workspace**.
4. On the confirmation screen, click **Continue**.

**Expected**
- After step 3 the page heading is `Workspace created` with the sub-line
  `Taking you to your setup checklist…`.
- After step 4 the browser is on `/setup` and the heading reads `Welcome to QA Alpha 👋`.
- The app shell renders with the sidebar visible — you are signed in as the new admin.

**Pass / Fail**
- PASS if the workspace is created, `Workspace created` is shown, and **Continue** lands on `/setup`
  with the workspace name in the welcome heading.
- FAIL if signup errors, the heading shows a placeholder name such as `Acme Corp`, or **Continue**
  goes anywhere other than `/setup`.

**Test data**
- Workspace `QA Alpha` · owner `qa+a.owner@edvensoft.com` · password `QaTest-2026!`

**Notes**
- Substitute your own tester row from the plan (§3) if you are Tester B or C.
- This account is the tenant admin for the whole cycle. Do not delete it.

---

### TC-002 · Signup rejects an email that already has an account

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Negative |
| Priority | High |
| Screen | `/signup` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-001 has passed, so `qa+a.owner@edvensoft.com` already exists.
- Not logged in (private/incognito window).

**Steps**
1. Go to `http://localhost:5173/signup`.
2. Enter Full name `QA Alpha Owner`, Work email `qa+a.owner@edvensoft.com`, Password `QaTest-2026!`,
   Workspace / org name `QA Alpha Again`.
3. Click **Create workspace**.

**Expected**
- No second workspace is created — the page stays on `Create your workspace`.
- An error appears under the Work email field. Check its three parts separately:
  the sentence `An account with this email already exists.`, then a link labelled `Log in instead`,
  then a full stop.
- The Work email input is marked invalid (red border / `aria-invalid`).
- Clicking `Log in instead` goes to `/login`.

**Pass / Fail**
- PASS if the duplicate is refused and all three parts of the error are present against the email
  field.
- FAIL if a workspace is created, the error is generic or points at another field, or a raw `409` /
  stack trace is shown.

**Test data**
- Email: `qa+a.owner@edvensoft.com` (already registered)

**Notes**
- The error is assembled from text plus a React link, not from one string. Do not fail the case over
  where the space or the full stop sits relative to the link — judge the three parts above.
- The backend answers this with HTTP 409; the tester should never see the status code itself.
- This 409 is the **only** signup rejection the screen renders anything for. Every other rejection
  (short password, blank name, blank workspace name) is silent — see TC-003, TC-004 and TC-501.

---

### TC-003 · Signup rejects a password under 8 characters

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Negative |
| Priority | High |
| Screen | `/signup` |
| Persona | Any |
| Automation | Yes |

**Preconditions**
- Not logged in (private/incognito window).

**Steps**
1. Go to `http://localhost:5173/signup`.
2. Enter Full name `QA Tester`, Work email `qa+short@edvensoft.com`, Password `Short1`,
   Workspace / org name `Short Pass Co`.
3. Click **Create workspace**.

**Expected**
- No workspace is created — the heading is still `Create your workspace` and the browser never
  reaches `Workspace created`.
- Nothing at all is shown to the user: no error against the Password field, no banner, no spinner
  left running. The form is left exactly as it was and the button appears to have done nothing.
- Nothing is logged you can see in the browser — no raw `400`, no stack trace, no blank screen.

**Pass / Fail**
- PASS if the 6-character password is refused, no workspace is created, and the app stays on an
  intact `Create your workspace` form.
- FAIL if the workspace **is** created with a 6-character password, or the app shows a raw 400 /
  an unhandled error / a blank screen.

**Test data**
- Password: `Short1` (6 characters)

**Notes**
- **The silence is the current behaviour, not a pass criterion in itself.** Signup renders a field
  error for exactly one case — an email that is already registered (409). Every other rejection,
  including this one, is swallowed. That silent-400 defect is already tracked (it also affects
  TC-004, TC-501, and the accept-invite/reset forms in TC-502 and TC-504) — **do not raise it again
  here**; this case only proves the weak password is refused.
- The backend enforces a minimum length of 8 only. Django's stronger validators are configured but
  never invoked, so a weak-but-long password such as `password1` is expected to be accepted today.
  That is tracked separately too.

---

### TC-004 · Signup with a blank workspace name

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Negative |
| Priority | Medium |
| Screen | `/signup` |
| Persona | Any |
| Automation | Yes |

**Preconditions**
- Not logged in (private/incognito window).

**Steps**
1. Go to `http://localhost:5173/signup`.
2. Enter Full name `QA Tester`, Work email `qa+noorg@edvensoft.com`, Password `QaTest-2026!`.
3. Leave `Workspace / org name` empty.
4. Click **Create workspace**.

**Expected**
- No workspace is created — the heading is still `Create your workspace`.
- The failure is communicated on the form (an error against `Workspace / org name`, or the button
  does nothing visible); the app does not navigate to `Workspace created`.
- The app does not render a blank/unnamed workspace anywhere.

**Pass / Fail**
- PASS if the submission is blocked and the user stays on the signup form.
- FAIL if a workspace with an empty name is created, or the app crashes / shows a raw API error.

**Test data**
- Workspace / org name: *(empty)*

**Notes**
- The screen has no client-side required-field marking on this input, so the rejection comes from
  the API. If nothing at all is shown to the user, log it as a Medium defect (silent failure) — the
  case still fails.

---

### TC-005 · Signup rejects a malformed email address

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Negative |
| Priority | Medium |
| Screen | `/signup` |
| Persona | Any |
| Automation | Yes |

**Preconditions**
- Not logged in (private/incognito window).

**Steps**
1. Go to `http://localhost:5173/signup`.
2. Enter Full name `QA Tester`, Work email `qa-at-edvensoft`, Password `QaTest-2026!`,
   Workspace / org name `Bad Email Co`.
3. Click **Create workspace**.

**Expected**
- No workspace is created and the heading is still `Create your workspace`.
- The Work email field is flagged — the browser's own validation bubble on the `email` input, or an
  inline error against the field.

**Pass / Fail**
- PASS if the submission is blocked and the email field is the thing flagged.
- FAIL if the malformed address is accepted, or the error points at an unrelated field.

**Test data**
- Work email: `qa-at-edvensoft` (no `@`, no domain)

**Notes**
- Also try `qa@` and `qa@edvensoft` — record any that slip through in the same defect row.

---

### TC-006 · The password strength meter responds as you type

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | UX |
| Priority | Low |
| Screen | `/signup` |
| Persona | Any |
| Automation | No |

**Preconditions**
- Not logged in (private/incognito window).

**Steps**
1. Go to `http://localhost:5173/signup`.
2. Click into the Password field and type `abc`.
3. Extend it to `abcdefgh`.
4. Extend it to `QaTest-2026!`.

**Expected**
- Before you type, the strength meter under the Password field is at its lowest — no bars filled.
- With `abc` the meter is **still at its lowest** — visually identical to the empty field.
- With `abcdefgh` exactly one bar is filled.
- With `QaTest-2026!` the meter is full (all bars filled).
- The meter never goes backwards as you extend the password.
- Once any character is typed, the help line under the field reads
  `Strong — add a symbol to max it out.`

**Pass / Fail**
- PASS if the meter is at its lowest for both empty and `abc`, one bar at `abcdefgh`, full at
  `QaTest-2026!`, and never decreases.
- FAIL if the meter never changes between `abcdefgh` and `QaTest-2026!`, goes backwards, or is
  missing entirely.

**Test data**
- `abc` (scores 0) · `abcdefgh` (scores 1) · `QaTest-2026!` (scores 4)

**Notes**
- **`abc` scoring zero is correct, not a bug.** The meter scores four things only: length ≥ 8,
  length ≥ 12, mixed upper/lower case, a digit, a symbol. A short all-lowercase password earns
  none of them, so it is indistinguishable from an empty field. Do not raise that.
- The help line is static copy — it says `Strong…` for *any* non-empty password, including `abc`,
  which is a direct contradiction of the meter showing zero. That mismatch is a known copy defect;
  note it against this case rather than raising a second one.

---

### TC-007 · Signup shows a submitting state while the workspace is created

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | UX |
| Priority | Medium |
| Screen | `/signup` |
| Persona | Any |
| Automation | No |

**Preconditions**
- Not logged in (private/incognito window).
- Optional but recommended: throttle the network to "Slow 3G" in DevTools so the state is visible.

**Steps**
1. Go to `http://localhost:5173/signup`.
2. Fill in Full name `QA Submit`, Work email `qa+submit@edvensoft.com`, Password `QaTest-2026!`,
   Workspace / org name `QA Submit Co`.
3. Click **Create workspace** and watch the card without clicking again.

**Expected**
- The card switches to a submitting state: the sub-line reads `Setting up QA Submit Co…` and the
  button shows a spinner with the label `Creating workspace…`.
- The button is disabled while submitting — a second click does nothing.
- The state resolves to `Workspace created`.

**Pass / Fail**
- PASS if the submitting state is shown with that copy and the button cannot be double-submitted.
- FAIL if the button stays clickable, or two workspaces are created from a double click.

**Test data**
- Workspace: `QA Submit Co`

**Notes**
- Delete nothing afterwards — an extra throwaway workspace is harmless and isolated by tenant.

---

### TC-008 · Log in with valid credentials

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Functional |
| Priority | Critical |
| Screen | `/login` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-001 has passed.
- Not logged in — if you are, open the avatar menu and click **Sign out** first.

**Steps**
1. Go to `http://localhost:5173/login`.
2. Enter Work email `qa+a.owner@edvensoft.com` and Password `QaTest-2026!`.
3. Click **Log in**.

**Expected**
- The browser lands on `/` and the dashboard renders inside the app shell.
- The sidebar is visible, and the top-bar avatar shows the signed-in user's initials.
- No error banner is present.

**Pass / Fail**
- PASS if login succeeds and the dashboard renders.
- FAIL if login is refused with correct credentials, or the app lands on a blank/erroring screen.

**Test data**
- `qa+a.owner@edvensoft.com` / `QaTest-2026!`

**Notes**
- The session is a server-side cookie session — closing the tab and reopening
  `http://localhost:5173` should keep you signed in.

---

### TC-009 · Log in with the wrong password

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Negative |
| Priority | High |
| Screen | `/login` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Not logged in.

**Steps**
1. Go to `http://localhost:5173/login`.
2. Enter Work email `qa+a.owner@edvensoft.com` and Password `WrongPassword1`.
3. Click **Log in**.

**Expected**
- You stay on `/login` — the heading is still `Log in`.
- A red banner reads `Email or password is incorrect.`
- The Password field shows the inline error `Incorrect password.`

**Pass / Fail**
- PASS if the login is refused with exactly that banner and field error.
- FAIL if login succeeds, or the error text differs, or the app shows a raw 401.

**Test data**
- Password: `WrongPassword1`

**Notes**
- Keep the failure count low here — TC-011 needs a clean run of consecutive failures.

---

### TC-010 · Log in with an email that has no account

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Negative |
| Priority | Medium |
| Screen | `/login` |
| Persona | Any |
| Automation | Yes |

**Preconditions**
- Not logged in.
- `qa+nobody@edvensoft.com` has never signed up or been invited.

**Steps**
1. Go to `http://localhost:5173/login`.
2. Enter Work email `qa+nobody@edvensoft.com` and Password `QaTest-2026!`.
3. Click **Log in**.

**Expected**
- You stay on `/login`.
- The banner reads `Email or password is incorrect.` — the same message as a wrong password, with
  nothing that reveals whether the account exists.

**Pass / Fail**
- PASS if the message is identical to the wrong-password message (no account enumeration).
- FAIL if the app says the account does not exist, or distinguishes the two cases in any way.

**Test data**
- `qa+nobody@edvensoft.com` / `QaTest-2026!`

**Notes**
- Not leaking account existence is deliberate. If the copy ever differs between TC-009 and TC-010,
  raise it as a Medium security-hygiene defect.

---

### TC-011 · Repeated failed logins lock the account

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Negative |
| Priority | High |
| Screen | `/login` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Not logged in.
- Use a throwaway account (`qa+submit@edvensoft.com` from TC-007) so you do not lock the admin out.

**Steps**
1. Go to `http://localhost:5173/login`.
2. Enter Work email `qa+submit@edvensoft.com` and Password `WrongPassword1`, click **Log in**.
3. Repeat step 2 ten times in a row without pausing.
4. Attempt an eleventh login, this time with the *correct* password `QaTest-2026!`.

**Expected**
- At some point during step 3 the card switches to the locked state: a warning banner titled
  `Too many attempts` with the body
  `Your account is locked for 15 minutes. Reset your password to regain access sooner.`
- A **Reset password** button is shown; clicking it goes to `/reset`.
- The correct-password attempt in step 4 is also refused while the lock is in force.

**Pass / Fail**
- PASS if the locked banner appears and the correct password is refused while locked.
- FAIL if unlimited failed attempts are accepted and the locked state never appears.

**Test data**
- `qa+submit@edvensoft.com` · wrong password `WrongPassword1` · correct password `QaTest-2026!`

**Notes**
- **Expect this to fail today.** The locked view renders only on an HTTP 429, and the login endpoint
  has no throttling or lockout — it returns 401 on every failed attempt, forever. Raise it **once**
  as a single Medium defect ("no login rate limiting / lockout is implemented") and do not
  re-raise it from any other case.

---

### TC-012 · Login shows a submitting state

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | UX |
| Priority | Low |
| Screen | `/login` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Not logged in. Throttle the network to "Slow 3G" in DevTools so the state is visible.

**Steps**
1. Go to `http://localhost:5173/login`.
2. Enter valid credentials for `qa+a.owner@edvensoft.com`.
3. Click **Log in** once and watch the card.

**Expected**
- The card switches to the submitting state: sub-line `Signing you in…` and a disabled button
  showing a spinner with the label `Logging in…`.
- The form fields are no longer shown while submitting.
- The state resolves to the dashboard.

**Pass / Fail**
- PASS if the submitting state renders with that copy and the button is disabled.
- FAIL if the button stays live and can be clicked repeatedly.

**Test data**
- `qa+a.owner@edvensoft.com` / `QaTest-2026!`

**Notes**
- Remember to remove the DevTools throttle before continuing.

---

### TC-013 · Login returns you to the page you originally asked for

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Functional |
| Priority | High |
| Screen | `/login` → `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Not logged in (open the avatar menu and click **Sign out** if you are).

**Steps**
1. With no session, paste `http://localhost:5173/work-items` into the address bar.
2. Confirm you are bounced to the `Log in` screen.
3. Enter `qa+a.owner@edvensoft.com` / `QaTest-2026!` and click **Log in**.

**Expected**
- After login the browser is on `/work-items`, not `/`.
- The work items screen renders inside the app shell.
- Pressing the browser Back button does not return you to the login screen (the redirect replaces
  history).

**Pass / Fail**
- PASS if you land back on `/work-items` after authenticating.
- FAIL if you land on the dashboard and the requested destination is lost.

**Test data**
- Deep-link target: `/work-items`

**Notes**
- Try `/gates` as a second target if `/work-items` passes; report both in one row.

---

### TC-014 · Sign out from the avatar menu

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Functional |
| Priority | High |
| Screen | app shell → `/login` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin.

**Steps**
1. Click the circular avatar (initials) at the right of the top bar.
2. Confirm the menu shows your name and email.
3. Click **Sign out**.
4. After the redirect, paste `http://localhost:5173/work-items` into the address bar.

**Expected**
- The menu opens with the account name and email at the top and a **Sign out** item below a
  separator.
- After step 3 the browser is on `/login` showing the heading `Log in`.
- Step 4 does not reach the work items screen — you are returned to `Log in`.

**Pass / Fail**
- PASS if the menu opens, sign-out redirects to `/login`, and the session is genuinely gone.
- FAIL if the menu will not open, or a protected route still renders after signing out.

**Test data**
- *(none)*

**Notes**
- Pressing `Escape` or clicking outside should close the menu without signing out — check that too.

---

### TC-015 · An anonymous visitor cannot reach a protected route

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Permission |
| Priority | Critical |
| Screen | `/work-items` → `/login` |
| Persona | Any |
| Automation | Yes |

**Preconditions**
- A fresh private/incognito window that has never signed in.

**Steps**
1. Paste `http://localhost:5173/work-items` into the address bar and press Enter.
2. Wait for the page to settle.

**Expected**
- The browser ends on `/login` with the heading `Log in`.
- No work item data, sidebar counts, or project names are visible at any point.
- A brief `Loading workspace` panel while the session is checked is acceptable; it must not leak
  any workspace content.

**Pass / Fail**
- PASS if the anonymous visitor is redirected to `/login` and sees no workspace data.
- FAIL if the protected screen renders, even briefly with real data.

**Test data**
- Route: `/work-items`

**Notes**
- Reach this state by using a fresh incognito window, not by clearing localStorage — the session is
  a server cookie.

---

### TC-016 · A signed-in user visiting /login is sent to the dashboard

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Functional |
| Priority | Medium |
| Screen | `/login` → `/` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 Owner-Admin.

**Steps**
1. Paste `http://localhost:5173/login` into the address bar and press Enter.
2. Repeat with `http://localhost:5173/signup`.

**Expected**
- Both URLs **settle** on `/` with the dashboard rendered inside the app shell.
- Neither the `Log in` nor the `Create your workspace` card is still on screen once the page has
  settled, and neither form can be submitted.
- A brief flash of the auth card while the session is being re-checked is expected on a hard reload
  and is **not** a failure — see the Notes.

**Pass / Fail**
- PASS if both routes end on the dashboard and the auth form is gone once the page has settled.
- FAIL if either route *stays* on the auth form while a session is active, or the form stays
  interactive.

**Test data**
- Routes: `/login`, `/signup`

**Notes**
- **Judge the settled state, not the first frame.** The redirect guard does not wait for the session
  check to finish, so on a hard reload the auth card renders for a moment before the redirect fires.
  That flash is a known defect and is tracked separately — confirm it and move on; do **not** raise
  it, and do not fail the case on it.
- `/reset` and `/accept-invite` sit behind the same guard and behave differently enough to need
  their own case — see TC-503.

---

### TC-017 · Request a password reset

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Functional |
| Priority | High |
| Screen | `/reset` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Not logged in (private/incognito window).

**Steps**
1. Go to `http://localhost:5173/reset`.
2. Confirm the heading reads `Forgot your password?`.
3. Clear the Work email field and type `qa+a.owner@edvensoft.com`.
4. Click **Send reset link**.

**Expected**
- The card switches to the confirmation state with the heading `Check your email`.
- The body names the address you entered and states the link expires in 1 hour.
- A **Back to log in** button is shown and returns you to `/login`.

**Pass / Fail**
- PASS if `Check your email` is shown naming the address you typed.
- FAIL if the screen stays on the request form, errors, or names a different address.

**Test data**
- `qa+a.owner@edvensoft.com`

**Notes**
- The same confirmation is shown for an unknown address (no account enumeration) — that is
  intentional, not a defect.
- The reset link is printed to the backend log (`docker compose logs backend`); TC-018 uses it.

---

### TC-018 · Set a new password from a reset link and log in with it

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | E2E |
| Priority | High |
| Screen | `/reset?token=…` → `/login` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-017 has passed within the last hour, and you can read the reset link from
  `docker compose logs backend`.
- Not logged in.

**Steps**
1. Copy the `/reset?token=…` link from the backend log and open it in the browser.
2. Confirm the heading reads `Set a new password`.
3. Enter New password `QaTest-2026-New!` and Confirm password `QaTest-2026-New!`.
4. Click **Update password**.
5. Click **Log in** on the confirmation screen and sign in with the new password.
6. Sign out. Re-open the **same** `/reset?token=…` link in a private window, enter
   `QaTest-2026-New!` in both password fields, and click **Update password** again.

**Expected**
- After step 4 the heading reads `Password updated` with the sub-line
  `You can now log in with your new password.`
- Step 5 signs you in and the dashboard renders.
- In step 6 the link re-opens on the `Set a new password` **form** — that is expected. Only after
  you submit it does the card switch to `This reset link is invalid`, proving the token was consumed.

**Pass / Fail**
- PASS if the password changes, the new one works, and the second submit of the same token is
  refused with `This reset link is invalid`.
- FAIL if the update errors, the old password still works, or the second submit succeeds and
  changes the password again.

**Test data**
- New password: `QaTest-2026-New!`

**Notes**
- **The reset screen never validates the token on load.** With any `token` in the URL it renders the
  form; the invalid card only appears after a rejected submit. So "re-opening the link shows the
  invalid card" is not a valid oracle — you have to submit, which is why step 6 does.
- **Change the password back** afterwards (repeat TC-017/TC-018 with `QaTest-2026!`) so the rest of
  the pack's test data stays valid.
- The Confirm password field is not compared against the first field in the current build. If a
  mismatched confirmation is accepted, log it once as a Medium defect against this case.

---

### TC-019 · An invalid or expired reset link shows the invalid state

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Negative |
| Priority | Medium |
| Screen | `/reset?token=…` |
| Persona | Any |
| Automation | Yes |

**Preconditions**
- Not logged in (private/incognito window).

**Steps**
1. Go to `http://localhost:5173/reset?token=not-a-real-token`.
2. Enter New password `QaTest-2026!` and Confirm password `QaTest-2026!`.
3. Click **Update password**.
4. Click **Request a new link**.

**Expected**
- After step 3 the card shows the heading `This reset link is invalid` with the body
  `It may have expired or already been used. Request a fresh link to continue.`
- No password is changed anywhere.
- After step 4 nothing happens — the screen does not navigate and no new link is sent.

**Pass / Fail**
- PASS if the invalid state renders with that exact copy.
- FAIL if the app errors, shows a raw 410, or claims the password was updated.

**Test data**
- Token: `not-a-real-token`

**Notes**
- **`Request a new link` is a known inert control** — it has no click handler. It is on the plan's
  known-inert list (§10). Confirm it does nothing and do **not** raise a new defect.

---

### TC-020 · The reset form is prefilled with a hardcoded sample address

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | UX |
| Priority | Medium |
| Screen | `/reset` |
| Persona | Any |
| Automation | Yes |

**Preconditions**
- Not logged in (private/incognito window), with no prior visit to `/reset` in this window.

**Steps**
1. Go to `http://localhost:5173/reset`.
2. Read the value in the Work email field without typing anything.
3. Click **Send reset link** without editing the field.

4. Open a reset link from TC-017 (`/reset?token=…`) and read the sub-line under
   `Set a new password` without typing anything.

**Expected**
- The Work email field should be **empty** on first load — it must not contain an unrelated third
  party's address.
- The `Set a new password` sub-line should name the account the link belongs to, not a sample.

**Pass / Fail**
- **Expect this case to fail today.** The current build ships leftover design-mock data on a live
  screen.
- PASS only if the field is empty on first load and the sub-line names a real address.
- FAIL if the field contains `sarah@acme.com`, or the sub-line reads
  `Choose a strong password for sarah@acme.com`.

**Test data**
- Prefilled value: `sarah@acme.com`

**Notes**
- **Record what you actually see at each step** — that is the evidence for the defect:
  step 2 the field reads `sarah@acme.com`; step 3 the confirmation card reads `Check your email`
  naming `sarah@acme.com`; step 4 the sub-line reads `Choose a strong password for sarah@acme.com`.
- Raise this **once**, Medium severity, against this case, covering all three symptoms in one row —
  a user who does not notice the prefill sends a reset request for a stranger's address and is then
  shown that stranger's email. Do not open a second defect for the sub-line.
- Do not raise it again from TC-017 or TC-018, which both walk past the same prefill.

---

### TC-021 · Join a workspace from an invitation link

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | E2E |
| Priority | Critical |
| Screen | `/accept-invite?token=…` → `/` |
| Persona | P10 Engineer |
| Automation | No |

**Preconditions**
- TS-02 TC-024 has been run, so a pending invitation exists for `qa+a.eng@edvensoft.com` with an
  `engineer` grant on `Payment Gateway v2`.
- You can read the invite link from `docker compose logs backend`.
- Use a second browser / private window so the admin session stays signed in.

**Steps**
1. Copy the `/accept-invite?token=…` link from the backend log and open it in the private window.
2. Confirm the heading reads `Join QA Alpha` and the sub-line names the inviter and the granted role
   on `Payment Gateway v2`.
3. Check the `Email` field.
4. Enter Your name `QA Alpha Engineer` and Set a password `QaTest-2026!`.
5. Click **Join workspace**.

**Expected**
- The heading is `Join QA Alpha` (your workspace name, not `Acme Corp`).
- The `Email` field shows `qa+a.eng@edvensoft.com` and is **disabled** — it cannot be edited.
- After step 5 the browser lands on `/` and the dashboard renders as the newly-joined user; the
  avatar menu shows `qa+a.eng@edvensoft.com`.

**Pass / Fail**
- PASS if the account is created, the email field was locked, and the user lands signed in on `/`.
- FAIL if the heading shows placeholder copy (`Join Acme Corp` / `Sarah Chen` / `raj@acme.com`), the
  email is editable, or joining errors.

**Test data**
- `qa+a.eng@edvensoft.com` / `QaTest-2026!` — this becomes **P10 Engineer** for the rest of the pack.

**Notes**
- P10 is the negative persona used by TS-02's permission cases and TS-03 TC-053. Do not delete it.
- Placeholder values (`Acme Corp`, `Sarah Chen`, `raj@acme.com`) belong to the design gallery only;
  seeing any of them on the live route is a defect.

---

### TC-022 · An expired or already-used invite link shows the expired state

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Negative |
| Priority | Medium |
| Screen | `/accept-invite?token=…` |
| Persona | Any |
| Automation | Yes |

**Preconditions**
- TC-021 has passed, so its invitation token has been consumed.
- A fresh private/incognito window (not signed in).

**Steps**
1. Re-open the invite link consumed in TC-021.
2. Read the card.
3. Click **Request a new invite**.
4. Now open `http://localhost:5173/accept-invite` with no `token` at all.

**Expected**
- Steps 1–2 show the heading `This invite link has expired` with the body
  `Invitation links are valid for 7 days, or expire once used. Ask your admin to resend it.`
- Step 3 does nothing — no navigation, no confirmation, no new invitation.
- Step 4 shows the same expired card rather than an empty or broken form.

**Pass / Fail**
- PASS if a used token and a missing token both land on the expired card with that exact copy.
- FAIL if the form renders and a second account can be created from a used link.

**Test data**
- The consumed token from TC-021 · and a bare `/accept-invite` URL

**Notes**
- **`Request a new invite` is a known inert control** — no click handler, listed in the plan's
  known-inert list (§10). Confirm and move on; do not raise a new defect.
- Invitations are single-use and expire after 7 days; a revoked invitation behaves the same way.

---

### TC-501 · Signup with a blank full name is refused silently

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Negative |
| Priority | Medium |
| Screen | `/signup` |
| Persona | Any |
| Automation | Yes |

**Preconditions**
- Not logged in (private/incognito window).

**Steps**
1. Go to `http://localhost:5173/signup`.
2. Leave `Full name` empty.
3. Enter Work email `qa+noname@edvensoft.com`, Password `QaTest-2026!`, Workspace / org name
   `QA No Name Co`.
4. Click **Create workspace**.
5. Open `http://localhost:5173/login` and try to log in as `qa+noname@edvensoft.com` /
   `QaTest-2026!`.

**Expected**
- After step 4 the heading is still `Create your workspace` — the browser never reaches
  `Workspace created`.
- Nothing is shown to the user: no error against `Full name`, no banner, no navigation.
- Step 5 is refused with `Email or password is incorrect.` — confirming no account was created.

**Pass / Fail**
- PASS if no account and no workspace are created, and the user is left on an intact signup form.
- FAIL if a workspace is created with a blank owner name, or the app shows a raw 400 / a blank
  screen.

**Test data**
- Full name: *(empty)* · `qa+noname@edvensoft.com`

**Notes**
- Step 5 is the oracle. Without it there is nothing on screen that distinguishes "refused" from
  "the button is broken", because the form renders no error for this rejection.
- The silent rejection is the same tracked defect described in TC-003's Notes. Confirm it here;
  do **not** raise a second defect for it.

---

### TC-502 · A short password on the invitation form is refused silently

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Negative |
| Priority | Medium |
| Screen | `/accept-invite?token=…` |
| Persona | P10 Engineer |
| Automation | No |

**Preconditions**
- A **fresh, unused** invitation exists. Create one from `/admin/users` for
  `qa+a.shortpw@edvensoft.com` using TS-02 TC-024's steps, and read its link from
  `docker compose logs backend`.
- A private/incognito window, not signed in.

**Steps**
1. Open the `/accept-invite?token=…` link in the private window and confirm the `Join {workspace}`
   form renders.
2. Enter Your name `QA Short Pass` and Set a password `Short1`.
3. Click **Join workspace**.
4. Read the card.
5. Correct the password to `QaTest-2026!` and click **Join workspace** again.

**Expected**
- After step 3 you stay on the `Join {workspace}` form. The `Email` field is still filled and
  disabled and the form is otherwise untouched.
- Nothing is shown to the user: no error against `Set a password`, no banner, and **not** the
  `This invite link has expired` card.
- Step 5 succeeds — the account is created and the browser lands on `/` — proving the token was not
  consumed or invalidated by the failed attempt.

**Pass / Fail**
- PASS if the 6-character password is refused, the token survives, and the corrected password then
  works.
- FAIL if the account is created with a 6-character password, or the failed attempt burns the token
  and step 5 lands on `This invite link has expired`.

**Test data**
- `qa+a.shortpw@edvensoft.com` · rejected `Short1` · accepted `QaTest-2026!`

**Notes**
- The accept-invite screen only renders its error card for a used/expired invitation (409/410).
  A 400 — which is what a short password produces — is swallowed entirely. That is the same tracked
  silent-400 defect as TC-003; confirm it, do not raise it again.
- The account created in step 5 is throwaway. Leave it; it is isolated inside your workspace and
  does not disturb P10 Engineer from TC-021.

---

### TC-504 · A short password on the reset form is refused silently

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Negative |
| Priority | Medium |
| Screen | `/reset?token=…` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A **fresh, unused** reset link for `qa+submit@edvensoft.com` (the throwaway account from TC-007):
  run TC-017's steps for that address and read the link from `docker compose logs backend`.
- Not logged in (private/incognito window).

**Steps**
1. Open the `/reset?token=…` link and confirm the heading reads `Set a new password`.
2. Enter New password `Short1` and Confirm password `Short1`.
3. Click **Update password**.
4. Read the card.
5. Change both fields to `QaTest-2026!` and click **Update password** again.

**Expected**
- After step 3 you stay on the `Set a new password` form with both fields intact.
- Nothing is shown to the user: no error against `New password`, no banner, and **not** the
  `This reset link is invalid` card.
- Step 5 succeeds and the heading becomes `Password updated` — the token was not consumed by the
  rejected attempt.

**Pass / Fail**
- PASS if the 6-character password is refused, the token survives, and the corrected password then
  updates successfully.
- FAIL if the password is changed to `Short1`, or the failed attempt invalidates the token so
  step 5 shows `This reset link is invalid`.

**Test data**
- Account `qa+submit@edvensoft.com` · rejected `Short1` · accepted `QaTest-2026!`

**Notes**
- Use the throwaway account, not the admin — this case deliberately changes a password.
- The reset screen renders its error card only for a 410 (used/expired token). A 400 from a short
  password shows nothing at all — the same tracked silent-400 defect as TC-003. Confirm, do not
  re-raise.

---

### TC-503 · A signed-in user opening an invite or reset link is bounced with no explanation

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | UX |
| Priority | Medium |
| Screen | `/accept-invite?token=…` · `/reset?token=…` → `/` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Signed in as P1 Owner-Admin in your normal browser window.
- You have a valid, unused invitation link and a valid, unused reset link to hand (from TC-024 and
  TC-017). A stale link works too — the guard fires before the token is ever looked at.

**Steps**
1. While signed in, paste the `/accept-invite?token=…` link into the address bar and press Enter.
2. Note where you end up and what, if anything, the app tells you.
3. Repeat with the `/reset?token=…` link.
4. Confirm you are still signed in as P1 Owner-Admin (check the avatar menu).

**Expected**
- Both links land on `/` with the dashboard rendered. Neither the `Join {workspace}` form nor the
  `Set a new password` form is shown.
- **No message of any kind is shown** — no banner, no toast, no explanation that the link was
  ignored because you are already signed in. The user is simply dropped on the dashboard.
- The existing session is untouched: you are still P1 Owner-Admin, and the invitation/reset token is
  **not** consumed (a private window can still open the same link and use it).

**Pass / Fail**
- PASS if both links redirect to `/`, the session is untouched, and the token is still usable in a
  private window.
- FAIL if the app signs you out, consumes the token, renders the invite/reset form over an active
  session, or errors.

**Test data**
- One unused invite link · one unused reset link

**Notes**
- The silent bounce is the point of this case: someone forwarded an invite to a colleague who is
  already a member, or clicked their own reset link in a logged-in tab, and the product says nothing.
  Raise it once as a **Low** UX defect against this case.
- Verify the token survived by opening the same link in a private window afterwards — that is the
  only browser-visible proof, and it matters because a consumed token would make this High, not Low.
- Do not confuse this with TC-016, which covers `/login` and `/signup` behind the same guard.
