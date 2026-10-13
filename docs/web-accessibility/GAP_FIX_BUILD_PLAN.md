# Web Accessibility — Gap Fix Build Plan (POC + Phase 2)

**Branch:** `web-accessibility-build` · **Written:** 2026-08-19

---

## 0. What this document is

The 24 QA tasks are built. This plan covers the **eleven gaps found afterwards**, when the team
asked how a real user reaches the accessibility work in the greenfield and brownfield journeys.

Every gap here was found by reading the code, not the docs. Each one below says what is wrong in
plain words, why it happens underneath, exactly what will change, and how we prove it worked.

We take one task at a time: I surface it in full, the team says go, I build it, we test it, and
only then do we move on.

> **Status, 2026-08-31.** This line used to read *"nothing in here is built yet"*. **All eleven
> gaps in §3 and §4 are built**, and the document has since grown a second half nobody planned
> for: **§9, what running it turned up** — **forty so far across twenty-five sections**, all built
> bar one that is deliberately recorded and not built (§9.25.5). #19–#35 were found by people
> watching the product work rather than by reading code; #36–#41 came the other way, from the team
> asking whether we capture every element WCAG puts in scope and the answer being no; #42–#45 from
> tracking a live audit end to end and reconciling it against a second tenant’s; and **§9.25 from
> the first audit at real size — 94 pages, 2,171 elements — which is where four defects nothing
> smaller could have surfaced came out at once.** §3 is the plan as written; §9 is what reality
> added to it, and §9 is now the larger and the more useful of the two.

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
| 1 | **G1** — greenfield records what passed, not only what failed ✅ | A truthful conformance report on greenfield | S |
| 2 | **G4** — hide the "Accessibility judging" plumbing task ✅ | A clean work-items board | S |
| 3 | **G5** — make sure the Testing agent sees the screen list ✅ | Accessibility test cases actually get written | S |
| 4 | **B3** — take the address from the repository ✅ | One less thing typed by hand | S |
| 5 | **B5** — audit any number of pages, in passes ✅ | Meridian's 68 pages, and anything bigger | M |
| 6 | **G2 + G2b** — the platform learns which test cases are WCAG ✅ | You can see and filter them | M |
| 7 | **G3** — a finding says which test case found it ✅ | The review console makes sense on greenfield | M |
| 8a | **B1 + B4 + B2** — the audit screen, and the way in ✅ | Brownfield audit with no terminal at all | L |
| 8b | **The page editor** — edit one page, not the whole list ✅ | A path can be corrected without creating a second page | M |
| 9 | **G3b** — the review list stops fetching evidence nobody reads ✅ | A queue that does the work it is read for | S |
| 10 | **G6** — the keyboard journey, working on both journeys ✅ | Eight criteria nothing else can reach | M |

> **✅ here means built and tested, not proven live** — and the two are not the same thing, which
> is the whole argument of §9. **10 (the keyboard journey) is the sharpest example**: every slice
> is built and every acceptance criterion is green against a planted trap, and it **has still
> never opened a page in a real browser.** Testing Guide §10.2 is the list that tracks that
> difference; this column does not.

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
routes twice over on a real application is not something a test here can establish.

> **Still true on 21 August, after five live runs.** Every one of them was **11 or 12 pages** —
> comfortably inside a single pass. The multi-pass loop has never run against a real browser, and
> the first audit of a 68-page application is still the first time we learn it. This is item 5 in
> Testing Guide §10.2.

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
screen. It could not be checked when this was written: the running app points at the **shared**
database, where migrations 0021–0026 were unapplied.

> ✅ **Proven, 21 August.** The migrations were applied by the team and a full audit has now been
> started, watched and completed **from the screen, with no terminal**, five times over. This
> entry no longer needs its caveat.

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

A green test suite here means *"it behaves as designed"*. It does not mean *"the scanner really
returns what we think it returns"* — only a live run does that.

Where a task below can only be half-proven by tests, it says so in its own words rather than
leaving the team to assume otherwise.

> **Updated 2026-08-21.** This section used to end *"and the first one is still ahead of us"*.
> **It is behind us.** The brownfield chain has now run against Meridian Library five times —
> capture, judge, triage, ledger, defects, report, baseline, and a second pass over one capture —
> and §9 exists because of what those runs found. What is still ahead is narrower and named in
> the Testing Guide §10.2: the **greenfield** capture, the **keyboard journey**, a **review queue
> with something actually in it**, a **signed** conformance statement, and a run big enough to
> need **two capture passes**. Five live runs have not touched any of those five.

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

## 9. The live runs — 20/21 August

The first time any of this was executed against a real application, and then four more times.
Meridian Library at `http://localhost:4180`, 79 routes registered, on a brownfield project with no
Jira and no Confluence — 10 in scope on the first run, 12 on the third, 11 on the last after the
team took `/staff/shelf-audit` out to stay under the judging cap.

> **This section was appended as an afterthought and is now the larger half of the document.**
> §3 is the plan as written; §9 is what running it added: **thirty-five findings across twenty-four
> sections** (§9.1–§9.23), all built — and it has gone on growing since that was written. **§9.24
> to §9.28** carry the 25 and 31 August and 1 September findings and are also all built; **§9.29 is
> the 1 September re-reading of every fix ever made, and built nothing; §9.30 and §9.31 are what the
> team asked for in answer to it — everything that review found, cleared, and the sixth check
> back in with the registry agreeing, at 1,765 passing and zero failing.** #19–#35 were produced by a person
> watching the product work; #36–#45 by putting twelve textbook WCAG failures through the
> selection code after the team asked what we do and do not capture. **Every built one has a
> green test suite standing over it** — which is the point, and why they are written up at
> length. They are numbered #19–#64 in the Testing Guide.

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


---

### 9.6 A pass that stopped at its limit, and said nothing — 21 August (BUILT)

The twelve-page scope came to **205 element slots against a cap of 200**, so the dispatch
stopped and handed back **5 deferred**. It recorded that honestly, in the audit's own summary:

> *"Stopped at this run's limit of 200 — 5 item(s) still need judging. Run the check again to
> continue from here; nothing was skipped."*

**And nothing anywhere read it.** Grepping the whole frontend for `ai_pass` or `deferred`
returned nothing; the run report and the published baseline never mention them either. So the
audit would have closed as **complete**, shown *12 of 12 pages reported*, and never once said
that five element-slots were not checked. A quiet success, which is the worst failure this
capability has.

⚠️ **And the "Check the rest" button would not have appeared.** This was stated wrongly to the
team first and corrected against the code. `unanswered_counts` counted exactly two things —
`filed_unjudged` (no judge to ask) and the judge run's `a11y_unanswered` (given to a run that
never reported). Cap-deferred elements are in **neither**: never dispatched, never filed. The
audit's own `filed_unjudged: 0` proves it.

#### D1 — "nothing looked at this" now means what it says

`unanswered_for_capture` asks the direct question: **is there a verdict for this element at
all?** No verdict row means nothing looked, whatever the reason nothing did — no judge, a run
that dropped it, or a dispatch that stopped short. One rule instead of three categories to keep
in step, and the cap case is covered by construction rather than by remembering it exists.

An element that *was* answered stays answered, including a genuine `uncertain`: that verdict
belongs to the person in the review queue, and re-asking would quietly recycle the queue through
the machine. `unanswered_counts` — the cheap screen count — adds `deferred` to what it already
counted.

⚠️ `deferred` is counted in **slots**, the only number the summary kept, and repeated chrome is
several slots and one element. So the button can read high where the tail of a capped pass was
markup the cache can already answer. `unanswered_for_capture` recomputes in elements and is the
number that acts; the docstring says so.

#### D2 — the finished audit says why part of it was never asked about

The dispatch's own sentence now renders: a warning banner on the complete panel
(*"Not everything captured was checked"*) and a line on the audit's row under Past audits. It
sits beside — not instead of — `summary.reason`, because *why the audit failed* and *why a
successful audit is incomplete* are two different sentences.

#### D3 — and the onboarding step stopped calling a running audit a finished one

Reported by the team from the live run: the hub read **"1 audit run — open the report from
Artifacts"** while the audit was still judging. The step counted `complete` **and** `judging` as
run. But there is no report to open until the judging ends — the baseline is published when the
judge run closes, deliberately, so that it never states a position that is still changing.

`audits_run` now counts finished audits only, and a separate `running` rides beside it — the
same `{status, running}` pairing the Index code step already uses, and for the same reason: the
tick and the button switch on `status`, while the line of text has to be able to say *"and
another one is going right now"* over the top of it. Four states, each with a test: running says
so and offers no report; finished is done; finished-plus-running keeps the tick and adds the
sentence; and a failed audit leaves the step simply *ready*, which is the true thing to say.

**This is the team's point about a fix touching everything it touches**, and they were right to
make it: the audit screen had been taught to tell the truth about a running audit three times
over, and the hub two clicks away was still reading the old count.

**Verified:** 62 in `test_a11y_report.py`, 19 in `test_onboarding_rest.py`, 46 on the audit
screen, 23 on the hub, `tsc` and `eslint` clean on every changed file.


---

### 9.7 The check that never ran — 21 August ⭐ (BUILT)

The twelve-page audit finished cleanly: **12 of 12 pages, 125 of 125 elements judged, 19 real
failures, 0 never answered.** Both control pages behaved — `/loans/history` and `/staff/overview`
are built correctly and came back clean while their broken twins produced eight findings between
them, which is the evidence that the judge is judging rather than pattern-matching.

**And the review queue was still empty.** Zero `uncertain`, zero below the 0.80 threshold. So the
question became *why*, and the answer was not the model.

```
checker slots, every audit this project has ever run:
color 173   ·   semantics 47   ·   alt 22   ·   label 0
```

**`label` has never selected a single element.** Not on these pages, not on the previous ten, not
once in the life of the feature. The chain, each link verified rather than reasoned about:

1. `rules._applies_label` requires a computed accessible name — `if not name: return False`,
   deliberately: 2.5.3 compares the announced name against the visible text, and with no name
   there is nothing to compare.
2. That name is filled by the capture calling **`page.accessibility.snapshot()`**.
3. **Playwright removed that API.** `probe: page.accessibility is: undefined` — no
   `accessibility.js` in `playwright-core/lib/client`, no `accessibility` in `types.d.ts`, at the
   pinned 1.62.1.
4. `fillAccessibleNames` wrapped each element in a bare `catch {}` — written for one awkward
   element, and it swallowed a total failure just as quietly.
5. **0 of 242 stored elements carry a non-empty accessible name.**

So WCAG **2.5.3 Label in Name** — the check with most to say that only a person can settle, and
therefore the likeliest source of a review-queue item — was switched off from the day it was
written, by a dependency change, behind a silent guard. The team's instinct that an always-empty
queue was suspicious was right, and it was never about the pages.

#### The fix, in four parts

**1 · The name comes back.** `locator.ariaSnapshot({ timeout, depth: 0 })` replaces the removed
call. Measured against the real browser before writing a line of it: 106 elements in **590ms**
(~6ms each), and a selector that matches nothing throws at the timeout instead of hanging — that
matters, because `ariaSnapshot` defaults to **no timeout at all**, so one stale selector would
have stopped the audit rather than cost it a name.

The parse is anchored: `- role "name"` at the start of the first line. An unanchored search for a
quoted string reads `- paragraph: He said "hello"` as a paragraph named *hello*, and **inventing a
name is worse than having none** — a made-up name is exactly what makes the label check compare a
string against itself and always pass. Tested as JavaScript, extracted from the shipped file and
run against snapshots copied from a real browser, including that trap.

**2 · The platform checks its own input, so this cannot hide again.** `baseline._name_coverage`
counts, over the elements a capture actually produced, how many *nameable* ones (links, buttons,
form controls, headings — things that have a name by definition) came back named. None of them
named is a broken machine, not an application without names, and the audit records it and the
screen says so: *"One of the checks could not run."* Named apart from the cap banner on purpose —
it must never read as "the application has no label problems", because nothing looked for any.

Checked server-side rather than trusted from the capture, because a capture written by an older
companion cannot report a problem nobody knew to look for. Silent when there is nothing nameable
in a capture at all: that says nothing about the machine, and an accusation would be a guess.

**3 · The stopped pass counts elements, not slots.** ⚠️ **A defect D1 introduced, caught by
running the numbers against the finished audit rather than assuming.** The 21 August run deferred
**5 request slots and lost nothing** — every one was chrome already dispatched earlier in the same
run, so one verdict answered it, and all 125 distinct elements were judged. Counting the raw
`deferred` would have put a *"Check the rest — 5 elements"* button on an audit with nothing left
to check. `start_ai_pass` now records `deferred_distinct` (deferred hashes minus dispatched ones)
and that is what the button counts; an audit from before the key existed reports **none** rather
than the misleading number, the same choice the "elements judged" tile made.

**4 · And a boundary D1 got wrong, caught by an existing test.** "No verdict anywhere" is only
*asking again* once a pass has run. A capture that has never been judged also has no verdicts, and
every element would have answered the question — but what that capture needs is its **first**
pass, dispatched the ordinary way. `unanswered_for_capture` now applies the rule only when a judge
run exists for the capture. The test that caught it,
`test_asking_again_when_everything_has_been_looked_at_starts_nothing`, was right and the code was
wrong.

**Verified:** 262 across `test_a11y_baseline.py` + `test_a11y_scope_rest.py` +
`test_a11y_scan_coverage.py`, 64 in `test_a11y_report.py`, 48 on the audit screen, `tsc` and
`eslint` clean.

**Not yet proven live**, and this is the next run's job: `/account/card-services` alone should
produce seven label candidates — buttons whose spoken name shares no word with the visible one
("Renew" → *"Extend the loan period on every item"*) — and that is where the first genuine
`uncertain` should appear.

### 9.8 Three things the team found reading the documents — 21 August (BUILT)

The 21 August audit finished cleanly and produced its two artifacts. Reading them raised three
observations, all of them about the documents rather than the checking. Mock-ups of the first two
were drawn on the product's own design system, confirmed by the team, and then built.

#### 1 · The reports printed part of the finding

A markdown table cell cannot hold a line break, so every cell was bounded — 300 characters in the
per-run report, **160** in the baseline backlog. Measured on that run: 9 of 26 evidence strings
exceeded the first, 13 of 26 fixes exceeded the second. The chart finding lost the sentence that
made it a failure (*"Those figures are unavailable to screen-reader users"*), and the backlog's
copy of its fix stopped mid-sentence **inside the quoted alt text it was telling somebody to
write**.

Raising the limit moves the cut; it does not remove it. **A table is the wrong container for a
paragraph**, so the paragraphs left it:

* rows are **numbered**, with one counter across the whole document — three sections numbering
  from 1 would give one report three number 1s, and "have a look at 4" would be a question;
* *What was found* becomes a gist (`report._gist`) — a whole sentence where there is one to end
  on, a whole word otherwise, and `…` only when it genuinely stopped early;
* *Suggested fix* leaves the table entirely, and both halves are printed under **Details**
  beneath their own criterion's table (`report._details`, `baseline_report._backlog_details`).

`_cell` stays, for the things a cell can hold — a route, a selector, an enumeration. `_prose`
flattens line structure and nothing else. The blockquote reasons in the D-A11Y-3 notices were
bounded at 400 for the same borrowed reason and are no longer: a blockquote line is not a cell.

#### 2 · "Screenshot shows…" pointed at nothing — **S-39**

All 26 findings say it. The pictures were being kept, and `a11y-review/<id>/screenshot` already
served any finding on the project. What did not exist was anywhere to *see* one: the only screen
that drew a capture was the review console, which by definition holds `needs_review` items only,
and all 26 of these were confirmed failures.

Almost everything needed already existed. **The one genuinely new thing is opening a finding
without claiming it** — `GET a11y-review/<id>` takes the review claim as a side effect, which is
right for a reviewer working a queue and wrong for anyone following a link out of a report: a
failure nobody is reviewing must not acquire a reviewer's name because somebody looked at it.

* `review.read_finding` = `open_item(take_lock=False)` plus the audit that took the picture.
* `GET projects/<id>/a11y-finding/<finding_id>` — same gating as the console's read.
* `review._captured_by` resolves the audit from the capture's own `run_key`, **not** from the
  finding: a finding outlives every pass that saw it, and the question a reader looking at a
  picture is asking is "which audit took this one?". `null` on greenfield, where the key names a
  `Run` — the same rule `_provenance` follows.
* S-39 (`A11yFinding.tsx`) reuses the console's `Capture` component, which moved to its own file
  so two screens cannot drift about where the element box goes.
* Both documents link to it. ⚠️ **The per-run report needed one extra step**: a baseline audit
  manufactures no `Run`, so `open_findings_for_run` matches nothing and that report renders from
  the *merge*, whose rows have no id. `findings.ids_by_fingerprint` maps fingerprint → id and
  `finding_link` resolves through it. Without that the link would have appeared on the baseline
  and silently not on the report — which is the document the team was reading.

#### 3 · The statement could not say which run produced it

`conformance.evidence_basis` names the most recent **completed** audit, when it finished, and how
many pages it opened; it counts the earlier ones rather than naming them, because the findings
ledger is cumulative and "this is what was checked" would be untrue the moment a project has had
two. A `failed` audit is excluded — it published nothing, so listing it would credit the statement
with coverage it never had.

It is rendered **inside** `draft_body`, which is the point: the section is covered by
`signed_body_hash`, so the person signing signs the claim about provenance too. A label beside the
document would not be signed, and would go on looking right after the wording was replaced. The
same data is also on `state()` for the screen, because the wording is the reviewer's to edit and
they may cut the section.

**Verified:** 45 in `test_a11y_conformance.py`, 23 in `test_a11y_review_rest.py`, 32 in
`test_a11y_report_fields.py`, 24 in `test_a11y_baseline_report.py`, plus the report, findings,
defects, gate and baseline suites unchanged and green; 364 frontend tests including 9 new on S-39
and 3 on the statement's provenance; `tsc` and `eslint` clean.

**Proven against the live data, read-only**: rendering the 21 August audit's baseline and report
from the shared database now prints every fix in full — the chart's alt text ends where the judge
ended it — and puts 26 capture links on the report, each resolving to the same finding id the
baseline links to.

### 9.9 A running audit described as stopped — 21 August (BUILT)

Found by the team watching the Past-audits row while the judge was working through the fresh
run. The row read:

> Stopped at this run's limit of 200 — 12 item(s) still need judging.

The audit was at that moment `judging`, 60 of 126 elements in. Three defects in one sentence,
all three introduced by earlier work in this section.

**1 · It is written when the pass STARTS.** `dispatch` records its reason before the judge is
asked anything, so `summary.ai_pass.reason` exists for the whole pass — in the past tense. The
row rendered it with no status check. The API already refuses to compute the "check the rest"
count for an in-flight audit for exactly this reason (`views.a11y_audits`), and `LatestAudit`
already guards on `!running`. The row was the one place that skipped it — and it is the same
running-thing-described-as-finished bug §9.6 fixed on the onboarding hub and did not carry
across.

**2 · The sentence counted request slots; the button counts elements.** The pass had
`deferred 12, deferred_distinct 6`. §9.6 changed `unanswered_counts` to use the distinct number
*precisely because the raw one misleads*, wrote up why, and left `OVER_CAP` formatting the raw
one. So one card was about to say **12** beside a button offering **6**.

**3 · With nothing genuinely left, it still claimed work.** All-repeat remainders give
`deferred_distinct == 0`; the button correctly disappeared and the sentence stayed.

#### The fix

`dispatch.distinct_remainder(dispatched, deferred)` is now **the one definition** of that
number, called by the dispatcher's own sentence and by `aipass`'s stored count — they were two
expressions of one idea and one of them was wrong. The sentence is not recorded at all when the
remainder is zero. `result.complete` is unchanged: requests really were deferred and a re-run
really does continue from here; what changed is that nobody is told to act on it. `OVER_CAP` is
reworded to describe the dispatcher rather than the audit.

**The screen composes its own sentence from the count, and never renders the stored prose for
this case** (`A11yAudit.unaskedNote`). That is deliberate and is what makes the fix reach the
audit that was already running: its summary has `12` baked into the text, and fixing only the
writer would have left that row wrong for ever. The judge-unavailable reasons are still shown
as written — they are not derivable from a count — and are told apart by `filed_unjudged`
rather than by matching on wording, which would break the moment somebody improved a sentence.

**A wrong call on this page, twice, worth recording.** During the run I said the cap would be
hit, then "corrected" myself to say it had not been, reading `dispatched: 126` as the whole
story. 126 is the de-duplicated count *inside* the 200 that were taken; 212 went in and 12 were
deferred. The cap was hit. Both statements were made from a progress number instead of from
`_split_at_cap`, which is four lines long.

**Verified:** 29 in `test_a11y_dispatch.py` (3 new: elements-not-slots, the silent all-repeat
case, and one definition of the remainder), 291 across dispatch + report + baseline, 53 on the
audit screen (5 new, including a `judging` row that must stay silent), `tsc` and `eslint` clean.

### 9.10 The second pass, described in the first pass's words — 21 August (BUILT)

The last untested path in this section: pressing **Check the rest** on the finished 21 August
audit. It offered 6 elements, all on `/staff/shelf-audit` — the tail of the capped pass, which
is where the four broken `#shelf-*` switches live.

**The engine half worked, first time.** 6 asked, 6 answered, four new 1.3.1 failures at 0.97
confidence, findings 21 → 25, the report re-published in place (25 failures, 0 needing review,
**and the incompleteness blockquote correctly gone**), the baseline at v2 — 3 criteria across 7
pages in 25 items. The `Check the rest` path does what it says.

**The screen then described that pass entirely in the previous one's words.** Four claims on one
screen, all wrong:

> Not everything captured was checked · This run reached its limit before every element was
> checked — 6 elements were left for a second pass.
>
> 6 elements were never looked at … They are waiting on a person in the review queue.
>
> \[Check the rest]

…while the tile beside them read **0 waiting on a person**, and the panel above read
**0 of 126** for a pass that went back for six.

#### One root cause

`rejudge_capture` merged **four** keys onto the pass that had stopped and inherited the rest:

```
this pass:  dispatched 6 · judge_run_id <new> · filed_unjudged 0 · rejudged true
inherited:  distinct 126 · deferred 12 · deferred_distinct 6
            reason "Stopped at this run's limit of 200 — 12 item(s)…"
```

`_distinct_dispatched` prefers `distinct` → the running tile's denominator was the first pass's
(**0 of 126**). `unanswered_counts` sums `deferred_distinct` → the badge, the sentence and the
button all offered 6 elements the pass had just answered. `unaskedNote` reads
`deferred_distinct` → a pass that hit no limit said it had stopped at one.

The first pass is written with `summary["ai_pass"] = {…result…}` — a **replacement**. The second
pass was the only place that merged. It now replaces too, keeping only the audit-level facts
around it (`asked`, `opened`, `names`, `never_reported`), which are facts about the **capture**
that a second judging pass does not touch. It adds `rejudged_at` and `rejudged_asked`.

#### The button that could not be cleared by using it

Separately, and worse. The badge is a cheap sum of what each pass recorded about itself;
`unanswered_for_capture` is the authoritative recount from the capture. The two can legitimately
disagree — an element may since have been answered by another run, or have dropped out of the
capture — and `unanswered_counts`' own docstring says so. That disagreement was **permanent**:
the button offered work that did not exist, and pressing it returned early with
`started: False` **without writing anything**, because only the started path touched the
summary. So it offered the same work again, for ever.

`_mark_nothing_left` now records the recount — zeroing `filed_unjudged` and `deferred_distinct`,
clearing the sentence that explained them, and setting `nothing_left`, which `unanswered_counts`
honours outright (the third input, the judging run's own list of what it never reported, is a
true record of that run and is not rewritten; the flag is what says it has since been answered).
This is also what repairs the audit already in that state: pressing the button fixes it.

#### The review queue it never checked

> 6 elements were never looked at … **They are waiting on a person in the review queue.**

Hard-coded copy, checking nothing. An element nothing ever looked at has no finding and
therefore no queue entry — that is exactly what distinguishes it from an `uncertain`, which a
check reached and could not decide. The sentence sent a reader to an empty queue to look for
work that was only ever behind that button. Reworded to say nobody is waiting on them and that
asking again is the only thing that answers them. **Not a symptom of the above:** it would
mislead just as badly on an audit whose counts were perfectly correct.

#### Saying that a second pass is a second pass

`rejudged` has been written to the summary since §9.3 and **no screen read it**. So a completed
audit appeared to vanish and be replaced by a running one, and the panel said *Audit running ·
Pages visited 12 of 12* for a pass that opens no browser at all. The panel is now "Checking the
rest of this audit", the badge is "Checking the rest", the two capture tiles are relabelled to
say they describe the capture, and a line states plainly that no page is visited. The finished
title and the Past-audits row carry the recheck time — `created_at` still identifies the audit,
`rejudged_at` says when the numbers under it last changed. `updated_at` is now sent on each
audit row; it was not exposed at all.

#### Decided, not fixed

**The newest audit is on screen twice** — as the panel and as the first Past-audits row. The
comment on `latest` claimed Past audits held "every older audit"; the code passed the whole
list. **Team decision, 21 August: keep the row, fix the comment.** Dropping it would take
**Check the rest** — which lives on that row — off the only audit anyone presses it on, and a
history that stops before today is the worse screen.

**Every one of the 25 findings is `critical`, none `high`** — and on 21 August this was written
up here as a judge-calibration question. **That was wrong, and the doc recon of the same day
caught it.** The judge does not set severity at all. `findings.SEVERITY_BY_LEVEL` derives it from
the criterion's WCAG level — **A → critical, AA → high, AAA → medium** — and every criterion in
that run (1.1.1, 1.3.1, 2.5.3) is Level A. All-critical was not a judgement anybody made; it was
the documented rule applied correctly. Nothing to calibrate, and nothing to fix.

The lesson is the one this section keeps re-learning: a number that looks like an opinion is
worth tracing to the line that produces it before it is called an opinion.

**Verified:** 2 new backend tests in `test_a11y_report.py` (a second pass inherits nothing; a
re-judge that finds nothing left clears the button), **264 across report + baseline**, 5 new on
the audit screen for 58 total and **114 across the a11y frontend suite**, `tsc`, `eslint` and
`ruff` clean.

### 9.11 The baseline did not say when a check was incomplete — 21 August (BUILT)

Surfaced during the §9.10 investigation and left open until the team called it. The per-run
**report** has stated an incomplete check since D-A11Y-3:

> **This check is incomplete.** 6 element(s) were selected for an AI check and no verdict was
> recorded for them, so nothing here says whether they are accessible.

The **baseline** said nothing. It opened *"2 criteria breached across 6 pages"* over a check that
had never looked at part of what it captured, and no line anywhere in the document mentioned it.

**The asymmetry is the dangerous way round.** The report is a working artefact for whoever ran
the pass. The baseline is the document a client is shown, the one the Movement section compares
against, and the one a **conformance statement is built on**. Of the two, it is the one that must
never read cleaner than the evidence behind it.

#### What it says now

Two blockquotes in **What has been looked at**, beside the "page could not be opened" warning
that was already there — coverage before findings, so a reader knows how much of the application
this standing is about before reading it.

> **This check is incomplete.** N element(s) on the pages that were opened were captured and
> never checked, so nothing in this document says whether they are accessible — they are not
> counted as passing and not counted as failing. Ask again from the audit screen to carry on
> from where it stopped.

> **One of the checks could not run at all.** {the check's own reason} Nothing here says
> anything about that check, so its silence is not a clean result.

The second is a different failure from the first and worse: the name check needs the browser to
answer what each element is called, and when that breaks it silently selects nothing — every
element still arrives, the other checks run perfectly, and that one reports a clean-looking blank.

*Corrected 2026-09-17: this block was drafted as "one of the **four** checks" and "the fourth".
There are six checks, and what shipped says neither — `backend/apps/a11y/baseline_report.py:278`
and the audit screen at `A11yAudit.tsx:1157` both say "One of the checks could not run", with no
number, which is what stops the sentence going stale each time a checker is added. The quote above
now matches the shipped string.*
The audit screen has said this since §9.7. The document had not.

#### One definition, deliberately

The count is `baseline.unanswered_counts` — **the same function the "check the rest" button
reads**. Not a second count computed from the same data: §9.10 was spent on a screen saying six
elements were outstanding while the code that would ask about them said none were, and a
*document* disagreeing with a *screen* about how much of an application was checked would be
that failure in public and in writing. It therefore also honours `nothing_left`, so a re-judge
that finishes the job clears the warning from the document exactly as it clears the button.

#### The case that matters most

**A baseline with no findings at all still carries the warning.** That branch opens *"No
accessibility problems are open for this application"* — which is precisely when "part of this
was never checked" has to be on the page. Pinned by its own test, because it is the one a future
refactor would most easily drop.

**Known and not built:** `publish_baseline(audit=None)` states nothing, because with no audit in
hand there is no honest per-pass coverage to report. Every path the team uses passes the audit.

**Verified:** 6 new tests in `test_a11y_baseline_report.py` for 64 total; rendered against the
live WCAG-Audit project in all three states (complete, six unchecked, a check that never ran)
before any test was written; `ruff` clean.

### 9.12 A criterion checked on eleven pages, reported on one — 21 August ⭐ (BUILT)

Found by a recon pass over the **live** conformance statement, not by reading code. Two rows of
the same document, from the same audit:

| Criterion | What it said |
|---|---|
| **1.1.1** | 14 open failures; failed on 5 of 11 pages checked; checked on 1 page with nothing wrong; **5 pages had nothing for this rule to apply to** |
| **2.5.3** | 7 open failures; **failed on 1 of 1 pages checked** |

1.1.1 accounts for all eleven pages. **2.5.3 accounts for one and drops ten in silence.** The
audit visited eleven and the Label-in-Name check ran over every one of them.

#### Why

Coverage — the record of *what was looked at*, as opposed to *what was wrong* — is written by
each engine separately. The rule scanner reads all four of axe's channels **including
`inapplicable`**, so an axe-owned criterion gets a row for every page whether anything applied or
not (`coverage.from_scan`). The AI half builds its coverage from the elements it **judged**
(`findings.record_run_findings`), so a page where a check selected nothing wrote nothing.

For 1.1.1, 1.3.1, 1.4.1 and 4.1.2 that is invisible: axe covers those criteria too and fills the
per-page account in. **2.5.3 is the only criterion in the registry that is AI-owned with no
scanner counterpart** (`ownership.json`), so it is the only one where the silence reaches the
document.

And the silence is describing the *strongest positive result there is*. `_applies_label` skips a
control when its accessible name already contains its visible text, because at that point 2.5.3
is **met as a matter of fact** and there is nothing left to judge. Ten pages of correctly-labelled
controls produced ten pages of nothing.

#### The direction that matters

Meridian fails 2.5.3, so its statement made a *failure* claim from thin evidence — bad, but the
safe direction. **Invert it.** An application with **no** Label-in-Name problems produces no
coverage at all, and the statement prints **not evaluated** — a criterion the platform checked on
every single page, reported to a client as one nobody looked at, in a document somebody signs.
That is this capability's founding rule broken by the capability itself.

#### The fix

`findings._fill_in_scope_gaps`: after the judged rows are turned into observations, every
AI-owned criterion that a page raised no question about is recorded as `not_applicable` with
*"no element on this page was in scope for this check"* — deliberately the same outcome and the
same meaning as axe's `inapplicable`, because the two halves of one report must not use one word
for two things.

**Two guards, and both are the point:**

- **`report.routes` only — the pages that OPENED.** `scanner.rule_findings_for` keeps an
  unreachable route out of that list on purpose. A page the browser never reached must never
  appear as one a check ran over.
- **A page with anything unjudged is skipped entirely.** If a pass stopped at its limit part way
  through a page, the elements it never reached might have raised exactly the question being
  filled in. "We do not know" is the true answer, and silence is how this codebase says it.

Existing answers always win: `coverage.record` ranks `not_applicable` last, and the fill-in skips
any criterion already answered.

#### Verified against the real capture before a test was written

Re-computed from the stored 21 August capture, without writing anything:

| Criterion | Pages accounted for, before → after |
|---|---|
| 1.1.1 | 6 → **11** |
| 1.3.1 | 11 → 11 |
| 1.4.1 | 11 → 11 |
| **2.5.3** | **1 → 11** |
| 4.1.2 | 11 → 11 |

1.1.1 moving 6 → 11 is the same defect a second time, hidden: the AI half only ever covered six
of those pages and axe was quietly making up the difference.

⚠️ **This changes the NEXT audit, not the stored one.** Coverage rows are written when a run is
recorded, so the 21 August statement keeps saying "1 of 1" until another audit runs. Said here
because the reverse mistake — telling the team a fix had landed and letting them open a document
rendered before it — cost a round trip on 21 August (§9.8).

**Not built, by team decision:** the fuller variant, which would tell the two skip reasons apart
— *no visible text* (genuinely inapplicable) versus *name already contains the label* (the
criterion **met**) — and record the second as a pass. That would turn ten silent pages into ten
positive results rather than ten neutral ones. It touches the selection path; the surgical fix
above does not.

**Verified:** 4 new tests in `test_a11y_conformance.py` for 49 total — the page with nothing to
ask about, the page that never opened, the page left part-checked, and the real answer that must
not be spoken over.

### 9.13 Two housekeeping items from the same recon — 21 August

**Cleared:** `_mark_nothing_left` zeroed the counts the screens read but left `distinct` and
`dispatched` behind from the previous pass. **No screen could reach them** — they are only read
for an audit *in flight*, and that function only runs on one that has *finished*. Cleared anyway:
one pass's numbers sitting inside another pass's record is the exact shape of §9.10, and that one
was unreachable too, right up until it was on screen saying "0 of 126".

**Left alone, deliberately, and recorded so nobody re-finds them as bugs:**

- **`publish_baseline(audit=None)` states no incompleteness.** With no audit in hand there is no
  honest per-pass coverage to report. Every path a person can reach passes the audit; the other
  is not called by anything. Building a warning for an unreachable case adds code with no reader.
- **`A11yRoute.Source.ONBOARDING` is defined and has never been written by anything.** It is the
  label a page would carry if onboarding had discovered it — a slot held open for **OP-06**, not
  a feature that exists and fails. Removing it would only mean putting it back.

### 9.14 Elements WCAG puts in scope that we never looked at — 24 August ⭐ (BUILT)

**How it was found.** The team asked, before committing to more accuracy work: *are we capturing
and checking everything WCAG says we should?* Twelve textbook failures were run through the
platform's own selection function. **Eleven were handed to no check at all.** Several of those
are the rule scanner's job and correctly excluded; after allowing for that, roughly eight were
reported by nobody.

**The one that had already happened on a real page.** `/loans/current` shows borrowed books in a
table and tints each **row** to say overdue / due soon / on loan, with a colour key underneath
and the status written nowhere else — a plain 1.4.1 failure. The 21 August audit captured eleven
elements on that page: a heading, two paragraphs, six footer pieces, a header span. Not the
table, not a tinted row, not the key.

The colour check then looked at nine of those and correctly said colour was carrying nothing.
So the audit reported **no colour problems**, and the conformance statement recorded the page as
one where 1.4.1 **had been checked**.

**Two things combined, and neither is wrong on its own.** The capture offers table *cells* but
not table *rows*. The tint sits on the row. A cell inherits it rather than painting it, so the
colour rule correctly declines the cells — while the row that owns the colour was never offered.
The colour falls straight down the gap between the two, and nothing reports a gap.

**Fixed — the capture now offers the containers:** `table`, `tr`, `ul`, `ol`, `fieldset`, `form`,
`canvas`, `iframe`. The tinted row is claimed by the colour rule the moment it arrives; that rule
never needed changing and is unchanged.

**Most of the rest are not claimed by any rule yet, and that is deliberate.** An element offered
and declined is **counted**, and `rules.explain()` can name the rule that declined it. An element
never offered is a silence nothing can measure. This converts the second into the first, and it
is the groundwork whichever way §9.16 is decided.

⚠️ **Watch the judgement count on the next audit.** Zebra-striped tables now produce a colour
question per tinted row, and the dispatch cap is 200 per run. If it bites, the fix is to treat a
repeated identical row tint as one question — not to un-offer the row.

**Verified:** 2 new tests in `test_a11y_checkers.py` (the tinted row is a colour question; the
cells inside it are left to the row) and 2 in `test_a11y_baseline.py` reading the capture script
itself — one asserting the containers are offered, one asserting the list never quietly shrinks.
The pairing failed silently precisely because each half was fine alone, so both halves are pinned.

### 9.15 A submit button's label could never be read — 24 August (BUILT)

**What was wrong.** The 2.5.3 check compares a control's **visible text** against what a screen
reader announces. It read visible text as the element's inner text. **An `<input>` has no inner
text — not usually none, none, ever.** A submit button's face is its `value` attribute.

So the rule found no visible label, concluded from that silence that the criterion did not
apply, and moved on. Every submit and reset button in every form of every client application was
permanently out of scope for Label in Name, and nothing anywhere said so.
`<input type="submit" value="Search">` announced as "Go" is a textbook failure and could not be
reported.

**Fixed** in the selection rule: for `type` of `submit`, `reset` or `button` — the three HTML
renders as the button's face — `value` is read as the visible label.

**Named types rather than every `<input>`, deliberately.** On a text field `value` holds what the
**user typed**. Reading that as a label would compare somebody's own name against the field's
accessible name and report the difference as a defect — a finding raised against a real person's
data, on every filled-in form. There is a test pinning that it does not.

**A submit button with no `value` stays out of scope**, also deliberately: the browser draws its
own word there, in its own language, and it is not in the markup to compare anything against.

**Not fixed, and flagged rather than quietly widened:** the same blindness exists in two
neighbours — 1.4.1's "is there any text here at all?" test and its marker-character check both
read inner text, so `<input type="submit" value="Delete">` styled only in red is still out of
scope for colour. Same family, different criterion, and the team scoped this fix to 2.5.3.

**Verified:** 7 new tests in `test_a11y_checkers.py`, including the three value-bearing types
parametrised, the typed-in text field that must **not** be selected, the valueless button, and
the button whose name already contains its label.

### 9.16 The 1.3.1 scope gap — 24 August ⭐ (BUILT — Option B)

The third finding from the same investigation, and the only one that is not a fix. The check
carrying **1.3.1 Info and Relationships** asks *"is this a fake control or a fake heading?"* The
criterion asks *"is the visible structure real?"* — tables with header cells, lists that are
lists, grouped fields that are grouped. Those are different questions, and a table with no header
cells is claimed by nobody while the page is recorded as passing 1.3.1.

It is not a bug: every rule is deliberate, documented and tested. The check was built to answer a
narrower question than the routing table records it against, and nothing ever compared the two.

**Decided and built the same day: Option B**, a fifth checker called `structure` owning 1.3.1
on its own, whose unit of work is the **container** — because whether a table has headers is a
fact about the table and not about any cell in it. It is handed every rendered table, list and
field group, a form whose radio buttons or checkboxes have no grouping around them, and a
container repeating the same child class three or more times (a list drawn without being one).
Two repeats are left alone: a pair is a layout.

`semantics` keeps 1.3.1 alongside it, deliberately. The two ask different questions and stay
apart because accuracy is scored **per checker** — folded together, a good score on fake buttons
would average away a poor one on tables, which is the same hiding that let this go unnoticed.

**Option C was skipped on the team's instruction** ("the fix should be accurate, time does not
matter"), so the conformance statement kept claiming full 1.3.1 coverage until this landed.

**Found while building it:** a container's markup reaches the judge bounded at 8000 characters,
so a long table would have been judged from a fragment, silently. The capture now reports when
it had to cut, and the judge answers `uncertain` naming the truncation instead. That one helps
every check.

**Not built, and still worth doing:** a guard that fails when a check is registered against a
criterion it does not actually cover. That is the thing that stops this recurring elsewhere; the
test that exists pins the mapping, which is narrower.

**Verified:** 26 new tests in `test_a11y_checkers.py` (126 total) — every container shape, both
correctly-built shapes that must be left alone, the repeated-class threshold, the container's
own class not counting as one of its children, and the truncation flag end to end. Two guard
tests fired during the build and were updated with their reasoning rather than loosened.
Regression: 462 across checkers, capability, judge, WCAG, ownership and the baseline report.

**Full analysis and the options as they were put: `SCOPE_GAP_INFO_AND_RELATIONSHIPS.md`.**

### 9.17 Two more things nobody was looking at — 24 August (BUILT)

The last two uncovered shapes from the twelve-case probe of §9.14, both **1.1.1 Non-text
Content**, both reported by nobody — not by the rule scanner and not by us.

**A `<canvas>`.** A drawing surface: a chart, a signature pad, a seating plan. Whatever it
renders exists only as pixels, and nothing inside it is reachable. No rule anywhere can say
whether its fallback text describes what was drawn, because answering needs somebody to look at
it — which is the exact shape of question the AI half exists for. Now selected.

**An icon drawn by a font.** Two ways in, and the first is not a heuristic: a single character
from the Unicode **Private Use Area** has no meaning of its own, so what a sighted person sees
is whatever picture the font puts there. The second is the empty-element case — nothing to
read, no image inside, and a class naming an icon family.

**Deliberately still not selected**, each for a stated reason rather than by omission: an
`<iframe>` with no title (the rule scanner proves that deterministically, and a second opinion
costs a judgment on every embed); and an icon font using a real word as its ligature
(`<i class="material-icons">delete</i>` is announced as "delete" — a poor alternative, but an
alternative, and selecting it would queue every such icon to be told it is mediocre).

### 9.18 Nothing checked that a check covers the criterion it claims — 24 August ⭐ (BUILT)

**The durable lesson of §9.16, made mechanical.** The 1.3.1 gap was not a coding error. A check
was built to answer one question well, the routing table filed it under a criterion far broader
than that question, and **nothing anywhere compared the two**. Every test in the suite asked
*"does this rule do what it says?"*; none asked *"does what it says amount to the criterion it
is filed under?"*

**Built:** `backend/tests/test_a11y_selection_corpus.py` — a corpus of real accessibility
failures, each with the same shape done correctly beside it. Three rules bind it:

1. **Every criterion the checks claim must own at least one failing shape.** Claim a criterion,
   build no selection for it, and there is nothing to put in the corpus. That is exactly the 21
   August failure, and it can no longer pass.
2. **Every failing shape must be selected by a check claiming its criterion** — so a criterion
   with nothing reaching it fails here rather than in a client's conformance statement.
3. **Every criterion must also own a shape that must NOT be selected.** Without this a rule
   that returned `True` would satisfy rule 2 for everything and the file would be a rubber
   stamp. These rows come straight from the `skips` prose on each `SelectionRule` — that prose,
   made executable.

**Proven against the failure it was built for.** With `structure` removed in memory — the
platform exactly as it stood on 21 August — **five of the recorded 1.3.1 failures reach no
check at all** and the guard names each one. Before it existed, the same state produced a clean
run and a conformance statement saying eleven pages satisfied 1.3.1.

**What it cannot do**, recorded so a green run is not over-read: it proves a criterion has
*some* path to a check, not that the coverage is complete. A criterion can hold one shape here
and still miss ten others in the world. It converts an unbounded silence into a list somebody
can argue with, which is the most a test can do about this.

**Verified:** 55 tests, 46 corpus rows across all five claimed criteria. Regression: 354 across
the corpus, checkers, capability, capture and dispatch suites.

### 9.19 A container's markup did not scale, and failed silently — 24 August ⭐ (BUILT)

**Raised by the team**, reading §9.16: *if answering "not sure" does not actually help, it
should have a surgical permanent fix, right?* It should, and it now does.

**The number, which §9.16 should have stated.** An element's markup reaches the judge bounded at
**8,000 characters**. A five-column table row of realistic markup measures 188, so the bound
holds roughly **forty rows**. Across the whole 21 August audit the largest element captured was
503 characters — nowhere near it — because Meridian's tables are small. On a client's reporting
screen it would bite on almost every table.

**Why `uncertain` was not the fix.** It stops us being *wrong*; it does not make us *useful*. An
uncertain verdict routes the element to a person, so on a real reporting screen **every large
table would land in the review queue** — an automated check turned back into a manual one
exactly where tables matter most. Honest, and useless.

**The fix: send the shape, not the markup.** What 1.3.1 asks about a table is its arrangement —
how many rows and columns, which cells are headers and what they are scoped to, whether there is
a caption, what the top row and left column say. That is a few hundred characters for a table of
**any** size, because it is bounded by how *wide* a container is rather than how *long*.

**Measured in the real browser engine, against a real 401-row table:**

| | markup | outline |
|---|---|---|
| 3-row table | 206 chars | 317 chars |
| **401-row table** | **31,985 chars** — cut at 8,000, three quarters lost | **906 chars, nothing about the shape lost** |

**It is also the better input, not merely the smaller one.** Recovering a grid from a wall of
tags is something code does perfectly and a language model does unreliably. The parsing now
happens once, in the browser, and the judge spends itself on the part that actually needs
judgment. The failing case reads directly: `rows: 401, columns: 2, header_cells: 0`, with a
first row of two cells whose `header` is `false` and whose text is "Title" and "Status" —
column headings to every reader of the page, ordinary cells to every screen reader.

**In the cache key, and it had to be.** A container's markup is bounded, so a table can gain
three hundred rows while its first 8,000 characters stay byte-for-byte identical. Keyed on
markup alone, that table would keep its old verdict for ever — the cache answering about a page
that no longer exists. A missed cache hit costs one judgment; a stale one costs the truth.

⚠️ **This invalidates every stored verdict once**, so the next audit re-judges from scratch.
That is the intended price, and it was paid at the one moment it is free: **no reviewer has
ruled on any finding yet**, so no human decision went with it. Later, it would have cleared
rulings people had made.

**The truncation flag stays**, demoted to what it should always have been — a backstop for
detail further down the markup, not the answer to the question.

**Three deliberate details:**
- A container the capture **could not** describe arrives as `{"kind": "unreadable"}` with a
  reason, never as an absent outline. "We could not look" and "there is no structure here" are
  different answers and must not collapse into one.
- A non-container carries **no** outline at all, so an empty one can never read as an empty
  table.
- Serialised with sorted keys, or two runs over an unchanged page would disagree about the
  cache key and re-judge everything for ever.

**Verified:** the outline functions were lifted out of the shipped capture script and run in
**Playwright, the same engine the companion drives**, against a page holding every shape they
exist for — a table with no headers, the same table done correctly, a list with stray content,
grouped and ungrouped fields, a card grid, a two-panel layout (correctly `null`), and the
401-row table. 10 new tests in `test_a11y_checkers.py` and 3 in `test_a11y_baseline.py`, 235
across the checker and capture suites, 305 across dispatch, corpus, report and judge. A third
guard test — the one pinning exactly what the cache key reads — fired and was updated with its
reasoning rather than loosened.

### 9.20 A pass that stopped short reported the pages it never opened as clean — 24 August ⭐⭐ (BUILT)

**Found by tracking a live seventeen-page audit**, and it is the most serious thing this
capability has produced. The audit reached its judging limit after **eight** pages. The other
nine had **not one element** sent to the AI — and were recorded as **passing**.

**Why a page nobody looked at came out clean.** A site's header, footer and nav are the same
markup on every page, so the platform correctly recognises them as one question and stores one
answer. That answer is then written back against every page the markup appears on, which is
right — the footer really is on all of them and really is fine. But `/catalogue/subject-index`
has eighteen things worth checking and **eight of them are shared furniture**. Those eight
borrowed a pass from pages the AI had actually visited. Its own ten — including a table whose
column headings are ordinary cells — were never asked about and said nothing.

**Eight passes and no failures is indistinguishable from a clean page.** For forty minutes the
audit sat at status **complete** claiming *Info and Relationships: satisfied on all 17 pages*.

```
subject-index requests answered by a verdict borrowed from another page:  8
subject-index requests genuinely its own, never asked                  : 10
```

**The existing guard could not catch it.** `findings._fill_in_scope_gaps` already refuses to
invent a result for a page with anything unjudged — its docstring says so. But it only stops the
platform *inventing*; a **real** passing verdict that arrived from somewhere else walks straight
past it.

**Two fixes, and the second is the one the team insisted on.**

1. **The limit now counts distinct questions** (§9.21). On this site that alone means nothing is
   deferred, so the situation stops existing rather than being caught.
2. **An element nobody asked about is recorded as such, on its own page.** A fifth coverage
   outcome, `not_checked`, ranked above `passed` so a page we broke off halfway through can
   never be written down as clean — and above `needs_human` too.

**Why `not_checked` rather than reusing `needs_human`.** The team rejected the first proposal
outright and were right to: *"he needs a solution that can work — if they are really uncertain
then it would be correct and he will accept."* `needs_human` means a check looked and could not
decide: settled work belonging to a person. Labelling our own unfinished work that way hands
somebody an element nobody looked at, dressed as a judgement that hesitated. `not_checked` says
what is true, and the thing to do about it is the **Check the rest** control that already
exists — an action, not a judgement.

**Ranked above `needs_human` deliberately:** finish the cheap automated work first, and only
then hand over what genuinely needs a person. The conformance document makes no claim while a
criterion has either, and says which in its own words.

**Verified:** the live case reproduced as a test — a borrowed pass plus one unasked element must
not read as passed — together with the three ways a fix like this goes wrong: a finished page
must still record its passes, a real failure must still outrank a silence, and an unasked colour
question must not cloud a structural one. 84 tests across dispatch and findings, 91 across
knowledge, conformance and scan coverage, 370 across report, judge, baseline and review.

### 9.21 The judging limit counted the same question up to seventeen times — 24 August ⭐ (BUILT)

**The cause behind §9.20, and it was never a big-site problem.** The limit of 200 judgments was
applied to raw requests, and duplicates are only collapsed when an *answer is stored*. So one
footer on seventeen pages took seventeen of the 200 places — and was genuinely asked seventeen
times.

| | selected | actually different |
|---|---|---|
| The 17-page audit | 371 | **192** |
| The dev's 3-page audit | 39 | **28** |

**192 is under 200.** The whole site fitted in one pass. It was never too big; the counting was
wrong. Instead it took two passes, sent 276 elements to the AI where 192 would do, and reported
nine untouched pages as passing in between.

**The codebase already did it correctly elsewhere**, which is what made this a small change: the
"Check the rest" path asked 76 questions to cover 64 distinct elements and deferred nothing. Two
behaviours, one codebase, one of them right.

**The fix:** collapse duplicates *before* the limit, so it means what its own comment says —
how many elements one run may judge. Safe because the merged report walks every request the
**capture** holds rather than the ones dispatched and looks each up by fingerprint, so every
copy still gets its own row, on its own page, with its own selector. That fan-out already
existed; it is what produced the borrowed passes in the first place.

**Measured against both real captures after the fix:**

```
MINE 17 pages:  371 selected -> 192 distinct -> 192 asked, 0 deferred
DEV   3 pages:   39 selected ->  28 distinct ->  28 asked, 0 deferred
```

De-duplication is by **question**, never by element: a `<div role="button">` styled only in
colour is both a semantics question and a colour question, and the fingerprint includes the
checker. Pinned by a test, because a "de-duplicate the elements" refactor would silently halve
the coverage of every multi-checker element and nothing else would notice.

**One test fixture had to change, and it is not housekeeping.** The screens-cap test used the
same default image on three routes. The route is deliberately not part of a fingerprint —
identical markup in identical surroundings is one question wherever it appears, which is the
whole reason the footer stopped costing a judgment per page — so those three collapsed and the
screen cap never got to bite. Giving each page a genuinely different element put the screen cap
back under test.

### 9.22 The judge was handed its own previous answers — 24 August ⭐⭐ (BUILT)

**Found on the dev's tenant, on current code.** His judging run recorded **zero** verdicts while
writing a confident summary: *"Gate outcome: PASS — no work blocked. 33 AI-judged elements. All
pass."* It had judged nothing, and its own count was wrong — there were 32 colour elements, not
26. "All pass" would have been wrong regardless: the same rows correctly **failed** on the other
tenant an hour later.

**Every one of those words came out of its own briefing.** The platform indexes every artifact
as searchable knowledge the moment it is registered, and fills each run's briefing by searching
that index for what the run is about. So an accessibility judging run searched for accessibility
judging knowledge, and the best match in the whole project was **the last accessibility
judgement**. Retrieval returned, among the top eight:

```
'**31. `#loans-table > tbody > tr:nth-of-type(3)` on `/loans/history`** - 1.4.1 ...'
```

— one of the very elements it was being asked to judge, with last time's answer attached. The
previous run's complete verdict document sat in its briefing at character 6233, "Gate outcome:
PASS" and all.

**This was not an unreliable model, and that matters.** The same agent judged 128 elements
correctly an hour later on a tenant whose retrieval happened to return summaries instead of a
verdict table. Which of the eight you get is chance. Measured afterwards: **215 of 221** indexed
chunks in that project were accessibility verdicts — 97% of its "knowledge" was previous answers.

**The fix: a result is not knowledge.** `a11y_judge`, `a11y_report`, `a11y_baseline` and
`a11y_conformance` are no longer indexed. They stay fully reachable by name — `list_artifacts`
then `get_artifact_body`, which the briefing tells every agent about — so an agent with a
*reason* to read last week's report still can. What it can no longer do is find it in its own
pocket.

**Not a rule telling the agent to ignore it**, which was the first proposal and was wrong: an
agent cannot be relied on to disregard a plausible, authoritative, on-topic answer sitting in its
own context, and should not have to. These documents are also the wrong shape for an index —
each is a statement about one capture, superseded by the next run, so a project accumulates
contradictory copies of "the answer" retrieved by recency-blind search.

**A migration removes what is already indexed**, because stopping the indexing does nothing about
the 52 and 215 chunks already sitting in the two tenants. Deleting them loses nothing: a chunk is
a retrieval copy, and the artifact, its body and its version history are untouched.

**The safety net stays and earned its place:** the write-completeness check caught the empty run,
failed it, and refused to call the audit complete.

**⚠️ A residue was found and deliberately left — team decision, 25 August.**

Each judging run writes two documents: its verdicts, and a short note on its own reasoning
(*"here is how I mapped this axe rule to this criterion"*). Only the verdicts are a result, so
only the verdicts were excluded — a note about *how* to reason carries no answers and is worth
having next time.

**One of the five surviving notes has an answer in it.** From the dev's tenant:

> *"1.4.1 vs 1.4.3 independence — An element can simultaneously fail 1.4.3 and pass 1.4.1 … the
> `#hours-note` element exhibits exactly this combination."*

That names a live element on a page under audit and states its verdicts. It is the same class as
what §9.22 removed — one sentence about one element rather than a findings table, and a nudge
rather than a finished answer to copy, but the same class.

**How it would bite, and it is worth recognising the symptom.** `#hours-note` is a real open
defect. If somebody fixes it and re-audits, the judge starts the run holding a note that says it
fails 1.4.3 — and may report a **fixed defect as still broken**. If that is ever seen, this is
the first place to look.

**Why it was left.** One sentence about one element is a long way from a findings table, it may
never bite, and the methodology in those notes is genuinely useful. The counter-argument, which
did not win but should be recorded: "the judge mostly does not put answers in its reasoning
notes" is not something it can be held to, and one note in five already did.

**If it is ever built**, the fix is narrow and the same two pieces as §9.22 — stop indexing
`assumption` artifacts whose phase is `a11y_judge` or `a11y_journey`, and clean up the five
already stored. Assumption records from every other phase (onboarding, document vision, testing)
carry no verdicts about pages under test and stay indexed. Counted at the time: 2 in the dev's
project, 3 in ours.

### 9.23 The container outline never reached the AI — 24 August ⭐ (BUILT)

**§9.19 was built and was inert.** The outline was added to the element contract, the selection
rules, the cache key, the batch the judge receives and the judge's own instructions — and not to
`capture._element`, which is the only thing that decides what survives to storage. The browser
measured every table's shape, the platform received it, and that one function dropped it.

Across 371 captured elements on a seventeen-page audit, elements carrying an outline: **zero**.
The judge is told *"start with the outline"* and was handed the field name with nothing in it.
Confirmed on the dev's tenant too.

That function's own docstring said *"Every key `rules.CapturedElement` reads is passed straight
through"*, which stopped being true the moment the fields were added.

**Nothing failed, because nothing compared the two lists.** That is the defect — not the two
missing keys, which are a symptom of it. The fix stores them; the *permanent* fix is
`test_every_field_the_contract_reads_is_actually_stored`, which diffs what the contract reads
against what is stored and names any field that goes missing. `route` and `screenshot_ref` are
named exceptions with a reason, so a third one has to be argued for rather than quietly appear.

A second test pins the **value** as well as the key: a normaliser that coerced the outline to
`{}` would satisfy the contract check and still hand the judge nothing.

### 9.24 Eight UI observations from reading the screens — 25 August ⭐⭐ (BUILT)

The team walked the three accessibility screens and the work items an audit creates, and wrote up
eight groups of problems. **Four were exactly what the screenshots showed. Four had a cause nobody
would have guessed from the symptom**, and those are the ones worth reading:

| The symptom | What was actually causing it |
|---|---|
| An audit says "Complete" when it isn't | The screen read the audit's state machine and never the "how much was left" number sitting beside it |
| Only `assumptions` is auto-published | **Every** artifact of a judging run is. The other one is tagged as run output, so it wore a disguise |
| Bounding boxes in the wrong place | Not the capture, not the arithmetic. One line: `max-height: 340px` |
| A defect description looks like a warning | The text was already correct markdown. One screen printed it raw inside a red alert |

Written up per observation, in the team's own numbering, as **#46–#53 in the Testing Guide**. Only
the parts with a design consequence are recorded here.

#### The ring was off by exactly the clamp ratio, and that is what proved it

The ring is placed in percentages of the capture's own pixels. A percentage on an absolutely
positioned element resolves against its **containing block** — which was `.shot__stage`, whose
height CSS clamps to 340px while a full-page capture renders several times taller. Measured on a
1280 × 1144 shot in this panel: the ring landed 237.8px down where the element was at 461.3px, and
17.8px tall where it was 34.6px. Both are 340 ÷ 659.6 of where they belonged — the same factor,
twice, which is what turns a plausible explanation into the explanation.

The ring now sits inside `.shot__frame`, which shrink-wraps the image, so the percentages resolve
against the picture in both display modes. Verified against the shipped stylesheet, exact in both.
The same line was also cropping ~319px off every tall capture in *Fit to width*, which now scrolls.

**No test could have caught it and none can now.** It lives entirely in CSS and the test
environment computes no layout. What is pinned instead is the arrangement the fix depends on — the
image and the ring alone together inside the frame. That is the honest boundary of what a test can
hold here, and it is stated rather than papered over.

#### `auto_approve` published two things it was never meant to

`publish_artifacts_core` runs on gate approval, and **published** in this platform means a named
human approved this. A run started with `auto_approve` has no gate and the activity runs anyway —
correct for document vision (00e), where the human had already adopted the source document, and
the reason that exception was argued for.

The accessibility judging and journey runs set the same flag for a **different** reason: nobody
watches their carrier work item, so a gate there would hang the audit for ever. They inherited the
publishing without inheriting the justification. Measured 25 August across two tenants: every
artifact of every judging run, published, approved by nobody.

`NEVER_AUTO_PUBLISHED_PHASES` in `orchestration.activities` now names the two phases, and what was
left as a draft is returned by the activity **and** put on the event — a step that quietly does
less than its name says is the shape of failure this file keeps meeting.

#### A derived status cannot drift; a stored one can

The audit badge is now computed from the audit's state **and** its outstanding count, rather than
from the state alone. That is why pressing *Check the rest* turns it green with nothing else to
update. The team asked for "In progress" and chose **"Not fully checked"** once it was pointed out
that the same screen has a real *Audit running* panel, and two things reading as in-flight sends
somebody looking for a run that is not happening.

#### A generated title is only fixed for the next one

`_title` is called when a defect opens and never again — `record_a11y_findings` deliberately does
not restamp it, because somebody may have renamed the ticket. So improving the wording fixes
nothing already on a board. Migration `a11y/0029` retitles the 35 existing ones, matching **only**
titles still in the exact shape the platform generated, so a hand-edited title is left alone.

#### Two migrations, and what the last round taught them

`0029` (titles + the epic's description) and `0030` (artifacts back to draft) both reach across
tenants, so both **arrange their own access** rather than trusting the role — the lesson from
`knowledge/0003`, which trusted it, deleted nothing, and recorded itself as applied. Both print
what they found and what they changed.

They also **read `FORCE ROW LEVEL SECURITY` before lifting it and restore what they found**, rather
than switching it on the way out. `knowledge/0004` restored unconditionally; on a database where
FORCE happened to be off, that would have been a migration quietly tightening a table it was only
passing through.

And a dependency has to name the state a migration actually needs: `0029` first declared
`workitems 0001_initial` and failed on a database built from scratch with `column "title" does not
exist` — from a data migration whose whole job is titles. It now names the migration that adds the
column.

#### One thing chosen over a cheaper alternative

The long copy on two panels folds behind a **native disclosure**, not a hover tooltip. A tooltip
cannot be opened with a keyboard and does not exist on a touch screen; this product exists to find
that defect on client sites. Its label is **grey** (`--text-body`, 10.03:1) rather than a link
colour: it opens something on the same page, it does not navigate, and two blue lines on one
screen read as loud. Brand orange was never available — **2.97:1** on white, below the 4.5:1 this
capability sells.

And the marker is **drawn with borders, not written as a character**. It shipped as
`content: "\25B8"`, the escape was mangled on its way through the script that wrote it, and the
file ended up holding a raw control byte — rendering live as a tofu box followed by the text
"B8". A shape with no glyph in it cannot be mis-encoded and needs no font installed. Every file
this change touched is now scanned for stray control bytes.

### 9.25 The first full-scale audit — 31 August ⭐⭐ (BUILT)

**The first run at real size: 94 pages, 2,171 elements, 1,065 questions.** Everything built for
scale worked — every page visited, every element captured, the judge answering steadily. Then one
duplicated call destroyed the audit's own account of itself, and every wrong number the team saw
for the rest of the day came from that one record.

Four defects, all of them **product** defects that would hit any client application identically,
plus a fifth finding that is recorded rather than fixed.

#### 9.25.1 One audit was closed twice, and the second close wrote off the first ⭐⭐

**The chain, end to end, and none of the links is exotic.**

Closing a 94-route audit is minutes of work: reconcile the route list, hash 2,171 stored
elements, check each against the cache, file what cannot be asked about, start the judging run,
write the batches. The companion's platform client had a hard **60-second timeout on every call**
(`state_client.py`). The socket gave up; the server carried on regardless; the daemon read the
timeout as *the audit failed* and ran its recovery path — which closes the audit. **The same close
ran a second time while the first was still going.**

The second close was refused a judge, correctly, by `trigger._guard_no_active_run` — a run was
already live on that work item. But that refusal arrived at `dispatch` as an ordinary exception,
so it was reported as *the judge could not be started* and every pending element was filed as
`uncertain` for a person.

**What that cost, read straight off the audit row before and after:**

```
started        : true            ->  false
dispatched     : 800             ->  0
deferred       : 265             ->  0
judge_run_id   : dce6c6be…       ->  null
filed_unjudged : 0               ->  1065
status         : judging         ->  complete
```

**1,065 elements written off while 800 of them were being judged at that moment**, the record of
the pass that *was* running replaced by the record of a pass that did nothing, and the audit
marked complete with the judge still working. The screen then said *"1065 elements were never
looked at"* about an audit that had 338 real verdicts in the database and climbing.

**Three fixes, and the first two are independent of each other on purpose.**

1. **A run already in progress is no longer a failure.** `dispatch` catches `ActiveRunError`
   separately from every other trigger failure and returns `already_running`: nothing filed,
   nothing deferred away, nothing written off. This is the fix that matters — it protects every
   caller, not only a baseline audit, and it is stateless, so no crash can leave it half-applied.
2. **A repeat close returns the audit untouched.** `finish_baseline_audit` sees
   `already_running` and returns what the call doing the work left — status, summary and baseline
   all belong to the run that is judging, and it completes them through the ordinary closing step.
3. **The client stops timing out on a call whose job takes minutes.** `SLOW_TIMEOUT_S` for the
   three `finish_a11y_audit` call sites. A client that reports a healthy audit as failed is wrong
   on its own terms, and would have gone on doing it on every large audit.

**Verified:** the live case reproduced as a test that closes one audit twice through the
platform's **real** `_guard_no_active_run` — only the Temporal start is stubbed — and asserts the
summary is byte-identical afterwards, the status is still `judging`, `filed_unjudged` is 0, and
exactly one judge run exists. 238 tests across dispatch and baseline.

#### 9.25.2 A failed dispatch relabelled work that was correctly queued ⭐

**Two facts about two different sets of elements, held in one string and one list.**

Both failure paths in `dispatch` did `unjudged_requests = pending + deferred` and then
`deferred = []`. So the 265 elements correctly held back at this run's limit were filed carrying
*"the judge could not be started"* — a sentence that is not true of them. They were queued, not
unaskable, and the difference is the whole content of the **Check the rest** button.

Client-visible result: the sidebar badge read **1,731 items waiting on a person**, every one of
them `source='AI'`, `verdict='uncertain'`, and none of them real.

**The fix.** Each path files only what it actually attempted. The deferred tail stays deferred and
carries its own reason in its own field (`deferred_reason`), so a failure can no longer overwrite
it. Nothing is lost by leaving them: an element with no verdict row at all is exactly what
`unanswered_for_capture` looks for, and `unanswered_counts` still adds `filed_unjudged` to
`deferred_distinct`, so the total a screen shows is unchanged. **What changes is that each half
now carries the reason that is true of it.**

**And the consequence had to be fixed with it.** `unaskedNote` on the audit screen returned the
cap sentence *or* the failure sentence. Now that both can be true at once, showing one would have
hidden the other — and the hidden one would have been the failure, which is the half somebody has
to act on. It says both, failure first.

#### 9.25.3 A container `<div>` with no class was never captured ⭐

Same shape as the `tr` gap and the `polyline` gap before it, one step further out. The `OFFER`
list carried `div[class]`; the three season containers on `/events/workshops` are
`<div id="workshops-spring" style="padding-left:1.5rem">` wrapping five identically classed
children. `structure` claims that shape on sight — it was simply never shown one.

**Never offered is worse than declined, and this is why.** An element that is offered and turned
down is *counted*, and `rules.explain()` can say which rule declined it. An element never offered
produces no row anywhere: nothing declined it, nothing recorded that it existed, and the page is
written down as checked.

**Measured before it was written**, exactly as the `polyline` change was, and the two candidates
cost the same on this fixture:

```
routes measured : 95
offered today   : 8,385 elements
div:has(> *:nth-child(3))  -> +3, all 3 claimed   (busiest page 545 of the 600 ceiling)
div[id], div[style]        -> +3, all 3 claimed
```

**`div:has(> *:nth-child(3))` was chosen, and not because of the fixture.** It is
`REPEATED_CHILD_MINIMUM` said in CSS — the same bar the rule that would claim it uses — so it
offers what that rule can actually want and not a wrapper more. `div[id], div[style]` would have
fixed Meridian and left every framework's class-less, id-less wrapper exactly as invisible as
before, and the target is any real application rather than this one.

**Verified live** against the running fixture: that page went from 80 to 83 elements and all three
containers arrive carrying their structural outline.

#### 9.25.4 Our own check could never have found 9.25.3 ⭐⭐

**The one that should worry us most**, because it is a check that reported green on exactly the
thing it exists to find.

`verify-selectable.js` asks whether every answer-key record can reach the checker it was labelled
for. It reached each recorded element with `document.querySelector` — which finds anything on the
page, offered or not. So it ran the **second** step of selection (do the rules claim it?) and
never the **first** (would an audit collect it at all?), and the only failure it could not see was
an element missing from the `OFFER` list.

**What that hid, and the asymmetry is why it stayed hidden.** An expected-`fail` record counts
toward a checker's ceiling whether or not anything reaches it. So `structure` reported a reachable
sample of 30 — over the line — while **3 of its 15 failure records could never be found by any
judge**. Its recall was capped at **12/15 = 80%** and every check was green.

**The fix.** `OFFER` is exported from the companion's audit script and imported by the harness —
one definition, so it cannot drift, the same rule `selectable.py` already follows by importing
`rules.py` rather than restating it. The check compares **element identity** rather than selector
strings, because the companion writes its own `cssPath` and comparing that against a hand-written
golden selector would call two spellings of one element a miss.

`selectable.py` now reports two different problems instead of one, and only the second fails the
run:

| | Means | Fix lives in |
|---|---|---|
| *collected, then declined* | a rule looked and said no | the answer key, or nowhere |
| *NEVER COLLECTED* | nothing ever showed it to a rule | the `OFFER` list |

**Proved rather than asserted:** with the 9.25.3 fix temporarily removed, the check names all
three records by id, says which rule would have claimed each, and exits non-zero.

#### 9.25.5 Terminating a run does not stop the agent — BUILT, 31 August ⭐⭐

**Found while stopping the audit, and it is a platform-wide fact rather than an accessibility
one.** The workflow was terminated on Temporal at 06:46:36 and reported `TERMINATED`. Verdicts
went on arriving until **07:37** — 49 minutes later, one every five to ten seconds, all stamped
with the terminated run's id.

The agent is a Claude Code process on the companion. It posts each verdict through the runner
state API, which never asks whether the run it names is still live. So the workflow is the
platform's control over *orchestration* and not over *work*, and "stop" stops only the former.
Only killing the companion ended it.

**BUILT, 31 August, at the agent surface — and the choice of surface IS the fix.**

The three tools the agent calls — `batch_for_run`, `record_finding`, `screenshot_pointers` — now
refuse a run whose status is `failed`, `completed`, `rejected` or `approved`. Refusing the write
alone would not have been enough: most of those forty-nine minutes were an agent reading batches
and reasoning about elements, so it is refused work as well as refused writes.

**`STALLED` is deliberately absent from that list, and it is the whole subtlety.** A parked run is
not over — its deadline passed while the machine was still working, and the platform keeps waiting
on purpose so a late report reconciles it (S.No 89). On 31 August that is exactly what happened:
the deadline fired at two hours and the pass reported normally sixteen minutes later. Refusing a
parked run's verdicts would have thrown away the last fifteen answers of that pass.

**And the platform's own accounting is not the agent.** `verify_judgment_completeness` files a
fallback for every element the judge never answered, and `close_unfinished_ai_pass` calls it on
runs that are ALREADY terminal by design — it is the recovery that saved this audit twice. A guard
that could not tell the platform from the agent would have silenced the thing that guarantees
nothing dispatched vanishes. Tested explicitly, in both directions.

**The message is written for a model to act on**, because that is who reads it: it says the work is
over, that nothing was stored, and to stop — rather than describing a state and leaving the next
move to be guessed. A rejection an agent cannot act on is a rejection it repeats.

**What is still open, and named rather than implied.** This closes the surface where the leak was
observed and where it corrupts a client-facing conformance report. It does not make the runner
state API refuse every write for every closed run of every phase, and it does not have the
companion poll its own run's status and exit — both are control-plane changes with their own
blast radius, and neither is a11y's to make unilaterally. The earlier defence still stands too:
tenant clean-up refuses to delete anything if a judgment was written in the last five minutes,
because "the workflow is stopped" turned out not to be evidence that nothing is writing.

#### What this audit produced, and what it could not

**No accuracy number, and the reason is stated rather than worked around.** Only **43 of 173**
answer-key records received a real verdict — `alt` 12, `color` 9, `label` 19, `semantics` 0,
`structure` 3. `DEFAULT_MIN_SAMPLE` is 30 and no checker reached it, so every figure reads *not
yet measurable*, which is correct and is the point of that floor.

**What did stand up, and is worth saying because it is easy to lose in a bad day:** all 94 pages
visited and 2,171 elements captured with no reconciliation gaps; 335 genuine rule-scanner
findings; and Friday's fixes confirmed working on real output — 20 `label-content-name-mismatch`
and 3 `td-has-header` findings that no pre-28-August audit could have produced.

#### One thing found that is not ours to fix here

**14 backend tests were already failing on this branch**, identically with every change above
stashed. ~~All of them trace to the `graphics` / 1.4.11 checker added on 27 August~~ and never wired
into `integrations.capabilities.A11yAI`, the selection corpus, or several test expectations that
enumerate checkers. One may be a real product gap rather than a stale test: there is no
`check_graphics`, so 1.4.11 cannot be asked through the capability at all. Logged as its own
task, deliberately not fixed in passing — the corpus entries need writing properly and the
capability question needs a decision.

> **Corrected 1 September — see §9.29.A.** The struck clause is wrong, and the count has moved.
> Re-measured across eleven a11y test files the figure is **16, from three causes**: 11 are the
> graphics widening described here, **3 are stale assertions against the conformance guard of
> §9.26 and have nothing to do with `graphics`**, and 2 are the selection corpus reporting that
> 1.4.11 owns no failure shape. None of the sixteen is a product defect. The suspicion recorded
> above — that the missing `check_graphics` is real rather than a stale test — **is confirmed**,
> and is one of the three gaps in §9.29.B.
>
> **And corrected again, the same day — see §9.30.** The figure of 16 was itself short: eleven of
> thirty-three a11y test files were measured, and a full sweep found **21 backend and 1 frontend**.
> The three "conformance guard" failures were also mis-explained here — see §9.30.D. **All of them
> are now green**, sixteen of the twenty-one without an assertion being edited, because they were
> all objecting to one thing: `graphics` claiming a criterion the ownership registry gives to
> `rule`. That claim is withdrawn (§9.30.A). The missing `check_graphics` is no longer a gap for
> the same reason — a held-back check needs no capability method.

One of the fourteen was fixed, because it sat in a file this work was already changing and a red
test on the branch we build on is a hazard: `test_finishing_produces_findings_for_the_registered_routes`
asserted the exact list of every finding regardless of source, so a correctly added checker read
as a broken audit. It now asserts on rule-scanner findings, which is what it was always about.

### 9.26 The first audit that RAN TO COMPLETION — 31 August ⭐⭐ (ALL BUILT)

**The second attempt of 31 August finished.** 94 pages, 2,174 elements, 1,068 distinct questions;
800 judged in the first pass, 268 deliberately left for a second; **358 findings** (75 critical,
283 high); report and baseline both published; `filed_unjudged` **0** and placeholders **0** where
the broken run of the same morning finished at 1,065 and 727. The four §9.25 fixes are proven on
real output.

Running to completion exposed **four more defects, none of them caused by those fixes**. Every one
is behaviour that has always been there and that no previous audit survived long enough to reach —
the first attempt was killed at 1 h 07 m and never got past the two-hour mark at all.

**Deliberately NOT built yet.** The team's decision: finish the audit first, judge whether the run
was a success, then fix these together. This section is the record so nothing is lost in between.

Timeline of the close, straight from the ledger:

```
11:55:37  phase.reported   status ok, cost $33.12, "all 800 elements judged"
11:55:40  the judge's own write-up registered
11:55:42  run.executed     phase result registered; the takeover flag cleared itself
12:00:44  run.failed       "write-completeness check failed: activity StartToClose timeout"
12:00:50  the accessibility report published
12:00:51+ defects opened, one per finding
12:02:12  baseline v1   12:02:36  v2   12:03:12  v3   12:04:14  v4
12:03:43  audit status complete
```

---

#### 9.26.A The phase report deadline is one fixed number for every kind of work ⭐⭐ — BUILT, 31 August

**What it is.** When the platform hands a phase to the user's machine it starts a timer. If no
report has come back when it rings, the platform raises a *human takeover* flag saying the
companion appears offline.

**What went wrong.** At **11:39:05.905** it fired on a companion that was demonstrably online — a
verdict had landed seconds before and another landed seconds after. The arithmetic is exact:

| | |
|---|---|
| phase dispatched | 09:39:04.8 |
| takeover written | 11:39:05.9 |
| elapsed | **7,200 s — two hours to the second** |
| `report_timeout_seconds` on the run | never set, so the default of **7200** applied |

The judging actually took **8,193 s** for 800 elements — **10.2 s per element**. The timer is a
single constant shared by every phase; a planning phase takes minutes and this takes hours.

**What it means.** Nothing broke — the design is right: the workflow does **not** end, it writes
the flag and waits again with no deadline, and the late report reconciled it automatically at
11:55:42, sixteen minutes later. **The danger is the wording.** The event says *"companion
offline"*, and the natural response to "offline" is to press **take over** — the one signal that
turns this soft park into a terminal failure. It would have stopped the run **fifteen verdicts
from the end**. On this run the only thing that saved it was somebody deciding not to click.

**The fix — two halves, both small.**

1. **Let the phase say how long its own work should take.** `orchestration/trigger.py:234` builds
   `AgentRunInput` without ever setting `report_timeout_seconds`, so every phase silently inherits
   the `7200` default at `orchestration/types.py:28`. Add an optional
   `report_timeout_seconds: int | None = None` parameter to `trigger_phase` and pass it through.
   Then `apps/a11y/dispatch.py:480` passes a budget derived from the batch it is handing over:

   ```
   report_timeout_seconds = min(28_800, max(7_200, distinct * 25))
   ```

   **25 s/element is ~2.4× the 10.2 s/element measured here** — generous without being unbounded.
   This run would have been given 5 h 33 m; a small re-judge still gets the two-hour floor; the
   8-hour ceiling keeps a runaway bounded. **No other phase changes behaviour.**

2. **Say what actually happened.** `orchestration/activities.py:1050` writes the reason
   `"companion offline / no report before timeout"`. It should say that no report arrived inside
   the phase's budget, name the budget, and state that **the run is still waiting and will
   complete on its own if the machine reports** — which is what the code already does. A message
   that describes a deadline as a detection is what makes the dangerous click look reasonable.

**Proof it works:** a test that a11y dispatch passes a timeout scaled to `distinct`, and that a
small batch keeps the floor.

**BUILT, 31 August — as specified, both halves.** `trigger_phase` takes an optional
`report_timeout_seconds` (and B's `verify_timeout_seconds`); `None` keeps the dataclass default,
so every caller but one is byte-identical. The one is `dispatch_judgments`, which passes
`judging_deadlines(len(pending))` — `pending` being the distinct list *after* de-duplication and
*after* the cap, which is exactly the work handed over. The constants are named and carry their
measurement: 25 s/element against the 10.2 s/element measured, a 2-hour floor, an 8-hour ceiling.

`mark_phase_takeover_core` no longer says "companion offline" anywhere. It names the budget in
minutes, states in the same breath that **the machine has not been checked and may still be
working**, that the run is still waiting and completes on its own if the report arrives, and that
taking over is only for stopping it. Nothing in the codebase matched on the old string.

**Three tests**, one of them asserting the words that are absent — `"offline" not in reason` —
because the danger was never a missing fact, it was a present and wrong one.

**What it is.** After a phase reports, the platform runs a separate step that checks everything
the agent claimed to write was actually written. That step is deliberately strict.

**What went wrong.** At 12:00:44 the run failed with:

```
write-completeness check failed: activity StartToClose timeout
```

The *check* ran out of its own time budget. The judging had already reported `ok` at 11:55:37 with
all 800 elements answered.

**What it means.** **Nothing in the data was lost** — the failure path is built for exactly this
and did all three of its jobs: the report published, the defects opened, the baseline published,
the audit reached `complete`. But the run row reads **failed**, and anyone opening the run console
sees a failed run with no way to tell that the *checker* timed out rather than the work. On a
client-facing audit that is a false alarm about the one thing the platform exists to be trusted on.

**Root cause — VERIFIED after the first write-up.** `workflows.py:158` gives `verify_writes`
**5 minutes** for the phases in `LONG_VERIFY_PHASES` (`build_types.py:205` — `a11y_judge` and
`a11y_journey`) and 1 minute for everything else. Judging 800 elements blew through the five.

**And this is the same bug, one size up.** The constant's own comment records why it exists: at
**60 seconds** the check was cancelled mid-way on a 144-element run, **81 of 144 fallback verdicts
were written and 63 elements silently got none** — precisely the *"nothing dispatched may vanish
from a conformance report"* guarantee the branch exists to keep. It was raised to five minutes.
**At 800 elements five minutes is the new sixty seconds.**

**So this is not cosmetic, and today's run was lucky.** The check is cancellable half-way through
work it is supposed to complete. It only *looked* harmless this time because the judge had
answered all 800 and there were no fallbacks left to write. Had the judge stopped short — the
usage-limit case the team asked about, or 9.26.E's dead machine — the cancellation would have
filed some of the unanswered elements and silently skipped the rest.

What saved the run afterwards is worth knowing: the a11y judge dispatches with `auto_approve=True`
(`dispatch.py:483`), and `workflows.py:170` sends an auto-apply phase to `fail_run` rather than
parking it — so `close_unfinished_ai_pass` redid the accounting properly and published. **A gated
phase in the same situation parks and waits for a human instead.**

**The fix — the same shape as 9.26.A, because it is the same mistake.** Stop picking a constant
and size the budget to the work:

```
start_to_close_timeout = 1 min                                  (ordinary phases)
                       = min(30 min, max(5 min, elements * 2s)) (LONG_VERIFY_PHASES)
```

Today's 800 elements would have been given 26 minutes against the ~5 it needed. `verify_writes`
already receives `inp`; the element count comes from the same `run.inputs.a11y_batches` the check
is about to walk, so nothing new has to be plumbed through the workflow's arguments.

**Second, smaller half:** a *timeout* and a *found gap* are different facts and should not produce
the same run state. A check that could not finish should say so in those words.

**Not on the table: weakening the check.** It is the thing that guarantees nothing dispatched
vanishes silently, and §9.25 is what happens when that guarantee slips.

**BUILT, 31 August — with one deliberate departure from the sketch above.** The budget is sized
by the DISPATCHER and read by the workflow, rather than computed inside the workflow. The
workflow module is Django-free on purpose — it cannot read `run.inputs.a11y_batches`, so the
line above ("nothing new has to be plumbed through") was wrong when it was written. It travels as
`AgentRunInput.verify_timeout_seconds`, defaulting to the 300 s the workflow used to hard-code.
`min(30 min, max(5 min, elements × 2 s))`, so 800 elements get 26 minutes against the ~5 they
needed, and no size of pass gets less than it has today.

**One deploy consequence, and it is the usual one: worker before API.** An input carrying a field
the worker's dataclass does not have yet fails to deserialize. Same rule as the `revise` flag.

The second half is built too, and it is the half a person actually sees. A cancelled check and a
check that found a gap were producing one sentence, and it was the alarming one — a run whose work
was complete and correct read as having FAILED its completeness check. `is_activity_timeout` tells
them apart (structured cause first, message fallback — the same shape as `is_merge_conflict`), and
the timeout wording now says in words that it ran out of its own budget **rather than finding
anything missing**. On a capability whose entire promise is that nothing dispatched vanishes
silently, a false alarm about that promise is the most expensive one available.

---

#### 9.26.C The baseline document published four times for one audit — BUILT, 31 August

**What it is.** Every audit publishes an **Accessibility baseline** — the document a client is
actually shown.

**What went wrong.** Four versions, one audit, inside two minutes: v1 12:02:12, v2 12:02:36,
v3 12:03:12, v4 12:04:14.

**Why the report did not do this.** `report.publish_report` is keyed to its capture and *updates*
in place — there is exactly one report artifact, correctly. `baseline_report.publish_baseline`
deliberately creates the **next version** each time (`supersedes`), so that two audits of one
project can be compared. Each behaviour is right on its own. Together with a closing sequence that
runs more than once, the report absorbs the repeat and the baseline stacks.

**Cause — two of the four publishers are now named; the other two are not.** Tracing 9.26.B turned
up the mechanism: for `a11y_judge`, **`verify_writes` itself publishes the merged report and closes
the audit**, and when it was cancelled at five minutes `fail_run` → `close_unfinished_ai_pass`
**published again**. That is two. A Temporal cancellation stops the *activity*, not the worker
thread already running inside it, so the cancelled publish very likely finished anyway — but
**that is inference, not a reading**, and it does not by itself account for four. The remaining
calls are **NOT VERIFIED** and are not written here as though they were.

**What it means.** Cosmetic, and misleading in a way that matters to a client-facing artefact: the
version history says this project was baselined four times today when it was baselined once.

**The fix.** In `publish_baseline`, when the newest existing baseline already carries
`external_ref.audit == this audit's id` **and** the same content hash, update that row instead of
superseding it. A genuinely new audit still produces a new version; one audit closing repeatedly
no longer does. Fix 9.26.B as well and this stops being reachable — but the guard is worth having
regardless, because "the closing path ran twice" is a recurring shape (§9.25.1).

---

#### 9.26.D The incomplete-audit banner under-reports what was never checked ⭐ — BUILT, 31 August

**What it is.** Two places on the audit screen say how much was left unchecked. The team spotted
them disagreeing:

- the amber banner: *"268 elements were left for a second pass"*
- the **Past audits** card, right beside it: *"269 elements were never looked at"*

**Which is right: 269.** Verified against the database rather than reasoned about:

| Source | Count | What it is |
|---|---|---|
| `ai_pass.deferred_distinct` | 268 | the dispatch reached its 800 limit and stopped short |
| `ai_pass.filed_unjudged` | 0 | nothing was written off — the §9.25 fix holding |
| the judge run's `outputs.a11y_unanswered` | **1** | element `ad26a8b6…`, handed to the judge and never reported on |
| **total, `baseline.unanswered_counts`** | **269** | |

That one element was filed `uncertain` by `verify_judgment_completeness` and recorded on the run,
which is exactly the mechanism built in §9.3 to keep *"nothing looked at this"* distinguishable
from *"a check looked and could not decide"*. **The "Check the rest" button is already correct**:
`unanswered_for_capture` was run directly and returns **269**, including that element.

**So the banner is the wrong one.** Its sentence is `ai_pass.reason` — a string composed at
**dispatch** time, when the only thing that could be known was the cap. It cannot know that the
judge would later fail to report on an element, so it can only ever under-count.

**What it means.** The prominent, reassuring number is the wrong one, and the small print beside
it is right. This is precisely the failure `_incomplete_lines` was written against, in its own
words: *two counts of one thing is how this capability spent 21 August telling a team six elements
were outstanding while the code that would ask about them said none were.* It says so and then
does it, one screen over.

**The fix.** The banner renders its **count** from `baseline.unanswered_counts` — the same single
source the button, the baseline document and the Past audits card already use — and keeps
`ai_pass.reason` only as the *explanation* of why work was deferred, never as the number. One
count, one source, two sentences:

> **269 elements were captured and never checked.** This run reached its limit of 800, so 268 were
> left for a second pass, and 1 more was sent to the judge and never reported on. Nothing was
> skipped — asking again is the only thing that answers them.

**Proof it works:** a test with a non-empty `a11y_unanswered` on the judge run asserting the
banner count equals `unanswered_counts`, not `deferred_distinct`.

**BUILT, 31 August.** `unaskedNote` takes its count from `audit.unanswered` — the field the row
already carried, computed by `baseline.unanswered_counts`, which is what the button, the Past
audits card and the baseline document all read. `deferred_distinct` survives only as the fallback
for an audit closed before `unanswered` was ever computed for it, never as a second opinion when
both are present.

**And the two halves are now said separately when they differ**, which the sketch above already
had right: "269 elements were captured and never checked. This run reached its limit, so 268 were
left for a second pass, and 1 more was sent to the check and never reported on." The limit
explains the 268 it explains and does not pretend to explain the one it does not. Tested with the
real 31 August numbers.

---

#### 9.26.E The machine holding a JUDGING pass died, and nothing said so ⭐⭐ — BUILT, 31 August

**How this was found.** Not a thought experiment. During the second pass the operator's **Windows
machine restarted itself** — the Docker stack went down and the companion was killed mid-judging.

**MEASURED, after the stack came back up:**

```
last verdict written    13:04:11     (898 total — 98 of the 269 done)
last companion heartbeat 13:04:21
last claim renewal       13:04:21
state 25 minutes later   audit  = judging        run = running
                         dispatch = claimed      takeover_flag = False
                         Temporal workflow = RUNNING, still waiting
```

**What survived, and it is worth saying first.** Nothing was lost. All 898 verdicts are permanent
rows; the capture is untouched; `filed_unjudged` is still 0; the remote Temporal workflow never
noticed the local machine had gone. The platform's durability held exactly as designed.

**What is wrong — two things, and the first is the serious one.**

**E1 · A judging audit whose machine is gone goes on saying it is working.** For 25 minutes the
screen said *judging*, the run said *running*, and nothing anywhere said the companion had been
dead since 13:04. There is no signal at all until the two-hour report deadline (§9.26.A) fires at
~14:45 and raises a takeover flag — **101 minutes after the machine died.**

The capture phase already has exactly this protection and has had it since 21 August: §9.5 built
`abandon_stale_audits` precisely so that *"an audit captured by a machine this server cannot see"*
stops claiming to be visiting pages once the claim lease expires. **The judging phase never got
the same treatment.** The claim lease is already stale here — 15 minutes, expired at 13:19:21 —
so the fact is available and simply is not acted on.

**The team then sharpened this, and their observation is worse than the version above.** The
platform does not merely *have* the fact somewhere. **It is already on the screen, twice, in the
same viewport as the panel that contradicts it:**

```
header badge   ●  Companion: Offline
sidebar badge  ●  Companion: Offline
the panel between them:
   "Checking the rest of this audit"          ●  Checking the rest
   "99 of 269  ELEMENTS JUDGED — the AI half, in progress"
   "You can leave this page. This carries on and the result appears under Past audits."
```

**Three separate false statements, on one screen, next to two badges that say why they are
false.** Nothing is in progress; nothing carries on; the result will not appear. A user reading
this leaves the page and comes back to an audit that has not moved.

Two things make it worse than an ordinary stale-UI bug:

- **the counter is presented as live and carries no timestamp.** "99 of 269, in progress" looks
  identical whether the last verdict landed one second ago or twenty-five minutes ago. The one
  piece of information that would have made this obvious — *when* the 99th answer arrived — is the
  one thing not shown;
- **it is the same mistake this document already records the observer making** (§7.3 of
  `Audit_Live_Check_Reasoning.md`): reading a status field as liveness instead of the newest
  verdict's timestamp. The screen does exactly what the watcher did before it was corrected.

**The fix, now in two independent halves — the second one is nearly free.**

1. **Server side.** Extend the sweep the capture phase already uses to audits in `judging`: when
   the judge run's claim has been stale past `CLAIM_LEASE` and the run is still `running`, say so
   on the audit — *"the machine that was checking this stopped responding N minutes ago"* — with
   the two honest choices beside it (restart the companion and it picks the work back up, or close
   the audit now and ask again later). **Do not auto-fail it.** A laptop that slept can come back,
   which is the whole reasoning behind the soft takeover in §9.26.A; the defect is the silence,
   not the waiting.

2. **UI side.** When the audit reads stalled the panel must stop claiming progress: no live dot,
   no *"in progress"*, and above all not *"You can leave this page."* Show the count as **last
   known** with the time it was last known beside it. **A number with a timestamp cannot lie
   about being live.** And it must say the JUDGING truth, not the capture's: every verdict is
   kept, no page is visited again, and starting the machine carries on from here — telling a
   half-judged capture that it "will be closed as failed" and offering a fresh audit would throw
   away an hour of judging that is already paid for and already correct.

   **…and the same audit's ROW, which the team caught the moment the panel was fixed.** The list
   under *Past audits* draws its badge from `statusLabel`, which knew about the status and not
   about the stall — so the corrected panel sat directly above a live blue **Checking the rest**
   badge for the same audit. One audit, two answers, one screen. `statusLabel` and `auditBadge`
   now read `stalled` **first**, before the status word, because it contradicts it: a row in a
   list is exactly where somebody scans for what still needs attention, and it must not be the
   reassuring one. This also fixes the same latent bug for a stalled CAPTURE, whose row has been
   saying *Visiting pages* since the flag existed.

**One number on that screen that is NOT a bug, checked so nobody chases it.** The panel says
**99 of 269** while the database holds **898** verdict rows against the first pass's 800 — a
difference of 98, not 99. Both are right and they count different things: one of the 269 is the
element the first pass filed `uncertain` (§9.26.D), so answering it **updated** an existing row
instead of inserting a new one. Verified directly — of this run's 269 dispatched hashes, 99 now
carry a verdict. It is also why the finished audit should total **1,068** distinct answers and not
1,069.

**E2 · The recovery re-does work that is already done.** The claim lease means a restarted
companion **re-claims this very run** and re-runs the phase. But the agent starts a fresh session
and `judge.batch_for_run` pages from `start=0` with no knowledge of which elements already carry a
verdict — so it re-judges **all 269**, including the **98 already answered**.

Not corrupting: `record_verdict` is idempotent and the second answer simply overwrites the first.
But it is **36% of this pass burned on the user's own Claude subscription re-deciding questions
whose answers are already in the database** — and on a bigger audit interrupted later, that
fraction is worse.

**The fix, with its constraint named.** A resumed judging run should be handed the elements that
are still **unanswered by this run**, not the whole batch. The constraint that makes this less
trivial than it looks: `total_elements` is the judge's own contract — *every dispatched element
gets exactly one verdict* — so it must be recomputed for the resumed set rather than left
describing the original dispatch, or the judge will believe it has failed to finish. And the
filter must key on *this run's* verdicts, not on any verdict, so that an element deliberately
filed `uncertain` by an earlier pass is not quietly skipped.

**One thing that worked, and is worth recording because it is the first time.** The five-minute
stall alarm fired, and this is its **first true positive** — every earlier firing was the alarm
measuring the wrong thing (§7.2, §7.3 of `Audit_Live_Check_Reasoning.md`). Measured from the later
of *the newest verdict* or *this pass's start*, it named a genuinely dead judge within five
minutes, against a platform that would not have said anything for another hour and a half.

---

#### 9.26.F A parked judging run cannot be recovered, and the screen tells the user the wrong thing ⭐⭐ — BUILT, 31 August

**The team's question, and it is the right one:** *the run had to be taken over by hand — but in
real time a user does not know that. Does Fix A close it?*

**No. Fix A does not close it, and E1 as shipped this afternoon made one half of it worse.**

**What happened.** The machine died at 13:04 with 99 of 269 judged. At **14:45:28** — two hours
after dispatch — the report deadline fired and parked the run `stalled`. The re-claim rule
(`runner_views.py:499`) offers a stale claim back only when the run is `PENDING` or `RUNNING`:

```python
if (st == "claimed" and claimed_at and claimed_at < stale_before
        and cand.status in (Run.Status.PENDING, Run.Status.RUNNING)):
```

`STALLED` is not in that tuple. **So the moment the deadline fires, the judging pass becomes
unrecoverable by the claim lease — permanently.** Reconnecting the companion does nothing. The
only way out is a human takeover from the run-recovery screen, which is a page a person auditing
their website has no reason to have ever opened.

**Why Fix A does not close it.** A longer, size-scaled deadline makes the timeout fire less often.
It does not change what happens when it *does* fire, and a machine that dies at hour six of a
five-and-a-half-hour budget lands in exactly this state. **A makes this rarer; it does not make it
recoverable.**

**And it silently disarms 9.26.E2.** The "hand a resumed run only what it has not answered" fix can
only ever run if the run is **re-claimed** — which is possible only inside the deadline window.
After the park, E2 is unreachable. Fixing A is what makes E2 reachable at all; that is a better
argument for A than anything written under it.

**The half that is ours, and it is hours old.** 9.26.E1's panel says:

> Start the machine again and it carries on from where it stopped — nothing here needs to be
> re-run by hand.

**That was true when it was written and is false once the run is parked.** It was measured against
a run that was still `running` and therefore still re-claimable. In the parked state the sentence
sends a person to restart a machine that will sit there doing nothing, and offers them no other
route. A wrong instruction is worse than no instruction, and this one is mine.

**The fix — the audit screen owns the whole recovery, because the audit is what the user
understands.** Two states, told apart, each with the true sentence:

| The judge run is | The screen says | The action |
|---|---|---|
| `running` (still re-claimable) | "Start the machine again and it carries on from where it stopped." | none needed — it resumes itself |
| `stalled` (parked past the deadline) | "The machine did not come back in time, so this audit is waiting on you." | one button: **Finish this audit** |

**Finish this audit** does exactly what the run-recovery screen's takeover does — ends the parked
run, files what was never answered, publishes the report and baseline, closes the audit — after
which **Check the rest** appears on the row and offers the remainder. The user never learns the
words "parked run", "takeover" or "workflow", and never leaves the page they started on.

Mechanically small: the audits payload already carries `stalled`; it needs one more field saying
whether the judge run is parked, and the panel needs one button wired to the existing take-over
endpoint.

**The alternative, and why it is not the recommendation.** The re-claim rule could simply accept
`STALLED` for judging runs, and the work would resume with no human involved. It is fewer moving
parts — and it spends the user's own Claude subscription on a decision nobody asked them about.
The team has already ruled on this shape once, rejecting an audit that continues itself: *"that is
not the platform's job — what if he adds 30 routes and all his Claude usage burns?"* The same
reasoning applies here. **Offer the button; do not press it for them.**

**BUILT, 31 August — exactly as specified, including the alternative that was rejected.**
`baseline.parked_judge_runs` returns `{audit_id: judge_run_id}` for judging audits whose run is
`STALLED`, and the audits payload carries it as `parked_run_id` — null on every audit that can
still recover, which is what makes its presence the signal. The re-claim rule in
`runner_views.py` was **not** touched: a parked pass still does not resume itself, and the reason
is the team's own ruling about somebody's Claude usage, not an implementation limit.

The panel now has three states rather than two, and the parked one replaces the wrong instruction
instead of merely removing it — "Restarting the machine on its own will not pick this up" — beside
one button, **Finish this audit**, which makes the same `take-over` call the run console makes.
One recovery path, two places it is offered. Tested for the wording in both directions and for
the words the person must never meet: *take over*, *parked*, *workflow* are all asserted absent
from the screen.

**And this is what makes 9.26.E2 reachable at all.** The "hand a resumed run only what it has not
answered" fix can only run if the run is re-claimed, which is only possible inside the deadline
window — so it was unreachable after a park. A's longer, size-scaled deadline is what widens that
window, and F is what gives the person a way out when it closes anyway.

---

#### 9.26.G Concurrent closes overwrote the record of what was never looked at ⭐⭐ — BUILT, 31 August

**Found by watching the takeover close the audit**, 15:32–15:36.

The takeover worked: the run ended, 170 unanswered elements were filed for review, the report and
baseline published, the audit reached `complete` with **1,068 verdicts** — the exact total
predicted from 800 + 268 (9.26.D's arithmetic, confirmed).

**But "Check the rest" now offers 65, not 170.**

**What happened.** The closing path ran **three times** (`run.failed` at 15:32:19, 15:33:20,
15:34:22 — the same repeated-close shape as 9.26.C). `verify_judgment_completeness` files every
unanswered element as `uncertain` and then records the list on the run under `a11y_unanswered`,
**replacing** whatever was there:

```python
run.outputs = {**(run.outputs or {}), UNANSWERED_KEY: sorted(set(content_hashes))}
```

The attempts overlapped. Verdicts were still being written at 15:32:42 (932), 15:33:12 (988),
15:33:50 (1,055) while later attempts were already counting. So a **later attempt saw fewer
elements still missing** — because an earlier attempt had just filed them — and its shorter list
overwrote the true one. 170 became 65.

**Why that matters more than a wrong number.** `_remember_unanswered` exists for exactly one
purpose, in its own words: the moment the fallback verdicts are stored, *"a check looked at this
and could not decide"* and *"nothing ever looked at this"* become the same row. **The list on the
run is the only thing that tells them apart** — and the overwrite destroyed that distinction for
105 elements. They now read as somebody's job in the review queue when they are actually work that
never happened.

**Nothing is lost, and this is the part that makes the fix easy.** Every one of the 170 carries the
platform's own reason text, and it is unambiguous:

```
uncertain rows on this run                : 170
   carrying the platform's NOT_JUDGED text: 170
   authored by the judge                  :   0
```

Across the whole project: 185 uncertain, of which 170 are the platform's. **The two kinds are
still perfectly separable** — just not by the field the code currently reads.

**The fix — two halves, either of which closes it alone; do both.**

1. **Never shrink the record — BUILT, 31 August.** `_remember_unanswered` now UNIONs with what is
   already there instead of replacing it. An element recorded as never-looked-at does not stop
   being that because a later pass over the same run found it already filed; **a later, shorter
   reading is never a correction.** One line, and it makes the write safe under the concurrency
   that 9.26.C proves is real. Tested for the overlap itself (a full list then a partial re-count
   keeps the full set) and for the thing it shares its field with (a failed run's `error` survives
   the write). The safety it rests on — that keeping a hash is not the same as offering it back —
   is `unanswered_for_capture`'s own last step and is proven where the captures live.
2. **Do not depend on the record alone — BUILT, 31 August.** `unanswered_for_capture` now also
   recognises an `uncertain` whose evidence is the platform's own `NOT_JUDGED` text — that string
   is written by the platform and never by an agent, so it is a reliable marker of *work that did
   not happen*. The answer is derivable from the verdicts themselves rather than from a
   side-record that can be lost.

   **Scoped to this run**, deliberately: a `NOT_JUDGED` uncertain belonging to an earlier run of
   the same project is that run's history, and dragging it in would re-offer elements this capture
   has since dealt with.

   **Proved by deleting the record outright** — a harsher test than the partial overwrite that
   actually happened — and asserting the answer does not move. And guarded in the other direction
   by the test that matters more: this reading is one keystroke from "every `uncertain`", which
   would hand the review queue's own contents back to the machine and recycle a person's job list.
   A judge's own `uncertain`, sitting beside the fallbacks with only its evidence text to tell
   them apart, is asserted **not** offered while the fallbacks beside it are.

**Recovery for the audit already in this state — DONE, 31 August, on the team's instruction.**
`a11y_unanswered` on run `c454d5f0` was rewritten to the 170 hashes whose verdict is `uncertain`
and whose evidence is `NOT_JUDGED` — one named run, nothing else touched, and exactly what fix 2
would compute:

```
BEFORE  a11y_unanswered: 65    Check-the-rest offers: 65
        platform-filed never-looked-at: 170
        is the old list a subset of it? True      ← the overwrite theory, confirmed
AFTER   a11y_unanswered: 170   Check-the-rest offers: 170   badge: 170
```

The old list being a strict **subset** is the proof: the shorter reading was a real but partial
count taken mid-filing, not a different set. Nothing was invented by the repair.

**The hazard is not gone until fix 1 lands.** The next pass writes its own record, so if its close
runs more than once — which is the norm, not the exception (9.26.C) — the same overwrite can
happen again to the new run.

Without it, the 105 are recoverable only by a **fresh audit**: `dispatch._cached` never serves an
`uncertain` back, so a new audit re-asks them. They are not stranded for ever — just not offered by
this audit's button.

---

#### 9.26.H Two screens describing the wrong thing in the right words — BUILT, 31 August

Found in the end-to-end cross-check after the audit closed. Neither is a counting error; **both
numbers were right and both captions were wrong**, which is the harder kind to spot because the
only symptom is a reader concluding the platform contradicts itself.

**H1 · "4 awaiting a person" beside a review queue of 19.** The team asked which number was wrong.
Neither. They count different things and can never match:

| | Unit | Question |
|---|---|---|
| review queue · **19** | *elements* | a check reached this one and could not settle it |
| conformance tile · **4** | *criteria* | the platform will not suggest a conformance level at all |

The 4 are **1.2.2 Captions, 2.1.1 Keyboard, 2.2.1 Timing Adjustable, 2.2.2 Pause Stop Hide** — each
with **0 open failures**, reached on all 94 routes by the **rule scanner only**. The platform
declines to suggest a level because *"axe found nothing"* is not evidence that keyboard operation
works. Meanwhile all five criteria that DO have queue items carry a suggested level, so **not one
of the 19 is among the 4** — the overlap is zero.

The tile's sub-line read *"A check looked and could not decide"* — **the review queue's own
sentence**, on the conformance statement's number. Now: **"Need your decision · Criteria the
platform will not suggest a level for."**

**H2 · A low-confidence PASS described as though nothing had been decided.** The review queue holds
two shapes, and until now said the same thing about both:

```
15 × uncertain   confidence 0.50–0.60   a check looked and could not decide
 4 × pass        confidence 0.75–0.80   the check DID decide; it was under this check's bar
```

The banner interpolated the verdict label into one sentence, so a low-confidence pass rendered
**"The check gave not sure · 75%"** — broken English that also buried the fact the reviewer most
needs: *the check said this element is fine, and how sure it was.* The body went on to say the
platform *"did not act on it either way"*, true of the routing and misleading about the check.

Now the two shapes get their own sentences: *"The check gave no verdict"* for an `uncertain`, and
*"The check said this is fine, and was 75% sure — that is under the confidence this check needs
before the platform will act on its own, so it is asking you instead."* Tested both ways.

**Why these are the same bug as 9.26.E1 and 9.26.D.** Four separate screens today said something
true of a neighbouring concept and false of the one in front of them. The pattern is worth naming
because it is cheap to keep making: **a number is copied from one place and its explanation from
another.** The check that catches it is asking, of every caption, *what exactly is being counted,
and in what unit* — which is what found all four.

---

### 9.27 Scoring the completed audit — 1 September ⭐⭐ (BUILT)

**The first accuracy baseline this capability has ever had.** Scored against audit `ee977648`
(Meridian Library v1.4.0, 94 pages, 1,068 distinct questions) and locked. Two defects had to be
fixed to get there, and **both were in the harness, not in the product** — the checkers were
already right; the scorecard was describing them wrongly.

| check | precision | recall | F1 | sample |
|---|---|---|---|---|
| alt | 1.000 | 1.000 | 1.000 | 30 |
| color | 1.000 | 0.938 | 0.968 | 32 |
| label | 1.000 | 1.000 | 1.000 | **40** (20 by the check, 20 by rule) |
| semantics | 1.000 | 0.875 | 0.933 | 31 |
| structure | **0.833** *(contested)* | 1.000 | 0.909 | 30 |

**All five cleared the 30-record floor.** On 31 August none did — only 43 of 173 answer-key
records had received a verdict at all.

---

#### 9.27.A A correct answer, recorded as "nobody looked" ⭐⭐ — BUILT

**What it is.** 2.5.3 asks whether a control's spoken name contains the words printed on it. When
it demonstrably does, that is a string comparison and not an opinion, so the selection rules
settle it and the AI is never asked. Right, and free.

**What went wrong.** Nothing recorded that a decision had been made. `_applies_label` returned a
single boolean for two entirely different situations — *"this criterion does not apply here"* and
*"it applies and is satisfied"* — so a control the platform had correctly cleared was
indistinguishable from one nothing had ever examined. No dispatch, no verdict row, no trace.

**Measured on this audit:** 22 of the 42 labelled 2.5.3 controls. Every one right. Every one
reported by the harness as **NEVER LOOKED AT**, counted as **wrong** in the difficulty band
(`clear: 20/40` for a checker that was 42/42), and excluded from `sample`.

**And it was structural, not a data shortage.** `sample = TP + FP + FN + TN`; the 22 are true
negatives. The dataset pairs every AI-judged failure with a rule-settled pass *by construction* —
that is what makes it a clean pair — so **every new pair adds one to the sample and one to the
ignored pile.** `label` could never have reached 30 no matter how much data was authored.

**The fork, and the team's ruling.** Two honest readings: score *the AI* (the 22 don't belong;
the AI never exercised that restraint) or score *the platform* (a client experiences the
platform's answer, and an answer reached by rule is still correct — and cheaper). **The team
chose the platform reading, with the split printed.** What does not move either way: precision
and recall use neither TN, so `label` reads 1.000 / 1.000 before and after. **Nothing was
inflated** — only whether we are allowed to believe it.

**The fix.** `rules.settled()`, beside the existing `explain()`. Three states where there were
two: *dispatched* · *settled here* · *out of scope*. The scorer reads it **from the platform's own
rule module and never re-implements it** — a second copy would agree with the first by
construction and the comparison would become decoration, the same trap `check_app_version` exists
to avoid. The rule's answer is then scored against the answer key like any other, which is what
keeps it falsifiable.

**It proved that on its first run.** `/account/my-loans#renew-all` — a button reading **"Renew"**
announced as **"Renew all loans"**. The rule says pass: the letter of 2.5.3 is met. The answer key
says an expert should weigh it, because *"Renew"* alone does not warn a sighted user it renews
**everything**. **The rule can compare words; it cannot see a name widening what the button
promised.** Reported as `over-confident … settled by RULE, not by the check — narrow the rule, do
not re-prompt the model`, because the two have different remedies. **Before this change that
record was invisible.**

**One bug introduced and caught in the same session:** the first version counted rule-settled
records *before* the branches that exclude some from the sample, so the printed split described a
different set from the one it was splitting (`19 / 21` for a sample of 40). Counted at the point
of scoring instead: **20 / 20.** Ironically the exact class of mistake the change exists to
remove.

**Proof:** 5 tests, including the invariant `a checker never both asks and answers` — asserted
across every checker, not only `label`, so the next rule that learns to settle something inherits
the guarantee instead of re-deriving it.

---

#### 9.27.B The completeness half weighed the bag instead of reading the list ⭐⭐ — BUILT

**What it is.** The half of the harness the spec says to *"build and trust before any accuracy
figure"*, because it separates *"the check got it wrong"* from *"the check was never shown it"*.

**What went wrong.** It compared **totals**. `RouteCount` held three integers and no identities:

```python
if self.captured < self.expected:   → dropped before capture
elif self.captured > self.expected: → surplus (explicitly NOT a failure)
```

So a page can capture twenty-nine of the wrong things, miss every one of the eleven the answer key
names, and print `ok`. **A packing list checked by weighing the bag.**

**It was doing exactly that on 1 September.** `/help/membership-actions` printed
`expected 11 · captured 29 · judged 29 · ok` on the same run where the accuracy half reported
eleven records on that page as never looked at. **One page, one run, two halves of one tool,
opposite readings — and nothing anywhere noticing they disagreed.**

**The fix.** The names were already there — the key records route, selector and checker for all
173 records, and they were read, discarded, and reduced to a count per page. They are now carried
through and ticked off one at a time; a page reports **which** expected elements never reached
their check. The counts remain for pages the manifest gives a number for without naming anything,
and with no answer key at all this still does what it always did — captured against judged, which
needs no key and works on any run of any application.

**It found four immediately**, and where it found them is the point:

```
/loans/renewals    #renew-tidewater [color]
/newsletter        #newsletter-email [label]
/staff/exports     #open-exports [semantics]
/staff/quick-edit  #save-entry [semantics]
```

**Every one sits on a page the manifest gives no expected count for.** The counting check could
not have found them *even in principle* — there was no number to compare against. And the totals
match the accuracy half's own `NEVER LOOKED AT` lines exactly (1 colour, 1 label, 2 semantics):
**the two halves now agree.**

The page that motivated all this, `/help/membership-actions`, now correctly reads `ok` with
nothing missing — not because the check got weaker but because 9.27.A made it true.

**Consequence to know:** the run now exits **2** (*"something was dropped"*), which was true
before and merely invisible. It blocks nothing; blocking is exit 1.

**Proof:** 6 tests, one of which reconstructs the 11-vs-29 failure with its real numbers and
asserts it no longer passes.

---

#### 9.27.C What the baseline commits us to, and the one figure that is not settled

`baseline.json` holds the accepted figure per checker, `min_sample: 30`, `tolerance: 0.02`. A
later run more than two points below a stored figure prints `SHIPPING IS BLOCKED` and exits 1 —
and **does not overwrite the baseline**, so a regression cannot be cleared by re-running. There is
no CI in this repository: the exit code is a signal to a person, for the day there is one.

**What is blocked is OUR release of a changed prompt, model or selection rule. Never a client's
work, and nothing in the platform reads any of it.**

**`structure` 0.833 is contested and is recorded as such in the results file.** It rests on three
records — `/staff/staffing-plan#rota-week-1/2/3` — where our checker and the answer key's author
genuinely disagree: the tables carry correct `<th scope="col">` column headers, and the shift
names in the first column are `<td>` rather than `<th scope="row">`. Our checker calls that a
1.3.1 breach; the key says the column headers suffice. **Both are defensible readings**, the
golden set is `draft-unadjudicated` throughout, and no code change resolves it — it needs an
expert to rule. It is a **floor, not a ceiling**: whichever way the ruling goes the number can
only move up, so locking it cannot trap us.

**A `--note` flag was added for exactly this.** A figure can be correct and still not settled, and
a number that outlives the reason for it is read three months later as a settled fact. The caveat
travels **in** the results file rather than in somebody's memory of the day it was written.

---

#### 9.27.D Three things this left open

1. **The rota adjudication** — above. Needs a person, not a commit.
2. **Four elements no rule reaches** — the ones 9.27.B found. ~~Same family as §9.25.3's
   class-less container `<div>`.~~ **That reading was wrong on both counts**, and §9.28.A has
   the root cause of each: they have four different owners, only one is a platform gap, and it
   is a gap in what the capture *records* rather than in what the selectors *reach*.
3. **The containment rule cannot see scope-widening** — 9.27.A's `#renew-all`. Now visible and
   scored, which is the precondition for fixing it.

---

### 9.28 Reading the completed audit's review queue — 1 September ⭐⭐ (BUILT)

The team opened the 19 items waiting on a person and read the judge's own words on the *Label in
Name* ones:

> *"this is likely a `<label>` element not provided in this batch… Cannot determine accessible
> name without the full surrounding HTML."*

Then asked the question that decided the outcome: **the audit ran in three passes and we took one
of them over by hand — did our own interference make these, and are we about to call it a bug?**

**It was the right challenge and it changed the answer twice.** Two of the six things first
reported were the observer's own analysis errors, not defects. They are written up in
`Audit_Live_Check_Reasoning.md` §14.2 rather than quietly dropped.

**Where the 19 came from.** Every one traces to pass 1, the run that answered 799 of 800:

```
15  genuine "I could not decide" verdicts   — label 11, colour 2, alt 1, graphics 1
 4  passes at or below the confidence bar   — routed to a person BY DESIGN (triage.py uses <=)
```

Passes 2 and 3 — including the one we abandoned — produced **not one** uncertain verdict between
them. **Our disturbance put nothing in this queue.**

**And the judge is not the problem.** Across the whole audit:

```
953 pass   100 fail   15 uncertain      — 1.4% of 1,068 answers
colour: 512 judged,  2 uncertain (0.4%)
label:   32 judged, 11 uncertain (34%)  ← every one of them a <select>
```

One data-plumbing gap accounts for nearly all the uncertainty there is.

---

#### 9.28.A The judge was never told the accessible name ⭐⭐ — BUILT

**What it is.** WCAG 2.5.3 asks one question: *does the name a screen reader announces contain the
words printed on the control?* The browser computes that name during the capture, deliberately —
never approximated from `aria-label` or the text content, because an approximation makes the two
agree by construction and switches the check off. The platform stores it.

**And then `dispatch._group_by_screen` did not send it.** The judge received the markup, the
picture, the surrounding text and the container outline, and not the one string the criterion is
about. `git log -S accessible_name` on that file across every branch returns nothing: **it had
never been sent, on any run, ever.**

**Why it only shows on dropdowns.** A `<button>`'s name is the word printed on it, and `html`
carries that word — so the judge could answer. A `<select>` is named by a `<label for=…>` that is
a **sibling**, so it is never inside the element's own markup and is recoverable from nothing else
that travels. The split is total:

| | judged | uncertain |
|---|---|---|
| `<button>` | 19 | **0** |
| `<select>` | 13 | **11**, plus 2 low-confidence passes — **none resolved** |

**The fix.** `accessible_name` is carried on `A11yCandidate`, through `to_candidate`, into the
batch, and named in the judge's instructions — with the "I cannot tell without the surrounding
HTML" escape removed for this case, because it stops being true.

**`tag` and `role` were deliberately NOT added.** The judge reads both off `html`; restating them
would change the cache key for no gain. The name is different in kind — computed from the whole
page, recoverable from nothing else.

#### 9.28.B A dropdown's options were being read as its label ⭐ — BUILT

**The rule that decides what reaches the AI had already got this wrong, one step earlier.**
`_visible_text` returns the element's inner text; for a `<select>` that is every option it holds.
So the rule compared

```
announced name   "Home branch"
"visible label"  "Fenner Road Ashcombe North Quay"
```

found no match, concluded *possible mismatch*, and sent it on — to a judge that had not been given
the name either. **Two faults stacked, and fixing either alone leaves dropdowns broken.**

There was never anything to compare. A closed dropdown displays none of its options, and a
dropdown's visible label **is** its accessible name. `VALUE_NOT_LABEL_TAGS` (`select`, `textarea`)
now puts them out of scope — the mirror of the `VALUE_LABEL_INPUT_TYPES` carve-out §9.15 added for
`<input type=submit>`, and for the same reason: **no visible label we can read means no comparison
we can make.** Out of scope is not a pass, and `settled()` reports neither.

**Proved against the stored audit, read-only: 13 of the 19 leave the queue. The other 6 stay, and
every one of them should.**

#### 9.28.C `border-color` was never captured — the same silent loss, a third time ⭐ — BUILT

`STYLE_KEYS` records `border-style`, which says a border **exists** and never what it looks like.
So the third way to colour a thing was invisible, after `background-color` (the first) and
`stroke`/`fill` (§9.23's, the second).

On `/loans/renewals` three status markers sit in adjacent rows of one table. Two are `.dot`,
coloured by `background`; one is a `.ring`, drawn with `border: 3px solid`. **The two were offered
to the colour rule and the third was not** — `_applies_color` looked for a painted background,
found none on an empty span, and concluded there was no colour here to ask about.

Both `STYLE_KEYS` lists now carry `border-color` and `outline-color`, and a painted border counts
as carrying colour — **but only when there is nothing else**, no text and no background. That
narrowness is measured, not cautious: the reasoning already recorded on `_has_second_cue`
establishes that parents almost never have a border to compare against, so treating any painted
border as a difference would make every input and card on the page a colour candidate and spend
the judgment budget on chrome.

#### 9.28.D An icon's parent was never described ⭐ — BUILT

The bookmark icon on `/events/calendar` is the `alt` uncertain **and** the `graphics` uncertain —
one element, both of the remaining non-colour uncertains in the entire audit. Both criteria turn
on **what the icon sits inside**: a link whose only content is this icon (so `alt=""` hides where
it goes) or an already-labelled container (so `alt=""` is right).

`surroundingText` sends the parent's **words**. An icon-only link has none — correctly, and
uselessly. The capture now carries the parent's `tag`, `role`, `href` and text.

#### 9.28.E Two guards, because this class of loss is silent by design ⭐⭐ — BUILT

The companion's own comment says it out loud: *a missing style key is not an error anywhere.*
That is why 9.28.C is the third occurrence and why 9.28.A survived from the first day.

- **`test_the_batch_carries_every_field_a_check_needs`** — every field of the candidate contract
  must be in the batch the judge receives. The sibling of the test §9.23 added after `structure`
  was dropped one step before storage, and written for the same reason: *nothing failed, because
  the two lists had never been compared.*
- **`test_the_companion_captures_exactly_the_styles_the_rules_read`** — the two `STYLE_KEYS`
  lists must be **identical**, not merely overlapping.

#### 9.28.F What this costs, and it is not a footnote

**Every judgment cached before today is invalidated.** `accessible_name` and `parent` are inputs
the judge now reads, so both are in the cache key — the same argument §9.19 made for `structure`.
A verdict reached without ever seeing a field must not be served as a hit, because a cache hit is
a promise that nothing the judge looks at has moved.

**The next audit therefore re-judges everything.** Pass 1 of the 31 August run cost **$33.12** for
800 elements. Recorded here so the number is a decision and not a surprise.

#### 9.28.G Withdrawn — the "106 silently closed findings"

**Reported as a serious defect, investigated, and it is not one.** The full correction is in
§14.2; in short: 104 distinct elements filed as *"nothing looked at this"* when we abandoned pass
2 were **all re-judged by pass 3 and all passed**, so the placeholders were correctly closed. The
guard drafted for `findings.record_run_findings` was written and **reverted** — it fixed nothing
and would have stopped a genuinely deleted element from ever resolving.

**`Audit_Live_Check_Reasoning.md` §6.11 had recorded this correctly on the day** — *"114 of those
133 were never work for a person at all"*. The document was right and was not read.

#### 9.28.H Still open after this

1. **Not provable until a fresh capture.** 9.28.A, C and D change what is *collected*; the August
   bundles cannot carry fields nothing asked for. The rules are covered by tests; the end-to-end
   proof waits.
2. **`#open-exports`** — should the `semantics` rule reach a link styled as a button? A judgement
   call the answer key's own author flags both ways. Needs a decision, not a fix.
3. **`#newsletter-email`** — marked *"Disputed — flagged for the expert"* by its author. An input
   labelled only by its placeholder.
4. **Screenshot paging** — the batch is served per screen (25) while images are served as one
   run-wide list (4 a call), so a judge on screen 9 must page past screens 1–8. The shape mismatch
   is real; **the damage first attributed to it was a miscount** (§14.2). Pass 1 worked through 73
   screens and 800 elements, so it is survivable. Recorded, not fixed.
5. **The rota adjudication** and **the `#renew-all` containment limit** — unchanged from §9.27.D.


### 9.29 Re-reading every fix, oldest to newest — 1 September 🔬 (REVIEW — NOTHING BUILT)

Before the next full-scale audit the team asked for something this plan has never had: **every
correction made since 12 August, re-checked against the code as it stands** rather than against
the commit message written on the day. One straight line of 149 commits from `47578d0` to
`41458ae` — `web-accessibility-build` turned out to be wholly contained in `Eval-accuracy`, so
there is no second history to reconcile. 200 corrections catalogued.

**The result is good, and should be read precisely: all 200 are present at HEAD.** None was
reverted and none was undone by a later change. Eleven needed a second fix; two were withdrawn as
not defects (§9.28.G, and §14.2 of `Audit_Live_Check_Reasoning.md`).

What follows is only what the review found that this plan did not already say.

#### 9.29.A The red tests are three causes, not one — §9.25's note is corrected

> **Corrected the same day — see §9.30.B and §9.30.D.** Two things below are wrong. The count is
> **21, not 16**: this was measured across eleven a11y test files and there are thirty-three, and
> the five that were missed are four drift guards all naming the same fact. And the three
> conformance failures do **not** come from a fixture with no ownership registry — the registry is
> loaded; the fixture records a *rule-scanner* pass for a criterion the registry gives to the *AI*,
> which is the guard working precisely as designed. The shape of the paragraph below is right and
> its two specifics are not, which is the habit it is itself about.

§9.25 records **14 backend tests failing, "all of them" tracing to the `graphics` / 1.4.11 checker
added on 27 August**. Re-measured today across eleven a11y test files, the figure is **16, and
they have three separate causes**:

```
11   the graphics widening (27 Aug)   capture 5, report 6
 3   the conformance guard (27 Aug)   conformance 2, findings 1
 2   the selection corpus             no 1.4.11 rows — see 9.29.B
```

The eleven are what §9.25 described, and they are stale assertions rather than defects: an image
is now legitimately claimed by **both** `alt` and `graphics`, deliberately and for different
questions (§9.25 and the `graphics` docstring), so an assertion expecting one checker sees two.
The report failures name the extra row outright — `1.4.11 /checkout img.hero`.

**The three are not the graphics checker at all.** They are stale assertions against the
conformance guard of §9.26 — the one that stopped a narrow rule pass claiming a criterion it
cannot prove. Those tests build a fixture with no ownership registry loaded, so `suggest()`
correctly answers nothing where they still expect `supports`:

```
AssertionError: assert 'not_evaluated' == 'supports'
AssertionError: assert None == 'supports'
```

That is the guard working exactly as designed — *an unknown owner claims nothing, and those rows
go to a reviewer* — and the tests predate it. **Neither group is a product defect.**

The correction worth having is not the number. It is that **one cause was recorded for a set that
had three**, which is the habit §14.2.3 names: taking the explanation from the nearest place
rather than from the place that answers the question.

#### 9.29.B 1.4.11 has no evidence of any kind — the one item to decide before the next audit ⭐⭐

> **Decided and acted on the same day — see §9.30.A.** The team's answer was **hold it back**: the
> claim on 1.4.11 is withdrawn until the ownership registry, the corpus and the answer key can
> support it, and the check itself is kept intact and idle rather than deleted. Everything below
> still stands as the description of the gap; what changed is that the platform no longer claims
> the criterion while the gap is open. §9.30.C is the part of that which nearly went wrong.

Three separate gaps, all pointing the same way. Each verified today rather than inferred.

1. **No selection-corpus rows.** §9.22's corpus of forty-six failure shapes holds 1.1.1, 1.3.1,
   1.4.1, 2.5.3 and 4.1.2 — and nothing for 1.4.11. So both of its assertions fail for that
   criterion: it owns no recorded failure shape, and no recorded shape it must leave alone.
   **Red since 27 August.**
2. **No `check_graphics` on the capability.** `integrations.capabilities.A11yAI` and the built-in
   connector expose `check_alt`, `check_semantics`, `check_structure`, `check_color`,
   `check_label` and `check_journey` — **five element checks, not six**. An **audit is
   unaffected**, because the dispatch path reads the checker list from the rules; what cannot be
   done is asking the capability directly about 1.4.11.
3. **No answer-key records.** The scorer already carries the aliases — `non-text-contrast` and
   `graphic-contrast` map to `graphics` — and the golden set holds alt 32, color 35, label 42,
   semantics 33, structure 31, and graphics **0**. The golden README already says why, and the
   rule it sets for closing it stands: the labeller must not be the person who wrote the checker.

**Why this needs a decision rather than a patch.** §9.22 exists precisely to stop a check being
filed under a criterion it does not cover — it is the guard that caught the 1.3.1 gap, and writing
corpus rows to silence it without settling the scope question would defeat the thing it is for. It
has now been reporting this condition for five days and has been read as part of the background
red, which is the exact failure §9.24 recorded once already: *a test whose whole purpose is to
notice a change, red because of the change it was meant to notice, and passed over.*

**Nothing here says `graphics` is wrong.** It says we have no evidence either way, and two of the
three gaps are things the platform already knows how to state.

#### 9.29.C One frontend test passes only in UTC

`frontend/src/features/a11y/audit.test.tsx` — *"a judging pass whose machine went away stops
claiming to be in progress"* — asserts `getByText(/13:04|1:04/)` against a stubbed
`stalled_since` of `2026-08-31T13:04:11Z`. The component renders that through
`toLocaleString(undefined, …)`, which is deliberately the **viewer's** local time. So the test
passes on a machine in UTC and fails everywhere else; on IST the screen correctly reads 18:34.

The feature is right and is the point of §9.26.E — *a count with no time beside it reads
identically one second and half an hour after the machine died* — and the time is being shown.
**The test is the defect**, and it is the same class as the harness default fixed in §9.25.5's
sibling change: a check that only works on the machine of whoever wrote it.

#### 9.29.D One thing the review itself got wrong, recorded rather than dropped

The review's first pass carried a fourth item: that `structure` findings may not be scorable
against the answer key at all — flagged in the commit that widened the checker count on 25 August,
and never ruled on. **It is not open. It was closed on 28 August, and nothing recorded that it had
been closed.**

`CHECKER_ALIASES` carries `fake-structure` and `real-structure` → `structure`; the golden set holds
31 structure records; and the baseline locked at 09:00 on 1 September scores it — sample 30,
recall 1.0, precision 0.833, which is the contested figure of §9.27.C.

**The error was checking whether a *ruling* had been recorded, finding none, and concluding the
question was still open** — without asking whether the situation had changed underneath it. It is
§14.2.3 one document further along, and it is written here for the same reason that section
exists: a review that keeps only the findings which survived is not evidence of anything.

---

---

### What was deliberately NOT built — 24 August

**An audit that continues itself until nothing is left.** Proposed, and the team rejected it:
*"that is not the platform's job — what if he adds 30 routes and all his Claude usage burns?"*
They are right. Continuing costs the user's own subscription, and whether to spend it is theirs
to decide. §9.21 removes the reason a normal site ever stops; if a genuinely large one does, it
stops and says so, and the person chooses.

**The dev's missing structure check.** His audit selected zero containers although his capture
offered them and the live rules select them — verified by running his exact table through the
code. His platform was on current code and ingest ran 2.4 seconds before dispatch, so no restart
came between. Every link says it should have worked. The remaining explanations are all about
his working copy rather than our code, and no fix was invented for a defect that has not been
shown to exist.


### 9.30 Clearing everything before the next audit — 1 September ✅ (BUILT)

> **Read with §9.30.A. The hold described there lasted part of one day.** The team asked whether
> the checker actually worked; it does, and the evidence is in §9.31. `graphics` runs
> again, the ownership registry now agrees it is AI-owned, and the two things missing since
> 27 August — the capability method and the corpus rows — are built. What stays true from
> §9.30 is §9.30.C: the guard that stops a future hold handing a criterion to the wrong half.

§9.29 was a review and built nothing. The team's answer to it was short: *before I click Run audit,
everything has to be fixed and cleared.* This is that work. **Route B was chosen for 1.4.11** — hold
the claim back rather than complete it — and the investigation that followed showed that choice was
better founded than the case put for it.

**The state before: 21 backend tests red and 1 frontend, not 16 and 1.** §9.29.A measured eleven
a11y test files. There are thirty-three. **Sweeping all of them found five more**, and those five
are the subject of §9.30.B.

**The state after: 1,747 a11y backend tests passing, 0 failing; 416 of 416 frontend passing.**
Plus the scorer at 47/47, and 126 tests across the capability, WCAG-gate, integrations-admin,
phase-4 acceptance and build-activity suites, all green.

#### 9.30.A The claim on 1.4.11 is withdrawn, and the check is kept

`ownership.json` records **1.4.11 as owned by `rule`**. `A11Y_CHECKER_CRITERIA` is the map of what
the **AI** owns. When `graphics` was added on 27 August it put 1.4.11 into that map, and the case
for doing so was argued in a code comment — *"the registry said so itself… and then recorded the
owner as `rule` anyway"* — while the registry itself was never changed to agree. Five guards said so
immediately and went on saying it (§9.30.B).

So the entry moved rather than being deleted:

* `A11Y_HELD_BACK_CRITERIA` in `integrations/types.py` holds `{"graphics": ("1.4.11",)}`, with the
  reason, what is lost, and the three things that must be true before it returns;
* `HELD_BACK_SELECTION_RULES` in `checkers/rules.py` holds the selection rule itself — its `covers`
  and `skips` prose intact, so the scope somebody argued for is readable rather than reconstructable
  from a git log;
* `describe_rules()` prints it with **HELD BACK, NOT RUNNING** and a line saying nothing it would
  have found is reported, because a reviewer has to be able to tell what runs from what does not;
* `A11Y_ALL_CHECKER_CRITERIA` — the *validation* union, which nothing selects from — still contains
  it, so a verdict recorded before the pause can still be validated and a workspace that had tuned
  its confidence threshold is not told the check "does not exist" (the QA-20 error, avoided).

**Sixteen of the twenty-one red tests went green on this change alone, with no assertion touched.**
That is the strongest evidence that the hold is the right reading rather than a convenient one:
sixteen independent guards were objecting to one thing.

Bringing it back is three moves in two files, listed in the code — **after** the registry is changed
to agree, which is the step that was skipped last time.

#### 9.30.B Five red tests nobody had counted, all saying the same thing

| Test | What it had been saying since 27 August |
|---|---|
| `test_the_capability_offers_a_check_for_every_checker_in_the_registry` | there is no `check_graphics` — a checker selectable and dispatchable with nowhere to put its verdict |
| `test_every_checker_maps_to_a_real_wcag_criterion` | the checker map is not the five the POC shipped |
| `test_the_poc_checkers_and_the_registry_cannot_drift_apart` | the map claims 1.4.11; the registry does not give it to the AI |
| `test_the_poc_element_checks_are_untouched` | the element-check set changed without a decision |
| `test_the_statement_arrives_compiled_with_every_criterion` | the conformance guard, as in §9.29.A |

Four of the five are the platform's own drift guards and **all four were pointing at §9.30.A**. They
were not noise around a known problem; they *were* the problem, stated four times over, in a suite
everybody had been told had "about sixteen expected failures".

**This is #57 for the third time** — a check whose whole purpose is to notice something, ignored
because it was noticing it. First a scan rule, then 1.4.11, now the test suite. The lesson is not
about tests: **an accepted background of red destroys every signal inside it**, so the bar from here
is a green suite, not a remembered count.

#### 9.30.C The dangerous one: pausing the judge would have rebuilt the bug it was built to fix ⭐⭐

One test refused to go green after §9.30.A, and it was right to:
*`test_non_text_contrast_is_covered_by_a_rule_AND_a_judge_and_needs_both`*.

Following it through: the registry gives 1.4.11 to `rule`; `page_rules` records its measurements
under the `rule` engine; and the §9.26 conformance guard asks *did an engine entitled to settle this
criterion look?* With `graphics` held back, the answer would have been **yes** — so a page whose
buttons all had visible edges would have been reported as **Supports 1.4.11** with nothing having
looked at a single icon.

**That is QA-25 word for word**, recreated by the act of pausing the check built to fix it.

The fix: a held-back check now **withdraws its criterion from positive claims** rather than handing
it to the other half. `A11Y_HELD_BACK_CLAIMS` derives those criteria, and `suggest()` declines for
them — placed beside the other positive-only guards, so **failures are untouched in both
directions**: a control edge under 3:1 is still a proven Level AA defect and is still reported.
1.4.11 now reads as **measured but not judged**, which is what is true.

The test holds both ends now: that the judged half is *held and not deleted*, and that while it is
held nothing may claim the criterion.

#### 9.30.D §9.29.A's diagnosis of the conformance failures was wrong

§9.29.A says those tests *"build a fixture with no ownership registry loaded"*. **They load it.**

The real cause is sharper. The fixture records a **rule-scanner** pass for **1.1.1**, and the
registry gives 1.1.1 to the **AI**. axe's `image-alt` proves an alt attribute *exists*; whether it
*says* anything is the judge's question. The guard declined — correctly, and for exactly the reason
it was written.

Fixed by having those four fixtures name the engine that owns the criterion, each with a comment
saying why so nobody reverses it. The guard's own coverage is untouched:
`test_a11y_conformance_guard.py` holds thirteen tests on this rule from both directions, including
`test_a_scanner_pass_cannot_claim_a_criterion_the_ai_decides` — which is the case those four had
been accidentally re-testing.

**Recorded rather than quietly corrected**, for the same reason as §9.29.D: this is the third time
in this document that an explanation was taken from the nearest place rather than the place that
answers the question, and the count matters.

#### 9.30.E The timezone, pinned once for the whole suite

`audit.test.tsx` asserted `13:04` for a `13:04Z` stamp; the screen renders the **viewer's** local
time, deliberately, so it read 18:34 in India and failed. Pinned `TZ=UTC` in `vite.config.ts` rather
than patching the assertion — every time-rendering test written from now on inherits it, and it is
set at config load in the Vitest parent before any worker forks, which is the only cross-platform
place to do it. **416 of 416.**

#### 9.30.F What is still open going into the run

Unchanged by any of the above, and stated so the numbers are read for what they are:

* **the answer key is 173 draft-unadjudicated records** — the accuracy figures measure agreement
  with a careful draft, not correctness. Only a person who did not write the checkers can close
  this, and 1.4.11 cannot come back without it;
* the contested **0.833** precision on `structure` — three tables, needs a ruling, can only move up;
* `#open-exports` and `#newsletter-email` — two judgement calls the key's own author flagged both
  ways;
* screenshot paging — a real shape mismatch, survivable, recorded not fixed;
* **§9.28.H / #58 — terminating a run still does not stop the agent.** The writes are refused; the
  agent keeps going. To actually end a run, stop the companion.

**And one thing that is not a code item at all:** the running worker and API containers were started
at 04:17 UTC on 1 September and hold 31 August code in memory. Every fix in §9.29 and §9.30 lives on
disk only until they are restarted — **worker first, then API** (the deploy order of `b8617a1`,
because the verify timeout travels on the run's payload and an older worker cannot read it), and the
companion started fresh so it captures `border-color`, `outline-color` and the parent description.


### 9.31 The sixth check goes back in, and the registry finally agrees — 1 September ✅ (BUILT)

§9.30 held `graphics` back because the map of what the AI owns and the ownership registry disagreed
about 1.4.11, and five guards had been saying so for five days. The team then asked the right
question: **does the checker actually work?**

**It does, and the evidence was already in the database.** From the 31 August Meridian run:

```
graphics elements selected     59
screenshots delivered          59      every one
verdicts returned              59      every one
   pass                        58      confidence 0.85-1.00, mean 0.91
   uncertain                    1      0.50
routed to a person              5
background-image captured     yes
```

Selection → capture → crop → dispatch → judge → verdict → cache → finding: **every stage fired and
nothing fell through.** And it is reading pixels, not markup — the judge's own words on one page:

> *"Screenshot shows a flat SVG illustration of a brick building. The meaningful parts — the
> terracotta building outline against a light grey background, the arched windows (white/light on
> the dark brown wall)…"*

**The caveat, kept in view: 58 pass, 1 uncertain, 0 fail.** It has never returned a failure. So it
runs, looks at the right thing and answers with high confidence; whether it can say *no* is
unproven, and only the answer key settles that (§9.30.F, #64).

So the hold was lifted — properly, which took four things rather than one.

#### 9.31.A The decision was made on 27 August and never reached the data

`RESEARCH_CORRECTIONS.md` **R14**, agreed 27 August, says of 1.4.11: *"the rationale is correct and
the owner is not."* Both halves were built the same day. **`ownership.json` was never changed.**

That is the whole five-day failure in one sentence: a correction agreed in prose, and the registry
— the thing that actually routes — never told. Everything downstream had already assumed the
correction; only the data disagreed, and only the guards noticed.

#### 9.31.B Carried into the data as an override, not an edit ⭐

`data/ownership.json` is **not a decision record**. `ownership_build` rebuilds it from the committed
research PDF and proves it against eight independent cross-checks — the report's headline counts
(RULE 14 / AI 11 / HUMAN 30), its enumeration of the fourteen rule-primary criteria, its
per-principle headers, and five more. Editing a row there to record a decision would make the file
disagree with its own source, and `build_ownership_dataset --check` would fail. Correctly.

So the decision lives in **`ownership.ENGINEERING_OVERRIDES`**, applied at load:

* `dataset()` stays a faithful read of the file, and every test holding it to the report stays green;
* `CriterionOwnership` — the table every routing and conformance decision actually reads — carries
  1.4.11 as **`ai`**, with the rule half recorded as a `secondary_check`, exactly the shape 1.1.1
  already has;
* the two views are asserted to differ by **exactly the override**, written as
  `RULE_PRIMARY_14 minus 1.4.11` rather than as a second hand-typed list, so a second departure
  cannot arrive quietly.

Three guards hold it: the committed file is unedited, the override set is exactly `{1.4.11}`, and
**every override must name a criterion that appears in `RESEARCH_CORRECTIONS.md`** — a correction in
code with none in prose is the same failure as R14's, pointing the other way. An override naming a
criterion that does not exist is refused rather than silently doing nothing.

#### 9.31.C The two things missing since 27 August, now built

* **`check_graphics` on the capability.** Five element checks were exposed, not six. An audit was
  unaffected — the audit path reads its checker list from the rules — so this was invisible to every
  run and visible only to the test that had been failing about it since the day the checker landed.
  What could not be done was asking the capability about 1.4.11 for one element, which is how
  anything outside an audit reaches the criterion.
* **Seven selection-corpus rows for 1.4.11** — five failure shapes it must reach, two it must leave
  alone, every one drawn from the rule's own `covers` and `skips` prose rather than invented. **Two
  of the five are reachable by nothing else in the platform**, and they are why `graphics` is a
  separate check rather than folded into `alt`:

  | Shape | Why only this check sees it |
  |---|---|
  | a chart drawn as a bare `<svg>` | never announced, so `alt` skips it deliberately — and it is still drawn on the screen |
  | an icon painted as a CSS background image | no tag, role or attribute says it is a picture; it is visible only because `background-image` is in `STYLE_KEYS` for this check |

  The negative side is deliberately narrow, because the rule's own `skips` says *"graphics with no
  rendered box, and nothing else"*. A photograph is **not** skipped: no rule can tell a photograph
  from a diagram, and the standard's "essential presentation" exemption is a judgment the judge
  makes and reports as not applicable.

#### 9.31.D Eleven tests, fixed for the right reason this time

§9.30 recorded that sixteen of the twenty-one red tests went green when `graphics` was withdrawn.
Putting it back turned eleven of those red again — which is the correct outcome, because **those
eleven were never fixed; they were made moot.** They are fixed now:

* **Five in `test_a11y_capture` and six in `test_a11y_report`** asserted an exact checker list, or a
  literal count of requests, in tests about something else entirely — stability, ordering,
  carry-forward, "the report is still produced". Each now asserts *its own subject*: sets of
  elements rather than lists of checks, `len(_selected(world))` rather than `== 2`.
* **Exactly one test keeps the exact list** — `test_only_selected_elements_are_stored`, whose
  subject that genuinely is. Widening coverage is now one deliberate edit in one place, which is
  the only thing an exact list is worth having for.
* The tempting alternative — deriving the expected set from the rules — was rejected: a test that
  agrees with the code by construction proves nothing.

Two fixtures also had to change substance rather than arithmetic: `_judge_everything(world)` now
answers **every selected check** instead of a hand-named `("alt", "semantics")`, because a complete
run reading as incomplete the moment a sixth check starts selecting elements is not a test problem,
it is a fixture asserting a fact about August.

#### 9.31.E Where this leaves the run

```
a11y backend      1,765 passing   0 failing   (33 files)
adjacent suites     126 passing   0 failing
scorer               47 passing   0 failing
frontend            416 passing   0 failing
migrations          none needed
```

Six element checks live, all six exposed on the capability, nothing held back, registry and code
agreeing for the first time since 27 August. 1.4.11 is now **measured and judged**, and the
conformance guard requires the judge to have looked before the criterion can read as supported —
which is stricter than it was before any of this started.

**Still open and unchanged:** the answer key is 173 draft-unadjudicated records, so 1.4.11 ships
with no accuracy figure — accepted by the team, and #64 records it. §9.30.F holds the rest.

**And still the team's to do before the run:** restart the worker, then the API and frontend, then
start the companion fresh. Everything above is on disk; none of it is in the running processes.

---

### 9.32 The audit that ran to completion on a fresh tenant — 2 September ✅ (BUILT / 2 RECORDED)

**Audit `f60c8f1a` · fresh tenant `Edvensoft-WCAG-2` · 94 pages · three passes · complete.**

The first full-scale audit run with all six element checks live and the ownership registry agreeing
with the code. Full reading-by-reading account in `Audit_Live_Check_Reasoning.md` Part II.

**The result.** 2,177 elements captured, 2,283 requests collapsing to **1,068 distinct questions**,
**1,068 judged, 0 unanswered**. 968 pass, 100 fail. 410 open problems (105 critical, 305 high),
**2 awaiting a person**. Active work 3 h 31 m; engine cost $37.18 on the subscription.

**What it proved, and none of it was assumed:**

* **The five original checks were untouched by the 1 September work.** The 31 August selection rules
  were loaded alongside the current ones and all 50 corpus elements walked past both. Identical
  selection, identical scope prose, identical criteria. Recorded because "we did not change that"
  is not evidence.
* **The audit selected the same work as before the changes.** 1,068 distinct questions on both runs,
  dedup 2.15× vs 2.14×, and `graphics` selecting **59 elements on both**. The single most convincing
  number of the day.
* **`graphics` works end to end on real content.** 59 selected, 59 judged, mean confidence 0.938,
  reading pixels and correctly declining the photograph exemption on a flat illustration.
* **The 1 September capture fields are live and in use.** `parent` on 800 of 800 dispatched elements,
  `accessible_name` on 524 — and the judge quotes `accessible_name` in its own evidence, so it is
  being reasoned with rather than merely delivered.
* **Interruption costs nothing but time.** Two passes stopped for environmental reasons and the third
  completed the work. No element was lost, re-judged unnecessarily, or silently marked as passing.
  Answers already banked were reused at zero cost.

#### 9.32.1 A new tenant silently inherits a judging cap of 200 🔬 RECORDED, NOT FIXED

`caps_for()` reads `max_judgments_per_run` from the `a11yai` connection scopes and falls back to
`DEFAULT_MAX_JUDGMENTS_PER_RUN = 200`. A freshly created tenant has `scopes = {}`, so it inherits
200 — where the previous tenant had 800 configured by hand.

**Effect measured on this run:** 1,068 distinct questions at a cap of 200 is roughly five passes
instead of two. Caught during capture and corrected to 800 before dispatch, so it never bit.

**Why it is worth fixing rather than remembering.** Nothing on any screen states the cap, and the
first symptom is an audit that stops early saying it reached "this run's limit" — which reads as
normal behaviour, because it is. The failure mode is a slow day, not an error, so nobody
investigates. Options: surface the cap at project setup, seed it with the tenant, or state it on the
audit screen before the run starts.

#### 9.32.2 The ledger write fails silently when a run fails ⭐⭐ 🔬 RECORDED, NOT FIXED

**Symptom.** After pass 2 the screen showed 370 problems and 106 awaiting review. Both were pass 1
figures, 80 minutes stale. The report document had regenerated; the ledger had not.

**Proof.** All 476 ledger rows were created *and last touched* between 04:13 and 04:16. Pass 2
finished at 05:39. Not one row moved.

**Diagnosis**, from a dry run inside a rolled-back transaction:

```
merge_run           :   8.3 s
record_run_findings : 427.3 s   <- and it SUCCEEDS
   would open      76
   would see again 377
   would resolve   99
```

`record_run_findings` is not broken — it is **slow**, and `publish_report` calls it inside a
best-effort handler that stores the failure on the returned dict. That dict travels back on the
Temporal activity's return value, **which a failed run never persists**. So the one case where the
ledger write is most likely to be cut short is exactly the case where its error cannot be recorded.

**Confirmed non-permanent:** on pass 3 the same write ran to completion, moving the queue 106 → 2 and
open problems 370 → 410.

**The write is correct. The silence is the defect.** Two directions, neither urgent: make the failure
durable (write it to the audit `summary`, which survives a failed run, rather than only to the
activity result), and reduce the write's cost so it is less likely to be interrupted. The first is
the one that matters — an 80-minute-wrong screen with no signal anywhere is the same class of failure
as the accepted background of red in §9.29.

**Cross-check that no new bad behaviour was introduced:** the resolution rules held correctly
throughout. The 44 elements still unanswered after pass 2 did **not** have their findings closed,
because "we did not get an answer" is not "the problem is gone".

#### 9.32.3 The accuracy score for the completed audit — 2 September ✅ (RUN, RECORDED)

Scored against the golden set (`--app-version 1.4.0`, confirmed by the team), audit `f60c8f1a`.
Result file `evaluation/scorer/results/20260902T140726+0000.json`, carrying a stored note that
explains the colour movement. **`baseline.json` was deliberately left alone** — the run blocked,
and the harness keeps the baseline untouched on a block so the comparison stays honest.

| Check | Records | Precision | Recall | F1 | Caught | False alarms | Missed |
|---|---|---|---|---|---|---|---|
| alt | 30 | 1.000 | 1.000 | 1.000 | 15 | 0 | 0 |
| label | 40 | 1.000 | 1.000 | 1.000 | 20 | 0 | 0 |
| semantics | 31 | 1.000 | 1.000 | 1.000 | 16 | 0 | 0 |
| structure | 30 | 0.833 | 1.000 | 0.909 | 15 | **3** | 0 |
| colour | 32 | 0.938 | 0.938 | 0.938 | 15 | 1 | 1 |

**`graphics` has no score and that is correct** — the answer key holds zero records for 1.4.11,
deliberately, as its manifest states. Five of six checks are measurable; the sixth ships judged
but not measured, unchanged from §9.32.

**Completeness: 2,283 element-checks offered, 2,283 answered, across all 94 routes.** Nothing was
dropped between being on a page and getting an answer. Three elements the key names were never
offered to their check — `#newsletter-email [label]`, `#open-exports [semantics]`,
`#save-entry [semantics]` — all three already recorded at §9.28, and two are the standing
judgement calls the key's own author flagged both ways. **On 1 September there were four; the
fourth was `/loans/renewals #renew-tidewater [color]`, and it is now captured.** That is the
border-colour capture fix proven on live data rather than by test.

**Movement since 1 September.** `semantics` recall improved 0.875 → 1.000. `alt`, `label` and
`structure` unchanged. `colour` precision fell 1.000 → 0.938 and the run blocked on it.

**The colour movement, root-caused and accepted by the team.** The entire drop is one record:
`/help/problem-report #problem-detail`. That page and `/help/report-a-problem` are a deliberate
A/B twin — the same textarea, one carrying `aria-invalid` and an `aria-describedby` note that
states the error in words, one carrying neither. **The 1 September capture work is what first put
those attributes in front of the judge**; the 1 September results file mentions `problem-detail`
nowhere, because the judge could not reason about it at all. Shown them, the judge applied the
platform's own rule for 1.4.1 as written in `_has_second_cue` — *only visual cues count; an ARIA
attribute is not one, because 1.4.1 is about what a person who cannot distinguish the colours can
still see* — and failed the field. The key's record assumes the ARIA makes it a pass.

**The checker did what it is specified to do.** This is a disagreement between a documented
platform rule and one answer-key record, and it needs an expert's ruling, not a code change. The
three `ambiguous` `/loans/renewals` markers moved for the same reason and are excluded from
precision and recall by design.

> **The largest real gap is `structure`, not colour.** Precision 0.833 on three false alarms is
> the lowest figure on the board, it is **unchanged from the baseline** so it is not new, and
> nobody has looked at it. Colour got the attention this run because it moved.

**The standing caveat is unchanged and governs every number above.** The dataset's own manifest:
every verdict is an unadjudicated draft awaiting expert review, single-labeller, no blind
re-label round (`relabel_agreement: null`). These measure how often the checks agree with a
careful draft, **not how often they are right**. Internal only; the team has confirmed they will
not be published or shown to a client.

**One gap found while running it:** the harness demands `--app-version` and never records it —
see `TESTING_GUIDE.md` #69.

> **Team decision, 2 September.** Both of the above were presented in full with a proposed fix, a size and a risk assessment. **The team weighed them and judged neither urgent**, and chose to spend the time on conformance-tab UI work instead. They are deferred by decision, not by neglect — do not reopen the question without new evidence. The fixes proposed were: for the cap, show it on the audit screen and set it explicitly for new workspaces; for the ledger, record the reconciliation outcome on the audit's own `summary` (which survives a failed run) rather than only on the run's return value, and leave the seven-minute write cost alone — speed is a comfort, the silence is the defect.
