import { useState } from "react";

import { Badge, Button, Card, CardBody, Check, EmptyState, Field, Input, Panel, Select } from "../../components/ui";
import { useAnswerClarification } from "./hooks";

// S-20 view states: one-pending(confirm) · multi-question · required-error ·
// already-answered · cancelled · empty.
export type ClarificationsView =
  | "one-pending"
  | "multi"
  | "required-error"
  | "answered"
  | "cancelled"
  | "empty";

export function Clarifications({ forceView }: { forceView?: ClarificationsView }) {
  const answer = useAnswerClarification();
  const [submitted, setSubmitted] = useState(false);
  const [touched, setTouched] = useState(false);
  const view: ClarificationsView = forceView ?? (submitted ? "answered" : "one-pending");

  const onSubmitOne = () => {
    setTouched(true);
    answer.mutate({ id: "clar-1", answers: { csv_export: true } });
    setSubmitted(true);
  };

  return (
    <div className="canvas-pad" style={{ maxWidth: "880px" }}>
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Clarifications</h1>
          <p className="page-head__sub">
            Questions your agents are waiting on. Answering resumes the run in the same session —
            and nothing is billed while it waits.
          </p>
        </div>
      </div>

      {view === "empty" && (
        <Panel>
          <EmptyState
            title="No questions waiting"
            text="When an agent needs input, it pauses (billing $0) and the question appears here."
          />
        </Panel>
      )}

      {view === "one-pending" && (
        <Card className="clar-card">
          <CardBody>
            <div className="clar-card__head">
              <span className="wi-card__id">WI-510</span>
              <Badge variant="needs-answer">Requirements · needs answer</Badge>
              <span className="u-spacer" />
              <span className="zero-cost">⏸ Paused — no usage billed while waiting · 6m</span>
            </div>
            <p className="t-body u-strong">Should the analytics dashboard support CSV export in v1?</p>
            <p className="clar-card__why">
              <span className="lbl">Why I'm asking:</span> Affects the data-export NFR scope.
            </p>
            <Check>Yes — include CSV export in v1</Check>
            <div className="gate-panel__actions">
              <Button variant="primary" onClick={onSubmitOne} disabled={answer.isPending}>
                Submit answer
              </Button>
              <Button variant="ghost">Skip for now</Button>
            </div>
          </CardBody>
        </Card>
      )}

      {view === "multi" && (
        <Card className="clar-card">
          <CardBody>
            <div className="clar-card__head">
              <span className="wi-card__id">WI-492</span>
              <Badge variant="needs-answer">Architecture · needs answer</Badge>
              <span className="u-spacer" />
              <span className="zero-cost">⏸ $0 while waiting · 2m</span>
            </div>
            <p className="clar-card__why">
              <span className="lbl">Why I'm asking:</span> Three details unblock the sequence diagram.
            </p>
            <Field
              label={
                <>
                  1 · Which Confluence space should the spec publish to? <span className="req">*</span>
                </>
              }
            >
              <Input type="text" placeholder="e.g. PAY" />
            </Field>
            <Field
              label={
                <>
                  2 · Preferred retry strategy for failed webhooks? <span className="req">*</span>
                </>
              }
            >
              <Select>
                <option value="">Choose one…</option>
                <option>Exponential backoff</option>
                <option>Fixed interval</option>
                <option>Dead-letter queue</option>
              </Select>
            </Field>
            <Check>3 · Require signature verification on every event (recommended)</Check>
            <div className="gate-panel__actions">
              <Button variant="primary">Submit answers</Button>
            </div>
          </CardBody>
        </Card>
      )}

      {view === "required-error" && (
        <Card className="clar-card">
          <CardBody>
            <div className="clar-card__head">
              <span className="wi-card__id">WI-492</span>
              <Badge variant="needs-answer">Architecture · needs answer</Badge>
            </div>
            <Field
              label={
                <>
                  Which Confluence space should the spec publish to? <span className="req">*</span>
                </>
              }
              error="This answer is required before the run can resume."
            >
              <Input type="text" aria-invalid />
            </Field>
            <div className="gate-panel__actions">
              <Button variant="primary">Submit answers</Button>
            </div>
          </CardBody>
        </Card>
      )}

      {view === "answered" && (
        <Card>
          <CardBody style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
            <Badge variant="done">Answered</Badge>
            <span className="t-sm u-body">
              WI-510 · "CSV export in v1?" — answered <strong>Yes</strong> by{" "}
              {touched ? "you" : "Sarah Chen"} · run resumed.
            </span>
            <span className="u-spacer" />
            <Button variant="ghost" size="sm">
              View
            </Button>
          </CardBody>
        </Card>
      )}

      {view === "cancelled" && (
        <Card>
          <CardBody style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
            <Badge variant="neutral">Cancelled</Badge>
            <span className="t-sm u-muted">
              WI-487 · question withdrawn when the run was re-dispatched.
            </span>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
