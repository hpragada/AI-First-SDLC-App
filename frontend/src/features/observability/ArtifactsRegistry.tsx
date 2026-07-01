import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, EmptyState, Panel, Table } from "../../components/ui";
import { useArtifacts } from "./hooks";

// S-28 view states: populated · internal-only (no external link) · empty.
export type ArtifactsView = "populated" | "internal-only" | "empty";

function statusBadge(status: string) {
  if (status === "published" || status === "done") return <Badge variant="done">Published</Badge>;
  if (status === "pending_gate" || status === "gate") return <Badge variant="gate">Pending gate</Badge>;
  return <Badge variant="info-hue">Draft</Badge>;
}

export function ArtifactsRegistry({ forceView }: { forceView?: ArtifactsView }) {
  const { selectedProject } = useAuth();
  const artifacts = useArtifacts({ project: selectedProject?.project });
  const list = artifacts.data ?? [];
  const view: ArtifactsView =
    forceView ?? (list.length === 0 && artifacts.isSuccess ? "empty" : "populated");

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Artifacts</h1>
          <p className="page-head__sub">
            The registry: pointers, versions, and system-of-record links — never artifact bodies.
            Preview opens read-only.
          </p>
        </div>
        <Link to="/traceability" className="btn btn--secondary">
          View traceability
        </Link>
      </div>

      {view === "empty" ? (
        <Panel>
          <EmptyState
            title="No artifacts yet"
            text="Run a phase to produce the first artifact. It registers here as a draft pointer until its gate is approved."
          />
        </Panel>
      ) : (
        <>
          <div className="u-row u-wrap" style={{ marginBottom: "var(--space-4)" }}>
            <input
              className="input"
              type="search"
              placeholder="Search artifacts…"
              style={{ maxWidth: "240px" }}
              aria-label="Search artifacts"
            />
            <select className="select" style={{ maxWidth: "150px" }} aria-label="Filter by phase">
              <option>Phase: All</option>
            </select>
            <select className="select" style={{ maxWidth: "140px" }} aria-label="Filter by type">
              <option>Type: All</option>
            </select>
            <select className="select" style={{ maxWidth: "150px" }} aria-label="Filter by status">
              <option>Status: All</option>
            </select>
          </div>
          <Panel flush>
            <Table
              headers={["Artifact", "Phase", "Version", "Status", "System of record", ""]}
              rows={
                view === "internal-only"
                  ? [
                      [
                        <span className="table__primary" key="t">
                          Ideation Brief — Loyalty Program
                        </span>,
                        "Ideation",
                        <span className="table__id" key="v">
                          v0.3
                        </span>,
                        <Badge variant="info-hue" key="s">
                          Draft
                        </Badge>,
                        <span className="t-xs u-muted" key="sor">
                          Platform only — not published
                        </span>,
                        <Link to="/artifacts/internal-1" className="btn btn--ghost btn--sm" key="a">
                          Preview
                        </Link>,
                      ],
                    ]
                  : list.map((artifact) => [
                      <span className="table__primary" key="t">
                        {artifact.type}
                      </span>,
                      artifact.phase,
                      <span className="table__id" key="v">
                        v{artifact.version}
                      </span>,
                      statusBadge(artifact.status),
                      artifact.sor ? (
                        <span className="sor-chip sor-chip--confluence" key="sor">
                          <span className="sor-chip__glyph">C</span>
                          {artifact.sor}
                        </span>
                      ) : (
                        <span className="t-xs u-muted" key="sor">
                          Platform only
                        </span>
                      ),
                      <Link to={`/artifacts/${artifact.id}`} className="btn btn--ghost btn--sm" key="a">
                        Preview
                      </Link>,
                    ])
              }
            />
          </Panel>
        </>
      )}
    </div>
  );
}
