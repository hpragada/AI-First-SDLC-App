import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import {
  Avatar,
  Badge,
  Button,
  Chip,
  Drawer,
  EmptyState,
  Field,
  Input,
  Needs,
  Panel,
  RowMenu,
  Select,
  Table,
} from "../../components/ui";
import type { BadgeVariant } from "../../components/ui";
import { isTerminalState, PLANNING_PHASES } from "../../types";
import type { WorkItemCard, WorkItemState } from "../../types";
import { CancelWorkItem } from "./CancelWorkItem";
import { roleLabel } from "../identity/roles";
import { useCreateWorkItem, usePhaseCatalog, useWorkItems } from "./hooks";
import { workItemLink } from "../../links";
import { humanizeLabel, lifecyclePhaseColumns, phaseLabel, statusLabel } from "./phases";

// S-14 view states: board (default) · list · filtered (tasks only) · empty.
export type BoardView = "board" | "list" | "filtered" | "empty";

// Bugs S.No 117. An item nothing has run on yet has no phase, and the board dropped it into
// whichever column happened to be FIRST — Ideation on the default board, Implementation once
// filtered to Tasks — so brand-new work looked as if it were already under way, and the same item
// changed column when the filter changed. It has a column of its own now.
const BACKLOG_KEY = "backlog";
const BACKLOG = { key: BACKLOG_KEY, label: "Backlog" };

// Bugs.xlsx row 27.1: columns are the full lifecycle in SDLC order (from the catalog), not a
// hardcoded four. The board scrolls horizontally, so the extra columns need no layout change.
const PHASE_COLUMNS = [BACKLOG, ...lifecyclePhaseColumns()];

// Keyed by the agent key, like every column above, so `barePhase` matches them. They were keyed
// `implementation` and `review`, and a code-review run reduces to `code_review` — which matched
// neither, so every task in review sat in Implementation. Found on the same line as S.No 117.
const BUILD_COLUMNS = [
  BACKLOG,
  { key: "07_implementation", label: "Implementation" },
  { key: "08_code_review", label: "Review" },
];

// Where each phase sits in the lifecycle, so a column added for a phase lands in order.
const PHASE_ORDER = new Map(PLANNING_PHASES.map((p, index) => [barePhase(p.key), index]));

// Bugs S.No 140. This was a chain of ifs ending in `return <Badge variant="queued">Draft</Badge>`,
// so FOUR of the six states rendered as "Draft" — an item in review, an item blocked, an item
// accepted into the tracker, and (once the state existed) a cancelled one. Confidently wrong is
// worse than unlabelled: a board that calls abandoned work a draft is a board that gets planned
// against. The chain also tested `card.state === "running"`, which has never been a work-item
// state — dead code that read as coverage.
//
// An exhaustive map over the union, so the compiler names any state added later instead of
// letting it fall into the wrong bucket. `satisfies` is what enforces that.
const STATE_BADGE = {
  proposed: { variant: "queued", label: "Draft" },
  accepted: { variant: "neutral", label: "Accepted" },
  in_progress: { variant: "running", label: "In progress" },
  in_review: { variant: "waiting", label: "In review" },
  blocked: { variant: "failed", label: "Blocked" },
  done: { variant: "done", label: "Phase complete" },
  cancelled: { variant: "cancelled", label: "Cancelled" },
} satisfies Record<WorkItemState, { variant: BadgeVariant; label: string }>;

function statusBadge(card: WorkItemCard) {
  // Cancelled outranks a pending need, and is checked FIRST for that reason: a stale gate or
  // clarification left over from before the decision must not badge abandoned work as
  // "waiting on you".
  if (card.state === "cancelled") return <Badge variant="cancelled">Cancelled</Badge>;
  const label = humanizeLabel(card.needs?.label);
  if (label && card.needs?.clarification) return <Needs type="clar">{label}</Needs>;
  if (label && card.needs?.gate) return <Needs type="gate">{label}</Needs>;
  const badge = STATE_BADGE[card.state] ?? STATE_BADGE.proposed;
  return <Badge variant={badge.variant}>{badge.label}</Badge>;
}

// Bugs S.No 117 — what the phase a card sits in is DOING, in words, on the card: the team's
// option B, a status pill (the badge the rest of the app already uses). Read off the same run the
// card's column comes from, so the column and the pill can never describe different runs.
//
// Four markers, not three: a phase can FINISH and still be waiting for a person to approve it, and
// calling that "Done" is the same kind of untruth as the bug being fixed.
function phasePill(card: WorkItemCard) {
  // Cancelled outranks everything, for the reason `statusBadge` gives.
  if (card.state === "cancelled") return <Badge variant="cancelled">Cancelled</Badge>;
  if (!card.current_phase) return <Badge variant="queued">Not started</Badge>;
  if (card.needs?.gate || card.needs?.clarification) {
    return <Badge variant="gate">Waiting for you</Badge>;
  }
  switch (card.run_status) {
    case "pending":
    case "running":
      return <Badge variant="running">Running</Badge>;
    case "awaiting_gate":
      return <Badge variant="gate">Waiting for you</Badge>;
    case "approved":
    case "completed":
      return <Badge variant="done">Done</Badge>;
    // The same reading Phases & Runs gives a rejected run.
    case "failed":
    case "rejected":
      return <Badge variant="failed">Failed</Badge>;
    default:
      // An API too old to send the run's status, or a status with no marker of its own (a run
      // parked waiting for its machine): the work item's own badge, rather than a guess.
      return statusBadge(card);
  }
}

// Human-readable work-item type ("story" → "Story"). One place so the board card and list agree.
function typeLabel(type: string | undefined): string {
  if (!type) return "Item";
  const s = type.replace(/_/g, " ");        // "test_case" → "Test case"
  return s[0].toUpperCase() + s.slice(1);
}

function WiCard({ card }: { card: WorkItemCard }) {
  return (
    <Link to={`/work-items/${card.id}`} className="wi-card">
      <div className="wi-card__top">
        <span className="wi-card__id">{card.key || card.id}</span>
        {phasePill(card)}
      </div>
      <div className="wi-card__title">{card.title || card.key || card.id}</div>
      <div className="wi-card__meta">
        <Chip variant={card.type === "task" ? undefined : "navy"}>
          {typeLabel(card.type)}
        </Chip>
        {card.parent && <Chip>↖ {card.parent}</Chip>}
      </div>
      <div className="wi-card__foot">
        <span>{card.artifact_count ?? 0} artifacts</span>
        <span className="u-spacer" />
        {card.owner && <Avatar size="sm">{card.owner.slice(0, 2).toUpperCase()}</Avatar>}
      </div>
    </Link>
  );
}

function CreateWorkItemDrawer({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const createWorkItem = useCreateWorkItem(projectId);
  const [title, setTitle] = useState("");
  const [type, setType] = useState("epic");

  const titleValid = title.trim().length > 0;

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!titleValid) return;
    try {
      const created = await createWorkItem.mutateAsync({ type, title: title.trim() });
      onClose();
      navigate(`/work-items/${created.id}`);
    } catch {
      /* error surfaced inline below */
    }
  };

  // What each work-item type means, in plain language — no internal "tier" jargon
  // (Bugs.xlsx rows 21 iii + 36).
  const TYPE_HELP =
    "Epic — a large feature or initiative that goes through all the planning phases, "
    + "from Ideation to Task Breakdown. "
    + "Story — a smaller, user-facing piece of an epic, planned the same way. "
    + "Task — a concrete development job that gets implemented, code-reviewed and tested. "
    + "Defect — a bug fix that follows the shorter fix-and-verify flow.";

  return (
    <Drawer
      title="New work item"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="create-work-item-form" disabled={createWorkItem.isPending || !titleValid}>
            {createWorkItem.isPending ? "Creating…" : "Create"}
          </Button>
        </>
      }
    >
      <form id="create-work-item-form" onSubmit={onSubmit}>
        <Field label="Title" required>
          <Input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Stripe Webhook Integration"
            aria-required="true"
          />
        </Field>
        <Field label="Type" help={TYPE_HELP}>
          <Select value={type} onChange={(e) => setType(e.target.value)} aria-label="Type" title={TYPE_HELP}>
            <option value="epic">Epic</option>
            <option value="story">Story</option>
            <option value="task">Task</option>
            <option value="defect">Defect</option>
          </Select>
        </Field>
        {createWorkItem.isError && (
          <p className="t-sm" style={{ color: "var(--danger)" }}>
            {createWorkItem.error instanceof Error ? createWorkItem.error.message : "Couldn't create this work item."}
          </p>
        )}
      </form>
    </Drawer>
  );
}

// Ordinal-stripped phase name, so "03_prd" (agent key) matches the "03_prd" column key
// or a bare "prd" value regardless of which form each side carries.
function barePhase(phase: string | undefined): string {
  return (phase ?? "").replace(/^\d+[a-z]?_/i, "").toLowerCase();
}

export function WorkItemsBoard({ forceView }: { forceView?: BoardView }) {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const [level, setLevel] = useState<"all" | "epic" | "task" | "defect">("all");
  const [mode, setMode] = useState<"board" | "list">("board");
  const [createOpen, setCreateOpen] = useState(false);
  // Bugs.xlsx row 49: the search box and Phase/Role/Status dropdowns were inert (only the
  // level chips filtered). Client-side over the loaded board, same as the Artifacts fix.
  const [search, setSearch] = useState("");
  const [phaseFilter, setPhaseFilter] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [cancelling, setCancelling] = useState<WorkItemCard | null>(null);
  const catalog = usePhaseCatalog();

  const items = useWorkItems(projectId, level === "all" ? {} : { type: level });
  // The gate role responsible for a phase, from the live catalog ("Role" filter).
  const roleByPhase = useMemo(() => {
    const entries = [
      ...(catalog.data?.plan ?? []),
      ...(catalog.data?.build ?? []),
      ...(catalog.data?.remediation ?? []),
    ];
    return new Map(entries.map((e) => [barePhase(e.key), e.gate_role]));
  }, [catalog.data]);

  const allItems = items.data ?? [];
  const list = useMemo(
    () =>
      allItems.filter((item) => {
        const phase = barePhase(item.current_phase);
        if (phaseFilter && phase !== phaseFilter) return false;
        if (roleFilter && (roleByPhase.get(phase) ?? "") !== roleFilter) return false;
        if (statusFilter && item.state !== statusFilter) return false;
        // Bugs S.No 140: cancelled work is hidden by default. Cancelling exists to get things
        // OFF the board — leaving them on it would make cancelling pointless. Never hidden
        // outright, though: choosing "Cancelled" in the status filter shows exactly those, so
        // the record stays reachable and a cancellation can be found and questioned.
        if (!statusFilter && item.state === "cancelled") return false;
        if (search) {
          const hay = `${item.key ?? ""} ${item.title ?? ""} ${item.type ?? ""} ${item.feature_stream ?? ""}`.toLowerCase();
          if (!hay.includes(search.toLowerCase())) return false;
        }
        return true;
      }),
    [allItems, phaseFilter, roleFilter, statusFilter, search, roleByPhase],
  );

  // Filter options reflect what's actually on the board.
  const phaseOptions = useMemo(
    () => [...new Set(allItems.map((i) => barePhase(i.current_phase)).filter(Boolean))].sort(),
    [allItems],
  );
  const roleOptions = useMemo(
    () =>
      [...new Set(
        allItems.map((i) => roleByPhase.get(barePhase(i.current_phase)) ?? "").filter(Boolean),
      )].sort(),
    [allItems, roleByPhase],
  );
  const statusOptions = useMemo(
    () => [...new Set(allItems.map((i) => i.state).filter(Boolean))].sort(),
    [allItems],
  );
  // How many are being hidden right now — said out loud beside the filter. A board that
  // quietly drops rows is a board whose counts nobody can reconcile; "3 cancelled hidden" is
  // the difference between a filter and a disappearance.
  const hiddenCancelled = useMemo(
    () => (statusFilter ? 0 : allItems.filter((i) => i.state === "cancelled").length),
    [allItems, statusFilter],
  );

  const view: BoardView =
    forceView ??
    (level === "task"
      ? "filtered"
      : mode === "list"
        ? "list"
        : allItems.length === 0 && items.isSuccess
          ? "empty"
          : "board");

  const baseColumns = view === "filtered" ? BUILD_COLUMNS : PHASE_COLUMNS;
  // A phase this view has no column for — a task in a later build phase on the Tasks view, say —
  // gets a column of its own, in lifecycle order, named after the phase. Falling back to some
  // other column would misstate where the item is, which is exactly what this bug looked like.
  const columns = useMemo(() => {
    const have = new Set(baseColumns.map((c) => barePhase(c.key)));
    const extra = new Map<string, { key: string; label: string }>();
    for (const item of list) {
      const bare = barePhase(item.current_phase);
      if (bare && !have.has(bare) && !extra.has(bare)) {
        extra.set(bare, { key: item.current_phase as string, label: phaseLabel(item.current_phase) });
      }
    }
    if (extra.size === 0) return baseColumns;
    const order = (key: string) =>
      key === BACKLOG_KEY ? -1 : PHASE_ORDER.get(barePhase(key)) ?? Number.MAX_SAFE_INTEGER;
    return [...baseColumns, ...extra.values()].sort((a, b) => order(a.key) - order(b.key));
  }, [baseColumns, list]);
  const byPhase = useMemo(() => {
    const map = new Map<string, WorkItemCard[]>(columns.map((col) => [col.key, []]));
    for (const item of list) {
      // Column = the item's CURRENT lifecycle phase (Bugs.xlsx row 50: the feature stream was
      // wrongly used as the phase). Nothing has run on it yet → Backlog (S.No 117).
      const bare = barePhase(item.current_phase);
      const key = bare
        ? columns.find((c) => c.key !== BACKLOG_KEY && barePhase(c.key) === bare)?.key
        : BACKLOG_KEY;
      map.get(key ?? BACKLOG_KEY)?.push(item);
    }
    return map;
  }, [list, columns]);

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Work Items</h1>
          <p className="page-head__sub">
            Every work item across its phase. Columns are lifecycle phases; filter by level so the
            two tiers don't collide.
          </p>
        </div>
        <button className="btn btn--primary" onClick={() => setCreateOpen(true)}>
          + New Work Item
        </button>
      </div>

      {view !== "empty" && (
        <div className="u-row u-wrap" style={{ marginBottom: "var(--space-4)" }}>
          <input
            className="input"
            type="search"
            placeholder="Search work items…"
            style={{ maxWidth: "240px" }}
            aria-label="Search work items"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="select"
            style={{ maxWidth: "150px" }}
            aria-label="Filter by phase"
            value={phaseFilter}
            onChange={(e) => setPhaseFilter(e.target.value)}
          >
            <option value="">Phase: All</option>
            {phaseOptions.map((p) => (
              <option key={p} value={p}>
                {phaseLabel(p)}
              </option>
            ))}
          </select>
          <span className="u-row-tight">
            {(["all", "epic", "task", "defect"] as const).map((l) => (
              <button
                key={l}
                className="chip chip--filter"
                aria-pressed={level === l}
                onClick={() => setLevel(l)}
              >
                {l === "all" ? "All levels" : l === "epic" ? "Epics" : l === "task" ? "Tasks" : "Defects"}
              </button>
            ))}
          </span>
          <select
            className="select"
            style={{ maxWidth: "160px" }}
            aria-label="Filter by role"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          >
            <option value="">Role: All</option>
            {roleOptions.map((r) => (
              <option key={r} value={r}>
                {roleLabel(r)}
              </option>
            ))}
          </select>
          <select
            className="select"
            style={{ maxWidth: "150px" }}
            aria-label="Filter by status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">Status: All</option>
            {statusOptions.map((s) => (
              <option key={s} value={s}>
                {statusLabel(s)}
              </option>
            ))}
          </select>
          {hiddenCancelled > 0 && (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => setStatusFilter("cancelled")}
            >
              {hiddenCancelled} cancelled hidden
            </button>
          )}
          <span className="u-spacer" />
          <span className="segmented">
            <button aria-pressed={mode === "board"} onClick={() => setMode("board")}>
              Board
            </button>
            <button aria-pressed={mode === "list"} onClick={() => setMode("list")}>
              List
            </button>
          </span>
        </div>
      )}

      {view === "filtered" && (
        <p className="t-sm u-muted" style={{ marginBottom: "var(--space-3)" }}>
          Showing tasks from the build tier — fanned out by Task Breakdown.
        </p>
      )}

      {view === "empty" ? (
        <Panel>
          <EmptyState
            title="No work items yet"
            text="Create your first work item to start the lifecycle. Epics run the plan tier; Task Breakdown fans out the build tier."
            action={
              <button className="btn btn--primary" onClick={() => setCreateOpen(true)}>
                + New Work Item
              </button>
            }
          />
        </Panel>
      ) : view === "list" ? (
        <Panel flush>
          <Table
            headers={["ID", "Title", "Level", "Phase", "Status", "Artifacts", "Owner",
                      // Named for a screen reader, blank to the eye — an unlabelled column is
                      // a column a non-sighted user cannot make sense of.
                      <span className="u-visually-hidden" key="a">Actions</span>]}
            rows={list.map((item) => [
              // N2: the board's own ID column was inert text — the one thing on the row that
              // IS the work item was the one thing you could not click.
              <Link className="table__id" to={workItemLink(item.id)} key="id">
                {item.key || item.id}
              </Link>,
              <span className="table__primary" key="t">
                {item.title || item.key || item.id}
              </span>,
              <Chip key="l" variant={item.type === "task" ? undefined : "navy"}>
                {typeLabel(item.type)}
              </Chip>,
              // The actual lifecycle phase — the feature stream is not a phase (row 50).
              item.current_phase ? phaseLabel(item.current_phase) : "Not started",
              statusBadge(item),
              item.artifact_count ?? 0,
              item.owner ?? "—",
              // Bugs S.No 140. The row action lives in the LIST, not on the board card: a card
              // is one <Link> wrapping everything, and a button inside an anchor is invalid
              // markup that breaks keyboard and screen-reader navigation. The list is also
              // where clearing several stale items actually happens.
              //
              // "Cancel…" is offered only while there is something left to cancel. It is shown
              // to everyone: the server allows tech leads and admins, and refuses anyone else
              // with a sentence the dialog puts on screen — the same bar, and the same way of
              // saying so, as the task and defect pages.
              <RowMenu
                key="menu"
                label={`Actions for ${item.key || item.id}`}
                items={[
                  { label: "Open", href: workItemLink(item.id) },
                  ...(isTerminalState(item.state)
                    ? []
                    : [{ label: "Cancel…", onSelect: () => setCancelling(item), danger: true }]),
                ]}
              />,
            ])}
          />
        </Panel>
      ) : (
        <div className="board">
          {columns.map((col) => {
            const colItems = byPhase.get(col.key) ?? [];
            return (
              <div className="board__col" key={col.key}>
                <div className="board__col-head">
                  <span className="board__col-title">{col.label}</span>
                  <span className="u-spacer" />
                  <span className="board__col-count">{colItems.length}</span>
                </div>
                <div className="board__list">
                  {colItems.map((item) => (
                    <WiCard key={item.id} card={item} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {createOpen && projectId && (
        <CreateWorkItemDrawer projectId={projectId} onClose={() => setCreateOpen(false)} />
      )}

      {cancelling && (
        <CancelWorkItem workItem={cancelling} onClose={() => setCancelling(null)} />
      )}
    </div>
  );
}
