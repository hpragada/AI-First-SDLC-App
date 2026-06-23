import { useState } from "react";

import { TenantProjectBar } from "./components/TenantProjectBar";
import { ProfileEditor } from "./components/ProfileEditor";
import { PhaseConsole } from "./components/PhaseConsole";
import { Gates } from "./components/Gates";
import { Artifacts } from "./components/Artifacts";
import { Traceability } from "./components/Traceability";
import { useApp } from "./state";

type Tab = "profile" | "console" | "gates" | "artifacts" | "trace";

const TABS: { id: Tab; label: string }[] = [
  { id: "profile", label: "Project Profile" },
  { id: "console", label: "Phase Console" },
  { id: "gates", label: "Gate Approvals" },
  { id: "artifacts", label: "Artifacts" },
  { id: "trace", label: "Traceability" },
];

export function App() {
  const { tenantId, project } = useApp();
  const [tab, setTab] = useState<Tab>("profile");

  const ready = Boolean(tenantId && project);

  return (
    <div className="app">
      <TenantProjectBar />

      {!ready ? (
        <div className="panel empty">
          Create or select a tenant and project above to begin. The acceptance slice:
          create a project, fill its profile, then trigger ideation → requirements → PRD →
          architecture in the Phase Console.
        </div>
      ) : (
        <>
          <nav className="tabs">
            {TABS.map((t) => (
              <button
                key={t.id}
                className={tab === t.id ? "active" : ""}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </nav>

          {tab === "profile" && <ProfileEditor />}
          {tab === "console" && <PhaseConsole />}
          {tab === "gates" && <Gates />}
          {tab === "artifacts" && <Artifacts />}
          {tab === "trace" && <Traceability />}
        </>
      )}
    </div>
  );
}
