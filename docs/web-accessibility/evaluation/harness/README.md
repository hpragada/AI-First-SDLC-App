# Meridian Library — verification harness

**Edvensoft-internal. This never ships with the app.**

Six checks that the Meridian Library fixture still holds the defects the golden dataset was
labelled against, and that nothing about it has drifted.

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
| `npm run counts` | Do the long pages still hold exactly 12 / 20 / 15 / 8 / 0 candidates? |
| `npm run journeys` | Do the interaction pages still behave as planted? |
| `npm run audit` | Leaks, external origins, determinism, duplicate ids, orphan views. |

`plants` and `journeys` exist because most of this fixture is built so a scanner stays **quiet** —
and quiet is also what a page returns once somebody tidies away the markup it was built around.
Without them, a page could lose its defect and every other check would still pass.

`axe` cuts both ways: a rule nobody planted means the page picked up a defect it was not meant to
have; silence where a failure was expected means the defect is gone. Both are bugs in the fixture.

## When a check disagrees with the build guide

The check is right about what the page does. Correct `PROVING_GROUND_BUILD_GUIDE.md`, unless the
page has picked up a defect the guide never asked for — then fix the page.

## Keeping the answer key out of the app

`audit.js` scans the app's **served** files for comments that name a defect. It deliberately does
not scan this folder, which is allowed to say anything. If you add a check here, keep it here.

**See also:** `../PROVING_GROUND_BUILD_GUIDE.md` (what each page is and why) ·
`../GOLDEN_DATASET_SPEC.md` (how these pages get labelled).
