import type { ReactNode } from "react";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, Button, Card, CardBody, Chip, ConnStatus, Input, Panel, Spinner, Tooltip, WriteError, writeErrorSentence } from "../../components/ui";
import { documentStatusLabel } from "../../labels";
import type { Capability, OnboardingRegister, OnboardingRepoIndex } from "../../types";
import { useRunners } from "../identity/hooks";
import { ConnectCapability } from "../setup/ConnectCapability";
import { useRepositories } from "../setup/hooks";

import {
  useLinkConfluencePages,
  useOnboardAtlassian,
  useOnboardingHub,
  useRunGapReport,
  useStartCodeIntel,
} from "./hooks";
import { clarificationLink, gateLink } from "../../links";

// S-24 view states: nothing-done (resume=Ideation) · in-progress (extracting/
// indexing) · gap-ready (resume=Architecture).
export type OnboardingView = "nothing-done" | "in-progress" | "gap-ready";

/** What "connect your machine" means, said once.
 *
 * The old wording opened with "Some of this work runs on your own machine…" — forty-one words
 * whose subject was "some of this work", with the reason buried in the middle and a second idea
 * (what you give up by not connecting) added on the end. Users read past it.
 *
 * Now the visible line is one short sentence and the rest is a tooltip, so nobody has to read
 * the detail to get on with the step — but it is one keypress away for anyone who wants to know
 * where their files go, which is a fair question to ask of a platform.
 *
 * **These live in one place because there are four of them.** The same explanation appears on
 * the prerequisite card and on the live step, each in a connected and a not-connected state, and
 * before this they had drifted into three different sentences saying the same thing.
 */
const MACHINE_COPY = {
  // One line for both connected and not — because it states a fact about where the work happens,
  // and that does not change once you connect. Two near-identical sentences is how the four
  // variants drifted apart in the first place; the heading beside it already says which state
  // you are in.
  line: "Your documents and code are read on your own computer — nothing is uploaded.",
  offline: "Start your companion again to carry on reading your documents on your computer.",
  detail:
    "Connecting lets the platform read the diagrams and screenshots inside your documents and " +
    "analyse your code — all on your machine. You can upload documents without connecting, but " +
    "the pictures inside them won't be read.",
} as const;

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
//   not connected → Connect pop-up (reuses ConnectCapability, no page hop);
//   connected     → Jira: "Import backlog" (bulk); Confluence: the "bring in docs" form.
// Exported for its own tests: what it says depends entirely on the `register` payload, and
// driving that through the whole live hub would test the plumbing rather than the labels.
export function RegisterToolsStep({
  projectId,
  register,
}: {
  projectId: string;
  register: OnboardingRegister;
}) {
  const onboardAtlassian = useOnboardAtlassian(projectId);
  const qc = useQueryClient();
  const [connectCap, setConnectCap] = useState<Capability | null>(null);

  const registerDone =
    register.docstore_connected || register.tasktracker_connected || register.designsource_connected;

  // B3-6: refresh the checklist behind the modal, but do NOT close it. Saving sets a banner that
  // says "…saved. Test the connection to verify it." — closing here destroyed that banner in the
  // same tick, so the instruction was literally unreachable and nobody ever tested a connection
  // they had just entered. The user closes it themselves once they're satisfied ("Done").
  const onConnected = () => {
    qc.invalidateQueries({ queryKey: ["onboarding", projectId] });
  };

  return (
    <Vstep
      num="2"
      title="Register existing tools"
      desc="Bring your existing backlog and documentation in — register, don't recreate."
      state={registerDone ? "done" : undefined}
    >
      <div className="u-stack" style={{ marginTop: "var(--space-2)", gap: "var(--space-3)" }}>
        {/* Task tracker — a backlog is meant to arrive whole, so it's a bulk import.
            The heading and the connect button name the CAPABILITY, not a vendor (#9): the
            pop-up behind them is "Connect Task tracker" and asks which vendor, so a button
            saying "Connect Jira" promised a choice the user had not made yet. Once something IS
            connected the vendor is known and gets named, because "Import task tracker backlog"
            would be worse for someone who plainly connected Jira. */}
        <div>
          <div className="u-row" style={{ gap: "var(--space-2)", alignItems: "center" }}>
            <span className="u-strong">{register.tasktracker_vendor ?? "Task tracker"}</span>
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
                  : register.issues_registered > 0
                    ? "Re-import backlog"
                    : `Import ${register.tasktracker_vendor ?? "task tracker"} backlog`}
              </Button>
            ) : (
              <Button variant="secondary" onClick={() => setConnectCap("tasktracker")}>Connect task tracker</Button>
            )}
          </div>
          {/* S3-15: say what the import actually covered. The old screen showed only the count it
              created, so an import that reached its cap and left issues behind in Jira looked
              identical to one that brought everything — which is exactly how 25-of-68 went
              unnoticed. Silent on the happy path; loud only when something was left behind. */}
          {onboardAtlassian.isSuccess && onboardAtlassian.data && (
            <p className="t-sm" style={{ marginTop: "var(--space-2)",
                 color: onboardAtlassian.data.truncated ? "var(--warning)" : "var(--success)" }}>
              {onboardAtlassian.data.truncated
                ? `Imported ${onboardAtlassian.data.issues_seen} of ${onboardAtlassian.data.issues_available} issues — this project is larger than one import can take. Re-import to bring in the rest.`
                : `Brought in ${onboardAtlassian.data.registered_issues.length} new issue${onboardAtlassian.data.registered_issues.length === 1 ? "" : "s"}${(onboardAtlassian.data.issues_available ?? -1) >= 0 ? ` · ${onboardAtlassian.data.issues_available} in ${register.tasktracker_vendor ?? "the tracker"}` : ""}.`}
            </p>
          )}
        </div>

        {/* Confluence — the user provides the specific typed page links (B3-4), no space crawl. */}
        <div>
          <div className="u-row" style={{ gap: "var(--space-2)", alignItems: "center" }}>
            <span className="u-strong">{register.docstore_vendor ?? "Documentation store"}</span>
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
              <Button variant="secondary" onClick={() => setConnectCap("docstore")}>Connect documentation store</Button>
            </div>
          )}
        </div>

        {/* Figma / design source — surface the already-built designsource capability so a team
            can import screens instead of uploading them as PDFs (connect only here). */}
        <div>
          <div className="u-row" style={{ gap: "var(--space-2)", alignItems: "center" }}>
            <span className="u-strong">{register.designsource_vendor ?? "Design source"}</span>
            {register.designsource_connected ? <Badge variant="done">Connected</Badge> : <Badge>Not connected</Badge>}
          </div>
          <div className="gate-panel__actions" style={{ marginTop: "var(--space-2)" }}>
            {register.designsource_connected ? (
              <span className="t-sm u-muted">
                Connected — design screens can come from {register.designsource_vendor ?? "your design tool"} instead of uploaded PDFs.
              </span>
            ) : (
              <Button variant="secondary" onClick={() => setConnectCap("designsource")}>Connect design source</Button>
            )}
          </div>
        </div>

        {/* B3-1 Option B: connect without leaving onboarding — as a pop-up (B3-6), so the steps
            below don't get pushed down the page while the form is open. */}
        {connectCap && (
          <ConnectCapability
            embedded
            capability={connectCap}
            onConnected={onConnected}
            onClose={() => setConnectCap(null)}
          />
        )}
      </div>
    </Vstep>
  );
}

// S3-6: a linked page is brought in as a DOCUMENT awaiting adoption, not registered on the spot.
// The type dropdown that used to sit in this row is gone: classification happens at the adopt
// gate, next to the extraction it applies to, exactly as it does for an uploaded file. Asking
// here as well would ask the same question twice, and would ask it before the user has seen what
// actually came through from the page.
function ConfluenceLinkForm({ projectId }: { projectId: string }) {
  const linkPages = useLinkConfluencePages(projectId);
  const [rows, setRows] = useState<{ page: string }[]>([{ page: "" }]);
  const [result, setResult] = useState<{ linked: number; errors: { page: string; error: string }[] } | null>(null);

  const setRow = (i: number, patch: Partial<{ page: string }>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const addRow = () => setRows((rs) => [...rs, { page: "" }]);
  const removeRow = (i: number) => setRows((rs) => (rs.length > 1 ? rs.filter((_, j) => j !== i) : rs));

  const submit = async () => {
    const clean = rows.filter((r) => r.page.trim());
    if (clean.length === 0) return;
    try {
      const out = await linkPages.mutateAsync(clean);
      setResult({ linked: out.linked.length, errors: out.errors });
      if (out.errors.length === 0) setRows([{ page: "" }]);
    } catch (e) {
      // Screen Words group 5: shared handling, so a lost connection here reads the same as it
      // does everywhere else rather than showing the browser's own wording.
      setResult({
        linked: 0,
        errors: [{ page: "", error: writeErrorSentence(e, "Could not bring those pages in.") }],
      });
    }
  };

  return (
    <div className="u-stack" style={{ marginTop: "var(--space-2)" }}>
      <p className="t-sm u-muted">
        Paste the Confluence page link (or page ID) for each doc the flow needs. We bring in the
        page’s text and any diagrams attached to it; you review what came through and choose its
        type when you adopt it — the same way as an uploaded file.
      </p>
      {rows.map((r, i) => (
        <div key={i} className="u-row" style={{ gap: "var(--space-2)", alignItems: "center" }}>
          {/* Both .input and .select are `width: 100%`. Left alone in a flex row a sibling select
              keeps that full width while the input's `flex: 1` starts it from zero — which is how
              this paste box once collapsed to an unusable sliver. `minWidth: 0` lets it actually
              shrink-to-fit rather than be forced wide by its placeholder. */}
          <Input
            /* S3-10: the short "Copy link" form (…/wiki/x/AYAkAQ) is accepted too — it is the one
               the Confluence UI actually hands you, so it belongs in the example. */
            placeholder="https://…/wiki/…/pages/12345  ·  https://…/wiki/x/AYAkAQ  ·  or  12345"
            value={r.page}
            onChange={(e) => setRow(i, { page: e.target.value })}
            style={{ flex: "1 1 auto", minWidth: 0 }}
          />
          {rows.length > 1 && (
            <Button variant="ghost" onClick={() => removeRow(i)}>Remove</Button>
          )}
        </div>
      ))}
      <div className="u-row" style={{ gap: "var(--space-2)" }}>
        <Button variant="ghost" onClick={addRow}>＋ Add another</Button>
        <Button variant="secondary" onClick={submit} disabled={linkPages.isPending}>
          {linkPages.isPending ? <Spinner /> : "Bring in documents"}
        </Button>
      </div>
      {result && (
        <div className="t-sm">
          {result.linked > 0 && (
            <p style={{ color: "var(--success)" }}>
              Brought in {result.linked} page{result.linked === 1 ? "" : "s"}.{" "}
              <Link to="/onboarding/documents">Review and adopt {result.linked === 1 ? "it" : "them"} ↗</Link>
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

// ── Shared: what a headless onboarding step is doing right now ──────────────
// Index code and Gap report run as agents on a carrier work item that is hidden from the backlog,
// from Phases & Runs and from the dashboard — deliberately, so a setup step never looks like
// lifecycle work needing review. That makes THIS the only place their progress can be reported,
// which is why the message is driven by the hub's polled state and not by the POST's result: a
// mutation result is set once and never clears, so the old "running…" line survived completion
// and every later re-index. Server state clears itself.
function AgentStepStatus({ state, workingText, questionText, gateText }: {
  state: {
    running: boolean;
    question?: { id: string; count: number } | null;
    approval_id?: string | null;
  };
  workingText: string;
  questionText: string;
  gateText?: string;
}) {
  if (!state.running) return null;
  // Parked at its review gate (S5-8). The run is not finished, so `running` is still true — but
  // it is waiting on the USER, not working. The gap report is gated by design, and without this
  // the step said "working…" for as long as approval took and offered no way to reach the gate.
  if (state.approval_id) {
    return (
      <Card attention>
        <CardBody style={{ maxWidth: "520px" }}>
          <span className="gate-panel__role">Waiting for your approval</span>
          <p className="t-sm" style={{ marginTop: "var(--space-1)" }}>
            {gateText ?? "The assessment is ready and needs your sign-off before the project resumes."}
          </p>
          <div className="gate-panel__actions">
            {/* N2 — this was a DEAD LINK. There is no `/gates/:id` route, so the catch-all
                bounced the user to the Dashboard without a word: the primary action on a
                *blocking* onboarding step went nowhere. `/gates/:id` is now registered as a
                redirect so bookmarks already in the wild resolve, and new code links direct. */}
            <Link to={gateLink(state.approval_id)} className="btn btn--primary">
              Review the assessment
            </Link>
          </div>
        </CardBody>
      </Card>
    );
  }
  // A blocked agent is still "running", but the user has to act and nothing else would say so.
  if (state.question) {
    return (
      <Card attention>
        <CardBody style={{ maxWidth: "520px" }}>
          <span className="gate-panel__role">Waiting on you</span>
          <p className="t-sm" style={{ marginTop: "var(--space-1)" }}>{questionText}</p>
          <div className="gate-panel__actions">
            {/* N2: the id is right there on the state. Sending "Answer the question" (singular,
                whose text is printed directly above) to the bare list meant the screen could open
                on a DIFFERENT pending question — which is worse than a list, because it invites
                the wrong answer to be typed into the wrong box. */}
            <Link to={clarificationLink(state.question.id)} className="btn btn--primary">
              {state.question.count === 1 ? "Answer the question" : "Answer the questions"}
            </Link>
          </div>
        </CardBody>
      </Card>
    );
  }
  // Amber, not muted grey: this is the only signal that a multi-minute agent run is under way —
  // the run is deliberately absent from Phases & Runs, Gates and the dashboard — so it has to be
  // findable at a glance. `--warning` is the token the product already uses for in-progress
  // states (e.g. the connecting companion pill), so this reads as "working", not "broken".
  return (
    <p
      className="t-sm u-row"
      style={{ gap: "var(--space-2)", alignItems: "center", color: "var(--warning)" }}
    >
      <Spinner />
      <span>{workingText}</span>
    </p>
  );
}

// ── Step 4: Index code (B4-1) — dispatch real code intelligence per repo ──
// The button dispatches the code-intelligence agent to the connected companion, which analyses the
// repo in a read-only worktree and reports back (nothing is copied off the machine). The web
// endpoint only dispatches — it can't fabricate an index (B4-2).
function IndexCodeStep({ projectId, repoStates, indexDone }: {
  projectId: string;
  repoStates: OnboardingRepoIndex[];
  indexDone: boolean;
}) {
  const startCodeIntel = useStartCodeIntel(projectId);

  return (
    <Vstep
      num="4"
      title="Index code"
      desc={
        indexDone
          ? "Code intelligence is ready."
          : "Analyse each repository on your connected companion — it reads the code in a read-only copy and reports back. Nothing is copied off your machine."
      }
      state={indexDone ? "done" : undefined}
    >
      {repoStates.length === 0 ? (
        <p className="t-sm u-muted" style={{ marginTop: "var(--space-2)" }}>
          Register a repository first (step 3) to index code.
        </p>
      ) : (
        <div className="u-stack" style={{ marginTop: "var(--space-2)" }}>
          {repoStates.map((r) => (
            <div key={r.repo_id} className="u-stack" style={{ gap: "var(--space-1)" }}>
              <div className="u-row" style={{ gap: "var(--space-2)", alignItems: "center" }}>
                <span className="u-strong">{r.name}</span>
                <Button
                  variant="secondary"
                  onClick={() => startCodeIntel.mutate(r.repo_id)}
                  disabled={r.status === "running" || startCodeIntel.isPending}
                >
                  {r.status === "running"
                    ? "Indexing dispatched…"
                    : r.status === "indexed"
                      ? "Re-index code"
                      : "Index code"}
                </Button>
                {/* Straight to the result, not a filtered list — one click to what it produced. */}
                {r.status === "indexed" && r.artifact_id && (
                  <Link to={`/artifacts/${r.artifact_id}`} className="t-sm">
                    View what it found
                  </Link>
                )}
              </div>
              <AgentStepStatus
                state={r}
                workingText={`Reading ${r.name} on your machine — this usually takes a few minutes. You can leave this page; it keeps going.`}
                questionText={`The code-intelligence agent has a question about ${r.name} before it can finish.`}
              />
              {r.status === "indexed" && (
                <p className="t-sm" style={{ color: "var(--success)" }}>
                  Done — {r.name} has been analysed and the findings are saved. They feed the gap
                  report next.
                </p>
              )}
            </div>
          ))}
          <p className="t-sm u-muted">
            Requires your companion online. It runs the analysis on your machine and reports back.
          </p>
          {startCodeIntel.isError && (
            <div style={{ marginTop: "var(--space-2)" }}>
              <WriteError title="Couldn't start indexing" detail={startCodeIntel.error} />
            </div>
          )}
        </div>
      )}
    </Vstep>
  );
}

// ── Prerequisite: the machine that runs the agents ─────────────────────────
// Brownfield onboarding leans on the user's own machine for the work that must stay local —
// reading a document's diagrams, and indexing the code. Greenfield users meet this on the setup
// checklist before they start; brownfield users met it only as a failure message *after* adopting
// a document, using a word ("companion") that appears nowhere else in the product. This puts the
// same step in front of them on arrival, in the app's own vocabulary, with the button right here.
function ConnectMachineStep() {
  // Polled, because this reports a LIVE connection: a companion that stops while the page is
  // open must stop claiming to be connected without a manual reload.
  const runners = useRunners(true);
  if (runners.isLoading) return null;
  // `online` only — deliberately NOT "has ever checked in". That weaker test is right on the
  // setup checklist, where the question is "did you complete this step once", and wrong here,
  // where the question is "can this document's diagrams be read right now". Using it made the
  // page report a connected machine while the header showed the companion offline.
  const connected = Boolean(runners.data?.some((r) => r.online));
  if (connected) {
    return (
      <Card>
        <CardBody className="u-row" style={{ gap: "var(--space-3)", alignItems: "center" }}>
          <span className="vstep__num vstep__num--done">✓</span>
          <div style={{ flex: "1 1 auto" }}>
            <div className="t-body u-strong">Your machine is connected</div>
            <div className="t-sm u-muted">
              Diagrams in your documents get read into text, and your code is analysed locally.
            </div>
          </div>
          <Badge variant="done">Connected</Badge>
        </CardBody>
      </Card>
    );
  }
  // Enrolled once but not answering now is a different problem from never having set it up, and
  // it has a different fix — start the companion, rather than go and connect a machine.
  const everConnected = Boolean(runners.data?.some((r) => r.last_seen));
  return (
    <Card>
      <CardBody className="u-row" style={{ gap: "var(--space-3)", alignItems: "center" }}>
        {/* `!`, not `1`. This card is a PREREQUISITE, not the first step — and rendering a
            `1` here put two steps numbered 1 in front of every first-time user, because
            "Upload resources" below is also 1. */}
        <span className="vstep__num vstep__num--active">!</span>
        <div style={{ flex: "1 1 auto" }}>
          <div className="t-body u-strong">
            {everConnected ? "Your machine isn't running right now" : "Connect your machine first"}
          </div>
          <div className="t-sm u-muted">
            {everConnected ? MACHINE_COPY.offline : MACHINE_COPY.line}
            <Tooltip placement="below">{MACHINE_COPY.detail}</Tooltip>
          </div>
        </div>
        <Link to="/connect" className="btn btn--primary">
          {everConnected ? "Machine setup" : "Connect your machine"}
        </Link>
      </CardBody>
    </Card>
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
  // S3-14: a linked Confluence page is a source document, so it belongs in this list — but it was
  // never "uploaded", and counting it as one made this step contradict the one below it ("11
  // documents uploaded" over "2 pages linked"). Split the sentence, don't split the list.
  const linkedCount = data.upload.filter((d) => d.origin === "confluence").length;
  const uploadedCount = data.upload.length - linkedCount;
  const sourcesSummary = [
    uploadedCount > 0 ? `${uploadedCount} document${uploadedCount === 1 ? "" : "s"} uploaded` : "",
    linkedCount > 0 ? `${linkedCount} page${linkedCount === 1 ? "" : "s"} linked` : "",
  ].filter(Boolean).join(" · ") + ".";
  const repoCount = repos.data?.length ?? 0;
  const reposDone = repoCount > 0;
  // Prefer the hub's per-repo state (carries running / question / artifact link). Fall back to the
  // repositories list so a backend that predates `index.repos` still renders the step.
  const repoStates: OnboardingRepoIndex[] =
    data.index.repos ??
    (repos.data ?? []).map((r) => ({
      repo_id: r.id, name: r.name, status: "not_started" as const,
      running: false, run_id: null, question: null, artifact_id: null,
    }));
  const indexDone = repoStates.length > 0 && repoStates.every((r) => r.status === "indexed");
  // The backend serves the human label beside the key (S5-7). The hub used to interpolate the raw
  // key, so a user read "Resume at: task_breakdown". Fall back to prettifying the slug rather than
  // to a lookup table, which is what drifted in the first place.
  // Defaulted rather than optional-chained at every use: a backend that predates this field
  // must still render the step, showing it as not started, which is what it is.
  const a11y = data.a11y ?? {
    routes_registered: 0, audits_run: 0, running: false, status: "not_started" as const,
  };
  const gapResumeLabel =
    data.gap.resume_label ||
    (data.gap.resume_phase ?? "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

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

      <ConnectMachineStep />

      <Card>
        <CardBody>
          <Vstep
            num="1"
            title="Upload resources"
            desc={
              data.upload.length === 0
                ? "Drag in existing specs, PRDs, designs (.docx · .pdf · .xlsx · .txt · .html)."
                : sourcesSummary
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
                    {/* Screen Words group 4: "Spec.pdf · extracted" -> "Spec.pdf · Ready to
                        adopt". Same map as the Source documents screen this chip links to. */}
                    {doc.filename} · {documentStatusLabel(doc.status)}
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

          <IndexCodeStep projectId={projectId} repoStates={repoStates} indexDone={indexDone} />

          <Vstep
            num="5"
            title="Gap report"
            desc={data.gap.ready
              ? `Ready — resume at ${gapResumeLabel}.`
              : "What exists, what's missing, and where to resume."}
            state={data.gap.ready ? "done" : undefined}
          >
            {/* The ready card and the run controls render TOGETHER, not either/or (S5-8). When
                they were exclusive, a re-run after adopting more documents showed nothing at all:
                no progress line, no "waiting on you" card, and no button to press — because the
                whole branch was unreachable the moment a report existed. Re-running is the normal
                case, so it has to be visible. */}
            <div className="u-stack" style={{ marginTop: "var(--space-2)" }}>
              {data.gap.ready && (
                <Card attention>
                  <CardBody style={{ maxWidth: "520px" }}>
                    <span className="gate-panel__role">Recommended resume point</span>
                    <h3 className="t-h3">Resume at: {gapResumeLabel}</h3>
                    <div className="gate-panel__actions">
                      <Link to="/onboarding/gap-report" className="btn btn--secondary">
                        View full gap report
                      </Link>
                      {/* The rendered report document itself, mirroring what the Index code
                          step already offers for its intelligence artifact (S5-19). */}
                      {data.gap.report_artifact_id && (
                        <Link
                          to={`/artifacts/${data.gap.report_artifact_id}`}
                          className="btn btn--ghost"
                        >
                          Open the report document
                        </Link>
                      )}
                    </div>
                  </CardBody>
                </Card>
              )}
              <div className="gate-panel__actions">
                <Button
                  variant="secondary"
                  onClick={() => runGapReport.mutate()}
                  disabled={data.gap.running || runGapReport.isPending}
                >
                  {data.gap.running
                    ? "Assessment dispatched…"
                    : data.gap.ready ? "Re-run gap report" : "Run gap report"}
                </Button>
              </div>
              <AgentStepStatus
                state={data.gap}
                workingText="Assessing your project on your machine — reading everything you've brought in and the code analysis. This usually takes a few minutes."
                questionText="The onboarding agent has a question about your project before it can finish the assessment."
                gateText="The assessment is ready. Approve it to publish the gap report and set the resume point."
              />
              {/* Which path ran (S5-9). The two are genuinely different products: the agent
                  reasons over the evidence on your machine and takes minutes; the fallback is a
                  mechanical count that returns instantly. Saying nothing left the user unable to
                  tell a considered assessment from a tally. */}
              {runGapReport.data?.mode === "deterministic" && !data.gap.running && (
                <p className="t-sm u-muted">
                  Assessed mechanically from what's registered — your machine wasn't connected, so
                  no agent reasoned over it. Connect your machine and re-run for a fuller reading.
                </p>
              )}
              {runGapReport.data?.mode === "agent" && (
                <p className="t-sm u-muted">Your machine is assessing the project.</p>
              )}
              {runGapReport.isError && (
                <div style={{ marginTop: "var(--space-2)" }}>
                  <WriteError title="Couldn't run the gap report" detail={runGapReport.error} />
                </div>
              )}
            </div>
          </Vstep>

          {/* B4 — the way anyone finds the accessibility work at all. The audit screen existed
              behind a tab nothing pointed at, which is found only by someone who already knew.
              It sits before Resume on purpose: the point of a baseline is to know where the
              application stands BEFORE anything is changed. */}
          <Vstep
            num="6"
            title="Check accessibility"
            desc={
              a11y.status === "done"
                ? `${a11y.audits_run} audit${a11y.audits_run === 1 ? "" : "s"} run — open the report from Artifacts.` +
                  // Said over the top of the tick rather than instead of it. A finished audit
                  // stays finished while the next one runs, and both facts are true at once.
                  (a11y.running ? " Another audit is running now." : "")
                : a11y.status === "running"
                  ? "An audit is running now. It appears here, with its report, once it finishes."
                  : a11y.status === "ready"
                    ? `${a11y.routes_registered} page(s) registered. Run a first audit against WCAG 2.2 AA.`
                    : "Register the pages of the application and run a first audit against WCAG 2.2 AA. This tells you where the application stands before you change anything."
            }
            state={
              a11y.status === "done"
                ? "done"
                : a11y.status === "ready" || a11y.status === "running"
                  ? "active"
                  : undefined
            }
          >
            <div className="gate-panel__actions" style={{ marginTop: "var(--space-3)" }}>
              <Link
                to="/a11y/pages"
                className={a11y.status === "done" ? "btn btn--secondary" : "btn btn--primary"}
              >
                {a11y.status === "not_started" ? "Set up the audit" : "Pages & audit"}
              </Link>
            </div>
          </Vstep>

          <Vstep
            num="7"
            title="Resume"
            desc={data.gap.ready ? `Trigger ${gapResumeLabel} on a work item to enter the pipeline.` : "Available after the gap report."}
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
//
// These MIRROR the live hub above, step for step. They drifted once — the gallery kept the
// original five steps while the real screen grew to a prerequisite card plus seven — so every
// design review and every journey test ran against a screen that no longer existed. If a step
// is added above, add it here in the same pass.

function GalleryConnect({ connected }: { connected: boolean }) {
  return (
    <Card>
      <CardBody className="u-row" style={{ gap: "var(--space-3)", alignItems: "center" }}>
        <span className={`vstep__num vstep__num--${connected ? "done" : "active"}`}>
          {connected ? "✓" : "!"}
        </span>
        <div style={{ flex: "1 1 auto" }}>
          <div className="t-body u-strong">
            {connected ? "Your machine is connected" : "Connect your machine first"}
          </div>
          <div className="t-sm u-muted">
            {MACHINE_COPY.line}
            <Tooltip>{MACHINE_COPY.detail}</Tooltip>
          </div>
        </div>
        <Badge variant={connected ? "done" : undefined}>
          {connected ? "Connected" : "Not connected"}
        </Badge>
      </CardBody>
    </Card>
  );
}

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

      <GalleryConnect connected={view !== "nothing-done"} />

      <Card>
        <CardBody>
          {view === "nothing-done" && (
            <>
              <Vstep num="1" title="Upload resources" desc="Drag in existing specs, PRDs, designs (.docx · .pdf · .xlsx · .txt · .html)." state="active">
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
              <Vstep num="2" title="Register existing tools" desc="Bring your existing backlog and documentation in — register, don't recreate." />
              <Vstep num="3" title="Register repositories" desc="Add the repositories the platform should analyse — code indexing and the gap report need at least one." />
              <Vstep num="4" title="Index code" desc="Point at a repo; built-in code intelligence indexes it." />
              <Vstep num="5" title="Gap report" desc="What exists, what's missing, and where to resume." />
              <Vstep num="6" title="Check accessibility" desc="Register the pages of the application and run a first audit against WCAG 2.2 AA — where it stands before you change anything." />
              <Vstep num="7" title="Resume" desc="Trigger the recommended phase and hand into the normal pipeline." />
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
              <Vstep num="3" title="Register repositories" desc="1 repository registered." state="done" />
              <Vstep num="4" title="Index code" desc="Indexing acme/legacy-billing…" state="running">
                <ConnStatus state="waiting">
                  <Spinner /> Indexing 1,284 files… 64%
                </ConnStatus>
              </Vstep>
              <Vstep num="5" title="Gap report" desc="Runs once indexing completes." />
              <Vstep num="6" title="Check accessibility" desc="Register the pages of the application and run a first audit against WCAG 2.2 AA." />
              <Vstep num="7" title="Resume" desc="Available after the gap report." />
            </>
          )}

          {view === "gap-ready" && (
            <>
              <Vstep num="1" title="Upload resources" desc="3 documents adopted as draft artifacts." state="done" />
              <Vstep num="2" title="Register existing tools" desc="32 Jira issues linked." state="done" />
              <Vstep num="3" title="Register repositories" desc="1 repository registered." state="done" />
              <Vstep num="4" title="Index code" desc="1,284 files indexed." state="done" />
              <Vstep num="5" title="Gap report" desc="Ideation ✓ · Requirements ✓ · PRD ~Partial · Architecture ✗ missing." state="done">
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
              <Vstep num="6" title="Check accessibility" desc="2 audits run — open the report from Artifacts." state="done">
                <div className="gate-panel__actions" style={{ marginTop: "var(--space-3)" }}>
                  <Link to="/a11y/pages" className="btn btn--secondary">
                    Pages &amp; audit
                  </Link>
                </div>
              </Vstep>
              <Vstep num="7" title="Resume" desc="Trigger Architecture on a work item to enter the pipeline." state="active">
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
