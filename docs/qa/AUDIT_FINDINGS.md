# QA Lead Audit — Greenfield Test Pack

Audit of all 212 cases in [`suites/`](suites/) against the **shipped application source**, not the design
docs. Every finding below cites `file:line`.

> **Status: applied.** Everything below has been worked through — the suites, the plan and the tracker
> now reflect it. Parts 1–4 are kept as the record of *why* cases read the way they do; Part 6 (product
> defects) is logged separately in `docs/Bugs.xlsx`. Read this if a case surprises you, not as a to-do
> list.
>
> One case was deleted (TC-032, which had no reachable object) and 42 were added, taking the pack from
> 212 cases to 253. A handful of audit claims did not survive re-checking against source; those are
> flagged inline below.

**Original verdict: do not hand this pack to the team as-is.** 161 defects in the pack itself, plus ~20
coverage gaps. Roughly **35 cases will produce a wrong verdict** — they assert strings the app never
renders, or demand states the app cannot reach. A tester following them raises false defects, or
(worse) passes a broken build.

| Suite | Findings | Wrong | Assumed | Missed | Unclear |
|---|---|---|---|---|---|
| TS-01 Identity | 11 | 4 | 1 | 4 | 2 |
| TS-02 Admin & Roles | 8 | 2 | 1 | 3 | 2 |
| TS-03 Project Setup | 9 | 4 | 1 | 3 | 1 |
| TS-04 Integrations | 9 | 2 | 1 | 4 | 2 |
| TS-05 Companion | 8 | 1 | 1 | 3 | 3 |
| TS-06 Work Items | 11 | 4 | 1 | 4 | 2 |
| TS-07 Runs | 12 | 3 | 3 | 3 | 3 |
| TS-08 Clarifications | 10 | 1 | 4 | 3 | 2 |
| TS-09 Gates | 15 | 3 | 4 | 4 | 4 |
| TS-10 Artifacts | 17 | 3 | 1 | 9 | 4 |
| TS-11 Traceability | 11 | 1 | 0 | 7 | 3 |
| TS-12 Shell & Dashboard | 12 | 3 | 1 | 6 | 2 |
| TS-13 Test Cases | 9 | 2 | 3 | 3 | 1 |
| TS-14 Recovery | 8 | 3 | 2 | 2 | 1 |
| TS-15 End-to-end | 11 | 4 | 1 | 3 | 3 |
| **Total** | **161** | **40** | **25** | **61** | **35** |

---

## Part 1 — The five systemic errors

Each of these invalidates a group of cases at once. Fix these first; they account for ~30 of the 40
WRONG findings.

### S1 · `approved` is never displayed — the app shows `Published` — 8 cases

Gate approval publishes the artifact in the same transaction. There is no observable `approved` state
in the registry.

- `backend/orchestration/activities.py:299-302` — `tools.update_artifact(..., status=Artifact.Status.PUBLISHED, sor=Artifact.SoR.INTERNAL)`
- `frontend/src/features/observability/ArtifactsRegistry.tsx:21` — `if (status === "published" ...) return <Badge variant="done">Published</Badge>`

**Affected:** TC-128, TC-203, TC-204, TC-205, TC-206, TC-210, TC-211 (+ the `Approved` filter option in
TC-128, which cannot exist because `statusOptions` is derived from statuses actually present —
`ArtifactsRegistry.tsx:40`).

TC-211 is worst: its spine is "approve, then publish, then observe `Published`" — but the artifact is
already published before step 2, so the Critical assertion is vacuous. Its step 1 ("pick a draft and try
to publish it") also has no button to click — **Export** renders only for `approved`/`published`
(`ArtifactsRegistry.tsx:191-196`).

**Fix:** rewrite all 8 against `Published`. Delete the note in TC-128 claiming the badge reads `Draft`.

### S2 · `pending_gate` is not an artifact status — the badge is dead code — 3 cases

`Artifact.Status` is `DRAFT / STAGED / APPROVED / PUBLISHED` (`backend/apps/registry/models.py:35-39`).
The `Pending gate` badge (`ArtifactsRegistry.tsx:20-24`) and the matching traceability node colour
(`TraceabilityView.tsx:13-17`) can never render.

**Affected:** TC-142 (demands the badge), TC-158 (demands the legend colour), TC-146 (precondition
"an artifact still sitting at its gate" is not distinguishable in the UI — both states badge `Draft`).

**Fix:** rewrite TC-142/TC-158 to assert the badge/legend entry is *unreachable* and raise the dead code
as a product defect. Give TC-146 a real oracle (the Gates screen).

> **Fixed in 4ac75f9.** The dead `pending_gate` badge and legend entry were deleted. Opening a gate now
> marks the run's drafts `staged` (`open_gate_core`), shown everywhere as `Waiting for approval`
> (`artifactStatus.tsx`), so an artifact at its gate *is* distinguishable. TC-142, TC-146 and TC-158 were
> rewritten to match.

### S3 · The trigger guard is per **work item**, not per **phase** — 3 cases

- UI blocks on the same phase: `PhasesAndRuns.tsx:82-92` — `latestRunForPhase(phase.agent_key)`
- Backend blocks on the whole item: `orchestration/trigger.py:43-57` — `_guard_no_active_run(tenant_id, work_item_id)`

**Affected:** TC-204 asserts a modal reading `Ideation is already running` after clicking *Requirements*.
Impossible twice over — the modal title is built from the phase you clicked
(`PhasesAndRuns.tsx:268`), and no modal fires at all; the user gets a red `Trigger failed` banner
carrying the raw 409. TC-106's Notes wrongly imply the two guards agree.

**Consequence for scheduling:** every gate-producing run on the shared epic must be **sequential**.
TC-130, TC-133, TC-137, TC-139, TC-140 cannot be prepared in parallel. Neither suite says so.

**Fix:** rewrite TC-204, correct TC-106's Notes, add a case for the cross-phase 409, and state the
serialisation constraint in the plan's schedule.

### S4 · `takeover_flag` guards nothing — 2 cases built on a mechanism that doesn't exist

The only reader in the entire backend is the manifest renderer (`backend/manifest/composer.py:162-163`).
Trigger admission is decided purely by run status (`trigger.py:43-57`).

**Affected:** TC-195 ("a successful dispatch is the observable proof that the release happened" — false;
dispatch succeeds either way, so the case has no assertion). TC-196 (instructs a pointless
**Reconnect & re-run** before TS-15). The flag is also already set by the timeout park itself
(`activities.py:588-590`), before any human acts.

### S5 · `/recovery` targets "the first stalled-or-failed run in the project", and `?run=` is dead — 4 cases

- `OfflineTakeover.tsx:28-31` — `(runs.data ?? []).find(r => r.status === "stalled" || r.status === "failed")`
- When `?run=` is set, `parkedRun` is forced undefined → the screen renders **`No parked runs`** (`:47-56`)

**Affected:** TC-194, TC-196 (will act on a stale run from TC-195), TC-198 (its repro is impossible —
"Take over instead" navigates with no run parameter, `RunConsole.tsx:266`), TC-200 (precondition
"no run is parked or failed" is unachievable once TC-196 creates a permanent `FAILED` run,
`workflows.py:117`).

---

## Part 2 — Individually wrong cases

Grouped by why a tester would get the wrong answer.

### Asserts copy or state the app never produces

| TC | Defect | Evidence |
|---|---|---|
| **TC-003** | "An error is shown against the Password field" — Signup renders an error on the **email** field only, and only for a 409. A 400 leaves the form untouched. | `Signup.tsx:96-102, 112-115` |
| **TC-006** | "The meter fills further at 2 → 3 → 4" — `abc` scores **0**, identical to empty. | `identity/hooks.ts:147-156` |
| **TC-018** | "Re-opening the reset link shows `This reset link is invalid`" — it shows the **form**; the invalid card needs a failed submit first. | `ResetPassword.tsx:25-40` |
| **TC-030** | Expects `Reviewer — nobody`; actual is `Reviewer — nobody (no Reviewer assigned — an admin can approve the merge gate)`. | `RolesMatrix.tsx:182-184`, `tenancy/services.py:396` |
| **TC-032** | The gap banner **can never render** — `gate_blocked` requires no admin fallback, and P1 always exists. The case has no object. **Fixed in b40c557** — the banner now shows whenever a gate role is empty. | `tenancy/services.py:374-389`, `RolesMatrix.tsx:156` |
| **TC-043** | The `A description is required` error is gallery-only; on `/profile` **Save** silently no-ops. **Fixed in b40c557** — Save now shows the error on the field. | `ProjectProfileEditor.tsx:87, 107` |
| **TC-050** | The topology chip does **not** flip at step 3 — `showAdd` is never reset, so the view stays `add-form` and reads `single` with two repos. **Fixed in 4ac75f9** — the add form closes and the topology shown is the platform's. | `Repositories.tsx:171-174, 83-92` |
| **TC-063** | `fail_reason` is not in the serializer, so the hardcoded 401 string always renders — even for a 404/429. | `serializers.py:152-153`, `Integrations.tsx:86` |
| **TC-087** | The board's Defect chip is **navy**, not orange. Orange is the detail screen only. | `WorkItemsBoard.tsx:61` |
| **TC-096** | Both expected badges are unreachable: `"running"` is not a WorkItem state (a live run sets `in_progress` → renders `Draft`), and a plan-tier epic never reaches `done`. `Awaiting gate` is also never produced — cards read `Phase gate`. | `WorkItemsBoard.tsx:40-42`, `workitems/models.py:21-27`, `views.py:847-855` |
| **TC-101/102** | `claude · local` is gallery copy. Real value is `claude · claude-sonnet-4-6`. | `catalog.py:23`, `trigger.py:206` |
| **TC-126** | `Preview artifact under review ↗` opens the **whole registry**, not the artifact. | `Gates.tsx:338` |
| **TC-138** | The not-found branch renders **no breadcrumb**. | `CriteriaGate.tsx:51-61` |
| **TC-149** | `Preview unavailable` is unreachable for an internal artifact — it 404s and renders `Artifact not found`, which the case calls a FAIL. **Fixed in 4ac75f9** — the endpoint answers with an empty body (`allow_empty`) and the screen shows `Preview unavailable`. | `integrations/preview.py:305-309` |
| **TC-152** | The capability select does **not** default to Internal for phases with an export target — following the step verbatim publishes **externally**. | `ExportPublish.tsx:55, 161-164` |
| **TC-168** | The Gates badge is **not** "gates needing you" — no user or role filter, and capped at 20. **Fixed in 4ac75f9** — filtered by `gate_roles_decidable_by`, true totals. | `api/views.py:508-511` |
| **TC-177** | A Companion card **is** rendered in the no-project state, contradicting TC-173's note. One of the two is always wrong. | `Dashboard.tsx:23-25, 370-378` |
| **TC-183** | "the row appears without a manual refresh" — the create mutation invalidates `["work-items"]`; the table reads `["test-cases"]`. Nothing invalidates it. **Fixed in 4ac75f9** — `useCreateTestCase` invalidates both. | `lifecycle/hooks.ts:37, 45` |
| **TC-187** | `/runs` filters to one selected work item (defaulting to the first in the project) — the tester must select the test-case item first. | `PhasesAndRuns.tsx:24-30` |
| **TC-207** | The heading counts **all** children, not just tasks — it drifts once TC-209 creates test cases. | `TaskBreakdown.tsx:19, 57` |

### Demands a state the app cannot reach

| TC | Defect |
|---|---|
| **TC-038** | **Critical.** There is *no* duplicate-project check — `Project.name` has no unique constraint and `create` is stock DRF. A second `Payment Gateway v2` is created and the tester lands on `/profile`. The expected result is fiction, and it poisons the rest of the suite (two same-named projects in the selector). `apps/projects/models.py:21`, `api/views.py:178-186` |
| **TC-066** | The 409 race is unperformable — **Save** is disabled until a vendor is selected. `ConnectCapability.tsx:105, 198` |
| **TC-078** | Disconnect revokes **one enrollment row**, not the machine. By TC-078 the suite has created two; the card does not disappear. `enrollment.py:108-116`, `runner_views.py:187-193` |
| **TC-091/093/095** | `No phases run yet.` is unreachable — the lifecycle endpoint computes `tier` and **never uses it**, emitting one node per registered spec. This also means a task's "Build tier" rail renders **plan** phases, and TC-093 only checks the panel *title*, so it passes while the bug is on screen. `api/views.py:1106-1107, 1132-1174` |
| **TC-132** | The UI gap is deterministic, not "likely" — `canDecide` has no admin branch, so the Expected can never be observed. `Gates.tsx:97-98` |
| **TC-135** | The stale-tab path is unreachable — `refetchOnWindowFocus` removes the card before Approve can be pressed. |
| **TC-090/111/122/124** | FAIL criteria referencing demo rows (`WI-492`, `RUN-42`, `awaiting_gate`…) that exist only behind `forceView`. Cannot fire. |
| **TC-016** | `RedirectIfAuthed` does not consume `isLoading`, so a signed-in user **does** briefly see the login card. Flaky by construction. `routes.tsx:73-77` |
| **TC-020** | The email field is pre-filled (`ResetPassword.tsx:19`), so the "PASS only if empty" branch is dead. It is a defect-confirmation dressed as a pass/fail. |
| **TC-051** | The Notes blame a missing endpoint. `POST .../set-default` **exists** (`api/views.py:647-648`); the gap is purely unwired frontend. Filing it "known inert, do not raise" buries a real defect. **Fixed in 4ac75f9** — Set default is wired. |

---

## Part 3 — Can the assigned tester execute it?

### Blocking

- **TC-055** contradicts itself: preconditions require steps 1–3 complete, but once they are, the
  checklist is **replaced** by the completion card and step 4 is no longer on screen to read
  (`SetupChecklist.tsx:109-118`). Unexecutable as ordered. Also depends on Tester C enrolling a
  companion in Tester A's workspace — stated as a parenthetical.
- **TC-086 / TC-089** (Tester B) require phase history that only exists in **Tester C's tenant**.
  TC-096 acknowledges this and prescribes pairing; these two do not. Tester B has no executable path.
- **TC-153 vs TC-156** have mutually destructive preconditions — TC-156 tells the tester to disconnect
  the connector TC-153 needs, and TS-04 owns it. No sequencing stated.
- **TC-077 → TC-078** is missing a step: TC-077 stops the companion and mints a fake token; TC-078
  assumes it is running again on TC-076's token.
- **TC-197**'s repro (bad base branch) is not verifiable — that fails on clone, giving `FAILED`, not a
  resumable park. Resumable parks arise at exactly four call sites (`build_workflow.py:205, 264, 311`,
  `workflows.py:157`).

### Unfalsifiable or ambiguous oracles

- **TC-026 / TC-027** — "No error appears anywhere" can never fail; `resend`/`revoke` have no `onError`
  and the screen has no error surface (`UsersInvites.tsx:255-258`). A failing revoke is silent.
- **TC-157** — "FAIL if nodes render with no edges" — edges exist only if the agent chose to call
  `add_trace_edge` (an LLM-authored step, `agents/03_prd/agent.md:82`). The case cannot distinguish an
  agent-behaviour defect from a `/traceability` defect.
- **TC-116** — the quoted FAIL string is a fallback for a non-`Error` throw; real failures surface the
  server text (`Clarifications.tsx:298-302`).
- **TC-030** — the `saving` banner is a single-frame flash and is mutually exclusive with the matrix it
  asks you to observe. No throttling instruction (contrast TC-007/TC-012, which do throttle).
- **TC-166** — "Ask Tester C which run, if any, completed without turns" — no way to determine or induce.
- **TC-172** — step 5 has no corresponding line in Expected.
- **TC-002 / TC-009 / TC-010** quote composed JSX as a single string, inviting false failures over
  punctuation placement.

### Timing — the biggest systemic executability hole

**Seven TS-15 cases (TC-203…TC-210), plus TC-103, TC-100, TC-113, TC-123, TC-127, contain 20–30 minute
agent runs and not one specifies a wait or a timeout.** They say "follow the run console to completion".
TC-103's Notes then remove the only stuck-run signal ("Do not kill a silent run"), so "still running" and
"hung" are indistinguishable **by design**. Two testers will produce different verdicts on the same run.

Also: `/gates` **does not poll** (`lifecycle/hooks.ts:180-187` — no `refetchInterval`, unlike `useRun` at
`:111-119`). TC-123 and TC-127 say "watch the Pending tab" with no reload instruction. And TC-074's
"~2.5 minutes" tolerance is too tight — worst case is heartbeat interval (30 s) + threshold (2 min) +
shell poll (15 s) ≈ 2 m 45 s, inside its own FAIL window.

### No checkpoints in TS-15

TC-203 → TC-212 are 60–90 minute cases with no recorded state between them — no "record the epic id / run
ids here" step, no resume protocol. TC-210 alone requires four logins. An interrupted case has no restart
point short of re-running the phase.

TS-15 also silently re-walks earlier suites (TC-201 ≈ TS-01/TS-05, TC-202 ≈ TS-02, TC-206/TC-210 ≈ the
criteria-gate cases). Each should declare what it adds beyond sequencing.

---

## Part 4 — What's missing

### High risk

1. **09b Test Automation is never run end-to-end.** TS-15 walks 11 phases and skips it; TC-187 only
   dispatches it and stops. Its `qa_lead` gate, its build-tier PR, and its `imports_test_results`
   defect loopback (`catalog.py:96`, `testgate.py:53`) are covered by **no case**. The Testing gate's
   only derived condition is computed from that loopback — so TC-209 observes it in its
   trivially-satisfied state forever.
2. **The repo-assignment review on the Task Breakdown gate** — an entire gate variant with zero
   coverage (`Gates.tsx:264-288`, `RepoAssignmentReview.tsx`). Approving commits every assignment
   (`Gates.tsx:286`), so a wrong default silently sends tasks to the wrong repo. Multi-repo is in scope.
3. **The inline Approve/Reject on `/work-items/:id`** — a second gate-decision path with **no
   `canDecide` check and no comment field** (`WorkItemEpic.tsx:133-157`, `WorkItemTask.tsx:180-212`),
   while still claiming "Decision is logged with your role & comment". Every TS-09 role case uses
   `/gates` only.
4. **Only the first pending clarification is ever rendered** (`Clarifications.tsx:103` — `pending[0]`).
   The badge can read `2` with one card on screen. No case drives two runs into `needs_answer`.
5. **Permission coverage is absent where it matters most.** `create`/`profile` on projects, work-item
   create/patch, phase trigger, run takeover, and companion enroll/revoke all fall through to the
   project default `AllowAny` (`config/settings.py:259`). A P10 Engineer can create projects, rewrite
   the profile every agent reads, enroll a companion, and revoke someone else's. TS-03 has one
   permission case; TS-05, TS-06 and TS-07 have none.
6. **08 Code Review** — a gate role in the catalog (`catalog.py:92`) with no case. TC-208 handles it
   as an aside.
7. **The late-report reconciliation path** — the single most prominent promise on `/recovery`
   ("bringing it back online lets it finish this same run", `OfflineTakeover.tsx:106-110`) has no case.
   TC-195 tests only the *other* button.
8. **CI results ingestion** — no case posts a JUnit file, checks a revoked token is rejected, or checks
   `Last used` flips. The whole point of the CI token is untested (`TestReporting.tsx:50-59`).
9. **The cross-phase 409** — the most likely real trigger failure (see S3). No case.

### Medium

- `/onboarding` is **in the greenfield sidebar for every project** (`AppShell.tsx:59`) and hardcodes
  "Brownfield project…" with no track check (`OnboardingHub.tsx:293-301`). A greenfield tester is one
  click from a wizard telling them their project is brownfield. Nothing defines the expected result.
- `Parked for takeover` + `Resume from where it stopped` (`RunConsole.tsx:118-119, 219-271`) — a whole
  console state with no case; TC-103's FAIL list gives a tester whose run parks no verdict.
- The **auto-retry banner** (`RunConsole.tsx:209-218`) — the failure path build tier hits most.
- The **re-trigger confirmation modal** on a task, including its destructive-action copy
  (`WorkItemTask.tsx:45-55, 231-273`) — forbidden by TC-093, unclaimed by TS-07.
- **Rejection paths**: no case rejects a criteria gate (do the ticks persist?) or a build-tier gate
  (which must unwind a live PR). TC-212 rejects a plan gate only.
- **Companion enrollment ignores the project selection** (`ConnectMachine.tsx:65, 198-240`) — the
  multi-select value is never passed; it always binds `memberships[0]`. TS-05 is single-project, so it
  cannot catch this.
- **Error states that render as success** — a failed request renders the *empty* or *zero* state on
  `/dashboard` (`Dashboard.tsx:37-41`), `/artifacts`, `/traceability` (`:68-74`), `/repositories`
  (`:170`) and the admin user list (`UsersInvites.tsx:204`). Several cases would **pass on a broken
  backend**. This is the single most valuable batch of cases to add.
- **Unknown work-item id** — `WorkItemDetail` has no not-found state; a bad id silently falls through
  to the Epic screen (`WorkItemDetail.tsx:27-29`).
- **Merge gate / merge conflict** (`Gates.tsx:226-234`) — mentioned in TC-125's Notes, never decided.
- `/work-items/:id/breakdown` has **no in-app link** and only one case (which asserts the count only) —
  the greenfield default state ("Connect a task tracker" CTA, `TaskBreakdown.tsx:70-92`) is untested.
- The top-bar project selector emits **one option per role grant** (`AppShell.tsx:271-273`), so a
  two-role user sees the project twice. TC-040 and TC-030 both walk into this.
- Artifact preview branches: multi-state wireframes, external-SoR card, `text/html`
  (`ArtifactPreviewScreen.tsx:13-49, 113-171`). Only markdown has a case.
- `Published this week` / `Recent publishes` filter on **`created_at`**, not publish time
  (`api/views.py:525-530, 570-574`). An artifact created 8 days ago and published today never appears —
  a legitimate FAIL for TC-176 on any long-lived workspace, and TC-211's parenthetical is wrong.
  **Fixed in 4ac75f9** — both now filter on `published_at`.

### Low

- Signup with a blank name; accept-invite and reset with a short password — all 400 **silently**
  (`AcceptInvite.tsx:78-80`, `ResetPassword.tsx:56-59`). Three uncovered dead-ends.
- A signed-in user opening an invite or reset link is bounced to `/` with no explanation
  (`routes.tsx:120-125`).
- Inert "Request a new invite" / "Request a new link" buttons (`AcceptInvite.tsx:83-103`).
- `/admin/anything` falls through to a developer placeholder reading "Foundation route mounted.
  Feature screens land in T2-T5." (`routes.tsx:101-115`) — reachable in production. **Fixed in
  4ac75f9** — unknown admin routes redirect to `/admin/users`; the placeholder is deleted.
- `RequireAdmin` copy says "manages workspace users and roles" but also guards `/test-reporting`
  (`routes.tsx:86-90, 160`).
- TC-123's `Screen` field says `/dashboard`; the route is `/` (`routes.tsx:131`).
- No sorting/pagination coverage anywhere; `/artifacts` is unpaginated and filtered client-side.

---

## Part 5 — Recommended order of work

1. **Rewrite the 8 S1 cases** (`approved` → `Published`). Highest count, lowest effort, and they are all
   Critical priority.
2. **Fix or delete the 12 unreachable-state cases** — TC-032, TC-038, TC-043, TC-050, TC-066, TC-078,
   TC-091/093/095, TC-132, TC-135, TC-142, TC-158. Each currently guarantees a wrong verdict.
3. **Add a timeout policy** — one line in the plan ("a phase that shows no console activity for N
   minutes is Blocked, not Failed"), then a per-case max wait on every run-dependent case.
4. **Resolve the cross-tester blocks** — TC-055, TC-086, TC-089, TC-153/TC-156. Either move them to
   Tester C or give them a self-contained fixture.
5. **State the one-active-run-per-work-item constraint** in the schedule; it serialises most of TS-09.
6. **Add the High-risk missing cases** (Part 4), starting with the error-states-render-as-success batch —
   several existing cases pass on a broken backend today.
7. **Add checkpoints to TS-15** — a "record these ids" step per case and a stated resume point.

Then re-run `python docs/qa/build_tracker.py`.

---

## Part 6 — Product defects found during the audit

These are bugs in the **app**, not the pack. Worth logging in `docs/Bugs.xlsx` independently of the QA cycle.

1. No uniqueness constraint on project name — duplicates are created silently.
2. `set-default` repository endpoint exists but no frontend caller — an unwired control. **Fixed in 4ac75f9.**
3. Lifecycle endpoint computes `tier` and never applies it — tasks show plan phases.
4. `create`/`profile`/work-item/trigger/takeover/enroll endpoints inherit `AllowAny`.
5. Test-case creation invalidates the wrong query key — the new row needs a manual reload. **Fixed in 4ac75f9.**
6. `takeover_flag` is set and released but never read as a guard.
7. `/recovery?run=` is inert; there is no way to take over a *named* run.
8. Dead code: the `pending_gate` artifact badge, the `"running"` work-item badge, the roles gap banner,
   the `A description is required` validation, the `Preview unavailable` state for internal artifacts.
   **Mostly fixed:** the `pending_gate` badge and the `Preview unavailable` state in 4ac75f9; the roles
   gap banner and the description validation in b40c557. The `"running"` work-item badge is also
   resolved in 4ac75f9: the board card's status pill now reads `Running` from the card's latest run
   (`WorkItemsBoard.tsx:112-114`), so running work is no longer shown as `Draft`.
9. Silent failure paths: invite resend/revoke, repository 403, `GenerateCell` trigger errors, short
   passwords on accept-invite and reset, blank signup name.
10. Failed requests render as empty/zero states across the dashboard, artifacts, traceability,
    repositories and the admin user list.
11. `/onboarding` is in the greenfield sidebar and hardcodes brownfield copy.
12. Dashboard "gates" badge is unfiltered by role and capped at 20. **Fixed in 4ac75f9.**
13. Companion enrollment ignores the project multi-select.
14. `Published this week` filters on `created_at`, not publish time. **Fixed in 4ac75f9.**
15. Developer placeholder reachable at `/admin/<anything>`. **Fixed in 4ac75f9.**

---

## Part 7 — Audit claims that did not survive re-checking

Recorded so nobody re-litigates them. Each was re-opened against source while applying the fixes.

- **TC-009 / TC-010 are fine.** The audit grouped them with TC-002 as "composed JSX quoted as a single
  string". They are not — the login errors are plain string literals, quoted correctly.
- **There is no missing not-found state on an unknown work-item id.** The fall-through in
  `WorkItemDetail` is real, but `WorkItemEpic` does guard and renders `Work item not found.`
- **TC-078's mechanism was wrong**, though its outcome was right. Label-less enrollments group by
  project, and revoke clears the group's representative row — so the screen lands on the *offline*
  layout, not the not-started one the audit predicted.
- **The build-tier gate is not mis-roled.** Implementation's merge gate correctly requires `tech_lead`
  and 09b's requires `qa_lead`; the `reviewer` default is unreachable through the UI.
- **`/admin/<anything>` is admin-only.** Still a defect, but it sits behind the admin guard — a
  non-admin gets the access panel, not the placeholder. (The placeholder itself was removed in
  4ac75f9.)
- **Companion revoke's `AllowAny` is real but not browser-reachable** — `/connect` lists only your own
  enrollments, so there is no UI path to revoke someone else's machine. Documented in a case's Notes
  rather than written as an unexecutable case.

Three defects the audit **missed** and the fix pass found:

- **`Platform only` is dead code**, and every artifact renders a Confluence-styled system-of-record
  chip carrying the raw `sor` token regardless of its actual SoR. This invalidated the SoR expectation
  in four TS-10 cases.
- **The publish screen's `Target capability` select pre-selects the external target**, so following
  TC-152's original steps verbatim would have published externally.
- **The internal-fallback publish path is unreachable** — it is gated on status `approved`, which
  nothing in production ever writes.
