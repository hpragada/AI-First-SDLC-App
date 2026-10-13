// @vitest-environment jsdom
/**
 * Nothing starts a phase run without asking first.
 *
 * Six places in the app could trigger a phase. **Four asked nothing at all**, and the two that did
 * ask only asked when the phase had run before — so a first-ever trigger fired on a single click,
 * everywhere. Each one dispatches work to the user's own machine for several minutes.
 *
 * There is a test per site rather than one test for the dialog, on purpose. Asking inconsistently is
 * worse than not asking: it teaches people that the absence of a dialog means the action is small,
 * and the next person to add a trigger copies whichever example they happen to open.
 *
 * The re-run warnings that already existed are part of the contract and are pinned here too — they
 * were ADDED to the question, not replaced by it.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "../../test/utils";
import { PhasesAndRuns } from "./PhasesAndRuns";
import { WorkItemDefect } from "./WorkItemDefect";
import { WorkItemTask } from "./WorkItemTask";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "tech_lead" }],
};

const card = (over: Record<string, unknown> = {}) => ({
  id: "wi-1", key: "WI-1", number: 1, project: "p1", feature_stream: "",
  type: "task", state: "in_progress", created_at: "2026-09-01T00:00:00Z",
  title: "Export to CSV", current_phase: "07_implementation", artifact_count: 0,
  ...over,
});

const triggered: Array<{ url: string; body: unknown }> = [];

/** A connected machine for project p1, which every trigger on these screens now requires: the
 *  buttons grey themselves when the companion for the work item's project is offline, so a stub
 *  without this describes a machine-less workspace where nothing can start. `projects` is what
 *  makes it count — status is scoped to the project on screen. */
const CONNECTED_MACHINE = [{
  id: "r1", machine: "Dev laptop", online: true, age_s: 3, last_seen: "2026-10-05T09:00:00Z",
  projects: [{ project_id: "p1", project_name: "Platform" }],
}];

/** Reads resolve by URL substring in insertion order, so a specific key like "/lifecycle" must be
 *  listed BEFORE "/work-items/". Writes are recorded and answered 200. */
function stub(routes: Record<string, unknown>) {
  triggered.length = 0;
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;
    if ((init?.method ?? "GET").toUpperCase() !== "GET") {
      if (u.includes("/trigger/")) {
        triggered.push({ url: u, body: JSON.parse(String(init?.body ?? "{}")) });
        return ok({ run_id: "run-new", workflow_id: "wf" });
      }
      return ok({ ok: true });
    }
    if (u.includes("/auth/me")) return ok(me);
    // Answered before the caller's routes only as a DEFAULT — a test that passes its own
    // "/runners" wins, which is how the offline cases below say so.
    if (u.includes("/runners") && !("/runners" in routes)) return ok(CONNECTED_MACHINE);
    for (const [needle, value] of Object.entries(routes)) {
      if (u.includes(needle)) return ok(value);
    }
    return ok([]);
  }));
}

const renderAt = (element: React.ReactElement) =>
  renderWithProviders(
    <Routes>
      <Route path="/work-items/:id" element={element} />
    </Routes>,
    { route: "/work-items/wi-1" },
  );

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

// ── Phases & Runs: the first-ever trigger used to fire on one click ──
describe("Phases & Runs", () => {
  const PHASES_STUB = {
    "/phases": { plan: [], build: [], remediation: [] },
    "/runs": [],
    "/work-items": [card({ id: "wi-1", key: "WI-159", title: "Login times out" })],
  };

  beforeEach(() => {
    localStorage.setItem("selectedProjectId", "p1");
    localStorage.setItem("selectedWorkItemId", "wi-1");
  });

  /** The screen ignores a trigger until its work item has loaded, so every test here waits for the
   *  name to appear first — clicking sooner silently does nothing and would pass a weaker test. */
  async function openTaskBreakdown() {
    const user = userEvent.setup();
    renderWithProviders(<PhasesAndRuns />);
    await waitFor(() => expect(screen.getAllByText(/WI-159 · Login times out/).length)
      .toBeGreaterThan(0));
    await user.click(screen.getByRole("button", { name: /Task Breakdown/ }));
    return { user, dialog: await screen.findByRole("dialog") };
  }

  it("asks before starting a phase that has never run", async () => {
    stub(PHASES_STUB);
    const { dialog } = await openTaskBreakdown();
    expect(within(dialog).getByText(/on your companion/i)).toBeTruthy();
    expect(triggered).toHaveLength(0);
  });

  it("starts nothing when the question is declined", async () => {
    stub(PHASES_STUB);
    const { user, dialog } = await openTaskBreakdown();
    await user.click(within(dialog).getByRole("button", { name: "Not now" }));
    expect(triggered).toHaveLength(0);
  });

  it("starts the phase once confirmed", async () => {
    stub(PHASES_STUB);
    const { user, dialog } = await openTaskBreakdown();
    await user.click(within(dialog).getByRole("button", { name: "Start phase" }));
    await waitFor(() => expect(triggered).toHaveLength(1));
  });

  it("still warns that a re-run replaces the last result", async () => {
    // The warning predates this change and is the one thing a person re-running a phase must know.
    stub({ ...PHASES_STUB, "/runs": [{
      id: "r0", work_item: "wi-1", agent_key: "06_task_breakdown", status: "completed",
      agent_spec: "s", agent_phase: "Task Breakdown", engine: "claude", model: "",
      cost_usd: null, temporal_workflow_id: "", started_at: null, ended_at: null,
      created_at: "2026-10-01T00:00:00Z",
    }] });
    const { dialog } = await openTaskBreakdown();
    expect(within(dialog).getByText(/replaces this phase/i)).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "Re-run phase" })).toBeTruthy();
  });
});

// ── the work-item screens ───────────────────────────────────────────
describe("a task", () => {
  it("asks before building, and builds nothing if declined", async () => {
    stub({ "/lifecycle": { nodes: [], loops: [], children: [] }, "/work-items/": card() });
    const user = userEvent.setup();
    renderAt(<WorkItemTask />);
    await waitFor(() => expect(screen.getByText("Export to CSV")).toBeDefined());

    await user.click(screen.getByRole("button", { name: /Trigger phase/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/opens a pull request for review/i)).toBeTruthy();
    expect(triggered).toHaveLength(0);

    await user.click(within(dialog).getByRole("button", { name: "Not now" }));
    expect(triggered).toHaveLength(0);
  });

  it("builds once confirmed", async () => {
    stub({ "/lifecycle": { nodes: [], loops: [], children: [] }, "/work-items/": card() });
    const user = userEvent.setup();
    renderAt(<WorkItemTask />);
    await waitFor(() => expect(screen.getByText("Export to CSV")).toBeDefined());
    await user.click(screen.getByRole("button", { name: /Trigger phase/ }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Start phase" }));

    await waitFor(() => expect(triggered).toHaveLength(1));
  });
});

describe("a defect", () => {
  const DEFECT_STUB = {
    "/lifecycle": { nodes: [], loops: [], children: [] },
    "/work-items/": card({ type: "defect", title: "Flaky login test" }),
  };

  it("asks before starting the fix", async () => {
    // This one had no confirmation of ANY kind — one click dispatched a build.
    stub(DEFECT_STUB);
    const user = userEvent.setup();
    renderAt(<WorkItemDefect />);
    await waitFor(() => expect(screen.getByText("Flaky login test")).toBeDefined());

    await user.click(screen.getByRole("button", { name: /Trigger Fix/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Start fix" })).toBeTruthy();
    expect(triggered).toHaveLength(0);
  });

  it("starts the fix once confirmed", async () => {
    stub(DEFECT_STUB);
    const user = userEvent.setup();
    renderAt(<WorkItemDefect />);
    await waitFor(() => expect(screen.getByText("Flaky login test")).toBeDefined());
    await user.click(screen.getByRole("button", { name: /Trigger Fix/ }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Start fix" }));

    await waitFor(() => expect(triggered).toHaveLength(1));
  });
});
