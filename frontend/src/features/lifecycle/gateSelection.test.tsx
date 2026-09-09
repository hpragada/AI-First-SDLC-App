// @vitest-environment jsdom
//
// Bugs S.No 189 and 250 — picking a gate from the list, and being told the truth afterwards.
//
// S.No 189 (reopened 2026-09-09; closed too early on 2026-09-07 against a button in one
// column rather than a selectable row). The gates screen is a list beside a decision panel, which only works if the list is
// how you choose what the panel shows. It wasn't. The only thing that selected anything was a
// small button in the first column; the work-item name — the obvious thing to click — was a link
// that left the screen for the work-item page. So a reviewer with five gates could not do the one
// thing the layout exists for: read the list, pick one, decide it, pick the next.
//
// S.No 250. The confirmation after a decision was driven by the mutation's own success flag and
// mounted INSIDE the panel, so it belonged to the button press rather than to the gate. Approve
// the first gate and it leaves the pending list; the panel auto-selects the next one; and the
// banner came along, announcing "Decision recorded" on a gate nobody had decided. A reviewer
// working through a queue reads that and moves on, leaving it pending. It was visible in the
// team's own screenshot: a green banner naming WI-96 above a panel showing WI-95.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { Gates } from "./Gates";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "admin" }],
};

const gate = (id: string, title: string, over: Record<string, unknown> = {}) => ({
  id, run: `run-${id}`, gate_type: "merge_gate", phase: "07_implementation",
  phase_label: "implementation", work_item: `wi-${id}`, work_item_title: title,
  required_role: "tech_lead", approver: null, approver_name: null,
  decision: "pending", comment: "", decided_at: null,
  created_at: "2026-09-04T00:00:00Z", merge_conflict: null, external_merge: null,
  run_paused: false,
  ...over,
});

const GATES = [
  gate("ap1", "WI-96 · TASK-039: Leave policy configuration"),
  gate("ap2", "WI-95 · TASK-038: Comp-off grant API"),
  gate("ap3", "WI-93 · TASK-036: Holiday calendar import"),
];

/** `decided` drops the approved gate from the list the way the server would, so the panel
 *  re-selects on its own — which is the exact condition S.No 250 lived in. */
function stubGates(all: unknown[], decided: { current: string[] }) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: RequestInfo | URL) => {
      const u = String(url);
      const ok = (body: unknown) =>
        ({ ok: true, status: 200, statusText: "ok",
           text: async () => JSON.stringify(body) }) as Response;
      if (u.includes("/auth/me")) return ok(me);
      if (u.includes("/decide")) return ok({ ok: true });
      if (u.includes("/approvals/")) {
        return ok((all as Array<{ id: string }>).filter((a) => !decided.current.includes(a.id)));
      }
      return ok([]);
    }),
  );
}

/** The LIST row for a gate. The selected gate's name appears twice on screen by design — once in
 *  the row, once as the decision panel's heading — so this picks the one inside the table. */
const rowFor = (text: string) =>
  screen
    .getAllByText(text)
    .map((node) => node.closest("tr"))
    .find(Boolean) as HTMLElement;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("picking a gate from the list (S.No 189)", () => {
  it("★ clicking the work item selects that gate instead of leaving the screen", async () => {
    // The bug, stated as a test: the work-item cell used to be a link, so the natural click
    // navigated away from the only screen where the gate can be decided.
    localStorage.setItem("selectedProjectId", "p1");
    stubGates(GATES, { current: [] });
    renderWithProviders(<Gates />);

    await waitFor(() => expect(screen.getByText("Pending approvals")).toBeDefined());
    const cell = screen.getByText("WI-93 · TASK-036: Holiday calendar import");
    expect(cell.closest("a")).toBeNull();

    await userEvent.click(cell);
    // The panel — not the browser — moved. The heading in the decision card is the gate now open.
    await waitFor(() =>
      expect(
        screen.getAllByText("WI-93 · TASK-036: Holiday calendar import").length,
      ).toBeGreaterThan(1));
  });

  it("marks the selected row, and only that row", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stubGates(GATES, { current: [] });
    renderWithProviders(<Gates />);

    await waitFor(() => expect(screen.getByText("Pending approvals")).toBeDefined());
    // First gate is selected by default, so the panel is never empty on arrival.
    expect(rowFor("WI-96 · TASK-039: Leave policy configuration").className).toContain("table__row--sel");
    expect(rowFor("WI-95 · TASK-038: Comp-off grant API").className).not.toContain("table__row--sel");

    await userEvent.click(screen.getByText("WI-95 · TASK-038: Comp-off grant API"));
    await waitFor(() =>
      expect(rowFor("WI-95 · TASK-038: Comp-off grant API").className).toContain("table__row--sel"));
    expect(rowFor("WI-96 · TASK-039: Leave policy configuration").className).not.toContain("table__row--sel");
  });

  it("is operable from the keyboard, which is not optional in this product", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stubGates(GATES, { current: [] });
    renderWithProviders(<Gates />);

    await waitFor(() => expect(screen.getByText("Pending approvals")).toBeDefined());
    const first = rowFor("WI-96 · TASK-039: Leave policy configuration");
    // One tab stop for the whole list (roving tabindex), not one per row.
    expect(first.getAttribute("tabindex")).toBe("0");
    expect(rowFor("WI-95 · TASK-038: Comp-off grant API").getAttribute("tabindex")).toBe("-1");
    expect(first.getAttribute("aria-selected")).toBe("true");

    first.focus();
    await userEvent.keyboard("{ArrowDown}");
    await waitFor(() =>
      expect(rowFor("WI-95 · TASK-038: Comp-off grant API").getAttribute("aria-selected")).toBe("true"));
  });

  it("a link inside a row still navigates, and does not also change the selection", async () => {
    // "Preview ↗" is a deliberate way out. If the row swallowed the click, or if the link also
    // selected on its way out, one of the two behaviours would be a surprise.
    localStorage.setItem("selectedProjectId", "p1");
    stubGates(GATES, { current: [] });
    renderWithProviders(<Gates />);

    await waitFor(() => expect(screen.getByText("Pending approvals")).toBeDefined());
    const third = rowFor("WI-93 · TASK-036: Holiday calendar import");
    await userEvent.click(within(third).getByRole("link", { name: /Preview/ }));
    expect(third.className).not.toContain("table__row--sel");
  });

  it("opening the work item is still one click, from the panel", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stubGates(GATES, { current: [] });
    renderWithProviders(<Gates />);

    await waitFor(() => expect(screen.getByText("Pending approvals")).toBeDefined());
    const open = screen.getByRole("link", { name: /Open work item/ });
    expect(open.getAttribute("href")).toContain("wi-ap1");
  });
});

describe("the confirmation after a decision (S.No 250)", () => {
  it("★ never claims a decision on the gate that opens next", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    const decided = { current: [] as string[] };
    stubGates(GATES, decided);
    renderWithProviders(<Gates />);

    await waitFor(() => expect(screen.getByRole("button", { name: /^Approve/ })).toBeDefined());
    decided.current = ["ap1"];
    await userEvent.click(screen.getByRole("button", { name: /^Approve/ }));

    // The confirmation names the gate it belongs to...
    await waitFor(() => expect(screen.getByText("Approved")).toBeDefined());
    expect(screen.getByText(/WI-96 · TASK-039/)).toBeDefined();
    // ...and the old in-panel banner, which is what drifted, is gone for good.
    expect(screen.queryByText("Decision recorded")).toBeNull();
    expect(screen.queryByText(/Logged with your role and comment/i)).toBeNull();
  });

  it("says a decision once, not three times", async () => {
    // Approving used to produce a page banner, an in-panel banner and a footer line — and the
    // last two duplicated by construction, because deciding clears the comment box and that is
    // exactly what flipped the footer to the duplicate wording.
    localStorage.setItem("selectedProjectId", "p1");
    stubGates(GATES, { current: [] });
    renderWithProviders(<Gates />);

    await waitFor(() => expect(screen.getByRole("button", { name: /^Approve/ })).toBeDefined());
    await userEvent.click(screen.getByRole("button", { name: /^Approve/ }));

    await waitFor(() => expect(screen.getByText("Approved")).toBeDefined());
    expect(screen.queryAllByText(/Logged with your role/i).length).toBe(0);
    expect(screen.queryAllByText(/is saved/i).length).toBe(1);
  });

  it("clears the confirmation when the reviewer moves to another gate", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    const decided = { current: [] as string[] };
    stubGates(GATES, decided);
    renderWithProviders(<Gates />);

    await waitFor(() => expect(screen.getByRole("button", { name: /^Approve/ })).toBeDefined());
    decided.current = ["ap1"];
    await userEvent.click(screen.getByRole("button", { name: /^Approve/ }));
    await waitFor(() => expect(screen.getByText("Approved")).toBeDefined());

    await userEvent.click(screen.getByText("WI-93 · TASK-036: Holiday calendar import"));
    await waitFor(() => expect(screen.queryByText("Approved")).toBeNull());
  });
});
