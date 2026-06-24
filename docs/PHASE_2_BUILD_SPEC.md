# Phase 2 Build Spec — Build Execution (Code → PR → CI, durably)

> **Purpose:** fix Phase 2's contracts (the CodeHost capability, build-runner provisioning,
> `run_build_task`, the Temporal build saga, the 07↔08 remediation loop, injection
> guardrails, webhook reconciliation, acceptance) so Claude Code *implements* rather than
> *re-decides*. Same rule as Phases 0–1: contracts here don't change without updating this
> file; exact code is Claude Code's job.
>
> **Builds on Phases 0–1** — the spine (RLS state, Platform-State MCP, ClaudeDriver
> *planning*, Manifest Composer, Temporal `AgentRunWorkflow`, Gate/Approval), the
> Integration plane (capability seam `get_capability`, per-tenant `IntegrationConnection`,
> publish-to-SoR, reconciliation, traceability), and the **Rate governor** (every connector
> call already routes through it) are done and **not re-opened**. Phase 2 adds the
> *Execution plane for real code* and the *CodeHost* capability.
>
> **Phase 2 goal (blueprint Part C):** real code — implementation/review/test producing
> **GitHub PRs, durably**. A `proposed/accepted` WorkItem (Phase 1 backlog) is driven to a
> branch + draft PR by a **build runner**; tests run; the **Code Review** agent reviews and
> the **07↔08 remediation loop** runs as gated sub-work; on the **merge gate** the PR merges;
> CI status round-trips; a forced **mid-run failure recovers idempotently** via a Temporal
> saga. This is the **stop-and-dogfood MVP** — greenfield idea→PR is complete after Phase 2.

## 0. In / out of scope
**In:** the **CodeHost** capability (`codehost.*`) + GitHub connector (headless, per-tenant); **build runners** (local-first, sandboxed *workspace*, runner provisioning: toolchain, test DB, private registry, secrets inject, egress allowlist); **`ClaudeDriver.run_build_task`** (the build half of the engine seam, repo-scoped); **Temporal build saga** (long-running, retries/idempotency/dead-letter/compensation, PG6); **build phases** implementation→review→test with the **REM-C/REM-W remediation loop** preserved; **secret scanning + egress allowlist** (initial prompt-injection guardrails, PG12/PG14 v1); **human takeover** state + **Git-webhook reconciliation** (PG10); **migrate agents 07 (Implementation) + 08 (Code Review)**; (adjustable) **migrate 11 (CI/CD) + 12 (Deployment)**.
**Out (later phases):** Figma/Xray + design/test-mgmt loops (P3); CodeIntel, multi-repo, live drift gates (P4); secrets-vault/RBAC depth, **cloud runner fleet + gVisor/Firecracker hardening** (P5 Cloud-Migration); Codex/Copilot drivers (P6). **No SoR write before its gate is APPROVED — ever** (LOCKED #5/#8); for code the gated SoR write is the **PR merge** (see §5).

---

## 1. CodeHost capability (the integration seam for Git — non-negotiable #9)

Business logic calls **capabilities, never vendors**: `codehost.*`, never `github.*`. Same shape as Phase 1's `docstore.*`/`tasktracker.*`, resolved per tenant via `get_capability`, and **routed through the Rate governor** (connectors never build their own sockets).

```python
# backend/integrations/capabilities.py  (extend)
class CodeHost(Protocol):                 # GitHub-shaped, vendor-free
    def ensure_branch(self, *, repo: str, name: str, base: str) -> BranchRef: ...     # idempotent
    def open_pull_request(self, *, repo: str, head: str, base: str, title: str,
                          body: str, draft: bool = True) -> PullRequestRef: ...        # idempotent by head
    def get_pull_request(self, *, pr_ref: str) -> PullRequest: ...                     # read-through (live)
    def list_pr_files(self, *, pr_ref: str) -> list[str]: ...                          # review scope
    def set_commit_status(self, *, repo: str, sha: str, state: str, context: str,
                          description: str = "", target_url: str | None = None) -> None: ...
    def add_pr_comment(self, *, pr_ref: str, body: str) -> None: ...                   # review findings
    def merge_pull_request(self, *, pr_ref: str, method: str = "squash") -> PullRequest: ...  # gate-only
    def get_file(self, *, repo: str, path: str, ref: str) -> str: ...                  # read-through
```

```python
@dataclass
class PullRequestRef:  # persisted into Artifact.external_ref / WorkItem.external_ref (pointer, not body)
    sor: str = "git"        # "git" (SoR.GIT exists since P0)
    repo: str = ""          # "owner/name"
    number: int = 0         # PR number
    head: str = ""          # branch
    url: str = ""
    sha: str | None = None
```

- **Connector selection per tenant:** `get_capability(tenant_id, "codehost") -> CodeHost` over `IntegrationConnection(capability="codehost", connector="github", scopes={"repo": "...", "default_base": "develop"}, token_ref, health)`. No connection ⇒ `CapabilityUnavailable` (a build cannot proceed without a CodeHost — surfaced, not silently skipped).
- **Default connector (D1 — recommend, mirrors Phase-1 D1):** `GithubCodeHost` over the **GitHub REST API**, headless per-tenant (GitHub App installation token **or** PAT) via `token_ref` indirection (the Phase-5 vault seam). The GitHub **MCP** stays the *optional agent-side* transport; the platform's control-plane writes go through this connector. Interface identical either way.
- **Idempotency / register-don't-recreate (B1):** `ensure_branch`/`open_pull_request` are idempotent — an existing branch/PR for the same head is returned, never duplicated. Reconciling an existing repo registers PRs/branches as pointers, creating nothing (the §7 webhook path is the live-update half).
- **The platform owns Git side-effects, not the engine (#2):** branch push + PR open/merge/status are **control-plane activities** calling `CodeHost`. The build agent writes code into its workspace and runs tests; it does **not** shell `gh`/`git push` or call GitHub directly (D2). This keeps gates in the control plane and behaviour identical across engines.

---

## 2. Data-model deltas (extend Phases 0–1 — additive, RLS-aware, no breaking changes)

Every new table carries `tenant_id` + the standard RLS policy from its first migration (#6).

- **Repository** (exists since P0 scaffold; now populated): `project, name("owner/repo"), default_base, connector, scopes, provenance`. A project has ≥1 repo (multi-repo is P4; v1 = one).
- **Artifact** — new **types**: `code` (the implemented change; `sor=git`, `external_ref` = `PullRequestRef`), `code_review` (the review findings document; `sor=internal`), `test_report` (coverage/results; `sor=internal`). No schema change — `sor=git`, `status`, `external_ref` already exist.
- **WorkItem** — add `takeover bool default false` (human-takeover state, PG10) and use `external_ref` for the PR pointer once a story is in build. New lifecycle usage: `accepted → in_progress → in_review → done` (build phases ride the existing `state`; no new column beyond `takeover`).
- **RemediationItem** = a **child WorkItem** (`parent` = the story), `type="remediation"`, carrying `external_ref={"rem": "REM-C1", "severity": "critical|warning", "file": "...", "line": N}`. The 07↔08 loop is thus first-class DAG sub-work (BUILD_PLAN); a `code_review` artifact → `code` artifact `TraceEdge(rel="tests")`/`("implements")` records the lineage.
- **WebhookDelivery** (new — idempotent ingest): `provider, delivery_id (unique per tenant), event, received_at, status`. Dedups GitHub redeliveries; the payload is processed once, then the Event Ledger records the reconciliation (no body stored beyond what's needed to reconcile — #3).
- **IntegrationConnection** — now also `(tenant, "codehost") → github`.

---

## 3. Build runner + provisioning + `run_build_task` (the execution plane for code)

**Runner topology (LOCKED — local-first):** Phases 0–4 use a **local runner**; the **cloud fleet + gVisor/Firecracker** are the Phase-5 Cloud-Migration workstream. A build runner is an **ephemeral, isolated workspace** (local container/dir) — never a source of truth; the workspace is **discarded after the run** (#1 local files ephemeral; state = pointers/events).

- **Provisioning** (`backend/orchestration/runner.py`, a Temporal activity): clone the repo at the task's base branch into a fresh workspace; install the **toolchain** declared by the Project Profile/repo; bring up an ephemeral **test DB** and **private-registry** config; **inject secrets** as env from `token_ref`/the vault seam (never written to the repo); render **AGENTS.md** (Manifest Composer) into the workspace; apply the **egress allowlist** (§6). Tear-down always runs (saga compensation, §4).
- **`ClaudeDriver.run_build_task`** (implements the P0 stub, signature already in `drivers/base.py`): launches the Agent SDK with the composed manifest, **filesystem tools (Read/Write/Edit/Bash) scoped to `repo_workspace`** + the **Platform-State MCP** (tenant bound by the control plane). `allowed_tools` is the **per-phase allowlist** (PG12) — build phases add FS/Bash; **CodeHost is *not* exposed to the agent** (D2). Returns `RunResult` whose `outputs` carry the workspace diff summary, test/lint results, and proposed branch name; `cost_usd` metered.
- **Order of side-effects (control plane, post-run):** read the workspace diff → **secret-scan** (§6, block on hit) → commit (Conventional Commits) → `codehost.ensure_branch` → push → `codehost.open_pull_request(draft=True)` → register a `code` Artifact (`sor=git`, `external_ref`=PR) → `set_commit_status`. The **draft PR + pushed branch are staging**, not a gated SoR write; the gated write is the **merge** (§5).
- **`get_driver`/`get_object_store` stay injectable** (tests swap a stub driver that writes a canned diff into the workspace — no live engine, mirroring the P0/P1 acceptance pattern).

---

## 4. Temporal build saga (durable, long-running — PG6)

A new **`BuildWorkflow`** (sibling to `AgentRunWorkflow`), idempotent by `run_id`, composed of activities each wrapping an idempotent core (the `_boundary` pattern from P0):

```
provision_runner → run_build_task(implementation) → run_tests → secret_scan
  → commit+push+open_pr (CodeHost) → set_status
  → run_code_review(08) → [remediation loop §5] → MERGE GATE (Approval)
  → merge_pr (CodeHost) → transition_work_item(done) → teardown_runner
```

- **Retries & idempotency:** Temporal retries each activity; cores are idempotent (re-running `open_pr`/`ensure_branch` returns the existing PR/branch; re-running `merge` on a merged PR is a no-op). The **forced mid-run failure** in the acceptance slice (§9) is recovered by Temporal replay without duplicating a branch/PR/merge.
- **Compensation (saga):** on abort, **teardown_runner always runs** (workspace discarded); a pushed-but-unmerged branch/draft PR is left for human disposition (register-don't-recreate, never force-deleted) and the run is marked; the WorkItem returns to `in_progress`.
- **Dead-letter:** after max attempts an activity dead-letters → the run is flagged `failed`, an Event is logged, and a control-plane signal opens a takeover/triage path (§7) — poison runs never silently retry forever.
- **Gates are signals, not hooks (#2):** the merge gate is a control-plane `Approval`; `decide_gate` signals the workflow (the exact P0 mechanism), so behaviour is identical across engines.

---

## 5. Build phases + the 07↔08 remediation loop (preserve verbatim — migration-spec §6)

The loop is the product's intelligence; it is **reused, not reinvented**. Mapping legacy → platform:

- **Implementation (07)** runs in the build runner (§3) and **proposes** a change: code in the workspace + tests (target **≥90% new-line coverage**, verbatim), Conventional-Commit messages, `feature/<key>-slug → <default_base>`. Its legacy **Human Gates** (session-start, architecture-deviation, new-dependency, destructive-migration, task-completion) become **control-plane Approvals** (no "reply APPROVED" in prose; the §8 sweep enforces this). Track-awareness (Greenfield / UI-Modernization / Legacy-Transformation / Microservices) is preserved verbatim.
- **Code Review (08)** reviews the PR across its **eleven dimensions** (verbatim), reading scope via `codehost.list_pr_files`/`get_file` (read-through), and emits a `code_review` artifact + structured findings **REM-C (critical) / REM-W (warning) / REM-S (suggestion)**. Its **Remediation Gate** (Options A/B/C) is the control-plane gate that drives the loop.
- **Remediation loop:** each **REM-C/REM-W** becomes a **child WorkItem** (`type="remediation"`, §2). **Implementation re-runs in Remediation Mode** (skips session-start gate; resolves criticals then warnings; REM-S excluded), then the **Re-Review Protocol** runs a **targeted** re-review of only the changed files. The loop repeats until the review resolves to **APPROVED / APPROVED WITH CONDITIONS** (legacy "Option C") — represented as the merge-gate Approval being grantable. Only then does §4 proceed to **merge**.
- **Gate roles (D6 — recommend):** implementation task-completion gate → **`tech_lead`** (consistent with migrated agent 06); code-review remediation/merge gate → **`tech_lead`**. Confirm before coding the AgentSpec seed.
- **§8 reference sweep must pass** for both agents (no `TASKS.md`/`docs/…`/`CLAUDE.md`/"reply APPROVED"): inputs reroute — backlog/acceptance-criteria → the **accepted WorkItem** + `get_context()`; architecture/UX/intelligence → `get_artifact()`; CLAUDE.md → the rendered **AGENTS.md**; outputs reroute — code/PR → the **control-plane CodeHost step**, findings → the `code_review` artifact + remediation child WorkItems, phase advance → the **Approval**. Store at `/agents/07_implementation/agent.md` and `/agents/08_code_review/agent.md`; add per-agent run tests (read inputs from the platform; produce the expected artifacts/sub-work; open the `tech_lead` gate).

---

## 6. Injection guardrails v1 — secret scanning + egress allowlist (PG12/PG14)

Initial defenses; the **full sandbox hardening (gVisor/Firecracker, no-prod-net) is Phase 5** (D3).

- **Secret scanning:** before any commit/push, scan the workspace diff for credentials (high-entropy strings, known key formats). A hit **blocks the PR**, logs an Event, and opens a triage path — secrets never reach GitHub.
- **Egress allowlist:** the runner may reach only approved hosts (the tenant's GitHub, declared package registries, the Anthropic API, the platform). Everything else is denied at the runner boundary. v1 enforces via the runner's network config + an allowlist in settings; deny is logged.
- **Per-phase tool allowlist (PG12):** the agent gets only its phase's tools (build = FS/Bash + Platform-State MCP; **no CodeHost, no arbitrary network**). Untrusted SoR/tool content is treated as data, never instructions; sensitive writes (merge) require the human gate.

---

## 7. Human takeover + Git-webhook reconciliation (PG10)

- **Takeover:** a human can take over a WorkItem mid-build (`WorkItem.takeover=true`); the saga pauses automated steps for that item and waits for human/webhook signals. Resuming clears the flag. Dead-lettered runs (§4) route here.
- **Webhook ingestion:** a signed GitHub webhook endpoint (`POST /api/webhooks/github/`) **verifies the signature**, dedups by delivery id (**WebhookDelivery**, §2), then **reconciles**: `push`/`pull_request`/`status` events update the registry — human commits on a tracked branch update the `code` Artifact's `external_ref.sha` and log an Event; a merged/closed PR transitions the WorkItem; CI `status` round-trips into the ledger. **Register-don't-recreate** throughout (a human commit is registered, never overwritten). Bodies are read-through (#3).
- This closes the loop with the Phase-1 invariants: webhooks → ingestion → ledger (the P4 *live drift gates* build on this; P2 only reconciles).

---

## 8. Agent migration — 07 Implementation + 08 Code Review (and 11/12)

Same **75 / 15 / 10** discipline + **§8 sweep** that gated agents 01–04, 06.
- **07 Implementation** and **08 Code Review** per §5 above — the remediation loop, the eleven review dimensions, the ≥90% coverage bar, track-awareness, and the teaching patterns are **reused verbatim**; every data reference (incl. mid-step) is rerouted; invocation glue (frontmatter→AgentSpec, command→phase-trigger, Human Gate→Approval) is replaced.
- **11 CI/CD + 12 Deployment (D5 — adjustable):** BUILD_PLAN places them in Phase 2. **Recommend:** wire **CI status round-trip** (commit-status + checks) as part of the 07/08 slice now, and migrate the **11/12 agent bodies after** the implementation↔review↔merge core is green (they produce pipeline + release artifacts; deployment stays gated). Their placement may move to a later Phase-2 slice or P3 without reopening §1–§7.

---

## 9. Phase 2 acceptance (thin slice to demo)

- **Greenfield happy path (live GitHub, skips without creds, self-cleaning — Phase-1 pattern):** take an `accepted` WorkItem → `BuildWorkflow` with a **stub build driver** (writes a canned diff + passing tests into the workspace; no live engine) → secret-scan passes → branch pushed + **draft PR opened** (`sor=git`, `external_ref` set) → `get_pull_request(KEY)` returns it live → CI **status round-trips** into the ledger → Code Review emits findings → one **REM-C** remediation child WorkItem is resolved (Remediation Mode → targeted re-review) → **merge gate APPROVED** → PR **merges** → WorkItem `done`. Cleanup: close PR + delete branch.
- **Durability:** a **forced mid-run failure** (kill the activity after push, before merge) is **recovered idempotently** — replay does not duplicate the branch/PR/merge (idempotent cores + saga).
- **Brownfield/takeover:** a **human commit** delivered via the **GitHub webhook** reconciles into the registry (the `code` Artifact's `external_ref.sha` updates; Event logged) without creating duplicates; a taken-over WorkItem pauses automation.
- **Invariants preserved:** **no PR merges before its gate is APPROVED** (gate-then-merge); RLS holds (a second tenant sees no repos/PRs/runs); idempotent saga (re-run creates nothing new); secret-scan blocks a planted credential; the per-phase allowlist holds (agent has no CodeHost/network). Tests + demo green; `/BUILD_PLAN.md` ticked; this file updated if a contract changed.

---

## 10. Open decisions to confirm (before coding the affected task)
- **D1 — CodeHost transport:** headless **GitHub REST** for control-plane writes (recommend, parity with Phase-1 D1) vs GitHub MCP. Interface identical either way; MCP stays the optional agent-side transport.
- **D2 — Who performs Git side-effects:** the **platform control plane** via `CodeHost` (recommend — gates in control plane, #2) vs the agent shelling `git`/`gh`. Recommend platform; agent only edits the workspace + runs tests.
- **D3 — Sandbox depth in v1:** local container isolation + **egress allowlist + secret scanning** (recommend) now; **gVisor/Firecracker + no-prod-net** deferred to Phase 5 Cloud-Migration.
- **D4 — Gated SoR write for code = PR merge:** branch push + draft PR are *staging*; the **merge** is the gate-then-write (recommend/confirm).
- **D5 — 11/12 placement:** CI status round-trip in P2 now; **migrate agents 11/12 after** the 07/08 core (adjustable to a later P2 slice or P3).
- **D6 — Gate roles:** 07 task-completion + 08 remediation/merge → **`tech_lead`** (recommend; confirm vs a distinct `reviewer` role).
- **D7 — Test DB / toolchain source:** provisioning reads toolchain + test-DB needs from the **Project Profile/Repository** record (recommend) vs a per-repo manifest file (the manifest-file route is P4 multi-repo).
