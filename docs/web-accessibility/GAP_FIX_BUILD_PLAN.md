# Web Accessibility — Gap Fix Build Plan (POC + Phase 2)

**Branch:** `web-accessibility-build` · **Written:** 2026-08-19

---

## 0. What this document is

The 24 QA tasks are built. This plan covers the **eleven gaps found afterwards**, when the team
asked how a real user reaches the accessibility work in the greenfield and brownfield journeys.

Every gap here was found by reading the code, not the docs. Each one below says what is wrong in
plain words, why it happens underneath, exactly what will change, and how we prove it worked.

**Nothing in here is built yet.** We take one task at a time: I surface it in full, the team says
go, I build it, we test it, and only then do we move on.

### How to read a task

Each task has the same six parts:

| Part | What it tells you |
|---|---|
| **In plain words** | What a person notices, with no code in it |
| **Why it happens** | The actual cause, with file and line |
| **What we change** | The files, and what goes in them |
| **What you see afterwards** | How you can tell it worked, without reading code |
| **How we prove it** | The tests, named |
| **Size · Risk · Needs first** | Honest sizing so the team can schedule |

**Size** is `S` (an hour or two), `M` (half a day), `L` (a day or more).

---

## 1. Rules that do not change while we do this

These are not negotiable and every task below respects them.

1. **The platform never reaches your application.** Every request to the app under test comes from
   the companion on a developer's own machine. The platform stores the address and nothing else.
2. **Silence is reported, never guessed.** A page that would not open, a criterion nobody checked,
   a step never reached — all of them are recorded as themselves. None of them is ever allowed to
   read as a pass.
3. **One standard, one meaning.** Greenfield and brownfield share the capture format, the selection
   rules, the judge, the triage, the ledger and the report. Two ways of deciding what "a failure"
   means would be two standards.
4. **Nothing reaches a system of record without an approved gate.**
5. **We never run the full backend test suite** — only the files a change touches.
6. **We never apply migrations to the shared server.** That is the team's call, always.

---

## 2. The build order

Small and safe first, so the team gets working ground under them before the big pieces.

| # | Task | What it unblocks | Size |
|---|---|---|---|
| 1 | **G1** — greenfield records what passed, not only what failed | A truthful conformance report on greenfield | S |
| 2 | **G4** — hide the "Accessibility judging" plumbing task | A clean work-items board | S |
| 3 | **G5** — make sure the Testing agent sees the screen list | Accessibility test cases actually get written | S |
| 4 | **B3** — take the address from the repository | One less thing typed by hand | S |
| 5 | **B5** — audit any number of pages, in passes | Meridian's 68 pages, and anything bigger | M |
| 6 | **G2 + G2b** — the platform learns which test cases are WCAG | You can see and filter them | M |
| 7 | **G3** — a finding says which test case found it | The review console makes sense on greenfield | M |
| 8a | **B1 + B4 + B2** — the audit screen, and the way in | Brownfield audit with no terminal at all | L |
| 8b | **The page editor** — edit one page, not the whole list | A path can be corrected without creating a second page | M |
| 9 | **G3b** — the review list stops fetching evidence nobody reads ✅ | A queue that does the work it is read for | S |
| 10 | **G6** — the keyboard journey, working on both journeys ✅ | Eight criteria nothing else can reach | M |

Tasks 1–4 are independent of each other. 6 should land before 7. 8 has the wireframe already
approved (`docs/design/screens/S-38-a11y-audit.html`) and was **split by team decision on
2026-08-19**: 8a delivers the promise end to end (register pages, run an audit, no terminal), 8b
makes the page list editable a row at a time. 10 is broken into three slices of its own and shares
the 8a screen, so it is cheaper to build after it than before.

---

## 3. The tasks

### G1 · Greenfield records only what failed

🟢 **Built 2026-08-19.** The agent body now carries all four scanner channels, `scanner_version`,
and the WCAG tag filter on the capture's own scan. Seven tests added — the load-bearing one runs
the agent's example document through the platform's real parser, so the instruction cannot drift
from the format the platform accepts without a test going red. Still unproven by a live run.

**In plain words.** On a greenfield project the conformance statement will say *"not evaluated"*
against almost every WCAG criterion — even the ones the scanner checked and found nothing wrong
with. The report is not lying, but it is useless: it looks like nobody checked anything.

**Why it happens.** The industry scanner gives four answers about every rule it runs: *violations*,
*passes*, *inapplicable* and *incomplete*. QA-24 taught the platform to keep all four, and updated
the **brownfield** scanner (`runner/companion/assets/a11y_audit.mjs`) and the platform's parser
(`backend/apps/a11y/capture.py`). It did not update the **greenfield** producer.

Greenfield captures are written by the test suite that the Test Automation agent generates, and
that agent's instructions still describe a file carrying violations only —
`agents/09b_test_automation/agent.md:459-505`, and its finish checklist at `:620`.

When the three positive arrays are absent, `capture._rule_list` reads that as `[]`, which means
*"no positive evidence"*. The coverage map then records failures and nothing else, and the
conformance table has nothing to say.

**What we change.** One file: `agents/09b_test_automation/agent.md`.

- The example capture at `:459` gains `axe_passes`, `axe_inapplicable`, `axe_incomplete` and
  `scanner_version`, in the same shape `a11y_audit.mjs` already writes.
- The field explanations after it explain each one — in particular that *inapplicable* means "the
  rule ran and there was nothing on this page for it to apply to", which is a different fact from
  "it passed", and that an **absent** array means no positive evidence rather than "nothing passed".
- The `axe_error` paragraph at `:501` says all four are omitted when no scan ran, not just two.
- The finish checklist at `:620` checks for all four.
- **Added while building, agreed 2026-08-19:** Step 5b told the script to run axe and never said
  to scope it — the tag filter was written only into Step 5a, which covers dedicated accessibility
  cases. An unscoped scan fills the three new channels with axe's best-practice rules, which map
  to no WCAG criterion and so become neither a finding nor coverage. `_rule_list`'s own refusal
  message already tells the author to use the tag filter; now the instruction does too.

No platform code moves. The ingest path (`backend/apps/a11y/ingest.py:228-231`) already reads all
four and already writes the coverage rows.

**What you see afterwards.** Run test automation on a greenfield project, then open
**Accessibility → Conformance statement**. Criteria the scanner confirmed read *"Checked on N
pages with nothing wrong"* instead of *"Nothing checked this."*

**How we prove it.** `backend/tests/test_a11y_capture.py` and `test_a11y_scan_coverage.py` already
assert the platform half; they stay green. The agent-body half is proven by reading it against the
scanner file, and truly proven only by a real greenfield run.

*As built:* seven tests in `test_a11y_scan_coverage.py`. The first two lift the agent's example
document out of the body and run it through `parse_capture` and `coverage.from_scan` — proving the
shape the agent is shown is a document the platform accepts, and that it yields all four outcomes
(`failed`, `passed`, `not_applicable`, `needs_human`) rather than failures alone. The other five
hold the prose that stops the two known mistakes: folding *inapplicable* into a pass, and reading
an absent channel as "nothing passed". `test_a11y_scan_coverage.py`, `test_a11y_capture.py` and
`test_a11y_conformance.py` — 171 passed. **What this does not prove:** that a generated suite
actually writes the four channels. This is an instruction to a model; the tests prove the
instruction is right and present, never that it was followed. Only a live greenfield run does that.

**Size S · Risk low · Needs first: nothing.**

---

### G4 · Every test run leaves a plumbing task on the board

🟢 **Built 2026-08-19.** The judging work item is marked a carrier and disappears from the board,
from Phases & Runs, and from what an agent is shown as the project's backlog. A migration marks
the ones already on a board. The dashboard's **Work items** and **Phases in progress** counts now
exclude carriers too, which also fixes the onboarding and vision carriers that were inflating
them. Nine tests, all at REST level. Proven end to end by test — no live run needed.

**In plain words.** Automate 30 test cases and you get 30 extra tasks on the work-items board
called *"Accessibility judging — …"*, plus 30 extra runs in Phases & Runs. Nothing is broken, but
it looks like the platform is generating junk work, and on a real project it buries the backlog.

**Why it happens.** The accessibility judge is an agent, and every agent run in this platform must
hang off a WorkItem. Judging a captured page is not work on a story, so the platform creates a
throwaway WorkItem to host the run (`backend/apps/a11y/aipass.py:46`), one per test run.

The platform already knows this kind of object should be hidden. `carrier_q()` in
`backend/integrations/onboarding.py:1093` is the filter, and the work-item list
(`backend/api/views.py:1360`), the runs list (`:1697`) and the dashboard's *my runs* panel
(`:942`) all use it. It matches on `external_ref.source` against `CARRIER_SOURCES`. The judging
item writes `external_ref.kind` instead, so the filter never fires.

*(Corrected while building: this document originally called `views.py:942` "the gates list". It
is not — it is the dashboard's **my runs** panel. Gates are carrier-filtered **nowhere**, and
that turns out not to matter: the judge is dispatched with `auto_approve=True`
(`backend/apps/a11y/dispatch.py:366`), so it never creates a gate anyone must act on.)*

**What we change.**

- `backend/apps/a11y/aipass.py:64` — add `"source": "a11y_judging_carrier"` alongside the existing
  `kind` (keep `kind`; something may read it).
- `backend/integrations/onboarding.py:1091` — add that marker to `CARRIER_SOURCES`.
- `backend/apps/workitems/migrations/0006_a11y_judging_carrier_marker.py` — a data migration that
  marks the judging items already sitting on people's boards. `get_or_create` writes the marker on
  new items only, so without this the fix is invisible on exactly the projects that have the
  problem. Follows `a11y/0005_load_wcag_for_existing_tenants`: the tables are FORCE ROW LEVEL
  SECURITY, so it sets `app.tenant_id` per tenant and resets it afterwards. Adds one key and
  preserves the rest of the `external_ref`; the reverse takes only that key back off.
- `backend/api/views.py:984` — the dashboard's **Work items** and **Phases in progress** counts
  exclude carriers, which they never did. Already wrong before this task for the onboarding and
  vision carriers: the board showed 30 items while the health panel said 62. **`awaiting_gate`
  deliberately does not exclude them** — gates are not carrier-filtered anywhere, and the gap
  report has been gated since 2026-08-03, so its approval sits on a carrier and is real work a
  person must do. Excluding it there would hide a pending gate the Gates screen still lists.

**Four consumers of this filter the first draft of this plan did not name, all checked:** the MCP
`list_work_items` (agents stop counting platform scaffolding as the project's backlog — right, and
the same reason it already excludes onboarding carriers); the gap-report evidence builder
(`onboarding.py:1400`, same); `_phase_artifact_title` (`orchestration/activities.py:845` — the
judge's artifact loses its phase prefix, becoming *"Accessibility judging — Add login"*, which is
what that function says carriers should read like); and the dashboard counts above.

**Load-bearing detail:** read `carrier_q`'s docstring before touching it. The `has_key` half of
that query is what stops Postgres dropping every work item whose `external_ref` has no `source`
key at all — every Jira-imported story. Removing it once emptied the backlog on every project in
the product. We are adding a marker, not touching the query.

**Not touched:** the **"Accessibility backlog"** epic that a brownfield audit's defects hang off
stays visible. That is deliberate and documented at `backend/apps/a11y/backlog.py:170` — a client
is meant to see it, work through it and watch it shrink.

**What you see afterwards.** The work-items board shows your stories, test cases and defects, and
no "Accessibility judging" tasks. The Accessibility backlog epic is still there.

**How we prove it.** One test: after an AI pass, the judging work item is absent from the work-item
list and the runs list, and the backlog epic is still present in both.

*As built:* nine tests in `backend/tests/test_a11y_judging_carrier.py`, all **over HTTP** — "hidden
from a queryset" is not the claim this task makes; "a person does not see it on the board" is. They
cover: the task is off the board and its run out of Phases & Runs; the story, a Jira-imported item
with no `source` key (the S3-13 guard, re-proven because this change edits the tuple that query
reads) and the Accessibility backlog epic all stay; the item still resolves by direct id so a link
from a run detail opens; `kind` survives beside the new `source`; the migration marks a
legacy-shaped row and its reverse puts it back; and the dashboard counts equal the lists beside
them. One more asserts the mechanism itself — put `CARRIER_SOURCES` back the way it was and the
task returns to the board, so the file is testing the fix rather than something already true.
Regression: `test_a11y_report.py`, `test_onboarding.py`, `test_a11y_baseline_report.py`,
`test_a11y_baseline_enforcement.py`, `test_api.py`, `test_frontend_integration.py` — all green.
`test_document_vision.py` has two failures that predate this work (`triggered_by="user-1"` is not
a valid UUID); they fail identically on the commit before it and are not part of this change.

**Size S · Risk low, with one sharp edge named above · Needs first: nothing.**

---

### G5 · The Testing agent may never see the screen list

🟢 **Built 2026-08-19.** `09_testing` now declares every artifact type its body reads — ten,
not four — so the screen inventory is guaranteed to reach it. Step 9 was also pointed at the
document the inventory actually lives in. Four tests; no migration, no reseed.

**In plain words.** The Testing agent is told to write one accessibility test case per screen. It
gets the list of screens from the UX Design phase's wireframe document. On a project with a lot of
documents that wireframe can drop out of what the agent is given — and then it writes no
accessibility test cases at all, and nothing says why.

**Why it happens.** Each agent declares the artifact types it needs, and the manifest guarantees
those reach it. `09_testing` declares `("prd", "requirements", "architecture", "api_spec")` —
`backend/apps/registry/catalog.py:99`. `wireframe` is not in that list. Its Step 9 instruction
depends on an input it never asked for. It can still pull the wireframe on demand, but nothing
guarantees it.

**What we change.** Add `"wireframe"` and `"ux_design"` to `09_testing`'s `needs_artifacts` in
`backend/apps/registry/catalog.py:99`.

**Corrected while building — the plan's fix was half right.** The required tier pins **the latest
artifact of each declared type**, and `05_ux_design` registers `wireframe` **one per screen**. So
declaring `wireframe` guarantees the agent one wireframe, not the list. What carries the screen
list is the **`ux_design`** artifact, where 05 registers the Screen Inventory; `wireframe` is still
worth declaring, as a concrete pointer proving the type exists on this project. Two changes follow
from that:

- **Step 9 of `agents/09_testing/agent.md` said the inventory lives in "the `wireframe` artifacts'
  screen inventory".** Two agent bodies disagreeing, and it is the disagreement that produces the
  gap: an agent handed a single wireframe pointer could reasonably write one case and stop. Step 9
  now names the `ux_design` Screen Inventory, says to enumerate the screens with
  `list_artifacts(type="wireframe")`, and says to report any screen it could not reach rather than
  quietly writing fewer cases.
- **Four more declared inputs, folded in by team decision (2026-08-19).** The same body names
  `user_stories`, `backlog`, `definition_of_done` and `security_architecture` as things it reads,
  and each was subject to the identical eviction. Every one has a producing agent (02, 06, 06, 04),
  checked before declaring it — a declared type nothing produces would render a permanent gap. The
  declared list is now the ten types the body actually reads. The required tier carries **pointers,
  not bodies**, so ten costs ten lines of manifest.

No migration and no reseed: `needs_artifacts` lives in the catalog and is read at call time —
`AgentSpec` has no such column.

**What you see afterwards.** Run the Testing phase on a project that has a wireframe, and the
screen inventory is in the agent's context every time, not sometimes. Accessibility cases get
written for every screen.

**How we prove it.** The manifest composer's required-tier test — a wireframe registered long ago,
with a dozen newer artifacts on top, still reaches the Testing agent's context.

*As built:* four tests in `backend/tests/test_mcp_platform_state.py`, mirroring the existing
`test_get_context_pins_required_input_past_the_recency_tail`. A `ux_design` and a `wireframe`
buried under 20 newer artifacts both come back flagged `required` while the tail stays capped at
12; the declared list is asserted whole; a project with no UX phase reports both as a **named gap**
and raises nothing (`composer.py:336` — a missing declared input is reported, never fatal); and
Step 9 is asserted to name the right document. Regression: `test_manifest_composer.py`,
`test_a11y_axe_execution.py`, `test_a11y_policy.py`, `test_agents_migration.py`,
`test_design_test_agents_migration.py` — 186 passed. Five failures across those files and
`test_mcp_platform_state.py` predate this work and fail identically on the commit before it.

**What this proves, and what it does not.** It proves the platform *guarantees* the screen list
reaches the agent — at the exact boundary that was dropping it. It does not prove the agent then
writes one case per screen: that is a model following an instruction, and only a real Testing run
on a project with wireframes shows it. The instruction now at least points at the right document.

**Size S · Risk low · Needs first: nothing.**

---

### B3 · The application address has to be typed again

🟢 **Built 2026-08-19.** The platform now resolves the application's address from what it
already holds, in four steps, and refuses the audit with a readable reason when it holds none.
`--base-url` on the companion is optional as a result, so this is visible from the terminal today
rather than only once B1's screen exists. Twelve tests.

**In plain words.** You add a Preview URL to your repository. Then, to audit the application, you
type the same address again on a command line. The platform already knew it.

**Why it happens.** The greenfield build path reads `Repository.preview_url` through
`resolve_preview_url` (`backend/apps/projects/preview_config.py:43`). The audit path does not —
`start_baseline_audit` (`backend/apps/a11y/baseline.py:72`) takes `base_url` as a parameter and
stores whatever it was given. Nothing in `backend/apps/a11y/` reads `preview_url` at all.

**What we change.** An explicit address still wins, always: a person deliberately auditing a
staging site must not be overridden by a stored dev URL. When nothing can be resolved, the audit is
refused with a sentence saying so, rather than opened with an empty address that fails later on the
companion.

**What `preview_url` is, since the team asked (2026-08-19).** It is an **application address** —
where the running app answers, e.g. `http://127.0.0.1:5173` — and never a repository URL; a repo's
git identity is its `name` / `code_host_ref`. It lives on the repository row because the served
thing *is* a repo: the frontend repo runs the UI and a backend-only repo has no UI to preview. It
is optional (`blank=True`). The platform holds the same fact a second way: `preview_start` carries
a **command and a port**, and when a build brings the app up the companion reaches it at
`http://127.0.0.1:{port}` (`runner/companion/runner.py:371`).

**The resolution, as built** — `resolve_app_base_url` in `backend/apps/projects/preview_config.py`,
placed there because that module is already the platform's single answer to *"how do we reach this
app?"*, and a second answer inside `apps/a11y` would be a second answer:

1. an address given for this pass;
2. the **default** repository's `preview_url` — the project's own record of which repo serves the app;
3. else the `preview_url` of the **only** repo that has one. A `preview_url` is a claim that this
   repo serves the application, and normally exactly one repo makes it. Two or more with no default
   is a project with two applications, and that is refused **naming them** rather than resolved by
   picking the first — the same rule `orchestration/trigger.py:154` applies to an unpinned work item;
4. else `http://127.0.0.1:{port}` from `preview_start` (team decision 2026-08-19). That is the
   address the companion itself uses during a build, so it is derived from the platform's own
   behaviour rather than invented. Nothing is started: if the app is not up, the audit reports pages
   nothing answered on, which is honest and never a pass.

It returns **where the address came from** as well as the address, so B1's field can say *"from the
default repository acme/web"* instead of pre-filling out of nowhere, and returns a **reason** naming
what to set when there is nothing.

**Two more edits than the plan named:**

- `runner/companion/__main__.py:216` — **`--base-url` is no longer required.** Without this the
  fix changes nothing anybody can see: the CLI is the only way to start an audit until B1 exists,
  so the platform would resolve an address the user was still forced to type. The resolved address
  comes back on the manifest, which is what the script visits.
- `backend/tests/test_a11y_baseline.py` — `test_an_audit_can_be_given_routes_directly` started an
  audit with no address at all and expected success. The manifest it produced carried
  `base_url: ""`, which the audit script cannot visit; it now passes an address. What it tests —
  dedupe and order — is unchanged. The new refusal sits **after** the route checks, so every other
  existing refusal keeps its wording and its order.

**What you see afterwards.** On the audit screen (B1), the address field is pre-filled from your
repository, with a note saying where it came from. You can change it, and changing it does not
write back to the repository.

**How we prove it.** Three tests in `backend/tests/test_a11y_baseline.py`: the fallback fires, an
explicit address wins over the stored one, and an audit with neither is refused with a readable
reason.

*As built:* twelve tests in that file. Each step of the resolution, in isolation: the default repo's
URL; an explicit address beating it; the one repo that serves an app when the default does not; the
default winning over a second repo that also serves one; two applications and no default refused by
name; the `preview_start` port; and nothing anywhere refused with `Preview URL` named in the
sentence and **no audit row written**. Plus: a project with no routes is still told about the routes
first, the resolver reports its own provenance for B1 to display, and the companion path leaves the
address empty and visits the one the platform resolved. `test_a11y_baseline.py` (83),
`test_a11y_baseline_report.py`, `test_a11y_baseline_enforcement.py`, `test_preview_config.py` (88),
`test_build_preview.py`, `test_a11y_capture.py` (107) — all green.

**Fully provable by test** — platform code and a CLI argument, not an instruction to a model. What
no test can prove is that the stored address is *correct*: a dead URL in a repository produces an
audit that honestly finds nothing there and says so.

**Size S · Risk low · Needs first: nothing (but it is only visible once B1 lands).**

---

### B5 · An audit stops at 60 pages

🟢 **Built 2026-08-19.** An audit now runs in as many passes as it needs, all posting to the
same audit. `MAX_SCREENS` stays at 60 as a bound on one capture document. Six tests, including the
one that matters most: a pass that dies never re-posts the previous pass's pages.

**In plain words.** The platform visits at most 60 pages in one go. Meridian has 68 in scope, so
eight are left out with only a line on a console that nobody is watching. The next application
might have 400.

**Why it happens.** `MAX_SCREENS = 60` in two places — `runner/companion/assets/a11y_audit.mjs:31`
and `backend/apps/a11y/capture.py:38`. The number was chosen when the working assumption was "about
ten pages per run, maybe fifty per application".

**The important thing about that number:** it bounds **one capture file**, not an audit. Screens
are posted to the platform **one per HTTP call** (`runner/companion/a11yaudit.py:88`), because one
page carries a full-page screenshot and ten of those in one request is several megabytes. So
nothing downstream cares how many files there were.

**What we change.** `runner/companion/a11yaudit.py` — `run_baseline_audit` splits the manifest into
passes of 60 routes, runs the audit script once per pass, and posts every screen to the **same
audit**. The route reconciliation at the end already accounts for every route the audit was asked
for, so nothing about honesty changes.

`MAX_SCREENS` stays exactly where it is, as what it always should have been: a safety bound on how
big one file may be, not a limit on how big an application may be. It is now **imported** from
`apps.a11y.capture` rather than retyped, so the companion cannot drift from the number the platform
refuses a document for. The script's own truncation warning stays as a backstop: someone running it
by hand with a hand-written manifest still deserves the honest message.

**The sharp edge, designed out rather than guarded against.** `run_audit_script` reads the file the
script was told to write. If every pass wrote to the same filename, a pass that died before writing
would leave the previous pass's file in place — which would be read again and posted a second time,
reporting pages as seen in a pass that never visited them. That is the exact failure this feature
exists to prevent, reintroduced by its own fix. So **each pass writes its own file**
(`a11y-candidates-pass-2.json`, via `pass_output`), a single-pass audit keeps the plain name, and a
pass that dies produces nothing. Asserted directly by `test_a_pass_that_dies_never_reposts...`.

**Two ceilings this does NOT remove, named so nobody meets them by surprise:**

- **`MAX_ROUTES = 200` per project** (`routes.py`). A 400-page application cannot *register* 400
  pages, so "any number of pages" honestly means "any number up to the 200 a project may register".
  **Team decision 2026-08-19: left at 200** — it is a scope judgement, not a technical bound, and
  raising it is its own decision. Its comment used to derive the number from `MAX_SCREENS`; that
  relationship is exactly what this task severs, so the comment now says what it really is.
- **The AI judging cap — 200 items per run** (`dispatch.DEFAULT_MAX_JUDGMENTS_PER_RUN`). Everything
  over it is **deferred and reported** — *"Stopped at this run's limit of 200 — N item(s) still need
  judging. Run the check again to continue from here; nothing was skipped."* Unchanged, and already
  honest. A 68-page audit captures all 68; whether all 68 are *judged* in one go depends on how many
  elements they carry.

`capture.MAX_SCREENS`'s own comment said *"a run that captures 60 screens has gone wrong in a way
that should be said out loud"*. After this, 60 screens is a full first pass of a large audit, so the
comment now says it bounds one document and points at the pass loop.

**What you see afterwards.** Before you start: *"68 pages · 2 passes"*. While it runs: a pass
counter. Afterwards: 68 pages reported, or an honest account of the ones that would not open.

**How we prove it.** A test that a 130-route manifest produces three passes and one audit
accounting for all 130; and that a single route that would not open is still reported as never
seen, in whichever pass it fell in.

*As built:* six tests in `backend/tests/test_a11y_baseline.py`. 130 routes → passes of 60/60/10,
one `start`, one `finish`, and every page posted once and in order to the same audit; each pass
writes its own file; **a pass that dies posts nothing and duplicates nothing** (the sharp edge); a
failed pass does not abandon the audit — the later passes still run, it is still closed, and the one
returncode reported is not just the last pass's; an audit that fits in one pass is byte-for-byte
unchanged, plain filename included; and, on the platform side, 70 routes across two capture
documents reconcile to 70 asked with the unopenable page in the second pass reported as itself.
`test_a11y_baseline.py` (89), `test_a11y_baseline_report.py`, `test_a11y_baseline_enforcement.py`,
`test_a11y_capture.py` — 272 passed.

**What the tests do not prove.** They drive a stubbed script. That a **real** browser survives 60
routes twice over on a real application is not something a test here can establish — that is the
live run still ahead of us, and the first audit of a 68-page application is the first time we
learn it.

**Size M · Risk low-medium (the loop must not lose a pass's screens if one pass fails — a failed
pass reports its routes as unreported, it does not abandon the audit) · Needs first: nothing.**

---

### G2 + G2b · The platform cannot tell a WCAG test case from any other

🟢 **Built 2026-08-19.** The platform reads what a case says about itself, carries it onto the
work item, and the Test cases screen shows a Type column with a filter. One parser for that line,
not two. The approved screen was updated in the same change. Fourteen tests.

**In plain words.** The Testing agent writes accessibility test cases marked `Type: Accessibility`.
The platform never reads that. On the Test cases screen you cannot tell which of your forty cases
are the WCAG ones, and the Priority column is blank for all of them.

**Why it happens.** Two halves of one root cause.

The type is written as prose in the test case document. Nothing in the platform stored it. The
Test Automation agent behaves correctly because *it* reads the document; the platform never
learned anything.

*Corrected while building:* there **was** already a general reader — `declared_type` in
`backend/apps/a11y/journeys.py`, which returns the value and already handled the trap that a body
still carrying the template's `[Functional / Integration / …]` placeholder has declared **nothing**.
Adding a second parser would have given the platform two readers of one line, which is this plan's
own rule against two formats. **Team decision 2026-08-19: one parser.** `declared_type` and a new
`declared_priority` now live in `backend/apps/workitems/test_cases.py` — the module that owns test
cases — and `apps/a11y/journeys.py` asks it rather than parsing. The dependency direction is right:
a11y and quality both sit above workitems, never the reverse.

Priority is the same shape of problem seen from the other end. When test cases become work items
(`backend/apps/workitems/test_cases.py:63`), only `{test_case_artifact_id, tc_id}` are copied. The
Test cases screen then reads `priority` from the **work item** (`backend/api/views.py:1409`), where
it was never written — while defect severity reads it from the **artifact**
(`backend/apps/quality/services.py:367`), where it lives.

*Corrected while building:* the Priority column was **not** blank for every case. A **manually
added** case stores its priority in `external_ref` (`views.py:1394`), so it showed. It was blank
for exactly the **agent-generated** ones — which on a real project is all of them.

**Worth stating plainly:** accessibility coverage does **not** depend on this. Every generated
script captures accessibility evidence, not only the accessibility cases — deliberately, because a
login screen is exactly as likely to have an unreadable button as one somebody wrote a case for.
This gap is about what a person can *see*, not about what gets checked.

**What we change.**

- `backend/apps/workitems/test_cases.py` — the platform's one reader of both lines
  (`declared_type` / `declared_priority` / `declared_fields`), using the same two-step
  `_test_case_severity` already used: structured `external_ref` first (free), the document body
  only when it is absent. `_test_case_severity` **stays** in `apps/quality` — it adds a fail-safe
  "unknown means Critical" which is right for a defect and would be a lie on a screen.
- `backend/apps/workitems/test_cases.py:63` — copy `type` **and** `priority` onto the work item's
  `external_ref` when materialising. Absent stays absent; nothing is guessed.
- `backend/api/views.py:1409` — return `type` alongside `priority`.
- `frontend/src/features/lifecycle/TestCases.tsx` — a Type column and a filter chip
  (All · Accessibility · Functional · E2E …), and Priority now populated.

**What you see afterwards.** Open a story's Test cases screen. Each case shows its type and
priority. One click filters to the accessibility cases.

**How we prove it.** A case with `Type: Accessibility` materialises carrying its type and priority;
a case whose document says neither materialises with both blank rather than a default; the screen
renders the column and the filter narrows the list.

*As built:* eleven backend tests and three frontend ones. Backend: a case materialises carrying
what it declared; a case that declared neither carries **no keys at all** rather than blanks; the
template's own placeholder declares nothing (the trap the move must not lose); structured
`external_ref` beats the body; a later run that could not read the document does **not** blank what
an earlier one recovered; the readers themselves; and `journeys.declared_type is declared_type` —
literally asserting one parser, not two. REST: the endpoint returns the type, and a case that never
said comes back blank. Frontend: the Type column and filter narrow the list; a filter that matches
nothing says *"No integration test cases"* rather than looking like a story with none; `cleanup()`
runs in that describe because this file predates auto-cleanup being off.
`test_materialize_test_cases.py`, `test_test_cases_rest.py`, `test_a11y_journey.py`,
`test_quality.py` — 87 passed. `lifecycle.test.tsx` — 25 passed. `tsc -b` clean.

**Two decisions taken with this task (2026-08-19):**

- **The approved screen was updated in the same change.** `docs/design/screens/S-35-test-cases.html`
  had four columns and no filter; the DoD requires the app and the screen to agree, so the wireframe
  now carries the Type column, the filter chips, and a row showing "—" for a case that declared
  nothing. Rendered and checked in the design gallery.
- **No backfill.** Test-case work items that already exist stay blank until the Testing phase runs
  again on that story. A backfill would mean reading every test-case artifact's body out of the
  object store inside a migration, which does not belong in one. Said plainly rather than implied.

**Size M · Risk low · Needs first: nothing.**

---

### G3 · A finding does not say which test case found it

🟢 **Built 2026-08-19.** A greenfield finding now names the test case that found it and links
to it and to its run, in the review console's own provenance row. A brownfield finding shows
nothing extra — the nulls are correct data, not a gap. Six backend tests, two on the screen.

**In plain words.** In the review console a QA Lead sees *"1.4.3 · /checkout · button.pay"* and has
no way to reach the story, the test case or the run that found it. On brownfield that is correct —
an audit of an existing application has no story. On greenfield it is a hole.

**Why it happens.** The data exists and is simply not passed through. `A11yFinding` carries
`first_seen_run` and `last_seen_run` (`backend/apps/a11y/models.py:452-457`), and for a greenfield
finding that run's work item **is** the test-case work item. The projection the screen receives —
`_item()` in `backend/apps/a11y/review.py` — never includes them.

*Traced rather than assumed, because it is the load-bearing claim:* findings are recorded against
the **capture** run, not the judge's — `aipass.finish_ai_pass` publishes for `source_run`
(`aipass.py:192`) — and Test Automation runs one test case per run. Worth checking twice after G4:
the **judge's** work item is the carrier that task hid, and it is not the one a finding points at.
And on brownfield, `record_run_findings` resolves the audit's key to `None` on purpose
(`findings.py:225`), so an audit finding carries no run at all.

It was invisible until now because the console was designed against the brownfield case, where
there genuinely is nothing to link to.

**What we change.**

- `backend/apps/a11y/review.py` — `_provenance()` gives `_item()` four fields: `source_run`,
  `work_item_id`, `work_item_label` and `work_item_title`, read from `last_seen_run` (falling back
  to `first_seen_run`). All four are `null` when the run does not exist or has no work item —
  which is the honest answer for a baseline audit, not a bug. `select_related` on the queue **and**
  on the single-item read, so neither fires a query per row.
- **`work_item_label` is the case's own `TC-031`, not the platform's `WI-84`** — that is what a QA
  Lead recognises and what the document calls itself (G2 is what makes it reliably present). It
  falls back to the work-item key, because the source is not always a test case: a capture posted
  from CI is keyed to the project, and a finding can hang off a story.
- `frontend/src/features/a11y/A11yReview.tsx` — **a fifth item in the detail panel's `meta-row`**,
  not a new line under the route. That row is already where this screen puts provenance: its
  decided state shows *"Decided by Aisha Khan"* in exactly the same place, beside Screen, Element
  and Check. Putting "Found by" anywhere else would invent a second pattern next to an existing
  one. It sits directly above the capture image, which is where a reviewer is reading when the
  question "what was this test even doing?" arises.
- **Not on the queue rows.** That list is scan-and-pick: route, selector, level, verdict. Adding a
  third line to forty rows makes it harder to do the one job it has.
- **Both links open in a new tab** (`target="_blank" rel="noreferrer"`, this app's convention for
  leaving a task in hand). The reviewer holds a 15-minute claim on the item (`LOCK_MINUTES`) and a
  place in a long queue; neither should be spent to glance at a test case.

**What you see afterwards.** A greenfield finding names the test case that found it and links to
it. A brownfield finding shows nothing extra, exactly as today.

**How we prove it.** Two tests, one per shape: a greenfield finding names its test case; a baseline
finding returns nulls and the screen renders no link at all.

*As built:* six backend tests in `test_a11y_review.py` and two in `a11y.test.tsx`. Backend: a
greenfield finding built the real way round (a Test Automation run on a test-case work item) names
`TC-031`; a baseline finding returns four nulls; the label falls back to the work-item key when the
source is a story; a finding whose run has since been deleted (`SET_NULL`) returns nulls rather
than raising on the queue everyone opens; the provenance costs **zero** extra queries across eight
rows, asserted with `django_assert_num_queries(0)` so the `select_related` cannot be dropped
silently; and the single-item read carries the fields too — the panel the reviewer judges in reads
`open_item`, not the queue. Frontend: the greenfield state renders both links with the right hrefs
and `target="_blank"`, and the brownfield state renders **neither**, checked after the panel is up
so the absence is the screen's answer rather than a slow render. `test_a11y_review.py`,
`test_a11y_findings.py`, `test_a11y_review_rest.py` — 100 passed. `a11y.test.tsx` — 13 passed.
`tsc -b` clean. `docs/design/screens/S-36-a11y-review.html` updated in the same change and rendered
in the gallery: the second panel keeps **no** "Found by", with a comment saying why, so the file
shows both shapes.

**Found while building, not fixed (out of scope):** `_item()`'s docstring says `evidence` is
"passed in for the list (one query pass)", but `queue()` does not pass it — so `evidence_for` runs
per row, two queries each. Eight findings cost about forty queries, and that was true before this
task. The docstring describes an intention the code never implemented.

**Size M · Risk low · Needs first: G2 (so the test case's own type is available to show alongside).**

---

### 8a · B1 + B4 + B2 · The audit screen, and the way in

🟢 **Built 2026-08-19.** A brownfield user finishes onboarding, sees *"6 · Check
accessibility"*, pastes their page list, presses **Run audit**, and reads the result — no terminal
at any point. 131 backend tests and 36 on the screens. **One acceptance criterion still needs a
real run** — see *What only a live run can prove* at the end of this entry.

**In plain words.** Today, auditing an existing application means two things a user cannot do in
the product: registering the list of pages by raw HTTP, and running a command in a terminal. This
task replaces both with a screen, and puts a step in onboarding so people find it.

The wireframe is approved: **`docs/design/screens/S-38-a11y-audit.html`** — seven labelled states
for this task, plus three for the keyboard journeys (task 10) on the same tab.

**Why it happens.** QA-17 built the REST endpoints and the companion command; no screen was ever
built. `frontend/src/api.ts` has clients for review and conformance only. Four backend endpoints —
`a11y-policy`, `a11y-routes`, `a11y-audits`, `a11y-backlog` — have no client at all. And
`A11yRoute.Source.ONBOARDING` exists as a value in the code that nothing has ever written: the hook
for this was planned and never finished.

**Found before building, and it changes everything else in this task.** The audit program could
not run on ANY machine, and never had. It imports the browser (Playwright) and the scanner
(axe-core) by name, and Node resolves a bare name from the IMPORTING FILE's directory upward —
`runner/companion/assets/`, where the companion ships no `node_modules` and no `package.json`.
`cwd` is not consulted and `NODE_PATH` is ignored for ES modules, so neither running from the
project nor setting the environment helped. Verified three ways rather than reasoned about: bare
import → `ERR_MODULE_NOT_FOUND`; with `NODE_PATH` → still `ERR_MODULE_NOT_FOUND`;
`createRequire(cwd)` + `import(pathToFileURL(req.resolve(…)))` → resolves.

*Why nothing caught it:* **no test had ever executed the script.** Every test stubs it, and the one
real invocation points at a missing `node` on purpose to check an error message. A green suite
proving "it behaves as designed" while nobody could reach it — exactly the pattern this whole plan
was written against.

Anchoring on the audited project is also right on its own terms (team decision ①): the report names
the scanner version that produced it, and that has to be the version the client's own build uses,
not one we carry.

**What we change.** Four pieces.

**(a) The audit becomes work a machine can claim.** Today `POST /a11y-audits/` opens an audit that
visits nothing — its own docstring says so — and without someone running the CLI it sits in
`capturing` forever. We make it claimable, mirroring `CodeIntelJob` exactly, which exists for the
same reason and took the same shape:

- `backend/apps/a11y/models.py` — `A11yBaselineAudit` gains `PENDING` and `CLAIMED` statuses, an
  `enrollment` foreign key and `claimed_at`. **Migration `0026`.**
- `backend/api/urls.py` + `runner_views.py` — `GET /api/runner/a11y-audits/` to claim, mirroring
  `RunnerCodeIntelClaimView`. A **separate endpoint** on purpose, exactly as code intelligence did,
  so the proven plan / review / build claim path is not touched.
- `runner/companion/daemon.py` — a `claim_a11y_audit()` and an `audit` branch that calls the
  `run_baseline_audit` we already have.

**(b) Registering pages, for any application.** `PUT /a11y-routes/` learns two input forms:

- **one path per line** — the universal form. An optional name after two spaces. A leading `#`
  registers the page but leaves it out of scope.
- **a pasted list** — either a plain array of paths, or objects carrying `path` with optional
  `title` and `enabled`.

Anything unreadable comes back naming the line that failed. Nothing is silently dropped. Nothing
in this is specific to any one application; Meridian's file happens to fit the second form, which
is a consequence and not the design.

**(c) The screen and the way in.**

- `frontend/src/features/a11y/A11yAudit.tsx` — a third tab on the Accessibility destination,
  "Pages & audit", before Review and Conformance. Run strip, pages table, add-pages panel, past
  audits, and the five other states in the wireframe.
- `frontend/src/api.ts` + `hooks.ts` — clients for the four orphaned endpoints.
- `frontend/src/features/observability/OnboardingHub.tsx` — a new step *"Check accessibility"*
  between the gap report and Resume, linking to that tab, with a done state once an audit has run.
- `backend/integrations/onboarding.py` — the hub read model gains whether pages are registered and
  whether an audit has ever completed, so the step can show its state.

**Is B4 solved by B1?** Yes, and that is why they are one task. B1 builds the screen; B4 is whether
anyone ever finds it. A tab nothing points at is found only by someone who already knew.

**What you see afterwards.** A brownfield user finishes the gap report, sees *"6 · Check
accessibility"*, clicks through, pastes their page list, presses **Run audit**, and reads the
result — without opening a terminal once.

**Decisions the team took on 2026-08-19, recorded so they can be revisited:**

| | Decision |
|---|---|
| D-8a-1 | The audit resolves its tools **from the customer's project**, never from beside the companion, and the platform **never installs anything** into a client's project — it says what is missing, where it looked, and the one command that fixes it |
| D-8a-2 | The audit runs from **the registered repository clone** — the same repository the address comes from, so two rules can never point at different applications. No clone, no guess: the audit is closed with a stated reason |
| D-8a-3 | **One status rule, no mode flag.** An audit is *pending* when opened from the app and *capturing* the moment the first screen arrives, whoever sent it. The terminal command keeps working as a consequence, not as a second code path |
| D-8a-4 | **One box, the structured format.** The line-per-path form is dropped: its name separator was two spaces, and `normalise_path` cannot reject a space — a single space would register `/events/:id Event detail` as a real path, unreachable on every audit forever |
| D-8a-5 | **Every unrecognised key is named back**, on every column. An unreadable `path` refuses the whole paste, naming the entry and the keys it does have |
| D-8a-6 | **A confirm step before every registration.** A page is identified by its path, so a corrected path is indistinguishable from a new page — the difference is shown to the person before anything is written |
| D-8a-7 | **A pattern route is visited by example.** `/events/:id` keeps its identity; `/events/482` is what the browser opens |
| D-8a-8 | **Every change to the page list is recorded** — in the ledger, on the run strip, and in the report |

**As built.**

- **The tools are found where they live.** `importFromProject` in `a11y_audit.mjs`, plus a
  `--check` mode and `a11yaudit.preflight` so a folder that cannot run an audit says so BEFORE one
  starts rather than after one reports nothing. No browser is fatal; no scanner is a warning and
  the pass still runs. `finish_a11y_audit` gained a `reason` that replaces the generic "the
  application did not respond", which would send someone to check a server nothing ever contacted.
- **The audit is claimable.** `A11yBaselineAudit` gains `pending`/`claimed`, `enrollment` and
  `claimed_at` (**migration 0026**, which also adds `A11yRoute.example_path`). New
  `GET /api/runner/a11y-audits/` mirroring `RunnerCodeIntelClaimView`; a daemon branch beside
  `claim_code_intel`. **A seam the plan missed:** `run_baseline_audit` opened its own audit as its
  first act, so every claimed audit would have created a second one — it now accepts the audit it
  was handed, and reads the manifest back with `get_a11y_audit` so a companion that reconnects
  never opens another.
- **Recovery is same-machine only, deliberately.** A companion that restarts picks its own audit
  back up past the lease; another machine never takes it over, because an audit belongs to the
  machine that can reach the running application and a colleague's may not have it up — handing it
  across would produce a report saying every page was unreachable, which is worse than a visibly
  stalled audit.
- **Registration.** `parse_routes_text` (the platform parses, so one refusal is worded once),
  `_read_entries` (one reader for the preview and the write, so a confirmation can never describe
  something the write would reject), `preview_registration`, and `_record_change` writing
  `a11y.routes.registered` to the ledger — the app already writes it for review decisions and
  conformance signatures, and scope was the one change of that weight leaving no trace.
- **`scope_change_since`** compares today's list against the one the last finished audit froze —
  both already existed and neither is invented. Surfaced above the Run button and in the baseline
  document, so a reader who never opens the screen is not misled either.
- **The screen.** `frontend/src/features/a11y/A11yAudit.tsx`, a third tab (first), clients for the
  four endpoints that had none, and **"6 · Check accessibility"** on the onboarding hub with Resume
  moving to 7.

**Found while building, and fixed:** the screen rendered *"No pages are registered yet"* before
authentication resolved — the query is disabled until the project is known, so `isLoading` is false
and the data is undefined. On this screen of all screens that sentence has to be an answer rather
than a stage of loading. Caught by a test, not by reading.

**How it is proven.** 131 tests in `test_a11y_baseline.py` (+52 in `test_a11y_baseline_report.py`),
36 across `a11y.test.tsx`, `audit.test.tsx` and `conformance.test.tsx`, 21 in
`observability.test.tsx`. Includes **three tests that execute the audit script for real** — the
first in this codebase — skipped where there is no Node but never faked, because faking is what hid
the resolution bug. `tsc -b` clean; ruff clean; eslint clean apart from the pre-existing
`Gates.tsx` rule-not-found.

**What only a live run can prove.** That a full audit of a real application completes from the
screen. It cannot be checked here: the running app points at the **shared** database, where
migrations 0021–0026 are unapplied and applying them is the team's call, never a build's. So the
first real run is still ahead of us, and this entry does not claim otherwise.

**Size L · Risk medium — a claim path, a migration, and a fix to code no test had ever executed ·
Needed first: B3 (the address) and B5 (the passes) — both landed.**

---

### 8b · The page editor

🟢 **Built 2026-08-19.** A page can be corrected, renamed, taken out of scope or removed
one row at a time. The ghost page is now impossible rather than warned about. 12 backend tests and
7 on the screen.

Everything in 8a registers pages in bulk. Editing one still meant re-pasting the list, and the
confirm step exists precisely because a re-paste cannot express "rename this". A row editor can:
the platform edits a row it already knows, so the ghost page becomes impossible rather than merely
visible.

**What changed.**

- `routes.update_route` edits ONE named row. `EDITABLE` is `path`, `label`, `enabled`, `notes`,
  `example_path` — `source` and `id` are deliberately absent, because who put a page here is a
  fact about how it arrived and a row's identity is not something a person edits. Anything else is
  refused **by name**.
- **Renaming onto a page that already exists is refused, not merged.** Merging two rows would
  silently discard whichever page's name and scope lost, and the audit would then visit a page
  under a description nobody wrote for it. The refusal names the page it collided with.
- `routes.delete_route` removes a page **that was never real** — never opened, nothing recorded
  against it — and takes any other page out of scope instead, keeping it visible as excluded. The
  disabled-never-deleted rule protects pages that existed; a path typed by mistake never was one,
  and keeping the row forever is noise on a screen people have to read. The screen says which
  happened, afterwards, because the answer depends on what the page accumulated and the person
  asking cannot be expected to know.
- `routes.history_for` gives every row its `open_findings` and `visits` in one query pair, so the
  rename warning is there the moment the path field is touched rather than after a round trip.
- `PATCH`/`DELETE /api/projects/<id>/a11y-routes/<route_id>/`.
- The Pages table is the editor: **Add a page** leads (the everyday action), **Import a list**
  follows (how a project starts, not how it is kept), the in-scope toggle writes, and every row
  has Edit and Remove.

**What it does NOT fix, and cannot.** A finding is identified by *(route + element + rule)*, so a
rename leaves the page's history behind whatever the input form is. The editor makes that
*knowable* — the platform is certain it is a rename — which is the prerequisite for warning at all.
Team decision: **warn and proceed**, never rewrite recorded findings. A test asserts the findings
stay at the old address, so nobody can quietly "improve" this later.

**Found while building:** replacing the Excluded badge with an editable toggle lost a word. A
toggle that is off reads as *"not set yet"*; **Excluded** is a decision somebody took about that
page. The cell now carries both, and a test holds it there.

**How it is proven.** 12 tests in `test_a11y_baseline.py` — the rename creates nothing, a refused
edit changes nothing, a collision is refused naming the other page, an edit that changes nothing
writes nothing, every edit is recorded with its before-value, a typo can be deleted, an audited
page cannot, a clean-but-visited page cannot either (being clean is a result, not an absence). 7 on
the screen, including the rename warning appearing for a page with history and **not** appearing
for one without — a warning on every rename is a warning nobody reads by the third one.

**Size M · Risk low — a change to a table 8a already built.**

---

### 9 · G3b · The review list fetches evidence nobody reads

**In plain words.** Opening the accessibility review console asks the server for the waiting list.
For every item in it the server digs out the screenshot information — which picture exists, where
the marker goes, why there is none. **The list does not show any of that.** It shows the rule, the
page, the element, the level and the verdict. The picture belongs to the detail panel, which
fetches its one item separately.

**Measured, not estimated.** Counted with `CaptureQueriesContext` on local Postgres: 8 findings
cost **40** database round trips where about 4 would do (2 per row when the evidence exists, 4 when
it does not, because each lookup misses and then falls back). The endpoint passes no limit, so a
project with 200 open uncertain findings loads all of them.

**Why it is like this.** `_item()`'s docstring says `evidence` is *"passed in for the list (one
query pass)"* — an optimisation for a design where the list carried its own evidence. The screen
was built the other way, and the work the old plan required was never removed.

**What we change (team decision, option b).** `queue()` stops computing evidence. Three assertions
move from the queue to `open_item`, which is where the screen actually reads them
(`test_a11y_review.py:159`, `:184`, `test_a11y_review_rest.py:94`). Query cost becomes flat.

**The one risk, stated.** It is a REST response shape change — five fields leave the list payload.
Nothing in this repository reads them; anything outside it would stop seeing them.

**Size S · Risk low · Deliberately its own commit**, so a contract change is not hidden inside a
feature.

**BUILT — 2026-08-19.** `_item` splits: `_row` is what is true of a finding without going and
looking for its capture, and the five evidence keys are added only when a caller passes
`evidence=`. The only caller that does is `open_item`.

*Measured after, the same way as before:* **8 findings → 8 round trips, and 60 findings → 8**, of
which six are the tenant-scoping statements Django issues around any query. **Two real queries,
and two is what it stays at.** Before: 40 for 8.

On the frontend the type splits with it, which is what makes the mistake impossible rather than
merely absent: `A11yReviewItem` is the queue row, `A11yReviewFinding` extends it with the capture,
and `Capture` takes the second — so a component reaching for a picture in the list no longer
compiles. The test fixtures split the same way (`row()` / `item()`).

Proven by: a queue row asserted to carry none of the five keys; the same five asserted present on
the item read, in the module and over REST; and a query-count test that doubles the findings and
asserts the round trips do not move — the *shape*, not a hard-coded number that would break on any
unrelated change and teach the next reader nothing.

---

## 4. G6 · The keyboard journey, working on both journeys

This has its own section because when I looked for the fix, the gap turned out to be bigger than
"nobody calls it" — and because a team decision then made the hardest half of it unnecessary.

### What it is for

Eight WCAG criteria cannot be measured by reading a page standing still — keyboard traps, focus
order, visible focus, status messages. They are only answerable by *operating* the application.
The industry scanner covers **one** of the eight. That is the whole reason this agent exists.

### What is actually missing — three things, not one

1. **No caller.** `start_journey_check` (`backend/apps/a11y/journey.py:122`) is never invoked
   anywhere in the platform, the orchestration layer, the MCP server or the companion. Only tests
   call it.
2. **No browser.** `playwright_tools_for` (`runner/companion/guardrails.py:385`) grants the browser
   only when the phase is `test_automation`. The journey's phase is `a11y_journey`. And it is
   dispatched as a *planning* run, which on the companion gets `PLAN_ALLOWED_TOOLS` — platform
   state tools and nothing else (`runner/companion/daemon.py:41`).
3. **No address.** `journey_for_run` hands the agent its steps, its preconditions and the eight
   checks — and no address for the application.

So even with a caller wired in today, the agent would start, find it has nothing to open, and
honestly report every step blocked.

### The design: the journey runs against an application the user has started

**Team decision, 2026-08-19 (D-G6b).** On both journeys the user starts the application and gives
its address when they are ready. Keyboard-journey testing is something a person does once the
application is built and running — it is not something the platform should try to squeeze into the
few minutes a build has an app up.

That decision removes the hardest and riskiest part of this task. There is **one** path, and
greenfield and brownfield use it identically:

| | Who starts the application | Where the address comes from |
|---|---|---|
| **Brownfield** | The user | The last audit's address, pre-filled and editable |
| **Greenfield** | The user | The repository's Preview URL, pre-filled and editable |

Three consequences worth naming, because they are what make this safe:

- **Nothing in the build path changes.** No new activity in `BuildWorkflow`, no change to
  `runner/companion/runner.py`, no extension of the window in which a build holds an app up. A
  build cannot be slowed, delayed or failed by anything in this task.
- **A journey never runs unasked.** One journey is a real browser walking every step of a test
  case, which is far more expensive than judging a still page. Making it deliberate is both
  honest and cheaper.
- **If the application is not up when the button is pressed, the run fails immediately with a
  readable reason** — *"nothing answered at that address"* — and records no steps at all. The
  platform never reports on steps it did not walk.

**One constraint the team should know now:** a journey **is** an E2E test case. On a brownfield
project that has just onboarded and audited, no test cases exist yet, so there is nothing to walk.
The panel says exactly that — *"no walkable journeys yet; run the Testing phase to write them"* —
rather than showing an empty list that looks like a fault.

### Three slices

**G6a · Give the journey an address and a browser** *(the shared core — everything else depends on it)*

- `backend/apps/a11y/models.py` — `A11yJourneyRun` gains `base_url`. **Migration `0027`.**
- `backend/apps/a11y/journey.py` — `start_journey_check` takes `base_url` and refuses to start
  without one, with a sentence saying why. `journey_for_run` returns it, so the agent's contract
  now includes where to go.
- `runner/companion/guardrails.py` — `playwright_tools_for` grants the browser for `a11y_journey`
  as well as `test_automation`. This is safe for the reason the code already states at `:394`: the
  real bound is the egress policy scoping the browser to one host, not the tool's name.
- `runner/companion/daemon.py` — wire the Playwright MCP server into the planning path for that one
  phase, exactly the way `codeintel_mcp` is wired in at `:348`, scoped to the journey's address.
- `agents/09d_a11y_journey/agent.md` — name the browser tools it may use and the address it is
  given, and state that a mouse click invalidates the test. The body already says the second part.

*Size M · Risk medium — it widens a tool grant, so the egress scoping must be asserted, not assumed.*

---

#### G6a — BUILT, 2026-08-19, and three things the plan above had wrong

**① The safety argument for the browser did not hold.** The line above says the grant is safe
because "the real bound is the egress policy". Checked: **`EgressPolicy` does not exist on the
planning path at all**, and on the build path it gates *shell commands* (`check_command_egress`),
never a browser. The browser's only bound, on both paths, is the `--allowed-origins` argument
handed to the Playwright server.

That matters, because the build path writes it as `if preview_url:` — so an unresolved preview URL
there **silently launches an unbounded browser**. Not repeated here. A journey is refused twice
over: `start_journey_check` will not dispatch without an address, and the companion raises rather
than launching if a payload somehow arrives without one. Asserted, not assumed.

**② G6b's claim endpoint is dropped — team decision, 2026-08-19.** It would have built a second
delivery route beside one that already works. The audit (B1) needed its own because an audit is
*not an agent run* — no run, no engine, nothing to report through. A journey **is** an agent run,
so it already travels the planning dispatch channel every companion phase uses, which has already
learned five things a new route would have to learn again: routing to the right machine, handing
work to any available machine when the intended one is not running, re-handing work a dead machine
abandoned, never letting two machines take one job, and surviving a dropped database connection.
Every one of those was originally found by a user. What is left of G6b — a carrier work item per
journey, queueing several at once — moves into the next slice.

**③ Two end-to-end blockers the plan did not list, both now closed.**

- **A journey would never have completed, even walking perfectly.** The write-completeness gate
  asks every phase for the document it registered, and 09d registers none. Without an
  `a11y_journey` branch — the one the judging pass already has, for the identical reason — a
  flawless walk would have parked its run asking for a file it was never meant to write.
- **A walk whose run died read `walking` for ever.** `finish_journey` has exactly one caller, the
  agent, and an agent that died is not still running to call it. The platform now closes it on
  both the success and the failure path, keeping everything the agent did record and accounting
  for the rest — the steps nobody spoke about become `not_reached`, never "passed".

And one race closed: `start_journey_check` triggers the run and writes the journey row afterwards,
because the row is keyed by the run id the trigger returns. A companion claiming inside that window
would have started an agent whose first call failed with *"no accessibility journey is attached to
this run"*. The claim now defers one poll — about a second — rather than handing out a task that
cannot work.

**How the address travels.** Read at claim time for the one phase that needs it, not added to the
generic dispatch payload — that payload's shape belongs to every phase in the platform, and the
Temporal input behind it more so. Every other phase's payload is byte-identical to before, and
there is a test that asserts exactly that.

*Proven by: a journey refused before anything is read when it has no address, and nothing
dispatched; the agent's contract carrying the address; the address stored as walked rather than
looked up later; a browser locked to that address and to nothing else; a journey with no address
reported failed with the engine never started; every other planning phase still having no browser
at all; the phase string the companion hardcodes checked against the agent catalog; the claim
carrying the address, deferring when the row is not written yet, and leaving every other phase's
payload untouched; a walk closed by the platform on both the success and the failure path, keeping
its findings; closing being idempotent and a no-op on a run that has no journey; and a journey
blocked half way reported rather than failed.*

**Not yet proven, and only a live run can:** that a real browser, driven by 09d, walks a real
application and comes back with findings.

---

**G6b · One carrier per journey, and starting several** *(what the screen's Run button needs)*

- A carrier work item **per journey**, keyed by test ref and marked a carrier from the start
  (see G4), mirroring `aipass.judging_work_item`. Needed because the platform refuses a second run
  on a work item that already has a live one — so without this, "Walk 2 selected journeys" would
  start one and refuse the other.
- Queue N journeys, capped by the existing `MAX_JOURNEYS = 10`, with the excess **reported**.
  `start_journey_check` walks `journeys[0]` and stops today.
- `POST /api/projects/<id>/a11y-journeys/` to queue, `GET` to list. Same QA Lead gate as the rest
  of the destination; a reader sees everything and starts nothing.

*Size M · Risk low · Needs G6a.*

#### G6b — BUILT, 2026-08-20

**One work item per journey.** Every agent run in this platform hangs off a work item, and the
platform refuses a second run on one that already has a live one. Sharing a work item would have
started the first ticked journey and had the rest turned away by a rule that was never about
them. Each journey now gets its own, keyed by test ref, **marked a carrier from the start** so it
never reaches anybody's board — the mistake the judging carrier made and G4 had to come back and
fix. Asserted against `CARRIER_SOURCES` itself, not a copy of the string.

**Nothing is dropped in silence.** What the cap left out, a journey already being walked, a
dispatch that was refused, an E2E case with no readable steps, and a name asked for that this
project does not have — every one comes back named, with its own reason. A journey quietly not
run reads exactly like one that passed.

**Two endpoints, one payload.** `GET/POST /api/projects/<id>/a11y-journeys/`. The `GET` carries
the address to pre-fill — the last audit's, else the repository's Preview URL, with the reason to
show when there is neither — so the panel reads one payload instead of making two calls. That is
the plan's G6c item moved here, because otherwise the endpoint gets built twice.

**Anyone may look; only the accessibility reviewer may start one.** `403` on the POST, `can_start`
on the GET so the screen greys the button rather than failing on click. Enforced in the module,
the way `conformance.sign` does it, because the role is a project Membership.

**One cost fixed on the way past.** Listing journeys read every test case's body out of the object
store — ninety reads on a project with ninety cases to find three journeys. It now checks the type
the Testing agent already stamps on the artifact and only opens the ones that claim to be
journeys. Free where the stamp is there, unchanged where it is not. The same mistake task 9 had
just fixed in the review list.

*Proven by: three ticked journeys starting three runs on three distinct work items; a journey's
work item being invisible to `carrier_q` while the real story stays visible; the same journey
started twice refused **by name** while the others still start; ten started and the eleventh
named; a reader listing and being refused the button (`403`, nothing started); a name this
project does not have coming back named; no address starting nothing and saying why; the panel
showing E2E cases it could not walk with their reasons; "last walked" empty meaning never walked;
the address preferring the last audit then the repository then saying what to go and set; and a
spy proving three test cases stamped `Functional` are never opened.*

**Not proven, and only a live run can:** that a queued journey is picked up by a real companion
and walked by a real browser.

**G6c · The way a person starts one** *(the same on both journeys)*

A **"Keyboard journeys"** panel on the Accessibility → Pages & audit tab (S-38), directly under the
audit strip, because it is the same subject, the same role and the same address field.

- It lists the walkable E2E test cases the project has, each with when it was last walked and how
  it went. Where there are none, it says why and points at the Testing phase.
- The address is pre-filled from the last audit (brownfield) or the repository's Preview URL
  (greenfield), and is editable — the user confirms the application is up before starting.
- **Run** starts the selected journeys, capped by the existing `MAX_JOURNEYS = 10`. Anything over
  the cap is **reported**, never silently dropped.
- A **"Run keyboard journey"** action on an individual E2E test case, for walking just that one.
- Backend: `POST /api/projects/<id>/a11y-journeys/` to queue, `GET` to list. Same QA Lead role gate
  as the rest of the destination; a reader sees everything and starts nothing.

Frontend: `A11yAudit.tsx` gains the panel; `api.ts` and `hooks.ts` gain the two calls.

*Size M · Risk low — it starts work, it does not change how anything is judged · Needs G6b, and
shares a screen with B1 so it is cheaper built after it.*

#### G6c — BUILT, 2026-08-20. **A person can now start a keyboard journey.**

The panel sits on Pages & audit, under the audit strip, and **renders whether or not any pages
are registered** — a journey follows a test case, not the page list, so a greenfield project that
has run the Testing phase and registered nothing must still be able to walk one. A panel that
vanished with the page list would look like a feature that does not exist.

What it says, and why each sentence is there:

- **No journeys yet** → *"run the Testing phase and they appear here"*. Not an empty table. A
  project whose Testing phase has never run must not look like one with no keyboard problems.
- **The address**, pre-filled and editable, with where it came from — your last audit, else the
  repository — or what to go and set when the platform holds neither.
- **Start your application first**, said *before* the button, because it is the one thing the
  platform cannot do for anyone: nothing here starts an application, and a walk against an
  address nothing answers on stops immediately and records no steps.
- **No machine connected**, also before the button, matching the audit strip above it.
- **What could not be walked**, with its reason. A test case that declares `Type: E2E` and has no
  readable steps is a different fact from a project with no journeys.
- **What the cap left out**, by name.
- **After pressing**: what started, and what did not *and why*, each by name.
- A reader sees all of it, is told the QA Lead starts them, and gets a disabled button rather
  than one that fails on click.

**Watching it happen.** A journey's work item is a hidden carrier, so Phases & Runs cannot show
it — this panel is the only place a person can see a walk in progress, and it polls while one is
running. A journey being walked cannot be ticked again.

*Proven by eleven tests: the empty state saying why; the address and its source; unwalkable cases
shown with reasons; two ticked, one started and one refused, both named on screen; a reader
seeing the list with the button disabled; a walking journey un-tickable; a finished walk showing
what it found and a blocked one not reading as clean; the cap named; no address meaning no start;
no machine said before the button; and the panel present with no pages registered.*

---

### A loophole the cross-check found, and closed

Not from a failing test — from tracing the path end to end before building the screen on top of
it.

**Two journeys from test cases nobody stamped with a `TC-…` would have collided.** `journey_from`
reads the test ref off the artifact and leaves it blank when the producer wrote none, and G6b
keyed each journey's work item on that ref. Two unstamped journeys therefore shared one work
item — so the second was refused as *"already being walked"* by the first, and the panel showed
each of them the other's last walk. Exactly the bug G6b existed to fix, one level down.

Keyed on the **artifact** now, which is the document's identity and is always present. The test
ref is what a person reads; the artifact is what the platform counts. Both directions are tested.

**And one thing worth having found along the way:** the journey's work item now also carries
`tc_id`, because that is the key the review console reads to say where a finding came from (G3).
Without it a keyboard finding would have been attributed to *"WI-84"* — the internal number of a
work item deliberately hidden from every board — instead of to *TC-031*.

### What the cross-check confirmed was already sound

| Seam | Verified |
|---|---|
| A journey finding never blocks a gate (D1) | `policy.ADVISORY_CHECKERS` is the eight journey checkers, keyed on **checker** not source, and the gate reports them in its own sentence |
| Journey findings reach the review queue | recorded with `needs_review`, which is exactly what `findings.review_queue` selects |
| Journey coverage reaches the conformance report | `coverage.record` is called for every verdict, pass included |
| A confirmed journey finding raises a ticket | `finish_journey` calls the defect loopback |
| Reachable from onboarding | hub step 6 links `/a11y/pages`, which is where the panel is |
| Tenant isolation | `A11yJourneyRun` + step results proven under RLS on a non-superuser connection |

### One cost, measured and accepted

Listing journeys reads the E2E test cases out of the object store. With the type filter G6b added
that is only the cases that claim to be journeys — for a project whose Testing agent stamped them,
three reads rather than ninety. For older artifacts with no stamp it still reads all of them, and
that is stated here rather than left to be discovered.

### What you see afterwards

For each journey: every step recorded as **walked**, **blocked** or **never reached** — a blocked
step must say why, and everything after it is never-reached, not passed. Up to eight verdicts per
step. Findings land in the same ledger, the same review queue and the same conformance coverage as
everything else.

**And one thing that does not change:** findings from this agent are **reported, ticketed and
reviewed but never block a gate** — the team's decision D1, because the agent has not yet been
proven against a real application. The gate passes and says they are there.

### How we prove it

- G6a: the agent's contract carries an address; a journey started without one is refused with a
  readable reason; the browser grant is asserted for `a11y_journey` and still refused for every
  other planning phase.
- G6b: a queued journey is claimed, walked and finished by a stubbed companion; its carrier work
  item is hidden.
- G6c: queueing caps at ten and reports the excess rather than dropping it; a project with no
  walkable E2E case returns an empty list with the reason, not an error; a reader cannot queue one;
  and a journey started against an address nothing answers on fails with a readable reason and
  records no steps.

---

## 5. Database changes

Three migrations. Two are additive schema changes, neither touching an existing column; one is
data-only and adds a single key to rows that already exist.

| Migration | What it does | For |
|---|---|---|
| `workitems/0006_a11y_judging_carrier_marker` | Marks the judging work items already on people's boards as carriers. Data only — no schema change | G4 · **built** |
| `a11y/0026_audit_claimable` | `A11yBaselineAudit`: `PENDING`/`CLAIMED` statuses, `enrollment`, `claimed_at` | B1 |
| `a11y/0027_journey_address` | `A11yJourneyRun`: `base_url`. One column, additive | G6a · **built** |

The two schema ones are RLS-aware from the first migration, like every table in this platform. The
data one runs as the privileged migration role for the same reason `a11y/0005` does: work items are
FORCE ROW LEVEL SECURITY, so a merely-owner role would read zero rows and quietly do nothing.

⚠️ **Corrected on 2026-08-20 by reading the shared server directly: it was not six, it was 32,
and it started at `a11y/0001`.** Nothing accessibility-related had ever been migrated there — the
tables did not exist. The full list was `a11y/0001`–`0027` (all 27), `integrations/0010`,
`projects/0011`, `registry/0006`, `registry/0007` and `workitems/0006`; the two `registry` ones
seed the judge and journey agents, so without them nothing judged and nothing walked. Every
pending migration in the whole platform was accessibility work.

✅ **The team applied all 32 on 2026-08-20.** Re-read afterwards: nothing pending, in any app.
`TESTING_GUIDE.md` §1 carries the list of what landed.

---

## 6. Decisions already taken, and what is still open

**Taken by the team, recorded so they can be revisited:**

| | Decision |
|---|---|
| D-A | Capture all four scanner answers, not just violations (chosen over showing only what the platform could act on) |
| D-B | The signature on a conformance statement is the gate |
| D-C | New evidence marks a signed statement stale rather than clearing it |
| D-G6 | The keyboard journey must work accurately on **both** greenfield and brownfield |
| D-G6b | On both journeys the **user starts the application and gives the address**. No in-build variant is built, so nothing in this work can affect a build. |
| D-B2 | Page registration must be generic to any application, never shaped around one |
| D-B5 | The 60-page limit is solved by running in passes, not by raising the number |

**Still open:**

- **The notification bell** counts gates and clarifications, not accessibility work. Arguably it
  should. Not changed, because it affects an existing screen and was not asked for.
- **`.diagram-frame` is 2.29:1 contrast** in our own design system, used by S-29. Flagged three
  times now, still not fixed. We are building an accessibility product.

---

## 7. What is still true about proof

Six of the twenty-four built tasks have never run against a real browser, and every task in this
plan adds to what a real run would prove. A green test suite here means *"it behaves as designed"*.
It does not mean *"the scanner really returns what we think it returns"* — only a live run does
that, and the first one is still ahead of us.

Where a task below can only be half-proven by tests, it says so in its own words rather than
leaving the team to assume otherwise.

---

## 8. Two documents to rewrite when this work is done — DONE, 2026-08-20

Both carried a correction notice rather than a rewrite, because most of what was wrong in them
stopped being wrong the moment these gaps closed. Both notices are now gone.

- **`TESTING_GUIDE.md`** — **rewritten from the source, walked screen by screen.** It now covers the
  whole journey a user walks on both tracks, with the accessibility work in its real place inside
  it (greenfield: an evidence capture inside Test Automation; brownfield: step 6 of 7 on the
  onboarding hub), and with the terminal steps gone because they no longer exist. The one remaining
  terminal step is starting the companion, which is not an accessibility step and is stated as such.
  Three of its own numbers were corrected against the code while rewriting: the AI half covers
  **five** criteria today and not the eleven the registry classifies as AI-owned; the human-only
  remainder is **23**, not 22, because 2.4.7 is registry-owned by `ai` and covered by the journey;
  and the pending-migration count is **32**, not five (see §5).
- **`TASK_BACKLOG_QA.md`** — its 31 tasks are correctly ticked against their own acceptance criteria,
  and the reachability notice is replaced by a statement that all eleven gaps are closed, that a tick
  now means both *behaves as specified* and *a person can reach it*, and that reachable still is not
  the same as run.

### The walkthrough that produced the rewrite produced fifteen more findings — BUILT, 2026-08-20

Places where what was built worked but, read as the person using it, would not have served them.
**The team reviewed all fifteen and approved fourteen; all fourteen are built.** The fifteenth is
the 32 pending migrations, which are the team's to run. `TESTING_GUIDE.md` §9 carries every one
with what was wrong, what was done and how it is proven; the four that changed how the platform
behaves rather than how it reads are:

| | What changed |
|---|---|
| **#1** | **A failed fetch is no longer rendered as an empty state.** All four accessibility screens fell through to *"No pages are registered yet"* / *"Nothing is waiting on you"* when the server did not answer — this plan's own principle broken at the outermost layer of the screens that argue for it, and precisely what the team would have met first with 32 migrations pending. One shared `LoadFailed` panel, four branches, and the sentence that does the work: *"Nothing shown here is a statement about your application."* |
| **#2** | **Page scope and audits are role-gated.** They fell through `ProjectViewSet.get_permissions` to `AllowAny` — not even a session required — while starting a keyboard journey on the same screen was refused for anyone but the reviewer. Now **QA Lead, Tech Lead or Admin** (`policy.PAGE_MANAGE_ROLES`, team decision), checked in the view the way `repositories` does it, with `can_manage` on the payload so a reader gets the whole screen read-only. |
| **#4** | **A keyboard journey can say *waiting for a machine*.** It was marked WALKING at dispatch and the panel rendered that as "Walking now", so one dispatched with no companion online read as a browser stepping through the application for ever — while the audit strip above it had told those two states apart since 8a. Derived from the run's `dispatch.status`, so no migration. |
| **#9** | **A brownfield audit no longer needs a repository.** It resolved its browser and scanner out of the audited project's `node_modules` and refused without a local clone, which made every non-Node application unauditable unless someone added npm dev-dependencies to the client's own repository. The companion now has its own pinned toolchain (`runner/package.json`), the clone is preferred rather than required, and a fallback scan records `axe-core X.Y.Z (companion)` — because without that third piece the fix would have traded a visible limitation for an invisible lie. |

**One of them is worth remembering as a lesson rather than a fix.** #14 — accepting `in_scope` as
a synonym for `enabled` — looked like a one-line change to `ENTRY_KEYS`. It was not: that constant
fed the *ignored-keys warning* and nothing else, while the field reads were a separate list of
names. The one-line version silenced the warning and changed no behaviour, which is **worse than
the bug** — a page marked out of scope would then have been audited with nothing said about it. A
test caught it before it shipped. The two lists are now one.

**And the lesson that produced this plan, recorded so it is not learned twice:** every one of the 24
tasks passed its tests and the backlog read as complete, while a user could not register a page list,
start an audit, or start a keyboard journey. The acceptance criteria never asked *"can a person get
to this?"* Every task in this plan carries a **"What you see afterwards"** section for that reason —
it is the question the last round did not ask.

---

## 9. The first live run — 20/21 August

The first time any of this was executed against a real application. Meridian Library at
`http://localhost:4180`, 79 routes registered, 10 in scope, on a brownfield project with no Jira
and no Confluence.

**It worked, and it found four defects no test could have caught, each hidden behind the one
before it.** That is the shape of a capability that has never run: the first defect stops you
before you can meet the second. All four are fixed and all four are in `TESTING_GUIDE.md`; they
are recorded here because the *reason* each survived a green test suite is worth keeping.

| | What was wrong | Why the tests were green |
|---|---|---|
| 1 | An audit opened from the screen was born **unclaimable** — `capturing`, which no companion offers to take — while the screen read *Visiting pages*. | `claimable=True` existed only in test code. The tests asserted the right behaviour of a call the product never made. |
| 2 | The serve→audit path never called `ensure_backend_importable()`, so the audit died on `ModuleNotFoundError` — and the serve loop caught only `DaemonError`, so it took the whole companion down with it. | Every other companion path called it. Nothing tested the one that did not. |
| 3 | **Seven granted tools were never exposed.** The judge was granted 24 and the MCP server defined 17: `get_a11y_batch`, `get_wcag_grounding`, `record_a11y_finding` and all four journey tools had no `@server.tool()` wrapper. The judge and the keyboard journey had been **unrunnable since the day they were written**. | The tests checked the permission list and the HTTP route. Neither of those puts a tool in an agent's hands; only the wrapper does. There are **three** such lists, and a test now asserts that `granted − exposed` is empty. |
| 4 | `get_a11y_batch` returned every screen at once — 144 elements, about 80,000 characters — and the judge correctly refused to judge part of it. Its own docstring had said *"one screen at a time"* since the day it was written. | Every test used three elements over two screens, where paged and unpaged look identical. |

**And a fifth, taken as a precaution rather than proven:** `verify_writes` gets one minute, which
is right for "does the artifact exist" and wrong for the judge's closing step — that step files a
fallback verdict per unanswered element and then publishes a report. `LONG_VERIFY_PHASES` now
gives those two phases five minutes.

⚠️ **The evidence first given for this was a misreading, and 9.4 corrects it.** The "81 of 144"
that looked like a cancelled half-write was neither: 144 request slots are 81 distinct elements,
and the judge had answered all of them. On the first complete run this step took **22 seconds**,
comfortably inside the original minute. The longer window is still the right call — that step's
work grows with the audit, and being cut off half-way through it would leave the accounting it
exists to guarantee half-done — but it fixed a risk, not an observed failure.

**What the run proved:** capture 10 of 10, twice. An audit reaching `complete`. And the judge
recording real verdicts — 80 pass, 1 fail — including a defect no scanner can reach:
`<img id="photo-interior" src="/assets/photos/reading-room.svg" alt="library">` against 1.1.1 at
0.92 confidence, with the replacement text proposed.

### 9.1 The six fixed the next morning — BUILT, 2026-08-21

The run was cut short by a dropped connection, and what that exposed was **not** the judging. It
was that a run which stops is invisible, and that no screen could say so.

| | What was wrong | What was done |
|---|---|---|
| **A** | **A failed judging run stranded its audit for ever.** The workflow returns at its `phase_failed` branch *before* `verify_writes`, which is where the judge's accounting lives — so a crashed engine left the elements it never answered recorded nowhere, no report published, and the audit reading *Checking what was found* permanently. | `aipass.close_unfinished_ai_pass`, called from `fail_run_core` **one line below the journey's identical closure**, which had sat on that path since G6a without the judge's ever being added beside it. It files every unanswered element as `uncertain`, publishes the merged report and completes the audit — landing the crash path in the state the normal path already produces. A no-op for every other phase, and that is asserted rather than assumed. |
| **B** | **A question from a headless run could be seen and never answered.** The sidebar badge counted the project's pending clarifications server-side; the page narrowed the tenant's against the visible backlog. A run on a hidden carrier work item — accessibility judging, code indexing, the gap report — is deliberately absent from that backlog, so its question was counted and then filtered away. Badge 1, page none, run waiting for ever. | The page asks the API for the project's questions — a filter the endpoint already had — instead of narrowing them in the browser, and reads the work item's name off the clarification's own `work_item_title` rather than looking it up in a list a carrier is never in. Hiding plumbing from a board is right; hiding a question that blocks a run is not. |
| **C** | **Two tests asserted the pre-#9 world** — that a project folder with nothing installed is refused — and failed for anyone who had run `npm install` in `runner/`, which committing the lockfile made standard. | Rewritten to assert what #9 actually built: a bare folder falls back to the companion's toolchain, and the report can say `(companion)`. The refusal they were protecting is real, but now only happens when **both** places are empty, so it has a test of its own that runs the real script from a copy stranded where nothing resolves above it. |
| **D** | **A running audit had nothing to watch.** S-38 line 598 designs a full panel; what existed was a status word in a 320px rail. The live run spent forty minutes on *Checking what was found* with no way to see that the judge was at 81 of 144, or that it had stopped. | The panel's **three tiles**, built: pass, pages visited and would-not-open while capturing; **elements judged of dispatched** once the AI half starts. Every number derived from rows already being written — `baseline.audit_progress`, two grouped queries, asked only for audits still in flight. The live console is **not** built; see 9.2. |
| **E** | **`.grid--detail` never collapsed.** Fixed at `minmax(0,1fr) 320px` for every width, while its sibling `.grid--console` collapses at 900px on the line below it. *Past audits* — the only place an audit's progress appeared — was squeezed beside 79 page rows and pushed below the fold. Two people looked for it and concluded it did not exist. | One media query at 900px, matching the rule directly below it. |
| **F** | The companion printed `10 page(s) ? 1 pass(es)` — characters the Windows console cannot encode once output is redirected to a file. | The six affected lines across four companion files write ASCII. Only the companion's own printed output changed; nothing that travels to the platform did. |

### 9.2 Recorded, not built — the live audit console

**What is missing.** S-38 designs a scrolling console beneath the tiles, one line per page as it is
visited: `14:02:12 / · 41 elements · scanner ran`, `14:05:44 /admin/reports · could not open (timed
out after 30s)`. The tiles now say *how far*; the console says *what happened, page by page*, which
is what turns "3 of 10 visited" into "and the fourth one timed out".

**Why it is not built alongside the tiles.** The tiles cost two grouped queries over rows the
platform already stores. The console has nothing to read: the companion posts one screen per call
and says nothing between them, and a page that **failed** to open is only recorded when the pass
ends. There is no progress channel, and per-page lines would mean building one — an append-only
event stream per audit, written by the companion as it goes and read by the panel on the 5-second
poll it already runs.

**What it would take**, so this is a decision rather than a hope:

- an event row per audit step — route, element count, scanner ran or did not, opened or would not
  open with the reason, timestamp — written on the same call that posts a screen, and on the
  failure the companion currently only counts;
- a read endpoint returning the tail, on the poll the running panel already makes;
- the same bounding every other list here has — a cap on rows kept, stated on screen when it bites,
  because a 200-page audit is 200 lines and a silent truncation reads as "that is all that
  happened".

**Until then the tiles are the whole story on screen**, and they are honest about being counts
rather than a narrative: *would not open* is a number, and which page it was appears on the audit's
row under Past audits when it closes.

### 9.3 Asking the machine again about what it never judged — BUILT, 2026-08-21

**The situation.** A judging run that dies part-way leaves every element it never reached filed as
`uncertain — not judged`. That is the design working: nothing dispatched may vanish. But those
elements then sit on a person for a reason that has nothing to do with them — not because a check
looked and could not decide, which is what the review queue is for, but because nothing looked at
all.

⚠️ **This was surfaced with a worked example — "81 of 144, so 63 handed to a person" — and that
example was wrong**; see 9.4. Those 144 request slots were 81 distinct elements and the judge had
answered every one. The situation this closes is real and will happen the first time a judging run
genuinely dies part-way; it simply had not happened yet when this was built.

**Most of it already existed**, and that was the surprise when this was looked at properly:

- **`dispatch._cached` never serves an `uncertain` back to a dispatch.** Its own docstring says
  why: an `uncertain` means no answer was reached, and serving it back would turn a *transient*
  inability into a permanent one.
- **`ingest.requests_for` reads the stored candidate bundles**, keyed on the audit's own id. The
  elements, their markup, their styles and their screenshot crops are all still in the database.
  **A re-judge needs no browser, no companion and no page visited again.**

So what was missing was **a caller** — the same shape as **G6c**, where `start_journey_check` had
no caller anywhere in the platform.

#### What was built

| | |
|---|---|
| **The marker** | `judge._remember_unanswered` writes the content hashes a run never reported on onto `Run.outputs`, at the one moment they are still distinguishable from an answered `uncertain`. A JSON field the run already owns: no schema change and no second place to keep in step. |
| **The reader** | `aipass.unanswered_for_capture` — the elements nothing ever looked at, from two sources: verdicts filed with **no run against them** (`_file_unjudged`, when the pass could not start at all) and the hashes the judge run recorded. Both intersected with what this capture actually holds, because a judgment row is project-wide and one audit must not drag in another's leftovers. |
| **The pass** | `aipass.rejudge_capture` — `start_ai_pass` with a new `only_hashes` filter, then the audit back to `judging`. It re-uses the ordinary machinery entirely: same carrier work item, same dispatch, same closing step, same report re-published, same audit completed. Whatever it does not answer this time is filed again. |
| **The way in** | `POST /api/projects/<p>/a11y-audits/<audit>/rejudge/` and a **Check the rest** button on the audit's own row under Past audits, appearing only on a **closed** audit that has some, and saying how many. |

#### The three decisions the team took, and what each cost

1. **Where it starts** — the audit's own row, because that is the thing that was incomplete. The
   count comes from what each pass recorded about itself (`baseline.unanswered_counts`, one extra
   query for the whole list); the *authoritative* set is recomputed at re-judge time. A test
   asserts the two agree, because a screen that offers to check twelve things and then checks
   nine is a screen nobody trusts again.
2. **What it does to the audit** — back to `judging`, so the running panel and the row say what
   is happening in the words they already use, and it reaches `complete` again through the
   ordinary closing step. Not a second audit: re-running one would re-visit every page to re-ask
   about a handful of elements, and would then compare a fresh capture against a report drawn
   from the old one.
3. **What it must never do** — re-ask about an `uncertain` a check actually *reached*. That is a
   real verdict and it belongs to the person in the review queue; handing it back would quietly
   recycle the queue's own contents through the machine. This was the one piece of real design,
   and it is why the marker above exists.

⚠️ **The marker rests on an invariant, so the invariant is pinned by a test.** A verdict with a
**null run** means the platform filed it because nothing could be asked; only `_file_unjudged`
writes one. There are exactly three `record_verdict` call sites, and a test asserts that the
agent's own tool (`judge.record_finding`) always stamps its run — because the day one of them
stops, elements a check genuinely answered would start being fed back to the machine.

⚠️ **Two real bugs were caught by these tests before they shipped**, both in the first draft of
`rejudge_capture`: `trigger` was passed a string where the dispatch expects the trigger
*callable*, and the re-judge had no way for a test to inject one — which would have meant a test
starting a real workflow on the shared Temporal server.

### 9.4 The first COMPLETE run — 21 August

Meridian again, and this time end to end: **10 of 10 pages visited, 0 that would not open, every
distinct element judged, the report published, the audit `complete`.** The Temporal history shows
all six activities in order, `verify_writes` running for 22 seconds and passing, and the workflow
closing `auto_approved: true`.

The one failing finding is the one that justifies the whole build — a defect no scanner can reach:

> `<img src="/assets/photos/reading-room.svg" alt="library">` against **1.1.1**, confidence
> **0.95**, evidence citing the screenshot: the image is an illustration of a reading room, and
> *library* describes neither what it shows nor why it is there.

#### The correction: "81 of 144" was never a truncation

**This corrects what §9 said the morning before.** The 20 August run was read as having died at
81 of 144 with **63 elements lost**, and the accounting was described as having been broken. It
was not. The judging had finished.

An audit dispatches one request per (element, checker) **slot**. Ten pages of Meridian produce
**144 slots but only 81 distinct elements**: the site header, the footer and the nav are the same
markup on every page, they hash identically, and one verdict answers all ten. The most repeated
one is `<span class="brand-name">Meridian Library</span>`, on all ten pages.

```
element slots: 144   ·   distinct elements: 81
```

`verify_judgment_completeness` compares hashes, computed **0 missing**, and was right. What
actually went wrong on 20 August was only that the workflow never closed the audit — item **A**
in 9.1 — and that fix is what let this run finish properly. The accounting was never broken.

#### And the run exposed a defect in the tile built that same morning

**The tile read `81 of 144` on a complete audit.** The numerator counted distinct verdicts, the
denominator counted request slots — so a finished, correct run told the person who started it
that a third of the checking had not happened. A screen stating something about a client's
application that is not true, in the feature built to refuse exactly that.

**Fixed by making both numbers the same unit.** `start_ai_pass` now records `distinct` — how many
distinct elements the requests are about — beside `dispatched`, and the tile counts against that.
An audit dispatched before this was recorded derives the number from the run's own batches rather
than showing the old misleading one. Two tests: a capture with repeated chrome must not report
itself incomplete, and the pre-fix shape must still produce a true number.

#### The panel no longer disappears when the run ends — BUILT

The team's other observation from the same run, and it is the same principle one step later: the
panel they had been watching **vanished at the moment the answer arrived**. A person who starts an
audit and watches it work must not have the result disappear on completion.

It now stays and changes what it says. Three tiles throughout:

| Stage | The three tiles |
|---|---|
| Visiting pages | Pass *k of m* · Pages visited · Would not open |
| Checking what was found | **Elements judged** *n of m distinct* · Pages visited · Would not open |
| Complete | **Pages reported** *n of m asked* · **Problems open** *n, c critical · h high* · **Waiting on a person** *n* |
| Could not run | the machine's own reason, in its own words |

Plus the never-opened banner when pages were asked for and never reported, and a way through to
the review queue when anything is waiting.

⚠️ **One thing about that panel is scoped wider than it looks, and it is labelled so.** *Problems
open* is **this project's** current standing, not this audit's tally. A finding carries no audit
key — `A11yFinding.last_seen_run` is a foreign key to a real `Run`, and a baseline audit
deliberately manufactures none (QA-17), so for every brownfield audit that column is NULL. The
first draft counted on it and would have reported **0 problems on an audit that found three**. It
is also the right scope: the **Accessibility baseline** this panel points at is itself
project-scoped, so that an audit covering part of an application never drops what is already known
about the rest. The tile's sub-line says *in this project* rather than letting the number imply a
per-run count, and a test pins the NULL column so the shortcut cannot be taken again.


---

### 9.5 An audit whose machine went away — 21 August (BUILT)

The scope was re-cut to twelve pages chosen to make the AI hesitate, the audit was started, and
the **operator's computer restarted while it was running**. Page 1 was in; nothing else ever
came. The audit sat at:

```
audit 1c471111   status = capturing
claimed 04:20:06   ·   last write 04:20:57   ·   screens in: 1 of 12
```

and it would have sat there for ever. The screen went on saying **Visiting pages** about a
machine that no longer existed — this capability's own worst failure, in the feature built to
refuse it. It is the same defect as 9.1 item **A**, one state further along: that fix closed the
audit when the *judging* run died, and nobody checked the *capture* end.

#### Why nothing could end it

The platform already recovers a dead companion's work — the claim lease from Bugs S.No 110/111.
It offers back two audit states: `pending`, and `claimed` whose stamp has gone stale. An audit
moves to **`capturing`** the instant its first screen lands, and past that line there was no
lease, no timeout and no cancel:

* the restarted companion could not pick it back up — its claim poll cannot see `capturing`;
* nothing renewed an audit's lease either. `claimed_at` was stamped once and never touched
  again, so **an audit's liveness was not actually being tracked at all**;
* and starting another audit is not refused, so the abandoned one just becomes a row under Past
  audits that reads "Visiting pages" permanently.

#### The fix — three parts

**A. The heartbeat renews the audit's lease.** `_renew_claims_for` already does this for runs;
it now also renews the audit each companion is *capturing*, capped off `created_at` rather than
a `first_claimed_at` column — an audit is claimed within a second of being created, so its own
age is the same measurement without a migration. This part had to come first: without it, part B
would declare a slow-but-healthy capture dead, which is exactly the S.No 111 mid-flight re-claim
being reintroduced.

**B. A stale capture is closed as failed, with the reason.** `baseline.abandon_audit` /
`abandon_stale_audits`, swept from the companion's heartbeat and its audit claim — both already
writes, so **reading the audit list never writes to it**. Liveness is measured from *either*
signal: the heartbeat, or a screen actually arriving. Keying on the heartbeat alone would depend
on a companion mode that might not heartbeat; keying on screens alone would kill an audit stuck
on one very slow page.

Failed, **not judged and not resumed**, both deliberate. A report built from four of twelve
pages would be a document stating a position about an application most of which was never looked
at. Re-visiting routes already captured under this key would need a resumption design that does
not exist — what happens to the bundles already stored for a route being visited twice — and a
fresh audit costs minutes. Resumption is worth its own task if captures ever get long enough for
the difference to matter.

**C. The screen tells the truth even if the machine never comes back.** A computer switched off
for good never reports in to be swept, so `stalled` is **derived on read and never written**:
an in-flight audit nothing has been heard from for the lease reads as *Audit stopped reporting*,
says how far it got, and says a new one can be started now.

⚠️ **The near-miss, and the reason `ABANDONABLE_STATUSES` is one state and not two.** The first
version swept `claimed` as well as `capturing`, and broke
`test_a_machine_that_restarts_mid_audit_picks_its_own_audit_back_up`. That test was right: a
`claimed` audit has captured **nothing**, and the existing lease hands it to the next machine
that asks, so it simply runs. Failing it would have converted a recovery that worked into a
failure somebody has to go and restart by hand. Abandonment now applies to `capturing` alone —
the one state nothing else could get an audit out of — and a test pins the distinction.

#### It closed the real one before it was ever run by hand

The plan was to close audit `1c471111` explicitly. By the time that ran, the sweep had already
done it: **04:38:36**, on the live companion's own heartbeat, `opened: 1`, the eleven unvisited
pages listed under `never_reported`, and the reason in the machine's words. The bug found on the
live run was closed by the fix for it, on the live system, unassisted.

**Verified:** 191 in `test_a11y_baseline.py`, 73 across `test_a11y_scope_rest.py` +
`test_companion_daemon.py`, 44 on the audit screen, `tsc` and `eslint` clean on the changed
files. The four pre-existing `views.py` ruff findings are unchanged and still not from this work.
