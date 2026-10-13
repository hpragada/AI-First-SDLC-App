---
allowed-tools: ["Read", "Write", "Bash", "Glob", "Grep", "LS"]
description: "Phase 11 — CI/CD Pipeline Design & Implementation. Invoke after /sdlc:security passes. Designs and implements the complete automation pipeline from commit to production: multi-stage Dockerfile (build, test, SAST, minimal runtime), docker-compose.yml for local dev parity, CI pipeline (lint → type-check → unit tests → integration tests → SAST → container build → semantic versioning), staging CD (auto-deploy on merge to main → smoke tests), and production CD (release tag or manual approval → blue/green or canary → smoke tests → auto-rollback on failure). Repository-architecture-aware: generates per-service independent pipelines for Multi-Repo Microservices. Produces Dockerfile, docker-compose.yml, workflow files, CICD-ARCHITECTURE.md, and SECRETS-MANIFEST.md."
---

# /sdlc:cicd

Invoke the **CI/CD Agent** to execute Phase 11 of the SDLC pipeline.

## Usage

```
/sdlc:cicd
```

To update an existing pipeline:
```
/sdlc:cicd --update
```

## Prerequisites

- Phase 10 complete: Security review cleared

## Outputs

| File | Description |
|------|-------------|
| `Dockerfile` | Multi-stage production container |
| `docker-compose.yml` | Local development environment |
| `.github/workflows/ci.yml` | PR validation pipeline |
| `.github/workflows/cd-staging.yml` | Staging deployment |
| `.github/workflows/cd-production.yml` | Production deployment |
| `docs/ops/CICD-ARCHITECTURE.md` | Pipeline design decisions |
| `docs/ops/SECRETS-MANIFEST.md` | Required secrets documentation |

## Human Gate

DevOps Engineer configures secrets in repository settings and validates pipeline execution. Once confirmed:
```
/sdlc:deploy
```

---
*AI SDLC Suite — Phase 11 of 14*

Use `@.claude/agents/11_cicd_agent.md` as the agent for this command.
