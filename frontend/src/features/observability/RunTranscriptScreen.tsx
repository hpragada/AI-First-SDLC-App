import { useParams } from "react-router-dom";

import { Badge, Banner, Breadcrumb, EmptyState, Panel, Table, Transcript, Turn } from "../../components/ui";
import { useRunTranscript } from "./hooks";

// S-33 view states: runs-list (no run selected) · transcript · empty.
export type TranscriptView = "runs-list" | "transcript" | "empty";

export function RunTranscriptScreen({ forceView }: { forceView?: TranscriptView }) {
  const { id } = useParams();
  const transcript = useRunTranscript(id ?? (forceView === "transcript" ? "RUN-42" : undefined));
  const view: TranscriptView = forceView ?? (id ? "transcript" : "runs-list");

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
          title={`${transcript.data?.run_id ?? "RUN-42"} · ${transcript.data?.phase ?? "Architecture"} · WI-492`}
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
