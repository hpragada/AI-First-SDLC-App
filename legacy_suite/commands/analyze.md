---
allowed-tools: ["Read", "Write", "Bash", "Glob", "LS", "Grep"]
description: "Phase 0a — Codebase Intelligence agent invoking command. Once invoked the agent must Install and run the codebase intelligence engine against an existing codebase, producing five intelligence layers that every downstream SDLC agent can consume, and starts a queryable MCP intelligence server for the rest of the session — there should not be any manual exploration. Run BEFORE /sdlc:onboard for richer results."
---

# /sdlc:analyze

Invoke the **Intelligent Context Extractor Agent** to build a full codebase intelligence model.

## When to Run

| Scenario | Run /sdlc:analyze? |
|----------|--------------------|
| Existing project — before onboarding | **YES — recommended before /sdlc:onboard** |
| UI Modernization track | **YES — REQUIRED** |
| Legacy Transformation track | **YES — REQUIRED** |
| Microservices Decomposition track | YES — strongly recommended |
| Greenfield project with no code yet | NO — nothing to index |
| Resuming after a break (already indexed) | NO — engine auto-updates on git commit |

## Prerequisites

- Be in the root directory of an existing codebase
- Python 3.11+ available
- API key for your chosen LLM provider (or use index-only mode, no API key needed)

## Outputs

| File | Description |
|------|-------------|
| `docs/intelligence/CODEBASE-INTELLIGENCE.md` | Master intelligence document — architecture, hotspots, health |
| `docs/intelligence/DEPENDENCY-GRAPH-SUMMARY.md` | Architecture communities and coupling map |
| `docs/intelligence/GIT-ANALYTICS.md` | Churn, ownership, velocity, co-change pairs |
| `docs/intelligence/DEAD-CODE-REPORT.md` | Unused code candidates with confidence scores |
| `docs/intelligence/ARCHITECTURE-DECISIONS-REGISTER.md` | Discovered architectural decisions with staleness flags |
| MCP Server + Dashboard | Started automatically once indexing completes — 8 query tools become available to every downstream agent for the rest of the session |
| Updated `CLAUDE.md` | Codebase Intelligence section populated (including MCP Tools Reference); hotspot warnings added; Project Description, Repository Structure, and Architecture Decisions filled in only if still `[TBD]`; Open Questions appended with any genuinely unresolved findings |
| `docs/assumptions/00c-intelligence-assumptions.md` | All inferences made during intelligence extraction, including any flagged conflicts between discovered and existing CLAUDE.md content |

---
*AI SDLC Suite — Codebase Intelligence for Brownfield and Transformation Projects*

Use `@.claude/agents/00c_intelligent_context_extractor_agent.md` as the agent for this command
