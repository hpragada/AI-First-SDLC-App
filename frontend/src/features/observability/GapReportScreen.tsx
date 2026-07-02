import { useAuth } from "../../auth/AuthContext";
import { Assess, Banner, Breadcrumb, Button, Card, CardBody, Panel, Spinner, Table } from "../../components/ui";
import { PLANNING_PHASES } from "../../types";
import { useGapReport, useRunGapReport } from "./hooks";

// S-26 view states: partial (resume=Architecture, main sample) · empty
// (resume=Ideation) · mature (resume=Task Breakdown).
export type GapReportView = "partial" | "empty" | "mature";

const ASSESS_LABEL: Record<"complete" | "partial" | "missing", string> = {
  complete: "✓ Complete",
  partial: "~ Partial",
  missing: "✗ Missing",
};

function phaseLabel(key: string) {
  return PLANNING_PHASES.find((p) => p.key === key)?.label ?? key;
}

export function GapReportScreen({ forceView }: { forceView?: GapReportView }) {
  if (forceView) return <GapReportGallery view={forceView} />;
  return <GapReportLive />;
}

// ── Live: the real gap report for the selected project ──────────────────────
function GapReportLive() {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const gap = useGapReport(projectId);
  const runGap = useRunGapReport(projectId);

  if (gap.isLoading) {
    return (
      <div className="canvas-pad" style={{ maxWidth: "920px" }}>
        <Panel>
          <Spinner /> Loading gap report…
        </Panel>
      </div>
    );
  }

  const data = gap.data;

  return (
    <div className="canvas-pad" style={{ maxWidth: "920px" }}>
      <Breadcrumb items={[{ label: "Onboarding", href: "/onboarding" }, "Gap report"]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Gap report — {selectedProject?.project_name}</h1>
          <p className="page-head__sub">
            What exists, what's missing, and the recommended phase to resume at. Re-run after each
            upload to watch the resume point move.
          </p>
        </div>
        <Button variant="secondary" onClick={() => runGap.mutate()} disabled={runGap.isPending}>
          {runGap.isPending ? <Spinner /> : "Re-run gap report"}
        </Button>
      </div>

      {runGap.isError && (
        <Banner variant="danger" title="Couldn't run the gap report">
          {runGap.error instanceof Error ? runGap.error.message : "Unknown error"}
        </Banner>
      )}

      {!data || data.phases.length === 0 ? (
        <Panel>
          <p className="t-sm u-muted">
            No gap report yet — click <strong>Re-run gap report</strong> to assess this project.
          </p>
        </Panel>
      ) : (
        <div className="grid grid--detail">
          <Panel flush title="Lifecycle assessment">
            <Table
              headers={["Phase", "Assessment", "Evidence"]}
              rows={data.phases.map((row) => ({
                cells: [
                  <span className="table__primary" key="p">
                    {phaseLabel(row.phase)}
                  </span>,
                  <Assess state={row.assessment} key="a">
                    {ASSESS_LABEL[row.assessment]}
                  </Assess>,
                  row.phase === data.resume_phase ? <strong key="e">{row.evidence}</strong> : row.evidence,
                ],
                className: row.phase === data.resume_phase ? "row--resume" : undefined,
              }))}
            />
          </Panel>

          <div className="u-stack">
            <Card attention>
              <CardBody>
                <span className="gate-panel__role">Recommended resume point</span>
                <h3 className="t-h3">Resume at: {phaseLabel(data.resume_phase)}</h3>
                <div className="gate-panel__actions">
                  <a href="/runs" className="btn btn--primary">
                    Go to Phases &amp; Runs
                  </a>
                </div>
              </CardBody>
            </Card>
            {data.blocking.length > 0 && (
              <Card>
                <CardBody>
                  <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                    Blocking gaps
                  </h3>
                  <ul className="u-stack" style={{ ["--space-4" as string]: "8px" }}>
                    {data.blocking.map((b) => (
                      <li className="u-row-tight" key={b}>
                        <Assess state="missing">✗</Assess>
                        <span className="t-sm">{phaseLabel(b)}</span>
                      </li>
                    ))}
                  </ul>
                </CardBody>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
interface Row {
  phase: string;
  assessment: "complete" | "partial" | "missing";
  evidence: string;
  resume?: boolean;
}

const ROWS: Record<GapReportView, Row[]> = {
  partial: [
    { phase: "Ideation", assessment: "complete", evidence: "Vision.pdf (adopted)" },
    { phase: "Requirements", assessment: "complete", evidence: "Billing-Spec-v4.docx" },
    { phase: "PRD", assessment: "partial", evidence: "Draft only — ungated, missing NFR sign-off" },
    { phase: "Architecture", assessment: "missing", evidence: "Resume here — no architecture evidence", resume: true },
    { phase: "UX Design", assessment: "missing", evidence: "—" },
    { phase: "Task Breakdown", assessment: "missing", evidence: "—" },
  ],
  empty: [
    { phase: "Ideation", assessment: "missing", evidence: "Resume here — start from scratch", resume: true },
    { phase: "Requirements", assessment: "missing", evidence: "—" },
    { phase: "PRD", assessment: "missing", evidence: "—" },
    { phase: "Architecture", assessment: "missing", evidence: "—" },
  ],
  mature: [
    { phase: "Ideation", assessment: "complete", evidence: "Vision.pdf" },
    { phase: "Requirements", assessment: "complete", evidence: "Billing-Spec-v4.docx" },
    { phase: "PRD", assessment: "complete", evidence: "Confluence BILL-204" },
    { phase: "Architecture", assessment: "complete", evidence: "Indexed code + ADRs" },
    { phase: "Task Breakdown", assessment: "partial", evidence: "Resume here — backlog not generated", resume: true },
  ],
};

const RESUME_COPY: Record<GapReportView, { phase: string; body: string; cta: string }> = {
  partial: {
    phase: "Architecture",
    body: "Requirements are covered by your uploaded spec; architecture has no evidence yet.",
    cta: "Resume at Architecture",
  },
  empty: {
    phase: "Ideation",
    body: "Upload docs or index code to move the resume point forward.",
    cta: "Upload resources",
  },
  mature: {
    phase: "Task Breakdown",
    body: "Plan tier is well-covered — fan out into task work items.",
    cta: "Resume at Task Breakdown",
  },
};

function GapReportGallery({ view }: { view: GapReportView }) {
  const rows = ROWS[view];
  const resume = RESUME_COPY[view];

  return (
    <div className="canvas-pad" style={{ maxWidth: "920px" }}>
      <Breadcrumb items={[{ label: "Onboarding", href: "/onboarding" }, "Gap report"]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Gap report — Legacy Billing</h1>
          <p className="page-head__sub">
            What exists, what's missing, and the recommended phase to resume at. Re-run after each
            upload to watch the resume point move.
          </p>
        </div>
        <Button variant="secondary">Re-run gap report</Button>
      </div>

      <div className="grid grid--detail">
        <Panel flush title="Lifecycle assessment">
          <Table
            headers={["Phase", "Assessment", "Evidence"]}
            rows={rows.map((row) => ({
              cells: [
                <span className="table__primary" key="p">
                  {row.phase}
                </span>,
                <Assess state={row.assessment} key="a">
                  {ASSESS_LABEL[row.assessment]}
                </Assess>,
                row.resume ? <strong key="e">{row.evidence}</strong> : row.evidence,
              ],
              className: row.resume ? "row--resume" : undefined,
            }))}
          />
        </Panel>

        {view === "partial" ? (
          <div className="u-stack">
            <Card attention>
              <CardBody>
                <span className="gate-panel__role">Recommended resume point</span>
                <h3 className="t-h3">Resume at: {resume.phase}</h3>
                <p className="t-sm u-body">{resume.body}</p>
                <div className="gate-panel__actions">
                  <Button variant="primary">{resume.cta}</Button>
                </div>
              </CardBody>
            </Card>
            <Card>
              <CardBody>
                <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                  Blocking gaps
                </h3>
                <ul className="u-stack" style={{ ["--space-4" as string]: "8px" }}>
                  <li className="u-row-tight">
                    <Assess state="missing">✗</Assess>
                    <span className="t-sm">No architecture artifact for the ledger reconciliation flow.</span>
                  </li>
                  <li className="u-row-tight">
                    <Assess state="partial">~</Assess>
                    <span className="t-sm">PRD not gate-approved — NFR sign-off missing.</span>
                  </li>
                </ul>
              </CardBody>
            </Card>
          </div>
        ) : (
          <Card attention>
            <CardBody>
              <span className="gate-panel__role">Recommended resume point</span>
              <h3 className="t-h3">Resume at: {resume.phase}</h3>
              <p className="t-sm u-body">{resume.body}</p>
              <div className="gate-panel__actions">
                <Button variant="primary">{resume.cta}</Button>
              </div>
            </CardBody>
          </Card>
        )}
      </div>
    </div>
  );
}
