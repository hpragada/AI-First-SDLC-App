// @vitest-environment jsdom
/**
 * Bugs S.No 219 — an action that fails must say so.
 *
 * The counterpart to errorStates.test.tsx, which covers failed READS. Seven places did work on
 * the user's behalf and, when the server refused, showed nothing at all: an invitation resend
 * that quietly did nothing, a repository refusal caught and thrown away, a button that flipped
 * back as if nothing had been asked, three password forms that sat there in silence.
 *
 * The root cause was that there was no shared way to show a failed write — there was one for
 * reads — so four screens each invented their own and three more gave up.
 *
 * Each test asserts BOTH halves: the error IS shown, and the reassuring/unchanged state is NOT.
 * The second assertion is the one that pins the bug.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { AcceptInvite } from "../identity/AcceptInvite";
import { ResetPassword } from "../identity/ResetPassword";
import { Signup } from "../identity/Signup";
import { UsersInvites } from "../identity/UsersInvites";
import { Repositories } from "../setup/Repositories";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "admin" }],
};

/** Reads succeed, every WRITE fails — the state a person is actually in when a button appears
 *  to do nothing. `body` is the server's own answer, which is what must reach the screen. */
function stubWriteFailure(
  { reads = {} as Record<string, unknown>, status = 403, body = {} as unknown,
    signedOut = false } = {},
) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const u = String(url);
      const method = (init?.method ?? "GET").toUpperCase();
      const res = (s: number, b: unknown) =>
        ({ ok: s < 400, status: s, statusText: "stub",
           text: async () => JSON.stringify(b) }) as Response;
      // A password reset is done signed OUT; signed in, the page now asks you to sign out first.
      if (u.includes("/auth/me")) return signedOut ? res(401, { detail: "no session" }) : res(200, me);
      if (method !== "GET") return res(status, body);
      for (const [needle, value] of Object.entries(reads)) {
        if (u.includes(needle)) return res(200, value);
      }
      return res(200, []);
    }),
  );
}

beforeEach(() => {
  // AuthContext seeds the selected project from localStorage on its first render, so a screen
  // that scopes its query by project fetches nothing without this.
  localStorage.setItem("selectedProjectId", "p1");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

// ── actions on a row ────────────────────────────────────────────────
const invitation = {
  id: "inv1", email: "jo@acme.test", name: "Jo", status: "pending",
  grants: [], expires_at: null, accepted_at: null, created_at: "2026-09-01T00:00:00Z",
};

describe("resending or revoking an invitation", () => {
  it("says why it failed instead of doing nothing", async () => {
    stubWriteFailure({
      reads: { "/invitations": [invitation], "/users": [] },
      status: 410,
      body: { detail: "This invitation expired on 4 September." },
    });
    const user = userEvent.setup();
    renderWithProviders(<UsersInvites />);

    await user.click(await screen.findByRole("button", { name: "Resend" }));

    await waitFor(() => expect(screen.getByText(/Invitation not resent/)).toBeDefined());
    expect(screen.getByText(/expired on 4 September/)).toBeDefined();
  });

  it("stays silent when the resend actually works", async () => {
    stubWriteFailure({
      reads: { "/invitations": [invitation], "/users": [] }, status: 200, body: {},
    });
    const user = userEvent.setup();
    renderWithProviders(<UsersInvites />);

    await user.click(await screen.findByRole("button", { name: "Resend" }));
    await new Promise((r) => setTimeout(r, 80));

    expect(screen.queryByText(/Invitation not resent/)).toBeNull();
  });

  it("says why a revoke failed", async () => {
    stubWriteFailure({
      reads: { "/invitations": [invitation], "/users": [] },
      status: 403, body: { detail: "Only an admin can revoke an invitation." },
    });
    const user = userEvent.setup();
    renderWithProviders(<UsersInvites />);

    await user.click(await screen.findByRole("button", { name: "Revoke" }));

    await waitFor(() => expect(screen.getByText(/Invitation not revoked/)).toBeDefined());
    expect(screen.getByText(/Only an admin/)).toBeDefined();
  });
});

describe("repositories", () => {
  const repo = {
    id: "r1", name: "acme/api", role: "backend", default_base: "main",
    preview_url: "", status: "active", is_default: true,
  };

  it("surfaces a refusal to add, not only a duplicate", async () => {
    // Only 409 was ever inspected. A 403 from the role check — the most likely failure, and the
    // one a person can act on — was caught and discarded, so Add did nothing and said nothing.
    stubWriteFailure({
      reads: { "/repositories": { repo_topology: "single", repositories: [] } },
      status: 403,
      body: { detail: "You need the tech lead role to add a repository." },
    });
    const user = userEvent.setup();
    renderWithProviders(<Repositories forceView="add-form" />);

    await user.type(await screen.findByPlaceholderText("acme/payments-jobs"), "acme/new");
    await user.click(screen.getByRole("button", { name: /^Add$/ }));

    await waitFor(() => expect(screen.getByText(/add that repository/)).toBeDefined());
    expect(screen.getByText(/tech lead role/)).toBeDefined();
    // ...and it is NOT mislabelled as the duplicate case, which is a different problem.
    expect(screen.queryByText(/already registered/)).toBeNull();
  });

  it("surfaces a refusal to remove", async () => {
    stubWriteFailure({
      reads: { "/repositories": { repo_topology: "single", repositories: [repo] } },
      status: 403, body: { detail: "You need the tech lead role to remove a repository." },
    });
    const user = userEvent.setup();
    renderWithProviders(<Repositories />);

    await user.click(await screen.findByRole("button", { name: "Remove" }));

    await waitFor(() => expect(screen.getByText(/remove that repository/)).toBeDefined());
  });
});

// ── the three password forms ────────────────────────────────────────
describe("sign-up", () => {
  async function fillSignup(user: ReturnType<typeof userEvent.setup>, password: string) {
    await user.type(screen.getByPlaceholderText("e.g. Jordan Lee"), "Jo");
    await user.type(screen.getByPlaceholderText("you@company.com"), "jo@acme.test");
    await user.type(screen.getByPlaceholderText("At least 8 characters"), password);
    await user.type(screen.getByPlaceholderText("e.g. Northwind Labs"), "Acme");
    await user.click(screen.getByRole("button", { name: /Create workspace/ }));
  }

  it("puts the server's complaint on the field it names", async () => {
    stubWriteFailure({
      status: 400,
      body: { password: ["This password is too short. It must contain at least 8 characters."] },
    });
    const user = userEvent.setup();
    renderWithProviders(<Signup />);

    await fillSignup(user, "short");

    await waitFor(() => expect(screen.getByText(/must contain at least 8/i)).toBeDefined());
  });

  it("falls back to a banner when the server names no field", async () => {
    stubWriteFailure({ status: 500, body: { detail: "The database is unavailable." } });
    const user = userEvent.setup();
    renderWithProviders(<Signup />);

    await fillSignup(user, "longenough1");

    await waitFor(() => expect(screen.getByText(/database is unavailable/)).toBeDefined());
    // The reassuring subtitle is replaced by the problem — the form is not left looking calm.
    expect(screen.queryByText(/Start your free Edvensoft workspace/)).toBeNull();
  });
});

describe("accepting an invitation", () => {
  it("shows a rejected password instead of sitting in silence", async () => {
    stubWriteFailure({
      reads: { "invitation": { email: "jo@acme.test", name: "Jo" } },
      status: 400,
      body: { password: ["This password is too common."] },
    });
    const user = userEvent.setup();
    renderWithProviders(<AcceptInvite />, { route: "/accept?token=abc" });

    // A name is required now (2026-10-09), so it is filled in like a person would.
    await user.type(await screen.findByPlaceholderText("e.g. Jordan Lee"), "Jo");
    await user.type(screen.getByPlaceholderText("At least 8 characters"), "password123");
    await user.click(screen.getByRole("button", { name: /Join workspace/ }));

    await waitFor(() => expect(screen.getByText(/too common/)).toBeDefined());
  });
});

describe("setting a new password", () => {
  it("shows a rejected password", async () => {
    stubWriteFailure({ status: 400, body: { password: ["This password is entirely numeric."] },
                       signedOut: true });
    const user = userEvent.setup();
    renderWithProviders(<ResetPassword />, { route: "/reset?token=abc" });

    const boxes = document.querySelectorAll('input[type="password"]');
    await user.type(boxes[0] as HTMLElement, "12345678");
    await user.type(boxes[1] as HTMLElement, "12345678");
    await user.click(screen.getByRole("button", { name: /Update password/ }));

    await waitFor(() => expect(screen.getByText(/entirely numeric/)).toBeDefined());
  });

  it("refuses to submit when the confirmation does not match", async () => {
    // Found while fixing the above: the form asked you to confirm and then never compared the
    // two, so a mistyped confirmation silently accepted the FIRST value — you set a password
    // you did not think you set. The server is sent one password and cannot detect this.
    const writes: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
        const u = String(url);
        if ((init?.method ?? "GET").toUpperCase() !== "GET") writes.push(u);
        // Signed out, as a person resetting a password is.
        if (u.includes("/auth/me")) {
          return { ok: false, status: 401, statusText: "stub",
                   text: async () => JSON.stringify({ detail: "no session" }) } as Response;
        }
        return { ok: true, status: 200, statusText: "stub",
                 text: async () => JSON.stringify({}) } as Response;
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<ResetPassword />, { route: "/reset?token=abc" });

    const boxes = document.querySelectorAll('input[type="password"]');
    await user.type(boxes[0] as HTMLElement, "correcthorse1");
    await user.type(boxes[1] as HTMLElement, "correcthorse2");
    await user.click(screen.getByRole("button", { name: /Update password/ }));

    await waitFor(() => expect(screen.getByText(/match/)).toBeDefined());
    expect(writes.length).toBe(0);                       // nothing was sent
    expect(screen.queryByText(/Password updated/)).toBeNull();
  });
});
