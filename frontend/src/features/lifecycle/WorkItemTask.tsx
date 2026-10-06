import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  Badge,
  Banner,
  Breadcrumb,
  Button,
  Card,
  CardBody,
  ConfirmDialog,
  Kv,
  LifecycleRail,
  Markdown,
  Modal,
  Panel,
  Spinner,
} from "../../components/ui";
import { CancelWorkItem } from "./CancelWorkItem";
import { EditWorkItem } from "./EditWorkItem";
import { ReopenWorkItem } from "./ReopenWorkItem";
import { countCell } from "./glance";
import { railNodeView } from "./railView";
import { gateLabel, phaseLabel, statusLabel, visibleLifecycleNodes } from "./phases";
import { useCompanionGate } from "../identity/CompanionGate";
import { useApprovals, useClarifications, useDecideApproval, useLifecycle, usePatchWorkItem, useRuns, useTriggerPhase, useWorkItem } from "./hooks";
import { artifactLink, artifactsForWorkItem, clarificationsForWorkItem, gateLink } from "../../links";
import { useArtifactPreview } from "../observability/hooks";
import { repoRoleLabel, workItemTypeLabel } from "../../labels";
import { roleLabel } from "../identity/roles";
import { useRepositories } from "../setup/hooks";
import { dispatchUnclaimed } from "../../types";
import type { WorkItemCard } from "../../types";

// ── The test case itself, read from the artifact the work item points at ────
// Deliberately a pointer, not a copy: the artifact is the source of truth (#1/#3), it is the
// same text 09b reads when it writes the script, and it cannot drift when Testing re-runs.
function TestCasePanel({ artifactId }: { artifactId: string }) {
  const preview = useArtifactPreview(artifactId);
  const link = <Link to={artifactLink(artifactId)} className="t-sm">View artifact</Link>;
  return (
    <Panel title="Test case" actions={link}>
      {preview.isLoading ? (
        <p className="t-body u-muted">
          <Spinner /> Loading the test case…
        </p>
      ) : preview.data?.body ? (
        <Markdown className="prose md-body">{preview.data.body}</Markdown>
      ) : (
        // Never silently blank: say the case could not be read and offer the artifact, so an
        // unreadable body is visibly different from a case with nothing in it.
        <p className="t-body u-muted">This test case could not be read. {link}</p>
      )}
    </Panel>
  );
}

// S-16 view states: review-loop+test-failed (default) · implementation-running ·
// merge-gate · done.
export type TaskView = "loop-failed" | "running" | "merge-gate" | "done";

export function WorkItemTask({ forceView }: { forceView?: TaskView }) {
  if (forceView) return <WorkItemTaskGallery view={forceView} />;
  return <WorkItemTaskLive />;
}

// ── Live: the real task + its build-tier lifecycle ──────────────────────────
function WorkItemTaskLive() {
  const { id } = useParams();
  const workItem = useWorkItem(id);
  const lifecycle = useLifecycle(id);
  const approvals = useApprovals({ work_item: id, decision: "pending" });
  // A task's phases can stop to ask a question exactly as a planning phase can — clarifications
  // attach to whatever work item the run belongs to, with no restriction by type.
  const clarifications = useClarifications({ work_item: id, status: "pending" });
  const runs = useRuns({ work_item: id });
  const decideApproval = useDecideApproval();
  const trigger = useTriggerPhase(id);
  // Scoped to the work item's own project, not the project switcher: this page is reachable
  // by direct link from anywhere.
  const companionGate = useCompanionGate(workItem.data?.project);
  // Confirm before re-triggering implementation when a run already exists (Bugs S.No 77):
  // in progress → blocked; already run → restart & replace this phase's artifacts.
  // "first" is the case that used to start a build on one click with nothing asked. "active" is a
  // refusal, not a confirmation, which is why it keeps a plain Modal.
  const [confirm, setConfirm] = useState<{ kind: "first" | "rerun" | "active"; runId?: string } | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [reopenOpen, setReopenOpen] = useState(false);

  const handleImplTrigger = () => {
    const prior = runs.data?.[0];
    const active = ["pending", "running", "awaiting_gate", "approved"];
    if (prior && active.includes(prior.status)) {
      setConfirm({ kind: "active", runId: prior.id });
    } else if (prior) {
      setConfirm({ kind: "rerun", runId: prior.id });
    } else {
      setConfirm({ kind: "first" });
    }
  };

  if (workItem.isLoading || lifecycle.isLoading) {
    return (
      <div className="canvas-pad">
        <Panel>
          <Spinner /> Loading task…
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

  const pendingGate = approvals.data?.[0];
  const latestRun = runs.data?.[0];
  const running = latestRun?.status === "running";
  // A badge must not assert a machine is working when it isn't. "Running on your companion" was
  // printed from run status alone, so a phase dispatched to a dead machine advertised itself as
  // running on it — the same false claim the run console was making, one screen along.
  const strandedRun = Boolean(
    latestRun && dispatchUnclaimed(latestRun.inputs) && companionGate.blocked);
  const done = workItem.data.state === "done";
  // Bugs S.No 140. Kept separate from `done`: they are different facts and the screen says
  // different things about each.
  const cancelled = workItem.data.state === "cancelled";
  const nodes = visibleLifecycleNodes(lifecycle.data?.nodes ?? []).map((n, i) => railNodeView(n, i));
  const loops = lifecycle.data?.loops ?? [];
  // A test case's steps live in the artifact it points at, never on the work item, so the
  // Description panel had nothing to show and said "No description yet" on every auto-created
  // case. Read the case from its artifact instead — test cases only; every other type keeps
  // the ordinary Description panel.
  const testCaseArtifactId =
    workItem.data.type === "test_case"
      ? workItem.data.external_ref?.test_case_artifact_id
      : undefined;

  return (
    <div className="canvas-pad">
      {/* Both crumbs used to be UUIDs — the parent's first eight characters, and the route id in
          full. `WorkItemSerializer.key` exists with the comment "so the UI never has to show the
          UUID"; this screen showed it anyway, on the line above the title. The parent crumb is
          dropped entirely rather than shown unnamed: a crumb reading "↖ 65db8214" tells a reader
          nothing and costs them a click to find out. */}
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
              <span className="chip">Task</span>
            </span>
            {workItem.data.parent && workItem.data.parent_key && (
              <span className="meta-item">
                Parent <Link to={`/work-items/${workItem.data.parent}`}>↖ {workItem.data.parent_key}</Link>
              </span>
            )}
            {workItem.data.owner && (
              <span className="meta-item">
                Owner <strong>{workItem.data.owner}</strong>
              </span>
            )}
          </div>
        </div>
        <span className="u-row-tight">
          {/* Cancelling is the platform's only closure, so it has to be undoable — this is the
              one control a cancelled task offers, in the slot the live ones use for Edit. */}
          {cancelled && (
            <Button variant="secondary" onClick={() => setReopenOpen(true)}>
              Reopen…
            </Button>
          )}
          {/* Nothing to trigger on a cancelled task, and nothing left to cancel either — the
              buttons disappear together, so the page stops offering work nobody will do.
              A DONE task keeps its trigger: re-running a phase on finished work is a real
              thing people do, and that is not what this fix is about. */}
          {!cancelled && (
            <>
              {/* S.No 76 / SCREEN_BUILD_MAP S-16. A task the platform wrote in Task Breakdown
                  often arrives with a terse title and no description, and until now nobody
                  could fix one — including the person who has to build it. */}
              <Button variant="secondary" onClick={() => setEditOpen(true)}>
                Edit
              </Button>
              {/* Greyed when there is no machine to build on — this used to dispatch into a
                  run nobody could claim. The reason sits beside the button, not behind a
                  click. */}
              <Button
                variant="primary"
                disabled={trigger.isPending || companionGate.blocked}
                onClick={handleImplTrigger}
              >
                {trigger.isPending ? <Spinner /> : "Trigger phase"}
              </Button>
              {!done && (
                <Button variant="secondary" onClick={() => setCancelOpen(true)}>
                  Cancel work item…
                </Button>
              )}
            </>
          )}
        </span>
      </div>
      {/* Right-aligned, under the action row and beneath the button it is about. It used to
          render full width from the left margin while the button it explains sat at the far
          right of the row above — so the sentence read as a page-level announcement rather
          than as the reason that button is grey, and the team said so on sight (2026-10-06).
          Still OUTSIDE the row: the row is a tight horizontal strip and a sentence inside it
          would push the buttons out of line, which is why it was moved out in the first
          place. */}
      {!cancelled && companionGate.note && (
        <div style={{ marginTop: "var(--space-2)", textAlign: "right" }}>
          {companionGate.note}
        </div>
      )}

      <Panel
        flush
        title="Lifecycle — Delivery"
        // See the note on the epic's caption: a sentence about this item, not a label.
        actions={<span className="t-sm u-muted">The phases that deliver this task</span>}
      >
        {nodes.length === 0 ? (
          <p className="t-sm u-muted">No phases run yet.</p>
        ) : (
          <LifecycleRail
            nodes={nodes}
            loop={loops.length > 0 && `↺ ${loops.map((l) => `${l.from} ↔ ${l.to} ×${l.count}`).join(", ")}`}
          />
        )}
      </Panel>

      <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
        <div className="u-stack">
          {testCaseArtifactId ? (
            <TestCasePanel artifactId={testCaseArtifactId} />
          ) : (
            <Panel title="Description">
              {workItem.data.description ? (
                <Markdown className="prose md-body">{workItem.data.description}</Markdown>
              ) : (
                <p className="t-body u-muted">No description yet.</p>
              )}
            </Panel>
          )}

          {latestRun && (
            <Panel
              title="Latest run"
              actions={
                <Badge variant={
                  strandedRun ? "waiting"
                    : running ? "running"
                      : latestRun.status === "failed" ? "failed" : "done"}>
                  {strandedRun ? "Waiting for your machine"
                    : running ? "Running on your companion" : statusLabel(latestRun.status)}
                </Badge>
              }
            >
              <Kv
                rows={[
                  ["Phase", phaseLabel(latestRun.agent_phase ?? latestRun.agent_key)],
                ]}
              />
              <Link to={`/runs/${latestRun.id}`} className="t-sm">
                View run console ↗
              </Link>
            </Panel>
          )}

          {(lifecycle.data?.children.length ?? 0) > 0 && (
            <Panel title="Related work items">
              {lifecycle.data!.children.map((c) => (
                <div className="artifact-row" key={c.id}>
                  <div className="artifact-row__main">
                    <div className="artifact-row__title">{c.title || c.id.slice(0, 8)}</div>
                    {/* Screen Words group 4: `test_case` -> `Test case`. */}
                    <div className="artifact-row__meta">{workItemTypeLabel(c.type)} · {phaseLabel(c.phase)}</div>
                  </div>
                  <Link to={`/work-items/${c.id}`} className="btn btn--ghost btn--sm">
                    Open
                  </Link>
                </div>
              ))}
            </Panel>
          )}
        </div>

        <div className="u-stack">
          {pendingGate ? (
            <Card attention>
              <CardBody>
                {/* Screen Words group 3 — see the same line on the Epic screen. */}
                <span className="gate-panel__role">▲ {gateLabel(pendingGate.gate_type)} · decided by a {roleLabel(pendingGate.required_role)}</span>
                <h3 className="t-h3">Awaiting your decision</h3>
                <div className="gate-panel__actions">
                  <Button
                    variant="primary"
                    disabled={decideApproval.isPending}
                    onClick={() => decideApproval.mutate({ id: pendingGate.id, decision: "approved" })}
                  >
                    Approve
                  </Button>
                  {/* Rejecting from here sent NO comment at all — there is no box on this card,
                      so the reason was lost. The gate is where you can reject with a reason or
                      request changes and have the build actually revise. */}
                  <Link className="btn btn--secondary" to={gateLink(pendingGate.id)}>
                    Reject or request changes…
                  </Link>
                </div>
              </CardBody>
            </Card>
          ) : done ? (
            <Panel>
              <div className="toast toast--success" style={{ boxShadow: "none", maxWidth: "none" }}>
                <div>
                  <div className="toast__title">Done</div>
                  <div className="toast__body">This task is complete.</div>
                </div>
              </div>
            </Panel>
          ) : null}
          <Card>
            <CardBody>
              <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                At a glance
              </h3>
              <Kv
                rows={[
                  ["State", statusLabel(workItem.data.state)],
                  // N2: the count was inert text — the card told you there were four artifacts
                  // and left you to find them in the registry by hand.
                  [
                    "Artifacts",
                    countCell(workItem.data.artifact_count ?? 0,
                              artifactsForWorkItem(workItem.data.id)),
                  ],
                  ["Open gates", String(approvals.data?.length ?? 0)],
                  // "Open" because the query asks for pending only. Without the word, a
                  // finished work item that answered six questions reads "Clarifications 0",
                  // which says it was never asked anything.
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
          <RepoAssignmentCard workItem={workItem.data} buildStarted={Boolean(latestRun)} />
        </div>
      </div>

      {confirm && confirm.kind !== "active" && (
        <ConfirmDialog
          title={confirm.kind === "rerun" ? "Re-run implementation?" : "Start implementation?"}
          confirmLabel={confirm.kind === "rerun" ? "Re-run phase" : "Start phase"}
          cancelLabel="Not now"
          busy={trigger.isPending}
          error={trigger.isError ? trigger.error : undefined}
          errorFallback="The phase could not be started."
          onClose={() => setConfirm(null)}
          onConfirm={() =>
            trigger.mutate("07_implementation", { onSuccess: () => setConfirm(null) })
          }
        >
          <p className="u-body">
            This builds {workItem.data?.key || "this task"} on your companion — it writes code on a
            branch and opens a pull request for review. It may take several minutes.
          </p>
          {confirm.kind === "rerun" && (
            <Banner variant="warning">
              Implementation has already run for this task. Running it again starts over and
              replaces what the last run produced. The previous run stays in the history.
            </Banner>
          )}
          {confirm.kind === "first" && <p className="u-body">You can pause it at any time.</p>}
        </ConfirmDialog>
      )}

      {confirm && confirm.kind === "active" && (
        <Modal
          title="A run is already in progress"
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setConfirm(null)}>Close</Button>
              {confirm.runId && (
                <Link className="btn btn--primary" to={`/runs/${confirm.runId}`}>
                  Open current run
                </Link>
              )}
            </>
          }
        >
          <p className="u-body">
            This task already has a run <strong>in progress</strong>. You can&apos;t start a new one
            until it finishes — wait for it, or open the run to take it over.
          </p>
        </Modal>
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

      {/* No "Answered questions" panel here (team decision, 25 August). It was a full search
          box, phase filter and paging control, rendered whether or not the item had a single
          answered question — and on anything the platform created for itself (an accessibility
          defect, the accessibility backlog) there never are any, so it could only ever be an
          empty card. Nothing became unreachable: the same history, with the same search plus a
          work-item filter, is the History tab of Clarifications. */}
    </div>
  );
}

// B3 (Hybrid Option C): assign / redirect a task's target repository. Multi-repo projects only
// (single-repo has nothing to choose). Editable until the build starts. Shows the agent's plain-
// language suggestion + a "needs review" flag when its confidence was low.
function RepoAssignmentCard({ workItem, buildStarted }: { workItem: WorkItemCard; buildStarted: boolean }) {
  const repos = useRepositories(workItem.project);
  const patch = usePatchWorkItem(workItem.id);
  const list = repos.data ?? [];
  if (list.length <= 1) return null; // single-repo → no assignment choice
  const suggestion = workItem.external_ref?.repo_assignment;
  return (
    <Card>
      <CardBody>
        <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>Repository</h3>
        <label className="field" style={{ marginBottom: 0 }}>
          <span className="field__label">Target repository</span>
          <select
            className="select"
            value={workItem.repo ?? ""}
            disabled={patch.isPending || buildStarted}
            onChange={(e) => patch.mutate({ repo: e.target.value || null })}
          >
            <option value="">— default repository —</option>
            {list.map((r) => (
              // Screen Words group 4: the repository picker's role word.
              <option key={r.id} value={r.id}>
                {r.name} · {repoRoleLabel(r.role)}
              </option>
            ))}
          </select>
        </label>
        {suggestion?.rationale && (
          <p className="t-sm u-muted" style={{ marginTop: "var(--space-2)" }}>
            {suggestion.confidence === "low" ? "⚠ Needs review — " : ""}
            Suggested by the planner: {suggestion.rationale}
          </p>
        )}
        <p className="t-xs u-faint" style={{ marginTop: "var(--space-2)" }}>
          {buildStarted ? "Locked — the build has started." : "You can redirect this task until its build starts."}
        </p>
      </CardBody>
    </Card>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
function WorkItemTaskGallery({ view }: { view: TaskView }) {
  const id = "WI-540";
  const nodes = {
    "loop-failed": [
      { label: "Implementation", state: "PR #218", tone: "done" as const, mark: "✓" },
      { label: "Review", state: "Clean", tone: "done" as const, mark: "✓" },
      { label: "Test", state: "Defect WI-547", tone: "failed" as const, mark: "!" },
      { label: "Merge", state: "Not started", tone: "upcoming" as const, mark: 4 },
    ],
    running: [
      { label: "Implementation", state: "Running", tone: "running" as const, mark: "" },
      { label: "Review", state: "Not started", tone: "upcoming" as const, mark: 2 },
      { label: "Test", state: "Not started", tone: "upcoming" as const, mark: 3 },
      { label: "Merge", state: "Not started", tone: "upcoming" as const, mark: 4 },
    ],
    "merge-gate": [
      { label: "Implementation", state: "PR #218", tone: "done" as const, mark: "✓" },
      { label: "Review", state: "Clean", tone: "done" as const, mark: "✓" },
      { label: "Test", state: "Passing", tone: "done" as const, mark: "✓" },
      { label: "Merge", state: "Gate Pending", tone: "current" as const, mark: "●" },
    ],
    done: [
      { label: "Implementation", state: "PR #218", tone: "done" as const, mark: "✓" },
      { label: "Review", state: "Clean", tone: "done" as const, mark: "✓" },
      { label: "Test", state: "Passing", tone: "done" as const, mark: "✓" },
      { label: "Merge", state: "Merged", tone: "done" as const, mark: "✓" },
    ],
  }[view];

  return (
    <div className="canvas-pad">
      <Breadcrumb
        items={[
          { label: "Work Items", href: "/work-items" },
          { label: "WI-492", href: "/work-items/WI-492" },
          id,
        ]}
      />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Verify Stripe signing secret</h1>
          <div className="meta-row" style={{ marginTop: "var(--space-2)" }}>
            <span className="meta-item">
              <span className="chip">Task</span>
            </span>
            <span className="meta-item">
              Parent <strong>↖ WI-492 Stripe Webhook Integration</strong>
            </span>
            <span className="meta-item">
              Owner <strong>Dan Ortiz</strong>
            </span>
          </div>
        </div>
        <span className="u-row-tight">
          <Button variant="secondary">Edit</Button>
          <Button variant="primary">Trigger phase</Button>
        </span>
      </div>

      <Panel
        flush
        title="Lifecycle — Delivery"
        actions={
          view !== "loop-failed" && <span className="t-sm u-muted">The phases that deliver this task</span>
        }
      >
        <LifecycleRail
          nodes={nodes}
          loop={view === "loop-failed" && "↺ Review ↔ Implementation loop ×2"}
          branch={
            view === "loop-failed" && (
              <>
                ⌐ Child defect:{" "}
                <Link to="/work-items/WI-547">WI-547 "Signature check rejects valid test events"</Link> —
                closes on clean re-run.
              </>
            )
          }
        />
      </Panel>

      {view === "running" && (
        <div style={{ marginTop: "var(--space-5)" }}>
          <Panel title="Run console" actions={<Badge variant="running">Running on your companion</Badge>}>
            <p className="t-sm u-muted">Implementing signature verification…</p>
          </Panel>
        </div>
      )}

      {view === "merge-gate" && (
        <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
          <Panel title="Lifecycle status">
            <p className="t-sm u-body">All checks pass. Approving merges the PR and completes this task.</p>
          </Panel>
          <Card attention>
            <CardBody>
              <span className="gate-panel__role">▲ Merge gate · required role: reviewer</span>
              <h3 className="t-h3">PR #218 ready to merge</h3>
              <p className="t-sm u-body">All checks pass. Approving merges the PR and completes this task.</p>
              <div className="gate-panel__actions">
                <Button variant="primary">Approve & merge</Button>
                <Button variant="secondary">Reject</Button>
              </div>
            </CardBody>
          </Card>
        </div>
      )}

      {view === "done" && (
        <div style={{ marginTop: "var(--space-5)" }}>
          <Panel>
            <div className="toast toast--success" style={{ boxShadow: "none", maxWidth: "none" }}>
              <div>
                <div className="toast__title">Merged to main</div>
                <div className="toast__body">
                  PR #218 merged · WI-540 done. Parent epic WI-492 advances when all children
                  complete.
                </div>
              </div>
            </div>
          </Panel>
        </div>
      )}

      {view === "loop-failed" && (
        <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
          <div className="u-stack">
            <Panel title="Linked pull request">
              <div className="artifact-row">
                <div className="artifact-row__main">
                  <div className="artifact-row__title">PR #218 · Verify Stripe signing secret</div>
                  <div className="artifact-row__meta">Open · acme/payments-api · base main</div>
                </div>
                <Badge variant="waiting">Open</Badge>
              </div>
            </Panel>
            <Panel title="Child defects & remediations">
              <div className="artifact-row">
                <div className="artifact-row__main">
                  <div className="artifact-row__title">Signature check rejects valid test events</div>
                  <div className="artifact-row__meta">WI-547 · from Testing run #61</div>
                </div>
                <Badge variant="failed">Open</Badge>
                <Button variant="ghost" size="sm">
                  Open
                </Button>
              </div>
            </Panel>
          </div>
          <div className="u-stack">
            <Card>
              <CardBody>
                <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                  At a glance
                </h3>
                <Kv
                  rows={[
                    ["Parent epic", "WI-492"],
                    ["Phase", "Test"],
                    ["PR", "#218 open"],
                    ["Open defects", "1"],
                  ]}
                />
              </CardBody>
            </Card>
            <Card>
              <CardBody>
                <h3 className="t-h3">Next step</h3>
                <p className="t-sm u-body">
                  Fix WI-547, then re-run Testing. A clean run closes the defect and unblocks the
                  Merge gate.
                </p>
              </CardBody>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
