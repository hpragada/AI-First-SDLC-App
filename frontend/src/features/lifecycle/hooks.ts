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
      priority?: string;
    }) => api.createWorkItem(tenantId, projectId as string, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["work-items", projectId] }),
  });
}

// A story's child test_case work items + automation status (P3-09b coverage screen).
export function useTestCases(storyId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["test-cases", storyId],
    queryFn: () => api.listTestCases(tenantId, storyId as string),
    enabled: Boolean(storyId),
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
    mutationFn: (patch: { title?: string; description?: string; type?: string; repo?: string | null }) =>
      api.patchWorkItem(tenantId, workItemId as string, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["work-items"] });
      qc.invalidateQueries({ queryKey: ["lifecycle", workItemId] });
    },
  });
}

// Patch ANY work item by id (not bound to one) — used by the Task Breakdown repo-assignment
// review, which overrides the target repo across many proposed tasks (Option C, B2).
export function usePatchAnyWorkItem() {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: { repo?: string | null } }) =>
      api.patchWorkItem(tenantId, id, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["work-items"] }),
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

// Resume a run parked at an error (Bugs S.No 157): the workflow is still alive and waiting, so
// this picks up at the failed step — the build/phase already done is kept, not re-run.
export function useResumeRun(runId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.resumeRun(tenantId, runId as string),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["run", runId] });
      qc.invalidateQueries({ queryKey: ["run-events", runId] });
      qc.invalidateQueries({ queryKey: ["runs"] });
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

// Answered/cancelled clarifications for the history tab — paged, and filterable by work item
// and phase. Deliberately a separate hook from `useClarifications`: that one polls every 4s for
// pending questions, which is wrong for a record that only changes when someone answers.
export function useClarificationHistory(q: {
  project?: string;
  work_item?: string;
  phase?: string;
  // Free-text search across questions, answers and the agent's reason for asking. Server-side,
  // because the list is paged — searching in the browser would only search the visible page.
  q?: string;
  page?: number;
}) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["clarification-history", q],
    queryFn: () => api.listClarificationHistory(tenantId, q),
    enabled: Boolean(tenantId && q.project),
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
export function useApprovals(
  q: { decision?: string; work_item?: string; run?: string; project?: string } = {},
) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["approvals", q],
    queryFn: () => api.listApprovals(tenantId, q),
    enabled: Boolean(tenantId),
  });
}

// Decided gates for the history tab — paged, filterable by work item and phase. Same reasoning
// as useClarificationHistory: a decided gate is a record, not a live queue.
export function useApprovalHistory(q: {
  project?: string;
  work_item?: string;
  phase?: string;
  page?: number;
}) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["approval-history", q],
    queryFn: () => api.listApprovalHistory(tenantId, q),
    enabled: Boolean(tenantId && q.project),
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
      revise,
    }: {
      id: string;
      decision: "approved" | "rejected";
      comment?: string;
      conditions?: { key: string; satisfied: boolean }[];
      revise?: boolean;
    }) => api.decideApproval(tenantId, id, { decision, comment, conditions, revise }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approvals"] });
      qc.invalidateQueries({ queryKey: ["gate-criteria"] });
      qc.invalidateQueries({ queryKey: ["lifecycle"] });
      // A "Request changes" starts a NEW run — but not before this response returns: the gate
      // service replies as soon as it has signalled Temporal, and the revision run is created
      // later, by the workflow. So there is no run id to show here; refresh the list and let it
      // appear. (Promising an id in this response would be promising one that does not exist.)
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}
