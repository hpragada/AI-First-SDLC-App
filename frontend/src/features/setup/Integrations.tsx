import { Link } from "react-router-dom";

import { Badge, Banner, CapCard } from "../../components/ui";
import { SetupReturnLink } from "../identity/SetupReturnLink";
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
};

// The capabilities a person connects, in the order the grid shows them.
//
// N1: Code intelligence is gone from this grid. It was not a control — there is nothing to
// connect; the analyser runs on the developer's own machine with no credentials — and its card
// was hard-wired to read "Connected · Built-in" whatever the platform knew. Real workspaces were
// only ever given the accessibility capability automatically, so a real customer's workspace
// could have no code-intelligence record at all while its card said "Connected". It is now
// provisioned automatically the same way (`AUTO_PROVISIONED`), and — like accessibility — does
// not appear here. The team's option A: the other five cards stay exactly as they were.
export const ALL_CAPS: Capability[] = [
  "docstore",
  "tasktracker",
  "designsource",
  "codehost",
  "testmgmt",
];

export function isCapability(value: string | undefined): value is Capability {
  return ALL_CAPS.includes(value as Capability);
}

function statusBadge(connected: boolean, failed: boolean) {
  if (failed) return <Badge variant="failed">Failed</Badge>;
  if (connected) return <Badge variant="done">Connected</Badge>;
  return <Badge variant="queued">Not connected</Badge>;
}

export function Integrations({ forceView }: { forceView?: IntegrationsView }) {
  const integrations = useIntegrations();
  const byCap = new Map((integrations.data ?? []).map((i) => [i.capability, i]));
  // Only a capability this grid shows. The list also carries the automatically provisioned ones,
  // and a failure on one of those must not collapse the grid to a card that is not here.
  const failedOne = (integrations.data ?? []).find(
    (i) => i.status === "failed" && isCapability(i.capability),
  );

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
        <SetupReturnLink />
      </div>

      <div className="grid grid--auto">
        {caps.map((cap) => {
          const integration = view === "empty" ? undefined : byCap.get(cap);
          const failed = integration?.status === "failed";
          const connected = integration?.status === "connected";
          const linkLabel = failed ? "Fix connection" : connected ? "Manage" : "Connect";
          const linkVariant = failed ? "btn--secondary" : connected ? "btn--ghost" : "btn--primary";
          return (
            <CapCard
              key={cap}
              vendor={integration?.vendor || "Not connected"}
              capability={CAP_LABEL[cap]}
              capabilityKey={cap}
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
