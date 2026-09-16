# User Journey: Brownfield Project — Legacy Codebase Onboarding to Deployment

**Document purpose:** Complete reference for the brownfield track — importing an existing codebase,
registering legacy artifacts, running a gap report, and resuming the lifecycle from the detected
resume phase through to deployment.

**Platform version:** Phase 4.8 (Hi-Fi React UI + Phase 4.7 backend)
**Last updated:** 2026-09-16
**What changed in this revision:** corrected against the code — the connect-machine step and the
onboarding agents (00c, 00e, 00_onboarding), the artifact types documents are adopted as, the gap
report's actual response shape, what the lifecycle rail really reads, what an adopted document's
status is, the fact that brownfield runs the same twelve phases as greenfield (design included),
the brownfield-only route guard, and where accessibility sits.

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

Same as Greenfield A-0 and A-1. Sarah signs up and invites the team.

**Connect a companion machine (Greenfield A-2) is not optional here.** Two of the onboarding
steps below run on a person's enrolled local companion and fail closed without one: indexing the
code reads a git worktree, and both onboarding agents can stop to ask a question. With no
companion enrolled the platform refuses the agent path with "start your companion" rather than
running it server-side, and falls back to the mechanical path where there is one.

Create project with **brownfield track:**
- `POST /api/projects/` `{ name: "Legacy Billing Modernisation", track: "brownfield", repo_topology: "multi" }`
- Creating a brownfield project lands on `/onboarding`

The three onboarding screens (`/onboarding`, `/onboarding/documents`,
`/onboarding/gap-report`) are **brownfield-only**: opening any of them on a project whose track is
`greenfield` shows "Nothing to onboard yet" and points at the dashboard and the project profile
instead. The guard sits on the routes, not in the screens, so a typed or bookmarked URL behaves
the same as the hidden sidebar link. A project whose track is not known — an API too old to send
it — is let through rather than locked out.

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
6. Extracted draft artifacts created. The types are the bare lifecycle names — `ideation`,
   `requirements`, `prd`, `architecture`, `ux_design` and the other document-authored types — not
   `requirements_doc` / `architecture_doc`

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
1. Review the extracted draft artifact
2. Choose the document's type in the "Adopt as …" picker (pre-filled from the filename, editable), then click "Adopt". The picker offers **every phase's document types** — Ideation, Requirements, PRD, Architecture (plus ADR, data model, API spec, tech stack, security architecture), UX Design (plus user journey, wireframe, design system, accessibility), Task Breakdown, Code Review, test cases and reports, security review and threat model, CI/CD and deployment. The one exclusion is the implementation phase: a running codebase is proven from git, never from an uploaded file
3. `POST /api/source-documents/{id}/adopt/` `{ target_type: "requirements" }` (session-authenticated; `user_id` is an optional pre-auth/test fallback)
4. Platform:
   - Reclassifies the extracted draft into `Artifact(type=<target_type>, status="published", sor="internal")` — so the gap report recognises it as phase evidence
   - Provenance to the original is kept via the artifact's `external_ref` (`source_document_id`)
5. SourceDocument `status` → `adopted`

Screen state: `adopt-gate` (awaiting product_owner) → `adopted`

Business rules:
- Only `product_owner` (or a project-admin / tenant-admin, who may approve any gate) may adopt (403 otherwise)
- `target_type` must be one of the adoptable lifecycle types listed above
- Re-adopting an already-adopted document is **idempotent** — it returns `200 {"idempotent": true}` and changes nothing

---

### BF-A-2b · Document vision reads the pages (00e)

Adopting a document also starts the **document-vision agent** (`00e_document_vision`) on the
adopting user's companion, for that one document. It reads the page images the platform preserved
at upload and writes faithful markdown for the things text extraction cannot carry — diagrams,
screenshots, tables — and that is applied automatically as a **new version of the same artifact**.

- There is **no gate**: the person already adopted these pages, so the result is published without
  a second approval
- It fails closed and quietly: with no companion enrolled the adopt simply skips this step and the
  document stays adopted with its extracted text

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
4. Backend: `record_code_intel_index()` → companion analyses codebase structure. Where a companion
   is enrolled, this runs as the **00c code-intelligence agent** (`00c_intelligent_context_extractor`)
   in a read-only worktree; without one, the mechanical indexer is the fallback
5. The 00c run is hosted on a **carrier work item** the platform creates per project, hidden from
   the backlog and from Phases & Runs — it exists only to give the run something to hang off
6. It runs **headless: there is no gate**. Indexing is a setup step, not a lifecycle phase anyone
   signs off, and the Onboarding hub reporting its progress and what it produced is the review
   surface. It publishes internally only — exporting anything to a system of record stays a
   deliberate human action
7. Polling: `GET /api/projects/{id}/onboarding/` shows:
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
1. `POST /api/projects/{id}/gap-report/` → runs the **00_onboarding assessment agent** on the
   triggering user's companion, against the same hidden carrier work item 00c used. With no
   companion enrolled the platform refuses and keeps the deterministic assessment as the fallback
2. Poll: `GET /api/projects/{id}/gap-report/`
3. Response — phase keys are the bare lifecycle names (`ideation`, not `01_ideation`), each with
   its human `label`, and `evidence` is a list of the artifacts the assessment actually relied on:
   ```json
   {
     "gap_report_id": "…",
     "resume_phase": "prd",
     "resume_label": "PRD",
     "intel_present": true,
     "phases": [
       { "phase": "ideation",     "label": "1. Ideation",     "assessment": "complete",
         "evidence": [{ "artifact_id": "…", "type": "ideation", "sor": "internal", "status": "published" }] },
       { "phase": "requirements", "label": "2. Requirements", "assessment": "partial",  "evidence": [ … ] },
       { "phase": "prd",          "label": "3. PRD",          "assessment": "missing",  "evidence": [] },
       { "phase": "architecture", "label": "4. Architecture", "assessment": "complete", "evidence": [ … ] }
     ],
     "blocking": []
   }
   ```
4. Screen shows: "Resume at: PRD"
5. `OnboardingHub.gap.ready: true`

Screen states: `partial` (resuming mid-lifecycle) / `empty` (nothing done) / `mature` (well-covered)

**This one IS gated, unlike 00c and 00e.** The gap report is a judgement about the client's
project — which phases are done, where to resume — so a `product_owner` owns it before the
pipeline acts on it. The report is registered as a **draft** and the gate approval is what
publishes it; the gate appears on the Gates screen and on the dashboard like any other, even
though its carrier work item is hidden from the backlog.

Business rules:
- Gap report `resume_phase` = first phase whose assessment is not `complete`
- `blocking` = phases still `missing` at or before the resume point

---

### BF-A-6 · Resume lifecycle at detected resume phase

**Screen:** `/work-items` → create epic → trigger from resume phase  
**Actor:** Dev Patel

Steps:
1. Create epic: `POST /api/work-items/` `{ type: "epic", title: "Billing Microservice Extract", feature_stream: "core" }`
2. Navigate to epic lifecycle rail: `GET /api/work-items/{id}/lifecycle/`
3. Every phase on the rail starts at "not_started", including the ones the gap report called
   complete. **The rail reads runs, not the gap report**: a node's state comes from this work
   item's latest run for that phase, plus any pending gate or clarification on it. The gap report
   is a project-level assessment and the rail is per work item, so nothing carries across
4. The resume point is what the gap report screen says, not something the rail shows
5. Trigger PRD: `POST /api/work-items/{id}/trigger/` `{ agent_key: "03_prd" }`
6. The agent works from the adopted artifacts, which are in the registry like any other artifact
   and reach the run through the normal context assembly

Business rules:
- Triggering a phase the gap report called complete is still allowed (re-run with new context)
- The whole lifecycle is a DAG, so no phase order is enforced

**Brownfield runs the same twelve phases as greenfield — design included.** The track decides what
onboarding a project gets; it does not change the phase list. Nothing in the platform varies the
phases, the gates or the gate roles by `Project.track`, so a brownfield work item goes through
ideation, requirements, PRD, architecture, UX design, task breakdown, implementation, code review,
testing, security, CI/CD and deployment exactly as a greenfield one does. What differs is only
where it starts: the gap report says which of them the client already has evidence for.

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
- `requirements` (from source doc adoption) — status: published, `sor: "internal"` (adoption
  publishes the document; it is not left staged, because the gap report only counts published
  evidence)
- `prd` (from phase 03) — status: approved
- `architecture` (adopted from the ADR document) — status: published

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

## Where accessibility sits in this journey

Accessibility is not an onboarding step and is not started by it. Five things touch a brownfield
project:

1. **The baseline audit** — the answer to "how bad is what we already have?". A person starts it
   from the accessibility screens (`/a11y/pages`) against a registered list of routes; onboarding
   never triggers it. It is project-level, and it is **not brownfield-only** — any project can run
   one. The server never opens a browser: the platform freezes the route list and hands out a
   manifest, the companion visits the routes and posts what it saw, and the platform reconciles
   what came back against what was asked for. A route that was asked for and never reported is
   recorded as unreachable, with that as its stated reason
2. **The design gate (phase 05)** carries the WCAG 2.2 AA checklist — the questions a designer can
   settle from the design. Required items unticked block the gate
3. **The testing gate (phase 09)** carries a derived accessibility condition the platform computes
   from the open accessibility defects on the work item; a reviewer cannot tick it by hand. The
   problems a brownfield project inherited from its baseline audit sit on the project's
   accessibility backlog rather than on any story, so by default they are **reported at the gate
   but do not block it** — a team is not stopped on day one by problems they inherited. A project
   can choose to be held to them in its accessibility settings
4. **Phases 09c and 09d** — the accessibility judge (what a scanner cannot decide) and the
   keyboard journey (operating the application and watching focus). Both are gated by `qa_lead`,
   and the journey's findings are tracked without ever blocking a gate
5. **The conformance statement** lays out all 55 Level A and AA criteria with the evidence beside
   each one, and is signed by the accessibility reviewer — the `qa_lead`. The platform suggests a
   level only where the evidence supports it and never asserts one; the claim belongs to the
   person who signs

---

## Integration failure log (expected)

| Integration | Screen | Failure type | Platform response |
|-------------|--------|--------------|-------------------|
| Confluence | `/onboarding` | `CapabilityUnavailable` | Continue with internal-only |
| Jira | `/onboarding` | `CapabilityUnavailable` | Skip registration; platform-only |
| GitHub | `/onboarding/gap-report` | Webhook not received | Manual drift input required |
| Figma | `/runs` (phase 05 UX Design) | Invalid token | UX Design artifact created internally |
| Xray | `/runs` (phases 09 / 09b) | API key expired | Test report as internal artifact |
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
