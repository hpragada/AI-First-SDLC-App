import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { EmptyState, ErrorState, GraphCanvas, Panel, Spinner } from "../../components/ui";
import type { TraceGraph, TraceNode } from "../../types";
import { phaseLabel, artifactLabel } from "../lifecycle/phases";
import { ARTIFACT_STATUSES, artifactStatusColor, artifactStatusLabel } from "./artifactStatus";
import { useTraceability } from "./hooks";

// S-30 view states: small (default) · highlighted (WI-492 lineage) · large-cluster
// · empty.
export type TraceabilityViewState = "small" | "highlighted" | "large-cluster" | "empty";

/** The Highlight choice for documents that belong to no work item (adopted in onboarding).
 *  A UUID can never collide with it. */
const UNTIED = "untied";

// Node colours and the legend that explains them come from the shared status map (Bugs S.No 218).
// This screen kept its own three-way copy that knew only "published" and a status nothing ever
// set ("pending_gate"), so an approved, a waiting and a superseded document all drew as "Draft" —
// and the legend promised a colour no node could have.
//
// 2026-10-08: the live map's legend explains only the statuses actually ON the map. All five
// were always listed, so a map of nothing but published documents carried four colours that
// explained nothing — and "Approved", which only a signed accessibility conformance report ever
// reaches (a phase approval publishes straight away), read as stale. Same rule as the filters
// beside it: never offer what matches nothing.
function Legend({ statuses = ARTIFACT_STATUSES }: { statuses?: readonly string[] }) {
  const present = new Set(statuses);
  return (
    <span className="graph-legend">
      {ARTIFACT_STATUSES.filter((s) => present.has(s)).map((status) => (
        <span className="graph-legend__item" key={status}>
          <span className="graph-legend__dot" style={{ background: artifactStatusColor(status) }} />
          {artifactStatusLabel(status)}
        </span>
      ))}
      {/* A status this map does not know still gets explained, in its own words. */}
      {[...present].filter((s) => !(ARTIFACT_STATUSES as readonly string[]).includes(s)).map((s) => (
        <span className="graph-legend__item" key={s}>
          <span className="graph-legend__dot" style={{ background: artifactStatusColor(s) }} />
          {artifactStatusLabel(s)}
        </span>
      ))}
    </span>
  );
}

export function TraceabilityView({ forceView }: { forceView?: TraceabilityViewState }) {
  if (forceView) return <TraceabilityGallery view={forceView} />;
  return <TraceabilityLive />;
}

// ── Live: the real lineage graph for the selected project ──────────────────
function TraceabilityLive() {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const graph = useTraceability(projectId);

  // Filters this screen was drawn with and never given (P3). They existed only in the component
  // gallery, wired to nothing and offering a work item invented during the build ("WI-492"); the
  // real screen shipped with the legend alone. On a project with a few hundred documents that is
  // a wall of boxes with no way in, and no way to answer the question the map exists for: what
  // came out of THIS piece of work.
  //
  // Phase and type NARROW the map; a work item HIGHLIGHTS instead — its documents stay lit and
  // everything else dims rather than disappearing, so the chain is readable without losing the
  // surrounding shape. Options are the values actually present, the same rule the Artifacts
  // screen follows, so a filter can never offer something that matches nothing.
  const [phase, setPhase] = useState("");
  const [type, setType] = useState("");
  const [highlight, setHighlight] = useState("");
  const nodes = graph.data?.nodes ?? [];

  const phaseOptions = useMemo(
    () => [...new Set(nodes.map((n) => n.phase))].filter(Boolean).sort(), [nodes]);
  const typeOptions = useMemo(
    () => [...new Set(nodes.map((n) => n.type))].filter(Boolean).sort(), [nodes]);
  // One entry per work item on the map, plus — when the project has any — the documents that
  // belong to no work item at all. Those are the ones adopted during brownfield onboarding: no
  // run produced them, so they have no work item, and leaving them out of the list would make
  // them the one group the filter could never reach.
  const workItemOptions = useMemo(() => {
    const byId = new Map<string, string>();
    let untied = false;
    for (const n of nodes) {
      if (n.work_item) {
        byId.set(n.work_item, [n.work_item_key, n.work_item_title].filter(Boolean).join(" ")
          || "Untitled work item");
      } else {
        untied = true;
      }
    }
    const list = [...byId].map(([value, label]) => ({ value, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
    if (untied) list.push({ value: UNTIED, label: "Not tied to a work item" });
    return list;
  }, [nodes]);

  const shown = useMemo(
    () => nodes.filter((n) => (!phase || n.phase === phase) && (!type || n.type === type)),
    [nodes, phase, type],
  );
  // Dimmed, not hidden: the answer to "what belongs to this work item" is clearer when the rest
  // of the map is still in view behind it.
  const dimmed = useMemo(() => {
    if (!highlight) return undefined;
    const lit = (n: TraceNode) =>
      highlight === UNTIED ? !n.work_item : n.work_item === highlight;
    return new Set(shown.filter((n) => !lit(n)).map((n) => n.id));
  }, [shown, highlight]);

  const filtered: TraceGraph = useMemo(() => {
    const ids = new Set(shown.map((n) => n.id));
    return {
      nodes: shown,
      edges: (graph.data?.edges ?? []).filter((e) => ids.has(e.from) && ids.has(e.to)),
    };
  }, [shown, graph.data]);

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Traceability</h1>
          <p className="page-head__sub">
            Artifact lineage — what derives from what, which tasks implement which requirement,
            which tests cover which task. Click a node to preview or deep-link.
          </p>
        </div>
      </div>

      <div className="u-row u-wrap" style={{ marginBottom: "var(--space-4)" }}>
        <select
          className="select select--fit"
          aria-label="Filter by phase"
          value={phase}
          onChange={(e) => setPhase(e.target.value)}
        >
          <option value="">Phase: All</option>
          {phaseOptions.map((p) => (
            <option key={p} value={p}>{phaseLabel(p)}</option>
          ))}
        </select>
        <select
          className="select select--fit"
          aria-label="Filter by type"
          value={type}
          onChange={(e) => setType(e.target.value)}
        >
          <option value="">Type: All</option>
          {typeOptions.map((t) => (
            <option key={t} value={t}>{phaseLabel(t)}</option>
          ))}
        </select>
        <select
          className="select select--fit"
          aria-label="Highlight work item"
          value={highlight}
          onChange={(e) => setHighlight(e.target.value)}
        >
          {/* 2026-10-08: "Highlight: none" read like "no results" and never said WHAT is
              highlighted. Each choice carries the prefix so the closed box reads
              "Highlight: WI-1 …" once one is picked. */}
          <option value="">Highlight: All work items</option>
          {workItemOptions.map((w) => (
            <option key={w.value} value={w.value}>{`Highlight: ${w.label}`}</option>
          ))}
        </select>
        {/* The number is the honest part of a filtered view: a map showing 12 of 340 documents
            looks much like a small project unless it says so. */}
        {(phase || type) && nodes.length > 0 && (
          <span className="t-sm u-muted">
            {shown.length} of {nodes.length} shown
          </span>
        )}
        <span className="u-spacer" />
        <Legend statuses={[...new Set(filtered.nodes.map((n) => n.status))]} />
      </div>

      {graph.isLoading ? (
        <Panel>
          <Spinner /> Loading traceability graph…
        </Panel>
      ) : graph.isError ? (
        // S.No 220: `!graph.data` is true both when the project has no lineage yet and when the
        // request failed, and the branch below tells the user the reassuring one. Check the
        // failure FIRST.
        <Panel>
          <ErrorState
            title="We couldn't load the traceability graph"
            detail={graph.error}
            onRetry={() => void graph.refetch()}
          />
        </Panel>
      ) : !graph.data || graph.data.nodes.length === 0 ? (
        <Panel>
          <EmptyState
            title="No lineage yet"
            text="Once phases produce artifacts and tasks, their relationships render here as a graph."
          />
        </Panel>
      ) : filtered.nodes.length === 0 ? (
        // The project HAS lineage; this filter matched none of it. Saying "no lineage yet" here
        // would be the same untruth the Artifacts screen was fixed for.
        <Panel>
          <EmptyState
            title="Nothing matches these filters"
            text="Clear the phase or type filter to see the whole map."
          />
        </Panel>
      ) : (
        <LineageGraph graph={filtered} dimmed={dimmed} />
      )}
    </div>
  );
}

function LineageGraph({ graph, dimmed }: { graph: TraceGraph; dimmed?: Set<string> }) {
  const navigate = useNavigate();
  // 2026-10-08: three per row and wider, with the name wrapping onto a second line (team choice
  // B). Boxes were 150 wide, four to a row, and the name was cut by COUNTING 22 letters — which at
  // this font is wider than the box, so the text ran out past the border.
  const cols = 3;
  const boxW = 240;
  const boxH = 62;
  const gapX = 90;
  const gapY = 80;
  const marginX = 20;
  const marginY = 40;

  const positions = new Map<string, { x: number; y: number }>();
  graph.nodes.forEach((n, i) => {
    const row = Math.floor(i / cols);
    const col = i % cols;
    positions.set(n.id, {
      x: marginX + col * (boxW + gapX),
      y: marginY + row * (boxH + gapY),
    });
  });
  const rows = Math.ceil(graph.nodes.length / cols);
  const width = marginX * 2 + cols * boxW + (cols - 1) * gapX;
  const height = marginY * 2 + rows * boxH + (rows - 1) * gapY;

  return (
    <GraphCanvas>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label="Lineage graph">
        <g className="gedge">
          {graph.edges.map((e, i) => {
            const from = positions.get(e.from);
            const to = positions.get(e.to);
            if (!from || !to) return null;
            return (
              <line
                key={i}
                x1={from.x + boxW}
                y1={from.y + boxH / 2}
                x2={to.x}
                y2={to.y + boxH / 2}
              />
            );
          })}
        </g>
        <g fontFamily="var(--font-sans)">
          {graph.nodes.map((n) => {
            const pos = positions.get(n.id)!;
            const go = () => (n.url ? window.open(n.url, "_blank", "noopener") : navigate(`/artifacts/${n.id}`));
            const label = artifactLabel(n.title, n.type);  // human name, not the raw type (S.No 120)
            // The status in words, not the machine token it used to print (S.No 218). Cut to
            // the box the way the title is; the full line is the node's <title>, so hovering
            // shows it and a screen reader announces it as the node's name.
            const detail = `${phaseLabel(n.phase)} · ${artifactStatusLabel(n.status)}`;
            const color = artifactStatusColor(n.status);
            return (
              <g
                key={n.id}
                transform={`translate(${pos.x},${pos.y})`}
                // Outside the highlighted work item's chain: still there, still clickable, just
                // quiet.
                style={{ cursor: "pointer", opacity: dimmed?.has(n.id) ? 0.28 : 1 }}
                role="button"
                tabIndex={0}
                onClick={go}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && go()}
              >
                <title>{`${label} — ${detail}`}</title>
                <rect width={boxW} height={boxH} rx="8" className="gnode" style={{ stroke: color }} />
                <circle cx="16" cy="18" r="5" style={{ fill: color }} />
                {/* HTML inside the box, so the BROWSER measures the text: up to two lines of name,
                    then "…", always inside the border. The full name is the node's <title>. */}
                <foreignObject x="28" y="6" width={boxW - 38} height={boxH - 12}>
                  <div className="gnode__text">
                    <span className="gnode__title">{label}</span>
                    <span className="gnode__detail">{detail}</span>
                  </div>
                </foreignObject>
              </g>
            );
          })}
        </g>
      </svg>
    </GraphCanvas>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
function TraceabilityGallery({ view }: { view: TraceabilityViewState }) {
  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Traceability</h1>
          <p className="page-head__sub">
            Artifact lineage — what derives from what, which tasks implement which requirement,
            which tests cover which task. Click a node to preview or deep-link.
          </p>
        </div>
      </div>

      {/* The three dropdowns that used to sit here are gone. They were wired to nothing, and one
          offered "Highlight: WI-492 lineage" — a work item invented during the build, which
          exists in no project. The live screen above has the real filters; a gallery state is
          for showing the map's own states, not for pretending controls work. */}
      <div className="u-row u-wrap" style={{ marginBottom: "var(--space-4)" }}>
        <span className="u-spacer" />
        <Legend />
      </div>

      {view === "empty" ? (
        <Panel>
          <EmptyState
            title="No lineage yet"
            text="Once phases produce artifacts and tasks, their relationships render here as a graph."
          />
        </Panel>
      ) : view === "large-cluster" ? (
        <GraphCanvas style={{ position: "relative" }}>
          <div className="u-row-tight" style={{ position: "absolute", top: "8px", right: "8px", zIndex: 1 }}>
            <button className="btn btn--secondary btn--sm">−</button>
            <button className="btn btn--secondary btn--sm">+</button>
            <button className="btn btn--secondary btn--sm">Fit</button>
          </div>
          <svg viewBox="0 0 920 360" width="100%" role="img" aria-label="Large lineage cluster">
            <g className="gedge">
              <line x1="120" y1="60" x2="120" y2="120" />
              <line x1="120" y1="60" x2="320" y2="60" />
              <line x1="520" y1="120" x2="720" y2="60" />
            </g>
            <g fontFamily="var(--font-sans)">
              <g transform="translate(60,40)">
                <rect width="120" height="40" rx="7" className="gnode" style={{ stroke: "var(--success)" }} />
                <text x="14" y="24" style={{ fill: "var(--text-strong)", fontSize: "11px", fontWeight: 600 }}>Ideation</text>
              </g>
              <g transform="translate(260,40)">
                <rect width="120" height="40" rx="7" className="gnode" style={{ stroke: "var(--success)" }} />
                <text x="14" y="24" style={{ fill: "var(--text-strong)", fontSize: "11px", fontWeight: 600 }}>PRD</text>
              </g>
              <g transform="translate(460,100)">
                <rect width="120" height="40" rx="7" className="gnode" style={{ stroke: "var(--border-strong)" }} />
                <text x="14" y="24" style={{ fill: "var(--text-strong)", fontSize: "11px", fontWeight: 600 }}>Tasks ×6</text>
              </g>
            </g>
          </svg>
        </GraphCanvas>
      ) : view === "highlighted" ? (
        <GraphCanvas>
          <svg viewBox="0 0 920 320" width="100%" role="img" aria-label="Highlighted lineage">
            <g className="gedge">
              <line x1="170" y1="80" x2="250" y2="80" style={{ stroke: "var(--brand-orange)", strokeWidth: 2.5 }} />
              <line x1="400" y1="80" x2="480" y2="80" style={{ stroke: "var(--brand-orange)", strokeWidth: 2.5 }} />
              <line x1="400" y1="80" x2="480" y2="200" style={{ opacity: 0.3 }} />
            </g>
            <g fontFamily="var(--font-sans)">
              <g transform="translate(20,58)">
                <rect width="150" height="44" rx="8" className="gnode" style={{ stroke: "var(--brand-orange)", strokeWidth: 2 }} />
                <circle cx="16" cy="22" r="5" style={{ fill: "var(--success)" }} />
                <text x="30" y="20" style={{ fill: "var(--text-strong)", fontSize: "12px", fontWeight: 600 }}>Requirements</text>
                <text x="30" y="35" style={{ fill: "var(--text-muted)", fontSize: "11px" }}>v1.0</text>
              </g>
              <g transform="translate(250,58)">
                <rect width="150" height="44" rx="8" className="gnode" style={{ stroke: "var(--brand-orange)", strokeWidth: 2 }} />
                <circle cx="16" cy="22" r="5" style={{ fill: "var(--success)" }} />
                <text x="30" y="20" style={{ fill: "var(--text-strong)", fontSize: "12px", fontWeight: 600 }}>PRD v1.2</text>
                <text x="30" y="35" style={{ fill: "var(--text-muted)", fontSize: "11px" }}>Published</text>
              </g>
              <g transform="translate(480,58)">
                <rect width="150" height="44" rx="8" className="gnode" style={{ stroke: "var(--brand-orange)", strokeWidth: 2 }} />
                <circle cx="16" cy="22" r="5" style={{ fill: "var(--warning)" }} />
                <text x="30" y="20" style={{ fill: "var(--text-strong)", fontSize: "12px", fontWeight: 600 }}>Seq. Diagram</text>
                <text x="30" y="35" style={{ fill: "var(--text-muted)", fontSize: "11px" }}>v0.9 · Pending</text>
              </g>
            </g>
          </svg>
        </GraphCanvas>
      ) : (
        // small graph (default)
        <GraphCanvas>
          <svg viewBox="0 0 920 320" width="100%" role="img" aria-label="Lineage graph for WI-492">
            <g className="gedge">
              <line x1="170" y1="80" x2="250" y2="80" />
              <line x1="400" y1="80" x2="480" y2="80" />
              <line x1="400" y1="80" x2="480" y2="200" />
              <line x1="630" y1="80" x2="710" y2="80" />
              <line x1="630" y1="200" x2="710" y2="200" />
            </g>
            <g fontFamily="var(--font-sans)">
              <g transform="translate(20,58)">
                <rect width="150" height="44" rx="8" className="gnode" style={{ stroke: "var(--success)" }} />
                <circle cx="16" cy="22" r="5" style={{ fill: "var(--success)" }} />
                <text x="30" y="20" style={{ fill: "var(--text-strong)", fontSize: "12px", fontWeight: 600 }}>Requirements</text>
                <text x="30" y="35" style={{ fill: "var(--text-muted)", fontSize: "11px" }}>v1.0 · Confluence</text>
              </g>
              <g transform="translate(250,58)">
                <rect width="150" height="44" rx="8" className="gnode" style={{ stroke: "var(--success)" }} />
                <circle cx="16" cy="22" r="5" style={{ fill: "var(--success)" }} />
                <text x="30" y="20" style={{ fill: "var(--text-strong)", fontSize: "12px", fontWeight: 600 }}>PRD v1.2</text>
                <text x="30" y="35" style={{ fill: "var(--text-muted)", fontSize: "11px" }}>Published</text>
              </g>
              <g transform="translate(480,58)">
                <rect width="150" height="44" rx="8" className="gnode" style={{ stroke: "var(--warning)" }} />
                <circle cx="16" cy="22" r="5" style={{ fill: "var(--warning)" }} />
                <text x="30" y="20" style={{ fill: "var(--text-strong)", fontSize: "12px", fontWeight: 600 }}>Seq. Diagram</text>
                <text x="30" y="35" style={{ fill: "var(--text-muted)", fontSize: "11px" }}>v0.9 · Pending</text>
              </g>
            </g>
          </svg>
        </GraphCanvas>
      )}
    </div>
  );
}
