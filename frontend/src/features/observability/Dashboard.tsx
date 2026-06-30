import { Link } from "react-router-dom";

import { Badge, Button, Card, CardBody, ConnStatus, EmptyState, Kv, Panel, Tile, Todo } from "../../components/ui";

// S-31 view states: busy (default) · calm · new-project.
export type DashboardView = "busy" | "calm" | "new-project";

export function Dashboard({ forceView }: { forceView?: DashboardView }) {
  const view: DashboardView = forceView ?? "busy";

  return (
    <div className="canvas-pad">
      {(view === "busy" || view === "calm") && (
        <div className="page-head">
          <div className="page-head__titles">
            <h1 className="t-h1">
              {view === "busy" ? "Good morning — here's what needs you" : "Good morning"}
            </h1>
            <p className="page-head__sub">
              Payment Gateway v2 · your runs, gates, and questions in one place.
            </p>
          </div>
          <span className="u-row-tight">
            <Button variant="secondary">Trigger phase</Button>
            <Button variant="primary">+ New Work Item</Button>
          </span>
        </div>
      )}

      {view === "busy" && (
        <>
          <div className="grid grid--3" style={{ marginBottom: "var(--space-5)" }}>
            <Tile num={2} label="Gates need your approval" sub="required role: architect" />
            <Tile num={1} label="Question awaiting you" sub="$0 while waiting" />
            <Tile num={3} label="My runs in flight" sub="1 running · 2 awaiting gate" />
          </div>
          <div className="grid grid--detail">
            <Panel
              flush
              title="Needs me"
              actions={
                <Badge variant="orange" dot={false}>
                  6 items
                </Badge>
              }
            >
              <Todo
                icon="▲"
                type="gate"
                title="Architecture gate · WI-492 Stripe Webhook Integration"
                meta="required role: architect · Run #42 awaiting gate"
                action={
                  <Link to="/gates" className="btn btn--primary btn--sm">
                    Review
                  </Link>
                }
              />
              <Todo
                icon="?"
                type="clar"
                title="Question · WI-510 Analytics Dashboard PRD"
                meta='"CSV export in v1?" · waiting 6m · $0 while waiting'
                action={
                  <Link to="/clarifications" className="btn btn--secondary btn--sm">
                    Answer
                  </Link>
                }
              />
              <Todo
                icon="▶"
                type="run"
                title="Run #44 · UX Design running"
                meta="WI-487 Checkout Flow Redesign"
                action={
                  <Link to="/runs/RUN-44" className="btn btn--ghost btn--sm">
                    View
                  </Link>
                }
              />
            </Panel>

            <div className="u-stack">
              <Card>
                <CardBody>
                  <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                    Companion
                  </h3>
                  <ConnStatus state="connected">Connected — Sarah's MacBook</ConnStatus>
                  <p className="field__help">Phases run on your machine. Keep it online.</p>
                </CardBody>
              </Card>
              <Card>
                <CardBody>
                  <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                    Project health
                  </h3>
                  <Kv
                    rows={[
                      ["Work items", "18"],
                      ["Phases in progress", "3"],
                      ["Awaiting gate", "2"],
                      ["Published this week", "5"],
                    ]}
                  />
                </CardBody>
              </Card>
              <Card>
                <CardBody>
                  <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                    Recent publishes
                  </h3>
                  <div className="u-stack" style={{ ["--space-4" as string]: "8px" }}>
                    <div className="u-row-tight">
                      <Badge variant="done">Published</Badge>
                      <span className="t-sm">PRD: Stripe Webhook v1.2</span>
                    </div>
                    <div className="u-row-tight">
                      <Badge variant="done">Published</Badge>
                      <span className="t-sm">Multi-Currency Requirements</span>
                    </div>
                  </div>
                </CardBody>
              </Card>
            </div>
          </div>
        </>
      )}

      {view === "calm" && (
        <>
          <div className="grid grid--3" style={{ marginBottom: "var(--space-5)" }}>
            <Tile num={0} label="Gates need you" sub="all clear" />
            <Tile num={0} label="Questions awaiting you" sub="all answered" />
            <Tile num={1} label="My runs in flight" sub="1 running" />
          </div>
          <Panel title="Needs me">
            <EmptyState
              title="You're all caught up"
              text="No gates or questions need you right now. Trigger a phase or start a new work item."
              action={
                <span className="u-row-tight">
                  <Button variant="secondary">Trigger phase</Button>
                  <Button variant="primary">+ New Work Item</Button>
                </span>
              }
            />
          </Panel>
        </>
      )}

      {view === "new-project" && (
        <div className="grid grid--detail">
          <Panel title="Get started">
            <div className="vstep vstep--done">
              <span className="vstep__num">✓</span>
              <div className="vstep__body">
                <div className="vstep__title">Create your first project</div>
                <div className="vstep__desc">Payment Gateway v2 created.</div>
              </div>
            </div>
            <div className="vstep vstep--active">
              <span className="vstep__num">2</span>
              <div className="vstep__body">
                <div className="vstep__title">Connect your machine</div>
                <div className="vstep__desc">Phases run on your computer.</div>
                <div className="gate-panel__actions" style={{ marginTop: "var(--space-2)" }}>
                  <Link to="/connect" className="btn btn--primary btn--sm">
                    Connect
                  </Link>
                </div>
              </div>
            </div>
            <div className="vstep">
              <span className="vstep__num">3</span>
              <div className="vstep__body">
                <div className="vstep__title">Invite your team & assign roles</div>
                <div className="vstep__desc">So gates have someone to decide them.</div>
              </div>
            </div>
            <div className="vstep" style={{ paddingBottom: 0 }}>
              <span className="vstep__num">4</span>
              <div className="vstep__body">
                <div className="vstep__title">Connect integrations</div>
                <div className="vstep__desc">Confluence, Jira, Figma, GitHub…</div>
              </div>
            </div>
          </Panel>
          <Card>
            <CardBody>
              <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                Companion
              </h3>
              <ConnStatus state="offline">Not connected yet</ConnStatus>
              <p className="field__help">Connect your machine to run your first phase.</p>
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}
