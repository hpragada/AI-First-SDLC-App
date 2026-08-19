# Web Accessibility — What Was Built, and How To Test It

**For the Edvensoft team · 18 August 2026 · covers QA‑01 … QA‑24 (31 tasks)**

---

> ⚠️ **Correction notice — 19 August 2026. Parts of this guide are wrong. Read this before the rest.**
>
> A source-level trace of the greenfield and brownfield journeys (18–19 August) contradicted this
> document in five places. It is kept as the record of **what the team was told**, not as an account
> of how the system works.
>
> | Where | What this guide says | What is actually true |
> |---|---|---|
> | §3 and §4 headings | "Journey A" and "Journey B" | Both cover the accessibility slice **only**. A real user's journey begins at create-project and runs through upload, adopt, connect Jira/Confluence, register repositories, index code and the gap report. None of that is here. |
> | Step A1 | Routes may be registered "through Onboarding if that path is wired" | It is **not** wired. `A11yRoute.Source.ONBOARDING` exists in the code and nothing has ever written it. Registering pages is a raw `PUT` with no screen. |
> | Step A3 | `POST /a11y-audits/` as a separate step before the scan | Redundant. The companion's `audit` command opens the audit, runs it, posts every screen and closes it by itself. |
> | Step B1 | The generated greenfield suite writes "the four scanner answers" | It does **not**. The Test Automation agent's capture contract still names violations only — gap **G1**. Until that is fixed, a greenfield conformance report reads "not evaluated" against nearly every criterion. |
> | Step B4 | The keyboard journey is "optional" | It **cannot be started at all**. It has no caller, no browser grant and no address — gap **G6**. |
>
> One thing this guide never says and should: registering pages and running an audit are **terminal-only
> today**. There is no screen for either.
>
> **This document will be rewritten once the gaps in `GAP_FIX_BUILD_PLAN.md` are resolved** — at that
> point most of the rows above become true rather than corrections, and the journey sections can finally
> cover the whole journey. Until then, **`GAP_FIX_BUILD_PLAN.md` is the accurate account**, and the code
> is the source of truth over both.

---

## 0. How to read this document

This is written for someone who has not read the code. Where a technical name is unavoidable it
is explained the first time it appears.

**Three markers are used throughout, and they matter:**

| Marker | Means |
|---|---|
| ✅ | Built, and proven by automated tests |
| 🔬 | Built, and proven by automated tests — **but never once run against a real browser or a real application** |
| ⚠️ | A known limit, a gap, or something that will surprise you |

**The honest caveat, said once, at the front.** I have never run either of these journeys end to
end. This document is written from the code, the specifications and 1,100+ automated tests — not
from watching it work. Where it says *"you will see X"*, that is what the code does, not what
anyone has observed. Six of the twenty-four tasks have never touched a real browser. That is
exactly why you are testing tomorrow, and it is why every step below tells you **what would mean
it is broken** as well as what should happen.

---

## 1. What this thing is, in plain language

Making a website usable by disabled people is governed by a standard called **WCAG 2.2**. It has
**55 rules** at the levels the law generally cares about (Level A and Level AA). A conformance
claim means going through all 55 and saying where you stand on each.

Doing that by hand takes an expert several days per application. Most teams therefore either
don't do it, or run a free browser plugin, find nothing, and assume they are fine.

**What we built does three things a plugin cannot:**

1. **It uses three different kinds of checker**, because no single one can cover the standard.
2. **It never guesses.** When a check cannot settle something, it says so and hands it to a
   person, rather than reporting a clean result.
3. **It produces a document a person signs.** The platform compiles the evidence and drafts the
   wording, then stops. It never calls anything compliant on its own.

### The three checkers, and why there are three

| Checker | What it is | Covers | Example |
|---|---|---|---|
| **Rule scanner** | An industry-standard tool called **axe** that runs inside the page and measures things | **14 of 55** | "This text is grey on white at 2.9:1. The rule is 4.5:1." — measured, not judged |
| **AI checks** | Four checks that read the page and form a judgement | **11 of 55** | "This image's alt text is `checkout-hero-v2`, which reads like a filename." — a judgement |
| **Keyboard agent** | An agent that actually walks through a journey using only the keyboard | **8 of 55** | "I tabbed into the date picker and could not tab out." |

The remaining **22 criteria can only be assessed by a person.** No tool on earth can tell you
whether a video's captions are *accurate*, or whether an error message is *helpful*. The
platform says so rather than pretending otherwise.

### The one idea everything is built around

> **A criterion nobody looked at must never look like a criterion that passed.**

This sounds obvious. It is the single most common way accessibility tooling lies. If a scanner
has no rule for "captions are accurate", it reports nothing — and a report that lists only
problems then shows a clean page. Every design decision in this build traces back to refusing
that.

---

## 2. Before you start — setting up

⚠️ **None of this works until these five things are done.** They are not optional, and four of
them are outside my control.

### 2.1 Apply the database changes

Five database changes were added by the last two tasks and **have never been applied to the
shared server**. I created them and ran them only against a local test database, because
changing the team's shared database is your call, not mine.

Without them, the accessibility screens will error immediately.

```bash
cd backend && ../.venv/Scripts/python.exe manage.py migrate a11y
```

⚠️ This must be run as the **postgres owner**, not as the application user — the application
user cannot alter tables. If you see a permission error on `ALTER`, that is why.

The five changes are `0021` to `0025`. They add: the pointer to page screenshots, the reviewer's
lock and decision fields, the new coverage table, the conformance statement table, and the
tenant-isolation policies for both new tables.

**How to check it worked:**

```bash
cd backend && ../.venv/Scripts/python.exe manage.py showmigrations a11y
```

You should see `[X]` beside `0021_review_console` through `0025_conformance_rls`.

### 2.2 Update the companion on the tester's machine

The **companion** is the small program that runs on a developer's own laptop. It exists because
the application being tested runs at `localhost`, which our servers cannot reach. The companion
is the bridge.

The file that drives the browser scan was changed yesterday. An **old companion silently
produces no positive evidence** — every criterion would read as "nothing checked this", and the
conformance report would be empty and technically correct but useless.

Make sure the tester's checkout is on branch `web-accessibility-build` and up to date. The file
that matters is `runner/companion/assets/a11y_audit.mjs`.

**How to check it worked:** open that file and search for `axe_passes`. If it is not there, the
companion is stale.

### 2.3 The application under test must have `axe` installed

The companion loads the scanner **from the application's own project**, deliberately — so the
version tested is the version that application ships with, not ours.

- **Meridian Library** already has it: `axe-core 4.13.0`, pulled in through
  `@axe-core/playwright`. ⚠️ It is a **development** dependency, so `npm install` works but
  `npm ci --omit=dev` would silently leave the scanner missing.
- **SpendLog** — check before you start. If `axe-core` is absent, the AI checks and the keyboard
  agent still run, and the platform will report *"the measurable checks did not run"* rather
  than pretending they passed.

### 2.4 Start the applications

**Meridian Library** (brownfield):

```bash
cd meridian-library-web-accessibility && npm install && npm start
```

It serves at `http://localhost:4180`.

**SpendLog** (greenfield) — start it however that project is normally started, and note the port.

### 2.5 Start the platform

```bash
docker compose --profile app up -d
```

Then sign in at `http://localhost:5173`. You will need an account holding the **QA Lead** role on
the project — that is the role the accessibility screens check for. Everyone else can read
everything and change nothing.

---

## 3. Journey A — Brownfield: auditing Meridian Library

**Brownfield** means an application that already exists and was not built through this platform.
You point the platform at it and ask *"where does this stand?"*

Meridian Library is a community library site: Node and Express, server-rendered pages, no
JavaScript framework. It has **69 pages**, 68 of which are marked in-scope.

⚠️ Its README claims *"Meridian Library conforms to WCAG 2.1 Level AA. Last audited March 2024."*
Treat that as a claim to be tested, not a fact.

### Step A1 — Tell the platform which pages exist

**What you do:** register the list of pages to visit.

**What this is doing inside:** the platform keeps a list of an application's pages. It has no
way to discover them — it cannot reach the app — so somebody has to say what they are. Meridian
ships a `routes.json` file listing all 69 with titles and an in-scope flag.

**Where:** `PUT /api/projects/<project>/a11y-routes/` with the list, or through Onboarding if
that path is wired for this project.

**What you should see:** a response listing every route with `enabled: true` and a summary
line.

⚠️ **The limit you will hit here.** The platform accepts at most **60 pages in one capture**.
Meridian has 68 in scope. The companion will visit the first 60, print a warning to the console,
and the platform will record the remaining 8 as **never reported** — which is honest, but the
warning is on the console and easy to miss.

> **This is worth your attention.** The number 60 was chosen when the assumption was "about 10
> pages per run, maybe 50 per application". Meridian is the first real application to exceed it.
> Options are in §7.

✅ Proven by tests.

### Step A2 — Open an audit

**What you do:** start a baseline audit.

**What this is doing inside:** the platform creates an audit record and hands back a **manifest**
— a list of pages and the base address. Opening an audit visits nothing; it cannot. The manifest
is handed to the machine that *can* reach the application.

**Where:** `POST /api/projects/<project>/a11y-audits/` with `{"base_url": "http://localhost:4180"}`

**What you should see:** an audit id, a status of `capturing`, and a manifest listing the routes.

**What would mean it is broken:** an empty manifest — that means no routes are registered, and
step A1 did not take.

✅ Proven by tests.

### Step A3 — Run the scan from the machine that can see the app

**What you do:**

```bash
python -m runner.companion audit \
  --api-url http://localhost:8000/api \
  --tenant <tenant-id> \
  --token <companion-token> \
  --project <project-id> \
  --base-url http://localhost:4180
```

**What this is doing inside — this is the heart of it:**

For each page, the companion opens a real Chrome browser and:

1. **Runs the axe scanner** and keeps **all four** of its answers:
   - *violations* — it failed
   - *passes* — checked, and fine
   - *inapplicable* — the rule ran, and there was nothing on this page for it to apply to
   - *incomplete* — **axe looked and cannot decide; a human must**
2. **Records the scanner's version**, taken from the application's own copy.
3. **Writes down every element** the AI checks might apply to — the markup, the text around it,
   the computed colours, whether a screen reader would announce a name.
4. **Takes one full-page screenshot** and records each element's exact rectangle on it.

⚠️ **The four-answer part is new as of yesterday and has never run for real.** Until yesterday
only *violations* survived, which meant a criterion with nothing against it was indistinguishable
from one nothing had checked. Fixing that is what makes a conformance report possible. **Nobody
has yet seen a real `passes` array come back.** 🔬

**What you should see on the console:** a line per route, and at the end a JSON summary with
`posted`, `captured`, `selected`.

**What would mean it is broken:**

| Symptom | What it means |
|---|---|
| `axe-core is not installed in this project` | §2.3 — the scanner is missing. The run continues; the measurable half does not. |
| `68 routes were asked for and this file carries at most 60` | The limit in §A1. Eight pages unreported. |
| `posted: 0` | Nothing reached the platform. Check the token and the API address. |
| A route reported with a `load_error` | That page would not open. The platform records it as never seen, and — importantly — will **not** let it resolve any existing finding by absence. |

### Step A4 — The platform judges what came back

**What you do:** nothing. This happens when the audit is closed.

**What this is doing inside, in order:**

1. **The scan is stored as-is**, all four answers, per page.
2. **The coverage map is written** — one line per *(page, criterion, checker)* saying: failed,
   passed, nothing-to-apply-to, or needs-a-human. **This is what lets the report say anything
   positive at all.**
3. **Elements are selected** for AI checking — only those one of the four AI checks applies to.
   A page with 400 elements might select 30.
4. **A picture of each selected element is cut** from the page screenshot.
5. **The AI checks run** — four of them: `alt` (image descriptions), `semantics` (headings and
   structure), `color` (colour used alone to convey meaning), `label` (form field labels).
6. **Everything is merged into one report**, with the scanner's measurements taking precedence
   over the AI's opinion wherever both looked at the same thing.
7. **Findings are written to a permanent ledger.** Each gets a fingerprint from *(page, element,
   criterion, checker)*, so the same problem next week is the same row — not a duplicate.

**The judgement rule, which is the important part:** every AI answer comes with a confidence.

- Confident it fails → **a failure**
- Confident it passes → **a pass**
- **Not confident either way → it goes to a person.** It is not counted as a failure and it is
  not counted as a pass.

✅ Steps 1–7 are proven by tests. 🔬 The AI checks have never run against real captured pages.

### Step A5 — Read the baseline report

**Where:** Artifacts → the artifact named **Accessibility baseline**.

**What this is:** *where this application stands*, one line per breached criterion, worst first —
severity, level, how many pages affected, how many items. Not a list of every finding; that is
what the fix list is for.

**What you should see:** a table with Meridian's real problems, and a stated note of what the
audit covered.

**What would mean it is broken:** a report claiming full coverage when eight pages were never
visited. It should say so.

### Step A6 — Read the fix list

**Where:** `GET /api/projects/<project>/a11y-backlog/`

**What this is:** what to fix first, worst first. Narrow by default — it shows the items that
clear the project's blocking bar, so the list matches what the tracker holds. Add `?all=1` to see
everything including items waiting on a reviewer.

### Step A7 — Answer the uncertain findings ⭐

**Where:** the **Accessibility** item in the left sidebar → **Review queue**.

⚠️ **This is the screen most worth your attention tomorrow.** It is new, it is where a person's
judgement enters the system, and it has never been used.

**What you should see:**

- A count badge on the sidebar item, showing how many findings are waiting **on you**. (Someone
  without the QA Lead role sees the menu item with no badge — they can read everything and
  decide nothing.)
- A narrow list on the left, worst first. Each row: the criterion and its name, the page, the
  element, and what the AI said.
- The item under review on the right, with:
  - **The page screenshot with an orange box around the failing element.**
  - A **Fit to width / Actual size** toggle. Actual size matters: you cannot judge contrast or
    a focus ring on a scaled-down image.
  - What the check saw, in plain words.
  - What it would ask for.
  - A note box, and two buttons: **Yes — this is a real problem** / **No — this is fine**.

**What happens when you answer:**

| You click | What the platform does |
|---|---|
| **Yes** | The finding becomes a **real failure**. If its severity clears this project's bar, a **defect ticket is opened** and appears on the work-items board. |
| **No** | The finding is closed. The reasoning stays on the record — nothing is deleted. |

**A note is required to reject and optional to confirm.** That is deliberate: confirming agrees
with evidence already written down; rejecting overrules it, and the note is the only record of
why.

**Three things to test deliberately:**

1. **Open the same item as two different QA Leads.** The second should see it **read-only with
   the first person's name**, and a message saying it returns to the queue on its own. If both
   can answer, that is a serious bug.
2. **Answer something, then run the audit again.** Your answer must **survive**. If the finding
   comes back to the queue, or the ticket you raised closes itself, that is the single most
   important bug in this build — see §7.
3. **Check the message when you confirm.** It should only say *"a defect has been opened"* when
   one really was. A project whose policy blocks on nothing should say so instead.

🔬 All of this is proven by 48 automated tests and has never been used by a person.

### Step A8 — Produce the conformance statement ⭐

**Where:** **Accessibility** → **Conformance statement** tab.

**What you should see:**

- Three counts at the top: **evaluated**, **not evaluated**, **awaiting a person**.
- A table of **all 55 criteria** — not just the interesting ones.
- For each: the level (A/AA), a conformance word, **which checker established it**, and **what
  was actually checked**, in words like *"Checked on 12 of 14 pages with nothing wrong"* or
  *"Nothing checked this."*
- An editable draft statement.
- A signing panel.

**What the platform will and will not say:**

| Situation | What it says |
|---|---|
| Something failed on every page checked | Does not support |
| Failed on some pages, clean on others | Partially supports |
| Checked, nothing wrong | Supports |
| The rule ran, nothing on the page applied | Not applicable |
| **A check looked and could not decide** | **No suggestion at all** — you decide |
| **Nothing looked at it** | **Not evaluated** — never rolled into anything else |

**Signing.** You must tick two boxes. The second one names two numbers: how many criteria were
**not evaluated**, and how many conformance words the **platform suggested and you did not
change**. That second number is what you are taking responsibility for, so it is on the checkbox
rather than buried.

**Test these deliberately:**

1. **Try to export without signing.** It must refuse, and say why.
2. **Sign it, then edit the wording.** The signature must be **cleared** — a signature on words
   nobody signed is worse than none.
3. **Sign it, then run the audit again so new problems appear.** The signature should **stand**
   (you did sign those words) but the statement should be marked **stale** and export refused
   until you re-sign.
4. **Look for our internal details.** The AI model, the prompt version and the scanner version
   must **not** appear anywhere on this screen. They are recorded on the export so a statement
   can be traced back later, but they are our business, not a client's. There is an automated
   test that greps for them; check it with your own eyes too.

🔬 Never run for real.

---

## 4. Journey B — Greenfield: SpendLog

**Greenfield** means an application being built through this platform. Accessibility is not a
separate exercise here — it rides along with the normal testing phase.

⚠️ **Read this before you start.** The accessibility capture is produced by the **generated test
suite**, which the test-automation agent writes. If SpendLog's suite was generated before that
capability existed, **there will be no capture and nothing to judge.** Check for a step that
writes `test-results/a11y-candidates.json`. If it is absent, re-run the test-automation phase
first.

### Step B1 — Run the testing phase

**Where:** Phases & Runs → the work item → trigger the testing phase.

**What this is doing inside:** the test-automation agent writes a test suite into a working copy
of the repository. Part of that suite is an accessibility pass that visits each screen the tests
touch and writes down exactly what the brownfield audit writes down — the four scanner answers,
the elements, the screenshot, the rectangles.

**What you should see:** a run in the console, and a test report artifact.

### Step B2 — The capture reaches the platform

**What this is doing inside:** before the temporary working copy is deleted, the companion looks
for the capture file and posts it, **one screen per call** — so a page's screenshot never shares
a request with nine others.

⚠️ **If the capture is missing, nothing is imported.** An absent capture is never treated as an
empty pass. A scan that captured nothing can never read as a page with nothing wrong on it.

### Step B3 — The AI checks run

**What this is doing inside:** the accessibility judge agent reads the stored elements in
batches, judges each, and records a verdict with the model and prompt version that produced it —
read from the run, never from the agent's own claim.

**A cost control worth knowing about:** if the same element is unchanged since last time, the
stored verdict is reused rather than re-asked. The check is on the *content* — the markup, the
surrounding text, the picture — so an unchanged button is not re-judged, and an edited one is.

⚠️ A page with a clock, a carousel or a rotating banner will look different every run and will be
re-judged every run. That is correct, not a defect, but it costs money.

### Step B4 — The keyboard journey (optional, and the newest part)

**What this is:** an agent that takes one of the written test cases and walks it using **only the
keyboard**, reporting on eight criteria that no scanner can measure — keyboard traps, focus
order, visible focus, status messages.

Of the eight, the industry scanner covers exactly **one**. That is why this exists.

**What it reports:** for each step — walked, blocked, or never reached. A blocked step must state
why. Steps after a blocked one are recorded as **never reached**, not as passed.

⚠️ **Findings from this agent never block anything.** They are reported, ticketed and reviewed,
but they never stop work — that was a deliberate decision (§7). The ticket says so on its face.

🔬 Never run for real.

### Step B5 — The gate

**Where:** Gates → the testing gate.

**What you should see:** a condition reading *"No unresolved accessibility failure — every WCAG
2.2 finding that blocks under this project's accessibility policy is fixed"*.

**What this is doing inside:** the gate is held shut by two things, and only two:

1. **Open accessibility defects** that clear this project's blocking bar.
2. **Checks nobody answered** — where the judge was unavailable or the run hit its cap.

**What does NOT hold it shut**, deliberately:

- Findings the AI was unsure about — those go to a person, not to a gate.
- Findings from the keyboard agent — advisory, always.
- Findings a person has already ruled on — once answered, the "nobody answered" claim is false.

⚠️ **A project can be configured to block on nothing at all.** That is a supported choice, not a
bug. If your project blocks on nothing, the gate will pass with open findings, and the policy
screen will say so in plain words.

### Step B6 — Defects on the board

**Where:** Work Items.

**What you should see:** each blocking accessibility problem as a defect, a child of the work
item it came from, titled with the criterion. When the problem is fixed and a later run confirms
it, the defect **closes itself**. If it comes back, the **same ticket reopens** — never a
duplicate.

⚠️ **One ticket per problem, not per finding.** If the scanner and the AI both flag the same
button, that is one ticket, and it names both.

### Steps B7–B8 — Review and conformance

Identical to A7 and A8.

---

## 5. What you can observe — the full catalogue

### 5.1 Artifacts

| Artifact | When | What it says |
|---|---|---|
| **Accessibility report** | Every run | What *this run* found, row by row, with source, confidence and suggested fix |
| **Accessibility baseline** | Every audit | *Where the application stands*, one line per breached criterion, worst first, with movement since last time |
| **Accessibility conformance statement** | When compiled | All 55 criteria, the evidence, and a person's signature |

### 5.2 Screens

| Screen | Where | What it shows |
|---|---|---|
| Review queue | Accessibility → Review queue | Findings waiting on a person |
| Conformance statement | Accessibility → Conformance | All 55 criteria and the signing flow |
| Gates | Gates | The accessibility condition and why it is or is not satisfied |
| Work items | Work Items | Accessibility defects, opened and closed automatically |
| Artifacts | Artifacts | All three documents above |
| Phases & Runs | Runs | The run console, live |

### 5.3 Verdicts a person gives

| Where | Choice | Consequence |
|---|---|---|
| Review queue | Yes, real problem | Becomes a failure; a defect opens if it clears the bar |
| Review queue | No, this is fine | Closed; the reasoning is kept |
| Conformance | Pick a conformance word per criterion | Overrides the platform's suggestion |
| Conformance | Sign | Locks the wording; unlocks export |
| Gate | Approve / reject | Ordinary gate behaviour |

### 5.4 Numbers you can check

- **55** criteria in the table. If it is not 55, something is wrong.
- **Evaluated + not evaluated = 55**, always.
- The **backlog** and the **gate** must agree about what blocks. They are built from the same
  query on purpose. If they disagree, that is a real bug.
- Meridian's **`axe-baseline.json`** is an independent record of what axe alone found. Comparing
  our reported violations against it is the strongest check available tomorrow — if we report
  fewer, we are losing findings; if more, we are inventing them.

---

## 6. The build, piece by piece

| Task | What it does | State |
|---|---|---|
| QA‑01 | Accessibility capability wired, honestly reported when absent | ✅ |
| QA‑02 / 02a | The judge is checked before dispatch; unavailability routes to people | ✅ |
| QA‑03 | The four AI checks defined | ✅ |
| QA‑04 | The WCAG 2.2 standard loaded from W3C — all 55 criteria, verbatim | ✅ |
| QA‑05 | Which checker owns which criterion — 14 rule, 11 AI, 30 human | ✅ |
| QA‑06 | Confidence thresholds; unsure goes to a person | ✅ |
| QA‑07 | Unchanged screens are not re-judged | ✅ |
| QA‑08 | Per-project policy: what to aim at, what blocks | ✅ |
| QA‑09 / 10 / 10a | Internal accuracy evaluation | ⏸ Parked. **Gates nothing.** |
| QA‑11 / 11a / 11b | The capture format and the scan inside the test suite | 🔬 |
| QA‑12 / 12a | Scanner + AI merged into one report; the findings ledger | 🔬 |
| QA‑13 | Source, confidence and fix in the report | ✅ |
| QA‑14 | Findings become defects that close themselves | ✅ |
| QA‑15 / 15a | The accessibility gate condition | ✅ |
| QA‑16 | A screen the scanner never ran on is reported, not assumed clean | ✅ |
| QA‑17 | Brownfield baseline audit — routes, manifest, reconciliation | ✅ |
| QA‑18 | The fix list, worst first | ✅ |
| QA‑19 | Design-phase accessibility criteria | ✅ |
| QA‑20 | The keyboard journey agent | 🔬 |
| QA‑21 | Its findings become tickets | 🔬 |
| QA‑22 | Keyboard findings never block work | ✅ |
| QA‑23a | The two screens, drawn and reviewed | ✅ |
| QA‑23 | The review console | 🔬 |
| QA‑24 | The conformance statement | 🔬 |

**Six tasks are 🔬.** One live session closes all six.

---

## 7. Decisions the team made — for your review

Each of these was your call. They are listed so you can reason about them and revise if you want.
Where I think one is worth a second look, I say so.

### D1 — Findings from the keyboard agent never block work

**You decided:** they are reported, tracked and reviewed, but never stop a release. Not
configurable.

**Why:** the agent judges things specialists genuinely dispute. Blocking on a disputed judgement
puts the platform in an argument it cannot win.

**Cost:** a real keyboard trap — which locks some people out of a page entirely — will not stop a
release. It appears as a ticket and it is visible, but nothing forces the issue.

**My view:** ⚠️ **worth revisiting.** A keyboard trap the agent is *confident* about is as
measurable as a contrast failure. You may want the confident ones to block while the judgement
calls stay advisory.

### D2 — The internal accuracy evaluation gates nothing

**You decided:** how well our platform performs is our report card, not a lever in a client's
release process.

**My view:** ✅ right, and it corrected a design error of mine.

### D3 — The reviewer sees the whole page with the element ringed

**Cost:** a database change and an extra image served per review.

**My view:** ✅ right. Most of these judgements turn on context.

### D4 — A reviewer's decision holds until the element itself changes

**Cost:** if a page changes around an element without changing the element, the old answer stands.

**My view:** ✅ right, and the alternatives are worse.

### D5 — A review lock lasts 15 minutes and renews itself

**Cost:** a reviewer thinking hard for 20 minutes without touching the screen could lose the item.

**My view:** ✅ right, but **watch this tomorrow.** If 15 minutes proves short in practice, it is
a one-line change.

### D6 — Capture all four scanner answers now

**You overruled my recommendation, and you were right.** I proposed showing evidence and letting
the reviewer choose every word, avoiding a companion change. You said whatever the platform
captures should be shown as it was.

**Following it through revealed the problem was three times larger than I described** — all three
checkers discarded their positive results, not just the scanner. Fixing only the scanner would
have covered 14 of 55.

**My view:** ✅ your call was right and mine was wrong. Recorded as D‑A11Y‑105.

### D7 — The signature is the gate

**Cost:** the conformance statement does not use the same approval machinery as every other gate.
It genuinely cannot — that machinery needs a run and a live workflow, and this document has
neither.

**My view:** ✅ right. Worth confirming you are comfortable that this is a *different kind* of
approval object.

### D8 — New evidence marks a signed statement stale rather than clearing it

**My view:** ✅ right.

### D9 — The engine, model, prompt and scanner versions are never shown to the tenant

**Cost:** a client cannot see what produced their statement without asking us.

**My view:** ✅ right for now. ⚠️ Note that a regulator or a procurement team may eventually ask,
and the data is recorded, so this is reversible.

### D10 — Sixty pages per capture ⚠️ **NEW — needs a decision**

**Not previously a team decision** — it was my number, chosen when the assumption was ~10 pages
per run and ~50 per application. Meridian has 68.

**What happens today:** the first 60 are visited, 8 are recorded as never reported, and a warning
goes to the console.

**Options:**
- **Raise the limit.** Simple; the risk is request size and run time, both of which tomorrow will
  measure for the first time.
- **Split into several audits.** Works today with no change, but the coverage picture is then
  spread across audits.
- **Leave it.** Honest, but easy to miss.

**My recommendation:** run tomorrow as-is so we learn the real cost of a 60-page capture, then
raise it with evidence.

### D11 — The notification bell does not count accessibility work ⚠️ **Open question**

The sidebar badge now shows findings waiting on you (fixed today). The **bell** still counts only
gates and clarifications.

**My view:** arguably it should include accessibility. I did not change it because it affects an
existing screen and was not asked for. **Your call.**

---

## 8. What has never been run, and what I am least sure about

Ranked by how likely I think each is to surprise you:

1. **The four-answer scanner capture.** Written yesterday, never executed in a browser. Nobody
   has seen a real `passes` array. The size limits I set are estimates.
2. **The conformance table against real data.** All 55 rows have only ever been compiled from
   test fixtures.
3. **The keyboard journey agent.** Built two days ago, never walked a real page.
4. **The review console with real screenshots.** The marker position is computed from the
   element's rectangle in the page screenshot's coordinates. That arithmetic is correct in
   tests; whether it lands on the right element in a real 2560-pixel-wide capture is unproven.
5. **The screens' appearance.** I verified structure, contrast ratios and that every control has
   a name. The browser preview reported a zero-size viewport throughout, so **no one has seen how
   these screens actually look.**
6. **`.diagram-frame` is a real accessibility defect in our own design system** — 2.29:1 contrast,
   used by the artifact preview screen. Flagged during the design task and deliberately not
   fixed, because it was out of scope. It is still there. ⚠️ We are selling accessibility.

---

## 9. Appendix — for anyone who wants the detail

### 9.1 Endpoints

| Purpose | Call |
|---|---|
| Policy | `GET /api/projects/<id>/a11y-policy/` |
| Pages | `GET\|PUT /api/projects/<id>/a11y-routes/` |
| Audits | `GET\|POST /api/projects/<id>/a11y-audits/` |
| Fix list | `GET /api/projects/<id>/a11y-backlog/?all=1` |
| Review queue | `GET /api/projects/<id>/a11y-review/` |
| One item | `GET\|POST /api/projects/<id>/a11y-review/<finding>/` |
| A capture | `GET /api/projects/<id>/a11y-review/<finding>/screenshot/?kind=page\|element` |
| Conformance | `GET\|PUT /api/projects/<id>/a11y-conformance/` |
| Sign | `POST /api/projects/<id>/a11y-conformance/sign/` |
| Export | `POST /api/projects/<id>/a11y-conformance/export/` |

### 9.2 Limits

| Limit | Value | On breach |
|---|---|---|
| Pages per capture | 60 | Companion truncates + warns; parser refuses |
| Elements per page | 600 | Refused |
| Page screenshot | 1.5 MB | Refused with the reason |
| Scanner violations per page | 400 | Refused |
| Scanner rule results per page | 400 | Refused |
| Review lock | 15 minutes | Returns to the queue |

**Every limit refuses rather than trims.** A capture that quietly lost half its results would
read as a page with half as much wrong with it.

### 9.3 Severity

Taken from the standard, not from anyone's opinion: **Level A → Critical**, **Level AA → High**.
A criterion whose level cannot be read falls back to High — erring towards surfacing.

### 9.4 Roles

The accessibility reviewer is the **QA Lead**. A project admin or a tenant admin can also act.
Everyone else reads everything and changes nothing.

### 9.5 Test counts

| Area | Tests |
|---|---|
| Accessibility backend (26 files) | 492 + 145 + 224 + 274 |
| Frontend | 266 |
| New in the last two tasks | 115 |

Coverage on the newest code: **98%**.

---

*Written from the code, the specs and the tests. Not from a live run — that is tomorrow's job.*
