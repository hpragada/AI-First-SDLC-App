// Typed client for the Phase-0 REST API. Every tenant-scoped call sends the
// `X-Tenant-ID` header (the pre-auth scoping mechanism); tenant-create is the one
// call that doesn't. No business logic lives here — it mirrors the server surface.
import type {
  AcceptInviteRequest,
  AdminUser,
  Approval,
  Artifact,
  Clarification,
  CurrentUser,
  Integration,
  Invitation,
  LoginRequest,
  Project,
  ProjectProfile,
  Repository,
  ResetRequest,
  RoleCoverage,
  Run,
  Runner,
  RunnerToken,
  SignupRequest,
  Tenant,
  TestConnectionResult,
  TraceEdge,
  TraceGraph,
  TriggerResult,
  WorkItem,
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

async function req<T>(method: string, path: string, opts: ReqOpts = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.tenantId) headers["X-Tenant-ID"] = opts.tenantId;

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
  listRunners: () => req<Runner[]>("GET", "/runners/"),
  createRunner: (body: { projects: string[] }) =>
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
  listRepositories: (projectId: string) =>
    req<Repository[]>("GET", `/projects/${projectId}/repositories/`),
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
  listWorkItems: (tenantId: string, projectId: string, state?: string) =>
    req<WorkItem[]>("GET", "/work-items/", { tenantId, query: { project: projectId, state } }),
  createWorkItem: (
    tenantId: string,
    projectId: string,
    data: { type: string; feature_stream?: string },
  ) => req<WorkItem>("POST", "/work-items/", { tenantId, body: { project: projectId, ...data } }),
  triggerPhase: (tenantId: string, workItemId: string, agentKey: string) =>
    req<TriggerResult>("POST", `/work-items/${workItemId}/trigger/`, {
      tenantId,
      body: { agent_key: agentKey },
    }),

  // Read planes.
  listRuns: (tenantId: string, q: { work_item?: string; project?: string }) =>
    req<Run[]>("GET", "/runs/", { tenantId, query: q }),
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
    body: { user_id: string; decision: "approved" | "rejected"; comment?: string },
  ) => req<Record<string, unknown>>("POST", `/approvals/${approvalId}/decide/`, { tenantId, body }),

  // Clarifications (interactive Q&A — req #2): list pending and answer them in the web app.
  listClarifications: (
    tenantId: string,
    q: { status?: string; work_item?: string; run?: string } = {},
  ) => req<Clarification[]>("GET", "/clarifications/", { tenantId, query: q }),
  answerClarification: (
    tenantId: string,
    clarificationId: string,
    body: { user_id: string; answers: Record<string, unknown> },
  ) =>
    req<Record<string, unknown>>("POST", `/clarifications/${clarificationId}/answer/`, {
      tenantId,
      body,
    }),
};
