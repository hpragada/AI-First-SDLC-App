// @vitest-environment jsdom
/**
 * N2 — a link's text is a promise.
 *
 * Across this app the promise was routinely broken: the text named one thing, the link opened a
 * list of everything, and the user re-found by hand what they had just been looking at. The two
 * tests marked ★ are the ones that must FAIL on the code before this change, or the fix is not
 * proven — one for the wrong-item selection, one for the destination that denied the run existed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";

import { renderWithProviders } from "./test/utils";
import { Gates } from "./features/lifecycle/Gates";
import { Clarifications } from "./features/lifecycle/Clarifications";
import { OfflineTakeover } from "./features/observability/OfflineTakeover";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "admin" }],
};

const approval = (id: string, title: string) => ({
  id,
  run: `run-${id}`,
  gate_type: "phase_gate",
  phase: "03_prd",
  phase_label: "prd",
  work_item: `wi-${id}`,
  work_item_title: title,
  required_role: "product_owner",
  approver: null,
  approver_name: null,
  decision: "pending",
  comment: "",
  decided_at: null,
  created_at: "2026-09-01T00:00:00Z",
  merge_conflict: null,
});

const clarification = (id: string, text: string) => ({
  id,
  run: `run-${id}`,
  work_item: `wi-${id}`,
  work_item_title: "Add login",
  phase: "prd",
  status: "pending",
  context: "",
  questions: [{ id: "q1", text, tier: 1, kind: "text" }],
  answers: {},
  created_at: "2026-09-01T00:00:00Z",
});

/** Route every request to a canned body, keyed on the path. */
function stub(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/auth/me")) {
        return { ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(me) } as Response;
      }
      for (const [needle, body] of Object.entries(routes)) {
        if (u.includes(needle)) {
          return { ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) } as Response;
        }
      }
      return { ok: true, status: 200, statusText: "ok", text: async () => "[]" } as Response;
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a gate deep link", () => {
  beforeEach(() =>
    stub({ "/approvals/": [approval("ap1", "First — Checkout"), approval("ap2", "Second — Search")] }),
  );

  it("★ selects the gate the link names, not the first pending one", async () => {
    renderWithProviders(<Gates />, { route: "/gates?gate=ap2" });
    // The selected gate's own panel names its work item. Before this change the screen always
    // selected `pending[0]`, so clicking "Review" beside the second gate opened the first —
    // and a reviewer could approve the wrong one having read the right one.
    await waitFor(() => expect(screen.getAllByText(/Second — Search/).length).toBeGreaterThan(0));
    // Both gates appear in the LIST either way, so the list is no evidence. What proves the fix
    // is which row is SELECTED — the highlighted one must be the gate the URL named. (The tint
    // moved from an inline style to a class when the whole row became selectable, S.No 189.)
    const highlighted = Array.from(document.querySelectorAll(".table__row--sel"));
    expect(highlighted.length).toBe(1);
    expect(highlighted[0].textContent).toContain("Second — Search");
    expect(highlighted[0].textContent).not.toContain("First — Checkout");
  });

  it("with no param behaves exactly as before", async () => {
    renderWithProviders(<Gates />, { route: "/gates" });
    await waitFor(() => expect(screen.getAllByText(/First — Checkout/).length).toBeGreaterThan(0));
    expect(screen.queryByText(/no longer pending/i)).toBeNull();
  });

  it("naming a gate that is no longer pending selects nothing and says so", async () => {
    renderWithProviders(<Gates />, { route: "/gates?gate=ap-decided-yesterday" });
    await waitFor(() => expect(screen.getByText(/no longer pending/i)).toBeTruthy());
    expect(document.querySelectorAll('[style*="brand-orange-50"]').length).toBe(0);
  });
});

describe("a clarification deep link", () => {
  beforeEach(() =>
    stub({
      "/clarifications/": [
        clarification("c1", "Which payment providers must we support?"),
        clarification("c2", "Should guests be able to check out?"),
      ],
    }),
  );

  it("opens the question the link names", async () => {
    renderWithProviders(<Clarifications />, { route: "/clarifications?clarification=c2" });
    await waitFor(() => expect(screen.getByText(/Should guests be able to check out/)).toBeTruthy());
    expect(screen.queryByText(/Which payment providers/)).toBeNull();
  });

  it("with no param behaves exactly as before", async () => {
    renderWithProviders(<Clarifications />, { route: "/clarifications" });
    await waitFor(() => expect(screen.getByText(/Which payment providers/)).toBeTruthy());
  });

  it("naming an answered question opens nothing rather than the wrong box", async () => {
    renderWithProviders(<Clarifications />, { route: "/clarifications?clarification=c-answered" });
    await waitFor(() => expect(screen.getByText(/already been answered/i)).toBeTruthy());
    expect(screen.queryByText(/Which payment providers/)).toBeNull();
  });
});

describe("the recovery screen", () => {
  it("★ shows the run the link names instead of 'No parked runs'", async () => {
    stub({
      "/runs/r-parked": {
        id: "r-parked",
        work_item: "wi-1",
        agent_phase: "prd",
        status: "stalled",
        engine: "claude",
        started_at: "2026-09-01T00:00:00Z",
        outputs: { error: "the companion went offline", resumable: true },
      },
    });
    renderWithProviders(<OfflineTakeover />, { route: "/recovery?run=r-parked" });
    // Before this change `?run=` was read and then thrown away — `parkedRun` was forced to
    // undefined whenever the param was present, and the screen denied the run existed.
    await waitFor(() => expect(screen.queryByText(/No parked runs/i)).toBeNull());
    expect(screen.queryByText(/Checking for parked runs/i)).toBeNull();
  });
});
