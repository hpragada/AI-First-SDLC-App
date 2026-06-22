# backend/ — control + state planes (Django + DRF)

Scaffolded in **P0-T1**. Code lands in later P0 tasks:

| Dir | Purpose | Task |
|---|---|---|
| `config/` | Django project (settings, urls, asgi) | P0-T2 |
| `apps/` | `tenancy · projects · workitems · registry · ledger · runs · gates · integrations` | P0-T2/T3 |
| `orchestration/` | Temporal workflows + activities | P0-T8 |
| `drivers/` | `ExecutionDriver` interface + `ClaudeDriver` | P0-T6 |
| `manifest/` | Manifest Composer (Project Profile → AGENTS.md) + distilled `rules/` | P0-T7/T10a |

Every model carries `tenant_id`; every table gets an RLS policy from its first migration (non-negotiable #6).
