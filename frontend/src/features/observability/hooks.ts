// Query/mutation hooks for the brownfield + observability group (S-24..S-34).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api";
import { useAuth } from "../../auth/AuthContext";

function useTenantId() {
  const { currentUser } = useAuth();
  return currentUser?.tenant.id ?? "";
}

// ── Onboarding hub + gap report (S-24/25/26) ───────────────────────────────
export function useOnboardingHub(projectId: string | undefined) {
  return useQuery({
    queryKey: ["onboarding", projectId],
    queryFn: () => api.getOnboardingHub(projectId as string),
    enabled: Boolean(projectId),
    refetchInterval: 4000,
  });
}

export function useSourceDocuments(projectId: string | undefined) {
  return useQuery({
    queryKey: ["source-documents", projectId],
    queryFn: () => api.listSourceDocuments(projectId as string),
    enabled: Boolean(projectId),
    refetchInterval: 4000,
  });
}

export function useUploadSourceDocument(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.uploadSourceDocument(projectId as string, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["source-documents", projectId] });
      qc.invalidateQueries({ queryKey: ["onboarding", projectId] });
    },
  });
}

export function useAdoptSourceDocument(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, targetType, userId }: { id: string; targetType: string; userId?: string }) =>
      api.adoptSourceDocument(id, targetType, userId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["source-documents", projectId] });
      qc.invalidateQueries({ queryKey: ["onboarding", projectId] });
    },
  });
}

export function useOnboardAtlassian(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.onboardAtlassian(projectId as string),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["onboarding", projectId] }),
  });
}

// B3-4: link user-provided Confluence pages as typed pointers; refresh the hub on success.
export function useLinkConfluencePages(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (links: { page: string; type?: string }[]) =>
      api.linkConfluencePages(projectId as string, links),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["onboarding", projectId] }),
  });
}

export function useStartCodeIntel(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (repoId: string) => api.startCodeIntel(projectId as string, repoId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["onboarding", projectId] }),
  });
}

export function useGapReport(projectId: string | undefined) {
  return useQuery({
    queryKey: ["gap-report", projectId],
    queryFn: () => api.getGapReport(projectId as string),
    enabled: Boolean(projectId),
    // Polls like the hub does (S5-8). Without this the Gap report screen only refetched on mount:
    // sitting on it while an agent run finished showed a stale report, or none at all, until the
    // user reloaded by hand. An agent assessment takes minutes — the screen has to notice.
    refetchInterval: 4000,
  });
}

export function useRunGapReport(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.runGapReport(projectId as string),
    onSuccess: () => {
      // The deterministic path builds the report inline (hub.gap flips ready); the agent path
      // is async. Refresh both so whichever ran surfaces without a manual reload.
      qc.invalidateQueries({ queryKey: ["gap-report", projectId] });
      qc.invalidateQueries({ queryKey: ["onboarding", projectId] });
    },
  });
}

// ── API contracts & drift (S-27) ───────────────────────────────────────────
export function useApiContracts(projectId: string | undefined) {
  return useQuery({
    queryKey: ["api-contracts", projectId],
    queryFn: () => api.listApiContracts(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function useDrift(projectId: string | undefined) {
  return useQuery({
    queryKey: ["drift", projectId],
    queryFn: () => api.listDrift(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function useDecideDrift() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision, comment }: { id: string; decision: "accept" | "reject"; comment?: string }) =>
      api.decideDrift(id, { decision, comment }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["drift"] }),
  });
}

// ── Artifacts registry + preview (S-28/29) ─────────────────────────────────
export function useArtifacts(q: {
  project?: string;
  phase?: string;
  status?: string;
  type?: string;
  run?: string;
  work_item?: string;
  latest?: boolean;
}) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["artifacts", q],
    queryFn: () => api.listArtifacts(tenantId, q),
    enabled: Boolean(tenantId && q.project),
  });
}

export function useArtifactPreview(artifactId: string | undefined, raw = false) {
  return useQuery({
    // `raw` is part of the key so switching to the raw file and back is instant and each is
    // cached on its own — the rendered view is not thrown away to look at the source.
    queryKey: ["artifact-preview", artifactId, raw],
    queryFn: () => api.getArtifactPreview(artifactId as string, raw),
    enabled: Boolean(artifactId),
  });
}

export function usePublishArtifact(artifactId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { target_capability: string; destination: string }) =>
      api.publishArtifact(artifactId as string, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["artifact-preview", artifactId] }),
  });
}

// ── Traceability (S-30) ─────────────────────────────────────────────────────
export function useTraceability(projectId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["traceability", projectId],
    queryFn: () => api.getTraceability(tenantId, projectId as string),
    enabled: Boolean(projectId && tenantId),
  });
}

// ── Dashboard (S-31) ─────────────────────────────────────────────────────────
export function useDashboard(projectId: string | undefined) {
  return useQuery({
    queryKey: ["dashboard", projectId],
    queryFn: () => api.getDashboard(projectId as string),
    enabled: Boolean(projectId),
    refetchInterval: 4000,
  });
}

// ── Offline takeover (S-32) ──────────────────────────────────────────────────
export function useTakeOverRun() {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, release }: { runId: string; release?: boolean }) =>
      api.takeOverRun(tenantId, runId, release ? { release: true } : {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["run"] });
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

// ── Run transcripts (S-33) ───────────────────────────────────────────────────
export function useRunTranscript(runId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["transcript", runId],
    queryFn: () => api.getRunTranscript(tenantId, runId as string),
    enabled: Boolean(runId && tenantId),
  });
}
