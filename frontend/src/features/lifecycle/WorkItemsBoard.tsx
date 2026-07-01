import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Avatar, Badge, Chip, EmptyState, Needs, Panel, Table } from "../../components/ui";
import type { WorkItemCard } from "../../types";
import { useWorkItems } from "./hooks";

// S-14 view states: board (default) · list · filtered (tasks only) · empty.
export type BoardView = "board" | "list" | "filtered" | "empty";

const PHASE_COLUMNS = [
  { key: "01_ideation", label: "1. Ideation" },
  { key: "02_requirements", label: "2. Requirements" },
  { key: "03_architecture", label: "3. Architecture" },
  { key: "04_ux_design", label: "4. UX Design" },
];

const BUILD_COLUMNS = [
  { key: "implementation", label: "Implementation" },
  { key: "review", label: "Review" },
];

function statusBadge(card: WorkItemCard) {
  const label = card.needs?.label;
  if (label && card.needs?.clarification) return <Needs type="clar">{label}</Needs>;
  if (label && card.needs?.gate) return <Needs type="gate">{label}</Needs>;
  if (card.state === "done") return <Badge variant="done">Phase complete</Badge>;
  if (card.state === "running") return <Badge variant="running">AI compiling…</Badge>;
  return <Badge variant="queued">Draft</Badge>;
}

function WiCard({ card }: { card: WorkItemCard }) {
  return (
    <Link to={`/work-items/${card.id}`} className="wi-card">
      <div className="wi-card__top">
        <span className="wi-card__id">{card.id}</span>
        {statusBadge(card)}
      </div>
      <div className="wi-card__title">{card.title ?? card.id}</div>
      <div className="wi-card__meta">
        <Chip variant={card.type === "task" ? undefined : "navy"}>
          {card.type ? card.type[0].toUpperCase() + card.type.slice(1) : "Item"}
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

export function WorkItemsBoard({ forceView }: { forceView?: BoardView }) {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project;
  const [level, setLevel] = useState<"all" | "epic" | "task" | "defect">("all");
  const [mode, setMode] = useState<"board" | "list">("board");

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
        <button className="btn btn--primary">+ New Work Item</button>
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
            action={<button className="btn btn--primary">+ New Work Item</button>}
          />
        </Panel>
      ) : view === "list" ? (
        <Panel flush>
          <Table
            headers={["ID", "Title", "Level", "Phase", "Status", "Artifacts", "Owner"]}
            rows={list.map((item) => [
              <span className="table__id" key="id">
                {item.id}
              </span>,
              <span className="table__primary" key="t">
                {item.title ?? item.id}
              </span>,
              <Chip key="l" variant={item.type === "task" ? undefined : "navy"}>
                {item.type}
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
    </div>
  );
}
