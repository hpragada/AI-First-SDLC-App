import { Link } from "react-router-dom";

import { Banner, Breadcrumb, Button, Card, CardBody, ConnStatus, Console, Kv, Spinner } from "../../components/ui";

// S-32 view states: parked · reconnecting · resumed.
export type TakeoverView = "parked" | "reconnecting" | "resumed";

export function OfflineTakeover({ forceView }: { forceView?: TakeoverView }) {
  const view: TakeoverView = forceView ?? "parked";

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
              <ConnStatus state="waiting">
                <Spinner /> Reconnecting Sarah's MacBook… waiting for check-in
              </ConnStatus>
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
              <Console
                lines={[
                  <span key="1">
                    <span className="console__ts">10:52:01</span>
                    <span className="info">Re-dispatched. Companion claimed RUN-43.</span>
                  </span>,
                  <span key="2">
                    <span className="console__ts">10:52:04</span>Applying remembered answers…{" "}
                    <span className="ok">[OK]</span>
                  </span>,
                  <span key="3">
                    <span className="console__ts">10:52:18</span>Resuming Architecture phase…{" "}
                    <span className="console__cursor" />
                  </span>,
                ]}
              />
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
