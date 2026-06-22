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

## Local dev (virtualenv)

The platform **runs in Docker** (backend/worker/mcp are containers). The project-local
`.venv` at the repo root is for **local tooling only** — fast `pytest`/`ruff`/`mypy`,
IDE type-checking, and the local planning runner — never a global install.

```bash
python -m venv .venv                          # once, at repo root
./.venv/Scripts/python -m pip install -r backend/requirements-dev.txt   # Windows
# source .venv/bin/activate                   # macOS/Linux
```

Pins in `requirements*.txt` are exact and verified to resolve. Containers install the
same pins at build time, so local and in-container deps stay in lockstep.

### Database & migrations

The Compose Postgres is published on host **port 5433** (container-internal is still
`postgres:5432`) to avoid clashing with a native Postgres on 5432. Two ways to run
DB-backed work:

```bash
# A) In-container (matches runtime; no host creds needed)
docker compose exec -e DATABASE_URL=postgres://postgres:postgres@postgres:5432/sdlc_platform \
  backend python manage.py migrate

# B) Local venv against the remapped host port (e.g. fast pytest)
cd backend
DATABASE_URL=postgres://postgres:postgres@localhost:5433/sdlc_platform ../.venv/Scripts/python -m pytest
```

> Migrations are generated with **explicit app labels** (`makemigrations tenancy projects …`)
> — a bare `makemigrations` can no-op before the migration packages exist.

### RLS role split (#6)

Two roles, on purpose:
- **Migrations** run as the **privileged** role (the `DATABASE_URL` superuser) — it does
  DDL and bypasses RLS.
- The **app + worker** connect as the non-superuser **`sdlc_app`** role, which RLS applies
  to. Every tenant-scoped query needs `app.tenant_id` set first — the request middleware
  (`apps.tenancy.middleware`) and Temporal activities (P0-T8) do this via
  `apps.tenancy.context.tenant_context`. Unset context fails closed (matches no rows).
