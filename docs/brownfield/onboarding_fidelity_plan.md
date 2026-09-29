# Brownfield Onboarding — Lossless Capture Plan (Part A + Part B)

**Status (updated 2026-09-17): BUILT — both parts are in the tree and merged.** Part A's
high-fidelity extraction and page-image preservation are live (`mcp_platform_state/tools.py`,
`get_page_images` and the page-image window); Part B shipped as the `00e_document_vision` agent
(`agents/00e_document_vision/agent.md`, catalogued at
`backend/apps/registry/catalog.py:159`). The work is no longer on its own branch — it is merged.

*The original header said "plan awaiting approval — no code yet", which stopped being true when the
first slice landed. The plan text below is kept as written: it is the specification the build
followed, and the "After Part A / After Part B" notes are what it promised, not what is still owed.*

## Why (the team's two goals)

1. **Lossless capture for the agents.** Whatever the user uploads — text, tables, diagrams, images, screenshots — must reach the onboarding agent (and every resumed downstream phase) *in full*, so the "where do we resume?" decision is based on everything, not a lossy skeleton.
2. **Visible trust for the user.** The user must be able to *see* exactly what they uploaded being captured and adopted correctly — so they trust the platform.

## What happens today (verified in code + against real files)

- **The original bytes are preserved** in S3 at `onboarding/<tenant>/<project>/<doc>/source/<filename>` (`ingest_source_document` → `store.put(src_key, content)`) — but it's a **write-only vault**:
  - The user can't see it — `SourceDocumentSerializer` exposes no URL/viewer; the preview reads only the extracted markdown.
  - The agent can't see it — `get_artifact_body` returns the extracted markdown (`artifact.s3_key`), never the original.
- **Extraction is lossy** (`backend/integrations/extract.py`): `pypdf` (text only), `python-docx` (paragraphs + tables, drops images), stdlib HTML (drops `<img>`), `openpyxl` (fine).
  - PDF tables → flattened run-on text · diagrams/vector → gone · images → gone · **image-only/scanned PDF → empty**.
  - DOCX embedded images → dropped · HTML `<img>` → dropped.
- **Net:** anything pictorial, and PDF table structure, is invisible to the user, the adopt gate, the gap agent, and downstream phases. Functionally lost.
- **Backend toolbox is minimal:** only `pypdf` + `python-docx` + `openpyxl`. No OCR, no PDF rasterizer, no table lib, no image handling.

## Engine reality (corrected, verified)

SDLC phases — including the onboarding agents — run on the **companion**, which **forces subscription-only auth and drops the API key at runtime**:
- `runner/companion/daemon.py::ensure_local_engine_auth` pops `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` (daemon.py:550–551), refuses to run on a stored API key, and requires a Claude Code **subscription** OAuth login. Re-asserted **before every run** (daemon.py:440).
- `cost_usd` is a **display-only** "subscription-equivalent" figure (daemon.py:261–264), not an API bill.
- So vision (Part B) runs on the **user's Claude Code subscription** (multimodal included) — no per-token API cost. The constraint is subscription **usage limits + latency**, handled by sane image sizing + the on-adopt trigger.

## Locked decisions

- **Vision engine:** Claude Vision (the platform's own multimodal engine — the same capability that reads a pasted screenshot).
- **When vision runs:** automatically **on adopt** (only for docs the human keeps).
- **Sequencing:** **Part A first** (no engine change, fast, low-risk), then **Part B**.
- **Engine/auth:** user's **Claude Code subscription via the companion** (API key dropped at runtime); vision guarded by image-sizing + on-adopt volume.
- **BF-BUG-3b/3c re-opened** and folded into this plan (the earlier "note/limitation" is replaced by real preservation).

---

## Part A — Capture everything + let the user see it (no engine change)

Fast, low-risk, one new pure-wheel dependency (`pymupdf`). Fixes most of the loss and delivers Goal 2 immediately.

### A1 — Higher-fidelity extraction
- **`backend/integrations/extract.py`:** add `pymupdf` (fitz).
  - PDF: fitz text (better layout, keep the markdown hard-break structure) + `page.find_tables()` → real markdown tables + collect embedded raster images per page (xref).
  - DOCX: keep paragraphs/tables; also pull embedded images via `document.part.rels` (image relationships). No new dependency.
  - HTML: keep `<img>` references (src / data-URI).
  - `extract()` returns a richer result: `(title, markdown_body, images: [{name, bytes, mime, page}])` (today it returns `(title, body)`), so the ingest layer can persist images.
- **Tests:** a PDF with a table → markdown table in body; a DOCX with an image → image captured; existing text/txt/html/xlsx round-trips still pass.

### A2 — Persist page + image renders as attached views
- **`backend/integrations/onboarding.py::ingest_source_document`:** after extract,
  - render each PDF page to a PNG (fitz, sane DPI) and keep every embedded image from A1;
  - store each PNG in S3 under the doc's prefix;
  - record them on the artifact `external_ref` as `page_images: [{name, s3_key, page, mime}]` (the "one artifact → many views" idea used by wireframe `states`).
- **Note:** wireframe `states` are read as UTF-8 text; images are binary, so delivery is a **binary endpoint** (A3), not the text body path. We reuse the *concept*, not the text reader.
- **Tests:** ingest a PDF → the artifact carries N page-image pointers in S3.

### A3 — Show the original + page images (the trust piece)
- **Backend:** a gated read-through endpoint to stream the **original file** and each **page image** from S3 (auth = `IsAuthenticatedMember`, tenant-scoped). `SourceDocumentSerializer` gains safe references (URLs to the new endpoint), not raw S3 keys.
- **Frontend (`SourceDocuments.tsx` / preview):** render the original (PDF inline / image) and the page thumbnails next to the extracted text, so the user sees exactly what they uploaded.
- **Tests:** endpoint returns bytes only for an authenticated member of the tenant (403 otherwise); frontend renders the viewer.

### A4 — Honest status (derived — no DB migration)
- **`backend/integrations/onboarding.py`:** derive an extraction-fidelity marker from what came out — e.g. `text` (real text extracted), `images_only` (no text, page images captured → needs AI read), `empty` — and record it in `provenance`/`external_ref` (derived, so **no model migration**).
- **Frontend:** the row badge shows the truth — *Text extracted · Images saved · Needs AI read* — instead of a blanket "Extracted".
- **Gap counting:** an `images_only`/`empty` doc is not counted as full phase evidence until Part B transcribes it (so the gap agent doesn't over-count).
- **Tests:** an image-only PDF → status "Needs AI read", not "Extracted".

**After Part A:** text + tables + pictures are captured and *visible*; nothing pictorial is silently dropped; status tells the truth. Goal 2 met; Goal 1 met for text-based files.

---

## Part B — The vision pipe (after Part A lands)

Makes diagrams / screenshots / wireframes fully meaningful to the agents. Runs on the companion subscription.

- **B0 — Capability check (first, small):** confirm the companion's Claude Code (subscription, via the Agent SDK) accepts **image content blocks** — via a tool result or the prompt. This is the one unknown; a spike, not a build. Picks the pipe (tool-result vs prompt-attachment).
  - **✅ DONE — verified live on the subscription CLI (no API key).** A throwaway spike stood up a stdio FastMCP server (the exact shape of `state_mcp.py`) whose one tool returns a PNG via FastMCP's `Image` helper → MCP `ImageContent`. Driven through `claude_agent_sdk.query` with the on-PATH `claude` CLI and `ANTHROPIC_API_KEY` unset, the model called the tool, received the image, and read back the secret phrase painted into it exactly. **Verdict: the MCP tool-result image pipe reaches the model on the subscription path.**
  - **Pipe chosen: MCP tool-result** (agent pulls page images on demand from a platform-state tool). It's the least invasive, matches how the onboarding agent already fetches bodies, and honours rule #7 (through the driver's MCP surface, never the API). Stack support is native: `mcp.types.ImageContent` + `mcp.server.fastmcp.Image` (pinned mcp), and the SDK forwards it.
  - **Fallback available if ever needed:** prompt-attachment — `query(prompt=...)` accepts `str | AsyncIterable[dict]`, so image content blocks can ride the initial user message. Not needed; tool-result won.
- **B1 — Open the image pipe:** let the `ExecutionDriver` / tool surface deliver the S3 page-images to the engine as image blocks (the same shape that reaches Claude here). Through the driver, never the API directly (rule #7).
  - **✅ DONE.** New platform-state tool **`get_page_images(artifact_id, start=0)`** on both MCP surfaces — the companion `runner/companion/state_mcp.py` (the real onboarding path, HTTP-proxied) and the backend in-process `mcp_platform_state/server.py` (parity). It reads a document's `external_ref.page_images` pointers, streams their bytes from the object store (never copied onto the row — #1/#3), and returns them as **FastMCP `Image` blocks** preceded by a one-line text summary. Shared logic lives in `mcp_platform_state/tools.py` (`get_page_images` = DB read; `_build_page_image_window` = pure fetch/downscale/paginate); the companion HTTP route is allow-listed in `backend/api/runner_views.py`.
  - **Guards baked in:** paginated **4 images per call** with `next_start` (read a many-page upload page-by-page, like `get_artifact_body`'s one-state-per-call), and every image **downscaled to ≤1568px long-edge** (`downscale_image_for_vision`, Pillow/LANCZOS) — Claude downsamples larger anyway, so this only trims payload/tokens.
  - **Verified:** 7 unit tests (`backend/tests/test_page_images.py`: downscale, pagination, missing-object skip, base64→`Image` round-trip) + a live build of the real companion server returning `[TextContent(summary), ImageContent(png)]` — the exact shape the B0 spike proved the model reads. DB read verified live (backend uses the cloud DB).
- **B2 — Document-vision step (on adopt):** a small companion agent (same pattern as `00c`) reads the page images and writes **faithful markdown** — transcribes screenshots, rebuilds tables, renders diagrams as mermaid/description, flags inferences. This becomes the artifact body the gap agent and downstream phases read. Guards: sane image resolution + on-adopt volume.
  - **Decisions (team, confirmed):** new **`00e_document_vision`** catalog agent (reuse the run machinery) · **auto-apply** the transcription (no second human gate) · runs on **every adopted document**.
  - **Concrete design (recon complete):**
    - **Agent** `00e_document_vision` — phase_label `document_vision`, gate_role `product_owner`, **not** `reads_code` (it reads page images over MCP, no worktree). Native (no legacy source) → new `native` catalog marker so the legacy-file test skips it; body at `agents/00e_document_vision/agent.md`. Seeded ADDITIVELY (`seed_agent_specs` is idempotent — one new row, nothing else touched).
    - **Tool access:** add `get_page_images` to the companion `BUILD_STATE_TOOLS` (→ `PLAN_ALLOWED_TOOLS`) and server `PLATFORM_TOOLS` (both additive; permitted by the PG12 allowlist).
    - **Isolation:** a per-document carrier WorkItem (`external_ref.source="vision_carrier"`, keyed by `source_document_id` + the target `artifact_id`), so concurrent adopts never collide on the shared onboarding carrier and the completion `done`-transition is harmless.
    - **Auto-apply:** the agent re-registers the target artifact as a **new version** (same phase/type/title) with the faithful body → `get_context`'s required tier serves the newest version, so downstream reads the faithful text automatically. The run skips the human gate via a **default-off `auto_approve` flag on `AgentRunInput`**: a single, localized branch in `AgentRunWorkflow` (auto_approve → publish + done, no `open_gate`); every existing phase keeps `auto_approve=False` → byte-identical behaviour. `verify_writes` for an auto_approve run requires "≥1 non-empty artifact this run" instead of a phase-typed one.
  - **B3 trigger:** `adopt_source_document`, after publishing, best-effort enqueues one 00e run per adopted document (no companion enrolled → skip silently; the doc stays adopted).
  - **Risk surface (why this is the caution checkpoint):** touches two crown-jewel pieces — the deterministic `AgentRunWorkflow` (one default-off branch) and `verify_writes` (one auto_approve branch) — plus a new native agent + additive seed. Each change is small, default-preserving, and unit-tested; no existing phase's path changes.
  - **✅ DONE (committed `08a43e3`, `d507b99`, `93795af`).** Implemented exactly as designed, in three commits: (1) 00e agent — catalog entry + `native` marker + agent body + `get_page_images` on both tool allow-lists; (2) per-document `vision_carrier` work item (hidden from the backlog list — the pre-existing `onboarding_carrier` leak is now hidden too) + the auto-apply path (`auto_approve` flag on `AgentRunInput`, default-off branches in `AgentRunWorkflow` and `verify_writes`, `trigger_vision`); (3) the adopt hook (`_maybe_trigger_vision`, best-effort, only when the artifact has `page_images`) + a 6-test suite (`backend/tests/test_document_vision.py`).
  - **Decision refinement (team, confirmed):** carriers are **hidden from the backlog** (pure plumbing, no user content). Vision fires on every adopted doc **that has page images to read** (a pure-text upload with zero images is skipped — vision would be a no-op).
  - **Enablement for live test:** the `00e_document_vision` AgentSpec must be **seeded additively** for the test tenant (idempotent — adds one row), and the **companion restarted** (picks up `get_page_images` + the new agent body). Backend + worker already restarted with the new code; with no seed, adoption degrades gracefully (vision skipped, doc still adopted).
- **B3 — Trigger:** run it automatically on adopt (per the locked decision).

**After Part B:** an image-only wireframe/scanned PDF arrives as described screens + reconstructed content — not a "no text" note. The agents receive everything.

---

## Reuse ledger (why this is surgical)

- **REUSE:** the "one artifact → many views" concept from wireframe `states`; the companion + gate + register machinery; the `00c` agent pattern for B2; the existing preview read-through; the S3 store already holding the originals.
- **NEW (contained):** `pymupdf` extraction + image pull (A1); page-image persistence (A2); a binary read-through endpoint + viewer (A3); a derived fidelity marker (A4); the driver image-block path + document-vision agent (B1/B2).

## Risks

- **A1 signature change** (`extract()` returns images) ripples into `ingest_source_document` — contained, covered by tests.
- **Image delivery is binary** — must not go through the UTF-8 text body path (A2/A3 handle this explicitly).
- **B0 is the real unknown** — if the SDK can't pass image blocks on the subscription path, Part B pivots to the prompt-attachment route; **Part A stands on its own regardless.**
- **Subscription usage** — vision consumes the user's Claude Code usage; mitigated by image sizing + on-adopt.

## Verification

- Targeted unit tests per slice (never the full suite).
- Live E2E on `SpendLog-Brownfield-Testing`: the wireframes PDF is the proof — after Part A it's viewable with page images and honestly statused; after Part B it comes through as real, agent-readable content.
- `docs/brownfield/Bugs-fix.md` BF-BUG-3b/3c reopened; marked fixed only when verified live.

## Rollout

Part A: **A1 → (pause for review) → A2 → A3 → A4**. Then Part B: **B0 → B1 → B2 → B3**. One slice per commit, tested, on the feature branch; merge to develop only when green.
