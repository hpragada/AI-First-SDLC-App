// @vitest-environment jsdom
//
// 2026-10-09 — the invite suite, as the team approved it in mockups 2–6.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { AcceptInvite } from "./AcceptInvite";
import { SetupChecklist } from "./SetupChecklist";
import { UsersInvites } from "./UsersInvites";

const PREVIEW = {
  tenant_name: "SDLC-companion-test",
  inviter_name: "test-companion",
  email: "priya@acme.com",
  name: "",
  grants: [{ project_id: "p1", project_name: "PeopleDesk", role: "engineer", role_label: "Engineer" }],
};
const ADMIN = {
  user: { id: "u0", email: "testcompanion@gmail.com", name: "test-companion", is_tenant_admin: true },
  tenant: { id: "t1", name: "SDLC-companion-test" },
  memberships: [{ project_id: "p1", project_name: "PeopleDesk", role: "admin" }],
};
const TEAMMATE = {
  user: { id: "u1", email: "priya@acme.com", name: "Priya", is_tenant_admin: false },
  tenant: { id: "t1", name: "SDLC-companion-test" },
  memberships: [{ project_id: "p1", project_name: "PeopleDesk", role: "engineer" }],
};

type Handler = (url: string, init?: RequestInit) => { status: number; body: unknown } | "offline" | undefined;

function stub(handler: Handler) {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const out = handler(url, init);
    if (out === "offline") throw new TypeError("Failed to fetch");
    const { status, body } = out ?? { status: 401, body: { detail: "no session" } };
    return { ok: status < 400, status, statusText: "stub",
             text: async () => JSON.stringify(body) } as Response;
  }));
}

const AT_INVITE = { route: "/accept-invite?token=tok" };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Accept invite · can't use this link (mockup 4)", () => {
  const cases: [string, number, string, RegExp][] = [
    ["used", 409, "You've already joined", /Sign in instead/],
    ["expired", 410, "This invite has expired", /Ask test-companion to send a new one/],
    ["revoked", 410, "This invite was cancelled", /Ask test-companion if you still need access/],
    ["invalid", 410, "This link doesn't work any more", /A newer invite may have replaced it/],
  ];
  for (const [reason, status, title, line] of cases) {
    it(`words "${reason}" on its own`, async () => {
      stub((url) =>
        url.includes("/invitations/preview")
          ? { status, body: { detail: "x", reason, inviter_name: "test-companion" } }
          : undefined,
      );
      renderWithProviders(<AcceptInvite />, AT_INVITE);
      expect(await screen.findByText(title)).toBeDefined();
      expect(screen.getByText(line)).toBeDefined();
      expect(screen.queryByText(/Request a new invite/)).toBeNull();
      expect(screen.queryByRole("button", { name: "Sign in" }) !== null).toBe(reason === "used");
    });
  }

  it("says the link isn't complete when there is no token at all", async () => {
    stub(() => undefined);
    renderWithProviders(<AcceptInvite />, { route: "/accept-invite" });
    expect(await screen.findByText("This link doesn't work any more")).toBeDefined();
    expect(screen.getByText("You're Invited to Edvensoft SDLC App")).toBeDefined();
  });
});

describe("Accept invite · app can't be reached (mockup 5)", () => {
  it("shows the banner and Try again instead of an empty form", async () => {
    stub((url) => (url.includes("/invitations/preview") ? "offline" : undefined));
    renderWithProviders(<AcceptInvite />, AT_INVITE);
    expect(await screen.findByText("Can't reach the SDLC app right now")).toBeDefined();
    expect(screen.getByText(/Your invite is safe/)).toBeDefined();
    expect(screen.getByRole("button", { name: "Try again" })).toBeDefined();
    expect(screen.queryByRole("button", { name: /Join workspace/ })).toBeNull();
  });
});

describe("Accept invite · someone is already signed in (mockup 3)", () => {
  it("names both people and offers to sign out", async () => {
    let signedIn = true;
    stub((url) => {
      if (url.includes("/invitations/preview")) return { status: 200, body: PREVIEW };
      if (url.includes("/auth/logout")) { signedIn = false; return { status: 200, body: {} }; }
      if (url.includes("/auth/me")) return signedIn ? { status: 200, body: ADMIN } : undefined;
      return { status: 200, body: [] };
    });
    const user = userEvent.setup();
    renderWithProviders(<AcceptInvite />, AT_INVITE);
    expect(await screen.findByText("This invite is for priya@acme.com.")).toBeDefined();
    expect(screen.getByText(/You're signed in as testcompanion@gmail.com/)).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Sign out and continue" }));
    expect(await screen.findByRole("button", { name: /Join workspace/ })).toBeDefined();
  });
});

describe("Get started · a teammate (mockup 6)", () => {
  it("shows only their own step and never the admin's", async () => {
    stub((url) => {
      if (url.includes("/auth/me")) return { status: 200, body: TEAMMATE };
      if (url.includes("/runners")) return { status: 200, body: [] };
      return undefined;
    });
    renderWithProviders(<SetupChecklist />);
    expect(await screen.findByText("Welcome to PeopleDesk")).toBeDefined();
    expect(screen.getByText(/You've joined as Engineer\. One step left\./)).toBeDefined();
    expect(screen.getByText("Join the workspace")).toBeDefined();
    expect(screen.getByText("Connect your machine")).toBeDefined();
    expect(screen.queryByText(/Invite your team/)).toBeNull();
    expect(screen.queryByText(/Connect integrations/)).toBeNull();
    expect(screen.getByText(/set up by your workspace admin/)).toBeDefined();
  });
});

describe("Users & invitations · after Send invite (mockup 2)", () => {
  const outcomes: [string, Record<string, unknown>, RegExp][] = [
    ["emailed", { email_sent: true, email_delivery: "email" }, /Invite emailed to priya@acme\.com/],
    ["saved, not sent", { email_sent: false, email_delivery: "email" },
      /The invite was saved but the email couldn.t be sent\. Try Resend in a few minutes\./],
    ["no mail service", { email_sent: false, email_delivery: "console" },
      /Invite created\. The link is in the server terminal\./],
  ];
  for (const [name, outcome, words] of outcomes) {
    it(`says so when ${name}`, async () => {
      stub((url, init) => {
        if (url.includes("/auth/me")) return { status: 200, body: ADMIN };
        if (url.includes("/invitations") && init?.method === "POST") {
          return { status: 201, body: { id: "i1", email: "priya@acme.com", status: "pending",
                                        expires_at: "", grants: [], ...outcome } };
        }
        return { status: 200, body: [] };
      });
      const user = userEvent.setup();
      renderWithProviders(<UsersInvites />);
      await user.click((await screen.findAllByRole("button", { name: "+ Invite" }))[0]);
      await user.type(screen.getByPlaceholderText("name@acme.com"), "priya@acme.com");
      await user.click(screen.getByRole("button", { name: "Send invite" }));
      await waitFor(() => expect(screen.getByText(words)).toBeDefined());
    });
  }
});

describe("every role an invite grants (approved 2026-10-09)", () => {
  it("is worded by one rule", async () => {
    const { grantsPhrase } = await import("./roles");
    const g = (project_name: string, role_label: string) => ({ project_name, role_label });
    expect(grantsPhrase([g("PeopleDesk", "Engineer")])).toBe("as Engineer on PeopleDesk");
    expect(grantsPhrase([g("PeopleDesk", "Engineer"), g("PeopleDesk", "Architect")]))
      .toBe("as Engineer and Architect on PeopleDesk");
    expect(grantsPhrase([g("P", "Engineer"), g("P", "Architect"), g("P", "QA Lead")]))
      .toBe("as Engineer, Architect and QA Lead on P");
    expect(grantsPhrase([g("PeopleDesk", "Engineer"), g("Payroll", "Designer")]))
      .toBe("as Engineer on PeopleDesk and as Designer on Payroll");
  });

  it("shows on the invite page", async () => {
    stub((url) =>
      url.includes("/invitations/preview")
        ? { status: 200, body: { ...PREVIEW, grants: [
            ...PREVIEW.grants,
            { project_id: "p1", project_name: "PeopleDesk", role: "architect", role_label: "Architect" },
          ] } }
        : undefined,
    );
    renderWithProviders(<AcceptInvite />, AT_INVITE);
    expect(await screen.findByText(/as Engineer and Architect on PeopleDesk\./)).toBeDefined();
  });
});

describe("the live sweep fixes (approved 2026-10-09)", () => {
  it("never calls a short password strong, and says what the server would", async () => {
    const { passwordHelp } = await import("./hooks");
    expect(passwordHelp("abc")).toEqual({ tooShort: true, text: "Too short. Use at least 8 characters." });
    expect(passwordHelp("abcdefgh")?.text).toBe("Weak");
    expect(passwordHelp("Abcdefgh1!")?.text).not.toBe("Weak");
    expect(passwordHelp("")).toBeNull();
  });

  it("asks for a name before joining", async () => {
    const writes: string[] = [];
    stub((url, init) => {
      if (init?.method === "POST" && url.includes("accept-invitation")) writes.push(url);
      return url.includes("/invitations/preview") ? { status: 200, body: PREVIEW } : undefined;
    });
    const user = userEvent.setup();
    renderWithProviders(<AcceptInvite />, AT_INVITE);
    await user.type(await screen.findByPlaceholderText("At least 8 characters"), "LongEnough#1");
    await user.click(screen.getByRole("button", { name: /Join workspace/ }));
    expect(await screen.findByText("Enter your name.")).toBeDefined();
    expect(writes).toEqual([]);
  });

  it("a used link, signed in, does not tell you to sign in", async () => {
    stub((url) => {
      if (url.includes("/invitations/preview")) return { status: 409, body: { reason: "used" } };
      if (url.includes("/auth/me")) return { status: 200, body: TEAMMATE };
      return { status: 200, body: [] };
    });
    renderWithProviders(<AcceptInvite />, AT_INVITE);
    expect(await screen.findByText("This invite was used, and you're signed in.")).toBeDefined();
    expect(screen.getByRole("button", { name: "Go to my dashboard" })).toBeDefined();
  });
});

describe("password reset (approved 2026-10-09)", () => {
  it("never pre-fills somebody's address", async () => {
    const { ResetPassword } = await import("./ResetPassword");
    stub(() => undefined);
    renderWithProviders(<ResetPassword />, { route: "/reset" });
    const box = (await screen.findByPlaceholderText("you@company.com")) as HTMLInputElement;
    expect(box.value).toBe("");
  });

  it("a reset link opened while signed in asks you to sign out", async () => {
    const { ResetPassword } = await import("./ResetPassword");
    stub((url) => (url.includes("/auth/me") ? { status: 200, body: TEAMMATE } : { status: 200, body: [] }));
    renderWithProviders(<ResetPassword />, { route: "/reset?token=abc" });
    expect(await screen.findByText(/You're signed in as priya@acme\.com\. Sign out to set a new password/))
      .toBeDefined();
    expect(screen.queryByText(/sarah@acme\.com/)).toBeNull();
  });
});

describe("dashboard greeting (approved 2026-10-09)", () => {
  it("follows the clock", async () => {
    const { greeting } = await import("../observability/Dashboard");
    expect(greeting(new Date(2026, 9, 9, 9))).toBe("Good morning");
    expect(greeting(new Date(2026, 9, 9, 13))).toBe("Good afternoon");
    expect(greeting(new Date(2026, 9, 9, 19))).toBe("Good evening");
  });
});

describe("reset · Request a new link", () => {
  it("leaves the refused link behind", async () => {
    const { ResetPassword } = await import("./ResetPassword");
    stub((url, init) =>
      init?.method === "POST" && url.includes("/auth/reset")
        ? { status: 410, body: { detail: "This reset link is invalid or has expired." } }
        : undefined,
    );
    const user = userEvent.setup();
    renderWithProviders(<ResetPassword />, { route: "/reset?token=old" });
    const boxes = document.querySelectorAll('input[type="password"]');
    await user.type(boxes[0] as HTMLElement, "LongEnough#1");
    await user.type(boxes[1] as HTMLElement, "LongEnough#1");
    await user.click(screen.getByRole("button", { name: /Update password/ }));
    await user.click(await screen.findByRole("link", { name: "Request a new link" }));
    expect(await screen.findByText("Forgot your password?")).toBeDefined();
  });
});
