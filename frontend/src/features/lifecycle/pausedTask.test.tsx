// @vitest-environment jsdom
//
// Bugs S.No 246 — a task nobody is serving, told to the person looking at it.
//
// Temporal pins a running job to the code version that started it, for life, and says nothing
// when no worker carries that version any more. So the job reports Running, the worker reports
// healthy, and the screen shows an ordinary waiting state — while the task is dead. Twelve of
// them sat like that, the oldest for 46 days, and nobody was told.
//
// REWRITTEN 8 September. The detection was right; the words were written for us. The team's rule:
// every string on screen is for the CLIENT, who did not build this and has no code to read. So
// what these tests now pin is mostly what must NOT be there — an instruction they cannot carry
// out, a button into our engine room, a disclosure holding our build stamps. What is left is the
// state on the chip and one sentence about what it means for them.
//
// Both notices must still appear only while the condition holds and disappear on their own. A
// notice with a permanent slot on the screen is the thing the team asked us not to build.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "../../test/utils";
import { Gates } from "./Gates";
import { RunConsole } from "./RunConsole";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "admin" }],
};

const gate = (over: Record<string, unknown> = {}) => ({
  id: "ap1", run: "run-1", gate_type: "merge_gate", phase: "07_implementation",
  phase_label: "implementation", work_item: "wi-1",
  work_item_title: "TASK-038 — Comp-off grant flow",
  required_role: "tech_lead", approver: null, approver_name: null,
  decision: "pending", comment: "", decided_at: null,
  created_at: "2026-09-04T00:00:00Z", merge_conflict: null, external_merge: null,
  run_paused: false,
  ...over,
});

/** What the reconciler leaves on a run while nobody serves its code version. */
const STALLED = {
  pinned_build: "20260902T075326Z-5ceff9d45ff3",
  newest_served: "20260907T143603Z-7962c1135cae",
  version_sets: 1,
  noticed_at: "2026-09-08T06:57:00Z",
};

function stubGates(approvals: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: RequestInfo | URL) => {
      const u = String(url);
      const ok = (body: unknown) =>
        ({ ok: true, status: 200, statusText: "ok",
           text: async () => JSON.stringify(body) }) as Response;
      if (u.includes("/auth/me")) return ok(me);
      if (u.includes("/decide")) return ok({ ok: true });
      if (u.includes("/approvals/")) return ok(approvals);
      return ok([]);
    }),
  );
}

function stubRun(outputs: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: RequestInfo | URL) => {
      const u = String(url);
      const ok = (body: unknown) =>
        ({ ok: true, status: 200, statusText: "ok",
           text: async () => JSON.stringify(body) }) as Response;
      if (u.includes("/auth/me")) return ok(me);
      if (u.includes("/runs/run-1")) {
        return ok({
          id: "run-1", work_item: "wi-1", agent_spec: "s1",
          agent_key: "07_implementation", agent_phase: "Implementation",
          engine: "claude", model: "", status: "stalled", cost_usd: null,
          temporal_workflow_id: "build-run-1", outputs,
          started_at: null, ended_at: null, created_at: "2026-09-07T06:42:00Z",
        });
      }
      if (u.includes("/work-items/wi-1")) {
        return ok({ id: "wi-1", project: "p1", type: "task", title: "Leave policy", state: "in_progress" });
      }
      return ok([]);
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("the approvals screen", () => {
  it("marks a paused task with one chip, and does not block the decision", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stubGates([gate({ run_paused: true })]);
    renderWithProviders(<Gates />);

    await waitFor(() => expect(screen.getByText("Paused")).toBeDefined());
    // The whole point of the team's choice: the reviewer can still decide. A disabled control
    // here would discard a real decision, because the approval lands either way.
    expect(screen.getByRole("button", { name: /^Approve/ })).toHaveProperty("disabled", false);
  });

  it("does not explain our machinery to the reviewer", async () => {
    // The chip marks the task and stops. The line that used to sit under it — "Approving now
    // will be queued — it takes effect once this task is running again" — warned about something
    // the reviewer cannot influence, in words that need our internals explained first.
    localStorage.setItem("selectedProjectId", "p1");
    stubGates([gate({ run_paused: true })]);
    renderWithProviders(<Gates />);

    await waitFor(() => expect(screen.getByText("Paused")).toBeDefined());
    expect(screen.queryByText(/will be queued/i)).toBeNull();
    expect(screen.queryByText(/running again/i)).toBeNull();
  });

  it("says nothing at all when the task is running normally", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stubGates([gate({ run_paused: false })]);
    renderWithProviders(<Gates />);

    await waitFor(() => expect(screen.getByRole("button", { name: /^Approve/ })).toBeDefined());
    expect(screen.queryByText("Paused")).toBeNull();
  });

  it("confirms the decision in one sentence, naming the gate", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stubGates([gate({ run_paused: true })]);
    renderWithProviders(<Gates />);

    await waitFor(() => expect(screen.getByRole("button", { name: /^Approve/ })).toBeDefined());
    await userEvent.click(screen.getByRole("button", { name: /^Approve/ }));

    await waitFor(() => expect(screen.getByText("Approved")).toBeDefined());
    expect(screen.getByText(/is saved/i)).toBeDefined();
    // Naming the gate is the load-bearing part — see gateSelection.test.tsx for why an
    // unnamed confirmation drifted onto the next gate in the list.
    expect(screen.getAllByText(/TASK-038/).length).toBeGreaterThan(0);
    // Gone with the rest of the explanation: whether the task happens to be running is not
    // something the reviewer needed to carry.
    expect(screen.queryByText(/nothing else for you to do/i)).toBeNull();
    expect(screen.queryByText(/carry on the moment/i)).toBeNull();
  });
});

describe("the task's own screen", () => {
  const renderConsole = () =>
    renderWithProviders(
      <Routes>
        <Route path="/runs/:id" element={<RunConsole />} />
      </Routes>,
      { route: "/runs/run-1" },
    );

  it("says the state, and what it means, in one sentence", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stubRun({ worker_stalled: STALLED });
    renderConsole();

    await waitFor(() =>
      expect(screen.getByText(/This task has stopped and will continue/i)).toBeDefined());
    // The state, in the reader's word — not "Parked for takeover".
    expect(screen.getByText("Stopped")).toBeDefined();
    expect(screen.queryByText(/parked/i)).toBeNull();
    expect(screen.queryByText(/take over/i)).toBeNull();
  });

  it("★ never puts our diagnostic equipment on the client's screen", async () => {
    // The one that pins the team's rule. The client did not build this, has no code to read, and
    // cannot restart anything — so a build stamp, a "Technical details" disclosure, and an
    // instruction to go and have our platform restarted are all worse than saying nothing. Every
    // one of them was in the version this replaces.
    localStorage.setItem("selectedProjectId", "p1");
    stubRun({ worker_stalled: STALLED });
    renderConsole();

    await waitFor(() =>
      expect(screen.getByText(/This task has stopped and will continue/i)).toBeDefined());
    expect(screen.queryByText(/Technical details/i)).toBeNull();
    expect(screen.queryByText(new RegExp(STALLED.pinned_build))).toBeNull();
    expect(screen.queryByText(new RegExp(STALLED.newest_served))).toBeNull();
    expect(screen.queryByText(/restart/i)).toBeNull();
    expect(screen.queryByText(/tech lead/i)).toBeNull();
    expect(screen.queryByText(/SDLC helper/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /take over/i })).toBeNull();
  });

  it("shows nothing when the run is healthy", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stubRun({});
    renderConsole();

    // The heading, specifically: the breadcrumb's last crumb also names the phase now that it
    // no longer prints the run's id (2026-10-05), so a loose match finds two.
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /Run console/i })).toBeDefined());
    expect(screen.queryByText(/This task has stopped/i)).toBeNull();
  });

  it("closes itself once the run is being served again", async () => {
    // The recovery case, and the team's rule for every notice in this batch: it must go away
    // because the problem went away, not because somebody dismissed it. The reconciler REMOVES
    // the field rather than setting it false, so an empty outputs is the resolved state.
    localStorage.setItem("selectedProjectId", "p1");
    stubRun({ worker_stalled: STALLED });
    const { unmount } = renderConsole();
    await waitFor(() =>
      expect(screen.getByText(/This task has stopped and will continue/i)).toBeDefined());
    unmount();
    cleanup();

    stubRun({});
    renderConsole();

    // The heading, specifically: the breadcrumb's last crumb also names the phase now that it
    // no longer prints the run's id (2026-10-05), so a loose match finds two.
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /Run console/i })).toBeDefined());
    expect(screen.queryByText(/This task has stopped/i)).toBeNull();
  });
});
