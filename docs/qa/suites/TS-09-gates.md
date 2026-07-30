# TS-09 · Gates

This is the suite that proves the platform's central promise: **nothing reaches a system-of-record
without an approved gate, and only the right person can approve it.** A gate that the wrong role can
decide, or an artifact that publishes without a decision, is a Critical defect every time — no
matter how small the workspace.

**Run these in order.** TC-123 → TC-140 follow one gate from the moment it opens to the moment it is
decided, then branch into role enforcement, rejection and the checklist gates. TC-124 (the empty
state) only holds *before* your first gate opens, so do it first. TC-135 needs a gate you have
already decided, so it must come after TC-127.

**Time budget.** Every case here needs a **completed phase run (20–30 minutes typical, max wait 45
minutes)** to produce the gate it decides. Plan a session as: trigger a phase, work other cases while
it runs, then decide its gate. TC-137 (UX Design) and TC-140 (Deployment) each need their own phase
run, so schedule them on separate sittings.

**Timeout policy.** If a run has not reached `Awaiting gate` within **45 minutes** of the trigger,
record the dependent case **Blocked** with the reason `gate never opened within the 45-minute max
wait` — never Failed. Failed means the app rendered something wrong, not that it was slow. Record
the run id and the last console line.

**`/gates` does not refresh itself.** Unlike the run console, the gates list is **not polled**. Any
step below that says "watch the Pending tab" or "the gate leaves Pending" requires a **manual page
reload** (F5) before you read the result. A gate that is still listed on a stale screen is not a
defect — reload first, then judge.

**One run per WORK ITEM — these cases must run sequentially.** The backend admits a phase trigger
only when the work item has **no** live run of *any* phase. Every gate below is produced by a run on
the same shared epic, so **TC-130, TC-133, TC-137, TC-139 and TC-140 cannot be prepared in
parallel**: finish and decide one gate before triggering the run that produces the next. Attempting
to queue them up gets a red `Trigger failed` banner (TS-07 TC-701), not a second gate. Budget the
session accordingly — five gates is five sequential runs.

**Personas.** You need more than one login. P1 Owner-Admin, P2 `product_owner`, P3 `architect`,
P4 `designer`, P7 `qa_lead`, P9 `devops` and P10 `engineer` are all used below. Switch identity by
logging out and logging back in — never by editing data.

---

### TC-123 · A completed run opens a gate and surfaces it everywhere

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Functional |
| Priority | Critical |
| Screen | `/runs/:id` · `/gates` · `/` (dashboard) |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-124 has already been executed (the empty state only exists before the first gate).
- An Ideation run on the epic `Stripe Webhook Integration` has reached `Awaiting gate`
  (TS-07 TC-103). **Needs a completed run: 20–30 minutes typical, max wait 45 minutes.**

**Steps**
1. On the run console, confirm the status badge reads `Awaiting gate`.
2. Click `Open gate ↗` in the awaiting-gate banner.
3. **Reload the page (F5)** — `/gates` does not poll, so a screen opened before the gate existed
   will not show it.
4. Read the h1 and the badge next to it on `/gates`.
5. Look at the sidebar `Gates` nav item.
6. Go to the dashboard at `http://localhost:5173/` and read the gates tile.

**Expected**
- `Open gate ↗` navigates to `/gates`.
- The h1 reads `Gates` followed by a badge reading `1 pending` (or the true count).
- The sub-heading reads `Approvals awaiting a decision. Only the required role can decide each gate —
  nothing reaches a system-of-record without one.`
- The tabs read `Pending (1)` and `Decided history`.
- The sidebar `Gates` item carries a count badge matching the pending count.
- The dashboard shows a tile with the pending count and the label `Gates need your approval`, with a
  sub-line naming the required role.

**Pass / Fail**
- PASS if the gate appears on `/gates` with a matching count on the sidebar and the dashboard tile.
- FAIL if the run says `Awaiting gate` but no gate is listed, if the counts disagree with the number
  of pending rows, or if `Open gate ↗` leads nowhere.

**Notes**
- Gates are scoped to the selected project. If the count looks wrong, check the project selector
  before raising anything.
- **Reload before judging any count on `/gates`.** The screen has no auto-refresh; it only refetches
  on mount and when the browser window regains focus. A stale count on a screen you left open is
  expected, not a defect.
- The dashboard gates tile is **not** filtered to gates you personally can decide, and it is capped
  at 20. A count that does not match "gates needing me" is a known product defect — do not raise it
  from this case, which only asserts the counts agree with the number of pending rows.

---

### TC-124 · The Gates empty state

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | UX |
| Priority | Medium |
| Screen | `/gates` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- No pending gate exists on the selected project — run this **before** your first phase reaches its
  gate, or after every gate has been decided.

**Steps**
1. Go to `http://localhost:5173/gates`.
2. Read the panel body on the `Pending` tab.
3. Switch to `Decided history` (if you have never decided a gate).

**Expected**
- The `Pending` tab shows the empty state: title `No gates need you`, text
  `Approvals you can act on will appear here and in the notifications bell.`
- No pending table renders.
- The h1 shows `Gates` with **no** pending badge, and the first tab reads `Pending (0)`.
- With no decisions yet, `Decided history` shows `No decided gates yet` /
  `Decisions you make will show up here.`

**Pass / Fail**
- PASS if both empty states render with the exact copy and no rows.
- FAIL if another project's gates are listed, or if a pending badge renders on the h1 while the
  panel shows the empty state.

**Notes**
- Earlier versions of this case also failed on demo rows (`WI-492`, `WI-511`, `PM Approval`). Those
  exist only behind the design-gallery route and cannot render on `/gates`, so the criterion could
  never fire and has been dropped. The leak this case can actually catch is another **project's**
  gates.

---

### TC-125 · The pending approvals table columns

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | UX |
| Priority | High |
| Screen | `/gates` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-123 passed; at least one gate is pending.

**Steps**
1. On `/gates`, `Pending` tab, read the table headers.
2. Read the row for the Ideation gate.
3. Click `Preview ↗` in the `Artifact` cell.
4. Navigate back to `/gates`.

**Expected**
- The headers are exactly `Gate`, `Required role`, `Work item`, `Artifact`.
- The `Gate` cell is a clickable label — for a plan-phase gate it reads `Phase gate`.
- `Required role` shows a chip with the humanised role — `Product Owner` for the Ideation gate.
- `Work item` shows the epic's key and title.
- `Artifact` shows a link reading `Preview ↗` which navigates to the artifacts registry.
- Clicking a row's `Gate` cell selects that gate and highlights the row.

**Pass / Fail**
- PASS if all four headers match and each cell renders as described.
- FAIL if a header is renamed or missing, if `Required role` shows a raw key such as
  `product_owner`, or if `Preview ↗` is not a working link.

**Notes**
- Every plan-phase gate is typed `phase_gate`, so the `Gate` column reads `Phase gate` for all of
  them — it does not name the phase. Identify the gate by the `Work item` and `Required role`
  columns. Merge gates from the build path read `Merge gate`.

---

### TC-126 · The decision card renders for the role holder

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Functional |
| Priority | Critical |
| Screen | `/gates` |
| Persona | P2 Product Owner |
| Automation | No |

**Preconditions**
- The Ideation gate (required role `product_owner`) is pending.
- P2 exists with the `product_owner` role on `Payment Gateway v2`.

**Steps**
1. Log out of P1 and log in as P2 (`qa+<x>.po@edvensoft.com` / `QaTest-2026!`).
2. Go to `/gates` and select the Ideation gate row.
3. Read the card on the right.
4. Click `Preview artifact under review ↗`, then navigate back.
5. Read the buttons and the footer line.

**Expected**
- The card header reads `▲ Phase gate · required role: Product Owner`, followed by the work item's
  key and title as a sub-heading.
- A link reads `Preview artifact under review ↗` and navigates to the artifacts registry
  (`/artifacts`) — the whole list, filtered to nothing.
- A field labelled `Comment (optional)` with the placeholder `Add context for your decision…` is
  present and editable.
- Two enabled buttons are shown: `Approve` (primary) and `Reject` (danger).
- The footer line reads `Decision logged with your role & comment.`
- No read-only banner is shown.

**Pass / Fail**
- PASS if the role holder gets an actionable card with both buttons enabled.
- FAIL if the role holder sees the read-only card, if `Approve` is disabled for a gate with no
  checklist, or if the preview link is missing or dead.

**Notes**
- **`Preview artifact under review ↗` does not open the artifact under review** — it links to the
  registry index, exactly like the `Preview ↗` cell in the pending table (TC-125). The reviewer must
  find the right artifact themselves. That mismatch between the link's copy and its destination is
  a known product defect and is tracked separately: assert only that the link navigates to
  `/artifacts`, and do not raise a duplicate.

---

### TC-127 · Approving with a comment resumes the run to completion

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | E2E |
| Priority | Critical |
| Screen | `/gates` · `/runs/:id` |
| Persona | P2 Product Owner |
| Automation | No |

**Preconditions**
- TC-126 passed; P2 is logged in with the Ideation gate selected.
- Note the run's short reference from `/runs` before approving.

**Steps**
1. In the decision card, type a comment: `Approved — scope matches the epic.`
2. Click `Approve`.
3. **Reload `/gates` (F5)** and read the `Pending` tab. The screen does not poll — without a reload
   the decided gate may still be listed.
4. Open `/runs/{the same run id}` and read the status badge.

**Expected**
- No `Couldn't record the decision` banner appears.
- After the reload the gate has left the `Pending` tab; the pending count on the h1, the sidebar and
  the dashboard all decrease by one.
- The run console for the **same** run leaves `Awaiting gate` and reaches `Completed` — the
  awaiting-gate banner is gone.
- No new run is created.

**Test data**
- Comment: `Approved — scope matches the epic.`

**Pass / Fail**
- PASS if the approval is recorded, the gate clears from `Pending` after a reload, and the run
  reaches `Completed`.
- FAIL if the decision errors, or if the gate is still pending after a reload following a successful
  approve.
- **BLOCKED** (not Failed) if the gate clears correctly but the run has not left `Awaiting gate`
  after a **max wait of 10 minutes**. Reason: `run did not resume within 10 minutes`.

**Notes**
- The run resumes via a workflow signal, so allow a short delay before the console badge updates —
  it is polled, not pushed.

---

### TC-128 · The artifact stops being a draft only once its gate is approved

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Functional |
| Priority | Critical |
| Screen | `/artifacts` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Record the artifact's state on `/artifacts` **before** approving (do this during TC-126).
- TC-127 has approved the Ideation gate.

**Steps**
1. Before the approval, go to `/artifacts` and find the Ideation artifact. Note its `Status` badge
   and whether an `Export` button is offered next to `Preview`.
2. Open the `Filter by status` dropdown and read the options it offers.
3. Approve the gate (TC-127).
4. Return to `/artifacts` and **reload the page**, then find the same artifact again.
5. Read its `Status` badge and its action buttons.
6. Re-open the `Filter by status` dropdown, select `Published`, and confirm the artifact is listed.

**Expected**
- **Before approval:** the artifact's `Status` badge reads `Draft`, and its only action is
  `Preview` — there is no `Export` button.
- Before approval, the `Filter by status` dropdown offers `Status: All` and `Draft`. It does **not**
  offer `Published` yet.
- **After approval:** the same artifact's `Status` badge reads `Published`, and an `Export` button
  is now offered next to `Preview`.
- After approval the dropdown offers `Published` as well, and selecting it lists this artifact.

**Pass / Fail**
- PASS if the badge moves `Draft` → `Published` and the `Export` action appears only after the gate
  is approved.
- FAIL if `Export` is offered while the gate is still pending, or if the artifact reaches
  `Published` with no approved gate (**Critical** — this is the non-negotiable the product exists to
  enforce).

**Notes**
- **There is no observable `Approved` state.** Approving a gate publishes the artifact in the same
  transaction, so it goes straight from `Draft` to `Published`. The `Filter by status` dropdown is
  built from the statuses actually present in the registry, so an `Approved` option can never appear
  — do not look for one, and do not raise its absence.
- The `System of record` cell reads `internal` in a chip for these artifacts, both before and after
  approval — **not** `Platform only`. `Platform only` renders only when an artifact carries no
  system-of-record value at all, which a phase artifact never does. Do not raise the chip as a
  premature publish: `internal` means the platform itself is the system of record. Pushing to an
  external SoR (Confluence) is a separate, explicit action covered by TS-10.
- Publishing to an external system is TS-10. This case only proves that the gate decision is what
  moves the artifact off `Draft`.

---

### TC-129 · Wrong role gets a read-only card — PRD gate (Product Owner)

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Permission |
| Priority | Critical |
| Screen | `/gates` |
| Persona | P10 Engineer |
| Automation | No |

**Preconditions**
- A gate whose required role is `product_owner` is pending (a PRD, Requirements or Ideation run that
  has reached `Awaiting gate`). **Needs a completed run: 20–30 minutes.**
- P10 exists with the `engineer` role on `Payment Gateway v2` and holds no other role.

**Steps**
1. Log out and log in as P10 (`qa+<x>.eng@edvensoft.com` / `QaTest-2026!`).
2. Go to `/gates` and select the pending gate.
3. Read the card on the right.
4. Try to click `Approve`, then try `Reject`.
5. Log out, log back in as P1, and confirm the gate is still pending.

**Expected**
- The card shows a muted header `Phase gate · {work item}` and an info banner titled
  `Awaiting product_owner` whose body reads
  `You don't hold the product_owner role on this project, so this is read-only.`
- `Preview artifact under review ↗` is still available — reading is allowed.
- `Approve` and `Reject` are both present but **disabled**; clicking them does nothing (no request,
  no error banner, no state change).
- Back as P1, the gate is still listed under `Pending` and its run is still `Awaiting gate`.

**Pass / Fail**
- PASS if P10 sees the read-only card, cannot decide, and the gate is unchanged afterwards.
- FAIL — **Critical** — if P10 can approve or reject, or if either button is enabled for them.

**Notes**
- The banner and body quote the **raw** role key (`product_owner`) while the pending table and the
  decision card use the humanised label (`Product Owner`). That inconsistency is expected today; log
  it as Low if you want it fixed, but it is not this case's pass condition.

---

### TC-130 · Wrong role gets a read-only card — Architecture gate (Architect)

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Permission |
| Priority | Critical |
| Screen | `/gates` |
| Persona | P2 Product Owner |
| Automation | No |

**Preconditions**
- An Architecture run on the epic has reached `Awaiting gate`, so a gate with required role
  `architect` is pending. **Needs a completed run: 20–30 minutes typical, max wait 45 minutes.**
- **Sequential only.** Only one run may be live per work item, so the epic's previous gate (TC-127's
  Ideation gate) must already be **decided** before you can trigger Architecture. Do not attempt to
  prepare this gate alongside TC-133/TC-137/TC-139/TC-140 — they queue behind each other.
- P2 holds `product_owner` and P3 holds `architect` on the project.

**Steps**
1. Log in as P2 (the Product Owner — the *wrong* role for this gate).
2. Go to `/gates` and select the Architecture gate row.
3. Read the card.
4. Log out and log in as P3 (`qa+<x>.arch@edvensoft.com`).
5. Select the same gate and read the card.

**Expected**
- As P2: the read-only card is shown with the banner `Awaiting architect` /
  `You don't hold the architect role on this project, so this is read-only.` and disabled `Approve`
  and `Reject` buttons — even though P2 could decide the *product_owner* gates.
- As P3: the actionable card is shown with header `▲ Phase gate · required role: Architect`, an
  editable `Comment (optional)` field and enabled `Approve` / `Reject` buttons.

**Pass / Fail**
- PASS if the same gate is read-only for the Product Owner and actionable for the Architect.
- FAIL — **Critical** — if P2 can decide the Architecture gate, or if P3 (the correct role holder)
  is locked out of it.

**Notes**
- Running this alongside TC-129 proves the rule is per-gate, not "some roles can decide everything".

---

### TC-131 · A tenant admin can decide any gate

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Permission |
| Priority | High |
| Screen | `/gates` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A pending gate whose required role P1 does **not** personally hold as their project role — e.g.
  the Architecture gate (`architect`) or a UX Design gate (`designer`).
- P1 is the signup account and is therefore a tenant admin.

**Steps**
1. Log in as P1.
2. Go to `/gates` and select the gate whose required role is not P1's project role.
3. Read the card.
4. Add the comment `Admin approval — role holder unavailable.` and click `Approve`.
5. Check the `Decided history` tab.

**Expected**
- P1 sees the **actionable** card (`▲ Phase gate · required role: {Role}`), not the read-only
  banner, even though the gate requires a role they do not hold.
- The approval succeeds with no `Couldn't record the decision` banner.
- The gate moves out of `Pending` and appears on `Decided history` with `Approved` and `You` as the
  approver.

**Pass / Fail**
- PASS if the tenant admin can decide a gate for a role they do not hold.
- FAIL if the tenant admin gets the read-only card, or if the approve attempt errors with a role
  message.

**Notes**
- This is intended behaviour: the required role **or** the project `admin` role **or** any tenant
  admin may decide. It is a deliberate escape hatch, not a permission hole.

---

### TC-132 · A project `admin` is shown the read-only card for another role's gate

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Permission |
| Priority | High |
| Screen | `/gates` |
| Persona | Any (a project-admin account that is not a tenant admin) |
| Automation | No |

**Preconditions**
- A pending gate on `Payment Gateway v2` with a required role such as `architect`.
- An account that holds the `admin` role **on the project** but is **not** a tenant admin: invite
  `qa+<x>.projadmin@edvensoft.com` from `/admin/users`, grant it the `Admin` role on
  `Payment Gateway v2`, and do not make it a workspace admin. Accept the invite and set the password
  `QaTest-2026!`.

**Steps**
1. Log out and log in as the project-admin account.
2. Go to `/gates` and select the pending gate.
3. Read the card on the right.
4. Try to click `Approve`, then try `Reject`.
5. Log out, log back in as P1, and confirm the gate is still pending.

**Expected**
- The card shows a muted header `Phase gate · {work item}` and an info banner titled
  `Awaiting {required role key}` (e.g. `Awaiting architect`) whose body reads
  `You don't hold the {role} role on this project, so this is read-only.`
- `Preview artifact under review ↗` is still available.
- `Approve` and `Reject` are both present but **disabled**; clicking them does nothing — no request,
  no error banner, no state change.
- Back as P1, the gate is still listed under `Pending`.

**Pass / Fail**
- PASS if the project admin is shown the read-only card and cannot decide from the browser.
- FAIL if the buttons are **enabled** for the project admin and pressing one produces a role error
  banner — a control that is offered and then refused is worse than one that is withheld.

**Notes**
- **This case asserts the app's current, deliberate-looking-but-wrong behaviour, and the underlying
  gap is already tracked — do not raise a duplicate.** The backend permits a project `admin` to
  decide any gate on their project; the Gates screen decides which card to render from "tenant admin
  **or** exactly the required role", with no project-admin branch. So a permitted user is blocked in
  the browser. It is a **Medium** UI defect, not a security issue — nothing extra is allowed through.
- This case was previously written to expect the actionable card. That state cannot be reached, so
  the case could only ever produce a wrong verdict; it now asserts the observed behaviour and pins
  it, so the day the project-admin branch is added the case fails and gets updated.
- The escape hatch that *does* work today is a **tenant** admin (TC-131), not a project admin.

---

### TC-133 · Rejecting a gate with a comment fails the run

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Functional |
| Priority | Critical |
| Screen | `/gates` · `/runs/:id` |
| Persona | P2 Product Owner |
| Automation | No |

**Preconditions**
- A pending `product_owner` gate on the epic (a Requirements or PRD run that has reached
  `Awaiting gate`). **Needs a completed run: 20–30 minutes typical, max wait 45 minutes.**
- **Sequential only.** The epic's previous gate must already be decided before this run can be
  triggered — only one run may be live per work item.
- Note the run's short reference from `/runs` before deciding.

**Steps**
1. Log in as P2 and select the gate on `/gates`.
2. Type the comment `Rejected — the retry policy for failed webhooks is missing.`
3. Click `Reject`.
4. Open `/runs/{the same run id}`.
5. Read the status badge and the banner.

**Expected**
- The rejection is recorded with no `Couldn't record the decision` banner, and after a **page
  reload** the gate has left the `Pending` tab and appears on `Decided history` badged `Rejected`.
- The run console badge reads `Failed`.
- A red banner titled `Gate rejected` reads `The gate was rejected. Re-trigger to try again.`
- On `/artifacts`, the artifact from that run still badges `Draft` and offers only `Preview` — no
  `Export` action, and it never reaches `Published`.

**Test data**
- Comment: `Rejected — the retry policy for failed webhooks is missing.`

**Pass / Fail**
- PASS if the rejection is recorded and the run shows `Failed` with the `Gate rejected` banner.
- FAIL if the run completes anyway, if the artifact reaches `Published` or gains `Export`, or if the
  rejection errors.
- **BLOCKED** (not Failed) if the rejection records cleanly but the run console has not reached
  `Failed` after a **max wait of 10 minutes**.

**Notes**
- Rejection is **never** blocked by unmet criteria — only Approve is. Rejecting a checklist gate
  with nothing ticked is valid and should succeed.

---

### TC-134 · After a rejection the work item is still workable and re-triggering makes a new run

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | E2E |
| Priority | Critical |
| Screen | `/runs` · `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-133 passed; the epic has a rejected run showing `Failed` / `Gate rejected`.
- The companion is online.
- **Budget 20–30 minutes** if you let the new run finish; the assertions below need only the first
  minute.

**Steps**
1. Log in as P1 and go to `/work-items`. Confirm the epic is still listed and openable.
2. Go to `/runs` and select the epic. Note the rejected run's short reference.
3. Click `▶ {the rejected phase}`.
4. In the `Re-run {Phase}?` modal, click `Re-run phase`.
5. Read the Runs table.

**Expected**
- The epic is still open and editable — a rejection does not archive or lock the work item.
- The `Phase triggered` banner appears.
- The Runs table shows **two** rows for that phase: the rejected one (still `Failed`) and a new one
  with a different `Run` reference and a newer `Created` time.
- The old run is preserved in history — it is not overwritten or deleted.

**Pass / Fail**
- PASS if a new run is created and the rejected run remains visible in the table.
- FAIL if the phase cannot be re-triggered after a rejection, or if the rejected run disappears.

---

### TC-135 · An already-decided gate cannot be decided again

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Negative |
| Priority | High |
| Screen | `/gates` |
| Persona | P2 Product Owner |
| Automation | No |

**Preconditions**
- TC-127 approved a gate as P2, and TC-133 rejected one. Both are now on `Decided history`.
- P2 is logged in.

**Steps**
1. On `/gates`, open the `Decided history` tab and note the approved gate's row: its `Decision`
   badge, `By` value and `When` timestamp. Write the timestamp down.
2. Return to the `Pending` tab and confirm the decided gate is **not** listed there, and that no
   decision card for it can be selected.
3. Open a **second browser tab** on `/gates` and let it load. Confirm the decided gate is absent from
   its `Pending` tab too.
4. In the first tab, reload the page (F5) and re-read both tabs.
5. Log out, log back in as P1, and read `Decided history` again.

**Expected**
- A decided gate never appears on the `Pending` tab, in either browser tab, and has no decision card
  — so there is no `Approve` or `Reject` control to press for it anywhere in the product.
- The `Decided history` row is unchanged across the reload: same `Decision` badge, same `By`, same
  `When` timestamp you wrote down.
- Viewed by P1 the same row still shows the original decision, with P2 named in `By`.

**Pass / Fail**
- PASS if the decided gate is absent from `Pending` everywhere and its history row is stable across
  a reload and an identity change.
- FAIL if the gate reappears under `Pending`, if a decision card for it can still be opened, or if
  the recorded decision, approver or timestamp changes.

**Notes**
- This case was previously written around a "stale tab" — leave a tab open from before the decision
  and press `Approve` again to provoke `approval already decided: approved`. **That path is not
  reachable from the browser:** the gates list refetches whenever a tab regains focus, so the card
  is gone before you can click it. The re-decide guard still exists in the backend, but there is no
  UI route to it, so the case now asserts the property a tester *can* verify — a decided gate
  permanently leaves `Pending` and its record is immutable.
- Consequently there is no expectation of a `Couldn't record the decision` banner here. If you do
  somehow see one, capture the exact message; it would mean the list is serving a decided gate as
  pending, which is the FAIL above.

---

### TC-136 · The Decided history tab

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | UX |
| Priority | Medium |
| Screen | `/gates` |
| Persona | P2 Product Owner |
| Automation | No |

**Preconditions**
- At least one approved gate (TC-127) and one rejected gate (TC-133) exist, both decided by P2.

**Steps**
1. Log in as P2 and go to `/gates`.
2. Click the `Decided history` tab.
3. Read the headers and the rows.
4. Log out, log in as P1, and read the same tab.

**Expected**
- The headers are exactly `Gate`, `Work item`, `Decision`, `By`, `When`.
- The approved gate shows a green `Approved` badge; the rejected gate shows a red `Rejected` badge.
- Viewed by P2 (who made both decisions), the `By` column reads `You` for both rows.
- Viewed by P1, the same rows show P2's name (or a short identifier) in `By`, not `You`.
- `When` shows a formatted local date and time, not a raw ISO string.

**Pass / Fail**
- PASS if the five headers match, the decision badges are correct, and `You` renders only for the
  viewer's own decisions.
- FAIL if a header is renamed, if `You` shows for someone else's decision, or if decided gates are
  missing from the tab.

---

### TC-137 · The UX Design gate blocks approval until all 9 WCAG criteria are ticked

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Functional |
| Priority | Critical |
| Screen | `/gates` |
| Persona | P4 Designer |
| Automation | No |

**Preconditions**
- A UX Design run on the epic has reached `Awaiting gate`, so a gate with required role `designer`
  is pending. **Needs its own completed run: 20–30 minutes typical, max wait 45 minutes.**
- **Sequential only.** The epic's previous gate must already be decided before the UX Design run can
  be triggered — only one run may be live per work item. This gate cannot be prepared in parallel
  with TC-130/TC-133/TC-139/TC-140.
- P4 exists with the `designer` role on `Payment Gateway v2`.

**Steps**
1. Log in as P4 (`qa+<x>.design@edvensoft.com`) and go to `/gates`.
2. Select the UX Design gate and read the `Required checklist` block.
3. Count the criteria and read the counter.
4. Read the `Approve` button without ticking anything.
5. Tick eight of the nine criteria and re-read the button.
6. Tick the ninth criterion and re-read the button.
7. Add the comment `A11y reviewed against WCAG 2.1 AA.` and click `Approve`.

**Expected**
- The card shows a `Required checklist` block with a counter reading `0 of 9 met`, and **nine**
  criteria, each marked with `*` because all are required — including
  `Contrast (minimum): text ≥ 4.5:1, large text & UI ≥ 3:1`,
  `All functionality is keyboard operable` and
  `Components expose name, role, and value (ARIA)`.
- With nothing ticked, `Approve` is **disabled** and its label reads `Approve (9 remaining)`.
- With eight ticked, the counter reads `8 of 9 met` and the button reads `Approve (1 remaining)`,
  still disabled.
- With all nine ticked, the counter reads `9 of 9 met` and the button becomes enabled and reads
  plainly `Approve`.
- Clicking `Approve` records the decision; the gate leaves `Pending` and the run resumes.
- `Reject` stays enabled the whole time, at every tick count.

**Test data**
- Comment: `A11y reviewed against WCAG 2.1 AA.`

**Pass / Fail**
- PASS if approval is impossible until all nine required criteria are ticked, and possible
  immediately after.
- FAIL — **Critical** — if `Approve` is enabled with a required criterion unticked, if fewer than
  nine criteria are listed, or if the counter disagrees with the ticks.

**Notes**
- Nothing is persisted by a blocked approve attempt: the gate stays pending and your ticks are not
  saved if you navigate away. Re-ticking after a reload is expected, not a bug.

---

### TC-138 · The standalone criteria-gate screen

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | UX |
| Priority | Low |
| Screen | `/gates/:id/criteria` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Logged in as P1 with a project selected.

**Steps**
1. Look for any link in the product that leads to a gate's own criteria page — check `/gates`
   (the `Gate` cell, the decision card), the dashboard tile, the work-item detail and the
   notifications bell.
2. Go directly to `http://localhost:5173/gates/00000000-0000-0000-0000-000000000000/criteria`.
3. Read the breadcrumb and the banner.

**Expected**
- Step 1 finds **no** link anywhere in the product that leads to `/gates/:id/criteria`.
- For an id that does not exist, the screen shows a red banner titled `Gate not found` reading
  `This approval doesn't exist or you don't have access to it.` inside the normal app shell — no
  white screen and no raw error payload.
- **No breadcrumb is rendered on the not-found screen.** The `Gates / Criteria gate` breadcrumb
  appears only when a real gate loads, so on this route there is no in-page way back to `/gates` —
  the sidebar is the only route out.

**Pass / Fail**
- PASS if the route renders the `Gate not found` banner cleanly inside the app shell.
- FAIL if the page crashes, spins forever, or shows a raw 404 payload.

**Notes**
- The missing breadcrumb on the not-found branch is **expected today** and is tracked separately as
  a Low navigability defect — do not raise a duplicate. An earlier version of this case asserted the
  breadcrumb was present, which would have produced a false failure.
- There is **no in-app link to `/gates/:id/criteria` anywhere in the product** — it can only be
  reached by typing a gate id into the address bar, which a tester has no UI route to obtain. Log
  this as a **Low** navigability defect. It is not a blocker: the same checklist is fully usable
  inline on the `/gates` decision card, which is what TC-137, TC-139 and TC-140 exercise.
- When it *is* reached with a real gate id it renders the h1 `Gate criteria checklist`, the
  sub-heading `A quality gate: approval stays disabled until every required criterion is ticked.`,
  a counter `{met} of {total} criteria met`, and on decision either
  `Approved` / `The gate was approved — the run resumes.` or
  `Rejected — sent back for rework`. A gate with no checklist shows
  `This gate has no checklist — decide directly.`

---

### TC-139 · The Testing gate carries one platform-derived condition

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Negative |
| Priority | High |
| Screen | `/gates` |
| Persona | P7 QA Lead |
| Automation | No |

**Preconditions**
- A Testing run on the epic has reached `Awaiting gate`, so a gate with required role `qa_lead` is
  pending. **Needs its own completed run: 20–30 minutes typical, max wait 45 minutes.**
- **Sequential only.** The epic's previous gate must already be decided before the Testing run can
  be triggered — only one run may be live per work item. This gate cannot be prepared in parallel
  with TC-130/TC-133/TC-137/TC-140.
- P7 exists with the `qa_lead` role on `Payment Gateway v2`.

**Steps**
1. Log in as P7 (`qa+<x>.qa@edvensoft.com`) and go to `/gates`.
2. Select the Testing gate and read the `Required checklist` block.
3. If the condition shows as unmet, tick it and click `Approve`.
4. Read any error banner.

**Expected**
- The checklist has exactly **one** required item:
  `No failing blocking test — every failing test's defect is resolved, or the test is quarantined as
  flaky`, with a counter reading `0 of 1 met` or `1 of 1 met`.
- If the work item has open test defects, `Approve` is blocked. Ticking the item by hand does
  **not** unlock it: the attempt returns the banner `Couldn't record the decision` whose message
  names the unmet condition (`no_blocking_test_failures`) and lists the open test defects.
- If the work item has no open test defects, the condition is already satisfied and `Approve`
  succeeds.
- The gate stays pending after a blocked attempt — nothing is recorded.

**Pass / Fail**
- PASS if the single condition renders and a reviewer's tick cannot substitute for real state when
  test defects are open.
- FAIL — **Critical** — if ticking the box lets a gate through while blocking test defects are still
  open on the work item.

**Notes**
- This condition is **derived**: the platform recomputes it from live state at decide time, so a
  reviewer's tick is deliberately ignored. Seeing your tick "not take" is the feature working.
- The blocked approve is the assertion here. If the run produced no failing tests, the condition will
  simply already be met — record that outcome and note that the negative half could not be exercised
  on this run.

---

### TC-140 · The Deployment gate carries 7 readiness criteria

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Functional |
| Priority | High |
| Screen | `/gates` |
| Persona | P9 DevOps |
| Automation | No |

**Preconditions**
- A Deployment run on the epic has reached `Awaiting gate`, so a gate with required role `devops` is
  pending. **Needs its own completed run: 20–30 minutes typical, max wait 45 minutes**, and it is
  late in the lifecycle — expect to reach it only in a full TS-15 pass.
- **Sequential only.** The epic's previous gate must already be decided before the Deployment run
  can be triggered — only one run may be live per work item.
- P9 exists with the `devops` role on `Payment Gateway v2`.

**Steps**
1. Log in as P9 (`qa+<x>.devops@edvensoft.com`) and go to `/gates`.
2. Select the Deployment gate and read the `Required checklist` block.
3. Count the criteria and read the counter and the `Approve` button label.
4. Tick six of the seven and re-read the button.
5. Tick the seventh, add the comment `Release readiness attested.` and click `Approve`.

**Expected**
- The checklist shows **seven** required criteria, each marked `*`, including
  `Rollback procedure is documented and tested`,
  `On-call engineer designated and available; deployment window communicated to stakeholders` and
  `Release notes and the version-specific rollback runbook are registered`.
- With nothing ticked the counter reads `0 of 7 met` and `Approve` is disabled reading
  `Approve (7 remaining)`.
- With six ticked it reads `6 of 7 met` / `Approve (1 remaining)`, still disabled.
- With all seven ticked `Approve` enables and the decision is recorded; the gate leaves `Pending`.

**Test data**
- Comment: `Release readiness attested.`

**Pass / Fail**
- PASS if all seven criteria render as required and approval unlocks only when every one is ticked.
- FAIL — **Critical** — if the deployment gate can be approved with an unticked readiness item.

**Notes**
- These items are reviewer-attested, not derived — the platform cannot compute on-call availability.
  Ticking them is the human's attestation, which is the intended design.
- Deployment is a planning/document-producing phase today: approving the gate does **not** perform a
  real deploy. Do not expect a deployment to happen, and do not raise its absence here.

---

### TC-901 · The Task Breakdown gate reviews every task's repository assignment

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Functional |
| Priority | Critical |
| Screen | `/gates` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- `Payment Gateway v2` has **two or more repositories** connected on `/repositories` — this panel
  renders only on a multi-repo project.
- A Task Breakdown run on the epic has reached `Awaiting gate`, so a gate with required role
  `tech_lead` is pending, and it produced child tasks. **Needs its own completed run: 20–30 minutes
  typical, max wait 45 minutes.**
- **Sequential only** — the epic's previous gate must be decided first.
- You are logged in as P1 (a tenant admin, so the actionable card renders regardless of role).

**Steps**
1. Go to `/gates` and select the Task Breakdown gate row (the `Gate` cell reads `Phase gate`;
   identify it by `Required role: Tech Lead`).
2. Read the card. Between the checklist area and the `Comment (optional)` field, find the
   repository-assignment review block.
3. Read the proposed tasks listed there and the repository each has been assigned.
4. Find a task the planner flagged as low confidence and read the banner above the reassurance line.
5. Change one task's repository to a different connected repo using its control.
6. Read the line directly above `Comment (optional)`.
7. Approve the gate, then go to `/work-items` and open the task you re-pointed in step 5.

**Expected**
- The review block lists the proposed child tasks, each showing the repository the planner chose.
- If any task is low-confidence and not yet confirmed, an info banner titled
  `{n} task(s) the planner wasn't sure about` is shown, offering a `confirm all as-is` control and
  stating `You can still approve — this is a heads-up, not a block.`
- The reassurance line immediately above the comment field reads
  `Approving confirms these repository assignments.`
- `Approve` is **not** blocked by unreviewed assignments — the banner is advisory only.
- After approval, the task you re-pointed in step 5 shows the repository you chose, not the
  planner's original suggestion.

**Pass / Fail**
- PASS if the review block renders on the Task Breakdown gate, an override changes that task's
  repository, and approving commits the assignments shown.
- FAIL — **Critical** — if approving sends a task to a repository other than the one displayed on
  the card at the moment you approved, or if an override is silently discarded.

**Notes**
- **This block appears on the Task Breakdown gate only.** It is deliberately suppressed on merge
  gates and every later phase gate, even though proposed sibling tasks keep their assignments. If
  you see it on another phase's gate, that is a real defect — capture which gate.
- On a **single-repo** project the block never renders and there is nothing to choose. Record this
  case **Blocked** with the reason `project is single-repo` rather than Failed if you cannot connect
  a second repository.
- The risk this case exists for is silent: approving commits every assignment on screen, so a wrong
  default that nobody read still sends work to the wrong repository. Read the list before approving.

---

### TC-902 · The work-item screen offers a second Approve/Reject with no role check

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Permission |
| Priority | Critical |
| Screen | `/work-items/:id` |
| Persona | P10 Engineer |
| Automation | No |

**Preconditions**
- A pending gate on the epic whose required role is **not** `engineer` — e.g. the Ideation gate
  (`product_owner`). **Needs a completed run: 20–30 minutes typical, max wait 45 minutes.**
- P10 exists with the `engineer` role on `Payment Gateway v2` and holds no other role.
- TC-129 has already confirmed that P10 gets the **read-only** card for this same gate on `/gates`.
  Run that first — the contrast is the point of this case.

**Steps**
1. Log out and log in as P10 (`qa+<x>.eng@edvensoft.com` / `QaTest-2026!`).
2. Go to `/gates`, select the pending gate, and confirm the buttons are **disabled** there.
3. Go to `/work-items`, open the epic `Stripe Webhook Integration`, and look at the right-hand
   column.
4. Read the card headed `Awaiting your decision` and its buttons.
5. Look for a comment field on that card.
6. Click `Approve`.
7. Reload the page, then go to `/gates` and open `Decided history`.

**Expected**
- On the epic screen a card is shown with the header
  `▲ Phase gate · required role: product_owner` — note the **raw** role key here, where `/gates`
  humanises it — and the heading `Awaiting your decision`.
- Both `Approve` and `Reject` are **enabled** for P10, even though the same gate is read-only for
  them on `/gates`.
- **No comment field is offered** on this card, yet the footer line reads
  `Decision is logged with your role & comment.`
- Clicking `Approve` records the decision: after the reload, the gate is gone from `Pending` and
  appears on `Decided history` badged `Approved`, with the Engineer as the approver.

**Pass / Fail**
- PASS if the decision is recorded from this screen with an empty comment.
- FAIL if the click white-screens, or if the gate stays pending with no error shown at all (a
  silently swallowed decision).

**Notes**
- **Read this before you raise anything.** This case deliberately asserts behaviour that is wrong by
  design intent: the inline card applies **no `canDecide` check**, so it is a second gate-decision
  path that bypasses the role enforcement `/gates` implements, and it promises a comment it never
  collects. Both are already logged as product defects. **Do not raise a duplicate** — the value of
  this case is to detect the day the role check is added or the card is removed.
- Whether the backend also lets the decision through depends on its own role check. If the approval
  is **refused**, that is a better outcome than this case's Expected, not a failure: record what you
  saw, note that the backend held the line, and flag it to the plan owner.
- The gate you spend here is consumed. Sequence this case where losing that gate does not strand
  TC-127 or TC-133, or use a gate you no longer need.

---

### TC-903 · The merge gate requires the Reviewer role (08 Code Review)

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Permission |
| Priority | High |
| Screen | `/gates` |
| Persona | P10 Engineer · a `reviewer` account |
| Automation | No |

**Preconditions**
- An **Implementation** run on a task under the epic has run its build and reached `Awaiting gate`,
  opening a merge gate. **Needs a build-tier run — allow 45 minutes, max wait 90 minutes** (a build
  clones a repo, runs the code-review loop and opens a PR, so it is slower than a plan phase). If it
  has not opened a gate by then, record **Blocked**.
- The project has a repository connected and the companion is online.
- An account holding the `reviewer` role on `Payment Gateway v2` exists — invite
  `qa+<x>.reviewer@edvensoft.com` from `/admin/users`, grant it the `Reviewer` role, accept the
  invite and set the password `QaTest-2026!`.
- P10 holds `engineer` only.

**Steps**
1. Log in as P10 and go to `/gates`.
2. Find the new gate and read its `Gate` and `Required role` cells.
3. Select it and read the card.
4. Log out and log in as the reviewer account.
5. Select the same gate and read the card.

**Expected**
- The gate's `Gate` cell reads `Merge gate` — not `Phase gate` — and `Required role` shows the chip
  `Reviewer`.
- As P10: the read-only card is shown, with the banner `Awaiting reviewer` /
  `You don't hold the reviewer role on this project, so this is read-only.` and both buttons
  disabled.
- As the reviewer: the actionable card is shown, headed
  `▲ Merge gate · required role: Reviewer`, with an editable `Comment (optional)` field and enabled
  `Approve` / `Reject` buttons.

**Pass / Fail**
- PASS if the merge gate is labelled `Merge gate`, requires `Reviewer`, and is actionable only for
  the reviewer (and admins).
- FAIL — **Critical** — if an Engineer can decide the merge gate, or if the reviewer is locked out
  of it.

**Notes**
- The 08 Code Review phase is **never triggered on its own** — it runs inside the build loop, and
  the human checkpoint it produces is this merge gate, which is why its `reviewer` role only ever
  surfaces here. Do not look for a `▶ Code Review` button on `/runs` and do not raise its absence.
- If the merge gate card carries a warning banner titled
  `Merge paused — conflict needs resolving`, the merge hit a conflict on an earlier approval. That
  is a different state — record it in the notes and it does not change this case's assertions, which
  are about the label and the role only.

---

### TC-904 · Rejecting the UX Design criteria gate is never blocked by unticked criteria

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Negative |
| Priority | High |
| Screen | `/gates` |
| Persona | P4 Designer |
| Automation | No |

**Preconditions**
- A pending UX Design gate (required role `designer`) with its 9-item WCAG checklist —
  TC-137's precondition. **Needs its own completed run: 20–30 minutes typical, max wait 45 minutes.**
- **Sequential only**, and this case **consumes the gate**: run it on a UX Design gate you are
  willing to lose, or run TC-137 first, re-trigger UX Design, and use the second gate here.
- Note the run's short reference from `/runs` before deciding.

**Steps**
1. Log in as P4 and select the UX Design gate on `/gates`.
2. Confirm the counter reads `0 of 9 met` and `Approve` is disabled reading `Approve (9 remaining)`.
3. Confirm `Reject` is **enabled** with nothing ticked.
4. Type the comment `Rejected — secondary button contrast is 3.1:1 on white.`
5. Click `Reject`.
6. Reload `/gates` and read both tabs.
7. Open `/runs/{the same run id}` and read the badge and banner.
8. Re-trigger UX Design from `/runs` and, once the new run reaches its gate, select it and read the
   checklist counter.

**Expected**
- `Reject` is enabled at zero ticks — the checklist blocks `Approve` only.
- The rejection is recorded with no `Couldn't record the decision` banner.
- After the reload the gate has left `Pending` and appears on `Decided history` badged `Rejected`.
- The run console badge reads `Failed` with the red banner `Gate rejected` /
  `The gate was rejected. Re-trigger to try again.`
- The re-triggered run opens a **fresh** gate whose counter reads `0 of 9 met` — no tick from the
  rejected gate carries over.

**Pass / Fail**
- PASS if a rejection with nothing ticked succeeds and the replacement gate starts from a clean
  checklist.
- FAIL if `Reject` is disabled while criteria are unmet, if the rejection errors, or if the new
  gate's checklist arrives pre-ticked from the rejected one.

**Notes**
- Ticks made on the `/gates` card are **not persisted** while the gate is pending — navigating away
  and back loses them (TC-137's note). This case checks the stronger property: they do not survive
  the decision either.
- A rejected gate is gone for good; the only route forward is a re-trigger, which is why step 8 is
  part of the case rather than a separate one.

---

### TC-905 · Rejecting a build-tier merge gate stops the merge and leaves the PR open

| Field | Value |
|---|---|
| Suite | TS-09 Gates |
| Type | Functional |
| Priority | Critical |
| Screen | `/gates` · `/runs/:id` · `/work-items/:id` |
| Persona | a `reviewer` account |
| Automation | No |

**Preconditions**
- A pending **merge gate** on an Implementation run — TC-903's precondition. **Max wait 90 minutes**
  for the build to open the gate; record **Blocked** beyond that.
- You are logged in as the `reviewer` account (or P1, a tenant admin).
- Note the run's short reference and the task's work-item id before deciding.
- **This consumes the merge gate and abandons the build.** Schedule it after TC-903, and do not run
  it on a build you still need for TS-15.

**Steps**
1. On `/gates`, select the merge gate.
2. Type the comment `Rejected — error handling on the webhook retry path is missing.`
3. Click `Reject`.
4. Reload `/gates` and read both tabs.
5. Open `/runs/{the same run id}` and read the status badge and banner.
6. Open the task on `/work-items/:id` and read its `State`.
7. Go to `/artifacts` and find the artifacts produced by that run.

**Expected**
- The rejection is recorded with no `Couldn't record the decision` banner; after the reload the gate
  is on `Decided history` badged `Rejected`.
- The run console badge reads `Failed` with the red banner `Gate rejected` /
  `The gate was rejected. Re-trigger to try again.`
- The task's `State` returns to `In progress` — a rejected merge does **not** mark the task done and
  does **not** archive or lock it.
- **None** of that run's artifacts reach `Published`; they still badge `Draft` and offer no `Export`
  action. In particular the `code` artifact is not published.

**Pass / Fail**
- PASS if the rejection is recorded, the run shows `Failed` / `Gate rejected`, the task returns to
  `In progress`, and no artifact from the run is published.
- FAIL — **Critical** — if any artifact from the run becomes `Published`, or if the task is marked
  done, after a rejected merge gate.

**Notes**
- **The pull request is deliberately left open on the remote.** A rejection ends the build and
  unwinds the *platform* state; it does not close, revert or delete the branch or PR — the reviewer
  is expected to handle the PR in the host. Do not raise the still-open PR as a defect from this
  case. If you want to confirm it, open the PR link from the run's artifacts.
- This is the rejection path with the widest blast radius: a plan-tier rejection only strands a
  document, while this one has already pushed a branch and opened a PR. The assertion that matters
  most is the last one — nothing publishes.
