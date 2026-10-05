// S-36 — the accessibility review console (QA-23).
//
// The platform refuses to guess. When a check cannot settle an element it marks the finding
// "needs review" and puts it aside; this is where a person picks that up and answers it. Their
// answer becomes the platform's answer — confirming raises a real defect, rejecting closes the
// finding — so every state here is written to be honest about what is about to happen.
//
// Layout is `grid--console` (a narrow rail, then the workspace), NOT `grid--detail` (content
// plus a 320px sidebar). The mockup used the latter and put the panel holding a screenshot, a
// note box and three decision buttons into the 320px slot, which clipped the buttons off the
// edge — D-A11Y-99. The list is the narrow half; the item under review is the wide one.
import { useState } from "react";

import { useParamState } from "../../urlState";

import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import {
  Badge,
  Banner,
  Button,
  EmptyState,
  Panel,
  Skeleton,
  Textarea,
  writeErrorSentence,
} from "../../components/ui";
import type { A11yReviewItem } from "../../types";
import { A11yTabs } from "./A11yTabs";
import { Capture } from "./Capture";
import { LoadFailed } from "./LoadFailed";
import { useA11yReviewItem, useA11yReviewQueue, useDecideA11yFinding } from "./hooks";

const SEVERITY_BADGE: Record<string, "failed" | "waiting" | "neutral"> = {
  critical: "failed",
  high: "failed",
  medium: "waiting",
  low: "neutral",
};

// An `uncertain` verdict carries a confidence of 0 by construction. Printing "0%" reads as
// "the AI was 0% confident" when it means "the AI gave no verdict" — two different facts, and
// the wrong one would make a reviewer distrust a check that behaved correctly (D-A11Y-95).
function verdictLabel(item: A11yReviewItem): string {
  if (item.verdict === "uncertain" || item.confidence == null) return "No verdict";
  return `Not sure · ${Math.round(item.confidence * 100)}%`;
}

function QueueRow({
  item,
  selected,
  onSelect,
}: {
  item: A11yReviewItem;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className="artifact-row"
      style={{
        width: "100%",
        textAlign: "left",
        background: selected ? "var(--brand-orange-50)" : "transparent",
        border: 0,
        cursor: "pointer",
      }}
      aria-current={selected ? "true" : undefined}
      onClick={onSelect}
    >
      <div className="artifact-row__main">
        <div className="artifact-row__title">
          {item.criterion} {item.criterion_handle}
        </div>
        <div className="artifact-row__meta">
          {item.route} · <span className="t-mono">{item.selector}</span>
        </div>
        <div className="u-row" style={{ marginTop: 6 }}>
          {item.wcag_level && (
            <Badge variant="outline" dot={false}>
              Level {item.wcag_level}
            </Badge>
          )}
          <Badge variant="waiting">{verdictLabel(item)}</Badge>
        </div>
      </div>
    </button>
  );
}

// Mounted with `key={finding.id}`, so switching items REMOUNTS this and every piece of local
// state (the note, the submitted banner, the capture's zoom mode) resets by construction. No
// reset effect, and none wanted: an effect that has to remember to clear four things is how a
// reviewer's note ends up on the next reviewer's finding.
function ItemPanel({
  projectId,
  findingId,
  onDecided,
}: {
  projectId: string;
  findingId: string;
  onDecided: () => void;
}) {
  const query = useA11yReviewItem(projectId, findingId);
  const decide = useDecideA11yFinding(projectId);
  const [note, setNote] = useState("");
  const [done, setDone] = useState<{ decision: string; opens_defect: boolean } | undefined>();

  if (query.isLoading) {
    return (
      <Panel title="Loading the finding">
        <Skeleton kind="title" />
        <Skeleton />
        <Skeleton kind="block" />
      </Panel>
    );
  }
  if (query.isError || !query.data) {
    return (
      <Panel title="This finding could not be opened">
        <Banner variant="danger" title="Not found">
          It may have been resolved by a later run, or answered by someone else.
        </Banner>
      </Panel>
    );
  }

  const item = query.data;
  const readOnly = item.can_review === false;
  const lockedOut = Boolean(item.locked_out);

  if (done) {
    return (
      <Panel title={`${item.criterion} ${item.criterion_handle}`}>
        <Banner
          variant={done.decision === "confirm" ? "success" : "info"}
          title={done.decision === "confirm" ? "Recorded as a real problem" : "Recorded as fine"}
        >
          {done.decision === "confirm"
            ? done.opens_defect
              ? "A defect has been opened against this work item, and it closes itself when a later run stops finding the problem."
              : "It is recorded as a failure. This project's policy does not raise a ticket at this severity, so no defect was opened — the finding is still in the report."
            : "The finding is closed and will not come back unless the element itself changes."}
        </Banner>
        <p className="t-sm u-muted" style={{ marginTop: "var(--space-3)" }}>
          Recorded against your name and the WCAG criterion.
        </p>
        <div className="gate-panel__actions">
          <Button variant="primary" onClick={onDecided}>
            Next item
          </Button>
        </div>
      </Panel>
    );
  }

  return (
    <Panel
      title={`${item.criterion} ${item.criterion_handle}`}
      actions={
        item.wcag_level ? (
          <Badge variant="outline" dot={false}>
            Level {item.wcag_level}
          </Badge>
        ) : undefined
      }
    >
      <div className="meta-row">
        <span className="meta-item">
          Screen <strong>{item.route}</strong>
        </span>
        <span className="meta-item">
          Element <span className="t-mono">{item.selector}</span>
        </span>
        {item.checker && (
          <span className="meta-item">
            Check <strong>{item.checker}</strong>
          </span>
        )}
        {/* Where this finding came from. This row is already where the screen puts provenance —
            the decided state shows "Decided by …" here — so it belongs beside the other facts a
            reviewer reads before judging, not as a new line of its own.

            Absent entirely on a baseline audit, where there is no story, no test case and no
            run: an empty link or a dash would be a question a brownfield reviewer has to answer
            for themselves. Both links open in a new tab, matching how this app links out of a
            task in hand — the reviewer holds a 15-minute claim on this item and a place in a
            long queue, and neither should be spent to glance at a test case. */}
        {item.work_item_id && (
          <span className="meta-item">
            Found by{" "}
            <Link to={`/work-items/${item.work_item_id}`} target="_blank" rel="noreferrer">
              <strong>{item.work_item_label}</strong>
              {item.work_item_title ? ` — ${item.work_item_title}` : ""}
            </Link>
          </span>
        )}
        {item.source_run && (
          <span className="meta-item">
            <Link to={`/runs/${item.source_run}`} target="_blank" rel="noreferrer">
              View run
            </Link>
          </span>
        )}
        <span className="meta-item">
          If confirmed{" "}
          <Badge variant={SEVERITY_BADGE[item.severity_if_confirmed] ?? "neutral"}>
            {item.severity_if_confirmed}
          </Badge>
        </span>
      </div>

      {!item.stable_selector && (
        <Banner variant="warning" title="This element has a weak handle">
          The capture had no stable selector for it, so this finding is identified by where it
          sat on the page. Re-ordering the page will record it again as a new finding.
        </Banner>
      )}

      <Capture projectId={projectId} item={item} />

      {/* **Two different reasons land an element here, and they need different sentences.**
          An `uncertain` is "a check looked and could not decide". A pass or a fail whose
          confidence did not clear this check's bar is the opposite: the check DID reach an
          answer, and the platform declined to act on it alone.

          Until this, both said "The check gave …" with the verdict label pasted in, so a
          low-confidence pass read "The check gave not sure · 75%" — broken English that also
          hid the one fact a reviewer needs, which is that the check said the element was fine
          and how sure it was. On 31 August four of nineteen items in the queue were that shape,
          all of them passes at 75–80%, all of them described as though nothing had been decided. */}
      {item.verdict === "uncertain" || item.confidence == null ? (
        <Banner variant="warning" title="The check gave no verdict">
          So the platform did not act on it either way. It is not counted as a failure and it is
          not counted as a pass.
        </Banner>
      ) : (
        <Banner
          variant="warning"
          title={`The check said this ${item.verdict === "pass" ? "is fine" : "fails"}, and was ${Math.round(item.confidence * 100)}% sure`}
        >
          That is under the confidence this check needs before the platform will act on its own,
          so it is asking you instead. It is not counted as a failure and it is not counted as a
          pass until you decide.
        </Banner>
      )}

      <h3 className="t-h3" style={{ marginTop: "var(--space-5)" }}>
        What the check saw
      </h3>
      <p className="t-sm u-body">{item.evidence || "Nothing was recorded."}</p>

      {item.suggested_fix && (
        <>
          <h3 className="t-h3" style={{ marginTop: "var(--space-4)" }}>
            What it would ask for
          </h3>
          <p className="t-sm u-body">{item.suggested_fix}</p>
        </>
      )}

      {readOnly && (
        <Banner variant="info" title="You are not the accessibility reviewer">
          Anyone can read this. Only the QA Lead on this project can answer it — everything above
          is what they will be looking at.
        </Banner>
      )}

      {lockedOut && !readOnly && (
        <Banner variant="warning" title="Someone else is already on this one">
          {item.locked_out}
        </Banner>
      )}

      {!readOnly && !lockedOut && (
        <>
          <label className="field" style={{ marginTop: "var(--space-5)" }}>
            <span className="field__label" id={`note-${item.id}`}>
              Your note <span className="u-muted">(optional — required when you reject)</span>
            </span>
            <Textarea
              aria-labelledby={`note-${item.id}`}
              placeholder="Why is this a real problem, or why is it fine?"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>

          {decide.isError && (
            <Banner variant="danger" title="The decision could not be saved">
              {writeErrorSentence(decide.error)} Nothing was changed — your note is still here.
            </Banner>
          )}

          <div className="gate-panel__actions" style={{ marginTop: "var(--space-4)" }}>
            <Button
              variant="primary"
              disabled={decide.isPending}
              onClick={() =>
                decide
                  .mutateAsync({ findingId: item.id, decision: "confirm", note })
                  .then((r) => setDone({ decision: "confirm", opens_defect: r.opens_defect }))
                  .catch(() => undefined)
              }
            >
              Yes — this is a real problem
            </Button>
            <Button
              variant="secondary"
              disabled={decide.isPending}
              onClick={() =>
                decide
                  .mutateAsync({ findingId: item.id, decision: "reject", note })
                  .then(() => setDone({ decision: "reject", opens_defect: false }))
                  .catch(() => undefined)
              }
            >
              No — this is fine
            </Button>
            <span className="u-spacer" />
            <Button variant="ghost" onClick={onDecided}>
              Skip for now
            </Button>
          </div>
          <span className="gate-reassure">
            Recorded against your name and the WCAG criterion. Confirming opens a defect;
            rejecting closes the finding. Either way it stops appearing here.
          </span>
        </>
      )}
    </Panel>
  );
}

export function A11yReview() {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const queue = useA11yReviewQueue(projectId);
  // N2: `?finding=<id>` opens THAT finding. Note what opening one does — `ItemPanel` CLAIMS the
  // finding server-side for 15 minutes — so landing on the wrong one is not a cosmetic mistake:
  // it takes another reviewer's item out of the queue. That is also why a stale link must select
  // NOTHING rather than fall back to `items[0]`.
  const [selectedId, setSelectedId, pinnedFromUrl] = useParamState("finding");

  const items = queue.data?.queue ?? [];
  const selected = items.find((i) => i.id === selectedId) ?? (pinnedFromUrl ? undefined : items[0]);
  const staleLink = pinnedFromUrl && Boolean(selectedId) && !selected && !queue.isLoading;

  if (queue.isLoading) {
    return (
      <main className="canvas-pad">
        <A11yTabs active="queue" />
        <Panel title="Loading the review queue">
          <Skeleton kind="title" />
          <Skeleton />
          <Skeleton kind="block" />
        </Panel>
      </main>
    );
  }

  // A failure is not an empty queue. "Nothing is waiting on you" over a 500 is the most
  // reassuring sentence this product can say and the least true.
  if (queue.isError) {
    return (
      <main className="canvas-pad">
        <A11yTabs active="queue" />
        <LoadFailed
          what="The review queue"
          error={queue.error}
          onRetry={() => void queue.refetch()}
        />
      </main>
    );
  }

  return (
    <main className="canvas-pad">
      <A11yTabs active="queue" />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Accessibility review</h1>
          <p className="page-head__sub">
            The checks that could not settle an element, waiting on a person. Your answer becomes
            the platform's answer.
          </p>
        </div>
      </div>

      {items.length === 0 ? (
        <Panel>
          {/* TWO empty states, not one. D-A11Y-93 says an empty queue tells you nothing about
              how accessible the application is — and the original single sentence went further
              than that, telling a project where NOTHING had ever run that "every check so far
              was sure enough to answer on its own". Vacuously true, and read as reassurance by
              the one reader who most needs pointing at the starting line: this is the screen
              the sidebar used to land on. */}
          {queue.data?.ever_checked === false ? (
            <EmptyState
              title="Nothing has been checked yet"
              text="No accessibility check has ever run on this project, so there is nothing for anyone to answer — and nothing here says whether the application is accessible. Register the pages of the application and run a first audit to find out."
              action={
                <Link to="/a11y/pages" className="btn btn--primary">
                  Go to Pages &amp; audit
                </Link>
              }
            />
          ) : (
            <EmptyState
              title="Nothing is waiting on you"
              text="An empty queue means every check so far was sure enough to answer on its own — not that no problems were found. The accessibility report is where the findings are."
            />
          )}
        </Panel>
      ) : (
        <div className="grid grid--console">
          {staleLink && (
            <Banner variant="info" title="That finding is not in your queue">
              It may already have been reviewed, or claimed by someone else. Nothing is open, so
              no decision can land on the wrong finding — pick one from the list.
            </Banner>
          )}
          <Panel title="Waiting on you" flush>
            {items.map((item) => (
              <QueueRow
                key={item.id}
                item={item}
                selected={selected?.id === item.id}
                onSelect={() => setSelectedId(item.id)}
              />
            ))}
          </Panel>
          {selected && (
            <ItemPanel
              key={selected.id}
              projectId={projectId as string}
              findingId={selected.id}
              onDecided={() => {
                // Clearing the selection also clears the "pinned from URL" state, so the next
                // item is picked normally rather than the deep link re-opening the one just
                // decided.
                setSelectedId("");
                queue.refetch();
              }}
            />
          )}
        </div>
      )}
    </main>
  );
}
