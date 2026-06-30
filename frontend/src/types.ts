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

// The four planning phases migrated in P0 (the acceptance slice).
export const PLANNING_PHASES: { key: string; label: string }[] = [
  { key: "01_ideation", label: "Ideation" },
  { key: "02_requirements", label: "Requirements" },
  { key: "03_prd", label: "PRD" },
  { key: "04_architecture", label: "Architecture" },
];

// Phase 4.8 auth/session surface. Tenant comes from the authenticated session;
// memberships drive the project switcher and route guards.
export interface User {
  id: string;
  email: string;
  name: string;
  is_tenant_admin?: boolean;
}

export interface Membership {
  id: string;
  project: string;
  project_name: string;
  role: string;
}

export interface CurrentUser {
  user: User;
  tenant: Tenant;
  memberships: Membership[];
  isAdmin: boolean;
}

export interface LoginRequest {
  email: string;
  password: string;
}
