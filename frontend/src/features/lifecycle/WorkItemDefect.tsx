import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Badge, Banner, Breadcrumb, Button, Card, CardBody, Kv, LifecycleRail, Markdown, Panel, Spinner } from "../../components/ui";
import { runStatusLabel, runStatusTone } from "../../labels";
import { railNodeView } from "./railView";
import { phaseLabel, statusLabel, visibleLifecycleNodes } from "./phases";
import { useLifecycle, useRuns, useTriggerPhase, useWorkItem } from "./hooks";
import { isTerminalState } from "../../types";
import { CancelWorkItem } from "./CancelWorkItem";
import { EditWorkItem } from "./EditWorkItem";
import { ReopenWorkItem } from "./ReopenWorkItem";

// S-17 view states: open (default) · fixing · closed.
export type DefectView = "open" | "fixing" | "closed";

export function WorkItemDefect({ forceView }: { forceView?: DefectView }) {
  if (forceView) return <WorkItemDefectGallery view={forceView} />;
  return <WorkItemDefectLive />;
}

// ── Live: the real defect + its remediation-tier lifecycle ──────────────────
function WorkItemDefectLive() {
  const { id } = useParams();
  const workItem = useWorkItem(id);
  const lifecycle = useLifecycle(id);
  const runs = useRuns({ work_item: id });
  const trigger = useTriggerPhase(id);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [reopenOpen, setReopenOpen] = useState(false);

  if (workItem.isLoading || lifecycle.isLoading) {
    return (
      <div className="canvas-pad">
        <Panel>
          <Spinner /> Loading defect…
        </Panel>
      </div>
    );
  }

  if (!workItem.data || !id) {
    return (
      <div className="canvas-pad">
        <Panel>Work item not found.</Panel>
      </div>
    );
  }

  const latestRun = runs.data?.[0];
  const running = latestRun?.status === "running";
  // Bugs S.No 140. `=== "done"` meant a CANCELLED defect rendered a red "Open" badge and
  // offered a Trigger Fix button for work nobody intends to do. `closed` is the question these
  // three places are actually asking — "is there anything left to do here" — and `cancelled` is
  // kept separate from it because the two say opposite things to a reader.
  const cancelled = workItem.data.state === "cancelled";
  const closed = isTerminalState(workItem.data.state);
  const nodes = visibleLifecycleNodes(lifecycle.data?.nodes ?? []).map((n, i) => railNodeView(n, i));

  return (
    <div className="canvas-pad">
      <Breadcrumb
        items={[
          { label: "Work Items", href: "/work-items" },
          ...(workItem.data.parent ? [{ label: workItem.data.parent.slice(0, 8), href: `/work-items/${workItem.data.parent}` }] : []),
          id,
        ]}
      />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">{workItem.data.title || workItem.data.key || id.slice(0, 8)}</h1>
          <div className="meta-row" style={{ marginTop: "var(--space-2)" }}>
            <span className="meta-item">
              <span className="chip badge--orange">Defect</span>
            </span>
            {workItem.data.parent && (
              <span className="meta-item">
                Parent <Link to={`/work-items/${workItem.data.parent}`}>↖ {workItem.data.parent.slice(0, 8)}</Link>
              </span>
            )}
          </div>
        </div>
        {/* A cancelled defect is closed, so the block above offers it nothing — but "won't fix"
            is exactly the decision people reverse, and cancelling is the only closure there is,
            so it has to be undoable from the page where it was decided. */}
        {cancelled && (
          <span className="u-row-tight">
            <Button variant="secondary" onClick={() => setReopenOpen(true)}>
              Reopen…
            </Button>
          </span>
        )}
        {!closed && (
          <span className="u-row-tight">
            {/* S.No 76. A defect the platform raised from a test or accessibility run often has
                no description a person wrote — and this is the page where somebody adds the
                detail that makes it fixable. */}
            <Button variant="secondary" onClick={() => setEditOpen(true)}>
              Edit
            </Button>
            <Button variant="primary" disabled={trigger.isPending} onClick={() => trigger.mutate("07_implementation")}>
              {trigger.isPending ? <Spinner /> : "Trigger Fix"}
            </Button>
            {/* Bugs S.No 140. The defect page is where "we are not going to fix this" is most
                often decided — and cancelling a defect is what releases the gate it was
                holding shut, so the dialog says that before anyone commits to it. */}
            <Button variant="secondary" onClick={() => setCancelOpen(true)}>
              Won't fix…
            </Button>
          </span>
        )}
      </div>

      <Panel
        flush
        title="Lifecycle — Remediation"
        actions={
          cancelled ? <Badge variant="cancelled">Cancelled</Badge>
            : closed ? <Badge variant="done">Closed</Badge>
              : <span className="t-sm u-muted">minimal rail</span>
        }
      >
        {nodes.length === 0 ? <p className="t-sm u-muted">No phases run yet.</p> : <LifecycleRail nodes={nodes} />}
      </Panel>

      <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
        <div className="u-stack">
          {/* The state is a LABEL; the description is a DOCUMENT. This used to put the whole
              description inside the coloured alert that carried the state — as plain text, so an
              accessibility defect (which the platform writes as structured markdown: what was
              found, the screen, the element, the confidence, the evidence, the suggested fix)
              arrived as one unbroken paragraph with its asterisks and backticks showing. The
              most useful line on the ticket, the suggested fix, was buried in the middle of it.

              Every other work item in the platform renders its description properly
              (`WorkItemTask`, `WorkItemEpic`); this screen was the one that did not. So the
              state moves to a one-line strip beside the panel title, where a state belongs, and
              the description is rendered as what it is. */}
          <Panel
            title="Description"
            actions={
              <Badge variant={cancelled ? "cancelled" : closed ? "done" : running ? "running" : "failed"}>
                {cancelled ? "Cancelled"
                  : closed ? "Closed"
                    : running ? "Fix running on your companion" : "Open"}
              </Badge>
            }
          >
            {workItem.data.description ? (
              <Markdown className="prose md-body">{workItem.data.description}</Markdown>
            ) : (
              <p className="t-body u-muted">
                {cancelled
                  ? "This defect was cancelled — nobody is going to fix it. The reason is on the work item's history."
                  : closed
                    ? "This defect was closed by a clean re-run."
                    : running
                      ? "Fixing…"
                      : "No description yet."}
              </p>
            )}
          </Panel>
          {/* Screen Words group 4. The badge below was green for every status except `running`,
              so a FAILED run and a completed one read alike, and it printed the stored word.
              Both the words and the colour now come from the shared map. */}
          {latestRun && (
            <Panel title="Latest run" actions={<Badge variant={runStatusTone(latestRun.status)}>{runStatusLabel(latestRun.status)}</Badge>}>
              <Kv rows={[["Phase", phaseLabel(latestRun.agent_phase ?? latestRun.agent_key)]]} />
              <Link to={`/runs/${latestRun.id}`} className="t-sm">
                View run console ↗
              </Link>
            </Panel>
          )}
        </div>
        <Card>
          <CardBody>
            <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
              At a glance
            </h3>
            <Kv
              rows={[
                ["Parent", workItem.data.parent?.slice(0, 8) ?? "—"],
                ["Status", statusLabel(workItem.data.state)],
              ]}
            />
          </CardBody>
        </Card>
      </div>

      {cancelOpen && (
        <CancelWorkItem workItem={workItem.data} onClose={() => setCancelOpen(false)} />
      )}

      {editOpen && (
        <EditWorkItem workItem={workItem.data} onClose={() => setEditOpen(false)} />
      )}

      {reopenOpen && (
        <ReopenWorkItem workItem={workItem.data} onClose={() => setReopenOpen(false)} />
      )}
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
function WorkItemDefectGallery({ view }: { view: DefectView }) {
  const id = "WI-547";
  const nodes = {
    open: [
      { label: "Fix", state: "Open", tone: "current" as const, mark: "●" },
      { label: "Review", state: "Upcoming", tone: "upcoming" as const, mark: 2 },
      { label: "Test", state: "Upcoming", tone: "upcoming" as const, mark: 3 },
    ],
    fixing: [
      { label: "Fix", state: "Running", tone: "running" as const, mark: "" },
      { label: "Review", state: "Upcoming", tone: "upcoming" as const, mark: 2 },
      { label: "Test", state: "Upcoming", tone: "upcoming" as const, mark: 3 },
    ],
    closed: [
      { label: "Fix", state: "Patched", tone: "done" as const, mark: "✓" },
      { label: "Review", state: "Clean", tone: "done" as const, mark: "✓" },
      { label: "Test", state: "Passing", tone: "done" as const, mark: "✓" },
    ],
  }[view];

  return (
    <div className="canvas-pad">
      <Breadcrumb
        items={[
          { label: "Work Items", href: "/work-items" },
          { label: "WI-540", href: "/work-items/WI-540" },
          id,
        ]}
      />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Signature check rejects valid test events</h1>
          <div className="meta-row" style={{ marginTop: "var(--space-2)" }}>
            <span className="meta-item">
              <span className="chip badge--orange">Defect</span>
            </span>
            <span className="meta-item">
              Parent <strong>↖ WI-540 Verify Stripe signing secret</strong>
            </span>
            <span className="meta-item">
              From <strong>Testing run #61</strong>
            </span>
          </div>
        </div>
        <Button variant="primary">Trigger Fix</Button>
      </div>

      <Panel
        flush
        title="Lifecycle — Remediation"
        actions={
          view === "closed" ? (
            <Badge variant="done">Closed</Badge>
          ) : (
            <span className="t-sm u-muted">minimal rail</span>
          )
        }
      >
        <LifecycleRail nodes={nodes} />
      </Panel>

      {view === "open" && (
        <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
          <div className="u-stack">
            <Panel title="Originating finding">
              <Banner variant="danger" title="FAIL · webhook.signature.valid_test_event">
                Valid Stripe test-mode events are rejected by the signature check. Opened
                automatically from Testing run #61, traced to the test case.
              </Banner>
            </Panel>
          </div>
          <Card>
            <CardBody>
              <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                At a glance
              </h3>
              <Kv
                rows={[
                  ["Parent task", "WI-540"],
                  ["Epic", "WI-492"],
                  ["Severity", "High"],
                  ["Status", "Open"],
                ]}
              />
            </CardBody>
          </Card>
        </div>
      )}

      {view === "fixing" && (
        <div style={{ marginTop: "var(--space-5)" }}>
          <Panel title="Run console · Fix" actions={<Badge variant="running">Running on your companion</Badge>}>
            <p className="t-sm u-muted">Patching signature tolerance for test-mode events…</p>
          </Panel>
        </div>
      )}

      {view === "closed" && (
        <div style={{ marginTop: "var(--space-5)" }}>
          <Panel>
            <Banner variant="success" title="Defect closed automatically">
              Testing re-run #63 passed <code className="t-mono">webhook.signature.valid_test_event</code>.
              WI-540 is unblocked for the Merge gate.
            </Banner>
          </Panel>
        </div>
      )}
    </div>
  );
}
