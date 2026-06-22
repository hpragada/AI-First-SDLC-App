---
allowed-tools: ["Read", "Write", "Glob"]
description: "Phase 6 — Task Breakdown & Sprint Planning agent invoking command. Invoke after /sdlc:architecture and /sdlc:ux-design (if applicable) are approved. Decomposes PRD and architecture into atomic, typed, estimated, dependency-mapped, acceptance-criteria-bearing tasks loaded into balanced sprints respecting team velocity and the critical path. Human-gated by Tech Lead before Phase 7."
---

# /sdlc:task-breakdown

Invoke the **Task Breakdown Agent** to execute Phase 6 of the SDLC pipeline.

## Usage

```
/sdlc:task-breakdown
```

## Prerequisites

- Phase 4 complete: `docs/design/ARCHITECTURE.md` approved
- Phase 5 complete (if frontend): `docs/ux/WIREFRAMES.md` approved + `docs/visuals/ux/SCR-XXX-*.html` files present (HTML wireframes are used to accurately size frontend tasks — every frontend task references its wireframe file)

## Outputs

| File | Description |
|------|-------------|
| `docs/planning/TASKS.md` | Complete prioritized task backlog |
| `docs/planning/SPRINT-PLAN.md` | Sprint allocations and goals |
| `docs/planning/DEFINITION-OF-DONE.md` | Team DoD agreement |
| `docs/planning/DEPENDENCY-MAP.md` | Task dependency and critical path |

## Human Gate

Tech Lead reviews task granularity and sprint load. Once approved:
```
/sdlc:implement
```

---
*AI SDLC Suite — Phase 6 of 14*

Use `@.claude/agents/06_task_breakdown_agent.md` as the agent for this command.
