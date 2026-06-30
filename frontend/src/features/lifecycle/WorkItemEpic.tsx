import { useParams } from "react-router-dom";

import {
  Badge,
  Breadcrumb,
  Button,
  Card,
  CardBody,
  Console,
  Kv,
  LifecycleRail,
  Panel,
} from "../../components/ui";
import { useDecideApproval } from "./hooks";

// S-15 view states: gate-pending (default) · running+needs-answer · all-complete.
export type EpicView = "gate-pending" | "needs-answer" | "complete";

const GATE_PENDING_NODES = [
  { label: "Ideation", state: "Approved", tone: "done" as const, mark: "✓" },
  { label: "Requirements", state: "Approved", tone: "done" as const, mark: "✓" },
  { label: "PRD", state: "Approved", tone: "done" as const, mark: "✓" },
  { label: "Architecture", state: "Gate Pending", tone: "current" as const, mark: "●" },
  { label: "UX Design", state: "Upcoming", tone: "upcoming" as const, mark: 5 },
  { label: "Task Breakdown", state: "Upcoming", tone: "upcoming" as const, mark: 6 },
];

const NEEDS_ANSWER_NODES = [
  { label: "Ideation", state: "Approved", tone: "done" as const, mark: "✓" },
  { label: "Requirements", state: "Approved", tone: "done" as const, mark: "✓" },
  { label: "PRD", state: "Needs answer", tone: "needs" as const, mark: "?" },
  { label: "Architecture", state: "Upcoming", tone: "upcoming" as const, mark: 4 },
  { label: "UX Design", state: "Upcoming", tone: "upcoming" as const, mark: 5 },
  { label: "Task Breakdown", state: "Upcoming", tone: "upcoming" as const, mark: 6 },
];

const COMPLETE_NODES = [
  { label: "Ideation", state: "Approved", tone: "done" as const, mark: "✓" },
  { label: "Requirements", state: "Approved", tone: "done" as const, mark: "✓" },
  { label: "PRD", state: "Approved", tone: "done" as const, mark: "✓" },
  { label: "Architecture", state: "Approved", tone: "done" as const, mark: "✓" },
  { label: "UX Design", state: "Approved", tone: "done" as const, mark: "✓" },
  { label: "Task Breakdown", state: "6 tasks", tone: "done" as const, mark: "✓" },
];

export function WorkItemEpic({ forceView }: { forceView?: EpicView }) {
  const { id = "WI-492" } = useParams();
  const decideApproval = useDecideApproval();
  const view: EpicView = forceView ?? "gate-pending";

  const nodes =
    view === "complete" ? COMPLETE_NODES : view === "needs-answer" ? NEEDS_ANSWER_NODES : GATE_PENDING_NODES;

  return (
    <div className="canvas-pad">
      <Breadcrumb items={[{ label: "Work Items", href: "/work-items" }, id]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">⚡ Stripe Webhook Integration</h1>
          <div className="meta-row" style={{ marginTop: "var(--space-2)" }}>
            <span className="meta-item">
              <span className="chip badge--navy">Epic</span>
            </span>
            <span className="meta-item">
              Created <strong>2d ago</strong>
            </span>
            <span className="meta-item">
              Owner <strong>Sarah Chen</strong>
            </span>
          </div>
        </div>
        <span className="u-row-tight">
          <Button variant="secondary">Edit</Button>
          {view === "gate-pending" && <Button variant="primary">Architecture Gate</Button>}
        </span>
      </div>

      <Panel
        flush
        title="Lifecycle — Plan tier"
        actions={<span className="t-sm u-muted">Epic · one pass through plan phases</span>}
      >
        <LifecycleRail nodes={nodes} />
      </Panel>

      <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
        <div className="u-stack">
          {view !== "complete" && (
            <Panel title="Description & context">
              <p className="t-body">
                Integrate Stripe webhooks to reconcile asynchronous payment events (charge
                succeeded/failed, dispute created) into the gateway's ledger, with signature
                verification and idempotent processing.
              </p>
              <Kv
                rows={[
                  ["Feature stream", "Payments core"],
                  ["NFRs", "PCI-DSS scope, <500ms ack, at-least-once delivery"],
                  ["Constraints", "Stripe + Adyen parity required"],
                ]}
              />
            </Panel>
          )}

          {view === "needs-answer" && (
            <Panel title="Latest AI run" actions={<Badge variant="needs-answer">Needs answer</Badge>}>
              <Console
                lines={[
                  <span key="1">
                    <span className="console__ts">11:03:10</span>Reading approved Requirements…{" "}
                    <span className="ok">[OK]</span>
                  </span>,
                  <span key="2">
                    <span className="console__ts">11:03:44</span>Drafting PRD sections…{" "}
                    <span className="ok">[OK]</span>
                  </span>,
                  <span key="3">
                    <span className="console__ts">11:04:02</span>
                    <span className="warn">[?] Need input: CSV export in v1?</span>
                  </span>,
                ]}
              />
            </Panel>
          )}

          {view === "gate-pending" && (
            <Panel title="Latest AI run" actions={<a href="/runs" className="t-sm">View full run console ↗</a>}>
              <Console
                lines={[
                  <span key="1">
                    <span className="console__ts">10:42:01</span>Compiling requirements…{" "}
                    <span className="ok">[OK]</span>
                  </span>,
                  <span key="2">
                    <span className="console__ts">10:42:30</span>Validating against security rules…{" "}
                    <span className="ok">[OK]</span>
                  </span>,
                  <span key="3">
                    <span className="console__ts">10:42:31</span>
                    <span className="info">Run completed. Awaiting gate.</span>
                  </span>,
                ]}
              />
            </Panel>
          )}

          {view === "complete" && (
            <Panel title="Child tasks" actions={<span className="t-sm u-muted">6 created · pushed to Jira backlog</span>}>
              <div className="artifact-row">
                <div className="artifact-row__main">
                  <div className="artifact-row__title">Verify Stripe signing secret</div>
                  <div className="artifact-row__meta">WI-540 · Implementation</div>
                </div>
                <Button variant="ghost" size="sm">Open</Button>
              </div>
            </Panel>
          )}
        </div>

        <div className="u-stack">
          {view === "gate-pending" && (
            <Card attention>
              <CardBody>
                <span className="gate-panel__role">▲ Architecture gate · required role: architect</span>
                <h3 className="t-h3">Awaiting your decision</h3>
                <p className="t-sm u-body">
                  Approve to publish the System Sequence Diagram to Figma and advance to UX Design.
                </p>
                <div className="gate-panel__actions">
                  <Button variant="primary" onClick={() => decideApproval.mutate({ id, decision: "approved" })}>
                    Approve
                  </Button>
                  <Button variant="secondary" onClick={() => decideApproval.mutate({ id, decision: "rejected" })}>
                    Reject
                  </Button>
                </div>
                <span className="gate-reassure">Decision is logged with your role & comment.</span>
              </CardBody>
            </Card>
          )}
          {view === "needs-answer" && (
            <Card attention>
              <CardBody>
                <span className="gate-panel__role" style={{ color: "var(--accent-purple)" }}>
                  ? Clarification · WI-510
                </span>
                <h3 className="t-h3">1 question awaiting an answer</h3>
                <p className="zero-cost">⏸ Paused — no usage billed while waiting · 6m</p>
                <div className="gate-panel__actions">
                  <a href="/clarifications" className="btn btn--primary">
                    Answer question
                  </a>
                </div>
              </CardBody>
            </Card>
          )}
          <Card>
            <CardBody>
              <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                At a glance
              </h3>
              <Kv
                rows={[
                  ["Phase", view === "complete" ? "Task Breakdown" : "Architecture"],
                  ["Artifacts", "2"],
                  ["Open gates", view === "gate-pending" ? "1" : "0"],
                  ["Clarifications", view === "needs-answer" ? "1" : "0"],
                ]}
              />
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
