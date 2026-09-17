# Brownfield SDLC — Onboarding Flow: E2E Verification Tracker + Findings Register

**Single source of truth** for the brownfield onboarding user journey. This file has **two parts**:

1. **Part 1 — E2E Verification Tracker (the reshaped, agent-driven journey).** One row per step of the *new* flow. Each starts **🔲 OPEN**; as the team tests end-to-end on the `brownfield-agent-onboarding` branch we flip each to **✅ DONE** (or **🐞 BUG** with a note, and it stays OPEN until fixed). **This is the live checklist we mark together as we go.**
2. **Part 2 — Legacy findings register (2026-07-27 live walkthrough).** The original bug discovery that *justified* the redesign, kept verbatim for provenance, with each item annotated **✅ resolved-by-redesign** / **🔧 still-open (polish/decision)** so nothing is lost.

- **Journey today:** agent-driven. `00c` (code intelligence) and `00_onboarding` (phase-completeness → gap report) agents *reason*; the old deterministic Python rules table is kept only as a **fallback** (no companion). See `docs/USER_JOURNEY_BROWNFIELD.md` for the narrative, and `Bugs-fix.md` in this folder for the build detail slice by slice. *(Until 2026-09-17 this line also pointed at a plan called `shiny-tinkering-tide.md`. No such file exists, in this tree or anywhere in the git history — it was a working name that never became a document.)*
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

| B.4 | No silent content loss | An auto-applied vision version that is materially **shorter** than the one it replaces is refused: the run fails with a plain reason and the adopted version stays live. Emptiness alone was never a sufficient bar for a publish with no human gate. | agent | Part B fix 1 | ✅ DONE (live — fired for real on a 93% loss) |
| B.5 | Version, not duplicate | `register_artifact(supersedes=<id>)` takes phase/type/title off the target, so the new version can't fork a second document when the agent restates a title imperfectly. | agent | Part B fix 2 | ✅ DONE (live) |
| B.6 | Honest vision status | Adopt returns a `vision` state + a finished human sentence (running / no visuals / no companion / already running / failed). The no-companion explanation — previously written and then discarded — now reaches the user. | both | Part B fix 3 | ✅ DONE (live) |
| B.7 | Failed run stays visible | A vision run that dies **after** dispatch shows on the document row on every page load, not just in the adopt response (the carrier is hidden from the backlog, so nothing else surfaced it). | both | Part B fix 4 | ✅ DONE (live) |
| B.8 | One row per document | Artifacts list collapses to the newest version per artifact (`?latest=1`); prior versions stay readable as history. 20 uploads read as 20 rows, not 40. Preview's version history now groups by title too, so distinct documents of one type stop listing each other as versions. | both | Part B fix 5 | ✅ DONE (live) |

> **STATE AS OF 2026-07-29 — Steps 1 & 2 (upload · extract · adopt · vision) are GREEN and live.**
> Part A verified earlier; Part B taken live this session — see *Part B live bring-up* below for
> the 25 defects found and fixed. **Next: Step 3, the connectors (Confluence / Jira / Figma).**
> Carried forward, deliberately, as non-blockers for step-3 testing:
> **(a)** ~~transcription quality unmeasured~~ → **✅ team-reviewed 2026-07-29: the architecture
> transcription is "the best one and very good".** This was the one thing the platform could not
> judge for itself — the guard can prove text was not LOST, never that a diagram was read WELL.
> Quality is now confirmed on a real client-shaped document by the people who own it;
> **(b)** 3 backend test files still assert the pre-PB-7 "upload registers the artifact" behaviour
> and will fail in CI — needs `ALTER ROLE sdlc_app CREATEDB;` before they can even run;
> **(c)** the **auth pass (X-1 / B7-1)** — team decision: build it once the whole onboarding flow
> is green end to end, not step by step. It remains the merge gate to `develop`;
> **(d)** PB-16 — vision runs on every PDF, including text-only ones (open decision).
>
> **Part A: ✅ team-verified live** ("strongly completed… everything works").
> **Part B: ✅ team-verified live 2026-07-29** — the full document set (Architecture, wireframes,
> Security, PRD) was adopted end to end on the team's own machine: text-and-diagram PDFs, the
> image-only wireframes, and a retry after a deliberate failure. The PRD and Architecture
> transcriptions were reviewed and accepted by the team. **Parts A and B are CLOSED.**

## Step 3 — Connect → Import Jira backlog → Link Confluence docs (typed) → Figma

| # | Step | What to verify | Path | Delivered by | Status |
|---|------|----------------|------|--------------|--------|
| S3.1 | Graceful connect (no 400) | Not-connected → connect **pop-up** in Step 3 (no hard 400, no raw error, no tenant UUID leaked); the checklist below does not move while it is open; after connect the step advances in place. | both | B3-1/B3-2/B3-3 + S3-2/S3-4 | ✅ DONE (live) |
| S3.2 | Import Jira backlog | Bulk import registers issues as epics/stories/tasks (work items). No adopt step — a Jira issue already declares its type. | both | existing | ✅ DONE (live — 13 real issues) |
| S3.3 | Bring in Confluence docs | Paste link → the page is snapshotted into a **source document** awaiting adoption (no artifact yet); review the extraction, adopt with a type, vision reads its attached diagrams. One artifact at v1. Idempotent by page id. | both | B3-4 + S3-1/S3-3 + S3-6/7/8 | ✅ DONE (live) |
| S3.4 | Surface Figma (designsource) | Step 3 shows a **Figma / UX-design** connect row via the existing `designsource` capability; `onboarding_hub` reports `designsource_connected`. | both | Slice 2 (surface only) | 🟡 connect pop-up verified; **no Figma account yet — import untested** |

## Step 4 — Index the codebase → **`00c` agent** (or mechanical fallback)

| # | Step | What to verify | Path | Delivered by | Status |
|---|------|----------------|------|--------------|--------|
| S4.1 | Trigger "Index code" | Button dispatches; UI shows the correct mode banner (**agent** when companion enrolled, **mechanical** otherwise). | both | Slice 5/6 (REST + UI) | ✅ DONE (live, 2026-07-31 — after S4-3/4/5/6) |
| S4.1b | **Headless UX** (team requirement, 2026-07-31) | Click → button locks to "Indexing dispatched…" + amber working line for the life of the run; on completion the button reverts, a done line appears with a link **straight to the artifact preview**; re-index clears the old message. A pending `ask_human` shows a "Waiting on you" card linking to Clarifications. | agent | S4-3/4/5/6 | ✅ DONE (live). Post-run state confirmed **in the data** — hub reads `indexed` with the artifact id linked. The rendered done message + link have **not yet been confirmed by eye**; the "Waiting on you" question state remains unseen (no run has asked one). |
| S4.1c | **Fully hidden** (team requirement, 2026-07-31) | The run opens **no gate**, appears in **no** run list (Phases & Runs) and does **not** move the dashboard "Needs me" counts. Progress lives only on the Onboarding hub. | agent | S4-1/S4-2 | ✅ DONE (verified live — `pending gates: 0` across a full run) |
| S4.2 | `00c` reaches CodeIntel tools | With companion: `00c` runs in a **read-only worktree** and can call `index()` + the 8 read tools via the new `codeintel` MCP server; produces the 5 intelligence artifacts incl. `codebase_intelligence`. | agent | Slice 4 (`codeintel_mcp.py`, `00c reads_code=True`) | ✅ DONE (**verified live 2026-07-31, run `98ab9a8c`** — 7 artifacts published, `file_count 73`, `commits 22`, 0 gates. Unblocked by S4-13 + S4-14, after three killed runs) |
| S4.3 | No source leaves the machine | Code analysis is local-only (git + static); nothing network-bound; artifact stores pointers + rich body in S3, lean registry pointer. | agent | Slice 4 + B4-5 | ✅ DONE (verified live — analysis ran entirely in the companion worktree; only findings + S3 body pointers reached the platform) |
| S4.4 | Mechanical fallback | No companion → the mechanical `CodeIntelJob` path still produces a `codebase_intelligence` artifact (no dead end). | fallback | B4-1/B4-2 | 🔲 OPEN (not exercised — a companion has been enrolled throughout) |
| S4.5 | Gap-report gating | "Run gap report" enables only **after** a `codebase_intelligence` artifact exists. | both | Slice 2/6 | ✅ DONE (observed both ways live: `gap.ready` was **false** through the cleanup with no intel artifact, and **true** once run `9d1b4d32` published one) |

> **STEP 4 IS GREEN (2026-08-03).** Run **`9d1b4d32`** completed in 10 minutes: 7 artifacts,
> **51 knowledge chunks**, 5 `derives` edges, **0 gates**, `cost_usd` 1.19 (display-only — phases
> run on the subscription). Third live run of the session; the first two were aborted for setup
> reasons and cleaned up. Every Step-4 finding is fixed except **S4-8** (companion logging),
> **S4-10** / **S4-11** (team decisions), **S4-25** (`ended_at`) and **S4-26** (missing-flag
> pre-flight) — none of which blocks the journey. Full detail in `Bugs-fix.md`.
> **Next: Step 5 — the gap report, now genuinely unblocked.**

### Step 4 findings register (live session 2026-07-31) — full detail in `Bugs-fix.md`

One row per finding, ready to lift into the tracking spreadsheet. **Severity**: P1 = blocks the journey · P2 = wrong/confusing behaviour the user sees · P3 = debt, observability or a decision to take.

| ID | Title | Area | Severity | Root cause (one line) | Status |
|----|-------|------|----------|------------------------|--------|
| S4-1 | Onboarding agent opened a gate nobody could action | Backend · gates | P1 | `trigger_onboarding_agent` never passed `auto_approve`, so a gate opened on a carrier hidden from every list | ✅ FIXED (verified live) |
| S4-2 | Carrier runs leaked into Phases & Runs + dashboard | Backend · API | P2 | `RunViewSet` and the dashboard rollup filter by project with no carrier exclusion | ✅ FIXED (verified live) |
| S4-3 | No "running" state — a 25-min run looked like a dead click | Backend · API | P1 | `onboarding_hub.index` had only `indexed`/`not_started` | ✅ FIXED (verified live) |
| S4-4 | Progress message never cleared | Frontend | P2 | UI rendered from the mutation result, which never resets | ✅ FIXED |
| S4-5 | Message rendered nothing while the button worked | Backend · API | P2 | payload sent `status` but omitted the `running` boolean the shared component reads | ✅ FIXED (verified live) |
| S4-6 | Copy leaked `00c` and pointed at an invisible screen | Frontend · copy | P2 | internal agent key in user text + a link to a screen that structurally cannot show the run | ✅ FIXED |
| S4-7 | Repo-scoped runs: local tools un-denied but never allow-listed (00c AND 10_security) | Engine · driver | P2 | scan path stops *denying* Read/Glob/Grep/Bash but never *allow-lists* them | ✅ FIX KEPT — **but this was NOT the cause of the hangs** (the run-1 transcript shows `Bash` returning normally *before* the fix existed). Real cause = S4-13. Genuine latent inconsistency, so the change stands |
| S4-8 | Companion reports nothing while a run is in progress | Companion · logging | P3 | no INFO logging of claim / phase start / tool calls | 🔲 OPEN |
| S4-9 | 7 tests assert behaviour `b97f804` deliberately changed | Tests | P3 | artifact creation moved upload → adopt; tests never updated | 🔲 OPEN (**blocks merge**) |
| S4-10 | Connect Machine silently kills the running companion | Backend · enrollment | P3 | visiting the page mints a new enrollment and revokes the live one; token is unrecoverable | 🔲 OPEN (decision) |
| S4-11 | Humans and agents see different projects | Backend · registry | P3 | run-record exclusion applied in `ArtifactViewSet` only, not in the agent-facing `list_artifacts` | 🔲 OPEN (decision) |
| S4-12 | **`00c` agent body ≠ the tools the platform gives it** | **Agent migration** | P2 | §8 reference-sweep miss: `index(workspace=…)` and `get_dependency_path(from=…)` name signatures that don't exist; a required "index into the Knowledge Index" step has **no tool**; the completion text still promises a review gate that `auto_approve` removed | ✅ FIXED — all four (c became S4-18). **Re-sweep of the other migrated agents still owed** |
| S4-13 | **THE HANG — git inherited the MCP server's JSON-RPC channel** | Companion · CodeIntel | **P1** | `capture_output=True` redirects stdout/stderr only, so git inherited the stdio MCP server's stdin — *which is the protocol pipe* — and blocked on it, leaving the server no line to answer on. Observed: git alive 369 s at **0 s CPU**, parent gone; engine reported "no response for 1800s" | ✅ FIXED (verified live — run `98ab9a8c` completed) |
| S4-14 | CodeIntel MCP server launched without an environment | Companion · daemon | **P1** | started with 3 hand-built env vars, so no `PATH` → git invisible → `commits: 0` reported as "no history" rather than an error | ✅ FIXED (verified live — `commits 0 → 22`) |
| S4-15 | Agent delegated its own work to a queue nothing runs | Engine · driver | P2 | background tools (`TaskCreate`, Cron*, Monitor…) reachable from a headless run | ✅ FIXED |
| S4-16 | `add_trace_edge` undiscoverable; caller error returned HTTP 500 | Platform-state · MCP | P2 | valid rels existed only in the model enum — not in the signature, docstring or error; and only `TypeError` mapped to 400. Agent guessed **9** values, then used one (`implements`) for **every** edge | ✅ FIXED (tests green) |
| S4-17 | `search_codebase` matched substrings, and only file names | CodeIntel · search | P2 | `low.count(term)` over paths only: `'CI CD'` matched `dependen**ci**es.py`; `'authentication JWT'` found nothing in a repo that authenticates. Never errored — answered wrongly | ✅ FIXED (tests green) |
| S4-18 | **Knowledge Index never populated — 0 chunks for 7 artifacts** | Platform-state · knowledge | **P1** | agent bodies order "index each artifact into the Knowledge Index"; **no such tool exists**. Every later phase would re-read the codebase instead of retrieving Step 4's work | ✅ FIXED — platform now indexes on `register_artifact`; **fixes retrieval for every phase** (tests green) |
| S4-19 | 10 languages only; CI/config files invisible; unknown reported as zero | CodeIntel · collection | **P1** | one extension filter gates `file_meta`, the only node set every layer reads. A C#/PHP/Swift repo indexes as 0 files while git still reports thousands of commits and **0 hotspots** — the shape of a healthy codebase. Config/CI files carry non-code extensions, so "CI/CD presence" and "tech stack" were unanswerable | ✅ FIXED (tests green) |
| S4-20 | Any git failure indistinguishable from "this repo has no history" | CodeIntel · git | P2 | `_git` collapsed timeout / missing binary / empty repo to `""` → all counters 0 → **hotspot ranking silently empty** while `file_count` stays healthy, so the agent's own "index is non-empty" check passes | ✅ FIXED (tests green) |
| S4-21 | Companion died on a transient 5xx from the platform | Companion · daemon | P2 | shared Postgres dropped one connection → `/api/runner/work/` 500 → `DaemonError` escaped the serve loop (which caught only OSError) → companion exited. Symptom: a button that silently stops working | ✅ FIXED (tests green) |
| S4-22 | A leaking test made a passing test look broken | Tests | P3 | `--headed` wrote to the real `os.environ`; `monkeypatch.delenv` on an absent var records nothing to restore, so the flag leaked session-wide | ✅ FIXED |
| S4-23 | **The dependency graph invented edges that do not exist in the code** | CodeIntel · graph | **P1** | `resolve()` matched an import to a file **by bare name, across the whole repo, in any language**, with no stdlib / third-party / language check. `import logging` wired 6 files to `middleware/logging.py`; `import types` and `from starlette.types` wired two Python files to `frontend/src/api/types.ts`. **8 of 127 edges false**; the fake cross-tier links merged the backend and frontend into one architecture community | ✅ FIXED — **verified live** (`9d1b4d32`): 119 edges, 0 cross-language, communities 2 → 3 |
| S4-24 | Agent forwarded an unverified anomaly to the user instead of resolving it | **Agent migration** | P2 | `00c` reported a structurally impossible import as a finding and asked the reader to check it — while holding `Read`/`Grep` over the worktree. Its body mentioned `ask_human` **zero times** in 152 lines, so the clarification channel was wired but unreachable from the instructions, and the only route offered for an odd result was "record an assumption" | ✅ FIXED — **verified live** for self-verify; **`ask_human` branch untested** (no run has needed it) |
| S4-25 | A completed run never records when it ended | Backend · runs | P3 | `ended_at` stays NULL on the success path (`9d1b4d32`, `98ab9a8c`, `bf0f27c0`, every completed `00e`), while **failed** runs do set it — so no screen can show a run's duration and run-time regressions cannot be measured | 🔲 OPEN |
| S4-26 | A companion started without `--repo-path`/`--worktrees` analyses nothing, and says so only in a log nobody reads | Companion · daemon | P2 | `daemon.py` logs *"has no worktree … scanning manifest only"* and **continues**: no worktree, no `codeintel` MCP server, no source — yet the run completes and would publish confident artifacts about a codebase it never opened. Cost one aborted run this session. Prerequisite #4 below already requires the flags; nothing enforces them | 🔲 OPEN — **pre-flight**: after clicking, a `codeintel_mcp` process and a `.sdlc-worktrees/scan-<run-id>` directory must both exist |

**Cross-reference (platform-wide, team-owned, not brownfield):** re-running any phase produces **v1 + v2** instead of replacing, leaving phantom gates, stranded clarifications, unreclaimed S3 bodies and orphan trace edges. Full blast-radius recon delivered 2026-07-31; spans greenfield *and* brownfield because the defect is in the shared `register_artifact`.

## Step 5 — Gap report → **`00_onboarding` agent** (or deterministic fallback)

| # | Step | What to verify | Path | Delivered by | Status |
|---|------|----------------|------|--------------|--------|
| S5.1 | Trigger "Run gap report" | Dispatches; correct mode banner (**agent** vs **deterministic**). | both | Slice 5/6 | ✅ **DONE (live)** — 202 agent dispatch confirmed; mode is now named on the hub |
| S5.1b | ~~**Headless** + progress UX~~ → **GATED + progress UX** (team decision, **2026-08-03**, supersedes 2026-07-31) | The gap report is **not** treated like Index code. Index code stays headless — it is a mechanical index. The gap report is a **judgement about the client's project** that the pipeline acts on, so a **Product Owner gate** owns it and approval is what publishes the report. It still hides from Phases & Runs and the dashboard and still shares `AgentStepStatus`, which gains a third state: **"Waiting for your approval"** linking to the gate (`gap.approval_id`) — without it `awaiting_gate` reads as "still working" forever. No new gate surface was needed: only the backlog and Phases & Runs hide carriers; `ApprovalViewSet` and the dashboard do not. | agent | S5-4/S5-5 · S5-8 | ✅ **DONE (live)** — gate opened, was reachable, approved by product_owner, and approval published the report |
| S5.2 | Agent reasons, calls `submit_gap_report` | `00_onboarding` assesses each phase Complete/Partial/Missing and **calls `submit_gap_report`** — it does **not** dump the assessment into a document (the ideation-class prompt-adherence risk). | agent | Slice 5 (agent body + tool) | ✅ **DONE (live)** — run `448b8d21` called it, and registered no document instead. The pre-flight audit found the body **never named the tool** and told the agent the opposite (**S5-1**). Body rewritten around a single call; a runtime backstop (`_PHASE_REQUIRED_ARTIFACTS["onboarding"]`) now fails the run loudly if the call is skipped |
| S5.2b | **Assess-only remit** (team decision, 2026-08-03 — option c) | `00_onboarding` registers **no lifecycle content**: it judges the evidence and submits the report. `assumption` artifacts are the one exception. Transformation belongs to the phase agents, each already gated. | agent | S5-4/S5-5 | ✅ **DONE (live)** — the run registered exactly `gap_report` + `assumption` + the phase blob. Zero lifecycle content |
| S5.3 | Contract guaranteed | Whatever the agent emits, the stored `external_ref` has the exact shape `{source, resume_phase, phases:[{phase,label,status,evidence}], blockers, intel_present}` — the shared `write_gap_report_artifact` normalizes it. UI/`types.ts` unchanged. | agent | Slice 5 (shared writer) | ✅ **DONE (live)** — run `448b8d21`'s `external_ref` parsed by `read_gap_report` + both screens |
| S5.4 | Gap report is accurate | With real adopted docs + code intel, the report reflects reality — **not** "all Missing, resume at ideation." Resume point matches the evidence. | both | B5-1 (redesign) | ✅ **DONE (live)** — run `448b8d21` read the real evidence: ten phases Complete, resume at Implementation. **Not** "all Missing, resume at ideation". **A second accuracy defect was fixed before it could bite (S5-27) was found and fixed before it could bite (S5-27): onboarding's own carrier work items are `epic`s, so Task Breakdown read Complete on any project that had ever run an onboarding step.** Still to verify on a project with NO real backlog: the report must say **resume at task_breakdown**, not implementation. This project has 68 genuine backlog items, so it reads Complete either way |
| S5.4b | Phases ahead of the resume point read as "not started" | A team that finished only Ideation..UX Design must not see six ✗ Missing rows reading as six failures (**S5-28**). | both | S5-28 | ✅ FIXED (tests green) — this run had no phases past the resume point, so it did not render |
| S5.5 | Deterministic fallback | No companion → `build_gap_report` writes the **byte-identical** `external_ref` via the same shared writer. | fallback | Slice 5 | ✅ DONE (tests green) — same shared writer; no companion-less run has been exercised live |
| S5.6 | Hub refreshes in place | Running the report flips the hub's Resume step without a manual reload (both query keys invalidated). | both | B5-2 + Slice 6 | ✅ **DONE (live)** — the hub flipped to "Ready — resume at Implementation" without a reload |

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
- **S3-6 · 🔴 NEW BLOCKER: a linked Confluence page's content never reaches the agents.** Typing it fixed *classification*; the body was never carried. Proven live: agent reads **0 chars** where an uploaded doc of the same type reads 84,896. See *Step 3 live bring-up* for root cause, the recommended fix, and the two design options awaiting a team decision.
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

#### Pre-flight audit, 2026-08-03 — 20 findings, read BEFORE the first run
Full detail in `Bugs-fix.md` ("Step 5 — Gap report"). The five that made the run impossible or wrong:
- **S5-1 · 🔴 The agent was never told to call `submit_gap_report`** — the body instructed the opposite. — **✅ fixed** (body + a runtime backstop).
- **S5-2 · 🔴 The body described a runtime that does not exist** (worktree / `codeintel.*` / file tools, all denied). — **✅ fixed by correcting the BODY, not the flag**: 00c is the single source of code facts and is now a stated prerequisite.
- **S5-3 · 🔴 A perfect run would have been marked FAILED** — the report was registered unbound to its run. — **✅ fixed** (`run_id` threaded through; this is also what lets the gate publish it).
- **S5-4/S5-5 · 🔴 The gate was inverted** — the report never published, while agent-registered lifecycle content auto-published unreviewed (#5). — **✅ resolved by the option-(c) + gate decision**.
- **S5-27 · 🔴 Onboarding's own carriers faked a backlog**, flipping "resume at Task Breakdown" into "resume at Implementation". Found by the team's UX-Design scenario question. — **✅ fixed** (`carrier_q()` exclusion in the assessor *and* in `list_work_items`).

Plus **S5-6** (the screen crashed on any real report), **S5-7** (raw slugs), **S5-8** (a re-run was
silent), **S5-28**, **S5-15** (the tests were locking three bugs in), **S5-18** (stale hub tests),
**S5-10/12/13/14** (the §8 sweep this agent never got), **S5-11** (intelligence artifacts not
guaranteed in context).

**Second pass (team: "fix everything, including the deferred") — all closed:** **S5-9** (mode now
named), **S5-19** (blockers are actionable; Implementation/Code Review correctly route to *Index
code*, not to a phase agent), **S5-20** (evidence validated) and **S5-20b** — 🔴 *found by the new
end-to-end test, not by review*: **one invented artifact id destroyed the entire report**, because
a non-UUID raised out of `add_trace_edge` before any lookup. **S5-21** (project-id fallback),
**S5-22** (dead branch removed, not switched on — see the note), **S5-23** (`code` → the artifact
actually measured), **S5-24** (replayed answers flagged as possibly stale), **S5-25** (a truncated
run no longer reports as a clean success), **S5-26** (`ended_at` stamped on success — this also
closes **S4-25**). Also the stale `daemon.py:341` comment, the **409** test and the **full MCP
chain** test.

**Nothing from the Step-5 audit remains open.**

#### LIVE RESULT — run `448b8d21` (2026-08-03): **STEP 5 IS GREEN** ✅
Ran end to end on the team's companion and was approved. **completed** · 23.5 min · gate
`fd18a0a1` approved by product_owner · `gap_report` **published on approval** · `assumption` +
the phase blob and **nothing else** (option (c) holding) · 15 resolved trace edges ·
**`ended_at` stamped** — the first successful run in this system ever to record when it finished.
Verdict: **resume at Implementation**, ten phases Complete, Implementation + Code Review *Partial*,
no blockers. The agent reasoned rather than counted rows: the deterministic path would have said
"Code Review missing".

**Four defects that only the live run found — three caused by the gate change**, because flipping
`auto_approve` off broke assumptions that held only while every carrier run was headless:
- **S5-29 · 🔴 the gate was INVISIBLE** — badge said 1, the Gates page said "No gates need you". The
  screen kept only approvals whose work item was in the work-item list, **which hides carriers**. I
  had checked the API had no carrier filter and never checked what the client did with the response.
- **S5-30 · 🟠** phase artifact titled "Onboarding — Onboarding — project assessment".
- **S5-31 · 🟠** the gap report registered with an empty title.
- **S5-32 · 🟡** the resume card clipped "Open the report document" mid-word (no `flex-wrap`).

All four fixed with regression tests; **S5-30/31/32 not yet seen live** (they were not in the
containers during this run). Full status board — fixed-live vs tests-green vs open vs to-be-done —
in `Bugs-fix.md`.

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

---

# Step 3 live bring-up — connectors (2026-07-29)

Tested live against the team's real Atlassian Cloud site (Jira + Confluence connected, both
probing healthy). Figma untested — no account yet.

> **STATE: connect + import are GREEN. Linking a Confluence doc is NOT — see S3-6, the blocker.**

## Fixed this session

- **S3-1 · 🔴 The Confluence page-link box was crushed to an unusable sliver.** The paste box
  rendered ~30 px wide, so there was visibly nowhere to put the page link the instruction asked
  for. **Root cause:** `.input` and `.select` both carry `width: 100%` (`components.css`). In that
  flex row the input asked for `flex: 1` — *start from zero and grow* — while the type dropdown
  carried no flex rule at all and kept its full width, claiming the entire row. There was no free
  space left to grow into. The box was never broken; the dropdown ate it. Fix: dropdown pinned to
  a fixed 200 px track, input takes the remainder with `minWidth: 0`.
  — **✅ fixed** · verified live: input **30 px → 574 px**.

- **S3-2 · 🟠 The connect form expanded inline and rearranged the checklist.** Opening it pushed
  every step below it down the page and snapped them back on close, so connecting a tool visually
  reshuffled the page around it. Fix: the embedded form is now a centred **modal over a scrim**
  (the `Modal` component already existed), bringing scrim-click / Esc / ✕ dismissal with it.
  — **✅ fixed** · verified live: page height **1313 px before opening and after** — nothing moves.

- **S3-3 · 🟠 A linked Confluence page registered with a blank title.** The page title was written
  into `external_ref` but never onto the artifact's own `title` column — the one every UI surface
  renders and the field the platform uses to tell sibling artifacts of one type apart. A linked
  page listed as an empty row. Fix: title carried onto the artifact; re-linking repairs rows
  registered before the fix. — **✅ fixed** · verified live.

- **S3-4 · 🟠 "Test the connection to verify it" was unreachable.** Saving set that banner and
  closed the modal in the same tick, so the instruction was destroyed before it could be read and
  nobody ever tested a connection they had just entered. Fix: the modal stays open after save and
  the user closes it ("Cancel" becomes **"Done"**). Found while fixing it: a failed test *replaced*
  the form with the error, so the one screen telling you the token was wrong was also the screen
  where you could not retype it — outcome banners now sit **above** a form that stays put.
  — **✅ fixed** · verified live, including the failed-test path.

- **S3-5 · ⚪ "Ideation (Ideation)", "PRD (PRD)".** The `(Phase)` suffix exists to disambiguate —
  "ADR (Architecture)" earns it — but where the type *is* its own phase it disambiguates nothing
  and reads as a bug. Fix: suffix dropped only in that case, in the backend (source of truth) and
  the frontend fallback together. — **✅ fixed** · verified live: 0 redundant labels remain.

- **S3-M · misdiagnosis, reverted not shipped.** A linked page's URL pointed at
  `/spaces/SDLC/overview` rather than the page, and a "fix" plus a speculative draft-page guard
  were written before checking: the page is `status: current` with a 2115-char body — it is the
  **space homepage**, whose canonical URL legitimately *is* the space overview. Nothing was broken;
  the change rewrote a correct URL into a legacy one. Both reverted. Recorded because the pattern
  matters: only the finding that was *demonstrated* survived.

## Verified working

- **Jira import** — 13 real issues imported as work items; button flips to "Re-import backlog".
  Issues arrive as `WorkItem` at state `ACCEPTED` with `external_ref={"sor":"jira", …}`.
  **No adopt step needed, and that is correct**: adopt exists to answer *"what kind of document is
  this?"*, and a Jira issue already declares its own type.
- **Confluence link** — accepts a bare page ID *or* a pasted URL; idempotent by page id.
- **Live credential probe** — a deliberately wrong token is correctly rejected with a plain-English
  reason, and the connection test reaches Atlassian for real.

---

# S3-6 · 🔴 BLOCKER — a linked Confluence document is invisible to the agents — **✅ FIXED**

> **RESOLVED 2026-07-29, verified live** on a real 141,273-char Requirements page (97 tables, one
> attached system-context PNG). Agent-readable body went **0 → 37,192 chars**; the diagram was
> transcribed into structured text; three re-links produced **one** document; adopting produced
> **one artifact at v1, published**. The fix and the two design decisions behind it are below.

**A linked page is registered, counted as evidence, and marked complete — while every agent that
opens it reads an empty string.**

## Evidence

A real page linked, then read back through the exact call an agent makes:

```
artifact: type=prd  status=published  s3_key=''  content_hash=''

=== WHAT AN AGENT GETS FROM get_artifact_body ===
body length: 0
body: ''
```

Beside an uploaded-and-adopted document of the same type in the same project:

| | Uploaded + adopted | Linked from Confluence |
|---|---|---|
| Agent reads | **84,896 chars** of real PRD text | **0 chars** |
| `s3_key` | set | empty |
| `content_hash` | set | empty |

## Root cause

A live read-through for Confluence **exists and works** — `_read_confluence` (`preview.py`). It is
wired into exactly one caller: `read_artifact_preview`, the **human** preview panel. The agent path,
`artifact_body_for_agent`, falls through to `_read_internal`, which looks for an S3 body, an inline
`external_ref.body`, or a run output. A linked page has none of the three, so it returns `""`.

**The human sees the page. The agents see nothing.**

## Why it is a blocker and not a cosmetic gap

`build_gap_report` counts evidence **by type, never by content**:

```python
by_type.setdefault(a.type, []).append(a)
```

So a linked Confluence PRD marks the PRD phase **complete** and moves the resume point past it —
on the strength of a document no agent can read. The lifecycle then resumes at a later phase
believing requirements are covered, and the downstream agent receives an empty string.

Same failure shape as the vision defects: **silent, and confidently wrong.** No error, no warning.

> **Honesty about the evidence:** the empty body is proven through the exact tool call an agent
> makes. The downstream consequence — a phase resuming on empty evidence — is reasoned from the
> code, **not yet observed in a live run**. Worth confirming that way once fixed.

## Two further gaps in the same area

- **S3-7 · 🟠 No vision on linked pages.** Confluence carries diagrams as **attachments**
  (`<ac:image><ri:attachment/>`), not as `<img src>`. The existing HTML extractor only understands
  `<img>`, and the connector has **no attachment support at all** (`get_page`, `create_page`,
  `update_page`, `search`, `delete_page` — nothing else). So a linked architecture page's diagrams
  are dropped exactly the way uploaded PDFs' diagrams were before Part B. The attachments REST
  endpoint was confirmed reachable on the team's site, so this is buildable, not blocked.

- **S3-8 · 🟠 Confluence storage format is not HTML, and reusing the HTML extractor leaks macro
  internals.** Running a real page through the existing extractor produced real content *mixed
  with* machine noise:

  ```
  ## Description
  #F4F5F7                                              ← a background-colour parameter
  In a sentence or two, describe the purpose of this space.
  ## Project Tracker
  com.atlassian.confluence.project-linker … 3781a39a-…  ← macro internals
  page,whiteboard,database,blog 10 concise true         ← macro parameters
  ```

  The team's four pages carry 0, 3, 5 and 8 `<ac:structured-macro>` elements, so this is typical,
  not an edge case. A Confluence-aware pass (unwrap `ac:rich-text-body`, drop `ac:parameter`) is
  needed, or agents read colour codes as requirements.

---

# The fix as built — a linked page is a first-class document (**✅ shipped**)

**Requirement (team, 2026-07-29): linking a Confluence doc must run the same end-to-end adoption as
an upload in Step 2, with the same clear messages, including the vision pass.**

The one-branch patch (`artifact_body_for_agent` branching on `sor == "confluence"`) fixes the empty
body **only**. It does not give the page a version, a diagram read, a fidelity badge, or drift
detection. It is not enough for the requirement above.

The structural fix is to route a linked page into the **pipeline that already exists**: create a
`SourceDocument` for it, so everything downstream — adopt, artifact-at-v1, vision, the content-loss
guard, the honest status badges, retry — works unchanged, because none of it is upload-specific.
`SourceDocument` is origin-agnostic today except that `s3_key` assumes an uploaded file.

Work required:

1. **Connector — attachments.** `list_attachments(page_ref)` + `download_attachment(id)` on the
   Atlassian docstore. (Endpoint confirmed live.) — *new*
2. **A Confluence-aware body pass.** Storage XHTML → clean markdown, unwrapping macro rich-text and
   discarding macro parameters (S3-8). — *new*
3. **`ingest_confluence_page`** — the sibling of `ingest_source_document`: fetch page, convert body,
   download attachments as `page_images`, create the `SourceDocument` with the same provenance
   shape (`fidelity`, `page_count`, `extracted_s3_key`, `extracted_hash`, `artifact_type`). — *new*
4. **Adopt + vision** — *no change*. Both already key off the `SourceDocument`.
5. **UI** — linked pages appear in the same documents list with the same badges and messages.

Steps 4 and 5 are close to free, which is the argument for this shape over the one-branch patch.

## ✅ Team decision — TWO STEPS (option B), taken 2026-07-29

Uploads are deliberately **two steps** — upload, look at what was extracted, *then* adopt with a
type — because nobody can classify a file before seeing inside it. Linking already asks for the type
**up front**, in the dropdown beside the paste box. So which does "just like Step 2" mean?

- **Option A — one step.** Link (with type) → ingest, adopt, run vision immediately. Fewest clicks;
  the existing type dropdown is kept and does the classifying.
- **Option B — two steps.** Link → the page appears in the documents list as *extracted, awaiting
  adopt* → the user reviews what was pulled in and adopts it there. Literally identical to Step 2;
  the user sees the extraction (and any macro noise) **before** committing. The link-row type
  dropdown becomes redundant and should be removed, or it asks the same question twice.

**Recommendation: Option B.** The review beat is the whole point of adopt, and it is worth more for
Confluence than for uploads — a Confluence page's extraction is *less* predictable than a PDF's
(macros, attachments, templates), so seeing it before it becomes project evidence catches exactly
the class of problem S3-8 describes. It also means one adopt path and one set of messages, rather
than a second flow to keep in step.

---

# Design decision — snapshot at link time vs live read at agent time

The question underneath both options: when a linked page's content is needed, do we **store a copy
at link time** or **fetch it live from Confluence each time**?

| | **A · Snapshot at link time** | **B · Live read at agent time** |
|---|---|---|
| **How** | Fetch once, store the body in S3 like an upload | Fetch from Confluence on every agent read |
| **Content is** | Fixed at the moment you linked it | Always current |
| **If Confluence is down / token expires** | Runs continue — the copy is local | **Runs fail mid-flight**, and the read is best-effort so it may fail *silently* to `""` — the current bug's exact shape |
| **Reproducibility** | A re-run reads what the first run read | Two runs of the same phase can read different text |
| **Versioning** | v1, v2… like uploads; diffs visible | No versions — nothing to diff |
| **Vision** | Works: pages exist as stored images | Blocked: nothing durable to attach renders to |
| **Content-loss guard** | Works: there is a baseline to compare against | **Cannot work** — no prior version exists |
| **Drift** | Detectable (stored hash vs live page) — you can *tell the user* the page changed | Invisible: content silently changes underfoot |
| **Staleness** | Real. Needs a re-link / refresh to pick up edits | None |
| **Rate limits** | One fetch per link | Every agent read hits Atlassian |
| **Blueprint rule 1** *(platform owns state, tools own content)* | Consistent — the same pointer + S3 draft pattern uploads already use | Also consistent |
| **Effort** | Moderate — reuses the whole upload pipeline | Small for text, but **cannot deliver the team's vision requirement** |

**Recommendation: A — snapshot at link time.**

Three reasons, in order of weight:

1. **B cannot satisfy the requirement the team just set.** Vision needs durable page images to
   transcribe, and the content-loss guard needs a prior version to measure against. Live reading
   provides neither. Choosing B means dropping vision for Confluence.
2. **B makes runs depend on Atlassian being up at the moment an agent reads.** A token expiring
   mid-lifecycle turns into a phase built on an empty document — and because the read-through is
   best-effort, it degrades to `""` rather than raising. That is the bug this section documents,
   re-introduced by design.
3. **A makes a linked page behave *identically* to an uploaded one.** Same versioning, same badges,
   same guard, same retry, same messages — one pipeline to reason about and to maintain.

**The honest cost of A: staleness.** Someone edits the Confluence page and the platform keeps
reading the version you linked. The mitigation is what a snapshot uniquely makes possible — you
have a stored hash, so the platform can **compare it against the live page and tell the user the
source has changed since they linked it**, offering a re-link. Drift detection already exists
(`detect_drift`). Under B this problem does not exist, but neither does any way to notice it: the
content just changes underneath the project with nobody informed.

**Hybrid, if the team wants both:** snapshot for content (so vision, versioning and the guard all
work) **plus** a periodic or on-demand drift check against the live page. That is strictly A with a
freshness signal added, and is the recommendation if staleness is the main worry.

> ## ✅ TEAM DECISION — 2026-07-29
>
> **Content: SNAPSHOT at link time** (option A). **Flow: TWO STEPS** (option B) — link → the page
> appears in the documents list awaiting adopt → the user reviews the extraction → adopts.
>
> **The hybrid is explicitly held in reserve:** the team agreed to snapshot now and *"if needed we
> can shift to hybrid"* — snapshot plus a drift check against the live page. Nothing in the
> snapshot design forecloses it; the stored `content_hash` is precisely what a later drift check
> would compare against, so adding it is additive, not a rewrite. Revisit when staleness is
> observed in real use rather than anticipated.

## S3-7 / S3-8 — closed with S3-6

- **S3-7 · 🟠 No vision on linked pages — ✅ fixed.** The Atlassian docstore gained
  `list_attachments` (followed to the end of Confluence's paging, so a page never reports only its
  first images) and `download_attachment`. That needed the SHARED transport to stop assuming every
  response is JSON — it now falls back to raw bytes, which is strictly additive (anything that
  parsed as JSON still does) and was regression-checked against Jira and Confluence. Verified live:
  a 383,205-byte PNG downloaded intact and opened as a 2720×2240 image.

- **S3-8 · 🟠 Storage format leaked macro internals — ✅ fixed.** New module
  `integrations/confluence_body.py` converts Confluence storage XHTML to markdown. Three
  judgements worth keeping in mind when editing it:
  1. **A macro parameter is not automatically noise.** `<ac:parameter ac:name="title">Not started`
     on a `status` macro is that cell's whole content; `colour` beside it is presentation. Filtered
     by NAME, not dropped wholesale.
  2. **Some macros hold no content at all** (`recently-updated`, `project-linker`, …) — they render
     server-side, so storage holds only their configuration. Dropped entire.
  3. **`ac:placeholder` is dropped on purpose.** It is the grey hint text an empty template shows
     ("Add action items to close the loop…"), addressed to a human author. An agent ingesting it
     reads instructions-to-the-writer as requirements. Consequence, and it is the honest one: an
     unfilled template now comes back **empty**, and the existing `fidelity: empty` path says so.

  Two bugs here were only exposed by a REAL page, never by the four Confluence templates:
  the page had **zero `<h1>/<h2>/<h3>` and 140 `<strong>`** (its author wrote headings as bold, so
  dropping emphasis flattened the document), and its tables used `<td>` for header rows with no
  `<th>` anywhere (so the renderer emitted an empty header and pushed "Version | Date | Author"
  into the body). Both fixed. Known cosmetic residue: **2 of 140 bold runs** render with a stray
  space inside the markers; the text is intact, so nothing an agent reads is affected.

## S3-9 · 🔴 Runs execute on other developers' machines — INFRASTRUCTURE, not code

Every developer's Temporal worker polls the **same** task queue (`sdlc-planning` on a shared
remote Temporal). A workflow's steps are therefore handed to whichever worker is free — including
one running a **different branch's code**.

Caught directly: one vision run's history listed **three** worker identities, only one of which was
this machine. A step ran on a worker predating the auto-apply branch, so the run **opened a review
gate** instead of publishing — for a phase that is deliberately gate-free. Four identical runs
earlier the same day had auto-published correctly.

**Why it matters beyond the one run:** it is non-deterministic and silent. The same code passes or
fails depending on which machine picks up the job, which means a green test proves less than it
appears to. Proven by isolation: same document and same code, the run on the shared queue gated;
the run on a private queue published at v1.

**Not fixed in code** — the queue name is already environment-driven (`TEMPORAL_TASK_QUEUE`), so a
per-developer queue needs no change here, and `.env` is gitignored. Team decision (2026-07-29): the
shared queue is only dangerous while people run different code, so it is left as-is and owned by
the team going forward. Worth re-reading this entry the next time a workflow behaves differently
between two runs of the same code.


## S3-10 · 🔴 "Bring in documents" always failed — three bugs in one paste-a-link path — **✅ FIXED**

Found on the team's first live run of the rebuilt Step 3 (2026-07-30). Pasting two Confluence
links and pressing **Bring in documents** produced, verbatim on screen:

```
{"links":[{"type":["This field is required."]},{"type":["This field is required."]}]}
```

Three separate defects sat behind that one line. They are recorded together because fixing only
the first would have replaced the error with a different dead end.

### 1. The API still demanded a type the form no longer sends

S3-6 moved classification to the ADOPT step: a linked page is a source document first, and its
lifecycle type is declared when the human adopts it, exactly as for an uploaded file. The form
stopped sending `type` and `link_confluence_pages` was updated to default a missing type to
`document` — but `_ConfluenceLinkSerializer.type` stayed `required=True`, so DRF rejected the
request before the service that handles its absence ever ran.

**Root cause:** a contract change applied at both ends of the call and not in the validator in the
middle. **Fix:** `type = CharField(required=False, allow_blank=True)`. `page` stays required.

### 2. The pasted links were "tiny" links, which the parser could not read

Both boxes held `https://<site>/wiki/x/AYAxAQ`. That short form is what the **Copy link** button
hands you in the current Confluence editor, so it is the link a user is *most* likely to paste —
and `_parse_confluence_page_id` understood only `/pages/<numeric-id>/…`, `?pageId=`, and a bare
id. After fix 1 alone, every one of these links would have failed with "couldn't find that page".

**Root cause:** the parser was written against the URL shape you get from the browser address bar,
not the one the product's own share button produces. The earlier note in that docstring — that
tiny links "can't be resolved offline" — was simply wrong.

**Fix:** they decode locally, no extra API call. The code is base64 of the page id as
little-endian bytes with `=` padding dropped: `AYAkAQ` → `01 80 24 01` → **19169281**, which is
the same Requirements page the S3-6 fix was verified against. Confluence swaps `/`→`-` and
`+`→`_`, the opposite of Python's urlsafe alphabet, so both mappings are attempted; a code
containing neither character — the common case — decodes identically either way.

### 3. Raw JSON was shown to the user as an error message

Not specific to this form. `api.ts` built every failure message as `data.detail ||
JSON.stringify(data)`, so any DRF validation error anywhere in the app reached the screen as a
literal JSON blob — unreadable, unactionable, and indistinguishable from a crash.

**Fix:** one shared `humanizeError` walks the nested shape and keeps the leaf strings, which are
the only part written for a human, prefixed by field name where one exists (`This field is
required` alone doesn't say *which* field). Array indices are dropped — "1" names nothing on
screen. Duplicates collapse, so two rows failing the same way say it once. Applied at both error
sites, which fixes every screen, not just this one.

### Verified

- Serializer: a row with no `type` validates; with a `type` still validates; a row with no `page`
  still fails. Parser: tiny link → `19169281` (matches the known real page), plus `/pages/<id>/`,
  `?pageId=`, and bare-id forms all unchanged, and unparseable input still returns `None`.
- `humanizeError` on the exact failing body returns `type: This field is required.`; on
  `{"detail": …}`, on `non_field_errors`, and on an empty/absent body it returns the sentence or
  the HTTP fallback.
- Frontend typechecks clean; vite is serving the new code.


## S3-11 · 🟡 A linked Confluence page read as "File · 1 page captured" — **✅ FIXED**

Two labels, two different mistakes, on the same row.

- **"File"** — every branch of `fileKindLabel` tests a file EXTENSION, and a Confluence page has
  none, so it fell through to the bare fallback. Now returns **"Confluence page"**, checked FIRST:
  a page TITLE can look like it has an extension ("Release 1.2" → ext `2`).
- **"1 page captured"** — `page_count` means two different things. For an upload it is how many
  pages of the file were rendered as images. For a linked page there is exactly one page and the
  count is its ATTACHED images, so the row told the user a one-page document has one page. Now
  **"1 attached image"**.

Discriminator is the mime the backend already stamps (`text/confluence-storage`) via a single
`isConfluencePage()` helper — no API change. Team considered "Confluence page/file"; kept the
single noun, since the flow only ever accepts page links and the sibling rows say "PDF"/"Word".
Revisit if linking Confluence ATTACHMENTS is ever added, where the row really could be either.

## S3-12 · 🟠 Gates badge said 1, the Gates page said "Pending (0)" — **✅ CLOSED BY S3-13**

Logged as its own defect, then proved to be a symptom. First diagnosis (the gate's `required_role`
being one the user doesn't hold) was WRONG — role never enters the filter. The Gates screen keeps
only approvals whose work item appears in the work-items list, and S3-13 had emptied that list
entirely. Fixing S3-13 fixed this. **Consequence worth remembering:** the badge pointed at a
screen that could never show the gate, so a legitimately-opened gate would have been unreachable
through the UI — nobody could approve it and the document would sit half-published forever.
Re-check this pairing whenever the work-item list gains another filter.

## S3-13 · 🔴 The backlog was empty for EVERY project — **✅ FIXED** (branch-local, never reached develop)

Introduced by me in `d507b99` (2026-07-28) while hiding vision carriers from the backlog:

```python
qs = qs.exclude(external_ref__source__in=CARRIER_SOURCES)     # the bug
```

**Root cause — SQL three-valued logic on a MISSING json key.** A Jira import carries
`{"sor": "jira", "id": "ST-447"}` with no `source` key, so `external_ref -> 'source'` is NULL,
`NULL IN (…)` is NULL, `NOT NULL` is NULL, and the row is dropped. The rule actually written was
"hide any work item that has an `external_ref` without a `source` key". Measured: **32 → 0** on the
brownfield project, **152 → 8** on another (the 8 survivors being rows whose `external_ref` is
column-NULL, which Django's added `IS NOT NULL` guard rescued — the one shape that worked).

**Blast radius:** the work-item list feeds Work Items, Phases & Runs (so nothing could be
triggered), Gates, Clarifications, Task Breakdown and the board. `git branch --contains` confirmed
the line existed ONLY on `brownfield-agent-onboarding` — develop was never affected, but a merge
would have broken every project, greenfield included.

**Fix** — exclude only when the key EXISTS *and* names a carrier:

```python
qs = qs.exclude(Q(external_ref__has_key="source")
                & Q(external_ref__source__in=CARRIER_SOURCES))
```

Verified: brownfield **0 → 25**, greenfield **8 → 152**, 7 carriers still hidden, 0 leaked.

**The test was giving false confidence and was fixed too.** `external_ref` is nullable and the old
test's only real row had a NULL ref — the single shape the broken filter handled correctly — so it
passed while the product's backlog was empty. It now also creates a Jira-shaped row, with a comment
marking the `has_key` guard as load-bearing. **A test that only covers the shape you invented is
not coverage** — this is the lesson worth carrying, not the one-line fix.

## S3-14 · 🟡 "11 documents uploaded" counted pages nobody uploaded — **✅ FIXED**

9 files + 2 linked Confluence pages, all reported as uploads, directly above a step correctly
saying "2 pages linked". `onboarding_hub` now returns `origin` per document ("upload" by default,
"confluence" for a linked page) and the step composes **"9 documents uploaded · 2 pages linked"**.
Additive and defaulted, so a project with no linked pages — every greenfield one — renders exactly
the sentence it did before.

## S3-15 · 🔴 The Jira import silently stopped at 25 issues — **✅ FIXED** (⚠️ ALSO LIVE ON DEVELOP)

`AtlassianTaskTracker.search` sent `maxResults: 25` and read ONE page. Jira returned 25 rows plus a
`nextPageToken` nobody looked at, so the import took the first 25 and reported success.

**Measured on a real project: Jira held 68 issues (14 Epic · 15 Story · 38 Subtask · 1 Task); 25
were imported, all Subtasks.** The cut removed every Epic and every Story — precisely the tier a
user triggers a phase on. What remained was the bottom of a hierarchy whose top never arrived.

> **⚠️ This is NOT branch-local.** `origin/develop` carries the identical line, so any project with
> more than 25 Jira issues has been importing a silent subset. Flagged to the team separately.

Also corrected here: an earlier claim that `_ISSUE_TYPE` failed to recognise the issue types was
**wrong** — all 25 really were `Subtask`, which maps to `task` correctly. The mapping was never the
problem; the cap was.

**Fixed in three parts:**
1. **Page to the end** — follow `nextPageToken`, 100 per request, with a stated `_SEARCH_LIMIT`
   runaway guard. A cap is fine; a cap pretending to be everything is not.
2. **Never report a silent subset** — new `count()` (Jira's approximate-count; returns -1 when Jira
   won't answer, read as "unknown", never as zero) lets the response carry
   `issues_available`/`issues_seen`/`truncated`, and the screen says "Imported N of M" when the cap
   bites. Silent on the happy path, loud only when something was left behind.
3. **Carry the hierarchy** — `get_issue` always returned `parent_ref` and the import discarded it.
   Parents are attached in a SECOND pass after every row exists, so Jira's ordering cannot matter.

**Re-import is now a reconcile, not an append.** It re-reads keys it already holds, so rows
imported before this fix get their parents filled in — verified: the 25 pre-existing rows went from
0 parented to 25 parented without any deletion or re-import from scratch. Parent is only ever set
when currently empty, so a parent edited in the platform is never overwritten by Jira.

**Verified live:** 43 newly registered, 68 total, `available 68 / seen 68 / truncated False`,
types `epic 14 · story 15 · task 39`, 53 parented. The single unparented non-epic (`ST-414`) is a
standalone Jira Task with genuinely no parent. Backlog still shows 68 with 0 carriers leaked.

## Standing note — what "surgical" means on this branch (2026-07-30)

Team instruction: nothing built for brownfield may disturb the **greenfield** journey on merge.
S3-13 is the cautionary tale — a change aimed at a brownfield-only surface (hiding vision carriers)
silently emptied the backlog for every project, because it went through SHARED code. For any change
to a shared query or endpoint, check the rows that DON'T carry the brownfield marker — missing json
key, null column, empty dict. That is the greenfield case, and it is the one that breaks quietly.
