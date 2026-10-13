---
allowed-tools: ["Read", "Write", "Bash", "Glob", "Grep", "LS"]
description: "Phase 10 — Security Review agent invoking command. Opens with a Stack Identification & Tool Selection Pass followed by execution of nine review tracks: Static Application Security Testing (SAST), Software Composition Analysis (SCA), Software Bill Of Materials (SBOM) & Supply Chain Security, OWASP Top 10 assessment, Authentication & Authorization deep dive, Data Security, Infrastructure Security, Cloud Security Posture, and STRIDE threat modelling. Produces SECURITY-REVIEW.md, THREAT-MODEL.md, DEPENDENCY-SCAN.md, and SBOM.json. No Critical or High findings may remain open before /sdlc:cicd."
---

# /sdlc:security

Invoke the **Security Agent** to execute Phase 10 of the SDLC pipeline.

## What This Does

Runs a comprehensive adversarial security review across ten steps — approaching the codebase as a skilled attacker before documenting defences.

## Usage

```
/sdlc:security
```

## Outputs

| File | Description |
|------|-------------|
| `docs/security/SECURITY-REVIEW.md` | Eleven-section report: findings with CVSS ratings, OWASP assessment, auth/data/infra/cloud reviews, compliance verification, and remediation priority queue |
| `docs/security/THREAT-MODEL.md` | DFD-grounded STRIDE analysis per element type |
| `docs/security/DEPENDENCY-SCAN.md` | CVE inventory and license compliance table |
| `docs/security/SBOM.json` | CycloneDX-format component inventory |

## Policy

**No Critical or High findings may remain open before proceeding to deployment.**

## Human Gate

Security Engineer review and sign-off required across output sections. Once cleared:

```
/sdlc:cicd
```

---
*AI SDLC Suite — Phase 10 of 14*

Use `@.claude/agents/10_security_agent.md` as the agent for this command.