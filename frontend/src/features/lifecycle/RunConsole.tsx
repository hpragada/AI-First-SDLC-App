import { useParams } from "react-router-dom";

import { Badge, Banner, Breadcrumb, Button, Console, Panel } from "../../components/ui";

// S-19 view states: dispatched · running · needs-answer · awaiting-gate · completed ·
// failed · parked.
export type RunConsoleView =
  | "dispatched"
  | "running"
  | "needs-answer"
  | "awaiting-gate"
  | "completed"
  | "failed"
  | "parked";

const BADGE_VARIANT: Record<RunConsoleView, "waiting" | "running" | "needs-answer" | "gate" | "done" | "failed" | "parked"> = {
  dispatched: "waiting",
  running: "running",
  "needs-answer": "needs-answer",
  "awaiting-gate": "gate",
  completed: "done",
  failed: "failed",
  parked: "parked",
};

const BADGE_LABEL: Record<RunConsoleView, string> = {
  dispatched: "Dispatched · waiting",
  running: "Running",
  "needs-answer": "Needs answer",
  "awaiting-gate": "Awaiting gate",
  completed: "Completed",
  failed: "Failed",
  parked: "Parked for takeover",
};

export function RunConsole({ forceView }: { forceView?: RunConsoleView }) {
  const { id = "RUN-42" } = useParams();
  const view: RunConsoleView = forceView ?? "running";

  return (
    <div className="canvas-pad">
      <Breadcrumb items={[{ label: "Phases & Runs", href: "/runs" }, id]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Run console — Architecture · WI-492</h1>
          <div className="meta-row" style={{ marginTop: "var(--space-2)" }}>
            <span className="meta-item">
              Engine <strong>Claude · local companion</strong>
            </span>
            <span className="meta-item">
              Workflow <strong>wf-7c3a</strong>
            </span>
            <span className="meta-item">
              Triggered by <strong>You</strong>
            </span>
          </div>
        </div>
      </div>

      <Panel
        title={id}
        actions={
          <>
            {view === "completed" && (
              <span className="meta-item">
                Cost <strong>$0.31</strong>
              </span>
            )}
            <Badge variant={BADGE_VARIANT[view]}>{BADGE_LABEL[view]}</Badge>
          </>
        }
      >
        {view === "dispatched" && (
          <Banner variant="info">
            Queued for <strong>Sarah's MacBook</strong>. It will start as soon as your companion claims
            it.
          </Banner>
        )}
        {view === "needs-answer" && (
          <Banner variant="purple" title="Paused — no usage billed while waiting">
            The agent asked a question. Answer it to resume in the same session.{" "}
            <a href="/clarifications">Answer now ↗</a>
          </Banner>
        )}
        {view === "awaiting-gate" && (
          <Banner variant="warning" title="Awaiting Architecture gate">
            The artifact is a draft until the architect approves. <a href="/gates">Open gate ↗</a>
          </Banner>
        )}
        {view === "failed" && (
          <Banner variant="danger" title="Engine exited before reporting">
            The local engine crashed mid-run. No artifact was registered.
          </Banner>
        )}
        {view === "parked" && (
          <Banner variant="danger" title="Your machine went offline — this run is parked">
            Rather than hang, it's parked for human takeover. Reconnect and re-run; answered
            clarifications are remembered. <a href="/connect">Reconnect &amp; re-run ↗</a>
          </Banner>
        )}

        <div style={{ marginTop: view === "running" ? 0 : "var(--space-3)" }}>
          <Console lines={consoleLines(view)} />
        </div>

        {view === "failed" && (
          <div className="gate-panel__actions" style={{ marginTop: "var(--space-3)" }}>
            <Button variant="primary">Retry run</Button>
          </div>
        )}
      </Panel>
    </div>
  );
}

function consoleLines(view: RunConsoleView) {
  switch (view) {
    case "dispatched":
      return [
        <span key="1">
          <span className="console__ts">10:41:55</span>
          <span className="info">Dispatched. Waiting for companion to claim…</span>{" "}
          <span className="console__cursor" />
        </span>,
      ];
    case "needs-answer":
      return [
        <span key="1">
          <span className="console__ts">10:42:30</span>Validating against security rules…{" "}
          <span className="ok">[OK]</span>
        </span>,
        <span key="2">
          <span className="console__ts">10:42:44</span>
          <span className="warn">[?] Need input: target Confluence space for the spec?</span>
        </span>,
      ];
    case "awaiting-gate":
      return [
        <span key="1">
          <span className="console__ts">10:42:30</span>Validating against security rules…{" "}
          <span className="ok">[OK]</span>
        </span>,
        <span key="2">
          <span className="console__ts">10:42:31</span>
          <span className="info">Run completed. Awaiting gate.</span>
        </span>,
      ];
    case "completed":
      return [
        <span key="1">
          <span className="console__ts">10:42:30</span>Validating against security rules…{" "}
          <span className="ok">[OK]</span>
        </span>,
        <span key="2">
          <span className="console__ts">10:42:31</span>
          <span className="ok">[OK] Artifact registered as draft (v0.9).</span>
        </span>,
        <span key="3">
          <span className="console__ts">10:42:31</span>
          <span className="info">Run completed in 30s · $0.31 (your subscription).</span>
        </span>,
      ];
    case "failed":
      return [
        <span key="1">
          <span className="console__ts">10:42:14</span>Generating sequence diagrams…
        </span>,
        <span key="2">
          <span className="console__ts">10:42:19</span>
          <span className="err">[ERROR] engine process exited (code 1)</span>
        </span>,
      ];
    case "parked":
      return [
        <span key="1">
          <span className="console__ts">10:42:14</span>Generating sequence diagrams…
        </span>,
        <span key="2">
          <span className="console__ts">10:47:14</span>
          <span className="err">[TIMEOUT] companion last seen 5m ago — parked.</span>
        </span>,
      ];
    case "running":
    default:
      return [
        <span key="1">
          <span className="console__ts">10:42:01</span>Compiling requirements…{" "}
          <span className="ok">[OK]</span>
        </span>,
        <span key="2">
          <span className="console__ts">10:42:14</span>Generating sequence diagrams…{" "}
          <span className="ok">[OK]</span>
        </span>,
        <span key="3">
          <span className="console__ts">10:42:30</span>Validating against security rules…{" "}
          <span className="console__cursor" />
        </span>,
      ];
  }
}
