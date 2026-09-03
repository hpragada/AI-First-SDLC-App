# frontend/ — Experience plane (React + Vite + TypeScript)

The Phase-0 UI (**P0-T12**). A thin client over the REST API (`backend/api/`) — no
business logic here; every tenant-scoped call sends the `X-Tenant-ID` header (the
pre-auth scoping mechanism).

## Screens
- **Tenant/Project bar** — bootstrap a tenant, create/select a project.
- **Project Profile** — edit the profile (becomes the composed manifest); `important_context` is rendered verbatim into the agent prompt. Saving bumps the version.
- **Phase Console** — create work items and trigger the four planning phases (ideation → requirements → PRD → architecture); live run timeline.
- **Gate Approvals** — decide pending gates (approve/reject); resumes the Temporal workflow. Pre-auth, the approver's user id is entered by hand.
- **Artifacts** — registry pointers (phase/type/status/sor + s3_key + hash), never bodies.
- **Traceability** — the provenance DAG (`from --rel--> to`), resolved to artifact phase/type.

## Run it
The whole stack (infra + backend + worker + this UI) comes up with one command from
the repo root:
```bash
make up && make migrate && make seed && make dev   # or ./make.ps1 <target> on Windows
```
`make seed` prints the demo **tenant id** (paste into the UI's X-Tenant-ID field) and a
demo **user id / email** (`demo@demo.test`) that holds the gate roles. `make dev` serves
this app at http://localhost:5173.

To run just the UI against an already-running backend:
```bash
npm install
npm run dev      # Vite dev server on http://localhost:5173
```
Point it at a non-default API with `VITE_API_BASE` (defaults to `http://localhost:8000/api`).
The backend must allow the dev-server origin via `CORS_ALLOWED_ORIGINS` (see `.env.example`).

```bash
npm run build    # tsc typecheck + production bundle (dist/)
npm test         # vitest — api-client unit tests
npm run lint     # eslint (flat config, typescript-eslint)
```
