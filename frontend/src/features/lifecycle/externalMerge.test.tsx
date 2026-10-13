// @vitest-environment jsdom
//
// Bugs S.No 88 — a pull request merged on GitHub.
//
// A developer merging by hand is a legitimate outcome, and the team was explicit that habit
// must not change to suit the platform. But the merge gate then waited for an approval nobody
// would ever give, and the reviewer was looking at a panel asking them to approve a merge that
// had already happened, with nothing on screen saying so.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { Gates } from "./Gates";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "admin" }],
};

const mergeGate = (over: Record<string, unknown> = {}) => ({
  id: "ap1",
  run: "run-1",
  gate_type: "merge_gate",
  phase: "07_implementation",
  phase_label: "implementation",
  work_item: "wi-1",
  work_item_title: "WI-214 — Add spend export to CSV",
  required_role: "tech_lead",
  approver: null,
  approver_name: null,
  decision: "pending",
  comment: "",
  decided_at: null,
  created_at: "2026-09-01T00:00:00Z",
  merge_conflict: null,
  external_merge: null,
  ...over,
});

const MERGED = {
  merged_by: "alex-w",
  merged_at: "2026-09-07T09:41:00Z",
  pr_ref: "acme/api#88",
  detected_by: "webhook",
};

function stub(approvals: unknown[], onDecide?: (body: unknown) => void, who = me) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const u = String(url);
      const ok = (body: unknown) =>
        ({ ok: true, status: 200, statusText: "ok",
           text: async () => JSON.stringify(body) }) as Response;
      if (u.includes("/auth/me")) return ok(who);
      if (u.includes("/decide")) {
        onDecide?.({ url: u, body: JSON.parse(String(init?.body ?? "{}")) });
        return ok({ ok: true });
      }
      if (u.includes("/approvals/")) return ok(approvals);
      return ok([]);
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the merge gate on a pull request merged outside the platform", () => {
  it("says so, and says who merged it and when", async () => {
    stub([mergeGate({ external_merge: MERGED })]);
    renderWithProviders(<Gates />, { route: "/gates" });

    await waitFor(() => expect(screen.getByText(/Already merged on GitHub/)).toBeDefined());
    const panel = document.body.textContent ?? "";
    expect(panel).toContain("alex-w");
    expect(panel).toContain("acme/api#88");
    expect(panel).toMatch(/merged outside the platform/);
  });

  it("asks you to acknowledge, not to approve", async () => {
    stub([mergeGate({ external_merge: MERGED })]);
    renderWithProviders(<Gates />, { route: "/gates" });

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Acknowledge merge & complete/ })).toBeDefined(),
    );
    // "Approve" is the wrong word for something already done.
    expect(screen.queryByRole("button", { name: /^Approve$/ })).toBeNull();
  });

  it("acknowledging goes through the SAME decision endpoint", async () => {
    // The whole safety argument rests on this: nothing new decides a gate. Same endpoint, same
    // role check, same ledger event, same signal to the workflow — only the wording changed.
    const calls: unknown[] = [];
    stub([mergeGate({ external_merge: MERGED })], (c) => calls.push(c));
    const user = userEvent.setup();
    renderWithProviders(<Gates />, { route: "/gates" });

    await user.click(
      await screen.findByRole("button", { name: /Acknowledge merge & complete/ }),
    );

    await waitFor(() => expect(calls.length).toBe(1));
    const call = calls[0] as { url: string; body: { decision: string } };
    expect(call.url).toContain("/approvals/ap1/decide");
    expect(call.body.decision).toBe("approved");
  });

  it("an ordinary merge gate is completely unchanged", async () => {
    stub([mergeGate()]);
    renderWithProviders(<Gates />, { route: "/gates" });

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^Approve$/ })).toBeDefined(),
    );
    expect(screen.queryByText(/Already merged on GitHub/)).toBeNull();
    expect(screen.queryByRole("button", { name: /Acknowledge/ })).toBeNull();
  });

  it("tells someone who cannot decide it, too", async () => {
    // Found live: the notice sat only in the panel for whoever holds the role, so for
    // everybody else the screen still said nothing — the original bug, kept alive for all
    // but one person.
    const onlooker = {
      ...me,
      user: { ...me.user, is_tenant_admin: false },
      memberships: [{ project_id: "p1", project_name: "Platform", role: "engineer" }],
    };
    stub([mergeGate({ external_merge: MERGED })], undefined, onlooker);
    renderWithProviders(<Gates />, { route: "/gates" });

    // Screen Words group 3 reworded this banner: it names the role properly and says an admin
    // can decide too. What this test is about is unchanged — an onlooker is told they may read it.
    await waitFor(() => expect(screen.getByText(/You can read it/)).toBeDefined());
    expect(screen.getByText(/Already merged on GitHub/)).toBeDefined();
    expect(document.body.textContent ?? "").toContain("alex-w");
  });

  it("a merge conflict still shows its own explanation", async () => {
    // The two notes are different situations and must not be confused: a conflict means the
    // merge did NOT happen, an external merge means it already did.
    stub([mergeGate({ merge_conflict: "two branches touched the same file" })]);
    renderWithProviders(<Gates />, { route: "/gates" });

    await waitFor(() => expect(screen.getByText(/Merge paused/)).toBeDefined());
    expect(screen.queryByText(/Already merged on GitHub/)).toBeNull();
  });
});
