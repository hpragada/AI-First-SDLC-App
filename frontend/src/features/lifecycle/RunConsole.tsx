import { useNavigate, useParams } from "react-router-dom";

import { Badge, Banner, Breadcrumb, Button, Console, Panel, Spinner } from "../../components/ui";
import type { RunEvent } from "../../types";
import { phaseLabel } from "./phases";
import { useClarifications, useRun, useRunEvents, useTriggerPhase, useWorkItem } from "./hooks";

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
  if (forceView) return <RunConsoleGallery view={forceView} />;
  return <RunConsoleLive />;
}

function eventLine(e: RunEvent) {
  const ts = new Date(e.ts).toLocaleTimeString();
  const cls = e.kind === "ok" ? "ok" : e.kind === "warn" ? "warn" : e.kind === "err" ? "err" : "info";
  return (
    <span key={e.id}>
      <span className="console__ts">{ts}</span>
      <span className={cls}>{e.message}</span>
    </span>
  );
}

// ── Live: the real run + its event stream ───────────────────────────────────
function RunConsoleLive() {
  const { id } = useParams();
  const navigate = useNavigate();
  const run = useRun(id);
  const events = useRunEvents(id);
  const workItem = useWorkItem(run.data?.work_item);
  const clarifications = useClarifications({ run: id, status: "pending" });
  const retry = useTriggerPhase(run.data?.work_item);

  if (run.isLoading) {
    return (
      <div className="canvas-pad">
        <Panel>
          <Spinner /> Loading run…
        </Panel>
      </div>
    );
  }

  if (!run.data || !id) {
    return (
      <div className="canvas-pad">
        <Breadcrumb items={[{ label: "Phases & Runs", href: "/runs" }, "Not found"]} />
        <Panel>
          <Banner variant="danger" title="Run not found">
            This run doesn't exist or you don't have access to it.
          </Banner>
        </Panel>
      </div>
    );
  }

  const hasPendingClarification = (clarifications.data ?? []).length > 0;
  const view: RunConsoleView = hasPendingClarification
    ? "needs-answer"
    : run.data.status === "pending"
      ? "dispatched"
      : run.data.status === "running"
        ? "running"
        : run.data.status === "awaiting_gate"
          ? "awaiting-gate"
          : run.data.status === "approved" || run.data.status === "completed"
            ? "completed"
            : "failed";

  const lines = (events.data ?? []).map(eventLine);
  // Surface a concrete failure reason (Bugs.xlsx row 21 v.1) — the last error event, or an
  // error captured on the run's outputs — rather than a generic "engine exited" message.
  const outputsError =
    run.data.outputs && typeof run.data.outputs === "object"
      ? ((run.data.outputs as Record<string, unknown>).error ??
        (run.data.outputs as Record<string, unknown>).detail)
      : undefined;
  const lastError = [...(events.data ?? [])].reverse().find((e) => e.kind === "err")?.message;
  const failureReason =
    (typeof outputsError === "string" && outputsError) || lastError || undefined;

  const handleRetry = () => {
    // Re-trigger by the AgentSpec *key* (e.g. "04_architecture"), never the run's
    // agent_spec UUID — the trigger endpoint resolves by key (Bugs.xlsx row 21).
    if (!run.data?.agent_key) return;
    retry.mutate(run.data.agent_key, {
      onSuccess: (result) => navigate(`/runs/${result.run_id}`),
    });
  };

  return (
    <div className="canvas-pad">
      <Breadcrumb items={[{ label: "Phases & Runs", href: "/runs" }, id]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">
            Run console — {phaseLabel(run.data.agent_phase ?? run.data.agent_key)}
            {workItem.data ? ` · ${workItem.data.title || workItem.data.id.slice(0, 8)}` : ""}
          </h1>
          <div className="meta-row" style={{ marginTop: "var(--space-2)" }}>
            <span className="meta-item">
              Engine <strong>{run.data.engine} · {run.data.model}</strong>
            </span>
            <span className="meta-item">
              Workflow <strong>{run.data.temporal_workflow_id || "—"}</strong>
            </span>
          </div>
        </div>
      </div>

      <Panel
        title={id}
        actions={
          <>
            {view === "completed" && run.data.cost_usd && (
              <span className="meta-item">
                Cost <strong>${run.data.cost_usd}</strong>
              </span>
            )}
            <Badge variant={BADGE_VARIANT[view]}>{BADGE_LABEL[view]}</Badge>
          </>
        }
      >
        {view === "dispatched" && (
          <Banner variant="info">Queued. It will start as soon as your companion claims it.</Banner>
        )}
        {view === "needs-answer" && (
          <Banner variant="purple" title="Paused — no usage billed while waiting">
            The agent asked a question. Answer it to resume in the same session.{" "}
            <a href="/clarifications">Answer now ↗</a>
          </Banner>
        )}
        {view === "awaiting-gate" && (
          <Banner variant="warning" title="Awaiting gate">
            The artifact is a draft until its gate is approved. <a href="/gates">Open gate ↗</a>
          </Banner>
        )}
        {view === "failed" && (
          <Banner variant="danger" title={run.data.status === "rejected" ? "Gate rejected" : "Run failed"}>
            {run.data.status === "rejected"
              ? "The gate was rejected. Re-trigger to try again."
              : failureReason
                ? `Reason: ${failureReason}`
                : "The engine exited before reporting. No artifact was registered."}
          </Banner>
        )}

        <div style={{ marginTop: view === "running" ? 0 : "var(--space-3)" }}>
          {lines.length === 0 ? (
            <Console lines={[<span key="empty" className="t-sm u-muted">No log lines yet…</span>]} />
          ) : (
            <Console lines={lines} />
          )}
        </div>

        {view === "failed" && (
          <div className="gate-panel__actions" style={{ marginTop: "var(--space-3)" }}>
            <Button variant="primary" onClick={handleRetry} disabled={retry.isPending}>
              {retry.isPending ? <Spinner /> : "Retry run"}
            </Button>
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
function RunConsoleGallery({ view }: { view: RunConsoleView }) {
  const id = "RUN-42";
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
