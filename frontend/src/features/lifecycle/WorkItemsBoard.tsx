import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import {
  Avatar,
  Badge,
  Button,
  Chip,
  Drawer,
  FilterSelect,
  EmptyState,
  Field,
  Input,
  Needs,
  Panel,
  RowMenu,
  Select,
  Table,
  Tooltip,
  cx,
  writeErrorSentence,
} from "../../components/ui";
import type { BadgeVariant } from "../../components/ui";
import { isTerminalState, PLANNING_PHASES } from "../../types";
import type { WorkItemCard, WorkItemState } from "../../types";
import { CancelWorkItem } from "./CancelWorkItem";
import { ReopenWorkItem } from "./ReopenWorkItem";
import { roleLabel } from "../identity/roles";
import { useCreateWorkItem, usePhaseCatalog, useWorkItems } from "./hooks";
import { workItemLink } from "../../links";
import { humanizeLabel, lifecyclePhaseColumns, phaseLabel } from "./phases";

// S-14 view states: board (default) · list · filtered (tasks only) · empty.
export type BoardView = "board" | "list" | "filtered" | "empty";

// Bugs S.No 117. An item nothing has run on yet has no phase, and the board dropped it into
// whichever column happened to be FIRST — Ideation on the default board, Implementation once
// filtered to Tasks — so brand-new work looked as if it were already under way, and the same item
// changed column when the filter changed. It has a column of its own now.
const BACKLOG_KEY = "backlog";
const BACKLOG = { key: BACKLOG_KEY, label: "Backlog" };
// The Phase filter's value for those items (the choice is labelled "Backlog", like the column).
const NOT_STARTED = "not_started";

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
  done: { variant: "done", label: "Done" },
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
// 2026-10-08: the pill and the Status filter are now ONE vocabulary. The filter used to list the
// item's stored state ("Proposed", "Done") while the card said something else ("Not started",
// "Done" about the PHASE), so the two could not be matched. Every situation now has one word,
// the same for every reader, and the filter offers exactly those words.
//
// "Yours" is no longer said in words ("Waiting for you" hid WHAT was being waited for, and meant
// something different to each reader). It is the pill's colour plus a small person marker —
// never colour alone, which a colour-blind reader or a screen reader cannot see (WCAG 1.4.1).
export type BoardStatusKey =
  | "not_started"
  | "running"
  | "paused"
  | "stalled"
  | "waiting_answer"
  | "waiting_review"
  | "done"
  | "failed"
  | "cancelled";

/** Filter order and wording. The card pill uses the same labels. */
export const BOARD_STATUSES: { key: BoardStatusKey; label: string }[] = [
  { key: "not_started", label: "Not started" },
  { key: "running", label: "Running" },
  { key: "paused", label: "Paused" },
  { key: "stalled", label: "Stopped responding" },
  { key: "waiting_answer", label: "Waiting for answer" },
  { key: "waiting_review", label: "Waiting for review" },
  { key: "done", label: "Done" },
  { key: "failed", label: "Failed" },
  { key: "cancelled", label: "Cancelled" },
];
const BOARD_STATUS_LABEL = new Map(BOARD_STATUSES.map((s) => [s.key, s.label]));

const BOARD_STATUS_VARIANT = {
  not_started: "queued",
  running: "running",
  // Outline, not a colour: a person stopped it on purpose, which is neither progress nor trouble.
  paused: "outline",
  // The same striped badge the run console uses for a run parked for takeover.
  stalled: "parked",
  waiting_answer: "neutral",
  waiting_review: "neutral",
  done: "done",
  failed: "failed",
  cancelled: "cancelled",
} satisfies Record<BoardStatusKey, BadgeVariant>;

// When it is the reader's to act on, the waiting pills keep the colours they had.
const YOURS_VARIANT: Partial<Record<BoardStatusKey, BadgeVariant>> = {
  waiting_answer: "needs-answer",
  waiting_review: "gate",
};

/** The one situation a card is in, and whether the reader can act on it. `key` is null only
 *  for a run status with no word of its own (an API older than this screen); the pill then
 *  falls back to the item's own badge and the card appears under "Status: All" only. */
export function boardStatus(card: WorkItemCard): { key: BoardStatusKey | null; yours: boolean } {
  // Cancelled outranks everything, for the reason `statusBadge` gives.
  if (card.state === "cancelled") return { key: "cancelled", yours: false };
  if (!card.current_phase) return { key: "not_started", yours: false };
  // `needs.yours` is decided by the same rule as the Approve and Answer buttons.
  if (card.needs?.clarification) return { key: "waiting_answer", yours: Boolean(card.needs.yours) };
  if (card.needs?.gate) return { key: "waiting_review", yours: Boolean(card.needs.yours) };
  switch (card.run_status) {
    case "pending":
    case "running":
      return { key: "running", yours: false };
    case "paused":
      return { key: "paused", yours: false };
    case "stalled":
      return { key: "stalled", yours: false };
    // At its gate, but no pending approval reached this card — nobody to name, so not "yours".
    case "awaiting_gate":
      return { key: "waiting_review", yours: false };
    case "approved":
    case "completed":
      return { key: "done", yours: false };
    // The same reading Phases & Runs gives a rejected run.
    case "failed":
    case "rejected":
      return { key: "failed", yours: false };
    default:
      return { key: null, yours: false };
  }
}

/** The status words a card shows, as plain text — the Board's own rule, so every screen that
 *  names a work item's status says the same thing (recon 2026-10-10, mockup M9). Falls back to
 *  the stored state only where the Board itself would. */
export function boardStatusLabel(card: WorkItemCard): string {
  const { key } = boardStatus(card);
  return (key && BOARD_STATUS_LABEL.get(key)) || STATE_BADGE[card.state]?.label || card.state;
}

function PersonMark() {
  return (
    <span className="badge__mine" title="You can act on this">
      <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor"
        strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="8" r="4" />
        <path d="M5 21v-1a7 7 0 0 1 14 0v1" />
      </svg>
      <span className="u-visually-hidden">You can act on this: </span>
    </span>
  );
}

function phasePill(card: WorkItemCard) {
  const { key, yours } = boardStatus(card);
  if (!key) return statusBadge(card);
  const variant = (yours && YOURS_VARIANT[key]) || BOARD_STATUS_VARIANT[key];
  return (
    <Badge variant={variant}>
      {yours && <PersonMark />}
      {BOARD_STATUS_LABEL.get(key)}
    </Badge>
  );
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
        {/* `parent_key` ("WI-260"), never `parent` — that is the raw UUID, and this chip printed
            all 36 characters of it on the busiest screen in the product. The chip's whole job is
            to say which item this belongs to, which a UUID does not do, so without a key there
            is nothing worth drawing. */}
        {card.parent_key && <Chip>↖ {card.parent_key}</Chip>}
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
  // QA created an item on a demo project, left the description empty, and then had no way back
  // in: the drawer had no field, and no screen could edit one afterwards. The API has accepted
  // `description` on create all along — only the input was missing. (`EditWorkItem` closes the
  // other half, so an item created without one is no longer stuck that way.)
  const [description, setDescription] = useState("");

  const titleValid = title.trim().length > 0;

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!titleValid) return;
    try {
      const created = await createWorkItem.mutateAsync({
        type,
        title: title.trim(),
        description: description.trim(),
      });
      onClose();
      navigate(`/work-items/${created.id}`);
    } catch {
      /* error surfaced inline below */
    }
  };

  // What each work-item type means, in plain language — no internal "tier" jargon
  // (Bugs.xlsx rows 21 iii + 36).
  //
  // The WORDS here are unchanged; only their presentation is. They used to be concatenated into
  // one string and rendered both as help text and as the select's hover tooltip, so a person
  // choosing a type read four definitions in a single unbroken paragraph that did not change
  // when they changed the selection. QA called it "plain text all mixed which is not readable",
  // and they were right: the user's actual problem is COMPARING epic against story before
  // picking, which a wall of prose makes hardest of all.
  //
  // Four labelled rows, with the selected one marked (team decision, option A). The duplicate
  // `title=` tooltip is gone — a hover repeating all four definitions was noise on top of noise.
  //
  // 2026-09-30, second pass: the rows now live behind the ⓘ beside the Type label rather than
  // sitting in the drawer permanently. The team's reasoning is that somebody creating their
  // fiftieth work item does not need four definitions re-explained every time, and they are
  // right — reference material that cannot be dismissed is just furniture the reader learns to
  // look past. `Tooltip` is the accessible one (focus and tap as well as hover, Escape to close,
  // `aria-describedby`), so this is not the hover-only tooltip its docstring refuses.
  const TYPE_HELP: Record<string, string> = {
    epic: "A large feature or initiative that goes through all the planning phases, from "
      + "Ideation to Task Breakdown.",
    story: "A smaller, user-facing piece of an epic, planned the same way.",
    task: "A concrete development job that gets implemented, code-reviewed and tested.",
    defect: "A bug fix that follows the shorter fix-and-verify flow.",
  };
  const TYPE_ORDER = ["epic", "story", "task", "defect"] as const;

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
        {/* Not `<Field>`, deliberately: `Field` renders a `<label>` around its children, and the
            ⓘ is a real `<button>`. A button inside a label is invalid markup — the label forwards
            the click to its control, so one press fires twice and the tooltip opens and shuts. The
            select carries its own `aria-label`, so nothing is lost by laying the row out here. */}
        <div className="field">
          <span className="field__label" id="wi-type-label">
            Type
            {/* `below`: this sits near the top of the drawer, where an upward bubble is
                off-screen. */}
            <Tooltip label="What the work item types mean" placement="below">
              <dl className="wi-type-legend wi-type-legend--tip">
                {TYPE_ORDER.map((t) => (
                  <div
                    key={t}
                    className={cx("wi-type-legend__row", t === type && "is-selected")}
                  >
                    <dt className="wi-type-legend__term">{typeLabel(t)}</dt>
                    <dd className="wi-type-legend__desc">{TYPE_HELP[t]}</dd>
                  </div>
                ))}
              </dl>
            </Tooltip>
          </span>
          <Select value={type} onChange={(e) => setType(e.target.value)} aria-label="Type">
            {TYPE_ORDER.map((t) => (
              <option key={t} value={t}>{typeLabel(t)}</option>
            ))}
          </Select>
        </div>

        <Field label="Description" help="Optional — you can add this later.">
          <textarea
            className="textarea"
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What needs to happen, and why."
          />
        </Field>
        {createWorkItem.isError && (
          <p className="t-sm" style={{ color: "var(--danger)" }}>
            {writeErrorSentence(createWorkItem.error, "Couldn't create this work item.")}
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
  const [reopening, setReopening] = useState<WorkItemCard | null>(null);
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

  // 2026-10-08: every filter lists its WHOLE vocabulary, in lifecycle order, with how many items
  // each choice would show. They used to list only what the loaded items happened to contain, so
  // a project with one run offered one phase, one role and two statuses, and read as broken.
  // Onboarding phases are left out for every project: they run on the project, never on a work
  // item, so no card can ever be in one (the same reason the board has no column for them).
  const phaseChoices = useMemo(
    () => [
      { key: NOT_STARTED, label: "Backlog" },
      ...lifecyclePhaseColumns().map((c) => ({ key: barePhase(c.key), label: phaseLabel(c.key) })),
    ],
    [],
  );
  // The roles that sign off a work item's phases, in the order their phases come. Engineer and
  // Admin approve no phase, so choosing them could only ever show an empty board.
  const roleChoices = useMemo(() => {
    const seen: string[] = [];
    for (const c of lifecyclePhaseColumns()) {
      const role = roleByPhase.get(barePhase(c.key));
      if (role && !seen.includes(role)) seen.push(role);
    }
    return seen.map((r) => ({ key: r, label: roleLabel(r) }));
  }, [roleByPhase]);

  // One test per filter, so a count can apply every filter EXCEPT its own.
  const matches = useMemo(() => {
    const phaseOf = (item: WorkItemCard) => barePhase(item.current_phase) || NOT_STARTED;
    return {
      phase: (item: WorkItemCard) => !phaseFilter || phaseOf(item) === phaseFilter,
      role: (item: WorkItemCard) =>
        !roleFilter || (roleByPhase.get(barePhase(item.current_phase)) ?? "") === roleFilter,
      status: (item: WorkItemCard) => {
        if (statusFilter) return boardStatus(item).key === statusFilter;
        // Bugs S.No 140: cancelled work is hidden by default. Cancelling exists to get things
        // OFF the board — leaving them on it would make cancelling pointless. Never hidden
        // outright, though: choosing "Cancelled" in the status filter shows exactly those, so
        // the record stays reachable and a cancellation can be found and questioned.
        return item.state !== "cancelled";
      },
      search: (item: WorkItemCard) => {
        if (!search) return true;
        const hay = `${item.key ?? ""} ${item.title ?? ""} ${item.type ?? ""} ${item.feature_stream ?? ""}`.toLowerCase();
        return hay.includes(search.toLowerCase());
      },
      phaseOf,
    };
  }, [phaseFilter, roleFilter, statusFilter, search, roleByPhase]);

  const list = useMemo(
    () => allItems.filter((i) => matches.phase(i) && matches.role(i) && matches.status(i) && matches.search(i)),
    [allItems, matches],
  );

  const phaseCounts = useMemo(() => {
    const pool = allItems.filter((i) => matches.role(i) && matches.status(i) && matches.search(i));
    const counts = new Map<string, number>();
    for (const i of pool) counts.set(matches.phaseOf(i), (counts.get(matches.phaseOf(i)) ?? 0) + 1);
    return { all: pool.length, counts };
  }, [allItems, matches]);
  const roleCounts = useMemo(() => {
    const pool = allItems.filter((i) => matches.phase(i) && matches.status(i) && matches.search(i));
    const counts = new Map<string, number>();
    for (const i of pool) {
      const role = roleByPhase.get(barePhase(i.current_phase));
      if (role) counts.set(role, (counts.get(role) ?? 0) + 1);
    }
    return { all: pool.length, counts };
  }, [allItems, matches, roleByPhase]);
  const statusCounts = useMemo(() => {
    const pool = allItems.filter((i) => matches.phase(i) && matches.role(i) && matches.search(i));
    const counts = new Map<string, number>();
    for (const i of pool) {
      const key = boardStatus(i).key;
      if (key) counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    // "All" never includes cancelled work (it is hidden until asked for), so neither does its count.
    return { all: pool.filter((i) => i.state !== "cancelled").length, counts };
  }, [allItems, matches]);
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

  // Only the BOARD gets the fixed-height treatment: it is the view whose columns grow without
  // limit (a 122-card Backlog made the page thousands of pixels tall and put the board's own
  // horizontal scrollbar below the fold). The list and empty views scroll the page as before.
  const boardShown = view !== "empty" && view !== "list";

  return (
    <div className={boardShown ? "canvas-pad canvas-pad--board" : "canvas-pad"}>
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
          {/* Sized to the longest phase name rather than capped by eye: "Intelligent Context
              Extraction" used to be cut in the closed box with no way to read it. */}
          <FilterSelect
            label="Filter by phase"
            prefix="Phase"
            allLabel="All phases"
            allCount={phaseCounts.all}
            options={phaseChoices.map((p) => ({
              value: p.key, label: p.label, count: phaseCounts.counts.get(p.key) ?? 0,
            }))}
            value={phaseFilter}
            onChange={setPhaseFilter}
          />
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
          <FilterSelect
            label="Filter by role"
            prefix="Role"
            allLabel="All roles"
            allCount={roleCounts.all}
            options={roleChoices.map((r) => ({
              value: r.key, label: r.label, count: roleCounts.counts.get(r.key) ?? 0,
            }))}
            value={roleFilter}
            onChange={setRoleFilter}
          />
          <FilterSelect
            label="Filter by status"
            prefix="Status"
            allLabel="All statuses"
            allCount={statusCounts.all}
            options={BOARD_STATUSES.map((st) => ({
              value: st.key, label: st.label, count: statusCounts.counts.get(st.key) ?? 0,
            }))}
            value={statusFilter}
            onChange={setStatusFilter}
          />
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
              // Mockup M9: the Board's pill, not the stored state. A new defect read "Not
              // started" on the Board and "In progress" here — one item, two statuses.
              phasePill(item),
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
                  // Three cases, not two. A cancelled item is terminal but not finished, and
                  // cancelling is the platform's only closure — there is no delete — so this
                  // menu is the only place a mis-click can be undone. It is also the natural
                  // one: the "N cancelled hidden" chip above filters to exactly these rows.
                  ...(item.state === "cancelled"
                    ? [{ label: "Reopen…", onSelect: () => setReopening(item) }]
                    : isTerminalState(item.state)
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

      {reopening && (
        <ReopenWorkItem workItem={reopening} onClose={() => setReopening(null)} />
      )}
    </div>
  );
}
