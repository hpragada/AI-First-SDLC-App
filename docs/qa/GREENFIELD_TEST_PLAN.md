# Greenfield Test Plan — AI-First SDLC Platform

**Cycle:** Greenfield Cycle 1 · **Team:** 3 testers · **Planned duration:** 10 working days
**Scope baseline:** the shipped app as of this branch (`develop`), verified against source — not against the design docs.

---

## 1. Scope

### In scope — the greenfield journey, end to end

A brand-new workspace running a brand-new project from signup to a published artifact:

| # | Area | Suite |
|---|---|---|
| 1 | Signup, login, password reset, invitations | TS-01 |
| 2 | Workspace admin — users, invites, role matrix, admin gating | TS-02 |
| 3 | Project creation, project profile, repositories | TS-03 |
| 4 | Integrations (capability grid, connect, test-connection, secrets) | TS-04 |
| 5 | Companion machine — enrollment, online/offline | TS-05 |
| 6 | Work items — board, list, create, epic/task/defect detail | TS-06 |
| 7 | Phases & runs — trigger, run console, run states | TS-07 |
| 8 | Clarifications — the agent asking, the human answering | TS-08 |
| 9 | Gates — plain gates, criteria gates, role enforcement, rejection | TS-09 |
| 10 | Artifacts — registry, preview, publish/export | TS-10 |
| 11 | Traceability graph and run transcripts | TS-11 |
| 12 | Dashboard, app shell, navigation | TS-12 |
| 13 | Test cases screen, test automation trigger, CI test-reporting tokens | TS-13 |
| 14 | Recovery — stalled runs, takeover, resume | TS-14 |
| 15 | Full-lifecycle end-to-end journeys | TS-15 |

### Explicitly out of scope this cycle

- **The entire brownfield track.** Do not create a Brownfield project. `/onboarding`,
  `/onboarding/documents`, `/onboarding/gap-report`, `/contracts` (API contracts & drift) and the
  Confluence/Jira *register-don't-recreate* flow are all brownfield surface and are still being
  built. The only brownfield case in this pack is TS-03's check that the Brownfield toggle exists
  and routes correctly — nothing beyond the first screen.
- Performance and load testing (no NFR targets are declared for the platform itself yet).
- Penetration testing. A handful of permission checks are included as `Type: Permission` cases
  because they are part of the product's promise; deep security testing is a separate engagement.
- The agents' *content* quality (is this a good PRD?). We test that the phase runs, produces an
  artifact, gates it, and publishes it — not whether the prose is good. Content quality is a
  product review, not a QA pass.
- `/dev/components` (the internal design gallery) except for one case confirming it is not linked
  from the product.

### Known-broken, do not re-raise

These are already logged. Confirm the behaviour matches the description; if it does, mark the case
**Blocked** with the reference rather than raising a new defect.

| Behaviour | Reference |
|---|---|
| Each `test_case` artifact preview shows a batch of ~25 unrelated test cases | `docs/TESTING_PHASE_BUGS_HANDOFF.md` Bug 1 |
| Testing-phase cases read as engineer-facing (API-level), not manual-QA-executable | Bug 2 |
| The run console is silent for 20+ minutes during a long phase | Bug 3 |
| A phase can reach its gate with an empty phase document | Bug 4 |

---

## 2. Environment

Everything runs locally. There is no shared staging for this cycle.

### Stack

```bash
# from the repo root
docker compose up -d                      # postgres · temporal · minio
docker compose --profile app up -d        # backend · worker · frontend
```

| Service | URL | Notes |
|---|---|---|
| **App (what you test)** | http://localhost:5173 | The only URL a tester normally needs |
| Backend API | http://localhost:8000/api | For evidence gathering only |
| Temporal UI | http://localhost:8080 | Useful when a run hangs — attach a screenshot to a defect |
| MinIO console | http://localhost:9001 | `minioadmin` / `minioadmin` |

**Health check before you start each day** — record the result in the tracker's Daily Log tab:

1. http://localhost:5173 loads the login page.
2. You can log in and the sidebar renders.
3. The companion pill at the bottom of the sidebar reads `Companion: Ready` (Tester C only).

If any of these fail, the environment is broken. Do **not** log the day's cases as failures — log
the day as blocked and raise an environment issue.

### The companion (Tester C only)

Phase runs execute on a local companion daemon using a logged-in Claude Code — not an API key.
Testers A and B do not need one; their suites never trigger a run.

```bash
# prerequisites: Python 3.12, git on PATH, Claude Code logged in (`claude`)
python -m runner.companion serve \
  --api-url http://localhost:8000 --tenant <TENANT-ID> --token <rnr_...> \
  --worktrees ~/sdlc --repo-path ~/repos/<your-test-repo>
```

Leave it running in its own terminal for the whole session. If it stops, every triggered run will
stall — which is a real test (TS-14), but not one you want to run by accident.

> **Known trap:** if `POST /api/runners/` fails, the Connect screen silently shows a fake token
> `rnr_3f9a…b2` and advances to the success state anyway. If the companion rejects your token,
> check whether you were handed that literal fake value — that is a real defect (TS-05).

---

## 3. Test data and personas

### Workspaces

Each tester works in **their own workspace** (tenant). This keeps three people from colliding on
gate decisions and run state, and it means each of you exercises signup for real.

| Tester | Workspace name | Signup email |
|---|---|---|
| A | `QA Alpha` | `qa+a.owner@edvensoft.com` |
| B | `QA Bravo` | `qa+b.owner@edvensoft.com` |
| C | `QA Charlie` | `qa+c.owner@edvensoft.com` |

If your mail provider does not support `+` aliases, substitute any three addresses you control —
the invitation flow needs a real inbox for the one-time link.

### Personas

Gate decisions are role-gated, so you need more than one identity. Invite these from
`/admin/users` after creating your workspace. Substitute your own initial for `<x>`.

| ID | Role granted on the project | Email | Exists to prove |
|---|---|---|---|
| **P1** | *(the signup account)* tenant admin + `admin` on the project | `qa+<x>.owner@…` | Admin can do everything; tenant-admin bypasses gate roles |
| **P2** | `product_owner` | `qa+<x>.po@…` | Ideation / Requirements / PRD gates |
| **P3** | `architect` | `qa+<x>.arch@…` | Architecture gate |
| **P4** | `designer` | `qa+<x>.design@…` | UX Design gate (the WCAG criteria gate) |
| **P5** | `tech_lead` | `qa+<x>.lead@…` | Task Breakdown & Implementation gates; repository management |
| **P6** | `reviewer` | `qa+<x>.rev@…` | Code Review gate |
| **P7** | `qa_lead` | `qa+<x>.qa@…` | Testing & Test Automation gates |
| **P8** | `security_engineer` | `qa+<x>.sec@…` | Security gate |
| **P9** | `devops` | `qa+<x>.devops@…` | CI/CD & Deployment gates |
| **P10** | `engineer` | `qa+<x>.eng@…` | **The negative persona** — holds no gate role, so every gate must be read-only for them |

Password for every persona: `QaTest-2026!`

**Tester A and B** only need P1, P5 and P10 — they do not run phases, so they never reach a gate
that needs the others. **Tester C** needs all ten.

### The project under test

| Field | Value |
|---|---|
| Project name | `Payment Gateway v2` |
| Track | **Greenfield** |
| Profile description | `A card payment gateway that accepts Stripe webhooks, reconciles charges, and exposes a refunds API.` |
| Domain | `Payments` |
| Tech stack | `Django 5, React 18, Postgres 16` |
| NFRs | `P95 API latency under 200ms. 99.9% uptime. PCI-DSS SAQ-A scope.` |
| Repository | `acme/payments-api`, role `backend`, base branch `main` |
| Epic | `Stripe Webhook Integration` |

Use these exact values. When three people report the same defect, identical test data is what makes
the reports collapse into one instead of three.

> Repo topology is **derived from repo count**, not chosen at creation: 0–1 repo = `single`,
> 2 = `split`, 3+ = `multi`. There is no topology picker on the Create Project screen — the docs are
> stale on this point.

---

## 4. Priority and severity

### Test case priority — what it costs us if this case is never run

| Priority | Meaning |
|---|---|
| **Critical** | The journey cannot proceed at all if this breaks. Signup, trigger a phase, approve a gate. |
| **High** | Core journey broken but a workaround exists, or a permission boundary. |
| **Medium** | A supporting feature, a state that renders wrong, an error message that misleads. |
| **Low** | Cosmetic, copy, an edge case with minimal impact. |

### Defect severity — what it costs us if this bug ships

| Severity | Criteria |
|---|---|
| **Critical** | Data loss; an unapproved artifact reaches a system-of-record; a gate can be bypassed; the app is unusable; a tenant sees another tenant's data. |
| **High** | A core lifecycle step is broken with no workaround; the wrong role can decide a gate; a run is lost with no recovery path. |
| **Medium** | A feature is broken but has a workaround; a state renders incorrectly; an error message is wrong or missing. |
| **Low** | Cosmetic; copy; an inert control; an edge case. |
| **Blocked** | Not a defect — the case could not be run (environment, a dependency case failed, a known-broken area). |

**Severity is set by the tester, priority to fix is set by the team.** Do not negotiate severity with
yourself to avoid an awkward conversation — a gate that the wrong role can approve is Critical even
if it is "just the demo workspace".

---

## 5. Who tests what

The split is driven by **session length, not seniority**. Agent phase runs take 20–30 minutes each
and cannot be paused, so everything that depends on a live run belongs to the full-time tester.
A and B get suites that complete inside a 2-hour window with no waiting.

| Tester | Hours/day | Suites | Cases | Why |
|---|---|---|---|---|
| **A** | 2 | TS-01 Identity · TS-02 Admin & Roles · TS-03 Project Setup | 62 | Self-contained forms and permissions. No companion needed. Each case finishes in minutes. |
| **B** | 2 | TS-04 Integrations · TS-06 Work Items · TS-11 Traceability & Transcripts · TS-12 Shell & Dashboard · TS-13 Test Cases & Reporting | 82 | Screen-level and state-level testing. Reads the artifacts and runs that C produces, without triggering any. |
| **C** | 6–8 | TS-05 Companion · TS-07 Runs · TS-08 Clarifications · TS-09 Gates · TS-10 Artifacts · TS-14 Recovery · TS-15 End-to-end | 112 | The lifecycle spine. Needs a running companion and long uninterrupted sessions. |

**256 test cases in total** — 61 Critical, 97 High, 83 Medium, 15 Low. (Up from 212 after the
pre-execution audit: see [`AUDIT_FINDINGS.md`](AUDIT_FINDINGS.md). C's share grew most, because
most of what was missing needed a live run. Three more were added for commits 4ac75f9 and b40c557:
TC-906 Security gate rule, TC-245 `Show the whole registry`, TC-266 the notification bell.)

**The dependency to watch:** B's traceability, transcript and artifact-registry cases need real
artifacts to look at. C produces those from day 3. B should run TS-04, TS-06 and TS-12 first
(days 1–4) and hold TS-11 and TS-13 until C's first lifecycle is through its gates.

### Two constraints that shape every run-dependent case

**1. One run at a time per work item.** The backend refuses a trigger while *any* run on that work
item is active — not just a second run of the same phase. The screen you clicked from does not know
this: the button stays enabled and you get a red `Trigger failed` banner carrying a raw 409. So
**every phase on a given work item must be run sequentially**, and cases that prepare different
gates on the same epic (most of TS-09) cannot be set up in parallel. If you need two runs going at
once, use two different work items.

**2. A run that goes quiet is Blocked, not Failed.** Phase runs take 20–30 minutes and cannot be
paused. Each run-dependent case states its own max wait; where it does not, use this default:

| Situation | Verdict |
|---|---|
| Console shows new activity within the last **10 minutes** | Still running — keep waiting |
| No new console activity for **10 minutes**, run not finished | **Blocked.** Record the run id, move on, tell the standup |
| Run exceeds the case's stated max wait (default **45 minutes**) | **Blocked**, same treatment |
| Run ends in an explicit failed/parked state | **Fail** — that is a real result, write the defect |

Never mark a silent run Fail. "Slow" and "hung" are not distinguishable from the console, and the
difference between them is a scheduling problem, not a product defect. Record the wall-clock wait
in the case's Notes column either way — if several runs cross 45 minutes, *that* is the defect, and
it needs the timings to be believable.

**A related trap:** `/gates` does **not** auto-refresh. If a case tells you to watch the Pending
tab for something to appear, reload the page — the screen will happily show you a stale empty list
for as long as you stare at it.

### Suggested 10-day shape

| Days | A (2h) | B (2h) | C (6–8h) |
|---|---|---|---|
| 1 | Env setup · TS-01 signup/login | Env setup · TS-12 shell & nav | Env setup · companion · TS-05 |
| 2 | TS-01 reset & invitations | TS-06 board & create | TS-07 trigger & run console |
| 3 | TS-02 users & invites | TS-06 detail screens | TS-07 run states · TS-08 clarifications |
| 4 | TS-02 roles matrix & admin gating | TS-04 integrations | TS-09 gates — happy paths |
| 5 | TS-03 create project & profile | TS-04 integrations & secrets | TS-09 role enforcement & criteria gate |
| 6 | TS-03 repositories | TS-11 traceability | TS-09 rejection & re-trigger |
| 7 | Re-test A's fixed defects | TS-11 transcripts | TS-10 artifacts & preview |
| 8 | Re-test | TS-13 test cases | TS-10 publish & export |
| 9 | Exploratory — A's areas | TS-13 CI tokens · re-test | TS-14 recovery & takeover |
| 10 | Regression pass | Regression pass | TS-15 full end-to-end |

Days 7–10 always slip. That is expected — the schedule is a shape, not a contract. Log what you
actually ran.

---

## 6. Daily rhythm

**Start of session (5 min)**
1. Run the §2 health check. Record it on the **Daily Log** tab.
2. Open the tracker, filter the **Test Cases** tab to your Owner.

**During (the whole session)**
3. Execute in TC-ID order within a suite. Skipping around loses the preconditions each case builds on.
4. Log **every** result — Pass, Fail, Blocked, or Not Run. An empty row reads as "nobody looked",
   which is the one thing a tracker must never be ambiguous about.
5. On a failure: screenshot first, then write the Defect row, then put the DEFECT-ID in the case row.
   A failure with no screenshot usually cannot be reproduced two days later.

**End of session (10 min)**
6. Fill in the Daily Log: cases run, passed, failed, blocked, and one line on what got in your way.
7. Post the same one-liner in the team channel. Three people, three lines, no meeting.

**Standup (15 min, daily)** — only three questions: what's blocking anyone, what's the worst thing
found since yesterday, and does the plan for today still make sense.

---

## 7. Defect workflow

1. **Reproduce it once more** before writing it up. Roughly a third of first-look failures are
   stale-state artefacts of the previous test case.
2. **Write the Defect row** on the tracker's Defects tab. Required: title, severity, the TC-ID that
   found it, exact reproduction steps with the test data used, expected vs actual (paste error text
   verbatim), and a screenshot path.
3. **Mark the test case** Fail, and put the DEFECT-ID in its row.
4. **Blocked ≠ Fail.** If a case cannot run because a prior case failed, mark it Blocked and name
   the blocking DEFECT-ID. Do not mark it Fail — that inflates the failure count and hides the
   single root cause behind ten symptoms.
5. **Re-test on fix.** When a defect is marked resolved, re-run the original TC and record the
   result in the case's `Re-test` column. A defect is closed by a passing TC, not by a developer's
   say-so.

Defects that are genuinely platform-wide (not tied to one TC) still get a Defects row — use
`TC-ID = —` and say where you found it.

---

## 8. Entry and exit criteria

### Entry — do not start the cycle until

- [ ] `docker compose --profile app up -d` brings up backend, worker and frontend with no restart loops.
- [ ] Each tester can sign up and reach the dashboard.
- [ ] Tester C's companion reaches `Companion: Ready` and completes one throwaway phase run end to end.
- [ ] The tracker is shared and each tester can see their assigned rows.

### Exit — the cycle is done when

- [ ] Every **Critical** and **High** priority case has been executed (not necessarily passed).
- [ ] ≥ 90% of all cases executed; every unexecuted case has a written reason.
- [ ] **Zero open Critical defects.** No exceptions.
- [ ] Zero open High defects, or each one has a named owner and an agreed ship-or-fix decision.
- [ ] Every fixed defect has been re-tested and its TC re-run.
- [ ] At least one complete TS-15 end-to-end journey has passed start to finish in one sitting.
- [ ] The Summary tab is filled in and the cycle is written up in one page.

---

## 9. Suite index and ID ranges

The original ranges were allocated back to back with no headroom, so every suite is full. New cases
therefore go in each suite's **extension block** — still at the end of the relevant file, still in
TC-ID order. Never reuse an ID from a deleted case.

| Suite | File | Original range | Extension block | Owner |
|---|---|---|---|---|
| TS-01 Identity & Access | [`suites/TS-01-identity-access.md`](suites/TS-01-identity-access.md) | TC-001 – TC-022 | TC-501 – TC-519 | A |
| TS-02 Workspace Admin & Roles | [`suites/TS-02-admin-roles.md`](suites/TS-02-admin-roles.md) | TC-023 – TC-036 | TC-521 – TC-539 | A |
| TS-03 Project Setup | [`suites/TS-03-project-setup.md`](suites/TS-03-project-setup.md) | TC-037 – TC-055 | TC-541 – TC-559 | A |
| TS-04 Integrations | [`suites/TS-04-integrations.md`](suites/TS-04-integrations.md) | TC-056 – TC-068 | TC-561 – TC-579 | B |
| TS-05 Companion Machine | [`suites/TS-05-companion.md`](suites/TS-05-companion.md) | TC-069 – TC-078 | TC-581 – TC-599 | C |
| TS-06 Work Items | [`suites/TS-06-work-items.md`](suites/TS-06-work-items.md) | TC-079 – TC-096 | TC-601 – TC-619 | B |
| TS-07 Phases & Runs | [`suites/TS-07-runs.md`](suites/TS-07-runs.md) | TC-097 – TC-112 | TC-701 – TC-719 | C |
| TS-08 Clarifications | [`suites/TS-08-clarifications.md`](suites/TS-08-clarifications.md) | TC-113 – TC-122 | TC-801 – TC-819 | C |
| TS-09 Gates | [`suites/TS-09-gates.md`](suites/TS-09-gates.md) | TC-123 – TC-140 | TC-901 – TC-919 | C |
| TS-10 Artifacts & Publish | [`suites/TS-10-artifacts.md`](suites/TS-10-artifacts.md) | TC-141 – TC-156 | TC-241 – TC-249 | C |
| TS-11 Traceability & Transcripts | [`suites/TS-11-traceability-transcripts.md`](suites/TS-11-traceability-transcripts.md) | TC-157 – TC-166 | TC-251 – TC-259 | B |
| TS-12 Shell, Navigation & Dashboard | [`suites/TS-12-shell-dashboard.md`](suites/TS-12-shell-dashboard.md) | TC-167 – TC-180 | TC-261 – TC-269 | B |
| TS-13 Test Cases & Test Reporting | [`suites/TS-13-test-cases-reporting.md`](suites/TS-13-test-cases-reporting.md) | TC-181 – TC-192 | TC-213 – TC-215 | B |
| TS-14 Recovery & Takeover | [`suites/TS-14-recovery.md`](suites/TS-14-recovery.md) | TC-193 – TC-200 | TC-216 – TC-217 | C |
| TS-15 End-to-End Greenfield Lifecycle | [`suites/TS-15-e2e-lifecycle.md`](suites/TS-15-e2e-lifecycle.md) | TC-201 – TC-212 | TC-218 – TC-229 | C |

The blocks are not tidy — TS-13/14/15 extend just past the original end of the pack, the rest use
5xx–9xx. That is deliberate: the tracker parses `TC-\d+` only, so every ID must be plain digits and
unique, and no scheme that satisfies both is also pretty.

---

## 10. Reference — facts the test cases rely on

Verified against the code, because several published docs are out of date.

**The 19 phases in the catalog and who decides their gate:**

| Phase (button label) | `agent_key` | Gate role |
|---|---|---|
| Onboarding | `00_onboarding` | Product Owner |
| Context Bridge | `00b_context_bridge` | Architect |
| Context Extraction | `00c_intelligent_context_extractor` | Tech Lead |
| Document Vision | `00e_document_vision` | Product Owner *(platform-native)* |
| Ideation | `01_ideation` | Product Owner |
| Requirements | `02_requirements` | Product Owner |
| PRD | `03_prd` | Product Owner |
| Architecture | `04_architecture` | Architect |
| UX Design | `05_ux_design` | Designer *(22 required WCAG 2.2 criteria)* |
| Task Breakdown | `06_task_breakdown` | Tech Lead |
| Implementation | `07_implementation` | Tech Lead *(build)* |
| Code Review | `08_code_review` | Reviewer *(dispatched inside the build loop — not triggered directly)* |
| Testing | `09_testing` | QA Lead *(2 derived conditions: no blocking test failures · no blocking accessibility failures)* |
| Test Automation | `09b_test_automation` | QA Lead *(build)* |
| Accessibility Judge | `09c_a11y_judge` | QA Lead *(platform-native; dispatched by the accessibility pass)* |
| Accessibility Journey | `09d_a11y_journey` | QA Lead *(platform-native; dispatched by the accessibility pass)* |
| Security | `10_security` | Security Engineer *(1 derived condition: no unresolved Critical/High security finding)* |
| CI/CD | `11_cicd` | DevOps *(build)* |
| Deployment | `12_deployment` | DevOps *(7 required readiness criteria)* |

> **Three of these are platform-native and are not meant to be triggered by hand.**
> `00e_document_vision`, `09c_a11y_judge` and `09d_a11y_journey` have no migrated legacy body — they
> were authored fresh for the platform. `09c` and `09d` are dispatched by the accessibility pass, the
> way `08_code_review` is dispatched inside the build loop. They nevertheless **appear in the phase
> list**, because the
> catalog seeds every non-retired agent and the API buckets them by key prefix
> (`backend/api/views.py:1896`). Seeing them on `/runs` is expected. **Triggering `09c` or `09d` by
> hand is not a supported path** — if you do it, treat whatever happens as exploratory, not as a
> defect, and note it for the team.
>
> **Count history.** The old count of 16 was wrong twice over: `00e` was missing before this cycle,
> and `09c` was added by the accessibility build in August 2026. The count was then 18 and still
> missed `09d_a11y_journey`, the keyboard-journey agent from the same build — **corrected to 19 on
> 2026-09-17**, verified against `backend/apps/registry/catalog.py` (20 definitions, of which
> `00d_context_snapshot` is `retired=True` and never seeded).

**Run statuses:** `pending` · `running` · `awaiting_gate` · `approved` · `rejected` · `failed` ·
`completed` · `stalled`. Shown in the console as `Dispatched · waiting`, `Running`, `Needs answer`,
`Awaiting gate`, `Completed`, `Failed`, `Parked for takeover`.

**Work item types:** `epic` · `story` · `task` · `defect` · `test_case`. Every work item starts at
state `proposed`.

**Gate approval rights:** the required role **or** the `admin` role on that project **or** any
tenant admin. Everyone else gets a read-only card.

**Companion online window:** a machine is `online` if it checked in within the last **2 minutes**
(not 5, as some docs say). Triggering a phase at an offline companion is blocked by the UI, but the
backend does not block it — the run stalls at its report timeout instead.

**Known inert controls** (do not raise these as new defects; confirm and reference this list):
the top-bar tenant switcher, `Request a new invite` on an expired invitation,
`Request a new link` on an expired reset, and `Promote a member` in the last-admin modal.

Removed from that list, because they now work (commits 4ac75f9 and b40c557): the **notification
bell** opens the dashboard's `Needs me` queue (TS-12 TC-266); the **project select on
`/admin/roles`** was replaced by a plain line naming the project; and **`Set default` on
Repositories** sets the default and moves the marker to the chosen row (TC-051). A failure of any of
them is a real defect and should be raised.
