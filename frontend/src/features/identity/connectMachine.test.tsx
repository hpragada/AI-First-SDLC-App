// @vitest-environment jsdom
//
// Bugs S.No 198 + 223 — Connect Machine.
//
// The screen decided "are we finished?" by asking "is there a token?", and the FAILURE path
// set a hardcoded placeholder token. So a request that failed rendered as a completed one,
// with a token that could never authenticate. Alongside it, the Projects picker was wired to
// nothing at all: whatever you chose, the machine was enrolled against your first project.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { ConnectMachine } from "./ConnectMachine";

const PLACEHOLDER = /rnr_3f9a/;

const ME = {
  user: { id: "u1", email: "dev@acme.test", name: "Dev", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [
    { project_id: "p1", project_name: "SpendLog", role: "engineer" },
    { project_id: "p2", project_name: "Receipts API", role: "engineer" },
  ],
};

/** Routes by URL so AuthProvider gets a real user while the runner calls are controlled. */
function stubApi({ createStatus = 201, createBody = {} as unknown } = {}) {
  const calls: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const json = (status: number, body: unknown) =>
        ({ ok: status < 400, status, statusText: "stub",
           text: async () => JSON.stringify(body) }) as Response;
      if (url.includes("/auth/me")) return json(200, ME);
      if (url.includes("/runners") && (init?.method ?? "GET") === "POST") {
        calls.push({ url, body: JSON.parse(String(init?.body ?? "{}")) });
        return json(createStatus, createBody);
      }
      if (url.includes("/runners")) return json(200, []);          // no machine yet
      return json(401, { detail: "no session" });
    }),
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("S-06 Connect machine · a failure must not look like success", () => {
  beforeEach(() => {});

  it("shows the server's reason and NO token when generating fails", async () => {
    // THE TEST THAT WOULD HAVE CAUGHT THE BUG.
    stubApi({ createStatus: 403, createBody: { detail: "Your session has expired." } });
    const user = userEvent.setup();
    renderWithProviders(<ConnectMachine />);

    const button = await screen.findByRole("button", { name: /generate enrollment token/i });
    await user.click(button);

    await waitFor(() => expect(screen.getByText(/Could not generate a token/)).toBeDefined());
    expect(screen.getByText(/Your session has expired/)).toBeDefined();
    // The success view must NOT have appeared, and no token of any kind is on screen.
    expect(screen.queryByText("Token generated")).toBeNull();
    expect(screen.queryByText(/Waiting for first check-in/)).toBeNull();
    expect(document.body.textContent ?? "").not.toMatch(PLACEHOLDER);
    // The control that failed is still there — that is the retry.
    expect(screen.getByRole("button", { name: /generate enrollment token/i })).toBeDefined();
  });

  it("shows the real token, and only a real token, on success", async () => {
    stubApi({ createStatus: 201, createBody: { id: "r1", token: "rnr_realtoken_123" } });
    const user = userEvent.setup();
    renderWithProviders(<ConnectMachine />);

    await user.click(await screen.findByRole("button", { name: /generate enrollment token/i }));
    await waitFor(() => expect(screen.getByText("Token generated")).toBeDefined());
    expect(document.body.textContent ?? "").toContain("rnr_realtoken_123");
    expect(document.body.textContent ?? "").not.toMatch(PLACEHOLDER);
  });
});

describe("S-06 Connect machine · the project picker actually picks", () => {
  it("enrolls against the project that was chosen, not the first one", async () => {
    // Bugs S.No 223: the select had no value, no onChange and no state, so it was decorative.
    const calls = stubApi({ createStatus: 201, createBody: { id: "r1", token: "rnr_x" } });
    const user = userEvent.setup();
    renderWithProviders(<ConnectMachine />);

    const select = await screen.findByLabelText("Project");
    await user.selectOptions(select, "p2");
    await user.click(screen.getByRole("button", { name: /generate enrollment token/i }));

    await waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0].body).toEqual({ project_id: "p2" });
  });

  it("offers one project at a time, because an enrollment binds one machine to one project", async () => {
    stubApi();
    renderWithProviders(<ConnectMachine />);
    const select = (await screen.findByLabelText("Project")) as HTMLSelectElement;
    expect(select.multiple).toBe(false);
    // ...and carries no leftover demo data: "Payment Gateway v2" was hardcoded as a fallback.
    expect(document.body.textContent ?? "").not.toContain("Payment Gateway v2");
    expect([...select.options].map((o) => o.textContent)).toEqual(["SpendLog", "Receipts API"]);
  });
});

describe("S-06 Connect machine · a workspace with no project", () => {
  it("says what is missing instead of sending an empty request", async () => {
    const calls = stubApi();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const json = (status: number, body: unknown) =>
          ({ ok: status < 400, status, statusText: "stub",
             text: async () => JSON.stringify(body) }) as Response;
        if (url.includes("/auth/me")) return json(200, { ...ME, memberships: [] });
        if (url.includes("/runners")) return json(200, []);
        return json(401, { detail: "no session" });
      }),
    );
    renderWithProviders(<ConnectMachine />);

    await waitFor(() => expect(screen.getByText(/Create a project first/)).toBeDefined());
    expect(screen.queryByRole("button", { name: /generate enrollment token/i })).toBeNull();
    expect(calls.length).toBe(0);
  });
});

describe("S-06 Connect machine · the offline screen", () => {
  it("never prints a fake token into a command it tells you to run", async () => {
    // The same bug one screen along: a returning user has no token in state, so this command
    // used to be printed with the hardcoded placeholder in it.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const json = (status: number, body: unknown) =>
          ({ ok: status < 400, status, statusText: "stub",
             text: async () => JSON.stringify(body) }) as Response;
        if (url.includes("/auth/me")) return json(200, ME);
        if (url.includes("/runners"))
          return json(200, [{ id: "r1", machine: "dev-box", online: false,
                              last_seen: "2026-09-07T06:00:00Z" }]);
        return json(401, { detail: "no session" });
      }),
    );
    renderWithProviders(<ConnectMachine />);

    await waitFor(() => expect(screen.getByText(/Offline —/)).toBeDefined());
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(PLACEHOLDER);
    expect(text).toContain("--token <your-token>");
    expect(text).toMatch(/shown only once/);
  });
});
