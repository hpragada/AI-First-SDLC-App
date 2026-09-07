import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Badge, Banner, Breadcrumb, Button, Console, Panel, Spinner } from "../../components/ui";
import { isTerminalState, type RunEvent } from "../../types";
import { CancelWorkItem } from "./CancelWorkItem";
import { phaseLabel } from "./phases";
import {
  useClarifications,
  useResumeRun,
  useRun,
  useRunEvents,
  useTriggerPhase,
  useWorkItem,
} from "./hooks";
import { clarificationLink, recoveryLink, runLink } from "../../links";

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
  const [cancelOpen, setCancelOpen] = useState(false);
  const resume = useResumeRun(id);
  // Bugs S.No 161 follow-up: when a build exhausts remediation it is marked FAILED and the
  // platform auto-starts a FRESH run for the same work item, storing that run's id on this
  // run's outputs.retry_run_id. Nothing surfaced it — the console showed "Failed / auto-retrying"
  // with no link and no sign the retry was actually running, which repeatedly confused users
  // (they saw a failed run and a separate pending gate with nothing connecting them). Read the
  // pointer and fetch the retry run so we can link to it and show its LIVE status.
  const retryRunId =
    run.data?.outputs && typeof run.data.outputs === "object"
      ? (run.data.outputs as Record<string, unknown>).retry_run_id
      : undefined;
  const retryRun = useRun(typeof retryRunId === "string" ? retryRunId : undefined);

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

  const firstPendingClarification = (clarifications.data ?? [])[0];
  const hasPendingClarification = Boolean(firstPendingClarification);
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
            : run.data.status === "stalled"
              ? "parked"
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
  // A run parked at an ERROR is resumable from the step that failed (Bugs S.No 157) — its
  // workflow is still alive and waiting. That's what distinguishes it from a companion-offline
  // park (S.No 89), which is only recoverable via reconnect/takeover.
  const isResumable =
    run.data.outputs && typeof run.data.outputs === "object"
      ? (run.data.outputs as Record<string, unknown>).resumable === true
      : false;

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
      <Breadcrumb items={[{ label: "Phases & Runs", href: "/runs" }, `Run ${id.slice(0, 8)}`]} />
      <div className="page-head">
        <div className="page-head__titles">
          {/* Bugs S.No 172: lead with the work item (key + title) so the user can confirm the
              right item is running; the raw IDs are labelled and kept for debugging. */}
          <h1 className="t-h1">
            Run console — {phaseLabel(run.data.agent_phase ?? run.data.agent_key)}
            {workItem.data
              ? ` · ${workItem.data.key ? `${workItem.data.key} ` : ""}${workItem.data.title || workItem.data.id.slice(0, 8)}`
              : ""}
          </h1>
          <div className="meta-row" style={{ marginTop: "var(--space-2)" }}>
            {workItem.data && (
              <span className="meta-item" title={workItem.data.id}>
                Work item <strong>{workItem.data.key || workItem.data.title || workItem.data.id.slice(0, 8)}</strong>
              </span>
            )}
            <span className="meta-item" title={id}>
              Run ID <strong>{id.slice(0, 8)}</strong>
            </span>
            <span className="meta-item">
              Engine <strong>{run.data.engine} · {run.data.model}</strong>
            </span>
            <span className="meta-item" title={run.data.temporal_workflow_id || undefined}>
              Workflow <strong>{run.data.temporal_workflow_id ? run.data.temporal_workflow_id.slice(0, 16) : "—"}</strong>
            </span>
          </div>
        </div>
      </div>

      <Panel
        title={<span title={id}>Run {id.slice(0, 8)}</span>}
        actions={<Badge variant={BADGE_VARIANT[view]}>{BADGE_LABEL[view]}</Badge>}
      >
        {view === "dispatched" && (
          <Banner variant="info">Queued. It will start as soon as your companion claims it.</Banner>
        )}
        {view === "needs-answer" && (
          <Banner variant="purple" title="Paused — waiting for your answer">
            The agent asked a question. Answer it to resume in the same session.{" "}
            {/* N2: this console already fetches THIS run's pending clarifications. Sending
                "Answer now" to the bare list opened whatever question happened to be first
                across the project — not the one this run is blocked on. */}
            <Link
              to={
                firstPendingClarification
                  ? clarificationLink(firstPendingClarification.id)
                  : "/clarifications"
              }
            >
              Answer now ↗
            </Link>
          </Banner>
        )}
        {view === "awaiting-gate" && (
          <Banner variant="warning" title="Awaiting gate">
            The artifact is a draft until its gate is approved. <Link to="/gates">Open gate ↗</Link>
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
        {view === "failed" && typeof retryRunId === "string" && (
          <Banner variant="info" title="Automatically retried">
            The platform started a fresh attempt for this work item — you don't need to
            re-trigger.{" "}
            <Link to={`/runs/${retryRunId}`}>
              Continued as run {retryRunId.slice(0, 8)}
              {retryRun.data ? ` (${retryRun.data.status.replace(/_/g, " ")})` : ""} ↗
            </Link>
          </Banner>
        )}
        {view === "parked" && isResumable && (
          <Banner variant="warning" title="Paused on an error — you can carry on from here">
            {failureReason ? `Reason: ${failureReason}` : "This run hit an error and paused."}
            {" "}Nothing you've done is lost — the work already finished is kept. Fix the cause if
            you need to, then <strong>Resume</strong> to continue from the step that failed
            instead of starting the phase over. Or take over to end this run.
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
            {typeof retryRunId === "string" ? (
              // Already auto-retried — sending the user to the live attempt, not spawning a
              // duplicate run via a manual re-trigger.
              <Button variant="primary" onClick={() => navigate(runLink(retryRunId))}>
                Go to the retry run →
              </Button>
            ) : (
              <Button variant="primary" onClick={handleRetry} disabled={retry.isPending}>
                {retry.isPending ? <Spinner /> : "Retry run"}
              </Button>
            )}
            {/* Bugs S.No 140 — offered beside Retry, at the moment Retry stops being worth
                pressing. Watching the same build fail for the fourth time is exactly when a
                person decides this work is not going to happen, and until now the only way to
                act on that decision was to mark the item done (a lie) or leave it open for
                ever. Hidden once the item is already finished or abandoned. */}
            {workItem.data && !isTerminalState(workItem.data.state) && (
              <Button variant="secondary" onClick={() => setCancelOpen(true)}>
                Cancel this work item…
              </Button>
            )}
          </div>
        )}
        {view === "parked" && isResumable && (
          <>
            {resume.isError && (
              <Banner variant="danger" title="Couldn't resume">
                {resume.error instanceof Error ? resume.error.message : "Unknown error"}
              </Banner>
            )}
            <div className="gate-panel__actions" style={{ marginTop: "var(--space-3)" }}>
              <Button
                variant="primary"
                onClick={() => resume.mutate()}
                disabled={resume.isPending}
              >
                {resume.isPending ? <Spinner /> : "Resume from where it stopped"}
              </Button>
              {/* N2: this offered takeover from the console of a SPECIFIC parked run and then
                  navigated with no run id, so the destination had to guess — and guessed the
                  first parked run in the project, which on a project with two is the wrong one.
                  It is now the first producer of `?run=`. */}
              <Button variant="secondary" onClick={() => navigate(recoveryLink(id as string))}>
                Take over instead
              </Button>
            </div>
          </>
        )}
      </Panel>

      {cancelOpen && workItem.data && (
        <CancelWorkItem workItem={workItem.data} onClose={() => setCancelOpen(false)} />
      )}
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
        actions={<Badge variant={BADGE_VARIANT[view]}>{BADGE_LABEL[view]}</Badge>}
      >
        {view === "dispatched" && (
          <Banner variant="info">
            Queued for <strong>Sarah's MacBook</strong>. It will start as soon as your companion claims
            it.
          </Banner>
        )}
        {view === "needs-answer" && (
          <Banner variant="purple" title="Paused — waiting for your answer">
            The agent asked a question. Answer it to resume in the same session.{" "}
            <Link to="/clarifications">Answer now ↗</Link>
          </Banner>
        )}
        {view === "awaiting-gate" && (
          <Banner variant="warning" title="Awaiting Architecture gate">
            The artifact is a draft until the architect approves. <Link to="/gates">Open gate ↗</Link>
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
            clarifications are remembered. <Link to="/connect">Reconnect &amp; re-run ↗</Link>
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
