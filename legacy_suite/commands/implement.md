---
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "LS"]
description: "Phase 7 — Implementation agent invoking command. Invoke iteratively — one task per invocation. Mandatory human gates at session start, architecture deviation, new dependency, destructive migration, and task completion."
---

# /sdlc:implement

Invoke the **Implementation Agent** to execute one task in Phase 7.

## What This Does

1. Reads `docs/planning/TASKS.md` and selects the next `⬜ Pending` task whose dependencies are resolved
2. Explores the codebase to understand existing patterns
3. Implements the task following architecture and coding standards
4. Writes unit tests (≥ 80% coverage) and integration tests
5. Runs linter and verifies all checks pass
6. Marks the task `🟢 Done` in TASKS.md

## Usage

```
/sdlc:implement
```

Run this command repeatedly — each invocation handles one task.

To implement a specific task:
```
/sdlc:implement TASK-015
```

## Prerequisites

- Phase 6 complete: `docs/planning/TASKS.md` must exist and be approved
- `CLAUDE.md` must have correct tech stack and commands filled in
- For frontend tasks: `docs/visuals/ux/SCR-XXX-[slug]/` wireframe directories must be present (agent reads all state files in the directory specified in the task's `Wireframe Reference` field before writing any component code)

## Outputs

- Source code implementing the task
- Unit and integration tests
- Updated `docs/planning/TASKS.md` (task marked done)

## After Each Task

Run code review before proceeding to the next task:
```
/sdlc:code-review
```

Or continue implementing if in a fast iteration cycle:
```
/sdlc:implement   (picks next task)
```

---
*AI SDLC Suite — Phase 7 of 14*

Use `@.claude/agents/07_implementation_agent.md` as the agent for this command.
