import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { useRunners, useUsers } from "./hooks";

// Shown on setup destination screens (connect machine, invite team, integrations)
// so a new user can always get back to the Get Started checklist — the hub of the
// first-run flow. Hidden once the three required steps are done (same completion
// logic as SetupChecklist), so it never nags established users.
export function SetupReturnLink() {
  const { currentUser } = useAuth();
  const runners = useRunners();
  const users = useUsers();

  const hasProject = Boolean(currentUser?.memberships.length);
  const hasMachine = Boolean(runners.data?.some((r) => r.online || r.last_seen));
  const hasTeam = (users.data?.length ?? 0) > 1;
  const requiredDone = hasProject && hasMachine && hasTeam;
  if (requiredDone) return null;

  return (
    <Link to="/setup" className="btn btn--ghost btn--sm">
      ← Back to Get started
    </Link>
  );
}
