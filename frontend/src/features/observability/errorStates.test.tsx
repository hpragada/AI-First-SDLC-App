// @vitest-environment jsdom
/**
 * Bugs S.No 220 — a failed request must not render as an empty workspace.
 *
 * Five list screens branched on "loading?" and then on "is the list empty?", and a failed request
 * produces an empty list. So a completely broken backend rendered as a calm, healthy, brand-new
 * workspace: "You're all caught up", "No lineage yet", "It's just you so far". The QA audit found
 * the sharpest consequence — several written test cases would PASS against a dead server, because
 * "the dashboard shows no pending gates" is exactly what they assert.
 *
 * Each test below asserts BOTH halves: the error is shown, AND the reassuring empty-state copy is
 * not. The second assertion is the one that actually pins the bug.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";

import { renderWithProviders } from "../../test/utils";
import { Dashboard } from "./Dashboard";
import { TraceabilityView } from "./TraceabilityView";
import { ArtifactsRegistry } from "./ArtifactsRegistry";
import { UsersInvites } from "../identity/UsersInvites";
import { Repositories } from "../setup/Repositories";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "admin" }],
};

/** Everything fails with a 500 except `/auth/me/`, so a project is selected and the screens
 *  actually attempt their fetch — which is the state a broken backend puts a real user in. */
function stubEverythingBroken() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/auth/me")) {
        return { ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(me) } as Response;
      }
      return {
        ok: false,
        status: 500,
        statusText: "Server Error",
        text: async () => JSON.stringify({ detail: "the database is unreachable" }),
      } as Response;
    }),
  );
}

beforeEach(stubEverythingBroken);
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const CASES: [string, () => JSX.Element, RegExp][] = [
  ["the dashboard", () => <Dashboard />, /all caught up/i],
  ["traceability", () => <TraceabilityView />, /no lineage yet/i],
  ["the artifact registry", () => <ArtifactsRegistry />, /no artifacts yet/i],
  ["the team roster", () => <UsersInvites />, /just you so far/i],
  ["repositories", () => <Repositories />, /no repositories yet/i],
];

describe.each(CASES)("%s", (_label, render, emptyCopy) => {
  it("says the request failed instead of showing an empty state", async () => {
    renderWithProviders(render());
    await waitFor(() => expect(screen.getByText(/Something went wrong on our side/i)).toBeTruthy());
    expect(screen.queryByText(emptyCopy)).toBeNull();
  });

  it("★ never shows the client what the server said to us", async () => {
    // CHANGED 8 September (Bugs S.No 248). This used to assert the opposite — that the server's
    // own words reached the screen — and "the database is unreachable" is precisely why that was
    // wrong. A client who did not build this cannot act on our database, and in the real failure
    // the text was worse than unhelpful: an unreachable server produced the browser's "Failed to
    // fetch", and a 500 produced a JSON parse error, because the body was parsed before the
    // status was checked. The server's words still exist — in the server log, for us.
    renderWithProviders(render());
    await waitFor(() => expect(screen.getByText(/Something went wrong on our side/i)).toBeTruthy());
    expect(screen.queryByText(/the database is unreachable/i)).toBeNull();
    expect(screen.queryByText(/Failed to fetch/i)).toBeNull();
    expect(screen.queryByText(/is not valid JSON/i)).toBeNull();
    expect(screen.queryByText(/500/)).toBeNull();
  });

  it("still says the screen is empty because it failed, not because there is nothing", async () => {
    // The load-bearing half of S.No 220, kept: a broken screen must never read as a clean one.
    renderWithProviders(render());
    await waitFor(() =>
      expect(screen.getByText(/not because there is nothing here/i)).toBeTruthy());
  });

  it("offers a way to try again", async () => {
    renderWithProviders(render());
    await waitFor(() => expect(screen.getByRole("button", { name: /try again/i })).toBeTruthy());
  });
});

/** Everything answers `answer` except `/auth/me/`, so a project is selected and the screen really
 *  attempts its fetch. `answer` is a thunk so it can also REJECT, which is what a browser does
 *  when the request never leaves it. */
function stubWith(answer: () => Promise<Response>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: RequestInfo | URL) => {
      if (String(url).includes("/auth/me")) {
        return { ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(me) } as Response;
      }
      return answer();
    }),
  );
}

describe("the three failures a screen can tell apart (S.No 248)", () => {
  it("★ a server that cannot be reached says so, in the reader's words", async () => {
    // The team's screenshot. `fetch` rejects with the browser's own `TypeError: Failed to fetch`
    // when the request never left the browser — the backend not running, or an origin the API
    // does not allow. That string reached the screen verbatim for months.
    stubWith(() => Promise.reject(new TypeError("Failed to fetch")));
    renderWithProviders(<Dashboard />);

    await waitFor(() =>
      expect(screen.getByText(/Can't reach the SDLC app right now/i)).toBeTruthy());
    expect(screen.getByText(/Your browser couldn't connect/i)).toBeTruthy();
    expect(screen.queryByText(/Failed to fetch/i)).toBeNull();
    expect(screen.getByRole("button", { name: /try again/i })).toBeTruthy();
  });

  it("★ a 500 answered as an HTML page is a server error, not a parse error", async () => {
    // THE plumbing fix, stated as a test. Django answers a 500 with an HTML error page, and the
    // body used to be parsed as JSON BEFORE the status was checked — so every real 500 became
    // `Unexpected token '<'` and the status code was thrown away. A server error could not
    // describe itself, and no screen could tell it apart from a lost connection.
    stubWith(async () => ({
      ok: false, status: 500, statusText: "Server Error",
      text: async () => "<!doctype html><html><body><h1>Server Error (500)</h1></body></html>",
    }) as Response);
    renderWithProviders(<Dashboard />);

    await waitFor(() =>
      expect(screen.getByText(/Something went wrong on our side/i)).toBeTruthy());
    expect(screen.queryByText(/is not valid JSON/i)).toBeNull();
    expect(screen.queryByText(/doctype/i)).toBeNull();
    expect(screen.queryByText(/Can't reach the SDLC app/i)).toBeNull();
  });

  it("★ a permission problem offers no Try again, because retrying cannot help", async () => {
    stubWith(async () => ({
      ok: false, status: 403, statusText: "Forbidden",
      text: async () => JSON.stringify({ detail: "You are not a member of this project." }),
    }) as Response);
    renderWithProviders(<Dashboard />);

    await waitFor(() => expect(screen.getByText(/don't have access/i)).toBeTruthy());
    expect(screen.getByText(/Ask a workspace admin/i)).toBeTruthy();
    // A control that cannot work is its own small lie.
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
    // And this one is not our fault, so it must not claim to be.
    expect(screen.queryByText(/Something went wrong on our side/i)).toBeNull();
  });
});
