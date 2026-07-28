# Brownfield SDLC — Onboarding Flow: E2E Verification Tracker + Findings Register

**Single source of truth** for the brownfield onboarding user journey. This file has **two parts**:

1. **Part 1 — E2E Verification Tracker (the reshaped, agent-driven journey).** One row per step of the *new* flow. Each starts **🔲 OPEN**; as the team tests end-to-end on the `brownfield-agent-onboarding` branch we flip each to **✅ DONE** (or **🐞 BUG** with a note, and it stays OPEN until fixed). **This is the live checklist we mark together as we go.**
2. **Part 2 — Legacy findings register (2026-07-27 live walkthrough).** The original bug discovery that *justified* the redesign, kept verbatim for provenance, with each item annotated **✅ resolved-by-redesign** / **🔧 still-open (polish/decision)** so nothing is lost.

- **Journey today:** agent-driven. `00c` (code intelligence) and `00_onboarding` (phase-completeness → gap report) agents *reason*; the old deterministic Python rules table is kept only as a **fallback** (no companion). See `docs/USER_JOURNEY_BROWNFIELD.md` for the narrative and the plan at `shiny-tinkering-tide.md` for the build detail.
- **Branch:** all changes live on **`brownfield-agent-onboarding`** (develop stays clean); merge to develop only when the tracker below is all-green.
- **Companion matters:** the *agent* paths need a companion enrolled for the test project + the branch's companion code checked out. No companion → the deterministic/mechanical fallbacks run (and those rows verify the fallback, not the agent).

---

## Legend

| Status | Meaning |
|--------|---------|
| 🔲 OPEN | Not yet verified end-to-end on the live stack |
| ✅ DONE | Verified working end-to-end (agent path unless noted) |
| 🐞 BUG | Tested, broke — stays OPEN; bug logged inline + fixed on the branch |
| ⏭️ N/A | Not exercised this round (e.g. no companion → agent path skipped) |

**Path column:** `agent` = companion-driven agent run · `fallback` = deterministic/mechanical (no companion) · `both` = should be checked on both paths.

---

# Part 1 — E2E Verification Tracker (reshaped agent-driven journey)

Walk these **in order** against the running stack. Update the **Status** cell as we test.

## Step 0 — Create the brownfield project & land on onboarding

| # | Step | What to verify | Path | Delivered by | Status |
|---|------|----------------|------|--------------|--------|
| S0.1 | Create brownfield project | Create → app switches the **active project to the new one** and lands on `/onboarding` for *it* (not the previous project). | both | B0-1 fix | 🔲 OPEN |
| S0.2 | Repo topology | `repo_topology` reflects the real repo count (derived, not a stale client hint). | both | B0-2 fix | 🔲 OPEN |
| S0.3 | Register a repository | Onboarding guides you to add a repo **before** Index-code; empty state links to `/repositories`. | both | B0-3 fix | 🔲 OPEN |

## Step 1 — Upload & extract legacy docs (now incl. txt / html)

| # | Step | What to verify | Path | Delivered by | Status |
|---|------|----------------|------|--------------|--------|
| S1.1 | Upload `.docx/.pdf/.xlsx` | Real parse → draft artifact with real markdown body + provenance; `Artifact.title` populated (not blank). | both | existing + B1-2 | 🔲 OPEN |
| S1.2 | Upload **`.txt`** | Plain-text ingest → extracted draft (utf-8, zero-dep). | both | Slice 1 (`extract.py`) | 🔲 OPEN |
| S1.3 | Upload **`.html/.htm`** | Stdlib tag-stripper → clean text (headings + `- ` lists kept, no `login .` punctuation gaps, script/style dropped). | both | Slice 1 (`_extract_html`) | 🔲 OPEN |
| S1.4 | Unsupported type | A binary (e.g. `logo.png`) is rejected clearly, not silently mislabeled. | both | Slice 1 (`_kind`) | 🔲 OPEN |

## Step 1b / 2 — Adopt across the **full lifecycle** (humanized "Type (Phase)")

| # | Step | What to verify | Path | Delivered by | Status |
|---|------|----------------|------|--------------|--------|
| S2.1 | Adopt-as picker | The dropdown lists **all lifecycle types except implementation**, labeled humanized **"Wireframe (UX Design)"** etc. — served from the backend (`adopt_types`), no underscores, no `code`. | both | Slice 2 (`adoptable_type_choices`) | 🔲 OPEN |
| S2.2 | Adopt assigns canonical type | Adopting relabels the artifact to the chosen canonical lifecycle type (not `document`), keeps the `extracted_from` provenance edge, uses the **session user** (no hand-passed `user_id`). | both | B2-1 + B2-2 | 🔲 OPEN |
| S2.3 | Backend/frontend never drift | Adopt vocabulary comes from one server-derived source (`_LIFECYCLE`); UI renders it — changing `_LIFECYCLE` changes both. | both | Slice 2 | 🔲 OPEN |

## Step 1c / 2b — Lossless capture (Part A) & document vision (Part B)

The crux of trust: whatever is uploaded (text, tables, diagrams, screenshots) must reach the agents **in full**, and the user must **see** it captured correctly. Detail + slice log: `onboarding_fidelity_plan.md`; live fix log: `Bugs-fix.md`.

| # | Step | What to verify | Path | Delivered by | Status |
|---|------|----------------|------|--------------|--------|
| A.1 | High-fidelity extraction | PDF text + tables reconstructed (pymupdf4llm), embedded images captured (PDF/DOCX/HTML); no wall-of-text, no `## Page N`, no `<br>` literals, no empty-table grids. | both | Part A1 + A-fix | ✅ DONE |
| A.2 | Page renders preserved | Every PDF page (and embedded images) rendered + stored in S3 as `external_ref.page_images`. | both | Part A2 | ✅ DONE |
| A.3 | See the original | Gated viewer streams the original file + page images next to the extracted text. | both | Part A3 | ✅ DONE |
| A.4 | Honest status | Row badge = truth (`text` / `Needs AI read` / `No text`), not a blanket "Extracted"; image-only PDF shows a plain-language "pages preserved, AI reads them" message (dynamic page count). | both | Part A4 | ✅ DONE |
| B.0 | Vision capability | The MCP tool-result **image pipe reaches the model on the subscription CLI** (spike proven — model read a secret off a returned image). | agent | Part B0 | ✅ DONE (spike) |
| B.1 | Image pipe tool | `get_page_images(artifact_id)` streams a doc's page images as image blocks (paginated ≤4/call, downscaled ≤1568px). | agent | Part B1 | ✅ unit-tested |
| B.2 | Vision agent on adopt | Adopting a doc with visuals runs **`00e_document_vision`** on the companion; it transcribes screenshots/tables/diagrams into faithful text, **auto-applied** as a new version (no 2nd gate); per-doc carrier hidden from the backlog. | agent | Part B2 | 🔲 OPEN (built; needs seed + companion) |
| B.3 | Trigger + universal seed | Adopt fires vision only when page images exist; `00e` seeded on every tenant via the `0004` data migration (+ on-create hook for new tenants). | agent | Part B3 + migration | 🔲 OPEN (run migrate + restart companion) |

> **Part A: ✅ team-verified live** ("strongly completed… everything works"). **Part B: built + unit-tested, not yet live** — to exercise it: run migrations (seeds `00e`) and restart the companion, then adopt the Architecture / wireframes PDF and confirm diagrams/screens arrive as text.

## Step 3 — Connect → Import Jira backlog → Link Confluence docs (typed) → Figma

| # | Step | What to verify | Path | Delivered by | Status |
|---|------|----------------|------|--------------|--------|
| S3.1 | Graceful connect (no 400) | Not-connected → **inline connect drawer** in Step 3 (no hard 400, no raw error, no tenant UUID leaked); after connect the step advances in place. | both | B3-1/B3-2/B3-3 | 🔲 OPEN |
| S3.2 | Import Jira backlog | Bulk import registers issues as epics/stories/tasks (work items). | both | existing | 🔲 OPEN |
| S3.3 | Link Confluence docs (typed) | Per-row paste link + choose type → **typed pointer** artifact (`sor=confluence`, no body copied), idempotent by page id. Feeds the gap report. | both | B3-4 | 🔲 OPEN |
| S3.4 | Surface Figma (designsource) | Step 3 shows a **Figma / UX-design** connect row via the existing `designsource` capability; `onboarding_hub` reports `designsource_connected`. | both | Slice 2 (surface only) | 🔲 OPEN |

## Step 4 — Index the codebase → **`00c` agent** (or mechanical fallback)

| # | Step | What to verify | Path | Delivered by | Status |
|---|------|----------------|------|--------------|--------|
| S4.1 | Trigger "Index code" | Button dispatches; UI shows the correct mode banner (**agent** when companion enrolled, **mechanical** otherwise). | both | Slice 5/6 (REST + UI) | 🔲 OPEN |
| S4.2 | `00c` reaches CodeIntel tools | With companion: `00c` runs in a **read-only worktree** and can call `index()` + the 8 read tools via the new `codeintel` MCP server; produces the 5 intelligence artifacts incl. `codebase_intelligence`. | agent | Slice 4 (`codeintel_mcp.py`, `00c reads_code=True`) | 🔲 OPEN |
| S4.3 | No source leaves the machine | Code analysis is local-only (git + static); nothing network-bound; artifact stores pointers + rich body in S3, lean registry pointer. | agent | Slice 4 + B4-5 | 🔲 OPEN |
| S4.4 | Mechanical fallback | No companion → the mechanical `CodeIntelJob` path still produces a `codebase_intelligence` artifact (no dead end). | fallback | B4-1/B4-2 | 🔲 OPEN |
| S4.5 | Gap-report gating | "Run gap report" enables only **after** a `codebase_intelligence` artifact exists. | both | Slice 2/6 | 🔲 OPEN |

## Step 5 — Gap report → **`00_onboarding` agent** (or deterministic fallback)

| # | Step | What to verify | Path | Delivered by | Status |
|---|------|----------------|------|--------------|--------|
| S5.1 | Trigger "Run gap report" | Dispatches; correct mode banner (**agent** vs **deterministic**). | both | Slice 5/6 | 🔲 OPEN |
| S5.2 | Agent reasons, calls `submit_gap_report` | `00_onboarding` assesses each phase Complete/Partial/Missing and **calls `submit_gap_report`** — it does **not** dump the assessment into a document (the ideation-class prompt-adherence risk). | agent | Slice 5 (agent body + tool) | 🔲 OPEN |
| S5.3 | Contract guaranteed | Whatever the agent emits, the stored `external_ref` has the exact shape `{source, resume_phase, phases:[{phase,label,status,evidence}], blockers, intel_present}` — the shared `write_gap_report_artifact` normalizes it. UI/`types.ts` unchanged. | agent | Slice 5 (shared writer) | 🔲 OPEN |
| S5.4 | Gap report is accurate | With real adopted docs + code intel, the report reflects reality — **not** "all Missing, resume at ideation." Resume point matches the evidence. | both | B5-1 (redesign) | 🔲 OPEN |
| S5.5 | Deterministic fallback | No companion → `build_gap_report` writes the **byte-identical** `external_ref` via the same shared writer. | fallback | Slice 5 | 🔲 OPEN |
| S5.6 | Hub refreshes in place | Running the report flips the hub's Resume step without a manual reload (both query keys invalidated). | both | B5-2 + Slice 6 | 🔲 OPEN |

## Step 6 — Resume the lifecycle at the agent-decided phase

| # | Step | What to verify | Path | Delivered by | Status |
|---|------|----------------|------|--------------|--------|
| S6.1 | Resume routing | Resume lands at the phase the gap report chose (e.g. a mid-implementation client resumes at implementation, **not** ideation). | both | B6-1 (redesign) | 🔲 OPEN |
| S6.2 | Evidence threaded to the run | The gap-report evidence refs are passed as `inputs` to the resumed run's manifest/context. | agent | B6-2 (verify) | 🔲 OPEN |

## Step 7 — Contracts, drift, publish

| # | Step | What to verify | Path | Delivered by | Status |
|---|------|----------------|------|--------------|--------|
| S7.1 | Publish is authenticated | `publish` requires a logged-in, publish-capable actor (no AllowAny to a live-SoR write). | both | B7-1 / X-1 | 🔲 OPEN |
| S7.2 | No gate bypass | Nothing reaches a system-of-record before its gate is APPROVED. | both | platform invariant | 🔲 OPEN |
| S7.3 | Contracts / drift | Drift detection + `decide_drift` behave per spec; contract empty-state copy is truthful. | both | B7-2/B7-4 (decision) | 🔲 OPEN |

## Cross-cutting

| # | Step | What to verify | Path | Delivered by | Status |
|---|------|----------------|------|--------------|--------|
| X.1 | Auth on onboarding endpoints | `source_documents`, `onboard_atlassian`, `traceability`, `publish`, `adopt` all require an authenticated member (no AllowAny). | both | X-1 | 🔲 OPEN |
| X.2 | No tenant UUID in errors | User-facing errors never leak the tenant UUID. | both | X-2 / B3-2 | 🔲 OPEN |
| X.3 | No console errors | Every onboarding screen renders clean (no JS console errors) across states. | both | existing | 🔲 OPEN |

---

## E2E prerequisites (read before the first pass)

1. **Check out `brownfield-agent-onboarding`** on both the app host and the companion host.
2. **Restart** backend + worker + frontend (and the companion). **No migration, no re-seed** needed.
3. **Companion enrolled** for the test project → you exercise the **agent** rows. No companion → you exercise the **fallback** rows (mark the agent-only rows ⏭️ N/A for that pass).
4. For Step 4 the companion needs a **repo clone + `--worktrees`** so `00c` gets a read-only worktree.
5. Known non-issue: `test_tools_are_tenant_scoped` fails under the postgres-superuser test DB (RLS bypass) — pre-existing/environmental, proven on a clean tree. Not a brownfield regression.

**As we test:** flip each row's **Status** to ✅ DONE when it passes, or 🐞 BUG with a one-line note + the run id/console line if it breaks — then I fix it on the branch and we re-run that row.

---

# Part 2 — Legacy findings register (2026-07-27 live walkthrough)

> Kept for provenance — this is the discovery that justified the reshaped journey. Each item is annotated with its **new status**. **✅ resolved-by-redesign** = the agent-driven flow or an already-shipped fix closes it (re-confirm via the Part 1 row noted). **🔧 still-open** = polish/decision not yet done; carry it into the Part 1 pass.

## Method (how it was verified)

- Docker stack up; backend → shared cloud DB (`13.203.56.29`) + shared Temporal + real S3; `EMBEDDING_PROVIDER=null`.
- Logged in as a real admin (`test@edvensoft.com`, tenant `212395b8-…`); created "Recon Brownfield Billing" (`cdf3bcc4-…`, multi-repo) via the UI and clicked the whole flow.
- Uploaded/adopted a real `.docx` through the real HTTP endpoint; ran register-Atlassian + gap report; checked contracts/publish; probed every endpoint's auth; cross-checked DB + source; treated all docs as untrusted.

## Severity legend (original)

| Tag | Meaning |
|-----|---------|
| 🔴 Critical | Breaks the core journey |
| 🟠 High | Blocks a step, or a real security/correctness gap |
| 🟡 Medium | Breaks/badly confuses testing |
| ⚪ Low | Polish / brittleness |
| 💡 Enhancement | Missing capability vs. intended journey; not a regression |

## What works today (live-verified — solid ground)

- Create brownfield project — `track`/`repo_topology` persist.
- Upload + extract — real `.docx/.pdf/.xlsx` parsing → draft artifact with real body + provenance.
- Adopt via UI — document → `adopted`, artifact published.
- Gap-report engine reads real DB evidence (logic real; input was starved — B5-1).
- Drift + `decide_drift`, register-don't-recreate + reconcile, API-contract read-through, cross-repo change-impact — all real and unit-tested.
- Data model: `SourceDocument` + `DriftRecord` real, full state machines, FORCE-RLS.
- Frontend: zero JS console errors across screens; loading/empty/error states clean.

## Findings — in user-flow order (with new status)

### Step 0 — Create brownfield project
- **B0-1 · 🟡 Creating a project does not switch you to it.** Fix: set returned project active before `navigate("/onboarding")`. — **✅ resolved (done)** · re-confirm at **S0.1**.
- **B0-2 · ⚪ `repo_topology` client-settable, never reconciled.** Fix: derived read-only field. — **✅ resolved (done)** · re-confirm at **S0.2**.
- **B0-3 · 💡 Onboarding never guides you to register repositories.** Fix: repo-registration step before Index-code. — **✅ resolved (done)** · re-confirm at **S0.3**.

### Step 1 — Upload & extract
- **B1-1 · 🔴 Extracted artifacts typed `"document"` (root cause of the headline break).** Fix: classify at adopt. — **✅ resolved via B2-1** · re-confirm at **S2.2**.
- **B1-2 · ⚪ Extracted artifact `title` empty.** Fix: thread `title` into `register_artifact`. — **✅ resolved (done)** · re-confirm at **S1.1**.
- **B1-3 · ⚪ Ingest not atomic across S3 + DB.** Fix: `transaction.atomic()` + compensating S3 delete. — **✅ resolved (done)**.
- *(new)* txt/html upload support — **added (Slice 1)** · verify at **S1.2/S1.3**.

### Step 2 — Adopt (the review gate)
- **B2-1 · 🔴 No classification on adopt — core loop broken.** Fix: `adopt_source_document(..., target_type)` assigns a canonical lifecycle type from the shared vocabulary. — **✅ resolved (done)**; **widened to full lifecycle + humanized labels (Slice 2)** · re-confirm at **S2.1/S2.2**.
- **B2-2 · 🟡 Adopt ignores logged-in user.** Fix: `resolve_actor` + `IsAuthenticatedMember`. — **✅ resolved (done)** · re-confirm at **S2.2**.
- **B2-3 · ⚪ Re-adopt returns idempotent 200.** Design-reasonable; fix was doc wording. — **✅ resolved (doc)**.

### Step 3 — Register Confluence / Jira
- **B3-1 · 🟡 Hard 400 when no connector.** Fix: graceful skip + inline connect drawer. — **✅ resolved (done)** · re-confirm at **S3.1**.
- **B3-2 · 🟡 Raw error + tenant UUID leaked to UI.** — **✅ resolved (done)** · re-confirm at **S3.1/X.2**.
- **B3-3 · ⚪ "Register" offered with no precondition signal.** Fix: status-driven step. — **✅ resolved (done)** · re-confirm at **S3.1**.
- **B3-4 · 🔴 Confluence pages register as untyped `document`.** Fix: user-provided typed links (SoR sibling of B2-1). — **✅ resolved (done)** · re-confirm at **S3.3**.
- *(new)* Figma/UX-design connector surfaced in Step 3 — **added (Slice 2)** · verify at **S3.4**.

### Step 4 — Index the codebase
- **B4-1 · 🟠 Code indexing not runnable from the app.** — **✅ resolved**: Index-code button + dispatch (mechanical) **and** agent path (`00c`) · verify at **S4.1/S4.4**.
- **B4-2 · 🟠 `code-intel` endpoint accepted a fabricatable index.** Fix: real dispatch via the `reads_code` worktree seam; report sink. — **✅ resolved** · verify at **S4.2/S4.4**.
- **B4-3 · 🟠 Consequence: gap-report code evidence blank.** — **✅ resolved by B4-1/B4-2**.
- **B4-4 · 🟡 `00c` seeded but not wired (no worktree).** Fix: `00c reads_code=True` + companion CodeIntel MCP. — **✅ resolved (Slice 4)** · verify at **S4.2**.
- **B4-5 · 💡 Code-intel artifact enriched to a deep, readable report.** — **✅ resolved (done)** · verify at **S4.3**.

### Step 5 — Gap report
- **B5-1 · 🔴 HEADLINE: gap report blind to adopted docs ("all Missing, resume at ideation").** — **✅ resolved**: typed adoption feeds the assessor; the agent path reasons over real evidence · verify at **S5.4**.
- **B5-2 · ⚪ Running the report doesn't refresh the hub's Resume step.** Fix: invalidate the onboarding query. — **✅ resolved (done)** · re-confirm at **S5.6**.

### Step 6 — Resume the lifecycle
- **B6-1 · 🟠 Resume routes to the wrong phase.** — **✅ resolved by B5-1 + the agent path** · verify at **S6.1**.
- **B6-2 · ⚪ Needs-verification: gap-report evidence passed as `inputs` to the resumed run.** — **🔧 still-open (verify live)** · **S6.2**.

### Step 7 — API contracts, drift, publish
- **B7-1 · 🟠 Publish endpoint has no authentication.** Fix: `IsAuthenticatedMember` + role check. — **🔧 still-open unless already applied** · verify at **S7.1** (part of the X-1 auth pass).
- **B7-2 · 💡 No UI way to export a contract during onboarding, but empty state implies one.** — **🔧 still-open (reword or add export)** · **S7.3**.
- **B7-3 · 💡 One `api_contract` per project, mockup shows several.** — **🔧 team decision** (multi-contract real?) · **S7.3**.
- **B7-4 · 🟡 "Reject drift blocks deployment" not built.** — **🔧 team decision** (build the coupling or delete the promise) · **S7.3**.

### Cross-cutting — auth & data exposure
- **X-1 · 🟠 Several onboarding endpoints AllowAny (upload, register, adopt, publish, traceability).** Fix: add `IsAuthenticatedMember` (+ role) to the five missing guards. — **🔧 still-open unless already applied** · verify at **X.1**.
- **X-2 · 🟡 Tenant UUID leaks in error messages.** — **✅ resolved via B3-2**; sweep others · verify at **X.2**.

### Quality / process
- **Q-1 · 🟡 No test exercises the real upload → adopt → gap-report chain.** — **🔧 add acceptance test** (uploads real docx, adopts as requirements, asserts resume moves off ideation).
- **Q-2 · 🟡 `test_journey_brownfield.py` loosens assertions.** — **🔧 tighten** (remove skip-on-failure + status tolerance).

## Open team decisions (still live)

1. **B7-4** — reject-drift-blocks-deploy: build the coupling, or delete the promise from the journey doc.
2. **B7-3** — multi-contract-per-project: real requirement or correct the mockup.
3. **X-1 / B7-1** — auth pass: confirm the five AllowAny guards are added before merging to develop.

## Housekeeping

- Test project **"Recon Brownfield Billing"** (`cdf3bcc4-1734-4df7-84da-a95a5336048a`) + one uploaded/adopted doc in tenant `212395b8-…` from the walkthrough — deletable once no longer needed for reproduction.
