# PHASE 4.7 BUILD SPEC — Web-App Productization: Auth & Admin Foundation (backend)

**Read this before any Phase 4.7 task.** It is the **contract** parallel backend assistants build
against — endpoint shapes, response schemas, permissions, and new models are fixed here so two people
on T4 and T6 never re-decide them. Tasks live in `/BUILD_PLAN.md` (P4.7-T1…T11). Flows: `/docs/UX_JOURNEYS_AND_IA_SPEC.md`
(personas, IA, J1–J22, the **eight** CONFIRMED decisions §9). Screens: `/docs/design/screens/S-NN.html`.

**Scope.** 4.7 = the **design-invariant** backend (endpoints forced by the data model + locked
architecture, not by pixel layout). **Design-sensitive** endpoints (criteria-gate schema, dashboard
rollup, lifecycle-rail) are **bucket B → Phase 4.8 spec**, not here. 4.7 builds app-level **auth +
RBAC + a secret store**; Phase 5 hardens them (vault, SoD, immutable audit).

---

## 0. Conventions (apply to every endpoint)

- **Base:** `/api/`. JSON in/out. Existing collection viewsets (`projects`, `work-items`, `runs`,
  `artifacts`, `approvals`, `clarifications`, …) and the runner/webhook routes are **unchanged**.
- **Pattern to follow (do not reinvent):** `backend/api/views.py` `TenantScopedMixin` + DRF
  `ModelViewSet`/`APIView` delegating to **domain services** (e.g. `orchestration.trigger.trigger_phase`,
  `apps.gates.services.decide_gate`). New endpoints add a **service** in the owning app and a thin view.
- **Tenancy / RLS:** every new table has `tenant_id` + an RLS migration (FORCE ROW LEVEL SECURITY +
  `tenant_isolation`, mirror `apps/integrations/migrations` DriftRecord `0008` / Clarification `0002`).
  **Run migrations as the `postgres` owner** (the `sdlc_app` role can't ALTER — see team memory).
  Keep the explicit `.filter(tenant_id=…)` defense-in-depth that `TenantScopedMixin` already does.
- **Errors:** `400` validation, `401` unauthenticated, `403` wrong role / not admin, `404` not found
  (or cross-tenant — never leak existence), `409` conflict (duplicate/last-admin). Body `{ "detail": "…" }`.
- **Tests per task:** service unit tests + REST tests (happy/permission/validation) + **DB-level RLS
  isolation** for any new table. Serialize full-suite runs; `ruff`/`mypy` clean.

---

## 1. Auth model (DECISION-3) — the foundation T1/T2/T5 establish

- **Server sessions for the browser.** Enable DRF `SessionAuthentication` for the `/api/` app
  endpoints; the **runner-token** path (`/api/runner/*`, `/api/runners/`) and the **signed webhook**
  path keep their existing auth untouched.
- **`CurrentUser` resolution.** Add a helper (`apps/tenancy/auth.py::current_user(request)`) plus DRF
  permissions `IsAuthenticatedMember` / `IsTenantAdmin`. Authenticated views resolve the **tenant from
  the user** (`user.tenant_id`), NOT the `X-Tenant-ID` header.
- **`TenantContextMiddleware` precedence (the one cross-cutting change):** if an authenticated session
  user exists → set `request.tenant_id` + the RLS GUC from `user.tenant_id`; **else** fall back to the
  `X-Tenant-ID` header (preserves runner/pre-auth/test paths). This is the single seam that flips the
  app from header-scoped to user-scoped; everything else inherits it.
- **Actor for actions:** `WorkItem.trigger`, gate `decide`, clarification `answer` take the **session
  user** as actor when present (T5); the `user_id` body param becomes optional/ignored under a session.

---

## 2. New models / migrations (RLS-aware, postgres-owner)

| Model | App | Fields (new) | Notes |
|---|---|---|---|
| `User.is_tenant_admin` | `tenancy` | `BooleanField(default=False)` | DECISION-1; tenant-level admin (no project). Covered by the existing user-table RLS — plain `AddField`. |
| `Invitation` | `tenancy` | `tenant`(FK), `email`, `name?`, `grants`(JSON `[{project_id,role}]`), `token_hash`, `status`(pending/accepted/revoked/expired), `invited_by`(FK User), `expires_at`, `created_at`, `accepted_at?` | New table → **RLS migration**. Only the **hash** of the token is stored. |
| Secret store | `integrations` | `IntegrationConnection.secret_ref` (or `secret_encrypted`) | **Write-only**. Never serialized back. Responses expose `configured: bool` only (DECISION-4). Prefer an encrypted column via a settings-driven key (Phase 5 swaps in a vault). |

No other new tables — `IntegrationConnection`, `Repository`, `Membership`, `RunnerEnrollment`,
`DriftRecord`, `Artifact`, `Approval` already exist (Phases 1–4.5).

---

## 3. Endpoint contract (every 4.7 route)

> Request/response are JSON. `me`-derived tenant unless noted. Roles from the fixed 10-role enum.

### T1 — Auth core · *backs S-02 login, the AppShell top-bar/avatar (`me`)*
| Method · Path | Req | Resp | Perm |
|---|---|---|---|
| `POST /api/auth/login` | `{email,password}` | `{user:{id,name,email,is_tenant_admin}, tenant:{id,name}, memberships:[{project_id,project_name,role}]}` + session cookie | public |
| `POST /api/auth/logout` | — | `204` | session |
| `GET /api/auth/me` | — | same shape as login `.body` | session → `401` if none |

### T2 — Signup → new tenant + first admin · *backs S-01 signup* (DECISIONS 1 & 2)
| `POST /api/auth/signup` | `{name,email,password,org_name}` | `201` `{user,tenant,memberships:[]}` + session | public; **atomic** create `Tenant`+`User(is_tenant_admin=True)`; `409` duplicate email |

### T3 — Invitations + accept + reset · *backs S-03 accept, S-04 reset, S-07 invite drawer* (J2/J3/J4)
| `POST /api/invitations/` | `{email,name?,grants?:[{project_id,role}]}` | `201` invitation `{id,email,status,expires_at,grants}` | **admin** |
| `POST /api/invitations/{id}/resend` | — | `200` | admin |
| `POST /api/invitations/{id}/revoke` | — | `200` `{status:"revoked"}` | admin |
| `POST /api/auth/accept-invitation` | `{token,password,name?}` | `200` `{user,tenant,memberships}` + session; creates the tenant `User` + queued memberships | public; `409`/`410` used/expired/revoked |
| `POST /api/auth/request-reset` | `{email}` | `200` (always — no account enumeration) | public |
| `POST /api/auth/reset` | `{token,password}` | `200` | public; `410` invalid/expired token |
Email via a **pluggable sender** (console backend in dev — no real-mail dependency).

### T4 — User & role management · *backs S-07 users table, S-08 roles matrix + coverage* (J6)
**Two admin concepts (team decision, this phase):** *tenant-admin* = `User.is_tenant_admin` — tenant-wide,
gates the admin REST surface, **can approve any gate in the tenant**, a tenant must always keep ≥1;
*project-admin* = `Membership(role="admin")` — per-project, **can approve any gate on that project**. A
phase gate is actionable when a holder of its required role **or** an admin (project- or tenant-) exists.
| Method · Path | Req | Resp | Perm |
|---|---|---|---|
| `GET /api/users/` | — | `[{id,name,email,status,is_tenant_admin, memberships:[{project_id,project_name,role}]}]` | **admin** |
| `PATCH /api/users/{id}/` | `{is_tenant_admin}` | `200` `{id,name,email,is_tenant_admin}` | admin; **`409` last-admin guard** (can't demote the tenant's only admin — incl. your own) |
| `GET /api/projects/{id}/memberships/` | — | `[{id,user_id,project,role,created_at}]` | admin |
| `POST /api/projects/{id}/memberships/` | `{user_id,role}` | `201` membership (`role="admin"` → project-admin) | admin; `409` duplicate; `404` unknown user |
| `DELETE /api/projects/{id}/memberships/{mid}/` | — | `204` | admin (no guard — the tenant-admin population is guarded on `PATCH /users/{id}`, not on project-role grants) |
| `GET /api/projects/{id}/role-coverage/` | — | `{admin_fallback:bool, roles:[{role,holders:[{user_id,name}], covered:bool, gate_blocked:bool, note?}]}` | admin |
> **Gate roles** are derived from the phase catalog (`registry.catalog.gate_roles()`), never hand-listed.
> `covered` = a direct holder of the role exists. `gate_blocked` = gate role **and** not covered **and**
> no `admin_fallback` (an admin — project or tenant — can approve any gate). `note`: when uncovered and no
> fallback → `"{gate} unactionable — no {role}"` (e.g. `"merge gate unactionable — no reviewer"`); when
> uncovered but a fallback exists → `"no {role} assigned — an admin can approve the {gate}"`.
> **Screen-complete / S-08 UI implication:** the merged S-08 mockup shows the coverage gap as a hard red
> "unactionable" even though *You* is an admin. Under the team's admin-approves-any-gate rule that gap is
> **advisory** (an admin can approve) whenever `admin_fallback:true` — S-08 should render the milder
> "admin can approve as fallback" state from `gate_blocked:false`+`note`, reserving the hard-red
> "unactionable" banner for `gate_blocked:true` (no holder **and** no admin at all).

### T5 — Authn-aware trigger & decisions · *backs S-14/S-18 trigger, S-21 decide, S-20 answer* (req #1)
No new routes — modify `WorkItem.trigger` / `approvals/{id}/decide` / `clarifications/{id}/answer` to use
the **session user** as actor (routes UI-triggered phases to *that user's* companion enrollment →
`execution_mode=companion`). `user_id` body becomes optional. Role enforcement unchanged.

### T6 — Integrations management + secret store · *backs S-11 grid, S-12 connect drawer* (J9, DECISION-4)
| `GET /api/integrations/` | — | `[{id,capability,vendor,status,configured:bool,binding:{…non-secret…}}]` | admin |
| `POST /api/integrations/` | `{capability,vendor,binding,secrets:{…}}` | `201` (secrets **write-only**) | admin |
| `PATCH /api/integrations/{id}/` | partial | `200` (secret only re-written if supplied) | admin |
| `DELETE /api/integrations/{id}/` | — | `204` | admin |
| `POST /api/integrations/{id}/test-connection/` | — | `{ok:bool, detail, fix_hint?}` | admin |
> Capabilities: `docstore/tasktracker/codehost/designsource/testmgmt/codeintel`. **Secret never in any
> response.** Replaces the shell-only `IntegrationConnection.update_or_create` (guide §5.3).
> **Implementation notes:** one connection per `(tenant, capability)` — reconnecting to a different
> vendor is a `PATCH`, a second `POST` for the same capability is `409`. `vendor`/`binding`/`status` are
> the wire names for the existing `connector`/`scopes`/`health` columns (no DB rename); `secrets` is a
> new encrypted column (`IntegrationConnection.secret_encrypted`, Fernet, key from
> `INTEGRATIONS_SECRET_KEY`/falls back to `SECRET_KEY` — Phase 5 swaps in a vault). `test-connection`
> checks the vendor is builder-registered (`integrations.registry.get_builder`) and a secret is stored
> (or none is needed, e.g. `codeintel:builtin`) — it does **not** make a live network call yet (matches
> `registry.py`'s existing "building a connector makes no network call" seam); real reachability is
> Phase 5.

### T7 — Repositories · *backs S-13* (J10)
| `GET /api/projects/{id}/repositories/` | — | `[{id,name,role,default_base,status,is_default}]` + project `repo_topology` | member |
| `POST /api/projects/{id}/repositories/` | `{name,role,base_branch}` | `201`; reconciles topology (single/split/multi) | tech_lead/admin; `409` duplicate-by-name |
| `DELETE /api/projects/{id}/repositories/{rid}` | — | `204`; reconciles topology | tech_lead/admin |
Reuse `apps/projects/repos.py` (`add_repository`/`repositories_for`); add remove + set-default.

### T8 — Brownfield onboarding · *backs S-24 hub, S-25 source docs, S-26 gap report* (J17)
| `GET /api/projects/{id}/onboarding/` | — | hub state `{upload:[…], adopt:[…], register:{…}, index:{status}, gap:{ready,resume_phase?}}` | member |
| `POST /api/projects/{id}/code-intel/` | `{repo_id}` | `202` (dispatch built-in analyzer → companion worktree; index stored, **source never copied**) | tech_lead/admin |
| `POST /api/projects/{id}/gap-report/` | — | `202`/`200` build `build_gap_report` | member |
| `GET /api/projects/{id}/gap-report/` | — | `{phases:[{phase,assessment:Complete/Partial/Missing,evidence}], resume_phase, blocking:[…]}` | member |
Existing source-doc `upload`+`adopt/` and `onboard-atlassian/` are surfaced in the hub payload.

### T9 — API-contract & drift · *backs S-27* (J18)
| `GET /api/projects/{id}/api-contracts/` | — | `[{artifact_id,name,version,provider_repo,status}]` | member |
| `GET /api/projects/{id}/api-contracts/{aid}/` | — | read-through current/version body | member |
| `GET /api/projects/{id}/drift/` | — | open `DriftRecord` queue `[{id,kind,required_role,detail,impacted:[{node,repo_id}]}]` | member |
| `POST /api/drift/{id}/decide/` | `{decision:accept/reject,comment?}` | `200` (`decide_drift`) | **architect/tech_lead**; `403` wrong role; idempotent once decided |

### T10 — Artifact preview read-through · *backs S-28 list, S-29 preview* (J19, DECISION-5)
| `GET /api/artifacts/{id}/preview/` | — | `{body, content_type, status, version, versions:[…], sor_link?}` — read-through from S3 (draft/snapshot) or SoR; **never an editor, never copied into the registry** | member; `404` missing-body |
List payloads keep **pointers only** (no body) — unchanged.

### T11 — Companion status + connect · *backs S-05 checklist tick, S-06 connect-machine* (J5)
| `GET /api/runners/` | — | caller's enrollments `[{id,machine,last_seen,online:bool,projects:[…]}]` (online derived from `last_seen`) | session |
`POST /api/runners/` (issue) already exists — ensure it binds the enrollment to the **session user**
(`developer_id`). Token issuance/`revoke` unchanged.

### P4.7 slice
A from-scratch acceptance test with **no shell/manage.py step**: signup → invite → accept+set-password →
grant gate roles → connect-machine status → create greenfield project → trigger a phase as the authed
user (routes to their companion) → answer a clarification → decide a gate → preview the published
artifact. Update `UX_JOURNEYS_AND_IA_SPEC.md` §10 marking closed gaps. (Guide PDF rewrite waits for 4.8.)

---

## 4. Dependency order (for parallel work)

```
T1 (auth core) ──▶ T2 (signup + is_tenant_admin)
                      │  (admin flag + CurrentUser now exist)
                      ▼
   ┌──────── parallel-safe, one assistant each, own app/views module ────────┐
   T3 invitations(tenancy)  T4 users/roles(tenancy)  T5 actor-wiring(api+orchestration)
   T6 integrations(integrations)  T7 repos(projects)  T8 onboarding(integrations)
   T9 drift(integrations)  T10 preview(registry)  T11 runners(runs)
   └──────────────────────────────────────────────────────────────────────────┘
                      ▼
                  P4.7 slice (integrates all)
```
T3–T11 touch **disjoint apps** → minimal collisions. Shared touch-points (append-only, coordinate):
`backend/api/urls.py` (add routes), `serializers.py`, `settings.py` (auth backend). See `AGENTS.md`
file-ownership rules.
