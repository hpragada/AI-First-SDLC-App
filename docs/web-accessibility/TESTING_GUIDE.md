# Web Accessibility — What Was Built, Where It Sits In The Journey, and How To Test It

**For the Edvensoft team · updated 31 August 2026 · branch `Eval-accuracy`**
**Covers QA‑01 … QA‑24 (31 tasks), the ten gap-fix tasks G1 … G6c, the eighteen
user-experience fixes of 20 August, the seventeen that five live runs found on 20–21 August,
the three that came out of the capture-scope question on 24 August, the eight from reading the
screens on 25 August, and the five (#54–#58) from the first audit at real size on 31 August (§9)**

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
(`apps/a11y/data/ownership.json`) *classifies* as AI-owned. **Six checkers are built**, and they
cover **six** criteria. The rest are Phase 2 — which the task backlog has said all along, in
QA‑02b's known limitations. The guide simply quoted the wrong number.

**Updated 16 September 2026.** This section said four checkers covering five criteria. It has been
six since `structure` was added on 24 August and `graphics` on 27 August (`A11Y_CHECKER_CRITERIA`
in `backend/integrations/types.py`, `CHECKERS` in `backend/apps/a11y/checkers/rules.py`).

| Checker | What it is | Criteria it can speak to **today** | Registry says it owns |
|---|---|---|---|
| **Rule scanner** | The industry-standard **axe** engine, running inside the page and measuring things | **14** | 14 |
| **AI checks** | Six checks that read a captured element and form a judgement: `alt`, `semantics`, `structure`, `color`, `label`, `graphics` | **6** — 1.1.1, 1.3.1, 1.4.1, 1.4.11, 2.5.3, 4.1.2 | 11 |
| **Keyboard journey** | An agent that operates the running application with only the keyboard | **8** — 2.1.1, 2.1.2, 2.4.3, 2.4.7, 2.4.11, 3.2.1, 3.2.2, 4.1.3 | 8 |

**So the honest total: 27 of the 55 criteria have some automated evidence today. 28 do not.**
1.4.11 is counted once, in both of the first two rows: the scanner measures whether you can see
where the controls are, and `graphics` judges whether the meaningful parts of icons and diagrams
can be made out. Neither half covers the criterion alone. `semantics` and `structure` likewise
share 1.3.1, asking different questions about it.

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

Accessibility **evidence** enters at **Test Automation** and is not a phase of its own. There is
no "accessibility" button on the phase picker and there should not be — the evidence is a
by-product of the suite that was going to run anyway.

One thing does happen earlier, and it is not automated: the **UX Design** gate carries a
22-question WCAG 2.2 checklist (`backend/apps/gates/wcag.py`), plus 5 criteria a project can
switch on, answered by the reviewer looking at the design. Nothing reads a wireframe and judges
it — see `USER_JOURNEYS.md` J2.

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
3. **Every element** the six AI checks might apply to — its markup, the text around it, six
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

The platform picks up what was captured, selects the elements each of the six checks applies to,
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

## 9. The sixty-five findings, and what was done about each

Walking this guide screen by screen turned up fifteen places where what was built worked, but on
reading it as the person using it would not have satisfied them. **The team reviewed all fifteen on
20 August. Fourteen were approved and all fourteen are built; the fifteenth was the migrations,
which the team ran the same day.**

**Three more arrived the same day, and they arrived the best possible way: the team read the two
page-registration dialogs during a live run and told us what they thought each one did.** Both
readings were wrong, and nothing was broken — the words were. A screen understood backwards by the
people who commissioned it is not a screen that works, so #16–#18 are wording, and the wording is
now pinned by tests like any other behaviour. All eighteen are closed.

**#19 onward came from running it.** Seventeen more, found across five live audits of Meridian
Library on 20–21 August by people watching the product work — the last of them by reading the
conformance statement those audits produced. **Every one of them had a green test
suite standing over it** — which is why they are written up at length rather than ticked off. The
list is now longer than the walkthrough that started it.

**#46–#53 came from the team reading the screens, not from a run.** Eight groups of UI observations written up against Meridian Library on 25 August and fixed together. Four were exactly what the screenshots showed. Four were not: the audit status and the bounding boxes each had a single cause nobody would have guessed from the symptom, the defect description was already correct and was being rendered wrongly, and the artifact that looked over-published was one of several.

**#36–#38 came from a question, not a run.** Before committing to more accuracy work the team
asked: *as per WCAG, are we capturing and checking every element we should be?* Twelve textbook
failures were put through the platform's own selection code. **Eleven were handed to no check at
all** — several correctly, because they are the rule scanner's job; roughly eight were reported
by nobody. All three are fixed. The third was a scope decision rather than a defect — the team
was given three options and chose the thorough one — and its full analysis is written up on its
own in `SCOPE_GAP_INFO_AND_RELATIONSHIPS.md`.

**#39 and #40 close the same investigation.** #39 is the last two shapes from that same
twelve-case probe. **#40 is the one that matters most**: nothing anywhere checked that a check
actually covers the rule it is filed under, which is *why* #38 could happen at all and could
have happened again on a different rule.

**#59–#65 came from re-reading every fix we have ever made, and then from clearing what that
found.** Before the next full-scale audit the team asked whether every correction since 12 August is
accurate, surgical and permanent — and, most of all, *true rather than a confident assumption*. All
149 commits were read and every fix re-checked against the code as it stands: **200 corrections, all
200 still present**. None of what the review turned up was a product defect, and the team's
instruction was that everything be cleared before the audit is run rather than carried into it. So
#59, #61, #62, #63 and #65 are fixed. #60 ends up in two halves: the corpus rows and the missing
capability method are built, and the accuracy evidence is **#64** — the one thing here no code
change can close, because it needs a person who did not write the checkers.

**#65 is the one to read.** It is the single fact underneath #60, #62 and #63: a correction the
team agreed on 27 August was written into a document and never into the register that actually
routes checks. Everything else in this group is a consequence of that gap. The full account is
`GAP_FIX_BUILD_PLAN.md` §9.29 to §9.31 — including §9.29.D and §9.30.D, which record what the
review itself got wrong.

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
| 25 | An audit whose machine went away could never end | ✅ fixed |
| 26 | A pass that stopped at its limit said nothing, anywhere | ✅ fixed |
| 27 | The onboarding step called a running audit a finished one | ✅ fixed |
| 28 | **One of the four checks had never run** | ✅ fixed |
| 29 | The reports printed part of the finding | ✅ fixed |
| 30 | **"Screenshot shows…" pointed at nothing** — no screen drew the capture a report described | ✅ fixed |
| 31 | The conformance statement could not say which run produced it | ✅ fixed |
| 32 | A running audit was described as stopped | ✅ fixed |
| 33 | **The second pass was described in the first pass's words** | ✅ fixed |
| 34 | The baseline never said when a check was incomplete | ✅ fixed |
| 35 | **A criterion checked on eleven pages was reported on one** | ✅ fixed |
| 36 | **Table rows, lists and form groups were never captured at all** | ✅ fixed |
| 37 | A submit button's visible label could never be read | ✅ fixed |
| 38 | **The 1.3.1 check is narrower than the criterion it is recorded against** | ✅ fixed |
| 39 | Charts drawn on a canvas, and icons drawn by a font, were checked by nobody | ✅ fixed |
| 40 | **Nothing checked that a check covers the criterion it claims** | ✅ fixed |
| 41 | **A big table reached the AI with most of it missing** | ✅ fixed |
| 42 | **Pages we never opened were reported as passing** | ✅ fixed |
| 43 | **The judging limit counted the same question seventeen times** | ✅ fixed |
| 44 | **The AI was handed its own previous answers** | ✅ fixed |
| 45 | **The table-shape fix was built and never reached the AI** | ✅ fixed |
| 46 | The empty page list explained our architecture instead of naming the next step | ✅ fixed |
| 47 | Two panels announced a machine the navigation bar already announces | ✅ fixed |
| 48 | A third of two panels was prose read once and skipped forever after | ✅ fixed |
| 49 | **An audit that stopped at its limit called itself complete, in green** | ✅ fixed |
| 50 | **Every artifact of an accessibility run was published, approved by nobody** | ✅ fixed |
| 51 | **The bounding boxes were drawn in the wrong place, by exactly half** | ✅ fixed |
| 52 | The work items an audit creates could not be read | ✅ fixed |
| 53 | "Answered questions" showed an empty card on every platform-created item | ✅ fixed |
| 54 | **One audit was closed twice, and the second close wrote off the first** | ✅ fixed |
| 55 | **Work correctly queued for a second pass was reported as unaskable** | ✅ fixed |
| 56 | **Some containers were never looked at, on any page, in any audit** | ✅ fixed |
| 57 | **Our own check could never have found #56** | ✅ fixed |
| 58 | Stopping a run does not stop the work | 🔬 recorded, not fixed |
| 59 | The failing backend tests are three causes, not one | ✅ fixed |
| 60 | **1.4.11 has no corpus rows, no capability method and no answer-key records** | ✅ corpus + method built |
| 61 | One frontend test only passes in UTC | ✅ fixed |
| 62 | **Five more red tests than anyone had counted, all naming the same thing** | ✅ fixed |
| 63 | **Pausing the judge would have handed 1.4.11 back to the arithmetic** | ✅ fixed |
| 64 | The answer key still has nobody's signature on it | 🔬 recorded, not fixed |
| 65 | **A correction agreed on 27 August never reached the data** | ✅ fixed |

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

*"The AI half covers 11 of 55"* is the ownership **registry's** classification. Four checkers were
built at the time and they covered **five**; the rest were Phase 2, which the task backlog has
said all along. (**Since 27 August it is six checkers covering six criteria** — `structure` and
`graphics` were added after this finding was written; §2 carries the current figure.) And *"22 criteria only a person can assess"* is **23** — 2.4.7 is registry-owned by `ai`
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


### #29 — The reports printed part of the finding ✅

Found by the team reading the 21 August artifacts. A markdown table cell cannot hold a line
break, so every cell was bounded: **300** characters in the per-run report, **160** in the
baseline backlog. On that run, 9 of 26 evidence strings and 13 of 26 fixes were longer than that.

What the cut took was not filler. The chart finding lost the sentence that made it a failure —
*"Those figures are unavailable to screen-reader users"* — leaving a reader with a description
and no conclusion. The backlog's copy of the same fix stopped **inside the quoted alt text it was
telling somebody to write**.

Raising the limit moves the cut. It does not remove it, and a 687-character cell is unreadable in
a table anyway. **A table is the wrong container for a paragraph**, so both documents now number
their rows, summarise in the column, and print every finding in full underneath its own table
under **Details**. The gist ends on a whole sentence where there is one and a whole word
otherwise, and carries `…` only when it really stopped early — so a short finding reads as
complete, because it is.

Two smaller things went with it: the *Suggested fix* column is gone from the table rather than
widened, and the blockquote reasons in the "we did not look at everything" notices are no longer
bounded either — they were cut at 400 only because `_cell` was the tool at hand, and a blockquote
line is not a cell.

### #30 — "Screenshot shows…" pointed at nothing ⭐ ✅

Every one of the 26 findings opens with it, and the team could not find a screenshot anywhere.

The pictures were being kept. An endpoint already streamed them, for any finding on the project.
The element's rectangle was already stored in the screenshot's own pixel space. What did not
exist was **anywhere to look**: the only screen that drew a capture was the review console, which
holds `needs_review` items and nothing else — and all 26 of these were confirmed failures.

So S-39 is mostly assembly, with one genuinely new piece. **Opening a finding must not claim it.**
`GET a11y-review/<id>` takes the review lock as a side effect — correct for a reviewer working a
queue, wrong for anyone following a link out of a report, because a failure nobody is reviewing
would acquire a reviewer's name just because somebody looked at it. `GET a11y-finding/<id>` is the
same read with the claim off.

The screen names the audit that took the picture, resolved from the capture's own key rather than
from the finding — a finding outlives every pass that saw it, and "which audit took *this* one" is
the question a person looking at a picture is asking. Null on greenfield, where there is no audit,
and said as nothing rather than as an empty link.

⚠️ **The link nearly landed on only one of the two documents.** A baseline audit manufactures no
`Run`, so the per-run report renders from the merge, whose rows carry no ledger id — the link
would have appeared on the baseline and silently not on the report, which is the document a client
reads. Resolved by fingerprint (`findings.ids_by_fingerprint`), which is what "the same problem"
already means here.

**How to check it:** open the accessibility report artifact, follow **See the capture** on any
failure. You should get the page with an orange box round the element, the audit named and dated,
and the whole of what the check saw. Then reload the review queue — the finding you opened must
**not** be locked to you.

### #31 — The conformance statement could not say which run produced it ✅

A signed statement that cannot name its evidence is one nobody can check a year later. It now
opens with **What this is based on**: the most recent completed audit, its id, when it finished,
and how many pages it opened — plus a count of the earlier ones, because the findings ledger is
cumulative and naming only the latest would read as "this is what was checked".

It is inside the wording rather than beside it, and that is the whole design. The section is
covered by `signed_body_hash`, so it is signed along with the conformance claims; a label printed
next to the document would not be, and would go on looking right after the wording was edited to
say something else. A failed audit is left out — it published nothing, and listing it would credit
the statement with coverage it never had.

The screen keeps its own copy of the same facts, because the wording is the reviewer's to replace
and they may cut the section.

---

### #32 — A running audit was described as stopped ✅

Spotted by the team watching the Past-audits row while the fresh run of 21 August was still
judging. The row said:

> Stopped at this run's limit of 200 — 12 item(s) still need judging.

The audit was `judging` at the time, 60 of 126 elements in, and nothing had stopped.

**Why it was there.** The dispatcher writes that sentence *before* the judge is asked anything,
so it sits in the audit's summary for the whole pass — in the past tense. The row printed it
with no status check. The API already refuses to compute the "check the rest" count for an
audit in flight for exactly this reason, and the panel above already hides everything until the
run finishes. The row was the one place that skipped the rule.

**And the number was the wrong one.** That pass deferred 12 request *slots* but only **6
elements**; the other six repeated markup already judged in the same run. The count on the
button had been fixed to use the element number back in #26 — the sentence beside it had not.
One card was about to show 12 and offer 6.

**Now:** there is a single definition of "how many elements are actually left", used by the
sentence and the button; a pass with nothing genuinely outstanding records no sentence at all;
and the screen composes the sentence **from the count rather than from the stored text** — which
is what let the fix reach the audit that was already running with the wrong wording saved in it.

**How to check it:** while an audit is judging, its Past-audits row should show the badge
*Checking what was found* and nothing else. When it completes, if anything was left, the number
in the sentence and the number on the **Check the rest** button must be the same.

⚠️ **A wrong call I made twice during the run, recorded because it is the kind of mistake that
matters.** I predicted the cap would be hit, then "corrected" myself mid-run to say it had not
been, reading `dispatched: 126` as the whole story. That 126 is the de-duplicated count *inside*
the 200 that were taken — 212 went in, 12 were deferred, the cap was hit. Both claims came from
reading a progress number instead of the four-line function that applies the cap.

### #33 — The second pass was described in the first pass's words ⭐ ✅

Found by the team pressing **Check the rest** on the finished 21 August audit — the last path in
this capability that had never been exercised.

**The check itself worked, first time.** It went back for the 6 elements nothing had looked at,
all on `/staff/shelf-audit`, and answered all six: **four new failures**, the broken
`#shelf-fiction` / `-childrens` / `-local` / `-reference` switches, WCAG 1.3.1 at 0.97. Findings
went 21 → 25, the report was re-published with its incompleteness warning correctly **gone**, and
the baseline reached v2 — 3 criteria across 7 pages in 25 items.

**Then the screen described that pass entirely in the previous one's words.** Four claims on one
screen: *"this run reached its limit … 6 elements were left"* (it hit no limit and left none),
*"6 elements were never looked at"* (they had just been looked at), a **Check the rest** button
offering those same six, and a progress tile reading **0 of 126** for a pass that went back for
six. Underneath, one cause: a second pass wrote four keys onto the stopped pass's record and
inherited everything else. It now replaces that record wholesale, exactly as the first pass does,
keeping only the facts about the capture — which a second judging pass does not touch.

**A button that could not be cleared by using it.** The badge is a cheap sum of what each pass
recorded about itself; the re-judge recomputes the real list from the capture. When they
disagreed — as they legitimately can — pressing the button returned "every element has been
looked at" and **wrote nothing**, so it offered the same phantom work again for ever. The
recount is now recorded, which also means pressing the button is what repairs an audit already
stuck in that state.

**A sentence that sent people to an empty queue.** *"They are waiting on a person in the review
queue"* was hard-coded and checked nothing — printed three inches under a tile reading **0
waiting on a person**. An element nothing ever looked at has no finding and so no queue entry;
that is precisely what makes it different from one a check reached and could not decide. It now
says nobody is waiting on them and that asking again is the only thing that answers them.

**And a second pass now says it is one.** The flag saying so had been recorded since the feature
was built and no screen read it — so a completed audit appeared to vanish and be replaced by a
running one, and the panel claimed *Pages visited 12 of 12* for a pass that opens no browser.

**How to check it:** finish an audit that left something unchecked, press **Check the rest**. The
panel should read *Checking the rest of this audit*, say plainly that no page is visited, and
count against the number it went back for — not the original audit's. When it finishes, the
warning banner, the "never looked at" line and the button should all be **gone**, and the title
should carry both times: when the audit ran, and when it was rechecked. Press **Check the rest**
on an audit with nothing left and the button must disappear rather than sit there.

⚠️ **A wrong call recorded here on 21 August and corrected the same day.** This paragraph used
to say all 25 findings being `critical` was "what the judge actually decided — a calibration
question". The judge does not decide severity. It is derived from the criterion's WCAG level —
**A → critical, AA → high, AAA → medium** (§11.4, and `findings.SEVERITY_BY_LEVEL`) — and every
criterion in that run is Level A. All-critical was the rule working, not a judgement to review.

### #34 — The baseline never said when a check was incomplete ✅

The per-run **report** has always said so, in its own blockquote at the top. The **baseline** did
not — it opened *"2 criteria breached across 6 pages"* over a check that had never looked at part
of what it captured, and said nothing.

**Why that is the wrong way round.** The report is a working document for whoever ran the pass.
The baseline is what a client is shown, what the next audit is compared against, and what a
**conformance statement is built on**. It is the one that must never read cleaner than the
evidence behind it.

**Now:** the baseline states both silences a page count cannot express — elements that were
captured and never checked, and a whole check that could not run at all (the name check reports a
clean-looking blank when the browser stops answering). The number is taken from the **same
function the Check-the-rest button uses**, so the document and the screen cannot disagree about
how much was looked at, and it clears itself when a re-judge finishes the job.

**How to check it:** run an audit big enough to stop at its limit — the Meridian scope does this,
212 element slots against a limit of 200. Open the **Accessibility baseline** from Artifacts:
under *What has been looked at* it should say the check is incomplete and name the number. Press
**Check the rest**, let it finish, and the next baseline should not say it.

**The case worth checking deliberately:** a baseline with **no findings at all** must still carry
the warning. "No accessibility problems are open" is exactly when "part of this was never
checked" matters most.

### #35 — A criterion checked on eleven pages was reported on one ⭐ ✅

Found by reading the **live** conformance statement, which is the only place it was ever visible.
Two rows of the same document, from the same audit of eleven pages:

> **1.1.1** — 14 open failures; failed on 5 of 11 pages checked; checked on 1 page with nothing
> wrong; **5 pages had nothing for this rule to apply to.**
>
> **2.5.3** — 7 open failures; **failed on 1 of 1 pages checked.**

The first accounts for all eleven pages. The second accounts for one and drops ten without a word
— and the Label-in-Name check had run over every one of them.

**Why the ten vanished.** The platform records two different things: what was **wrong**, and what
was **looked at**. The rule scanner records "looked at" for every page, including pages where its
rules found nothing to apply to. The AI checks only recorded "looked at" for pages where they
actually had a question to ask. On a page where every button already announces its own visible
text, the Label-in-Name check has nothing to ask — the criterion is simply **satisfied** — so it
said nothing at all.

For four of the five AI-owned criteria that never showed, because the rule scanner covers those
same criteria and quietly filled the gaps. **Label in Name is the only criterion in the whole
standard that our AI checks own and the scanner does not touch**, so it is the only one where the
hole reached the page.

**The direction that matters, and it is the opposite of what we saw.** Meridian *fails* this
criterion, so the statement made a failure claim on thin evidence — not good, but the safe way
round. Now picture an application with **no** Label-in-Name problems at all: it produces no record
of being looked at, and the statement prints **not evaluated** — a criterion the platform checked
on every single page, reported to a client as one nobody looked at, in a document someone signs.
That is the exact sentence this whole capability exists to prevent, printed by the capability
itself.

**Now:** every page a check ran over gets an answer, including *"nothing on this page was in scope
for this check"* — the same words, and the same meaning, the rule scanner already uses. Two things
are deliberately left silent: a page the browser **never opened**, and a page where the checking
**stopped part way through**. In both cases we genuinely do not know, and saying nothing is how
this codebase says so.

**How to check it:** run an audit, open the **Conformance statement**, and read the *What was
checked* column. Every criterion with a tick in *Established by* should account for the **same
number of pages** as the audit opened. A criterion claiming fewer pages than the audit visited is
this bug coming back.

⚠️ **This changes the next audit, not the one already stored.** The record of what was looked at
is written when a run is recorded, so the 21 August statement will keep saying "1 of 1" until
another audit runs. Verified before any test was written by re-computing from the stored capture:
2.5.3 goes from 1 page to 11, and 1.1.1 from 6 to 11 — the same defect a second time, which the
scanner had been hiding.

---

### #36 — Table rows, lists and form groups were never captured at all ⭐ ✅

**What it is.** Before any check can look at something on a page, the audit has to pick it up. It
works from a fixed list of which kinds of page furniture to collect.

**What was wrong.** That list included table **cells** but not table **rows** — and not tables,
lists, form groups, embedded frames or charts either. Across the whole 21 August audit, 196
elements were collected from 11 pages, and every single one was a paragraph, a heading, an image,
a link, a button, a span or a plain container. Not one table. Not one form field group.

**What it meant.** `/loans/current` lists borrowed books in a table and **tints each row** to say
overdue, due soon or on loan, with a colour key underneath and the status written nowhere in
words. Someone who cannot tell those colours apart cannot tell which book is overdue — a
textbook Use of Colour failure.

Here is everything the AI was shown on that page: the heading, two paragraphs, six pieces of the
footer, one span in the site header. **The table is not in that list.** Neither are the tinted
rows, nor the key.

So the colour check looked at nine ordinary bits of text, correctly said colour was carrying
nothing, and the audit reported **no colour problems**. The conformance statement then recorded
the page as one where Use of Colour **had been checked**. A confident silence over the one thing
on the page that fails.

**Two innocent halves.** The tint sits on the row. A cell inside it *inherits* that colour rather
than painting it, so the colour rule correctly declines the cells — while the row that owns the
colour was never offered. Neither half is wrong on its own, and nothing anywhere reported a gap.

**Now:** the capture collects the containers too — tables, rows, lists, form groups, frames and
charts. The colour rule claims a tinted row the moment it arrives; that rule never needed
changing and was not changed.

Most of the other containers are **not claimed by any check yet**, and that is deliberate rather
than half-done. Something collected and then declined is **counted**, and the platform can say
which rule declined it and why. Something never collected is a silence nothing can measure. This
turns the second into the first.

**How to check it:** run an audit including `/loans/current`, open the report, and look for a
colour finding against the loans table. Before this fix there could never be one.

⚠️ **Watch the judgement count on the next run.** Striped tables now raise a colour question
per tinted row, and there is a ceiling of 200 judgements per audit. If it starts biting, the
answer is to treat a repeated identical row tint as one question — not to stop collecting rows.

### #37 — A submit button's visible label could never be read ✅

**What it is.** The Label in Name check compares the words you can **see** on a button against the
words a screen reader **says**. When a voice-control user says "click Search" and the button is
secretly named "Go", nothing happens — that is the failure it exists to catch.

**What was wrong.** It read the visible words as the text sitting inside the element. That works
for `<button>Search</button>`. It can never work for a form's submit button, which is written
`<input type="submit" value="Search">` — there is nothing inside it. The words are in the
`value`.

So the check found no visible words, concluded from that silence that the criterion did not
apply, and moved on. **Every submit and reset button in every form of every client application
was permanently out of scope**, and nothing anywhere said so.

**Now:** for the three button-like input types, the `value` is read as the visible label.

**Why only those three, and not every field.** On an ordinary text box, `value` holds **what the
user typed**. Treating that as a label would compare somebody's own name against the field's name
and report the difference as an accessibility defect — a finding raised against a real person's
data, on every filled-in form. There is a test making sure it does not.

A submit button with **no** `value` stays out of scope, also on purpose: the browser draws its own
word there, in its own language, and it is not in the page for us to compare anything against.

**How to check it:** on a page with a real form, give the submit button a `value` of "Search" and
an `aria-label` of "Go". It should now be reported against 2.5.3. Before this it could not be.

**Flagged, not fixed:** the same blindness exists in two neighbours — the colour check's "is
there any text here?" test reads inner text the same way, so a submit button styled only in red is
still out of scope for Use of Colour. Same family, different criterion; this fix was scoped to
2.5.3 and widening it is a separate decision.

### #38 — The 1.3.1 check is narrower than the criterion it is recorded against ⭐ ✅

**What it is.** WCAG 1.3.1 *Info and Relationships* says: anything a sighted person can work out
by **looking** at the page must also be written into the markup. Table headings must be marked as
headings. A list must be a list. Radio buttons that belong together must be grouped.

**What is wrong.** Our check for it asks one question — *"is this thing pretending to be a button
or a heading without being one?"* That is a real and useful question, and we do find those. But it
is not the question 1.3.1 asks. A table with no header cells is claimed by no check, by the rule
scanner or by us, and the page is recorded as **passing 1.3.1**.

**Why it is not a bug.** Every rule in that code is deliberate, documented and individually
tested. The check was built to answer a narrower question than the routing table records it
against, and nothing in between ever compared the two.

**What was done.** The team was given three options and chose the thorough one: a **fifth
check**, called `structure`, whose job is only this. Its unit of work is the **container** —
because whether a table has headers is a fact about the table, not about any cell in it.

It is now shown every table, list and group of fields on a page, a form whose radio buttons or
checkboxes have no grouping around them, and any container that repeats the same kind of child
three or more times — which is how a list gets drawn without being one. Two repeats are left
alone, because a pair is a layout rather than a list.

**Containers that look correct are shown to it too.** Whether a table's headings are the *right*
cells, whether a list's items are really items, whether a group's label actually names the
question — none of that can be decided from the markup alone, and most containers on most pages
turn out to be fine. A confident "this is correct" is a useful answer.

**A layout table is still asked about.** A page can declare that a table is only for
arrangement. That is the author's *claim*, and whether it is true is exactly what 1.3.1 asks —
the same reasoning that keeps a blank `alt` in scope for the image check.

**The team chose to skip the cheap interim option** (recording 1.3.1 as only partly covered, so
the paperwork was honest while the real fix was built), on the instruction that accuracy
mattered more than time. So the conformance statement kept claiming full coverage until this
landed. Worth knowing, and it was a deliberate call.

**Found while building it.** A container's markup reaches the AI capped at a fixed size. For a
button that is never close to the limit; for a long table it is — and the AI would have
answered about a table it only saw the top of, without anyone knowing. The capture now says
when it had to cut, and the AI is told to answer "not sure, I only saw part of this" instead of
guessing. **That helps every check, not just this one.**

**How to check it:** run an audit over a page holding a table whose top row is styled as
headings but marked up as ordinary cells. It should now produce a 1.3.1 finding naming the
markup to add. Before this, nothing looked at it and the page was reported as passing.

**Still open, and worth doing:** nothing yet fails when a check is registered against a
criterion it does not actually cover. That is the guard that would stop this happening on a
different criterion. What exists is narrower — a test pinning which check claims which
criterion, which catches a change to the mapping but cannot tell whether the check underneath
covers what it claims.

**Full analysis, and the options as they were put to the team:**
`SCOPE_GAP_INFO_AND_RELATIONSHIPS.md`.

### #39 — Charts drawn on a canvas, and icons drawn by a font, were checked by nobody ✅

**What these are.** Two ways of putting a picture on a page that are not an image tag, so
nothing that looks for images ever found them.

A **canvas** is a blank drawing surface a page paints on — charts, signature pads, seating
plans. Whatever it draws exists only as coloured pixels; there is nothing inside it to read. No
rule can say whether the text offered as a substitute describes what was actually drawn,
because answering that needs somebody to look at the picture. That is exactly the kind of
question the AI half exists for, and it was never being asked.

An **icon font** draws a picture using a character. A page writes what looks like a letter, and
the font renders a bin, a warning triangle, a padlock. Because it is technically text, an image
check never sees it — and a screen reader announces nothing useful.

**Now:** both are checked. For icon fonts there are two ways in, and the first is not
guesswork — certain character codes are reserved to mean "whatever this font wants", so a
single one of those is a picture by definition. The second catches an empty element whose class
names an icon family: nothing to read, no image inside, and something visibly being drawn.

**Two things are still deliberately left alone**, each for a stated reason:
- An **embedded frame with no title** — the rule scanner proves that one outright, and asking
  the AI as well would cost a judgement on every embed for a second opinion on a settled fact.
- An icon font that uses a **real word** to pick its picture. It is announced as that word —
  a poor description, but a description. Flagging it would queue every such icon on every page
  to be told it is mediocre.

**How to check it:** put a chart on a page as a canvas with no description. It should now be
reported against 1.1.1. Before this, nothing looked at it.

### #40 — Nothing checked that a check covers the criterion it claims ⭐ ✅

**What this is.** Not a defect in any one check — a hole in what our tests were able to ask.

Finding #38 happened because a check was built to answer one question well, was then filed
under a rule of the standard that is much broader than that question, and **nothing ever
compared the two.** Every test we had asked *"does this check do what it says?"* Not one asked
*"does what it says add up to the rule it is filed under?"* So the platform reported eleven
pages as passing a rule it had barely examined, every test was green, and it took a person
reading the finished document to notice.

That is the kind of thing that happens again, on a different rule, unless something stops it.

**Now:** there is a list of **real accessibility failures** — forty-six of them — each written
down as the actual shape it takes on a page, and each paired with the same thing done
correctly. Three rules hold it together:

1. **Every rule of the standard we claim must have at least one real failure written down for
   it.** Claim it, build nothing that finds it, and there is nothing to add to the list. That
   is precisely what happened on 21 August, and it can no longer pass quietly.
2. **Every one of those failures must actually reach a check.** If one doesn't, a named test
   fails here — rather than a client's conformance document being wrong.
3. **Every rule must also have something written down that must NOT be flagged.** Without
   this, a check that flagged absolutely everything would satisfy point 2 for every rule at
   once, and the whole list would be a rubber stamp.

**Proven against the failure it was built for.** I put the platform back to exactly how it
stood on 21 August and ran it: **five of the recorded failures reach no check at all**, and the
list names each one. In that same state, before this existed, everything was green.

**What it does not do**, said plainly so a green run is not read as more than it is: it proves
each rule has *a* way of being found, not that we find everything. A rule can have one failure
listed here and still miss ten others in the real world. What it does is turn an open-ended
silence into a list somebody can look at and argue with — which is the most a test can do
about a problem of this shape.

**How to use it:** whenever a new kind of failure turns up in the wild, add it to the list —
**before** fixing it, so the fix has something to prove itself against. Same discipline as the
list of false alarms kept for the secret scanner.

### #41 — A big table reached the AI with most of it missing ⭐ ✅

**Raised by the team**, reading #38: *if answering "not sure" does not actually help, it should
have a surgical permanent fix, right?* It should, and it now does.

**What was wrong.** Everything on a page that we send to the AI is capped at **8,000
characters** — a sensible limit that stops one enormous element swamping a run. A button is
never anywhere near it. **A table is.** A realistic row of five columns costs about 190
characters, so the cap holds roughly **forty rows**. Past that, the AI was handed the top of a
table and answered as though it had seen all of it, and nothing told anybody.

It never showed up in testing because our test site's tables are small — across the whole 21
August audit the largest thing we captured was 503 characters. On a client's reporting screen it
would have happened on almost every table.

**Why "say you're not sure" wasn't good enough.** That stops us being *wrong*. It does not make
us *useful*. "Not sure" sends the item to a person to look at — so on a real reporting screen,
**every large table would land in the review queue**, and we'd have turned an automated check
back into a manual one precisely where tables matter most. Honest, and no use to anybody.

**The fix: send the shape instead of the contents.** What the rule actually asks about a table
is its *arrangement* — how many rows and columns, which cells are headings, what the top row
and the left-hand column say. That is a few hundred characters **for a table of any size**,
because it depends on how *wide* a table is, not how *long*.

Measured against a real 401-row table, in the same browser the audit uses:

| | Sent before | Sent now |
|---|---|---|
| A 3-row table | 206 characters | 317 characters |
| **A 401-row table** | **31,985 characters, cut off at 8,000 — three quarters lost** | **906 characters, nothing about the shape lost** |

**It is also a better answer, not just a smaller one.** Working out a table's grid from raw page
code is something ordinary software does perfectly and an AI does unreliably. That work now
happens once, in the browser, and the AI spends its effort on the part that genuinely needs
judgement. The failing case now reads straight off: *401 rows, 2 columns, no heading cells, and
a top row saying "Title" and "Status" that isn't marked up as headings.*

⚠️ **One consequence, and it is deliberate.** The shape is part of how we recognise "we have
already answered this element", so **every stored answer is discarded once** and the next audit
works from scratch. It has to be: a table can gain three hundred rows while its first 8,000
characters stay identical, and without this it would keep its old verdict for ever — the
platform answering about a page that no longer exists.

The timing is the good part: **nobody has reviewed a single finding yet**, so no human decision
was lost with it. Done later, it would have cleared rulings people had made.

**How to check it:** put a table of more than about fifty rows on a page and audit it. The
finding should describe the whole table — its real row count — not just the top of it.

### #42 — Pages we never opened were reported as passing ⭐⭐ ✅

**What it is.** When an audit runs, each page is checked against the WCAG rules and the result
is recorded per page: passed, failed, nothing here to check, or needs a person.

**What was wrong.** On 24 August we audited seventeen pages. The AI ran out of its per-run
budget after **eight** of them. The remaining nine had **not a single element** looked at — and
all nine were written down as **passing**.

**Why that happened, because it is not obvious.** Every page of a website shares the same
header, footer and menu. The platform is clever about this: it notices the footer is identical
everywhere, asks about it once, and applies that one answer to every page it appears on. Sensible
— the footer really is on all of them and really is fine.

But a page is more than its furniture. `/catalogue/subject-index` had eighteen things worth
checking, and **eight of them were the shared header and footer**. Those eight collected a pass
from pages the AI *had* looked at. The other ten — including a table whose column headings are
ordinary cells, which is exactly the kind of thing that page was there to test — were never
asked about, so they said nothing at all.

Eight passes and no failures looks precisely like a clean page.

**What it meant.** For about forty minutes the audit sat marked **complete**, stating *"Info and
Relationships: satisfied on all 17 pages"*, with a broken table sitting unexamined on one of
them. Had anyone opened the report in that window, they would have been shown a clean bill of
health for work nobody had done. For an accessibility product that is the worst thing it can do.

**The fix, in two parts.**

First, the reason we ran out of budget was itself a bug — see #43. Fixing that means a site this
size now finishes in one go, so the situation stops arising rather than being caught.

Second, and this is the part the team pushed hard on: **an element nobody asked about is now
recorded as exactly that**, on its own page. The page reads *"still waiting on a check that has
not run"*, never *"passed"*, and the conformance document refuses to claim anything for that
criterion until it has.

**Why not just say "a person needs to look at this"?** That was the first proposal and the team
rejected it, correctly. "A person needs to look" means a check examined something and genuinely
could not decide — a real result, and something a reviewer can act on. Using those words for
work *we* had not done would hand somebody an element nobody had looked at, dressed up as a
judgement that hesitated. What they get instead is a plain statement that the checking is not
finished, and the **Check the rest** button, which is an action rather than a homework
assignment.

**How to check it:** run an audit big enough to stop part way. Every page it did not reach must
say it is still waiting, and the conformance document must make no claim for those criteria.
Then press Check the rest and watch them resolve.

### #43 — The judging limit counted the same question seventeen times ⭐ ✅

**What it is.** Each audit run will ask the AI at most 200 questions. It is a sensible safety
limit — it stops one enormous page costing an unbounded amount of money.

**What was wrong.** The limit was counted against the raw list of elements, and identical
elements were only merged *after* an answer came back. So one footer appearing on seventeen
pages took **seventeen of the 200 places** — and was genuinely asked seventeen times. You can
see the AI noticing: *"Same footer structure as element 36. Four columns. Pass."*, over and over.

| | elements selected | actually different questions |
|---|---|---|
| Our 17-page audit | 371 | **192** |
| The dev's 3-page audit | 39 | **28** |

**192 is under 200.** The whole site fitted comfortably in one run. It was never too big — the
counting was wrong. Instead it took two runs, sent 276 elements to the AI where 192 would have
done, and reported nine untouched pages as passing in between (#42).

**What it meant.** Wasted money on every audit, a second pass somebody has to notice and press,
and — far worse — whole pages pushed past the end of the run.

**The fix.** Merge the duplicates *before* applying the limit, so it means what it always said
it meant: how many elements one run may judge. Nothing is lost — the report is built from every
element the audit captured, not from the ones we asked about, so each copy still gets its own
line, on its own page. That was already true; it is what made the duplicates invisible.

Measured against both real audits after the fix:

```
Ours:      371 selected -> 192 different -> all 192 asked, none left over
The dev's:  39 selected ->  28 different -> all  28 asked, none left over
```

**How to check it:** audit a site with a common header and footer. The number of AI questions
should be close to the number of genuinely different elements, not the number of elements times
the number of pages.

### #44 — The AI was handed its own previous answers ⭐⭐ ✅

**What happened.** The dev ran an audit on his own machine. The AI recorded **no verdicts at
all** — and wrote a confident summary saying *"Gate outcome: PASS — no work blocked. 33
elements judged. All pass."* It had judged nothing. Its own count was wrong too (there were 32
colour elements, not 26), and "all pass" would have been wrong anyway — the same table rows
correctly **failed** on our tenant an hour later.

**Where those words came from, and this is the whole story.** The platform saves every document
it produces into a searchable library, and before each run it searches that library for anything
relevant and puts it in the AI's briefing. So an accessibility-judging run searched for
accessibility-judging material — and the best match in the entire project was **the last
accessibility judgement**. Its full text, "Gate outcome: PASS" and all, was placed in the
briefing of the run whose only job was to produce that document. One of the items retrieved was
a verdict about *the very table row it was about to be asked about*.

It was shown a finished, confident, authoritative answer to its own question, and handed it
back.

**Why it did not happen every time — it was never the AI being unreliable.** The same agent
judged 128 elements correctly on our tenant an hour later, because that search happened to
return summaries rather than a verdict table. Which documents come back is chance. Afterwards we
measured our own project: **215 of 221** saved items were previous accessibility answers. 97% of
its "knowledge" was its own homework.

**The fix: a result is not knowledge.** Accessibility judgements, reports, baselines and
conformance statements are no longer put in that library. They remain fully available to any
agent that asks for them **by name** — which the briefing explicitly tells every agent how to do
— so anyone with a reason to read last week's report still can. What they can no longer do is
find it already sitting in their pocket.

**Why not just tell the AI to ignore it?** That was the first proposal and it was the wrong
shape. You cannot rely on anyone — person or model — to disregard a plausible, authoritative,
directly-relevant answer placed in front of them, and they should not have to. A cleanup also
removes the copies already saved, since stopping the saving does nothing about what is already
there.

**The safety net worked, and stays.** The platform noticed the run had recorded nothing, failed
it, and refused to call the audit complete — which is why the dev saw a review queue instead of
a false all-clear. But a check that catches a fabricated answer is a worse place to be than
never inviting one.

**How to check it:** run two audits on the same project. The second must produce its own
verdicts, and its summary must match what the platform actually recorded.

**⚠️ One small piece was left in, on purpose — a decision, not an oversight.**

At the end of every audit the AI writes two things: its verdicts, and a short note on how it
reasoned. We removed the verdicts from the library it searches. We kept the reasoning notes,
because knowing *how* to weigh a rule is useful next time and carries no answers.

One of the five kept notes slipped an answer in. It names a specific element on a specific
page — `#hours-note` — and says which rules it failed and passed.

**What that could look like if it ever bites:** somebody fixes that element, re-runs the audit,
and the report says it is **still broken**. If a defect that was genuinely fixed comes back
reported as unfixed, this is the first thing to check.

The team weighed it and chose to leave it: one sentence about one element, on one page, in one
project. Closing it is a small change if it ever proves worth doing — see §9.22 of
`GAP_FIX_BUILD_PLAN.md`.

### #45 — The table-shape fix was built and never reached the AI ⭐ ✅

**What it is.** Finding #41 added something valuable: instead of sending the AI thousands of
characters of raw page code for a big table, we measure its **shape** in the browser — how many
rows and columns, which cells are headings, what the top row says — and send that instead. A few
hundred characters for a table of any size.

**What was wrong.** It never arrived. The shape was added everywhere it needed to be — except
the one small function that decides which pieces of a captured element are kept when it is
saved. That function works from a fixed list, and the list was never updated. So the browser
measured every table, the platform received the measurement, and it was thrown away one step
before storage.

Across all 371 elements of the seventeen-page audit, elements that arrived carrying a shape:
**zero**. The AI is instructed to *"start with the outline"* and was handed the label with
nothing behind it.

**What it meant.** On our test site, nothing — its tables are small enough that the raw code
fits, so the answers were sound. On a client's reporting screen it would have mattered on almost
every table, which is the exact case #41 existed for.

**The fix, and the part that matters more.** Keeping the two pieces is a one-line change. The
real fix is a new test that compares *what the code expects to read* against *what is actually
stored*, and fails naming anything missing. Nothing checked that before, which is how an entire
piece of work could be built, shipped, and do nothing at all without a single test failing. Two
fields are the symptom; nothing comparing the lists was the defect.

**How to check it:** put a table of more than about fifty rows on a page and audit it. The
finding should describe the whole table — its real row count — not just the top of it.


### #46 — The empty page list explained our architecture instead of naming the next step ✅

**What it is.** Pages & audit, before anybody has registered a page.

**What was wrong.** It opened with *"The platform has no access to your application, so it cannot
discover its pages — somebody has to say what they are. Nothing is audited until you do."* Three
sentences about why we are built the way we are, in front of somebody who wants to know which of
two buttons to press. The same explanation appeared a second time inside the **Import a list**
dialog, so it was read twice on the way to one action.

**What it meant.** The sentence that helps — do you already have the list, or are you building it
up — came last, after the reasoning nobody asked for.

**The fix.** Both are gone. The empty state now says only which button to press and when, and the
dialog goes straight to the box with the format help underneath it.

**How to check it:** open Accessibility on a project with no pages registered.

### #47 — Two panels announced a machine the navigation bar already announces ✅

**What it is.** The corners of **Run an audit** and **Keyboard journeys**.

**What was wrong.** Both carried a `Machine connected` badge while the navigation bar says
*Companion: Ready* permanently, a few inches away. Keyboard journeys also carried
`Reported, never blocking` — a policy about what happens to results, sitting where a status
indicator goes, and already stated in full at the foot of the same panel.

**What it meant.** The place the eye goes first was spent on something it had already read.

**The fix.** All three removed. **Nothing was lost**, and that is why it was safe: when there is
*no* machine, each panel still shows a full banner saying so and what to do about it — which was
always the half worth the space.

### #48 — A third of two panels was prose read once and skipped forever after ✅

**What it is.** *"Eight things cannot be judged from a page standing still…"* and
*"Start your application first"* on Keyboard journeys; the two paragraphs above the address box on
Run an audit.

**What was wrong.** Roughly a third of each panel's height was explanation, above the controls the
person came for. Useful on the first visit; re-read past on every visit after.

**The fix.** One sentence stays visible, and the rest folds behind a **What this means** line that
opens on a click. Nothing was deleted — the detail about what your machine needs installed still
earns its place on the day an audit fails because the browser is missing.

**Why an expander rather than a hover tooltip.** A tooltip cannot be opened with a keyboard and
does not exist on a touch screen. This product's whole job is finding that defect on other
people's sites. The expander is the browser's own, so it is focusable, works with Enter and Space,
and announces its open state to a screen reader with nothing added. **The label is grey**, not the
product's link blue and not the brand orange: this opens something on the same page rather than
navigating, so a link colour overstated it and two of them on one screen read as loud. What says
it is interactive is the marker, the pointer and the underline on hover — none of which is
colour. Brand orange was never an option here: it measures **2.97:1** on white, below the 4.5:1
this capability sells. The grey used measures **10.03:1**.

### #49 — An audit that stopped at its limit called itself complete ⭐ ✅

**What it is.** Past audits, and the panel above it.

**What was wrong.** An audit that hit the 200-element limit showed a green **Complete** badge and
the heading *"Audit complete"* — directly above its own amber warning that six elements were never
checked, and a button offering to check them. The screen read the audit's internal state, which
really is `complete` because the run finished and nothing crashed, and never looked at the number
beside it saying how much of the work was never done.

**What it meant.** The strongest signal on the row said the job was done. On a list of past audits
somebody scanning badges concludes an application has been fully checked when part of it was never
looked at. That is the quietest way this capability can fail.

**The fix.** The badge and the heading are now derived from both facts. Closed with nothing
outstanding reads **Complete** in green, exactly as before; closed with elements never looked at
reads **Not fully checked** in amber. Because it is derived from the same count the button uses,
pressing **Check the rest** turns it green by itself — there is no second piece of state to keep
in step.

**On the word.** The team first asked for *"In progress"*. It was raised that the same screen shows
a real **Audit running** panel for work actually in flight, so two different things reading as
in-flight would send somebody looking for a run that is not happening. The team chose
**Not fully checked**.

**How to check it:** the 21 August audit with six elements outstanding.

### #50 — Every artifact of an accessibility run was published, approved by nobody ⭐ ✅

**What it is.** Artifacts & Traceability, after an audit.

**What was wrong — and it is twice what the screenshot showed.** The team spotted the
`Assumptions` row marked **Published**. Checking the database directly: **every** artifact of
every judging run is published, in both tenants — the judge's own document as well. It does not
look wrong in the list only because it is separately tagged as run output, which the screen shows
instead of a status. The one row anybody noticed was the one not wearing a disguise.

**Why it happened.** The judging run is started with a flag meaning *no human gate on this one*,
which is right: nobody is watching that machine step and a gate there would hang the audit waiting
on an approval nobody knows to give. But that flag also runs the publish step. It was built for a
different feature — document vision, where a human really had already adopted the source document
— and the accessibility runs inherited the behaviour without inheriting the reason.

**What it meant.** In this platform **published** means a named human approved this and it is the
project's answer. Nobody approved these, which contradicts the platform's own rule that nothing is
published without an approved gate.

**The fix.** The two accessibility phases no longer mark anything published; their artifacts stay
**Draft**, which is what they are — kept, readable, previewable, and still handed to later phases.
Signing the conformance statement remains the one signature in this capability that means
something, and it still sets its own document to Approved. Document vision is untouched.

**How to check it:** every accessibility row in the registry reads Draft.

### #51 — The bounding boxes were drawn in the wrong place, by exactly half ⭐⭐ ✅

**What it is.** The orange ring around the failing element, on the review queue and on every
finding opened from a report.

**What was wrong, measured.** Reproduced in a browser with the numbers from the team's own
screenshot — a 1280 × 1144 capture in the panel width the app uses:

| | Where the ring was drawn | Where it belonged |
|---|---|---|
| Distance down the picture | **237.8 px** | **461.3 px** |
| Height of the ring | **17.8 px** | **34.6 px** |

**223 pixels too high, and squashed to half height.** That is why `#photo-interior`, a photo well
down the page, was ringed around the "Visit us" heading near the top.

**The cause is one line of styling**, not the capture and not the arithmetic. The browser records
the element's position correctly and the screen places the ring as a percentage of the picture,
which is right. But the frame the picture sits in is capped at 340 pixels tall while the picture
renders 659.6 — and percentages resolve against **the frame**, not the picture. Every ring was
compressed by 340 ÷ 659.6, a factor of 0.515. Both numbers above are exactly that factor off,
which is what confirmed the diagnosis rather than merely fitting it.

**A second problem fell out of the same line.** In *Fit to width* the frame hid what did not fit,
so **319 pixels of every tall capture were silently cropped** — a reviewer could not scroll to the
bottom half of the page they were judging.

**The fix, verified rather than proposed.** The ring now lives in a wrapper that hugs the picture
exactly, and *Fit to width* scrolls instead of hiding. Measured against the shipped stylesheet:

| | Fit to width | Actual size |
|---|---|---|
| Ring position | 452.0 px — **correct: 452.0** | 800 px — **correct: 800** |
| Ring height | 33.9 px — **correct: 33.9** | 60 px — **correct: 60** |
| Whole capture reachable | yes | yes |

Exact in both modes. The picture also scrolls itself so the ringed element is in view when the
panel opens — a correct ring three screens down still reads as "there is no ring on this one".

**The part that matters more.** No test could see this, because it lives entirely in CSS and the
test environment computes no layout. What is pinned now is the *arrangement* the fix depends on:
the picture and the ring alone together inside their wrapper. A stylesheet comment is not a test.

### #52 — The work items an audit creates could not be read ✅

**(a) Titles.** They read `Accessibility: 1.4.1 on /loans/current — #loans-table > tbody >
tr:nth-of-type(2)`: a rule named by a number nobody has memorised, an element named by a CSS path
nobody can read, and the whole thing truncated on a board card. They now read
**`Accessibility: Use of Color (1.4.1) on /loans/current — row 2 of the loans table`**. The exact
selector is not lost — it is on the ticket under **Element**, where somebody fixing it looks.

An element with an id of its own keeps it (`#photo-interior`): that is the name its own developer
chose, and describing it as "the image" would be a downgrade.

**The part that is easy to miss.** A defect's title is written once and never touched again, so
changing how titles are generated fixes nothing already on a board — 35 defects across the two
tenants. A one-off migration retitles them, and matches only titles still in the exact shape the
platform generated, so anything renamed by hand is left alone.

**(b) The description was printed as a warning.** A defect's description is already well-structured
— what was found, the screen, the element, the confidence, the evidence, a suggested fix. The
defect screen dropped the whole thing into a red alert box as raw text, so it arrived as one
unbroken paragraph with its formatting marks showing, and the most useful line on the ticket was
buried in the middle. Every other work item in the platform renders its description properly; this
screen was the one that did not. The state is now a badge beside the panel title, where a state
belongs, and the description is rendered as the document it is.

**(c) The Accessibility backlog epic.** It introduced itself in two sentences and then printed
**FEATURE STREAM: `__a11y_backlog__`** — an internal key the platform uses to find the epic again,
shown to a person under a heading and left to make sense of. The field is now hidden for the
platform's own containers (a real stream like "Payments core" still shows), and the epic explains
what it is, where its children come from, what closes and reopens them, and what order to work in.

### #53 — "Answered questions" on work items ✅

**The recon before the removal.** It is a full search panel — search box, phase filter, expandable
question-and-answer rows, paging — shown on Epic and Task detail pages, and rendered whether or
not there is anything to show. On anything the platform created for itself, a defect or the
accessibility backlog, there never are any answered questions, so on exactly the screens in the
team's screenshots it could only ever be an empty card.

**Nothing became unreachable.** The identical history, with the same search plus a work-item
filter, is the **History** tab of Clarifications. No data was deleted and no endpoint removed; it
is one click further away.

**The fix.** Removed from Epic and Task detail.

### #54 — One audit was closed twice, and the second close wrote off the first ⭐⭐ ✅

**What it is.** The 31 August audit: 94 pages, the first run at real size.

**What you saw.** The audit went to **Complete** while the judge was visibly still working. Under
*Past audits* it said **"1065 elements were never looked at"** — about an audit that had 338 real
verdicts in the database at that moment, and 644 by the time it was measured again. The sidebar
badge climbed into the hundreds. None of the numbers on screen matched the database.

**What was wrong.** Closing an audit this size takes minutes of real work. The companion gave up
waiting after 60 seconds, decided the audit had failed, and ran its recovery — **which closes the
audit**. So the same close ran twice, and the second one overlapped the first.

The second close asked for a judge and was refused, correctly, because one was already running.
But that refusal was reported as *"the judge could not be started"* — so the platform did what it
does when no judge can be reached: **it wrote off all 1,065 elements as unjudgeable, and replaced
the audit's record of the pass that was actually running with its own empty one.**

**What it meant.** Every wrong number the team saw for the rest of that day came from that one
record. Not from the judge, not from the capture, not from the pages — all three were working. The
audit simply lost its own account of itself.

**The fix — three parts, and the first two work independently.**
1. A run already in progress is no longer treated as a failure. Nothing is filed and nothing is
   written off, because those elements are being judged right now.
2. A repeated close returns the audit exactly as the call doing the work left it, and changes
   nothing.
3. The companion no longer times out on a call whose job takes minutes.

**How to check it:** close an audit twice. The second one reports `repeat` and the audit's numbers
do not move.

### #55 — Work correctly queued for a second pass was reported as unaskable ⭐ ✅

**What it is.** The review queue badge, and the message under a finished audit.

**What you saw.** **1,731 items waiting on a person.** Not one of them was real.

**What was wrong.** The audit correctly held 265 elements back — over its 800-question budget,
queued for a second pass, exactly as designed. When the dispatch above then failed, those 265 were
swept in with everything else and stamped *"the judge could not be started"*. That is not true of
them: they were queued, not unaskable, and the difference is the entire meaning of the **Check the
rest** button.

**The fix.** Each half now carries the reason that is actually true of it — "N could not be sent"
and "M left for a second pass" are two facts about two different sets of elements, and both are
shown. The failure comes first, because it is the half somebody has to act on.

**How to check it:** an audit that reaches its limit and then cannot send says both sentences.

### #56 — Some containers were never looked at, on any page, in any audit ⭐ ✅

**What it is.** What the capture picks up off a page.

**What was wrong.** The capture collected a `<div>` only if it had a `class` on it. A container
styled by `id` or by an inline style — very common in real applications, and the normal output of
several page builders — was **never collected at all**. Not declined by a check: never shown to
one. So nothing recorded that it existed, and the page was written down as checked.

**What it meant.** On the fixture this hid three real failures on one page. On a client site it
would hide however many of that kind of container the site has, silently, with the page reported
as fine.

**The fix.** The capture now also offers any `<div>` with three or more children — the same bar the
structure check itself uses. Measured across all 95 pages before it went in: **8,385 elements
offered today, and this adds three.** It is not a broadening that costs anything.

**How to check it:** `/events/workshops` goes from 80 elements to 83.

### #57 — Our own check could never have found #56 ⭐⭐ ✅

**What it is.** `verify-selectable` — the check whose whole job is to prove every answer-key record
can reach the check it was written for.

**What was wrong.** It looked elements up directly on the page, which finds anything that is
there — whether or not an audit would ever collect it. So it tested *"do the rules want this?"* and
never *"would we even have picked it up?"*. **The one failure it could not see was #56**, and it
reported all three affected records as perfectly fine.

**What it meant, and this is the part worth reading twice.** The `structure` check reported a
reachable sample of 30 — over the line, measurable, healthy — while 3 of its 15 failure records
could never be found by any judge. Its best possible recall was **80%**, and nothing anywhere said
so.

**The fix.** The check now uses the capture's real list, imported from the audit script itself so
the two cannot drift apart, and asks both questions. It reports them separately, because they are
different problems: *collected then declined by a rule* is often correct and sometimes unavoidable;
*never collected at all* is always a gap, and now fails the check.

**Proved, not asserted:** with the #56 fix temporarily removed, the check names all three records
and fails.

### #58 — Stopping a run does not stop the work 🔬 RECORDED, NOT FIXED

**What it is.** Anything the platform runs on your machine, not only accessibility.

**What was observed.** The audit's judge was stopped on the server at **06:46**. It went on writing
answers into the database until **07:37** — 49 minutes, one every few seconds. Only killing the
companion actually stopped it.

**Why.** The work runs as a process on your own machine and reports its results straight to the
platform. Stopping the run stops the platform's *supervision* of it; nothing tells the process
itself, and nothing refuses its results afterwards.

**What it means.** "Stop" is not a stop today. If you need work to actually end, stop the
companion.

**Why it is not fixed here.** It needs a decision about where the check belongs — the platform
refusing results for a stopped run, the companion checking its own run's state, or both — and that
is a change to how every run on the platform works, not an accessibility one. It is written down
so nobody discovers it the way we did.

### #59 — The failing backend tests were three causes, not one ✅ FIXED

**What it was.** Running the accessibility suites produced failures. They were expected and they
were logged, and **not one of them was a product defect** — but the record said they were all one
thing, and they were not.

**What was observed.** `GAP_FIX_BUILD_PLAN.md` §9.25 recorded 14, all attributed to the `graphics`
checker. Re-measured on 1 September the real figure was **21 backend and 1 frontend**, from four
causes — and the last five of those are their own finding, **#62**.

| Count | Where | What it was |
|---|---|---|
| 11 | `test_a11y_capture` (5), `test_a11y_report` (6) | The `graphics` widening of 27 August. An image was claimed by **both** `alt` and `graphics`, deliberately — different questions, and an accurate alt text on an invisible icon passes one and fails the other. The tests still expected one checker. |
| 4 | `test_a11y_conformance` (2), `test_a11y_findings` (1), `test_a11y_conformance_rest` (1) | **Nothing to do with `graphics`.** Stale assertions against the conformance guard of 27 August. |
| 5 | `test_a11yai_capability` (2), `test_a11y_ownership`, `test_a11y_journey`, `test_a11y_wcag` | Never counted before — see **#62**. |
| 2 | `test_a11y_selection_corpus` | 1.4.11 owning no failure shape — see **#60**. |

**One diagnosis in the 1 September note was itself wrong, and it is corrected here.** The
conformance failures were written up as *"their fixtures load no ownership registry"*. They do load
it. The real cause is sharper: the fixture records a **rule-scanner** pass for **1.1.1**, and
`ownership.json` gives 1.1.1 to the **AI**. axe's `image-alt` proves an alt attribute *exists*;
whether it *says* anything is the judge's question. So the guard correctly refused the claim —
which is the 1.2.2 captions bug in miniature, caught by the very guard built for it.

**How it was fixed.** Sixteen of the twenty-one needed **no assertion edited at all**: they went
green the moment the `graphics` claim was withdrawn (**#60**), because every one of them was
objecting to that single thing. Of the rest, the four conformance fixtures now name the engine that
owns the criterion they are covering — each with a comment saying why, so nobody "fixes" them back.
The guard's own coverage is untouched: `test_a11y_conformance_guard.py` already holds thirteen
tests on exactly this rule, from both directions.

**What it means going forward.** The bar is a **green suite**, not "the sixteen are these sixteen".
A background of expected red is how #62 hid for five days.


### #60 — 1.4.11 was claimed with no evidence of any kind ⭐⭐ ✅ CORPUS AND METHOD BUILT

**What it is.** `graphics`, the sixth element check, added 27 August. It asks the half of *Non-text
Contrast* that arithmetic cannot: **are the meaningful parts of the icons, charts and diagrams
actually visible enough?** Somebody has to know which parts of a picture carry meaning before any
ratio means anything, which is why it is an AI check and not a rule.

**What was observed.** Three gaps: no selection-corpus rows, no `check_graphics` on the capability,
and **zero answer-key records** where every other checker has 31 to 42. Every other check on this
platform can say how often it is right. This one could not, at all.

**And then the decisive thing, which nobody had read.** The platform had been saying since the day
the check landed that the claim itself was wrong:

```
claimed == set(criteria_for(owner=Owner.AI, tier=Tier.IN_POC))
Extra items in the left set: '1.4.11'
```

`apps/a11y/data/ownership.json` records 1.4.11 as owned by **`rule`**. `A11Y_CHECKER_CRITERIA` is
the map of what the **AI** owns. Putting 1.4.11 in it made the two disagree, and the drift guard
said so — along with four other guards. The case for the widening was argued in a code comment; the
registry was never changed to agree.

**How it was fixed, in two steps on the same day.** The claim was first *withdrawn* — `graphics`
moved out of the live checker list into `HELD_BACK_SELECTION_RULES`, with nothing deleted. The team
then asked the right question: **does the checker actually work?**

It does, and the proof was already in the database. On the 31 August Meridian run it selected 59
pictures, received 59 screenshots and returned 59 verdicts — and it was reading pixels, not markup:

> *"Screenshot shows a flat SVG illustration of a brick building. The meaningful parts — the
> terracotta building outline against a light grey background, the arched windows (white/light on
> the dark brown wall)…"*

So the hold was lifted after a few hours and the real blocker was fixed instead — see **#65**.

**Two of the three gaps are now closed.** `check_graphics` exists on the capability, so the
criterion can be asked about outside an audit run. The selection corpus holds seven rows for
1.4.11 — five shapes the check must reach and two it must leave alone — every one drawn from the
rule's own written scope rather than invented, and two of the five reachable by nothing else in the
platform: a chart drawn as a bare `<svg>`, and an icon painted as a CSS background image.

**The third stays open, and is now #64.** Answer-key records have to be labelled by someone other
than the author of the checker, and no code change satisfies that. So 1.4.11 ships **judged but not
measured for accuracy** — which the team has accepted, and which the report should state rather
than gloss. Worth keeping in view: in 59 verdicts this check has never once returned a failure. It
runs, and it reasons about the right thing; whether it can say *no* is still unproven.


### #61 — One frontend test only passed in UTC ✅ FIXED

**What it was.** `audit.test.tsx` asserted the screen shows `13:04` for a stubbed
`2026-08-31T13:04:11Z`. The screen renders that in the **viewer's own local time**, deliberately, so
on a machine in India it correctly read 18:34 and the test failed. 415 of 416 frontend tests passed;
this was the one.

**What it meant.** The feature is right and is the point of the fix it covers — a count with no time
beside it reads identically one second and half an hour after the machine died. Nothing a user sees
was wrong. But the suite was **not portable**, and a test that is red only on your machine is one
people learn to ignore.

**How it was fixed.** The **test timezone is pinned to UTC** in `vite.config.ts`, not the one
assertion — because the next time-rendering test somebody writes would have had the same problem and
nobody would have connected the two. Set at config load, which happens in the Vitest parent process
before any worker is forked, so workers inherit it; and cross-platform, unlike a `TZ=UTC` prefix on
the npm script, which Windows does not understand. **416 of 416 pass.**


### #62 — Five more red tests than anyone had counted, all naming the same thing ✅ FIXED

**What it is.** The 1 September review measured the failing tests across eleven a11y test files and
reported sixteen. There are **thirty-three** a11y test files. Sweeping all of them found
**twenty-one**.

**What the five were, and why they matter more than their number.**

| Test | What it had been saying since 27 August |
|---|---|
| `test_the_capability_offers_a_check_for_every_checker_in_the_registry` | there is no `check_graphics` method — a checker that can be selected and dispatched and has nowhere to put its verdict |
| `test_every_checker_maps_to_a_real_wcag_criterion` | the checker map is not the five the POC shipped |
| `test_the_poc_checkers_and_the_registry_cannot_drift_apart` | the map claims 1.4.11 and the registry does not give it to the AI |
| `test_the_poc_element_checks_are_untouched` | the element-check set changed without a decision |
| `test_the_statement_arrives_compiled_with_every_criterion` | the conformance guard, as in **#59** |

**What it means.** Four of the five were the platform's own drift guards, and **all four were
pointing at the same fact** — the one in **#60**. They were not noise around a known problem; they
*were* the problem, stated four times, for five days, in a suite everybody had been told had "about
sixteen expected failures".

This is **#57 for the third time**: a check whose whole purpose is to notice something, ignored
because it was noticing it. The first was a scan rule, the second was 1.4.11 itself, and this is the
test suite. The pattern is not a test problem — it is what an accepted background of red does to
every signal inside it.

**How it was fixed.** All five are green. Four of them were saying one thing — see **#65** —
and went green when that was fixed. And the count is no longer the thing being remembered:
**the a11y suite is at 1,765 passing and zero failing across all thirty-three files**, so the
next red test is visible on the day it appears rather than five days later.


### #63 — Pausing the judge would have handed 1.4.11 back to the arithmetic ✅ FIXED

**What it is.** The most dangerous thing found today, and it was found by a test refusing to go
green for the wrong reason.

**What was observed.** With `graphics` held back (**#60**), one test stayed red:
*`test_non_text_contrast_is_covered_by_a_rule_AND_a_judge_and_needs_both`*. Its whole point is that
1.4.11 has two halves and needs both. Following it through:

* the ownership registry gives 1.4.11 to **`rule`**;
* `page_rules` records its measurements under the **`rule`** engine;
* the conformance guard asks *did an engine entitled to settle this criterion look?* — and with
  `graphics` gone, the answer would have been **yes**.

So a page whose buttons all had visible edges would have been reported as **Supports 1.4.11** with
**nothing having looked at a single icon**. That is QA-25 word for word — a narrow pass claiming a
criterion it cannot prove — recreated by the act of pausing the check built to fix it.

**How it was fixed.** A held-back check now **withdraws its criterion from positive claims** rather
than handing it to the other half. `A11Y_HELD_BACK_CLAIMS` derives the criteria from the held-back
map, and `suggest()` returns no suggestion for them — placed with the other positive-only guards, so
**failures are untouched in both directions**: a control edge under 3:1 is still a proven Level AA
defect and is still reported. The test holds both ends: that a held check is *held and not
deleted*, and that while it is held nothing may claim its criterion.

**What it means.** Withdrawing a claim is not the same as disabling a feature, and doing the
first by doing the second is how the original bug gets rebuilt.

**Nothing is held back today** — `graphics` runs again and 1.4.11 is both measured and judged
(**#65**). The guard is kept and tested anyway, because the day somebody holds a check is
exactly the day nobody re-derives this, and it cost a near-miss on a client-facing document
to learn it once.


### #64 — The answer key still has nobody's signature on it 🔬 RECORDED, NOT FIXED

**What it is.** The accuracy figures rest on an answer key of **173 records that are all
draft-unadjudicated**. Until an expert signs them off and the blind second pass runs, those figures
measure how often our checks agree with a careful draft — not how often they are right.

**Why it is not fixed here.** It cannot be. The golden set's own rule is that the person who labels
must not be the person who wrote the checker, and no code change satisfies that. It is recorded here
so the number is read for what it is, and because **#60** cannot be reversed without it.

**What is also still open, and does not block a run:** the contested 0.833 precision on `structure`
(three tables where our check and the key disagree, needing a ruling, and it can only move up);
`#open-exports` and `#newsletter-email`, two judgement calls the key's own author flagged both ways;
screenshot paging; and **#58** — terminating a run still does not stop the agent, so if a run must
actually end, stop the companion.


### #65 — A correction agreed on 27 August never reached the data ⭐⭐ ✅ FIXED

**What it is.** The single fact underneath #60, #62 and #63, and the reason all three existed.

**What was observed.** `RESEARCH_CORRECTIONS.md` **R14**, agreed 27 August, says of WCAG 1.4.11:
*"the rationale is correct and the owner is not."* The research report gives the criterion to the
arithmetic; the team decided the judge decides it. Both halves of the check were built the same day.

**And `ownership.json` was never changed.** The register that actually routes every check still said
`"owner": "rule"`.

So from 27 August the code assumed one thing and the data said another. Five separate self-checks
reported the disagreement **every day for five days**, and every one was read as background red:

| Guard | What it was saying |
|---|---|
| the ownership drift test | the AI's map claims 1.4.11 and the register does not give it to the AI |
| the register/map equality test | the checker map is not the five the POC shipped |
| the POC element-check list | the set of checks changed without a decision |
| the capability-surface check | there is no `check_graphics` method |
| the selection corpus (both halves) | 1.4.11 is claimed with no example behind it |

**What it means.** *A decision recorded only in prose is not a decision the platform can act on.*
Every layer above the register had already been changed to match R14 — that is why the checker
worked. Only the register was left, and the register is what routes.

**How it was fixed — and deliberately not by editing the register.** `data/ownership.json` is a
**derivation**, not a decision record: it is rebuilt from the committed research PDF and proved
against eight independent cross-checks, including the report's own headline counts. Editing a row
there would make the file disagree with its own source, and the rebuild would fail — correctly.

So the decision lives in **`ownership.ENGINEERING_OVERRIDES`**, applied when the register is loaded.
The committed file keeps saying what the report says; the routing table carries what the team
decided. Both are true statements about different things. Three guards keep it honest: the file is
asserted to be unedited, the override set is exactly one criterion, and **every override must name a
criterion that appears in `RESEARCH_CORRECTIONS.md`** — because a correction in code with none in
prose is this same failure pointing the other way.

**Also completed, both missing since 27 August:** `check_graphics` on the capability, and seven
selection-corpus rows for 1.4.11 — five shapes the check must catch and two it must leave alone,
every one taken from the rule's own written scope rather than invented. Two of the five can be seen
by nothing else in the platform: a chart drawn as a bare `<svg>` (never announced, so the alt check
skips it on purpose) and an icon painted as a CSS background image (no tag or attribute says it is a
picture).

**What it leaves.** Six element checks, all six exposed, register and code agreeing for the first
time since 27 August, and 1.4.11 both measured and judged. The conformance statement is now
*stricter* than before any of this: the criterion cannot read as supported unless the judge has
actually looked.

---

## 10. What has run live, what has not, and what I am least sure about

**This section used to open *"nothing has ever run live, not once"*. That is no longer true**, and
the correction is the most important one in this guide. It has been rewritten on **21 August**
against five real runs, because a section whose only job is to say what is proven is worthless
the moment it lags.

### 10.1 What has now run live ✅

**Meridian Library, 20–21 August, five runs**, a real browser on a real machine. The last one:

| | |
|---|---|
| Pages | **11 of 11** captured, none unreachable |
| Dispatch | **196 element slots of a 200 limit** — 124 distinct elements |
| Verdicts | **124 of 124**, nothing deferred, nothing filed unjudged |
| Findings | **21** — 14 `alt` (1.1.1) and 7 `label` (2.5.3), every one a failure |
| Waiting on a person | **0** |
| Raised from nothing | **21 defects + 1 backlog epic** |
| Documents | report (103,748 chars, 22 capture links) and baseline v1, both published |
| Wall clock | 10:51 → 11:50 |

**What those five runs have proven, end to end:**

| | |
|---|---|
| **Registering a page list** | 79 routes pasted from `routes.json`, `/health` honoured as out of scope |
| **An audit claimed by a machine** | *Waiting for a machine* → *Starting* → *Visiting pages* → *Checking what was found* → *Complete* |
| **The capture** | elements, computed styles, accessible names and screenshots, posted one screen at a time |
| **The scanner resolving out of the audited project** | Meridian's own axe, not the companion's |
| **Real AI verdicts** | including `<img id="photo-interior" … alt="library">` against 1.1.1 at 0.92, and four `<div>` switches against 1.3.1 at 0.97. **Defects no scanner on the market finds** — the entire argument for this build, demonstrated repeatedly |
| **The ledger, the defects and the backlog** | 21 defects and an epic raised from findings, deduplicated by fingerprint |
| **Both documents** | report and baseline published from real findings, with working links to the captures |
| **The conformance statement rendered from real evidence** | it names the audit it was drawn from, and when |
| **A pass stopping at its own limit, and saying so** | 212 slots against a limit of 200 — recorded, counted and offered back |
| **A second pass over one capture** | "Check the rest" answered the 6 elements the cap left, found **four more real failures**, and republished both documents |
| **A run that left nothing behind** | 196 of 200 — no deferral, no button, no incompleteness warning. The negative case is proven too |

⚠️ **And this corrects what was said about the 20 August run.** It was read as having died at
"81 of 144" with 63 elements lost. It had not: an audit sends one request per (element, check)
slot, and those ten pages are **144 slots but 81 distinct elements** — the header and footer are
the same markup on every page and one verdict answers all ten. Nothing was ever lost.

#### The first run at real size — 31 August

**94 pages, 2,171 elements, 1,065 questions.** Eight times the largest previous run, and the first
one big enough for the capture and the judging to take long enough to collide.

| | |
|---|---|
| Pages | **94 of 94** captured, none unreachable, no reconciliation gaps |
| Elements | **2,171** |
| Questions | **1,065** distinct — 800 sent, 265 correctly queued |
| Real verdicts | **644** before it was stopped (567 pass, 51 fail, 18 uncertain) |
| Rule-scanner findings | **335**, all genuine |
| Friday's fixes, confirmed live | 20 `label-content-name-mismatch` + 3 `td-has-header` — findings no audit before 28 August could have produced |
| Accuracy number | **none, and correctly none** — see below |

**What worked is most of it.** Every page visited, every element captured, the judge answering
steadily for over an hour. The scale that Friday's dataset work made possible is the scale that
this run proved the capture holds.

**What broke is one thing, four ways.** A duplicated close destroyed the audit's own record of
itself: #54 above, with #55 as its consequence, and #56/#57 found in the wreckage while reading
what had actually been measured. All four are fixed. #58 was found while trying to stop it.

**Why there is no accuracy figure, and why that is the right outcome.** Only **43 of the 173**
answer-key records received a real verdict — `alt` 12, `color` 9, `label` 19, `semantics` 0,
`structure` 3 — against a minimum sample of 30. Every checker reads *not yet measurable*. The
floor did exactly what it exists for: a number built on 43 records would have been quotable,
wrong, and impossible to withdraw.

The audit was cleared afterwards on the team's decision — a genuinely blank slate, judgments
included — so the next run proves itself end to end with nothing inherited. The 95 registered
routes were kept.

### 10.2 What is still unproven 🔬

Five runs have not touched **any** of these. Ranked by how likely a live run is to surprise us:

1. **The greenfield capture.** Every run so far has been a **brownfield baseline audit**. The
   greenfield capture is generated by an agent from a written contract, not run from a script we
   ship. The contract is right and enforced on ingest; whether every generated suite honours it
   is unknown. The tell is a report where nearly everything reads *not evaluated*.
2. **The keyboard journey.** Eight criteria, one agent, a real browser, a live application. ⚠️ It
   has **never opened a page**, and until #21 it *could not have* — four of its tools were never
   exposed to the agent. Still the least-proven part of this build, by a distance.
3. **The review queue with something in it.** ⚠️ **New to this list on 21 August, and it earned
   its place by being invisible.** Across five runs the queue has been **empty every single
   time** — every check has been confident enough to answer on its own. That is a good result for
   the judge and it means the console, the 15-minute lock, the claim-and-release, and the
   confirm-raises-a-defect path have **never been exercised by a real reviewer on a real
   finding**. A screen that is never reached is not a screen that works.
4. **Signing a conformance statement.** It has been *rendered* from a real audit's findings —
   that part is proven. Nobody has signed one against a live run, and signing is what registers
   and approves the artifact.
5. **An audit that finishes at real size.** ⚠️ **Corrected 31 August, and only half answered.** The
   multi-pass capture is now proven at 94 pages: two passes, every page visited, nothing
   reconciled away. What is *not* proven is a run of that size **finishing** — the 31 August audit
   was stopped by hand after the defects in #54–#55, so no large audit has yet reached
   `complete` under its own steam and published its documents. That is the next thing a live run
   settles.

⚠️ **A real `passes` array is no longer on this list.** The scanner returns positive evidence into
the platform on every live run — 175 passed on the last one. Answered.

⚠️ **And one item was removed from this list on 31 August without being proven: an accuracy
number.** It is not unproven-and-pending; it is *not yet measurable*, which is a different and
more honest state. 43 of 173 records were scored against a floor of 30 per checker. See §10.1.

### 10.3 What is proven by tests, and how much

Measured on this branch on **31 August**, after §9.25. **The failure counts in this table were
superseded on 1 September** — see the note under it, and #62 and #65:

| Ran | Result |
|---|---|
| `test_a11y_dispatch.py` · `test_a11y_baseline.py` | **238 passed**, including the three new regressions for #54 and #55 |
| `test_a11y_report.py` · `test_a11y_findings.py` · `test_a11y_review.py` · `test_a11y_defects.py` · `test_a11y_judging_carrier.py` · `test_a11y_baseline_report.py` · `test_a11yai_capability.py` | 312 passed, 9 failed — **all 9 pre-existing, see below** |
| The a11y audit frontend suite | **65 passed**, `tsc --noEmit` clean |
| The scorer's own tests | **41 passed**, no database, no Django |
| The fixture harness (`npm run check`) | **all 8 checks green**, 94 routes, 173 records, 0 never-collected |
| `ruff` on `apps/a11y` | clean. `mypy` reports 3 errors, all pre-existing on the same lines |

⚠️ **Superseded on 1 September, and kept here because the count is the point.** This paragraph
recorded 14 tests failing before the work started, all tracing to the `graphics` / 1.4.11 checker
added on 27 August and never wired into the capability interface, the selection corpus, or the
test expectations that enumerate checkers — and it said there is no `check_graphics`, so 1.4.11
could not be asked through the capability at all.

**Both halves of that are now out of date.** Sweeping all thirty-three a11y test files found
**21 failing, not 14** (#62), and they were all naming one fact — the correction of 27 August that
never reached the data (#65). `check_graphics` exists on the capability
(`backend/integrations/a11yai/builtin.py`), `graphics` is in the live checker list
(`backend/apps/a11y/checkers/rules.py`), and the a11y suite is reported at **1,765 passing and
zero failing** across those thirty-three files. What is still open is the answer key: #64 records
that nobody outside the checker's author has signed it, and no code change satisfies that.

Every number here was **measured on the day this section was written**, not carried forward. An
earlier version of this table quoted 390 backend and 374 frontend tests from 21 August; both had
been true once.

⚠️ **The backend suite is never run whole** — it is killed by the machine. Only the files a change
touches are run, which is why the table names files rather than claiming a total.

⚠️ **Failures elsewhere in the repository**, all pre-existing and none accessibility:
`test_guardrails.py::test_run_build_clean_change_reports_ok` fails because this machine has no git
remote to push to; there is Claude Agent SDK API drift in `test_drivers.py`; and `ruff` reports
four long-standing E501/E402 findings in `api/views.py`, none in accessibility code. **No task has
been raised for any of them.**

⚠️ **And the lesson of 20 August, which this section exists to keep in front of everyone:** three
of the six defects that run found had a **green test suite standing over them the whole time**. A
passing test proves the thing it tests. It does not prove the product ever calls it — #19 — nor
that the list it checks is the list that matters — #21 — nor that the fixture resembles the real
case — the batch that was 144 elements where every test used three.

**21 August added a fourth to that list.** Every fix in §9.8–§9.11 was green in tests and wrong on
screen, because the tests asserted the renderer and the team was reading a **stored file rendered
before the fix**, or a screen showing a **previous pass's numbers**. A test proves the function.
It does not prove the artefact the person actually opens.

---

## 11. Appendix

### 11.1 Screens

| Screen | Route |
|---|---|
| Pages & audit, and keyboard journeys | `/a11y/pages` |
| Review queue | `/a11y` |
| Conformance statement | `/a11y/conformance` |
| One finding, read-only — the capture the report describes | `/a11y/finding/<finding id>` |
| Brownfield onboarding hub (step 6 links here) | `/onboarding` |

### 11.2 Endpoints

| | |
|---|---|
| `GET/PUT /api/projects/<p>/a11y-routes/` | the page list |
| `GET/POST /api/projects/<p>/a11y-audits/` | audits; POST opens one and returns its manifest. GET carries live `progress` for anything in flight and `unanswered` for anything finished |
| `POST /api/projects/<p>/a11y-audits/<a>/rejudge/` | ask again about the elements of one finished audit that nothing ever looked at. Visits no page |
| `GET/POST /api/projects/<p>/a11y-journeys/` | journeys; POST starts up to the cap and names what it did not start |
| `GET /api/projects/<p>/a11y-review/` | the queue |
| `GET /api/projects/<p>/a11y-finding/<f>/` | one finding, opened to be read. **Takes no review claim** — the queue's own `GET a11y-review/<f>/` does, which is why this is separate |
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
| Element judgments per judging run | 200 by default — **set per workspace**; the 31 August audit ran at 800 |
| Keyboard journeys started at once | 10 |
| Steps per journey | 40 |
| Review lock | 15 minutes, self-renewing |
| How long the companion waits for the platform | 60 seconds — **except closing an audit, which is allowed 15 minutes** (#54) |

⚠️ **The judgment limit counts distinct questions, not elements-times-checks.** The same markup on
twenty pages is one question and one answer, so a site whose furniture repeats costs far less than
its element count suggests. It is a limit on what one run may *spend*, and a run that reaches it
stops and offers the rest back rather than skipping anything.

⚠️ **The 15-minute allowance on closing an audit is not a tuning knob.** Closing a 94-page audit
is minutes of real work, and the 60-second default caused #54 — the companion decided a healthy
audit had failed and closed it a second time.

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

### #66 — A new tenant silently inherits a judging cap of 200 🔬 RECORDED, NOT FIXED

**What.** `caps_for()` falls back to `DEFAULT_MAX_JUDGMENTS_PER_RUN = 200` when the `a11yai`
connection has no `max_judgments_per_run` in its scopes. A freshly created tenant has empty scopes.

**Found.** 2 September, during the capture phase of audit `f60c8f1a` on a brand-new tenant — early
enough to correct before dispatch.

**Why it matters more than the number suggests.** 1,068 distinct questions at 200 per pass is about
five passes instead of two. But the failure is invisible: the audit stops saying it reached "this
run's limit", which is exactly what it says when a correctly configured run reaches 800. There is no
error, nothing is lost, and nothing on screen states the cap — so the symptom is a slow day nobody
investigates.

**How to reproduce.** Create a tenant, add the `a11yai` connection, read `caps_for(tenant_id)`.
Returns `(200, None)`.

**Not fixed.** Options are to surface the cap at project setup, seed it with the tenant, or print it
on the audit screen before the run. The team's call.

---

### #67 — The findings ledger write fails silently when the run fails ⭐⭐ 🔬 RECORDED, NOT FIXED

**What.** `publish_report` calls `merge_run` then `record_run_findings` inside a best-effort handler
that records any failure onto the returned dict. That dict comes back on the Temporal activity's
return value — which is never persisted when the run itself fails. `record_run_findings` takes
**427 seconds** on a 94-page audit. So on precisely the run most likely to cut it short, its error
cannot be recorded anywhere.

**Found.** 2 September, after pass 2 of audit `f60c8f1a` ended on a subscription session limit. The
Accessibility screen read 370 problems and 106 awaiting review for **80 minutes**; both were pass 1
figures. The report document had regenerated at 05:39:38 and the ledger had not.

**How it was proven.** Every one of the 476 ledger rows had `created_at` and `updated_at` between
04:13 and 04:16, and pass 2 finished at 05:39 — so no row was touched afterwards. A dry run of
`record_run_findings` inside a rolled-back transaction then showed the function itself succeeds
(76 opened, 377 seen again, 99 resolved) and takes 7 minutes.

**Confirmed non-permanent.** Pass 3 ran the same write to completion, moving the queue 106 → 2.

**The write is correct; the silence is the defect.** Preferred fix: record the ledger outcome on the
audit `summary`, which survives a failed run, instead of only on the activity result. Secondary:
reduce the write cost.

**Watch for it.** If an audit finishes and the two headline counts do not move within about ten
minutes, the ledger write did not complete. There is currently no other signal.

> **Team decision, 2 September.** Both of the above were presented in full with a proposed fix, a size and a risk assessment. **The team weighed them and judged neither urgent**, and chose to spend the time on conformance-tab UI work instead. They are deferred by decision, not by neglect — do not reopen the question without new evidence. The fixes proposed were: for the cap, show it on the audit screen and set it explicitly for new workspaces; for the ledger, record the reconciliation outcome on the audit's own `summary` (which survives a failed run) rather than only on the run's return value, and leave the seven-minute write cost alone — speed is a comfort, the silence is the defect.

---

### #68 — Three defects on the conformance tab, and a fourth found while fixing them ✅ FIXED

**Found.** 2 September, from the team reading the screen. All three were bugs rather than design
choices — nobody decided any of this.

**#68a — The three summary tiles ran together on one line.** The tab hand-rolled its own copy of
the shared `Tile` component using `<span>` for the number, the label and the sentence. A span is
inline, so all three sat on one line — `20EVALUATEDSomething actually checked these` — and the
`margin-top` on `.tile__label` / `.tile__sub` was inert, because top margins do nothing on an
inline box. Every other screen used the component and stacked correctly, which is why this was
the only tab that looked wrong. **Fix:** use the component.

The wording was rewritten at the same time, by team decision: `20 of 55 · Checked`,
`35 of 55 · Not checked yet`, `4 · Waiting on you`. The third deliberately carries no "of 55"
because **it is a subset of the second** — a criterion lands there precisely because nothing
suggested a level, which drops it into "not evaluated". Printing "4 of 55" would invite a reader
to add it to the other two.

**#68b — The count of criteria needing a decision could not be acted on.** The tile said four
criteria were waiting on a person; nothing in the list of fifty-five said which. **Fix:** those
rows carry an amber edge, a tint, and a "needs your decision" chip. `needs_a_person` was already
on every row and already reaching the browser — no backend change was needed, it simply was not
shown. Colour is never the only cue: the chip says it in words.

**#68c — The conformance dropdown clipped every option longer than a few characters.** It
carried `.input` rather than `.select`, so it never got `appearance: none` nor the 32px of right
padding the chevron needs — the **browser's own** arrow was painted over the words, and
"Partially supports" rendered as "Partial". It also shared one flex row with the "suggested"
chip, so in a narrow column the two competed and the control lost. **Fix:** the right class, a
168px floor, and the chip stacked beneath rather than beside.

**#68d — A 2.46:1 chip, introduced by the fix for #68b and caught before it shipped.** The first
version of the "needs your decision" chip was white on `--warning`, which measures **2.46:1** —
a hard WCAG AA failure at any size, in the accessibility tool. It was found by measuring the
rendered page rather than by looking at it.

**The wider finding is the one worth keeping: `--warning` cannot be used as a text colour at
all.** It measures 2.19:1 on its own `--warning-bg` tint and 2.46:1 under white. The app's
existing pattern for other roles (`background: var(--x-bg); color: var(--x);`) would therefore
have failed here too, so copying it was not an option. **Fix:** a new `--warning-ink` (#7A4E06)
for warning-coloured text and figures — 6.42:1 on the tint, 7.19:1 on white, both measured in
the live browser.

> **Not checked, and worth someone's time:** whether `--warning` is used as a text colour
> anywhere else in the app. This entry only fixed the two places the conformance work created.

**Verified.** 418 of 418 frontend tests pass, including two new ones pinning the row marking and
the dropdown's class. The rendered page was measured in a real browser for computed colour,
contrast, control width and stacking direction — not eyeballed.

---

### #69 — The accuracy harness demands an app version and then throws it away 🔬 RECORDED, NOT FIXED

**What.** `run.py` takes `--app-version` and **refuses to score without it**. The Makefile explains
why in detail: nothing in the platform records which version of the application was audited, so
the number has to be stated by hand, and taking it from the answer key instead *"would make both
sides agree by construction and turn the check into decoration"*. All of that reasoning is sound.

**But the value is used for exactly one thing — `labels.check_app_version(manifest, ...)`, a guard
that the key matches the app — and is then never written to the results file.** Confirmed on the
2 September run: `1.4.0` was passed on the command line and the string appears **zero times** in
`results/20260902T140726+0000.json`. There is no `app_version` key in the file at all.

**Why it matters.** The results files are the accuracy record; the whole point of demanding the
version is that a score is meaningless without knowing what was scored. As it stands, a file from
six months hence cannot answer *"which build of Meridian produced these numbers?"* — and the two
1 September files cannot answer it either. The guard runs and the evidence of it is discarded.

**Found.** 2 September, while running the harness for real against audit `f60c8f1a`. Not a
regression — it has been true since the harness was written.

**The fix is one line**: put `app_version` on the results payload beside `audit`, `project` and
`generated_on`. Worth doing before the next run rather than after, because the files already
written cannot be repaired — nobody recorded what they scored.

**Not fixed.** Recorded for the team's decision.
