// @vitest-environment jsdom
/**
 * Screen Words group 9, Option A (2026-09-21) — a story is a planning item.
 *
 * The spec said a story belonged on the build rail; the code put it on the plan rail. The team
 * chose the code: a story opens the planning screen, with its children, and the rail headings
 * stop saying "tier" (internal vocabulary). A task still opens the delivery screen.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "../../test/utils";
import { WorkItemDetail } from "./WorkItemDetail";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "tech_lead" }],
};

function stubItem(type: string) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;
    if (u.includes("/auth/me")) return ok(me);
    if (u.includes("/lifecycle")) return ok({ nodes: [], loops: [], children: [] });
    if (u.includes("/work-items/wi-1")) {
      return ok({ id: "wi-1", key: "ST-14", number: 14, project: "p1", feature_stream: "",
                  type, state: "in_progress", title: "Round to the nearest minor unit",
                  created_at: "2026-09-01T00:00:00Z" });
    }
    return ok([]);
  }));
}

const renderDetail = () =>
  renderWithProviders(
    <Routes>
      <Route path="/work-items/:id" element={<WorkItemDetail />} />
    </Routes>,
    { route: "/work-items/wi-1" },
  );

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("where a work item's rail belongs", () => {
  it("opens a story on the planning screen", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stubItem("story");
    renderDetail();
    expect((await screen.findAllByText("Lifecycle — Planning")).length).toBeGreaterThan(0);
    expect(screen.queryByText("Lifecycle — Delivery")).toBeNull();
    expect(screen.queryByText(/tier/i)).toBeNull();
  });

  it("opens a task on the delivery screen", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stubItem("task");
    renderDetail();
    expect((await screen.findAllByText("Lifecycle — Delivery")).length).toBeGreaterThan(0);
    expect(screen.queryByText("Lifecycle — Planning")).toBeNull();
    expect(screen.queryByText(/tier/i)).toBeNull();
  });
});
