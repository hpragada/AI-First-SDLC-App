// @vitest-environment jsdom
/**
 * F1 — the warning about gate roles nobody holds (the team's option B+), and P4.
 *
 * The warning was drawn only when a role was empty AND no admin could approve instead. Only a
 * workspace admin can open this screen, and the platform counts any workspace admin as backup for
 * every gate — so whoever was reading the page WAS the backup, and the warning could never appear.
 * A workspace cannot lose its last admin either, so it could not appear anywhere. An unfilled role
 * showed up only as a red line at the bottom of the page, under a ten-column table, while its
 * gates quietly fell to the admins. And if it had ever appeared, its title always read
 * "No reviewer", whichever role was actually empty.
 *
 * Option B+: ONE line however many roles are empty — a new project starts with nearly all eight
 * unfilled, so naming each would be a wall of text that pushes the table off the screen. It names
 * the roles while one or two are missing and counts them beyond that.
 *
 * P4 rides along because it changes the same page head: the "Project" dropdown beside the title
 * held one option and did nothing, two inches under the top bar's real project switcher.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";

import { renderWithProviders } from "../../test/utils";
import { RolesMatrix } from "./RolesMatrix";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "SpendLog", role: "admin" }],
};

const role = (name: string, covered: boolean, note: string | null, gate_blocked = false) => ({
  role: name, covered, gate_blocked, note,
  holders: covered ? [{ user_id: "u1", name: "Ada" }] : [],
});

/** `coverage` is what GET /projects/p1/role-coverage/ answers. */
function stub(coverage: { admin_fallback: boolean; roles: unknown[] }) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;
    if (u.includes("/auth/me")) return ok(me);
    if (u.includes("/role-coverage/")) return ok(coverage);
    if (u.includes("/users/")) return ok([]);
    return ok([]);
  }));
}

const ADMIN_COVERED = (uncovered: string[]) => ({
  admin_fallback: true,
  roles: [
    role("product_owner", true, null),
    ...uncovered.map((r) => role(r, false, `no ${r} assigned — an admin can approve the gate`)),
  ],
});

beforeEach(() => localStorage.setItem("selectedProjectId", "p1"));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("the warning appears at all", () => {
  it("shows for a role nobody holds, even though an admin could approve instead", async () => {
    stub(ADMIN_COVERED(["reviewer"]));
    renderWithProviders(<RolesMatrix />);

    await waitFor(() =>
      expect(screen.getByText(/Nobody holds Reviewer on SpendLog/)).toBeDefined());
    expect(screen.getByText(/That gate falls to an admin meanwhile/)).toBeDefined();
  });

  it("says nothing when every gate role is held", async () => {
    stub({ admin_fallback: true, roles: [role("product_owner", true, null),
                                          role("reviewer", true, null)] });
    renderWithProviders(<RolesMatrix />);

    await waitFor(() => expect(screen.getByText("Gate-role coverage")).toBeDefined());
    expect(screen.queryByText(/Nobody holds/)).toBeNull();
    expect(screen.queryByText(/have nobody/)).toBeNull();
  });
});

describe("one line, whatever the number", () => {
  it("names two roles", async () => {
    stub(ADMIN_COVERED(["reviewer", "qa_lead"]));
    renderWithProviders(<RolesMatrix />);

    await waitFor(() =>
      expect(screen.getByText(/Nobody holds Reviewer or QA Lead on SpendLog/)).toBeDefined());
    expect(screen.getByText(/Those gates fall to an admin meanwhile/)).toBeDefined();
  });

  it("counts them once there are three or more, instead of listing them", async () => {
    stub(ADMIN_COVERED(["reviewer", "qa_lead", "security_engineer"]));
    renderWithProviders(<RolesMatrix />);

    await waitFor(() =>
      expect(screen.getByText(/3 roles have nobody on SpendLog/)).toBeDefined());
    expect(screen.queryByText(/Nobody holds Reviewer/)).toBeNull();
  });

  it("stays one line for a brand-new project with seven roles empty", async () => {
    stub(ADMIN_COVERED(["architect", "designer", "tech_lead", "reviewer", "qa_lead",
                        "security_engineer", "devops"]));
    renderWithProviders(<RolesMatrix />);

    const banner = await screen.findByText(/7 roles have nobody on SpendLog/);
    // The count, the consequence, and the way to the detail — and no per-role list.
    expect(banner.parentElement?.textContent).toContain("fall to an admin");
    expect(screen.getByRole("button", { name: "see gate-role coverage" })).toBeDefined();
  });

  it("never hardcodes 'No reviewer' for whichever role is missing", async () => {
    stub(ADMIN_COVERED(["devops"]));
    renderWithProviders(<RolesMatrix />);

    await waitFor(() => expect(screen.getByText(/Nobody holds DevOps on SpendLog/)).toBeDefined());
    expect(document.body.textContent).not.toMatch(/No reviewer/i);
  });
});

describe("a genuine hard block", () => {
  it("says the gate cannot be approved by anyone, and offers no 'an admin will do it'", async () => {
    stub({
      admin_fallback: false,
      roles: [role("reviewer", false, "merge gate unactionable — no Reviewer", true)],
    });
    renderWithProviders(<RolesMatrix />);

    await waitFor(() =>
      expect(screen.getByText(/That gate cannot be approved by anyone/)).toBeDefined());
    expect(screen.queryByText(/falls to an admin/)).toBeNull();
  });
});

describe("the way down to the detail", () => {
  it("points at the coverage box, which is focusable so a keyboard lands in it", async () => {
    stub(ADMIN_COVERED(["reviewer"]));
    renderWithProviders(<RolesMatrix />);

    await screen.findByText(/Nobody holds Reviewer/);
    const box = document.getElementById("gate-role-coverage");
    expect(box).not.toBeNull();
    expect(box?.getAttribute("tabindex")).toBe("-1");
    expect(box?.textContent).toContain("Gate-role coverage");
  });
});

describe("P4 — the dead project dropdown", () => {
  it("is a plain line of text now, not a second project picker", async () => {
    stub(ADMIN_COVERED([]));
    renderWithProviders(<RolesMatrix />);

    // Wait for the signed-in project to arrive, not just for the page frame.
    await waitFor(() => expect(screen.getByText("SpendLog")).toBeDefined());
    expect(screen.queryByLabelText("Project")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
  });
});
