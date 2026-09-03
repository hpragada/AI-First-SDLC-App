# Design review — P1 UX bugs, batch 2 (2026-07-03)

Source: `docs/Bugs.xlsx` — the new P1 rows filed after deeper end-to-end testing (including live
Companion / Connect-Machine flows). This report states each issue, its root cause, and the planned
change **for team review before any screen code is edited**, per standing practice. Companion-1
of `docs/design/reviews/2026-07-03-P1-ux-bugs.md`.

Scope: P1 rows only. P2/P3/no-priority and Enhancement/Clarification rows deferred. Anything
code-intel / brownfield-specific is deferred to its own session.

---

## 1. Create Work Item / Invite / Integrations — broken overlay: "grey background, form floated right" (Bugs.xlsx row 16)

- **Issue:** Clicking **+ New Work Item** (also **Invite user**, and every **Connect** button on
  Integrations) opens a form that looks broken: a grey block appears embedded in the page and the
  form is squashed to the right side. The ✕ and clicking outside don't close it.
- **Root cause:** The shared `Drawer` and `Modal` primitives
  (`frontend/src/components/ui/index.tsx`) were authored as **inline gallery swatches**. Their CSS
  (`.drawer` / `.modal-scrim`) uses `position: relative`, a fixed `min-height`, `border-radius`, and
  the `--scrim` grey as a *card background* — never `position: fixed`. So when reused live they
  render **in the page flow** as a grey card with the panel floated right, instead of as a true
  overlay above a dimmed page. The ✕ close button had no handler and the scrim wasn't clickable.
- **Planned fix (primitive level — fixes all three screens at once):**
  - Make `Drawer` a real right-side slide-over and `Modal` a real centred dialog: a fixed,
    full-viewport dimmed backdrop (`.scrim-overlay`) with the panel above it.
  - Wire the ✕ button and a backdrop click and the **Esc** key to `onClose`.
  - Keep an `inline` escape hatch so the dev component gallery still shows them as static swatches.
- **Screen refs:** `components/ui/index.tsx` (`Drawer`, `Modal`), `styles/components.css`;
  callers `WorkItemsBoard.tsx`, `UsersInvites.tsx`, `ConnectCapability.tsx` (unchanged — they
  already pass `onClose`).

## 2. Users & Invitations — role picker: only 4 roles, `product_owner` shown raw, no way to remove a granted role (Bugs.xlsx row 20)

- **Issue:** When inviting a user: (1) the role dropdown lists only 4 roles; (2) one shows as the raw
  key `product_owner` (underscore) instead of "Product Owner"; (3) after "grant another role" there's
  no way to remove a row you added by mistake.
- **Root cause:** The role list and labels are hardcoded/short in the invite drawer, and granted-role
  rows are append-only with no remove control.
- **Planned fix:** Source the full role list from one shared place, render every role as a
  human-readable label (title-case, no underscores), and add a remove (✕) control to each granted-role
  row.
- **Screen ref:** `features/identity/UsersInvites.tsx` (+ shared role labels).

## 3. Work Item lifecycle — phase list, labels, type, streaming, trigger errors (Bugs.xlsx row 21)

Multiple sub-issues on the Work Item detail / lifecycle screen:
  - **(i)** Greenfield lifecycle shows brownfield-only phases (`context_bridge`,
    `context_extraction`, `on-boarding`) that shouldn't appear; and phase names show with
    underscores. **Everywhere phase names appear they must be human-readable (no underscores).**
  - **(ii)** Creating a work item of a different type (e.g. Story) still shows "Epic" on the
    lifecycle screen.
  - **(iv)** Latest AI run doesn't show streaming content (also in "view full console").
  - **(v)** A failed trigger shows no reason; re-running throws
    `no AgentSpec registered for key '<uuid>'`.
  - (iii) Type tooltip is an **Enhancement** → out of scope this pass.
- **Scope note:** Human-readable phase labels and hiding brownfield phases for greenfield are UI/label
  fixes and in scope. Sub-issues (iv)/(v) touch the run/trigger backend and the ExecutionDriver /
  AgentSpec registry — I will investigate and fix what is safely a UI/label/wiring bug, and flag
  anything that reaches into code-intel/brownfield orchestration as **Needs team decision** rather
  than touch deferred areas.
- **Screen refs:** `features/lifecycle/*`, `features/lifecycle/railView.ts`.

## 4. Artifacts & Traceability — preview not working (Bugs.xlsx row 22)

- **Issue:** After a phase runs, artifacts list on Artifacts & Traceability but **preview fails**.
  The preview API returns `{"detail":"artifact has no body to preview"}` for some artifacts even
  though other artifacts clearly carry a body in `external_ref.body`.
- **Root cause (to confirm live):** artifacts store their draft body under `external_ref.body`
  (SoR=`internal`, `s3_key` empty). The preview endpoint appears to look only at a different field
  (e.g. a stored body/`s3_key`) and misses the `external_ref.body` drafts. Per the non-negotiables,
  bodies live in S3/SoR, not the DB as source of truth — so the fix is to have preview resolve an
  internal draft's body from where it actually lives, not to copy content into a new column.
- **Screen/refs:** artifacts API `preview` action (backend `apps/registry`), front
  `features/observability/ArtifactPreviewScreen.tsx`.

## 5. Clarifications — "Other (please specify)" has no text box (Bugs.xlsx row 24)

- **Issue:** When an agent asks a clarification with options and the user picks
  "Other (please specify)", there's nowhere to type the specifics.
- **Root cause:** The option renders as a plain choice; there's no conditional free-text input tied
  to the "other" selection.
- **Planned fix:** When the selected option is the "other" one, reveal a text input and submit its
  value as the answer.
- **Screen ref:** `features/lifecycle/Clarifications.tsx`.

## 6. Artifact registration — agent asks the user for a project Id (Bugs.xlsx row 25)

- **Issue:** When registering generated artifacts, the agent raises a clarification asking for the
  **project Id**, which the user can't know. The system already knows the project from context.
- **Root cause:** The registration path doesn't inject the known `project_id` from the run/work-item
  context, so the agent has to ask for it.
- **Planned fix:** Supply `project_id` from the run/work-item context at registration time so it's
  never asked. Go through the capability/registry interface — don't hardcode.
- **Screen/refs:** backend registry registration / MCP platform-state tool that registers artifacts.

---

### Verification plan
Bring up `docker compose up -d`, backend on :8000, frontend preview on :5173, and run the Companion
(`python -m runner.companion serve …`) to complete pairing + first check-in, then exercise the real
Create Work Item → lifecycle → trigger → artifacts → clarifications path. Front tests `npx vitest run`;
backend `make test`.
