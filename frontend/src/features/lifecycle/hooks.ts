// Query/mutation hooks for the lifecycle group (S-14..S-23).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api";
import { useAuth } from "../../auth/AuthContext";

function useTenantId() {
  const { currentUser } = useAuth();
  return currentUser?.tenant.id ?? "";
}

// ── Work items board + detail (S-14/15/16/17) ────────────────────────────
export function useWorkItems(
  projectId: string | undefined,
  opts: { state?: string; type?: string; parent?: string; phase?: string } = {},
) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["work-items", projectId, opts],
    queryFn: () => api.listWorkItems(tenantId, projectId as string, opts),
    enabled: Boolean(projectId && tenantId),
  });
}

export function useCreateWorkItem(projectId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      type: string;
      title?: string;
      description?: string;
      feature_stream?: string;
      parent?: string;
    }) => api.createWorkItem(tenantId, projectId as string, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["work-items", projectId] }),
  });
}

export function useWorkItem(workItemId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["work-item", workItemId],
    queryFn: () => api.getWorkItem(tenantId, workItemId as string),
    enabled: Boolean(workItemId && tenantId),
  });
}

export function usePatchWorkItem(workItemId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: { title?: string; description?: string; type?: string }) =>
      api.patchWorkItem(tenantId, workItemId as string, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["work-items"] });
      qc.invalidateQueries({ queryKey: ["lifecycle", workItemId] });
    },
  });
}

export function useLifecycle(workItemId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["lifecycle", workItemId],
    queryFn: () => api.getLifecycle(tenantId, workItemId as string),
    enabled: Boolean(workItemId && tenantId),
    refetchInterval: 4000,
  });
}

// ── Phase catalog (S-14 columns, S-18 trigger picker) ─────────────────────
export function usePhaseCatalog() {
  return useQuery({ queryKey: ["phases"], queryFn: api.listPhases });
}

// ── Phases & runs (S-18/19) ────────────────────────────────────────────────
export function useRuns(q: { work_item?: string; project?: string }) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["runs", q],
    queryFn: () => api.listRuns(tenantId, q),
    enabled: Boolean(tenantId && (q.work_item || q.project)),
    refetchInterval: 4000,
  });
}

export function useRun(runId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.getRun(tenantId, runId as string),
    enabled: Boolean(runId && tenantId),
    refetchInterval: 3000,
  });
}

export function useRunEvents(runId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["events", "run", runId],
    queryFn: () => api.listEvents(tenantId, { target_type: "run", target_id: runId as string }),
    enabled: Boolean(runId && tenantId),
    refetchInterval: 3000,
  });
}

export function useTriggerPhase(workItemId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (agentKey: string) => api.triggerPhase(tenantId, workItemId as string, agentKey),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      qc.invalidateQueries({ queryKey: ["lifecycle", workItemId] });
    },
  });
}

// ── Clarifications (S-20) ──────────────────────────────────────────────────
export function useClarifications(q: { status?: string; work_item?: string; run?: string } = {}) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["clarifications", q],
    queryFn: () => api.listClarifications(tenantId, q),
    enabled: Boolean(tenantId),
    refetchInterval: 4000,
  });
}

export function useAnswerClarification() {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, answers }: { id: string; answers: Record<string, unknown> }) =>
      api.answerClarification(tenantId, id, { answers }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["clarifications"] }),
  });
}

// ── Gates (S-21/22) ─────────────────────────────────────────────────────────
export function useApprovals(q: { decision?: string; work_item?: string; run?: string } = {}) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["approvals", q],
    queryFn: () => api.listApprovals(tenantId, q),
    enabled: Boolean(tenantId),
  });
}

export function useGateCriteria(approvalId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["gate-criteria", approvalId],
    queryFn: () => api.getGateCriteria(tenantId, approvalId as string),
    enabled: Boolean(approvalId && tenantId),
  });
}

export function useDecideApproval() {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      decision,
      comment,
      conditions,
    }: {
      id: string;
      decision: "approved" | "rejected";
      comment?: string;
      conditions?: { key: string; satisfied: boolean }[];
    }) => api.decideApproval(tenantId, id, { decision, comment, conditions }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approvals"] });
      qc.invalidateQueries({ queryKey: ["gate-criteria"] });
      qc.invalidateQueries({ queryKey: ["lifecycle"] });
    },
  });
}
