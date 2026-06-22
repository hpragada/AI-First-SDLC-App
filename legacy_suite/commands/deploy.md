---
allowed-tools: ["Read", "Write", "Bash", "Glob", "Grep"]
description: "Phase 12 — Deployment & Release Management. Invoke after /sdlc:cicd is configured and staging is validated. Orchestrates the full production release operation: pre-deployment readiness checklist (all tasks done, tests green, security cleared, migrations pre-flighted, rollback plan documented, on-call confirmed), release notes generated from git history with categorised change log, blue/green or canary deployment execution with defined traffic shift schedule, post-deployment smoke test suite, 30-minute active monitoring window with predefined rollback triggers, rollback procedure documentation for this specific version, and deployment log update. Auto-aborts and rolls back if any smoke test fails or error rate or latency breaches thresholds. Produces vX.Y.Z.md release notes, ROLLBACK-vX.Y.Z.md, and updated DEPLOYMENT-LOG.md."
---

# /sdlc:deploy

Invoke the **Deployment Agent** to execute Phase 12 of the SDLC pipeline.

## Usage

Deploy current main branch to production:
```
/sdlc:deploy
```

Deploy a specific version:
```
/sdlc:deploy v1.2.3
```

Pre-flight check only (no deployment):
```
/sdlc:deploy --preflight-only
```

Execute rollback for a specific version:
```
/sdlc:deploy --rollback v1.2.3
```

## Prerequisites

- Phase 11 complete: CI/CD pipeline validated
- Staging deployment tested and confirmed
- Production environment provisioned

## Outputs

| File | Description |
|------|-------------|
| `docs/releases/vX.Y.Z.md` | Release notes |
| `docs/ops/ROLLBACK-vX.Y.Z.md` | Version-specific rollback procedure |
| `docs/ops/DEPLOYMENT-LOG.md` | Updated deployment history |

## After Deployment

```
/sdlc:monitor
```

---
*AI SDLC Suite — Phase 12 of 14*

Use `@.claude/agents/12_deployment_agent.md` as the agent for this command.
