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
| 8 | **B1 + B4 + B2** — the audit screen, and the way in | Brownfield audit with no terminal at all | L |
| 9 | **G6** — the keyboard journey, working on both journeys | Eight criteria nothing else can reach | M |

Tasks 1–4 are independent of each other. 6 should land before 7. 8 has the wireframe already
approved (`docs/design/screens/S-38-a11y-audit.html`). 9 is broken into three slices of its own and
shares that screen, so it is cheaper to build after 8 than before it.

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

**In plain words.** The Testing agent writes accessibility test cases marked `Type: Accessibility`.
The platform never reads that. On the Test cases screen you cannot tell which of your forty cases
are the WCAG ones, and the Priority column is blank for all of them.

**Why it happens.** Two halves of one root cause.

The type is written as prose in the test case document. Nothing in the platform parses it — the
only `Type:` reader anywhere is `backend/apps/a11y/journeys.py:101`, which looks for `e2e` and
nothing else. The Test Automation agent behaves correctly because *it* reads the document; the
platform never learns anything.

Priority is the same shape of problem seen from the other end. When test cases become work items
(`backend/apps/workitems/test_cases.py:63`), only `{test_case_artifact_id, tc_id}` are copied. The
Test cases screen then reads `priority` from the **work item** (`backend/api/views.py:1409`), where
it was never written — while defect severity reads it from the **artifact**
(`backend/apps/quality/services.py:367`), where it lives.

**Worth stating plainly:** accessibility coverage does **not** depend on this. Every generated
script captures accessibility evidence, not only the accessibility cases — deliberately, because a
login screen is exactly as likely to have an unreadable button as one somebody wrote a case for.
This gap is about what a person can *see*, not about what gets checked.

**What we change.**

- `backend/apps/quality/services.py` — add a `_test_case_type` reader beside the existing
  `_test_case_severity`, using the same two-step it already uses: structured `external_ref` first,
  then a regex over the document body. No new pattern is invented.
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

**Size M · Risk low · Needs first: nothing.**

---

### G3 · A finding does not say which test case found it

**In plain words.** In the review console a QA Lead sees *"1.4.3 · /checkout · button.pay"* and has
no way to reach the story, the test case or the run that found it. On brownfield that is correct —
an audit of an existing application has no story. On greenfield it is a hole.

**Why it happens.** The data exists and is simply not passed through. `A11yFinding` carries
`first_seen_run` and `last_seen_run` (`backend/apps/a11y/models.py:452-457`), and for a greenfield
finding that run's work item **is** the test-case work item. The projection the screen receives —
`_item()` in `backend/apps/a11y/review.py` — never includes them.

It was invisible until now because the console was designed against the brownfield case, where
there genuinely is nothing to link to.

**What we change.**

- `backend/apps/a11y/review.py` — `_item()` gains `source_run`, `work_item_key` and
  `work_item_title`, read from `last_seen_run` (falling back to `first_seen_run`). All three are
  `null` when the run does not exist or has no work item — which is the honest answer for a
  baseline audit, not a bug. One `select_related` so the queue does not fire a query per row.
- `frontend/src/features/a11y/A11yReview.tsx` — a line under the route: *"Found by TC-031 —
  Checkout with valid card"*, linking to the work item, and a link to the run. Absent entirely
  when the values are null — no empty link, no "—".

**What you see afterwards.** A greenfield finding names the test case that found it and links to
it. A brownfield finding shows nothing extra, exactly as today.

**How we prove it.** Two tests, one per shape: a greenfield finding names its test case; a baseline
finding returns nulls and the screen renders no link at all.

**Size M · Risk low · Needs first: G2 (so the test case's own type is available to show alongside).**

---

### B1 + B4 + B2 · The audit screen, and the way in

**In plain words.** Today, auditing an existing application means two things a user cannot do in
the product: registering the list of pages by raw HTTP, and running a command in a terminal. This
task replaces both with a screen, and puts a step in onboarding so people find it.

The wireframe is approved: **`docs/design/screens/S-38-a11y-audit.html`** — seven labelled states.

**Why it happens.** QA-17 built the REST endpoints and the companion command; no screen was ever
built. `frontend/src/api.ts` has clients for review and conformance only. Four backend endpoints —
`a11y-policy`, `a11y-routes`, `a11y-audits`, `a11y-backlog` — have no client at all. And
`A11yRoute.Source.ONBOARDING` exists as a value in the code that nothing has ever written: the hook
for this was planned and never finished.

**What we change.** Three pieces, built in this order.

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

**How we prove it.** An end-to-end test: an audit created through the API is claimed by a stubbed
companion, runs, and completes. Parser tests for all input forms including a malformed one. Frontend
tests for every state in the wireframe, including read-only and no-machine-connected.

**Size L · Risk medium — it adds a claim path and a migration · Needs first: B3 (so the address
pre-fills) and B5 (so a real application's page count is not silently truncated on the first run
anyone does from the UI).**

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

**G6b · Make a journey claimable work** *(the seam both journeys use)*

- `A11yJourneyRun` gains `PENDING` / `CLAIMED` and an `enrollment`, like the audit in B1.
- `GET /api/runner/a11y-journeys/` to claim, and a `journey` branch in the companion daemon that
  runs the 09d agent against the claimed journey's address.
- The journey's own carrier work item is marked a **carrier** from the start (see G4), so this
  never repeats that mistake.

*Size M · Risk medium · Needs G6a.*

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
| `a11y/0027_journey_address` | `A11yJourneyRun`: `base_url`, `PENDING`/`CLAIMED`, `enrollment` | G6a, G6b |

The two schema ones are RLS-aware from the first migration, like every table in this platform. The
data one runs as the privileged migration role for the same reason `a11y/0005` does: work items are
FORCE ROW LEVEL SECURITY, so a merely-owner role would read zero rows and quietly do nothing.

⚠️ **Five migrations from the last round — `0021` to `0025` — are still unapplied on the shared
server**, and `workitems/0006` now makes six. These land on top of them. Applying any of them to
the shared database is the team's call, never mine.

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

## 8. Two documents to rewrite when this work is done

Both currently carry a correction notice rather than a rewrite, because most of what is wrong in
them stops being wrong the moment these gaps close. **Neither notice is the fix; both documents are
to be rewritten, and their notices removed, as the last task of this plan.**

- **`TESTING_GUIDE.md`** — written before the journey recon. Its two "journeys" are the accessibility
  slice only, and five specific statements in it are untrue today (its notice lists them). When this
  plan lands it needs rewriting to cover the **whole** journey a user walks — create project, upload,
  adopt, connect Jira and Confluence, register repositories, index code, gap report, resume — with
  the accessibility work shown in its real place inside it, and with the terminal steps gone because
  they no longer exist.
- **`TASK_BACKLOG_QA.md`** — its 31 tasks are correctly ticked against their own acceptance criteria.
  Its notice explains that those criteria tested units rather than reachability. Remove the notice
  when the eleven gaps are closed.

**And the lesson that produced this plan, recorded so it is not learned twice:** every one of the 24
tasks passed its tests and the backlog read as complete, while a user could not register a page list,
start an audit, or start a keyboard journey. The acceptance criteria never asked *"can a person get
to this?"* Every task in this plan carries a **"What you see afterwards"** section for that reason —
it is the question the last round did not ask.
