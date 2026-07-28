# Brownfield Onboarding — Live E2E Bug-Fix Log

Bugs found by the team during the **live end-to-end test** of the new agent-driven brownfield flow (branch `brownfield-agent-onboarding`), with **root cause verified in code + against the real generated test material**, and the **surgical fix**. We mark each **✅ FIXED** once verified together.

- **Test tenant:** `test-brown@edvensoft.com` (workspace *Edvensoft-brown*) · **Project:** `SpendLog-Brownfield-Testing`
- **Branch:** all fixes land on `brownfield-agent-onboarding` (develop stays clean; merge when green).
- **Test material:** `…/EdvenSDLC-Project/Brownfield_Test_Material/` (the 11 SpendLog docs).

## Legend
🔲 OPEN · 🔧 FIX WRITTEN (awaiting live re-test) · ✅ FIXED (verified) · 🐞 regressed

---

## BF-BUG-1 · 🔧 Raw MIME string wraps and misaligns the "Extracted" badge
- **Symptom:** Under each document name the raw content-type is shown (`application/pdf`, and for DOCX the 70-char `application/vnd.openxmlformats-officedocument.wordprocessingml.document`). The long ones wrap to two lines and push the status badge out of alignment.
- **Root cause:** `frontend/src/features/observability/SourceDocuments.tsx:213` renders `{doc.mime}` verbatim in `artifact-row__meta`.
- **Surgical fix:** Add a `fileKindLabel(mime, filename)` helper → a short, human label (**PDF**, **Word (DOCX)**, **Excel (XLSX)**, **Text**, **HTML**). Render that instead of the raw MIME. Frontend-only, cosmetic.
- **Verify:** every row shows a short type; badge stays aligned for DOCX and PDF alike.

## BF-BUG-2 · 🔧 Re-uploading the same file duplicates it (source list + artifacts)
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

## Status summary
| ID | Title | Status |
|----|-------|--------|
| BF-BUG-1 | MIME label wraps / misaligns badge | 🔧 FIX WRITTEN (unit-verified) |
| BF-BUG-2 | Re-upload duplicates | 🔧 FIX WRITTEN (awaiting live re-test) |
| BF-BUG-3a | PDF wall-of-text + Page N noise | 🔧 FIX WRITTEN (real-file verified) |
| BF-BUG-3b | Image-only PDF dumps pointer metadata | 🔧 SUPERSEDED by Part A — real preservation (page images captured + viewable + honest status); awaiting live re-test |
| BF-BUG-3c | PDF tables/diagrams lost | 🔧 REOPENED → Part A: PDF tables reconstructed (confidence-gated) + page images preserved; diagrams/scans fully handled by Part B vision. See `onboarding_fidelity_plan.md` |
| T-1 | Test PDFs: dashes → � | ✅ FIXED (regenerated) |
| T-2 | Wireframes image-only → add HTML | ✅ FIXED (HTML added) |

**To finish verifying (live, team):** restart backend + frontend to pick up the branch (no migration). Then: (1) each row shows a short type + aligned badge; (2) re-upload a file → one row/one artifact; (3) preview a PDF artifact → structured, no "Page N", no `�`; (4) preview an image-only PDF → friendly note (or upload `11_UX_Wireframes.html` to test the Wireframe adopt path). Mark each ✅ when confirmed.
