import { Link } from "react-router-dom";
import { useState } from "react";

import { useAuth } from "../../auth/AuthContext";
import { Assess, Badge, Banner, Button, Card, CardBody, EmptyState, Panel, Spinner, Table, Tabs, Textarea, WriteError } from "../../components/ui";
import { driftKindLabel } from "../../labels";
import type { DriftRecord } from "../../types";
import { roleLabel } from "../identity/roles";
import { artifactStatusBadge } from "./artifactStatus";
import { useApiContracts, useDecideDrift, useDrift } from "./hooks";

// S-27 view states: healthy · drift-pending (cross-repo impact) · wrong-role
// (read-only) · decided.
export type ContractsDriftView = "healthy" | "drift-pending" | "wrong-role" | "decided";

function driftSummary(detail: Record<string, unknown>) {
  const oldV = detail.old_version as string | undefined;
  const newV = detail.new_version as string | undefined;
  const breaking = detail.breaking as string[] | undefined;
  if (oldV && newV) {
    return `${oldV} → ${newV}${breaking?.length ? ` — breaks ${breaking.join(", ")}` : ""}`;
  }
  if (breaking?.length) return `Breaking changes: ${breaking.join(", ")}`;
  // Humanize the remaining scalar fields instead of dumping raw JSON at the user (S.No 120, Part C-2).
  const parts = Object.entries(detail)
    .filter(([, v]) => v != null && typeof v !== "object")
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`);
  return parts.length ? parts.join(" · ") : "Contract changed — open the contract for details";
}

export function ContractsDrift({ forceView }: { forceView?: ContractsDriftView }) {
  if (forceView) return <ContractsDriftGallery view={forceView} />;
  return <ContractsDriftLive />;
}

// ── Live: the real contract registry + drift queue for the selected project ─
function ContractsDriftLive() {
  const { selectedProject, hasRole } = useAuth();
  const projectId = selectedProject?.project_id;
  const contracts = useApiContracts(projectId);
  const drift = useDrift(projectId);
  const decideDrift = useDecideDrift();
  const [tab, setTab] = useState<"contracts" | "drift">("contracts");
  const [comment, setComment] = useState("");
  const [decidedId, setDecidedId] = useState<string | null>(null);

  const driftList = drift.data ?? [];
  const selected: DriftRecord | undefined = driftList.find((d) => d.id !== decidedId) ?? driftList[0];
  // Same fix as the Gates screen, and the same reason — this had an identical copy of the
  // one-role comparison, so a person holding two roles was locked out here too.
  const canDecide = (d: DriftRecord) => hasRole(d.required_role);

  const handleDecide = (decision: "accept" | "reject") => {
    if (!selected) return;
    decideDrift.mutate(
      { id: selected.id, decision, comment: comment || undefined },
      { onSuccess: () => setDecidedId(selected.id) },
    );
  };

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">API Contracts &amp; Drift</h1>
          <p className="page-head__sub">
            Versioned API contracts across repos. A breaking change opens a drift gate the{" "}
            <strong>architect</strong> decides — with cross-repo impact spelled out.
          </p>
        </div>
      </div>

      <Tabs
        tabs={[
          { id: "contracts", label: "Contracts" },
          { id: "drift", label: `Drift queue (${driftList.length})` },
        ]}
        active={tab}
        onSelect={(id) => setTab(id as "contracts" | "drift")}
      />

      <div style={{ marginTop: "var(--space-5)" }}>
        {tab === "contracts" ? (
          contracts.isLoading ? (
            <Panel>
              <Spinner /> Loading contracts…
            </Panel>
          ) : (contracts.data ?? []).length === 0 ? (
            <Panel>
              <EmptyState title="No API contracts registered yet" text="Export one from a repo's onboarding step." />
            </Panel>
          ) : (
            <Panel flush>
              <Table
                headers={["Contract", "Version", "Provider repo", "Status", ""]}
                rows={contracts.data!.map((c) => [
                  <span className="table__primary" key="c">
                    {c.name}
                  </span>,
                  <span className="table__id" key="v">
                    {c.semver ?? `v${c.version}`}
                  </span>,
                  <span className="table__id" key="r">
                    {c.provider_repo ?? "—"}
                  </span>,
                  // Screen Words group 4: a contract IS a registered document, so it uses the
                  // same badge as the Artifacts list rather than printing the stored word in
                  // green whatever it says.
                  artifactStatusBadge(c.status),
                  <Link to={`/artifacts/${c.artifact_id}`} key="a">
                    View ↗
                  </Link>,
                ])}
              />
            </Panel>
          )
        ) : drift.isLoading ? (
          <Panel>
            <Spinner /> Loading drift queue…
          </Panel>
        ) : driftList.length === 0 ? (
          decidedId ? (
            <Card>
              <CardBody>
                <Banner variant="success" title="Decision recorded">
                  The drift record was decided. Cross-repo impact has been reconciled or flagged.
                </Banner>
              </CardBody>
            </Card>
          ) : (
            <Panel>
              <EmptyState title="No drift" text="Contracts and their consumers are in sync." />
            </Panel>
          )
        ) : (
          <div className="grid grid--detail">
            <Panel flush title="Drift queue">
              <Table
                headers={["What changed", "Decided by", "Impact", ""]}
                rows={driftList.map((d) => ({
                  cells: [
                    // Screen Words groups 3 and 4: the drift kind and the role were both stored
                    // keys. "pointer_hash" is not a sentence anyone can act on.
                    <Badge variant="failed" key="k">
                      {driftKindLabel(d.kind)}
                    </Badge>,
                    roleLabel(d.required_role),
                    `${d.impacted.length} consumer${d.impacted.length === 1 ? "" : "s"}`,
                    "",
                  ],
                  style: d.id === selected?.id ? { background: "var(--danger-bg)" } : undefined,
                }))}
              />
            </Panel>

            {selected &&
              (canDecide(selected) ? (
                <Card attention>
                  <CardBody>
                    {/* Screen Words group 3 — same wording as the gate panels elsewhere. */}
                    <span className="gate-panel__role">▲ Drift gate · decided by a {roleLabel(selected.required_role)}</span>
                    <h3 className="t-h3">{driftKindLabel(selected.kind)}</h3>
                    <Banner variant="danger" title={`Impacts ${selected.impacted.length} consumer(s)`}>
                      {driftSummary(selected.detail)}
                    </Banner>
                    {selected.impacted.length > 0 && (
                      <ul className="u-stack" style={{ ["--space-4" as string]: "6px" }}>
                        {selected.impacted.map((imp, i) => (
                          <li className="u-row-tight" key={i}>
                            <Assess state="missing">✗</Assess>
                            <span className="t-sm">
                              {imp.node_title || `Artifact ${imp.node.slice(0, 8)}`} · {imp.repo_name || `repo ${imp.repo_id.slice(0, 8)}`}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                    <label className="field" style={{ marginBottom: 0 }}>
                      <span className="field__label">Decision comment</span>
                      <Textarea
                        value={comment}
                        onChange={(e) => setComment(e.target.value)}
                        placeholder="Why accept or reject this breaking change…"
                      />
                    </label>
                    <div className="gate-panel__actions">
                      <Button variant="primary" disabled={decideDrift.isPending} onClick={() => handleDecide("accept")}>
                        Accept
                      </Button>
                      <Button variant="danger" disabled={decideDrift.isPending} onClick={() => handleDecide("reject")}>
                        Reject
                      </Button>
                    </div>
                    {decideDrift.isError && (
                      <WriteError title="Couldn't record the decision" detail={decideDrift.error} />
                    )}
                  </CardBody>
                </Card>
              ) : (
                <Card>
                  <CardBody>
                    <span className="gate-panel__role" style={{ color: "var(--text-muted)" }}>
                      Drift gate · {driftKindLabel(selected.kind)}
                    </span>
                    {/* Screen Words group 3: the role's own name instead of the key. NOTE: no
                        "or an admin" here, unlike the Gates banner. `decide_drift` checks the
                        exact required role and has no admin fallback, so offering one would be
                        a promise the server does not keep. */}
                    <Banner variant="info" title={`Waiting for a ${roleLabel(selected.required_role)}`}>
                      Only a <strong>{roleLabel(selected.required_role)}</strong> on this project
                      can decide this drift. You can read it.
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
              ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
function ContractsDriftGallery({ view }: { view: ContractsDriftView }) {
  const tab: "contracts" | "drift" = view === "healthy" ? "contracts" : "drift";
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
                  <Link to="/artifacts" key="a">
                    View ↗
                  </Link>,
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
                  <Link to="/artifacts" key="a">
                    View ↗
                  </Link>,
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
                    <Button variant="primary">Accept</Button>
                    <Button variant="danger">Reject</Button>
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
