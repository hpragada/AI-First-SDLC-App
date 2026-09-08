// @vitest-environment jsdom
//
// Bugs S.No 246 — a task nobody is serving, told to the person looking at it.
//
// Temporal pins a running job to the code version that started it, for life, and says nothing
// when no worker carries that version any more. So the job reports Running, the worker reports
// healthy, and the screen shows an ordinary waiting state — while the task is dead. Twelve of
// them sat like that, the oldest for 46 days, and nobody was told.
//
// The team chose the SHAPE of the telling, and these tests are mostly about that choice rather
// than about the detection:
//
//   - On the APPROVALS screen the reviewer is not warned and not blocked. Their decision is
//     written and signalled either way, so only the timing differs — and a warning about
//     something they cannot fix, on a screen they use all day, is noise. One chip, then the
//     plain truth after they act.
//   - On the TASK screen the reader is usually the person who can restart the helper, so it
//     earns a full banner that names the next step.
//   - Both must appear only while the condition holds and disappear on their own. A notice with
//     a permanent slot on the screen is the thing the team asked us not to build.
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
          engine: "claude", model: "", status: "running", cost_usd: null,
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
    expect(screen.getByText(/Approving now will be queued/i)).toBeDefined();
    // The whole point of the team's choice: the reviewer can still decide. A disabled control
    // here would discard a real decision, because the approval lands either way.
    expect(screen.getByRole("button", { name: /^Approve/ })).toHaveProperty("disabled", false);
  });

  it("says nothing at all when the task is running normally", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stubGates([gate({ run_paused: false })]);
    renderWithProviders(<Gates />);

    await waitFor(() => expect(screen.getByRole("button", { name: /^Approve/ })).toBeDefined());
    expect(screen.queryByText("Paused")).toBeNull();
    expect(screen.queryByText(/will be queued/i)).toBeNull();
  });

  it("tells the reviewer what happened after they approve", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stubGates([gate({ run_paused: true })]);
    renderWithProviders(<Gates />);

    await waitFor(() => expect(screen.getByRole("button", { name: /^Approve/ })).toBeDefined());
    await userEvent.click(screen.getByRole("button", { name: /^Approve/ }));

    // Not "it failed", and not silence either — the decision was recorded, and the only thing
    // the reviewer needs is to know they are done.
    await waitFor(() => expect(screen.getByText(/Approved and saved/i)).toBeDefined());
    expect(screen.getByText(/nothing else for you to do/i)).toBeDefined();
  });

  it("stays quiet after approving a task that was NOT paused", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stubGates([gate({ run_paused: false })]);
    renderWithProviders(<Gates />);

    await waitFor(() => expect(screen.getByRole("button", { name: /^Approve/ })).toBeDefined());
    await userEvent.click(screen.getByRole("button", { name: /^Approve/ }));

    // The confirmation belongs to the paused case only. Shown on every approval it would be
    // one more thing to read on the screen people use most.
    await waitFor(() =>
      expect(screen.queryByText(/Approved and saved/i)).toBeNull());
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

  it("explains the stop and offers the way out", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stubRun({ worker_stalled: STALLED });
    renderConsole();

    await waitFor(() =>
      expect(screen.getByText(/won't start again on its own/i)).toBeDefined());
    // Written for whoever is looking, not for whoever will fix it.
    expect(screen.getByText(/None of the work so far is lost/i)).toBeDefined();
    expect(screen.getByRole("button", { name: /Take over this task/i })).toBeDefined();
    // The version numbers still exist — behind a disclosure, for the person who needs them.
    expect(screen.getByText(/Technical details/i)).toBeDefined();
  });

  it("shows nothing when the run is healthy", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stubRun({});
    renderConsole();

    await waitFor(() => expect(screen.getByText(/Implementation/i)).toBeDefined());
    expect(screen.queryByText(/won't start again on its own/i)).toBeNull();
  });

  it("closes itself once the run is being served again", async () => {
    // The recovery case, and the team's rule for every notice in this batch: it must go away
    // because the problem went away, not because somebody dismissed it. The reconciler REMOVES
    // the field rather than setting it false, so an empty outputs is the resolved state.
    localStorage.setItem("selectedProjectId", "p1");
    stubRun({ worker_stalled: STALLED });
    const { unmount } = renderConsole();
    await waitFor(() =>
      expect(screen.getByText(/won't start again on its own/i)).toBeDefined());
    unmount();
    cleanup();

    stubRun({});
    renderConsole();

    await waitFor(() => expect(screen.getByText(/Implementation/i)).toBeDefined());
    expect(screen.queryByText(/won't start again on its own/i)).toBeNull();
  });
});
