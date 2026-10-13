// Query/mutation hooks for the lifecycle group (S-14..S-23).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import type { WorkItemState } from "../../types";

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

// Bugs S.No 215. A test case IS a work item underneath, which is why creating one refreshed the
// work-items list — and never the story's test-case table that was actually on screen. It saved,
// the table kept showing the old list, and it looked like a failure worth trying again. This
// refreshes both: the table in front of the person, and the board the case also appears on.
export function useCreateTestCase(projectId: string | undefined, storyId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { title: string; priority: string; description: string }) =>
      api.createWorkItem(tenantId, projectId as string, {
        type: "test_case", parent: storyId, ...data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["work-items", projectId] });
      qc.invalidateQueries({ queryKey: ["test-cases", storyId] });
    },
  });
}

// A story's child test_case work items + automation status (P3-09b coverage screen).
export function useTestCases(storyId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["test-cases", storyId],
    queryFn: () => api.listTestCases(tenantId, storyId as string),
    enabled: Boolean(storyId),
    // Same class as S.No 215: a script is generated on the developer's machine, and nothing told
    // this table when it finished — "Generating…" stayed until a reload. Poll while any row is
    // generating, and only then.
    refetchInterval: (query) =>
      query.state.data?.some((tc) => tc.automation_status === "generating") ? 4000 : false,
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
      // `work-item` (singular) is the detail page's own query, and it was missing. That did not
      // matter while the only caller was the repo dropdown — a repo is not drawn in the page
      // heading — but an edited TITLE is, so saving one left the old title on screen until a
      // reload. The board refreshed and the page the user was looking at did not.
      qc.invalidateQueries({ queryKey: ["work-item", workItemId] });
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

// Bugs S.No 140 — close a work item that cannot be built.
//
// Invalidates broadly on purpose. Cancelling changes what four different screens should show:
// the item itself, the board it sits on (where it now disappears by default), the dashboard
// count beside that board, and — when the item is a blocking defect — the gate it just
// released, which has gained an acknowledgement the reviewer has to tick. Refetching one of
// those and not the others is how a board and its own count end up disagreeing.
export function useTransitionWorkItem(workItemId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ toState, reason }: { toState: WorkItemState; reason?: string }) =>
      api.transitionWorkItem(tenantId, workItemId as string, toState, reason ?? ""),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["work-item", workItemId] });
      qc.invalidateQueries({ queryKey: ["work-items"] });
      qc.invalidateQueries({ queryKey: ["lifecycle", workItemId] });
      qc.invalidateQueries({ queryKey: ["approvals"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

// Stop a run on purpose, so it can be picked up later. Resumed through `useResumeRun` below — the
// workflow waits on one signal whether it parked at an error or was paused deliberately, which is
// why there is no second resume hook.
export function usePauseRun(runId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.pauseRun(tenantId, runId as string),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["run", runId] });
      // Same three keys as resume, and for the same reason: the console reads the run, its event
      // list and the runs table, and refreshing one without the others leaves two of them stale.
      qc.invalidateQueries({ queryKey: ["events", "run", runId] });
      qc.invalidateQueries({ queryKey: ["runs"] });
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
      // The key `useRunEvents` actually reads. This said ["run-events", runId], which no query
      // uses, so a resumed run's event list never refreshed — found beside S.No 215, same class.
      qc.invalidateQueries({ queryKey: ["events", "run", runId] });
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

// ── Clarifications (S-20) ──────────────────────────────────────────────────
export function useClarifications(
  // `project` scopes the whole project's pending questions server-side. The Clarifications
  // screen used to fetch the tenant's and narrow them to the visible backlog in the browser,
  // which silently dropped every question asked by a run on a HIDDEN carrier work item —
  // accessibility judging, code indexing, the gap report. Those runs then waited for ever on
  // an answer the screen would not let anyone give.
  q: { status?: string; work_item?: string; run?: string; project?: string } = {},
) {
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
