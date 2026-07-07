// Phase Console — the replacement for the legacy slash commands. Pick a work item,
// trigger a planning phase (which starts a Temporal AgentRunWorkflow server-side),
// and watch the run timeline. Gates for these runs are decided on the Gate Approvals tab.
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../api";
import { useApp } from "../state";
import { PLANNING_PHASES, type Run, type WorkItem } from "../types";
import { statusLabel } from "../features/lifecycle/phases";

// Keep the raw status as the CSS class (styling hook) but show a humanized label —
// no raw "awaiting_gate" with an underscore leaks to the user (Bugs.xlsx rows 57/58).
function StateBadge({ value }: { value: string }) {
  return <span className={`badge ${value}`}>{statusLabel(value)}</span>;
}

export function PhaseConsole() {
  const { tenantId, project } = useApp();
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [needsAnswer, setNeedsAnswer] = useState<Set<string>>(new Set());
  const [stream, setStream] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const tid = tenantId!;
  const pid = project!.id;

  const loadWorkItems = useCallback(async () => {
    try {
      const items = await api.listWorkItems(tid, pid);
      setWorkItems(items);
      setSelected((cur) => cur ?? items[0]?.id ?? null);
      setErr(null);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }, [tid, pid]);

  const loadRuns = useCallback(async () => {
    if (!selected) {
      setRuns([]);
      setNeedsAnswer(new Set());
      return;
    }
    try {
      const [runList, pending] = await Promise.all([
        api.listRuns(tid, { work_item: selected }),
        api.listClarifications(tid, { status: "pending", work_item: selected }),
      ]);
      setRuns(runList);
      setNeedsAnswer(new Set(pending.map((c) => c.run)));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }, [tid, selected]);

  useEffect(() => {
    void loadWorkItems();
  }, [loadWorkItems]);

  // Poll the run timeline so status moves (running → awaiting_gate → completed) show up.
  useEffect(() => {
    void loadRuns();
    const h = setInterval(() => void loadRuns(), 4000);
    return () => clearInterval(h);
  }, [loadRuns]);

  async function addWorkItem() {
    try {
      const wi = await api.createWorkItem(tid, pid, {
        type: "story",
        feature_stream: stream.trim(),
      });
      setStream("");
      await loadWorkItems();
      setSelected(wi.id);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function trigger(agentKey: string) {
    if (!selected) return;
    setBusy(true);
    try {
      await api.triggerPhase(tid, selected, agentKey);
      setErr(null);
      await loadRuns();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="panel">
        <h2>Work Items</h2>
        <div className="row">
          <select value={selected ?? ""} onChange={(e) => setSelected(e.target.value || null)}>
            <option value="">— select work item —</option>
            {workItems.map((w) => (
              <option key={w.id} value={w.id}>
                {w.feature_stream || w.id.slice(0, 8)} · {w.type} · {statusLabel(w.state)}
              </option>
            ))}
          </select>
          <input
            placeholder="New work item (feature stream)"
            value={stream}
            onChange={(e) => setStream(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void addWorkItem()}
          />
          <button className="primary" onClick={() => void addWorkItem()}>
            Add
          </button>
        </div>

        <h3>Trigger phase</h3>
        <div className="flex">
          {PLANNING_PHASES.map((ph) => (
            <button
              key={ph.key}
              className="ghost"
              disabled={!selected || busy}
              onClick={() => void trigger(ph.key)}
              title={ph.key}
            >
              ▶ {ph.label}
            </button>
          ))}
        </div>
        {err && <div className="err">{err}</div>}
      </div>

      <div className="panel">
        <h2>Run Timeline</h2>
        {runs.length === 0 ? (
          <div className="empty">No runs yet for this work item.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Status</th>
                <th>Engine / Model</th>
                <th>Cost (USD)</th>
                <th>Workflow</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.id.slice(0, 8)}</td>
                  <td>
                    <StateBadge value={r.status} />
                    {needsAnswer.has(r.id) && (
                      <span className="badge" title="An agent is waiting for an answer on the Clarifications tab">
                        ● needs answer
                      </span>
                    )}
                  </td>
                  <td className="muted">
                    {r.engine}
                    {r.model ? ` / ${r.model}` : ""}
                  </td>
                  <td className="mono">{r.cost_usd ?? "—"}</td>
                  <td className="mono">{r.temporal_workflow_id || "—"}</td>
                  <td className="muted">{new Date(r.created_at).toLocaleTimeString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
