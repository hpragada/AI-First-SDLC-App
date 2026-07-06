# Hi-fi gallery reconciliation — brought in line with the as-built app (2026-07-06)

**Why:** the review on 2026-07-06 established that the hi-fi gallery (`docs/design/screens/`)
was the *original build target* and had drifted behind the shipped app after ~33 fixes
(`Bugs.xlsx` rows 2–33). It was stale on content, layout, and behaviour, so it could no longer
be trusted as a reference. This pass reconciles the **greenfield-flow** screens to the current
app.

**Method / decisions (agreed with the team):**
- **Kept illustrative sample data** (Acme Corp / Payment Gateway v2 / WI-492, etc.) — a gallery
  needs populated states — but **aligned it with how the app now renders**: humanised
  phase/role labels, full phase-catalog columns, correct copy, neutral empty/draft states,
  real placeholders.
- **Scope:** greenfield-flow divergent screens only. Brownfield / onboarding / code-intel
  screens (S-24, S-25, S-26, S-27, and code-intel bits) were **not** touched — deferred per the
  standing guardrail.
- Where the **app has a genuine defect** (open finding), the hi-fi shows the **intended** design,
  not the bug — those are called out below so they aren't mistaken for "the app is fine."

---

## Screens reconciled

| Screen | What changed (to match the app) | Fix ref |
|--------|--------------------------------|---------|
| **S-01 Signup** | Default fields now empty with real placeholders (`e.g. Jordan Lee`, `you@company.com`, `At least 8 characters`, `e.g. Northwind Labs`); strength meter starts empty. Was pre-filled "Sarah Chen / sarah@acme.com / Acme Corp". | row 5 |
| **S-02 Login** | Greeting "Welcome back to Acme Corp." → "Welcome back."; email empty + placeholder `you@company.com`; password placeholder `Your password`. | rows 2, 3, 4 |
| **S-03 Accept-invite** | Name/password fields now empty with placeholders (`e.g. Jordan Lee`, `At least 8 characters`). Email stays pre-filled+disabled (known from the invite). | row 4 |
| **S-06 Connect machine** | Serve command no longer hardcodes `https://app.acme.com` — uses a representative deployment URL and now includes `--tenant …` to match the current command shape. | rows 15, 16 |
| **S-07 Users & Invitations** | Users-table roles humanised (Product Owner / Architect / Engineer); invite email placeholder neutralised (`name@company.com`); role dropdown expanded from 4 raw keys to the **full 10 human-readable roles**; "Empty · only you" replaced with a one-row table (the admin is always listed). | rows 20, 21, 31 |
| **S-08 Roles matrix** | Gate-role coverage list + warning banner humanised (Product Owner / Architect / Reviewer / Designer). Column-header `title` tooltips left as raw keys **intentionally** — the app's matrix headers also use the raw key there. | rows 21, 30 |
| **S-09 Create project** | Name field empty + placeholder `e.g. Billing Service`; Create button disabled until a name is typed; the long track-explainer paragraph replaced with an info-tooltip on the Track selector (new `.field__tip` component added to `components.css`). | rows 8, 9 |
| **S-10 Project profile** | Tech stack changed from a one-line input to a full-width multi-line box; added a **"Draft · not saved yet"** state for a never-saved profile (was always "✓ Saved · v3"); dirty-hint versioning corrected. | rows 10, 11 |
| **S-14 Work items board** | Board columns rebuilt from the **full phase catalog in SDLC order** (13 columns, PRD added, numbered, human-readable) instead of a hardcoded 4; per-column icons removed (the app renders none — see "component divergences"); work-item type "Feature" → valid types (Epic/Story). | row 27 |
| **S-21 Gates** | Required-role chips and the read-only banner humanised (Architect / Product Owner / Designer). | rows 21, 30 |
| **S-31 Dashboard** | Get-started step 1 is now the **active, not-yet-done** step (numbered 1 with a "Create a project" action) instead of pre-ticked; Needs-me role text humanised (Architect / Product Owner). | rows 7, 29 |
| **S-18 Phases & Runs** | **No change needed** — already matched the app (offline banner + "No runs yet" empty state). | row 33 |

---

## Component divergences flagged for a team decision (not silently changed)

- **Board column icons:** the hi-fi had a per-phase icon on each board column; the **app renders
  none**. To match the app I removed them from S-14. If the icons are wanted, that's an *app*
  enhancement — decide which way to converge.
- **Integrations grid (`.grid--3`):** hi-fi and app are **identical** (fixed 3-column). Left as
  is; responsive behaviour is a separate design-system decision (see the findings report).

## Where the hi-fi now shows the INTENDED design because the app has an open bug
So these mockups are correct and the **app** is what needs fixing (per the findings report):
- Work-item rail phase names appear humanised (app bug: shows "Prd"/"Ux Design").
- Board/List filters appear populated & working (app bug: board filters are inert).
- List "Phase" column shows a real phase (app bug: shows the feature stream).

## Not reconciled this pass (greenfield, minor — next pass)
- S-11 / S-12 integrations connect **drawer overlay** styling (row 17 rebuilt Drawer/Modal as
  real overlays) — the gallery Drawer/Modal components may need the same overlay treatment.
- S-20 Clarifications "Other → reveals a text box" state (row 25) — no such state in the mock yet.
- S-28 Artifacts populated filter dropdowns + Markdown/Mermaid preview (rows 23, 24, 28).
- `shell.js` companion pill / bell count are static sample values (row 19 made them dynamic in
  the app) — acceptable as gallery sample data, but note it's not a live state.

## Not touched (deferred by guardrail)
Brownfield / onboarding / code-intel screens: S-24, S-25, S-26, S-27 (and code-intel elements).

---

**Net:** the greenfield gallery now reflects the as-built app for the high-traffic screens.
Until the remaining items above are done, treat those specific areas of the gallery as
"styling reference only." Recommend a follow-up pass for the four "not reconciled" items and a
team decision on the two component divergences.
