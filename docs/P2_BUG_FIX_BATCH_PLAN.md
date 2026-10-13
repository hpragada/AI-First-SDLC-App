# P2 BUG-FIX BATCH — build plan for team review

**Status: APPROVED, BUILT AND MERGED — 7 September 2026.** All ten waves shipped, one commit each;
`develop` carries them and the three migrations are applied.

**This document is the plan as approved, and is deliberately left as it was written.** It records
what the team agreed to, not what happened afterwards — letting it drift into a build log would
destroy the only account of what was actually signed off. For what shipped, what was decided along
the way and what was found after the merge, read
[SDLC_BUG_FIX_ENHANCEMENTS.md](SDLC_BUG_FIX_ENHANCEMENTS.md).

**Branch:** built on `SDLC_Bug_Fix_Enhancements`, merged into `develop` at `eab96e9` (`--no-ff`, so
the whole batch reverts in one step).
**Companion document:** [CONNECT_MACHINE_REDESIGN_SPEC.md](CONNECT_MACHINE_REDESIGN_SPEC.md) —
written and complete; that work is parked for later implementation.

Read §1 and §2 first. §3 onward is the per-item detail, and each wave stands on its own — you can
review them in any order, or split them between reviewers.

---

## 1. What this batch is

The P1 defects and the platform-wide "a link drops its context" problem shipped earlier on this
branch. The team then reviewed the **24 open P2 rows** in `Bugs.xlsx` and selected this batch.

| Outcome | Rows |
|---|---|
| **Already fixed — close the row, no code** | S.No 181, 189, 217 |
| **Built in this batch** | S.No 87, 88, 140, 187, 198, 211, 219, 221, 223, 236, 237 |
| **Spec written, implementation parked** | S.No 35 (+ S.No 138, folded in) |
| **Approved but sequenced after one live security run** | S.No 178 |
| **Dropped — the Work Items dashboard redesign owns it** | S.No 213 |
| **Parked untouched (Group C)** | S.No 75, 78, 79, 210 |

### Decisions the team has already made

This plan implements these. It does not re-open them.

| Item | Decision |
|---|---|
| **A1 · S.No 187** | The platform renders machine-readable bodies to markdown, and **the raw body is kept** |
| **B2 · S.No 88** | Absorb the external merge, sweep for missed ones, webhook as delivery — and the bypass is **acknowledged by a human** |
| **B3 · S.No 140** | A terminal `cancelled` state plus a gated human transition. Cancelling a defect **releases** the gate it blocked **and the gate says so**. **Tech lead or admin** may cancel. Cancelled items are **hidden from the board by default**, with a filter |
| **B8 · S.No 236 + 237** | Validate the pointer; select candidates on "has no tracker id" — and **a re-export must never move an item already past `accepted`**, pinned by a test |
| **B9 · S.No 35** | Full experience, layers 1–5 — spec only, no code this batch |

---

## 2. Three corrections we owe the team

Recon after the options discussion overturned three things stated earlier. All three are recorded
here and will be corrected in the Bugs.xlsx rows themselves.

1. **The "405 infinite merge loop" on S.No 88 does not exist.** `merge_build_pr_core`
   (`backend/orchestration/build_activities.py:386-418`) already reads the PR first and
   short-circuits on `if not pr.merged:` — its docstring says *"Idempotent — an already-merged PR
   is a no-op."* **This makes the fix smaller and safer than described:** the workflow already
   completes correctly the moment any approval arrives. The bug is only that nobody ever approves,
   and nothing tells them they should.
2. **S.No 87 is already half-fixed.** Commit `83a2036` added a server-side block on agents setting
   `done`. The row records a hole that is partly shut.
3. **`Project.Track` has two values, not three** — greenfield and brownfield. "Multi" is
   `repo_topology`, a different field.

**And one item grew rather than shrank.** S.No 140 is not "add a state". `cancelled` is a new
**terminal** state, and the codebase encodes "terminal" as `== done` in about ten places —
including **seven that would silently un-cancel an item** and **three gate queries** that would
hold a gate shut on a cancelled defect for ever. That is why it is sequenced last and why it
carries the most tests.

---

## 3. Ground rules

- **Read-only on shared infrastructure.** Migrations are written, **never run** — the team runs
  them. No Temporal workflow is terminated. Nothing touches the shared server.
- **Never run the full backend suite** — it gets SIGKILLed. Only the test files named per wave.
- **Every fix gets a test that fails before it and passes after it.** Where that is impossible (a
  new capability), the commit says so.
- **Baseline first** (`git stash`, run, record, unstash) so no pre-existing failure is
  misattributed. Known pre-existing: `test_acceptance_phase47`, one `test_webhook_reconcile` test,
  `test_gate_service::test_default_signal_sender_resumes_real_workflow` (hangs), 4 type errors in
  `observability.test.tsx`, 71 ruff errors, 147 mypy errors.
- **`Bugs.xlsx` carries in-cell screenshots** — openpyxl drops them on save. Row edits go through
  the XML-in-zip script only.

---

## 4. Wave 0 — Close three rows that are already fixed

No code. Each was verified in the codebase.

| Row | Why it is closed | Evidence |
|---|---|---|
| **S.No 181** — a failed initial build was terminal | The initial dispatch is wrapped in a retry loop and parks on a failed first report — exactly the row's own planned fix | `backend/orchestration/build_workflow.py:118,161` |
| **S.No 189** — only the top gate was actionable | Every pending row is selectable, drives the decision panel, and is highlighted when selected — the team-selected Option A | `frontend/src/features/lifecycle/Gates.tsx:64,73,220,241` |
| **S.No 217** — `/recovery?run=` was inert | The screen fetches the named run, both loading branches are guarded, and the run console now produces the URL | `frontend/src/features/observability/OfflineTakeover.tsx:24-45` |

---

## 5. Wave 1 — A1 · S.No 187: machine-readable artifacts render as a wall of text

### The defect
The preview claims **every** internal artifact is markdown, whatever it actually contains
(`backend/integrations/preview.py:151-154`). Agent 10 is told to *"register the CycloneDX JSON
output as an `sbom` artifact"* (`agents/10_security/agent.md:235-239`), so JSON is handed to the
markdown renderer and collapses into a run-on blob.

### Three findings that shape the fix

1. **The format machinery that should have prevented this is dead code.** The format map knows only
   markdown/md/html/text/plain — **no json, yaml, xml or csv** — and **nothing anywhere writes the
   format field**. `register_artifact` has no `format` parameter at all. Both halves are
   unreachable.
2. **The frontend is already safe.** The preview screen renders HTML, then markdown, then falls
   through to a plain preformatted block. **JSON would already be legible if the backend told the
   truth.** No frontend work is needed.
3. **Three readers share the same body reader, and only one may change:**

| Reader | Used by | Must return |
|---|---|---|
| `read_artifact_preview` | The human preview screen | **Rendered** |
| `internal_draft_body` | Publish/export, quality services, test cases | **Raw** |
| `artifact_body_for_agent` | MCP `get_artifact_body` — what agents read | **Raw** |

Putting the renderer in the shared reader would hand an agent a markdown table where it asked for
parseable JSON. **The renderer attaches to the preview reader only.**

### The fix
- **(a)** Detect the real format on the S3 path and declare it honestly; add json/yaml/xml/csv to
  the map. This alone makes the SBOM legible, via the existing frontend fallback — the safety net
  under everything else.
- **(b)** Give `register_artifact` a real `format` parameter so an agent can declare rather than
  the platform guess, with detection as the fallback.
- **(c)** A presentation step in the preview reader only, keyed on artifact type: an `sbom` with a
  JSON body renders as metadata, component count, and a components table (name, version, licence,
  purl), plus vulnerabilities when present. Modelled on the existing `render_structured_ref`
  (`preview.py:119`), reusing its helpers. The preview already renders GitHub-flavoured markdown
  with wide-table scrolling, so tables work with no frontend change.
- **(d)** Pin agent 04's `api_spec` output as markdown. It is told to produce an "OpenAPI 3.0-style
  specification"; today it emits prose, but nothing requires that, and raw YAML would break
  identically.

**Size discipline:** a large SBOM must be **summarised, not truncated** — a bounded table with an
explicit "showing N of M components", so nobody is silently shown a partial inventory.

**Deliberately unchanged:** publish keeps pushing the raw body. Whether an exported SBOM should be
JSON or the rendered table is a separate product question.

### Tests
A JSON body previews as a table; the same artifact read by an agent and by publish still returns
**byte-identical raw JSON** (the regression guard that matters most); an oversized SBOM summarises;
malformed JSON degrades to plain text rather than raising.

---

## 6. Wave 2 — A3 · S.No 198 + 223: a fake token, and a project picker that does nothing

Two rows, one file: `frontend/src/features/identity/ConnectMachine.tsx`.

### The defect, precisely
- `:61` — a hardcoded placeholder `"rnr_3f9a…b2"` (with a literal ellipsis) is the null fallback.
- `:68-70` — **the failure path sets the same placeholder.**
- `:53-59` — the view is derived from whether a token exists, so setting the placeholder in the
  catch **flips the screen into the success state**. That is the mechanism: a failed generation
  renders as a completed one, with a copyable token that can never authenticate.
- `:64` — the project comes from the first membership, so a new workspace with no project posts an
  empty `project_id` and gets a 400.
- `:207-212` — the "Projects" multi-select is **fully uncontrolled**: no value, no handler, no
  state. Decorative. It also carries a second piece of mock data, a hardcoded option.

### The fix
Delete the placeholder entirely; the success view becomes reachable only by a successful request.
Surface the backend's real error. Guard the no-project case **before** posting, with a "create a
project first" prompt. **Make the select single and controlled**, defaulting to the current
project — the enrollment API binds one enrollment to one project, so a *multi*-select is a promise
the API cannot keep; multi-project enrollment belongs to the S.No 35 redesign. Remove the mock
option.

### Tests
A failed generation shows the error and **does not** show the success view — the test that would
have caught this. No project → the guard, and no request sent. The selected project is the one
posted.

---

## 7. Wave 3 — B8 · S.No 236 + 237: the Jira pointer lifecycle

### What is wrong
- **236:** reconciliation treats a stored Jira key as durable truth and **never checks it still
  resolves**. An issue deleted in Jira leaves a dead pointer with no detection and no repair path.
- **237:** candidates are selected on `state=proposed`, so an item that has moved into
  implementation can never be exported — 70 of 109 items in SpendLog were permanently ineligible.

### The fix
- **(a) Validate the pointer** before trusting it, through the vendor-free `get_issue` capability —
  not a Jira-specific call.

  > **The safety rule that makes this safe: only 404/410 may be read as "gone."** A 401, 403, 429 or
  > 5xx must leave the pointer untouched. Otherwise a token expiry or an outage would wipe every
  > pointer in the project in one pass. This is the most dangerous line in the wave.

- **(b) Select on "has no tracker id"**, not on state, so an item's lifecycle stage stops deciding
  whether it can be tracked.
- **(c) Preserve state — the team's explicit rule.** Reconciliation currently forces `accepted` on
  every success. With (b) in place that would flip completed work back and destroy the history —
  the exact trap that made the July recovery need a snapshot/rewind/restore script. **Only promote
  `proposed → accepted`; anything past `accepted` keeps its state.**

### Answers to the two questions the team asked
- **Does this re-export deleted issues?** Yes — it recreates them, as **new issues with new keys**.
  Jira never reuses a key, so external references to the old keys stay broken; the platform's own
  links repair themselves.
- **Will a second export duplicate them?** **No.** Two independent guards already exist: the
  pointer check, and *register-don't-recreate*, which searches the tracker by exact title and
  adopts an existing issue rather than creating a second. **Caveat:** that search is skipped
  entirely when the Jira project key is not configured, and then everything is created blind — so
  this wave adds a **pre-flight check that refuses to export** rather than exporting unsafely.

### Tests
**The pinned rule (team-requested):** a `done` item that is re-exported gets its pointer set and
**is still `done`** — written so that removing the guard fails loudly. Plus: a 404 clears the
pointer and recreates, **a 401/500 does not**; a second export creates nothing; an item past
`proposed` with no key is now a candidate.

---

## 8. Wave 4 — B2 · S.No 88: a PR merged on GitHub strands the platform

### What the bug actually is
See correction 1 in §2 — there is no merge loop. **Nobody ever approves, and nothing tells anybody
they should.** The workflow waits on a gate decision with no timeout, by design. The webhook sees a
pending merge gate and **deliberately declines** to move the work item — a correct guard that stops
a webhook jumping ahead of a human. Net: the run sits at `AWAITING_GATE` for ever, the work item
never reaches `done`, artifacts stay Draft, the preview environment is never torn down, and the
reviewer is asked to approve a merge that already happened with nothing on screen saying so.

### The fix — detect, annotate, let a human acknowledge
The team chose **human acknowledgement**, which makes this clean: **nothing in the platform ever
decides a gate.** Detection only annotates.

- **(a) Capture what is thrown away.** GitHub sends who merged and who sent the event; both are
  currently discarded. They are the compliance record.
- **(b) Annotate the pending gate** with a nullable field recording who merged, when, and how it
  was detected. **Nullable deliberately**, so a branch that does not know the field can still
  insert (ADR 0003). A migration is required.
- **(c) Log it** — `webhook.pr_merged_while_gated` on detection, `build.merged_externally` on
  acknowledgement, matching the existing event grammar.
- **(d) Reframe the gate in the UI.** When the annotation is present, the panel states plainly that
  the PR was merged outside the platform, by whom and when, and the button becomes
  **"Acknowledge external merge & complete"**. It calls the **same** decide endpoint, so the role
  check, the ledger event and the Temporal signal are unchanged. **No workflow change is needed**,
  because of the existing short-circuit.
- **(e) A sweep**, because webhooks are not guaranteed delivery. Registered in the existing
  reconciler extension point, it finds merge gates pending past a cutoff, probes whether the PR has
  merged, and **annotates only — never decides**. Bounded, age-gated, never raising, following the
  existing accessibility reconciler.

  > **This sweep is the only thing that will ever recover the run already stranded today** — no
  > webhook fires retroactively. It will annotate it; a human then acknowledges. **No Temporal
  > surgery.**

- **(f) Webhook delivery**, at cloud deployment: a reachable URL and the webhook secret.

### Two security facts that shaped this design
- **The webhook secret is a single global setting**, not per-tenant, and the tenant rides in the
  URL path. Anyone who can sign a payload can aim it at any tenant. Because our change only
  *annotates*, the worst a mis-addressed delivery can do is add a false note a human must still act
  on. **That containment is why the human-acknowledgement choice is the right one.**
- **The de-duplication row is written before the handler runs**, so a redelivery of a failed webhook
  is a silent no-op. The annotation must therefore be **best-effort** in the webhook, with the
  sweep as the real safety net.

### Tests
A merged PR with a pending gate annotates and logs, and **still does not transition the work item**
(the existing guard test must keep passing). The sweep annotates but never decides; a network
failure is swallowed; an acknowledgement drives the run to completion through the existing path.

---

## 9. Wave 5 — A4 · S.No 211: two projects can share a name

**The UI for this is already built and simply unreachable.** The create-project screen already
renders *"A project named 'X' already exists in this workspace."* It branches on **HTTP 409**, and
the backend never returns 409 — or anything else. `Project` has **no `class Meta` at all** and the
serializer has no name validation.

**The fix:** a tenant-scoped unique constraint (copying the shape used across the a11y and quality
models), plus a view-level check returning **409**, matching the repository-duplicate precedent —
so the existing frontend branch lights up with **no frontend change**. Also reject a
whitespace-only name, currently accepted.

**Migration `projects/0013`. It will fail if duplicates already exist**, so a read-only pre-check
runs first and the team is told what needs renaming.

**Judgement call made, flag if you disagree:** an archived project's name **stays reserved**.
Un-archiving a project whose name had been reused would be the worse surprise.

---

## 10. Wave 6 — A5 · S.No 219: actions that fail with no message

| Site | What happens |
|---|---|
| Invite **resend** / **revoke** | Fire-and-forget. The screen has an error surface for the *read* and reads the write error **nowhere** |
| Repository create | Only 409 is inspected; a **403** is caught and discarded |
| Repository delete | No error read at all |
| Test-script generate | Reads "pending", never "error"; the button just flips back |
| Signup blank name / short password | Branches only on 409; the 400 is swallowed |
| Accept-invite short password | Branches only on 409/410 |
| Reset short password | Branches only on 410 |

**Root cause, in one line: there is no mutation error handler anywhere in the codebase and no
shared write-error surface** — so four screens invented four different ad-hoc spellings of the
same idea.

**The fix:** a `WriteError` primitive beside the existing read-side `ErrorState`, taking an API
error directly, with **no retry affordance** (retrying a write is a re-submit, not a refetch);
replace the four ad-hoc spellings with it, which is what stops a fifth screen inventing a fifth.
Field-level errors on the auth forms using the two-tier pattern the Login screen already
demonstrates. And **every default branch must show something** — these screens each catch one
status and drop the rest.

**One extra defect found during recon, included here:** the reset-password screen captures a
*confirm* field and **never compares it to the password**. A mistyped confirmation is silently
accepted. Same file, same session; noted on the row rather than opened as a new one.

---

## 11. Wave 7 — A6 · S.No 221: greenfield projects are offered a brownfield wizard

The Onboarding nav item is rendered with no gate, and the hub screen does not *check* the track —
it **asserts** it, with copy saying "Brownfield project" and a Brownfield badge over whatever
project you have.

**The blocker:** `track` is not available where the decision must be made. The selected project in
the frontend carries only id, name and role. **Add `track` alongside them** — one field, and it
then rides everywhere, exactly as `role` does.

**The fix:** generalize the sidebar's single hardcoded `adminOnly` predicate into a real one, then
hide Onboarding for greenfield. Generalizing is the point — a second one-off boolean is how the
first one became a problem. Make the hub read the track rather than assert it. Add a backend track
check for defence in depth.

**Judgement call made, flag if you disagree:** `/onboarding/documents` is hidden with the rest.
Uploading a specification is not *meaningless* on a greenfield project, so this one is arguable —
but it is reached from the hub anyway, and "greenfield document upload" is a product question of
its own.

---

## 12. Wave 8 — B1 · S.No 87: the build agent can move the main work item

**Already half-fixed** — commit `83a2036` blocks agents from setting `done` at the single agent
entry point, and the orchestrator's own path is unaffected. What remains: the agent can still move
the **main** work item into other states, and the tool is still granted without scope.

**This wave does the cheap, unbreakable half only** — extend the forbidden set to the other states
the control plane owns. **Ownership scoping** ("the agent may transition only the child items it
created") is the precise-but-fragile half and is **deliberately deferred** until the extended block
has been in use; it may prove unnecessary.

---

## 13. Wave 9 — B3 · S.No 140: no human way to close a task that cannot be built

The largest wave, and the one that most repays a careful read.

### 13a · One definition of "terminal", used everywhere
Add `cancelled` to the work-item states **and a `TERMINAL_STATES` set on the model**, then replace
every `== done` / `!= done` / `exclude(state=done)` with it. That single helper turns the rest of
this wave from a hunt into a sweep.

**Migration `workitems/0007` — choices only.** No table, no column, no backfill, and **the SQL it
runs is empty**, because Django holds choices in application code and Postgres has no constraint to
alter. The field is already long enough. ADR 0003 does not apply.

### 13b · The seven sites that would silently un-cancel an item
Each forces a state without asking what the item's current state is:

| Where | Forces | Why it bites |
|---|---|---|
| The merged-PR webhook | `done` | A cancelled item whose PR later merges flips to done |
| Gate rejection | `in_progress` | Rejecting a gate resurrects a cancelled item |
| Build failure compensation | `in_progress` | Same |
| Build start (two entry points) | `in_progress` | Same |
| Remediation refresh | `in_progress` | Un-cancels a cancelled child |
| Defect close/reopen matrices (quality) | both | Tests `== done` only |
| Defect close/reopen (accessibility) | both | Same shape |

**Rule: a terminal state is left only by an explicit human action.** No automated path may move an
item out of `cancelled`.

### 13c · Where the team's gate decision lands
Three gate queries compute open blocking defects as "everything that is not done". Switching them
to the terminal set is what implements *"cancelling releases the gate"*.

**And then the gate must say so.** A **reviewer-attested** condition — the same kind as the existing
WCAG checklist — lists each cancelled defect with its reason and who cancelled it, and the approver
must tick *"I have reviewed the cancelled defects"* before approving.

> **This is the half that makes the decision safe.** Releasing the gate silently would let a
> "won't fix" quietly become a pass. The release and the disclosure ship together, never
> separately.

### 13d · The endpoint
A new `transition` action on the work-item viewset, copying the existing `trigger` action exactly:
**tech lead or admin** per the team's decision; an **allowlist** of permitted human transitions —
not the any-to-any of the internal tool; **a reason is required** for `cancelled`; and an audit
event recording who, from what, to what, and why.

**Two traps, both recorded because they have bitten this codebase before:**
- **Do not widen the patch serializer** — its own docstring states that state changes go through
  their own actions.
- **Add the new action to the viewset's permission set.** Miss it and the endpoint runs under the
  project-wide "allow anyone" default — which is precisely S.No 214, the P1 defect just fixed.

### 13e · Block agents from the new state
Add `cancelled` to the agent-forbidden transitions **in the same commit that adds the state**.
The underlying tool validates only that a value is a member of the enum, so a build agent could
cancel its own work item the moment the value exists.

### 13f · Frontend
- **Narrow the state type into a union.** It is currently a bare string, so nothing breaks at
  compile time — which is exactly the risk. **This is the highest-value change in the wave:** it
  turns every site below from a silent wrong answer into a compile error.
- **The board badge is the worst offender** — it falls through to **"Draft"**, so a cancelled item
  is labelled as new work. (The same fallthrough already mislabels `blocked`, `in_review` and
  `accepted`, and one of its branches is dead code for a state that has never existed.)
- **The defect screen** renders a cancelled defect as a red **"Open"** badge; **the task screen**
  still offers trigger buttons on cancelled work.
- **Hide cancelled by default**, with a filter to show them — the filter and its options are
  derived from live data and pick the value up for free.
- **The dashboard count must agree.** It counts work items with no state filter, and its own
  comment demands the number match the board — hiding on the board without excluding here
  re-introduces exactly the bug that comment guards against.

### 13g · The buttons
**Task page** (beside Retry, the moment Retry stops being useful) · **Work Items board** (row-level,
for cleanup) · **Run console** (where the build just failed and the person is looking).

Labels: **Mark as done · Close as redundant · Skip.** The **reason** is what differs, and it is what
makes delivery reporting honest later.

---

## 14. Wave 10 — S.No 35: documentation only

[CONNECT_MACHINE_REDESIGN_SPEC.md](CONNECT_MACHINE_REDESIGN_SPEC.md) — **written and complete.**
No code in this batch. It covers the nine measured onboarding steps, the three structural findings,
all five layers with contracts, the security model, corrected costing (~2.5–3 weeks for layers 1–3,
~6–8 weeks for all five), the procurement item to start early, and four open questions for the
team.

---

## 15. Records updated in the final commit

- **`Bugs.xlsx`** — close rows for Waves 0–9; **S.No 35 stays Open** with a pointer to the spec;
  **S.No 178** gets a note that option 3 is approved and sequenced after one live scan; the three
  corrections from §2 are written into their rows.
- **`SDLC_BUG_FIX_ENHANCEMENTS.md`** — a P2 batch section recording the S.No 213 drop and the
  Group C park, so the scope decision is not re-litigated later.
- **A new ADR** for the external-merge model: the platform observes the code host, never polices
  it; detection annotates and only a human decides; and why that containment matters given a
  globally-shared webhook secret.

---

## 16. Sequencing — seven commits

1. **Wave 0** — close three already-fixed rows *(no code)*
2. **Wave 1** — A1 preview rendering *(backend + agent 04)*
3. **Waves 2, 5, 6, 7** — the UI-honesty group: A3, A4, A5, A6
4. **Wave 3** — B8 Jira pointer lifecycle *(backend)*
5. **Wave 4** — B2 external merge *(backend + frontend + migration)*
6. **Waves 8 + 9** — B1 + B3 terminal state *(the deepest; migration)*
7. **Records** — Bugs.xlsx, the ADR, the batch doc

Waves 1–8 are independent. **Wave 9 comes last** — it touches gates, webhooks, build activities and
the board, and doing it earlier would make every later diff harder to read.

---

## 17. Verification

- Per wave, **only the named test files** — never the full backend suite.
- **Baseline first**, so nothing pre-existing is misattributed.
- Frontend: `npm test` (currently 449 passing) and `npx tsc --noEmit -p tsconfig.app.json` —
  **not** the root config, which has `"files": []` and checks nothing.
- **Lint must return to its exact 71-ruff / 147-mypy baseline.** Any new error is ours.
- **Live check** on the Docker stack for the UI waves and the A1 preview — browser-verified against
  a real SBOM artifact, not only asserted in a test.
- **Two migrations written, not run** (`projects/0013`, `workitems/0007`). `projects/0013` will
  fail if duplicate project names already exist, so a read-only pre-check and a rename report are
  handed over with it.

---

## 18. Risks and how each is contained

| Risk | Containment |
|---|---|
| Wave 9's sweep misses a site and an item is silently un-cancelled | The terminal-state helper plus the narrowed type turn most misses into compile errors; one test per resurrection site for the rest |
| A cancelled defect silently unblocks a gate | The reviewer-attested condition — release and disclosure ship together, never separately |
| The A1 renderer leaks into what agents and publish read | It attaches to the preview reader only; a test asserts the other two still return byte-identical raw JSON |
| B8's pointer check wipes pointers during an auth outage | Only 404/410 count as "gone"; everything else leaves the pointer untouched — with a test |
| `projects/0013` fails on existing duplicates | Read-only pre-check before handover |
| Scope creep into S.No 213 or Group C | Explicitly out of scope, recorded here and in the batch doc |

---

## 19. What we need from the team

**Nothing is blocking** — the plan can be executed as written. These are judgement calls already
made; flag any you disagree with.

1. **§9** — an archived project's name stays reserved. Agree?
2. **§11** — `/onboarding/documents` is hidden for greenfield along with the rest of onboarding.
   Agree, or should greenfield document upload stay reachable?
3. **§5** — publish continues to push the **raw** SBOM, not the rendered table. Confirm that is
   what you want when an SBOM is exported to a system of record.
4. **§14** — the four open questions in the Connect Machine spec (OS scope; whether the assistant
   may auto-install Claude Code; whether a VS Code extension is worth costing; whether target
   developers are already set up). Not needed for this batch — needed before that work starts.
