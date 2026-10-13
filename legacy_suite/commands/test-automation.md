---
allowed-tools: ["Read", "Write", "Bash", "Glob", "Grep", "LS"]
description: "Phase 9b — Test Script Generation. Invoke after /sdlc:test produces TEST-CASES.md and AUTOMATION-BRIEF.md. Generates a complete, runnable test automation script for one test case per invocation — same discipline as /sdlc:implement (one TC-ID, one artifact, human gate). Navigates the live application via Playwright MCP to discover real DOM locators before writing any code. Supports any language/framework (Selenium C#/Java, Playwright TS/Python/C#, Cypress, etc.) read from CLAUDE.md Testing Tech Stack. Tracks progress in docs/qa/AUTOMATION-LOG.md."
---

# /sdlc:test-automation

Invoke the **Test Automation Agent** to generate a runnable automation script for one test case in Phase 9b.

## Usage

Generate a script for a specific test case:
```
/sdlc:test-automation TC-007
```

Generate the next un-automated candidate:
```
/sdlc:test-automation next
```

List automation candidates and their status:
```
/sdlc:test-automation list
```

Run this command repeatedly — each invocation handles one test case.

## Prerequisites

- Phase 9 complete: `docs/qa/TEST-CASES.md` and `docs/qa/AUTOMATION-BRIEF.md` exist
- **Playwright MCP must be configured and available** — Step 4 (live locator discovery) halts without it. If using Claude Code, run `claude mcp add playwright ...` before invoking this command.
- `CLAUDE.md → Testing Tech Stack` filled in (or be ready to answer the one-time setup prompt)

## Outputs

| File | Description |
|------|-------------|
| `tests/automated/[Helpers or fixtures]/...` | Base classes / shared fixtures (created only if missing) |
| `tests/automated/[pages or PageObjects]/[PageName]Page.[ext]` | Page object with real DOM locators |
| `tests/automated/[Tests or tests]/TC[XXX]-[slug].[ext]` | The generated test script |
| `docs/qa/AUTOMATION-LOG.md` | Tracks every TC-ID's automation status |

## Human Gate

After each script is generated, review the locators and assertions against the live app, then confirm:
```
APPROVED
```

To generate the next script:
```
/sdlc:test-automation next
```

---
*AI SDLC Suite — Phase 9b (between Phase 9 and Phase 10)*

Use `@.claude/agents/09b_test_automation_agent.md` as the agent for this command.
