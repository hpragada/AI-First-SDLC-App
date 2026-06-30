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
  });
}

export function useRunGapReport(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.runGapReport(projectId as string),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["gap-report", projectId] }),
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
export function useArtifacts(q: { project?: string; phase?: string; status?: string }) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["artifacts", q],
    queryFn: () => api.listArtifacts(tenantId, q),
    enabled: Boolean(tenantId && q.project),
  });
}

export function useArtifactPreview(artifactId: string | undefined) {
  return useQuery({
    queryKey: ["artifact-preview", artifactId],
    queryFn: () => api.getArtifactPreview(artifactId as string),
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
    mutationFn: (runId: string) => api.takeOverRun(tenantId, runId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["run"] }),
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
