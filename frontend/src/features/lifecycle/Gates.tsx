import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import {
  Badge,
  Banner,
  Button,
  Card,
  CardBody,
  CriteriaItem,
  CriteriaList,
  EmptyState,
  Panel,
  Spinner,
  Table,
  Tabs,
  Textarea,
  WriteError,
} from "../../components/ui";
import type { Approval } from "../../types";
import { roleLabel } from "../identity/roles";
import { Pager, PhaseFilter, WorkItemFilter } from "./HistoryControls";
import {
  useApprovalHistory,
  useApprovals,
  useDecideApproval,
  useGateCriteria,
  usePatchAnyWorkItem,
  useWorkItems,
} from "./hooks";
import { useRepositories } from "../setup/hooks";
import { RepoAssignmentReview } from "./RepoAssignmentReview";
import { gateLabel, phaseLabel } from "./phases";
import { artifactsForRun, workItemLink } from "../../links";
import { useParamState } from "../../urlState";

// S-21 view states: can-decide (your role) · cannot-decide (permission) ·
// decided-history · empty.
export type GatesView = "can-decide" | "cannot-decide" | "history" | "empty";

export function Gates({ forceView }: { forceView?: GatesView }) {
  if (forceView) return <GatesGallery view={forceView} />;
  return <GatesLive />;
}

// ── Live: real pending/decided approvals for the selected project ──────────
function GatesLive() {
  const { selectedProject, currentUser, hasRole } = useAuth();
  const projectId = selectedProject?.project_id;
  const workItems = useWorkItems(projectId);
  // Scoped SERVER-side. This used to fetch every approval and keep only those whose work item
  // appeared in `workItems` — but that list hides carrier work items on purpose, so the
  // onboarding gate vanished from this page while the sidebar badge (which doesn't cross-filter)
  // still counted it. The work-item list is for labelling; it must not decide what a gate IS.
  const approvals = useApprovals(projectId ? { project: projectId } : {});
  const decideApproval = useDecideApproval();
  const repos = useRepositories(projectId);
  const patchAny = usePatchAnyWorkItem();
  const [tab, setTab] = useState<"pending" | "history">("pending");
  const [comment, setComment] = useState("");
  // N2: `?gate=<id>` opens THAT gate. Without it, "Review the assessment" beside a named work
  // item could open a different one — worse than a bare list, because it invites the decision
  // to be made on the wrong gate.
  const [selectedId, setSelectedId, pinnedFromUrl] = useParamState("gate");
  const [satisfied, setSatisfied] = useState<Record<string, boolean>>({});
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  // The decision just made, held at PAGE level rather than in the gate panel (Bugs S.No 250).
  //
  // It used to be the mutation's own `isSuccess` that drove a confirmation banner inside the
  // panel — which meant the confirmation belonged to the button press, not to the gate. Approve
  // WI-96, and WI-96 leaves the pending list; the panel auto-selects the next gate; and the
  // banner came along with it, so WI-95's panel announced "Decision recorded" for a gate nobody
  // had decided. A reviewer working through five gates reads that and moves on, leaving it
  // pending. Naming the gate in the banner and keeping the banner OUT of any gate's panel is
  // what makes that impossible rather than merely unlikely.
  const [decided, setDecided] = useState<
    { label: string; kind: "approved" | "revised" | "rejected"; merge: boolean } | null
  >(null);

  const loading = approvals.isLoading || workItems.isLoading;
  const projectApprovals = approvals.data ?? [];
  const pending = projectApprovals.filter((a) => a.decision === "pending");
  // Decided gates are no longer derived here — GateHistory fetches them paged and filtered
  // server-side, so this screen never holds a project's entire decision history in memory.
  const selected = pending.find((a) => a.id === selectedId) ?? (pinnedFromUrl ? undefined : pending[0]);
  // A link that names a gate which is no longer pending must say so and select NOTHING.
  // Falling back to `pending[0]` here would make a stale deep link silently show the wrong
  // gate, which is the bug this fix exists to remove, re-introduced one level down.
  const staleLink = pinnedFromUrl && Boolean(selectedId) && !selected && !approvals.isLoading;

  // Bugs S.No 88. A developer merging on GitHub is a legitimate outcome — the platform observes
  // the code host, it does not police it. But the run then waited for ever for an approval of
  // something that had already happened, and this screen said nothing about it. Say it, in
  // BOTH panels: the reviewer who can decide, and everyone else who can only look.
  const externalMerge = selected?.external_merge;
  const externalMergeNotice = externalMerge ? (
    <div style={{ margin: "var(--space-3) 0 0" }}>
      <Banner variant="info" title="Already merged on GitHub">
        This pull request was merged outside the platform
        {externalMerge.merged_by ? <> by <strong>{externalMerge.merged_by}</strong></> : null}
        {externalMerge.merged_at
          ? ` on ${new Date(externalMerge.merged_at).toLocaleString()}`
          : null}
        . Nothing further will be pushed
        {externalMerge.pr_ref ? ` for ${externalMerge.pr_ref}` : null}
        {" "}— acknowledging closes out the run and publishes its artifacts.
      </Banner>
    </div>
  ) : null;

  // Some gates (e.g. the UX Design a11y gate) carry a required WCAG checklist that must be
  // satisfied before APPROVE — surface it here and send the reviewer's ticks with the decision,
  // otherwise the backend rejects the approval with "required gate condition(s) unmet".
  const criteria = useGateCriteria(selected?.id);
  const criteriaList = criteria.data?.criteria ?? [];
  useEffect(() => {
    setSatisfied(Object.fromEntries(criteriaList.map((c) => [c.id, c.satisfied])));
    // Reset when the selected gate (and thus its criteria payload) changes — deliberately not
    // on `criteriaList`, which is rebuilt each render and would wipe the reviewer's ticks.
  }, [criteria.data, selected?.id]);

  // The confirmation belongs to one decision, not to the screen. Picking another gate clears it,
  // so it cannot sit there implying something about a gate it never described.
  useEffect(() => setDecided(null), [selectedId]);

  const metCount = criteriaList.filter((c) => satisfied[c.id]).length;
  const requiredUnmet = criteriaList.some((c) => c.required && !satisfied[c.id]);

  // B2/C1 (Option C): on a multi-repo project, a Task Breakdown gate carries proposed tasks
  // each with the planner's repo suggestion — surface them for confirm/override at the gate.
  const repoList = repos.data ?? [];
  const multiRepo = repoList.length > 1;
  const assignmentItems = (workItems.data ?? []).filter(
    (w) => w.state === "proposed" && w.external_ref?.repo_assignment,
  );
  // The repo-assignment review belongs to the Task Breakdown gate ONLY. Proposed sibling tasks
  // keep their repo_assignment long after Task Breakdown, so keying purely on "multi-repo +
  // assignments exist" resurfaced this panel on the merge gate (and would on any later
  // testing/security/deployment phase gate too) — Bugs S.No 106 follow-up. Gate it on the
  // selected gate's own phase being Task Breakdown so it never bleeds into another phase's gate.
  const isTaskBreakdownGate = selected?.phase === "06_task_breakdown";
  const showReview = multiRepo && isTaskBreakdownGate && assignmentItems.length > 0;
  const unreviewedLow = assignmentItems.filter(
    (w) => w.external_ref?.repo_assignment?.confidence === "low" && !confirmed[w.id],
  ).length;
  const overrideRepo = (id: string, repoId: string) => {
    patchAny.mutate({ id, patch: { repo: repoId || null } });
    setConfirmed((c) => ({ ...c, [id]: true }));
  };
  const keepAssignment = (id: string) => setConfirmed((c) => ({ ...c, [id]: true }));
  const confirmAll = () =>
    setConfirmed(Object.fromEntries(assignmentItems.map((w) => [w.id, true])));

  // `hasRole`, not a comparison against one role. Memberships are one row per role, so
  // `selectedProject.role` is whichever came back first — a tech lead who is also product owner
  // was shown "you don't hold the tech_lead role" on a gate the SERVER would have let them
  // decide. The rules were never wrong; this screen was reading one row of several.
  const canDecide = (a: Approval) => hasRole(a.required_role);

  const workItemLabel = (id: string, fallbackTitle?: string | null) => {
    const wi = workItems.data?.find((w) => w.id === id);
    // A carrier work item is not in that list by design, so fall back to the title the approval
    // carries. Showing "Onboarding — project assessment" beats an 8-character id fragment for the
    // one gate whose work item the user is never meant to see in their backlog.
    if (!wi) return fallbackTitle || id.slice(0, 8);
    return `${wi.key || id.slice(0, 8)} · ${wi.title || wi.type}`;
  };

  const handleDecide = (decision: "approved" | "rejected", revise = false) => {
    if (!selected) return;
    // Captured BEFORE the mutation, from the gate being decided — not read back afterwards from
    // whatever `selected` has become by then. A merge gate revises IN PLACE (same branch, same
    // pull request, preview kept); a phase gate starts a fresh attempt. Same button, different
    // promise, so the sentence has to know which gate it was.
    setDecided({
      label: workItemLabel(selected.work_item, selected.work_item_title),
      kind: decision === "approved" ? "approved" : revise ? "revised" : "rejected",
      merge: selected.gate_type === "merge_gate",
    });
    decideApproval.mutate({
      id: selected.id,
      decision,
      comment: comment || undefined,
      conditions: criteriaList.length
        ? criteriaList.map((c) => ({ key: c.id, satisfied: Boolean(satisfied[c.id]) }))
        : undefined,
      revise,
    });
    setComment("");
  };
  // "Request changes" IS the comment — without one there is nothing for the agent to act on,
  // and the server refuses it. Keep the button visibly disabled rather than letting the click
  // fail with a validation error.
  const canRequestChanges = comment.trim().length > 0;

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">
            Gates{" "}
            {!loading && pending.length > 0 && (
              <Badge variant="gate" dot={false}>
                {pending.length} pending
              </Badge>
            )}
          </h1>
          <p className="page-head__sub">
            Approvals awaiting a decision. Only the required role can decide each gate — nothing
            reaches a system-of-record without one.
          </p>
        </div>
      </div>

      <Tabs
        tabs={[
          { id: "pending", label: `Pending (${pending.length})` },
          { id: "history", label: "Decided history" },
        ]}
        active={tab}
        onSelect={(id) => setTab(id as "pending" | "history")}
      />

      {/* THE confirmation — one per decision, above the list rather than inside a gate's panel,
          and it names the gate it is about. Appears only after a decision lands and only until
          the reviewer picks another gate; no permanently mounted slot.

          Whether the task happens to be running is deliberately NOT mentioned (team decision,
          8 September). The reviewer's decision is written and signalled identically either way,
          so it was an explanation of our machinery offered to someone who never needed it. */}
      {decided && decideApproval.isSuccess && (
        <Banner
          variant={decided.kind === "approved" ? "success" : "info"}
          title={
            decided.kind === "approved"
              ? "Approved"
              : decided.kind === "revised"
                ? "Sent back for changes"
                : "Rejected"
          }
        >
          <p className="t-sm">
            {decided.kind === "approved" ? (
              <>
                Your approval of <strong>{decided.label}</strong> is saved.
              </>
            ) : decided.kind === "revised" ? (
              decided.merge ? (
                <>
                  Your note on <strong>{decided.label}</strong> has been sent back. The same branch
                  and pull request are updated — your preview stays up — and this gate re-opens for
                  you when it's ready.
                </>
              ) : (
                <>
                  Your note on <strong>{decided.label}</strong> has been sent back. A fresh attempt
                  starts shortly using it as the instructions — follow it in Phases &amp; Runs.
                </>
              )
            ) : (
              <>
                <strong>{decided.label}</strong> was rejected, and will not go any further.
              </>
            )}
          </p>
        </Banner>
      )}

      {staleLink && (
        <Banner variant="info" title="That gate is no longer pending">
          <p className="t-sm">
            Nothing is selected, so nothing here can be approved by mistake. If it was just
            decided, it is in the decided history.
          </p>
          <Button variant="secondary" size="sm" onClick={() => setTab("history")}>
            Look in the decided history
          </Button>
        </Banner>
      )}

      {loading ? (
        <Panel>
          <Spinner /> Loading gates…
        </Panel>
      ) : tab === "history" ? (
        <GateHistory projectId={projectId} currentUserId={currentUser?.user.id} />
      ) : pending.length === 0 ? (
        <Panel>
          <EmptyState
            title="No gates need you"
            text="Approvals you can act on will appear here and in the notifications bell."
          />
        </Panel>
      ) : (
        <div
          className={showReview ? "u-stack" : "grid grid--detail"}
          style={{ marginTop: "var(--space-5)" }}
        >
          <Panel title="Pending approvals" flush>
            <Table
              headers={["Gate", "Required role", "Work item", "Artifact"]}
              rows={pending.map((a) => ({
                // Bugs S.No 189: the WHOLE row picks the gate. Before this, the only thing that
                // selected anything was the small button in the first column, and the work-item
                // name — the obvious thing to click — was a link that left the screen entirely.
                // So a reviewer with five gates could not do the one thing this layout exists
                // for: read the list, pick one, decide it, pick the next.
                onSelect: () => setSelectedId(a.id),
                selected: Boolean(selected && a.id === selected.id),
                selectLabel: `${gateLabel(a.gate_type)} — ${workItemLabel(a.work_item, a.work_item_title)}`,
                cells: [
                  gateLabel(a.gate_type),
                  <span className="chip badge--navy" key="r">
                    {roleLabel(a.required_role)}
                  </span>,
                  // Plain text, not a link: clicking the work item now picks the gate, and
                  // opening the work item moved to the panel on the right where it doesn't
                  // compete with selecting.
                  <span className="table__id" key="w">
                    {workItemLabel(a.work_item, a.work_item_title)}
                  </span>,
                  // N2 / UX spec J19: "a link to preview the artifact under review". The
                  // endpoint was built and signed off; this link never was, and sent the
                  // reviewer to the whole registry to re-find what they were reviewing.
                  // Scoped by RUN rather than by a single artifact id because a run can
                  // register several — a "pick the first" rule would be a new lie.
                  <Link to={artifactsForRun(a.run)} key="a">
                    Preview ↗
                  </Link>,
                ],
              }))}
            />
          </Panel>

          {selected &&
            (canDecide(selected) ? (
              <Card attention>
                <CardBody>
                  <span className="gate-panel__role">
                    ▲ {gateLabel(selected.gate_type)} · required role: {roleLabel(selected.required_role)}
                  </span>
                  <div className="u-row-tight">
                    <h3 className="t-h3">{workItemLabel(selected.work_item, selected.work_item_title)}</h3>
                    {/* One chip, at chip size. The reviewer is not being warned or blocked —
                        their decision lands either way — so this marks the task and stops. */}
                    {selected.run_paused && <Badge variant="paused" dot={false}>Paused</Badge>}
                  </div>
                  {/* UX spec J19: "a link to preview the artifact under review". The preview
                      endpoint was built and signed off; this link never was, and sent the
                      reviewer to the whole registry to re-find what they were reviewing.

                      "Open work item" joins it here because the row stopped navigating
                      (S.No 189). Beside the artifact preview on purpose: both are ways of
                      looking deeper at the thing under review, and neither competes with
                      picking a gate. Stacked, not inline — two links on one line read as one. */}
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "var(--space-1)",
                      margin: "var(--space-2) 0 0",
                      alignItems: "flex-start",
                    }}
                  >
                    <Link to={artifactsForRun(selected.run)} className="t-sm">
                      Preview artifact under review ↗
                    </Link>
                    <Link to={workItemLink(selected.work_item)} className="t-sm">
                      Open work item ↗
                    </Link>
                  </div>
                  {externalMergeNotice}
                  {selected.merge_conflict && (
                    <div style={{ margin: "var(--space-3) 0 0" }}>
                      <Banner variant="warning" title="Merge paused — conflict needs resolving">
                        This merge couldn't be completed automatically: {selected.merge_conflict}{" "}
                        Resolve the conflict in the pull request on GitHub, then approve again to
                        retry the merge — the build does not need to run again.
                      </Banner>
                    </div>
                  )}
                  {criteriaList.length > 0 && (
                    <div style={{ margin: "var(--space-3) 0 0" }}>
                      <div className="u-row">
                        <span className="gate-panel__role">Required checklist</span>
                        <span className="u-spacer" />
                        <span
                          className="criteria-progress"
                          style={!requiredUnmet ? { color: "var(--success)" } : undefined}
                        >
                          {metCount} of {criteriaList.length} met
                        </span>
                      </div>
                      <CriteriaList>
                        {criteriaList.map((c) => (
                          <div
                            key={c.id}
                            style={{ cursor: "pointer" }}
                            onClick={() => setSatisfied((s) => ({ ...s, [c.id]: !s[c.id] }))}
                          >
                            {/* remount on toggle: CriteriaItem's checkbox is uncontrolled */}
                            <CriteriaItem key={String(satisfied[c.id])} met={Boolean(satisfied[c.id])}>
                              {c.text}
                              {c.required && " *"}
                            </CriteriaItem>
                          </div>
                        ))}
                      </CriteriaList>
                    </div>
                  )}
                  {showReview && (
                    <>
                      <RepoAssignmentReview
                        items={assignmentItems}
                        repos={repoList}
                        confirmed={confirmed}
                        onOverride={overrideRepo}
                        onKeep={keepAssignment}
                        busy={patchAny.isPending}
                      />
                      {unreviewedLow > 0 && (
                        <Banner
                          variant="info"
                          title={`${unreviewedLow} task${unreviewedLow > 1 ? "s" : ""} the planner wasn't sure about`}
                        >
                          Review the flagged tasks above, or{" "}
                          <button className="btn btn--ghost btn--sm" onClick={confirmAll}>
                            confirm all as-is
                          </button>
                          . You can still approve — this is a heads-up, not a block.
                        </Banner>
                      )}
                      <span className="gate-reassure">Approving confirms these repository assignments.</span>
                    </>
                  )}
                  <label className="field" style={{ margin: "var(--space-2) 0 0" }}>
                    <span className="field__label">
                      Comment{canRequestChanges ? "" : " (optional to approve or reject)"}
                    </span>
                    <Textarea
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      placeholder="Add context for your decision — or say what you want changed…"
                    />
                  </label>
                  <div className="gate-panel__actions">
                    <Button
                      variant="primary"
                      disabled={decideApproval.isPending || requiredUnmet}
                      aria-disabled={requiredUnmet}
                      onClick={() => handleDecide("approved")}
                    >
                      {decideApproval.isPending ? (
                        <Spinner />
                      ) : requiredUnmet ? (
                        `Approve (${criteriaList.length - metCount} remaining)`
                      ) : selected.external_merge ? (
                        // Same button, same endpoint, same role check, same ledger event and
                        // the same signal to the workflow — only the word changes, because
                        // "Approve" is the wrong word for something already done.
                        "Acknowledge merge & complete"
                      ) : (
                        "Approve"
                      )}
                    </Button>
                    <Button
                      variant="secondary"
                      disabled={decideApproval.isPending || !canRequestChanges}
                      aria-disabled={!canRequestChanges}
                      title={
                        canRequestChanges
                          ? undefined
                          : "Write what you want changed first — the agent re-runs on this text"
                      }
                      onClick={() => handleDecide("rejected", true)}
                    >
                      Request changes
                    </Button>
                    <Button
                      variant="danger"
                      disabled={decideApproval.isPending}
                      onClick={() => handleDecide("rejected")}
                    >
                      Reject
                    </Button>
                  </div>
                  {decideApproval.isError && (
                    <WriteError title="Couldn't record the decision" detail={decideApproval.error} />
                  )}
                  {/* No confirmation banner here. There used to be one, and it was the third
                      telling of a single click: the page-level banner above, then "Decision
                      recorded — Logged with your role and comment", then the line below saying
                      "Decision logged with your role & comment". The last two were not merely
                      similar, they duplicated by CONSTRUCTION — deciding clears the comment box,
                      which is exactly what flipped that line to the duplicate wording. And being
                      mounted inside the panel is what let it drift onto the next gate
                      (S.No 250). One confirmation, above the list, naming its own gate.

                      The line below is guidance for the gate now on screen, not a report on the
                      last one — so it says what will happen, in one sentence. */}
                  <span className="gate-reassure">
                    Decisions are recorded with your name and role.
                  </span>
                </CardBody>
              </Card>
            ) : (
              <Card>
                <CardBody>
                  <span className="gate-panel__role" style={{ color: "var(--text-muted)" }}>
                    {gateLabel(selected.gate_type)} · {workItemLabel(selected.work_item, selected.work_item_title)}
                  </span>
                  {/* Screen Words group 3. Two lines above, this same file already prints the
                      readable role, so the page mixed both. It also never said that an admin can
                      decide, which is true and is the one thing a blocked reader most needs. */}
                  <Banner variant="info" title={`Waiting for a ${roleLabel(selected.required_role)}`}>
                    Only a <strong>{roleLabel(selected.required_role)}</strong> on this project, or
                    an admin, can decide this gate. You can read it.
                  </Banner>
                  {/* Whoever is LOOKING at this gate needs to know the merge already happened,
                      not only whoever can decide it. Leaving it out here would keep the
                      original bug alive for everyone but the tech lead. */}
                  {externalMergeNotice}
                  <Link to={artifactsForRun(selected.run)} className="t-sm">
                    Preview artifact under review ↗
                  </Link>
                  <div className="gate-panel__actions">
                    <Button variant="primary" disabled aria-disabled="true">
                      Approve
                    </Button>
                    <Button variant="secondary" disabled aria-disabled="true">
                      Reject
                    </Button>
                  </div>
                </CardBody>
              </Card>
            ))}
        </div>
      )}
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
// ── Decided-gate history ───────────────────────────────────────────────────
// Paged and filterable, because this is a record that only grows: a project six months in has
// hundreds of decided gates, and the table rendered every one of them. Phase is shown as its own
// column — it was already being sent to the browser and nothing displayed it, so a reviewer
// could see THAT a gate was decided but not WHICH phase it belonged to.
const GATE_HISTORY_PAGE_SIZE = 25;

function GateHistory({
  projectId,
  currentUserId,
}: {
  projectId: string | undefined;
  currentUserId: string | undefined;
}) {
  const [workItem, setWorkItem] = useState("");
  const [phase, setPhase] = useState("");
  const [page, setPage] = useState(1);
  const workItems = useWorkItems(projectId);
  const history = useApprovalHistory({
    project: projectId,
    work_item: workItem || undefined,
    phase: phase || undefined,
    page,
  });

  // A filter change resets to page 1 — page 3 of the previous result set says nothing about the
  // new one, and landing on an empty page reads as "there is nothing here".
  const applyFilter = (set: (v: string) => void) => (v: string) => {
    set(v);
    setPage(1);
  };

  const rows = (history.data?.results ?? []).filter((a) => a.decision !== "pending");
  // Mirrors the pending table's labeller: a carrier work item is deliberately absent from the
  // backlog list, so fall back to the title the approval itself carries rather than showing an
  // 8-character id fragment for the one gate whose work item the user never sees.
  const label = (id: string, fallbackTitle?: string | null) => {
    const wi = workItems.data?.find((w) => w.id === id);
    if (!wi) return fallbackTitle || id.slice(0, 8);
    return `${wi.key || id.slice(0, 8)} · ${wi.title || wi.type}`;
  };

  return (
    <div style={{ marginTop: "var(--space-4)" }}>
      <div className="history-filters" style={{ marginBottom: "var(--space-3)" }}>
        <WorkItemFilter
          value={workItem}
          onChange={applyFilter(setWorkItem)}
          items={workItems.data ?? []}
        />
        <PhaseFilter value={phase} onChange={applyFilter(setPhase)} as="key" />
      </div>

      {history.isLoading ? (
        <Panel>
          <Spinner /> Loading history…
        </Panel>
      ) : rows.length === 0 ? (
        <Panel>
          <EmptyState title="No decided gates yet" text="Decisions you make will show up here." />
        </Panel>
      ) : (
        <>
          <Panel flush>
            <Table
              headers={["Gate", "Phase", "Work item", "Decision", "Comment", "By", "When"]}
              rows={rows.map((a) => [
                gateLabel(a.gate_type),
                a.phase ? phaseLabel(a.phase) : "—",
                <Link className="table__id" to={workItemLink(a.work_item)} key="w">
                  {label(a.work_item, a.work_item_title)}
                </Link>,
                <Badge variant={a.decision === "approved" ? "done" : "failed"} key="d">
                  {a.decision === "approved" ? "Approved" : "Rejected"}
                </Badge>,
                // What the reviewer actually wrote. Stored and served all along, never shown —
                // so a rejection read as a bare "Rejected" with the reason invisible, even to
                // the person who wrote it.
                <span
                  key="c"
                  className="t-sm u-body"
                  title={a.comment || undefined}
                  style={{
                    display: "block",
                    maxWidth: "28rem",
                    whiteSpace: "pre-wrap",
                    overflowWrap: "anywhere",
                  }}
                >
                  {a.comment || "—"}
                </span>,
                a.approver === currentUserId
                  ? "You"
                  : a.approver_name ?? (a.approver ? a.approver.slice(0, 8) : "—"),
                a.decided_at ? new Date(a.decided_at).toLocaleString() : "—",
              ])}
            />
          </Panel>
          <Pager
            page={page}
            count={history.data?.count ?? 0}
            pageSize={GATE_HISTORY_PAGE_SIZE}
            onPage={setPage}
            noun="decided gates"
          />
        </>
      )}
    </div>
  );
}

function GatesGallery({ view }: { view: GatesView }) {
  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">
            Gates{" "}
            {view !== "empty" && (
              <Badge variant="gate" dot={false}>
                3 pending
              </Badge>
            )}
          </h1>
          <p className="page-head__sub">
            Approvals awaiting a decision. Only the required role can decide each gate — nothing
            reaches a system-of-record without one.
          </p>
        </div>
      </div>

      {view !== "empty" && (
        <Tabs
          tabs={[
            { id: "pending", label: "Pending (3)" },
            { id: "history", label: "Decided history" },
          ]}
          active={view === "history" ? "history" : "pending"}
        />
      )}

      {view === "empty" ? (
        <Panel>
          <EmptyState
            title="No gates need you"
            text="Approvals you can act on will appear here and in the notifications bell."
          />
        </Panel>
      ) : view === "history" ? (
        <div style={{ marginTop: "var(--space-4)" }}>
          <Panel flush>
            <Table
              headers={["Gate", "Work item", "Decision", "Comment", "By", "When"]}
              rows={[
                [
                  "PRD",
                  <span className="table__id" key="w">
                    WI-492
                  </span>,
                  <Badge variant="done" key="d">
                    Approved
                  </Badge>,
                  "—",
                  "Sarah Chen",
                  "1h ago",
                ],
                [
                  "Requirements",
                  <span className="table__id" key="w">
                    WI-499
                  </span>,
                  <Badge variant="done" key="d">
                    Approved
                  </Badge>,
                  "Scope matches the signed-off brief.",
                  "Sarah Chen",
                  "2d ago",
                ],
                [
                  "Architecture",
                  <span className="table__id" key="w">
                    WI-470
                  </span>,
                  <Badge variant="failed" key="d">
                    Rejected
                  </Badge>,
                  "Event bus is overkill at this scale — use a queue.",
                  "Marcus Lee",
                  "3d ago",
                ],
              ]}
            />
          </Panel>
        </div>
      ) : (
        <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
          <Panel title="Pending approvals" flush>
            <Table
              headers={["Gate", "Required role", "Work item", "Artifact"]}
              rows={[
                {
                  cells: [
                    "Architecture",
                    <span className="chip badge--navy" key="r">
                      architect
                    </span>,
                    <span className="table__id" key="w">
                      WI-492
                    </span>,
                    <Link to="/artifacts" key="a">
                      Preview ↗
                    </Link>,
                  ],
                  style: { background: "var(--brand-orange-50)" },
                },
                [
                  "PM Approval",
                  <span className="chip badge--navy" key="r">
                    product_owner
                  </span>,
                  <span className="table__id" key="w">
                    WI-511
                  </span>,
                  <Link to="/artifacts" key="a">
                    Preview ↗
                  </Link>,
                ],
                [
                  "UX Design",
                  <span className="chip badge--navy" key="r">
                    designer
                  </span>,
                  <span className="table__id" key="w">
                    WI-487
                  </span>,
                  <Link to="/work-items/WI-487" key="a">
                    Preview ↗
                  </Link>,
                ],
              ]}
            />
          </Panel>

          {view === "can-decide" ? (
            <Card attention>
              <CardBody>
                <span className="gate-panel__role">▲ Architecture gate · required role: architect</span>
                <h3 className="t-h3">WI-492 · Stripe Webhook Integration</h3>
                <p className="t-sm u-body">
                  Reviewing: <strong>System Sequence Diagram v0.9</strong>. Approve to publish to Figma
                  and advance to UX Design.
                </p>
                <Link to="/artifacts" className="t-sm">
                  Preview artifact under review ↗
                </Link>
                <label className="field" style={{ margin: "var(--space-2) 0 0" }}>
                  <span className="field__label">Comment (optional to approve or reject)</span>
                  <Textarea placeholder="Add context for your decision — or say what you want changed…" />
                </label>
                <div className="gate-panel__actions">
                  <Button variant="primary">Approve</Button>
                  {/* Disabled until something is written: "Request changes" IS the comment. */}
                  <Button variant="secondary" disabled aria-disabled>
                    Request changes
                  </Button>
                  <Button variant="danger">Reject</Button>
                </div>
                <span className="gate-reassure">
                  Request changes re-runs this phase with your note as the agent's instructions.
                  Reject just stops it.
                </span>
              </CardBody>
            </Card>
          ) : (
            <Card>
              <CardBody>
                <span className="gate-panel__role" style={{ color: "var(--text-muted)" }}>
                  PM Approval gate · WI-511 Fix Session Timeout Logic
                </span>
                <Banner variant="info" title="Awaiting product_owner">
                  You don't hold the <strong>product_owner</strong> role on this project, so this is
                  read-only. <strong>Sarah Chen</strong> can decide.
                </Banner>
                <Link to="/artifacts" className="t-sm">
                  Preview artifact under review ↗
                </Link>
                <div className="gate-panel__actions">
                  <Button variant="primary" disabled aria-disabled="true">
                    Approve
                  </Button>
                  <Button variant="secondary" disabled aria-disabled="true">
                    Reject
                  </Button>
                </div>
              </CardBody>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
