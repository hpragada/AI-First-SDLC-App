# Design review — P1 UX bugs, batch 3 (2026-07-03)

Source: `docs/Bugs.xlsx` — the newest P1 rows (27, 28, 29) filed after further end-to-end testing of
the Work Items board, the Artifacts preview, and the Workspace Dashboard. This report states each
issue, its root cause, and the change made, per standing practice. Continues
`docs/design/reviews/2026-07-03-P1-ux-bugs-batch2.md`.

Scope: P1 rows only. Team decisions taken up front via AskUserQuestion:
- Do all three, in row order (27 → 28 → 29).
- Markdown rendering: add `react-markdown` + `remark-gfm`.
- Diagrams: render Mermaid now (`` ```mermaid `` fenced blocks), not deferred.
- Board columns: show **all lifecycle phases** as columns (not just the 4 plan-tier ones).

Guardrails honoured: tenant isolation / RLS untouched; artifacts stay pointers-not-bodies (the
version fix only sets the integer `version` field, never stores content); brownfield/onboarding
phases stay hidden on per-work-item surfaces; no gate logic changed.

---

## Row 27 — Work Items board

### 27.1 — Board shows only 4 phases, not the full SDLC in order
- **Issue:** The board's columns are lifecycle phases but only four appear
  (Ideation → Requirements → Architecture → UX Design), and the order skips PRD.
- **Root cause:** `WorkItemsBoard.tsx` hardcoded a 4-item `PHASE_COLUMNS`. The real phase order
  lives in the AgentSpec catalog (`backend/apps/registry/catalog.py`) / `PLANNING_PHASES`
  (`frontend/src/types.ts`), which has 13 non-brownfield phases (01_ideation … 12_deployment).
- **Fix:** Build the board columns from `PLANNING_PHASES`, dropping the brownfield/onboarding
  phases (via `isBrownfieldPhase`) and humanising the labels (`phaseLabel`). The board already
  scrolls horizontally (`.board { overflow-x: auto }`), so the extra columns need no layout rewrite;
  a narrower per-column width keeps them scannable. The "Tasks only" filtered view keeps its
  build-tier columns.

### 27.2 — Work-item card looks broken on gate/clarification, raw underscores
- **Issue:** When a card is waiting for gate approval or a clarification, the status pill's long
  label breaks the card layout, and gate labels show a raw phase key (e.g. `04_architecture gate`).
- **Root cause:** `.wi-card__top` didn't wrap, so a long status pill overflowed; the gate label from
  the API is `"<gate_type> gate"` and `gate_type` can be a raw phase key.
- **Fix:** Let the card header wrap (`.wi-card__top { flex-wrap: wrap }`) and humanise the needs
  label on render (reuse `phaseLabel` per token when the label contains an underscore).

## Row 28 — Artifacts & Traceability

### 28.1 — Markdown/diagram artifacts shown as raw text
- **Issue:** Generated artifacts are Markdown but the preview shows the raw markdown source; where
  a diagram is embedded it's unreadable.
- **Root cause:** `ArtifactPreviewScreen.tsx` only rendered `text/html`; `text/markdown` fell into a
  `<pre>` block (raw source).
- **Fix:** Render `text/markdown` through `react-markdown` + `remark-gfm` (GitHub-flavoured: tables,
  lists, code). `` ```mermaid `` fenced blocks are rendered as diagrams via `mermaid`. Wrapped in a
  small `Markdown` UI primitive so tests/gallery and the live screen share one renderer. The preview
  stays strictly read-through — it renders the read body, never edits or persists it.

### 28.2 — Re-running a phase duplicates the artifact at v1 instead of v2
- **Issue:** Re-running a work-item phase creates a second artifact still labelled v1; the preview's
  version history shows v1 for both.
- **Root cause:** `mcp_platform_state/tools.py::register_artifact` always created the row with the
  model default `version=1` and never looked at prior siblings. `preview.py` even documents this as a
  known gap.
- **Fix:** On registration, set `version = (max version among sibling artifacts sharing the same
  project + phase + type) + 1`. Purely the integer counter — still a pointer row, no content stored.
  The single-instance `api_contract` pattern (which bumps one row in place) is unaffected: its first
  registration has no siblings → v1, and it never re-registers.

## Row 29 — Workspace Dashboard

### 29.1 — "Needs me" shows raw underscore names
- **Issue:** The Needs-me list and tiles show raw phase keys and role keys (underscores).
- **Root cause:** `Dashboard.tsx` rendered `g.role`, `g.gate`, `r.phase` verbatim.
- **Fix:** Humanise with the existing shared helpers `phaseLabel` (phases) and `roleLabel` (roles).

### 29.2 — Hardcoded nav / bell counts
- **Issue:** The sidebar Gates (3) and Clarifications (1) badges and the top-bar bell (4) are
  hardcoded literals.
- **Root cause:** `AppShell.tsx` had literal `count:` values and a literal bell badge.
- **Fix:** Feed the sidebar/bell counts from the real needs-me rollup the dashboard already exposes
  (gates / clarifications counts; bell = their sum), via a small shared hook so the nav doesn't need a
  selected project context to render zero.
