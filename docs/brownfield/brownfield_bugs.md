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
| B.2 | Vision agent on adopt | Adopting a doc with visuals runs **`00e_document_vision`** on the user's machine; it transcribes screenshots/tables/diagrams into faithful text, **auto-applied** (no 2nd gate); per-doc carrier hidden from the backlog. | agent | Part B2 | ✅ DONE (live 2026-07-29 — incl. the image-only wireframes) |
| B.3 | Trigger + universal seed | Adopt fires vision when page images exist; `00e` seeded per tenant. **Note:** the `0004` data migration seeds **0 tenants** when run as `sdlc_migrator` — RLS hides them. Use `manage.py seed_agents --tenant <id>`. | agent | Part B3 + migration | ✅ DONE (seeded via `seed_agents`) |
| B.9 | One upload → one artifact at v1 | Upload registers **no** artifact; adopt registers exactly one, `v1`, published, correctly typed — carrying the transcription when pages were read, the plain extraction when not. Retry also lands on v1. | both | PB-7 / PB-8 | ✅ DONE (live) |
| B.10 | Never stranded, never silent | A failed reading recovers to the extracted text rather than leaving the document empty; every outcome reports a plain sentence and a retry. | both | PB-3/4/10/12 | ✅ DONE (live) |

| B.4 | No silent content loss | An auto-applied vision version that is materially **shorter** than the one it replaces is refused: the run fails with a plain reason and the adopted version stays live. Emptiness alone was never a sufficient bar for a publish with no human gate. | agent | Part B fix 1 | ✅ built + tested |
| B.5 | Version, not duplicate | `register_artifact(supersedes=<id>)` takes phase/type/title off the target, so the new version can't fork a second document when the agent restates a title imperfectly. | agent | Part B fix 2 | ✅ built + tested |
| B.6 | Honest vision status | Adopt returns a `vision` state + a finished human sentence (running / no visuals / no companion / already running / failed). The no-companion explanation — previously written and then discarded — now reaches the user. | both | Part B fix 3 | ✅ built + tested |
| B.7 | Failed run stays visible | A vision run that dies **after** dispatch shows on the document row on every page load, not just in the adopt response (the carrier is hidden from the backlog, so nothing else surfaced it). | both | Part B fix 4 | ✅ built + tested |
| B.8 | One row per document | Artifacts list collapses to the newest version per artifact (`?latest=1`); prior versions stay readable as history. 20 uploads read as 20 rows, not 40. Preview's version history now groups by title too, so distinct documents of one type stop listing each other as versions. | both | Part B fix 5 | ✅ built |

> **STATE AS OF 2026-07-29 — Steps 1 & 2 (upload · extract · adopt · vision) are GREEN and live.**
> Part A verified earlier; Part B taken live this session — see *Part B live bring-up* below for
> the 25 defects found and fixed. **Next: Step 3, the connectors (Confluence / Jira / Figma).**
> Carried forward, deliberately, as non-blockers for step-3 testing:
> **(a)** transcription *quality* is unmeasured — the pipeline works, how well it reads a diagram
> is a judgement on real documents (architecture PDF pending team review);
> **(b)** 3 backend test files still assert the pre-PB-7 "upload registers the artifact" behaviour
> and will fail in CI — needs `ALTER ROLE sdlc_app CREATEDB;` before they can even run;
> **(c)** the **auth pass (X-1 / B7-1)** — team decision: build it once the whole onboarding flow
> is green end to end, not step by step. It remains the merge gate to `develop`;
> **(d)** PB-16 — vision runs on every PDF, including text-only ones (open decision).
>
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
4. **PB-16 — when should document vision run?** Today it runs for **every PDF**, because the
   trigger asks "does this document have page images?" and Part A renders every page of every PDF
   whether or not it holds a diagram. So a purely textual PDF (e.g. `09_Security.pdf`, fidelity
   `text`) spends minutes being "read" for no gain. Noted 2026-07-29; team chose to leave the
   behaviour as-is for now. The options when it is picked up:
   - **A. Fidelity only** — run only when fidelity is `images_only`/`empty`. Never wastes time,
     but **misses diagrams inside text-rich PDFs** (the architecture PDF extracts 32 KB of good
     text *and* carries C4 diagrams) — the exact loss Part B exists to prevent.
   - **B. Fidelity + embedded images** — also run when the file carries embedded rasters. Catches
     most real cases; still misses **vector** diagrams, which draw as shapes, not images.
   - **C. Ask at adopt** — a "Read the diagrams in this document" checkbox, pre-ticked per rule B.
     Always right, because the person who uploaded it knows; costs one click.
   No heuristic reliably detects a vector-drawn diagram in a text-rich PDF, which is the argument
   for C.

## Housekeeping

- Test project **"Recon Brownfield Billing"** (`cdf3bcc4-1734-4df7-84da-a95a5336048a`) + one uploaded/adopted doc in tenant `212395b8-…` from the walkthrough — deletable once no longer needed for reproduction.

---

# Part B live bring-up — 2026-07-29

The day document vision first actually ran. Everything below was found by taking Part B live on
the `Edvensoft-brown` tenant against the real SpendLog documents; the ones marked **live** could
not have been found any other way — they only appear when a run genuinely reaches the companion.

## Design hardening (before the first live run)

- **PB-1 · 🔴 A vision pass could silently delete a document's text.** The only check before
  publishing was "is the result non-empty". A pass that returned just the diagram transcriptions
  would satisfy that, publish over the adopted document, and drop its prose from every downstream
  read — with no human gate anywhere in the path. Fix: compare the new body against the one it
  replaces (or, when the run is creating the document's first artifact, against the extraction
  staged at upload) and refuse to publish a version that shrank. 10% slack absorbs honest
  reformatting. — **✅ fixed** · *fired for real on the first live run and blocked a transcription
  that had dropped 93% of the document.*
- **PB-2 · 🟠 A mistyped title forked a duplicate document.** Versioning keys on
  (project, phase, type, title), so "this is the next version of that document" depended on the
  agent echoing three strings back byte-for-byte. One character of drift silently created a second
  artifact instead of a new version. Fix: `register_artifact(supersedes=<id>)` — the platform reads
  the identity off the target. — **✅ fixed**
- **PB-3 · 🔴 Vision failures were invisible.** Adopt swallowed every outcome. Worst case: no
  companion running → the user got none of the benefit, no message, and no way to know. The
  explanation was already written in `NoCompanionError` and thrown away by the caller. Fix: adopt
  returns a `vision` state plus a finished human sentence for each outcome. — **✅ fixed**
- **PB-4 · 🟠 A run that died after dispatch stayed invisible.** Its work item is deliberately
  hidden from the backlog, so nothing pointed at the failure and the user waited forever. Fix: the
  document row reads the run's real state on every page load. — **✅ fixed**
- **PB-5 · 🟠 One document read as two rows.** Fix: the registry list collapses to the newest
  version per artifact (`?latest=1`); prior versions stay readable as history. — **✅ fixed**
- **PB-6 · 🟠 …and that fix went to a screen nothing routes.** `/artifacts` renders
  `ArtifactsRegistry`, not `components/Artifacts` — the collapse was written but never reached the
  screen the user opens. Fix: threaded through `useArtifacts`. — **✅ fixed**

## Structural change — one upload, one artifact, v1

- **PB-7 · 🟠 A single uploaded file produced v1 then v2.** Upload registered v1 and a vision pass
  replaced it with v2, so one file read as a version history the user had no way to interpret.
  Fix: **upload no longer registers an artifact.** It still extracts, renders pages, and sets
  title/fidelity/page count — now stored on the source document. **Adopt** registers the single
  artifact, carrying the vision transcription when the pages were read and the plain extraction
  when they were not. Documents uploaded before the change keep their upload-time artifact and
  take the old path. — **✅ fixed**
- **PB-8 · 🟠 A retried reading still produced v2.** The failure path registered the extraction so
  the document was never empty, and the retry then superseded it. Fix: the retry clears that
  placeholder first, so it registers at v1 exactly as the first attempt would have. Only the
  placeholder is cleared — identified by pointing at the same staged extraction and having come
  from no run — so a real transcription can never be discarded. — **✅ fixed**

## Found live (only a real run could surface these)

- **PB-9 · 🔴 live · Vision could never dispatch, and the onboarding agent never ran either.**
  `trigger_vision` and `trigger_onboarding_agent` resolved the user's companion **outside a tenant
  context**. Under forced row-level security that query returns nothing, so both always concluded
  "no companion connected" however many machines were connected. Vision had never once run; the
  gap report had been silently falling back to the deterministic path since it was built. The two
  other call sites in the same file already did this correctly. — **✅ fixed**
- **PB-10 · 🔴 live · "Adopt again" was a dead end.** The retry only fired for a *failed* run, but
  the common case — adopting with no machine connected — dispatches nothing, so there is no run to
  have failed. The message told the user to connect their machine and adopt again, and adopting
  again did nothing. Fix: a document still holding only its plain extraction retries. — **✅ fixed**
- **PB-11 · 🔴 live · Both write checks measured the wrong artifact.** The platform registers a
  phase-typed artifact for every run holding the agent's closing message. The emptiness check
  counted it, which made that check **unfailable** — a run where the agent registered no document
  at all read as a success. The content-loss guard compared it against the document's text, so a
  short sign-off would have failed a *good* run. Fix: both ignore it and judge only what the agent
  registered as the document. — **✅ fixed**
- **PB-12 · 🔴 live · A failed vision run left the document with nothing.** Auto-apply runs
  *parked* on a write-check failure. Parking waits for a human to resume — but nobody watches a
  vision run, its work item is hidden — so the run sat `stalled` and the document stayed adopted
  with no artifact at all, silently. Fix: an auto-apply run fails instead, which runs the recovery
  that registers the extracted text. — **✅ fixed**
- **PB-13 · 🔴 live · The agent had no platform tools at all.** It correctly refused to fabricate
  and reported the blocker. `get_source_extraction` had been added to the backend MCP server but
  not to the **companion's proxy shim** nor to the **runner's tool allowlist**, so the companion
  could neither expose nor permit it. — **✅ fixed**
- **PB-14 · 🔴 live · Page reads overflowed the transport and killed the run.**
  `JSON message exceeded maximum buffer size of 1048576 bytes` — four lossless page renders at
  full vision resolution pass 1 MiB once base64 adds its third. Bounding the window by **count**
  could never prevent this, because page weight varies enormously. Fix: the window carries a byte
  budget too and returns fewer pages when they are heavy; a single page too heavy on its own is
  re-encoded smaller. Ceiling set to `_MAX_BODY_READ_BYTES` (400 KB) — **the same figure the
  greenfield build path arrived at when it hit this identical wall** — because a payload does not
  travel once: the companion decodes what the platform sends and the MCP layer re-encodes it for
  the stdio hop. Measured on the 13-page architecture PDF: 5 windows, largest 390 KB. — **✅ fixed**
- **PB-15 · 🟠 live · Recovery erased the evidence.** Clearing a failed run's unpublished artifacts
  also removed the run's own phase artifact — the agent's closing message, which the run console
  reads and the only account of *why* a pass failed. — **✅ fixed** (that artifact is now kept)

## Presentation

- **PB-17 · 🔴 Brownfield never told the user their machine was needed.** Reading a document's
  diagrams and analysing code both run on the user's own machine, but a brownfield user only
  learned that from a failure message *after* adopting. Greenfield meets the same step up front on
  the setup checklist. Fix: onboarding now opens with a **Connect your machine** step. — **✅ fixed**
- **PB-18 · 🟠 The word "companion" appeared nowhere else in the product.** A first-time user has
  never met it. Fix: every user-facing message says **"your machine"**, matching "Connect your
  machine" elsewhere, and the failure notice links straight to `/connect`. A test asserts
  "companion" can never reappear in that message. — **✅ fixed**
- **PB-19 · 🔴 Onboarding claimed the machine was connected while the header said offline.** The
  step tested whether a companion had **ever** checked in — right on the setup checklist ("did you
  complete this step once"), wrong here ("can this document's diagrams be read right now"). It also
  never polled, so a companion that stopped while the page was open kept claiming connected. Fix:
  tests `online` only, polls every 4s, and distinguishes *enrolled but not running* (start your
  companion) from *never set up* (connect a machine). — **✅ fixed**
- **PB-20 · 🔴 Every vision-read document appeared twice in the registry.** The second row was the
  run's own phase blob, published alongside the real document — precisely the duplication that
  moving registration to adopt time was meant to end. Fix: run records are hidden from the registry
  list, the same way carrier work items are hidden from the backlog. Still stored, still on the
  run, still what the run console reads. — **✅ fixed**
- **PB-21 · 🟠 Artifact titles renamed the user's own file.** The record read
  `Document vision — Document vision — 09_Security.pdf`: the carrier work item carried the phase in
  its title, and the platform prefixed the phase again. Fix: the carrier is titled with just the
  filename, and an auto-apply run's artifact uses **the user's filename alone** — their name for
  their file is the only one that means anything to them. Other phases are unchanged
  (`Testing — Add login` still reads correctly). — **✅ fixed**

## Still open

- **PB-22 · 🔴 Intermittent transport overflow — RESOLVED: `Pillow` was missing from the running
  image.** Runs died with `JSON message exceeded maximum buffer size of 1048576 bytes`, but only
  sometimes: text-light documents passed, `11_UX_Wireframes.pdf` failed every time.
  `downscale_image_for_vision` catches any failure and returns the image **unchanged**, so with
  Pillow absent **no page image had ever been downscaled** — every render travelled at full size
  and image-heavy documents overran the transport. Pillow was declared in `requirements.txt` all
  along; the container image was stale.

  **Worth keeping the wrong turns visible**, because the lesson outlives the bug: three successive
  payload-sizing fixes (byte-budget window, 400 KB ceiling, per-page step-down) each measured
  convincingly and each treated a symptom — the measurements agreed because they were measuring
  the same undownscaled bytes throughout. A hypothesis that `get_source_extraction` was to blame
  was disproved by measuring it (3.7 KB on the failing document). The diagnosis only came from
  asking *why is this document different* rather than *how do I make the payload smaller*.
  Fix: rebuild the image; make a missing Pillow raise instead of degrading silently (PB-24).
  — **✅ fixed** · verified live: wireframe pages now 255–385 KB each, and the document that had
  never once succeeded transcribed.

- **PB-23 · 🟠 Every vision run threw a 500 on `add_trace_edge`.** Introduced by PB-7: the run is
  now pointed at a SOURCE DOCUMENT, but the agent body still told it to draw a `derives` edge to
  that id — and trace edges accept artifacts on both ends. The agent handled it gracefully and
  recorded provenance in `external_ref.source_document_id` instead, so nothing was lost, but every
  run logged a server error. Fix: the edge is drawn only when the work item named an artifact.
  — **✅ fixed**

- **PB-24 · 🔴 A stale container image hid a declared dependency, and the worker builds its own.**
  `Pillow` sat in `requirements.txt` while being absent from the running container — correct on
  paper, missing in reality, and invisible because the code fails soft. Compounding it: the
  `worker` service builds a **separate image** from `backend`, so `docker compose build backend`
  leaves the worker stale. Fixes: (1) a missing Pillow now raises with a message naming the cause
  and the remedy, instead of silently returning images untouched; (2) recorded here that a
  dependency change requires **`docker compose build backend worker`**, not just `backend`.
  — **✅ fixed**

- **PB-25 · 🟠 Body reads truncated a client's own document.** `get_source_extraction` cut off at
  400 KB and set an advisory `truncated` flag — so a large client specification could be
  transcribed from a partial read and look complete. A ceiling is unavoidable (one agent-transport
  message cannot exceed 1 MiB) but discarding is not: the read is now **paginated**
  (`start` / `next_start` / `total_bytes`), like `get_page_images` already was, so the agent
  receives every byte in pieces. The 400 KB per-message ceiling is deliberately **unchanged** —
  raising it trades a certain small problem for an occasional large one. — **✅ fixed**
