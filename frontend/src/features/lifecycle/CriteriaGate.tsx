import { Banner, Breadcrumb, Button, Card, CardBody, CriteriaItem, CriteriaList, Textarea } from "../../components/ui";
import { useDecideApproval } from "./hooks";

// S-22 view states: none-ticked · partial · all-ticked · rejected.
export type CriteriaGateView = "none" | "partial" | "all" | "rejected";

const CRITERIA = [
  "Color contrast ≥ 4.5:1 for body text",
  "Keyboard navigable end-to-end",
  "Visible focus on all interactive controls",
  "Hit targets ≥ 40px",
  "Form fields have programmatic labels",
  "Status never encoded by color alone",
  "Respects prefers-reduced-motion",
  "Images have text alternatives",
];

export function CriteriaGate({ forceView = "none" }: { forceView?: CriteriaGateView }) {
  const decideApproval = useDecideApproval();
  const view = forceView;

  const displayMet = view === "all" ? CRITERIA.length : view === "partial" ? 5 : 0;
  const approveEnabled = view === "all";

  if (view === "rejected") {
    return (
      <div className="canvas-pad" style={{ maxWidth: "880px" }}>
        <Breadcrumb items={[{ label: "Gates", href: "/gates" }, "UX Design · WI-487"]} />
        <Card>
          <CardBody>
            <span className="gate-panel__role">UX Design criteria · WI-487</span>
            <Banner variant="danger" title="Rejected — sent back for rework">
              Contrast failed on the secondary buttons. A remediation note was sent to the run; the
              design returns to UX Design.
            </Banner>
            <label className="field">
              <span className="field__label">Rejection comment</span>
              <Textarea defaultValue="Secondary button text is 3.1:1 on white — bump to navy text or darken the fill." />
            </label>
          </CardBody>
        </Card>
      </div>
    );
  }

  return (
    <div className="canvas-pad" style={{ maxWidth: "880px" }}>
      <Breadcrumb items={[{ label: "Gates", href: "/gates" }, "UX Design · WI-487"]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">UX Design gate — Checkout Flow Redesign</h1>
          <p className="page-head__sub">
            A quality gate: approval stays disabled until every required WCAG 2.1 AA criterion is
            ticked. The product gates on accessibility, so the product must pass.
          </p>
        </div>
        <span className="meta-item">
          <span className="chip badge--navy">designer</span>
        </span>
      </div>

      <Card attention={view === "all"} className={view === "all" ? undefined : "gate-panel"}>
        <CardBody>
          <div className="u-row">
            <span className="gate-panel__role">UX Design criteria · WI-487</span>
            <span className="u-spacer" />
            <span
              className="criteria-progress"
              style={view === "all" ? { color: "var(--success)" } : undefined}
            >
              {displayMet} of {CRITERIA.length} criteria met
            </span>
          </div>
          {view === "none" && (
            <a href="/artifacts" className="t-sm">
              Preview design under review ↗
            </a>
          )}
          <CriteriaList>
            {CRITERIA.map((text, index) => (
              <CriteriaItem key={text} met={index < displayMet}>
                {text}
              </CriteriaItem>
            ))}
          </CriteriaList>
          <div className="gate-panel__actions">
            <Button
              variant="primary"
              disabled={!approveEnabled}
              aria-disabled={!approveEnabled}
              onClick={() => decideApproval.mutate({ id: "approval-22", decision: "approved" })}
            >
              {approveEnabled ? "Approve" : `Approve (${CRITERIA.length - displayMet} remaining)`}
            </Button>
            <Button
              variant="danger"
              onClick={() => decideApproval.mutate({ id: "approval-22", decision: "rejected" })}
            >
              Reject
            </Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
