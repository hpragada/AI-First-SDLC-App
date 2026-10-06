import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import {
  Badge,
  Banner,
  Button,
  Card,
  CardBody,
  Check,
  ChoiceSelect,
  EmptyState,
  Field,
  Input,
  Panel,
  Select,
  Spinner,
  Tabs,
  writeErrorSentence,
} from "../../components/ui";
import { isRunListening, type Clarification, type ClarificationQuestion } from "../../types";
import { Pager, PhaseFilter, WorkItemFilter } from "./HistoryControls";
import {
  useAnswerClarification,
  useClarificationHistory,
  useClarifications,
  useWorkItem,
  useWorkItems,
} from "./hooks";
import { phaseLabel } from "./phases";
import { useParamState } from "../../urlState";

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

// ── History: what the agent asked and what you told it ─────────────────────
// Every answer here is a decision that shaped a deliverable, and until now it was written once
// and never shown again — the only way to recall what you told an agent three weeks ago was to
// read the artifact it produced and infer backwards. Pending questions deliberately do NOT
// appear: they live in "Needs answer" until they are answered, so the two tabs never disagree
// about what still needs you.
const HISTORY_PAGE_SIZE = 25;

function answerText(value: unknown): string {
  if (value === undefined || value === null || value === "") return "— not answered";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

export function ClarificationHistory({
  projectId,
  // When set, the view is pinned to one work item and the work-item filter disappears — this is
  // the same component embedded on a work item's own page, where "which work item" is already
  // answered by being there.
  workItemId,
}: {
  projectId: string | undefined;
  workItemId?: string;
}) {
  const [workItem, setWorkItem] = useState("");
  const [phase, setPhase] = useState("");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const workItems = useWorkItems(projectId);

  // Search on a pause, not on every keystroke — typing "probation" would otherwise fire nine
  // queries and show eight sets of results nobody asked for.
  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const history = useClarificationHistory({
    project: projectId,
    work_item: workItemId ?? (workItem || undefined),
    phase: phase || undefined,
    q: debounced || undefined,
    page,
  });

  // Any filter change invalidates the page number — page 3 of the old result set is meaningless
  // against the new one, and silently showing an empty page reads as "there is nothing here".
  const applyFilter = (set: (v: string) => void) => (v: string) => {
    set(v);
    setPage(1);
  };

  const rows = (history.data?.results ?? []).filter((c) => c.status !== "pending");

  return (
    <div style={{ marginTop: "var(--space-4)" }}>
      {/* Search on its own full-width row, filters beneath. Sharing one row with two dropdowns
          squeezed the search box to a few characters — the control people reach for first was
          the smallest thing on the screen, and its own placeholder didn't fit inside it. */}
      <div style={{ marginBottom: "var(--space-3)" }}>
        <Input
          type="search"
          aria-label="Search questions and answers"
          placeholder="Search questions and answers…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="history-filters">
          {!workItemId && (
            <WorkItemFilter
              value={workItem}
              onChange={applyFilter(setWorkItem)}
              items={workItems.data ?? []}
            />
          )}
          <PhaseFilter value={phase} onChange={applyFilter(setPhase)} as="slug" />
        </div>
      </div>

      {history.isLoading ? (
        <Panel>
          <Spinner /> Loading history…
        </Panel>
      ) : rows.length === 0 ? (
        <Panel>
          {debounced || workItem || phase ? (
            // Nothing MATCHED is a different fact from nothing EXISTS — saying "none yet" to
            // someone whose search just missed reads as "you never answered anything".
            <EmptyState
              title="Nothing matches those filters"
              text="Try a different search, or clear the filters to see everything."
            />
          ) : (
            <EmptyState
              title="No answered questions yet"
              text="Questions you answer will be kept here, with what you told the agent."
            />
          )}
        </Panel>
      ) : (
        <>
          <Panel flush>
            {rows.map((c) => {
              const expanded = Boolean(open[c.id]);
              return (
                <div key={c.id} className="clar-history__row">
                  <button
                    type="button"
                    className="clar-history__head"
                    aria-expanded={expanded}
                    onClick={() => setOpen((o) => ({ ...o, [c.id]: !o[c.id] }))}
                  >
                    <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
                    <span className="u-stack-tight">
                      <span className="t-sm">
                        {c.work_item_title || c.work_item.slice(0, 8)}
                      </span>
                      <span className="t-xs u-muted">
                        {phaseLabel(c.phase)} · {c.questions.length} question
                        {c.questions.length === 1 ? "" : "s"}
                        {c.answered_by_name ? ` · answered by ${c.answered_by_name}` : ""}
                        {c.answered_at ? ` · ${new Date(c.answered_at).toLocaleString()}` : ""}
                      </span>
                    </span>
                    <span className="u-spacer" />
                    <Badge variant={c.status === "answered" ? "done" : "failed"}>
                      {c.status === "answered" ? "Answered" : "Cancelled"}
                    </Badge>
                  </button>

                  {expanded && (
                    <div className="clar-history__body">
                      {c.context && <p className="clar-card__why">{c.context}</p>}
                      {groupByTier(c.questions).map(({ tier, questions }) => (
                        <section key={tier} className="clar-tier" data-tier={tier}>
                          <div className="clar-tier__head">
                            <span className={`clar-tier__badge clar-tier__badge--t${tier}`}>
                              {TIER_META[tier].title}
                            </span>
                          </div>
                          {questions.map((q) => (
                            <div key={q.id} className="clar-history__qa">
                              <p className="t-sm u-muted">{q.text}</p>
                              <p className="t-sm u-body">{answerText(c.answers?.[q.id])}</p>
                            </div>
                          ))}
                        </section>
                      ))}
                      {/* The link already goes to that run; printing its id as the label added
                          nothing a person could use. Same decision as the Run console's own
                          Run ID, 2026-10-05. */}
                      <Link className="t-sm" to={`/runs/${c.run}`}>
                        Open the run that asked this ↗
                      </Link>
                    </div>
                  )}
                </div>
              );
            })}
          </Panel>
          <Pager
            page={page}
            count={history.data?.count ?? 0}
            pageSize={HISTORY_PAGE_SIZE}
            onPage={setPage}
            noun="answered questions"
          />
        </>
      )}
    </div>
  );
}

// ── Live: real pending clarifications for the selected project ─────────────
function ClarificationsLive() {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  // Scoped to the project by the API, NOT narrowed against the backlog here. A question asked
  // by a run on a hidden carrier work item — accessibility judging, code indexing, the gap
  // report — has no row in `useWorkItems` (`carrier_q` excludes them by design), so filtering
  // on it hid exactly the questions nobody else can answer and left those runs waiting for
  // ever. Hiding plumbing from a board is right; hiding a question that blocks a run is not.
  // Arrives only in a link, from a work item's "At a glance" card — so the URL is its only
  // source, exactly as the artifact registry treats its own scopes.
  const [searchParams] = useSearchParams();
  const workItemScope = searchParams.get("work_item") ?? "";
  const scopedItem = useWorkItem(workItemScope || undefined);
  const clarifications = useClarifications({
    status: "pending",
    project: projectId,
    ...(workItemScope ? { work_item: workItemScope } : {}),
  });
  const answer = useAnswerClarification();
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  // Free text typed against an "Other (please specify)" choice, keyed by question id.
  const [otherText, setOtherText] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState(false);
  const [justAnswered, setJustAnswered] = useState<Clarification | null>(null);
  const [tab, setTab] = useState<"pending" | "history">("pending");

  // `!projectId` counts as loading. The query drops an empty filter rather than sending one, so
  // without this the half-second before the project resolves would fetch the WHOLE workspace's
  // pending questions and show another project's on this one's screen. It never did before,
  // because the backlog it used to filter against was empty until the project resolved too.
  const loading = !projectId || clarifications.isLoading;
  const pending = projectId ? (clarifications.data ?? []) : [];
  // N2: this screen answers ONE question at a time and always picked `pending[0]`, so "Answer the
  // question" beside a question whose text you had just read could open a DIFFERENT one. That is
  // worse than landing on a list: it invites the wrong answer to be typed into the wrong box.
  const [askedFor, , pinnedFromUrl] = useParamState("clarification");
  const current = pending.find((c) => c.id === askedFor) ?? (pinnedFromUrl ? undefined : pending[0]);
  // NOTE the answer-form effect below keys on `currentId` — the RESOLVED clarification, never on
  // the param. Keying it on the param would re-run when the URL changed to something that is not
  // in the list and wipe a half-typed answer.
  const currentId = current?.id;
  const staleLink = pinnedFromUrl && Boolean(askedFor) && !current && !loading;

  // Whenever a new clarification surfaces, seed the form with the agent's Tier-2/3
  // suggestions so agreeing is one click and only Tier-1 blanks remain.
  useEffect(() => {
    setAnswers(current ? suggestionDefaults(current.questions) : {});
    setOtherText({});
    setTouched(false);
    // Keyed on the clarification id only — re-seeding on every render would wipe edits.
  }, [currentId]);

  // Read off the clarification itself rather than looked up in the backlog. The serializer
  // already resolves `work_item_title` for every clarification, including the ones whose work
  // item is hidden plumbing — so a judging run's question reads "Accessibility judging" instead
  // of a bare uuid, which is the whole reason the lookup existed.
  // The readable key, never the internal id. This used to print eight characters of a uuid
  // beside every question — the same thing the defect screen was printing as its parent. A
  // clarification whose work item is hidden plumbing has a title but no key, and a title alone
  // reads better than a fragment of an identifier nobody can use.
  const workItemLabel = (c: Clarification) =>
    [c.work_item_key, c.work_item_title].filter(Boolean).join(" · ") || "Work item";

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
            {/* Bugs S.No 184: the browser's own dropdown ran agent-written, sentence-long options
                off the card on one unbroken line — the operating system draws that list, so
                nothing here could bound it or wrap it. The answer, and the "Other" box beneath
                it, behave exactly as before; only who draws the list has changed. */}
            <ChoiceSelect
              value={(answers[q.id] as string) ?? ""}
              onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))}
              options={q.options.map((opt) => ({ value: opt, label: opt }))}
              invalid={touched && q.required && resolvedAnswer(q) === undefined}
            />
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

      <Tabs
        tabs={[
          { id: "pending", label: `Needs answer (${pending.length})` },
          { id: "history", label: "History" },
        ]}
        active={tab}
        onSelect={(id) => setTab(id as "pending" | "history")}
      />

      {/* Arrived from one work item's "At a glance" card. Without this notice, seeing two
          questions here would reasonably read as "the project has two" while another work item
          sat with five. Mirrors the artifact registry's scope notice, which this screen's
          readers have already met. The HISTORY tab is deliberately left project-wide. */}
      {workItemScope && tab !== "history" && (
        <Banner variant="info" title="Showing questions for one work item">
          <p className="t-sm">
            {[scopedItem.data?.key, scopedItem.data?.title].filter(Boolean).join(" · ") ||
              "One work item"}
            . Other work items may have questions waiting too.
          </p>
          <Link to="/clarifications" className="btn btn--secondary btn--sm">
            Show all questions
          </Link>
        </Banner>
      )}

      {/* Not on the history tab (S.No 319). The whole job of this notice is to send you to the
          answered history; once you are there it has nothing left to say, and its button —
          which only switches to this tab — does nothing at all when pressed. */}
      {staleLink && tab !== "history" && (
        <Banner variant="info" title="That question has already been answered">
          <p className="t-sm">
            Nothing is open, so no answer can land on the wrong question. If it was just answered,
            it is in the answered history.
          </p>
          <Button variant="secondary" size="sm" onClick={() => setTab("history")}>
            Look in the answered history
          </Button>
        </Banner>
      )}

      {tab === "history" ? (
        <ClarificationHistory projectId={projectId} />
      ) : loading ? (
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
                  {workItemLabel(justAnswered)} — run resumed.
                </span>
              </CardBody>
            </Card>
          )}
        </Panel>
      ) : (
        <Card className="clar-card">
          <CardBody>
            <div className="clar-card__head">
              <span className="wi-card__id">{workItemLabel(current)}</span>
              <Badge variant="needs-answer">{phaseLabel(current.phase)} · needs answer</Badge>
              <span className="u-spacer" />
              {isRunListening(current.run_status) ? (
                <span className="zero-cost">⏸ Paused — waiting for your answer</span>
              ) : (
                <span className="t-xs u-muted">⚠ This run has ended</span>
              )}
            </div>
            {!isRunListening(current.run_status) && (
              // The agent that asked this is gone (run fad927a2: its poll died, the phase
              // reported, the run parked). Answering cannot resume anything — but the answer
              // is replayed into the next run's manifest, so it is still worth giving. Say
              // exactly that instead of promising a resume that cannot happen.
              <p className="clar-card__why">
                The run that asked this has already ended, so answering won't resume it. Your
                answers are still saved and replayed the next time you run this phase — so
                answer here, then re-run the phase and it won't ask again.
              </p>
            )}
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
                {writeErrorSentence(answer.error, "Couldn't submit the answer.")}
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
