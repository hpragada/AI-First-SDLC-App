import { useParams } from "react-router-dom";

import { Badge, Banner, Breadcrumb, Button, Card, CardBody, Console, Kv, LifecycleRail, Panel } from "../../components/ui";

// S-17 view states: open (default) · fixing · closed.
export type DefectView = "open" | "fixing" | "closed";

export function WorkItemDefect({ forceView }: { forceView?: DefectView }) {
  const { id = "WI-547" } = useParams();
  const view: DefectView = forceView ?? "open";

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
            <Console
              lines={[
                <span key="1">
                  <span className="console__ts">15:02:10</span>Reproducing failing case…{" "}
                  <span className="ok">[OK]</span>
                </span>,
                <span key="2">
                  <span className="console__ts">15:02:48</span>Patching signature tolerance for
                  test-mode events…
                </span>,
              ]}
            />
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
