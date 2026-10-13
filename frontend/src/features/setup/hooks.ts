// Query/mutation hooks for the project-setup group (S-09..S-13).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import type { ProjectProfile } from "../../types";

// ── Create project (S-09) ────────────────────────────────────────────────
export function useCreateProject() {
  const { currentUser } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; track: "greenfield" | "brownfield" }) =>
      api.createProject(currentUser?.tenant.id ?? "", body.name, {
        track: body.track,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["auth", "me"] }),
  });
}

// ── Project profile editor (S-10) ────────────────────────────────────────
export function useProfile(projectId: string | undefined) {
  const { currentUser } = useAuth();
  return useQuery({
    queryKey: ["profile", projectId],
    queryFn: () => api.getProfile(currentUser?.tenant.id ?? "", projectId as string),
    enabled: Boolean(projectId && currentUser),
  });
}

export function useSaveProfile(projectId: string | undefined) {
  const { currentUser } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<ProjectProfile>) =>
      api.putProfile(currentUser?.tenant.id ?? "", projectId as string, patch),
    onSuccess: (data) => {
      qc.setQueryData(["profile", projectId], data);
      // Overrides may have changed — effective export policy must refetch.
      qc.invalidateQueries({ queryKey: ["export-policy", projectId] });
    },
  });
}

// Phase-scoped export policy (defaults + overrides + connector presence) — drives the
// profile editor's export matrix; the Export modal reads its target off the preview.
export function useExportPolicy(projectId: string | undefined) {
  return useQuery({
    queryKey: ["export-policy", projectId],
    queryFn: () => api.getExportPolicy(projectId as string),
    enabled: Boolean(projectId),
  });
}

// ── Integrations grid + connect drawer (S-11/S-12) ───────────────────────
export function useIntegrations() {
  return useQuery({ queryKey: ["integrations"], queryFn: api.listIntegrations });
}

// Per-capability vendor + field catalog (Bugs #40) — static wiring metadata.
export function useIntegrationsCatalog() {
  return useQuery({
    queryKey: ["integrations", "catalog"],
    queryFn: api.integrationsCatalog,
    staleTime: Infinity,
  });
}

export function useCreateIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.createIntegration,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["integrations"] }),
  });
}

export function usePatchIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<Record<string, unknown>> }) =>
      api.patchIntegration(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["integrations"] }),
  });
}

export function useTestConnection() {
  return useMutation({ mutationFn: (id: string) => api.testIntegrationConnection(id) });
}

// Test credentials before they're saved (Bugs S.No 156).
export function useTestCredentials() {
  return useMutation({
    mutationFn: (body: {
      capability: string;
      vendor: string;
      binding?: Record<string, string>;
      secrets?: Record<string, string>;
    }) => api.testIntegrationCredentials(body),
  });
}

// ── Repositories (S-13) ───────────────────────────────────────────────────
// One request, one cache entry, two views of it. The endpoint answers with the list AND the
// project's topology; the topology used to be thrown away here and recomputed on screen from the
// count, with a rule that disagreed with the platform's (S.No 212 — S.No 104's problem, moved).
function repositoriesQuery(projectId: string | undefined) {
  return {
    queryKey: ["repositories", projectId],
    queryFn: () => api.getRepositories(projectId as string),
    enabled: Boolean(projectId),
  };
}

export function useRepositories(projectId: string | undefined) {
  return useQuery({ ...repositoriesQuery(projectId), select: (data) => data.repositories });
}

/** The project's repository topology as the platform computed it — never worked out on screen. */
export function useRepositoryTopology(projectId: string | undefined) {
  return useQuery({ ...repositoriesQuery(projectId), select: (data) => data.repo_topology });
}

export function useCreateRepository(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; role: string; base_branch: string; preview_url?: string }) =>
      api.createRepository(projectId as string, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["repositories", projectId] }),
  });
}

export function useDeleteRepository(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (repoId: string) => api.deleteRepository(projectId as string, repoId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["repositories", projectId] }),
  });
}

export function useUpdateRepository(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ repoId, body }: { repoId: string; body: { preview_url?: string } }) =>
      api.updateRepository(projectId as string, repoId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["repositories", projectId] }),
  });
}

// "Set default" (S.No 212). The button's handler was a stub that threw the repository away, beside
// a note saying the backend could not do this yet — the endpoint had existed, permission-checked,
// all along. The list refreshes, so the "default" marker moving IS the confirmation (option A).
export function useSetDefaultRepository(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (repoId: string) => api.setDefaultRepository(projectId as string, repoId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["repositories", projectId] }),
  });
}

// ── Test reporting — CI ingest tokens (P3-09bX) ────────────────────────────
export function useCiTokens(projectId: string | undefined) {
  return useQuery({
    queryKey: ["ci-tokens", projectId],
    queryFn: () => api.listCiTokens(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function useCreateCiToken(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { label?: string }) => api.createCiToken(projectId as string, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ci-tokens", projectId] }),
  });
}

export function useRevokeCiToken(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tokenId: string) => api.revokeCiToken(projectId as string, tokenId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ci-tokens", projectId] }),
  });
}
