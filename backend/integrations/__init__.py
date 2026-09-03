"""Integration plane (Phase 1+) — capability-abstracted connectors to external SoRs.

Business logic calls capabilities (`docstore.*` / `tasktracker.*`), never vendors
(non-negotiable #9). Connectors are vendor adapters behind those interfaces; the
per-tenant connector selection + rate governor land in later Phase-1 tasks. The
IntegrationConnection model (which connector a tenant uses, and its token_ref) lives
in the `apps.integrations` Django app.
"""
