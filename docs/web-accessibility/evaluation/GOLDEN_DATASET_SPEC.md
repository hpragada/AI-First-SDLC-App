# Golden Dataset — specification

**Doc B of two.** This is the *answer key*: the hand-labelled ground truth that tells us how often
the accessibility AI checkers are right. Doc A (`PROVING_GROUND_APP_SPEC.md`) is the application it
labels.

**Status (updated 2026-09-17): BUILT.** The golden set exists beside this spec in `golden/` — five
files, 173 labelled items (1.1.1 ×32, 1.3.1 ×37, 1.4.1 ×35, 2.5.3 ×42, 4.1.2 ×27) plus
`manifest.json` — and the harness and scorer are in `harness/` and `scorer/`. · **Delivers:** QA-09
(build the golden set) and QA-10 (the accuracy harness) · **Edvensoft-internal — never ships to a
tenant**

> ⚠️ **Checker names in this spec are the old spelling and match nothing in the code or the data.**
> They lost their hyphens and shortened during the build, and two checkers were added afterwards.
> The live names, used by both `backend/apps/a11y/checkers/rules.py` and the `golden/` files
> themselves, are:
>
> | This spec says | The code and the data say |
> |---|---|
> | `meaningful-alt` | **`alt`** |
> | `fake-semantics` | **`semantics`** |
> | `colour-only` | **`color`** |
> | `label` | `label` *(unchanged)* |
> | — | **`structure`** *(added later; appears in the 1.3.1 golden file)* |
> | — | **`graphics`** *(added later)* |
>
> So there are **six** checkers, not four. Take names and counts from the code, not from this page.

---

## 1. What this is for

Before these checkers go in front of a client, we need a number for how often they are right — and a
tripwire that stops a prompt or model change from quietly making them worse. That number needs an
answer key: a set of judgments an expert has made by hand, against which the machine's judgments can
be scored.

QA-09 states the stake plainly: *"the golden set must be trustworthy or the numbers it produces are
meaningless."* Everything in this document exists to protect that.

### The internal-only rule

Per QA-09's acceptance criteria and the note at the top of `../USER_JOURNEYS.md`, this dataset is
**Edvensoft's internal quality control**. It is not part of any tenant journey, never appears in the
platform UI, and is never stored in tenant data. A tenant does not create, import, or see one.

**Where it lives:** `docs/web-accessibility/evaluation/golden/` in **this** repository, with the harness entry
point (QA-10a) in code.

Note the split: the Proving Ground **application** is its own repository
(`edvensoft/a11y-proving-ground`) because M2 has to onboard it as a genuine brownfield project, and
because it gets deployed. The **dataset stays here**, where QA-09 wants it and where `make
a11y-eval` runs. They are versioned independently and reconciled by `app_version` (§7).

That split is also a safeguard. Anything in the app repo is visible to the judge; the answer key
must not be. Keeping them apart makes an accidental leak much harder.

Every file carries this header:

```
INTERNAL — Edvensoft accessibility evaluation data.
Not a tenant feature. Must never be read by tenant-facing code or written to tenant tables.
```

QA-09's third acceptance criterion is a code search proving no tenant-facing code references it.
Keep the directory name `golden/` stable so that search is a single, reliable grep.

---

## 2. The unit of labelling is a candidate, not a page

This is the correction that **R4** forces, and it is easy to get wrong.

The judge never sees a URL. Per the corrected design, the companion captures **candidate bundles**
(QA-11b) — an element, its screenshot, its accessibility-tree node, its surrounding context — and
ships them server-side, where `09c_a11y_judge` runs as a constrained agent through `ExecutionDriver`
and writes findings via `record_a11y_finding` (QA-02a).

So the pipeline is:

```
page  ──capture──▶  candidate bundle  ──judge──▶  finding
 │                        │                          │
 └── Doc A defines        └── THE GOLDEN SET         └── what QA-10 scores
     the page                 LABELS THIS                against the label
```

A page produces many candidates. Label the candidates.

### Candidate identity

A label is worthless if it cannot be matched back to the thing the judge saw. Identity is the
composite key:

```
(app_version, route, checker, selector)
```

- **`app_version`** — from the Proving Ground's `package.json`. Doc A §11 requires a bump on any
  page change, and the harness refuses to score a mismatched pair.
- **`route`** — the path from `routes.json`.
- **`checker`** — one of `alt`, `semantics`, `structure`, `color`, `label`, `graphics` *(this line
  originally read `meaningful-alt`, `fake-semantics`, `colour-only`, `label`; corrected 2026-09-17
  to the names the code and the `golden/` files actually use — see the note at the top)*. The same
  element can be a candidate for more than one checker and carries a separate label for each.
- **`selector`** — a stable CSS selector. **Author the pages with explicit `id`s on every labelled
  element** so the selector never depends on DOM position. `#cover-tidewater`, not
  `div.grid > article:nth-child(3) > img`. Positional selectors break the moment anyone adds a row.
  The `id` must be neutral — name the content, never the defect. `#cover-tidewater`, never
  `#bad-alt-1`.

> **This file is the only place the route → defect mapping exists.** Doc A §2 principle 4 forbids
> the app from naming its own defects anywhere, including in route names, because a URL is visible
> in the browser, in the screenshots the vision model receives, and on screen during a client demo.
> So `/catalogue/new-arrivals` looks like an ordinary page and only this dataset records that six
> covers on it carry meaningless alt text.
>
> The cost is real: your expert cannot read a URL and know what is planted there. They work from
> this file. That inconvenience *is* the safeguard — accept it rather than engineering around it.

---

## 3. Record schema

One JSON object per labelled candidate. One file per criterion, so a labelling session touches one
file and diffs stay readable.

```
docs/web-accessibility/evaluation/golden/
  1.1.1-non-text-content.json
  1.3.1-info-and-relationships.json
  4.1.2-name-role-value.json
  1.4.1-use-of-colour.json
  2.5.3-label-in-name.json
  manifest.json            app_version, dataset_version, counts, checksums
```

```json
{
  "id": "g-111-0042",
  "app_version": "1.4.0",
  "route": "/catalogue/new-arrivals",
  "selector": "#cover-tidewater",
  "checker": "alt",
  "criterion": "1.1.1",

  "truth": "fail",
  "expected_verdict": "fail",
  "difficulty": "clear",

  "rationale": "alt=\"cover\" conveys that the image is a cover but nothing about which book. A screen-reader user hears \"cover\" six times in a row on this page and cannot tell the titles apart. The title is not adjacent in the DOM.",
  "expected_fix_mentions": ["title", "author"],

  "labelled_by": "AV",
  "labelled_on": "2026-08-20",
  "relabel_verdict": "fail",
  "relabel_on": "2026-09-10",
  "adjudication": null,
  "anchor": "ACT 23a2a8 — image accessible name is descriptive"
}
```

| Field | Why it exists |
|---|---|
| `truth` | What is actually correct per WCAG 2.2. `pass` / `fail`. |
| `expected_verdict` | What a well-calibrated checker should **return**. `pass` / `fail` / `uncertain`. Usually equals `truth` — but see §4. |
| `difficulty` | `clear` / `borderline` / `ambiguous`. Lets QA-10 report accuracy on clear cases separately from hard ones. A checker at 95% on clear and 40% on borderline is a very different product from one at 78% flat. |
| `rationale` | The expert's reasoning, in prose. This is the most valuable field in the file — it is what makes a disputed label re-examinable in six months, and what a second labeller would be checked against. Never leave it blank. |
| `expected_fix_mentions` | Substrings a useful `suggested_fix` should contain. Lets the harness score fix quality crudely without a second model. Optional. |
| `relabel_verdict` | The blind re-label (§6). Disagreement with `truth` is a signal about the *label*, not the model. |
| `anchor` | An external reference — an ACT rule, a WAI technique — for contested calls. See §6. |

---

## 4. Three verdicts, and why the third one matters most

`truth` and `expected_verdict` are separate fields because on hard cases they diverge, and the
divergence is the point.

| Case | `truth` | `expected_verdict` | Reasoning |
|---|---|---|---|
| `alt="cover"` on a book cover | `fail` | `fail` | Unambiguous. |
| Descriptive alt, title not adjacent | `pass` | `pass` | Unambiguous. |
| Cover with full-title alt **immediately** beside the same title as text | `fail` | **`uncertain`** | Redundancy is a real harm; so is an unnamed cover. A confident verdict either way is over-claiming. |
| Photo of the library in a "Visit us" panel | `pass` | **`uncertain`** | Decorative or informative depends on authorial intent, which is not recoverable from the page. |

On an `ambiguous` record, **a checker that confidently answers `pass` is wrong even when `pass`
matches `truth`.** It got the right answer for the wrong reason and, more importantly, it did not
route to the SME. QA-06's triage and the whole gate design depend on the checker knowing when it
does not know. Scoring only against `truth` would reward exactly the behaviour that breaks the
product.

**Consequence for QA-10:** score against `expected_verdict`, and report calibration separately —
see §8.

---

## 5. Sizing

Per **R7 / D5**, the POC judges five criteria. The `semantics` checker produces verdicts on two
of them (1.3.1 and 4.1.2), so score per-criterion *and* per-checker.

### Why size matters more than it looks

With 20 true-fail samples, one miss moves recall by 5 points. With 50, one miss moves it by 2. QA-10
blocks a model or prompt promotion when accuracy drops below the last accepted number — so on a
small set, that gate fires on noise and the team learns to ignore it.

### Two tiers

**v0.1 — harness proving (100 records, 20 per criterion).** Enough to build QA-10, produce a first
baseline, and prove the plumbing. **Do not publish these numbers or gate on them.**

**v1.0 — release bar (250 records, 50 per criterion).**

| Criterion | Clear fail | Clear pass | Borderline | Ambiguous | Total |
|---|---|---|---|---|---|
| 1.1.1 | 18 | 18 | 8 | 6 | 50 |
| 1.3.1 | 18 | 18 | 8 | 6 | 50 |
| 4.1.2 | 18 | 18 | 8 | 6 | 50 |
| 1.4.1 | 18 | 18 | 8 | 6 | 50 |
| 2.5.3 | 18 | 18 | 8 | 6 | 50 |
| | **90** | **90** | **40** | **30** | **250** |

The near-50/50 fail/pass balance is deliberate. An unbalanced set lets a checker score well by
leaning one way — and "flag everything" is the failure mode a compliance tool falls into naturally.

### What the fixture supplies (measured 2026-08-20, app v1.3.0)

The tables above say what each tier *wants*. This one says what there is to label. **The binding
constraint is the fail side, not the total** — passing candidates are abundant (roughly 480 across
the app), so a criterion is limited by how many distinct failing elements exist for it.

| Criterion | Failing elements | v0.1 needs 10 | v1.0 needs 18 |
|---|---|---|---|
| 1.1.1 | 16 | ✓ | short 2 |
| 1.3.1 | 10 | ✓ | short 8 |
| 4.1.2 | 10 | ✓ | short 8 |
| 1.4.1 | 10 | ✓ | short 8 |
| 2.5.3 | 10 | ✓ | short 8 |
| | **56** | | **short 34** |

**v0.1 is fully supplied at a balanced 10 fail / 10 pass per criterion.** Seventeen failing
elements were added on 2026-08-20 to reach it — five `<td>` header cells on `/catalogue/subject-index`,
four switches on `/staff/shelf-audit`, seven buttons on `/account/card-services`, one rejected field
on `/help/report-a-problem`. Each has a passing twin, and `verify-plants.js` asserts both directions.

**v1.0 needs 34 more failing elements**, plus the 40 borderline and 30 ambiguous records against the
6 `uncertain` cases the fixture plants today. That is a page-building job before it is a labelling
job, and it has not been done.

> **Do not close the gap by labelling every candidate in the app.** It would give recall an honest
> denominator, but it also drags the set to roughly 56 fails against 480 passes — at which ratio any
> headline accuracy figure is meaningless, because answering `pass` to everything scores about 90%.
> Recall itself stays sound (it is computed over fails only), and precision gets harder and more
> honest; it is the single-number summary that stops meaning anything. Plant more failures instead.

### Be honest about the cost

At 3–5 minutes per record including a written rationale, 250 records is roughly **15–20 hours** of
expert time — and the blind re-label pass (§6) doubles it. That is real, and it is the schedule risk
in this whole workstream. Plan it as a named piece of work, not something that happens between other
things.

---

## 6. Labelling with one expert

QA-09 specifies two independent labellers with a third adjudicating disagreements. You have one
expert. That is workable, but the substitutes must be deliberate, because the two-labeller design
exists to stop one person's blind spot from becoming the ground truth — and with one labeller,
**every accuracy number inherits their individual judgment**, including its errors.

### Substitute 1 — blind re-label (intra-rater reliability)

The expert labels every record twice, **at least three weeks apart**, without sight of the first
pass. Practically: the harness emits a shuffled, label-stripped worksheet for round two.

- Agreement between rounds → the label is stable. Record `relabel_verdict` and move on.
- Disagreement → **the label is the problem, not the model.** Re-examine, rewrite the rationale, and
  usually reclassify the record's `difficulty` upward. A record the expert cannot label the same way
  twice is not a `clear` case.

Track the round-one/round-two agreement rate. **If it is below 90%, stop and fix the labelling
process before scoring anything** — you do not have ground truth yet, you have opinions.

This catches inconsistency. It does not catch systematic bias, and nothing available to you will.
Record that limitation in `manifest.json` so nobody later reads these numbers as more than they are.

### Substitute 2 — external anchoring for contested calls

Every `borderline` and `ambiguous` record must carry an `anchor`: an ACT rule id, a WAI technique
number, or a WCAG Understanding-document paragraph that supports the call. This puts an external
authority behind exactly the records where a single expert's judgment is weakest.

Where no anchor exists, say so explicitly (`"anchor": "none — judgment call, see rationale"`). That
is honest and re-examinable; a fabricated citation is neither.

### Substitute 3 — free pre-labelled data

W3C **ACT Rules** ship Passed / Failed / Inapplicable examples. Import them as a separate tier with
`labelled_by: "ACT"`. Two caveats, both important:

- ACT covers the **machine-decidable** rules — the axe half. The five AI criteria live in the
  judgment zone ACT deliberately avoids, so this supplements your set, it does not replace it.
- **Score ACT records separately.** They are not drawn from the Proving Ground and mixing them into
  headline precision/recall silently changes what the number describes.

### The adjudication field

`adjudication` stays `null` in the one-expert model. Leave it in the schema: when a second expert
exists, disputed records get a third opinion recorded there with no migration.

---

## 7. Versioning and invalidation

A label describes a candidate on a specific version of a specific page. Change the page and the
label may no longer describe anything.

**`manifest.json`:**

```json
{
  "dataset_version": "1.0.0",
  "app_version": "1.4.0",
  "generated_on": "2026-09-15",
  "counts": { "1.1.1": 50, "1.3.1": 50, "4.1.2": 50, "1.4.1": 50, "2.5.3": 50 },
  "relabel_agreement": 0.94,
  "notes": "Single-labeller dataset. See GOLDEN_DATASET_SPEC.md §6 for the limitation."
}
```

**Rules the harness enforces, refusing to run rather than warning:**

1. `manifest.app_version` must equal the running Proving Ground's `package.json` version. A mismatch
   is a hard stop — scoring against a changed app produces numbers that look fine and mean nothing.
   **This is why accuracy scoring runs against a local instance, not the deployed one.** The
   platform *can* scan a deployed URL (Doc A §3), and that is right for demos, the expert's manual
   review and the M2 audit — but a shared deployment can be redeployed or cached between labelling
   and scoring, and then the harness is measuring something other than what was labelled.
2. Every `(route, selector)` in the dataset must resolve on the running app. An unresolvable selector
   is a hard stop, not a skipped record — silently dropping records inflates every score.
3. Counts must match the manifest.

When the app changes, the affected records are **re-labelled, not migrated**. Bump
`dataset_version`, keep the old file in git history.

---

## 8. What the harness reports (QA-10)

Per **R6 / decision D4** there is no CI in this repository, so the harness runs locally via `make`
(QA-10a), not in a pipeline.

```bash
make a11y-eval
```

### Per checker and per criterion

- **Precision** — of the things it flagged, how many were real. Low precision means alert fatigue and
  a team that stops trusting the tool.
- **Recall** — of the real problems, how many it caught. Low recall means shipping inaccessible
  software while believing otherwise. **For a compliance feature, recall failures are worse.**
- **F1** — the headline, the gate number.
- Broken out by `difficulty`, because a flat number hides the shape.

### Calibration — reported separately

Because `expected_verdict` includes `uncertain`, two extra numbers matter:

- **Over-confidence rate** — records where `expected_verdict` was `uncertain` but the checker gave a
  confident `pass`/`fail`. These are the ones that bypass the SME queue and reach the gate on their
  own. **This is the most dangerous number in the report.**
- **Under-confidence rate** — records where the truth was clear but the checker said `uncertain`.
  Harmless to correctness, expensive in SME time. Watch the trend.

### Completeness — a separate, deterministic check

Distinct from accuracy, and per **R4** the more urgent of the two: silent under-reporting is *"the
worst possible failure"* for a compliance feature. Doc A §9's completeness pages have exactly known
candidate counts.

```
/catalogue/browse-all →  12 candidates in, 12 findings out   PASS
/staff/bulk-actions   →  20 candidates in, 17 findings out   FAIL — 3 candidates silently dropped
/about/terms          →   0 candidates in,  0 findings, no error
```

The expected count per route lives here, in `manifest.json`, **not** in the app — the page must not
advertise how many candidates it holds.

This needs **no labels**, runs in seconds, and is stable across model changes — so it can gate every
commit while the accuracy numbers move slowly. Build it first.

### Baselines and the promotion gate

QA-10 blocks promoting a new model or prompt if any checker's accuracy drops below the last accepted
figure. Two rules that keep that gate usable:

- **A new checker with no prior baseline records its first numbers as the baseline** rather than
  blocking (QA-10's stated edge case).
- **Give the gate a tolerance band.** On 50 records per criterion, ±2 points is sampling noise, not
  regression. A gate with no tolerance fires constantly and gets disabled — which is worse than no
  gate. Record the chosen band in the baseline file so it is a decision, not an accident.

---

## 9. How to make this dataset worthless

Worth stating plainly, because each of these has happened to somebody:

- **Leak the answer key into the app.** A class name, a comment, a data attribute, a suspiciously
  regular URL pattern. Doc A §3 forbids it; check it in review.
- **Label only easy cases.** 98% F1 on samples nobody would get wrong tells you nothing about
  production.
- **Let the model help you label.** The labels must be independent of the system under test. If an
  expert reviews the checker's output and ticks "yes, agree", that is not ground truth — it is
  measuring the model against itself. Label first, then look.
- **Silently drop unresolvable records.** Each dropped record inflates every score. §7 rule 2 makes
  it a hard stop for exactly this reason.
- **Publish v0.1's numbers.** 20 records per criterion has confidence intervals wide enough to drive
  through. Mark them internal-only and mean it.
- **Score ambiguous records against `truth`.** Rewards the over-confidence that breaks the SME queue.

---

## 10. Build order

1. `golden/` directory, headers, `manifest.json`, and the schema — no records yet.
2. **Completeness check** (§8). No labels needed, immediate value, gates every commit.
3. ACT import as its own tier — free, and it exercises the harness's file reading.
4. **v0.1**: 20 records per criterion, `clear` only, from Doc A §7's fail/pass pairs. Baseline the
   harness. Do not publish.
5. Blind re-label round on v0.1 (three weeks later). **Check the agreement rate before going
   further** — if the process is unsound, better to learn it at 100 records than at 250.
6. **v1.0**: grow to 50 per criterion, adding borderline and ambiguous records with anchors.
7. Blind re-label round on the new records. Publish `relabel_agreement` in the manifest.
8. Set baselines and the tolerance band; turn on the promotion gate (QA-10 → unblocks QA-22).

Steps 1–3 need no accessibility expertise at all. Start them immediately; they run in parallel with
the expert's work on Doc A §7 and with M1's build.

---

## Cross-references

- **The application this labels:** `PROVING_GROUND_APP_SPEC.md` (Doc A).
- **Corrections that shaped this spec:** `../RESEARCH_CORRECTIONS.md` — R4 (candidate bundles;
  write-completeness), R6 (no CI, local `make` harness), R7 (five criteria).
- **Tasks delivered:** `../TASK_BACKLOG_QA.md` — QA-09, QA-10, QA-10a; unblocks QA-22.
- **Why the golden set is internal:** `../USER_JOURNEYS.md`, opening note.
