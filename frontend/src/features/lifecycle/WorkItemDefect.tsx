import { useParams } from "react-router-dom";

import { Badge, Banner, Breadcrumb, Button, Card, CardBody, Kv, LifecycleRail, Panel, Spinner } from "../../components/ui";
import { railNodeView } from "./railView";
import { phaseLabel, statusLabel, visibleLifecycleNodes } from "./phases";
import { useLifecycle, useRuns, useTriggerPhase, useWorkItem } from "./hooks";

// S-17 view states: open (default) · fixing · closed.
export type DefectView = "open" | "fixing" | "closed";

export function WorkItemDefect({ forceView }: { forceView?: DefectView }) {
  if (forceView) return <WorkItemDefectGallery view={forceView} />;
  return <WorkItemDefectLive />;
}

// ── Live: the real defect + its remediation-tier lifecycle ──────────────────
function WorkItemDefectLive() {
  const { id } = useParams();
  const workItem = useWorkItem(id);
  const lifecycle = useLifecycle(id);
  const runs = useRuns({ work_item: id });
  const trigger = useTriggerPhase(id);

  if (workItem.isLoading || lifecycle.isLoading) {
    return (
      <div className="canvas-pad">
        <Panel>
          <Spinner /> Loading defect…
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

  const latestRun = runs.data?.[0];
  const running = latestRun?.status === "running";
  const closed = workItem.data.state === "done";
  const nodes = visibleLifecycleNodes(lifecycle.data?.nodes ?? []).map((n, i) => railNodeView(n, i));

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
              <span className="chip badge--orange">Defect</span>
            </span>
            {workItem.data.parent && (
              <span className="meta-item">
                Parent <a href={`/work-items/${workItem.data.parent}`}>↖ {workItem.data.parent.slice(0, 8)}</a>
              </span>
            )}
          </div>
        </div>
        {!closed && (
          <Button variant="primary" disabled={trigger.isPending} onClick={() => trigger.mutate("07_implementation")}>
            {trigger.isPending ? <Spinner /> : "Trigger Fix"}
          </Button>
        )}
      </div>

      <Panel
        flush
        title="Lifecycle — Remediation"
        actions={closed ? <Badge variant="done">Closed</Badge> : <span className="t-sm u-muted">minimal rail</span>}
      >
        {nodes.length === 0 ? <p className="t-sm u-muted">No phases run yet.</p> : <LifecycleRail nodes={nodes} />}
      </Panel>

      <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
        <div className="u-stack">
          <Panel title="Description">
            {closed ? (
              <Banner variant="success" title="Defect closed">
                {workItem.data.description || "This defect was closed by a clean re-run."}
              </Banner>
            ) : running ? (
              <Banner variant="info" title="Fix running on your companion">
                {workItem.data.description || "Fixing…"}
              </Banner>
            ) : (
              <Banner variant="danger" title="Open">
                {workItem.data.description || "No description yet."}
              </Banner>
            )}
          </Panel>
          {latestRun && (
            <Panel title="Latest run" actions={<Badge variant={running ? "running" : "done"}>{latestRun.status}</Badge>}>
              <Kv rows={[["Phase", phaseLabel(latestRun.agent_phase ?? latestRun.agent_key)]]} />
              <a href={`/runs/${latestRun.id}`} className="t-sm">
                View run console ↗
              </a>
            </Panel>
          )}
        </div>
        <Card>
          <CardBody>
            <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
              At a glance
            </h3>
            <Kv
              rows={[
                ["Parent", workItem.data.parent?.slice(0, 8) ?? "—"],
                ["Status", statusLabel(workItem.data.state)],
              ]}
            />
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
function WorkItemDefectGallery({ view }: { view: DefectView }) {
  const id = "WI-547";
  const nodes = {
    open: [
      { label: "Fix", state: "Open", tone: "current" as const, mark: "●" },
      { label: "Review", state: "Upcoming", tone: "upcoming" as const, mark: 2 },
      { label: "Test", state: "Upcoming", tone: "upcoming" as const, mark: 3 },
    ],
    fixing: [
      { label: "Fix", state: "Running", tone: "running" as const, mark: "" },
      { label: "Review", state: "Upcoming", tone: "upcoming" as const, mark: 2 },
      { label: "Test", state: "Upcoming", tone: "upcoming" as const, mark: 3 },
    ],
    closed: [
      { label: "Fix", state: "Patched", tone: "done" as const, mark: "✓" },
      { label: "Review", state: "Clean", tone: "done" as const, mark: "✓" },
      { label: "Test", state: "Passing", tone: "done" as const, mark: "✓" },
    ],
  }[view];

  return (
    <div className="canvas-pad">
      <Breadcrumb
        items={[
          { label: "Work Items", href: "/work-items" },
          { label: "WI-540", href: "/work-items/WI-540" },
          id,
        ]}
      />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Signature check rejects valid test events</h1>
          <div className="meta-row" style={{ marginTop: "var(--space-2)" }}>
            <span className="meta-item">
              <span className="chip badge--orange">Defect</span>
            </span>
            <span className="meta-item">
              Parent <strong>↖ WI-540 Verify Stripe signing secret</strong>
            </span>
            <span className="meta-item">
              From <strong>Testing run #61</strong>
            </span>
          </div>
        </div>
        <Button variant="primary">Trigger Fix</Button>
      </div>

      <Panel
        flush
        title="Lifecycle — Remediation"
        actions={
          view === "closed" ? (
            <Badge variant="done">Closed</Badge>
          ) : (
            <span className="t-sm u-muted">minimal rail</span>
          )
        }
      >
        <LifecycleRail nodes={nodes} />
      </Panel>

      {view === "open" && (
        <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
          <div className="u-stack">
            <Panel title="Originating finding">
              <Banner variant="danger" title="FAIL · webhook.signature.valid_test_event">
                Valid Stripe test-mode events are rejected by the signature check. Opened
                automatically from Testing run #61, traced to the test case.
              </Banner>
            </Panel>
          </div>
          <Card>
            <CardBody>
              <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                At a glance
              </h3>
              <Kv
                rows={[
                  ["Parent task", "WI-540"],
                  ["Epic", "WI-492"],
                  ["Severity", "High"],
                  ["Status", "Open"],
                ]}
              />
            </CardBody>
          </Card>
        </div>
      )}

      {view === "fixing" && (
        <div style={{ marginTop: "var(--space-5)" }}>
          <Panel title="Run console · Fix" actions={<Badge variant="running">Running on your companion</Badge>}>
            <p className="t-sm u-muted">Patching signature tolerance for test-mode events…</p>
          </Panel>
        </div>
      )}

      {view === "closed" && (
        <div style={{ marginTop: "var(--space-5)" }}>
          <Panel>
            <Banner variant="success" title="Defect closed automatically">
              Testing re-run #63 passed <code className="t-mono">webhook.signature.valid_test_event</code>.
              WI-540 is unblocked for the Merge gate.
            </Banner>
          </Panel>
        </div>
      )}
    </div>
  );
}
