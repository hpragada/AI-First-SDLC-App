# User Journeys — Web Accessibility

**Rewritten 20 August 2026, from the source.** The first version was written before any of this
was built, as a description of what we intended. This one says what a person can actually do
today, what they cannot, and where each journey is reached from on screen. Where the intention
and the code disagree, the code wins and the step is corrected here.

**How to read a journey.** Each one carries a status, and the statuses mean exactly this:

| | |
|---|---|
| ✅ **Built** | Every step below can be done by a person today, from a screen |
| 🟡 **Part-built** | Some steps are real; the rest are named, with what is missing |
| ⬜ **Not built** | Nothing of it exists. It is written here because it is still the plan |

⚠️ **Built means "a person can reach it and the tests pass". It does not mean "it has run."**

**Updated 21 August 2026.** This paragraph used to say *"nothing in this document has ever
executed against a real browser or a real application"*. **That is no longer true, and the
distinction it was making still is.**

**What has run:** five audits against Meridian Library on 20–21 August drove the **brownfield**
chain end to end — a real browser on a real machine, real AI verdicts, real defects opened, both
documents published, and a second judging pass over one capture. Seventeen findings came out
of those runs and are built (`GAP_FIX_BUILD_PLAN.md` §9).

**What has not:** every one of those runs was a **baseline audit of an existing application**. A
baseline audit does not touch the greenfield capture, the keyboard journey, the review console or
signing — so a ✅ on J8 or J9 below still means *"reachable and tested"*, not *"watched working"*.
Each journey now says which it is. `TESTING_GUIDE.md` §10.2 is the live list.

---

## Two things the first version got wrong about who does this

**There is no "Accessibility SME" role, and there was never going to be one.** The first version
invented one and then said "for the POC this can be the QA Lead wearing a second hat". What was
built has no second hat: the role **is** `qa_lead`, with a workspace-admin carve-out, and it is
what every accessibility permission checks. Nothing to assign, nothing to configure.

**Two different permissions, decided 20 August 2026.** Answering a finding and signing a
conformance statement are the accessibility reviewer's alone. Saying which pages an application
has, and starting an audit over them, is ordinary project work — **QA Lead, Tech Lead or
Admin**. Everyone else on the project reads every accessibility screen in full and operates none
of them, and each screen says whose call it is rather than offering a control that fails on
click.

**The golden set is still an Edvensoft-internal thing, and it is parked.** It never appears in a
tenant's journey — no tenant creates, imports or sees one. QA-09 was parked by team decision on
17 August, so the 0.80 confidence threshold in the triage step is an unmeasured placeholder and
recall stays unmeasurable. Live reviewer verdicts can tell us how many of the findings we
reported were real; only the golden set could tell us how many real problems we stayed silent
about.

---

## J1 — Set up a project to be held to WCAG accessibility 🟡

*Foundation · greenfield and brownfield*

**What it delivers:** a project measured against WCAG 2.2 Level AA, with a gate that blocks on
real problems and reports the rest.

1. **The target and the gate are already set**, to WCAG 2.2 AA and the severities that follow
   from it: Level A breaches are Critical and Level AA are High, and an AA-target project blocks
   on both. Nobody has to choose them for the common case.
2. ⚠️ **There is no editor for them.** The policy lives as an `a11y` block on the Project
   Profile, exactly as the theme and export-policy blocks do, and the effective policy is
   readable at `GET /projects/{id}/a11y-policy/` — but the profile screen has no accessibility
   section, so changing the target or the gate is an API call today. The first version described
   an owner "opening the project's settings and choosing how strict the gate should be"; that
   screen does not exist. **This is the one part of J1 that is not built.**
3. **The AI checks resolve for the tenant on their own.** `a11yai` is auto-provisioned by
   migration. Nobody picks a model — and no model is ever called directly: a judgement is an
   agent run through the platform's normal driver, like every other run.
4. **The WCAG 2.2 rulebook is loaded by migration**, platform-wide rather than per project — all
   55 Level A and AA criteria (31 A, 24 AA), so every finding can quote the criterion it is
   judging against.

**Done when:** the project has a target and a gate (it does, by default), the checks resolve,
and the rulebook is loaded. **Not done:** a screen to change any of it.

---

## J2 — Design a screen accessibly and clear the design gate 🟡

*Greenfield · `OP-01`, `OP-02`, `OP-03`*

**Corrected 16 September 2026.** This journey was recorded as ⬜ *none of it exists*, with the
gate policy's `design_checks` block described as its only trace. That was wrong: the design gate
has carried a WCAG 2.2 checklist since QA-11.

The intention stands and is worth keeping: accessibility problems caught while a screen is still
a wireframe are the cheapest ones there are.

**What exists.** `apps/gates/wcag.py` builds a **22-question WCAG 2.2 checklist** onto the
`ux_design` phase's `Approval` — the questions a person can settle by looking at the design, with
each one's number, title and level read from the loaded standard rather than typed here. Every
question is required, so a question the reviewer has not marked satisfied blocks approval. A
project can switch on **5 further criteria** (2.2.1, 2.3.1, 2.5.4, 3.2.4, 3.3.4) through the
`design_checks` block on the Project Profile, with no code change. Nothing is silently left out:
each of the 55 Level A/AA criteria is either asked here or recorded with the reason it is not,
and a test proves there is no third category. The design agent targets WCAG 2.2.

**What does not exist.** There is no automated design-time check. Nothing reads a wireframe and
reports an image whose intended alt text says nothing, a status carried by colour alone, or a tap
target too small — every question on the checklist is answered by a person.

---

## J3 — Build and review a screen with accessibility caught early ⬜

*Greenfield · `OP-04`, `OP-05` — none built*

The intention: the "meaning" defects — a `<div>` behaving as a button, a field whose visible
label disagrees with what a screen reader announces — caught at code review rather than at
testing, with serious ones opening a fix item that blocks the merge.

**None of it exists.** Nothing accessibility-related runs at code review. The earlier touchpoint
is the design gate's reviewed checklist (J2); the first **automated** evidence is at **Test
Automation** (J4). A merge gate carrying the accessibility rule is an open product decision
that neither this build nor the test gate before it chose to make.

---

## J4 — Test the built screen against WCAG and clear the test gate ✅

*Greenfield · the core of the POC*

**What it delivers:** the implemented screens checked by the rule scanner and the AI checks
together, in one report, with real problems becoming tracked defects on their own.

1. **The Test Automation phase (`09b`) is where automated accessibility evidence enters.** There
   is no accessibility phase and there should not be — the evidence is a by-product of the suite that was going to
   run anyway. There is no accessibility button on the phase picker.
2. **The capture happens on the developer's machine**, in the same window in which the
   application is up and the worktree still exists — the only place with a browser and the only
   place that can reach the application. It records, per screen:
   - **all four of the scanner's answers**, not just failures — *violations*, *passes*,
     *inapplicable*, and *incomplete* (axe looked and cannot decide);
   - the scanner's version, read from the module the project imported;
   - every element the AI checks might apply to, with the browser's own computed accessible name
     and six computed style properties;
   - one full-page screenshot, and each element's exact rectangle on it.
   > ⚠️ **Gap G1, now closed.** Until 19 August only *violations* survived, which made "checked
   > and clean" and "nobody looked" identical — the one distinction a conformance statement is
   > made of. The four-answer contract is written into the Test Automation agent's body,
   > including the trap that *inapplicable is not a pass*.
   > ⚠️ **And this half is code an agent generates**, from that contract, rather than a script we
   > ship. The contract is right and enforced on ingest; whether every generated suite honours it
   > is the single most valuable thing to check on the first live greenfield run.
3. **The platform judges what came back.** Six AI checks — `alt`, `semantics`, `structure`,
   `color`, `label`, `graphics` — covering six criteria between them (1.1.1, 1.3.1, 1.4.1,
   1.4.11, 2.5.3, 4.1.2), run as an agent on a **hidden carrier work item** so
   the plumbing never appears on anyone's board (gap G4, closed). Up to 200 element judgments per
   run; the excess is deferred, never dropped.
4. **Confident findings become defects; unsure ones go to a person.** One ticket per problem, not
   per finding: the scanner and an AI check flagging the same element for the same criterion is
   one ticket. Tickets close themselves when the problem stops being found and reopen when it
   comes back.
5. **The QA Lead approves the testing gate.** The accessibility rule binds to the **testing**
   gate and to no other. Three things it says that are worth recognising: a gate with nothing to
   report says *"no accessibility check has run for this work item yet"* rather than passing;
   keyboard-journey findings are named in their own sentence and never block; and a project
   configured to block on nothing at all is a supported choice, left alone rather than corrected.

**Done when:** all of the above, which it is. **Where:** Phases & Runs → the work item's Testing
gate; findings on the Accessibility screens.

---

## J5 — Onboard an existing app and get a WCAG baseline 🟡

*Brownfield · "test it for WCAG"*

**What it delivers:** an honest account of where an application that was never built here stands
against WCAG 2.2.

1. ✅ **The way in is step 6 of the onboarding hub**, *Check accessibility*, sitting before
   *Resume* on purpose: the point of a baseline is to know where the application stands **before**
   anything is changed. Its wording changes with what has actually happened — no pages
   registered, pages registered and no audit, or audits run.
2. ⬜ **Onboarding does not assess the application's accessibility posture.** The first version
   said it would check for an existing accessibility spec and what WCAG level the app claims.
   That is `OP-06` and it is not built. Nothing reads a README's conformance claim.
3. ⬜ **Onboarding does not register the screens either.** `A11yRoute.Source.ONBOARDING` exists
   in the code and nothing has ever written it. ✅ **A person registers them**, on Pages & audit —
   paste one path per line, or a JSON list when you also want names and scope. The confirm step
   shows what would be added, what would be updated, and which pages you already have that the
   list does not mention, with their recorded problems, so "I removed this page" and "I fixed a
   typo" are told apart by the person who knows which it was.
4. ✅ **The audit runs from a screen**, on a machine that can reach the application, in as many
   passes of 60 pages as it takes. It visits exactly the pages it was asked for and accounts for
   every one — a page that would not open is recorded as never seen and is **not** allowed to
   resolve an existing finding by absence.
   > **Changed 20 August:** the audit no longer needs a local clone of the application's
   > repository. It prefers one, because the scanner resolved out of the application's own
   > dependencies is the version that application actually ships — but where there is none, it
   > falls back to the companion's own pinned browser and scanner, and every scan then records
   > `axe-core X.Y.Z (companion)` so no report implies the client's version when it used ours.
   > This is what makes an application that is not a Node project auditable at all.
5. ✅ **It leaves an Accessibility baseline document** in Artifacts: one line per criterion,
   scoped to the project rather than to the audit, so a pass that reached 38 of 50 routes does not
   silently drop what is already known about the other 12. Running it twice gives movement — what
   was fixed, what is new, what is still open.
6. ✅ **The findings become a prioritised backlog**, ordered by severity, then by how many distinct
   pages breach the same criterion, then by criterion number. Effort is deliberately not in the
   order: how long a fix takes is a judgement about your codebase the platform has no basis for
   making. Re-running never duplicates a ticket.
7. ✅ **Nothing about a baseline blocks anything.** `block_on_baseline_debt` is false by default —
   inherited debt is reported, not held against the team who inherited it. For brownfield there is
   no accessibility gate at all, because the gate binds to a testing phase run; the thing that
   plays its part is the **signature on the conformance statement** (J9).

**Done when:** 1 and 4–7, which are. **Not done:** 2 and 3 — onboarding assesses no posture and
registers no pages.

> ✅ **And 4–7 have now been watched working, five times** (20–21 August, Meridian Library). The
> last run: 11 pages asked for and 11 opened, 124 distinct elements judged, 21 failures found, 21
> defect tickets and a backlog epic opened from nothing, and both documents published with a
> working link from every finding to the screenshot it describes. **This is the one journey in
> this document that is proven rather than tested.**
>
> ⬜ Step 3's automatic half stays unbuilt and its placeholder is visible in the code:
> `A11yRoute.Source.ONBOARDING` — the label a page would carry if onboarding had found it — is
> defined and **has never been written by anything**. It is a slot held open for OP-06, not a
> feature that exists and fails.

---

## J6 — Remediate an onboarded app to WCAG 🟡

*Brownfield · "fix it to WCAG"*

**The loop exists; the campaign around it does not.**

✅ Every accessibility problem is already a defect work item that a developer picks up, fixes in
the source, and which **closes itself** when a later audit stops finding it — and reopens if it
comes back. The reviewer confirms anything the checks were unsure about, that decision holds until
the element itself changes, and the baseline report's movement section is the progress-against-
baseline view.

> ⚠️ **Built and tested; never once observed.** Five live audits have opened defects. **None has
> ever closed one**, because the project's data was wiped between every run — so a second audit
> has never met a finding from a first. That makes three things in the paragraph above claims
> resting on tests alone: a defect **closing itself**, a defect **reopening**, and the baseline's
> **Movement** section, which has only ever printed *"this is the first baseline"*.
>
> **This is the cheapest gap on the board to close and the most valuable.** Fix two or three of
> the findings in the application, run the audit again, and do not reset. It is the difference
> between "we find your problems" and "we track them to closed" — which is what this journey
> sells.

⬜ What does not exist is `OP-08`: the campaign wrapper — picking a slice of the backlog as a
piece of work, tracking it as one thing, and reporting the campaign rather than the ledger. Today
that is done by working the backlog, which is ordered for exactly this and is genuinely usable,
but it is a list rather than a plan.

⚠️ **A human signs off, always.** The platform compiles evidence and drafts wording and stops.
"Conformant to target" is not a status the platform can set.

---

## J7 — Keep building an onboarded app accessibly ⬜

*Brownfield · "build it with WCAG" · `OP-09` — not built*

The intention: new features on an imported application held to the same standard as a new
project, with pre-existing debt tracked separately so old problems do not block unrelated new
work.

**Half of the foundation is already true and worth saying:** greenfield and brownfield share one
findings ledger, one criterion registry, one review queue and one conformance statement, and
inherited debt already does not block (J5.7). What is missing is the separation in reporting —
"new work" and "legacy debt" are one list today — and any gate on new pull requests, which is
J3's missing piece.

---

## J8 — Test keyboard and interaction journeys with an agent ✅

*Greenfield and brownfield · gap G6, built 19–20 August*

**What it delivers:** the eight criteria that cannot be answered by reading a page standing
still, because each one is a question about what happens *while you operate the application*.

> ⚠️ **The ✅ here means built and tested. This has never opened a page in a real browser.**
> Every acceptance criterion below is green against a deliberately planted trap in the test
> suite, and **zero journey runs exist in any project.** Five live audits did not touch it —
> they read pages standing still, which is the one thing this journey exists because you cannot
> do. It is the least-proven part of the whole build, by a distance.

1. ✅ **The QA Lead points it at a journey**, from the Keyboard journeys panel on Pages & audit.
   A journey is a test case describing a complete path through the application — so the panel is
   there whether or not any pages are registered, because a journey follows a test case and not
   the page list.
   > ⚠️ **Until 20 August this could not be started at all.** `start_journey_check` had no caller
   > anywhere in the platform, no browser grant and no address. That was gap G6, in three parts:
   > **G6a** gave it an address, a browser bound to exactly that origin, and a walk that closes
   > itself rather than reading *walking* for ever; **G6b** let several run at once by giving each
   > its own hidden work item; **G6c** built the panel a person presses.
2. ✅ **The user starts the application and gives the address** — pre-filled from the last audit,
   else from the repository. The platform never starts an application, and the panel says so
   before the button rather than after: a walk against an address nothing answers on stops
   immediately and records no steps.
3. ✅ **The agent operates the application with the keyboard**, one step at a time, and reports
   against eight criteria: can everything be reached and operated (2.1.1), can you always get
   back out (2.1.2), does tab order preserve meaning (2.4.3), is the focus indicator actually
   drawn (2.4.7), is focus hidden behind sticky UI (2.4.11), does anything change unexpectedly on
   focus (3.2.1) or on input (3.2.2), and is a status message announced (4.1.3).
4. ✅ **What it cannot walk is named, with its reason**, and so is anything the cap of ten left
   out. A step nobody reported comes back as *not reached* rather than as a pass — the step list
   is frozen when the walk starts, and what is missing is subtracted at the end.
5. ✅ **Its findings flow into the same loop as everything else** — same review queue, same one
   ticket per problem — and **never block a gate**. Advisory is keyed on the *checker*, not on the
   source, so a proven keyboard-trap check could be promoted later without dragging seven newer
   checks in with it. That was the point of one checker per criterion.
6. ✅ **This panel is the only place a walk can be watched.** The journey's work item is hidden
   plumbing, so Phases & Runs cannot show it. The panel polls while anything is in flight and
   tells apart *waiting for a machine* from *walking now* — the audit strip above it has drawn
   that distinction since task 8a, and as of 20 August so does this.

**Where:** Accessibility → Pages & audit → Keyboard journeys.

---

## J9 — Human review and a signed conformance statement ✅

*Greenfield and brownfield*

**What it delivers:** a person keeps the checks honest, and produces a statement they have signed
— with the platform never claiming compliance on its own.

> ⚠️ **Half proven, and the halves are worth separating** (21 August).
>
> ✅ **The statement drafts itself correctly from a real audit.** Checked against the live
> Meridian data: it names which audit it was drawn from and when, lists all 55 criteria with 21
> genuinely evaluated from real evidence and 34 as *not evaluated*, and **refuses to export while
> unsigned**, saying so in its own words.
>
> ⬜ **Nobody has ever signed one**, so step 4 below — signing, the export it unlocks, and a
> statement being marked *stale* when new evidence arrives — rests entirely on tests.
>
> ⬜ **And the review queue in step 1 has been empty on all five runs.** Every check was
> confident enough to answer on its own. So the queue, the 15-minute claim, the "someone else has
> this open" message and confirm-raises-a-defect have **never met a real finding**. Filling it
> deliberately needs a genuinely *ambiguous* page, not a broken one — ambiguity is what makes a
> check say "I am not sure".

1. ✅ **The unsure findings land in the review queue.** Each shows the criterion in plain words,
   the element's markup and the text around it, and **the whole page with the element ringed** —
   not the element alone, because you cannot judge whether an alt text is meaningful without
   seeing what the image is doing on the page. On greenfield it also says which test case found
   it, and links to it (gap G3).
   > Opening an item claims it for 15 minutes and holding it open renews the claim; close the tab
   > and it lapses by itself. Someone else already on an item is told so by name rather than being
   > allowed to collide.
   > ⚠️ **An empty queue says nothing about how accessible the application is** — it holds only
   > what a check could not settle. And as of 20 August a project where nothing has ever run gets
   > a different sentence from one where every check was sure enough to answer on its own, because
   > telling the first reader the second thing was reassurance they had not earned.
2. ✅ **The decision sticks.** It holds until the element itself changes; the same element judged
   again does not come back. Confirming raises a defect, rejecting records that this is fine, with
   the reviewer's note.
3. ✅ **The statement lists all 55 criteria** — including the ones nothing looked at, printed as
   **not evaluated** and never folded into a supporting result. A project with no evidence at all
   correctly shows 55 not evaluated. The platform drafts the wording; the reviewer edits and
   signs; **any edit clears the signature**, because a signature on wording nobody signed is worse
   than none.
4. ✅ **Signing is the gate**, and it is what unlocks export and registers the statement as an
   approved artifact. New evidence afterwards marks it **stale** rather than clearing it, and
   export is blocked with that as its reason.
   > ⚠️ **Correction to the first version.** It said the export carries "which AI model and prompt
   > produced each finding". It does not, deliberately (D9): the engine, model, prompt and scanner
   > versions are recorded on the **signature's audit entry**, where a statement can still be
   > traced back to what produced it, but they are our implementation detail and not a client's
   > business. What the client's document does carry is the scanner's version — including
   > `(companion)` when the scan used ours rather than the application's own.

**Where:** Accessibility → Review queue, then Conformance statement.

---

## What is actually covered, and what is not

The number to quote is **27 of 55**, not 33 and not 55.

| Checker | Criteria it can speak to today | The registry classifies |
|---|---|---|
| Rule scanner (axe) | **14** | 14 as rule-owned |
| AI checks — six of them, built | **6** (1.1.1, 1.3.1, 1.4.1, 1.4.11, 2.5.3, 4.1.2) | 11 as AI-owned; the other six are Phase 2 |
| Keyboard journey | **8** (2.1.1, 2.1.2, 2.4.3, 2.4.7, 2.4.11, 3.2.1, 3.2.2, 4.1.3) | 8 |

**The total is still 27**, because 1.4.11 sits in two rows: it is a criterion in two halves, the
rule scanner measures the control edges and the `graphics` checker judges the icons, and one
criterion counted once either way. What changed is that the judged half is now built — the six
checkers are `alt`, `semantics`, `structure`, `color`, `label` and `graphics`, `structure` and
`semantics` sharing 1.3.1. The registry file still records 1.4.11 as rule-owned; routing gives it
to the AI. See `WCAG_COVERAGE_REFERENCE.md` §1.

**28 criteria have no automated evidence today**: five AI-owned ones whose checker is not built,
and **23 that only a person can ever assess** — nothing can tell you whether a video's captions
are *accurate* or whether an error message is *helpful*. The platform prints those as *not
evaluated* rather than pretending otherwise, and a test pins these numbers so the next person to
change either list has to restate them rather than leave a stale figure in a proposal.

---

## How the journeys map to the four things we sell

| We say | Journeys | Can we do it today |
|---|---|---|
| Start a new project and keep it accessible | J1 → J2 → J3 → J4 → J8 → J9 | **Partly.** J4, J8 and J9 are built; J2 is a reviewed checklist at the design gate with no automated design check behind it, and J3 is not built, so automated accessibility evidence starts at Test Automation |
| Onboard an existing app and test it for WCAG | J1 → J5 | **Yes**, with the pages registered by a person rather than discovered by onboarding |
| Onboard an existing app and remediate it | J5 → J6 → J9 | **Yes as a loop**, no as a campaign |
| Onboard an existing app and keep building it accessibly | J5 → J7 | **No.** J7 needs J3 |

---

## Which plan delivers which journey

- **`BUILD_PLAN_QA.md` / `TASK_BACKLOG_QA.md`** — J1, J4, the J5 **audit**, J8, J9, plus the
  `a11yai` capability and Edvensoft's internal accuracy work. All 31 tasks built.
- **`GAP_FIX_BUILD_PLAN.md`** — the **eleven** fixes that made those tasks *reachable*: a screen
  to register pages and run an audit, a caller for the keyboard journey, a truthful greenfield
  capture, and the plumbing kept off the user's board. All eleven built, 19–20 August. **Plus §9,
  which nobody planned for:** thirty-five more findings across twenty-four sections (§9.1–§9.23),
  all built — and §9 has kept growing: **§9.24–§9.28** are the 25 and 31 August and 1 September
  findings, also all built, and **§9.29** is the 1 September re-reading of every fix made since
  12 August, which built nothing and is a review.
  Seventeen were produced by a person watching the product work on 20–21 August rather
  than by reading code; ten more came on 24 August from the opposite direction, when the team
  asked whether we capture every element WCAG puts in scope. §9 is now the larger half of that
  document.
- **`BUILD_PLAN_OTHER_PHASES.md` / `TASK_BACKLOG_OTHER_PHASES.md`** — J2, J3, the J5 **onboarding
  posture step**, J6's campaign, J7. **None of the nine tasks is built.**

---

## Guardrails carried through every journey

- **Never over-claim.** The product finds and helps fix problems; it does not certify compliance.
  Only a person signs a conformance statement, and the platform will not mark anything conformant
  on its own.
- **A criterion nobody looked at must never look like a criterion that passed.** This is the one
  idea everything traces back to, and it applies to the screens as much as to the reports: a
  screen that failed to load now says so instead of showing an empty state.
- **The target standard is set per project**, default WCAG 2.2 AA. Accessibility law varies by
  country and almost all of it references WCAG, so the engine is portable; which legal document
  you produce — a US-style VPAT, an EU accessibility statement — is a reporting choice.
- **Everything rides the platform's existing rules:** capabilities rather than vendors, gates in
  the control plane, tenant isolation on every table, no direct model call anywhere, and the
  engine and prompt version recorded on every finding without being shown to the tenant.
