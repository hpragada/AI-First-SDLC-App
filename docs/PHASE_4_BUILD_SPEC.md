# Phase 4 Build Spec — Brownfield-Full & Multi-Repo (onboard, intelligence, contracts, drift)

> **Purpose:** fix Phase 4's contracts (the **CodeIntel** capability + built-in SOTA analyzer,
> the **Knowledge Index** + embedding-provider seam, **full multi-repo** + the **API-Contract**
> artifact + cross-repo edges, the **full onboarding** orchestration with gap-fill, **live drift
> detection**, and the migrated 00-series agents) so Claude Code *implements* rather than
> *re-decides*. Same rule as Phases 0–3: contracts here don't change without updating this file;
> exact code is Claude Code's job.
>
> **This is the client front door.** Phase 4 is how a real client brings an existing project onto
> the platform and resumes the lifecycle from the middle. Accuracy and "works for every client
> out of the box" outrank breadth.
>
> **Builds on Phases 0–3 — not re-opened.** The spine (RLS state, Platform-State MCP, Manifest
> Composer, Temporal workflows, Gate/Approval), the Integration plane (`get_capability`,
> connectors, publish, **reconciliation**, **traceability**, rate governor), the **P1
> brownfield-lite onboarding** (`integrations/onboarding.py`: static-file extraction +
> Atlassian register-don't-recreate), the **P2 local-companion runner + managed worktree +
> remote Platform-State + signed Git-webhook reconcile**, and the **P3 design/test/quality
> plane** are all done and frozen. Phase 4 *extends* them.

## 0. In / out of scope
**In:** the **CodeIntel** capability (`codeintel.*`) + a **built-in SOTA static analyzer** (default) + **Repowise** optional connector behind the same seam; the **Knowledge Index** (chunk-level store + an **EmbeddingProvider** seam — Voyage / Gemini — over an **always-on no-cost structural+keyword retrieval baseline**); **full multi-repo** (N repos per project, per-repo manifest scoping, shared memory) + the **API-Contract** artifact + **cross-repo DAG edges**; the **full onboarding** orchestration (discover → register → reconcile → **gap-fill** → gap report → **resume mid-pipeline**); **live drift detection** (webhook → ledger → `drift_gate` + change-impact via traceability); **migrate agents 00 Onboarding, 00b Context Bridge, 00c Intelligent Context Extractor**; **retire 00d Snapshot**. The thin slice: onboard a split FE/BE project, resume mid-pipeline, change a contract → drift gates.
**Out (later phases):** semantic/AST contract *diffing* (v1 drift is contract-version + pointer/hash); the **cloud runner fleet** + server-side sandbox hardening (P5); RBAC/SoD depth, secrets-vault depth, immutable audit, GDPR erasure across embeddings, eval/quality harness (P5); Codex/Copilot drivers, DAG parallelism, notifications/dashboards, agents 13/14 (P6). **No SoR write before its gate is APPROVED — ever** (#5/#8); onboarding **registers pointers, never re-creates** what a live SoR already holds (B1).

---

## 1. CodeIntel capability — built-in SOTA analyzer + optional Repowise (D1)

Business logic calls **capabilities, never vendors**: `codeintel.*`, never `repowise.*`. Same shape as every other connector, resolved per tenant via `get_capability`. The **8-tool surface is fixed** so agents never change when the engine changes.

```python
# backend/integrations/capabilities.py  (extend)
class CodeIntel(Protocol):                              # engine-agnostic code intelligence
    def index(self, *, workspace: Path, repo: str, scope: dict | None = None) -> IntelIndex: ...
    def get_overview(self, *, repo: str) -> dict: ...                       # architecture summary, entry points
    def get_context(self, *, repo: str, targets: list[str]) -> dict: ...    # docs/ownership/decisions/freshness
    def get_risk(self, *, repo: str, targets: list[str]) -> dict: ...       # hotspot score, dependents, blast radius
    def get_why(self, *, repo: str, query: str = "") -> dict: ...           # architectural decisions governing X
    def search_codebase(self, *, repo: str, query: str) -> list[dict]: ...  # semantic search (Knowledge Index)
    def get_dependency_path(self, *, repo: str, frm: str, to: str) -> dict: ...
    def get_dead_code(self, *, repo: str) -> list[dict]: ...
    def get_architecture_diagram(self, *, repo: str, module: str | None = None) -> str: ...
```

- **Default connector — `BuiltinCodeIntel` (D1, LOCKED):** a no-license analyzer that matches the algorithmic SOTA Repowise targets, built from well-known libraries:
  - **Git analytics / hotspots** — churn × complexity per **Tornhill, *Software Design X-Rays*** (the same evidence base the legacy 00c cites): `git log`/blame/diff stats → hotspots, ownership, **bus-factor**, co-change, velocity. *Full parity; language-agnostic.*
  - **Dependency graph** — `tree-sitter` symbol/import extraction → `networkx` PageRank, Louvain **communities**, betweenness, coupling. *Parity where a parser exists (Python/TS-JS/Go/Java first); degrades gracefully to git+file signals for any language.*
  - **Code health** — dead-code reference analysis + cyclomatic complexity (`radon`-style).
  - **Architecture-decision archaeology** — ADR markers + commit-message/history mining.
  - **Auto-generated module docs** — produced by the platform's own **ClaudeDriver** (equal/better than a bundled LLM), topological order.
  - **Semantic search** — backed by the **Knowledge Index** embeddings (§2); falls back to the no-cost keyword baseline when no embedding key is set.
- **Optional connector — `RepowiseCodeIntel`:** registered behind `register_connector("codeintel","repowise")`; a tenant with Repowise selects it via its `IntegrationConnection` — **zero agent change** (same 8-tool surface). Parity with optional Atlassian/Figma/Xray.
- **Topology (D2, LOCKED):** code intelligence runs in the **P2 companion worktree** on the client's machine. The platform persists only the **index + code-intel artifacts + Knowledge-Index chunks** — never the source (#1/#3). The companion reports results over the remote Platform-State transport, exactly like the P2 build report.

---

## 2. Knowledge Index — chunk store + EmbeddingProvider seam + no-cost baseline (D3)

Populates the `retrieved_knowledge` the Manifest Composer renders (today a stub). **Retrieval works with zero external keys**; embeddings are an optional quality upgrade.

```python
# backend/knowledge/  (new)
class EmbeddingProvider(Protocol):
    name: str
    dim: int
    def embed(self, texts: list[str], *, kind: str = "document") -> list[list[float]]: ...

# adapters: VoyageEmbeddings (voyage-code-3, dim 1024) · GeminiEmbeddings
#           (gemini-embedding-001, dim 1536) · NullEmbeddings (no-op; baseline-only)
def retrieve(tenant_id, *, project_id, query, repo=None, k=8) -> list[dict]: ...
```

- **Always-on baseline (no creds):** a deterministic **structural + keyword/BM25** ranker over `KnowledgeChunk` rows (chunked artifact/intel text). This is what populates `retrieved_knowledge` by default — every client gets retrieval offline, at zero cost.
- **Optional embeddings (D3, LOCKED):** an `EmbeddingProvider` seam with **`voyage-code-3`** (purpose-built for code; **dim 1024**) and **`gemini-embedding-001`** (**dim 1536**; has a free tier) adapters, selected by `EMBEDDING_PROVIDER` + key in settings. When set, retrieval blends vector similarity with the keyword baseline; when unset, baseline-only. **`EMBEDDING_DIM` is provider-driven** (`settings.EMBEDDING_DIM`, default **1536** so Gemini fits the column as-is; set **1024** for Voyage and re-migrate). Free-tier terms must be confirmed on each provider's pricing page before relying on them.
- **`KnowledgeChunk`** (new, RLS) is the index store (§3); it carries the embedding so switching the *Artifact*-level `embedding` column is unnecessary (Artifact.embedding is left as-is). The chunk embedding column's dimension is `settings.EMBEDDING_DIM`.

---

## 3. Data-model deltas (extend Phases 0–3 — additive, RLS-aware, no breaking changes)

Every new table carries `tenant_id` + the standard forced-RLS `tenant_isolation` policy from its first migration (#6), with a DB-level isolation test.

- **`KnowledgeChunk`** (new): `tenant, project, artifact(FK), repo(FK, null), ordinal, text, token_count, embedding(Vector(settings.EMBEDDING_DIM), null), source`. The Knowledge Index; written during code-intel + artifact registration; read by `retrieve()`.
- **`DriftRecord`**: `tenant, project, **artifact(FK)**, kind(contract|pointer_hash), required_role, status(open|accepted|rejected), **detail**(json — hashes/semver/source), impacted(json — artifact/repo ids from the traceability walk), decided_by(user, null), decided_at, **comment**`.

  > *Field list corrected 2026-09-17 against `backend/apps/integrations/models.py:94-130`, which is what was built.* Four differences, all of which would break code written to this spec: it hangs off **`artifact`**, not `repo`; `source` and `summary` were never built — that content lives inside **`detail`**; there is a **`comment`** field this line omitted; and **`auto_reconciled` is not a status** — `Status` is `open · accepted · rejected` only, because nothing is silently applied to a system of record. The drift-gate lifecycle (§6) — the control-plane analog of `Approval` for changes that arrive **without** an agent run (so it does not distort `Approval`, which is bound to a `Run`/workflow).
- **Artifact** — new **types** (free-text, no schema change): `codebase_intelligence`, `dependency_graph`, `git_analytics`, `dead_code`, `architecture_decisions` (the five 00c layers), **`api_contract`** (versioned cross-repo contract — M2), `gap_report` (00 onboarding output). `api_contract` is `sor=internal`, registry-versioned; consumers read it **read-through** via `get_artifact` (no copied file).
- **Repository** (exists since P0; now fully exercised): `role` (frontend/backend/service), `stack_overrides`, `provenance`, `scopes`, `default_base`, `connector` — drive **per-repo manifest scoping** and the split/multi topology. No migration.
- **Cross-repo DAG edges (D5):** modeled with the **existing `TraceEdge`** between artifacts whose `repo_id` differs — e.g. a consumer repo's `code`/`api_spec` artifact `implements` the provider repo's `api_contract` artifact — plus **`WorkItem.depends_on`** (already a repo-agnostic UUID list) across repos. No new edge table.
- **Project** — `repo_topology` (`single|split|multi`, exists) is now exercised for split/multi; the registry, traceability graph, and Knowledge Index are **project-scoped** so they are the shared cross-repo memory (M3).
- **No change** to the P1 `SourceDocument`, P2 `RunnerEnrollment`/`WebhookDelivery`, or the gate/approval schemas — Phase 4 reuses them.

---

## 4. Migrated agents — 00 Onboarding, 00b Context Bridge, 00c Intelligent Context Extractor (00d retired)

Same **75 / 15 / 10** discipline + **§8 reference sweep** that gated every prior agent. Bodies stored at `/agents/<key>/agent.md`; AgentSpecs already cataloged with gate roles (`catalog.py`): **00→`product_owner`, 00b→`architect`, 00c→`tech_lead`**. Per-agent run tests + the sweep (`grep` for `.md`/`docs/`/`tasks.md`/`CLAUDE.md`/`reply approved`/`/sdlc:`) must be clean.

- **00c Intelligent Context Extractor** (client-facing name preserved) — keep verbatim: the **Codebase Intelligence Architect** persona + Evidence Base (Tornhill, Chidamber-Kemerer, Lehman), the **five intelligence layers**, the hotspot/dead-code/decision reasoning, and the **8-tool** reference. Reroute: the engine (`repowise init/serve`, MCP :7337) → the **`codeintel.*` capability** (built-in default, Repowise optional); the codebase read → the **companion worktree**; the 5 output files (`docs/intelligence/*.md`) → registered artifacts (`codebase_intelligence`/`dependency_graph`/`git_analytics`/`dead_code`/`architecture_decisions`) + **Knowledge-Index population**; the CLAUDE.md write-back → registry/ledger; Step-0/Human-Gate glue → a Tier-1 confirmation + the control-plane **tech_lead** gate. §8-clean.
- **00 Onboarding (full)** — keep verbatim: the discovery/assessment reasoning. Reroute to the **onboarding orchestration** (§5): discover across connected SoRs (reusing P1 `register_atlassian` + static-file extraction) **and** code-intel (00c), **register pointers** (B1, never re-create), **reconcile** proposed→accepted, **gap-fill** the genuinely-missing lifecycle artifacts via the normal phase agents (each individually gated), and emit a **`gap_report`** artifact. Gate **product_owner**. §8-clean.
- **00b Context Bridge → API-Contract artifact (M2)** — keep verbatim: the **Principal Integration Architect** persona + the contract-extraction discipline (OpenAPI/semver, "export ground truth from code"). Replace the copied `CONTEXT-BRIDGE.md` file with a **versioned `api_contract` artifact in the registry**: *Export* mode (run on the provider repo) **registers/updates** the `api_contract` artifact (semver in `external_ref`); *Import* mode is replaced by **read-through** — consumer repos read the current `api_contract` via `get_artifact` at run time (like the P3 designsource read-as-SoR) and a cross-repo `TraceEdge` (consumer `implements` contract) is recorded. The semver bump is what the drift detector keys on (§6). Gate **architect**. §8-clean.
- **00d Context Snapshot — RETIRED (D8, LOCKED).** Session continuity is now the platform DB + Temporal resumable runs; there is **no unique reconciliation logic to migrate**. No agent body is authored; the catalog marks `00d` **retired** (a test asserts there is no `/agents/00d_*/agent.md` and that the catalog flags it retired). The onboarding **gap report** covers any "where are we" reporting need.

---

## 5. Full onboarding orchestration + multi-repo + the API-Contract (the front door)

> ⚠️ **Built differently — noted 2026-09-17.** **There is no `OnboardingWorkflow`.** No Temporal
> workflow of that name exists anywhere in the tree. What shipped instead is **agent-driven
> onboarding on the ordinary agent-run path**: `00c_intelligent_context_extractor` reads the
> codebase and `00_onboarding` judges phase completeness and produces the `gap_report`, with a
> deterministic Python fallback when no companion is enrolled (`orchestration/trigger.py:267`
> raises `NoCompanionError` and the REST layer falls back). The **steps below still describe what
> onboarding does** — discover, register, reconcile, gap-fill, report and resume — so they remain
> useful as the intent; only the "durable saga sibling to `BuildWorkflow`" framing is wrong.

- **OnboardingWorkflow (Temporal):** a durable saga (sibling to `AgentRunWorkflow`/`BuildWorkflow`), idempotent by run/onboarding id, that runs for each repo in the project:
  1. **Discover** — connected SoRs (Atlassian pages/issues via P1 `register_atlassian`), static files (P1 extraction), and **code intelligence** (dispatch a code-intel task to the **companion**, 00c).
  2. **Register** — pointers only; **register-don't-recreate** (B1; idempotent by `external_ref` / content hash). Index registered + intel text into the **Knowledge Index** (§2).
  3. **Reconcile** — proposed → accepted into the SoR via the P1 reconciliation service (no duplicates).
  4. **Gap-fill** — detect missing lifecycle artifacts (e.g. no PRD / architecture / tests); generate each via its normal phase agent, **individually gated** (no auto-publish). 
  5. **Report + resume** — emit a **`gap_report`** artifact (what existed, what was registered, what was generated, what is still missing) and set the project's WorkItems/state so the team **resumes mid-pipeline** on the normal Phase Console (B3) — onboarding hands off to the *same* pipeline, it does not fork it.
- **Entry point:** an `onboard` trigger (UI/API) that starts the OnboardingWorkflow for a project's repos. Extends — does not replace — the P1 onboarding API.
- **Full multi-repo (D5):** a project carries **N repos** (`Repository.role`); the **Manifest Composer scopes context per repo** (repo-scoped artifacts + the shared `api_contract`); the registry/traceability/Knowledge-Index are project-scoped **shared memory** across repos. Cross-repo dependencies are `TraceEdge`s across `repo_id`s + `WorkItem.depends_on`.
- **API-Contract (D4):** the provider repo's 00b export registers a versioned `api_contract` artifact; consumer repos read it read-through; the consumer's implementing artifact records `implements -> api_contract`. This is the cross-repo contract **and** the drift trigger.

---

## 6. Live drift detection (webhooks → ledger → drift gate → change-impact) — D6

Extends the **P2 signed Git-webhook reconcile** (`integrations/webhooks.py`); it does **not** reopen it.

- **Detect (v1 scope, LOCKED):**
  1. **Contract drift** — an `api_contract` semver bump, or a `push` touching contract-governed paths/files, diverges consumers from the registered contract version.
  2. **Pointer/hash drift** — a registered SoR artifact's external content changed since we indexed it (detected by a read-through **content-hash mismatch** against the stored hash, e.g. a Confluence page or Jira issue edited outside the platform). 
  (Full semantic/AST diffing of contracts is deferred.)
- **Record + impact:** on detection, write a **`DriftRecord`** + an Event, and compute **change-impact via the traceability graph** — the downstream artifacts/repos reachable from the changed node (e.g. a contract change impacts every consumer artifact that `implements` it). The impacted set is stored on the `DriftRecord`.
- **Gate (control-plane, #2/#5):** open a **drift gate** — `DriftRecord.status=open`, decided by `decide_drift(role)` (the `Approval`-analog for run-less changes): **`architect`** for contract drift, **`tech_lead`** for pointer/hash drift. On **accept** → reconcile the pointer/version + re-index; on **reject** → flag for revert. Nothing is silently auto-applied to a system of record.

---

## 7. Phase 4 acceptance (thin slice to demo)

Same live-optional shape as Phases 2–3 (external SoRs skip without creds; deterministic invariants run offline; self-cleaning):

- **Onboard a split FE/BE project (two repos):** an `OnboardingWorkflow` per repo → P1 register-don't-recreate (Atlassian/GitHub, when creds) + **built-in code-intel** in a real **companion worktree** (the analyzer runs for real on a local clone; the platform stores only the intel artifacts + Knowledge-Index chunks) → reconcile → **gap-fill** a missing artifact (gated) → **`gap_report`**. Asserts: register-don't-recreate (no duplicates on re-onboard), the five intel artifacts + chunks land, and source is **never** copied into state.
- **API-Contract + cross-repo:** the backend repo's 00b export registers a versioned `api_contract`; the frontend repo reads it read-through and records `implements -> api_contract` (a cross-repo `TraceEdge`).
- **Resume mid-pipeline:** after onboarding, the platform triggers the next appropriate phase on the normal Phase Console and it runs to its gate (proving B3 — onboarding hands to the same pipeline).
- **Contract change → drift gates:** bump the `api_contract` (or push a contract-governed change) → a **`DriftRecord`** opens with **change-impact spanning both repos** (via traceability) → the **architect drift gate** decides; accept re-indexes, reject flags.
- **Knowledge Index:** code-intel text is retrievable — the **no-cost baseline** returns relevant chunks into `get_context().retrieved_knowledge`; the embedding path is exercised when a provider key is set (skips otherwise).
- **Invariants preserved:** **RLS** (a second tenant sees no intel/chunks/contracts/drift records); **register-don't-recreate** idempotency; **§8 sweep clean** on 00/00b/00c and **00d retired**; **companion topology** (the platform holds the index, not the code — #1/#3); **gate-then-publish** (gap-fill artifacts publish only on approval); **tenant binding + RLS remain server-side**. Tests + the full cross-phase suite green; `/BUILD_PLAN.md` ticked; `/docs` updated if a contract changed.

---

## 8. Decisions (LOCKED — team-approved)
- **D1 — CodeIntel engine:** a **built-in SOTA analyzer** is the default `codeintel.*` connector (git/Tornhill hotspots + tree-sitter/networkx dependency graph + complexity/dead-code/ownership + Claude-generated docs + embedding-backed semantic search), exposing the fixed **8-tool** surface; **Repowise is an optional connector** behind the same seam (no agent change). Dependency-graph depth is bounded by tree-sitter language coverage and degrades gracefully.
- **D2 — Analysis topology:** code intelligence runs in the **P2 companion worktree** on the client's machine; the platform stores only the **index + artifacts + chunks**, never the source (#1/#3).
- **D3 — Knowledge Index:** an **always-on no-cost structural+keyword (BM25) retrieval baseline** over chunk-level `KnowledgeChunk` rows, plus an optional **`EmbeddingProvider` seam** (`voyage-code-3` @1024 / `gemini-embedding-001` @1536); **`EMBEDDING_DIM` is provider-driven** (default 1536/Gemini; 1024/Voyage via re-migrate). Retrieval works with zero keys.
- **D4 — API-Contract = a versioned `api_contract` artifact** in the registry (00b export), read **read-through** by consumers; **no copied file**; semver drives drift.
- **D5 — Cross-repo edges = `TraceEdge`** between artifacts across `repo_id`s (consumer `implements` contract) + `WorkItem.depends_on`; full multi-repo via `Project.repo_topology` + **per-repo manifest scoping**; project-scoped shared memory.
- **D6 — Drift v1 = contract + pointer/hash drift** → a **`DriftRecord`** + a control-plane **`decide_drift`** gate (**architect** contract / **tech_lead** pointer-hash) + **change-impact via the traceability graph**; semantic diffing deferred. Built on the P2 webhook reconcile.
- **D7 — Onboarding (00 full) = discover → register → reconcile → gap-fill → `gap_report` → resume mid-pipeline**, extending the P1 onboarding services; onboarding hands off to the *same* pipeline (B3).
- **D8 — 00d Snapshot RETIRED** (continuity = platform DB + Temporal resumable runs); no agent body; the catalog marks it retired.
- **D9 — Gate roles:** 00c → `tech_lead`; 00 → `product_owner`; 00b → `architect`; drift → `architect` (contract) / `tech_lead` (pointer-hash).
- **D10 — Builds on, never reopens, P0–P3** (companion runner, signed webhooks, capability seam, reconciliation, traceability, gates, Manifest Composer).
