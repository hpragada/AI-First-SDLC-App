import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import {
  Badge,
  Banner,
  Button,
  Card,
  CardBody,
  CriteriaItem,
  CriteriaList,
  EmptyState,
  Panel,
  Spinner,
  Table,
  Tabs,
  Textarea,
} from "../../components/ui";
import type { Approval } from "../../types";
import { roleLabel } from "../identity/roles";
import { useApprovals, useDecideApproval, useGateCriteria, useWorkItems } from "./hooks";
import { gateLabel } from "./phases";

// S-21 view states: can-decide (your role) · cannot-decide (permission) ·
// decided-history · empty.
export type GatesView = "can-decide" | "cannot-decide" | "history" | "empty";

export function Gates({ forceView }: { forceView?: GatesView }) {
  if (forceView) return <GatesGallery view={forceView} />;
  return <GatesLive />;
}

// ── Live: real pending/decided approvals for the selected project ──────────
function GatesLive() {
  const { selectedProject, currentUser } = useAuth();
  const projectId = selectedProject?.project_id;
  const workItems = useWorkItems(projectId);
  const workItemIds = new Set((workItems.data ?? []).map((w) => w.id));
  const approvals = useApprovals();
  const decideApproval = useDecideApproval();
  const [tab, setTab] = useState<"pending" | "history">("pending");
  const [comment, setComment] = useState("");
  const [selectedId, setSelectedId] = useState<string | undefined>();
  const [satisfied, setSatisfied] = useState<Record<string, boolean>>({});

  const loading = approvals.isLoading || workItems.isLoading;
  const projectApprovals = (approvals.data ?? []).filter((a) => workItemIds.has(a.work_item));
  const pending = projectApprovals.filter((a) => a.decision === "pending");
  const decided = projectApprovals.filter((a) => a.decision !== "pending");
  const selected = pending.find((a) => a.id === selectedId) ?? pending[0];

  // Some gates (e.g. the UX Design a11y gate) carry a required WCAG checklist that must be
  // satisfied before APPROVE — surface it here and send the reviewer's ticks with the decision,
  // otherwise the backend rejects the approval with "required gate condition(s) unmet".
  const criteria = useGateCriteria(selected?.id);
  const criteriaList = criteria.data?.criteria ?? [];
  useEffect(() => {
    setSatisfied(Object.fromEntries(criteriaList.map((c) => [c.id, c.satisfied])));
    // reset when the selected gate (and thus its criteria payload) changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [criteria.data, selected?.id]);

  const metCount = criteriaList.filter((c) => satisfied[c.id]).length;
  const requiredUnmet = criteriaList.some((c) => c.required && !satisfied[c.id]);

  const canDecide = (a: Approval) =>
    Boolean(currentUser?.user.is_tenant_admin) || selectedProject?.role === a.required_role;

  const workItemLabel = (id: string) => {
    const wi = workItems.data?.find((w) => w.id === id);
    if (!wi) return id.slice(0, 8);
    return `${wi.key || id.slice(0, 8)} · ${wi.title || wi.type}`;
  };

  const handleDecide = (decision: "approved" | "rejected") => {
    if (!selected) return;
    decideApproval.mutate({
      id: selected.id,
      decision,
      comment: comment || undefined,
      conditions: criteriaList.length
        ? criteriaList.map((c) => ({ key: c.id, satisfied: Boolean(satisfied[c.id]) }))
        : undefined,
    });
    setComment("");
  };

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">
            Gates{" "}
            {!loading && pending.length > 0 && (
              <Badge variant="gate" dot={false}>
                {pending.length} pending
              </Badge>
            )}
          </h1>
          <p className="page-head__sub">
            Approvals awaiting a decision. Only the required role can decide each gate — nothing
            reaches a system-of-record without one.
          </p>
        </div>
      </div>

      <Tabs
        tabs={[
          { id: "pending", label: `Pending (${pending.length})` },
          { id: "history", label: "Decided history" },
        ]}
        active={tab}
        onSelect={(id) => setTab(id as "pending" | "history")}
      />

      {loading ? (
        <Panel>
          <Spinner /> Loading gates…
        </Panel>
      ) : tab === "history" ? (
        <div style={{ marginTop: "var(--space-4)" }}>
          <Panel flush>
            {decided.length === 0 ? (
              <EmptyState title="No decided gates yet" text="Decisions you make will show up here." />
            ) : (
              <Table
                headers={["Gate", "Work item", "Decision", "By", "When"]}
                rows={decided.map((a) => [
                  gateLabel(a.gate_type),
                  <span className="table__id" key="w">
                    {workItemLabel(a.work_item)}
                  </span>,
                  <Badge variant={a.decision === "approved" ? "done" : "failed"} key="d">
                    {a.decision === "approved" ? "Approved" : "Rejected"}
                  </Badge>,
                  a.approver === currentUser?.user.id
                    ? "You"
                    : a.approver_name ?? (a.approver ? a.approver.slice(0, 8) : "—"),
                  a.decided_at ? new Date(a.decided_at).toLocaleString() : "—",
                ])}
              />
            )}
          </Panel>
        </div>
      ) : pending.length === 0 ? (
        <Panel>
          <EmptyState
            title="No gates need you"
            text="Approvals you can act on will appear here and in the notifications bell."
          />
        </Panel>
      ) : (
        <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
          <Panel title="Pending approvals" flush>
            <Table
              headers={["Gate", "Required role", "Work item", "Artifact"]}
              rows={pending.map((a) => ({
                cells: [
                  <button
                    key="g"
                    className="btn btn--ghost btn--sm"
                    onClick={() => setSelectedId(a.id)}
                  >
                    {gateLabel(a.gate_type)}
                  </button>,
                  <span className="chip badge--navy" key="r">
                    {roleLabel(a.required_role)}
                  </span>,
                  <span className="table__id" key="w">
                    {workItemLabel(a.work_item)}
                  </span>,
                  <Link to="/artifacts" key="a">
                    Preview ↗
                  </Link>,
                ],
                style: selected && a.id === selected.id ? { background: "var(--brand-orange-50)" } : undefined,
              }))}
            />
          </Panel>

          {selected &&
            (canDecide(selected) ? (
              <Card attention>
                <CardBody>
                  <span className="gate-panel__role">
                    ▲ {gateLabel(selected.gate_type)} · required role: {roleLabel(selected.required_role)}
                  </span>
                  <h3 className="t-h3">{workItemLabel(selected.work_item)}</h3>
                  <Link to="/artifacts" className="t-sm">
                    Preview artifact under review ↗
                  </Link>
                  {criteriaList.length > 0 && (
                    <div style={{ margin: "var(--space-3) 0 0" }}>
                      <div className="u-row">
                        <span className="gate-panel__role">Required checklist</span>
                        <span className="u-spacer" />
                        <span
                          className="criteria-progress"
                          style={!requiredUnmet ? { color: "var(--success)" } : undefined}
                        >
                          {metCount} of {criteriaList.length} met
                        </span>
                      </div>
                      <CriteriaList>
                        {criteriaList.map((c) => (
                          <div
                            key={c.id}
                            style={{ cursor: "pointer" }}
                            onClick={() => setSatisfied((s) => ({ ...s, [c.id]: !s[c.id] }))}
                          >
                            {/* remount on toggle: CriteriaItem's checkbox is uncontrolled */}
                            <CriteriaItem key={String(satisfied[c.id])} met={Boolean(satisfied[c.id])}>
                              {c.text}
                              {c.required && " *"}
                            </CriteriaItem>
                          </div>
                        ))}
                      </CriteriaList>
                    </div>
                  )}
                  <label className="field" style={{ margin: "var(--space-2) 0 0" }}>
                    <span className="field__label">Comment (optional)</span>
                    <Textarea
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      placeholder="Add context for your decision…"
                    />
                  </label>
                  <div className="gate-panel__actions">
                    <Button
                      variant="primary"
                      disabled={decideApproval.isPending || requiredUnmet}
                      aria-disabled={requiredUnmet}
                      onClick={() => handleDecide("approved")}
                    >
                      {decideApproval.isPending ? (
                        <Spinner />
                      ) : requiredUnmet ? (
                        `Approve (${criteriaList.length - metCount} remaining)`
                      ) : (
                        "Approve"
                      )}
                    </Button>
                    <Button
                      variant="danger"
                      disabled={decideApproval.isPending}
                      onClick={() => handleDecide("rejected")}
                    >
                      Reject
                    </Button>
                  </div>
                  {decideApproval.isError && (
                    <Banner variant="danger" title="Couldn't record the decision">
                      {decideApproval.error instanceof Error ? decideApproval.error.message : "Unknown error"}
                    </Banner>
                  )}
                  <span className="gate-reassure">Decision logged with your role &amp; comment.</span>
                </CardBody>
              </Card>
            ) : (
              <Card>
                <CardBody>
                  <span className="gate-panel__role" style={{ color: "var(--text-muted)" }}>
                    {gateLabel(selected.gate_type)} · {workItemLabel(selected.work_item)}
                  </span>
                  <Banner variant="info" title={`Awaiting ${selected.required_role}`}>
                    You don't hold the <strong>{selected.required_role}</strong> role on this
                    project, so this is read-only.
                  </Banner>
                  <Link to="/artifacts" className="t-sm">
                    Preview artifact under review ↗
                  </Link>
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
            ))}
        </div>
      )}
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
function GatesGallery({ view }: { view: GatesView }) {
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
          active={view === "history" ? "history" : "pending"}
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
                  <Button variant="primary">Approve</Button>
                  <Button variant="danger">Reject</Button>
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
