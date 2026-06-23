// Typed client for the Phase-0 REST API. Every tenant-scoped call sends the
// `X-Tenant-ID` header (the pre-auth scoping mechanism); tenant-create is the one
// call that doesn't. No business logic lives here — it mirrors the server surface.
import type {
  Approval,
  Artifact,
  Project,
  ProjectProfile,
  Run,
  Tenant,
  TraceEdge,
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
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const msg =
      (data && (data.detail || JSON.stringify(data))) || `${res.status} ${res.statusText}`;
    throw new ApiError(res.status, msg, data);
  }
  return data as T;
}

export const api = {
  // Tenants (bootstrap — no tenant context yet).
  createTenant: (name: string) => req<Tenant>("POST", "/tenants/", { body: { name } }),

  // Projects + profile.
  listProjects: (tenantId: string) => req<Project[]>("GET", "/projects/", { tenantId }),
  createProject: (tenantId: string, name: string) =>
    req<Project>("POST", "/projects/", { tenantId, body: { name } }),
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

  // Gates.
  listApprovals: (tenantId: string, q: { decision?: string } = {}) =>
    req<Approval[]>("GET", "/approvals/", { tenantId, query: q }),
  decideApproval: (
    tenantId: string,
    approvalId: string,
    body: { user_id: string; decision: "approved" | "rejected"; comment?: string },
  ) => req<Record<string, unknown>>("POST", `/approvals/${approvalId}/decide/`, { tenantId, body }),
};
