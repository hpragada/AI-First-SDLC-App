# User Journey: Brownfield Project — Legacy Codebase Onboarding to Deployment

**Document purpose:** Complete reference for the brownfield track — importing an existing codebase,
registering legacy artifacts, running a gap report, and resuming the lifecycle from the detected
resume phase through to deployment.

**Platform version:** Phase 4.8 (Hi-Fi React UI + Phase 4.7 backend)
**Last updated:** 2026-07-01

---

## Cast of characters

| Persona | Role | Notes |
|---------|------|-------|
| Sarah Chen | Product Owner / Admin | Owns the workspace |
| Marcus Lee | Architect | Reviews architecture gate |
| Dev Patel | Tech Lead | Manages repositories |
| Carlos Reyes | QA Lead | Manages test gate |

**Existing system:** "Legacy Billing System" — a 5-year-old Django monolith with existing Confluence
docs and Jira backlog. Goal: modernise to microservices without losing existing compliance
documentation.

---

## Scenario BF-A — Full brownfield onboarding and lifecycle resume

### BF-A-0 · Workspace + project creation

Same as Greenfield A-0 and A-1. Sarah signs up, invites team, connects machine.

Create project with **brownfield track:**
- `POST /api/projects/` `{ name: "Legacy Billing Modernisation", track: "brownfield", repo_topology: "multi" }`

Multi-repo topology:
- `POST /api/projects/{id}/repositories/` `{ name: "acme/billing-monolith", role: "backend", base_branch: "main" }`
- `POST /api/projects/{id}/repositories/` `{ name: "acme/billing-api", role: "service", base_branch: "develop" }`
- Project topology auto-upgrades: single → split (2 repos) → multi (3+ repos)

---

### BF-A-1 · Upload legacy documentation

**Screen:** `/onboarding` (OnboardingHub)  
**Actor:** Sarah

Steps:
1. `GET /api/projects/{id}/onboarding/` returns OnboardingHub state:
   ```json
   {
     "upload": [],
     "adopt": [],
     "register": {},
     "index": { "status": "not_started" },
     "gap": { "ready": false }
   }
   ```
2. Navigate to `/onboarding/documents` (SourceDocuments screen)
3. Upload legacy PDF: `POST /api/projects/{id}/source-documents/` (multipart)
   - Files: "Legacy Billing Requirements v3.pdf", "Architecture Decision Records 2021.pdf"
4. Backend: `ingest_source_document()` → S3 upload → extraction pipeline → SourceDocument row
5. SourceDocument `status`: `uploaded → extracting → extracted`
6. Extracted artifacts created (type="requirements_doc", "architecture_doc")

Screen states observed:
- `empty` → after upload → `uploading` → `extracted`

Business rules:
- Only `file` multipart field accepted; missing file → 400
- Extraction failure → `status: "failed"` (note; platform continues)

---

### BF-A-2 · Adopt source documents as artifacts

**Screen:** `/onboarding/documents`  
**Actor:** Sarah

Steps:
1. Review extracted artifact preview
2. Click "Adopt as Requirements artifact"
3. `POST /api/source-documents/{id}/adopt/` `{ user_id: <sarah_id> }`
4. Platform:
   - Creates `Artifact(type="requirements_doc", status="staged", sor="internal")`
   - Creates `TraceEdge(from=source_doc_artifact, to=requirements_artifact, rel="extracted_from")`
5. SourceDocument `status` → `adopted`

Screen state: `adopt-gate` (awaiting product_owner) → `adopted`

Business rules:
- Only `product_owner` role may adopt (405/403 for other roles)
- Already-adopted document cannot be re-adopted

---

### BF-A-3 · Register against Confluence / Jira (brownfield-lite)

**Screen:** `/onboarding` (OnboardingHub, "Register" section)  
**Actor:** Sarah

Steps:
1. Click "Register existing Confluence space"
2. `POST /api/projects/{id}/onboard-atlassian/`
3. Platform calls `register_atlassian(tenant_id, project_id)`

**If Confluence available:**
- Registers Confluence space pointer → `register.docstore_space = "~BILLING"`
- Crawls existing pages for artifact pointers (does NOT copy content)
- `OnboardingHub.register.linked_issues = <count>`

**If Confluence unavailable (INTEGRATION_FAILURE):**
- Note: `INTEGRATION_FAILURE: docstore/confluence — register_atlassian failed: CapabilityUnavailable`
- Platform continues with internal-only artifacts
- `register.docstore_space` remains null

**If Jira available:**
- `register.tasktracker_project = "BILLING"`
- `register.linked_issues = 142`

**If Jira unavailable (INTEGRATION_FAILURE):**
- Note: `INTEGRATION_FAILURE: tasktracker/jira — Jira registration skipped`
- WorkItem `external_ref` not populated; platform tracks internally

---

### BF-A-4 · Code Intelligence indexing

**Screen:** `/onboarding` (OnboardingHub, "Index" section)  
**Actor:** Dev Patel (tech_lead)

Steps:
1. Select repository "acme/billing-monolith" in dropdown
2. Click "Start code intelligence"
3. `POST /api/projects/{id}/code-intel/` `{ repo_id: <billing_monolith_repo_id> }`
4. Backend: `record_code_intel_index()` → companion analyses codebase structure
5. Polling: `GET /api/projects/{id}/onboarding/` shows:
   - `index.status: "running"`, `files_indexed: 284`, `total_files: 1284`
   - Eventually: `index.status: "done"`, `files_indexed: 1284`

**If code intel fails:**
- Note: `INTEGRATION_FAILURE: codeintel — index failed`
- Platform continues; gap report runs with partial data

Business rules:
- Only `tech_lead` or `admin` may trigger code intel (403 for product_owner)
- Requires at least one registered repository (400 if none)

---

### BF-A-5 · Run Gap Report

**Screen:** `/onboarding/gap-report` (GapReportScreen)  
**Actor:** Sarah

Steps:
1. `POST /api/projects/{id}/gap-report/` → triggers gap analysis
2. Poll: `GET /api/projects/{id}/gap-report/`
3. Response:
   ```json
   {
     "phases": [
       { "phase": "01_ideation",     "assessment": "complete",  "evidence": "source doc covers scope" },
       { "phase": "02_requirements", "assessment": "partial",   "evidence": "requirements doc v3 found" },
       { "phase": "03_prd",          "assessment": "missing",   "evidence": "no PRD found" },
       { "phase": "04_architecture", "assessment": "complete",  "evidence": "ADR document found" }
     ],
     "resume_phase": "03_prd",
     "blocking": []
   }
   ```
4. Screen shows: "Resume at: PRD"
5. `OnboardingHub.gap.ready: true`

Screen states: `partial` (resuming mid-lifecycle) / `empty` (nothing done) / `mature` (well-covered)

Business rules:
- Gap report `resume_phase` = first phase with `assessment != "complete"`
- `blocking` = phases required but have no evidence AND no predecessor

---

### BF-A-6 · Resume lifecycle at detected resume phase

**Screen:** `/work-items` → create epic → trigger from resume phase  
**Actor:** Dev Patel

Steps:
1. Create epic: `POST /api/work-items/` `{ type: "epic", title: "Billing Microservice Extract", feature_stream: "core" }`
2. Navigate to epic lifecycle rail: `GET /api/work-items/{id}/lifecycle/`
3. Phases 01 (ideation) and 04 (architecture) show as "complete" based on gap report evidence
4. Phase 03 (PRD) shows as "not_started" — this is the resume point
5. Trigger PRD: `POST /api/work-items/{id}/trigger/` `{ agent_key: "03_prd" }`
6. Agent runs with context from gap report + adopted artifacts

Business rules:
- Triggering a "complete" phase is still allowed (re-run with new context)
- Gap report evidence is passed as `inputs` to the agent run

---

### BF-A-7 · API Contract management

**Screen:** `/contracts` (ContractsDrift)  
**Actor:** Marcus Lee (architect)

Scenario: "billing-api" exposes a REST API. A new PR adds breaking changes.

**Healthy state:**
- `GET /api/projects/{id}/api-contracts/` → list of contract artifacts
- `GET /api/projects/{id}/api-contracts/{artifact_id}/` → rendered OpenAPI body

**Drift detected (breaking change merged):**
- GitHub webhook fires: `POST /api/webhooks/github/{tenant_id}/`
- Platform creates `DriftRecord(kind="contract", required_role="architect", status="open")`
- `detail: { "old_version": "v2.0.0", "new_version": "v2.1.0", "breaking": ["DELETE /payments/{id}"] }`
- `impacted: [{ "node": <requirements_artifact_id>, "repo_id": <billing_api_repo_id> }]`

**Dashboard shows alert:**
- `needs_me.gates` includes the drift record (if Marcus is logged in)

**Marcus decides:**
- Navigate to `/contracts` → drift queue tab
- `POST /api/drift/{id}/decide/` `{ decision: "accept", comment: "Breaking change approved for v3 migration" }`

**If GitHub webhook unavailable:**
- Note: `INTEGRATION_FAILURE: codehost/github — webhook not received`
- Drift must be logged manually via admin

Business rules:
- Only `architect` role may decide contract drift (403 for product_owner)
- Drift already decided → 400 (DriftError)
- `decision: "reject"` → platform blocks the deployment gate

---

### BF-A-8 · Artifact registry and traceability

**Screen:** `/artifacts` (ArtifactsRegistry) + `/traceability`  
**Actor:** Sarah

Artifacts accumulated:
- `requirements_doc` (from source doc adoption) — status: staged
- `prd` (from phase 03) — status: approved
- `architecture_doc` (from gap report evidence) — status: approved

**Traceability graph:**
- `GET /api/projects/{id}/traceability/`
- Nodes: source_doc → requirements → prd → architecture
- Edges: `extracted_from`, `satisfies`, `implements`

**Preview artifact:**
- `GET /api/artifacts/{id}/preview/` → `{ body: "...", content_type: "text/markdown", status: "approved", versions: [...] }`

---

### BF-A-9 · Publish artifact to Confluence

**Screen:** `/artifacts/{id}/publish` (ExportPublish)  
**Actor:** Sarah

**Happy path (Confluence available):**
1. Navigate to `/artifacts/{id}/publish`
2. `GET /api/artifacts/{id}/` — confirm `status: "approved"`
3. Select target: "Confluence"
4. `POST /api/artifacts/{id}/publish/` `{ target_capability: "confluence", destination: "https://confluence.acme.com/~BILLING" }`
5. Response: `{ status: "published", sor_link: "https://confluence.acme.com/~BILLING/{artifact_id}" }`
6. Artifact `sor: "confluence"`, `status: "published"`

**Blocked state (draft artifact):**
- Attempt to publish draft artifact → 400 "Artifact must be gate-approved before publishing"

**If Confluence unavailable (INTEGRATION_FAILURE):**
- Note: `INTEGRATION_FAILURE: docstore/confluence — publish failed`
- Artifact marked `status: "published"` with `sor: "internal"` fallback
- `sor_link: null`

---

## Scenario BF-B — Drift rejection blocks deployment

**Trigger:** Marcus rejects drift (breaking change is not acceptable)

Steps:
1. `POST /api/drift/{id}/decide/` `{ decision: "reject", comment: "Breaking DELETE endpoint cannot ship" }`
2. Platform flags deployment gate: cannot approve until drift resolved
3. Sarah sees dashboard: `needs_me.gates` shows deployment gate blocked
4. Dev reverts the breaking change in PR
5. GitHub webhook fires again → drift status updated
6. Deployment gate unblocked → can now be approved

---

## Scenario BF-C — Partial lifecycle (skip completed phases)

Existing system already has working CI/CD. Team wants to skip phases 11 (CI/CD) and trigger 12 (deployment) directly.

Steps:
1. Trigger `12_deployment` on the work item (skip 11)
2. `POST /api/work-items/{id}/trigger/` `{ agent_key: "12_deployment" }`
3. Platform allows this — no enforced sequential ordering
4. Agent context includes prior completed phases' artifacts

Business rule confirmed: Platform does NOT enforce sequential phase execution. Phases are a DAG — any phase can be triggered if its evidence is available.

---

## Scenario BF-D — Multi-repo drift cascade

**Trigger:** Contract change in `billing-api` affects `billing-monolith`

1. DriftRecord created for `billing-api` contract change
2. `impacted: [{ node: requirements_artifact, repo_id: billing_monolith_repo_id }]`
3. Traceability graph shows cascading impact
4. Marcus must accept drift in `billing-api` before `billing-monolith` deployment

Business rule: Impact computed from `TraceEdge` graph — all artifacts downstream of the changed
contract are flagged as `impacted`.

---

## Integration failure log (expected)

| Integration | Screen | Failure type | Platform response |
|-------------|--------|--------------|-------------------|
| Confluence | `/onboarding` | `CapabilityUnavailable` | Continue with internal-only |
| Jira | `/onboarding` | `CapabilityUnavailable` | Skip registration; platform-only |
| GitHub | `/onboarding/gap-report` | Webhook not received | Manual drift input required |
| Figma | N/A (brownfield has no design phase by default) | — | — |
| Xray | N/A | — | — |
| Confluence (publish) | `/artifacts/{id}/publish` | Network error | `sor: "internal"`, `sor_link: null` |

---

## State machine — SourceDocument

```
uploaded → extracting → extracted → adopted
                              ↓
                           failed (on extraction error)
```

---

## State machine — DriftRecord

```
open → accepted (decide: "accept")
open → rejected (decide: "reject")
```

---

## Key brownfield-only API calls

| Action | Method | Endpoint | Auth |
|--------|--------|----------|------|
| Get onboarding hub | GET | `/projects/{id}/onboarding/` | member |
| Upload source doc | POST | `/projects/{id}/source-documents/` | member |
| Adopt source doc | POST | `/source-documents/{id}/adopt/` | member (po role) |
| Register Atlassian | POST | `/projects/{id}/onboard-atlassian/` | member |
| Start code intel | POST | `/projects/{id}/code-intel/` | member (tech_lead) |
| Run gap report | POST | `/projects/{id}/gap-report/` | member |
| Get gap report | GET | `/projects/{id}/gap-report/` | member |
| List API contracts | GET | `/projects/{id}/api-contracts/` | member |
| List drift queue | GET | `/projects/{id}/drift/` | member |
| Decide drift | POST | `/drift/{id}/decide/` | member (architect role) |
