# mcp_platform_state/ — Platform-State MCP server (spec §2)

Server name: **`platform-state`**, **stdio** transport. The **only** way agents read or
write platform state — app code may use the ORM directly, agents may not.

## Design
- **Reuses the Django ORM** (`bootstrap.setup_django()`), so it inherits the exact
  models, enums, RLS context util, and the append-only `Event` guard — one source of
  schema truth, no parallel SQL to drift. It therefore runs **inside the backend
  environment** (Django + deps already present; `mcp` is in `backend/requirements.txt`).
- **Tenant is bound from the launch context** (`PLATFORM_TENANT_ID`, set by the
  ClaudeDriver per run) — agents never pass a tenant, so they cannot reach another
  tenant's rows. Every tool also filters by `tenant_id` explicitly **and** sets
  `app.tenant_id` so Postgres RLS is the backstop when running as the `sdlc_app` role.
- **Launched on-demand over stdio** by the ClaudeDriver (P0-T6) as a subprocess of the
  worker — it is not a long-running daemon.

## Layout
- `bootstrap.py` — idempotent `django.setup()` (no-op under pytest).
- `tools.py` — the 10 tool implementations (plain, integration-tested functions).
- `server.py` — `FastMCP("platform-state")` exposing the tools; injects the bound tenant.

## Tools (spec §2)
`get_context` · `register_artifact` · `update_artifact` · `add_trace_edge` · `log_event`
· `list_work_items` · `transition_work_item` · `get_artifact` · `list_artifacts` ·
`detect_drift` (stub in P0 — always `drift=false`; real comparison in Phase 4).
