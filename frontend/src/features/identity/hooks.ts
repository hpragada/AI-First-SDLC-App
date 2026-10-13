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

export function useInvitationPreview(token: string) {
  return useQuery({
    queryKey: ["invitation-preview", token],
    queryFn: () => api.getInvitationPreview(token),
    enabled: Boolean(token),
    retry: false, // a 409/410 here is a real terminal state, not a transient failure
  });
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
// Bugs.xlsx row 13: the interval is configurable so the always-mounted app shell can poll
// gently (companion pill) while Connect Machine / Phases keep the fast 4s liveness cadence.
// All callers share the ["runners"] query key, so react-query dedupes to one request per tick.
export function useRunners(poll = false, intervalMs: number = 4000) {
  return useQuery({
    queryKey: ["runners"],
    queryFn: api.listRunners,
    refetchInterval: poll ? intervalMs : false,
  });
}

// ── Is MY machine there, for the project I am looking at? ───────────────────
// The one place that question is answered. Every surface that shows companion status reads this
// rather than deriving its own, because the two derivations that existed before both got it
// wrong in the same way: `runners.some(r => r.online)` asks "is ANY machine of mine alive on ANY
// project?", so a companion alive on another project kept the status green while the one running
// your phase was dead — and unlike the other wording defects, that one never corrected itself.
//
// `checking` is the middle state, and it exists to close a 2¼-minute blind window. A companion
// heartbeats every 30s but is only called offline after ONLINE_THRESHOLD (2 min), so a machine
// that died 90 seconds ago still reads `online`. Rather than shorten that threshold — it also
// drives dispatch routing and the claim lease, the S.No 84/111/134 machinery — the amber band
// says "we have stopped hearing from it" at ~40s and leaves the threshold alone.
export type CompanionState = "ready" | "checking" | "offline" | "unknown";

// Two missed heartbeats (30s each) plus a little slack. Below ONLINE_THRESHOLD by design: this
// band lives INSIDE "online", warning before the server gives up rather than instead of it.
const QUIET_AFTER_S = 40;

export interface CompanionStatus {
  state: CompanionState;
  machine: string;
  lastSeen: string | null;
  /** Has a machine ever connected for this project? Distinguishes "dropped" from "never set
   *  up" — the difference between "reconnect it" and "connect one". */
  everConnected: boolean;
}

// `poll` is passed through rather than hardcoded off, and that is load-bearing: the app shell is
// the ONE caller that keeps this query refreshing (gently, every 15s — Bugs S.No 12), and every
// other screen rides its shared ["runners"] cache. A version of this hook that always called
// useRunners() with polling off would have silently stopped liveness updating everywhere the
// moment the shell switched over to it.
export function useCompanionStatus(
  projectId?: string,
  { poll = false, intervalMs }: { poll?: boolean; intervalMs?: number } = {},
): CompanionStatus {
  const runners = useRunners(poll, intervalMs);
  // `?? []` on `projects`, not just on `data`: a row that arrives without the array — an older
  // API, a partial response — must not take down the app shell, which mounts this on every
  // screen. It reads as "this machine serves no project I can match", which is the safe answer.
  const rows = (runners.data ?? []).filter((r) =>
    (r.projects ?? []).some((p) => p.project_id === projectId),
  );
  // Freshest first, so `machine`/`lastSeen` describe the row the state came from. A machine
  // serving several projects is ONE process, so its single liveness is true for all of them;
  // a label-less enrollment (the default from the web app) is already grouped per project
  // server-side. Either way, filtering by project then taking the freshest is correct.
  const best = [...rows].sort((a, b) => Number(b.online) - Number(a.online))[0];
  const everConnected = rows.some((r) => r.last_seen);

  let state: CompanionState;
  if (!projectId || (runners.isLoading && !runners.data)) {
    // Nothing is claimed before the answer arrives. "unknown" never reads as connected on
    // screen, so the status fails safe exactly as the old pill did while loading.
    state = "unknown";
  } else if (!best?.online) {
    state = "offline";
  } else if (typeof best.age_s === "number" && best.age_s >= QUIET_AFTER_S) {
    state = "checking";
  } else {
    state = "ready";
  }

  return {
    state,
    machine: best?.machine ?? "",
    lastSeen: best?.last_seen ?? null,
    everConnected,
  };
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runners"] });
      qc.invalidateQueries({ queryKey: ["last-disconnect"] });
    },
  });
}

export function useLastDisconnect(projectId: string | undefined) {
  return useQuery({
    queryKey: ["last-disconnect", projectId],
    queryFn: () => api.lastDisconnect(projectId as string),
    enabled: Boolean(projectId),
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
/** What the meter under a password box says (team-approved mockup 4, 2026-10-09). Every
 *  screen used to print "Strong" for anything typed, even "abc". Under 8 characters the
 *  server will refuse it, so that is said first; after that the label follows the bars. */
export function passwordHelp(value: string): { tooShort: boolean; text: string } | null {
  if (!value) return null;
  if (value.length < 8) return { tooShort: true, text: "Too short. Use at least 8 characters." };
  const label = ["Weak", "Weak", "Fair", "Good", "Strong"][passwordStrength(value)];
  return { tooShort: false, text: label };
}

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
