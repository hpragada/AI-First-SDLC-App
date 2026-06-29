// Clarifications — the interactive Q&A surface (req #2). When a phase agent needs missing
// information it calls `ask_human` and pauses (the model is idle, so it costs nothing) while
// a pending Clarification appears here. Answering it resumes the run in the same session.
// Mirrors Gates.tsx: a 4s poll, a hand-entered user id (pre-auth), and a per-question form.
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../api";
import { useApp } from "../state";
import type { Clarification, ClarificationQuestion } from "../types";

type AnswerMap = Record<string, Record<string, string | boolean>>;

export function Clarifications() {
  const { tenantId } = useApp();
  const tid = tenantId!;
  const [pending, setPending] = useState<Clarification[]>([]);
  const [userId, setUserId] = useState("");
  const [answers, setAnswers] = useState<AnswerMap>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setPending(await api.listClarifications(tid, { status: "pending" }));
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

  function setAnswer(cid: string, qid: string, value: string | boolean) {
    setAnswers((prev) => ({ ...prev, [cid]: { ...(prev[cid] ?? {}), [qid]: value } }));
  }

  async function submit(c: Clarification) {
    if (!userId.trim()) {
      setErr("Enter your user id (must be a member of the project).");
      return;
    }
    try {
      await api.answerClarification(tid, c.id, {
        user_id: userId.trim(),
        answers: answers[c.id] ?? {},
      });
      setMsg("Answer sent — the agent will continue.");
      setErr(null);
      setAnswers((prev) => {
        const next = { ...prev };
        delete next[c.id];
        return next;
      });
      await load();
    } catch (e) {
      setMsg(null);
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  function field(c: Clarification, q: ClarificationQuestion) {
    const cur = answers[c.id]?.[q.id];
    const kind = q.kind ?? "text";
    if (kind === "confirm") {
      return (
        <label className="flex">
          <input
            type="checkbox"
            checked={Boolean(cur)}
            onChange={(e) => setAnswer(c.id, q.id, e.target.checked)}
          />
          <span className="muted">yes / confirmed</span>
        </label>
      );
    }
    if (kind === "choice") {
      return (
        <select
          value={(cur as string) ?? ""}
          onChange={(e) => setAnswer(c.id, q.id, e.target.value)}
        >
          <option value="">— choose —</option>
          {(q.options ?? []).map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      );
    }
    return (
      <input
        value={(cur as string) ?? ""}
        placeholder="your answer"
        onChange={(e) => setAnswer(c.id, q.id, e.target.value)}
      />
    );
  }

  return (
    <div className="panel">
      <h2>Clarifications</h2>
      <p className="muted">
        When an agent needs information to proceed it asks here and waits at no cost. Answer
        and the run continues — no terminal needed.
      </p>

      <div className="row">
        <div>
          <label>Your user id</label>
          <input
            className="mono"
            placeholder="uuid of a project member"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
          />
        </div>
      </div>
      {msg && <div className="ok">{msg}</div>}
      {err && <div className="err">{err}</div>}

      {pending.length === 0 ? (
        <div className="empty">No questions awaiting an answer.</div>
      ) : (
        pending.map((c) => (
          <div key={c.id} className="card">
            <div className="flex">
              <span className="badge">{c.phase || "phase"}</span>
              <span className="mono muted">run {c.run.slice(0, 8)}</span>
            </div>
            {c.context && <p>{c.context}</p>}
            {c.questions.map((q) => (
              <div key={q.id} className="field">
                <label>
                  {q.text}
                  {q.required === false ? " (optional)" : ""}
                </label>
                {field(c, q)}
              </div>
            ))}
            <button className="primary" onClick={() => void submit(c)}>
              Send answer
            </button>
          </div>
        ))
      )}
    </div>
  );
}
