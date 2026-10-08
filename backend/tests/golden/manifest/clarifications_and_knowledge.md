# Project

- name: PeopleDesk
- track: greenfield
- repo_topology: single
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

# Answered Clarifications

Questions you already asked were answered by a human — **use these answers; do NOT ask them again**:

> These answers may come from an EARLIER run of this phase (they persist on the work item, which is how a re-dispatched run avoids re-asking). If the project has changed since — new documents adopted, a repository added, a source disconnected — an answer about *scope* may no longer hold. Trust it unless the evidence in front of you contradicts it; when it does, say so and ask once rather than reasoning from a stale answer.

_Round 2_
- What is the carryover cap? → **Five days.**
- Who approves a manager's leave? → **The department head.**

_Round 1_
- What is the carryover cap? → **Five days.**
- Who approves a manager's leave? → **The department head.**

# Relevant Artifacts

Pointers only — fetch full bodies with the platform-state `get_artifact_body(artifact_id)` tool.

Need an artifact that isn't listed here? Fetch it precisely by type with `list_artifacts(type="<artifact_type>")`, then `get_artifact_body(id)`.

**Other recent artifacts** (situational):
- [requirements v1] a1 — phase=requirements, status=published, sor=internal, ptr=s3://b/req1.md

# Recent Events

- 2026-06-22T10:01:00 · system · run.completed → run:r1

# Retrieved Knowledge

- The leave policy applies to all permanent staff. Carryover is capped at five days and lapses on 31 March. The leave policy applies to all permanent staff. Carryover is capped at five days and lapses on 31 March. The leave policy applies to all permanent staff. Carryover is capped at five days and lapses on 31 March. 
- The leave policy applies to all permanent staff. Carryover is capped at five days and lapses on 31 March. The leave policy applies to all permanent staff. Carryover is capped at five days and lapses on 31 March. The leave policy applies to all permanent staff. Carryover is capped at five days and lapses on 31 March.

# Rules

RULE-BEHAVIOR: zero hallucination.
RULE-EXECUTION: Tier 1 first.
