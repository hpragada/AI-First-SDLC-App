// @vitest-environment jsdom
/**
 * A test case's detail page said "No description yet" on every auto-created case.
 *
 * The steps never lived on the work item: `materialize_test_cases` copies the title and a pointer
 * to the `test_case` artifact and nothing else, so the Description panel had nothing to render.
 * The page now reads the case from the artifact it points at — a pointer, not a copy, so it
 * cannot drift when the Testing phase re-runs. Test cases only; every other type of work item
 * keeps the ordinary Description panel.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "../../test/utils";
import { WorkItemTask } from "./WorkItemTask";

const me = {
  user: { id: "u1", name: "Q", email: "qa@acme.test", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Checkout", role: "qa_lead" }],
};

const TC_BODY = "## TC-005\n\n### Test Steps\n1. Navigate to /login\n\n### Test Data\nvalid@example.com";

function stub({ workItem, preview }: { workItem: Record<string, unknown>; preview?: unknown }) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;
    if (u.includes("/auth/me")) return ok(me);
    if (u.includes("/preview/")) {
      if (preview === undefined) {
        return { ok: false, status: 404, statusText: "not found", text: async () => "{}" } as Response;
      }
      return ok(preview);
    }
    // "/lifecycle" must be matched BEFORE "/work-items/", which would otherwise swallow it.
    if (u.includes("/lifecycle")) return ok({ nodes: [], loops: [], children: [] });
    if (u.includes("/work-items/wi1")) return ok(workItem);
    return ok([]);
  }));
}

function renderScreen() {
  return renderWithProviders(
    <Routes>
      <Route path="/work-items/:id" element={<WorkItemTask />} />
    </Routes>,
    { route: "/work-items/wi1" },
  );
}

const testCase = (over: Record<string, unknown> = {}) => ({
  id: "wi1", key: "WI-99", title: "TC-005 — User Login Happy Path", project: "p1",
  feature_stream: "", type: "test_case", state: "accepted", created_at: "2026-09-01T00:00:00Z",
  description: "",
  external_ref: { tc_id: "TC-005", test_case_artifact_id: "art1" },
  ...over,
});

beforeEach(() => localStorage.setItem("selectedProjectId", "p1"));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("a test case's detail page", () => {
  it("shows the case from the artifact it points at, not 'No description yet'", async () => {
    stub({ workItem: testCase(), preview: { body: TC_BODY, content_type: "text/markdown",
                                            status: "draft", version: 1, versions: [] } });
    renderScreen();

    expect(await screen.findByText("Test case")).toBeDefined();
    expect(await screen.findByText(/Navigate to \/login/)).toBeDefined();
    expect(screen.queryByText("No description yet.")).toBeNull();
  });

  it("says so when the case cannot be read, rather than rendering nothing", async () => {
    stub({ workItem: testCase() });
    renderScreen();

    expect(await screen.findByText(/could not be read/)).toBeDefined();
  });

  it("leaves other work items on the ordinary Description panel", async () => {
    stub({ workItem: testCase({ type: "task", external_ref: null }) });
    renderScreen();

    expect(await screen.findByText("Description")).toBeDefined();
    expect(screen.queryByText("Test case")).toBeNull();
  });

  it("falls back to Description for a hand-added case, which carries its own steps", async () => {
    stub({ workItem: testCase({ description: "1. Open the app", external_ref: { tc_id: "TC-005" } }) });
    renderScreen();

    expect(await screen.findByText("Description")).toBeDefined();
    expect(screen.getByText(/Open the app/)).toBeDefined();
  });
});
