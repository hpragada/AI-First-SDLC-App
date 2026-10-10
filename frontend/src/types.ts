// Mirrors the Phase-0 REST serializers (backend/api/serializers.py). Pointers and
// provenance only — artifact bodies live in S3/the SoR, never in these payloads.

export interface Tenant {
  id: string;
  name: string;
  config: Record<string, unknown>;
  model_routing: Record<string, unknown>;
  created_at: string;
}

export interface Project {
  id: string;
  name: string;
  track: string;
  repo_topology: string;
  status: string;
  created_at: string;
}

export interface ProjectProfile {
  id: string;
  project: string;
  description: string;
  domain: string;
  tech_stack: Record<string, unknown>;
  coding_standards: Record<string, unknown>;
  nfrs: Record<string, unknown>;
  constraints: Record<string, unknown>;
  glossary: Record<string, unknown>;
  // Phase-scoped manual-export overrides (bare phase name -> capability | "internal").
  export_policy?: Record<string, string | null>;
  // Accessibility policy (QA-08): {target, gate:{block_severities, min_confidence,
  // block_on_incomplete_run, design_checks}}. Absent = the documented default; the effective
  // policy is readable at GET /projects/{id}/a11y-policy/. No editor for it yet — the profile
  // PUT is partial, so a client that never sends this key leaves it untouched.
  a11y?: Record<string, unknown>;
  important_context: string;
  version: number;
}

// Bugs S.No 140. `state` used to be a bare `string`, which is how a cancelled item ended up
// rendering as "Draft": every place that switches on it had a fall-through default, and a bare
// string means the compiler cannot tell you that you missed a case. Narrowing it turns each of
// those silent wrong answers into a build error — which is the whole reason this type exists.
export type WorkItemState =
  | "proposed"
  | "accepted"
  | "in_progress"
  | "in_review"
  | "blocked"
  | "done"
  | "cancelled";

/** Finished or abandoned — "there is nothing left to do here". NOT a claim that the work
 *  happened: `done` and `cancelled` say opposite things and must never be collapsed into one
 *  label. Mirrors `WorkItem.TERMINAL_STATES` on the backend. */
export const TERMINAL_WORK_ITEM_STATES: readonly WorkItemState[] = ["done", "cancelled"];

export function isTerminalState(state: string | undefined): boolean {
  return TERMINAL_WORK_ITEM_STATES.includes(state as WorkItemState);
}

export interface WorkItem {
  id: string;
  // Human-readable per-project key ("WI-42") + its raw number. Shown to users instead of the UUID.
  key?: string;
  number?: number | null;
  project: string;
  feature_stream: string;
  type: string;
  state: WorkItemState;
  created_at: string;
  title?: string;
  description?: string;
  parent?: string | null;
  // The parent's human key ("WI-260"). `parent` is a UUID and must never be drawn — anything
  // naming the parent on screen reads this instead. Null when there is no parent, and absent
  // from an API too old to send it, which reads the same way: nothing to show.
  parent_key?: string | null;
  assignee?: string | null;
  takeover_flag?: boolean;
  // Multi-repo (Hybrid Option C): the repository this work item targets (null = default repo).
  repo?: string | null;
  external_ref?: {
    sor?: string;
    id?: string;
    key?: string;
    url?: string;
    // The Task Breakdown agent's draft repo suggestion — the reviewer confirms/overrides it.
    repo_assignment?: RepoAssignment;
    // `test_case` items: the pointer to the artifact that holds the case itself. The steps,
    // preconditions and test data live THERE, not on the work item — materialize_test_cases
    // copies the title and this pointer and nothing else.
    test_case_artifact_id?: string;
    tc_id?: string;
  } | null;
}

// The agent's proposed repo for a work item, shown for review at the Task Breakdown gate.
export interface RepoAssignment {
  suggested_repo_id: string | null;
  rationale: string;
  confidence: "high" | "low" | string;
  source: string;
}

export interface Run {
  id: string;
  work_item: string;
  agent_spec: string; // AgentSpec primary key (UUID) — do NOT re-trigger with this
  agent_key: string | null; // AgentSpec key ("04_architecture") — use this to (re)trigger
  agent_phase: string | null; // human phase label for display
  engine: string;
  model: string;
  status: string;
  cost_usd: string | null;
  temporal_workflow_id: string;
  // Both are served whole by RunSerializer and narrowed by the helpers below, never read
  // field-by-field at a call site.
  inputs?: unknown;
  outputs?: unknown;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
}

/** Was this run handed to a machine that never picked it up?
 *
 *  The one place `Run.inputs.dispatch` is narrowed, for the same reason `workerStalled` exists:
 *  one shape, one reader.
 *
 *  Read this rather than the run's status, which cannot answer the question. Dispatching sets a
 *  run to RUNNING while leaving `dispatch.status` at "pending", so by status alone a phase sent
 *  to a dead companion is indistinguishable from one being actively worked on — which is exactly
 *  how a stranded run came to render a live console, spinner and all, until the 2h takeover.
 *
 *  "Pending" on its own is not a fault: a healthy companion claims within ~5s. It only means
 *  something is wrong alongside a companion that has stopped answering.
 */
export function dispatchUnclaimed(inputs: unknown): boolean {
  return (inputs as { dispatch?: { status?: string } } | null | undefined)
    ?.dispatch?.status === "pending";
}

/** Written onto a run while nobody is serving the code version it is pinned to (S.No 246), and
 *  REMOVED again as soon as somebody is — so anything keyed on it appears and disappears with
 *  the condition itself rather than needing to be dismissed. */
export interface WorkerStalled {
  pinned_build: string;
  newest_served: string;
  version_sets: number;
  noticed_at: string;
}

/** The one place `Run.outputs` is narrowed for this, so no screen re-invents the shape. */
export function workerStalled(outputs: unknown): WorkerStalled | null {
  const held = (outputs as { worker_stalled?: WorkerStalled } | null | undefined)?.worker_stalled;
  return held && held.pinned_build ? held : null;
}

export interface Artifact {
  id: string;
  project: string;
  run: string | null;
  phase: string;
  type: string;
  title: string; // human-readable name (Bugs S.No 120); blank → humanize `type` for display
  status: string;
  sor: string;
  s3_key: string;
  content_hash: string;
  version: number;
  created_at: string;
  // Whether Preview can show anything at all — a body, or a link to the system of record.
  // Computed server-side beside `read_artifact_preview` so the rule cannot drift; do NOT
  // re-derive it from `s3_key`/`sor` here (a wireframe previews from `external_ref.states`
  // with no `s3_key` of its own). Optional so an older API response degrades to "offer it".
  previewable?: boolean;
  /** The gate for this document's run was already decided, yet it is still unpublished —
   *  so "Waiting for approval" would invite a decision that cannot be given (S.No 318).
   *  Optional: an older API simply yields today's wording. */
  gate_decided?: boolean;
  /** Whether this row can be handed over as a FILE. Stricter than `previewable`:
   *  a preview may be a link or a synthesised summary, which a file may not be. */
  downloadable?: boolean;
  // Pointer + provenance. `source: "phase_report"` marks the platform's own copy of the
  // engine's closing message — see `isPhaseReport`.
  external_ref?: {
    sor?: string;
    id?: string;
    url?: string;
    source?: string;
  } | null;
}

export interface TraceEdge {
  id: string;
  from_artifact: string;
  to_artifact: string;
  rel: string;
  created_at: string;
}

export interface Approval {
  id: string;
  run: string;
  gate_type: string;
  /** Agent key of the run that opened this gate, e.g. "06_task_breakdown" (phase-specific
   *  gate panels key on this so they render only for their own phase). */
  phase?: string | null;
  work_item: string;
  /** The work item's own title. A CARRIER work item (onboarding / document vision) is hidden from
   *  the work-item list on purpose, so the Gates screen cannot look its name up — it uses this. */
  work_item_title?: string | null;
  required_role: string;
  approver: string | null;
  approver_name?: string | null;
  decision: string;
  comment: string;
  decided_at: string | null;
  created_at: string;
  /** Set when a merge gate was re-opened because the merge hit a conflict (ENH-2 / S.No 141):
   *  the human-readable conflict reason, so the gate panel can explain the retry. */
  merge_conflict?: string | null;
  /** Set when this gate's pull request was already merged outside the platform — somebody
   *  merged it on GitHub (S.No 88). The reviewer was being asked to approve a merge that had
   *  already happened, with nothing on screen saying so. A note, never a decision: a person
   *  still approves, through the same endpoint. */
  external_merge?: {
    merged_by: string;
    merged_at: string;
    pr_ref: string;
    detected_by: string;
  } | null;
  /** True while nobody is serving the code version this gate's run is pinned to (S.No 246).
   *  The decision still lands — it is written and signalled either way — so this is about
   *  TIMING only, and the screen says when it will take effect rather than pretending the
   *  click did nothing. Optional so an API too old to send it reads as "fine". */
  run_paused?: boolean;
}

export interface TriggerResult {
  run_id: string;
  workflow_id: string;
}

// Interactive clarifications (req #2): an agent's question, answered in the web app while
// the run waits at zero cost. Mirrors backend/api/serializers.py ClarificationSerializer.
export interface ClarificationQuestion {
  id: string;
  text: string;
  kind?: "text" | "choice" | "confirm";
  options?: string[];
  required?: boolean;
  // Surface-all-tiers gate: 1 = must-answer, 2 = suggested, 3 = industry-standard inference.
  // Absent → treated as Tier 1 (legacy questions). Tier 2/3 carry the agent's proposed answer.
  tier?: 1 | 2 | 3;
  suggestion?: unknown;
}

// Answering a clarification resumes the agent's OPEN `ask_human` tool call — but only while
// that session still exists. Once the run has left these states the poller is gone and no
// answer can resume anything; the answer is still worth giving (it replays into a re-run's
// manifest), so the question stays answerable and only the promise changes.
export function isRunListening(runStatus: string | undefined) {
  return runStatus === "pending" || runStatus === "running";
}

export interface Clarification {
  id: string;
  run: string;
  // The parent run's status, so the screen can tell a live wait from an orphaned question.
  run_status?: string;
  work_item: string;
  // Resolved names for the history view, which is read back long after the fact — an id and a
  // raw uuid don't tell you what you decided or who decided it.
  work_item_title?: string | null;
  // The readable key, "WI-3". Absent on a hidden carrier work item, which has none.
  work_item_key?: string | null;
  phase: string;
  status: string; // "pending" | "answered" | "cancelled"
  questions: ClarificationQuestion[];
  answers: Record<string, unknown>;
  context: string;
  answered_by: string | null;
  answered_by_name?: string | null;
  answered_at: string | null;
  created_at: string;
}

// Opt-in pagination envelope. The API returns a bare array unless the caller passes `page`, so
// this shape appears only where we ask for it (the history views). See backend api/pagination.py.
export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// Traceability viewer (GET /projects/{id}/traceability/) — lineage graph.
export interface TraceNode {
  id: string;
  kind: string; // "artifact"
  phase: string;
  type: string;
  title?: string; // human-readable name (Bugs S.No 120); blank → humanize `type`
  status: string;
  sor: string;
  external_ref: Record<string, unknown> | null;
  url: string | null; // deep-link to the live SoR (Confluence page / Jira issue)
  // Which work item this document came out of, so the map can follow one item's chain (P3).
  // Null/blank for documents adopted during brownfield onboarding: they were never produced by
  // a run, so they belong to no work item — the Highlight filter offers them as a group of
  // their own rather than leaving them unreachable.
  work_item?: string | null;
  work_item_key?: string;
  work_item_title?: string;
}

export interface TraceGraphEdge {
  from: string;
  to: string;
  rel: string;
}

export interface TraceGraph {
  nodes: TraceNode[];
  edges: TraceGraphEdge[];
}

// All 16 active agent phases (matches ACTIVE_AGENT_CATALOG in backend/apps/registry/catalog.py).
// Plan tier: onboarding/context setup (00_*) + strategy phases (01–04).
// Build tier: implementation, quality, ops phases (05–12).
// Used by PhaseConsole (legacy) and any component that needs the full static list.
// For dynamic/tenant-specific ordering use GET /api/phases/ via usePhaseCatalog().
export const PLANNING_PHASES: { key: string; label: string; tier: "plan" | "build" }[] = [
  { key: "00_onboarding",                    label: "Onboarding",         tier: "plan" },
  { key: "00b_context_bridge",               label: "Context Bridge",     tier: "plan" },
  { key: "00c_intelligent_context_extractor",label: "Context Extraction", tier: "plan" },
  { key: "01_ideation",                      label: "Ideation",           tier: "plan" },
  { key: "02_requirements",                  label: "Requirements",       tier: "plan" },
  { key: "03_prd",                           label: "PRD",                tier: "plan" },
  { key: "04_architecture",                  label: "Architecture",       tier: "plan" },
  // Plan, not build. 06 is the phase that CREATES tasks — its body calls create_work_item for
  // every epic, story and task it emits — so it can never run ON a task, and 05's wireframes
  // are an input to 07 rather than part of it. The backend's PLAN_PHASE_KEYS is the one that
  // decides a rail; this field is documentation and is read by nothing.
  { key: "05_ux_design",                     label: "UX Design",          tier: "plan"  },
  { key: "06_task_breakdown",                label: "Task Breakdown",     tier: "plan"  },
  { key: "07_implementation",                label: "Implementation",     tier: "build" },
  { key: "08_code_review",                   label: "Code Review",        tier: "build" },
  { key: "09_testing",                       label: "Testing",            tier: "build" },
  { key: "09b_test_automation",              label: "Test Automation",    tier: "build" },
  { key: "10_security",                      label: "Security",           tier: "build" },
  { key: "11_cicd",                          label: "CI/CD",              tier: "build" },
  { key: "12_deployment",                    label: "Deployment",         tier: "build" },
];

// Phase 4.8 auth/session surface. Tenant comes from the authenticated session;
// memberships drive the project switcher and route guards.
export interface User {
  id: string;
  email: string;
  name: string;
  is_tenant_admin?: boolean;
}

export type ProjectTrack = "greenfield" | "brownfield";

// Backend returns { project_id, project_name, role, track } — no top-level id field.
// `track` is OPTIONAL on purpose (S.No 221): during a rolling deploy the frontend can be
// newer than the API, and a missing track must never hide a brownfield project's onboarding.
// Everything that reads it therefore hides only on an explicit "greenfield".
export interface Membership {
  project_id: string;
  project_name: string;
  role: string;
  track?: ProjectTrack;
}

// isAdmin is NOT a top-level field in the backend response — it lives in user.is_tenant_admin.
// AuthContext derives context.isAdmin from that field.
export interface CurrentUser {
  user: User;
  tenant: Tenant;
  memberships: Membership[];
}

export interface LoginRequest {
  email: string;
  password: string;
}

// ── Phase 4.8 T2 — identity & onboarding (binds 4.7 T1–T4, T11) ──────────────
export interface SignupRequest {
  name: string;
  email: string;
  password: string;
  org_name: string;
}

export interface AcceptInviteRequest {
  token: string;
  password: string;
  name?: string;
}

export interface ResetRequest {
  token: string;
  password: string;
}

// POST /auth/invitations/preview {token} — the accept-invite page's pre-submit lookup
// (public, pre-auth). Never carries the token/hash/id — just what the page displays.
export interface InvitationPreviewGrant {
  project_id: string;
  project_name: string;
  role: string;
  role_label: string;
}

export interface InvitationPreview {
  tenant_name: string;
  inviter_name: string | null;
  email: string;
  name: string;
  grants: InvitationPreviewGrant[];
}

// Admin: users & invitations (S-07).
export interface InvitationGrant {
  project_id: string;
  project_name?: string;
  role: string;
}

export interface Invitation {
  id: string;
  email: string;
  name?: string;
  status: string; // "pending" | "revoked" | "accepted" | "expired"
  expires_at: string;
  sent_at?: string;
  grants: InvitationGrant[];
}

/** What Send invite / Resend report back (2026-10-09): whether the email went, or that this copy
 *  of the app has no mail service and printed the link to the server terminal instead. */
export interface InvitationSent extends Invitation {
  email_sent: boolean;
  email_delivery: "email" | "console";
}

export interface AdminUserMembership {
  id: string;
  project_id: string;
  project_name: string;
  role: string;
}

export interface AdminUser {
  id: string;
  name: string;
  email: string;
  status: string; // "active" | "invited"
  is_tenant_admin: boolean;
  memberships: AdminUserMembership[];
}

// Roles matrix + gate-role coverage (S-08).
export interface RoleHolder {
  user_id: string;
  name: string;
}

export interface RoleCoverageRow {
  role: string;
  holders: RoleHolder[];
  covered: boolean;
  gate_blocked: boolean;
  note?: string;
}

export interface RoleCoverage {
  roles: RoleCoverageRow[];
}

// Companion enrollments (S-05 tick, S-06 connect-machine).
// Backend groups by machine label; each project entry uses project_id/project_name.
export interface RunnerProject {
  project_id: string;
  project_name: string;
}

export interface Runner {
  id: string;
  machine: string;
  last_seen: string | null;
  // Whole seconds since this machine last called in; null when it never has. Computed on the
  // SERVER (apps/runs/enrollment.py) so a skewed browser clock cannot move it — the
  // "checking…" band in useCompanionStatus is a judgement about elapsed time, and subtracting
  // Date.now() from last_seen would paint a healthy machine as dying on a device whose clock
  // is wrong. Optional: an API too old to send it simply produces no amber band.
  age_s?: number | null;
  online: boolean;
  projects: RunnerProject[];
}

export interface RunnerToken {
  id: string;
  token: string; // shown once
}

// ── Phase 4.8 T3 — project setup (binds 4.7 T6/T7 + existing profile) ───────
export interface CreateProjectRequest {
  name: string;
  track: "greenfield" | "brownfield";
  repo_topology: "single" | "multi";
}

// Integrations grid + connect drawer (S-11/S-12, 4.7-T6). The capabilities a person connects.
// Code intelligence is not one of them (N1): it needs no connection, so it is provisioned
// automatically like accessibility checking, and neither appears here.
export type Capability =
  | "docstore"
  | "tasktracker"
  | "designsource"
  | "codehost"
  | "testmgmt";

// A project's repository topology as the platform computes it from the repository count:
// 0–1 single, 2 split, 3+ multi (`apps/projects/repos.py`). Never recomputed on screen (S.No 212).
export type RepoTopology = "single" | "split" | "multi";

export interface Integration {
  id: string;
  capability: Capability;
  connector: string; // vendor slug (e.g. "confluence")
  vendor: string; // human label (e.g. "Confluence")
  status: "connected" | "not_connected" | "failed";
  configured: boolean;
  binding: Record<string, unknown>;
  fail_reason?: string;
}

export interface TestConnectionResult {
  ok: boolean;
  detail: string;
  fix_hint?: string;
}

// Connector catalog (Bugs #40) — drives the per-vendor connect form.
export interface ConnectorField {
  name: string;
  label: string;
  type: "text" | "password";
  placeholder: string;
  required: boolean;
  hint?: string;
}

export interface ConnectorVendor {
  slug: string;
  label: string;
  no_secret?: boolean;
  binding: ConnectorField[];
  secrets: ConnectorField[];
}

export interface CapabilityCatalogEntry {
  capability: Capability;
  label: string;
  vendors: ConnectorVendor[];
}

// Repositories (S-13, 4.7-T7).
export interface Repository {
  id: string;
  name: string;
  role: string;
  default_base: string;
  status: string;
  is_default: boolean;
  preview_url: string; // manual app URL 09b explores (P3-09bR); "" = none
}

// A story's child test_case work item + its automation status (P3-09b coverage screen).
export type AutomationStatus = "not_automated" | "generating" | "ready";
export interface TestCase {
  id: string;
  key: string;
  title: string;
  tc_id: string;
  // What the case says about itself, read off its own document when it was materialised (G2).
  // Empty means the case never said — the platform does not guess one.
  priority: string;
  type: string;
  state: string;
  automation_status: AutomationStatus;
}

// CI ingest tokens (P3-09bX-1) — a per-project credential the client's CI uses to POST
// automated-test results back. Metadata only; the secret is never stored/returned after issue.
export interface CIToken {
  id: string;
  label: string;
  status: string; // "active" | "revoked"
  last_used_at: string | null;
  created_at: string;
}

// The one issue response that also carries the raw secret — shown ONCE, never again.
export interface CITokenIssued extends CIToken {
  token: string;
}

// ── Phase 4.8 T4 — lifecycle (bucket B + existing runs/artifacts/clarifications/approvals) ──

// Work-item list card deltas + filters (gap B).
export interface WorkItemCard extends WorkItem {
  title?: string;
  artifact_count?: number;
  owner?: string;
  parent?: string | null;
  parent_key?: string | null;
  // `yours` answers "may the person looking act on this?" — the gate's required role (or admin)
  // for a gate, project membership for a question, decided by the same rules as the Approve and
  // Answer buttons. Without it the board called every pending gate "Waiting for you", including
  // gates the viewer is refused on. Absent from an API too old to send it, which reads as
  // "not known to be yours" and keeps the neutral wording.
  needs?: { clarification?: boolean; gate?: boolean; label?: string; yours?: boolean };
  // The item's current lifecycle phase (latest run's agent key, e.g. "03_prd");
  // empty when no phase has run yet. Bugs.xlsx rows 49/50.
  current_phase?: string;
  // That same run's status ("running", "awaiting_gate", "completed", "failed", …), so the board
  // can say what the phase is doing (Bugs S.No 117). Empty when nothing has run; absent from an
  // API too old to send it.
  run_status?: string;
}

export type LifecycleNodeState =
  | "not_started"
  | "running"
  | "needs_answer"
  | "awaiting_gate"
  | "done"
  | "failed";

export interface LifecycleNode {
  phase: string;
  label: string;
  state: LifecycleNodeState;
  run_id?: string;
  triggerable: boolean;
}

export interface LifecycleLoop {
  from: string;
  to: string;
  count: number;
}

export interface LifecycleChild {
  id: string;
  title: string;
  type: string;
  phase: string;
}

export interface Lifecycle {
  tier: "plan" | "build" | "remediation";
  nodes: LifecycleNode[];
  loops: LifecycleLoop[];
  children: LifecycleChild[];
  parent?: { id: string; title: string };
}

// Phase catalog (gap C) — backs the S-18 trigger picker + board phase-columns.
export interface PhaseCatalogEntry {
  key: string;
  label: string;
  agent_key: string;
  gate_role: string;
}

export interface PhaseCatalog {
  plan: PhaseCatalogEntry[];
  build: PhaseCatalogEntry[];
  remediation: PhaseCatalogEntry[];
}

// Generalized criteria-gate checklist (S-22, DECISION-6).
export interface GateCriterion {
  id: string;
  text: string;
  required: boolean;
  satisfied: boolean;
  note?: string;
}

export interface GateCriteria {
  criteria: GateCriterion[];
  met: number;
  total: number;
  approve_enabled: boolean;
}

// S-19 live run console — no new endpoint, polls GET /runs/{id}/ + GET /events/
// (target_type=run, target_id=<run>); see SCREEN_BUILD_MAP.md "Notes for builders".
export interface RunEvent {
  id: string;
  target_type: string;
  target_id: string;
  kind: string; // "log" | "ok" | "warn" | "err" | "info"
  message: string;
  ts: string;
}

// ── Phase 4.8 T5 — brownfield onboarding + observability (4.7 T8/T9/T10 + bucket B) ──

// Source documents (S-25, spec §6). Mirrors `SourceDocumentSerializer` exactly.
export interface SourcePageImage {
  name: string;
  page: number | null;
}
export interface SourceDocument {
  id: string;
  project: string;
  filename: string;
  mime: string;
  status: "uploaded" | "extracting" | "extracted" | "adopted" | "failed";
  extracted_artifact_ids: string[];
  provenance: Record<string, unknown>;
  created_at: string;
  // A3/A4: view the original + captured pages, and the honest extraction fidelity.
  has_original: boolean;
  page_images: SourcePageImage[];
  fidelity: "" | "text" | "images_only" | "empty";
  // Part B fix 4: standing state of this document's vision pass (null when none ran). Survives a
  // page reload, so a run that failed after dispatch is still visible.
  vision: SourceDocVision | null;
}

// Part B fix 4: `done` and `failed` are terminal states only a dispatched run can reach; the
// adopt-time states live in AdoptVisionStatus below.
export interface SourceDocVision {
  state: "running" | "done" | "failed";
  message: string;
  run_id: string | null;
}

// Part B fix 3: what the document-vision pass did when the document was adopted. Adoption always
// succeeds — vision only enriches the extracted text — but the user must still be told when it
// did NOT run, because the usual cause (no companion running) is theirs to fix. `message` is a
// finished, human sentence from the backend; render it as-is rather than mapping `state` to copy,
// so the two can never drift. `vision: null` = this call started nothing (already-adopted doc).
export interface AdoptVisionStatus {
  state: "running" | "no_visuals" | "no_companion" | "already_running" | "failed";
  message: string;
  run_id: string | null;
}
export interface AdoptResult {
  source_document_id: string;
  status: string;
  artifact_ids: string[];
  target_type?: string | null;
  idempotent?: boolean;
  vision: AdoptVisionStatus | null;
}

// Onboarding hub (S-24, 4.7-T8). Mirrors `integrations/onboarding.py::onboarding_hub()` exactly.
export interface OnboardingUploadDoc {
  id: string;
  filename: string;
  status: "uploaded" | "extracting" | "extracted" | "adopted" | "failed";
  // S3-14: where the document came from. "upload" for a file the user dropped in (and for any
  // row an older API returns, hence the optional), "confluence" for a linked page.
  origin?: "upload" | "confluence";
}

export interface OnboardingAdoptDoc {
  id: string;
  filename: string;
}

export interface OnboardingRegister {
  docstore_connected: boolean;
  tasktracker_connected: boolean;
  designsource_connected: boolean;
  // The tool actually behind each capability ("Jira", "Confluence"), or null while nothing is
  // connected. The step offers to connect a CAPABILITY — naming a vendor before the user has
  // chosen one is what made the buttons and the pop-up disagree — and names the real tool only
  // once there is one to name.
  docstore_vendor: string | null;
  tasktracker_vendor: string | null;
  designsource_vendor: string | null;
  pages_registered: number;
  issues_registered: number;
}

// One adopt/link vocabulary option, served from the backend (derived from the gap-report
// lifecycle) so the dropdown can never drift from what the assessor recognises.
export interface AdoptType {
  value: string;
  type_label: string;
  phase: string;
  phase_label: string;
  label: string; // "<Type> (<Phase>)"
}

// A headless onboarding step's live state. Index code and Gap report run as agents on a carrier
// work item hidden from every list, so this hub is the ONLY surface that can report their
// progress — `running` and `question` exist for exactly that. `question` non-null means the agent
// called ask_human and is blocked until the user answers on the Clarifications screen.
export interface OnboardingStepState {
  running: boolean;
  run_id?: string | null;
  question?: { id: string; count: number } | null;
  // Non-null when the run finished and is parked at its review gate (S5-8). The gap report is
  // gated by design, so "running" alone would show "working…" for as long as approval takes.
  approval_id?: string | null;
}

export interface OnboardingRepoIndex extends OnboardingStepState {
  repo_id: string;
  name: string;
  status: "not_started" | "running" | "indexed";
  artifact_id?: string | null;
}

export interface OnboardingHub {
  upload: OnboardingUploadDoc[];
  adopt: OnboardingAdoptDoc[];
  register: OnboardingRegister;
  index: {
    status: "not_started" | "indexed";
    artifact_id?: string | null;
    repos?: OnboardingRepoIndex[];
  };
  gap: {
    ready: boolean;
    resume_phase?: string;
    resume_label?: string;
    report_artifact_id?: string;
  } & OnboardingStepState;
  // Where the accessibility step stands (task 8a). Optional so an older cached payload — or a
  // backend that predates this — still renders the hub rather than blanking it.
  a11y?: {
    routes_registered: number;
    // FINISHED audits only. A `judging` audit used to count here, and the step then said "1
    // audit run — open the report from Artifacts" while it was still going: there is no report
    // until the judging ends, because the baseline is published only when a position has
    // settled.
    audits_run: number;
    // …so an audit still going is carried separately, and the line can say so over the top of
    // whatever the tick says. Same pairing as the Index code step.
    running?: boolean;
    status: "not_started" | "ready" | "running" | "done";
  };
  adopt_types: AdoptType[];
}

// Gap report (S-26, 4.7-T8).
// One artifact the report weighed as evidence for a phase. This is a LIST OF OBJECTS, not a
// string (S5-6): it was typed `evidence: string` and rendered straight into a table cell, so
// React threw "Objects are not valid as a React child" on every report that had any evidence —
// i.e. every real one. The only live-mode test stubbed a 404, so nothing caught it.
export interface GapEvidence {
  artifact_id: string;
  type: string;
  sor: string;
  status: string;
}

export interface GapPhaseAssessment {
  phase: string;
  // Human label served by the backend (S5-7) — the frontend used to map `phase` itself against a
  // list keyed `01_ideation` while the API emits the bare `ideation`, so every lookup missed and
  // the screen showed raw slugs. Optional so an older cached payload still renders.
  label?: string;
  assessment: "complete" | "partial" | "missing";
  evidence: GapEvidence[];
}

export interface GapReport {
  gap_report_id?: string;
  phases: GapPhaseAssessment[];
  resume_phase: string | null;
  resume_label?: string;
  intel_present?: boolean;
  blocking: string[];
}

// POST /gap-report/ answers in two shapes: 202 when the agent path dispatched a run on the user's
// companion, 200 with the whole report when the deterministic fallback ran inline (S5-9).
export type GapReportRunResult =
  | ({ mode: "deterministic" } & GapReport)
  | { mode: "agent"; run_id: string; workflow_id: string };

// API contracts & drift (S-27, 4.7-T9). Mirrors `integrations/api_contract.py::list_api_contracts`.
export interface ApiContract {
  artifact_id: string;
  name: string;
  version: number;
  semver?: string | null;
  provider_repo: string | null;
  status: string;
}

export interface DriftImpact {
  node: string;
  repo_id: string;
  node_title?: string; // human-readable artifact name (Bugs S.No 120, Part C-2); blank → short id
  repo_name?: string; // "owner/name"; blank → short id
}

// `detail` is DriftRecord.detail — a JSONField (hashes/semver/source), not a string.
export interface DriftRecord {
  id: string;
  kind: string;
  required_role: string;
  detail: Record<string, unknown>;
  impacted: DriftImpact[];
}

// Artifact preview read-through (S-29, 4.7-T10, DECISION-5). `versions` mirrors
// `integrations/preview.py::_versions()` exactly — sibling registry rows, newest first.
export interface ArtifactVersion {
  artifact_id: string;
  version: number;
  status: string;
  run_id: string | null;
  created_at: string;
}

export interface ArtifactPreview {
  body: string | null;
  content_type: string;
  status: string;
  version: number;
  title?: string; // human-readable name (Bugs S.No 120); blank → humanize `artifact_type`
  versions: ArtifactVersion[];
  sor_link?: string | null;
  // Export policy context (team flow decision 2026-07-07): the phase's single allowed
  // manual-export capability, or null when the phase publishes internally only.
  phase?: string;
  artifact_type?: string;
  export_target?: string | null;
  // The PENDING gate on the run that produced this document, so "Open its gate" goes to that
  // gate instead of the whole list (Screen Words group 2). Null when there is no open gate —
  // the screen then shows no link rather than one that goes nowhere.
  gate_approval_id?: string | null;
  // Multi-state artifacts (per-screen wireframes) carry one self-contained HTML document per
  // UI state; the preview renders them behind a state switcher. Empty for single-body ones.
  states?: ArtifactState[];
  // Provenance: "phase_report" means the PLATFORM filed this from the engine's closing
  // message — it is not a deliverable the agent chose to register. See PHASE_REPORT_ARTIFACT.
  source?: string;
  // True when this body was RENDERED from a machine-readable file (an SBOM, say). The screen
  // uses it to offer "View raw" — the raw file is kept, and without this control no person
  // could ever see it (Bugs S.No 187).
  rendered?: boolean;
  /** True when this body belongs to the artifact's RUN, not to the artifact — it has no
   *  content of its own and you are reading the phase report instead (S.No 317). The screen
   *  must say so: without it, one document's content shows under another's name. */
  body_from_run?: boolean;
  /** The gate for this document's run was decided while it is still unpublished (S.No 318). */
  gate_decided?: boolean;
  /** The headline figures behind a rendered body (an SBOM's counts and provenance), so the
   *  screen shows them as labelled numbers rather than a run-on line of prose. `taken` is an
   *  ISO timestamp the screen formats in the reader's own locale. */
  render_summary?: {
    components?: number;
    licences?: number;
    tool?: string;
    taken?: string;
    spec_version?: string;
  } | null;
  /** Whether this document can also be handed over as a file. Computed server-side beside
   *  `previewable`; stricter, because a preview may be a link or a synthesised summary. */
  downloadable?: boolean;
}

// `external_ref.source` on an artifact the platform filed from the engine's final message.
// Mirrors `orchestration.activities.PHASE_REPORT_SOURCE` — a contract, not a label.
export const PHASE_REPORT_ARTIFACT = "phase_report";

// True when the platform, not the agent, produced this row. Such a row is a record of what
// the engine last said (often an error or a list of questions) and must never be presented
// as a reviewable deliverable.
export function isPhaseReport(a: { external_ref?: { source?: string } | null } | { source?: string }) {
  const ref = a as { external_ref?: { source?: string } | null; source?: string };
  return (ref.external_ref?.source ?? ref.source) === PHASE_REPORT_ARTIFACT;
}

// Feature streams the PLATFORM keys its own containers on: the accessibility backlog, one per
// judging run, one per keyboard journey, the CI regression bucket. Mirrors `BACKLOG_STREAM` and
// its siblings in the backend, which all share this shape on purpose. They are lookup keys — no
// user chose one, nobody can read one, and `__a11y_backlog__` under a heading saying FEATURE
// STREAM is the platform showing a person its own plumbing. A real stream ("Payments core") is
// a name somebody typed and is shown as before.
export function isInternalStream(stream: string | null | undefined): boolean {
  return (stream ?? "").trim().startsWith("__");
}

export interface ArtifactState {
  name: string;
  body: string;
  content_type: string;
}

// Run transcript (S-33, new — DECISION-7).
export interface TranscriptTurn {
  role: "agent" | "tool" | "human";
  body: string;
  meta?: string;
}

export interface RunTranscript {
  run_id: string;
  phase: string;
  engine: string;
  cost: string | null;
  turns: TranscriptTurn[];
}

// Manual gate-respecting publish (S-34, new — DECISION-8).
export interface PublishResult {
  status: string;
  sor_link?: string | null;
  // tasktracker export (backlog reconciliation) summary:
  reconciled?: number;
  created?: number;
  // Items that failed to reconcile to the SoR (e.g. a rejected Jira create) — reported, not
  // hidden, so a partial push isn't shown as a clean success.
  failed?: { work_item_id: string; type: string; error: string }[];
  items?: { work_item_id: string; key: string; url: string }[];
  // testmgmt export:
  test_key?: string;
}

// Phase-scoped export policy (GET /projects/{id}/export-policy/).
export interface ExportPolicy {
  defaults: Record<string, string>;
  overrides: Record<string, string | null>;
  effective: Record<string, string>;
  connected: Record<string, boolean>;
}

// Dashboard rollup (S-31, bucket B).
export interface DashboardGateItem {
  approval_id: string;
  gate: string;
  work_item: string;
  role: string;
  // The work item's NUMBER and TITLE, so a queue row can name it the way the rest of the product
  // does instead of printing eight characters of an internal id (P2). Optional: a response from
  // an older API has neither, and the row falls back to its title-less shape.
  work_item_key?: string;
  work_item_title?: string;
}

export interface DashboardClarificationItem {
  id: string;
  work_item: string;
  question: string;
  waiting_s: number;
  work_item_key?: string;
  work_item_title?: string;
}

export interface DashboardRunItem {
  run_id: string;
  phase: string;
  work_item: string;
  status: string;
  work_item_key?: string;
  work_item_title?: string;
  // How long the run has been going, so the row says that rather than reprinting an id.
  started_s?: number;
}

export interface DashboardRollup {
  needs_me: {
    // Filtered to the person reading them (Bugs S.No 222), and trimmed — gates and questions to
    // 20, runs to 10.
    gates: DashboardGateItem[];
    clarifications: DashboardClarificationItem[];
    my_runs: DashboardRunItem[];
    // The true totals behind those lists, for the tiles and the bell. Optional so a response from
    // an older API still renders, from the list lengths.
    counts?: { gates: number; clarifications: number; my_runs: number };
  };
  health: {
    work_items: number;
    phases_in_progress: number;
    awaiting_gate: number;
    published_week: number;
  };
  recent_publishes: { title: string }[];
}

// ── Accessibility review console (QA-23, S-36) ────────────────────────────
// One finding a check could not settle, with everything a person needs to settle it.
export interface A11yReviewLock {
  held: boolean;
  by_me: boolean;
  held_by: string | null;
  held_by_name: string;
  expires_at: string | null;
}

// ── Pages & audit (S-38, task 8a) ────────────────────────────────────────────────────────
// The brownfield way in: the platform cannot reach a client's application and cannot discover
// its pages, so somebody says what they are and a machine that CAN reach it does the visiting.

export interface A11yRoute {
  id: string;
  path: string;
  label: string;
  source: string;
  enabled: boolean;
  notes: string;
  // A real page standing for a pattern route — `/events/:id` is visited as `/events/482`.
  example_path: string;
  // When an audit last actually opened it. Null means never — a fact about the page, not a
  // gap in the screen.
  last_visited: string | null;
  // What a rename would leave behind. A finding is identified by the page it was found on, so
  // changing a path starts that page's history over — these two are what let the screen say so
  // while the path is still being typed, and what decides whether removing a page deletes the
  // row or takes it out of scope.
  open_findings: number;
  visits: number;
}

// A key in a pasted list that we could not use, named rather than dropped. The one that
// matters is the in-scope flag: ignore it silently and we audit pages the client excluded.
export interface A11yIgnoredKey {
  key: string;
  entries: number;
}

// How today's page list differs from the one the last finished audit used. Empty when there is
// nothing to say, so the screen hides the whole warning behind one check.
export interface A11yScopeChange {
  audit_id?: string;
  audit_at?: string;
  added?: string[];
  removed?: string[];
  before?: number;
  now?: number;
}

export interface A11yRoutesResponse {
  routes: A11yRoute[];
  summary: string;
  scope_change: A11yScopeChange;
  // Whether THIS reader may change the page list or start an audit (QA Lead / Tech Lead /
  // Admin). Everyone on the project reads the same screen; only these three operate it.
  can_manage: boolean;
  // Where the platform believes this application answers, and how it knows. The SAME resolver
  // the keyboard-journeys panel reads, so the two panels on one screen cannot disagree about
  // it. `base_url_reason` says what to go and set when there is no address at all. Optional
  // because an older API response does not carry them.
  base_url?: string;
  base_url_source?: string;
  base_url_reason?: string;
  changed?: {
    added: string[];
    updated: string[];
    disabled: string[];
    ignored_keys: A11yIgnoredKey[];
    total: number;
  };
}

// What a paste WOULD do, before any of it is written. `missing` is the load-bearing half:
// pages already registered that this list does not mention, with what excluding them costs.
export interface A11yRegistrationPreview {
  adding: string[];
  updating: string[];
  missing: {
    path: string;
    label: string;
    enabled: boolean;
    open_findings: number;
  }[];
  ignored_keys: A11yIgnoredKey[];
  total_now: number;
}

export interface A11yAudit {
  id: string;
  status: string;
  base_url: string;
  routes: string[];
  summary: {
    asked?: number;
    opened?: number;
    unreachable?: string[];
    never_reported?: string[];
    reason?: string;
    // What the AI half did. `reason` here is the DISPATCH's own account — most importantly the
    // one it gives when it stopped at this run's limit, which is the only record that some
    // elements were never asked about at all.
    ai_pass?: {
      reason?: string;
      deferred?: number;
      // Distinct ELEMENTS the cap left unanswered, which is not the same as `deferred` above:
      // duplicates are not collapsed before the cap, so the tail of a stopped pass is often
      // markup already judged earlier in the same run.
      deferred_distinct?: number;
      // Why those were deferred, kept apart from `reason` so one cannot overwrite the other. A
      // pass can reach its limit AND then fail to send what it had kept: two facts about two
      // different sets of elements, and a single string could only hold the last one to happen.
      deferred_reason?: string;
      dispatched?: number;
      distinct?: number;
      // A judgment run was ALREADY live for this capture, so this pass deliberately did nothing
      // — it did not dispatch, and it wrote nothing off. Not a failure: the run that got there
      // first is judging those elements. A pass carrying this never replaces the record of the
      // pass that is running.
      already_running?: boolean;
      // How many elements nothing could be asked about at all — no judge registered, or no
      // machine connected. Tells that case apart from the cap case WITHOUT matching on the
      // wording of `reason`, which would break the moment somebody improved a sentence.
      filed_unjudged?: number;
      // A SECOND judging pass over the same capture ("check the rest"), not the audit's first.
      // Written by `rejudge_capture`, which re-uses the audit row rather than opening a second
      // audit — so without this a completed audit appears to vanish and be replaced by a
      // running one, with nothing on screen explaining why.
      rejudged?: boolean;
      // When that second pass started. The audit's own `created_at` is the first pass's, and on
      // a re-judge it is the wrong time to put next to work that is happening now.
      rejudged_at?: string;
      // How many elements that second pass went back for. Not `dispatched` — they differ
      // whenever an element is answered from cache — and this is the number the button
      // promised out loud before it was pressed.
      rejudged_asked?: number;
      // A re-judge went looking and found nothing of this capture unanswered. Settles the
      // count outright: the other fields are what each pass recorded about ITSELF at the time,
      // and this is the authoritative recount from the capture.
      nothing_left?: boolean;
    };
    // Whether the browser answered when the capture asked what each element is called. A whole
    // capture with no names is a broken toolchain, and it hides: every element still arrives,
    // three checks run perfectly, and the fourth silently never selects anything.
    names?: { named?: number; nameable?: number; reason?: string };
    // Closed by the platform because the machine capturing it went away, rather than by a run
    // that finished and found nothing openable. Same status, entirely different thing to do.
    abandoned?: boolean;
  };
  // This audit says it is running, and nothing has been heard from the machine holding it for
  // a long while. DERIVED on read and never written: a machine switched off for good never
  // comes back to be swept, and the screen must not be the last thing still claiming the audit
  // is running.
  stalled?: boolean;
  // When it last gave any sign of life — the newest screen, the newest verdict, or its last
  // heartbeat, whichever came last. Only sent when `stalled`; on a healthy audit the honest
  // answer is "it is talking to us now". A count with no time beside it reads identically after
  // one second and after twenty-five minutes, which is how a dead judging pass went on calling
  // itself "in progress".
  stalled_since?: string | null;
  // The judging run to finish when this audit can no longer recover on its own. A quiet judging
  // pass resumes by itself for as long as its report deadline has not fired; once it has, the
  // run is PARKED and the claim lease will never offer it back — so "start the machine again"
  // stops being true and the screen has to offer a way out instead. Null on every audit that can
  // still recover, which is what makes its presence the signal.
  parked_run_id?: string | null;
  // How far this audit has got RIGHT NOW. Present only while it is still going somewhere —
  // `summary` above is written when it closes, so until then there was no count of anything
  // anywhere and a screen could only show the status word. `judged`/`dispatched` appear once
  // the AI pass has been dispatched, and not before, so "none judged yet" stays distinguishable
  // from "not that stage".
  progress?: {
    visited: number;
    unreachable: number;
    judged?: number;
    dispatched?: number;
  } | null;
  // How many elements of this audit NOTHING ever looked at — never dispatched, or dispatched to
  // a judging run that died before reaching them. Not the same as an 'uncertain' a check
  // actually reached: that one belongs to a person. Only counted for a closed audit, because
  // while a pass is running the answer is still changing.
  unanswered?: number;
  // What a FINISHED audit came to, for the panel that stays on screen after the run ends.
  // `waiting` is counted apart from `problems` on purpose: a problem the platform is sure
  // about and a question it is asking a person are not the same thing. Present only on the
  // newest audit, because that is the only one the panel shows.
  outcome?: { problems: number; critical: number; high: number; waiting: number } | null;
  created_at: string;
  // When the audit last moved. Equal to `created_at` for an audit that ran once; later than it
  // once a second judging pass has run over the same capture.
  updated_at?: string;
}

export interface A11yPolicy {
  defaults: Record<string, unknown>;
  overrides: Record<string, unknown>;
  effective: Record<string, unknown>;
  summary: string;
  error: string;
}

// One row of the review queue: what the rail on the left draws, and nothing else.
//
// The capture is deliberately absent (G3b). Working it out costs the server two lookups per
// finding when the picture exists and four when it does not, and the rail draws no picture —
// so the list used to pay for evidence it threw away, once per row, on every load. It belongs
// to `A11yReviewFinding` below, which is the read the detail panel makes for the one item a
// reviewer actually opened.
export interface A11yReviewItem {
  id: string;
  criterion: string;
  criterion_handle: string;
  wcag_level: string;
  route: string;
  selector: string;
  stable_selector: boolean;
  checker: string;
  // What the AI SAID (pass/fail/uncertain) — not what the platform decided about it.
  // `uncertain` means "I looked and cannot tell", and the screen prints that as "No verdict"
  // rather than 0%, which would read as "the AI was 0% confident" (D-A11Y-95).
  verdict: string;
  confidence: number | null;
  severity_if_confirmed: string;
  // What the PLATFORM decided, and whether it is still open. Constant across the review queue —
  // everything in it is `needs_review` and open — and the first thing a reader needs on S-39,
  // which is reached from a report and is therefore mostly opened on confirmed failures.
  outcome: string;
  status: string;
  evidence: string;
  suggested_fix: string;
  // Where the finding came from (G3). All null on a baseline audit — an audit of an existing
  // application has no story, no test case and no run, so there is genuinely nothing to link
  // to and the screen shows nothing rather than an empty link.
  source_run: string | null;
  work_item_id: string | null;
  // The test case's own `TC-031` where it has one, else the work item key.
  work_item_label: string | null;
  work_item_title: string | null;
  lock: A11yReviewLock;
}

// The single-item read: the row, plus the capture the reviewer judges it by and the state of
// their own permission to answer. Only this call carries them, and only this call pays for them.
export interface A11yReviewFinding extends A11yReviewItem {
  page_image: boolean;
  element_image: boolean;
  box: { x: number; y: number; width: number; height: number } | null;
  url: string;
  // Why there is no picture. Blank when there is one. Never left unsaid.
  capture_reason: string;
  // Which capture this evidence came out of — the audit's own id on a brownfield pass, the
  // run's on a greenfield one. Resolved to `captured_by` on the read-only screen.
  capture_key: string;
  can_review: boolean;
  locked_out: string;
  adjudication: string;
  note: string;
}

// The read-only view of one finding (S-39): the same evidence the console shows, opened without
// taking a review claim, plus the audit whose pass took the picture.
//
// **`captured_by` is null on greenfield and must stay so.** There the capture key names a `Run`
// and no audit exists — the same rule `work_item_id` follows, and for the same reason: nothing
// to link to, so nothing shown rather than an empty link.
export interface A11yFindingDetail extends A11yReviewFinding {
  captured_by: {
    id: string;
    // "audit 4850688e" — short enough to say out loud, long enough to find.
    label: string;
    finished_at: string | null;
    status: string;
    asked: number;
    opened: number;
  } | null;
}

export interface A11yReviewQueue {
  queue: A11yReviewItem[];
  can_review: boolean;
  lock_minutes: number;
  // Which empty state to show when `queue` is empty. `false` means nothing on this project has
  // ever been checked — a completely different sentence from "every check was sure enough to
  // answer on its own", and the two used to be told to the reader as the same thing.
  ever_checked: boolean;
}

// ── G6 · keyboard journeys (S-38) ────────────────────────────────────────────────────────
//
// Eight WCAG criteria cannot be answered by reading a page standing still — whether tabbing ever
// traps you, whether focus stays visible, whether a status message is announced. They are only
// answerable by OPERATING the application, which is what a journey does.

// `status` is the last walk's status, with one value the platform derives rather than stores:
// `"queued"` means dispatched and not yet claimed by a machine. See `journey.QUEUED`.
export interface A11yJourneyRow {
  // What the screen sends back to start this one. Always present, unlike `test_ref`: a test case
  // is only usually stamped with a TC id, and two unstamped ones must not become one row.
  id: string;
  test_ref: string;
  title: string;
  artifact_id: string;
  steps: number;
  last_walked: string | null;
  // "walking" | "complete" | "failed", or "" when it has never been walked.
  status: string;
  // The pass's own honesty check: asked / walked / blocked / never reached.
  summary: {
    asked?: number;
    walked?: number;
    blocked?: { step: number; reason: string }[];
    not_reached?: number[];
    findings?: number;
    reason?: string;
  };
}

// A test case that CALLS itself a journey and cannot be walked. Shown, never hidden: omitting it
// is how an application with no keyboard coverage comes to look like one with no problems.
export interface A11yUnwalkable {
  artifact_id: string;
  title: string;
  test_ref?: string;
  reason: string;
}

export interface A11yJourneyList {
  journeys: A11yJourneyRow[];
  unwalkable: A11yUnwalkable[];
  over_cap: string[];
  max_journeys: number;
  // Pre-filled from the last audit, else the repository. Editable — the user starts the
  // application and confirms where it is answering.
  base_url: string;
  base_url_source: string;
  base_url_reason: string;
  // Whether THIS user may start one. The list is readable by anyone on the project.
  can_start: boolean;
}

export interface A11yJourneyStarted {
  name: string;
  test_ref: string;
  run_id: string;
  journey_run_id: string;
  steps: number;
}

export interface A11yJourneyQueued {
  started: A11yJourneyStarted[];
  // Named, never dropped: already walking, no companion, over the cap, or a name this project
  // does not have.
  refused: { name: string; test_ref: string; reason: string }[];
  over_cap: string[];
  unwalkable: A11yUnwalkable[];
  reason: string;
}

// ── QA-24 · conformance statement (S-37) ─────────────────────────────────────────────────

// The VPAT vocabulary, deliberately the standard's own words — a procurement team reads this
// against other vendors' documents.
export type A11yConformanceLevel =
  | "supports"
  | "partially_supports"
  | "does_not_support"
  | "not_applicable"
  | "not_evaluated";

export interface A11yConformanceRow {
  criterion: string;
  handle: string;
  level: string;
  // What actually happened, with no verdict in it: "checked on 12 pages with nothing wrong",
  // "nothing checked this". This is the column the evidence lives in.
  evidence: string;
  // Which engines produced that evidence — rule / AI / agentic / human. AC1's provenance.
  established_by: string[];
  routes_checked: number;
  open_failures: number;
  human_decisions: number;
  // What the evidence supports. `null` means the platform declines to put a word in the
  // reviewer's mouth, which is what happens whenever a check looked and could not decide.
  suggested: A11yConformanceLevel | null;
  // The reviewer's own word, when they gave one. Always wins.
  verdict: A11yConformanceLevel | null;
  // What the statement will actually say: their word, else the evidence's, else not evaluated.
  effective: A11yConformanceLevel;
  needs_a_person: boolean;
  // Why no level is suggested, when `needs_a_person` — one line a reviewer can act on. Empty
  // otherwise (recon 2026-10-10, finding 7).
  why: string;
}

export interface A11yConformanceTotals {
  supports: number;
  partially_supports: number;
  does_not_support: number;
  not_applicable: number;
  not_evaluated: number;
  total: number;
  evaluated: number;
  awaiting_a_person: number;
  // How many levels the platform suggested and the reviewer did not change. Counted out loud
  // at signing rather than hidden — it is the thing they are taking responsibility for.
  platform_suggested: number;
}

// Which accessibility checks the statement was compiled from, and when the most recent of them
// ran. Also written INTO the wording by `draft_body`, so the person signing signs it too — this
// copy is for the screen, which still has to be able to say it after a reviewer has replaced the
// wording with their own.
export interface A11yConformanceBasis {
  latest: {
    id: string;
    label: string;
    // When the audit started — the screen adds the time of day in the reader's own clock.
    started_at: string | null;
    finished_at: string | null;
    asked: number;
    opened: number;
  } | null;
  // Every completed audit, not just the named one: the findings ledger is cumulative, so a
  // statement compiled today rests on every pass recorded up to today.
  audits: number;
  runs: number;
}

export interface A11yConformance {
  scope: string;
  body: string;
  basis: A11yConformanceBasis;
  drafted: boolean;
  rows: A11yConformanceRow[];
  totals: A11yConformanceTotals;
  disclaimer: string;
  signed: boolean;
  signed_name: string;
  signed_role: string;
  signed_at: string | null;
  // Signed, but the evidence has moved since (team decision C1). The wording is still what they
  // signed; it no longer describes what the platform holds, and export is refused until re-signed.
  stale: boolean;
  artifact_id: string | null;
  required_role: string;
  can_export: boolean;
  // When the signed statement was last exported (marked Published); null until then.
  exported_at?: string | null;
  export_refused_because: string;
  can_sign: boolean;
  // An audit is still running, so the numbers are still coming in; signing waits for it.
  audit_in_progress: boolean;
  // Nothing has looked at anything yet: the signing panel says "Run an audit first".
  has_evidence: boolean;
}

export interface A11yReviewDecision {
  id: string;
  adjudication: string;
  outcome: string;
  status: string;
  severity: string;
  // True only when this project's policy will actually raise a ticket, so the screen never
  // promises a defect that will not exist.
  opens_defect: boolean;
}
