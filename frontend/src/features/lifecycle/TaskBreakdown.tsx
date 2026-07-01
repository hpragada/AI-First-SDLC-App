import { Banner, Breadcrumb, Button, Card, CardBody, Panel } from "../../components/ui";

// S-23 view states: pushed-to-jira · internal-only.
export type TaskBreakdownView = "pushed" | "internal";

const TASKS = [
  { title: "Verify Stripe signing secret", id: "WI-540", ref: "STR-15" },
  { title: "Persist webhook event log", id: "WI-541", ref: "STR-16" },
  { title: "Add idempotency key handling", id: "WI-542", ref: "STR-17" },
  { title: "Handle charge.dispute.created", id: "WI-543", ref: "STR-18" },
  { title: "Backfill reconciliation job", id: "WI-544", ref: "STR-19" },
  { title: "Wire webhook metrics & alerts", id: "WI-545", ref: "STR-20" },
];

export function TaskBreakdown({ forceView }: { forceView?: TaskBreakdownView }) {
  const view: TaskBreakdownView = forceView ?? "pushed";

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
            <a href="/work-items" className="btn btn--primary">
              Go to board
            </a>
            {view === "pushed" ? (
              <a href="/work-items/WI-492" className="btn btn--secondary">
                Back to epic
              </a>
            ) : (
              <a href="/integrations" className="btn btn--secondary">
                Connect a task tracker
              </a>
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
