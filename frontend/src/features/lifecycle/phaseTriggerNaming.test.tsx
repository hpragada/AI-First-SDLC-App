// @vitest-environment jsdom
/**
 * P1 — one work item, three different names on one screen.
 *
 * The picker called it "WI-159". The line under it, above the phase buttons, called the same item
 * "3f2a9c1b" — the first eight characters of its internal id, a string that appears nowhere else
 * a user can see. The Runs panel called it neither, showing the bare title. All three now read
 * "WI-159 · title"; an item with no number falls back to its title, never to the id.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";

import { renderWithProviders } from "../../test/utils";
import { PhasesAndRuns } from "./PhasesAndRuns";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "SpendLog", role: "product_owner" }],
};

const WI = "3f2a9c1b-1111-2222-3333-444455556666";
const TITLE = "PaginatedExpenses.total_pages conflicts with API spec field name pages";

const workItem = (over: Record<string, unknown> = {}) => ({
  id: WI, key: "WI-159", number: 159, project: "p1", type: "defect", state: "in_progress",
  title: TITLE, created_at: "2026-09-01T00:00:00Z", ...over,
});

function stub(items: unknown[] = [workItem()]) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;
    if (u.includes("/auth/me")) return ok(me);
    if (u.includes("/work-items")) return ok(items);
    if (u.includes("/phases")) return ok({ plan: [], build: [], remediation: [] });
    // `online` is the flag the screen reads; without it the whole panel renders its offline
    // state, which has no work-item line at all.
    // Scoped companion status needs the row to name its project (see hooks.ts).
    if (u.includes("/runners")) return ok([{ id: "r1", online: true, age_s: 3,
      projects: [{ project_id: "p1", project_name: "SpendLog" }] }]);
    return ok([]);
  }));
}

beforeEach(() => {
  localStorage.setItem("selectedProjectId", "p1");
  localStorage.setItem("selectedWorkItemId", WI);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("the line above the phase buttons", () => {
  it("names the work item by its number, as the picker does", async () => {
    stub();
    renderWithProviders(<PhasesAndRuns />);

    await waitFor(() => expect(screen.getByText(`All phases — WI-159 · ${TITLE}`)).toBeDefined());
  });

  it("prints no fragment of the internal id anywhere on the screen", async () => {
    stub();
    renderWithProviders(<PhasesAndRuns />);

    await waitFor(() => expect(screen.getByText(/All phases — WI-159/)).toBeDefined());
    expect(document.body.textContent).not.toContain("3f2a9c1b");
  });

  it("falls back to the title alone for an item with no number — never to the id", async () => {
    stub([workItem({ key: "", number: null })]);
    renderWithProviders(<PhasesAndRuns />);

    await waitFor(() => expect(screen.getByText(`All phases — ${TITLE}`)).toBeDefined());
    expect(document.body.textContent).not.toContain("3f2a9c1b");
  });
});
