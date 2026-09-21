// B2 (Hybrid Option C): the Task Breakdown repo-assignment review, shown on the gate (Decision
// 1). The planner proposed a repo for each task; the reviewer confirms or overrides here before
// approving. Low-confidence tasks are surfaced FIRST and expanded; the confident repo groups are
// collapsed (a count + a chevron) so the reviewer isn't buried in 30+ obvious rows (Decision 3 —
// grouped by repo). Nothing is committed until the gate is approved.
import { useState } from "react";

import { repoRoleLabel } from "../../labels";
import type { Repository, WorkItemCard } from "../../types";

const roleClass = (role: string) =>
  role === "frontend" ? "chip--frontend" : role === "infra" ? "chip--infra" : "chip--backend";

function repoOf(repos: Repository[], id: string | null | undefined) {
  return repos.find((r) => r.id === id);
}

function AssignRow({
  item,
  repos,
  flagged,
  onOverride,
  onKeep,
  busy,
}: {
  item: WorkItemCard;
  repos: Repository[];
  flagged: boolean;
  onOverride: (id: string, repoId: string) => void;
  onKeep: (id: string) => void;
  busy: boolean;
}) {
  const a = item.external_ref?.repo_assignment;
  return (
    <div className="trow" style={flagged ? { background: "var(--warning-bg)" } : undefined}>
      <div className="trow__main">
        <div className="t-sm u-strong">{item.title || item.key || item.id.slice(0, 8)}</div>
        {/* the reason is only worth showing for the flagged (uncertain) tasks */}
        {flagged && a?.rationale && (
          <div className="t-xs u-muted" style={{ marginTop: 2 }}>{a.rationale}</div>
        )}
      </div>
      <select
        className="select"
        // fixed flex-basis so the dropdown doesn't inherit `.select{width:100%}` and crush the
        // title; can shrink to 200px on narrow screens, never grows past the title.
        style={{ flex: "0 1 320px", minWidth: 200 }}
        value={item.repo ?? ""}
        disabled={busy}
        onChange={(e) => onOverride(item.id, e.target.value)}
        aria-label={`Repository for ${item.key || item.id}`}
      >
        {/* Screen Words group 4: the stored role word through the shared map. */}
        <option value="">— Not assigned —</option>
        {repos.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name} · {repoRoleLabel(r.role)}
          </option>
        ))}
      </select>
      {flagged && (
        <button className="btn btn--secondary btn--sm" disabled={busy} onClick={() => onKeep(item.id)}>
          Keep
        </button>
      )}
    </div>
  );
}

export function RepoAssignmentReview({
  items,
  repos,
  confirmed,
  onOverride,
  onKeep,
  busy,
}: {
  items: WorkItemCard[];
  repos: Repository[];
  confirmed: Record<string, boolean>;
  onOverride: (id: string, repoId: string) => void;
  onKeep: (id: string) => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});

  const flagged = items.filter(
    (w) => w.external_ref?.repo_assignment?.confidence === "low" && !confirmed[w.id],
  );
  const flaggedIds = new Set(flagged.map((w) => w.id));
  const rest = items.filter((w) => !flaggedIds.has(w.id));

  const groups = new Map<string, WorkItemCard[]>();
  for (const w of rest) {
    const key = w.repo ?? "unassigned";
    const g = groups.get(key);
    if (g) g.push(w);
    else groups.set(key, [w]);
  }

  return (
    <div>
      {/* summary: total + the split by repo + how many need review */}
      <div className="u-row u-wrap" style={{ gap: "var(--space-2)", marginBottom: "var(--space-3)" }}>
        <span className="t-sm u-strong">{items.length} tasks</span>
        {[...groups.entries()].map(([id, ws]) => {
          const r = repoOf(repos, id === "unassigned" ? undefined : id);
          return (
            <span key={id} className={`chip ${r ? roleClass(r.role) : ""}`}>
              {/* Screen Words group 4 */}
              {r ? repoRoleLabel(r.role) : "Not assigned"} · {ws.length}
            </span>
          );
        })}
        {flagged.length > 0 && <span className="chip chip--low">{flagged.length} need review</span>}
      </div>

      {/* flagged tasks — always expanded, at the top */}
      {flagged.length > 0 && (
        <div className="panel" style={{ marginBottom: "var(--space-3)" }}>
          <div className="repogroup__head">
            <span className="chip chip--low">needs review</span>
            <span className="t-xs u-muted">
              {flagged.length} the planner wasn't sure about — confirm or change the repo
            </span>
          </div>
          {flagged.map((w) => (
            <AssignRow key={w.id} item={w} repos={repos} flagged onOverride={onOverride} onKeep={onKeep} busy={busy} />
          ))}
        </div>
      )}

      {/* confident groups — collapsed by default; click the header to expand */}
      {[...groups.entries()].map(([repoId, ws]) => {
        const r = repoOf(repos, repoId === "unassigned" ? undefined : repoId);
        const isOpen = Boolean(open[repoId]);
        return (
          <div className="panel" key={repoId} style={{ marginBottom: "var(--space-2)" }}>
            <button
              type="button"
              className="repogroup__head"
              style={{ width: "100%", border: "none", background: "var(--bg-subtle)", cursor: "pointer", textAlign: "left" }}
              aria-expanded={isOpen}
              onClick={() => setOpen((o) => ({ ...o, [repoId]: !o[repoId] }))}
            >
              <span aria-hidden style={{ fontFamily: "var(--font-mono)" }}>{isOpen ? "▾" : "▸"}</span>
              {r ? (
                <span className={`chip ${roleClass(r.role)}`}>{repoRoleLabel(r.role)}</span>
              ) : (
                <span className="chip">Not assigned</span>
              )}
              <span className="t-sm u-strong" style={{ fontFamily: "var(--font-mono)" }}>{r?.name ?? "—"}</span>
              <span className="t-xs u-muted">· {ws.length} tasks · all confident</span>
            </button>
            {isOpen &&
              ws.map((w) => (
                <AssignRow key={w.id} item={w} repos={repos} flagged={false} onOverride={onOverride} onKeep={onKeep} busy={busy} />
              ))}
          </div>
        );
      })}
    </div>
  );
}
