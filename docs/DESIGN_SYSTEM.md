# Edvensoft AI-First SDLC — Design System

**Purpose:** the single visual source of truth for all hi-fi screens. Paste this (or link it) into every screen-generation prompt so every screen shares one look. Derived from the Edvensoft logo (deep-navy wordmark + orange accent) and the existing platform mockups (navy sidebar, orange primary actions, light-gray canvas, green companion status).

> **Rule for whoever generates screens:** use **only** the tokens below for color, type, spacing, radius, and shadow. Never invent ad-hoc hex values or font sizes. If something isn't covered here, pick the nearest token and flag it.

---

## 1. Brand foundation

- **Personality:** trustworthy, enterprise, calm, precise. Not playful, not flashy. "Your trusted partner."
- **Logo:** navy `edvensoft` wordmark with a single orange triangle accent. Orange is the **accent**, used sparingly for primary action + active state — navy and neutrals carry the UI.
- **60 / 30 / 10 rule:** ~60% neutral surfaces (white/gray), ~30% navy (chrome, headers, text), ~10% orange (primary CTA, active nav, key highlights). Orange is a spice, not a base.

---

## 2. Color tokens

### 2.1 Brand
| Token | Hex | Use |
|---|---|---|
| `--brand-navy` | `#1E2A5A` | Primary brand, headings, sidebar text-on-light |
| `--brand-navy-900` | `#15204A` | Sidebar background, deepest navy |
| `--brand-navy-700` | `#1E2A5A` | Primary navy (same as brand) |
| `--brand-navy-500` | `#33417A` | Hover on navy, secondary navy fills |
| `--brand-navy-100` | `#E5E9F4` | Navy-tinted backgrounds, selected rows |
| `--brand-orange` | `#F26F21` | Primary CTA, active nav indicator, key accent |
| `--brand-orange-600` | `#D95E15` | Orange hover/pressed |
| `--brand-orange-300` | `#FBA968` | Disabled/secondary orange, focus glow |
| `--brand-orange-50` | `#FDF0E7` | Orange-tinted highlight backgrounds (e.g. gate-pending card) |

### 2.2 Neutrals (surfaces, borders, text)
| Token | Hex | Use |
|---|---|---|
| `--bg-app` | `#F4F6F9` | App canvas background |
| `--bg-surface` | `#FFFFFF` | Cards, panels, tables |
| `--bg-subtle` | `#EEF1F6` | Subtle fills, hover rows, code blocks header |
| `--border` | `#E2E7EF` | Default borders, dividers |
| `--border-strong` | `#CBD3E0` | Emphasized borders, input outlines |
| `--text-strong` | `#1B2440` | Primary text / headings (near-navy) |
| `--text-body` | `#3A4256` | Body text |
| `--text-muted` | `#6B7385` | Secondary/meta text, placeholders |
| `--text-faint` | `#9AA1B1` | Disabled text, timestamps |
| `--text-on-navy` | `#E8ECF7` | Text on navy sidebar/headers |
| `--text-on-orange` | `#FFFFFF` | Text on orange buttons |

### 2.3 Semantic / status
| Token | Hex | Meaning |
|---|---|---|
| `--success` | `#1FA971` | Approved, published, companion online, passing |
| `--success-bg` | `#E5F5EE` | Success chip/banner background |
| `--warning` | `#E0961B` | Awaiting gate, needs attention, partial. **Fill and border only — never text** |
| `--warning-bg` | `#FBF1DE` | Warning chip/banner background |
| `--warning-ink` | `#7A4E06` | **Amber text.** Use this wherever warning-coloured *text* or a figure is needed. `--warning` as text measures 2.19:1 on the tint and 2.46:1 on white — both fail WCAG AA at any size. This measures 6.42:1 and 7.19:1 |
| `--danger` | `#DC2626` | Rejected, failed, blocked, offline, critical defect |
| `--danger-bg` | `#FCEAEA` | Danger chip/banner background |
| `--info` | `#2563EB` | Running, informational, links |
| `--info-bg` | `#E7EEFD` | Info chip/banner background |
| `--accent-purple` | `#7C5CD6` | "Needs answer" / clarification (distinct from gate) |
| `--accent-purple-bg`| `#EFEAFB` | Clarification chip background |

### 2.4 Run/lifecycle state → color map (use consistently everywhere a state appears)
| State | Fill token | Text |
|---|---|---|
| queued / not started | `--bg-subtle` | `--text-muted` |
| dispatched / waiting | `--info-bg` | `--info` |
| running | `--info-bg` (animated) | `--info` |
| needs answer (clarification) | `--accent-purple-bg` | `--accent-purple` |
| awaiting gate | `--warning-bg` | `--warning-ink` *(not `--warning` — see §2.3)* |
| approved / published / done | `--success-bg` | `--success` |
| rejected / failed / blocked | `--danger-bg` | `--danger` |
| parked for takeover | `--danger-bg` (striped) | `--danger` |

---

## 3. Typography

- **Font family:** `Inter`, with system fallback: `Inter, "Segoe UI", system-ui, -apple-system, Roboto, Helvetica, Arial, sans-serif`.
- **Monospace** (IDs, hashes, code/console): `"JetBrains Mono", "SF Mono", ui-monospace, Menlo, Consolas, monospace`.

| Token | Size / line-height | Weight | Use |
|---|---|---|---|
| `--text-display` | 28 / 36 | 700 | Page hero (rare) |
| `--text-h1` | 22 / 30 | 700 | Screen title (e.g., work item name) |
| `--text-h2` | 18 / 26 | 600 | Section headers (panel titles) |
| `--text-h3` | 15 / 22 | 600 | Sub-section, card titles |
| `--text-body` | 14 / 21 | 400 | Default body |
| `--text-sm` | 13 / 19 | 400 | Secondary/meta |
| `--text-xs` | 12 / 16 | 500 | Badges, labels, timestamps (often uppercase, +0.3px tracking) |
| `--text-mono` | 13 / 20 | 400 | IDs, hashes, console |

---

## 4. Spacing, radius, shadow, layout

- **Spacing scale (4px base):** `4, 8, 12, 16, 20, 24, 32, 40, 48`. Tokens `--space-1`…`--space-9`. Default card padding `--space-5` (20px); page gutters `--space-6` (24px).
- **Radius:** `--radius-sm 6px` (inputs, badges), `--radius-md 10px` (cards, buttons), `--radius-lg 14px` (panels, modals), `--radius-pill 999px` (chips, status dots).
- **Shadow:** `--shadow-sm 0 1px 2px rgba(20,30,60,.06)`, `--shadow-md 0 4px 12px rgba(20,30,60,.08)`, `--shadow-lg 0 12px 32px rgba(20,30,60,.14)` (modals/popovers).
- **Layout shell:**
  - **Left sidebar nav:** fixed width **240px**, background `--brand-navy-900`, text `--text-on-navy`; active item has an **orange left-border (3px) + slightly lighter navy fill**; section labels in `--text-xs` uppercase muted.
  - **Top bar:** height **56px**, white, bottom `--border`; holds tenant/workspace switcher, project switcher (breadcrumb style), spacer, **companion status pill**, notifications bell (with count badge), user avatar menu.
  - **Content area:** max-width **1200px** centered with `--space-6` gutters on `--bg-app`; panels are `--bg-surface` cards with `--radius-lg` + `--shadow-sm`.
  - **Density:** comfortable. Table row height 44px; list item 56px.

---

## 5. Core components (specs)

> All interactive elements: visible focus ring = `0 0 0 3px var(--brand-orange-300)`; transitions 120ms ease.

- **Button — Primary:** orange fill `--brand-orange`, text `--text-on-orange`, `--radius-md`, padding 10×16, weight 600; hover `--brand-orange-600`; disabled `--brand-orange-300` + `--text-faint`.
- **Button — Secondary:** white fill, `--border-strong` outline, text `--text-strong`; hover `--bg-subtle`.
- **Button — Ghost/Tertiary:** transparent, text `--brand-navy-700`; hover `--brand-navy-100`.
- **Button — Danger:** outline style with `--danger` text/border; solid only for destructive confirm.
- **Badge / Chip:** pill, `--text-xs`, status colors from §2.4. A **status dot** (8px circle) may precede the label.
- **Card / Panel:** `--bg-surface`, `--radius-lg`, `--shadow-sm`, header row (`--text-h2` + optional right-aligned action). The **highlighted/attention card** (e.g., active gate) uses a `--brand-orange` left accent bar + `--brand-orange-50` tint + a folded-corner motif (as in the mockup's "Architecture Gate Review" card).
- **Table:** white, header row `--bg-subtle` + `--text-xs` uppercase muted; rows divided by `--border`; row hover `--bg-subtle`; primary cell `--text-strong`, meta `--text-muted`; monospace for IDs.
- **Tabs / Sub-nav:** underline style; active = `--brand-navy-700` text + 2px orange underline.
- **Input / Select / Textarea:** `--bg-surface`, `--border-strong`, `--radius-sm`, 10×12 padding; label `--text-xs` muted above; error state `--danger` border + helper text.
  - **Filter selects size to their content** — add `.select--fit` (`width: auto; max-width: 100%`) so a filter box is as wide as its longest choice instead of cutting it. Used on the Work Items, Artifacts and Traceability filter rows (2026-09-12).
- **Floating popup layer (Bugs S.No 166, 2026-09-11).** Every popup — dropdown lists, row and account menus, tooltips — is drawn at the top of the page so no panel's `overflow: hidden` can cut it off. Built from shared pieces in `frontend/src/components/ui/index.tsx`:
  - **`FloatingLayer`** — renders its children into `document.body` (a React portal). Give the popup the `.popover-layer` class (`position: fixed`, `z-index: var(--z-popover)`).
  - **`useFloatingPosition(open, anchor, floating, options)`** — places the popup beside its trigger and re-measures on scroll (including scrolling panels) and resize. Below the trigger by default; **flips above** when it does not fit below and there is more room above; scrolls only when it fits neither way. Options: `align` (`start`/`end`/`center`), `matchWidth` (same width as the trigger — dropdown lists), `preferAbove` (tooltips), `gap`, and **`overlay`** — draw the popup *over* the trigger from its top-left corner, never narrower than it, clamped on screen.
  - **`--z-popover: 110`** (in `design-system.css`) — the one depth every popup uses: above the sticky top bar (20) and above the dialog scrim (100), so a popup opened inside a dialog draws over it.
  - **Truncation peek (`.peek`, 2026-09-12).** When a dropdown row's label is actually cut off, the whole text opens out over that row (`overlay` placement) on hover and on arrow-key highlight — shown only when the text is really cut. Styled as the same row showing more: `max-content` width capped at `min(560px, 80vw)`, wraps, `--brand-orange-300` border, `--shadow-lg`. Used by the shared searchable dropdown (the work-item picker and the history filters).
- **Status pill (companion):** pill with dot — online `--success`, offline `--danger`, connecting `--warning`. Label "Companion: Ready / Offline / Connecting".
- **Avatar:** 32px circle, navy ring; initials fallback on `--brand-navy-500`.
- **Notification bell:** icon + `--brand-orange` count badge.
- **Console/log block:** dark surface `#10182B`, mono text, status tokens colorized (`[OK]` green, errors red); used for the live run console.
- **Toast:** top-right, `--shadow-lg`, semantic left accent.
- **Modal:** centered, `--radius-lg`, `--shadow-lg`, scrim `rgba(20,30,60,.45)`.
- **Empty state:** centered icon (muted) + one-line explanation + a single primary action.

---

## 6. Signature patterns (specific to this product)

- **Lifecycle rail** (work item detail): a horizontal stepper of phase nodes connected by a line. Node = circled icon; completed = `--success` filled check; current = `--brand-orange` ring + filled dot + label in orange ("Gate Pending"); upcoming = `--border-strong` outline + muted label. **Must support loops** (a curved back-edge for review↔fix) and a **branch indicator** for child items. **Type-adaptive:** epics show the plan rail, tasks show the build rail only (see SCREEN_INVENTORY §work items).
- **Board columns = phases:** Kanban columns titled by phase, each with a count chip; cards are work items with title, type/level chip, status chip, artifact count, owner avatar, and "needs you" flags. Column header carries the phase's small icon.
  - *As built (2026-09-11/12):* a **Backlog** column comes first, for work items nothing has run on yet. Each card carries a **status pill** using the shared Badge: "Not started" (queued), "Running" (running), **"Waiting for you"** (needs-answer or gate colour — only when this person may answer or decide it), grey "Waiting for review" / "Waiting for an answer" / "Waiting for approval" when it is someone else's, "Done" (done), "Failed" (failed), "Cancelled".
- **"Needs you" affordances:** clarification = purple "● needs answer" chip; gate = orange/amber "Awaiting gate" chip. These appear on cards, run rows, and the global bell.
- **Gate panel:** the attention card with Approve (primary) / Reject (secondary) and, for **criteria gates** (WCAG), a checklist where Approve stays disabled until all required items are ticked (show "3 of 8 criteria met").
- **Artifact row:** icon by type, title, version + phase, SoR chip (Confluence/Jira/Figma/Xray with vendor glyph) that is an external deep-link, and a Preview affordance. Bodies are **never** edited inline — Preview opens read-only.
- **Zero-cost-wait reassurance:** wherever a run is "needs answer," show a subtle line: "Paused — no usage billed while waiting."
- **Connect-your-machine:** a guided two-step "device pairing" card — Step A (in-app: generate token, copy) and Step B (terminal: copy the two commands) — with a live "waiting → connected" status. Make it feel like pairing a device, not a dev chore.

---

## 7. Accessibility (WCAG 2.2 AA — the product gates on it, so the product itself must pass)

- Text contrast ≥ 4.5:1 (≥3:1 for ≥18px/bold). Verify orange-on-white only for large text or non-text use; for body, use navy/gray text.
- Never encode meaning by color alone — pair status color with a label/icon (the badges already do this).
- Visible focus on every interactive element (the orange focus ring).
- Hit targets ≥ 40px; form fields have programmatic labels; tables have header scope.
- Respect `prefers-reduced-motion` (disable the running-state animation).

---

## 8. Dark mode (optional, later)

Not required for v1 hi-fi. If introduced: keep navy chrome, flip `--bg-app` to `#0F1530`, surfaces to `#161D38`, text to light neutrals; orange and semantic hues stay. Token names stay identical (only values swap), so screens don't change structurally.

---

## 9. Drop-in CSS variables (hand to engineering / paste into mockups)

```css
:root {
  /* brand */
  --brand-navy:#1E2A5A; --brand-navy-900:#15204A; --brand-navy-700:#1E2A5A;
  --brand-navy-500:#33417A; --brand-navy-100:#E5E9F4;
  --brand-orange:#F26F21; --brand-orange-600:#D95E15; --brand-orange-300:#FBA968;
  --brand-orange-50:#FDF0E7;
  /* neutrals */
  --bg-app:#F4F6F9; --bg-surface:#FFFFFF; --bg-subtle:#EEF1F6;
  --border:#E2E7EF; --border-strong:#CBD3E0;
  --text-strong:#1B2440; --text-body:#3A4256; --text-muted:#6B7385;
  --text-faint:#9AA1B1; --text-on-navy:#E8ECF7; --text-on-orange:#FFFFFF;
  /* semantic */
  --success:#1FA971; --success-bg:#E5F5EE;
  --warning:#E0961B; --warning-bg:#FBF1DE;
  /* Amber INK, for warning-coloured TEXT and figures. `--warning` is a fill/border colour and
     must not be used as text: 2.19:1 on the tint, 2.46:1 on white. This is 6.42:1 and 7.19:1. */
  --warning-ink:#7A4E06;
  --danger:#DC2626;  --danger-bg:#FCEAEA;
  --info:#2563EB;    --info-bg:#E7EEFD;
  --accent-purple:#7C5CD6; --accent-purple-bg:#EFEAFB;
  /* radius / shadow */
  --radius-sm:6px; --radius-md:10px; --radius-lg:14px; --radius-pill:999px;
  --shadow-sm:0 1px 2px rgba(20,30,60,.06);
  --shadow-md:0 4px 12px rgba(20,30,60,.08);
  --shadow-lg:0 12px 32px rgba(20,30,60,.14);
  /* type */
  --font-sans:Inter,"Segoe UI",system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif;
  --font-mono:"JetBrains Mono","SF Mono",ui-monospace,Menlo,Consolas,monospace;
}
```
