import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, Button, Card, CardBody, Chip, ConnStatus, Spinner } from "../../components/ui";

// S-24 view states: nothing-done (resume=Ideation) · in-progress (extracting/
// indexing) · gap-ready (resume=Architecture).
export type OnboardingView = "nothing-done" | "in-progress" | "gap-ready";

function Vstep({
  num,
  title,
  desc,
  state,
  children,
}: {
  num: string;
  title: string;
  desc: string;
  state?: "done" | "active" | "running";
  children?: ReactNode;
}) {
  return (
    <div className={`vstep${state ? ` vstep--${state}` : ""}`} style={{ paddingBottom: children ? undefined : 0 }}>
      <span className="vstep__num">{state === "done" ? "✓" : num}</span>
      <div className="vstep__body">
        <div className="vstep__title">{title}</div>
        <div className="vstep__desc">{desc}</div>
        {children}
      </div>
    </div>
  );
}

export function OnboardingHub({ forceView }: { forceView?: OnboardingView }) {
  const { selectedProject } = useAuth();
  const projectName = selectedProject?.project_name ?? "Legacy Billing";
  const view: OnboardingView = forceView ?? "nothing-done";

  return (
    <div className="canvas-pad" style={{ maxWidth: "920px" }}>
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Onboarding — {projectName}</h1>
          <p className="page-head__sub">
            Brownfield project. Let's assess what already exists, then resume the lifecycle at the
            right phase. We store analysis + pointers — never your source.
          </p>
        </div>
        <Badge variant="navy" dot={false}>
          Brownfield
        </Badge>
      </div>

      <Card>
        <CardBody>
          {view === "nothing-done" && (
            <>
              <Vstep num="1" title="Upload resources" desc="Drag in existing specs, PRDs, designs (.docx · .pdf · .xlsx)." state="active">
                <div className="dropzone" style={{ marginTop: "var(--space-3)" }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                    <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />
                  </svg>
                  <div className="t-body u-strong">Drag & drop documents</div>
                  <div className="t-sm u-muted">
                    or <Link to="/onboarding/documents">browse</Link>
                  </div>
                </div>
              </Vstep>
              <Vstep num="2" title="Register existing tools" desc="Link existing Confluence / Jira — register, don't recreate." />
              <Vstep num="3" title="Index code" desc="Point at a repo; built-in code intelligence indexes it." />
              <Vstep num="4" title="Gap report" desc="What exists, what's missing, and where to resume." />
              <Vstep num="5" title="Resume" desc="Trigger the recommended phase and hand into the normal pipeline." />
            </>
          )}

          {view === "in-progress" && (
            <>
              <Vstep num="1" title="Upload resources" desc="3 documents uploaded." state="done">
                <div className="u-row u-wrap" style={{ marginTop: "var(--space-2)" }}>
                  <Chip variant="done">Billing-Spec-v4.docx · extracted</Chip>
                  <Chip variant="done">NFRs.xlsx · extracted</Chip>
                  <Chip variant="running">Vision.pdf · extracting…</Chip>
                </div>
              </Vstep>
              <Vstep
                num="2"
                title="Register existing tools"
                desc="Confluence space BILL and Jira project BILL linked — found 32 existing Jira issues, linked (no duplicates created)."
                state="done"
              />
              <Vstep num="3" title="Index code" desc="Indexing acme/legacy-billing…" state="running">
                <ConnStatus state="waiting">
                  <Spinner /> Indexing 1,284 files… 64%
                </ConnStatus>
              </Vstep>
              <Vstep num="4" title="Gap report" desc="Runs once indexing completes." />
              <Vstep num="5" title="Resume" desc="Available after the gap report." />
            </>
          )}

          {view === "gap-ready" && (
            <>
              <Vstep num="1" title="Upload resources" desc="3 documents adopted as draft artifacts." state="done" />
              <Vstep num="2" title="Register existing tools" desc="32 Jira issues linked." state="done" />
              <Vstep num="3" title="Index code" desc="1,284 files indexed." state="done" />
              <Vstep num="4" title="Gap report" desc="Ideation ✓ · Requirements ✓ · PRD ~Partial · Architecture ✗ missing." state="done">
                <Card attention>
                  <CardBody style={{ maxWidth: "520px" }}>
                    <span className="gate-panel__role">Recommended resume point</span>
                    <h3 className="t-h3">Resume at: Architecture</h3>
                    <p className="t-sm u-body">
                      Requirements are covered by your uploaded spec; the architecture phase has no
                      evidence yet.
                    </p>
                    <div className="gate-panel__actions">
                      <Link to="/onboarding/gap-report" className="btn btn--secondary">
                        View full gap report
                      </Link>
                    </div>
                  </CardBody>
                </Card>
              </Vstep>
              <Vstep num="5" title="Resume" desc="Trigger Architecture on a work item to enter the pipeline." state="active">
                <div className="gate-panel__actions" style={{ marginTop: "var(--space-3)" }}>
                  <Button variant="primary">Resume at Architecture</Button>
                  <Button variant="ghost">Re-run gap report</Button>
                </div>
              </Vstep>
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
