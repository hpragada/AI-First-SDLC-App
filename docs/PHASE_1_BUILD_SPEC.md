# Phase 1 Build Spec — First System of Record (Atlassian) + Brownfield-lite

> **Purpose:** fix Phase 1's contracts (capability interfaces, connector signatures, data-model
> deltas, publish/reconcile flow, acceptance) so Claude Code *implements* rather than *re-decides*.
> Same rule as Phase 0: contracts here don't change without updating this file. Implementation
> detail (exact code) is Claude Code's job.
>
> **Builds on Phase 0** — the spine (RLS state, Platform-State MCP, ClaudeDriver, Manifest
> Composer, Temporal `AgentRunWorkflow`, Gate/Approval) is done and **not re-opened**. Phase 1
> adds the *Integration plane* and the *publish-to-SoR* half of the artifact lifecycle.
>
> **Phase 1 goal (blueprint Part C):** real **bidirectional Confluence + Jira**. On gate
> approval, a PRD publishes to Confluence and a backlog reconciles into Jira (no duplicates);
> live issues are read-through; lineage (requirement→PRD→epic→story) is visible; **both
> greenfield and brownfield single-repo** projects can be driven from Phase 1.

## 0. In / out of scope
**In:** capability abstraction (`docstore.*` / `tasktracker.*`) + per-tenant connector selection; DocStore (Confluence) + TaskTracker (Jira) connectors via Atlassian Rovo MCP; the publish-to-SoR step of the artifact lifecycle (gate→publish→pointer+version); Reconciliation service (`proposed→accepted`, idempotent); Traceability graph API + viewer; Rate governor v1; **migrate agent 06 (Task Breakdown)**; brownfield-lite single-repo onboarding (Atlassian register-don't-recreate + static-file extraction).
**Out (later phases):** code execution / GitHub PRs (P2), Figma/Xray (P3), CodeIntel + multi-repo + live drift (P4), secrets vault / RBAC depth (P5), Codex/Copilot drivers (P6). No auto-publish — ever (LOCKED gate policy #8).

---

## 1. Capability abstraction layer (the integration seam — non-negotiable #9)

Business logic calls **capabilities, never vendors**: `docstore.*` / `tasktracker.*`, never `jira.*` / `confluence.*` directly. This is the integration analogue of Phase 0's `ExecutionDriver` engine seam.

```python
# backend/integrations/capabilities.py
class DocStore(Protocol):       # Confluence-shaped, vendor-free
    def create_page(self, *, space: str, title: str, body_html: str,
                    parent_ref: str | None = None) -> ExternalRef: ...
    def update_page(self, *, page_ref: str, title: str, body_html: str,
                    base_version: int) -> ExternalRef: ...      # optimistic-locked
    def get_page(self, *, page_ref: str) -> DocPage: ...        # read-through
    def search(self, *, query: str, space: str | None = None) -> list[DocHit]: ...

class TaskTracker(Protocol):    # Jira-shaped, vendor-free
    def create_issue(self, *, kind: str, summary: str, description: str,
                     parent_ref: str | None = None, fields: dict | None = None) -> ExternalRef: ...
    def get_issue(self, *, issue_ref: str) -> Issue: ...        # read-through (live)
    def transition_issue(self, *, issue_ref: str, to_state: str) -> Issue: ...
    def add_comment(self, *, issue_ref: str, body: str) -> None: ...
    def search(self, *, jql: str) -> list[IssueHit]: ...

@dataclass
class ExternalRef:  # what we persist into Artifact.external_ref / WorkItem.external_ref
    sor: str            # "confluence" | "jira"
    id: str             # page id / issue key  (e.g. "PROJ-123")
    url: str
    version: int | None = None
```

- **Connector selection per tenant.** `get_capability(tenant_id, capability) -> DocStore | TaskTracker` resolves the tenant's `IntegrationConnection(capability, connector, scopes, token_ref, health)` row (model exists since P0) and returns the configured connector. No connection ⇒ raises `CapabilityUnavailable` (callers fall back to `sor=internal`).
- **Default connectors (LOCKED decision #2):** `AtlassianDocStore` / `AtlassianTaskTracker`, both over the **Atlassian Rovo MCP (Cloud)**. The platform is an **MCP client** here (control-plane calls), separate from the agent's tool use. A connector is a thin adapter: capability call → Rovo MCP tool call → `ExternalRef`.
- **Auth:** per-tenant headless (API-token / OAuth-app). Phase 1 reads the credential via `IntegrationConnection.token_ref` indirection (env/secret lookup); the real **vault + token broker is Phase 5** — `token_ref` is the seam that makes that swap non-breaking.
- **All connector I/O goes through the Rate governor (§9).**

> **Decision to confirm (D1):** control-plane writes via the **Rovo MCP client** (blueprint-locked) vs. direct Atlassian REST. Default to Rovo MCP; keep the connector interface identical either way so the transport is swappable.

---

## 2. Data-model deltas (extend Phase 0 §1 — additive, RLS-aware, no breaking changes)

Every new table carries `tenant_id` + the standard RLS policy from its first migration (#6).

- **WorkItem** — add `external_ref jsonb null` (the Jira issue key/url once accepted) and use the existing `state` lifecycle with **`proposed` → `accepted`** as the reconciliation transition (proposed = agent-drafted backlog; accepted = reconciled into the SoR).
- **Artifact** — no schema change; Phase 1 *exercises* `external_ref`, `sor ∈ {confluence, jira}`, and `status=published`. New artifact **types** appear: `backlog` (the proposed epics/stories set), plus the agent-06 output.
- **IntegrationConnection** (exists) — now populated: one row per `(tenant, capability)` → connector + scopes + `token_ref` + `health`.
- **SourceDocument** (new — brownfield static-file ingest): `project_id, filename, mime, s3_key, status(uploaded/extracting/extracted/adopted/failed), extracted_artifact_ids uuid[], provenance jsonb`.
- **Reconciliation idempotency:** the dedup key is `WorkItem.external_ref.id` / `Artifact.external_ref.id`. A reconcile NEVER creates a SoR object that already has a ref or that `search` matches (register-don't-recreate). No separate table needed; the Event Ledger records each reconcile decision.

---

## 3. Artifact lifecycle — the publish-to-SoR step (gate-then-publish, #5/#8)

Phase 0 ends a run at `status=published, sor=internal` (snapshot to S3). Phase 1 makes **publish actually push to the live SoR on APPROVED** — and only then.

- **Publish-target resolution** (`backend/integrations/publish.py`): `(artifact.type, tenant connectors) -> target`. Defaults: `prd|requirements|architecture → docstore(Confluence)`; `backlog → tasktracker(Jira)` via reconciliation (§4); anything with no configured connector → stays `sor=internal` (the Internal-SoR fallback, B3). Mapping is tenant-overridable via `IntegrationConnection`/profile.
- **Extends `publish_artifacts` activity** (orchestration, P0-T8): on APPROVED, for each artifact → resolve target → call the capability connector → set `sor`, `external_ref`, `status=published` → snapshot to S3 → `log_event`. **Idempotent by `run_id`+artifact** (re-publish updates the existing page/issue via `base_version`, never duplicates). Reject path unchanged.
- **Read-through:** published artifacts are pointers; bodies are re-fetched live via `get_page`/`get_issue`, never copied into state (#1/#3).

---

## 4. Reconciliation service (`proposed → accepted`; idempotent — PG2/B1)

`backend/integrations/reconcile.py` — turns a draft backlog into SoR issues **without duplicating**.

- **Greenfield (create):** for each `proposed` WorkItem with no `external_ref`: `search` the tracker for a matching issue; if none, `tasktracker.create_issue(kind=epic|story|subtask, parent_ref=…)`; set `external_ref`, transition WorkItem `proposed→accepted`, `add_trace_edge` PRD→epic→story, `log_event`. Re-runs are no-ops (ref already set).
- **Brownfield (register-don't-recreate):** `search`/discover existing Confluence pages + Jira issues, **register pointers** as Artifacts / WorkItems with `external_ref` and `status=published`, `sor=jira|confluence` — create nothing. Establishes lineage over what already exists.
- Hierarchy/order: epics before their stories before subtasks; partial-failure safe (each item idempotent by its ref).

---

## 5. Traceability Graph + viewer (requirement→PRD→epic→story — PG1)

- **Edges** use the existing `TraceEdge(from, to, rel ∈ derives/implements/tests/deploys)`. Phase 1 guarantees the cross-SoR chain is written: `requirements →derives→ prd →derives→ epic →derives→ story`.
- **API:** `GET /api/projects/{id}/traceability/ → { nodes: [{id, kind: artifact|work_item, phase, type, sor, external_ref}], edges: [{from, to, rel}] }` (tenant-scoped like every P0-T11 route).
- **UI:** a Traceability viewer screen rendering the chain (tree/graph), each node deep-linking to its SoR (`external_ref.url`). Extends the P0-T12 Traceability tab from a flat edge list to the lineage view.

---

## 6. Brownfield-lite onboarding (single-repo — B4/decision #7)

Two ingest modes, both ending at a **review gate** before adoption (no silent adoption):

1. **Atlassian register-don't-recreate:** point at an existing project's Confluence space / Jira project → §4 brownfield reconcile → pointers registered, lineage built, nothing created.
2. **Static-file extraction:** upload Word/PDF/Excel → `SourceDocument` (body to S3) → a **Temporal extraction workflow** (`extract → structure → register as `sor=internal` artifacts with provenance to the original`) → review gate → on approval the artifacts become first-class (and may later be re-pointed to a live SoR with no agent change).
   - Extraction adapters by mime: `.docx`→python-docx, `.xlsx`→openpyxl, `.pdf`→a PDF text extractor. **(Decision to confirm D2: exact libraries + which formats ship in v1 — recommend docx+xlsx first, pdf best-effort.)**
- **API:** `POST /api/projects/{id}/source-documents/` (upload), `POST …/onboard-atlassian/` (mode 1). Each opens the standard control-plane gate (`required_role=product_owner`).

---

## 7. Rate governor v1 (per-tenant queue/backoff/cache — PG18)

`backend/integrations/rate_governor.py` wraps **every** connector call. It decorates the
`Transport` callable (the sole network path in `atlassian/rest.py`) and is injected at
connector-build time by `registry.get_capability`, so every per-tenant connector is governed
automatically. Buckets/caches are process-global, shared per `(tenant, capability)`:
- **Token bucket per `(tenant, capability)`** (configurable rate; defaults in settings); serialize bursts.
- **Backoff/retry** on 429/5xx with full-jitter exponential backoff + a max-attempts cap; on exhaustion the last response is surfaced so the connector raises `CapabilityError` as before. Non-retryable 4xx pass straight through.
- **Short-TTL read cache** keyed by `(tenant, capability, method, url, body)`, scoped to **safe HTTP methods (GET/HEAD)** — covers `get_*` and Confluence search; only successful responses are cached. (Jira `search` is a POST in v1 and is rate-limited/backed-off but not cached — safe-by-construction, avoiding any chance of caching a write.)
- It is the single choke point the capability layer (§1) routes through — connectors never call the network directly. Time/sleep/randomness are injectable for deterministic tests.

---

## 8. Agent 06 — Task Breakdown migration (worked template; per AGENT_MIGRATION_SPEC §2–3 + §8)

Same 75/15/10 discipline + §8 reference-sweep that gated agents 01–04.
- **~75% verbatim reasoning:** the decomposition logic (vertical-slice tasks, explicit acceptance criteria, reject horizontal-slice anti-patterns), the three-part teaching pattern, the Quality Gate — word-for-word.
- **~15% rerouted references (incl. mid-step):** inputs (PRD, architecture) → `get_context()` / `get_artifact()`; outputs ("write tasks to `tasks.md`") → **propose** WorkItems + a `backlog` draft artifact (`register_artifact(type="backlog", sor="internal")`) + `add_trace_edge(prd→backlog)` + `log_event`. The agent **proposes**; it does not write Jira (gate-then-publish). On approval the **reconciliation service (§4)** creates the Jira issues.
- **~10% glue:** frontmatter→AgentSpec (already seeded, key `06_task_breakdown`, gate role **`tech_lead`**); command→phase trigger; Human Gate→control-plane Approval.
- **§8 sweep must pass** (no `.md`/`docs/`/`tasks.md`/`CLAUDE.md`/"reply APPROVED"). Store at `/agents/06_task_breakdown/agent.md`; add the per-agent run test (reads inputs from the platform, produces proposed WorkItems + backlog artifact, opens the `tech_lead` gate).

---

## 9. Phase 1 acceptance (thin slice to demo)

- **Greenfield:** run PRD (P0 agent) → approve → **PRD page in Confluence** (`sor=confluence`, `external_ref` set). Run Task Breakdown → approve → **epics/stories in Jira** (`sor=jira`), no duplicates on re-run. `tasktracker.get_issue(KEY)` returns the live issue; a status transition round-trips into the ledger. The **Traceability viewer** shows requirement→PRD→epic→story with working SoR deep-links.
- **Brownfield:** onboard a project whose PRD is a **Word doc** + stories in an **Excel sheet** → extraction → review-gated adoption as internal artifacts with provenance. Separately, onboard a project **already in Jira** → registered without creating duplicates.
- **Invariants preserved:** RLS holds (second tenant sees nothing); **no artifact reaches a SoR before its gate is APPROVED**; idempotent reconcile (re-run creates nothing new). Tests + demo green; `/BUILD_PLAN.md` ticked; this file updated if a contract changed.
- **Lineage scope (v1):** the traceability graph (`TraceEdge`) is **artifact-centric** — the chain it renders is `requirements →derives→ PRD →derives→ backlog`, with each node carrying its SoR deep-link (PRD → Confluence). Epic/story granularity lives as the **reconciled WorkItems** (`state=accepted`, `external_ref` → Jira `/browse/KEY`), linked parent→child via `WorkItem.parent`; promoting individual epics/stories to first-class trace nodes is deferred (would need WorkItem-typed edges). The acceptance slice (`tests/test_acceptance_phase1.py`) is **live** (greenfield, skips without creds, self-cleaning) + **offline** (brownfield extraction/adopt + register-don't-recreate); the full Temporal gate-signal path remains proven in the P0 slice.

---

## 10. Open decisions to confirm (before coding the affected task)
- **D1 — Atlassian transport:** Rovo MCP client (default, blueprint-locked) vs direct REST for control-plane writes. Interface is identical either way.
- **D2 — Extraction libraries / formats in v1:** recommend `.docx`+`.xlsx` first, `.pdf` best-effort.
- **D3 — Sprint creation:** is sprint/board creation in TaskTracker v1, or epics/stories/subtasks only (sprints deferred)? Recommend epics/stories/subtasks first; sprints behind a follow-up.
- **D4 — Confluence body format:** store/publish as storage-format HTML (`body_html`) — confirm vs ADF; recommend storage HTML for v1.
