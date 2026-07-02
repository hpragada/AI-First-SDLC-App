// Typed client for the Phase-0 REST API. Every tenant-scoped call sends the
// `X-Tenant-ID` header (the pre-auth scoping mechanism); tenant-create is the one
// call that doesn't. No business logic lives here — it mirrors the server surface.
import type {
  AcceptInviteRequest,
  AdminUser,
  ApiContract,
  Approval,
  Artifact,
  ArtifactPreview,
  Clarification,
  CurrentUser,
  DashboardRollup,
  DriftRecord,
  GapReport,
  GateCriteria,
  Integration,
  Invitation,
  Lifecycle,
  LoginRequest,
  OnboardingHub,
  PhaseCatalog,
  Project,
  ProjectProfile,
  PublishResult,
  Repository,
  ResetRequest,
  RoleCoverage,
  Run,
  RunEvent,
  Runner,
  RunnerToken,
  RunTranscript,
  SignupRequest,
  Tenant,
  TestConnectionResult,
  TraceEdge,
  TraceGraph,
  TriggerResult,
  WorkItem,
  WorkItemCard,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface ReqOpts {
  tenantId?: string;
  body?: unknown;
  query?: Record<string, string | undefined>;
}

function getCsrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function req<T>(method: string, path: string, opts: ReqOpts = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.tenantId) headers["X-Tenant-ID"] = opts.tenantId;
  // Django SessionAuthentication requires X-CSRFToken on all unsafe methods.
  if (method !== "GET" && method !== "HEAD") {
    const csrf = getCsrfToken();
    if (csrf) headers["X-CSRFToken"] = csrf;
  }

  let url = BASE + path;
  if (opts.query) {
    const qs = Object.entries(opts.query)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v as string)}`)
      .join("&");
    if (qs) url += (path.includes("?") ? "&" : "?") + qs;
  }

  const res = await fetch(url, {
    method,
    headers,
    credentials: "include",
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const msg =
      (data && (data.detail || JSON.stringify(data))) || `${res.status} ${res.statusText}`;
    if (res.status === 401) {
      window.dispatchEvent(new CustomEvent("auth:unauthorized"));
    }
    throw new ApiError(res.status, msg, data);
  }
  return data as T;
}

export const api = {
  // Auth (Phase 4.8 foundation): session cookies; tenant is server-derived.
  me: () => req<CurrentUser>("GET", "/auth/me/"),
  login: (body: LoginRequest) => req<CurrentUser>("POST", "/auth/login/", { body }),
  logout: () => req<Record<string, never>>("POST", "/auth/logout/"),

  // Phase 4.8 T2 — public auth (no session yet): signup, invite-accept, reset.
  signup: (body: SignupRequest) => req<CurrentUser>("POST", "/auth/signup/", { body }),
  acceptInvitation: (body: AcceptInviteRequest) =>
    req<CurrentUser>("POST", "/auth/accept-invitation/", { body }),
  requestReset: (email: string) =>
    req<Record<string, never>>("POST", "/auth/request-reset/", { body: { email } }),
  resetPassword: (body: ResetRequest) =>
    req<Record<string, never>>("POST", "/auth/reset/", { body }),

  // Phase 4.8 T2 — admin: users, invitations, memberships, role coverage (4.7 T3/T4).
  listUsers: () => req<AdminUser[]>("GET", "/users/"),
  createInvitation: (body: {
    email: string;
    name?: string;
    grants?: { project_id: string; role: string }[];
  }) => req<Invitation>("POST", "/invitations/", { body }),
  resendInvitation: (id: string) =>
    req<Record<string, unknown>>("POST", `/invitations/${id}/resend/`),
  revokeInvitation: (id: string) =>
    req<{ status: string }>("POST", `/invitations/${id}/revoke/`),
  createMembership: (projectId: string, body: { user_id: string; role: string }) =>
    req<Record<string, unknown>>("POST", `/projects/${projectId}/memberships/`, { body }),
  deleteMembership: (projectId: string, membershipId: string) =>
    req<void>("DELETE", `/projects/${projectId}/memberships/${membershipId}/`),
  roleCoverage: (projectId: string) =>
    req<RoleCoverage>("GET", `/projects/${projectId}/role-coverage/`),

  // Phase 4.8 T2 — companion enrollments (4.7 T11). POST issues a one-time token.
  // Backend groups enrollments by machine label on GET; POST binds developer_id from session.
  listRunners: () => req<Runner[]>("GET", "/runners/"),
  createRunner: (body: { project_id: string; label?: string }) =>
    req<RunnerToken>("POST", "/runners/", { body }),

  // Phase 4.8 T3 — integrations management + secret store (4.7 T6). Session-derived
  // tenant; secrets are write-only and never appear in any response.
  listIntegrations: () => req<Integration[]>("GET", "/integrations/"),
  createIntegration: (body: {
    capability: string;
    vendor: string;
    binding: Record<string, unknown>;
    secrets: Record<string, unknown>;
  }) => req<Integration>("POST", "/integrations/", { body }),
  patchIntegration: (id: string, body: Partial<Record<string, unknown>>) =>
    req<Integration>("PATCH", `/integrations/${id}/`, { body }),
  deleteIntegration: (id: string) => req<void>("DELETE", `/integrations/${id}/`),
  testIntegrationConnection: (id: string) =>
    req<TestConnectionResult>("POST", `/integrations/${id}/test-connection/`),

  // Phase 4.8 T3 — repositories (4.7 T7). Session-derived tenant; member-scoped reads,
  // tech_lead/admin writes.
  // Backend wraps the list: { repo_topology, repositories: [...] } — unwrap here.
  listRepositories: async (projectId: string): Promise<Repository[]> => {
    const data = await req<{ repo_topology: string; repositories: Repository[] }>(
      "GET", `/projects/${projectId}/repositories/`
    );
    return data.repositories;
  },
  createRepository: (
    projectId: string,
    body: { name: string; role: string; base_branch: string },
  ) => req<Repository>("POST", `/projects/${projectId}/repositories/`, { body }),
  deleteRepository: (projectId: string, repoId: string) =>
    req<void>("DELETE", `/projects/${projectId}/repositories/${repoId}/`),

  // Tenants (bootstrap — no tenant context yet).
  createTenant: (name: string) => req<Tenant>("POST", "/tenants/", { body: { name } }),

  // Projects + profile.
  listProjects: (tenantId: string) => req<Project[]>("GET", "/projects/", { tenantId }),
  createProject: (
    tenantId: string,
    name: string,
    opts?: { track?: string; repo_topology?: string },
  ) => req<Project>("POST", "/projects/", { tenantId, body: { name, ...opts } }),
  getProfile: async (tenantId: string, projectId: string): Promise<ProjectProfile | null> => {
    try {
      return await req<ProjectProfile>("GET", `/projects/${projectId}/profile/`, { tenantId });
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }
  },
  putProfile: (tenantId: string, projectId: string, patch: Partial<ProjectProfile>) =>
    req<ProjectProfile>("PUT", `/projects/${projectId}/profile/`, { tenantId, body: patch }),

  // Work items + phase trigger.
  listWorkItems: (
    tenantId: string,
    projectId: string,
    opts: { state?: string; type?: string; parent?: string; phase?: string } = {},
  ) =>
    req<WorkItemCard[]>("GET", "/work-items/", {
      tenantId,
      query: { project: projectId, ...opts },
    }),
  createWorkItem: (
    tenantId: string,
    projectId: string,
    data: { type: string; feature_stream?: string },
  ) => req<WorkItem>("POST", "/work-items/", { tenantId, body: { project: projectId, ...data } }),
  getWorkItem: (tenantId: string, workItemId: string) =>
    req<WorkItemCard>("GET", `/work-items/${workItemId}/`, { tenantId }),
  patchWorkItem: (
    tenantId: string,
    workItemId: string,
    patch: { title?: string; description?: string; type?: string },
  ) => req<WorkItem>("PATCH", `/work-items/${workItemId}/`, { tenantId, body: patch }),
  triggerPhase: (tenantId: string, workItemId: string, agentKey: string) =>
    req<TriggerResult>("POST", `/work-items/${workItemId}/trigger/`, {
      tenantId,
      body: { agent_key: agentKey },
    }),

  // Phase 4.8 T4 — lifecycle rail (bucket B; type-adaptive plan/build/remediation).
  getLifecycle: (tenantId: string, workItemId: string) =>
    req<Lifecycle>("GET", `/work-items/${workItemId}/lifecycle/`, { tenantId }),

  // Phase 4.8 T4 — phase catalog (bucket B gap C). Tenant-agnostic static catalog.
  listPhases: () => req<PhaseCatalog>("GET", "/phases/"),

  // Read planes.
  listRuns: (tenantId: string, q: { work_item?: string; project?: string }) =>
    req<Run[]>("GET", "/runs/", { tenantId, query: q }),
  getRun: (tenantId: string, runId: string) => req<Run>("GET", `/runs/${runId}/`, { tenantId }),
  // S-19 live console: no new endpoint — polls the run + its event stream (DECISION: confirmed
  // in SCREEN_BUILD_MAP.md "Notes for builders").
  listEvents: (tenantId: string, q: { target_type: string; target_id: string }) =>
    req<RunEvent[]>("GET", "/events/", { tenantId, query: q }),
  listArtifacts: (tenantId: string, q: { project?: string; phase?: string; status?: string }) =>
    req<Artifact[]>("GET", "/artifacts/", { tenantId, query: q }),
  listTraceEdges: (tenantId: string, projectId: string) =>
    req<TraceEdge[]>("GET", "/trace-edges/", { tenantId, query: { project: projectId } }),
  getTraceability: (tenantId: string, projectId: string) =>
    req<TraceGraph>("GET", `/projects/${projectId}/traceability/`, { tenantId }),

  // Gates.
  listApprovals: (tenantId: string, q: { decision?: string } = {}) =>
    req<Approval[]>("GET", "/approvals/", { tenantId, query: q }),
  decideApproval: (
    tenantId: string,
    approvalId: string,
    body: {
      user_id?: string;
      decision: "approved" | "rejected";
      comment?: string;
      satisfied?: Record<string, boolean>;
    },
  ) => req<Record<string, unknown>>("POST", `/approvals/${approvalId}/decide/`, { tenantId, body }),

  // Phase 4.8 T4 — generalized criteria-gate checklist (bucket B, S-22, DECISION-6).
  getGateCriteria: (tenantId: string, approvalId: string) =>
    req<GateCriteria>("GET", `/approvals/${approvalId}/criteria/`, { tenantId }),

  // Clarifications (interactive Q&A — req #2): list pending and answer them in the web app.
  listClarifications: (
    tenantId: string,
    q: { status?: string; work_item?: string; run?: string } = {},
  ) => req<Clarification[]>("GET", "/clarifications/", { tenantId, query: q }),
  answerClarification: (
    tenantId: string,
    clarificationId: string,
    body: { user_id?: string; answers: Record<string, unknown> },
  ) =>
    req<Record<string, unknown>>("POST", `/clarifications/${clarificationId}/answer/`, {
      tenantId,
      body,
    }),

  // Phase 4.8 T5 — brownfield onboarding (4.7 T8). Session-derived tenant.
  getOnboardingHub: (projectId: string) =>
    req<OnboardingHub>("GET", `/projects/${projectId}/onboarding/`),
  startCodeIntel: (projectId: string, repoId: string) =>
    req<Record<string, unknown>>("POST", `/projects/${projectId}/code-intel/`, {
      body: { repo_id: repoId },
    }),
  runGapReport: (projectId: string) =>
    req<Record<string, unknown>>("POST", `/projects/${projectId}/gap-report/`),
  getGapReport: (projectId: string) =>
    req<GapReport>("GET", `/projects/${projectId}/gap-report/`),

  // Phase 4.8 T5 — API contracts & drift (4.7 T9).
  listApiContracts: (projectId: string) =>
    req<ApiContract[]>("GET", `/projects/${projectId}/api-contracts/`),
  getApiContract: (projectId: string, artifactId: string) =>
    req<ApiContract>("GET", `/projects/${projectId}/api-contracts/${artifactId}/`),
  listDrift: (projectId: string) => req<DriftRecord[]>("GET", `/projects/${projectId}/drift/`),
  decideDrift: (driftId: string, body: { decision: "accept" | "reject"; comment?: string }) =>
    req<Record<string, unknown>>("POST", `/drift/${driftId}/decide/`, { body }),

  // Phase 4.8 T5 — artifact preview read-through (4.7 T10, DECISION-5).
  getArtifactPreview: (artifactId: string) =>
    req<ArtifactPreview>("GET", `/artifacts/${artifactId}/preview/`),

  // Phase 4.8 T5 — run transcript (new, DECISION-7). Read-only persisted conversation.
  getRunTranscript: (tenantId: string, runId: string) =>
    req<RunTranscript>("GET", `/runs/${runId}/transcript/`, { tenantId }),

  // Phase 4.8 T5 — manual gate-respecting publish (new, DECISION-8). Never bypasses a gate.
  publishArtifact: (
    artifactId: string,
    body: { target_capability: string; destination: string },
  ) => req<PublishResult>("POST", `/artifacts/${artifactId}/publish/`, { body }),

  // Phase 4.8 T5 — dashboard rollup (bucket B, S-31).
  getDashboard: (projectId: string) =>
    req<DashboardRollup>("GET", `/projects/${projectId}/dashboard/`),

  // Offline takeover (S-32) — reuses GET /runners/ (4.7-T11) + existing take-over/.
  takeOverRun: (tenantId: string, runId: string) =>
    req<Record<string, unknown>>("POST", `/runs/${runId}/take-over/`, { tenantId }),
};
