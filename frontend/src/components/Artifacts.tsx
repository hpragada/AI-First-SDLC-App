// Artifact view — registry entries (pointers + provenance, never the body: #1/#3).
// Shows phase/type/status/sor plus the S3 key and content hash that locate the draft.
import { useEffect, useState } from "react";

import { api, ApiError } from "../api";
import { useApp } from "../state";
import type { Artifact } from "../types";

export function Artifacts() {
  const { tenantId, project } = useApp();
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!tenantId || !project) return;
    void (async () => {
      try {
        // One row per artifact, newest version (Part B fix 5) — prior versions stay readable as
        // version history on the artifact's own screen.
        setArtifacts(await api.listArtifacts(tenantId, { project: project.id, latest: true }));
        setErr(null);
      } catch (e) {
        setErr(e instanceof ApiError ? e.message : String(e));
      }
    })();
  }, [tenantId, project]);

  return (
    <div className="panel">
      <h2>Artifacts</h2>
      {err && <div className="err">{err}</div>}
      {artifacts.length === 0 ? (
        <div className="empty">No artifacts registered yet. Run a phase to produce one.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Phase</th>
              <th>Type</th>
              <th>Status</th>
              <th>SoR</th>
              <th>Ver</th>
              <th>S3 key</th>
              <th>Hash</th>
            </tr>
          </thead>
          <tbody>
            {artifacts.map((a) => (
              <tr key={a.id}>
                <td>{a.phase}</td>
                <td>{a.type}</td>
                <td>
                  <span className={`badge ${a.status}`}>{a.status}</span>
                </td>
                <td className="muted">{a.sor}</td>
                <td className="mono">{a.version}</td>
                <td className="mono">{a.s3_key || "—"}</td>
                <td className="mono">{a.content_hash ? a.content_hash.slice(0, 12) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
