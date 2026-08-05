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
  CapabilityCatalogEntry,
  CIToken,
  CITokenIssued,
  Clarification,
  CurrentUser,
  DashboardRollup,
  DriftRecord,
  ExportPolicy,
  GapReport,
  GateCriteria,
  Integration,
  Invitation,
  InvitationPreview,
  Lifecycle,
  LoginRequest,
  OnboardingHub,
  PhaseCatalog,
  Page,
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
  SourceDocument,
  Tenant,
  TestCase,
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

async function uploadFile<T>(path: string, file: File): Promise<T> {
  const headers: Record<string, string> = {};
  const csrf = getCsrfToken();
  if (csrf) headers["X-CSRFToken"] = csrf;
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(BASE + path, { method: "POST", headers, credentials: "include", body: form });
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const msg = (data && (data.detail || JSON.stringify(data))) || `${res.status} ${res.statusText}`;
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
  // The accept-invite page's pre-submit lookup — org/inviter/role/project to display
  // before the user fills anything in. Public, pre-auth, never returns the token/hash. The
  // token rides the POST body (like accept), not the URL, so it stays out of access logs.
  getInvitationPreview: (token: string) =>
    req<InvitationPreview>("POST", "/auth/invitations/preview/", { body: { token } }),
  acceptInvitation: (body: AcceptInviteRequest) =>
    req<CurrentUser>("POST", "/auth/accept-invitation/", { body }),
  requestReset: (email: string) =>
    req<Record<string, never>>("POST", "/auth/request-reset/", { body: { email } }),
  resetPassword: (body: ResetRequest) =>
    req<Record<string, never>>("POST", "/auth/reset/", { body }),

  // Phase 4.8 T2 — admin: users, invitations, memberships, role coverage (4.7 T3/T4).
  listUsers: () => req<AdminUser[]>("GET", "/users/"),
  // GET /users/ only ever returns accepted accounts — pending/revoked/expired invitations
  // are a separate resource the Users & Invitations table also needs to render.
  listInvitations: () => req<Invitation[]>("GET", "/invitations/"),
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
  // PATCH /api/users/{id}/ — tenant-wide admin flag (separate from per-project role grants
  // above). Backend 409s if this would leave the tenant with no admin.
  setTenantAdmin: (userId: string, isTenantAdmin: boolean) =>
    req<{ id: string; name: string; email: string; is_tenant_admin: boolean }>(
      "PATCH", `/users/${userId}/`, { body: { is_tenant_admin: isTenantAdmin } },
    ),

  // Phase 4.8 T2 — companion enrollments (4.7 T11). POST issues a one-time token.
  // Backend groups enrollments by machine label on GET; POST binds developer_id from session.
  listRunners: () => req<Runner[]>("GET", "/runners/"),
  createRunner: (body: { project_id: string; label?: string }) =>
    req<RunnerToken>("POST", "/runners/", { body }),
  revokeRunner: (id: string) =>
    req<{ id: string; status: string }>("POST", `/runners/${id}/revoke/`),

  // Phase 4.8 T3 — integrations management + secret store (4.7 T6). Session-derived
  // tenant; secrets are write-only and never appear in any response.
  listIntegrations: () => req<Integration[]>("GET", "/integrations/"),
  integrationsCatalog: () =>
    req<CapabilityCatalogEntry[]>("GET", "/integrations/catalog/"),
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

  // Test credentials BEFORE saving them (Bugs S.No 156) — probed on a throwaway connection
  // server-side; nothing is persisted to the tenant.
  testIntegrationCredentials: (body: {
    capability: string;
    vendor: string;
    binding?: Record<string, string>;
    secrets?: Record<string, string>;
  }) => req<TestConnectionResult>("POST", "/integrations/test-credentials/", { body }),

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
    body: { name: string; role: string; base_branch: string; preview_url?: string },
  ) => req<Repository>("POST", `/projects/${projectId}/repositories/`, { body }),
  // PATCH edits an existing repo's settings (currently the manual preview URL); returns the
  // refreshed repo list, same shape as GET.
  updateRepository: (projectId: string, repoId: string, body: { preview_url?: string }) =>
    req<Repository[]>("PATCH", `/projects/${projectId}/repositories/${repoId}/`, { body }),
  deleteRepository: (projectId: string, repoId: string) =>
    req<void>("DELETE", `/projects/${projectId}/repositories/${repoId}/`),

  // Test reporting — per-project CI ingest tokens (P3-09bX-1). Admin-only; session-derived
  // tenant. GET returns metadata only; POST returns the raw secret ONCE; DELETE revokes (204).
  listCiTokens: (projectId: string) =>
    req<CIToken[]>("GET", `/projects/${projectId}/ci-tokens/`),
  createCiToken: (projectId: string, body: { label?: string }) =>
    req<CITokenIssued>("POST", `/projects/${projectId}/ci-tokens/`, { body }),
  revokeCiToken: (projectId: string, tokenId: string) =>
    req<void>("DELETE", `/projects/${projectId}/ci-tokens/${tokenId}/`),

  // Tenants (bootstrap — no tenant context yet).
  createTenant: (name: string) => req<Tenant>("POST", "/tenants/", { body: { name } }),

  // Projects + profile.
  listProjects: (tenantId: string) => req<Project[]>("GET", "/projects/", { tenantId }),
  createProject: (
    tenantId: string,
    name: string,
    opts?: { track?: string }, // B0-2: repo_topology is derived server-side, never client-set.
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
    data: {
      type: string;
      title?: string;
      description?: string;
      feature_stream?: string;
      parent?: string;
      priority?: string; // test_case only — stored in external_ref
    },
  ) => req<WorkItem>("POST", "/work-items/", { tenantId, body: { project: projectId, ...data } }),
  getWorkItem: (tenantId: string, workItemId: string) =>
    req<WorkItemCard>("GET", `/work-items/${workItemId}/`, { tenantId }),
  // A story's child test_case work items + each one's automation status (P3-09b coverage screen).
  listTestCases: (tenantId: string, storyId: string) =>
    req<TestCase[]>("GET", `/work-items/${storyId}/test-cases/`, { tenantId }),
  patchWorkItem: (
    tenantId: string,
    workItemId: string,
    // `repo` (Option C): assign/redirect the target repository; null clears it (default repo).
    patch: { title?: string; description?: string; type?: string; repo?: string | null },
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
  listApprovals: (tenantId: string, q: { decision?: string; work_item?: string; run?: string } = {}) =>
    req<Approval[]>("GET", "/approvals/", { tenantId, query: q }),
  // Decided-gate history: paged, and filterable by phase/work item/project. Same opt-in rule —
  // `page` is what asks for the envelope.
  listApprovalHistory: (
    tenantId: string,
    q: { project?: string; work_item?: string; phase?: string; decision?: string; page?: number },
  ) =>
    req<Page<Approval>>("GET", "/approvals/", {
      tenantId,
      query: { ...q, page: String(q.page ?? 1) },
    }),
  decideApproval: (
    tenantId: string,
    approvalId: string,
    body: {
      user_id?: string;
      decision: "approved" | "rejected";
      comment?: string;
      // Reviewer's checklist updates — matched server-side by `key` (== GateCriterion.id).
      // Field name/shape must match `GateDecisionSerializer.conditions` exactly.
      conditions?: { key: string; satisfied: boolean }[];
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
  // History: the same endpoint, but paged. Passing `page` is what switches the response to an
  // envelope — callers that omit it (every existing one) still get a bare array.
  listClarificationHistory: (
    tenantId: string,
    q: { project?: string; work_item?: string; phase?: string; page?: number },
  ) =>
    req<Page<Clarification>>("GET", "/clarifications/", {
      tenantId,
      query: { ...q, page: String(q.page ?? 1) },
    }),
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
  onboardAtlassian: (projectId: string) =>
    req<Record<string, unknown>>("POST", `/projects/${projectId}/onboard-atlassian/`),
  // B3-4: register user-provided Confluence pages as typed pointers (feeds the gap report).
  linkConfluencePages: (projectId: string, links: { page: string; type: string }[]) =>
    req<{
      linked: { page_id: string; artifact_id: string; type: string; title: string; created: boolean }[];
      errors: { page: string; error: string }[];
    }>("POST", `/projects/${projectId}/link-confluence/`, { body: { links } }),
  listSourceDocuments: (projectId: string) =>
    req<SourceDocument[]>("GET", `/projects/${projectId}/source-documents/`),
  uploadSourceDocument: (projectId: string, file: File) =>
    uploadFile<Record<string, unknown>>(`/projects/${projectId}/source-documents/`, file),
  adoptSourceDocument: (sourceDocumentId: string, targetType: string, userId?: string) =>
    req<Record<string, unknown>>("POST", `/source-documents/${sourceDocumentId}/adopt/`, {
      body: { target_type: targetType, ...(userId ? { user_id: userId } : {}) },
    }),
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
  // destination optional: falls back to the connector's configured space/project key.
  publishArtifact: (
    artifactId: string,
    body: { target_capability: string; destination?: string },
  ) => req<PublishResult>("POST", `/artifacts/${artifactId}/publish/`, { body }),

  // Phase-scoped export policy (team flow decision 2026-07-07): defaults + per-project
  // overrides + which export capabilities have a connector bound.
  getExportPolicy: (projectId: string) =>
    req<ExportPolicy>("GET", `/projects/${projectId}/export-policy/`),

  // Phase 4.8 T5 — dashboard rollup (bucket B, S-31).
  getDashboard: (projectId: string) =>
    req<DashboardRollup>("GET", `/projects/${projectId}/dashboard/`),

  // Offline takeover (S-32) — reuses GET /runners/ (4.7-T11) + existing take-over/.
  takeOverRun: (
    tenantId: string,
    runId: string,
    body: { release?: boolean; actor?: string; reason?: string } = {},
  ) => req<{ work_item_id: string; takeover: boolean }>("POST", `/runs/${runId}/take-over/`, { tenantId, body }),

  // Resume a run parked at an error, from the step that failed (Bugs S.No 157) — the
  // counterpart to take-over: continue the run instead of ending it.
  resumeRun: (tenantId: string, runId: string) =>
    req<{ run_id: string; resumed: boolean; resume_from: string }>(
      "POST", `/runs/${runId}/resume/`, { tenantId },
    ),
};
