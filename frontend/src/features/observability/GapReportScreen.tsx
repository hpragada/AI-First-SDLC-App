import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Assess, Breadcrumb, Button, Card, CardBody, Panel, Spinner, Table, WriteError } from "../../components/ui";
import type { GapReport } from "../../types";
import { useGapReport, useRunGapReport } from "./hooks";

// S-26 view states: partial (resume=Architecture, main sample) · empty
// (resume=Ideation) · mature (resume=Task Breakdown).
export type GapReportView = "partial" | "empty" | "mature";

const ASSESS_LABEL: Record<"complete" | "partial" | "missing", string> = {
  complete: "✓ Complete",
  partial: "~ Partial",
  missing: "✗ Missing",
};

// A phase key with no human label — the backend now serves `label` on every phase and
// `resume_label` alongside the resume key (S5-7), so this only catches an older cached payload.
// The previous fallback looked keys up in PLANNING_PHASES, which is keyed `01_ideation` while the
// API emits the bare `ideation`: every lookup missed and the screen rendered raw slugs.
function humanize(key: string) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function labelOf(data: GapReport, key: string) {
  return data.phases.find((p) => p.phase === key)?.label ?? humanize(key);
}

// What actually resolves a blocker, per phase (S5-19). Two phases are NOT resolved by running a
// phase agent — you cannot author your way out of a missing codebase or an absent review history
// — so pointing them at "Phases & Runs" was wrong advice, not just a missing button.
// Keyed by phase, then by whether code intelligence has already run — telling someone to index a
// repo that is already indexed is the wrong-but-confident advice this audit was about.
const BLOCKER_ACTION: Record<string, (indexed: boolean) => { text: string; to: string; cta: string }> = {
  implementation: (indexed) => indexed
    ? { text: "Code intelligence ran but found no codebase for this project — check the linked repository is the right one.", to: "/repositories", cta: "Check repositories" }
    : { text: "The codebase is the evidence — index it so the platform can measure it.", to: "/onboarding", cta: "Go to Index code" },
  code_review: (indexed) => indexed
    ? { text: "No review evidence in the indexed history. If reviews happen outside this repository, register that record.", to: "/runs", cta: "Run Code Review" }
    : { text: "Evidenced by merge history and required checks — index the repository first.", to: "/onboarding", cta: "Go to Index code" },
  task_breakdown: () =>
    ({ text: "No backlog yet — run Task Breakdown, or import an existing backlog.", to: "/runs", cta: "Run Task Breakdown" }),
};

// A phase AFTER the resume point that has no evidence hasn't been reached yet — it is not a gap
// the team failed to fill (S5-28). Showing six identical "✗ Missing" rows to a team that has
// legitimately only finished UX Design reads as six failures. Blockers sit at or before the
// resume point; everything past it is simply ahead of them.
function isAhead(data: GapReport, index: number) {
  const resumeIdx = data.phases.findIndex((p) => p.phase === data.resume_phase);
  return resumeIdx !== -1 && index > resumeIdx;
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
        <WriteError title="Couldn't run the gap report" detail={runGap.error} />
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
              rows={data.phases.map((row, i) => {
                const ahead = row.assessment === "missing" && isAhead(data, i);
                const n = row.evidence?.length ?? 0;
                return {
                  cells: [
                    <span className="table__primary" key="p">
                      {row.label ?? humanize(row.phase)}
                    </span>,
                    ahead ? (
                      <span className="t-sm u-muted" key="a">
                        Not started yet
                      </span>
                    ) : (
                      <Assess state={row.assessment} key="a">
                        {ASSESS_LABEL[row.assessment]}
                      </Assess>
                    ),
                    // `evidence` is a list of artifact refs, never a string — rendering it raw
                    // threw "Objects are not valid as a React child" on every real report (S5-6).
                    <span className="t-sm u-muted" key="e">
                      {n === 0 ? "—" : `${n} artifact${n === 1 ? "" : "s"}`}
                    </span>,
                  ],
                  className: row.phase === data.resume_phase ? "row--resume" : undefined,
                };
              })}
            />
          </Panel>

          <div className="u-stack">
            <Card attention>
              <CardBody>
                <span className="gate-panel__role">Recommended resume point</span>
                <h3 className="t-h3">
                  Resume at: {data.resume_label || (data.resume_phase ? labelOf(data, data.resume_phase) : "Pipeline complete")}
                </h3>
                <div className="gate-panel__actions">
                  {/* A router Link, not a raw <a>: the anchor triggered a full page reload and
                      dropped the SPA's state on the way to Phases & Runs. */}
                  <Link to="/runs" className="btn btn--primary">
                    Go to Phases &amp; Runs
                  </Link>
                  {data.gap_report_id && (
                    <Link to={`/artifacts/${data.gap_report_id}`} className="btn btn--ghost">
                      Open the report document
                    </Link>
                  )}
                </div>
                {/* How this reading was produced (S5-9) — measured code evidence, or not. */}
                <p className="t-sm u-muted" style={{ marginTop: "var(--space-2)" }}>
                  {data.intel_present
                    ? "Implementation and Code Review were assessed from measured code."
                    : "Code intelligence hasn't run, so Implementation and Code Review are reported as missing rather than judged."}
                </p>
              </CardBody>
            </Card>
            {data.blocking.length > 0 && (
              <Card>
                <CardBody>
                  <h3 className="t-h3" style={{ marginBottom: "var(--space-3)" }}>
                    Blocking gaps
                  </h3>
                  {/* Each blocker now says what resolves it and links there (S5-19). The list
                      used to be display-only while the report's own text told the reader to
                      "generate it via its phase agent" — with nothing to click. */}
                  <ul className="u-stack" style={{ ["--space-4" as string]: "8px" }}>
                    {data.blocking.map((b) => (
                      <li className="u-stack" key={b} style={{ ["--space-4" as string]: "2px" }}>
                        <span className="u-row-tight">
                          <Assess state="missing">✗</Assess>
                          <span className="t-sm">{labelOf(data, b)}</span>
                        </span>
                        {(() => {
                          const act = BLOCKER_ACTION[b]?.(Boolean(data.intel_present)) ?? {
                            text: "No evidence found — run this phase to generate it, or upload and adopt the existing source.",
                            to: "/runs",
                            cta: "Run this phase",
                          };
                          return (
                            <span className="t-sm u-muted">
                              {act.text} <Link to={act.to}>{act.cta}</Link>
                            </span>
                          );
                        })()}
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
    body: "Planning is well covered — fan out into task work items.",
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
