// @vitest-environment jsdom
/**
 * Bugs S.No 221 — a greenfield project was offered a brownfield wizard.
 *
 * The sidebar no longer shows Onboarding on a project started from scratch (covered in
 * AppShell.test.tsx), but hiding a link is not the same as closing a door: `/onboarding` is
 * still a URL that can be typed, bookmarked, or carried over from another project. These
 * cover the route guard, which is what makes the hub's "Brownfield project" claim true
 * rather than merely usually-true.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";

import { renderWithProviders } from "../../test/utils";
import { AppRoutes } from "../../routes";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

const user = { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: false };

function signInWith(track?: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: RequestInfo | URL) => {
      const u = String(url);
      const body = u.includes("/auth/me/")
        ? {
            user,
            tenant: { id: "t1", name: "Acme" },
            memberships: [
              { project_id: "p1", project_name: "Platform", role: "developer", ...(track ? { track } : {}) },
            ],
          }
        : {};
      return { ok: true, status: 200, statusText: "stub",
               text: async () => JSON.stringify(body) } as Response;
    }),
  );
}

const ONBOARDING_ROUTES = ["/onboarding", "/onboarding/documents", "/onboarding/gap-report"];

describe("S.No 221 · onboarding is brownfield-only", () => {
  for (const route of ONBOARDING_ROUTES) {
    it(`explains itself instead of running the wizard at ${route}`, async () => {
      signInWith("greenfield");
      renderWithProviders(<AppRoutes />, { route });

      await waitFor(() => expect(screen.getByText("Nothing to onboard yet")).toBeDefined());
      // ...and the brownfield assertion — the actual defect — is nowhere on the page.
      expect(document.body.textContent ?? "").not.toMatch(/Brownfield project/);
      // The way out is named, not left to the back button. (The sidebar carries its own
      // "Project Profile" link, so this asserts on the one the panel itself offers.)
      expect(screen.getByRole("link", { name: /back to the dashboard/i })).toBeDefined();
    });
  }

  it("lets a brownfield project through to the hub", async () => {
    signInWith("brownfield");
    renderWithProviders(<AppRoutes />, { route: "/onboarding" });

    await waitFor(() =>
      expect(document.body.textContent ?? "").toMatch(/Loading onboarding status|Onboarding —/),
    );
    expect(screen.queryByText("Nothing to onboard yet")).toBeNull();
  });

  it("lets a project through when the API is too old to send a track", async () => {
    // Fail open, for the same reason the sidebar does: a frontend ahead of its API must not
    // lock a brownfield team out of the screen that starts their lifecycle.
    signInWith(undefined);
    renderWithProviders(<AppRoutes />, { route: "/onboarding" });

    await waitFor(() =>
      expect(document.body.textContent ?? "").toMatch(/Loading onboarding status|Onboarding —/),
    );
    expect(screen.queryByText("Nothing to onboard yet")).toBeNull();
  });
});
