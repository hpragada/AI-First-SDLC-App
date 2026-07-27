import type { ReactNode } from "react";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, Button, Card, CardBody, Chip, ConnStatus, Input, Panel, Select, Spinner } from "../../components/ui";
import type { Capability, OnboardingRegister } from "../../types";
import { ConnectCapability } from "../setup/ConnectCapability";
import { useRepositories } from "../setup/hooks";
import { ADOPT_TYPES } from "./SourceDocuments";
import {
  useLinkConfluencePages,
  useOnboardAtlassian,
  useOnboardingHub,
  useRunGapReport,
  useStartCodeIntel,
} from "./hooks";

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

// ── Step 2: Register existing tools (B3-1 graceful connect + B3-4 typed Confluence linking) ──
// A per-tool state machine driven by the connection status the hub already returns:
//   not connected → inline Connect drawer (Option B — reuses ConnectCapability, no page hop);
//   connected     → Jira: "Import backlog" (bulk); Confluence: the typed "Link docs" form.
function RegisterToolsStep({ projectId, register }: { projectId: string; register: OnboardingRegister }) {
  const onboardAtlassian = useOnboardAtlassian(projectId);
  const qc = useQueryClient();
  const [connectCap, setConnectCap] = useState<Capability | null>(null);

  const registerDone = register.docstore_connected || register.tasktracker_connected;

  const onConnected = () => {
    setConnectCap(null);
    qc.invalidateQueries({ queryKey: ["onboarding", projectId] });
  };

  return (
    <Vstep
      num="2"
      title="Register existing tools"
      desc="Bring your existing Jira backlog and Confluence docs in — register, don't recreate."
      state={registerDone ? "done" : undefined}
    >
      <div className="u-stack" style={{ marginTop: "var(--space-2)", gap: "var(--space-3)" }}>
        {/* Jira — a backlog is meant to arrive whole, so it's a bulk import. */}
        <div>
          <div className="u-row" style={{ gap: "var(--space-2)", alignItems: "center" }}>
            <span className="u-strong">Jira</span>
            {register.tasktracker_connected ? <Badge variant="done">Connected</Badge> : <Badge>Not connected</Badge>}
            {register.tasktracker_connected && (
              <span className="t-sm u-muted">
                {register.issues_registered} issue{register.issues_registered === 1 ? "" : "s"} imported
              </span>
            )}
          </div>
          <div className="gate-panel__actions" style={{ marginTop: "var(--space-2)" }}>
            {register.tasktracker_connected ? (
              <Button variant="secondary" onClick={() => onboardAtlassian.mutate()} disabled={onboardAtlassian.isPending}>
                {onboardAtlassian.isPending
                  ? <Spinner />
                  : register.issues_registered > 0 ? "Re-import backlog" : "Import Jira backlog"}
              </Button>
            ) : (
              <Button variant="secondary" onClick={() => setConnectCap("tasktracker")}>Connect Jira</Button>
            )}
          </div>
        </div>

        {/* Confluence — the user provides the specific typed page links (B3-4), no space crawl. */}
        <div>
          <div className="u-row" style={{ gap: "var(--space-2)", alignItems: "center" }}>
            <span className="u-strong">Confluence</span>
            {register.docstore_connected ? <Badge variant="done">Connected</Badge> : <Badge>Not connected</Badge>}
            {register.docstore_connected && (
              <span className="t-sm u-muted">
                {register.pages_registered} page{register.pages_registered === 1 ? "" : "s"} linked
              </span>
            )}
          </div>
          {register.docstore_connected ? (
            <ConfluenceLinkForm projectId={projectId} />
          ) : (
            <div className="gate-panel__actions" style={{ marginTop: "var(--space-2)" }}>
              <Button variant="secondary" onClick={() => setConnectCap("docstore")}>Connect Confluence</Button>
            </div>
          )}
        </div>

        {/* B3-1 Option B: connect inline, without leaving onboarding. */}
        {connectCap && (
          <div style={{ marginTop: "var(--space-2)" }}>
            <ConnectCapability embedded capability={connectCap} onConnected={onConnected} />
            <Button variant="ghost" onClick={() => setConnectCap(null)}>Cancel</Button>
          </div>
        )}
      </div>
    </Vstep>
  );
}

function ConfluenceLinkForm({ projectId }: { projectId: string }) {
  const linkPages = useLinkConfluencePages(projectId);
  const [rows, setRows] = useState<{ page: string; type: string }[]>([
    { page: "", type: ADOPT_TYPES[0].value },
  ]);
  const [result, setResult] = useState<{ linked: number; errors: { page: string; error: string }[] } | null>(null);

  const setRow = (i: number, patch: Partial<{ page: string; type: string }>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const addRow = () => setRows((rs) => [...rs, { page: "", type: ADOPT_TYPES[0].value }]);
  const removeRow = (i: number) => setRows((rs) => (rs.length > 1 ? rs.filter((_, j) => j !== i) : rs));

  const submit = async () => {
    const clean = rows.filter((r) => r.page.trim());
    if (clean.length === 0) return;
    try {
      const out = await linkPages.mutateAsync(clean);
      setResult({ linked: out.linked.length, errors: out.errors });
      if (out.errors.length === 0) setRows([{ page: "", type: ADOPT_TYPES[0].value }]);
    } catch (e) {
      setResult({ linked: 0, errors: [{ page: "", error: e instanceof Error ? e.message : "Could not link pages." }] });
    }
  };

  return (
    <div className="u-stack" style={{ marginTop: "var(--space-2)" }}>
      <p className="t-sm u-muted">
        Paste the Confluence page link (or page ID) for each doc the flow needs, and pick its type.
      </p>
      {rows.map((r, i) => (
        <div key={i} className="u-row" style={{ gap: "var(--space-2)" }}>
          <Input
            placeholder="https://…/wiki/…/pages/12345  ·  or  12345"
            value={r.page}
            onChange={(e) => setRow(i, { page: e.target.value })}
            style={{ flex: 1 }}
          />
          <Select value={r.type} onChange={(e) => setRow(i, { type: e.target.value })}>
            {ADOPT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </Select>
          {rows.length > 1 && (
            <Button variant="ghost" onClick={() => removeRow(i)}>Remove</Button>
          )}
        </div>
      ))}
      <div className="u-row" style={{ gap: "var(--space-2)" }}>
        <Button variant="ghost" onClick={addRow}>＋ Add another</Button>
        <Button variant="secondary" onClick={submit} disabled={linkPages.isPending}>
          {linkPages.isPending ? <Spinner /> : "Link documents"}
        </Button>
      </div>
      {result && (
        <div className="t-sm">
          {result.linked > 0 && (
            <p style={{ color: "var(--success)" }}>
              Linked {result.linked} page{result.linked === 1 ? "" : "s"}.
            </p>
          )}
          {result.errors.map((er, i) => (
            <p key={i} style={{ color: "var(--danger)" }}>
              {er.page ? `${er.page}: ` : ""}{er.error}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Step 4: Index code (B4-1) — dispatch real code intelligence per repo ──
// The button dispatches an indexing job to the connected companion, which analyses the repo in
// a read-only worktree and reports the index back (nothing is copied off the machine). The web
// endpoint only dispatches — it can't fabricate an index (B4-2).
function IndexCodeStep({ projectId, repos, indexDone }: {
  projectId: string;
  repos: { id: string; name: string }[];
  indexDone: boolean;
}) {
  const startCodeIntel = useStartCodeIntel(projectId);
  const [dispatched, setDispatched] = useState<Record<string, boolean>>({});

  const onIndex = (repoId: string) => {
    setDispatched((d) => ({ ...d, [repoId]: true }));
    startCodeIntel.mutate(repoId);
  };

  return (
    <Vstep
      num="4"
      title="Index code"
      desc={
        indexDone
          ? "Code intelligence indexed."
          : "Analyse each repository on your connected companion — the built-in code-intel runs in a read-only worktree and reports back. Nothing is copied off your machine."
      }
      state={indexDone ? "done" : undefined}
    >
      {repos.length === 0 ? (
        <p className="t-sm u-muted" style={{ marginTop: "var(--space-2)" }}>
          Register a repository first (step 3) to index code.
        </p>
      ) : (
        <div className="u-stack" style={{ marginTop: "var(--space-2)" }}>
          {repos.map((r) => (
            <div key={r.id} className="u-row" style={{ gap: "var(--space-2)", alignItems: "center" }}>
              <span className="u-strong">{r.name}</span>
              <Button variant="secondary" onClick={() => onIndex(r.id)} disabled={startCodeIntel.isPending}>
                {dispatched[r.id] ? "Indexing dispatched…" : "Index code"}
              </Button>
            </div>
          ))}
          <p className="t-sm u-muted">
            Requires your companion online. It runs the analysis and reports back — the result
            appears here and feeds the gap report.
          </p>
        </div>
      )}
    </Vstep>
  );
}

// ── Live: the real onboarding state for the selected project ───────────────
function OnboardingHubLive() {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const hub = useOnboardingHub(projectId);
  const repos = useRepositories(projectId);
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
  const repoCount = repos.data?.length ?? 0;
  const reposDone = repoCount > 0;
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

          <RegisterToolsStep projectId={projectId} register={data.register} />

          {/* B0-3: repos must be registered before code indexing / the gap report can use them.
              This step reads the project's repositories and points you to the Repositories screen
              when none exist yet — placed before "Index code". */}
          <Vstep
            num="3"
            title="Register repositories"
            desc={
              reposDone
                ? `${repoCount} repositor${repoCount === 1 ? "y" : "ies"} registered.`
                : "Add the repositories the platform should analyse — code indexing and the gap report need at least one."
            }
            state={reposDone ? "done" : undefined}
          >
            {!reposDone && (
              <div className="gate-panel__actions" style={{ marginTop: "var(--space-2)" }}>
                <Link to="/repositories" className="btn btn--secondary">
                  Add a repository
                </Link>
              </div>
            )}
          </Vstep>

          <IndexCodeStep projectId={projectId} repos={repos.data ?? []} indexDone={indexDone} />

          <Vstep
            num="5"
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
            num="6"
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
