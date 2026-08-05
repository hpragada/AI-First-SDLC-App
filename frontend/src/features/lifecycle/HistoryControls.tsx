// Shared controls for the two history views — decided gates (S-21) and answered clarifications.
// Both are records rather than queues: they grow forever, they are read back weeks later, and
// they are searched by "which work item" and "which phase". Keeping the controls in one place is
// what stops the two screens drifting into looking like different products.
import { Button, Select } from "../../components/ui";
import { usePhaseCatalog } from "./hooks";
import { phaseLabel } from "./phases";

// A clarification stores its phase as the bare slug the run carried (`ideation`, `prd`), while
// an approval's phase is the agent key that opened it (`01_ideation`, `03_prd`). Same concept,
// two vocabularies, so the filter has to speak whichever the endpoint expects. Stripping the
// ordinal prefix is the whole difference.
export function phaseSlug(agentKey: string): string {
  return agentKey.replace(/^\d+[a-z]?_/, "");
}

export function PhaseFilter({
  value,
  onChange,
  as,
}: {
  value: string;
  onChange: (v: string) => void;
  // "key" → send the agent key (approvals). "slug" → send the bare phase (clarifications).
  as: "key" | "slug";
}) {
  const catalog = usePhaseCatalog();
  const entries = [
    ...(catalog.data?.plan ?? []),
    ...(catalog.data?.build ?? []),
    ...(catalog.data?.remediation ?? []),
  ];
  return (
    <Select
      aria-label="Filter by phase"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">All phases</option>
      {entries.map((p) => (
        <option key={p.agent_key} value={as === "key" ? p.agent_key : phaseSlug(p.agent_key)}>
          {phaseLabel(p.agent_key)}
        </option>
      ))}
    </Select>
  );
}

export function WorkItemFilter({
  value,
  onChange,
  items,
}: {
  value: string;
  onChange: (v: string) => void;
  items: { id: string; title?: string; type?: string }[];
}) {
  return (
    <Select
      aria-label="Filter by work item"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">All work items</option>
      {items.map((w) => (
        <option key={w.id} value={w.id}>
          {w.title || w.type || w.id.slice(0, 8)}
        </option>
      ))}
    </Select>
  );
}

// Page numbers, not infinite scroll. These are records people cite ("what did we decide about
// probation leave, and when") — a page you can return to beats a scroll position you can't.
export function Pager({
  page,
  count,
  pageSize,
  onPage,
  noun,
}: {
  page: number;
  count: number;
  pageSize: number;
  onPage: (p: number) => void;
  noun: string;
}) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (count === 0) return null;
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, count);
  return (
    <div
      className="u-row"
      style={{ justifyContent: "space-between", alignItems: "center", marginTop: "var(--space-4)" }}
    >
      <span className="t-sm u-muted">
        {first}–{last} of {count} {noun}
      </span>
      <span className="u-row" style={{ gap: "var(--space-2)" }}>
        <Button variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Previous
        </Button>
        <span className="t-sm u-muted">
          Page {page} of {pages}
        </span>
        <Button variant="ghost" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next
        </Button>
      </span>
    </div>
  );
}
