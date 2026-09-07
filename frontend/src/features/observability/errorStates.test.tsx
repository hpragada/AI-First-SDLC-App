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

const CASES: [string, () => JSX.Element, RegExp, RegExp][] = [
  ["the dashboard", () => <Dashboard />, /couldn't load your dashboard/i, /all caught up/i],
  ["traceability", () => <TraceabilityView />, /couldn't load the traceability graph/i, /no lineage yet/i],
  ["the artifact registry", () => <ArtifactsRegistry />, /couldn't load the artifact registry/i, /no artifacts yet/i],
  ["the team roster", () => <UsersInvites />, /couldn't load your team/i, /just you so far/i],
  ["repositories", () => <Repositories />, /couldn't load this project's repositories/i, /no repositories yet/i],
];

describe.each(CASES)("%s", (_label, render, errorCopy, emptyCopy) => {
  it("says the request failed instead of showing an empty state", async () => {
    renderWithProviders(render());
    await waitFor(() => expect(screen.getByText(errorCopy)).toBeTruthy());
    expect(screen.queryByText(emptyCopy)).toBeNull();
  });

  it("surfaces the server's own words, not a generic message", async () => {
    renderWithProviders(render());
    await waitFor(() => expect(screen.getByText(/the database is unreachable/i)).toBeTruthy());
  });

  it("offers a way to try again", async () => {
    renderWithProviders(render());
    await waitFor(() => expect(screen.getByRole("button", { name: /try again/i })).toBeTruthy());
  });
});
