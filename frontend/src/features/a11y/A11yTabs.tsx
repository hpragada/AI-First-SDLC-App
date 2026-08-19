// The Accessibility destination is one place with two tabs, not two pages (D-A11Y-94): the
// review queue is the landing page and the conformance statement is its second tab.
//
// Both tabs are ALWAYS present. The conformance tab does not appear only once a statement
// exists, for the same reason the sidebar item does not appear only after the first run — "no
// tab" and "nothing has ever been checked" would look identical, and the honest empty state is
// what tells the two apart.
import { useNavigate } from "react-router-dom";

import { Tabs } from "../../components/ui";
import { useA11yReviewQueue } from "./hooks";
import { useAuth } from "../../auth/AuthContext";

export function A11yTabs({ active }: { active: "audit" | "queue" | "conformance" }) {
  const navigate = useNavigate();
  const { selectedProject } = useAuth();
  const queue = useA11yReviewQueue(selectedProject?.project_id);
  const waiting = queue.data?.queue.length ?? 0;

  return (
    <div style={{ marginBottom: "var(--space-5)" }}>
      <Tabs
        active={active}
        tabs={[
          // First on purpose: on a brownfield project this is where the work starts, and the
          // other two have nothing to show until an audit has run.
          { id: "audit", label: "Pages & audit" },
          { id: "queue", label: waiting ? `Review queue (${waiting})` : "Review queue" },
          { id: "conformance", label: "Conformance statement" },
        ]}
        onSelect={(id) =>
          navigate(
            id === "audit" ? "/a11y/pages" : id === "queue" ? "/a11y" : "/a11y/conformance",
          )
        }
      />
    </div>
  );
}
