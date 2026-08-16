# Meridian Library — build guide

**Companion to `PROVING_GROUND_APP_SPEC.md`.** The spec says *what* the fixture is and why. This
says *exactly what to write*. Build from this document; read the spec first for the reasoning.

**Repository:** `meridian-library-web-accessibility` · **Internal to Edvensoft**

---

## 0. Read this before writing a single line

### The defects in this document are the deliverable

You are building an application that is **deliberately wrong**. Every accessibility problem below is
there on purpose, and reproducing it exactly is the job.

You will feel the urge to fix them. A `<div>` with an `onclick` and no role looks like an oversight;
`alt="cover"` looks lazy; grey text at 3:1 looks like a mistake. **They are not mistakes.** If you
"improve" them, the fixture silently stops working: a scan finds nothing, and nobody can tell that
from a broken checker — which is the exact ambiguity this app exists to remove.

**Rules:**

1. Reproduce the markup in this guide **character for character** where it is given in a code block.
2. Do **not** add `role`, `aria-*`, `tabindex`, `alt`, `<label>`, or a `lang` attribute that this
   guide does not ask for.
3. Do **not** "round up" a colour to make it pass contrast.
4. Do **not** run a linter or formatter that rewrites HTML attributes.
5. If a page looks wrong to you, that is the point. If it looks wrong in a way this guide does
   **not** describe, that is a real bug — stop and raise it.

### The twins must be genuinely clean

Every broken page has a correct twin. A twin must be clean **on every criterion**, not just the one
it is paired on. An accidental contrast failure on a page that exists to be correct makes any
finding there ambiguous, which is as damaging as a missing defect.

---

## 1. Project setup

### `package.json`

```json
{
  "name": "meridian-library",
  "version": "1.0.0",
  "private": true,
  "type": "commonjs",
  "scripts": { "start": "node server.js" },
  "dependencies": { "express": "^4.19.2", "ejs": "^3.1.10" }
}
```

`version` is load-bearing. The golden dataset pins its labels to it — bump it on any change to a
rendered view (spec §12).

### `server.js`

```js
const express = require("express");
const path = require("path");

const app = express();
const PORT = process.env.PORT || 4180;

app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"));
app.use(express.static(path.join(__dirname, "public")));

app.get("/health", (_req, res) => res.json({ status: "ok" }));

require("./routes")(app);

app.use((_req, res) => res.status(404).render("not-found", { title: "Page not found" }));

app.listen(PORT, () => console.log(`Meridian Library listening on http://localhost:${PORT}`));
```

The startup line must read exactly `Meridian Library listening on` — the companion's
`preview_start.ready_log` matches on it.

### `views/layout.ejs`

Every page uses this except `/about/membership`, which needs a variant (§5.4).

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title><%= title %> · Meridian Library</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header class="site-head">
    <p class="brand">Meridian Library</p>
    <nav aria-label="Main">
      <ul>
        <li><a href="/catalogue">Catalogue</a></li>
        <li><a href="/loans/current">My loans</a></li>
        <li><a href="/events/calendar">Events</a></li>
        <li><a href="/help/faq">Help</a></li>
      </ul>
    </nav>
  </header>
  <main id="main">
    <h1><%= title %></h1>
    <%- body %>
  </main>
  <footer class="site-foot">
    <p>Meridian Library · 14 Fenner Road · Open Tuesday to Saturday</p>
  </footer>
</body>
</html>
```

The layout itself must be **flawless**. A defect here would appear on all 45 pages and contaminate
every label.

### `public/styles.css` — the palette

These values are computed, not estimated. Do not change them.

```css
:root {
  --bg: #ffffff;
  --ink: #1a1a1a;      /* 17.40:1 on white — body text */
  --muted: #757575;    /* 4.61:1 on white — PASSES AA for normal text */
  --faint: #929292;    /* 3.11:1 on white — FAILS AA. Deliberate. Only on /about/opening-hours */
  --link: #0b5fa5;     /* 6.57:1 on white */
  --tint-overdue:  #fdecea;   /* ink on this = 15.22:1 */
  --tint-due-soon: #fff8e1;   /* ink on this = 16.38:1 */
  --tint-on-loan:  #e8f5e9;   /* ink on this = 15.47:1 */
}
body { background: var(--bg); color: var(--ink); font: 16px/1.5 system-ui, sans-serif; }
a { color: var(--link); }
.muted { color: var(--muted); }
:focus-visible { outline: 3px solid var(--link); outline-offset: 2px; }
```

> **Why the status tints are so pale.** The colour-only pages (§8.4) must fail 1.4.1 and **nothing
> else**. If a tint dropped text contrast below 4.5:1, those pages would fail contrast too, axe would
> report it, and you could no longer tell which engine found what. Every tint above keeps text above
> 15:1. Verified, not guessed.

**No external resources.** No CDN fonts, no hosted scripts, no remote images. Playwright is launched
with `--allowed-origins` scoped to the preview host, so a cross-origin asset may be blocked — and a
page that renders differently under scan than in your expert's browser invalidates its labels.

---

## 2. Global rules

### Every labelled element needs a stable, neutral `id`

The golden dataset keys its labels on `(app_version, route, checker, selector)`. Positional
selectors break the moment anyone adds a row.

- **Required:** an explicit `id` on every element this guide plants a defect on, and on its twin.
- **Name it after the content, never the defect.** `id="cover-tidewater"` ✔ · `id="bad-alt-1"` ✘
- The twin uses the **same** id as its counterpart, on the corresponding element.

### Determinism

The same URL must return **byte-identical HTML** on every request. No timestamps in the DOM, no
random ordering, no request counters, no "last updated" values, no `Math.random()`. The screenshot
hash is part of the judgment cache key; drift means the label stops describing what was judged.

### Nothing may reveal the answer

Not in a comment, a class name, a data attribute, a route, or an `id`. The judge sees the rendered
page and the URL. Class names describe appearance (`.status-row`), never intent (`.planted-fail`).

---

## 3. Seed data — `data/seed.json`

Fixed forever. Six books, chosen so a correct `alt` is verifiable against something.

| id | Title | Author | The cover depicts |
|---|---|---|---|
| `tidewater` | Tidewater | Ursula Vane | A flooded harbour at dusk |
| `salt-path` | The Salt Path Home | Idris Okonkwo | A dirt road through wheat fields |
| `nightjar` | Nightjar | Marta Lindqvist | A single bird against a full moon |
| `cartographer` | The Cartographer's Apprentice | Hana Sato | A hand-drawn map with a compass rose |
| `bell-bone` | Bell and Bone | Cormac Deasy | A cracked church bell |
| `quiet-inventory` | A Quiet Inventory | Priya Raghunathan | Stacked cardboard boxes in an empty room |

**Cover images:** `public/assets/covers/<id>.jpg`, 400×600. Any fixed image is fine **provided it
actually depicts the description above** — the alt-text judgment is scored against whether the alt
conveys what the image shows, so a mismatch makes the label wrong.

Loans, for the status pages — fixed:

| Book | Due | Status |
|---|---|---|
| Tidewater | 2026-07-02 | overdue |
| Nightjar | 2026-08-19 | due soon |
| Bell and Bone | 2026-09-30 | on loan |

Dates are **hardcoded strings**, never computed from today. A computed date changes the DOM daily
and breaks every label on the page.

---

## 4. The acceptance check — build this second, before any content

Nothing else in this guide is trustworthy until you can prove what axe actually reports.

### `tools/verify.js`

Run axe over every route in `routes.json` and write a report. Use exactly this tag set:

```js
const tags = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const results = await new AxeBuilder({ page }).withTags(tags).analyze();
```

**The tag set is not optional.** Without it axe also runs best-practice rules (`region`,
`landmark-one-main`, `page-has-heading-one`) that are not WCAG A/AA. Those would fire on pages this
guide expects to be clean, and you would spend a day chasing a phantom.

**Confirm the WCAG 2.2 rules are actually live.** `@axe-core/playwright` pulls `axe-core` in
transitively, so the version that matters is the transitive one:

```bash
npm ls axe-core                                  # need 4.9+ for the wcag22aa tag
grep -c "wcag22aa" node_modules/axe-core/axe.js  # non-zero means rules carry the tag
node -e "const a=require('axe-core');console.log(a.version);console.log(a.getRules(['wcag22aa']).map(r=>r.ruleId).join(', '))"
```

Run the third one and read the list. **axe's WCAG 2.2 coverage is much smaller than the criteria
list suggests** — most 2.2 additions are not statically decidable, so axe does not attempt them.
Know which rules you actually get rather than assuming the tag buys you all of 2.2.

These commands tell you what is *installed*. They do not tell you your harness passes the tags
through correctly — a typo in the tag array fails silently and every page just looks clean. §5.9 is
the canary that catches that.

### The reconciliation rule

Each page below states the axe rule it is **expected** to trigger. Those expectations are my best
reading of axe's behaviour; they are not gospel.

**Run `verify.js` and record what axe actually reports for every route.** Then:

- axe reports the expected rule and nothing else → good.
- axe reports **extra** violations on a page → **fix the page.** You have introduced a defect this
  guide did not ask for.
- axe reports **nothing** on a page expected to fail → **fix the page.** The defect did not land.
- axe reports a **different but genuinely correct** rule → **fix this document's expectation, never
  the page.** Record what it actually said.

That last rule matters most. The fixture's value is that reality and the record agree; when they
diverge, reality wins and the record gets corrected.

The recorded output becomes the fixture's own baseline. Re-run it on every change.

---

## 5. Batch 1 — the rule pages (axe-detectable)

These prove the rule half of the engine works before any AI exists. Build them first.

### 5.1 `/catalogue/recommended` — image with no alt at all

```html
<h2>Recommended this month</h2>
<img id="cover-nightjar" src="/assets/covers/nightjar.jpg" width="200" height="300">
<p>Chosen by our Tuesday reading group.</p>
```

Expect: **`image-alt`**. Note the difference from §8.1 — there the attribute is present but useless,
which axe accepts. Here it is absent, which axe rejects.

### 5.2 `/about/opening-hours` — text below 4.5:1

```html
<p id="hours-note" style="color: #929292;">
  We close at 4pm on the first Wednesday of each month for staff training.
</p>
<p>Tuesday to Friday, 9am to 7pm. Saturday, 9am to 5pm.</p>
```

Expect: **`color-contrast`** on `#hours-note` (3.11:1, needs 4.5:1). Inline style is deliberate —
it keeps the failure on one element instead of leaking through a shared class. Font must stay 16px
normal weight; at 18pt or bold-14pt the 3:1 threshold would apply and it would pass.

### 5.3 `/contact` — input with no label of any kind

```html
<form action="/contact" method="post">
  <p>Send us a message and we will reply within two working days.</p>
  <input id="contact-email" type="text" name="email">
  <button type="submit">Send</button>
</form>
```

Expect: **`label`**. No `<label>`, no `aria-label`, no `title`, no `placeholder`.

### 5.4 `/about/membership` — no `lang` on `<html>`

Needs `views/layout-nolang.ejs`: a copy of `layout.ejs` with `lang="en"` removed from `<html>` and
**nothing else changed**. Used by this route only.

Expect: **`html-has-lang`**.

### 5.5 `/events/calendar` — duplicate id referenced by ARIA

```html
<h2>What's on</h2>
<p id="event-note">Booking opens two weeks before each event.</p>
<button type="button" aria-describedby="event-note">Book a place</button>
<p id="event-note">Members may bring one guest.</p>
```

Expect: **`duplicate-id-aria`**.

### 5.6 `/catalogue/reserve` — button with no accessible name

```html
<h2>Reserve a copy</h2>
<p>Reserved copies are held at the front desk for three days.</p>
<button id="reserve-submit" type="button" class="icon-only"></button>
```

```css
.icon-only { width: 44px; height: 44px; background: url("/assets/icons/bookmark.svg") center/20px no-repeat; border: 1px solid var(--ink); }
```

Expect: **`button-name`**. The button must contain **nothing** — no text node, no whitespace-only
child, no `aria-label`.

### 5.7 `/about/history` — the control page, zero violations

```html
<h2>A short history</h2>
<p>Meridian Library opened in 1897 in a converted corn exchange on Fenner Road.</p>
<img id="photo-corn-exchange" src="/assets/photos/corn-exchange.jpg" width="480" height="320"
     alt="The corn exchange in 1897, a two-storey brick building with arched windows">
<h3>The reading room</h3>
<p class="muted">The first-floor reading room was added in 1923.</p>
```

Expect: **nothing**. Zero violations at the WCAG tag set.

**This is the most important page in the batch.** If it reports anything, your scan configuration or
your layout is wrong, and every other result that day is suspect. Do not proceed until it is clean.

### 5.8 `/events/tickets` — the WCAG 2.2 canary

A page with one job: prove the 2.2 ruleset is running end to end. A 20×20 tap target, below the
24×24 minimum in 2.5.8:

```html
<h2>Tickets</h2>
<p>Tickets for paid events are collected at the front desk.</p>
<p>See the <a id="ticket-info" href="/events/calendar"
   style="display:inline-block;width:20px;height:20px;overflow:hidden">i</a> for details.</p>
```

Expect: **`target-size`**, under `wcag22aa`.

**If this page comes back clean, your 2.2 rules are not running** — whatever `npm ls` reported. The
tag is missing from your config, or your axe-core predates it, or the array has a typo. Stop and fix
that before trusting any other result.

This is the same idea as `/about/history` in reverse: a page whose expected result is known
absolutely, so it catches configuration errors before they contaminate real findings. `/about/history`
proves the scan is not over-reporting; this proves it is not under-reporting.

> 2.5.8 is not one of the five POC criteria and this page carries no AI label. It is pure
> instrumentation. Keep the inline style — it must not depend on a shared class someone could later
> "tidy" into compliance.

### 5.9 The overlap pair — where the two engines meet

**`/reports/lending-summary`** — informative image marked as decorative:

```html
<h2>Lending summary</h2>
<img id="chart-lending" src="/assets/charts/lending-2026.png" width="600" height="360" alt="">
<p>Loans rose in the spring and fell back over the summer holidays.</p>
```

axe: **clean** — an empty `alt` is legal, and axe reads it as decorative. AI: should **fail 1.1.1**,
because the image carries information the empty alt discards.

**`/about/team`** — genuinely decorative image marked as decorative:

```html
<h2>Our team</h2>
<img id="divider-team" src="/assets/decor/rule.svg" width="600" height="8" alt="" role="presentation">
<p>Eleven librarians and four volunteers.</p>
```

axe: clean. AI: should **pass** — empty alt is correct here.

Together these test that the AI adds judgment where the rules stop, without firing where the rules'
silence was right. Both are inputs to QA-14's de-duplication.

---

## 6. Batch 2 — the demo path

Four pages, and three of them come from Batch 4 below. Build these next so you can demo and test M1:

| Order | Route | Built in |
|---|---|---|
| 1 | `/about/opening-hours` | §5.2 |
| 2 | `/catalogue/new-arrivals` | §8.1 |
| 3 | `/catalogue/staff-picks` | §8.1 |
| 4 | `/about/visit-us` | §8.1 |

The demo turns on pages 2 and 3 being **visually near-identical** and axe being silent on both.
Give them the same layout, the same six covers, the same spacing. The only difference a sighted
person can see is the page title.

---

## 7. Batch 3 — the completeness pages

Exact counts, no labels needed, deterministic. These test that no candidate is silently dropped.

| Route | Contains exactly | For checker |
|---|---|---|
| `/catalogue/browse-all` | **12** `<img>` elements | meaningful-alt |
| `/staff/bulk-actions` | **20** interactive controls | fake-semantics |
| `/account/full-profile` | **15** labelled form controls | label |
| `/branches` | **8** colour-coded indicators | colour-only |
| `/about/terms` | **0** candidates — prose only | all |

**Build rules:**

- The count must be exact and easy to re-verify. Generate them from a seed array of that length, not
  by hand-copying markup — a hand-copied 20th item is how you end up with 19.
- On `/catalogue/browse-all`, mix alt quality (some good, some poor). The count is what is being
  tested, not the verdicts.
- `/about/terms` must contain **no images, no form controls, no buttons, no colour-coded anything**.
  It exists to prove an empty page is a clean no-op rather than an error.
- The expected counts live in the golden dataset's `manifest.json`, **not** on the page. Nothing may
  advertise how many candidates it holds.

---

## 8. Batch 4 — the AI half

### 8.1 · 1.1.1 — meaningful alt

**`/catalogue/new-arrivals` — FAIL.** All six covers, every one identical:

```html
<img id="cover-tidewater" src="/assets/covers/tidewater.jpg" width="200" height="300" alt="cover">
<img id="cover-salt-path" src="/assets/covers/salt-path.jpg" width="200" height="300" alt="cover">
<!-- …all six, alt="cover" each time… -->
```

**`/catalogue/staff-picks` — PASS.** Same six covers, same ids, real alt:

```html
<img id="cover-tidewater" src="/assets/covers/tidewater.jpg" width="200" height="300"
     alt="Tidewater by Ursula Vane — cover showing a flooded harbour at dusk">
<img id="cover-salt-path" src="/assets/covers/salt-path.jpg" width="200" height="300"
     alt="The Salt Path Home by Idris Okonkwo — cover showing a dirt road through wheat fields">
```

Both pass axe. Only judgment separates them.

| Route | Element | Markup | Expected |
|---|---|---|---|
| `/authors/featured` | `#portrait-vane` | `alt="IMG_2231.jpg"` | **fail** |
| `/authors/spotlight` | `#portrait-vane` | `alt="Ursula Vane, photographed at the 2019 festival"` | **pass** |
| `/reports/borrowing-trends` | `#chart-borrowing` | `alt="chart"` | **fail** |
| `/reports/annual-review` | `#chart-borrowing` | `alt="Monthly loans in 2026: a rise from January to a May peak of 1,240, then a decline to 780 in August"` + a linked long description | **pass** |
| `/events/summer-reading` | `#divider-summer` | decorative rule, `alt="decorative divider line"` | **fail** — noise in the reading order |
| `/events/book-club` | `#divider-summer` | same rule, `alt="" role="presentation"` | **pass** |

**The two ambiguous pages — author these last, with the expert present.**

`/catalogue/award-winners` — a cover with full-title alt, the same title as visible text
**immediately after it in the DOM**:

```html
<figure>
  <img id="cover-cartographer" src="/assets/covers/cartographer.jpg" width="200" height="300"
       alt="The Cartographer's Apprentice by Hana Sato">
  <figcaption>The Cartographer's Apprentice — Hana Sato</figcaption>
</figure>
```

Expected: **uncertain**. Redundancy makes a screen reader say it twice; an empty alt leaves the cover
unnamed. Both defensible.

`/about/visit-us` — a photo in a "Visit us" panel:

```html
<h2>Visit us</h2>
<img id="photo-interior" src="/assets/photos/reading-room.jpg" width="480" height="320" alt="library">
<p>We are on Fenner Road, a five-minute walk from the bus station.</p>
```

Expected: **uncertain**. Decorative or informative depends on intent the page does not record.

### 8.2 · 1.3.1 — info and relationships

| Route | Planted | Expected |
|---|---|---|
| `/help/borrowing-guide` | `<div class="h2" id="sec-renewals">Renewals</div>` styled to look like a heading | **fail** |
| `/help/getting-started` | `<h2 id="sec-renewals">Renewals</h2>`, same appearance | **pass** |
| `/account/loan-history` | Loan table built from `<div>` + CSS grid, visually a table with header row | **fail** |
| `/account/statements` | Same data as `<table>` with `<th scope="col">` | **pass** |
| `/account/notifications` | Three radios visually grouped under a "Notify me by" heading, **no `<fieldset>`** | **fail** |
| `/account/preferences` | Same three radios in `<fieldset><legend>Notify me by</legend>` | **pass** |
| `/catalogue/genres` | A genre shown in `<b>` where it may or may not carry meaning | **uncertain** |

```html
<!-- /account/notifications — FAIL. Each radio has its own label, so axe stays quiet;
     what is missing is the group. -->
<h2>Notify me by</h2>
<div class="radio-group" id="notify-group">
  <input type="radio" id="notify-email" name="notify" value="email">
  <label for="notify-email">Email</label>
  <input type="radio" id="notify-post" name="notify" value="post">
  <label for="notify-post">Post</label>
  <input type="radio" id="notify-none" name="notify" value="none">
  <label for="notify-none">Do not contact me</label>
</div>
```

### 8.3 · 4.1.2 — name, role, value

| Route | Planted | Expected |
|---|---|---|
| `/staff/catalogue-entry` | `<div class="btn" id="save-entry" onclick="save()">Save</div>` | **fail** |
| `/staff/quick-edit` | `<button type="button" id="save-entry" class="btn">Save</button>` | **pass** |
| `/staff/branch-settings` | Custom switch, state shown only by CSS position | **fail** |
| `/staff/display-options` | `<button type="button" role="switch" aria-checked="true">` | **pass** |
| `/staff/reports` | Tab strip built from `<a href="#panel-1">`, no tab roles | **fail** |
| `/staff/overview` | Same strip with `role="tablist"` / `role="tab"` / `role="tabpanel"` / `aria-selected` | **pass** |
| `/staff/exports` | A real navigation link styled to look exactly like a button | **uncertain** |

```html
<!-- /staff/branch-settings — FAIL. To a sighted user the knob position says on or off.
     To assistive technology this is a div with a word next to it. -->
<div class="field">
  <span>Show closed branches</span>
  <div id="toggle-closed-branches" class="switch is-on" onclick="toggleSwitch(this)"></div>
</div>
```

> **`/staff/catalogue-entry` implicates two criteria and that is unavoidable.** A `div` with an
> `onclick` and no `tabindex` is both a missing role (4.1.2) and unreachable by keyboard (2.1.1).
> One planted defect, two criteria. Label it against 4.1.2 and record 2.1.1 in the rationale — do
> **not** add `tabindex="0"` to "isolate" it, because a keyboard-reachable div is a *different*
> defect and no longer the one described here.

### 8.4 · 1.4.1 — use of colour

**`/loans/current` — FAIL.** Status carried by row tint only; the legend maps colour to meaning,
which is exactly the mapping a colourblind user cannot make.

```html
<h2>Current loans</h2>
<ul class="legend" id="loans-legend">
  <li><span class="swatch swatch-overdue"></span> Overdue</li>
  <li><span class="swatch swatch-due-soon"></span> Due soon</li>
  <li><span class="swatch swatch-on-loan"></span> On loan</li>
</ul>
<table id="loans-table">
  <thead><tr><th scope="col">Title</th><th scope="col">Due</th></tr></thead>
  <tbody>
    <tr class="row-overdue"><td>Tidewater</td><td>2 July 2026</td></tr>
    <tr class="row-due-soon"><td>Nightjar</td><td>19 August 2026</td></tr>
    <tr class="row-on-loan"><td>Bell and Bone</td><td>30 September 2026</td></tr>
  </tbody>
</table>
```

**`/loans/history` — PASS.** Identical, plus a text badge per row:

```html
<tr class="row-overdue"><td>Tidewater</td><td>2 July 2026</td><td><span class="badge">Overdue</span></td></tr>
```

| Route | Planted | Expected |
|---|---|---|
| `/account/join` | Required fields marked **only** by a red `<label>` | **fail** |
| `/account/update-details` | Same fields marked `(required)` in text, plus `aria-required="true"` | **pass** |
| `/reports/branch-comparison` | Inline SVG chart, three series distinguished by colour only, legend maps colour to branch | **fail** |
| `/reports/monthly-issues` | Same chart with distinct hatch patterns **and** direct labels on each series | **pass** |
| `/loans/renewals` | Colour **plus** an icon that is not self-explanatory — a filled dot vs a hollow ring | **uncertain** |

> On `/account/join`, the red label must still meet contrast against white. The defect is that colour
> is the *only* signal, not that the colour is hard to read. Use `#c0392b` (5.44:1) — verified.
>
> The SVG charts carry `role="img"` and a full `aria-label` describing the data, so 1.1.1 is
> satisfied and the **only** issue is the colour-only visual encoding.

### 8.5 · 2.5.3 — label in name

> **Read this before building this section.** axe-core has a rule for 2.5.3 —
> **`label-content-name-mismatch`** — so unlike the other four criteria, part of this one is
> machine-detectable. Two consequences:
>
> 1. `/catalogue/search` and `/account/apply` will probably be flagged by **both** axe and the AI.
>    That makes them **overlap** cases, valuable for QA-14's de-duplication, not AI-only cases.
> 2. The genuinely AI-only case is `/account/my-loans`, where the accessible name *does* contain the
>    visible text and axe is satisfied — but the name adds scope the user never said.
>
> Verify which of these axe actually reports in §4 and record it. Do not assume.

| Route | Planted | Expected |
|---|---|---|
| `/catalogue/search` | Visible `Search`, `aria-label="Find books"` | **fail** (likely axe + AI) |
| `/catalogue/advanced-search` | Visible `Search`, `aria-label="Search books"` | **pass** |
| `/account/apply` | Visible `Join`, `aria-label="Submit membership application"` | **fail** (likely axe + AI) |
| `/account/register` | Visible `Join`, accessible name `Join the library` | **pass** |
| `/newsletter` | Field whose only label is `placeholder="Email"` | **fail** |
| `/account/my-loans` | Icon button, visible `Renew`, accessible name `Renew all loans` | **uncertain** |

```html
<!-- /catalogue/search — FAIL. A voice user says "click Search" and nothing happens. -->
<button id="search-submit" type="submit" aria-label="Find books">Search</button>

<!-- /catalogue/advanced-search — PASS. The accessible name contains the visible text. -->
<button id="search-submit" type="submit" aria-label="Search books">Search</button>
```

---

## 9. Batch 5 — interaction journeys (M3)

Not needed until QA-20. Vanilla JS only, one file per page under `public/js/`.

| Route | Planted | Criterion |
|---|---|---|
| `/events/book-a-room` | Date picker that captures Tab and never releases it | 2.1.2 |
| `/events/book-a-seat` | Same picker; Escape closes, focus returns to the trigger | 2.1.2 |
| `/catalogue/reserve-copy` | Dialog that does not return focus to its trigger on close | 2.4.3 |
| `/catalogue/place-hold` | Same dialog, focus returns correctly | 2.4.3 |
| `/catalogue/all-titles` | Focused row scrolls under a `position: sticky` header — ring hidden | **2.4.11** |
| `/catalogue/by-subject` | Same page with `scroll-padding-top` so the ring stays visible | 2.4.11 |
| `/account/settings` | Positive `tabindex` values scrambling the order | 2.4.3 |
| `/account/security` | Natural DOM order, no positive `tabindex` | 2.4.3 |
| `/help/faq` | `outline: none` with no replacement indicator | 2.4.7 |
| `/help/contact-us` | Visible custom focus ring | 2.4.7 |
| `/catalogue/filter` | `<select>` that submits the form on `change` | 3.2.2 |
| `/catalogue/refine` | Same select plus an explicit Apply button | 3.2.2 |
| `/catalogue/results` | "3 results found" injected with no live region | 4.1.3 |
| `/catalogue/quick-find` | Same message inside `aria-live="polite"` | 4.1.3 |

`/help/faq` needs `outline: none` scoped to that page only — do **not** touch the global
`:focus-visible` rule, or you break focus on all 45 pages.

**`/catalogue/all-titles` is not an axe page.** Whether a sticky header covers the focused element
depends on scroll position and live layout, so it is not statically decidable and axe has no rule
for 2.4.11. This page is caught by the **M3 agentic checker** (J8), which operates the app — axe will
report nothing on it, with or without the `wcag22aa` tag, and that is correct.

The page that proves the 2.2 *ruleset* is live is the canary at §5.8. This one proves the *agent*
can find what a scanner structurally cannot, which is the whole argument for M3.

---

## 10. `routes.json` and the README

`routes.json` lists every rendered route exactly once with a human title, `in_scope: true` for all
but `/health`. **Titles only, never verdicts** — this file ships in the app repo and the judge can
read it.

`README.md` carries the deliberately false conformance claim for M2's posture check:

```markdown
## Accessibility

Meridian Library conforms to WCAG 2.1 Level AA. Last audited March 2024.
```

Also add `CONTRIBUTING.md` whose **first paragraph** reads: *the accessibility problems in this
application are deliberate. Do not fix them. See the build guide.*

Give the repo a dozen or so plausible commits over time. Code-intel reads the history, and a
one-commit repo looks like exactly what it is.

---

## 11. Definition of done

- [ ] `npm start` serves on 4180 and logs `Meridian Library listening on …`
- [ ] `/health` returns `200 {"status":"ok"}` and is `in_scope: false` in `routes.json`
- [ ] Every route in `routes.json` renders; every rendered route is in `routes.json`
- [ ] The same URL returns byte-identical HTML on two consecutive requests
- [ ] **`/about/history` reports zero axe violations** at the WCAG tag set (not over-reporting)
- [ ] **`/events/tickets` reports `target-size`** (not under-reporting — the 2.2 ruleset is live)
- [ ] **`/about/terms` yields zero candidates** and produces no error
- [ ] Every Batch 1 page reports its expected rule **and nothing else**
- [ ] Every "pass" twin reports **zero** violations
- [ ] The completeness pages hold exactly 12 / 20 / 15 / 8 candidates — counted, not assumed
- [ ] Every element named in §8 has a stable, neutral `id`, and each twin reuses its counterpart's
- [ ] `verify.js` output is committed as the fixture's baseline
- [ ] No route, class, comment, id or data attribute names a defect
- [ ] No external origins are referenced anywhere
- [ ] README carries the false claim; CONTRIBUTING carries the do-not-fix warning

**The last word.** If the acceptance run disagrees with this guide, the run is right. Correct the
guide, never the page — unless the page has a defect this guide did not ask for, in which case fix
the page. Knowing which is which is why §4 gets built before any content.

---

**See also:** `PROVING_GROUND_APP_SPEC.md` (why each page exists) · `GOLDEN_DATASET_SPEC.md` (how
these pages get labelled) · `../RESEARCH_CORRECTIONS.md` (R2 on companion-local browsing).
