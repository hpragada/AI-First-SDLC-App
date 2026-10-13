import { useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, Banner, Button, Combobox, ConfirmDialog, EmptyState, Field, Modal, Panel, Select, Spinner, Table, WriteError } from "../../components/ui";
import { engineLabel, runStatusLabel, runStatusTone } from "../../labels";
import { useCompanionStatus } from "../identity/hooks";
import { roleLabel } from "../identity/roles";
import { isBrownfieldPhase, phaseLabel } from "./phases";
import { usePhaseCatalog, useRuns, useTriggerPhase, useWorkItems } from "./hooks";
import type { PhaseCatalogEntry, Run } from "../../types";

// S-18 view states: companion online + triggerable (default) · companion offline
// (blocked) · no runs yet.
export type PhasesRunsView = "online" | "offline" | "no-runs";

export function PhasesAndRuns({ forceView }: { forceView?: PhasesRunsView }) {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const workItems = useWorkItems(projectId);
  const catalog = usePhaseCatalog();
  const [selectedWorkItemId, setSelectedWorkItemId] = useState<string | undefined>();

  const activeWorkItemId =
    selectedWorkItemId ?? workItems.data?.[0]?.id;

  const runs = useRuns({
    project: forceView ? undefined : projectId,
    work_item: forceView ? undefined : activeWorkItemId,
  });
  const trigger = useTriggerPhase(activeWorkItemId);

  // Scoped to this project. The old `runners.some(r => r.online)` asked whether ANY machine of
  // this user's was alive on ANY project, so a companion serving a different project left these
  // phase buttons enabled while the machine that would actually run them was dead — a trigger
  // straight into a run nobody claims. `checking` counts as online on purpose: one missed
  // heartbeat must not take the trigger away mid-session.
  const companion = useCompanionStatus(projectId);
  const online = companion.state === "ready" || companion.state === "checking";
  const view: PhasesRunsView =
    forceView ??
    (!online ? "offline" : (runs.data?.length ?? 0) === 0 ? "no-runs" : "online");

  // Bugs.xlsx row 33: when the companion is offline (or there are simply no runs yet), the Runs
  // panel must show the "No runs yet" empty state — not the demo sampleRuns it used to fall back to.
  // In the gallery (forceView) we still show sampleRuns so the design catalogue has data.
  const showRunsEmpty = view === "no-runs" || (!forceView && (runs.data?.length ?? 0) === 0);

  // All phases from the live catalog: plan + build in order.
  //
  // The onboarding phases (Onboarding, Context Bridge, Context Extraction, Document Vision)
  // read an existing codebase and report what is missing from it. On a project started from
  // scratch there is nothing for them to read, and the team found all four offered on a
  // greenfield project with no way to tell they were irrelevant (2026-10-06). The app already
  // takes this position elsewhere — the Onboarding SCREEN is hidden from greenfield, saying
  // "the lifecycle begins at Ideation instead" (AppShell, RequireBrownfield) — and this screen
  // simply never got the same rule.
  //
  // `=== "greenfield"` and NOT `!== "brownfield"`, matching those two exactly: an API too old
  // to send the track must show the phases rather than hide a brownfield team's own work from
  // them mid-deploy (S.No 221).
  const hideOnboardingPhases = selectedProject?.track === "greenfield";
  const allPhases: PhaseCatalogEntry[] = [
    ...(catalog.data?.plan ?? []),
    ...(catalog.data?.build ?? []),
    ...(catalog.data?.remediation ?? []),
  ].filter((p) => !(hideOnboardingPhases && isBrownfieldPhase(p.key)));

  // Gallery fallback phases (used only when forceView is set)
  const galleryPhases: PhaseCatalogEntry[] = [
    { key: "01_ideation",     label: "Ideation",      agent_key: "01_ideation",     gate_role: "product_owner" },
    { key: "02_requirements", label: "Requirements",  agent_key: "02_requirements", gate_role: "product_owner" },
    { key: "03_prd",          label: "PRD",           agent_key: "03_prd",          gate_role: "product_owner" },
    { key: "04_architecture", label: "Architecture",  agent_key: "04_architecture", gate_role: "architect" },
    { key: "05_ux_design",    label: "UX Design",     agent_key: "05_ux_design",    gate_role: "designer" },
    { key: "06_task_breakdown",label:"Task Breakdown", agent_key:"06_task_breakdown",gate_role:"tech_lead" },
    { key: "07_implementation",label:"Implementation", agent_key:"07_implementation",gate_role:"tech_lead" },
    { key: "08_code_review",  label: "Code Review",   agent_key: "08_code_review",  gate_role: "reviewer" },
    { key: "09_testing",      label: "Testing",       agent_key: "09_testing",      gate_role: "qa_lead" },
    { key: "10_security",     label: "Security",      agent_key: "10_security",     gate_role: "security_engineer" },
    { key: "11_cicd",         label: "CI/CD",         agent_key: "11_cicd",         gate_role: "devops" },
    { key: "12_deployment",   label: "Deployment",    agent_key: "12_deployment",   gate_role: "devops" },
  ];

  const phases = forceView ? galleryPhases : (allPhases.length > 0 ? allPhases : galleryPhases);

  // Runs that mean a phase is still live — re-triggering one of these would spawn a second
  // concurrent run (the backend blocks it with 409; the UI warns first). Bugs S.No 77.
  const ACTIVE_STATUSES = ["pending", "running", "awaiting_gate", "approved"];
  const runsForItem = forceView ? [] : (runs.data ?? []);
  const latestRunForPhase = (agentKey: string): Run | undefined =>
    runsForItem
      .filter((r) => r.agent_key === agentKey)
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))[0];

  // When a phase already has a run, confirm before re-triggering (Case 1: completed → restart &
  // replace this phase's artifacts; Case 2: in progress → blocked). Applies to EVERY phase, not
  // just Task Breakdown — any re-run regenerates that phase's artifacts.
  // "first" is the case that used to fire with no question at all. It is a confirmation like
  // "rerun"; "active" is a refusal, which is why it keeps a plain Modal with no confirm button.
  const [confirm, setConfirm] = useState<{ phase: PhaseCatalogEntry; kind: "first" | "rerun" | "active"; run?: Run } | null>(null);

  const handleTrigger = (phase: PhaseCatalogEntry) => {
    if (!activeWorkItemId) return;
    const prior = latestRunForPhase(phase.agent_key);
    if (prior && ACTIVE_STATUSES.includes(prior.status)) {
      setConfirm({ phase, kind: "active", run: prior });
    } else if (prior) {
      setConfirm({ phase, kind: "rerun", run: prior });
    } else {
      // Was `trigger.mutate(...)` — a phase run started on a single click, dispatching work to the
      // user's own machine for several minutes, with nothing asked.
      setConfirm({ phase, kind: "first" });
    }
  };

  const confirmTrigger = () => {
    if (!confirm) return;
    // Closes on SUCCESS only. Closing straight away threw away the refusal the server sends when a
    // phase cannot start (an active run, a missing companion), so the click looked as though it had
    // worked and nothing happened.
    trigger.mutate(confirm.phase.agent_key, { onSuccess: () => setConfirm(null) });
  };

  const activeWorkItem = workItems.data?.find((wi) => wi.id === activeWorkItemId);
  // One name for one work item, everywhere on this screen (P1). The picker called it "WI-159",
  // this line called the same item "3f2a9c1b" — eight characters of an internal id that appears
  // nowhere else a user can see — and the Runs panel called it neither, showing the bare title.
  // An item with no number falls back to its title, never to the id.
  const workItemName = (wi: { key?: string; title?: string; type?: string }) =>
    [wi.key, wi.title || wi.type].filter(Boolean).join(" · ");
  const workItemLabel = activeWorkItem
    ? workItemName(activeWorkItem)
    : "No work item selected";

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Phases & Runs</h1>
          <p className="page-head__sub">
            Trigger a phase for a work item — it runs on <strong>your</strong> companion — and watch
            every run here.
          </p>
        </div>
      </div>

      <div style={{ marginBottom: "var(--space-5)" }}>
        <Panel title="Trigger a phase">
          {view === "offline" ? (
            <div className="u-stack">
              <Banner variant="warning" title="Your machine isn't connected">
                Phases can't run until your companion is online.{" "}
                <Link to="/connect">Connect your machine ↗</Link>
              </Banner>
              {/* Bugs S.No 173: show the FULL phase list even when offline (greyed + non-
                  interactive) so the user can see every phase that exists — not just a 3-phase
                  placeholder. They become clickable once the companion is online. */}
              <div className="phase-picker" style={{ opacity: 0.5, pointerEvents: "none" }}>
                {phases.map((p) => (
                  <button key={p.key} className="btn btn--secondary btn--sm" aria-disabled="true">
                    ▶ {phaseLabel(p.key)}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="u-stack">
              {/* Bugs S.No 171: the companion status lives in the top bar only — no separate
                  "Companion ready" box here. */}
              <div className="u-row u-wrap">
                <Field label="Work item" style={{ marginBottom: 0, minWidth: "280px" }}>
                  {forceView ? (
                    <Select>
                      <option>WI-492 · Stripe Webhook Integration (Epic)</option>
                      <option>WI-540 · Verify Stripe signing secret (Task)</option>
                    </Select>
                  ) : (
                    // Searchable (Bugs S.No 150): a project can have dozens of work items, so
                    // scrolling a plain <select> to find one is painful — type to filter instead.
                    <Combobox
                      id="work-item-picker"
                      value={activeWorkItemId ?? ""}
                      onChange={setSelectedWorkItemId}
                      disabled={workItems.isLoading}
                      placeholder={workItems.isLoading ? "Loading…" : "Search work items…"}
                      emptyText="No work items match"
                      options={(workItems.data ?? []).map((wi) => ({
                        value: wi.id,
                        label: `${wi.key || wi.id.slice(0, 8)} · ${wi.title || wi.type}`,
                      }))}
                    />
                  )}
                </Field>
              </div>
              <div>
                <span className="field__label">
                  {forceView
                    ? "Phases valid for this Epic"
                    : `All phases — ${workItemLabel}`}
                </span>
                {catalog.isLoading && !forceView && (
                  <span className="u-muted t-sm" style={{ marginLeft: "var(--space-2)" }}>
                    <Spinner /> Loading phases…
                  </span>
                )}
                <div className="phase-picker" style={{ marginTop: "var(--space-3)" }}>
                  {phases.map((p) => (
                    <button
                      key={p.key}
                      className="btn btn--secondary btn--sm"
                      disabled={
                        forceView
                          ? ["01_ideation", "02_requirements", "03_prd"].includes(p.key)
                          : trigger.isPending || !activeWorkItemId
                      }
                      onClick={() => handleTrigger(p)}
                      title={`Trigger ${phaseLabel(p.key)} (gate: ${roleLabel(p.gate_role)})`}
                    >
                      {trigger.isPending && trigger.variables === p.agent_key ? (
                        <><Spinner /> Triggering…</>
                      ) : (
                        `▶ ${phaseLabel(p.key)}`
                      )}
                    </button>
                  ))}
                </div>
                {trigger.isError && (
                  <div style={{ marginTop: "var(--space-3)" }}>
                    <WriteError title="Trigger failed" detail={trigger.error} />
                  </div>
                )}
                {trigger.isSuccess && (
                  <div style={{ marginTop: "var(--space-3)" }}>
                    <Banner variant="success" title="Phase triggered">
                      Run started — watch it appear in the Runs table below.
                    </Banner>
                  </div>
                )}
              </div>
            </div>
          )}
        </Panel>
      </div>

      <Panel
        flush={!showRunsEmpty}
        title="Runs"
        // Bugs S.No 173: the selected work-item label shows only when the companion is online;
        // it's hidden in the offline state.
        actions={
          view === "offline" ? undefined : (
            <span className="t-sm u-muted">
              {forceView ? "WI-492" : (activeWorkItem ? workItemName(activeWorkItem) : "—")}
            </span>
          )
        }
      >
        {showRunsEmpty ? (
          <EmptyState
            title="No runs yet"
            text="Trigger the first phase for this work item to see runs appear here with live status."
          />
        ) : (
          <>
            {/* Bugs S.No 175: the "Cost (est.)" column and its note were testing-only and have
                been removed. */}
            <Table
              headers={[
                "Run", "Phase", "Status", "Engine / model",
                "Workflow", "Created",
              ]}
              rows={(forceView ? sampleRuns : runs.data ?? []).map((r) => [
                // Humanised short reference, full id on hover; opens the run console
                // (Bugs.xlsx row 55: no raw long UUIDs in the table).
                <Link to={`/runs/${r.id}`} className="table__id" title={r.id} key="id">
                  Run {shortRef(r.id)} ↗
                </Link>,
                <span className="table__primary" key="p">{phaseLabel(r.agent_phase ?? r.agent_key)}</span>,
                // Screen Words group 4: was a local copy of the status-to-colour rules, which is
                // how "unlinked" ended up green on another screen. One shared map now.
                <Badge variant={runStatusTone(r.status)} key="s">{runStatusLabel(r.status)}</Badge>,
                // Screen Words group 4, Option A (team's pick 18 Sep): the line stays, written
                // as the product and model name rather than `claude · claude-opus-5`.
                engineLabel(r.engine, r.model),
                <span className="table__id" title={r.temporal_workflow_id} key="w">
                  {shortRef(r.temporal_workflow_id)}
                </span>,
                formatWhen(r.created_at),
              ])}
            />
          </>
        )}
      </Panel>

      {confirm && confirm.kind !== "active" && (
        <ConfirmDialog
          title={
            confirm.kind === "rerun"
              ? `Re-run ${phaseLabel(confirm.phase.key)}?`
              : `Start ${phaseLabel(confirm.phase.key)}?`
          }
          confirmLabel={confirm.kind === "rerun" ? "Re-run phase" : "Start phase"}
          cancelLabel="Not now"
          busy={trigger.isPending}
          error={trigger.isError ? trigger.error : undefined}
          errorFallback="The phase could not be started."
          onClose={() => setConfirm(null)}
          onConfirm={confirmTrigger}
        >
          <p className="u-body">
            This runs {phaseLabel(confirm.phase.key)} for <strong>{workItemLabel}</strong> on your
            companion. It may take several minutes, and you&apos;ll be asked to review the result
            before anything is published.
          </p>
          {/* The warning that was already here, kept as an addition rather than a replacement — it
              is the one thing somebody re-running a phase has to know. */}
          {confirm.kind === "rerun" && (
            <Banner variant="warning">
              This phase has already run. Running it again starts over and{" "}
              <strong>replaces this phase&apos;s artifacts</strong> — it does not create
              duplicates. The previous run stays in the history.
            </Banner>
          )}
          {confirm.kind === "first" && <p className="u-body">You can pause it at any time.</p>}
        </ConfirmDialog>
      )}

      {confirm && confirm.kind === "active" && (
        <Modal
          title={`${phaseLabel(confirm.phase.key)} is already running`}
          onClose={() => setConfirm(null)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setConfirm(null)}>Close</Button>
              {confirm.run && (
                <Link className="btn btn--primary" to={`/runs/${confirm.run.id}`}>
                  Open current run
                </Link>
              )}
            </>
          }
        >
          <p className="u-body">
            This work item already has a run <strong>in progress</strong> for this phase. You
            can&apos;t start a new one until it finishes — wait for it, or open the run to take it
            over.
          </p>
        </Modal>
      )}
    </div>
  );
}

const sampleRuns: Run[] = [
  {
    id: "RUN-42", work_item: "WI-492", agent_spec: "Architecture",
    agent_key: "04_architecture", agent_phase: "Architecture",
    status: "gate", engine: "Claude", model: "local",
    cost_usd: "0.31", temporal_workflow_id: "wf-7c3a",
    started_at: null, ended_at: null, created_at: "just now",
  },
  {
    id: "RUN-41", work_item: "WI-492", agent_spec: "PRD",
    agent_key: "03_prd", agent_phase: "PRD",
    status: "done", engine: "Claude", model: "local",
    cost_usd: "0.18", temporal_workflow_id: "wf-6b21",
    started_at: null, ended_at: null, created_at: "1h ago",
  },
];


// A short human reference for any long id ("82a4ff91-…" -> "82a4ff91",
// "agent-run-82a4ff91-…" -> "agent-run-82a4ff91"); short values pass through.
// Dynamic — works for every run/workflow, full value stays on hover (row 55).
function shortRef(id: string | null | undefined): string {
  if (!id) return "—";
  const m = id.match(/^(.*?)([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f-]+$/i);
  if (m) return `${m[1]}${m[2]}`;
  return id.length > 20 ? `${id.slice(0, 17)}…` : id;
}

// Locale-formatted timestamp for user-facing display; non-date strings (gallery
// samples like "just now") pass through unchanged.
function formatWhen(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
