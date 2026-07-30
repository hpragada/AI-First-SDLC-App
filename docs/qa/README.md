# QA — Greenfield Test Pack

Everything the QA team needs to test the **greenfield** journey of the AI-First SDLC platform.
Brownfield is **out of scope** for this cycle (still under active development).

## What's in here

| File | What it is | Who touches it |
|---|---|---|
| [`GREENFIELD_TEST_PLAN.md`](GREENFIELD_TEST_PLAN.md) | The plan: scope, environment setup, test accounts, entry/exit criteria, the 3-person schedule, defect workflow | Read once at the start of the cycle |
| [`suites/`](suites/) | The test cases themselves — 15 suites, one Markdown file each | Read while testing; the source of truth for *what* to test |
| `Greenfield_Test_Execution_Tracker.xlsx` | The daily execution log — one row per test case, plus a Defects tab and a live Summary | Filled in every day by each tester |
| [`TEST_CASE_CONVENTIONS.md`](TEST_CASE_CONVENTIONS.md) | The format every test case follows, and the rules for writing new ones | Read before adding a case |
| [`AUDIT_FINDINGS.md`](AUDIT_FINDINGS.md) | The QA-lead audit the pack was corrected against — why cases read the way they do, and the 15 product defects it turned up | Background; read if a case surprises you |

> **The pack was audited against the shipped source before release and the findings have been
> applied.** It grew from 212 cases to 253: 40-odd cases asserted copy the app never renders or states
> it cannot reach, and the gaps that audit exposed became new cases. Two things changed that affect how
> you work rather than what you check — read §5 of the plan for both: **only one run can be active per
> work item**, and **a run that goes quiet is Blocked, not Failed**.

## The format, in one paragraph

Test cases live in **Markdown in the repo** (reviewable, diffable, version-controlled alongside the
code they test). Execution results live in a **single shared Excel tracker** (fast to fill in, easy
to see progress across three people, and it matches how `docs/Bugs.xlsx` is already used). The
Markdown says *what to test and how*; the Excel says *what happened, when, and by whom*. Never edit
a test case's steps in Excel — fix the Markdown and raise it in the standup.

## Day one — do this in order

1. Read [`GREENFIELD_TEST_PLAN.md`](GREENFIELD_TEST_PLAN.md) §2 (Environment) and get the stack running.
2. Create your test accounts per §3 (Test data and personas).
3. Open `Greenfield_Test_Execution_Tracker.xlsx`, find the rows assigned to you in the **Owner** column.
4. Work your suites in ID order. Log every case — including the ones that pass.
5. Anything that fails: raise it on the **Defects** tab first, then put the DEFECT-ID in the test case row.

## The one rule that matters

**Every test case here is executable by a human through the browser, with no database access, no
JWT decoding, and no API client.** If you hit a case you cannot execute from the UI alone, that is
itself a bug in the test pack — flag it rather than skipping it.
