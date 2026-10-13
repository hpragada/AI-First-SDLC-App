# The accuracy harness

**Edvensoft-internal. Never a tenant feature.** Delivers **QA-10a** (the way to run it) and
**QA-10** (the scoring itself).

> **These numbers are our report card. They decide nothing for a client.**
> Nothing in the platform reads this harness's output. It reads the platform's own audit
> records, writes a file we look at, and stops there. What decides whether anything blocks a
> client's work is the client's own accessibility policy, which they set themselves
> (`../../TASK_BACKLOG_QA.md`, D-A11Y-82).

---

## Running it

```
make a11y-eval                                    # the latest finished audit
make a11y-eval ARGS="--run <audit-id>"            # a specific one
make a11y-eval ARGS="--completeness-only"         # counting only — needs no answer key
make a11y-eval ARGS="--dry-run"                   # print everything, write nothing
make a11y-eval-test                               # unit tests: no database, no platform
```

There is no CI in this repository — no pipeline of any kind — which is why this runs through
`make` and is a task of its own (decision D4).

**Exit codes mean different things:**

| Code | Meaning |
|---|---|
| `0` | nothing to report, or nothing measurable yet |
| `1` | a check got worse than last time — **our** release is blocked, never a client's work |
| `2` | something was dropped between being on the page and getting an answer |

---

## The two halves, and why one comes first

### Completeness — counting. Needs no answer key.

Follows every element through two transitions, and they fail for completely different reasons:

```
expected  ──►  captured  ──►  judged
   │              │              │
   │              │              └─ lost here: the run hit its ceiling, or judging stopped
   │              │                 early. A coverage problem.
   │              └─ lost here: nothing offered it to any check at all. This is what put
   │                 "checked" on a page whose only failure was never looked at.
   └─ how many candidates the page is known to hold, from the golden set's manifest.json —
      never from the page itself, which must not advertise how many problems it has.
```

Runs in seconds, needs no labels, and does not move when the model changes. **Build and trust
this before any accuracy figure**, because it tells the difference between *"the check got it
wrong"* and *"the check was never shown it"* — which look identical on a scorecard and need
opposite responses.

**It reads the list; it does not weigh the bag.** The manifest gives a count per page, and for a
long time a count was all this compared — so a page could capture twenty-nine of the wrong things,
miss every one of the eleven the answer key names, and print `ok`. It did exactly that on
1 September, on the same run where the accuracy half reported eleven of that page's records as
never looked at. The key names route, selector and checker for every record it holds, so those
names are now ticked off one at a time and a page reports **which** expected elements never
reached their check:

```
/staff/exports   expected  ?  captured 19  judged 19   named in the answer key and never offered to its check
     missing: #open-exports [semantics]
```

The counts remain, for pages the manifest numbers without naming anything. Both comparisons are
optional and independent: with no answer key at all this is still captured-against-judged, which
is why it works on any run of any application from day one.

### Accuracy — needs an answer key.

Per check, per source: precision, recall, F1, and the calibration figures.

---

## Three states, not two — and the sample line says which

A record can reach this harness in three conditions, and for a long time the middle one was
invisible:

| | What happened | How it scores |
|---|---|---|
| **asked** | the question went to the AI | scored |
| **settled by rule** | the criterion's own wording made the answer a matter of fact, so the platform answered it and paid nothing | **scored, exactly the same way** |
| **out of scope** | the criterion cannot be asked about this element at all | not an answer; reported as a silence |

The middle row is why the sample line reads:

```
label (golden) — scored on 40 records — 20 answered by the check, 20 settled by rule
```

**Both are decisions and both are scored**, because what a client experiences is the platform's
answer, not the AI's — and an answer reached by rule is still correct and costs nothing. The split
is printed so nobody mistakes one kind of work for the other.

**This is what keeps a rule honest.** Its answer is compared against the answer key like any
other, so a rule that ever clears something the key calls a failure is recorded as a miss. On the
first run it caught itself: a button reading *"Renew"* announced as *"Renew all loans"* passes the
letter of 2.5.3, and the key says a person should weigh it — the name widens what the visible word
promised. That is reported as

```
of those, 1 was settled by RULE, not by the check — narrow the rule, do not re-prompt the model
```

because the two have different remedies.

**The rule is read from `apps.a11y.checkers.rules`, never re-implemented here.** A second copy
would agree with the first by construction and the comparison would stop meaning anything — the
same trap `check_app_version` exists to avoid.

---

## Recording a caveat: `--note`

```
make a11y-eval APP_VERSION=1.4.0 ARGS="--note 'structure 0.833 is contested, see §9.27.C'"
```

Whatever you pass is stored in the results file for that run. A figure can be correct and still
not settled, and **a number that outlives the reason for it gets read months later as a settled
fact.** The caveat travels in the file rather than in somebody's memory of the day it was written.

---

## What this refuses to do

Each of these, done the obvious way, produces a number that looks right and is not.

**It never scores against `truth`.** It scores against `expected_verdict`. On a genuinely
arguable element the right answer is *"I am not sure"* — a check that answers confidently there
got the right answer for the wrong reason and skipped the human review queue. Scoring against
truth would reward exactly the behaviour that breaks the product.

**It never computes recall from live review verdicts.** Those only exist for findings we
already raised, so the denominator would be *"things we found"* — precision wearing recall's
name. It reports `unmeasured` instead. Only the golden set can say what we stayed silent about.

**It never reads a silence as a pass.** An element nobody looked at has no verdict. Counting
that as "the check said it was fine" would turn every gap in coverage into a free correct
answer.

**It never adds the two sources together.** A precision figure from live review and one from a
fixed answer key are different claims about the world.

**It never prints a number it does not have.** With no answer key at all it says so and stops.

---

## The two silences

The distinction that makes this worth building:

| | What happened | How it scores |
|---|---|---|
| **Captured, never judged** | the run hit its ceiling of 200, or stopped early | **excluded from every figure** and reported as coverage — the run was incomplete, not inaccurate |
| **Never captured** | nothing offered it to any check | **counts against us**: a real failure nobody looked at is a miss, and it gets its own line, because its fix is nowhere near the model |

A silence never earns credit. Where the answer key says an element should have passed and we
never looked at it, we get no point for a right answer we did not give.

### …and the second silence has two causes, which `selectable.py` now separates

Selection is two steps: the capture **collects** everything matching the companion's `OFFER`
list, then the platform's rules decide what to **claim**. Something that never reaches a checker
failed at one of those steps, and which one decides where the fix goes:

| | What it means | Where the fix is | Does it fail the run? |
|---|---|---|---|
| **collected, then declined** | a rule looked and said no | the answer key, or nowhere — sometimes it is a property of the criterion (`KNOWN_SHORTFALL`) | no |
| **never collected** | nothing ever showed it to a rule | the `OFFER` list in `runner/companion/assets/a11y_audit.mjs` | **yes** |

**They read identically until 31 August, and the cost of that was hidden by the asymmetry.** An
expected-`fail` record counts toward a checker's ceiling whether or not anything reaches it — so
`structure` reported a reachable sample of 30 while 3 of its 15 failure records could never be
found by any judge, capping its recall at 80%. Nothing said so, because `verify-selectable.js`
reached each element with `document.querySelector` and reported all three as selectable. Both
halves are fixed; the harness README has the detail.

---

## The gate

Blocks **shipping a changed prompt or model of ours**. Never a client's work.

- **No stored numbers means record, not fail.** A first run has nothing to regress against.
- **There is a tolerance band.** On fifty records a two-point move is sampling noise. A gate
  with no tolerance fires constantly and gets switched off, which is worse than no gate.
- **Too small a sample never gates, either way.** Below the minimum a check reads as *not yet
  measurable* — never as passing, and never as having regressed.
- **A check that got worse has the worse number written down.** Keeping the flattering old one
  is how "proven once" quietly becomes "trusted forever".

Both the minimum sample and the tolerance live in `baseline.json`, so changing either is an
edit to a decision record rather than a code change nobody sees.

---

## Files

| File | What it does |
|---|---|
| `run.py` | the entry point — arguments, orchestration, what gets printed |
| `completeness.py` | the counting check |
| `accuracy.py` | precision, recall, F1, calibration. Pure arithmetic |
| `labels.py` | reads the golden set; refuses to run on one that does not add up |
| `baseline.py` | the stored numbers, the tolerance band, and the gate |
| `platformdata.py` | **the only module that touches the platform.** Read-only, always |
| `selectable.py` | could each record ever *score*? Run from `../harness/verify-selectable.js` |
| `tests/` | 41 tests, no database, no Django |

The platform is imported, not re-implemented: `merge_run` already returns every element of a
run with what each check said about it, **including the passes**. A scorer that went looking for
findings instead would count every genuine miss as correct, because a finding is only ever
written when something is broken.

---

## Two things to know before labelling

**The names for the checks differ between the spec and the code.** The dataset spec says
`meaningful-alt` / `fake-semantics` / `colour-only` / `label`; the platform's stored verdicts
say `alt` / `semantics` / `color` / `label`. `labels.py` translates, and either set of names
works. Left untranslated, no label would have joined to any verdict and the report would have
announced that the checks found nothing at all.

**Every labelled element needs its own `id`.** Without one the platform records the element by
its position on the page — *"the second row inside the loans table"* — and that breaks the
moment anyone adds a row. It does not break loudly: the label starts pointing at a different
element and the score stays plausible. Name the content, never the defect: `#loan-row-tidewater`,
not `#bad-colour-1`.

---

## See also

- `../GOLDEN_DATASET_SPEC.md` — what the answer key is and how it gets built (QA-09)
- `../harness/` — a **different** harness: six checks that the Meridian fixture still holds the
  defects it was built to hold. It knows nothing about accuracy, the platform, or the AI
- `../../TASK_BACKLOG_QA.md` — QA-09, QA-10, QA-10a and the decisions behind them
