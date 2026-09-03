# User Journey: Greenfield Project — Ideation to Deployment

**Document purpose:** Complete reference for every screen, API call, business-logic rule, and gate
that a team experiences when running a brand-new project through the Edvensoft AI-First SDLC
platform from zero to first deployment.

**Platform version:** Phase 4.8 (Hi-Fi React UI + Phase 4.7 backend)
**Last updated:** 2026-07-01

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
- `seed_agent_specs(tenant)` seeds all 16 AgentSpec rows
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
   - **Code Intel (builtin):** No secret needed
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
6. Redirects to `/setup` → sets up Project Profile

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

After approval:
- Temporal workflow resumes, run → `completed`
- `Artifact` created: `phase="01_ideation", type="brief", status="approved"`

---

### A-9 · Phase 02–04 — Requirements, PRD, Architecture

Same pattern as A-7/A-8 for each phase:

| Phase | Agent key | Gate role | Artifact type |
|-------|-----------|-----------|---------------|
| Requirements | `02_requirements` | product_owner | requirements_doc |
| PRD | `03_prd` | product_owner | prd |
| Architecture | `04_architecture` | architect (Marcus) | architecture_doc |

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

**Actor:** Aisha (engineer triggers), Dev approves code review  

- `07_implementation` → companion writes code to branch
- `08_code_review` → code review gate (tech_lead: Dev)
- If GitHub unavailable: note failure, implementation artifact still created internally

---

### A-14 · Phase 09 — Testing

**Actor:** Carlos Reyes (qa_lead)

- Trigger `09_testing`
- Gate role: `qa_lead`
- If Xray unavailable: note failure, test report artifact still created internally

---

### A-15 · Phase 10 — Security

**Actor:** Yuki Tanaka (security_engineer)

- Trigger `10_security`
- Gate role: `security_engineer`
- Security report artifact created

---

### A-16 · Phase 11–12 — CI/CD & Deployment

**Actor:** Jordan Kim (devops)

- Trigger `11_cicd` → `12_deployment`
- Gate role: `devops`
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
2. Each node has `sor`, `phase`, `type`, `status`, `url` (Confluence deep link if connected)
3. Dashboard: `GET /api/projects/{id}/dashboard/`
   - `needs_me.gates` → empty (all decided)
   - `health.work_items` → count
   - `health.published_week` → count of published artifacts
   - `recent_publishes` → list

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
```
