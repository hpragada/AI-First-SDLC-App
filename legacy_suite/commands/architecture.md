---
allowed-tools: ["Read", "Write", "Glob"]
description: "Phase 4 — System Architecture & Design agent invoking command. Designs the complete technical blueprint with every decision traced to a PRD requirement or NFR. Human-gated before Phase 5 or 6 of SDLC pipeline."
---

# /sdlc:architecture

Invoke the **Architecture Agent** to execute Phase 4 of the SDLC pipeline.

## Usage

```
/sdlc:architecture
```

## Prerequisites

- Phase 3 complete: `docs/prd/PRD.md` must be approved

## Outputs

| File | Description |
|------|-------------|
| `docs/design/ARCHITECTURE.md` | System architecture with C4 diagrams |
| `docs/design/DATA-MODEL.md` | ERD and database schema |
| `docs/design/API-SPEC.md` | API contracts (OpenAPI 3.0 style) |
| `docs/design/TECH-STACK.md` | Technology choices with rationale |
| `docs/design/adrs/ADR-001...N.md` | Architecture Decision Records |
| `docs/design/SECURITY-ARCHITECTURE.md` | Security controls and threat model |

## Human Gate

CTO/Engineering Manager and Security Engineer review required. Once approved:
```
/sdlc:ux-design   (for user-facing products)
/sdlc:task-breakdown  (for API/backend-only products)
```

---
*AI SDLC Suite — Phase 4 of 14*

Use `@.claude/agents/04_architecture_agent.md` as the agent for this command.
