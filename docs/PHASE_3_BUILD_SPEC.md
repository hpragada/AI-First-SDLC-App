# Phase 3 Build Spec — Design & Test Loops (Figma read-as-SoR → Xray → traced defects)

> **Purpose:** fix Phase 3's contracts (the **DesignSource** and **TestMgmt** capabilities,
> the migrated design/test/security agents 05/09/09b/10, the a11y/design/test/security
> **control-plane gates**, the design↔code round-trip, the defect-loopback + test-impact +
> flaky-quarantine + per-PR preview flows, and acceptance) so Claude Code *implements*
> rather than *re-decides*. Same rule as Phases 0–2: contracts here don't change without
> updating this file; exact code is Claude Code's job.
>
> **Builds on Phases 0–2 — not re-opened.** The spine (RLS state, Platform-State MCP,
> Manifest Composer, Temporal `AgentRunWorkflow` + Gate/Approval), the Integration plane
> (`get_capability`, per-tenant `IntegrationConnection`, publish-to-SoR, reconciliation,
> traceability, Rate governor), and the **whole Phase-2 build vertical** (local-companion
> runner + managed worktree, CodeHost, `BuildWorkflow` saga, the 07↔08 remediation loop,
> injection guardrails, webhook reconciliation, migrated 07/08/11/12) are **done and
> frozen**. Phase 3 adds the *Design plane* and the *Test/Quality plane* and migrates the
> four remaining SOTA agents. **No SoR write before its gate is APPROVED — ever** (#5/#8).

## 0. In / out of scope
**In:** the **DesignSource** capability (`designsource.*`) + Figma connector (headless, per-tenant, **read-as-SoR**; write = internal artifacts, canvas round-trip a deferred seam); the **Design-System / tokens artifact** + **Code Connect** mapping; **responsive** wireframes + **per-tenant theming**; the **a11y (WCAG) gate** + design-review gate (control-plane Approvals); the **TestMgmt** capability (`testmgmt.*`) + Xray connector (headless REST/GraphQL, per-tenant, rate-governed) — test authoring, **result import**, NFR tests; **test-impact selection** v1 (traceability-graph based), **flaky quarantine** v1, **defect loopback** (failing test → traced defect WorkItem reusing the P2 remediation machinery); **ephemeral preview env per PR** as a **companion-local seam**; **migrate agents 05 UX, 09 Testing, 09b Test Automation, 10 Security**; the design→code→test→security thin slice.
**Out (later phases):** Figma **write beta** canvas round-trip (`generate_figma_design` against the live write API — kept behind the seam); **cloud** per-PR preview environments + sandbox hardening (P5 cloud-runner workstream); CodeIntel / full multi-repo / brownfield-full (P4); RBAC/SoD depth, secrets-vault depth, eval/quality harness (P5); Codex/Copilot drivers (P6). Phase 2's `BuildWorkflow` saga is **not reopened** — security (10) runs standalone (D8); the defect loop reuses, not rewrites, the remediation/webhook plumbing.

---

## 1. DesignSource capability (the integration seam for design — non-negotiable #9)

Business logic calls **capabilities, never vendors**: `designsource.*`, never `figma.*`. Same shape as the Phase 1/2 connectors, resolved per tenant via `get_capability`, **routed through the Rate governor** (`governed_transport`), wired in `registry._BUILDERS` via `register_connector`.

```python
# backend/integrations/capabilities.py  (extend)
class DesignSource(Protocol):                       # Figma-shaped, vendor-free
    def get_design_context(self, *, file_key: str,
                           node_id: str | None = None) -> DesignContext: ...   # read-through (live, current design)
    def get_variable_defs(self, *, file_key: str) -> list[DesignToken]: ...    # tokens: color/type/spacing/radius/elevation
    def list_components(self, *, file_key: str) -> list[ComponentRef]: ...      # Code Connect mapping source
    def generate_figma_design(self, *, file_key: str,
                              spec: DesignSpec) -> DesignRef: ...                # write beta — DEFERRED SEAM (D2)
```

```python
@dataclass(frozen=True)
class DesignToken:
    name: str           # e.g. "primary-action"
    kind: str           # "color" | "type" | "spacing" | "radius" | "elevation"
    value: str          # resolved value (hex / px / token expr)
    ref: str | None = None   # source variable id (for round-trip / Code Connect)

@dataclass(frozen=True)
class ComponentRef:
    key: str            # Figma component key
    name: str
    node_id: str
    url: str

@dataclass(frozen=True)
class DesignContext:    # read-through summary, NOT a copied body (#3)
    file_key: str
    name: str
    frames: list[dict]  # {node_id, name, type} — structural pointers only
    url: str

@dataclass(frozen=True)
class DesignRef:        # pointer persisted into Artifact.external_ref (figma SoR)
    sor: str = "figma"
    file_key: str = ""
    node_id: str | None = None
    url: str = ""
    version: int | None = None
```

- **Connector selection per tenant:** `get_capability(tenant_id, "designsource") -> DesignSource` over `IntegrationConnection(capability="designsource", connector="figma", scopes={"file_key": "..."}, token_ref, health)`.
- **Default connector (D1 — LOCKED):** `FigmaDesignSource` over the **Figma REST API**, headless per-tenant via `token_ref` (the Phase-5 vault seam). The Figma remote MCP stays the optional agent-side transport. **Read-as-SoR is the primary mode** (G2/G3): implementation reads the *current* design at run time; the platform never copies design bodies into state — only pointers/tokens.
- **Write depth (D2 — LOCKED):** v1 "design write" = the **05 agent's self-contained HTML wireframes** + the **Design-System/tokens** registered as **internal artifacts** (`sor=internal`). `generate_figma_design` (code-to-canvas round-trip, PG22) is implemented as a **seam** that raises `NotImplementedError` / is skipped without write creds — parity with the P2 "live-optional" pattern. The beta Figma write + Full-seat path drops in behind this seam without caller changes.

---

## 2. TestMgmt capability (the integration seam for test management — #9)

`testmgmt.*`, never `xray.*`. Xray tests are themselves Jira issues, but the capability is kept **separate** from `tasktracker` so the test-management vendor is swappable independently.

```python
# backend/integrations/capabilities.py  (extend)
class TestMgmt(Protocol):                           # Xray-shaped, vendor-free
    def create_test(self, *, project: str, summary: str, steps: list[TestStep],
                    fields: dict | None = None) -> ExternalRef: ...    # TC-XXX -> Xray Test issue (idempotent by summary/label)
    def get_test(self, *, test_ref: str) -> TestCase: ...                            # read-through
    def import_results(self, *, execution: TestExecutionImport) -> ExternalRef: ...  # Xray "import execution"
    def link_defect(self, *, test_ref: str, defect_ref: str) -> None: ...            # test -> defect link
    def search(self, *, jql: str) -> list[IssueHit]: ...
```

```python
@dataclass(frozen=True)
class TestStep:
    action: str
    data: str = ""
    expected: str = ""

@dataclass(frozen=True)
class TestCase:         # read-through, not stored
    key: str            # "PROJ-123" (Xray Test issue key)
    summary: str
    steps: list[TestStep]
    status: str
    url: str

@dataclass(frozen=True)
class TestResult:
    test_ref: str
    status: str         # "PASS" | "FAIL" | "SKIP"
    evidence: str = ""  # short note / log pointer (not a copied body)

@dataclass(frozen=True)
class TestExecutionImport:
    project: str
    work_item_ref: str          # the WorkItem/issue the run covers
    results: list[TestResult]
    summary: str = ""
```

- **Default connector (D3 — LOCKED):** `XrayTestMgmt` over the **Xray Cloud REST/GraphQL API**, headless per-tenant via `token_ref`, **rate-governed** (parity with Phase 1/2 D1). `import_results` is **idempotent** (re-importing the same execution updates, never duplicates — register-don't-recreate).
- **Connector selection:** `get_capability(tenant_id, "testmgmt") -> TestMgmt` over `IntegrationConnection(capability="testmgmt", connector="xray", scopes={"project_key": "..."}, token_ref, health)`.

---

## 3. Data-model deltas (extend Phases 0–2 — additive, RLS-aware, no breaking changes)

Every new table carries `tenant_id` + the standard RLS policy (forced + `tenant_isolation`) from its first migration (#6), verified by a DB-level isolation test.

- **IntegrationConnection** — now also `(tenant, "designsource") → figma` and `(tenant, "testmgmt") → xray`. Seeded for the demo tenant.
- **Artifact** — new **types** (no schema change): `user_journey`, `wireframe` (`sor=internal`, `external_ref` may point at Figma when read-as-SoR), `design_system` (tokens), `accessibility` (WCAG report), `test_case` (`sor=xray`/`internal`), `test_report` (exists since P2), `security_finding`, `sbom`. Design-system tokens are stored as a `design_system` artifact (pointer + token list), never a copied Figma body (#3).
- **Defect = a child WorkItem** (`parent`=story, `type="defect"`, `external_ref={"defect":"DEF-1","severity":...,"test_ref":...}`) — the **defect-loopback** modeled as first-class DAG sub-work exactly like the P2 `RemediationItem` (which is a `task` carrying a `rem` key — see the correction in `PHASE_2_BUILD_SPEC.md` §; `defect` **is** a real `WorkItem.Type` member, so this line is right about defects). A `test_report → defect` and `defect → code` `TraceEdge` records lineage. **Reuses the P2 remediation machinery; no new loop engine.**
- **TestExecution** (new): `tenant, project, work_item, run_id, status(pending/running/passed/failed), results(json summary), external_ref(Xray execution), flaky(bool), created_at`. The platform-side record of a companion test run; the bodies/evidence stay in Xray/logs.
- **TestQuarantine** (new): `tenant, project, test_ref, reason, since, active` — flaky-quarantine v1 register (a quarantined test is excluded from the blocking test gate).
- **PreviewEnv** (new): `tenant, project, work_item, run_id, url, status(provisioning/ready/torn_down/failed), provider(companion_local), created_at` — the companion-local per-PR preview seam (§6).
- **ProjectProfile** — `theme` (JSON, optional): **per-tenant theming** tokens flowed into the rendered manifest (PG23). No per-tenant code fork; a `design_system` artifact + this field drive theming.
- **No change** to WorkItem/Repository/Approval/TraceEdge schemas — Phase 3 exercises the existing `state` machine (`accepted → in_progress → in_review → done`), `external_ref`, gates, and trace edges.

---

## 4. Migrated agents — 05 UX, 09 Testing, 09b Test Automation, 10 Security

Same **75 / 15 / 10** discipline + **§8 reference sweep** that gated 01–04, 06, 07/08/11/12. Reasoning **verbatim**; every data reference (incl. mid-Process-step) rerouted via `AGENT_MIGRATION_SPEC §3`; glue (frontmatter→AgentSpec, command→phase-trigger, Human Gate→Approval) replaced. Bodies stored at `/agents/<key>/agent.md`; AgentSpecs already cataloged (`backend/apps/registry/catalog.py`): **05→`designer`, 09→`qa_lead`, 09b→`qa_lead`, 10→`security_engineer`**. Per-agent run tests required; the sweep (`grep` for `.md`/`docs/`/`tasks.md`/`CLAUDE.md`/"reply APPROVED") must be clean.

- **05 UX Design** — keep verbatim: Senior UX/Design-Systems persona + Evidence Base, journey mapping (happy/error/edge), information architecture, screen inventory, the **wireframe states** discipline (default/loading/empty/error/success + Loading-State Classification), **Atomic Design** system + usage rules, **Cognitive Walkthrough**, **WCAG 2.2 AA** criteria *(corrected from 2.1 on 2026-09-17 — this was the one prescriptive line the 2026-09-16 sweep missed; the agent body itself already says 2.2)*. Reroute: inputs (`docs/prd/`, `docs/requirements/`, `docs/design/`, "the current screens") → `get_context()` / `get_artifact()` / `designsource.get_design_context()`+`get_variable_defs()` (read client-designed Figma as SoR — G3); outputs (`docs/ux/*.md`, `docs/visuals/ux/**/*.html`, `CLAUDE.md` write-back, assumption log) → `register_artifact` (`user_journey`/`wireframe`/`design_system`/`accessibility`) + `add_trace_edge` + `log_event`. The HTML wireframe bodies go to S3 (draft) as `wireframe` artifacts; the Human Gate is removed (control-plane Approval).
- **09 Testing** — keep verbatim: the test-design reasoning, TC-XXX structure, NFR/edge coverage, quality bar. Reroute: reads (PRD, acceptance criteria) → `get_artifact()` / the WorkItem; writes (test cases) → `testmgmt.create_test` (Xray) + `register_artifact("test_case")` + trace edges; failing-result handling → defect-loopback WorkItem (§5). *Corrected 2026-09-17: this line said 09 reads **code** and the **worktree**. It does neither — its catalog entry sets neither `reads_code` nor `rides_build` (`catalog.py:113`), so it is a planning phase working from artifacts. The phase that reads the worktree is **09b Test Automation**, below.*
- **09b Test Automation** — keep verbatim: **Playwright-MCP locator discovery + Page Object Model** logic, automation patterns, ≥ coverage discipline. Reroute: reads (test cases) → the `test_case` artifacts / `testmgmt.get_test`; the automated tests are authored **into the companion worktree** and executed there (D4); results → `testmgmt.import_results` + a `TestExecution` record + `test_report` artifact.
- **10 Security** — keep verbatim: the SOTA security persona + benchmark **quality bar**, OWASP coverage, dependency/SBOM analysis, severity tiers. Reroute: reads (code + dependencies) → the worktree + the registry; writes (findings, SBOM) → `register_artifact("security_finding"/"sbom")` + trace edges; **criticals open defect-loopback WorkItems** (§5). Runs **standalone** on the agent-run path (D8) — it does **not** reopen the P2 `BuildWorkflow`.

---

## 5. Gates + the defect-loopback loop (control-plane, reusing P2 machinery)

- **Gates are control-plane Approvals (#2/#5), never engine hooks** — identical mechanism to P0/P2 (`decide_gate` signals the workflow). Phase-3 gates:
  - **Design review + a11y (WCAG) gate → `designer`** (05). The **WCAG checklist** (PG21) is enforced as **gate conditions on the design Approval** — a control-plane checklist, not a prompt rule and not an engine hook. Design artifacts publish (internal, or Confluence via DocStore on APPROVED) only after the gate.
  - **Test gate → `qa_lead`** (09/09b). Test cases publish to Xray and the `test_report` is accepted only after the gate; a failing **blocking** test cannot be gated past until its defect is resolved or quarantined (D9).
  - **Security gate → `security_engineer`** (10). Findings/SBOM gated; criticals must be resolved or explicitly accepted.
- **Defect loopback (D5 — LOCKED):** a **FAIL** in `import_results` (or a critical security finding) opens a **child WorkItem** (`type="defect"`) + `TraceEdge(test_report→defect)`, briefs it back to implementation (07 in remediation mode) **in the existing companion worktree**, the developer/agent fixes + re-tests locally, results re-import, and the loop repeats until clean — **the same remediation-loop + webhook-reconcile plumbing built in P2**, not a new engine. Cycle-capped → escalate (parity with `max_remediation_cycles`).
- **Test-impact selection v1 (D9):** select which tests to run by **traceability graph** — a changed `code` artifact → its `TraceEdge`s → the linked `test_case`s. Graph-based and honest about its bound (no coverage-map instrumentation; that's a later refinement).
- **Flaky quarantine v1 (D9):** a test that **flips pass/fail across reruns within one execution** is flagged `flaky`, recorded in `TestQuarantine`, **excluded from the blocking test gate**, and logged — it never silently blocks a merge nor silently passes.

---

## 6. Ephemeral preview env per PR — companion-local seam (D7 — LOCKED)

The per-PR preview (PG11) is a **temporary running copy of the app** built from the PR branch, so a reviewer can exercise the real feature and the E2E tests have a live target. In local-companion mode the honest v1 is **companion-local**:

- The companion brings the app up from the **worktree** (project-declared command — e.g. `docker compose up` / `make dev`, from the Project Profile/Repository per D7-parity with P2's toolchain source), records a **`PreviewEnv`** (`status=ready`, local `url`), and posts the link back as a **CodeHost commit-status / PR comment**.
- E2E/Playwright runs (09b) target that URL; design review can eyeball rendered screens vs the `wireframe`/Figma.
- Teardown on PR merge/close (or saga compensation); `status=torn_down`; Event logged.
- It is a **seam**: a real **cloud per-PR environment** (public URL, autoscaled) is the **P5 cloud-runner workstream** and drops in behind `PreviewEnv.provider` without caller changes. No cloud infra in P3.

---

## 7. Design↔code round-trip + read-as-SoR (G2/G3/PG22)

- **Read-as-SoR (primary):** **07 Implementation reads the *current* Figma at run time** via `designsource.get_design_context()` + `get_variable_defs()` (read-through, live) — when a client designs in Figma, the platform consumes it rather than regenerating it (G3). Without Figma creds the run **falls back to the `wireframe`/`design_system` artifacts** (live-optional, parity with P2).
- **Code Connect mapping:** `list_components()` + the `design_system` tokens produce a **Code Connect mapping** artifact linking design components → code components (PG20) — registered, gated, traceable.
- **Code-to-canvas round-trip (deferred seam):** `generate_figma_design` (PG22) is the seam from §1/D2 — not built live in P3.

---

## 8. Phase 3 acceptance (thin slice to demo)

Same live-optional shape as Phase 2 (skips Figma/Xray calls without creds; deterministic invariants run offline; self-cleaning):

- **Design:** a greenfield project with approved PRD/requirements/architecture artifacts → **05** runs (agent-run path), reads them via `get_context()`/`get_artifact()` (and the current Figma via `designsource` when creds exist, else falls back), produces `user_journey` + `wireframe` (HTML) + `design_system` (tokens) + `accessibility` artifacts → **designer + WCAG gate** → published (internal; Confluence optional on APPROVED).
- **Implementation reads current design:** a build run (reusing the P2 companion worktree) reads the *current* design via `designsource` (or the wireframe artifact fallback) — proving read-as-SoR.
- **Test → Xray → traced defect:** **09** authors TC → `testmgmt.create_test` (Xray; skips without creds) + `test_case` artifacts → **09b** automates into the worktree → the companion **runs the tests** (D4) → `import_results` (Xray) + `TestExecution` + `test_report` → **a FAILing test opens a traced `defect` WorkItem** (`TraceEdge` test_report→defect) → defect-loopback remediation in the worktree → re-run passes → **`qa_lead` gate**.
- **Security (standalone):** **10** reads the worktree code + deps → `security_finding` + `sbom` artifacts → a critical opens a defect-loopback item → **`security_engineer` gate**.
- **Preview env:** the companion brings the app up from the worktree, a `PreviewEnv(ready, url)` is recorded + linked on the PR; torn down on close.
- **Invariants preserved:** **no artifact publishes before its gate is APPROVED** (gate-then-publish); **RLS holds** (a second tenant sees no design/test/security artifacts, connections, executions, defects, quarantine, or previews — DB-level); **idempotent** (re-`create_test` + re-`import_results` register-don't-recreate; replayed defect loop duplicates nothing); **test-impact selection** picks only traceability-linked tests; **flaky quarantine** excludes a flip-flopping test from the blocking gate; **§8 sweep clean** on 05/09/09b/10; **tenant binding + RLS remain server-side**. Tests + demo green; `/BUILD_PLAN.md` ticked; `/docs` updated if a contract changed.

---

## 9. Decisions (LOCKED)
- **D1 — DesignSource transport:** headless **Figma REST**, per-tenant, rate-governed; **read-as-SoR** primary (read the client's current Figma — G3). Figma MCP stays the optional agent-side transport.
- **D2 — Design write depth v1:** "write" = **internal artifacts** (self-contained HTML wireframes + `design_system` tokens); **`generate_figma_design` canvas round-trip is a deferred seam** (beta + Full seat → later, behind the seam).
- **D3 — TestMgmt transport:** headless **Xray REST/GraphQL**, per-tenant, rate-governed (parity with P1/P2 D1); `import_results` idempotent.
- **D4 — Test execution topology:** the **P2 companion worktree** executes tests (parity with P2 D8); results imported via `testmgmt.*` on report.
- **D5 — Defects = child WorkItems** (`type="defect"`), reusing the P2 remediation-loop + webhook-reconcile machinery; `TraceEdge` lineage. No new loop engine.
- **D6 — a11y / WCAG = a control-plane gate** (WCAG checklist as conditions on the design Approval), never an engine hook.
- **D7 — Preview env = companion-local seam** (worktree bring-up + PR status link, torn down on close); cloud per-PR env → P5 (behind `PreviewEnv.provider`).
- **D8 — Security (10) = standalone gated P3 phase** (`security_engineer`); criticals open defect-loopback items; **does not reopen the P2 `BuildWorkflow`**.
- **D9 — Test-impact selection v1 = traceability-graph based** (changed code → linked tests); **flaky quarantine v1 = rerun-flip detection** → excluded from the blocking gate.
- **D10 — Per-tenant theming = `design_system` tokens artifact + `ProjectProfile.theme` flowed into the manifest**; no per-tenant code fork.
- **D11 — Gate roles** (already in the catalog): 05 → `designer`; 09 / 09b → `qa_lead`; 10 → `security_engineer`.
