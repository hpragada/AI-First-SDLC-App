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
  "version": "1.2.0",
  "private": true,
  "type": "commonjs",
  "scripts": {
    "start": "node server.js",
    "routes": "node tools/gen-routes.js"
  },
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

// Express has no layout support of its own, and this is not worth a dependency: render the page
// to a string, then render the layout around it. `layout` lets a route ask for a different shell.
app.use((_req, res, next) => {
  res.page = (view, locals = {}) => {
    res.render(view, locals, (err, body) => {
      if (err) return next(err);
      res.render(locals.layout || "layout", Object.assign({}, locals, { body }));
    });
  };
  next();
});

app.get("/health", (_req, res) => res.json({ status: "ok" }));

require("./routes/index")(app);

app.use((_req, res) => { res.status(404); res.page("not-found", { title: "Page not found" }); });

app.listen(PORT, () => console.log(`Meridian Library listening on http://localhost:${PORT}`));
```

The startup line must read exactly `Meridian Library listening on` — the companion's
`preview_start.ready_log` matches on it.

**Write `require("./routes/index")`, not `require("./routes")`.** Node tries `routes.json` before
the `routes/` directory, so the short form loads the generated route manifest instead of the code
that serves the routes. It works right up until `gen-routes.js` writes `routes.json` for the first
time, then breaks in a way that reads like a corrupted install.

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

The layout itself must be **flawless**. A defect here would appear on all 68 pages and contaminate
every label.

### `public/styles.css` — the palette

These values are computed, not estimated. Do not change them without re-running
the harness's `npm run contrast`.

```css
:root {
  --ground: #f2f0ea;      /* the page behind the content card */
  --surface: #ffffff;     /* the content card — every ratio below is measured against this */
  --surface-alt: #f7f5f0; /* panels and table headings */

  --ink: #1a1a1a;         /* 17.40:1 on surface — body text */
  --ink-soft: #43423f;    /* 10.05:1 on surface — secondary text */
  --muted: #666666;       /* 5.74:1 on surface, 5.27:1 on a panel — passes everywhere it is used */
  --faint: #929292;       /* 3.11:1 on surface — FAILS AA. Deliberate. /about/opening-hours only */
  --link: #0b5fa5;        /* 6.57:1 on surface */
  --required: #c0392b;    /* 5.44:1 on surface */

  --brand: #14434e;       /* white on this = 10.81:1 — header, buttons */
  --brand-deep: #0e3038;  /* white on this = 14.01:1 — footer */
  --brand-soft: #cfdde1;  /* on brand-deep = 10.06:1 — footer secondary text */

  --tint-overdue:  #fdecea;   /* ink on this = 15.22:1 */
  --tint-due-soon: #fff8e1;   /* ink on this = 16.38:1 */
  --tint-on-loan:  #e8f5e9;   /* ink on this = 15.47:1 */
}
```

Two colours used by the app are **not** tokens, and both are deliberate.

```css
/* Every text input, select and textarea. 2.98:1 on the surface, 2.73:1 on a panel.
   FAILS the 3:1 that 1.4.11 asks of a non-text part you have to be able to see. */
border: 1px solid #9a958c;

/* The two states on the charges statement (v1.4.0). Both legible; near-identical in lightness. */
color: #c0392b;   /* still owed  — 5.44:1 on surface, relative luminance 0.143 */
color: #2e7d32;   /* settled     — 5.13:1 on surface, relative luminance 0.155 */
```

> **The field border is a planted 1.4.11 failure, and it is the only one in the fixture.** It
> appears on every form page, which is a knowing exception to one-defect-per-page: it is a
> property of the shared form styling rather than of any one view, and giving it its own page
> would mean styling that page's fields differently from every other page's — which is a bigger
> lie than the exception. No golden record cites it yet, because the checker that would judge it
> (`graphics`, 1.4.11) has no answer key at all; see "Not covered, and how to add it" in
> `golden/README.md`. It is asserted in `check-contrast.js` under `DELIBERATE_FAILURES` so it
> survives until somebody labels it.

> **The two charge colours must stay ALIKE, which is the opposite of every other rule here.**
> They are a 1.4.1 case: both are comfortably legible, so contrast is not the defect — what makes
> them a failure is that hue is the only thing separating them. Darken one "to be safe" and they
> become tellable apart in greyscale, the pages stop being colour-only, and the records that
> depend on them quietly become wrong while every other check still passes. `check-contrast.js`
> asserts the luminance gap stays under 0.03 (`SAME_LIGHTNESS`); it is currently 0.012.

> **Why the status tints are so pale.** The colour-only pages (§8.4) must fail 1.4.1 and **nothing
> else**. If a tint dropped text contrast below 4.5:1, those pages would fail contrast too, axe would
> report it, and you could no longer tell which engine found what. Every tint above keeps text above
> 15:1. Verified, not guessed.

> **Why page content sits on white.** `--faint` fails at exactly 3.11:1 *against white*. Tint the
> surface it sits on and the planted failure moves, possibly out of failing range. Keep the warmth
> in the ground around the content card, never under the content.

### `harness/check-contrast.js` — compute the palette, do not choose it

Nineteen pairs pass, three have to fail, and one pair has to stay indistinguishable. Write a
checker that asserts all three kinds, so the failing and the look-alike pairs are guarded as
carefully as the passing ones — a planted defect that nothing asserts is a planted defect that
quietly disappears:

```js
function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
const ratio = (fg, bg) => {
  const [a, b] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
};
```

This earns its place immediately. The first palette used `#757575` for muted text — a documented
4.61:1 on white — which drops to **4.23:1** the moment that text sits on a panel. It is now
`#666666`. axe would have caught it eventually, on whichever pages happened to have panels; this
catches it while choosing the colour.

### The design has to be good enough to show people

The demo script in the spec opens with *"here is an ordinary-looking library application"*. A page
that reads as unstyled HTML undermines that before the first finding lands, so the fixture carries a
real design: a brand header, a content card on a tinted ground, a serif display face, card grids, a
four-column footer.

**Do the design work before the dataset is labelled.** Screenshots are part of the judgment cache
key. A redesign afterwards invalidates the answer key and buys you the labelling cost twice.

Three constraints are not negotiable, because each one silently breaks a planted defect:

**The shell contributes no `<img>` and no form control.** It renders on all 68 pages, so a logo
image or a header search box becomes a candidate on *every* page — including `/about/terms`, whose
entire job is to hold **zero**, and `/account/full-profile`, which must hold exactly 15 controls.
Text and CSS only; draw the monogram as a `background-image` on `::before` with empty content.

**The site header is not `position: sticky`.** `/catalogue/all-titles` plants WCAG 2.4.11 with a
sticky column header at the top of the viewport. A second sticky bar above it changes the geometry
the defect depends on.

**Keep the shell's link count modest.** Every link in the header and footer is a candidate for the
fake-semantics checker on all 68 pages. Five nav links and twelve footer links is a realistic site
and a bearable judging cost; forty would triple the bill for no extra coverage.

**No external resources.** No CDN fonts, no hosted scripts, no remote images. Use system font stacks
(`"Iowan Old Style", Palatino, Georgia, serif` for display) and `data:` URIs for anything drawn.
Playwright is launched with `--allowed-origins` scoped to the preview host, so a cross-origin asset
may be blocked — and a page that renders differently under scan than in your expert's browser
invalidates its labels.

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

### The checks do not live in the app repository

**Every tool that knows what the answers are belongs outside the fixture**, in
`evaluation/harness/`. The app repository holds only what a real library application would hold.

This is not tidiness. The fixture gets onboarded as a brownfield project, and code intelligence
indexes what it finds: `integrations/codeintel/builtin.py` treats `.js` as source and `.json` as
context, and `runner/companion/codeintel_mcp.py` mines **commit messages** for "decision
archaeology". A file listing every route, criterion and expected verdict — indexed next to the app
— lets an agent find the planted defects by reading the tests instead of by examining the pages,
and the whole measurement is then worth nothing.

The same applies to the history. Commit messages naming what was planted are indexed as
decisions. Write them as ordinary product work: *"Add the account, staff and report pages"*, not
*"check the planted cases are actually planted"*.

If the app is only ever scanned live (QA-17 visits rendered pages and never reads the repository)
this costs nothing anyway — so there is no reason not to do it.

### Nothing may reveal the answer

Not in a comment, a class name, a data attribute, a route, or an `id`. The judge sees the rendered
page and the URL. Class names describe appearance (`.status-row`), never intent (`.planted-fail`).

> **The stylesheet and the scripts count as "the page".** They are fetched by every route, so a
> comment in `styles.css` is exactly as readable as the markup. This is the easiest rule in the
> guide to break, because the comments that give the game away are the ones you most want to write
> — the ones stopping the next developer "fixing" the CSS. The first build of this fixture shipped
> ten of them, including `/* Required marked by colour alone — one page depends on this being the
> only cue. */` sitting directly above the class that does it.
>
> The rule that resolves it: **CSS and JS comments say what the code does, never why it is that
> way.** The why goes in `CONTRIBUTING.md` and this guide, neither of which a browser downloads.
> Where a developer genuinely needs the warning, point at `CONTRIBUTING.md` rather than explaining.
>
> `CONTRIBUTING.md` itself disclosing that the app is deliberately wrong is fine and intended — it
> is what stops a well-meaning fix. What must never leak is *which element on which page*.

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

**Cover images:** `public/assets/covers/<id>.svg`, 400×600. Any fixed image is fine **provided it
actually depicts the description above** — the alt-text judgment is scored against whether the alt
conveys what the image shows, so a mismatch makes the label wrong.

Hand-authored SVG rather than photographs, for three reasons: it can be made to depict the
description exactly, it is diffable so a later change to a cover is visible in review, and it keeps
the repo free of binary assets whose provenance nobody can check. Each one carries
`role="presentation"`, so the SVG contributes no accessible name of its own and the `<img>` alt is
the only name in play — which is the thing under judgment.

**A second set of six** — `winter-orchard`, `long-field`, `paper-boats`, `red-kite`, `signal-box`,
`almanac` — exists only to make the twelve-image completeness page (§7) reach twelve without
repeating a cover. Those six carry an `altStyle` field holding the poor alt text used on that page.
Keep them out of `/catalogue`, `/catalogue/new-arrivals` and `/catalogue/staff-picks`: the matched
pair in §8.1 turns on both pages showing the **same six** covers.

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

### `harness/verify.js`

Run axe over every route in `routes.json` and write a report. Use exactly this configuration:

```js
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

// `label-content-name-mismatch` is experimental upstream, so a tag filter leaves it out.
// `target-size` runs under `wcag22aa` on its own; naming it here is belt-and-braces.
const OPT_IN_RULES = {
  "target-size": { enabled: true },                 // WCAG 2.5.8
  "label-content-name-mismatch": { enabled: true }, // WCAG 2.5.3, "experimental" upstream
};

// One options() call. Not withTags().options() — see below.
const results = await new AxeBuilder({ page })
  .options({ runOnly: { type: "tag", values: TAGS }, rules: OPT_IN_RULES })
  .analyze();
```

Also give the browser context a fixed viewport (`1280×900`). `@axe-core/playwright` refuses a page
created straight off the browser, and contrast and target-size are measured against layout, so a
varying viewport makes those results vary with it.

**The tag set is not optional.** Without it axe also runs best-practice rules (`region`,
`landmark-one-main`, `page-has-heading-one`, `tabindex`) that are not WCAG A/AA. Those would fire on
pages this guide expects to be clean, and you would spend a day chasing a phantom.

### Three things about axe that the first build got wrong

Each of these was found by running the check, not by reading. They cost half a day between them,
and every one of them applies to any scanner built on axe — including the platform's own.

**1 · `AxeBuilder.options()` overwrites; it does not merge.** `withTags(t)` sets
`this.option = { runOnly: … }` and `options(o)` then sets `this.option = o`, discarding it. So

```js
new AxeBuilder({ page }).withTags(TAGS).options({ rules: OPT_IN_RULES })  // WRONG
```

throws the tag filter away and silently runs **every rule axe has**, best-practice included. Nothing
errors. The scan looks like it worked; it just answered a different question. Put both settings in
one `options()` call, as above.

**2 · One rule needs naming, and not for the reason it looks like.** Corrected 2026-08-20 after
measuring it; the earlier version of this section said both rules ship disabled, and that is wrong.

`target-size` (2.5.8) does carry `enabled: false` — but a tag-based `runOnly` runs it anyway. The
`enabled` flag governs only what axe does when you give it **no** instructions. Select `wcag22aa`
and the rule fires.

`label-content-name-mismatch` (2.5.3) is the opposite case: it carries `enabled: true` and it does
**not** run under a tag filter. What holds it back is its `experimental` tag — axe leaves
experimental rules out of a tag-selected run. Two ways in: add `"experimental"` to the tag list,
which also pulls in seven unrelated experimental rules, or name it in `rules`.

Measured on axe-core 4.13.0 against a page carrying both defects:

```
tags only                           | 64 rules | target-size RAN | label-in-name no
tags + "experimental"               | 71 rules | target-size RAN | label-in-name RAN
tags + rules opt-in (this guide)    | 65 rules | target-size RAN | label-in-name RAN
no runOnly at all (axe defaults)    | 89 rules | target-size no  | label-in-name no
```

So `OPT_IN_RULES` is load-bearing for `label-content-name-mismatch` only. Keeping `target-size` in
it changes nothing and makes the intent explicit.

**This applies to the platform, not just this harness.** `runner/companion/assets/a11y_audit.mjs`
sends the tag list with no `rules` override, so it gets `target-size` and does not get
`label-content-name-mismatch`. That is defensible — 2.5.3 is owned by the AI `label` checker — but
it should be a decision rather than an accident.

**3 · `wcag22aa` is one rule, and `wcag22a` is none.** In axe-core 4.13 `wcag22aa` matches exactly
`target-size` and nothing else; `wcag22a` matches no rule at all. Everything else WCAG 2.2 added is either not statically decidable or has no axe rule. Do not
read a clean 2.2 result as coverage.

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

**Run the harness's `verify` and record what axe actually reports for every route.** Then:

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
<img id="cover-nightjar" src="/assets/covers/nightjar.svg" width="200" height="300">
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

### 5.5 `/events/calendar` — a link whose only content is an unnamed image

```html
<h2>What's on</h2>
<p id="event-note">Booking opens two weeks before each event.</p>
<button type="button" aria-describedby="event-note">Book a place</button>

<p>Add the season to your own calendar:
  <a id="calendar-download" href="/events/tickets"><img src="/assets/icons/bookmark.svg"
     width="20" height="20" alt=""></a>
</p>
```

Expect: **`link-name`**. The link has no text and its image is marked decorative, so it has no
accessible name at all.

> This page originally planted a duplicate `id` referenced by `aria-describedby`, expecting
> **`duplicate-id-aria`**. It does not work: axe returns that rule as **`incomplete`**, not as a
> violation — it cannot decide the case automatically. An `incomplete` result is not a finding, so
> the page reported clean and the defect was invisible. `link-name` fails deterministically.
>
> Worth remembering beyond this page: **`incomplete` is a third outcome**, and a scanner that reads
> only `violations` discards it silently. Whatever consumes axe results downstream should decide
> what it does with `incomplete` rather than let it fall on the floor.

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
<img id="photo-corn-exchange" src="/assets/photos/corn-exchange.svg" width="480" height="320"
     alt="The corn exchange in 1897, a two-storey brick building with arched windows">
<h3>The reading room</h3>
<p class="muted">The first-floor reading room was added in 1923.</p>
```

Expect: **nothing**. Zero violations at the WCAG tag set.

**This is the most important page in the batch.** If it reports anything, your scan configuration or
your layout is wrong, and every other result that day is suspect. Do not proceed until it is clean.

### 5.8 `/events/tickets` — the WCAG 2.2 canary

A page with one job: prove the 2.2 ruleset is running end to end. Four adjacent 20×20 tap targets,
below the 24×24 minimum in 2.5.8:

```html
<h2>Tickets</h2>
<p>Tickets for paid events are collected at the front desk.</p>

<h3>Browse past seasons</h3>
<ul class="pager">
  <li><a id="page-1" href="/events/calendar">1</a></li>
  <li><a id="page-2" href="/events/calendar">2</a></li>
  <li><a id="page-3" href="/events/calendar">3</a></li>
  <li><a id="page-4" href="/events/calendar">4</a></li>
</ul>
```

```css
.pager { display: flex; gap: 0; list-style: none; margin: 0; padding: 0; }
.pager a { display: block; width: 20px; height: 20px; line-height: 20px; text-align: center;
           font-size: 12px; border: 1px solid var(--rule); text-decoration: none; }
```

Expect: **`target-size`**, under `wcag22aa`.

> **This has to be right or the page reports clean, which is the one result it must never give.**
>
> **A pager, not a link in a sentence.** 2.5.8 exempts a target that sits inline within a block of
> text, so an undersized link inside a paragraph passes and passing is correct. Four adjacent
> block-level links with `gap: 0` satisfy neither the size threshold nor the spacing exception.
> This — not the `enabled` flag — is what the first build got wrong here; `target-size` runs under
> the `wcag22aa` tag whether or not it is named in `rules`. See §4, item 2.

**If this page comes back clean, your 2.2 rules are not running** — whatever `npm ls` reported. The
rule is not opted in, or the tag is missing from your config, or your axe-core predates it. Stop and
fix that before trusting any other result.

This is the same idea as `/about/history` in reverse: a page whose expected result is known
absolutely, so it catches configuration errors before they contaminate real findings. `/about/history`
proves the scan is not over-reporting; this proves it is not under-reporting.

> 2.5.8 is not one of the five POC criteria and this page carries no AI label. It is pure
> instrumentation. `.pager` is used on this page only — if it ever appears elsewhere, give this page
> its own class, or someone will "tidy" the spacing and take the canary out without knowing it.

### 5.9 The overlap pair — where the two engines meet

**`/reports/lending-summary`** — informative image marked as decorative:

```html
<h2>Lending summary</h2>
<img id="chart-lending" src="/assets/charts/lending-2026.svg" width="600" height="360" alt="">
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

### `harness/count-candidates.js` — count them, do not assume them

These pages are worthless if their own counts are taken on trust. A checker returning eleven results
for a page holding twelve images has dropped one silently — but only if the page really holds twelve.
Count from the rendered DOM:

```js
{ route: "/catalogue/browse-all", expected: 12,
  count: () => document.querySelectorAll("main img").length }
```

Scope every selector to `main`. The header nav and the footer are the same on all 68 pages and
belong to no page in particular; counting them makes every number four higher than the answer key
says and sends you looking for a bug in the checker.

Run it after any change to these five pages. It is cheap and it catches the one failure mode —
a page quietly holding nineteen of something — that nothing else in this repo would notice.

---

## 8. Batch 4 — the AI half

### 8.1 · 1.1.1 — meaningful alt

**`/catalogue/new-arrivals` — FAIL.** All six covers, every one identical:

```html
<img id="cover-tidewater" src="/assets/covers/tidewater.svg" width="200" height="300" alt="cover">
<img id="cover-salt-path" src="/assets/covers/salt-path.svg" width="200" height="300" alt="cover">
<!-- …all six, alt="cover" each time… -->
```

**`/catalogue/staff-picks` — PASS.** Same six covers, same ids, real alt:

```html
<img id="cover-tidewater" src="/assets/covers/tidewater.svg" width="200" height="300"
     alt="Tidewater by Ursula Vane — cover showing a flooded harbour at dusk">
<img id="cover-salt-path" src="/assets/covers/salt-path.svg" width="200" height="300"
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
  <img id="cover-cartographer" src="/assets/covers/cartographer.svg" width="200" height="300"
       alt="The Cartographer's Apprentice by Hana Sato">
  <figcaption>The Cartographer's Apprentice — Hana Sato</figcaption>
</figure>
```

Expected: **uncertain**. Redundancy makes a screen reader say it twice; an empty alt leaves the cover
unnamed. Both defensible.

`/about/visit-us` — a photo in a "Visit us" panel:

```html
<h2>Visit us</h2>
<img id="photo-interior" src="/assets/photos/reading-room.svg" width="480" height="320" alt="library">
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
| `/catalogue/subject-index` | Five-column subject table whose header row is `<td>`; no `<th>` on the page. Five failing cells | **fail** × 5 |
| `/catalogue/subject-list` | Same table, header row as `<th scope="col">` | **pass** |

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
| `/staff/shelf-audit` | Four section switches as bare `<div>` — no role, no name, no state, not focusable. Four failing controls | **fail** × 4 |
| `/staff/shelf-settings` | Same four as `<button role="switch" aria-checked aria-labelledby>` | **pass** |
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
| `/help/report-a-problem` | A rejected field shown by a red border alone — no note, no `aria-invalid`, no `aria-describedby` | **fail** |
| `/help/problem-report` | Same field, plus a `.field-note` in words and `aria-invalid` + `aria-describedby` | **pass** |
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
> machine-detectable. But **only if you opt the rule in by name**: it ships `enabled: false` and is
> marked experimental upstream, so a scan configured with WCAG tags alone never runs it, and 2.5.3
> is AI-only in practice. See §4.
>
> With the rule enabled, the measured behaviour is:
>
> - `/catalogue/search` and `/account/apply` are flagged by **both** axe and the AI. **Overlap**
>   cases, valuable for QA-14's de-duplication, not AI-only cases.
> - `/account/my-loans` is genuinely AI-only: the accessible name *does* contain the visible text so
>   axe is satisfied, but the name adds scope the user never said.
> - `/newsletter` is also AI-only, for a different reason — see the note under the table.

| Route | Planted | axe | Expected |
|---|---|---|---|
| `/catalogue/search` | Visible `Search`, `aria-label="Find books"` | `label-content-name-mismatch` | **fail** |
| `/catalogue/advanced-search` | Visible `Search`, `aria-label="Search books"` | clean | **pass** |
| `/account/apply` | Visible `Join`, `aria-label="Submit membership application"` | `label-content-name-mismatch` | **fail** |
| `/account/register` | Visible `Join`, accessible name `Join the library` | clean | **pass** |
| `/newsletter` | Field whose only label is `placeholder="Email"` | clean | **fail** |
| `/account/card-services` | Seven action buttons — visible `Renew`/`Pay`/`Report`/`Freeze`/`Replace`/`Upgrade`/`Close`, each `aria-label` dropping that word entirely. Seven failing controls | `label-content-name-mismatch` × 7 nodes | **fail** × 7 |
| `/account/card-options` | Same seven, each `aria-label` starting with the visible word | clean | **pass** |
| `/account/my-loans` | Icon button, visible `Renew`, accessible name `Renew all loans` | clean | **uncertain** |

> **`/newsletter` reports clean, and that is correct axe behaviour, not a missing defect.** axe's
> `label` rule accepts `non-empty-placeholder` as one of the ways a control can be named, so a
> placeholder-only field satisfies it. The field does have *a* name; the problem is that the name
> disappears the moment anything is typed into it, which is a judgment call and not a static one.
> Do not "fix" this page into failing by removing the placeholder — that turns it into a duplicate
> of `/contact` (§5.3).

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
| `/catalogue/by-subject` | Same page with `scroll-margin-top` on the rows so the ring stays visible | 2.4.11 |
| `/account/settings` | Positive `tabindex` values scrambling the order | 2.4.3 |
| `/account/security` | Natural DOM order, no positive `tabindex` | 2.4.3 |
| `/help/faq` | `outline: none` with no replacement indicator | 2.4.7 |
| `/help/contact-us` | Visible custom focus ring | 2.4.7 |
| `/about/find-a-branch` | Branch `<select>` that navigates the moment it takes focus — choosing a value does nothing, arriving on it does | **3.2.1** |
| `/about/choose-a-branch` | Same select; nothing happens on focus or on change, only when **Go** is pressed | 3.2.1 |
| `/catalogue/filter` | `<select>` that submits the form on `change` | 3.2.2 |
| `/catalogue/refine` | Same select plus an explicit Apply button | 3.2.2 |
| `/catalogue/results` | "3 results found" injected with no live region | 4.1.3 |
| `/catalogue/quick-find` | Same message inside `aria-live="polite"` | 4.1.3 |

`/help/faq` needs `outline: none` scoped to that page only — do **not** touch the global
`:focus-visible` rule, or you break focus on all 68 pages.

`/account/settings` uses positive `tabindex` values. axe *does* have a rule for that (`tabindex`),
but it is tagged **best-practice only**, so the WCAG tag set excludes it and the page reports clean.
That is the intended outcome: this stays an agent-only page. If it ever reports `tabindex`, the tag
filter is not being applied — see §4.

### Building the 2.4.11 pair — three things that look right and are not

**`/catalogue/all-titles` is not an axe page.** Whether a sticky header covers the focused element
depends on scroll position and live layout, so it is not statically decidable and axe has no rule
for 2.4.11. This page is caught by the **M3 agentic checker** (J8), which operates the app — axe will
report nothing on it, with or without the `wcag22aa` tag, and that is correct.

The page that proves the 2.2 *ruleset* is live is the canary at §5.8. This one proves the *agent*
can find what a scanner structurally cannot, which is the whole argument for M3.

Getting the page to actually misbehave took three attempts. All three failures produced a page that
*looked* right and quietly did the correct thing:

**The header must stick to the viewport, not to a scroll box.** The obvious build — a list in its own
`overflow-y: auto` container with a sticky header inside it — does not reproduce the defect in
Chromium, which keeps a container's own sticky children out of the way when it scrolls something
into view inside that container. Nothing does that for a header stuck to the viewport. So: the page
scrolls, not a box on the page.

**The fix goes on the rows, not the page.** `scroll-padding-top` belongs to the scroll container,
which for a page-scrolled document is the root element — so it cannot be scoped to one page without
putting a class on `<html>`. `scroll-margin-top` on the rows themselves does the same job, is a
per-element property, and scopes cleanly to one list:

```css
.title-list.with-scroll-margin a { scroll-margin-top: 4rem; }
```

**The list has to be long.** Ninety-six rows — twelve titles across eight branches. With a short
list, walking back up reaches the top of the document before any row needs top-aligning, and the
defect never gets a chance to appear.

**And afterwards, never put `overflow` on the container.** This one bit twice. `overflow: hidden` on
the list wrapper — the obvious way to clip its rounded corners — makes that wrapper the scroll
container for its own sticky child. The header then sticks to a box that never scrolls and slides
off the top of the screen with everything else. The page still looks right until you scroll it.
Round the corners on the header and the last row individually instead.

> **If you write a check for this, note that `element.focus()` will not reproduce it.** Chromium
> centres a programmatically focused element in the viewport, where nothing covers it. Sequential
> focus navigation aligns to the nearest edge — the top, when moving up — which is what a keyboard
> user actually gets. Drive it with real `Shift+Tab` presses, and take the highest position reached
> across the whole walk rather than sampling one step: the browser only scrolls on the steps where
> the next row is off screen, so most steps show nothing.

### `harness/verify-journeys.js`

Every page in this batch reports clean under axe, so nothing else in the repo can tell whether the
planted behaviour is there. A focus trap that does not trap, or a dialog that happens to restore
focus anyway, becomes a scoring error the day an agent is run over the site — the agent gets marked
wrong for reporting what the page really does.

Drive each page and assert the behaviour, **in both directions**: the fail page must misbehave and
the twin must behave. A check that only asserts the failure still passes when both pages are broken.

---

## 10. `routes.json` and the README

`routes.json` lists every rendered route exactly once with a human title, `in_scope: true` for all
but `/health`. **Titles only, never verdicts** — this file ships in the app repo and the judge can
read it.

**Generate it, do not maintain it.** Keep the routes in one declarative table in `routes/index.js`
and have `tools/gen-routes.js` write `routes.json` from that table. A hand-maintained manifest
drifts, and it drifts in the direction that hurts: a route served but missing from the manifest is
never scanned, and the platform's coverage number is quietly wrong with nothing to indicate it.

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

## 10a. The two checks that catch what the others cannot

Everything described so far proves axe reports the right thing. For roughly two thirds of this app
the right thing is **nothing** — and nothing is also what you get from a page that has quietly lost
the markup it was built around. Two more checks close that gap. Build both.

### `harness/verify-plants.js` — assert the defect is still there

One entry per planted case, stating the DOM fact its label depends on, asserted **in both
directions**: the broken page must be broken *and* the twin must be correct. A check that only
asserts the failure still passes when both halves of a pair are broken.

```js
{
  route: "/account/notifications", criterion: "1.3.1", verdict: "fail",
  what: "radios with individual labels but no group",
  test: () => {
    const group = document.getElementById("notify-group");
    const radios = group.querySelectorAll('input[type="radio"]');
    if (radios.length !== 3) return `${radios.length} radios, expected 3`;
    if (group.closest("fieldset")) return "the group is in a fieldset — the defect is gone";
    return true;
  },
}
```

Return `true` or a **string saying what was found instead**. When one of these fires a year from
now, the string is the whole diagnosis.

It should also compare **twin page heights**. The demo turns on two pages being indistinguishable
to a sighted person; a structural divergence shows up as a height difference long before anyone
notices it by eye.

### `harness/audit.js` — the invariants no single page owns

- no comment in any **served** file names a defect (see §2)
- no page references an external origin — `xmlns` declarations are not fetches, allow those
- every route returns byte-identical HTML on two consecutive requests
- no page has a duplicate `id`, which would silently change what a dataset selector resolves to
- every view on disk is routed, and every route appears in `routes.json`
- no console errors anywhere

### Sizing check — is there enough here to label?

Before committing to a dataset version, count the candidates the app actually offers per checker.
Measured on this fixture at 68 routes:

| Checker | Candidates | Pages holding any |
|---|---|---|
| meaningful-alt | 48 | 19 |
| fake-semantics | 366 | 43 |
| colour-only | 41 | 8 |
| label | 68 | 23 |

Comfortable for **v0.1 (100 records, 20 per criterion)**. For **v1.0 (250 records, 50 per
criterion)** `meaningful-alt` and `colour-only` have no headroom and need more pages first —
every record is a distinct `(route, checker, selector)`, so candidates cannot be reused. Count
before labelling, not after.

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
- [ ] Every journey page behaves as planted, and each twin behaves correctly — driven, not assumed
- [ ] Every planted case is asserted present, and every twin asserted correct — in both directions
- [ ] Every colour pair the stylesheet uses is computed, including the one that must keep failing
- [ ] No **served** file — markup, CSS or JS — carries a comment naming a defect
- [ ] No duplicate `id` on any page, and every view on disk is routed
- [ ] The shell holds no `<img>` and no form control, and the site header is not sticky
- [ ] There are enough candidates per checker for the dataset version you intend to label
- [ ] The site looks like something you would show a client
- [ ] Every element named in §8 has a stable, neutral `id`, and each twin reuses its counterpart's
- [ ] the harness's axe baseline is committed as the fixture's baseline
- [ ] `routes.json` is generated, not hand-edited, and regenerated after adding a route
- [ ] No route, class, comment, id or data attribute names a defect
- [ ] No external origins are referenced anywhere
- [ ] README carries the false claim; CONTRIBUTING carries the do-not-fix warning

**The last word.** If the acceptance run disagrees with this guide, the run is right. Correct the
guide, never the page — unless the page has a defect this guide did not ask for, in which case fix
the page. Knowing which is which is why §4 gets built before any content.

---

**See also:** `PROVING_GROUND_APP_SPEC.md` (why each page exists) · `GOLDEN_DATASET_SPEC.md` (how
these pages get labelled) · `../RESEARCH_CORRECTIONS.md` (R2 on companion-local browsing).
