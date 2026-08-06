// How an artifact's status is shown, in one place — the registry list and the preview screen
// both read from here so a status cannot mean one thing on one screen and another elsewhere.
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

const STATUS_BADGES: Record<string, { variant: BadgeVariant; label: string }> = {
  published: { variant: "done", label: "Published" },
  done: { variant: "done", label: "Published" },
  approved: { variant: "navy", label: "Approved" },
  pending_gate: { variant: "gate", label: "Pending gate" },
  gate: { variant: "gate", label: "Pending gate" },
  staged: { variant: "gate", label: "Staged" },
  // Neutral, not an alarm colour: superseded is the normal outcome of a review round, not a
  // failure. It means "a later round replaced this" — the body stays readable, and the revision's
  // manifest cites it by id.
  superseded: { variant: "neutral", label: "Superseded" },
  draft: { variant: "info-hue", label: "Draft" },
};

export function artifactStatusBadge(status: string) {
  const b = STATUS_BADGES[status];
  return <Badge variant={b?.variant ?? "info-hue"}>{b?.label ?? statusLabel(status)}</Badge>;
}
