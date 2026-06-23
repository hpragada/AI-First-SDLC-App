// Top bar: bootstrap a tenant, then create/select a project within it. This is the
// "project create" screen plus the tenant entry the rest of the UI scopes to.
import { useEffect, useState } from "react";

import { api, ApiError } from "../api";
import { useApp } from "../state";
import type { Project } from "../types";

export function TenantProjectBar() {
  const { tenantId, setTenantId, project, setProject } = useApp();
  const [tenantName, setTenantName] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [newProject, setNewProject] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function refreshProjects(tid: string) {
    try {
      setProjects(await api.listProjects(tid));
      setErr(null);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  useEffect(() => {
    if (tenantId) void refreshProjects(tenantId);
    else setProjects([]);
  }, [tenantId]);

  async function createTenant() {
    if (!tenantName.trim()) return;
    try {
      const t = await api.createTenant(tenantName.trim());
      setTenantId(t.id);
      setTenantName("");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function createProject() {
    if (!tenantId || !newProject.trim()) return;
    try {
      const p = await api.createProject(tenantId, newProject.trim());
      setNewProject("");
      await refreshProjects(tenantId);
      setProject(p);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <header className="topbar">
      <h1>AI-First SDLC</h1>

      {!tenantId ? (
        <div className="flex grow">
          <input
            placeholder="New tenant name"
            value={tenantName}
            onChange={(e) => setTenantName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void createTenant()}
          />
          <button className="primary" onClick={() => void createTenant()}>
            Create tenant
          </button>
        </div>
      ) : (
        <div className="flex grow">
          <span className="badge">tenant</span>
          <span className="mono">{tenantId.slice(0, 8)}…</span>

          <select
            value={project?.id ?? ""}
            onChange={(e) =>
              setProject(projects.find((p) => p.id === e.target.value) ?? null)
            }
          >
            <option value="">— select project —</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.track})
              </option>
            ))}
          </select>

          <input
            placeholder="New project name"
            value={newProject}
            onChange={(e) => setNewProject(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void createProject()}
          />
          <button className="primary" onClick={() => void createProject()}>
            Create project
          </button>

          <div className="spacer" />
          <button className="ghost" onClick={() => setTenantId(null)}>
            Switch tenant
          </button>
        </div>
      )}

      {err && <div className="err">{err}</div>}
    </header>
  );
}
