import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Banner, Breadcrumb, Button, Card, CardBody, EmptyState, Kv, Panel, Spinner } from "../../components/ui";
import { useRuns, useTriggerPhase, useWorkItem } from "../lifecycle/hooks";
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
  const parkedRun = runIdParam
    ? undefined
    : (runs.data ?? []).find((r) => r.status === "failed");

  const runId = runIdParam ?? parkedRun?.id;
  const workItem = useWorkItem(parkedRun?.work_item);
  const takeOver = useTakeOverRun();
  const retry = useTriggerPhase(parkedRun?.work_item);

  if (!runIdParam && runs.isLoading) {
    return (
      <div className="canvas-pad" style={{ maxWidth: "880px" }}>
        <Panel>
          <Spinner /> Checking for parked runs…
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
          retry.mutate(parkedRun.agent_spec, {
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
            Run recovery — {workItem.data?.title || parkedRun.work_item.slice(0, 8)} · {parkedRun.agent_spec}
          </h1>
          <p className="page-head__sub">
            When your machine goes offline mid-run, the platform parks the run for takeover rather
            than letting it hang.
          </p>
        </div>
      </div>

      <Card>
        <CardBody className="u-stack">
          <Banner variant="danger" title="This run is parked for takeover">
            {parkedRun.id} did not report back. Nothing was lost: no artifact is published, and any
            answered clarifications are remembered.
          </Banner>
          <Kv
            rows={[
              ["Run", `${parkedRun.id} · ${parkedRun.agent_spec} · ${parkedRun.work_item.slice(0, 8)}`],
              ["Status", parkedRun.status],
              ["Created", parkedRun.created_at],
            ]}
          />
          <Banner variant="info">
            Reconnect your companion and re-run — the phase resumes from a clean dispatch, folding
            in your earlier answers.
          </Banner>
          {takeOver.isError && (
            <Banner variant="danger" title="Couldn't update takeover state">
              {takeOver.error instanceof Error ? takeOver.error.message : "Unknown error"}
            </Banner>
          )}
          <div className="gate-panel__actions">
            <Button variant="primary" onClick={handleResume} disabled={takeOver.isPending || retry.isPending}>
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
