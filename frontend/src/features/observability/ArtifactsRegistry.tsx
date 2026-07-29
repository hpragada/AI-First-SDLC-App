import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, EmptyState, Panel, Table } from "../../components/ui";
import { phaseLabel, artifactLabel } from "../lifecycle/phases";
import { useArtifacts } from "./hooks";

// Humanize a status token (draft / pending_gate / published) for display + filter options.
function statusLabel(status: string) {
  return status
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

// S-28 view states: populated · internal-only (no external link) · empty.
export type ArtifactsView = "populated" | "internal-only" | "empty";

function statusBadge(status: string) {
  if (status === "published" || status === "done") return <Badge variant="done">Published</Badge>;
  if (status === "pending_gate" || status === "gate") return <Badge variant="gate">Pending gate</Badge>;
  return <Badge variant="info-hue">Draft</Badge>;
}

export function ArtifactsRegistry({ forceView }: { forceView?: ArtifactsView }) {
  const { selectedProject } = useAuth();
  // One row per artifact, newest version (Part B fix 5) — prior versions stay readable as version
  // history on the artifact's own screen, so a document that vision re-transcribed reads as one
  // entry rather than two.
  const artifacts = useArtifacts({ project: selectedProject?.project_id, latest: true });
  const list = artifacts.data ?? [];

  // Bugs.xlsx row 24: the search box and Phase/Type/Status filters were inert with no options.
  // Filter client-side over the registry in view; options are the distinct values actually present.
  const [search, setSearch] = useState("");
  const [phase, setPhase] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");

  const phaseOptions = useMemo(() => [...new Set(list.map((a) => a.phase))].filter(Boolean).sort(), [list]);
  const typeOptions = useMemo(() => [...new Set(list.map((a) => a.type))].filter(Boolean).sort(), [list]);
  const statusOptions = useMemo(() => [...new Set(list.map((a) => a.status))].filter(Boolean).sort(), [list]);

  const filtered = useMemo(
    () =>
      list.filter(
        (a) =>
          (!phase || a.phase === phase) &&
          (!type || a.type === type) &&
          (!status || a.status === status) &&
          (!search ||
            `${a.title} ${a.type} ${a.phase}`.toLowerCase().includes(search.toLowerCase())),
      ),
    [list, phase, type, status, search],
  );

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
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <select
              className="select"
              style={{ maxWidth: "170px" }}
              aria-label="Filter by phase"
              value={phase}
              onChange={(e) => setPhase(e.target.value)}
            >
              <option value="">Phase: All</option>
              {phaseOptions.map((p) => (
                <option key={p} value={p}>
                  {phaseLabel(p)}
                </option>
              ))}
            </select>
            <select
              className="select"
              style={{ maxWidth: "170px" }}
              aria-label="Filter by type"
              value={type}
              onChange={(e) => setType(e.target.value)}
            >
              <option value="">Type: All</option>
              {typeOptions.map((t) => (
                <option key={t} value={t}>
                  {phaseLabel(t)}
                </option>
              ))}
            </select>
            <select
              className="select"
              style={{ maxWidth: "160px" }}
              aria-label="Filter by status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">Status: All</option>
              {statusOptions.map((s) => (
                <option key={s} value={s}>
                  {statusLabel(s)}
                </option>
              ))}
            </select>
          </div>
          {view !== "internal-only" && filtered.length === 0 ? (
            <Panel>
              <EmptyState
                title="No artifacts match these filters"
                text="Clear the search or filters to see the full registry."
              />
            </Panel>
          ) : (
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
                  : filtered.map((artifact) => [
                      <span className="table__primary" key="t">
                        {artifactLabel(artifact.title, artifact.type)}
                      </span>,
                      phaseLabel(artifact.phase),
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
                      <span className="u-row-tight" key="a">
                        <Link to={`/artifacts/${artifact.id}`} className="btn btn--ghost btn--sm">
                          Preview
                        </Link>
                        {(artifact.status === "approved" || artifact.status === "published") && (
                          // Mirrors the backend export eligibility (gate passed) so the
                          // button never lands on a status 400.
                          <Link to={`/artifacts/${artifact.id}/publish`} className="btn btn--ghost btn--sm">
                            Export
                          </Link>
                        )}
                      </span>,
                    ])
              }
            />
          </Panel>
          )}
        </>
      )}
    </div>
  );
}
