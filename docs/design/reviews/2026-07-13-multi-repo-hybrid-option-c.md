# Design decision & build record — Multi-repo repo assignment (Hybrid "Option C") (2026-07-13)

Status: **Shipped** on `develop` @ `10b67a8`. Verified live end-to-end on a multi-repo greenfield
tenant (Task Breakdown gate approved). Bugs.xlsx rows **S.No 90–106**. Mockup:
`docs/design/screens/S-23b-repo-assignment-flow.html`.

This record captures **why** we built it, **what** was decided, and **how** it was implemented, so
the team can review the reasoning later without reverse-engineering the diff.

---

## 1. The problem

On a **multi-repo** project (e.g. separate `frontend` / `backend` / `infra` repos), each work item
must build into the *right* repository. The platform already had the multi-repo plumbing (D5:
`WorkItem.repo`, repo-scoped context, `repo_topology`, per-repo build routing), but nothing:
- let Task Breakdown **assign** a repo to a work item (`create_work_item` had no `repo_id`), nor
- let a human **see or change** those assignments,

so multi-repo routing was impossible end-to-end.

## 2. The decision — Hybrid ("Option C")

A senior dev flagged the risk that a fully-automatic agent could mis-assign a repo. We evaluated
three approaches:

| Option | Who assigns | Verdict |
|---|---|---|
| A — Pure agent | Agent auto-assigns, no human check | ❌ Wrong-repo risk slips through; violates the platform's "no auto-publish" rule |
| B — Pure manual | Human assigns every task by hand | ❌ Tedious at 30–50+ tasks; wastes the agent |
| **C — Hybrid** | **Agent proposes, human confirms/overrides at the gate** | ✅ **Chosen** |

**Why C:** it is the platform's own `draft → reviewed → gated → published` rule applied to *where
code lands*. The agent does the bulk correctly; the human's attention goes to the few uncertain
cases; a person signs off before any code is placed. Speed **and** accountability.

## 3. The five UI decisions (team-approved)

| # | Decision | Chosen | Why |
|---|---|---|---|
| 1 | Where the review lives | **At the gate** | Approving the assignment *is* the Task Breakdown gate decision — one screen, one click |
| 2 | Show confidence + reason | **Yes** (plain-language reason) | Lets the reviewer skim confident ones and focus on flagged ones; makes overrides informed |
| 3 | Layout | **Grouped by repo** | The split (e.g. 17 backend / 15 frontend) is visible at a glance; a lopsided split jumps out |
| 4 | Bulk actions | **Later** | The per-task dropdown covers 100% of cases; add bulk only if real use shows it's needed |
| 5 | Unreviewed low-confidence at approve | **Warn + "confirm all"** (not block) | Surfaces the risk without dead-ending the reviewer on a big backlog |

## 4. The end-to-end flow

1. **Setup** — user registers repos + tags each `role` (frontend/backend/infra) on the Repositories
   screen (already existed).
2. **Task Breakdown** — the agent classifies each task by its nature and assigns it a repo, with a
   plain-language reason and a `high`/`low` confidence.
3. **Review at the gate** — the reviewer sees tasks grouped by repo; low-confidence ones surfaced
   first (expanded), confident groups collapsed; override any via a dropdown.
4. **Approve** — locks the assignments (a warning + "confirm all" appears if flagged items are
   untouched, but approval is never blocked).
5. **Redirect anytime** — a per-task repo selector lets a user move a task until its build starts.
6. **Implementation** — each task's build opens its PR in the assigned repo.

**Single-repo projects are unaffected** — the feature activates on **repo count > 1**, not the
topology label. With ≤ 1 repo there is no `# Repositories` section, no assignment, no review panel
(verified live: a single-repo Task Breakdown produced 0 repo assignments).

## 5. Implementation (tasks → files)

**Agent proposes (A):**
- **A1** `get_context` returns `repositories[]` (id/name/role/base/is_default) for planning runs — `mcp_platform_state/tools.py`
- **A2** `create_work_item` takes `repo_id` + `assignment_rationale`/`assignment_confidence` — `tools.py`, `mcp_platform_state/server.py`, `runner/companion/state_mcp.py` (the runner state route passes kwargs generically, so no allowlist change)
- **A3** composer renders a `# Repositories` section for multi-repo project-level runs — `backend/manifest/composer.py`
- **A4** the `06_task_breakdown` agent classifies + assigns each task with a plain-language reason — `agents/06_task_breakdown/agent.md`
- **A5** the agent's draft is stored on `external_ref.repo_assignment` (no migration needed)

**Human reviews / overrides (B):**
- **B1** `WorkItem.repo` assignable via the work-item PATCH, validated to a repo on the same project — `backend/api/serializers.py`, `views.py`
- **B2** the gate review panel — `frontend/src/features/lifecycle/RepoAssignmentReview.tsx` (new), wired into `Gates.tsx`; grouped by repo, low-confidence first, confident groups collapsible, bounded override dropdowns
- **B3** repo selector on the task screen (locks after build starts) — `WorkItemTask.tsx`

**Gate (C):**
- **C1** Approve = the gate decision (assignments confirmed) — reuses the existing gate flow
- **C2** warn + "confirm all as-is" on unreviewed low-confidence — `Gates.tsx`

**Test enabler (E):**
- **E1** `clone_upstream` management command — `backend/apps/projects/management/commands/clone_upstream.py` (new). Copies **upstream artifacts (through UX Design) + their S3 bodies + trace edges** from one tenant/project to another, **write-only to the target**, excluding Task-Breakdown/build outputs. Cross-tenant, so it switches the RLS `app.tenant_id` context between the source read and the target write; run as the **`sdlc_migrator`** role. This is an **admin/ops tool for the multi-repo test — not a productized platform feature** (no UI). It could become a "clone project / start from template" capability later.

**Tests:** frontend 212 pass (incl. `RepoAssignmentReview.test.tsx`); backend
`test_mcp_platform_state`, `test_manifest_composer`, `test_api`, `test_clone_upstream`. Two
pre-existing stale tests were fixed along the way (S.No 80, 82).

## 6. Verification

Cloned the old single-repo tenant's upstream (39 artifacts) into a fresh 2-repo tenant, ran Task
Breakdown natively there: 32 tasks assigned **17 backend / 15 frontend**, 2 flagged low-confidence,
the review panel rendered correctly (after a layout fix — S.No 106), and the **gate was approved**.

## 7. Known gaps & follow-ups (open in Bugs.xlsx)

- **S.No 89 (P1)** — takeover-timeout marks a companion run failed + can block gate approve (tarun's co-dev). Left the old-tenant architecture run parked at `awaiting_gate`.
- **S.No 103 (P2)** — Code host connect shows a single "Repository" field on multi-repo projects (should read "Default repository"; the token must cover all repos).
- **S.No 104 (P3)** — project topology auto-derives from repo count (2 = split, 3+ = multi) and overrides the user's explicit "Multi-repo" choice; Option C keys off repo count so it's unaffected.
- **S.No 105 (P2)** — a backend/worker restart drops the companion and it doesn't auto-reconnect (reconnect with the **same** token).
- **Greenfield integrations (Confluence/Jira/Figma/Xray SoR push) are UNVERIFIED** — every run so far is `sor=internal` with 0 connections configured. Needs a dedicated pass.

## 8. References

- Mockup: `docs/design/screens/S-23b-repo-assignment-flow.html`
- Bugs.xlsx: **S.No 90 (epic) → 106**
- Non-negotiable this implements: **D5 (multi-repo / capabilities)** + "draft → reviewed → gated → published"
