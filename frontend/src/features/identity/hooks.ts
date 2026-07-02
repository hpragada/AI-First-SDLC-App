// Query/mutation hooks for the identity & onboarding group (S-01..S-08).
// All server reads/writes go through TanStack Query over the typed api client.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api";
import type {
  AcceptInviteRequest,
  ResetRequest,
  SignupRequest,
} from "../../types";

// ── Public auth (no session yet) ────────────────────────────────────────────
export function useSignup() {
  return useMutation({ mutationFn: (body: SignupRequest) => api.signup(body) });
}

export function useAcceptInvitation() {
  return useMutation({ mutationFn: (body: AcceptInviteRequest) => api.acceptInvitation(body) });
}

export function useRequestReset() {
  return useMutation({ mutationFn: (email: string) => api.requestReset(email) });
}

export function useResetPassword() {
  return useMutation({ mutationFn: (body: ResetRequest) => api.resetPassword(body) });
}

// ── Companion enrollments (S-05 tick, S-06 connect-machine) ─────────────────
// Poll while the connect screen waits for the first check-in (gallery: live status).
export function useRunners(poll = false) {
  return useQuery({
    queryKey: ["runners"],
    queryFn: api.listRunners,
    refetchInterval: poll ? 4000 : false,
  });
}

export function useCreateRunner() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { project_id: string; label?: string }) => api.createRunner(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runners"] }),
  });
}

export function useRevokeRunner() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.revokeRunner(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runners"] }),
  });
}

// ── Admin: users, invitations, memberships, role coverage (S-07/S-08) ───────
export function useUsers() {
  return useQuery({ queryKey: ["users"], queryFn: api.listUsers });
}

export function useInvitations() {
  return useQuery({ queryKey: ["invitations"], queryFn: api.listInvitations });
}

export function useCreateInvitation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.createInvitation,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["invitations"] });
    },
  });
}

export function useResendInvitation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.resendInvitation(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invitations"] }),
  });
}

export function useRevokeInvitation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.revokeInvitation(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["invitations"] });
    },
  });
}

export function useRoleCoverage(projectId: string | undefined) {
  return useQuery({
    queryKey: ["role-coverage", projectId],
    queryFn: () => api.roleCoverage(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function useSetMembership(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { user_id: string; role: string }) =>
      api.createMembership(projectId as string, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["role-coverage", projectId] });
    },
  });
}

export function useRevokeMembership(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (membershipId: string) => api.deleteMembership(projectId as string, membershipId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["role-coverage", projectId] });
    },
  });
}

export function useSetTenantAdmin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, isTenantAdmin }: { userId: string; isTenantAdmin: boolean }) =>
      api.setTenantAdmin(userId, isTenantAdmin),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

// Password-strength estimate (0–4) — drives the <Strength> bars on signup/invite/reset.
export function passwordStrength(value: string): 0 | 1 | 2 | 3 | 4 {
  if (!value) return 0;
  let score = 0;
  if (value.length >= 8) score++;
  if (value.length >= 12) score++;
  if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score++;
  if (/\d/.test(value)) score++;
  if (/[^A-Za-z0-9]/.test(value)) score++;
  return Math.min(4, score) as 0 | 1 | 2 | 3 | 4;
}
