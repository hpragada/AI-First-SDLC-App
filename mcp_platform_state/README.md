# mcp_platform_state/ — Platform-State MCP server

Scaffolded in **P0-T1**; tools implemented in **P0-T5** (spec §2).

Server name: `platform-state`. Stdio transport for local. Tenant-scoped on every call.
It is the **only** way agents read/write platform state — app code may use the ORM
directly, agents may not. Tools: `get_context`, `register_artifact`, `update_artifact`,
`add_trace_edge`, `log_event`, `list_work_items`, `transition_work_item`, `get_artifact`,
`list_artifacts`, `detect_drift` (stub in P0).
