# PHASE 4.8 BUILD SPEC — Hi-Fi Web App (frontend architecture + design-sensitive backend)

**Read this before any Phase 4.8 task.** It is the **contract** parallel UI assistants build against —
app architecture, the component-library port, data-fetching conventions, and the design-sensitive
("bucket B") backend endpoint schemas are fixed here so screens built by different people compose
identically and never re-decide the shell or the client. Tasks: `/BUILD_PLAN.md` (P4.8-T0…T6).

**Design source-of-truth (signed off, merged to `develop`):** the hi-fi gallery `docs/design/` —
`design-system.css` (tokens), `components.css` (component classes), `shell.js` (the app shell),
`screens/S-01…S-34.html` (every screen, **all states stacked + labelled**), `index.html`,
`README.md` (component catalog). Per-screen build crosswalk: **`docs/SCREEN_BUILD_MAP.md`**. Journeys:
`docs/UX_JOURNEYS_AND_IA_SPEC.md` (J1–J22, **eight** decisions §9). Backend it binds to:
`docs/PHASE_4.7_BUILD_SPEC.md` + bucket B below.

**Hard rule:** build to the gallery. A screen is done when it renders **every labelled state** from
its `S-NN.html` with **visual parity** (same tokens/classes), wired to live endpoints. Never invent UI
the mockup doesn't show; never show an editable artifact body; pair status colour with a label.

---

## 1. App architecture (LOCKED — do not re-decide)

Stack stays **Vite + React + TypeScript** (extend `frontend/`, don't rewrite the toolchain).

- **Design tokens:** adopt `docs/design/design-system.css` as the app's base stylesheet (tokens +
  reset + typography) and `components.css` as the component styles — **copy them into
  `frontend/src/styles/` and keep the class names verbatim** so tokens carry over 1:1. This supersedes
  the current dark-blue `frontend/src/styles.css` (delete it in T0).
- **Routing — React Router**, two route groups:
  - `(unauth)` — no shell, the `.auth` split-panel: `/login` (S-02), `/signup` (S-01),
    `/accept-invite` (S-03), `/reset` (S-04). Redirect to `/` if already authed.
  - `(app)` — everything inside `<AppShell>`, guarded by auth. Routes map to nav ids:
    `/` dashboard (S-31) · `/work-items` (S-14) · `/work-items/:id` (S-15/16/17 by level) ·
    `/runs` (S-18) · `/runs/:id` (S-19) · `/gates` (S-21) · `/clarifications` (S-20) ·
    `/artifacts` (S-28) · `/artifacts/:id` (S-29) · `/traceability` (S-30) · `/profile` (S-10) ·
    `/onboarding` (S-24) · `/integrations` (S-11) · `/repositories` (S-13) · `/admin/*` (S-07/S-08) ·
    `/connect` (S-06) · `/setup` (S-05) · `/transcripts` (S-33) · `/contracts` (S-27).
- **Auth — `AuthContext`** seeded from `GET /api/auth/me` on boot: `{user, tenant, memberships,
  isAdmin}` + `login/logout`. The router's auth guard reads it; `401` from any call → redirect to
  `/login`. Switch the client to **session cookies** (`credentials:"include"`); drop the
  `X-Tenant-ID` header for authed calls (tenant is server-derived). Keep `state.tsx`'s project-selection
  idea but source the project from `me.memberships` + the top-bar switcher.
- **Server state — TanStack Query.** All reads via `useQuery`, all writes via `useMutation` +
  invalidation. Poll where the gallery implies live data (runs/clarifications/gates ~4s, companion
  status). No bespoke caching. Loading → `Skeleton`; empty → `EmptyState`; error → `Toast`/`Banner`
  (the gallery already defines all three).
- **Typed api client:** **extend `frontend/src/api.ts`** (same `req<T>()` shape) — append one method
  per endpoint; append types to `types.ts`. These two files are **shared / append-only** (see
  `AGENTS.md`). Co-locate Query hooks per feature (`features/<group>/hooks.ts`).
- **Feature folders (collision-free parallelism):** `frontend/src/`
  - `components/ui/` — the component library (T0, shared; coordinate)
  - `components/AppShell.tsx` — the shell (T0, shared)
  - `features/identity/` `features/setup/` `features/lifecycle/` `features/brownfield/`
    `features/observability/` — one journey group per folder, **task-owned** (T2–T5).
  - `routes.tsx`, `api.ts`, `types.ts`, `auth/AuthContext.tsx` — shared/append-only.

## 2. Component-library port (`components.css` → React 1:1)

Build these in `components/ui/` in **T0**, one component per `components.css` class group, **keeping
the class names** (props drive variants → classNames). They are the vocabulary every screen composes
from — mirror `docs/design/screens/S-00-component-library.html` (the catalog) for parity:

`Button` (`--primary/secondary/ghost/danger/danger-solid/sm`, disabled) · `Field`/`Input`/`Select`/
`Textarea` (+`--error`, help/error) · `Check` · `Strength` · `Badge` (run-state map
`queued/waiting/running/needs-answer/gate/done/failed/parked`) · `StatusDot` · `Chip`/`Chip--filter` ·
`Needs` (`clar/gate`) · `Avatar`(+group) · `Card`/`CardAttention` · `Panel`/`PanelHeader` · `Tabs` ·
`Table`(+`--matrix`) · `Switch` · `LifecycleRail` (node states + `Loop` + `Branch`, **type-adaptive**) ·
`Board`/`BoardCol`/`WiCard` · `GatePanel`/`CriteriaList`/`CriteriaItem` · `ClarificationCard` ·
`ArtifactRow`/`SorChip` (Confluence/Jira/Figma/GitHub/Xray) · `Console` · `Toast` · `Modal` · `Drawer` ·
`Banner` (info/warning/danger/success/purple) · `Tile` · `Todo` · `Segmented` · `CapCard`(+vendor
tints) · `Breadcrumb` · `MetaRow` · `Kv` · `CmdBlock`/`TokenReveal` · `Vstep` · `ConnStatus` ·
`Dropzone` · `Assess` · `VersionRow` · `DocPreview`/`Prose` · `DiagramFrame` · `GraphCanvas`/`GraphLegend` ·
`AuthSplit` · `Transcript`/`Turn` · `EmptyState` · `Skeleton`. **`<AppShell>`** ports `shell.js`
(`shellMount(navId, opts)` → `<AppShell active={navId} companion bell user admin>`): 240px navy sidebar
(nav ids above), 56px top bar (tenant/project switchers, companion pill, bell, avatar), companion pill
pinned bottom.

> Acceptance for T0: a `/dev/components` route (or Storybook-lite page) renders the library at **parity
> with `S-00`**, and `<AppShell>` renders for an authed user with the correct active nav.

## 3. Design-sensitive backend — **bucket B** (P4.8-T1; build alongside T0)

The endpoints whose shape needed the concrete screens. Same conventions as the 4.7 spec (tenant from
session, member perm, tests per endpoint).

| Endpoint | Backs | Response schema |
|---|---|---|
| `GET /api/projects/{id}/dashboard/` | **S-31** | `{needs_me:{gates:[{approval_id,gate,work_item,role}], clarifications:[{id,work_item,question,waiting_s}], my_runs:[{run_id,phase,work_item,status}]}, health:{work_items,phases_in_progress,awaiting_gate,published_week}, recent_publishes:[…]}` |
| `GET /api/work-items/{id}/lifecycle/` | **S-15/16/17** | `{tier:"plan"|"build"|"remediation", nodes:[{phase,label,state:not_started/running/needs_answer/awaiting_gate/done/failed,run_id?,triggerable:bool}], loops:[{from,to,count}], children:[{id,title,type,phase}], parent?:{id,title}}` — **type-adaptive** (epic→plan rail, task→build rail only); `triggerable` per node drives the S-18 trigger picker. |
| `GET /api/approvals/{id}/criteria/` + `criteria` on decide | **S-22** | generalized required-criteria checklist: `{criteria:[{id,text,required,satisfied,note?}], met,total, approve_enabled:bool}`; `decide` accepts `{satisfied:{id:bool}}` and blocks APPROVED while any required is unmet (generalize the WCAG `Approval.conditions` from Phase 3 — DECISION-6). |
| `GET /api/runs/{id}/transcript/` | **S-33** (new, **DECISION-7**) | persisted engine conversation, read-only: `{run_id,phase,engine,cost,turns:[{role:"agent"|"tool"|"human",body,meta?}]}`. Transcript stored in the DB (no retention window for now; user-facing retention later). |
| `POST /api/artifacts/{id}/publish/` | **S-34** (new, **DECISION-8**; reworked by the 2026-07-07 team flow decision — locked decision 9 in the continuation brief) | manual **gate-respecting** publish: `{target_capability: "internal"\|"docstore"\|"tasktracker"\|"testmgmt", destination?}` → a REAL capability push for a **gate-APPROVED (or re-exported published)** artifact; `400` if not approved (never bypasses a gate, #5) or if the target violates the **phase-scoped export policy** (`export_policy.py` defaults + `ProjectProfile.export_policy` overrides; `GET /api/projects/{id}/export-policy/` serves it). docstore transfers the SoR; tasktracker = backlog reconciliation (returns `{reconciled,created,items}`); testmgmt = `create_test` per `test_case` artifact (returns `{test_key}`); all return `{status,sor_link}`. Gate approval itself publishes internal-only — never auto-exports. |
| `PATCH /api/work-items/{id}/` **(gap A)** | **S-15/S-16** | edit a work item (`title,description,type`) — add `UpdateModelMixin` to `WorkItemViewSet` (the serializer already allows these writable; `state`/`external_ref`/`project` stay read-only). The "Edit" affordance has no endpoint today. |
| `GET /api/work-items/` filter+card deltas **(gap B)** | **S-14/S-15/S-23** | extend the list: filters `type` (board **Level**: epic/feature/task/story/defect), `parent` (epic→child tasks; S-23 fan-out), `phase` (keep `project`/`state`); card fields `artifact_count`, `owner`, `needs` (clarification/gate flags). Today the list filters only `project`+`state`. |
| `GET /api/phases/` **(gap C)** | **S-14/S-18** | static catalog of phases per tier — `{plan:[{key,label,agent_key,gate_role}], build:[…], remediation:[…]}` — for the board **phase-columns** and the S-18 trigger picker. (Pairs with `triggerable` on lifecycle nodes above.) |
| field deltas | various | add only what a screen renders and the existing payload lacks (e.g. board card `artifact_count`, `owner`, `needs` flags on the work-item list). Document each delta here when you add it. |

## 4. Per-task acceptance (P4.8-T2…T5)

For each screen the task owns (see `docs/SCREEN_BUILD_MAP.md`): implement **every labelled
`state-block`** from `S-NN.html`; compose **only** from `components/ui/`; wire reads/writes via Query
hooks to the named endpoints; **visual parity** with the mockup (tokens/classes); a11y (focus rings,
labelled fields, ≥4.5:1, status never colour-alone, ≥40px targets, `prefers-reduced-motion`); tests
(component render of each state + the happy-path interaction). Done = matches the gallery screen.

## 5. Dependency / parallel model

```
P4.8-T0 (shell + component lib + api/auth client + router)   ── gates all UI
P4.8-T1 (bucket-B backend)  ── parallel to T0; gates the screens that read it
        ▼
  P4.8-T2 identity   P4.8-T3 setup   P4.8-T4 lifecycle   P4.8-T5 brownfield+obs
   (own feature folder each — parallel-safe; shared files append-only)
        ▼
  P4.8-T6 guide PDF rewrite
```
FE streams build against this spec's contracts using **Query hooks over the typed client**, mocking a
4.7/bucket-B endpoint until it lands — BE and FE never block each other. Shared/append-only:
`api.ts`, `types.ts`, `routes.tsx`, `components/ui/index.ts`, `auth/AuthContext.tsx`. See `AGENTS.md`.

## 6. Verification

Build a feature → run the dev server → confirm each screen renders **all** its states and matches the
gallery (open the matching `docs/design/screens/S-NN.html` side-by-side); `npm run lint` + `tsc -b`
green; component tests pass; no stray hex/px (tokens only, same rule as the gallery).
