import { Link } from "react-router-dom";

import { Badge, Banner, CapCard } from "../../components/ui";
import type { Capability } from "../../types";
import { useIntegrations } from "./hooks";

// S-11 view states: mixed (some connected) · connection-failed · all-empty.
export type IntegrationsView = "mixed" | "failed" | "empty";

export const CAP_LABEL: Record<Capability, string> = {
  docstore: "Documentation store",
  tasktracker: "Task tracker",
  designsource: "Design source",
  codehost: "Code host",
  testmgmt: "Test management",
  codeintel: "Code intelligence",
};

const ALL_CAPS: Capability[] = [
  "docstore",
  "tasktracker",
  "designsource",
  "codehost",
  "testmgmt",
  "codeintel",
];

function statusBadge(connected: boolean, failed: boolean) {
  if (failed) return <Badge variant="failed">Failed</Badge>;
  if (connected) return <Badge variant="done">Connected</Badge>;
  return <Badge variant="queued">Not connected</Badge>;
}

export function Integrations({ forceView }: { forceView?: IntegrationsView }) {
  const integrations = useIntegrations();
  const byCap = new Map((integrations.data ?? []).map((i) => [i.capability, i]));
  const failedOne = (integrations.data ?? []).find((i) => i.status === "failed");

  const view: IntegrationsView =
    forceView ??
    (failedOne ? "failed" : (integrations.data?.length ?? 0) > 0 ? "mixed" : "empty");

  const caps = view === "failed" && failedOne ? [failedOne.capability] : ALL_CAPS;

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Integrations</h1>
          <p className="page-head__sub">
            Capabilities, not vendors — connect a vendor as the current binding for each capability.
            Phases use whatever is connected.
          </p>
        </div>
      </div>

      <div className="grid grid--3">
        {caps.map((cap) => {
          const integration = view === "empty" ? undefined : byCap.get(cap);
          const builtIn = cap === "codeintel";
          const failed = integration?.status === "failed";
          const connected = integration?.status === "connected" || builtIn;
          const linkLabel = failed ? "Fix connection" : connected ? "Manage" : "Connect";
          const linkVariant = failed ? "btn--secondary" : connected ? "btn--ghost" : "btn--primary";
          return (
            <CapCard
              key={cap}
              vendor={integration?.vendor || (builtIn ? "Built-in" : "Not connected")}
              capability={CAP_LABEL[cap]}
              failed={failed}
              status={
                <>
                  {statusBadge(connected, failed)}
                  <span className="u-spacer" />
                  <Link to={`/integrations/${cap}`} className={`btn ${linkVariant} btn--sm`}>
                    {linkLabel}
                  </Link>
                </>
              }
            >
              {failed && integration && (
                <Banner variant="danger">
                  {integration.fail_reason ?? "Token rejected (401). The app credential may have expired."}
                </Banner>
              )}
            </CapCard>
          );
        })}
      </div>
    </div>
  );
}
