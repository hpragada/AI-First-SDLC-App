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

// ── Bugs S.No 221 — a greenfield project was offered the brownfield wizard ──────────
//
// This file previously asserted NOTHING about which nav items appear, which is how the
// Onboarding item stayed unconditional: nothing was watching. The sidebar's whole job is
// deciding what a person is offered, so that decision needs tests of its own.
describe("sidebar — which items a project is offered", () => {
  /** Re-stubs fetch with a `/auth/me` whose single membership carries `track`. */
  function signInWith(membership: Record<string, unknown>) {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: RequestInfo | URL) => {
        const u = String(url);
        if (u.includes("/auth/me/")) {
          return Promise.resolve(jsonResponse(200, { ...me, memberships: [membership] }));
        }
        if (u.includes("/dashboard/")) {
          return Promise.resolve(
            jsonResponse(200, { needs_me: { gates: [], clarifications: [] } }),
          );
        }
        return Promise.resolve(jsonResponse(200, []));
      }),
    );
  }

  const base = { project_id: "p1", project_name: "Platform", role: "developer" };

  it("hides Onboarding on a project started from scratch", async () => {
    signInWith({ ...base, track: "greenfield" });
    renderWithProviders(<AppShell />);

    // Wait for the SESSION, not merely for the nav. The shell renders immediately, before
    // /auth/me resolves, and at that moment there is no track and the item is (correctly)
    // still shown — asserting too early passes against a screen that knows nothing yet.
    await screen.findByRole("button", { name: /account menu for ada/i });
    expect(screen.queryByRole("link", { name: "Onboarding" })).toBeNull();
  });

  it("still offers Onboarding on a project with an existing codebase", async () => {
    signInWith({ ...base, track: "brownfield" });
    renderWithProviders(<AppShell />);

    expect(await screen.findByRole("link", { name: "Onboarding" })).toBeDefined();
  });

  it("offers Onboarding when the API is too old to send a track", async () => {
    // Fail OPEN. A frontend deployed ahead of its API must not lock a brownfield team out
    // of the only screen that starts their lifecycle.
    signInWith(base);
    renderWithProviders(<AppShell />);

    expect(await screen.findByRole("link", { name: "Onboarding" })).toBeDefined();
  });

  it("keeps Test Reporting admin-only after the gate was generalised", async () => {
    // `adminOnly` became a predicate in this change; this pins that the one rule it
    // already enforced still holds. `me` is a non-admin.
    signInWith({ ...base, track: "brownfield" });
    renderWithProviders(<AppShell />);

    await screen.findByRole("link", { name: "Onboarding" });
    expect(screen.queryByRole("link", { name: "Test Reporting" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Workspace Admin" })).toBeNull();
  });
});
