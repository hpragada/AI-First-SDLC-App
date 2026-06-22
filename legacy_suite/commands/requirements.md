---
allowed-tools: ["Read", "Write", "Glob"]
description: "Phase 2 — Requirements Engineering agent invoking command. Invoked after /sdlc:ideate artifacts are approved. Elicits and documents the approved product concept into a complete, traceable, and testable functional and non-functional requirements set with zero tolerance for ambiguity or unquantified targets. Human-gated before Phase 3."
---

# /sdlc:requirements

Invoke the **Requirements Agent** to execute Phase 2 of the SDLC pipeline.

## Usage

```
/sdlc:requirements
```

## Prerequisites

- Phase 1 complete: `docs/ideation/` artifacts must exist and be approved

## Outputs

| File | Description |
|------|-------------|
| `docs/requirements/REQUIREMENTS.md` | All functional and non-functional requirements |
| `docs/requirements/USER-STORIES.md` | Prioritized backlog with acceptance criteria |
| `docs/requirements/USE-CASES.md` | Detailed use case specifications |
| `docs/requirements/BUSINESS-RULES.md` | Business rules catalog with authority references |
| `docs/requirements/TRACEABILITY-MATRIX.md` | Requirement → test mapping |
| `docs/assumptions/02-requirements-assumptions.md` | Tier 3 inference log |

## Human Gate

Stakeholder sign-off required. Once confirmed:
```
/sdlc:prd
```

---
*AI SDLC Suite — Phase 2 of 14*

Use `@.claude/agents/02_requirements_agent.md` as the agent for this command.
