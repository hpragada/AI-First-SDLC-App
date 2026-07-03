import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { useRunners } from "./hooks";

// Shown on setup destination screens (connect machine, invite team, integrations)
// so a new user can always get back to the Get Started checklist — the hub of the
// first-run flow. Bugs.xlsx row 32: it used to also require an accepted teammate, so a
// solo developer who finished setup still saw the link forever. Per team decision the
// link now hides once the user has a project and a connected machine (inviting a team
// stays optional), so it no longer nags an established user.
export function SetupReturnLink() {
  const { currentUser } = useAuth();
  const runners = useRunners();

  const hasProject = Boolean(currentUser?.memberships.length);
  const hasMachine = Boolean(runners.data?.some((r) => r.online || r.last_seen));
  if (hasProject && hasMachine) return null;

  return (
    <Link to="/setup" className="btn btn--ghost btn--sm">
      ← Back to Get started
    </Link>
  );
}
