// @vitest-environment jsdom
//
// A person who holds more than one role on a project.
//
// Memberships are stored ONE ROW PER ROLE, and three screens treated them as one row per
// project. `selectedProject` is therefore whichever row came back first, so:
//
//   - the Gates screen compared that single role against the gate's required role and told a
//     tech lead who is also product owner "you don't hold the tech_lead role on this project",
//     hiding a decision the SERVER would have accepted (`decide_gate` checks all of a user's
//     rows, `role__in=[required, admin]`). A locked door with no lock in it.
//   - the contracts/drift screen had an identical copy of the comparison, with the same effect.
//   - the project switcher listed a project once per role.
//
// These fail without the fix, in the way a user would actually meet them.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor, within } from "@testing-library/react";

import { renderWithProviders } from "../../test/utils";
import { AppShell } from "../../components/AppShell";
import { Gates } from "./Gates";

/** Ada is product_owner AND tech_lead on the same project, and is NOT a workspace admin —
 *  the admin flag short-circuits every check here and would hide the bug. */
const multiRole = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [
    { project_id: "p1", project_name: "Platform", role: "product_owner", track: "brownfield" },
    { project_id: "p1", project_name: "Platform", role: "tech_lead", track: "brownfield" },
    { project_id: "p2", project_name: "Receipts", role: "engineer", track: "greenfield" },
  ],
};

const approval = {
  id: "ap1", run: "run-1", gate_type: "merge_gate", phase: "07_implementation",
  work_item: "wi-1", work_item_title: "WI-1 — Export to CSV",
  required_role: "tech_lead",          // Ada's SECOND row — the one nothing was looking at
  approver: null, approver_name: null, decision: "pending", comment: "",
  decided_at: null, created_at: "2026-09-01T00:00:00Z",
  merge_conflict: null, external_merge: null,
};

function stub(me: unknown, approvals: unknown[] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: RequestInfo | URL) => {
      const u = String(url);
      const ok = (body: unknown) =>
        ({ ok: true, status: 200, statusText: "ok",
           text: async () => JSON.stringify(body) }) as Response;
      if (u.includes("/auth/me")) return ok(me);
      if (u.includes("/approvals/")) return ok(approvals);
      if (u.includes("/dashboard/")) return ok({ needs_me: { gates: [], clarifications: [] } });
      return ok([]);
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("a gate whose required role is the user's SECOND role", () => {
  it("is decidable — the screen no longer disagrees with the server", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stub(multiRole, [approval]);
    renderWithProviders(<Gates />);

    // The read-only panel shows a DISABLED Approve on purpose, so "is there a button" proves
    // nothing — whether it can be pressed is the whole difference.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^Approve/ })).not.toHaveProperty(
        "disabled", true));
    // ...and the wrong answer, in the words a person actually saw, is gone. Matched on the
    // CURRENT refusal sentence (Screen Words group 3) — asserting the absence of wording that no
    // longer exists anywhere would pass for the wrong reason.
    expect(screen.queryByText(/can decide this gate/i)).toBeNull();
  });

  it("still refuses someone who genuinely lacks the role", async () => {
    // The guard has to keep biting, or this "fix" is just removing the check. Ada is only an
    // engineer on p2, and this gate needs a tech lead.
    localStorage.setItem("selectedProjectId", "p2");
    stub(multiRole, [{ ...approval, required_role: "tech_lead" }]);
    renderWithProviders(<Gates />);

    // Screen Words group 3 reworded the refusal from "you don't hold the tech_lead role" to
    // "Only a Tech Lead on this project, or an admin, can decide this gate." The guard being
    // tested is the same one; only the sentence changed.
    // The body sentence wraps the role in <strong>, so it is split across elements; the banner
    // title carries the same fact in one node.
    await waitFor(() =>
      expect(screen.getAllByText(/Waiting for a Tech Lead/i).length).toBeGreaterThan(0));
    // Present but unpressable — the screen explains rather than hiding the control.
    expect(screen.getByRole("button", { name: /^Approve/ })).toHaveProperty("disabled", true);
  });

  it("lets a workspace admin decide anything, as the server does", async () => {
    localStorage.setItem("selectedProjectId", "p2");
    stub({ ...multiRole, user: { ...multiRole.user, is_tenant_admin: true } }, [approval]);
    renderWithProviders(<Gates />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^Approve/ })).not.toHaveProperty(
        "disabled", true));
    expect(screen.queryByText(/can decide this gate/i)).toBeNull();
  });
});

describe("the project switcher", () => {
  it("lists each project once, not once per role", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stub(multiRole);
    renderWithProviders(<AppShell />);

    // Wait for the SESSION, not just the control — the shell renders the switcher before
    // /auth/me resolves, and at that moment it legitimately has no projects to list.
    await screen.findByRole("button", { name: /account menu for ada/i });
    const switcher = screen.getByRole("combobox", { name: /switch project/i });
    const options = within(switcher).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual(["Platform", "Receipts"]);
  });
});
