import { useState } from "react";
import { Link, useParams } from "react-router-dom";

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
import { isInternalStream } from "../../types";
import { CancelWorkItem } from "./CancelWorkItem";
import { EditWorkItem } from "./EditWorkItem";
import { ReopenWorkItem } from "./ReopenWorkItem";
import { countCell } from "./glance";
import { railNodeView } from "./railView";
import { gateLabel, phaseLabel, statusLabel, visibleLifecycleNodes } from "./phases";
import { useApprovals, useClarifications, useDecideApproval, useLifecycle, useRuns, useWorkItem } from "./hooks";
import { artifactsForWorkItem, clarificationsForWorkItem, clarificationLink, gateLink } from "../../links";
import { roleLabel } from "../identity/roles";

function typeLabel(type: string): string {
  if (!type) return "Item";
  const s = type.replace(/_/g, " ");        // "test_case" → "Test case"
  return s.charAt(0).toUpperCase() + s.slice(1);
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
  // Declared above the early returns below — these are hooks, and a hook behind a conditional
  // return is a hook that stops being called once the data arrives.
  const [editOpen, setEditOpen] = useState(false);
  const [reopenOpen, setReopenOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);

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
        <span className="u-row-tight">
          {/* S.No 76 / SCREEN_BUILD_MAP S-15. The gallery has drawn an Edit button in this slot
              since the screen was designed; only the live one was never wired up. An epic is
              where a description matters most — it is what every planning phase reads first. */}
          {workItem.data.state === "cancelled" ? (
            <Button variant="secondary" onClick={() => setReopenOpen(true)}>
              Reopen…
            </Button>
          ) : (
            <Button variant="secondary" onClick={() => setEditOpen(true)}>
              Edit
            </Button>
          )}
          <Link to={`/work-items/${id}/test-cases`} className="btn btn--secondary">
            Test cases
          </Link>
          {/* An epic and a story could be cancelled through the API all along — the server has
              never restricted it by type — but no screen offered it, and this one has shown
              Reopen… since it was built. It could undo a cancellation it gave nobody a way to
              make (2026-10-06). Hidden once the work is done, matching the task screen: `done`
              is terminal, and the only move out of it is not this one. */}
          {workItem.data.state !== "cancelled" && workItem.data.state !== "done" && (
            <Button variant="secondary" onClick={() => setCancelOpen(true)}>
              Cancel work item…
            </Button>
          )}
        </span>
      </div>

      <Panel
        flush
        title="Lifecycle — Planning"
        // Says what these phases are FOR, about this item, rather than labelling our internals.
        actions={(
          <span className="t-sm u-muted">
            Planned once for the whole {itemType.toLowerCase()}
          </span>
        )}
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
            {/* Hidden for the platform's own containers. The accessibility backlog is keyed
                on `__a11y_backlog__` so the platform can find it again; it is not a feature, not
                a stream, and printing it under a heading reading FEATURE STREAM is us showing a
                person our plumbing and asking them to make sense of it. */}
            {!isInternalStream(workItem.data.feature_stream) && (
              <Kv rows={[["Feature stream", workItem.data.feature_stream || "—"]]} />
            )}
          </Panel>

          {latestRun && (
            <Panel
              title="Latest run"
              actions={
                <Link to={`/runs/${latestRun.id}`} className="t-sm">
                  View run console ↗
                </Link>
              }
            >
              <Kv
                rows={[
                  ["Phase", phaseLabel(latestRun.agent_phase ?? latestRun.agent_key)],
                  ["Status", statusLabel(latestRun.status)],
                ]}
              />
            </Panel>
          )}
        </div>

        <div className="u-stack">
          {pendingGate && (
            <Card attention>
              <CardBody>
                {/* Screen Words group 3: "required role: product_owner" -> "decided by a
                    Product Owner". Same helper as the Gates screen. */}
                <span className="gate-panel__role">▲ {gateLabel(pendingGate.gate_type)} · decided by a {roleLabel(pendingGate.required_role)}</span>
                <h3 className="t-h3">Awaiting your decision</h3>
                <div className="gate-panel__actions">
                  <Button
                    variant="primary"
                    disabled={decideApproval.isPending}
                    onClick={() => decideApproval.mutate({ id: pendingGate.id, decision: "approved" })}
                  >
                    Approve
                  </Button>
                  {/* Rejecting from here sent NO comment at all — the reviewer had no box to
                      write in, so the reason was lost and nothing could act on it. Send them to
                      the gate, where they can reject with a reason or request changes. */}
                  <Link className="btn btn--secondary" to={gateLink(pendingGate.id)}>
                    Reject or request changes…
                  </Link>
                </div>
                <span className="gate-reassure">
                  Approving is logged with your role. To send it back, open the gate and say what
                  you want changed.
                </span>
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
                <p className="zero-cost">⏸ Paused — waiting for your answer</p>
                <div className="gate-panel__actions">
                  <Link to={clarificationLink(pendingClar.id)} className="btn btn--primary">
                    Answer question
                  </Link>
                </div>
              </CardBody>
            </Card>
          )}
          <Card>
            <CardBody>
              <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                At a glance
              </h3>
              {/* The five rows every work item screen now answers, in the same order, so moving
                  between an epic, a task and a defect does not mean re-learning the card.
                  `State` was the one this screen lacked. */}
              <Kv
                rows={[
                  ["State", statusLabel(workItem.data.state)],
                  // N2: the count was inert text — the card told you there were four artifacts
                  // and left you to find them in the registry by hand.
                  [
                    "Artifacts",
                    countCell(workItem.data.artifact_count ?? 0,
                              artifactsForWorkItem(workItem.data.id)),
                  ],
                  ["Open gates", String(approvals.data?.length ?? 0)],
                  [
                    "Open clarifications",
                    countCell(clarifications.data?.length ?? 0,
                              clarificationsForWorkItem(workItem.data.id)),
                  ],
                  ["Children", String(lifecycle.data?.children.length ?? 0)],
                ]}
              />
            </CardBody>
          </Card>
        </div>
      </div>

      {/* No "Answered questions" panel here (team decision, 25 August). It was a full search
          box, phase filter and paging control, rendered whether or not the item had a single
          answered question — and on anything the platform created for itself (an accessibility
          defect, the accessibility backlog) there never are any, so it could only ever be an
          empty card. Nothing became unreachable: the same history, with the same search plus a
          work-item filter, is the History tab of Clarifications. */}

      {editOpen && (
        <EditWorkItem workItem={workItem.data} onClose={() => setEditOpen(false)} />
      )}

      {cancelOpen && (
        <CancelWorkItem
          workItem={workItem.data}
          childCount={lifecycle.data?.children?.length ?? 0}
          onClose={() => setCancelOpen(false)}
        />
      )}
      {reopenOpen && (
        <ReopenWorkItem workItem={workItem.data} onClose={() => setReopenOpen(false)} />
      )}
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
const GATE_PENDING_NODES = [
  { label: "Ideation", state: "Approved", tone: "done" as const, mark: "✓" },
  { label: "Requirements", state: "Approved", tone: "done" as const, mark: "✓" },
  { label: "PRD", state: "Approved", tone: "done" as const, mark: "✓" },
  { label: "Architecture", state: "Gate Pending", tone: "current" as const, mark: "●" },
  { label: "UX Design", state: "Not started", tone: "upcoming" as const, mark: 5 },
  { label: "Task Breakdown", state: "Not started", tone: "upcoming" as const, mark: 6 },
];

const NEEDS_ANSWER_NODES = [
  { label: "Ideation", state: "Approved", tone: "done" as const, mark: "✓" },
  { label: "Requirements", state: "Approved", tone: "done" as const, mark: "✓" },
  { label: "PRD", state: "Needs answer", tone: "needs" as const, mark: "?" },
  { label: "Architecture", state: "Not started", tone: "upcoming" as const, mark: 4 },
  { label: "UX Design", state: "Not started", tone: "upcoming" as const, mark: 5 },
  { label: "Task Breakdown", state: "Not started", tone: "upcoming" as const, mark: 6 },
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
        title="Lifecycle — Planning"
        actions={<span className="t-sm u-muted">Planned once for the whole epic</span>}
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
                <p className="zero-cost">⏸ Paused — waiting for your answer · 6m</p>
                <div className="gate-panel__actions">
                  <Link to="/clarifications" className="btn btn--primary">
                    Answer question
                  </Link>
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
