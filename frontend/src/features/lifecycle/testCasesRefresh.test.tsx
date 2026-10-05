// @vitest-environment jsdom
/**
 * Bugs S.No 215 — a new test case did not appear until the page was reloaded.
 *
 * A test case IS a work item underneath, so creating one refreshed the work-items list — and never
 * the story's test-case table that was on screen. It saved; the table kept the old list; it looked
 * like a failure, and invited creating it twice. No pixel changes: the screen now simply does what
 * it already appeared to do. The same class covered two more doors: starting script generation
 * refreshed nothing, and a script finishing on the developer's machine never reached the table.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "../../test/utils";
import { TestCases } from "./TestCases";

const me = {
  user: { id: "u1", name: "Q", email: "qa@acme.test", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Checkout", role: "qa_lead" }],
};

const tc = (over: Record<string, unknown> = {}) => ({
  id: "tc9", key: "WI-9", title: "Checkout with saved card", tc_id: "TC-009", priority: "Medium",
  type: "functional", state: "proposed", automation_status: "not_automated", ...over,
});

let listReads = 0;
let writes: Array<{ url: string; body: unknown }> = [];

function stub(listFor: (read: number) => unknown[]) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    const ok = (status: number, body: unknown) =>
      ({ ok: true, status, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;
    if ((init?.method ?? "GET").toUpperCase() !== "GET") {
      writes.push({ url: u, body: JSON.parse(String(init?.body ?? "{}")) });
      return ok(201, u.includes("/trigger/") ? { run_id: "r1" } : tc());
    }
    if (u.includes("/auth/me")) return ok(200, me);
    if (u.includes("/test-cases/")) return ok(200, listFor(listReads++));
    // Generating a script runs on the user's machine, so the button is greyed when none is
    // connected. The catch-all [] below made this screen look machine-less.
    if (u.includes("/runners")) {
      return ok(200, [{ id: "r1", online: true, age_s: 3,
                        projects: [{ project_id: "p1", project_name: "Checkout" }] }]);
    }
    return ok(200, []);
  }));
}

function renderScreen() {
  return renderWithProviders(
    <Routes>
      <Route path="/work-items/:id/test-cases" element={<TestCases />} />
    </Routes>,
    { route: "/work-items/s1/test-cases" },
  );
}

beforeEach(() => {
  localStorage.setItem("selectedProjectId", "p1");
  listReads = 0;
  writes = [];
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("adding a test case", () => {
  it("shows it in the table straight away, without a reload", async () => {
    let created = false;
    stub(() => (created ? [tc()] : []));
    const user = userEvent.setup();
    renderScreen();

    await screen.findByText("No test cases yet");
    await user.click(screen.getAllByRole("button", { name: "+ Add test case" })[0]);
    await user.type(screen.getByPlaceholderText("Checkout with saved card"), "Checkout with saved card");
    created = true;
    await user.click(screen.getByRole("button", { name: "Add test case" }));

    expect(await screen.findByText("Checkout with saved card", { selector: ".table__primary" }))
      .toBeDefined();
    // ...created as a child of this story, exactly as before.
    expect(writes[0].body).toMatchObject({ type: "test_case", parent: "s1",
                                            title: "Checkout with saved card" });
  });
});

describe("script generation", () => {
  it("refreshes the row when generation is started", async () => {
    stub((read) => [tc({ automation_status: read === 0 ? "not_automated" : "generating" })]);
    const user = userEvent.setup();
    renderScreen();

    await user.click(await screen.findByRole("button", { name: "Generate script" }));
    // Generating a script is a phase run on the user's own machine, so it asks first now. Confirm
    // inside the dialog — the table's button carries the same words.
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Generate script" }));

    expect(await screen.findByText("Generating…")).toBeDefined();
  });

  it("notices when a script being generated is ready", async () => {
    stub((read) => [tc({ automation_status: read === 0 ? "generating" : "ready" })]);
    renderScreen();

    expect(await screen.findByText("Generating…")).toBeDefined();
    await waitFor(() => expect(screen.getByText("Script ready")).toBeDefined(), { timeout: 7000 });
  }, 10000);
});
