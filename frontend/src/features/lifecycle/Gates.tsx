import { useState } from "react";

import { Badge, Banner, Button, Card, CardBody, EmptyState, Panel, Table, Tabs, Textarea } from "../../components/ui";
import { useDecideApproval } from "./hooks";

// S-21 view states: can-decide (your role) · cannot-decide (permission) ·
// decided-history · empty.
export type GatesView = "can-decide" | "cannot-decide" | "history" | "empty";

export function Gates({ forceView }: { forceView?: GatesView }) {
  const decideApproval = useDecideApproval();
  const [tab, setTab] = useState<"pending" | "history">("pending");
  const view: GatesView = forceView ?? (tab === "history" ? "history" : "can-decide");

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">
            Gates{" "}
            {view !== "empty" && (
              <Badge variant="gate" dot={false}>
                3 pending
              </Badge>
            )}
          </h1>
          <p className="page-head__sub">
            Approvals awaiting a decision. Only the required role can decide each gate — nothing
            reaches a system-of-record without one.
          </p>
        </div>
      </div>

      {view !== "empty" && (
        <Tabs
          tabs={[
            { id: "pending", label: "Pending (3)" },
            { id: "history", label: "Decided history" },
          ]}
          active={tab}
          onSelect={(id) => setTab(id as "pending" | "history")}
        />
      )}

      {view === "empty" ? (
        <Panel>
          <EmptyState
            title="No gates need you"
            text="Approvals you can act on will appear here and in the notifications bell."
          />
        </Panel>
      ) : view === "history" ? (
        <div style={{ marginTop: "var(--space-4)" }}>
          <Panel flush>
            <Table
              headers={["Gate", "Work item", "Decision", "By", "When"]}
              rows={[
                [
                  "PRD",
                  <span className="table__id" key="w">
                    WI-492
                  </span>,
                  <Badge variant="done" key="d">
                    Approved
                  </Badge>,
                  "Sarah Chen",
                  "1h ago",
                ],
                [
                  "Requirements",
                  <span className="table__id" key="w">
                    WI-499
                  </span>,
                  <Badge variant="done" key="d">
                    Approved
                  </Badge>,
                  "Sarah Chen",
                  "2d ago",
                ],
                [
                  "Architecture",
                  <span className="table__id" key="w">
                    WI-470
                  </span>,
                  <Badge variant="failed" key="d">
                    Rejected
                  </Badge>,
                  "Marcus Lee",
                  "3d ago",
                ],
              ]}
            />
          </Panel>
        </div>
      ) : (
        <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
          <Panel title="Pending approvals" flush>
            <Table
              headers={["Gate", "Required role", "Work item", "Artifact"]}
              rows={[
                {
                  cells: [
                    "Architecture",
                    <span className="chip badge--navy" key="r">
                      architect
                    </span>,
                    <span className="table__id" key="w">
                      WI-492
                    </span>,
                    <a href="/artifacts" key="a">
                      Preview ↗
                    </a>,
                  ],
                  style: { background: "var(--brand-orange-50)" },
                },
                [
                  "PM Approval",
                  <span className="chip badge--navy" key="r">
                    product_owner
                  </span>,
                  <span className="table__id" key="w">
                    WI-511
                  </span>,
                  <a href="/artifacts" key="a">
                    Preview ↗
                  </a>,
                ],
                [
                  "UX Design",
                  <span className="chip badge--navy" key="r">
                    designer
                  </span>,
                  <span className="table__id" key="w">
                    WI-487
                  </span>,
                  <a href="/work-items/WI-487" key="a">
                    Preview ↗
                  </a>,
                ],
              ]}
            />
          </Panel>

          {view === "can-decide" ? (
            <Card attention>
              <CardBody>
                <span className="gate-panel__role">▲ Architecture gate · required role: architect</span>
                <h3 className="t-h3">WI-492 · Stripe Webhook Integration</h3>
                <p className="t-sm u-body">
                  Reviewing: <strong>System Sequence Diagram v0.9</strong>. Approve to publish to Figma
                  and advance to UX Design.
                </p>
                <a href="/artifacts" className="t-sm">
                  Preview artifact under review ↗
                </a>
                <label className="field" style={{ margin: "var(--space-2) 0 0" }}>
                  <span className="field__label">Comment (optional)</span>
                  <Textarea placeholder="Add context for your decision…" />
                </label>
                <div className="gate-panel__actions">
                  <Button
                    variant="primary"
                    onClick={() => decideApproval.mutate({ id: "approval-1", decision: "approved" })}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="danger"
                    onClick={() => decideApproval.mutate({ id: "approval-1", decision: "rejected" })}
                  >
                    Reject
                  </Button>
                </div>
                <span className="gate-reassure">Decision logged with your role &amp; comment.</span>
              </CardBody>
            </Card>
          ) : (
            <Card>
              <CardBody>
                <span className="gate-panel__role" style={{ color: "var(--text-muted)" }}>
                  PM Approval gate · WI-511 Fix Session Timeout Logic
                </span>
                <Banner variant="info" title="Awaiting product_owner">
                  You don't hold the <strong>product_owner</strong> role on this project, so this is
                  read-only. <strong>Sarah Chen</strong> can decide.
                </Banner>
                <a href="/artifacts" className="t-sm">
                  Preview artifact under review ↗
                </a>
                <div className="gate-panel__actions">
                  <Button variant="primary" disabled aria-disabled="true">
                    Approve
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
  );
}
