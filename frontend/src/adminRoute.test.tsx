// @vitest-environment jsdom
/**
 * Bugs S.No 225 — an admin address the app does not know.
 *
 * Every unknown address in the app returns you somewhere real. The admin section alone rendered a
 * developer's placeholder — "Foundation route mounted. Feature screens land in T2-T5", "rendered
 * inside the Phase 4.8 app shell" — to the client's own administrator, with no way back. The team
 * chose option A: it goes to the admin landing screen, and the placeholder is deleted.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen } from "@testing-library/react";

import { AppRoutes } from "./routes";
import { renderWithProviders } from "./test/utils";

function signIn(isAdmin: boolean) {
  const me = {
    user: { id: "u1", name: "Sam", email: "sam@acme.test", is_tenant_admin: isAdmin },
    tenant: { id: "t1", name: "Acme" },
    memberships: [{ project_id: "p1", project_name: "Checkout", role: isAdmin ? "admin" : "engineer" }],
  };
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const body = String(url).includes("/auth/me") ? me : [];
    return { ok: true, status: 200, statusText: "ok",
             text: async () => JSON.stringify(body) } as Response;
  }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("an admin address that does not exist", () => {
  it("lands on the admin landing screen", async () => {
    signIn(true);
    renderWithProviders(<AppRoutes />, { route: "/admin/settings-that-do-not-exist" });

    expect(await screen.findByText("Users & invitations")).toBeDefined();
  });

  it("never shows the client a developer's note", async () => {
    signIn(true);
    renderWithProviders(<AppRoutes />, { route: "/admin/anything" });

    await screen.findByText("Users & invitations");
    expect(screen.queryByText(/Foundation route/)).toBeNull();
    expect(screen.queryByText(/Ready for screen implementation/)).toBeNull();
    expect(screen.queryByText(/Phase 4\.8/)).toBeNull();
  });

  it("still tells someone who is not an admin that the page is for admins", async () => {
    signIn(false);
    renderWithProviders(<AppRoutes />, { route: "/admin/anything" });

    expect(await screen.findByText("Admin access needed")).toBeDefined();
  });
});
