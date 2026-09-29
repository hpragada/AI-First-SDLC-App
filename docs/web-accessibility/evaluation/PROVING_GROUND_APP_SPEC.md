# A11y Proving Ground — application spec

**Doc A of two.** This is the *fixture application*: a small web app that is wrong in known,
deliberate ways. Doc B (`GOLDEN_DATASET_SPEC.md`) is the answer key over it.

**Status (updated 2026-09-17): BUILT** — the fixture exists as Meridian Library and has been audited
repeatedly; the answer key over it is in `golden/` (see `GOLDEN_DATASET_SPEC.md`). · **Audience:**
whoever builds or extends the fixture · **Internal to Edvensoft**

> ⚠️ **The checker names used throughout this spec are the old spelling.** `meaningful-alt` is
> **`alt`**, `fake-semantics` is **`semantics`**, `colour-only` is **`color`**; `label` is
> unchanged; and two more shipped later — **`structure`** and **`graphics`**, six in all. The
> tables below are left in the original spelling as the record of what was specified; take live
> names from `backend/apps/a11y/checkers/rules.py`.

---

## 1. What this is, and what it is not

**It is** a hand-written web application whose accessibility defects are planted on purpose, each
one paired with a correct twin, so that when the platform's accessibility engine reports a finding
we already know whether it was right.

**It is not** a project the platform builds. That distinction is the entire point. If the agents
generate the app *and* judge it, a clean report proves nothing — you cannot separate "the app is
accessible" from "the checker is blind". Ground truth has to come from outside the system under
test. **A human writes every line of this app.**

**It is not** a product, and no tenant ever sees it.

### It has two jobs

| Job | What it means |
|---|---|
| **Measurement** | The engine's findings are scored against a known answer key (Doc B). This is why the app exists. |
| **Demonstration** | It is the app shown to clients when demonstrating the accessibility capability. |

Those two jobs pull in the same direction more than they look like they do — but only if the demo
story is the right one. See §6.

### What it unblocks

| Milestone | What the Proving Ground gives it |
|---|---|
| **M0 / M1** (POC) | The only target that exists on day one. The SDLC fixture projects must be fully built and running before 09b can scan them — days of phase runs away. This app runs now. |
| **M2** (brownfield audit) | An app that genuinely was never built through the pipeline — onboard it, register its routes, get a baseline. Exactly J5's shape. |
| **M3** (agentic keyboard testing) | Planted interaction defects: traps, focus-return failures, obscured focus, scrambled tab order. |
| **M4** (governance) | A conformance picture whose correct answer is known, so a draft VPAT can be checked rather than admired. |

---

## 2. Design principles

These matter more than the page content. Get one wrong and the dataset built on top is worthless.

**1 · Server-rendered only. No client-side framework.**
Every route returns complete HTML from the server. Your expert has to be *certain* what the browser
produced, because their label is the ground truth everything else is scored against — and a
client-rendered app is blank until hydration, so a capture taken a moment too early records nothing
while the label says otherwise. Server rendering removes that whole class of problem. Vanilla JS is
used only for the interaction pages in §10.

**2 · Matched pairs.**
Every defective page has a visually near-identical correct twin. Without pass cases, a checker that
flags everything scores perfect recall — and QA-10 reports precision and F1, so the pass cases carry
half the measurement.

**3 · One planted defect per page.**
If a page carries five defects and the judge finds three, you cannot attribute the two misses.
Isolation is what makes per-criterion numbers mean anything. The exception is §9's completeness
pages, which exist precisely to carry many.

**4 · Nothing in the app may reveal the answer — including the URL.**
No comment, no class name like `.planted-fail`, no data attribute, and **no route name that
describes its defect**. A URL is visible in the browser, in the screenshots the vision model is
given, and on screen during a client demo. Matched pairs must not be adjacent in name either — an
`-a` / `-b` suffix announces the pairing. Every route below reads like a page a real library would
have. The mapping from route to planted defect lives **only** in the golden dataset.

**5 · It must look like a real app.**
Realistic content, plausible layout, a working nav, actual visual polish. Three reasons: a judge
that can tell "this is a test page" may behave differently than it will in production, M2 needs
something that reads as a genuine brownfield app, and a client is going to be looking at it. No page
may contain the words *test*, *fixture*, *fail*, *pass*, or a criterion number in visible copy.

**6 · Include the hard cases, not just the textbook ones.**
`alt="IMG_1234"` is the acceptance criterion in QA-03, not a real test. The valuable samples are the
ones where a thoughtful person hesitates — see §8.

**7 · Nothing self-healing.**
No accessibility overlay, no runtime ARIA patching, no `axe` running inside the app. The app must
not improve itself between the author writing it and the judge seeing it.

---

## 3. The application

**Product name shown in the UI:** Meridian Library
**Repository:** `edvensoft/a11y-proving-ground`
**Domain:** a small community library — book catalogue, loans, member account, staff admin.

Chosen because it produces all five POC criteria naturally, without contrivance: book covers and
author portraits (1.1.1), loan-status badges (1.4.1), search and membership forms (2.5.3), custom
staff controls and a fake tab strip (4.1.2), and a results layout begging to be built out of divs
(1.3.1).

### Stack

```
Runtime:        Node.js 22 LTS
Server:         Express 4
Templates:      EJS — server-rendered, one view per route, shared layout + partials
Client JS:      vanilla ES2022, only on the §10 interaction pages. No framework. No bundler.
Styling:        hand-written CSS, one stylesheet
Data:           a seeded JSON file. No database
Build step:     none. `npm start` and it serves
Tests:          none in this repo — this app is the subject, not the tester
```

**Why this stack.** It is a real, nameable one — *"a Node and Express app"* — so it stands up in a
demo. Every route is a genuine server URL, which `routes.json` and the M2 route list depend on. And
there is **no build step**, which matters more than it sounds: the companion's `preview_start` has to
bring this up reliably on every single run, and a build is one more thing that can fail between the
author's intent and the judge's input.

EJS gives you layout and partial reuse, so the repo reads like a real codebase to code-intel when
you onboard it for M2 — while the rendered DOM stays exactly what the template says.

### Where it lives — a separate repository

The Proving Ground is its **own repository**, not a directory in the SDLC platform repo:

- **M2 requires it.** J5 onboards an existing app that never went through the pipeline. There has to
  be a real repository to onboard.
- **It needs its own commit history** (§12) — code-intel reads the repository, and a one-commit repo
  looks like exactly what it is.
- **Deployment is trivial standalone**, awkward otherwise.

| Thing | Where |
|---|---|
| The app | `edvensoft/a11y-proving-ground` — its own repo |
| The golden dataset | **Stays** in the SDLC repo at `docs/web-accessibility/evaluation/golden/` — QA-09 wants it in Edvensoft's own repo, and QA-10a's `make a11y-eval` harness lives there |

### Deploying it — and yes, the platform can scan a deployed URL

You will want a deployed URL so the WCAG expert can review by hand and so the app can be shown
without a laptop. **A deployed instance can be scanned by the platform**, through a supported path:

Set the repo's **Preview URL** (`Repository.preview_url`, editable on the Repositories screen). When
it is non-empty the companion **skips auto-start entirely**, probes the URL once so a stopped app
fails loud, and points Playwright at it — the code comment names this case exactly: *"the user keeps
a dev server / staging up, so use it directly and start nothing"*
(`backend/apps/projects/preview_config.py:43`, `runner/companion/runner.py:342`). Playwright MCP is
then launched with `--allowed-origins <preview_url>`, scoping the browser to that host
(`runner/companion/runner.py:194`). The egress allowlist does not block it — `check_command_egress`
runs only on the auto-start branch, which this path returns before reaching.

**What correction R2 actually constrains** is the *platform server*, not the browser. Judgment,
triage, findings and gates live server-side and cannot reach your app; the browser lives in the
companion on a developer's machine, and that machine has internet access like any other.
`PreviewEnv.Provider = companion_local` describes who **provisions** the preview environment, not
which URLs the browser may visit.

**But still scan locally for the golden dataset.** Doc B pins every label to an `app_version` and
requires byte-identical HTML for the same URL. A shared deployment can be redeployed, cached or
changed underneath you between labelling and scoring, and the harness would then be measuring
something other than what was labelled. Use them for different jobs:

| Purpose | Where it runs |
|---|---|
| Client demo, expert's manual review, M2 brownfield audit | **Deployed URL** via `preview_url` |
| Accuracy scoring against the golden dataset | **Local**, started by `preview_start` at a pinned app version |

**Two practical cautions.**

*Do not put HTTP auth in front of it if you intend to scan it.* Playwright will hit the auth wall
and see a login page instead of your app. Use an unlisted hostname plus `X-Robots-Tag: noindex`
rather than a password — or keep the auth and scan locally. An application full of planted WCAG
failures, publicly indexed under your organisation's name, is a bad thing for a client or auditor to
find while you are selling accessibility services.

*Keep the app self-contained.* `--allowed-origins` scopes the browser to the preview host, so
anything loaded from another origin — CDN fonts, hosted scripts, remote images — may be blocked, and
a page that renders differently under scan than in your expert's browser breaks the labels. Serve
every asset from the app itself. §2 principle 7 already wants this for other reasons.

### How the companion runs it

Register the repo with this `preview_start` config:

```json
{
  "command": "npm start",
  "port": 4180,
  "health_path": "/health",
  "ready_timeout_s": 60,
  "ready_log": "Meridian Library listening on"
}
```

`/health` returns `200 {"status":"ok"}` and is excluded from every route list and every scan.

Requirements on the server: deterministic output (no randomised content, no timestamps in the DOM,
no A/B behaviour) and no outbound network calls. **The same URL must produce byte-identical HTML on
every run** — otherwise a candidate's screenshot hash changes, the QA-02 cache misses, and labels
drift away from what the judge actually saw.

### Repository layout

```
a11y-proving-ground/
  package.json
  server.js                 Express app: routes, static assets, /health
  routes/                   one router per section (catalogue, loans, account, staff, …)
  views/
    layout.ejs              shared shell — header, nav, footer
    partials/               book card, status badge, form field, …
    catalogue/ loans/ account/ staff/ help/ about/ events/ reports/
  public/
    styles.css
    js/                     vanilla JS, only for the §10 interaction pages
    assets/                 images
  data/seed.json            books, members, loans — fixed, never randomised
  routes.json               THE ROUTE LIST (§5) — hand-maintained
  README.md                 see §11 — contains a deliberately false claim
  CONTRIBUTING.md           "never fix a planted defect" — see §12
```

> **No answer key anywhere in this repository.** Not in a template, not in a comment, not in a class
> name, not in a route. The judge sees the rendered page; a leaked hint invalidates every number the
> dataset produces. Labels live only in the golden dataset (Doc B).

---

## 4. Coverage — the five POC criteria

Per correction R7 / decision D5, the POC judges **five** criteria (2.4.6 moved to Phase 2):

| Criterion | Checker | What the AI is judging |
|---|---|---|
| **1.1.1** Non-text Content | meaningful-alt | Is the alt text actually useful? |
| **1.3.1** Info and Relationships | fake-semantics | Is structure conveyed programmatically, or only visually? |
| **4.1.2** Name, Role, Value | fake-semantics | Is this control exposed as the control it appears to be? |
| **1.4.1** Use of Colour | colour-only | Is meaning carried by colour with no backup? |
| **2.5.3** Label in Name | label | Does the accessible name contain the visible label? |

Phase-2 criteria get pages too, marked as such in the dataset, but no labels until their checkers
exist.

---

## 5. The route list

Correction R5 established that no route registry exists in the platform, and QA-17 must be built
against a hand-provided list until OP-06 lands. This app therefore ships one, at `routes.json`:

```json
{
  "version": "1.1.0",
  "base_url": "http://localhost:4180",
  "routes": [
    { "path": "/",                      "title": "Home",            "in_scope": true },
    { "path": "/catalogue/new-arrivals","title": "New arrivals",    "in_scope": true },
    { "path": "/catalogue/staff-picks", "title": "Staff picks",     "in_scope": true },
    { "path": "/health",                "title": "Health",          "in_scope": false }
  ]
}
```

Rules: every rendered route appears exactly once; `in_scope: false` only for `/health`; the file is
updated **in the same commit** as any route addition or removal. A route that renders but is missing
from `routes.json` is a bug in the fixture, and QA-17's coverage numbers will be quietly wrong.

The way to hold that rule is not discipline: the app keeps its routes in one declarative table and
generates `routes.json` from it, so the manifest cannot disagree with what the server serves.

> `routes.json` carries **titles only, never verdicts.** It ships in the app repo, so anything in it
> is visible to the judge.

---

## 6. The demo path

The app is also what you show clients. The demo story is **not** "look at the app we built" — it is
deliberately broken, and pretending otherwise would be strange. The story is:

> Here is an ordinary-looking library application. Watch the platform find its accessibility
> problems, cite the WCAG rule each one breaks, open tracked defects for the real ones, send the
> uncertain ones to a human, and hold the release gate until they are fixed.

That is a stronger demo than a clean app, because a clean app proves nothing — the audience cannot
see what was caught. And because you know the planted answers, you can make a claim nobody else in
the room can: *"it found 18 of the 20 problems we planted, and correctly flagged 2 more as needing a
human."*

### A ten-minute script — five pages, in this order

| # | Route | What it shows | Why it lands |
|---|---|---|---|
| 1 | `/about/opening-hours` | axe catches text at 3.1:1 contrast | Start with something a free tool also finds. Sets the baseline honestly. |
| 2 | `/catalogue/new-arrivals` | Six book covers, every one `alt="cover"` | **The moment.** axe reports zero violations — the attribute is present and non-empty, so the rule is satisfied. The AI flags all six. This is the gap the product exists to fill, and it is visible in ten seconds. |
| 3 | `/catalogue/staff-picks` | The same page done properly | The tool stays quiet. Showing it *not* firing is what makes everything else credible. |
| 4 | `/about/visit-us` | An ambiguous image — decorative or informative? | Returns `uncertain` and routes to the SME queue instead of guessing. Demonstrates the product knows what it does not know, which is the thing buyers of compliance tooling actually worry about. |
| 5 | `/gates` in the platform | The accessibility gate blocking on a confirmed critical | Closes the loop: a finding is not a report, it is a thing that stops a release. |

Keep pages 2 and 3 adjacent. The contrast between "axe passes, we don't" and "we stay quiet when
it's right" is the whole pitch, and it takes ninety seconds.

**Build the demo path first.** Those four app pages plus §7's rule pages are about twelve pages —
enough to demo and enough to test M1, long before the full set exists.

---

## 7. Page catalogue — the rule half (axe-detectable)

These verify the *other* half of the engine: 09b generating `@axe-core/playwright` assertions
(QA-11a), JUnit flowing into the defect loop, and QA-14's de-duplication, which must not report the
same problem twice when both axe and the AI see it.

| Route | Planted defect | axe rule |
|---|---|---|
| `/catalogue/recommended` | `<img>` with no `alt` attribute at all | `image-alt` |
| `/about/opening-hours` | Body text at 3.1:1 on its background | `color-contrast` |
| `/contact` | `<input>` with no label, no `aria-label`, no `title` | `label` |
| `/about/membership` | `<html>` with no `lang` | `html-has-lang` |
| `/events/calendar` | A link whose only content is an image with an empty `alt` | `link-name` |
| `/catalogue/reserve` | `<button></button>` with a CSS background icon | `button-name` |
| `/about/history` | **Control page — zero axe violations** | — |
| `/events/tickets` | A 20×20 tap target, below the 24×24 minimum | `target-size` *(the WCAG 2.2 canary)* |

**The last two rows are instrumentation, and they matter more than the rest.** `/about/history`
catches the scan **over**-reporting: violations there mean the configuration is wrong and every
other number that day is suspect. `/events/tickets` catches it **under**-reporting: `target-size` is
tagged `wcag22aa`, so if that page comes back clean the WCAG 2.2 ruleset is not running at all and
every 2.2 result is a false pass.

> **Two things about axe that QA-11a needs to know before it configures a scan.** Both were found by
> running the fixture, and both produce a report that looks complete while being silently narrower
> than intended.
>
> **`label-content-name-mismatch` (2.5.3) does not run under a tag filter.** It is not disabled — it
> carries axe's `experimental` tag, and axe leaves experimental rules out of a tag-selected run. A
> scan configured with tags alone reports every page clean on 2.5.3, with no warning and no gap in
> the output. Name it in `rules` to include it, or add `experimental` to the tag list and accept the
> seven other experimental rules that come with it.
>
> **`target-size` (2.5.8) looks like the same case and is not.** It ships `enabled: false`, but a
> tag-based `runOnly` runs it anyway: the `enabled` flag governs only what axe does when given no
> instructions. Select `wcag22aa` and the rule fires. Measured on axe-core 4.13.0, not reasoned.
>
> **`AxeBuilder.options()` overwrites the builder's options rather than merging.** So
> `.withTags(tags).options({ rules })` silently discards the tag filter and runs every rule axe has,
> best-practice included. The two settings have to go in a single `options()` call.
>
> A third, smaller one: axe returns some rules as **`incomplete`** rather than as violations when it
> cannot decide automatically. Whatever consumes the results should decide what happens to those
> rather than reading `violations` and letting the rest fall on the floor.

> **Do not expect axe to catch 2.4.11.** Whether a sticky header covers the focused element depends
> on scroll position and live layout, so it is not statically decidable and axe has no rule for it.
> `/catalogue/all-titles` (§10) is caught by the M3 agent, not the scanner. axe's real WCAG 2.2
> coverage is much narrower than the criteria list implies — the build guide shows how to enumerate
> what you actually get.

### The seam between the two engines

| Route | Content | Expected |
|---|---|---|
| `/reports/lending-summary` | An informative chart with `alt=""` | axe: **clean** (empty alt is legal). AI: **fail** on 1.1.1 |
| `/about/team` | A genuinely decorative divider with `alt=""` | axe: clean. AI: **pass** — empty alt is correct here |

Together these test that the AI adds judgment where the rules stop, without firing on the case where
the rules' silence was right.

---

## 8. Page catalogue — the AI half

For each criterion: clear fails, clear passes, and **ambiguous** cases where a careful expert says
"either reading is defensible". The ambiguous pages are the most valuable in the app — Doc B §4
explains why the expected verdict there is `uncertain`, not a coin-flip guess.

### 1.1.1 — meaningful alt

| Route | Content | Expected |
|---|---|---|
| `/catalogue/new-arrivals` | 6 book covers, each `alt="cover"` | **fail** |
| `/catalogue/staff-picks` | Same 6 covers, alt = title + author + what the cover shows | **pass** |
| `/authors/featured` | Author photo, `alt="IMG_2231.jpg"` | **fail** |
| `/authors/spotlight` | Same photo, `alt="Ursula Vane, photographed at the 2019 festival"` | **pass** |
| `/reports/borrowing-trends` | Loans-by-month chart, `alt="chart"` | **fail** |
| `/reports/annual-review` | Same chart, alt summarising the trend; long description linked | **pass** |
| `/events/summer-reading` | Purely decorative rule, `alt="decorative divider line"` | **fail** (noise) |
| `/events/book-club` | Same rule, `alt=""` + `role="presentation"` | **pass** |
| `/catalogue/award-winners` | Cover with full-title alt, **immediately adjacent** to the same title as text | **uncertain** — redundancy is a real harm, but so is an unnamed cover |
| `/about/visit-us` | Photo of the library interior in a "Visit us" panel, `alt="library"` | **uncertain** — arguably decorative, arguably informative |

```html
<!-- views/catalogue/new-arrivals.ejs — the defect axe cannot see -->
<img src="/assets/covers/tidewater.svg" alt="cover">

<!-- views/catalogue/staff-picks.ejs — its twin -->
<img src="/assets/covers/tidewater.svg"
     alt="Tidewater by Ursula Vane — cover showing a flooded harbour at dusk">
```

Both pass axe. Only judgment separates them.

### 1.3.1 — info and relationships

| Route | Content | Expected |
|---|---|---|
| `/help/borrowing-guide` | Section titles styled as headings with `<div class="h2">` | **fail** |
| `/help/getting-started` | Same visual result using `<h2>` | **pass** |
| `/account/loan-history` | Loan history laid out with divs and CSS grid, visually a table | **fail** |
| `/account/statements` | Same data in `<table>` with `<th scope>` | **pass** |
| `/account/notifications` | Three radios visually grouped under "Notify me by", no fieldset | **fail** |
| `/account/preferences` | Same, wrapped in `<fieldset><legend>` | **pass** |
| `/catalogue/genres` | A genre shown in bold, where boldness may or may not carry meaning | **uncertain** |

### 4.1.2 — name, role, value

| Route | Content | Expected |
|---|---|---|
| `/staff/catalogue-entry` | `<div class="btn" onclick="…">Save</div>` | **fail** |
| `/staff/quick-edit` | `<button type="button">Save</button>` | **pass** |
| `/staff/branch-settings` | Custom switch, state shown only by CSS position | **fail** |
| `/staff/display-options` | Same switch with `role="switch"` + `aria-checked` | **pass** |
| `/staff/reports` | Tab strip built from `<a href="#">`, no tab roles | **fail** |
| `/staff/overview` | Same strip with `role="tablist"` / `tab` / `tabpanel` | **pass** |
| `/staff/exports` | A genuine navigation styled as a button | **uncertain** — appearance suggests button, behaviour is correctly a link |

### 1.4.1 — use of colour

| Route | Content | Expected |
|---|---|---|
| `/loans/current` | Loan rows tinted red / amber / green; legend is colour swatches only | **fail** |
| `/loans/history` | Same rows, each carrying a text badge "Overdue" / "Due soon" / "On loan" | **pass** |
| `/account/join` | Required fields marked only by a red label | **fail** |
| `/account/update-details` | Required fields marked "(required)" with `aria-required` | **pass** |
| `/reports/branch-comparison` | Stacked chart, series distinguished by colour only | **fail** |
| `/reports/monthly-issues` | Same chart with direct labels and distinct patterns | **pass** |
| `/loans/renewals` | Colour **plus** an icon that is not self-explanatory (a dot vs a ring) | **uncertain** — a backup exists, but is it perceivable? |

### 2.5.3 — label in name

| Route | Content | Expected |
|---|---|---|
| `/catalogue/search` | Button reads "Search", `aria-label="Find books"` | **fail** |
| `/catalogue/advanced-search` | Button reads "Search", `aria-label="Search books"` | **pass** |
| `/account/apply` | Button reads "Join", `aria-label="Submit membership application"` | **fail** |
| `/account/register` | Button reads "Join", accessible name "Join the library" | **pass** |
| `/newsletter` | Field with placeholder "Email" as its only label | **fail** (also 1.3.1 — labelled for 2.5.3) |
| `/account/my-loans` | Icon button, visible "Renew", accessible name "Renew all loans" | **uncertain** — contains the label, but adds scope the user did not say |

---

## 9. Completeness pages — a separate, cheaper check

Correction R4 names silent under-reporting as *"the worst possible failure"* for a compliance
feature, and puts a write-completeness check in the first version: if 40 candidates go in and 31
findings come back, the run must fail loudly.

That is a different failure mode from being wrong, and it deserves pages with an **exactly known
candidate count**:

| Route | Contains | Expected candidates |
|---|---|---|
| `/catalogue/browse-all` | Exactly 12 `<img>`, mixed alt quality | 12 for meaningful-alt |
| `/staff/bulk-actions` | Exactly 20 interactive controls | 20 for fake-semantics |
| `/account/full-profile` | Exactly 15 labelled form controls | 15 for label |
| `/branches` | Exactly 8 colour-coded indicators | 8 for colour-only |
| `/about/terms` | Text only — **no** candidates of any kind | 0, and a clean no-op rather than an error (QA-12 edge case) |

Deterministic, runs in seconds, needs no labels, and stable across model changes — so it can gate
every commit while accuracy numbers move slowly.

> Keep the counts odd and specific (12, 20, 15, 8) rather than round. A run reporting "10 findings"
> against a 12-candidate page is obviously wrong; against a 10-candidate page it looks fine.

---

## 10. M3 — keyboard and interaction journeys

J8's agent *operates* the app, so these need real behaviour, not markup. Vanilla JS only. Each is a
short journey with one planted defect and a correct twin.

| Route | Planted defect | Criterion |
|---|---|---|
| `/events/book-a-room` | Date picker that captures Tab and never releases | 2.1.2 |
| `/events/book-a-seat` | Same picker, Escape closes and focus returns | 2.1.2 |
| `/catalogue/reserve-copy` | Dialog that does not return focus to its trigger on close | 2.4.3 |
| `/catalogue/place-hold` | Same dialog, focus returns correctly | 2.4.3 |
| `/catalogue/all-titles` | Focused row scrolls under a sticky header — focus ring hidden | **2.4.11** (2.2-only) |
| `/catalogue/by-subject` | Same page with scroll padding, ring stays visible | 2.4.11 |
| `/account/settings` | Positive `tabindex` values scrambling the sequence | 2.4.3 |
| `/account/security` | Natural DOM order | 2.4.3 |
| `/help/faq` | `outline: none` with no replacement indicator | 2.4.7 |
| `/help/contact-us` | Visible custom focus ring | 2.4.7 |
| `/catalogue/filter` | `<select>` that submits the form on change | 3.2.2 |
| `/catalogue/refine` | Same select with an explicit Apply button | 3.2.2 |
| `/catalogue/results` | "3 results found" injected with no live region | 4.1.3 |
| `/catalogue/quick-find` | Same message in `aria-live="polite"` | 4.1.3 |

**2.4.11 deserves a note.** It is new in WCAG 2.2 and the sticky-header case is its canonical form —
but **axe has no rule for it**, because whether a sticky region covers the focused element depends
on scroll position and live layout rather than markup. So `/catalogue/all-titles` is silent under the
scanner by design, and the M3 agent is the only thing that can catch it. That makes it the clearest
single argument for building M3 at all: a defect a scanner structurally cannot see, that a user hits
immediately.

Proof that the WCAG **2.2 ruleset** is running lives elsewhere — the `/events/tickets` canary in §7.

---

## 11. M2 — making it a credible brownfield subject

J5 onboards an existing app and records its **accessibility posture**: does it have an accessibility
spec, what WCAG level does it claim, does the rule scanner currently pass? For that step to be
testable, this app needs a posture worth recording — and worth catching.

**Plant a false conformance claim** in `README.md`:

```markdown
## Accessibility

Meridian Library conforms to WCAG 2.1 Level AA. Last audited March 2024.
```

Untrue — the app is full of planted failures. It is exactly the situation a real brownfield audit
walks into. J5's posture check should record the claim, and the baseline should contradict it. If
onboarding records "claims 2.1 AA" and the audit never flags the contradiction, that is a finding
about the platform.

Note the claim sits in the README, not in the UI, so a deployment does not publish it.

Deliberately absent, so onboarding's gap detection has something to find:

- no `accessibility` artifact of any kind
- no design-phase history — this app never went through a design phase, which is J5's premise
- no automated accessibility tests in the repo

The repo should carry **real commit history** — a dozen or so plausible commits over time, not a
single "initial commit".

---

## 12. Rules for changing this app

The golden dataset labels *candidates captured from these pages*. Editing a page can silently
invalidate its labels — a changed DOM produces a different selector, a different screenshot hash, a
different cache key.

1. **Any change to a rendered view bumps the app version** in `package.json`.
2. **A change that alters a labelled element invalidates that label.** The dataset records the app
   version it was labelled against (Doc B §7); the harness refuses to score a dataset whose version
   does not match the running app.
3. **Never fix a planted defect.** If someone "tidies up" `/catalogue/new-arrivals`, the fixture is
   broken and the accuracy numbers become nonsense. `CONTRIBUTING.md` says so in its first paragraph.
4. **Adding a page is cheap; changing one is expensive.** Prefer a new route over editing an
   existing one.
5. `routes.json` changes in the same commit as any route addition or removal.
6. **Never rename a route to describe its defect**, however convenient. Principle 4 is not
   negotiable — the URL is visible to the model and to the client.

---

## 13. Build order

1. Server, layout, nav, `/health`, `routes.json`, README with the false claim, realistic commit
   history.
2. **The rule pages (§7).** Verify 09b and the defect loop end to end (QA-11a) before any AI work
   exists. `/about/history` proves the scan is configured correctly.
3. **The demo path (§6)** — four app pages. You can demo and test M1 from here.
4. **The completeness pages (§9).** Testable the moment QA-02a's write-completeness check exists,
   and they need no labels.
5. The remaining fail/pass pairs (§8) — the bulk of the work, and the input to Doc B.
6. The ambiguous pages. Author these **last and with the expert present** — they are the hardest to
   get right and the easiest to accidentally make unambiguous.
7. The interaction journeys (§10) — M3. Not needed until QA-20.

Steps 1–4 need no accessibility expertise and no labelling. Start there; they unblock M1 testing and
the client demo while the expert is still working through §8.

---

## Cross-references

- **What to actually write:** `PROVING_GROUND_BUILD_GUIDE.md` — exact markup per page, the verified
  colour palette, the axe configuration and acceptance procedure. Build from that; this document is
  the reasoning behind it.
- **The answer key over this app:** `GOLDEN_DATASET_SPEC.md` (Doc B).
- **Corrections that shaped this spec:** `../RESEARCH_CORRECTIONS.md` — R1 (no scan exists; 09b is the
  route), R2 (companion-local, localhost), R4 (judgment via ExecutionDriver; write-completeness),
  R5 (no route registry), R7 (five criteria, not six).
- **Task detail:** `../TASK_BACKLOG_QA.md` — QA-11a, QA-11b, QA-02a, QA-10a, QA-17.
- **Journeys served:** `../USER_JOURNEYS.md` — J4 (test), J5 (brownfield baseline), J8 (agentic), J9
  (conformance).
