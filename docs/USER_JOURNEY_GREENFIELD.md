# User Journey: Greenfield Project — Ideation to Deployment

**Document purpose:** Complete reference for every screen, API call, business-logic rule, and gate
that a team experiences when running a brand-new project through the Edvensoft AI-First SDLC
platform from zero to first deployment.

**Platform version:** Phase 4.8 (Hi-Fi React UI + Phase 4.7 backend)
**Last updated:** 2026-09-16
**What changed in this revision:** corrected against the code — the seeded agent count, the
artifact type names, the code-review gate role, the new project redirect, the build/PR/merge
flow for the phases that write code, the accessibility judge and journey phases, the checklists
on the design and deployment gates, "Request changes", and the `stalled` run status.

---

## Cast of characters

| Persona | Role | Membership role |
|---------|------|-----------------|
| Sarah Chen | Founder / Product Owner | `product_owner`, `is_tenant_admin = true` |
| Marcus Lee | Architect | `architect` |
| Dev Patel | Tech Lead | `tech_lead` |
| Aisha Okonkwo | Engineer | `engineer` |
| Priya Nair | Designer | `designer` |
| Carlos Reyes | QA Lead | `qa_lead` |
| Yuki Tanaka | Security Engineer | `security_engineer` |
| Jordan Kim | DevOps | `devops` |

---

## Scenario A — Full lifecycle happy path (Stripe Webhook Integration epic)

### A-0 · Workspace setup

**Screen:** `/signup`  
**Actor:** Sarah (founder)

Steps:
1. Sarah navigates to `/signup`
2. Fills in: Full Name = "Sarah Chen", Email = "sarah@acme.com", Password = "Str0ng-Pass!", Workspace = "Acme Corp"
3. Submits → `POST /api/auth/signup/` with `{ name, email, password, org_name }`

Expected:
- Backend creates `Tenant("Acme Corp")` + `User(is_tenant_admin=True)` atomically
- `seed_agent_specs(tenant)` seeds all 19 active AgentSpec rows (the whole catalogue except the
  retired `00d_context_snapshot`)
- Session cookie set; response: `{ user: { is_tenant_admin: true }, tenant: { name: "Acme Corp" }, memberships: [] }`
- Frontend reads `user.is_tenant_admin` → `AuthContext.isAdmin = true`
- Redirects to `/setup` (SetupChecklist)

Business rules verified:
- Duplicate email → 409
- Password < 8 chars → 400
- `org_name` blank → 400

---

### A-1 · Invite team members

**Screen:** `/admin/users`  
**Actor:** Sarah (admin)

Steps:
1. Sarah opens Users & Invites
2. Invites Marcus: `POST /api/invitations/` `{ email: "marcus@acme.com", name: "Marcus Lee", grants: [{ project_id: <pid>, role: "architect" }] }`
3. Invites Dev, Aisha, Priya, Carlos, Yuki, Jordan (each with their role)
4. Each invitee receives email with one-time token

Acceptance:
- Each invitee hits `POST /api/auth/accept-invitation/` with `{ token, password, name }`
- Membership rows created; session established
- Token single-use — replaying → 409

Business rules:
- Only `is_tenant_admin` may POST to `/invitations/` → non-admin → 403
- Expired invitation → 410
- Revoked invitation → 410

---

### A-2 · Connect companion machine

**Screen:** `/connect`  
**Actor:** Sarah, then Dev Patel

Steps:
1. Dev navigates to `/connect`
2. Picks project "Acme Corp / Payment Gateway v2" from dropdown
3. Clicks "Generate enrollment token" → `POST /api/runners/` `{ project_id: <pid>, label: "Dev's MacBook" }`
4. Backend returns `{ id, token }` (token shown once)
5. Dev runs `companion serve --token rnr_<token>` on terminal
6. Companion polls `GET /api/runners/` — `online: true` when last_seen < 5 min

Business rules:
- Authenticated session required (403 otherwise)
- Token is SHA-256 hashed server-side; raw token never stored

---

### A-3 · Connect integrations

**Screen:** `/integrations`  
**Actor:** Sarah (admin)

Steps:
1. Sarah opens Integrations grid
2. Clicks "Connect" on each capability tile:
   - **Docstore (Confluence):** URL + API token → `POST /api/integrations/` `{ capability: "docstore", vendor: "confluence", binding: { url }, secrets: { token } }`
   - **Task Tracker (Jira):** URL + API token
   - **Code Host (GitHub):** GitHub App installation
   - **Design Source (Figma):** OAuth token
   - **Test Mgmt (Xray):** API key
   - *(Code intelligence has no tile any more — since 2026-09-11 (`4ac75f9`, N1) it is set up
     automatically for every workspace, like accessibility.)*
3. Each → `POST /api/integrations/{id}/test-connection/` → `{ ok: true, detail: "..." }`

Business rules:
- Secrets write-only: never appear in GET responses (`configured: bool` only)
- `test-connection` returns `{ ok, detail, fix_hint? }` — never a 500
- Admin-only: non-admin → 403

Integration failure handling:
- If Confluence unavailable: note "INTEGRATION_FAILURE: docstore/confluence — test-connection ok=false" and continue
- If GitHub unavailable: note "INTEGRATION_FAILURE: codehost/github — test-connection ok=false" and continue

---

### A-4 · Create greenfield project

**Screen:** `/projects/new`  
**Actor:** Sarah

Steps:
1. Navigates to Create Project
2. Name = "Stripe Webhook Integration"
3. Track = "greenfield"
4. Repo topology = "single"
5. Submits → `POST /api/projects/` `{ name, track: "greenfield", repo_topology: "single" }`
6. A new greenfield project lands straight on its profile: `/profile?project={id}&setup=1`
   (a brownfield project goes to `/onboarding` instead)

Profile step:
- `PUT /api/projects/{id}/profile/` with description, domain, tech_stack, nfrs, constraints, glossary
- `version` increments on each save

Business rules:
- Project name uniqueness per tenant enforced
- `repo_topology` must be `"single" | "split" | "multi"`
- Profile 1:1 with project; PUT creates-or-updates

---

### A-5 · Register repositories

**Screen:** `/repositories`  
**Actor:** Dev Patel (tech_lead)

Steps:
1. Dev clicks "Add repository"
2. `POST /api/projects/{id}/repositories/` `{ name: "acme/payments", role: "backend", base_branch: "main" }`
3. Response: `{ id, name, default_base: "main", is_default: true, status: "unlinked" }`
4. After GitHub integration connects: status becomes `"connected"`

Business rules:
- First repo → `is_default: true`; second repo → topology changes single→split, `is_default: false`
- Only `tech_lead` / `admin` may add/remove repos (403 for `engineer`)
- Duplicate name → 409

---

### A-6 · Create Epic work item

**Screen:** `/work-items`  
**Actor:** Sarah

Steps:
1. Clicks "New work item"
2. `POST /api/work-items/` `{ project: <pid>, type: "epic", feature_stream: "payments", title: "Stripe Webhook Integration" }`
3. Response: `{ id, type: "epic", state: "proposed", ... }`
4. Navigate to `/work-items/{id}` → `WorkItemEpic` view

Business rules:
- Initial state always `"proposed"`
- No `parent` field for epics
- `feature_stream` is free-text

---

### A-7 · Phase 01 — Ideation

**Screen:** `/runs` (Phases & Runs → trigger)  
**Actor:** Dev Patel (companion owner)

Steps:
1. Dev selects the epic from work-item dropdown
2. Clicks "▶ Ideation" button
3. `POST /api/work-items/{wi_id}/trigger/` `{ agent_key: "01_ideation" }`
4. Response: `{ run_id, workflow_id }` → 202

Backend flow:
- `trigger_phase()` creates `Run(status="pending")` + Temporal `AgentRunWorkflow`
- `AgentRunWorkflow` executes `01_ideation/agent.md` via companion (Dev's MacBook)
- Run status progresses: `pending → running → awaiting_gate`
- Frontend polls `GET /api/runs/{id}/` every 3s + `GET /api/events/?target_type=run&target_id={id}` for log stream

**Screen:** `/runs/{id}` (RunConsole)  
Live states observed: queued → running (log lines appear) → gate (awaiting Sarah's approval)

---

### A-8 · Gate approval — Ideation (product_owner)

**Screen:** `/gates/{approval_id}/criteria`  
**Actor:** Sarah (product_owner)

Steps:
1. Dashboard → "Gates need your approval" card
2. Navigate to `/gates/{approval_id}/criteria`
3. `GET /api/approvals/{id}/criteria/` returns criteria checklist
4. Sarah checks all boxes, submits decision
5. `POST /api/approvals/{id}/decide/` `{ decision: "approved", comment: "Good scope", satisfied: { "c1": true, "c2": true } }`

Response: `{ decision: "approved", approver_id: ..., conditions: [...] }`

Business rules enforced:
- Only `product_owner` (or tenant admin fallback) may approve this gate
- `tech_lead` attempting → 403 (GateRoleError)
- `decision: "approved"` with required condition unsatisfied → 400 (GateError)
- `decision: "rejected"` → run terminates; work item stays `in_progress`; re-trigger allowed
- **Request changes** is a rejection the reviewer wants acted on: `decision: "rejected"` with
  `revise: true` and a comment saying what to change. The comment is required, and `revise` on
  anything other than a rejection is refused. The platform starts the revising run itself, with
  the review conversation carried into it — the reviewer does not re-trigger the phase by hand

After approval:
- Temporal workflow resumes, run → `completed`
- `Artifact` created: `phase="ideation", type="ideation", status="approved"` (the phase label and
  the artifact types are the bare lifecycle names — no `NN_` prefix, no `_doc` suffix)

---

### A-9 · Phase 02–04 — Requirements, PRD, Architecture

Same pattern as A-7/A-8 for each phase:

| Phase | Agent key | Gate role | Artifact type |
|-------|-----------|-----------|---------------|
| Requirements | `02_requirements` | product_owner | requirements |
| PRD | `03_prd` | product_owner | prd |
| Architecture | `04_architecture` | architect (Marcus) | architecture (plus `adr`, `data_model`, `api_spec`) |

Architecture gate — Marcus approves:
- `POST /api/approvals/{id}/decide/` as Marcus (architect role)
- Sarah (product_owner) attempting architecture gate → 403

---

### A-10 · Clarification mid-phase (agent asks a question)

**Screen:** `/clarifications`  
**Actor:** Sarah (answering for PRD phase)

When the PRD agent needs clarification:
- Companion creates `POST /api/runner/clarifications/` `{ run_id, questions: [{id, text, kind, required}], context, phase }`
- Clarification status = `"pending"`; run pauses (Temporal waits on signal)

Steps (human side):
1. Dashboard shows clarification badge
2. Navigate to `/clarifications`
3. `GET /api/clarifications/?status=pending&work_item={id}`
4. Sarah reads question, types answer
5. `POST /api/clarifications/{id}/answer/` `{ answers: { "q1": "We need CSV export for reporting" } }`
6. Run resumes automatically

Business rules:
- `required: true` question left unanswered → 400 (ClarificationError)
- Non-member answering → 403 (ClarificationRoleError)
- Already-answered clarification re-answered → 400

---

### A-11 · Phase 05 — UX Design

**Actor:** Priya Nair (designer)  
**Gate role:** designer

- Trigger `05_ux_design`
- Gate approval by Priya (designer role)
- The design gate carries the **WCAG 2.2 AA checklist** — 22 questions a designer can settle from
  the design itself (alt text intent, colour not carrying meaning alone, contrast, focus order,
  visible focus, tap target size, labelled fields, error wording, and so on). Every item is
  required, and one left unticked blocks approval. Five further questions can be switched on per
  project in its accessibility settings. The wording of each item comes from the WCAG 2.2 rows
  loaded into the database, so a new release of the standard is a data reload, not a code change
- If Figma integration unavailable: note failure, agent still produces internal design spec artifact

---

### A-12 · Phase 06 — Task Breakdown

**Actor:** Dev Patel (tech_lead)  
**Gate role:** tech_lead

- Trigger `06_task_breakdown`
- Agent creates child `WorkItem` rows (type="task") as output
- Gate approval by Dev
- Tasks appear in `/work-items` board under the epic

---

### A-13 · Phase 07–08 — Implementation & Code Review

**Actor:** Aisha (engineer triggers); the code-review and merge gates are decided by a holder of
the `reviewer` role (or a tenant admin)  

- `07_implementation` **rides the build**: triggering it starts the build workflow, not a plain
  phase run. The companion works in a git worktree, commits, pushes the branch and the platform
  opens a **draft pull request**
- `08_code_review` is dispatched **inside** that build loop — it is not a standalone trigger. Its
  gate role is `reviewer` (not `tech_lead`), and the implementation and review agents loop on
  remediation until the review is clean
- The build then waits on the **merge gate**: a reviewer approves, and only then does the platform
  merge the PR. Rejecting ends the build with the branch and PR left in place; "Request changes"
  re-enters the loop — the PR is reconciled to the new head, the remediation loop runs again and
  the gate re-opens. A merge conflict parks the build rather than failing it, so a reviewer can
  resolve it in GitHub and approve again without a rebuild
- `09b_test_automation` and `11_cicd` ride the same build flow for the same reason: they write
  code into the worktree
- If GitHub unavailable: note failure, implementation artifact still created internally

---

### A-14 · Phase 09 — Testing

**Actor:** Carlos Reyes (qa_lead)

- Trigger `09_testing` — **planning only**: it writes the `test_plan` and one `test_case` per case
  and never registers a `test_report`
- Gate role: `qa_lead`
- Then `09b` (Test Automation) writes and runs the tests; its run produces the only `test_report`,
  imports results to Xray, and a failing test opens a defect
- If Xray unavailable: note failure; test artifacts are still created internally
- The testing gate also carries a **derived accessibility condition**: "no unresolved
  accessibility failure". It is computed when the gate is decided, from the open accessibility
  defects on this work item, and a reviewer cannot tick it by hand. If nothing is blocking it
  still says what it found — problems the keyboard journey raised (tracked, never blocking),
  accessibility debt inherited from a baseline audit, or that no accessibility check has run for
  this work item at all

---

### A-14b · Accessibility phases 09c and 09d

Two platform-native phases sit beside testing, both gated by `qa_lead`:

- `09c_a11y_judge` — judges what a rule scanner cannot decide (is this alt text meaningful, is
  this `div` really a button) against the loaded WCAG 2.2 wording. It registers no artifacts: its
  output is one verdict per element, so the platform checks its coverage instead
- `09d_a11y_journey` — operates the application with a keyboard through a critical journey and
  watches what focus does and what assistive technology is told. Its findings are recorded,
  reported and ticketed, but they never fail a gate

---

### A-15 · Phase 10 — Security

**Actor:** Yuki Tanaka (security_engineer)

- Trigger `10_security`
- Gate role: `security_engineer`
- Security report artifact created
- The security gate **cannot be approved while any Critical or High finding is open** — the
  platform checks this when the gate is decided (`apps/gates/securitygate.py`)

---

### A-16 · Phase 11–12 — CI/CD & Deployment

**Actor:** Jordan Kim (devops)

- Trigger `11_cicd` (rides the build — worktree, PR, merge gate) → `12_deployment`
- Gate role: `devops`
- The deployment gate carries a **readiness checklist** the DevOps reviewer attests item by item:
  CI-passing PRs and coverage, Critical/High test cases passed with UAT signed off, zero open
  Critical or High security findings, migrations tested on staging with a rollback script,
  a documented and tested rollback procedure, an on-call engineer named and the window
  communicated, and release notes plus the version-specific rollback runbook registered. Every
  item is required; one left unticked blocks approval
- Final artifact published to SoR

**Artifact publish flow:**
1. `GET /api/artifacts/{id}/` — confirm `status = "approved"`
2. Navigate to `/artifacts/{id}/publish`
3. `POST /api/artifacts/{id}/publish/` `{ target_capability: "confluence", destination: "https://confluence.acme.com/space" }`
4. Response: `{ status: "published", sor_link: "..." }`

Business rules:
- Draft/staged artifact → 400 (must be gate-approved first)
- `status` changes from `"approved"` → `"published"`

---

## Scenario B — Gate rejection and re-trigger

**Trigger:** Sarah rejects the PRD gate

Steps:
1. `POST /api/approvals/{id}/decide/` `{ decision: "rejected", comment: "Missing payment flow section" }`
2. Run → `status: "rejected"`
3. Work item remains `in_progress`
4. Dev re-triggers: `POST /api/work-items/{id}/trigger/` `{ agent_key: "03_prd" }` → new Run created
5. New run goes through the cycle again with the rejection context

Business rules:
- Re-triggering creates a NEW Run (not amending old one)
- Old run remains in history with `status: "rejected"`
- Multiple concurrent runs for same phase → only latest is primary

---

## Scenario C — Human takeover mid-run

**Trigger:** Network loss; companion goes offline mid-implementation

Steps:
1. Dev's MacBook goes offline: `GET /api/runners/` → `online: false`
2. Run stuck at `status: "running"` with no heartbeat
3. Jordan decides to take over manually
4. `POST /api/runs/{run_id}/take-over/` `{ actor: "developer", reason: "Companion lost network" }`
5. Work item `takeover_flag = true`
6. Jordan pushes commits manually to the branch
7. GitHub webhook fires → `POST /api/webhooks/github/{tenant_id}/` → reconciliation
8. `POST /api/runs/{run_id}/take-over/` `{ release: true }` → automation resumes

Business rules:
- Takeover delegates to `request_takeover(tenant_id, work_item_id, actor, reason)`
- `release: true` calls `release_takeover()`
- TakeoverError on invalid state → 400

---

## Scenario D — Traceability and Dashboard

After all phases complete:

1. `GET /api/projects/{id}/traceability/` → graph of artifact → artifact edges
2. Each node has `sor`, `phase`, `type`, `status`, `url` (Confluence deep link if connected), and
   `work_item`, `work_item_key`, `work_item_title` (empty for documents adopted in onboarding)
3. Dashboard: `GET /api/projects/{id}/dashboard/` — personalised to the signed-in user
   - `needs_me.gates` → only gates this user may decide (empty once all are decided)
   - `needs_me.clarifications` → only if this user is a member of the project
   - every gate / question / run row carries `work_item_key` and `work_item_title`; run rows add
     `started_s` (seconds since the run started)
   - `needs_me.counts` → true totals (`gates`, `clarifications`, `my_runs`), not capped by the list
   - `health.work_items` → count
   - `health.published_week` → count of artifacts **published** in the last 7 days (by `published_at`)
   - `recent_publishes` → list

---

## Where accessibility sits in this journey

Accessibility is not a phase of its own; it is four things attached to the lifecycle the team
already runs:

1. **The design gate (05)** carries the WCAG 2.2 AA checklist — the questions a designer can
   answer from the design. Unticked required items block the gate (A-11)
2. **The judge and journey phases (09c, 09d)** check the built pages and a keyboard journey
   (A-14b)
3. **The testing gate (09)** carries a derived accessibility condition the platform computes
   from the open accessibility defects on the work item — a reviewer cannot attest it (A-14)
4. **The conformance statement** is a separate, signed document: the platform lays out all 55
   Level A and AA criteria with the evidence beside each one, suggests a level only where the
   evidence supports it, and then stops. Only the accessibility reviewer on the project — the
   `qa_lead` — can sign it, and the claim belongs to the person who signs. It is produced from
   `/a11y/conformance`

---

## Known integration failure points

| Integration | Failure scenario | Platform behaviour |
|-------------|-----------------|-------------------|
| Confluence (docstore) | `test-connection ok=false` | Agent creates internal artifact; publish to SoR deferred |
| Jira (tasktracker) | Connection refused | WorkItem external_ref not set; platform-only tracking |
| GitHub (codehost) | Missing installation | Repository `status: "unlinked"`; code pushed locally only |
| Figma (designsource) | Invalid token | UX Design artifact created internally |
| Xray (testmgmt) | API key expired | Test report as internal artifact |

---

## State machine — WorkItem

```
proposed → accepted (on reconcile with SoR)
accepted → in_progress (on trigger)
in_progress → in_review (on awaiting_gate)
in_review → in_progress (on rejection → re-trigger)
in_review → done (on final gate approval + artifact published)
in_progress → blocked (on takeover_flag=true)
blocked → in_progress (on takeover released)
```

---

## State machine — Run

```
pending → running (companion picks up task)
running → awaiting_gate (agent finishes, gate created)
awaiting_gate → approved (gate approved)
awaiting_gate → rejected (gate rejected)
approved → completed (workflow finishes)
running → failed (agent error)
running → stalled (no companion report before the timeout)
stalled → running / awaiting_gate (a companion that only slept comes back and reports)
stalled → failed (an explicit human takeover, or a reported failure)
```

`stalled` is not terminal. It means the run is parked for a human to take over, and a late
companion report still reconciles it through the normal gate path.
