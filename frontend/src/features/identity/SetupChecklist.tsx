import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, Button, Card, CardBody } from "../../components/ui";
import { useRunners, useUsers } from "./hooks";
import { andList, roleLabel } from "./roles";

// S-05 view states: all-incomplete · partial (2 of 4) · all-complete (dismiss).
export type SetupView = "all-incomplete" | "partial" | "complete";

interface Step {
  id: string;
  title: React.ReactNode;
  desc?: React.ReactNode;
  done: boolean;
  action: React.ReactNode;
}

function StepCard({ step, active }: { step: Step; active: boolean }) {
  const numClass = step.done
    ? "vstep__num vstep__num--done"
    : active
      ? "vstep__num vstep__num--active"
      : "vstep__num";
  return (
    <Card>
      <CardBody style={{ display: "flex", alignItems: "center", gap: "var(--space-4)" }}>
        <span className={numClass}>{step.done ? "✓" : step.id}</span>
        <div style={{ flex: "1 1 auto" }}>
          <div className="t-h3">{step.title}</div>
          {step.desc && <div className="t-sm u-muted">{step.desc}</div>}
        </div>
        {step.done ? (
          <Badge variant="done">Done</Badge>
        ) : (
          step.action
        )}
      </CardBody>
    </Card>
  );
}

export function SetupChecklist({ forceView }: { forceView?: SetupView }) {
  const { currentUser, isAdmin } = useAuth();
  // 2026-10-09 (team-approved mockup 6): a teammate who joined by invite was shown the
  // workspace owner's four steps — two of them admin-only, one ending at "Admin access
  // needed". They get their own page. The gallery (forceView) keeps the owner's.
  if (!forceView && currentUser && !isAdmin) return <TeammateSetup />;
  return <OwnerSetup forceView={forceView} />;
}

function TeammateSetup() {
  const { currentUser, selectedProject } = useAuth();
  const runners = useRunners();
  const hasMachine = Boolean(runners.data?.some((r) => r.online || r.last_seen));
  const steps: Step[] = [
    { id: "1", title: "Join the workspace", done: true, action: null },
    {
      id: "2",
      title: "Connect your machine",
      desc: hasMachine
        ? `${runners.data?.[0]?.machine || "Machine"} connected.`
        : "Phases you start run on your computer.",
      done: hasMachine,
      action: (
        <Link to="/connect" className="btn btn--primary">
          Connect
        </Link>
      ),
    },
  ];
  const project = selectedProject ?? currentUser?.memberships[0];
  // Every role held on this project (memberships are one row per role), in the order granted.
  const roles = [
    ...new Set(
      (currentUser?.memberships ?? [])
        .filter((m) => m.project_id === project?.project_id)
        .map((m) => roleLabel(m.role)),
    ),
  ];
  return (
    <div className="canvas-pad" style={{ maxWidth: "880px" }}>
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-display">Welcome to {project?.project_name ?? currentUser?.tenant.name}</h1>
          <p className="page-head__sub">
            {roles.length ? `You've joined as ${andList(roles)}. ` : ""}
            {hasMachine ? "You're ready to run phases." : "One step left."}
          </p>
        </div>
      </div>
      <div className="u-stack">
        {steps.map((step) => (
          <StepCard key={step.id} step={step} active={!step.done} />
        ))}
      </div>
      <p className="t-sm u-muted" style={{ marginTop: "var(--space-3)" }}>
        Inviting people and integrations are set up by your workspace admin.
      </p>
    </div>
  );
}

function OwnerSetup({ forceView }: { forceView?: SetupView }) {
  const { currentUser } = useAuth();
  const runners = useRunners();
  const users = useUsers();
  const [dismissed, setDismissed] = useState(false);

  const steps = useMemo<Step[]>(() => {
    const hasProject = Boolean(currentUser?.memberships.length);
    const hasMachine = Boolean(runners.data?.some((r) => r.online || r.last_seen));
    const hasTeam = (users.data?.length ?? 0) > 1;
    return [
      {
        id: "1",
        title: "Create your first project",
        desc: hasProject
          ? `${currentUser?.memberships[0]?.project_name ?? "Project"} created.`
          : "Greenfield or brownfield — this is where work items live.",
        done: hasProject,
        action: (
          <Link to="/projects/new" className="btn btn--primary">
            Create project
          </Link>
        ),
      },
      {
        id: "2",
        title: "Connect your machine",
        desc: hasMachine
          ? `${runners.data?.[0]?.machine ?? "Machine"} connected.`
          : "Phases run on your computer using your Claude Code subscription.",
        done: hasMachine,
        action: (
          <Link to="/connect" className="btn btn--secondary">
            Connect
          </Link>
        ),
      },
      {
        id: "3",
        title: "Invite your team & assign roles",
        desc: "So gates have someone to decide them.",
        done: hasTeam,
        action: (
          <Link to="/admin/users" className="btn btn--secondary">
            Invite team
          </Link>
        ),
      },
      {
        id: "4",
        title: (
          <>
            Connect integrations <span className="t-xs u-muted">(optional)</span>
          </>
        ),
        desc: "Confluence, Jira, Figma, GitHub, Xray.",
        done: false,
        action: (
          <Link to="/integrations" className="btn btn--secondary">
            Connect
          </Link>
        ),
      },
    ];
  }, [currentUser, runners.data, users.data]);

  const requiredDone = steps.slice(0, 3).every((s) => s.done);
  const doneCount = steps.filter((s) => s.done).length;
  const view: SetupView =
    forceView ??
    (requiredDone ? "complete" : doneCount > 0 ? "partial" : "all-incomplete");
  const firstIncomplete = steps.find((s) => !s.done)?.id;

  if (view === "complete") {
    if (dismissed) return null;
    return (
      <div className="canvas-pad" style={{ maxWidth: "880px" }}>
        <div className="card--attention">
          <CardBody style={{ display: "flex", alignItems: "center", gap: "var(--space-4)" }}>
            <span className="vstep__num vstep__num--done">✓</span>
            <div style={{ flex: "1 1 auto" }}>
              <div className="t-h3">Setup complete — you're ready to run phases</div>
              <div className="t-sm u-body">
                All four steps done. This checklist won't show again.
              </div>
            </div>
            <Link to="/" className="btn btn--primary">
              Go to dashboard
            </Link>
            <Button variant="ghost" onClick={() => setDismissed(true)}>
              Dismiss
            </Button>
          </CardBody>
        </div>
      </div>
    );
  }

  return (
    <div className="canvas-pad" style={{ maxWidth: "880px" }}>
      {view === "all-incomplete" ? (
        <div className="page-head">
          <div className="page-head__titles">
            <h1 className="t-display">Welcome to {currentUser?.tenant.name ?? "Acme Corp"} 👋</h1>
            <p className="page-head__sub">
              Let's get your workspace ready. Four quick steps and you can run your first phase.
            </p>
          </div>
        </div>
      ) : (
        <div className="u-row" style={{ marginBottom: "var(--space-4)" }}>
          <h2 className="t-h2">Setup · {doneCount} of 4 complete</h2>
          <span className="u-spacer" />
          <span className="save-state save-state--saving">Almost there</span>
        </div>
      )}
      <div className="u-stack">
        {steps.map((step) => (
          <StepCard key={step.id} step={step} active={step.id === firstIncomplete} />
        ))}
      </div>
    </div>
  );
}
