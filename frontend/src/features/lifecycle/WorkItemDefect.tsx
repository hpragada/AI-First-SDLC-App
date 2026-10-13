import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Badge, Banner, Breadcrumb, Button, Card, CardBody, ConfirmDialog, Kv, LifecycleRail, Markdown, Panel, Spinner } from "../../components/ui";
import { runStatusLabel, runStatusTone } from "../../labels";
import { artifactsForWorkItem, clarificationsForWorkItem } from "../../links";
import { countCell } from "./glance";
import { railNodeView } from "./railView";
import { phaseLabel, visibleLifecycleNodes } from "./phases";
import { boardStatusLabel } from "./WorkItemsBoard";
import { useCompanionGate } from "../identity/CompanionGate";
import { useApprovals, useClarifications, useLifecycle, useRuns, useTriggerPhase, useWorkItem } from "./hooks";
import { dispatchUnclaimed, isTerminalState } from "../../types";
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
  // The same two questions the epic screen has always asked. A defect can have both: its Fix
  // runs Implementation, so it registers artifacts, can stop to ask a question, and opens a
  // merge gate against the defect itself.
  const approvals = useApprovals({ work_item: id, decision: "pending" });
  const clarifications = useClarifications({ work_item: id, status: "pending" });
  const lifecycle = useLifecycle(id);
  const runs = useRuns({ work_item: id });
  const trigger = useTriggerPhase(id);
  // The defect's own project — this page is reachable by direct link.
  const companionGate = useCompanionGate(workItem.data?.project);
  // Fixing a defect dispatches a build to the user's machine. It fired on one click.
  const [fixOpen, setFixOpen] = useState(false);
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
  // A badge must not assert a machine is working when it isn't. "Running on your companion" was
  // printed from run status alone, so a phase dispatched to a dead machine advertised itself as
  // running on it — the same false claim the run console was making, one screen along.
  const strandedRun = Boolean(
    latestRun && dispatchUnclaimed(latestRun.inputs) && companionGate.blocked);
  // Bugs S.No 140. `=== "done"` meant a CANCELLED defect rendered a red "Open" badge and
  // offered a Trigger Fix button for work nobody intends to do. `closed` is the question these
  // three places are actually asking — "is there anything left to do here" — and `cancelled` is
  // kept separate from it because the two say opposite things to a reader.
  const cancelled = workItem.data.state === "cancelled";
  const closed = isTerminalState(workItem.data.state);
  const nodes = visibleLifecycleNodes(lifecycle.data?.nodes ?? []).map((n, i) => railNodeView(n, i));

  return (
    <div className="canvas-pad">
      {/* See the note on the same breadcrumb in WorkItemTask.tsx — both crumbs were UUIDs. */}
      <Breadcrumb
        items={[
          { label: "Work Items", href: "/work-items" },
          ...(workItem.data.parent && workItem.data.parent_key
            ? [{ label: workItem.data.parent_key, href: `/work-items/${workItem.data.parent}` }]
            : []),
          workItem.data.key || "This work item",
        ]}
      />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">{workItem.data.title || workItem.data.key || id.slice(0, 8)}</h1>
          <div className="meta-row" style={{ marginTop: "var(--space-2)" }}>
            <span className="meta-item">
              <span className="chip badge--orange">Defect</span>
            </span>
            {workItem.data.parent && workItem.data.parent_key && (
              <span className="meta-item">
                Parent <Link to={`/work-items/${workItem.data.parent}`}>↖ {workItem.data.parent_key}</Link>
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
            {/* Greyed when there is no machine to run the fix on — see CompanionGate. */}
            <Button
              variant="primary"
              disabled={trigger.isPending || companionGate.blocked}
              onClick={() => setFixOpen(true)}
            >
              {trigger.isPending ? <Spinner /> : "Trigger Fix"}
            </Button>
            {/* Bugs S.No 140 put "Won't fix…" here, because the defect page is where "we are
                not going to fix this" is most often decided. It stays true, and it is still
                said — as one of the dialog's standing REASONS. What it may not do is rename
                the action: one thing a person can do to a work item had two names depending
                on which screen they were looking at (2026-10-06). The dialog still explains
                that cancelling a defect releases the gate it was holding shut. */}
            <Button variant="secondary" onClick={() => setCancelOpen(true)}>
              Cancel work item…
            </Button>
          </span>
        )}
      </div>
      {/* Right-aligned, under the action row and beneath the button it is about. It used to
          render full width from the left margin while the button it explains sat at the far
          right of the row above — so the sentence read as a page-level announcement rather
          than as the reason that button is grey, and the team said so on sight (2026-10-06).
          Still OUTSIDE the row: the row is a tight horizontal strip and a sentence inside it
          would push the buttons out of line, which is why it was moved out in the first
          place. */}
      {companionGate.note && (
        <div style={{ marginTop: "var(--space-2)", textAlign: "right" }}>
          {companionGate.note}
        </div>
      )}

      <Panel
        flush
        title="Lifecycle — Repair"
        actions={
          cancelled ? <Badge variant="cancelled">Cancelled</Badge>
            : closed ? <Badge variant="done">Closed</Badge>
              : <span className="t-sm u-muted">The phases that fix this defect</span>
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
            // This badge reports the RUN; "At a glance" reports the ITEM. They used to report
            // both, in different words — the header said "Open" while the panel beside it said
            // "Proposed", for one defect (2026-10-06). Splitting them means neither can
            // contradict the other, and this one keeps the thing the state row cannot say: that
            // a fix is on somebody's machine right now, or waiting for a machine that is gone.
            //
            // Nothing at all when the defect is simply sitting there. A badge that is always
            // present is one nobody reads; this one appears when there is news.
            actions={
              strandedRun || running ? (
                <Badge variant={strandedRun ? "waiting" : "running"}>
                  {strandedRun ? "Waiting for your machine" : "Fix running on your companion"}
                </Badge>
              ) : null
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
            {/* `parent`, not `parent_key`, printed eight characters of a raw UUID at a client
                — the exact thing `parent_key` was added to prevent, and whose own comment says
                a parent id "must never be drawn". Found in recon 2026-10-06; invisible on a
                defect raised by hand because those have no parent, and every defect the test
                loop raises does.

                Status is gone from here as well: the badge on this panel's header already
                states it, and the two disagreed in vocabulary — "Open" above, "Proposed"
                here, for one defect. The badge stays because it carries more (it knows when a
                fix is running, and when a machine is missing); this row only repeated it. */}
            {/* The same five rows as the epic and task screens, so a person moving between
                them is answering the same questions each time. Every one of these is real for
                a defect — verified 2026-10-06 rather than assumed. `parent_key`, never the
                internal id: that is what it exists for. */}
            <Kv
              rows={[
                // Mockup M9: the same words the Board and the List show for this item.
                ["State", boardStatusLabel(workItem.data)],
                [
                  "Artifacts",
                  countCell(workItem.data.artifact_count ?? 0,
                            artifactsForWorkItem(workItem.data.id)),
                ],
                ["Open gates", String(approvals.data?.length ?? 0)],
                [
                  "Open clarifications",
                  countCell(clarifications.data?.length ?? 0,
                            clarificationsForWorkItem(workItem.data.id)),
                ],
                ["Parent", workItem.data.parent_key || "—"],
              ]}
            />
          </CardBody>
        </Card>
      </div>

      {fixOpen && (
        <ConfirmDialog
          title="Start the fix?"
          confirmLabel="Start fix"
          cancelLabel="Not now"
          busy={trigger.isPending}
          error={trigger.isError ? trigger.error : undefined}
          errorFallback="The fix could not be started."
          onClose={() => setFixOpen(false)}
          onConfirm={() =>
            trigger.mutate("07_implementation", { onSuccess: () => setFixOpen(false) })
          }
        >
          <p className="u-body">
            This works on {workItem.data?.key || "this defect"} on your companion — it writes the fix
            on a branch and opens a pull request for review. It may take several minutes, and
            you&apos;ll be asked to review before anything is merged.
          </p>
          <p className="u-body">You can pause it at any time.</p>
        </ConfirmDialog>
      )}
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
      { label: "Review", state: "Not started", tone: "upcoming" as const, mark: 2 },
      { label: "Test", state: "Not started", tone: "upcoming" as const, mark: 3 },
    ],
    fixing: [
      { label: "Fix", state: "Running", tone: "running" as const, mark: "" },
      { label: "Review", state: "Not started", tone: "upcoming" as const, mark: 2 },
      { label: "Test", state: "Not started", tone: "upcoming" as const, mark: 3 },
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
        title="Lifecycle — Repair"
        actions={
          view === "closed" ? (
            <Badge variant="done">Closed</Badge>
          ) : (
            <span className="t-sm u-muted">The phases that fix this defect</span>
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
