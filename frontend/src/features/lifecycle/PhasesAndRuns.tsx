import { useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, Banner, EmptyState, Field, Panel, Select, Spinner, Table } from "../../components/ui";
import { useRunners } from "../identity/hooks";
import { roleLabel } from "../identity/roles";
import { phaseLabel, statusLabel } from "./phases";
import { usePhaseCatalog, useRuns, useTriggerPhase, useWorkItems } from "./hooks";
import type { PhaseCatalogEntry, Run } from "../../types";

// S-18 view states: companion online + triggerable (default) · companion offline
// (blocked) · no runs yet.
export type PhasesRunsView = "online" | "offline" | "no-runs";

export function PhasesAndRuns({ forceView }: { forceView?: PhasesRunsView }) {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const runners = useRunners();
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

  const online = Boolean(runners.data?.some((r) => r.online));
  const view: PhasesRunsView =
    forceView ??
    (!online ? "offline" : (runs.data?.length ?? 0) === 0 ? "no-runs" : "online");

  // Bugs.xlsx row 33: when the companion is offline (or there are simply no runs yet), the Runs
  // panel must show the "No runs yet" empty state — not the demo sampleRuns it used to fall back to.
  // In the gallery (forceView) we still show sampleRuns so the design catalogue has data.
  const showRunsEmpty = view === "no-runs" || (!forceView && (runs.data?.length ?? 0) === 0);

  // All phases from the live catalog: plan + build in order
  const allPhases: PhaseCatalogEntry[] = [
    ...(catalog.data?.plan ?? []),
    ...(catalog.data?.build ?? []),
    ...(catalog.data?.remediation ?? []),
  ];

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

  const handleTrigger = (agentKey: string) => {
    if (!activeWorkItemId) return;
    trigger.mutate(agentKey);
  };

  const activeWorkItem = workItems.data?.find((wi) => wi.id === activeWorkItemId);
  const workItemLabel = activeWorkItem
    ? `${activeWorkItem.id.slice(0, 8)} · ${activeWorkItem.title || activeWorkItem.type}`
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
              <div className="phase-picker" style={{ opacity: 0.5, pointerEvents: "none" }}>
                {phases.slice(3, 6).map((p) => (
                  <button key={p.key} className="btn btn--secondary btn--sm" aria-disabled="true">
                    ▶ {phaseLabel(p.key)}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="u-stack">
              <div className="u-row u-wrap">
                <Field label="Work item" style={{ marginBottom: 0, minWidth: "280px" }}>
                  {forceView ? (
                    <Select>
                      <option>WI-492 · Stripe Webhook Integration (Epic)</option>
                      <option>WI-540 · Verify Stripe signing secret (Task)</option>
                    </Select>
                  ) : (
                    <Select
                      value={activeWorkItemId ?? ""}
                      onChange={(e) => setSelectedWorkItemId(e.target.value)}
                    >
                      {workItems.isLoading && <option disabled>Loading…</option>}
                      {(workItems.data ?? []).map((wi) => (
                        <option key={wi.id} value={wi.id}>
                          {wi.key || wi.id.slice(0, 8)} · {wi.title || wi.type}
                        </option>
                      ))}
                      {!workItems.isLoading && (workItems.data?.length ?? 0) === 0 && (
                        <option disabled>No work items yet</option>
                      )}
                    </Select>
                  )}
                </Field>
                <span
                  className="conn-status conn-status--connected"
                  style={{ alignSelf: "flex-end" }}
                >
                  Companion ready — {runners.data?.[0]?.machine ?? "Sarah's MacBook"}
                </span>
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
                      onClick={() => handleTrigger(p.agent_key)}
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
                    <Banner variant="danger" title="Trigger failed">
                      {trigger.error instanceof Error ? trigger.error.message : "Unknown error"}
                    </Banner>
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
        actions={
          <span className="t-sm u-muted">
            {forceView ? "WI-492" : (activeWorkItem?.title ?? activeWorkItemId?.slice(0, 8) ?? "—")}
          </span>
        }
      >
        {showRunsEmpty ? (
          <EmptyState
            title="No runs yet"
            text="Trigger the first phase for this work item to see runs appear here with live status and cost."
          />
        ) : (
          <>
            <Table
              headers={[
                "Run", "Phase", "Status", "Engine / model",
                <span
                  key="cost-h"
                  title="Computed Claude Code subscription-equivalent usage — for testing reference. The subscription is not billed per token (actual cost is $0)."
                >
                  Cost (est.)
                </span>,
                "Workflow", "Created",
              ]}
              rows={(forceView ? sampleRuns : runs.data ?? []).map((r) => [
                // Humanised short reference, full id on hover; opens the run console
                // (Bugs.xlsx row 55: no raw long UUIDs in the table).
                <Link to={`/runs/${r.id}`} className="table__id" title={r.id} key="id">
                  Run {shortRef(r.id)} ↗
                </Link>,
                <span className="table__primary" key="p">{phaseLabel(r.agent_phase ?? r.agent_key)}</span>,
                <Badge variant={statusVariant(r.status)} key="s">{statusLabel(r.status)}</Badge>,
                `${r.engine} · ${r.model}`,
                <span className="table__id" key="c">{r.cost_usd ? `$${r.cost_usd}` : "—"}</span>,
                <span className="table__id" title={r.temporal_workflow_id} key="w">
                  {shortRef(r.temporal_workflow_id)}
                </span>,
                formatWhen(r.created_at),
              ])}
            />
            <p className="t-sm u-muted">
              Cost is the computed Claude Code <strong>subscription-equivalent</strong> usage,
              shown for the team's testing reference — the subscription itself is not billed per
              token (actual charge is $0).
            </p>
          </>
        )}
      </Panel>
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

function statusVariant(status: string) {
  if (status === "done" || status === "completed" || status === "approved") return "done" as const;
  if (status === "gate" || status === "awaiting_gate") return "gate" as const;
  if (status === "failed" || status === "rejected") return "failed" as const;
  if (status === "running") return "running" as const;
  return "queued" as const;
}

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
