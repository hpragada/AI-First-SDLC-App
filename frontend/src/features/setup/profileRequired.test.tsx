// @vitest-environment jsdom
/**
 * F2 — Save did nothing at all while the description was empty (the team's option A).
 *
 * `onSave` began by refusing, and the sentence explaining why had only ever been wired into the
 * design gallery — so in the real app the button stayed live, pressing it did nothing, no field
 * turned red, and the domain and tech stack typed above were stuck with it. A brand-new project
 * lands on this screen straight from Create Project, so setup never continued either.
 *
 * Option A keeps the field required and says so: an asterisk before anyone types, the reason on
 * Save, the cursor moved into the field, and every other field left on screen with its contents.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { ProjectProfileEditor } from "./ProjectProfileEditor";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "SpendLog", role: "tech_lead" }],
};

let writes: Array<{ url: string; body: Record<string, unknown> }> = [];

/** `profile` is what GET .../profile/ answers; 404 is a project with no briefing yet. */
function stub(profile: Record<string, unknown> | null) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    const res = (status: number, body: unknown) =>
      ({ ok: status < 400, status, statusText: "stub",
         text: async () => JSON.stringify(body) }) as Response;
    if ((init?.method ?? "GET").toUpperCase() !== "GET") {
      writes.push({ url: u, body: JSON.parse(String(init?.body ?? "{}")) });
      return res(200, { ...(profile ?? {}), version: 1 });
    }
    if (u.includes("/auth/me")) return res(200, me);
    if (u.includes("/profile/")) return profile ? res(200, profile) : res(404, { detail: "x" });
    if (u.includes("/export-policy/")) return res(200, { defaults: {} });
    return res(200, []);
  }));
}

const DESCRIPTION = "What this project is and what it should achieve, e.g. A web app for individuals to log daily expenses and see where their money goes.";
const MESSAGE = /A description is required — agents rely on it for every phase/;
const save = () => screen.getByRole("button", { name: "Save" });

beforeEach(() => {
  localStorage.setItem("selectedProjectId", "p1");
  writes = [];
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("pressing Save with no description", () => {
  it("says why, instead of doing nothing", async () => {
    stub(null);
    const user = userEvent.setup();
    renderWithProviders(<ProjectProfileEditor />);

    // Make the form dirty so Save is live, exactly as a real user would.
    await user.type(screen.getByPlaceholderText(/Personal finance/), "Personal finance");
    await user.click(save());

    expect(await screen.findByText(MESSAGE)).toBeDefined();
    expect(writes).toEqual([]);                      // nothing was sent, as before — but now said
  });

  it("puts the cursor in the field it is asking about", async () => {
    stub(null);
    const user = userEvent.setup();
    renderWithProviders(<ProjectProfileEditor />);

    await user.type(screen.getByPlaceholderText(/Personal finance/), "Personal finance");
    await user.click(save());

    expect(document.activeElement).toBe(screen.getByPlaceholderText(DESCRIPTION));
  });

  it("keeps every other field on screen, with what was typed in it", async () => {
    stub(null);
    const user = userEvent.setup();
    renderWithProviders(<ProjectProfileEditor />);

    await user.type(screen.getByPlaceholderText(/Personal finance/), "Personal finance");
    await user.click(save());

    await screen.findByText(MESSAGE);
    // The refusal used to hide all of these, so a user watched their typing disappear.
    expect((screen.getByPlaceholderText(/Personal finance/) as HTMLInputElement).value)
      .toBe("Personal finance");
    expect(screen.getByText("Tech stack")).toBeDefined();
    expect(screen.getByText("Export policy")).toBeDefined();
  });

  it("marks the field as required before anyone presses anything", async () => {
    stub(null);
    renderWithProviders(<ProjectProfileEditor />);

    await waitFor(() => expect(screen.getByText("Description")).toBeDefined());
    expect(screen.getByText("Description").parentElement?.textContent).toContain("*");
    expect(screen.queryByText(MESSAGE)).toBeNull();   // asked for, not complained about, yet
  });
});

describe("once a description is there", () => {
  it("saves the whole briefing", async () => {
    stub(null);
    const user = userEvent.setup();
    renderWithProviders(<ProjectProfileEditor />);

    await user.type(screen.getByPlaceholderText(DESCRIPTION), "Expense tracking for individuals.");
    await user.type(screen.getByPlaceholderText(/Personal finance/), "Personal finance");
    await user.click(save());

    await waitFor(() => expect(writes.length).toBe(1));
    expect(writes[0].body).toMatchObject({
      description: "Expense tracking for individuals.",
      domain: "Personal finance",
    });
  });

  it("clears the refusal as soon as the field is typed into", async () => {
    stub(null);
    const user = userEvent.setup();
    renderWithProviders(<ProjectProfileEditor />);

    await user.type(screen.getByPlaceholderText(/Personal finance/), "Personal finance");
    await user.click(save());
    await screen.findByText(MESSAGE);

    await user.type(screen.getByPlaceholderText(DESCRIPTION), "Expense tracking.");

    expect(screen.queryByText(MESSAGE)).toBeNull();
  });
});
