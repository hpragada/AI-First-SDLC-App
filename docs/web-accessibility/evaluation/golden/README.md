# Golden set — v0.1.0

```
INTERNAL — Edvensoft accessibility evaluation data.
Not a tenant feature. Must never be read by tenant-facing code or written to tenant tables.
```

The answer key for QA-09. 99 hand-authored labels over the Meridian Library fixture at
**app v1.3.0**, against which QA-10 scores how often each AI checker is right.

The specification is `../GOLDEN_DATASET_SPEC.md`. This file records what was actually built,
what was decided along the way, and the four things the reviewing expert needs to rule on.

> **v0.1 is for proving the harness. Do not publish these numbers and do not gate on them.**
> At ~10 failing elements per criterion, one miss moves recall by 10 points.

---

## Status: draft, awaiting expert adjudication

Every record carries `"labelled_by": "draft-unadjudicated"`. QA-09 requires an
expert-adjudicated verdict per record, and that has not happened yet — the field says so rather
than implying a sign-off. When the expert has reviewed a criterion, change `LABELLED_BY` in
`build.py` (or the individual records) to their initials and bump `dataset_version`.

`relabel_verdict`, `relabel_on` and `adjudication` are `null` throughout. The blind re-label
round (spec §6) is a separate piece of work and must happen at least three weeks after the
first pass.

---

## What is in it

| Criterion | Checker(s) | Records | Clear fail | Clear pass | Ambiguous |
|---|---|---|---|---|---|
| 1.1.1 Non-text Content | `alt` | 22 | 10 | 10 | 2 |
| 1.3.1 Info and Relationships | `semantics`, `structure` | 13 | 6 | 6 | 1 |
| 4.1.2 Name, Role, Value | `semantics` | 21 | 10 | 10 | 1 |
| 1.4.1 Use of Color | `color` | 23 | 10 | 10 | 3 |
| 2.5.3 Label in Name | `label` | 20 | 9 | 9 | 2 |
| | | **99** | **45** | **45** | **9** |

The clear tier is exactly balanced fail/pass in every criterion. That is deliberate: an
unbalanced set lets a checker score well by leaning one way, and "flag everything" is the
failure mode a compliance tool falls into naturally.

Every record comes from a planted fail/pass **twin pair** — the same element, on two pages that
look identical to a sighted reader, correct on one and broken on the other. `verify-plants.js`
asserts both directions on every pair, so a page that quietly loses its defect fails the harness
rather than silently invalidating a label.

---

## Files

```
1.1.1-non-text-content.json
1.3.1-info-and-relationships.json
4.1.2-name-role-value.json
1.4.1-use-of-colour.json
2.5.3-label-in-name.json
manifest.json      dataset/app version, per-criterion counts, the limitation note
build.py           the authored labels; regenerates all six files
```

**Why the JSON files do not carry the internal-use header.** Spec §1 asks for it on every file.
`scorer/labels.py` requires each criterion file to be a JSON *list* of records, and JSON has no
comments, so there is nowhere to put a header that would not also have to parse as a record. The
notice lives in `manifest.json`'s `notes`, in `build.py`'s docstring, and at the top of this
README instead.

**Why there is a generator.** The manifest's per-criterion counts are a hard stop in
`labels.py` — a file and a count that disagree refuse to score rather than scoring a sample
nobody chose. Deriving both from one table makes that mistake impossible instead of merely
unlikely. The labels themselves are hand-authored: every `truth`, `expected_verdict` and
`rationale` is written per element.

To change a label, edit `build.py` and re-run `python build.py`.

---

## Checking it

```bash
node verify-golden.js
```

From `../harness/`, with the fixture running. It asserts spec §7 rule 2 — every
`(route, selector)` resolves on the running app — and re-derives each selector with the
companion's own `cssPath()` to confirm it still matches. Also in `npm run check`.

Both matter because `scorer/platformdata.py` joins a label to a verdict on
`(route, selector, checker)` as an **exact string match with no normalisation**. A selector that
is merely equivalent does not join, and the record scores as never-looked-at — which reads as a
coverage miss when it is really a stale answer key.

Every selector in this set was produced by running `cssPath()` against the fixture
(`../harness/dump-selectors.js`), not written by hand. All 99 currently resolve and match.

---

## Two coverage gaps this set already exposes — one now closed

Both were found while labelling, before any scoring run. They are recorded as normal `fail`
records, so the harness reports them as never-captured misses against recall. **The set earning
its keep before it scored anything is the point worth noticing here.**

**1. The chart series on `/reports/branch-comparison` are never captured.** — **FIXED
2026‑08‑28.** Three `<polyline>` elements distinguished by stroke colour alone. `polyline`
was not in the companion's `OFFER` list, so they were never sent to any check — the page's only
1.4.1 defect could not be found, and the page was still recorded as checked. Same shape as the
`tr` gap `5af4c53` fixed for `/loans/current`. **3 records: `g-141-0013/0015/0017`.**

> **Closing it took two changes, not one, and the second was not obvious.** Offering the shapes
> is necessary and does nothing on its own: a `<polyline>` has no text and no `background-color`,
> and `stroke` was not a captured style, so every rule would have looked at it, found no colour
> at all, and correctly declined. The elements would have moved from *never captured* to
> *captured and claimed by nobody* — which reads better on a coverage report and finds exactly
> as many defects.
>
> So `stroke` and `fill` are now captured, and the colour rule reads them **for `polyline` and
> `polygon` only**. `fill` computes to opaque black on any SVG element that never set it, so
> reading it everywhere would make every icon in an application a colour candidate and spend the
> run's judgment budget on decoration.
>
> Verified against the running fixture: all three series report distinct painted strokes against
> a parent stroke of `none`, and the real rule claims all three. The parent `<svg>`, carrying the
> default black fill, is not claimed — it goes to `graphics`, which is the right question for
> it.

**2. The tab strip on `/staff/reports` is never captured for `semantics`.** The container is a
`<div>` with no role and no handler, and the three tabs are `<a href="#panel-…">`. The semantics
rule deliberately skips an `<a>` that has an href, on the reasoning that a real link with real
semantics needs no judgment. That is right in general and may be wrong when the link is dressed
as a tab. **4 records: `g-412-0005` through `g-412-0008`.** Needs an expert ruling before
anyone changes the rule — see below.

A pass-side label on an element the platform correctly declines to select is **not** a problem:
`accuracy.py` counts it as `never_looked` and excludes it from every other figure, so the
platform gets no credit and no penalty for a right answer it never gave.

---

## Four things for the reviewing expert

1. **`/newsletter` `#newsletter-email` is filed under the wrong criterion** (`g-253-0019`). The
   fixture calls it a 2.5.3 failure — "a field whose only label is its placeholder". On the
   criterion's own terms 2.5.3 is *satisfied*: the visible text is the placeholder "Email" and
   the accessible name derived from it is "Email", so the name contains the visible label. The
   real defects are 3.3.2 (the label vanishes on typing) and arguably 4.1.2. Labelled `pass`
   with `difficulty: ambiguous` so the disagreement is visible rather than silently dropped.
   **If you agree, the fix is in the fixture, not here** — re-plant it as a 3.3.2 case.

2. **Is a link dressed as a tab a 4.1.2 failure?** (`g-412-0005`–`0008`, and the related
   `/staff/exports` case `g-412-0021`.) The answer decides whether the semantics rule's
   `<a href>` skip needs narrowing, which is a platform change.

3. **The `uncertain` tier.** 9 records where `truth` and `expected_verdict` deliberately
   diverge — a confident answer is scored as *wrong* even when it matches truth, because the
   product depends on the checker knowing when it does not know. Please sanity-check that each
   is genuinely arguable and not just something we found hard. Where you can supply a real ACT
   rule id or WAI technique number for one, replace the `anchor`: the current anchors cite WCAG
   Understanding documents by name, and none are fabricated, but a specific rule id is stronger.

4. **1.3.1 is short.** 6 clear failures against 10 for every other criterion, because the
   fixture plants fewer distinct 1.3.1 failing elements. Growing it is a page-building job in
   the fixture repo, not a labelling job here.

---

## What v0.1 is not

- **Not expert-adjudicated.** See Status above.
- **Not blind re-labelled.** `relabel_agreement` is `null`. Spec §6: if round-one/round-two
  agreement comes in below 90%, stop and fix the labelling process before scoring anything.
- **Not a recall denominator for the whole app.** It labels the planted twins, not every
  candidate on every page. Recall here means "of the failures we planted, how many were found".
- **Not big enough to gate on.** Spec §5: v1.0 wants 50 per criterion, which needs ~34 more
  planted failures in the fixture first.

## Cross-references

- `../GOLDEN_DATASET_SPEC.md` — the specification (Doc B)
- `../PROVING_GROUND_APP_SPEC.md` — the fixture this labels (Doc A)
- `../harness/verify-plants.js` — asserts every planted defect and every clean twin
- `../harness/verify-golden.js` — asserts every label still resolves
- `../scorer/` — QA-10, the harness that consumes this
- `../../TASK_BACKLOG_QA.md` — QA-09, QA-10
