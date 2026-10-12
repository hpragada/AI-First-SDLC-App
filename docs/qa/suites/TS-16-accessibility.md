# TS-16 · Accessibility audit, review and conformance statement

The Accessibility screens of a brownfield project: **Pages & audit**, **Review queue** and
**Conformance statement**, plus the defects an audit files on Work Items and the documents it files
in Artifacts. Written from the live audit of 10 Oct 2026 (Bugs S.No 371–389).

**Run these in order.** TC-954 runs the audit that every later case reads. TC-963 onward sign and
export the statement, which cannot be undone without a new signature.

**Set up first.**
- A project with a repository registered, and the companion running on your machine ("Companion:
  Ready").
- The application under test running and reachable, for example Meridian Library at
  `http://localhost:4180`.
- 5 pages listed on Pages & audit, every one in scope.
- Sign in as a user who holds the **QA Lead** role on the project (the reviewer who may sign).

**ID note.** This suite starts at **TC-954**, the next free number after TS-01's TC-953.

---

### TC-954 · An audit runs from start to finish and is named by when it ran

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | Functional |
| Priority | High |
| Screen | `/a11y/pages` |
| Persona | QA Lead |
| Automation | Partly (screen and server tests); this run is live |

**Why this case exists.** Bugs S.No 373, 382, 383.

**Steps**
1. Open **Accessibility → Pages & audit**. Check the address and press **Run audit**.
2. Wait until the audit finishes. A 5-page audit took about 15 minutes on 10 Oct.

**Expected**
- What-will-be-visited box: `Passes 1 · up to 60 pages per pass`.
- When done: `Audit complete · finished 10 Oct 2026, 6:26 PM`, with `started 6:12 PM` under it
  (your own date and time).
- Tiles: `Pages reported 5 · of 5 asked for`, `Problems open`, and `Items to review` with the link
  `in the Review queue →`.
- The Pages box says `5 pages listed`.

**Pass / Fail**
- FAIL if the header shows the start time beside "complete", or any tile reads `Waiting on a person`
  or `Would not open`.

---

### TC-955 · The "Items to review" link opens the Review queue

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | UX |
| Priority | Medium |
| Screen | `/a11y/pages` → `/a11y` |
| Persona | QA Lead |
| Automation | Yes |

**Why this case exists.** Bugs S.No 381. The two "waiting" numbers counted different things
(page elements versus WCAG criteria) but used nearly the same words.

**Steps**
1. After TC-954, click `in the Review queue →`.

**Expected**
- The Review queue opens. With 0 items it says `Nothing is waiting on you`.
- On the Conformance tab, the third tile reads `Criteria to decide`, not `Waiting on you`.

---

### TC-956 · Defect titles name the page and the part of it in words

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | UX |
| Priority | High |
| Screen | `/work-items` |
| Persona | Any |
| Automation | Yes |

**Why this case exists.** Bugs S.No 375, 384.

**Steps**
1. Open **Work Items** and filter to **Defects**.
2. Open one defect.

**Expected**
- Titles read like `Accessibility: Reflow (1.4.10) on the Opening hours page — main content` or
  `… on the Current loans page — row 3 in the loans table`.
- An element with no wording of its own is named in quotes, for example `the "hours-note" element`.
- No title contains a page path (`/loans/current`) or a `#selector`.
- The state on the defect's page matches the board's label (for example `Not started`).
- No "judging" task appears on the board.

---

### TC-957 · The activity log records the audit starting and finishing

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | Functional |
| Priority | Medium |
| Screen | Activity log / database |
| Persona | Dev |
| Automation | Yes |

**Why this case exists.** Bugs S.No 373, 374.

**Steps**
1. After TC-954, read the project's activity log.

**Expected**
- Entries `a11y.audit.started` (listing the pages) and `a11y.audit.finished`.
- The baseline entry is `a11y.baseline_recorded`, not `…published`.

---

### TC-958 · The statement is compiled from a named audit, in one date format

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | UX |
| Priority | Medium |
| Screen | `/a11y/conformance` |
| Persona | QA Lead |
| Automation | Yes |

**Why this case exists.** Bugs S.No 376, 389.

**Steps**
1. Open **Conformance statement** and scroll to **Statement**.

**Expected**
- `Compiled from the audit of 10 Oct 2026, 6:12 PM · Finished 10 Oct 2026, 6:26 PM · Pages 5 of 5`.
- No audit number anywhere. Every date on the Audit and Conformance tabs reads like
  `10 Oct 2026, 6:12 PM`.

---

### TC-959 · Each undecided criterion says why it needs a person

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | UX |
| Priority | Medium |
| Screen | `/a11y/conformance` |
| Persona | QA Lead |
| Automation | Yes |

**Why this case exists.** Bugs S.No 377.

**Steps**
1. Find a row marked `needs your decision`, for example 1.2.2 Captions (Prerecorded).

**Expected**
- Under "What was checked" is a reason, for example `Only a person can judge this criterion — no
  check can observe it. Pick its result in the Conformance column.`
- FAIL if any reason says `Choose a level` (Bugs S.No 392).

---

### TC-960 · During an audit the statement says so and cannot be signed

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | Negative |
| Priority | High |
| Screen | `/a11y/conformance` |
| Persona | QA Lead |
| Automation | Yes |

**Why this case exists.** Bugs S.No 378.

**Steps**
1. Start an audit (TC-954, step 1) and open the Conformance tab while it runs.

**Expected**
- Banner: `An audit is running — these numbers are still coming in`.
- The first tile reads `Checked so far`.
- **Sign** is disabled, with `Sign opens when the audit finishes.`

---

### TC-961 · With nothing checked, the statement asks for an audit first

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | Negative |
| Priority | Medium |
| Screen | `/a11y/conformance` |
| Persona | QA Lead |
| Automation | Yes |

**Why this case exists.** Bugs S.No 379.

**Steps**
1. On a project that has never been audited, open the Conformance tab.

**Expected**
- The signing panel says `Run an audit first`, with no checkboxes and no **Sign** button.

---

### TC-962 · The Sign panel says what signing does

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | UX |
| Priority | Low |
| Screen | `/a11y/conformance` |
| Persona | QA Lead |
| Automation | Yes |

**Why this case exists.** Bugs S.No 388.

**Expected**
- Under **Sign**: `Signing records your name, your role and the exact wording, and publishes the
  accessibility report and baseline it rests on. The statement itself is published when you export
  it.`
- FAIL if it says signing `does not publish anything`.

---

### TC-963 · Signing publishes the report and baseline

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | Functional |
| Priority | High |
| Screen | `/a11y/conformance` → `/artifacts` |
| Persona | QA Lead |
| Automation | Yes; verified live 10 Oct 18:51 |

**Why this case exists.** Bugs S.No 380.

**Steps**
1. Before signing, open **Artifacts**. `Accessibility report` and `Accessibility baseline` read
   **Draft**.
2. Decide every `needs your decision` row, tick both boxes, and press **Sign**.
3. Open **Artifacts** again.

**Expected**
- The statement header reads **Signed**.
- `Accessibility report` and `Accessibility baseline` read **Published**.
- `Accessibility judging — audit of …` still reads **Run output**.

---

### TC-964 · The Export box after signing: Export and View statement only

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | UX |
| Priority | Medium |
| Screen | `/a11y/conformance` |
| Persona | QA Lead |
| Automation | Yes |

**Why this case exists.** Bugs S.No 386, 387.

**Expected**
- The banner `Signed by <name> · QA Lead`.
- Buttons **Export** and **View statement**, and the line `Export downloads the signed statement
  and marks it Published.`
- **View statement** opens the statement's own page in Artifacts.
- FAIL if `Open publish gate` or any sentence about engine or prompt versions appears.

---

### TC-965 · Export publishes the statement and downloads it

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | Functional |
| Priority | High |
| Screen | `/a11y/conformance` → `/artifacts` |
| Persona | QA Lead |
| Automation | Yes; verified live 10 Oct 19:23 |

**Why this case exists.** Bugs S.No 385. Export used to say `Preparing…` and then do nothing.

**Steps**
1. Press **Export**.
2. Open the downloaded file.
3. Open **Artifacts**.

**Expected**
- A file downloads, holding exactly the signed wording.
- The box says `Exported 10 Oct 2026, 7:23 PM` / `The file is in your downloads.`, and the button
  becomes **Export again**.
- In Artifacts, `Accessibility conformance statement` reads **Published**.
- Nothing is sent to Xray or Jira.

**Pass / Fail**
- FAIL if `Preparing…` stays or nothing downloads, or if the publish-to-system-of-record screen opens.

---

### TC-966 · Editing a signed statement clears the signature and the export

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | Negative |
| Priority | Medium |
| Screen | `/a11y/conformance` |
| Persona | QA Lead |
| Automation | Yes |

**Steps**
1. After TC-965, change one word of the statement and press **Save draft**.

**Expected**
- The statement is no longer signed, and the Export box is gone until it is signed again.
- After re-signing, Export reads **Export** (not "Export again") until it is exported again.
- Export again, then check the box: `Exported …` shows the time of **this** export, not the earlier
  one (Bugs S.No 393). In Artifacts the statement reads **Published**.

---

### TC-967 · After signing, the Statement and Export boxes stay on screen

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | Functional |
| Priority | High |
| Screen | `/a11y/conformance` |
| Persona | QA Lead |
| Automation | Yes (server test) |

**Why this case exists.** Bugs S.No 390. Signing used to hide both boxes until the page was
reloaded.

**Steps**
1. On a signed statement, change one word and press **Save draft**. The signature clears.
2. Tick both boxes and press **Sign**. Do not leave the page.

**Expected**
- The **Statement** box stays where it was.
- The Sign box turns into the **Export** box straight away.
- No `You are not the accessibility reviewer` banner appears.

**Pass / Fail**
- FAIL if either box disappears, or only comes back after visiting another page.

---

### TC-968 · While the first audit runs, the statement says so

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | UX |
| Priority | Medium |
| Screen | `/a11y/conformance` |
| Persona | QA Lead |
| Automation | Yes |

**Why this case exists.** Bugs S.No 391.

**Steps**
1. On a project with no finished audit, press **Run audit**, then open the Conformance tab while it
   runs.

**Expected**
- The Statement box shows a blue note: `The first audit is still running` / `This statement will be
  compiled from it once it finishes. Until then, the numbers above are only what has been checked
  so far.`
- On a project that has never been audited and has no audit running, the yellow `No completed audit
  is recorded for this project` warning still shows (TC-961).

---

### TC-969 · The person's pick is a "result", never a "level"

| Field | Value |
|---|---|
| Suite | TS-16 Accessibility |
| Type | UX |
| Priority | Low |
| Screen | `/a11y/conformance` |
| Persona | QA Lead |
| Automation | Yes |

**Why this case exists.** Bugs S.No 392. On this page "level" is WCAG's Level A / AA.

**Expected**
- Third tile: `Pick a conformance result for each one in the table below`, or `Nothing left to
  decide` when it shows 0.
- Every row reason ends `Pick its result in the Conformance column.`
- Sign box: `…and that N results were suggested by the evidence…`
- The table's `Level` column and the title `all 55 Level A & AA criteria` are unchanged.

**Pass / Fail**
- FAIL if `choose a level` or `levels were suggested` appears anywhere on the tab.
