import { useEffect, useRef } from "react";
import { Link, useLocation } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, Button, Card, CardBody, ConnStatus, EmptyState, ErrorState, Kv, Panel, Spinner, Tile, Todo } from "../../components/ui";
import { roleLabel } from "../identity/roles";
import { gateLabel, phaseLabel, statusLabel } from "../lifecycle/phases";
import { useDashboard } from "./hooks";
import { clarificationLink, gateLink } from "../../links";

// S-31 view states: busy (default) · calm · new-project.
export type DashboardView = "busy" | "calm" | "new-project";

/** "Good morning" before 12, "Good afternoon" until 5 PM, "Good evening" after — by the viewer's
 *  own clock (team-approved 2026-10-09; it said "Good morning" at every hour). */
export function greeting(now: Date = new Date()): string {
  const h = now.getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export function Dashboard({ forceView }: { forceView?: DashboardView }) {
  if (forceView) return <DashboardGallery view={forceView} />;
  return <DashboardLive />;
}

// The subtitle under the "needs you" tiles — the team's option A for S.No 222: say how many,
// plainly. It used to read the required role off whichever gate came FIRST, which could name a
// role the reader does not hold. A count is true for everyone who reads it, and zero is a real
// answer, said as one.
function waitingOnYou(count: number): string {
  return count > 0 ? `${count} waiting on you` : "nothing waiting on you";
}

/** Names the work item a queue row is about, the way the rest of the product names it (P2).
 *
 * Every row here used to identify its work item by the first eight characters of an internal id
 * — "Merge gate · 3f2a9c1b" — on the first screen a client reads each morning. That string
 * matches nothing they can search for, quote in a meeting, or recognise anywhere else, and the
 * run rows printed one twice. The number and title now travel with each row; an older API sends
 * neither, and then the row simply carries no name rather than an unreadable one.
 */
function itemName(row: { work_item_key?: string; work_item_title?: string }): string {
  return [row.work_item_key, row.work_item_title].filter(Boolean).join(" ") || "a work item";
}

/** "6m · " — how long a run has been going, in place of its own id. Under a minute reads as
 *  "just started", because "0m" says nothing. */
function runAge(run: { started_s?: number }): string {
  if (run.started_s === undefined) return "";
  const minutes = Math.floor(run.started_s / 60);
  return minutes < 1 ? "just started · " : `started ${minutes}m ago · `;
}

// ── Live: the real needs-me rollup + health for the selected project ───────
function DashboardLive() {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const dashboard = useDashboard(projectId);
  const location = useLocation();
  const needsRef = useRef<HTMLDivElement>(null);
  const loaded = Boolean(projectId) && dashboard.isSuccess;

  // N2: the topbar bell lands HERE — on the queue, not the top of the page. Focus moves with the
  // scroll, so a keyboard or screen-reader user arrives where a sighted one does. Keyed on the
  // navigation as well, so pressing the bell while already on the dashboard still brings the
  // queue back into view.
  useEffect(() => {
    if (!loaded || location.hash !== "#needs-me") return;
    const queue = needsRef.current;
    if (!queue) return;
    queue.scrollIntoView?.({ block: "start", behavior: "smooth" });
    queue.focus({ preventScroll: true });
  }, [loaded, location.hash, location.key]);

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

  // S.No 220: a failed request produces an empty rollup, and every branch below reads an empty
  // rollup as "you are all caught up". Say which it was, before anything else renders.
  if (dashboard.isError) {
    return (
      <div className="canvas-pad">
        <ErrorState
          title="We couldn't load your dashboard"
          detail={dashboard.error}
          onRetry={() => void dashboard.refetch()}
        />
      </div>
    );
  }

  const data = dashboard.data;
  const gates = data?.needs_me.gates ?? [];
  const clars = data?.needs_me.clarifications ?? [];
  const runs = data?.needs_me.my_runs ?? [];
  // The TRUE totals (S.No 222). The lists above are filtered to this person and trimmed — gates
  // and questions to 20 — so their lengths under-reported a busy project, on the one figure that
  // has to be right. The lengths remain as the fallback for an API too old to send totals.
  const counts = data?.needs_me.counts;
  const gateTotal = counts?.gates ?? gates.length;
  const clarTotal = counts?.clarifications ?? clars.length;
  const runTotal = counts?.my_runs ?? runs.length;
  const needsCount = gateTotal + clarTotal + runTotal;

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">
            {needsCount > 0 ? `${greeting()} — here's what needs you` : greeting()}
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
        <Tile num={gateTotal} label="Gates need your approval" sub={waitingOnYou(gateTotal)} />
        <Tile num={clarTotal} label="Questions awaiting you" sub={waitingOnYou(clarTotal)} />
        <Tile num={runTotal} label="My runs in flight" sub={runs.length > 0 ? `${runs.filter((r) => r.status === "running").length} running` : "none"} />
      </div>

      <div className="grid grid--detail">
        {/* The bell's landing place (N2). A plain wrapper rather than an `id` on Panel, so the
            shared component is untouched; `display: grid` keeps the panel stretching to the row
            exactly as it did when it was the grid item itself. */}
        <div id="needs-me" ref={needsRef} tabIndex={-1} className="needs-me">
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
                  title={`${gateLabel(g.gate)} · ${itemName(g)}`}
                  meta={`required role: ${roleLabel(g.role)}`}
                  action={
                    // N2: the rollup already carries the approval id. "Review" beside a NAMED
                    // gate that opened the whole gates list — and then selected `pending[0]` —
                    // is how a reviewer ends up deciding a different gate to the one they read.
                    <Link to={gateLink(g.approval_id)} className="btn btn--primary btn--sm">
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
                  title={`Question · ${itemName(c)}`}
                  meta={`"${c.question}" · waiting ${Math.round(c.waiting_s / 60)}m`}
                  action={
                    // Same shape, and worse consequence: the question's own text is printed
                    // directly above this button, and the destination showed `pending[0]`.
                    <Link to={clarificationLink(c.id)} className="btn btn--secondary btn--sm">
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
                  title={`${phaseLabel(r.phase)} run · ${itemName(r)}`}
                  meta={`${runAge(r)}${statusLabel(r.status)}`}
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
        </div>

        {/* Bugs S.No 171: the companion status lives in the top bar only — the separate
            Companion card was removed from the dashboard. */}
        <div className="u-stack">
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
              {view === "busy" ? `${greeting()} — here's what needs you` : greeting()}
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
            <Tile num={2} label="Gates need your approval" sub={waitingOnYou(2)} />
            <Tile num={1} label="Question awaiting you" sub={waitingOnYou(1)} />
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
            <Tile num={0} label="Gates need you" sub={waitingOnYou(0)} />
            <Tile num={0} label="Questions awaiting you" sub={waitingOnYou(0)} />
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
