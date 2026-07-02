import { useNavigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { EmptyState, GraphCanvas, Panel, Spinner } from "../../components/ui";
import type { TraceGraph } from "../../types";
import { useTraceability } from "./hooks";

// S-30 view states: small (default) · highlighted (WI-492 lineage) · large-cluster
// · empty.
export type TraceabilityViewState = "small" | "highlighted" | "large-cluster" | "empty";

function nodeColor(status: string) {
  if (status === "published") return "var(--success)";
  if (status === "pending_gate" || status === "gate") return "var(--warning)";
  return "var(--info)";
}

const LEGEND = (
  <span className="graph-legend">
    <span className="graph-legend__item">
      <span className="graph-legend__dot" style={{ background: "var(--success)" }} />
      Published
    </span>
    <span className="graph-legend__item">
      <span className="graph-legend__dot" style={{ background: "var(--warning)" }} />
      Pending gate
    </span>
    <span className="graph-legend__item">
      <span className="graph-legend__dot" style={{ background: "var(--info)" }} />
      Draft
    </span>
  </span>
);

export function TraceabilityView({ forceView }: { forceView?: TraceabilityViewState }) {
  if (forceView) return <TraceabilityGallery view={forceView} />;
  return <TraceabilityLive />;
}

// ── Live: the real lineage graph for the selected project ──────────────────
function TraceabilityLive() {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const graph = useTraceability(projectId);

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
        <span className="u-spacer" />
        {LEGEND}
      </div>

      {graph.isLoading ? (
        <Panel>
          <Spinner /> Loading traceability graph…
        </Panel>
      ) : !graph.data || graph.data.nodes.length === 0 ? (
        <Panel>
          <EmptyState
            title="No lineage yet"
            text="Once phases produce artifacts and tasks, their relationships render here as a graph."
          />
        </Panel>
      ) : (
        <LineageGraph graph={graph.data} />
      )}
    </div>
  );
}

function LineageGraph({ graph }: { graph: TraceGraph }) {
  const navigate = useNavigate();
  const cols = 4;
  const boxW = 150;
  const boxH = 44;
  const gapX = 100;
  const gapY = 90;
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
            return (
              <g
                key={n.id}
                transform={`translate(${pos.x},${pos.y})`}
                style={{ cursor: "pointer" }}
                role="button"
                tabIndex={0}
                onClick={go}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && go()}
              >
                <rect width={boxW} height={boxH} rx="8" className="gnode" style={{ stroke: nodeColor(n.status) }} />
                <circle cx="16" cy="22" r="5" style={{ fill: nodeColor(n.status) }} />
                <text x="30" y="20" style={{ fill: "var(--text-strong)", fontSize: "12px", fontWeight: 600 }}>
                  {n.type.length > 16 ? `${n.type.slice(0, 16)}…` : n.type}
                </text>
                <text x="30" y="35" style={{ fill: "var(--text-muted)", fontSize: "11px" }}>
                  {n.phase} · {n.status}
                </text>
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

      <div className="u-row u-wrap" style={{ marginBottom: "var(--space-4)" }}>
        <select className="select" style={{ maxWidth: "170px" }} aria-label="Filter by phase">
          <option>Phase: All</option>
        </select>
        <select className="select" style={{ maxWidth: "150px" }} aria-label="Filter by type">
          <option>Type: All</option>
        </select>
        <select className="select" style={{ maxWidth: "200px" }} aria-label="Highlight work item">
          <option>Highlight: WI-492 lineage</option>
          <option>None</option>
        </select>
        <span className="u-spacer" />
        {LEGEND}
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
