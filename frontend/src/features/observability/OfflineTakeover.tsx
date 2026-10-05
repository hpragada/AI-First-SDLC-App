import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Banner, Breadcrumb, Button, Card, CardBody, ConfirmDialog, EmptyState, ErrorState, Kv, Panel, Spinner, WriteError } from "../../components/ui";
import { useRun, useRuns, useTriggerPhase, useWorkItem } from "../lifecycle/hooks";
import { phaseLabel } from "../lifecycle/phases";
import { useTakeOverRun } from "./hooks";

// S-32 view states: parked · reconnecting · resumed.
export type TakeoverView = "parked" | "reconnecting" | "resumed";

export function OfflineTakeover({ forceView }: { forceView?: TakeoverView }) {
  if (forceView) return <OfflineTakeoverGallery view={forceView} />;
  return <OfflineTakeoverLive />;
}

// ── Live: the real parked (failed) run for the selected project ────────────
function OfflineTakeoverLive() {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const runIdParam = params.get("run") ?? undefined;

  const runs = useRuns({ project: runIdParam ? undefined : projectId });
  // N2 — `?run=` was read here and then thrown away: `parkedRun` was forced to `undefined`
  // whenever the param was present, and the guard below then rendered "No parked runs", denying
  // the run existed. Nothing in the app ever produced the URL either, so the feature was
  // unreachable from both ends and fixing one alone would have left it that way. Fetch the run
  // the link names.
  const named = useRun(runIdParam);
  // A report-timeout parks a run as "stalled" (non-terminal, reconcilable — Bugs S.No 89);
  // "failed" is the legacy/terminal park. Surface either for takeover.
  const parkedRun = runIdParam
    ? named.data
    : (runs.data ?? []).find((r) => r.status === "stalled" || r.status === "failed");

  const runId = runIdParam ?? parkedRun?.id;
  const workItem = useWorkItem(parkedRun?.work_item);
  const takeOver = useTakeOverRun();
  const retry = useTriggerPhase(parkedRun?.work_item);
  // "Reconnect & re-run" starts a whole new phase run — and it fired on one click, on a recovery
  // screen somebody reaches when something has already gone wrong.
  const [asking, setAsking] = useState(false);

  // Guard the loading state on BOTH branches. Before, only the list branch had one — so a
  // deep link flashed "No parked runs" while its fetch was still in flight, which is the same
  // lie the bug told, just briefly.
  if (runIdParam ? named.isLoading : runs.isLoading) {
    return (
      <div className="canvas-pad" style={{ maxWidth: "880px" }}>
        <Panel>
          <Spinner /> {runIdParam ? "Loading this run…" : "Checking for parked runs…"}
        </Panel>
      </div>
    );
  }

  if (runIdParam && (named.isError || !named.data)) {
    return (
      <div className="canvas-pad" style={{ maxWidth: "880px" }}>
        <Breadcrumb items={[{ label: "Phases & Runs", href: "/runs" }, "Recovery"]} />
        <Panel>
          <ErrorState
            title="We couldn't open that run"
            detail={named.error}
            onRetry={() => void named.refetch()}
          />
        </Panel>
      </div>
    );
  }

  if (!runId || !parkedRun) {
    return (
      <div className="canvas-pad" style={{ maxWidth: "880px" }}>
        <Breadcrumb items={[{ label: "Phases & Runs", href: "/runs" }, "Recovery"]} />
        <Panel>
          <EmptyState title="No parked runs" text="Nothing needs human takeover right now." />
        </Panel>
      </div>
    );
  }

  const handleTakeover = () => {
    takeOver.mutate({ runId });
  };

  const handleResume = () => {
    if (!parkedRun) return;
    takeOver.mutate(
      { runId, release: true },
      {
        onSuccess: () => {
          if (!parkedRun.agent_key) return;
          // Re-trigger by AgentSpec key, not the run's agent_spec UUID (Bugs.xlsx row 21).
          retry.mutate(parkedRun.agent_key, {
            onSuccess: (result) => navigate(`/runs/${result.run_id}`),
          });
        },
      },
    );
  };

  return (
    <div className="canvas-pad" style={{ maxWidth: "880px" }}>
      <Breadcrumb items={[{ label: "Phases & Runs", href: "/runs" }, "Recovery"]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">
            Run recovery — {workItem.data?.title || parkedRun.work_item.slice(0, 8)} · {phaseLabel(parkedRun.agent_phase ?? parkedRun.agent_key)}
          </h1>
          {/* Rewritten 8 September under the team's rule: the words are for whoever opens this
              screen, not for us. "The platform parks the run for takeover rather than letting it
              hang" described our design decision; a raw UUID was the subject of the sentence
              below it; and the details list printed a full id, a database status value and an
              ISO timestamp. Everything here now reads as a sentence. The labelled short Run ID
              survived that pass and came off on 2026-10-05: the four rows above it — the task, the
              phase, why it stopped and when it started — already say which run this is, in words,
              so the id was the only machine string left on the screen. */}
          <p className="page-head__sub">
            When your machine goes offline part-way through, a task stops and waits here instead of
            hanging.
          </p>
        </div>
      </div>

      <Card>
        <CardBody className="u-stack">
          <Banner variant="warning" title="This task stopped and is waiting for you">
            Your machine stopped reporting back. Nothing has been lost — nothing was published, and
            any questions you already answered are remembered.
          </Banner>
          <Kv
            rows={[
              ["Task", workItem.data?.title || workItem.data?.key || "—"],
              ["Phase", phaseLabel(parkedRun.agent_phase ?? parkedRun.agent_key)],
              ["Stopped", parkedRun.status === "failed" ? "After an error" : "After going quiet"],
              ["Started", new Date(parkedRun.created_at).toLocaleString()],
            ]}
          />
          <Banner variant="info">
            If your machine simply went to sleep, bringing it back online lets it finish this same
            task on its own and carry on to its approval. Or reconnect and run it again to start
            fresh — your earlier answers are kept either way.
          </Banner>
          {takeOver.isError && (
            <WriteError title="That didn't work" detail={takeOver.error} />
          )}
          <div className="gate-panel__actions">
            <Button variant="primary" onClick={() => setAsking(true)} disabled={takeOver.isPending || retry.isPending}>
              {takeOver.isPending || retry.isPending ? <Spinner /> : "Reconnect & re-run"}
            </Button>
            <Button variant="secondary" onClick={handleTakeover} disabled={takeOver.isPending}>
              Take over manually
            </Button>
            <Link to="/connect" className="btn btn--ghost">
              Connect your machine
            </Link>
          </div>
        </CardBody>
      </Card>

      {asking && (
        <ConfirmDialog
          title="Reconnect and run this phase again?"
          confirmLabel="Reconnect & re-run"
          cancelLabel="Not now"
          busy={takeOver.isPending || retry.isPending}
          error={takeOver.isError ? takeOver.error : undefined}
          errorFallback="The phase could not be started."
          onClose={() => setAsking(false)}
          onConfirm={() => {
            setAsking(false);
            handleResume();
          }}
        >
          <p className="u-body">
            This hands the task back to your machine and starts{" "}
            {phaseLabel(parkedRun.agent_phase ?? parkedRun.agent_key)} again from the beginning.
            Your earlier answers are kept.
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
function OfflineTakeoverGallery({ view }: { view: TakeoverView }) {
  return (
    <div className="canvas-pad" style={{ maxWidth: "880px" }}>
      <Breadcrumb items={[{ label: "Phases & Runs", href: "/runs" }, "Recovery"]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Run recovery — WI-492 · Architecture</h1>
          <p className="page-head__sub">
            When your machine goes offline mid-run, the platform parks the run for takeover rather
            than letting it hang.
          </p>
        </div>
      </div>

      <Card>
        <CardBody className="u-stack">
          {view === "parked" && (
            <>
              <Banner variant="danger" title="Your machine went offline — this run is parked for takeover">
                RUN-42 was running on <strong>Sarah's MacBook</strong>, last seen 6m ago. Nothing was
                lost: no artifact is published, and any answered clarifications are remembered.
              </Banner>
              <Kv
                rows={[
                  ["Run", "RUN-42 · Architecture · WI-492"],
                  ["Parked at", "10:47 · after report timeout"],
                  ["Answered clarifications", "1 remembered (won't be re-asked)"],
                ]}
              />
              <Banner variant="info">
                Reconnect your machine and re-run — the phase resumes from a clean dispatch, folding
                in your earlier answers.
              </Banner>
              <div className="gate-panel__actions">
                <Link to="/connect" className="btn btn--primary">
                  Reconnect & re-run
                </Link>
                <Button variant="secondary">Reassign to another machine</Button>
              </div>
            </>
          )}

          {view === "reconnecting" && (
            <>
              <div className="conn-status conn-status--waiting">
                <Spinner /> Reconnecting Sarah's MacBook… waiting for check-in
              </div>
              <p className="t-sm u-muted">
                Once your companion is back online, re-running will pick up the parked work.
              </p>
            </>
          )}

          {view === "resumed" && (
            <>
              <Banner variant="success" title="Run resumed">
                RUN-43 dispatched to Sarah's MacBook. Your previously answered clarification ("CSV
                export in v1? → Yes") was folded in automatically.
              </Banner>
              <div className="gate-panel__actions">
                <Link to="/runs/RUN-43" className="btn btn--primary">
                  View run console
                </Link>
              </div>
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
