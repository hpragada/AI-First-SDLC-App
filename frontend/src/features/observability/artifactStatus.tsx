// How an artifact's status is shown, in one place — the registry list, the preview screen and the
// traceability map all read from here, so a status cannot mean one thing on one screen and
// another elsewhere.
//
// `Artifact.Status` is draft · staged · approved · published · superseded. The registry list used
// to recognise only "published" and "pending_gate" and returned a hardcoded "Draft" for everything
// else, so an APPROVED artifact read as a draft. That went unnoticed until "Request changes"
// started marking a rejected run's drafts `superseded`: the page then showed "Draft" for seven
// artifacts that had just been retired — the one word that means the opposite of what happened.
//
// The fallback humanizes the raw token rather than naming a status, so a status added later
// renders honestly instead of quietly claiming to be a draft.
import { Badge } from "../../components/ui";
import type { BadgeVariant } from "../../components/ui";

export function statusLabel(status: string) {
  return status
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

// Bugs S.No 218. Three keys used to sit here that no artifact can ever have — `pending_gate`,
// `gate` and `done`. `pending_gate` was the remains of a "waiting at the gate" status that was
// designed and never wired up; the other two were guesses at it. Opening a gate now marks the
// run's documents `staged` (`open_gate_core`), the status that already existed for exactly this,
// so the three are deleted rather than left behind looking like coverage.
const STATUS: Record<string, { variant: BadgeVariant; label: string; color: string }> = {
  published: { variant: "done", label: "Published", color: "var(--success)" },
  approved: { variant: "navy", label: "Approved", color: "var(--brand-navy-500)" },
  // A named person has been asked to decide on this document. It was shown as "Staged" — the
  // platform's word, not the client's, and one that says nothing about anyone having to act.
  staged: { variant: "gate", label: "Waiting for approval", color: "var(--warning)" },
  // Neutral, not an alarm colour: superseded is the normal outcome of a review round, not a
  // failure. It means "a later round replaced this" — the body stays readable, and the revision's
  // manifest cites it by id.
  superseded: { variant: "neutral", label: "Superseded", color: "var(--text-faint)" },
  draft: { variant: "info-hue", label: "Draft", color: "var(--info)" },
};

/** Every status, in the order a legend explains them. */
export const ARTIFACT_STATUSES = ["published", "approved", "staged", "draft", "superseded"] as const;

export function artifactStatusLabel(status: string): string {
  return STATUS[status]?.label ?? statusLabel(status);
}

// S.No 318. "Waiting for approval" is true only while an approval can still be given. Once the
// gate has been decided and a document is STILL unpublished, that label invites a decision that
// no longer exists anywhere — which is exactly what six documents said on 2026-10-05 while the
// Gates screen said "No gates need you".
//
// Deliberately not a new artifact status: nothing changed about the row, only what is true
// about it. The status stays `staged`; the label stops making a promise on its behalf.
const APPROVED_NOT_PUBLISHED = "Approved · not published";

function label(status: string, gateDecided?: boolean): string {
  if (gateDecided && status === "staged") return APPROVED_NOT_PUBLISHED;
  return artifactStatusLabel(status);
}

/** The colour a status is drawn in where there is no badge to carry it — the traceability map. */
export function artifactStatusColor(status: string): string {
  return STATUS[status]?.color ?? "var(--info)";
}

export function artifactStatusBadge(status: string, gateDecided?: boolean) {
  const b = STATUS[status];
  // Navy, like `approved` — it HAS been approved. Not the amber of a pending gate, which is
  // the colour of "somebody must act", and nobody can.
  const variant = gateDecided && status === "staged" ? "navy" : (b?.variant ?? "info-hue");
  return <Badge variant={variant}>{label(status, gateDecided)}</Badge>;
}
