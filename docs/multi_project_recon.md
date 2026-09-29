# Multiple projects per workspace — recon report

**Date:** 2026-08-06 · **Branch:** `brownfield-agent-onboarding` (tip `2977caf`) · **Status:** recon only,
no code changed.

> ## Status as of 2026-09-17 — partly closed, NOT finished
>
> Re-checked against the current code, finding by finding. **This file is still live** — do not
> archive it.
>
> **Closed since it was written (5):**
>
> | Finding | Now |
> |---|---|
> | §2.2 Connect Machine could only ever enroll the *first* project | Fixed |
> | §2.4 No project-name uniqueness | Fixed |
> | §2.6 `Project.track` is write-only | **The finding was overstated** — the track *is* read, at `mcp_platform_state/tools.py:175` |
> | R2 Clarifications inbox repeating the bug Gates had already fixed | Fixed |
> | R3 `/me` returning one row per (user, project, role) | Fixed |
>
> **Still open — including the question that started this recon:**
>
> - **§2.1 — there is still no way to create a second project from inside the app.** The only
>   "Create project" control in the tree is `frontend/src/components/TenantProjectBar.tsx`, a
>   development-era bar that shows raw tenant ids and is not part of the shipped shell. **The
>   team's original complaint is not fixed.**
> - §2.3 one running companion serves one project · §2.5 no archive, rename or delete
> - R1, R4, R5, R6
> - §8 — the per-project companion decision (not yet taken)
> - §9 — making the execution mode visible and deliberate (recommendation, not built)

**The question the team asked:** a user creates one project — greenfield or brownfield — and then wants
a second one. Today there is no way to do that from inside the app, the Project Profile and Onboarding
screens each show one project, and nobody knows whether the top-bar project switcher genuinely re-scopes
the app or only changes a label. The goal is to give users N projects they can switch between, **without
disturbing anything already built**.

**The short answer:** the platform was designed for this from the beginning and most of it already works.
The data model, the endpoints, the switcher and per-project scoping are all in place, and no database
migration is needed. What is missing is mostly **wiring and navigation** — plus exactly one genuine
design decision, about the companion. Detail below; sizing in §6.

**Important caveat on evidence.** Everything here comes from reading the code and from read-only queries
against the shared database. **No multi-project scenario has ever been run**, on any tenant: the query
below found no tenant that has ever held more than one project, so nothing in this area has live
evidence behind it either way.

```
projects in tenant d6a89745 (the Request-changes fixture): 1
  PeopleDesk | track=greenfield | status=active
memberships: 1   ·   active enrollments: 1
```

---

## 1. What is already built and works

These need **no work**. They are the reason this is a small job rather than a large one.

| # | What | Evidence |
|---|------|----------|
| 1 | **The data model is already multi-project.** `Project` is tenant-scoped with `track` and `status`; nothing limits a tenant to one. **No migration needed.** | `backend/apps/projects/models.py:10` |
| 2 | **Work-item numbering is per project.** A `uniq_workitem_number_per_project` constraint means project B starts at WI-1, not WI-69. | `backend/apps/workitems/models.py:59` |
| 3 | **Creating a project already grants the creator a membership.** Without this the new project could never appear in the switcher. It is already there, with a comment explaining exactly why. | `backend/api/views.py:215` |
| 4 | **The create screen already hands off correctly** — refresh `/me`, select the new project, then navigate. This is the fiddly part of "create a second project" and it is already right. | `frontend/src/features/setup/CreateProject.tsx:31` |
| 5 | **The switcher is real, not decorative.** A `<select>` bound to `setSelectedProjectId`, persisted to `localStorage`. | `AppShell.tsx:266` · `AuthContext.tsx:62` |
| 6 | **Most screens are already project-scoped** and their React Query keys include the project id, so switching refetches rather than showing stale rows: Work Items, Runs, Gates, Artifacts, Dashboard, Profile, Repositories, Onboarding, Gap Report, Traceability, Contracts, CI tokens. | `features/*/hooks.ts` |
| 7 | **Backend endpoints are project-scoped by construction** — project actions are `detail=True` (`/api/projects/{id}/…`) and list endpoints accept `?project=`. | `backend/api/views.py:182` |
| 8 | **The runner backend is already multi-project aware.** `list_developer_enrollments` explicitly groups one machine across several projects — "a machine connected to several projects surfaces as one entry with `projects: [...]`". Dispatch picks the enrollment for *that* project. | `apps/runs/enrollment.py:81` · `orchestration/trigger.py:114` |
| 9 | **Temporal workflow ids are `agent-run-{run-uuid}`** — no cross-project collision. | `orchestration/trigger.py:230` |
| 10 | **`GET /api/projects/` already lists a tenant's projects**, and `api.listProjects` already exists in the frontend client. | `views.py:182` · `frontend/src/api.ts:281` |
| 11 | **QA already wrote the acceptance contract** — TC-170 "the top-bar project select switches project and the screens re-scope", and TC-038 on duplicate names. We are building to a spec that exists. | `docs/qa/suites/TS-12-…:162` · `TS-03-…:70` |

---

## 2. What is genuinely missing

### 2.1 No way to create a second project from inside the app — the team's main complaint

`/projects/new` **is mounted** (`routes.tsx:143`) and the screen behind it works. But the sidebar `NAV`
has no entry for it and no screen links to it (`AppShell.tsx:40-69`). It is reachable **only by typing
the URL** — which is exactly how QA reaches it in TC-038.

So the capability exists and the doorway does not. This is the single highest-value, lowest-risk fix
in the report.

### 2.2 Connect Machine can only ever enroll the *first* project — the hardest blocker

The screen renders a **Projects multi-select** and tells the user to "pick the projects this machine will
run phases for" (`ConnectMachine.tsx:203-213`). That control has **no `value` and no `onChange`** — it is
decorative. The handler ignores it entirely:

```ts
const projectId = currentUser?.memberships[0]?.project_id ?? "";   // ConnectMachine.tsx:64
```

**Consequence:** you cannot connect a companion to your second project through the UI at all. And without
an enrollment on project B, no phase can run on B — planning dispatch finds no companion, and brownfield
onboarding fails closed with `NoCompanionError`.

This matters more than anything else in the report: without it, a user can create and switch to a second
project and then not be able to *do* anything in it.

### 2.3 One running companion serves exactly one project

Separate from the UI gap, and a real design question rather than a bug. The daemon runs with **one token**
(`daemon.py:214`), that token resolves to **one enrollment**, and the work-claim endpoint filters by
`runner.project_id` (`runner_views.py:374`, `:575`).

So working on two projects today means **two companion processes**, each launched with that project's own
token. The backend already supports this cleanly; the companion and the instructions on screen do not
mention it. The alternative — one daemon holding several tokens — is a larger change.

### 2.4 No project-name uniqueness

There is no unique constraint and no serializer validation (`serializers.py:297`), so a tenant can hold
two projects with the identical name — indistinguishable in the switcher, which is the only control that
picks between them.

The create screen **already renders a `collision` state** for a 409 (`CreateProject.tsx:25-27`) that the
backend never returns. Half of this fix is already written. QA documented it as a known Medium finding
and noted the sting: there is no rename and no delete, so a mistake is permanent.

### 2.5 No archive, rename or delete

`Project.Status.ARCHIVED` is declared at `models.py:19` and **referenced nowhere else in the codebase**.
The switcher therefore grows forever and nothing can be tidied away.

### 2.6 `Project.track` is write-only — the platform forgets whether a project is greenfield or brownfield

The user picks greenfield or brownfield at creation, it is stored, and **no backend code ever reads it**.
A grep across `backend/` (excluding tests and migrations) returns only the model definition, the
serializer field list, and the seed. The only reader anywhere is a dead legacy component (§3).

Consequences, all of which matter once mixed types share a workspace:
- The nav shows **Onboarding** for every project, so a greenfield project offers the full brownfield
  onboarding hub. `onboarding_hub` has no track check either (`integrations/onboarding.py:1742`).
- Nothing can route a returning brownfield user to onboarding, or a greenfield user to their profile.
- `/me` does not carry `track`, so the switcher cannot even label the two apart.

---

## 3. Exists but is not wired

| Thing | State | Note |
|---|---|---|
| `/projects/new` route | Mounted, no nav entry | §2.1 |
| `api.listProjects` + `GET /api/projects/` | Both work | Unused by the current UI |
| Connect Machine project multi-select | Rendered, unbound | §2.2 |
| `Project.track` | Written, never read | §2.6 |
| `Project.Status.ARCHIVED` | Declared, never used | §2.5 |
| `CreateProject` collision/409 state | UI built, backend never sends it | §2.4 |
| `TenantProjectBar.tsx` + `App.tsx` | **Dead legacy code** | `main.tsx` renders `AppRoutes`, not `App`. It is the Phase-0/1 prototype and happens to contain a working list + create + switch bar — but on the old `useApp` state system, not AuthContext/React Query. **Reference only; do not revive it.** |
| Tenant switcher button | Inert by design | Documented as expected in TC-179 |

---

## 4. Correctness risks once a workspace really holds several projects

These are the ones worth taking seriously, because they are silent.

### R1 · Switching projects never clears the query cache — *mostly* safe

`setSelectedProjectId` only sets state (`AuthContext.tsx:94`). Compare `logout`, which calls
`queryClient.clear()`. Switching does not. That is safe **only** because most query keys carry the
project id — which they do. The exceptions, checked one by one:

| Key | Verdict |
|---|---|
| `["clarifications", {status}]` | ⚠️ **See R2** — the only real problem |
| `["integrations"]` | Safe — `IntegrationConnection` has no project FK (§R4) |
| `["phases"]`, `["users"]`, `["invitations"]`, `["runners"]` | Safe — genuinely tenant-wide |
| `["run", id]`, `["work-item", id]`, `["transcript", id]`, `["artifact-preview", id]` | Safe — keyed by route param |

So there is no broad cross-project leak. Adding a cache flush on switch would make the property
*guaranteed* rather than *currently true by inspection* — cheap insurance.

### R2 · The Clarifications inbox repeats a bug the Gates screen already fixed

`ClarificationsLive` fetches **every pending clarification in the tenant** and filters client-side against
the selected project's work-item list:

```ts
const clarifications = useClarifications({ status: "pending" });                  // :276
const pending = (clarifications.data ?? []).filter(c => workItemIds.has(c.work_item));  // :286
```

The Gates code carries a comment describing exactly why this pattern was abandoned there
(`views.py:1696`): the work-item list **hides carrier work items by design**, so the onboarding gate was
silently dropped — the badge counted 1 while the page said "No gates need you". Approvals were moved to a
server-side `?project=` filter. **Clarifications still uses the old client-side filter**, so a
clarification on a hidden brownfield carrier can vanish the same way.

This is a pre-existing brownfield-relevant bug that multi-project makes worse, not a new one.

### R3 · `/me` returns one row per **(user, project, role)** — not per project

`serialize_me` iterates memberships with no dedupe and no ordering (`apps/tenancy/auth.py:45`), and
`Membership` is unique on `(user, project, role)` — so **two roles on one project produce two rows**.

Three consequences:
- The switcher renders the same project **twice**, with a duplicated React `key` (`AppShell.tsx:272`).
- `selectedProject` resolves by `.find()` and so picks an **arbitrary** one of the user's roles
  (`AuthContext.tsx:55`). That value feeds the gate permission check
  `selectedProject?.role === a.required_role` (`Gates.tsx:110`) — so a user holding both `product_owner`
  and `tech_lead` can be refused a gate they are entitled to approve.
- With no `order_by`, switcher order and the default project (`memberships[0]`) are non-deterministic.

Live data has no user with two roles on one project today, so this has never bitten. It is latent, and it
is not strictly a multi-project bug — but multi-project is what makes it likely.

### R4 · Integrations are tenant-wide, but onboarding reports them per project

`IntegrationConnection` has **no project FK** — it is tenant-scoped (`apps/integrations/models.py:38`),
and `onboarding_hub` queries it with no project filter (`onboarding.py:1780`).

So once *any* project connects Jira, **every** project's onboarding hub reports "Connected" — even though
nothing has been adopted for it. Whether one Jira credential should serve every project, or each project
should bind its own project key / space, is a **product decision**, not a defect. It needs answering
before mixed workspaces are real.

### R5 · The setup checklist speaks for the wrong project

`SetupChecklist` treats "has any membership" as done and names `memberships[0]`
(`SetupChecklist.tsx:50,58`). A freshly created second project therefore shows a checklist that is
already ticked, naming a different project.

### R6 · `/profile?project=X` — the parameter is ignored

`CreateProject` navigates to `/profile?project=${project.id}&setup=1` (`CreateProject.tsx:39`), but
`ProjectProfileEditor` reads only `setup` and takes the project from `selectedProject`
(`ProjectProfileEditor.tsx:60-64`). It works today **only** because the selection was set a line earlier.
A bookmarked or shared profile link silently opens whichever project happens to be selected.

---

## 5. What must not break

The greenfield journey is the thing QA runs on `develop`, and this work touches shared code. Guards that
already exist and must stay green:

- `frontend/src/journey_greenfield.test.tsx` (97 greenfield assertions) and `journey_brownfield.test.tsx`
- `backend/tests/test_journey_greenfield.py`, `test_journey_brownfield.py`
- `backend/tests/test_acceptance_phase47.py` — covers enrollment REST

Every fix proposed in §6 Group 1 is **additive** (a nav entry, a bound form control, a new validator).
None changes an existing endpoint's response shape, and none changes a Temporal payload — so no
worker-before-API ordering is required for them.

The one to watch is §2.4 project-name uniqueness: it makes a previously-accepted request fail with 409.
That is the intended behaviour and the UI already handles it, but the seed and any test that creates
same-named projects must be checked first.

---

## 6. Is this big, or quick?

**Mostly quick.** No migration, no new endpoint, no architectural change. The platform was built for
multi-project; what is missing is the doorway and a few bindings. One item needs a team decision before
it can be sized.

### Group 1 — makes the journey actually work (small, low risk, additive)

| # | Fix | Where | Size |
|---|---|---|---|
| 1 | Add a **New project** entry to the nav and/or the switcher, so `/projects/new` is reachable | `AppShell.tsx` | ~1 h |
| 2 | Bind the Connect Machine project select to state, defaulting to the selected project | `ConnectMachine.tsx` | ~2 h |
| 3 | Reject duplicate project names with the 409 the UI already renders | `serializers.py` / `views.py` | ~2 h |
| 4 | Dedupe + order memberships by project for the switcher (and pick the role deliberately) | `auth.py` or `AuthContext.tsx` | ~2 h |
| 5 | Clear the query cache on project switch — insurance for R1 | `AuthContext.tsx` | ~30 m |

Together: **roughly one to two days including tests.** After these, a user can create any number of
greenfield or brownfield projects, switch between them, and connect a companion to each.

### Group 2 — needs a decision first

| # | Question for the team |
|---|---|
| 6 | **Companion across projects** (§2.3). Accept "one companion process per project" and say so on screen? Or extend the daemon to hold several tokens? The first is hours; the second is a genuine piece of work. **This is the only real fork in the road.** |
| 7 | **Integrations** (§R4). One Jira/Confluence credential per workspace, or per project? Today it is per workspace and onboarding misreports it. |
| 8 | **Track-aware navigation** (§2.6). Should the nav adapt per project? Needs `track` surfaced through `/me` first. |

### Group 3 — worth doing, not blocking

Archive/rename (§2.5) · a projects index screen · moving the Clarifications filter server-side (R2 —
this one is a real pre-existing bug and deserves its own fix regardless of multi-project) · R5 and R6.

### Recommendation

Do **Group 1** as one small change set and get TC-170 passing live — that is the journey the team
described, and it is achievable quickly. Answer question 6 in parallel, because it decides whether
"switch to my other project and run a phase" works end to end or stops at the companion. Treat Group 3 as
follow-up, with R2 pulled forward if brownfield clarifications matter in the near term.

---

## 7. What was NOT verified

Stated plainly, because none of the above has been exercised:

- **No multi-project scenario has been run live.** No tenant in the shared database has ever held two
  projects, so every finding here is from code reading, not observation.
- TC-170 has never been executed.
- The duplicate-name behaviour (§2.4) is read from code and from QA's written expectation, not observed.
- R3 (two roles on one project) has no live instance — the query returned none.
- No test was run and no file was modified to produce this report.

---

# Part 2 — The companion across projects, and the move to cloud

Added 2026-08-06 after the team confirmed the scoping decision: **Integrations, Repositories, Test
Reporting, Users & Invitations, Work Items, Dashboard, Phases & Runs, Gates, Clarifications, Artifacts
& Traceability are all per-project and isolated** — the whole SDLC app re-scopes when you switch.

## 8. Should the companion connection be per project?

### 8.1 The facts the answer rests on

| # | Fact | Evidence |
|---|---|---|
| F1 | An enrollment is `(tenant, project, developer)`. One token resolves to exactly one enrollment. | `apps/runs/models.py:60` · `enrollment.py:40` |
| F2 | The work queue filters on the runner's project — with an explicit comment that broadcast dispatch is "scoped to the runner's project so a companion never steals another project's work". | `runner_views.py:373` |
| F3 | **The serve loop is single-threaded.** Claim one task, run it to completion, claim the next. Only the heartbeat is a background thread. **One companion = one phase at a time.** | `daemon.py:585` |
| F4 | Dispatch already routes per developer — `_pick_enrollment` filters by `developer_id`, so a run goes to the *triggering user's* companion. Several developers per project already works. | `orchestration/trigger.py:114` |
| F5 | The backend already models one machine spanning several projects: `list_developer_enrollments` groups by machine label and returns `projects: [...]`. | `enrollment.py:81` |
| F6 | The Claude subscription login is **per machine/user**, not per project — one `~/.claude/.credentials.json`. | `daemon.py:681` |
| F7 | Repo clones, worktrees and preview config are **inherently per project**. | `daemon.py:216` |

**F6 and F7 together are the whole answer.** The *credential* is per user-machine. The *work context* is
per project. Today's design welds them into one thing — one token, one enrollment, one project, one
process — and that is what forces the awkward choice.

### 8.2 Option A — per-project enrollment **and** per-project process (today)

| Pros | Cons |
|---|---|
| Isolation enforced by the token itself: a leaked token exposes exactly **one** project | The user runs and babysits **N terminal processes** — the friction the team is feeling |
| Matches the platform's project isolation model; no new authorization surface | N processes × single-threaded (F3) = **N concurrent Claude sessions on one subscription**, which risks account concurrency limits |
| Repo maps, worktrees and preview config stay unambiguous — one process, one project's repos | N tokens, each shown once and unrecoverable |
| A crash or hang in project A cannot stall project B | **Silent failure:** switch to project B in the UI, trigger a phase, and nothing happens because B's companion was never started. Nothing on screen says so |
| Per-project revoke is natural — disconnecting B leaves A running | Every new project means another Connect Machine visit and another terminal |
| Already built, already proven, including the anti-theft guard (F2) | Which terminal is running which project becomes tribal knowledge |

### 8.3 Option B — one enrollment spanning all of a developer's projects

| Pros | Cons |
|---|---|
| One process, one command — "my machine is connected to my workspace" | The token becomes **workspace-scoped**: a leak exposes *every* project that developer can reach. Worse given the token is currently passed on the command line, visible to any process listing |
| One subscription session; work naturally serialises, no concurrency pile-up | One long phase blocks **every** project (F3), unless concurrency is added — which brings back the subscription-concurrency problem plus worktree contention |
| A new project needs no new local setup | Revocation goes coarse: disconnect means disconnect from everything |
| The UI switcher and local reality stay in sync | Requires backend surgery on the **run path everything depends on**: enrollment→projects becomes many, the claim query spans projects, dispatch routing and `list_developer_enrollments` all change |
| | Loses the property that a companion *physically cannot see* another project's work |

### 8.4 Recommendation — keep the enrollment per project, stop making it one process per project

**The two questions are separate, and today they are welded together.** Decouple them:

> **Enrollment scope stays per project** (the security boundary — already correct, already proven).
> **One companion process serves several enrollments** (the ergonomics — a config file holding N tokens).

This takes Option B's ergonomics without paying any of its isolation costs.

**Why it is cheap:**
- **Backend: no change at all.** The claim endpoint already authenticates per token and scopes per
  enrollment. The daemon simply holds several tokens and polls each in turn.
- **Daemon:** replace `--token` with a config file listing `{project, token, repos, worktrees}`. That
  **also closes the known finding** that the token sits in the process command line — which matters much
  more once this runs on managed corporate machines.
- **UI: nearly there already.** `list_developer_enrollments` groups a machine across projects (F5). Fix
  the decorative project select (§2.2), then show one merged config block covering every project.
- **Serialisation is a feature here, not a bug.** One process round-robining projects means one Claude
  session at a time — which is what a subscription wants. If a long phase blocking other projects proves
  painful, add a small bounded worker pool later; that is tuning, not architecture.

**What still needs deciding:** whether the daemon polls projects serially (simple, one at a time) or runs
a bounded pool. Recommend starting serial — it is the current per-project behaviour, so nothing regresses.

### 8.5 A note on the team's scoping list — Integrations is the one real schema question

Nine of the ten surfaces named are already project-scoped or nearly so. **Integrations is the exception:**
`IntegrationConnection` has **no project FK** at all — it is tenant-scoped (`apps/integrations/models.py:38`),
queried in 8 non-test places, and `onboarding_hub` reads it with no project filter, which is why every
project reports Jira "Connected" once any project connects it.

Before making it strictly per-project, note what the row actually holds: **a credential *and* a binding**
in one record — `scopes` carries e.g. `{"project_key": "PAY"}` (`catalog.py:60`, `views.py:1637`).

- Making the whole row per-project means every user re-enters the **same Atlassian credential** once per
  project.
- Splitting it — **credential stays per workspace, binding becomes per project** — gives the isolation the
  team wants (project A pushes to `PAY`, project B to `HRD`) without re-entering secrets, and is the
  smaller change.

**Recommend the split.** Either way this needs a migration and a backfill decision for existing
connections, so it is the only item on the team's list that is not just wiring.

"Users & Invitations" is a lighter question: `Membership` is already per project and `Invitation.grants`
already carries `project_id`. What needs deciding is only whether the admin screens list *workspace* users
or *this project's* members — a filter and a product call, not a schema change.

---

## 9. Cloud-hosted platform + the developer's local Claude subscription

### 9.1 The good news: the architecture already does this

Nothing needs inventing. **The companion is a pull-based, outbound agent.** It polls
`GET /api/runner/work/` over HTTPS with a bearer token and a tenant header (`daemon.py:228-239`), and the
platform never opens a connection *to* the developer's machine.

So hosting the platform on a cloud server changes exactly one thing for the user:

```
--api-url https://sdlc.yourcompany.com     # instead of http://localhost:8000
```

Three properties make this work, and all three already hold:

1. **Source code never leaves the machine.** The worktree is local; the platform stores pointers, not
   bodies (non-negotiable #1). Cloud hosting does not change that.
2. **The subscription stays local and stays the user's.** `ensure_local_engine_auth` requires a local
   OAuth login and **refuses to run** if an API key could be reached through any of three channels
   (`daemon.py:638`). Each developer's phases bill *their own* Claude seat — the organisation never gets
   an API bill, wherever the platform is hosted.
3. **Outbound-only, short-poll.** `claim()` returns 204 when idle and the loop sleeps ~5s; requests use
   `urllib` with a 120s timeout (`daemon.py:73`), so TLS verification and `HTTPS_PROXY` are honoured for
   free. No inbound firewall rule, no VPN, and no long-held connection for a corporate proxy to sever.

Django is already environment-driven — `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`
and `DEBUG` all read from env (`config/settings.py:32-192`). **Cloud deployment is configuration, not
code.**

### 9.2 What genuinely needs work before an organisation uses it

| # | Item | Why it matters in the cloud |
|---|---|---|
| C1 | **Get the token off the command line** (already-known finding) | On a shared or managed corporate machine, any process listing reveals a credential that now reaches a public endpoint. Solved by the same config file as §8.4 — one change, two problems |
| C2 | **Enrollment at organisational scale** | 50 developers × N projects is a lot of one-time tokens, each shown once and unrecoverable. Needs a pairing flow (device-code style, or SSO-linked enrollment) rather than copy-paste-a-secret |
| C3 | **`SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` are not set** | Must be on before session cookies cross the public internet |
| C4 | **Token lifetime and rotation** | Enrollment tokens have no expiry. Fine on localhost; not fine as a long-lived credential against a public endpoint |
| C5 | **Companion install and update story** | Today it is "run this Python module from the repo". An organisation needs a packaged installer and a way to keep versions in step with the hosted platform |
| C6 | **Poll cost at scale** | Every companion polls ~every 5s. 50 developers × several projects is a lot of empty 204s. Fine to start; worth revisiting with long-poll or push later |

### 9.3 What a developer actually needs on their machine

For an **implementation phase (07)**, the developer's own machine must have:

| # | What | Why | Permanent? |
|---|---|---|---|
| 1 | **The companion program** — today: the platform repo checked out + Python 3.12 | The README is explicit: "the repo checked out (the companion imports `runner.companion` from the root)" | **No** — a packaging gap (C5). It should become an installer |
| 2 | **Claude Code, logged in** with their own subscription | `ensure_local_engine_auth` refuses to run without a local OAuth login | **Yes** — by design |
| 3 | **git on PATH + a local clone of the *project's* repo** | The companion cuts a worktree from that clone; the agent edits there; commit/push/PR run **from that clone with the developer's own git credentials** (`worktree.py:69-75`) | **Yes** — by design (#1: source never reaches the platform) |
| 4 | Node + Playwright + browsers | Test automation (09b) only — it explores the running app for real locators | Only for 09b |

**Two different "source codes" are easy to confuse here:**
- The **companion's** source (this platform repo) — needed today *only* because the companion is not yet
  packaged. Temporary.
- The **project's** source (the client's application repo) — needed permanently, because that is the code
  being written.

The platform's **backend** (Django, Postgres, Temporal) does **not** need to be local. That is the cloud
server. Only the companion is local.

### 9.4 The real gap: what happens when the person triggering has no companion

**Correction to an earlier draft of this document, which said such a user "cannot run any phase."
That is wrong.** Something always happens — but it is a different something in each of three cases, and
**none of them is shown on screen**. That inconsistency, not an inability, is the actual gap.

| Phase kind | What happens with **no** enrollment for the triggering user | Where |
|---|---|---|
| **Planning** (requirements, PRD, architecture, …) | Silently falls back to **server mode** — the engine runs *inside the platform worker*, on whatever engine credential that host has. The user is told nothing. | `trigger.py:221` → `workflows.py:132` |
| **Build / implementation** (07, 09b, 11) | Dispatch is stamped with a **null enrollment** = *broadcast*: **any** online companion on that project may claim it. So it runs on a **teammate's machine, billing the teammate's subscription**. If nobody's companion is online, it waits indefinitely. | `trigger.py:467` → `runner_views.py:361-371` |
| **Brownfield onboarding** (`00c`, `00_onboarding`) | **Fails closed** with `NoCompanionError`; the REST layer falls back to the deterministic path. The only one of the three that is explicit. | `trigger.py:267` |

Why this matters once an organisation is on a hosted platform:

- **Cost lands unpredictably.** Sometimes the company's engine credential on the server, sometimes a
  named developer's personal Claude subscription — decided implicitly by who happened to press the button.
- **A product owner pressing "Run" can silently consume a developer's personal subscription quota** on a
  machine they do not own.
- **Nothing on screen distinguishes the three.** Same button, same spinner, three different execution
  models and three different payers.

**Recommendation:** make execution mode **visible and deliberate** rather than implicit. Before a run
starts, say which of the three will happen ("this will run on your machine" / "on a teammate's companion" /
"on the server"), and let the organisation set the policy. The mode is already computed and already logged
to `run.triggered` as `execution_mode` — it simply is not surfaced. That makes this a **display and policy
change, not an architectural one**.

The underlying boundary is still worth stating plainly: **reviewing is web-only; running code needs a
machine that has the code.** If an organisation ever wants phases to run with no developer machine at all,
that means a hosted runner — which cannot use a personal Claude subscription and would therefore bill the
API. Commercial decision, not a technical one.

### 9.5 Sizing

- **Move to cloud as it stands:** configuration only — hosting, TLS, env vars, and telling users a
  different `--api-url`. Days, not weeks, and no code change.
- **Ready for an organisation:** C1–C4 are the real list. C1 comes free with the multi-project config file
  from §8.4; C2 is the largest single item and the one worth designing properly.
