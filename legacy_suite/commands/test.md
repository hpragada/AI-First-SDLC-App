---
allowed-tools: ["Read", "Write", "Bash", "Glob", "Grep", "LS"]
description: "Phase 9 — Testing & Quality Assurance. Invoke after all sprint tasks are complete and code reviews are approved. Executes the full QA lifecycle: formal test cases for every user story (happy path, negative path, boundary values, error conditions), E2E tests for all critical user journeys, performance and load tests against quantified NFR targets from REQUIREMENTS.md, full regression suite execution, defect documentation with severity and reproduction steps, and UAT scenarios with pass/fail criteria for Product Owner sign-off. Produces TEST-PLAN.md, TEST-CASES.md, TEST-RESULTS.md, and DEFECT-LOG.md. No Critical or High defects may remain open before /sdlc:security."
---

# /sdlc:test

Invoke the **Testing Agent** to execute Phase 9 of the SDLC pipeline.

## Usage

Full QA pass (recommended):
```
/sdlc:test
```

Test a specific user story:
```
/sdlc:test US-012
```

Run only performance tests:
```
/sdlc:test --performance
```

## Prerequisites

- Implementation complete: all Sprint tasks are `🟢 Done` in TASKS.md
- Code reviews approved for all changes

## Outputs

| File | Description |
|------|-------------|
| `docs/qa/TEST-PLAN.md` | Test strategy and scope |
| `docs/qa/TEST-CASES.md` | All formal test cases |
| `docs/qa/TEST-RESULTS.md` | Execution results and coverage |
| `docs/qa/DEFECT-LOG.md` | Defects with severity and status |

## Human Gate

Product Owner UAT sign-off required. All Critical/High defects must be resolved. Then:
```
/sdlc:security
```

---
*AI SDLC Suite — Phase 9 of 14*

Use `@.claude/agents/09_testing_agent.md` as the agent for this command.
