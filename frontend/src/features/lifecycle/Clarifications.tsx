import { useEffect, useState } from "react";

import { useAuth } from "../../auth/AuthContext";
import {
  Badge,
  Button,
  Card,
  CardBody,
  Check,
  EmptyState,
  Field,
  Input,
  Panel,
  Select,
  Spinner,
} from "../../components/ui";
import type { Clarification, ClarificationQuestion } from "../../types";
import { useAnswerClarification, useClarifications, useWorkItems } from "./hooks";
import { phaseLabel } from "./phases";

// S-20 view states: one-pending(confirm) · multi-question · tiered (all three tiers) ·
// required-error · already-answered · cancelled · empty.
export type ClarificationsView =
  | "one-pending"
  | "multi"
  | "tiered"
  | "required-error"
  | "answered"
  | "cancelled"
  | "empty";

// ── Tier model (surface-all-tiers gate) ────────────────────────────────────
// Every context gap is surfaced through the gate grouped by tier. A question with no `tier`
// is treated as Tier 1 (legacy questions), so nothing regresses.
export const TIER_META: Record<1 | 2 | 3, { title: string; hint: string }> = {
  1: { title: "Tier 1 · Must answer", hint: "Business decisions the agent can't make for you." },
  2: { title: "Tier 2 · Suggested", hint: "The agent's recommendation — confirm or adjust." },
  3: {
    title: "Tier 3 · Industry-standard inference",
    hint: "High-confidence defaults — accept or override.",
  },
};

export function tierOf(q: ClarificationQuestion): 1 | 2 | 3 {
  return q.tier === 2 ? 2 : q.tier === 3 ? 3 : 1;
}

// Ordered, non-empty tier groups; question order within a tier is preserved.
export function groupByTier(
  questions: ClarificationQuestion[],
): { tier: 1 | 2 | 3; questions: ClarificationQuestion[] }[] {
  const groups: { tier: 1 | 2 | 3; questions: ClarificationQuestion[] }[] = [];
  for (const tier of [1, 2, 3] as const) {
    const qs = questions.filter((q) => tierOf(q) === tier);
    if (qs.length) groups.push({ tier, questions: qs });
  }
  return groups;
}

// Pre-fill Tier-2/3 answers with the agent's suggestion so the human can accept in one click
// (and leaving one untouched still submits a concrete value — the backend mirrors this).
export function suggestionDefaults(questions: ClarificationQuestion[]): Record<string, unknown> {
  const init: Record<string, unknown> = {};
  for (const q of questions) {
    if ((tierOf(q) === 2 || tierOf(q) === 3) && q.suggestion !== undefined) {
      init[q.id] = q.suggestion;
    }
  }
  return init;
}

// An option that lets the user supply their own answer (e.g. "Other", "Other (please
// specify)", "Something else — please specify"). When picked we reveal a free-text box.
// Agents routinely prefix options with an enumerator ("a) ", "3. ", "- "), so we strip a
// leading enumerator before matching — otherwise "d) Other" fails the start-anchored test and
// the free-text box silently never renders (Bugs S.No 60).
export function isOtherOption(option: string): boolean {
  const bare = option.replace(/^\s*(?:[a-z]|\d+)[).:-]\s*/i, "").trim();
  return /^(other|something else)\b/i.test(bare) || /please specify/i.test(bare);
}

export function Clarifications({ forceView }: { forceView?: ClarificationsView }) {
  if (forceView) return <ClarificationsGallery view={forceView} />;
  return <ClarificationsLive />;
}

// ── Live: real pending clarifications for the selected project ─────────────
function ClarificationsLive() {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const workItems = useWorkItems(projectId);
  const workItemIds = new Set((workItems.data ?? []).map((w) => w.id));
  const clarifications = useClarifications({ status: "pending" });
  const answer = useAnswerClarification();
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  // Free text typed against an "Other (please specify)" choice, keyed by question id.
  const [otherText, setOtherText] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState(false);
  const [justAnswered, setJustAnswered] = useState<Clarification | null>(null);

  const loading = clarifications.isLoading || workItems.isLoading;
  const pending = (clarifications.data ?? []).filter((c) => workItemIds.has(c.work_item));
  const current = pending[0];
  const currentId = current?.id;

  // Whenever a new clarification surfaces, seed the form with the agent's Tier-2/3
  // suggestions so agreeing is one click and only Tier-1 blanks remain.
  useEffect(() => {
    setAnswers(current ? suggestionDefaults(current.questions) : {});
    setOtherText({});
    setTouched(false);
    // Keyed on the clarification id only — re-seeding on every render would wipe edits.
  }, [currentId]);

  const workItemLabel = (id: string) => {
    const wi = workItems.data?.find((w) => w.id === id);
    return wi ? `${id.slice(0, 8)} · ${wi.title || wi.type}` : id.slice(0, 8);
  };

  // The answer actually submitted for a question. For a choice where the selected option is
  // the "Other (please specify)" one, that's the free text the user typed — not the literal
  // option label (which the agent can't act on). Empty free text counts as unanswered.
  const resolvedAnswer = (q: Clarification["questions"][number]): unknown => {
    const raw = answers[q.id];
    if (q.kind === "choice" && typeof raw === "string" && isOtherOption(raw)) {
      const typed = (otherText[q.id] ?? "").trim();
      return typed === "" ? undefined : typed;
    }
    return raw;
  };

  const missingRequired = current
    ? current.questions.filter((q) => q.required && resolvedAnswer(q) === undefined)
    : [];

  const handleSubmit = () => {
    if (!current) return;
    setTouched(true);
    if (missingRequired.length > 0) return;
    const payload: Record<string, unknown> = {};
    for (const q of current.questions) {
      const value = resolvedAnswer(q);
      if (value !== undefined) payload[q.id] = value;
    }
    answer.mutate(
      { id: current.id, answers: payload },
      {
        onSuccess: () => {
          setJustAnswered(current);
          setAnswers({});
          setOtherText({});
          setTouched(false);
        },
      },
    );
  };

  // Restore every Tier-2/3 field to the agent's suggestion (the one-click "I agree").
  const acceptAllSuggestions = () => {
    if (!current) return;
    setAnswers((a) => ({ ...a, ...suggestionDefaults(current.questions) }));
    setOtherText({});
  };

  // One question's input + label, numbered by its position across the whole gate.
  const renderQuestion = (q: Clarification["questions"][number]) => {
    const number = current ? current.questions.findIndex((x) => x.id === q.id) + 1 : 0;
    return (
      <Field
        key={q.id}
        label={
          <>
            {current && current.questions.length > 1 ? `${number} · ` : ""}
            {q.text} {q.required && <span className="req">*</span>}
          </>
        }
        error={
          touched && q.required && resolvedAnswer(q) === undefined
            ? "This answer is required before the run can resume."
            : undefined
        }
      >
        {q.kind === "confirm" ? (
          <Check
            checked={Boolean(answers[q.id])}
            onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.checked }))}
          >
            Yes
          </Check>
        ) : q.kind === "choice" && q.options?.length ? (
          <>
            <Select
              value={(answers[q.id] as string) ?? ""}
              onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
              aria-invalid={touched && q.required && resolvedAnswer(q) === undefined}
            >
              <option value="">Choose one…</option>
              {q.options.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </Select>
            {typeof answers[q.id] === "string" && isOtherOption(answers[q.id] as string) && (
              <Input
                type="text"
                placeholder="Please specify…"
                aria-label="Please specify"
                style={{ marginTop: "var(--space-2)" }}
                value={otherText[q.id] ?? ""}
                onChange={(e) => setOtherText((o) => ({ ...o, [q.id]: e.target.value }))}
                aria-invalid={touched && q.required && resolvedAnswer(q) === undefined}
              />
            )}
          </>
        ) : (
          <Input
            type="text"
            placeholder="Type your answer…"
            value={(answers[q.id] as string) ?? ""}
            onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
            aria-invalid={touched && q.required && resolvedAnswer(q) === undefined}
          />
        )}
      </Field>
    );
  };

  return (
    <div className="canvas-pad" style={{ maxWidth: "880px" }}>
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Clarifications</h1>
          <p className="page-head__sub">
            Questions your agents are waiting on. Answering resumes the run in the same session.
          </p>
        </div>
      </div>

      {loading ? (
        <Panel>
          <Spinner /> Loading clarifications…
        </Panel>
      ) : !current ? (
        <Panel>
          <EmptyState
            title="No questions waiting"
            text="When an agent needs input, it pauses and the question appears here."
          />
          {justAnswered && (
            <Card style={{ marginTop: "var(--space-4)" }}>
              <CardBody style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
                <Badge variant="done">Answered</Badge>
                <span className="t-sm u-body">
                  {workItemLabel(justAnswered.work_item)} — run resumed.
                </span>
              </CardBody>
            </Card>
          )}
        </Panel>
      ) : (
        <Card className="clar-card">
          <CardBody>
            <div className="clar-card__head">
              <span className="wi-card__id">{workItemLabel(current.work_item)}</span>
              <Badge variant="needs-answer">{phaseLabel(current.phase)} · needs answer</Badge>
              <span className="u-spacer" />
              <span className="zero-cost">⏸ Paused — waiting for your answer</span>
            </div>
            {current.context && <p className="clar-card__why">{current.context}</p>}
            {groupByTier(current.questions).map(({ tier, questions }) => (
              <section key={tier} className="clar-tier" data-tier={tier}>
                <div className="clar-tier__head">
                  <span className={`clar-tier__badge clar-tier__badge--t${tier}`}>
                    {TIER_META[tier].title}
                  </span>
                  <span className="clar-tier__hint">{TIER_META[tier].hint}</span>
                </div>
                {questions.map((q) => renderQuestion(q))}
              </section>
            ))}
            <div className="gate-panel__actions">
              <Button variant="primary" onClick={handleSubmit} disabled={answer.isPending}>
                {answer.isPending ? (
                  <Spinner />
                ) : current.questions.length > 1 ? (
                  "Submit answers"
                ) : (
                  "Submit answer"
                )}
              </Button>
              {current.questions.some((q) => tierOf(q) !== 1) && (
                <Button variant="ghost" onClick={acceptAllSuggestions} disabled={answer.isPending}>
                  Accept all suggestions &amp; inferences
                </Button>
              )}
            </div>
            {answer.isError && (
              <p className="t-sm" style={{ color: "var(--danger)", marginTop: "var(--space-2)" }}>
                {answer.error instanceof Error ? answer.error.message : "Couldn't submit the answer."}
              </p>
            )}
          </CardBody>
        </Card>
      )}
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
function ClarificationsGallery({ view }: { view: ClarificationsView }) {
  return (
    <div className="canvas-pad" style={{ maxWidth: "880px" }}>
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Clarifications</h1>
          <p className="page-head__sub">
            Questions your agents are waiting on. Answering resumes the run in the same session.
          </p>
        </div>
      </div>

      {view === "empty" && (
        <Panel>
          <EmptyState
            title="No questions waiting"
            text="When an agent needs input, it pauses and the question appears here."
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
              <span className="zero-cost">⏸ Paused — waiting for your answer · 6m</span>
            </div>
            <p className="t-body u-strong">Should the analytics dashboard support CSV export in v1?</p>
            <p className="clar-card__why">
              <span className="lbl">Why I'm asking:</span> Affects the data-export NFR scope.
            </p>
            <Check>Yes — include CSV export in v1</Check>
            <div className="gate-panel__actions">
              <Button variant="primary">Submit answer</Button>
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

      {view === "tiered" && (
        <Card className="clar-card">
          <CardBody>
            <div className="clar-card__head">
              <span className="wi-card__id">WI-492</span>
              <Badge variant="needs-answer">PRD · needs answer</Badge>
              <span className="u-spacer" />
              <span className="zero-cost">⏸ $0 while waiting</span>
            </div>
            <p className="clar-card__why">
              <span className="lbl">Why I'm asking:</span> A few decisions shape the PRD — I've
              pre-filled my suggestions and inferences; confirm or change them.
            </p>
            <section className="clar-tier" data-tier={1}>
              <div className="clar-tier__head">
                <span className="clar-tier__badge clar-tier__badge--t1">{TIER_META[1].title}</span>
                <span className="clar-tier__hint">{TIER_META[1].hint}</span>
              </div>
              <Field label={<>1 · Which billing model should v1 support? <span className="req">*</span></>}>
                <Select>
                  <option value="">Choose one…</option>
                  <option>Subscription</option>
                  <option>Usage-based</option>
                </Select>
              </Field>
            </section>
            <section className="clar-tier" data-tier={2}>
              <div className="clar-tier__head">
                <span className="clar-tier__badge clar-tier__badge--t2">{TIER_META[2].title}</span>
                <span className="clar-tier__hint">{TIER_META[2].hint}</span>
              </div>
              <Field label={<>2 · Data-retention window for expense records?</>}>
                <Input type="text" defaultValue="90 days" />
              </Field>
            </section>
            <section className="clar-tier" data-tier={3}>
              <div className="clar-tier__head">
                <span className="clar-tier__badge clar-tier__badge--t3">{TIER_META[3].title}</span>
                <span className="clar-tier__hint">{TIER_META[3].hint}</span>
              </div>
              <Field label={<>3 · Store timestamps in UTC?</>}>
                <Input type="text" defaultValue="UTC" />
              </Field>
            </section>
            <div className="gate-panel__actions">
              <Button variant="primary">Submit answers</Button>
              <Button variant="ghost">Accept all suggestions &amp; inferences</Button>
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
              WI-510 · "CSV export in v1?" — answered <strong>Yes</strong> by Sarah Chen · run resumed.
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
