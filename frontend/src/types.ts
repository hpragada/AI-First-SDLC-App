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
  important_context: string;
  version: number;
}

export interface WorkItem {
  id: string;
  project: string;
  feature_stream: string;
  type: string;
  state: string;
  created_at: string;
}

export interface Run {
  id: string;
  work_item: string;
  agent_spec: string;
  engine: string;
  model: string;
  status: string;
  cost_usd: string | null;
  temporal_workflow_id: string;
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
  status: string;
  sor: string;
  s3_key: string;
  content_hash: string;
  version: number;
  created_at: string;
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
  work_item: string;
  required_role: string;
  approver: string | null;
  decision: string;
  comment: string;
  decided_at: string | null;
  created_at: string;
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
}

export interface Clarification {
  id: string;
  run: string;
  work_item: string;
  phase: string;
  status: string; // "pending" | "answered" | "cancelled"
  questions: ClarificationQuestion[];
  answers: Record<string, unknown>;
  context: string;
  answered_by: string | null;
  answered_at: string | null;
  created_at: string;
}

// Traceability viewer (GET /projects/{id}/traceability/) — lineage graph.
export interface TraceNode {
  id: string;
  kind: string; // "artifact"
  phase: string;
  type: string;
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

// Admin: users & invitations (S-07).
export interface InvitationGrant {
  project_id: string;
  project_name?: string;
  role: string;
}

export interface Invitation {
  id: string;
  email: string;
  status: string; // "pending" | "revoked" | "accepted" | "expired"
  expires_at: string;
  grants: InvitationGrant[];
}

export interface AdminUserMembership {
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
  vendor: string;
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

// Repositories (S-13, 4.7-T7).
export interface Repository {
  id: string;
  name: string;
  role: string;
  default_base: string;
  status: string;
  is_default: boolean;
}

// ── Phase 4.8 T4 — lifecycle (bucket B + existing runs/artifacts/clarifications/approvals) ──

// Work-item list card deltas + filters (gap B).
export interface WorkItemCard extends WorkItem {
  title?: string;
  artifact_count?: number;
  owner?: string;
  parent?: string | null;
  needs?: { clarification?: boolean; gate?: boolean; label?: string };
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

// Onboarding hub (S-24, 4.7-T8).
export interface OnboardingDoc {
  id: string;
  name: string;
  size_bytes: number;
  status: "uploading" | "extracting" | "extracted" | "adopted";
  progress?: number;
}

export interface OnboardingRegister {
  docstore_space?: string;
  tasktracker_project?: string;
  linked_issues?: number;
}

export interface OnboardingHub {
  upload: OnboardingDoc[];
  adopt: OnboardingDoc[];
  register: OnboardingRegister;
  index: { status: "not_started" | "running" | "done"; files_indexed?: number; total_files?: number };
  gap: { ready: boolean; resume_phase?: string };
}

// Gap report (S-26, 4.7-T8).
export interface GapPhaseAssessment {
  phase: string;
  assessment: "complete" | "partial" | "missing";
  evidence: string;
}

export interface GapReport {
  phases: GapPhaseAssessment[];
  resume_phase: string;
  blocking: string[];
}

// API contracts & drift (S-27, 4.7-T9).
export interface ApiContract {
  artifact_id: string;
  name: string;
  version: string;
  provider_repo: string;
  status: string;
}

export interface DriftImpact {
  node: string;
  repo_id: string;
}

export interface DriftRecord {
  id: string;
  kind: string;
  required_role: string;
  detail: string;
  impacted: DriftImpact[];
}

// Artifact preview read-through (S-29, 4.7-T10, DECISION-5).
export interface ArtifactVersion {
  version: string;
  status: string;
  by: string;
  when: string;
}

export interface ArtifactPreview {
  body: string | null;
  content_type: string;
  status: string;
  version: string;
  versions: ArtifactVersion[];
  sor_link?: string;
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
  sor_link?: string;
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
