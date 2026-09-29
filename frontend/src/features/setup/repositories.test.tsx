// @vitest-environment jsdom
/**
 * Bugs S.No 212 — "Set default" on Repositories did nothing, and usually was not there.
 *
 *   * The button was drawn only when the screen decided the project was "multi", worked out from
 *     the count with its OWN rule (more than one) instead of the platform's (0–1 single, 2 split,
 *     3+ multi). The API sent the platform's answer and the screen threw it away.
 *   * Opening "Add repository" switched the table to its single-repository layout — no Set
 *     default — and nothing ever closed the form.
 *   * The click handler was a stub, beside a note saying the backend could not do this yet. It
 *     could; the endpoint had existed, permission-checked, all along.
 *
 * The team chose option A: the table answers. The "default" marker moves to the chosen row; a
 * refusal is shown in the server's own words, beside the existing "couldn't remove" message.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { Repositories } from "./Repositories";

const me = {
  user: { id: "u1", name: "Dev", email: "dev@acme.test", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Checkout", role: "tech_lead" }],
};

type Repo = { id: string; name: string; role: string; default_base: string; preview_url: string;
              status: string; is_default: boolean };
const repo = (id: string, name: string, role: string, is_default = false): Repo =>
  ({ id, name, role, default_base: "main", preview_url: "", status: "connected", is_default });

// The platform's rule, so the stub answers the way the backend does.
const topologyFor = (n: number) => (n >= 3 ? "multi" : n === 2 ? "split" : "single");

let repos: Repo[] = [];
let writes: Array<{ url: string; method: string; body?: unknown }> = [];

function stub({ refuseSetDefault }: { refuseSetDefault?: string } = {}) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    const method = (init?.method ?? "GET").toUpperCase();
    const res = (status: number, body?: unknown) =>
      ({ ok: status < 400, status, statusText: "stub",
         text: async () => (body === undefined ? "" : JSON.stringify(body)) }) as Response;
    if (u.includes("/auth/me")) return res(200, me);
    if (method !== "GET") {
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      writes.push({ url: u, method, body });
      if (u.endsWith("/set-default/")) {
        if (refuseSetDefault) return res(403, { detail: refuseSetDefault });
        const id = u.split("/").slice(-3)[0];
        repos = repos.map((r) => ({ ...r, is_default: r.id === id }));
        return res(200, repos);
      }
      if (method === "POST") {
        const created = repo("r9", body.name, body.role);
        repos = [...repos, created];
        return res(201, created);
      }
      return res(204);
    }
    if (u.includes("/repositories")) {
      return res(200, { repo_topology: topologyFor(repos.length), repositories: repos });
    }
    return res(200, []);
  }));
}

const row = (name: string) => screen.getByText(name).closest("tr") as HTMLElement;

beforeEach(() => {
  localStorage.setItem("selectedProjectId", "p1");
  repos = [repo("r1", "acme/api", "backend", true), repo("r2", "acme/web", "frontend")];
  writes = [];
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("Set default", () => {
  it("is offered on the repository that is not the default, and not on the one that is", async () => {
    stub();
    renderWithProviders(<Repositories />);

    await waitFor(() => expect(screen.getByText("acme/web")).toBeDefined());
    expect(within(row("acme/api")).getByText("default")).toBeDefined();
    expect(within(row("acme/api")).queryByRole("button", { name: "Set default" })).toBeNull();
    expect(within(row("acme/web")).getByRole("button", { name: "Set default" })).toBeDefined();
  });

  it("does something now: the default marker moves to the chosen row", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<Repositories />);

    await user.click(await within(await screen.findByText("acme/web").then(
      (el) => el.closest("tr") as HTMLElement)).findByRole("button", { name: "Set default" }));

    expect(writes).toEqual([
      { url: expect.stringContaining("/projects/p1/repositories/r2/set-default/"),
        method: "POST", body: undefined },
    ]);
    await waitFor(() => expect(within(row("acme/web")).getByText("default")).toBeDefined());
    expect(within(row("acme/web")).queryByRole("button", { name: "Set default" })).toBeNull();
    expect(within(row("acme/api")).getByRole("button", { name: "Set default" })).toBeDefined();
    expect(within(row("acme/api")).queryByText("default")).toBeNull();
  });

  it("is not offered when there is only one repository — there is nothing to choose", async () => {
    repos = [repo("r1", "acme/api", "backend", true)];
    stub();
    renderWithProviders(<Repositories />);

    await waitFor(() => expect(screen.getByText("acme/api")).toBeDefined());
    expect(screen.queryByRole("button", { name: "Set default" })).toBeNull();
  });

  it("says why the server refused, in its own words", async () => {
    const reason =
      "Only a tech lead or an admin can change which repository is the default for this project.";
    stub({ refuseSetDefault: reason });
    const user = userEvent.setup();
    renderWithProviders(<Repositories />);

    await waitFor(() => expect(screen.getByText("acme/web")).toBeDefined());
    await user.click(within(row("acme/web")).getByRole("button", { name: "Set default" }));

    expect(await screen.findByText("Couldn't set the default repository")).toBeDefined();
    expect(screen.getByText(reason)).toBeDefined();
    expect(within(row("acme/api")).getByText("default")).toBeDefined();  // nothing moved
  });
});

describe("the topology shown", () => {
  it("is the platform's own, not one worked out on screen", async () => {
    // Two repositories are "split" to the platform; the old screen called any count above one
    // "multi", which is the disagreement S.No 104 was about, moved to this screen.
    stub();
    renderWithProviders(<Repositories />);

    expect(await screen.findByText("Topology: split")).toBeDefined();
    expect(screen.queryByText("Topology: multi")).toBeNull();
  });
});

describe("the add form", () => {
  it("leaves the table and its Set default in place while it is open", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<Repositories />);

    await waitFor(() => expect(screen.getByText("acme/web")).toBeDefined());
    await user.click(screen.getByRole("button", { name: "+ Add repository" }));

    expect(screen.getByPlaceholderText("acme/payments-jobs")).toBeDefined();
    expect(within(row("acme/web")).getByRole("button", { name: "Set default" })).toBeDefined();
  });

  it("closes once the repository is added", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<Repositories />);

    await waitFor(() => expect(screen.getByText("acme/web")).toBeDefined());
    await user.click(screen.getByRole("button", { name: "+ Add repository" }));
    await user.type(screen.getByPlaceholderText("acme/payments-jobs"), "acme/jobs");
    await user.click(screen.getByRole("button", { name: /^Add$/ }));

    await waitFor(() => expect(screen.queryByPlaceholderText("acme/payments-jobs")).toBeNull());
    expect(await screen.findByText("acme/jobs")).toBeDefined();
  });

  it("can be closed without adding anything", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<Repositories />);

    await waitFor(() => expect(screen.getByText("acme/web")).toBeDefined());
    await user.click(screen.getByRole("button", { name: "+ Add repository" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByPlaceholderText("acme/payments-jobs")).toBeNull();
    expect(writes).toEqual([]);
  });
});
