---
allowed-tools: ["Read", "Write", "Bash", "Glob", "Grep", "LS"]
description: "Session Continuity agent invoking command — Captures the complete project state (current phase, last completed action, next action, all in-session decisions not yet in artifacts, task queue status, open threads, blockers, and environment status) into SESSION-SNAPSHOT.md. Solves the multi-session AI memory problem. Run at the end of every work session, before switching phases, or before a long break. Resume by saying: 'Load SESSION-SNAPSHOT.md and continue.'"
---

# /sdlc:snapshot

Invoke the **Context Snapshot Agent** to capture project state for session continuity.

## When to Run

```
End of every work session          → /sdlc:snapshot (before closing Claude Code)
Before switching phases            → /sdlc:snapshot (capture implementation state before code review)
Before a long break                → /sdlc:snapshot (weekend, sprint boundary, vacation)
After major decisions in session   → /sdlc:snapshot (decision not yet in artifact files)
When handing off to another team   → /sdlc:snapshot (include extra context for new audience)
Before onboarding a new team member → /sdlc:snapshot (comprehensive onboarding snapshot)
```

## How to Resume

At the start of the next session, say:

> **"Load SESSION-SNAPSHOT.md and continue"**

Claude reads the snapshot and all referenced artifacts, presents a brief confirmation of where it's resuming from, and begins productive work immediately — no re-explanation needed.

## Greenfield vs. Brownfield Usage

Both use the snapshot identically. The snapshot's track field distinguishes the project type, and the Phase Completion Status table reflects whichever phases are relevant (brownfield projects will show intelligence and onboarding phases; greenfield projects will show those as N/A).

## Multi-Repo Projects

Run `/sdlc:snapshot` in each repository independently. Each repo's snapshot captures that repo's specific phase status and task queue. The shared context (CONTEXT-BRIDGE.md contract version, cross-repo decisions) is captured in the Open Threads and Decisions sections.

## Outputs

| File | Description |
|------|-------------|
| `SESSION-SNAPSHOT.md` | Complete project state snapshot with Quick Resume Guide |
| Updated `CLAUDE.md` | Header line updated with latest snapshot timestamp, phase, and next command |

---
*AI SDLC Suite — Session Continuity for Multi-Session AI-Assisted Development*

Use `@.claude/agents/00d_context_snapshot_agent.md` as the agent for this command
