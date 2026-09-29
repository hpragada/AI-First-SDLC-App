# TS-15 · End-to-End Greenfield Lifecycle

This suite is the product's whole promise in one thread: a brand-new workspace goes from signup to a
published, traceable artifact, through every gate, with the right role deciding each one. Each case
here is a **multi-screen journey**, not a single-screen check — expect 30–90 minutes per case, most
of it waiting on real agent runs. **Owner: Tester C.**

**Run these in order, and in as few sittings as possible.** Every case names the case it continues
from in its Preconditions: TC-204 assumes TC-203 passed, TC-208 assumes TC-207 produced child tasks,
and so on. If an earlier case fails, mark the dependants **Blocked** with that DEFECT-ID rather than
Fail. The plan's exit criteria require at least one complete pass of TC-201 → TC-212.

---

## Three rules that apply to every case in this suite

### 1 · Checkpoints — write the ids down as you go

These cases run 40–90 minutes each and there is no way to reconstruct where you were from the
screen alone. Every case has a **Checkpoint** step that names exactly what to record, and a
**Resume point** telling you where to restart if you are interrupted. Keep one scratch note per
cycle with these fields and fill them in as you go:

| Field | Filled in by |
|---|---|
| Workspace / project / repo | TC-201 |
| Persona logins confirmed working | TC-202 |
| Epic id — `Stripe Webhook Integration` | TC-203 |
| Run id per phase (ideation → deployment) | TC-203 … TC-210 |
| First child task id | TC-207 |
| Test case work item ids | TC-209 |
| PRD artifact id | TC-211 |
| Second epic id — `Refunds API` | TC-212 |

**Never re-trigger a phase to "get back to where you were."** A re-trigger replaces that phase's
artifacts and costs another 20–30 minutes. If you lost your place, open `/runs`, select the work
item, and read the run history — it tells you which phases have run and their status.

### 2 · Timing — every run-dependent step has a max wait

Each case states a **max wait** for its runs. If a run has not reached the state the case names
within that window, record the case **Blocked** with the run id — **never Fail**. "Fail" is for the
app doing the wrong thing, not for the app being slow. A silent console is not evidence of a hang
(`docs/TESTING_PHASE_BUGS_HANDOFF.md` Bug 3), so "still running" and "hung" genuinely cannot be
told apart from the console — the clock is the only tie-breaker, which is why it is written down.

**`/gates` does not poll.** Unlike the run console (which refreshes every 3 seconds), the gates
list has no refresh interval — a gate that opens while you are looking at the screen will not
appear. Every "watch the Pending tab" step below says **reload manually**. Do not fail a gate case
because a gate "never appeared" without reloading first.

### 3 · One run at a time per work item

The backend admits one active run per **work item**, not per phase. Phases on the same epic must be
run strictly **sequentially** — you cannot prepare two gates in parallel to save time. Attempting it
produces a red `Trigger failed` banner (TS-14 TC-217), not a queued run.

---

### TC-201 · Zero to ready — signup to a dashboard that says you can start

| Field | Value |
|---|---|
| Suite | TS-15 End-to-End Greenfield Lifecycle |
| Type | E2E |
| Priority | Critical |
| Screen | `/signup`, `/setup`, `/projects/new`, `/profile`, `/repositories`, `/connect`, `/` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- The first case of the suite — nothing to continue from.
- Stack up per plan §2. Not logged in; use a fresh private window.
- The companion prerequisites are installed (Python 3.12, `git` on PATH, Claude Code logged in) and
  a local clone exists at `~/repos/payments-api`.

**Steps**
1. Sign up at `/signup` as `qa+c.owner@edvensoft.com`, workspace `QA Charlie`, password
   `QaTest-2026!`, and land in the app.
2. Work the setup checklist at `/setup` from top to bottom, following its links.
3. Create the project at `/projects/new`: name `Payment Gateway v2`, track **Greenfield**.
4. Fill the project profile at `/profile` with the plan §3 values (description, domain `Payments`,
   tech stack, NFRs) and save.
5. Register the repository at `/repositories`: `acme/payments-api`, role `backend`, base branch
   `main`.
6. Enrol the companion at `/connect`, then start it in its own terminal with the issued token.
7. Return to the dashboard at `/`.
8. **Checkpoint — record:** workspace name, the project id (from the `/profile` URL), the repo
   slug and base branch, and the companion machine name shown in the sidebar pill.
   **Resume point:** the `/setup` checklist is itself the resume protocol — reopen it and continue
   from the first step still showing as incomplete.

**Expected**
- Signup lands you inside the app with `QA Charlie` shown as the workspace, without a second login.
- After step 3 the project `Payment Gateway v2` is selectable in the project switcher.
- The saved profile survives a reload of `/profile` — the description, domain, stack and NFRs are
  all still there.
- `/repositories` lists `acme/payments-api` with role `backend` and base branch `main`.
- The sidebar companion pill reads `Companion: Ready`.
- The `/setup` checklist shows the project, profile, repository and companion steps as complete.
- The dashboard renders with the project selected and no blocking "finish setup" banner.

**Pass / Fail**
- PASS if a brand-new workspace reaches a ready dashboard with a live companion, entirely through
  the UI.
- FAIL if any step must be done outside the browser (other than starting the companion process), the
  profile does not persist, or the companion never reaches `Ready`.

**Test data**
- Workspace `QA Charlie` · project `Payment Gateway v2` · repo `acme/payments-api` / `main`

**Notes**
- **What this case adds beyond TS-01 and TS-05.** Those suites test signup, the setup checklist,
  project creation, the profile editor, repositories and companion enrolment *as individual
  screens*. This case adds the thing none of them can: that the six steps compose into a working
  workspace **in one uninterrupted sitting**, in the order the checklist itself dictates, with each
  step's output actually consumed by the next (the project is selectable for the profile, the
  profile persists for the agents to read, the repo and companion are both bound to that project).
  A screen that passes in isolation and still cannot be reached in sequence fails here and passes
  there. Do not re-verify per-field validation — that is TS-01/TS-03's job.
- **Time estimate: 45 minutes**, most of it companion setup on a first run.
- **Max wait: 10 minutes** for the companion pill to reach `Companion: Ready` after you start the
  process. Beyond that, record **Blocked** — the whole suite depends on this.
- Known trap (plan §2): if `POST /api/runners/` fails, the Connect screen shows a fake token
  `rnr_3f9a…b2` and advances anyway. If the companion rejects your token, check for that literal
  value — it is a real defect (TS-05), and it blocks this whole suite.
- Repo topology is derived from repo count, not chosen. There is no topology picker; do not look
  for one.

---

### TC-202 · Invite the team until every gate role is covered

| Field | Value |
|---|---|
| Suite | TS-15 End-to-End Greenfield Lifecycle |
| Type | E2E |
| Priority | Critical |
| Screen | `/admin/users`, `/accept-invite`, `/admin/roles` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-201 passed. Logged in as P1 in `QA Charlie` with `Payment Gateway v2` selected.
- You can read the inboxes for the persona addresses in plan §3.

**Steps**
1. Go to `/admin/users` and invite P2–P9 (product_owner, architect, designer, tech_lead, reviewer,
   qa_lead, security_engineer, devops) plus P10 (engineer) with the plan's addresses.
2. Accept each invitation from its one-time link, setting the password `QaTest-2026!`.
3. Log back in as P1 and open `/admin/roles`.
4. Confirm each persona holds its role in the matrix, toggling any that did not carry over from the
   invitation.
5. Read the **Gate-role coverage** panel at the bottom of the screen.
6. **Checkpoint — record:** for each of P2–P10, the email, the role granted, and a tick once you
   have personally signed in as that persona at least once. Every later case in this suite depends
   on these logins working; discovering a broken one at TC-210 costs an hour.
   **Resume point:** `/admin/roles` is the resume protocol — the matrix shows exactly which
   personas exist and which roles are on. Continue inviting or toggling from there.

**Expected**
- Each invited persona can accept and sign in with their own credentials.
- `/admin/roles` lists all ten users, with a switch column per role.
- Each of P2–P9 shows its role switch on for `Payment Gateway v2`, and P10 shows no role switch on
  except `engineer`.
- The **Gate-role coverage** panel lists every gate role with a `✓` and the holder's name after it
  (e.g. `Reviewer — <P6's name>`).
- No role is listed with `✗` or `— nobody`.
- No warning banner about an uncovered gate role is shown above the matrix.

**Pass / Fail**
- PASS if every gate role reports covered, with a named holder, and no gap warning is displayed.
- FAIL if any role stays uncovered after being granted, the coverage panel disagrees with the
  matrix, or the warning banner persists after full coverage.

**Test data**
- Personas P2–P10 per plan §3, password `QaTest-2026!`

**Notes**
- **What this case adds beyond TS-02.** TS-02 tests the invite lifecycle and the roles matrix as
  screens — one invite, one toggle, the coverage panel's rendering. This case adds **completeness as
  a precondition for the lifecycle**: that all nine gate roles can be held simultaneously by nine
  distinct real logins in one project, and that the coverage panel agrees with the matrix once they
  are. It is the fixture-builder for TC-203 → TC-212, and its unique assertion is "zero uncovered
  roles", which a single-invite case structurally cannot make. Do not re-verify invite expiry,
  resend or revoke here — that is TS-02.
- **Time estimate: 40 minutes** — inbox round-trips dominate.
- `/admin/roles` names the project as a plain line of text (`Project {name}`), not a dropdown, since
  commit b40c557. Roles are switched per project from the top-bar project select.
- A user holding two roles appears **twice** in the top-bar project selector (one option per role
  grant). Expect it; it is a tracked defect, not a finding for this case.
- Full coverage here is what makes the rest of the suite possible: every gate from TC-203 onward
  needs its role to exist.

---

### TC-203 · Plan tier, part 1 — Ideation from trigger to approved artifact

| Field | Value |
|---|---|
| Suite | TS-15 End-to-End Greenfield Lifecycle |
| Type | E2E |
| Priority | Critical |
| Screen | `/work-items`, `/runs`, `/runs/:id`, `/clarifications`, `/gates`, `/artifacts` |
| Persona | P1 Owner-Admin, P2 Product Owner |
| Automation | No |

**Preconditions**
- TC-202 passed — all gate roles covered, companion `Ready`.

**Steps**
1. As P1, create the epic `Stripe Webhook Integration` on `/work-items`.
2. **Checkpoint — record:** the epic id from its URL. Every case through TC-211 uses it.
3. Go to `/runs`, select the epic, and trigger **Ideation**.
4. **Checkpoint — record:** the run id. **Resume point:** if interrupted, reopen
   `/runs/<this run id>` and continue from step 5 — do not re-trigger.
5. Follow the run console to `Awaiting gate`, checking `/clarifications` whenever the console shows
   `Needs answer`, and answering any question the agent asks.
6. Open `/artifacts` and read the ideation artifact's **Status** badge. Record it.
7. Log out and log in as **P2 Product Owner**.
8. Open `/gates` and **reload the page** — the gates list does not poll. Select the Ideation gate.
9. Read the panel, then click **Approve**.
10. Reload `/gates`, then return to `/artifacts` and re-read the ideation artifact's badge.

**Expected**
- The epic appears on the board at state `proposed`.
- The run console badge progresses `Dispatched · waiting` → `Running` → (optionally `Needs answer`)
  → `Awaiting gate`.
- A clarification, if raised, appears on `/clarifications` and the run resumes after it is answered
  — the same run id, not a new one.
- Before approval (run at `Awaiting gate`), the ideation artifact's badge reads
  `Waiting for approval`.
- P2 sees the Ideation gate as actionable — **enabled** `Approve` and `Reject` buttons and a
  `Comment (optional to approve or reject)` field, not a read-only card.
- After approving, the gate leaves the `Pending (N)` tab (reload to confirm) and the run console
  badge reads `Completed`.
- The ideation artifact's badge in `/artifacts` now reads **`Published`**.

**Pass / Fail**
- PASS if the artifact goes `Waiting for approval` → `Published` through a Product Owner decision,
  with the run reaching its gate first.
- FAIL if the artifact reaches `Published` **before** the gate is approved, if the gate is decidable
  before the run reaches it, or if the artifact still reads `Waiting for approval` or `Draft` after
  approval.
- **Blocked** (not Fail) if the run has not reached `Awaiting gate` within **40 minutes**. Record
  the run id.

**Test data**
- Epic: `Stripe Webhook Integration`

**Notes**
- **Time estimate: 60 minutes** — the run itself is 20–30 minutes. **Max wait: 40 minutes** to
  `Awaiting gate`.
- **The badge sequence is `Draft` → `Waiting for approval` → `Published`.** When the run opens its
  gate, the run's draft artifacts are marked staged, which every screen shows as
  `Waiting for approval` (`open_gate_core` in `backend/orchestration/activities.py`; words from
  `frontend/src/features/observability/artifactStatus.tsx`; since commit 4ac75f9). Gate approval and
  publication then happen in the same transaction (`publish_artifacts_core`), so there is no
  observable `Approved` state on this path. Do **not** look for an `Approved` badge or an `Approved`
  option in the Status filter — the filter options are built from statuses actually present. Nothing
  reaches a system of record before its gate, and the gate approval *is* the publish. The rest of
  this suite asserts `Published` after each approval.
- Do not kill a silent run. A long phase can show no console output for 20+ minutes (Bug 3).
- A phase can reach its gate with an empty phase document (Bug 4). If the artifact previews empty,
  reference that bug in the tracker rather than raising a new defect — this case is about the state
  machine, not content quality.

---

### TC-204 · Plan tier, part 2 — Requirements then PRD, each through its gate

| Field | Value |
|---|---|
| Suite | TS-15 End-to-End Greenfield Lifecycle |
| Type | E2E |
| Priority | Critical |
| Screen | `/runs`, `/runs/:id`, `/gates`, `/artifacts`, `/work-items/:id` |
| Persona | P1 Owner-Admin, P2 Product Owner |
| Automation | No |

**Preconditions**
- TC-203 passed — the Ideation artifact for `Stripe Webhook Integration` is approved.

**Steps**
1. As P1, trigger **Requirements** on the epic from `/runs`.
2. **Checkpoint — record:** the Requirements run id. **Resume point:** reopen that run console.
3. Follow the run to `Awaiting gate`, answering any clarification.
4. Log in as P2, reload `/gates`, and approve the Requirements gate.
5. Log back in as P1 and trigger **PRD** on the same epic.
6. **Checkpoint — record:** the PRD run id.
7. Follow that run to `Awaiting gate`.
8. Log in as P2, reload `/gates`, and approve the PRD gate.
9. Open the epic at `/work-items/:id` and read the lifecycle rail.
10. Open `/runs`, select the epic, and count the run rows.

**Expected**
- Each phase produces exactly one run, and one artifact reading `Waiting for approval` while its gate
  is open.
- P2 can decide both gates; each shows enabled **Approve** and **Reject** buttons.
- After each approval, that phase's artifact reads **`Published`** in `/artifacts`.
- The epic's lifecycle rail shows Ideation, Requirements and PRD as completed nodes, in order.
- `/runs` lists three separate runs for the epic, none of them lost or duplicated.

**Pass / Fail**
- PASS if both phases run, gate and approve under the Product Owner role, and the rail reflects all
  three plan phases.
- FAIL if an approval leaves the artifact `Waiting for approval`, if an artifact reads `Published` before its gate
  is approved, or if the rail loses a completed phase.
- **Blocked** (not Fail) if either run has not reached `Awaiting gate` within **40 minutes**.

**Test data**
- Epic: `Stripe Webhook Integration` · Phases: `Requirements`, `PRD`

**Notes**
- **Time estimate: 90 minutes** — two full runs back to back. **Max wait: 40 minutes per run.**
- **The concurrency assertion that used to be here was wrong and has been removed.** The old
  Expected line claimed that clicking **Requirements** while Ideation was live raises a modal
  reading `Ideation is already running`. That cannot happen, for two independent reasons. First,
  the modal's title is built from **the phase you clicked**, so it could only ever read
  `Requirements is already running` (`frontend/src/features/lifecycle/PhasesAndRuns.tsx:268`).
  Second, no modal fires at all: the front-end guard looks up the latest run *for the clicked
  phase* (`:82-92`), and Requirements has no prior run — so the click goes straight through to the
  backend, which refuses it with a 409 surfaced as a red **`Trigger failed`** banner. That
  cross-phase refusal now has its own case, **TS-14 TC-217**; run it there rather than here.
- Because of that one-run-per-work-item rule, steps 1–8 **must** be sequential. You cannot start PRD
  while Requirements is live to save time.
- Ideation, Requirements and PRD all gate to `product_owner`. This case is where a role mix-up
  would surface as P2 unexpectedly getting a read-only card.
- Approval publishes in the same transaction, so `Published` — not `Approved` — is the badge to
  expect after each gate. See TC-203's Notes.

---

### TC-205 · Architecture — the Product Owner cannot decide it, the Architect can

| Field | Value |
|---|---|
| Suite | TS-15 End-to-End Greenfield Lifecycle |
| Type | E2E |
| Priority | Critical |
| Screen | `/runs`, `/gates`, `/artifacts` |
| Persona | P1 Owner-Admin, P2 Product Owner, P3 Architect |
| Automation | No |

**Preconditions**
- TC-204 passed — the PRD gate is approved and its artifact reads `Published`.

**Steps**
1. As P1, trigger **Architecture** on the epic and follow the run to `Awaiting gate`.
2. **Checkpoint — record:** the Architecture run id. **Resume point:** reopen that run console; if
   it already reads `Awaiting gate`, restart at step 3.
3. Log in as **P2 Product Owner**, open `/gates` and **reload**.
4. Select the Architecture gate and try to decide it.
5. Log out and log in as **P3 Architect**.
6. Open `/gates`, reload, select the Architecture gate, and click **Approve**.
7. Reload `/gates`, then check `/artifacts`.

**Expected**
- For P2, the Architecture gate renders as a **read-only card**: an informational banner titled
  `Awaiting architect` says `You don't hold the architect role on this project, so this is
  read-only.`, and the **Approve** / **Reject** buttons are disabled.
- P2 cannot change the gate's state by any control on the screen.
- For P3, the same gate is actionable with enabled **Approve** and **Reject** buttons.
- After P3 approves, the gate leaves the `Pending (N)` tab and the architecture artifact reads
  **`Published`** in `/artifacts`.
- The run for the phase reads `Completed`.

**Pass / Fail**
- PASS if the wrong role is read-only and the Architect's approval is what moves the artifact.
- FAIL if P2 can approve or reject. That is a **Critical** severity defect — a gate that the wrong
  role can decide.
- **Blocked** (not Fail) if the run has not reached `Awaiting gate` within **40 minutes**.

**Test data**
- Phase: `Architecture` · Gate role: `architect`

**Notes**
- **Time estimate: 60 minutes. Max wait: 40 minutes** to `Awaiting gate`.
- The read-only banner's title is built from the gate's required role, so it reads
  `Awaiting architect` for this phase. Quote it as rendered.
- P1 is a tenant admin and *may* approve any gate by design. Do not use P1 to test the boundary —
  P2 is the correct negative persona here because it holds a real but wrong gate role.
- The badge after approval is `Published`, not `Approved` — see TC-203's Notes.

---

### TC-206 · UX Design — the criteria gate needs all 22 WCAG 2.2 criteria ticked

| Field | Value |
|---|---|
| Suite | TS-15 End-to-End Greenfield Lifecycle |
| Type | E2E |
| Priority | Critical |
| Screen | `/runs`, `/gates`, `/gates/:id/criteria`, `/artifacts` |
| Persona | P1 Owner-Admin, P4 Designer |
| Automation | No |

**Preconditions**
- TC-205 passed — the Architecture gate is approved and its artifact reads `Published`.

**Steps**
1. As P1, trigger **UX Design** on the epic and follow the run to `Awaiting gate`.
2. **Checkpoint — record:** the UX Design run id. **Resume point:** log in as P4 and reopen the
   gate's criteria screen — ticks are not persisted until you approve, so restart the ticking from
   zero.
3. Log in as **P4 Designer**, reload `/gates`, and open the UX Design gate's criteria screen.
4. Read the criteria list and the state of the **Approve** button before ticking anything.
5. Tick the criteria one at a time, watching the button label after each tick.
6. With all 22 ticked, click **Approve**.
7. Reload `/gates`, then check `/artifacts`.

**Expected**
- The criteria screen lists **22 required criteria**, all required, at **WCAG 2.2 AA**:
  `1.1.1`, `1.4.1`, `1.4.3`, `1.4.11`, `1.4.13`, `2.1.1`, `2.2.2`, `2.4.3`, `2.4.5`, `2.4.6`,
  `2.4.7`, `2.4.11`, `2.5.1`, `2.5.7`, `2.5.8`, `3.2.3`, `3.2.6`, `3.3.1`, `3.3.2`, `3.3.3`,
  `3.3.7`, `3.3.8`.
- The counter above the list reads `0 of 22 criteria met`.
- With none ticked, the approve button is disabled and reads `Approve (22 remaining)`.
- The count in the label decreases by one with each tick — `Approve (21 remaining)`, `Approve (20
  remaining)`, and so on.
- With 21 of 22 ticked, the button still reads `Approve (1 remaining)` and is still disabled.
- With all 22 ticked, the label becomes `Approve` and the button is enabled.
- After approving, the gate leaves the `Pending (N)` tab and the ux_design artifact reads
  **`Published`** in `/artifacts`.

**Pass / Fail**
- PASS if approval is impossible until all 22 criteria are ticked and the remaining-count label
  tracks the ticks exactly.
- FAIL if the button enables early, the count is wrong, or the criteria can be bypassed from the
  plain `/gates` card.
- FAIL — **High** — if the list has 9 criteria rather than 22, or if `1.4.4` or `4.1.2` appear. That
  means the design gate is still on the old hand-typed WCAG 2.1 list and the 2.2 uplift did not
  reach it.
- **Blocked** (not Fail) if the run has not reached `Awaiting gate` within **40 minutes**.

**Test data**
- Phase: `UX Design` · Gate role: `designer` · 22 required WCAG 2.2 criteria

**Notes**
- **What this case adds beyond the TS-09 criteria-gate cases.** TS-09 tests the criteria screen's
  mechanics on whatever gate is available. This case adds that the checklist gate sits **in the
  live plan sequence** — that a real UX Design run opened it, that the designer persona created in
  TC-202 can reach and clear it, and that clearing it lets the chain continue to Task Breakdown.
  Its unique risk is a checklist gate becoming an unclearable dead end mid-lifecycle. Do not
  re-verify per-criterion toggling minutiae here.
- **The checklist grew from 9 criteria to 22 in August 2026, deliberately.** It used to be nine
  hand-typed WCAG 2.1 criteria; it is now derived from the WCAG 2.2 standard the platform loaded, so
  a future release of the standard is a data reload rather than a code edit. `1.4.4` Resize Text and
  `4.1.2` Name, Role, Value both left the list on purpose — neither can be judged from a drawing.
  Do not raise a defect for the count. See TS-09 TC-137's Notes for the full reasoning.
- **Budget for the ticking.** 22 ticks in the middle of a 60-minute case is real time and real
  tedium. If the list is hard to work through — no sense of what you have already ticked, awkward
  scrolling — raise it as a **Medium** usability defect even though the mechanics pass. A checklist
  nobody can complete honestly gets ticked without being read, which defeats the gate.
- **Time estimate: 60 minutes. Max wait: 40 minutes** to `Awaiting gate`.
- Also confirm from the plain `/gates` list that the same gate cannot be approved there without the
  criteria — if it can, that is a **Critical** gate-bypass finding.
- `ux_design` is internal-only: it has no external export target, so its publish screen shows the
  banner `This phase publishes internally only per the project's export policy.` rather than a
  target picker. That is by design — see TC-211.
- The badge after approval is `Published`, not `Approved` — see TC-203's Notes.

---

### TC-207 · Task Breakdown — approve as Tech Lead and see the fan-out

| Field | Value |
|---|---|
| Suite | TS-15 End-to-End Greenfield Lifecycle |
| Type | E2E |
| Priority | Critical |
| Screen | `/runs`, `/gates`, `/work-items`, `/work-items/:id/breakdown` |
| Persona | P1 Owner-Admin, P5 Tech Lead |
| Automation | No |

**Preconditions**
- TC-206 passed — the UX Design gate is approved.

**Steps**
1. As P1, trigger **Task Breakdown** on the epic and follow the run to `Awaiting gate`.
2. **Checkpoint — record:** the Task Breakdown run id.
3. Log in as **P5 Tech Lead**, reload `/gates`, and approve the Task Breakdown gate.
4. Go to `/work-items` and inspect the board under the epic. **Count the children of the epic, by
   type**, and record the counts. At this point every child should be a `task`.
5. Open `/work-items/<epic id>/breakdown` and read the heading number.
6. **Checkpoint — record:** the total child count, and the id and title of the **first child task**
   — TC-208 runs against it. **Resume point:** restart at step 5; the fan-out is durable.
7. Back on `/runs`, re-run **Task Breakdown** on the same epic (confirm the `Re-run Task Breakdown?`
   modal), approve it again as P5, and re-check the breakdown screen.

**Expected**
- P5 can decide the gate; the Product Owner would see a read-only card (spot-check if time allows).
- Child work items of type `task` appear under the epic on the board, each at state `proposed`.
- `/work-items/:id/breakdown` shows the heading `N task work items`, where `N` matches **the total
  number of children of the epic** counted at step 4.
- Because no task tracker is connected, the screen shows the banner `Saved in the platform` with the
  text `Task tracker isn't connected, so these live in the platform only. Connect Jira to push them
  to a backlog.`
- The actions **Go to board** and **Connect a task tracker** are present, and **Go to board**
  returns you to `/work-items`.
- A panel titled `Task work items` lists each child with an **Open** action.
- After the re-run in step 7, the child count is unchanged — the tasks are de-duplicated, not
  doubled.

**Pass / Fail**
- PASS if approving Task Breakdown fans out child task work items that appear on the board and on
  the breakdown screen, and a re-run does not duplicate them.
- FAIL if no children appear, the heading disagrees with the epic's **total** child count, or the
  re-run doubles the tasks.
- **Blocked** (not Fail) if either run has not reached `Awaiting gate` within **40 minutes**.

**Test data**
- Phase: `Task Breakdown` · Gate role: `tech_lead`

**Notes**
- **Time estimate: 60 minutes** including the re-run. **Max wait: 40 minutes per run.**
- **The heading counts ALL children, not just tasks.** Despite reading `N task work items`, the
  screen lists every child of the epic regardless of type — it queries children by parent with no
  type filter (`frontend/src/features/lifecycle/TaskBreakdown.tsx:19, 57`). Run this case **before**
  TC-209 creates `test_case` children, or the number will legitimately exceed the task count and
  you will chase a phantom. If you must re-read this screen after TC-209, compare the heading
  against the epic's **total** children, not its tasks. The mislabelled heading is worth raising
  once as a Low copy/logic defect; do not raise it again from a later case.
- Later phases add more children of other types — `test_case` (TC-209) and, in the build tier,
  remediation `task` children opened by Code Review. Expect this number to drift upward for
  legitimate reasons.
- The fan-out is done by the **agent**, not by the gate approval, so the children may already exist
  before you approve. Confirm they are there after approval; do not fail the case because they
  appeared early.
- If Jira had been connected, the banner would instead read `Pushed to Jira backlog` with a
  **Back to epic** action. Integrations are TS-04's territory.
- `/work-items/:id/breakdown` has **no in-app link** — reach it by typing the URL.

---

### TC-208 · Build tier — Implementation on a child task through its gate

| Field | Value |
|---|---|
| Suite | TS-15 End-to-End Greenfield Lifecycle |
| Type | E2E |
| Priority | Critical |
| Screen | `/work-items/:id`, `/runs`, `/runs/:id`, `/gates` |
| Persona | P1 Owner-Admin, P5 Tech Lead |
| Automation | No |

**Preconditions**
- TC-207 passed — child task work items exist under the epic.
- The repository `acme/payments-api` is registered and the companion has a working clone.

**Steps**
1. Open the first child task recorded in TC-207 and confirm its title.
2. Go to `/runs`, select that **task** (not the epic) in the work-item selector, and trigger
   **Implementation**.
3. **Checkpoint — record:** the task id and the Implementation run id. **Resume point:** reopen
   `/runs/<this run id>` — do not re-trigger, a build re-run is the most expensive restart in the
   pack.
4. Follow the run console to `Awaiting gate`, answering any clarification.
5. Log in as **P5 Tech Lead**, reload `/gates`, and approve the Implementation gate.
6. Reload `/gates`, then return to the task's detail screen.
7. Open `/artifacts` and filter to this task.

**Expected**
- The trigger targets the child task — the run console header names that task, not the epic.
- The run reaches `Awaiting gate` and an Implementation gate appears on `/gates` for the task
  (reload — the list does not poll).
- P5 can decide the gate; after approval the run console badge reads `Completed`.
- `/artifacts` lists a `code` artifact for the run whose `SoR` cell carries the pull-request
  reference.
- The task's detail screen shows the Implementation phase as completed on its lifecycle rail.
- The epic's own runs are untouched — no new run is created against the epic.

**Pass / Fail**
- PASS if Implementation runs against a child task and completes through a Tech Lead approval, with
  a PR recorded.
- FAIL if the run is created against the epic, no gate appears, no PR reference is recorded, or
  approving the task's gate also closes an epic-level gate.
- **Blocked** (not Fail) if the run has not reached `Awaiting gate` within **60 minutes**, or if the
  companion cannot clone or push the repository.

**Test data**
- Work item: the first child task of `Stripe Webhook Integration` · Phase: `Implementation`

**Notes**
- **Time estimate: 90 minutes** — build-tier runs are the longest in the suite. **Max wait: 60
  minutes** to `Awaiting gate`.
- **Do not expect a separate Code Review gate to appear during this run.** Code Review (08) runs
  *inside* the build loop, dispatched by the workflow, and it opens **no Approval of its own** — the
  build tier has exactly one gate, the merge gate, and it carries the role of the phase you
  triggered (`tech_lead` for Implementation). The old instruction to "decide it as P6 if a reviewer
  gate appears" was wrong; no such gate is created. 08's real observable evidence is a `code_review`
  artifact and any remediation child tasks — **TC-218** covers that, and it reads the output of
  *this* run. Do not clean up this task before TC-218.
- The task's lifecycle rail renders **plan** phases as well as build ones. That is a tracked defect
  (the lifecycle endpoint computes a tier and never applies it); assert only that Implementation
  shows as completed, and ignore the irrelevant plan nodes.
- If the run parks on an error, that is TS-14's `Resume from where it stopped` path (TC-197) — use
  it and continue rather than restarting the phase. If it parks at a **report timeout** instead
  (no `Paused on an error` banner), recovery is `/recovery`, not resume.
- The build tier may show an `Automatically retried` banner on a failed run — the platform starts a
  fresh attempt on its own. Follow the link to the retry run rather than re-triggering.

---

### TC-209 · Testing — QA Lead approval produces test_case work items and artifacts

| Field | Value |
|---|---|
| Suite | TS-15 End-to-End Greenfield Lifecycle |
| Type | E2E |
| Priority | High |
| Screen | `/runs`, `/gates`, `/artifacts`, `/work-items/:id/test-cases` |
| Persona | P1 Owner-Admin, P7 QA Lead |
| Automation | No |

**Preconditions**
- TC-208 passed — at least one child task has been implemented and gated.

**Steps**
1. As P1, trigger **Testing** on a story/task under the epic and follow the run to `Awaiting gate`.
2. **Checkpoint — record:** the work item you are testing and the Testing run id.
3. Log in as **P7 QA Lead**, reload `/gates`, and open the Testing gate.
4. Read the gate's condition — record its exact label and whether it shows as satisfied.
5. Approve.
6. Reload `/gates`, then open `/artifacts` and filter to the tested work item.
7. Open `/work-items/<the tested item>/test-cases`.
8. **Checkpoint — record:** the ids of the child `test_case` work items. TS-13 TC-213 runs 09b
   against one of them. **Resume point:** restart at step 7; the fan-out is durable.

**Expected**
- The Testing gate shows **exactly 2 derived conditions** — `No failing blocking test — every
  failing test's defect is resolved, or the test is quarantined as flaky` and `No unresolved
  accessibility failure — every WCAG 2.2 finding that blocks under this project's accessibility
  policy is fixed` — and the gate is decidable by P7. *(Corrected 2026-09-17 alongside TS-09
  TC-139: the accessibility condition has been on this gate since it shipped.)*
- Both conditions show as **satisfied**, and neither is **tickable** — they are platform-evaluated,
  not reviewer-attested, so the checkbox rejects a manual change.
- The Product Owner would see a read-only card for this gate (spot-check if time allows).
- After approval, the run reads `Completed`.
- `/artifacts` lists one or more `test_case` artifacts registered by the run.
- `/work-items/:id/test-cases` lists child `test_case` work items with `TC-ID`, `Title`, `Priority`
  and `Automation` columns, and the counter line `N of M automated`.
- Each of those cases is badged `Not automated` and offers a **Generate script** action.

**Pass / Fail**
- PASS if Testing gates under QA Lead and materialises both `test_case` artifacts and child
  `test_case` work items visible on the test-cases screen.
- FAIL if no test cases are materialised, the test-cases screen stays empty, the gate is decidable
  by the wrong role, or the derived condition can be **ticked by hand** (that would make a
  platform-evaluated rule reviewer-overridable — **Critical**).
- **Blocked** (not Fail) if the run has not reached `Awaiting gate` within **45 minutes**.

**Test data**
- Phase: `Testing` · Gate role: `qa_lead`

**Notes**
- **Time estimate: 75 minutes. Max wait: 45 minutes** to `Awaiting gate`.
- **This case observes the blocking-test condition only in its trivially-satisfied state, and that
  is a known coverage limit — not a defect to raise.** The condition is computed from open `defect`
  child work items under the tested item
  (`backend/apps/gates/testgate.py:53`, `evaluate`). Those defects are opened only by the
  **test-results loopback**, which fires when a build-tier 09b run reports JUnit results
  (`import_build_test_results`, gated on the catalog's `imports_test_results`). Since no 09b run has
  reported against this work item yet, there are no defects, so the condition is satisfied by
  emptiness. Nothing in this suite drives it to *unsatisfied*. Record it as observed-satisfied and
  move on.
- Note also that CI-posted results (TS-13 TC-214) attach to a project-level `CI Regression`
  container, **not** to this story — so they cannot flip this condition either. Driving this gate
  to a blocked state has no browser-reachable path today; that gap is documented, not a bug to file
  from here.
- **Known, do not re-raise:** every `test_case` artifact previews a batch of ~25 unrelated cases
  (`docs/TESTING_PHASE_BUGS_HANDOFF.md` Bug 1), and the generated cases read as engineer-facing
  rather than manual-QA-executable (Bug 2). Confirm the behaviour matches and reference the handoff
  in the tracker.
- The derived condition is recomputed at decide time, so it can flip between opening the gate and
  clicking approve. Re-read it immediately before deciding.

---

### TC-210 · Security, CI/CD and Deployment — each to its own role

| Field | Value |
|---|---|
| Suite | TS-15 End-to-End Greenfield Lifecycle |
| Type | E2E |
| Priority | Critical |
| Screen | `/runs`, `/gates`, `/gates/:id/criteria`, `/artifacts` |
| Persona | P1 Owner-Admin, P8 Security Engineer, P9 DevOps |
| Automation | No |

**Preconditions**
- TC-209 passed — Testing is approved for the work item you are driving.

**This case is three sub-cycles. Treat each as its own checkpoint** — it is the longest case in the
pack and requires four logins. Record the run id at the start of each sub-cycle, and note which
sub-cycles are complete. **Resume point: the start of the first incomplete sub-cycle.** Never
restart from sub-cycle A to "be safe" — re-running a completed phase replaces its artifacts.

**Steps**

*Sub-cycle A — Security*
1. As P1, trigger **Security** on the work item; **record the run id**; follow to `Awaiting gate`.
2. Log in as **P9 DevOps**, reload `/gates`, open the Security gate and confirm it is read-only.
3. Log in as **P8 Security Engineer**, reload `/gates`, open the Security gate and read its
   `Required checklist` block. If it is met, approve the Security gate. If it is not met, record the
   open findings it names and follow TS-09 TC-906 until they are resolved, then approve.
4. **Mark sub-cycle A complete in your notes.**

*Sub-cycle B — CI/CD*
5. As P1, trigger **CI/CD**; **record the run id**; follow to `Awaiting gate`.
6. Log in as **P8 Security Engineer**, reload `/gates`, open the CI/CD gate and confirm it is
   read-only.
7. Log in as **P9 DevOps**, reload `/gates`, and approve the CI/CD gate.
8. **Mark sub-cycle B complete.**

*Sub-cycle C — Deployment*
9. As P1, trigger **Deployment**; **record the run id**; follow to `Awaiting gate`.
10. As **P9 DevOps**, open the Deployment gate's criteria screen and read the readiness criteria and
    the approve button label before ticking anything.
11. Tick all readiness criteria and approve.
12. Reload `/gates`, then check `/artifacts` for all three phases.

**Expected**
- The Security gate is decidable by P8 and read-only for P9 (banner `Awaiting security_engineer`).
- The Security gate carries exactly one required item,
  `No unresolved Critical or High security finding — every one the security review raised has been
  fixed`. P8's `Approve` is disabled (`Approve (1 remaining)`) while any Critical or High security
  finding is open, and the item shows as met by itself once none is (commit 4ac75f9; see TC-906).
- The CI/CD gate is decidable by P9 and read-only for P8 (banner `Awaiting devops`).
- The Deployment criteria screen lists **7 required readiness criteria** — code quality, testing,
  security, migrations, rollback, on-call, deliverables.
- With none ticked, the approve button is disabled and reads `Approve (7 remaining)`; the count
  decreases with each tick and the button only enables at `Approve`.
- After each approval, that phase's artifact reads **`Published`** in `/artifacts`.
- All three runs end at `Completed`.

**Pass / Fail**
- PASS if each of the three gates is decided only by its own role, and Deployment requires all 7
  criteria.
- FAIL if a role can decide another role's gate, Deployment approves with criteria outstanding, or
  the Security gate is approved while a Critical or High security finding is still open
  (**Critical**).
- **Blocked** (not Fail) if any run has not reached `Awaiting gate` within **45 minutes**. Record
  which sub-cycle blocked, so a re-run resumes there.

**Test data**
- Phases: `Security` (security_engineer) · `CI/CD` (devops) · `Deployment` (devops, 7 criteria)

**Notes**
- **What this case adds beyond TS-09 and TC-206.** TS-09 proves a single gate enforces a single
  role; TC-206 proves one checklist gate works. This case adds the **role-separation matrix across
  adjacent phases**: that P8 and P9 each hold exactly one of two consecutive gates and are
  read-only on the other. A per-gate case cannot catch a role mapping that is right in isolation
  but swapped between two neighbouring phases, which is the specific failure here. The Deployment
  checklist is included because it is a *different* checklist (readiness, 7) from TC-206's (WCAG,
  22 by default — `DESIGN_CHECKS` in `backend/apps/gates/wcag.py`), and a shared bug would show as
  the wrong count.
- **Time estimate: 90 minutes** — three runs plus four persona switches. **Max wait: 45 minutes per
  run.**
- Deployment is a **doc-producing planning phase**: approving it does not deploy anything, and no
  smoke test, monitor or rollback is performed. Do not raise the absence of a real deployment as a
  defect; assert the artifact and the gate only.
- The badge after each approval is `Published`, not `Approved` — see TC-203's Notes.

---

### TC-211 · The gate rule holds at the publish screen, and the chain agrees across surfaces

| Field | Value |
|---|---|
| Suite | TS-15 End-to-End Greenfield Lifecycle |
| Type | E2E |
| Priority | Critical |
| Screen | `/artifacts`, `/artifacts/:id`, `/artifacts/:id/publish`, `/`, `/traceability` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-210 passed — the plan and build chain for `Payment Gateway v2` is through its gates.
- **You need one artifact that is not gate-approved.** Every gated artifact is already `Published` by now, so
  create the fixture the cheap way: perform **TC-212 step 1 only** (as P1, trigger **Ideation** on a
  new epic `Refunds API` and let it reach `Awaiting gate`), then come back here. TC-212 needs that
  run anyway, so this costs nothing extra. Do **not** let P2 decide its gate until TC-212.
- No document connector is configured (the greenfield default for this cycle).
- **Checkpoint — record:** the ungated artifact's id, and the PRD artifact's id.

**Steps**
1. Open `/artifacts` and find the ideation artifact for `Refunds API`, badged
   `Waiting for approval`. Read its row's action cell.
2. Click **Preview** on that row and copy its id from the URL (`/artifacts/<id>`). Now navigate
   directly to `/artifacts/<id>/publish`.
3. Read the panel. Do not attempt to force the button.
4. Return to `/artifacts` and open the **PRD** artifact for `Stripe Webhook Integration` — the one
   approved in TC-204. Click **Export**.
5. Read the `Target capability` select and note which option is **preselected**.
6. Leave the preselected external target as-is and click **Publish**. Read the result.
7. Now change `Target capability` to `Internal (platform)` and click **Publish** again.
8. Click **Done**, return to `/artifacts` and read the PRD artifact's badge.
9. Open the dashboard at `/` and read the `Recent publishes` card and the `Project health` row
   `Published this week`.
10. Open `/traceability` and find the node for that artifact.

**Expected**
- **Step 1:** the `Waiting for approval` row offers **Preview only** — there is **no Export action**.
  The UI itself withholds the route to publishing for an ungated artifact.
- **Step 3:** reached by URL, the publish screen refuses it — a danger banner titled
  `Can't publish — not gate-approved` reads `This artifact is still staged. Approve its gate first;
  manual publish never bypasses a gate.` (this banner prints the raw status token) with an
  `Open gate ↗` link, and the **Publish** button is
  **disabled**. Only **Cancel** is actionable.
- **Step 4:** the `Published` PRD row offers both **Preview** and **Export**.
- **Step 5:** the `Target capability` select is preselected to the phase's **external** target,
  `Documentation store · Confluence` — **not** `Internal (platform)`. Both options are present.
- **Step 6:** with no connector configured, the external publish **fails honestly** — a danger
  banner titled `Publish failed` carries the message `No documentation-store connector is
  configured for this workspace. Connect one on the Integrations page first.` Nothing is exported
  and the artifact's status is unchanged.
- **Step 7:** publishing to `Internal (platform)` succeeds — a `Published` modal appears with the
  banner text `Artifact v<n> is now published.` and no system-of-record link.
- **Step 8:** `/artifacts` still shows the PRD as **`Published`**.
- **Step 9:** the dashboard's `Recent publishes` card lists the artifact, and `Published this week`
  is at least 1.
- **Step 10:** `/traceability` shows the artifact as a **Published** node, connected back to the
  epic it came from.

**Pass / Fail**
- PASS if an ungated artifact is refused at both the row level (no Export) and the screen level
  (disabled Publish + the gate banner); the external publish fails with readable guidance rather
  than silently claiming success; and the registry, dashboard and graph agree.
- FAIL — **Critical** — if the draft can be published by any route, or if the external publish
  reports success while no connector exists (a provenance lie: the platform would be claiming a
  push that did not happen).
- FAIL if the failed external publish leaves the artifact in a changed or broken state, or if the
  three surfaces disagree about what was published.

**Test data**
- Draft artifact: the `ideation` artifact for `Refunds API`
- Approved artifact: the `prd` artifact for `Stripe Webhook Integration`

**Notes**
- **What this case was, and why it was rebuilt.** It used to read "approve the artifact, then
  publish it, then observe `Published`". That spine was vacuous: gate approval publishes in the same
  transaction, so the artifact is already `Published` before the publish step, and the Critical
  assertion asserted nothing. Its step 1 was also unexecutable — it said to pick a draft and "try to
  publish it", but the **Export** control renders only for approved/published artifacts
  (`frontend/src/features/observability/ArtifactsRegistry.tsx:191-196`), so there was no button to
  click. The rebuilt case tests the same risk — *nothing ungated reaches a system of record* — via
  the two routes that actually exist: the withheld control, and the URL-reached guard.
- **The internal fallback does not apply here, by design.** The backend falls back to an internal
  publish only when the artifact is still `APPROVED` (`backend/api/views.py:1386-1393`). Because
  gate approval already advanced it to `PUBLISHED`, a manual external export is treated as a
  **re-export**, and a re-export that cannot reach its system of record fails honestly rather than
  succeeding as a no-op. Step 6's `Publish failed` is therefore **correct behaviour**, not a defect.
- **Time estimate: 40 minutes** (plus the Ideation run in the preconditions, which TC-212 reuses).
- Default export targets: ideation / requirements / prd / architecture / security / cicd →
  Confluence; task_breakdown → Jira; testing / test_automation → Xray; `ux_design` is internal-only
  and its publish screen shows `This phase publishes internally only per the project's export
  policy.` instead of a target picker. A missing destination on `ux_design` is correct.
- **`Recent publishes` and `Published this week` filter on the date the artifact was published**
  (`published_at`, `backend/api/views.py` dashboard rollup; since commit 4ac75f9 — audit Part 6,
  item 14 is fixed). The PRD was first published when its gate was approved in TC-204, and the
  internal re-publish in step 7 does not move that date. So step 9 passes when TC-204 was within the
  last 7 days; if it was earlier, the PRD correctly drops out of both surfaces — record that rather
  than failing the case.

---

### TC-212 · Rejection and recovery — reject a gate, re-trigger, pass on the second attempt

| Field | Value |
|---|---|
| Suite | TS-15 End-to-End Greenfield Lifecycle |
| Type | E2E |
| Priority | High |
| Screen | `/gates`, `/runs`, `/runs/:id`, `/artifacts` |
| Persona | P1 Owner-Admin, P2 Product Owner |
| Automation | No |

**Preconditions**
- TC-211 passed.
- The epic `Refunds API` and its first Ideation run already exist — you created them as TC-211's
  draft fixture, and that run is sitting at `Awaiting gate`. If you skipped that, do step 1 now.
- **Checkpoint — record:** the `Refunds API` epic id and the first Ideation run id.

**Steps**
1. If not already done for TC-211: as P1, trigger **Ideation** on `Refunds API` and follow the run
   to `Awaiting gate`. **Record the run id.**
2. Log in as **P2 Product Owner**, reload `/gates`, open the gate, type a written reason in
   the comment field (`Comment (optional to approve or reject)`, which reads `Comment` once you
   type), and click **Reject** — not **Request changes**, which would start a new attempt itself.
3. Open the rejected run's console and read its state.
4. Go to `/runs`, select `Refunds API`, and read the run history.
5. Check `/artifacts` for the ideation artifact's badge.
6. As P1, trigger **Ideation** on `Refunds API` again.
7. **Checkpoint — record:** the second run id. **Resume point:** reopen that run console.
8. Follow the second run to `Awaiting gate`, then reload `/gates` and approve it as P2.
9. Re-check `/artifacts` for both the `Refunds API` ideation artifact and the TC-211 PRD artifact.

**Expected**
- The rejection is accepted and the gate leaves the `Pending (N)` tab.
- The rejected run's console shows a danger banner titled `Gate rejected` whose body reads
  `The gate was rejected. Re-trigger to try again.`
- `/runs` still lists the rejected run in history — it is not deleted or overwritten.
- After the rejection the first run's ideation artifact reads **`Superseded`** — it is **not**
  `Published`. (While the gate was open it read `Waiting for approval`.)
- The re-trigger in step 6 is accepted (a rejected run does not block a new one) and creates a
  **second, distinct** run id.
- After P2 approves the second run's gate, the `Refunds API` ideation artifact reads **`Published`**
  and both runs remain visible in history.
- The TC-211 PRD artifact is still `Published` and untouched by this case.

**Pass / Fail**
- PASS if rejection is durable and visible, the rejected run's artifact reads `Superseded`, and a second attempt can be
  run and approved to `Published`.
- FAIL if the rejected run vanishes from history, the artifact reaches `Published` despite the
  rejection, or the re-trigger is blocked with no way forward.
- **Blocked** (not Fail) if either run has not reached `Awaiting gate` within **40 minutes**.

**Test data**
- Epic: `Refunds API` · Phase: `Ideation` · Gate role: `product_owner`

**Notes**
- **Time estimate: 75 minutes** — two full runs (one of them already paid for by TC-211's fixture).
  **Max wait: 40 minutes per run.**
- This is the pack's **only** gate rejection. It rejects a plain plan gate; rejecting a criteria
  gate (do the ticks persist?) and rejecting a build-tier merge gate (which must unwind a live PR)
  are both uncovered. Do not try to cover them here — note the gap and keep this case single-purpose.
- Re-running a phase replaces that phase's artifacts rather than creating duplicates; the
  `Re-run Ideation?` modal says so. The previous run stays in the history — that is the assertion
  here.
- The badge after the second approval is `Published`, not `Approved` — see TC-203's Notes.

---

### TC-218 · Code Review (08) leaves its evidence inside the build loop

| Field | Value |
|---|---|
| Suite | TS-15 End-to-End Greenfield Lifecycle |
| Type | E2E |
| Priority | High |
| Screen | `/runs/:id`, `/artifacts`, `/work-items` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-208 passed and its child task, Implementation run and merged PR are **still present**. This
  case reads that run's output; it triggers nothing.
- **Checkpoint — you need from TC-208:** the child task id and the Implementation run id.

**Steps**
1. Open `/runs/<the TC-208 Implementation run id>`.
2. Read the console log from the top, looking for the review phase of the build loop.
3. Open `/artifacts` and filter to the TC-208 child task. List every artifact registered by that
   run and its type.
4. Go to `/work-items` and inspect the children of the TC-208 child task.
5. Open `/gates`, reload, and switch to the **Decided history** tab. Read every gate recorded
   against the TC-208 child task.

**Expected**
- The run's artifacts include a **`code_review`** artifact alongside the `code` artifact — 08 ran
  and registered its verdict.
- The `code_review` artifact's title names the work item under review.
- Exactly **one** gate exists for this run in the decided history — the merge gate, recorded against
  the role **`tech_lead`** (the role of the phase that was triggered).
- **No separate Code Review gate and no `reviewer`-role gate exists** for this run, in either the
  Pending or the Decided history tab.
- If the reviewer found blocking issues, remediation child work items exist under the task; if it
  found none, there are none. Either is a pass — record which you saw.

**Pass / Fail**
- PASS if 08's evidence (a `code_review` artifact) is present and the build tier shows exactly one
  gate, held by the triggered phase's role.
- FAIL if no `code_review` artifact was ever registered — that means the review step did not run,
  and the remediation loop that guards build quality is inert.
- FAIL if a second, `reviewer`-role gate was opened for this run — the build tier is designed to
  have one gate, and a second one would mean a build can stall on a role nobody was told to staff.
- **Blocked** if TC-208's run or its artifacts have been cleaned up.

**Test data**
- Work item: the TC-208 child task · Phase under inspection: `Code Review` (`08_code_review`)

**Notes**
- **Time estimate: 20 minutes** — this is a read-only inspection of an existing run. No agent run,
  so no max wait applies.
- **Why this case exists.** `08_code_review` is a full gate role in the agent catalog
  (`backend/apps/registry/catalog.py`, gate role `reviewer`) and the entire remediation loop hangs
  off it, yet no case in the pack exercised it — TC-208 mentioned it only as an aside, and that
  aside was **wrong** (it told the tester to decide a reviewer gate as P6; no such gate is ever
  created).
- **How 08 actually runs.** It is dispatched *inside* the build workflow's review→remediate loop,
  never as a standalone user trigger — the catalog marks it `rides_build=False` precisely because
  the workflow drives it. It registers a `code_review` artifact and opens/closes remediation child
  work items, but it opens **no Approval of its own**. The build tier's single gate is the merge
  gate, whose required role comes from the phase the user triggered.
- Because P6 Reviewer holds a gate role that the greenfield build path never actually uses, P6 may
  legitimately never see a gate in this whole cycle. That is worth noting in the tracker as a
  coverage observation, not raising as a defect against this case.
- If TC-208's run **parked** and was resumed, expect the review step to appear more than once in the
  console — the resumed block re-runs the review, which is idempotent. Duplicate console entries are
  not a duplicate artifact; check the artifact list, not the log.
