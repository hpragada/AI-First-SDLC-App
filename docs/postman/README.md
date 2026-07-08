# AI-First SDLC Platform — Postman Collection

Import these two files into Postman:

- **`SDLC-Platform-API.postman_collection.json`** — the collection (94 requests, 20 folders).
- **`SDLC-Platform-Local.postman_environment.json`** — a matching environment pre-seeded with `baseUrl = http://localhost:8000` and all the id variables.

> The collection also ships with the same variables as **collection variables**, so it works even without selecting the environment. The environment is handy if you want to point at multiple deployments (local / staging).

## Authentication (read this first)

The platform is multi-tenant; every scoped request needs a tenant context. Three paths:

1. **Server session (primary, browser path).** Run `Auth → Signup` (or `Login`) — Postman stores the session cookie automatically. Then run `Auth → Get Current User (me)` once to receive the `csrftoken` cookie. A **collection-level pre-request script** mirrors that cookie into `X-CSRFToken` on every POST/PUT/PATCH/DELETE, so writes just work.
2. **`X-Tenant-ID` header (dev/testing).** Most read/write endpoints accept it directly. The same pre-request script attaches `X-Tenant-ID` automatically whenever the `tenantId` variable is set. **Admin** endpoints (Users, Invitations, Integrations, project membership/role actions) and **member** endpoints (repositories, onboarding, dashboard, artifact preview, enrollment GET) still require a real **session**.
3. **Runner token (companion daemon).** The `Runner — Companion` folder sends `Authorization: Runner {{runnerToken}}`. Enroll a runner first (`Runner — Enrollment → Enroll Runner`) — the one-time token is captured into `runnerToken` automatically.

## Recommended first run

1. `Auth → Signup` — creates a tenant + first admin, logs you in. Captures `tenantId`, `userId`.
2. `Auth → Get Current User (me)` — sets the CSRF cookie.
3. `Projects → Create Project` — captures `projectId`.
4. `Work Items → Create Work Item` — captures `workItemId`.
5. `Work Items → Trigger Phase Run` (use an `agent_key` from `Phases → List Phase Catalog`) — captures `runId`.
6. Explore `Runs`, `Approvals`, `Clarifications`, `Artifacts` from there.

Auto-capture test scripts populate `tenantId`, `userId`, `projectId`, `workItemId`, `runId`, `membershipId`, `repositoryId`, `invitationId`, `integrationId`, `runnerId`, `runnerToken`, and `clarificationId` from their create/login responses — so you rarely paste an id by hand.

## Notes

- **Trailing slashes are required** (Django `APPEND_SLASH`). All URLs already include them.
- List endpoints expose optional query filters as **disabled** params — enable them in the Params tab.
- The GitHub webhook needs a valid `X-Hub-Signature-256` HMAC over the exact request body; it's included for manual testing only.
- Regenerate/extend the collection from the source of truth: `backend/api/urls.py`, `backend/api/views.py`, `auth_views.py`, `runner_views.py`, `webhook_views.py`, and `serializers.py`.
