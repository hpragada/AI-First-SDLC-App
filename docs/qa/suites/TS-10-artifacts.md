# TS-10 · Artifacts & Publish

The artifact registry and everything downstream of it: the listing and its filters, the read-only
preview, and the manual publish/export flow that must never bypass a gate. **Owner: Tester C.**
This suite is the one that proves non-negotiable #5 — *nothing reaches a system-of-record without an
approved gate* — so TC-151 is the single most important case in the file.

**Run these in order.** The suite builds on state that the earlier cases create: TC-141 needs at
least one completed phase run from TS-07, and TC-146 onwards need at least one artifact whose gate
has been approved in TS-09.

**Read this before you start — it changes what several cases assert.** When a run reaches its
gate, its draft artifacts are marked **`Waiting for approval`** (since commit 4ac75f9; before that
they kept reading `Draft`). Approving the gate **publishes** them in the same transaction, and
rejecting it marks them **`Superseded`**. So on the plan path an artifact reads `Draft` while its
run is still working, `Waiting for approval` while its gate is open, and `Published` the instant the
gate is approved. There is no observable `Approved` state on that path. The manual publish screen
(TC-152 onwards) is a **re-publish** of an already-published artifact, not the thing that first
publishes it. Any expectation that a gate-approved artifact reads `Approved`, or that the registry
offers an `Approved` filter option, is wrong.

Everything here is done as **P1 Owner-Admin** unless a case says otherwise — a tenant admin can
approve any gate, which keeps the suite from stalling behind a persona swap.

**Sequencing note (TC-153 → TC-156).** TC-153 needs a connected documentation-store connector;
TC-156 needs none. Run TC-153 first, then TC-156, and follow TC-156's mandatory reconnect step —
the connector belongs to TS-04 (Tester B) and must be left connected.

**ID note.** The plan reserves TC-141 – TC-156 for this suite and that range is fully used. Cases
added by the pack audit therefore continue at **TC-241**, which collides with nothing.

---

### TC-141 · Registry lists an artifact after a phase run, with the right columns

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | Functional |
| Priority | Critical |
| Screen | `/artifacts` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Project `Payment Gateway v2` is selected in the top bar.
- At least one phase (Ideation is the quickest) has been run to completion in TS-07, so the run has
  registered an artifact.

**Steps**
1. Log in as P1 and click **Artifacts & Traceability** in the sidebar.
2. Read the page heading and sub-heading.
3. Read the table's column headers left to right.
4. Find the row for the phase you ran.

**Expected**
- The heading is `Artifacts` and the sub-heading is
  `The registry: pointers, versions, and system-of-record links — never artifact bodies. Preview opens read-only.`
- A **View traceability** link sits in the page header.
- The table headers read `Artifact`, `Phase`, `Version`, `Status`, `System of record`, followed by
  one blank header above the actions column.
- The row shows a human artifact name (not a raw key like `01_ideation`), the humanized phase name,
  a version like `v1`, and a status badge.
- The `System of record` cell shows a chip carrying the artifact's raw system-of-record token.
  For an artifact that has never been exported the chip reads `internal`; after an external
  export it reads `confluence` or `jira`.
- The row's actions column contains a **Preview** link.

**Pass / Fail**
- PASS if the artifact appears with all six columns rendered as above.
- FAIL if the run completed but no row appears, if a header is missing or renamed, or if the
  `Artifact` or `Phase` cell shows a raw key (`03_prd`, `test_case`) where a human label is
  expected.

**Notes**
- The registry stores *pointers*, never bodies. `internal` in the `System of record` cell means
  "not exported anywhere yet" and is correct, not a defect.
- **Two known display defects, already tracked — do not raise them again.** (a) The cell renders
  a Confluence-styled chip regardless of the actual system of record, so an `internal` or `jira`
  artifact is drawn with the Confluence glyph. (b) The copy `Platform only`, which several
  wireframes and the design gallery show for a non-exported artifact, can never render on the live
  screen — the underlying value is never blank. Record what you actually see.

---

### TC-142 · Each status badge matches the artifact's gate state — `Waiting for approval`, `Published`, `Superseded`

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | UX |
| Priority | Medium |
| Screen | `/artifacts` · `/gates` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-141 passed.
- At least two artifacts exist in different states: one from a phase whose gate is still open on
  `/gates`, and one from a phase whose gate has been approved in TS-09.
- Optional, for the third badge: one artifact from a run whose gate was **rejected** (TS-09 TC-133).

**Steps**
1. Go to `/gates` and, on the **Pending** tab, note the work item and gate of every gate that is
   still open. These are the phases whose artifacts are waiting on a decision.
2. Go to `/artifacts` and read the `Status` cell of every row.
3. Find the row for a phase you listed in step 1 and read its badge.
4. Find the row for a phase whose gate was approved and read its badge.
5. If you have one, find the row for the run whose gate was rejected and read its badge.
6. Note which rows also offer an **Export** action.

**Expected**
- The artifact of a phase whose gate is still open (step 1) reads `Waiting for approval` and offers
  **Preview** only.
- The artifact of a phase whose gate was approved reads `Published` and offers **Preview** and
  **Export**.
- The artifact of a run whose gate was rejected reads `Superseded` (grey) and offers **Preview**
  only.
- An artifact whose run is still working and has not reached its gate reads `Draft`.
- Every badge is one of those words (or `Run output` on a run's closing-message row). No cell shows
  a raw token such as `staged`, `pending_gate`, `superseded` or `approved`, and no `Pending gate`
  badge appears anywhere.

**Pass / Fail**
- PASS if every badge is one of the words above and each maps to the gate state you established on
  `/gates` in step 1.
- FAIL if any raw underscore or lower-case token is rendered, if a still-gated artifact reads
  `Published` or `Draft`, if a gate-approved artifact does not read `Published`, or if a rejected
  run's artifact reads `Draft` or `Waiting for approval`.

**Notes**
- **Changed in commit 4ac75f9.** Opening a gate now marks the run's draft artifacts as staged, shown
  as `Waiting for approval`. The old `Pending gate` badge, which nothing could ever trigger, was
  deleted, so the note that used to sit here about a "dead" badge no longer applies.
- There is no observable `Approved` badge on the gate path: approving a gate publishes the artifact
  in the same transaction, so it goes straight from `Waiting for approval` to `Published`. That is
  why **Export** and `Published` always appear together here.

---

### TC-143 · Phase, Type and Status filters and the search box narrow the registry

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | Functional |
| Priority | Medium |
| Screen | `/artifacts` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- At least three artifacts from at least two different phases exist.

**Steps**
1. Go to `/artifacts` and note the total number of rows.
2. Open the `Phase: All` select and choose one of the listed phases.
3. Reset it to `Phase: All`, then use `Type: All` and pick a type; reset again and use `Status: All`
   and pick a status.
4. Reset all three, type part of one artifact's name into `Search artifacts…`.
5. Clear the search box.

**Expected**
- Each select's options are the values actually present in the registry, plus the `…: All` default —
  not a fixed vendor list.
- Choosing a phase leaves only rows whose `Phase` cell matches; the same for type and status.
- Typing in `Search artifacts…` narrows the table to rows whose name, type or phase contains the
  text, case-insensitively.
- Clearing the search restores the full row count from step 1.
- Each of the three selects is as wide as the option it is showing. With `Waiting for approval` or a
  long phase name selected, the whole word is visible in the closed select — nothing is cut off.

**Pass / Fail**
- PASS if all four controls change the visible rows and clearing them restores the full list.
- FAIL if any control is inert (row count never changes), or a select renders with only the
  `…: All` option while multiple phases/types/statuses are clearly present in the table.

**Test data**
- Search term: the first word of any artifact name in the table.

**Notes**
- Each select's options are built from the values actually present, so `Status: All` offers only
  the statuses in the registry — typically `Draft`, `Waiting for approval`, `Published` and
  `Superseded`, in the same words as the badges. There is deliberately **no** `Pending Gate` option,
  and `Approved` appears only if some artifact actually carries that status (see TC-142). An absent
  option is not a defect.
- The selects sizing themselves to their text is new in commit b40c557; they used to be fixed-width
  and cut `Waiting for approval` short.
- All four controls filter **client-side over the rows already fetched**; there is no pagination,
  so the row count in step 1 is the whole registry. See TC-244.

---

### TC-144 · Filtered-empty state appears when nothing matches

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | UX |
| Priority | Medium |
| Screen | `/artifacts` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- The registry has at least one artifact.

**Steps**
1. Go to `/artifacts`.
2. Type `zzzzz` into `Search artifacts…`.
3. Read the panel that replaces the table.
4. Clear the search box.

**Expected**
- The table is replaced by an empty state titled `No artifacts match these filters` with the text
  `Clear the search or filters to see the full registry.`
- The search box and the three selects remain visible above it, so the filters can be cleared.
- Clearing the search restores the table.

**Pass / Fail**
- PASS if that exact filtered-empty copy is shown and the filter bar stays on screen.
- FAIL if the `No artifacts yet` copy is shown instead (that is the *truly*-empty state — see
  TC-145), if the filter bar disappears, or if the table simply renders zero rows with no message.

---

### TC-145 · Truly-empty registry on a project that has never run a phase

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | UX |
| Priority | Medium |
| Screen | `/artifacts` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A second project exists in the workspace with no completed runs. Create one from
  `/projects/new` if you do not have one (name it `QA Empty Project`, Greenfield).

**Steps**
1. Switch the top-bar project select to `QA Empty Project`.
2. Go to `/artifacts`.
3. Read the panel.

**Expected**
- An empty state titled `No artifacts yet` with the text
  `Run a phase to produce the first artifact. It registers here as a draft pointer until its gate is approved.`
- The search box and the `Phase: All` / `Type: All` / `Status: All` selects are **not** rendered —
  there is nothing to filter.

**Pass / Fail**
- PASS if the truly-empty copy is shown and the filter bar is absent.
- FAIL if the filtered-empty copy appears instead, or an empty table with headers renders.

**Notes**
- Switch back to `Payment Gateway v2` before the next case.

---

### TC-146 · Export appears only once a phase's gate has been approved

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | Functional |
| Priority | High |
| Screen | `/gates` → `/artifacts` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- At least one artifact whose gate has been approved in TS-09.
- At least one artifact from a phase whose gate is still open.

**Steps**
1. Go to `/gates`. On the **Pending** tab, write down the gate label and work item of one gate that
   is still open. This is your not-yet-approved phase — the registry itself cannot tell you this,
   so establish it here first.
2. Switch to the **History** tab and write down one gate that was approved. This is your approved
   phase.
3. Go to `/artifacts`. Find the row for the phase from step 1 and read its actions column.
4. Find the row for the phase from step 2 and read its actions column.
5. Click **Export** on that second row.

**Expected**
- The row for the still-open gate (step 1) shows **Preview** only — no **Export** — and its status
  badge reads `Waiting for approval`.
- The row for the approved gate (step 2) shows both **Preview** and **Export**, and its status
  badge reads `Published`.
- Clicking **Export** opens `/artifacts/{id}/publish` with the heading
  `Publish to system of record`.

**Pass / Fail**
- PASS if **Export** is present only on the row whose gate you confirmed approved on `/gates`, and
  lands on the publish screen.
- FAIL if **Export** shows on a row whose gate is listed as Pending on `/gates` — that is a **High**
  severity gate-bypass affordance even though the backend would still reject it.

**Notes**
- The button is deliberately hidden rather than disabled, so the user can never land on a status
  rejection from the registry.
- `/gates` is the oracle for this case, and the registry now agrees with it: since commit 4ac75f9 an
  artifact at an open gate reads `Waiting for approval`, not `Draft`. Step 1 stays, because the
  assertion is that the registry and the gates list tell the same story.

---

### TC-147 · Preview opens read-only with the never-an-editor banner and version history

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | Functional |
| Priority | High |
| Screen | `/artifacts/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- At least one artifact with a body exists (any completed phase).

**Steps**
1. Go to `/artifacts` and click **Preview** on any row.
2. Read the breadcrumb and the page heading.
3. Read the banner directly under the heading.
4. Look at the card in the right column.
5. Try to click into the artifact body and type.

**Expected**
- The breadcrumb reads `Artifacts / Preview`.
- The heading reads `{artifact name} · v{n}` with a status badge beside it. The badge uses the same
  words and colours as `/artifacts` — `Published`, `Waiting for approval`, `Draft` or `Superseded`,
  never a lower-case token.
- An info banner reads exactly
  `Read-through from the system-of-record. This preview is never an editor.`
- The right column shows a card titled `Version history`. With only one version registered it reads
  `No prior versions.`; with more, it lists one row per version tagged `v{n}`, each with its status in
  words (for example `Superseded`), not a lower-case token.
- The body is not editable — clicking into it places no cursor and typing changes nothing. There is
  no Save/Edit control anywhere on the screen.
- If the artifact has been published to Confluence, an `Open source` chip appears next to the
  heading.

**Pass / Fail**
- PASS if the banner copy is exact, the `Version history` card renders, and nothing on the screen
  can edit the body.
- FAIL if any editing affordance exists (that is **Critical** — it breaks the read-through rule), or
  if the banner or card is missing.

---

### TC-148 · A markdown artifact previews as formatted markdown, not raw source

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | UX |
| Priority | Medium |
| Screen | `/artifacts/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- An artifact from a document-producing phase (Ideation, Requirements, PRD or Architecture) exists.

**Steps**
1. Open that artifact's preview from `/artifacts`.
2. Read the body.

**Expected**
- Headings render as headings, lists as bulleted/numbered lists, and inline code as code — the body
  reads as a formatted document.
- No raw markdown syntax is visible as literal text (no stray `##`, `**`, `- ` at line starts).
- If the body contains a ```mermaid fence, a diagram renders rather than the fence text.

**Pass / Fail**
- PASS if the document renders formatted.
- FAIL if raw markdown source is displayed.

**Notes**
- Do **not** run this case against a `test_case` artifact from a Testing run — those preview a batch
  of ~25 unrelated test cases (`docs/TESTING_PHASE_BUGS_HANDOFF.md` Bug 1, already logged). Also
  already logged: a phase can reach its gate with an empty phase document (Bug 4), so an entirely
  blank body is not a new defect either — mark the case **Blocked** with that reference and pick a
  different artifact.

---

### TC-149 · A listed artifact with no readable body shows `Preview unavailable`, not "not found"

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | UX |
| Priority | Medium |
| Screen | `/artifacts` · `/traceability` · `/artifacts/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- An internal artifact exists whose body cannot be read back. On `/artifacts` such a row shows the
  muted text `Nothing to preview` in its actions cell instead of a **Preview** link. Runs that failed
  or were parked before reporting a body (TS-07/TS-14) are the usual source. Do not force the state
  any other way.

**Steps**
1. Go to `/artifacts` and find a row whose actions cell reads `Nothing to preview`. Note its name,
   phase and status.
2. Click **View traceability** in the page header.
3. Find the node carrying that artifact's name and click it.
4. Read the screen.
5. Go back to `/artifacts` and confirm the row is still listed.

**Expected**
- Step 3 opens `/artifacts/{id}` in the same tab (an internal artifact has no external link).
- The breadcrumb `Artifacts / Preview` is shown.
- In place of a document, an empty state titled `Preview unavailable` reads
  `The document couldn't be read from its source right now. Its record and version are intact.`
- **No** `We couldn't find that document` banner appears — the document exists, so the screen must
  not say it is missing.
- No raw error text, stack trace or status code is visible.
- The row is still present in the registry after step 5 — the record is intact, only its body is
  unreadable.

**Pass / Fail**
- PASS if `Preview unavailable` renders inside the normal shell and the registry row survives.
- FAIL if the screen says the document cannot be found, blanks, shows a raw error or status code, or
  redirects away from `/artifacts/:id`.

**Notes**
- **Changed in commit 4ac75f9.** The screen used to answer this artifact with the same
  `Artifact not found` banner as a document that does not exist, and `Preview unavailable` could
  never render. The server now answers a readable-but-empty artifact normally, so the two cases show
  different screens. TC-150 covers the not-found half.
- The registry hides **Preview** on these rows on purpose, so the traceability map is the in-product
  route to the preview address. It is not a workaround for a bug.
- If no row in your registry reads `Nothing to preview`, mark this case **Not Run** with the reason
  rather than manufacturing the state outside the product.

---

### TC-150 · An unknown artifact id shows `We couldn't find that document`

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | Negative |
| Priority | Medium |
| Screen | `/artifacts/:id` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 with a project selected.

**Steps**
1. Open a real artifact preview and copy its URL.
2. Edit the id in the address bar to `00000000-0000-0000-0000-000000000000` and press Enter.
3. Read the panel.

**Expected**
- A danger banner titled `We couldn't find that document` with the text
  `It may have been removed, or you may not have access to this project.`
- The breadcrumb `Artifacts / Preview` still renders and the app shell is intact.
- The `Preview unavailable` state from TC-149 does **not** appear.

**Pass / Fail**
- PASS if the not-found banner renders inside the normal shell.
- FAIL if the app crashes to a blank page, redirects silently to `/`, or leaks a raw 404/500 body.

**Test data**
- Artifact id: `00000000-0000-0000-0000-000000000000`

**Notes**
- The banner copy changed in commit 4ac75f9. The old `Artifact not found` /
  `This artifact doesn't exist, has no body, or you don't have access to it.` text no longer exists.
- If the request **fails** rather than finding nothing (for example the backend is down), the screen
  shows a different panel titled `We couldn't open this document` with a retry control. That is a
  separate state, not this case's result.

---

### TC-151 · A draft or staged artifact cannot be published — the gate rule holds

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | Negative |
| Priority | Critical |
| Screen | `/artifacts/:id/publish` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- An artifact exists whose gate has **not** been approved — trigger a phase in TS-07 and stop at
  `Awaiting gate`. Do not approve it.
- You have that artifact's preview URL (from `/artifacts` → **Preview**).

**Steps**
1. Confirm on `/artifacts` that this row shows **Preview** only — no **Export**.
2. In the address bar, append `/publish` to the artifact's preview URL and press Enter.
3. Read the modal.
4. Try to click the **Publish** button.
5. Click **Open gate ↗**.

**Expected**
- The heading is `Publish to system of record` with the sub-heading
  `Manually publish (or re-publish) a gate-approved artifact to a chosen target. Gate rule still holds — only approved artifacts can be published.`
- A modal titled `Publish artifact` shows a disabled `Artifact` field, and a red banner titled
  `Can't publish — not gate-approved` reading
  `This artifact is still {status}. Approve its gate first; manual publish never bypasses a gate.`
  with the artifact's current status in bold. For an artifact whose run is at `Awaiting gate`,
  `{status}` is the lower-case token `staged` — this banner prints the raw status, while the
  registry badge for the same artifact reads `Waiting for approval`.
- The **Publish** button is disabled and clicking it does nothing — no request, no navigation, no
  change of state.
- **Open gate ↗** navigates to the gates screen.
- **Cancel** returns to the artifact preview.
- Returning to `/artifacts` afterwards, the artifact's status badge is unchanged.

**Pass / Fail**
- PASS if the blocked banner renders, **Publish** is disabled, and the artifact's status is
  unchanged after the attempt.
- FAIL — severity **Critical** — if the artifact publishes, its status changes, a system-of-record
  link appears, or the **Publish** button is live for a non-approved artifact.

**Notes**
- The bold status in the banner is the raw token (`staged`, `draft`) because the banner prints the
  stored value (`ExportPublish.tsx:129`), while every other screen says `Waiting for approval` /
  `Draft`. This banner is reached only by typing the `/publish` address — the registry offers
  **Export** on approved or published rows only. The approved branch has the same fault in its
  `Artifact` field, which ends `· approved` or `· published` in lower case (`ExportPublish.tsx:152`),
  and that one IS on the normal Export path. That is a **known client-copy issue raised with the team**; assert what ships today and
  do not raise a duplicate.
- This is the load-bearing case of the suite. Deep-linking to `/publish` is a legitimate way to
  reach the screen through the product (the URL is reachable from the address bar); it is not an
  API call or a state hack.

---

### TC-152 · An internal re-publish of a gate-approved artifact succeeds and changes nothing

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | Functional |
| Priority | Critical |
| Screen | `/artifacts/:id/publish` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- An artifact whose gate was approved in TS-09 (its row offers **Export** in the registry).

**Steps**
1. Go to `/artifacts` and read the approved row's `Status` and `System of record` cells **before**
   you do anything. Write both down.
2. Click **Export** on that row.
3. Read the `Artifact` field and the banner above the target picker.
4. Open the `Target capability` select and read which option is **already selected**.
5. Explicitly choose `Internal (platform)`.
6. Click **Publish**.
7. When the result modal appears, read its title and body, then click **Done**.
8. Return to `/artifacts` and re-read the row's `Status` and `System of record` cells.

**Expected**
- Step 1: the row already reads `Published`, with `internal` in the `System of record` cell —
  approving the gate published it. This case is a *re*-publish.
- The `Artifact` field is disabled and shows `{name} · v{n} · published` (the status is the raw
  lower-case token).
- A green banner titled `Gate approved` reads `Eligible to publish.`
- Step 4: for a phase that has an external export target, the select is **pre-selected on the
  external option**, not on `Internal (platform)`. Step 5 is therefore mandatory — do not skip it.
- While the request is in flight the button reads `Publishing…` and **Cancel** is disabled.
- The result modal is titled `Published`.
- **Done** returns to the artifact preview.
- Step 8: both cells are unchanged — still `Published`, still `internal`. An internal publish
  creates no external link and no new version.

**Pass / Fail**
- PASS if the modal title is `Published` and the registry row is byte-for-byte the same afterwards.
- FAIL if the publish errors, if the `System of record` cell gains an external reference after an
  internal publish, or if the status badge changes to anything other than `Published`.

**Notes**
- The pre-selected external target (step 4) is the trap in this case: following the old "leave the
  select where it is" instruction publishes **externally**. It is already tracked as a product
  defect that the control defaults to the riskier option; do not raise it again, but do follow
  step 5 exactly or the case tests the wrong thing.
- Because the gate already published the artifact, the assertion here is **idempotence**, not a
  status transition. There is no state in which a gate-approved artifact reads anything but
  `Published` before this screen is opened.

---

### TC-153 · Target capability select and the Destination field's per-vendor help text

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | Functional |
| Priority | High |
| Screen | `/artifacts/:id/publish` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A Confluence (docstore) connector is connected and tested on `/integrations` (TS-04).
- A gate-approved artifact from a docstore phase — Ideation, Requirements, PRD, Architecture,
  Security or CI/CD.
- **Run this case before TC-156.** TC-156 disconnects the workspace's documentation-store
  connector, which is the connector this case depends on and which TS-04 (Tester B) owns. If you
  have already run TC-156, reconnect the connector on `/integrations` before starting here.

**Steps**
1. Open that artifact's publish screen via **Export**.
2. Open the `Target capability` select and read every option.
3. Choose the non-internal option and read the `Destination` field's help text.
4. Leave `Destination` blank and click **Publish**.
5. Read the result modal and click the `Open` chip.

**Expected**
- The `Target capability` select offers exactly two options: `Internal (platform)` and
  `Documentation store · Confluence` — one phase, one allowed external target.
- Selecting the external option reveals a `Destination` field whose help text reads
  `Confluence space key (blank = connector default)`.
- Switching back to `Internal (platform)` hides the `Destination` field again.
- The result modal is titled `Published`, and below the banner a line reads
  `View it in the system of record:` next to an `Open` chip.
- The `Open` chip opens the Confluence page in a new tab.
- Back on `/artifacts` the row's `System of record` chip now reads `confluence` instead of
  `internal`.

**Pass / Fail**
- PASS if the select offers only those two options, the correct help text appears, and the success
  modal carries a working `Open` chip.
- FAIL if a phase's disallowed capability is offered, if the help text names the wrong vendor, or if
  the modal claims success without a link after an external publish.

**Notes**
- The per-vendor help strings are `Confluence space key…` for docstore,
  `Jira project key…` for tasktracker and `Xray/Jira project key…` for testmgmt.
- On a Task Breakdown → Jira export, if some backlog items fail to reach the tracker the modal is
  titled **`Published — with issues`** and carries a red sub-banner naming the failed items. That is
  the expected honest-partial state, not a defect on its own — record what you saw.
- Only `test_case` artifacts may go to test management. A test plan or test report rejected with
  `Only test_case artifacts export to the test-management system; test plans and reports stay internal.`
  is correct behaviour.

---

### TC-154 · A phase with an internal-only export policy offers no external target

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | UX |
| Priority | Medium |
| Screen | `/artifacts/:id/publish` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A gate-approved artifact from a phase with no external target. Either use a UX Design artifact
  (TC-155 covers its extra note), or set one phase to internal-only on `/profile`'s export policy.

**Steps**
1. Open that artifact's publish screen via **Export**.
2. Look for the `Target capability` select.
3. Read the banner in its place.
4. Click **Publish**.

**Expected**
- No `Target capability` select and no `Destination` field are rendered.
- An info banner reads `This phase publishes internally only per the project's export policy.`
- **Publish** is enabled and completes with the `Published` modal — internal-only means restricted
  *destination*, not blocked publishing.
- The registry row afterwards reads `Published` with `Platform only` in the `System of record` cell.

**Pass / Fail**
- PASS if the internal-only banner replaces the target picker and the internal publish still
  succeeds.
- FAIL if an external capability is offered for a phase the policy does not allow it for — that is
  a **High** severity policy hole.

---

### TC-155 · UX Design artifacts are hard-locked to internal with the Figma note

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | UX |
| Priority | Medium |
| Screen | `/artifacts/:id/publish` |
| Persona | P1 Owner-Admin / P4 Designer |
| Automation | No |

**Preconditions**
- A UX Design phase has been run and its gate approved by P4 Designer (or P1) in TS-09.
- A Figma connector may be connected or not — it must make no difference to this case.

**Steps**
1. Go to `/artifacts` and click **Export** on the UX Design artifact.
2. Read the banner where the target picker would be.
3. Confirm no `Target capability` select is present.

**Expected**
- The banner reads, in one block:
  `This phase publishes internally only per the project's export policy.` followed by
  `Figma export is coming later; UX artifacts stay internal for now.`
- No `Target capability` select and no `Destination` field appear.
- **Publish** is enabled and publishes internally only.

**Pass / Fail**
- PASS if both sentences appear together and no Figma target is offered.
- FAIL if a Figma or docstore target is offered for a UX Design artifact, or if only the generic
  internal-only sentence appears without the Figma note.

**Notes**
- Figma *write* is a deliberately deferred seam. Figma *read* is unaffected — a connected Figma
  integration on `/integrations` is not evidence that this banner is wrong.

---

### TC-156 · An external publish with no connector fails loudly and never claims a push

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | Negative |
| Priority | High |
| Screen | `/integrations` · `/artifacts/:id/publish` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- **TC-153 has already passed.** This case disconnects the workspace's documentation-store
  connector, which TC-153 and TS-04 both depend on.
- Tell Tester B (who owns TS-04) that the docstore connector will be down for the duration of this
  case.
- A gate-approved artifact from a docstore phase (PRD or Requirements) that has **not** been
  exported externally — its `System of record` chip reads `internal`.

**Steps**
1. Go to `/integrations`. If a documentation-store connector is connected, disconnect it through
   that screen. Confirm the docstore capability now shows as not connected.
2. Go to `/artifacts` and click **Export** on the artifact from the preconditions.
3. Choose `Documentation store · Confluence` as the `Target capability`.
4. Leave `Destination` blank and click **Publish**.
5. Read the panel that appears in the modal.
6. Click **Cancel**, go back to `/artifacts` and read the row's `Status` and `System of record`
   cells.
7. **Cleanup — mandatory.** Go back to `/integrations` and reconnect the documentation-store
   connector exactly as TS-04 left it, then run its **Test connection** action and confirm it
   passes. Do not leave the workspace disconnected; TC-153 and Tester B's suite both need it.

**Expected**
- Step 5: the publish **fails**. A red banner titled `Publish failed` reads
  `No documentation-store connector is configured for this workspace. Connect one on the Integrations page first.`
- No result modal titled `Published` appears, and no `View it in the system of record:` line or
  `Open` chip is shown.
- Step 6: the row is unchanged — still `Published` (its gate approval published it), and the
  `System of record` chip still reads `internal`. The platform never records a push that did not
  happen.
- Step 7: the connector reconnects and tests green.

**Pass / Fail**
- PASS if the export fails with that exact connector-guidance message and the registry row is
  untouched afterwards.
- FAIL — severity **High** — if the modal reports success, if a system-of-record link appears for a
  push that could not have happened, or if the `System of record` chip changes to `confluence`.
- FAIL if the screen shows a raw 400/500 body or a stack trace instead of the guidance banner.

**Notes**
- **This case previously expected an internal fallback on the first attempt. That branch is
  unreachable and the expectation has been corrected.** The fallback only fires for an artifact in
  the `approved` state, and no artifact ever reaches `approved` — approving a gate publishes in the
  same transaction. Every artifact you can click **Export** on is already `published`, so every
  export failure takes the honest-failure path. Do not raise the missing fallback as a defect; the
  dead branch is tracked separately.
- Do not skip step 7. Leaving the connector disconnected silently invalidates TC-153 and several
  TS-04 cases.

---

### TC-241 · A failed registry request shows an error panel with `Try again`, not an empty registry

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | UX |
| Priority | High |
| Screen | `/artifacts` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Two projects exist that P1 is a member of: `Payment Gateway v2` (populated) and a second one.
- You can stop and restart the backend process (the `make dev` / `docker compose` terminal). This
  case needs the backend down for about a minute.
- **Do not reload the browser tab at any point during this case.** A reload re-requests your
  session, which fails with the backend down and bounces you to `/login`, and you will observe
  nothing. Every step below is an in-app navigation.

**Steps**
1. Signed in as P1 with `Payment Gateway v2` selected, go to `/artifacts` and confirm rows are
   listed. Note the row count.
2. Stop the backend.
3. **Without reloading**, use the top-bar project select to switch to the second project. This
   forces a fresh registry request for a project the browser has never fetched.
4. Wait about 15 seconds — the app retries a failed request a few times before giving up — then
   read the whole screen. Note the heading, the panel's title and text, and whether the search box
   and the three filter selects are present.
5. Click **Try again** while the backend is still down, and read the screen again.
6. **Cleanup — mandatory.** Restart the backend, wait for it to come up, click **Try again**, then
   switch the project select back to `Payment Gateway v2`. Confirm the rows from step 1 return.

**Expected**
- The `Artifacts` heading, its sub-heading and the **View traceability** link still render.
- In place of the filter bar and the table, a danger banner titled
  `Can't reach the SDLC app right now` reads `Your browser couldn't connect.`, followed by a
  **Try again** button and the line
  `This screen is empty because it didn't load — not because there is nothing here.`
- The `Search artifacts…` box and the three filter selects are **not** shown, and neither
  `No artifacts yet` nor `No artifacts match these filters` appears.
- No status code, raw error text or stack trace is visible.
- Step 5: with the backend still down, the same panel returns after the retries.
- Step 6: after **Try again** with the backend up, the second project's registry (or its
  `No artifacts yet` state) renders, and switching back restores the rows from step 1.

**Pass / Fail**
- PASS if a failed registry request shows the `Can't reach the SDLC app right now` panel with a
  working **Try again**, and never an empty-registry or filtered-empty message.
- FAIL if the failure renders as `No artifacts yet` or `No artifacts match these filters`, if the
  panel has no **Try again**, or if the app blanks, crashes, shows a raw error body, or redirects to
  `/login`.

**Notes**
- **Rewritten for commit 6d85ec9.** This case used to record that a failed request looked exactly
  like an empty, filtered registry. The screen now checks for a failed request before anything else
  (`ArtifactsRegistry.tsx:116-123`), so that defect is fixed and this case guards it.
- The title and line depend on **why** the request failed. Stopping the backend is a lost
  connection, which gives the copy above. A server fault would instead read
  `Something went wrong on our side` / `The app couldn't load this. Nothing you did caused it.`
  Record the title you actually saw.

---

### TC-242 · A multi-state wireframe artifact previews behind a state switcher

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | Functional |
| Priority | Medium |
| Screen | `/artifacts/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A UX Design phase has been run to completion, producing per-screen wireframe artifacts. These are
  the only artifacts that carry more than one document body.

**Steps**
1. Go to `/artifacts`, narrow `Phase: All` to the UX Design phase, and click **Preview** on one of
   the wireframe rows.
2. Read the row of buttons directly under the read-through banner.
3. Note which button is selected when the screen first paints.
4. Click each of the other buttons in turn and watch the framed document below.
5. Confirm the `Version history` card is still rendered in the right column.

**Expected**
- Under the `Read-through from the system-of-record. This preview is never an editor.` banner sits
  a row of buttons, one per captured UI state, with the names humanized — a `state-01-default`
  state renders as `default`, `state-03-empty` as `empty`, and so on.
- The buttons are in alphabetical order by state name, and the `default` state is selected on load.
- Clicking a button swaps the framed document below it; the selected button is styled as primary
  and the others are not.
- Each state renders as a laid-out page inside its own frame, not as raw HTML source text.
- The `Version history` card renders as described in TC-147.

**Pass / Fail**
- PASS if every captured state is reachable from its own button and each renders a laid-out
  document.
- FAIL if only one state renders, if clicking a button does nothing, if a state renders as escaped
  HTML source, or if the button labels show raw keys such as `state-01-default`.

**Notes**
- If a state's document cannot be read back, the app renders a warning panel titled
  `State body unavailable` reading
  `This state's HTML couldn't be read from the object store right now.` in place of the frame.
  That is a legitimate degraded state, not a crash — record it against the state that showed it and
  carry on with the others.
- Wireframe documents render inside an isolated frame by design, with their own styling. Do not
  raise visual inconsistency between a wireframe and the surrounding app shell.

---

### TC-243 · An artifact owned by an external system of record shows the read-there card

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | Functional |
| Priority | Medium |
| Screen | `/artifacts/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-153 has passed, so at least one artifact has been exported to Confluence and its
  `System of record` chip reads `confluence`.

**Steps**
1. Go to `/artifacts` and click **Preview** on that exported row.
2. Read what renders below the breadcrumb.
3. If a document body renders, note that and read the chip beside the heading.
4. If no body renders, read the card and the banner inside it.
5. Click the system-of-record chip.

**Expected**
- The breadcrumb `Artifacts / Preview` renders either way.
- **If the body could be read back from Confluence**, the screen is the normal preview — heading,
  read-through banner, formatted body, `Version history` card — plus an `Open source` chip beside
  the heading.
- **If the body could not be read back but the external link is known**, the screen instead shows a
  single card carrying the artifact's name and version, its status in words underneath (for example
  `Published`), an `Open source`
  chip on the right, and an info banner reading
  `This artifact is owned by its system of record. Open it there for the live, editable copy.`
- Either way the chip opens the Confluence page in a **new tab** and leaves `/artifacts/:id` on
  screen.
- Nothing on the screen can edit the artifact.

**Pass / Fail**
- PASS if one of the two states above renders cleanly and the chip reaches the right Confluence
  page in a new tab.
- FAIL if the screen shows `Artifact not found` for an artifact that carries an external reference,
  if the chip is missing or dead, or if it navigates in the same tab.

**Notes**
- Which of the two states you get depends on whether the connector can read the page back at that
  moment, not on anything you did. Record which one you saw; both are correct.
- The equivalent card in the design gallery at `/dev/components` names Confluence explicitly
  (`This artifact is owned by Confluence…`) while the live screen says `its system of record`. That
  difference is expected — do not raise it as a copy defect.

---

### TC-244 · The registry has no pagination and no sortable columns

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | UX |
| Priority | Low |
| Screen | `/artifacts` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A project with as many artifacts as the cycle has produced. Run this late, after TS-15, so the
  registry is at its largest.

**Steps**
1. Go to `/artifacts` and scroll to the very bottom of the page.
2. Look for page numbers, a `Next` control, a rows-per-page select, or a "showing n of m" line.
3. Click each of the five column headers — `Artifact`, `Phase`, `Version`, `Status`,
   `System of record` — in turn and watch the row order.
4. Count the rows and compare that with the number of artifacts you expect the project to have
   (one per completed phase, plus one per wireframe and per test-case batch).

**Expected**
- There is **no** pagination control anywhere on the screen. Every artifact in the project renders
  in one list.
- The column headers are plain text: clicking one does nothing, shows no sort arrow, and does not
  reorder the rows.
- The row order is fixed — newest artifact first — and does not change during the case.
- The visible row count equals the project's full artifact count; nothing is cut off.

**Pass / Fail**
- PASS if the whole registry renders in one unpaginated, unsorted list and the headers are inert
  text.
- FAIL if a header *looks* sortable (sort arrow, pointer cursor, hover state) but does not sort, or
  if a pagination control is rendered but inert. An inert control is worse than an absent one —
  raise either as **Low**.
- FAIL if the row count falls short of the project's artifacts, which would mean a silent
  server-side cap.

**Notes**
- The absence of sorting and pagination is the **correct current behaviour** — the whole registry is
  fetched once and filtered in the browser. Do not raise the missing features as functional
  defects.
- If the list has grown long enough to be genuinely hard to work with, that is worth one **Low**
  usability observation against this TC-ID, recorded once with the row count you saw.

---

### TC-245 · `Show the whole registry` clears the filter a gate's Preview link set

| Field | Value |
|---|---|
| Suite | TS-10 Artifacts & Publish |
| Type | Functional |
| Priority | Medium |
| Screen | `/gates` → `/artifacts?run=…` → `/artifacts` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- At least one gate is pending on `/gates`.
- The project has artifacts from **more than one** run, so the whole registry has more rows than the
  one run's view.

**Steps**
1. Go to `/artifacts` with no filter and note the total number of rows.
2. Go to `/gates`, select a pending gate, and click `Preview ↗` in its `Artifact` cell.
3. Read the address bar, the banner above the table, and the number of rows.
4. Click **Show the whole registry** in that banner.
5. Read the address bar, look for the banner, and count the rows again.

**Expected**
- Step 2 opens `/artifacts` with a `run` value in the address.
- Step 3: an info banner titled `Showing part of the registry` reads
  `Everything one run produced, including superseded versions.` and carries a
  **Show the whole registry** button. The table lists only that run's artifacts — fewer rows than
  step 1.
- Step 5: the address bar reads plain `/artifacts` with no `run` value, the
  `Showing part of the registry` banner is gone, and the row count is back to the step 1 total —
  without a page reload.

**Pass / Fail**
- PASS if **Show the whole registry** removes both the scope in the address and the narrowed list,
  in one click.
- FAIL if the address changes but the list stays narrowed to the one run, or if the banner stays on
  screen after the click.

**Notes**
- **Fixed in commit 4ac75f9.** Before it, the click changed the address to `/artifacts` but the
  screen kept showing the one run's artifacts, so the button looked dead.
- If a scoped view matches nothing, the empty state `Nothing matched this filter` carries its own
  **Show the whole registry** button. It must behave the same way — check it if you reach that state.
