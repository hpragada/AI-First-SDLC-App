import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, Banner, EmptyState, Field, Panel, Select, Table } from "../../components/ui";
import { useRunners } from "../identity/hooks";
import { useRuns } from "./hooks";
import type { Run } from "../../types";

// S-18 view states: companion online + triggerable (default) · companion offline
// (blocked) · no runs yet.
export type PhasesRunsView = "online" | "offline" | "no-runs";

const PHASE_PICKER = [
  { label: "Ideation ✓", done: true },
  { label: "Requirements ✓", done: true },
  { label: "PRD ✓", done: true },
  { label: "Run Architecture", primary: true },
  { label: "UX Design" },
  { label: "Task Breakdown" },
];

export function PhasesAndRuns({ forceView }: { forceView?: PhasesRunsView }) {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project;
  const runners = useRunners();
  const runs = useRuns({ project: projectId });

  const online = Boolean(runners.data?.some((r) => r.online));
  const view: PhasesRunsView =
    forceView ?? (!online ? "offline" : (runs.data?.length ?? 0) === 0 ? "no-runs" : "online");

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
                {PHASE_PICKER.slice(3).map((p) => (
                  <button
                    key={p.label}
                    className={`btn btn--${p.primary ? "primary" : "secondary"} btn--sm`}
                    aria-disabled="true"
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="u-stack">
              <div className="u-row u-wrap">
                <Field label="Work item" style={{ marginBottom: 0, minWidth: "280px" }}>
                  <Select>
                    <option>WI-492 · Stripe Webhook Integration (Epic)</option>
                    <option>WI-540 · Verify Stripe signing secret (Task)</option>
                  </Select>
                </Field>
                <span className="conn-status conn-status--connected" style={{ alignSelf: "flex-end" }}>
                  Companion ready — {runners.data?.[0]?.machine ?? "Sarah's MacBook"}
                </span>
              </div>
              <div>
                <span className="field__label">Phases valid for this Epic</span>
                <div className="phase-picker">
                  {PHASE_PICKER.map((p) => (
                    <button
                      key={p.label}
                      className={`btn btn--${p.primary ? "primary" : "secondary"} btn--sm`}
                      disabled={p.done}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </Panel>
      </div>

      <Panel
        flush={view !== "no-runs"}
        title="Runs"
        actions={<span className="t-sm u-muted">{view === "no-runs" ? "WI-508" : "WI-492"}</span>}
      >
        {view === "no-runs" ? (
          <EmptyState
            title="No runs yet"
            text="Trigger the first phase for this work item to see runs appear here with live status and cost."
          />
        ) : (
          <Table
            headers={["Run", "Phase", "Status", "Engine / model", "Cost", "Workflow", "Created"]}
            rows={(runs.data ?? sampleRuns).map((r) => [
              <span className="table__id" key="id">
                {r.id}
              </span>,
              <span className="table__primary" key="p">
                {r.agent_spec}
              </span>,
              <Badge variant={statusVariant(r.status)} key="s">
                {r.status}
              </Badge>,
              `${r.engine} · ${r.model}`,
              <span className="table__id" key="c">
                {r.cost_usd ? `$${r.cost_usd}` : "—"}
              </span>,
              <span className="table__id" key="w">
                {r.temporal_workflow_id}
              </span>,
              r.created_at,
            ])}
          />
        )}
      </Panel>
    </div>
  );
}

const sampleRuns: Run[] = [
  {
    id: "RUN-42",
    work_item: "WI-492",
    agent_spec: "Architecture",
    status: "gate",
    engine: "Claude",
    model: "local",
    cost_usd: "0.31",
    temporal_workflow_id: "wf-7c3a",
    started_at: null,
    ended_at: null,
    created_at: "just now",
  },
  {
    id: "RUN-41",
    work_item: "WI-492",
    agent_spec: "PRD",
    status: "done",
    engine: "Claude",
    model: "local",
    cost_usd: "0.18",
    temporal_workflow_id: "wf-6b21",
    started_at: null,
    ended_at: null,
    created_at: "1h ago",
  },
];

function statusVariant(status: string) {
  if (status === "done" || status === "completed") return "done" as const;
  if (status === "gate") return "gate" as const;
  if (status === "failed") return "failed" as const;
  if (status === "running") return "running" as const;
  return "queued" as const;
}
