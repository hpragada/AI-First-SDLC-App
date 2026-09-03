// Gate Approvals — the control-plane gate (#2/#5). A pending Approval blocks the
// Temporal workflow on the `gate_decision` signal; deciding here records the decision
// and resumes the run. Only a user holding the gate's required Membership role may
// decide (server-enforced) — pre-auth, the approver's user id is entered by hand.
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../api";
import { useApp } from "../state";
import type { Approval } from "../types";

export function Gates() {
  const { tenantId } = useApp();
  const tid = tenantId!;
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [userId, setUserId] = useState("");
  const [comment, setComment] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setApprovals(await api.listApprovals(tid));
      setErr(null);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }, [tid]);

  useEffect(() => {
    void load();
    const h = setInterval(() => void load(), 4000);
    return () => clearInterval(h);
  }, [load]);

  async function decide(id: string, decision: "approved" | "rejected") {
    if (!userId.trim()) {
      setErr("Enter the approver's user id (must hold the gate's required role).");
      return;
    }
    try {
      await api.decideApproval(tid, id, {
        user_id: userId.trim(),
        decision,
        comment: comment.trim(),
      });
      setMsg(`Gate ${decision}.`);
      setErr(null);
      setComment("");
      await load();
    } catch (e) {
      setMsg(null);
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  const pending = approvals.filter((a) => a.decision === "pending");
  const decided = approvals.filter((a) => a.decision !== "pending");

  return (
    <div className="panel">
      <h2>Gate Approvals</h2>

      <div className="row">
        <div>
          <label>Approver user id</label>
          <input
            className="mono"
            placeholder="uuid of a user with the required role"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
          />
        </div>
        <div className="grow">
          <label>Comment (optional)</label>
          <input value={comment} onChange={(e) => setComment(e.target.value)} />
        </div>
      </div>
      {msg && <div className="ok">{msg}</div>}
      {err && <div className="err">{err}</div>}

      <h3>Pending</h3>
      {pending.length === 0 ? (
        <div className="empty">No gates awaiting a decision.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Approval</th>
              <th>Gate</th>
              <th>Required role</th>
              <th>Run</th>
              <th>Decision</th>
            </tr>
          </thead>
          <tbody>
            {pending.map((a) => (
              <tr key={a.id}>
                <td className="mono">{a.id.slice(0, 8)}</td>
                <td>{a.gate_type}</td>
                <td>
                  <span className="badge">{a.required_role}</span>
                </td>
                <td className="mono">{a.run.slice(0, 8)}</td>
                <td className="flex">
                  <button className="primary" onClick={() => void decide(a.id, "approved")}>
                    Approve
                  </button>
                  <button className="ghost" onClick={() => void decide(a.id, "rejected")}>
                    Reject
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>Decided</h3>
      {decided.length === 0 ? (
        <div className="empty">None yet.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Approval</th>
              <th>Required role</th>
              <th>Decision</th>
              <th>Comment</th>
            </tr>
          </thead>
          <tbody>
            {decided.map((a) => (
              <tr key={a.id}>
                <td className="mono">{a.id.slice(0, 8)}</td>
                <td className="muted">{a.required_role}</td>
                <td>
                  <span className={`badge ${a.decision}`}>{a.decision}</span>
                </td>
                <td className="muted">{a.comment || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
