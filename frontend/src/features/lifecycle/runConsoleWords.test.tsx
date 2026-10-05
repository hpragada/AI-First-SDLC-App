// @vitest-environment jsdom
/**
 * What the run console shows, as opposed to what it says — Section 4, the message sweep.
 *
 * The WORDING is the server's: one sentence per event action, in `EVENT_SENTENCES`
 * (`backend/api/serializers.py`), guarded by `backend/tests/test_event_wording.py`. It lives there
 * on purpose, and the first test below is the reason — the console must print the sentence it is
 * given and never compose one of its own, or the two ends drift and the guard stops meaning
 * anything. This is the same lesson as `previewable` on the artifact registry.
 *
 * The second is the Run ID coming off the page (2026-10-05). The earlier pass removed the raw
 * workflow id and kept a short labelled one; looking again, the work item's key and the phase in
 * the heading already name this run in words, so the id was the last machine string on the screen.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "../../test/utils";
import { RunConsole } from "./RunConsole";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "admin" }],
};

/** Lines exactly as the server now renders them, including the two that carry a tail. */
const EVENTS = [
  { id: "e1", target_type: "run", target_id: "run-1", kind: "info", ts: "2026-10-05T06:00:00Z",
    message: "Started — on your machine" },
  { id: "e2", target_type: "run", target_id: "run-1", kind: "info", ts: "2026-10-05T06:00:01Z",
    message: "Sent to your machine" },
  { id: "e3", target_type: "run", target_id: "run-1", kind: "ok", ts: "2026-10-05T06:10:00Z",
    message: "Your machine reported back" },
  { id: "e4", target_type: "run", target_id: "run-1", kind: "err", ts: "2026-10-05T06:11:00Z",
    message: "Build stopped — Claude usage limit reached" },
];

function stub(events: unknown[] = EVENTS) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok",
         text: async () => JSON.stringify(body) }) as Response;
    if (u.includes("/auth/me")) return ok(me);
    if (u.includes("/events/")) return ok(events);
    if (u.includes("/runs/run-1")) {
      return ok({
        id: "run-1", work_item: "wi-1", agent_spec: "s1", agent_key: "07_implementation",
        agent_phase: "Implementation", engine: "claude", model: "claude-opus-5",
        status: "running", cost_usd: null, temporal_workflow_id: "build-run-1", outputs: {},
        started_at: "2026-10-05T06:00:00Z", ended_at: null, created_at: "2026-10-05T06:00:00Z",
      });
    }
    if (u.includes("/work-items/wi-1")) {
      return ok({ id: "wi-1", project: "p1", type: "task", title: "Login", key: "WI-265",
                  state: "in_progress" });
    }
    return ok([]);
  }));
}

const renderRun = () =>
  renderWithProviders(
    <Routes>
      <Route path="/runs/:id" element={<RunConsole />} />
    </Routes>,
    { route: "/runs/run-1" },
  );

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("the console's event lines", () => {
  it("prints the sentence the server sent, untouched", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stub();
    renderRun();

    for (const e of EVENTS) {
      expect(await screen.findByText(e.message)).toBeDefined();
    }
  });

  it("composes nothing itself — no action key is ever rendered", async () => {
    // If a future change starts building a line in TypeScript from the action, this is what
    // catches it: the payload and the action are on the row, and neither belongs on screen.
    localStorage.setItem("selectedProjectId", "p1");
    stub([{ id: "e9", target_type: "run", target_id: "run-1", kind: "warn",
            ts: "2026-10-05T06:00:00Z", action: "phase.empty_result",
            payload: { phase: "06_task_breakdown", message: "engine returned no final text" },
            message: "The agent finished without writing anything — the draft is empty" }]);
    renderRun();

    await screen.findByText("The agent finished without writing anything — the draft is empty");
    expect(screen.queryByText(/phase.empty_result/)).toBeNull();
    expect(screen.queryByText(/Phase empty result/)).toBeNull();
    expect(screen.queryByText(/06_task_breakdown/)).toBeNull();
    expect(screen.queryByText(/engine returned no final text/)).toBeNull();
  });
});

describe("what names this run on the page", () => {
  it("names the work item and the phase, and prints no run id", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stub();
    renderRun();

    // The two things that do the naming, in words.
    expect(await screen.findByText("WI-265")).toBeDefined();
    expect(screen.getAllByText(/Implementation/).length).toBeGreaterThan(0);

    expect(screen.queryByText(/Run ID/)).toBeNull();
    // Nor the id itself, under any label — including as a tooltip, which is where the second
    // printing of it used to hide.
    expect(document.body.innerHTML).not.toContain("run-1");
  });
});
