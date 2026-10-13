# QA

This folder holds **two separate test packs**. They answer different questions, they are worked
through at different times, and you should not confuse them.

| Pack | The question it answers | Start here |
|---|---|---|
| **Greenfield test pack** | Does the product work, from signing up to a finished build? | [`GREENFIELD_TEST_PLAN.md`](GREENFIELD_TEST_PLAN.md) |
| **Bug-fix verification pack** | Do the fixes we have *already made* actually hold up in the app? | `QA_Bug_Fix_Testing.xlsx`, "How to use this sheet" tab |

Brownfield is **out of scope** for this cycle (still under active development).

---

## Pack 1 — Greenfield test pack

Everything the QA team needs to test the **greenfield** journey of the AI-First SDLC platform.

| File | What it is | Who touches it |
|---|---|---|
| [`GREENFIELD_TEST_PLAN.md`](GREENFIELD_TEST_PLAN.md) | The plan: scope, environment setup, test accounts, entry/exit criteria, the 3-person schedule, defect workflow | Read once at the start of the cycle |
| [`suites/`](suites/) | The test cases themselves — 15 suites, one Markdown file each | Read while testing; the source of truth for *what* to test |
| `Greenfield_Test_Execution_Tracker_V1.xlsx` | **Use this one.** The daily execution log — one row per test case, plus a Defects tab and a live Summary. Rebuilt on 2026-09-15 from the updated suites; everything logged in the original was carried into it | Filled in every day by each tester |
| `Greenfield_Test_Execution_Tracker.xlsx` | The original tracker, kept unchanged at the team's request. Superseded by V1 | Nobody — reference only |
| [`TEST_CASE_CONVENTIONS.md`](TEST_CASE_CONVENTIONS.md) | The format every test case follows, and the rules for writing new ones | Read before adding a case |
| [`FIXTURE_PROJECTS.md`](FIXTURE_PROJECTS.md) | The fixture projects the cases run against | Reference while testing |
| [`AUDIT_FINDINGS.md`](AUDIT_FINDINGS.md) | The QA-lead audit the pack was corrected against — why cases read the way they do, and the 15 product defects it turned up | Background; read if a case surprises you |
| `build_tracker.py` | Regenerates the tracker from the Markdown suites, carrying forward everything already logged. `--out <name>.xlsx` writes a new versioned workbook instead of overwriting (V1 was built with `--out Greenfield_Test_Execution_Tracker_V1.xlsx`) | Only when the suites change |

> **The pack was audited against the shipped source before release and the findings have been
> applied.** It grew from 212 cases to 253 (and to 256 on 2026-09-15, for the bug-fix batches): 40-odd cases asserted copy the app never renders or states
> it cannot reach, and the gaps that audit exposed became new cases. Two things changed that affect how
> you work rather than what you check — read §5 of the plan for both: **only one run can be active per
> work item**, and **a run that goes quiet is Blocked, not Failed**.

### The format, in one paragraph

Test cases live in **Markdown in the repo** (reviewable, diffable, version-controlled alongside the
code they test). Execution results live in a **single shared Excel tracker** (fast to fill in, easy
to see progress across three people, and it matches how `docs/Bugs.xlsx` is already used). The
Markdown says *what to test and how*; the Excel says *what happened, when, and by whom*. Never edit
a test case's steps in Excel — fix the Markdown and raise it in the standup.

### Day one — do this in order

1. Read [`GREENFIELD_TEST_PLAN.md`](GREENFIELD_TEST_PLAN.md) §2 (Environment) and get the stack running.
2. Create your test accounts per §3 (Test data and personas).
3. Open `Greenfield_Test_Execution_Tracker_V1.xlsx`, find the rows assigned to you in the **Owner** column.
4. Work your suites in ID order. Log every case — including the ones that pass.
5. Anything that fails: raise it on the **Defects** tab first, then put the DEFECT-ID in the test case row.

### The one rule that matters

**Every test case in this pack is executable by a human through the browser, with no database access, no
JWT decoding, and no API client.** If you hit a case you cannot execute from the UI alone, that is
itself a bug in the test pack — flag it rather than skipping it.

---

## Pack 2 — Bug-fix verification pack

| File | What it is | Who touches it |
|---|---|---|
| `QA_Bug_Fix_Testing.xlsx` | **239 rows** (211 at first release; 28 added on 2026-09-15 for the 4ac75f9 and b40c557 batches). Every fix written in code that has never been confirmed live by a QA member on a tenant account. Three tabs: how to use it, the cases, a coverage summary | Filled in by whoever runs the verification pass |
| `qa_bug_fix_testing/` | Regenerates that workbook — the procedures are authored as text there, not typed into Excel | Only when a procedure needs changing |

### Why this pack exists, and how it differs from pack 1

Pack 1 asks whether the product works. This one asks whether **a specific fix we already made**
holds up — so every row names the bug, the fix, and how to prove it by hand, and carries the
original `docs/Bugs.xlsx` S. No so results map straight back onto the register.

It exists because "Fixed" in the bug register has, until now, mostly meant *verified by tests, or by
a developer driving a browser* — not signed off by QA. Of 199 rows marked Fixed, about ten record a
confirmation from the team. This pack closes that gap in one pass.

Two differences from pack 1 that matter:

- **The rows are ordered by TEST PASS, not by number.** The 14 passes follow the real journey
  through the product, so one run through the lifecycle clears dozens of rows. Working in S. No
  order would mean building the same conditions over and over.
- **Not every row is a browser-only test**, so pack 1's "one rule" does not apply here. Each row
  states its own kind: `DIRECT` (drive it from the app now, 114 rows), `DURING A RUN` (a checkpoint
  while a phase or build runs, 81), `SET UP FIRST` (create a condition first — stop the app,
  restart the worker, delete a Jira issue — 40), and `DEV CHECK` (not reachable from the app at
  all, 4). A row you cannot execute is not a defect in the pack; mark it **Blocked** and say what
  you were missing.

### Regenerating it

```
.venv/Scripts/python.exe docs/qa/qa_bug_fix_testing/build.py
```

**Safe to re-run while testing is under way.** Anything a tester has typed — Status, QA Comment,
Tested By, Test Date — is read out of the existing workbook and written back, keyed on S. No, the
same way `build_tracker.py` preserves the greenfield tracker. If a logged result belongs to a row
the build no longer produces, the script **refuses to write** and names the rows rather than
silently discarding somebody's work.

Priority and Area are read live from `docs/Bugs.xlsx` every time, so they cannot drift away from
the register.
