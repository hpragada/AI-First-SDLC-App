# Web Accessibility — What Was Built, Where It Sits In The Journey, and How To Test It

**For the Edvensoft team · 21 August 2026 · branch `web-accessibility-build`**
**Covers QA‑01 … QA‑24 (31 tasks), the ten gap-fix tasks G1 … G6c, the eighteen
user-experience fixes of 20 August, and the six of 21 August that the first live run found (§9)**

---

## 0. How to read this document

This is written for someone who has **not** read the code. Where a technical name is unavoidable
it is explained the first time it appears.

**This is the second version of this guide.** The first was written before anyone traced the
journeys, and it was wrong in five places — it called the accessibility slice "the journey", it
described steps that had no screen, and it called the keyboard test "optional" when it could not
be started at all. Those gaps are now closed, and this rewrite is written **from the source,
walked screen by screen**, not from the specifications. Where the source and the plan disagreed,
the source won and the plan was corrected in the same change.

**The walk itself changed the product.** Reading each screen as the person using it turned up
fifteen things that worked but would not have served them; the team approved fourteen and they
are built. **Three more came from the team's own first live run, the same day** — two dialogs they
read and described back to us wrongly, which is the most reliable signal a screen can give. Every one of them is recorded in §9, and every place in this guide where the behaviour
changed says what it used to do — so a reader who saw the old screen is not left wondering
whether they misremembered.

**Three markers, and they matter:**

| Marker | Means |
|---|---|
| ✅ | Built, and proven by automated tests |
| 🔬 | Built, and proven by automated tests — **but never once run against a real browser or a real application** |
| ⚠️ | A limit, a prerequisite, or something that will surprise you |

**The honest caveat, said once, at the front — and it changed on 20 August.** It used to read
*"no part of this has ever run live, not once"*. **The brownfield audit has now run live**, against
Meridian Library on a real browser: pages registered, an audit claimed by a real companion, ten
pages visited twice, and real AI verdicts recorded — including a defect no scanner can find. What
that run also did was expose **four defects stacked behind one another**, none of which any test
could have caught, plus five more the morning after. They are §9 items #19–#24 and they are built.

**What is still unproven is now a much shorter list, and §10 is it:** the greenfield capture, the
keyboard journey, a complete judging pass end to end, and two capture passes over 68 pages. Where
this guide says *"you will see X"* for one of those, that is still what the code does rather than
what anyone has watched — and every step says **what would mean it is broken.**

**§9 is the section to read if you only read one.** Walking this guide turned up fifteen places
where what was built worked but would not, on reading it as the person using it, have satisfied
them. **The team reviewed all fifteen on 20 August: fourteen were approved and are now built, and
the fifteenth — the migrations — the team ran themselves.** Three more (#16–#18) came from the
team's first live run later the same day, all of them wording on the two page-registration dialogs;
**six more (#19–#24) came from that run actually executing**, and those are defects rather than
wording. §9 is the record: what was wrong, what was done, and how it is proven.

---

## 1. The database is ready — done 20 August

✅ **All 32 accessibility database changes are applied on the shared server.** The team ran them
on 20 August and I re-read the database afterwards: `showmigrations` comes back with **nothing
pending**, across every app.

This section is kept rather than deleted because of how it read that morning, and because the
number was wrong everywhere. The previous guide and the gap plan both said "five migrations are
pending". Reading the shared database directly showed **32** — starting at `a11y/0001`. Not one
accessibility table had ever existed there. Every pending migration in the whole platform was
accessibility work.

```
a11y          0001 … 0027   all 27 pending
integrations  0010_a11yai_autoprovision
projects      0011_projectprofile_a11y
registry      0006_seed_a11y_judge
registry      0007_seed_a11y_journey
workitems     0006_a11y_judging_carrier_marker
```

**What each group created, so the team knows what landed:**

| Group | What it creates |
|---|---|
| `a11y 0001–0020` | The whole capability: findings, screen scans, candidate bundles, routes, baseline audits, journey runs — and the WCAG 2.2 dataset itself (`0005`, `0006`) |
| `a11y 0021–0025` | The review console's lock and decision fields, the per-criterion coverage table, the conformance statement, and RLS policies for both new tables |
| `a11y 0026–0027` | An audit a machine can claim, a page's example path, and the journey's address |
| `registry 0006`, `0007` | **Seed the two agents.** Without these there is no `09c_a11y_judge` and no `09d_a11y_journey` — nothing judges and nothing walks |
| `projects 0011` | The per-project accessibility policy block |
| `integrations 0010` | Auto-provisions the `a11yai` capability |
| `workitems 0006` | Marks judging work items already on people's boards as hidden plumbing |

**How to check for yourself, at any time:**

```bash
cd backend && ../.venv/Scripts/python.exe manage.py showmigrations a11y
```

Every line should read `[X]`. It does.

⚠️ **If you ever have to run them on another environment**, run as the **postgres owner**, not as
the application user — the application user cannot `ALTER`, and a permission error on `ALTER` is
what that looks like. Deploy the worker before the API.

✅ **And if an environment is ever missing them again, the screens now say so.** The API
returns 500 because the tables are gone, and each of the four accessibility screens says exactly
that — *"The page list could not be loaded"*, carrying the platform's own message (`relation
"a11y_route" does not exist`), a **Try again** button, and the line that matters: **"Nothing
shown here is a statement about your application."**

⚠️ **They did not, until 20 August.** Every one of them fell through to its empty state — *"No
pages are registered yet"*, *"Nothing is waiting on you"* — so a system that was down looked like
a clean, empty, working one. That was item **#1 in §9**, and while the 32 migrations were pending
it was not hypothetical: it is precisely what the first person to open the feature would have
been told that morning.

**With the database in place and the fourteen fixes built, there was nothing left between the team
and a first live run — and it happened the same evening.** What it found is §9 #19–#24.

---

## 2. What this thing is, in plain language

Making a website usable by disabled people is governed by a standard called **WCAG 2.2**. At the
levels the law generally cares about — Level A and Level AA — it has **55 rules**, called
*success criteria*. A conformance claim means going through all 55 and saying where you stand on
each one.

Doing that by hand takes an expert several days per application. Most teams therefore either
don't do it, or run a free browser plugin, find nothing, and assume they are fine.

**What we built does three things a plugin cannot:**

1. **It uses three different kinds of checker**, because no single one can cover the standard.
2. **It never guesses.** When a check cannot settle something it says so and hands it to a
   person, rather than reporting a clean result.
3. **It produces a document a person signs.** The platform compiles the evidence and drafts the
   wording, then stops. It never calls anything compliant on its own.

### The three checkers, and the real coverage arithmetic

⚠️ **The previous guide's numbers here were wrong, and this is the correction.** It said the AI
half covers "11 of 55". Eleven is how many criteria the platform's own registry
(`apps/a11y/data/ownership.json`) *classifies* as AI-owned. Only **four checkers are built**, and
they cover **five** criteria. The other six are Phase 2 — which the task backlog has said all
along, in QA‑02b's known limitations. The guide simply quoted the wrong number.

| Checker | What it is | Criteria it can speak to **today** | Registry says it owns |
|---|---|---|---|
| **Rule scanner** | The industry-standard **axe** engine, running inside the page and measuring things | **14** | 14 |
| **AI checks** | Four checks that read a captured element and form a judgement: `alt`, `semantics`, `color`, `label` | **5** — 1.1.1, 1.3.1, 1.4.1, 2.5.3, 4.1.2 | 11 |
| **Keyboard journey** | An agent that operates the running application with only the keyboard | **8** — 2.1.1, 2.1.2, 2.4.3, 2.4.7, 2.4.11, 3.2.1, 3.2.2, 4.1.3 | 8 |

**So the honest total: 27 of the 55 criteria have some automated evidence today. 28 do not.**

Of those 28: **five** are AI-owned criteria whose checker is not built yet (Phase 2), and
**twenty-three** can only ever be assessed by a person. (The previous guide said 22. It is 23 —
2.4.7 *Focus Visible* is classified AI-owned in the registry, and the keyboard journey is what
actually covers it, so it must not be counted twice against the human remainder.)

No tool on earth can tell you whether a video's captions are *accurate*, or whether an error
message is *helpful*. The platform prints those 23 as **not evaluated** rather than pretending
otherwise.

### The one idea everything is built around

> **A criterion nobody looked at must never look like a criterion that passed.**

This sounds obvious. It is the single most common way accessibility tooling lies. If a scanner
has no rule for "captions are accurate" it reports nothing — and a report that lists only
problems then shows a clean page. Every design decision in this build traces back to refusing
that. It is also the yardstick §9 measures the screens against, and the reason item #1 there
matters as much as it does.

### Who does what

| Action | Who |
|---|---|
| Start a **keyboard journey** | **QA Lead** (`qa_lead`), or a workspace admin by carve-out |
| **Decide** a finding — confirm or reject | the same |
| **Edit and sign** the conformance statement | the same |
| **Register, edit or delete pages**, and **start an audit** | **QA Lead, Tech Lead or Admin** |
| **Read** every accessibility screen in full | anyone on the project — a developer wanting to see what a reviewer is looking at is exactly the transparency this build is for |

**Two lists, and the difference is deliberate.** Answering a finding and signing a statement are
the accessibility reviewer's alone. Saying which pages an application has is ordinary project
work a Tech Lead does as readily as a QA Lead, so the scope list is wider.

Every gated action renders in full for a reader, with a sentence saying whose call it is and a
disabled control rather than one that fails on click.

⚠️ **Until 20 August, page scope and audits were not gated at all** — they fell through to the
viewset default, `AllowAny`, while starting a keyboard journey on the same screen was refused for
anyone but the reviewer. Nothing escaped the tenant, so this was never a cross-customer hole; it
was an inconsistency on top of the input every later number depends on. Item **#2 in §9**.

---

## 3. Setting up, once

### 3.1 The platform

```bash
docker compose --profile app up -d
```

Sign in at `http://localhost:5173`. You need an account holding **QA Lead** on the project under
test. ⚠️ On Windows the frontend container's hot reload does not always pick up host edits —
restart the `frontend` service if a change does not appear.

### 3.2 The companion, on the tester's own machine

The **companion** is a small program that runs on a developer's laptop. It exists because the
application being tested runs at an address our servers cannot reach — `localhost:4180` on
someone's machine is not a thing a container in AWS can open. The companion is the bridge, and
everything that touches a real browser happens there.

```bash
python -m runner.companion enroll --api-url http://localhost:8000 --tenant <T> --project <P> --label laptop
python -m runner.companion serve  --api-url http://localhost:8000 --tenant <T> --token <TOK> --worktrees ~/sdlc
```

⚠️ **This is the one terminal step that remains, and it is not an accessibility step.** It is how
the platform gets a machine at all — greenfield users already meet it on the setup checklist and
brownfield users meet it at the top of the onboarding hub. Once it is running, **every
accessibility action in this guide is taken from a screen.** There is no accessibility CLI in
this document, and the `python -m runner.companion audit` command the previous guide told you to
run is no longer how anyone audits anything.

Make sure the checkout is on `web-accessibility-build` and current. The companion serves three
things this build needs: it claims **audits**, it runs **keyboard journeys**, and it captures
accessibility evidence during a **build**.

**How to check it is connected:** the header shows the machine as online, and the "Run an audit"
strip shows a green **Machine connected** badge. If it shows a red **No machine connected**, the
platform can see no machine *of yours* — it deliberately does not report anyone else's.

### 3.3 What the application under test needs

**Install the companion's own toolchain once, and this section is largely done with.**

```bash
cd runner && npm install && npx playwright install chromium
```

That gives the companion its own pinned browser and scanner (`runner/package.json`:
`playwright 1.62.1`, `axe-core 4.13.0`). Do it once per machine and every project on it becomes
auditable, whatever it is written in.

| | The **audit** needs | The **keyboard journey** needs |
|---|---|---|
| The companion's own toolchain (above) | ✅ unless the project supplies its own | not used |
| A registered repository, cloned locally, with `playwright` + `axe-core` in it | preferred, **not required** | not used |
| `npx` available | no | ✅ (it fetches `@playwright/mcp`) |
| The application running, at an address that machine can reach | ✅ | ✅ |

**Why the project's own copy is still preferred.** The version stamped on every scan should be
the version that application actually ships — that is what makes a conformance statement
re-examinable later. So the audit resolves the scanner out of the audited project first and falls
back to the companion's only when there is none.

✅ **And it says which one it used.** A scan that fell back records `axe-core 4.13.0
(companion)`, and that suffix rides on the version string that already travels everywhere a
version is shown — per screen, in the report, and onto the signed statement. Without it the
platform would name a version the client's application does not ship.

⚠️ **Until 20 August the clone was a hard requirement**, which made a whole class of application
unauditable: a Django, Rails or .NET app has no `node_modules`, so the only way to audit one was
to add npm dev-dependencies to the client's own repository in order to look at it. Item **#9 in
§9**.

- **Meridian Library** ships both itself: `@axe-core/playwright ^4.10.0` and `playwright ^1.47.0`,
  so it is scanned with its own axe and the report says so by *not* saying `(companion)`.
  ⚠️ They are **development** dependencies, so `npm install` works and `npm ci --omit=dev` would
  leave the project's copy missing — in which case the audit still runs, on the companion's.
- If neither can be found, the audit is closed carrying that exact reason — naming both places it
  looked — rather than the generic "the application did not respond", which would send someone to
  check a server that was never contacted.
- If only the *scanner* is missing, the AI checks still run and the platform states *"the
  measurable checks did not run"* rather than reporting a clean page.

### 3.4 The demo applications

**Meridian Library** (brownfield — an application we did not build):

```bash
cd ../meridian-library-web-accessibility && npm install && npm start
```

Serves at `http://localhost:4180`. **79 routes** in `routes.json`; one (`/health`) is marked
out of scope, so **78 pages to audit** — two capture passes.

⚠️ It was 69 until 20 August. The developer's `main` added ten pages (subject index, shelf audit,
card services, problem report, branch finder and their near-duplicate partners) and moved the
fixture-checking tools out of the app into `docs/web-accessibility/evaluation/harness/`. If you
see 69, you are on the old history — see §1.

⚠️ Its README claims *"Meridian Library conforms to WCAG 2.1 Level AA. Last audited March
2024."* Treat that as a claim to be tested, not a fact.

**A greenfield project** is whatever you build through the platform in Journey A below.

---

## 4. Where accessibility sits in the whole journey

The previous guide's biggest error was calling the accessibility slice "the journey". It is not.
It is **one step inside a much longer one**, and the point of this section is to show where.

### Greenfield — a project built through the platform

```
sign up → setup checklist → connect machine → invite people → connect Jira/Confluence
       → create project → project profile → register repositories
       → create a work item → run the phases:
             Ideation → Requirements → PRD → Architecture → UX Design → Task Breakdown
             → Implementation → Code Review → Testing → TEST AUTOMATION ← accessibility
                                                                          evidence is
                                                                          captured HERE
             → Security → CI/CD → Deployment
       → gates and clarifications along the way
       → ACCESSIBILITY REVIEW  ← the uncertain findings, answered by a person
       → KEYBOARD JOURNEYS     ← the eight criteria nothing else reaches
       → CONFORMANCE STATEMENT ← compiled, drafted, signed
       → artifacts, traceability, publish
```

Accessibility enters at **Test Automation** and is not a phase of its own. There is no
"accessibility" button on the phase picker and there should not be — the evidence is a
by-product of the suite that was going to run anyway.

### Brownfield — an application that already exists

The onboarding hub (`/onboarding`) is the spine. It has a prerequisite card and seven numbered
steps, and accessibility is **step 6 of 7**:

```
   ✓  Connect your machine                       (a card above the steps)
   1  Upload resources          → /onboarding/documents
   2  Register existing tools   → Jira + Confluence, in place
   3  Register repositories     → /repositories
   4  Index code                → per repo, on your machine
   5  Gap report                → /onboarding/gap-report
   6  CHECK ACCESSIBILITY       → /a11y/pages          ← the whole slice lives here
   7  Resume                    → /runs
```

**Step 6 sits before Resume on purpose.** The point of a baseline is to know where the
application stands **before** anything is changed. Its wording changes with what has actually
happened, from three counted facts:

| Hub says | Because |
|---|---|
| *"Register the pages of the application and run a first audit…"* + **Set up the audit** | no routes registered |
| *"N page(s) registered. Run a first audit against WCAG 2.2 AA."* + **Pages & audit** | routes registered, no audit finished |
| *"N audit(s) run — open the report from Artifacts."* | at least one audit `complete` or `judging` |

The middle state counts `judging` as done deliberately — the pages *have* been visited by then;
the AI half still finishing is not the user's step to wait on.

---

## 5. Journey A — Greenfield, end to end

This is the shorter of the two, because the accessibility work rides along with the build.

### A1 — Get a project and a machine ✅

Sign up → the setup checklist walks you through connecting a machine, inviting people, and
connecting Jira/Confluence. Create the project. Register at least one repository.

**What would mean it is broken:** the setup checklist marking a step done that you have not done.
Note that the checklist asks *"did you ever complete this"* while the onboarding hub asks *"is
your machine answering right now"* — the two are deliberately different questions and can
disagree without either being wrong.

### A2 — Run the phases up to Test Automation ✅

Create a work item, then trigger phases from **Phases & Runs**. All 16 are in the picker.
Accessibility needs the build path to have reached **Test Automation** (`09b_test_automation`),
because that is the phase that generates and runs the browser suite.

### A3 — The accessibility capture 🔬

**What you do:** nothing extra. It happens inside the Test Automation run.

**What is happening inside.** At the end of the build run, in the same window in which the
application is up and the worktree still exists, the companion collects what the generated suite
wrote and posts it to the platform. A screen carries a full-page PNG, so it is posted directly
rather than carried on the run report.

**What it captures per screen, and why every field is load-bearing:**

1. **All four of the scanner's answers**, not just failures:
   - *violations* — it failed
   - *passes* — checked, and fine
   - *inapplicable* — the rule ran, and there was nothing on this page for it to apply to
   - *incomplete* — **axe looked and cannot decide; a person must**
2. **The scanner's version**, read from the module the project imported.
3. **Every element** the four AI checks might apply to — its markup, the text around it, six
   computed style properties, and the browser's own computed accessible name.
4. **One full-page screenshot**, and each element's exact rectangle on it.

⚠️ **Gap G1 was exactly this and it is now closed.** Until 19 August only *violations* survived,
which meant a criterion with nothing against it was indistinguishable from one nothing had
checked — and a greenfield conformance report read "not evaluated" against nearly every
criterion. The four-answer contract is now written into `09b_test_automation`'s agent body in
detail, including the trap that *inapplicable is not a pass*.

⚠️ **But this half is written by an agent, not by us.** The brownfield audit runs a fixed script
we ship and review; the greenfield capture is code the Test Automation agent *generates* from
that contract. So "G1 is built" means the contract is correct and enforced on ingest — it does
not mean every generated suite will honour it. **This is the single most valuable thing to check
on the first live greenfield run.** 🔬

**What would mean it is broken:** a conformance report where nearly every criterion reads *not
evaluated* after a successful test run. That is the signature of a capture that wrote violations
only.

### A4 — The AI pass ✅

The platform picks up what was captured, selects the elements each of the four checks applies to,
and dispatches a judging run. The judge is a real agent run through the normal driver — there is
no direct model call anywhere in this build.

**Where you watch it:** you don't, and that is deliberate. The judging run hangs off a **hidden
carrier work item** so it never appears on anyone's board (gap **G4**, closed). A plumbing task
called "Accessibility judging" sitting in a client's backlog was the problem it solved.

Up to **200 element judgments per run**; the excess is deferred, never dropped.

### A5 — The gate ✅

The accessibility rule binds to the **Testing** gate — the same gate that already accepts the
test report — and to no other. A merge gate carrying it too is an open product decision that
neither this build nor the test gate before it chose to make.

The gate blocks on **severity**, which is derived from the criterion's WCAG level: Level A →
Critical, AA → High, AAA → Medium. An AA-target project therefore blocks on Critical and High.

Three things it will say that are worth recognising:

- ⚠️ **"No accessibility check has run for this work item yet, so this says nothing about
  whether it is accessible."** A gate with nothing to report says that, rather than passing.
- **Findings from the keyboard journey are named in their own sentence and never block.** See D1.
- ⚠️ **A project can be configured to block on nothing at all.** An empty `block_severities` is a
  real, supported choice — "report everything, block nothing" — and is left alone rather than
  corrected.

### A6 — Defects on the board ✅

Confirming a finding raises a defect work item. **One ticket per problem, not per finding**: if
the scanner and an AI check both flag the same element for the same criterion, that is one
ticket. Tickets close themselves when the problem stops being found, and reopen when it comes
back.

They are ordered by **severity, then breadth, then criterion number** — breadth being how many
distinct pages breach the same criterion, because one criterion broken on twelve pages is usually
one component fixed once. ⚠️ **Effort is deliberately not in the order.** How long a fix takes is
a judgement about your codebase the platform has no basis for making.

### A7 — Review, journeys, conformance

The same three screens as brownfield. They are described once, in §6.

---

## 6. Journey B — Brownfield, end to end

**Brownfield** means an application that already exists and was not built through this platform.
You point the platform at it and ask *"where does this stand?"*

Meridian Library is a community library site: Node and Express, server-rendered, no JavaScript
framework, 79 routes.

### B1 — Create the project and reach the hub ✅

Create the project on the **brownfield** track. You land on `/onboarding`.

**What you should see:** a *Connect your machine* card, then seven numbered steps. ✅ The
design-gallery fixture used to show five and has been brought back into step with the live screen
(item #12 in §9), so a design review is now a review of the screen that exists.

✅ **The prerequisite card no longer carries a `1`.** It shows `!` when your machine is not
connected and `✓` when it is, so the numbered list reads 1–7 with nothing repeated. It used to
show `1`, and so does *Upload resources* below it — two steps numbered 1, on the first screen a
brownfield client ever sees. Item #10 in §9.

### B2 — Steps 1 to 5 ✅

Upload documents → adopt them → register Jira and Confluence in place → register repositories →
index code → run the gap report. The gap report tells you where to resume.

✅ **Step 3 used to be a hard prerequisite for the audit; as of 20 August it is not.** No
registered repository once meant no project folder and a refused audit. The audit now falls back
to the companion's own toolchain, so a project with no repository at all can still be audited —
which is what *"point the platform at a running application and ask where it stands"* ought to
mean. A repository is still worth registering: the audit prefers the application's own scanner
when it can reach one. See §3.3.

### B3 — Step 6: register the pages ✅

Follow **Check accessibility** to `/a11y/pages`, or the sidebar's **Accessibility** item and then
the **Pages & audit** tab.

**Why this step exists at all.** The platform has no access to your application — deliberately —
so it cannot discover its pages. Somebody has to say what they are. Nothing is audited until you
do, and the empty state says exactly that.

**Which of the two buttons.** **Import a list** if you already have the pages written down
somewhere — a routes file, a sitemap, a page inventory. **Add a page** if you are building the
list up by hand. The empty state says this; until 20 August it did not, and the two buttons were
a choice with nothing to make it on.

**What you do:** press **Import a list** and paste a list of pages. The dialog is titled
*Import a list* — ⚠️ until 20 August it was titled **"Add pages"**, which is nearly the name of
the other button, so people believed they had opened the wrong one. Item #16 in §9.

✅ **One path per line is enough.**

```
/
/catalogue
/about/history
```

Blank lines are skipped and so are `#` comments. Paste a **JSON** list instead when you also want
to give each page a name or say whether it is in scope: entries carrying `path`, with optional
`title`, `enabled` (or `in_scope`), `notes` and `example`.

```json
[{"path": "/catalogue", "title": "Browse the catalogue"},
 {"path": "/events/:id", "example": "/events/482"}]
```

⚠️ **A pattern must go in the JSON form, and only there.** Line mode returns bare paths, so there
is nowhere to say what `/events/:id` should open; the audit would then request that address
literally, fail, and report the page unreachable on every run. The placeholder in the box used to
demonstrate a pattern in the **line** half — teaching the one combination that cannot work — and
that was fixed on 20 August along with showing both formats side by side. Item #17 in §9.

✅ Meridian has **no** pattern routes, so this does not affect the walkthrough below.

⚠️ **A line containing a space is refused, by line number**, and that refusal is deliberate. The
path checker rejects an empty path, a full URL, a path not starting with `/` and a line break —
but not a space, so `Home /catalogue` would register a page that cannot exist and be reported
unreachable on every audit forever, from a typo nobody can see. That is the exact hole that killed
an earlier line-per-path form; it is closed rather than reopened.

⚠️ **Until 20 August only JSON was accepted**, and one path per line — the most natural thing to
paste — was refused with a message explaining JSON to somebody who had just pasted a perfectly
clear list of pages. Item #8 in §9.

**Walking this with Meridian, concretely:**

1. **You cannot paste the whole file.** `routes.json` is an object with `version`, `base_url` and
   `routes`. Paste the value of `routes`.
2. ✅ **`in_scope` is honoured**, so `/health` — the one route Meridian's author marked out of
   scope — arrives out of scope, and nothing is named back to you as unrecognised. Until 20 August
   `in_scope` was not a recognised column, all of its pages were registered in scope, and the confirm
   screen warned about it (honestly, but as a chore for the reader). Item #14 in §9.
   ⚠️ A *genuinely* unknown column — `inScope` in camelCase, say — is still named back, with the
   sentence that matters: *"If one of them says whether a page is in scope, those pages will be
   audited."*
3. **The confirm screen is the point of the whole step.** It shows what would be added, what
   would be updated, and — the half that matters — **which pages you already have that this list
   does not mention**, with their recorded problems. A page is identified by its path, so
   correcting a path in the text does not rename a page, it points at a different one. The
   platform cannot tell "I removed this page" from "I just fixed a typo" apart, and nobody has to:
   you are shown both and asked which, before anything is written.

**Then, day to day:** **Add a page** adds one, and **Edit** on a row edits that row.

**What Add a page asks for.** Four controls, and only the first is required:

| Field | Required | What it is for |
|---|---|---|
| **Path** | **yes** | any page — `/catalogue`, `/about/history`. A pattern is allowed too. |
| **Name** | no | makes the report readable; nothing depends on it |
| **Example page** | no | **only** when the path cannot be opened in a browser as written |
| **Audit this page** | on by default | whether it is in scope |

⚠️ **This dialog is not "for patterns".** Two people on the team read it that way on 20 August,
because the Example page help began *"Only for a pattern like `/events/:id`"* — which, read
scanning down the form, describes the dialog rather than the field. It now begins *"Leave this
empty for a normal page."* Item #18 in §9.

✅ **Any pattern shape works**, not just `:id`. The platform never parses patterns: `normalise_path`
wants a leading `/` and nothing else, so `/events/:id`, `/books/[isbn]` and `/users/{id}/loans` are
all stored exactly as written. The rule is not "must look like `:id`" — it is *"if the path as
written cannot be opened, give one that can"*, and the field now names three shapes so no single
framework's syntax reads as the only one allowed.

Editing a row
is an edit — the ghost-page problem only exists in the pasted list, where there are no
identities. ⚠️ **Renaming a page does not move its history**: findings are identified by the page
they were found on, so the problems stay at the old address. The editor says so before it happens.

⚠️ **Removing a page usually does not remove it.** If it has accumulated findings it is taken out
of scope and kept, and you are told so afterwards — because the answer depends on what the page
has, which the person pressing the button cannot be expected to know.

**Limits:** at most **200 registered pages** per project. That is a scope judgement, not a
technical one: a list past 200 is a sitemap dump rather than a considered audit scope.

**What you should see:** every route listed with a path, a name, an in-scope switch, and *Never
visited*. **What would mean it is broken:** the summary line disagreeing with the row count.

✅ **Signed in without QA Lead, Tech Lead or Admin?** You see the whole list and every control is
disabled, under *"You can see this; the QA Lead or Tech Lead runs it"*. With no pages registered
at all you are told who registers them rather than being offered a button you cannot press.

### B4 — Step 6 continued: run the audit ✅ 🔬

The **Run an audit** strip appears once at least one page is registered.

**What you do:** check the address, then press **Run audit**.

**The address.** Leave it blank to use the address the platform already holds — it resolves that
from the default repository's Preview URL, else from the only repository claiming one, else from
the port the companion itself uses when it brings an app up. ⚠️ Two repositories both claiming to
serve the application is **refused by name**, never resolved by picking the first: only a person
knows which application you meant. Typing an address here scans a different environment **for
this run only** and is not saved back.

**What the strip tells you before you press anything:**

- **Pages in scope**, *n* of *m*.
- **Passes** — 68 in scope is **2 passes of 60**. ⚠️ Gap **B5** is closed: an audit bigger than 60
  pages runs in more passes rather than visiting the first 60 and printing a warning to a console
  nobody is watching. The 60 bounds one capture *document*, not an application.
- **Standard** — WCAG 2.2 Level AA.
- ⚠️ **"The page list has changed since the last audit"**, if it has, with how many were added and
  removed and both page counts — because the report's Movement section compares audits, and a
  shrinking page list makes the numbers improve on their own.
- ⚠️ **"You have no machine connected"**, if you have none. The button stays live on purpose: a
  colleague's machine may be connected and the platform only ever reports *yours*.

**What happens then.** The platform opens an audit and hands back a manifest. Opening an audit
visits nothing — it cannot. Your companion claims it, resolves the browser and the scanner out of
the project's own folder, visits each page, posts each screen one at a time, and closes the audit.
Two companions never take the same audit; a companion that *restarts* picks its own audit back up
once the lease passes, but another machine never takes it over — an audit belongs to the machine
that can reach the running application.

✅ **While it is running, an `Audit running` panel leads the screen** — full width, above the page
table, and only while something is actually happening. Three tiles, and the middle one changes with
the stage because what you need to know changes with it:

| Stage | The three tiles |
|---|---|
| Visiting pages | **Pass** *k of m* · **Pages visited** *n of m asked for* · **Would not open** *n* |
| Checking what was found | **Elements judged** *n of m* · **Pages visited** · **Would not open** |
| Complete | **Pages reported** *n of m asked* · **Problems open** *n, c critical · h high* · **Waiting on a person** *n* |
| Could not run | the machine's own reason, in its own words |

✅ **It does not disappear when the audit finishes — it changes what it says.** The team's first
complete run met the old behaviour: the panel they had been watching vanished at the moment the
answer arrived. A complete audit also shows the never-opened banner, if any page was asked for
and never reported, and a way through to the review queue if anything is waiting on a person.

Every number is derived from rows the platform was already writing, so nothing new is recorded to
be able to say this. A page that **would not open** is counted as visited-and-known, not as
progress still to come — it is a result.

⚠️ **Two of these are counted more carefully than they look, and both were wrong first.**

*Elements judged* counts **distinct elements**, not requests. An audit sends one request per
(element, check) slot, and ten Meridian pages are **144 slots but only 81 distinct elements** —
the header, the footer and the nav are the same markup everywhere, they hash identically, and one
verdict answers all ten. Counting verdicts against slots made a complete run read *81 of 144*.

*Problems open* is **this project's** current standing, not this audit's tally, and the tile says
so. A finding carries no audit key — a baseline audit deliberately manufactures no `Run` for its
`last_seen_run` to point at — so counting per audit reported **0 problems on an audit that found
three**. It is also the right scope: the Accessibility baseline is itself project-scoped, so an
audit covering part of an application never drops what is known about the rest.

⚠️ **Until 21 August there was no such panel**, and the only thing on screen while an audit ran was
a status word — in a 320px rail, below seventy-nine page rows. The team's first live run spent
forty minutes on *Checking what was found* with no way to see how far the judge had got, or that
it had stopped. Item **#22 in §9**. ⚠️ **And in its first version the panel disappeared when the
audit finished**, so the answer vanished at the moment it arrived; it now stays and reports what
the audit came to. ⚠️ **The design's live per-page console is still not
built** — the companion posts one screen per call and says nothing between them, so there is no
progress channel for it to read. What it would take is written down in
`GAP_FIX_BUILD_PLAN.md` §9.2 rather than left as an assumption.

**What you should see, in order, in Past audits** — this panel polls every 5 seconds while
anything is in flight, and shows the same status the running panel does, in the same words:

| Badge | Means |
|---|---|
| Waiting for a machine | opened, nothing has claimed it |
| Starting | a machine has claimed it |
| Visiting pages | the browser is walking the list |
| Checking what was found | pages are in; the AI half is running |
| Complete | done |
| Could not run | with the reason underneath, in its own words |

Plus **"N never opened"** when pages were asked for and never reported.

✅ **And, on a finished audit, "N elements were never looked at" with a Check the rest button.**

This is not the review queue's *uncertain*. A check that looked at an element and could not
decide produced a real verdict, and it is a person's to answer. An element that was **never
looked at** — because the pass could not start, or because the judging run ended before reaching
it — is work that did not happen, and the machine can simply be asked again.

**Pressing it visits no page.** Everything the judge needs was stored when the pages were
captured: the markup, the text around it, the computed styles, the accessible name and the
screenshot crop. So this is a second pass over one capture, not a second audit — the audit goes
back to *Checking what was found*, the running panel shows the new pass, and it completes through
the same closing step. Anything it still cannot answer is filed again, and the report says again
that the check was incomplete.

⚠️ **It only appears on a finished audit**, and only when there are some. While a pass is running
the answer is still changing, and re-asking about elements the judge is at that moment working
through would start a second pass over the same work — the API refuses it by name. Same roles as
starting an audit, because it spends a real engine run.

**What would mean it is broken:**

| Symptom | What it means |
|---|---|
| Stuck on *Waiting for a machine* | Nothing claimed it. Companion not running, or not enrolled on this project. |
| *Could not run* — "Playwright could not be loaded from this project … or from the companion's own toolchain" | §3.3 — run `npm install` in `runner/`. Names both places it looked. |
| *Could not run* — "axe-core could not be loaded …" | §3.3 — the scanner is missing from both. The AI half still ran. |
| A page reported with a load error | That page would not open. The platform records it as never seen and — importantly — will **not** let it resolve any existing finding by absence. |
| An audit that says *Complete* with 0 reported | Something answered but produced nothing. Check the companion's console. |
| Stuck on *Checking what was found*, with **Elements judged** not moving | The judging run has stopped. ✅ Since 21 August a judging run that dies **closes its own audit** — it files everything it never answered for human review, publishes the partial report and marks the audit complete, and the report says at the top that the check was incomplete. If it is genuinely stuck instead, the tile is what tells you: the number stops. |

**What it leaves behind:** an **Accessibility baseline** document in Artifacts. One criterion per
line — twenty findings of 1.4.3 across six pages is one row saying *Level AA, High, 6 pages, 20
items*, because the question a baseline answers is "where do we stand on 1.4.3?". It is scoped to
the **project**, not to the audit, so an audit that reached 38 of 50 routes does not silently drop
what is already known about the other 12 — what this pass covered is stated inside the document
instead.

⚠️ **There is no gate on this path.** The accessibility gate binds to the Testing phase, and a
brownfield audit is not a phase run. For brownfield, the thing that plays the part of a gate is
the **signature on the conformance statement**.

---

## 7. The three screens, in detail

These are the same for both journeys. They live under **Accessibility** in the sidebar, as one
destination with three tabs: **Pages & audit**, **Review queue**, **Conformance statement**.

All three tabs are always present. The conformance tab does not appear only once a statement
exists, for the same reason the sidebar item does not appear only after the first run: *"no tab"*
and *"nothing has ever been checked"* would look identical, and the honest empty state is what
tells those apart.

✅ **The sidebar lands on Pages & audit**, which is where the work starts and what the tab strip
has always put first. It used to land on the Review queue — the one tab with nothing on it until
an audit has run — so the first click on the feature showed an empty screen. Item #6 in §9. The
queue's waiting count still rides on the sidebar item, so a reviewer loses nothing.

### 7.1 Review queue — the uncertain findings ⭐ 🔬

**This is the screen most worth your attention.** It is where a person's judgement enters the
system and becomes the platform's answer.

**What is on it:** only findings a check could not settle. Not all findings — the settled ones are
in the report.

**Opening an item claims it**, and holding it open renews the claim. The lock lasts **15
minutes**, and the open item re-reads itself every 5 minutes, which is what renews it. Close the
tab and it lapses by itself —
which is the point: a reviewer who wanders off hands the item back without anyone remembering to
release it. Someone else already on an item is told so by name rather than being allowed to
collide.

**What you see for one finding:**

- The criterion and its plain-language handle.
- The **full page screenshot with the element ringed** — not the element alone. You cannot judge
  whether an alt text is meaningful without seeing what the image is doing on the page (D3).
- The element's markup and the text around it.
- ⚠️ **"This element has a weak handle"** when the selector is fragile — a warning that the
  finding may not follow the element if the page changes.
- **Which test case found it**, on greenfield, linked. Gap **G3** closed: before it, a finding
  said nothing about where it came from, which made the console unreadable on greenfield.
- **Confirm** or **Reject**, with a note.

**What your answer does.** It sticks. A decision holds **until the element itself changes** (D4) —
the same element judged again does not come back to you. Confirming raises a defect; rejecting
records that this is fine, with your note.

**What would mean it is broken:** an item you decided coming straight back; a screenshot that
will not load (it should say *"the capture could not be loaded"*, not show an empty frame); or
the queue count in the sidebar disagreeing with the rows.

✅ **Two empty states now, not one.** A project where something has run says *"An empty queue
means every check so far was sure enough to answer on its own — not that no problems were
found."* A project where **nothing** has ever run says *"Nothing has been checked yet"*, adds
*"nothing here says whether the application is accessible"*, and links to Pages & audit.

⚠️ There was one sentence until 20 August, and it was the first one — vacuously true of a project
where nothing had run, and read as reassurance by the reader who most needed pointing at the
starting line. Item #5 in §9.

⚠️ **Performance, gap G3b, closed.** The queue used to fetch every finding's screenshots and
provenance to draw a list that shows neither. It now fetches five extra pieces of evidence only
when you open one item. Measured: 8 findings went from 40 round trips to 8; 60 findings is also
8. The cost of the list is now flat in the number of findings.

### 7.2 Keyboard journeys — the eight criteria nothing else reaches ✅ 🔬

On the **Pages & audit** tab, below the audit strip. It renders **whether or not any pages are
registered** — a journey follows a *test case*, not the page list.

**Why it exists.** Eight criteria cannot be judged from a page standing still: whether focus can
get out of a menu, whether you can see where you are, whether a screen reader is told when
something changed. They can only be answered by *operating* the application. The industry scanner
covers one of the eight.

**Gap G6 was three separate things, and all three are now closed:**

- **G6a** — it had no address, no browser and nowhere to report. A journey now carries the
  address it was started with, the companion grants it a browser scoped to exactly that origin,
  and a run that ends without finishing closes its journey instead of reading *walking* for ever.
- **G6b** — starting several at once. Each journey gets its **own** hidden work item, so one
  being walked does not refuse the next. Queueing ten costs one scan of the project's test cases,
  not ten.
- **G6c** — a person can start one. Before this, `start_journey_check` had **no caller anywhere in
  the platform**.

**What you do:** check the address, tick the journeys, press **Walk N selected journeys**.

**What the panel says, and why each sentence is there:**

- **No journeys yet** → *"run the Testing phase and they appear here"*. Not an empty table: a
  project whose Testing phase has never run must not look like one with no keyboard problems.
- **The address**, pre-filled and editable, saying where it came from — your last audit, else the
  repository — or what to go and set when the platform holds neither.
- ⚠️ **"Start your application first"**, said *before* the button, because it is the one thing the
  platform cannot do for anyone. Nothing here starts an application, and a walk against an address
  nothing answers on stops immediately and records no steps.
- **"You have no machine connected"**, also before the button.
- **What could not be walked, and why.** A test case declaring `Type: E2E` with no readable steps
  is a different fact from a project with no journeys, and both are shown.
- **What the cap left out, by name.** Up to **10** journeys at a time, at most **40** steps each.
- **After pressing:** what started, and what did not *and why*, each by name.
- **A reader** sees all of it, is told the QA Lead starts them, and gets a disabled button rather
  than one that fails on click.

**Watching it happen.** A journey's work item is hidden plumbing, so **Phases & Runs cannot show
it** — this panel is the only place a person can see a walk in progress. It polls every 15
seconds while any journey is walking, and a journey being walked cannot be ticked again.

**The result badges:**

| Badge | Means |
|---|---|
| Never walked | no walk on record |
| Walking now | dispatched |
| Walked · nothing found | it walked every step and found nothing |
| *n* blocked · *n* finding(s) | it could not complete some steps, and/or found problems |
| Nothing was walked | the run ended having recorded no steps |

✅ **Plus *Waiting for a machine***, for a journey that has been dispatched and that nothing has
picked up — the same words the audit strip above it uses. It is derived from the run's own
dispatch state rather than stored, so it needed no database change, and a journey waiting cannot
be ticked again because it is already spoken for.

⚠️ Until 20 August a journey was marked *walking* the moment it was dispatched and the panel
rendered that as **Walking now**, so one dispatched with no companion online read as a browser
stepping through the application, for ever. Item #4 in §9.

**What would mean it is broken:** a journey that reports *Walked · nothing found* on an
application you know traps focus; a step count of 0; or a walk that stays on *Waiting for a
machine* with a companion demonstrably online.

⚠️ **What it finds never blocks a gate** (D1). It is reported, ticketed and reviewed like
everything else. And it is advisory by **checker**, not by source — so a proven keyboard-trap
check could be promoted to blocking later without dragging seven newer checks in with it.

### 7.3 Conformance statement ⭐ ✅ 🔬

**What is on it:** all **55** Level A and AA criteria, every one of them listed — including the
ones nothing looked at, printed as **not evaluated** and never folded into a supporting result.

Three counts across the top:

| Tile | Means |
|---|---|
| **Evaluated** | something actually checked these |
| **Not evaluated** | stated, never assumed |
| **Awaiting a person** | a check looked and could not decide |

⚠️ On a project with no evidence at all you should see **55 not evaluated** — not an empty
screen, and not an error. That is the correct and useful answer.

**What you do:** set a per-criterion level where you disagree with the suggestion, edit the scope
and the wording, then sign.

- **Any edit clears the signature**, and you are warned before you save. A signature on wording
  nobody signed is worse than none.
- **Signing is the gate** (D7). It is also what unlocks export, and what registers and approves
  the statement as an artifact.
- **New evidence marks a signed statement stale rather than clearing it** (D8) — the header reads
  *Signed · evidence has changed*, and export is blocked with that as its reason.
- ⚠️ The engine, model, prompt and scanner versions are **not** on this screen (D9). They are
  recorded on the signature's audit entry, so a statement can be traced back to what produced it
  without putting our implementation detail on a client's screen.

**What would mean it is broken:** a total that is not 55; a criterion nothing checked showing as
supported; export enabled without a signature; a signature surviving an edit.

✅ Non-reviewers are told *"Editing and signing need the **QA Lead** role on this project"* — the
name, through the label helper the platform already has for exactly this. It showed the raw key
`qa_lead` until 20 August. Item #15 in §9.

---

## 8. The decisions already taken

Recorded so they can be revisited, not re-argued.

| | Decision | Where it shows |
|---|---|---|
| **D1** | Findings from the keyboard journey never block work — reported, ticketed, reviewed. Advisory by **checker**, not by source | The gate's own sentence; §7.2 |
| **D2** | The internal accuracy evaluation gates nothing. It is our report card, not a lever in a client's gate | not on any client screen |
| **D3** | The reviewer sees the whole page with the element ringed | §7.1 |
| **D4** | A reviewer's decision holds until the element itself changes | §7.1 |
| **D5** | A review lock lasts 15 minutes and renews itself | §7.1 |
| **D6** | Capture all four scanner answers, not only violations | §5 A3 |
| **D7** | The signature is the gate | §7.3 |
| **D8** | New evidence marks a signed statement stale rather than clearing it | §7.3 |
| **D9** | Engine, model, prompt and scanner versions are never shown to the tenant | §7.3 |
| **D‑B2** | Page registration is generic to any application, never shaped around one | §6 B3 |
| **D‑B5** | The 60-page limit is solved by running in passes, not by raising the number | §6 B4 |
| **D‑G6** | The keyboard journey must work on **both** journeys | §7.2 |
| **D‑G6b** | On both journeys the **user** starts the application and gives the address. No in-build variant exists, so nothing in this work can affect a build | §7.2 |

---

## 9. The twenty-four findings, and what was done about each

Walking this guide screen by screen turned up fifteen places where what was built worked, but on
reading it as the person using it would not have satisfied them. **The team reviewed all fifteen on
20 August. Fourteen were approved and all fourteen are built; the fifteenth was the migrations,
which the team ran the same day.**

**Three more arrived the same day, and they arrived the best possible way: the team read the two
page-registration dialogs during a live run and told us what they thought each one did.** Both
readings were wrong, and nothing was broken — the words were. A screen understood backwards by the
people who commissioned it is not a screen that works, so #16–#18 are wording, and the wording is
now pinned by tests like any other behaviour. All eighteen are closed.

| # | What was wrong | Status |
|---|---|---|
| 1 | A failed fetch rendered as a confident empty state, on all four screens | ✅ fixed |
| 2 | Page scope and audits were not role-gated at all | ✅ fixed |
| 3 | Nothing accessibility-related has ever been migrated | ✅ run by the team, 20 Aug |
| 4 | A keyboard journey had no *waiting for a machine* state | ✅ fixed |
| 5 | The review queue's empty state assumed checks had run | ✅ fixed |
| 6 | The sidebar landed on the Review queue, not Pages & audit | ✅ fixed |
| 7 | The conformance empty state told brownfield users to run the Testing phase | ✅ fixed |
| 8 | Pasting a page list required JSON | ✅ fixed |
| 9 | The audit needed the app's repo cloned locally, with npm packages in it | ✅ fixed |
| 10 | Two steps numbered "1" on the brownfield hub | ✅ fixed |
| 11 | The coverage numbers everyone was quoting were wrong | ✅ fixed, and pinned |
| 12 | The onboarding gallery showed five steps; the real hub has seven | ✅ fixed |
| 13 | `.diagram-frame` was 2.29:1 contrast in our own design system | ✅ fixed |
| 14 | `in_scope` was not an accepted column, and our own demo app uses it | ✅ fixed |
| 15 | A role key was shown to the user as a role name | ✅ fixed |
| 16 | **Import a list** opened a dialog titled "Add pages" — nearly the other button's name | ✅ fixed |
| 17 | The paste box demonstrated a URL pattern in the one format that cannot carry its example | ✅ fixed |
| 18 | **Add a page** read as though it accepted patterns only | ✅ fixed |
| 19 | An audit opened from the screen was born unclaimable, while the screen said *Visiting pages* | ✅ fixed |
| 20 | The companion died on the audit path, and took the whole machine down with it | ✅ fixed |
| 21 | **Seven of the judge's tools were never exposed** — it had been unrunnable since it was written | ✅ fixed |
| 22 | A running audit had nothing to watch, and a dead judging run stranded its audit for ever | ✅ fixed |
| 23 | A question from a headless run could be counted but never answered | ✅ fixed |
| 24 | Two tests still asserted a world #9 had replaced, and a `·` the Windows console cannot print | ✅ fixed |

**#19–#24 are a different kind of finding from the first eighteen, and the difference matters.**
Those came from *reading* the screens. These came from *running* them, and five of the six are
defects rather than wording — three of which had a green test suite standing over them the whole
time. The full account, including why each survived its tests, is
`GAP_FIX_BUILD_PLAN.md` §9; the entries below are the short version.

---

### #1 — A failed fetch rendered as a confident empty state ✅

**Was:** all four accessibility screens loaded a list and none handled the error case. On a
failure the data was undefined, the list fell back to empty, and the screen rendered its empty
state — *"No pages are registered yet"*, *"Nothing is waiting on you"*, *"There is nothing to
compile yet"*, *"No journeys to walk yet"*. The one thing this capability exists to refuse,
happening at the outermost layer of the screens that make the argument. And not hypothetical:
while the 32 migrations were still pending that morning, it is exactly what the first person to
open the feature would have been told.

**Now:** one shared `LoadFailed` panel and four error branches. It carries the platform's own
message, a **Try again** button, and the line that does the work: **"Nothing shown here is a
statement about your application."** Without that sentence a reader still walks away with an
impression of their application, formed from a screen that had no data at all.

*New file `LoadFailed.tsx`; branches in `A11yAudit.tsx` (×2), `A11yReview.tsx`,
`A11yConformance.tsx`. Proven by five tests in `resilience.test.tsx`, one per screen plus one
asserting the journeys panel can fail without taking the page list with it.*

### #2 — Page scope and audits were not role-gated at all ✅

**Was:** `a11y_routes`, `a11y_route_item` and `a11y_audits` were not in the permission list, so
they fell through to the viewset default — `AllowAny`, which does not even require a session —
while starting a keyboard journey on the same screen was refused for anyone but the reviewer.
No role check inside `register_routes`, `update_route`, `delete_route` or `start_baseline_audit`
either. Nothing escaped the tenant, so this was never a cross-customer hole; it was an
inconsistency on top of the input every later number depends on, because a page quietly taken out
of scope makes the next baseline read as an improvement.

**Now:** `policy.PAGE_MANAGE_ROLES` is **QA Lead, Tech Lead or Admin** (team decision, 20 August),
with the tenant-admin carve-out `can_review` already used. Checked in the view rather than inside
the service functions, matching `repositories` — because the same `register_routes` is what
onboarding will eventually use to write a discovered list with no acting user, and a mandatory
check inside it would have no honest answer for that. The GET payload carries `can_manage`, so a
reader gets the whole screen with disabled controls and a sentence saying whose call it is, rather
than controls that 403 on click.

*`policy.py`, `review.can_manage_pages`, four call sites in `views.py`, the page/run controls in
`A11yAudit.tsx`. Proven by 22 tests in `test_a11y_scope_rest.py` and five in `audit.test.tsx`.*

### #3 — Nothing accessibility-related had ever been migrated ✅

32 pending, including `a11y/0001` and the two that seed the judge and journey agents — so on the
shared server the accessibility tables did not exist and neither agent had a spec. Not a code fix;
a deployment decision, and the team's.

**Run by the team on 20 August.** Re-read afterwards: nothing pending, in any app. §1 has the
list of what landed.

### #4 — A keyboard journey had no *waiting for a machine* state ✅

**Was:** the row was marked `WALKING` at dispatch — correct, the platform has handed the work
over — and the panel rendered that as **Walking now**. A journey dispatched with no companion
online read as a browser stepping through the application, for ever, while the audit strip six
inches above told the same two states apart.

**Now:** a fifth badge, **Waiting for a machine**, in the audit's own words. **Derived, not
stored, so it needed no migration**: a dispatched run carries `inputs.dispatch.status`, which the
work-claim endpoint flips from `pending` to `claimed`. One query for the whole list, and only for
the rows claiming to be in flight — a finished walk is finished however it was dispatched. A
waiting journey cannot be re-ticked, and the panel keeps polling until something takes it.

*`journey._claimed` + `QUEUED`, `journeyResult`, the poll predicate. Proven by three tests in
`test_a11y_journeys_rest.py` and two in `journeys.test.tsx`.*

### #5 — The review queue's empty state assumed checks had run ✅

**Was:** one sentence — *"every check so far was sure enough to answer on its own"* — shown to
every reader including one whose project had never run anything. Vacuously true, and read as
reassurance. It was also the first accessibility sentence a new user ever saw, because of #6.

**Now:** the queue payload carries `ever_checked`, and there are two empty states. **Asked only
when the queue is empty**, because that is the only time the answer changes anything and two
extra `.exists()` on the busiest accessibility screen every poll would be a real cost for an
answer nothing reads.

*A screen scan **or** a finding counts as having looked — a keyboard journey writes findings and
never writes a scan, so asking only about scans would tell a project that had walked every journey
that nothing had been checked. Proven by four tests in `test_a11y_scope_rest.py` and two in
`resilience.test.tsx`.*

### #6 — The sidebar landed on the Review queue ✅

**Was:** `AppShell.tsx` pointed **Accessibility** at `/a11y`, while the tab strip's own comment
said Pages & audit is first *"because on a brownfield project this is where the work starts"*. So
the first click on the feature went to the one tab with nothing on it until much later.

**Now:** `/a11y/pages`. The queue's waiting count still rides on the sidebar item.

### #7 — The conformance empty state sent brownfield users to the Testing phase ✅

**Was:** *"Run the testing phase on this project"* — the wrong instruction for an existing
application, whose route to evidence is an audit. Doubly wrong because, per #1, that text only
ever appeared when the request had failed.

**Now:** the failure is #1's, and the true empty state names both roads and links to Pages &
audit, which is where each of them starts.

### #8 — Pasting a page list required JSON ✅

**Was:** one path per line — the most natural thing to paste, and the first thing anyone does on
this screen — was refused, with a message explaining JSON to somebody who had just pasted a
perfectly clear list of pages.

**Now:** text that does not open with `[` or `{` is read as one path per line. Blank lines and
`#` comments are skipped; quotes and trailing commas are stripped, because they belong to the
other format. **A line containing a space is refused, by line number** — the path checker rejects
an empty path, a full URL, a path not starting with `/` and a line break, but not a space, and
`Home /catalogue` would otherwise register a page that cannot exist and be reported unreachable
forever. That is the exact hole that killed an earlier line-per-path form, closed rather than
reopened. A malformed JSON list still gets the JSON error; line mode does not swallow it.

*`routes._read_lines`, and the box's own help text. Proven by six tests.*

### #9 — The audit needed the app's repo cloned locally, with npm packages in it ✅

**Was:** the audit resolved its browser and scanner out of the audited project's `node_modules`
and **refused** without a local clone. A Django, Rails or .NET application has none, so the only
way to audit one was to add a `package.json` and two npm dev-dependencies to the client's own
repository in order to look at it — which many clients will not permit, and which is a strange
thing to ask of a product that promises to audit an application it did not build.

**Now, in three pieces:**

1. **The companion has its own pinned toolchain** — `runner/package.json`, `playwright 1.62.1`
   and `axe-core 4.13.0`, installed once per machine with `npm install && npx playwright install
   chromium`. The audit script has had a fallback import since its first version, resolved from
   its own directory upward; **nothing had ever been installed for it to find.** This is what
   turns it from dead code into the answer for a non-Node stack.
2. **A missing clone is a fallback, not a refusal.** The project's own copy is still tried first
   and still wins, so an application that ships its own axe is scanned with the version it ships.
   Where there is none, the audit runs from a companion-owned scratch folder, one per project so
   two audits cannot fight over one candidates file. **A brownfield audit no longer needs a
   repository at all.**
3. **The report says which copy it used.** A fallback scan records `axe-core 4.13.0 (companion)`.
   The suffix rides on the version string that already travels everywhere a version is shown — per
   screen, in the report, onto the signed statement — so there is no new field, no migration, and
   no display that can forget to mention it. **Without this piece the fix would have traded a
   visible limitation for an invisible lie**, naming a version the client's application does not
   ship.

*Both missing-tool messages now name both places they looked. `runner/package.json` (new),
`daemon._a11y_scratch`, `a11y_audit.mjs`, and the screen states the prerequisites before the
button. Proven by six tests.*

### #10 — Two steps numbered "1" on the brownfield hub ✅

The prerequisite card showed `1`, and so did *Upload resources*. It now shows `!` when the machine
is not connected and `✓` when it is, so the numbered list reads 1–7 with nothing repeated.

### #11 — The coverage numbers everyone was quoting were wrong ✅

*"The AI half covers 11 of 55"* is the ownership **registry's** classification. Four checkers are
built and they cover **five**; the other six are Phase 2, which the task backlog has said all
along. And *"22 criteria only a person can assess"* is **23** — 2.4.7 is registry-owned by `ai`
and covered by the keyboard journey, so counting it in both makes the human remainder one too
small.

**Corrected throughout this guide, and pinned in code.** Two tests assert the built checkers, the
journey criteria, the registry's own counts, and the arithmetic that follows — 7 of the 8 journey
criteria human-owned, 23 human-only remaining, 27 distinct with automated evidence. Change either
list and a test fails, so the next person has to restate the number rather than leave a stale one
in a proposal.

### #12 — The onboarding gallery showed five steps ✅

The design-gallery fixture kept the original five while the real screen grew to a prerequisite
card plus seven, so every design review and every journey test ran against a screen that no longer
existed. All three gallery states now mirror the live hub, with a note saying to change them in
the same pass.

### #13 — `.diagram-frame` was 2.29:1 contrast ✅

`--text-faint` on `--bg-subtle`, in our own design system, under the 4.5:1 this product exists to
enforce. Flagged three times. Now `--text-body`, which is 8.86:1 — the value the neighbouring
`.shot--missing` rule already used, with a comment pointing at this component as the defect.

### #14 — `in_scope` was not an accepted column ✅

Our own reference brownfield application writes `in_scope` for all 79 of its routes. Every one
came back as an unrecognised column and every page was registered in scope, including the one its
author had deliberately excluded.

⚠️ **And the obvious one-line fix was wrong, which is worth recording.** `ENTRY_KEYS` fed the
*ignored-keys warning* and nothing else; the field reads were a separate list of names. Adding the
alias there alone silenced the warning and changed nothing — strictly worse than before, because
`in_scope: false` would then have been ignored with nothing said about it. A test caught it. The
field reads now go through `ENTRY_KEYS` too, so a key the warning treats as recognised is a key
something actually reads.

### #15 — A role key was shown as a role name ✅

*"Editing and signing need the qa_lead role"* → *"…the QA Lead role"*, through the `roleLabel`
helper that exists for exactly this and was written after an earlier bug of the same kind.

### #16 — The button and the dialog it opens had different names ✅

**Was:** the **Import a list** button opened a modal titled **"Add pages"** — which is nearly the
name of the *other* button on the same screen. A person who pressed Import a list arrived somewhere
that read like the single-page form and could reasonably think they had misclicked.

**Now:** the dialog is titled **Import a list**, after the button that opens it. A test asserts the
heading matches, and that "Add pages" is gone.

**Also fixed alongside it:** the empty state now names *which* button to press — *"If you already
have the list — a routes file, a sitemap, a page inventory — import it. Otherwise add them one page
at a time."* Two buttons that both add pages, with nothing anywhere saying what separated them, was
the reason the question was asked at all.

### #17 — The paste box taught the one combination that cannot work ✅

**Was:** the placeholder read `/` · `/catalogue` · `/catalogue/:id` — a **pattern**, demonstrated in
**line** mode. Line mode returns bare paths (`_read_lines`), so there is nowhere to say what
`/catalogue/:id` should open. Following the example registers a page no browser can open, and every
audit afterwards reports it unreachable. The placeholder demonstrated the single combination the
platform cannot honour.

**Now:** the placeholder shows **both accepted formats**, and the pattern appears only in the JSON
half — the half that can carry `example`:

```
/
/catalogue
/about/history

— or a JSON list —

[{"path": "/catalogue", "title": "Browse the catalogue"},
 {"path": "/events/:id", "example": "/events/482"}]
```

Showing both was the team's own requirement, and it is what makes the placement meaningful: the two
formats sit side by side, and the pattern is visibly in the one that works. The help now says so in
words — *"A path no browser can open needs the JSON form, because only it can carry the example page
to visit."* A test splits the placeholder on the separator and asserts nothing pattern-shaped is in
the line half and `example` is in the JSON half.

⚠️ **Both formats were always accepted.** The team's recollection that the box was JSON-only was the
opposite of the truth: JSON-only was the *bug*, fixed as #8 on 20 August. Nothing about acceptance
changed here — only what the box shows you.

### #18 — "Add a page" read as though it were for patterns only ✅

**Was:** the Example page help began *"Only for a pattern like `/events/:id`, which no browser can
open."* Read on its own — which is how anyone scanning down a form reads it — that describes the
**dialog**, not the field. Two people concluded the form accepted patterns only, and asked how they
were meant to add an ordinary page.

**Now:** it begins **"Leave this empty for a normal page."** — the case that applies to nearly
everyone, said first — and only then explains what the field is for.

**And it names three pattern shapes, not one**, because the platform never parses patterns at all:
`normalise_path` requires a leading `/` and checks nothing else, so `/events/:id`, `/books/[isbn]`
and `/users/{id}/loans` are stored exactly as written. Naming one framework's syntax made it read as
the only syntax allowed. The real rule is *"if the path as written cannot be opened, give one that
can"*, and that is now what it says.

### #19 — An audit could not be claimed by anything ✅

**Was:** an audit opened from the screen was created as `capturing` — "a machine is already
visiting" — and the claim endpoint only ever offers `pending` audits (or a stale `claimed` one). So
no companion could see it, ever. It sat there while the screen showed **Visiting pages**, which is
this capability's own worst failure: a confident report of work that was not happening.

**Now:** the POST passes `claimable=True`, so an audit opened from the app waits as *Waiting for a
machine* until something takes it. The companion's own `audit` subcommand still leaves the default,
because there the machine that opened it is already standing there.

⚠️ **The tests were green throughout**, and asserted exactly the right behaviour — of a call the
product never made. `claimable=True` appeared nowhere outside test code.

### #20 — The companion died on the audit path, taking the machine with it ✅

**Was:** every other companion path called `ensure_backend_importable()` before touching platform
code; the serve→audit path did not, so an audit failed with `ModuleNotFoundError: No module named
'apps'`. Worse, the serve loop caught only `DaemonError`, so an unexpected exception ended the whole
companion — every other kind of work on that machine with it — and the audit was left open for ever.

**Now:** the import call is there, and the guard catches anything, closing the audit with a
plain-language reason first. **This is the widest change of the six**, and it is recorded as such:
widening a serve-loop guard is a blunt instrument, taken because one bad audit must not stop a
machine.

### #21 — Seven of the judge's tools were never exposed ⭐ ✅

**Was:** the judge was **granted** 24 tools, and the MCP server it actually talks to **defined 17**.
`get_a11y_batch`, `get_wcag_grounding`, `record_a11y_finding` and all four keyboard-journey tools had
no `@server.tool()` wrapper, and `get_a11y_screenshots` had quietly dropped `run_id`. **The judge and
the keyboard journey had therefore been unrunnable since the day they were written** — the agent
reported it had no way to read its work, and it was right.

**Now:** the seven wrappers exist, `run_id` is back, and — the part that matters more — a test
computes `granted − exposed` as a set difference and fails if anything is in it.

⚠️ **Why nothing caught it, and the lesson.** There are **three** lists that look interchangeable and
are not: the companion's tool *grant*, the HTTP route's *executable* map, and the MCP server's
`@server.tool()` definitions. Only the third puts a tool in an agent's hands. Every test checked one
of the first two.

### #22 — A running audit could not be watched, and a dead one was never closed ✅

**Two halves of one silence, and they are the reason the first live run had to be diagnosed from the
database.**

**Was, half one:** S-38 designs a full running panel; what existed was a status word in a list, in a
320px rail that never collapsed, below seventy-nine page rows. An audit that had visited six of ten
pages and one that had visited none looked identical.

**Was, half two:** when a run reports failure, the workflow returns at its failure branch
**before** the step that does the judge's accounting. So nothing it had left unanswered was
recorded, no report was published, and the audit read *Checking what was found* permanently.

**Now:** the panel's three tiles are built, including **Elements judged** — the number that could
not be seen at all — and the panel stays after the run ends rather than vanishing at the moment
the answer arrives. And a judging run that dies closes its own pass: everything
unanswered is filed for a person, the partial report is published saying it is partial, and the
audit is completed. That closure sits one line below the keyboard journey's identical one, which had
been on that path since G6a with the judge's never added beside it.

⚠️ **The live console is still not built.** See §6 B4 and `GAP_FIX_BUILD_PLAN.md` §9.2, which says
what it would take rather than leaving it as an assumption.

### #23 — A question from a headless run could be counted but never answered ✅

**Was:** the sidebar badge counted the project's pending questions on the server; the Clarifications
page fetched the tenant's and narrowed them to the work items on the **visible backlog**. A run on a
hidden carrier work item — accessibility judging, code indexing, the gap report — is deliberately
absent from that backlog, so its question was counted by one and hidden by the other. The badge said
**1**, the page said **none**, and the run waited for an answer nobody could give.

**Now:** the page asks the API for the project's questions — a filter that endpoint already had —
instead of narrowing them in the browser, and takes the work item's name from the clarification
itself, so a judging run's question reads *"Accessibility judging"* rather than eight characters of
uuid. Hiding plumbing from a board is right; hiding a question that blocks a run is not.

### #24 — Two stale tests, and a character the Windows console cannot print ✅

**Two small ones, together because neither is worth its own section.**

**The tests:** `test_a_folder_with_nothing_installed_…` and `test_the_scanner_alone_missing_…` both
asserted the **pre-#9** world, where a project folder with nothing installed was refused. #9
deliberately ended that. They only passed while nobody had run `npm install` in `runner/` — and
committing the lockfile made that setup standard, so they went red for everyone. Rewritten to assert
what #9 built, with the refusal they were protecting now covered by its own test, which runs the real
script from a copy stranded where nothing can resolve above it.

**The character:** the companion printed `10 page(s) · 1 pass(es)`, and a Windows console redirected
to a file cannot encode `·`, so the log read `10 page(s) ? 1 pass(es)`. Six lines across four
companion files now use ASCII. Only what the companion prints changed; nothing that travels to the
platform did.


### #25 — An audit whose machine went away could never end ✅

**Found on the live run of 21 August**, by the operator's computer restarting mid-audit. One page
was in; nothing else ever came. The audit stayed `capturing` and the screen went on saying
**Visiting pages** about a machine that no longer existed.

**The claim lease already recovers a dead companion's work — but only from `pending` and stale
`claimed`.** An audit reaches `capturing` the instant its first screen lands, and past that line
there was no lease, no timeout and no cancel. Worse, nothing renewed an audit's lease at all:
`claimed_at` was stamped once at claim and never touched again, so audit liveness was not being
tracked in the first place.

**Three parts.** The heartbeat now renews the lease on the audit a companion is *capturing*
(capped off `created_at`, so no migration). A capture nothing has been heard from for the lease
is closed as `failed` with the machine's own reason — swept from the companion's heartbeat and
its claim, both of which are already writes, so reading the audit list never writes to it.
Liveness counts *either* signal, the heartbeat or a screen arriving: heartbeat alone would depend
on a companion mode that might not heartbeat, screens alone would kill an audit stuck on one very
slow page. And the screen derives `stalled` on read, never written, so a computer switched off
for good still produces an honest panel rather than a permanent lie.

**Failed, not judged and not resumed** — a report from four of twelve pages would state a
position about an application most of which was never looked at, and re-visiting captured routes
needs a resumption design that does not exist. A fresh audit costs minutes.

⚠️ **The near-miss.** The first version also swept `claimed`, and broke an existing test that was
right to break: a `claimed` audit has captured nothing, and the lease hands it to the next machine
that asks, so it simply runs. Failing it would have turned a working recovery into a manual
restart. Abandonment applies to `capturing` alone.

**It closed the live one itself.** The plan was to close the stuck audit by hand; by the time that
ran, the companion's own heartbeat had already done it at 04:38:36 — `opened: 1`, eleven pages
listed as never reported, reason in the machine's words.



### #26 — A pass that stopped at its limit said nothing, anywhere ✅

**Found on the live run of 21 August.** Twelve pages came to 205 element slots against a cap of
200, so the dispatch stopped and deferred 5. It wrote an honest sentence into the audit's own
summary — *"Stopped at this run's limit of 200 — 5 item(s) still need judging"* — and **nothing
read it**: not the screen, not the run report, not the published baseline. The audit would have
closed as **complete**, shown *12 of 12 pages reported*, and never said part of it was unchecked.

**And the "Check the rest" button would not have appeared either.** `unanswered_counts` counted
elements no judge could be asked about, and elements a run was given and dropped. Cap-deferred
elements are neither: never dispatched, never filed.

**The fix asks the direct question.** An element of this capture with **no verdict at all** is
unanswered — no judge, run dropped it, or the dispatch stopped short, all one rule instead of
three categories to keep in step. An element that *was* answered stays answered, a real
`uncertain` included: that belongs to the person in the review queue. The finished audit now
renders the dispatch's own reason, as a banner on the panel and a line on the row.

⚠️ The count on the button is in **slots**, the only number the summary keeps, and repeated
chrome is several slots and one element — so it can read high where the tail of a capped pass
was markup the cache can already answer. The re-judge recomputes in elements and is what acts.

### #27 — The onboarding step called a running audit a finished one ✅

**Reported by the team from the same run.** The hub read **"1 audit run — open the report from
Artifacts"** while the audit was still judging. There is no report to open until judging ends:
the baseline is published when the judge run closes, deliberately, so it never states a position
that is still changing.

`audits_run` now counts finished audits only, with a separate `running` beside it — the same
`{status, running}` pairing the Index code step already uses, because the tick switches on one
and the sentence has to be able to say *"and another is going right now"* over the top of it.
Four states, four tests: running says so and offers no report; finished is done; finished-plus-
running keeps the tick and adds the sentence; a failed audit leaves the step simply *ready*.

**The team's note is the lesson worth keeping:** *when you fix something, consider everything
else it touches so those behave accordingly.* The audit screen had been taught to tell the truth
about a running audit three separate times, and the hub two clicks away was still reading the
old count.



### #28 — One of the four checks had never run ⭐ ✅

**The most important defect this feature has had**, found on the live audit of 21 August — not by
a failure, but by a number that had always been zero.

```
checker slots, every audit ever run on this project:
color 173   ·   semantics 47   ·   alt 22   ·   label 0
```

`_applies_label` requires a computed accessible name, deliberately: 2.5.3 compares the name a
screen reader announces against the visible text, and with no name there is nothing to compare.
That name came from `page.accessibility.snapshot()` — **an API Playwright has since removed**. It
threw on every element; `fillAccessibleNames` wrapped each element in a bare `catch {}` written
for one awkward element, and it swallowed the total failure just as quietly. **0 of 242 stored
elements had a name.** So **2.5.3 Label in Name** — the check with most to say that only a person
can settle — was off from the day it was written, and the always-empty review queue was the
symptom.

**Four parts.** `locator.ariaSnapshot({ timeout, depth: 0 })` restores the name — measured first
against a real browser at ~6ms an element, with an explicit timeout because that call otherwise
waits for ever and one stale selector would stop an audit. The parse is anchored at `- role
"name"` so it cannot read a quoted word out of an element's own text and invent a name, which is
worse than having none. The platform then counts, on every audit, how many *nameable* elements
came back named, and says *"One of the checks could not run"* when none did — so this can never
hide again, and it is named apart from the cap warning because it must never read as "the
application has no label problems". Finally the "check the rest" count moved to distinct elements,
after the finished audit showed that its 5 deferred slots were repeats that had lost nothing.

⚠️ **An existing test caught a mistake in the fix**, and it was right to:
`test_asking_again_when_everything_has_been_looked_at_starts_nothing`. "No verdict anywhere" only
means *ask again* once a pass has run — a capture that has never been judged needs its **first**
pass, not a second.

**Not yet proven live.** `/account/card-services` should produce seven label candidates on the
next run, and that is where the first real `uncertain` is expected.


---

## 10. What has run live, what has not, and what I am least sure about

**This section used to open *"nothing has ever run live, not once"*. That is no longer true**, and
the correction is the most important one in this guide.

### 10.1 What has now run live ✅

Meridian Library, 20/21 August, a real browser on a real machine:

| | Proven by watching it |
|---|---|
| **Registering a page list** | 79 routes pasted from `routes.json`, `/health` honoured as out of scope, 10 put in scope |
| **Opening an audit and having a machine claim it** | *Waiting for a machine* → *Starting* → *Visiting pages*, on a companion enrolled on that project |
| **The capture** | 10 of 10 pages visited, twice, with elements, styles, accessible names and screenshots posted one screen at a time |
| **The scanner resolving out of the audited project** | Meridian's own axe, not the companion's — the report says so by *not* saying `(companion)` |
| **Real AI verdicts** | 80 pass, 1 fail — including `<img id="photo-interior" … alt="library">` against 1.1.1 at 0.92 confidence, with the replacement text proposed. **That is a defect no scanner on the market can find**, which is the entire argument for this build, demonstrated once against a real page. |
| **An audit reaching `complete`** | with its baseline document in Artifacts |

✅ **A judging pass, start to finish.** On **21 August** the whole brownfield journey ran end to
end: 10 of 10 pages visited, none that would not open, **every distinct element judged**, the
report published and the audit `complete`. 80 pass, 1 fail — the `alt="library"` defect above.

⚠️ **And this corrects what was said about the 20 August run.** It was read as having died at
"81 of 144" with 63 elements lost. It had not: an audit sends one request per (element, check)
slot, and those ten pages are **144 slots but 81 distinct elements** — the header and footer are
the same markup on every page and one verdict answers all ten. The judging had finished; the only
thing broken that day was that the workflow never closed the audit, which is item #22. Nothing
was ever lost, and no re-judge was needed.

### 10.2 What is still unproven 🔬

**Ranked by how likely I think a live run is to surprise us:**

1. **The greenfield capture.** It is generated by an agent from a written contract, not run from
   a script we ship. The contract is right and enforced on ingest; whether every generated suite
   honours it is unknown. The tell is a report where nearly everything reads *not evaluated*.
2. **The keyboard journey.** Eight criteria, one agent, a real browser, a live application. ⚠️ It
   has never opened a page — and until #21 it **could not have**, because four of its tools were
   never exposed to the agent at all. It is the least-proven part of this build by a distance.
3. ~~**A judging pass that finishes.**~~ ✅ **Answered on 21 August** — see 10.1. About 27 minutes
   end to end, all of it on one unbroken connection.
4. **Two passes over 68 pages.** The pass loop is tested; a 68-page run against a live Express
   app is not. Ten pages is the small case.
5. **The conformance statement against real evidence.** All 55 criteria have been rendered from
   test data; none from a real audit's findings.

⚠️ **A real `passes` array is no longer on this list.** The scanner returned positive evidence
into the platform on the live run — that one is answered.

### 10.3 What is proven by tests, and how much

Verified on this branch on **21 August**, after all twenty-four findings were fixed:

| Ran | Result |
|---|---|
| `test_a11y_baseline.py` + `test_a11y_judge.py` + `test_a11y_scope_rest.py` | **246 passed** |
| `test_a11y_journey.py` + `test_a11y_review.py` | 129 passed |
| `test_a11y_review_rest.py` + `test_a11y_conformance_rest.py` + `test_a11y_capture.py` | 123 passed |
| `test_a11y_journeys_rest.py` | 9 passed |
| `test_a11y_wcag.py` (the two pinning tests) | 2 passed |
| `test_companion_runner.py` (includes the granted-minus-exposed guard) | 6 passed |
| The whole frontend suite | **336 passed across 20 files**, `tsc -b` clean |

⚠️ **Two tests in that set were failing until 21 August**, and for everyone: they asserted the
pre-#9 world. Item #24. They are green now.

⚠️ **Failures elsewhere in the repository**, all pre-existing and none accessibility:
`test_guardrails.py::test_run_build_clean_change_reports_ok` fails because this machine has no git
remote to push to; there is Claude Agent SDK API drift in `test_drivers.py`; and `npm run lint`
reports one unresolved rule reference in `Gates.tsx`. **No task has been raised for any of them.**

⚠️ **The backend suite is never run whole** — it is killed by the machine. Only the files a
change touches are run, which is what the table above lists.

⚠️ **And the lesson of 20 August, which this section exists to keep in front of everyone:** three
of the six defects that run found had a **green test suite standing over them the whole time**. A
passing test proves the thing it tests. It does not prove the product ever calls it — #19 — nor
that the list it checks is the list that matters — #21 — nor that the fixture resembles the real
case — the batch that was 144 elements where every test used three.

---

## 11. Appendix

### 11.1 Screens

| Screen | Route |
|---|---|
| Pages & audit, and keyboard journeys | `/a11y/pages` |
| Review queue | `/a11y` |
| Conformance statement | `/a11y/conformance` |
| Brownfield onboarding hub (step 6 links here) | `/onboarding` |

### 11.2 Endpoints

| | |
|---|---|
| `GET/PUT /api/projects/<p>/a11y-routes/` | the page list |
| `GET/POST /api/projects/<p>/a11y-audits/` | audits; POST opens one and returns its manifest. GET carries live `progress` for anything in flight and `unanswered` for anything finished |
| `POST /api/projects/<p>/a11y-audits/<a>/rejudge/` | ask again about the elements of one finished audit that nothing ever looked at. Visits no page |
| `GET/POST /api/projects/<p>/a11y-journeys/` | journeys; POST starts up to the cap and names what it did not start |
| `GET /api/projects/<p>/a11y-review/` | the queue |
| `GET /api/projects/<p>/a11y-conformance/` · `PUT` · `POST …/sign` · `POST …/export` | the statement |
| `GET /api/projects/<p>/a11y-backlog/` | what to fix first |
| `GET /api/projects/<p>/a11y-policy/` | this project's effective policy |
| `GET /api/runner/a11y-audits/` | the companion claims an audit here |

### 11.3 Limits

| | |
|---|---|
| Registered pages per project | 200 |
| Pages per capture document (⇒ per pass) | 60 |
| Elements per screen | 600 |
| Element judgments per judging run | 200 |
| Keyboard journeys started at once | 10 |
| Steps per journey | 40 |
| Review lock | 15 minutes, self-renewing |

### 11.4 Severity

Derived from the criterion's WCAG level, never from the scanner's own vocabulary: **Level A →
Critical, AA → High, AAA → Medium.** The scanner's `impact` (`critical`/`serious`/`moderate`/
`minor`) stays visible beside it in reports but is never what the gate blocks on — a policy naming
`serious` is refused with a message saying where that word does belong.

### 11.5 Standard

WCAG 2.2, 55 Level A and AA criteria: **31 Level A, 24 Level AA.** The dataset ships with the
platform (`apps/a11y/data/wcag22.json`) and is loaded by migration.

### 11.6 The ten gap-fix tasks, and what each closed

| | Closed |
|---|---|
| **G1** | Greenfield recorded only what failed |
| **G4** | Every test run left a plumbing task on the user's board |
| **G5** | The Testing agent might never see the screen list |
| **B3** | The application address had to be typed again |
| **B5** | An audit stopped at 60 pages |
| **G2 + G2b** | The platform could not tell a WCAG test case from any other |
| **G3** | A finding did not say which test case found it |
| **8a + 8b** | The audit screen, the way in, and a page editable a row at a time |
| **G3b** | The review list fetched evidence nobody read |
| **G6a/b/c** | The keyboard journey had no address, no browser, no way to run several, and no caller |

And on **20 August**, the fourteen findings in §9 — the ones that separated *"a person can reach
it"* from *"a person is well served by it"* — followed, the same day, by three more (#16–#18)
that the team found by reading the page-registration dialogs aloud during their first live run.

**And then the run itself, which found six more (#19–#24)** — the ones that separated *"a person
is well served by it"* from *"it runs at all"*. Three of those six had passed every test they had.

Plus one found by cross-checking rather than by a failing test: **two journeys from test cases
with no `TC-…` id shared one work item**, so the second was refused as "already being walked" and
each showed the other's last walk. Keyed on the artifact now.

### 11.7 Related documents

| | |
|---|---|
| `GAP_FIX_BUILD_PLAN.md` | the ten tasks, in full, with what each build got wrong along the way — **and §9, the first live run: why each defect it found survived a green test suite, plus the two things recorded rather than built (the live console, and re-asking the machine about what it never judged)** |
| `TASK_BACKLOG_QA.md` | the 31 original tasks and their acceptance criteria |
| `RESEARCH_CORRECTIONS.md` | where the research reports disagreed with the platform |
| `USER_JOURNEYS.md` | the nine journeys, rewritten 20 August against what the code does — each marked built, part-built or not built |
| `docs/design/screens/S-38-a11y-audit.html` | the approved wireframe for Pages & audit |
