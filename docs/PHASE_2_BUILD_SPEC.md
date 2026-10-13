# Phase 2 Build Spec — Build Execution (local-companion runner → PR → CI, durably)

> **Purpose:** fix Phase 2's contracts (the CodeHost capability, the **local-companion
> runner** + managed-worktree edit surface, `run_build_task`, the Temporal build saga, the
> 07↔08 remediation loop, injection guardrails, webhook reconciliation, light multi-repo,
> acceptance) so Claude Code *implements* rather than *re-decides*. Same rule as Phases 0–1:
> contracts here don't change without updating this file; exact code is Claude Code's job.
>
> **Builds on Phases 0–1** — the spine (RLS state, Platform-State MCP, ClaudeDriver
> *planning*, Manifest Composer, Temporal `AgentRunWorkflow`, Gate/Approval), the
> Integration plane (`get_capability`, per-tenant `IntegrationConnection`, publish-to-SoR,
> reconciliation, traceability), and the **Rate governor** are done and **not re-opened**.
> Phase 2 adds the *Execution plane for real code* and the *CodeHost* capability.
>
> **Phase 2 goal (blueprint Part C):** real code — implementation/review/test producing
> **GitHub PRs, durably** — **without changing how a developer works day to day.** An
> `accepted` WorkItem (Phase-1 backlog) is driven by a **local-companion runner on the
> developer's own machine**, editing a **platform-managed git worktree** (a clean
> `feature/<key>` branch off the repo's base) so the developer **runs and tests the change
> locally, exactly as today, before any PR**. The platform owns the PR/merge SoR surface,
> the gates, durability, and the registry. This is the **stop-and-dogfood MVP**.

## 0. In / out of scope
**In:** the **CodeHost** capability (`codehost.*`) + GitHub connector (headless, per-tenant); the **local-companion runner** (a developer-machine daemon — the *only* topology in v1) + **enrollment/auth** + **managed git-worktree** edit surface + runner provisioning (toolchain, test DB, secrets inject); **remote Platform-State serving** so the companion uses the state tools without direct DB access (tenant binding + RLS stay server-side); **`ClaudeDriver.run_build_task`** scoped to the worktree; **Temporal build saga** (dispatch-to-companion, retries/idempotency/dead-letter/compensation, PG6); **build phases** implementation→review→test with the **REM-C/REM-W remediation loop** preserved; **secret scanning + egress allowlist** v1 (PG12/PG14); **human takeover** + **Git-webhook reconciliation** (PG10); **light multi-repo** (repo-per-WorkItem); **migrate agents 07 + 08**; (adjustable) **11 + 12**.
**Out (later phases):** the **server-side ephemeral runner** topology (kept as an optional future addition behind the same seam); Figma/Xray + design/test-mgmt + **per-PR preview environments** (P3); CodeIntel, **full multi-repo** (cross-repo DAG, API-contract artifact, live drift), brownfield-full (P4); secrets-vault/RBAC depth, **cloud runner fleet + gVisor/Firecracker sandbox hardening** (P5); Codex/Copilot drivers (P6). **No SoR write before its gate is APPROVED — ever** (#5/#8); for code the gated SoR write is the **PR merge** (§5).

---

## 1. CodeHost capability (the integration seam for Git — non-negotiable #9)

Business logic calls **capabilities, never vendors**: `codehost.*`, never `github.*`. Same shape as Phase 1's connectors, resolved per tenant via `get_capability`, **routed through the Rate governor**.

```python
# backend/integrations/capabilities.py  (extend)
class CodeHost(Protocol):                 # GitHub-shaped, vendor-free
    def get_branch(self, *, repo: str, name: str) -> BranchRef | None: ...
    def open_pull_request(self, *, repo: str, head: str, base: str, title: str,
                          body: str, draft: bool = True) -> PullRequestRef: ...   # idempotent by head
    def get_pull_request(self, *, pr_ref: str) -> PullRequest: ...                # read-through (live)
    def list_pr_files(self, *, pr_ref: str) -> list[str]: ...                     # review scope
    def set_commit_status(self, *, repo: str, sha: str, state: str, context: str,
                          description: str = "", target_url: str | None = None) -> None: ...
    def add_pr_comment(self, *, pr_ref: str, body: str) -> None: ...
    def merge_pull_request(self, *, pr_ref: str, method: str = "squash") -> PullRequest: ...  # gate-only
    def get_file(self, *, repo: str, path: str, ref: str) -> str: ...             # read-through
```

```python
@dataclass
class PullRequestRef:  # persisted into Artifact/WorkItem.external_ref (pointer, not body)
    sor: str = "git"        # SoR.GIT exists since P0
    repo: str = ""          # "owner/name"
    number: int = 0
    head: str = ""          # branch
    url: str = ""
    sha: str | None = None
```

- **Connector selection per tenant/repo:** `get_capability(tenant_id, "codehost") -> CodeHost` over `IntegrationConnection(capability="codehost", connector="github", scopes={"repo": "...", "default_base": "develop"}, token_ref, health)`. The CodeHost owns the **PR/merge/status/comment/webhook** surface.
- **Default connector (D1 — LOCKED):** `GithubCodeHost` over the **GitHub REST API**, headless per-tenant (GitHub App-installation token **or** PAT) via `token_ref` (the Phase-5 vault seam). Server-side, multi-tenant, headless — *not* a local `gh` CLI. GitHub MCP stays the optional agent-side transport.
- **Git side-effects (D2 — LOCKED, companion-aware):** the **working-copy edits and the local commit/push happen on the developer's machine** in the managed worktree (§3). The **platform owns the PR/merge SoR surface** — it opens the PR (or adopts a dev-opened one, register-don't-recreate), sets status, runs review, and performs the **gated merge** — via `CodeHost`. The engine never calls GitHub directly. `get_branch`/`open_pull_request` are idempotent (an existing branch/PR for a head is adopted, never duplicated).

---

## 2. Data-model deltas (extend Phases 0–1 — additive, RLS-aware, no breaking changes)

Every new table carries `tenant_id` + the standard RLS policy from its first migration (#6).

- **Repository** (exists since P0; now populated): `project, name("owner/repo"), default_base, connector, scopes, provenance`. **Light multi-repo (this phase):** a project has **N repos**; each carries its own base branch + CodeHost connection. (Full multi-repo — cross-repo DAG, API-contract artifact, drift — is **P4**.)
- **WorkItem** — `repo` FK → `Repository` (**which repo a task targets** — the light-multi-repo slice) and `takeover_flag` (human-takeover, PG10) **already exist in the P0 scaffold** — no migration needed; Phase 2 just exercises them. Build rides the existing `state` (`accepted → in_progress → in_review → done`) + `external_ref` (the PR pointer).
- **Artifact** — new **types**: `code` (`sor=git`, `external_ref`=`PullRequestRef`), `code_review` (findings doc, `sor=internal`), `test_report` (`sor=internal`). No schema change.
- **RemediationItem** = a **child WorkItem** (`parent`=story, `external_ref={"rem":"REM-C1","severity":"critical|warning","file":...,"line":N}`) — **its `type` is `task`, not `"remediation"`.** *Corrected 2026-09-17: there has never been a `remediation` member of `WorkItem.Type`, which is `epic · story · task · defect · test_case` (`backend/apps/workitems/models.py:9-19`). What was built creates these as tasks and identifies them by the `rem` key in `external_ref` (`build_activities.py:1089`). Code written against `type="remediation"` would match nothing.* — the 07↔08 loop as first-class DAG sub-work (BUILD_PLAN); a `code_review → code` `TraceEdge` records lineage.
- **RunnerEnrollment** (new — the local companion's identity): `tenant, project, developer(user), label, enroll_token_hash, repos(allowed), status(active/revoked), last_seen`. Scopes a developer-machine companion to a tenant+project+repos; the basis for auth (§3). No secret stored in clear (#token_ref seam).
- **WebhookDelivery** (new — idempotent ingest): `provider, delivery_id (unique/tenant), event, received_at, status` — dedups GitHub redeliveries; the Event Ledger records each reconciliation (§7).
- **IntegrationConnection** — now also `(tenant, "codehost") → github`, per repo.

---

## 3. Local-companion runner + managed worktree + `run_build_task` (the execution plane)

**Topology (D8 — LOCKED): local-companion only.** Execution happens on the **developer's own machine**, so the daily loop (write → unit-test → run the app → PR) is unchanged. The server-side ephemeral runner is a *later optional* topology behind the same seam (out of scope here). The **cloud fleet + gVisor/Firecracker** remain Phase-5.

- **The companion daemon** (`runner/companion/`, building on the P0 `runner/` scaffold): a small process the developer runs locally. It **enrolls** with the platform (RunnerEnrollment token → bearer/mTLS), then **pulls assigned build tasks** for its tenant/project/repos. It connects **outbound** to the platform (the platform never reaches into the dev machine).
- **Edit surface = managed git worktree (D9 — LOCKED, Option B).** For a task on repo `acme/api`, the companion runs `git worktree add ~/sdlc/<key> -b feature/<key> <base>` off the developer's existing clone (or clones once if absent) — an **isolated working tree on a clean task branch**, sharing the clone's object store. The developer **opens that folder in their IDE** to review, run, and **test the application locally before any PR**. Their main working copy and uncommitted work are never touched.
- **Multi-repo companion invocation (D5).** Each build task carries its routed repo (`BuildTask.repo` = `work_item.repo`), so on a **multi-repo project the companion needs one local clone per repo**. Start it with a repeatable mapping — `serve --worktrees ~/sdlc --repo acme/api=~/repos/api --repo acme/web=~/repos/web` — and `_run_build` provisions the worktree from the clone matching `task.repo`. **Single-repo projects are unchanged**: `serve --repo-path ~/repos/api --worktrees ~/sdlc` (the one clone serves every task). An unmapped repo **fails that build loudly** (reported failed, daemon keeps serving) rather than falling back to the wrong clone; a defense-in-depth check also refuses to push if the clone's `origin` doesn't match the routed repo. The **single `GITHUB_TOKEN` must have write access to every mapped repo** (per-tenant/per-repo vault is a Phase-5 seam — Bugs S.No 103).
- **Provisioning** (in the companion): ensure toolchain present, bring up an ephemeral **test DB** + private-registry config, **inject secrets** as env (from `token_ref`/the vault seam — never written into the repo), render **AGENTS.md** (Manifest Composer) into the worktree, apply the **egress allowlist** (§6). Worktree teardown (`git worktree remove`) is saga-compensated (§4).
- **Remote Platform-State serving (new):** in companion mode the agent's `mcp__platform-state__*` tools are served by the platform over a **remote, authenticated transport** (the enrollment token), **not** the stdio+direct-DB mode (the dev machine gets no DB creds). **Tenant binding + RLS stay server-side** (the agent still never passes a tenant). The stdio mode is retained for server-side/test runs.
- **`ClaudeDriver.run_build_task`** (implements the P0 stub; signature in `drivers/base.py` already takes `repo_workspace: Path`): launches the Agent SDK with the composed manifest, **filesystem tools (Read/Write/Edit/Bash) scoped to the worktree** + the **remote Platform-State tools**, under the **per-phase allowlist** (PG12 — build adds FS/Bash; **no CodeHost, no arbitrary network**). Returns `RunResult` (workspace diff summary, test/lint results, proposed branch; `cost_usd` metered).
- **Order of side-effects (companion-driven, control-plane-governed):** agent edits worktree → run tests/lint locally → **secret-scan** (§6, block on hit) → commit (Conventional Commits) → push `feature/<key>` → register a `code` Artifact (`sor=git`) → the **platform opens the draft PR** via `CodeHost` + `set_commit_status`. The **pushed branch + draft PR are staging**; the gated write is the **merge** (§5). The developer may instead commit/push by hand (companion still reports it; §7 reconciles).

---

## 4. Temporal build saga (durable, dispatch-to-companion — PG6)

A new **`BuildWorkflow`** (sibling to `AgentRunWorkflow`), idempotent by `run_id`, durable across a runner that may be **offline/slow** (it's a laptop):

```
resolve repo+enrollment → dispatch_build_task(companion) → await companion result
  → run_code_review(08) → [remediation loop §5] → MERGE GATE (Approval, reviewer)
  → merge_pr (CodeHost) → transition_work_item(done) → release worktree
```

- **Dispatch + await:** the workflow hands the build task to an enrolled companion (durable task queue / signal) and **waits** for the companion to report (agent ran, tests passed, branch pushed, `code` artifact registered). Companion offline past a timeout → the run parks for **human takeover** (§7), never fails silently.
- **Retries & idempotency:** Temporal retries activities; cores are idempotent (re-opening a PR/branch adopts the existing one; re-merging a merged PR is a no-op; re-dispatching re-uses the existing worktree/branch). The acceptance **mid-run failure** (§9) replays without duplicating branch/PR/merge.
- **Compensation (saga):** on abort, **worktree teardown** is attempted; a pushed-but-unmerged branch/draft PR is left for human disposition (register-don't-recreate, never force-deleted); the WorkItem returns to `in_progress`.
- **Dead-letter:** after max attempts → run flagged `failed`, Event logged, takeover/triage signal opened.
- **Gates are signals, not hooks (#2):** the merge gate is a control-plane `Approval`; `decide_gate` signals the workflow (the P0 mechanism) — identical across engines.

---

## 5. Build phases + the 07↔08 remediation loop (preserve verbatim — migration-spec §6)

The loop is the product's intelligence; **reused, not reinvented.** Legacy → platform mapping:

- **Implementation (07)** runs in the **companion worktree** (§3) and **proposes** a change: code + tests (≥**90%** new-line coverage, verbatim), Conventional-Commit messages, `feature/<key> → <base>`. The developer **runs/tests it locally** throughout. Its legacy **Human Gates** (session-start, architecture-deviation, new-dependency, destructive-migration, task-completion) become **control-plane Approvals** (no "reply APPROVED" prose — the §8 sweep enforces this). Track-awareness (Greenfield / UI-Modernization / Legacy-Transformation / Microservices) preserved verbatim.
- **Code Review (08)** reviews the PR across its **eleven dimensions** (verbatim), reading scope via `codehost.list_pr_files`/`get_file`, and emits a `code_review` artifact + **REM-C / REM-W / REM-S** findings. Its **Remediation Gate** (Options A/B/C) drives the loop.
- **Remediation loop:** each **REM-C/REM-W** → a **child WorkItem** (§2). Implementation **re-runs in Remediation Mode** in the same worktree (criticals then warnings; REM-S excluded); the developer re-tests locally; the **Re-Review Protocol** re-reviews only changed files. Loop repeats until **APPROVED / APPROVED WITH CONDITIONS** (legacy "Option C") — i.e., the merge-gate Approval becomes grantable. Only then does §4 **merge**.
- **Gate roles (D6 — LOCKED, split):** 07 task-completion → **`tech_lead`**; 08 remediation + **merge** → a distinct **`reviewer`** role (segregation of duties — the change's approver is not the implementer's lead). Seed both roles.
- **§8 reference sweep must pass** for both agents: inputs reroute (backlog/acceptance-criteria → the accepted WorkItem + `get_context()`; architecture/UX/intelligence → `get_artifact()`; CLAUDE.md → AGENTS.md); outputs reroute (code/PR → the companion-push + control-plane CodeHost step; findings → `code_review` artifact + remediation child WorkItems; phase advance → the Approval). Store at `/agents/07_implementation/agent.md` and `/agents/08_code_review/agent.md`; add per-agent run tests.

---

## 6. Injection guardrails v1 — secret scanning + egress allowlist (PG12/PG14)

Initial defenses; full sandbox hardening is **Phase 5** (D3).

- **Honest trust note (local-companion):** the runner is the **developer's own trusted machine**, so the *isolation* guarantees are weaker than a server/cloud sandbox — the strong gVisor/Firecracker/no-prod-net story is the server-runner + Phase-5 path. v1 here is **secret-scan-before-push + egress allowlist + per-phase tool allowlist**, which is the right bar for a developer-trusted runner.
- **Secret scanning:** before any commit/push, scan the worktree diff for credentials (entropy + known key formats). A hit **blocks the push/PR**, logs an Event — secrets never reach GitHub.
  - **Precision obligation (added 2026-08-17).** The spec originally said only *what* to detect, with no false-positive budget — and the entropy half then blocked five legitimate builds across two tenants, each "fixed" by adding one more narrow exception. The rule now: **the entropy heuristic scores string LITERALS only** — quoted in any file, or unquoted in a config file or a comment. An unquoted value in source code is an expression (a call, a variable, an attribute chain) and is never a credential, because a hardcoded credential in code is always quoted. The high-precision format patterns (AKIA…, `ghp_`…, PEM, JWT) are unaffected and run everywhere. A literal high-entropy value in a **config** file is a leak even when it is a dev or CI one (Bugs S.No 193) — the scanner is deliberately not weakened there. See `runner/companion/guardrails.py::_scans_bare_values`, pinned by the false-positive/true-positive corpus in `backend/tests/test_guardrails.py`; every new false positive gets a corpus row.
  - **On a block:** the build fails and nothing is pushed. It is **not** a merge gate and no triage object is created (the earlier wording here promised "opens triage", which was never built and would have nothing to gate — no branch exists). The recourse is one bounded auto-retry seeded with the redacted findings, then a terminal failure (`handle_secret_block_core`, same two-tier shape as remediation-exhaustion, S.No 161). The redacted findings are persisted on the run (decision **D6**) so a block is diagnosable after the fact.
- **Egress allowlist:** the build step targets only approved hosts (the tenant's GitHub, declared registries, the Anthropic API, the platform). Enforced via the companion's config; denials logged.
- **Per-phase tool allowlist (PG12):** the agent gets only build tools (FS/Bash + remote Platform-State; **no CodeHost, no arbitrary network**). Untrusted SoR/tool content is data, never instructions; the merge is human-gated.

---

## 7. Human takeover + Git-webhook reconciliation (PG10) — the primary collaboration path

In local-companion mode this is the **normal** path, not an edge case.

- **Takeover:** a developer can take a WorkItem over (`WorkItem.takeover=true`) and just **work in the worktree by hand** — commit, push, iterate locally — exactly as today. The saga pauses automated steps for that item and resumes on signals. Dead-lettered runs route here.
- **Webhook ingestion:** a signed endpoint (`POST /api/webhooks/github/<tenant_id>/`) **verifies the signature**, dedups by delivery id (**WebhookDelivery**), then **reconciles**: `push` updates the `code` Artifact's `external_ref.sha` and logs an Event (human commits register, never overwrite — register-don't-recreate); `pull_request` merged/closed transitions the WorkItem; CI `status` round-trips into the ledger. Bodies are read-through (#3). (P4 *live drift gates* build on this; P2 only reconciles.) *Corrected 2026-09-17: this line gave the path without its **tenant segment**. What shipped is `webhooks/github/<uuid:tenant_id>/` (`backend/api/urls.py:122`) — the tenant is in the path because the request is signature-authenticated with no session to carry it. A webhook configured against the path as written here would never reach the platform.*

---

## 8. Agent migration — 07 Implementation + 08 Code Review (and 11/12)

Same **75 / 15 / 10** discipline + **§8 sweep** that gated agents 01–04, 06. **07** and **08** per §5 — the remediation loop, eleven review dimensions, ≥90% coverage, track-awareness, teaching patterns **reused verbatim**; every data reference (incl. mid-step) rerouted; glue (frontmatter→AgentSpec, command→phase-trigger, Human Gate→Approval) replaced. **11 CI/CD + 12 Deployment (D5 — LOCKED: after the 07/08 core):** wire **CI status round-trip** in the 07/08 slice now; migrate the 11/12 bodies once implementation↔review↔merge is green (deployment stays gated). Placement may move to a later P2 slice or P3 without reopening §1–§7.

---

## 9. Phase 2 acceptance (thin slice to demo)

- **Greenfield happy path (real local worktree + live GitHub; skips without creds; self-cleaning):** an `accepted` WorkItem targeting a project **Repository** → `BuildWorkflow` dispatches to a companion (in-test: a real `git worktree` off a local clone of the test repo) → **stub build driver** writes a canned diff + passing tests into the **worktree** (no live engine) → secret-scan passes → commit + push `feature/<key>` → platform opens **draft PR** (`sor=git`, `external_ref` set) → `get_pull_request` returns it live → CI **status round-trips** into the ledger → Code Review emits findings → one **REM-C** remediation child WorkItem resolved in the worktree (targeted re-review) → **merge gate APPROVED by a `reviewer`** → PR **merges** → WorkItem `done` → worktree removed. Cleanup: close PR + delete branch.
- **Durability:** a **forced mid-run failure** (kill after push, before merge) recovers **idempotently** — replay duplicates no branch/PR/merge.
- **Developer-in-the-loop / takeover:** a **human commit** pushed to the worktree branch reconciles via the **GitHub webhook** (the `code` Artifact's `external_ref.sha` updates; Event logged) without duplicates; a taken-over WorkItem pauses automation.
- **Light multi-repo:** two WorkItems targeting **two different repos** in one project each build on their own worktree/branch/PR without cross-contamination.
- **Invariants preserved:** **no PR merges before its gate is APPROVED** (gate-then-merge); RLS holds (a second tenant sees no repos/PRs/runs/enrollments); idempotent saga; secret-scan blocks a planted credential; the per-phase allowlist holds; **tenant binding + RLS remain server-side even though the agent ran on the dev machine**. Tests + demo green; `/BUILD_PLAN.md` ticked; `/docs` updated if a contract changed.

---

## 10. Decisions (LOCKED)
- **D1 — CodeHost transport:** headless **GitHub REST**, per-tenant, rate-governed (parity with Phase-1 D1). Server-side/headless, not a local `gh` CLI; GitHub MCP stays the optional agent-side transport.
- **D2 — Git side-effects (companion-aware):** working-copy edits + local commit/push happen on the **developer's machine** in the managed worktree; the **platform owns the PR/merge SoR surface + gates** via `CodeHost`. The engine never calls GitHub directly.
- **D3 — Sandbox depth v1:** secret-scan + egress allowlist + per-phase allowlist on a **developer-trusted runner**; gVisor/Firecracker + no-prod-net (server/cloud) → Phase 5.
- **D4 — Gated SoR write for code = PR merge** (branch + draft PR are staging).
- **D5 — 11/12 after the 07/08 core.**
- **D6 — Split gate roles:** 07 → `tech_lead`; 08 remediation + merge → `reviewer`.
- **D7 — Toolchain/test-DB source:** from the **Project Profile/Repository** record; per-repo manifest-file is P4.
- **D8 — Runner topology: local-companion only** (developer's machine); server-side ephemeral runner is a later optional topology behind the same seam.
- **D9 — Edit surface: platform-managed git worktree** (Option B) — clean `feature/<key>` branch off base, isolated from the dev's main working copy; the developer runs/tests it locally before PR.
- **D10 — Multi-repo scope: light repo-per-WorkItem in P2** (`WorkItem.repo`, N repos per project, per-repo CodeHost); full multi-repo (cross-repo DAG, API-contract, drift) stays **P4**.
