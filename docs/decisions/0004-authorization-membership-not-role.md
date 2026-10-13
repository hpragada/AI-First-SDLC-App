# ADR 0004 — Project **membership** authorizes ordinary work; a **lead role** authorizes only what re-steers the project

- **Status:** Accepted (2026-09-03)
- **Deciders:** Build team
- **Context task:** Bugs.xlsx S.No 214 (nine write endpoints accepted anonymous requests), fixed on
  `SDLC_Bug_Fix_Enhancements`. This ADR records a **deliberate departure** from the approved plan
  for that fix, and the evidence that forced it.

## Problem

DRF's project-wide default here is `AllowAny`. Nine write endpoints never stated their own
permission, so inside a tenant nothing checked who the caller was: creating projects, rewriting the
project profile every agent reads as its briefing, creating and editing work items, starting a
phase run, seizing or resuming someone else's run, minting a companion enrollment token.

Closing that needs two separate questions answered, because they have different right answers:

1. **Is anybody logged in?** `IsAuthenticatedMember` answers exactly this and nothing more — its
   own docstring says so. It does not check project membership despite the name.
2. **Are you allowed to do *this*?** This is where the plan and the code disagreed.

The approved plan specified `require_project_write_role` — `tech_lead` or `admin` on the project,
tenant-admin as fallback, matching `require_repo_manage_role` — on all five privileged actions:
profile edit, trigger, build, take-over/resume, and enrollment.

**Implementing that broke the ordinary journey, and the existing tests said so immediately.**
`test_authn_actor` drives `trigger` as a `product_owner` and as an `engineer`.
`test_runner_enrollment_rest` connects a machine as an `engineer`. Those are not edge cases — they
are the product working as designed. The platform's whole structure is that each role drives its
own phase: that is what `project_role_coverage` exists to track and what the gate `required_role`
enforces. A Product Owner triggers ideation; an Engineer triggers implementation; a developer
connects their own laptop.

A `tech_lead`-only bar on those actions would have locked most of the team out of ordinary work
while claiming to be a security fix.

## Decision

Two distinct checks, applied by what the action actually does:

| Bar | Function | Where it applies | Why |
|---|---|---|---|
| **tech_lead / admin** (tenant-admin fallback) | `require_project_write_role` | Project profile edit **only** | Rewriting the profile re-steers every agent that will ever run on the project. It is the most load-bearing text in the platform. |
| **Any project membership** (tenant-admin fallback) | `require_project_member` | trigger, build, take-over, resume | Each role drives its own phase. What needs closing here is a signed-in user acting on a project they are not on at all. |
| **Session only** | `IsAuthenticatedMember` | create, source-documents, traceability, onboard-atlassian, work-item writes, runner revoke | Ordinary member work. Raising this bar would break the journey and protects nothing extra. |

`require_project_member` is not a weaker version of the role check — it closes a hole the role
check was never aimed at. `IsAuthenticatedMember` only asks for a session, so before this change a
signed-in user from the same tenant could trigger runs on a project they had no membership of.

### The one endpoint deliberately left open

`POST /api/runners/` mints a credential and is genuinely the ninth hole. It is **not** gated,
because the documented CLI onboarding — `python -m runner.companion enroll` (runner/README.md,
Quick start step 1) — sends a tenant header and a `developer_id` body param and has no session to
present. There is no user-token auth for it to use instead; adding one is new capability, not a bug
fix. Recorded against **S.No 35**, which already owns the Connect Machine credential redesign along
with three sibling findings (disconnect revokes one row of several; the token travels on the
command line; tokens never expire). All four are the same question — *how does a headless machine
authenticate* — and must be answered together.

## Consequences

**A behaviour change worth announcing.** A signed-in user who is not a member of a project can no
longer trigger runs on it, take over its runs, or resume them. That is intended, but it is new: any
script or fixture that acted cross-project on a bare session now gets a 403.

**Ten test files needed a session added.** They were posting anonymously, which is precisely the
hole that was closed — the edits are setup changes, not logic changes. Two tests asserted the old
behaviour and were rewritten to assert the new one; a third
(`test_post_without_session_falls_back_to_body_developer_id`) is restored, because that path is
held for S.No 35.

**The plan was wrong and the tests were right.** Recorded because the failure mode is worth
remembering: the plan reasoned from what an action *costs* (engine time, a credential) and
concluded "lead only". The code encodes who the platform expects to *do* it. When those disagree,
the running system is the evidence.
