// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";

import { renderWithProviders } from "../test/utils";
import { AppShell } from "./AppShell";

const me = {
  user: { id: "u1", name: "Ada Lovelace", email: "ada@acme.test", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme Corp" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "developer" }],
};

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status < 400,
    status,
    statusText: "stub",
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

let logoutCalls: { method?: string }[] = [];

beforeEach(() => {
  logoutCalls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: RequestInfo | URL, opts?: RequestInit) => {
      const u = String(url);
      if (u.includes("/auth/logout/")) {
        logoutCalls.push({ method: opts?.method });
        return Promise.resolve(jsonResponse(204, undefined));
      }
      if (u.includes("/auth/me/")) return Promise.resolve(jsonResponse(200, me));
      if (u.includes("/dashboard/")) {
        return Promise.resolve(
          jsonResponse(200, { needs_me: { gates: [], clarifications: [] } }),
        );
      }
      // runners polling + anything else the shell touches — keep them empty.
      return Promise.resolve(jsonResponse(200, []));
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AppShell account menu — logout", () => {
  it("opens the account menu and shows the signed-in user", async () => {
    renderWithProviders(<AppShell />);
    const trigger = await screen.findByRole("button", { name: /account menu for ada/i });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("menuitem", { name: /sign out/i })).toBeDefined();
    expect(screen.getByText("ada@acme.test")).toBeDefined();
  });

  it("signs out via POST /auth/logout when Sign out is clicked", async () => {
    renderWithProviders(<AppShell />);
    const trigger = await screen.findByRole("button", { name: /account menu for ada/i });
    fireEvent.click(trigger);

    fireEvent.click(screen.getByRole("menuitem", { name: /sign out/i }));

    await waitFor(() => expect(logoutCalls.length).toBe(1));
    expect(logoutCalls[0].method).toBe("POST");
    // selectedProjectId is cleared as part of logout (AuthContext onSettled).
    await waitFor(() => expect(localStorage.getItem("selectedProjectId")).toBeNull());
  });

  it("closes the menu on Escape", async () => {
    renderWithProviders(<AppShell />);
    const trigger = await screen.findByRole("button", { name: /account menu for ada/i });
    fireEvent.click(trigger);
    expect(screen.getByRole("menuitem", { name: /sign out/i })).toBeDefined();

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("menuitem", { name: /sign out/i })).toBeNull());
  });
});
