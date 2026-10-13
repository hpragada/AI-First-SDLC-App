---
allowed-tools: ["Read", "Write", "Glob"]
description: "Phase 3 — Product Requirements Document. Invoke after /sdlc:requirements is stakeholder-approved. Synthesises all Phase 1 and Phase 2 artifacts into the single authoritative PRD — the north star document governing all downstream engineering and delivery decisions. Resolves conflicts between ideation and requirements before producing output. The final approval gate before engineering investment begins. Human-gated before Phase 4."
---

# /sdlc:prd

Invoke the **PRD Agent** to execute Phase 3 of the SDLC pipeline.

## Usage

```
/sdlc:prd
```

## Prerequisites

- Phase 2 complete: `docs/requirements/` artifacts must exist and be stakeholder-approved

## Outputs

| File | Description |
|------|-------------|
| `docs/prd/PRD.md` | Complete Product Requirements Document |
| `docs/prd/GLOSSARY.md` | Domain terminology definitions |
| `docs/prd/PRD-ANALYTICS-PLAN.md` | Analytics instrumentation specification |
| `docs/assumptions/03-prd-assumptions.md` | Tier 3 inference log |

## Human Gate

Product Owner and Tech Lead sign-off required. Once approved:
```
/sdlc:architecture
```

---
*AI SDLC Suite — Phase 3 of 14*

Use `@.claude/agents/03-prd-agent.md` as the agent for this command.