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

import { useAuth } from "../../auth/AuthContext";
import {
  Badge,
  Banner,
  Button,
  EmptyState,
  Panel,
  Skeleton,
  Textarea,
  cx,
} from "../../components/ui";
import type { A11yReviewItem } from "../../types";
import { useA11yCapture, useA11yReviewItem, useA11yReviewQueue, useDecideA11yFinding } from "./hooks";

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

// The capture, with the failing element ringed. Two modes because a reviewer needs both: FIT to
// judge the layout, ACTUAL to judge the pixels — contrast and focus rings are not decidable on
// a scaled-down image, and those are most of what this reviewer is deciding.
function Capture({ projectId, item }: { projectId: string; item: A11yReviewItem }) {
  const [fit, setFit] = useState(true);
  const [natural, setNatural] = useState<{ w: number; h: number } | undefined>();
  const kind: "page" | "element" = item.page_image ? "page" : "element";
  const available = item.page_image || item.element_image;
  const { url, error } = useA11yCapture(projectId, item.id, kind, available);

  if (!available || error) {
    return (
      <div className="shot shot--missing" style={{ marginTop: "var(--space-4)" }}>
        <div className="shot__stage">
          <strong>There is no picture of this one</strong>
          {/* Never a bare empty frame. A missing capture is a fact with a cause, and saying
              which cause is the difference between "we could not" and "nothing was wrong". */}
          <span className="t-sm">
            {error ?? item.capture_reason ?? "no capture was kept for this element"}
          </span>
          <span className="t-xs u-muted">
            You can still judge it from the element, the criterion and what the check saw.
          </span>
        </div>
      </div>
    );
  }

  // The box is in the page screenshot's own pixel space — the capture records
  // `getBoundingClientRect()` plus the scroll offset and the shot is full-page, so the two share
  // one coordinate system. Positioned as a PERCENTAGE of the image's natural size, which lands
  // correctly in FIT (image scaled to the panel) and in ACTUAL (1:1, scrolling) with no
  // per-mode arithmetic. Drawn only over the page: on an element crop the crop IS the element,
  // and a ring around the whole picture would say nothing.
  const marker = kind === "page" && item.box && natural;

  return (
    <div className="shot" style={{ marginTop: "var(--space-4)" }}>
      <div className={cx("shot__stage", fit && "shot__stage--fit")}>
        {url ? (
          <>
            <img
              className="shot__img"
              src={url}
              alt={`Captured screen ${item.route}`}
              onLoad={(e) =>
                setNatural({
                  w: e.currentTarget.naturalWidth,
                  h: e.currentTarget.naturalHeight,
                })
              }
            />
            {marker && (
              <span
                className="shot__marker"
                data-label={item.selector}
                style={{
                  left: `${(item.box!.x / natural!.w) * 100}%`,
                  top: `${(item.box!.y / natural!.h) * 100}%`,
                  width: `${(item.box!.width / natural!.w) * 100}%`,
                  height: `${(item.box!.height / natural!.h) * 100}%`,
                }}
              />
            )}
          </>
        ) : (
          <Skeleton kind="block" />
        )}
      </div>
      <div className="shot__bar">
        <span>{fit ? "Fit to width" : "Actual size"}</span>
        <Button variant="ghost" size="sm" onClick={() => setFit((v) => !v)}>
          {fit ? "View actual size" : "Fit to width"}
        </Button>
        <span className="u-spacer" />
        {natural && (
          <span className="shot__dims">
            {natural.w} × {natural.h}
          </span>
        )}
      </div>
    </div>
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

      <Banner variant="warning" title={`The check gave ${verdictLabel(item).toLowerCase()}`}>
        So the platform did not act on it either way. It is not counted as a failure and it is
        not counted as a pass.
      </Banner>

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
              {(decide.error as Error).message} Nothing was changed — your note is still here.
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
  const [selectedId, setSelectedId] = useState<string | undefined>();

  const items = queue.data?.queue ?? [];
  const selected = items.find((i) => i.id === selectedId) ?? items[0];

  if (queue.isLoading) {
    return (
      <main className="canvas-pad">
        <Panel title="Loading the review queue">
          <Skeleton kind="title" />
          <Skeleton />
          <Skeleton kind="block" />
        </Panel>
      </main>
    );
  }

  return (
    <main className="canvas-pad">
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
          <EmptyState
            title="Nothing is waiting on you"
            // D-A11Y-93. This screen shows only findings a check could not settle, so an empty
            // queue says NOTHING about how accessible the application is. A screen that let
            // someone believe otherwise would be the most expensive silence in the build.
            text="An empty queue means every check so far was sure enough to answer on its own — not that no problems were found. The accessibility report is where the findings are."
          />
        </Panel>
      ) : (
        <div className="grid grid--console">
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
                setSelectedId(undefined);
                queue.refetch();
              }}
            />
          )}
        </div>
      )}
    </main>
  );
}
