---
allowed-tools: ["Read", "Write", "Glob", "Bash", "LS", "Grep"]
description: "Cross-Repository Context Bridge agent invoking command. Runs in two modes: Export (run in source repo) and Import (run in target repo). Solves the split-repo contract mismatch problem for both brownfield and greenfield multi-repo projects."
---

# /sdlc:context-bridge

Invoke the **Context Bridge Agent** to share context between repositories.

## Usage

### Scenario 1: Frontend → Backend

```bash
# Step 1: In the frontend repo
/sdlc:context-bridge --export --target backend
# → Produces: CONTEXT-BRIDGE.md in the frontend repo root

# Step 2: Copy the bridge file to the backend repo
cp CONTEXT-BRIDGE.md ../backend-repo/CONTEXT-BRIDGE.md

# Step 3: In the backend repo
/sdlc:context-bridge --import
# → Reads the bridge, updates CLAUDE.md, generates API-SPEC.md, DATA-MODEL.md, REQUIREMENTS.md

# Step 4: Continue with backend development
/sdlc:architecture
```

### Scenario 2: Service A → Service B

```bash
# In Service A repo:
/sdlc:context-bridge --export --target service-b

# In Service B repo (after copying bridge file):
/sdlc:context-bridge --import --source service-a
```

### Refresh a Stale Bridge

```bash
# Re-run in source repo after API changes:
/sdlc:context-bridge --export --target backend
# Then re-run import in target repo
```

## The Three Layers of Context

```
Layer 1 — EXPORTED (Shared Contract):
  API endpoints, data models, auth flows, error codes, response envelopes

Layer 2 — EXPORTED (Shared Requirements):
  Business rules, compliance requirements, NFRs, user stories relevant to backend

Layer 3 — NOT EXPORTED (Implementation-Specific):
  UI components, state management, styling — stays in source repo
```

## Outputs

| Mode | File | Description |
|------|------|-------------|
| Export | `CONTEXT-BRIDGE.md` | Complete API contract, data models, business rules |
| Export | `docs/assumptions/00b-context-bridge-assumptions.md` | Inferred contract elements with evidence sources |
| Import | Updated `CLAUDE.md` | Cross-Repository Context section added |
| Import | `docs/design/API-SPEC.md` | API specification for implementation |
| Import | `docs/design/DATA-MODEL.md` | Shared entity definitions |
| Import | `docs/requirements/REQUIREMENTS.md` | Backend-specific requirements |

---
*AI SDLC Suite — Cross-Repository Context Sharing for Split-Repo Projects*

Use `@.claude/agents/00b_context_bridge_agent.md` as the agent for this command.
