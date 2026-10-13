// @vitest-environment jsdom
//
// Reopening cancelled work (2026-09-30).
//
// The team asked whether a work item can be deleted. It cannot, on purpose — items are referenced
// by runs, gates, artifacts, trace edges and ledger events, and a provenance platform that offers
// to destroy that history is not one. The honest answer is this instead: cancelling is reversible.
//
// So two things are pinned. It sends `proposed` and nothing else, because that is the only move
// the server's allowlist offers out of `cancelled` and the dialog's promise ("back on the board
// as a draft") has to match what it actually does. And it says the consequence for a defect
// BEFORE the decision, the same way the cancel dialog does — reopening re-blocks somebody else's
// review, and that person is not in the room.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { ReopenWorkItem } from "./ReopenWorkItem";
import { WorkItemsBoard } from "./WorkItemsBoard";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "tech_lead" }],
};

const card = (over: Record<string, unknown> = {}) => ({
  id: "wi-1", key: "WI-1", number: 1, project: "p1", feature_stream: "",
  type: "task", state: "in_progress", created_at: "2026-09-01T00:00:00Z",
  title: "Export to CSV", current_phase: "07_implementation", artifact_count: 0,
  ...over,
});

function stub(routes: Record<string, unknown> = {},
              writes: Array<{ url: string; body: unknown }> = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const u = String(url);
      const ok = (body: unknown) =>
        ({ ok: true, status: 200, statusText: "ok",
           text: async () => JSON.stringify(body) }) as Response;
      if ((init?.method ?? "GET").toUpperCase() !== "GET") {
        writes.push({ url: u, body: JSON.parse(String(init?.body ?? "{}")) });
        return ok({ ok: true });
      }
      if (u.includes("/auth/me")) return ok(me);
      for (const [needle, value] of Object.entries(routes)) {
        if (u.includes(needle)) return ok(value);
      }
      return ok([]);
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("the reopen dialog", () => {
  it("sends `proposed`, which is the only move out of cancelled", async () => {
    const writes: Array<{ url: string; body: unknown }> = [];
    stub({}, writes);
    const user = userEvent.setup();
    renderWithProviders(
      <ReopenWorkItem workItem={{ id: "wi-1", key: "WI-1", title: "Export to CSV", type: "task" }}
                      onClose={() => {}} />,
    );

    await user.click(screen.getByRole("button", { name: "Yes, reopen" }));

    await waitFor(() => expect(writes.length).toBe(1));
    expect(writes[0].url).toContain("/work-items/wi-1/transition/");
    expect(writes[0].body).toMatchObject({ to_state: "proposed" });
  });

  it("needs no reason, and sends one when it is given", async () => {
    // Only cancelling requires a reason: it is the record of a decision that work will not
    // happen. Bringing it back needs no defence — but "cancelled by mistake" is worth keeping.
    const writes: Array<{ url: string; body: unknown }> = [];
    stub({}, writes);
    const user = userEvent.setup();
    renderWithProviders(
      <ReopenWorkItem workItem={{ id: "wi-1", key: "WI-1", title: "X", type: "task" }}
                      onClose={() => {}} />,
    );

    await user.type(screen.getByLabelText(/Why is it coming back/), "Cancelled by mistake");
    await user.click(screen.getByRole("button", { name: "Yes, reopen" }));

    await waitFor(() => expect(writes.length).toBe(1));
    expect(writes[0].body).toMatchObject({ to_state: "proposed",
                                           reason: "Cancelled by mistake" });
  });

  it("says it will not resume the phase it was on", async () => {
    // The one thing a person could reasonably expect and will not get. Said in the dialog rather
    // than discovered afterwards on a board where the item sits in Backlog.
    stub();
    renderWithProviders(
      <ReopenWorkItem workItem={{ id: "wi-1", key: "WI-1", title: "X", type: "task" }}
                      onClose={() => {}} />,
    );

    expect(screen.getByText(/does not resume the phase/)).toBeDefined();
  });

  it("warns about the review it re-blocks, on a defect only", async () => {
    stub();
    const { rerender } = renderWithProviders(
      <ReopenWorkItem workItem={{ id: "d1", key: "WI-9", title: "D", type: "defect" }}
                      onClose={() => {}} />,
    );
    expect(screen.getByText(/will need to be fixed/)).toBeDefined();

    rerender(
      <ReopenWorkItem workItem={{ id: "wi-1", key: "WI-1", title: "T", type: "task" }}
                      onClose={() => {}} />,
    );
    expect(screen.queryByText(/will need to be fixed/)).toBeNull();
  });

  it("does not close on a refusal, and puts the refusal on screen", async () => {
    // A reopen is tech_lead or admin, same bar as cancelling. Closing the dialog on a 403 would
    // leave the user believing it worked.
    const onClose = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
        const u = String(url);
        if (u.includes("/auth/me")) {
          return ({ ok: true, status: 200, statusText: "ok",
                    text: async () => JSON.stringify(me) }) as Response;
        }
        if ((init?.method ?? "GET").toUpperCase() !== "GET") {
          return ({ ok: false, status: 403, statusText: "Forbidden",
                    text: async () => JSON.stringify(
                      { detail: "You don't have permission to do that." }) }) as Response;
        }
        return ({ ok: true, status: 200, statusText: "ok",
                  text: async () => "[]" }) as Response;
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <ReopenWorkItem workItem={{ id: "wi-1", key: "WI-1", title: "X", type: "task" }}
                      onClose={onClose} />,
    );

    await user.click(screen.getByRole("button", { name: "Yes, reopen" }));

    await waitFor(() => expect(screen.getByText(/Could not reopen this item/)).toBeDefined());
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("finding a cancelled item to reopen", () => {
  it("offers Reopen on a cancelled row, and Cancel on a live one", async () => {
    // The board hides cancelled work behind a "N cancelled hidden" chip, and that filtered list
    // is the only place a mis-cancelled item can be found again — so it is where the undo lives.
    localStorage.setItem("selectedProjectId", "p1");
    stub({ "/work-items": [card(), card({ id: "wi-2", key: "WI-2", title: "Dropped idea",
                                          state: "cancelled" })] });
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard forceView="list" />);

    // Cancelled work is hidden by default; the count is the way back to it.
    await user.click(await screen.findByRole("button", { name: /1 cancelled hidden/ }));
    await waitFor(() => expect(screen.getByText("Dropped idea")).toBeDefined());

    await user.click(screen.getByRole("button", { name: /Actions for WI-2/ }));
    expect(screen.getByRole("menuitem", { name: /Reopen/ })).toBeDefined();
    expect(screen.queryByRole("menuitem", { name: /Cancel/ })).toBeNull();
  });

  it("still offers Cancel on a live row", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stub({ "/work-items": [card()] });
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard forceView="list" />);

    await waitFor(() => expect(screen.getByText("Export to CSV")).toBeDefined());

    await user.click(screen.getByRole("button", { name: /Actions for WI-1/ }));
    expect(screen.getByRole("menuitem", { name: /Cancel/ })).toBeDefined();
    expect(screen.queryByRole("menuitem", { name: /Reopen/ })).toBeNull();
  });
});
