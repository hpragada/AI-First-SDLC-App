# Hi-Fi HTML Mockup Gallery (`docs/design/`)

> **⚠ 2026-07-06 — Gallery reconciled to the as-built app.** This gallery was the *original*
> build target and had drifted behind the shipped app after the `Bugs.xlsx` rows 2–33 fixes
> (stale on content, layout, and behaviour). The **greenfield-flow** screens have now been
> updated to match the current app — see
> [`reviews/2026-07-06-hifi-reconciliation.md`](reviews/2026-07-06-hifi-reconciliation.md) for
> exactly what changed and what is still pending. A few areas remain "styling reference only"
> until a follow-up pass (integrations drawer overlay, clarifications "Other" state, artifacts
> filters/preview, dynamic shell counts); brownfield/onboarding/code-intel screens were left
> untouched by guardrail. When in doubt, the **running app is the source of truth for
> content/behaviour**; use the gallery for component/visual design.

The **visual acceptance reference** for the Phase-4.8 React build. Every screen of the
Edvensoft AI-First SDLC platform is rendered as **static, self-contained HTML**, composed
**only** from shared component classes over one shared shell. No app code lives here; this
directory does not touch `frontend/` or the Phase-4.7 backend.

Open **[`index.html`](index.html)** to browse the gallery. Open
**[`screens/S-00-component-library.html`](screens/S-00-component-library.html)** to see every
component in every variant.

---

## Files

| File | Role |
|---|---|
| `design-system.css` | Tokens (DESIGN_SYSTEM §9, verbatim) + spacing/type tokens + reset + base typography. **Link first.** |
| `components.css` | Every reusable component class (atoms → organisms). Screens use these classes **only**. **Link second.** |
| `shell.js` | Injects the canonical app shell (240px navy sidebar + 56px top bar). Call `shellMount("nav-id")`. |
| `index.html` | The gallery — every screen grouped A–E with build status. The acceptance ref. |
| `screens/S-00-component-library.html` | The component catalog — all variants in one page. |
| `screens/S-01 … S-34.html` | One file per screen (one `<main id="screen">`, states stacked + labelled). |

**True single-source reuse:** the shell comes from `shell.js`; components come from
`components.css`. Editing one class updates every screen. Works opening files over `file://`
(no server, no build step, no external requests).

---

## Anatomy of a screen file

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>S-NN · Name — Edvensoft SDLC</title>
  <link rel="stylesheet" href="../design-system.css">
  <link rel="stylesheet" href="../components.css">
</head>
<body>
  <main id="screen">
    <div class="canvas-pad">
      <!-- DEFAULT state, then each listed state, each wrapped: -->
      <div class="state-block">
        <span class="state-block__label">Default</span>
        ... built ONLY from components.css classes ...
      </div>
      <div class="state-block">
        <span class="state-block__label">Awaiting gate</span>
        ...
      </div>
    </div>
  </main>
  <script src="../shell.js"></script>
  <script>shellMount("work-items", { companion: "ready", bell: 4 });</script>
</body>
</html>
```

- **Authed screens** load `shell.js` and call `shellMount(navId, opts?)`.
- **Unauth screens (S-01–S-04)** do **not** load `shell.js` — they render a centered card on
  a branded split panel; no sidebar/top bar.

### `shellMount(navId, opts?)`
`navId` ∈ `dashboard · work-items · runs · gates · clarifications · artifacts · a11y · profile ·
onboarding · integrations · repositories · admin` (activates that sidebar item).
*`a11y` was added to `shell.js` by the accessibility build and was missing from this list until
2026-09-17. Note that the gallery shell does not carry the shipped app's `Test Reporting` (admin
only) or `Connect Machine` items, and its `Onboarding` is unconditional where the app now hides it
on greenfield — see the drift note in `reviews/`.*
`opts` (all optional, sample-data defaults): `{ tenant:"Acme Corp",
project:"Payment Gateway v2", companion:"ready"|"offline"|"connecting", bell:4, user:"You",
admin:true }`.

> The nav is the SCREEN_INVENTORY shared-chrome list, expanded per UX IA §2.1 (Project +
> Admin sections) so every authed screen has an active target. Counts (Gates 3,
> Clarifications 1) use the canonical sample data.

---

## Per-screen generation procedure (follow for every screen)

1. **Read the screen's row** in `../SCREEN_INVENTORY.md` (purpose, elements, states, sample
   data, role) and its journey in `../UX_JOURNEYS_AND_IA_SPEC.md`.
2. **Compose from `components.css` classes only** — no one-off markup. If a needed component
   is missing, **add it to `components.css` + `S-00` first**, then use it (keeps everything
   reusable and keeps the catalog complete).
3. **Render the default state first**, then each listed state, each in its own
   `.state-block` with a `.state-block__label`.
4. **Use the inventory's verbatim sample data** — Acme Corp, Payment Gateway v2, WI-492
   "Stripe Webhook Integration", Sarah Chen, etc. Real content, never lorem ipsum.
5. **Add the screen to `index.html`** (flip its card from Planned → Built, link it).
6. **Self-check** (see Verification).

---

## Component catalog (defined in `components.css`, shown in `S-00`)

**Atoms** — buttons (`.btn` + `--primary/--secondary/--ghost/--danger/--danger-solid`,
`--sm`, disabled); form fields (`.field`, `.input`, `.select`, `.textarea`, `--error`,
`.check`, `.strength`); badges (`.badge` + run-state map `--queued/--waiting/--running/
--needs-answer/--gate/--done/--failed/--parked`); chips (`.chip`, `.chip--filter`); "needs
you" (`.needs--clar/--gate`); `.status-dot`; `.avatar` (+ `--sm/--lg`, `.avatar-group`);
`.sor-chip` (Confluence/Jira/Figma/GitHub/Xray).

**Molecules** — `.card` / `.card--attention` (folded-corner gate card); `.panel` +
`.panel__header`; `.tabs`/`.tab`; `.table`; `.artifact-row`; `.criteria-item`;
`.clar-card`; `.toast` (4 hues); `.empty`; `.skeleton`.

**Media** — `.doc-preview`/`.prose` (read-only artifact body); `.diagram-frame` (centred embed placeholder); **`.shot`** (a captured page, contained — `--fit` scales the whole thing to judge layout, the default scrolls at 1:1 inside the frame to judge contrast, focus rings and text size; `.shot__marker` points at the element and travels with the scroll; `.shot--missing` for a finding with no capture).

**Organisms / signature** — `.rail` (type-adaptive lifecycle rail: node states +
`.rail__loop` + `.rail__branch`); `.board` + `.board__col` + `.wi-card` (columns are phases);
`.gate-panel` + `.criteria-list`; `.console` (dark run log); `.modal`; the app shell
(sidebar + top bar + companion pill + bell) from `shell.js`.

---

## How to extend

- **New component:** add the class to `components.css` (in the right section), render every
  variant in `S-00-component-library.html`, then use it on screens. Never inline a one-off.
- **New token:** add it to `design-system.css` `:root` only. Never hardcode a hex/size on a
  screen — if something isn't covered, add a token and flag it.
- **New screen:** copy the anatomy above, follow the per-screen procedure, register it in
  `index.html`.

---

## Verification (run per batch)

- Open `index.html`, click through every built screen; confirm each renders **all** its
  states and reuses the shared shell + components.
- **Tokens only:** no stray hex or `px` font-sizes in screen files (colors/sizes come from
  `var(--…)`). The only literal hexes live in `design-system.css` `:root` and the SoR vendor
  glyphs in `components.css`.
- **Accessibility basics:** visible orange focus rings, programmatic form labels, ≥4.5:1 text
  contrast, ≥40px hit targets, and **status is never color-alone** (every status badge pairs
  color with a text label + dot/icon). `prefers-reduced-motion` disables the running
  animations.

---

## Build order (batches; review checkpoint after each)

- **Batch 0 — Foundation** ✅ `design-system.css`, `components.css`, `shell.js`,
  `S-00-component-library.html`, `index.html`, `README.md`.
- **Batch 1 — Signature screens** ✅ S-14 board, S-15 epic, S-16 task, S-06 connect-machine,
  S-24 onboarding hub, S-26 gap report, S-31 dashboard.
- **Batch 2 — Lifecycle / observability** ✅ S-17, S-18, S-19, S-20, S-21, S-22, S-23, S-25,
  S-27, S-28, S-29, S-30.
- **Batch 3 — Setup & admin** ✅ S-05, S-07, S-08, S-09, S-10, S-11, S-12, S-13.
- **Batch 4 — Auth (unauth)** ✅ S-01, S-02, S-03, S-04.
- **Decision-gated** ✅ S-33 transcript (DECISION-7), S-34 export/publish (DECISION-8) —
  decisions locked, now **fully built**.
- **Batch 5 — Accessibility (QA-23a)** ✅ S-36 review queue, S-37 conformance/VPAT. Adds the `.shot` component and the `.grid--console` layout (rail + workspace). These are the UI half of QA-23 and QA-24.

**Gallery:** S-00 + S-01…S-38 (plus S-23b) = **40 files**. The "35/35 complete" line here was written before S-23b, S-35, S-36 and S-37 arrived and was corrected on 2026-08-18; **S-38 (accessibility pages & audit) then arrived and was missed, taking the count to 40 — corrected 2026-09-17.**

> These mockups define the **new** design target. Phase 4.8 replaces the current
> `frontend/src/styles.css` (dark-blue) shell + tokens to match this gallery.
