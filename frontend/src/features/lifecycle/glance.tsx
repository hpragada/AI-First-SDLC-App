// The "At a glance" card's counts, shared by the epic, task and defect screens so the three
// cannot drift apart again.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

/** A count that is a link only when there is something on the other end of it.
 *
 *  The link was added because an inert number told you there were four documents and left you
 *  to find them in the registry by hand. At ZERO it does the opposite: it invites a click that
 *  lands on "Nothing matched this filter", which reads like a failure when the honest answer is
 *  simply that this work item has not produced anything yet. */
export function countCell(count: number, to: string): ReactNode {
  return count > 0 ? <Link to={to}>{count}</Link> : <span className="u-muted">0</span>;
}
