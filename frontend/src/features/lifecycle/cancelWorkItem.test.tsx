// @vitest-environment jsdom
//
// Bugs S.No 140 — closing work that cannot be built.
//
// The frontend half. Three things are being pinned:
//
//   1. A cancelled item does not LIE about itself. The board's badge chain ended in a
//      fall-through that labelled anything it did not recognise "Draft", so a cancelled item —
//      and, it turned out, an item in review, blocked, or accepted — rendered as a draft. A
//      board that calls abandoned work a draft is a board that gets planned against.
//   2. A cancelled item is off the board by default, but never invisible. Cancelling exists to
//      clear the board; a board that silently drops rows is a board whose counts nobody can
//      reconcile, so the number hidden is stated and one click brings them back.
//   3. A cancelled item stops offering work. Trigger/Retry buttons on something nobody intends
//      to build are the same mistake in a different place.
import { afterEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { CancelWorkItem } from "./CancelWorkItem";
import { WorkItemDefect } from "./WorkItemDefect";
import { WorkItemTask } from "./WorkItemTask";
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

/** Reads resolve from `routes` by URL substring, in insertion order — so a specific key like
 *  "/lifecycle" must be listed BEFORE "/work-items/", which would otherwise swallow it.
 *  Writes are recorded and answered 200. */
function stub(routes: Record<string, unknown>, writes: Array<{ url: string; body: unknown }> = []) {
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

/** The detail screens read their id from the route, so they need a real route to sit on —
 *  rendered bare, `useParams` yields nothing and every one of them says "not found". */
function renderAt(element: React.ReactElement) {
  return renderWithProviders(
    <Routes>
      <Route path="/work-items/:id" element={element} />
    </Routes>,
    { route: "/work-items/wi-1" },
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

// ── 1 + 2. the board ────────────────────────────────────────────────
describe("the work items board", () => {
  it("hides cancelled items, and says how many it is hiding", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stub({ "/work-items": [card(), card({ id: "wi-2", key: "WI-2", title: "Dropped idea",
                                          state: "cancelled" })] });
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Export to CSV")).toBeDefined());
    expect(screen.queryByText("Dropped idea")).toBeNull();
    // Hidden, never disappeared: the count is on screen and it is a way back in.
    expect(screen.getByRole("button", { name: /1 cancelled hidden/ })).toBeDefined();
  });

  it("brings them back when asked", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stub({ "/work-items": [card(), card({ id: "wi-2", key: "WI-2", title: "Dropped idea",
                                          state: "cancelled" })] });
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await user.click(await screen.findByRole("button", { name: /1 cancelled hidden/ }));

    await waitFor(() => expect(screen.getByText("Dropped idea")).toBeDefined());
    // ...and showing them means showing ONLY them, which is what the filter says it does.
    expect(screen.queryByText("Export to CSV")).toBeNull();
  });

  it("says nothing when there is nothing to hide", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stub({ "/work-items": [card()] });
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Export to CSV")).toBeDefined());
    expect(screen.queryByText(/cancelled hidden/)).toBeNull();
  });

  it.each([
    ["cancelled", "Cancelled"],
    ["in_review", "In review"],
    ["blocked", "Blocked"],
    ["accepted", "Accepted"],
  ])("labels a %s item %s rather than 'Draft'", async (state, label) => {
    // Every one of these fell through to "Draft" before. The list view is used because it
    // renders the badge in a cell rather than on a card, so the text is unambiguous.
    localStorage.setItem("selectedProjectId", "p1");
    stub({ "/work-items": [card({ state, title: "An item" })] });
    renderWithProviders(<WorkItemsBoard forceView="list" />);

    // A cancelled item is filtered off the default board, so ask for it explicitly.
    if (state === "cancelled") {
      const user = userEvent.setup();
      await user.click(await screen.findByRole("button", { name: /cancelled hidden/ }));
    }
    await waitFor(() => expect(screen.getByText("An item")).toBeDefined());
    const row = screen.getByText("An item").closest("tr") as HTMLElement;
    expect(within(row).getByText(label)).toBeDefined();
    expect(within(row).queryByText("Draft")).toBeNull();
  });
});

// ── the row action in the list view (9G-A) ──────────────────────────
describe("the list view's row menu", () => {
  it("offers Cancel on a live row, and opens the dialog", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stub({ "/work-items": [card()] });
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard forceView="list" />);

    // Named by ROW, not "Actions" forty times over — a screen-reader user has to be able to
    // tell which row they are about to act on.
    await user.click(await screen.findByRole("button", { name: "Actions for WI-1" }));
    await user.click(screen.getByRole("menuitem", { name: "Cancel…" }));

    await waitFor(() =>
      expect(screen.getByText(/Cancel Export to CSV\?/)).toBeDefined());
  });

  it("offers no Cancel on a row that is already finished or abandoned", async () => {
    // Nothing left to cancel — and the menu still exists, because Open always makes sense.
    localStorage.setItem("selectedProjectId", "p1");
    stub({ "/work-items": [card({ state: "done" })] });
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard forceView="list" />);

    await user.click(await screen.findByRole("button", { name: "Actions for WI-1" }));

    expect(screen.getByRole("menuitem", { name: "Open" })).toBeDefined();
    expect(screen.queryByRole("menuitem", { name: "Cancel…" })).toBeNull();
  });

  it("closes on Escape", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stub({ "/work-items": [card()] });
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard forceView="list" />);

    await user.click(await screen.findByRole("button", { name: "Actions for WI-1" }));
    expect(screen.getByRole("menu")).toBeDefined();

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
  });
});

// ── 3. the detail screens stop offering work ────────────────────────
describe("a cancelled work item", () => {
  it("offers no Trigger Fix on a defect, and does not call it Open", async () => {
    stub({ "/lifecycle": { nodes: [], loops: [], children: [] },
           "/work-items/": card({ type: "defect", state: "cancelled",
                                  title: "Flaky login test" }) });
    renderAt(<WorkItemDefect />);

    await waitFor(() => expect(screen.getByText("Flaky login test")).toBeDefined());
    expect(screen.getAllByText("Cancelled").length).toBeGreaterThan(0);
    // The bug: a cancelled defect rendered a red "Open" badge and a Trigger Fix button.
    expect(screen.queryByText("Open")).toBeNull();
    expect(screen.queryByRole("button", { name: /Trigger Fix/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Cancel work item/ })).toBeNull();
  });

  it("offers no Trigger phase on a task", async () => {
    stub({ "/lifecycle": { nodes: [], loops: [], children: [] },
           "/work-items/": card({ state: "cancelled" }) });
    renderAt(<WorkItemTask />);

    await waitFor(() => expect(screen.getByText("Export to CSV")).toBeDefined());
    expect(screen.queryByRole("button", { name: /Trigger phase/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Cancel work item/ })).toBeNull();
  });

  it("still offers both on a live task", async () => {
    // The guard has to be scoped, or it would take the buttons off every task in the platform.
    stub({ "/lifecycle": { nodes: [], loops: [], children: [] },
           "/work-items/": card() });
    renderAt(<WorkItemTask />);

    await waitFor(() => expect(screen.getByText("Export to CSV")).toBeDefined());
    expect(screen.getByRole("button", { name: /Trigger phase/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /Cancel work item/ })).toBeDefined();
  });
});

// ── the dialog ──────────────────────────────────────────────────────
describe("the cancel dialog", () => {
  it("sends the chosen reason, and cancelling is what it sends", async () => {
    const writes: Array<{ url: string; body: unknown }> = [];
    stub({}, writes);
    const user = userEvent.setup();
    renderWithProviders(
      <CancelWorkItem workItem={{ id: "wi-1", key: "WI-1", title: "Export to CSV", type: "task" }}
                      onClose={() => {}} />,
    );

    await user.click(screen.getByRole("button", { name: "Cancel this item" }));

    await waitFor(() => expect(writes.length).toBe(1));
    expect(writes[0].url).toContain("/work-items/wi-1/transition/");
    expect(writes[0].body).toMatchObject({ to_state: "cancelled",
                                           reason: "Duplicate of another item" });
  });

  it("will not submit an empty free-text reason", async () => {
    // The server requires a reason and this must not send a request it knows will fail —
    // "Something else" with nothing typed is exactly the case a busy person produces.
    const writes: Array<{ url: string; body: unknown }> = [];
    stub({}, writes);
    const user = userEvent.setup();
    renderWithProviders(
      <CancelWorkItem workItem={{ id: "wi-1", key: "WI-1", title: "X", type: "task" }}
                      onClose={() => {}} />,
    );

    await user.selectOptions(screen.getByLabelText("Why?"), "Something else");
    await user.click(screen.getByRole("button", { name: "Cancel this item" }));

    expect(writes.length).toBe(0);
  });

  it("warns about the gate before the decision, on a defect only", async () => {
    stub({});
    const { rerender } = renderWithProviders(
      <CancelWorkItem workItem={{ id: "d1", key: "WI-9", title: "D", type: "defect" }}
                      onClose={() => {}} />,
    );
    expect(screen.getByText(/releases that gate/)).toBeDefined();

    rerender(
      <CancelWorkItem workItem={{ id: "wi-1", key: "WI-1", title: "T", type: "task" }}
                      onClose={() => {}} />,
    );
    expect(screen.queryByText(/releases that gate/)).toBeNull();
  });
});

// ── the words on the cancel dialog (2026-09-30) ─────────────────────
//
// The second sentence used to read "It is not the same as marking it done, and reports count the
// two separately." The team could not make sense of it, and it was wrong twice: it asked the
// reader to know what our reports do, and it predated Reopen — so it never answered the question
// somebody about to cancel is actually holding, which is whether this is permanent.
describe("what the cancel dialog says", () => {
  it("says it is not finishing, and that it can be undone", async () => {
    stub({});
    renderWithProviders(
      <CancelWorkItem workItem={{ id: "wi-1", key: "WI-1", title: "X", type: "task" }}
                      onClose={() => {}} />,
    );

    const said = document.body.textContent ?? "";
    expect(said).toContain("not going to happen");
    expect(said).toContain("not the same as finishing it");
    expect(said).toContain("you can reopen it later");
    // The sentence the team could not read is gone, and stays gone.
    expect(said).not.toContain("reports count the two separately");
  });
});

// ── no raw UUID on a work item screen (2026-09-30) ──────────────────
//
// `WorkItemSerializer.key` exists with the comment "so the UI never has to show the UUID", and
// these two screens showed it anyway — the route id in the breadcrumb, and the parent's first
// eight characters beside it, presented as a link.
const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

describe("work item screens never print an id", () => {
  it("names a task by its key, not the id in the address bar", async () => {
    stub({ "/lifecycle": { nodes: [], loops: [], children: [] },
           "/work-items/": card({ key: "WI-266", title: "People Desk Security Check" }) });
    renderAt(<WorkItemTask />);

    await waitFor(() => expect(screen.getByText("People Desk Security Check")).toBeDefined());
    const crumbs = document.querySelector(".breadcrumb") as HTMLElement;
    expect(crumbs.textContent).toContain("WI-266");
    expect(crumbs.textContent).not.toMatch(UUID_RE);
  });

  it("names a task's parent by its key", async () => {
    stub({ "/lifecycle": { nodes: [], loops: [], children: [] },
           "/work-items/": card({ key: "WI-266", title: "Child task",
                                  parent: "65db8214-f26c-4246-b63e-81297b5f50df",
                                  parent_key: "WI-260" }) });
    renderAt(<WorkItemTask />);

    await waitFor(() => expect(screen.getByText("Child task")).toBeDefined());
    expect(document.body.textContent).toContain("WI-260");
    expect(document.body.textContent).not.toContain("65db8214");
  });

  it("says nothing about a parent it cannot name", async () => {
    // An older API sending `parent` with no `parent_key`. "↖ 65db8214" is not a name.
    stub({ "/lifecycle": { nodes: [], loops: [], children: [] },
           "/work-items/": card({ key: "WI-266", title: "Child task",
                                  parent: "65db8214-f26c-4246-b63e-81297b5f50df" }) });
    renderAt(<WorkItemTask />);

    await waitFor(() => expect(screen.getByText("Child task")).toBeDefined());
    expect(document.body.textContent).not.toContain("65db8214");
  });

  it("names a defect by its key too", async () => {
    stub({ "/lifecycle": { nodes: [], loops: [], children: [] },
           "/work-items/": card({ key: "WI-301", title: "Signature check rejects valid events",
                                  type: "defect" }) });
    renderAt(<WorkItemDefect />);

    await waitFor(() =>
      expect(screen.getByText("Signature check rejects valid events")).toBeDefined());
    const crumbs = document.querySelector(".breadcrumb") as HTMLElement;
    expect(crumbs.textContent).toContain("WI-301");
    expect(crumbs.textContent).not.toMatch(UUID_RE);
  });
});
