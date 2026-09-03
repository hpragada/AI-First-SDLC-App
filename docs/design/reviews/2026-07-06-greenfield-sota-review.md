# SOTA Greenfield Review — findings for team triage (2026-07-06, rev 2)

**Reviewer:** Claude (Opus) session · **Branch:** `develop` (synced through `f97eda8`).
**Scope:** greenfield flow end-to-end, front end + back end.
**This is a findings list only — nothing is fixed.** Suggested priorities are hints for triage,
not decisions.

---

## IMPORTANT — methodology correction (why this is rev 2)

The team asked a critical question: *were the hi-fi screens cross-verified against the fixes
already made to the app, or were they trusted blindly as "the truth"?* If the hi-fi is stale,
any "app ≠ hi-fi" finding could be backwards — flagging the **corrected** app against an
**outdated** mock.

**We checked. The hi-fi gallery (`docs/design/screens/`) is stale — on content, layout, AND
behavior.** It is the *original build target*, made before the 33 fixes. Proof:

- **Content:** `Payment Gateway v2`, `Sarah Chen`, `Acme Corp`, `WI-492`, `sarah@acme.com`
  appear across ~24 of the screen files — the exact demo data the fixes removed from the app.
- **Layout:** hi-fi `S-14` board shows only **4 columns** (Ideation, Requirements,
  Architecture, UX Design) — the pre-fix layout row 27 explicitly fixed ("PRD was missing… a
  hardcoded list of four"). The app now correctly shows the full phase catalog.
- **Behavior:** hi-fi `S-18` still shows demo runs (Stripe/WI-49) — the pre-fix state row 33
  replaced with an empty state. hi-fi `S-02` still shows "Welcome back to Acme Corp." (row 2).

**Conclusion / method used:** the hi-fi is authoritative **only for component visual design**
(colors, spacing, the card/table/button/rail/badge styling that did not change). It is **not**
authoritative for content, which states exist, column sets, empty states, or any behavior the
fixes changed. So every finding below is graded by its **evidence basis**:

- **Live+Code** — observed in the running app and confirmed in source. Independent of hi-fi.
- **Fix-history** — matches a bug class already fixed in `Bugs.xlsx` rows 2–33, recurring in a
  place that wasn't swept. Independent of hi-fi.
- **Self-inconsistency** — the app contradicts *itself* (e.g. board vs rail). Independent of hi-fi.
- **Hi-fi-derived** — leaned on the hi-fi. **Re-verified; see the two that changed below.**

**Net effect of the re-check:** 15 findings are robust (Live+Code / Fix-history /
Self-inconsistency). **2 findings that leaned on the hi-fi were corrected** — old #5 (WI-492
key) and old #16 (Integrations grid). Details in "Corrected on re-verification" below.

---

## How it was tested
Local stack (`docker compose up` + backend + `migrate` + `seed`), demo tenant for populated
screens, plus a **fresh signup** (`Reviewers Inc` / `Orders API`) for the true new-admin setup
flow. Live browser walk + backend/API + component code review. The **live Companion cannot run
on this machine**, so phase-execution screens were reviewed via seed data + code (their
populated states rely on the UX dev's companion session).

**Env note (not a bug):** after pulling, `frontend/` needs `npm install` (row-28 added
`react-markdown`/`remark-gfm`/`mermaid`); without it the app is a Vite white-screen. Flag for CI.

**Re-verified GOOD (no action):** Login (2,3), Signup (5), navbar "No project yet" (6), Create
Project (8), Profile draft badge + tech-stack box (10,11), Get-Started return flow (12), Connect
Machine copy/single-loader/dynamic command (14,15,16), Users & Invitations dynamic name + admin
listed + 10 human roles + overlay drawer (17,20,21,31), Dashboard counts/companion pill (19,29),
post-run empty states (33). (Where the app differs from the stale hi-fi here, the **app is
correct** and the hi-fi is out of date.)

---

## Findings (15 robust)

| # | Bug/Issue | Description | Feature | Type | Evidence basis | Sugg. Priority | Root Cause (likely) |
|---|-----------|-------------|---------|------|----------------|----------------|---------------------|
| 1 | Work items never appear on the board | Every phase column shows 0 even when a work item exists; it shows only in List view. A greenfield user who just created their first work item sees an empty board. | Work Items | Bug | Live+Code | **P1** | Board groups by `item.feature_stream`, but columns are keyed by phase keys; free-text stream never matches → item bucketed into a never-rendered key. `WorkItemsBoard.tsx:164-173`. |
| 2 | Board Search + Phase/Role/Status filters do nothing | Search box and Phase/Role/Status dropdowns are inert; only the level chips work. | Work Items | Bug | Live+Code, Fix-history (row 24) | **P1** | Static markup, no state/handlers, single hardcoded option each. `WorkItemsBoard.tsx:192-219`. |
| 3 | List "Phase" column shows the feature stream, not the phase | Column headed "Phase" prints the feature stream ("Greenfield MVP"); the real phase is never shown. | Work Items | Bug | Live+Code | **P2** | Header "Phase" vs cell `item.feature_stream`. `WorkItemsBoard.tsx:253` vs `:264`. |
| 4 | Work item type raw & lowercase in List | List "Level" shows "story" not "Story"; board card humanises, list doesn't. | Work Items | Bug | Live+Code, Fix-history (22/29) | **P2** | `{item.type}` rendered directly. `WorkItemsBoard.tsx:261-263`. |
| 5 | Empty-title work item shows a blank title / UUID heading | A work item with no title shows a blank Title cell in List and a raw-UUID H1 on the detail page. | Work Items | Bug | Live+Code | **P2** | `title ?? id` uses `??`, so empty-string title ("") renders blank instead of falling back; detail H1 falls back to the UUID. `WorkItemsBoard.tsx:51,259`. |
| 6 | Phase names not humanised on the work-item rail ("Prd", "Ux Design") | The detail rail shows "Prd"/"Ux Design" while the board shows "PRD"/"UX Design" — the app disagrees with itself. | Work Items | Bug | Self-inconsistency, Code | **P2** | Rail passes the node's *bare* label ("prd") to `phaseLabel()`, but the catalog map is keyed by full keys ("03_prd") → lookup misses → naive title-casing mangles acronyms. `phases.ts:30-47`. |
| 7 | "Trigger a phase" buttons show raw lowercase phase names | Buttons read "ideation", "requirements", "prd" instead of "Ideation"/"Requirements"/"PRD". | Phases & Runs | Bug | Live+Code, Fix-history (22/29/33) | **P2** | Phase names not passed through the humaniser. `PhasesAndRuns.tsx`. |
| 8 | Gate "Required role" shown raw | Required-role chip and decision panel show "product_owner"/"architect" with underscores. | Gates | Bug | Code, Fix-history (21/29/30) | **P2** | `GatesLive` renders `a.required_role` without `roleLabel()`. `Gates.tsx:145-147,165`. |
| 9 | Gate-role coverage notes leak raw role keys | "(no product_owner assigned…)", "(no tech_lead…)", etc. Leading label humanised, note keeps raw key. | Roles Matrix | Bug | Live+Code, Fix-history (29/30) | **P2** | Backend `note` string embeds the raw key. `RolesMatrix.tsx:174-179`. |
| 10 | Non-admin lands on a blank/broken admin screen | A non-admin opening `/admin/roles` (or `/admin/users`) by URL sees an empty matrix, no error, no redirect. | Admin | Bug | Live+Code | **P2** | `users.data` 403s for non-admins; screen renders nothing; no route guard. `RolesMatrix.tsx:62`. |
| 11 | Hardcoded sample name/project in live Roles Matrix states | "saving" banner hardcodes "Tom Reyes (reviewer…)"; project-name fallback is still "Payment Gateway v2". | Roles Matrix | Bug | Code, Fix-history (6/8) | **P2/P3** | Sample text + stale demo default in a live view state. `RolesMatrix.tsx:46,121`. |
| 12 | "Context Snapshot" appears on a per-work-item rail | A Story's rail lists "Context Snapshot" (00d) as step 1, alongside normal phases. | Work Items | Bug | Live+Code, Fix-history (22) | **P2/P3** | `isBrownfieldPhase` filters `00`,`00b`,`00c` but not `00d_context_snapshot` (also absent from `PLANNING_PHASES`). `phases.ts:12-27`. Confirm intent. |
| 13 | Invite email placeholder still uses "acme" | Invite drawer Work-email hint is `name@acme.com`; Signup/Login use `you@company.com`. | Users & Invitations | Design Issue | Live+Code, Fix-history (3/5) | **P3** | Placeholder not neutralised. `UsersInvites.tsx`. |
| 14 | Gate decided-history "By" shows a raw user-id fragment | Decisions by others show a user-UUID fragment instead of a name (own show "You"). | Gates | Bug | Code | **P3** | `approver.slice(0,8)` fallback, no name lookup. `Gates.tsx:117`. |
| 15 | Add-repository placeholder uses "acme" | Add-repo form hints `acme/payments-jobs`. | Repositories | Design Issue | Live+Code, Fix-history (3/5) | **P4 / nit** | Placeholder example not neutralised. |

> **Raw work-item id (was a sub-point of old #5):** work items are shown by raw UUID (List ID,
> board card, breadcrumb, Gate rows, `id.slice(0,8)`). This is real UX friction, but see
> "Corrected on re-verification" — there is **no** human key field in the model, so a
> "WI-492" style key is a **new feature**, not a regression. Listed there, not counted here.

---

## Corrected on re-verification (findings that had leaned on the stale hi-fi)

**Old #5 — "Work items should show a human key like WI-492" → reclassified as an ENHANCEMENT,
de-scoped.**
Re-check: the `WorkItem` backend model (`backend/apps/workitems/models.py`) has **no**
key/number/slug field — only `external_ref` (a Jira-key pointer, populated only after SoR
reconciliation). "WI-492" exists **only as hi-fi sample text**; nothing in the product produces
it. So "should show WI-492" was grounded purely in the stale hi-fi. The defensible part —
*raw UUIDs are shown to users, which is poor UX* — remains, but it's a **new capability**
(generate/display a short work-item key), not a bug or a regression. Priority is the team's call;
suggested **P3 Enhancement**.

**Old #16 — "Integrations cards should be responsive" → reclassified as a DESIGN-SYSTEM
question, not an app defect.**
Re-check: hi-fi `S-11` uses `grid grid--3` — **identical to the app** (`Integrations.tsx:59`).
The app faithfully matches the design. The clipping on narrow windows is a property of the
**fixed 3-column design itself** (desktop-first), shared by mock and app. So this is **not** an
app-integrity gap; if narrow-window/responsive support is wanted, it's a change to the design
system (`.grid--3`), to be decided with design — not a review finding against the app.

---

## Questions / to confirm (not counted as bugs)
- **Story rail tier:** detail rail is headed "Plan tier · one pass through plan phases" but also
  lists build-tier phases (UX Design, Task Breakdown…). Confirm whether a Story's rail should stop
  at Architecture.
- **Onboarding nav for greenfield:** the "Onboarding" sidebar item shows for greenfield projects
  (brownfield-adjacent; deferred per the code-intel/brownfield guardrail — flagged only).
- **Dashboard greeting** ("Good morning") — confirm it's time/timezone-based.

---

## Separate recommendation — refresh the hi-fi gallery

Independent of the app fixes: **the hi-fi gallery (`docs/design/screens/`) is now out of date
with the shipped app** and should be refreshed so it stays a trustworthy reference. Concrete
divergences found (app is correct, hi-fi is stale): `S-14` board (4 cols → full catalog),
`S-18` phases&runs (demo runs → empty state), `S-02` login (Acme greeting), and demo content
(`Payment Gateway v2` / `Sarah Chen` / `Acme Corp` / `sarah@acme.com` / `WI-492`) across ~24
screen files. Until refreshed, use the hi-fi for **component styling only**, not content/state.

---

## Cross-cutting theme (the biggest lever)
Findings #4, #6, #7, #8, #9, #14 (and the raw-UUID note) are the **same class**: a machine key
or raw id (phase, role, type, user id) rendered directly instead of through the existing
`roleLabel`/`phaseLabel` helpers, which are already used in *most* places. A single "always
route through the label helpers" sweep closes most of them. **#1 and #2 are the standouts** —
the board is the primary Work Items view and today it is effectively empty and unfilterable.
(Brownfield/code-intel screens excluded, per guardrail.)
