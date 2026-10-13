# Brownfield Onboarding — Live E2E Bug-Fix Log

Bugs found by the team during the **live end-to-end test** of the new agent-driven brownfield flow (branch `brownfield-agent-onboarding`), with **root cause verified in code + against the real generated test material**, and the **surgical fix**. We mark each **✅ FIXED** once verified together.

- **Test tenant:** `test-brown@edvensoft.com` (workspace *Edvensoft-brown*) · **Project:** `SpendLog-Brownfield-Testing`
- **Branch:** all fixes land on `brownfield-agent-onboarding` (develop stays clean; merge when green).
- **Test material:** `…/EdvenSDLC-Project/Brownfield_Test_Material/` (the 11 SpendLog docs).

## Legend
🔲 OPEN · 🔧 FIX WRITTEN (awaiting live re-test) · ✅ FIXED (verified) · 🐞 regressed

---

## BF-BUG-1 · ✅ Raw MIME string wraps and misaligns the "Extracted" badge
- **Symptom:** Under each document name the raw content-type is shown (`application/pdf`, and for DOCX the 70-char `application/vnd.openxmlformats-officedocument.wordprocessingml.document`). The long ones wrap to two lines and push the status badge out of alignment.
- **Root cause:** `frontend/src/features/observability/SourceDocuments.tsx:213` renders `{doc.mime}` verbatim in `artifact-row__meta`.
- **Surgical fix:** Add a `fileKindLabel(mime, filename)` helper → a short, human label (**PDF**, **Word (DOCX)**, **Excel (XLSX)**, **Text**, **HTML**). Render that instead of the raw MIME. Frontend-only, cosmetic.
- **Verify:** every row shows a short type; badge stays aligned for DOCX and PDF alike.

## BF-BUG-2 · ✅ Re-uploading the same file duplicates it (source list + artifacts)
- **Symptom:** Uploading a file that was already uploaded/adopted creates a **second** source-document row and a **second** artifact instead of replacing the first.
- **Root cause:** `backend/integrations/onboarding.py::ingest_source_document` always calls `SourceDocument.objects.create(...)`; there is no dedupe by `(project, filename)` and no unique constraint on the model.
- **Surgical fix:** Before creating, look up existing `SourceDocument` rows with the same `(tenant, project, filename)`. **Replace** them: delete their extracted artifacts (safe — `TraceEdge` FK is `on_delete=CASCADE`) + best-effort S3 cleanup + delete the rows, then ingest fresh. Result: exactly one row per filename; re-upload = replace.
  - **Chosen semantics:** re-upload **replaces** the prior upload of that filename regardless of status. If the prior was already *adopted*, it is superseded and the file must be re-adopted. (Team can flip this to "block re-upload when already adopted" — one-line change.)
- **Verify:** upload → adopt → re-upload the same file → still **one** row and **one** artifact.

## BF-BUG-3 · 🔧 Extracted content renders badly (wall of text · no body · no tables)
Three distinct sub-causes, verified by running the platform's own `extract()` on the real files.

### 3a · 🔧 PDF preview is a single wall of text with `## Page 1 / ## Page 2` noise
- **Root cause:** `_extract_pdf` returns `page.extract_text()` whose lines are separated by **single** newlines, and prepends `## Page N`. The preview renderer (`react-markdown` + `remark-gfm`, **no `breaks`**) collapses single newlines into spaces → the whole page becomes one paragraph.
- **Surgical fix (`backend/integrations/extract.py::_extract_pdf`):** preserve the visual line structure — emit each line with a Markdown **hard break** (trailing two spaces) and keep blank lines as paragraph breaks; **drop** the `## Page N` headers (join pages with a blank line). Headings/rows now stay on their own line when rendered.
- **Verify:** the Architecture PDF preview shows separated lines, not one blob; no "Page N" noise.

### 3b · 🔧 Image-only PDF (wireframes) shows only "Source: static_file Filename:…"
- **Root cause:** the wireframes PDF is image-only → `extract_text()` returns **empty** (verified `body_len=0`). With an empty internal body, `preview.py::_read_internal` falls through to `render_structured_ref`, which renders the `external_ref` **pointer** keys (`source`/`filename`/`source_document_id`/`source_s3_key`) as if they were content.
- **Surgical fix:**
  1. `backend/integrations/preview.py` — add the ingest pointer keys to `_REF_POINTER_KEYS` so provenance is **never** rendered as body.
  2. `backend/integrations/onboarding.py::ingest_source_document` — when the extracted body is empty/whitespace, store a clear Markdown note ("_No extractable text — this PDF appears to be image-only…_") so the preview is helpful, not a JSON dump.
- **Verify:** an image-only PDF previews the friendly note; a text doc is unaffected.

### 3c · ✅ Tables/diagrams don't survive PDF extraction (known limitation, not a code bug)
- **Cause:** PDF text extraction cannot recover table structure or embedded diagrams; `_extract_docx` **does** build real Markdown tables. This is why the DOCX-vs-PDF split exists.
- **Action:** document it — for table-heavy or diagram docs, upload **DOCX** (or link the design source). No code change; captured here so testers expect it.

### Test-material issues (self-inflicted in the generated files — not platform bugs)
- **T-1 · em/en-dashes extract as `�`:** my reportlab PDFs embed a font subset whose Unicode map loses `—`/`–`. **Fix (generator):** map dashes → ASCII in the PDF path, regenerate the 5 content PDFs so they extract cleanly.
- **T-2 · wireframes are image-only:** can't be text-extracted (see 3b). **Fix (material):** also provide `11_UX_Wireframes.html` (extractable text) for the adopt-path test; keep the PDF for viewing/Confluence.

---

## Fixes applied (this session) — files + verification

| Fix | Files changed | Verified by |
|-----|---------------|-------------|
| BF-BUG-1 | `frontend/.../SourceDocuments.tsx` (`fileKindLabel` + row) | vitest `fileKindLabel` (5 cases) ✓ · tsc ✓ · eslint ✓ |
| BF-BUG-2 | `backend/integrations/onboarding.py` (`_supersede_prior_uploads` + ingest call) | code + `TraceEdge` CASCADE confirmed · **live re-test pending** (DB) |
| BF-BUG-3a | `backend/integrations/extract.py::_extract_pdf` | `test_extract_pdf_preserves_line_structure` ✓ · **real-file extract**: Architecture.pdf → hard-breaks, no `## Page`, 0 `U+FFFD` ✓ |
| BF-BUG-3b | `backend/integrations/preview.py` (`_REF_POINTER_KEYS`) + `onboarding.py` (empty-body note) | `test_preview_render.py` (2) ✓ · `test_extract_pdf_empty_when_no_text` ✓ |
| BF-BUG-3c | (doc only — known limitation) | n/a |
| T-1 | generator dash→ASCII; **5 PDFs regenerated** | re-extract: 0 `U+FFFD` across all 5 PDFs ✓ |
| T-2 | **added `11_UX_Wireframes.html`** (extractable) | extract → 7,162 chars of structured text ✓ |

---

## Part A — Lossless capture (✅ verified live; team satisfied — "everything works")

Reworked extraction so nothing pictorial is silently dropped, the user can SEE exactly what they uploaded, and status tells the truth. Detail + slice log in `onboarding_fidelity_plan.md`. Verified live on `SpendLog-Brownfield-Testing` (fresh re-uploads of the Architecture + wireframes PDFs).

| Slice | What it does | Status |
|-------|--------------|--------|
| A1 | High-fidelity extraction — **PyMuPDF + pymupdf4llm** PDF text+tables, embedded raster images (PDF/DOCX/HTML) captured, never dropped | ✅ verified |
| A2 | Persist **page renders** + embedded images to S3 as attached views (`external_ref.page_images`) | ✅ verified |
| A3 | **View the original** upload + page images (gated read-through endpoints + viewer) | ✅ verified |
| A4 | **Honest status** — derived fidelity marker (`text` / `images_only` / `empty`) → real badge, not a blanket "Extracted" | ✅ verified |
| A-fix | pymupdf4llm output cleanup — flatten in-cell `<br>` → space, drop empty-table skeletons + bare headings (`_clean_pdf_markdown`) so Architecture tables read cleanly and image-only pages show the reassuring message | ✅ verified |

**Supersession:** BF-BUG-3a/3b/3c are now delivered by Part A (real preservation), not the earlier "note/limitation" stopgaps. PDF tables are reconstructed and read cleanly; image-only PDFs (wireframes) show a plain-language "your pages are preserved, the AI reads them" message + honest badge. The one remaining gap — **diagrams / screenshots as agent-readable text** — is Part B.

## Part B — Document vision (🔧 BUILT this session; awaiting live test)

On adopt, a new **`00e_document_vision`** agent reads the preserved page images on the companion (subscription) and writes faithful text — transcribing screenshots, rebuilding tables, describing diagrams (mermaid/structured) — auto-applied as a new version of the document artifact, so the gap agent + downstream phases read the full content. Detail in `onboarding_fidelity_plan.md`.

| Slice | What it does | Status |
|-------|--------------|--------|
| B0 | Capability check — the MCP tool-result image pipe reaches the model on the subscription CLI (spike, proven) | ✅ verified (spike) |
| B1 | `get_page_images` MCP tool streams a document's page images as image blocks (paginated, downscaled) | ✅ unit-tested |
| B2 | `00e` agent + auto-apply run path (per-doc hidden carrier, `auto_approve` flag, workflow + verify_writes branches) | 🔧 built, unit-tested |
| B3 | Trigger vision on adopt (best-effort, only when page images exist) | 🔧 built, unit-tested |
| Universal seed | Data migration backfills `00e` onto every existing tenant on `make migrate`; on-create hook covers future tenants | 🔧 built |

**Part B needs, before live test:** (1) run migrations (or `seed_agents --tenant <id>`) so `00e` is seeded for the tenant; (2) restart the companion so it picks up `get_page_images` + the agent body. Backend + worker already restarted. Without the seed, adoption degrades gracefully (vision skipped, doc still adopted).

## Step 4 — Index code (live E2E, 2026-07-31)

Second live session on `brownfield-agent-onboarding`. Tenant `test-brown@edvensoft.com` · project **SpendLog-Brownfield-Testing** · repo **TARUN51/medslot-single-repo** (100 files, base `main`).

Context the team should know before reading these: **"Index code" does NOT run the mechanical indexer.** Per commit `bcddebd` (*Agent-driven brownfield onboarding — Slices 3-5*) it triggers the **`00c_intelligent_context_extractor` agent** on the user's companion; the mechanical `CodeIntelJob` survives only as the no-companion fallback. Same for "Run gap report" → `00_onboarding`. Both run against a **carrier work item** hidden from the backlog, and both return **202 + a run id** (async), not a result.

### S4-1 · ✅ Index code / Gap report opened a gate nobody could ever action
- **Symptom:** every onboarding agent run left a **PENDING approval** behind. It inflated the gate count and could never be approved or dismissed.
- **Root cause:** `orchestration/trigger.py::trigger_onboarding_agent` called `trigger_phase` without `auto_approve`, so it defaulted to `False` and `AgentRunWorkflow` ran `open_gate`. The approval attaches to the **carrier** work item, which is hidden from every user-facing list — so the gate existed but was unreachable.
- **Surgical fix:** pass `auto_approve=True` (the mechanism the `00e` vision path already proved). The workflow's auto-apply branch publishes and completes without opening an Approval.
- **Not a #5 violation:** `publish_artifacts_core` publishes **INTERNAL** only; external export to a SoR stays user-triggered. Nothing reaches Confluence/Jira without a human.
- **Guard:** `test_a_normal_phase_still_opens_its_gate` asserts `auto_approve` stays `False` for every ordinary phase.
- **Verify:** run Index code → `pending gates` stays 0. ✅ verified live.

### S4-2 · ✅ Carrier runs leaked into Phases & Runs and the dashboard
- **Symptom:** the onboarding run surfaced in project-wide run lists and inflated the workspace dashboard's "Needs me" counts, despite its work item being hidden.
- **Root cause:** hiding the **work item** was not enough. `api/views.py::RunViewSet.get_queryset` filters by `project` and had **no carrier exclusion**; the dashboard rollup queried `Run.objects.filter(work_item__project=…)` the same way.
- **Surgical fix:** exclude carrier-hosted runs from `RunViewSet`'s **list** action and from the dashboard rollup. Retrieval by id is untouched, so a direct run link still resolves.
- **Also:** extracted the shared `integrations/onboarding.py::carrier_q(prefix)` so the **load-bearing S3-13 `has_key` guard** exists once instead of being copy-pasted three times.
- **Verify:** Phases & Runs, Gates and the dashboard show nothing during an index run. ✅ verified live.

### S4-3 · ✅ No "running" state — the button reverted and the run looked like a no-op
- **Symptom:** click Index code, the button flicked back to normal, no message, nothing anywhere. A 25-minute agent run was indistinguishable from a dead click.
- **Root cause:** `onboarding_hub`'s `index` block had only two states — `"indexed" if intel_artifact else "not_started"`. **There was no "running".** The UI could not know work was in flight.
- **Surgical fix:** new `onboarding_step_state()` + per-repo `index.repos[]` (`status` / `running` / `run_id` / `question` / `artifact_id`) and `gap.running` / `gap.question`. The hub polls every 4 s and renders from that.
- **Verify:** button holds "Indexing dispatched…" for the life of the run. ✅ verified live.

### S4-4 · ✅ The progress message never cleared
- **Symptom:** once shown, the "running" line stayed forever — through completion and every later re-index.
- **Root cause:** the message was rendered from the **mutation result** (`startCodeIntel.data`), which is set once and never resets. Same for the local `dispatched` map driving the button label.
- **Surgical fix:** derive **all** button + message state from the polled server resource. Server state clears itself, so completion and re-index need no manual reset.
- **Lesson for the team:** *drive UI from the resource, not from the mutation.* Any "it never goes away" bug on this screen is likely this shape.

### S4-5 · ✅ Message rendered nothing while the button worked
- **Symptom:** after S4-3/S4-4 the button correctly showed "Indexing dispatched…" but **no message appeared below it**.
- **Root cause:** the payload gave each repo `status: "running"` but **omitted the `running` boolean**. The button switches on `status`; the shared message component switches on `running` → `undefined` → rendered `null`.
- **Surgical fix:** emit **both** keys. `status` is the tri-state the button needs; `{running, question}` is the shape the shared component needs so one component serves Index code *and* Gap report.
- **Why the tests missed it:** they covered `onboarding_step_state()` directly but never the **hub payload wiring**. Added `test_hub_index_repos_carry_both_running_and_status`.

### S4-6 · ✅ UI copy leaked an internal agent key and pointed at an invisible screen
- **Symptom:** *"Running the code-intelligence agent (00c) on your companion — track it in Phases & Runs."*
- **Root cause:** two faults in one sentence — `00c` is an internal registry key no user can interpret, and the run is **structurally invisible** in Phases & Runs (it hangs off a hidden carrier, and that screen filters runs by the selected work item).
- **Surgical fix:** plain-language copy, no agent keys, no false pointer. Progress is reported **on the Onboarding hub itself**, which is the only place it can be. Done state links straight to the artifact preview.

### S4-7 · 🔧 Repo-scoped runs hang forever — tools un-denied but never allow-listed
**The big one. This path had never worked.**
- **Symptom:** `00c` ran for **27 min**, then **15 min**, with **zero artifacts, zero tool calls, no error**. Killed both times.
- **Evidence:** engine process at **4.5 s CPU over 15 minutes**; `codeintel_mcp` at **0 s** (never called); scan worktree unmodified since creation — while MCP servers, the 26 KB system prompt and all 9 `codeintel__*` tools were correctly wired.
- **Root cause:** `drivers/claude_driver.py` — a `reads_code` phase uses `_SCAN_DISALLOWED_TOOLS`, which deliberately **stops blocking** `Read/Glob/Grep/Bash` (10_security needs them for semgrep / pip-audit / syft). But `allowed_tools` was passed through **unchanged**, so those tools were neither denied nor allow-listed. Under **`permission-mode=default`** that combination raises a **permission request** — and an engine run has **no human and no TTY** to answer it. The CLI blocks forever.
  - A stale comment asserted *"Built-in tools are governed by this denylist, not `allowed_tools`"*. That assumption is what shipped the bug. Removed.
- **Why vision (`00e`) was never affected:** the sandbox path **hard-denies** those tools, so the agent is told "no" and moves on to its MCP tools. It never gets the chance to ask.
- **Surgical fix:** `allowed_tools=list(allowed_tools) + _SCAN_LOCAL_TOOLS` on the scan branch (`Read, Glob, Grep, Bash, BashOutput, KillShell`). Confirmed live: the engine's granted tool count went **26 → 32**.
- **Blast radius:** affects **both** `reads_code` agents — `00c` (Index code) **and** `10_security`. The security phase carries the same latent hang.
- **Guards added:** `test_scan_path_allow_lists_the_local_tools_it_stops_denying` and `test_sandbox_planning_still_denies_local_tools` (proves greenfield keeps its no-filesystem sandbox).
- **Status:** fix applied and loaded (companion restarted); **a successful end-to-end index has NOT yet been observed.** Stays 🔧 until one completes.
- **Open decision:** granting `Bash` to `00c` is wider than that agent needs — `daemon.py` states 00c should query via `codeintel.*`, not raw file tools. Option B (allow local tools only for `10_security`, keep `00c` on `codeintel.*`) is the cleaner end state.

### S4-8 · 🔲 The companion reports nothing while a run is in progress
- **Symptom:** during a 15-minute run `companion.log` contained **144 bytes** — two reconnect lines, nothing about the run. No claim, no tool call, no phase progress.
- **Impact:** for a step that is invisible by design and takes minutes, there is **no way to tell working from hung** without inspecting OS process CPU. Both hangs above were diagnosed that way, not from any log.
- **Suggested fix:** log claim / phase start / each tool call / report at INFO. Cheap, and it turns a 30-minute investigation into a glance.

### S4-9 · 🔲 Seven tests assert behaviour the branch deliberately changed
- **Symptom:** `tests/test_onboarding.py` — 7 failures (`IndexError: list index out of range` on `out["artifact_ids"][0]`, plus two assertion mismatches).
- **Root cause:** commit `b97f804` (*Create a document's artifact when it is adopted, not when it is uploaded*) intentionally moved artifact creation from upload → adopt. These tests still assert the old behaviour and were never updated. **Brownfield-only** — the commit is not on develop.
- **Affected:** `test_ingest_creates_draft_artifact_with_provenance`, `test_ingest_carries_title_onto_artifact`, `test_adopt_publishes_after_role_check_and_is_idempotent`, `test_adopt_wrong_role_is_blocked`, `test_adopt_with_target_type_reclassifies_so_gap_report_sees_it`, `test_link_confluence_pages_registers_typed_pointers_idempotently`, `test_linked_confluence_page_feeds_gap_report`.
- **Also:** `test_document_vision.py::test_auto_apply_rejects_a_version_that_shrank` greps for *"shorter version"*; the message now says *"shorter rendering"*.
- **Must be fixed before this branch merges** — a red suite hides real regressions.

### S4-10 · ✅ Opening "Connect Machine" silently kills the running companion
- **Symptom:** a working companion started failing every poll with `401 invalid or missing Runner token`.
- **Root cause:** visiting the Connect Machine page mints a **new** enrollment and **revokes** the current one. The running companion holds the revoked token and dies. Verified in the data: `20cddcee` revoked at 09:13, `90b52e99` created 09:13.
- **Compounding:** the token is shown **once** and stored only as a hash — unrecoverable. The tenant had **10 enrollments**, 8 `active`, most never used.
- **Suggested fix:** warn before revoking while a companion is online, and/or offer "show the command for the current enrollment" without minting a new one.
- **✅ VERIFIED FIXED 2026-09-03 — by work already merged, not by anything new.** Re-read against the code as it stands, all three links in the chain are broken, and any one of them alone would break it:
  1. *Opening the screen mints a token* — it does not. A token is minted only when the user **clicks** "Generate enrollment token" (`ConnectMachine.tsx` `onGenerate`).
  2. *Minting revokes the previous enrollment* — it does not. `apps/runs/enrollment.py::enroll_runner` creates a row and returns a token. It contains no revoke, no update, nothing that touches another row.
  3. *A second enrollment steals the work* — it does not. `trigger.py::_resolve_enrollment` prefers an enrollment that is **online** (`last_seen` inside the threshold), then one that has been seen at all, and only then the newest. A freshly minted, never-used enrollment is chosen **last**.
  The symptom was fixed by the row-61/RC-4 grouping work — `list_developer_enrollments` collapses label-less enrollments for one project into a single card, and its comment names that bug — and hardened again by the online-preferring dispatch. **No further work is needed for the symptom this entry describes.**
- **What remains, and where it went:** the *compounding* observation above is real and outlives the symptom. Disconnect sends only the representative row's id and `revoke_runner` revokes exactly one row by primary key, so a developer who generated three tokens still holds two working ones afterwards; and enrollment tokens never expire. That is recorded against **Bugs.xlsx S.No 35**, which owns the Connect Machine redesign, together with the token travelling on the command line (`multi_project_recon` C1/C4) and the still-anonymous `POST /api/runners/` found while closing S.No 214. All four are one question — how does a headless machine authenticate — and are to be answered together, not piecemeal.

### S4-11 · 🔲 Humans and agents see different projects
- **Symptom:** the Artifacts page shows **11** artifacts; the database holds **19**.
- **Root cause (correct, by design):** `RUN_RECORD_ARTIFACT_TYPES = ("document_vision",)` hides per-run bookkeeping blobs from the registry list (commit `dee8106`) — the deliverable is the document the agent rewrote, not the run's own record.
- **The asymmetry:** that exclusion lives **only** in `api/views.py::ArtifactViewSet`. The agent-facing `mcp_platform_state/tools.py::list_artifacts` has **no such filter**, so agents see all 19.
- **Risk:** an agent reasoning over *counts* or *coverage* double-counts every vision-read file. **`00_onboarding` (gap report) is exactly that kind of reasoning** — watch its evidence counts for duplicated document names.
- **Suggested fix:** apply the same exclusion inside `list_artifacts` (or an explicit `include_run_records=False` default) so both doors show the same project.

### S4-12 · 🔲 `00c` agent body does not match the tools it is given (MIGRATION DEFECT)
Found by reading `agents/00c_intelligent_context_extractor/agent.md` (152 lines) against the real
`codeintel` MCP surface and the platform-state allowlist. **These are `AGENT_MIGRATION_SPEC` §8
reference-sweep misses** — the ~15% "rewrite every data reference" bucket. The reasoning (Role,
Evidence, Process, quality gate) is sound and must be preserved verbatim; it is the *references*
that are wrong. A migrated agent that still names a tool signature the platform does not expose
is a FAILED migration by the spec's own definition.

| # | Agent body says | Platform actually exposes | Impact |
|---|-----------------|---------------------------|--------|
| a | `codeintel.index(workspace=…, repo=…)` (line 59) | `index(repo: str \| None = None)` — **no `workspace` parameter** | Low in practice: MCP tool schemas are authoritative and the live transcript shows the agent sent `{"repo": "TARUN51/medslot-single-repo"}`, ignoring the doc. Still a wrong instruction. |
| b | `get_dependency_path(repo, from, to)` (line 82/131) | `get_dependency_path(frm, to, repo=None)` — `from` is a Python keyword, so the code uses `frm` | **An agent following the doc literally fails this call.** |
| c | "**Also index each artifact's body into the Knowledge Index**" (line 91, and required again in the quality gate line 141) | **No Knowledge-Index tool exists** in the agent's 16 platform-state tools | The agent is ordered to perform a step it has no tool for — and its own completion checklist demands it. A plausible stall/loop source: an agent that cannot tick a required box may keep retrying. |
| d | "The platform opens the review gate — the required reviewer (Tech Lead) decides" (line 152) | **Wrong as of 2026-07-31** — Index code now runs headless (`auto_approve`, see S4-1). No gate opens. | The agent will tell the user a reviewer must approve something that will never appear. |

**Also worth calibrating:** the body requires **five** artifacts (`codebase_intelligence`, `dependency_graph`, `git_analytics`, `dead_code`, `architecture_decisions`) plus an `assumption` artifact, and the master document alone specifies 13 sections. Even a healthy run is minutes of writing after the analysis — not seconds. Expectations were set wrongly earlier in testing.

**Action:** run the §8 reference sweep over `00c` (and then over every other migrated agent — b/c/d are the kind of miss that repeats). Fix the two signatures, delete or implement the Knowledge-Index step, and align the completion text with the headless path.

---

## Step 4 — second pass (2026-07-31, after the first successful run)

Run `98ab9a8c` **completed** — the first time Index code has ever worked end to end: 7 artifacts
published, 0 gates, `commits: 22`, 73 files. Everything below was found either while diagnosing
why the three runs before it failed, or by watching that successful run closely.

> **Correction to an earlier claim in this document.** S4-7 was reported as the cause of the
> hangs. **It was not.** Reading the run-1 engine transcript afterwards showed `Bash` returning
> normally at 09:30:55 — *before* the S4-7 fix existed. The real cause is S4-13. The S4-7 change
> is still correct and is kept (it fixes a genuine latent inconsistency, and `10_security`
> carries the same one), but it did not fix this. The diagnosis was published before the
> transcripts were read.

### S4-13 · ✅ THE HANG — git inherited the MCP server's JSON-RPC channel (ROOT CAUSE)
- **Symptom:** three runs died. `codeintel.index` never returned; the engine eventually reported
  *"MCP server 'codeintel' tool 'index' sent no response or progress for 1800s"*.
- **Evidence:** `git log … --name-only` alive **369 seconds at 0 s CPU**, parent already gone.
  The identical command run by hand returned 6,689 bytes instantly.
- **Root cause:** `_git` used `capture_output=True`, which redirects **stdout and stderr only** —
  stdin is still inherited. Harmless from a web process. Fatal inside a **stdio MCP server**,
  whose stdin *is* the JSON-RPC channel to the engine: git got a duplicate handle to the protocol
  pipe, blocked on it, and the server had no line left to answer on.
- **Surgical fix:** `stdin=subprocess.DEVNULL` in **four** places — `codeintel/builtin.py::_git`,
  `worktree.py::_git`, `runner.py` provisioning commands, and the `runner.py` build `Popen`.
- **Guard:** `test_git_helper_never_inherits_stdin`.
- **Rule this establishes:** *any* subprocess spawned under a stdio MCP server must own its stdin.

### S4-14 · ✅ The CodeIntel server ran without an environment (git invisible)
- **Symptom:** `commits: 0` on a repo with real history — reported as "no history", not as an error.
- **Root cause:** `daemon.py` launched `codeintel_mcp` with **3 hand-built env vars**. No `PATH`,
  so git could not be found. (On Windows, no `SYSTEMROOT` is worse still: the interpreter dies in
  `import asyncio` with WinError 10106 before any of our code can log it.)
- **Fix:** inherit `os.environ`, then overlay the run-specific vars. Measured: `commits 0 → 22`.
- **Guard:** `test_both_mcp_servers_inherit_the_environment`.

### S4-15 · ✅ The agent delegated its own work to a queue nothing was running
- **Symptom:** the agent called `TaskCreate` and waited on a background task that would never run.
- **Fix:** `_BACKGROUND_TOOLS` (Task*/Cron*/Monitor/SendMessage/…) denied on both driver paths.

### S4-16 · ✅ `add_trace_edge` was undiscoverable, and failed with HTTP 500
- **Symptom:** the agent guessed **nine** relationship values before one stuck, then used that one
  (`implements`) for **every** edge. Verified in the data: all 5 edges of run `98ab9a8c` read
  `implements` — semantically wrong (a dependency graph does not "implement" a document).
- **Root cause, three layers:** the valid set (`derives, implements, tests, deploys`) existed only
  in the model enum — not in the tool signature, not in a docstring, not in the error message; and
  `RunnerStateView` mapped only `TypeError` to 400, so every rejected **value** surfaced as a
  **500**. An agent reading 500 concludes the platform is broken and retries the same call.
- **Surgical fix:** docstring naming all four values with their meaning (on **both** MCP surfaces —
  `mcp_platform_state/server.py` *and* `runner/companion/state_mcp.py`, which is the one the
  companion agent actually sees); error message lists the valid values and echoes what was
  rejected; `ValueError → 400`.
- **Guards:** 3 tests incl. `test_rejected_value_is_400_and_explains_itself`.

### S4-17 · ✅ `search_codebase` matched letters, not words — and only file names
- **Symptom, both observed live:** `'authentication JWT token'` → **nothing**, in a repo that
  authenticates. `'CI CD pipeline docker compose'` → **`dependencies.py`**, because "ci" sits
  inside "dependen**ci**es". It never errored; it answered confidently and wrongly.
- **Root cause:** `sum(low.count(t) for t in terms)` over **paths only** — raw substring counting.
- **Surgical fix:** whole-word regex matching; searches file **contents** as well as paths (a
  bounded, lower-cased copy — 20 KB/file, 40 MB/repo, so a monorepo cannot exhaust the developer's
  machine); single-character terms dropped; results carry `terms_matched` / `of_terms` / `where`.
- **Guards:** `test_search_matches_whole_words_not_substrings`,
  `test_search_finds_content_not_just_filenames`.

### S4-18 · ✅ The Knowledge Index was never populated — the phase's whole purpose leaked out
- **Symptom:** measured in the DB after the successful run — `KnowledgeChunk` rows for its seven
  artifacts: **0**. Every later phase would re-read the codebase rather than retrieve what Step 4
  computed at a cost of ~40 minutes.
- **Root cause:** the agent bodies instruct *"index each artifact's body into the Knowledge
  Index"*, and **no such tool is exposed**. No agent could ever have complied. (This is S4-12c,
  now closed.)
- **Surgical fix:** the **platform** does it — `register_artifact` chunks the staged body via the
  existing `apps/knowledge/index.py::index_artifact` at registration. Idempotent, so a
  re-registration re-indexes cleanly. Best-effort: retrieval is an accelerator, never a
  correctness gate, so a store hiccup logs a warning and never fails a registration.
- **Blast radius (good):** this fixes retrieval for **every phase**, not just Step 4.
- **Guards:** 3 tests incl. failure-tolerance and pointer-only artifacts.

### S4-19 · ✅ Only 10 languages recognised; config/CI files invisible; unknown reported as zero
- **Root cause:** one line — `if path.suffix not in _LANG_EXT` — gates `file_meta`, which is the
  **only node set** the dependency graph, PageRank, hotspots, dead code and search all read.
- **Three distinct failures it caused:**
  1. A C#/PHP/Swift/C++/Vue repo indexes as **zero files**. Git analytics is *not* filtered, so it
     still reports thousands of commits with **0 hotspots** — the shape of a *healthy* codebase.
     The worst possible failure for a tool whose job is finding risk.
  2. `package.json`, `.github/workflows/*.yml`, `docker-compose.yml`, `Dockerfile` all carry
     non-code (or no) extensions, so **"CI/CD presence" and "tech stack" were unanswerable** — the
     only evidence available was which code extensions appeared. This is why the agent offered
     `dependencies.py` as CI/CD evidence.
  3. `get_context` on an unindexed path returned a full row of **zeros** — 0 lines, 0 complexity,
     no owner, `bus_factor_risk: false` — indistinguishable from a small, clean, well-shared file.
- **Surgical fix:** widened `_LANG_EXT` (+20 languages); added a **separate** `_CONTEXT_EXT` /
  `_CONTEXT_NAMES` inventory collected for **presence only**, never graph nodes, so the evidence
  base widens without distorting the analysis; `get_overview().signals` gives evidence-backed
  yes/no for CI/CD, containerisation, IaC, dependency manifests and docs, each naming the proving
  files; `get_context`/`get_risk` return `{"indexed": false, "reason": …}`; `index()` reports
  `skipped_files` by extension.
- **Note:** `skipped_files` closes a checkbox the agent could never honestly tick — its own quality
  gate demands *"any skipped files recorded as assumptions"*, and it had no way to know.
- **Guards:** 4 tests.

### S4-20 · ✅ Any git failure was indistinguishable from "this repo has no history"
- **Root cause:** `_git` collapsed **every** outcome to `""` — timeout, missing binary, corrupt
  index, and a genuinely empty repo all identical. Empty string → every counter stays 0 →
  `_hotspots` skips every file (`churn <= 0`) → **the churn×complexity ranking, the highest-value
  output of this phase, comes back empty and reports as "no hotspots found"**. The agent's own
  Step 1 check passes regardless, because `file_count` comes from the filesystem walk.
- **Not hypothetical: S4-14 was exactly this shape** and cost real debugging time.
- **Surgical fix:** `_git_checked` returns `(stdout, error)`; analytics carries
  `ok` / `partial` / `error`; a timeout **retries smaller** (`-n 200`) so partial history that we
  *know* is partial beats none; new `index_report` tool + `index_health` on `index()`;
  `worktree.py::_git` gained a 300 s timeout (it previously had **none at all** — the companion
  could wait forever on a remote git operation).
- **Guards:** 3 tests.

### S4-21 · ✅ The companion died on a transient backend error
- **Symptom (caught live by a background monitor, mid-session):** the shared Postgres dropped one
  connection (`SSL SYSCALL error: EOF detected`), `/api/runner/work/` returned 500, and the
  companion **exited**. Heartbeat went stale; the developer's only symptom is a button that
  silently stops working, with no visible link to a blip minutes earlier.
- **Root cause:** connection failures (OSError) were already retried forever, but an HTTP **5xx**
  raised a plain `DaemonError` that the serve loop — catching only OSError — let escape.
- **Surgical fix:** new `TransientBackendError` for 5xx on both claim paths, retried with the
  existing backoff; `_report` also retries a 5xx (a finished phase is too expensive to lose to a
  database blip). **4xx stays fatal** — a revoked token is a real rejection retrying cannot fix.
- **Guards:** 3 tests incl. `test_claim_4xx_is_still_fatal`.

### S4-22 · ✅ A leaking test made a passing test look broken
- `--headed` wrote to the real `os.environ`; `monkeypatch.delenv` on an already-absent variable
  records nothing to restore, so the flag leaked into every later test in the session. A Playwright
  test then **failed in a full run and passed alone** — the exact signature of a phantom
  regression, and a guaranteed time-sink during demo prep. Popped explicitly.

### Cross-reference — platform-wide, owned by the team (not brownfield)
**Re-running a phase duplicates artifacts (v1 + v2) instead of replacing.** Full blast-radius recon delivered 2026-07-31: the defect is in the shared `register_artifact`, so it spans **every phase, both branches, greenfield and brownfield**. Orphaned state includes phantom gates, stranded clarifications, unreclaimed S3 bodies, orphan trace edges and (if a published run is re-run) duplicate Confluence pages. The team took ownership of this one.

---

## Step 4 — third pass (2026-08-03): the fixes taken live, and two found by doing it

Three Index-code runs this session. The first two were aborted for setup reasons and cleaned up;
the third, **`9d1b4d32`**, completed in **10 minutes**: 7 artifacts, **51 knowledge chunks**,
5 `derives` edges, **0 gates**. This is the run that promotes S4-16 … S4-21 from "tests green"
to **verified live**, and it is where S4-23 and S4-24 were found.

**Setup finding worth recording (cost one aborted run).** The companion was restarted without
`--repo-path` / `--worktrees`. The agent then ran with **no worktree and no `codeintel` MCP
server at all** — and did not fail: `daemon.py` logged *"has no worktree … scanning manifest
only"* and carried on, analysing paperwork instead of code. E2E prerequisite #4 in
`brownfield_bugs.md` already requires those flags; nothing enforces them. **Pre-flight that
actually proves it:** after clicking, check a `codeintel_mcp` process exists and a
`.sdlc-worktrees/scan-<run-id>` directory was created. Both are absent when the flags are missing.

### S4-23 · ✅ The dependency graph invented edges that do not exist in the code
- **Symptom:** run `bf0f27c0` reported a "Cross-Tier Anomaly" — `backend/app/middleware/logging.py`
  and `backend/tests/test_migrations.py` importing `frontend/src/api/types.ts`. A backend module
  importing a frontend file is architecturally impossible.
- **Verified against source:** neither file imports anything from the frontend. `logging.py` imports
  `json`, `logging`, `time`, `starlette.requests`, `starlette.types`. **The edges are fabricated.**
- **Root cause** (`integrations/codeintel/builtin.py::_dependency_graph::resolve`): an import token
  was matched to a file **by bare name, across the whole repository, in any language**, with no
  check for stdlib, third-party, or language. Two rules misfired:
  - `import types` (stdlib) → rule 1's suffix match, `"frontend/src/api/types".endswith("/types")`;
  - `from starlette.types import …` (third-party) → rule 3's "unique basename" fallback, because
    exactly one file in the repo has the stem `types`.
- **Measured blast radius on the real repo — bigger than the two edges reported:** `_analyze` run
  directly over `medslot-single-repo` gave **127 edges, of which 8 were false**. Seven files
  "imported" `middleware/logging.py`; **only one really does** (`main.py`) — the other six merely
  write `import logging`, meaning that file's inbound count and PageRank were overstated **7×**.
- **Why it matters beyond two wrong lines:** the graph feeds PageRank, blast-radius, architecture
  communities and coupling risk. The false cross-tier edges were **welding the backend and frontend
  into one component**: the same repo reports **2 communities before the fix and 3 after**. The
  architecture map was wrong, not merely annotated.
- **Surgical fix** — three guards, each fenced by what the language makes possible:
  1. **Same-language-family only** (`_IMPORT_FAMILY`). A Python `import` can never name a `.ts`
     file. Extensions absent from the map can never be a target — correct: nothing imports `.css`.
  2. **Python stdlib roots skipped**, from `sys.stdlib_module_names` (authoritative, version-exact,
     cannot drift from the interpreter running the analysis). Relative imports are exempt — those
     are always local.
  3. **A dotted Python path must match in full.** `starlette.types` may no longer fall back to
     "the only file named `types`"; `a.b.c` has to match a path containing `a/b/c`.
- **Result:** 127 → **119 edges**; cross-language 2 → **0**; inbound to `middleware/logging.py`
  7 → **1**, and the surviving one is the genuine `from app.middleware.logging import …`.
- **Guards:** 4 tests, incl. `test_an_explicit_local_import_of_that_same_module_still_resolves` and
  `test_relative_js_import_still_resolves` — both exist to catch **over**-correction. Returning
  None is safe (a missing edge understates coupling); a fabricated edge invents architecture.
- **Verified live in run `9d1b4d32`:** no anomaly section raised, `middleware/logging` not mentioned
  at all, `types.ts` correctly placed inside the frontend community only, communities = 3.

### S4-24 · ✅ The agent forwarded an unverified anomaly instead of resolving it
- **Symptom:** having found the S4-23 edges, `00c` wrote them into the report as a finding and asked
  the reader to *"inspect `logging.py` before any refactor"*. One `grep` settles it.
- **The team's question:** should it not have used **clarifications** (`ask_human`)? Checked:
  `ask_human` **is** wired on this path (`state_mcp.py:218`, `BUILD_STATE_TOOLS`), the hub carries
  `index.repos[].question`, and the agent also had `Read`/`Grep`/`Glob` (the S4-7 allow-list).
  **The `00c` body mentioned `ask_human` zero times in 152 lines.**
- **Root cause:** the body offered only one route for an odd result — record an assumption. It never
  said *verify it yourself*, and never said the clarification channel existed.
- **Why asking the user is wrong *for this case*:** the answer is in the repo and the agent has the
  tools. Asking would stall a headless run on a question the user must read the code to answer.
  Clarifications are for what only a human knows — intent, ownership, whether something dormant is
  deliberate.
- **Surgical fix** (`agents/00c_.../agent.md`, Step 2 + quality gate): a ranked three-way rule —
  **(1)** answerable from code → answer it yourself; **(2)** answerable only by a person → a single
  `ask_human` call, surfaced on the Onboarding page; **(3)** neither → Tier-3 `assumption`. Plus the
  named failure mode: *forwarding an unverified anomaly hands your work to the user and the artifact
  still carries the wrong data — downstream agents read the artifact, not the caveat.*
- **Guards:** a migration test asserts `ask_human` is named **and** that self-verification is ranked
  before it, so this can never be "fixed" into an agent that stalls on code-answerable questions.
- **Verified live in run `9d1b4d32`** — and it generalised beyond the case that prompted it:
  - a new **"## Anomaly Verification"** section: *"No structurally impossible edges detected …
    all Python imports resolved within the repo"*, with `client.test.ts` and the Alembic files
    each checked and explained rather than flagged;
  - dead code went from *"5 candidates (all low confidence)"* to **"all five are false positives —
    verified by reading the architecture diagram and source"**, with a per-file reason.
- **⚠️ Honest limit:** this run contained no anomaly needing a human, so the **`ask_human` branch was
  never exercised**. S4-24 is verified for the self-verify path, **untested for the ask path**.

### S4-25 · ✅ A completed run never records when it ended — **CLOSED as S5-26**
- **Symptom:** run `9d1b4d32` is `completed` with `ended_at = None`. Same for `98ab9a8c`,
  `bf0f27c0` and every completed `00e` vision run.
- **Contrast:** *failed* runs do set `ended_at` (e.g. `2745c2e0`, `7c46b43c`), so the column works —
  it is the success path that skips it.
- **Impact:** run duration is uncomputable from the data, so no screen can show "took 10 minutes"
  and no regression in run time can be measured. Low severity, trivial to miss, easy to fix.
- Found while assembling the run report; not fixed at the time — logged for the team.
- **FIXED.** Re-found and closed in the Step-5 second pass as **S5-26**: `publish_artifacts` now
  stamps `ended_at` on the success path. Verified in the code on 2026-09-17 —
  `backend/orchestration/activities.py:423`, with the same stamp on the other completion paths at
  `:259` and `:286`. The last terminal path without it, **rejection**, was closed separately as
  **G-1**. Durations are recordable on every path.
- *The 🔲 on this heading survived until 2026-09-17 because the fix was recorded under S5-26's
  number, and only the summary tables were updated.*

---

## Status summary
| ID | Title | Status |
|----|-------|--------|
| BF-BUG-1 | MIME label wraps / misaligns badge | ✅ FIXED (verified live) |
| BF-BUG-2 | Re-upload duplicates | ✅ FIXED (verified live) |
| BF-BUG-3a | PDF wall-of-text + Page N noise | ✅ FIXED via Part A (pymupdf4llm clean markdown) |
| BF-BUG-3b | Image-only PDF dumps pointer metadata | ✅ FIXED via Part A (page images preserved + viewable + honest status + reassuring message) |
| BF-BUG-3c (tables) | PDF tables lost | ✅ FIXED via Part A (tables reconstructed, `<br>`/empty-table cleanup) |
| BF-BUG-3c (diagrams/screens) | Diagrams/screenshots not agent-readable | 🔧 Part B vision built — awaiting live test |
| T-1 | Test PDFs: dashes → � | ✅ FIXED (regenerated) |
| T-2 | Wireframes image-only → add HTML | ✅ FIXED (HTML added) |
| S4-1 | Onboarding agent opened an unreachable gate | ✅ FIXED (verified live) |
| S4-2 | Carrier runs leaked into Phases & Runs + dashboard | ✅ FIXED (verified live) |
| S4-3 | No "running" state — run looked like a no-op | ✅ FIXED (verified live) |
| S4-4 | Progress message never cleared | ✅ FIXED |
| S4-5 | Message rendered nothing (missing `running` key) | ✅ FIXED (verified live) |
| S4-6 | Copy leaked agent key `00c`, pointed at an invisible screen | ✅ FIXED |
| S4-7 | Repo-scoped runs hang — un-denied but not allow-listed | ✅ FIX KEPT — **but it was NOT the cause of the hangs** (see S4-13). Genuine latent inconsistency; `10_security` had it too |
| S4-8 | Companion logs nothing during a run | 🔲 OPEN — partially mitigated in practice: redirecting the companion's output to a file (`>> companion.log 2>&1`) does capture the failure-path lines, and caught the missing-worktree misconfiguration this session. It still reports **nothing** while a healthy run is in progress |
| S4-9 | 7 stale tests from `b97f804` | ✅ FIXED — `test_onboarding.py` **28/28 green**. Artifact ids now come from the **adopt** result (upload registers nothing since `b97f804`); the two Confluence tests gained the adopt step the 2026-07-29 two-step decision requires, and now assert the phase reads *missing* until adoption. Also fixed `test_document_vision.py` ("shorter version" → "shorter rendering") |
| S4-10 | Connect Machine revokes the live companion's token | ✅ FIXED (verified 2026-09-03; residue → S.No 35) |
| S4-11 | Agents see run-record artifacts the UI hides | 🔲 OPEN (decision) |
| S4-12 | **`00c` agent body ≠ the tools it is given** (migration §8 miss) | ✅ FIXED — all four (a `workspace` param, b `frm` not `from`, c Knowledge Index → S4-18, d headless not a Tech Lead gate). **Re-sweep of the OTHER migrated agents still owed** |
| S4-13 | **THE HANG — git inherited the MCP server's JSON-RPC channel** | ✅ FIXED (verified live: run completed) |
| S4-14 | CodeIntel server launched without an environment (git invisible) | ✅ FIXED (verified live: `commits 0 → 22`) |
| S4-15 | Agent delegated its work to a background queue nothing runs | ✅ FIXED |
| S4-16 | `add_trace_edge` undiscoverable; caller error returned 500 | ✅ FIXED — **verified live**: all 5 edges of `9d1b4d32` read `derives` (were 5 × `implements`) |
| S4-17 | `search_codebase` matched substrings, and only file names | ✅ FIXED — **verified live**: JWT/auth found by identifier; CI/CD answered from `signals`, not a coincidental match |
| S4-18 | **Knowledge Index never populated — 0 chunks for 7 artifacts** | ✅ FIXED — **verified live: 51 chunks** across 7 artifacts (was 0). Fixes retrieval platform-wide |
| S4-19 | 10 languages only; CI/config invisible; unknown reported as zero | ✅ FIXED — **verified live**: CI/CD cites `.github/workflows/ci.yml`, containerisation `backend/Dockerfile`; all 8 cited evidence files confirmed to exist; `skipped_files` recorded as assumptions |
| S4-20 | Any git failure indistinguishable from "no history" | ✅ FIXED — **verified live**: report carries `git.ok=true, git.partial=false, 22 commits read, content_search_complete=true` |
| S4-21 | Companion died on a transient 5xx from the platform | ✅ FIXED — **verified live**: companion rode out **two** backend restarts (backoff 5s → 10s → reconnected) instead of exiting. Note the observed path is the connection retry; the 5xx branch itself is still only covered by tests |
| S4-22 | Leaking test made a passing test look broken | ✅ FIXED |
| S4-23 | **Dependency graph invented edges (stdlib + cross-language)** | ✅ FIXED — **verified live**: 127 → 119 edges, 8 false removed, 1 real kept; communities 2 → 3 |
| S4-24 | Agent forwarded an unverified anomaly instead of resolving it | ✅ FIXED — **verified live** for the self-verify path (new "Anomaly Verification" section; dead code verified against source). **`ask_human` branch untested** |
| S4-25 | A completed run never records `ended_at` | ✅ FIXED (tests green) — closed in the Step-5 second pass as S5-26; `publish_artifacts` now stamps it on success, so durations are finally recordable |

**Legend.** ✅ *verified live* = proven by a completed run against the real repo. ✅ *(tests green)*
= fixed with guards, not yet exercised live.

**Current position (re-verified 2026-09-17): every Step-4 finding is fixed except S4-8 (companion
logging) and S4-11 (a team decision).** Neither blocks the journey.

*How it got here, since the history is scattered across three passes:* as of run **`9d1b4d32`**
(2026-08-03) four were open — S4-8, S4-10, S4-11 and S4-25. **S4-25 was closed** in the Step-5
second pass as **S5-26**, and **S4-10 was verified fixed on 2026-09-03** by work already merged (see
its entry above; the residue moved to Bugs.xlsx S.No 35).

---

## Step 5 — Gap report: read BEFORE running it (2026-08-03)

Step 4 cost days because its gaps were found by running it. The team asked for a full end-to-end
audit of the gap-report path and the `00_onboarding` agent **before** clicking the button. Twenty
findings; the five below made the run impossible or wrong, and all are fixed.

### What we found

**The run could not have succeeded, and the answer would have been wrong.**

| # | Finding | Where | Fix |
|---|---------|-------|-----|
| **S5-1** | **The agent was never told to write the report.** `submit_gap_report` is built, granted and wired end to end — and the body never mentioned it once. It said the *opposite*: "the platform computes this assessment; your job is to verify and correct it." Nothing pre-generates a report on the agent path, so the agent would have found nothing to verify and `gap.ready` would have stayed false forever. The old test passed on the word "gap_report" appearing anywhere in prose, which is why it survived. | `agents/00_onboarding/agent.md` :93/:158/:162/:193/:200 | Steps 2/5/Completion rewritten around a single `submit_gap_report` call, with the phase keys and status values inline so the shape is never guessed. Plus a runtime backstop: `_PHASE_REQUIRED_ARTIFACTS["onboarding"] = ["gap_report"]`, so a run that skips the call now **fails loudly** instead of completing with nothing |
| **S5-2** | **The body described a runtime that does not exist.** `reads_code=False` for this agent: no worktree, an empty temp working directory, no `codeintel` server, and Read/Grep/Glob/Bash **hard-denied**. The body instructed worktree + `codeintel.*` work in four places — including Step 1f, the *fallback* used when 00c never ran, i.e. the one case with no other source of code facts | `catalog.py:110`, `daemon.py:336`, `claude_driver.py:158-162` vs `agent.md` :29/:68/:71/:74/:132 | **Fixed the body, not the flag** (team review changed my first recommendation). 00c already names `.github/workflows/ci.yml` and `backend/Dockerfile` directly — the body's "intelligence may only give a yes/no flag" premise was stale, and a second independent look at the repo is how two artifacts end up with two different numbers (the S4-23 failure). Code evidence now comes only from 00c's artifacts, and 00c is a **stated prerequisite** |
| **S5-3** | **A perfect run would have been marked FAILED.** The completion check counts artifacts belonging to the run; the report was registered with `run_id=None`, so it counted as no write at all. Under the new assess-only remit this became certain, not merely likely | `onboarding.py:1236`, `state_mcp.py:186`, `activities.py:506-525` | `run_id` threaded through `submit_gap_report` → `tools.submit_gap_report` → `write_gap_report_artifact`. The deterministic REST path still registers unbound (it has no run) |
| **S5-4 / S5-5** | **The gate was inverted.** The gap report — the one artifact built for review — was never published; while everything the agent registered during the run (including requirements/PRD/architecture it was told to transform) **auto-published with no review**, contradicting non-negotiable #5. *Scope corrections from team review: "published" is INTERNAL only, nothing reaches Confluence/Jira; and Step 3 barely fired anyway, since adopted documents are already published → phase Complete → transformation skipped* | `activities.py:316`, `trigger.py:279`, `agent.md:105` | **Team decision (option c) + a real gate.** 00_onboarding now **assesses and reports only** — no lifecycle content, `assumption` artifacts excepted. And it runs **gated**: `auto_approve=False`, Product Owner approves, approval publishes the report. No new gate UI was needed — only the backlog and Phases & Runs hide carriers; `ApprovalViewSet` and the dashboard do not |
| **S5-27** | **Onboarding's own plumbing faked a backlog** — found by the team asking "what if a user has only finished UX Design?". Task Breakdown is judged from work items, and every onboarding/vision carrier is an **epic**. Clicking Index code was enough to make `has_backlog` true; the gap report even corrupted its own input, because its carrier is created before the run starts. Task Breakdown read **Complete** for a project with no backlog, and the resume point skipped a phase: correct advice "break the work down" became "go write code". **A failed run is obvious; a confidently wrong resume point is not** | `onboarding.py:1270/:1275` vs `carrier_q()` at `:1051`; `tools.py:568` | `.exclude(carrier_q())` in both `build_gap_report` and `list_work_items`, so the agent path gets the same clean input. Genuine backlog still counts — guarded by its own test |

**Also fixed — the report could not have been read even if it had been produced:**

| # | Finding | Where | Fix |
|---|---------|-------|-----|
| **S5-6** | **The Gap report screen crashed on any real report.** `evidence` is a list of artifact refs; the type said `string` and the cell rendered it raw → *"Objects are not valid as a React child"*. Every report with evidence. Never caught because the only live-mode test stubbed a **404** | `types.ts:654`, `GapReportScreen.tsx:85` | Typed as `GapEvidence[]`, rendered as a count. Plus the missing test: one live-mode render with a real payload |
| **S5-7** | **Every phase rendered as a raw slug** — the frontend mapped keys against a list keyed `01_ideation` while the API emits `ideation`. Users read "Resume at: task_breakdown". The right label was already in the database and was being dropped on the way out | `onboarding.py:1352`, `GapReportScreen.tsx:16` | Backend serves `label` per phase and `resume_label`; no client keeps a key→label map |
| **S5-8** | **A re-run was completely silent.** Once a report existed, the progress line and the "waiting on you" card became unreachable and the hub had no re-run button. Re-running after adopting more documents is the *normal* case | `OnboardingHub.tsx:568`, `hooks.ts:80` | Ready card and run controls render together; hub gains a "Re-run" button; the screen polls. **And the new gate made this bigger:** `awaiting_gate` counts as "running", so the hub would have said "working…" for as long as approval took — `approval_id` now surfaces a "Waiting for your approval" card that links to the gate |
| **S5-28** | **"Missing" conflated a real gap with "not started yet."** A team that has legitimately reached only UX Design saw six red ✗ rows reading as six failures | `GapReportScreen.tsx:75-120` | Phases past the resume point render as "Not started yet". Blockers are unchanged — that logic was already right |
| **S5-15** | **The tests were locking three of these bugs in.** The migration test asserted `"codeintel" in body`, `"worktree" in body`, `"docstore" in body` — enforcing instructions the runtime cannot honour, so fixing the body would break the test | `test_onboarding_agents_migration.py:141` | Rewritten alongside the body, with the assertions that would have caught S5-1 and S5-14 in the first place |
| **S5-18** | Two hub tests were **stale** — strict `==` on dicts that had gained keys (predicted in the audit, confirmed by running them) | `test_onboarding_rest.py:218` | Assert meaning, not dict equality — the same trap as S4-9 |
| **S5-10 · S5-12 · S5-13 · S5-14** | Body↔runtime drift the §8 sweep never reached this agent: four capability surfaces (`docstore.*` etc.) **no agent can call**; "index into the Knowledge Index", which is not an agent action; **no mention of `ask_human`** (the S4-24 defect, unfixed here); and a promised gate that did not open | `agent.md` :28/:63/:105/:189/:200 | All corrected. The `ask_human` rule is **weighted differently from 00c**: that agent was told to verify from the code first because it had Read/Grep — this one has no file tools, so the registry is the first route and asking carries far more of the load |
| **S5-11** | The five intelligence artifacts were **not guaranteed** to reach the agent — no declared inputs, so the manifest was just the newest 12 artifacts of any type, and on a real project they can be crowded out | `catalog.py:110` | `needs_artifacts` pins all five into the manifest's required tier |

### Second pass — the remainder, incl. everything originally deferred (team: "fix everything")

| # | Finding | Where | Fix |
|---|---------|-------|-----|
| **S5-9** | Agent vs deterministic mode was **invisible** — the two are different products (minutes of reasoning on your machine vs an instant mechanical count) and the screen said neither | `OnboardingHub.tsx`, `GapReportScreen.tsx` | The hub names which path ran; the report says whether Implementation/Code Review were assessed from measured code or reported unjudged |
| **S5-19** | **The report dead-ended** — blockers were display-only while the report's own text said "generate it via its phase agent", with nothing to click; and nothing linked to the report document | `GapReportScreen.tsx`, `OnboardingHub.tsx`, `onboarding.py` (hub) | Each blocker now says what resolves it and links there — **and two of them don't route to a phase agent at all**: Implementation and Code Review are resolved by **Index code**, because you cannot author your way out of a missing codebase. "Open the report document" added on both screens |
| **S5-20** | Agent evidence was **unvalidated**; elements could be anything | `onboarding.py` `_clean_evidence` | Coerced to the exact ref shape the UI expects; a bare id string is accepted as shorthand, anything without a usable id is dropped |
| **S5-20b** | 🔴 **Found while writing the end-to-end test, not by review: one invented artifact id destroyed the whole report.** Ids are exactly what a model reconstructs from memory, and a non-UUID raised straight out of `add_trace_edge` — Django validates the field before any lookup — so a single bad citation threw away the entire assessment and the user saw nothing | `onboarding.py` `_resolvable_artifact_ids` | Evidence ids are resolved first; only real artifacts **of this project** are linked, and the report survives. Losing one provenance link is a small visible loss; losing the assessment is not |
| **S5-21** | `submit_gap_report` had **no project-id fallback**, unlike its neighbours — an unset binding posted an empty string | `state_mcp.py:186` | `or None`, matching `get_context`/`list_artifacts` |
| **S5-22** | **Dead branch** in the assessor: `weak` was a strict subset of `strong`, so Implementation was never once assessed `partial` | `onboarding.py` `_assess_phase` | Removed rather than switched on — making Implementation permanently partial would park every brownfield resume point on it forever. Whether code matches the docs is Code Review's question |
| **S5-23** | `_LIFECYCLE` mapped Implementation to the type **`code`, which nothing anywhere registers** — the entry was inert and the phase's evidence list was always empty | `onboarding.py:939` | Mapped to `codebase_intelligence`, the artifact actually measured from the repo, so the assessment cites what it relied on. Adoption stays blocked for the phase — a running codebase is proven from git, never an uploaded file |
| **S5-24** | Re-runs **replay the first run's answers**, so a scope question is asked once, ever — and an answer about scope goes stale the moment new documents are adopted | `composer.py` `_render_clarifications` | Answers are still replayed (that continuity is the point), but the agent is told they may be from an earlier run and to ask again when the evidence in front of it contradicts them |
| **S5-25** | A **truncated run reported as a clean success.** The companion sends "engine ended abnormally (error_max_turns)" precisely so the platform can say so — and it was recorded **only when the body was also empty**, so a run cut off part-way through, with half its work done, looked complete | `activities.py` | The message is recorded whenever the companion sends one. A partial assessment that looks complete is the dangerous shape — nothing downstream can tell it apart |
| **S5-26** | **Every successful run had `ended_at = NULL`** (S4-25) — only failure paths stamped it, so no duration could be shown anywhere. Also the content-loss guard failed onboarding runs with a message written for document vision | `activities.py` | `ended_at` stamped on completion; the guard's message made phase-neutral. *The vision-worded guard no longer reaches the gap report at all — it only runs on auto-apply runs, and the gap report is now gated* |

**Also closed:** the stale comment at `daemon.py:341` that named `00_onboarding` as a `codeintel`
consumer — doubly wrong now, and exactly the kind of note that sent this audit down the wrong path
in the first place. And the last two test gaps: the **409** branch (a second click while a run is
live) and the **full MCP chain** end to end — companion tool → runner endpoint → allowlist →
writer → what the UI reads. That end-to-end test is what caught S5-20b.

---

## Step 5 — LIVE RESULT: run `448b8d21` (2026-08-03) ✅

Ran end to end on the real project, on the team's companion, and was approved. **Step 5 is closed.**

| | |
|---|---|
| Run | `448b8d21` · agent `00_onboarding` · **completed** · 23.5 min · cost 1.38 (display-only) |
| Gate | `fd18a0a1` · **approved** by product_owner · 12:06:15 |
| Artifacts | `gap_report` (**published on approval**), `assumption`, the platform's phase blob — **and nothing else** |
| Trace edges | 15, all resolved |
| Verdict | **Resume at Implementation**; Implementation + Code Review *Partial*, ten phases *Complete*, no blockers |

**Verified live by this run:** S5-1 (the agent called `submit_gap_report` — the blocker that made the
run impossible) · S5-3 (report bound to its run; unbound it would have failed) · S5-4/S5-5 (real
Product Owner gate; approval is what published the report) · **option (c)** (three artifacts, *zero*
lifecycle content — nothing rewritten and auto-published) · S5-7 (labels, not slugs) · S5-11 (the
manifest **was** truncated and the five pinned intelligence artifacts survived — the exact case the
fix exists for) · S5-20b (15 edges resolved, no crash) · S5-26 (**`ended_at` stamped** — the first
successful run in this system ever to record when it finished) · S5-28 (the new intel line).

**Note on the agent's answer.** The deterministic assessor would have said *"resume at Code Review,
Code Review missing"* — it has no `code_review` artifact type to find. The agent read the
intelligence artifacts and judged both Implementation and Code Review **Partial**: code exists, not
fully verified against the docs. That is reasoning rather than row-counting, and it is the more
defensible answer — but it *is* a judgement, and it is now the resume point.

### Four defects that only live testing found — three of them caused by the gate change

Review did not catch these. Flipping `auto_approve` off broke assumptions that had held only
because every carrier run until now happened to be headless.

| # | Defect | Cause | Status |
|---|--------|-------|--------|
| **S5-29** | 🔴 **The gate was invisible.** Sidebar badge said "Gates 1"; the page said "No gates need you" | The Gates screen fetched every approval and kept only those whose work item appeared in the **work-item list — which hides carriers by design**. I checked `ApprovalViewSet` had no carrier filter and concluded the gate was reachable; **I never checked what the client did with the response.** A gate nobody can reach is worse than no gate: the run waits forever | ✅ FIXED (tests green) — project scoping moved server-side (`?project=`), `work_item_title` added so a carrier gate names itself |
| **S5-30** | 🟠 Phase artifact titled **"Onboarding — Onboarding — project assessment"** | The phase prefix was suppressed by `auto_approve`, which only ever worked by coincidence. The stutter landed on the document a reviewer opens at the gate | ✅ FIXED (tests green) — keyed off **carrier**-ness, which was always the real condition (also protects the vision case) |
| **S5-31** | 🟠 The gap report registered with **`title=''`** — no name in any list | The platform wasn't holding itself to the "always pass a title" rule it gives agents | ✅ FIXED (tests green) — "Gap Report — resume at &lt;phase&gt;" |
| **S5-32** | 🟡 Right-hand card **clipped mid-word** ("Open the report…") | `gate-panel__actions` is `display:flex` with **no `flex-wrap`**; my second action link overflowed the narrow card | ✅ FIXED (tests green) — wraps now; shared CSS, so it fixes the same clipping wherever else a card is narrow |

**S5-30/31/32 are fixed in code but were NOT in the running containers for run `448b8d21`** — its
artifacts still carry the old titles. The next gap-report run confirms them.

---

## Status board — brownfield onboarding, as of 2026-08-03

The team declared the brownfield onboarding journey **logically and accurately closed** after run
`448b8d21`. This is the honest ledger behind that.

### ✅ Fixed AND verified live
Steps 1–4 (upload · adopt · register · Index code) and **Step 5 (Gap report)** end to end, including
the gate and publish. Part A lossless capture. S4-1…S4-7, S4-12…S4-24, S4-26. S5-1, S5-3, S5-4/5,
option (c), S5-7, S5-11, S5-20b, S5-26, S5-28.

### ✅ Fixed, tests green, NOT yet exercised live
Not a doubt about the fix — simply no run has hit the path yet. Each is confirmed by the next
gap-report run.

| # | What | How it gets confirmed |
|---|------|----------------------|
| S5-29 | Gate visible on the Gates **list** | The gate *was* reached and approved after the restart; whether via the list or the hub's direct link is not distinguishable from the DB, so this stays "tests green" |
| S5-30 · S5-31 | Artifact titles (stutter · untitled report) | Next run's artifact titles |
| S5-32 | Card no longer clips | Next look at the Gap report page |
| S5-27 | Carrier epics don't fake a backlog | Needs a project **without** a real backlog — this one has 68 genuine items, so it reads Complete either way |
| S5-13 | `ask_human` from `00_onboarding` | The agent asked nothing this run. **The clarification route has still never fired from any onboarding agent** (same gap as S4-24) |
| S5-9 · S5-19 · S5-22 · S5-23 · S5-24 · S5-25 | Mode banner · actionable blockers · assessor branch · evidence type · stale-answer note · truncation recorded | This run had no blockers, no truncation and no replayed answers, so none rendered |

### 🔲 OPEN — decisions for the team (not defects)
- ~~**S4-10** — "Connect Machine" revokes the live companion's token.~~ ✅ Verified fixed
  2026-09-03: the mechanism this described cannot occur in the current code (see the S4-10 entry).
  The credential-lifecycle residue it raised is now tracked on Bugs.xlsx S.No 35.
- **S4-11** — agents can see run-record artifacts the UI hides.

### 🔲 OPEN — observability / hardening
- **S4-8** — the companion logs **nothing** during a healthy run. Redirecting output to a file
  captures failures only. This is why every diagnosis this session went through the database.
- **S5-25b** — a run that exceeds the 2 h timeout goes **STALLED and waits indefinitely** for an
  `abandon_run` that has **no UI surface** on a hidden carrier. The truncation half is fixed; this
  half is not.
- **NEW · runner token in the process command line.** The companion is launched with
  `--token <secret>`, so any process listing on that machine reveals it. An env var or a token file
  would avoid it. Not urgent; worth doing before anything runs on a shared machine.

### 🔲 TO BE DONE — next work, not blockers
- **Step 6 — Resume.** Untested. The report says resume at Implementation; nobody has yet resumed
  the pipeline from a gap report.
- **`test_api.py:317`** — an 8th instance of the `b97f804` upload/adopt change (reads
  `artifact_ids[0]` from the upload response, which no longer registers an artifact). **Pre-existing
  and proven so by stashing**; it will block a clean merge.
- **AGENT_MIGRATION_SPEC §8 sweep** over the *other* migrated agents. Two agents have now been found
  with bodies describing tools they don't have (00c, 00_onboarding). The rest were written the same
  way; assume the same until checked.
- **Figma import** — still untested (no account).

### The lesson worth keeping
Twenty findings came from reading the code before running it, and that is what made Step 5 work on
the first attempt instead of costing days like Step 4. But **four more came only from running it,
and three of those were caused by my own fix** — flipping one flag broke assumptions that held only
by coincidence. The audit was necessary and was not sufficient. Both passes were needed.

**Still owed:** the AGENT_MIGRATION_SPEC §8 reference sweep over the **other** migrated agents.
S4-24 raised its priority: `00c`'s body never mentioned `ask_human` at all, and the other agents
were written the same way, so the same gap is likely to repeat.

---

## Gate rejection → "Request changes" (2026-08-04) — greenfield AND brownfield

Two issues the team raised about every SDLC phase, not just onboarding. Recon first, then built.

### Issue 1 — what a rejection did today

Traced end to end. The rejection was recorded honestly and then went nowhere.

| Layer | What happened |
|---|---|
| DB | `Approval` got `decision/approver/comment/decided_at`; `Run.status=rejected`; WorkItem → `in_progress`; two events (`gate.decided`, `run.rejected`) |
| SoR | Nothing published — `publish_artifacts` is inside the approved branch only. Correct |
| UI | **Nothing at all.** The mutation only invalidated queries; the gate silently vanished into a history tab with **no comment column** |
| Next run | **Blind.** Grepping `composer.py` for `approval`/`comment`/`feedback`/`rejected` returned **zero matches** |

Three defects fell out of that trace:

| # | Defect | Fix |
|---|---|---|
| **G-1** | **`Run.ended_at` was never stamped on rejection.** The approve path and the fail path both stamp it; rejection was the last terminal path that did not, so a rejected run's duration was permanently unknowable (same family as S4-25) | `reject_run_core` stamps it |
| **G-2** | **Rejected drafts were served downstream as authoritative.** `get_context`'s artifact query had **no status filter**, so the draft the reviewer rejected stayed the newest artifact of its type and was handed to every later phase. The reviewer said no and the platform kept passing it on | New `Artifact.Status.SUPERSEDED`, set on the rejected run's drafts and excluded from `get_context`. Not deleted — the revision cites them by id |
| **G-3** | **The reviewer's comment was write-only** — stored, event-logged, signalled into the workflow, and rendered nowhere. Two other Reject buttons (`WorkItemEpic`, `WorkItemTask`) sent **no comment field at all** | Comment column added to the decided-gate history; those two buttons now route to the gate instead of deciding blind |

### Issue 2 — no way to say what to change

`trigger_phase` took no free-text parameter, `AgentRunInput` had no such field, and
`TriggerSerializer` silently dropped unknown keys. Nothing carried human direction into a re-run.

**But the mechanism already existed on the build path.** `dispatch_remediation_core` folds a written
brief into agent 07's manifest and re-dispatches on the same run/branch/PR. Machine-generated, no UI.
So this gave an existing mechanism a human author and extended it to the planning path.

**Team decisions (locked):** three actions (Approve · Request changes · Reject) · the agent sees the
**whole review conversation**, not just the last note · rejected drafts marked superseded · **all**
phase families.

| Phase family | What "Request changes" does |
|---|---|
| Planning (requirements, PRD, architecture, UX design, task breakdown, testing, deployment, gap report) | Rejects the run, then starts a **fresh run** carrying the accumulated history |
| Scan (`10_security`, `reads_code=True`) | Same code path — no extra work |
| Build (`07_implementation`, `09b_test_automation`, `11_cicd`) | **Re-dispatches in place** — same run, same branch, same PR, preview kept |

`00c` Index code and `00e` document vision are out of scope by construction: they run headless
(`auto_approve=True`) and open no gate, so there is nothing to reject.

### Three things the design got right only after they were challenged

1. **The build path must NOT start a new build.** My first design called `trigger_build`. At the
   merge gate the branch is pushed and the draft PR is open, so that would have cut a **second
   branch and a second PR** and orphaned the first (`reject_build_core` never closes it) — and torn
   down the preview the reviewer was looking at. It now re-dispatches in place and re-enters the
   full PR → 07↔08 review → gate block, because *a change nobody reviewed is exactly what the merge
   gate exists to prevent*.
2. **The re-trigger must run from the WORKFLOW, not the API.** `decide_gate` returns 200 as soon as
   it has signalled, while the run is still `AWAITING_GATE` — which **is** in
   `_ACTIVE_RUN_STATUSES` — so a REST-layer re-trigger would hit `_guard_no_active_run` and 409.
   Not a narrow race: the normal case. Running after `reject_run` makes Temporal guarantee the order.
3. **The history lives on `Run.inputs`, not the Temporal payload.** `compose_manifest_core` is
   duck-typed and also receives `BuildInput`; reading a new attribute off `inp` would have raised
   `AttributeError` on **every build dispatch**. Reading from the Run row also keeps a
   grows-every-round list out of Temporal, leaving **one boolean** as the only payload change.

### Also true now that was false before

`CriteriaGate` claimed *"Rejected — sent back for rework"* and *"A remediation note was sent to the
run"* on **every** rejection. Neither was true — nothing was sent and nothing re-ran. That copy is
now shown only on the revise branch, where it is accurate.

### Verification

Backend, run per-file (the full suite SIGKILLs): 47 (develop's guards) · 45 (build) · 64 (gate/rules/
workflow) · 117 (onboarding/composer/activities) · 134 (journeys + dispatch). Frontend **241 passed**,
incl. all 97 greenfield. `tsc` clean. Lint unchanged (9 before, 9 after — all pre-existing).
`test_users_roles.py::test_role_coverage_hard_block_when_no_holder_and_no_admin` fails — **pre-existing,
proven by stashing**.

New tests worth naming, because each guards a failure that would otherwise be silent: re-trigger
idempotency under Temporal replay (a second pass must not create a second run) · the 409-race
regression · `compose_manifest_core` with a build-shaped input · a **three-deep** revision chain
(fails if the history is ever trimmed back to the last round) · budget truncation dropping whole
oldest rounds while the current direction survives intact.

### Live verification — round 1 (2026-08-05)

Tenant `d6a89745` · project **People Desk** · work item **WI-1** · greenfield planning path, no repo.
Reviewer direction: *"I want to build a SaaS based application where anyone can use my platform for
their HR management instead of just limiting it to my internal company tool."*

Worker and API restarted first (worker before API, as the payload change requires).

| # | Expected | Observed | Status |
|---|---|---|---|
| 1 | Old run rejected, `ended_at` stamped (G-1) | `75adb0ec` → `rejected`, `ended_at` 11:16:36 | ✅ |
| 2 | Rejected drafts superseded (G-2) | All **7** ideation artifacts `draft` → `superseded` | ✅ |
| 3 | Revision starts on the same companion | `5b4a1bab` created 11:16:37 — 1s later — `revision_of=75adb0ec`, enrollment `1327cdae` | ✅ |
| 4 | No 409 from the re-trigger race | `run.revision_requested` logged, no guard failure | ✅ |
| 5 | Direction stored verbatim + prior artifacts named by id | `review_history[0]` holds the text unaltered and all 7 artifact ids/types/titles/versions | ✅ |
| 6 | `# Reviewer Direction` above `# Current Work Item` | Section order: Project · Important Context · **Reviewer Direction** · Current Work Item · … | ✅ |
| 7 | Direction survives the budget intact | `manifest.truncated` fired for `Answered Clarifications` + `Retrieved Knowledge` — **not** Reviewer Direction | ✅ |
| 8 | The agent acts on the direction | Before writing anything it opened a clarification round with **four new ids** — `saas_target_segment`, `saas_pricing_model`, `saas_geographic_scope`, `saas_hosting_model`. None existed in round 1: it derived the questions the pivot creates | ✅ |

(8) is the substantive result. The agent did not merely echo the note — it recognised that "anyone
can use my platform" leaves customer segment, pricing, geography and hosting undefined, none of which
an internal tool needed. It also incidentally confirms the WP1 dedup fix in the direction that
worried us most: a genuinely **different** question set was let through rather than suppressed as a
repeat of round 1. One `clarification.asked`, one `clarification.answered`, no duplicate gate.

**Still NOT verified live:**

* **Round 2 — the decisive test for decision (2).** Reject again with *different* direction and
  confirm round 3's manifest carries **both** notes and names both rounds' superseded artifacts.
  Round 1 alone cannot show the history accumulating.
* The **decided-gate history** rendering both comments (G-3) — not yet opened after the rejection.
* The **build merge-gate** path in full: same PR, same branch, preview kept, gate reopened.

### G-4 · Artifact status badge showed "Draft" for every status it did not recognise

Found by the team on the Artifacts screen immediately after the rejection: all 7 artifacts read
**Draft** while the database had them `superseded`.

`ArtifactsRegistry.statusBadge` knew only `published` and `pending_gate` and returned a hardcoded
`<Badge>Draft</Badge>` for anything else. `Artifact.Status` has five members, so `staged`,
**`approved`** and `superseded` all rendered as drafts — an approved artifact has been displaying as
a draft for as long as the screen has existed. Not caused by this feature; `superseded` is simply the
first new status to see real use, which is what exposed it.

Fixed in a new `features/observability/artifactStatus.tsx`, shared by the registry list and the
preview screen so a status cannot mean one thing on one screen and another elsewhere. The fallback
now humanizes the raw token instead of naming a status, so a future addition renders honestly rather
than silently claiming to be a draft. Verified live: all 7 rows read **Superseded**.

Worth noting the data was never wrong and the API never dropped it — the Status filter dropdown,
which builds its options from the values actually present in the response, listed "Superseded"
correctly the whole time. Only the badge lied.
