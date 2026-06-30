import { Assess, Breadcrumb, Button, Card, CardBody, Panel, Table } from "../../components/ui";

// S-26 view states: partial (resume=Architecture, main sample) · empty
// (resume=Ideation) · mature (resume=Task Breakdown).
export type GapReportView = "partial" | "empty" | "mature";

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

const ASSESS_LABEL: Record<Row["assessment"], string> = {
  complete: "✓ Complete",
  partial: "~ Partial",
  missing: "✗ Missing",
};

export function GapReportScreen({ forceView }: { forceView?: GapReportView }) {
  const view: GapReportView = forceView ?? "partial";
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
