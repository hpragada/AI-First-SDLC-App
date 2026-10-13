# Golden set — v0.2.0

```
INTERNAL — Edvensoft accessibility evaluation data.
Not a tenant feature. Must never be read by tenant-facing code or written to tenant tables.
```

The answer key for QA-09. 173 hand-authored labels over the Meridian Library fixture at
**app v1.4.0**, against which QA-10 scores how often each AI checker is right.

The specification is `../GOLDEN_DATASET_SPEC.md`. This file records what was actually built,
what was decided along the way, and the things the reviewing expert needs to rule on.

> **v0.2 is still for proving the harness. Do not publish these numbers and do not gate on them.**
> Every checker can now reach the 30 scored records the scorer requires before it reports
> anything — which is the whole point of this version — but 30 records with ~15 failures means
> one miss moves recall by 6–7 points. Legitimate to look at internally. Not a figure to put in
> front of a client.

---

## Status: draft, awaiting expert adjudication

Every record carries `"labelled_by": "draft-unadjudicated"`. QA-09 requires an
expert-adjudicated verdict per record, and that has not happened yet — the field says so rather
than implying a sign-off. When the expert has reviewed a criterion, change `LABELLED_BY` in
`build.py` (or the individual records) to their initials and bump `dataset_version`.

`relabel_verdict`, `relabel_on` and `adjudication` are `null` throughout. The blind re-label
round (spec §6) is a separate piece of work and must happen at least three weeks after the
first pass.

**Two authoring passes, both drafts, both unadjudicated.** 99 records on 2026‑08‑26 and 74 on
2026‑08‑28; `labelled_on` says which, and `app_version` records the fixture version each was
actually written against rather than being rewritten to today's whenever the files are
regenerated. `labelled_by` is the same value on all 173 deliberately: they are the same kind of
artefact and should not read as two classes of record. **Not one of the 99 changed in any field
when the 74 were added**, which is checkable from the commit rather than taken on trust.

---

## What is in it

| Criterion | Checker(s) | Records | Clear fail | Clear pass | Ambiguous |
|---|---|---|---|---|---|
| 1.1.1 Non-text Content | `alt` | 32 | 15 | 15 | 2 |
| 1.3.1 Info and Relationships | `semantics`, `structure` | 37 | 18 | 18 | 1 |
| 4.1.2 Name, Role, Value | `semantics` | 27 | 13 | 13 | 1 |
| 1.4.1 Use of Color | `color` | 35 | 16 | 16 | 3 |
| 2.5.3 Label in Name | `label` | 42 | 20 | 20 | 2 |
| | | **173** | **82** | **82** | **9** |

Five of the platform's six AI checkers. The sixth has no records and that is a decision, not an
omission — see **Not covered, and how to add it** below.

The clear tier is exactly balanced fail/pass in every criterion. That is deliberate: an
unbalanced set lets a checker score well by leaning one way, and "flag everything" is the
failure mode a compliance tool falls into naturally.

Every record comes from a planted fail/pass **twin pair** — the same element, on two pages that
look identical to a sighted reader, correct on one and broken on the other. `verify-plants.js`
asserts both directions on every pair, so a page that quietly loses its defect fails the harness
rather than silently invalidating a label.

---

## What v0.2.0 added, and the measurement problem it fixed

**At v0.1.0 not one checker could produce a number, and more audits would never have changed
that.** `accuracy.py` refuses to call a checker measured below 30 scored records. The ceilings
were: `alt` 20, `color` 19, `label` 9, `semantics` 25, `structure` 6.

**The count of records was never the ceiling, and that is the part worth understanding.** A
record only reaches `Score.sample` if `accuracy._record` puts it there, and it does not treat the
two sides alike:

```
expected `fail`       always counts — a true positive if found, a false negative if not
expected `pass`       counts ONLY if the checker actually SELECTS the element
expected `uncertain`  never counts; it is scored on calibration instead
```

So a `pass` twin the selection rules skip is **inert**: it can never move any figure in either
direction, and it looks exactly like a healthy record in every other check. `label` sat at 9
usable records out of 19 for exactly this reason — all ten of its pass twins name a control whose
accessible name already contains its visible text, and `_applies_label` skips precisely those,
correctly, because the criterion is then met as a matter of fact and there is nothing left to
judge. **A deliberately balanced answer key was producing a completely one-sided scored sample
and every check in the harness was green.** Written up as `RESEARCH_CORRECTIONS.md` R20.

**74 records were added, on 16 new fixture pages (8 twin pairs), taking every checker over 30:**

| Checker | Could score at v0.1.0 | Added | Can score now |
|---|---|---|---|
| `alt` | 20 | +10 | 30 |
| `color` | 19 | +12 | **32** |
| `label` | 9 | +22 | **20** — see below |
| `semantics` | 25 | +6 | 31 |
| `structure` | 6 | +24 | 30 |

Three selection rules were corrected on the same day, after the records were written, and two of
those numbers moved because of it. `color` gained one when a border stopped counting as a
non-colour cue (R19). `label` **lost eleven** when the comparison behind it was corrected from
letters to words (R21) — the records became provably-fine controls the checker rightly skips.

**`label` is short by ten and cannot be made otherwise.** After the correction, the only controls
that reach the judge are ones where the words genuinely differ, and those are either real
failures or genuinely arguable. A clearly-correct example is, by definition, one the check skips.
So 2.5.3 has no balanced sample to be had: **recall for it is meaningful, precision is not.**
Recorded in `scorer/selectable.py` under `KNOWN_SHORTFALL`, which reports it and does not fail —
while any shortfall that is *not* recorded there still fails.

**Every one of the 74 elements was checked against the platform's real selection rules before
its label was written** — captured from the running fixture in the companion's own shape, then
run through `rules.checkers_for()`. All 74 are claimed by the checker they name, including all
37 pass records. `verify-selectable.js` now re-runs that check as part of `npm run check`, so
this cannot regress silently.

**What is deliberately not in the 74.** No `uncertain` records and no `ambiguous` tier. Those are
where a single labeller's judgment is worth least and where a labeller who is also the system
under test is worth least of all; the spec says to author them with the expert present, so the
nine that exist are all from the first pass.

**Citations.** Every v0.2.0 defect names a published WCAG technique, checked against the live W3C
document on 2026‑08‑28 rather than recalled. Where no failure technique covers the case — there
is none for "built a table out of divs" — the record cites the sufficient technique it fails to
meet and says which kind of citation it is. The v0.1.0 records mostly carry the default anchor;
item 3 for the expert below already asks for those to be strengthened, so the newer records
simply start where that request points.

**One design was thrown away after being measured.** The `label` pass twins first used a
bracketed count — visible "Pay (3 charges)", spoken "Pay". The W3C rule's label-in-name algorithm
strips bracketed text and calls that a pass; axe-core 4.13.0 does not strip it and reports a
violation. Two authoritative implementations disagreeing is the definition of a case that is not
clear, so it was replaced with the family both agree on: a typographic mark in the visible label
that the spoken name omits. Verified in both directions afterwards — axe reports all eleven
controls on the defect page and none on its twin.

---

## Not covered, and how to add it

**`graphics` — SC 1.4.11 Non-text Contrast — has zero records, in v0.1.0 and in v0.2.0.** The
platform ships that checker. It has **no accuracy evidence of any kind**, and this dataset does
not change that. Stated plainly here because a gap nobody wrote down reads, years later, like an
oversight, and nobody can tell whether it was ever considered.

**Why it is excluded.** The `graphics` checker was written on 27 Aug 2026 by the same author who
wrote the 74 records above. An answer key written by whoever wrote the checker measures whether
that author is consistent with themselves, not whether the checker is right. That is not a
failing to be careful about; it is not measurable by that person at all.

**The one constraint on adding it: the author of the records must not be the author of the
checker.** Everything else below is logistics.

**What is already in place for whoever writes them.**

- **Material exists in the fixture and is guarded.** Every form field carries a `#9a958c` border
  at **2.98:1 against the content surface and 2.73:1 against a panel**, below the 3:1 that
  1.4.11 requires of a non-text part you need to see. It is deliberate and it is now asserted in
  `../harness/check-contrast.js` under `DELIBERATE_FAILURES`, so it cannot quietly disappear
  before anyone gets to label it. It appears on every form page, which is a knowing exception to
  "one planted defect per page" — recorded in `../PROVING_GROUND_BUILD_GUIDE.md`.
- **The checker's scope is wider than `alt`'s, on purpose.** `_applies_graphics` selects a bare
  `<svg>` with no name and a CSS background image, both of which `_applies_alt` skips. Read the
  docstring before choosing elements: the two checks disagree about the same element deliberately,
  and a labeller who assumes they agree will write records that never score.
- **The standard's own exemption is the judge's to apply, not the rule's.** 1.4.11 exempts
  graphics where a particular presentation is essential — a photograph is the textbook case — and
  the rules deliberately do not try to tell a photograph from a diagram. "This is a photograph, so
  not applicable" is a complete and correct answer, which means some records should expect exactly
  that.
- **Check selectability before writing labels.** `npm run selectable` will tell you which of your
  draft records could never score. Doing this after writing the labels is how v0.1.0 ended up
  with a `label` ceiling of 9.

**Also still uncovered:** SC 1.4.10 Reflow, and the 23 criteria the rule scanner owns. Those are
a different kind of gap — they are measured by the scanner's own determinism, not by this set.

---

## Files

```
1.1.1-non-text-content.json
1.3.1-info-and-relationships.json
4.1.2-name-role-value.json
1.4.1-use-of-colour.json
2.5.3-label-in-name.json
manifest.json      dataset/app version, per-criterion counts, expected candidates, the caveats
build.py           the authored labels; regenerates all six files
```

`manifest.json` also carries `expected_candidates` — how many candidates a page is known to
hold, which `scorer/completeness.py` compares against how many the run actually captured. **It is
a lower bound and the check it feeds is coarser than it looks**: the comparison counts every
(element, checker) claim on the route, not only the planted ones, so a page holding five
photographs reports a surplus and the number only fires if capture on that route collapses. The
five v0.1.0 pages are also asserted from the rendered DOM by `../harness/count-candidates.js`,
and the two agreeing is itself a check. **The sixteen v0.2.0 pages are not in that file, on
purpose** — they are twin pairs, so `verify-plants.js` already asserts their exact contents
element by element, which is strictly stronger than a total. Duplicating the totals there would
add a second place to keep in step and check nothing new.

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
node verify-golden.js        # do these labels still point at real elements?
node verify-selectable.js    # could these labels ever score?
```

From `../harness/`, with the fixture running. Both are in `npm run check`.

**They answer different questions and you need both.** `verify-golden.js` asserts spec §7 rule 2
— every `(route, selector)` resolves on the running app — and re-derives each selector with the
companion's own `cssPath()` to confirm it still matches. That is about the page.

`verify-selectable.js` asks whether the checker a record names would actually **select** that
element, which is about the selection rules. A record can resolve perfectly and still be
incapable of ever scoring; see "What v0.2.0 added" above for the version of this that cost a
checker half its usable records. It captures in Node and decides in Python using the platform's
own `rules.py` rather than a copy — a copy would drift, and would then be certifying the answer
key against rules nobody runs.

Both matter because `scorer/platformdata.py` joins a label to a verdict on
`(route, selector, checker)` as an **exact string match with no normalisation**. A selector that
is merely equivalent does not join, and the record scores as never-looked-at — which reads as a
coverage miss when it is really a stale answer key.

Every selector in this set was produced by running `cssPath()` against the fixture
(`../harness/dump-selectors.js`), not written by hand. All 99 currently resolve and match.

---

## Four coverage gaps this set exposed — all four now closed

The first three were found while labelling, before any scoring run, and were closed on
2026‑08‑28 once the team had ruled on the two that changed platform behaviour. **The fourth was
found by a live audit on 2026‑08‑31**, and it is the one worth reading twice: it had been sitting
inside a set that every harness check called healthy. Each is recorded as a normal `fail` record,
so the harness reports it as a never-captured miss against recall rather than as a special case.

**The set earning its keep before it scored anything is the point worth noticing here** — four
real defects on four different checkers, found by writing down what the right answer was and
checking whether the platform could even be asked the question.

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
as a tab. **4 records: `g-412-0005` through `g-412-0008`**, and the related `/staff/exports`
case `g-412-0021`. Needs an expert ruling before anyone changes the rule — see below.

> **Still open, and wider than this paragraph says.** Checked on 2026‑08‑28 against the real
> markup, on the theory that `structure` might be reaching the container even though `semantics`
> is not — it claims a `<div>` whose children repeat a class, which is what a tab strip usually
> looks like. It is not reaching it. Both the container and every tab come back claimed by
> **nothing at all**:
>
> ```
> #report-tabs        (the <div class="tabstrip">)   ->  ()
> #report-tabs a      (one tab, an <a href>)         ->  ()
> ```
>
> The container escapes `structure` on a detail: the rule looks for a **repeated** child class,
> and only one of the three tabs carries one (`is-current`). So the elements are captured, every
> rule declines them, and the page is recorded as checked.
>
> **FIXED 2026‑08‑28**, on the team's ruling that a link dressed as a tab is a 4.1.2 failure.
>
> The worry about narrowing the `<a href>` skip was that it changes how every link in every
> tenant's application is treated. So the narrowing was made on a fact about behaviour rather
> than about styling: **an in-page link does not navigate.** "A real link with real semantics
> needs no judgment" holds for a link that goes somewhere; it is not safely true of one that
> stays on the page, which may be a tab, a disclosure or a toggle wearing an anchor.
>
> Measured before it was written, so the blast radius is known rather than hoped for: the whole
> fixture holds **four in-page links against 228 ordinary ones**, so this asks about 1.7% of the
> anchors on the site and leaves every real navigation link exactly where it was.
>
> The container is claimed too, by the same measure — a `div` holding three or more in-page
> links. One tab cannot tell you whether it is part of a tab list, and the relationship between
> the strip and the panels below it lives on the container or nowhere. Exactly **one** container
> in the fixture matches.
>
> All four records now reach the checker they name, so they can be found rather than only
> missed.

**3. A field whose error state is a red border is invisible to the colour check — because it has
a border.** Found 2026‑08‑28 while planting 1.4.1 material for v0.2.0. `_has_second_cue` treats
any `border-style` other than `none` as a non-colour cue, which is right in general and wrong
here: the field already had a border, and only its **colour** changed. **1 record:
`g-141-0019`**, labelled a clear failure, declined by the rule; its twin `g-141-0020` is declined
too and cannot score.

> Measured across the whole fixture: **219 of 6,885 captured elements are excluded from the
> colour check for having a border**, including every form control in the application. Nothing
> else covers them — 1.4.1 has exactly one axe rule in our tag selection (`link-in-text-block`)
> and it is about links in prose. So the commonest way on the web to mark a field invalid is
> decided by no engine the platform runs.
>
> **FIXED 2026‑08‑28**, on the team's ruling, by removing the border from the second-cue test
> entirely.
>
> Every narrower option was measured first and none of them work. Comparing the border's colour
> against the parent's saves four candidates out of three hundred, because a parent almost never
> has a border to compare against; comparing it against the element's own text colour saves
> none. There is no way to tell a decorative border from a signalling one from what a single
> element carries, so the judge decides — the same trade `_repeats_a_child_class` already makes
> and states: it costs a judgment on things that turn out to be fine, and that is the direction
> worth being wrong in.
>
> Cost: **+300 colour candidates across 94 routes**, against the 901 already selected. Both
> records on this pair now score, and `color`'s reachable sample went from 31 to 32. Full
> write-up in `../RESEARCH_CORRECTIONS.md` R19.

**4. A container `<div>` with no class on it is never captured — found 2026‑08‑31, FIXED the
same day.** The three season containers on `/events/workshops` are
`<div id="workshops-spring" style="padding-left:1.5rem">`, each wrapping five identically classed
children. `structure` claims that shape on sight; it was simply never shown one, because the
`OFFER` list carried `div[class]` and these have no class. **3 records: `g-131-0032/0034/0036`.**

> **This one was found by a live audit and not by the harness, and that is the finding.** All
> three were labelled `fail`, and an expected-`fail` record counts toward a checker's ceiling
> whether or not anything reaches it — so `structure` read as reaching 30 the whole time, while
> **3 of its 15 failure records could never be found by any judge.** Its recall was capped at
> **12/15 = 80%** and nothing said so.
>
> `verify-selectable.js` could not have caught it either: it reached each recorded element with
> `document.querySelector`, which finds anything on the page whether an audit would collect it or
> not, so it reported all three as perfectly selectable. **Both halves are fixed** — see gap-fix
> §9.25 and the harness README.
>
> The capture now also offers `div:has(> *:nth-child(3))`, which is `REPEATED_CHILD_MINIMUM` said
> in CSS: the same bar the rule that would claim it uses. Deliberately not `div[id], div[style]`,
> which would have fixed this fixture and left every framework's class-less, id-less wrapper
> exactly as invisible as before.
>
> Cost, measured across all 95 routes before it was written: **8,385 elements offered today, and
> this adds three** — the three on this page, all three claimed. The busiest page in the fixture
> sits at 545 of the 600-per-page ceiling and is unchanged by it.

A pass-side label on an element the platform correctly declines to select is **not** a problem in
itself: `accuracy.py` counts it as `never_looked` and excludes it from every other figure, so the
platform gets no credit and no penalty for a right answer it never gave. It becomes a problem
when there are enough of them to hollow out a checker's sample, which is what `verify-selectable.js`
now watches for.

**And "declined by a rule" is now told apart from "never collected at all".** They used to read
the same and they are not the same: the first is a rule's decision, visible and often correct;
the second is an element nothing ever looked at, which no answer key can compensate for. Only the
second fails the run.

---

## Things for the reviewing expert

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

4. **~~1.3.1 is short.~~ Closed 2026‑08‑28** — it was 6 clear failures against 10 elsewhere,
   and v0.2.0 added 12 more container records across four kinds of failure. Now 18, in line with
   the rest.

5. **Is a field marked invalid by a red border a case the colour check should reach?** (`g-141-0019`,
   `g-141-0020`, gap 3 above.) The answer decides a one-line change to `_has_second_cue` that
   widens the colour check on every tenant page. Please rule before anyone writes it.

6. **The v0.2.0 `label` pass twins rest on a reading of the label-in-name comparison.** All eleven
   name a control whose spoken name differs from its visible label by a typographic mark only.
   Both axe-core 4.13.0 and the W3C rule's algorithm treat that as a pass and this was verified in
   both directions — but it is one family of case standing for a checker's entire pass side,
   because the selection rule leaves very little else that can both differ and be correct. If you
   disagree with the reading, `label`'s scored sample goes back to failures only and the honest
   report for it is "not measurable", not a number.

7. **The 74 records of v0.2.0 were drafted by the same author as five of the six checkers.** That
   is the reason `graphics` has none, and it is a weaker version of the same problem for the five
   that do. Where a record's rationale reads as a description of what the checker looks for rather
   than of what the criterion requires, that is the tell, and it is worth marking.

---

## What v0.2 is not

- **Not expert-adjudicated.** See Status above. Until a human signs these off, scoring against
  them measures how often the checkers agree with a careful draft — not how often they are right.
- **Not independent of the system under test.** The 74 newest records were drafted by the author
  of five of the six checkers. On the clear cases that matters less than it sounds, which is why
  the pass is restricted to clear cases; it is still the single biggest reason not to publish
  anything computed from this.
- **Not blind re-labelled.** `relabel_agreement` is `null`. Spec §6: if round-one/round-two
  agreement comes in below 90%, stop and fix the labelling process before scoring anything.
- **Not a recall denominator for the whole app.** It labels the planted twins, not every
  candidate on every page. Recall here means "of the failures we planted, how many were found".
- **Not six checkers.** Five. `graphics` / 1.4.11 has no records — see "Not covered, and how to
  add it".
- **Not big enough to publish.** Every checker now clears the 30 the scorer requires, which makes
  the numbers *legitimate to look at internally* and nothing more. Spec §5 wants 50 per criterion
  for v1.0.

## Cross-references

- `../GOLDEN_DATASET_SPEC.md` — the specification (Doc B)
- `../PROVING_GROUND_APP_SPEC.md` — the fixture this labels (Doc A)
- `../harness/verify-plants.js` — asserts every planted defect and every clean twin
- `../harness/verify-golden.js` — asserts every label still resolves
- `../scorer/` — QA-10, the harness that consumes this
- `../../TASK_BACKLOG_QA.md` — QA-09, QA-10
