// Minimal app-wide selection state: which tenant + project the screens operate on.
// Persisted to localStorage so a reload keeps you in context (pre-auth dev UX).
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import type { Project } from "./types";

interface AppState {
  tenantId: string | null;
  setTenantId: (id: string | null) => void;
  project: Project | null;
  setProject: (p: Project | null) => void;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [tenantId, setTenantIdRaw] = useState<string | null>(
    () => localStorage.getItem("tenantId"),
  );
  const [project, setProjectRaw] = useState<Project | null>(() => {
    const raw = localStorage.getItem("project");
    return raw ? (JSON.parse(raw) as Project) : null;
  });

  useEffect(() => {
    if (tenantId) localStorage.setItem("tenantId", tenantId);
    else localStorage.removeItem("tenantId");
  }, [tenantId]);

  useEffect(() => {
    if (project) localStorage.setItem("project", JSON.stringify(project));
    else localStorage.removeItem("project");
  }, [project]);

  const setTenantId = (id: string | null) => {
    setTenantIdRaw(id);
    setProjectRaw(null); // switching tenant clears the project selection
  };

  const value = useMemo<AppState>(
    () => ({ tenantId, setTenantId, project, setProject: setProjectRaw }),
    [tenantId, project],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp must be used within AppProvider");
  return v;
}
