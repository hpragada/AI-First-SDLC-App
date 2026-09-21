import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  Banner,
  Breadcrumb,
  Button,
  Card,
  CardBody,
  CriteriaItem,
  CriteriaList,
  Panel,
  Spinner,
  Textarea,
  WriteError,
} from "../../components/ui";
import { useDecideApproval, useGateCriteria } from "./hooks";

// S-22 view states: none-ticked · partial · all-ticked · rejected.
export type CriteriaGateView = "none" | "partial" | "all" | "rejected";

export function CriteriaGate({ forceView }: { forceView?: CriteriaGateView }) {
  if (forceView) return <CriteriaGateGallery view={forceView} />;
  return <CriteriaGateLive />;
}

// ── Live: the real approval's criteria checklist ────────────────────────────
function CriteriaGateLive() {
  const { id } = useParams();
  const criteria = useGateCriteria(id);
  const decideApproval = useDecideApproval();
  const [satisfied, setSatisfied] = useState<Record<string, boolean>>({});
  const [comment, setComment] = useState("");
  const [decided, setDecided] = useState<"approved" | "rejected" | null>(null);
  const [revisionRequested, setRevisionRequested] = useState(false);

  useEffect(() => {
    if (criteria.data) {
      setSatisfied(Object.fromEntries(criteria.data.criteria.map((c) => [c.id, c.satisfied])));
    }
  }, [criteria.data]);

  if (criteria.isLoading) {
    return (
      <div className="canvas-pad" style={{ maxWidth: "880px" }}>
        <Panel>
          <Spinner /> Loading gate criteria…
        </Panel>
      </div>
    );
  }

  if (!criteria.data || !id) {
    return (
      <div className="canvas-pad" style={{ maxWidth: "880px" }}>
        <Panel>
          <Banner variant="danger" title="Gate not found">
            This approval doesn't exist or you don't have access to it.
          </Banner>
        </Panel>
      </div>
    );
  }

  const list = criteria.data.criteria;
  const met = list.filter((c) => satisfied[c.id]).length;
  const requiredUnmet = list.some((c) => c.required && !satisfied[c.id]);
  const approveEnabled = !requiredUnmet;

  const canRequestChanges = comment.trim().length > 0;

  const handleDecide = (decision: "approved" | "rejected", revise = false) => {
    setRevisionRequested(revise);
    decideApproval.mutate(
      {
        id,
        decision,
        comment: comment || undefined,
        conditions: list.map((c) => ({ key: c.id, satisfied: Boolean(satisfied[c.id]) })),
        revise,
      },
      { onSuccess: () => setDecided(decision) },
    );
  };

  if (decided === "rejected") {
    return (
      <div className="canvas-pad" style={{ maxWidth: "880px" }}>
        <Breadcrumb items={[{ label: "Gates", href: "/gates" }, "Criteria gate"]} />
        <Card>
          <CardBody>
            <span className="gate-panel__role">Criteria gate</span>
            {/* Only the revise branch may claim rework — this screen used to say "sent back for
                rework" and "a remediation note was sent to the run" on EVERY rejection, and
                neither was true: nothing was sent and nothing re-ran. */}
            {revisionRequested ? (
              <Banner variant="danger" title="Sent back for changes">
                {comment
                  ? `The phase re-runs with your note as its instructions: “${comment}”`
                  : "The phase re-runs with your note as its instructions."}
              </Banner>
            ) : (
              <Banner variant="danger" title="Rejected">
                {comment
                  ? `Recorded: “${comment}”. Nothing re-runs — use Request changes if you want a revision.`
                  : "Recorded. Nothing re-runs — use Request changes if you want a revision."}
              </Banner>
            )}
          </CardBody>
        </Card>
      </div>
    );
  }

  return (
    <div className="canvas-pad" style={{ maxWidth: "880px" }}>
      <Breadcrumb items={[{ label: "Gates", href: "/gates" }, "Criteria gate"]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Gate criteria checklist</h1>
          <p className="page-head__sub">
            A quality gate: approval stays disabled until every required criterion is ticked.
          </p>
        </div>
      </div>

      {decided === "approved" ? (
        <Banner variant="success" title="Approved">
          The gate was approved — the run resumes.
        </Banner>
      ) : (
        <Card attention={approveEnabled} className={approveEnabled ? undefined : "gate-panel"}>
          <CardBody>
            <div className="u-row">
              <span className="gate-panel__role">Criteria</span>
              <span className="u-spacer" />
              <span
                className="criteria-progress"
                style={approveEnabled ? { color: "var(--success)" } : undefined}
              >
                {met} of {list.length} criteria met
              </span>
            </div>
            {list.length === 0 ? (
              <p className="t-sm u-muted">This gate has no checklist — decide directly.</p>
            ) : (
              <CriteriaList>
                {list.map((c) => (
                  <div
                    key={c.id}
                    style={{ cursor: "pointer" }}
                    onClick={() => setSatisfied((s) => ({ ...s, [c.id]: !s[c.id] }))}
                  >
                    {/* remount on toggle: CriteriaItem's checkbox is uncontrolled (defaultChecked) */}
                    <CriteriaItem key={String(satisfied[c.id])} met={Boolean(satisfied[c.id])}>
                      {c.text}
                      {c.required && " *"}
                    </CriteriaItem>
                  </div>
                ))}
              </CriteriaList>
            )}
            <label className="field" style={{ margin: "var(--space-2) 0 0" }}>
              <span className="field__label">Comment</span>
              <Textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Add context for your decision — or say what you want changed…"
              />
            </label>
            <div className="gate-panel__actions">
              <Button
                variant="primary"
                disabled={!approveEnabled || decideApproval.isPending}
                aria-disabled={!approveEnabled}
                onClick={() => handleDecide("approved")}
              >
                {approveEnabled
                  ? decideApproval.isPending
                    ? <Spinner />
                    : "Approve"
                  : `Approve (${list.length - met} remaining)`}
              </Button>
              <Button
                variant="secondary"
                disabled={decideApproval.isPending || !canRequestChanges}
                aria-disabled={!canRequestChanges}
                title={
                  canRequestChanges
                    ? undefined
                    : "Write what you want changed first — the agent re-runs on this text"
                }
                onClick={() => handleDecide("rejected", true)}
              >
                Request changes
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
              <WriteError title="Couldn't record the decision" detail={decideApproval.error} />
            )}
          </CardBody>
        </Card>
      )}
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
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

function CriteriaGateGallery({ view }: { view: CriteriaGateView }) {
  const displayMet = view === "all" ? CRITERIA.length : view === "partial" ? 5 : 0;
  const approveEnabled = view === "all";

  if (view === "rejected") {
    return (
      <div className="canvas-pad" style={{ maxWidth: "880px" }}>
        <Breadcrumb items={[{ label: "Gates", href: "/gates" }, "UX Design · WI-487"]} />
        <Card>
          <CardBody>
            <span className="gate-panel__role">UX Design criteria · WI-487</span>
            <Banner variant="danger" title="Sent back for changes">
              Contrast failed on the secondary buttons. UX Design re-runs with this note as its
              instructions.
            </Banner>
            <label className="field">
              <span className="field__label">What you asked to be changed</span>
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
            A quality gate: approval stays disabled until every required WCAG 2.2 AA criterion is
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
            <Link to="/artifacts" className="t-sm">
              Preview design under review ↗
            </Link>
          )}
          <CriteriaList>
            {CRITERIA.map((text, index) => (
              <CriteriaItem key={text} met={index < displayMet}>
                {text}
              </CriteriaItem>
            ))}
          </CriteriaList>
          <div className="gate-panel__actions">
            <Button variant="primary" disabled={!approveEnabled} aria-disabled={!approveEnabled}>
              {approveEnabled ? "Approve" : `Approve (${CRITERIA.length - displayMet} remaining)`}
            </Button>
            <Button variant="danger">Reject</Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
