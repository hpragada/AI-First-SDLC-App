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
  Select,
  Table,
} from "../../components/ui";
import type { WorkItemCard } from "../../types";
import { roleLabel } from "../identity/roles";
import { useCreateWorkItem, usePhaseCatalog, useWorkItems } from "./hooks";
import { humanizeLabel, lifecyclePhaseColumns, phaseLabel, statusLabel } from "./phases";

// S-14 view states: board (default) · list · filtered (tasks only) · empty.
export type BoardView = "board" | "list" | "filtered" | "empty";

// Bugs.xlsx row 27.1: columns are the full lifecycle in SDLC order (from the catalog), not a
// hardcoded four. The board scrolls horizontally, so the extra columns need no layout change.
const PHASE_COLUMNS = lifecyclePhaseColumns();

const BUILD_COLUMNS = [
  { key: "implementation", label: "Implementation" },
  { key: "review", label: "Review" },
];

function statusBadge(card: WorkItemCard) {
  const label = humanizeLabel(card.needs?.label);
  if (label && card.needs?.clarification) return <Needs type="clar">{label}</Needs>;
  if (label && card.needs?.gate) return <Needs type="gate">{label}</Needs>;
  if (card.state === "done") return <Badge variant="done">Phase complete</Badge>;
  if (card.state === "running") return <Badge variant="running">AI compiling…</Badge>;
  return <Badge variant="queued">Draft</Badge>;
}

// Human-readable work-item type ("story" → "Story"). One place so the board card and list agree.
function typeLabel(type: string | undefined): string {
  return type ? type[0].toUpperCase() + type.slice(1) : "Item";
}

function WiCard({ card }: { card: WorkItemCard }) {
  return (
    <Link to={`/work-items/${card.id}`} className="wi-card">
      <div className="wi-card__top">
        <span className="wi-card__id">{card.key || card.id}</span>
        {statusBadge(card)}
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

  const view: BoardView =
    forceView ??
    (level === "task"
      ? "filtered"
      : mode === "list"
        ? "list"
        : allItems.length === 0 && items.isSuccess
          ? "empty"
          : "board");

  const columns = view === "filtered" ? BUILD_COLUMNS : PHASE_COLUMNS;
  const byPhase = useMemo(() => {
    const map = new Map<string, WorkItemCard[]>();
    for (const col of columns) map.set(col.key, []);
    for (const item of list) {
      // Column = the item's CURRENT lifecycle phase (Bugs.xlsx row 50: the feature
      // stream was wrongly used as the phase). No phase run yet → first column.
      const bare = barePhase(item.current_phase);
      const key = columns.find((c) => barePhase(c.key) === bare)?.key ?? columns[0]?.key;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(item);
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
            headers={["ID", "Title", "Level", "Phase", "Status", "Artifacts", "Owner"]}
            rows={list.map((item) => [
              <span className="table__id" key="id">
                {item.key || item.id}
              </span>,
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
    </div>
  );
}
