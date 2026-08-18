# SCREEN BUILD MAP — screen → states → components → endpoints → owner

The crosswalk a UI assistant uses to build a screen **end-to-end**. One row per screen. Pair with the
mockup `docs/design/screens/S-NN.html` (the visual + state source-of-truth), the component library
`docs/design/README.md` §catalog, and the endpoint contracts in `docs/PHASE_4.7_BUILD_SPEC.md` +
`docs/PHASE_4.8_BUILD_SPEC.md` (bucket B). **States** = the labelled `.state-block`s in the screen file;
build **all** of them. Keep this file in sync when screens or endpoints change (append-only / coordinate).

Legend — endpoints: `4.7-Tn` = Phase 4.7 task; `B` = Phase 4.8 bucket-B; `(exists)` = already built;
`(new)` = net-new from a locked decision. Owner = the BUILD_PLAN Phase-4.8 UI task.

| Screen | J# | States | Key components | Backend endpoints | Owner |
|---|---|---|---|---|---|
| **S-01** Sign up | J1 | default · email-in-use · submitting · success | AuthSplit, Field, Strength, Button, Banner | `POST /auth/signup` (4.7-T2) | T2 |
| **S-02** Log in | J4 | default · invalid · locked · submitting | AuthSplit, Field, Banner, Button | `POST /auth/login` (4.7-T1) | T2 |
| **S-03** Accept invite | J3 | default · expired-link · submitting | AuthSplit, Field, Strength, Empty | `POST /auth/accept-invitation` (4.7-T3) | T2 |
| **S-04** Reset password | J4 | request · sent · set-new · invalid-token · success | AuthSplit, Field, Vstep✓, Empty | `request-reset`,`reset` (4.7-T3) | T2 |
| **S-05** Setup checklist | J1 | all-incomplete · partial · complete-dismiss | Card, Vstep, Button, CardAttention | `GET /auth/me`, `GET /runners/`, onboarding state (4.7-T11/T8) | T2 |
| **S-06** Connect machine | J5 | not-started · token-generated · connected · offline | Vstep, TokenReveal, CmdBlock, ConnStatus | `POST /runners/` (exists), `GET /runners/` (4.7-T11) | T2 |
| **S-07** Users & invites | J2/J6 | populated · invite-drawer · dup-error · empty | Table, Drawer, Field, Badge, Avatar | `GET /users/`, `POST /invitations/` +resend/revoke (4.7-T4/T3) | T2 |
| **S-08** Roles matrix | J6 | gap-warning · saving · last-admin-guard | Table--matrix, Switch, Banner, Modal | memberships + `role-coverage/` (4.7-T4) | T2 |
| **S-09** Create project | J7 | default(greenfield) · brownfield · name-collision | Card, Segmented, Field, Banner | `POST /projects/` (exists) | T3 |
| **S-10** Project profile | J8 | clean(v3) · dirty · saving · validation | Panel, Field, SaveState | `GET/PUT profile/` (exists) | T3 |
| **S-11** Integrations grid | J9 | mixed · connection-failed · all-empty | CapCard(+vendor), Badge, Button | `GET /integrations/` (4.7-T6) | T3 |
| **S-12** Connect capability | J9 | empty · filled · testing · success · fail | Drawer, Field, Banner, Badge | `POST/PATCH /integrations/`, `test-connection/` (4.7-T6) | T3 |
| **S-13** Repositories | J10 | multi · add-form · single · duplicate · empty | Table, Chip, Field, Button | `…/repositories/` CRUD (4.7-T7) | T3 |
| **S-14** Work Items board | J11 | board · list · tasks-filtered · empty | Board, WiCard, Chip, Segmented, Needs | `GET /work-items/` +`type`/`parent`/`phase` filters +card deltas (B), `GET /phases/` (B) | T4 |
| **S-15** Work Item — Epic | J11 | gate-pending · running+needs-answer · all-complete | Rail(plan), Panel, ArtifactRow, Console, GatePanel | `work-items/{id}/lifecycle/` (B), `PATCH /work-items/{id}/` edit (B), artifacts/runs (exists) | T4 |
| **S-16** Work Item — Task | J16 | loop+test-failed · impl-running · merge-gate · done | Rail(build,loop,branch), ArtifactRow(PR), Console, GatePanel | `…/lifecycle/` (B), `PATCH /work-items/{id}/` edit (B) | T4 |
| **S-17** Work Item — Defect | J16 | open · fixing · closed | Rail(remediation), Banner, Console, Kv | `…/lifecycle/` (B) | T4 |
| **S-18** Phases & Runs | J12 | online-triggerable · offline-blocked · no-runs | PhasePicker, Table, Banner, ConnStatus | `GET /runs/`, `GET /phases/` (B), trigger (4.7-T5), `GET /runners/` (4.7-T11) | T4 |
| **S-19** Run console | J12 | dispatched · running · needs-answer · awaiting-gate · completed · failed · parked | Console, Badge, Banner, MetaRow | `GET /runs/{id}/` (exists) | T4 |
| **S-20** Clarifications | J13 | one(confirm) · multi · required-error · already-answered · cancelled · empty | ClarificationCard, Field, Check, Badge | `GET /clarifications/`, `answer/` (exists; actor 4.7-T5) | T4 |
| **S-21** Gates | J14 | can-decide · cannot-decide · decided-history · empty | Table, GatePanel, Banner, Tabs | `GET /approvals/`, `decide/` (exists; actor 4.7-T5) | T4 |
| **S-22** Criteria gate | J15 | none · partial · all-ticked · rejected | GatePanel, CriteriaList, CriteriaItem | `approvals/{id}/criteria/` + decide (B) | T4 |
| **S-23** Task breakdown | J16 | pushed-to-jira · internal-only | Card, Banner, ArtifactRow, Tile | `GET /work-items/?parent=` child tasks (B), post-approval read (exists) | T4 |
| **S-24** Onboarding hub | J17 | nothing-done · in-progress · gap-ready | Vstep, Dropzone, Banner, ConnStatus, CardAttention | `GET …/onboarding/`, `code-intel/`, `gap-report/` (4.7-T8) | T5 |
| **S-25** Source documents | J17 | empty · uploading · extracted · adopt-gate · adopted | Dropzone, ArtifactRow, DocPreview, Banner | upload + `adopt/` (exists), hub (4.7-T8) | T5 |
| **S-26** Gap report | J17 | partial · empty · mature | Table, Assess, CardAttention, Button | `GET …/gap-report/` (4.7-T8) | T5 |
| **S-27** Contracts & drift | J18 | healthy · drift-pending · wrong-role · decided | Table, Tabs, GatePanel, Banner | `api-contracts/`, `drift/`, `drift/{id}/decide/` (4.7-T9) | T5 |
| **S-28** Artifacts registry | J19 | populated · internal-only · empty | Table, Badge, SorChip, Button, Field | `GET /artifacts/` (exists) | T5 |
| **S-29** Artifact preview | J19 | markdown · diagram · external · body-unavailable | DocPreview/Prose, DiagramFrame, VersionRow, Banner, SorChip | `artifacts/{id}/preview/` (4.7-T10) | T5 |
| **S-30** Traceability | J20 | small · highlighted · large-cluster · empty | GraphCanvas, GraphLegend, Select | `…/traceability/` (exists) | T5 |
| **S-31** Dashboard | J22 | busy · calm · new-project | Tile, Todo, ConnStatus, Vstep, Kv, Panel | `…/dashboard/` (B) | T5 |
| **S-32** Offline takeover | J21 | parked · reconnecting · resumed | Card, Banner, ConnStatus, Console, Kv | `GET /runners/` (4.7-T11), `take-over/` (exists) | T5 |
| **S-33** Run transcript | persist | runs-list · transcript · empty | Table, Transcript/Turn, Banner | `GET /runs/{id}/transcript/` **(new, DECISION-7)** | T5 |
| **S-34** Export / publish | publish | choose-target · publishing · success · blocked | Modal, Field, Banner, SorChip | `POST /artifacts/{id}/publish/` **(new, DECISION-8, gate-respecting)** | T5 |
| **S-35** Test cases | 09b | list · coverage tab · generate · empty | Table, Tabs, Chip, Button | test-case work items (exists) | T4 |
| **S-36** Accessibility review | a11y | default(queue+item) · actual-size · tall/no-capture · loading · submitted · locked-by-other · **not-your-role** · error · empty | ArtifactRow (queue rail), Panel, **Shot**, Banner, Field, Toast, Skeleton, Empty, Badge, Tabs, **`grid--console`** | queue + adjudicate + **screenshot read-through** + **lock/claim** **(all new, QA-23)** | QA-23 |
| **S-37** Conformance / VPAT | a11y | per-criterion · draft-edit · export-refused · signing · signed · empty | Table, Tile, ArtifactRow, Check, Field, GatePanel, Banner, Tabs | conformance artifact + sign + export **(new, QA-24; gate-respecting)** | QA-24 |

## Notes for builders

- **S-36 `Shot` is a new component** (`components.css`, rendered in `S-00`): a captured page is routinely 2560px wide and taller than the viewport, and the existing `.diagram-frame` is a centred *placeholder* with no overflow handling — it breaks the panel. `Shot` has two modes and both are needed: **fit** to judge layout, **actual size** to judge the things a scaled image destroys (contrast, focus rings, text size).
- **S-36/S-37 are one destination, not two pages.** Both live under the new **Accessibility** sidebar item (`shell.js`, count badge like Gates): S-36 is the landing page, S-37 its second tab. Always present — never revealed by a run, or "no menu" and "never checked" look the same.
- **S-36 is a rail + workspace (`grid--console`), not a sidebar layout (`grid--detail`)** — D-A11Y-99. The first draft used `grid--detail` (`1fr` + a 320px sidebar) with the queue in the wide slot, which put the panel a reviewer actually *works* in into the 320px sidebar and clipped its own decision buttons off the panel edge at 1280px. The list is the narrow half and the item under review is the wide half. Build it that way.
- **S-36/S-37 have no endpoints yet.** They are the UI half of QA-23 and QA-24. The queue already exists as a query over the findings ledger (QA-12a), but **four things do not exist and the mockup needs them** (D-A11Y-98): element bounding boxes, a screenshot read-through endpoint, confirm-flips-outcome-to-failure, and a lock field on the finding.
- **Never show the engine, prompt version or scanner version on S-37** (D-A11Y-96). They are recorded on the export and are not the client's business.
- **S-35 was missing from this map** until 2026-08-18 — the file existed with no row. Added above.

- **Type-adaptive rail (S-15/16/17):** the `lifecycle/` endpoint returns `tier` — render the plan rail
  for epics, the build rail (only) for tasks, the remediation rail for defects. Never show plan phases
  on a task (the §6.0 rule in the journeys spec).
- **S-33/S-34 new endpoints** are the only net-new backend in Phase 4.8 beyond bucket B — decided this
  session (DECISION-7 persist transcript read; DECISION-8 manual gate-respecting publish). Their
  contracts are stubbed in the 4.8 spec §3; build the read/publish endpoints alongside the screen.
- **"exists" endpoints** still need 4.7-T5's actor change (session user) before the UI drops the
  hand-entered `user_id`.
- Component names map 1:1 to `components.css` classes — see `docs/PHASE_4.8_BUILD_SPEC.md` §2 and the
  live catalog `docs/design/screens/S-00-component-library.html`.
