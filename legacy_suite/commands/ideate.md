---
allowed-tools: ["Read", "Write", "Glob"]
description: "Phase 1 — Ideation & Concept Discovery agent invoking command. Entry point for all new projects and major feature initiatives. Invokes the Ideation Agent to transform a given raw project idea/description in CLAUDE.md context file brief into six evidence-anchored strategic artifacts.
---

# /sdlc:ideate

Invoke the **Ideation Agent** to execute Phase 1 of the SDLC pipeline.

## Usage

```
/sdlc:ideate
```

Or with a direct description if CLAUDE.md is not yet set up:
```
/sdlc:ideate [brief description of your project idea]
```

## Prerequisites

- `CLAUDE.md` filled in (at minimum: project name, description, target users, constraints)

## Outputs

| File | Description |
|------|-------------|
| `docs/ideation/PROJECT-CONCEPT.md` | Project Vision, problem, solution, scope |
| `docs/ideation/FEASIBILITY-REPORT.md` | 4-dimension feasibility matrix with Go/No-Go recommendation |
| `docs/ideation/STAKEHOLDER-MAP.md` | Stakeholder registry with grounded interests and engagement strategies |
| `docs/ideation/SUCCESS-METRICS.md` | Desired outcome, Business/User/Technical KPIs, leading indicators |
| `docs/ideation/COMPETITIVE-ANALYSIS.md` | Competitive matrix, gap analysis, beachhead segment rationale |
| `docs/ideation/MARKET-SIZING.md` | TAM/SAM/SOM with assumptions and best/base/worst case |
| `docs/assumptions/01-ideation-assumptions.md` | Tier 3 inference log |

## Human Gate

Review all output artifacts. Once approved by the product owner, proceed with:
```
/sdlc:requirements
```

---
*AI SDLC Suite — Phase 1 of 14*

Use `@.claude/agents/01_ideation_agent.md` as the agent for this command.
