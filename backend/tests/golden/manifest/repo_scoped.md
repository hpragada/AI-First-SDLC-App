# Project

- name: PeopleDesk
- track: greenfield
- repo_topology: multi
- domain: hr
- profile_version: 3
- description: leave and attendance

**tech_stack**:
```json
{
  "backend": "django",
  "frontend": "react"
}
```

**coding_standards**:
```json
{
  "python": "ruff"
}
```

**nfrs**:
```json
{
  "p95_ms": 300
}
```

**constraints**:
```json
{
  "auth": "email + password only"
}
```

**glossary**:
```json
{
  "WI": "work item"
}
```

# Repository

- name: peopledesk-api
- role: backend
- default_base: 
- repo_id: 

Artifacts below are scoped to this repo (its own + project-shared + the cross-repo `api_contract`). The registry, traceability, and Knowledge Index are project-wide shared memory across all repos.

# Important Context

ALWAYS prefer retrieval over dumping the profile.

# Current Work Item

- id: wi-1
- phase: implementation
- type: story
- state: in_progress
- feature_stream: leave
- title: Leave policy configuration API and screen
- depends_on: wi-0
- repo_id: r1

# Relevant Artifacts

Pointers only — fetch full bodies with the platform-state `get_artifact_body(artifact_id)` tool.

**Required inputs for this phase** (your declared upstream dependencies — always the latest version):
- [requirements v1] a1 — phase=requirements, status=published, sor=internal, ptr=s3://b/req1.md

Need an artifact that isn't listed here? Fetch it precisely by type with `list_artifacts(type="<artifact_type>")`, then `get_artifact_body(id)`.

**Other recent artifacts** (situational):
- [requirements v1] a2 — phase=requirements, status=published, sor=internal, ptr=s3://b/req2.md

# Recent Events

- 2026-06-22T10:01:00 · system · run.completed → run:r1
- 2026-06-22T10:02:00 · system · run.completed → run:r2

# Retrieved Knowledge

_none (Knowledge Index is Phase 4)_

# Rules

RULE-BEHAVIOR: zero hallucination.
RULE-EXECUTION: Tier 1 first.
