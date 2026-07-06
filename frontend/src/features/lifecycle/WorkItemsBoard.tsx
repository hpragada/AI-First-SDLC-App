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
import { useCreateWorkItem, useWorkItems } from "./hooks";
import { humanizeLabel, lifecyclePhaseColumns } from "./phases";

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

  // What each work-item type means, surfaced as a tooltip on the Type field (Bugs.xlsx row 21 iii).
  const TYPE_HELP =
    "Epic — a large body of work that runs the full plan tier (ideation → architecture). " +
    "Story — a user-facing slice of an epic, also plan tier. " +
    "Task — a concrete build-tier unit of work (implementation → review). " +
    "Defect — a fix that runs the remediation tier.";

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

export function WorkItemsBoard({ forceView }: { forceView?: BoardView }) {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const [level, setLevel] = useState<"all" | "epic" | "task" | "defect">("all");
  const [mode, setMode] = useState<"board" | "list">("board");
  const [createOpen, setCreateOpen] = useState(false);

  const items = useWorkItems(projectId, level === "all" ? {} : { type: level });
  const list = items.data ?? [];

  const view: BoardView =
    forceView ??
    (level === "task"
      ? "filtered"
      : mode === "list"
        ? "list"
        : list.length === 0 && items.isSuccess
          ? "empty"
          : "board");

  const columns = view === "filtered" ? BUILD_COLUMNS : PHASE_COLUMNS;
  const byPhase = useMemo(() => {
    const map = new Map<string, WorkItemCard[]>();
    for (const col of columns) map.set(col.key, []);
    for (const item of list) {
      const key = item.feature_stream || columns[0]?.key;
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
          />
          <select className="select" style={{ maxWidth: "150px" }} aria-label="Filter by phase">
            <option>Phase: All</option>
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
          <select className="select" style={{ maxWidth: "140px" }} aria-label="Filter by role">
            <option>Role: All</option>
          </select>
          <select className="select" style={{ maxWidth: "150px" }} aria-label="Filter by status">
            <option>Status: All</option>
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
              item.feature_stream,
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
