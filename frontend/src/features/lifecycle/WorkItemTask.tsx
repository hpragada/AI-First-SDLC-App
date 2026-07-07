import { useParams } from "react-router-dom";

import {
  Badge,
  Breadcrumb,
  Button,
  Card,
  CardBody,
  Kv,
  LifecycleRail,
  Panel,
  Spinner,
} from "../../components/ui";
import { railNodeView } from "./railView";
import { gateLabel, phaseLabel, statusLabel, visibleLifecycleNodes } from "./phases";
import { useApprovals, useDecideApproval, useLifecycle, useRuns, useTriggerPhase, useWorkItem } from "./hooks";

// S-16 view states: review-loop+test-failed (default) · implementation-running ·
// merge-gate · done.
export type TaskView = "loop-failed" | "running" | "merge-gate" | "done";

export function WorkItemTask({ forceView }: { forceView?: TaskView }) {
  if (forceView) return <WorkItemTaskGallery view={forceView} />;
  return <WorkItemTaskLive />;
}

// ── Live: the real task + its build-tier lifecycle ──────────────────────────
function WorkItemTaskLive() {
  const { id } = useParams();
  const workItem = useWorkItem(id);
  const lifecycle = useLifecycle(id);
  const approvals = useApprovals({ work_item: id, decision: "pending" });
  const runs = useRuns({ work_item: id });
  const decideApproval = useDecideApproval();
  const trigger = useTriggerPhase(id);

  if (workItem.isLoading || lifecycle.isLoading) {
    return (
      <div className="canvas-pad">
        <Panel>
          <Spinner /> Loading task…
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
  const latestRun = runs.data?.[0];
  const running = latestRun?.status === "running";
  const done = workItem.data.state === "done";
  const nodes = visibleLifecycleNodes(lifecycle.data?.nodes ?? []).map((n, i) => railNodeView(n, i));
  const loops = lifecycle.data?.loops ?? [];

  return (
    <div className="canvas-pad">
      <Breadcrumb
        items={[
          { label: "Work Items", href: "/work-items" },
          ...(workItem.data.parent ? [{ label: workItem.data.parent.slice(0, 8), href: `/work-items/${workItem.data.parent}` }] : []),
          id,
        ]}
      />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">{workItem.data.title || workItem.data.key || id.slice(0, 8)}</h1>
          <div className="meta-row" style={{ marginTop: "var(--space-2)" }}>
            <span className="meta-item">
              <span className="chip">Task</span>
            </span>
            {workItem.data.parent && (
              <span className="meta-item">
                Parent <a href={`/work-items/${workItem.data.parent}`}>↖ {workItem.data.parent.slice(0, 8)}</a>
              </span>
            )}
            {workItem.data.owner && (
              <span className="meta-item">
                Owner <strong>{workItem.data.owner}</strong>
              </span>
            )}
          </div>
        </div>
        <span className="u-row-tight">
          <Button variant="primary" disabled={trigger.isPending} onClick={() => trigger.mutate("07_implementation")}>
            {trigger.isPending ? <Spinner /> : "Trigger phase"}
          </Button>
        </span>
      </div>

      <Panel
        flush
        title="Lifecycle — Build tier"
        actions={<span className="t-sm u-muted">Task · build phases only</span>}
      >
        {nodes.length === 0 ? (
          <p className="t-sm u-muted">No phases run yet.</p>
        ) : (
          <LifecycleRail
            nodes={nodes}
            loop={loops.length > 0 && `↺ ${loops.map((l) => `${l.from} ↔ ${l.to} ×${l.count}`).join(", ")}`}
          />
        )}
      </Panel>

      <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
        <div className="u-stack">
          <Panel title="Description">
            <p className="t-body">{workItem.data.description || "No description yet."}</p>
          </Panel>

          {latestRun && (
            <Panel
              title="Latest run"
              actions={
                <Badge variant={running ? "running" : latestRun.status === "failed" ? "failed" : "done"}>
                  {running ? "Running on your companion" : statusLabel(latestRun.status)}
                </Badge>
              }
            >
              <Kv
                rows={[
                  ["Phase", phaseLabel(latestRun.agent_phase ?? latestRun.agent_key)],
                  ["Cost", latestRun.cost_usd ? `$${latestRun.cost_usd}` : "—"],
                ]}
              />
              <a href={`/runs/${latestRun.id}`} className="t-sm">
                View run console ↗
              </a>
            </Panel>
          )}

          {(lifecycle.data?.children.length ?? 0) > 0 && (
            <Panel title="Related work items">
              {lifecycle.data!.children.map((c) => (
                <div className="artifact-row" key={c.id}>
                  <div className="artifact-row__main">
                    <div className="artifact-row__title">{c.title || c.id.slice(0, 8)}</div>
                    <div className="artifact-row__meta">{c.type} · {phaseLabel(c.phase)}</div>
                  </div>
                  <a href={`/work-items/${c.id}`} className="btn btn--ghost btn--sm">
                    Open
                  </a>
                </div>
              ))}
            </Panel>
          )}
        </div>

        <div className="u-stack">
          {pendingGate ? (
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
              </CardBody>
            </Card>
          ) : done ? (
            <Panel>
              <div className="toast toast--success" style={{ boxShadow: "none", maxWidth: "none" }}>
                <div>
                  <div className="toast__title">Done</div>
                  <div className="toast__body">This task is complete.</div>
                </div>
              </div>
            </Panel>
          ) : null}
          <Card>
            <CardBody>
              <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                At a glance
              </h3>
              <Kv
                rows={[
                  ["State", statusLabel(workItem.data.state)],
                  ["Artifacts", String(workItem.data.artifact_count ?? 0)],
                  ["Open gates", String(approvals.data?.length ?? 0)],
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
function WorkItemTaskGallery({ view }: { view: TaskView }) {
  const id = "WI-540";
  const nodes = {
    "loop-failed": [
      { label: "Implementation", state: "PR #218", tone: "done" as const, mark: "✓" },
      { label: "Review", state: "Clean", tone: "done" as const, mark: "✓" },
      { label: "Test", state: "Defect WI-547", tone: "failed" as const, mark: "!" },
      { label: "Merge", state: "Upcoming", tone: "upcoming" as const, mark: 4 },
    ],
    running: [
      { label: "Implementation", state: "Running", tone: "running" as const, mark: "" },
      { label: "Review", state: "Upcoming", tone: "upcoming" as const, mark: 2 },
      { label: "Test", state: "Upcoming", tone: "upcoming" as const, mark: 3 },
      { label: "Merge", state: "Upcoming", tone: "upcoming" as const, mark: 4 },
    ],
    "merge-gate": [
      { label: "Implementation", state: "PR #218", tone: "done" as const, mark: "✓" },
      { label: "Review", state: "Clean", tone: "done" as const, mark: "✓" },
      { label: "Test", state: "Passing", tone: "done" as const, mark: "✓" },
      { label: "Merge", state: "Gate Pending", tone: "current" as const, mark: "●" },
    ],
    done: [
      { label: "Implementation", state: "PR #218", tone: "done" as const, mark: "✓" },
      { label: "Review", state: "Clean", tone: "done" as const, mark: "✓" },
      { label: "Test", state: "Passing", tone: "done" as const, mark: "✓" },
      { label: "Merge", state: "Merged", tone: "done" as const, mark: "✓" },
    ],
  }[view];

  return (
    <div className="canvas-pad">
      <Breadcrumb
        items={[
          { label: "Work Items", href: "/work-items" },
          { label: "WI-492", href: "/work-items/WI-492" },
          id,
        ]}
      />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Verify Stripe signing secret</h1>
          <div className="meta-row" style={{ marginTop: "var(--space-2)" }}>
            <span className="meta-item">
              <span className="chip">Task</span>
            </span>
            <span className="meta-item">
              Parent <strong>↖ WI-492 Stripe Webhook Integration</strong>
            </span>
            <span className="meta-item">
              Owner <strong>Dan Ortiz</strong>
            </span>
          </div>
        </div>
        <span className="u-row-tight">
          <Button variant="secondary">Edit</Button>
          <Button variant="primary">Trigger phase</Button>
        </span>
      </div>

      <Panel
        flush
        title="Lifecycle — Build tier"
        actions={
          view !== "loop-failed" && <span className="t-sm u-muted">Task · build phases only</span>
        }
      >
        <LifecycleRail
          nodes={nodes}
          loop={view === "loop-failed" && "↺ Review ↔ Implementation loop ×2"}
          branch={
            view === "loop-failed" && (
              <>
                ⌐ Child defect:{" "}
                <a href="/work-items/WI-547">WI-547 "Signature check rejects valid test events"</a> —
                closes on clean re-run.
              </>
            )
          }
        />
      </Panel>

      {view === "running" && (
        <div style={{ marginTop: "var(--space-5)" }}>
          <Panel title="Run console" actions={<Badge variant="running">Running on your companion</Badge>}>
            <p className="t-sm u-muted">Implementing signature verification…</p>
          </Panel>
        </div>
      )}

      {view === "merge-gate" && (
        <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
          <Panel title="Lifecycle status">
            <p className="t-sm u-body">All checks pass. Approving merges the PR and completes this task.</p>
          </Panel>
          <Card attention>
            <CardBody>
              <span className="gate-panel__role">▲ Merge gate · required role: reviewer</span>
              <h3 className="t-h3">PR #218 ready to merge</h3>
              <p className="t-sm u-body">All checks pass. Approving merges the PR and completes this task.</p>
              <div className="gate-panel__actions">
                <Button variant="primary">Approve & merge</Button>
                <Button variant="secondary">Reject</Button>
              </div>
            </CardBody>
          </Card>
        </div>
      )}

      {view === "done" && (
        <div style={{ marginTop: "var(--space-5)" }}>
          <Panel>
            <div className="toast toast--success" style={{ boxShadow: "none", maxWidth: "none" }}>
              <div>
                <div className="toast__title">Merged to main</div>
                <div className="toast__body">
                  PR #218 merged · WI-540 done. Parent epic WI-492 advances when all children
                  complete.
                </div>
              </div>
            </div>
          </Panel>
        </div>
      )}

      {view === "loop-failed" && (
        <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
          <div className="u-stack">
            <Panel title="Linked pull request">
              <div className="artifact-row">
                <div className="artifact-row__main">
                  <div className="artifact-row__title">PR #218 · Verify Stripe signing secret</div>
                  <div className="artifact-row__meta">Open · acme/payments-api · base main</div>
                </div>
                <Badge variant="waiting">Open</Badge>
              </div>
            </Panel>
            <Panel title="Child defects & remediations">
              <div className="artifact-row">
                <div className="artifact-row__main">
                  <div className="artifact-row__title">Signature check rejects valid test events</div>
                  <div className="artifact-row__meta">WI-547 · from Testing run #61</div>
                </div>
                <Badge variant="failed">Open</Badge>
                <Button variant="ghost" size="sm">
                  Open
                </Button>
              </div>
            </Panel>
          </div>
          <div className="u-stack">
            <Card>
              <CardBody>
                <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                  At a glance
                </h3>
                <Kv
                  rows={[
                    ["Parent epic", "WI-492"],
                    ["Phase", "Test"],
                    ["PR", "#218 open"],
                    ["Open defects", "1"],
                  ]}
                />
              </CardBody>
            </Card>
            <Card>
              <CardBody>
                <h3 className="t-h3">Next step</h3>
                <p className="t-sm u-body">
                  Fix WI-547, then re-run Testing. A clean run closes the defect and unblocks the
                  Merge gate.
                </p>
              </CardBody>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
