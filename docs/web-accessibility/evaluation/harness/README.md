# Meridian Library — verification harness

**Edvensoft-internal. This never ships with the app.**

Eight checks that the Meridian Library fixture still holds the defects the golden dataset was
labelled against, that nothing about it has drifted, and that every labelled element can actually
reach the checker it was labelled for.

## Why this is not in the app repository

It used to be. It was moved because the fixture gets onboarded as a brownfield project, and code
intelligence indexes what it finds there — `builtin.py` treats `.js` as source and `.json` as
context, and `codeintel_mcp.py` mines commit messages for "decision archaeology".

Every file here names a route, a criterion, and the verdict expected of it. Together they *are*
the answer key. Sitting in the app repository they would let an agent find the planted defects by
reading the tests instead of by examining the pages, and the measurement would be worth nothing.

**The app repository holds only what a real library application would hold. Anything that knows
the answers lives here.**

## Running it

```
npm install
npm run check
```

The app must be running first. Point the harness elsewhere with `MERIDIAN_APP` (checkout path)
and `MERIDIAN_URL` (base URL); the defaults are in `config.js`.

## What each one is for

| Command | Answers |
|---|---|
| `npm run contrast` | Does every colour pair still compute — including the one that has to keep failing? |
| `npm run axe` | Does each route report the rule it was built to trigger, **and nothing else**? |
| `npm run plants` | Is each planted case still in the page, and each twin still correct? |
| `npm run golden` | Does every answer-key record's `(route, selector)` still resolve on the page? |
| `npm run selectable` | Could each record ever *score*? See below — this is the subtlest of the eight. |
| `npm run counts` | Do the long pages still hold exactly 12 / 20 / 15 / 8 / 0 candidates? |
| `npm run journeys` | Do the interaction pages still behave as planted? |
| `npm run audit` | Leaks, external origins, determinism, duplicate ids, orphan views. |

`plants` and `journeys` exist because most of this fixture is built so a scanner stays **quiet** —
and quiet is also what a page returns once somebody tidies away the markup it was built around.
Without them, a page could lose its defect and every other check would still pass.

`axe` cuts both ways: a rule nobody planted means the page picked up a defect it was not meant to
have; silence where a failure was expected means the defect is gone. Both are bugs in the fixture.

### `selectable` — and why it is two questions, not one

`golden` proves a record still *resolves*. That is necessary and it is not enough: resolving is
about the page, and scoring is about the selection rules. A `pass` record only counts if the
checker actually selects the element, so a record can resolve perfectly and be permanently unable
to contribute a number in either direction. `scorer/selectable.py` carries the full reasoning.

Selection happens in **two steps**, and this check now reports them separately because they are
different problems with different fixes:

| What it says | What it means | Where the fix is |
|---|---|---|
| *collected, then declined by a rule* | A rule looked at it and said no. Often correct — sometimes a property of the criterion itself, in which case it belongs in `KNOWN_SHORTFALL` with its reason. | The answer key, or nowhere |
| *NEVER COLLECTED by the capture* | Nothing ever showed it to a rule. No rule declined it; nothing recorded that it existed. **Always a gap, and it fails the run.** | The `OFFER` list in `runner/companion/assets/a11y_audit.mjs` |

**The second answer only became possible on 31 August.** This check used to reach each recorded
element with `document.querySelector`, which finds anything on the page whether an audit would
collect it or not — so the one failure it could never see was an element the capture does not
offer, which is exactly the failure it exists to find. Three `structure` records had been in that
state for a whole live audit while every check here was green. It now imports the real `OFFER`
array from the companion's own audit script and compares **element identity**, so it can only ever
see what an audit would see.

## When a check disagrees with the build guide

The check is right about what the page does. Correct `PROVING_GROUND_BUILD_GUIDE.md`, unless the
page has picked up a defect the guide never asked for — then fix the page.

## Keeping the answer key out of the app

`audit.js` scans the app's **served** files for comments that name a defect. It deliberately does
not scan this folder, which is allowed to say anything. If you add a check here, keep it here.

**See also:** `../PROVING_GROUND_BUILD_GUIDE.md` (what each page is and why) ·
`../GOLDEN_DATASET_SPEC.md` (how these pages get labelled).
