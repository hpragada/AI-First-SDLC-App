// @vitest-environment jsdom
//
// Bugs S.No 76 / SCREEN_BUILD_MAP S-15 + S-16 — the edit surface that was specified, built on the
// server, and then never given a screen.
//
// Three things are pinned here, and the middle one is why the file exists:
//
//   1. The form opens on what the item actually holds, so an edit starts from the truth rather
//      than from an empty box a user would have to retype.
//   2. **Only what changed is sent.** A PATCH is a partial update: sending the description back
//      unchanged makes a title fix look, in the item's history, like somebody rewrote both.
//   3. Nothing can save an empty title. Every other screen falls back to the title when it has
//      nothing else to show, so blanking it is never an edit anybody meant to make.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { EditWorkItem } from "./EditWorkItem";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "tech_lead" }],
};

const item = {
  id: "wi-1",
  key: "WI-1",
  title: "Export to CSV",
  description: "Users want their board as a spreadsheet.",
};

function stub(writes: Array<{ url: string; method: string; body: unknown }> = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const u = String(url);
      const method = (init?.method ?? "GET").toUpperCase();
      const ok = (body: unknown) =>
        ({ ok: true, status: 200, statusText: "ok",
           text: async () => JSON.stringify(body) }) as Response;
      if (method !== "GET") {
        writes.push({ url: u, method, body: JSON.parse(String(init?.body ?? "{}")) });
        return ok({ ok: true });
      }
      if (u.includes("/auth/me")) return ok(me);
      return ok([]);
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("the edit dialog", () => {
  it("opens on what the item already says", () => {
    stub();
    renderWithProviders(<EditWorkItem workItem={item} onClose={() => {}} />);

    expect(screen.getByDisplayValue("Export to CSV")).toBeDefined();
    expect(screen.getByDisplayValue("Users want their board as a spreadsheet.")).toBeDefined();
  });

  it("sends a PATCH carrying only the field that changed", async () => {
    const writes: Array<{ url: string; method: string; body: unknown }> = [];
    stub(writes);
    const user = userEvent.setup();
    renderWithProviders(<EditWorkItem workItem={item} onClose={() => {}} />);

    await user.clear(screen.getByDisplayValue("Export to CSV"));
    await user.type(screen.getByLabelText(/Title/), "Export the board to CSV");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(writes.length).toBe(1));
    expect(writes[0].method).toBe("PATCH");
    expect(writes[0].url).toContain("/work-items/wi-1/");
    expect(writes[0].body).toEqual({ title: "Export the board to CSV" });
  });

  it("adds a description to an item that has none", async () => {
    // The case the QA team actually hit: an item created with an empty description, and no way
    // to put one in afterwards. This is the half of that fix that lives on an existing item.
    const writes: Array<{ url: string; method: string; body: unknown }> = [];
    stub(writes);
    const user = userEvent.setup();
    renderWithProviders(
      <EditWorkItem workItem={{ ...item, description: "" }} onClose={() => {}} />,
    );

    await user.type(screen.getByLabelText(/Description/), "Cap requests at 100 a minute.");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(writes.length).toBe(1));
    expect(writes[0].body).toEqual({ description: "Cap requests at 100 a minute." });
  });

  it("will not save until something has actually changed", async () => {
    // Typing a word and deleting it again is back to unchanged — the comparison is against what
    // the item holds, not against whether the field has been touched.
    stub();
    const user = userEvent.setup();
    renderWithProviders(<EditWorkItem workItem={item} onClose={() => {}} />);

    const save = screen.getByRole("button", { name: "Save changes" });
    expect(save).toHaveProperty("disabled", true);

    await user.type(screen.getByLabelText(/Title/), "!");
    expect(screen.getByRole("button", { name: "Save changes" })).toHaveProperty("disabled", false);

    await user.keyboard("{Backspace}");
    expect(screen.getByRole("button", { name: "Save changes" })).toHaveProperty("disabled", true);
  });

  it("will not save an empty title", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<EditWorkItem workItem={item} onClose={() => {}} />);

    await user.clear(screen.getByLabelText(/Title/));

    expect(screen.getByRole("button", { name: "Save changes" })).toHaveProperty("disabled", true);
  });

  it("closes without sending anything when the edit is discarded", async () => {
    const writes: Array<{ url: string; method: string; body: unknown }> = [];
    stub(writes);
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderWithProviders(<EditWorkItem workItem={item} onClose={onClose} />);

    await user.type(screen.getByLabelText(/Title/), " and PDF");
    await user.click(screen.getByRole("button", { name: "Discard" }));

    expect(onClose).toHaveBeenCalled();
    expect(writes.length).toBe(0);
  });
});
