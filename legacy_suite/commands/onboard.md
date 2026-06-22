---
allowed-tools: ["Read", "Write", "Glob", "Bash", "LS", "Grep"]
description: "Phase 0b — Existing Project Onboarding agent invoking command. Use this INSTEAD of /sdlc:ideate when joining an existing project mid-pipeline. Scans all existing documentation (any format, any location), maps it to the SDLC artifact structure, marks completed phases in CLAUDE.md, and tells you exactly where to resume. Run /sdlc:analyze first for richer onboarding results."
---

# /sdlc:onboard

Invoke the **Onboarding Agent** to enter an existing project at the correct pipeline phase.

## When to Use

| Situation | Command |
|-----------|---------|
| Brand new project, nothing exists | `/sdlc:ideate` |
| Existing project, run before onboarding | `/sdlc:analyze` (then `/sdlc:onboard`) |
| Existing project, ready to onboard | `/sdlc:onboard` |
| Project already onboarded, resuming | Run the next phase command directly |
| Multi-repo project setup | `/sdlc:onboard` → then `/sdlc:context-bridge` |

## Recommended Sequence for Brownfield Projects

```
Step 1: /sdlc:analyze    ← Indexes codebase, produces intelligence artifacts (RECOMMENDED FIRST)
Step 2: /sdlc:onboard    ← Maps existing docs to SDLC structure, fills CLAUDE.md
Step 3: /sdlc:[phase]    ← Resume from the confirmed phase (e.g., /sdlc:task-breakdown)
```

## Prerequisites

- Be in the root directory of the existing project
- `CLAUDE.md` should exist (copy the brownfield template and fill in what you know)
- Any existing documentation accessible at discoverable paths

## Outputs

| File | Description |
|------|-------------|
| Updated `CLAUDE.md` | Phase status, tech stack, commands, resume instructions filled in, etc. |
| `ONBOARDING-REPORT.md` | Discovery Report + Gap Analysis Report with blockers |
| `docs/ideation/*.md` | Generated from existing concept docs |
| `docs/requirements/*.md` | Reformatted from existing spec documents |
| `docs/prd/PRD.md` | Synthesised from requirements sources |
| `docs/design/*.md` | From existing architecture documents and code structure |
| `docs/planning/TASKS.md` | From existing task lists, sprint docs, or Jira exports |
| `docs/assumptions/00-onboarding-assumptions.md` | All Tier 3 inferences made during discovery |

---
*AI SDLC Suite — Entry Point for Existing Projects*

Use `@.claude/agents/00_onboarding_agent.md` as the agent for this command
