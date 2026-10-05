import { Link, useParams } from "react-router-dom";

import { Banner, Breadcrumb, Button, Card, CardBody, Panel, Spinner } from "../../components/ui";
import { useWorkItem, useWorkItems } from "./hooks";
import { statusLabel } from "./phases";

// S-23 view states: pushed-to-jira · internal-only.
export type TaskBreakdownView = "pushed" | "internal";

export function TaskBreakdown({ forceView }: { forceView?: TaskBreakdownView }) {
  if (forceView) return <TaskBreakdownGallery view={forceView} />;
  return <TaskBreakdownLive />;
}

// ── Live: the real epic's fanned-out child work items ───────────────────────
function TaskBreakdownLive() {
  const { id } = useParams();
  const epic = useWorkItem(id);
  const children = useWorkItems(epic.data?.project, { parent: id });

  if (epic.isLoading || children.isLoading) {
    return (
      <div className="canvas-pad" style={{ maxWidth: "880px" }}>
        <Panel>
          <Spinner /> Loading task breakdown…
        </Panel>
      </div>
    );
  }

  if (!epic.data || !id) {
    return (
      <div className="canvas-pad" style={{ maxWidth: "880px" }}>
        <Panel>
          <Banner variant="danger" title="Work item not found">
            This work item doesn't exist or you don't have access to it.
          </Banner>
        </Panel>
      </div>
    );
  }

  const tasks = children.data ?? [];
  const epicLabel = epic.data.title || epic.data.id.slice(0, 8);
  const view: TaskBreakdownView = tasks.some((t) => t.external_ref?.sor === "jira") ? "pushed" : "internal";

  return (
    <div className="canvas-pad" style={{ maxWidth: "880px" }}>
      <Breadcrumb items={[{ label: epicLabel, href: `/work-items/${id}` }, "Task Breakdown"]} />

      <Card>
        <CardBody style={{ textAlign: "center", padding: "var(--space-7) var(--space-6)" }}>
          <div className="tile__num" style={{ color: "var(--success)" }}>
            {tasks.length}
          </div>
          <h1 className="t-h1" style={{ marginTop: "var(--space-2)" }}>
            {tasks.length === 0 ? "No task work items yet" : `${tasks.length} task work item${tasks.length === 1 ? "" : "s"}`}
          </h1>
          {tasks.length > 0 && (
            <p className="t-body u-muted" style={{ marginTop: "var(--space-2)" }}>
              The approved plan for <strong>{epicLabel}</strong> fanned out into the build tier.
              Each task starts in the Implementation column under this epic.
            </p>
          )}
          {tasks.length > 0 && (
            <div style={{ marginTop: "var(--space-4)", textAlign: "left" }}>
              {view === "pushed" ? (
                <Banner variant="success" title="Pushed to Jira backlog">
                  These tasks are deep-linked to their Jira issues below.
                </Banner>
              ) : (
                <Banner variant="info" title="Saved in the platform">
                  Task tracker isn't connected, so these live in the platform only. Connect Jira to
                  push them to a backlog.
                </Banner>
              )}
            </div>
          )}
          <div
            className="gate-panel__actions"
            style={{ justifyContent: "center", marginTop: "var(--space-4)" }}
          >
            <Link to="/work-items" className="btn btn--primary">
              Go to board
            </Link>
            {view === "pushed" ? (
              <Link to={`/work-items/${id}`} className="btn btn--secondary">
                Back to epic
              </Link>
            ) : (
              <Link to="/integrations" className="btn btn--secondary">
                Connect a task tracker
              </Link>
            )}
          </div>
        </CardBody>
      </Card>

      {tasks.length > 0 && (
        <div style={{ marginTop: "var(--space-5)" }}>
          <Panel flush title="Task work items">
            {tasks.map((task) => (
              <div className="artifact-row" key={task.id}>
                <div className="artifact-row__main">
                  <div className="artifact-row__title">{task.title || task.key || task.id.slice(0, 8)}</div>
                  {/* The meta line printed the id outright, next to a title that was already
                      there. The task's KEY ("WI-265") is the reference a person uses, and when
                      there isn't one the status alone is more use than an id fragment. */}
                  <div className="artifact-row__meta">
                    {[task.key, statusLabel(task.state)].filter(Boolean).join(" · ")}
                  </div>
                </div>
                {task.external_ref?.sor === "jira" && task.external_ref.key && (
                  <span className="sor-chip sor-chip--jira">
                    <span className="sor-chip__glyph">J</span>
                    {task.external_ref.key}
                  </span>
                )}
                <Link to={`/work-items/${task.id}`} className="btn btn--ghost btn--sm">
                  Open
                </Link>
              </div>
            ))}
          </Panel>
        </div>
      )}
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
const TASKS = [
  { title: "Verify Stripe signing secret", id: "WI-540", ref: "STR-15" },
  { title: "Persist webhook event log", id: "WI-541", ref: "STR-16" },
  { title: "Add idempotency key handling", id: "WI-542", ref: "STR-17" },
  { title: "Handle charge.dispute.created", id: "WI-543", ref: "STR-18" },
  { title: "Backfill reconciliation job", id: "WI-544", ref: "STR-19" },
  { title: "Wire webhook metrics & alerts", id: "WI-545", ref: "STR-20" },
];

function TaskBreakdownGallery({ view }: { view: TaskBreakdownView }) {
  return (
    <div className="canvas-pad" style={{ maxWidth: "880px" }}>
      <Breadcrumb items={[{ label: "WI-492", href: "/work-items/WI-492" }, "Task Breakdown"]} />

      <Card>
        <CardBody style={{ textAlign: "center", padding: "var(--space-7) var(--space-6)" }}>
          <div className="tile__num" style={{ color: "var(--success)" }}>
            6
          </div>
          <h1 className="t-h1" style={{ marginTop: "var(--space-2)" }}>
            Created 6 task work items
          </h1>
          {view === "pushed" && (
            <p className="t-body u-muted" style={{ marginTop: "var(--space-2)" }}>
              The approved plan for <strong>WI-492 Stripe Webhook Integration</strong> fanned out into
              the build tier. Each task starts in the Implementation column under this epic.
            </p>
          )}
          <div style={{ marginTop: "var(--space-4)", textAlign: "left" }}>
            {view === "pushed" ? (
              <Banner variant="success" title="Pushed to Jira backlog">
                Created as STR-15…STR-20 under epic STR-14 — deep-linked below.
              </Banner>
            ) : (
              <Banner variant="info" title="Saved in the platform">
                Task tracker isn't connected, so these live in the platform only. Connect Jira to push
                them to a backlog.
              </Banner>
            )}
          </div>
          <div
            className="gate-panel__actions"
            style={{ justifyContent: "center", marginTop: "var(--space-4)" }}
          >
            <Link to="/work-items" className="btn btn--primary">
              Go to board
            </Link>
            {view === "pushed" ? (
              <Link to="/work-items/WI-492" className="btn btn--secondary">
                Back to epic
              </Link>
            ) : (
              <Link to="/integrations" className="btn btn--secondary">
                Connect a task tracker
              </Link>
            )}
          </div>
        </CardBody>
      </Card>

      {view === "pushed" && (
        <div style={{ marginTop: "var(--space-5)" }}>
          <Panel flush title="New task work items">
            {TASKS.map((task) => (
              <div className="artifact-row" key={task.id}>
                <div className="artifact-row__main">
                  <div className="artifact-row__title">{task.title}</div>
                  <div className="artifact-row__meta">{task.id} · Implementation</div>
                </div>
                <span className="sor-chip sor-chip--jira">
                  <span className="sor-chip__glyph">J</span>
                  {task.ref}
                </span>
                <Button variant="ghost" size="sm">
                  Open
                </Button>
              </div>
            ))}
          </Panel>
        </div>
      )}
    </div>
  );
}
