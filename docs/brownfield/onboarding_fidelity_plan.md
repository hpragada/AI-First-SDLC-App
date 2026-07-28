# Brownfield Onboarding — Lossless Capture Plan (Part A + Part B)

**Status:** plan awaiting approval — no code yet. Everything lands on `brownfield-agent-onboarding`, one slice at a time, tested each step.

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
- **B2 — Document-vision step (on adopt):** a small companion agent (same pattern as `00c`) reads the page images and writes **faithful markdown** — transcribes screenshots, rebuilds tables, renders diagrams as mermaid/description, flags inferences. This becomes the artifact body the gap agent and downstream phases read. Gated like any artifact. Guards: sane image resolution + on-adopt volume.
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
