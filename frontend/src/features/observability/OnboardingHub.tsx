import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, Button, Card, CardBody, Chip, ConnStatus, Panel, Spinner } from "../../components/ui";
import { useOnboardAtlassian, useOnboardingHub, useRunGapReport } from "./hooks";

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
  if (forceView) return <OnboardingHubGallery view={forceView} />;
  return <OnboardingHubLive />;
}

// ── Live: the real onboarding state for the selected project ───────────────
function OnboardingHubLive() {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const hub = useOnboardingHub(projectId);
  const onboardAtlassian = useOnboardAtlassian(projectId);
  const runGapReport = useRunGapReport(projectId);

  if (!projectId || hub.isLoading) {
    return (
      <div className="canvas-pad" style={{ maxWidth: "920px" }}>
        <Panel>
          <Spinner /> Loading onboarding status…
        </Panel>
      </div>
    );
  }

  const data = hub.data;
  if (!data) {
    return (
      <div className="canvas-pad" style={{ maxWidth: "920px" }}>
        <Panel>Couldn't load onboarding status.</Panel>
      </div>
    );
  }

  const uploadDone = data.upload.length > 0 && data.upload.every((d) => d.status === "extracted" || d.status === "adopted");
  const registerDone = data.register.docstore_connected || data.register.tasktracker_connected;
  const indexDone = data.index.status === "indexed";

  return (
    <div className="canvas-pad" style={{ maxWidth: "920px" }}>
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Onboarding — {selectedProject?.project_name}</h1>
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
          <Vstep
            num="1"
            title="Upload resources"
            desc={
              data.upload.length === 0
                ? "Drag in existing specs, PRDs, designs (.docx · .pdf · .xlsx)."
                : `${data.upload.length} document${data.upload.length === 1 ? "" : "s"} uploaded.`
            }
            state={uploadDone ? "done" : data.upload.length > 0 ? "running" : "active"}
          >
            {data.upload.length === 0 ? (
              <div className="dropzone" style={{ marginTop: "var(--space-3)" }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                  <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />
                </svg>
                <div className="t-body u-strong">Drag & drop documents</div>
                <div className="t-sm u-muted">
                  or <Link to="/onboarding/documents">browse</Link>
                </div>
              </div>
            ) : (
              <div className="u-row u-wrap" style={{ marginTop: "var(--space-2)" }}>
                {data.upload.map((doc) => (
                  <Chip key={doc.id} variant={doc.status === "extracting" ? "running" : doc.status === "failed" ? undefined : "done"}>
                    {doc.filename} · {doc.status}
                  </Chip>
                ))}
                <Link to="/onboarding/documents" className="t-sm">
                  Manage documents ↗
                </Link>
              </div>
            )}
          </Vstep>

          <Vstep
            num="2"
            title="Register existing tools"
            desc={
              registerDone
                ? `${data.register.docstore_connected ? "Confluence" : ""}${
                    data.register.docstore_connected && data.register.tasktracker_connected ? " + " : ""
                  }${data.register.tasktracker_connected ? "Jira" : ""} — ${data.register.pages_registered} pages, ${data.register.issues_registered} issues registered.`
                : "Link existing Confluence / Jira — register, don't recreate."
            }
            state={registerDone ? "done" : undefined}
          >
            {!registerDone && (
              <div className="gate-panel__actions" style={{ marginTop: "var(--space-2)" }}>
                <Button variant="secondary" onClick={() => onboardAtlassian.mutate()} disabled={onboardAtlassian.isPending}>
                  {onboardAtlassian.isPending ? <Spinner /> : "Register Confluence & Jira"}
                </Button>
              </div>
            )}
            {onboardAtlassian.isError && (
              <p className="t-sm" style={{ color: "var(--danger)" }}>
                {onboardAtlassian.error instanceof Error ? onboardAtlassian.error.message : "Registration failed — no connector configured for this tenant?"}
              </p>
            )}
          </Vstep>

          <Vstep
            num="3"
            title="Index code"
            desc={
              indexDone
                ? "Code intelligence indexed."
                : "Point your companion at a repo clone — the built-in code-intel indexes it (companion CLI; see Section 3 of the guide)."
            }
            state={indexDone ? "done" : undefined}
          />

          <Vstep
            num="4"
            title="Gap report"
            desc={data.gap.ready ? `Ready — resume at ${data.gap.resume_phase}.` : "What exists, what's missing, and where to resume."}
            state={data.gap.ready ? "done" : undefined}
          >
            {data.gap.ready ? (
              <Card attention>
                <CardBody style={{ maxWidth: "520px" }}>
                  <span className="gate-panel__role">Recommended resume point</span>
                  <h3 className="t-h3">Resume at: {data.gap.resume_phase}</h3>
                  <div className="gate-panel__actions">
                    <Link to="/onboarding/gap-report" className="btn btn--secondary">
                      View full gap report
                    </Link>
                  </div>
                </CardBody>
              </Card>
            ) : (
              <div className="gate-panel__actions" style={{ marginTop: "var(--space-2)" }}>
                <Button variant="secondary" onClick={() => runGapReport.mutate()} disabled={runGapReport.isPending}>
                  {runGapReport.isPending ? <Spinner /> : "Run gap report"}
                </Button>
              </div>
            )}
          </Vstep>

          <Vstep
            num="5"
            title="Resume"
            desc={data.gap.ready ? `Trigger ${data.gap.resume_phase} on a work item to enter the pipeline.` : "Available after the gap report."}
            state={data.gap.ready ? "active" : undefined}
          >
            {data.gap.ready && (
              <div className="gate-panel__actions" style={{ marginTop: "var(--space-3)" }}>
                <Link to="/runs" className="btn btn--primary">
                  Go to Phases &amp; Runs
                </Link>
              </div>
            )}
          </Vstep>
        </CardBody>
      </Card>
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
function OnboardingHubGallery({ view }: { view: OnboardingView }) {
  return (
    <div className="canvas-pad" style={{ maxWidth: "920px" }}>
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Onboarding — Legacy Billing</h1>
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
