# TS-04 · Integrations

Covers the capability grid at `/integrations` and the connect form at `/integrations/:capability`:
that all five connectable capabilities render, that a vendor can be bound to a capability, that the vendor
choice drives the form, that secrets are genuinely write-only, and that a connection test reports
success and failure honestly. **Owner: Tester B**, working as **P1 Owner-Admin** in workspace
`QA Bravo`. No companion and no phase run is needed for this suite.

> **Run these in order.** TC-056 assumes a workspace with nothing connected yet; TC-058 creates the
> Documentation store connection that TC-059 to TC-062 and TC-066 all reuse; TC-062 deliberately
> leaves that connection in a failed state, which TC-063 then reads. Skipping around will give you
> a grid that does not match the preconditions.

> **One thing to know before you start:** `POST .../test-connection/` always returns HTTP 200 with a
> body of `{ok, detail, fix_hint}`. A failed test is *never* an HTTP error, so the app must always
> render a banner and must never show a crash, a blank card, or a raw error page. If you ever see
> the app break on a failed test, that is a defect regardless of what the case's Expected says.

---

### TC-056 · The capability grid renders all five capability cards in order

| Field | Value |
|---|---|
| Suite | TS-04 Integrations |
| Type | UX |
| Priority | High |
| Screen | `/integrations` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 in workspace `QA Bravo`.
- Nothing has been connected yet in this workspace, and no connection is in a failed state.

**Steps**
1. Click **Integrations** in the sidebar's setup section (or go to `http://localhost:5173/integrations`).
2. Read the page heading and sub-heading.
3. Read the cards top-left to bottom-right, in DOM order.

**Expected**
- The h1 reads `Integrations`.
- The sub-heading reads `Capabilities, not vendors — connect a vendor as the current binding for each capability. Phases use whatever is connected.`
- Exactly five cards render, in this order: `Documentation store`, `Task tracker`, `Design source`,
  `Code host`, `Test management`.
- All five cards show the badge `Not connected` and a link labelled `Connect`.
- There is **no** `Code intelligence` card.

**Pass / Fail**
- PASS if exactly five cards render in the listed order, each `Not connected` with a `Connect` link.
- FAIL if a card is missing, the order differs, a capability name is wrong, a `Code intelligence`
  card appears, or a card that was never connected shows `Connected`.

**Test data**
- None.

**Notes**
- The grid collapses to a single card as soon as any connection is failed (see TC-063). That is why
  this case must run before TC-062.
- Code intelligence is no longer something you connect: it is set up automatically for every
  workspace, so it has no card. Its old address is covered by TC-064.

---

### TC-057 · Choosing a vendor reveals that vendor's binding and secret fields

| Field | Value |
|---|---|
| Suite | TS-04 Integrations |
| Type | Functional |
| Priority | High |
| Screen | `/integrations/:capability` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-056 passed. Documentation store is still `Not connected`.

**Steps**
1. On `/integrations`, click **Connect** on the `Documentation store` card.
2. Read the heading, sub-heading and the `Vendor` field before touching it.
3. Open the `Vendor` select and choose `Confluence`.
4. Read the fields that appear below the select.

**Expected**
- The h1 reads `Connect a capability` and the sub-heading includes
  `Secrets are write-only — stored securely, never shown again.`
- Before a vendor is chosen, the `Vendor` select shows `Choose a vendor…` and **no** binding or
  secret fields are rendered.
- After choosing `Confluence`, three binding fields appear — `Space key`, `Base URL` and
  `Atlassian account email` — plus one secret field, `API token`, rendered as a masked password
  input.
- The footer shows the buttons **Test connection** and **Save**.

**Pass / Fail**
- PASS if the form is empty until a vendor is chosen and then renders exactly those four fields.
- FAIL if fields render before a vendor is chosen, if a field is missing or misnamed, or if the
  `API token` value is visible as plain text while typing.

**Test data**
- Vendor: `Confluence`

**Notes**
- Each capability currently offers exactly one vendor (docstore→Confluence, tasktracker→Jira,
  designsource→Figma, codehost→GitHub, testmgmt→Xray). A single-option dropdown is expected today,
  not a defect.

---

### TC-058 · Connect the Documentation store capability (happy path)

| Field | Value |
|---|---|
| Suite | TS-04 Integrations |
| Type | Functional |
| Priority | Critical |
| Screen | `/integrations/docstore` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-057 passed and you are still on the Documentation store connect form.
- You have a real Atlassian account, its site URL, and a current API token.

**Steps**
1. With `Confluence` selected, enter Space key `PAY`, Base URL `https://<your-site>.atlassian.net/wiki`,
   and Atlassian account email `<your Atlassian email>`.
2. Paste your API token into `API token`.
3. Click **Save**.
4. Click **Back to integrations**.

**Expected**
- The **Save** button becomes enabled only once the vendor, all required binding fields and the
  secret are filled.
- After saving, a green banner titled `Saved` appears reading `Confluence saved. Test the connection to verify it.`
- On `/integrations`, the `Documentation store` card now shows vendor `Confluence` and the badge
  `Connected`, and its link now reads `Manage`.

**Pass / Fail**
- PASS if the save succeeds, the `Saved` banner appears, and the grid card flips to
  `Connected` / `Manage` with vendor `Confluence`.
- FAIL if Save is enabled with required fields blank, if the banner is absent or reads
  `Couldn’t save`, or if the grid card still says `Not connected` after a reload.

**Test data**
- Space key: `PAY`
- Base URL: your Atlassian wiki URL
- API token: yours — do **not** paste it into a defect report

**Notes**
- Saving does not test the credential. A card can read `Connected` on a bad token until someone runs
  a connection test — that is by design (TC-061/TC-062 cover the test).

---

### TC-059 · A stored secret is never echoed back to the browser

| Field | Value |
|---|---|
| Suite | TS-04 Integrations |
| Type | Functional |
| Priority | Critical |
| Screen | `/integrations/docstore` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-058 passed — Documentation store is connected with a stored API token.

**Steps**
1. Go to `/integrations` and click **Manage** on the `Documentation store` card.
2. Look at the `API token` row.
3. Click into the input on that row and try to type.
4. Reload the page (F5) and look at the `API token` row again.

**Expected**
- The `API token` row shows a **disabled** password input, a badge reading `Configured ✓`, and a
  button labelled **Replace**.
- The help text under the field reads `Stored securely. Enter a new value only to rotate it.`
- The disabled input cannot be typed into, and its content is masked — the real token is not shown
  anywhere on the page in any form.
- After the reload the row renders identically; the token is still not shown.

**Pass / Fail**
- PASS if the token is never rendered, the input is disabled, and the badge and **Replace** button
  are present.
- FAIL if any part of the stored token appears on screen, if the input is editable without pressing
  **Replace**, or if the badge or button is missing.

**Test data**
- None.

**Notes**
- The masked characters you see are a fixed placeholder, not the token's real length — do not read
  anything into how many dots appear.

---

### TC-060 · Saving without retyping the secret does not erase it

| Field | Value |
|---|---|
| Suite | TS-04 Integrations |
| Type | Negative |
| Priority | High |
| Screen | `/integrations/docstore` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-059 passed — Documentation store is connected and shows `Configured ✓`.

**Steps**
1. On `/integrations/docstore`, change `Space key` from `PAY` to `PAY2`. Do **not** touch the
   `API token` row.
2. Click **Save**.
3. Click **Replace** on the `API token` row, then click **Cancel** without typing anything.
4. Click **Test connection**.

**Expected**
- Step 2 saves: the `Saved` banner appears and `Space key` reads `PAY2`.
- The `API token` row still shows `Configured ✓` and the **Replace** button after the save.
- After the Replace/Cancel in step 3 the row returns to the disabled input with `Configured ✓` —
  nothing was wiped.
- Step 4 returns a green `Connection OK` banner, proving the original token is still stored.

**Pass / Fail**
- PASS if the credential survives both an unrelated save and a cancelled rotation.
- FAIL if the row loses its `Configured ✓` badge, or if the connection test afterwards reports that
  no credentials have been saved.

**Test data**
- Space key: change to `PAY2`, then change it back to `PAY` before moving on.

**Notes**
- There is deliberately **no** way to blank a secret from this form; an empty secret means "no
  change", never "erase". To remove a credential you disconnect the capability. Do not raise the
  missing "clear secret" control as a defect.

---

### TC-061 · Test connection reports success for valid credentials

| Field | Value |
|---|---|
| Suite | TS-04 Integrations |
| Type | Functional |
| Priority | High |
| Screen | `/integrations/docstore` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-060 passed — Documentation store is connected with a valid Atlassian token, and `Space key` is
  back to `PAY`.

**Steps**
1. Go to `/integrations/docstore`.
2. Click **Test connection**.
3. Watch the form while the test runs.
4. When it finishes, read the banner and the left-hand footer button.

**Expected**
- While the test runs, the form body shows a spinner with `Testing connection to Confluence…` and
  the button label changes to `Testing…`.
- When it finishes, a green banner titled `Connection OK` appears with a one-line detail from the
  vendor.
- The footer button now reads `Re-test`.

**Pass / Fail**
- PASS if the testing state is shown and the result is a green `Connection OK` banner.
- FAIL if the app shows a raw error, hangs with no result, or reports failure on credentials that
  work in Confluence itself.

**Test data**
- The credentials saved in TC-058.

**Notes**
- Confluence, Jira, Figma and GitHub make a real authenticated call here. Xray and the built-in
  analyzer do not — see TC-065.

---

### TC-062 · Test connection reports the reason and a fix hint for a bad credential

| Field | Value |
|---|---|
| Suite | TS-04 Integrations |
| Type | Negative |
| Priority | High |
| Screen | `/integrations/docstore` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-061 passed.

**Steps**
1. On `/integrations/docstore`, click **Replace** on the `API token` row.
2. Type an obviously invalid token, e.g. `not-a-real-token`.
3. Click **Test connection**.
4. Read the banner in full.

**Expected**
- A red banner titled `Connection failed` appears — the page does not crash and no raw HTTP error
  or blank screen is shown.
- The detail explains the cause in plain language, e.g. `The credentials were rejected (not authorized). Check the API token is current and belongs to the account/email you entered, and that it has access.`
- The banner ends with a bolded `Fix:` followed by a hint, e.g.
  `Check the credentials and the site/host you entered, then re-test.`

**Pass / Fail**
- PASS if a red `Connection failed` banner shows both a human-readable reason and a `Fix:` hint.
- FAIL if the app crashes, shows a raw status code or stack trace, shows a green banner, or shows a
  failure with no reason and no hint.

**Test data**
- API token: `not-a-real-token`

**Notes**
- Do **not** click **Save** in this case — testing an untyped-but-unsaved credential is allowed and
  does not persist it. TC-063 needs a *saved* bad credential, and sets that up itself.

---

### TC-063 · A failed connection turns the card badge to `Failed` and the link to `Fix connection`

| Field | Value |
|---|---|
| Suite | TS-04 Integrations |
| Type | UX |
| Priority | High |
| Screen | `/integrations` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-062 passed and you are still on `/integrations/docstore` with the invalid token typed in.

**Steps**
1. Click **Save** to store the invalid token.
2. Click **Test connection** and wait for the red `Connection failed` banner.
3. Click **Back to integrations**.
4. Read the grid.

**Expected**
- The `Documentation store` card now shows the badge `Failed` and its link reads `Fix connection`.
- The card renders a red banner, and its text is the fixed string
  `Token rejected (401). The app credential may have expired.`
- Clicking **Fix connection** opens the same `Connect a capability` form for Documentation store.

**Pass / Fail**
- PASS if the badge reads `Failed`, the link reads `Fix connection`, and the red banner carries that
  exact fixed string.
- FAIL if the card still reads `Connected` / `Manage` after a failed test, or if no banner is shown
  at all.

**Test data**
- The invalid token from TC-062.

**Notes**
- **Do not read the banner as the real reason.** The API's connection payload carries no failure
  reason at all, so the card always falls back to the same hardcoded `Token rejected (401)…`
  sentence — you will see it word-for-word even when the true cause was a 404 host, a 429, or a
  timeout, and even when the detailed banner you read on the form in TC-062 said something else.
  That mismatch is a real product defect (the card reports a cause it does not know) but it is
  **already tracked separately** — confirm the string, note it, and do not raise a duplicate.
- **Known behaviour, do not raise as new:** while any capability is in the failed state, the grid
  renders **only that one card** — the other four capabilities disappear from `/integrations` until
  the failure is cleared. Verify it, note it, and restore a valid token (Replace → Save → Test) at
  the end of this case so the rest of the suite has a full grid again.

---

### TC-064 · The old Code intelligence address goes back to the Integrations grid

| Field | Value |
|---|---|
| Suite | TS-04 Integrations |
| Type | Negative |
| Priority | Medium |
| Screen | `/integrations/codeintel` → `/integrations` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- TC-063 passed and the grid is showing all five cards again.

**Steps**
1. Paste `http://localhost:5173/integrations/codeintel` into the address bar and press Enter.
2. Read the address bar and the page.
3. Repeat with a mistyped capability, `http://localhost:5173/integrations/not-a-capability`.
4. Click the browser Back button once.

**Expected**
- Steps 1 and 3 each land on `/integrations`: the address bar changes to `/integrations` and the
  capability grid from TC-056 renders, with the heading `Integrations`.
- No `Connect a capability` form renders for either address — no blank title, no empty breadcrumb,
  no empty `Vendor` select.
- The grid has no `Code intelligence` card.
- At step 4 Back does not return to the unknown address — the redirect replaced it in history.

**Pass / Fail**
- PASS if both addresses redirect to the `/integrations` grid.
- FAIL if either address renders a connect form (with or without a title), a blank page, or an error.

**Test data**
- `/integrations/codeintel` · `/integrations/not-a-capability`

**Notes**
- This case used to check a `Code intelligence` card and its connect form. That card was removed:
  code intelligence is now provisioned automatically for every workspace and needs nothing from you,
  so an old bookmark to it simply returns to the grid.

---

### TC-065 · A vendor with no live check reports OK even for junk credentials

| Field | Value |
|---|---|
| Suite | TS-04 Integrations |
| Type | Negative |
| Priority | Medium |
| Screen | `/integrations/testmgmt` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1. Test management is not connected.

**Steps**
1. On `/integrations`, click **Connect** on the `Test management` card.
2. Choose vendor `Xray`.
3. Enter Project key `PAY`, Client ID `junk-client-id`, Client secret `junk-client-secret`.
4. Click **Test connection**.

**Expected**
- A green banner titled `Connection OK` appears.
- Its detail is honest about what was and was not checked, reading
  `Connector is configured and ready (no live check for this vendor).`

**Pass / Fail**
- PASS if the banner is green **and** the detail explicitly says no live check was made.
- FAIL if the banner claims the connection was verified, or implies the credentials were accepted by
  Xray.

**Test data**
- Client ID: `junk-client-id` · Client secret: `junk-client-secret`

**Notes**
- **Known limitation, do not raise as new:** Xray and the built-in analyzer have no `ping()`, so
  their connection test only proves the connector could be constructed. The wording is what is under
  test here — the green banner is expected. Raise a defect only if the copy stops disclosing that no
  live check happened.

---

### TC-066 · Re-saving an already-connected capability updates it in place, never duplicating it

| Field | Value |
|---|---|
| Suite | TS-04 Integrations |
| Type | Negative |
| Priority | High |
| Screen | `/integrations/docstore` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Documentation store is already connected with a valid token (TC-058, restored at the end of
  TC-063), and `Space key` reads `PAY`.

**Steps**
1. Open `http://localhost:5173/integrations/docstore` in a fresh browser tab and wait for the form
   to finish loading (the `Loading connectors…` line is gone).
2. Read the `Vendor` select and the binding fields before touching anything.
3. Without changing a single field, click **Save**.
4. Go back to `/integrations`, reload the page (F5), and count the `Documentation store` cards.
5. Reopen the connection and re-read `Vendor`, `Space key`, `Base URL` and the `API token` row.
6. Repeat steps 1–5 once more.

**Expected**
- On load the form is already populated from the stored connection: `Vendor` reads `Confluence`,
  the binding fields carry the values saved in TC-058, and the `API token` row shows
  `Configured ✓` with a **Replace** button.
- Step 3 shows the green banner titled `Saved`.
- `/integrations` shows exactly **one** `Documentation store` card after each pass — never two, and
  never a second card for the same capability.
- Every binding value is unchanged after both passes, and the `API token` row still reads
  `Configured ✓` — re-saving did not blank the stored credential.

**Pass / Fail**
- PASS if re-saving an already-connected capability leaves exactly one connection with its binding
  and stored secret intact, twice in a row.
- FAIL if a second `Documentation store` card appears, if the binding is silently replaced by empty
  values, if the `Configured ✓` badge is lost, or if the app shows a crash or a raw `409`.

**Test data**
- None.

**Notes**
- The original version of this case asked you to race the page load and click **Save** before the
  form hydrated, in order to see the red `Couldn’t save` banner reading
  `docstore is already connected — edit or disconnect it first.` **That race cannot be run from the
  browser:** **Save** stays disabled until a vendor is selected, and the vendor is only populated by
  the same load you are trying to beat — so the fast click is always a no-op on a disabled button.
  The duplicate-connection guard does exist on the server, but the UI reaches it by a PATCH, never a
  second POST. The banner text above is therefore **not** something to look for here.
- What is under test is the risk the old case was aiming at — that a capability can only ever hold
  one connection — via the path the product actually takes.

---

### TC-067 · A non-admin cannot use Integrations

| Field | Value |
|---|---|
| Suite | TS-04 Integrations |
| Type | Permission |
| Priority | High |
| Screen | `/integrations`, `/integrations/docstore` |
| Persona | P10 Engineer |
| Automation | No |

**Preconditions**
- Documentation store, and at least one other capability, are connected in `QA Bravo` (TC-058,
  TC-065).
- P10 (`qa+b.eng@…`, role `engineer`, no tenant-admin) exists — invited by Tester A's TS-02 flow or
  by you from `/admin/users`.

**Steps**
1. Log out and log back in as P10 with password `QaTest-2026!`.
2. Click **Integrations** in the sidebar.
3. Read every card on the grid.
4. Click **Connect** on `Task tracker` and open the `Vendor` select.

**Expected**
- P10 can reach `/integrations` — the nav item is not hidden and the route is not blocked.
- All five cards show `Not connected`, **including the capabilities that are actually connected** —
  no other tenant's or admin's connection data is exposed.
- On the connect form the `Vendor` select contains only `Choose a vendor…`; no vendor can be chosen,
  no fields render, and **Save** stays disabled.
- P10 cannot create, change, or test any connection from the UI.

**Pass / Fail**
- PASS if a non-admin can see no connection data and can perform no integration action.
- FAIL if P10 sees a real vendor binding, a `Connected` badge on a capability an admin connected, a
  `Configured ✓` badge, or can successfully save or test a connection.

**Test data**
- P10 login: `qa+b.eng@edvensoft.com` / `QaTest-2026!`

**Notes**
- All integration endpoints are tenant-admin only, so P10's requests are refused. The screen has no
  error state for that refusal, so what a non-admin actually sees is an **empty-looking grid**, not a
  permission message. The security boundary holds (no data leaks), but the screen misleads a
  non-admin into thinking nothing is connected and that they are free to connect it. Raise **that**
  as a Medium UX defect if it is not already logged; do not raise it as a permission failure.

---

### TC-068 · The `Couldn’t save` banner uses a curly apostrophe where the rest of the app uses a straight one

| Field | Value |
|---|---|
| Suite | TS-04 Integrations |
| Type | UX |
| Priority | Low |
| Screen | `/integrations/:capability` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Logged in as P1. You have a way to make a save fail — the fastest is to stop the backend:
  `docker compose --profile app stop backend`.

**Steps**
1. Open `/integrations/designsource`, choose vendor `Figma`, enter File key `aBcD1234` and Access
   token `qa-copy-check`.
2. Stop the backend.
3. Click **Save**.
4. Zoom in on the red banner's title and compare the apostrophe with the ones on `/work-items`
   (`Couldn't create this work item.`) and `/connect` (`Couldn't disconnect this machine.`).
5. Restart the backend: `docker compose --profile app start backend`.

**Expected**
- The banner title reads `Couldn’t save` with a curly apostrophe (`’`).
- The comparable copy elsewhere in the app uses a straight apostrophe (`'`).

**Pass / Fail**
- PASS if the inconsistency is confirmed as described (log it as a Low copy defect).
- FAIL — i.e. nothing to report — if all three strings use the same apostrophe character.

**Test data**
- File key: `aBcD1234` · Access token: `qa-copy-check`

**Notes**
- Purely a copy-consistency case. Pick one character and use it everywhere; which one is a product
  decision, not a QA one. Remember to restart the backend before running any other case.
