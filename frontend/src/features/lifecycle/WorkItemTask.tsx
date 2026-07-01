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

// S-16 view states: review-loop+test-failed (default) · implementation-running ·
// merge-gate · done.
export type TaskView = "loop-failed" | "running" | "merge-gate" | "done";

export function WorkItemTask({ forceView }: { forceView?: TaskView }) {
  const { id = "WI-540" } = useParams();
  const decideApproval = useDecideApproval();
  const view: TaskView = forceView ?? "loop-failed";

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
            <Console
              lines={[
                <span key="1">
                  <span className="console__ts">09:15:02</span>Creating worktree on
                  acme/payments-api… <span className="ok">[OK]</span>
                </span>,
                <span key="2">
                  <span className="console__ts">09:15:30</span>Implementing signature verification…
                </span>,
              ]}
            />
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
                <Button variant="primary" onClick={() => decideApproval.mutate({ id, decision: "approved" })}>
                  Approve & merge
                </Button>
                <Button variant="secondary" onClick={() => decideApproval.mutate({ id, decision: "rejected" })}>
                  Reject
                </Button>
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
            <Panel title="Latest AI run · Testing">
              <Console
                lines={[
                  <span key="1">
                    <span className="console__ts">14:21:48</span>
                    <span className="err">[FAIL] webhook.signature.valid_test_event</span>
                  </span>,
                  <span key="2">
                    <span className="console__ts">14:21:49</span>
                    <span className="info">Opened defect WI-547 (traced).</span>
                  </span>,
                ]}
              />
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
