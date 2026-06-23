// Traceability view — the provenance DAG. Renders each TraceEdge as
// `<source artifact> --rel--> <target artifact>`, resolving artifact ids to their
// phase/type so the requirement → PRD → architecture chain reads at a glance.
import { useEffect, useState } from "react";

import { api, ApiError } from "../api";
import { useApp } from "../state";
import type { Artifact, TraceEdge } from "../types";

export function Traceability() {
  const { tenantId, project } = useApp();
  const [edges, setEdges] = useState<TraceEdge[]>([]);
  const [artifacts, setArtifacts] = useState<Record<string, Artifact>>({});
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!tenantId || !project) return;
    void (async () => {
      try {
        const [es, as] = await Promise.all([
          api.listTraceEdges(tenantId, project.id),
          api.listArtifacts(tenantId, { project: project.id }),
        ]);
        setEdges(es);
        setArtifacts(Object.fromEntries(as.map((a) => [a.id, a])));
        setErr(null);
      } catch (e) {
        setErr(e instanceof ApiError ? e.message : String(e));
      }
    })();
  }, [tenantId, project]);

  const label = (id: string) => {
    const a = artifacts[id];
    return a ? `${a.phase}:${a.type}` : id.slice(0, 8);
  };

  return (
    <div className="panel">
      <h2>Traceability</h2>
      {err && <div className="err">{err}</div>}
      {edges.length === 0 ? (
        <div className="empty">
          No trace edges yet. Edges are written when a phase derives from a prior artifact.
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>From</th>
              <th>Relation</th>
              <th>To</th>
            </tr>
          </thead>
          <tbody>
            {edges.map((e) => (
              <tr key={e.id}>
                <td className="mono">{label(e.from_artifact)}</td>
                <td>
                  <span className="badge">{e.rel}</span>
                </td>
                <td className="mono">{label(e.to_artifact)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
