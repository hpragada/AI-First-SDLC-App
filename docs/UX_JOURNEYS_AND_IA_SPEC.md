# UX Journeys & Information-Architecture Spec

**Audience:** UX/UI designers (to produce hi-fi designs) and the engineers who will build them.
**Status:** Draft v1 — designer-facing. This is a **design specification, not code.**
**Scope:** The entire AI-First SDLC platform web app, not just the guide PDF scenarios. The guide will be re-derived from these flows afterward.

This document defines **who** uses the platform, **how the app is organized** (information architecture), and **the end-to-end journeys** with screen-by-screen states. It is deliberately grounded in the platform's real data model and its **locked architecture** so the designs map 1:1 to what can be built.

---

## 0. Non-negotiable realities every screen must respect

These come from `CLAUDE.md` and the build specs. They shape the UX; designs that violate them can't be built.

1. **Platform owns STATE; external tools own CONTENT; the engine only executes.** The UI shows *pointers, provenance, status, and events* — never treats a local file or an editable text box as the source of truth for an artifact body.
2. **The engine runs on the user's own machine.** Every AI phase executes on the user's local Claude Code via a background **companion** daemon (their subscription, no API key). **Two actions are irreducibly local and can never be in-browser:** (a) signing into Claude Code, (b) running the companion daemon. The UX models these as a one-time **"Connect your machine"** step — token issued in-app, one command pasted into a terminal — and thereafter shows companion **online/offline** status everywhere it matters.
3. **Nothing reaches a system-of-record without an approved gate.** Every artifact moves `draft → reviewed → gated → published`. Gates are first-class screens, not dialogs.
4. **Work is a per-WorkItem DAG, not a linear wizard.** A project has many WorkItems; each advances through phases independently. The UI must make "where is each work item in its lifecycle" legible.
5. **Capabilities, not vendors.** The UI says "Documentation store", "Task tracker", "Design source", "Code host", "Test management" — with the connected vendor (Confluence/Jira/Figma/GitHub/Xray) shown as the *current binding*, swappable.
6. **Multi-tenant with hard isolation.** A user belongs to exactly one tenant; everything they see is tenant-scoped.

---

## 1. Personas & roles

### 1.1 The two "shapes" of user
- **Operators** — people doing SDLC work in the browser: triggering phases, answering agent questions, deciding gates, reviewing artifacts. They each **run their own companion** (their machine = where their phases execute).
- **Administrators** — manage the tenant: invite users, assign roles, connect integrations, manage projects. (An admin is usually also an operator.)

### 1.2 Roles (per-project, from the fixed enum)
`Membership` binds a **User → Project → Role**. The 10 roles and what they gate:

| Role | Primarily gates / does |
|---|---|
| **product_owner** | PRD gate; owns the product intent. |
| **architect** | Architecture gate; **drift** decisions (breaking API-contract changes). |
| **designer** | UX design gate (incl. WCAG criteria checklist). |
| **tech_lead** | Task-breakdown gate; implementation gate. |
| **engineer** | Executes build work items (companion). |
| **reviewer** | Code-review gate; **merge** gate. |
| **qa_lead** | Testing gate; defect triage. |
| **security_engineer** | Security review (where present). |
| **devops** | Deployment/release concerns. |
| **admin** | Tenant administration (see DECISION-1). |

> **DECISION-1 (tenant-level admin).** `Membership` currently *requires a project*, so there is no "org owner". Recommended: introduce a **tenant-scoped admin** (membership with `project = null`, or `User.is_tenant_admin`) who can manage users/roles/integrations across the whole tenant. The journeys below assume this exists. *Backend + design to confirm representation.*

### 1.3 Identity model (confirmed from the data model)
- **Tenant 1—\* User** — a user is hard-scoped to one tenant (`email` globally unique). No cross-tenant users.
- **User \*—\* Project via Membership**, each membership carrying **one role**; a user may hold different roles on different projects.
- Users **do not self-register into an existing tenant** — they are **invited by email** by an admin. (Self-serve signup, if offered, *creates a new tenant* with the signer-up as its first admin — see DECISION-2.)

> **DECISION-2 (tenant bootstrapping).** Who creates the first tenant + first admin? Recommended default: **self-serve signup creates a new tenant** and makes the signer-up its tenant-admin; everyone else joins by invitation. Alternative: platform-provisioned tenants only. *Product to confirm.*

---

## 2. Information architecture

### 2.1 Top-level structure
```
[ Unauthenticated ]
  • Sign up (create tenant + first admin)        ← DECISION-2
  • Log in
  • Accept invitation (set password)
  • Forgot / reset password

[ Authenticated — Tenant workspace ]
  Global chrome:
    • Tenant/workspace name + switcher (only if user later supports multi-tenant; today single)
    • Project switcher
    • Current user menu (name, role badges, log out)
    • Companion status indicator (●online / ●offline)  ← global, always visible
    • Notifications bell (gates awaiting me, questions awaiting me)

  Primary navigation (project-scoped unless noted):
    1. Dashboard            — project health, what needs ME, lifecycle overview
    2. Work Items           — the DAG: list/board of work items + per-item lifecycle
    3. Phases / Runs        — trigger phases, watch runs, live console
    4. Clarifications       — questions awaiting an answer
    5. Gates                — approvals awaiting a decision (incl. criteria gates, drift)
    6. Artifacts            — registry: pointers, versions, SoR deep-links, preview
    7. Traceability         — lineage graph
    8. Project Profile      — description, tech stack, NFRs, context
    9. Onboarding (brownfield projects only) — upload/adopt, code-intel, gap report
   10. Integrations         — connectors (admin), companion connect (per-user)
   11. Repositories         — multi-repo registry (brownfield/build)

  Admin area (tenant-admin only):
    • Users & invitations
    • Roles & memberships (per project)
    • Integrations (tenant-wide connectors + credentials)
    • Projects (create/archive)
```

### 2.2 Navigation principles
- **"What needs me" is the spine.** The Dashboard and the notifications bell always answer: *which gates need my decision, which questions need my answer, which runs are mine and where are they.* Operators live here.
- **Project is the working context;** the project switcher is always one click away. Tenant is mostly invisible (single-tenant per user today).
- **Companion status is ambient.** A persistent indicator (online/offline/last-seen) so a user never wonders "why is my phase not running."
- **Greenfield vs. brownfield** changes which nav items appear (Onboarding shows only for brownfield).

---

## 3. Cross-cutting UX patterns (define once, reused by every journey)

- **Run lifecycle states** (badge vocabulary, used everywhere a run appears):
  `queued → dispatched (waiting for your companion) → running → needs answer (clarification) → awaiting gate → publishing → completed`; plus `failed`, `parked for takeover`.
- **The "needs you" affordances:**
  - *Clarification:* run shows **"● needs answer"**; resolved on the Clarifications screen.
  - *Gate:* run shows **"awaiting gate"**; resolved on the Gates screen (only the role-holder can decide).
- **Companion-aware empty/error states:** any "trigger" action checks companion status first. If offline → inline banner: *"Your machine isn't connected — phases can't run. Connect your machine."* with a link to the connect flow, rather than a silent stuck run.
- **Zero-cost wait, made visible:** while a run is "needs answer", the UI explicitly reassures *"paused — no usage is being billed while waiting."* (This is a real architectural guarantee; surface it.)
- **Provenance, not bodies:** artifact rows show type, version, status, SoR + deep-link. A **Preview** opens a read-only rendered view (read-through from S3/SoR); it is never an editor.
- **Standard states for every list/detail screen:** Loading (skeleton), Empty (with the one next action), Error (with retry + reason), Permission-denied (explains which role is required), Success/toast.

---

## 4. Journeys — Identity & onboarding

### J1 — Sign up & create a workspace (tenant-admin, first run)  *(DECISION-2)*
**Actor:** a new customer. **Entry:** marketing → "Get started". **Pre:** none.
1. **Sign up screen** — name, work email, password. (States: validation errors, email-already-in-use.)
2. On submit → **create tenant** named after their org (or prompt for org name) → user becomes **tenant-admin**.
3. **Welcome / setup checklist screen** (the post-signup home), a guided list:
   - ☐ Create your first project
   - ☐ Connect your machine (companion)
   - ☐ Invite your team & assign roles
   - ☐ (optional) Connect integrations
4. Each item deep-links to its journey; checklist persists until done.
**Screen states:** empty workspace (no projects yet) shows the checklist front-and-center, not an empty nav.

### J2 — Invite a teammate (tenant-admin)
**Actor:** admin. **Entry:** Admin → Users & invitations → "Invite".
1. **Invite form** — email, optional name, optional initial project + role assignments.
2. Submit → invitation created, email sent. Row appears as **"Invited — pending"**.
3. **Resend / revoke** actions on pending invites.
**States:** duplicate-email (user already in tenant), invalid email, invite expired.

### J3 — Accept invitation & set password (invitee)
**Actor:** invited user. **Entry:** email link.
1. **Accept screen** — shows tenant name + who invited them; set password.
2. Submit → logged in, lands on **Dashboard** (or the project they were added to).
**States:** expired/used link → request a new invite.

### J4 — Log in / log out / reset password (any user)
Standard. Login lands on Dashboard; logout clears session. Reset = email link → new password.
> **DECISION-3 (auth tech).** Session cookie vs. token (JWT)? Recommended: server session for the web app; the **companion keeps its existing runner-enrollment token** (separate, already built). *Backend to confirm.*

### J5 — Connect your machine (companion) — *the key local step*
**Actor:** any operator. **Entry:** setup checklist, or Integrations → "Your machine", or the inline banner when a trigger is blocked.
1. **Connect screen** explains plainly: *"Phases run on your computer using your Claude Code subscription. Two one-time steps."*
2. **Step A (in-app):** pick the project(s) → **"Generate enrollment token"** → token shown once, copy button. (REST already exists: `POST /runners/`.)
3. **Step B (your terminal):** the screen shows the exact two commands to paste — `claude` (sign in) and `python -m runner.companion serve … --token …`. Copy buttons. Plain-language note: *"Leave this running in the background."*
4. **Live status:** the screen polls and flips to **"● Connected — last seen just now"** when the daemon checks in. Checklist item ticks.
**States:** waiting-for-first-checkin (spinner + "run the command above"); previously-connected-now-offline (last-seen timestamp + "restart the daemon"); token-not-yet-used.
**Design note:** this is the one place a terminal is unavoidable. Make it feel like a guided device-pairing, not a developer chore. Never imply phases can run without it.

### J6 — Manage users & roles (tenant-admin)
**Actor:** admin. **Entry:** Admin → Users & roles.
1. **Users list** — name, email, status, projects+roles summary.
2. **User detail / role matrix** — per project, toggle the user's role(s). (Backend: create/delete `Membership`.)
3. **Per-project view:** "who can decide which gate" — a matrix of role → people, so an admin can see coverage gaps (e.g., *no reviewer on this project → merge gate will have no one to approve*). Surface that warning.
**States:** removing your own admin (guard), last-admin guard, role with no holder (warning badge).

---

## 5. Journeys — Project setup

### J7 — Create a project (greenfield vs. brownfield)
**Actor:** admin (or a role permitted to create). **Entry:** Project switcher → "New project", or checklist.
1. **Create form** — name, **track: Greenfield | Brownfield**, repo topology (single/multi-repo).
2. **Branch by track:**
   - *Greenfield* → lands on **Project Profile** (J8) with a "next: add a work item" nudge.
   - *Brownfield* → lands on **Onboarding** (J14) — "let's assess what already exists."
**States:** name collision, permission-denied.

### J8 — Fill the project profile (any member)
**Actor:** member with edit rights. **Entry:** Project Profile tab.
1. **Profile editor** — sections: Description, Domain, Tech stack, Coding standards, NFRs, Constraints, Glossary, Important context. (Backed by `ProjectProfile`.)
2. Save → versioned (`version` increments). Show "last saved, v N".
**Why it matters (show as helper text):** the profile feeds every agent's context. Richer profile → better phases.
**States:** unsaved-changes guard, validation.

### J9 — Connect integrations (tenant-admin)
**Actor:** admin. **Entry:** Admin → Integrations.
1. **Capability grid** — one card per capability: Documentation store, Task tracker, Design source, Code host, Test management, Code intelligence. Each shows **connected vendor + status** or **"Not connected"**.
   > *Annotation 2026-09-15 (as built, `4ac75f9`, Bugs N1): the Code intelligence card has been removed. Code intelligence is set up automatically for every workspace, so the grid shows five capabilities.*
2. **Connect flow per capability** — choose vendor (Confluence/Jira/Figma/GitHub/Xray/built-in), enter the binding config (space key, project key, repo, file key…), and credentials.
   - **Credentials handling — DECISION-4:** today creds live in server `.env`. For a product, design a **secure credential entry** (write-only secret fields, "configured ✓" never echoing the value). *Backend to confirm secret storage.*
3. **Test connection** button → green/red result with the error reason.
4. Connected capability is now usable by phases for that tenant.
**States:** not-connected (empty card with "Connect"), connection-failed (reason + fix hint), credentials-missing.
**Note:** maps to `IntegrationConnection`; "register existing vs. create new" lives in brownfield (J17).

### J10 — Manage repositories (multi-repo)
**Actor:** tech_lead/admin. **Entry:** Repositories tab (brownfield/build projects).
1. **Repo list** — name (`owner/repo`), role (frontend/backend/…), default base branch, status.
2. **Add repo** form; **remove**; mark default.
**Why:** multi-repo drives API-contract/drift (J18) and where build PRs open.
**States:** empty (no repos), duplicate.

---

## 6. Journeys — The lifecycle (the core daily loop)

### 6.0 The mental model designers MUST get right: two tiers + a fan-out (READ FIRST)
A work item is **the unit a phase runs on** — and that unit lives at **different granularities** at different points in the pipeline. **A work item does NOT mean "a thing that replays the entire SDLC."** Most work items only ever traverse a *slice* of the lifecycle. There are two tiers, joined by one fan-out point:

| Tier | Phases | Granularity | Driven by | Shape |
|---|---|---|---|---|
| **Tier 1 — Plan** | Ideation → Requirements → PRD → Architecture → UX → **Task Breakdown** | the **project / release / epic / story** (one pass) | product_owner, architect, designer | mostly **linear**, each gated |
| **Tier 2 — Build** | Implementation → Review → Testing → Deploy/Merge | the **individual task / defect** (many, in parallel) | engineer, reviewer, qa_lead | **parallel + loops** |

- **Task Breakdown is the fan-out:** it decomposes the approved plan into **N task work items** (the stories/tasks pushed to Jira). *That is where the granular work items are born.* Everything upstream is project/epic-level; everything downstream is per-task.
- **Phases are user-triggered one at a time** (the platform never auto-advances) — but they are **not stateless**: each phase consumes the *approved* output of an earlier one (PRD reads Requirements; Implementation reads Tasks + Architecture; Review reads the code; a failing Test spawns a Defect). The work item's **lifecycle is the state model** that (a) confirms the inputs exist, (b) enforces the gate, (c) records provenance — it is **not** a forced wizard.
- **Why a DAG, not a list:** parallel tasks (fan-out), **loops** (review↔implementation, test→defect), **child work items** (remediations, defects), and **cross-task/cross-repo dependencies** (`depends_on`/`implements`) make this a directed graph of work items, each with its own (sub)lifecycle — non-negotiable #4.

**Design consequence (the thing the rail must encode):** the lifecycle rail is **type-adaptive** — it shows *only the phases applicable to that work item's level*. A task-level item must **not** render Ideation/PRD as "Waiting" (it was never their job); that misread is exactly what to avoid.

### J11 — Create a work item & see its (type-adaptive) lifecycle
**Actor:** any member. **Entry:** Work Items.
1. **Work Items board/list** — the board columns are **phases**; cards are work items, **filterable/groupable by level** (Epics vs Tasks vs Defects) so the two tiers don't visually collide. Each card shows title, type, current phase, parent (if a child), and any **"needs you"** flags.
2. **New work item** — type (epic / feature / story / task / defect), feature stream, optional parent. (Most *task*-level items are created automatically by **Task Breakdown**, not by hand — see J16.)
3. **Work item detail — the type-adaptive lifecycle rail:**
   - **Epic / Feature / Story** → the **plan-tier** rail (Ideation → Requirements → PRD → Architecture → UX → Task Breakdown) **plus a "Child tasks" section** listing the work items it fanned out into.
   - **Task** → the **build-tier** rail (Implementation → Review → Test → Deploy/Merge) **only** — never the plan phases — plus a link to its **parent epic** and any **child defects/remediations**.

   > **Settled 2026-09-21 — a story is a planning item (Screen Words group 9, Option A).** This spec
   > used to put a story on the build tier while the shipped code put it on the plan tier
   > (`backend/api/views.py`, `tier_map = {"epic": "plan", "story": "plan", "task": "build",
   > "defect": "remediation"}`). The team chose the code: Task Breakdown fans a story out into
   > tasks, and it is the tasks that carry a repository, a branch and a merge gate — a story on the
   > build rail would show a branch it does not own. A story therefore opens the Epic-shaped screen
   > (S-15) with its children. The rail headings no longer say "tier", which is internal
   > vocabulary: the plan rail is headed **"Lifecycle — Planning"** and the build rail
   > **"Lifecycle — Delivery"**. `SCREEN_INVENTORY.md` S-15/S-16 and `SCREEN_BUILD_MAP.md`'s
   > type-adaptive-rail note were corrected in the same change.
   - **Defect / Remediation** → its minimal rail (Fix → Review → Test) + a link to the **parent** that spawned it.
   Each step shows its state (not started / running / needs answer / awaiting gate / published), and the rail must be able to depict **loops** (review↔fix) and **child branches**, not just a straight line.
**States:** empty project (no work items → "create your first"); per-phase states on the rail; child-items list (empty until Task Breakdown runs); parent backlink on child items.

### J12 — Trigger a phase (runs on the operator's companion)
**Actor:** the operator (their companion executes it). **Entry:** Work item detail → a phase on the rail → "Run", or Phases tab.
1. **Pre-check:** is *my* companion online? If offline → blocked state with "Connect your machine" (J5). (Critical: the trigger must carry the acting user so it routes to their enrollment — req #1.)
2. **Trigger** → run appears as **dispatched → running** on the work item rail and the Runs list.
3. **Live run console** — streaming activity/log, current status badge, cost (filled only after completion), engine/model. Shows the zero-cost reassurance when paused.
4. Run reaches one of: **needs answer** (→ J13), **awaiting gate** (→ J15), or **completed** (artifact registered as draft → gate).
**States:** companion-offline (blocked), dispatched-waiting (your machine hasn't claimed it yet), running, parked-for-takeover (J20), failed (reason + retry).

### J13 — Answer a clarification (zero-cost Q&A)
**Actor:** the operator (or whoever can answer). **Entry:** Clarifications tab, notifications bell, or the run's "needs answer" badge.
1. **Clarification list** — pending questions, each showing the run/work item/phase and **how long it's been waiting** (with the reassurance: *paused, $0 while waiting*).
2. **Answer form** — renders per question `kind`: text → input, choice → select, confirm → checkbox. Shows the agent's **context** ("why I'm asking").
3. Submit → status flips to **answered**; the run resumes **in the same session** automatically.
**States:** empty (no questions), required-field validation, already-answered (someone else answered — collapse), cancelled.
**Durability note (show subtly):** if the run was re-dispatched, previously answered questions are remembered and won't be re-asked.

### J14 — Decide a gate (approve / reject)
**Actor:** the **role-holder** for that gate. **Entry:** Gates tab, notifications bell, or run's "awaiting gate" badge.
1. **Gates list** — pending approvals: gate type, **required role**, run/work item, and a **link to preview the artifact under review** (J19).
2. **Decision panel** — Approve / Reject + optional comment. Only a user holding the required role can act (server-enforced); others see a read-only "awaiting <role>" with who can act.
3. Approve → run continues to **publish**; the artifact flips `draft → published` and (if integrated) writes to the SoR. Reject → run handles rework.
**States:** permission-denied (not your role — show who can), already-decided, empty.

### J15 — Decide a **criteria gate** (e.g., WCAG on UX design)
A specialization of J14. The decision panel includes a **required-criteria checklist** (e.g., each WCAG criterion). **Approve is disabled until all required items are ticked.** Each item can carry a note. This makes "quality gate" tangible rather than a blind approve.
**States:** partially-ticked (approve disabled, show remaining count), all-ticked (approve enabled).

### J16 — Build tier: the per-task engineering loop (Implementation → Review → Test → Merge)
**This is Tier 2 (per §6.0): it operates on *individual task work items*, in parallel, with loops** — not on the project.

**Fan-out first (where the build tier's work items come from):** approving the **Task Breakdown** gate (a Tier-1, epic-level phase) **creates N task work items** and (if Jira is connected) pushes them to the backlog. The breakdown result screen reads as *"Created N task work items"* with links; each new task appears on the board in the **Implementation** column under its parent epic. The operator then **picks one task at a time** and works it through the build rail — exactly the intended flow.

Same trigger→gate pattern as J12/J14, surfaced on **the task's** lifecycle rail, with phase-specific outcomes the UI must show:
- **Implementation (07):** runs on the operator's companion **worktree** → a **draft PR** opens on the code host; the run links to the PR.
- **Code review (08):** runs on companion; findings become **child remediation work items**; the **07↔08 loop** re-runs until clean — the rail shows the loop, not a straight line.
- **Testing (09):** authors tests to test-management (Xray); a failing test opens a **linked, traced defect child work item** that closes on a clean re-run.
- **Merge gate:** reviewer approves → PR merges → the **task** work item → **done** (its parent epic advances only when its children complete).
**Design need:** the rail must represent **loops and child work items** (remediations, defects) and the **parent-epic backlink**, not a straight line (non-negotiable #4). A task item shows **only** these build phases — never the plan phases (§6.0).

---

## 7. Journeys — Brownfield onboarding

### J17 — Assess an existing project (onboarding hub)
**Actor:** tech_lead/admin. **Entry:** Onboarding tab (brownfield only).
1. **Onboarding hub** — a staged panel: *Upload resources → (optional) Register existing tools → Index code → Gap report → Resume*.
2. **Upload resources** (J17a): drag-drop docs (.docx/.pdf/.xlsx) → each extracted into **reviewable draft artifacts**. (REST exists: upload + `adopt/`.)
3. **Adopt** (J17b): review extracted drafts → **Adopt** (behind a gate or a simple adopt action) to make them project artifacts.
4. **Register existing tools** (J17c): for brownfield-with-tools, **register** existing Confluence/Jira (register, don't recreate — no duplicates). Show "found N existing items, linked".
5. **Index code** (J17d): point at a repo → built-in code intelligence indexes it (the platform stores **analysis + index, never your source**). Progress + result summary.
6. **Gap report** (J17e): a generated assessment — **what exists, what's missing, and the recommended `resume_phase`** — with the blocking gaps listed.
7. **Resume** (J17f): one click triggers the named phase (e.g., Architecture) on a work item → hands into the normal pipeline (J12).
**Onboarding-at-different-stages (design for this explicitly):** the gap report's resume point moves as more is provided — *empty → ideation; requirements doc only → prd/architecture; docs + code index → later.* The hub should let the user **re-run the gap report** after each addition and watch the resume point change.
**States:** nothing-uploaded (resume = ideation), extraction-in-progress, adopt-pending-gate, index-running, gap-report-ready.

### J18 — API contract & drift gate (multi-repo)
**Actor:** architect. **Entry:** triggered by a breaking change (or webhook); surfaced on Gates + a Contracts view.
1. **Contracts view** — versioned API contracts (semver), read across repos.
2. **Drift gate** — a breaking change opens a drift approval showing **cross-repo impact** (which repos/consumers are affected). The **architect** decides accept/reject.
3. Decision recorded; impacted work flows accordingly.
**States:** no-drift (healthy), drift-pending (impact list), decided.
> Backend note: `detect/decide_drift` exist as services with no REST/UI yet — these journeys assume new REST.

---

## 8. Journeys — Observability & recovery

### J19 — Browse artifacts & preview
**Actor:** any member. **Entry:** Artifacts tab.
1. **Artifact registry list** — type, phase, version, status (`draft · staged · approved · published · superseded`), SoR, **deep-link** to the live tool (Confluence page / Jira issue) when external. *(`superseded` = a draft whose gate was rejected: kept as the record, no longer served downstream. Added to this line 2026-09-17.)*
2. **Preview** — read-only rendered body (read-through). Never an editor. Version history visible.
**States:** empty, internal-only (no external link), published-with-link.

### J20 — Traceability graph
**Actor:** any member. **Entry:** Traceability tab.
1. **Lineage graph** — nodes = artifacts (phase/type/status/SoR), edges = relationships (`derives`, `story→requirement`, defect links). Click a node → deep-link/preview.
2. Filters by phase/type; highlight a work item's lineage.
   > *Annotation 2026-09-15 (as built, `b40c557`): these filters are now live on the client's screen — Phase, Type, and Highlight work item, which dims the rest of the map rather than hiding it. Documents adopted during onboarding appear as "Not tied to a work item".*
**States:** empty (no artifacts yet), large-graph (pan/zoom, cluster).

### J21 — Offline takeover & recovery
**Actor:** operator. **Entry:** a run that parked.
1. If the companion is offline past the report timeout, the run **parks for human takeover** (rather than hanging): the work item shows a **"needs takeover"** state with a clear explanation.
2. **Recovery affordance:** "Reconnect your machine and re-run" — bring the daemon back (J5), re-trigger; answered clarifications are remembered.
**States:** parked (explained), reconnecting, resumed.

### J22 — Dashboard (the operator's home)
**Actor:** any member. **Entry:** default landing.
- **"Needs me"** — gates awaiting my role, questions awaiting my answer, my runs in flight.
- **Project health** — work items by lifecycle stage; phases in progress; recent publishes.
- **Companion status** — am I connected.
- **Quick actions** — trigger a phase, create a work item.

---

## 9. Product decisions (CONFIRMED by the team)

All eight are locked. The journeys above assume these resolutions.

| # | Decision | **Confirmed resolution** |
|---|---|---|
| DECISION-1 | How is a **tenant-level admin** represented (no project)? | ✅ `Membership(project=null)` or `User.is_tenant_admin`; admin manages users/roles/integrations tenant-wide. |
| DECISION-2 | **Tenant bootstrapping** — who creates the first tenant/admin? | ✅ Self-serve signup creates a new tenant + first admin; everyone else joins by invitation. |
| DECISION-3 | **Auth mechanism** for the web app. | ✅ Server session for the browser; companion keeps its existing runner token. |
| DECISION-4 | **Integration credential storage/entry.** | ✅ Write-only secret fields in a secure store; never echo values; "configured ✓" + test-connection. |
| DECISION-5 | **Artifact preview source** (read-through endpoint). | ✅ Add a read-through preview endpoint (S3/SoR) — pointers only, no bodies in list payloads. |
| DECISION-6 | **Adopt-behind-gate vs. simple adopt** for brownfield source docs. | ✅ Gate it (consistency with "nothing published without a gate"); allow a lightweight path for internal-only. |
| DECISION-7 | **Persist the engine conversation** (run transcript / session view, S-33)? | ✅ **Yes — persist** agent turns + tool calls + Q&A in the DB, replayable **read-only** per run. **No retention window for now** (transcripts stay; a user-facing retention control is a later add). Implies a transcript store + read endpoint. |
| DECISION-8 | **Explicit manual export/publish** (S-34) beyond gate-approval auto-publish? | ✅ **Yes — manual, gate-respecting publish**: a user can publish/re-publish a **gate-APPROVED** artifact to a chosen SoR target. Hard rule preserved — manual publish **never bypasses a gate** (non-negotiable #5). Implies a gate-respecting publish endpoint. |

---

## 10. Backend gaps these journeys imply (so design + build stay honest)

Already exist (wire UI only): tenant/project create, profile, work items, planning-phase trigger, clarifications create/answer, gates decide, artifacts/trace read, companion enroll (`POST /runners/`), source-doc upload+adopt, atlassian register, runner work/report seam.

**Phase 4.7 backend status (updated after P4.7-T1…T11 + the acceptance slice):**
- ✅ **Closed — Real auth**: signup, login/logout, invitations, password reset, session (J1–J4). *(P4.7-T1/T2/T3.)*
- ✅ **Closed — Tenant-admin** concept + **user/role management REST** (J6). *(P4.7-T4; two-tier admin — tenant-admin + project-admin, both can approve any gate.)*
- ✅ **Closed — Trigger carries the acting user** so phases route to *their* companion (req #1). *(P4.7-T5 — `resolve_actor`: the session user wins over any hand-entered `user_id`.)*
- ✅ **Closed — Integrations management REST** + secure credentials + test-connection (J9). *(P4.7-T6.)*
- ✅ **Closed — Repositories REST** (J10). *(P4.7-T7.)*
- ✅ **Closed — Brownfield onboarding REST**: code-intel index trigger, **gap report**, resume (J17 d–f). *(P4.7-T8 — code-intel accepts an already-computed result; real companion-side dispatch is a documented follow-up, not a UI-facing gap.)*
- ✅ **Closed — API-contract / drift REST** (J18). *(P4.7-T9 — single contract per project today; a mockup showing multiple named contracts per project exceeds the current model, noted as a future enhancement.)*
- ✅ **Closed — Artifact preview** read-through endpoint (J19). *(P4.7-T10 — S3 for internal drafts, live through DocStore/TaskTracker for confluence/jira, link-only otherwise; "versions" is a time-ordered revision list, not yet a true incrementing per-artifact version counter.)*
- ✅ **Closed — Companion status + connect surface** (J5). *(P4.7-T11 — `GET /api/runners/` returns the session user's enrollments grouped by machine with online/offline derived from `last_seen`.)*
- ✅ **Proven end-to-end** by the P4.7 acceptance slice (`backend/tests/test_acceptance_phase47.py`): signup → invite → accept → grant gate role → connect-machine → create project → trigger a phase (routes to the user's companion) → answer a clarification → decide a gate → preview the published artifact — **no shell/manage.py step** anywhere in the chain.

**Still open (deferred to Phase 4.8 — design-sensitive, not a 4.7 REST-wrapping task):**
- **Criteria-gate** data on approvals (J15) — a generalized criteria-checklist gate schema beyond the existing WCAG-only conditions, needed once S-22's checklist UI is built.

---

## 11. How to use this document

1. **Designers:** take the IA (§2) + journeys (§4–§8) + cross-cutting patterns (§3) and produce hi-fi flows/screens. Treat §0 as guardrails and §9 decisions as inputs to confirm.
2. **Confirm the §9 decisions** with product/backend — they change a handful of screens (mostly auth/admin).
3. **Engineering** sequences the §10 backend gaps alongside the UI build.
4. **The guide PDF** (§3/§5) is rewritten *from* the finalized journeys, not before.
