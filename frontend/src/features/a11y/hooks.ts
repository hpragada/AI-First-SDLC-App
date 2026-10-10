// Query/mutation hooks for the accessibility screens: the review console (S-36, QA-23) and
// the conformance statement (S-37, QA-24).
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api";
import { useAuth } from "../../auth/AuthContext";

function useTenantId() {
  const { currentUser } = useAuth();
  return currentUser?.tenant.id ?? "";
}

export function useA11yReviewQueue(projectId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["a11y-review", projectId],
    queryFn: () => api.a11yReviewQueue(tenantId, projectId as string),
    enabled: Boolean(projectId && tenantId),
  });
}

// Opening an item is ALSO what claims it and renews the claim (team decision C1), so this
// refetches on an interval a little under the server's lock window. Stop polling and the claim
// lapses by itself — which is the whole point: a reviewer who closes the tab hands the item
// back without anyone having to remember to release it.
const RENEW_MS = 5 * 60 * 1000;

export function useA11yReviewItem(projectId: string | undefined, findingId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["a11y-review-item", projectId, findingId],
    queryFn: () => api.a11yReviewItem(tenantId, projectId as string, findingId as string),
    enabled: Boolean(projectId && findingId && tenantId),
    refetchInterval: RENEW_MS,
    refetchIntervalInBackground: false,
  });
}

// Reading one finding (S-39). No `refetchInterval`, and that is the point: the review item
// polls because polling is what renews its claim, and this read takes no claim to renew. A
// finding opened to be looked at should sit still.
export function useA11yFinding(projectId: string | undefined, findingId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["a11y-finding", projectId, findingId],
    queryFn: () => api.a11yFinding(tenantId, projectId as string, findingId as string),
    enabled: Boolean(projectId && findingId && tenantId),
  });
}

export function useDecideA11yFinding(projectId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { findingId: string; decision: "confirm" | "reject"; note?: string }) =>
      api.a11yReviewDecide(tenantId, projectId as string, vars.findingId, {
        decision: vars.decision,
        note: vars.note,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["a11y-review", projectId] });
      // The board and the tracker both change when a confirmation raises a defect.
      qc.invalidateQueries({ queryKey: ["work-items", projectId] });
    },
  });
}

// The capture, fetched with the session cookie and handed back as a blob URL. Revoked when the
// item or the mode changes, so a long review session does not leak one object URL per click.
export function useA11yCapture(
  projectId: string | undefined,
  findingId: string | undefined,
  kind: "page" | "element",
  available: boolean,
) {
  const [url, setUrl] = useState<string | undefined>();
  const [error, setError] = useState<string | undefined>();

  useEffect(() => {
    let revoked = false;
    let current: string | undefined;
    setUrl(undefined);
    setError(undefined);
    if (!projectId || !findingId || !available) return;
    api
      .getA11yCaptureUrl(projectId, findingId, kind)
      .then((next) => {
        if (revoked) {
          URL.revokeObjectURL(next);
          return;
        }
        current = next;
        setUrl(next);
      })
      .catch(() => setError("the capture could not be loaded"));
    return () => {
      revoked = true;
      if (current) URL.revokeObjectURL(current);
    };
  }, [projectId, findingId, kind, available]);

  return { url, error };
}

// ── Pages & audit (S-38, task 8a) ────────────────────────────────────────────────────────

export function useA11yRoutes(projectId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["a11y-routes", projectId],
    queryFn: () => api.a11yRoutes(tenantId, projectId as string),
    enabled: Boolean(projectId && tenantId),
  });
}

// An audit is claimed and run by a machine, so the screen watches rather than waits. Polling
// only while one is actually in flight: a page left open on a finished audit should not keep
// asking, and `refetchIntervalInBackground` off means a forgotten tab stops by itself.
const AUDIT_POLL_MS = 5000;
// Exported, because the screen asks the same question this poll does — "is anything still
// happening?" — and two copies of this list would drift into disagreeing about whether to show
// a running audit and whether to keep asking about it. Mirrors `baseline.IN_FLIGHT_STATUSES`,
// which is what decides whether the API sends live progress at all.
export const AUDIT_IN_FLIGHT = ["pending", "claimed", "capturing", "judging"];

export function useA11yAudits(projectId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["a11y-audits", projectId],
    queryFn: () => api.a11yAudits(tenantId, projectId as string),
    enabled: Boolean(projectId && tenantId),
    refetchInterval: (query) =>
      (query.state.data?.audits ?? []).some((a) => AUDIT_IN_FLIGHT.includes(a.status))
        ? AUDIT_POLL_MS
        : false,
    refetchIntervalInBackground: false,
  });
}

// Nothing is written. What this returns is what the person confirms against — see
// `preview_registration` on the platform for why that step exists at all.
export function usePreviewA11yRoutes(projectId: string | undefined) {
  const tenantId = useTenantId();
  return useMutation({
    mutationFn: (routesText: string) =>
      api.a11yRoutesPreview(tenantId, projectId as string, routesText),
  });
}

export function useRegisterA11yRoutes(projectId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { routesText: string; replace: boolean }) =>
      api.a11yRoutesRegister(tenantId, projectId as string, {
        routes_text: vars.routesText,
        replace: vars.replace,
      }),
    // The response IS the new list, so it is written straight into the cache. `a11y-audits` is
    // invalidated too because the scope warning on the run strip is derived from both.
    onSuccess: (next) => {
      qc.setQueryData(["a11y-routes", projectId], next);
      qc.invalidateQueries({ queryKey: ["a11y-audits", projectId] });
    },
  });
}

export function useUpdateA11yRoute(projectId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { routeId: string; fields: Record<string, unknown> }) =>
      api.a11yRouteUpdate(tenantId, projectId as string, vars.routeId, vars.fields),
    // Refetched rather than patched into the cache: an edit can change what a page's history
    // means for the scope warning, and that is computed server-side from both lists.
    onSuccess: () => qc.invalidateQueries({ queryKey: ["a11y-routes", projectId] }),
  });
}

export function useDeleteA11yRoute(projectId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (routeId: string) =>
      api.a11yRouteDelete(tenantId, projectId as string, routeId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["a11y-routes", projectId] }),
  });
}

export function useStartA11yAudit(projectId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { base_url?: string }) =>
      api.a11yAuditStart(tenantId, projectId as string, vars),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["a11y-audits", projectId] });
      qc.invalidateQueries({ queryKey: ["a11y-routes", projectId] });
    },
  });
}

/** Ask again about what nothing looked at (task R1). Invalidates the audit list, so the row's
 *  badge flips to "Checking what was found" and the running panel takes over from there. */
export function useRejudgeA11yAudit(projectId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (auditId: string) =>
      api.a11yAuditRejudge(tenantId, projectId as string, auditId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["a11y-audits", projectId] });
      // The queue holds the very items this re-asks about, so it must not go on showing them
      // as waiting on a person while the machine is having another go.
      qc.invalidateQueries({ queryKey: ["a11y-review", projectId] });
    },
  });
}

/** Finish an audit whose judging pass was parked past its deadline (9.26.F).
 *
 *  **The same call the run-recovery console's "Take over" makes**, deliberately — one recovery
 *  path, not two implementations of one. What differs is only where it is offered: a person
 *  auditing their own website has no reason to have ever opened a run console, and until this
 *  the parked pass was reachable from nowhere else. The re-claim lease will not offer a parked
 *  run back to a returning machine, so without this the audit was stuck for good.
 *
 *  Invalidates the audit list, because ending the run is what lets the closing path publish the
 *  report and baseline and move the audit to `complete` — after which the row grows its "Check
 *  the rest" button for everything the pass never reached.
 */
export function useFinishStalledA11yAudit(projectId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => api.takeOverRun(tenantId, runId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["a11y-audits", projectId] });
      // Everything the pass never answered is filed for a person as it closes, so the queue is
      // about to change too.
      qc.invalidateQueries({ queryKey: ["a11y-review", projectId] });
      qc.invalidateQueries({ queryKey: ["artifacts", projectId] });
    },
  });
}

// ── Conformance statement (S-37, QA-24) ──────────────────────────────────────────────────

export function useA11yConformance(projectId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["a11y-conformance", projectId],
    queryFn: () => api.a11yConformance(tenantId, projectId as string),
    enabled: Boolean(projectId && tenantId),
  });
}

export function useSaveA11yConformance(projectId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      scope?: string;
      body?: string;
      verdicts?: Record<string, { level: string; note?: string }>;
    }) => api.a11yConformanceSave(tenantId, projectId as string, vars),
    // The response IS the new state (signature cleared and all), so it is written straight into
    // the cache rather than refetched — a refetch would briefly show the pre-edit signature.
    onSuccess: (next) => qc.setQueryData(["a11y-conformance", projectId], next),
  });
}

export function useSignA11yConformance(projectId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { name: string; acknowledged: boolean }) =>
      api.a11yConformanceSign(tenantId, projectId as string, vars),
    onSuccess: (next) => {
      qc.setQueryData(["a11y-conformance", projectId], next);
      // Signing registers (and approves) the conformance artifact.
      qc.invalidateQueries({ queryKey: ["artifacts", projectId] });
    },
  });
}

export function useExportA11yConformance(projectId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.a11yConformanceExport(tenantId, projectId as string),
    onSuccess: () => {
      // The statement is Published now: the Export box says when, and Artifacts shows it.
      qc.invalidateQueries({ queryKey: ["a11y-conformance", projectId] });
      qc.invalidateQueries({ queryKey: ["artifacts", projectId] });
    },
  });
}

// ── keyboard journeys (G6c) ─────────────────────────────────────────────────
//
// A walk takes minutes in a real browser, so the list refreshes on a slow interval while one is
// in flight. The journey's own work item is a hidden carrier, so this panel is the ONLY place a
// person can watch it happen — a list that went stale would look like a run that never finished.
const WALKING_POLL_MS = 15 * 1000;

export function useA11yJourneys(projectId: string | undefined) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["a11y-journeys", projectId],
    queryFn: () => api.a11yJourneys(tenantId, projectId as string),
    enabled: Boolean(projectId && tenantId),
    refetchInterval: (query) =>
      // `queued` too — a journey waiting for a machine is exactly the one a person is watching,
      // and a list that stopped polling there would never show it start.
      query.state.data?.journeys.some((j) => j.status === "walking" || j.status === "queued")
        ? WALKING_POLL_MS
        : false,
    refetchIntervalInBackground: false,
  });
}

export function useStartA11yJourneys(projectId: string | undefined) {
  const tenantId = useTenantId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { base_url: string; test_refs?: string[] }) =>
      api.a11yJourneyStart(tenantId, projectId as string, vars),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["a11y-journeys", projectId] });
      // A journey's findings land in the same queue as everything else.
      qc.invalidateQueries({ queryKey: ["a11y-review", projectId] });
    },
  });
}
