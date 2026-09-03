// Project Profile editor — the migrated CLAUDE.md structure that becomes the composed
// manifest. `important_context` is rendered verbatim into the agent manifest, so it's
// the high-leverage field here. Saving bumps the profile version server-side.
import { useEffect, useState } from "react";

import { api, ApiError } from "../api";
import { useApp } from "../state";

export function ProfileEditor() {
  const { tenantId, project } = useApp();
  const [description, setDescription] = useState("");
  const [domain, setDomain] = useState("");
  const [importantContext, setImportantContext] = useState("");
  const [version, setVersion] = useState<number | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!tenantId || !project) return;
    void (async () => {
      try {
        const p = await api.getProfile(tenantId, project.id);
        setDescription(p?.description ?? "");
        setDomain(p?.domain ?? "");
        setImportantContext(p?.important_context ?? "");
        setVersion(p?.version ?? null);
        setErr(null);
      } catch (e) {
        setErr(e instanceof ApiError ? e.message : String(e));
      }
    })();
  }, [tenantId, project]);

  async function save() {
    if (!tenantId || !project) return;
    try {
      const saved = await api.putProfile(tenantId, project.id, {
        description,
        domain,
        important_context: importantContext,
      });
      setVersion(saved.version);
      setStatus(`Saved — version ${saved.version}`);
      setErr(null);
    } catch (e) {
      setStatus(null);
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <div className="panel">
      <h2>
        Project Profile{" "}
        {version !== null && <span className="badge">v{version}</span>}
      </h2>

      <label>Description</label>
      <textarea value={description} onChange={(e) => setDescription(e.target.value)} />

      <label>Domain</label>
      <input value={domain} onChange={(e) => setDomain(e.target.value)} />

      <label>
        Important context{" "}
        <small className="hint">(rendered verbatim into the agent manifest)</small>
      </label>
      <textarea
        value={importantContext}
        onChange={(e) => setImportantContext(e.target.value)}
      />

      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" onClick={() => void save()}>
          Save profile
        </button>
      </div>

      {status && <div className="ok">{status}</div>}
      {err && <div className="err">{err}</div>}
    </div>
  );
}
