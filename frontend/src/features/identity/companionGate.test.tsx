// @vitest-environment jsdom
/**
 * Not offering work that cannot start, and saying when a machine drops.
 *
 * Three screens offered a trigger without checking whether a machine was there — a task's
 * Implementation, a defect's Fix, and a test case's Generate script. Phases & Runs did check, so
 * the same click was refused on one screen and accepted on three, and the three dispatched into
 * a run nobody would ever claim. All four now read one hook.
 *
 * Kept in its own file rather than folded into `triggerConfirm.test.tsx`: that file is about the
 * confirmation dialog, which is a different question (does it ASK before starting) from this one
 * (does it OFFER to start at all). Its own stubs now default to a connected machine so it keeps
 * testing what it was written for.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "../../test/utils";
import { CompanionDropBanner } from "./CompanionDropBanner";
import { TestCases } from "../lifecycle/TestCases";
import { WorkItemDefect } from "../lifecycle/WorkItemDefect";
import { WorkItemTask } from "../lifecycle/WorkItemTask";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "tech_lead" }],
};

const machine = (over: Record<string, unknown> = {}) => [{
  id: "r1", machine: "Dev laptop", online: true, age_s: 3, last_seen: "2026-10-05T09:00:00Z",
  projects: [{ project_id: "p1", project_name: "Platform" }], ...over,
}];
const CONNECTED = machine();
const DROPPED = machine({ online: false, age_s: 600 });
const NEVER_CONNECTED = machine({ online: false, age_s: undefined, last_seen: null });

const item = (over: Record<string, unknown> = {}) => ({
  id: "wi-1", key: "WI-1", number: 1, project: "p1", feature_stream: "",
  type: "task", state: "in_progress", created_at: "2026-09-01T00:00:00Z",
  title: "Export to CSV", current_phase: "07_implementation", artifact_count: 0, ...over,
});

const testCase = {
  id: "tc9", key: "WI-9", title: "Checkout with saved card", tc_id: "TC-009",
  priority: "Medium", type: "functional", state: "proposed", automation_status: "not_automated",
};

function stub(runners: unknown[], over: Record<string, unknown> = {}) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok",
         text: async () => JSON.stringify(body) }) as Response;
    if (u.includes("/auth/me")) return ok(me);
    if (u.includes("/runners")) return ok(runners);
    for (const [needle, value] of Object.entries(over)) {
      if (u.includes(needle)) return ok(value);
    }
    if (u.includes("/lifecycle")) return ok({ nodes: [], loops: [], children: [] });
    if (u.includes("/test-cases/")) return ok([testCase]);
    if (u.includes("/work-items/")) return ok(item());
    return ok([]);
  }));
}

const renderItem = (element: React.ReactElement, route = "/work-items/wi-1") =>
  renderWithProviders(
    <Routes>
      <Route path="/work-items/:id" element={element} />
      <Route path="/work-items/:id/test-cases" element={element} />
    </Routes>,
    { route },
  );

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

const REASON = /Your machine isn't connected, so this can't start yet/i;

describe("a trigger is not offered when there is no machine to run it on", () => {
  it("greys the task's Implementation trigger and says why", async () => {
    stub(DROPPED);
    renderItem(<WorkItemTask />);
    const button = await screen.findByRole("button", { name: /Trigger phase/ });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    // Disabled alone is a dead end: a control that stops working without saying why is the
    // shape of bug this sweep exists to remove.
    expect(screen.getByText(REASON)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Reconnect your machine/i })).toBeTruthy();
  });

  it("greys the defect's Fix trigger and says why", async () => {
    stub(DROPPED, { "/work-items/": item({ type: "defect", title: "Flaky login test" }) });
    renderItem(<WorkItemDefect />);
    const button = await screen.findByRole("button", { name: /Trigger Fix/ });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(REASON)).toBeTruthy();
  });

  it("greys Generate script on a test case and says why", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stub(DROPPED);
    renderItem(<TestCases />, "/work-items/s1/test-cases");
    const button = await screen.findByRole("button", { name: /Generate script/ });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(REASON)).toBeTruthy();
  });

  it("offers all of them again once the machine is back", async () => {
    // The half that matters more. A guard that also blocks healthy work is not a fix, and this
    // is the assertion that would catch it.
    stub(CONNECTED);
    renderItem(<WorkItemTask />);
    const button = await screen.findByRole("button", { name: /Trigger phase/ });
    expect((button as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText(REASON)).toBeNull();
  });

  it("says CONNECT, not RE-connect, when no machine was ever set up", async () => {
    // Identical to a drop by "is it online", opposite in what to tell somebody. Sending a brand
    // new user to re-connect something they never connected is its own small dead end.
    stub(NEVER_CONNECTED);
    renderItem(<WorkItemTask />);
    await screen.findByRole("button", { name: /Trigger phase/ });
    expect(screen.getByText(/You haven't connected a machine yet/i)).toBeTruthy();
    expect(screen.getByRole("link", { name: /^Connect your machine ↗$/ })).toBeTruthy();
  });
});

describe("a badge does not claim a machine is working when it isn't", () => {
  const strandedRun = [{
    id: "run-1", work_item: "wi-1", agent_spec: "s1", agent_key: "07_implementation",
    agent_phase: "Implementation", engine: "claude", model: "claude-opus-5",
    // RUNNING with an unclaimed dispatch: the state a phase sent to a dead machine sits in.
    status: "running", cost_usd: null, temporal_workflow_id: "build-run-1",
    inputs: { dispatch: { status: "pending" } }, outputs: {},
    started_at: null, ended_at: null, created_at: "2026-10-05T09:00:00Z",
  }];

  it("says the task is waiting for the machine, not running on it", async () => {
    stub(DROPPED, { "/runs": strandedRun });
    renderItem(<WorkItemTask />);
    await waitFor(() => expect(screen.getByText(/Waiting for your machine/i)).toBeTruthy());
    expect(screen.queryByText(/Running on your companion/i)).toBeNull();
  });

  it("still says running on your companion when the machine is actually there", async () => {
    stub(CONNECTED, { "/runs": strandedRun });
    renderItem(<WorkItemTask />);
    await waitFor(() => expect(screen.getByText(/Running on your companion/i)).toBeTruthy());
  });
});

// ── The banner that interrupts, and the silence that matters more ──────────
function runRow(over: Record<string, unknown> = {}) {
  return {
    id: "run-1", work_item: "wi-1", agent_spec: "s1", agent_key: "01_ideation",
    agent_phase: "Ideation", engine: "claude", model: "claude-opus-5", status: "running",
    cost_usd: null, temporal_workflow_id: "agent-run-1",
    inputs: { dispatch: { status: "pending" } }, outputs: {},
    started_at: null, ended_at: null, created_at: "2026-10-05T09:00:00Z", ...over,
  };
}

// Through the real providers: the banner reads the project's runs, and that query needs the
// tenant from AuthContext to send its header at all.
function showBanner(runs: unknown[]) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok",
         text: async () => JSON.stringify(body) }) as Response;
    return String(url).includes("/auth/me") ? ok(me) : ok(runs);
  }));
  return renderWithProviders(<CompanionDropBanner projectId="p1" everConnected />);
}

describe("telling somebody their machine dropped", () => {
  it("interrupts when a phase is actually left waiting", async () => {
    showBanner([runRow()]);
    await waitFor(() =>
      expect(screen.getByText(/Your machine stopped responding/i)).toBeTruthy());
    expect(screen.getByText(/Ideation hasn't started/i)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Reconnect your machine/i })).toBeTruthy();
  });

  it("stays silent when nothing is waiting", async () => {
    // The condition that keeps this worth reading. A laptop closed overnight with no pending
    // work has caused no problem, and a banner that fired every time it happened would be
    // dismissed unread by the week it mattered.
    const { container } = showBanner([]);
    await waitFor(() => expect(container.innerHTML).toBe(""));
  });

  it("stays silent when the work was already claimed", async () => {
    const { container } = showBanner([runRow({ inputs: { dispatch: { status: "claimed" } } })]);
    await waitFor(() => expect(container.innerHTML).toBe(""));
  });

  it("counts them when several are waiting, rather than naming one", async () => {
    showBanner([runRow(), runRow({ id: "run-2" })]);
    await waitFor(() => expect(screen.getByText(/2 phases haven't started/i)).toBeTruthy());
  });

  it("names the phase but never an id", async () => {
    const { container } = showBanner([runRow()]);
    await waitFor(() =>
      expect(screen.getByText(/Your machine stopped responding/i)).toBeTruthy());
    // The run id appears in the "Open the run" href, which is a link target and not words on
    // the screen — so the TEXT is what is checked here.
    expect(container.textContent).not.toContain("run-1");
    expect(container.textContent).not.toContain("wi-1");
    expect(container.textContent).not.toContain("01_ideation");
  });

  it("can be dismissed, and stays dismissed for the session", async () => {
    showBanner([runRow()]);
    await waitFor(() =>
      expect(screen.getByText(/Your machine stopped responding/i)).toBeTruthy());
    screen.getByRole("button", { name: "Dismiss" }).click();
    await waitFor(() =>
      expect(screen.queryByText(/Your machine stopped responding/i)).toBeNull());

    cleanup();
    const { container } = showBanner([runRow()]);
    await waitFor(() => expect(container.innerHTML).toBe(""));
    sessionStorage.clear();
  });
});
