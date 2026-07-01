import { useState } from "react";

import { Assess, Badge, Banner, Button, Card, CardBody, Panel, Table, Tabs, Textarea } from "../../components/ui";
import { useDecideDrift } from "./hooks";

// S-27 view states: healthy · drift-pending (cross-repo impact) · wrong-role
// (read-only) · decided.
export type ContractsDriftView = "healthy" | "drift-pending" | "wrong-role" | "decided";

export function ContractsDrift({ forceView }: { forceView?: ContractsDriftView }) {
  const decideDrift = useDecideDrift();
  const [tab, setTab] = useState<"contracts" | "drift">("contracts");
  const view: ContractsDriftView = forceView ?? (tab === "drift" ? "drift-pending" : "healthy");

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">API Contracts & Drift</h1>
          <p className="page-head__sub">
            Versioned API contracts across repos. A breaking change opens a drift gate the{" "}
            <strong>architect</strong> decides — with cross-repo impact spelled out.
          </p>
        </div>
      </div>

      <Tabs
        tabs={[
          { id: "contracts", label: "Contracts" },
          { id: "drift", label: "Drift queue (1)" },
        ]}
        active={tab}
        onSelect={(id) => setTab(id as "contracts" | "drift")}
      />

      <div style={{ marginTop: "var(--space-5)" }}>
        {view === "healthy" && (
          <Panel flush>
            <Table
              headers={["Contract", "Version", "Provider repo", "Status", ""]}
              rows={[
                [
                  <span className="table__primary" key="c">
                    Payments API
                  </span>,
                  <span className="table__id" key="v">
                    v1.4.0
                  </span>,
                  <span className="table__id" key="r">
                    acme/payments-api
                  </span>,
                  <Badge variant="done" key="s">
                    Stable
                  </Badge>,
                  <a href="/artifacts" key="a">
                    View ↗
                  </a>,
                ],
                [
                  <span className="table__primary" key="c">
                    Ledger API
                  </span>,
                  <span className="table__id" key="v">
                    v2.1.0
                  </span>,
                  <span className="table__id" key="r">
                    acme/payments-api
                  </span>,
                  <Badge variant="done" key="s">
                    Stable
                  </Badge>,
                  <a href="/artifacts" key="a">
                    View ↗
                  </a>,
                ],
              ]}
            />
          </Panel>
        )}

        {view === "decided" && (
          <Card>
            <CardBody>
              <Banner variant="success" title="Accepted by Marcus Lee">
                Payments API v2.0.0 accepted · remediation work items opened for the 3 impacted
                consumers in acme/payments-web.
              </Banner>
            </CardBody>
          </Card>
        )}

        {(view === "drift-pending" || view === "wrong-role") && (
          <div className="grid grid--detail">
            <Panel flush title="Drift queue">
              <Table
                headers={["Contract", "Change", "Impact", "Decider"]}
                rows={[
                  {
                    cells: [
                      "Payments API v2.0.0",
                      <Badge variant="failed" key="c">
                        Breaking
                      </Badge>,
                      "3 consumers",
                      "Marcus Lee",
                    ],
                    style: { background: "var(--danger-bg)" },
                  },
                ]}
              />
            </Panel>

            {view === "drift-pending" ? (
              <Card attention>
                <CardBody>
                  <span className="gate-panel__role">▲ Drift gate · required role: architect</span>
                  <h3 className="t-h3">Payments API v2.0.0 — breaking change</h3>
                  <Banner variant="danger" title="Impacts acme/payments-web">
                    Removes <code>POST /charges</code> body field <code>legacy_token</code> —{" "}
                    <strong>3 consumers</strong> affected.
                  </Banner>
                  <ul className="u-stack" style={{ ["--space-4" as string]: "6px" }}>
                    <li className="u-row-tight">
                      <Assess state="missing">✗</Assess>
                      <span className="t-sm">CheckoutForm.tsx · acme/payments-web</span>
                    </li>
                    <li className="u-row-tight">
                      <Assess state="missing">✗</Assess>
                      <span className="t-sm">PaymentService.ts · acme/payments-web</span>
                    </li>
                    <li className="u-row-tight">
                      <Assess state="missing">✗</Assess>
                      <span className="t-sm">RetryWorker.ts · acme/payments-web</span>
                    </li>
                  </ul>
                  <label className="field" style={{ marginBottom: 0 }}>
                    <span className="field__label">Decision comment</span>
                    <Textarea placeholder="Why accept or reject this breaking change…" />
                  </label>
                  <div className="gate-panel__actions">
                    <Button
                      variant="primary"
                      onClick={() => decideDrift.mutate({ id: "drift-1", decision: "accept" })}
                    >
                      Accept
                    </Button>
                    <Button
                      variant="danger"
                      onClick={() => decideDrift.mutate({ id: "drift-1", decision: "reject" })}
                    >
                      Reject
                    </Button>
                  </div>
                </CardBody>
              </Card>
            ) : (
              <Card>
                <CardBody>
                  <span className="gate-panel__role" style={{ color: "var(--text-muted)" }}>
                    Drift gate · Payments API v2.0.0
                  </span>
                  <Banner variant="info" title="Awaiting architect">
                    Only the <strong>architect</strong> can decide drift. <strong>Marcus Lee</strong>{" "}
                    can act.
                  </Banner>
                  <div className="gate-panel__actions">
                    <Button variant="primary" disabled aria-disabled="true">
                      Accept
                    </Button>
                    <Button variant="secondary" disabled aria-disabled="true">
                      Reject
                    </Button>
                  </div>
                </CardBody>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
