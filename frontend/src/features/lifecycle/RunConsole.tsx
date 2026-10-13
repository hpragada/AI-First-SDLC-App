import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Badge, Banner, Breadcrumb, Button, ConfirmDialog, Console, Disclosure, Panel, Spinner, WriteError } from "../../components/ui";
import { engineLabel, readsAsSentence, runStatusLabel } from "../../labels";
import { dispatchUnclaimed, isTerminalState, workerStalled, type RunEvent } from "../../types";
import { CancelWorkItem } from "./CancelWorkItem";
import { phaseLabel } from "./phases";
import {
  useClarifications,
  usePauseRun,
  useResumeRun,
  useRun,
  useRunEvents,
  useTriggerPhase,
  useWorkItem,
} from "./hooks";
import { useCompanionStatus } from "../identity/hooks";
import { clarificationLink, recoveryLink, runLink, transcriptLink } from "../../links";

// S-19 view states: dispatched · running · needs-answer · awaiting-gate · completed ·
// failed · parked · paused.
//
// `parked` and `paused` are deliberately separate views of what is nearly the same machinery. A
// parked run stopped because something went wrong and the reader has to be told what; a paused run
// stopped because they chose to, and telling them a reason would be inventing a fault. Same waiting
// colour, different words, and a different second button.
export type RunConsoleView =
  | "dispatched"
  | "running"
  | "needs-answer"
  | "awaiting-gate"
  | "completed"
  | "failed"
  | "parked"
  | "paused";

const BADGE_VARIANT: Record<RunConsoleView, "waiting" | "running" | "needs-answer" | "gate" | "done" | "failed" | "parked"> = {
  dispatched: "waiting",
  running: "running",
  "needs-answer": "needs-answer",
  "awaiting-gate": "gate",
  completed: "done",
  failed: "failed",
  parked: "parked",
  paused: "parked",
};

const BADGE_LABEL: Record<RunConsoleView, string> = {
  dispatched: "Dispatched · waiting",
  running: "Running",
  "needs-answer": "Needs answer",
  "awaiting-gate": "Awaiting gate",
  completed: "Completed",
  failed: "Failed",
  // "Parked for takeover" was our words for our machinery, six pixels above a banner that called
  // the same state "stopped" — two vocabularies for one thing on one screen. The accessibility
  // screens already settled this: they show "Stopped", with a test that fails if the words "take
  // over" or "workflow" ever reach a user. This screen simply never got the memo.
  parked: "Stopped",
  // Not "Stopped": that is the word for a machine going quiet, and this reader stopped the run
  // themselves. Mirrors the `paused` run-status label in labels.ts.
  paused: "Paused by you",
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
  // Up here with the other hooks, not beside the banner that uses it: everything below the
  // early "run not found" return runs conditionally, and a hook called there changes hook order
  // between renders.
  const runCompanion = useCompanionStatus(workItem.data?.project);
  const retry = useTriggerPhase(run.data?.work_item);
  const [cancelOpen, setCancelOpen] = useState(false);
  const resume = useResumeRun(id);
  const pause = usePauseRun(id);
  // One state for which question is open. Three dialogs, never two at once — and a
  // `null` that means "nothing asked", so no dialog can be left mounted and invisible.
  const [asking, setAsking] = useState<"pause" | "resume" | "discard" | "retry" | null>(null);
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
              : run.data.status === "paused"
                ? "paused"
                : "failed";

  // "Dispatched to a machine that isn't there." Both halves are needed and neither is enough:
  // an unclaimed dispatch with a live companion is simply a run about to start (the claim poll
  // is 5s), and an offline companion with a CLAIMED dispatch is a machine working away that has
  // merely gone quiet — telling that reader to reconnect would be wrong, and it would throw away
  // work in progress.
  //
  // `runCompanion` is scoped to the RUN's own project, not the one in the switcher: somebody can
  // open a run from anywhere, and the question is about the machine that was given this phase.
  const stranded = dispatchUnclaimed(run.data.inputs) && runCompanion.state === "offline";

  const lines = (events.data ?? []).map(eventLine);
  // Surface a concrete failure reason (Bugs.xlsx row 21 v.1) — the error captured on the run's
  // outputs — rather than a generic "engine exited" message.
  const outputsError =
    run.data.outputs && typeof run.data.outputs === "object"
      ? ((run.data.outputs as Record<string, unknown>).error ??
        (run.data.outputs as Record<string, unknown>).detail)
      : undefined;
  // The stored reason is used only if it READS as a sentence (2026-10-05). The classifier's last
  // resort is to pass an unrecognised failure through word-for-word, so a real run here said
  // "Reason: Command failed with exit code 1 (exit code: 1) Error output: Check stderr output for
  // details" — the engine's own log, in the place where the explanation goes, while the event line
  // a few pixels below had already learned to refuse exactly that text. When it is a log excerpt we
  // fall through to the sentence this banner already shows for a failure with no reason recorded.
  // The raw text is not lost: it is under "Technical details", where this screen already puts it.
  //
  // The last error EVENT used to be the middle step of that fall-through, and the live check is why
  // it is not any more: with the log excerpt refused, the banner read "Reason: Stopped after a
  // problem" directly above an event line saying "Stopped after a problem". It restated the line
  // below it and called that the reason. The event list is always right there, so when we have no
  // explanation the banner's own sentence — which says what it means and what to do — is better.
  const failureReason =
    typeof outputsError === "string" && outputsError && readsAsSentence(outputsError)
      ? outputsError
      : undefined;
  // Run-console wording (2026-09-21, option A): the sentence above is for the reader; the raw
  // text behind it (the engine's output, the HTTP call) is `error_detail`, shown only under a
  // closed "Technical details". `kept` is what the platform says a paused run keeps — a build
  // keeps its build, branch and pull request; other runs fall back to the general line.
  const outputsRecord =
    run.data.outputs && typeof run.data.outputs === "object"
      ? (run.data.outputs as Record<string, unknown>)
      : {};
  const errorDetail =
    typeof outputsRecord.error_detail === "string" ? outputsRecord.error_detail : "";
  const kept =
    typeof outputsRecord.kept === "string" ? outputsRecord.kept : "the work already finished is kept";
  const technicalDetails = errorDetail ? (
    <Disclosure summary="Technical details">
      <pre className="t-mono u-wrap-pre">{errorDetail}</pre>
    </Disclosure>
  ) : null;
  // A run parked at an ERROR is resumable from the step that failed (Bugs S.No 157) — its
  // workflow is still alive and waiting. That's what distinguishes it from a companion-offline
  // park (S.No 89), which is only recoverable via reconnect/takeover.
  const isResumable =
    run.data.outputs && typeof run.data.outputs === "object"
      ? (run.data.outputs as Record<string, unknown>).resumable === true
      : false;

  // Bugs S.No 246 — nobody is serving the code version this run is pinned to. Read through one
  // shared narrowing helper so no second screen invents its own shape for the same field.
  const stalled = workerStalled(run.data.outputs);

  // Who paused it, and whether the companion had already started — the two facts the paused banner
  // and the pause dialog need. `was_claimed` is recorded at the moment of the pause, so it stays
  // true afterwards rather than being re-guessed from a status that has since moved on.
  const pausedInfo =
    outputsRecord.paused && typeof outputsRecord.paused === "object"
      ? (outputsRecord.paused as { by?: string; at?: string; was_claimed?: boolean })
      : undefined;
  // Offered only while the run is genuinely going. A run waiting at a gate is already stopped and
  // costs nothing, so pausing it would be offering to stop something that is not running; the
  // backend refuses those for the same reason.
  const canPause = run.data.status === "pending" || run.data.status === "running";

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
      {/* The last crumb names the run the way the heading below does — the phase, and the work
          item when it has loaded. It used to read "Run 3f9a1b2c", which was the id again under a
          different label, and the crumb a person reads first. */}
      <Breadcrumb
        items={[
          { label: "Phases & Runs", href: "/runs" },
          [phaseLabel(run.data.agent_phase ?? run.data.agent_key), workItem.data?.key]
            .filter(Boolean)
            .join(" · "),
        ]}
      />
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
            {/* The Run ID came off here on 2026-10-05, finishing what the earlier pass started.
                That pass removed the raw workflow id and the second printing of this one, and kept
                a labelled short id on the grounds that a user quotes it when asking about a task.
                Looking again with the team: the two things either side of it — the work item's key
                and the phase in the heading above — already name this run in words a client
                recognises, so the id was the only machine string left on the page and it was not
                earning its place. Support can reach a run from the work item plus the phase. */}
            <span className="meta-item">
              {/* Screen Words group 4, Option A: kept, but as the product and model name —
                  `claude · claude-opus-5` told a client nothing. */}
              Engine <strong>{engineLabel(run.data.engine, run.data.model)}</strong>
            </span>
          </div>
        </div>
      </div>

      <Panel
        // The id is already labelled "Run ID" a few pixels above; repeating it here as a title
        // spent the panel's heading on the one thing already on screen. Not the phase either —
        // the h1 above already names that, and swapping one duplicate for another is no fix.
        // What this panel actually holds is the task's progress.
        title="Progress"
        actions={
          <span className="u-row">
            {/* Screen Words group 7 (Option A): the transcript screen was built but nothing
                linked to it. It lists completed and approved runs, so the link appears on
                exactly those — a running or failed run has no transcript page to open. */}
            {(run.data.status === "completed" || run.data.status === "approved") && (
              <Link to={transcriptLink(run.data.id)} className="t-sm">
                Full transcript →
              </Link>
            )}
            {/* Pause sits with the status chip rather than at the foot of the panel, because it is
                offered WHILE the run is going and the log below keeps growing underneath it — a
                button at the bottom of a live log walks away from the pointer. */}
            {canPause && (
              <Button variant="secondary" size="sm" onClick={() => setAsking("pause")}>
                Pause run
              </Button>
            )}
            <Badge variant={BADGE_VARIANT[view]}>{BADGE_LABEL[view]}</Badge>
          </span>
        }
      >
        {/* A run nobody's machine ever picked up. Keyed off `dispatch.status`, NOT the run
            status, and that is the whole finding: dispatching sets the run to RUNNING while
            leaving `dispatch.status` at "pending", so a phase sent to a dead companion rendered
            the *running* view — a live-looking console, spinner and all — for up to the two
            hours until takeover. It never even reached the "waiting to start" line below.

            Wording lifted from RunConsoleGallery, where this banner has existed as an approved
            design all along while nothing wired it to live data. Shipping that copy rather than
            a second draft of it. */}
        {stranded && (
          <Banner variant="danger" title="Your machine isn't connected — this hasn't started">
            Nothing is lost. Reconnect your machine and it will pick this up on its own.{" "}
            <Link to="/connect">Reconnect your machine ↗</Link>
          </Banner>
        )}
        {/* "It will start as soon as your companion claims it" described our machinery competing
            for work. What the reader needs is that it begins on its own — true only while there
            is a machine there to do the beginning, hence the `!stranded`. */}
        {view === "dispatched" && !stranded && (
          <Banner variant="info">Waiting to start. This begins on its own — nothing to do.</Banner>
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
                : // "The engine exited before reporting. No artifact was registered." — three of
                  // our words in one sentence, for the case where we have no reason to give.
                  "This task stopped before it finished. Nothing was saved from it — it can be run again."}
            {run.data.status !== "rejected" && technicalDetails}
          </Banner>
        )}
        {view === "failed" && typeof retryRunId === "string" && (
          <Banner variant="info" title="Automatically retried">
            The platform started a fresh attempt for this work item — you don't need to
            re-trigger.{" "}
            {/* The id went with the Run ID above it (2026-10-05). The status stays, because that
                is the thing worth knowing before clicking — and it goes through the same label
                vocabulary as every other status instead of having its underscores swapped out. */}
            <Link to={`/runs/${retryRunId}`}>
              Open the new attempt
              {retryRun.data ? ` — ${runStatusLabel(retryRun.data.status)}` : ""} ↗
            </Link>
          </Banner>
        )}
        {view === "parked" && isResumable && (
          <Banner variant="warning" title="Paused on an error — you can carry on from here">
            {/* Two paragraphs: the reason used to run straight into "Nothing you've done is
                lost" ("…-> 401 Nothing you've done…"). */}
            <p>{failureReason || "This run hit an error and paused."}</p>
            <p>
              Nothing you&apos;ve done is lost — {kept}. <strong>Resume</strong> continues from
              the step that stopped instead of starting the phase over, or take over to end this
              run.
            </p>
            {technicalDetails}
          </Banner>
        )}
        {view === "paused" && (
          <Banner variant="warning" title="Paused — pick it up whenever you're ready">
            <p>
              {pausedInfo?.by ? `Paused by ${pausedInfo.by}` : "You paused this run"}
              {pausedInfo?.at ? ` at ${new Date(pausedInfo.at).toLocaleTimeString()}` : ""}.{" "}
              Nothing you&apos;ve done is lost — {kept}.
            </p>
            {/* Only said when it is true. Telling somebody their companion "may still be finishing
                the current step" when it had not started is noise that costs the sentence its
                credibility the next time it matters. */}
            {pausedInfo?.was_claimed && (
              <p>
                Your companion may still be finishing the step it was on when you paused — nothing
                new will be started, and the result is kept when it arrives.
              </p>
            )}
          </Banner>
        )}

        {/* Bugs S.No 246, rewritten 8 September for the person who actually reads it.
            Rendered ONLY while the reconciler says nobody is serving this run's code version,
            and gone the moment that stops being true — the note is the condition, not a slot on
            the screen.

            WHAT THIS USED TO SAY, AND WHY IT WAS WRONG. "Ask your tech lead to restart the SDLC
            helper, or take the task over here", a "Take over this task" button, and a Technical
            details panel holding two build stamps. Every part of that was written for us: the
            client does not run this platform, cannot restart it, has no idea what an "SDLC
            helper" is (the product's own word is Companion, and the Companion is not even the
            thing that needs restarting), and has no use for a version string. The button led to
            a screen with no navigation entry that opens with a raw id and the words "parked for
            takeover".

            The state is on the chip above. This is the one sentence that state means for them.
            The build stamps still exist where they belong — in the server log, which our team
            reads when a client says "my task says it has stopped".

            Amber, not red (team decision, 8 September): red means something is wrong and you
            must act, and there is nothing here for a client to act on. Amber means waiting,
            which is what this is — the same hue as the Paused chip on the gates screen, which is
            this same situation seen from the other end. */}
        {stalled && (
          <Banner variant="warning">
            This task has stopped and will continue once the system is up and running.
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
              <Button variant="primary" onClick={() => setAsking("retry")} disabled={retry.isPending}>
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
              <WriteError title="Couldn't resume" detail={resume.error} />
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
        {view === "paused" && (
          <>
            {resume.isError && <WriteError title="Couldn't resume" detail={resume.error} />}
            <div className="gate-panel__actions" style={{ marginTop: "var(--space-3)" }}>
              <Button variant="primary" onClick={() => setAsking("resume")} disabled={resume.isPending}>
                {resume.isPending ? <Spinner /> : "Resume run"}
              </Button>
              {/* The SAME action as "Take over instead" above — one endpoint, one signal — under
                  the only words that are true here. "Take over" is about rescuing something broken,
                  and nothing is broken: this person stopped the run on purpose. It has to be offered
                  at all because a paused run blocks re-triggering that phase, so without a way out
                  somebody who changed their mind would be stuck until their companion was back. */}
              <Button variant="secondary" onClick={() => setAsking("discard")}>
                Discard this run
              </Button>
            </div>
          </>
        )}
      </Panel>

      {cancelOpen && workItem.data && (
        <CancelWorkItem workItem={workItem.data} onClose={() => setCancelOpen(false)} />
      )}

      {asking === "pause" && (
        <ConfirmDialog
          title="Pause this run?"
          confirmLabel="Pause run"
          cancelLabel="Keep running"
          busy={pause.isPending}
          error={pause.isError ? pause.error : undefined}
          errorFallback="The run could not be paused."
          onClose={() => setAsking(null)}
          onConfirm={() => pause.mutate(undefined, { onSuccess: () => setAsking(null) })}
        >
          {/* Two different truths, and the screen knows which one applies, so it says that one
              rather than a vague sentence covering both. A Pause that implied an instant stop would
              be a promise we break in front of the client: there is NO channel from the platform to
              a companion, so an agent already working cannot be interrupted at all. */}
          {run.data.status === "pending" ? (
            <>
              <p>
                Your companion hasn&apos;t started this yet, so pausing stops it before any work
                begins.
              </p>
              <p>Nothing is lost. Resume whenever you&apos;re ready and it starts from here.</p>
            </>
          ) : (
            <>
              <p>
                Your companion is working on this now. It will finish the step it&apos;s on, then
                stop and wait for you — so this may take a few minutes to come to a stop.
              </p>
              <p>Everything done so far is kept. Resume picks up from where it stopped.</p>
              <p>
                If you need it to stop right now, close the companion on your machine.
              </p>
            </>
          )}
        </ConfirmDialog>
      )}

      {asking === "resume" && (
        <ConfirmDialog
          title="Resume this run?"
          confirmLabel="Resume run"
          cancelLabel="Not yet"
          busy={resume.isPending}
          error={resume.isError ? resume.error : undefined}
          errorFallback="The run could not be resumed."
          onClose={() => setAsking(null)}
          onConfirm={() => resume.mutate(undefined, { onSuccess: () => setAsking(null) })}
        >
          <p>
            This continues {phaseLabel(run.data.agent_phase ?? run.data.agent_key)} from where it
            stopped. Your companion needs to be running.
          </p>
        </ConfirmDialog>
      )}

      {asking === "retry" && (
        <ConfirmDialog
          title="Run this phase again?"
          confirmLabel="Retry run"
          cancelLabel="Not now"
          busy={retry.isPending}
          error={retry.isError ? retry.error : undefined}
          errorFallback="The phase could not be started."
          onClose={() => setAsking(null)}
          onConfirm={handleRetry}
        >
          <p>
            This starts {phaseLabel(run.data.agent_phase ?? run.data.agent_key)} again from the
            beginning, on your companion. It replaces what the failed run produced; the run you are
            looking at stays in the history.
          </p>
        </ConfirmDialog>
      )}

      {asking === "discard" && (
        <ConfirmDialog
          title="Discard this paused run?"
          confirmLabel="Discard run"
          cancelLabel="Keep it paused"
          danger
          onClose={() => setAsking(null)}
          onConfirm={() => {
            setAsking(null);
            navigate(recoveryLink(id as string));
          }}
        >
          <p>
            This ends the run. What it produced so far is kept, but the run itself can&apos;t be
            resumed afterwards — you&apos;d start the phase again from the beginning.
          </p>
        </ConfirmDialog>
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
