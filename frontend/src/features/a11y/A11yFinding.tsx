// S-39 — one accessibility finding, opened to be READ.
//
// **Why this screen exists.** Every AI finding an audit produces opens with "Screenshot
// shows…", and the team could not find that screenshot anywhere. The pictures were being kept
// and an endpoint was already serving them; the only screen that drew one was the review
// console, which by definition holds nothing except items awaiting a person. On the audit that
// prompted this, all twenty-six findings were confirmed failures — so the evidence existed,
// was reachable, and had nowhere to be looked at.
//
// **It takes no review claim, and that is the one genuinely new thing here.** Opening an item
// in the console is also what claims it, which is right for a reviewer working a queue and
// wrong for anyone following a link out of a report: a failure nobody is reviewing must not
// acquire a reviewer's name because somebody looked at it. Same evidence, same picture, no
// side effect — `GET a11y-finding/<id>` rather than `GET a11y-review/<id>`.
import { Link, useParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, Banner, Panel, Skeleton } from "../../components/ui";
import type { A11yFindingDetail } from "../../types";
import { A11yTabs } from "./A11yTabs";
import { Capture } from "./Capture";
import { LoadFailed } from "./LoadFailed";
import { useA11yFinding } from "./hooks";

const SEVERITY_BADGE: Record<string, "failed" | "waiting" | "neutral"> = {
  critical: "failed",
  high: "failed",
  medium: "waiting",
  low: "neutral",
};

function when(value: string | null | undefined): string {
  if (!value) return "";
  return new Date(value).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// What the PLATFORM decided, which is not what the AI said. A reader arriving from a report is
// looking at a failure; a reader arriving from the queue is looking at a question. The screen
// has to open by saying which, because the rest of it looks identical either way.
function OutcomeBanner({ item }: { item: A11yFindingDetail }) {
  if (item.status === "resolved") {
    return (
      <Banner variant="success" title="This one is no longer found">
        A later check did not see it again, so it was closed. Everything below is what was
        recorded when it was last seen.
      </Banner>
    );
  }
  if (item.outcome === "needs_review") {
    return (
      <Banner variant="warning" title="This one is still waiting on a person">
        The check could not settle it, so the platform has not counted it as a failure or as a
        pass.{" "}
        {item.can_review ? (
          <Link to="/a11y">Answer it in the review queue</Link>
        ) : (
          "Only the accessibility reviewer on this project can answer it."
        )}
      </Banner>
    );
  }
  if (item.adjudication === "confirmed") {
    return (
      <Banner variant="danger" title="A person confirmed this is a real problem">
        It is counted as a failure, and it is what the project's gates are held against.
      </Banner>
    );
  }
  return (
    <Banner variant="danger" title="This is recorded as a failure">
      It counts against this project's accessibility standing until a later check no longer
      finds it.
    </Banner>
  );
}

export function A11yFinding() {
  const { findingId } = useParams();
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const finding = useA11yFinding(projectId, findingId);

  if (finding.isLoading) {
    return (
      <main className="canvas-pad">
        <A11yTabs active="queue" />
        <Panel title="Loading the finding">
          <Skeleton kind="title" />
          <Skeleton />
          <Skeleton kind="block" />
        </Panel>
      </main>
    );
  }

  // A finding that cannot be loaded is not a finding that is fine. Reports link here, and a
  // dead link out of a conformance document has to say it is dead.
  if (finding.isError || !finding.data) {
    return (
      <main className="canvas-pad">
        <A11yTabs active="queue" />
        <LoadFailed
          what="This finding"
          error={finding.error}
          onRetry={() => void finding.refetch()}
        />
      </main>
    );
  }

  const item = finding.data;

  return (
    <main className="canvas-pad">
      <A11yTabs active="queue" />

      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/a11y/pages">Pages &amp; audit</Link>
        <span className="sep">/</span>
        <span className="here t-mono">{item.selector}</span>
      </nav>

      <Panel
        title={`${item.criterion} ${item.criterion_handle}`.trim()}
        actions={
          <>
            {item.wcag_level && (
              <Badge variant="outline" dot={false}>
                Level {item.wcag_level}
              </Badge>
            )}
            <Badge variant={SEVERITY_BADGE[item.severity_if_confirmed] ?? "neutral"}>
              {item.severity_if_confirmed}
            </Badge>
          </>
        }
      >
        <div className="meta-row">
          <span className="meta-item">
            Page <strong>{item.route}</strong>
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
            Confidence{" "}
            <strong>
              {item.confidence == null ? "measured" : `${Math.round(item.confidence * 100)}%`}
            </strong>
          </span>
          {/* Which pass took this picture, and when. Absent on greenfield, where the capture
              belongs to a build's own run and there is no audit — an empty link there would be
              a question the reader has to answer for themselves. */}
          {item.captured_by && (
            <span className="meta-item">
              Found by <strong>{item.captured_by.label}</strong>
              {item.captured_by.finished_at ? ` — ${when(item.captured_by.finished_at)}` : ""}
              {`, ${item.captured_by.opened} of ${item.captured_by.asked} page(s)`}
            </span>
          )}
          {item.url && (
            <span className="meta-item">
              <a href={item.url} target="_blank" rel="noreferrer">
                Open the page
              </a>
            </span>
          )}
          {item.work_item_id && (
            <span className="meta-item">
              <Link to={`/work-items/${item.work_item_id}`} target="_blank" rel="noreferrer">
                <strong>{item.work_item_label}</strong>
                {item.work_item_title ? ` — ${item.work_item_title}` : ""}
              </Link>
            </span>
          )}
        </div>

        <OutcomeBanner item={item} />

        {!item.stable_selector && (
          <Banner variant="warning" title="This element has a weak handle">
            The capture had no stable selector for it, so this finding is identified by where it
            sat on the page. Re-ordering the page will record it again as a new finding.
          </Banner>
        )}

        <Capture projectId={projectId as string} item={item} />

        <h3 className="t-h3" style={{ marginTop: "var(--space-5)" }}>
          What the check saw
        </h3>
        <p className="t-sm u-body">{item.evidence || "Nothing was recorded."}</p>

        {item.suggested_fix && (
          <>
            <h3 className="t-h3" style={{ marginTop: "var(--space-4)" }}>
              What to change
            </h3>
            <p className="t-sm u-body">{item.suggested_fix}</p>
          </>
        )}

        {item.note && (
          <>
            <h3 className="t-h3" style={{ marginTop: "var(--space-4)" }}>
              What the reviewer said
            </h3>
            <p className="t-sm u-body">{item.note}</p>
          </>
        )}
      </Panel>
    </main>
  );
}
