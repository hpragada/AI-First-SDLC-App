# Test Case Conventions

Every test case in [`suites/`](suites/) follows this exact shape. The execution tracker is generated
by parsing these files, so the metadata table must not drift.

## The template

```markdown
### TC-042 · Signup rejects a password under 8 characters

| Field | Value |
|---|---|
| Suite | TS-01 Identity & Access |
| Type | Functional |
| Priority | High |
| Screen | `/signup` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- Not logged in (use a private/incognito window).

**Steps**
1. Go to `http://localhost:5173/signup`.
2. Enter Full name `QA Tester`, Work email `qa+short@edvensoft.com`, Password `Short1`,
   Workspace / org name `Short Pass Co`.
3. Click **Create workspace**.

**Expected**
- The form does not submit and no workspace is created.
- A validation error appears against the Password field.
- The page heading is still `Create your workspace`.

**Pass / Fail**
- PASS if the submission is blocked and an error is shown against the password field.
- FAIL if the workspace is created, or the error is generic/absent, or the app shows a raw 400.

**Test data**
- Password: `Short1` (6 chars)

**Notes**
- The backend only enforces a minimum length of 8. Django's stronger password validators are
  configured but not called — a weak-but-long password like `password` is expected to be accepted
  today. Do not raise that as a functional failure here; it is tracked separately.
```

## Field rules

| Field | Allowed values |
|---|---|
| **Suite** | `TS-01` … `TS-15`, with the suite title. Must match the file it lives in. |
| **Type** | `Functional` (UI, single screen) · `E2E` (multi-screen journey) · `Negative` · `Permission` (role/access) · `UX` (state, copy, empty/loading/error rendering) |
| **Priority** | `Critical` · `High` · `Medium` · `Low` — see the severity ladder in the plan |
| **Screen** | The route(s) under test, e.g. `/gates`, `/work-items/:id` |
| **Persona** | The persona ID from the plan (`P1`–`P9`), or `Any` |
| **Automation** | `Yes` if it is deterministic and needs no human judgement, `No` otherwise |

## Writing rules

1. **UI-observable oracles only.** An Expected Result must be something a tester can *see*. "The
   run row shows status `Awaiting gate`" is good. "The `Run.status` column is `awaiting_gate`" is
   not — that belongs in a Notes line, not an assertion.
2. **Reach the starting state through the product.** "Log out and sign in as P8 Engineer", never
   "clear localStorage" or "revoke the session in the DB".
3. **Exact strings.** Quote button labels, headings, and error copy exactly as the app renders them
   (`**Create workspace**`, `` `Awaiting {role}` ``). QA verifies copy too.
4. **One behaviour per case.** If the Expected list has an "and also" that could pass or fail
   independently, split it.
5. **Every Critical/High feature needs a happy path, a negative path, and a boundary/permission
   case.** Medium gets happy + negative. Low gets happy only.
6. **Say when a known limitation is expected.** Put it in Notes so the tester does not raise a
   duplicate defect against something already tracked.

## Adding a new case

Append to the end of the relevant suite file with the next free ID **in that suite's range** (the
ranges are listed in the plan). Then re-run the tracker generator:

```bash
python docs/qa/build_tracker.py
```

This regenerates `Greenfield_Test_Execution_Tracker.xlsx`. It **preserves existing execution
results** by TC-ID — new cases are appended as blank rows, and nobody's logged results are lost.
