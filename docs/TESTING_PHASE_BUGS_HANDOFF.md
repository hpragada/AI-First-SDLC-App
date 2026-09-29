# Testing Phase (09_testing) — Bug Handoff Brief

**Status:** **CLOSED** — all four bugs resolved in `e70fd9e`, plus the publishing drift (see the
status note below) · **Written:** 2026-07-17 · **Closed:** confirmed 2026-09-17

> The header said `open` until 2026-09-17 while the note immediately below it said every bug was
> resolved. The note was right; the header had simply never been changed.

> **Status note (2026-09-15).** The brief below is kept as written. Since then:
> - **Bugs 1–4 are resolved** in commit `e70fd9e` ("Testing phase: wire the test loop + fix the 4
>   handoff bugs", 2026-07-17). The agent now stages one body per test case
>   (`agents/09_testing/agent.md`, Output table), each registration emits an
>   `artifact.registered` progress event (`mcp_platform_state/tools.py`), and an empty phase
>   document is caught before a gate opens (`backend/orchestration/activities.py`, `phase.empty_result`).
> - **The "publishing is manual" drift is resolved:** the agent body now says a reviewer triggers
>   the export after the gate, which matches the code.
> - **S.No 132** (`sdlc/build` check stuck at pending) is resolved in commit `4ac75f9` — the check
>   now finishes as success or failure.
> - **09_testing is now planning-only** (S.No 85, `4ac75f9`): it writes the test plan and cases and
>   never registers a `test_report`; Test Automation (09b) runs the tests and produces the only one.

This brief is self-contained: it carries the evidence, root causes, and acceptance criteria so you
can act without the originating chat session.

---

## 0. Context — how to reproduce / inspect

A single `09_testing` phase run produced everything described below. **It is still parked at its
gate — do not approve it until you have decided on Bug 1**, since approving publishes bad data to
the test-management system of record.

| Item | Value |
|---|---|
| Run id | `b0e6557b-10ce-4adb-8e40-9591c46fcbae` |
| Workflow | `agent-run-b0e6557b-10ce-4adb-8e40-9591c46fcbae` |
| Agent | `09_testing` (`agents/09_testing/agent.md`), engine `claude-sonnet-4-6` |
| Tenant | `212395b8-f118-4eef-93eb-ba2c45468226` |
| Project | SpendLog (`6d4ea6d3-2744-453c-8c74-09435cbd9300`) |
| Run status | `awaiting_gate` (`phase_gate` = PENDING) |
| Produced | **90** `test_case` · 1 `test_plan` · 1 `test_report` · 1 `testing` · 1 `assumption` |
| Duration | dispatched 1:31:54 PM → reported 1:56:11 PM (~25 min) |

Inspect anything with (RLS requires the tenant GUC):

```bash
docker exec sdlc-platform-backend-1 python manage.py shell -c "
from django.db import connection
with connection.cursor() as c:
    c.execute(\"select set_config('app.tenant_id','212395b8-f118-4eef-93eb-ba2c45468226',false)\")
from apps.registry.models import Artifact
from apps.runs.models import Run
from mcp_platform_state.tools import get_artifact_body
r=Run.objects.get(id__startswith='b0e6557b')
a=Artifact.objects.filter(run_id=r.id, type='test_case').first()
print(a.title); print(get_artifact_body('212395b8-f118-4eef-93eb-ba2c45468226', str(a.id))['body'][:500])
"
```

**What worked (do not regress):** test-case *authoring* correctly derives from the PRD /
user_stories / acceptance criteria and does **not** require the implementation to be complete.
This run authored 90 test cases against a largely unimplemented app — that is by design (see the
agent's `## Inputs`). It also correctly gap-scanned the missing code into an `assumption` artifact
instead of blocking.

---

## Bug 1 — 90 test-case artifacts share only 4 bodies (each shows ~25 unrelated test cases) — **P1**

### Symptom
Opening any one `test_case` artifact in the UI displays a large batch of *other* test cases, not
just its own.

### Evidence (verified)
- 90 `test_case` artifacts → **4 distinct `s3_key`s / 4 distinct `content_hash`es**.
- Artifact `TC-SEC-001 — Unauthenticated access to all protected endpoints → 401` has a body of
  **22,938 chars containing 25 distinct TC ids** (`TC-ACC-001`, `TC-ACC-002`, …).
- The batch filenames give it away:

| Batch body (`.../testing/<file>`) | # artifacts pointing at it |
|---|---|
| `tc-perf-security-acc-e2e.md` | 30 |
| `tc-auth-001-023.md` | 23 |
| `tc-expense-024-044.md` | 21 |
| `tc-dashboard-nav-val-045-060.md` | 16 |

### Root cause
The agent staged **one markdown file per category** (~16–30 test cases per file) via
`stage_artifact_body`, then called `register_artifact` 90 times pointing every artifact at the 4
shared batch files. The registry is correct (1 artifact per TC, titles are right); the **bodies**
are batched.

`agents/09_testing/agent.md` says *"Register each test case as a `test_case` artifact… link it to
the requirement it verifies"* — one artifact per TC — but it never says **one body per test case**,
so batching is not actually prohibited by the body.

### Impact
1. UI: opening TC-001 shows 25 test cases (the reported symptom).
2. **Xray export is the real damage.** `backend/integrations/export_tests.py::parse_test_case`
   parses an artifact body into `(summary, steps)` for `testmgmt.create_test`. Fed a 25-TC batch it
   will produce garbage/duplicate Xray issues. **Approving the gate and exporting will pollute the
   system of record** — this is why the gate is still pending.
3. Traceability: `add_trace_edge (rel: tests)` per TC points at a body that isn't that TC.

### Fix direction
Make the agent stage **one body per test case** (`.../testing/tc-auth-001.md`) so each
`test_case` artifact has its own `s3_key`/hash. Two options:
- **(a) Agent-body fix (preferred, ~15%-bucket edit per `/docs/AGENT_MIGRATION_SPEC.md`):** state
  explicitly in `agents/09_testing/agent.md` Step 5 that each test case gets its **own staged body**,
  one `stage_artifact_body` per `register_artifact`, never a batch file.
- **(b) Platform guard:** reject/flag a `register_artifact` for `type="test_case"` whose `s3_key` is
  already claimed by another test_case in the same run — fail loud rather than silently sharing.

Consider doing both: (a) fixes intent, (b) prevents regression.

### Acceptance criteria
- A fresh `09_testing` run yields `count(distinct s3_key) == count(test_case artifacts)`.
- Opening any test_case in the UI shows exactly one TC.
- `parse_test_case` on any test_case body yields that TC's summary + steps only.

---

## Bug 2 — Test cases are engineer-facing; a manual QA cannot execute or verify them — **P2**

### Symptom
Reported: *"The test case details are very high level and a Manual QA cannot understand and verify."*
Example produced by the run:

```
TC-001: Register new account — happy path (full payload)
Type: Integration | Priority: Critical | Automation Candidate: Yes
Test Steps
  1. POST /api/v1/auth/register with body {"name": "TC User One", ...}
Expected Result
  HTTP 201 … Decoded access_token has type:"access" and exp ≈ issued_at + 1800.
  User record in DB has is_active = true.
Pass/Fail Criteria
  PASS if: status=201, both tokens present, user is_active=true in DB
```

### Evidence — the real defect is the **type mix**, not the template
Type distribution across all 90 test cases:

| Type | Count |
|---|---|
| Integration | **45** |
| E2E | 20 |
| Security | 9 |
| Accessibility | 8 |
| Performance | 6 |
| Unit | 1 |
| **Functional** | **1** |

**Only 1 of 90 is `Functional`** — the type a manual QA would execute through the UI.

### Root cause (important nuance — read before "fixing" the template)
The produced test case **does conform to the agent's own template** in
`agents/09_testing/agent.md` (Preconditions / Test Steps / Expected Result / Pass–Fail Criteria /
Test Data / Automation Notes are all present, with exact values). **This is not a compliance
violation.** Two genuine gaps:

1. **Type mix:** nothing in the agent body requires a manual-executable **Functional/UI** suite, so
   the agent chose API-level `Integration` for half the suite. For `Type: Integration`, "POST
   /api/v1/auth/register" *is* the correct precise action — it's just not manual-executable.
2. **Unverifiable oracles:** `Expected Result` / `Pass–Fail Criteria` depend on **decoding a JWT**
   and **direct DB assertions** (`user is_active = true in DB`). A manual tester cannot perform
   either. The template's "two engineers would reach the same verdict" bar is met; a **manual QA**
   bar is not.

### Fix direction
Decide the intended audience first — this is a **product decision, not a bug fix**:
- If the Testing phase must serve manual QA: amend `agents/09_testing/agent.md` Step 5 to require a
  **Functional/UI test case per user-facing acceptance criterion**, with browser-level steps
  (navigate → enter field → click → observe) and **UI-observable** expected results; restrict
  DB/JWT assertions to `Integration`-type cases.
- If the phase is automation-first, then the mix is arguably correct and the real gap is that the UI
  doesn't communicate that these are engineer-facing specs.

### Acceptance criteria (if manual QA is in scope)
- Every user-facing acceptance criterion has ≥1 `Type: Functional` test case whose steps are
  UI actions and whose Expected Result is observable in the UI with no DB/JWT access.

---

## Bug 3 — Phase console shows nothing for ~25 minutes while the agent works — **P2**

### Symptom
The run console (screenshot) shows only:

```
1:31:51 PM  Run triggered — companion
1:31:54 PM  Phase dispatched — testing
            ←—— 25 minutes of total silence ——→
1:56:11 PM  Phase reported
1:56:14 PM  Run executed
1:56:14 PM  Phase empty result — …
```

During that 25-minute gap the agent staged 4 bodies and registered **90 artifacts**. None of it
appears. The user cannot tell whether the run is working, stuck, or dead — which previously led to
killing/re-triggering healthy runs.

### Root cause
Only **orchestrator-level** events are written to the ledger (`tools.log_event` in
`backend/orchestration/activities.py`). The agent-driven MCP calls — `register_artifact` and
`stage_artifact_body` in `mcp_platform_state/tools.py` — do **not** log a ledger event, so nothing
reaches the run's event stream between `phase.dispatched` and `phase.reported`.

### Fix direction
Emit a progress event per artifact registration (e.g. `artifact.registered` with
`{type, title}`) from `register_artifact`, so the console streams
`Registered test_case — TC-001 — Register new account`. Throttle/batch if 90 events is too chatty
(e.g. one event per N, or a periodic `phase.progress` heartbeat with a running count). Keep it
append-only and tenant-scoped like every other event.

### Acceptance criteria
- A long phase run shows incremental progress in the console while the agent works.
- The gap between `phase.dispatched` and `phase.reported` contains at least periodic progress
  events.

---

## Bug 4 — `phase.empty_result`: the phase document is empty — **P2**

### Symptom
Console line: *"Phase empty result — companion reported ok but the engine returned no final text;
the staged phase draft is empty"*.

### What it means (this is the platform working correctly)
Emitted by `backend/orchestration/activities.py:388`. The companion reported `status=ok`, but the
engine returned **no final text**, so the phase's own document was staged empty. The platform
deliberately logs this rather than hiding a blank preview at gate time.

### Evidence
The `testing` artifact for this run:
- `title` = `""` (empty)
- `content_hash` = `sha256:e3b0c44298fc…` — **the SHA-256 of the empty string** (verified)
- `s3_key` = `…/testing/testing.md`

### Root cause (probable — confirm)
Max-turns. The agent spent its entire turn budget authoring/registering 90 test cases and never
wrote its final phase document. Note this run produced a `test_plan` and a `test_report` (both with
real bodies), so the *deliverables* exist — it's the phase summary doc that's empty.

Two sub-defects:
1. The **phase doc is empty** → the human is asked to approve a phase with a blank preview.
2. The `testing` artifact was registered with an **empty title** (related to the earlier
   "register_artifact must take a title" work, Bugs S.No 120) — it should never be titleless.

### Fix direction
- Detect the empty phase document **before** opening the gate and either fail the run with a clear
  reason or re-prompt the engine for its summary; don't open a gate on an empty draft.
- Ensure the phase doc always gets a non-empty title.
- Consider raising max-turns for `09_testing`, or having the agent write the phase document
  **first** and register test cases after, so a turn exhaustion loses the least valuable output.

### Acceptance criteria
- A phase run cannot reach `awaiting_gate` with an empty (`sha256:e3b0c…`) phase document.
- The phase artifact always has a non-empty title.

---

## Cross-cutting notes for whoever picks this up

- **Do not approve run `b0e6557b`'s gate** until Bug 1 is resolved — approval → Xray export →
  polluted system of record.
- **Agent edits** must follow `/docs/AGENT_MIGRATION_SPEC.md` (75/15/10 buckets). Bugs 1 and 2 are
  agent-body edits; Bugs 3 and 4 are platform edits.
- **Publishing is manual, not gate-triggered.** `agents/09_testing/agent.md` claims *"On gate
  approval the platform publishes the accepted test cases to the TestMgmt system of record via
  `testmgmt.create_test`"*, but the implementation is a **user-triggered export**
  (`backend/api/views.py::_publish_testmgmt`, and `backend/integrations/export_tests.py` header:
  *"manual export, team flow decision 2026-07-07"*). **This doc/implementation drift is itself a
  bug** — fix the agent body or the code so they agree.
- Related known bugs in `docs/Bugs.xlsx`: **S.No 120** (register_artifact title), **S.No 132**
  (`sdlc/build` commit status stuck pending), **S.No 138** (shared enrollment `32db7f5f`).
  *(2026-09-15: S.No 132 resolved in `4ac75f9`; the publishing drift above resolved — the agent
  body now describes a reviewer-triggered export. S.No 138 is folded into the Connect Machine
  spec, not built.)*
