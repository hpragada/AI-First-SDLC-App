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

export interface WorkItem {
  id: string;
  // Human-readable per-project key ("WI-42") + its raw number. Shown to users instead of the UUID.
  key?: string;
  number?: number | null;
  project: string;
  feature_stream: string;
  type: string;
  state: string;
  created_at: string;
  title?: string;
  description?: string;
  parent?: string | null;
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
  outputs?: unknown;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
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
  { key: "05_ux_design",                     label: "UX Design",          tier: "build" },
  { key: "06_task_breakdown",                label: "Task Breakdown",     tier: "build" },
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

// Backend returns { project_id, project_name, role } — no top-level id field.
export interface Membership {
  project_id: string;
  project_name: string;
  role: string;
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
  grants: InvitationGrant[];
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

// Integrations grid + connect drawer (S-11/S-12, 4.7-T6).
export type Capability =
  | "docstore"
  | "tasktracker"
  | "designsource"
  | "codehost"
  | "testmgmt"
  | "codeintel";

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
  needs?: { clarification?: boolean; gate?: boolean; label?: string };
  // The item's current lifecycle phase (latest run's agent key, e.g. "03_prd");
  // empty when no phase has run yet. Bugs.xlsx rows 49/50.
  current_phase?: string;
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
    audits_run: number;
    status: "not_started" | "ready" | "done";
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
  // Multi-state artifacts (per-screen wireframes) carry one self-contained HTML document per
  // UI state; the preview renders them behind a state switcher. Empty for single-body ones.
  states?: ArtifactState[];
  // Provenance: "phase_report" means the PLATFORM filed this from the engine's closing
  // message — it is not a deliverable the agent chose to register. See PHASE_REPORT_ARTIFACT.
  source?: string;
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
}

export interface DashboardClarificationItem {
  id: string;
  work_item: string;
  question: string;
  waiting_s: number;
}

export interface DashboardRunItem {
  run_id: string;
  phase: string;
  work_item: string;
  status: string;
}

export interface DashboardRollup {
  needs_me: {
    gates: DashboardGateItem[];
    clarifications: DashboardClarificationItem[];
    my_runs: DashboardRunItem[];
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
  };
  created_at: string;
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
  can_review: boolean;
  locked_out: string;
  adjudication: string;
  note: string;
}

export interface A11yReviewQueue {
  queue: A11yReviewItem[];
  can_review: boolean;
  lock_minutes: number;
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

export interface A11yConformance {
  scope: string;
  body: string;
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
  export_refused_because: string;
  can_sign: boolean;
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
