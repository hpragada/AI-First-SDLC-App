// @vitest-environment jsdom
/**
 * Bugs S.No 222 + N2 — the dashboard's "needs you" tiles, and the bell that reads them.
 *
 * 222: "Gates need your approval" and "Questions awaiting you" counted every pending gate and
 * question on the project, whoever they were for; the first tile's subtitle read the required role
 * off whichever gate came first; and both counts were the length of a list cut at 20. The server
 * now filters to the person reading and sends true totals; the team chose option A for the
 * subtitle — say how many, plainly.
 *
 * N2: the bell had a live count and no click handler. It now opens the Needs-me queue that
 * already exists, landing ON the queue rather than at the top of the page — and still opens at
 * zero, where the queue says you are all caught up.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import { AppShell } from "../../components/AppShell";
import { renderWithProviders } from "../../test/utils";
import { Dashboard } from "./Dashboard";

const me = {
  user: { id: "u1", name: "Aisha Khan", email: "aisha@acme.test", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Checkout", role: "qa_lead" }],
};

const gate = (i: number) => ({
  approval_id: `a${i}`, gate: "phase_gate", work_item: `w${i}-0000-0000`, role: "qa_lead",
});

function rollup(needsMe: Record<string, unknown>) {
  return {
    needs_me: { gates: [], clarifications: [], my_runs: [], ...needsMe },
    health: { work_items: 3, phases_in_progress: 1, awaiting_gate: 0, published_week: 0 },
    recent_publishes: [],
  };
}

function stub(dashboard: unknown) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;
    if (u.includes("/auth/me")) return ok(me);
    if (u.includes("/dashboard/")) return ok(dashboard);
    return ok([]);
  }));
}

const tile = (label: string) => screen.getByText(label).closest(".tile") as HTMLElement;

beforeEach(() => localStorage.setItem("selectedProjectId", "p1"));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("the needs-you tiles (S.No 222, option A)", () => {
  it("show the true total, not the length of a trimmed list", async () => {
    stub(rollup({
      gates: Array.from({ length: 20 }, (_, i) => gate(i)),
      my_runs: [{ run_id: "r1-aaaa", phase: "09_testing", work_item: "w1-0000", status: "running" }],
      counts: { gates: 25, clarifications: 0, my_runs: 1 },
    }));
    renderWithProviders(<Dashboard />);

    await waitFor(() => expect(screen.getByText("25 waiting on you")).toBeDefined());
    expect(within(tile("Gates need your approval")).getByText("25")).toBeDefined();
    expect(screen.getByText("26 items")).toBeDefined();         // the queue's own badge agrees
  });

  it("say how many are waiting on you, and never borrow the first gate's role", async () => {
    stub(rollup({ gates: [gate(1), gate(2)], counts: { gates: 2, clarifications: 0, my_runs: 0 } }));
    renderWithProviders(<Dashboard />);

    await waitFor(() => expect(screen.getByText("2 waiting on you")).toBeDefined());
    expect(within(tile("Gates need your approval")).queryByText(/required role/)).toBeNull();
  });

  it("say zero as a real answer", async () => {
    stub(rollup({ counts: { gates: 0, clarifications: 0, my_runs: 0 } }));
    renderWithProviders(<Dashboard />);

    await waitFor(() => expect(within(tile("Questions awaiting you"))
      .getByText("nothing waiting on you")).toBeDefined());
    expect(within(tile("Gates need your approval")).getByText("nothing waiting on you")).toBeDefined();
  });

  it("fall back to the list lengths for an API too old to send totals", async () => {
    stub(rollup({ gates: [gate(1), gate(2), gate(3)] }));
    renderWithProviders(<Dashboard />);

    await waitFor(() => expect(screen.getByText("3 waiting on you")).toBeDefined());
  });
});

describe("the bell (N2)", () => {
  function shell() {
    return renderWithProviders(
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/work-items" element={<p>The work items board</p>} />
        </Route>
      </Routes>,
      { route: "/work-items" },
    );
  }

  it("counts the same true totals the tiles do", async () => {
    stub(rollup({
      gates: Array.from({ length: 20 }, (_, i) => gate(i)),
      counts: { gates: 25, clarifications: 2, my_runs: 0 },
    }));
    shell();

    expect(await screen.findByRole("button", { name: "Notifications, 27 unread" })).toBeDefined();
  });

  it("opens the Needs-me queue and lands on it, not at the top of the page", async () => {
    stub(rollup({ gates: [gate(1)], counts: { gates: 1, clarifications: 0, my_runs: 0 } }));
    const user = userEvent.setup();
    shell();

    await user.click(await screen.findByRole("button", { name: "Notifications, 1 unread" }));

    expect(await screen.findByText("Needs me")).toBeDefined();
    expect(screen.queryByText("The work items board")).toBeNull();
    // Focus moves with it, so a keyboard or screen-reader user arrives where a sighted one does.
    await waitFor(() => expect(document.activeElement?.id).toBe("needs-me"));
  });

  it("still opens at zero, where the queue says you are all caught up", async () => {
    stub(rollup({ counts: { gates: 0, clarifications: 0, my_runs: 0 } }));
    const user = userEvent.setup();
    shell();

    await user.click(await screen.findByRole("button", { name: "Notifications, 0 unread" }));

    expect(await screen.findByText("You're all caught up")).toBeDefined();
  });
});
