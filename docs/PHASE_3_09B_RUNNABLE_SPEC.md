# Phase 3 Supplement — Making 09b Test Automation Runnable (Playwright-MCP + PreviewEnv wiring)

> **Purpose:** operationalize contracts **already locked in `PHASE_3_BUILD_SPEC.md`** (D4 test
> execution, D7 companion-local preview env, the 09b agent reroute in §4) so a `09b_test_automation`
> build can actually complete end-to-end. This supplement **decides nothing new** — the design is
> D7/D4; it fixes the *implementation* seams the Phase-3 spec declared but that were never wired.
> Same rule as every build spec: contracts here don't change without updating this file.
>
> **Builds on Phase 2 + Phase 3 — not re-opened.** The `BuildWorkflow` saga, the local-companion
> runner + managed worktree, `EgressPolicy`/guardrails, `build_mcp_servers`, and the `PreviewEnv`
> model + `apps/quality/preview.py` service are all **present and frozen**. This is wiring, not new
> architecture.

## 0. Problem statement — why 09b can't run today

The 09b control-plane path is complete and verified (trigger → `rides_build` → `trigger_build` →
`BuildWorkflow` → dispatch loads the real 09b body → `import_build_test_results` routed off the
catalog → defect loopback; the companion collects JUnit and reports it). But a **real** 09b build
cannot finish, because three runtime dependencies the D7/§4 contracts assume are **not wired**:

1. **No Playwright MCP on the build driver.** `runner/companion/runner.py::build_mcp_servers()`
   returns only `platform-state`. The 09b body's Step 4 (Live Application Exploration) **hard-halts**
   without `mcp__playwright__*`. → nothing is generated.
2. **No app/preview URL.** The agent navigates `[base_url][route]` to discover real DOM locators.
   Nothing brings the app up or ships a URL — `PreviewEnv` + `provision_preview`/`teardown_preview`
   exist but are **called only from tests**, never from the build saga, and the companion has no
   bring-up step. (D7 says the companion brings the app up from the worktree; that step is missing.)
3. **No config for how to start the app.** The project-declared start command / port / health path
   (D7: "from the Project Profile/Repository") has **no home on either model** yet.

Also fixed in the same effort (already landed 2026-07-18): `BuildInput.phase` defaulted to
`"implementation"` and `trigger_build` never overrode it, mislabeling every non-07 build. Now
`phase = spec.phase_label or agent_key` (mirrors `trigger_phase`) — so `task.phase == "test_automation"`
is a **reliable** discriminator for the phase-gated wiring below.

## 0.1 In / out of scope

**In:** Playwright MCP as a **phase-scoped** build-driver MCP server (09b only); the companion
**app bring-up** step + wiring `provision_preview`/`teardown_preview` into the `BuildWorkflow`;
the **preview-start config** model fields (Repository-first, ProjectProfile fallback) + their flow
into the `BuildTask`; threading `base_url` into the 09b manifest; egress **scoped to the preview
host + localhost**; the phase-allowlist extension for `mcp__playwright__*`.

**Out (unchanged deferrals):** **executing** the automated suite + emitting JUnit (the separate
author-vs-CI-execute decision — this supplement makes 09b *author* against a live app; the loopback
stays dormant until execution lands, and PreviewEnv here is its prerequisite). **Cloud** per-PR envs
(P5, behind `PreviewEnv.provider`). Any change to the 07↔08 remediation loop, gates, or the import
seam (`import_build_test_results` is correct and unchanged).

## 0.2 Assets already present (reuse, do not rebuild)

| Asset | Location | State |
|---|---|---|
| `PreviewEnv` model | `backend/apps/quality/models.py` | Exists (`provider=companion_local`, `status`, `url`) |
| `provision_preview` / `teardown_preview` | `backend/apps/quality/preview.py` | Exists + unit-tested; **not called from the saga** |
| `run_provisioning` hook | `runner/companion/runner.py:134` | Runs per-task worktree setup — the home for bring-up |
| `EgressPolicy` (+`extra_allowed_hosts`) | `runner/companion/guardrails.py:166` | Exists; preview host must be added |
| `build_mcp_servers` | `runner/companion/runner.py:93` | Returns only `platform-state` — plug-in point |
| `BUILD_ALLOWED_TOOLS` / `assert_phase_allowlist` | `runner/companion/runner.py:46` / `guardrails.py:211` | Forbid networked tools (D2) — needs phase-scoped extension |
| `import_build_test_results` | `backend/orchestration/build_activities.py:107` | Correct; consumes JUnit when execution eventually lands |

---

## 1. Preview-start config (new model fields — D7 "from the Project Profile/Repository")

The thing that is *served* is a **repo** (the frontend repo runs the UI; a backend repo has no UI to
preview), so preview-start config is **repo-first** with a project-level fallback for single-target
projects. Mirror the existing `provisioning_commands`/`stack_overrides` JSON-config pattern — no new
tables.

```python
# backend/apps/projects/models.py

# Repository (primary home — per-repo serve target)
preview_start = models.JSONField(default=dict, blank=True)
#   {"command": "npm run dev", "port": 5173, "health_path": "/", "ready_timeout_s": 120,
#    "ready_log": "Local:"}   # any ONE of health_path / ready_log satisfies readiness

# ProjectProfile (fallback for single-serve-target projects)
preview_start = models.JSONField(default=dict, blank=True)   # same shape
```

- **Resolution order (single source of truth — new helper):** `Repository.preview_start` →
  `ProjectProfile.preview_start` → **empty**. Empty ⇒ no preview is provisioned and 09b **fails
  loud** with a clear reason ("no preview-start command configured for this repo — set it before
  running test automation"), never a silent no-locator run.
- Both fields are **RLS-scoped** by their existing `TenantScopedModel` base; no new policy.
- Migration: additive JSON fields, defaults `{}` — safe, no backfill.

## 2. App bring-up on the companion (D7 — the missing worktree step)

```python
# runner/companion/runner.py  (new)
@dataclass
class PreviewHandle:
    url: str
    proc: subprocess.Popen            # for teardown
    port: int

def provision_preview_app(worktree: Path, task: BuildTask, policy: EgressPolicy) -> PreviewHandle | None:
    """Start the project-declared app from the worktree, wait for health, return its local URL.
    None when the phase declares no preview-start config. Runs AFTER run_provisioning (deps
    installed). The command's egress is checked (check_command_egress) exactly like provisioning."""
```

- **Only for `task.phase == "test_automation"`.** 07/11 builds never start an app.
- **Readiness:** poll `http://127.0.0.1:<port><health_path>` until 2xx/3xx, OR match `ready_log` in
  the process output, up to `ready_timeout_s`. Timeout ⇒ teardown + a failed build report with the
  captured tail of the server log (never hang).
- **Teardown is guaranteed:** extend the existing `finally` in `run_build` to kill the process group
  and free the port whether the build succeeds, fails, or the worktree is torn down.
- **URL travels back:** add `preview_url: str = ""` to `BuildReport` (build_types.py) and set it in
  `run_build`'s result → `to_build_report`.
- **Bind loopback only** (`127.0.0.1`): the preview is for the companion's own Playwright, not a
  public URL (that's the P5 cloud seam).

## 3. Playwright MCP on the build driver (phase-scoped — unblocks Step 4)

```python
# runner/companion/runner.py::build_mcp_servers  (extend)
servers = {"platform-state": { ... existing ... }}
if task.phase == "test_automation":
    servers["playwright"] = {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@playwright/mcp@latest", "--headless"],
        "env": {"PLAYWRIGHT_MCP_ALLOWED_ORIGINS": preview_origin},  # scope to preview host
    }
return servers
```

- **Allowlist extension (PG12).** `BUILD_ALLOWED_TOOLS` today forbids networked tools (`web/http/
  network/fetch/curl/codehost` hints, D2). Add a **phase-scoped** set: `mcp__playwright__*` is
  permitted **only** when `task.phase == "test_automation"`. `assert_phase_allowlist` gains a
  `phase` param and an explicit per-phase extra-allow set — `mcp__playwright__browser_*` cleared,
  everything else still asserted. Do **not** relax the global allowlist.
- **Companion prerequisite (enrollment, not per-run):** `@playwright/mcp` + browser binaries
  (`npx playwright install`) must be present on the enrolled machine. Document in the companion
  setup; a missing binary ⇒ Step 4's existing hard-halt with its clear message (already in the body).
- **09b must run as a top-level driver invocation** (the body already states this — MCP servers on a
  parent invocation aren't inherited by a nested one). The `BuildWorkflow` dispatch already invokes
  the agent at top level; no nesting is introduced.

## 4. Threading `base_url` to the agent + egress

- **Manifest:** the composed manifest for a `test_automation` run must carry the preview `base_url`
  so the agent's Step 4 has a concrete target. Since bring-up happens on the companion *after*
  dispatch, the URL is **loopback-deterministic** (`http://127.0.0.1:<resolved port>`) — resolve the
  port at config time and inject it into the manifest at dispatch, OR (simpler) have the companion
  substitute `[base_url]` into the run prompt after bring-up. **Chosen: companion substitutes**, so
  the platform never guesses a port the companion actually bound.
- **Egress (LOCKED — scope to preview host only):** add the preview host (`127.0.0.1` / `localhost`
  + resolved port) to `EgressPolicy` for the run. No broader hosts. A real login flow that needs an
  external IdP is **out of scope** for v1 (revisit only if a target app needs it — a deliberate,
  reviewable widening, not a default).

## 5. Saga ordering (BuildWorkflow — D7 provision/teardown)

```
dispatch_build
  → companion: provision_worktree → run_provisioning → provision_preview_app (09b only)
  → run 09b agent (Playwright explores base_url) → generate + compile scripts
  → report (status, changed_files, test_results=[], preview_url)
  → [platform] provision_preview activity: record PreviewEnv(ready, url) + PR comment (best-effort)
  → open_build_pr → 08 review loop → open_merge_gate
  → merge → publish_build_artifacts → transition_work_item(done)
  → teardown_preview (on merge/close AND on saga compensation)
```

- **`provision_preview` / `teardown_preview` become activities** called by name from
  `build_workflow.py` (Django-free workflow rule preserved — the activity does the ORM work).
  `provision_preview` runs after the report (URL is known); `teardown_preview` on terminal
  completion, rejection, and the `_park`→abandon compensation path.
- **No new park semantics** — a bring-up failure surfaces as a failed build report (companion-side),
  which the saga already handles.

## 6. Testing + Definition of Done

- **Unit (companion):** `provision_preview_app` returns a URL when config present / `None` when
  absent / raises→failed-report on timeout (mock `Popen` + a fake health endpoint); teardown always
  kills the process; `build_mcp_servers` includes `playwright` **only** for `test_automation`;
  `assert_phase_allowlist(phase="test_automation")` clears `mcp__playwright__browser_navigate` and
  still rejects `mcp__codehost__*` / `web` tools.
- **Unit (backend):** preview-start resolution order (Repo → Profile → empty-fails-loud); `provision_
  preview`/`teardown_preview` activities registered + idempotent; `BuildReport.preview_url` round-trips.
- **Contract/migration:** the new JSON fields migrate additively; `test_reference_sweep` still clean
  for the 09b body (no local-file/`.md` refs introduced by any manifest change).
- **Acceptance (extend `test_acceptance_phase3.py`):** a `test_automation` build with preview-start
  config provisions a `PreviewEnv(ready)`, dispatches with `playwright` MCP + `base_url` in the
  prompt, and tears the env down on completion — asserted with a fake companion (no live browser).
- **DoD:** `make test` green; a 09b run against a demo repo brings the app up, Step 4 no longer
  halts, scripts land in the worktree, the PR carries the preview link, and the env is torn down on
  merge. Execution/JUnit remains the explicit next slice.

## 7. Decisions ledger (all trace to existing LOCKED contracts)

- **Reuses D7 (LOCKED):** preview env = companion-local seam (worktree bring-up + PR link, torn down
  on close); cloud env → P5 behind `PreviewEnv.provider`.
- **Reuses D4 (LOCKED):** the worktree is where tests are authored/executed; results import on report.
- **Reuses D2 (LOCKED):** platform owns Git side-effects; the build driver stays network-restricted —
  Playwright is a **scoped, phase-only** exception to a **loopback preview host**, not a relaxation.
- **New (implementation, 2026-07-18):**
  - Preview-start config lives on **Repository** (repo-first) with **ProjectProfile** fallback —
    D7 already names "Project Profile/Repository" as the source; this fixes the shape/precedence.
  - Playwright egress **scoped to the preview host + localhost only**, `test_automation` phase only.
  - Companion substitutes `[base_url]` post-bring-up (platform never guesses the bound port).

## 8. Task checklist (for `/BUILD_PLAN.md`)

- [ ] P3-09bR-1 — `Repository.preview_start` + `ProjectProfile.preview_start` JSON fields + migration + resolver helper (fail-loud on empty).
- [ ] P3-09bR-2 — `provision_preview_app` on the companion (bring-up + readiness + guaranteed teardown); `BuildReport.preview_url`.
- [ ] P3-09bR-3 — phase-scoped `playwright` server in `build_mcp_servers`; `assert_phase_allowlist(phase=…)` + `BUILD_ALLOWED_TOOLS` extension for `mcp__playwright__*`.
- [ ] P3-09bR-4 — companion substitutes `[base_url]`; add preview host to `EgressPolicy` for the run.
- [ ] P3-09bR-5 — `provision_preview`/`teardown_preview` activities wired into `BuildWorkflow` (record + PR link + compensation teardown).
- [ ] P3-09bR-6 — unit + acceptance tests (§6); companion-setup docs note the `@playwright/mcp` + browser prerequisite.
- [ ] (later, separate slice) suite **execution** + JUnit emission → the dormant `import_build_test_results` loop lights up.
