---
allowed-tools: ["Read", "Bash", "Glob", "Grep", "LS"]
description: "Phase 8 — Code Review agent invoking command. Supports three review modes: Single Task, Full Sprint, and Branch/PR. Opens with mode-aware scope declaration. Performs code review using eleven review dimensions. Three-tier severity: Critical 🔴 (blocks merge), Warning ⚠️ (merge with justification), Suggestion 💡 (non-blocking). After every review cycle, presents a Remediation Gate — fix manually, hand off to the Implementation Agent via a structured Remediation Brief, or accept and proceed. Re-review loops within this agent until status reaches APPROVED or APPROVED WITH CONDITIONS before Phase 9 transition fires."
---

# /sdlc:code-review

Invoke the **Code Review Agent** to execute Phase 8 of the SDLC pipeline.

## Usage

```
/sdlc:code-review
```

The agent opens with a mode selection gate. Provide one of:

| Input | Mode | Behaviour |
|-------|------|-----------|
| `TASK-XXX` | Single Task | Reviews one task in isolation across all eleven dimensions |
| `Sprint-N` | Full Sprint | Reviews every task in the sprint; produces per-task reports + sprint summary |
| `[branch-name]` | Branch / PR | Runs `git diff main...HEAD`, maps files to task IDs, reviews all changed files |

## When to Invoke

| Trigger | Mode to use |
|---------|-------------|
| Human Gate #2 in Agent 07 → user selects **"Review now"** | Single Task |
| Sprint Completion Gate in Agent 07 approved → all tasks Done | Full Sprint |
| Returning from Implementation Agent after a **Remediation Brief** | — agent re-enters automatically via "re-review" signal |
| Standalone review outside the sprint cadence | Branch / PR |

## Prerequisites

- `docs/planning/TASKS.md` — task acceptance criteria and sprint assignments
- `docs/design/ARCHITECTURE.md` — architecture patterns for adherence checks
- `docs/design/API-SPEC.md` — API contracts for correctness checks
- `docs/design/SECURITY-ARCHITECTURE.md` — role-based access model
- `docs/planning/DEFINITION-OF-DONE.md` — completion criteria
- For frontend tasks: `docs/visuals/ux/SCR-XXX-[slug]/` wireframe state directories
- For frontend tasks: `docs/ux/ACCESSIBILITY.md` and `docs/ux/DESIGN-SYSTEM.md`

## Outputs

| Artifact | Description |
|----------|-------------|
| Per-task review report (chat) | Three-tier findings with code snippets where applicable |
| Sprint-level summary (Mode 2) | Aggregate table, cross-task observations, positive patterns |
| Remediation Brief (Option B) | Structured `REM-C` / `REM-W` items for the Implementation Agent |
| `docs/assumptions/08-code-review-assumptions.md` | Tier 3 inference log |
| `CLAUDE.md` | Phase 8 marked ✅ Complete (on final approval only) |

## Human Gate

Engineering Lead review required. Fires only after Remediation Gate resolves. Once approved:

```
/sdlc:test
```

---
*AI SDLC Suite — Phase 8 of 14*

Use `@.claude/agents/08_code_review_agent.md` as the agent for this command.
