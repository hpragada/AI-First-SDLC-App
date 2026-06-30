import { EmptyState, GraphCanvas, Panel } from "../../components/ui";

// S-30 view states: small (default) · highlighted (WI-492 lineage) · large-cluster
// · empty.
export type TraceabilityViewState = "small" | "highlighted" | "large-cluster" | "empty";

export function TraceabilityView({ forceView }: { forceView?: TraceabilityViewState }) {
  const view: TraceabilityViewState = forceView ?? "small";

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
