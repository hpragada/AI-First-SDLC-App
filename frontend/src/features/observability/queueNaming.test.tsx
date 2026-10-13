// @vitest-environment jsdom
/**
 * P2 — the dashboard's personal queue named its work by database id.
 *
 * Rows read "Merge gate · 3f2a9c1b", "Question · 7c41de90" and "Run a90f22b4 · PRD" — on the first
 * screen a client reads each morning. Eight characters of a UUID match nothing they can search
 * for, quote in a meeting or recognise anywhere else in the product, and the run row printed one
 * twice: its own, and its work item's. The rows now carry the work item's number and title, and
 * the run row spends that space on how long the run has been going instead.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";

import { renderWithProviders } from "../../test/utils";
import { Dashboard } from "./Dashboard";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "SpendLog", role: "reviewer" }],
};

const WI = "3f2a9c1b-1111-2222-3333-444455556666";
const RUN = "a90f22b4-9999-8888-7777-666655554444";

const ROLLUP = {
  needs_me: {
    gates: [{
      approval_id: "ap1", gate: "merge", work_item: WI, role: "reviewer",
      work_item_key: "WI-158", work_item_title: "ExpenseResponse missing created_at",
    }],
    clarifications: [{
      id: "c1", work_item: WI, question: "Which currency for refunds?", waiting_s: 3600,
      work_item_key: "WI-152", work_item_title: "Currency rounding rule",
    }],
    my_runs: [{
      run_id: RUN, phase: "03_prd", work_item: WI, status: "running",
      work_item_key: "WI-152", work_item_title: "Currency rounding rule", started_s: 380,
    }],
    counts: { gates: 1, clarifications: 1, my_runs: 1 },
  },
  health: { work_items: 4, phases_in_progress: 1, awaiting_gate: 1, published_week: 0 },
  recent_publishes: [],
};

function stub(rollup: unknown = ROLLUP) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;
    if (u.includes("/auth/me")) return ok(me);
    if (u.includes("/dashboard/")) return ok(rollup);
    return ok([]);
  }));
}

beforeEach(() => localStorage.setItem("selectedProjectId", "p1"));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("every row in the queue", () => {
  it("names its work item by number and title", async () => {
    stub();
    renderWithProviders(<Dashboard />);

    await waitFor(() => expect(screen.getByText(/WI-158/)).toBeDefined());
    expect(screen.getByText(/Merge gate · WI-158 ExpenseResponse missing created_at/)).toBeDefined();
    expect(screen.getByText(/Question · WI-152 Currency rounding rule/)).toBeDefined();
    expect(screen.getByText(/PRD run · WI-152 Currency rounding rule/)).toBeDefined();
  });

  it("prints no fragment of an internal id anywhere", async () => {
    stub();
    renderWithProviders(<Dashboard />);

    await waitFor(() => expect(screen.getByText(/WI-158/)).toBeDefined());
    expect(document.body.textContent).not.toContain("3f2a9c1b");
    expect(document.body.textContent).not.toContain("a90f22b4");
  });

  it("tells you how long a run has been going, in place of its id", async () => {
    stub();
    renderWithProviders(<Dashboard />);

    // 380 seconds — the reader wants "6 minutes", not "a90f22b4".
    expect(await screen.findByText(/started 6m ago · Running/)).toBeDefined();
  });

  it("says 'just started' rather than '0m ago'", async () => {
    stub({
      ...ROLLUP,
      needs_me: {
        ...ROLLUP.needs_me,
        my_runs: [{ ...ROLLUP.needs_me.my_runs[0], started_s: 12 }],
      },
    });
    renderWithProviders(<Dashboard />);

    expect(await screen.findByText(/just started · Running/)).toBeDefined();
  });

  it("carries no name rather than an unreadable one, against an older API", async () => {
    stub({
      ...ROLLUP,
      needs_me: {
        ...ROLLUP.needs_me,
        gates: [{ approval_id: "ap1", gate: "merge", work_item: WI, role: "reviewer" }],
        clarifications: [],
        my_runs: [],
        counts: { gates: 1, clarifications: 0, my_runs: 0 },
      },
    });
    renderWithProviders(<Dashboard />);

    await waitFor(() => expect(screen.getByText(/Merge gate · a work item/)).toBeDefined());
    expect(document.body.textContent).not.toContain("3f2a9c1b");
  });
});
