import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { useRunners } from "../identity/hooks";
import { Badge, Button, Card, CardBody, ConnStatus, EmptyState, Kv, Panel, Spinner, Tile, Todo } from "../../components/ui";
import { roleLabel } from "../identity/roles";
import { phaseLabel } from "../lifecycle/phases";
import { useDashboard } from "./hooks";

// S-31 view states: busy (default) · calm · new-project.
export type DashboardView = "busy" | "calm" | "new-project";

export function Dashboard({ forceView }: { forceView?: DashboardView }) {
  if (forceView) return <DashboardGallery view={forceView} />;
  return <DashboardLive />;
}

// ── Live: the real needs-me rollup + health for the selected project ───────
function DashboardLive() {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const dashboard = useDashboard(projectId);
  const runners = useRunners();

  if (!projectId) {
    return <DashboardGallery view="new-project" />;
  }

  if (dashboard.isLoading) {
    return (
      <div className="canvas-pad">
        <Panel>
          <Spinner /> Loading dashboard…
        </Panel>
      </div>
    );
  }

  const data = dashboard.data;
  const gates = data?.needs_me.gates ?? [];
  const clars = data?.needs_me.clarifications ?? [];
  const runs = data?.needs_me.my_runs ?? [];
  const needsCount = gates.length + clars.length + runs.length;
  const online = (runners.data ?? []).some((r) => r.online);
  const machine = runners.data?.find((r) => r.online)?.machine ?? runners.data?.[0]?.machine;

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">
            {needsCount > 0 ? "Good morning — here's what needs you" : "Good morning"}
          </h1>
          <p className="page-head__sub">
            {selectedProject?.project_name} · your runs, gates, and questions in one place.
          </p>
        </div>
        <span className="u-row-tight">
          <Link to="/runs" className="btn btn--secondary">
            Trigger phase
          </Link>
          <Link to="/work-items" className="btn btn--primary">
            + New Work Item
          </Link>
        </span>
      </div>

      <div className="grid grid--3" style={{ marginBottom: "var(--space-5)" }}>
        <Tile num={gates.length} label="Gates need your approval" sub={gates.length > 0 ? `required role: ${roleLabel(gates[0].role)}` : "all clear"} />
        <Tile num={clars.length} label="Questions awaiting you" sub={clars.length > 0 ? "$0 while waiting" : "all answered"} />
        <Tile num={runs.length} label="My runs in flight" sub={runs.length > 0 ? `${runs.filter((r) => r.status === "running").length} running` : "none"} />
      </div>

      <div className="grid grid--detail">
        <Panel
          flush
          title="Needs me"
          actions={
            <Badge variant="orange" dot={false}>
              {needsCount} items
            </Badge>
          }
        >
          {needsCount === 0 ? (
            <EmptyState
              title="You're all caught up"
              text="No gates or questions need you right now. Trigger a phase or start a new work item."
              action={
                <span className="u-row-tight">
                  <Link to="/runs" className="btn btn--secondary">
                    Trigger phase
                  </Link>
                  <Link to="/work-items" className="btn btn--primary">
                    + New Work Item
                  </Link>
                </span>
              }
            />
          ) : (
            <>
              {gates.map((g) => (
                <Todo
                  key={g.approval_id}
                  icon="▲"
                  type="gate"
                  title={`${phaseLabel(g.gate)} gate · ${g.work_item.slice(0, 8)}`}
                  meta={`required role: ${roleLabel(g.role)}`}
                  action={
                    <Link to="/gates" className="btn btn--primary btn--sm">
                      Review
                    </Link>
                  }
                />
              ))}
              {clars.map((c) => (
                <Todo
                  key={c.id}
                  icon="?"
                  type="clar"
                  title={`Question · ${c.work_item.slice(0, 8)}`}
                  meta={`"${c.question}" · waiting ${Math.round(c.waiting_s / 60)}m · $0 while waiting`}
                  action={
                    <Link to="/clarifications" className="btn btn--secondary btn--sm">
                      Answer
                    </Link>
                  }
                />
              ))}
              {runs.map((r) => (
                <Todo
                  key={r.run_id}
                  icon="▶"
                  type="run"
                  title={`Run ${r.run_id.slice(0, 8)} · ${phaseLabel(r.phase)}`}
                  meta={`${r.work_item.slice(0, 8)} · ${r.status}`}
                  action={
                    <Link to={`/runs/${r.run_id}`} className="btn btn--ghost btn--sm">
                      View
                    </Link>
                  }
                />
              ))}
            </>
          )}
        </Panel>

        <div className="u-stack">
          <Card>
            <CardBody>
              <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                Companion
              </h3>
              <ConnStatus state={online ? "connected" : "offline"}>
                {online ? `Connected — ${machine ?? "your machine"}` : "Not connected"}
              </ConnStatus>
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
                  ["Work items", String(data?.health.work_items ?? 0)],
                  ["Phases in progress", String(data?.health.phases_in_progress ?? 0)],
                  ["Awaiting gate", String(data?.health.awaiting_gate ?? 0)],
                  ["Published this week", String(data?.health.published_week ?? 0)],
                ]}
              />
            </CardBody>
          </Card>
          <Card>
            <CardBody>
              <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                Recent publishes
              </h3>
              {(data?.recent_publishes ?? []).length === 0 ? (
                <p className="t-sm u-muted">Nothing published yet.</p>
              ) : (
                <div className="u-stack" style={{ ["--space-4" as string]: "8px" }}>
                  {data!.recent_publishes.map((p, i) => (
                    <div className="u-row-tight" key={i}>
                      <Badge variant="done">Published</Badge>
                      <span className="t-sm">{p.title}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
function DashboardGallery({ view }: { view: DashboardView }) {
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
            <div className="vstep vstep--active">
              <span className="vstep__num">1</span>
              <div className="vstep__body">
                <div className="vstep__title">Create your first project</div>
                <div className="vstep__desc">Greenfield or brownfield — this is where work items live.</div>
                <div className="gate-panel__actions" style={{ marginTop: "var(--space-2)" }}>
                  <Link to="/projects/new" className="btn btn--primary btn--sm">
                    Create a project
                  </Link>
                </div>
              </div>
            </div>
            <div className="vstep">
              <span className="vstep__num">2</span>
              <div className="vstep__body">
                <div className="vstep__title">Connect your machine</div>
                <div className="vstep__desc">Phases run on your computer.</div>
                <div className="gate-panel__actions" style={{ marginTop: "var(--space-2)" }}>
                  <Link to="/connect" className="btn btn--secondary btn--sm">
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
