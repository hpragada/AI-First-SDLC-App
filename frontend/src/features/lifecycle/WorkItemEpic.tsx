import { useParams } from "react-router-dom";

import {
  Breadcrumb,
  Button,
  Card,
  CardBody,
  Kv,
  LifecycleRail,
  Markdown,
  Panel,
  Spinner,
} from "../../components/ui";
import { railNodeView } from "./railView";
import { gateLabel, phaseLabel, statusLabel, visibleLifecycleNodes } from "./phases";
import { useApprovals, useClarifications, useDecideApproval, useLifecycle, useRuns, useWorkItem } from "./hooks";

function typeLabel(type: string): string {
  return type ? type.charAt(0).toUpperCase() + type.slice(1) : "Item";
}

// S-15 view states: gate-pending (default) · running+needs-answer · all-complete.
export type EpicView = "gate-pending" | "needs-answer" | "complete";

export function WorkItemEpic({ forceView }: { forceView?: EpicView }) {
  if (forceView) return <WorkItemEpicGallery view={forceView} />;
  return <WorkItemEpicLive />;
}

// ── Live: the real epic + its plan-tier lifecycle ───────────────────────────
function WorkItemEpicLive() {
  const { id } = useParams();
  const workItem = useWorkItem(id);
  const lifecycle = useLifecycle(id);
  const approvals = useApprovals({ work_item: id, decision: "pending" });
  const clarifications = useClarifications({ work_item: id, status: "pending" });
  const runs = useRuns({ work_item: id });
  const decideApproval = useDecideApproval();

  if (workItem.isLoading || lifecycle.isLoading) {
    return (
      <div className="canvas-pad">
        <Panel>
          <Spinner /> Loading epic…
        </Panel>
      </div>
    );
  }

  if (!workItem.data || !id) {
    return (
      <div className="canvas-pad">
        <Panel>Work item not found.</Panel>
      </div>
    );
  }

  const pendingGate = approvals.data?.[0];
  const pendingClar = clarifications.data?.[0];

  const nodes = visibleLifecycleNodes(lifecycle.data?.nodes ?? []).map((n, i) => railNodeView(n, i));
  const latestRun = runs.data?.[0];
  const itemType = typeLabel(workItem.data.type);

  return (
    <div className="canvas-pad">
      <Breadcrumb items={[{ label: "Work Items", href: "/work-items" }, workItem.data.key || id]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">⚡ {workItem.data.title || workItem.data.key || id.slice(0, 8)}</h1>
          <div className="meta-row" style={{ marginTop: "var(--space-2)" }}>
            <span className="meta-item">
              <span className="chip badge--navy">{itemType}</span>
            </span>
            <span className="meta-item">
              Created <strong>{new Date(workItem.data.created_at).toLocaleDateString()}</strong>
            </span>
            {workItem.data.owner && (
              <span className="meta-item">
                Owner <strong>{workItem.data.owner}</strong>
              </span>
            )}
          </div>
        </div>
      </div>

      <Panel
        flush
        title="Lifecycle — Plan tier"
        actions={<span className="t-sm u-muted">{itemType} · one pass through plan phases</span>}
      >
        {nodes.length === 0 ? <p className="t-sm u-muted">No phases run yet.</p> : <LifecycleRail nodes={nodes} />}
      </Panel>

      <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
        <div className="u-stack">
          <Panel title="Description & context">
            {workItem.data.description ? (
              <Markdown className="prose md-body">{workItem.data.description}</Markdown>
            ) : (
              <p className="t-body u-muted">No description yet.</p>
            )}
            <Kv rows={[["Feature stream", workItem.data.feature_stream || "—"]]} />
          </Panel>

          {latestRun && (
            <Panel
              title="Latest run"
              actions={
                <a href={`/runs/${latestRun.id}`} className="t-sm">
                  View run console ↗
                </a>
              }
            >
              <Kv
                rows={[
                  ["Phase", phaseLabel(latestRun.agent_phase ?? latestRun.agent_key)],
                  ["Status", statusLabel(latestRun.status)],
                  ["Cost", latestRun.cost_usd ? `$${latestRun.cost_usd}` : "—"],
                ]}
              />
            </Panel>
          )}
        </div>

        <div className="u-stack">
          {pendingGate && (
            <Card attention>
              <CardBody>
                <span className="gate-panel__role">▲ {gateLabel(pendingGate.gate_type)} · required role: {pendingGate.required_role}</span>
                <h3 className="t-h3">Awaiting your decision</h3>
                <div className="gate-panel__actions">
                  <Button
                    variant="primary"
                    disabled={decideApproval.isPending}
                    onClick={() => decideApproval.mutate({ id: pendingGate.id, decision: "approved" })}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={decideApproval.isPending}
                    onClick={() => decideApproval.mutate({ id: pendingGate.id, decision: "rejected" })}
                  >
                    Reject
                  </Button>
                </div>
                <span className="gate-reassure">Decision is logged with your role &amp; comment.</span>
              </CardBody>
            </Card>
          )}
          {pendingClar && (
            <Card attention>
              <CardBody>
                <span className="gate-panel__role" style={{ color: "var(--accent-purple)" }}>
                  ? Clarification · {phaseLabel(pendingClar.phase)}
                </span>
                <h3 className="t-h3">1 question awaiting an answer</h3>
                <p className="zero-cost">⏸ Paused — no usage billed while waiting</p>
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
                  ["Artifacts", String(workItem.data.artifact_count ?? 0)],
                  ["Open gates", String(approvals.data?.length ?? 0)],
                  ["Clarifications", String(clarifications.data?.length ?? 0)],
                  ["Children", String(lifecycle.data?.children.length ?? 0)],
                ]}
              />
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
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

function WorkItemEpicGallery({ view }: { view: EpicView }) {
  const id = "WI-492";
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
                  <Button variant="primary">Approve</Button>
                  <Button variant="secondary">Reject</Button>
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
