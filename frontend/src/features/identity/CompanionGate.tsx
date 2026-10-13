// Starting work needs a machine to run it on. Three screens offer a trigger — the task's
// Implementation, the defect's Fix, and a test case's Generate script — and none of them used to
// check whether one was there. Phases & Runs did, so the same click was refused on one screen and
// accepted on three, and the three dispatched into a run nobody would ever claim: it flips to
// RUNNING with `dispatch.status` still "pending" and looks live until the two-hour takeover.
//
// One hook and one sentence here rather than three copies, so the reason a button is greyed reads
// the same wherever somebody meets it, and so there is one place to change it.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useCompanionStatus } from "./hooks";

export interface CompanionGate {
  /** Whether to disable the trigger. */
  blocked: boolean;
  /** The reason, ready to render under the button. `null` when there is nothing to say. */
  note: ReactNode | null;
}

export function useCompanionGate(projectId: string | undefined): CompanionGate {
  const companion = useCompanionStatus(projectId);
  // Only `offline` blocks. `checking` (one or two missed heartbeats) and `unknown` (the first
  // load, before any answer has arrived) deliberately do not: a button that disables itself for
  // half a second on every page load, or whenever a laptop gets briefly busy, costs more than
  // the stranded run it would prevent — and the server-side guard on the trigger endpoint is
  // what catches a screen whose status has gone stale.
  const blocked = companion.state === "offline" && Boolean(projectId);
  if (!blocked) return { blocked: false, note: null };
  return {
    blocked: true,
    note: (
      <span className="field__help">
        {companion.everConnected
          ? "Your machine isn't connected, so this can't start yet."
          : "You haven't connected a machine yet, so this can't start."}{" "}
        <Link to="/connect">
          {companion.everConnected ? "Reconnect your machine" : "Connect your machine"} ↗
        </Link>
      </span>
    ),
  };
}
