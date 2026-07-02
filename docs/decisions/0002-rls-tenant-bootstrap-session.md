# ADR 0002 — Resolve RLS tenant context from the session, not `request.user`

- **Status:** Accepted (2026-07-02)
- **Deciders:** Build team
- **Context task:** hotfix discovered during the P4.8 UI-wiring pass; corrects the
  `TenantContextMiddleware` design fixed by Phase 4.7-T1/T2 (DECISION-3,
  `/docs/PHASE_4.7_BUILD_SPEC.md` §1).

## Problem

DECISION-3 (Phase 4.7-T1) specified: *"if an authenticated session user exists → set
`request.tenant_id` + the RLS GUC from `user.tenant_id`."* Implemented literally, this is
circular: resolving whether a session user exists means evaluating `request.user`, which
`AuthenticationMiddleware` populates by querying the RLS-protected `tenancy_user` table —
but that query needs `app.tenant_id` already set to pass RLS, and `app.tenant_id` isn't set
until the tenant is known from `request.user`. Neither side of the cycle can go first.

Under the Postgres **superuser** role (which the test suite and `manage.py migrate` connect
as, per the documented `sdlc_app`-has-no-`CREATEDB` workaround), RLS is bypassed entirely, so
this never failed a test. Under the real `sdlc_app` role — every actual deployment — it meant
**no session-authenticated request could ever resolve `request.user`**: login, `/me`, and
every other authenticated endpoint failed. `ModelBackend.authenticate()` (the login lookup by
email) hit the identical problem one step earlier, so even a correct password returned
"Invalid email or password." Nobody had exercised the live app end-to-end against the real
`sdlc_app` role before this was found — the guide's own testing playbook was curl/shell-driven
(see `BUILD_PLAN.md` P4.8-T6), and the RLS bypass under the test role masked it completely.

## Decision

1. **Store `tenant_id` in the Django session at login** (`api/auth_views.py` —
   `SignupView`, `LoginView`, `AcceptInvitationView`, inside the same `tenant_context()` block
   that already scopes the `last_login` write and `serialize_me()` read).
2. **`TenantContextMiddleware` resolves the tenant from `request.session["tenant_id"]`**, not
   from `request.user` — no DB query needed, so RLS can't block it.
3. **`TenantContextMiddleware` now runs *before* `AuthenticationMiddleware`** in
   `config/settings.py::MIDDLEWARE`, so `app.tenant_id` is already set by the time anything
   later in the chain (starting with `AuthenticationMiddleware`'s own lazy `request.user`
   lookup) queries `tenancy_user`.
4. **`tenancy_user`'s RLS policy gets one narrow carve-out** (migration
   `apps/tenancy/migrations/0005_user_rls_auth_bootstrap.py`): a row is also visible when
   `app.tenant_id` is unset — i.e. only during the pre-auth bootstrap window (`authenticate()`
   by email during login, before any tenant is known). The `WITH CHECK` clause for writes
   stays strict. Once a tenant *is* scoped (normal authenticated operation), the widened
   clause is false and the original per-tenant match is all that applies — every other
   platform table's policy is untouched.

The `X-Tenant-ID` header fallback (pre-auth/dev/runner-token paths) is unchanged.

## Why this over alternatives

- **Why not keep resolving from `request.user`:** structurally circular under real RLS, as
  above — no ordering of `AuthenticationMiddleware` vs. `TenantContextMiddleware` fixes it
  without also changing *how* the tenant is discovered.
  - Alternative floated but not chosen: a raw SQL lookup as a workaround. Doesn't help — a raw
    query on the same `sdlc_app` connection is subject to the identical RLS policy; the
    conflict is at the Postgres role level, not the ORM.
  - Alternative floated but not chosen: a second, RLS-bypassing DB role/connection dedicated
    to auth bootstrap. Works, but adds a parallel privileged connection to reason about for a
    problem the session-storage approach solves with no new privilege at all.
- **Why the RLS carve-out is scoped the way it is:** it only ever widens access during the
  window where `app.tenant_id` is genuinely unset (pre-auth), which is also the only window
  where a plain `authenticate()`-by-email lookup is legitimate. Once any tenant is scoped, the
  strict predicate is back in force — this does not weaken isolation for any authenticated
  request, only for the bootstrap step every login must perform by definition.
- **Why session storage over re-deriving on every request:** it's one write at login instead
  of a query on every request, and it's what `TenantContextMiddleware`'s docstring now
  documents as the source of truth.

## Consequences

- `docs/PHASE_4.7_BUILD_SPEC.md` §1 (DECISION-3) is updated to describe this corrected
  behavior instead of the original circular one — see that section for the current contract.
- Any **future** code path that calls `django.contrib.auth.login()` (a new SSO flow, etc.)
  must also set `request.session["tenant_id"]` in the same block, or that user will
  authenticate but every subsequent request will fail to resolve a tenant. Grep
  `request.session["tenant_id"]` in `api/auth_views.py` for the existing pattern.
- Local/shared dev databases created before this migration need
  `apps/tenancy/migrations/0005_user_rls_auth_bootstrap.py` applied (run as the privileged
  migration role, same as every other RLS migration) before login will work against the
  `sdlc_app` role.
- This was found and fixed by exercising the real signup → login → `/me` flow through an
  actual browser session against the `sdlc_app` role for the first time — worth keeping as a
  standing verification step (not just curl/shell/superuser-role testing) before any future
  auth-adjacent change ships.
