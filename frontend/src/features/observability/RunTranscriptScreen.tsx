import { Link, useParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, Banner, Breadcrumb, EmptyState, Panel, Spinner, Table, Transcript, Turn } from "../../components/ui";
import { engineLabel, runStatusLabel, runStatusTone } from "../../labels";
import { useRuns } from "../lifecycle/hooks";
import { phaseLabel } from "../lifecycle/phases";
import { useRunTranscript } from "./hooks";

// S-33 view states: runs-list (no run selected) · transcript · empty.
export type TranscriptView = "runs-list" | "transcript" | "empty";

export function RunTranscriptScreen({ forceView }: { forceView?: TranscriptView }) {
  if (forceView) return <RunTranscriptGallery view={forceView} />;
  return <RunTranscriptLive />;
}

// ── Live: the real completed-runs list, or a real run's transcript ─────────
function RunTranscriptLive() {
  const { id } = useParams();
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const runs = useRuns({ project: id ? undefined : projectId });
  const transcript = useRunTranscript(id);

  if (id) {
    if (transcript.isLoading) {
      return (
        <div className="canvas-pad">
          <Panel>
            <Spinner /> Loading transcript…
          </Panel>
        </div>
      );
    }
    if (!transcript.data) {
      return (
        <div className="canvas-pad">
          <Breadcrumb items={[{ label: "Phases & Runs", href: "/runs" }, "Transcripts"]} />
          <Panel>
            <Banner variant="danger" title="Transcript not found">
              This run doesn't exist or you don't have access to it.
            </Banner>
          </Panel>
        </div>
      );
    }
    const data = transcript.data;
    return (
      <div className="canvas-pad">
        <Breadcrumb items={[{ label: "Phases & Runs", href: "/runs" }, "Transcripts"]} />
        <div className="page-head">
          <div className="page-head__titles">
            <h1 className="t-h1">Run transcripts</h1>
            <p className="page-head__sub">
              Read-only replay of each run — agent turns, tool calls, and the Q&amp;A. Stored for
              provenance; never editable.
            </p>
          </div>
        </div>
        <Panel
          // Screen Words group 4: the title was the 36-character run id. The transcript payload
          // carries no work item, so the phase leads, with the short run reference used elsewhere.
          title={`${phaseLabel(data.phase)} run · ${data.run_id.slice(0, 8)}`}
          actions={
            <>
              <span className="meta-item">
                Engine <strong>{engineLabel(data.engine)}</strong>
              </span>
              <Badge variant="done">{data.cost ? `$${data.cost}` : "—"}</Badge>
            </>
          }
        >
          {data.turns.length === 0 ? (
            <EmptyState title="No transcript recorded" text="This run has no captured conversation yet." />
          ) : (
            <Transcript>
              {data.turns.map((t, i) => (
                <Turn role={t.role} key={i}>
                  {t.body}
                  {t.meta ? ` (${t.meta})` : ""}
                </Turn>
              ))}
            </Transcript>
          )}
          <Banner variant="info" title="">
            Read-only replay — transcripts are stored for provenance and cannot be edited.
          </Banner>
        </Panel>
      </div>
    );
  }

  const completed = (runs.data ?? []).filter((r) => r.status === "completed" || r.status === "approved");

  return (
    <div className="canvas-pad">
      <Breadcrumb items={[{ label: "Phases & Runs", href: "/runs" }, "Transcripts"]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Run transcripts</h1>
          <p className="page-head__sub">
            Read-only replay of each run — agent turns, tool calls, and the Q&amp;A. Stored for
            provenance; never editable.
          </p>
        </div>
      </div>

      {runs.isLoading ? (
        <Panel>
          <Spinner /> Loading runs…
        </Panel>
      ) : completed.length === 0 ? (
        <Panel>
          <EmptyState
            title="No transcripts yet"
            text="Once you run a phase, its full session is captured here for read-only replay."
          />
        </Panel>
      ) : (
        <Panel flush>
          <Table
            headers={["Run", "Phase", "Work item", "Status", ""]}
            rows={completed.map((r) => [
              <span className="table__id" key="r">
                {r.id.slice(0, 8)}
              </span>,
              <span className="table__primary" key="p">
                {phaseLabel(r.agent_phase ?? r.agent_key)}
              </span>,
              <span className="table__id" key="w">
                {r.work_item.slice(0, 8)}
              </span>,
              // Screen Words group 4: status words and colour from the shared map.
              <Badge variant={runStatusTone(r.status)} key="s">
                {runStatusLabel(r.status)}
              </Badge>,
              <Link to={`/transcripts/${r.id}`} className="btn btn--ghost btn--sm" key="a">
                Open transcript
              </Link>,
            ])}
          />
        </Panel>
      )}
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
function RunTranscriptGallery({ view }: { view: TranscriptView }) {
  return (
    <div className="canvas-pad">
      <Breadcrumb items={[{ label: "Phases & Runs", href: "/runs" }, "Transcripts"]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Run transcripts</h1>
          <p className="page-head__sub">
            Read-only replay of each run — agent turns, tool calls, and the Q&A. Stored for
            provenance; never editable.
          </p>
        </div>
      </div>

      {view === "empty" && (
        <Panel>
          <EmptyState
            title="No transcripts yet"
            text="Once you run a phase, its full session is captured here for read-only replay."
          />
        </Panel>
      )}

      {view === "runs-list" && (
        <Panel flush>
          <Table
            headers={["Run", "Phase", "Work item", "Status", "Turns", "Cost", ""]}
            rows={[
              [
                <span className="table__id" key="r">
                  RUN-42
                </span>,
                <span className="table__primary" key="p">
                  Architecture
                </span>,
                <span className="table__id" key="w">
                  WI-492
                </span>,
                <Badge variant="done" key="s">
                  Completed
                </Badge>,
                14,
                <span className="table__id" key="c">
                  $0.31
                </span>,
                <button className="btn btn--ghost btn--sm" key="a">
                  Open transcript
                </button>,
              ],
              [
                <span className="table__id" key="r">
                  RUN-41
                </span>,
                <span className="table__primary" key="p">
                  PRD
                </span>,
                <span className="table__id" key="w">
                  WI-492
                </span>,
                <Badge variant="done" key="s">
                  Completed
                </Badge>,
                22,
                <span className="table__id" key="c">
                  $0.18
                </span>,
                <button className="btn btn--ghost btn--sm" key="a">
                  Open transcript
                </button>,
              ],
            ]}
          />
        </Panel>
      )}

      {view === "transcript" && (
        <Panel
          title="RUN-42 · Architecture · WI-492"
          actions={
            <>
              <span className="meta-item">
                Engine <strong>Claude · local</strong>
              </span>
              <Badge variant="done">Completed · $0.31</Badge>
            </>
          }
        >
          <Transcript>
            <Turn role="agent">
              Reading the approved PRD and security rules for the webhook integration…
            </Turn>
            <Turn role="tool">
              docstore.read("PRD: Stripe Webhook Integration v1.2") → ok
            </Turn>
            <Turn role="tool">
              designsource.list(project="Payment Gateway v2") → 3 files
            </Turn>
            <Turn role="agent">I need one detail before drafting the sequence diagram.</Turn>
            <Turn role="human">
              Q: "Which Confluence space should the spec publish to?" → answered{" "}
              <strong>PAY</strong>
            </Turn>
            <Turn role="agent">
              Generating the System Sequence Diagram and validating against security rules…
            </Turn>
            <Turn role="agent">Run complete. Draft registered; awaiting Architecture gate.</Turn>
          </Transcript>
          <Banner variant="info" title="">
            Read-only replay — transcripts are stored for provenance and cannot be edited.
          </Banner>
        </Panel>
      )}
    </div>
  );
}
