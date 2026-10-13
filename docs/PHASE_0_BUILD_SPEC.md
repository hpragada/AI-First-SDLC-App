# Phase 0 Build Spec — Platform Spine (build-grade contracts)

> **Purpose:** fix the contracts (schemas, interfaces, tool signatures) so Claude Code *implements* rather than re-decides. Implementation details (exact code) are Claude Code's job; the contracts here are not to be changed without updating this file.
>
> **Phase 0 goal:** run the existing planning agents (01 ideation → 02 requirements → 03 PRD → 04 architecture) entirely off platform state, with Temporal-orchestrated runs, gates, provenance, and a composed AGENTS.md manifest — **no external system-of-record yet** (artifacts live in S3 as drafts; "publish" target is `internal`).

## 0. In / out of scope
**In:** state plane (Postgres+RLS), Platform-State MCP, Temporal run orchestration, Manifest Composer, Gate/Approval, ExecutionDriver + ClaudeDriver, local planning runner, minimal React UI, migrate agents 01–04.
**Out (later phases):** Atlassian/Figma/Xray/GitHub connectors, build runners/real code PRs, RBAC depth, multi-repo, drift detection, cloud.

---

## 1. Data model (Postgres) — entities & key fields

> Every table includes `id (uuid pk)`, `tenant_id (uuid, not null)`, `created_at`, `updated_at`, and an **RLS policy** `USING (tenant_id = current_setting('app.tenant_id')::uuid)`. The app sets `app.tenant_id` per request/run via a DB session variable.

- **Tenant**(name, config jsonb, model_routing jsonb)
- **User**(email, name, is_active) · **Membership**(user_id, project_id, role) — roles enum: `product_owner, architect, designer, tech_lead, engineer, reviewer, qa_lead, security_engineer, devops, admin`
- **Project**(tenant_id, name, track enum[`greenfield,brownfield`], repo_topology enum[`single,split,multi`], status)
- **ProjectProfile**(project_id 1:1, description, domain, tech_stack jsonb, coding_standards jsonb, nfrs jsonb, constraints jsonb, glossary jsonb, **important_context text**, version int)
- **Repository**(project_id, role, code_host_ref, stack_overrides jsonb) — 0..N per project
- **WorkItem**(project_id, repo_id null, feature_stream, type enum[`epic,story,task,defect,test_case`], **state** enum[`proposed,accepted,in_progress,in_review,blocked,done,cancelled`], parent_id null, depends_on uuid[], assignee_id null, takeover_flag bool)
- **AgentSpec**(key e.g. `03_prd`, semver, prompt_version, body_ref (path in /agents), recommended_engine, recommended_model, phase_label) — the migrated agent registry
- **Run**(work_item_id, agent_spec_id, engine, model, prompt_version, temporal_workflow_id, status enum[`pending,running,awaiting_gate,approved,rejected,failed,completed,stalled`], cost_usd, inputs jsonb, outputs jsonb, started_at, ended_at)
- **Artifact**(project_id, repo_id null, run_id, phase, type, **status** enum[`draft,staged,approved,published,superseded`], **sor** enum[`internal,confluence,jira,figma,xray,git`], external_ref jsonb null, s3_key, content_hash, version int, embedding vector null)
- **TraceEdge**(from_artifact_id, to_artifact_id, rel enum[`derives,implements,tests,deploys`])
- **Event**(actor, action, target_type, target_id, ts, payload jsonb) — append-only; no updates/deletes
- **Approval**(run_id, gate_type, work_item_id, required_role, approver_id null, decision enum[`pending,approved,rejected`], comment, decided_at null)
- **IntegrationConnection**(tenant_id, capability, connector, scopes jsonb, token_ref, health) — table exists in P0, used Phase 1+

> **Enum drift, corrected 2026-09-17.** The four enums above are the Phase 0 shapes; each has gained a member since, and this spec is read as a contract, so the additions are folded in above rather than left for a reader to discover. **WorkItem.type** gained `defect` (P3 defect-loopback) and `test_case`. **WorkItem.state** gained `cancelled` — work that will never be done, which must not be recorded as `done`. **Run.status** gained `stalled` — a companion that missed its timeout, parked non-terminally for takeover (Bugs S.No 89). **Artifact.status** gained `superseded` — a draft whose gate was rejected, kept as the record but no longer served to downstream phases. Sources: `apps/workitems/models.py:9-36`, `apps/runs/models.py:9-21`, `apps/registry/models.py:36-46`.

**RLS:** enable on every table; create a Postgres role the app uses (non-superuser, so RLS applies); set `app.tenant_id` at the start of every request and every Temporal activity.

---

## 2. Platform-State MCP server — tool contract

Server name: `platform-state`. Stdio for local. Each tool is tenant-scoped (tenant_id passed in context/headers). Signatures (params → returns):

- `get_context(project_id, work_item_id?, phase) → { profile, relevant_artifacts[], recent_events[], retrieved_knowledge[] }` — the inputs the Manifest Composer renders.
- `register_artifact(project_id, run_id, phase, type, sor, s3_key?, external_ref?, content_hash, repo_id?) → artifact`
- `update_artifact(artifact_id, {status?, sor?, external_ref?, content_hash?, version?}) → artifact`
- `add_trace_edge(from_artifact_id, to_artifact_id, rel) → edge`
- `log_event(actor, action, target_type, target_id, payload) → event`
- `list_work_items(project_id, state?) → work_item[]`
- `transition_work_item(work_item_id, to_state) → work_item`
- `get_artifact(artifact_id) → artifact` / `list_artifacts(project_id, phase?, status?) → artifact[]`
- `detect_drift(artifact_id) → { drift: bool, current_version, registered_version }` — **stub in P0** (always returns drift=false), real in Phase 4.

The MCP server is the **only** way agents read/write platform state. App code may use the ORM directly; agents may not.

---

## 3. ExecutionDriver interface (the engine seam)

```python
class ExecutionDriver(Protocol):
    async def run_planning_task(self, *, manifest: str, agent_spec: AgentSpec,
                                mcp_servers: dict, allowed_tools: list[str],
                                work_item: WorkItem) -> RunResult: ...
    async def run_build_task(self, *, manifest: str, agent_spec: AgentSpec,
                             repo_workspace: Path, mcp_servers: dict,
                             allowed_tools: list[str], work_item: WorkItem) -> RunResult: ...
# RunResult: { outputs: dict, artifacts: list[ArtifactDraft], cost_usd: float, raw_messages: list }
```

**ClaudeDriver** (P0, planning only): uses `claude_agent_sdk.query()` with `ClaudeAgentOptions(system_prompt=<agent body>, mcp_servers={"platform-state": ...}, allowed_tools=[...])`. The composed manifest is written to the runner workdir as `AGENTS.md` and referenced. `run_build_task` may raise `NotImplementedError` in P0 (built Phase 2). Codex/Copilot drivers are Phase 6 — do not build now, but keep the interface honest.

---

## 4. Manifest Composer

Input: `get_context()` result. Output: an `AGENTS.md` string with a fixed section order:
`# Project` (profile core) → `# Important Context` (verbatim `important_context`) → `# Current Work Item` → `# Relevant Artifacts` (pointers + how to fetch via MCP) → `# Recent Events` → `# Retrieved Knowledge` → `# Rules` (the RULE-BEHAVIOR/RULE-EXECUTION essentials).
Apply a **token budget** (cap each section; prefer retrieval over dumping the whole profile). The manifest is ephemeral — written per run, discarded after.

---

## 5. Temporal — run orchestration shape

One agent run = one workflow `AgentRunWorkflow`:
1. `activity: compose_manifest(work_item, phase)` → manifest
2. `activity: execute_agent(driver, manifest, agent_spec, work_item)` → RunResult (artifacts as **drafts** in S3 + registered via MCP)
3. `activity: open_gate(run_id, gate_type, required_role)` → Approval(pending); workflow **waits on a signal** `gate_decision`
4. on `approved` → `activity: publish_artifacts(run_id)` (P0: set status=published, sor=internal; snapshot to S3) + `transition_work_item(done)` + `log_event`
   on `rejected` → mark run rejected, work_item back to `in_progress`, log_event
Retries/idempotency: activities idempotent by `run_id`; Temporal handles retry/backoff; failures land in a queryable state, not a crash.

---

## 6. Gate / Approval flow
A run that reaches a gate creates an `Approval(pending, required_role)`, surfaces in the React gate-approval UI, and the Temporal workflow blocks on the `gate_decision` signal. Only a user whose Membership role == `required_role` may decide — **plus either kind of admin, who may decide any gate**: a project-admin (`Membership(role="admin")`) or a tenant-admin (`User.is_tenant_admin`). *The admin override was added by the P4.7-T4 team decision and is missing from this line; noted 2026-09-17. See `backend/apps/gates/services.py:132-142`.* Decision → signal → workflow resumes. (RBAC enforcement is minimal in P0 — role check only; full SoD in Phase 5.)

---

## 7. Worked agent migration (template) — `03_prd`

**Before (current `.claude` agent, file-coupled):**
- Declared inputs: reads `docs/02-requirements.md`, `CLAUDE.md`.
- Process: reasoning steps (Role, Evidence Base, three-part teaching pattern, quality gate) **plus** embedded reads/writes inside steps (e.g. "using the requirements doc…", "record assumptions to `docs/assumptions/`").
- Post-Phase Writes: writes `docs/03-prd.md`, updates `CLAUDE.md`, writes assumption log.
- Human Gate: "reply APPROVED".

**After (platform — the 75/15/10 buckets, applied):**
- **~75% REUSE VERBATIM (reasoning):** Role, Evidence Base, Process how-to, three-part teaching pattern, quality gate — preserved word-for-word.
- **~15% REWRITE (data references, wherever they sit — incl. inside Process steps):** declared inputs → `platform-state.get_context(project_id, work_item_id, phase="prd")` + `get_artifact`; every in-step reference rerouted per `AGENT_MIGRATION_SPEC.md` §3 (the requirements read → the requirements artifact; the assumption write → an `assumption` artifact); outputs → write PRD body to S3 (draft) → `register_artifact(type="prd", sor="internal", s3_key, content_hash)` → `add_trace_edge(requirements_artifact, prd_artifact, "derives")` → `log_event(...)`. **Do not assume the body is untouched — sweep it (§8).**
- **~10% REPLACE (glue):** frontmatter `tools`/`model` → AgentSpec; command file → phase trigger; Human Gate "reply APPROVED" → removed, handled by the Temporal workflow's Approval.
- Human Gate → control-plane Approval (handled by the Temporal workflow, not the agent text).

Store the rewritten body in `/agents/03_prd/` and register an `AgentSpec(key="03_prd", semver, prompt_version, body_ref)`. Use this exact pattern for 01, 02, 04 in P0; 05–12 in later phases.

---

## 8. Phase 0 acceptance (thin slice to demo)
Create a tenant + project + profile (via UI). Trigger `ideation → requirements → prd → architecture` as WorkItems. Each runs as a Temporal workflow, composes an AGENTS.md manifest, executes via ClaudeDriver, registers a **draft** artifact in S3, opens a gate, and on approval publishes (`sor=internal`) + transitions the WorkItem to `done` + writes events + trace edges. The React UI shows the run timeline, the artifact, the gate, and the traceability chain. RLS verified by confirming a second tenant cannot see the first's rows.
