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
| **S-08** Roles matrix | J6 | gap-warning · saving · last-admin-guard | Table--matrix, Switch, Banner, Modal | memberships + `role-coverage/` (4.7-T4). *2026-09-12 (`b40c557`): gap warning shows whenever a gate role is uncovered (one line, names ≤2 / counts beyond); project is plain text, not a dropdown* | T2 |
| **S-09** Create project | J7 | default(greenfield) · brownfield · name-collision | Card, Segmented, Field, Banner | `POST /projects/` (exists) | T3 |
| **S-10** Project profile | J8 | clean(v3) · dirty · saving · validation | Panel, Field, SaveState | `GET/PUT profile/` (exists) | T3 |
| **S-11** Integrations grid | J9 | mixed · connection-failed · all-empty | CapCard(+vendor), Badge, Button | `GET /integrations/` (4.7-T6). *2026-09-11 (`4ac75f9`, N1): no Code intelligence card — auto-provisioned* | T3 |
| **S-12** Connect capability | J9 | empty · filled · testing · success · fail | Drawer, Field, Banner, Badge | `POST/PATCH /integrations/`, `test-connection/` (4.7-T6) | T3 |
| **S-13** Repositories | J10 | multi · add-form · single · duplicate · empty | Table, Chip, Field, Button | `…/repositories/` CRUD (4.7-T7) | T3 |
| **S-14** Work Items board | J11 | board · list · tasks-filtered · empty | Board, WiCard, Chip, Segmented, Needs | `GET /work-items/` +`type`/`parent`/`phase` filters +card deltas (B), `GET /phases/` (B) | T4 |
| **S-15** Work Item — Epic | J11 | gate-pending · running+needs-answer · all-complete | Rail(plan), Panel, ArtifactRow, Console, GatePanel | `work-items/{id}/lifecycle/` (B), `PATCH /work-items/{id}/` edit (B) — **built 2026-09-30**, artifacts/runs (exists) | T4 |
| **S-16** Work Item — Task | J16 | loop+test-failed · impl-running · merge-gate · done | Rail(build,loop,branch), ArtifactRow(PR), Console, GatePanel | `…/lifecycle/` (B), `PATCH /work-items/{id}/` edit (B) — **built 2026-09-30** | T4 |
| **S-17** Work Item — Defect | J16 | open · fixing · closed | Rail(remediation), Banner, Console, Kv | `…/lifecycle/` (B), `PATCH /work-items/{id}/` edit (B) — **built 2026-09-30** | T4 |
| **S-18** Phases & Runs | J12 | online-triggerable · offline-blocked · no-runs | PhasePicker, Table, Banner, ConnStatus | `GET /runs/`, `GET /phases/` (B), trigger (4.7-T5), `GET /runners/` (4.7-T11) | T4 |
| **S-19** Run console | J12 | dispatched · running · needs-answer · awaiting-gate · completed · failed · parked · **paused** | Console, Badge, Banner, MetaRow, ConfirmDialog | `GET /runs/{id}/`, `POST /runs/{id}/pause/`, `POST /runs/{id}/resume/` | T4 |
| **S-20** Clarifications | J13 | one(confirm) · multi · required-error · already-answered · cancelled · empty | ClarificationCard, Field, Check, Badge | `GET /clarifications/`, `answer/` (exists; actor 4.7-T5) | T4 |
| **S-21** Gates | J14 | can-decide · cannot-decide · decided-history · empty | Table, GatePanel, Banner, Tabs | `GET /approvals/`, `decide/` (exists; actor 4.7-T5) | T4 |
| **S-22** Criteria gate | J15 | none · partial · all-ticked · rejected | GatePanel, CriteriaList, CriteriaItem | `approvals/{id}/criteria/` + decide (B) | T4 |
| **S-23** Task breakdown | J16 | pushed-to-jira · internal-only | Card, Banner, ArtifactRow, Tile | `GET /work-items/?parent=` child tasks (B), post-approval read (exists) | T4 |
| **S-24** Onboarding hub | J17 | nothing-done · in-progress · gap-ready | Vstep, Dropzone, Banner, ConnStatus, CardAttention | `GET …/onboarding/`, `code-intel/`, `gap-report/` (4.7-T8) | T5 |
| **S-25** Source documents | J17 | empty · uploading · extracted · adopt-gate · adopted | Dropzone, ArtifactRow, DocPreview, Banner | upload + `adopt/` (exists), hub (4.7-T8) | T5 |
| **S-26** Gap report | J17 | partial · empty · mature | Table, Assess, CardAttention, Button | `GET …/gap-report/` (4.7-T8) | T5 |
| **S-27** Contracts & drift | J18 | healthy · drift-pending · wrong-role · decided | Table, Tabs, GatePanel, Banner | `api-contracts/`, `drift/`, `drift/{id}/decide/` (4.7-T9) | T5 |
| **S-28** Artifacts registry | J19 | populated · internal-only · empty | Table, Badge, SorChip, Button, Field | `GET /artifacts/`, `GET /artifacts/{id}/download/` | T5 |
| **S-29** Artifact preview | J19 | markdown · diagram · external · body-unavailable | DocPreview/Prose, DiagramFrame, VersionRow, Banner, SorChip | `artifacts/{id}/preview/` (4.7-T10), `artifacts/{id}/download/` | T5 |
| **S-30** Traceability | J20 | small · highlighted · large-cluster · empty | GraphCanvas, GraphLegend, Select | `…/traceability/` (exists). *2026-09-12 (`b40c557`): live Phase / Type filters + Highlight work item (dims the rest; "Not tied to a work item" group); nodes carry `work_item`/`work_item_key`/`work_item_title`* | T5 |
| **S-31** Dashboard | J22 | busy · calm · new-project | Tile, Todo, ConnStatus, Vstep, Kv, Panel | `…/dashboard/` (B) | T5 |
| **S-32** Offline takeover | J21 | parked · reconnecting · resumed | Card, Banner, ConnStatus, Console, Kv | `GET /runners/` (4.7-T11), `take-over/` (exists) | T5 |
| **S-33** Run transcript | persist | runs-list · transcript · empty | Table, Transcript/Turn, Banner | `GET /runs/{id}/transcript/` **(new, DECISION-7)** | T5 |
| **S-34** Export / publish | publish | choose-target · publishing · success · blocked | Modal, Field, Banner, SorChip | `POST /artifacts/{id}/publish/` **(new, DECISION-8, gate-respecting)** | T5 |
| **S-35** Test cases | 09b | list · coverage tab · generate · empty | Table, Tabs, Chip, Button | test-case work items (exists) | T4 |
| **S-36** Accessibility review | a11y | default(queue+item) · actual-size · tall/no-capture · loading · submitted · locked-by-other · **not-your-role** · error · empty | ArtifactRow (queue rail), Panel, **Shot**, Banner, Field, Toast, Skeleton, Empty, Badge, Tabs, **`grid--console`** | `GET/POST projects/:id/a11y-review/` + `…/<finding>/` + `…/<finding>/screenshot/` **(built, QA-23)** | QA-23 🟡 |
| **S-37** Conformance / VPAT | a11y | per-criterion · draft-edit · export-refused · signing · signed · empty | Table, Tile, ArtifactRow, Check, Field, GatePanel, Banner, Tabs | conformance artifact + sign + export **(new, QA-24; gate-respecting)** | QA-24 |

## Notes for builders

- **S-36 `Shot` is a new component** (`components.css`, rendered in `S-00`): a captured page is routinely 2560px wide and taller than the viewport, and the existing `.diagram-frame` is a centred *placeholder* with no overflow handling — it breaks the panel. `Shot` has two modes and both are needed: **fit** to judge layout, **actual size** to judge the things a scaled image destroys (contrast, focus rings, text size).
- **S-36/S-37 are one destination, not two pages.** Both live under the new **Accessibility** sidebar item (`shell.js`, count badge like Gates): S-36 is the landing page, S-37 its second tab. Always present — never revealed by a run, or "no menu" and "never checked" look the same.
- **S-36 is a rail + workspace (`grid--console`), not a sidebar layout (`grid--detail`)** — D-A11Y-99. The first draft used `grid--detail` (`1fr` + a 320px sidebar) with the queue in the wide slot, which put the panel a reviewer actually *works* in into the 320px sidebar and clipped its own decision buttons off the panel edge at 1280px. The list is the narrow half and the item under review is the wide half. Build it that way.
- **S-36 and S-37 are both built** (QA-23 and QA-24, 2026-08-18), and they are now one destination with two tabs, as the mockup drew it. The four things D-A11Y-98 said the mockup needed now all exist: the page screenshot's pointer is kept (the element boxes were already captured — see D-A11Y-100), the read-through endpoint serves it, confirming flips the outcome to `failure` so a real defect opens, and the finding carries a review lock with automatic release.
- **Never show the engine, prompt version or scanner version on S-37** (D-A11Y-96). They are recorded on the signature's ledger entry and are not the client's business — `test_the_versions_never_reach_the_screen` greps the API payload for them, so this is enforced rather than remembered.
- **S-35 was missing from this map** until 2026-08-18 — the file existed with no row. Added above.

- **Editing a work item (S-15/16/17) is one component, and it is frontend-only** — built 2026-09-30
  (Bugs S.No 76). `EditWorkItem.tsx` opens from an **Edit** button in the page header of all three
  screens, and calls the `PATCH /work-items/{id}/` that had been live and tested since Phase 4.8 with
  no screen calling it. **Title and description only.** Type is writable on the serializer but is
  deliberately not offered: changing a Story to an Epic mid-lifecycle changes which phases apply and
  which rail is drawn, which is a lifecycle decision rather than a correction. If that is ever wanted,
  it is its own decision with its own consequences — do not slip it into this form.
- **A cancelled work item can be reopened (S-14/15/16/17)** — built 2026-09-30 (Bugs S.No 285).
  There is **no delete** and there should not be one: work items are referenced by runs, gates,
  artifacts, trace edges and ledger events. Cancel is the closure, and it is now reversible —
  `cancelled → proposed` only, so the item returns to Backlog as a draft rather than to a phase whose
  run is long gone. Reopen is offered in the board's cancelled list (behind the existing
  "N cancelled hidden" chip) and in a cancelled item's own header. Reopening a **defect** withdraws
  the acknowledgement its cancellation put on the pending gate — the release and its disclosure ship
  together in both directions.
- **Never draw `parent` (S-14/15/16/17)** — added 2026-09-30 (Bugs S.No 288). `parent` is a UUID.
  `WorkItemSerializer` now serves **`parent_key`** ("WI-260") alongside the item's own `key`, and
  that is what any screen naming a parent renders — the board card's `↖` chip, the breadcrumb, the
  `Parent` link. Where there is no key, draw **nothing**: a chip reading `↖ 65db8214` names nothing
  and costs the reader a click to find out. `WorkItemViewSet` must keep its `select_related("parent")`
  or `parent_key` becomes one query per card on an unpaginated board; a test holds the query ceiling.
- **BUILT 2026-10-06, and it was not built before.** The endpoint worked `tier` out and then never
  used it, so every work item type rendered all 19 phases while each caption claimed otherwise —
  exactly what the rule below forbids. Which phases belong to which tier now lives in ONE place,
  `apps/registry/catalog.py` (`PLAN_PHASE_KEYS` / `BUILD_PHASE_KEYS` / `REMEDIATION_PHASE_KEYS`),
  beside the agents themselves. Do not re-derive it per screen or from a key's leading digits —
  that prefix rule is what mis-filed UX Design and Task Breakdown as build work (Bugs S.No 321).
  Two things to know before changing it: **remediation is a SELECTION over build, never a partition
  of it** (those phases belong to tasks too — carving them out empties the task rail), and the
  **plan RAIL is the plan tier minus onboarding** (onboarding belongs to a project, not a work item,
  while the phase CATALOG must still offer it so brownfield can trigger it).
- **Type-adaptive rail (S-15/16/17):** the `lifecycle/` endpoint returns `tier` — render the plan rail
  for epics **and stories**, the build rail (only) for tasks, the remediation rail for defects. Never
  show plan phases on a task (the §6.0 rule in the journeys spec). **A `story` is a planning item** —
  settled 2026-09-21 (Screen Words group 9, Option A): the endpoint's `plan` for a story is right and
  the journeys spec was corrected to match. Rail headings read "Lifecycle — Planning" and
  "Lifecycle — Delivery"; the word "tier" is not shown. A phase that has not started reads
  **"Not started"**, never "Upcoming" — the hollow numbered circle already says "not yet", and on a
  new work item that word repeated under all nine phases (Bugs S.No 335).
- **"At a glance" (S-15/16/17) is one card with one set of rows**, built from the shared helpers in
  `features/lifecycle/glance.tsx` — three hand-written copies is how the three screens drifted into
  asking three different sets of questions (Bugs S.No 331). Two rules it encodes: **a count is a link
  only above zero** (a zero that leads to "Nothing matched this filter" reads as a failure when the
  work item has simply not run — S.No 333), and **the clarification count is "Open clarifications"**,
  because the query behind it has only ever asked for `status=pending`; the answered history lives on
  the Clarifications screen's History tab, which is phase-aware (S.No 334). The count links to
  `/clarifications?work_item=…`, which narrows the **pending list only** — narrowing a history by an
  invisible filter is the more dangerous of the two.
- **S-33/S-34 new endpoints** are the only net-new backend in Phase 4.8 beyond bucket B — decided this
  session (DECISION-7 persist transcript read; DECISION-8 manual gate-respecting publish). Their
  contracts are stubbed in the 4.8 spec §3; build the read/publish endpoints alongside the screen.
- **"exists" endpoints** still need 4.7-T5's actor change (session user) before the UI drops the
  hand-entered `user_id`.
- Component names map 1:1 to `components.css` classes — see `docs/PHASE_4.8_BUILD_SPEC.md` §2 and the
  live catalog `docs/design/screens/S-00-component-library.html`.


### S-19: `paused` is not `parked`, and the difference is load-bearing (2026-10-03)

Two states that look alike on a status chip and must never share wording:

- **`parked`** (`Run.status == "stalled"`) — something went **wrong**. The reader is told what. It
  is deliberately **excluded** from the re-trigger guard, so starting the phase again is valid.
- **`paused`** (`Run.status == "paused"`) — somebody **chose** to stop. No error is shown, because
  showing one would call their own decision a fault. It **is** in the re-trigger guard, so the phase
  cannot be started again while it is paused; the way out is Resume or Discard.

The second button is the **same action** under two labels: `Take over` when parked, `Discard this
run` when paused. Do not add a third endpoint for it.

**Pause is offered only while a run is `pending` or `running`.** Never at a gate — that run is
already stopped.

**Any screen that starts a phase asks first** (S-18, S-15/16/17, S-13, S-19's retry, S-32), through
the shared `ConfirmDialog` in `components/ui`. There is no longer a trigger that fires on one click,
and a new one must not be added.


### S-28 / S-29: Download is not Export, and `downloadable` is not `previewable` (2026-10-03)

**Export writes; Download does not.** Export opens the publish screen, which pushes the document
into Confluence or Jira — a gated write to a system of record. Download reads a body and streams it:
no status change, no export record, no gate. They sit a few pixels apart on the row and must stay
visibly different (a link to `/publish` versus a button). Before Download existed, Export was the
only control that looked like "get me a copy", which is what this closed.

Their eligibility rules are deliberately different too:

| | Shown when |
|---|---|
| `previewable` | there is anything to show — a body, **or** a link to follow |
| `downloadable` | the platform actually **holds** the document (its own artifacts, and Confluence pages) |
| Export | the gate has passed (`approved` / `published`) **and** `previewable` |

So a Figma row previews and exports but does not download; a draft downloads but does not export.
Both flags are computed **server-side** in `integrations/preview.py`, beside the reader whose
branches they mirror, and are carried on the list payload and the preview payload. Do not
re-implement either rule in TypeScript — that is what `previewable` was added to prevent.

**Filenames go through `api/files.py`.** Every file this product serves is named after text an agent
or a user wrote, and that name goes into an HTTP header. Use `attachment_response` / `inline_response`
rather than building `Content-Disposition` by hand; they sanitise the name and write both the ASCII
and the UTF-8 form (RFC 6266).

### S-19: what the run console SAYS is owned by the platform (2026-10-05)

Every line in the progress list is a sentence the **server** chose, from `EVENT_SENTENCES` in
`backend/api/serializers.py` — one entry per event action a run can own, with an optional tail. The
screen prints what it is given and composes nothing. Do not rebuild any of this in TypeScript; that
is the `previewable` lesson, and here it is worse, because the wording is the whole feature.

Before this, each line was the event's internal action key with its punctuation swapped for spaces,
plus the first value found in the payload under a nine-key fallback chain. Seven actions had real
sentences; thirty-six read as "Review parse mismatch" and "Phase dispatched — 06_task_breakdown",
and one of them printed a database exception. The Screen Words guard
(`tests/test_refusal_wording.py`) could not see any of it — the sentences existed nowhere as
literals.

**Two rules worth knowing before changing anything here:**

| | |
|---|---|
| **A tail is opt-in** | An action declares whether it has one and where it lives. Only `error`, `reason`, `comment` and `title` may supply one, and each was read at its call site. Nothing else is ever appended. |
| **A copied tail must read as prose** | More than one line, or a word like "exit code" or "stderr", means a log excerpt, and it is dropped. The failure classifier passes an unrecognised reason through verbatim by design, and the ledger is append-only, so the read side has to recognise one. |

`tests/test_event_wording.py` walks the backend for every `log_event` call recorded against a run and
fails if any action has no sentence — so adding an event is also adding its words. The one hole it
cannot close is the MCP `log_event` tool, which lets an agent record anything; that is why
`get_message` still humanises an unknown key rather than rendering a blank line.

**The frontend shares one rule with it:** `readsAsSentence` in `frontend/src/labels.ts` mirrors the
backend's prose check, and the failure banner uses it on the stored reason. The two are deliberately
the same rule, because they are shown a few pixels apart.

No run id appears on S-19 or on the offline-takeover screen. The work item's key and the phase name
the run in words; the id is in the address bar for support.

### S-05 / S-06 / S-18 / S-19: "is my machine there?" has exactly one answer (2026-10-05)

**One hook, `useCompanionStatus(projectId)` in `features/identity/hooks.ts`.** Every surface that
shows or acts on companion status reads it — the status pill in both places, Phases & Runs' trigger
gating, the three per-item triggers (S-15/16/17 via `CompanionGate`), the run console's stranded
banner, and the drop banner in the shell. Nothing derives this from `useRunners` again.

**Why it is a hook and not two lines at each call site.** It used to be two lines, in two places,
and both were wrong in the same way: `runners.some(r => r.online)` asks "is any machine of mine
alive on **any** project?", so a companion serving another project kept the pill green — and kept
S-18's phase buttons enabled — while the machine running the phase on screen was dead. Scoping has
to be decided once. (Bugs S.No 306.)

**Three states, not two.** `ready` · `checking…` · `offline`, plus `unknown` before the first answer
arrives, which renders as not-connected so nothing ever claims a machine is there before asking.
The amber `checking` band exists because a companion heartbeats every 30s but the platform only
calls it gone after `ONLINE_THRESHOLD` (2 min), leaving a 2¼-minute window in which the screen was
confidently wrong. **Do not close that window by shortening `ONLINE_THRESHOLD`** — the same constant
picks which enrollment a dispatch routes to and how long a claim lease survives (S.No 84, 111, 134).
The band buys the warning without touching any of it. (Bugs S.No 307.)

**The elapsed time comes from the server** (`age_s`, `apps/runs/enrollment.py`), not from
subtracting `last_seen` in the browser: the band is a judgement about time, and a wrong device clock
would otherwise paint a healthy machine as dying.

### S-19 and S-15/16/17: read the dispatch, never the run status, to ask "has a machine got this?"

`dispatch_phase_core` sets a run to **RUNNING** at the moment it is sent out, while leaving
`inputs.dispatch.status` at `"pending"` until a machine claims it. So by status alone a stranded run
and a run being actively worked on are indistinguishable — which is how a phase sent to a dead
machine came to render a live console, spinner and all, until the 2h takeover. Use
`dispatchUnclaimed(run.inputs)` from `types.ts`; it is the one place that shape is narrowed, for the
same reason `workerStalled` is. (Bugs S.No 308, 310.)

Stranded = unclaimed **and** the companion for the **run's own** project is offline. Both halves are
required: unclaimed with a live machine is a run about to start, and offline with a *claimed*
dispatch is a machine working away that has merely gone quiet — telling that reader to reconnect
would discard work in progress.

### Starting work is refused on the server too, not only on the screen

The screens grey their triggers, but the status a page holds can be up to `ONLINE_THRESHOLD` old and
a page open since before the drop knows nothing at all. `POST /work-items/{id}/trigger/` therefore
calls `companion_liveness_for` and refuses a **`"stale"`** companion with a client-safe sentence
(reusing `NoCompanionError`, already mapped to a non-field error). It refuses only that one of the
four states: `"never"` is onboarding's mint-token-then-trigger-then-connect path and `"none"` is a
legitimate server-mode run, and collapsing either into the refusal breaks a real journey. The guard
lives in the **view**, not in `trigger_phase`, which is also called by the onboarding/vision hooks,
CI, and most of the test suite. (Bugs S.No 309.)
