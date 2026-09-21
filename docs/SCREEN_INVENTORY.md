# Edvensoft AI-First SDLC — Screen Inventory

**Purpose:** the bridge between the journeys (`UX_JOURNEYS_AND_IA_SPEC.md`) and hi-fi screens. Every screen is listed with its journey, role/permission, key elements, states to render, and **concrete sample data** so generated mockups look real. Use one **row block** per screen-generation prompt (see `PROMPT_TEMPLATE`).

**Conventions:**
- **J#** = the journey in the UX spec it realizes.
- **States** = the variants the designer must produce (default + the listed ones).
- **Companion-aware** screens must show the global companion status pill (online/offline) and block "Run" actions when offline.
- All screens sit inside the **app shell** (240px navy sidebar + 56px top bar) unless marked **(unauth)**.

---

## Shared chrome (build these once; reused on every authed screen)

| Element | Contents | Notes |
|---|---|---|
| **Sidebar** | Logo (edvensoft) · Workspace Dashboard · Work Items · Phases & Runs · Gates (count) · Clarifications (count) · Artifacts & Traceability · **Accessibility (count)** · — **Project** — Project Profile · Onboarding *(brownfield only)* · Integrations · Repositories · Test Reporting *(admin only)* · Connect Machine · — **Admin** — Workspace Admin | Active = orange left-bar + lighter navy. Admin section only for tenant-admin. Companion pill pinned bottom. *Corrected 2026-09-17 against `AppShell.tsx:63-112`: the second group is headed **Project**, not Settings, and it holds six items this row never listed.* |
| **Top bar** | Tenant switcher ("AC Acme Corp ▾") · Project switcher ("⚑ Payment Gateway v2 ▾") · spacer · Companion pill ("● Companion: Ready") · Bell (badge "4") · Avatar menu | Breadcrumb style for tenant/project. |
| **Sample identities** | Tenant: **Acme Corp**. Projects: **Payment Gateway v2** (greenfield), **Legacy Billing** (brownfield). Users: **Sarah Chen** (product_owner), **Marcus Lee** (architect), **Priya Nair** (designer), **Dan Ortiz** (tech_lead), **Aisha Khan** (qa_lead), **Tom Reyes** (reviewer), **You** (tenant-admin + engineer). | Reuse across all screens for consistency. |

---

## Group A — Identity & onboarding (J1–J6)

### S-01 · Sign up (unauth) — J1
- **Role:** anyone. **Layout:** centered card on branded split panel (navy panel with logo + tagline left, form right).
- **Elements:** name, work email, password (strength meter), org/workspace name, "Create workspace" primary; link "Already have an account? Log in".
- **States:** default, validation error (email in use), submitting (spinner), success→redirect.
- **Sample:** name "Sarah Chen", email "sarah@acme.com", org "Acme Corp".

### S-02 · Log in (unauth) — J4
- **Elements:** email, password, "Log in" primary, "Forgot password?", error banner.
- **States:** default, invalid credentials, locked/too-many-attempts, submitting.

### S-03 · Accept invitation (unauth) — J3
- **Elements:** "You've been invited to **Acme Corp** by Sarah Chen" header, set-password fields, "Join workspace" primary.
- **States:** default, expired/used link (→ request new), submitting.

### S-04 · Forgot / reset password (unauth) — J4
- Two screens: request (email) → confirmation; reset (new password via token).
- **States:** request sent, invalid/expired token, success.

### S-05 · Setup checklist / first-run home — J1
- **Role:** tenant-admin, empty workspace. **Elements:** welcome header, 4-item checklist cards (☐ Create first project · ☐ Connect your machine · ☐ Invite team & assign roles · ☐ Connect integrations), each with a CTA + done-tick.
- **States:** all incomplete (fresh), partial (2 done), all complete (collapses to dismiss).

### S-06 · Connect your machine (companion) — J5  **★ signature screen**
- **Role:** any operator. **Elements:** explainer ("Phases run on your computer using your Claude Code subscription"); **Step A card** (project multi-select → "Generate enrollment token" → token shown once + copy); **Step B card** (terminal with two copy-commands: `claude` sign-in and `python -m runner.companion serve … --token …`, note "leave running"); **live status** strip (waiting → ● Connected, last seen just now).
- **States:** not-started, token-generated (awaiting first check-in, spinner), connected (green), previously-connected-now-offline (last seen 5m ago + "restart the daemon").
- **Sample:** token `rnr_3f9a…b2`, machine "Sarah's MacBook".

### S-07 · Users & invitations (admin) — J2/J6
- **Role:** tenant-admin. **Elements:** Users table (name, email, status, projects+roles summary, actions), "Invite" primary opening an invite drawer (email, name, initial project+role grants); pending-invites rows with Resend/Revoke.
- **States:** populated, empty (only you), pending invite row, duplicate-email error in drawer.
- **Sample rows:** Sarah Chen — product_owner@PaymentGW; Marcus Lee — architect@PaymentGW; pending "raj@acme.com — invited 1d ago".

### S-08 · Roles & memberships matrix (admin) — J6
- **Elements:** per-project **role matrix** (rows = users, cols = the 10 roles, toggles), plus a **role-coverage panel** flagging uncovered gate roles ("⚠ No reviewer on Payment Gateway v2 — merge gate will be unactionable").
- **States:** full coverage, gap warning, last-admin guard, saving.
- **As built (2026-09-12, `b40c557`, option B+):** the gap warning shows whenever any gate role on the project has nobody — one line however many are empty. It names the roles while one or two are missing ("Nobody holds Reviewer on Payment Gateway v2." / "Nobody holds Reviewer or Designer on …") and counts them beyond that ("7 roles have nobody on …"), then says either "That gate falls to an admin meanwhile" or, when no admin can cover it, "That gate cannot be approved by anyone until someone holds the role." The project beside the title is a plain line of text, not a dropdown.

---

## Group B — Project setup (J7–J10)

### S-09 · Create project — J7
- **Elements:** name, **Track toggle (Greenfield / Brownfield)**, repo topology (single / multi), Create primary; helper text explaining the branch (greenfield→profile, brownfield→onboarding).
- **States:** default, brownfield-selected (hints onboarding next), name collision.

### S-10 · Project profile editor — J8
- **Elements:** sectioned form — Description, Domain, Tech stack, Coding standards, NFRs, Constraints, Glossary, Important context; "Save" with "last saved v3" indicator; helper "feeds every agent's context".
- **States:** clean, unsaved-changes (dirty), saving, validation.
- **Sample:** Description "Card payment gateway handling Stripe + Adyen…", Tech stack "Django, React, Postgres".

### S-11 · Integrations — capability grid (admin) — J9
- **Elements:** grid of capability cards — Documentation store, Task tracker, Design source, Code host, Test management — each showing connected vendor + status or "Not connected" + Connect.
- **As built (2026-09-11, `4ac75f9`, N1):** there is **no Code intelligence card**. It is set up automatically for every workspace (like accessibility), and an old `/integrations/codeintel` link returns to the grid.
- **States:** mixed (some connected), all empty, connection-failed card (red, reason).
- **Sample:** Documentation store → **Confluence ● Connected**; Task tracker → **Jira ● Connected**; Design source → **Figma ● Connected**; Code host → **GitHub ● Connected**; Test management → **Xray ○ Not connected**.

### S-12 · Connect a capability (drawer/modal) — J9
- **Elements:** vendor select, binding config (e.g., Confluence space key, Jira project key, GitHub repo, Figma file key), **write-only secret fields** (show "configured ✓", never echo), **Test connection** button + result.
- **States:** empty, filled, testing (spinner), test-success (green), test-fail (reason + fix hint).

### S-13 · Repositories — J10
- **Elements:** repo table (name `owner/repo`, role frontend/backend, default base, status), Add-repo form, set-default, remove.
- **States:** empty, single repo, multi-repo (topology chip "multi"), duplicate error.
- **Sample:** `acme/payments-api` (backend, main), `acme/payments-web` (frontend, main).

---

## Group C — The lifecycle, Tier 1 + Tier 2 (J11–J16)  ★ core of the product

> **Read §6.0 of the UX spec.** Two tiers: **Plan** (epic-level: Ideation→Requirements→PRD→Architecture→UX→Task Breakdown) and **Build** (task-level: Implementation→Review→Test→Merge). **Task Breakdown fans out into task work items.** The lifecycle rail is **type-adaptive**.

### S-14 · Work Items board — J11  **★ signature screen**
- **Elements:** header + "New Work Item"; filters (Phase, **Level: Epics/Tasks/Defects**, Role, Status) + Board/List toggle; **Kanban columns = phases** with count chips; cards = work items (title, level chip, status chip, artifact count, owner avatar, "needs you" flags).
- **States:** populated board, list view, filtered (e.g., Tasks only), empty project, a card with "1 Clarification" and another "Gate: PM Approval Req.".
- **As built (2026-09-11/12, `4ac75f9` + `b40c557`):** the first column is **Backlog** — work items nothing has run on yet — followed by the lifecycle phases; the Tasks view is Backlog · Implementation · Review. Every card has a **status pill** for what its phase is doing: Not started, Running, **Waiting for you** (only on a gate this person may decide or a question they may answer), Waiting for review / Waiting for an answer / Waiting for approval (grey, when it is someone else's), Done, Failed, Cancelled. The filter boxes size themselves to their longest choice.
- **Sample columns/cards:**
  - *1. Ideation* → WI-508 "Customer Loyalty Program" (Epic, Draft); WI-521 "Dark Mode UI Theme" (Feature, Draft).
  - *2. Requirements* → WI-510 "Analytics Dashboard PRD" (AI compiling…, 1 Clarification); WI-511 "Fix Session Timeout Logic" (Task, Gate: PM Approval Req.); WI-499 "Multi-Currency Support" (Phase complete, 3 artifacts).
  - *3. Architecture* → WI-492 "Stripe Webhook Integration" (selected, Review Architecture Gate, Jira STR-14).
  - *4. UX Design* → WI-487 "Checkout Flow Redesign" (AI compiling…).

### S-15 · Work Item Detail — EPIC / FEATURE / STORY level — J11  **★ signature screen**
- **Elements:** breadcrumb (Work Items › WI-492), title + ⚡icon, meta (Created 2d ago, Owner Sarah Chen, Jira STR-14), **Edit / [phase] Gate** action; **plan-tier lifecycle rail**, headed "Lifecycle — Planning" (Ideation→Requirements→PRD→Architecture→UX→Task Breakdown with states); **Description & context** panel; **Linked Artifacts** panel (rows with SoR chips + View Traceability link); **Latest AI Run** console snippet (+ View Full Run Console); **Child tasks** section (the fan-out — list of task work items it produced); right-side **attention card** when a gate is pending.
- **States:** mid-pipeline (Architecture = Gate Pending — like the mockup), gate-pending attention card visible, a phase running (console live), needs-answer badge, all-phases-complete.
- **Sample:** WI-492 "Stripe Webhook Integration"; rail Requirements ✓ Approved · Architecture ● Gate Pending · Build/QA/Deploy upcoming; artifacts "PRD: Stripe Webhook Integration v1.2 (Confluence)", "System Sequence Diagram v0.9 (Figma, Pending Architecture Gate)"; run console "Compiling requirements… [OK] / Generating sequence diagrams… [OK] / Validating against security rules… [OK] / Run completed. Awaiting gate."

### S-16 · Work Item Detail — TASK level — J16
> **A story is not on this screen** — settled 2026-09-21 (Screen Words group 9, Option A): a story is
> a planning item and opens S-15, where its children are listed. See `UX_JOURNEYS_AND_IA_SPEC.md`
> §6.0. The rail on this screen is headed "Lifecycle — Delivery".
- **Elements:** same shell but **build-tier rail only** (Implementation→Review→Test→Merge — **no plan phases**); **parent epic backlink**; **child defects/remediations** list; **linked PR** card (draft/open/merged); run console.
- **States:** implementation running, review loop (Review→back to Implementation, show the loop edge), test failed (defect child created), awaiting merge gate, done.
- **Sample:** WI-540 "Verify Stripe signing secret" (parent WI-492); PR #218 (draft) on `acme/payments-api`; child defect WI-547 "Signature check rejects valid test events".

### S-17 · Work Item Detail — DEFECT / REMEDIATION — J16
- **Elements:** minimal rail (Fix→Review→Test), parent backlink, originating run/finding reference.
- **States:** open, fixing, closed-on-clean-rerun.

### S-18 · Phases & Runs (trigger + run list) — J12
- **Elements:** select work item, **trigger phase** buttons (the phases valid for that item's level), runs table (run id, phase, status, engine/model, cost, workflow id, created), companion-offline blocked banner.
- **States:** companion-online (triggerable), companion-offline (blocked + Connect link), runs list with mixed statuses, no runs yet.

### S-19 · Live Run Console — J12
- **Elements:** dark console block streaming activity, status badge, cost (after completion), engine/model, "needs answer"/"awaiting gate" transitions, zero-cost reassurance when paused.
- **States:** dispatched-waiting (companion hasn't claimed), running (stream), needs-answer (purple), awaiting-gate (amber), completed (cost shown), failed (reason + retry), parked-for-takeover.

### S-20 · Clarifications — J13
- **Elements:** pending list (run/work item/phase + "waiting 6m · $0 while waiting"); **answer form** per question kind (text→input, choice→select, confirm→checkbox) with the agent's "why I'm asking" context; submit.
- **States:** empty, one pending (text q), multi-question, required-field error, already-answered-by-someone (collapsed), cancelled.
- **Sample:** WI-510 / Requirements — "Should the analytics dashboard support CSV export in v1?" (confirm); context "Affects the data-export NFR scope."

### S-21 · Gates — list + decision — J14
- **Elements:** pending approvals table (gate type, required role, run/work item, **Preview artifact** link); decision panel — **three actions: Approve (primary) / Reject / Request changes** + comment; role-gated (non-holders see read-only "awaiting <role>"). *`Request changes` was added after this row was written and listed here 2026-09-17: it rejects **and** re-runs the phase with the comment as the agent's direction, so it is disabled until a comment is typed — the comment **is** the request.*
- **States:** can-decide (your role), cannot-decide (permission, show who can), empty, decided history tab.
- **Sample:** "Architecture gate · required role architect · WI-492 · preview System Sequence Diagram"; count badge "3".

### S-22 · Criteria gate (WCAG) — J15
- **Elements:** the gate panel **plus a required-criteria checklist** (each WCAG criterion, tickable, optional note); **Approve disabled until all required ticked** ("5 of 8 criteria met"); progress indicator.
- **States:** none ticked (approve disabled), partial (disabled + remaining count), all ticked (approve enabled), rejected path.
- **Sample:** UX Design gate for WI-487; criteria "Color contrast ≥ 4.5:1", "Keyboard navigable", "Focus visible", etc.

### S-23 · Task Breakdown result (the fan-out moment) — J16
- **Elements:** post-approval screen "**Created 6 task work items**" with links + (if Jira connected) "pushed to Jira backlog" confirmation + deep-links; jump-to-board CTA.
- **States:** internal-only (saved locally), pushed-to-Jira (issue keys shown).
- **Sample:** STR-14 → tasks STR-15…STR-20.

---

## Group D — Brownfield onboarding (J17–J18)

### S-24 · Onboarding hub — J17  **★ signature screen (brownfield only)**
- **Elements:** staged panel — ① Upload resources (drag-drop docs) · ② Register existing tools (Confluence/Jira register-don't-recreate) · ③ Index code (point at repo) · ④ Gap report · ⑤ Resume; each stage shows progress/result.
- **States:** nothing-done, docs uploaded (extracting), tools registered ("found 32 existing Jira issues, linked"), index running, gap-report ready.

### S-25 · Source documents — upload & adopt — J17
- **Elements:** drag-drop zone (.docx/.pdf/.xlsx), uploaded list with extraction status, **review extracted draft** → **Adopt** (behind gate or lightweight for internal).
- **States:** empty, uploading, extracted (review), adopt-pending-gate, adopted.

### S-26 · Gap report — J17  **★**
- **Elements:** assessment table per lifecycle phase (Complete / Partial / Missing + evidence), **recommended Resume phase** highlight, blocking gaps list, "Re-run gap report" + "Resume at <phase>" CTA.
- **States:** empty→ideation, partial (resume prd/architecture), mature (resume later); show resume point moving as inputs added.
- **Sample:** Ideation ✓, Requirements ✓ (from uploaded spec), PRD ~Partial, Architecture ✗ → **Resume at: Architecture**.

### S-27 · API contracts & drift — J18
- **Elements:** contracts list (semver, provider repo, status, read-through view); **drift queue** (open DriftRecords with cross-repo impact list); **drift decision** panel (architect Accept/Reject + impact).
- **States:** healthy (no drift), drift-pending (impact spans repos), decided, wrong-role read-only.
- **Sample:** contract "Payments API v2.0.0 (acme/payments-api)"; drift "breaking change → impacts acme/payments-web (3 consumers)"; decider Marcus Lee (architect).

---

## Group E — Observability & recovery (J19–J22)

### S-28 · Artifacts registry — J19
- **Elements:** table (type icon, title, phase, version, status, SoR chip + deep-link, **Preview**); filters (phase/type/status). **Status is one of five** — `draft · staged · approved · published · superseded` (`backend/apps/registry/models.py:36-46`). *Corrected 2026-09-17: this row said "draft/published". `superseded` is the newest and the one most easily missed — it marks a draft whose gate was **rejected**, kept as the record but no longer served to downstream phases.*
- **States:** populated, internal-only (no link), published-with-link, empty.

### S-29 · Artifact preview (read-only) — J19
- **Elements:** rendered body (read-through), version history, SoR deep-link, "Published / Draft" badge; **never an editor**.
- **States:** markdown doc, diagram/image, external (Confluence) embed/link, body-unavailable.

### S-30 · Traceability graph — J20
- **Elements:** node-link lineage graph (nodes = artifacts by phase/type/status/SoR; edges = derives/implements/tests), filters, click→preview/deep-link, pan/zoom.
- **States:** empty, small graph, large graph (cluster), a work item's lineage highlighted.

### S-31 · Workspace Dashboard — J22  **★ landing screen**
- **Elements:** **"Needs me"** panel (gates awaiting my role, questions awaiting my answer, my runs in flight); **project health** (work items by lifecycle stage, phases in progress, recent publishes); companion status; quick actions (trigger phase, new work item).
- **States:** busy (lots needs-me), calm (nothing needs me), new project (mostly empty + nudges).
- **Sample:** "2 gates need your approval", "1 question awaiting you", "Run #42 awaiting gate".

### S-32 · Offline takeover / recovery — J21
- **Elements:** parked work item banner ("Your machine went offline — this run is parked for takeover"), explanation, **Reconnect & re-run** CTA (→ S-06), answered-clarifications-remembered note.
- **States:** parked, reconnecting, resumed.

---

## Decision-gated screens (now CONFIRMED — see journeys §9 DECISION-7/8)
- **S-33 · Run transcript / session view** — ✅ **DECISION-7 locked (build).** List of runs → per-run transcript (agent turns + tool calls + the Q&A), read-only. Engine conversation is **persisted in the DB** (no retention window for now; user-facing retention is a later add). **States:** runs list, transcript (read-only), empty.
- **S-34 · Explicit Export/Publish action** — ✅ **DECISION-8 locked (build).** Modal: choose target capability + destination, confirm. **Gate-respecting — only gate-APPROVED artifacts are publishable; never bypasses a gate. States:** choose target, publishing, success, blocked (not gate-approved).

---

## Build order suggestion (for generating screens)
1. **Shell + design-system primitives** (sidebar, top bar, companion pill, buttons, badges, tables) — S-shell.
2. **Signature screens first** (highest design risk): S-14 board, S-15 epic detail, S-16 task detail, S-06 connect-machine, S-24/S-26 onboarding+gap, S-31 dashboard.
3. **Flows around them:** S-18/19 runs, S-20 clarifications, S-21/22 gates, S-28/29 artifacts, S-30 trace.
4. **Setup & admin:** S-09–S-13, S-07/08.
5. **Auth (unauth):** S-01–S-05.
