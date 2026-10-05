// "My machine dropped and nothing told me." Before this, you found out by noticing: the pill was
// wrong, the run console showed a running spinner for a phase nobody had claimed, and nothing
// anywhere said to reconnect. The status pill now tells the truth, but a pill in the corner is
// not how somebody mid-task learns their work has stopped.
//
// Shown only when BOTH hold — the machine is gone AND a phase is actually sitting unclaimed. The
// second condition is the point: a laptop that sleeps overnight with nothing pending has caused
// no problem, and a banner that appeared every time it did would be dismissed unread by the week
// it mattered.
import { useState } from "react";
import { Link } from "react-router-dom";

import { Banner, Button } from "../../components/ui";
import { useRuns } from "../lifecycle/hooks";
import { phaseLabel } from "../lifecycle/phases";
import { runLink } from "../../links";
import { dispatchUnclaimed } from "../../types";

const DISMISS_KEY = "companion-drop-dismissed";

function wasDismissed(): boolean {
  // sessionStorage throws in a private window and comes back empty with site data blocked, so
  // every read and write is guarded and the banner simply shows when it cannot remember.
  try {
    return sessionStorage.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Mount this ONLY while the companion is offline.
 *
 * Not a guard inside the component — a deliberate contract, because it calls `useRuns`, which
 * polls every 4 seconds. Mounted unconditionally in the always-on app shell that would put a 4s
 * poll on every screen in the product, which is the background churn S.No 12 asked us to reduce
 * and the 15s companion poll was slowed down for. Rendered only while something is wrong, the
 * poll exists for the minutes it is useful and not otherwise.
 */
export function CompanionDropBanner(
  { projectId, everConnected }: { projectId: string | undefined; everConnected: boolean },
) {
  const [dismissed, setDismissed] = useState(wasDismissed);
  const runs = useRuns({ project: projectId });

  // A dispatch still "pending" is one no machine ever claimed. Read from `inputs.dispatch`
  // rather than the run status on purpose: dispatching sets the run to RUNNING, so by status
  // alone a stranded run is indistinguishable from one being actively worked on.
  const waiting = (runs.data ?? []).filter((r) => dispatchUnclaimed(r.inputs));
  if (dismissed || waiting.length === 0) return null;

  const first = waiting[0];
  // The phase, never the work item's id. `agent_phase` is already a readable label from the
  // catalog; `work_item` is a UUID, and a client's screen never shows one.
  const what = first.agent_phase ? phaseLabel(first.agent_phase) : "A phase";

  // Dismiss lives in the banner's own content rather than as a new `Banner` prop: `Banner` is
  // used on dozens of screens, and growing its API for one caller is a wider change than this
  // fix needs.
  const dismiss = () => {
    setDismissed(true);
    try {
      sessionStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // Dismissing still works for this render; it just won't be remembered.
    }
  };

  return (
    <Banner variant="danger" title="Your machine stopped responding">
      {waiting.length === 1
        ? `${what} hasn't started, and it won't until your machine is back.`
        : `${waiting.length} phases haven't started, and they won't until your machine is back.`}{" "}
      <Link to="/connect">{everConnected ? "Reconnect your machine" : "Connect your machine"} ↗</Link>
      {waiting.length === 1 && (
        <>
          {" · "}
          <Link to={runLink(first.id)}>Open the run ↗</Link>
        </>
      )}
      <div style={{ marginTop: "var(--space-2)" }}>
        <Button variant="ghost" size="sm" onClick={dismiss}>
          Dismiss
        </Button>
      </div>
    </Banner>
  );
}
