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
  return useMutation({
    mutationFn: () => api.a11yConformanceExport(tenantId, projectId as string),
  });
}
