# Brownfield SDLC — Onboarding Flow: Bugs, Gaps & Surgical Fixes

**Single source of truth** for the brownfield onboarding user journey's problems, discovered during a **live walkthrough** of the running application (not a static/doc review). Every item below was observed against the running stack or verified in code + DB.

- **Date:** 2026-07-27
- **Status:** discovered & documented — **no fixes applied yet** (awaiting team selection)
- **Scope:** brownfield onboarding journey end-to-end (create project → upload/adopt docs → register Atlassian → index code → gap report → resume → contracts/drift → publish), frontend + backend.
- **Companion sheet:** these will later be logged into a dedicated brownfield Bugs sheet (kept separate from the greenfield `docs/Bugs.xlsx`).

---

## How this was verified (method)

- Started the Docker stack (`docker compose --profile app up -d`); backend → **shared cloud DB** (`13.203.56.29`) + shared Temporal + real S3; `EMBEDDING_PROVIDER=null`.
- Logged into the app in a browser as a real admin (`test@edvensoft.com`, tenant `212395b8-f118-4eef-93eb-ba2c45468226`).
- **Created a brownfield project via the UI** ("Recon Brownfield Billing", `cdf3bcc4-1734-4df7-84da-a95a5336048a`, multi-repo), then clicked through the whole onboarding flow.
- Uploaded a **real `.docx`** through the real HTTP endpoint, adopted it via the UI, ran register-Atlassian and the gap report, checked contracts/publish.
- Probed every brownfield endpoint's authentication directly.
- Cross-checked results against the DB and source; **treated all docs as untrusted** (they may be outdated).

**Reference for intended behavior:** `docs/USER_JOURNEY_BROWNFIELD.md` (steps BF-A-0…BF-A-9 + scenarios BF-B…D). Note: that journey doc is dated 2026-07-01 and, in places, describes behavior that was never locked into a build spec — flagged where relevant (see B7-4).

---

## Severity legend

| Tag | Meaning |
|-----|---------|
| 🔴 Critical | Breaks the core journey; brownfield onboarding cannot do its job until fixed |
| 🟠 High | Blocks a step, or a real security/correctness gap |
| 🟡 Medium | Will break or badly confuse testing; wrong/ugly behavior |
| ⚪ Low | Polish / brittleness |
| 💡 Enhancement | Missing capability vs. the intended journey; not a regression |

**The critical path in one line:** everything hinges on **B2-1 (typed adoption)**. Fix that and the headline gap-report break (B5-1) and resume (B6-1) come alive. Next tier: **X-1 / B7-1 (auth)** and **B4 (code-intel dispatch)**. The rest is graceful-degradation and polish.

---

## What works today (live-verified — solid ground, do not re-fix)

- Create brownfield project — `track` and `repo_topology` persist (`POST /api/projects/` → 201).
- Upload + extract — **real** `.docx`/`.pdf`/`.xlsx` parsing (python-docx/pypdf/openpyxl, pinned) → draft artifact with real markdown body + provenance (`POST .../source-documents/` → 201, status `extracted`).
- Adopt via UI — `POST /api/source-documents/{id}/adopt/` → 200, document → `adopted`, artifact published.
- Gap-report **engine** runs and reads real DB evidence (the *logic* is real; its input is starved — see B5-1).
- Drift detection + `decide_drift` engine, register-don't-recreate + reconcile orchestration, API-contract export/read-through, cross-repo change-impact — all real and unit-tested (not re-verified live here; no UI path to reach them during onboarding).
- Data model: `SourceDocument` + `DriftRecord` real, full state machines, FORCE-RLS on both.
- Frontend: **zero JS console errors** across every screen; loading/empty/error states render cleanly; the `*Gallery` mock components are quarantined behind a `forceView` prop never passed by the router.

---

# Findings — in exact user-flow order

## Step 0 — Create brownfield project

### B0-1 · 🟡 Creating a project does not switch you to it
- **What:** After creating the brownfield project, the app navigates to `/onboarding` but the **active project stays the previous one** — you edit the wrong project's onboarding.
- **Evidence (live):** created "Recon Brownfield Billing"; the hub rendered **"Onboarding — SpendLog"** and fetched `GET /api/projects/6d4ea6d3…/onboarding/` (the old project). The new project appeared in the selector only as an unselected option.
- **Surgical fix:** In `frontend/src/features/setup/CreateProject.tsx`, on create success set the returned project as the active project via the same project-context setter the top-bar combobox uses, **then** `navigate("/onboarding")`. Root cause: navigation without updating the selected-project state.

### B0-2 · ⚪ `repo_topology` is client-settable and never reconciled at create
- **What:** A multi-repo project persists as "multi" with **zero repos**; topology is authoritative from the client instead of derived.
- **Evidence (DB):** created project row = `track=brownfield, repo_topology=multi, repos=0`.
- **Surgical fix:** Make `repo_topology` a **derived, read-only** field on `ProjectSerializer` (remove it from writable fields); compute it only in `backend/apps/projects/repos.py::_recompute_topology` on repo add/remove. The create-form Single/Multi choice becomes an initial hint that reconciles to the real repo count. Keep `track` writable.

### B0-3 · 💡 Onboarding never guides you to register repositories
- **What:** BF-A-0 expects repos registered, but the onboarding hub jumps to "Index code" assuming a repo exists — with no "add a repository" step.
- **Surgical fix:** Add a repo-registration step/link to `OnboardingHub` (reads `repositories_for`; links to `/repositories` when empty) placed **before** the code-intel step.

---

## Step 1 — Upload & extract legacy docs

### B1-1 · 🔴 Extracted artifacts are typed `"document"` — wrong vocabulary (root cause of the headline break)
- **What:** `ingest_source_document` hardcodes `artifact_type="document"`; nothing classifies the doc as requirements/architecture/PRD.
- **Evidence (DB):** uploaded a requirements `.docx` → artifact `type='document'`, `status=published`, `phase='onboarding'`.
- **Surgical fix:** Classification belongs at **adopt** (the human review gate) — see **B2-1**. Extraction may *pre-suggest* a type from filename/headings as a hint, but must not silently mislabel. (`backend/integrations/onboarding.py::ingest_source_document`.)

### B1-2 · ⚪ Extracted artifact `title` is empty
- **What:** The upload response carries the title, but the persisted `Artifact.title` is blank.
- **Evidence (DB):** upload returned `title:"Legacy Billing Requirements v3"`, but `Artifact.title=''`.
- **Surgical fix:** Thread `title` through `ingest_source_document → register_artifact(title=…)` (derive from the SourceDocument title / first heading / filename). One-line wiring gap.

### B1-3 · ⚪ Ingest is not atomic across S3 + DB
- **What:** A crash between the S3 put and the final `SourceDocument.save` orphans an artifact/body.
- **Surgical fix:** Wrap the `SourceDocument` row creation + `register_artifact` in `transaction.atomic()`; on failure best-effort delete the S3 body written for this ingest. Mirrors the compensation pattern used in the build path.

---

## Step 2 — Adopt as artifact (the review gate)

### B2-1 · 🔴 No document classification on adopt — the core brownfield loop is broken
- **What:** The UI has a single generic **"Adopt"** button; the backend publishes the artifact still typed `"document"`. Combined with B1-1, adopted docs carry a type the gap report never looks for. **This is the root cause of the headline break B5-1.**
- **Evidence (live + DB):** clicked "Adopt" → 200, but the resulting artifact remained `type='document'`.
- **Surgical fix (architecturally correct — adoption is already a human gate, so let the human declare the doc's role there):**
  1. **Backend:** `adopt_source_document(..., target_type)` registers/relabels the adopted artifact with a **canonical lifecycle type** (`requirements`, `architecture`, `prd`, `ux_design`, …) instead of `"document"`, preserving the `extracted_from` provenance edge. Validate `target_type` against a shared canonical set.
  2. **Single source of truth for the vocabulary:** draw the adopt type-picker's options from the **same constant** the gap-report assessor uses (`backend/integrations/onboarding.py`'s phase→type map, ~line 211+). This permanently removes the naming drift (`document` vs `requirements` vs the journey doc's `requirements_doc`).
  3. **UI:** turn "Adopt" into "**Adopt as ▾**" (Requirements / Architecture / PRD / UX / …) in `frontend/src/features/observability/SourceDocuments.tsx`.
- **↳ TEAM DECISION:** human-picks-type (**recommended** — deterministic, matches the journey's "Adopt as Requirements" intent) vs. auto-classify from content (riskier; wrong guesses corrupt the gap report). Recommended: human-picks with an optional auto-suggested default.

### B2-2 · 🟡 Adopt ignores the logged-in user; requires a hand-passed `user_id`
- **What:** Inconsistent with drift/gate/clarification, which use `resolve_actor` (session user).
- **Evidence (live):** `POST /adopt/` with no session still reached business logic (returned a business 400, not 403 auth).
- **Surgical fix:** In `SourceDocumentViewSet.adopt` (`backend/api/views.py`), use `resolve_actor(request, body_user_id)` (session first, body as pre-auth fallback) and gate with `IsAuthenticatedMember`. The service-level product_owner/admin role check stays. (See X-1.)

### B2-3 · ⚪ Re-adopting returns `200 {"idempotent":true}` (journey said "cannot re-adopt")
- **What:** Design-reasonable, not a defect — flagging only so the journey doc and testers expect idempotent, not an error.
- **Surgical fix:** None in code; correct the journey doc's wording (see B7-4 doc-reconciliation note).

---

## Step 3 — Register existing Confluence / Jira

> **LOCKED DESIGN (2026-07-27, team-agreed).** Step 3 is redesigned into three clear parts —
> **Connect → Import Jira backlog (bulk) → Link Confluence docs (user-provided, typed).** The old
> behavior (hard 400 when nothing is connected; a full Confluence space crawl that registered every
> page as an untyped `document`) is replaced. The findings below (B3-1/B3-2/B3-3) are the observed
> problems; the design that resolves them, plus the new **B3-4** (typed Confluence linking), follow.

### B3-1 · 🟡 Hard 400 when no connector is configured — no graceful degradation
- **What:** BF-A-3 (and the locked Phase-1 intent: "no connection → continue internal-only") expects a graceful skip. Reality: an instant error, and — worse — a dead end, because the step gives no way to connect.
- **Evidence (live):** clicking "Register Confluence & Jira" on a project with no Atlassian connected → `POST .../onboard-atlassian/` → **400**.
- **Key point the team raised:** just saying "not connected" is not enough — the user must be able to connect *mid-onboarding*. Connecting already happens on the **Integrations** screen (`/integrations`, creates an `IntegrationConnection` per capability); the user can go there any time and come back. The fix must therefore both (a) stop erroring and (b) route the user to connect and resume.

### B3-2 · 🟡 Raw backend error + tenant UUID leaked into the UI
- **What:** The screen displays `["no 'docstore' connector configured for tenant 212395b8-…"]` — a raw JSON error array containing the tenant UUID.
- **Evidence (live):** rendered verbatim in the OnboardingHub after the 400.

### B3-3 · ⚪ "Register" is offered with no precondition signal
- **What:** The hub presents the action as ready even when no connector exists. (The hub *already* returns `register.docstore_connected` / `tasktracker_connected` — it just isn't used to drive the step's state.)

### Locked design for B3-1 / B3-2 / B3-3 — graceful "Connect, then register" (Option B — inline drawer)
Step 3 becomes a small state machine per tool, driven by the connection status the hub already returns:
- **Not connected** → show *"Confluence not connected" / "Jira not connected"* with a **Connect** action that **opens an inline connect drawer right inside Step 3 (Option B — team decision 2026-07-27)** — the user connects Confluence/Jira **without leaving onboarding**, then the step advances in place. **No error, no raw text, no UUID.**
  - **How (reuse, don't rebuild):** embed the existing capability-connect form component (`frontend/src/features/setup/ConnectCapability.tsx`, used by the Integrations screen) in a drawer opened from Step 3. It already POSTs to the integrations REST (`POST /api/integrations/` with write-only secrets + `test-connection`), so the drawer creates the `IntegrationConnection` exactly as the Integrations screen does — no new backend, no duplicated connect logic.
  - **After a successful connect in the drawer:** invalidate the onboarding-hub query so Step 3 immediately re-renders in the "Connected, not yet registered" state (no page hop, no manual refresh). Close the drawer.
- **Connected, not yet registered** → show the register/import action.
- **Registered** → show a summary ("N pages / M issues") + a "Re-scan / Re-link" affordance.
- **Backend:** stop mapping `CapabilityUnavailable → 400` in the onboard view; the register service skips an unavailable capability gracefully (per-capability note, `200`), mirroring what **publish** already does. Also drop the tenant UUID from the `CapabilityUnavailable` message (`registry.get_capability` / `onboarding.py`).
- **Note:** the drawer is the *only* connect affordance in Step 3 (no link-out). A user can still manage connections on the full Integrations screen later; Step 3 just no longer requires leaving onboarding to get unblocked.

### B3-4 · 🔴 Confluence pages register as untyped `document` → invisible to the Gap Report (typed linking)
- **What:** Even when Confluence *is* connected, today's `register_atlassian` crawls the whole space and registers every page as a generic `type="document"` pointer. Like uploaded docs before the B2-1 fix, `document` matches no lifecycle phase, so **registered Confluence pages never move the Gap Report's resume point** — the platform "reads" them but doesn't "understand" them as phase evidence. (Jira issues are fine — they register as epics/stories/tasks and count toward the backlog / task-breakdown phase.)
- **Team decision (2026-07-27):** do **not** crawl-and-auto-classify hundreds of pages. Instead, **the user provides the specific Confluence page links for the docs the SDLC flow needs, and declares each one's type** — the same "user declares the type" model as the uploaded-doc adopt gate (B2-1). Simpler logic, accurate by construction, no volume/heuristic problem.
- **Locked design — "Link your existing docs":**
  - **Jira — keep the bulk import.** A backlog is meant to come in whole; "Import backlog" registers all issues as work items (unchanged crawl).
  - **Confluence — user-provided typed links.** A small repeatable form: each row = paste the **Confluence page link** + choose the **type** (Requirements / PRD / Architecture / UX Design / Ideation — the **same canonical set + dropdown component** as adopt-as). "＋ Add another."
  - **On submit, per row:** resolve the link → page id; call the existing **`docstore.get_page(page_ref=…)`** (already used by artifact preview) to validate it exists and fetch its title; register a **typed pointer** artifact (`status=published`, `sor=confluence`, `type=<declared>`, `external_ref`=id/url/title — **no body copied**, register-don't-recreate). **Idempotent by page id** (re-adding updates, never duplicates).
  - **Reuse:** the canonical type list, the type dropdown, and the `update_artifact(..., type=…)` / typed-registration path are **shared with the uploaded-doc flow (B2-1)** — one classification path, two sources. **The Gap Report needs no change** — it already counts typed artifacts as evidence.
- **Where in the journey:** inside/after Step 3, before the Gap Report (Step 5): **Upload → Connect + Import Jira backlog + Link Confluence docs → Index code → Gap Report.**
- **The one implementation wrinkle:** parsing a Confluence URL → page id (Cloud `/pages/<id>/…`, Server `?pageId=…`, "tiny" links). Parse the common formats, accept a pasted page ID as fallback, and show a clear *"couldn't find that page — paste the full URL or page ID"* error.
- **Explicitly out of scope (separate, later):** bulk-indexing the *entire* Confluence space into the Knowledge Index for agent-context breadth. Keep that decoupled from gap-report classification — targeted typed links feed the Gap Report; an optional whole-space index (later) feeds agent retrieval.
- **Related:** this is the Confluence sibling of **B2-1** (typed adoption for uploads). Same principle, same shared code.

---

## Step 4 — Index the existing codebase

### B4-1 · 🟠 Code indexing cannot be run from the app at all
- **What:** No trigger control on the hub (step 3 reads "companion CLI; see Section 3 of the guide"), and the companion is offline — so a brownfield user cannot index their code through the app.
- **Evidence (live):** hub step 3 has no button; companion pill shows "Offline".

### B4-2 · 🟠 The `code-intel` endpoint accepts a client-supplied, fabricatable index — no analysis actually runs
- **What:** The real `BuiltinCodeIntel` analyzer exists and is good, but nothing invokes it in production; the endpoint is a persist-only sink for a caller-supplied `{index, summary}`. A fabricated `{"file_count": 99999}` would be accepted and marked "indexed".
- **Evidence:** confirmed in code + serializer/service docstrings ("Real companion-side dispatch … is deferred"); endpoint is auth-gated (403 without session), so it is not itself a public hole, but it does no analysis.
- **Surgical fix (reuse the existing dispatch seam — do not invent new infra):** add `kind="codeintel"` to the Run + Temporal + `RunnerWorkClaimView` dispatch (alongside `plan`/`review`/`build`). The companion claims it, provisions a **read-only worktree** of the repo clone, runs `BuiltinCodeIntel.index()`, and POSTs the real `IntelIndex` to the report endpoint (which already persists artifact + knowledge chunk). Then change `record_code_intel_index` to be the **report sink for that dispatched run** and **reject client-supplied indexes** (or restrict them to the companion token) — closing the fabrication hole and wiring real analysis at once. **Precedent to copy exactly:** the Phase-10 security `reads_code` scan already does read-only-worktree companion analysis — same pattern, so this is consistent, not novel.
- **↳ TEAM DECISION:** build this now, or test brownfield without real code indexing this round (docs-only gap report).

### B4-3 · 🟠 Consequence: the gap report's code/implementation evidence is always blank/unreliable
- **What:** Because B4-1/B4-2 never produce a real `codebase_intelligence` artifact, the gap report can never assess implementation/code from real analysis.
- **Surgical fix:** Resolved by fixing B4-1/B4-2.

### B4-4 · 🟡 The `00c` Intelligent Context Extractor agent is seeded + triggerable but not wired to run (no worktree)
- **What:** `00c_intelligent_context_extractor` (the "Codebase Intelligence Architect" — the LLM reasoning layer over code) is seeded as an AgentSpec and appears in the trigger picker's Plan bucket, so a user *can* trigger it. But triggering it today launches an agent that **can't reach the code it is supposed to analyse.**
- **Exact flow / root cause:**
  - A planning agent only gets a **read-only code worktree** when its catalog entry has `reads_code=True`. That flag is set on **exactly one** agent — `10_security` (`apps/registry/catalog.py:98`); the helper says so: *"10_security today, and 09_testing later"* (`catalog.py:158`).
  - `00c`'s catalog entry has **no `reads_code`** (`catalog.py:107`). So in `trigger_phase`, `if reads_code(agent_key)` is False → **no repo/worktree is resolved** (`orchestration/trigger.py:198`).
  - The driver then runs it in an **empty sandbox with no filesystem** (`drivers/claude_driver.py:264`), and its `codeintel.*` tool surface has no indexed repo to query → its five-layer analysis can't run.
  - `onboarding.py`'s own docstring *assumes* 00c ran ("after … 00c has produced code intelligence, build_gap_report …") but nothing wires it into the flow.
- **Recommended fix (one line + verify):** set `reads_code=True` on the `00c` catalog entry (`catalog.py:107`), exactly like `10_security`, so `trigger_phase` provisions the read-only worktree and the companion runs `00c` with `codeintel.*` against real source. Then add an acceptance test that triggers `context_extraction` and asserts the run carries a `repo` + `reads_code` payload (mirror the 10_security dispatch test). Note: this is the LLM *reasoning* layer and is independent of the deterministic B4 "Index code" path — they coexist (B4 = fast facts; 00c = interpretation + the five structured artifacts downstream agents consume).
- **Status:** logged for later (team decision — do we need the LLM reasoning layer, or is the enriched deterministic artifact (B4-5) enough for the onboarding step?).

### B4-5 · 💡 (DONE) Code-intel artifact was a thin summary — enriched to a deep, readable report
- **What:** The persisted `codebase_intelligence` artifact rendered only counts (`files/commits/hotspots` + a raw `{'.py': 4}` dict) even though `BuiltinCodeIntel` computes far more.
- **Fix (done):** the companion now reports the analyzer's five layers (git activity, architecture/PageRank communities, churn×complexity hotspot **files**, dead code, decision archaeology) via `get_overview`/`get_dead_code`/`get_why`; `_render_code_intel_summary` renders them as readable markdown; the registry pointer stays lean (rich detail in the S3 body) and the rich body is now indexed into the Knowledge Index.

---

## Step 5 — Gap report

### B5-1 · 🔴 HEADLINE: the gap report is blind to uploaded/adopted documents — it always says "all Missing, resume at ideation"
- **What:** The single core promise of brownfield onboarding — *upload what exists → the platform figures out where you are → resume at the right phase* — is broken end-to-end. No matter how many real docs you upload and adopt, the gap report tells you to start from scratch.
- **Evidence (live):** uploaded **and adopted** a requirements `.docx`, ran the gap report → **every phase "✗ Missing"**, `resume_phase = ideation`, blocking = ideation. (`POST /gap-report/` → 200; UI + DB gap_report confirmed.)
- **Root cause:** B1-1 + B2-1. Docs are typed `"document"`; the assessor (`backend/integrations/onboarding.py`, phase→type map ~line 211+ and `_assess_phase`) matches only `requirements`/`prd`/`architecture`/… and **never `document`**.
- **Surgical fix:** Fixing **B2-1** (adopt assigns the canonical type) makes the gap report work as-is — its logic is already correct once fed typed evidence. **Do not** patch the assessor to count raw `"document"` against a guessed phase (that is the lame fix and yields wrong resume points). The clean fix is typed adoption feeding the existing, correct assessor.

### B5-2 · ⚪ Running the gap report from the hub does not refresh the hub's "Resume" step
- **What:** The hub's step 5 stays "Available after the gap report" until you navigate away.
- **Evidence (live):** `POST /gap-report/` → 200, but the hub step didn't update in place.
- **Surgical fix:** In the gap-report/register/adopt mutation hooks (`frontend/src/features/observability/hooks.ts`), `queryClient.invalidateQueries(['onboarding-hub', projectId])` on success; confirm `onboarding_hub.gap.ready` flips once a report exists.

---

## Step 6 — Resume the lifecycle

### B6-1 · 🟠 Resume routing works but resumes at the wrong phase
- **What:** A direct consequence of B5-1 — a real project with docs is told to resume at ideation.
- **Surgical fix:** Resolved by B2-1 / B5-1.

### B6-2 · ⚪ Needs-verification: gap-report evidence passed as `inputs` to the resumed run
- **What:** BF-A-6 says the gap-report evidence is passed to the resumed agent as `inputs`. Not confirmable live (needs a full agent run with a connected companion).
- **Next step:** Verify `trigger_phase` from the gap report threads the evidence refs into the manifest/context; if not, wire the gap-report evidence into the resumed run's inputs.

---

## Step 7 — API contracts, drift, publish

### B7-1 · 🟠 Publish endpoint has no authentication
- **What:** An unauthenticated caller with only the tenant UUID reaches publish — a live-SoR write.
- **Evidence (live):** `POST /api/artifacts/{id}/publish/` with **no session** → **400 business error** (i.e. it passed the auth layer), not 403.
- **Surgical fix:** Add `get_permissions → [IsAuthenticatedMember()]` to `ArtifactViewSet.publish` (`backend/api/views.py`), plus an actor/role check via `resolve_actor` (publish should require a publish-capable role — product_owner/architect/admin). Mirrors the guard `preview`/`code-intel`/`gap-report` already have. (See X-1.)

### B7-2 · 💡 No UI way to export a contract during onboarding, but the empty state tells you to
- **What:** The Contracts screen says "Export one from a repo's onboarding step" — that step does not exist (contracts are produced by an agent run via the Context-Bridge agent).
- **Evidence (live):** `/contracts` empty state on the fresh brownfield project.
- **Surgical fix:** Reword the empty state to the truth ("API contracts appear after a build/run exports one"), or add an explicit user-initiated export action if desired.

### B7-3 · 💡 One `api_contract` per project, but the journey/mockup shows several
- **What:** The model supports a single `api_contract` per project; the mockup (S-27) shows multiple named contracts.
- **Surgical fix:** If multiple named contracts are required, extend the `api_contract` key to `(project, name)`; otherwise correct the journey/mockup.
- **↳ TEAM DECISION:** is multi-contract-per-project a real requirement?

### B7-4 · 🟡 "Reject drift blocks deployment" (journey BF-B) is not built
- **What:** The journey doc promises that rejecting a breaking contract change blocks deployment. It was **never a locked decision** (Phase-4 D6 says reject = "flag for revert"); the code matches the spec, not the journey doc.
- **Evidence:** no drift condition in `backend/apps/gates/readiness.py` / `conditions.py`; `decide_drift` reject only sets status + logs.
- **Surgical fix — ↳ TEAM DECISION on intent:** (a) **build it** — add a readiness condition that blocks the deployment gate while an open/rejected contract `DriftRecord` exists for the project (clean addition to `gates/conditions.py` + `readiness.py`, using the existing change-impact set); or (b) **remove the promise** from `docs/USER_JOURNEY_BROWNFIELD.md` (BF-B). Do not leave the doc claiming a safety coupling that doesn't exist.

---

## Cross-cutting — authentication & data exposure

### X-1 · 🟠 Several onboarding endpoints have no auth (AllowAny) — verified live
- **What:** With only a tenant UUID and **no login**, a caller can: upload source docs, register Atlassian, adopt, publish, and **read the traceability graph**. Tenant isolation (RLS) still holds (a valid tenant UUID is required), so it is bounded — but B3-2 *leaks that tenant UUID*, so the two chain.
- **Evidence (live auth matrix — no session, `X-Tenant-ID` only):**

  | Endpoint | Result | Verdict |
  |---|---|---|
  | `GET .../traceability/` | **200** | ❌ AllowAny — leaks lineage |
  | `POST .../source-documents/` (upload) | **201** | ❌ AllowAny |
  | `POST .../onboard-atlassian/` | 400 (business) | ❌ AllowAny (passed auth) |
  | `POST /source-documents/{id}/adopt/` | 400 (business) | ❌ AllowAny |
  | `POST /artifacts/{id}/publish/` | 400 (business) | ❌ AllowAny |
  | `GET .../onboarding/`, `.../gap-report/`, `.../drift/`, `.../api-contracts/` | **403** | ✅ gated |
  | `GET /artifacts/{id}/preview/`, `POST .../code-intel/` | **403** | ✅ gated |

- **Surgical fix:** Add `get_permissions → [IsAuthenticatedMember()]` (+ role where warranted) to `ProjectViewSet.source_documents`, `onboard_atlassian`, `traceability`, `ArtifactViewSet.publish`, and `SourceDocumentViewSet.adopt`. These are the **only** brownfield actions missing the guard that `onboarding`/`gap-report`/`drift`/`api-contracts`/`preview`/`code-intel` already have — so it's extending an existing, consistent pattern, not new design.
- **↳ TEAM DECISION:** fix before this test round (**recommended** — publish-to-live-SoR with no auth is the sharp edge) or accept for an internal-only round.

### X-2 · 🟡 Tenant UUID leaks in error messages
- **What:** The register error returns the tenant UUID; chains with X-1.
- **Surgical fix:** Scrub tenant identifiers from user-facing error strings (covered by B3-2).

---

## Quality / process (why these shipped, and how to stop the next one)

### Q-1 · 🟡 No test exercises the real upload → adopt → gap-report chain
- **What:** Why B5-1 shipped despite green tests — the gap-report tests insert correctly-typed artifacts directly, so they never exercise the real produce-then-consume chain.
- **Surgical fix:** Add an acceptance test that uploads a real docx, adopts it **as requirements**, runs the gap report, and asserts the resume point moves **off** ideation. This single test guards the core journey.

### Q-2 · 🟡 `test_journey_brownfield.py` loosens assertions at the integration boundaries
- **What:** It skips on upload/adopt failure, accepts "success *or* failure" status codes, and catches bare `Exception` — green-by-construction; it hid B5-1 and X-1.
- **Surgical fix:** Tighten those assertions to fail on the real failure modes; remove the skip-on-failure and status-tolerance branches.

---

## Open decisions for the team (embedded above, collected here)

1. **B2-1 — classification approach:** human-picks-type (recommended) vs. auto-classify from content.
2. **B4-1/B4-2 — code-intel:** build the companion dispatch now, or test docs-only this round.
3. **X-1 / B7-1 — auth:** fix before this test round (recommended), or accept for an internal-only round.
4. **B7-4 — reject-blocks-deploy:** build the coupling, or delete the promise from the journey doc.
5. **B7-3 — multi-contract-per-project:** real requirement or correct the mockup.

## Suggested fix ordering

1. **B2-1** (typed adoption for uploads) → unblocks **B5-1**, **B6-1** (the core journey). ✅ done.
2. **B3-4** (typed Confluence linking — the SoR sibling of B2-1; reuses its shared code) so registered Confluence docs also feed the Gap Report.
3. **Step 3 graceful-connect pass — B3-1 / B3-2 / B3-3 together** (Connect→Import Jira→Link Confluence; no 400, no raw error/UUID, status-driven step).
4. **X-1 / B7-1 / X-2** (auth + info-leak) — one consistent pass.
5. **B4-1/B4-2** (code-intel dispatch) — if in scope this round.
6. **B0-1** (active-project switch). ✅ done.
7. Polish: **B1-2, B1-3, B0-2, B2-2, B5-2, B7-2, B0-3**.
8. Guardrails: **Q-1, Q-2** (add the missing acceptance test; tighten the loose one).
9. Decide + act: **B7-4, B7-3, B6-2**.

---

## Housekeeping

- A test project **"Recon Brownfield Billing"** (`cdf3bcc4-1734-4df7-84da-a95a5336048a`) plus one uploaded/adopted source document was created in the **`test@edvensoft.com`** tenant (`212395b8-…`) during the live walkthrough. It can be deleted once no longer useful for reproduction.
