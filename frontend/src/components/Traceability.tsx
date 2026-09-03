// Traceability viewer (spec §5) — the provenance lineage requirement→PRD→epic→story.
// Walks the TraceEdge DAG from its roots and renders each node indented under its
// parent, deep-linking to the live SoR (Confluence page / Jira issue) via node.url.
import { useEffect, useState } from "react";

import { api, ApiError } from "../api";
import { useApp } from "../state";
import type { TraceGraph, TraceNode } from "../types";

interface Row {
  node: TraceNode;
  rel: string | null; // relation from the parent edge (null for roots)
  depth: number;
  cycle?: boolean;
}

function flatten(graph: TraceGraph): Row[] {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const childrenOf = new Map<string, { to: string; rel: string }[]>();
  const hasIncoming = new Set<string>();
  for (const e of graph.edges) {
    if (!childrenOf.has(e.from)) childrenOf.set(e.from, []);
    childrenOf.get(e.from)!.push({ to: e.to, rel: e.rel });
    hasIncoming.add(e.to);
  }
  const roots = graph.nodes.filter((n) => !hasIncoming.has(n.id));

  const rows: Row[] = [];
  const walk = (id: string, rel: string | null, depth: number, seen: Set<string>) => {
    const node = byId.get(id);
    if (!node) return;
    if (seen.has(id)) {
      rows.push({ node, rel, depth, cycle: true });
      return;
    }
    rows.push({ node, rel, depth });
    const next = new Set(seen).add(id);
    for (const child of childrenOf.get(id) ?? []) walk(child.to, child.rel, depth + 1, next);
  };
  for (const r of roots) walk(r.id, null, 0, new Set());
  return rows;
}

export function Traceability() {
  const { tenantId, project } = useApp();
  const [graph, setGraph] = useState<TraceGraph>({ nodes: [], edges: [] });
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!tenantId || !project) return;
    void (async () => {
      try {
        setGraph(await api.getTraceability(tenantId, project.id));
        setErr(null);
      } catch (e) {
        setErr(e instanceof ApiError ? e.message : String(e));
      }
    })();
  }, [tenantId, project]);

  const rows = flatten(graph);

  return (
    <div className="panel">
      <h2>Traceability</h2>
      {err && <div className="err">{err}</div>}
      {rows.length === 0 ? (
        <div className="empty">
          No lineage yet. Edges are written when a phase derives from a prior artifact
          (requirement → PRD → epic → story).
        </div>
      ) : (
        <div>
          {rows.map((r, i) => (
            <div
              key={`${r.node.id}-${i}`}
              className="flex"
              style={{ marginLeft: r.depth * 24, padding: "6px 0",
                       borderBottom: "1px solid var(--border)" }}
            >
              {r.rel && <span className="badge">{r.rel} →</span>}
              <span className="mono">{r.node.phase}:{r.node.type}</span>
              <span className={`badge ${r.node.status}`}>{r.node.status}</span>
              <span className="badge">{r.node.sor}</span>
              {r.node.url && (
                <a href={r.node.url} target="_blank" rel="noreferrer">↗ open in {r.node.sor}</a>
              )}
              {r.cycle && <span className="muted">(cycle)</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
